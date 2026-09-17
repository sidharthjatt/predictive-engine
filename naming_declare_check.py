"""
naming_declare_check.py -- DECLARE OR FAIL, AND HONOUR OR FAIL.
===============================================================

TWO GATES, AND THE SECOND IS THE ONE THAT MATTERS
    GATE 1, DECLARE. Every site that writes an artefact must carry an inline
    `# naming:` directive saying which axes its filename varies over. A site with
    no directive is a FAILURE, not a default: the bug class being closed is a
    silently omitted axis, and a permissive default reproduces it exactly.

    GATE 2, HONOUR. A declaration is a CLAIM, not a proof. A site may declare
    `arm,cadence,profile` and then write a bare literal that varies over nothing --
    which is the same defect as a commit message asserting completion without
    verifying it. So for every site declaring a non-empty axis set, this check
    proves the claim: it emits the site's name under a NON-DEFAULT selection and
    requires the tail naming.py computes to actually appear. A declaration that
    does not survive that is a FAILURE, and until this gate existed a declared site
    was worth no more than an undeclared one.

WHY THE DIRECTIVE LIVES AT THE WRITER
    A central table of 58 entries would be the fifth hardcoded list in this
    repository, and it would drift the moment someone adds a writer without
    knowing the table exists. The directive sits on the write call instead, so
    discovery picks it up where it is true and the next person adding a writer
    sees one on the line above.

DIRECTIVE SYNTAX -- immediately above the write call, or on the enclosing `def`.
    A directive above a call covers THAT CALL ONLY; the walk stops at the first
    line that is not a comment, so it can never silently adopt the statement
    after it. When a block of sibling writes shares one classification, the
    directive belongs on the `def`, where it covers all of them and a reader
    sees it before the block rather than inside it.
    # naming: arm,cadence,profile     this name varies over exactly these axes
    # naming: <axes> via <composer>   ... and <composer> is what builds it,
    #                                 checked against its MEASURED coverage in
    #                                 naming.CARRIES, not against its name
    # naming: axis-free -- <reason>   invariant to every axis; reason required
    # naming: delegated -- <where>    path arrives from a caller that declares it
    # naming: DEFECT <axis> -- <why>  known to omit an axis it should carry

WHY NON-DEFAULT IS THE ONLY HONEST TEST SELECTION
    At an all-default selection every axis contributes "", so a profile-blind
    writer and a correct one emit identical paths. The gate would pass on both.
    HONOUR_SELECTION below is deliberately non-default on all FOUR axes. It
    gained `tax` on 2026-09-17 with the tax axis itself, and that addition is the
    whole of condition 2 of the tax acceptance test: at tax=off a tax-blind
    writer and a tax-aware one emit identical paths, so the byte-exactness half
    of that test is passed by a no-op. Only a non-default probe can tell them
    apart, and only a declaration can be checked against it.
"""
import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules"}
SKIP_PREFIX = ("forensic_snapshot_",)
SELF = {"naming.py", "naming_declare_check.py"}
WRITERS = {"to_csv", "savefig", "to_parquet", "dump", "to_json", "write_text"}

DIRECTIVE = re.compile(r"#\s*naming:\s*(.+?)\s*$")

# Non-default on every axis, so no axis can hide behind an empty suffix.
HONOUR_SELECTION = {"arms": ["v1", "v3"], "cadence": 40, "profile": "tradeable",
                    "tax": True}

# THE MEMBERSHIP LIST IS GONE. Gate 2 used to ask "does this expression mention a
# blessed helper name?", which is a question about spelling. It now asks "does the
# composer this expression uses actually carry every axis the site declared?",
# which is a question about behaviour. naming.CARRIES holds the measured answer
# per composer; see the audit recorded above it. An expression whose composer is
# unknown carries nothing and fails -- a new helper must be measured before it can
# certify anything.


class Decl:
    __slots__ = ("kind", "axes", "reason", "line", "composer")

    def __init__(self, kind, axes=(), reason="", line=0):
        self.kind, self.axes, self.reason, self.line = kind, tuple(axes), reason, line
        self.composer = ""


