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

REFERENCE  results_<universe>/metrics/daily_holdings_<universe>.csv  (results/make_audit.py)
PORT       recorded by the strategy during the run

Run: ./venv/bin/python nautilus/nt_holdings_compare.py --universe=nifty100
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nt_run
import paths
from config import read_table  # the one CSV/parquet reader: config.read_table


def _universe():
    """The universe named by --universe=<tag>; defaults to the first certified one.

    An unknown tag, including a retired short tag, exits 2 with the valid list.
    Until 2026-09-24 this tool read the retired 58's artefacts from
    results/metrics/ and could not run on any universe that exists.
    """
    from universes.registry import CERTIFIED, REGISTRY, argv_universes, check_tags
    picked = check_tags(argv_universes(sys.argv), nt_run.UNIVERSES)
    return REGISTRY[picked[-1] if picked else CERTIFIED[0]]


def main():
    u = _universe()
    strat = nt_run.run("2019-01-01", nt_run.UNIVERSES[u.tag]["end"], universe=u.tag)

    port = pd.DataFrame(strat.holdings_log)
    if port.empty:
        print("No holdings were recorded. Nothing to compare.")
        return
    port["date"] = pd.to_datetime(port["date"])

    ref = read_table(paths.tagged_artefact(u, "daily_holdings"),
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
    rt = read_table(paths.tagged_artefact(u, "daily_trades"),
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
