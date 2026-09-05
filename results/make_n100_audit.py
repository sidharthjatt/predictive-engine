"""
make_n100_audit.py -- the daily audit trail for the Nifty 100 universe.

A per-universe entry point. The body lives once in results/audit_step.py, which
took over from the three near-identical copies this file used to be one of; every
difference between them was a universe property universes/registry.py already
records. See that module for what moved and why the entry points stayed separate.

Outputs (Nifty 100 universe):
  daily_holdings_n100.csv   every position, every day
  daily_summary_n100.csv    cash / mtm / total, every day
  daily_trades_n100.csv     every fill, with transaction cost
  daily_ranking_n100.csv    the score ranking at each rebalance
  daily_decisions_n100.csv  every rebalance: breadth, exposure, portfolio value, plan
  daily_skipped_n100.csv    orders created but not filled, with the reason
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_step
from universes.registry import REGISTRY
import arms.registry as arm_reg


def main():
    """The step, as a function, so run.py can call it in process."""
    # ONE TRAIL PER SELECTED ARM. This step wrote exactly one, v2's, because
    # audit_step hardcoded breadth+invvol. The literal REGISTRY["n100"] subscript
    # is kept -- check_pipeline_order reads it to resolve daily_*_{tag}.csv to a
    # directory, and a loop variable there matches nothing.
    #
    # A FROZEN UNIVERSE IS NOT REACHED FROM HERE. n100 is live; the 58 and 74 go
    # through frozen/make_daily_audit.py, which is deliberately left on v2 only.
    for _a in arm_reg.selected():
        audit_step.run(REGISTRY["n100"], _a)


if __name__ == "__main__":
    main()
