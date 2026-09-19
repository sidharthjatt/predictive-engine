"""
run_all.py -- the complete pipeline (58 + 74 + benchmark), from scratch, in one command.
=================================================================================
    ./venv/bin/python run_all.py            # uses cache if present (fast)
    ./venv/bin/python run_all.py --fresh    # everything from scratch (clears cache)

On a new machine or from nothing: `./venv/bin/python run_all.py --fresh`

THE INTERPRETER IN THAT COMMAND IS LOAD-BEARING. IT IS NOT INTERCHANGEABLE WITH
`python3`.
    Every step now runs IN THIS INTERPRETER (run.py imports and calls it), which
    makes the command line the only interpreter there is -- no fallback and no
    second chance. It was true when steps were subprocesses too, because the
    subprocess was spawned with sys.executable and inherited the same wrong
    interpreter thirty-one times; it is if anything more direct now.

    Corrected 2026-09-02. This docstring previously said `python3 run_all.py`.
    On the machine the published numbers were produced on, `python3` resolves to
    Python 3.11 with no lightgbm, so that command died at STEP 1 with
    ModuleNotFoundError -- and 3.11 is also BELOW nautilus_trader's 3.12 floor,
    which requirements.txt warns about. Both failures had the same cause.
    See KNOWN_ISSUES.md, "The documented commands are not verified against the
    machine they run on".

This rebuilds both universes, the benchmark comparison, and every chart and CSV.

ORDER:
  === MIDCAP150 ===
  10a. build_scores (mid)   -> MidCap150 scores (SLOW)
  10b. engine_v2_final(mid)-> MidCap150 v2 FINAL
  10c. make_audit (mid)     -> MidCap150 daily audit CSVs
  10d. make_chart (mid)   -> MidCap150 chart + cap-weighted index benchmark
  === NIFTY 100 ===
  10e. build_scores (n100)  -> Nifty 100 scores (SLOW)
  10f. engine_v2_final(n100)-> Nifty 100 v2 FINAL
  10g. make_audit (n100)    -> Nifty 100 daily audit CSVs
  10h. make_chart (n100)  -> Nifty 100 chart + cap-weighted index benchmark
  === ACROSS UNIVERSES ===
  12b. make_combined_universes -> the published comparison figure
  15.  make_daily_log          -> forensic daily text log
  15b. save_caches_step        -> persist the panels
  16.  nt_export_scores        -> Nautilus score parquets
  17.  nt_execute              -> the execution engine, per (universe, arm)

STEPS 0-9 AND 11-14 ARE GONE, not renumbered. They were the retired 58's and
74's, deleted on 2026-09-11 with those universes; the surviving numbering is
left as it was so a step's name means the same thing it did in every log and
every document written before that date. See RETIRED_UNIVERSES.md.

ORDERING IS LOAD-BEARING. A consumer must never be listed before its producer.
run_all.py enforces the non-obvious cases itself -- see REQUIRED_INPUTS below,
which fails with the missing filename and the owing step instead of a pandas
FileNotFoundError.
"""
# ---------------------------------------------------------------------------
# DETERMINISM PIN -- SET BEFORE ANY NUMERIC LIBRARY IS IMPORTED.
# ---------------------------------------------------------------------------
# WHY HERE AND NOT IN config.py. Every pipeline step runs as a SUBPROCESS
# (run() below spawns sys.executable). A child inherits os.environ AT SPAWN, so
# setting these here -- before the child exists -- guarantees they are in place
# before the child imports numpy, pandas or lightgbm. Setting them inside
# config.py would be too late for numpy, because most scripts import pandas
# BEFORE they import config, and an OpenMP/BLAS runtime reads its thread count
# when it initialises at import.
#
# This block is above `import sys` deliberately: only `os` is imported first, and
# `os` pulls in no numeric library.
#
# WHY 1 AND NOT A LARGER NUMBER. Parallelism in this pipeline is at the PROCESS
# level -- joblib runs one process per seed and engine_core._fit_seed already
# passes n_jobs=1 -- so pinning the thread count to 1 costs no wall clock while
# removing every intra-library reduction-order effect. Threads are what make a
# floating-point sum order-dependent; one thread has one order.
#
# PYTHONHASHSEED fixes string-hash randomisation. Nothing in the pipeline
# currently iterates an unsorted set of strings into an output, but nothing
# enforces that either, so the seed is pinned rather than relied upon.
#
# NOT COVERED: a step run STANDALONE (`python3 results/build_scores.py n100`)
# does not pass through here and gets the machine defaults. That gap is real and
# is not closed by this block.
import os as _os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ[_v] = "1"
_os.environ["PYTHONHASHSEED"] = "0"

import sys, time, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent
R = ROOT / "results"

# THERE IS NO FROZEN-WRITE OVERRIDE ANY MORE, and no frozen/ directory. Both
# existed for the retired 58 and 74: their scripts refused to run unless
# ALLOW_FROZEN_WRITE was set, because results*/metrics/ is gitignored and a stray
# standalone run overwrote a published artefact with no way back. Those universes
# were deleted on 2026-09-11 and every script they owned went with them. See
# RETIRED_UNIVERSES.md.

# WHERE STEPS LIVE. Searched in order, not matched against a list of names.
#
# THIS WAS AN ALLOWLIST OF ONE NAME AND IT FAILED TWICE. On 2026-09-04 STEP 16
# nt_export_scores.py resolved to results/, was not found, and was silently
# skipped by the ordering check -- it had never been covered. The fix was to add
# that one name to a set. On 2026-09-11 STEP 17 nt_execute.py, added to
# PIPELINE_ORDER without touching the set, reproduced the identical failure. A
# name allowlist cannot generalise to the next file, which was knowable when it
# was written. The directory list can.
# ROOT IS LAST, AND IT IS LAST ON PURPOSE. bh_lots_after_tax.py became a
# pipeline step on 2026-09-19 and lives at the repository root rather than under
# results/, so script_path() could not resolve it and GATE 2 failed all four of
# its rows by name -- which is the gate working. results/ and nautilus/ are still
# searched FIRST, so nothing that resolved before resolves differently now; the
# root can only satisfy a name neither of them holds.
STEP_DIRS = (ROOT / "results", ROOT / "nautilus", ROOT)

# A step whose body lives in a shared helper must be scanned WITH that helper, or
# the static ordering check loses the edges the helper writes. results/audit_step.py
# holds the one audit implementation the two per-universe entry points call.
STEP_HELPERS = {
    "make_audit.py":         (R / "audit_step.py",),
    # ONE ENTRY FOR BOTH ROWS. STEP_HELPERS is keyed by script, and after the
    # step 3 merge the two build_scores rows name the same script, so they share
    # this entry rather than needing one each. STEP_HELPERS shrinks with every
    # pair the collapse merges; that is the shape, not a special case.
    "build_scores.py":       (R / "build_scores_step.py",),
}


def script_path(script):
    """Where a pipeline step actually lives. One definition, used by run() and
    by the static ordering check, so the two cannot disagree about a step's
    location -- a disagreement would make check_pipeline_order silently skip a
    file it could not find rather than fail."""
    q = Path(script)
    if q.is_absolute():
        return q
    for d in STEP_DIRS:
        if (d / q.name).exists():
            return d / q.name
    # NOT FOUND ANYWHERE. The results/ path is returned so the caller can report
    # what it looked for; check_pipeline_order.enforce() treats an unresolvable
    # step as fatal rather than printing a banner and continuing.
    return R / q.name