def parse_directive(text, line):
    m = DIRECTIVE.search(text)
    if not m:
        return None
    body = m.group(1).strip()
    low = body.lower()
    if low.startswith("axis-free"):
        return Decl("axis-free", (), body.partition("--")[2].strip(), line)
    if low.startswith("delegated"):
        return Decl("delegated", (), body.partition("--")[2].strip(), line)
    if low.startswith("defect"):
        rest = body[6:].strip()
        axis = rest.partition("--")[0].strip().strip(",")
        return Decl("DEFECT", [a.strip() for a in axis.split(",") if a.strip()],
                    rest.partition("--")[2].strip(), line)
    # AXES FIRST, THEN AN OPTIONAL COMPOSER, THEN AN OPTIONAL REASON.
    #   # naming: arm,cadence,profile via artefact_tag -- why
    # Splitting on "--" before the comma split is what stops a reason clause being
    # parsed as three more axis names, which it was: audit_step declared
    # "profile -- every daily_* artefact here is named through" as an axis.
    head = body.split("--")[0].strip()
    reason = body.partition("--")[2].strip()
    composer = ""
    if " via " in head:
        head, _, composer = head.partition(" via ")
        composer = composer.strip()
    d = Decl("axes", [a.strip() for a in head.split(",") if a.strip()], reason, line)
    d.composer = composer
    return d


def _iter_py():
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if set(rel.parts) & SKIP_DIRS or rel.name in SELF:
            continue
        if any(str(rel).startswith(x) for x in SKIP_PREFIX):
            continue
        yield rel, p


def _walk_up(lines, ln):
    """The directive in the contiguous comment block immediately above a call.

    WALKING THE WHOLE BLOCK, not a fixed lookback. A directive that needs two
    lines of explanation sits further from its call than a one-liner does, and a
    fixed window silently dropped exactly those -- the longest-explained sites,
    which are the ones most worth reading. The walk stops at the first line that
    is neither a comment nor blank, so it can never cross into another statement.
    """
    i = ln - 2                      # 0-indexed line directly above the call
    while i >= 0:
        raw = lines[i].strip()
        if raw.startswith("#"):
            d = parse_directive(lines[i], i + 1)
            if d:
                # THE REASON CONTINUES across the comment lines beneath the
                # directive. Truncating at the first newline kept the shortest
                # half of every explanation -- "has no" -- and dropped the part
                # that says what goes wrong.
                tail_txt = []
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("#"):
                    if parse_directive(lines[j], j + 1):
                        break
                    tail_txt.append(lines[j].strip().lstrip("#").strip())
                    j += 1
                if tail_txt:
                    d.reason = " ".join([d.reason] + tail_txt).strip()
                return d
            i -= 1
            continue
        if raw == "":
            i -= 1
            continue
        return None
    return None


