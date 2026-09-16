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
# THE INVOCATION CONTRACT
# ---------------------------------------------------------------------------
# A STEP DECLARES ITS OWN ARITY, AT THE SITE, IN ITS SIGNATURE.
#
#     def main()      whole-run step. Invoked once. Decides from the selection.
#     def main(u)     per-universe step. Invoked once per universe, GIVEN it.
#
# THIS REPLACES STEP_UNIVERSES, which is retired along with SCORE_BUILD_STEPS and
# is NOT replaced by anything. Between them they were the fifth and sixth hardcoded
# lists in this project, and the failure both had is the one the cadence, arm and
# profile axes each produced in turn: a table that duplicates knowledge available
# elsewhere, and goes stale against it silently. STEP_UNIVERSES answered two
# questions -- which universes a step serves, and whether it is per-universe at all
# -- and both now fall out of something that cannot disagree with itself. Which
# universe: run_all.PIPELINE_ORDER's third field, the row that declares the
# invocation. Whether: the signature, read from the file.
#
# ARITY IS READ STATICALLY, WITHOUT IMPORTING THE STEP. ast, not inspect. Every
# step is import-safe by S4 -- "IMPORT MUST NOT DO THE WORK" -- so importing would
# be sound, but a plan is not allowed to cost what importing nt_execute costs, and
# --list must stay a thing you can run without loading nautilus_trader.
ALL_UNIVERSES = tuple(REGISTRY)          # NOT a literal list. See the check below.


def _declared_arity(scr, resolver):
    """How many arguments `scr`'s main() declares, read from the source.

    Returns None when the file has no module-level main(), which is a separate
    failure from a wrong arity and is reported as one.
    """
    import ast
    src = Path(resolver(scr))
    tree = ast.parse(src.read_text(), filename=str(src))
    for node in tree.body:                      # MODULE LEVEL ONLY -- a nested
        if isinstance(node, (ast.FunctionDef,   # def main() inside another function
                             ast.AsyncFunctionDef)) and node.name == "main":
            a = node.args
            return len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
    return None


