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
  === 58 UNIVERSE ===
  1.  build_scores       -> 58 scores (SLOW ~40-65min)
  2.  engine_core        -> v1 + validation + leakage checks
  3.  engine_v2_final    -> v2 FINAL (breadth)
  4.  diagnose_decay     -> period breakdown
  5.  validate_breadth   -> breadth robustness
  6.  reality_check      -> real-money P&L, hit rate
  7.  per-stock charts (58)
  === 74 UNIVERSE ===
  8.  build_scores74     -> 74 scores (SLOW ~27min)
  9.  engine_v2_final74  -> 74 v2 FINAL
  === MIDCAP150 UNIVERSE (third universe) ===
  build_scores_mid   -> MidCap150 scores (SLOW)
  engine_v2_final_mid-> MidCap150 v2 FINAL
  make_mid_audit     -> MidCap150 daily audit CSVs
  make_mid_chart     -> MidCap150 chart + cap-weighted index benchmark
  === BENCHMARK + FINAL ===
  11. make_cash_series      -> cash series (58 + 74)
  12. make_daily_audit      -> 58/74 daily audit CSVs  <- MUST precede step 13
  13. make_final_chart_fair -> Nifty100 benchmark + final 3-panel chart + fair table
  14. make_final_summary    -> FINAL summary table
  15. make_daily_log        -> forensic daily text log
  16. nt_export_scores      -> Nautilus score parquets

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
# NOT COVERED: a step run STANDALONE (`python3 results/build_scores_n100.py`)
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
F = ROOT / "frozen"

# FROZEN-WRITE OVERRIDE. The retired 58/74 scripts in frozen/ refuse to run unless
# this is set, because results*/metrics/ is gitignored and a stray standalone run
# overwrites a published artefact with no way back. A full pipeline run IS the
# sanctioned way to regenerate them, so it says so once here -- before main()
# spawns anything, and a child inherits os.environ at spawn.
# See frozen/_frozen_guard.py.
import os
os.environ["ALLOW_FROZEN_WRITE"] = "1"

# The retired 58/74 pipeline lives in frozen/, not results/. The split is by
# UNIVERSE, not by kind: every script here serves only the 58 or the 74 and
# carries a FROZEN marker. Shared libraries (engine_core, test_exposure,
# v34_common, survivorship, qbeast_in_charges) stay in results/ because the LIVE
# universes import them.
FROZEN_SCRIPTS = {
    "build_scores.py", "build_scores74.py",
    "engine_v2_final.py", "engine_v2_final74.py",
    "make_daily_audit.py", "make_cash_series.py",
    "make_combined_all.py", "make_stock_chart.py",
    "make_per_stock_charts.py", "validate_breadth.py",
}


# STEP 16 lives in nautilus/, not results/. Listing it by bare name meant the static
# checker resolved it to results/nt_export_scores.py, found nothing, and SILENTLY
# SKIPPED IT -- it had never been covered by the ordering check. Found 2026-09-04 when
# the checker was taught to report what it could not resolve.
NAUTILUS_SCRIPTS = {"nt_export_scores.py"}

# A step whose body lives in a shared helper must be scanned WITH that helper, or
# the static ordering check loses the edges the helper writes. results/audit_step.py
# holds the one audit implementation the three per-universe entry points call.
STEP_HELPERS = {
    "make_daily_audit.py":   (R / "audit_step.py",),
    "make_mid_audit.py":     (R / "audit_step.py",),
    "make_n100_audit.py":    (R / "audit_step.py",),
    "build_scores.py":       (R / "build_scores_step.py",),
    "build_scores74.py":     (R / "build_scores_step.py",),
    "build_scores_mid.py":   (R / "build_scores_step.py",),
    "build_scores_n100.py":  (R / "build_scores_step.py",),
}


def script_path(script):
    """Where a pipeline step actually lives. One definition, used by run() and
    by the static ordering check, so the two cannot disagree about a step's
    location -- a disagreement would make check_pipeline_order silently skip a
    file it could not find rather than fail."""
    q = Path(script)
    if q.is_absolute():
        return q
    if q.name in FROZEN_SCRIPTS:
        return F / q.name
    if q.name in NAUTILUS_SCRIPTS:
        return ROOT / "nautilus" / q.name
    return R / q.name
TMP = Path("/tmp")
FRESH = "--fresh" in sys.argv

# caches: both /tmp and the permanent copies
CACHE_TMP = [TMP / "v5_expanding.csv", TMP / "raw_panel_20.csv",
             TMP / "v74_expanding.csv", TMP / "raw_panel74_20.csv",
             TMP / "v_mid_expanding.csv", TMP / "raw_panel_mid_20.csv",
             TMP / "v_n100_expanding.csv", TMP / "raw_panel_n100_20.csv"] + \
            [TMP / f"FINAL_seed{i}.csv" for i in range(3)] + \
            [TMP / f"breadth_seed{i}.csv" for i in range(3)] + \
            [TMP / f"prune_{t}.csv" for t in ("all", "pruned", "random")]