TMP = Path("/tmp")
FRESH = "--fresh" in sys.argv

# caches: both /tmp and the permanent copies
def _cache_perm():
    from universes.registry import REGISTRY
    return [u.score_cache for u in REGISTRY.values()] + \
           [u.raw_cache for u in REGISTRY.values()]


CACHE_TMP = [TMP / "v5_expanding.csv", TMP / "raw_panel_20.csv",
             TMP / "v74_expanding.csv", TMP / "raw_panel74_20.csv",
             TMP / "v_mid_expanding.csv", TMP / "raw_panel_mid_20.csv",
             TMP / "v_n100_expanding.csv", TMP / "raw_panel_n100_20.csv"] + \
            [TMP / f"FINAL_seed{i}.csv" for i in range(3)] + \
            [TMP / f"breadth_seed{i}.csv" for i in range(3)] + \
            [TMP / f"prune_{t}.csv" for t in ("all", "pruned", "random")]
# THE PERMANENT PANELS, FROM THE REGISTRY. This was eight literal paths, four of
# them the 58's and the 74's; --fresh would have gone on trying to clear caches for
# universes that no longer exist, and a new universe's panels would have been
# missed silently.
CACHE_PERM = _cache_perm()

# Execution order, declared once so the static checker can read it. run() asserts
# every script it is handed appears here, so this list cannot silently drift out of
# step with main(). Steps 10a/10e are skipped at runtime when their panel is
# cached; that does not change the ORDER, which is what the checker reasons about.
#
# THIRD FIELD: THE UNIVERSE THIS ROW IS FOR, or None for a whole-run step.
# Added 2026-09-15 with the invocation contract, and it REPLACES run.py's
# STEP_UNIVERSES rather than joining it. The difference that matters: STEP_UNIVERSES
# was a second table, keyed by filename, that had to be kept in step with this one
# by hand -- and it is the shape this project has now been bitten by on the cadence,
# arm and profile axes in turn. The universe is not separate knowledge about a step;
# it is part of the invocation, so it belongs in the row that declares the
# invocation.
#
# A ROW WITH A UNIVERSE NAMES A STEP WHOSE main() TAKES ONE (arity 1). A row with
# None names a step whose main() takes nothing and which decides from the selection
# what to do. run.py checks the two against each other and REFUSES on a mismatch
# rather than defaulting; see _resolve_arity there.
#
# IT KEEPS 13 ROWS AFTER THE COLLAPSE COLLAPSES THE FILES 8 -> 4. Each row is still
# one invocation, so each keeps its own label, and STEP 10a..10h all survive the
# collapse meaning exactly what they meant in every log written before it -- the
# same identity-over-compaction rule the 2026-09-11 retirement set when it left
# STEPS 0-9 and 11-14 as gaps rather than renumbering.
# ---------------------------------------------------------------------------
# THE FOURTH FIELD: SPAN. WHOSE DIRECTORIES A STEP TOUCHES.
# ---------------------------------------------------------------------------
# ONE FIELD CANNOT ANSWER TWO QUESTIONS, AND THE THIRD FIELD WAS ANSWERING TWO.
#
#   field 3, INVOCATION -- "which universe is this step invoked for". run.py reads
#           it against the step's main() arity: a tag demands main(u), None demands
#           main(). run.py:126-130, "Nothing defaults."
#   field 4, SPAN -- "whose metrics directories does this step's source touch".
#           check_pipeline_order reads it to resolve producer edges.
#
# THEY COINCIDE FOR A PER-UNIVERSE STEP, which is why the scanner could co-opt
# field 3 and nobody noticed. THEY DIVERGE FOR AN N-WAY STEP: STEP 12b
# make_combined_universes is invoked ONCE for NO universe -- main() takes zero
# arguments and None is correct -- while touching EVERY universe's directory.
# Widening field 3 to carry both would make run.py refuse to start, because a
# non-None field 3 demands main(u).
#
# SPANS_REGISTRY IS RESOLVED LIVE, NOT SNAPSHOTTED, AND THAT IS THE WHOLE POINT.
# It means "this step is GENERIC OVER THE REGISTRY" -- its source loops over the
# registered tags rather than naming any -- so the correct span is whatever is
# registered when the scanner runs. A snapshot tuple would be a second copy of the
# registry that goes stale the day a ninth universe lands, and it would go stale
# SILENTLY: the scanner would simply resolve fewer edges, and `unresolved` would
# not grow to say so.
#
# IT IS A CLAIM ABOUT THE CODE, NOT ABOUT TESTING. A step may only use this
# sentinel if its source really is generic. A step that handles SOME universes and
# not others must NOT use it -- it lists its subset as an explicit literal tuple,
# e.g. ("mid", "n100"), which is checked against the registry and is exactly the
# spelling that says "these, and not whatever arrives later".
#
#   None              touches no universe metrics directory (the default, and what
#                     every per-universe row uses -- field 3 already names it)
#   ("mid", "n100")   touches exactly these, and does not follow the registry
#   SPANS_REGISTRY    generic over the registry, resolved live at scan time
#
# SPANS_REGISTRY IS LOAD-BEARING ON THE AUTHOR BEING HONEST, AND NOTHING CHECKS IT.
# STATED HERE, AT THE POINT OF USE, RATHER THAN LEFT FOR WHOEVER TRUSTS IT.
#
# The sentinel is a claim ABOUT THE SOURCE: that the step's paths are built from a
# loop over the registered tags, so every registered directory really is touched.
# If that claim is false -- paths built inside an `if t == "mid":` branch, say --
# check_pipeline_order will credit the step with EVERY registered directory and
# resolve producer edges the code never produces.
#
# THAT IS A FALSE RESOLUTION, AND `unresolved` CANNOT CATCH IT. `unresolved` grows
# when something fails to resolve; it never grows when something resolves WRONGLY.
# The failure is therefore silent in the same way the four incidents recorded in
# check_pipeline_order.py's own comments were silent -- and it is worse, because
# those left an edge missing while this one invents an edge that passes.
#
# IT IS NOT STATICALLY DETECTABLE IN GENERAL. Deciding which loop iterations reach
# which path expression is path-sensitive analysis, and the scanner is regexes over
# source text. A heuristic is possible -- refuse the sentinel in a file that
# compares a loop variable against a registered tag literal -- but it is defeatable
# and is NOT implemented here; a check that catches the careless case and misses
# the subtle one would be read as coverage.
#
# WHAT WOULD ACTUALLY CHECK IT is a RUN-TIME comparison: after a step executes,
# compare its declared span against the directories it actually wrote. That is a
# different mechanism from this table and is not built. Until it is, a row
# declaring SPANS_REGISTRY is an assertion by its author, and the reviewer of that
# row is the only thing standing behind it.
SPANS_REGISTRY = "__spans_registry__"


def row_span(row):
    """The universe tags a PIPELINE_ORDER row's step touches, resolved.

    INDEXED, NEVER UNPACKED, and absent means None -- the same contract field 3
    arrived under. Every consumer of this table reads by index behind a length
    guard, so a row that does not carry a fourth element is unaffected.
    """
    span = row[3] if len(row) > 3 else None
    if span is None:
        return ()
    if span == SPANS_REGISTRY:
        from universes.registry import REGISTRY
        return tuple(REGISTRY)
    unknown = [t for t in span if t not in _registry_tags()]
    if unknown:
        raise SystemExit(
            f"run_all.PIPELINE_ORDER: row {row[0]} {row[1]} declares a span over "
            f"universe(s) the registry does not define: {sorted(unknown)}.\n"
            f"  The fourth field is the set of universes whose metrics directories "
            f"this step touches.\n"
            f"  Known: {sorted(_registry_tags())}. Use SPANS_REGISTRY if the step "
            f"is generic over the registry rather than naming a subset.")
    return tuple(span)


