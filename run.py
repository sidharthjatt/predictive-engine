"""
run.py -- one entry point: choose the universe and the arm, everything runs for it.
==================================================================================

    ./venv/bin/python run.py --universe mid --arm v3
    ./venv/bin/python run.py --universe all --arm all
    ./venv/bin/python run.py --universe n100 --arm v1 --rebal 5
    ./venv/bin/python run.py --list                 # resolve and print, run nothing
    ./venv/bin/python run.py --dry-run              # same, with output paths

THE INTERPRETER IS LOAD-BEARING, exactly as it was for run_all.py. `python3` on the
machine these numbers were produced on is 3.11 with no lightgbm, and below
nautilus_trader's 3.12 floor. Use ./venv/bin/python.

TWO KINDS OF STEP, AND THEY SELECT DIFFERENTLY
    ARM STEPS are universe-generic AND arm-generic: one implementation
    (v34_common.run_arm) takes a Universe and an Arm and runs that single
    combination. Adding a universe or an arm to the registries makes new
    combinations available with no code change, which is the property this file
    exists to provide.

    PIPELINE STEPS are the thirty-one scripts run_all.py ordered. Most are still
    bound to one universe by their own filename -- engine_v2_final_mid.py is
    MidCap150 and nothing else -- because the engine family was deliberately not
    merged: what separates those files is written analysis, not duplication. So a
    NEW universe gets its scores, its audit and every arm automatically, and would
    still need an engine and a chart script written for it. That limit is real and
    is stated here rather than discovered later.

WHAT IS NOT MOVED
    results*/metrics/ is untouched. Every existing artefact keeps its path, so the
    seven identity gates that read v34_comparison.csv, and every consumer of the
    daily audit files, keep working. runs/{universe}/{arm}/ is ADDITIVE: it holds
    the per-combination output that did not exist before.
"""
# ---------------------------------------------------------------------------
# DETERMINISM PIN -- SET BEFORE ANY NUMERIC LIBRARY IS IMPORTED.
# Carried over from run_all.py unchanged, and for the same reason: an OpenMP/BLAS
# runtime reads its thread count when it initialises at import, so this must run
# before pandas or lightgbm arrive. Only `os` is imported above it.
# ---------------------------------------------------------------------------
import os as _os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ[_v] = "1"
_os.environ["PYTHONHASHSEED"] = "0"

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "results"), str(ROOT / "nautilus")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import paths                                        # noqa: E402
from universes.registry import REGISTRY             # noqa: E402
from arms.registry import ARMS, SHIPPING as SHIPPING_ARMS                      # noqa: E402

# ---------------------------------------------------------------------------
# WHICH PIPELINE STEPS BELONG TO WHICH UNIVERSE
# ---------------------------------------------------------------------------
# Derived by scanning each step (and its helpers) for the universe it names, then
# written down here so selection is explicit rather than re-derived by regex on
# every run.
#
# EVERY TAG HERE MUST BE A REGISTRY KEY, and _check_step_universes() below enforces
# that at import. Twenty entries were deleted with the 58 and the 74; the table
# used to name those two in eight places, and a tag that outlived its universe
# would have gone on selecting a step that could never run.
ALL_UNIVERSES = tuple(REGISTRY)          # NOT a literal list. See the check below.

STEP_UNIVERSES = {
    "build_scores_mid.py":        ("mid",),
    "engine_v2_final_mid.py":     ("mid",),
    "make_mid_audit.py":          ("mid",),
    "make_mid_chart.py":          ("mid",),
    "build_scores_n100.py":       ("n100",),
    "engine_v2_final_n100.py":    ("n100",),
    "make_n100_audit.py":         ("n100",),
    "make_n100_chart.py":         ("n100",),
    # SERVES EVERY UNIVERSE. It draws one comparison across whichever of them the
    # run selected, so it is selected whenever ANY universe is -- and then decides
    # for itself, from the selection, whether there are enough to compare.
    "make_combined_universes.py": ALL_UNIVERSES,
    "make_daily_log.py":          ALL_UNIVERSES,
    # SERVES EVERY UNIVERSE, so a selective run persists its panels too. Listed
    # against all rather than left unmapped: `--universe mid` must still reach
    # STEP 15b, or that path reproduces the very bug 15b exists to fix.
    "save_caches_step.py":        ALL_UNIVERSES,
    "nt_export_scores.py":        ALL_UNIVERSES,
    # SERVES EVERY UNIVERSE. It runs the execution engine for each selected
    # (universe, arm) at the selected cadence.
    "nt_execute.py":              ALL_UNIVERSES,
}


