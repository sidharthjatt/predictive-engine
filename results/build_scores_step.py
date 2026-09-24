"""
build_scores_step.py -- the raw panel and monthly score panel, once, for any universe.
======================================================================================

WHAT THIS REPLACES
    Four files carried the same body: two retired-universe scripts (deleted 2026-09-11),
    build_scores_mid.py and build_scores_n100.py. Each said in its own docstring that
    it was a copy of the one before it -- a chain of copies, each one universe
    further from the original.

    Every difference between them is a universe property universes/registry.py
    records:

        data directory   u.prepare_data_dir()
        raw panel out    u.raw_cache
        score panel out  u.score_cache
        purge mode       u.purge_mode        <- see below, this one is load-bearing
        index exclusion  u.index_name
        symbol check     u.symbols()

THE PURGE MODE IS A PROPERTY OF THE UNIVERSE, NOT OF THIS FILE
    The two deleted retired universes were scored with purge_mode="calendar", which
    engine_core.score_monthly documents as DEFECTIVE -- it underflows on a holiday
    cluster. They kept it because they were frozen and their published numbers
    could not move. Every remaining universe takes the corrected "trading" value.

    Before this merge that fact lived as a literal in two files and as an omission
    in the other two, with nothing connecting them: a reader had to notice that
    build_scores_mid.py did NOT pass purge_mode and know why. It is now read from
    u.purge_mode, so the setting travels with the universe rather than with
    whichever file happens to score it.

    midcap150 and nifty100 must resolve "trading". That is
    asserted explicitly, per universe, rather than left to be inferred.

SEEDS ARE UNIVERSE-INVARIANT
    All four files listed the same ten seeds. That is not a universe property -- it
    is the production ensemble, identical everywhere so the comparison between
    universes stays fair -- so it is one constant here rather than a registry field.
"""
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config                                                  # noqa: E402
from engine_core import build_panel, score_monthly, HORIZON   # noqa: E402
from features_v2 import FEATS_V2                              # noqa: E402

# The production ensemble. Identical in all four originals; not a universe property.
SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]


def run(u):
    """Build the raw panel and the monthly score panel for one universe.

    THE CACHED-PANEL SKIP LIVES HERE. The step that owns the panel owns the
    decision not to rebuild it.

    REUSE IS DECIDED BY CONTENT. Both panels are reused only when their sidecars
    carry the source key of the constituent farm as it is now -- every CSV name
    and the sha256 of its bytes (config.cache_staleness). Adding, removing or
    editing a CSV is a miss; the line printed says which names moved and the
    panels are rebuilt. Until 2026-09-23 the check was the source directory's
    name, and removing SUZLON.csv left the midcap50 panel in use with SUZLON in it.

    --fresh deletes the selected universes' panels before the loop, so this
    finds none and builds.
    """
    stale = [(what, config.cache_staleness(path, u))
             for what, path in (("score panel", u.score_cache),
                                ("raw panel", u.raw_cache))]
    stale = [(w, why) for w, why in stale if why is not None]
    if not stale:
        print(f"    score panel current, skipping build ({u.score_cache})", flush=True)
        return
    for what, why in stale:
        print(f"    REBUILDING {u.tag}: {what} {why}", flush=True)

    data_dir = u.prepare_data_dir()
    want = u.symbols()
    # THE KEY IS TAKEN BEFORE THE BUILD, from the files build_panel is about to
    # read, and written beside both panels after it.
    key = config.source_key_for(u)
    u.score_cache.parent.mkdir(parents=True, exist_ok=True)

    if want is None:
        print("[1/2] Building raw panel...", flush=True)
    else:
        print(f"[1/2] Building raw panel for {len(want)} {u.label} stocks...", flush=True)
    t0 = time.time()
    raw = build_panel(HORIZON, data_dir=data_dir)

    if u.index_name is not None:
        # THE INDEX IS EXCLUDED, AND THAT IS ASSERTED RATHER THAN ASSUMED.
        # build_panel globs its data_dir, so it is pointed at a constituents
        # directory that holds no index file. A bare glob over the source folder
        # would have made the index one more tradable name -- the error this project
        # made once before, when an index was averaged into its own constituent
        # basket and the result was labelled as the benchmark.
        got = set(raw["symbol"].unique())
        assert u.index_name not in got, "the index entered the panel as a tradable symbol"
        missing = set(want) - got
        print(f"    symbols in panel: {len(got)} of {len(want)}"
              + (f" | dropped for insufficient history: {sorted(missing)}" if missing else ""))
    else:
        got = set(raw["symbol"].unique())

    keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
    raw = raw[keep]
    config.write_panel(raw, u.raw_cache)
    config.write_cache_source(u.raw_cache, u, key)
    print(f"    done {(time.time()-t0)/60:.1f} min, {len(raw):,} rows", flush=True)

    print("[2/2] Monthly scoring, 10-seed ensemble (slow)...", flush=True)
    t0 = time.time()
    scored = score_monthly(raw, SEEDS, purge_mode=u.purge_mode)
    config.write_panel(scored[["date", "symbol", "open", "close", "score", "year"]],
                       u.score_cache)
    config.write_cache_source(u.score_cache, u, key)
    print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
    if want is None:
        print(f"DONE -- {u.score_cache} ready")
    else:
        print(f"DONE -- {u.score_cache} ready ({len(got)} stocks)")