def _registry_tags():
    from universes.registry import REGISTRY
    return set(REGISTRY)


# HOW MANY ROWS THIS TABLE HAS, DECLARED, so that a bulk edit over it cannot
# quietly cover part of it. check_all.py asserts len(PIPELINE_ORDER) against this
# number and fails when they disagree.
#
# IT EXISTS BECAUSE A REGEX MATCHED 12 OF 15 ROWS, TWICE. The script column
# contains digits -- engine_v2_final.py -- so a `"[a-z_]+\.py"` pattern skips the
# three engine rows and rewrites the rest. Both times the edit was a universe
# rename, both times the result imported cleanly, and both times the only thing
# that caught it was an assertion the author happened to write. This constant
# makes that assertion the repository's rather than the author's.
#
# UPDATE IT BY HAND when a row is added or removed. That is the point: a number
# derived from the table it is checking would agree with any table.
PIPELINE_ROW_COUNT = 53

PIPELINE_ORDER = [
    ("STEP 10a", "build_scores.py",            "midcap150"),
    ("STEP 10b", "engine_v2_final.py",         "midcap150"),
    ("STEP 10c", "make_audit.py",              "midcap150"),
    ("STEP 10d", "make_chart.py",              "midcap150"),
    ("STEP 10e", "build_scores.py",            "nifty100"),
    ("STEP 10f", "engine_v2_final.py",         "nifty100"),
    ("STEP 10g", "make_audit.py",              "nifty100"),
    ("STEP 10h", "make_chart.py",              "nifty100"),
    # n50, ADDED 2026-09-18. NEW LABELS, NOT 10i-10l. 10i meant
    # make_combined_universes.py until it moved to STEP 12b, and reusing any of
    # that block would make every log written before the move ambiguous -- the
    # same identity-over-compaction rule the 2026-09-11 retirement followed when
    # it left STEPS 0-9 and 11-14 as gaps rather than renumbering.
    ("STEP 10m", "build_scores.py",            "nifty50"),
    ("STEP 10n", "engine_v2_final.py",         "nifty50"),
    ("STEP 10o", "make_audit.py",              "nifty50"),
    ("STEP 10p", "make_chart.py",              "nifty50"),
    # midcap50, ADDED 2026-09-18. NEW LABELS AGAIN, 10q-10t, and not 10i-10l
    # for the reason the n50 block states: a reused label makes every log
    # written before the reuse ambiguous.
    ("STEP 10q", "build_scores.py",            "midcap50"),
    ("STEP 10r", "engine_v2_final.py",         "midcap50"),
    ("STEP 10s", "make_audit.py",              "midcap50"),
    ("STEP 10t", "make_chart.py",              "midcap50"),
    # midcap100, ADDED 2026-09-19. NEW LABELS AGAIN, 10u-10x, same rule: a
    # reused label makes every log written before the reuse ambiguous.
    ("STEP 10u", "build_scores.py",            "midcap100"),
    ("STEP 10v", "engine_v2_final.py",         "midcap100"),
    ("STEP 10w", "make_audit.py",              "midcap100"),
    ("STEP 10x", "make_chart.py",              "midcap100"),
    # nifty200, ADDED 2026-09-19, AND THE 10-SERIES IS NOW EXHAUSTED.
    #
    # 10y and 10z are the last single-letter suffixes, and a universe needs
    # FOUR. 10i-10l are burnt -- they were make_combined_universes' labels
    # before it moved to STEP 12b, and the n50 block above states why a reused
    # label makes every log written before the reuse ambiguous. 11-14 are the
    # deliberate gap left by the 2026-09-11 retirement, left so a step's name
    # still means what it meant in every older log; repopulating that gap would
    # spend the record it exists to keep.
    #
    # SO THE LAST TWO CARRY A SECOND CHARACTER, WHICH SORTS CORRECTLY:
    # "10y" < "10z" < "10za" < "10zb" < "12b" lexicographically, so no label
    # sorts after something it precedes. It is not pretty. THE SEVENTH UNIVERSE
    # NEEDS A DECISION RATHER THAN ANOTHER SUFFIX -- there is no third character
    # that keeps this readable, and smallcap250 is next.
    ("STEP 10y",  "build_scores.py",           "nifty200"),
    ("STEP 10z",  "engine_v2_final.py",        "nifty200"),
    ("STEP 10za", "make_audit.py",             "nifty200"),
    ("STEP 10zb", "make_chart.py",             "nifty200"),
    # ---------------------------------------------------------------------
    # FROM HERE THE LABELS ARE NUMERIC: STEP 10.01, 10.02, ... Adopted
    # 2026-09-19, NEW UNIVERSES ONLY. The map is in PANEL_MIGRATION.md
    # section 7, beside the tag map, because this repository now holds two
    # pairs of naming worlds and they belong in one document.
    #
    # NOTHING ABOVE IS RENAMED, INCLUDING nifty200's four. Renaming those to
    # save two awkward labels would create a THIRD naming world.
    #
    # UNIQUENESS IS THE ONLY MACHINE CONTRACT. Order comes from LIST POSITION
    # -- check_plan_order.py:70 builds its pos map from enumerate(pipeline) --
    # and nothing parses or sorts a label. _step_label() matches rows by
    # (script, tag) and treats the string as opaque. The label must be unique
    # because it is a dict key there and part of check_all's GATE 2/GATE 4
    # failure identity; it must be readable because people read it. It does
    # not have to sort, and commit 615e257 was wrong to present that as a
    # requirement rather than as the convention it is.
    # ---------------------------------------------------------------------
    # smallcap250, ADDED 2026-09-19 -- THE FIRST UNIVERSE ON THE NEW SCHEME.
    ("STEP 10.01", "build_scores.py",           "smallcap250"),
    ("STEP 10.02", "engine_v2_final.py",        "smallcap250"),
    ("STEP 10.03", "make_audit.py",             "smallcap250"),
    ("STEP 10.04", "make_chart.py",             "smallcap250"),
    # nifty500, ADDED 2026-09-19. THE EIGHTH AND LAST SUPPLIER FOLDER.
    ("STEP 10.05", "build_scores.py",           "nifty500"),
    ("STEP 10.06", "engine_v2_final.py",        "nifty500"),
    ("STEP 10.07", "make_audit.py",             "nifty500"),
    ("STEP 10.08", "make_chart.py",             "nifty500"),
    # MOVED FROM STEP 10i, and the move is load-bearing rather than cosmetic.
    # The combined chart is now generic over the selection, so it may need the 58's
    # and the 74's per-trade logs -- and those are written by STEP 12 immediately
    # above. At 10i they did not exist, which is why the old step could only ever
    # combine mid and n100. Its mid and n100 inputs are written at 10c and 10g, so
    # they are still upstream; nothing consumes the chart, so nothing downstream
    # moved. Output verified byte-identical across the move.
    # FIELD 4: this step is generic over the registry -- it loops the selected
    # tags rather than naming any. Field 3 stays None: main() takes no universe.
    ("STEP 12b", "make_combined_universes.py", None, SPANS_REGISTRY),
    ("STEP 15", "make_daily_log.py",           None),
    # ORDERING, AND WHY IT IS A STEP. STEP 16 reads the PERMANENT panels, so the
    # copy from /tmp must happen before it -- the constraint run_all.py used to
    # enforce with a bare call between two run() lines, and which S8 lost when it
    # folded the pipeline into one loop. It is a position in this list now, so
    # rewriting the loop cannot drop it. See results/save_caches_step.py.
    ("STEP 15b", "save_caches_step.py",        None),
    ("STEP 16", "nt_export_scores.py",         None),
    # STEP 17 IS THE EXECUTION HALF OF THE NAUTILUS STORY. STEP 16 exports the
    # score parquet the port READS; nothing in the pipeline ever ran the port
    # itself, so a normal run produced Nautilus input and no Nautilus output.
    # It must follow 16, which writes the parquet it loads.
    ("STEP 17", "nt_execute.py",               None),
    # STEP 18 IS THE TAX HALF, AND IT IS TWO ROWS BECAUSE THE ARTEFACTS ARE
    # PER-UNIVERSE. FY_TAX_STATEMENT, FY_EQUITY, HOLDING_PERIOD and
    # HOLDING_PERIOD_LOTS each carry the tag in their name and hold one
    # universe's lots, so main() takes a universe (arity 1).
    #
    # NEW LABELS, NOT 10i. That label meant make_combined_universes.py until it
    # moved to STEP 12b, and reusing it would make every log written before the
    # move ambiguous -- the same identity-over-compaction rule the 2026-09-11
    # retirement followed when it left STEPS 0-9 and 11-14 as gaps.
    #
    # AT THE END, BECAUSE THE ONLY INPUT IS THE SCORE PANEL. Running after
    # STEP 15b means the PERMANENT panel exists rather than relying on
    # config.require_cache's /tmp fallback. Nothing consumes what this writes,
    # so nothing downstream constrains it either.
    #
    # THE ROWS ARE UNCONDITIONAL AND THE STEP RETURNS EARLY AT tax=off. The
    # plan is therefore IDENTICAL under --tax on and --tax off, which is what
    # lets check_plan_order reason about one order instead of two. See
    # results/tax_report.main().
    # bh_lots_after_tax, ADDED 2026-09-19, AND IT IS A ROW RATHER THAN AN IMPORT
    # ON PURPOSE. STEP 18 composes TAX_TURNOVER from its own FY_EQUITY and this
    # step's BH_LOTS file, so the dependency is REAL; hiding it inside a
    # tax_report import would make it invisible to check_plan_order, which walks
    # the resolved plan and asks whether each declared input's writer comes
    # earlier in that same plan. It returns early at tax=off, like STEP 18.
    #
    # LABELS 17e-17h, unused before today, and NOT 18-anything: these run BEFORE
    # the 18 block, and a label that sorts after what it precedes is something a
    # reader has to re-derive every time.
    ("STEP 17e", "bh_lots_after_tax.py",      "midcap150"),
    ("STEP 17f", "bh_lots_after_tax.py",      "nifty100"),
    ("STEP 17g", "bh_lots_after_tax.py",      "nifty50"),
    ("STEP 17h", "bh_lots_after_tax.py",      "midcap50"),
    ("STEP 17i", "bh_lots_after_tax.py",      "midcap100"),
    ("STEP 17j", "bh_lots_after_tax.py",      "nifty200"),
    ("STEP 17.01", "bh_lots_after_tax.py",     "smallcap250"),
    ("STEP 17.02", "bh_lots_after_tax.py",     "nifty500"),
    ("STEP 18a", "tax_report.py",              "midcap150"),
    ("STEP 18b", "tax_report.py",              "nifty100"),
    ("STEP 18c", "tax_report.py",              "nifty50"),
    ("STEP 18d", "tax_report.py",              "midcap50"),
    ("STEP 18e", "tax_report.py",              "midcap100"),
    ("STEP 18f", "tax_report.py",              "nifty200"),
    ("STEP 18.01", "tax_report.py",            "smallcap250"),
    ("STEP 18.02", "tax_report.py",            "nifty500"),
]


