"""
nt_daily_compare.py -- find the FIRST day the Nautilus port diverges from the
reference engine, and show what traded on that day in each system.

WHY THIS EXISTS
    Chasing a gap by looking at the final equity and guessing at causes failed
    three times in a row. Every cause that was actually found came from tracing one
    thing end to end: the momentum mismatch showed up on the first rebalance, and
    the execution bug showed up in a single order.

    So this compares the two equity curves day by day, stops at the first day where
    they separate by more than a threshold, and prints both systems' trades for
    that day. Whatever is different will be visible there.

REFERENCE  results_<universe>/metrics/daily_summary_<universe>.csv  (results/make_audit.py)
PORT       recorded by the strategy during the run

Run: ./venv/bin/python nautilus/nt_daily_compare.py --universe=nifty100
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

THRESHOLD_PCT = 0.5      # first day the curves differ by more than this


def main():
    u = _universe()
    strat = nt_run.run("2019-01-01", nt_run.UNIVERSES[u.tag]["end"], universe=u.tag)

    port = pd.DataFrame(strat.daily_equity)
    if port.empty:
        print("The strategy recorded no daily equity. Nothing to compare.")
        return
    port["date"] = pd.to_datetime(port["date"])
    port = port.set_index("date")["equity"]

    ref_path = paths.tagged_artefact(u, "daily_summary")
    ref = read_table(ref_path, parse_dates=["date"]).set_index("date")["total"]

    common = port.index.intersection(ref.index)
    print(f"\n{'=' * 74}")
    print(f"DAILY COMPARISON  ({len(common):,} common trading days)")
    print("=" * 74)

    p, r = port.loc[common], ref.loc[common]
    dev = (p / r - 1) * 100

    print(f"  final reference : Rs {r.iloc[-1]:>12,.0f}")
    print(f"  final port      : Rs {p.iloc[-1]:>12,.0f}   ({dev.iloc[-1]:+.2f}%)")

    bad = dev[dev.abs() > THRESHOLD_PCT]
    if bad.empty:
        print(f"\n  The curves never separate by more than {THRESHOLD_PCT}%.")
        return

    d0 = bad.index[0]
    i = list(common).index(d0)
    print(f"\n  FIRST divergence beyond {THRESHOLD_PCT}%: {d0.date()}  "
          f"({dev.loc[d0]:+.2f}%)")
    print(f"\n  equity around that day:")
    print(f"      {'date':<12}{'reference':>14}{'port':>14}{'dev %':>9}")
    for k in range(max(0, i - 3), min(len(common), i + 3)):
        d = common[k]
        print(f"      {str(d.date()):<12}{r.loc[d]:>14,.0f}{p.loc[d]:>14,.0f}"
              f"{dev.loc[d]:>8.2f}%")

    # what traded, in each system, on and just before that day
    lo = common[max(0, i - 3)]
    rt = read_table(paths.tagged_artefact(u, "daily_trades"),
                     parse_dates=["date"])
    rt = rt[(rt["date"] >= lo) & (rt["date"] <= d0)]
    print(f"\n  REFERENCE trades {lo.date()} .. {d0.date()}  ({len(rt)})")
    if len(rt):
        print(rt[["date", "action", "symbol", "qty", "price", "value", "tc"]]
              .to_string(index=False))

    pt = pd.DataFrame(strat.fills)
    if not pt.empty:
        pt["date"] = pd.to_datetime(pt["date"])
        pt = pt[(pt["date"] >= lo) & (pt["date"] <= d0)]
    print(f"\n  PORT trades {lo.date()} .. {d0.date()}  ({len(pt)})")
    if len(pt):
        print(pt.to_string(index=False))

    print("\n" + "=" * 74)
    print("  Compare the two trade lists above: a symbol present in one and not the")
    print("  other, or the same symbol at a different quantity or price, is the cause.")
    print("=" * 74)


if __name__ == "__main__":
    main()
