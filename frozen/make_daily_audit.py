"""
make_daily_audit.py -- the daily audit trail for the RETIRED 58 and 74 universes.

A per-universe entry point. The body lives once in results/audit_step.py.

FROZEN. Both universes here are retired: their published numbers must not move.
audit_step.run() keys the two pins off u.frozen -- it passes value_at_open=False
(the pre-2026-09-04 close-valued sizing) and calls the frozen-write guard -- so
the freeze travels with the universe rather than with this file.

Outputs (both universes): daily_holdings_/summary_/trades_/ranking_/decisions_/
skipped_ {58,74}.csv, into results/metrics and results74/metrics respectively.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_step
from universes.registry import REGISTRY, selected_tags


def main():
    """The step, as a function, so run.py can call it in process."""
    # NAMED LITERALLY, NOT LOOPED. check_pipeline_order reads REGISTRY["<tag>"] out
    # of the source to resolve daily_*_{tag}.csv to a directory; REGISTRY[tag] with a
    # variable matches nothing, and the checker silently loses both producer edges.
    #
    # THE GUARDS KEEP THE LITERALS. A universe can be removed from the registry, so
    # each call is conditional -- but the condition is written around the literal
    # subscript, not in place of it, because REGISTRY_CALL matches the text
    # `REGISTRY["58"]` wherever it appears and does not care that it sits inside an
    # `if`. Rewriting this as a loop over REGISTRY would run correctly and blind the
    # checker, which is the failure this comment has existed to prevent since S5.
    # Verified by scanning this file before and after: identical edge set.
    # SELECTION, NOT REGISTRATION. `--universe 58` leaves 74 registered but
    # unselected, and this step used to do 74's work anyway -- writing artefacts
    # for a universe the caller did not ask for. selected_tags() defaults to every
    # registered universe, so a standalone run of this file is unchanged.
    # The literal REGISTRY["<tag>"] subscripts below are kept deliberately:
    # check_pipeline_order reads them to resolve this step's outputs, and only the
    # GUARD moved to the selection, not the subscript.
    SEL = set(selected_tags())
    if "58" in SEL:
        audit_step.run(REGISTRY["58"])
    else:
        print("  58 not selected for this run -- skipping its audit")
    if "74" in SEL:
        audit_step.run(REGISTRY["74"])
    else:
        print("  74 not selected for this run -- skipping its audit")


if __name__ == "__main__":
    main()
