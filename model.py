"""
model.py -- the purged training set, the LightGBM fit per seed, monthly
walk-forward scoring, the score build step and every cache key.

Sections, in order:
  1. training set with purge and embargo, the fit, score_monthly
  2. the score build step (SEEDS, run): raw panel and score panel per universe
  3. score-cache keys and staleness (panel_code_key, pit_membership_key,
     cache_staleness, require_cache, data_fingerprint)
  4. fit-cache and source-data keys (seed_cache_key, source_key)

The panel itself is built in market_data.py.
"""
import hashlib
import os
import sys
import time
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import settings
from settings import PROJECT_ROOT, list_dir
from market_data import (FEATS_V2, SCORE_INPUT_COLS, build_panel, read_table,
                         write_panel)


# ======================================================================================
# PURGED TRAINING SET, MODEL FIT AND MONTHLY SCORING. From engine_core.py (moved 2026-11-27).
# ======================================================================================

# Label horizon in trading sessions: fwd_ret is the close this many of the
# symbol's own rows ahead.
HORIZON = 20


PARALLEL_SEEDS = True   # False -> old sequential path (identical output, slower)


def _fit_seed(sd, Xtr, ytr, Xte, n_jobs=1):
    """Train one seed and predict. Top-level so joblib/loky can pickle it."""
    import warnings as _w
    # numpy arrays are passed (not DataFrames) to avoid per-process copies;
    # sklearn then warns about missing feature names. Column order is fixed
    # by FEATS_V2, so this is cosmetic only.
    _w.filterwarnings("ignore", message=".*does not have valid feature names.*")
    m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, max_depth=6,
                          num_leaves=48, subsample=0.8, colsample_bytree=0.8,
                          min_child_samples=100, random_state=sd, verbose=-1,
                          n_jobs=n_jobs)
    m.fit(Xtr, ytr)
    return m.predict(Xte)


# EMBARGO for the trading-row purge, in TRADING ROWS. See score_monthly.
PURGE_EMBARGO = 2


def score_floor():
    """The first day of the first month score_monthly scores (start_axis.score_floor):
    three years before the backtest start, 2016-01-01 for the default start."""
    from settings import start_axis
    return start_axis.score_floor()


def training_set(p, cal, i_first, horizon=HORIZON, embargo=PURGE_EMBARGO):
    """The training rows and targets for a period whose first session is cal[i_first].

    -> (index of training rows in `p`, their y_rank as an array), or None when
    i_first is too early for any row to qualify.

    `p` is a panel from build_panel (date, scorable, fwd_ret, label_end); `cal` is
    the sorted array of its dates. A row trains the model only when all of these
    hold, in TRADING SESSIONS on the panel's own calendar:

        date      <= cal[i_first - horizon - embargo]    the cut
        label_end <= cal[i_first - embargo]              the purge limit
        scorable, and fwd_ret present

    THE LABEL-END TEST IS THE 2026-10-22 FIX. The label is the close `horizon` of
    the symbol's OWN rows ahead, so for a symbol with missing sessions it ends
    later than `horizon` sessions after the row, and a row before the cut could
    carry a label ending inside the scored month. Until then only the row's date
    was checked. Measured before the fix: none on nifty100 static; 37 row-uses
    in 6 of 126 months on smallcap250 pit, the furthest 25 sessions past the limit.

    THE TARGET IS RANKED HERE, PER PERIOD. y_rank is the percentile rank of
    fwd_ret among the qualifying rows of the same date, so no row's target is
    shaped by a label that had not ended by the limit. It was ranked once over
    every label in build_panel until 2026-10-22.

    THE EMBARGO IS 2 SESSIONS. One clears the scored month. The second clears the
    close at i_first - 1, which is the BASE PRICE of the scored period's first
    return -- the strategy signals at a close and fills at the next open, so a
    label observing that close has observed the scored period's starting price.
    """
    j = i_first - horizon - embargo
    if j < 0:
        return None
    cut = pd.Timestamp(cal[j])
    limit = pd.Timestamp(cal[i_first - embargo])
    ok = ((p["date"] <= cut) & p["scorable"] & p["fwd_ret"].notna()
          & (p["label_end"] <= limit))
    y = p.loc[ok].groupby("date")["fwd_ret"].rank(pct=True)
    return y.index, y.to_numpy()


