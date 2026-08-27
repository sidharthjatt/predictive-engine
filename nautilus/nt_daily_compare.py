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

REFERENCE  results/metrics/daily_summary_58.csv  (built by make_daily_audit.py)
PORT       recorded by the strategy during the run

Run: python3 nautilus/nt_daily_compare.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nt_run

THRESHOLD_PCT = 0.5      # first day the curves differ by more than this


def main():
    strat = nt_run.run("2019-01-01", "2026-06-08")

    port = pd.DataFrame(strat.daily_equity)
    if port.empty:
        print("The strategy recorded no daily equity. Nothing to compare.")
        return
    port["date"] = pd.to_datetime(port["date"])
    port = port.set_index("date")["equity"]

    ref_path = ROOT / "results" / "metrics" / "daily_summary_58.csv"
    ref = pd.read_csv(ref_path, parse_dates=["date"]).set_index("date")["total"]

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
    rt = pd.read_csv(ROOT / "results" / "metrics" / "daily_trades_58.csv",
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
