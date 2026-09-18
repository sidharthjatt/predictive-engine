"""
liquidity_participation.py -- how much of the market each fill would actually be.

MEASUREMENT ONLY. Nothing is changed by this script.

THE VOLUME COLUMN IS NOT IN THE PANEL
    The task described using "the volume column already in the panel". It is not
    there: the score panel is date,symbol,open,close,score,year and the raw panel
    carries the 17 features, y_rank and scorable but no volume. build_panel never
    keeps it (build_scores_n100.py:44 lists the columns retained).

    Volume IS in the source CSVs, so it is read from those here and aligned to each
    symbol's own trading days. That is the same source nt_data reads volume from
    when it builds bars, so the two agree.

WHAT PARTICIPATION MEANS HERE
    order quantity / median daily volume over the prior N trading days, as a
    percentage. The median is taken over days STRICTLY BEFORE the fill date, so it
    is knowable at the time the order is sent. 20-day and 60-day windows are both
    reported.

CAPITAL SCALING
    The backtest runs Rs 10,00,000. Participation scales linearly with capital
    because every position is a fixed fraction of the portfolio, so the quantity at
    Rs 50,00,000 is 5x and at Rs 2,00,00,000 is 20x. The fills themselves are not
    re-simulated at those sizes -- doing so would change which names are affordable
    and confound the measurement. This reports what the SAME trades would represent
    at larger size, which is the question being asked.

    That linearity is exact only while the strategy's decisions are unchanged. At a
    size where participation is genuinely prohibitive, a real implementation would
    have to trade differently, so the large-capital figures are an upper bound on
    tradeability rather than a forecast of what would happen.
"""
import sys
import warnings

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import config
from universes.registry import REGISTRY

CAPITALS = [(1_000_000, "Rs 10,00,000  (the backtest)"),
            (5_000_000, "Rs 50,00,000"),
            (20_000_000, "Rs 2,00,00,000")]
BANDS = [("under Rs 10", 0, 10), ("Rs 10-50", 10, 50),
         ("Rs 50-250", 50, 250), ("above Rs 250", 250, np.inf)]
FLAG = 10.0          # participation percentage worth listing individually

# THE SAME THREE FACTS, FROM THE REGISTRY SINCE STEP 7. raw_data_dir is the source
# folder (index included), not data_dir, because volume_panel() resolves
# "<sym>.csv" by name and never globs.
UNIV = [
    ("nifty100", REGISTRY["nifty100"].metrics_dir, REGISTRY["nifty100"].raw_data_dir,
     REGISTRY["nifty100"].symbol_list),
    ("midcap150", REGISTRY["midcap150"].metrics_dir, REGISTRY["midcap150"].raw_data_dir,
     REGISTRY["midcap150"].symbol_list),
]


def volume_panel(raw_dir, symbols):
    """{symbol: Series of daily volume indexed by date} from the source CSVs."""
    out = {}
    for sym in symbols:
        f = Path(raw_dir) / f"{sym}.csv"
        if not f.exists():
            continue
        d = config.read_price_csv(f)
        if "volume" not in d.columns:
            continue
        s = d[["date", "volume"]].dropna().set_index("date")["volume"].sort_index()
        out[sym] = s[s > 0]
    return out


def measure(tag, mdir, raw_dir, symbols):
    tr = pd.read_csv(Path(mdir) / f"daily_trades_{tag}.csv", parse_dates=["date"])
    vol = volume_panel(raw_dir, symbols)

    rows = []
    missing = set()
    for _, t in tr.iterrows():
        sym, d, q = t["symbol"], t["date"], float(t["qty"])
        v = vol.get(sym)
        if v is None:
            missing.add(sym)
            continue
        prior = v[v.index < d]
        m20 = float(prior.tail(20).median()) if len(prior) >= 1 else np.nan
        m60 = float(prior.tail(60).median()) if len(prior) >= 1 else np.nan
        rows.append({"date": d, "symbol": sym, "action": t["action"], "qty": q,
                     "price": float(t["price"]), "med20": m20, "med60": m60,
                     "n_prior": len(prior)})
    f = pd.DataFrame(rows)
    if missing:
        print(f"    NOTE: no volume data for {len(missing)} symbols: "
              f"{', '.join(sorted(missing)[:8])}")
    return f


