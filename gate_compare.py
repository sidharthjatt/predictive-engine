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
# THE ONE ACCEPTED NON-IDENTICAL FIELD SET, AND IT LIVES HERE, NOT IN A REVIEW
# ---------------------------------------------------------------------------
# STEP 7 PRODUCED THE FIRST PRE/POST PAIR THAT WAS NOT BYTE-IDENTICAL. Six
# v34_params*.json files moved, one per cell, and all six moved only inside
# `git_state`, which records the commit the run was produced at and whether the
# tree was clean. HEAD necessarily differs between a pre-merge and a post-merge
# run, so that block MUST move; a merge that left it unmoved would mean it was
# recording nothing.
#
# THAT VERDICT WAS REACHED BY SURVEYING WHAT DIFFERED, WHICH IS THE EXACT SHAPE
# THE POLICY BELOW EXISTS TO REJECT. The conclusion was right and the process was
# not: an exception argued at review time is available to argue again, for a field
# that is not provenance, by a reader who wants a green gate. So the exception is
# DATA HERE, checked by the comparator on every run, and a params file that moves
# in any other field is DIFFERS exactly as before.
#
# SCOPED TO `git_state`, NOT MATCHED BY BARE KEY NAME. "note" in particular is a
# generic word; excluding it wherever it appears would silently swallow a moved
# note somewhere else in the document. The block is named on the left of each pair.
#
# NOTHING IS ADDED TO THIS TUPLE WITHOUT THE OWNER OF THE REPOSITORY SAYING SO.
# It is four fields because four fields are provenance. A fifth entry is a request
# to stop checking something, and it has to look like one.
PROVENANCE_FIELDS = (
    ("git_state", "commit"),
    ("git_state", "working_tree_dirty"),
    ("git_state", "modified_or_untracked_files"),
    ("git_state", "note"),
)


_ABSENT = object()


def _strip_provenance(doc):
    """`doc` without the named provenance fields. Returns (doc, [fields removed])."""
    if not isinstance(doc, dict):
        return doc, []
    out = dict(doc)
    removed = []
    for block, field in PROVENANCE_FIELDS:
        blk = out.get(block)
        if isinstance(blk, dict) and field in blk:
            blk = dict(blk)
            blk.pop(field)
            out[block] = blk
            removed.append(f"{block}.{field}")
    return out, removed


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
    ("midcap150",  "all", "research",  "67 s", 43, "canonical unsuffixed v34 artefacts"),
    ("nifty100", "all", "research",  "52 s", 43, "canonical, plus chart_nifty100_v1_v2_v3_v4.png"),
    ("midcap150",  "v3",  "research",  "24 s", 20, "the SUFFIXED naming branch on mid"),
    ("nifty100", "v2",  "research",  "20 s", 20, "the suffixed branch on n100; the accepted cell"),
    # THE TWO TRADEABLE CELLS. Added 2026-09-15 to cover the participation cap, and
    # they exercise the cap's CODE PATH -- vol20 is built, passed and consulted on
    # every buy -- but on today's data it never shrinks an order.
    #
    # THEY WERE ADDED AS "the cap BINDING, largest effect (Rs 3.85M)" AND THAT IS
    # NO LONGER WHAT THEY ARE. Measured 2026-09-20 at commit 7dd37d6: zero rows
    # with reason "participation cap" in either arm's daily_skipped artefact
    # (n=850 fills on v1, n=1006 on v2), highest participation 0.709 and 0.345
    # against a cap of 1.00, and all eight of {trades, skipped, holdings, summary}
    # x {v1, v2} byte-identical to their unsuffixed research twins. The Rs 3.85M
    # belonged to an earlier snapshot; the tree has moved since and nothing
    # re-checked the sentence.
    #
    # SO THE STATEMENT "mid is the only universe whose cap binds" IS WITHDRAWN.
    # n100 was already recorded inert; as of this commit mid is inert too, and no
    # cell in this gate replays a run in which the cap changed a single fill. What
    # these cells prove is that the tradeable naming branch and the cap's plumbing
    # reconcile -- not that a cap-shrunk order has ever been replayed.
    #
    # This is a dated measurement of these runs, not a property of the cap. Capital,
    # universe and data all move it. Re-count the "participation cap" rows in the
    # run's own daily_skipped artefact rather than trusting this comment.
    #
    # THE BYTE-IDENTITY ABOVE IS A PROPERTY OF cap=1.00, NOT OF THE CAP. Re-measured
    # 2026-09-22, and the sell side is now capped too, which it was not when the
    # sentences above were written: at cap=1.00 the cap still binds on NO fill on
    # either universe on either side (nifty100 940 fills, midcap150 1006), so the
    # identity holds. AT cap=0.10 IT DOES NOT, BY DESIGN:
    #
    #     nifty100    2 BUY + 1 SELL binds of 941 fills   CAGR 19.01 -> 18.88
    #     midcap150   7 BUY + 3 SELL binds of 1009 fills  CAGR 27.80 -> 27.61
    #
    # So a future run of these cells at a lower cap SHOULD differ from its research
    # twin, and a diff there is the cap working rather than a regression. These two
    # cells still run at the profile default; if that default moves, the expectation
    # above moves with it and this comment must be re-measured, not edited.
    ("midcap150",  "v1",  "tradeable", "25 s", 20, "tradeable branch; cap inert 2026-09-20  [PARTIAL]"),
    ("midcap150",  "v2",  "tradeable", "25 s", 20, "the arm 12b reads; cap inert  [PARTIAL]"),
)