# ---------------------------------------------------------------------------
# INPUT GUARD -- ordering bugs must fail by name, not as a pandas traceback
# ---------------------------------------------------------------------------
# Every entry is: consumer script -> [(file it reads, the step that writes it,
# the axis qualifier)].
#
# WHY THIS EXISTS. make_final_chart_fair.py read daily_trades_58.csv, which was
# produced two steps LATER. The pipeline appeared to work for months because the
# file survived in metrics/ from the previous run; the first run against a truly
# empty metrics/ died with a bare FileNotFoundError raised inside pandas, naming
# a path but not the step that owed it.
#
# ONLY NON-OBVIOUS DEPENDENCIES ARE LISTED -- the ones a reader would not catch
# by grepping, because the filename and the read() are in different places
# (helpers like tc_from_log() and before_tc() take a path argument, so the
# literal never appears next to a read_csv call).
#
# THIS GUARD DOES NOT MAKE ANY CONSUMER TOLERANT OF A MISSING FILE. A missing
# input is still fatal. It only replaces the traceback with a sentence that says
# which file is missing and who should have written it.
#
# ---------------------------------------------------------------------------
# STEP 8 OF THE COLLAPSE: IT IS DERIVED FROM THE REGISTRY, NOT WRITTEN OUT
# ---------------------------------------------------------------------------
# This was ten hand-written tuples, five per universe, and every one of them was
# `<that universe's metrics_dir> / <filename carrying its tag>` -- knowledge the
# registry already holds. Adding a universe meant finding all five; four of them
# outlived the 58 and the 74 by five days and were deleted in 6d618ac.
#
# THE PATHS COME FROM paths.py, NOT FROM A FORMAT STRING WRITTEN HERE.
# paths.tagged_artefact(u, "daily_trades") is the existing definition of the
# daily-audit family's naming -- the one place that puts the tag in the FILENAME
# as well as the directory -- and re-spelling it here would be a second rule that
# can disagree with the first. Same for nautilus_scores() and score_cache().
#
# THE STEP LABEL IS LOOKED UP FROM PIPELINE_ORDER BY (script, universe), NEVER
# RESTATED. The third element of each tuple used to read "STEP 10c make_audit.py"
# for mid and "STEP 10g make_audit.py" for n100 -- those are PIPELINE_ORDER
# labels, and a copy of them here would be the seventh hardcoded list in this
# repository, going stale against the rows above exactly as STEP_UNIVERSES and
# SCORE_BUILD_STEPS did. _step_label raises rather than guessing: a label that
# cannot be resolved means the producing step is not in PIPELINE_ORDER at all,
# which is a defect in the pipeline and not a formatting problem here.
#
# THIS TABLE IS NOT READ BY check_pipeline_order, AND THE COMMENT THAT SAID IT
# WAS HAS BEEN REMOVED. check_inputs' docstring claimed "check_pipeline_order
# reads the literal paths out of this table, and they are still literal paths in
# the same shape". It does not: analyse() scans PIPELINE_ORDER's step scripts and
# their STEP_HELPERS, and run_all.py is never among them. The claim was load-
# bearing for anyone deciding whether these could be computed -- it is why they
# were not -- so it is corrected rather than left.
def _step_label(script, tag):
    """The PIPELINE_ORDER label for one invocation: "STEP 10c make_audit.py".

    `tag` is the universe the producing invocation runs for, or None for a
    whole-run step. Raises rather than defaulting, because a producer that is not
    in PIPELINE_ORDER cannot be named in a guard that exists to say who owes a
    file.
    """
    for row in PIPELINE_ORDER:
        if row[1] == script and (row[2] if len(row) > 2 else None) == tag:
            return f"{row[0]} {script}"
    raise SystemExit(
        f"run_all.REQUIRED_INPUTS: no PIPELINE_ORDER row runs {script} for "
        f"universe {tag!r}, so the step that owes this input cannot be named.\n"
        f"  Either the producing step is missing from PIPELINE_ORDER -- in which "
        f"case it never runs for that universe -- or this dependency is stale. "
        f"Do not write the label in by hand; fix the row.")