def score_monthly(raw, seeds, purge_mode="trading", through=None):
    """Monthly expanding-window scoring with a purged training set (training_set).

    PURGE_MODE IS "trading" AND NOTHING ELSE. The calendar rule (`first -
    Timedelta(days=32)`) was removed on 2026-10-22: no universe used it, and it
    could not express the label-end limit. Every registry row declares "trading";
    anything else is refused rather than silently scored another way.

    THE HEADLINE MOVED WHEN THE TRADING RULE REPLACED THE CALENDAR ONE, AND THE
    MOVE WAS NOT AN IMPROVEMENT. It was not distinguishable from re-fit variation
    -- EXPERIMENTS.md entry 29 measured the seed noise floor at sd 0.97 to 2.14
    CAGR points against a purge effect of -0.12 and -0.52.

    `through`, a date or None: score only the months whose first session is on or
    before it. None scores every month, as every pipeline run does. It exists for
    tools/lookahead_proof.py, whose cut and noise variants need no month after the
    cut date; a month's model and scores do not depend on later months.
    """
    if purge_mode != "trading":
        raise ValueError(f"purge_mode must be 'trading', got {purge_mode!r}; the "
                         f"calendar rule was removed on 2026-10-22")
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["score"] = np.nan
    p["ym"] = p["date"].dt.to_period("M")
    _cal = np.array(sorted(p["date"].unique()))
    _pos = {d: i for i, d in enumerate(_cal)}
    # PROGRESS, ONE LINE PER MONTH, 2026-09-23. This loop printed nothing for up
    # to 70 minutes on nifty500, so a live run could not be told from a hung one.
    # The month is the sequential unit: the seeds inside it are fitted in
    # parallel (below), so a line per seed would be ten interleaved lines from
    # worker processes per month rather than a measure of progress.
    import time as _time
    _sel = p["date"] >= score_floor()
    if through is not None:
        _firsts = p.groupby("ym")["date"].transform("min")
        _sel &= _firsts <= pd.Timestamp(through)
    _months = sorted(p.loc[_sel, "ym"].unique())
    _t0 = _time.time()
    for _k, ym in enumerate(_months, start=1):
        _first = p.loc[p.ym == ym, "date"].min()
        _ts = training_set(p, _cal, _pos[np.datetime64(_first)])
        if _ts is None:
            continue
        _tri, ytr = _ts
        # Only scorable rows are predicted. The panel now carries price-only rows
        # whose features are NaN; scoring those would feed NaN into the model and
        # produce a rank for a name the model cannot actually assess. They keep
        # score = NaN, so sc.loc[dt].dropna() leaves them out of the ranking while
        # their PRICE still counts for valuation, momentum and buy&hold.
        te = (p["ym"] == ym) & p["scorable"]
        if len(ytr) < 5000 or te.sum() == 0:
            continue
        Xtr = p.loc[_tri, FEATS_V2].to_numpy()
        Xte = p.loc[te, FEATS_V2].to_numpy()
        if PARALLEL_SEEDS and len(seeds) > 1:
            # One process per seed, each single-threaded.
            #
            # EQUIVALENCE AND COST, re-measured 2026-08-23 on a retired universe's panel
            # (month 2026-01, 257,973 training rows, 10 seeds, Mac Mini M4,
            # 10 cores = 4 performance + 6 efficiency):
            #
            #   this path, 10 procs x 1 thread .............  5.90s
            #   sequential, 10 fits x n_jobs=10 ............ 23.90s   4.05x slower
            #   4 procs x 1 thread (P-cores only) ..........  8.72s   1.48x slower
            #
            #   ensemble scores identical in both comparisons: max|diff| 0.000e+00
            #
            # So the two paths agree exactly and this one is four times faster.
            # LightGBM's intra-tree threading has almost nothing to parallelise at
            # 17 features and 48 leaves, so n_jobs=10 buys synchronisation overhead;
            # training 10 independent models has none of that.
            #
            # (This note replaces a reference to verify_parallel_scoring.py, which
            # established the same equivalence and was deleted in the 2026-08
            # cleanup. The numbers above are the re-measurement, kept here so the
            # claim travels with the code rather than with a file that can vanish.)
            pr = Parallel(n_jobs=min(len(seeds), os.cpu_count() or 1),
                          backend="loky")(delayed(_fit_seed)(sd, Xtr, ytr, Xte)
                                          for sd in seeds)
        else:
            pr = [_fit_seed(sd, Xtr, ytr, Xte, n_jobs=-1) for sd in seeds]
        p.loc[te, "score"] = np.mean(pr, axis=0)
        _el = (_time.time() - _t0) / 60
        print(f"      month {_k}/{len(_months)} {ym}: {len(seeds)} seeds fitted, "
              f"{_el:.1f} min elapsed, ~{_el / _k * (len(_months) - _k):.1f} min left",
              flush=True)
    return p.drop(columns=["ym"])


