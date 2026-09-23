"""
build_scores.py -- one universe's raw panel and monthly scores

THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
build_scores_mid.py and build_scores_n100.py, which differed in nothing but the
registry key they passed and the filenames their docstrings quoted. Step 3 of the
collapse; the contract that made it possible is 5c636cf.

The body lives once in results/build_scores_step.py, which took over from the four
copies the two merged files used to be among; every difference between those was a
universe property universes/registry.py records. See that module for the mapping,
and for why purge_mode is read from the registry rather than written here.

The index is excluded by pointing build_panel at a constituents-only directory,
which u.prepare_data_dir() rebuilds; the panel's symbol set is then asserted
against the registry's list.

Output caches: u.raw_cache and u.score_cache -- cache/<tag>/raw_panel_<tag>_20.csv
and cache/<tag>/v_<tag>_expanding.csv, each with a .source sidecar holding the
source key. NO FILENAME IS WRITTEN HERE; they are registry attributes, which is
why adding a universe costs no edit to this file.

INVOKED TWICE PER FULL RUN, once per universe, from two PIPELINE_ORDER rows that
keep their own labels -- STEP 10a for mid, STEP 10e for n100. The labels are not
renumbered by the merge: a step's name means what it meant in every log written
before it, the same rule the 2026-09-11 retirement set when it left STEPS 0-9 and
11-14 as gaps.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_scores_step


def main(u):
    """The step, as a function, so run.py can call it in process.

    NO TRANSITIONAL ASSERT AND NO REGISTRY SUBSCRIPT. It takes the universe and
    uses it, which is what steps 3-7 exist to produce and what
    transitional_asserts_check.py is watching for.
    """
    build_scores_step.run(u)


if __name__ == "__main__":
    # STANDALONE, BY TAG. `python3 results/build_scores.py mid` -- the universe is
    # an argument here too, because there is no longer a file per universe to
    # imply it.
    from universes.registry import REGISTRY
    if len(sys.argv) != 2 or sys.argv[1] not in REGISTRY:
        raise SystemExit(f"usage: {Path(__file__).name} <universe>   "
                         f"known: {', '.join(sorted(REGISTRY))}")
    main(REGISTRY[sys.argv[1]])