def _resolve_arity(pipeline, resolver):
    """Check every row's declared universe against its step's signature. REFUSE.

    THREE REFUSALS, ALL AT PLAN TIME, ALL NAMING THE STEP. None of them may be a
    default: the failure this project keeps finding is a selection that quietly
    does less than it was asked, and every one of these has a plausible-looking
    silent outcome. A three-hour pipeline must not discover a contract violation
    at STEP 16.
    """
    bad = []
    for row in pipeline:
        label, scr, tag = row[0], row[1], (row[2] if len(row) > 2 else None)
        n = _declared_arity(scr, resolver)
        if n is None:
            bad.append(f"    {label:<9} {scr:<28} declares no module-level main()")
        elif n not in (0, 1):
            # A PROGRAMMING ERROR, NOT A CONFIGURATION. There is no selection that
            # makes a two-argument step runnable, so it cannot be worked around by
            # running something else; it is reported as the defect it is.
            bad.append(f"    {label:<9} {scr:<28} main() takes {n} arguments; "
                       f"the contract is main() or main(u)")
        elif tag is not None and n == 0:
            bad.append(f"    {label:<9} {scr:<28} PIPELINE_ORDER names universe "
                       f"'{tag}' but main() takes none")
        elif tag is None and n == 1:
            bad.append(f"    {label:<9} {scr:<28} main() takes a universe but "
                       f"PIPELINE_ORDER names none")
        elif tag is not None and tag not in REGISTRY:
            # THE SILENT FAILURE THE OLD _check_step_universes() CAUGHT, kept.
            # A step registered to a deleted universe is never selected -- no
            # error, no log line -- so it stops running and the run still reports
            # success. That is how the 58's steps could have outlived the 58.
            bad.append(f"    {label:<9} {scr:<28} names universe '{tag}', which the "
                       f"registry does not define (known: {', '.join(sorted(REGISTRY))})")
    if bad:
        raise SystemExit(
            "INVOCATION CONTRACT VIOLATED -- refusing to start.\n"
            + "\n".join(bad)
            + "\n  A step declares whether it takes a universe by its signature;\n"
              "  run_all.PIPELINE_ORDER declares which universe it is invoked for.\n"
              "  The two must agree. Nothing defaults.")


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
    """The run_all.py steps this selection invokes, IN ORDER, with their universe.

    Order comes from run_all.PIPELINE_ORDER and is never re-sorted: it is the thing
    check_pipeline_order.enforce verifies, and a consumer must never precede its
    producer.

    EACH ENTRY IS (label, script, tag-or-None) and tag is what main(u) will be
    GIVEN -- not a description of what the step serves. That is the whole change:
    the plan now carries the argument, so the dispatch has nothing left to decide.

    A WHOLE-RUN STEP IS ALWAYS IN THE PLAN when anything is selected. It takes no
    universe and works out from the selection what to do, which is why
    make_combined_universes can draw one comparison across whichever universes the
    run chose, and why `--universe mid` still reaches STEP 15b rather than
    reproducing the bug 15b exists to fix.
    """
    import runpy
    mod = runpy.run_path(str(ROOT / "run_all.py"), run_name="__not_main__")

    # REFUSE BEFORE ANYTHING IS PLANNED, let alone run.
    _resolve_arity(mod["PIPELINE_ORDER"], mod["script_path"])

    want = {u.tag for u in unis}
    out, dropped = [], []
    for row in mod["PIPELINE_ORDER"]:
        label, scr, tag = row[0], row[1], (row[2] if len(row) > 2 else None)
        if tag is None:
            out.append((label, scr, None))                 # whole-run
        elif tag not in REGISTRY:
            # UNREACHABLE VIA _resolve_arity, which already refused this. Kept
            # because pipeline_steps is called from print_plan as well, and a
            # defensive branch that can only fire if the refusal is removed is
            # cheaper than the silent drop it replaces.
            dropped.append((label, scr, (tag,)))
        elif tag in want:
            out.append((label, scr, tag))
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

    # ------------------------------------------------------------------
    # EVERY REGISTERED UNIVERSE, IN EVERY TABLE THAT NEEDS A ROW FOR IT
    # ------------------------------------------------------------------
    # THE CHECKS ABOVE ASK WHETHER THE SELECTION NAMES SOMETHING THAT EXISTS. This
    # asks the opposite question, and it is the one nothing was asking: whether
    # something that exists is NAMED EVERYWHERE IT HAS TO BE. Three of the seven
    # tables tolerated a missing row in silence, and run_all.PIPELINE_ORDER is the
    # one that matters -- a registered universe absent from it runs no scores, no
    # engine, no audit and no chart, and this file reports success.
    #
    # IT RUNS ON THE WHOLE REGISTRY, NOT THE SELECTION, for the reason the ordering
    # check does: coverage is a property of the repository. A run that selected one
    # universe would otherwise pass while the other is half-wired.
    import registry_coverage_check as _cov
    _, misses = _cov.coverage()
    for tag, table, why in misses:
        bad.append(f"universe {tag!r} has no entry in {table} -- {why}")

    if bad:
        raise SystemExit("REFUSING TO START -- the run names something that does "
                         "not exist, or something that exists is not named where "
                         "it must be:\n" + "\n".join(f"  {b}" for b in bad)
                         + "\n  Nothing has run. See RETIRED_UNIVERSES.md and "
                           "registry_coverage_check.py.")


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
        for label, scr, tag in plan["pipeline"]:
            # WHAT main() WILL BE GIVEN, not what the step is believed to serve.
            print(f"    {label:<9} {scr:<28} "
                  f"[{'main(' + tag + ')' if tag else 'main()'}]")
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
            print(f"    {label:<9} {scr:<28} names [{','.join(serves)}], which the registry does not define")

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

    # ----------------------------------------------------------------------
    # CAN THIS PLAN SATISFY ITS OWN DECLARED INPUTS? Before --list, before
    # --dry-run, and before STEP 10a on a real run.
    # ----------------------------------------------------------------------
    # IT ASKS A QUESTION check_pipeline_order CANNOT. That checker reasons per
    # SCRIPT and keeps each script's earliest position, so a merged step that runs
    # at several positions collapses to one and its per-invocation edges vanish --
    # make_chart.py to 10d, make_audit.py to 10c, 10c before 10d, no inversion.
    # This walks the RESOLVED PLAN, one entry per invocation, and asks whether the
    # writer of each DECLARED input comes earlier in that same plan.
    #
    # AND IT NEVER TOUCHES THE FILESYSTEM. check_inputs is satisfied by a file
    # whoever left there; this is not, which is why it fails on a warm tree as well
    # as a cold one. Every tree this project has ever run on was warm.
    #
    # IT RUNS FOR --list AND --dry-run TOO, deliberately: the question is about the
    # plan, and a plan you can print is a plan you can check.
    if plan["pipeline"] and plan.get("_run_all"):
        import check_plan_order
        _ra = plan["_run_all"]
        check_plan_order.enforce(
            plan["pipeline"], _ra["REQUIRED_INPUTS"],
            {u.tag for u in plan["universes"]}, {a.name for a in plan["arms"]},
            _ra["entry_applies"])

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
    # LOUD, AT THE START, BEFORE ANY NUMBER EXISTS. A run under a non-default
    # profile completes and exits 0, which is indistinguishable from a run that was
    # checked unless something says otherwise. profiles.gate_status() owns the
    # words; this prints them where the reader is looking before the output
    # scrolls, and the same sentence is written into v34_params{SFX}.json so it
    # survives the terminal.
    _gs = _prof.gate_status()
    if _gs:
        print("\n" + "!" * 90)
        print(f" PROFILE '{_prof.selected()}' -- {_gs}")
        print("!" * 90, flush=True)

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
    for label, scr, tag in plan["pipeline"]:
        # THE SKIP IS NOT DECIDED HERE ANY MORE. cached_panel() and
        # SCORE_BUILD_STEPS retired with the contract: the step that owns the panel
        # owns the decision not to rebuild it, so build_scores_step.run() returns
        # early and prints its own line. --fresh still works, and works for a
        # better reason -- it unlinks the panel above, so the step finds no cache
        # rather than being told to ignore one.
        #
        # THE DESIGN PREDICTED A COST HERE THAT DOES NOT EXIST, and the prediction
        # was never checked before it was stated: --list was said to lose its
        # advance notice of which score steps would skip. It never had any. The
        # skip was only ever printed at run time, so the before/after --list diff
        # is the 13 bracket fields and nothing else.
        #
        # SAFETY 4 -- fail by filename and owing step, not from inside pandas.
        # THE INVOCATION'S UNIVERSE GOES WITH IT. `tag` is this row's third field
        # and was bound by the loop above and dropped here, so the guard evaluated
        # every `u:` qualifier against the RUN's selection instead of against the
        # step being started. Under `--universe all` that made STEP 10d, mid's
        # chart, demand n100's trade logs -- written at STEP 10f and 10g, after it.
        mod["check_inputs"](label, scr, tag)
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
            # THE CONTRACT, AT THE ONE DISPATCH SITE. One branch on arity, and
            # both forms go through the same module_state.pinned() guard, the same
            # check_inputs, the same timing and logging above and below.
            _step = importlib.import_module(Path(scr).stem)
            _step.main(REGISTRY[tag]) if tag else _step.main()
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
    # AND AGAIN AT THE END, because the start banner is 200 lines up by now and
    # "DONE" is the line a reader stops at. Saying it twice is the point: the one
    # thing that must not be inferred from a clean exit is that the numbers were
    # checked.
    _gs2 = _prof.gate_status()
    if _gs2:
        print("!" * 90)
        print(f" PROFILE '{_prof.selected()}' -- {_gs2}")
        print("!" * 90, flush=True)
    collect_run_folder(plan, args, t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