# ======================================================================================
# THE SCORE BUILD STEP. From build_scores_step.py (moved 2026-11-27).
# ======================================================================================
# build_scores_step -- the raw panel and monthly score panel, once, for any universe.
# ======================================================================================
#
# WHAT THIS REPLACES
#     Four files carried the same body: two retired-universe scripts (deleted 2026-09-11),
#     build_scores_mid.py and build_scores_n100.py. Each said in its own docstring that
#     it was a copy of the one before it -- a chain of copies, each one universe
#     further from the original.
#
#     Every difference between them is a universe property settings.py
#     records:
#
#         data directory   u.prepare_data_dir()
#         raw panel out    u.raw_cache
#         score panel out  u.score_cache
#         purge mode       u.purge_mode        <- see below, this one is load-bearing
#         index exclusion  u.index_name
#         symbol check     u.symbols()
#
# THE PURGE MODE IS A PROPERTY OF THE UNIVERSE, NOT OF THIS FILE
#     The two deleted retired universes were scored with purge_mode="calendar", which
#     model.score_monthly documents as DEFECTIVE -- it underflows on a holiday
#     cluster. They kept it because they were frozen and their published numbers
#     could not move. Every remaining universe takes the corrected "trading" value.
#
#     Before this merge that fact lived as a literal in two files and as an omission
#     in the other two, with nothing connecting them: a reader had to notice that
#     build_scores_mid.py did NOT pass purge_mode and know why. It is now read from
#     u.purge_mode, so the setting travels with the universe rather than with
#     whichever file happens to score it.
#
#     midcap150 and nifty100 must resolve "trading". That is
#     asserted explicitly, per universe, rather than left to be inferred.
#
# SEEDS ARE UNIVERSE-INVARIANT
#     All four files listed the same ten seeds. That is not a universe property -- it
#     is the production ensemble, identical everywhere so the comparison between
#     universes stays fair -- so it is one constant here rather than a registry field.


warnings.filterwarnings("ignore")





# The production ensemble. Identical in all four originals; not a universe property.
SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]


