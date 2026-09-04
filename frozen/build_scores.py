"""
build_scores.py -- the 58-stock universe's raw panel and monthly scores

A per-universe entry point. The body lives once in results/build_scores_step.py,
which took over from the four copies this file used to be one of; every difference
between them was a universe property universes/registry.py records. See that module
for the mapping, and for why purge_mode is read from the registry rather than
written here.

FROZEN. This universe is retired: its published numbers must not move. The registry
records purge_mode="calendar" for it -- the DEFECTIVE calendar purge, kept
deliberately -- and build_scores_step.run() reads it from there and calls the
frozen-write guard, both keyed off u.frozen.

Output caches: raw_panel_20.csv and v5_expanding.csv in /tmp, copied to the permanent
results/metrics by run_all.py at the end of the run.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_scores_step
from universes.registry import REGISTRY


def main():
    """The step, as a function, so run.py can call it in process."""
    build_scores_step.run(REGISTRY["58"])


if __name__ == "__main__":
    main()
