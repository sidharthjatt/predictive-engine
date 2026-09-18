#!/usr/bin/env python3
"""check_all.py -- one command, against one class of defect.

    ./venv/bin/python check_all.py                  # before every commit, and in CI
    ./venv/bin/python check_all.py --since <epoch>  # after a run: did the steps write?

THE CLASS, STATED ONCE
    AN OPERATION REPORTS SUCCESS HAVING DONE PART OR NONE OF THE WORK.

    Not a family of unrelated bugs. One shape, four instances in this repository
    inside two weeks, each caught by a different accident:

      1. NINE things a new universe must be wired into, two of them invisible to
         every static check -- PAIR_CHART_REGISTRY_SIZE, read at a pipeline
         step's run time, and seed_noise_measure.LABELS, read at the import of a
         module the pipeline never imports. A survey conducted entirely through
         the static gates reported the cost as seven.
      2. seed_noise_measure and seed_noise_report UNIMPORTABLE FOR TWO WEEKS,
         from the day n50 was registered, beside four green checkers. Found by
         accident, in the control arm of an unrelated experiment.
      3. A REGEX OVER PIPELINE_ORDER MATCHING 12 OF 15 ROWS, twice, because the
         script column contains digits. Both times the half-renamed pipeline
         imported cleanly. Caught by an assertion the author happened to write.
      4. make_daily_log.py RUN DIRECTLY, WRITING NOTHING, EXITING 0 -- its
         __main__ guard exists only inside a docstring. Caught by diffing the
         output against copies saved beforehand.

    Every one of them would have passed `git commit`. Three of the four would
    have passed CI. The common property is not that the checks were missing; it
    is that SUCCESS AND PARTIAL SUCCESS WERE INDISTINGUISHABLE at the only
    moment anybody looked.

WHAT THIS DOES ABOUT IT
    Five gates, in one exit code. Gates 1-4 are new; gate 5 folds in the four
    checkers that already existed so there is ONE command rather than five, and
    so that "I ran the checks" means the same thing every time it is said.

    GATE 1  IMPORTS      every module in the repository, by name, loudly.
    GATE 2  TABLE        PIPELINE_ORDER's row count against a DECLARED constant,
                         and every script column resolved to a file on disk.
    GATE 3  ENTRY POINTS every script the pipeline invokes has a real __main__
                         block that CALLS something -- by AST, not by grep.
    GATE 4  OUTPUTS      with --since: every step's declared span contains a file
                         whose mtime moved. "Ran, wrote nothing, exited 0" fails.
    GATE 6  TAX          with --since: under tax=on the numbers must MOVE, by
                         what the ledger says. The string-only acceptance check
                         cannot tell a renaming axis from a charging one, and for
                         the axis's first day that is what it was.
    GATE 5  DELEGATES    registry_coverage_check, check_pipeline_order,
                         check_plan_order, naming_declare_check.

WHAT GATE 4 IS, AND WHAT IT IS NOT -- READ THIS BEFORE TRUSTING IT
    It was specified as "assert each step declares its outputs, then assert those
    files exist and their mtime moved". The first half is NOT implemented as a
    new table of outputs per step, deliberately, and the deviation is written
    here rather than left to be discovered.

    A second list of what each step writes would be a list that can disagree with
    the code -- the exact failure this repository has recorded under
    REQUIRED_INPUTS, PIPELINE_ORDER, REPORT_ORDER and FILES, four tables that
    each went stale once. check_pipeline_order's scanner cannot supply the list
    either: `_scan` on an entry point alone returns ZERO writes for all ten
    steps, because a step is scanned concatenated with its helpers and its tag is
    bound from the invocation. Reproducing that here would be a second copy of
    the hardest code in the repository.

    So gate 4 uses the declaration the table ALREADY CARRIES: field 3 (the
    universe a row runs for) and field 4 (row_span, the universes whose metrics
    directories the step touches). After a run, every step must have left at
    least one file with a moved mtime inside that span. It is coarser than a
    per-file manifest -- a step that writes three of its four artefacts passes --
    and it is exact on the case that has actually happened four times: a step
    that wrote NOTHING and said it was fine.

    A whole-run step (field 3 None, no span) declares nothing about where it
    writes, so gate 4 cannot check it and SAYS SO, per step, rather than
    counting it as passed.
"""
import argparse
import ast
import importlib
import subprocess
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Modules that are not this project's code, or that no import can reach without
# side effects worth avoiding. venv is obvious; the rest are directories this
# repository does not own or that hold copies rather than source.
SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules", "runs",
             "pre_repoint_baseline"}
