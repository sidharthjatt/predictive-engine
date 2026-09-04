"""
attribution_v2.py -- per-symbol attribution for the SHIPPING arm (v2).

Built entirely from the existing trade logs. NOTHING IS REFIT OR RE-SCORED.
Source: results_{uni}/metrics/daily_trades_{uni}.csv, written by
make_{uni}_audit.py from backtest_exposure(..., mode="breadth") -- the v2 arm.

METHOD
    FIFO lot matching per symbol. A round trip is one matched buy-lot against one
    sell. Realised P&L is reported GROSS and NET of transaction costs; TC is
    allocated per share from each leg's own recorded tc.

WHAT IS NOT DERIVABLE HERE, AND IS NOT APPROXIMATED
    PER-SYMBOL CONTRIBUTION TO CAGR. CAGR is a property of the equity path, which
    compounds: a rupee earned in 2019 is not the same rupee as one earned in 2025,
    and capital freed by one name is redeployed into others. Realised P&L cannot
    be decomposed into CAGR additively without assuming away that redeployment.
    P&L SHARE IS REPORTED INSTEAD, and no CAGR figure is attached to a symbol.

THE REMOVAL FIGURE IS ARITHMETIC, NOT A RE-RUN
    "Return with the largest contributor removed" here means: subtract that
    symbol's net realised P&L from the total and express the remainder against
    the same starting capital. IT IS NOT the same as re-running the strategy on a
    universe without that name -- the model would have selected differently and
    the capital would have gone elsewhere. mid_jackknife.py does the true re-run.
    Both numbers are reported so the difference is visible.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import datetime as _dt
import numpy as np
import pandas as pd
import config, config_mid, config_n100

START = 1_000_000
UNIVERSES = {
    "n100": (config_n100.METRICS_DIR_N100, "n100", "NIFTY 100"),
    "mid": (config_mid.METRICS_DIR_MID, "mid", "MIDCAP150"),
}


def round_trips(df):
    """FIFO match. Returns per-round-trip records."""
    out = []
    for sym, g in df.groupby("symbol"):
        lots, g = [], g.sort_values("date")
        for _, r in g.iterrows():
            tc_ps = (r["tc"] / r["qty"]) if r["qty"] else 0.0
            if r["action"] == "BUY":
                lots.append([r["date"], float(r["price"]), int(r["qty"]), tc_ps])
            else:
                q = int(r["qty"])
                while q > 0 and lots:
                    bd, bp, bq, btc = lots[0]
                    m = min(bq, q)
                    gross = m * (float(r["price"]) - bp)
                    out.append({"symbol": sym, "buy_date": bd, "sell_date": r["date"],
                                "qty": m, "gross": gross,
                                "net": gross - m * (btc + tc_ps),
                                "days": (r["date"] - bd).days})
                    if bq > m:
                        lots[0][2] = bq - m
                    else:
                        lots.pop(0)
                    q -= m
    return pd.DataFrame(out)


def run(uni, md, tag, label, W):
    f = Path(md) / f"daily_trades_{tag}.csv"
    T = pd.read_csv(f, parse_dates=["date"])
    eq = pd.read_csv(Path(md) / "v2FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    R = round_trips(T)

    per = R.groupby("symbol").agg(
        net=("net", "sum"), gross=("gross", "sum"), trips=("net", "size"),
        wins=("net", lambda s: int((s > 0).sum())),
        avg_win=("net", lambda s: float(s[s > 0].mean()) if (s > 0).any() else 0.0),
        avg_loss=("net", lambda s: float(s[s < 0].mean()) if (s < 0).any() else 0.0),
        days_held=("days", "sum")).reset_index()
    per["win_rate"] = per["wins"] / per["trips"] * 100
    tot = per["net"].sum()
    per["share"] = per["net"] / tot * 100
    per = per.sort_values("net", ascending=False)

    fin = float(eq["strategy"].iloc[-1])
    W("=" * 104)
    W(f" PER-SYMBOL ATTRIBUTION -- v2 (breadth), the SHIPPING arm -- {label} ({uni})")
    W("=" * 104)
    W("")
    W(f"  WINDOW {eq.index[0].date()} to {eq.index[-1].date()}, {len(eq):,} trading days.")
    W("  Every figure below is on that window and no other.")
    # LOCAL time. pd.Timestamp(st_mtime, unit="s") renders UTC and printed 09:36
    # for a 15:06 file, which reads as a different file. Fixed 2026-09-02.
    _mt = _dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    W(f"  source {f.name}, {len(T):,} fills, mtime {_mt} (local)")
    W(f"  arm: backtest_exposure(mode='breadth', sizing='invvol'); no refit, no re-score")
    W("")
    W("  RECONCILIATION -- how much of the result realised P&L explains")
    W(f"    start capital                  Rs {START:>14,.0f}")
    W(f"    final equity                   Rs {fin:>14,.0f}")
    W(f"    total gain                     Rs {fin-START:>14,.0f}")
    W(f"    sum of NET realised round trips Rs {tot:>13,.0f}")
    W(f"    unexplained (open positions at the end, and compounding)  "
      f"Rs {fin-START-tot:,.0f}")
    W("    Realised P&L does not equal the equity gain: positions open on the last")
    W("    day are never realised, and a rupee earned early compounds. Shares below")
    W("    are shares OF REALISED P&L, not of the equity gain.")
    W("")
    W(f"  symbols traded {len(per)}   round trips {len(R):,}   "
      f"overall win rate {(R['net'] > 0).mean()*100:.1f}%")
    W("")
    W("  TOP 15 BY NET REALISED P&L")
    W(f"  {'symbol':<14}{'net Rs':>13}{'share%':>8}{'trips':>7}{'win%':>7}"
      f"{'avg win':>11}{'avg loss':>11}{'days held':>10}")
    for _, r in per.head(15).iterrows():
        W(f"  {r['symbol']:<14}{r['net']:>13,.0f}{r['share']:>8.2f}{r['trips']:>7.0f}"
          f"{r['win_rate']:>7.0f}{r['avg_win']:>11,.0f}{r['avg_loss']:>11,.0f}"
          f"{r['days_held']:>10.0f}")
    W("")
    W("  BOTTOM 5 BY NET REALISED P&L")
    for _, r in per.tail(5).iterrows():
        W(f"  {r['symbol']:<14}{r['net']:>13,.0f}{r['share']:>8.2f}{r['trips']:>7.0f}"
          f"{r['win_rate']:>7.0f}{r['avg_win']:>11,.0f}{r['avg_loss']:>11,.0f}"
          f"{r['days_held']:>10.0f}")
    W("")
    W("  CONCENTRATION")
    for k in (1, 3, 5, 10):
        W(f"    top {k:>2} names: {per.head(k)['share'].sum():>6.2f}% of net realised P&L"
          f"   ({', '.join(per.head(k)['symbol'])})" if k <= 5 else
          f"    top {k:>2} names: {per.head(k)['share'].sum():>6.2f}% of net realised P&L")
    pos = per[per["net"] > 0]
    W(f"    {len(pos)} of {len(per)} symbols are net positive; the losers cost "
      f"Rs {per[per['net'] < 0]['net'].sum():,.0f}")
    W("")
    top = per.iloc[0]
    W("  LARGEST CONTRIBUTOR REMOVED -- ARITHMETIC, NOT A RE-RUN")
    W(f"    largest contributor            {top['symbol']} at Rs {top['net']:,.0f} "
      f"({top['share']:.2f}% of realised P&L)")
    W(f"    realised P&L without it        Rs {tot-top['net']:,.0f}  "
      f"(from Rs {tot:,.0f})")
    W(f"    that is a {(1-(tot-top['net'])/tot)*100:.1f}% reduction in realised P&L")
    W("    THIS IS NOT the strategy re-run without that name. The model would have")
    W("    selected differently and the capital would have gone elsewhere. A true")
    W("    leave-one-out requires re-running the engine; mid_jackknife.py does that.")
    W("")
    per.to_csv(Path(md) / "attribution_v2_per_symbol.csv", index=False)
    R.to_csv(Path(md) / "attribution_v2_round_trips.csv", index=False)
    W(f"  written: attribution_v2_per_symbol.csv, attribution_v2_round_trips.csv")
    W("")


def main():
    out = []
    for uni, (md, tag, label) in UNIVERSES.items():
        run(uni, md, tag, label, out.append)
        out.append("")
    (ROOT / "diagnostics" / "attribution_v2.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
