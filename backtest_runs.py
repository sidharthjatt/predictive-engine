"""
backtest_runs.py -- run the pipeline and every (universe, arm) cell.

Sections, in order:
  1. the pipeline: PIPELINE_ORDER (one row per step invocation), the input guard
     (REQUIRED_INPUTS, check_inputs), the step table (STEP_HOME, step_source,
     step_function) and the naming gate
  2. the steps that run a universe: build_scores, engine_v2_final
  3. the arm runner: run_arm, run_v34 and the v34 writers; fixed-capital figures;
     buy-and-hold holdings
  4. the steps that audit it: audit_step, bh_lots_after_tax

run.py is the entry point. Reports and charts are in reports.py, the dashboard in
dashboard.py, the strategy itself in portfolio.py.
"""
# ---------------------------------------------------------------------------
# DETERMINISM PIN -- SET BEFORE ANY NUMERIC LIBRARY IS IMPORTED.
# ---------------------------------------------------------------------------
# run.py sets the same values at its top, before any numeric import; this copy
# covers an import of this file from anywhere else. See run.py for the reasons.
import os as _os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ[_v] = "1"
_os.environ["PYTHONHASHSEED"] = "0"

import sys
from pathlib import Path
# engine_core.py (metrics() and the validation backtest) stays in results/ until
# batch 8 moves it into checks.py.
sys.path.append(str(Path(__file__).resolve().parent / "results"))

import matplotlib
matplotlib.use("Agg")
import time
import shutil
import settings
import model
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from settings import cadence
from settings import dd_axis
import portfolio as arm_reg
from engine_core import metrics
from market_data import precompute
from portfolio import backtest_exposure
from portfolio import CASH_YIELD
import costs
import market_data
from market_data import read_table
from settings import capital_axis as _capital_axis
from settings import impact_axis
from settings import pcap_axis
import subprocess
from decimal import Decimal
from decimal import localcontext
from costs import calc_tc
from costs import SLIPPAGE
from costs import fill_price
import os
from settings import capital_axis
from settings import REGISTRY


# ======================================================================================
# THE PIPELINE: STEP TABLE, INPUT GUARD, NAMING GATE. From run_all.py (moved 2026-11-27).
# ======================================================================================
# run_all.py -- the complete pipeline (every universe + benchmark), from scratch, in one command.
# =================================================================================
#     ./venv/bin/python run.py --universe all --arm all            # uses cache if present
#     ./venv/bin/python run.py --universe all --arm all --fresh    # everything from scratch
#
# On a new machine or from nothing: `./venv/bin/python run.py --universe all --arm all --fresh`
#
# THE INTERPRETER IN THAT COMMAND IS LOAD-BEARING. IT IS NOT INTERCHANGEABLE WITH
# `python3`.
#     Every step now runs IN THIS INTERPRETER (run.py imports and calls it), which
#     makes the command line the only interpreter there is -- no fallback and no
#     second chance. It was true when steps were subprocesses too, because the
#     subprocess was spawned with sys.executable and inherited the same wrong
#     interpreter thirty-one times; it is if anything more direct now.
#
#     Corrected 2026-09-02. This docstring previously said `python3 run_all.py`.
#     On the machine the published numbers were produced on, `python3` resolves to
#     Python 3.11 with no lightgbm, so that command died at STEP 1 with
#     ModuleNotFoundError -- and 3.11 is also BELOW nautilus_trader's 3.12 floor,
#     which requirements.txt warns about. Both failures had the same cause.
#     See KNOWN_ISSUES.md, "The documented commands are not verified against the
#     machine they run on".
#
# This rebuilds both universes, the benchmark comparison, and every chart and CSV.
#
# ORDER:
#   === MIDCAP150 ===
#   10a. build_scores (midcap150)    -> MidCap150 scores (SLOW)
#   10b. engine_v2_final (midcap150) -> MidCap150 v2 FINAL
#   10c. audit_step (midcap150)      -> MidCap150 daily audit CSVs
#   10d. make_chart (midcap150)      -> MidCap150 chart + cap-weighted index benchmark
#   === NIFTY 100 ===
#   10e. build_scores (nifty100)     -> Nifty 100 scores (SLOW)
#   10f. engine_v2_final (nifty100)  -> Nifty 100 v2 FINAL
#   10g. audit_step (nifty100)       -> Nifty 100 daily audit CSVs
#   10h. make_chart (nifty100)       -> Nifty 100 chart + cap-weighted index benchmark
#   === ACROSS UNIVERSES ===
#   12b. make_combined_universes -> the published comparison figure
#   15.  make_daily_log          -> forensic daily text log
#   16.  nt_export_scores        -> Nautilus score parquets
#   17.  nt_execute              -> the execution engine, per (universe, arm)
#
# STEPS 0-9 AND 11-14 ARE GONE, not renumbered. They belonged to two retired
# universes, deleted on 2026-09-11; the surviving numbering is left as it was so
# a step's name means the same thing it did in every log and every document
# written before that date. See git history (git show 50562ed:RETIRED_UNIVERSES.md).
#
# ORDERING IS LOAD-BEARING. A consumer must never be listed before its producer.
# backtest_runs.py enforces the non-obvious cases itself -- see REQUIRED_INPUTS below,
# which fails with the missing filename and the owing step instead of a pandas
# FileNotFoundError.

ROOT = Path(__file__).resolve().parent
R = ROOT / "results"


# WHERE EACH STEP LIVES. A PIPELINE_ORDER row names a step; this table names the
# file and the function that runs it. The function takes a universe when the row
# names one, and nothing when the row names None; run.py checks the two against
# each other at plan time (run._resolve_arity). The two Nautilus steps keep their
# own files and main() until batch 8 moves them into nautilus_port.py.
STEP_HOME = {
    "build_scores":            ("backtest_runs.py", "build_scores"),
    "engine_v2_final":         ("backtest_runs.py", "engine_v2_final"),
    "audit_step":              ("backtest_runs.py", "audit_step"),
    "bh_lots_after_tax":       ("backtest_runs.py", "bh_lots_after_tax"),
    "make_chart":              ("reports.py", "make_chart"),
    "make_combined_universes": ("reports.py", "make_combined_universes"),
    "make_daily_log":          ("reports.py", "make_daily_log"),
    "tax_report":              ("reports.py", "tax_report"),
    "nt_export_scores":        ("nautilus/nt_export_scores.py", "main"),
    "nt_execute":              ("nautilus/nt_execute.py", "main"),
}


def step_source(step):
    """(file, function name) of a step, without importing anything. run.py reads
    the function's signature from the file, so --list never loads nautilus_trader."""
    if step not in STEP_HOME:
        raise SystemExit(f"backtest_runs.STEP_HOME has no entry for step {step!r}; "
                         f"known: {', '.join(STEP_HOME)}")
    rel, fn = STEP_HOME[step]
    return ROOT / rel, fn


def step_function(step):
    """The function that runs a step, imported on first use."""
    import importlib
    path, fn = step_source(step)
    return getattr(importlib.import_module(path.stem), fn)

# THE PANEL CACHES ARE REGISTRY ATTRIBUTES, u.score_cache and u.raw_cache under
# cache/<tag>/. This file used to carry CACHE_TMP -- fourteen /tmp names, eight of
# them retired universes' and none of them a live universe's -- and
# CACHE_PERM over every registered universe. `--fresh` cleared both lists, so it
# deleted seven unselected universes' panels and missed the selected one's /tmp
# copy, which the next step then reused. run.py now clears the selected
# universes' panels from the registry and nothing else.

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
# e.g. ("midcap150", "nifty100"), which is checked against the registry and is exactly the
# spelling that says "these, and not whatever arrives later".
#
#   None              touches no universe metrics directory (the default, and what
#                     every per-universe row uses -- field 3 already names it)
#   ("midcap150", "nifty100")
#                     touches exactly these, and does not follow the registry
#   SPANS_REGISTRY    generic over the registry, resolved live at scan time
#
# SPANS_REGISTRY IS LOAD-BEARING ON THE AUTHOR BEING HONEST, AND NOTHING CHECKS IT.
# STATED HERE, AT THE POINT OF USE, RATHER THAN LEFT FOR WHOEVER TRUSTS IT.
#
# The sentinel is a claim ABOUT THE SOURCE: that the step's paths are built from a
# loop over the registered tags, so every registered directory really is touched.
# If that claim is false -- paths built inside an `if t == "midcap150":` branch, say --
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
        from settings import REGISTRY
        return tuple(REGISTRY)
    unknown = [t for t in span if t not in _registry_tags()]
    if unknown:
        raise SystemExit(
            f"backtest_runs.PIPELINE_ORDER: row {row[0]} {row[1]} declares a span over "
            f"universe(s) the registry does not define: {sorted(unknown)}.\n"
            f"  The fourth field is the set of universes whose metrics directories "
            f"this step touches.\n"
            f"  Known: {sorted(_registry_tags())}. Use SPANS_REGISTRY if the step "
            f"is generic over the registry rather than naming a subset.")
    return tuple(span)


def _registry_tags():
    from settings import REGISTRY
    return set(REGISTRY)


# HOW MANY ROWS THIS TABLE HAS, DECLARED, so that a bulk edit over it cannot
# quietly cover part of it. check_all.py asserts len(PIPELINE_ORDER) against this
# number and fails when they disagree.
#
# IT EXISTS BECAUSE A REGEX MATCHED 12 OF 15 ROWS, TWICE. The script column
# contains digits -- backtest_runs.py -- so a `"[a-z_]+\.py"` pattern skips the
# three engine rows and rewrites the rest. Both times the edit was a universe
# rename, both times the result imported cleanly, and both times the only thing
# that caught it was an assertion the author happened to write. This constant
# makes that assertion the repository's rather than the author's.
#
# UPDATE IT BY HAND when a row is added or removed. That is the point: a number
# derived from the table it is checking would agree with any table.
PIPELINE_ROW_COUNT = 76

PIPELINE_ORDER = [
    ("STEP 10a", "build_scores",            "midcap150"),
    ("STEP 10b", "engine_v2_final",         "midcap150"),
    ("STEP 10c", "audit_step",              "midcap150"),
    ("STEP 10d", "make_chart",              "midcap150"),
    ("STEP 10e", "build_scores",            "nifty100"),
    ("STEP 10f", "engine_v2_final",         "nifty100"),
    ("STEP 10g", "audit_step",              "nifty100"),
    ("STEP 10h", "make_chart",              "nifty100"),
    # nifty50, ADDED 2026-09-18. NEW LABELS, NOT 10i-10l. 10i meant
    # reports.py until it moved to STEP 12b, and reusing any of
    # that block would make every log written before the move ambiguous -- the
    # same identity-over-compaction rule the 2026-09-11 retirement followed when
    # it left STEPS 0-9 and 11-14 as gaps rather than renumbering.
    ("STEP 10m", "build_scores",            "nifty50"),
    ("STEP 10n", "engine_v2_final",         "nifty50"),
    ("STEP 10o", "audit_step",              "nifty50"),
    ("STEP 10p", "make_chart",              "nifty50"),
    # midcap50, ADDED 2026-09-18. NEW LABELS AGAIN, 10q-10t, and not 10i-10l
    # for the reason the nifty50 block states: a reused label makes every log
    # written before the reuse ambiguous.
    ("STEP 10q", "build_scores",            "midcap50"),
    ("STEP 10r", "engine_v2_final",         "midcap50"),
    ("STEP 10s", "audit_step",              "midcap50"),
    ("STEP 10t", "make_chart",              "midcap50"),
    # midcap100, ADDED 2026-09-19. NEW LABELS AGAIN, 10u-10x, same rule: a
    # reused label makes every log written before the reuse ambiguous.
    ("STEP 10u", "build_scores",            "midcap100"),
    ("STEP 10v", "engine_v2_final",         "midcap100"),
    ("STEP 10w", "audit_step",              "midcap100"),
    ("STEP 10x", "make_chart",              "midcap100"),
    # nifty200, ADDED 2026-09-19, AND THE 10-SERIES IS NOW EXHAUSTED.
    #
    # 10y and 10z are the last single-letter suffixes, and a universe needs
    # FOUR. 10i-10l are burnt -- they were make_combined_universes' labels
    # before it moved to STEP 12b, and the nifty50 block above states why a reused
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
    ("STEP 10y",  "build_scores",           "nifty200"),
    ("STEP 10z",  "engine_v2_final",        "nifty200"),
    ("STEP 10za", "audit_step",             "nifty200"),
    ("STEP 10zb", "make_chart",             "nifty200"),
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
    # -- check_pipeline_order.plan_analyse() builds its pos map from enumerate(pipeline) --
    # and nothing parses or sorts a label. _step_label() matches rows by
    # (script, tag) and treats the string as opaque. The label must be unique
    # because it is a dict key there and part of check_all's GATE 2/GATE 4
    # failure identity; it must be readable because people read it. It does
    # not have to sort, and commit 615e257 was wrong to present that as a
    # requirement rather than as the convention it is.
    # ---------------------------------------------------------------------
    # smallcap250, ADDED 2026-09-19 -- THE FIRST UNIVERSE ON THE NEW SCHEME.
    ("STEP 10.01", "build_scores",           "smallcap250"),
    ("STEP 10.02", "engine_v2_final",        "smallcap250"),
    ("STEP 10.03", "audit_step",             "smallcap250"),
    ("STEP 10.04", "make_chart",             "smallcap250"),
    # nifty500, ADDED 2026-09-19. THE EIGHTH AND LAST SUPPLIER FOLDER.
    ("STEP 10.05", "build_scores",           "nifty500"),
    ("STEP 10.06", "engine_v2_final",        "nifty500"),
    ("STEP 10.07", "audit_step",             "nifty500"),
    ("STEP 10.08", "make_chart",             "nifty500"),
    # microcap250, ADDED 2026-10-10 with the supplier's ninth folder.
    ("STEP 10.09", "build_scores",           "microcap250"),
    ("STEP 10.10", "engine_v2_final",        "microcap250"),
    ("STEP 10.11", "audit_step",             "microcap250"),
    ("STEP 10.12", "make_chart",             "microcap250"),
    # THE THREE MARKET-CAP BUCKETS, ADDED 2026-10-16. Static only: the supplier
    # delivered no membership files for them (settings.py).
    ("STEP 10.13", "build_scores",           "mcap1500to5000"),
    ("STEP 10.14", "engine_v2_final",        "mcap1500to5000"),
    ("STEP 10.15", "audit_step",             "mcap1500to5000"),
    ("STEP 10.16", "make_chart",             "mcap1500to5000"),
    ("STEP 10.17", "build_scores",           "mcap5001to10000"),
    ("STEP 10.18", "engine_v2_final",        "mcap5001to10000"),
    ("STEP 10.19", "audit_step",             "mcap5001to10000"),
    ("STEP 10.20", "make_chart",             "mcap5001to10000"),
    ("STEP 10.21", "build_scores",           "mcapover10000"),
    ("STEP 10.22", "engine_v2_final",        "mcapover10000"),
    ("STEP 10.23", "audit_step",             "mcapover10000"),
    ("STEP 10.24", "make_chart",             "mcapover10000"),
    # MOVED FROM STEP 10i, and the move is load-bearing rather than cosmetic.
    # The combined chart is generic over the selection, so it needed per-trade
    # logs from two retired universes (deleted 2026-09-11), written by their
    # STEP 12, which ran after 10i. At 10i those logs did not exist, which is why
    # the old step could only ever combine midcap150 and nifty100. Its midcap150
    # and nifty100 inputs are written at 10c and 10g, so
    # they are still upstream; nothing consumes the chart, so nothing downstream
    # moved. Output verified byte-identical across the move.
    # FIELD 4: this step is generic over the registry -- it loops the selected
    # tags rather than naming any. Field 3 stays None: main() takes no universe.
    ("STEP 12b", "make_combined_universes", None, SPANS_REGISTRY),
    ("STEP 15", "make_daily_log",           None),
    # STEP 15b (save_caches_step.py) IS GONE, 2026-09-23, NOT RENUMBERED. It
    # copied the /tmp panels to results*/metrics/; there is one panel per
    # universe now, written by build_scores where STEP 16 reads it.
    ("STEP 16", "nt_export_scores",         None),
    # STEP 17 IS THE EXECUTION HALF OF THE NAUTILUS STORY. STEP 16 exports the
    # score parquet the port READS; nothing in the pipeline ever ran the port
    # itself, so a normal run produced Nautilus input and no Nautilus output.
    # It must follow 16, which writes the parquet it loads.
    ("STEP 17", "nt_execute",               None),
    # STEP 18 IS THE TAX HALF, AND IT IS TWO ROWS BECAUSE THE ARTEFACTS ARE
    # PER-UNIVERSE. FY_TAX_STATEMENT, FY_EQUITY, HOLDING_PERIOD and
    # HOLDING_PERIOD_LOTS each carry the tag in their name and hold one
    # universe's lots, so main() takes a universe (arity 1).
    #
    # NEW LABELS, NOT 10i. That label meant reports.py until it
    # moved to STEP 12b, and reusing it would make every log written before the
    # move ambiguous -- the same identity-over-compaction rule the 2026-09-11
    # retirement followed when it left STEPS 0-9 and 11-14 as gaps.
    #
    # AT THE END, BECAUSE THE ONLY INPUT IS THE SCORE PANEL, which build_scores
    # writes. Nothing consumes what this writes, so nothing downstream
    # constrains it either.
    #
    # THE ROWS ARE UNCONDITIONAL AND THE STEP RETURNS EARLY AT tax=off. The
    # plan is therefore IDENTICAL under --tax on and --tax off, which is what
    # lets the plan check reason about one order instead of two. See
    # reports.tax_report().
    # bh_lots_after_tax, ADDED 2026-09-19, AND IT IS A ROW RATHER THAN AN IMPORT
    # ON PURPOSE. STEP 18 composes TAX_TURNOVER from its own FY_EQUITY and this
    # step's BH_LOTS file, so the dependency is REAL; hiding it inside a
    # tax_report import would make it invisible to the plan check, which walks
    # the resolved plan and asks whether each declared input's writer comes
    # earlier in that same plan. It returns early at tax=off, like STEP 18.
    #
    # LABELS 17e-17h, unused before today, and NOT 18-anything: these run BEFORE
    # the 18 block, and a label that sorts after what it precedes is something a
    # reader has to re-derive every time.
    ("STEP 17e", "bh_lots_after_tax",      "midcap150"),
    ("STEP 17f", "bh_lots_after_tax",      "nifty100"),
    ("STEP 17g", "bh_lots_after_tax",      "nifty50"),
    ("STEP 17h", "bh_lots_after_tax",      "midcap50"),
    ("STEP 17i", "bh_lots_after_tax",      "midcap100"),
    ("STEP 17j", "bh_lots_after_tax",      "nifty200"),
    ("STEP 17.01", "bh_lots_after_tax",     "smallcap250"),
    ("STEP 17.02", "bh_lots_after_tax",     "nifty500"),
    ("STEP 17.03", "bh_lots_after_tax",     "microcap250"),
    ("STEP 17.04", "bh_lots_after_tax",     "mcap1500to5000"),
    ("STEP 17.05", "bh_lots_after_tax",     "mcap5001to10000"),
    ("STEP 17.06", "bh_lots_after_tax",     "mcapover10000"),
    ("STEP 18a", "tax_report",              "midcap150"),
    ("STEP 18b", "tax_report",              "nifty100"),
    ("STEP 18c", "tax_report",              "nifty50"),
    ("STEP 18d", "tax_report",              "midcap50"),
    ("STEP 18e", "tax_report",              "midcap100"),
    ("STEP 18f", "tax_report",              "nifty200"),
    ("STEP 18.01", "tax_report",            "smallcap250"),
    ("STEP 18.02", "tax_report",            "nifty500"),
    ("STEP 18.03", "tax_report",            "microcap250"),
    ("STEP 18.04", "tax_report",            "mcap1500to5000"),
    ("STEP 18.05", "tax_report",            "mcap5001to10000"),
    ("STEP 18.06", "tax_report",            "mcapover10000"),
]