def _check_step_universes():
    """Every tag in STEP_UNIVERSES must name a universe the registry defines.

    THE FAILURE THIS CATCHES IS SILENT OTHERWISE. A step registered to a deleted
    universe is simply never selected -- no error, no log line -- so the step stops
    running and the run still reports success. That is how `--universe mid,n100`
    could have kept a 58-only step in the table indefinitely.
    """
    unknown = {t for tags in STEP_UNIVERSES.values() for t in tags} - set(REGISTRY)
    if unknown:
        raise SystemExit(
            f"STEP_UNIVERSES names universe(s) the registry does not define: "
            f"{sorted(unknown)}.\n"
            f"  known: {sorted(REGISTRY)}\n"
            f"  Either the universe was deleted and its steps must go with it, or "
            f"the registry entry is missing. See RETIRED_UNIVERSES.md.")


_check_step_universes()


# A SCORE-BUILD STEP IS SKIPPED WHEN ITS PANEL IS ALREADY ON DISK.
# run_all.main() did this with hand-written `if not (TMP/"v5_expanding.csv")`
# guards. Without it a shimmed run_all.py would rebuild every panel on every
# run -- hours, for nothing -- so the behaviour moves here rather than being lost.
#
# WHICH STEPS is written down; WHICH FILE is read from the registry (u.score_tmp),
# so a new universe's build step inherits the skip with no path repeated here.
SCORE_BUILD_STEPS = {
    "build_scores_mid.py", "build_scores_n100.py",
}


def cached_panel(scr):
    """The already-built score panel that lets `scr` be skipped, or None."""
    if Path(scr).name not in SCORE_BUILD_STEPS:
        return None
    serves = STEP_UNIVERSES.get(Path(scr).name) or ()
    for tag in serves:
        p = Path(REGISTRY[tag].score_tmp)
        if p.exists():
            return p
    return None


def show(p):
    """A path as the reader will recognise it: repo-relative when it is in the repo.

    NOT Path.relative_to, which RAISES on a path outside ROOT. A universe is free to
    put its metrics anywhere -- nothing in universes/registry.py says the directory
    must be inside this checkout, and the first throwaway universe added to test
    that (requirement 6: adding a universe is a config change) pointed its
    metrics_dir at /tmp and crashed --dry-run here. Printing a plan is not a place
    to enforce a layout rule the registry does not have.
    """
    p = Path(p)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def resolve_universes(name):
    """ANY SUBSET OF THE REGISTERED UNIVERSES, size 1 to 4.

    Accepts "all" (every registered universe), a single tag, or a comma-separated
    list -- "mid,58". Whitespace around a tag is tolerated because a shell quoting
    a list is the normal way this gets typed.

    THE RESULT IS ALWAYS IN REGISTRY ORDER, NOT IN THE ORDER TYPED. Selection must
    name a SET, not a sequence: `--universe mid,58` and `--universe 58,mid` are the
    same request and must produce the same artefacts, or the filename of a combined
    comparison would depend on typing order and two runs of the same selection
    would leave two files. Reporting order is a separate decision and lives in
    universes/registry.REPORT_ORDER, which the steps that care consult.

    A REPEATED TAG IS NOT AN ERROR, it is the same set: `--universe mid,mid` is mid.
    Deduplication happens through REGISTRY iteration below, so it cannot produce a
    universe twice on one chart.
    """
    if name in ("all", None):
        return list(REGISTRY.values())
    want = [t.strip() for t in str(name).split(",") if t.strip()]
    if not want:
        raise SystemExit("--universe was empty; give a tag, a comma-separated list, "
                         f"or 'all'. known: {', '.join(REGISTRY)}")
    unknown = [t for t in want if t not in REGISTRY]
    if unknown:
        # NAMES EVERY UNKNOWN TAG, not just the first. Typing three tags and being
        # told about one typo at a time is three runs to learn one thing.
        raise SystemExit(f"unknown universe(s) {', '.join(repr(t) for t in unknown)}; "
                         f"known: {', '.join(REGISTRY)}")
    sel = set(want)
    return [u for t, u in REGISTRY.items() if t in sel]


