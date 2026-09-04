"""
make_daily_audit.py -- a complete daily audit trail.
It runs the official v2 backtest unchanged and simply passes an audit dict into it.
SAFETY: the script verifies for itself that the equity curve matches the official
one exactly, and stops if it does not.

Outputs (both universes):
  daily_holdings_*.csv  every day, every stock : qty, price, value, weight%
  daily_summary_*.csv   every day              : n_stocks, cash, mtm, total, inv%, cash%
  daily_trades_*.csv    every BUY/SELL         : date, symbol, qty, price, tc
  daily_ranking_*.csv   every rebalance        : rank, score, vol60, target weight, action
  daily_decisions_*.csv every rebalance        : breadth, exposure, portfolio value, plan
  daily_skipped_*.csv   orders created but not filled, with the reason
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_guard import guard as _frozen_guard
import config, config74
from engine_core import precompute
from test_exposure import backtest_exposure
def cache(tmp, perm):
    if Path(perm).exists(): return perm
    if Path(tmp).exists():  return tmp
    raise FileNotFoundError(f"{perm} / {tmp} missing -- run run_all.py first")
def run(tmp, perm, mdir, y_end, tag):
    print(f"\n{'='*74}\n{tag} UNIVERSE\n{'='*74}")
    p = pd.read_csv(cache(tmp, perm), parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px); mom20 = px / px.shift(20) - 1
    # WINDOW FROZEN: retired universe -- serves only the retired 58/74. Their published
    # numbers must not move, so this window is deliberately left on the old
    # year cut while the live universes moved to config.BT_START_DATE/BT_END_DATE.
    bd = px.index[(px.index.year >= 2019) & (px.index.year <= y_end)]

    audit = {"holdings": [], "summary": [], "trades": [], "ranking": [], "decisions": [], "skipped": []}
    # FROZEN 58/74 ONLY: this script serves no live universe. value_at_open=False
    # pins the pre-2026-09-04 close-valued sizing. It must stay in lockstep with
    # engine_v2_final*.py, because the SAFETY check below compares this curve
    # against v2FINAL_equity.csv and would fail if only one side moved.
    eq, tc, ntr, expo = backtest_exposure(px, op, sc, bd, pc, mom20,
                                          mode="breadth", audit=audit,
                                          value_at_open=False)

    # ---- SAFETY: does this match the official equity curve? ----
    off = pd.read_csv(Path(mdir) / "v2FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    diff = float((eq - off["strategy"].reindex(eq.index)).abs().max())
    status = "MATCH" if diff < 0.01 else f"*** MISMATCH Rs {diff:.2f} ***"
    print(f"  equity vs official v2FINAL_equity.csv : {status}")
    if diff >= 0.01:
        print("  !! audit logging changed something -- do not go further")
        return

    M = Path(mdir)
    h = pd.DataFrame(audit["holdings"]); s = pd.DataFrame(audit["summary"])
    t = pd.DataFrame(audit["trades"])
    h.to_csv(M / f"daily_holdings_{tag}.csv", index=False)
    s.to_csv(M / f"daily_summary_{tag}.csv", index=False)
    t.to_csv(M / f"daily_trades_{tag}.csv", index=False)
    rkdf = pd.DataFrame(audit["ranking"]); dcdf = pd.DataFrame(audit["decisions"])
    rkdf.to_csv(M / f"daily_ranking_{tag}.csv", index=False)
    dcdf.to_csv(M / f"daily_decisions_{tag}.csv", index=False)
    skdf = pd.DataFrame(audit["skipped"])
    skdf.to_csv(M / f"daily_skipped_{tag}.csv", index=False)
    if len(skdf):
        print(f"  SKIPPED orders: {len(skdf)}")
        print(skdf["reason"].value_counts().to_string().replace("\n", "\n    "))
    else:
        print("  SKIPPED orders: 0")
    print(f"  rebalance (decision) days: {len(dcdf)} | ranking rows: {len(rkdf):,}")

    print(f"  trades logged : {len(t):,}   (engine reported {ntr:,})"
          f"   {'OK' if len(t)==ntr else '*** COUNT MISMATCH ***'}")
    print(f"  daily rows    : {len(s):,} days | holdings rows {len(h):,}")
    print(f"  avg stocks held: {s['n_stocks'].mean():.1f} | "
          f"avg cash {s['cash_pct'].mean():.1f}% | final Rs {s['total'].iloc[-1]:,.0f}")
    print(f"\n  saved -> daily_holdings_{tag}.csv / daily_summary_{tag}.csv / daily_trades_{tag}.csv")

    print(f"\n  --- SAMPLE: latest day ({s['date'].iloc[-1].date()}) ---")
    last = h[h["date"] == h["date"].max()]
    print(last[["symbol","qty","price","value","weight_pct"]].to_string(index=False))
    r = s.iloc[-1]
    print(f"  cash Rs {r['cash']:,.0f} ({r['cash_pct']}%) | holdings Rs {r['mtm']:,.0f} "
          f"({r['invested_pct']}%) | TOTAL Rs {r['total']:,.0f}")


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. This body used to run at module level, so
    importing this file executed the whole step as a side effect -- which is why
    the pipeline could only ever spawn it as a subprocess.
    """
    # THE FROZEN GUARD MOVED IN HERE WITH THE WORK. At module level it fired on
    # IMPORT, so run.py could not load this file at all. It guards the WRITE, so
    # it belongs where the writing happens.
    _frozen_guard("58/74")   # refuses unless ALLOW_FROZEN_WRITE=1; run_all.py sets it

    run("/tmp/v5_expanding.csv",  "results/metrics/v5_expanding_cache.csv",
        config.METRICS_DIR, 2026, "58")
    run("/tmp/v74_expanding.csv", "results74/metrics/v74_expanding_cache.csv",
        config74.METRICS_DIR_74, 2025, "74")


if __name__ == "__main__":
    main()
