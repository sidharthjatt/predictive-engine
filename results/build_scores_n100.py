"""
build_scores_n100.py -- the Nifty 100 universe's raw panel and monthly scores

A per-universe entry point. The body lives once in results/build_scores_step.py,
which took over from the four copies this file used to be one of; every difference
between them was a universe property universes/registry.py records. See that module
for the mapping, and for why purge_mode is read from the registry rather than
written here.
\nThe index is excluded by pointing build_panel at a constituents-only directory,\nwhich u.prepare_data_dir() rebuilds; the panel's symbol set is then asserted\nagainst the registry's list.\n
Output caches: raw_panel_n100_20.csv and v_n100_expanding.csv in /tmp, copied to the permanent
results_n100/metrics by run_all.py at the end of the run.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_scores_step
from universes.registry import REGISTRY


def main(u):
    """The step, as a function, so run.py can call it in process."""
    # THE CONTRACT, AND WHY THIS STEP ONLY ACCEPTS ONE UNIVERSE.
    # main(u) is the declaration run.py dispatches on. This file is still the
    # per-n100 half of a pair, so it can only do n100's work -- and a step that
    # took a universe and quietly ignored it would be the "selection that silently
    # does less than it was asked" failure in its purest form. It verifies the
    # argument instead. The check goes when the pair collapses and the literals
    # below become u.
    assert u.tag == "n100", (
        f"{__name__} is n100's half of an uncollapsed pair; "
        f"invoked for {u.tag}")
    build_scores_step.run(REGISTRY["n100"])


if __name__ == "__main__":
    from universes.registry import REGISTRY as _R
    main(_R["n100"])