def resolve_arms(name):
    """ANY SUBSET OF THE FOUR ARMS, size 1 to 4.

    Accepts "all" (every arm), a single name, or a comma-separated list --
    "v1,v3". Exactly the shape --universe takes, and for the same reasons:

    THE RESULT IS ALWAYS IN ARMS ORDER, NOT IN THE ORDER TYPED, so `--arm v3,v1`
    and `--arm v1,v3` are the same request and produce the same artefacts. A
    selection names a SET; if order were preserved the derived filename of a
    subset measurement would depend on typing order.

    A REPEATED NAME IS NOT AN ERROR, it is the same set. Deduplication happens
    through ARMS iteration below, so an arm cannot appear twice in one table.
    """
    if name in ("all", None):
        return list(ARMS.values())
    want = [t.strip() for t in str(name).split(",") if t.strip()]
    if not want:
        raise SystemExit("--arm was empty; give an arm name, a comma-separated "
                         f"list, or 'all'. known: {', '.join(ARMS)}")
    unknown = [t for t in want if t not in ARMS]
    if unknown:
        # Every unknown name at once, not one per run.
        raise SystemExit(f"unknown arm(s) {', '.join(repr(t) for t in unknown)}; "
                         f"known: {', '.join(ARMS)}")
    sel = set(want)
    return [a for n, a in ARMS.items() if n in sel]


def pipeline_steps(unis):
    """The run_all.py steps that serve any selected universe, IN ORDER.

    Order comes from run_all.PIPELINE_ORDER and is never re-sorted: it is the thing
    check_pipeline_order.enforce verifies, and a consumer must never precede its
    producer.
    """
    import runpy
    mod = runpy.run_path(str(ROOT / "run_all.py"), run_name="__not_main__")
    want = {u.tag for u in unis}
    out, dropped = [], []
    for label, scr in mod["PIPELINE_ORDER"]:
        serves = STEP_UNIVERSES.get(scr)
        if serves is None:
            out.append((label, scr, "?unmapped"))          # surfaced, never skipped
            continue
        # WHAT THE STEP CAN ACTUALLY SERVE, not what it was written to serve.
        # STEP_UNIVERSES is a static map; REGISTRY is what exists right now. A step
        # listed against (mid, n100) whose n100 config has been deleted serves only
        # mid, and selecting it on the strength of the absent half used to run it
        # and crash inside. The steps themselves now run on whatever remains; this
        # intersection is what tells them -- and the reader -- what that is.
        present = tuple(t for t in serves if t in REGISTRY)
        if not present:
            dropped.append((label, scr, serves))           # nothing left to do
        elif want & set(present):
            out.append((label, scr, ",".join(present)))
    return out, mod, dropped


def arm_steps(unis, arms, rebal=None):
    """One entry per (universe, arm).

    NOTHING IS SKIPPED HERE ANY MORE. The skip list existed for the retired 58 and
    74: they ran only the shipping arms, because their engines never called
    v34_common and had no v3/v4 path at all, and they ran only at cadence 20. Both
    universes are deleted, so every (universe, arm) pair in the selection is real
    and runnable. The second return value is kept -- callers unpack two -- and is
    always empty; when a universe needs excluding again it will be for a reason
    that exists then, recorded then.
    """
    runs, skipped = [], []
    for u in unis:
        for a in arms:
            runs.append((u, a))
    return runs, skipped


def _cadence_default(args):
    """True when this run uses the shipped cadence, so nothing is cadence-scoped."""
    return args.rebal is None or int(args.rebal) == paths.DEFAULT_REBAL


