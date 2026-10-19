"""
code_checks.py -- four static and reconciliation checks, one subcommand each.

    ./venv/bin/python code_checks.py <case> [the old file's arguments]

    case                  was
    stop_callsite         stop_callsite_check.py
    transitional_asserts  transitional_asserts_check.py
    platform_identity     platform_identity_check.py
    cost_reconcile        cost_reconcile_check.py [--universe=<tag>[,<tag>...]]

Merged on 2026-10-19. The old files last exist at commit b2742a1. Each old file's
body is the function _<case> below, unchanged apart from one level of indentation
(the inside of multi-line strings is left as it was), so a case runs only its own
imports and constants. The case name is removed from sys.argv before the case
runs, so each sees the arguments its old file saw.

ONE EXCEPTION, SHARED CODE. stop_callsite_check imported tracked_py and SKIP from
platform_identity_check. Both, with what they need (subprocess, Path, ROOT,
MANIFEST), are at module level here, as they were in platform_identity_check;
stop_callsite's body no longer has that import or the sys.path line that served
it. Neither name is rebound anywhere.

ONE CASE PER PROCESS. check_all runs every case as its own subprocess.
"""
import sys

# ---------------------------------------------------------------------------
# shared by platform_identity and stop_callsite (was platform_identity_check.py)
# ---------------------------------------------------------------------------
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MANIFEST = ROOT / "TRACKED_FILES_SHA256.txt"
SKIP = 3        # check_all reads this exit code as a named skip; the reason is the last line


def tracked_py():
    """-> (tracked .py paths, where the list came from), or (None, reason).

    `git ls-files` in a checkout. Outside one, the tracked-file checksum manifest
    (TRACKED_FILES_SHA256.txt, "<sha256>  <path>" per line), whose listed .py files
    must still have their recorded checksums. Neither: no list, and the reason."""
    try:
        r = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.split(), "git ls-files"
    except FileNotFoundError:
        pass
    if not MANIFEST.exists():
        return None, (f"not a git checkout and no {MANIFEST.name}, so the tracked .py files "
                      f"cannot be listed")
    import hashlib
    files, changed = [], []
    for line in MANIFEST.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        if rel.endswith(".py"):
            files.append(rel)
            f = ROOT / rel
            if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != digest:
                changed.append(rel)
    if changed:
        return None, (f"{len(changed)} .py file(s) differ from {MANIFEST.name}, first "
                      f"{changed[0]}; the manifest does not describe this tree")
    return files, MANIFEST.name


