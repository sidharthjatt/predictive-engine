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
from universes.registry import REGISTRY


def main():
    """The step, as a function, so run.py can call it in process."""
    # NAMED LITERALLY, NOT LOOPED. check_pipeline_order reads REGISTRY["<tag>"] out
    # of the source to resolve daily_*_{tag}.csv to a directory; REGISTRY[tag] with a
    # variable matches nothing, and the checker silently loses both producer edges.
    audit_step.run(REGISTRY["58"])
    audit_step.run(REGISTRY["74"])


if __name__ == "__main__":
    main()