# ---------------------------------------------------------------------------
# WHICH AXES AN INPUT'S NAME CARRIES -- THE FOURTH FIELD, AND WHY IT EXISTS
# ---------------------------------------------------------------------------
# check_inputs._present() used to compose cadence.suffix() + profiles.suffix()
# onto EVERY required input, as though all five were alike. Two of them are not.
#
#   `--rebal 200` on mid v3 completed eight of nine steps and died at STEP 16
#   demanding v_mid_expanding_cache_r200.csv. STEP 15b had written
#   v_mid_expanding_cache.csv and that was correct: the score panel does not vary
#   with cadence, so there is no r200 copy of it to write. The refusal machinery
#   was right and its SCOPE was wrong, and the two are indistinguishable at the
#   call site because the message is identical.
#
# THE SAME OVER-APPLICATION IS WHY `--profile tradeable` CANNOT COMPLETE. STEP 16
# demands v_mid_expanding_cache_tradeable.csv, and the score panel has no profile
# dimension either. One scope, two blocked axes.
#
# MEASURED, NOT ASSUMED, AND THE TWO AXES REST ON DIFFERENT EVIDENCE:
#
#   cadence   Built from source at r20 and r200, in one process, determinism
#             pinned before any numeric import. Raw panel and score panel
#             BYTE-IDENTICAL, sha256 163ad6db... and 4dae4a55... -- and both equal
#             the shipped caches. 19.0 and 17.4 minutes of scoring per pass.
#   profile   The transitive import closure of build_scores_step is seven modules
#             -- config, engine_core, features_v2, qbeast_in_charges, survivorship,
#             tradability -- and NONE of them imports or references `profiles`.
#             Code that never reads a value cannot vary with it.
#
# build_scores_step already declared `# naming: axis-free` on both writes. That was
# a CLAIM; it is now a measured one.
AXIS_FREE = ""                      # the name carries no run axis at all
CADENCE_PROFILE = "cadence,profile"  # the two axes _present() may compose


def _required_inputs():
    """The guard table, per registered universe. See the block above.

    EVERY ENTRY IS A 4-TUPLE and the fourth field is compulsory. A default would
    reproduce exactly the defect being closed: the whole failure was a rule applied
    uniformly to inputs that do not all carry the same axes, so "unspecified" must
    not be spellable.
    """
    import paths
    from universes.registry import REGISTRY
    out = {"make_chart.py": [], "make_combined_universes.py": [],
           "nt_execute.py": [], "nt_export_scores.py": [], "tax_report.py": [],
           "bh_lots_after_tax.py": []}
    for u in REGISTRY.values():
        # ARM-TAGGED. daily_trades_<tag>.csv is v2's audit trail and a selection
        # without v2 writes no v2 trail at all; daily_trades_v1_<tag>.csv exists
        # only when v1 is selected. Demanding either unconditionally made
        # `--arm v1,v3` impossible from a cold tree, and it only ever passed
        # because an earlier default run had left the file on disk.
        out["make_chart.py"].append(
            (paths.tagged_artefact(u, "daily_trades"),
             _step_label("make_audit.py", u.tag), f"u:{u.tag},v2", CADENCE_PROFILE))
        out["make_chart.py"].append(
            (paths.tagged_artefact(u, "daily_trades_v1"),
             _step_label("engine_v2_final.py", u.tag), f"u:{u.tag},v1", CADENCE_PROFILE))
        # THE COMBINED STEP READS EVERY SELECTED UNIVERSE'S TRADE LOG. It is
        # qualified by ARM only: the universe is carried by the path, and this
        # step runs once for whatever the selection holds. That is why it moved
        # from STEP 10i to STEP 12b -- at 10i the logs did not exist yet.
        # THE UNIVERSE IS NAMED HERE TOO, AND IT WAS NOT. This entry carried "v2"
        # alone -- the arm, and nothing about whose file it is -- so it was demanded
        # whatever the selection was. `--universe n100` therefore required mid's
        # trade log, which that plan never writes, while the step itself reads only
        # selected_tags() (make_combined_universes.py:184). Latent since step 6 and
        # invisible because mid's file was always on disk; found by
        # check_plan_order.py on its first run.
        #
        # STEP 12b IS STILL A WHOLE-RUN STEP. Its invocation carries tag=None, so
        # entry_applies() resolves `u:` against the run's selection -- the correct
        # scope for a step invoked once. What changed is that the ENTRY now says
        # which universe's file it is, so it drops when that universe is not
        # selected instead of being demanded regardless.
        out["make_combined_universes.py"].append(
            (paths.tagged_artefact(u, "daily_trades"),
             _step_label("make_audit.py", u.tag), f"u:{u.tag},v2", CADENCE_PROFILE))
        # UNIVERSE-TAGGED. The port loads the parquet for each SELECTED universe,
        # and a run that selected one universe has one of these.
        out["nt_execute.py"].append(
            (paths.nautilus_scores(u),
             _step_label("nt_export_scores.py", None), f"u:{u.tag}", AXIS_FREE))
        # STEP 16 reads the PERMANENT panels, which STEP 15b copies from /tmp.
        # Named so that if the two are ever re-ordered again the run stops with the
        # missing filename and the step that owes it, instead of dying inside
        # pandas with no indication of who writes it. nt_export_scores also falls
        # back to /tmp via config.require_cache, so this fires only when BOTH
        # copies are absent -- a genuine missing panel.
        out["nt_export_scores.py"].append(
            (paths.score_cache(u),
             _step_label("save_caches_step.py", None), f"u:{u.tag}", AXIS_FREE))
        # STEP 18 RE-RUNS THE BACKTEST, so its only input is the score panel --
        # the same one nt_export_scores reads, from the same writer.
        #
        # NOT QUALIFIED `tax:on`, AND THAT IS DELIBERATE. The score panel exists
        # on every run; it does not vary with the tax axis and is not produced
        # by it. Adding `tax:on` here would make the entry drop at tax=off,
        # which is harmless in effect and FALSE in what it asserts -- it would
        # say this input is tax-dependent. An entry that misdescribes itself is
        # the shape of defect this table keeps finding. See the `tax:` branch in
        # entry_applies() for what a qualified entry would look like.
        #
        # AXIS_FREE for the reason the --rebal 200 refusal established: the
        # score panel carries no axis suffix, so composing one onto it would
        # demand v_mid_expanding_cache_tax.csv, which nothing writes.
        out["tax_report.py"].append(
            (paths.score_cache(u),
             _step_label("save_caches_step.py", None), f"u:{u.tag}", AXIS_FREE))
    return out


