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
sys.path.insert(0, str(ROOT))
from platform_identity_check import tracked_py, SKIP  # noqa: E402


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


if __name__ == "__main__":
    sys.exit(main())