SKIP_PREFIX = ("forensic_snapshot_",)

# The four checkers this folds in. Each already exits non-zero on failure; this
# runs them and reports them together rather than replacing them, because each
# one's message is better than any summary of it.
DELEGATES = ("registry_coverage_check.py", "check_pipeline_order.py",
             "check_plan_order.py", "naming_declare_check.py")

# naming_declare_check reports a KNOWN, PRE-EXISTING count of undeclared write
# calls and exits 1 for it. That number was 111 before this checker existed and
# is not this checker's business to fix; what IS its business is that the number
# does not GROW unnoticed. Declared here, checked below, and a mismatch in
# either direction is reported.
NAMING_UNDECLARED_BASELINE = 111

# MODULES KNOWN NOT TO IMPORT, EACH WITH ITS REASON. An unlisted failure is a
# gate-1 failure; so is a LISTED module that starts importing, because an
# exception nobody removes is how a list like this rots. The whole point of this
# checker is that a green run means something, and a checker that is permanently
# red means nothing at all -- but the cure for that is a declaration with a
# reason, not a lowered bar.
#
# NONE OF THESE FOUR IS THE DEFECT CLASS. Two are dead scripts importing a module
# this repository does not contain, one wants an optional dependency, and one
# refuses at import BY DESIGN. They are declared so that the fifth failure --
# which will be the defect class -- is visible the moment it appears.
KNOWN_UNIMPORTABLE = {
    "diagnostics/membership/analyse.py":
        "needs pdfplumber, an optional dependency not in requirements.txt",
    "results/audit_leakage.py":
        "imports `engine_v2`, a module that does not exist in this repository "
        "-- a dead script left from before the engine was renamed",
    "results/stability_test.py":
        "imports `engine_v2`, same as audit_leakage.py -- dead script",
    "results/save_ewma_comparison.py":
        "refuses at import BY DESIGN: importing it is running it, and it will "
        "not overwrite a hand-maintained file. Correct behaviour, not a defect.",
}


class Result:
    def __init__(self):
        self.failures = []
        self.notes = []

    def fail(self, gate, what, detail=""):
        self.failures.append((gate, what, detail))

    def note(self, text):
        self.notes.append(text)