REQUIRED_INPUTS = _required_inputs()

# DECLARE OR FAIL, CHECKED AT IMPORT. The table is derived, so this can only fire
# on an edit to _required_inputs() -- which is the point: the next person adding a
# consumer is stopped here rather than inheriting a silent default.
_undeclared = [(c, e[0].name) for c, lst in REQUIRED_INPUTS.items() for e in lst
               if len(e) < 4]
if _undeclared:
    raise SystemExit(
        "run_all.REQUIRED_INPUTS: these entries do not declare which axes their "
        "name carries:\n"
        + "\n".join(f"    {c}  {n}" for c, n in _undeclared)
        + "\n  Add AXIS_FREE or CADENCE_PROFILE as the fourth field. There is no "
          "default, because the defect this closes was a rule applied uniformly to "
          "inputs that do not all carry the same axes.")
# Kept as the canonical set of pipeline script names. run()'s membership guard used
# it; run.py needs the same answer when it maps a step to its universe.
_PIPELINE_SCRIPTS = {row[1] for row in PIPELINE_ORDER}


def entry_applies(e, tag, usel, asel, label="", script=""):
    """Is this REQUIRED_INPUTS entry required by THIS INVOCATION?

    ONE DEFINITION, CALLED FROM TWO PLACES: check_inputs() below, which asks it at
    run time about files on disk, and check_plan_order.py, which asks it at plan
    time about ordering. A second copy of this predicate is exactly the shape this
    repository keeps finding -- the two would answer differently the day one is
    edited, and the ordering check would then be verifying a rule the runtime does
    not use.

    `e`     the entry: (path, writer label, qualifiers[, naming axes])
    `tag`   the universe of the INVOCATION, or None for a whole-run step
    `usel`  the universes this run selected      `asel` the arms it selected

    No third field -> always. Otherwise the field is a COMMA-SEPARATED LIST OF
    QUALIFIERS, ALL of which must hold: "u:<tag>" names a universe, anything else
    names an arm that must be selected.

    A `u:` QUALIFIER IS EVALUATED AGAINST THE INVOCATION, NOT THE RUN. This is the
    defect this function grew a parameter for. The qualifier arrived with step 6 to
    stop a merged make_chart.py demanding the other universe's files, and it was
    tested with `q[2:] in selected_tags()` -- which asks "did this RUN select
    n100", not "is this invocation n100". Both hold under `--universe all`, so
    STEP 10d (mid's chart) demanded n100's trade logs, which STEP 10f and 10g write
    afterwards. Unsatisfiable on a cold tree, and invisible on a warm one.

    THE LIST FORM ARRIVED WITH STEP 6. Before the collapse, a chart's inputs were
    keyed by a per-universe FILENAME -- make_mid_chart.py -- so the file identity
    supplied the universe and the third field only had to name the arm. One merged
    make_chart.py serves both universes from one key, so a `--universe mid` run
    would have been made to demand n100's trade logs. The universe is now written
    down beside the arm instead of being implied by which file the entry sits under.
    """
    # ----------------------------------------------------------------------
    # DECLARE OR FAIL. A per-universe invocation reaching an entry that does not
    # say which universe it belongs to is an UNDER-DECLARED ENTRY, and it is
    # refused rather than skipped or assumed.
    # ----------------------------------------------------------------------
    # WHY REFUSE RATHER THAN SKIP OR ASSUME. Skipping drops a real input and the
    # step dies later inside pandas, which is what this table exists to prevent.
    # Assuming it applies is how the defect above behaved for five days: it read as
    # coverage and demanded another universe's files. Neither answer can be right,
    # because the entry does not contain the information needed to choose -- so the
    # entry is the thing to fix.
    #
    # THIS IS WHAT COVERS THE KEYS THAT HAVE NO ENTRIES YET. make_audit.py and
    # engine_v2_final.py are per-universe steps (main() arity 1) with no
    # REQUIRED_INPUTS entries at all, so there is nothing to mis-scope today. They
    # acquire this defect the moment someone adds their first entry without a `u:`,
    # and this is the line that stops them.
    #
    # NO "APPLIES TO EVERY UNIVERSE" MARKER WAS ADDED, and that is a decision
    # rather than an omission. _required_inputs() emits every entry inside
    # `for u in REGISTRY.values()`, so a per-universe entry that applies to all
    # universes cannot be authored -- the loop produces one per universe, each
    # carrying its own u:. A marker would be vocabulary for a case the table's
    # shape excludes. AXIS_FREE is NOT that marker: it is the FOURTH field and
    # answers a different question -- which axes the filename carries -- and the
    # two sit on the same tuple, so spending that word here would give it two
    # meanings in one place.
    # IMPORTED LOCALLY, as cadence and profiles are in this file. run_all is
    # imported by check_plan_order via runpy at module scope and must not pull an
    # axis module in at import time.
    import tax as _tax

    quals = [q.strip() for q in str(e[2]).split(",")] if len(e) >= 3 else []
    if tag is not None and not any(q.startswith("u:") for q in quals):
        raise SystemExit(
            f"REQUIRED_INPUTS: {script or '(step)'} is invoked per universe "
            f"({label or '(step)'}, universe {tag!r}), but this entry does not "
            f"declare which universe it belongs to:\n"
            f"    file   {e[0]}\n"
            f"    writer {e[1]}\n"
            f"    third field {(str(e[2]) if len(e) >= 3 else '(absent)')!r}\n"
            f"  A per-universe step must not inherit another universe's inputs. "
            f"Add a `u:<tag>` qualifier -- entries are emitted inside the "
            f"`for u in REGISTRY.values()` loop in _required_inputs(), so the tag "
            f"is `f\"u:{{u.tag}}\"` there. Do not make the step tolerant of the "
            f"file instead.")

    if len(e) < 3:
        return True
    for q in quals:
        if not q:
            continue
        if q.startswith("tax:"):
            # THE TAX QUALIFIER IS EVALUATED AGAINST THE RUN, NOT THE INVOCATION,
            # AND THAT IS THE OPPOSITE OF `u:` ON PURPOSE.
            #
            # `u:` had to move to invocation scope because ONE SCRIPT SERVES TWO
            # UNIVERSES IN ONE RUN -- merged make_chart.py is STEP 10d for mid and
            # STEP 10h for n100 -- so "did this RUN select n100" and "is this
            # INVOCATION n100" are different questions and the plan built from the
            # wrong one was unsatisfiable.
            #
            # There is no such collapse on the tax axis. run.py sets the tax
            # selection once, no script serves both a taxed and an untaxed
            # invocation, and run scope and invocation scope are provably the same
            # value. "Provably" is checked rather than trusted:
            # tax.is_uniform_over_plan() exists so that the day a per-universe tax
            # selection is introduced, THAT assertion fires at plan time instead of
            # this qualifier quietly answering the wrong question for five days.
            #
            # ZERO ENTRIES USE THIS TODAY, AND SAYING SO IS THE POINT.
            # Nothing in REQUIRED_INPUTS carries a `tax:` qualifier, because no
            # step reads a file that only exists under tax=on. STEP 18 WRITES
            # the four tax artefacts and nothing consumes them, and its own
            # input -- the score panel -- is not tax-dependent, so qualifying it
            # would be false (see the tax_report.py entry in _required_inputs).
            #
            # THE SHAPE THAT WOULD USE IT is a CONSUMER of a tax artefact:
            #
            #     out["some_tax_chart.py"].append(
            #         (M / "FY_TAX_STATEMENT_<tag>_tax.csv",
            #          _step_label("tax_report.py", u.tag),
            #          f"u:{u.tag},tax:on", naming.AXES))
            #
            # -- demanded when the run is taxed and dropped when it is not, so a
            # tax=off plan does not require a file that run never writes.
            #
            # IT IS LEFT UNUSED RATHER THAN REVERTED. An unused mechanism that
            # says it is unused costs one comment; the alternative on offer was
            # to attach it to the score-panel entry so it would look used, which
            # would have made the table assert something untrue in order to
            # avoid this paragraph.
            ok = (_tax.selected() if q[4:] == "on" else not _tax.selected())
        elif q.startswith("u:"):
            # THE tag-IS-None BRANCH IS THE WHOLE-RUN CONTRACT, NOT A FALLBACK.
            # PIPELINE_ORDER's third field is None for a step whose main() takes no
            # universe (make_daily_log.py; likewise STEP 12b, 15b, 16, 17). Such a
            # step is invoked ONCE and legitimately reads every SELECTED universe,
            # so the run's selection is the correct scope for it -- the only scope
            # it has. A per-universe invocation has a narrower one and must use it.
            ok = (q[2:] == tag) if tag is not None else (q[2:] in usel)
        else:
            ok = q in asel
        if not ok:
            return False
    return True


