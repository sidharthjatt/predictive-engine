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


# ---------------------------------------------------------------------------
# CHECKSUM IS THE GATE. GREP IS A HINT.
# ---------------------------------------------------------------------------
# POLICY, 2026-09-15. A keyword survey of divergences has twice declared itself
# complete and been wrong.
#
#   step 5  the engine pair was surveyed for render and artefact divergence, and
#           the survey held -- but only because the pre/post checksum was run.
#   step 6  the chart pair's survey named two divergent render parameters, dpi and
#           the ax[1] legend font size. It missed a THIRD: the drawdown legend's
#           label format, which differs in three ways at once (the split token,
#           the word "max", and .1f versus .0f). The pattern matched the
#           ax[1].plot call and never reached the argument on its CONTINUATION
#           LINE. n100's chart moved by 3,971 pixels -- 0.103% of the image, all
#           of it inside one legend box -- and nothing in the survey said so.
#
# SO: A MERGE IS NOT GATED UNTIL BOTH UNIVERSES' ARTEFACTS ARE BYTE-IDENTICAL
# PRE/POST ON THE SAME PANEL. Run the cell at HEAD, checksum, apply the merge, run
# it again, checksum. No survey of differences substitutes for that, and from
# step 7 on a survey must not be offered as evidence that a merge is clean.
#
# AND A COMPARISON MUST EXERCISE WHAT IT CLAIMS TO. The first pixel diff of that
# n100 chart reported ZERO differences, because the last run executed at that
# moment was the PRE-merge one -- so it compared the pre-merge file against its
# own copy and proved nothing. Same class as the prose stripper that passed a
# two-line test and did nothing on the real tree: a check that passes because it
# never exercised the thing it claims to check. State which run produced the file
# you are checksumming, or the checksum is decoration.

# ---------------------------------------------------------------------------
# THE STANDING GATE FOR STEPS 4-8 OF THE COLLAPSE
# ---------------------------------------------------------------------------
# FOUR CELLS, AND THE TWO KINDS ARE NOT INTERCHANGEABLE. Measured 2026-09-15 by
# running each and recording what it wrote, rather than reasoning about it.
#
# arms.registry.selection_suffix() is EMPTY for a full selection, because only a
# four-arm run may write the canonical v34 artefacts. So:
#
#   --arm all  writes  v34_comparison.csv      chart_v34.png      DAILY_LOG_mid.txt
#   --arm v3   writes  v34_comparison_v3.csv   chart_v34_v3.png   DAILY_LOG_mid_v3.txt
#
# These are DIFFERENT ARTEFACTS FROM DIFFERENT NAMING BRANCHES. An all-arm cell
# does not subsume a single-arm one, and a gate built only on all-arm cells leaves
# the suffixed branch -- exactly what the merged chart and engine must get right --
# entirely unexercised. That is the trap this table exists to close.
#
# Every cell runs on cached panels; the scoring path is skipped in all four.
STANDING_GATE = (
    # (universe, arm,  profile,    runtime, artefacts, what it alone exercises)
    ("mid",  "all", "research",  "67 s", 43, "canonical unsuffixed v34 artefacts"),
    ("n100", "all", "research",  "52 s", 43, "canonical, plus chart_n100_v1_v2_v3_v4.png"),
    ("mid",  "v3",  "research",  "24 s", 20, "the SUFFIXED naming branch on mid"),
    ("n100", "v2",  "research",  "20 s", 20, "the suffixed branch on n100; the accepted cell"),
    # THE ONLY CELLS WHERE THE PARTICIPATION CAP BINDS. Added 2026-09-15. mid is
    # the only universe whose cap binds at all -- n100 tradeable reproduces its
    # research run exactly -- so until these existed, NO cap-binding configuration
    # had ever been independently replayed, and audit_step measured research under
    # a tradeable label for as long as the profile existed. v1 carries the largest
    # cap effect (Rs 3.85M); v2 is the arm whose trail the chart and STEP 12b read.
    ("mid",  "v1",  "tradeable", "25 s", 20, "the cap BINDING, largest effect  [PARTIAL]"),
    ("mid",  "v2",  "tradeable", "25 s", 20, "the cap binding on the arm 12b reads  [PARTIAL]"),
)

# THE TWO TRADEABLE CELLS ARE PARTIAL, AND THAT IS NOT A DETAIL. They exercise the
# engine and the audit -- STEP 10b, 10c, 10d, 12b, 15, 15b all run, the artefacts
# are written, and all four mid arms reconcile to under a paisa. They then DIE AT
# STEP 16: run_all._present() demands a profile-suffixed
# v_mid_expanding_cache_tradeable.csv, and the score panel carries no profile
# dimension, so the guard asks for a file that should not exist.
#
# SO A GREEN TRADEABLE CELL MEANS "the cap is applied and replayed correctly",
# NOT "the tradeable pipeline works". STEP 16 and STEP 17 -- the Nautilus export
# and execution -- have never run under this profile. Do not quote these cells as
# end-to-end coverage.
#
# Parked until after the collapse by explicit decision: it is the third instance of
# one missing naming authority, and fixing it at the call site would add a fourth
# place that decides which artefacts carry a profile dimension. See KNOWN_ISSUES,
# "No component owns which axes an artefact carries".

# WHAT THE STANDING GATE DOES NOT COVER, stated so coverage is never assumed. Each
# of these is a real axis of this pipeline that no cell above touches:
#
#   --profile tradeable   RECONCILES since 2026-09-15 (audit_step now pairs the cap
#                         with vol20), and mid v1/v2 tradeable are gate cells above.
#                         It still cannot COMPLETE: run_all._present() demands a
#                         profile-suffixed v_mid_expanding_cache_tradeable.csv, and
#                         the score panel has no profile dimension, so STEP 16
#                         blocks. A naming-authority defect, not a cap one. See
#                         KNOWN_ISSUES.md, "The tradeable profile cannot complete".
#   --rebal 40            the _r40 cadence suffix. Exercised by no cell here.
#   9 of 15 arm subsets   arms.registry.suffix() names any subset (_v1_v3 and so
#                         on); four singles and one full selection are covered,
#                         the other ten combinations are not. docs/HANDOFF.md
#                         records the same gap.
#   the scoring path      every cell runs on cached panels, so
#                         build_scores_step.run() returns early. Covering it costs
#                         a 34-minute forced rebuild.


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


def print_cells():
    print("STANDING GATE -- steps 4-8 of the collapse\n")
    for u, arm, pf, rt, n, why in STANDING_GATE:
        print(f"  --universe {u:<4} --arm {arm:<3} --profile {pf:<8}"
              f"  {rt:>5}  {n:>3} artefacts   {why}")
    print("\n  Both kinds are required: a full selection writes the CANONICAL v34")
    print("  artefacts and a single arm writes the SUFFIXED ones. Neither subsumes")
    print("  the other. See the module docstring for what is outside this gate:")
    print("  the tradeable profile, the _r40 cadence, 10 of 15 arm subsets, and")
    print("  the scoring path.")


def main(argv=None):
    if (argv if argv is not None else sys.argv[1:])[:1] == ["--cells"]:
        print_cells(); return 0
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