def _stop_callsite():
    """
stop_callsite_check.py -- no call site may pass an arm's mode and sizing and drop
its drawdown stop.

v5 is (none, invvol) plus the stop and v6 is (none, provol) plus the stop: the same
mode and sizing as v1 and v3. A call site that hands the engine `mode=a.mode,
sizing=a.sizing` runs v5 as v1 with nothing saying so. The stop travels in
Arm.kwargs, so the safe spelling is `**arm.kwargs`; a call that spells mode or
sizing out must also say what it does about the stop, `drawdown_stop=...`, even
when that is None.

THE RULE. The functions that take a stop are found from the source: every function
defined in a tracked file with a `drawdown_stop` parameter. A call to one of those
names fails when
  - it passes `mode=` or `sizing=` and neither `drawdown_stop=` nor `**<x>.kwargs`.
    Any other `**` mapping (the cap's, for instance) does not excuse it; or
  - it unpacks `**name`, and `name` is assigned, anywhere in the file, a dict
    display or dict(...) call that carries mode or sizing and no drawdown_stop.
Metadata dicts that are never unpacked into such a call are not looked at.

Exit 0 when clean, 1 with every offending file:line, 3 (a named skip in check_all)
when the tracked files cannot be listed.
"""
    import ast
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent


    def stop_functions(trees):
        """Names of every function defined with a drawdown_stop parameter."""
        names = set()
        for tree in trees.values():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    a = node.args
                    if any(x.arg == "drawdown_stop" for x in a.args + a.kwonlyargs + a.posonlyargs):
                        names.add(node.name)
        return names


    def _called_name(call):
        f = call.func
        if isinstance(f, ast.Attribute):
            return f.attr
        if isinstance(f, ast.Name):
            return f.id
        return None


    def _is_arm_kwargs(expr):
        return isinstance(expr, ast.Attribute) and expr.attr == "kwargs"


    def _dict_keys(node):
        """The constant keys of a dict display or a dict(...) call, else None."""
        if isinstance(node, ast.Dict):
            return {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
            return {k.arg for k in node.keywords if k.arg is not None}
        return None


    def offences(tree, rel, targets):
        assigned = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                keys = _dict_keys(node.value)
                if keys is None:
                    continue
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        assigned.setdefault(t.id, []).append((node.lineno, keys))
        out = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _called_name(node) in targets):
                continue
            name = _called_name(node)
            kw = {k.arg for k in node.keywords if k.arg is not None}
            stars = [k.value for k in node.keywords if k.arg is None]
            if ({"mode", "sizing"} & kw and "drawdown_stop" not in kw
                    and not any(_is_arm_kwargs(x) for x in stars)):
                out.append(f"{rel}:{node.lineno}  {name}(...) passes "
                           f"{', '.join(sorted({'mode', 'sizing'} & kw))} without drawdown_stop")
            for x in stars:
                if isinstance(x, ast.Name):
                    for line, keys in assigned.get(x.id, []):
                        if {"mode", "sizing"} & keys and "drawdown_stop" not in keys:
                            out.append(f"{rel}:{node.lineno}  {name}(**{x.id}) unpacks the dict "
                                       f"at line {line}, which has mode or sizing and no "
                                       f"drawdown_stop")
        return sorted(set(out), key=lambda t: int(t.split(":")[1].split()[0]))


    def main():
        files, source = tracked_py()
        if files is None:
            print(f"stop_callsite_check: SKIP -- {source}")
            return SKIP
        trees = {}
        for rel in files:
            p = ROOT / rel
            if p.exists():
                trees[rel] = ast.parse(p.read_text(), filename=str(p))
        targets = stop_functions(trees)
        if "backtest_exposure" not in targets:
            print("stop_callsite_check: backtest_exposure has no drawdown_stop parameter; "
                  "the check has nothing to anchor on")
            return 1
        bad = []
        for rel, tree in trees.items():
            bad += offences(tree, rel, targets)
        if bad:
            print(f"stop_callsite_check: {len(bad)} site(s) pass mode or sizing without the stop:")
            for b in bad:
                print(f"    {b}")
            return 1
        print(f"stop_callsite_check: {len(files)} files ({source}); every call to "
              f"{', '.join(sorted(targets))} that names mode or sizing also names "
              f"drawdown_stop or passes **kwargs")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _transitional_asserts():
    """transitional_asserts_check.py -- the tree says the collapse is unfinished.

IT STAYS, AND IT IS GREEN BECAUSE THE WORK LANDED, NOT BECAUSE IT STOPPED
CHECKING: reintroduce one literal REGISTRY["midcap150"] in a step that takes a
universe and it fails again, as "MARKER REMOVED, HARDCODING KEPT". Deleting
it would remove the only thing in the tree that would notice.

WHAT THIS EXISTS FOR. Step 2 of the collapse (commit 5c636cf) gave the eight
per-universe steps `main(u)` while leaving their literal `REGISTRY["midcap150"]` /
`REGISTRY["nifty100"]` subscripts in place, because check_pipeline_order resolves
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
    from paths import list_dir

    ROOT = Path(__file__).resolve().parent
    MARKER = "TRANSITIONAL-ASSERT"

    # WHAT "STILL HARDCODED" ACTUALLY MEANS, and it is wider than one syntax.
    # The first version of this looked for REGISTRY["midcap150"] as a regex, and got two
    # things wrong at once. It matched its OWN marker comment -- which names the
    # subscript it warns about -- so a genuinely collapsed file still reported one. And
    # it MISSED the engines and the charts, which do not spell it that way: the engines
    # alias the import (`from universes.registry import REGISTRY as _REG`, then
    # _REG["midcap150"]) and the charts reach their universe through `import config_<tag>`.
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
        for node in ast.walk(tree):                     # module level: import config_<tag>
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
            for p in list_dir(d, "*.py"):
                src = p.read_text()
                if not _takes_universe(src, p):
                    continue
                # THE __main__ GUARD'S OWN SUBSCRIPT IS NOT A DEFECT. It supplies the
                # argument for a direct `python results/audit_step.py midcap150`, which
                # is how these are run by hand, and it survives the collapse as
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
        print("  THIS CHECK IS NOT RETIRED BY THAT. It is green because the collapse")
        print("  landed, not because it stopped checking: reintroduce one literal and")
        print("  it reports MARKER REMOVED, HARDCODING KEPT and exits non-zero again.")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _platform_identity():
    """