# ---------------------------------------------------------------------------
# PRE-FLIGHT -- refuse to start rather than fail somewhere in the middle
# ---------------------------------------------------------------------------
def preflight(args, plan):
    """Every axis of the selection must name something that EXISTS, and the shared
    metrics directory must hold nothing that belongs to a universe.

    WHY A REFUSAL AND NOT A WARNING. Both failures this catches are silent by
    nature. A selection naming a universe, arm, cadence or profile that nothing
    defines does not crash -- it selects an empty set, runs the steps that remain,
    and reports success over a smaller pipeline than the one that was asked for.
    That is how the 58's steps could have stayed registered after the 58 was
    deleted. And a universe-tagged artefact in results/metrics is the second half
    of the same defect: results/metrics was the 58's output home as well as the
    shared engine directory, so a step that still writes v2FINAL_* there is writing
    a retired universe's filename into a directory that no longer belongs to any
    universe. See RETIRED_UNIVERSES.md.

    Each check names EVERY offender, not the first: learning about one typo per run
    is three runs to learn one thing.
    """
    import arms.registry as _arms
    import cadence as _cad
    import profiles as _prof

    bad = []

    unknown_u = [u.tag for u in plan["universes"] if u.tag not in REGISTRY]
    if unknown_u:
        bad.append(f"universe(s) {sorted(unknown_u)} -- registry defines "
                   f"{sorted(REGISTRY)}")

    unknown_a = [a.name for a in plan["arms"] if a.name not in ARMS]
    if unknown_a:
        bad.append(f"arm(s) {sorted(unknown_a)} -- registry defines {sorted(ARMS)}")

    if args.rebal is not None:
        try:
            r = int(args.rebal)
            if r < 1:
                raise ValueError
        except (TypeError, ValueError):
            bad.append(f"cadence {args.rebal!r} -- must be a positive integer "
                       f"number of trading sessions (default {paths.DEFAULT_REBAL})")

    if args.profile is not None and args.profile not in _prof.PROFILES:
        bad.append(f"profile {args.profile!r} -- profiles.py defines "
                   f"{sorted(_prof.PROFILES)}")

    stray = _universe_artefacts_in_shared_metrics()
    if stray:
        bad.append("universe-tagged artefact(s) in results/metrics, which is the "
                   "SHARED directory and no universe's output home: "
                   + ", ".join(sorted(stray)[:8])
                   + (f" (+{len(stray) - 8} more)" if len(stray) > 8 else ""))

    if bad:
        raise SystemExit("REFUSING TO START -- the run names something that does "
                         "not exist:\n" + "\n".join(f"  {b}" for b in bad)
                         + "\n  Nothing has run. See RETIRED_UNIVERSES.md.")


# The naming schemes a universe's artefacts use. FINAL_*/v2FINAL_* were the
# retired 58's and 74's and no live code may emit them again; v34_* is the live
# pair's and belongs in results_mid/ and results_n100/, never here.
_UNIVERSE_ARTEFACT = re.compile(
    r"^(FINAL_|v2FINAL_|v34_|DAILY_LOG_|daily_trades_|daily_summary_|cash_series_)"
    r"|_(" + "|".join(sorted(REGISTRY)) + r")\.(csv|json|txt|png)$")


def _universe_artefacts_in_shared_metrics():
    """Filenames in results/metrics that belong to a universe. Empty is correct."""
    import config
    d = Path(config.METRICS_DIR)
    if not d.is_dir():
        return []
    return [f.name for f in d.iterdir()
            if f.is_file() and _UNIVERSE_ARTEFACT.search(f.name)]


