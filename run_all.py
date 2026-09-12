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
  10a. build_scores_mid     -> MidCap150 scores (SLOW)
  10b. engine_v2_final_mid  -> MidCap150 v2 FINAL
  10c. make_mid_audit       -> MidCap150 daily audit CSVs
  10d. make_mid_chart       -> MidCap150 chart + cap-weighted index benchmark
  === NIFTY 100 ===
  10e. build_scores_n100    -> Nifty 100 scores (SLOW)
  10f. engine_v2_final_n100 -> Nifty 100 v2 FINAL
  10g. make_n100_audit      -> Nifty 100 daily audit CSVs
  10h. make_n100_chart      -> Nifty 100 chart + cap-weighted index benchmark
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
STEP_DIRS = (ROOT / "results", ROOT / "nautilus")

# A step whose body lives in a shared helper must be scanned WITH that helper, or
# the static ordering check loses the edges the helper writes. results/audit_step.py
# holds the one audit implementation the two per-universe entry points call.
STEP_HELPERS = {
    "make_mid_audit.py":     (R / "audit_step.py",),
    "make_n100_audit.py":    (R / "audit_step.py",),
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
    # UNIVERSE-TAGGED, like nt_export_scores' own inputs: the port loads the
    # parquet for each SELECTED universe, and a run that selected one universe has
    # one of these four.
    "nt_execute.py": [
        (ROOT / "nautilus" / "data" / "scores_58.parquet",
         "STEP 16 nt_export_scores.py", "u:58"),
        (ROOT / "nautilus" / "data" / "scores_74.parquet",
         "STEP 16 nt_export_scores.py", "u:74"),
        (ROOT / "nautilus" / "data" / "scores_mid.parquet",
         "STEP 16 nt_export_scores.py", "u:mid"),
        (ROOT / "nautilus" / "data" / "scores_n100.parquet",
         "STEP 16 nt_export_scores.py", "u:n100"),
    ],
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
    ("STEP 10a", "build_scores_mid.py"),
    ("STEP 10b", "engine_v2_final_mid.py"),
    ("STEP 10c", "make_mid_audit.py"),
    ("STEP 10d", "make_mid_chart.py"),
    ("STEP 10e", "build_scores_n100.py"),
    ("STEP 10f", "engine_v2_final_n100.py"),
    ("STEP 10g", "make_n100_audit.py"),
    ("STEP 10h", "make_n100_chart.py"),
    # MOVED FROM STEP 10i, and the move is load-bearing rather than cosmetic.
    # The combined chart is now generic over the selection, so it may need the 58's
    # and the 74's per-trade logs -- and those are written by STEP 12 immediately
    # above. At 10i they did not exist, which is why the old step could only ever
    # combine mid and n100. Its mid and n100 inputs are written at 10c and 10g, so
    # they are still upstream; nothing consumes the chart, so nothing downstream
    # moved. Output verified byte-identical across the move.
    ("STEP 12b", "make_combined_universes.py"),
    ("STEP 15", "make_daily_log.py"),
    # ORDERING, AND WHY IT IS A STEP. STEP 16 reads the PERMANENT panels, so the
    # copy from /tmp must happen before it -- the constraint run_all.py used to
    # enforce with a bare call between two run() lines, and which S8 lost when it
    # folded the pipeline into one loop. It is a position in this list now, so
    # rewriting the loop cannot drop it. See results/save_caches_step.py.
    ("STEP 15b", "save_caches_step.py"),
    ("STEP 16", "nt_export_scores.py"),
    # STEP 17 IS THE EXECUTION HALF OF THE NAUTILUS STORY. STEP 16 exports the
    # score parquet the port READS; nothing in the pipeline ever ran the port
    # itself, so a normal run produced Nautilus input and no Nautilus output.
    # It must follow 16, which writes the parquet it loads.
    ("STEP 17", "nt_execute.py"),
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
        want = f if (_cd.is_default() and _pf.is_default()) else \
            f.with_name(f.stem + _cd.suffix() + _pf.suffix() + f.suffix)
        if want.exists():
            return True
        _found.append((f, want, sorted(
            q.name for q in want.parent.glob(f.stem + "*" + f.suffix))[:6]))
        return False

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

    _found = []
    missing = [(e[0], e[1]) for e in REQUIRED_INPUTS.get(Path(script).name, [])
               if _wanted(e) and not _present(e[0])]
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
    from universes.registry import REGISTRY
    pairs = [(u.score_cache.name, u.score_tmp.name, u.score_cache.parent)
             for u in REGISTRY.values()] + \
            [(u.raw_cache.name, u.raw_tmp.name, u.raw_cache.parent)
             for u in REGISTRY.values()]
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