def check_inputs(label, script, tag):
    """Fail by name before a step runs, rather than from inside pandas.

    AN ENTRY MAY CARRY A THIRD FIELD, the arm it belongs to. That input is
    required only when the arm is selected: daily_trades_v1_mid.csv is not
    written by `--arm v2`, and demanding it there turned a correct selective run
    into a hard stop. Entries with no third field are required unconditionally,
    which is all of them but two.

    THE STATIC INVENTORY IS UNAFFECTED, AND NOT FOR THE REASON THIS DOCSTRING
    USED TO GIVE. It said check_pipeline_order reads the literal paths out of
    REQUIRED_INPUTS, so they had to stay literal. It does not: analyse() scans
    PIPELINE_ORDER's step scripts and their STEP_HELPERS, and run_all.py is never
    among them. The edge inventory is unaffected because this table was never part
    of it -- which is what made step 8 possible.
    """
    import arms.registry as _ar
    import cadence as _cd
    _sel = set(_ar.selected_names())

    def _present(f, axes):
        """EXACTLY the name this run's axes produce, or the run does not start.

        STOPGAP, 2026-09-12. This is not the fix. The fix is a single naming
        authority that every writer, reader and guard calls; this closes the
        dangerous half of the bug until that lands, and it closes it by refusing
        rather than by guessing.

        WHAT IT USED TO DO AND WHY THAT WAS WORSE THAN BLOCKING. It accepted the
        canonical name OR its cadence sibling. Both branches could be satisfied by
        a file belonging to a DIFFERENT PROFILE:

          branch 1, default cadence -- a research canonical file left on disk by
            any earlier run satisfied the guard during a `tradeable` run;
          branch 3, non-default cadence -- a research `_r40` sibling satisfied it
            while the run itself wrote `_r40_tradeable`.

        In both cases the guard reports the input as covered and attributes it to
        the wrong file. That is the same shape as DIRKEY and NAUTILUS_SCRIPTS: a
        check that says covered while pointing somewhere else. A visible block is
        strictly better, because the alternative is a cross-profile number
        published with nothing saying so.

        THE CONDITIONS FOR IT CAME INTO EXISTENCE ON 2026-09-12, when the engines
        and charts became profile-aware (f6b970b) while this guard did not. Before
        that a tradeable run wrote the canonical name, so branch 1 matched the file
        that run had itself just written -- wrong for a different reason, but not a
        misattribution.

        THE CADENCE PROBLEM THE FALLBACK EXISTED FOR IS REAL AND IS NOT
        REINTRODUCED. Under --rebal 40 the producers write
        daily_trades_mid_r40.csv and leave the cadence-20 file alone. The guard
        therefore asks for the name THIS RUN'S AXES PRODUCE, built the same way the
        producers build it, rather than for the canonical name with a fallback.
        """
        import profiles as _pf
        # ONLY THE AXES THIS INPUT'S NAME ACTUALLY CARRIES. This used to compose
        # both suffixes onto every input, which is how a correct refusal came to
        # be raised against a file that does not and should not exist: the score
        # panel is invariant to both axes, so there is no _r200 or _tradeable copy
        # of it for STEP 15b to have written. Measured; see the block above
        # _required_inputs(). An input that DOES carry an axis is unchanged, and
        # the substitution refusal below is unchanged with it.
        _sfx = ""
        if "cadence" in axes and not _cd.is_default():
            _sfx += _cd.suffix()
        if "profile" in axes and not _pf.is_default():
            _sfx += _pf.suffix()
        want = f if not _sfx else f.with_name(f.stem + _sfx + f.suffix)
        if want.exists():
            return True
        _found.append((f, want, sorted(
            q.name for q in want.parent.glob(f.stem + "*" + f.suffix))[:6]))
        return False

    import universes.registry as _ur
    _usel = set(_ur.selected_tags())

    def _wanted(e):
        """This invocation's view of one entry. See entry_applies() above -- ONE
        definition, shared with check_plan_order.py."""
        return entry_applies(e, tag, _usel, _sel, label, Path(script).name)

    _found = []
    missing = [(e[0], e[1]) for e in REQUIRED_INPUTS.get(Path(script).name, [])
               if _wanted(e) and not _present(e[0], e[3])]
    if not missing:
        return
    print("\n" + "!" * 90)
    print(f"PIPELINE ORDERING ERROR -- cannot start {label}")
    print("!" * 90)
    print(f"\n  {Path(script).name} needs {len(missing)} file(s) that do not exist:\n")
    _want = {c: (w, near) for c, w, near in _found}
    for f, who in missing:
        w, near = _want.get(f, (f, []))
        print(f"    MISSING  {w.relative_to(ROOT)}")
        print(f"      writer {who}")
        if w != f:
            print(f"      this run's axes name it {w.name}, not {f.name}")
        if near:
            print(f"      present in that directory: {', '.join(near)}")
        elif w != f and f.exists():
            print(f"      {f.name} EXISTS but belongs to another profile or "
                  f"cadence and is NOT accepted")
    print("\n  Each of these is written by another pipeline step. If that step is")
    print("  listed AFTER this one in run_all.py, the order is wrong and the step")
    print("  must be moved earlier -- not made tolerant of the missing file.")
    print("  If the step ran and the file is still absent, that step failed quietly.")
    print("\n  A file of the same name from another profile or cadence is NOT")
    print("  accepted as a substitute, deliberately: it would publish one axis's")
    print("  numbers under another's. See the note on _present() above.")
    print("  That applies to inputs whose NAME carries the axis. An input declared")
    print("  AXIS_FREE is asked for by its one true name, because it has no other.")
    print("!" * 90, flush=True)
    sys.exit(1)