def discover():
    """Every artefact-writing call, with the declaration in force at that call."""
    sites = {}
    for rel, p in _iter_py():
        src = p.read_text(encoding="utf-8", errors="replace")
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        fn_at, fn_decl = {}, {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # SAME WALK AS A CALL-LEVEL DIRECTIVE. A fixed two-line lookback
                # here dropped any def whose directive ran to more than one line,
                # which is every def whose reason was worth writing down.
                d = _walk_up(lines, node.lineno)
                for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                    fn_at.setdefault(ln, node.name)
                    if d:
                        fn_decl.setdefault(ln, d)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if nm not in WRITERS:
                continue
            ln = node.lineno
            decl = _walk_up(lines, ln) or fn_decl.get(ln)
            try:
                expr = ast.unparse(node.args[1] if nm == "dump" and len(node.args) > 1
                                   else node.args[0]) if node.args else ""
            except Exception:
                expr = ""
            key = f"{rel}::{fn_at.get(ln, '<module>')}"
            sites.setdefault(key, []).append((ln, nm, expr, decl))
    return sites


def honour_probe():
    """Prove naming.py itself moves under HONOUR_SELECTION before trusting it."""
    import naming
    import arms.registry as ar
    import cadence
    import profiles
    import tax
    ar.set_selection(HONOUR_SELECTION["arms"])
    cadence.set_selection(HONOUR_SELECTION["cadence"])
    profiles.set_selection(HONOUR_SELECTION["profile"])
    tax.set_selection(HONOUR_SELECTION["tax"])
    return naming, naming.tail()


def added_lines(base):
    """{path: {line numbers ADDED relative to `base`}}, from git diff -U0.

    THE RATCHET EXISTS BECAUSE A BACKLOG DOES NOT BLOCK THE NEXT ENTRANT. The
    same defect recurred here within three days of being fixed, because the fix
    closed the instances it found and nothing stopped a new writer arriving
    undeclared. Gate 1 over the whole repository cannot be made blocking today --
    129 calls are undeclared. Gate 1 over the lines this change ADDED can be, and
    that is the half that keeps the count from growing.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "diff", "-U0", base, "--", "*.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    added, cur = {}, None
    for line in out.stdout.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].strip()
        elif line.startswith("@@") and cur:
            # @@ -a,b +c,d @@
            try:
                seg = line.split("+")[1].split("@@")[0].strip()
                start, _, cnt = seg.partition(",")
                start, cnt = int(start), int(cnt or 1)
            except (ValueError, IndexError):
                continue
            added.setdefault(cur, set()).update(range(start, start + cnt))
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-known-defects", action="store_true")
    ap.add_argument("--list-undeclared", action="store_true")
    ap.add_argument("--gate-declared-only", action="store_true",
                    help="block on Gate 2, on DEFECT, and on undeclared calls "
                         "inside a site that is already declared; report "
                         "undeclared calls in wholly-undeclared sites without "
                         "blocking. A site enters the gated set the moment "
                         "someone declares it and cannot leave.")
    ap.add_argument("--ratchet", metavar="BASE", default=None,
                    help="also block on any write call ADDED relative to BASE "
                         "(e.g. HEAD, origin/main) that carries no directive")
    args = ap.parse_args()

    naming, tail = honour_probe()
    if not tail:
        print("ABORT: naming.tail() is empty under the non-default honour "
              "selection. The authority itself is broken; every honour result "
              "below would be vacuous.")
        return 2

    sites = discover()
    undeclared, axis_free, delegated, defects, honoured, dishonoured = (
        [], [], [], [], [], [])

    for key in sorted(sites):
        calls = sites[key]
        undecl = [c for c in calls if c[3] is None]
        if undecl:
            undeclared.append((key, [c[0] for c in undecl]))
        for ln, nm, expr, d in calls:
            if d is None:
                continue
            if d.kind == "axis-free":
                axis_free.append((key, ln, d))
            elif d.kind == "delegated":
                delegated.append((key, ln, d))
            elif d.kind == "DEFECT":
                defects.append((key, ln, d))
            else:
                # GATE 2. Declared axes must be a subset of what the composer in
                # this expression provably carries.
                # A COMPOSER NAMED IN THE DIRECTIVE WINS over sniffing the write
                # expression. audit_step binds `tag = artefact_tag(...)` several
                # lines above its writes, so the expression at the write site says
                # only `{tag}` -- textual sniffing cannot see the composer that
                # actually built the name, and guessing from `{tag}` would credit
                # any variable that happened to be called tag.
                carried = (naming.carried_axes(d.composer) if d.composer
                           else naming.carried_axes(expr))
                missing = set(d.axes) - carried
                if missing:
                    dishonoured.append((key, ln, d, expr, sorted(missing), sorted(carried)))
                else:
                    honoured.append((key, ln, d, expr))

    n_sites = len(sites)
    n_calls = sum(len(v) for v in sites.values())
    print("=" * 78)
    print(" NAMING AUTHORITY -- DECLARE OR FAIL, HONOUR OR FAIL")
    print("=" * 78)
    print(f"  honour selection : arms={HONOUR_SELECTION['arms']} "
          f"cadence={HONOUR_SELECTION['cadence']} "
          f"profile={HONOUR_SELECTION['profile']} "
          f"tax={HONOUR_SELECTION['tax']}  -> tail {tail!r}")
    print(f"  sites / write calls          : {n_sites} / {n_calls}")
    print(f"  GATE 1  undeclared calls     : {sum(len(v) for _, v in undeclared)}"
          f"  across {len(undeclared)} site(s)")
    print(f"  GATE 2  declared + honoured  : {len(honoured)}")
    print(f"  GATE 2  declared, NOT honoured: {len(dishonoured)}")
    print(f"          axis-free declared   : {len(axis_free)}")
    print(f"          delegated            : {len(delegated)}")
    print(f"          DEFECT               : {len(defects)}")
    print()

    if dishonoured:
        print("-" * 78)
        print(" GATE 2 FAILURES -- declares an axis set it does not honour")
        print("-" * 78)
        for key, ln, d, expr, missing, carried in dishonoured:
            print(f"  {key}:{ln}")
            print(f"      declares : {','.join(d.axes)}")
            print(f"      writes   : {expr[:78]}")
            print(f"      carries  : {','.join(carried) or '(nothing -- composer unknown)'}")
            print(f"      MISSING  : {','.join(missing)}"
                  f"   -- under {tail!r} those axes vanish from the name")
        print()

    if defects:
        print("-" * 78)
        print(" KNOWN DEFECTS -- declared, and still wrong")
        print("-" * 78)
        for key, ln, d in defects:
            print(f"  {key}:{ln}")
            print(f"      missing axis : {', '.join(d.axes)}")
            print(f"      consequence  : {d.reason}")
        print()

    if undeclared and args.list_undeclared:
        print("-" * 78)
        print(" GATE 1 FAILURES -- artefact written with no `# naming:` directive")
        print("-" * 78)
        for key, lns in undeclared:
            print(f"  {key}  (lines {', '.join(map(str, lns))})")
        print()

    # THE GATED SET. A site is in it as soon as ANY of its calls is declared.
    # Undeclared calls inside such a site block; undeclared calls in a site nobody
    # has touched yet report only. That enforces at zero from the first day
    # instead of waiting for a backlog to clear with nothing holding the line.
    declared_sites = {k for k in sites
                      if any(c[3] is not None for c in sites[k])}
    blocking_undeclared = [(k, v) for k, v in undeclared if k in declared_sites]

    ratchet_hits = []
    if args.ratchet:
        add = added_lines(args.ratchet)
        if add is None:
            print(f"RATCHET: could not diff against {args.ratchet!r}; "
                  f"treating as a failure rather than a pass.")
            ratchet_hits = [("<git diff failed>", 0)]
        else:
            for key in sorted(sites):
                path = key.split("::")[0]
                for ln, nm, expr, d in sites[key]:
                    if d is None and ln in add.get(path, ()):
                        ratchet_hits.append((key, ln))

    if ratchet_hits:
        print("-" * 78)
        print(f" RATCHET FAILURES -- write call added since {args.ratchet},"
              f" no `# naming:` directive")
        print("-" * 78)
        for key, ln in ratchet_hits:
            print(f"  {key}:{ln}")
        print()

    gate1_blocking = blocking_undeclared if args.gate_declared_only else undeclared
    failed = bool(gate1_blocking) or bool(dishonoured) or bool(ratchet_hits) or (
        bool(defects) and not args.allow_known_defects)
    print("RESULT:", "FAIL" if failed else "PASS")
    if args.gate_declared_only:
        n_report = sum(len(v) for k, v in undeclared if k not in declared_sites)
        print(f"  gated set: {len(declared_sites)} site(s) declared and enforced.")
        if n_report:
            print(f"  GATE 1 (reporting only): {n_report} undeclared call(s) in "
                  f"{len([1 for k, _ in undeclared if k not in declared_sites])} "
                  f"site(s) nobody has declared yet. Not blocking.")
    if gate1_blocking:
        print(f"  GATE 1 (blocking): "
              f"{sum(len(v) for _, v in gate1_blocking)} write call(s) carry no "
              f"directive. --list-undeclared to see them.")
    if ratchet_hits:
        print(f"  RATCHET: {len(ratchet_hits)} newly added write call(s) undeclared.")
    if dishonoured:
        print(f"  GATE 2: {len(dishonoured)} declaration(s) are unproven claims.")
    if defects and not args.allow_known_defects:
        print(f"  {len(defects)} site(s) declared DEFECT and not yet fixed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