# ---------------------------------------------------------------------------
# GATE 1 -- every module imports
# ---------------------------------------------------------------------------
def gate_imports(res):
    """Import every module in the repository and name the ones that refuse.

    THIS IS THE GATE THAT WOULD HAVE CAUGHT seed_noise ON DAY ONE. Those two
    modules raised SystemExit at import from the moment n50 was registered, and
    nothing imported them: not run_all, not any checker, not any test. They are
    run by hand, so the failure waited two weeks for a person.
    """
    mods = []
    for p in sorted(ROOT.rglob("*.py")):
        if any(x in SKIP_DIRS for x in p.parts): continue
        if any(x.startswith(SKIP_PREFIX) for x in p.parts): continue
        if p.resolve() == Path(__file__).resolve(): continue
        rel = p.relative_to(ROOT)
        mods.append((rel, p.stem if len(rel.parts) == 1
                     else ".".join(rel.with_suffix("").parts)))
    for path in (ROOT / "results", ROOT / "nautilus"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    bad = 0
    known = set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for rel, name in mods:
            try:
                importlib.import_module(name)
            except BaseException as e:               # SystemExit included, on purpose
                first = str(e).splitlines()[0] if str(e) else ""
                if str(rel) in KNOWN_UNIMPORTABLE:
                    known.add(str(rel))
                    continue
                res.fail("GATE 1 imports", str(rel),
                         f"{type(e).__name__}: {first[:120]}")
                bad += 1
            else:
                if str(rel) in KNOWN_UNIMPORTABLE:
                    res.fail("GATE 1 imports", str(rel),
                             "is on KNOWN_UNIMPORTABLE and now imports fine. "
                             "Remove the entry; a stale exception is how the "
                             "list stops meaning anything.")
                    bad += 1
    res.note(f"GATE 1  {len(mods) - bad - len(known)} of {len(mods)} modules "
             f"import, {len(known)} known-unimportable and declared")
    return len(mods)


# ---------------------------------------------------------------------------
# GATE 2 -- the table is the size it says it is, and every script exists
# ---------------------------------------------------------------------------
def gate_table(res):
    """Row count against run_all.PIPELINE_ROW_COUNT, and every script resolved.

    THE ROW IS READ BY INDEX, NEVER MATCHED. row[1] is the script; nothing here
    constructs a pattern over the row's text, because a pattern over this table
    is precisely what matched 12 of 15 rows twice. A checker that re-enacted the
    defect while checking for it would be worse than no checker.
    """
    # THE IMPORT IS GUARDED, because run_all REFUSES AT IMPORT when the table is
    # half-edited -- _step_label cannot name a producer, and it raises SystemExit
    # before this gate can look at a single row. That refusal is correct and it is
    # the thing that caught the 12-of-15 rename twice. What was wrong is that it
    # killed the checker mid-run, so the operator saw one raw message and no
    # report. Caught here and reported as a gate-2 failure, with the rest of the
    # gates still running.
    try:
        import run_all
    except BaseException as e:
        res.fail("GATE 2 table", "run_all is unimportable",
                 f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")
        res.note("GATE 2  NOT CHECKED -- run_all does not import")
        return []
    rows = run_all.PIPELINE_ORDER
    declared = getattr(run_all, "PIPELINE_ROW_COUNT", None)
    if declared is None:
        res.fail("GATE 2 table", "run_all.PIPELINE_ROW_COUNT",
                 "not declared; a bulk edit over PIPELINE_ORDER cannot be checked")
    elif len(rows) != declared:
        res.fail("GATE 2 table", "row count",
                 f"PIPELINE_ORDER has {len(rows)} rows, PIPELINE_ROW_COUNT says "
                 f"{declared}. One of them is wrong; if a row was added, update "
                 f"the constant by hand.")
    # AND EVERY ROW'S UNIVERSE IS A REGISTERED ONE. This is the half-rename
    # check, and it is the one that speaks to instance 3 in the header. The row
    # COUNT does not catch that defect -- a bulk edit that rewrites 12 of 15 tag
    # values leaves 15 rows -- and run_all already refuses at import when
    # _step_label cannot name a producer. What this adds is WHERE: the failure
    # arrives naming the rows that were missed, at the table, instead of naming
    # the first consumer that could not find a producer.
    from universes.registry import REGISTRY
    missing = stale = 0
    for row in rows:
        label, script = row[0], row[1]
        tag = row[2] if len(row) > 2 else None
        p = run_all.script_path(script)
        if not Path(p).exists():
            res.fail("GATE 2 table", f"{label} {script}",
                     f"resolves to {p}, which does not exist")
            missing += 1
        if tag is not None and tag not in REGISTRY:
            res.fail("GATE 2 table", f"{label} {script}",
                     f"names universe {tag!r}, which the registry does not "
                     f"define. Known: {', '.join(sorted(REGISTRY))}. A bulk edit "
                     f"over this table covered part of it.")
            stale += 1
    res.note(f"GATE 2  {len(rows)} rows (declared {declared}), "
             f"{len(rows) - missing} scripts resolve, "
             f"{len(rows) - stale} rows name a registered universe")
    return rows


# ---------------------------------------------------------------------------
# GATE 3 -- a script the pipeline invokes must do something when invoked
# ---------------------------------------------------------------------------
def _has_live_main(path):
    """True when a module-level `if __name__ == "__main__":` block CALLS something.

    BY AST, NOT BY GREP, and the difference is the whole gate.
    make_daily_log.py contains the string "__main__" -- inside a docstring
    explaining that its body was moved out of the guard. A text search passes it.
    Running it does nothing and exits 0.

    This repository has already recorded a scanner matching a comment ABOUT code
    rather than code, twice, in check_pipeline_order's own header. This is the
    third, and it is why the check parses.
    """
    try:
        tree = ast.parse(Path(path).read_text())
    except SyntaxError as e:
        return None, f"does not parse: {e}"
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and getattr(node.test.left, "id", "") == "__name__"):
            if any(isinstance(n, ast.Call) for n in ast.walk(node)):
                return True, ""
            return False, "has a __main__ block that calls nothing"
    return False, ("has no module-level __main__ block; run directly it does "
                   "nothing and exits 0")


def gate_entry_points(res, rows):
    if not rows:
        res.note("GATE 3  NOT CHECKED -- no pipeline table")
        return
    import run_all
    seen, bad = [], 0
    for row in rows:
        script = row[1]
        if script in seen: continue
        seen.append(script)
        p = run_all.script_path(script)
        if not Path(p).exists(): continue          # already reported by gate 2
        ok, why = _has_live_main(p)
        if not ok:
            res.fail("GATE 3 entry points", script, why)
            bad += 1
    res.note(f"GATE 3  {len(seen) - bad} of {len(seen)} pipeline scripts have a "
             f"live __main__ block")


# ---------------------------------------------------------------------------
# GATE 4 -- a step that ran must have written something where it said it would
# ---------------------------------------------------------------------------
def gate_outputs(res, rows, since, sel):
    """After a run: every step's declared span must hold a file whose mtime moved.

    See the module docstring for what this is and is not. The span comes from the
    row itself -- field 3 for a per-universe step, row_span() for a step that
    declares one -- so there is no second table to go stale.
    """
    if not rows:
        res.note("GATE 4  NOT CHECKED -- no pipeline table")
        return
    import run_all
    from universes.registry import REGISTRY
    if since is None:
        res.note("GATE 4  SKIPPED -- needs --since <epoch>, i.e. a run to check "
                 "against. Not counted as passed.")
        return
    checked = unverifiable = 0
    for row in rows:
        label, script = row[0], row[1]
        tag = row[2] if len(row) > 2 else None
        span = run_all.row_span(row) if len(row) > 3 else ()
        tags = (tag,) if tag else tuple(span)
        if sel != "all":
            want = {t.strip() for t in sel.split(",")}
            tags = tuple(t for t in tags if t in want)
            if not tags and (tag or span):
                continue                       # not part of this run's selection
        if not tags:
            unverifiable += 1
            res.note(f"    {label} {script}: declares no universe and no span -- "
                     f"gate 4 cannot check where it writes")
            continue
        moved = []
        for t in tags:
            u = REGISTRY.get(t)
            if u is None: continue
            d = Path(u.metrics_dir)
            if not d.exists(): continue
            moved += [f for f in d.rglob("*")
                      if f.is_file() and f.stat().st_mtime >= since]
        checked += 1
        if not moved:
            res.fail("GATE 4 outputs", f"{label} {script}",
                     f"ran, exited 0, and left no file with a moved mtime under "
                     f"{', '.join(str(REGISTRY[t].metrics_dir.name) for t in tags if t in REGISTRY)}")
    res.note(f"GATE 4  {checked} steps checked against --since, "
             f"{unverifiable} not checkable (no declared span)")


# ---------------------------------------------------------------------------
# GATE 5 -- the four that already existed, run together
# ---------------------------------------------------------------------------
def gate_delegates(res):
    for name in DELEGATES:
        p = ROOT / name
        if not p.exists():
            res.fail("GATE 5 delegates", name, "not found")
            continue
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True)
        if name == "naming_declare_check.py":
            # ITS FAILURE IS A KNOWN NUMBER, AND THE CHECK IS THAT IT DOES NOT GROW.
            import re
            m = re.search(r"GATE 1 \(blocking\): (\d+) write call", r.stdout)
            n = int(m.group(1)) if m else None
            if n is None:
                res.fail("GATE 5 delegates", name,
                         "could not read its undeclared-write count")
            elif n > NAMING_UNDECLARED_BASELINE:
                res.fail("GATE 5 delegates", name,
                         f"undeclared write calls rose to {n} from a baseline of "
                         f"{NAMING_UNDECLARED_BASELINE}")
            else:
                res.note(f"GATE 5  {name}: {n} undeclared writes "
                         f"(baseline {NAMING_UNDECLARED_BASELINE})")
            continue
        if r.returncode != 0:
            tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-3:]
            res.fail("GATE 5 delegates", name,
                     f"exit {r.returncode}: " + " | ".join(tail))
        else:
            res.note(f"GATE 5  {name}: exit 0")


