#!/usr/bin/env python3
"""check_plan_order.py -- can THIS plan satisfy its own declared inputs?

    resolved by run.py for --list, --dry-run and a real run, before STEP 10a

WHAT THIS ASKS THAT check_pipeline_order DOES NOT
    check_pipeline_order reasons about the PIPELINE: it scans each step's source
    for the files it reads and writes and looks for a consumer that precedes its
    producer. That is a property of the step ORDER and it is measured per SCRIPT.

    This asks a different question, about the PLAN: for each INVOCATION in the
    order this run will actually execute, are the inputs that invocation DECLARES
    written by an invocation that comes before it?

    THE DIFFERENCE IS THE COLLAPSE. One script now appears at several positions --
    make_chart.py is STEP 10d for mid and STEP 10h for n100 -- and
    check_pipeline_order keeps the EARLIEST position per script
    (check_pipeline_order.py:430) and unions each script's reads and writes across
    its rows (468-469). So make_chart.py collapses to 10d, make_audit.py to 10c,
    10c precedes 10d, and no inversion exists to report. Its "0 inversions" is
    correct for what it measures and silent about this.

WHAT IT CAUGHT, AND WHY NOTHING ELSE COULD
    `--universe all` on a tree with no trade logs died at STEP 10d:

        make_chart.py needs 2 file(s) that do not exist:
          MISSING results_n100/metrics/daily_trades_n100.csv     writer STEP 10g
          MISSING results_n100/metrics/daily_trades_v1_n100.csv  writer STEP 10f

    Mid's chart demanded n100's trade logs, written two and three steps LATER. The
    cause was a declaration-scope defect -- REQUIRED_INPUTS' `u:` qualifier was
    evaluated against the run's selected_tags() rather than against the
    invocation's universe -- and the ordering it produced was unsatisfiable.

THIS IS A PLAN PROPERTY, NOT A FILESYSTEM PROPERTY, AND THAT IS THE POINT
    It never calls exists(). It fails identically on a tree where every one of
    those files is already present, which is the only way it could have been
    caught before a cold run: every warm tree in this project's history had the
    files sitting there from an earlier run, and check_inputs is satisfied by a
    file whoever wrote it. Demonstrated by reverting the predicate on a fully
    populated tree and watching this fire anyway.

THE PREDICATE IS NOT REIMPLEMENTED HERE
    Which entries an invocation declares is run_all.entry_applies(), the same
    function check_inputs() calls at run time. A second copy would answer
    differently the day one of them is edited, and this check would then be
    verifying a rule the runtime does not use -- which is the shape of the defect
    it exists to catch, one level up.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def analyse(pipeline, required_inputs, usel, asel, entry_applies):
    """-> [(i, label, script, tag, entry, reason)] for every unsatisfiable input.

    `pipeline` is the RESOLVED plan -- [(label, script, tag)] in execution order,
    already narrowed to this run's selection. Position is the index, so a merged
    script appearing at several positions is several invocations here, which is
    exactly what check_pipeline_order cannot express.
    """
    # KEYED BY "<label> <script>", WHICH IS HOW A WRITER NAMES ITSELF. The third
    # element of a REQUIRED_INPUTS entry is built by run_all._step_label() as
    # f"{row[0]} {script}", so the two spellings are one definition and a rename
    # cannot silently stop matching.
    pos = {f"{label} {script}": i for i, (label, script, _t) in enumerate(pipeline)}

    bad = []
    for i, (label, script, tag) in enumerate(pipeline):
        for e in required_inputs.get(Path(script).name, []):
            if not entry_applies(e, tag, usel, asel, label, Path(script).name):
                continue
            writer = str(e[1])
            if writer not in pos:
                bad.append((i, label, script, tag, e,
                            f"its writer, {writer}, is not in this plan at all, so "
                            f"nothing in this run will write it"))
            elif pos[writer] >= i:
                where = "at the same position as" if pos[writer] == i else "AFTER"
                bad.append((i, label, script, tag, e,
                            f"its writer, {writer}, runs {where} this step "
                            f"(position {pos[writer]} vs {i})"))
    return bad


def enforce(pipeline, required_inputs, usel, asel, entry_applies, quiet=False):
    """Print the verdict; raise SystemExit on any violation. Returns the count."""
    bad = analyse(pipeline, required_inputs, usel, asel, entry_applies)
    if not quiet:
        print(f"  plan input-order check: {len(pipeline)} invocation(s), "
              f"{len(bad)} unsatisfiable declared input(s)")
    if not bad:
        return 0
    print("\n" + "!" * 90)
    print("PLAN ORDERING ERROR -- an invocation declares an input this plan writes later")
    print("!" * 90)
    for i, label, script, tag, e, why in bad:
        print(f"\n  {label}  {script}" + (f"   universe {tag!r}" if tag else "   (whole-run)"))
        print(f"    declares  {Path(e[0]).name}")
        print(f"    qualifiers {str(e[2])!r}")
        print(f"    {why}")
    print("\n  THIS IS NOT ABOUT FILES ON DISK. Nothing here was checked for")
    print("  existence; a tree where every one of these already exists fails this")
    print("  check identically, because the plan cannot produce them in this order.")
    print("\n  Fix the DECLARATION or the ORDER. Do not make the step tolerant of a")
    print("  missing input, and do not add the file by hand -- either would leave a")
    print("  plan that only works on a tree somebody warmed up earlier.")
    print("!" * 90, flush=True)
    raise SystemExit(1)


if __name__ == "__main__":
    # STANDALONE: the FULL pipeline at the default selection, which is what
    # `run.py` with no arguments resolves. run.py passes its own resolved plan.
    import runpy
    mod = runpy.run_path(str(ROOT / "run_all.py"), run_name="__not_main__")
    from universes.registry import REGISTRY
    from arms.registry import ARMS
    pipeline = [(r[0], r[1], r[2] if len(r) > 2 else None) for r in mod["PIPELINE_ORDER"]]
    enforce(pipeline, mod["REQUIRED_INPUTS"], set(REGISTRY), set(ARMS),
            mod["entry_applies"])
    print("plan input-order check: PASS")