CACHE_PERM = [R / "metrics" / "v5_expanding_cache.csv",
              R / "metrics" / "raw_panel_cache.csv",
              ROOT / "results74" / "metrics" / "v74_expanding_cache.csv",
              ROOT / "results74" / "metrics" / "raw_panel74_cache.csv",
              ROOT / "results_mid" / "metrics" / "v_mid_expanding_cache.csv",
              ROOT / "results_mid" / "metrics" / "raw_panel_mid_cache.csv",
              ROOT / "results_n100" / "metrics" / "v_n100_expanding_cache.csv",
              ROOT / "results_n100" / "metrics" / "raw_panel_n100_cache.csv"]

# ---------------------------------------------------------------------------
# INPUT GUARD -- ordering bugs must fail by name, not as a pandas traceback
# ---------------------------------------------------------------------------
# Every entry is: consumer script -> [(file it reads, the step that writes it)].
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
REQUIRED_INPUTS = {
    "make_final_chart_fair.py": [
        (R / "metrics" / "daily_trades_58.csv",
         "STEP 12 make_daily_audit.py (tag 58)"),
        (ROOT / "results74" / "metrics" / "daily_trades_74.csv",
         "STEP 12 make_daily_audit.py (tag 74)"),
        (R / "metrics" / "daily_trades_v1_58.csv",
         "STEP 3 engine_v2_final.py"),
        (ROOT / "results74" / "metrics" / "daily_trades_v1_74.csv",
         "STEP 9 engine_v2_final74.py"),
        (R / "metrics" / "cash_series_58.csv", "STEP 11 make_cash_series.py"),
        (ROOT / "results74" / "metrics" / "cash_series_74.csv",
         "STEP 11 make_cash_series.py"),
    ],
    "make_mid_chart.py": [
        # ARM-TAGGED TOO: this is v2's audit trail, and a selection without v2
        # writes no v2 trail at all. Demanding it unconditionally made `--arm
        # v1,v3` impossible from a cold tree; it only ever passed because an
        # earlier default run had left the file on disk.
        (ROOT / "results_mid" / "metrics" / "daily_trades_mid.csv",
         "STEP 10c make_mid_audit.py", "v2"),
        # ARM-TAGGED. This input exists only when v1 is selected, so check_inputs
        # skips it otherwise. The tuple stays a literal path in the same shape, so
        # check_pipeline_order still resolves the edge and its inventory is
        # unchanged -- only the RUNTIME requirement became conditional.
        (ROOT / "results_mid" / "metrics" / "daily_trades_v1_mid.csv",
         "STEP 10b engine_v2_final_mid.py", "v1"),
    ],
    "make_n100_chart.py": [
        # ARM-TAGGED TOO: this is v2's audit trail, and a selection without v2
        # writes no v2 trail at all. Demanding it unconditionally made `--arm
        # v1,v3` impossible from a cold tree; it only ever passed because an
        # earlier default run had left the file on disk.
        (ROOT / "results_n100" / "metrics" / "daily_trades_n100.csv",
         "STEP 10g make_n100_audit.py", "v2"),
        # ARM-TAGGED. This input exists only when v1 is selected, so check_inputs
        # skips it otherwise. The tuple stays a literal path in the same shape, so
        # check_pipeline_order still resolves the edge and its inventory is
        # unchanged -- only the RUNTIME requirement became conditional.
        (ROOT / "results_n100" / "metrics" / "daily_trades_v1_n100.csv",
         "STEP 10f engine_v2_final_n100.py", "v1"),
    ],
    # THE COMBINED STEP READS EVERY SELECTED UNIVERSE'S TRADE LOG, and the two
    # retired universes' logs are written by STEP 12 make_daily_audit.py. That is
    # why this step moved from STEP 10i to STEP 12b: at 10i the 58 and 74 logs did
    # not exist yet, so a combined chart over those universes could not have been
    # drawn at all. The mid and n100 edges are declared because a full run always
    # has both; the 58/74 edges are NOT declared here because those universes can
    # legitimately be absent from a selection, and check_inputs is a hard failure.
    "make_combined_universes.py": [
        # ARM-TAGGED TOO: this is v2's audit trail, and a selection without v2
        # writes no v2 trail at all. Demanding it unconditionally made `--arm
        # v1,v3` impossible from a cold tree; it only ever passed because an
        # earlier default run had left the file on disk.
        (ROOT / "results_mid" / "metrics" / "daily_trades_mid.csv",
         "STEP 10c make_mid_audit.py", "v2"),
        # ARM-TAGGED TOO: this is v2's audit trail, and a selection without v2
        # writes no v2 trail at all. Demanding it unconditionally made `--arm
        # v1,v3` impossible from a cold tree; it only ever passed because an
        # earlier default run had left the file on disk.
        (ROOT / "results_n100" / "metrics" / "daily_trades_n100.csv",
         "STEP 10g make_n100_audit.py", "v2"),
    ],
    "make_final_summary.py": [
        (R / "metrics" / "fair_comparison_table.csv",
         "STEP 13 make_final_chart_fair.py"),
    ],
    # STEP 16 reads the PERMANENT panels, which STEP 15b copies from /tmp. Named
    # here so that if the two are ever re-ordered again the run stops with the
    # missing filename and the step that owes it, instead of dying inside pandas
    # with "v5_expanding_cache.csv missing" and no indication of who writes it.
    # nt_export_scores also falls back to /tmp via config.require_cache, so this
    # fires only when BOTH copies are absent -- a genuine missing panel.
    # UNIVERSE-TAGGED. The third field is the ARM an input belongs to; a leading
    # "u:" marks a UNIVERSE instead. Each cache exists only when its universe was
    # selected, so `--universe mid` from a cold tree has one of these four and not
    # the other three -- and demanding all four made that selection impossible
    # from cold. It only ever passed because an earlier full run had left them.
    "nt_export_scores.py": [
        (R / "metrics" / "v5_expanding_cache.csv",
         "STEP 15b save_caches_step.py", "u:58"),
        (ROOT / "results74" / "metrics" / "v74_expanding_cache.csv",
         "STEP 15b save_caches_step.py", "u:74"),
        (ROOT / "results_mid" / "metrics" / "v_mid_expanding_cache.csv",
         "STEP 15b save_caches_step.py", "u:mid"),
        (ROOT / "results_n100" / "metrics" / "v_n100_expanding_cache.csv",
         "STEP 15b save_caches_step.py", "u:n100"),
    ],
}