platform_identity_check.py -- two operations that give different bits on
different platforms are allowed only through their shared replacements.

RULE 1: every CSV read goes through config.read_table.

pandas' default read_csv float parser returns different last bits for the same
bytes on macOS and on Linux, and on either platform does not return the values
the file was written from (measured 2026-09-24; see config.read_table). One
such read anywhere on the pipeline path is enough to make two machines
disagree. This check parses every tracked .py file and fails on:

    <anything>.read_csv(...)         a direct pandas call
    from pandas import read_csv      the same call under another name

The one allowed site is config.read_table itself.

RULE 2: no pandas rolling or grouped variance. `.rolling(...).std()`,
`.rolling(...).var()`, `.groupby(...).std()/.var()` and `.transform("std")` or
`.transform("var")` gave different bits on macOS, Linux arm64 or Linux amd64
(measured 2026-09-24; see results/numerics.py). Use numerics.rolling_std,
numerics.rolling_var or numerics.group_mean_std.

Exit 0 when clean, 1 with every offending file:line otherwise, 3 (a named skip in
check_all) when the tracked files cannot be listed: outside a git checkout with no
TRACKED_FILES_SHA256.txt, or with one that no longer matches the tree.
"""
    import ast
    import sys

    ALLOWED = {("config.py", "read_table")}


    def offences(path, rel):
        tree = ast.parse(path.read_text(), filename=str(path))
        out = []

        def visit(node, fn=None):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = node.name
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "read_csv" and (rel, fn) not in ALLOWED):
                out.append(f"{rel}:{node.lineno}  .read_csv( call")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("std", "var")
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Attribute)
                    and node.func.value.func.attr in ("rolling", "groupby", "expanding")):
                out.append(f"{rel}:{node.lineno}  .{node.func.value.func.attr}(...).{node.func.attr}() -- use numerics")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "transform" and node.args
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value in ("std", "var")):
                out.append(f"{rel}:{node.lineno}  .transform({node.args[0].value!r}) -- use numerics.group_mean_std")
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pandas"):
                if any(a.name == "read_csv" for a in node.names):
                    out.append(f"{rel}:{node.lineno}  imports read_csv from pandas")
            for child in ast.iter_child_nodes(node):
                visit(child, fn)

        visit(tree)
        return out






    def main():
        files, source = tracked_py()
        if files is None:
            print(f"platform_identity_check: SKIP -- {source}")
            return SKIP
        bad = []
        for rel in files:
            bad += offences(ROOT / rel, rel)
        if bad:
            print(f"platform_identity_check: {len(bad)} call(s) bypass the shared implementations:")
            for b in bad:
                print(f"    {b}")
            return 1
        print(f"platform_identity_check: {len(files)} files ({source}), every CSV read goes through "
              f"config.read_table and no pandas rolling or grouped variance is used")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _cost_reconcile():
    """cost_reconcile_check.py -- the cost reconciliation on every cell, profile and tax setting.

    ./venv/bin/python cost_reconcile_check.py [--universe=<tag>[,<tag>...]]