# ---------------------------------------------------------------------------
# INPUT GUARD -- ordering bugs must fail by name, not as a pandas traceback
# ---------------------------------------------------------------------------
# Every entry is: consumer script -> [(file it reads, the step that writes it,
# the axis qualifier)].
#
# WHY THIS EXISTS. make_final_chart_fair.py read a retired universe's
# daily_trades file, which was produced two steps LATER. The pipeline appeared to work for months because the
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
# outlived the retired universes they served by five days and were deleted in
# 6d618ac.
#
# THE PATHS COME FROM settings.py, NOT FROM A FORMAT STRING WRITTEN HERE.
# settings.tagged_artefact(u, "daily_trades") is the existing definition of the
# daily-audit family's naming -- the one place that puts the tag in the FILENAME
# as well as the directory -- and re-spelling it here would be a second rule that
# can disagree with the first. Same for nautilus_scores() and score_cache().
#
# THE STEP LABEL IS LOOKED UP FROM PIPELINE_ORDER BY (script, universe), NEVER
# RESTATED. The third element of each tuple used to read "STEP 10c make_audit.py"
# for midcap150 and "STEP 10g make_audit.py" for nifty100 -- those are PIPELINE_ORDER
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
# their STEP_HELPERS, and backtest_runs.py is never among them. The claim was load-
# bearing for anyone deciding whether these could be computed -- it is why they
# were not -- so it is corrected rather than left.
def _step_label(script, tag):
    """The PIPELINE_ORDER label for one invocation: "STEP 10c audit_step".

    `tag` is the universe the producing invocation runs for, or None for a
    whole-run step. Raises rather than defaulting, because a producer that is not
    in PIPELINE_ORDER cannot be named in a guard that exists to say who owes a
    file.
    """
    for row in PIPELINE_ORDER:
        if row[1] == script and (row[2] if len(row) > 2 else None) == tag:
            return f"{row[0]} {script}"
    raise SystemExit(
        f"backtest_runs.REQUIRED_INPUTS: no PIPELINE_ORDER row runs {script} for "
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
#   `--rebal 200` on midcap150 v3 completed eight of nine steps and died at STEP 16
#   demanding v_mid_expanding_cache_r200.csv. The panel step had written
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
AXIS_FREE = ()                      # the name carries no run axis at all
# Every axis the writers put in a name, taken from settings.AXES. The arm is left
# out because it is part of the stem (daily_trades_v1_<tag> against
# daily_trades_<tag>), not of the tail.
#
# This was a hand-kept string, "cadence,profile,tax,survivorship", and it fell
# behind settings.AXES when dd, capital, impact, pcap and fixed were added. A v1 or
# v2 run with any of those five asked for the default cell's unsuffixed trade
# file, so on a fresh clone it stopped at STEP 10p, and where that file existed
# the check passed without looking at the file the run had written.
RUN_AXES = tuple(a for a in settings.AXES if a != "arm")


def _required_inputs():
    """The guard table, per registered universe. See the block above.

    EVERY ENTRY IS A 4-TUPLE and the fourth field is compulsory. A default would
    reproduce exactly the defect being closed: the whole failure was a rule applied
    uniformly to inputs that do not all carry the same axes, so "unspecified" must
    not be spellable.
    """
    import settings
    from settings import REGISTRY
    out = {"make_chart": [], "make_combined_universes": [],
           "nt_execute": [], "nt_export_scores": [], "tax_report": [],
           "bh_lots_after_tax": []}
    for u in REGISTRY.values():
        # ARM-TAGGED. daily_trades_<tag>.csv is v2's audit trail and a selection
        # without v2 writes no v2 trail at all; daily_trades_v1_<tag>.csv exists
        # only when v1 is selected. Demanding either unconditionally made
        # `--arm v1,v3` impossible from a cold tree, and it only ever passed
        # because an earlier default run had left the file on disk.
        out["make_chart"].append(
            (settings.tagged_artefact(u, "daily_trades"),
             _step_label("audit_step", u.tag), f"u:{u.tag},v2", RUN_AXES))
        out["make_chart"].append(
            (settings.tagged_artefact(u, "daily_trades_v1"),
             _step_label("engine_v2_final", u.tag), f"u:{u.tag},v1", RUN_AXES))
        # THE COMBINED STEP READS EVERY SELECTED UNIVERSE'S TRADE LOG. It is
        # qualified by ARM only: the universe is carried by the path, and this
        # step runs once for whatever the selection holds. That is why it moved
        # from STEP 10i to STEP 12b -- at 10i the logs did not exist yet.
        # THE UNIVERSE IS NAMED HERE TOO, AND IT WAS NOT. This entry carried "v2"
        # alone -- the arm, and nothing about whose file it is -- so it was demanded
        # whatever the selection was. `--universe nifty100` therefore required midcap150's
        # trade log, which that plan never writes, while the step itself reads only
        # selected_tags() (reports.py). Latent since step 6 and
        # invisible because midcap150's file was always on disk; found by
        # the plan check (check_pipeline_order.py --plan) on its first run.
        #
        # STEP 12b IS STILL A WHOLE-RUN STEP. Its invocation carries tag=None, so
        # entry_applies() resolves `u:` against the run's selection -- the correct
        # scope for a step invoked once. What changed is that the ENTRY now says
        # which universe's file it is, so it drops when that universe is not
        # selected instead of being demanded regardless.
        out["make_combined_universes"].append(
            (settings.tagged_artefact(u, "daily_trades"),
             _step_label("audit_step", u.tag), f"u:{u.tag},v2", RUN_AXES))
        # UNIVERSE-TAGGED. The port loads the parquet for each SELECTED universe,
        # and a run that selected one universe has one of these.
        out["nt_execute"].append(
            (settings.nautilus_scores(u),
             _step_label("nt_export_scores", None), f"u:{u.tag}", AXIS_FREE))
        # STEP 16 reads the score panel build_scores wrote. Named so that if the
        # two are ever re-ordered the run stops with the missing filename and the
        # step that owes it, instead of dying inside pandas.
        out["nt_export_scores"].append(
            (settings.score_cache(u),
             _step_label("build_scores", u.tag), f"u:{u.tag}", AXIS_FREE))
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
        # demand v_midcap150_expanding_tax.csv, which nothing writes.
        out["tax_report"].append(
            (settings.score_cache(u),
             _step_label("build_scores", u.tag), f"u:{u.tag}", AXIS_FREE))
    return out


REQUIRED_INPUTS = _required_inputs()

# DECLARE OR FAIL, CHECKED AT IMPORT. The table is derived, so this can only fire
# on an edit to _required_inputs() -- which is the point: the next person adding a
# consumer is stopped here rather than inheriting a silent default.
_undeclared = [(c, e[0].name) for c, lst in REQUIRED_INPUTS.items() for e in lst
               if len(e) < 4]
if _undeclared:
    raise SystemExit(
        "backtest_runs.REQUIRED_INPUTS: these entries do not declare which axes their "
        "name carries:\n"
        + "\n".join(f"    {c}  {n}" for c, n in _undeclared)
        + "\n  Add AXIS_FREE or RUN_AXES as the fourth field. There is no "
          "default, because the defect this closes was a rule applied uniformly to "
          "inputs that do not all carry the same axes.")
# Kept as the canonical set of pipeline script names. run()'s membership guard used
# it; run.py needs the same answer when it maps a step to its universe.
_PIPELINE_SCRIPTS = {row[1] for row in PIPELINE_ORDER}


def entry_applies(e, tag, usel, asel, label="", script=""):
    """Is this REQUIRED_INPUTS entry required by THIS INVOCATION?

    ONE DEFINITION, CALLED FROM TWO PLACES: check_inputs() below, which asks it at
    run time about files on disk, and check_pipeline_order.plan_analyse(), which asks it at plan
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
    nifty100", not "is this invocation nifty100". Both hold under `--universe all`, so
    STEP 10d (midcap150's chart) demanded nifty100's trade logs, which STEP 10f and 10g write
    afterwards. Unsatisfiable on a cold tree, and invisible on a warm one.

    THE LIST FORM ARRIVED WITH STEP 6. Before the collapse, a chart's inputs were
    keyed by a per-universe FILENAME -- make_mid_chart.py -- so the file identity
    supplied the universe and the third field only had to name the arm. One merged
    make_chart.py serves both universes from one key, so a `--universe midcap150` run
    would have been made to demand nifty100's trade logs. The universe is now written
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
    # backtest_runs.py are per-universe steps (main() arity 1) with no
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
    # imported by the plan check via runpy at module scope and must not pull an
    # axis module in at import time.
    from settings import tax as _tax

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
            # UNIVERSES IN ONE RUN -- merged reports.py is STEP 10d for midcap150
            # and STEP 10h for nifty100 -- so "did this RUN select nifty100" and "is
            # this INVOCATION nifty100" are different questions and the plan built from the
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
            # would be false (see the reports.py entry in _required_inputs).
            #
            # THE SHAPE THAT WOULD USE IT is a CONSUMER of a tax artefact:
            #
            #     out["some_tax_chart.py"].append(
            #         (M / "FY_TAX_STATEMENT_<tag>_tax.csv",
            #          _step_label("tax_report", u.tag),
            #          f"u:{u.tag},tax:on", settings.AXES))
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
            # universe (reports.py; likewise STEP 12b, 16, 17). Such a
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
    required only when the arm is selected: daily_trades_v1_midcap150.csv is not
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
    import portfolio as _ar
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
        daily_trades_midcap150_r40.csv and leave the cadence-20 file alone. The guard
        therefore asks for the name THIS RUN'S AXES PRODUCE, built the same way the
        producers build it, rather than for the canonical name with a fallback.
        """
        # ONLY THE AXES THIS INPUT'S NAME ACTUALLY CARRIES. This used to compose
        # both suffixes onto every input, which is how a correct refusal came to
        # be raised against a file that does not and should not exist: the score
        # panel is invariant to both axes, so there is no _r200 or _tradeable copy
        # of it for build_scores to have written. Measured; see the block above
        # _required_inputs(). An input that DOES carry an axis is unchanged, and
        # the substitution refusal below is unchanged with it.
        #
        # settings.tail composes the suffixes the writers use, in their order, so
        # the check cannot list a different set of axes from the writers.
        _sfx = settings.tail(axes)
        want = f if not _sfx else f.with_name(f.stem + _sfx + f.suffix)
        if want.exists():
            return True
        from settings import list_dir
        _found.append((f, want, [
            q.name for q in list_dir(want.parent, f.stem + "*" + f.suffix)][:6]))
        return False

    import settings
    _usel = set(settings.universe_axis.selected_tags())

    def _wanted(e):
        """This invocation's view of one entry. See entry_applies() above -- ONE
        definition, shared with check_pipeline_order.plan_analyse()."""
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
    print("  listed AFTER this one in backtest_runs.PIPELINE_ORDER, the order is wrong and the step")
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


# ======================================================================================
# STEP: BUILD THE SCORE PANEL. From results/build_scores.py (moved 2026-11-27).
# ======================================================================================
# build_scores.py -- one universe's raw panel and monthly scores
#
# THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
# build_scores_mid.py and build_scores_n100.py, which differed in nothing but the
# registry key they passed and the filenames their docstrings quoted. Step 3 of the
# collapse; the contract that made it possible is 5c636cf.
#
# The body lives once in model.py, which took over from the four
# copies the two merged files used to be among; every difference between those was a
# universe property settings.py records. See that module for the mapping,
# and for why purge_mode is read from the registry rather than written here.
#
# The index is excluded by pointing build_panel at a constituents-only directory,
# which u.prepare_data_dir() rebuilds; the panel's symbol set is then asserted
# against the registry's list.
#
# Output caches: u.raw_cache and u.score_cache -- cache/<tag>/raw_panel_<tag>_20.parquet
# and cache/<tag>/v_<tag>_expanding.parquet, each with a .source sidecar holding the
# source key and the code key. NO FILENAME IS WRITTEN HERE; they are registry attributes, which is
# why adding a universe costs no edit to this file.
#
# INVOKED TWICE PER FULL RUN, once per universe, from two PIPELINE_ORDER rows that
# keep their own labels -- STEP 10a for midcap150, STEP 10e for nifty100. The labels are not
# renumbered by the merge: a step's name means what it meant in every log written
# before it, the same rule the 2026-09-11 retirement set when it left STEPS 0-9 and
# 11-14 as gaps.

def build_scores(u):
    """The step, as a function, so run.py can call it in process.

    NO TRANSITIONAL ASSERT AND NO REGISTRY SUBSCRIPT. It takes the universe and
    uses it, which is what steps 3-7 exist to produce and what
    transitional_asserts_check.py is watching for.
    """
    model.run(u)


# ======================================================================================
# STEP: THE ENGINE RUN PER UNIVERSE (v1, v2, buy-and-hold). From results/engine_v2_final.py (moved 2026-11-27).
# ======================================================================================
# engine_v2_final.py -- FINAL v2 STRATEGY (breadth-scaled), for one universe
#
# THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
# engine_v2_final_mid.py and engine_v2_final_n100.py. Step 5 of the collapse, and
# the largest of the eight: unlike the step 3 and step 4 pairs, which differed only
# in the tag, these two had diverged in 95 lines of code after universe names were
# normalised, and some of that divergence REACHED PUBLISHED ARTEFACTS.
#
# EVERYTHING THAT DIVERGED IS NOW REGISTRY DATA, NOT CODE. settings.py
# carries, per universe: validation_status, engine_params_keys (the exact ordered
# key list for v2FINAL_params.json), engine_params_static, and engine_text (the
# panel description, the buy&hold label, and whether the index-absent assertion
# applies). The banner, chart title, verdict and selectivity note are built from
# the label and the run since 2026-09-30. The merge is therefore artefact-neutral by construction, and
# the gate proves it rather than the author asserting it.
#
# NOTHING HERE IS UNIFIED. midcap150's params carry "validated" and "rejected" and no
# "universe"/"n_symbols"; nifty100's carry the opposite. midcap150's chart title is two lines
# and nifty100's is one. Neither set is more correct -- they are what the two engines
# happened to write -- and changing either is a judgement about a published
# artefact, which belongs in its own commit where a moved byte has one possible
# cause.
#
# validation_status IS DELIBERATELY ASYMMETRIC. midcap150's dict of eight measured
# results and nifty100's sentence saying the work was not done here are a record of
# which universe got the validation, not drift. Type tells them apart.
#
# Same strategy, same features, same hyperparameters for every universe; only the
# universe differs.

warnings.filterwarnings("ignore")
# SURVIVORSHIP REPORTING, BACK-PORTED FROM engine_v2_final_n100.py 2026-09-13.
# midcap150 has run under the SAME static-membership bias as nifty100 since it existed --
# 148 of TODAY'S index members backfilled to 2019 -- and said nothing about it in
# any output it wrote. nifty100's engine has reported it all along. The bias was never
# universe-specific; only the disclosure was.

REBAL, VOL_WIN = 20, 60
# REBAL ABOVE IS THE DEFAULT AND STAYS 20. The cadence this RUN selected is read
# from cadence.selected() at call time and passed to backtest_exposure as an
# argument; the module constant is never reassigned, because a reassigned global
# leaks into the next step (module_state.py names the case).
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = settings.TOP_N, settings.BUFFER
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
# BACKTEST WINDOW -- imported from config.py, the single definition.
# Date-based and inclusive. The old year cut (BT_START, BT_END = 2019, 2026)
# ran to 2026-06-08, six trading days beyond this window.


# THE PATHS THIS RUN COMPOSED, IN THE ORDER IT WROTE THEM. Filled by _c() and read
# only by the two report lines at the end of main(). A list rather than a set so
# the order the reader sees is the order the files appeared on disk, and DEDUPED
# at the point of reporting rather than here.
#
# WHY A PATH APPEARS TWICE. daily_trades_v1_<tag>.csv is composed twice -- once in
# the to_csv call and once in the print that names it -- because the literal has
# to stay inside the write call for check_pipeline_order to resolve the edge, so
# the print cannot reuse a local. That is ONE file written once. Reporting it
# twice is the same defect this list exists to close, one turn smaller, and the
# `--arm all` gate run is what showed it: "v2FINAL_equity.csv,
# daily_trades_v1_mid.csv, daily_trades_v1_mid.csv, v2FINAL_params.json".
_WROTE = []


def _c(path):
    """This run's name for an output whose content depends on the cadence.

    THE LITERAL STAYS IN THE CALL. Writers are spelled `_c(M / "<name>.csv")`
    rather than routed through a precomputed variable, because check_pipeline_order
    reads the `M / "<literal>"` shape out of the source to resolve this step's
    edges -- and a computed name made three of them vanish once already.

    At the default cadence this returns the path unchanged, so every published
    filename is exactly what it has always been. A non-default cadence gets
    v2FINAL_equity_r40.csv beside it and never replaces the published file.
    
    THE PROFILE IS PART OF THIS NAME. `tradeable` caps fills at the symbol's
    prior-20-session median volume, which changes every number this step writes.
    Until 2026-09-12 only audit_step.py and v34_common.py consulted the profile,
    so the pipeline half wrote CAPPED numbers into the CANONICAL filenames -- the
    same defect the cadence suffix was introduced to fix, on a third axis, and
    silent rather than fatal. See KNOWN_ISSUES.md.
    """
    import settings
    from settings import tax as _tax
    # THE TAX AXIS IS PART OF THIS NAME TOO (2026-09-17). tax=on deducts a
    # lump sum from cash on a payment date, which changes the cash path, the
    # integer share counts sized from it and therefore every number this step
    # writes -- exactly the way `tradeable` does. Writing those into the
    # canonical filenames would be the same defect on a fourth axis.
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    _all_default = (cadence.is_default() and settings.profile_axis.is_default() and _tax.is_default()
                    and _sva.is_default() and _dda.is_default()
            and _capa.is_default() and _impa.is_default() and _pca.is_default() and _fxa.is_default() and _sta.is_default() and settings.shortfall_axis.is_default())
    _sfx = ("" if _all_default
            else (cadence.suffix() + settings.profile_axis.suffix() + _tax.suffix() + _sva.suffix()
                  + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix()))
    out = path if not _sfx else path.with_name(path.stem + _sfx + path.suffix)
    # WHAT THIS RUN ACTUALLY WROTE, RECORDED HERE BECAUSE HERE IS WHERE THE NAME
    # IS DECIDED. The step used to end by printing a hardcoded list of the
    # CANONICAL names -- "Saved -> v2FINAL_equity.csv, chart_v2FINAL.png" -- which
    # under `--rebal 200` named five gated files it had not touched and did not
    # name the five it had. A reader went looking for an overwrite that had not
    # happened. A report that misnames its own output is the same class as a check
    # that misdescribes what it checked, so the report is now derived from the
    # composer instead of restating it.
    #
    # RECORDED AT COMPOSE TIME, NOT AFTER THE WRITE, and that is sound here: every
    # caller is `<writer>(_c(...))`, and the summary line is only reached if all of
    # them returned. A write that raises kills the step before anything is printed.
    _WROTE.append(out)
    return out


def engine_v2_final(u):
    # EVERY PER-UNIVERSE VALUE COMES FROM THE REGISTRY, none from this file.
    # `tag` is spelled as a plain local and used in f-strings as "{tag}" because
    # check_pipeline_order substitutes THAT placeholder and no other: an f-string
    # written "{u.tag}" is not a word-character placeholder and every path built
    # from it would fall into unresolved, taking this step's producer edges with it.
    tag = u.tag
    M = Path(u.metrics_dir)
    _T = u.engine_text
    # ONE UNIVERSE'S WRITES PER CALL. run.py calls main() once per universe in one
    # process, and module_state restores globals a step reassigns, not a list it
    # appends to. So nifty100's "Saved ->" line listed midcap150's
    # daily_trades_v1_midcap150.csv, written by the call before it.
    _WROTE.clear()
    # ONE BANNER, FROM THE LABEL. It was registry text followed by this fixed
    # line, so midcap150, whose registry banner was the fixed line, printed it
    # twice.
    print("=" * 100)
    print(f"ENGINE v2 FINAL -- {u.label}: cross-sectional ranking + inverse-vol + "
          f"breadth scaling")
    print("=" * 100)
    print(f"  SURVIVORSHIP: {market_data.describe_state()}")

    # UNLISTED FIX 2026-08-28: this read /tmp/v_midcap150_expanding.csv directly and
    # raised FileNotFoundError whenever /tmp had been cleared. nifty100's engine has
    # always used model.require_cache with the permanent copy as the fallback;
    # this now matches it. Pre-existing bug, not introduced by the V34 work.
    # Guard loaded per universe -- see market_data.set_tradeability.
    market_data.set_tradeability(u)
    src = model.require_cache(u.score_cache, what=_T["panel_what"])
    p = read_table(src, parse_dates=["date"])
    # THE INDEX MUST NOT BE IN THE PANEL AS A TRADABLE NAME, where the universe
    # declares that check. nifty100's engine has always asserted it; midcap150's never did.
    # Preserved as declared per-universe data rather than switched on for both --
    # turning it on for midcap150 is a behaviour change and belongs in its own commit.
    if _T.get("assert_index_absent") and u.index_name:
        assert u.index_name not in set(p["symbol"].unique()), \
            "the index is in the score panel as a tradable name"
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    # THE UNIVERSE'S WINDOW: settings.BT_START_DATE..BT_END_DATE for every static row;
    # a pit row starts at its first membership row when that is later.
    bd = u.trading_days(px.index)
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1

    # baseline (inv-vol, always invested) and final (breadth-scaled)
    # The baseline's per-trade log is captured and persisted below. v1 rebalances
    # every 20 days and pays real costs -- more than v2 does, because it is always
    # 100% invested and so trades in larger size -- but only its TOTALS used to
    # survive, in v2FINAL_comparison.csv. A total cannot support a per-date
    # analysis, which left make_final_chart_fair.py treating v1 as costless.
    # `audit` only appends to lists; it changes no arithmetic, and the equity
    # curve is asserted identical to the un-audited baseline below.
    base_audit = {k: [] for k in
                  ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    # THE RUN'S CADENCE, PASSED AS AN ARGUMENT. `_reb` is 20 by default, which is
    # what REBAL already was, and `_rebal = REBAL if rebal is None else int(rebal)`
    # resolves both to the same 20 -- so the default path is byte-identical.
    _reb = cadence.selected()
    # THE TAX SELECTION, READ ONCE AND PASSED AS AN ARGUMENT -- exactly as _reb
    # above and participation_cap below. backtest_exposure's tax_enabled is a
    # PARAMETER by design (portfolio.py gives the reason: same as rebal
    # and participation_cap), so it stays one; what was missing was any caller on
    # the PUBLISHED path passing it.
    #
    # UNTIL 2026-09-18 NO SUCH CALLER EXISTED. tax_enabled defaulted to False at
    # every one of the 31 call sites except reports.py's and
    # backtest_runs.py's, so `--tax on` moved filenames and nothing else: 36
    # of 40 suffixed artefacts were BYTE-IDENTICAL to their untaxed twins and the
    # other 4 differed only in a header label. The axis renamed; it did not charge.
    from settings import tax as _tax_axis
    _taxon = _tax_axis.selected()
    # THE PROFILE'S CAP, RESOLVED ONCE AND PASSED AS AN ARGUMENT.
    # costs.py records why this is not a global on test_exposure: settings.cadence
    # documents rebal_cadence_sweep.py setting test_exposure.REBAL and never
    # restoring it, so every later in-process step silently used the wrong cadence.
    # None under profile="research", so `q` is untouched and the published history
    # is exact.
    import costs
    import settings
    _capkw = costs.cap_kwargs(u)
    base_eq, tcb, nb, base_expo = backtest_exposure(px, op, sc, bd, pc, mom20, mode="none", drawdown_stop=None,
                                                    audit=base_audit, rebal=_reb,
                                                    tax_enabled=_taxon, **_capkw)
    fin_eq, tcf, nf, expo = backtest_exposure(px, op, sc, bd, pc, mom20, mode="breadth", drawdown_stop=None,
                                              rebal=_reb, tax_enabled=_taxon,
                                              **_capkw)
    # THE BUY & HOLD BASKET: every name in static mode; in pit mode the members on
    # the first pit rebalance, bd[0] (owner's decision, 2026-10-10).
    bh = _capital_axis.selected() * (1 + market_data.buyhold_prices(px, bd[0], market_data.MEMBERSHIP)
                          .pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    mbase = metrics(base_eq, "Inverse-vol, 100% invested (v1 final)", tcb, nb)
    mfin = metrics(fin_eq, "+ breadth scaling (v2 FINAL)", tcf, nf)
    mbh = metrics(bh, _T["bh_label"])

    out = pd.DataFrame([mfin, mbase, mbh])
    print("\n" + out.to_string(index=False))
    print(f"\n   v2 FINAL average exposure: {expo*100:.0f}% invested "
          f"(rest in cash at {CASH_YIELD*100:g}% yield)")
    out.to_csv(_c(M / "v2FINAL_comparison.csv"), index=False)

    # yearly
    yr = pd.DataFrame({
        "Strategy%": (fin_eq.resample("YE").last().pct_change().dropna()*100).round(1),
        "BuyHold%": (bh.resample("YE").last().pct_change().dropna()*100).round(1)})
    yr.index = yr.index.year
    yr["Diff"] = (yr["Strategy%"] - yr["BuyHold%"]).round(1)
    print("\n--- YEAR BY YEAR ---")
    print(yr.to_string())
    yr.to_csv(_c(M / "v2FINAL_yearly.csv"))

    # PER-ARM COLUMNS ALONGSIDE THE ORIGINAL TWO.
    # `strategy` is v2 and `baseline_invvol` is v1 -- names that say what the
    # curve was FOR rather than which arm it IS, which is why nothing downstream
    # could ask this file for v3 or v4. The arm-keyed names are
    # arms/registry.Arm.equity_column, the same spelling v34_equity.csv already
    # uses, so the project ends up with ONE name per arm instead of two.
    #
    # THE OLD NAMES ARE GONE FROM THE LIVE UNIVERSES. They were kept as duplicates
    # while the nine readers were repointed one at a time, each byte-compared; that
    # is finished, and every reader now goes through arms/registry.equity_series.
    #
    # THE RETIRED UNIVERSES' FILES CARRY `strategy`/`baseline_invvol` AND ALWAYS
    # WILL. They are those universes' provenance and are not modified, so
    # equity_series' fallback is permanent rather than transitional -- it is how a
    # frozen universe's file is read, not a shim awaiting deletion.
    pd.DataFrame({"date": fin_eq.index,
                  "v1_invvol_none": base_eq.values,
                  "v2_invvol_breadth": fin_eq.values,
                  "buyhold": bh.values}).to_csv(_c(M / "v2FINAL_equity.csv"), index=False)

    # v1 baseline's per-trade log, written the same way daily_trades_<tag>.csv is.
    # Consumers (make_final_chart_fair.py) read the costs from the engine that
    # produced the equity curve, rather than re-running the baseline to recover
    # them. The count is asserted against what the engine itself reported.
    bt = pd.DataFrame(base_audit["trades"])
    # Only a trimmed buy has wanted_qty; written as a whole number, blank elsewhere.
    if "wanted_qty" in bt.columns:
        bt["wanted_qty"] = bt["wanted_qty"].astype("Int64")
    assert len(bt) == nb, f"v1 trade log {len(bt)} rows vs engine count {nb}"
    # WRITTEN UNCONDITIONALLY, AND THAT IS A KNOWN LEAK, RECORDED NOT HIDDEN.
    # `--arm v2` still produces daily_trades_v1_<tag>.csv -- a file named for an
    # arm the run did not select. Gating it was TRIED and reverted: STEP 10d
    # make_mid_chart.py declares this file in backtest_runs.REQUIRED_INPUTS as a hard
    # edge, so a gated write makes `--arm v2` die at check_inputs with a missing
    # file. Removing that edge would weaken the static contract and cost the
    # checker a resolved dependency, which experiments/ARM_SUBSET_SPEC.txt's G6
    # forbids. Closing this properly means making make_mid_chart.py arm-aware
    # too; see KNOWN_ISSUES.md.
    # GATED ON v1 BEING SELECTED. `--arm v2` no longer produces a file named for
    # an arm the run did not select.
    #
    # THIS ONLY BECAME POSSIBLE ONCE make_mid_chart.py WENT ARM-AWARE. The first
    # attempt gated the write while STEP 10d still demanded the file
    # unconditionally through backtest_runs.REQUIRED_INPUTS, so `--arm v2` died at
    # check_inputs. That edge now carries the arm it belongs to and is skipped
    # when v1 is not selected -- the requirement became conditional while the
    # literal path stayed put, so the static inventory did not move.
    # THE PRINT IS INSIDE THE CONDITION NOW. It used to sit outside it and name
    # the file unconditionally, so `--arm v3` logged
    #     "v1 baseline trade log: 852 trades, TC Rs 839,393 -> daily_trades_v1_mid.csv"
    # and wrote no such file. Two concrete numbers and a filename, all three read
    # as a completed write, for an arm the run did not select. That is an
    # assertion of completion the step never verified, and the file it names is
    # the one make_mid_chart then fails on.
    #
    # THE COUNTS ARE STILL REPORTED when the write is skipped, because they are a
    # real measurement of the baseline arm -- only the claim about the file is
    # conditional. And the printed name is the COMPOSED one, so a non-default
    # cadence or profile logs the filename it actually wrote rather than the
    # canonical spelling.
    if "v1" in set(arm_reg.selected_names()):
        bt.to_csv(_c(M / f"daily_trades_v1_{tag}.csv"), index=False)
        print(f"   v1 baseline trade log: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
              f"-> {_c(M / f'daily_trades_v1_{tag}.csv').name}")
    else:
        print(f"   v1 baseline: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
              f"-- trade log NOT WRITTEN, v1 is not in this run's arm selection")

    # THE KEY SET AND KEY ORDER ARE PER-UNIVERSE DATA, and json.dumps preserves
    # insertion order, so this loop is what keeps v2FINAL_params.json byte-identical
    # across the merge. midcap150 writes no "universe" and no "n_symbols"; nifty100 writes
    # both and writes no "validated"/"rejected". Neither set is more correct --
    # they are what the two engines happened to write. Unifying them would move a
    # published artefact, which is a judgement and belongs in its own commit.
    _vals = {
        "model": "cross-sectional LightGBM, 17 feats, 10-seed, monthly, 32d purge",
        "sizing": "inverse-volatility (1/vol60)",
        "exposure": "breadth scaling = fraction of positive-20d-momentum stocks",
        # THE CADENCE THIS RUN ACTUALLY USED, not the module default. Writing
        # REBAL here produced v2FINAL_params_r40.json saying rebalance_days: 20 --
        # a file named for one cadence whose contents claimed another, which is
        # the worst of the two possible errors because the name looks right.
        "top_n": TOP_N, "buffer": BUFFER, "rebalance_days": _reb,
        "avg_exposure_pct": round(expo*100),
        "n_symbols": int(p["symbol"].nunique()),
        "sharpe": mfin["Sharpe"], "maxdd_pct": mfin["MaxDD%"], "cagr_pct": mfin["CAGR%"],
        "cash_yield": CASH_YIELD,
        # STATED IN THE ARTEFACT, not only on the chart, so a reader of
        # v2FINAL_params.json alone knows which membership basis produced it.
        # In a pit run, the whole pit record: verdict, residual survivorship and
        # the look-ahead note. The static value is unchanged.
        "survivorship": (market_data.params_fields(u.tag)["survivorship"] if market_data.is_pit()
                         else market_data.describe_state()),
        # THE DRAWDOWN-LIMIT AXIS: present only with --dd, so this file is
        # unchanged without it.
        **({} if dd_axis.is_default() else {"dd": dd_axis.params()}),
        **({} if _capital_axis.is_default() else {"capital": _capital_axis.selected()}),
        **({} if impact_axis.is_default() else {"impact_k": impact_axis.selected()}),
        **({} if pcap_axis.is_default() else {"participation_cap": pcap_axis.selected()}),
        "vs_buyhold": (f"Sharpe {mfin['Sharpe']} vs {mbh['Sharpe']}, "
                       f"MaxDD {mfin['MaxDD%']}% vs {mbh['MaxDD%']}%, "
                       f"CAGR {mfin['CAGR%']}% vs {mbh['CAGR%']}%"),
        # A DICT MEANS MEASURED, A STRING MEANS NOT MEASURED ON THIS UNIVERSE.
        # The asymmetry is the record of which universe got the validation work;
        # see settings.py, where it is kept deliberately un-flattened.
        "validation_status": u.validation_status,
    }
    _vals.update(u.engine_params_static or {})
    (_c(M / "v2FINAL_params.json")).write_text(json.dumps(
        {k: _vals[k] for k in u.engine_params_keys}, indent=2))

    # chart
    fig, ax = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[2, 1])
    for s, c, ls, lab in [
            (fin_eq, "#d62728", "-", f"v2 FINAL: + breadth scaling  "
                                     f"(CAGR {mfin['CAGR%']}%, Sharpe {mfin['Sharpe']}, "
                                     f"MaxDD {mfin['MaxDD%']}%)"),
            (base_eq, "#1f77b4", "-", f"v1: inverse-vol, always invested  "
                                      f"(CAGR {mbase['CAGR%']}%, Sharpe {mbase['Sharpe']}, "
                                      f"MaxDD {mbase['MaxDD%']}%)"),
            (bh, "#2ca02c", "--", f"Equal-weight buy & hold  "
                                  f"(CAGR {mbh['CAGR%']}%, Sharpe {mbh['Sharpe']}, "
                                  f"MaxDD {mbh['MaxDD%']}%)")]:
        ax[0].plot(s.index, (s/s.iloc[0]-1)*100, lw=2.2, color=c, ls=ls, alpha=.9, label=lab)
    ax[0].axhline(0, color="k", lw=.7, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    # ONE TITLE FOR EVERY UNIVERSE, since 2026-09-30. It was registry text, and
    # midcap150's carried a fixed performance claim ("~half the drawdown,
    # higher Sharpe") that no longer matched its own numbers.
    ax[0].set_title(settings.run_label(u.label, ["v1", "v2"]) + "\n"
                    + f"{u.label} -- ranking + inverse-vol + breadth-scaled exposure\n"
                    + market_data.describe_state(), fontsize=10)
    ax[0].legend(loc="upper left", fontsize=9)
    ax[0].grid(alpha=.3)
    for s, c, ls, lab in [(fin_eq, "#d62728", "-", "v2 FINAL"),
                          (bh, "#2ca02c", "--", "Buy & hold")]:
        dd = (s/s.cummax()-1)*100
        ax[1].fill_between(s.index, dd, 0, color=c, alpha=.22)
        ax[1].plot(s.index, dd, lw=1.5, color=c, ls=ls, label=f"{lab} (max {dd.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=9)
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(_c(M / "chart_v2FINAL.png"), dpi=150, bbox_inches="tight", metadata={"Title": ax[0].get_title().split("\n")[0]})
    print(f"\n  saved -> {_WROTE[-1].name}")

    # ------------------------------------------------------------------ V3/V4
    # Four-arm pro-vol measurement, per experiments/V34_SPEC.txt. v1 and v2 above
    # are passed in rather than recomputed, so the arms in v34_comparison.csv are
    # the same curves that wrote v2FINAL_equity.csv. Same process, same panel,
    # same dates, same seeds -- which is what the spec requires.
    # Nothing above this line is altered; v2FINAL_* keeps its names and columns.
    _arm_audits = {}
    v34_comp, v34_subs, _ = run_v34(
        M, u.label, tag, px, op, sc, bd, pc, mom20,
        backtest_exposure,
        base_eq, tcb, nb, fin_eq, tcf, nf, expo,
        _capital_axis.selected(),
        [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)],
        {"TOP_N": TOP_N, "BUFFER": BUFFER, "REBAL": REBAL, "VOL_WIN": VOL_WIN,
         "START_CAPITAL": _capital_axis.selected(), "CASH_YIELD": CASH_YIELD,
         "SLIPPAGE": 0.0015},
        v1_audit=base_audit, audits_out=_arm_audits, v1_expo=base_expo)
    print("\n" + "=" * 100)
    print(f" V3/V4 FOUR-ARM MEASUREMENT -- {u.label}")
    print("=" * 100)
    print("\n FULL PERIOD")
    print(v34_comp.to_string(index=False))
    print("\n SUB-PERIODS")
    print(v34_subs.to_string(index=False))
    # NO "saved ->" LINE FOR THE v34 FAMILY HERE. Those five files are written by
    # backtest_runs.run_v34, which composes their names over THREE axes -- arm,
    # cadence and profile -- none of which this step can see from the literals it
    # used to print. run_v34 reports its own writes; a step reporting another
    # step's output was how the wrong five names came to be printed.

    # THE VERDICT AND THE SELECTIVITY NOTE ARE COMPUTED FROM THIS RUN. Until
    # 2026-09-30 both carried fixed text: "no capital gains tax is modelled" on
    # every run, tax on included; nifty100's before- and after-tax edge (+0.46,
    # -1.59) in every universe's verdict; and a TOP_N comparison against two
    # retired universes of 58 and 74 names. Every figure below now comes from
    # this universe, cadence, profile and tax setting, or from the registry.
    #
    # THE VERDICT COVERS THE ARMS THE RUN SELECTED. It reported v2 on every run,
    # because this step always computes v1 and v2, so `--arm v1,v3` printed a v2
    # verdict. Each selected arm's row is in v34_comp, which run_v34 built from
    # the same curves this step published, and its audit holds the tax it paid.
    _sel = arm_reg.selected()
    _rows = v34_comp.set_index("Config")
    _bhm = _rows.loc["buy & hold equal-weight"]
    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    print(f"  {u.label}: {', '.join(a.name for a in _sel)} against the equal-weight buy & hold, "
          f"cadence {_reb}, profile {settings.profile_axis.selected()}, tax {'on' if _taxon else 'off'}")

    def _line(name, m):
        print(f"  {name:<11}: CAGR {m['CAGR%']:>6.2f}%  Sharpe {m['Sharpe']:>5.2f}  "
              f"MaxDD {m['MaxDD%']:>7.2f}%  Calmar {m['Calmar']:.2f}")
    for a in _sel:
        _line(a.name, _rows.loc[a.label])
    _line("Buy & hold", _bhm)
    print("\n  Versus equal-weight buy & hold over the same period:")
    for a in _sel:
        m = _rows.loc[a.label]
        d_sh = m["Sharpe"] - _bhm["Sharpe"]
        print(f"    {a.name:<4} Sharpe {m['Sharpe']:>7.2f} vs {_bhm['Sharpe']:>6.2f}   ({d_sh:+.2f})  -- "
              f"{'ahead of' if d_sh > 0 else 'behind'} buy & hold")
        print(f"    {'':<4} MaxDD  {m['MaxDD%']:>7.2f}% vs {_bhm['MaxDD%']:>6.2f}%   "
              f"({m['MaxDD%'] - _bhm['MaxDD%']:+.2f} pts)")
        print(f"    {'':<4} CAGR   {m['CAGR%']:>7.2f}% vs {_bhm['CAGR%']:>6.2f}%   "
              f"({m['CAGR%'] - _bhm['CAGR%']:+.2f} pts)")
    _dep = [(a.name, float(_rows.loc[a.label, "Deployed%"])) for a in _sel]
    print(f"\n  Average invested: {', '.join(f'{n} {d:.0f}%' for n, d in _dep)}.")
    if any(d < 100 for _, d in _dep):
        print("  Where an arm holds cash, raw CAGR is not the right comparison on its own --\n"
              "  return per deployed rupee and drawdown are.")
    print(f"  Idle cash earns {CASH_YIELD*100:g}%, so none of the return above comes from interest.")
    # THE STOP ARMS' EXITS AND RE-ENTRIES, from the audit of the run above.
    for a in [x for x in _sel if x.stop is not None]:
        _ev = pd.DataFrame(_arm_audits[a.name].get("stop_events", []))
        _st = a.kwargs["drawdown_stop"]
        print(f"\n  {a.name} drawdown stop (parent {a.parent}): exit at "
              f"{_st.threshold:.0%} below the running peak, cooldown "
              f"{_st.cooldown_cycles} cycle(s), re-entry at breadth >= "
              f"{_st.reentry_breadth:.2f}"
              + ("  [TEST FIXTURE THRESHOLD, NOT A RESULT]"
                 if arm_reg.fixture_threshold() is not None else ""))
        if _ev.empty:
            print("    no exit")
            continue
        _key = _ev[_ev["event"].isin(["trigger", "flat", "re-entry order",
                                      "re-entry filled", "trigger on the last session"])]
        print(f"    exits {int((_ev['event'] == 'trigger').sum())}, re-entries "
              f"{int((_ev['event'] == 're-entry filled').sum())}")
        print(f"    {'date':<11} {'event':<28} {'peak':>14} {'equity':>14} {'drawdown':>9} "
              f"{'breadth':>8}")
        for _, r in _key.iterrows():
            _dd = "" if pd.isna(r["drawdown_pct"]) else f"{r['drawdown_pct']:+.2f}%"
            _br = "" if pd.isna(r["breadth"]) else f"{r['breadth']:.4f}"
            print(f"    {str(pd.Timestamp(r['date']).date()):<11} {r['event']:<28} "
                  f"{r['peak']:>14,.2f} {r['equity']:>14,.2f} {_dd:>9} {_br:>8}")
    if _taxon:
        _paid = [f"{a.name} Rs {_arm_audits[a.name]['tax']['cum_tax']:,.2f}" for a in _sel]
        # THE LAST-DAY FIGURE IS backtest_runs.held_lots', the one COST_SUMMARY and
        # BH_LOTS report for the buy & hold sold on the last day.
        _bh_tax = held_lots(px, op, bd)["detail"]["tax"]
        print(f"  Capital-gains tax was charged in this run and every figure above is after it.\n"
              f"  Tax paid: {', '.join(_paid)}.\n"
              f"  The buy & hold never sells, so it pays none. Sold on the last day, the investable\n"
              f"  buy & hold (whole shares of every name bought at the first open) would pay\n"
              f"  Rs {_bh_tax:,.2f}.")
    else:
        print("  Tax was not charged in this run (tax off): every figure above is before "
              "capital-gains\n  tax. --tax on charges it.")
    print(f"""
  Standing caveat: the universe is today's {len(u.symbol_list)} index members backfilled to
  {settings.BT_START_DATE.date()}, so every line above carries survivorship bias of unknown sign. See
  diagnostics/survivorship_attribution.txt for what has been estimated.
""")

    from settings import REGISTRY as _REG
    n_names = len(u.symbol_list)
    print("=" * 100)
    print("SELECTIVITY -- AN OBSERVATION, NOT A CHANGE")
    print("=" * 100)
    print(f"\n  TOP_N is {TOP_N} for every universe. The share of each registered "
          f"universe that it buys:\n")
    # A UNIVERSE WITH NO PRICE FILES ON DISK HAS NO NAMES, so it is listed last
    # and said so. A data folder copied for some universes only divided by zero
    # here and failed the step.
    for _v in sorted(_REG.values(), key=lambda v: (not v.symbol_list, len(v.symbol_list), v.tag)):
        _n = len(_v.symbol_list)
        if not _n:
            print(f"    {_v.tag:<12}    - names  -> no price data on disk")
            continue
        print(f"    {_v.tag:<12} {_n:>4} names  -> top {TOP_N/_n*100:>4.1f}%"
              + ("   <- this run" if _v.tag == tag else ""))
    print(f"""
  Under the Fundamental Law, IR is roughly IC x sqrt(breadth). Holding {n_names}
  candidates and buying {TOP_N} of them uses {TOP_N/n_names*100:.1f}% of this universe's names; the
  larger the universe, the smaller that share.
  This run does NOT act on that: TOP_N is fixed across universes, and changing it
  is a separate pre-registered experiment. Choosing it after seeing these numbers
  would be fitting the parameter to the result.
""")
    # WHAT WAS WRITTEN, NOT WHAT IS USUALLY WRITTEN. Under the default axes this
    # prints exactly the five names it always did, plus daily_trades_v1_<tag>.csv
    # when v1 is selected -- which this step writes and the old line never
    # mentioned. Under `--rebal 200` it prints the _r200 names, which are the files
    # that exist.
    print("Saved -> " + ", ".join(dict.fromkeys(q.name for q in _WROTE)))


# ======================================================================================
# THE ARM RUNNER: run_arm, run_v34 AND THE v34 WRITERS. From results/v34_common.py (moved 2026-11-27).
# ======================================================================================
# v34_common.py -- the four-arm pro-vol measurement, shared by both live engines.
#
# WHY THIS IS ONE MODULE AND NOT TWO COPIES
#     engine_v2_final_n100.py and engine_v2_final_mid.py both need the identical
#     four-arm block. Pasting it into each is how the engine and the Nautilus port
#     drifted apart before. One implementation, imported twice, cannot drift.
#
#     The spec (experiments/V34_SPEC.txt) requires the four arms to run in the SAME
#     process on the SAME panel, dates and seeds. That is satisfied because each
#     engine builds its panel once and hands the already-built objects to run_v34();
#     nothing is re-read or re-derived here.
#
# v1 AND v2 ARE NOT RECOMPUTED
#     The caller has already run them to write v2FINAL_*. Those exact curves are
#     passed in, so v1 and v2 in v34_comparison.csv are literally the same series as
#     v2FINAL_equity.csv rather than a second run that happens to agree. Only v3 and
#     v4 are computed here.
#
# WHAT metrics() DOES NOT GIVE, AND WHY IT IS EXTENDED HERE RATHER THAN CHANGED
#     engine_core.metrics() returns Config, CAGR%, Sharpe, Sortino, MaxDD%, Calmar,
#     Trades, TC_Rs. The spec also wants annualised volatility%, average deployed%
#     and final equity. metrics() is NOT modified: it writes v2FINAL_comparison.csv,
#     whose columns must not move. The three extra columns are added on top here.
#
# English only. Nothing printed here is hardcoded; every figure comes from the run.

def deployed_none(expo):
    """Deployed% of a mode-"none" arm. 100 without the drawdown limit, as it always
    was. With it, the engine's fourth return value, which is then the mean
    invested fraction at the close after the limit (test_exposure)."""
    from settings import dd_axis as _dda
    return 100.0 if _dda.is_default() else float(expo) * 100


def _dd_params():
    """{"dd": ...} when the drawdown-limit axis is on, {} when off, so a params
    file from a run without --dd is the file it always was. The other axes
    likewise, except buy_shortfall, which is written for every run."""
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    import settings
    return (({} if _dda.is_default() else {"dd": _dda.params()})
            | ({} if _capa.is_default() else {"capital": _capa.selected()})
            | ({} if _impa.is_default() else {"impact_k": _impa.selected()})
            | ({} if _pca.is_default() else {"participation_cap": _pca.selected()})
            | ({} if _fxa.is_default() else {"fixed_capital": True})
            | ({} if _sta.is_default() else {"bt_start": str(_sta.selected().date())})
            # Written for every run: the default itself changed on 2026-10-27, so
            # a params file without it is from a run that refused short buys.
            | {"buy_shortfall": settings.shortfall_axis.selected()})


def _window_label(eq=None):
    """One line naming the window every figure on the chart belongs to.

    ADDED 2026-09-02. Three different trade counts on three different windows
    once appeared on one chart with none of them labelled: 981 research fills on
    the 1,836-day window, 978 port fills on the same window, and 997 fills from a
    depth study on the retired 1,842-day window. A trade count without its window
    is not checkable, and a CAGR without its window has already been quoted
    against the wrong one in this project.
    """
    import settings
    n = f", {len(eq):,} trading days" if eq is not None else ""
    return (f"WINDOW {settings.BT_START_DATE.date()} to {settings.BT_END_DATE.date()}{n} -- "
            f"every CAGR, Sharpe, drawdown and TRADE COUNT on this page is on that "
            f"window and no other.")

TRADING_DAYS = 252


def ann_vol_pct(eq):
    """Annualised volatility of the daily returns of an equity curve, in percent."""
    r = eq.pct_change().dropna()
    return round(float(r.std() * np.sqrt(TRADING_DAYS) * 100), 2)


def arm_row(eq, label, tc=0, ntr=0, deployed_pct=100.0):
    """metrics() plus the three columns the spec asks for that it does not carry."""
    m = metrics(eq, label, tc, ntr)
    m["AnnVol%"] = ann_vol_pct(eq)
    m["Deployed%"] = round(float(deployed_pct), 1)
    m["FinalEquity"] = round(float(eq.iloc[-1]), 2)
    return m


def held_and_skips(audit, halves=None):
    """(mean names held per rebalance, cash-short skip count) from an audit dict.

    THESE TWO COLUMNS EXIST BECAUSE SIZING TURNED OUT TO CHANGE THE PORTFOLIO.
    Selection is rank-based and identical across arms -- verified, the top-8 target
    sets match on all 92 rebalances. But `invest_val` is computed over the WHOLE
    portfolio while new entrants are funded from CASH ALONE, so when the new names'
    combined target exceeds available cash the tail of the score-descending buy
    loop is skipped. Pro-vol hits that more often than inverse-vol. Without these
    columns a reader of v34_comparison.csv would assume v1 and v3 held the same
    names. They did not. See KNOWN_ISSUES.md.

    halves=None gives the full period; otherwise (y0, y1) restricts to one half.
    """
    dec = pd.DataFrame(audit["decisions"])
    hold = pd.DataFrame(audit["holdings"])
    skip = pd.DataFrame(audit["skipped"])
    if len(dec) == 0:
        return float("nan"), 0
    rb = pd.to_datetime(dec["decided_on"])
    if halves is not None:
        y0, y1 = halves
        rb = rb[(rb.dt.year >= y0) & (rb.dt.year <= y1)]
    if len(hold):
        h = hold[pd.to_datetime(hold["date"]).isin(rb)]
        mean_held = float(h.groupby("date")["symbol"].nunique().mean()) if len(h) else float("nan")
    else:
        mean_held = float("nan")
    if len(skip):
        s = skip[(skip["side"] == "BUY") & (skip["reason"] == "cash short (before TC)")]
        if halves is not None:
            sd = pd.to_datetime(s["date"])
            s = s[(sd.dt.year >= y0) & (sd.dt.year <= y1)]
        n_skip = int(len(s))
    else:
        n_skip = 0
    return mean_held, n_skip


def sub_rows(curves, halves, audits=None):
    """One row per (arm, half). Every cell carries CAGR and volatility.

    Each half is sliced FROM THE ARM'S OWN CURVE, which is already restricted to
    the backtest window, so the late half ends on the window's last day rather
    than on the last day of the price panel.
    """
    rows = []
    for hname, y0, y1 in halves:
        for label, eq, dep in curves:
            s = eq[(eq.index.year >= y0) & (eq.index.year <= y1)]
            if len(s) < 3:
                continue
            m = metrics(s, label)
            mh, nsk = (float("nan"), "")
            if audits and label in audits:
                mh, nsk = held_and_skips(audits[label], (y0, y1))
            rows.append({"Period": hname, "Config": label,
                         "CAGR%": m["CAGR%"], "AnnVol%": ann_vol_pct(s),
                         "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"],
                         "Deployed%": round(float(dep), 1),
                         "MeanNamesHeld": (round(mh, 2) if mh == mh else ""),
                         "CashShortSkips": nsk,
                         "FirstDate": str(s.index[0].date()),
                         "LastDate": str(s.index[-1].date()),
                         "Days": len(s)})
    return pd.DataFrame(rows)


def _git_state():
    """Describe the tree the run actually happened on, dirt included.

    Recording a bare commit hash was misleading: the working tree had roughly two
    dozen modified files, so the hash pointed at a tree that did not describe the
    run. A field pointing at the wrong tree is worse than an absent field, so this
    reports the commit AND whether the tree was dirty AND how many files differed.
    """
    def _run(args):
        try:
            r = subprocess.run(["git"] + args, capture_output=True, text=True,
                               timeout=10)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None

    head = _run(["rev-parse", "HEAD"])
    status = _run(["status", "--porcelain"])
    if head is None or status is None:
        return {"commit": None,
                "note": "git unavailable; the tree this ran on is not recorded"}
    modified = [l for l in status.splitlines() if l.strip()]
    dirty = len(modified) > 0
    return {"commit": head.strip(),
            "working_tree_dirty": dirty,
            "modified_or_untracked_files": len(modified),
            "note": ("the commit alone does NOT describe this run: the working "
                     "tree had uncommitted changes when it was produced"
                     if dirty else
                     "working tree clean; the commit describes this run exactly")}


# naming: arm,cadence,profile via SFX -- the caller composes SFX from
# selection_suffix() + cadence.suffix() + profiles.suffix() + tax suffix.
def _write_core(M, SFX, comp, subs, ARM_ON, bd, bh, curves, universe_label,
                universe_tag, consts, _reb, _wrote, arm_reg, cadence, costs):
    """The canonical v34_* files and chart_v34, exactly as run_v34 wrote them
    inline before the stop arms existed."""
    comp.to_csv(M / f"v34_comparison{SFX}.csv", index=False)
    _wrote.append(M / f"v34_comparison{SFX}.csv")

    subs.to_csv(M / f"v34_subperiods{SFX}.csv", index=False)
    _wrote.append(M / f"v34_subperiods{SFX}.csv")

    eq_cols = {"date": bd}
    for _, _, col, eq, _, _, _, _ in ARM_ON:
        eq_cols[col] = eq.values
    eq_cols["buyhold"] = bh.values
    pd.DataFrame(eq_cols).to_csv(M / f"v34_equity{SFX}.csv", index=False)
    _wrote.append(M / f"v34_equity{SFX}.csv")

    _wrote.append(M / f"v34_params{SFX}.json")
    (M / f"v34_params{SFX}.json").write_text(json.dumps({
        "universe": universe_label,
        "universe_tag": universe_tag,
        "window_start": str(bd[0].date()),
        "window_end": str(bd[-1].date()),
        "trading_days": int(len(bd)),
        # ONLY THE ARMS THIS RUN ACTUALLY MEASURED. On a full selection this is
        # the same four entries in the same order it has always carried.
        "arms": {n: f"{arm_reg.ARMS[n].sizing} + mode={arm_reg.ARMS[n].mode}"
                 for n, _, _, _, _, _, _, _ in ARM_ON},
        "reference": "equal-weight buy & hold of the same universe, same panel",
        # REBAL IS THE CADENCE THIS RUN USED. `consts` comes from the engine,
        # which passes its module constant; a cadence-3 run recorded "REBAL": 20
        # until 2026-09-23. At the default the value, and so the file, is unchanged.
        "constants": {**consts, "REBAL": _reb},
        "git_state": _git_state(),
        # WHICH PRICE DATA THIS RUN READ. git_state pins the CODE and already
        # says when it cannot ("working_tree_dirty"); nothing pinned the DATA
        # until 2026-09-20, and that is the half that moved: midcap150's two
        # tradeable artefacts were built on data/raw/MidCap150/clean, the
        # universe was repointed a day later, and no artefact and no gate could
        # say so. GATE 8 in check_all.py reads this field back and refuses a
        # mismatch. See model.data_fingerprint for what the digest covers and
        # why it is the whole file rather than a row count.
        "data_source": model.data_fingerprint(
            settings.REGISTRY[universe_tag].prepare_data_dir(),
            settings.REGISTRY[universe_tag].raw_data_dir),
        "run_date": str(pd.Timestamp.today().date()),
        "spec": "experiments/V34_SPEC.txt",
        # THE CAVEAT TRAVELS WITH THE NUMBERS. Present only when the profile is
        # not `research`, so every research artefact is byte-for-byte what it was
        # -- which the standing gate proves rather than this comment asserting.
        # costs.gate_status() returns None under research and the key is
        # dropped, so the key SET of a gated artefact does not move either.
        **({"gate_status": costs.gate_status()}
           if costs.gate_status() else {}),
        # PIT RUNS ONLY: the validator verdict, residual survivorship and the
        # look-ahead note. Absent in a static run.
        **market_data.params_fields(universe_tag),
        **_dd_params(),
    }, indent=2))

    # --- chart: four arms plus the reference on one axis ---
    fig, ax = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[2, 1])
    # COLOUR IS KEYED TO THE ARM, NOT TO POSITION. Zipping a fixed five-colour
    # list against `curves` gave v3 v2's colour the moment v2 was deselected, so
    # the same arm changed colour between two charts in the same directory.
    ARM_STYLE = {"v1": ("#1f77b4", "-"), "v2": ("#d62728", "-"),
                 "v3": ("#2ca02c", "-"), "v4": ("#9467bd", "-")}
    style = [ARM_STYLE[n] for n, *_ in ARM_ON] + [("#7f7f7f", "--")]
    for (lab, eq, dep), (c, ls) in zip(curves, style):
        m = metrics(eq, lab)
        ax[0].plot(eq.index, (eq / eq.iloc[0] - 1) * 100, lw=1.8, color=c, ls=ls,
                   label=f"{lab}  [inv {dep:.0f}%]  CAGR {m['CAGR%']}%  "
                         f"vol {ann_vol_pct(eq)}%  Sharpe {m['Sharpe']}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    # THE TITLE DESCRIBES THE ARMS ON THE CHART, DERIVED RATHER THAN ASSERTED.
    # It used to say "four ... v1/v3 hold 100% invested; v2/v4 scale exposure by
    # breadth" as a literal, which is a false statement on any subset. Derived
    # from ARM_ON it reproduces that sentence exactly when all four are present --
    # the always-invested arms ARE v1 and v3, the breadth-scaled ones ARE v2 and
    # v4 -- and tells the truth when they are not.
    _CNT = {1: "one", 2: "two", 3: "three", 4: "four"}
    _flat = "/".join(n for n, *_ in ARM_ON if arm_reg.ARMS[n].mode == "none")
    _brd = "/".join(n for n, *_ in ARM_ON if arm_reg.ARMS[n].mode == "breadth")
    _how = "; ".join(x for x in (f"{_flat} hold 100% invested" if _flat else "",
                                 f"{_brd} scale exposure by breadth" if _brd else "")
                     if x)
    _sizings = {arm_reg.ARMS[n].sizing for n, *_ in ARM_ON}
    _size_note = (" Sizing is the only other difference: 1/vol against vol."
                  if len(_sizings) > 1 else
                  f" All arms here size {'1/vol' if 'invvol' in _sizings else 'by vol'}.")
    ax[0].set_title(
        settings.run_label(universe_label, [n for n, *_ in ARM_ON]) + "\n" +
        f"{universe_label} -- {_CNT.get(len(ARM_ON), len(ARM_ON))} sizing/exposure "
        f"arm{'s' if len(ARM_ON) != 1 else ''} plus equal-weight buy & hold\n"
        f"WINDOW {bd[0].date()} to {bd[-1].date()}, {len(bd)} trading days -- every "
        f"CAGR, Sharpe, drawdown and TRADE COUNT here is on that window and no other.\n"
        f"All figures after Zerodha costs plus 0.15% slippage.\n"
        f"{_how}.{_size_note}", fontsize=9)
    ax[0].legend(loc="upper left", fontsize=8)
    ax[0].grid(alpha=.3)

    for (lab, eq, dep), (c, ls) in zip(curves, style):
        d = (eq / eq.cummax() - 1) * 100
        ax[1].plot(eq.index, d, lw=1.2, color=c, ls=ls,
                   label=f"{lab} (max {d.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=7.5, ncol=2)
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    # naming: arm,cadence,profile via SFX -- backtest_runs.py
    plt.savefig(M / f"chart_v34{SFX}.png", dpi=150, bbox_inches="tight", metadata={"Title": ax[0].get_title().split("\n")[0]})
    _wrote.append(M / f"chart_v34{SFX}.png")


# naming: arm,cadence,profile via SFX -- every artefact here is `v34_fixed<stem>{SFX}`,
# SFX composed in run_v34 and ending in "_fixed", the only setting that calls this.
def _write_fixed(M, SFX, ARM_ON, bd, bh, base, u, rebal, _wrote):
    """The fixed-capital companions: v34_fixed (figures per line), v34_fixed_years
    (rupee P&L per calendar year) and v34_fixed_equity (the basket's and the
    index's fixed-capital curves). See results/fixed_capital.py."""
    w0, w1 = bd[0], bd[-1]
    rows, years = [], []
    for _, lab, _, eq, _, _, _, au in ARM_ON:
        inv = max_invested((au or {}).get("fixed"), base)
        rows.append(figures(eq, base, STRATEGY, lab, inv, w0, w1))
        years += year_rows(eq, base, STRATEGY, lab)
    b_rows, b_years, b_curves = benchmark_rows(bh, u, bd, base, rebal, w0, w1)
    rows += b_rows
    years += b_years
    pd.DataFrame(rows).to_csv(M / f"v34_fixed{SFX}.csv", index=False)
    _wrote.append(M / f"v34_fixed{SFX}.csv")
    pd.DataFrame(years).to_csv(M / f"v34_fixed_years{SFX}.csv", index=False)
    _wrote.append(M / f"v34_fixed_years{SFX}.csv")
    pd.DataFrame({"date": bd, **{f"{k}_fixed": v.values for k, v in b_curves.items()}}
                 ).to_csv(M / f"v34_fixed_equity{SFX}.csv", index=False)
    _wrote.append(M / f"v34_fixed_equity{SFX}.csv")


# naming: arm,cadence,profile via SFX -- every artefact here is `v34_stop_<stem>{SFX}`,
# SFX composed from stop_selection_suffix() + cadence, profile and tax suffixes.
def _write_stop(M, stop_rows, stop_curves, stop_audits, bd, bh, halves,
                universe_label, universe_tag, consts, _reb, _wrote, arm_reg, cadence,
                costs, _tax):
    """The companion v34_stop_* files: the selected stop arms and the buy & hold."""
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    import settings
    SFX = (arm_reg.stop_selection_suffix() + cadence.suffix() + settings.profile_axis.suffix()
            + _tax.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix()
            + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix())
    rows = stop_rows + [arm_row(bh, "buy & hold equal-weight", 0, 0, 100.0)]
    rows[-1]["MeanNamesHeld"], rows[-1]["CashShortSkips"] = "", ""
    pd.DataFrame(rows).to_csv(M / f"v34_stop_comparison{SFX}.csv", index=False)
    _wrote.append(M / f"v34_stop_comparison{SFX}.csv")
    curves = [(a.label, eq, dep) for a, eq, dep in stop_curves] \
        + [("buy & hold equal-weight", bh, 100.0)]
    sub_rows(curves, halves, stop_audits).to_csv(M / f"v34_stop_subperiods{SFX}.csv",
                                                 index=False)
    _wrote.append(M / f"v34_stop_subperiods{SFX}.csv")
    eq_cols = {"date": bd}
    for a, eq, _ in stop_curves:
        eq_cols[a.equity_column] = eq.values
    eq_cols["buyhold"] = bh.values
    pd.DataFrame(eq_cols).to_csv(M / f"v34_stop_equity{SFX}.csv", index=False)
    _wrote.append(M / f"v34_stop_equity{SFX}.csv")
    _stop = {a.name: a.kwargs["drawdown_stop"] for a, _, _ in stop_curves}
    (M / f"v34_stop_params{SFX}.json").write_text(json.dumps({
        "universe": universe_label,
        "universe_tag": universe_tag,
        "window_start": str(bd[0].date()),
        "window_end": str(bd[-1].date()),
        "trading_days": int(len(bd)),
        "arms": {a.name: f"{a.sizing} + mode={a.mode} + drawdown stop, parent {a.parent}"
                 for a, _, _ in stop_curves},
        "drawdown_stop": {n: {"threshold": st.threshold,
                              "cooldown_cycles": st.cooldown_cycles,
                              "reentry_breadth": st.reentry_breadth}
                          for n, st in _stop.items()},
        # A FIXTURE RUN SAYS SO IN ITS OWN RECORD. It tests the wiring and is never
        # a result (portfolio.FIXTURE_ENV).
        "test_fixture": arm_reg.fixture_threshold() is not None,
        "reference": "equal-weight buy & hold of the same universe, same panel",
        "constants": {**consts, "REBAL": _reb},
        "git_state": _git_state(),
        "data_source": model.data_fingerprint(
            settings.REGISTRY[universe_tag].prepare_data_dir(),
            settings.REGISTRY[universe_tag].raw_data_dir),
        "run_date": str(pd.Timestamp.today().date()),
        "spec": "experiments/DRAWDOWN_STOP_PREREG.txt",
        **({"gate_status": costs.gate_status()}
           if costs.gate_status() else {}),
        # PIT RUNS ONLY: the validator verdict, residual survivorship and the
        # look-ahead note. Absent in a static run.
        **market_data.params_fields(universe_tag),
        **_dd_params(),
    }, indent=2))
    _wrote.append(M / f"v34_stop_params{SFX}.json")


# naming: arm,cadence,profile via SFX -- every artefact this step writes is
# named `<stem>{SFX}.<ext>` with SFX composed at backtest_runs.py from
# selection_suffix() + cadence.suffix() + profiles.suffix().
def run_v34(M, universe_label, universe_tag, px, op, sc, bd, pc, mom20,
            backtest_exposure, v1_eq, v1_tc, v1_n, v2_eq, v2_tc, v2_n, v2_expo,
            start_capital, halves, consts, v1_audit=None, audits_out=None, v1_expo=1.0):
    """Run v3 and v4, assemble all four arms plus buy & hold, write the outputs.

    `audits_out`, when a dict, receives {arm name: audit} for the selected arms, so
    the engine's verdict can state the tax each one paid."""
    def _blank():
        return {k: [] for k in ("holdings", "summary", "trades",
                                "ranking", "decisions", "skipped")}

    # v2 is re-run purely to obtain its audit for the two diagnostic columns. This
    # is safe: passing an audit dict was verified to leave the equity curve, the
    # transaction cost and the trade count bit-identical, so the reported v2 row
    # still comes from the caller's original curve, not from this run.
    import portfolio as arm_reg
    sel = set(arm_reg.selected_names())

    # GATED ON v2 BEING SELECTED, like v3 and v4 below. Its only purpose is v2's
    # MeanNamesHeld / CashShortSkips columns; with v2 deselected there is no v2
    # row to carry them and this is a whole backtest run for a discarded result.
    # THE RUN'S CADENCE, AS AN ARGUMENT. Default 20, which is what these calls
    # resolved to when they passed nothing, so the default path is unchanged.
    from settings import cadence
    _reb = cadence.selected()
    # THE TAX SELECTION, READ ONCE AND PASSED AS AN ARGUMENT -- exactly as _reb
    # above and participation_cap below. backtest_exposure's tax_enabled is a
    # PARAMETER by design (portfolio.py gives the reason: same as rebal
    # and participation_cap), so it stays one; what was missing was any caller on
    # the PUBLISHED path passing it.
    #
    # UNTIL 2026-09-18 NO SUCH CALLER EXISTED. tax_enabled defaulted to False at
    # every one of the 31 call sites except reports.py's and
    # backtest_runs.py's, so `--tax on` moved filenames and nothing else: 36
    # of 40 suffixed artefacts were BYTE-IDENTICAL to their untaxed twins and the
    # other 4 differed only in a header label. The axis renamed; it did not charge.
    from settings import tax as _tax_axis
    _taxon = _tax_axis.selected()
    # THE PROFILE'S CAP, RESOLVED ONCE AND PASSED AS AN ARGUMENT.
    # costs.py records why this is not a global on test_exposure: settings.cadence
    # documents rebal_cadence_sweep.py setting test_exposure.REBAL and never
    # restoring it, so every later in-process step silently used the wrong cadence.
    # None under profile="research", so `q` is untouched and the published history
    # is exact.
    import costs
    import settings
    from settings import REGISTRY as _REG
    _capkw = costs.cap_kwargs(_REG[universe_tag])
    a2 = _blank()
    if "v2" in sel:
        backtest_exposure(px, op, sc, bd, pc, mom20, mode="breadth",
                          sizing="invvol", drawdown_stop=None,
                          audit=a2, rebal=_reb,
                          tax_enabled=_taxon, **_capkw)

    # --- the two new arms, same panel and dates as v1/v2 ---
    # COMPUTED ONLY IF SELECTED. A run that asked for v1 and v3 has no use for
    # v4's curve, and running it would put a number in the process that must then
    # be filtered out of four separate artefacts -- the kind of thing that leaks.
    # ARM_SEL is read at CALL time, not at import, so run.py setting it after this
    # module is imported still takes effect.
    a3, a4 = _blank(), _blank()
    v3_eq = v3_tc = v3_n = None
    v3_expo = 1.0
    v4_eq = v4_tc = v4_n = None
    v4_expo = 0.0
    if "v3" in sel:
        v3_eq, v3_tc, v3_n, v3_expo = backtest_exposure(px, op, sc, bd, pc, mom20, mode="none", sizing="provol", drawdown_stop=None,
                                                        audit=a3,
                                                        rebal=_reb, tax_enabled=_taxon,
                                                        **_capkw)
    if "v4" in sel:
        v4_eq, v4_tc, v4_n, v4_expo = backtest_exposure(px, op, sc, bd, pc, mom20,
                                                        mode="breadth",
                                                        sizing="provol",
                                                        drawdown_stop=None,
                                                        audit=a4, rebal=_reb,
                                                        tax_enabled=_taxon, **_capkw)
    # THE BUY & HOLD BASKET: every name in static mode; in pit mode the members on
    # the first pit rebalance, bd[0] (owner's decision, 2026-10-10).
    bh = start_capital * (1 + market_data.buyhold_prices(px, bd[0], market_data.MEMBERSHIP)
                          .pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    # ONE TABLE DRIVES CURVES, AUDITS, ROWS AND THE EQUITY COLUMNS, so an arm
    # cannot be filtered out of one of them and left in another. Order is ARMS
    # order, which is the order the four-arm table has always been written in.
    ARM_DEF = [
        ("v1", "v1 invvol, 100% invested",  "v1_invvol_none",    v1_eq, v1_tc, v1_n, deployed_none(v1_expo), v1_audit),
        ("v2", "v2 invvol, breadth-scaled", "v2_invvol_breadth", v2_eq, v2_tc, v2_n, v2_expo * 100,  a2),
        ("v3", "v3 provol, 100% invested",  "v3_provol_none",    v3_eq, v3_tc, v3_n, deployed_none(v3_expo), a3),
        ("v4", "v4 provol, breadth-scaled", "v4_provol_breadth", v4_eq, v4_tc, v4_n, v4_expo * 100,  a4),
    ]
    ARM_ON = [a for a in ARM_DEF if a[0] in sel]
    import settings
    if audits_out is not None:
        audits_out.update({nm: au for nm, _, _, _, _, _, _, au in ARM_ON})

    curves = [(lab, eq, dep) for _, lab, _, eq, _, _, dep, _ in ARM_ON] \
        + [("buy & hold equal-weight", bh, 100.0)]

    audits = {lab: au for _, lab, _, _, _, _, _, au in ARM_ON if au is not None}

    rows = [arm_row(eq, lab, tc, n, dep)
            for _, lab, _, eq, tc, n, dep, _ in ARM_ON] \
        + [arm_row(bh, "buy & hold equal-weight", 0, 0, 100.0)]
    for r in rows:
        if r["Config"] in audits:
            mh, nsk = held_and_skips(audits[r["Config"]])
            r["MeanNamesHeld"] = round(mh, 2)
            r["CashShortSkips"] = nsk
            # Under trim, the buys cut to fit. A refuse run trims nothing and has
            # no such column, so its file is the one the rule always wrote.
            if settings.shortfall_axis.selected() == "trim":
                r["TrimmedBuys"] = audits[r["Config"]].get("buy_shortfall", {}).get("trimmed", "")
        else:
            # buy & hold holds the whole universe every day: not-applicable,
            # not unmeasured. Written as an empty cell so pandas does not
            # coerce the column to float and render it as NaN.
            r["MeanNamesHeld"] = ""
            r["CashShortSkips"] = ""
            if settings.shortfall_axis.selected() == "trim":
                r["TrimmedBuys"] = ""
    # THE CANONICAL v34_* FILES ARE WRITTEN ONLY ON A FULL FOUR-ARM SELECTION.
    # SFX is "" then, so those paths and their contents are exactly what they have
    # always been. A subset writes v34_comparison_v1_v3.csv and friends beside
    # them and leaves the canonical files untouched.
    #
    # THIS IS NOT TIDINESS, IT PROTECTS SEVEN GATES. purge_fix_measure,
    # seed_noise_measure, seed_noise_report, shuffle_test, validate_topn,
    # rebal_cadence_sweep and drawdown_exit_measure all read v34_comparison.csv,
    # and six of them assert their own control run against its v2 ROW. A two-arm
    # subset overwriting that file would leave every one of them comparing against
    # a table that no longer holds their reference -- and they would discover it
    # later, in a different script, as a missing row rather than as this run's
    # doing. The universe work set the same precedent: a narrower selection writes
    # its own file rather than silently rewriting the published one.
    # BOTH AXES IN THE NAME. The arm suffix says which arms are in the table; the
    # cadence suffix says which cadence produced them. Both are empty at the
    # default, so the canonical v34_* filenames are unchanged.
    # THE PROFILE JOINS THE FILENAME TOO -- and this is the "companion file"
    # decision. Adding tradeable ROWS to v34_comparison.csv would put them in front
    # of the seven identity gates that read it: several do .set_index("Config") and
    # .max() over the non-buy&hold rows, so extra arms would change what they
    # compute without any of them erroring. A suffixed companion leaves the file
    # those gates read untouched and puts both profiles one directory listing apart.
    # Empty for profile="research", so the published names are unchanged.
    from settings import tax as _tax
    # THE TAX AXIS JOINS THE NAME (2026-09-17), on the same default-is-unsuffixed
    # rule as the three before it: empty at tax=off, so every published
    # v34_* filename is byte-identical to what it has always been, and a tax run
    # writes a companion rather than overwriting the gated file. Measured, not
    # assumed -- settings.CARRIES records what this expression was probed to carry.
    # THE CORE PART OF THE SELECTION NAMES THE CORE FILES. A stop arm never enters
    # v34_comparison.csv: it is written to the companion v34_stop_* files below, so
    # a run of v1..v4 plus v5 still writes the canonical files with v1..v4 only.
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    import settings
    SFX = (arm_reg.selection_suffix([n for n, *_ in ARM_ON]) + cadence.suffix()
           + settings.profile_axis.suffix() + _tax.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix()
           + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix())
    # THE PATHS THIS CALL WRITES, IN ORDER. Read only by the report line below, so
    # that what is printed is derived from what was written rather than restated.
    _wrote = []

    comp = pd.DataFrame(rows)
    subs = sub_rows(curves, halves, audits)
    # A SELECTION OF STOP ARMS ONLY HAS NO CORE TABLE TO WRITE.
    if ARM_ON:
        _write_core(M, SFX, comp, subs, ARM_ON, bd, bh, curves, universe_label,
                    universe_tag, consts, _reb, _wrote, arm_reg, cadence, costs)
        if not _fxa.is_default():
            _write_fixed(M, SFX, ARM_ON, bd, bh, start_capital, _REG[universe_tag],
                         _reb, _wrote)

    # --- THE STOP ARMS, v5 AND v6, when selected by name ---
    # Same panel, same dates, same cap and tax as the core arms; the stop comes in
    # through Arm.kwargs, which refuses while the stop is sealed unless the
    # DRAWDOWN_STOP_FIXTURE test threshold is set. Written to companion files so
    # nothing a core-arm gate reads can change.
    stop_rows, stop_curves, stop_audits = [], [], {}
    for _a in arm_reg.selected_stop():
        _au = _blank()
        _au["costs"] = {"fills": [], "days": []}
        _eq, _tc, _n, _expo = backtest_exposure(px, op, sc, bd, pc, mom20, audit=_au, rebal=_reb,
                                                tax_enabled=_taxon, **_a.kwargs,
                                                **_capkw)
        _r = arm_row(_eq, _a.label, _tc, _n, _expo * 100)
        _mh, _nsk = held_and_skips(_au)
        _r["MeanNamesHeld"], _r["CashShortSkips"] = round(_mh, 2), _nsk
        stop_rows.append(_r)
        stop_curves.append((_a, _eq, _expo * 100))
        stop_audits[_a.label] = _au
        if audits_out is not None:
            audits_out[_a.name] = _au
    if stop_rows:
        _write_stop(M, stop_rows, stop_curves, stop_audits, bd, bh, halves,
                    universe_label, universe_tag, consts, _reb, _wrote, arm_reg,
                    cadence, costs, _tax)
        comp = pd.concat([comp, pd.DataFrame(stop_rows)], ignore_index=True)

    # THIS STEP REPORTS ITS OWN WRITES, AND IT IS THE ONLY THING THAT CAN. SFX is
    # composed above from THREE axes -- arm selection, cadence, profile -- so no
    # caller can name these files from anything it holds. engine_v2_final used to
    # print the five CANONICAL names on this step's behalf, which under `--rebal
    # 200` named five gated files nobody had touched and named none of the five
    # that were written. The names come from the paths, not from a second copy of
    # the f-strings above.
    # THE BUY-SHORTFALL TOTALS, one line per arm: buys cut to fit, and buys
    # refused for want of cash (every "cash short" reason but the trim).
    for _lab, _au in audits.items():
        _bs = _au.get("buy_shortfall")
        if _bs is not None:
            print(f"  buy_shortfall {_bs['rule']}: {_lab}: {_bs['trimmed']} buys trimmed, "
                  f"{_bs['refused']} buys refused")
    print("\n  saved -> " + ", ".join(q.name for q in _wrote))
    plt.close()

    return comp, subs, curves


# ---------------------------------------------------------------------------
# SINGLE-ARM EXECUTION
# ---------------------------------------------------------------------------
def run_arm(u, arm, rebal=None, out_dir=None):
    """Run ONE arm on ONE universe and write that combination's own artefacts.

    WHY THIS EXISTS ALONGSIDE run_v34, NOT INSTEAD OF IT.
        run_v34 computes all four arms in a single call and writes them as rows of
        v34_comparison.csv. That file is not just a report: SEVEN scripts read it as
        an IDENTITY GATE -- purge_fix_measure, seed_noise_measure, seed_noise_report,
        shuffle_test, validate_topn, drawdown_exit_measure and rebal_cadence_sweep
        each assert their own control run reproduces its published v2 row exactly,
        and make_v34_report indexes all five rows by Config. Replacing that table
        with per-arm files would break all seven.

        So this is ADDITIVE. run_v34 keeps producing the combined table when all
        four arms are run; this produces one arm's own output, into its own
        directory, so a single arm can be run on its own without touching anything
        the rest of the project reads.

    IT LOADS ITS OWN PANEL. run_v34 is handed already-built objects by an engine
    that has just used them; this is called directly by run.py for an arbitrary
    (universe, arm) pair, with no engine in the picture, so it builds what it needs.
    The construction is the same as the engines': close/open/score pivots, the
    universe's own window, precompute, 20-day momentum.
    """
    import settings
    from market_data import precompute
    from portfolio import backtest_exposure, START_CAPITAL

    # THE CADENCE IS PART OF THE OUTPUT PATH. Without it a --rebal 40 run wrote
    # into runs/<uni>/<arm>/ and replaced the published cadence-20 result.
    out = Path(out_dir) if out_dir is not None else settings.run_dir(u, arm, rebal)
    out.mkdir(parents=True, exist_ok=True)

    # THE GUARD IS LOADED PER UNIVERSE, HERE, because this is where the
    # universe is known. engine_core holds it (beside MEMBERSHIP) and
    # backtest_exposure reads it directly, so every call site inherits it.
    market_data.set_tradeability(u)
    src = model.require_cache(u.score_cache,
                               what=f"{u.label} score panel")
    p = read_table(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = u.trading_days(px.index)
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1

    # THE PROFILE'S CAP, RESOLVED ONCE AND PASSED AS AN ARGUMENT.
    # costs.py records why this is not a global on test_exposure: settings.cadence
    # documents rebal_cadence_sweep.py setting test_exposure.REBAL and never
    # restoring it, so every later in-process step silently used the wrong cadence.
    # None under profile="research", so `q` is untouched and the published history
    # is exact.
    import costs
    import settings
    _capkw = costs.cap_kwargs(u)
    audit = {k: [] for k in ("holdings", "summary", "trades",
                             "ranking", "decisions", "skipped")}
    # THE RUN'S TAX SELECTION, as run_v34 above. run_arm writes
    # runs/<u>/<arm>/comparison.csv and params.json; without this an arm run under
    # --tax on reported untaxed numbers under a taxed run folder.
    from settings import tax as _tax_axis
    eq, tc, ntr, expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, audit=audit, **arm.kwargs,
        tax_enabled=_tax_axis.selected(),
        # EVERY universe is valued at the open. The two that opted out of this
        # correction were two retired universes, and they are gone.
        rebal=rebal, **_capkw)

    # THE BUY & HOLD BASKET: every name in static mode; in pit mode the members on
    # the first pit rebalance, bd[0] (owner's decision, 2026-10-10).
    from settings import capital_axis as _capital_axis
    bh = _capital_axis.selected() * (1 + market_data.buyhold_prices(px, bd[0], market_data.MEMBERSHIP)
                          .pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    # A stop arm is not always invested: its share is the mean target exposure over
    # the rebalance grid, 0 on the days the stop holds it in cash, as for v2 and v4.
    dep = deployed_none(expo) if arm.mode == "none" and arm.stop is None else expo * 100
    rows = [arm_row(eq, arm.label, tc, ntr, dep),
            arm_row(bh, "buy & hold equal-weight", 0, 0, 100.0)]
    mh, nsk = held_and_skips(audit)
    rows[0]["MeanNamesHeld"], rows[0]["CashShortSkips"] = round(mh, 2), nsk
    rows[1]["MeanNamesHeld"], rows[1]["CashShortSkips"] = "", ""
    # Under trim, the buys cut to fit, as in run_v34; a refuse run has no column.
    import settings
    if settings.shortfall_axis.selected() == "trim":
        rows[0]["TrimmedBuys"], rows[1]["TrimmedBuys"] = audit["buy_shortfall"]["trimmed"], ""
    _bs = audit["buy_shortfall"]
    print(f"  buy_shortfall {_bs['rule']}: {arm.label}: {_bs['trimmed']} buys trimmed, "
          f"{_bs['refused']} buys refused")
    # UNDER tax=on, THREE MORE ROWS, AFTER THE TWO THAT HAVE ALWAYS BEEN HERE
    # (2026-09-25). Row 0 is the headline: nothing sold at the end, the last
    # partial financial year settled on realised gains. Row 1 is the untaxed
    # daily-rebalanced buy & hold, the reference. Then the same arm with every
    # holding sold on the last day, the investable held-lots buy & hold after tax
    # (held to the end, so nothing realised and nil tax), and that basket sold on
    # the last day with sell charges and tax. tax=off writes exactly the two rows
    # it always wrote.
    if _tax_axis.selected():
        eq_l, tc_l, ntr_l, _ = backtest_exposure(
            px, op, sc, bd, pc, mom20, audit=None, **arm.kwargs,
            tax_enabled=True, end_sale=True,
            rebal=rebal, **_capkw)
        hb = held_lots(px, op, bd)
        hd = hb["detail"]
        extra = [arm_row(eq_l, f"{arm.label}, sold on the last day", tc_l, ntr_l, dep),
                 arm_row(hb["eq_headline"], "buy & hold held lots, taxed (investable)",
                         hd["buy_tc"], hd["names"], 100.0),
                 arm_row(hb["eq_last_day"], "buy & hold held lots, sold on the last day",
                         hd["buy_tc"] + hd["sell_tc"], 2 * hd["names"], 100.0)]
        for r in extra:
            r["MeanNamesHeld"], r["CashShortSkips"] = "", ""
            if settings.shortfall_axis.selected() == "trim":
                r["TrimmedBuys"] = ""
        rows += extra
    comp = pd.DataFrame(rows)
    # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
    comp.to_csv(out / "comparison.csv", index=False)

    halves = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
    curves = [(arm.label, eq, dep), ("buy & hold equal-weight", bh, 100.0)]
    # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
    sub_rows(curves, halves, {arm.label: audit}).to_csv(out / "subperiods.csv", index=False)

    # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
    pd.DataFrame({"date": bd, arm.equity_column: eq.values,
                  "buyhold": bh.values}).to_csv(out / "equity.csv", index=False)

    # THE FIXED-CAPITAL FIGURES (settings.fixed_axis), in the arm directory beside
    # comparison.csv. Written only with --fixed-capital, whose directory ends in
    # "@fixed", so no other directory gains a file.
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    if not _fxa.is_default():
        _base = float(_capital_axis.selected())
        _reb = rebal if rebal is not None else 20
        f_rows = [figures(eq, _base, STRATEGY, arm.label,
                             max_invested(audit.get("fixed"), _base), bd[0], bd[-1])]
        f_years = year_rows(eq, _base, STRATEGY, arm.label)
        b_rows, b_years, b_curves = benchmark_rows(bh, u, bd, _base, _reb, bd[0], bd[-1])
        # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
        pd.DataFrame(f_rows + b_rows).to_csv(out / "fixed.csv", index=False)
        # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
        pd.DataFrame(f_years + b_years).to_csv(out / "fixed_years.csv", index=False)
        # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
        pd.DataFrame({"date": bd, "strategy": eq.values,
                      **{f"{k}_fixed": v.values for k, v in b_curves.items()}}
                     ).to_csv(out / "fixed_equity.csv", index=False)

    # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
    (out / "params.json").write_text(json.dumps({
        "universe": u.label, "universe_tag": u.tag,
        "arm": arm.name, "mode": arm.mode, "sizing": arm.sizing,
        "rebal": rebal if rebal is not None else 20,
        "profile": settings.profile_axis.selected(),
        "tax": "on" if _tax_axis.selected() else "off",
        "buy_sizing": "decision close",
        "purge_mode": u.purge_mode,
        "window_start": str(bd[0].date()), "window_end": str(bd[-1].date()),
        "trading_days": int(len(bd)),
        "deployed_pct": round(float(dep), 1),
        "git_state": _git_state(), "run_date": str(pd.Timestamp.today().date()),
        **market_data.params_fields(u.tag),
        **_dd_params(),
    }, indent=2))

    fig, ax = plt.subplots(2, 1, figsize=(13, 8), height_ratios=[2, 1])
    for (lab, e, d), c in zip(curves, ("#1f77b4", "#7f7f7f")):
        m = metrics(e, lab)
        ax[0].plot(e.index, (e / e.iloc[0] - 1) * 100, lw=1.8, color=c,
                   ls="-" if c != "#7f7f7f" else "--",
                   label=f"{lab}  [inv {d:.0f}%]  CAGR {m['CAGR%']}%  "
                         f"vol {ann_vol_pct(e)}%  Sharpe {m['Sharpe']}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(settings.run_label(u.label, [arm.name]) + "\n" +
                    f"{u.label} -- {arm.label}\n{_window_label(eq)}\n"
                    f"mode={arm.mode}  sizing={arm.sizing}  "
                    f"rebal={rebal if rebal is not None else 20}", fontsize=9)
    ax[0].legend(loc="upper left", fontsize=8); ax[0].grid(alpha=.3)
    for (lab, e, d), c in zip(curves, ("#1f77b4", "#7f7f7f")):
        dd = (e / e.cummax() - 1) * 100
        ax[1].plot(e.index, dd, lw=1.2, color=c, label=f"{lab} (max {dd.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=8); ax[1].grid(alpha=.3)
    # THE RUN LABEL TRAVELS IN THE PNG'S Title METADATA, so a script can check
    # which run drew a chart without reading pixels. 2026-09-23.
    # naming: delegated -- out is settings.run_dir(u, arm, rebal), named by settings.path_tail; run.py passes no out_dir
    plt.tight_layout(); plt.savefig(out / "chart.png", dpi=140, bbox_inches="tight", metadata={"Title": ax[0].get_title().split("\n")[0]})
    plt.close()
    return comp, out


# ======================================================================================
# FIXED-CAPITAL FIGURES. From results/fixed_capital.py (moved 2026-11-27).
# ======================================================================================
# fixed_capital.py -- the figures of a fixed-capital run (settings.fixed_axis), and its
# basket and index under the same rule.
#
# A fixed-capital run does not reinvest its profits, so CAGR understates it: the
# equity grows by the base times each period's return, not by the equity times it.
# The figures here are the ones that describe such a run. `base` is --capital.
#
#     AvgAnnRet%          (end equity - base) / base / years
#     Year% <y>           that calendar year's rupee P&L / base. A year's P&L runs
#                         from the previous year's last close (the base, for the
#                         first year) to its own last close, so base + the sum of
#                         the yearly P&L is the end equity.
#     MeanFullYear%       arithmetic mean of Year% over the full calendar years in
#                         the window; FullYears names them
#     MaxDD_Rs            the largest fall from a running peak, in rupees
#     MaxDD_base%         the largest (equity - running peak) / base
#     MaxInvested_base%   the highest held market value / base, with its date. For
#                         the strategy: at an execution-day open, after that day's
#                         buys (backtest_exposure's audit["fixed"]). For the basket
#                         and the index: at a grid-day close, before that day's reset.
#     CAGR%               shown, and labelled as understating a fixed-capital run
#
# years is calendar days / 365.25, as engine_core.metrics() computes it.
#
# THE BASKET AND THE INDEX UNDER THE SAME RULE. On each of the strategy's grid days
# (every `rebal`-th session from the first, the days the strategy decides a
# rebalance) the invested amount is reset to min(base, equity) at that day's close;
# the rest is idle cash that earns nothing. Between resets the invested amount moves
# with the line's daily return, so it compounds inside a period, as the strategy's
# positions do. Two differences from the strategy are stated, not modelled:
#   - the strategy's reset happens at the NEXT session's open, so the benchmarks'
#     reset is one session earlier; both series are close-only;
#   - the index is the universe's NSE price index file, without dividends.
# The reset also brings an invested amount above the base back to the base, which
# the strategy does not do to its held names.

STRATEGY, BASKET, INDEX = "strategy", "basket", "index"

CAGR_LABEL = "CAGR% (understates a fixed-capital run)"


def years_of(eq):
    return (eq.index[-1] - eq.index[0]).days / 365.25


def full_years(index, w0=None, w1=None):
    """Calendar years the window covers from 1 January to 31 December."""
    w0 = pd.Timestamp(index[0] if w0 is None else w0)
    w1 = pd.Timestamp(index[-1] if w1 is None else w1)
    return [int(y) for y in sorted(set(index.year))
            if w0 <= pd.Timestamp(f"{y}-01-01") and w1 >= pd.Timestamp(f"{y}-12-31")]


def yearly_pnl(eq, base):
    """{year: rupee P&L}, each year from the previous year's last close; the first
    year from the base."""
    out, prev = {}, float(base)
    for y, g in eq.groupby(eq.index.year):
        out[int(y)] = float(g.iloc[-1]) - prev
        prev = float(g.iloc[-1])
    return out


def yearly_sum_check(eq, base):
    """Format check: base + the sum of the yearly P&L = the end equity, in Decimal.

    Each float converts to Decimal exactly, so the sum telescopes exactly. It
    checks the yearly table is complete and anchored at the base; it cannot catch
    an engine error, which `engine_tests.py fixed_capital`'s trade-log reconciliation does."""
    with localcontext() as ctx:
        ctx.prec = 400          # wide enough that no float's exact value is rounded
        vals = [Decimal(float(base))]
        prev = Decimal(float(base))
        for _, g in eq.groupby(eq.index.year):
            last = Decimal(float(g.iloc[-1]))
            vals.append(last - prev)
            prev = last
        return sum(vals) == Decimal(float(eq.iloc[-1]))


def max_invested(rows, base):
    """(MaxInvested_base%, date) from audit["fixed"] rows, or (None, None)."""
    if not rows:
        return None, None
    best = max(rows, key=lambda r: r["held_after"])
    return best["held_after"] / base * 100, pd.Timestamp(best["date"])


def figures(eq, base, line, label, invested=(None, None), w0=None, w1=None):
    """One row of fixed-capital figures for an equity series."""
    eq = eq.astype(float)
    ny = years_of(eq)
    yp = yearly_pnl(eq, base)
    fy = full_years(eq.index, w0, w1)
    gap = eq - eq.cummax()
    i_dd = int(np.argmin(gap.to_numpy()))
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100
    mi, mi_d = invested
    row = {"Line": line, "Config": label,
           "AvgAnnRet%": round((float(eq.iloc[-1]) - base) / base / ny * 100, 2),
           "MeanFullYear%": (round(float(np.mean([yp[y] / base * 100 for y in fy])), 2)
                             if fy else None),
           "FullYears": " ".join(str(y) for y in fy),
           "MaxDD_Rs": round(float(gap.min()), 2),
           "MaxDD_base%": round(float(gap.min()) / base * 100, 2),
           "MaxDD_trough": str(eq.index[i_dd].date()),
           "MaxInvested_base%": None if mi is None else round(mi, 2),
           "MaxInvested_date": None if mi_d is None else str(mi_d.date()),
           CAGR_LABEL: round(cagr, 2),
           "Base": round(float(base), 2),
           "FinalEquity": round(float(eq.iloc[-1]), 2),
           "Years": round(ny, 4)}
    return row


def year_rows(eq, base, line, label):
    """One row per calendar year: rupee P&L and that as % of base."""
    return [{"Line": line, "Config": label, "Year": y, "PnL_Rs": round(v, 2),
             "Year%": round(v / base * 100, 2)}
            for y, v in yearly_pnl(eq.astype(float), base).items()]


def fixed_curve(values, reset_mask, base, prior=None):
    """A line's equity under min(base, equity), reset at the closes in reset_mask.

    `values` is the line's daily value series on the run's dates, any scale.
    `prior` is its value the session before the first date; None means the line
    starts at the first date with no return on it. Returns (equity, held value
    at each reset close before the reset, as a Series on the reset dates)."""
    v = values.astype(float).to_numpy()
    reset = np.asarray(reset_mask, dtype=bool)
    eq = np.empty(len(v))
    pre = {}
    held = float(base)
    cash = 0.0
    last = float(v[0] if prior is None else prior)
    for t in range(len(v)):
        held *= v[t] / last
        last = v[t]
        eq[t] = held + cash
        if reset[t]:
            pre[values.index[t]] = held
            held = min(float(base), eq[t])
            cash = eq[t] - held
    return pd.Series(eq, index=values.index), pd.Series(pre, dtype=float)


def grid_mask(dates, rebal):
    """The strategy's grid days: backtest_exposure decides on i % rebal == 0,
    except the last session, on which no order can fill."""
    n = len(dates)
    return [(i % rebal == 0 and i < n - 1) for i in range(n)]


def index_values(u, dates):
    """The universe's NSE price index close, forward-filled onto `dates`, or None."""
    import market_data
    import settings
    from pathlib import Path
    if getattr(u, "index_file", None) is None or not Path(u.index_file).exists():
        return None
    s = (market_data.read_price_csv(u.index_file)[["date", "close"]].dropna()
         .set_index("date")["close"].sort_index())
    ix = s.reindex(s.index.union(dates)).ffill().reindex(dates)
    return None if ix.isna().any() else ix.astype(float)


def benchmark_rows(bh, u, dates, base, rebal, w0=None, w1=None):
    """(figure rows, year rows, curves) for the basket and the index under the rule.

    `bh` is the run's compounded basket, base * cumprod(1 + daily mean return);
    its value the session before the window is the base."""
    mask = grid_mask(dates, rebal)
    rows, years, curves = [], [], {}
    lines = [(BASKET, "buy & hold equal-weight, fixed capital", bh, float(base))]
    ix = index_values(u, dates)
    if ix is not None:
        lines.append((INDEX, f"{getattr(u, 'index_name', 'index')} price index, fixed "
                             f"capital", ix, None))
    for line, label, ser, prior in lines:
        eq, pre = fixed_curve(ser, mask, base, prior)
        if len(pre):
            d = pre.idxmax()
            inv = (float(pre.max()) / base * 100, pd.Timestamp(d))
        else:
            inv = (None, None)
        rows.append(figures(eq, base, line, label, inv, w0, w1))
        years += year_rows(eq, base, line, label)
        curves[line] = eq
    return rows, years, curves


NOTES = (
    "Fixed capital: positions are sized from min(base, equity) at each rebalance "
    "open; profit above the base is held as idle cash at 0% and never used to buy; "
    "held names are not trimmed. CAGR understates such a run. The basket and the "
    "index are reset to min(base, equity) at the close of each of the strategy's "
    "grid days, one session before the strategy's own reset at the next open; the "
    "index is a price index without dividends.")


# ======================================================================================
# BUY-AND-HOLD HOLDINGS. From results/bh_held.py (moved 2026-11-27).
# ======================================================================================
# bh_held.py -- the investable buy & hold: equal-rupee lots bought once, never rebalanced.
#
# One construction, two endings, used by backtest_runs.py and by
# backtest_runs.run_arm so both report the same numbers:
#
#     headline      the lots are held to the end and marked to market. Nothing is
#                   sold, so no gain is realised, no capital-gains tax is due and no
#                   sell charge is paid. This is the taxed buy & hold's headline
#                   figure (owner's decision, 2026-09-25: no forced sale at the end,
#                   for the strategy or for buy & hold).
#     last_day      "sold on the last day": every lot is sold at the last session's
#                   open (its close where the open is missing) less slippage, the
#                   same calc_tc sell charge the strategy pays is deducted, and the
#                   realised gain is taxed with costs.tax_for_fy for the financial
#                   year of that session -- the document's netting and full annual
#                   exemption, nothing else.
#
# The purchase is the one backtest_runs.py has always made: every symbol priced
# on the first session gets an equal rupee share of START_CAPITAL, bought at that
# session's open plus slippage with the BUY charge. The untaxed published buy & hold
# (`px.pct_change().mean(axis=1)`, a costless daily-rebalanced index) is a different
# construction and stays the reference line.

def held_lots(px, op, bd):
    """-> dict(eq_headline, eq_last_day, detail) for the equal-rupee held basket."""
    d0, dN = bd[0], bd[-1]
    o0 = op.loc[d0]
    # THE BASKET: every name in static mode; in pit mode the members on d0, the
    # first pit rebalance (owner's decision, 2026-10-10).
    import market_data
    syms = [s for s in market_data.buyhold_columns(list(o0.index), d0, market_data.MEMBERSHIP)
            if not np.isnan(o0[s]) and o0[s] > 0]
    _cap0 = _capital_axis.selected()
    per = _cap0 / len(syms)
    shares, cash, buy_tc = {}, _cap0, 0.0
    for s in syms:
        pr = fill_price(o0[s], SLIPPAGE, True)
        q = int(per // pr)
        if q < 1:
            continue
        tc = calc_tc(pr, q, "BUY")
        if cash < q * pr + tc:
            continue
        cash -= q * pr + tc
        buy_tc += tc
        shares[s] = (q, pr)
    held = px.loc[bd, list(shares)].ffill()
    qty = np.array([shares[s][0] for s in shares], dtype=float)
    eq_headline = (held * qty).sum(axis=1) + cash

    # THE LAST-DAY SALE, at the last session's open with the usual slippage.
    gain = proceeds = sell_tc = 0.0
    oN = op.loc[dN]
    for s, (q, bp) in shares.items():
        pr = float(oN.get(s, np.nan))
        if np.isnan(pr) or pr <= 0:
            pr = float(px.loc[dN, s])
        pr = fill_price(pr, SLIPPAGE, False)
        proceeds += q * pr
        sell_tc += calc_tc(pr, q, "SELL")
        gain += q * (round(pr, 2) - round(bp, 2))   # section 3(C): price difference only
    held_days = (dN - d0).days
    fy = costs.financial_year(dN)
    reg = costs.regime_of(dN)
    b = dict.fromkeys(costs.BUCKETS, 0.0)
    b[("long_" if costs.is_long_term(d0, dN) else "short_") + reg] = gain
    tx = costs.tax_for_fy(fy, b)
    eq_last_day = eq_headline.copy()
    eq_last_day.iloc[-1] = cash + proceeds - sell_tc - tx["total_tax"]
    return {
        "eq_headline": eq_headline,
        "eq_last_day": eq_last_day,
        "shares": shares,
        "detail": dict(names=len(shares), held_days=held_days, fy=costs.fy_label(fy),
                       regime=reg, gain=gain, tax=tx["total_tax"],
                       exemption=tx["exemption"], residual_cash=cash,
                       proceeds=proceeds, sell_tc=sell_tc, buy_tc=buy_tc,
                       tax_row=tx),
    }


# ======================================================================================
# STEP: THE DAILY AUDIT TRAIL. From results/audit_step.py (moved 2026-11-27).
# ======================================================================================
# audit_step.py -- the daily audit trail, once, for any universe.
# ==============================================================
#
# WHAT THIS REPLACES
#     Three files carried this same ~60-line body: make_daily_audit.py (two retired universes),
#     make_mid_audit.py and make_n100_audit.py. The midcap150 and nifty100 pair were 98.4%
#     identical -- one differing code line each side -- and both were, by their own
#     docstrings, copies of the retired-universe script with the tail call changed.
#
#     Every difference between them turned out to be a universe property that
#     settings.py already records. Nothing needed inventing:
#
#         window          u.trading_days(index)   -- the retired pair cut by YEAR
#                                                    (2019..2026 / 2019..2025) and the
#                                                    live pair cut by DATE. Verified to
#                                                    reproduce all four exactly:
#                                                    1842 / 1732 / 1836 / 1836 days.
#         score panel     u.score_cache
#         output dir      u.metrics_dir
#         filename tag    u.tag
#
# SIZING IS AT THE DECISION CLOSE, WITH NO OPT-OUT
#     Since 2026-10-28 the engine sizes every buy from the book and the closes of the
#     decision session; it takes no switch for it. Before that it valued the book at
#     the fill session's open (value_at_open, removed), and the two deleted retired
#     universes once passed value_at_open=False.
#
#     That pin must stay in lockstep with engine_v2_final_*.py, because the SAFETY
#     check below compares this curve against v2FINAL_equity.csv and would fail if
#     only one side moved.
#
# THE ENTRY POINTS STAY SEPARATE, DELIBERATELY
#     main(u) below (results/make_audit.py until 2026-10-18) is the entry point, invoked once per universe by
#     its own PIPELINE_ORDER row, rather than one call covering every universe. check_pipeline_order.analyse keys its ordering dicts BY
#     SCRIPT NAME (`order = {scr: i ...}`), so three entries sharing one name collapse
#     to a single position and the 10c-before-10d ordering it exists to enforce becomes
#     invisible. Duplicating a name to save two files would disable a safety check to
#     tidy a directory listing.

warnings.filterwarnings("ignore")


def panel_path(u):
    """The score panel, through model.require_cache.

    Until 2026-09-23 this returned whichever copy existed WITHOUT checking what it
    was built from, so the audit was the one reader a stale panel passed
    silently. It now goes through the same content-key check as every other.
    """
    return model.require_cache(u.score_cache, what=f"{u.tag} score panel")


def prices(u):
    """(close, open, score, trading days) from the score panel, as run() replays them.
    make_daily_log reads the buy & hold's prices through this too."""
    p = read_table(panel_path(u), parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return px, op, sc, u.trading_days(px.index)


def artefact_tag(u, arm):
    """The filename tag for one (universe, arm, cadence) -- THE ONE DEFINITION.

    WHY THIS IS A FUNCTION AND NOT A LINE INSIDE run().
        It used to be two lines in run(), and run() is the WRITER. make_daily_log
        is a READER of the same files and had no way to ask for the rule, so it
        hardcoded the unsuffixed `daily_*_{u.tag}.csv` names instead and returned
        early whenever they did not exist -- which is every selection except v2 at
        the default cadence. A reader that reconstructs a writer's naming rule
        drifts from it the moment either changes. There is now one rule and both
        sides call it.

    v2 KEEPS THE UNSUFFIXED FILENAMES. nt_verify.py, nt_daily_compare.py and
    nt_holdings_compare.py read daily_summary_{tag}.csv, daily_holdings_{tag}.csv
    and daily_trades_{tag}.csv by those exact names, and they are the 92-of-92
    correctness gate. Suffixing v2 would break the gate that certifies the engine.
    DAILY_LOG_{tag}.txt inherits the same rule. Every other arm is suffixed.

    THE CADENCE JOINS THE FILENAME, empty at the default, so v2's unsuffixed names
    are untouched by a default run.

    `arm` may be an Arm or a bare name, because callers hold both.
    """
    import settings
    from settings import tax as _tax
    name = getattr(arm, "name", arm)
    tag = u.tag if name == "v2" else f"{u.tag}_{name}"
    # THE PROFILE JOINS THE TAG for the same reason the cadence does: a
    # profile="tradeable" run must not overwrite the research trail that the
    # Nautilus comparison scripts and the daily log read by name. Empty at the
    # default, so v2's unsuffixed names are untouched.
    # AND THE TAX AXIS, for the same reason again: a tax=on run must not
    # overwrite the trail the Nautilus comparison scripts and the daily log read
    # by name. Empty at tax=off, so the unsuffixed names are untouched.
    # AND THE SURVIVORSHIP AXIS, appended after tax: "" at static.
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    import settings
    return tag + cadence.suffix() + settings.profile_axis.suffix() + _tax.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix()


def _reference_curve(M, arm_name):
    """The engine's own recorded equity curve for this arm, or None.

    THE AUDIT IS A CHECK, NOT A DUMP, and this is what it checks against. The
    trail is produced by re-running the backtest with logging on; if that re-run
    disagreed with the curve the engine published, the trail would describe a
    portfolio nobody reported. So every arm's trail is reconciled against the
    engine's own number for that arm.

    TWO FILES, BECAUSE THE ENGINE WRITES TWO. v1 and v2 are the shipping strategy
    and its control and live in v2FINAL_equity.csv; v3 and v4 are measurement arms
    and live in v34_equity.csv. Both are written by the engine step that runs
    immediately before this one, so both are on disk by now.

    None means the engine did not record that arm on this run -- a frozen
    universe has no v3/v4 at all, and an arm-subset run has no file for an arm it
    did not measure. The caller reports that rather than asserting against nothing.
    """
    import portfolio as _ar
    # SPELLED `M / "..."`, NOT `Path(M) / "..."`. check_pipeline_order matches the
    # bare `<dir> / "<literal>"` shape; wrapping the directory in Path() made this
    # read invisible to the scanner and the edge vanished from its inventory.
    M = Path(M)
    # THE CADENCE-NAMED FILE FIRST. Under --rebal 40 the engine wrote
    # v2FINAL_equity_r40.csv and left the canonical cadence-20 file alone;
    # reconciling a cadence-40 trail against the cadence-20 curve reports a
    # MISMATCH of millions of rupees and refuses to write the trail. That is the
    # check working, but it is checking the wrong pair -- measured, before this
    # line existed: v1 MISMATCH Rs 2,923,934 and v2 MISMATCH Rs 1,825,210 on midcap150
    # at --rebal 40.
    #
    # AT A NON-DEFAULT CADENCE THERE IS NO FALLBACK TO THE UNSUFFIXED FILE.
    # Both chains used to end at one -- v2FINAL_equity.csv and v34_equity.csv --
    # which is a cadence-20 curve. Reaching either from a --rebal 200 run would
    # reconcile a cadence-200 trail against a cadence-20 curve: exactly the
    # mispairing measured above (v1 Rs 2,923,934, v2 Rs 1,825,210 on midcap150 at
    # --rebal 40). It failed safe only by accident, because backtest_runs.run()
    # happens to refuse a trail whose difference exceeds a paisa. Returning None
    # here makes it safe BY DESIGN: the caller reports that there is no reference
    # curve for this arm at this cadence and writes nothing.
    #
    # AT THE DEFAULT CADENCE NOTHING CHANGES, and provably so: cadence.suffix() is
    # "" there, so f"v2FINAL_equity{suffix}.csv" IS "v2FINAL_equity.csv" and
    # f"v34_equity{suffix}.csv" IS "v34_equity.csv". The removed lines were a
    # no-op at the default and a hazard everywhere else.
    # THE PROFILE SUFFIX JOINS THE CADENCE ONE. A profile="tradeable" run writes
    # v34_equity_tradeable.csv; resolving to the research curve here would report a
    # MISMATCH of the cap's whole effect and refuse to write the trail -- the same
    # class of mispairing as the cadence one above, with the same failure mode.
    import costs
    import settings
    # THE TAX SUFFIX JOINS THE OTHER TWO, 2026-09-18, and it is the same hazard a
    # third time. This expression was written 2026-09-10 (0ce8ed5) and the tax
    # axis landed 2026-09-17 (7846f67), so for as long as the axis has existed
    # this resolved to the UNSUFFIXED curve on a taxed run -- v2FINAL_equity.csv
    # rather than v2FINAL_equity_tax.csv. The comments above record the identical
    # mispairing being fixed for cadence and then for profile; nobody added the
    # fourth axis, and the reconciliation below therefore compared an untaxed
    # re-run against an untaxed curve left on disk by an EARLIER, DIFFERENT run
    # and reported MATCH. It could not fail.
    from settings import tax as _tax_axis
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    _cad = cadence.suffix() + settings.profile_axis.suffix() + _tax_axis.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix()
    # A STOP ARM'S CURVE IS IN THE COMPANION FILE, and only there.
    if arm_name in _ar.STOP_ARMS:
        g = M / f"v34_stop_equity{_ar.stop_selection_suffix()}{_cad}.csv"
        if g.exists():
            df = read_table(g, parse_dates=["date"]).set_index("date")
            col = _ar.STOP_ARMS[arm_name].equity_column
            if col in df.columns:
                return df[col]
        return None
    f = M / f"v2FINAL_equity{_cad}.csv"
    if f.exists():
        df = read_table(f, parse_dates=["date"]).set_index("date")
        s = _ar.equity_series(df, arm_name)
        if s is not None:
            return s
    _core = [n for n in _ar.selected_names() if n in _ar.ARMS]
    for name in (f"v34_equity{_ar.selection_suffix(_core)}{_cad}.csv",
                 f"v34_equity{_cad}.csv"):
        g = M / name
        if g.exists():
            df = read_table(g, parse_dates=["date"]).set_index("date")
            col = _ar.ARMS[arm_name].equity_column
            if col in df.columns:
                return df[col]
    return None


# naming: arm,cadence,profile via artefact_tag -- every daily_* artefact is
# artefact_tag() (backtest_runs.py), which appends cadence.suffix() and
# profiles.suffix(); the arm is in the tag body. nt_verify and make_daily_log
# read these by the same rule.
def run(u, arm=None):
    """Write the daily audit trail for one universe and one arm.

    arm=None means v2 -- the arm this step has always audited, and the one whose
    filenames the Nautilus verification reads. Passing None reproduces the old
    behaviour exactly, which is why every existing caller keeps working.

    FILENAMES. v2 writes the unsuffixed daily_*_{tag}.csv it always has, because
    nt_verify.py, nt_daily_compare.py and nt_holdings_compare.py read those exact
    names and they are the 92-of-92 correctness gate. Every other arm writes
    daily_*_{tag}_{arm}.csv. v2 is therefore NOT special-cased in what it
    measures, only in what its files are called -- and that is a compatibility
    fact about the Nautilus port, recorded here rather than inferred.
    """
    _hdr = u.tag if (arm is None or (arm.name if hasattr(arm, "name") else arm) == "v2") \
        else f"{u.tag} / {arm.name if hasattr(arm, 'name') else arm}"
    print(f"\n{'='*74}\n{_hdr} UNIVERSE\n{'='*74}")
    # THE TRAIL MUST BE PRODUCED UNDER THE SAME GUARD AS THE CURVE IT IS CHECKED
    # AGAINST. This step re-runs the backtest with logging on and reconciles the
    # result against the engine's published curve to within a paisa, refusing to
    # write anything if it disagrees. The engine loads the row rule (no trade in a
    # name on a session without a row); a trail built without it would differ by
    # every owed sale and refused buy, and this step would
    # correctly refuse to write -- so the audit would vanish for a reason that is
    # not a fault.
    import market_data
    market_data.set_tradeability(u)
    px, op, sc, bd = prices(u)
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1

    # THE ARM'S OWN PARAMETERS, not a hardcoded breadth/invvol pair. The default
    # is v2, which is the arm this step has always run, so mode and sizing below
    # are the same two values it always passed.
    _arm = arm_reg.ARMS["v2"] if arm is None else (
        arm if hasattr(arm, "name") else arm_reg.get(arm))
    audit = {"holdings": [], "summary": [], "trades": [],
             "ranking": [], "decisions": [], "skipped": [],
             # THE COST TRAIL for reports.py: every fill and every
             # day's cash at full precision. Recording only; the curve is unchanged.
             "costs": {"fills": [], "days": []}}
    # THE CAP AND THE DATA IT NEEDS, TOGETHER. This step passed
    # participation_cap() alone until 2026-09-15. backtest_exposure applies the cap
    # only where vol20 supplies a prior-20-session median, so a tradeable audit
    # replayed the RESEARCH strategy and reconciled it against the TRADEABLE curve:
    # "v1 MISMATCH Rs 3,851,027.09" on midcap150, which is the cap's whole effect to the
    # paisa. The trail was then refused -- correctly, for the wrong reason -- and
    # midcap150, the only universe where the cap binds, has never had a tradeable audit.
    #
    # THE SAME EXPRESSION THE ENGINES USE, deliberately. engine_v2_final_*.py and
    # backtest_runs.py build vol20 exactly this way; the audit must replay what the
    # engine ran, so it reads the volume from the same place by the same call
    # rather than by an equivalent-looking one.
    _capkw = costs.cap_kwargs(u)
    # THE RUN'S TAX SELECTION. The audit must replay what the engine ran, and
    # after 21c6624 the engine charges tax; an untaxed re-run would now differ
    # from the taxed curve by the whole tax effect and refuse to write the trail.
    from settings import tax as _tax_axis
    eq, tc, ntr, expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, audit=audit, **_arm.kwargs,
        tax_enabled=_tax_axis.selected(),
        # THE RUN'S CADENCE. A trail built at 20 while the engine ran at 40 would
        # fail the reconciliation below -- which is the check working, but the fix
        # is to audit the cadence that was actually run.
        rebal=cadence.selected(), **_capkw)

    # ---- SAFETY: does this match the official equity curve FOR THIS ARM? ----
    # The check is the point of the step. Auditing an arm against another arm's
    # curve would report MATCH only by accident, so the reference is looked up by
    # arm name -- v1/v2 from v2FINAL_equity.csv, v3/v4 from v34_equity.csv.
    M = Path(u.metrics_dir)
    _ref = _reference_curve(M, _arm.name)
    if _ref is None:
        # NOT AN ASSERTION FAILURE, AND NOT SILENT EITHER. It means the engine did
        # not record this arm on this run, so there is nothing to reconcile
        # against and writing an unchecked trail would be worse than writing none.
        print(f"  {u.tag}/{_arm.name}: the engine recorded no equity curve for this "
              f"arm, so its trail cannot be checked -- not written")
        return
    diff = float((eq - _ref.reindex(eq.index)).abs().max())
    status = "MATCH" if diff < 0.01 else f"*** MISMATCH Rs {diff:.2f} ***"
    print(f"  {_arm.name} equity vs the engine's recorded curve : {status}")
    if diff >= 0.01:
        print("  !! audit logging changed something -- do not go further")
        return

    # The naming rule lives in artefact_tag() above, so make_daily_log reads the
    # same files this writes instead of reconstructing the rule and drifting.
    tag = artefact_tag(u, _arm)
    # AN EMPTY TABLE KEEPS ITS HEADER. pd.DataFrame([]) has no columns and writes a
    # one-byte file that no reader can parse: a run with no skipped order (nifty500
    # v2 at cadence 30) failed in make_daily_log on exactly that. A non-empty table
    # is built exactly as before, so its file is unchanged.
    def _frame(rows, cols):
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)
    h = _frame(audit["holdings"], ["date", "symbol", "qty", "price", "value", "weight_pct"])
    s = pd.DataFrame(audit["summary"])
    t = _frame(audit["trades"], ["date", "action", "symbol", "qty", "price", "value", "tc"])
    # Only a trimmed buy has wanted_qty; written as a whole number, blank elsewhere.
    if "wanted_qty" in t.columns:
        t["wanted_qty"] = t["wanted_qty"].astype("Int64")
    h.to_csv(M / f"daily_holdings_{tag}.csv", index=False)
    s.to_csv(M / f"daily_summary_{tag}.csv", index=False)
    t.to_csv(M / f"daily_trades_{tag}.csv", index=False)
    rkdf = _frame(audit["ranking"], ["decided_on", "rank", "symbol", "score", "vol60",
                                     "target_wt_pct", "held_before", "action"])
    dcdf = pd.DataFrame(audit["decisions"])
    rkdf.to_csv(M / f"daily_ranking_{tag}.csv", index=False)
    dcdf.to_csv(M / f"daily_decisions_{tag}.csv", index=False)
    skdf = _frame(audit["skipped"], ["date", "side", "symbol", "reason", "detail"])
    skdf.to_csv(M / f"daily_skipped_{tag}.csv", index=False)
    # A STOP ARM'S EXITS, COOLDOWNS, WAITS AND RE-ENTRIES, one row per event.
    if _arm.stop is not None:
        stdf = pd.DataFrame(audit.get("stop_events", []),
                            columns=["date", "event", "state", "peak", "peak_date",
                                     "equity", "drawdown_pct", "breadth", "detail"])
        stdf.to_csv(M / f"daily_stop_events_{tag}.csv", index=False)
        print(f"  stop events: {len(stdf)} "
              f"({int((stdf['event'] == 'trigger').sum())} exits, "
              f"{int((stdf['event'] == 're-entry filled').sum())} re-entries)")
    # THE DRAWDOWN-LIMIT AXIS: one row per order and per fill. Only with --dd.
    if "dd_events" in audit:
        from portfolio import EVENT_COLUMNS
        dddf = pd.DataFrame(audit["dd_events"], columns=EVENT_COLUMNS)
        # naming: arm,cadence,profile,tax,survivorship,dd via artefact_tag -- `tag` is artefact_tag(u, _arm)
        dddf.to_csv(M / f"daily_dd_events_{tag}.csv", index=False)
        _d = audit["dd"]
        print(f"  drawdown limit {_d['limit_pct']:g}%: {_d['orders']} orders, worst close "
              f"drawdown {_d['worst_dd_pct']:.2f}% from the all-time peak, "
              + (f"limit breached by {_d['breach_points']:.2f} points"
                 if _d["breached"] else "limit not breached")
              + f", {_d['sessions_below_limit']} sessions below it, "
              f"{_d['days_at_floor']} days at the floor")
    if len(skdf):
        print(f"  SKIPPED orders: {len(skdf)}")
        print(skdf["reason"].value_counts().to_string().replace("\n", "\n    "))
    else:
        print("  SKIPPED orders: 0")
    print(f"  rebalance (decision) days: {len(dcdf)} | ranking rows: {len(rkdf):,}")
    # A cadence near or past the window length leaves one or two rebalances, and
    # the result is close to holding the first selection. Said once per arm.
    if len(dcdf) < 3:
        print(f"  WARNING: only {len(dcdf)} rebalance(s) in {len(s):,} trading days "
              f"at cadence {cadence.selected()}; this run is close to buy and hold "
              f"of the first selection")

    print(f"  trades logged : {len(t):,}   (engine reported {ntr:,})"
          f"   {'OK' if len(t)==ntr else '*** COUNT MISMATCH ***'}")
    print(f"  daily rows    : {len(s):,} days | holdings rows {len(h):,}")
    print(f"  avg stocks held: {s['n_stocks'].mean():.1f} | "
          f"avg cash {s['cash_pct'].mean():.1f}% | final Rs {s['total'].iloc[-1]:,.0f}")
    print(f"\n  saved -> daily_holdings_{tag}.csv / daily_summary_{tag}.csv / daily_trades_{tag}.csv")

    # CHARGES, SLIPPAGE AND TAX, reconciled to the paisa, for every run this step
    # audits. Raises reports.CostReconciliationError, naming the check, the
    # first day and the gap, and so fails the run, if any figure does not reconcile.
    import reports as cost_report
    from settings import capital_axis as _capital_axis
    cost_report.write(u, _arm, tag, audit, eq, tc, px, op, bd, float(_capital_axis.selected()),
                      settings.profile_axis.selected(), bool(_tax_axis.selected()), cadence.selected())

    print(f"\n  --- SAMPLE: latest day ({s['date'].iloc[-1].date()}) ---")
    last = h[h["date"] == h["date"].max()]
    print(last[["symbol", "qty", "price", "value", "weight_pct"]].to_string(index=False))
    r = s.iloc[-1]
    print(f"  cash Rs {r['cash']:,.0f} ({r['cash_pct']}%) | holdings Rs {r['mtm']:,.0f} "
          f"({r['invested_pct']}%) | TOTAL Rs {r['total']:,.0f}")


# ---------------------------------------------------------------------------
# THE PIPELINE STEP. Was results/make_audit.py until 2026-10-18 (last at aebf1da); this
# file is now the step itself, invoked once per universe by its PIPELINE_ORDER rows.
# ---------------------------------------------------------------------------
# make_audit.py -- the daily audit trail for one universe.
#
# THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
# make_mid_audit.py and make_n100_audit.py, which differed in nothing but the
# registry key they passed and the filenames their docstrings quoted. Step 4 of the
# collapse; the contract that made it possible is 5c636cf.
#
# The body lives once in backtest_runs.py, which took over from the three
# near-identical copies the merged files used to be among; every difference between
# those was a universe property settings.py already records.
#
# Outputs, per selected arm, named by backtest_runs.artefact_tag(u, arm) -- so the
# universe tag, the arm and the cadence/profile suffixes all come from the run's own
# axes and NO FILENAME IS WRITTEN HERE:
#
#   daily_holdings_<tag>.csv   every position, every day
#   daily_summary_<tag>.csv    cash / mtm / total, every day
#   daily_trades_<tag>.csv     every fill, with transaction cost
#   daily_ranking_<tag>.csv    the score ranking at each rebalance
#   daily_decisions_<tag>.csv  every rebalance: breadth, exposure, value, plan
#   daily_skipped_<tag>.csv    orders created but not filled, with the reason
#
# INVOKED TWICE PER FULL RUN, once per universe, from two PIPELINE_ORDER rows that
# keep their own labels -- STEP 10c for midcap150, STEP 10g for nifty100.
#
# THE PER-UNIVERSE REGISTRY SUBSCRIPT IS GONE, AND check_pipeline_order NO LONGER
# NEEDS IT. The merged files kept that literal deliberately: the scanner read it to
# resolve daily_*_{tag}.csv to a directory, and their comment said "a loop variable
# there matches nothing". The scanner now takes the universe from PIPELINE_ORDER's
# third field instead -- the declaration the literal was restating. Verified: the
# four `audit before chart` edges survive the merge.
#
# AND THIS DOCSTRING MUST NOT SPELL THAT SUBSCRIPT OUT. check_pipeline_order scans
# SOURCE TEXT, comments and docstrings included, so writing the literal here bound a
# phantom tag to BOTH pipeline rows: STEP 10g then saw two candidate directories,
# could not choose, and dropped nifty100's edges to unresolved. Prose about a name is
# indistinguishable from the name to a text scanner -- the same trap
# transitional_asserts_check.py hit when its own marker comment matched its regex.

def audit_step(u):
    """The step, as a function, so run.py can call it in process."""
    # ONE TRAIL PER SELECTED ARM. This step wrote exactly one, v2's, because
    # audit_step hardcoded breadth+invvol.
    #
    # A FROZEN UNIVERSE IS NOT REACHED FROM HERE. midcap150 and nifty100 are live; the retired
    # universes went through frozen/make_daily_audit.py, deliberately left on v2 only.
    for _a in arm_reg.selected():
        run(u, _a)


# ======================================================================================
# STEP: BUY-AND-HOLD LOTS AFTER TAX. From bh_lots_after_tax.py (moved 2026-11-27).
# ======================================================================================
# bh_lots_after_tax.py -- v2 after tax against a GENUINE buy & hold after tax.
#
#     ./venv/bin/python bh_lots_after_tax.py
#
# READ THE CONCENTRATION WARNING BEFORE QUOTING THE midcap150 NUMBERS. This script
# prints it; it is repeated here because a figure gets copied out of a terminal
# more often than a docstring gets read.
#
#     midcap150  bh_lots terminal value is 53.0% ONE NAME (AIIL, 956x over the window),
#          68.4% in three (AIIL, PATANJALI, LLOYDSME). The median name returns
#          3.45x. The midcap150 "benchmark" is therefore a single-stock bet wearing a
#          116-name basket's name, and the universe is SURVIVORSHIP_MODE=static --
#          today's MidCap150 members backfilled -- so AIIL is in the basket
#          PRECISELY BECAUSE it went up 956x. Buy-and-hold is the most
#          survivorship-exposed construction there is, and this is what that looks
#          like. midcap150's bh_lots CAGR is not an achievable return and the
#          v2-vs-midcap150 comparison must not be quoted as a strategy result.
#
#     nifty100 top name 8.1%, top three 18.8%, and bh_lots (23.97%) lands within 0.03
#          points of the published daily-rebalanced bh (24.00%). That comparison
#          is diversified and usable.
#
# WHAT IT MEASURES
#
# v2 after tax vs buy & hold after tax. bh_lots per Finding 1(a).
#
# bh_lots: equal-rupee across every symbol priced on the first session, NO
# rebalance, single realisation at BT_END_DATE. Same slippage and the same Zerodha
# charge engine as v2, so the two lines differ in strategy and tax treatment and in
# nothing else. The published `bh` line -- px.pct_change().mean(axis=1).cumprod() --
# is a DAILY-REBALANCED costless index and is reported alongside for reference
# only; it is a different construction and is never substituted for.

for v in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS",
          "VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"): os.environ[v]="1"
os.environ["PYTHONHASHSEED"]="0"
HALVES=[("2019-2022",2019,2022),("2023-2026",2023,2026)]

# ---------------------------------------------------------------------------
# THE CONCENTRATION LIMIT, AND WHY IT IS 11.62% AND NOT A ROUND NUMBER
# ---------------------------------------------------------------------------
# A benchmark is an INSTRUMENT. It can only resolve an effect larger than its own
# sensitivity to a single input. The effect this benchmark exists to measure is
# the after-tax edge swing -- MEASURED at -2.05 CAGR points on nifty100 (3f0ef05):
# v2 loses 3.77 points to tax, a held-lots buy & hold loses 1.72, and the 2.05
# between them is the turnover cost. If dropping ONE NAME from the basket moves
# the benchmark's CAGR by more than that, the instrument cannot see the effect,
# and any edge printed against it is noise wearing a decimal point.
#
# So the limit is the top-name weight at which a single name's removal would move
# the benchmark CAGR by exactly the effect size:
#
#     drop a name of weight w  ->  terminal multiple M becomes M(1-w)
#     dCAGR = (1 + CAGR) * [ (1-w)^(1/y) - 1 ]
#     set dCAGR = -0.0205, solve for w:
#         w_max = 1 - [ 1 - 0.0205/(1+CAGR) ]^y
#
# Evaluated on the two universes actually measured, over the 2,705-day window:
#
#     nifty100   CAGR 23.97%   ->  w_max 11.62%
#     midcap150  CAGR 44.34%   ->  w_max 10.05%
#
# THE LIMIT TAKES THE MORE PERMISSIVE OF THE TWO, 11.62%, ON PURPOSE. Taking the
# tighter one would be choosing the number that rejects midcap150 most comfortably,
# which is tuning a test to a verdict already known. The looser bound still
# rejects midcap150 by a factor of 4.6 and still admits nifty100 with 3.5 points of
# margin, so the conclusion does not depend on which of the two was used -- and that
# insensitivity is the reason it can be stated as a choice rather than a fit.
#
# WHAT IT DOES NOT CLAIM. Passing does not make a basket well-diversified: nifty100's
# top name at 8.1% still moves the benchmark CAGR by -1.41 points, which is most
# of the effect being measured. It is a floor on usability, not a certificate.
# The number is pinned to a 7.4-year window and to these CAGRs; a materially
# different window needs it recomputed, not carried over.
CONC_LIMIT = 0.1162
CONC_LIMIT_BASIS = ("2.05-point effect size (nifty100 after-tax edge swing, 3f0ef05) "
                    "over a 2,705-day window at 23.97% CAGR")

def cagr(s):
    y=(s.index[-1]-s.index[0]).days/365.25
    return ((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100

def bh_lots(px,op,bd):
    """-> (headline equity, last-day tax row, detail). Thin wrapper over
    results/bh_held.held_lots, kept so the name and its callers survive.

    SINCE 2026-09-25 the headline is held to the end and never sold, so it pays
    no tax and no sell charge; the "sold on the last day" curve and its tax are
    in detail["eq_last_day"] and the returned tax row."""
    r=held_lots(px,op,bd)
    globals()["_SH"]=r["shares"]
    det=dict(r["detail"]); det["eq_last_day"]=r["eq_last_day"]
    return r["eq_headline"],det.pop("tax_row"),det


# EVERYTHING BELOW RAN AT IMPORT UNTIL 2026-09-18, AND THAT WAS A DEFECT RATHER
# THAN A STYLE. This loop calls model.require_cache() on EVERY registered
# universe, so the module could only be imported on a machine where every
# universe had already been run. Registering midcap50 -- a universe this file has
# nothing to say about, and which it would have reported on for the first time
# only after a full run -- made `import bh_lots_after_tax` raise
# FileNotFoundError, and check_all.py GATE 1 went red on a wiring commit that had
# not touched this file.
#
# A MODULE THAT READS CACHES AT IMPORT BREAKS EVERY TIME A UNIVERSE IS
# REGISTERED. The failure is not about the new universe and cannot be fixed by
# anything done to it: running the pipeline hides this once, and listing the
# module as known-unimportable green-washes the gate and then fails the day the
# run happens. Moving the work behind the guard is what stops it recurring, and
# it is why this fires for the last time here.
#
# Nothing imports this module -- checked 2026-09-18 across the repository -- so
# the move costs no caller. `./venv/bin/python bh_lots_after_tax.py` behaves
# exactly as before.
def bh_lots_after_tax(u):
    """One universe's after-tax comparison, and the artefact STEP 18 reads.

    ARITY 1, LIKE tax_report's. This looped REGISTRY internally until 2026-09-19,
    which was fine for a script run by hand and wrong for a PIPELINE_ORDER row:
    a whole-run step would put run.py:_resolve_arity in the position of refusing a
    None tag, and check_plan_order could not see that STEP 18 depends on THIS
    universe's file rather than on the loop having happened.

    IT WRITES BH_LOTS_<tag>_tax.csv, which is the whole reason it is a step.
    tax_report composes TAX_TURNOVER from this plus its own FY_EQUITY, so the
    buy&hold side of that comparison comes from a REAL RUN rather than from an
    untaxed log with arithmetic applied -- tax_report.py:22 records that the
    implied and charged figures differ by about 4% and that "the implied one
    describes a run that did not happen".

    THE EARLY RETURN IS THE tax=off CONTRACT, the same one tax_report uses: the
    row is always in PIPELINE_ORDER and always invoked, and decides at run time
    to do nothing. The artefact is ABSENT at tax=off, not empty.
    """
    from settings import tax as _tax
    if not _tax.selected():
        print(f"    tax=off -- no bh_lots artefact for {u.tag} "
              f"(absent, not empty)")
        return
    tag = u.tag
    # EVERY SELECTED ARM, SINCE 2026-09-26. This compared v2 alone. Each arm now
    # gets the same three backtests and its own BH_LOTS_<artefact_tag>.csv; the
    # buy & hold rows are the same basket in every arm's file. v2 keeps its row
    # labels ("v2 after tax" and so on), which after_tax_noise.published and
    # tax_report read by name; the other arms' rows carry their own name.
    import portfolio as arm_reg
    for arm in arm_reg.selected():
        an = arm.name
        print("="*96)
        print(f" {an} AFTER TAX vs BUY & HOLD AFTER TAX   (bh_lots: equal-rupee once, "
              "no rebalance, held to the end)")
        print("="*96)
        market_data.set_tradeability(u)
        p=read_table(model.require_cache(u.score_cache,what=tag),parse_dates=["date"])
        px=p.pivot_table(index="date",columns="symbol",values="close").ffill()
        op=p.pivot_table(index="date",columns="symbol",values="open").ffill()
        sc=p.pivot_table(index="date",columns="symbol",values="score")
        pc=precompute(px); mom20=px/px.shift(20)-1
        bd=u.trading_days(px.index)   # the universe's window; see engine_v2_final
        kw=dict(rebal=cadence.selected(),
                **arm.kwargs,**costs.cap_kwargs(u))
        v2_off,_,_,_=backtest_exposure(px,op,sc,bd,pc,mom20,audit=None,tax_enabled=False,**kw)
        a={k:[] for k in ("holdings","summary","trades","ranking","decisions","skipped")}
        v2_on ,_,_,_=backtest_exposure(px,op,sc,bd,pc,mom20,audit=a,tax_enabled=True,**kw)
        a2={k:[] for k in ("holdings","summary","trades","ranking","decisions","skipped")}
        v2_last,_,_,_=backtest_exposure(px,op,sc,bd,pc,mom20,audit=a2,tax_enabled=True,
                                        end_sale=True,**kw)
        stmt,_=costs.liability_schedule(a["tax"]["lots"],bd)

        bh_eq,bh_tx,det=bh_lots(px,op,bd)
        bh_last=det["eq_last_day"]
        # The basket: every name in static mode, the members on bd[0] in pit mode.
        bh_pub=capital_axis.selected()*(1+market_data.buyhold_prices(px,bd[0],market_data.MEMBERSHIP)
                              .pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

        # SINCE 2026-09-25 NOTHING IS SETTLED HERE. The engine settles the last,
        # partial financial year in-loop on the final session (costs.Ledger
        # .due_on), so v2_on is already after all tax on what it realised. The
        # headline sells nothing at the end, for either line; the "sold on the
        # last day" lines sell everything, pay the sell charges and are taxed.
        v2_settled=v2_on
        bh_settled=bh_eq

        print(f"\n{'-'*96}\n {tag.upper()} {an}   {bd[0].date()} .. {bd[-1].date()}   {len(bd):,} sessions")
        print(f"{'-'*96}")
        print(f"  bh_lots construction: {det['names']} names, equal-rupee, held {det['held_days']:,} days "
              f"({det['held_days']/365.25:.1f}y) -> LONG term")
        print(f"      single realisation in {det['fy']}, regime '{det['regime']}', gain Rs {det['gain']:,.0f}, "
              f"exemption Rs {det['exemption']:,.0f}")
        print(f"      if sold on the last day: LTCG due Rs {det['tax']:,.0f}   (rate "
              f"{costs.LTCG_RATE[det['regime']]*100:g}%), sell charges Rs {det['sell_tc']:,.0f}; "
              f"headline sells nothing and pays neither")

        # THE LABELS SAY *WHEN*, NOT ONLY *WHETHER*. "after tax (settled)" was true
        # but silent on the thing that separates the two lines: v2 paid across the
        # window and lost the use of that capital; bh_lots pays once, at the end.
        _nded=int(stmt["assessed"].sum())
        # THE LABELS ARE BOUND ONCE AND REUSED as the res{} keys below. Repeating the
        # literal at the lookup is what broke when the wording changed.
        L_V2_POST=f"{an}  after tax  ({_nded} deductions in-loop, last FY settled at end)"
        L_BH_POST="bh_lots after tax  (held to the end, nothing realised, nil tax)"
        L_V2_LAST=f"{an}  sold on the last day, after tax"
        L_BH_LAST="bh_lots sold on the last day, after sell charges and tax"
        L_V2_PRE=f"{an}  before tax"; L_BH_PRE="bh_lots before tax"
        L_BH_PUB="bh published (costless, daily-rebal)"
        rows=[(L_V2_PRE,v2_off),(L_V2_POST,v2_settled),(L_V2_LAST,v2_last),
              (L_BH_PRE,bh_eq),(L_BH_POST,bh_settled),(L_BH_LAST,bh_last),
              (L_BH_PUB,bh_pub)]
        print(f"\n  WHEN THE TAX LEFT CASH -- the two lines are not comparable along the path")
        print(f"      {an}       headline  Rs {a['tax']['cum_tax']:>12,.0f}"
              f"      sold on the last day  Rs {a2['tax']['cum_tax']:>12,.0f}")
        print(f"      bh_lots  headline  Rs {0:>12,.0f}"
              f"      sold on the last day  Rs {bh_tx['total_tax']:>12,.0f}")
        print(f"\n  {'line':<66}{'FULL':>10}{'2019-2022':>12}{'2023-2026':>12}   final equity")
        res={}
        for lab,s in rows:
            full=cagr(s); res[lab]=full
            h=[cagr(s[(s.index.year>=y0)&(s.index.year<=y1)]) for _,y0,y1 in HALVES]
            print(f"  {lab:<66}{full:>9.2f}%{h[0]:>11.2f}%{h[1]:>11.2f}%   {s.iloc[-1]:>14,.0f}")
        print()
        for _l in (
          f"  {an}'s capital-gains tax leaves cash on the first trading day at or after 31",
          "  March of each financial year, and the last, partial year is settled on the",
          "  final session. bh_lots never sells in the headline, so it realises nothing and",
          "  pays no tax; that deferral is what a book that never trades earns. The 'sold on",
          "  the last day' lines sell everything on the final session, pay the same sell",
          "  charges and are taxed under the same rules."):
            print(_l)
        e_pre =res[L_V2_PRE]-res[L_BH_PRE]
        e_post=res[L_V2_POST]-res[L_BH_POST]
        e_last=res[L_V2_LAST]-res[L_BH_LAST]
        e_pub =res[L_V2_PRE]-res[L_BH_PUB]
        # THE GATE. A concentrated basket does not get to print an edge at all.
        # Annotating the number was not enough: a figure gets copied out of a
        # terminal far more often than the caveat beside it does, and this file's own
        # docstring says so. So the number is WITHHELD and the reason takes its place.
        _v={s_:q*float(px.loc[bd[-1],s_]) for s_,(q,_b) in _SH.items()}
        _t=sum(_v.values()); _top=sorted(_v.items(),key=lambda x:-x[1])
        _w=_top[0][1]/_t
        _yrs=(bd[-1]-bd[0]).days/365.25
        _impact=(1+res[L_BH_PRE]/100)*((1-_w)**(1/_yrs)-1)*100
        # WHAT A NAME AT THE LIMIT WOULD MOVE THIS BASKET BY, the run's own yardstick.
        # The withheld reason quoted a fixed "effect size of 2.05", nifty100's swing
        # at 3f0ef05, on every universe and run. This run's own swing is the
        # withheld TAX_COST_OF_TURNOVER, so it cannot be the yardstick either.
        _lim_impact=(1+res[L_BH_PRE]/100)*((1-CONC_LIMIT)**(1/_yrs)-1)*100
        print(f"\n  bh_lots concentration: top name {_top[0][0]} = {_w*100:.1f}% of terminal "
              f"value, top 3 = {sum(v for _,v in _top[:3])/_t*100:.1f}%")
        print(f"      dropping that one name would move the benchmark CAGR by "
              f"{_impact:+.2f} pts   (limit {CONC_LIMIT*100:.2f}%)")
        if _w > CONC_LIMIT:
            print(f"\n  EDGE  ** WITHHELD **  top-name weight {_w*100:.1f}% exceeds the "
                  f"{CONC_LIMIT*100:.2f}% limit by {_w/CONC_LIMIT:.1f}x.")
            print(f"        This basket cannot resolve the effect it is being asked to")
            print(f"        measure: one name moves it {abs(_impact):.2f} pts, where a name at the")
            print(f"        limit would move it {abs(_lim_impact):.2f}. The universe is")
            print(f"        SURVIVORSHIP_MODE=static -- today's members backfilled -- so")
            print(f"        {_top[0][0]} is in this basket because of the")
            print(f"        run it had. Any edge printed here would be that one name's history.")
            print(f"        Limit basis: {CONC_LIMIT_BASIS}.")
        else:
            print(f"\n  EDGE  {an} - bh_lots   before tax {e_pre:+.2f} pts      after tax {e_post:+.2f} pts"
                  f"      swing {e_post-e_pre:+.2f}      sold on the last day {e_last:+.2f} pts")
        print(f"  EDGE  {an} - bh published {e_pub:+.2f} pts"
              f"   [costless daily-rebalanced index, untaxable -- reference only]")

        # ------------------------------------------------------------------
        # THE ARTEFACT. Five measured lines plus the three gap rows, which is
        # what this whole axis exists to produce.
        # ------------------------------------------------------------------
        # WITHHELD IS A ROW, NOT A MISSING ROW. The guard above refuses to PRINT
        # a number a concentrated basket cannot resolve; the file records the
        # refusal in its own column rather than omitting the line, because an
        # absent row reads as "not computed" and this was computed and rejected.
        # The step does NOT fail: a withheld edge is a correct outcome.
        _withheld = _w > CONC_LIMIT
        _reason = ("" if not _withheld else
                   f"top-name weight {_w*100:.1f}% exceeds the {CONC_LIMIT*100:.2f}% "
                   f"limit by {_w/CONC_LIMIT:.1f}x; {_top[0][0]} alone moves the "
                   f"benchmark {_impact:+.2f} pts, where a name at the limit would move "
                   f"it {_lim_impact:+.2f} pts, "
                   f"and the universe is SURVIVORSHIP_MODE=static so that name is "
                   f"in the basket because of the run it had")
        _lines = [
            (f"{an} before tax",             L_V2_PRE,  v2_off,      0.0),
            (f"{an} after tax",              L_V2_POST, v2_settled,  float(a["tax"]["cum_tax"])),
            (f"{an} sold on the last day",   L_V2_LAST, v2_last,     float(a2["tax"]["cum_tax"])),
            ("bh_lots before tax",           L_BH_PRE,  bh_eq,       0.0),
            ("bh_lots after tax",            L_BH_POST, bh_settled,  0.0),
            ("bh_lots sold on the last day", L_BH_LAST, bh_last,     float(bh_tx["total_tax"])),
            ("bh published",                 L_BH_PUB,  bh_pub,      float("nan")),
        ]
        _out = []
        for _key, _lab, _s, _paid in _lines:
            _h = [cagr(_s[(_s.index.year >= y0) & (_s.index.year <= y1)])
                  for _, y0, y1 in HALVES]
            _out.append({"line": _key, "cagr_full": round(res[_lab], 4),
                         "cagr_2019_2022": round(_h[0], 4),
                         "cagr_2023_2026": round(_h[1], 4),
                         "final_equity": round(float(_s.iloc[-1]), 2),
                         "tax_paid": ("" if _paid != _paid else round(_paid, 2)),
                         "withheld_reason": ""})
        _out.append({"line": "gap_before_tax", "cagr_full": round(e_pre, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "", "withheld_reason": ""})
        _out.append({"line": "gap_after_tax", "cagr_full": round(e_post, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "", "withheld_reason": ""})
        _out.append({"line": "gap_sold_on_the_last_day", "cagr_full": round(e_last, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "", "withheld_reason": ""})
        _out.append({"line": "TAX_COST_OF_TURNOVER",
                     "cagr_full": "" if _withheld else round(e_post - e_pre, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "",
                     "withheld_reason": _reason})
        _atag = artefact_tag(u, arm)
        _p = Path(u.metrics_dir) / f"BH_LOTS_{_atag}.csv"
        # naming: arm,cadence,profile,tax via artefact_tag -- `_atag` is
        # backtest_runs.artefact_tag's output and already carries all four axes, so
        # the stem is appended and NOTHING else. Same rule, and the same reason,
        # as reports.py's four artefacts: this file exists only under tax=on.
        pd.DataFrame(_out).to_csv(_p, index=False)
        print(f"\n  saved -> {_p.name}"
              + ("   [TAX_COST_OF_TURNOVER withheld]" if _withheld else ""))
