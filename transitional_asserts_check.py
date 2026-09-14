#!/usr/bin/env python3
"""transitional_asserts_check.py -- the tree says the collapse is unfinished.

WHAT THIS EXISTS FOR. Step 2 of the collapse (commit 5c636cf) gave the eight
per-universe steps `main(u)` while leaving their literal `REGISTRY["mid"]` /
`REGISTRY["n100"]` subscripts in place, because check_pipeline_order resolves
`daily_*_{tag}.csv` to a directory by READING those literals and a loop variable
there matches nothing. The steps therefore ASSERT `u.tag` rather than using `u`.

That is a deliberate half-state, and a deliberate half-state that is recorded only
in a commit message or a conversation is indistinguishable, six days later, from a
finished one. This check makes the repository itself carry the fact. It FAILS --
non-zero exit -- for as long as any transitional assert survives.

IT CANNOT BE SILENCED BY DELETING THE MARKER. Three conditions are checked, and
the second is the one that matters:

  1. MARKER PRESENT              -> unfinished. Reported, and fatal.
  2. LITERAL WITHOUT MARKER      -> the marker was removed while the literal it
                                    describes is still there. FATAL, and reported
                                    as tampering rather than as progress.
  3. MARKER WITHOUT LITERAL      -> the collapse removed the literals but left the
                                    marker. FATAL: the marker is now a lie, and a
                                    stale warning is how a checker gets ignored.

So it goes green on exactly one state: no markers AND no literal REGISTRY[...]
subscripts in any step that takes a universe. That is the state steps 3-7 produce.

Run it directly, or read its exit code.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = "TRANSITIONAL-ASSERT"

# WHAT "STILL HARDCODED" ACTUALLY MEANS, and it is wider than one syntax.
# The first version of this looked for REGISTRY["mid"] as a regex, and got two
# things wrong at once. It matched its OWN marker comment -- which names the
# subscript it warns about -- so a genuinely collapsed file still reported one. And
# it MISSED the engines and the charts, which do not spell it that way: the engines
# alias the import (`from universes.registry import REGISTRY as _REG`, then
# _REG["mid"]) and the charts reach their universe through `import config_mid`.
# A check that passes four of eight files for a spelling reason is worse than none.
#
# The condition is not a syntax. It is: THIS STEP STILL KNOWS ITS UNIVERSE BY NAME.
# So it is tested as that -- any string constant in main() that IS a registry tag,
# plus any module-level import of that universe's config. ast is used rather than
# text so comments are invisible, which is what let the first version report a
# literal that was only being described.
#
# REGISTRY[u.tag], REGISTRY[tag] and u.metrics_dir are all invisible here: their
# slices are not string constants and they name no universe. That is the collapsed
# form, and reaching it is exactly what turns this check green.
def _hardcoded(fn, tree, tags):
    """The registry tags this step still names for itself, in code."""
    out = {n.value for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in tags}
    for node in ast.walk(tree):                     # module level: import config_mid
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for nm in names:
            for t in tags:
                if nm.split(".")[0] == f"config_{t}":
                    out.add(t)
    return sorted(out)


def _takes_universe(src, path):
    """True when this file's module-level main() declares one argument.

    The same ast read run.py._declared_arity does, and for the same reason: a step
    is not imported to find out how it is invoked.
    """
    for node in ast.parse(src, filename=str(path)).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
            a = node.args
            return len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs) == 1
    return False


def scan():
    """Every step that takes a universe, with its marker and hardcoding state."""
    sys.path.insert(0, str(ROOT))
    from universes.registry import REGISTRY
    tags = set(REGISTRY)
    rows = []
    for d in (ROOT / "results", ROOT / "nautilus"):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.py")):
            src = p.read_text()
            if not _takes_universe(src, p):
                continue
            # THE __main__ GUARD'S OWN SUBSCRIPT IS NOT A DEFECT. It supplies the
            # argument for a direct `python results/make_mid_audit.py`, which is
            # how these are run by hand, and it survives the collapse as
            # REGISTRY[sys.argv[1]] or equivalent. Only main() itself is scanned.
            tree = ast.parse(src, filename=str(p))
            fn = next(n for n in tree.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == "main")
            # The marker is a COMMENT, so ast cannot see it; it is read from the
            # source lines main() spans.
            lines = src.splitlines()[fn.lineno - 1:fn.end_lineno]
            rows.append((p, any(MARKER in l for l in lines),
                         _hardcoded(fn, tree, tags)))
    return rows


def main():
    rows = scan()
    marked = [r for r in rows if r[1]]
    untagged = [r for r in rows if not r[1] and r[2]]
    stale = [r for r in rows if r[1] and not r[2]]

    print("=" * 78)
    print(" TRANSITIONAL ASSERT CHECK -- is the collapse finished?")
    print("=" * 78)
    print(f"  steps taking a universe : {len(rows)}")
    print(f"  carrying the marker     : {len(marked)}")
    print()

    if marked:
        print(f"  UNFINISHED ({len(marked)}) -- these still name their own universe:")
        for p, _, lits in sorted(marked):
            print(f"    {p.relative_to(ROOT)!s:<34} names {', '.join(lits) or '?'}")
        print()
    if untagged:
        print(f"  MARKER REMOVED, HARDCODING KEPT ({len(untagged)}) -- this is not progress:")
        for p, _, lits in sorted(untagged):
            print(f"    {p.relative_to(ROOT)!s:<34} names {', '.join(lits)}")
        print()
    if stale:
        print(f"  STALE MARKER ({len(stale)}) -- nothing is hardcoded; remove the marker:")
        for p, _, _ in sorted(stale):
            print(f"    {p.relative_to(ROOT)!s}")
        print()

    if marked or untagged or stale:
        print("RESULT: FAIL -- the collapse (steps 3-7 of the new order) is unfinished.")
    
        return 1

    print("RESULT: PASS -- no transitional asserts remain; the collapse is complete.")
    print("  This check has done its job and can be retired with the work it tracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
