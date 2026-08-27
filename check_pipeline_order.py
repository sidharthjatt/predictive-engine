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
# and make_stats_both.py use, and missing it left real edges unresolved.
PATH_EXPR = re.compile(
    r'(?:(config(?:74|_mid|_n100)?)\.)?(\w+)\s*/\s*f?["\']'
    r'([A-Za-z0-9_.\-]*(?:\{\w+\}[A-Za-z0-9_.\-]*)*'
    r'\.(?:csv|png|json|parquet))["\']')
DIR_ASSIGN = re.compile(r'\b(\w+)\s*=\s*(config(?:74|_mid|_n100)?)\.(METRICS_DIR\w*)')
# make_final_summary.py binds both dirs in one tuple assignment, optionally wrapped
# in Path():  M58, M74 = Path(config.METRICS_DIR), Path(config74.METRICS_DIR_74)
# Missing this left fair_comparison_table.csv -- a real STEP 13 -> 14 edge --
# unresolved, so the checker could not see one of the dependencies it exists for.
ASSIGN_LINE = re.compile(r'^\s*([\w\s,]+?)\s*=\s*(.+)$')
DIR_REF = re.compile(r'(config(?:74|_mid|_n100)?)\.(METRICS_DIR\w*)')
# the audit scripts bind their tag at the bottom:
#   run(tmp, perm, config74.METRICS_DIR_74, 2025, "74")
TAG_CALL = re.compile(
    r'(config(?:74|_mid|_n100)?)\.(METRICS_DIR\w*)\s*,\s*\d+\s*,\s*["\'](\w+)["\']')

DIRKEY = {("config", "METRICS_DIR"): "results",
          ("config74", "METRICS_DIR_74"): "results74",
          ("config_mid", "METRICS_DIR_MID"): "results_mid",
          ("config_n100", "METRICS_DIR_N100"): "results_n100"}

# Panels restored into /tmp before the run, not produced by any step.
CACHES = {"v5_expanding_cache.csv", "raw_panel_cache.csv",
          "v74_expanding_cache.csv", "raw_panel74_cache.csv",
          "v_mid_expanding_cache.csv", "raw_panel_mid_cache.csv",
          "v_n100_expanding_cache.csv", "raw_panel_n100_cache.csv"}


def _scan(script_path):
    """-> (writes, reads, unresolved) as sets of (dirkey, filename)."""
    txt = script_path.read_text()
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


def analyse(pipeline, results_root=None):
    """pipeline: [(step_label, script_filename)] in execution order.

    -> (inversions, unresolved, edges) where an inversion is
       (step, script, dirkey, filename, [producing steps, all later]).
    """
    R = (results_root or ROOT / "results")
    order = {scr: i for i, (_, scr) in enumerate(pipeline)}
    step_of = {scr: label for label, scr in pipeline}

    W, Rd, U = {}, {}, {}
    for label, scr in pipeline:
        p = R / scr
        if not p.exists():
            continue
        W[scr], Rd[scr], U[scr] = _scan(p)

    producers = {}
    for scr, ws in W.items():
        for key in ws:
            producers.setdefault(key, []).append(scr)

    inversions, edges, unresolved = [], [], []
    for label, scr in pipeline:
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
        for key in sorted(U.get(scr, ())):
            unresolved.append((label, scr, key))
    return inversions, unresolved, edges


def enforce(pipeline, covered, results_root=None, verbose=False):
    """Fail the pipeline on any inversion not already named in REQUIRED_INPUTS.

    `covered` is the set of filenames REQUIRED_INPUTS already guards, so a known
    dependency that is correctly ordered AND guarded is not reported twice. An
    inversion is fatal whether or not it is covered -- being in REQUIRED_INPUTS
    means the failure is legible, not that the order is acceptable.
    """
    inversions, unresolved, edges = analyse(pipeline, results_root)
    print(f"  pipeline order check: {len(edges)} resolved cross-step "
          f"dependencies, {len(unresolved)} unresolved, "
          f"{len(inversions)} inversion(s)")
    if verbose or unresolved:
        for label, scr, key in unresolved:
            d = key[0] or "?"
            print(f"    unresolved  {scr} -> {d}/metrics/{key[1]}"
                  f"   (placeholder not expanded; not checked)")
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
    inv, unres, edges = analyse(mod["PIPELINE_ORDER"])
    print(f"{'step':<6}{'consumer':<28}{'file':<34}producers")
    for label, scr, key, prods in edges:
        print(f"{label:<6}{scr:<28}{key[0]+'/'+key[1]:<34}{','.join(prods)}")
    print(f"\nunresolved: {len(unres)}")
    for label, scr, key in unres:
        print(f"  {scr} -> {key[0]}/{key[1]}")
    print(f"\ninversions: {len(inv)}")
    for i in inv:
        print("   ", i)