# ---------------------------------------------------------------------------
# GATE 6 -- the tax axis CHARGES tax, it does not merely rename files
# ---------------------------------------------------------------------------

def gate_tax(res, since, sel):
    """CONDITION 3: under tax=on the numbers must move, by what the ledger says.

    WHAT THE STRING-ONLY CHECK COULD NOT DISTINGUISH, AND FOR HOW LONG.
    tax_acceptance_check.py asks two questions, and says plainly that it "checks
    NAMES, not CONTENTS":

        CONDITION 1  at the default, does every composer emit the same string?
        CONDITION 2  off the default, does every composer MOVE?

    Both are satisfied by an axis that renames artefacts and charges nothing.
    From the day the axis landed (7846f67, 2026-09-17) until 21c6624 that is
    exactly what it was: backtest_exposure's tax_enabled defaulted to False at
    every call site on the published path, so `--tax on` produced 36 of 40
    suffixed artefacts BYTE-IDENTICAL to their untaxed twins and the other four
    differed only in a header label. Both conditions passed throughout.

    IT IS THE TRAP THAT CHECK'S OWN DOCSTRING OPENS WITH, ONE LEVEL UP. It warns
    that "AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE SAME STRING" and builds
    condition 2 to catch that. What it cannot catch is a RENAMING axis and a
    CHARGING axis producing the same strings -- which they do, because the suffix
    is composed from the selection and not from anything the engine did with it.

    SO THIS GATE ASSERTS CONTENTS, AND IT LIVES HERE RATHER THAN THERE BECAUSE IT
    NEEDS A REAL RUN. tax_acceptance_check runs standalone with no caches and no
    engine, and correctly declines to pretend otherwise. --since already means a
    run happened.

    TWO PARTS, AND THE SECOND IS AN INEQUALITY ON PURPOSE:

      (i)  v34_equity<SFX>'s v2 column at the final session EQUALS FY_EQUITY's
           last close_equity, to a paisa. Two independent paths -- the engine
           under tax=on, and tax_report's own re-run -- must land on the same
           rupee.
      (ii) v34_equity<SFX> differs from the untaxed v34_equity by AT LEAST
           cum_tax.

    (ii) IS NOT AN EQUALITY, AND AN EQUALITY THERE WOULD FAIL ON A CORRECT
    IMPLEMENTATION. The equity gap EXCEEDS the cash taken, by the compounding the
    removed capital no longer earns: measured on midcap50, gap Rs 761,619.36
    against cum_tax Rs 492,955.59, a difference of Rs 268,663.77 -- 35.3% of the
    gap. bh_lots_after_tax.py states the mechanism: "the capital it removes stops
    compounding for the rest of the run". THAT IS THE AXIS WORKING. The identity
    that IS an equality is the one reconcile() already checks -- the per-year
    statement summing to the engine's cum_tax -- and it is checked there, at that
    tolerance, rather than restated here.

    SKIPPED, NOT PASSED, when no tax artefacts are on disk: a tax=off run writes
    none, and this gate says so rather than counting silence as agreement.
    """
    import csv
    if since is None:
        res.note("GATE 6  SKIPPED -- needs --since, i.e. a run to check against. "
                 "Not counted as passed.")
        return
    try:
        sys.path.insert(0, str(ROOT))
        from universes.registry import REGISTRY
    except Exception as e:
        res.fail("GATE 6 tax", "registry", f"{type(e).__name__}: {e}")
        return
    tags = sorted(REGISTRY) if sel in (None, "all") else [t.strip() for t in sel.split(",")]
    checked = 0
    for t in tags:
        u = REGISTRY.get(t)
        if u is None:
            continue
        M = Path(u.metrics_dir)
        taxed = M / "v34_equity_tax.csv"
        plain = M / "v34_equity.csv"
        fy = M / f"FY_EQUITY_{t}_v2_tax.csv"
        if not fy.exists():
            fy = next(iter(sorted(M.glob("FY_EQUITY_*_tax.csv"))), None)
        stmt = next(iter(sorted(M.glob("FY_TAX_STATEMENT_*_tax.csv"))), None)
        if not taxed.exists() or fy is None or stmt is None:
            continue
        checked += 1

        def col(path, name):
            with open(path, newline="") as fh:
                rows = list(csv.DictReader(fh))
            return [r for r in rows], rows[-1]

        trows, tlast = col(taxed, None)
        if "v2_invvol_breadth" not in tlast:
            res.fail("GATE 6 tax", f"{t} v34_equity_tax.csv",
                     "no v2_invvol_breadth column to check")
            continue
        t_final = float(tlast["v2_invvol_breadth"])

        with open(fy, newline="") as fh:
            fyr = list(csv.DictReader(fh))
        fy_final = float(fyr[-1]["close_equity"])

        # (i) EXACT, to a paisa.
        if abs(t_final - fy_final) > 0.01:
            res.fail("GATE 6 tax", f"{t} taxed equity vs FY_EQUITY",
                     f"v34_equity_tax v2 final Rs {t_final:,.2f} against "
                     f"FY_EQUITY close_equity Rs {fy_final:,.2f} -- two paths "
                     f"through the same engine disagree by Rs "
                     f"{abs(t_final-fy_final):,.2f}")
            continue

        if not plain.exists():
            res.note(f"GATE 6  {t}: no untaxed v34_equity.csv to compare against")
            continue
        with open(plain, newline="") as fh:
            prows = list(csv.DictReader(fh))
        p_final = float(prows[-1]["v2_invvol_breadth"])

        with open(stmt, newline="") as fh:
            srows = list(csv.DictReader(fh))
        cum = sum(float(r["total_tax"]) for r in srows)

        gap = p_final - t_final
        # (ii) AT LEAST, never equal -- see the docstring.
        if gap < cum - 0.01:
            res.fail("GATE 6 tax", f"{t} taxed equity vs ledger",
                     f"the taxed curve is only Rs {gap:,.2f} below the untaxed "
                     f"one, which is LESS than the Rs {cum:,.2f} the ledger says "
                     f"was taken. Tax was named but not charged.")
            continue
        res.note(f"GATE 6  {t}: taxed equity == FY_EQUITY to a paisa; gap Rs "
                 f"{gap:,.2f} >= cum_tax Rs {cum:,.2f} "
                 f"(compounding Rs {gap-cum:,.2f})")
    if checked == 0:
        res.note("GATE 6  SKIPPED -- no tax artefacts on disk (a tax=off run "
                 "writes none). Not counted as passed.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", type=float, default=None,
                    help="epoch seconds; gate 4 checks that steps wrote after it")
    # WHICH UNIVERSES THE RUN SELECTED. Without it gate 4 would demand that every
    # registered universe's steps wrote, and fail a `--universe nifty50` run for
    # midcap150 not moving -- which is the run doing exactly what it was asked.
    # A checker that fails correct behaviour teaches people to ignore it.
    ap.add_argument("--universe", default="all",
                    help="comma-separated tags the run selected, or 'all'")
    args = ap.parse_args(argv)

    res = Result()
    print("=" * 78)
    print(" check_all.py -- an operation must not report success having done "
          "part of the work")
    print("=" * 78)
    gate_imports(res)
    rows = gate_table(res)
    gate_entry_points(res, rows)
    gate_outputs(res, rows, args.since, args.universe)
    gate_delegates(res)
    gate_tax(res, args.since, args.universe)

    print()
    for n in res.notes:
        print("  " + n)
    print()
    if res.failures:
        print("!" * 78)
        print(f"FAILURES: {len(res.failures)}")
        print("!" * 78)
        for gate, what, detail in res.failures:
            print(f"\n  [{gate}]  {what}")
            if detail:
                print(f"      {detail}")
        print()
        return 1
    print("RESULT: PASS -- all six gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
