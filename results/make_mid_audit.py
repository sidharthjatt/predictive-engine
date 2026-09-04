"""
make_mid_audit.py -- the daily audit trail for the MidCap150 universe.

A per-universe entry point. The body lives once in results/audit_step.py, which
took over from the three near-identical copies this file used to be one of; every
difference between them was a universe property universes/registry.py already
records. See that module for what moved and why the entry points stayed separate.

Outputs (MidCap150 universe):
  daily_holdings_mid.csv   every position, every day
  daily_summary_mid.csv    cash / mtm / total, every day
  daily_trades_mid.csv     every fill, with transaction cost
  daily_ranking_mid.csv    the score ranking at each rebalance
  daily_decisions_mid.csv  every rebalance: breadth, exposure, portfolio value, plan
  daily_skipped_mid.csv    orders created but not filled, with the reason
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_step
from universes.registry import REGISTRY


def main():
    """The step, as a function, so run.py can call it in process."""
    audit_step.run(REGISTRY["mid"])


if __name__ == "__main__":
    main()
