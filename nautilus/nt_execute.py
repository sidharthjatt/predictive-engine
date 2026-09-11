"""
nt_execute.py -- run the Nautilus execution engine for every selected combination.

WHY THIS IS A PIPELINE STEP AND nt_run.py IS NOT
    nt_run.run() is a function that backtests ONE (universe, arm, cadence). Until
    this file existed, nothing in the pipeline called it: Nautilus execution
    happened only when somebody ran verify_v34_arms.py or nt_run.py by hand, and
    only for the arms those scripts happened to name. A normal `run.py` invocation
    produced Nautilus INPUT (STEP 16 exports the score parquet) and no Nautilus
    OUTPUT at all.

    That mattered because Nautilus is the execution engine with exact accounting --
    order lifecycle, fees, tick grid, latency -- so its output is the ground truth
    for what actually happened, day by day. Having it for one arm at one cadence
    meant having it for one twelfth of what the pipeline produces.

WHAT IT WRITES, PER COMBINATION
    nautilus/reports/<universe>/<arm>[@r<n>]/
        orders_all.csv     EVERY order submitted, whatever became of it. A DENIED
                           or CANCELED order appears here and nowhere else.
        order_fills.csv    one row per order that produced a fill
        fills.csv          every fill
        positions.csv      position lifecycle records
        daily_equity.csv   date, cash, mtm, equity -- one row per trading day
        daily_holdings.csv date, symbol, qty, price, value -- the position book

WHAT IT SKIPS, AND WHY IT SAYS SO
    A frozen universe has no v3/v4 path -- its engine never calls v34_common -- and
    runs only at the default cadence. Those combinations are reported as NOT RUN
    with the reason rather than silently omitted, exactly as run.py reports them
    for the research side.

RUNTIME
    Measured at 4.3 s (58) to 7.5 s (mid) per backtest, so the twelve combinations
    of a full run cost about ninety seconds. It is a pipeline step because that is
    affordable, not because it is free.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results"), str(ROOT / "nautilus")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cadence
import config
import arms.registry as arm_reg
import universes.registry as uni_reg


def main():
    """The step, as a function, so run.py can call it in process."""
    import nt_run

    reb = cadence.selected()
    ran, skipped = [], []

    print("=" * 96)
    print(" NAUTILUS EXECUTION -- the order book, the trade book and the daily "
          "portfolio state,")
    print(" for every selected combination. This is the execution engine's own "
          "accounting, not")
    print(" the research engine's: exact fees, tick grid, latency and order "
          "lifecycle.")
    print("=" * 96)

    for u in uni_reg.selected():
        for a in arm_reg.selected():
            # run.py's arm_steps applies no refusals any more -- the two it had
            # were for the retired 58 and 74 -- so neither does this, and the two
            # halves of a run still cannot disagree about what is possible.
            U = nt_run.UNIVERSES[u.tag]
            strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"],
                               universe=u.tag, sizing=a.sizing, mode=a.mode,
                               rebal=reb)
            ran.append((u.tag, a.name, strat.rebalances))

    print("\n" + "=" * 96)
    print(f" NAUTILUS EXECUTION COMPLETE -- {len(ran)} combination(s) run at "
          f"cadence {reb}")
    for tag, arm, n in ran:
        print(f"    {tag:<6} {arm:<4} {n} rebalances")
    if skipped:
        print(f"\n NOT RUN ({len(skipped)}):")
        for tag, arm, why in skipped:
            print(f"    {tag:<6} {arm:<4} {why}")
    print("=" * 96)


if __name__ == "__main__":
    main()