# THE SUBPROCESS RUNNER IS GONE, AND SO IS THE GUARD IT CARRIED.
# run() used to spawn each step with sys.executable and refuse any script absent
# from PIPELINE_ORDER -- a step added to main() but not to the list would otherwise
# have been invisible to the static ordering check. main() no longer names steps at
# all: run.py iterates PIPELINE_ORDER itself, so a step outside the list cannot run
# in the first place and the guard has nothing left to catch. It is removed rather
# than kept as unreachable code that reads like it is still protecting something.


def restore_cache_to_tmp():
    """Restore permanent copies into /tmp so scripts run without rebuilding."""
    # FROM THE REGISTRY. This was eight literal triples, four of them the deleted
    # 58's and 74's -- missed by 85f68a4's sweep, which claimed to have removed
    # every hardcoded universe list. Harmless only because the permanent files it
    # named no longer exist.
    # IMPORTED HERE, not at module level: run_all is imported by run.py before
    # the determinism pin's env vars would otherwise be set, and config pulls in
    # pandas. Every other registry/config use in this function is local for the
    # same reason.
    import config
    from universes.registry import REGISTRY
    pairs = [(u.score_cache.name, u.score_tmp.name, u.score_cache.parent)
             for u in REGISTRY.values()] + \
            [(u.raw_cache.name, u.raw_tmp.name, u.raw_cache.parent)
             for u in REGISTRY.values()]
    # THE SIDECAR TRAVELS WITH THE PANEL, OR THE PANEL DOES NOT TRAVEL.
    #
    # This copied the cache alone until 2026-09-18, which put a hole straight
    # through the provenance check added the same week: build_scores_step
    # verifies a warm /tmp panel and save_caches_step refuses to persist one
    # without a sidecar, and this function -- which runs at the START of every
    # run.py invocation -- was manufacturing exactly that file. MEASURED: on the
    # migrated tree, `run.py --universe n100` died at STEP 10e, its FIRST step,
    # on /tmp/v_n100_expanding.csv having no sidecar. n50 was not involved. Any
    # second run of a tree with permanent caches hit it.
    #
    # REFUSAL, NOT SILENT COPYING, when the permanent cache has no sidecar of its
    # own. Restoring it would put a panel of unknown origin where every
    # downstream step expects one it can check, which is the thing 8e32551 exists
    # to prevent; and inventing a sidecar here from the current raw_data_dir
    # would be forging the claim rather than carrying it. The remedy is in the
    # message: delete the cache and rebuild.
    for perm_name, tmp_name, folder in pairs:
        perm = folder / perm_name
        if perm.exists() and not (TMP / tmp_name).exists():
            side = config.cache_source_file(perm)
            if not side.exists():
                raise config.CacheSourceError(
                    f"refusing to restore {perm} into {TMP / tmp_name}: it has "
                    f"no source sidecar ({side.name}).\n"
                    f"  A restored panel whose origin cannot be established is "
                    f"exactly what the provenance check exists to refuse, and\n"
                    f"  copying it here would place it where every later step "
                    f"trusts it.\n"
                    f"  Delete {perm} and rebuild with "
                    f"`./venv/bin/python run_all.py`.")
            shutil.copy(perm, TMP / tmp_name)
            shutil.copy(side, config.cache_source_file(TMP / tmp_name))
            print(f"    restored {tmp_name} from permanent cache (with source)")

def save_permanent_caches():
    """Copy the /tmp panels back to their permanent homes.

    THE BODY MOVED TO results/save_caches_step.py, WHICH IS NOW STEP 15b. This
    stays as the one name callers already use, delegating rather than holding a
    second copy of the pair list -- two lists to keep in agreement is how the
    constraint got lost the first time.

    The eight hand-written pairs this used to carry are reproduced exactly by the
    step's registry-derived ones; verified pair for pair before the move.
    """
    sys.path.insert(0, str(R))
    import save_caches_step
    save_caches_step.main()


def naming_gate():
    """Run naming_declare_check in gated-declared-only mode. Non-zero stops the run.

    WHY THIS GATES AT ALL WHEN 117 CALLS ARE STILL UNDECLARED. Two options were
    rejected. Running it non-blocking would put a third checker in the pipeline
    that prints a banner and gets treated as coverage. Keeping it out until the
    count reaches zero would leave the whole backlog unenforced -- and during that
    window nothing stops a NEW writer landing undeclared, which is exactly how this
    bug class reached three axes in the first place.

    So it gates the DECLARED SET and only that. A site enters the set the moment
    someone declares it and cannot leave; inside the set, an undeclared sibling
    write blocks. Gate 2 and any DEFECT declaration block everywhere,
    unconditionally. Undeclared calls in sites nobody has touched yet are reported
    and do not block. The gated set is green today, so this is enforcing at zero
    from the first run rather than waiting for a backlog to clear.

    THE RATCHET IS NOT WIRED IN HERE. It needs a base revision to diff against,
    which a pipeline run does not have and a review does:

        ./venv/bin/python naming_declare_check.py --gate-declared-only --ratchet origin/main

    That is the call that closes the new-writer hole, and it belongs wherever
    changes are reviewed, not in the thing that runs the backtest.
    """
    import subprocess
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "naming_declare_check.py"),
         "--gate-declared-only"],
        cwd=Path(__file__).resolve().parent)
    if r.returncode != 0:
        print("\nNAMING GATE FAILED -- the run has not started.")
        print("An artefact would be written under a name that cannot say what")
        print("produced it. Fix the declaration or the composer, then re-run.")
    return r.returncode


def main():
    """Delegate to run.py. This file is now a compatibility entry point.

    WHAT STILL LIVES HERE, AND WHY IT WAS NOT MOVED
        PIPELINE_ORDER, REQUIRED_INPUTS, STEP_HELPERS,
        STEP_DIRS, script_path(), check_inputs(), the cache lists and the two
        cache functions are all READ BY run.py, which loads this file with
        runpy.run_path to get them. They are the ordered description of the pipeline;
        run.py is the thing that chooses a subset of it and runs it. Copying them
        into run.py would leave two orderings to keep in agreement, which is the
        class of bug check_pipeline_order.py exists to catch.

    WHAT CHANGED FOR SOMEONE WHO RUNS THIS FILE
        Steps now run IN THIS PROCESS rather than as thirty-one subprocesses, with
        module_state.pinned() restoring any shared global a step reassigns -- the
        thing a fresh interpreter used to give for free. The step labels in the log
        are PIPELINE_ORDER's short ones ("STEP 10c") rather than main()'s longer
        descriptions; the steps, their order, and their outputs are the same.

        `--fresh` still works. It is forwarded.
    """
    extra = [a for a in sys.argv[1:] if a != "--fresh"]
    if extra:
        # THIS FILE TAKES ONE FLAG. It never used argparse -- FRESH is a bare
        # `"--fresh" in sys.argv` -- so every other argument was silently ignored
        # and the full pipeline started anyway. `run_all.py --help` launching a
        # three-hour rebuild is not a help message. Unrecognised arguments now stop
        # the run and point at the entry point that understands them.
        print(__doc__)
        print(f"run_all.py takes only --fresh; got {' '.join(extra)}")
        print("For anything else -- one universe, one arm, --list, --dry-run,")
        print("--rebal -- use run.py, which this file now delegates to:")
        print("    ./venv/bin/python run.py --help")
        return 2

    rc = naming_gate()
    if rc != 0:
        return rc

    import run as _run
    argv = ["--universe", "all", "--arm", "all"]
    if FRESH:
        argv.append("--fresh")
    return _run.main(argv)


if __name__ == "__main__":
    sys.exit(main())
