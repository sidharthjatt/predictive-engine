"""
save_caches_step.py -- persist the working panels to their permanent homes.
==========================================================================

WHY THIS IS A PIPELINE STEP AND NOT A LINE AT THE END OF A FUNCTION
    Copying /tmp to results*/metrics/ is an ORDERING CONSTRAINT, not a tidy-up.
    nt_export_scores.py (STEP 16) reads the PERMANENT panel, so the copy has to
    happen before it. run_all.py knew that and said so:

        "AFTER the caches are persisted, not before ... Placing this earlier
         crashed the pipeline with 'v5_expanding_cache.csv missing'."

    It enforced the constraint by calling save_permanent_caches() between two
    hand-written run() calls. When S8 folded every step into one uniform
    PIPELINE_ORDER loop, the constraint had nowhere to live: the copy became a
    trailing call in run.py AFTER the whole loop, and STEP 16 moved in front of
    it. Every verification run in that session was warm -- the permanent caches
    already existed -- so nothing failed until the first genuinely cold run,
    which died at STEP 16 with exactly the message the old comment predicted.

    The constraint now lives in PIPELINE_ORDER, next to every other ordering
    constraint in this pipeline, where check_pipeline_order reads them and where
    `run.py --list` shows it. An ordering rule expressed as a position in a list
    cannot be lost by rewriting the loop that walks the list.

WHY THE STATIC CHECKER DOES NOT COVER THIS ONE
    check_pipeline_order deliberately EXCLUDES the panel caches from its
    producer/consumer graph -- see CACHES, "restored into /tmp before the run,
    not produced by any step". That exclusion is correct: on a warm run they are
    inputs that no step produces. Teaching it to treat this step as their
    producer would contradict that and risk false inversions, which are worse
    than the bug. The guard for this class is config.require_cache, which
    resolves the two locations explicitly, and whose own docstring already names
    this exact failure.

THE PAIRS COME FROM THE REGISTRY
    u.score_tmp -> u.score_cache and u.raw_tmp -> u.raw_cache, for every
    universe. Verified to reproduce run_all.py's eight hand-written pairs
    exactly. A new universe's panels are persisted with no edit here.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config                            # noqa: E402
from universes.registry import REGISTRY   # noqa: E402


def pairs():
    """(working copy, permanent copy) for every registered universe."""
    out = []
    for u in REGISTRY.values():
        out.append((Path(u.score_tmp), Path(u.score_cache)))
        out.append((Path(u.raw_tmp), Path(u.raw_cache)))
    return out


def main():
    """Copy every working panel that exists to its permanent home.

    A MISSING WORKING PANEL IS NOT AN ERROR. A selective run may not have built
    every universe, and a warm run may have restored some panels and rebuilt
    others. Only what is on disk is copied; what is absent keeps whatever
    permanent copy it already had.
    """
    print("Saving permanent caches...")
    n = 0
    for tmp, perm in pairs():
        if tmp.exists():
            # THE SIDECAR IS COPIED, NOT REGENERATED FROM THE REGISTRY. Writing
            # it here from u.raw_data_dir would stamp the CURRENT source onto a
            # panel built from whatever the source was when the panel was built
            # -- which is exactly the claim the sidecar exists to check, forged
            # by the step that persists it. A working panel with no sidecar is
            # refused rather than blessed on its way to a permanent home.
            side = config.cache_source_file(tmp)
            if not side.exists():
                raise config.CacheSourceError(
                    f"refusing to persist {tmp}: no source sidecar "
                    f"({side.name}).\n"
                    f"  It was written by something that does not record its "
                    f"source, or it survives from before source recording.\n"
                    f"  Delete it and rebuild with "
                    f"`./venv/bin/python run_all.py`.")
            perm.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(tmp, perm)
            shutil.copy(side, config.cache_source_file(perm))
            n += 1
    print(f"caches saved (restart-proof). {n} of {len(pairs())} panels persisted.")


if __name__ == "__main__":
    main()
