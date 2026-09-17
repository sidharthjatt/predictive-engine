"""
check_pipeline_order.py -- static consumer/producer ordering check for run_all.py.

WHY THIS EXISTS
    make_final_chart_fair.py read daily_trades_58.csv, which make_daily_audit.py
    produced two steps LATER. The pipeline appeared to work for the life of the
    project because the file survived in metrics/ from the previous run. The first
    run against a genuinely empty metrics/ died with a FileNotFoundError raised
    inside pandas.

    run_all.py already has REQUIRED_INPUTS, a hand-maintained list of the
    non-obvious dependencies. A hand-maintained list goes stale: a step added next
    year with the same shape of hidden read would not be in it. This module derives
    the dependencies from the source instead, and fails on any inversion that
    REQUIRED_INPUTS does not already cover.

WHY A NAIVE SCAN DOES NOT WORK, AND WHAT THIS DOES INSTEAD
    Two properties of this codebase defeat the obvious grep, and both were present
    in the original bug:

    1. THE READ IS INDIRECT. make_final_chart_fair.py calls
       tc_from_log(M58/"daily_trades_58.csv"); the pd.read_csv is inside that
       helper, a dozen lines away. So a scan keyed on read_csv() never sees the
       filename.
       -> This scans PATH EXPRESSIONS (`VAR / "name.csv"`) wherever they appear,
          and classifies as a WRITE only when a write call is on the same line.
          Everything else touching a path is treated as a read. That over-reports
          rather than under-reports, which is the safe direction.

    2. THE PRODUCER'S NAME IS TEMPLATED. make_daily_audit.py writes
       daily_trades_{tag}.csv, with tag bound to "58" and "74" at the call site,
       so the literal "daily_trades_58.csv" appears nowhere in the producer.
       Matching on the glob daily_trades_*.csv instead hides the bug, because the
       mid and n100 audits legitimately produce that glob at earlier steps.
       -> Tags are resolved per script from the bottom-level run(...) calls, and
          {tag} is expanded to the concrete filenames in the concrete metrics
          directory before matching.

LIMITS, STATED RATHER THAN PAPERED OVER
    - Placeholders other than {tag} (e.g. {sym} in per-stock charts, {f} in
      make_daily_log) are not expanded. They are reported under "unresolved" so
      they are visible, and they are not treated as failures.
    - A path built by string concatenation or os.path.join rather than the `/`
      operator is not seen.
    - Cross-directory writes done through a variable this module cannot resolve
      fall back to the script's own metrics directory.
    None of these can produce a false PASS for the bug class above; they can only
    leave a dependency unchecked, which is why unresolved entries are printed.

Run standalone to see the full map:
    python3 check_pipeline_order.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

WRITE_CALL = re.compile(r'\b(to_csv|savefig|write_text|to_parquet|to_json)\s*\(')
# Either `M / "x.csv"` (a variable bound above) or the dotted form used inline,
# `config74.METRICS_DIR_74 / "x.csv"`. The dotted form is what make_cash_series.py
# and the since-deleted make_stats_both.py used, and missing it left real edges
# unresolved.
PATH_EXPR = re.compile(
    r'(?:(config(?:74|_mid|_n100)?)\.)?(\w+)\s*/\s*f?["\']'
    r'([A-Za-z0-9_.\-]*(?:\{\w+\}[A-Za-z0-9_.\-]*)*'
    r'\.(?:csv|png|json|parquet))["\']')
DIR_ASSIGN = re.compile(r'\b(\w+)\s*=\s*(config(?:_\w+)?)\.(METRICS_DIR\w*)')
# A UNIVERSE'S METRICS DIRECTORY BOUND FROM THE REGISTRY, which is the only way to
# spell it after step 7 folded config_mid.py and config_n100.py into the registry.
# DIR_ASSIGN and the dotted branch of PATH_EXPR both key on a `config*` module, and
# no source names one for a universe any more, so without this make_combined_universes
# loses all eight of its STEP 12b producer edges -- silently, with the check still
# reporting success. That is the identical failure the audit merge produced when
# TAG_CALL stopped matching, and it is why this is a pattern rather than a fixup.
REG_ASSIGN = re.compile(r'\b(\w+)\s*=\s*REGISTRY\[["\'](\w+)["\']\]\.metrics_dir\b')
# make_final_summary.py binds both dirs in one tuple assignment, optionally wrapped
# in Path():  M58, M74 = Path(config.METRICS_DIR), Path(config74.METRICS_DIR_74)
# Missing this left fair_comparison_table.csv -- a real STEP 13 -> 14 edge --
# unresolved, so the checker could not see one of the dependencies it exists for.
ASSIGN_LINE = re.compile(r'^\s*([\w\s,]+?)\s*=\s*(.+)$')
DIR_REF = re.compile(r'(config(?:_\w+)?)\.(METRICS_DIR\w*)')
# the audit scripts bind their tag at the bottom:
#   run(tmp, perm, config74.METRICS_DIR_74, 2025, "74")
TAG_CALL = re.compile(
    r'(config(?:74|_mid|_n100)?)\.(METRICS_DIR\w*)\s*,\s*\d+\s*,\s*["\'](\w+)["\']')

# A STEP MAY NAME ITS UNIVERSE THROUGH THE REGISTRY INSTEAD OF A CONFIG MODULE.
# TAG_CALL above recognises the original shape -- run(..., config74.METRICS_DIR_74,
# 2025, "74") -- which is how the audit scripts used to bind their tag. Once they
# collapsed into one implementation they call audit_step.run(REGISTRY["mid"])
# instead, TAG_CALL matched nothing, and every daily_*_{tag}.csv became unresolved:
# the checker lost four producer edges and still reported success. This recognises
# the registry form as well.
REGISTRY_CALL = re.compile(r'REGISTRY\[["\'](\w+)["\']\]')


# ---------------------------------------------------------------------------
# NOT EVERY PATH EXPRESSION IS A PIPELINE EDGE
# ---------------------------------------------------------------------------
# A VARIABLE BOUND FROM prepare_data_dir() IS RAW PRICE DATA, NOT A METRICS
# ARTEFACT. results/make_chart.py:209 binds `_raw = u.prepare_data_dir()` and then
# reads `_raw / f"{sym}.csv"` -- the CONSTITUENTS SYMLINK FARM under data/raw. That
# is source data this pipeline consumes, not an artefact any step writes, so it is
# not an ordering edge and no step can be "out of order" with respect to it.
#
# THE EXCLUSION IS ON WHAT THE DIRECTORY IS, NOT ON THE PLACEHOLDER. Before this,
# those two reads landed in `unresolved` because `{sym}` could not expand -- which
# CONCEALED the real defect rather than being it: the scanner had already resolved
# `_raw` to `results_mid/` by falling back to `default`, so an improvement to
# placeholder handling would have started resolving them to the WRONG DIRECTORY,
# silently, and an exclusion written as "unexpandable placeholder" would have read
# as though it anticipated that. It would not have.
RAW_DIR_ASSIGN = re.compile(r'\b(\w+)\s*=\s*\w+\.prepare_data_dir\(\)')

# AN AXIS SUFFIX IS EMPTY AT THE DEFAULT SELECTION, WHICH IS THE CANONICAL NAME.
# results/audit_step.py:165 binds `_cad = cadence.suffix() + _prof.suffix()` and
# reads `M / f"v2FINAL_equity{_cad}.csv"`. The edge is real: naming.py's rule is
# that every axis returns "" at its default, so at the default selection that file
# IS the canonical v2FINAL_equity.csv written by engine_v2_final.py. Pinning these
# to "" resolves the edge to the artefact the default pipeline actually produces,
# which is the same convention every composed name in this project already uses.
AXIS_SUFFIX_ASSIGN = re.compile(
    r'\b(\w+)\s*=\s*[\w.]*\b(?:cadence|profiles|_prof|_cad)\b[\w.]*\.suffix\(\)')

# ---------------------------------------------------------------------------
# THE DECLARED ALLOWLIST -- edges that CANNOT be resolved, named with the reason
# ---------------------------------------------------------------------------
# WHAT CANNOT BE DERIVED IS DECLARED, AND THE DECLARATION IS WHAT FAILS. The same
# shape as run_all.REQUIRED_INPUTS' fourth field. Anything unresolved and NOT on
# this list is now fatal; these two are named, with why, so they stop being
# anonymous entries in a list nobody reads.
#
# THESE ARE NOT EASY FIXES AND MUST NOT BE TREATED AS ONE. Both come from
# results/make_daily_log.py:218-220, inside `load(M, tag)`, where BOTH the metrics
# directory and the universe tag are FUNCTION PARAMETERS -- the directory is not
# even known well enough to print, which is why it shows as `?`. The reads are
# genuine: the trail files are written by make_audit.py.
#
# RESOLVING THEM MEANS BINDING A PARAMETER TO A DIRECTORY, WHICH IS THE SAME
# CAPABILITY AS BINDING A LOOP VARIABLE -- and that capability was DECLINED on
# 2026-09-18 on silent-invention grounds: it makes the scanner resolve edges the
# code never produces, and `unresolved` cannot catch a wrong resolution because it
# only grows on a failure to resolve. See KNOWN_ISSUES.md, "`unresolved` is not
# fatal, which is why the same silent failure has happened four times", and
# run_all.SPANS_REGISTRY.
#
# SO THE NEXT PERSON READING THIS SHOULD NOT BUILD FAN-OUT TO CLOSE THESE TWO.
# That trade was measured and rejected; closing them this way costs the checker
# more than it gains.
ALLOWED_UNRESOLVED = {
    (None, "daily_skipped_{tag}.csv"): (
        "make_daily_log.load(M, tag) -- metrics dir AND tag are function "
        "parameters; binding either is the declined fan-out capability"),
    (None, "{f}_{tag}.csv"): (
        "make_daily_log.load(M, tag) -- the filename stem is a parameter too; "
        "same declined capability"),
}

def _mod2dir():
    """(config module, METRICS_DIR name) -> results directory, FROM THE REGISTRY.

    The scanner sees source text, so it matches on the spelling a step actually
    writes -- `config_mid.METRICS_DIR_MID / "x.csv"` -- and has to turn that pair
    back into a directory. That map used to be four hand-written literals, two of
    which named universes (`config74`, and `config` as the 58's output home) that
    no longer exist; a stale entry here does not fail, it silently mis-attributes
    a write and the ordering check passes with the edge missing.

    Each universe names its own config module and METRICS_DIR constant by
    convention -- config_mid.METRICS_DIR_MID for tag "mid" -- so both halves are
    derived from the tag rather than restated.

    NOTHING IN THE TREE SPELLS THAT FORM ANY MORE. Step 7 folded config_mid.py and
    config_n100.py into universes/registry.py, so the per-universe entries below
    match no source line today; REG_ASSIGN is what resolves a universe's metrics
    directory now. They are kept because they are DERIVED from the registry rather
    than written down -- they cannot go stale, they cost one dict entry each, and
    a universe reintroducing a config module would be recognised rather than
    silently unresolved. A hand-written entry would not have earned that.

    config.METRICS_DIR stays in the map, but NOT as a universe: results/metrics is
    the shared, non-universe artefact directory now. See RETIRED_UNIVERSES.md.
    """
    out = {("config", "METRICS_DIR"): "results"}
    try:
        from universes.registry import REGISTRY
        for u in REGISTRY.values():
            mod = f"config_{u.tag}"
            out[(mod, f"METRICS_DIR_{u.tag.upper()}")] = Path(u.metrics_dir).parent.name
    except Exception:
        pass
    return out


DIRKEY = _mod2dir()

def _tag2dir():
    """tag -> the results directory that universe writes into, from the registry.

    Derived rather than restated: universes/registry.py already knows where each
    universe's metrics live, and a second hand-written copy here is exactly the kind
    of thing that drifts.

    THERE IS NO LITERAL FALLBACK ANY MORE. It used to return the historical four
    tags when the registry could not be imported, so that this checker "kept
    working" -- but what it actually did was resurrect the 58 and the 74 after they
    were deleted, and check a pipeline that does not exist. A checker that cannot
    read the registry has nothing to check against and must say so.
    """
    import sys as _s
    from pathlib import Path as _P
    _r = str(_P(__file__).resolve().parent)
    if _r not in _s.path:
        _s.path.insert(0, _r)
    from universes.registry import REGISTRY
    return {u.tag: _P(u.metrics_dir).parent.name for u in REGISTRY.values()}


_TAG2DIR = _tag2dir()

def _caches():
    """The permanent panel caches, from the registry rather than a written list.

    Panels are restored into /tmp before the run and are NOT produced by any step,
    so analyse() skips them when building producer/consumer edges. That exclusion
    has to cover every universe: a fifth one whose caches were missing from this
    set would have its cache reads treated as real dependencies, find no producer,
    and -- if one ever appeared -- report an inversion that is not one. A false
    inversion is worse than the bug it would be pretending to catch, because it
    teaches the reader to ignore the checker.

    NO LITERAL FALLBACK, for the same reason _tag2dir() has none: the eight names
    it used to fall back to included four belonging to universes that have been
    deleted, and a cache list that names a dead universe is how a false inversion
    gets reported.
    """
    from universes.registry import REGISTRY
    return ({u.score_cache.name for u in REGISTRY.values()}
            | {u.raw_cache.name for u in REGISTRY.values()})


CACHES = _caches()


def _scan(script_path):
    """-> (writes, reads, unresolved) as sets of (dirkey, filename)."""
    return _scan_text(script_path.read_text())


# ---------------------------------------------------------------------------
# PROSE IS NOT CODE, AND THIS SCANNER USED TO TREAT IT AS CODE
# ---------------------------------------------------------------------------
# TWICE A TEXT SCANNER IN THIS REPOSITORY HAS MATCHED A COMMENT *ABOUT* CODE
# RATHER THAN CODE, and both times the prose was written by the person adding the
# check. transitional_asserts_check.py's first version matched its own marker
# comment, which names the subscript it warns about, and reported a literal in a
# file that no longer had one. Then make_audit.py's docstring explained the step-4
# merge by spelling the old REGISTRY subscript out -- REGISTRY_CALL matched it,
# bound a phantom "mid" tag to BOTH pipeline rows, and STEP 10g silently dropped
# n100's four producer edges because it could no longer choose a directory.
#
# WHY NOT A FULL AST REWRITE, which is what fixed the marker check. Three reasons,
# and they are specific to this scanner rather than general:
#
#   1. IT SCANS A STEP CONCATENATED WITH ITS HELPERS AS ONE TEXT, deliberately --
#      the tag is bound in the entry point and the to_csv that uses it lives in the
#      helper, and scanning them apart loses every edge. Under ast that stops being
#      concatenation and becomes cross-module scope analysis: which name in the
#      helper refers to which binding in the caller. That is an import resolver,
#      not a refactor.
#   2. ITS PATTERNS MATCH SHAPES, NOT NODES. `VAR / "literal.csv"` is one BinOp
#      spelling of many the regexes currently catch across several files, and
#      rewriting them as node matches changes WHICH EDGES ARE FOUND. The edge
#      inventory is the thing that must not move silently, and this is the middle
#      of a collapse that moves files every step.
#   3. THE DEFECT IS NOT "regex instead of ast". It is that comments and
#      docstrings reach the matcher at all. That is removable exactly.
#
# SO: PROSE IS STRIPPED BEFORE ANY PATTERN RUNS, and a tag that appears ONLY in
# prose is REPORTED BY LINE rather than bound. Silent binding is what cost the four
# edges; a named warning is what should have happened.
def _strip_prose(txt):
    """(code-only text, [(lineno, text)]) -- comments and docstrings blanked.

    LINE NUMBERS ARE PRESERVED: every removed region keeps its newlines, so a
    warning can name the line the prose is actually on.
    """
    import io, tokenize as _tk
    prose = []
    try:
        lines = txt.splitlines(keepends=True)
        kill = []                                   # (line, col, endline, endcol)
        for t in _tk.generate_tokens(io.StringIO(txt).readline):
            if t.type == _tk.COMMENT:
                kill.append((t.start[0], t.start[1], t.end[0], t.end[1]))
        tree = ast.parse(txt)
        for node in ast.walk(tree):
            # LIST-VALUED BODIES ONLY. ast.IfExp.body and ast.Lambda.body are
            # single EXPRESSIONS, not statement lists, so iterating them raises
            # TypeError -- which the except below swallowed, returning the text
            # unstripped and silently restoring the very behaviour this function
            # removes. Caught by testing the stripper on real source rather than a
            # two-line sample.
            for field in ("body", "orelse", "finalbody"):
                val = getattr(node, field, None)
                if not isinstance(val, list):
                    continue
                for stmt in val:
                    if (isinstance(stmt, ast.Expr)
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)):
                        kill.append((stmt.lineno, stmt.col_offset,
                                     stmt.end_lineno, stmt.end_col_offset))
    except Exception:
        # UNPARSEABLE TEXT IS RETURNED UNCHANGED rather than half-stripped. The
        # caller still gets a scan; it is the pre-2026-09-15 behaviour, and the
        # prose-collision warning below will not fire. Silent partial stripping
        # would be worse than not stripping.
        return txt, []
    for (l0, c0, l1, c1) in kill:
        if l0 == l1:
            seg = lines[l0 - 1][c0:c1]
            prose.append((l0, seg.strip()[:90]))
            lines[l0 - 1] = lines[l0 - 1][:c0] + " " * (c1 - c0) + lines[l0 - 1][c1:]
        else:
            prose.append((l0, lines[l0 - 1][c0:].strip()[:90]))
            lines[l0 - 1] = lines[l0 - 1][:c0] + "\n"
            for i in range(l0, l1 - 1):
                lines[i] = "\n"
            lines[l1 - 1] = " " * c1 + lines[l1 - 1][c1:]
    return "".join(lines), prose


def _warn_prose_tags(txt, code, label, scr, tag=None):
    """A prose tag that would have introduced a SECOND candidate directory.

    ONLY THE HARMFUL CASE WARNS. Prose naming this row's OWN universe is common and
    harmless -- the transitional-assert markers added at step 2 all quote the
    subscript they describe -- and it would have bound the directory the row
    already implies. Warning on those would fire on every clean run, and run.py
    records what that does to a checker: "a warning that fires every time about
    something irrelevant is how a checker gets ignored."

    A prose tag naming a DIFFERENT universe is the one that cost four edges: it
    gives the step two candidate directories, `default` becomes None, and every
    placeholder path falls into unresolved with the checker still reporting
    success.
    """
    in_code = {m.group(1) for m in REGISTRY_CALL.finditer(code)}
    for line_no, line in enumerate(txt.splitlines(), 1):
        for m in REGISTRY_CALL.finditer(line):
            if m.group(1) in in_code:
                continue
            if m.group(1) not in _TAG2DIR:
                continue
            if tag is not None and m.group(1) == tag:
                continue                      # this row's own universe: harmless
            print(f"  NOTE  {label} {scr}: '{m.group(0)}' appears in a comment or "
                  f"docstring at line {line_no} and is NOT bound.")
            print(f"        Before 2026-09-15 it WOULD have bound, and a second "
                  f"candidate directory makes this step's paths unresolvable.")
            in_code.add(m.group(1))


def _scan_text(txt, tag=None, span=()):
    """The scan, over source TEXT rather than one file.

    A STEP AND ITS HELPERS MUST BE SCANNED AS ONE UNIT, not scanned separately and
    unioned. The tag that resolves daily_trades_{tag}.csv is bound in the ENTRY
    POINT (audit_step.run(REGISTRY["mid"])) while the to_csv that uses it lives in
    the HELPER. Scanned apart, the helper has no tag and every filename with a
    placeholder falls into `unresolved`; scanned together, the tag applies. Getting
    this wrong is silent -- the checker reports success with the edges missing.
    """
    # CODE ONLY, from here down.
    _raw = txt
    txt, _ = _strip_prose(txt)
    var2dir, tags = {}, []
    for m in DIR_ASSIGN.finditer(txt):
        d = DIRKEY.get((m.group(2), m.group(3)))
        if d:
            var2dir[m.group(1)] = d
    for m in REG_ASSIGN.finditer(txt):
        d = _TAG2DIR.get(m.group(2))
        if d:
            var2dir[m.group(1)] = d
    for line in txt.splitlines():
        m = ASSIGN_LINE.match(line)
        if not m or "==" in line:
            continue
        names = [n.strip() for n in m.group(1).split(",") if n.strip().isidentifier()]
        refs = [DIRKEY.get(r) for r in DIR_REF.findall(m.group(2))]
        if len(names) > 1 and len(names) == len(refs) and all(refs):
            var2dir.update(dict(zip(names, refs)))
    for m in TAG_CALL.finditer(txt):
        d = DIRKEY.get((m.group(1), m.group(2)))
        if d:
            tags.append((d, m.group(3)))
    for m in REGISTRY_CALL.finditer(txt):
        d = _TAG2DIR.get(m.group(1))
        if d:
            tags.append((d, m.group(1)))
    # THE UNIVERSE FROM THE PIPELINE ROW, for a step that no longer names its own.
    # Before the collapse every per-universe step carried a literal
    # REGISTRY["mid"], and make_mid_audit.py's comment said in as many words that
    # the literal was KEPT because this scanner reads it -- "a loop variable there
    # matches nothing". Merging the pair removes the literal, and without this the
    # four `audit before chart` edges would vanish and the check would still report
    # success, which is the exact failure this module exists to catch.
    #
    # THE ROW IS A BETTER SOURCE THAN THE LITERAL EVER WAS. PIPELINE_ORDER's third
    # field is the declaration of which universe the step is invoked for (5c636cf);
    # the literal was a restatement of it inside the file, which is the duplicated
    # knowledge the collapse is removing everywhere else.
    if tag:
        d = _TAG2DIR.get(tag)
        if d:
            tags.append((d, tag))
    # THE ROW'S DECLARED SPAN, for a step that touches directories it never names.
    # Appended after the literals rather than replacing them: where the source does
    # name a universe, that naming still stands on its own, and this adds nothing
    # new. `tags` feeds a set-valued `own` and set-valued writes/reads, so a tag
    # contributed twice is indistinguishable from a tag contributed once.
    for t in span:
        d = _TAG2DIR.get(t)
        if d:
            tags.append((d, t))
    # VARIABLES THAT ARE NOT METRICS DIRECTORIES AT ALL -- see RAW_DIR_ASSIGN.
    nonmetrics = {m.group(1) for m in RAW_DIR_ASSIGN.finditer(txt)}
    # AXIS SUFFIX VARIABLES, PINNED TO THEIR DEFAULT "" -- see AXIS_SUFFIX_ASSIGN.
    axis_suffix = {m.group(1) for m in AXIS_SUFFIX_ASSIGN.finditer(txt)}
    own = sorted(set(var2dir.values()) | {d for d, _ in tags})
    default = own[0] if len(own) == 1 else None

    writes, reads, unresolved = set(), set(), set()
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        is_write = bool(WRITE_CALL.search(line))
        for mod, var, fname in PATH_EXPR.findall(line):
            # NOT AN EDGE: the directory is raw price data, not a metrics artefact.
            # Skipped outright rather than recorded as unresolved -- an unresolved
            # entry means "this MIGHT be an edge and I could not place it", and
            # this is not an edge at all.
            if not mod and var in nonmetrics:
                continue
            # AN AXIS SUFFIX IS "" AT THE DEFAULT SELECTION. Substituted before the
            # placeholder test, so the name becomes the canonical artefact.
            for _v in axis_suffix:
                fname = fname.replace("{" + _v + "}", "")
            if mod:                       # config74.METRICS_DIR_74 / "x.csv"
                d = DIRKEY.get((mod, var), default)
            else:
                d = var2dir.get(var, default)
            if "{tag}" in fname:
                targets = [(dd, fname.replace("{tag}", t)) for dd, t in tags] \
                          or ([(d, fname)] if d else [])
                if not tags:
                    unresolved.add((d, fname))
                    continue
            elif re.search(r'\{\w+\}', fname):
                unresolved.add((d, fname))
                continue
            elif d is None:
                unresolved.add((None, fname))
                continue
            else:
                targets = [(d, fname)]
            for t in targets:
                if re.search(r'\{\w+\}', t[1]):
                    unresolved.add(t)
                elif is_write:
                    writes.add(t)
                else:
                    reads.add(t)
    return writes, reads, unresolved


def analyse(pipeline, results_root=None, resolver=None, helpers=None,
            span_of=None):
    """pipeline: [(step_label, script_filename[, universe_tag])] in execution order.

    THE THIRD FIELD IS READ AND IGNORED HERE, deliberately. This checker reasons
    about ORDER -- which step writes a file another step reads -- and that is a
    property of the position, not of the universe the row is invoked for. Rows are
    indexed rather than unpacked so adding the field cannot break the check.

    -> (inversions, unresolved, edges) where an inversion is
       (step, script, dirkey, filename, [producing steps, all later]).

    `resolver` maps a script name to its path. It exists because the retired 58/74
    steps moved to frozen/ while the live ones stayed in results/, so a single root
    no longer locates every step. run_all.py passes its own script_path() so the
    checker and the runner cannot disagree about where a step lives.

    WHY THAT MATTERS MORE THAN IT LOOKS. The loop below SKIPS a script whose path
    does not exist. Without a shared resolver, moving a file would not fail the
    check -- it would quietly drop that file from the analysis and still report
    success, which is the exact failure mode this module was written to catch.
    """
    R = (results_root or ROOT / "results")
    # EARLIEST POSITION WINS, because after the collapse ONE SCRIPT APPEARS AT
    # SEVERAL POSITIONS. build_scores.py is STEP 10a for mid and STEP 10e for
    # n100; the dict comprehension this replaced kept whichever row came last, so
    # the merged step would have been treated as running only at 10e and every
    # mid consumer between 10a and 10e would have read as an inversion.
    #
    # min() is the correct reading and not merely the safe one: the question this
    # map answers is "had this producer run by the time that consumer ran", and a
    # script present at 10a HAS run by 10c whatever else it also does later.
    #
    # ------------------------------------------------------------------
    # AND THAT IS ALSO THIS CHECKER'S LIMIT, RECORDED RATHER THAN PATCHED.
    # ------------------------------------------------------------------
    # KEEPING THE EARLIEST POSITION PER SCRIPT, plus unioning each script's reads
    # and writes across its rows below, means a merged step COLLAPSES TO ONE
    # POSITION. make_chart.py becomes 10d and make_audit.py becomes 10c; 10c
    # precedes 10d, so no inversion exists here to report -- even when the n100
    # invocation at 10h depends on a writer at 10g that mid's invocation at 10d was
    # made to demand. That happened: on 2026-09-17 a cold `--universe all` died at
    # STEP 10d asking for results_n100/metrics/daily_trades_n100.csv, and this
    # checker reported 0 inversions on the same tree, correctly.
    #
    # IT IS NOT A DEFECT HERE AND IS NOT FIXED HERE. This module reasons about the
    # PIPELINE -- an ordering property of PIPELINE_ORDER, per script -- and that is
    # the right question for what it guards. Making it per-invocation would change
    # which edges it finds, and the edge inventory is the thing that must not move
    # silently; the collapse has already moved files under it six times.
    #
    # THE OTHER QUESTION HAS ITS OWN CHECK: check_plan_order.py walks the RESOLVED
    # PLAN one invocation at a time and asks whether each DECLARED input's writer
    # comes earlier in that same plan. run.py runs it for --list, --dry-run and a
    # real run. If you are here because an ordering bug got past this file, that is
    # probably where it lives.
    order = {}
    labels = {}
    for i, row in enumerate(pipeline):
        order.setdefault(row[1], i)
        labels.setdefault(row[1], []).append(row[0])
    # A MERGED STEP IS NAMED BY EVERY LABEL IT RUNS UNDER, so a report about
    # build_scores.py says "STEP 10a/10e" rather than silently picking one.
    step_of = {scr: "/".join(ls) for scr, ls in labels.items()}

    W, Rd, U = {}, {}, {}
    missing = []
    # ONE ROW AT A TIME, AND THE RESULTS UNIONED PER SCRIPT. A merged step appears
    # at several positions with a DIFFERENT universe each time -- make_audit.py is
    # STEP 10c for mid and STEP 10g for n100 -- and it genuinely writes both
    # universes' files across the run. Scanning once would resolve only one of
    # them; scanning per row and unioning gives the script the full write set it
    # actually has.
    for row in pipeline:
        label, scr = row[0], row[1]
        tag = row[2] if len(row) > 2 else None
        # FIELD 4, SPAN -- whose metrics directories this step's source touches.
        # DISTINCT FROM FIELD 3, which is INVOCATION: run.py reads field 3 against
        # main()'s arity, so an N-way step whose main() takes no universe must keep
        # field 3 None even though it writes into every universe's directory. That
        # divergence is why the scanner could not simply widen field 3 -- doing so
        # makes run.py refuse to start. See run_all.SPANS_REGISTRY.
        #
        # INERT WHILE THE SOURCE STILL NAMES ITS UNIVERSES IN LITERALS. REG_ASSIGN
        # and REGISTRY_CALL already resolve `M_n100 = REGISTRY["n100"].metrics_dir`,
        # so for STEP 12b as written today this contributes the same two directories
        # those literals already contribute and nothing moves. It exists so that a
        # registry-driven loop -- where `REGISTRY[t]` matches neither pattern,
        # because both require a quoted literal -- resolves instead of falling
        # silently into `unresolved`.
        span = span_of(row) if span_of else ()
        p = resolver(scr) if resolver else R / scr
        if not p.exists():
            if (label, scr, str(p)) not in missing:
                missing.append((label, scr, str(p)))
            continue
        # A STEP'S WRITES MAY LIVE IN A HELPER MODULE IT IMPORTS. When the three
        # near-identical audit scripts collapsed into results/audit_step.py, every
        # to_csv moved out of the step files and this scan stopped seeing them: four
        # producer edges vanished and the checker still reported success. The step
        # and its helpers are scanned as ONE text, so the tag bound in the entry
        # point resolves the filenames written in the helper.
        src = p.read_text()
        for hp in (helpers or {}).get(scr, ()):
            hp = Path(hp)
            if hp.exists():
                src += "\n" + hp.read_text()
        # A TAG IN PROSE IS NAMED, NOT BOUND AND NOT IGNORED. It no longer binds
        # (see _strip_prose), but staying silent would leave the next person to
        # rediscover why their docstring moved an edge.
        _warn_prose_tags(src, _strip_prose(src)[0], label, scr, tag)
        _w, _r, _u = _scan_text(src, tag=tag, span=span)
        W.setdefault(scr, set()).update(_w)
        Rd.setdefault(scr, set()).update(_r)
        U.setdefault(scr, set()).update(_u)

    producers = {}
    for scr, ws in W.items():
        for key in ws:
            producers.setdefault(key, []).append(scr)

    inversions, edges, unresolved = [], [], []

    _u_done = set()
    for label, scr in ((r[0], r[1]) for r in pipeline):
        for key in sorted(Rd.get(scr, ())):
            if key[1] in CACHES:
                continue
            if key in W.get(scr, ()):        # writes it itself
                continue
            prods = producers.get(key)
            if not prods:
                continue                      # external input
            earlier = [s for s in prods if order[s] < order[scr]]
            later = [s for s in prods if order[s] > order[scr]]
            edges.append((label, scr, key, prods))
            if not earlier:
                inversions.append((label, scr, key[0], key[1],
                                   [f"{step_of[s]} {s}" for s in later]))
        # ONCE PER SCRIPT, NOT ONCE PER ROW. U is unioned across a merged step's
        # rows, so iterating it inside the per-row loop reported every unresolved
        # key as many times as the script appears -- make_audit.py's two entries
        # printed four times and the count read 8 where the real figure is 2.
        # An inflated count in a checker is the same defect class as a deflated
        # one: the number stops meaning what it says.
        if scr not in _u_done:
            _u_done.add(scr)
            for key in sorted(U.get(scr, ()), key=lambda t: (t[0] or "", t[1])):
                unresolved.append((step_of[scr], scr, key))
    if missing:
        print("\n" + "!" * 88)
        print("PIPELINE ORDER CHECK -- these steps were NOT analysed: their files")
        print("were not found at the resolved path. The check below does NOT cover them.")
        for label, scr, path in missing:
            print(f"    {label:<10} {scr:<28} looked in {path}")
        print("!" * 88, flush=True)
    return inversions, unresolved, edges, missing


def enforce(pipeline, covered, results_root=None, verbose=False, resolver=None,
            helpers=None, list_unresolved=True, span_of=None):
    """Fail the pipeline on any inversion not already named in REQUIRED_INPUTS.

    `covered` is the set of filenames REQUIRED_INPUTS already guards, so a known
    dependency that is correctly ordered AND guarded is not reported twice. An
    inversion is fatal whether or not it is covered -- being in REQUIRED_INPUTS
    means the failure is legible, not that the order is acceptable.

    `list_unresolved=False` prints the COUNT but not the ten placeholder lines. It
    exists for the case where none of the steps that own those placeholders is
    being run -- an arms-only invocation of run.py -- because a warning that
    appears on every single run, about steps the run does not touch, is training to
    ignore the checker rather than information. The count still prints, so the
    entries are never invisible; an INVERSION is fatal either way, since ordering
    is a property of the pipeline and not of the selection.
    """
    inversions, unresolved, edges, missing = analyse(pipeline, results_root, resolver,
                                                     helpers, span_of=span_of)

    # AN UNDECLARED UNRESOLVED EDGE IS NOW FATAL.
    #
    # IT WAS A PRINTED LIST THAT GATED NOTHING, AND THAT IS WHY THE SAME SILENT
    # FAILURE HAPPENED FOUR TIMES -- STEP 16, STEP 17, the audit-script collapse
    # and the config-module fold. Each removed real producer edges from the
    # ordering check; each was found by a human reading the output rather than by
    # the check failing. A missing STEP was made fatal for exactly this reason and
    # the comment at that raise says so; `unresolved` never got the same treatment.
    #
    # THE KNOWN ONES ARE DECLARED, NOT TOLERATED. ALLOWED_UNRESOLVED names each
    # with why it cannot be resolved. Anything not on that list fails, so the cost
    # of a change that quietly stops an edge resolving is now a red build rather
    # than one more line in a list nobody reads.
    undeclared = [(lbl, scr, key) for lbl, scr, key in unresolved
                  if key not in ALLOWED_UNRESOLVED]
    if undeclared:
        raise SystemExit(
            "PIPELINE ORDER CHECK FAILED -- "
            f"{len(undeclared)} unresolved path expression(s) not declared:\n"
            + "\n".join(f"    {lbl:<9} {scr:<28} {(k[0] or '?')}/{k[1]}"
                         for lbl, scr, k in undeclared)
            + "\n\n  An unresolved expression is an edge the ordering check CANNOT SEE.\n"
              "  It is not a warning: a change that stops an edge resolving removes it\n"
              "  from the check silently, which has happened four times (see\n"
              "  KNOWN_ISSUES.md, \"`unresolved` is not fatal\").\n"
              "\n  Either make it resolvable, or -- if it genuinely cannot be resolved --\n"
              "  add it to check_pipeline_order.ALLOWED_UNRESOLVED WITH THE REASON.\n"
              "  Do not add it to silence this; the entry is read by whoever inherits it.")

    print(f"  pipeline order check: {len(edges)} resolved cross-step "
          f"dependencies, {len(unresolved)} unresolved, "
          f"{len(inversions)} inversion(s)"
          + ("" if (verbose or list_unresolved) else "  [unresolved not listed: no "
             "pipeline steps selected]"))
    # NAMED WITH THEIR REASON, NOT COUNTED. Everything reaching this point is on
    # ALLOWED_UNRESOLVED -- anything else already raised above -- so the line says
    # what it is and why, rather than leaving a bare count for a reader to wonder
    # about. The old form printed "(placeholder not expanded; not checked)" for
    # every entry, which described the symptom and never the reason.
    if verbose or (unresolved and list_unresolved):
        for label, scr, key in sorted(unresolved):
            print(f"    declared-unresolvable  {scr} -> {(key[0] or '?')}/{key[1]}")
            print(f"        {ALLOWED_UNRESOLVED[key]}")
    # A STEP THAT CANNOT BE FOUND IS FATAL, NOT A BANNER.
    #
    # It was a banner, and that is how STEP 16 went unchecked from whenever it was
    # added until 2026-09-04, and STEP 17 from 2026-09-11 until the run that found
    # it. An inversion is a defect the checker can SEE; an unresolvable step is the
    # checker having no information at all, which is strictly worse and was the
    # only outcome that did not stop the run. The banner stays -- it names what was
    # looked for -- and the run now stops.
    if missing:
        raise SystemExit(
            "PIPELINE ORDER CHECK FAILED -- "
            + f"{len(missing)} step(s) could not be found, so they were not checked:\n"
            + "\n".join(f"    {l:<10} {sc:<28} looked in {pa}" for l, sc, pa in missing)
            + "\n  A step the checker cannot locate is UNCHECKED, not merely unusual.\n"
              "  Either the file moved and run_all.STEP_DIRS does not cover its new\n"
              "  directory, or PIPELINE_ORDER names a step that no longer exists.")

    if not inversions:
        return
    print("\n" + "!" * 90)
    print("PIPELINE ORDERING ERROR -- a step reads a file written by a LATER step")
    print("!" * 90)
    for label, scr, d, fname, later in inversions:
        seen = " (named in REQUIRED_INPUTS)" if fname in covered else " (NOT in REQUIRED_INPUTS)"
        print(f"\n  {label}  {scr}")
        print(f"    reads   {d}/metrics/{fname}{seen}")
        print(f"    written by later step(s): {', '.join(later)}")
    print("\n  Move the producing step earlier in run_all.py. Do NOT make the")
    print("  consumer tolerate a missing file -- that hides the same bug again.")
    print("!" * 90, flush=True)
    sys.exit(1)


if __name__ == "__main__":
    import runpy
    mod = runpy.run_path(str(ROOT / "run_all.py"), run_name="__not_main__")
    # THE RESOLVER IS PASSED HERE TOO, AND IT WAS NOT. Standalone, this fell back
    # to `R / scr` and so could not find EITHER nautilus step, while the same check
    # run through run.py found one of them. Two entry points disagreeing about
    # where a step lives is how a step goes unchecked in one of them; run_all's
    # script_path() is the single definition and both now use it.
    inv, unres, edges, missing = analyse(mod["PIPELINE_ORDER"],
                                         resolver=mod["script_path"],
                                         helpers=mod["STEP_HELPERS"],
                                         span_of=mod["row_span"])
    print(f"{'step':<6}{'consumer':<28}{'file':<34}producers")
    for label, scr, key, prods in edges:
        print(f"{label:<6}{scr:<28}{key[0]+'/'+key[1]:<34}{','.join(prods)}")
    if missing:
        raise SystemExit(f"\n{len(missing)} step(s) could not be found; they are "
                         f"UNCHECKED. See the banner above.")
    print(f"\nunresolved: {len(unres)}")
    for label, scr, key in unres:
        print(f"  {scr} -> {key[0]}/{key[1]}")
    print(f"\ninversions: {len(inv)}")
    for i in inv:
        print("   ", i)
