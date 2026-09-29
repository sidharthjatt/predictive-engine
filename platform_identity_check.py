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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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


if __name__ == "__main__":
    sys.exit(main())
