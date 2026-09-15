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


def _scan_text(txt, tag=None):
    """The scan, over source TEXT rather than one file.

    A STEP AND ITS HELPERS MUST BE SCANNED AS ONE UNIT, not scanned separately and
    unioned. The tag that resolves daily_trades_{tag}.csv is bound in the ENTRY
    POINT (audit_step.run(REGISTRY["mid"])) while the to_csv that uses it lives in
    the HELPER. Scanned apart, the helper has no tag and every filename with a
    placeholder falls into `unresolved`; scanned together, the tag applies. Getting
    this wrong is silent -- the checker reports success with the edges missing.
    """
    var2dir, tags = {}, []
    for m in DIR_ASSIGN.finditer(txt):
        d = DIRKEY.get((m.group(2), m.group(3)))
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
    own = sorted(set(var2dir.values()) | {d for d, _ in tags})
    default = own[0] if len(own) == 1 else None

    writes, reads, unresolved = set(), set(), set()
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        is_write = bool(WRITE_CALL.search(line))
        for mod, var, fname in PATH_EXPR.findall(line):
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


def analyse(pipeline, results_root=None, resolver=None, helpers=None):
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
        _w, _r, _u = _scan_text(src, tag=tag)
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
            helpers=None, list_unresolved=True):
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
    inversions, unresolved, edges, missing = analyse(pipeline, results_root, resolver, helpers)
    print(f"  pipeline order check: {len(edges)} resolved cross-step "
          f"dependencies, {len(unresolved)} unresolved, "
          f"{len(inversions)} inversion(s)"
          + ("" if (verbose or list_unresolved) else "  [unresolved not listed: no "
             "pipeline steps selected]"))
    if verbose or (unresolved and list_unresolved):
        for label, scr, key in unresolved:
            d = key[0] or "?"
            print(f"    unresolved  {scr} -> {d}/metrics/{key[1]}"
                  f"   (placeholder not expanded; not checked)")
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
                                         helpers=mod["STEP_HELPERS"])
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