# Execution order, declared once so the static checker can read it. run() asserts
# every script it is handed appears here, so this list cannot silently drift out of
# step with main(). Steps 1/8/10a/10e are skipped at runtime when their panel is
# cached; that does not change the ORDER, which is what the checker reasons about.
PIPELINE_ORDER = [
    ("STEP 0", "make_trading_calendar.py"),
    ("STEP 1", "build_scores.py"),
    ("STEP 2", "engine_core.py"),
    ("STEP 3", "engine_v2_final.py"),
    ("STEP 4", "diagnose_decay.py"),
    ("STEP 5", "validate_breadth.py"),
    ("STEP 6", "reality_check.py"),
    ("STEP 7", "make_per_stock_charts.py"),
    ("STEP 7b", "make_combined_all.py"),
    ("STEP 7c", "make_final_table.py"),
    ("STEP 7d", "make_charts.py"),
    ("STEP 7e", "make_stock_chart.py"),
    ("STEP 7f", "make_combined_portfolio.py"),
    ("STEP 7g", "export_feature_docs.py"),
    ("STEP 8", "build_scores74.py"),
    ("STEP 9", "engine_v2_final74.py"),
    ("STEP 10a", "build_scores_mid.py"),
    ("STEP 10b", "engine_v2_final_mid.py"),
    ("STEP 10c", "make_mid_audit.py"),
    ("STEP 10d", "make_mid_chart.py"),
    ("STEP 10e", "build_scores_n100.py"),
    ("STEP 10f", "engine_v2_final_n100.py"),
    ("STEP 10g", "make_n100_audit.py"),
    ("STEP 10h", "make_n100_chart.py"),
    ("STEP 11", "make_cash_series.py"),
    ("STEP 12", "make_daily_audit.py"),
    # MOVED FROM STEP 10i, and the move is load-bearing rather than cosmetic.
    # The combined chart is now generic over the selection, so it may need the 58's
    # and the 74's per-trade logs -- and those are written by STEP 12 immediately
    # above. At 10i they did not exist, which is why the old step could only ever
    # combine mid and n100. Its mid and n100 inputs are written at 10c and 10g, so
    # they are still upstream; nothing consumes the chart, so nothing downstream
    # moved. Output verified byte-identical across the move.
    ("STEP 12b", "make_combined_universes.py"),
    ("STEP 13", "make_final_chart_fair.py"),
    ("STEP 14", "make_final_summary.py"),
    ("STEP 15", "make_daily_log.py"),
    # ORDERING, AND WHY IT IS A STEP. STEP 16 reads the PERMANENT panels, so the
    # copy from /tmp must happen before it -- the constraint run_all.py used to
    # enforce with a bare call between two run() lines, and which S8 lost when it
    # folded the pipeline into one loop. It is a position in this list now, so
    # rewriting the loop cannot drop it. See results/save_caches_step.py.
    ("STEP 15b", "save_caches_step.py"),
    ("STEP 16", "nt_export_scores.py"),
]
# Kept as the canonical set of pipeline script names. run()'s membership guard used
# it; run.py needs the same answer when it maps a step to its universe.
_PIPELINE_SCRIPTS = {s for _, s in PIPELINE_ORDER}