def run(u):
    """Build the raw panel and the monthly score panel for one universe.

    THE CACHED-PANEL SKIP LIVES HERE. The step that owns the panel owns the
    decision not to rebuild it.

    REUSE IS DECIDED BY CONTENT. Both panels are reused only when their sidecars
    carry the source key of the constituent farm as it is now -- every CSV name
    and the sha256 of its bytes (model.cache_staleness). Adding, removing or
    editing a CSV is a miss; the line printed says which names moved and the
    panels are rebuilt. Until 2026-09-23 the check was the source directory's
    name, and removing SUZLON.csv left the midcap50 panel in use with SUZLON in it.

    --fresh deletes the selected universes' panels before the loop, so this
    finds none and builds.
    """
    stale = [(what, cache_staleness(path, u))
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
    key = source_key_for(u)
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

    raw = raw[SCORE_INPUT_COLS]
    write_panel(raw, u.raw_cache)
    write_cache_source(u.raw_cache, u, key)
    print(f"    done {(time.time()-t0)/60:.1f} min, {len(raw):,} rows", flush=True)

    print("[2/2] Monthly scoring, 10-seed ensemble (slow)...", flush=True)
    t0 = time.time()
    scored = score_monthly(raw, SEEDS, purge_mode=u.purge_mode)
    write_panel(scored[["date", "symbol", "open", "close", "score", "year"]],
                       u.score_cache)
    write_cache_source(u.score_cache, u, key)
    print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
    if want is None:
        print(f"DONE -- {u.score_cache} ready")
    else:
        print(f"DONE -- {u.score_cache} ready ({len(got)} stocks)")


# ======================================================================================
# SCORE-CACHE KEYS AND STALENESS. From config.py (moved 2026-11-27).
# ======================================================================================

# ---------------------------------------------------------------------------
# CACHE RESOLUTION -- one place, so a stale or missing cache fails loudly
# ---------------------------------------------------------------------------
# A PANEL'S IDENTITY IS THE CONTENT OF THE CSVs IT WAS BUILT FROM.
#
# Until 2026-09-18 it was the path alone, and a repointed universe went on
# reading the old vendor's 217 MB panel. From 2026-09-18 to 2026-09-23 it was
# the path plus the source DIRECTORY, which caught a repoint and nothing else:
# removing SUZLON.csv from midcap50's source left the directory unchanged, the
# cached panel passed, and the run exited 0 still trading SUZLON 38 times.
#
# SO THE SIDECAR RECORDS model.source_key() OVER THE CONSTITUENT FARM:
# every CSV name and the sha256 of its bytes. The farm is what build_panel
# globs, so it is exactly the set of files scored. A panel is current only if
# that key matches the farm as it is now. The directory is recorded beside it
# for a reader and is not compared: the same bytes in another checkout are the
# same panel, which is what lets a copied tree reuse its cache.
#
# WHAT A MISS DOES DEPENDS ON WHO ASKED. The builder (build_scores_step) prints
# the reason and rebuilds. A reader raises CacheSourceError naming the reason and
# the command that rebuilds: a reader that rebuilt a 70-minute panel in passing
# would hide the fact that its input changed. There is no flag to accept a stale
# panel.
SOURCE_SIDECAR_SUFFIX = ".source"


class CacheSourceError(RuntimeError):
    """A cache could not be shown to have been built on the current source."""


def cache_source_file(cache_path):
    """The sidecar recording the source key `cache_path` was built from."""
    p = Path(cache_path)
    return p.with_name(p.name + SOURCE_SIDECAR_SUFFIX)


def source_key_for(u):
    """model.source_key over u's constituent farm, built if needed."""
    if u.raw_data_dir is None:
        raise CacheSourceError(
            f"{u.tag}: a universe with no raw_data_dir has no panel to key.")
    return source_key(list_dir(u.prepare_data_dir(), "*.csv"))


def _code_tokens(src):
    """The token stream of Python source with comments and blank lines removed.

    A comment or a blank line cannot change what the code computes, so neither
    may change a cache key. Everything else -- names, operators, literals,
    docstrings, error strings, indentation -- is kept, token by token.
    """
    import io
    import textwrap
    import tokenize
    toks = tokenize.generate_tokens(io.StringIO(textwrap.dedent(src)).readline)
    return "\x00".join(f"{t.type}:{t.string}" for t in toks
                        if t.type not in (tokenize.COMMENT, tokenize.NL))


def _data_lines(path):
    """A data file's bytes with its `#` comment lines removed.

    market_data._load_calendar reads the calendar with comment="#", so a header
    comment is invisible to the code and must be invisible to the key.
    """
    return b"".join(l for l in Path(path).read_bytes().splitlines(keepends=True)
                    if not l.lstrip().startswith(b"#"))


def panel_code_key():
    """sha256 over everything besides the source CSVs that determines a panel.

    COMMENTS ARE NOT PART OF THE KEY SINCE 2026-09-25. The functions below are
    hashed as token streams without comment tokens (_code_tokens), and the
    calendar without its `#` header (_data_lines), so rewording a comment does
    not force a rebuild. Docstrings and error strings are code tokens and are
    still covered. Changing this function changed every key once; all eight
    panels were rebuilt on 2026-09-25 and were byte-identical to the panels the
    previous key described.

    ADDED 2026-09-24. The key recorded only the source data, so a change to the
    feature code left every cached panel "current": a panel built by the old
    code would have been read as the output of the new. Covered: the functions
    that build and score the panel, the feature functions and their constants,
    market_data.py, the seed list, HORIZON and the purge constants, the
    scoring floor (start_axis.score_floor), the trading calendar and the LightGBM
    version. Nothing else, so an edit to the
    backtest code does not force a 75-minute rebuild. results/ratio_clean.py was
    covered from 2026-09-27 until it was removed on 2026-10-22.
    """
    import hashlib
    import inspect
    import lightgbm
    import market_data as md
    h = hashlib.sha256()
    for fn in (md.canonical_price, md._load_calendar, md._check_calendar,
               md.build_panel, _fit_seed, training_set, score_monthly,
               md.add_stock_features, md.add_market_relative_features,
               md.cross_sectional_normalize):
        h.update(_code_tokens(inspect.getsource(fn)).encode())
    # The variance functions, token by token in file order. Until 2026-11-27 this
    # hashed the whole of market_data.py, which no longer exists as a file.
    for fn in (md._rolling_var_1d, md.rolling_var, md.rolling_std, md.group_mean_std):
        h.update(_code_tokens(inspect.getsource(fn)).encode())
    h.update(_data_lines(md.TRADING_CALENDAR))
    h.update(repr((list(SEEDS), HORIZON, PURGE_EMBARGO, str(score_floor().date()),
                   list(md.FEATS_V2), md.EXTREME_RET_HI, md.EXTREME_RET_LO,
                   lightgbm.__version__)).encode())
    return "sha256:" + h.hexdigest()


# THE KEY A NOISE DRAW RECORDS, 2026-09-27. A draw is a rebuild of u's panel
# from a perturbed copy of u's farm, so it is fully determined by the code that
# builds panels (panel_code_key) and the unperturbed farm's bytes (source_key_for),
# plus the draw's own sigma and seed, which the record already carries. Every
# draw file and runs-CSV row stores both; a harness reuses a record only when both
# equal the current values, and reports and re-runs any record that does not.
RUN_KEY_FIELDS = ("panel_code", "source_digest")


def run_key(u):
    """{"panel_code": ..., "source_digest": ...} for universe u as it is now."""
    return {"panel_code": panel_code_key(),
            "source_digest": source_key_for(u)["digest"]}


def run_key_matches(rec, key):
    """True only if record `rec` (a dict or a row) carries exactly `key`.

    A record written before these fields existed has none of them and does not
    match: it is stale, not current by default.
    """
    return all(str(rec.get(k, "")) == key[k] for k in RUN_KEY_FIELDS)


def write_cache_source(cache_path, u, key):
    """Record `key` beside a cache. Called by whoever writes the cache.

    The key is taken BEFORE the build by the caller and passed in, so the
    sidecar describes the files that were read, not whatever is on disk after.
    """
    import json
    rel = root_relative(u.raw_data_dir)
    rec = {"universe": u.tag, "raw_data_dir": rel, "digest": key["digest"],
           "code": panel_code_key(),
           "n_files": key["n_files"], "files": key["files"]}
    if getattr(u, "is_pit", False):
        rec["membership"] = pit_membership_key(u)
    # naming: axis-free -- the sidecar's name is its cache's name plus a fixed
    # suffix, so it carries whatever axes that cache carries and adds none of
    # its own; there is no arm, cadence, profile or tax choice expressed here.
    cache_source_file(cache_path).write_text(json.dumps(rec, indent=1) + "\n")


def pit_membership_key(u):
    """What else a pit panel depends on: the membership file's bytes and the code
    that applies it (market_data.apply_to_panel, member_mask and RENAMES). Static panels
    carry no such field, so their sidecars are unchanged."""
    import hashlib
    import inspect
    import market_data as md
    h = hashlib.sha256(Path(u.membership_file).read_bytes())
    h.update(_code_tokens(inspect.getsource(md.apply_to_panel)).encode())
    h.update(_code_tokens(inspect.getsource(md.member_mask)).encode())
    h.update(repr(sorted(md.RENAMES.items())).encode())
    return "sha256:" + h.hexdigest()


def _cache_owner(path):
    """The registered universe whose cache `path` is, or None.

    IMPORTED LAZILY. settings.py is imported by this module at its own import
    time, and REGISTRY is built at the end of settings' import.
    """
    from settings import REGISTRY
    p = Path(path).resolve()
    for u in REGISTRY.values():
        for cand in (u.score_cache, u.raw_cache):
            if Path(cand).resolve() == p:
                return u
    return None


def cache_staleness(cache_path, u):
    """None if `cache_path` was built from u's current source, else the reason."""
    import json
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return f"no panel at {cache_path}"
    side = cache_source_file(cache_path)
    if not side.exists():
        return f"no source sidecar ({side.name}), so what it was built from is unknown"
    try:
        rec = json.loads(side.read_text())
    except ValueError:
        return (f"{side.name} is in the pre-2026-09-23 format (a directory path "
                f"only), which cannot show whether a CSV was added or removed")
    code = panel_code_key()
    if rec.get("code") != code:
        return ("the code that builds panels changed since this one was built "
                "(model.panel_code_key)" if rec.get("code") else
                "it predates the code key (model.panel_code_key, 2026-09-24)")
    if getattr(u, "is_pit", False) and rec.get("membership") != pit_membership_key(u):
        return ("the membership file or the code that applies it changed since this "
                "pit panel was built (model.pit_membership_key)")
    cur = source_key_for(u)
    if rec.get("digest") == cur["digest"]:
        return None
    diff = key_difference(rec.get("files", {}), cur["files"])
    return (f"source changed since the panel was built ({rec.get('n_files')} -> "
            f"{cur['n_files']} files): {diff or 'digest differs'}")


def _verified(cache_path, what):
    """Return `cache_path` only if it was built from its universe's current source."""
    u = _cache_owner(cache_path)
    if u is None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  This path is not the score or raw cache of any registered\n"
            f"  universe, so which source it was built from cannot be\n"
            f"  established. A panel of unknown provenance is not usable as\n"
            f"  evidence. Add the row that owns it, or delete the file.")
    why = cache_staleness(cache_path, u)
    if why is not None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  STALE PANEL -- refusing to return it: {why}.\n"
            f"  Every number computed from it would describe other data. Rebuild:\n"
            f"      ./venv/bin/python run.py --universe {u.tag} --steps pipeline")
    return cache_path