A check_all delegate. For each registered universe, each arm, the research and
tradeable profiles, and tax off and on, at the default cadence: run the backtest
with the cost trail and apply results/cost_report.reconcile -- cash every day,
slippage and charges every fill, tax every financial year, and the totals; and
the investable buy & hold, held and sold on the last day, per universe. Writes
nothing. Exits 1 at the end if any combination failed, naming each with the check,
the first day and the gap; 0 if all reconcile.
"""
    import os
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[_v] = "1"
    import sys
    import time
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    import config                                                    # noqa: E402
    import cost_report                                               # noqa: E402
    import engine_core                                               # noqa: E402
    import profiles                                                  # noqa: E402
    import arms.registry as arm_reg                                  # noqa: E402
    from config import read_table                                    # noqa: E402
    from engine_core import precompute                               # noqa: E402
    from test_exposure import backtest_exposure, START_CAPITAL       # noqa: E402
    from universes.registry import REGISTRY, argv_universes, check_tags  # noqa: E402

    KEYS = ("holdings", "summary", "trades", "ranking", "decisions", "skipped")


    def cell(u, arm, panel, profile, tax_on):
        px, op, sc, bd, pc, mom20 = panel
        profiles.set_selection(profile)
        try:
            audit = {k: [] for k in KEYS}
            audit["costs"] = {"fills": [], "days": []}
            _eq, tc, _n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, audit=audit,
                                               value_at_open=True, tax_enabled=tax_on,
                                               **arm.kwargs, **profiles.cap_kwargs(u))
        finally:
            profiles.set_selection(None)
        tx = audit.get("tax")
        cost_report.reconcile(audit["costs"], audit["trades"], list(bd), float(START_CAPITAL), tc,
                              float(tx["cum_tax"]) if tx else 0.0, tax_on,
                              tx["lots"] if tx else None)
        return len(audit["trades"])


    def main(argv):
        picked = check_tags(argv_universes(argv), REGISTRY) or list(REGISTRY)
        failed, n, t0 = [], 0, time.time()
        for tag in picked:
            u = REGISTRY[tag]
            engine_core.set_tradeability(u)
            p = read_table(config.require_cache(u.score_cache, what=tag), parse_dates=["date"])
            px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
            op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
            sc = p.pivot_table(index="date", columns="symbol", values="score")
            panel = (px, op, sc, u.trading_days(px.index), precompute(px), px / px.shift(20) - 1)
            for tax_on in (False, True):
                what = f"{tag} buy & hold tax {'on' if tax_on else 'off'}"
                try:
                    cost_report.bh_costs(px, op, panel[3], float(START_CAPITAL), tax_on)
                    print(f"  PASS  {what}", flush=True)
                except cost_report.CostReconciliationError as e:
                    failed.append(f"{what}: {e}")
                    print(f"  FAIL  {what:<36} {e}", flush=True)
                n += 1
            for arm in arm_reg.ARMS.values():
                for profile in profiles.PROFILES:
                    for tax_on in (False, True):
                        what = f"{tag} {arm.name} {profile} tax {'on' if tax_on else 'off'}"
                        try:
                            fills = cell(u, arm, panel, profile, tax_on)
                            print(f"  PASS  {what:<36} {fills:>5} fills", flush=True)
                        except cost_report.CostReconciliationError as e:
                            failed.append(f"{what}: {e}")
                            print(f"  FAIL  {what:<36} {e}", flush=True)
                        n += 1
        print(f"\n{n - len(failed)} of {n} combinations reconcile "
              f"({(time.time() - t0) / 60:.1f} min)")
        for f in failed:
            print(f"  FAILED {f}")
        return 1 if failed else 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main(sys.argv[1:]))



CASES = {"stop_callsite": _stop_callsite, "transitional_asserts": _transitional_asserts,
         "platform_identity": _platform_identity, "cost_reconcile": _cost_reconcile}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CASES:
        print(__doc__)
        sys.exit(2)
    _case = CASES[sys.argv[1]]
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    _case()