def band_of(p):
    for name, lo, hi in BANDS:
        if lo <= p < hi:
            return name
    return BANDS[-1][0]


def main():
    print("=" * 108)
    print(" LIQUIDITY PARTICIPATION -- order quantity as a share of median daily volume")
    print(" Measurement only. Nothing is changed.")
    print("=" * 108)

    for tag, mdir, raw_dir, syms in UNIV:
        print(f"\n{'='*108}\n {tag.upper()}\n{'='*108}")
        f = measure(tag, mdir, raw_dir, syms)
        f["band"] = f["price"].apply(band_of)
        print(f"  fills measured {len(f):,} | symbols {f['symbol'].nunique()} | "
              f"window {f['date'].min().date()} -> {f['date'].max().date()}")
        print(f"  median prior-day history per fill: {int(f['n_prior'].median()):,} days")

        for cap, lab in CAPITALS:
            mult = cap / 1_000_000
            print(f"\n  {'-'*104}")
            print(f"  CAPITAL {lab}   (quantity x{mult:g})")
            print(f"  {'-'*104}")
            for win, col in (("20d", "med20"), ("60d", "med60")):
                p = (f["qty"] * mult / f[col] * 100).replace([np.inf, -np.inf], np.nan)
                g = pd.DataFrame({"band": f["band"], "p": p}).dropna()
                print(f"\n    participation vs prior-{win} median daily volume")
                print(f"      {'band':<16}{'fills':>7}{'median':>10}{'p90':>10}"
                      f"{'p99':>10}{'max':>12}")
                for name, _, _ in BANDS:
                    s = g[g["band"] == name]["p"]
                    if not len(s):
                        print(f"      {name:<16}{0:>7}{'--':>10}{'--':>10}{'--':>10}{'--':>12}")
                        continue
                    print(f"      {name:<16}{len(s):>7}{s.median():>9.3f}%"
                          f"{s.quantile(.90):>9.3f}%{s.quantile(.99):>9.3f}%"
                          f"{s.max():>11.3f}%")
                s = g["p"]
                print(f"      {'ALL':<16}{len(s):>7}{s.median():>9.3f}%"
                      f"{s.quantile(.90):>9.3f}%{s.quantile(.99):>9.3f}%{s.max():>11.3f}%")
                over = g[g["p"] > FLAG]
                print(f"      fills above {FLAG:g}% participation: {len(over)} "
                      f"({len(over)/len(g)*100:.2f}% of fills)")

            # the individual list, on the 20-day window, for this capital
            p20 = (f["qty"] * mult / f["med20"] * 100).replace([np.inf, -np.inf], np.nan)
            hit = f.assign(part=p20)
            hit = hit[hit["part"] > FLAG].sort_values("part", ascending=False)
            if len(hit):
                print(f"\n    EVERY FILL ABOVE {FLAG:g}% PARTICIPATION (prior-20d median), "
                      f"{len(hit)} of {len(f)}")
                print(f"      {'date':<12}{'symbol':<13}{'side':<6}{'qty':>10}"
                      f"{'price':>10}{'med vol 20d':>14}{'part%':>9}")
                for _, x in hit.iterrows():
                    print(f"      {str(x['date'].date()):<12}{x['symbol']:<13}"
                          f"{x['action']:<6}{int(x['qty']*mult):>10,}{x['price']:>10.2f}"
                          f"{int(x['med20']):>14,}{x['part']:>8.2f}%")
            else:
                print(f"\n    No fill exceeds {FLAG:g}% participation at this capital.")


if __name__ == "__main__":
    main()
