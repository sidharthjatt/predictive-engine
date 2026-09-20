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
    GATE 8  DATA SOURCE  every v34_params*.json names the price data it was
                         built from -- resolved raw_data_dir, symlink target and a
                         sha256 over the whole input -- and that source is still
                         the one the registry uses. FAILS CLOSED: a missing field
                         is a failure. This is the only gate that opens a price
                         file. It exists because midcap150's tradeable artefacts
                         were built on a source the tree no longer has, and the
                         other seven were green for three days.
    GATE 7  LTCG         the artefacts' claim about the long-term branch must
                         match the lots. Fails when a universe's longest hold
                         crosses LTCG_HOLD_DAYS while HOLDING_PERIOD still says
                         the branch does not fire. This is the gate whose absence
                         let 443- and 588-day lots appear unannounced.

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


# THE SEVEN, BY NUMBER, so the verdict can subtract rather than be told a total.
# A gate added below without a line here would not be counted, which is the same
# defect this file exists to catch, so the count is asserted against it in main().
ALL_GATES = (1, 2, 3, 4, 5, 6, 7, 8)


class Result:
    """Failures, notes, and -- ADDED 2026-09-20 -- WHICH GATES DID NOT RUN.

    THE DEFECT THIS FIXES IS NOT A WRONG NUMBER. Every skip below was already
    printed, honestly, in the body: "GATE 4  SKIPPED -- needs --since ... Not
    counted as passed." The summary line then said "RESULT: PASS -- all seven
    gates" over the top of it. Both lines were produced by the same run and only
    one of them is read, because a verdict line is what a verdict line is for.

    A CHECK THAT REPORTS HONESTLY IN ITS BODY AND MISREPORTS IN ITS SUMMARY is
    its own shape, and it is not the "written, declared to be the fix, never
    wired" class this repository already tracks: the body here was wired, ran,
    and was correct. Nothing was unwired and no literal was stale. The summary
    simply did not read what the body had written -- so the cure is to make the
    verdict a FUNCTION of the recorded skips rather than a constant string.

    A SKIP STAYS LEGITIMATE AND STAYS EXIT 0. Gate 4 and gate 6 cannot assert
    anything without a run to check against; refusing to run them is correct,
    and turning a skip into an error would make the checker permanently red,
    which is the failure mode declared at KNOWN_UNIMPORTABLE above. What is not
    legitimate is a skip that the verdict line conceals.
    """

    def __init__(self):
        self.failures = []
        self.notes = []
        self.skipped = {}

    def fail(self, gate, what, detail=""):
        self.failures.append((gate, what, detail))

    def note(self, text):
        self.notes.append(text)

    def skip(self, gate_no, text, why):
        """Record that gate `gate_no` did not assert, and say so in the body too.

        `why` is the short reason the verdict line carries; `text` is the full
        body line, unchanged from what this file printed before.
        """
        self.skipped[gate_no] = why
        self.notes.append(text)

    def asserted(self):
        return [g for g in ALL_GATES if g not in self.skipped]


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
        res.skip(2, "GATE 2  NOT CHECKED -- run_all does not import",
                 "run_all does not import")
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
        res.skip(3, "GATE 3  NOT CHECKED -- no pipeline table",
                 "no pipeline table")
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
        res.skip(4, "GATE 4  NOT CHECKED -- no pipeline table",
                 "no pipeline table")
        return
    import run_all
    from universes.registry import REGISTRY
    if since is None:
        res.skip(4, "GATE 4  SKIPPED -- needs --since <epoch>, i.e. a run to "
                 "check against. Not counted as passed.", "need --since")
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

    IT ASSERTS ON THE ASSESSED TAX, NOT THE STATEMENT TOTAL, AND THAT WAS WRONG
    HERE FOR ONE DAY. This gate first summed every FY_TAX_STATEMENT row, which
    includes the final year's UNASSESSED liability -- section 3(9) charges
    FY2026-27 on the first trading day at or after 2027-03-31, outside the
    window, so no cash was taken for it and it cannot be inside an equity
    difference measured at the last session. Asserting against the total passed
    only by being STRICTER than the identity, which is luck rather than design.

    ONE UNIVERSE COULD NOT SHOW IT. midcap50's unassessed row is 0.00, and so is
    nifty50's, so on either of them the total and the assessed figure are the
    same number and the label looked right. It took a universe with a non-zero
    tail -- midcap150 at Rs 33,671.08, nifty100 at Rs 11,521.13 -- to separate
    them, and it surfaced only when the gate was run on four universes rather
    than the one it was written against. A gate exercised on a single case is a
    gate whose labels have not been read.

    ALL THREE FIGURES ARE PRINTED, separately labelled, because the difference
    between them is what section 3(9) does and a reader should not have to
    recompute it: assessed (deducted), statement total, and unassessed. Foregone
    compounding is derived from the ASSESSED figure -- deriving it from the total
    understates it by the unassessed amount.

    SKIPPED, NOT PASSED, when no tax artefacts are on disk: a tax=off run writes
    none, and this gate says so rather than counting silence as agreement.
    """
    import csv
    if since is None:
        res.skip(6, "GATE 6  SKIPPED -- needs --since, i.e. a run to check "
                 "against. Not counted as passed.", "need --since")
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
        # ASSESSED ONLY, WHICH IS THE CASH THAT ACTUALLY LEFT THE BOOK. A row
        # with assessed=False is a liability section 3(9) charges after the
        # window closes; no cash was taken for it, so it cannot be inside an
        # equity difference measured at the final session. This is the figure
        # audit["tax"]["cum_tax"] holds and the only one the identity is true of.
        def _f(r, k):
            v = (r.get(k) or "").strip()
            return v.lower() in ("true", "1", "yes")
        assessed = sum(float(r["total_tax"]) for r in srows if _f(r, "assessed"))
        unassessed = sum(float(r["total_tax"]) for r in srows
                         if not _f(r, "assessed"))
        total = assessed + unassessed

        gap = p_final - t_final
        # (ii) AT LEAST, never equal -- see the docstring.
        if gap < assessed - 0.01:
            res.fail("GATE 6 tax", f"{t} taxed equity vs ledger",
                     f"the taxed curve is only Rs {gap:,.2f} below the untaxed "
                     f"one, which is LESS than the Rs {assessed:,.2f} the ledger "
                     f"says was deducted. Tax was named but not charged.")
            continue
        res.note(f"GATE 6  {t}: taxed equity == FY_EQUITY to a paisa; gap Rs "
                 f"{gap:,.2f} >= assessed Rs {assessed:,.2f} "
                 f"(compounding Rs {gap-assessed:,.2f}; statement total Rs "
                 f"{total:,.2f}, unassessed Rs {unassessed:,.2f})")
    if checked == 0:
        res.skip(6, "GATE 6  SKIPPED -- no tax artefacts on disk (a tax=off "
                 "run writes none). Not counted as passed.",
                 "no tax artefacts on disk")


# ---------------------------------------------------------------------------
# GATE 7 -- the LTCG ceiling, watched rather than assumed
# ---------------------------------------------------------------------------

def gate_ltcg(res, sel):
    """HOLDING_PERIOD's claim about the long-term branch must match its lots.

    THIS GATE EXISTS BECAUSE ITS ABSENCE WAS MEASURED. tax_util.max_holding_days
    was written with the docstring "EXISTS SO A GATE CAN WATCH THE 326-DAY
    CEILING ... the failure mode is silent: the long-term rate simply starts
    applying and every tax figure moves." It then sat with ZERO CALL SITES for
    its whole life. The ceiling was crossed on 2026-09-18 -- nifty50 588 days,
    nifty100 443 days, four lots over the threshold -- and the failure mode was
    silent exactly as predicted, because the thing that was supposed to make
    noise had never been connected to anything.

    So the assertion here is deliberately the one the prose promised:

        max_holding_days(lots) >= LTCG_HOLD_DAYS  =>  the artefact must SAY SO

    and it is asserted against `tax_report.holding_period`, the producer, not
    against a file. A file can be stale; the producer is what the next run will
    write. Checking the producer means the gate goes green the moment the code
    is right, and red the moment a hardcoded claim is reintroduced -- which is
    the specific regression that happened.

    WHAT IT DOES NOT DO. It does not assert that no lot crosses 365. Crossing is
    legitimate: the tax code routes long lots correctly and always did, and
    midcap150 and midcap50 are short-term only as a property of their windows.
    The defect was never the crossing. It was an artefact asserting one thing
    while its own adjacent column said another.

    NO --since. It reads lots that are already on disk and calls a pure
    function, so there is nothing to date. A universe with no tax artefacts is
    skipped and counted, not silently passed.
    """
    try:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "results"))
        from universes.registry import REGISTRY
        import pandas as pd
        import tax_util as T
        import tax_report as TR
    except Exception as e:
        res.fail("GATE 7 ltcg", "import", f"{type(e).__name__}: {e}")
        return

    tags = sorted(REGISTRY) if sel in (None, "all") else [t.strip() for t in sel.split(",")]
    checked, stale = 0, []
    for t in tags:
        u = REGISTRY.get(t)
        if u is None:
            continue
        lp = next(iter(sorted(Path(u.metrics_dir).glob(
            f"HOLDING_PERIOD_LOTS_*_tax.csv"))), None)
        if lp is None:
            continue
        try:
            lots = pd.read_csv(lp)
        except Exception as e:
            res.fail("GATE 7 ltcg", f"{t} {lp.name}", f"{type(e).__name__}: {e}")
            continue
        if lots.empty:
            continue
        checked += 1

        mx = T.max_holding_days(lots)          # THE CALL SITE. Do not remove it.
        fires = mx >= T.LTCG_HOLD_DAYS
        row = TR.holding_period(lots).iloc[0]
        note = str(row["note"]).lower()
        says_fires = "fires" in note
        says_not = "does not fire" in note

        # the count must come from the same predicate that routes the lot
        routed = int((lots["held_days"] >= T.LTCG_HOLD_DAYS).sum())
        if int(row["lots_long_term"]) != routed:
            res.fail("GATE 7 ltcg", f"{t} lots_long_term",
                     f"artefact counts {int(row['lots_long_term'])} long lots, the "
                     f"routing predicate (held_days >= {T.LTCG_HOLD_DAYS}) finds "
                     f"{routed}. The count and the bucket disagree, which means "
                     f"LTCG may be charged at STCG rates or the reverse.")

        if fires and (says_not or not says_fires):
            res.fail("GATE 7 ltcg", f"{t} HOLDING_PERIOD note",
                     f"longest hold is {mx} days, which is >= LTCG_HOLD_DAYS="
                     f"{T.LTCG_HOLD_DAYS}, and {routed} lot(s) took the long "
                     f"branch -- but the note still claims the branch does not "
                     f"fire:\n      {row['note']}\n"
                     f"      headroom_days={int(row['headroom_days'])} in the same "
                     f"row already contradicts it. Make the whole sentence "
                     f"computed; do not hardcode the claim beside a measured "
                     f"margin. See tax_report.holding_period.")
        elif not fires and says_fires:
            res.fail("GATE 7 ltcg", f"{t} HOLDING_PERIOD note",
                     f"longest hold is {mx} days, under LTCG_HOLD_DAYS="
                     f"{T.LTCG_HOLD_DAYS}, but the note claims the branch fires:"
                     f"\n      {row['note']}")
        else:
            res.note(f"GATE 7  {t}: max hold {mx}d, "
                     f"{'FIRES' if fires else 'no fire'}, {routed} long lot(s), "
                     f"note agrees")

        # the file that is already on disk was written by an earlier run and may
        # predate a fix. Reported, never failed: no code change can turn it
        # green, only a re-run, and a gate that cannot be satisfied is ignored.
        # glob "HOLDING_PERIOD_*" also matches HOLDING_PERIOD_LOTS_*, and
        # sorted() puts LOTS first because "L" < a lowercase tag. Filter, then
        # take -- taking then filtering silently reports nothing, which is how
        # this block did nothing on its first run.
        onf = next((f for f in sorted(Path(u.metrics_dir).glob(
            "HOLDING_PERIOD_*_tax.csv")) if "_LOTS_" not in f.name), None)
        if onf is not None:
            try:
                disk = pd.read_csv(onf).iloc[0]
                dn = str(disk["note"]).lower()
                if (int(disk["max_held_days"]) >= T.LTCG_HOLD_DAYS) and \
                        "does not fire" in dn:
                    stale.append(f"{t}/{onf.name}")
            except Exception:
                pass

    if checked == 0:
        res.skip(7, "GATE 7  SKIPPED -- no HOLDING_PERIOD_LOTS artefacts on "
                 "disk (a tax=off run writes none). Not counted as passed.",
                 "no HOLDING_PERIOD_LOTS artefacts on disk")
    if stale:
        res.note(f"GATE 7  NOTE, not a failure: {len(stale)} artefact(s) on disk "
                 f"still carry a pre-fix note string and will be corrected by the "
                 f"next taxed run -- {', '.join(stale)}")


# ---------------------------------------------------------------------------
# GATE 8 -- a published artefact must name the price data it was built from
# ---------------------------------------------------------------------------

# THE ARTEFACTS THAT PREDATE THE data_source FIELD. Listed 2026-09-20.
#
# The field was added by 7dd37d6 on 2026-09-20. These 18 params files, across all
# eight universes, were written before it existed, so they carry no data_source and
# the gate failed all 18 on every run. That is 18 red lines that no commit can
# clear except re-running the artefact, and a gate that is permanently red is a
# gate nobody reads. The artefacts are not defective; the reporting was.
#
# NOTHING IS BACKFILLED AND NOTHING IS FORGIVEN. An exemption says only "this file
# predates the field", never "this file's provenance is known". It is still true
# that these 18 cannot say what price data produced them, and that is still a
# reason not to quote them. The remedy is unchanged: re-run the artefact.
#
# THE LIST ONLY SHRINKS. Re-running any of these writes a data_source, and the gate
# then FAILS on it for still being listed, naming the line to delete. A new
# artefact without the field is not on the list, so it fails the ordinary way. The
# count is asserted against the length of this tuple, so a name cannot be added
# here without the number moving in the same diff.
GATE8_EXEMPT = (
    "results_midcap100/metrics/v34_params.json",
    "results_midcap100/metrics/v34_params_tax.json",
    "results_midcap150/metrics/v34_params.json",
    "results_midcap150/metrics/v34_params_tax.json",
    "results_midcap150/metrics/v34_params_v3.json",
    "results_midcap50/metrics/v34_params.json",
    "results_midcap50/metrics/v34_params_tax.json",
    "results_nifty100/metrics/v34_params.json",
    "results_nifty100/metrics/v34_params_tax.json",
    "results_nifty100/metrics/v34_params_v2.json",
    "results_nifty200/metrics/v34_params.json",
    "results_nifty200/metrics/v34_params_tax.json",
    "results_nifty50/metrics/v34_params.json",
    "results_nifty50/metrics/v34_params_tax.json",
    "results_nifty500/metrics/v34_params.json",
    "results_nifty500/metrics/v34_params_tax.json",
    "results_smallcap250/metrics/v34_params.json",
    "results_smallcap250/metrics/v34_params_tax.json",
)
GATE8_EXEMPT_N = 18          # asserted below; move it when the tuple moves


def gate_data_source(res, sel):
    """Every v34_params*.json must record a data source that is still current.

    WHAT THIS CATCHES, MEASURED RATHER THAN IMAGINED. midcap150's two tradeable
    artefacts were written 2026-09-17 01:20 from data/raw/MidCap150/clean. The
    universe was repointed at Final_Without_Survivorship_Data on 2026-09-18.
    Afterwards 33 of the 1,019 fills in daily_trades_midcap150_tradeable.csv named
    a (symbol, date) pair with no price row in the tree at all, and 34 more
    recorded a fill price the tree does not imply. All seven gates stayed green
    for three days, because not one of them opens a price file.

    WHY THE OTHER SEVEN COULD NOT HAVE CAUGHT IT. Gates 1, 2 and 3 are static:
    modules, a table, and ASTs. Gate 4 stats mtimes, so a run against the wrong
    source moves them exactly like a correct one. Gate 5 delegates to four naming
    and wiring checkers. Gates 6 and 7 compare artefacts against other artefacts
    from the same run, which is self-consistent by construction. The missing
    comparison is artefact against INPUT, and this is it.

    THE MECHANISM IS BORROWED, NOT INVENTED. config.write_cache_source and
    config._verified have recorded and enforced a cache's source since
    2026-09-19; the rule was correct and lived one layer too low, because
    _cache_owner() matches only score_cache, raw_cache, score_tmp and raw_tmp. A
    daily_trades and a v34_params -- the files people read and quote -- were
    covered by nothing. This raises the same rule to the published artefact.

    IT FAILS CLOSED. A params file with no data_source is a FAILURE, not a skip:
    an artefact that cannot say what it was built from is exactly the state the
    tradeable cells were in, and treating silence as acceptable would re-admit it
    by default. Nothing is backfilled -- a source written in now for an artefact
    produced before the field existed would be a guess presented as provenance,
    which is worse than the gap. The remedy is to re-run the artefact.

    The gate SKIPS only when no params file exists at all, which is a tree with
    nothing to check rather than a check that declined.

    THE 18 EXEMPTIONS ARE A CLOSED LIST, NOT A PATTERN. GATE8_EXEMPT above names
    every artefact that predates the field. A file without data_source that is not
    on the list fails. A file on the list that has GAINED the field fails too, and
    says to delete the line -- so re-running an artefact shrinks the list and the
    gate insists on it. On a full run the number of exemptions actually used is
    checked against GATE8_EXEMPT_N and every listed path must still exist, so the
    list cannot grow, rot, or quietly cover something it was never meant to.
    """
    import json
    try:
        import config
        from universes.registry import REGISTRY
    except Exception as e:
        res.fail("GATE 8 data source", "registry",
                 f"{type(e).__name__}: {e}")
        return
    tags = sorted(REGISTRY) if sel in (None, "all") else [t.strip() for t in sel.split(",")]

    def name(f):
        """Repo-relative where possible, absolute otherwise. A metrics_dir outside
        ROOT is legal -- runs/ hard-links artefacts, and a test can point one at a
        scratch directory -- and relative_to() raises on exactly that, which would
        turn a reportable failure into a traceback from inside the gate."""
        try:
            return str(Path(f).relative_to(ROOT))
        except ValueError:
            return str(f)

    live = {}                      # tag -> fingerprint, computed at most once
    checked = 0
    exempt_used = set()            # listed paths that were seen, and had no field
    seen_paths = set()             # every params path this run actually looked at
    full_scan = sel in (None, "all")
    for t in tags:
        u = REGISTRY.get(t)
        if u is None:
            continue
        M = Path(u.metrics_dir)
        if not M.exists():
            continue
        for f in sorted(M.glob("v34_params*.json")):
            checked += 1
            nm = name(f)
            seen_paths.add(nm)
            try:
                doc = json.loads(f.read_text())
            except Exception as e:
                res.fail("GATE 8 data source", nm,
                         f"unreadable: {type(e).__name__}: {e}")
                continue
            rec = doc.get("data_source")
            if not isinstance(rec, dict):
                if nm in GATE8_EXEMPT:
                    # Predates the field. Listed, dated and counted, not forgiven:
                    # it still cannot say what produced it. Re-run it to clear it.
                    exempt_used.add(nm)
                    continue
                res.fail("GATE 8 data source", nm,
                         "no data_source field, so which price data produced this "
                         "artefact cannot be established. NOT BACKFILLED: a source "
                         "written in now would be a guess. Re-run the artefact.")
                continue
            if nm in GATE8_EXEMPT:
                res.fail("GATE 8 data source", nm,
                         "this artefact is on GATE8_EXEMPT but now HAS a "
                         "data_source, so it has been re-run since the list was "
                         "written. Delete its line from GATE8_EXEMPT in "
                         "check_all.py and reduce GATE8_EXEMPT_N by one. The list "
                         "is meant to shrink; leaving a cleared artefact on it "
                         "hides the next one that genuinely lacks the field.")
                continue
            if t not in live:
                live[t] = config.data_fingerprint(u.data_dir, u.raw_data_dir)
            cur = live[t]
            for key in ("raw_data_dir", "link_target_dir", "digest"):
                if rec.get(key) != cur.get(key):
                    res.fail("GATE 8 data source", name(f),
                             f"{key} MISMATCH -- this artefact describes data the "
                             f"universe no longer uses.\n"
                             f"          artefact  {rec.get(key)}\n"
                             f"          tree now  {cur.get(key)}\n"
                             f"      Every number in it is a number about the first "
                             f"and is filed under a universe that names the second.")
                    break
    if not checked:
        res.skip(8, "GATE 8  SKIPPED -- no v34_params*.json on disk, so there is "
                 "no published artefact to check. Not counted as passed.",
                 "no params artefacts on disk")
        return

    # THE LIST IS PINNED BY COUNT AND BY EXISTENCE, on a full scan only -- a run
    # scoped to one universe legitimately never visits most of these paths.
    if full_scan:
        gone = [x for x in GATE8_EXEMPT if x not in seen_paths]
        if gone:
            res.fail("GATE 8 exemptions", "check_all.py",
                     "GATE8_EXEMPT names {} artefact(s) that are not on disk:\n"
                     "          {}\n"
                     "      A listed path that no longer exists is a stale "
                     "exemption. Delete the line(s) and reduce GATE8_EXEMPT_N "
                     "to match.".format(len(gone), "\n          ".join(gone)))
        if len(GATE8_EXEMPT) != GATE8_EXEMPT_N:
            res.fail("GATE 8 exemptions", "check_all.py",
                     f"GATE8_EXEMPT holds {len(GATE8_EXEMPT)} names but "
                     f"GATE8_EXEMPT_N says {GATE8_EXEMPT_N}. The count exists so a "
                     f"name cannot be added without the number moving in the same "
                     f"diff. Set them equal deliberately.")
        elif len(exempt_used) != GATE8_EXEMPT_N:
            res.fail("GATE 8 exemptions", "check_all.py",
                     f"{len(exempt_used)} of {GATE8_EXEMPT_N} listed artefacts "
                     f"were actually missing a data_source this run. The others "
                     f"either gained the field (each is failed by name above) or "
                     f"were not visited. Bring GATE8_EXEMPT and GATE8_EXEMPT_N "
                     f"back in line with the tree.")

    res.note(f"GATE 8  {checked} published artefact(s) checked against the "
             f"registry's current raw_data_dir and a sha256 over the whole input; "
             f"{len(exempt_used)} of {GATE8_EXEMPT_N} listed exemptions predate the "
             f"field (2026-09-20) and still cannot say what produced them")


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
    gate_ltcg(res, args.universe)
    gate_data_source(res, args.universe)

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
    # THE VERDICT IS COMPUTED FROM THE SKIPS, NEVER TYPED. A constant string is
    # exactly what went wrong: it survived every skip the body recorded.
    n = len(ALL_GATES)
    assert n == 8, f"ALL_GATES holds {n} gates; the wording below says eight"
    ok = res.asserted()
    if res.skipped:
        # GROUPED BY REASON, because the common case is gates 4 and 6 skipping
        # for the identical reason and "GATE 4 -- need --since; GATE 6 -- need
        # --since" is a verdict line nobody finishes reading.
        by_reason = {}
        for g in sorted(res.skipped):
            by_reason.setdefault(res.skipped[g], []).append(g)
        parts = [f"{', '.join('GATE %d' % g for g in gs)} -- {why}"
                 for why, gs in by_reason.items()]
        print(f"RESULT: PASS ({len(ok)} of {n} asserted, "
              f"{len(res.skipped)} skipped: {'; '.join(parts)})")
        print(f"        ASSERTED: {', '.join('GATE %d' % g for g in ok)}")
        print("        A SKIPPED GATE IS NOT A PASSED GATE. Exit code is 0 "
              "because a skip is legitimate,")
        print("        not because the work was done. Re-run with --since "
              "<epoch> after a run to assert all eight.")
    else:
        print(f"RESULT: PASS -- all {n} gates asserted, none skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