def check_inputs(label, script):
    """Fail by name before a step runs, rather than from inside pandas.

    AN ENTRY MAY CARRY A THIRD FIELD, the arm it belongs to. That input is
    required only when the arm is selected: daily_trades_v1_mid.csv is not
    written by `--arm v2`, and demanding it there turned a correct selective run
    into a hard stop. Entries with no third field are required unconditionally,
    which is all of them but two.

    THE STATIC INVENTORY IS UNAFFECTED. check_pipeline_order reads the literal
    paths out of this table, and they are still literal paths in the same shape;
    only the runtime requirement became conditional.
    """
    import arms.registry as _ar
    import cadence as _cd
    _sel = set(_ar.selected_names())

    def _present(f):
        """The requirement is met by the canonical name OR its cadence sibling.

        A NON-DEFAULT CADENCE NEVER WRITES THE CANONICAL NAME. Under --rebal 40
        the producers write daily_trades_mid_r40.csv and leave the cadence-20 file
        alone, so demanding the canonical name made `--rebal 40` impossible from a
        cold tree -- it only ever passed because an earlier default run had left
        the canonical file on disk. Found by running --rebal 40 from an empty
        checkout; every warm run had passed.
        """
        if f.exists():
            return True
        if _cd.is_default():
            return False
        return f.with_name(f.stem + _cd.suffix() + f.suffix).exists()

    import universes.registry as _ur
    _usel = set(_ur.selected_tags())

    def _wanted(e):
        """Is this input required by THIS run's selection?

        No third field -> always. "u:<tag>" -> only when that universe is
        selected. Anything else -> the arm it names must be selected.
        """
        if len(e) < 3:
            return True
        return (e[2][2:] in _usel) if e[2].startswith("u:") else (e[2] in _sel)

    missing = [(e[0], e[1]) for e in REQUIRED_INPUTS.get(Path(script).name, [])
               if _wanted(e) and not _present(e[0])]
    if not missing:
        return
    print("\n" + "!" * 90)
    print(f"PIPELINE ORDERING ERROR -- cannot start {label}")
    print("!" * 90)
    print(f"\n  {Path(script).name} needs {len(missing)} file(s) that do not exist:\n")
    for f, who in missing:
        print(f"    MISSING  {f.relative_to(ROOT)}")
        print(f"      writer {who}")
    print("\n  Each of these is written by another pipeline step. If that step is")
    print("  listed AFTER this one in run_all.py, the order is wrong and the step")
    print("  must be moved earlier -- not made tolerant of the missing file.")
    print("  If the step ran and the file is still absent, that step failed quietly.")
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
    pairs = [("v5_expanding_cache.csv", "v5_expanding.csv", R/"metrics"),
             ("raw_panel_cache.csv", "raw_panel_20.csv", R/"metrics"),
             ("v74_expanding_cache.csv", "v74_expanding.csv", ROOT/"results74"/"metrics"),
             ("raw_panel74_cache.csv", "raw_panel74_20.csv", ROOT/"results74"/"metrics"),
             ("v_mid_expanding_cache.csv", "v_mid_expanding.csv", ROOT/"results_mid"/"metrics"),
             ("raw_panel_mid_cache.csv", "raw_panel_mid_20.csv", ROOT/"results_mid"/"metrics"),
             ("v_n100_expanding_cache.csv", "v_n100_expanding.csv", ROOT/"results_n100"/"metrics"),
             ("raw_panel_n100_cache.csv", "raw_panel_n100_20.csv", ROOT/"results_n100"/"metrics")]
    for perm_name, tmp_name, folder in pairs:
        perm = folder / perm_name
        if perm.exists() and not (TMP / tmp_name).exists():
            shutil.copy(perm, TMP / tmp_name)
            print(f"    restored {tmp_name} from permanent cache")

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


def main():
    """Delegate to run.py. This file is now a compatibility entry point.

    WHAT STILL LIVES HERE, AND WHY IT WAS NOT MOVED
        PIPELINE_ORDER, REQUIRED_INPUTS, STEP_HELPERS, FROZEN_SCRIPTS,
        NAUTILUS_SCRIPTS, script_path(), check_inputs(), the cache lists and the two
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

    import run as _run
    argv = ["--universe", "all", "--arm", "all"]
    if FRESH:
        argv.append("--fresh")
    return _run.main(argv)


if __name__ == "__main__":
    sys.exit(main())