def build_plan(args):
    unis = resolve_universes(args.universe)
    arms = resolve_arms(args.arm)
    plan = {"universes": unis, "arms": arms, "pipeline": [], "arm_runs": [],
            "skipped": [], "dropped": []}
    if args.steps in ("pipeline", "all"):
        # EVERY UNIVERSE HONOURS EVERY CADENCE NOW. This dropped the retired 58
        # and 74 from a non-default-cadence run, because their engines pinned
        # REBAL=20 and ignored the flag -- `--universe mid,58 --rebal 40` used to
        # run the 58's whole pipeline at 20 and write artefacts with no marker
        # saying so. Both universes are deleted; the drop list stays in the plan
        # shape because the reporting code reads it, and is always empty.
        _pipe_unis = list(unis)
        plan["pipeline"], plan["_run_all"], plan["dropped"] = pipeline_steps(_pipe_unis)
    if args.steps in ("arms", "all"):
        plan["arm_runs"], plan["skipped"] = arm_steps(unis, arms, args.rebal)
    return plan


def print_plan(plan, args, show_paths=False):
    unis, arms = plan["universes"], plan["arms"]
    print("=" * 96)
    print(f" RESOLVED PLAN   --universe {args.universe}   --arm {args.arm}   "
          f"--steps {args.steps}" + (f"   --rebal {args.rebal}" if args.rebal else ""))
    print("=" * 96)
    print(f"  universes ({len(unis)}): " + ", ".join(u.tag for u in unis))
    print(f"  arms      ({len(arms)}): " + ", ".join(f"{a.name}[{a.mode}/{a.sizing}]" for a in arms))
    if args.rebal:
        print(f"  rebalance cadence: {args.rebal} (default 20)")
    else:
        print(f"  rebalance cadence: 20 (default, unchanged)")

    if plan["pipeline"]:
        print(f"\n  PIPELINE STEPS ({len(plan['pipeline'])}), in run_all order:")
        for label, scr, serves in plan["pipeline"]:
            mark = "  <-- UNMAPPED" if serves == "?unmapped" else ""
            print(f"    {label:<9} {scr:<28} [{serves}]{mark}")
    elif args.steps in ("pipeline", "all"):
        print("\n  PIPELINE STEPS: none selected")

    if plan["arm_runs"]:
        print(f"\n  ARM RUNS ({len(plan['arm_runs'])}):")
        for u, a in plan["arm_runs"]:
            line = f"    {u.tag:<6} {a.name:<4} mode={a.mode:<8} sizing={a.sizing:<7}"
            if show_paths:
                line += f"  -> {show(paths.run_dir(u, a, args.rebal))}/"
            print(line)
    elif args.steps in ("arms", "all"):
        print("\n  ARM RUNS: none selected")

    if plan.get("cadence_dropped"):
        print(f"\n  NOT RUN -- frozen universes cannot take a non-default cadence "
              f"(--rebal {args.rebal}); their engines pin {paths.DEFAULT_REBAL}:")
        for u in plan["cadence_dropped"]:
            print(f"    {u.tag:<6} whole pipeline skipped: running it at "
                  f"{paths.DEFAULT_REBAL} would answer a different question from "
                  f"the one asked, and its published numbers must not move")

    if plan.get("dropped"):
        print(f"\n  NOT RUN ({len(plan['dropped'])}) -- every universe this step serves "
              f"has been removed from the registry:")
        for label, scr, serves in plan["dropped"]:
            print(f"    {label:<9} {scr:<28} served [{','.join(serves)}], none of which is registered")

    if plan["skipped"]:
        print(f"\n  SKIPPED ({len(plan['skipped'])}) -- combinations a frozen universe cannot supply:")
        # THE REASON TRAVELS WITH THE ENTRY. There are two now -- a frozen
        # universe has no v3/v4 path, and a frozen universe has only one cadence
        # -- so printing one hardcoded sentence would misdescribe the other.
        for u, a, why in plan["skipped"]:
            print(f"    {u.tag:<6} {a.name:<4} skipped: {why}")

    if show_paths:
        print("\n  OUTPUT LOCATIONS")
        for u, a in plan["arm_runs"]:
            d = show(paths.run_dir(u, a, args.rebal))
            print(f"    {u.tag}/{a.name:<4} {d}/comparison.csv  subperiods.csv  equity.csv  "
                  f"params.json  chart.png  run.log")
        seen = set()
        for u in unis:
            m = show(paths.metrics(u))
            if m not in seen:
                seen.add(m)
                print(f"    {u.tag:<6} existing artefacts stay in {m}/  (unchanged)")
    print("=" * 96)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the pipeline for one universe/arm combination.")
    ap.add_argument("--universe", default="all",
                    help="universe tag, a comma-separated subset (e.g. mid,58), or "
                         "'all' (default). known: " + ", ".join(REGISTRY))
    ap.add_argument("--arm", default="all",
                    help="arm name, a comma-separated subset (e.g. v1,v3), or "
                         "'all' (default). known: " + ", ".join(ARMS))
    ap.add_argument("--steps", default="all", choices=("all", "pipeline", "arms"),
                    help="which kinds of step to run (default all)")
    ap.add_argument("--rebal", type=int, default=None,
                    help="rebalance cadence in trading days; omit for the default 20")
    ap.add_argument("--profile", default=None, choices=("research", "tradeable"),
                    help="execution-realism profile; research (default) reproduces "
                         "the published history exactly, tradeable applies the "
                         "participation cap. See profiles.py.")
    ap.add_argument("--list", action="store_true", help="resolve and print the plan, run nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="like --list, and show every output location")
    ap.add_argument("--fresh", action="store_true", help="clear caches first (full rebuild)")
    args = ap.parse_args(argv)

    plan = build_plan(args)
    if args.list or args.dry_run:
        print_plan(plan, args, show_paths=args.dry_run)
        return 0

    return execute(plan, args)


def collect_run_folder(plan, args, t_start):
    """Gather everything THIS invocation produced into one named folder.

    HARD LINKS, NOT COPIES AND NOT SYMLINKS. The canonical artefacts are written
    first, to the paths they have always used, by the steps themselves -- nothing
    about where a step writes has changed, which is why G1 stays trivially true.
    This runs afterwards and links what appeared.

        copies   would double roughly half a gigabyte per invocation, and could
                 drift from the canonical file without anything noticing.
        symlinks would dangle the moment a cleanup removed the canonical file,
                 leaving a run folder full of broken pointers.
        hard links cost one inode, cannot drift because there is only one set of
                 bytes, and survive the canonical file being deleted.

    WHAT COUNTS AS "PRODUCED": modified at or after this run started. That is why
    t_start is taken before the first step rather than derived afterwards. A step
    that rewrote a file identically still counts -- it ran, and the folder is a
    record of what the run touched, not of what changed.

    A run folder is never required by anything. If linking fails -- a filesystem
    without hard links, a cross-device path -- the run has already succeeded and
    this says so rather than failing after the fact.
    """
    import os
    uni = [u.tag for u in plan["universes"]]
    arm = [a.name for a in plan["arms"]]
    reb = args.rebal if args.rebal is not None else paths.DEFAULT_REBAL
    dest = ROOT / "runs" / paths.run_folder_name(uni, arm, reb)
    linked, failed = 0, []
    for d in paths.ARTEFACT_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.stat().st_mtime < t_start:
                continue
            # DO NOT RECURSE INTO RUN FOLDERS. runs/ is an artefact dir, and a
            # previous invocation's folder sits inside it; without this a run
            # would link the last run's links into its own.
            if dest in f.parents or any(pp.name.startswith("20") and pp.parent.name == "runs"
                                        for pp in f.parents):
                continue
            # THE SCORE PANEL CACHES ARE INPUT, NOT THIS RUN'S RESULT.
            # STEP 15b re-persists all eight panels on every invocation whatever
            # was selected, so their mtime always moves -- which put
            # results74/metrics/v74_expanding_cache.csv inside a folder named
            # `mid_v1-v3_r40`. They are the model's persisted panels, the same
            # bytes every run, and a reader looking for what a run PRODUCED does
            # not want a 250 MB panel that predates it.
            if f.name.endswith("_cache.csv"):
                continue
            tgt = dest / d / f.relative_to(base)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            try:
                if tgt.exists():
                    tgt.unlink()
                os.link(f, tgt)
                linked += 1
            except OSError as e:
                failed.append(f"{f.relative_to(ROOT)}: {e}")
    if linked:
        (dest / "RUN.txt").write_text(
            f"universes : {', '.join(uni)}\n"
            f"arms      : {', '.join(arm)}\n"
            f"cadence   : {reb}\n"
            f"steps     : {len(plan['pipeline'])} pipeline, {len(plan['arm_runs'])} arm runs\n"
            f"artefacts : {linked} hard-linked from their canonical locations\n"
            f"\nEvery file here is a HARD LINK to the canonical artefact, not a copy.\n"
            f"Editing one edits the other; deleting one leaves the other intact.\n")
        print(f"\n  run folder -> {show(dest)}/   ({linked} artefacts hard-linked)")
    if failed:
        print(f"  {len(failed)} could not be linked (the run itself succeeded):")
        for m in failed[:5]:
            print(f"    {m}")


def execute(plan, args):
    """Run the plan in ONE process, carrying run_all.py's four safety mechanisms."""
    import importlib
    import time
    import module_state
    import check_pipeline_order as cpo

    mod = plan.get("_run_all")
    if mod is None:
        _, mod, _ = pipeline_steps(plan["universes"])

    # TELL THE STEPS WHAT WAS SELECTED, not just what is registered.
    # A step that builds MULTI-UNIVERSE output cannot get this from REGISTRY: with
    # `--universe mid,58` the registry still holds 74, and the fair-comparison
    # chart would put a universe on the page that nobody asked for. Set once, here,
    # before any step runs, so every step sees the same answer.
    # PRE-FLIGHT FIRST, BEFORE ANY SELECTION IS RECORDED OR ANY STEP RUNS.
    preflight(args, plan)

    import universes.registry as _reg
    _reg.set_selection([u.tag for u in plan["universes"]])
    # THE SAME FOR ARMS. run_v34 is reached through the ENGINE, a pipeline step
    # selected by universe, so it cannot be handed the arm selection as an
    # argument the way run_arm is -- it has to read it. Set here, once, beside
    # the universe selection.
    import arms.registry as _arms
    _arms.set_selection([a.name for a in plan["arms"]])
    # THE THIRD AXIS. Set here beside the other two, before any step runs, and
    # read by the engines as an ARGUMENT to backtest_exposure -- never written
    # into test_exposure.REBAL. See the note at the top of cadence.py.
    import cadence as _cad
    _cad.set_selection(args.rebal)
    # THE PROFILE, LIKE THE CADENCE, IS RECORDED ONCE HERE. Everything downstream
    # asks profiles.participation_cap() at call time.
    import profiles as _prof
    _prof.set_selection(args.profile)

    # SAFETY 1 -- the determinism pin is already set, at the top of this file,
    # before any numeric import. Nothing to do here; it is listed so the four are
    # accounted for in one place.

    # THE WORKING DIRECTORY IS ROOT, AND THAT IS NOT COSMETIC.
    # run_all.run() spawned every step with an explicit cwd=ROOT. In process there
    # is no cwd argument, so a step is handed whatever directory the shell happened
    # to be in -- and nautilus/nt_export_scores.py builds its four input paths as
    # bare relatives ("results/metrics/v5_expanding_cache.csv"). Without this,
    # run.py works from the repo root and fails from anywhere else, on one step,
    # with a FileNotFoundError that names a path the reader can see exists.
    _os.chdir(ROOT)

    # SAFETY 2 -- the static ordering check. Runs over the FULL pipeline, not the
    # selected subset: an inversion is a property of the pipeline, and checking only
    # what was selected would let a subset hide one.
    # The unresolved-placeholder LIST is suppressed when no pipeline step was
    # selected: on an arms-only run those ten lines name steps this invocation does
    # not touch, and a warning that fires every time about something irrelevant is
    # how a checker gets ignored. The count still prints, and an inversion is still
    # fatal.
    cpo.enforce(mod["PIPELINE_ORDER"],
                # INDEXED, NOT UNPACKED: an entry may carry a third field naming
                # the arm it belongs to, and `for f, _ in lst` raises on those.
                covered={e[0].name for lst in mod["REQUIRED_INPUTS"].values()
                         for e in lst},
                resolver=mod["script_path"], helpers=mod["STEP_HELPERS"],
                list_unresolved=bool(plan["pipeline"]))

    # SAFETY 3 -- cache restore, so a step reads the panel it expects.
    if args.fresh:
        print("--fresh: clearing caches (full rebuild)")
        for c in mod["CACHE_TMP"] + mod["CACHE_PERM"]:
            if c.exists():
                c.unlink()
    else:
        mod["restore_cache_to_tmp"]()

    # Stated once per run, as run_all.main() did, so the log itself records which
    # universe construction produced the numbers under it.
    import survivorship as sv
    print(f"SURVIVORSHIP: {sv.describe_state()}\n")

    t_start = time.time()
    for label, scr, serves in plan["pipeline"]:
        if serves == "?unmapped":
            raise SystemExit(f"{scr} is not in STEP_UNIVERSES; add it there so "
                             f"selection cannot silently drop it")
        cached = None if args.fresh else cached_panel(scr)
        if cached is not None:
            print(f"\n>>> {label}  {scr}  -- score panel cached, skipping "
                  f"({cached})")
            continue
        # SAFETY 4 -- fail by filename and owing step, not from inside pandas.
        mod["check_inputs"](label, scr)
        print("\n" + "=" * 90); print(f">>> {label}  {scr}"); print("=" * 90, flush=True)
        t0 = time.time()
        # IN PROCESS, NOT SPAWNED. Every step has main() (S4). module_state.pinned()
        # restores any shared module global a step reassigns, which a subprocess used
        # to get for free by exiting.
        with module_state.pinned(
                report=lambda ch: print(f"    [restored leaked globals: "
                                        f"{', '.join(f'{m}.{a}' for m, a, _, _ in ch)}]"),
                on_uncovered=lambda ms: print(f"    [note: {', '.join(ms)} imported "
                                              f"inside the step; not covered by the guard]")):
            importlib.import_module(Path(scr).stem).main()
        print(f"    [{label} done in {(time.time()-t0)/60:.1f} min]")

    # A DROPPED COMBINATION IS ANNOUNCED, NOT SILENTLY OMITTED.
    # arm_steps() separates the (universe, arm) pairs that cannot run -- a frozen
    # universe has no v3/v4 path at all -- from the ones that can. print_plan
    # showed them under SKIPPED, but only on --list/--dry-run: an actual
    # `--universe mid,58 --arm v1,v3` ran three of its four combinations and said
    # nothing about the fourth. A selection that quietly does less than it was
    # asked is the failure this project keeps finding; it is reported here, in the
    # run's own log, where the person who asked for it will read it.
    if plan["skipped"]:
        print("\n" + "=" * 90)
        print(f"NOT RUN ({len(plan['skipped'])}) -- combinations a frozen universe "
              f"cannot supply:")
        for u, a, why in plan["skipped"]:
            print(f"    {u.tag:<6} {a.name:<4} {why}")
        print("=" * 90, flush=True)

    for u, a in plan["arm_runs"]:
        print("\n" + "=" * 90)
        print(f">>> ARM {u.tag} / {a.name}   mode={a.mode} sizing={a.sizing}"
              + (f" rebal={args.rebal}" if args.rebal else ""))
        print("=" * 90, flush=True)
        t0 = time.time()
        import v34_common
        with module_state.pinned():
            comp, out = v34_common.run_arm(u, a, rebal=args.rebal)
        print(comp.to_string(index=False))
        print(f"    -> {show(out)}/   [{(time.time()-t0)/60:.1f} min]")

    # SAFETY 3, second half -- persisting the panels IS STEP 15b now, inside the
    # loop above and ahead of STEP 16, which reads them. It ran here, after the
    # whole loop AND after the arm runs, which put it after its own consumer: on a
    # cold run STEP 16 died with "v5_expanding_cache.csv missing". Nothing is
    # called here any more; the ordering is expressed in PIPELINE_ORDER.

    print("\n" + "=" * 90)
    print(f"DONE in {(time.time()-t_start)/60:.1f} min   "
          f"({len(plan['pipeline'])} pipeline steps, {len(plan['arm_runs'])} arm runs)")
    print("=" * 90)
    collect_run_folder(plan, args, t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
