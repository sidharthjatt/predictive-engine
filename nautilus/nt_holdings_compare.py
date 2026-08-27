"""
nt_holdings_compare.py -- find the FIRST rebalance where the port's holdings stop
matching the reference engine's.

WHY
    Comparing daily equity showed the curves separating around May 2020, but the
    trades that day already differed in a way that only makes sense if the two
    portfolios were ALREADY holding different things. So the daily view was showing
    a symptom, not the cause.

    This compares the two portfolios at every rebalance date and stops at the first
    one where the held symbols or their quantities differ. That is the origin.

REFERENCE  results/metrics/daily_holdings_58.csv
PORT       recorded by the strategy during the run

Run: python3 nautilus/nt_holdings_compare.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nt_run


def main():
    strat = nt_run.run("2019-01-01", "2026-06-08")

    port = pd.DataFrame(strat.holdings_log)
    if port.empty:
        print("No holdings were recorded. Nothing to compare.")
        return
    port["date"] = pd.to_datetime(port["date"])

    ref = pd.read_csv(ROOT / "results" / "metrics" / "daily_holdings_58.csv",
                      parse_dates=["date"])

    dates = sorted(port["date"].unique())
    print(f"\n{'=' * 74}")
    print(f"HOLDINGS COMPARISON at {len(dates)} rebalance dates")
    print("=" * 74)

    first_bad = None
    for d in dates:
        p = {r["symbol"]: int(r["qty"]) for _, r in port[port["date"] == d].iterrows()}
        g = ref[ref["date"] == d]
        r = {row["symbol"]: int(row["qty"]) for _, row in g.iterrows()}
        if p != r:
            first_bad = (pd.Timestamp(d), p, r)
            break

    if first_bad is None:
        print("\n  Holdings match at every rebalance date.")
        return

    d, p, r = first_bad
    i = dates.index(d)
    prev = pd.Timestamp(dates[i - 1]) if i > 0 else None
    print(f"\n  FIRST mismatch: {d.date()}   (rebalance {i + 1} of {len(dates)})")
    if prev is not None:
        print(f"  Previous rebalance {prev.date()} matched exactly.")

    syms = sorted(set(p) | set(r))
    print(f"\n      {'symbol':<13}{'reference':>11}{'port':>9}{'diff':>9}")
    for s in syms:
        a, b = r.get(s, 0), p.get(s, 0)
        flag = "" if a == b else "   <--"
        print(f"      {s:<13}{a:>11}{b:>9}{b - a:>9}{flag}")

    # the fills that produced this state, in both systems
    lo = prev if prev is not None else d
    rt = pd.read_csv(ROOT / "results" / "metrics" / "daily_trades_58.csv",
                     parse_dates=["date"])
    rt = rt[(rt["date"] > lo) & (rt["date"] <= d)]
    pt = pd.DataFrame(strat.fills)
    if not pt.empty:
        pt["date"] = pd.to_datetime(pt["date"])
        pt = pt[(pt["date"] > lo) & (pt["date"] <= d)]

    print(f"\n  REFERENCE fills after {lo.date()} up to {d.date()}  ({len(rt)})")
    if len(rt):
        print(rt[["date", "action", "symbol", "qty", "price"]].to_string(index=False))
    print(f"\n  PORT fills after {lo.date()} up to {d.date()}  ({len(pt)})")
    if len(pt):
        print(pt[["date", "action", "symbol", "qty", "price"]].to_string(index=False))

    print("\n" + "=" * 74)
    print("  A symbol whose quantity differs by a small amount points at sizing.")
    print("  A symbol present in one list only points at a skipped or denied order.")
    print("=" * 74)


if __name__ == "__main__":
    main()
