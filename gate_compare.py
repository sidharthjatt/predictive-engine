#!/usr/bin/env python3
"""gate_compare.py -- compare a cell's output against a preserved baseline.

WHY THIS IS A TRACKED TOOL AND NOT A SCRIPT REWRITTEN EACH SESSION. Every
regression verdict this project quoted in the week to 2026-09-15 came from an
ad-hoc comparison written fresh in the session that needed it, and every one of
them had the same defect: it walked the BASELINE DIRECTORY and sha'd whatever
stood at each name in the live tree, without ever asking whether the run had
written that file. A baseline directory is a snapshot of a whole metrics folder,
so it holds artefacts from other arms, other profiles and earlier runs. Those
files are not touched by the cell under test, so they match themselves, every
time, no matter what the change did.

MEASURED 2026-09-15: of the 36 deterministic artefacts in the mid_v3 baseline,
`--universe mid --arm v3` writes 17. The other 19 are v2's and the tradeable
profile's. Every mid verdict of the form "35 of 36 byte-identical" was therefore
reporting 19 files that could not have moved, and a real regression in any of
them would have been invisible for the same reason.

n100_v2 was not affected -- all 17 of its deterministic baseline artefacts are
written by its cell -- which is why the defect survived: half the evidence was
sound.

SO THE DENOMINATOR IS WHAT THE CELL WROTE, and the rest is listed but never
counted. A file the tool cannot explain is UNCLASSIFIED and fails the run: the
one outcome that must never be silent is "not written, and nobody knows why",
because that is indistinguishable from a step that stopped writing.

  python3 gate_compare.py <baseline-cell-dir> <live-metrics-dir> \
                          --universe mid --arm v3 [--profile research] [--since EPOCH]
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ULP = 2.3e-16          # one unit in the last place, relative


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def why_not_written(stem, universe, arm, profile, known_universes):
    """The reason this cell never writes that artefact, or None if unexplained."""
    if "tradeable" in stem and profile != "tradeable":
        return f"wrong profile (file is tradeable; cell ran {profile})"
    arms_in_name = set(re.findall(r'(?<![A-Za-z0-9])(v[1-4])(?![0-9])', stem))
    # v2FINAL / v34 are FILE FAMILIES, not arm tags -- strip them before deciding.
    for fam in ("v2FINAL", "v34"):
        if fam.lower() in stem.lower():
            arms_in_name -= {fam[:2].lower()}
    if arms_in_name and arm not in arms_in_name:
        return f"wrong arm (file is for {'/'.join(sorted(arms_in_name))}; cell ran {arm})"
    if not arms_in_name and stem.startswith("daily_"):
        return "wrong arm (unsuffixed daily log belongs to the default arm v2)"
    for u in known_universes:
        if u != universe and re.search(rf'(?<![A-Za-z0-9]){re.escape(u)}(?![A-Za-z0-9])', stem):
            return f"wrong universe (file is {u}; cell ran {universe})"
    return None


def compare(bp, lp):
    """(verdict, detail) for one artefact pair."""
    if sha(bp) == sha(lp):
        return "EXACT", ""
    if bp.suffix == ".png":
        return "DIFFERS", "image bytes (PNGs drift; not a regression verdict on their own)"
    if bp.suffix == ".json":
        a, b = json.loads(bp.read_text()), json.loads(lp.read_text())
        return "DIFFERS", f"keys {sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))}"
    if bp.suffix != ".csv":
        return "DIFFERS", "content"
    import pandas as pd
    da, db = pd.read_csv(bp), pd.read_csv(lp)
    if list(da.columns) != list(db.columns) or len(da) != len(db):
        return "DIFFERS", f"shape {da.shape} -> {db.shape}"
    worst, col = 0.0, None
    for c in da.columns:
        if pd.api.types.is_numeric_dtype(da[c]) and pd.api.types.is_numeric_dtype(db[c]):
            r = ((da[c] - db[c]).abs() / da[c].abs().clip(lower=1e-12)).max()
            if pd.notna(r) and r > worst:
                worst, col = float(r), c
        elif not da[c].astype(str).equals(db[c].astype(str)):
            return "DIFFERS", f"text column '{c}'"
    if worst == 0.0:
        return "EXACT", ""
    return ("ULP" if worst <= ULP else "DIFFERS"), f"max rel {worst:.3e} in '{col}'"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline"); ap.add_argument("live")
    ap.add_argument("--universe", required=True); ap.add_argument("--arm", required=True)
    ap.add_argument("--profile", default="research")
    ap.add_argument("--since", type=float, required=True,
                    help="epoch seconds; a live file newer than this was written by the cell")
    a = ap.parse_args(argv)

    B, L = Path(a.baseline), Path(a.live)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from universes.registry import REGISTRY
        known = set(REGISTRY)
    except Exception:
        known = {a.universe}

    written, notwritten, unclassified = [], [], []
    for bp in sorted(B.iterdir()):
        if bp.is_dir():
            continue
        lp = L / bp.name
        if lp.exists() and lp.stat().st_mtime >= a.since:
            written.append((bp, lp)); continue
        why = why_not_written(bp.stem, a.universe, a.arm, a.profile, known)
        (notwritten if why else unclassified).append((bp, why or "UNEXPLAINED"))

    print("=" * 88)
    print(f" GATE  {a.universe} {a.arm} profile={a.profile}   baseline {B}")
    print("=" * 88)
    print(f"  WRITTEN BY THIS CELL (compared) : {len(written)}")
    print(f"  NOT WRITTEN (listed, not counted): {len(notwritten)}")
    print(f"  UNCLASSIFIED                     : {len(unclassified)}")
    print()

    tally = {}
    print("  --- COMPARED " + "-" * 73)
    for bp, lp in written:
        v, d = compare(bp, lp)
        tally[v] = tally.get(v, 0) + 1
        if v != "EXACT":
            print(f"    {v:<8} {bp.name:<42} {d}")
    print(f"    {tally.get('EXACT', 0)} of {len(written)} byte-exact"
          + (f", {tally.get('ULP', 0)} within one ULP" if tally.get("ULP") else "")
          + (f", {tally.get('DIFFERS', 0)} differ" if tally.get("DIFFERS") else ""))
    print()
    print("  --- NOT WRITTEN BY THIS CELL (never counted) " + "-" * 42)
    for bp, why in notwritten:
        print(f"    {bp.name:<42} {why}")
    if unclassified:
        print()
        print("  --- UNCLASSIFIED -- FATAL " + "-" * 61)
        for bp, _ in unclassified:
            print(f"    {bp.name:<42} the cell did not write it and no rule explains why")
        print("\nRESULT: FAIL -- an artefact went unwritten for a reason this tool cannot")
        print("  name. That is indistinguishable from a step that stopped writing.")
        return 2

    bad = tally.get("DIFFERS", 0)
    print(f"\nRESULT: {'FAIL' if bad else 'PASS'} -- {len(written)} artefacts measured, "
          f"{tally.get('EXACT', 0)} byte-exact, {bad} differing.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