# THE TWO TRADEABLE CELLS ARE PARTIAL, AND THAT IS NOT A DETAIL. They exercise the
# engine and the audit -- STEP 10b, 10c, 10d, 12b, 15, 15b all run, the artefacts
# are written, and all four mid arms reconcile to under a paisa.
#
# THEY USED TO DIE AT STEP 16, AND NO LONGER DO. run_all._present() demanded a
# profile-suffixed v_midcap150_expanding_cache_tradeable.csv; the score panel carries no
# profile dimension, so the guard was asking for a file that should not exist.
# Fixed 2026-09-16 by scoping the guard to the axes each input's name declares.
# `--universe mid --arm v2 --profile tradeable` now runs all nine steps, exit 0.
#
# THE CELLS ARE STILL [PARTIAL], AND FOR A STRONGER REASON THAN BEFORE. They no
# longer stop early -- but NOTHING HERE COMPARES WHAT STEP 16 AND STEP 17 PRODUCE
# under this profile against anything. Before 2026-09-16 those steps had never run
# under it at all; now they run and are unmeasured, which is the easier of the two
# states to mistake for coverage. A green tradeable cell means "the cap is applied
# and replayed correctly", NOT "the tradeable pipeline is verified".
#
# UNTIL A CELL EXISTS THAT ANCHORS THEM, EVERY TRADEABLE ARTEFACT SAYS SO OF
# ITSELF: profiles.gate_status() is bannered by run.py at both ends of the run and
# written into v34_params{SFX}.json. Research artefacts are untouched by it, which
# the standing gate proves.
#
# THAT SAME NOTICE USED TO CARRY profiles.CAP_INERT_NOTICE. SUPERSEDED 2026-09-22.
# This comment read: "so a reader who meets a tradeable artefact is told in the
# artefact that its cap did not bind on 2026-09-20 and that it is not, on that
# date, a capped result ... on these runs applying it changed nothing." That was
# true of the two universes it was written from and false of six cells run on
# 2026-09-22, over which the banner printed CAP DID NOT BIND while the cap bound.
# The stored claim is deleted and profiles.cap_report() now counts the
# `participation cap` rows out of the run's own daily_skipped instead. A green
# tradeable cell still means "the cap is applied and replayed correctly" and
# whether applying it changed anything is a per-run measurement, not a property.
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
#                         The cells remain [PARTIAL] for the reason given above
#                         them: nothing here compares what STEP 16 and STEP 17
#                         produce under this profile against anything.
#
#                         THE CLAIM THAT FOLLOWED WAS DISCHARGED ON 2026-09-16 BY
#                         COMMIT 211f151, and is kept because it is the reason the
#                         fourth field in REQUIRED_INPUTS exists:
#
#                           "It still cannot COMPLETE: run_all._present() demands a
#                            profile-suffixed v_midcap150_expanding_cache_tradeable.csv,
#                            and the score panel has no profile dimension, so
#                            STEP 16 blocks. A naming-authority defect, not a cap
#                            one. See KNOWN_ISSUES.md, 'The tradeable profile
#                            cannot complete'."
#
#                         run_all._present() (run_all.py:819) now composes a
#                         suffix only for the axes an input's own name carries,
#                         taken from the compulsory fourth field of its
#                         REQUIRED_INPUTS entry. The score panel is declared
#                         AXIS_FREE (run_all.py:555, entries at :608, :617, :634),
#                         so the guard asks for v_midcap150_expanding_cache.csv by
#                         its one true name and STEP 16 does not block. The block
#                         at lines 161-165 above records the same discharge.
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


