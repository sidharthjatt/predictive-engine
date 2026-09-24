#!/usr/bin/env python3
"""registry_coverage_check.py -- every registered universe, in every table that
needs a row for it. A missing entry NAMES THE TAG AND THE TABLE and refuses.

THE DEFECT THIS CLOSES, AND IT IS A PATTERN RATHER THAN SEVEN BUGS
    A universe is registered in universes/registry.py. Seven other tables then
    have to carry a row for it, and until this existed, three of them tolerated a
    missing row SILENTLY:

      DISPLAY           degrades via .get(t, t) -- the chart is drawn with the raw
                        tag where a display name belongs, and nothing says so.
      PIPELINE_ORDER    raises NOTHING. A registered universe with no rows here
                        runs NO per-universe steps: no scores, no engine, no audit,
                        no chart. run.py reports success over a pipeline that did
                        a fraction of the work. This is the worst of the three.
      REQUIRED_INPUTS   leaves that universe's inputs unguarded, so an ordering
                        fault reappears as the bare pandas traceback the table
                        exists to replace.

    The other four already refuse -- REPORT_ORDER and COLOURS raise by name, FILES
    raises KeyError, LIQUIDITY is documented as optional -- and they are checked
    here anyway, in one place, because coverage that is enforced in four different
    files by four different mechanisms is not a property anybody can read off.

    A TABLE THAT SILENTLY TOLERATES A MISSING ENTRY IS INDISTINGUISHABLE FROM A
    TABLE THAT COVERS IT. Same family as the silent fallback: the failure mode is
    not an error, it is a quieter success. See KNOWN_ISSUES.md, instance seven.

WHY THE TABLES ARE READ STATICALLY AND NOT BY IMPORTING THEM
    make_combined_universes.py REFUSES AT IMPORT when COLOURS has no row for a
    registered universe -- which is the correct behaviour and would make this
    checker die on the one case it exists to report. It would report nothing and
    exit non-zero from somebody else's SystemExit, naming one table when several
    may be missing. So its four tables are read with ast, from source.

    FILES IS NOT A MODULE-LEVEL TABLE AT ALL. It is built inside main(). Until
    2026-09-24 that was `FILES = {}` followed by one `FILES["<tag>"] = (...)` per
    universe, and _subscript_keys read the constant keys. Since 2026-09-24 it is
    one loop, `for tag in tags: FILES[tag] = (...)`, over the run's selection, so
    it covers every registered universe by construction. _subscript_keys reports
    that as a loop-built table (every tag covered) rather than as eight holes.

THREE TABLES LEFT THIS CHECK ON 2026-09-16, AND IT SAYS SO RATHER THAN SHRINKING
    Phase 2 moved make_combined_universes' DISPLAY, COLOURS and LIQUIDITY into
    universes/registry.py as Universe fields WITH NO DEFAULT. This check used to
    cover them; it no longer does, and that is an INCREASE in coverage, not a
    reduction: a field with no default cannot be forgotten, because the row fails
    at CONSTRUCTION with a TypeError naming the field, before anything imports
    this checker. Those three tables stopped being NEEDED rather than being
    silenced.

    IT IS WRITTEN DOWN BECAUSE THE TABLE COUNT DROPPED FROM 13 TO 10, and a check
    that covers less than it did is exactly the thing this repository keeps
    catching. LIQUIDITY's declared absence survives the move as
    `liquidity_note=None`; _declared_keys, which told a declaration from a hole,
    went with it -- the constructor now enforces presence and None IS the
    declaration.

THE REQUIRED_INPUTS ROWS CANNOT FAIL ANY MORE, AND THAT IS NOT A PASS
    Step 8 made run_all.REQUIRED_INPUTS a comprehension over REGISTRY, so the four
    `run_all.REQUIRED_INPUTS [...]` rows below are derived from the same source
    this checker compares them against. They are green by construction and a
    reader must not take them as evidence of anything.

    THEY ARE KEPT BECAUSE THE DERIVATION IS NOT THE GUARANTEE. What they now check
    is that the comprehension actually produced an entry per universe per
    consumer -- a `for u in REGISTRY.values()` that someone later narrows to a
    literal pair, or a consumer key added without a loop, fails here. That is a
    smaller claim than the one the rows made before step 8, and it is written down
    rather than left for someone to infer from four green lines.

A TABLE THAT CANNOT BE FOUND IS A FAILURE, NOT AN EMPTY RESULT
    If a table is renamed or deleted, a checker that reads it as "no keys" would
    report every universe missing, or -- worse, depending on how it is written --
    nothing at all. Each reader below returns None for "not found" and that is
    reported as its own line, because a coverage check that is silently checking
    nothing is the defect it is meant to catch, one level up.

Run it directly, or read its exit code. run.py calls coverage() from preflight().
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COMBINED = ROOT / "results" / "make_combined_universes.py"
RUN_ALL = ROOT / "run_all.py"


def _dict_keys(tree, name):
    """The string keys of a module-level `NAME = {...}` literal, or None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return {k.value for k in node.value.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return None


def _tuple_items(tree, name):
    """The string items of a module-level `NAME = (...)` literal, or None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List)):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return {e.value for e in node.value.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return None


LOOP_BUILT = object()   # _subscript_keys: the table is filled by a loop variable


def _subscript_keys(tree, name):
    """The constant keys assigned as `NAME[...] = ...` anywhere, or None if NAME
    is never bound at all. LOOP_BUILT when the keys are a `for` loop's variable
    (`for tag in tags: NAME[tag] = ...`), which covers whatever is iterated."""
    bound = any(isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
                for n in ast.walk(tree))
    if not bound:
        return None
    out = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                    and t.value.id == name and isinstance(t.slice, ast.Constant)):
                out.add(t.slice.value)
    loop_vars = {f.target.id for f in ast.walk(tree)
                 if isinstance(f, ast.For) and isinstance(f.target, ast.Name)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                        and t.value.id == name and isinstance(t.slice, ast.Name)
                        and t.slice.id in loop_vars and not out):
                    return LOOP_BUILT
    return out


def _run_all():
    """run_all.py's module namespace, without running it. The same read
    check_pipeline_order does, and for the same reason: PIPELINE_ORDER and
    REQUIRED_INPUTS are data, and re-parsing them by hand would be a second
    reader that can disagree with the first."""
    import runpy
    return runpy.run_path(str(RUN_ALL), run_name="__not_main__")


def _required_inputs_by_universe(required, registry):
    """consumer -> the set of universes its entries name.

    AN ENTRY BELONGS TO A UNIVERSE BY EITHER OF TWO ROUTES, because the table uses
    both and neither alone is sufficient:
      - its qualifier carries `u:<tag>`   (nt_execute, nt_export_scores, make_chart)
      - its PATH lies under that universe's metrics_dir  (make_combined_universes,
        whose entries are qualified by ARM and carry the universe in the path)
    """
    out = {}
    for consumer, entries in required.items():
        for e in entries:
            path = str(e[0])
            quals = [q.strip() for q in (e[2] if len(e) > 2 else "").split(",")]
            for tag, u in registry.items():
                if f"u:{tag}" in quals or path.startswith(str(u.metrics_dir)):
                    out.setdefault(consumer, set()).add(tag)
    return out


def coverage(registry=None):
    """-> (rows, misses).

    rows   [(table, covered-tags-or-None)] for the report
    misses [(tag, table, consequence)] -- empty means every table covers every tag
    """
    if registry is None:
        from universes.registry import REGISTRY as registry
    tags = set(registry)

    import universes.registry as _reg
    comb = ast.parse(COMBINED.read_text(), filename=str(COMBINED))
    mod = _run_all()

    pipeline_by_script = {}
    for row in mod["PIPELINE_ORDER"]:
        if len(row) > 2 and row[2]:
            pipeline_by_script.setdefault(row[1], set()).add(row[2])
    required_by_consumer = _required_inputs_by_universe(mod["REQUIRED_INPUTS"], registry)

    # (label, covered set or None, consequence of a missing row)
    tables = [
        ("universes/registry.REPORT_ORDER", set(_reg.REPORT_ORDER),
         "dropped from every combined report (report_order raises)"),
        ("make_combined_universes.FILES", _subscript_keys(comb, "FILES"),
         "KeyError at FILES[t], deep in the draw, naming nothing"),
    ]
    # A LOOP-BUILT TABLE COVERS THE SELECTION, which is every registered universe
    # when nothing narrows it. Reported as covering all tags, by construction.
    tables = [(label, set(tags) if covered is LOOP_BUILT else covered, why)
              for label, covered, why in tables]
    for script, covered in sorted(pipeline_by_script.items()):
        tables.append((f"run_all.PIPELINE_ORDER [{script}]", covered,
                       "SILENT -- that step never runs for this universe"))
    for consumer, covered in sorted(required_by_consumer.items()):
        tables.append((f"run_all.REQUIRED_INPUTS [{consumer}]", covered,
                       "SILENT -- this universe's inputs are unguarded"))

    misses = []
    for label, covered, why in tables:
        if covered is None:
            misses.append(("(the table itself)", label,
                           "NOT FOUND -- renamed or deleted; this check was "
                           "covering nothing"))
            continue
        for t in sorted(tags - covered):
            misses.append((t, label, why))
    return tables, misses


def main(argv=None):
    tables, misses = coverage()
    from universes.registry import REGISTRY
    tags = sorted(REGISTRY)

    print("=" * 86)
    print(" REGISTRY COVERAGE -- every registered universe, in every table that needs it")
    print("=" * 86)
    print(f"  registered universes : {', '.join(tags)}")
    print(f"  tables checked       : {len(tables)}")
    print()
    for label, covered, _ in tables:
        shown = "TABLE NOT FOUND" if covered is None else ", ".join(sorted(covered)) or "(empty)"
        mark = " " if covered is not None and not (set(tags) - covered) else "!"
        print(f"  {mark} {label:<52} {shown}")
    print()

    if misses:
        print("  MISSING " + "-" * 76)
        for tag, label, why in misses:
            print(f"    universe {tag!r} has no entry in {label}")
            print(f"        consequence: {why}")
        print()
        print(f"RESULT: FAIL -- {len(misses)} missing entr(y/ies). A table that "
              f"silently tolerates a")
        print("  missing entry is indistinguishable from one that covers it. Add the "
              "row, or")
        print("  remove the universe from the registry; do not make the consumer "
              "tolerant.")
        return 1

    print("RESULT: PASS -- every registered universe has an entry in every table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