# ---------------------------------------------------------------------------
# THE SAME QUESTION, ONE LAYER UP: WHAT DATA DID A PUBLISHED ARTEFACT COME FROM
# ---------------------------------------------------------------------------
# The sidecar above protects CACHES. _cache_owner() matches only score_cache,
# raw_cache, score_tmp and raw_tmp, so a daily_trades or a v34_params -- the files
# people read and quote -- is covered by nothing.
#
# MEASURED 2026-09-20, WHICH IS WHY THIS EXISTS. midcap150's two tradeable
# artefacts were written 2026-09-17 against data/raw/MidCap150/clean. The universe
# was repointed at Final_Without_Survivorship_Data on 2026-09-18. Neither artefact
# said which source it came from, no gate compared one against the other, and the
# only reason it surfaced at all was someone reconstructing a median by hand. All
# seven gates were green throughout.
#
# WHOLE FILE, NOT A ROW COUNT. A row count catches a truncated or extended
# history and nothing else. The participation cap eats the VOLUME column, and a
# supplier that revised volume while leaving dates and prices untouched would pass
# a row count, pass a date-range check and pass a re-derivation of fill prices --
# every test available before this one. Hashing every byte catches it. It costs
# 0.11 s over midcap150's 96 MB and 0.30 s over nifty500's 312 MB, measured, which
# is small enough that there is no argument for a cheaper and weaker answer.
#
# THE LINK FARM IS WHAT IS HASHED, not raw_data_dir, because the farm is what
# build_panel globs. raw_data_dir is recorded beside it: if the two ever disagree
# the artefact carries both halves and the difference is readable.
def root_relative(p):
    """`p` resolved, as a path relative to the project root when it is inside it.
    A relative `p` is taken as already relative to the root, not to the cwd."""
    q = Path(p)
    q = (q if q.is_absolute() else PROJECT_ROOT / q).resolve()
    try:
        return str(q.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(q)


def data_fingerprint(data_dir, raw_data_dir):
    """What a published artefact records about the price data it was built from.

    Returns a dict with the resolved link directory, the resolved raw_data_dir,
    where the symlinks actually point, the file count, and
    model.source_key's digest over every CSV in the farm -- the same
    digest a panel's sidecar records.
    """
    import os
    d = Path(data_dir)
    files = list_dir(d, "*.csv")
    # WHERE THE FARM'S FILES COME FROM. Until 2026-09-24 the farm held symlinks
    # and this followed them. It now holds hard links or copies (see
    # Universe.prepare_data_dir), so each entry is checked against the file of
    # the same name in raw_data_dir: the same file, or a copy with the same size
    # and mtime. The recorded value is unchanged for a farm built from
    # raw_data_dir, which is what GATE 8 compares.
    raw = Path(raw_data_dir) if raw_data_dir else None

    def _from_raw(f):
        g = raw / f.name if raw is not None else None
        if g is None or not g.exists():
            return False
        if os.path.samefile(f, g):
            return True
        a, b = f.stat(), g.stat()
        return (a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns)

    if not files:
        target = None
    elif all(_from_raw(f) for f in files):
        target = str(raw.resolve())
    else:
        target = f"MIXED: {sum(not _from_raw(f) for f in files)} entries not from raw_data_dir"
    key = source_key(files)
    # PATHS ARE RECORDED RELATIVE TO THE PROJECT ROOT, 2026-09-23. They were
    # absolute, so the same data in a second checkout wrote a different
    # v34_params*.json. GATE 8 compares through root_relative() on both sides,
    # so artefacts written with absolute paths before this still compare.
    return {
        "link_dir": root_relative(d),
        "link_target_dir": root_relative(target) if target and not target.startswith("MIXED") else target,
        "raw_data_dir": root_relative(raw_data_dir) if raw_data_dir else None,
        "n_files": key["n_files"],
        "digest": key["digest"],
        "digest_covers": ("every byte of every CSV in link_dir, the volume column "
                          "included; recompute with config.data_fingerprint()"),
    }


def require_cache(path, what="score panel"):
    """Return `path` if it exists and is current, or raise with the remedy.

    ONE LOCATION PER PANEL SINCE 2026-09-23. There used to be a working copy in
    /tmp and a permanent copy under results*/metrics/, and this took both. /tmp
    is shared by every checkout on a machine, so a second checkout read the
    first one's panel. Both copies are now one file under cache/<tag>/.
    """
    p = Path(path)
    if p.exists():
        return _verified(p, what)
    u = _cache_owner(p)
    tag = u.tag if u is not None else "<universe>"
    raise FileNotFoundError(
        f"{what} not found at {p}.\n"
        f"  Build it with\n"
        f"      ./venv/bin/python run.py --universe {tag} --steps pipeline\n"
        f"  using the venv interpreter; see requirements.txt.")


# ======================================================================================
# FIT-CACHE AND SOURCE-DATA KEYS. From seed_cache_key.py (moved 2026-11-27).
# ======================================================================================
# seed_cache_key -- the keys for cached model fits and cached panels, in one place.
#
# Two keys live here: seed_cache_key() for a cached fit, and source_key() for the
# price CSVs a score or raw panel is built from (see the block above
# source_key()). Both hash content, never a path or an mtime.
#
# WHY THIS EXISTS. Two scripts cache score_monthly's output under /tmp and read it
# back on a later run: checks.py validate_sizing's T2 and checks.py validate_engine's T2.
# Both were keyed on the universe and the INDEX into SEED_SETS and nothing else --
# no code hash, no panel hash -- so neither could miss on a code change or a panel
# change. A cache written by any earlier engine against any earlier panel landed on
# the path a later run reads and was read back as current, with no warning.
#
#     validate_sizing  /tmp/VALSIZE_{universe}_seed{i}.csv     found 2026-09-22
#     validate_engine  /tmp/V2VAL_{tag}_seed{i}.csv            found 2026-09-22
#
# Both now carry the key in the name: /tmp/VALSIZE_{universe}_seed{i}_{key}.csv and
# /tmp/V2VAL_{tag}_seed{i}_{key}.csv.
#
# The first was fixed with a private copy of this logic. The second needed the same
# thing, and a second copy is how this repository already lost four tables to
# drift -- REQUIRED_INPUTS, PIPELINE_ORDER, REPORT_ORDER and FILES. One definition,
# both callers.
#
# WHAT A CALLER MUST PASS, AND WHY EACH ONE.
#     code_files  every source file whose contents can change the fit. Both callers
#                 pass model.py (score_monthly IS the computation),
#                 market_data.py (the readers), settings.py (the backtest window), and
#                 THEIR OWN FILE, because each
#                 chooses the seed sets and the columns written to the cache.
#     panel_path  the data fit against. Hashed by CONTENT, streamed. Not by path
#                 and not by mtime: two panels at one path is how this repository
#                 lost track of which source produced midcap150's artefacts.
#     parts       everything else that selects the computation -- the universe tag,
#                 the seed list, the purge mode. Values, not indices: "seed set 1"
#                 is not a fact about the seeds.
#
# This file hashes ITSELF as well. It cannot change the fit, but a key function
# that can be edited without invalidating the keys it already issued is the same
# defect one level up.
#
# THERE IS NO OVERRIDE FLAG AND THERE SHOULD NOT BE. An escape hatch on a
# correctness key is the silent reuse this replaces. A miss is a refit.


_SELF = Path(__file__).resolve()


def seed_cache_key(code_files, panel_path, parts, length=16):
    """Return a short hex key over code, panel content and the parts given.

    `code_files` and `panel_path` are paths; `parts` is any repr-able structure.
    Raises rather than returning a weak key if a named file is missing: a key
    computed over a file that is not there would silently collide with one that
    had it.
    """
    h = hashlib.sha256()
    for f in list(code_files) + [_SELF]:
        p = Path(f)
        if not p.exists():
            raise FileNotFoundError(
                f"seed_cache_key: {p} does not exist, so the key would not "
                f"describe the code that produced the fit")
        h.update(p.read_bytes())
    p = Path(panel_path)
    if not p.exists():
        raise FileNotFoundError(f"seed_cache_key: panel {p} does not exist")
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    h.update(repr(parts).encode())
    return h.hexdigest()[:length]


# ---------------------------------------------------------------------------
# THE SOURCE-DATA KEY. Same rule as the fit key above -- content, never a path or
# an mtime -- applied to the directory of price CSVs a panel is built from.
# ---------------------------------------------------------------------------
# Until 2026-09-23 a score panel's sidecar recorded only the DIRECTORY it was
# built from. Removing SUZLON.csv from midcap50's source left the directory name
# unchanged, the cached panel passed its check, and the run exited 0 trading
# SUZLON 38 times under a header that said "48 constituents".
#
# THE ALGORITHM IS model.data_fingerprint's, MOVED HERE, NOT A SECOND ONE. For
# each file in name order: the stem, then the sha256 of its bytes. Every
# published v34_params*.json records a digest computed this way, and GATE 8
# compares against it, so changing the algorithm would fail every artefact on
# disk. This function does NOT hash its own source, unlike seed_cache_key: its
# output is a fingerprint of data recorded in published artefacts, and it must
# stay stable across edits to this file.
_FILE_HASHES = {}      # (resolved path, size, mtime_ns) -> hex, per process


def _file_sha256(p):
    st = p.stat()
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _FILE_HASHES:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _FILE_HASHES[k] = h.hexdigest()
    return _FILE_HASHES[k]


def source_key(files):
    """Content key over a set of source CSVs.

    Returns {"digest": "sha256:<hex>", "n_files": n, "files": {stem: sha256}}.
    `files` may be symlinks; the bytes read are the targets'. The per-file map is
    what lets a key miss say WHICH names were added, removed or changed.
    """
    h = hashlib.sha256()
    per = {}
    for f in sorted((Path(x) for x in files), key=lambda x: x.name):
        d = _file_sha256(f.resolve())
        per[f.stem] = d
        h.update(f.stem.encode())
        h.update(bytes.fromhex(d))
    return {"digest": "sha256:" + h.hexdigest(), "n_files": len(per), "files": per}


def key_difference(old_files, new_files):
    """One line naming what changed between two `files` maps, or None if equal."""
    removed = sorted(set(old_files) - set(new_files))
    added = sorted(set(new_files) - set(old_files))
    changed = sorted(s for s in set(old_files) & set(new_files)
                     if old_files[s] != new_files[s])
    if not (removed or added or changed):
        return None

    def _few(xs):
        return ", ".join(xs[:8]) + (f" (+{len(xs) - 8} more)" if len(xs) > 8 else "")
    parts = []
    if removed:
        parts.append(f"{len(removed)} removed: {_few(removed)}")
    if added:
        parts.append(f"{len(added)} added: {_few(added)}")
    if changed:
        parts.append(f"{len(changed)} changed content: {_few(changed)}")
    return "; ".join(parts)
