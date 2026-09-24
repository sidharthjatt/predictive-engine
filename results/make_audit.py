"""
make_audit.py -- the daily audit trail for one universe.

THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
make_mid_audit.py and make_n100_audit.py, which differed in nothing but the
registry key they passed and the filenames their docstrings quoted. Step 4 of the
collapse; the contract that made it possible is 5c636cf.

The body lives once in results/audit_step.py, which took over from the three
near-identical copies the merged files used to be among; every difference between
those was a universe property universes/registry.py already records.

Outputs, per selected arm, named by audit_step.artefact_tag(u, arm) -- so the
universe tag, the arm and the cadence/profile suffixes all come from the run's own
axes and NO FILENAME IS WRITTEN HERE:

  daily_holdings_<tag>.csv   every position, every day
  daily_summary_<tag>.csv    cash / mtm / total, every day
  daily_trades_<tag>.csv     every fill, with transaction cost
  daily_ranking_<tag>.csv    the score ranking at each rebalance
  daily_decisions_<tag>.csv  every rebalance: breadth, exposure, value, plan
  daily_skipped_<tag>.csv    orders created but not filled, with the reason

INVOKED TWICE PER FULL RUN, once per universe, from two PIPELINE_ORDER rows that
keep their own labels -- STEP 10c for midcap150, STEP 10g for nifty100.

THE PER-UNIVERSE REGISTRY SUBSCRIPT IS GONE, AND check_pipeline_order NO LONGER
NEEDS IT. The merged files kept that literal deliberately: the scanner read it to
resolve daily_*_{tag}.csv to a directory, and their comment said "a loop variable
there matches nothing". The scanner now takes the universe from PIPELINE_ORDER's
third field instead -- the declaration the literal was restating. Verified: the
four `audit before chart` edges survive the merge.

AND THIS DOCSTRING MUST NOT SPELL THAT SUBSCRIPT OUT. check_pipeline_order scans
SOURCE TEXT, comments and docstrings included, so writing the literal here bound a
phantom tag to BOTH pipeline rows: STEP 10g then saw two candidate directories,
could not choose, and dropped nifty100's edges to unresolved. Prose about a name is
indistinguishable from the name to a text scanner -- the same trap
transitional_asserts_check.py hit when its own marker comment matched its regex.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_step
import arms.registry as arm_reg


def main(u):
    """The step, as a function, so run.py can call it in process."""
    # ONE TRAIL PER SELECTED ARM. This step wrote exactly one, v2's, because
    # audit_step hardcoded breadth+invvol.
    #
    # A FROZEN UNIVERSE IS NOT REACHED FROM HERE. midcap150 and nifty100 are live; the retired
    # universes went through frozen/make_daily_audit.py, deliberately left on v2 only.
    for _a in arm_reg.selected():
        audit_step.run(u, _a)


if __name__ == "__main__":
    # STANDALONE, BY TAG. There is no longer a file per universe to imply which.
    from universes.registry import REGISTRY
    if len(sys.argv) != 2 or sys.argv[1] not in REGISTRY:
        raise SystemExit(f"usage: {Path(__file__).name} <universe>   "
                         f"known: {', '.join(sorted(REGISTRY))}")
    main(REGISTRY[sys.argv[1]])