# ---------------------------------------------------------------------------
# A PASS THAT WENT DIRTY HALFWAY IS CAUGHT BY THE ARTEFACT, NOT BY THE HARNESS
# ---------------------------------------------------------------------------
# THE REFUSAL AT THE TOP OF main() CHECKS THE TREE ONCE, BEFORE COMPARING, AND
# THAT IS NOT ENOUGH. On 2026-09-16 a post pass started clean, and the tree was
# edited while its first cell ran; the second cell recorded
# working_tree_dirty=true. The gate still reported PASS, and the only sign was in
# the PROVENANCE detail -- "git_state.commit" on one cell and all four fields on
# the other. A gate that can be invalidated halfway and is caught only by reading
# its own verdict carefully is not a gate.
#
# THE ARTEFACT CARRIES THE ANSWER, WHICH IS BETTER THAN ANY HARNESS CHECK. Each
# run stamps `git_state.working_tree_dirty` into its params JSON. Reading it here
# catches a dirty pass PER CELL, whatever ran the cells, including a harness that
# checks nothing at all -- and it catches the half that went dirty rather than the
# pass as a whole.
#
# THE FIELD IS EXCLUDED FROM THE DIFF AND CHECKED FOR ITS VALUE. Those are
# different questions: whether it MOVED between passes is provenance and is
# forgiven; whether it is TRUE is the pass admitting it cannot be reproduced.
def dirty_stamp(p):
    """(commit, n_files) when this artefact records a dirty tree, else None."""
    if p.suffix != ".json":
        return None
    try:
        g = json.loads(p.read_text()).get("git_state")
    except Exception:
        return None
    if isinstance(g, dict) and g.get("working_tree_dirty") is True:
        return (str(g.get("commit", "?"))[:12], g.get("modified_or_untracked_files", "?"))
    return None


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
        # PROVENANCE IS STRIPPED AND THE VERDICT IS NAMED, NOT FOLDED INTO EXACT.
        # Calling it EXACT would hide that the file moved at all, which is the
        # other half of the same defect: an accepted difference has to stay
        # visible in the report or the next reader cannot tell it was accepted.
        sa, ra = _strip_provenance(a)
        sb, rb = _strip_provenance(b)
        if (ra or rb) and sa == sb:
            # NAME THE FIELDS THAT MOVED, NOT THE FIELDS THAT ARE EXCLUDED. The
            # first version printed all four whenever all four were present, so a
            # pair whose only real difference was `commit` was reported as though
            # the tree state and the note had moved too. An accepted exception that
            # overstates itself is the same defect as one that hides: the reader
            # cannot tell what was actually forgiven.
            moved = [f"{blk}.{f}" for blk, f in PROVENANCE_FIELDS
                     if isinstance(a.get(blk), dict) and isinstance(b.get(blk), dict)
                     and a[blk].get(f, _ABSENT) != b[blk].get(f, _ABSENT)]
            return "PROVENANCE", (", ".join(moved) + " only") if moved else "identical"
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

    # ------------------------------------------------------------------
    # BOTH PASSES RUN CLEAN, AND THIS IS WHERE THAT STOPS BEING A HABIT
    # ------------------------------------------------------------------
    # Step 7's post-merge pass ran with 23 modified files in the tree. The
    # comparison was still sound -- the only field that moved was provenance --
    # but it was sound by luck: `git_state.working_tree_dirty` was TRUE, so the
    # artefact itself recorded that the commit did not describe the run, and the
    # gate compared a reproducible pass against an unreproducible one.
    #
    # A DIRTY TREE MEANS THE POST PASS CANNOT BE RE-RUN TO THE SAME BYTES by
    # anyone, including the person who ran it, because what produced it is not in
    # git. That is not a comparison; it is a measurement of something that no
    # longer exists. So this refuses rather than warning: a warning at the top of
    # a long report is read once.
    #
    # THERE IS NO --allow-dirty. Adding one is a request to compare against
    # something unreproducible, and it should have to be argued for, in this file,
    # by name.
    import subprocess
    try:
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               cwd=str(Path(__file__).resolve().parent),
                               capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:                      # not a checkout, or no git
        dirty = ""
        print(f"  NOTE  could not read git state ({type(e).__name__}); "
              f"the clean-tree requirement was NOT checked.")
    if dirty:
        n = len(dirty.splitlines())
        print("REFUSING -- the working tree has "
              f"{n} modified or untracked file(s).")
        print("  Both passes of a pre/post gate must run from a clean tree, or the")
        print("  post pass records working_tree_dirty=true and cannot be reproduced")
        print("  by anyone from git. Commit the change, then run the post pass.")
        for line in dirty.splitlines()[:12]:
            print(f"    {line}")
        if n > 12:
            print(f"    ... and {n - 12} more")
        return 2

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
    stamped_dirty = []
    print("  --- COMPARED " + "-" * 73)
    for bp, lp in written:
        for side, q in (("baseline", bp), ("live", lp)):
            d0 = dirty_stamp(q)
            if d0:
                stamped_dirty.append((side, q.name, d0))
        v, d = compare(bp, lp)
        tally[v] = tally.get(v, 0) + 1
        if v != "EXACT":
            print(f"    {v:<8} {bp.name:<42} {d}")
    print(f"    {tally.get('EXACT', 0)} of {len(written)} byte-exact"
          + (f", {tally.get('ULP', 0)} within one ULP" if tally.get("ULP") else "")
          + (f", {tally.get('PROVENANCE', 0)} provenance-only" if tally.get("PROVENANCE") else "")
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

    if stamped_dirty:
        print()
        print("  --- PASS RECORDED A DIRTY TREE -- FATAL " + "-" * 47)
        for side, name, (commit, n) in stamped_dirty:
            print(f"    {side:<8} {name:<38} commit {commit}, {n} modified or "
                  f"untracked file(s)")
        print("\n  That artefact was produced from a tree that is not in git, so")
        print("  nobody -- including whoever ran it -- can reproduce it. The tree was")
        print("  clean when the pass STARTED or the refusal above would have fired;")
        print("  it went dirty while the pass was running. Commit, then run again.")
        print("\nRESULT: FAIL -- the comparison is against something unreproducible.")
        return 2

    bad = tally.get("DIFFERS", 0)
    prov = tally.get("PROVENANCE", 0)
    print(f"\nRESULT: {'FAIL' if bad else 'PASS'} -- {len(written)} artefacts measured, "
          f"{tally.get('EXACT', 0)} byte-exact, "
          + (f"{prov} provenance-only, " if prov else "")
          + f"{bad} differing.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
