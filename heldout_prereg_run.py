#!/usr/bin/env python3
"""heldout_prereg_run.py -- execute experiments/HELDOUT_PREREG.txt. Once.

    ./venv/bin/python heldout_prereg_run.py

WHAT THIS IS, AND WHAT IT REFUSES TO BE
    The pre-registration is a protocol, not a program. This is the program, and
    every choice in it is the file's choice rather than mine. Where the file is
    silent I have refused rather than decided -- see THE ONE THING THE FILE DOES
    NOT SPECIFY below.

THE WINDOW IS SPENDABLE EXACTLY ONCE, AND THAT IS ENFORCED HERE RATHER THAN
REMEMBERED. Section 4 of the pre-registration says so and cannot make itself true.
This script refuses to start if a result block is already present in
HELDOUT_PREREG.txt, and it appends its result to that file as its last act. A
second run is a refusal, not a second number.

    NOTHING HERE MAY BE RE-RUN "to check". If it aborts before the held-out
    figure, nothing was spent and it may be fixed and run again. If it reaches the
    verdict, the window is gone.

THE TRAP THIS SCRIPT EXISTS TO AVOID
    The obvious way to reach the held-out sessions is to move config.BT_END_DATE.
    That would also move the monthly walk-forward, refitting the model on the data
    it is being tested against, and section 1 forbids it: "training data
    UNCHANGED". THE SCORE PANEL IS NOT REBUILT, NOT REFITTED, AND NOT TOUCHED. It
    already covers the held-out sessions -- 575 rows over 6 sessions on n100, 887
    over 6 on mid -- scored by a walk-forward that stopped where it stopped.

    ONLY THE BACKTEST'S DATE INDEX IS EXTENDED. `bd` runs to the last panel date
    instead of to BT_END_DATE. Everything else is the shipping engine's own call.

    AND target_vol IS PINNED TO THE IN-SAMPLE WINDOW. results/engine_v2_final.py
    computes `tv = port_vol.loc[bd].median()`, so extending `bd` would recompute it
    over held-out data -- a refit, small but real, and on exactly the data under
    test. `tv` here is the median over the IN-SAMPLE dates only.

WHAT LICENSES THE EXTENSION, AND IT IS CHECKED RATHER THAN ASSUMED
    If extending the date index changed anything before 2026-05-29, the held-out
    tail would be a different backtest rather than a continuation of the published
    one. So the in-sample slice of the extended curve is compared against the
    SHIPPED v2FINAL_equity.csv, point for point, and the run ABORTS if it differs.
    That check runs BEFORE any held-out number is computed, so failing it costs
    nothing.

THE ONE THING THE FILE DOES NOT SPECIFY, AND WHY IT IS NOT DECIDED HERE
    Section 2 defines r_universe as "the equal-weight mean daily return of that
    universe's constituents" and does not say on which basis. There is exactly one
    such series in the shipping engine -- `px.pct_change().mean(axis=1)`, the
    thing v2FINAL's buy & hold is built from -- so that is what is used, and it is
    named in the output. If a reader thinks the file meant something else, the
    output says precisely which series was used and they can disagree with it.
"""
# ---------------------------------------------------------------------------
# DETERMINISM PIN -- SET BEFORE ANY NUMERIC LIBRARY IS IMPORTED, as run.py does
# and for the same reason: an OpenMP/BLAS runtime reads its thread count when it
# initialises at import.
# ---------------------------------------------------------------------------
import os as _os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ[_v] = "1"
_os.environ["PYTHONHASHSEED"] = "0"

import inspect
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "results"), str(ROOT / "nautilus")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pandas as pd

import cadence
import config
import profiles
import engine_core
from engine_core import precompute
from test_exposure import backtest_exposure, TOP_N, BUFFER
from build_scores_step import SEEDS
from universes.registry import REGISTRY

PREREG = ROOT / "experiments" / "HELDOUT_PREREG.txt"
OUT = ROOT / "diagnostics" / "heldout_prereg_result.txt"
# THE ALREADY-SPENT SENTINEL. A machine token rather than a phrase, because the
# check is `marker in file text` and prose in this file already contains the word
# RESULT ("A RESULT THAT IS TOO GOOD IS ALSO A FAIL", section 3).
#
# IT ERRS OVER-BROAD, DELIBERATELY. A false positive -- the token appearing for
# some unrelated reason -- refuses a FIRST run, which costs nothing and is
# recoverable by looking at the file. A false negative would permit a SECOND
# held-out number, which is not recoverable by anything. Given a choice between
# refusing a run that should have happened and allowing one that should not, this
# refuses.
#
# IT CANNOT BE UNDER-BROAD FOR ITS OWN BLOCK: the same constant is written into
# the block this script appends, so the check and the thing it looks for are one
# definition.
RESULT_MARKER = "[HELDOUT-PREREG-RESULT-BLOCK]"

# The pre-registration's own numbers, quoted here so the output can compare itself
# against the file rather than against my memory of it.
PREREG_COMMIT = "806a7fbba9a41a954e0ac75bc5a8064ecbabd414"
PREREG_ASSUMED_N = 65          # section 3, "roughly 65 pooled sessions"
VOL_WIN = 60                   # engine_v2_final's window for port_vol
REPRO_TOL = 1e-12              # exact zero is expected; see the reproduction gate


def _fail(*msg):
    print("\n" + "!" * 78)
    for m in msg:
        print(m)
    print("!" * 78)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# PRECONDITIONS -- section 6's checklist, in its order, before anything is read
# ---------------------------------------------------------------------------
def preconditions(W):
    spent = RESULT_MARKER in PREREG.read_text()
    if spent:
        _fail("REFUSING: experiments/HELDOUT_PREREG.txt already carries a result.",
              "  The window is spendable exactly once (section 4) and it has been",
              "  spent. A second run cannot produce a held-out number; it would",
              "  produce a second look at data that is no longer held out.",
              f"  Looked for the sentinel {RESULT_MARKER!r} and found it.")

    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT),
                           capture_output=True, text=True, check=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                          capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        _fail("REFUSING: the working tree is dirty.",
              "  Section 1: 'THE CLEAN TREE IS PART OF THE SPECIFICATION ... If the",
              "  tree is dirty when the run starts, stop and commit first.'",
              *[f"    {l}" for l in dirty.splitlines()[:10]])

    # THE COMMIT DEVIATION IS PRINTED, NOT WAIVED AND NOT SILENTLY ACCEPTED.
    # The decision to proceed is recorded in the pre-registration itself; this
    # states the fact again at run time so it appears in the output a reader keeps.
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", PREREG_COMMIT, "HEAD"],
                         cwd=str(ROOT), capture_output=True, text=True)
    W("  PRECONDITIONS")
    W(f"    already spent?          NO -- sentinel {RESULT_MARKER} absent from")
    W(f"                            experiments/HELDOUT_PREREG.txt. The check errs")
    W(f"                            OVER-BROAD: a false match refuses a first run,")
    W(f"                            which is recoverable; a miss would allow a")
    W(f"                            second number, which is not.")
    W("    working tree            clean")
    W(f"    HEAD                    {head}")
    W(f"    pre-registered commit   {PREREG_COMMIT}")
    W(f"    relationship            {'ANCESTOR of HEAD' if anc.returncode == 0 else 'NOT AN ANCESTOR -- see below'}")
    if anc.returncode != 0:
        _fail("REFUSING: the pre-registered commit is not an ancestor of HEAD.",
              "  The recorded deviation covers running at a DESCENDANT of 806a7fb",
              "  whose intervening changes were all gated byte-identical. A HEAD",
              "  that does not contain that commit is a different tree and the",
              "  deviation recorded in the file does not cover it.")

    # SECTION 1, PARAMETER BY PARAMETER. Anything that moved makes this a new
    # trial, and the file says so, so it is checked rather than trusted.
    checks = [
        ("TOP_N", TOP_N, 8),
        ("BUFFER", BUFFER, 16),
        ("HORIZON", engine_core.HORIZON, 20),
        ("rebalance", cadence.selected(), 20),
        ("PURGE", getattr(engine_core, "PURGE", None), 32),
        ("seeds", SEEDS, [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]),
        ("profile", profiles.selected(), "research"),
        ("participation_cap", profiles.participation_cap(), None),
        ("BT_END_DATE", str(config.BT_END_DATE.date()), "2026-05-29"),
    ]
    for tag, u in REGISTRY.items():
        checks.append((f"purge_mode[{tag}]", u.purge_mode, "trading"))
    bad = [(n, got, want) for n, got, want in checks if got != want]
    W("    frozen configuration    " +
      ("all %d parameters match section 1" % len(checks) if not bad else "MISMATCH"))
    if bad:
        _fail("REFUSING: the frozen configuration has moved.",
              *[f"    {n}: is {got!r}, section 1 says {want!r}" for n, got, want in bad],
              "  Section 1: 'If any of it changes, the run is a new trial and this",
              "  pre-registration is void.'")

    # Section 1's own test for the cost model, run as it is written there.
    real_tc = "compute_leg_charges" in inspect.getsource(engine_core.calc_tc)
    W(f"    real charge model       {'ACTIVE' if real_tc else 'NOT ACTIVE'}"
      f"  ('compute_leg_charges' in engine_core.calc_tc)")
    if not real_tc:
        _fail("REFUSING: the real charge model is not active.",
              "  Section 1 requires it and names this exact test. The 0.11% fallback",
              "  would move every cost figure by about 9%.")
    return head


# ---------------------------------------------------------------------------
# ONE UNIVERSE: the shipping v2 run, extended at the end and nowhere else
# ---------------------------------------------------------------------------
def universe_series(u, W):
    """-> (excess_in, excess_out, detail) for one universe.

    Every line that touches the engine is results/engine_v2_final.py's own, in its
    order. The two differences are marked EXTENSION and PINNED, and there are no
    others; a third would make this a different backtest wearing the same name.
    """
    engine_core.set_tradeability(u)          # the interior-gap guard, per section 1
    src = config.require_cache(u.score_cache,
                               what=f"{u.tag} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)

    bd_in = px.index[(px.index >= config.BT_START_DATE)
                     & (px.index <= config.BT_END_DATE)]
    # EXTENSION -- the one deliberate departure. The end is the last date the
    # panel carries; the start, the calendar and the panel are untouched.
    bd_ext = px.index[(px.index >= config.BT_START_DATE)]
    held = [d for d in bd_ext if d > config.BT_END_DATE]

    # PINNED -- target_vol over the IN-SAMPLE dates. engine_v2_final computes this
    # over `bd`; using bd_ext would fit a parameter on the held-out window.
    tv = port_vol.loc[bd_in].median()

    W(f"    {u.tag:<5} in-sample window  {bd_in[0].date()} .. {bd_in[-1].date()}"
      f"   ({len(bd_in):,} sessions)   BT_END_DATE is {config.BT_END_DATE.date()}")
    if bd_in[-1] != config.BT_END_DATE:
        W(f"          (last in-sample session is {bd_in[-1].date()}, the last TRADING "
          f"day on or before BT_END_DATE)")
    W(f"    {u.tag:<5} extended window   {bd_ext[0].date()} .. {bd_ext[-1].date()}"
      f"   ({len(bd_ext):,} sessions)   held out: {len(held)}")
    W(f"    {u.tag:<5} target_vol        {tv:.6f}  PINNED to the in-sample median")

    audit = {k: [] for k in
             ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    eq, tc, n_tr, expo = backtest_exposure(
        px, op, sc, bd_ext, pc, mom20, port_vol,
        mode="breadth", target_vol=tv, rebal=cadence.selected(),
        participation_cap=profiles.participation_cap(), audit=audit)

    # ------------------------------------------------------------------
    # THE REPRODUCTION GATE. Before any held-out figure exists.
    # ------------------------------------------------------------------
    shipped = pd.read_csv(Path(u.metrics_dir) / "v2FINAL_equity.csv",
                          parse_dates=["date"]).set_index("date")["v2_invvol_breadth"]
    mine = eq.reindex(shipped.index)
    if mine.isna().any():
        _fail(f"REFUSING: the extended {u.tag} run does not cover every date the",
              "  shipped v2FINAL_equity.csv carries. The extension is not a",
              "  continuation of the published backtest.")
    rel = float((mine - shipped).abs().div(shipped.abs().clip(lower=1e-12)).max())
    W(f"    {u.tag:<5} reproduction      shipped v2FINAL_equity.csv over "
      f"{len(shipped):,} in-sample sessions:")
    W(f"          max relative difference {rel:.3e}   tolerance {REPRO_TOL:.0e}   "
      f"{'PASS' if rel <= REPRO_TOL else 'BREACH'}")
    W(f"          a breach calls _fail() and exits 1 -- it stops the run before any")
    W(f"          held-out figure is read, it does not annotate the result")
    if rel > REPRO_TOL:
        _fail(f"REFUSING: extending the date index changed the {u.tag} backtest",
              f"  BEFORE 2026-05-29 (max relative difference {rel:.3e}).",
              "  The held-out tail would be a different backtest, not a",
              "  continuation of the published one. Nothing has been spent.")

    # excess(t) = r_v2(t) - inv(t-1) * r_universe(t)       [section 2]
    r_v2 = eq.pct_change()
    r_uni = px.pct_change().mean(axis=1)              # the buy&hold series, see docstring
    summ = pd.DataFrame(audit["summary"]).set_index("date")["invested_pct"] / 100.0
    inv_lag = summ.shift(1)                            # "lagged, so the benchmark
                                                       #  cannot use the day's own exposure"
    ex = (r_v2 - inv_lag * r_uni).dropna()
    return (ex[ex.index <= config.BT_END_DATE],
            ex[ex.index > config.BT_END_DATE],
            {"tag": u.tag, "held": held, "n_trades": n_tr, "expo": expo, "tv": tv})


def main():
    lines = []
    def W(s=""):
        print(s, flush=True)
        lines.append(s)

    W("=" * 78)
    W(" HELD-OUT PRE-REGISTRATION -- THE RUN")
    W(" experiments/HELDOUT_PREREG.txt, executed once")
    W("=" * 78)
    W("")
    head = preconditions(W)
    W("")
    W("  THE EXTENSION")
    W("    score panel        NOT rebuilt, NOT refitted, read from the permanent cache")
    W("    backtest window    extended at the END only, to the last panel date")
    W("    target_vol         PINNED to the in-sample median (not recomputed)")
    W("")

    ins, outs, details = {}, {}, []
    for tag in ("nifty100", "midcap150"):
        a, b, d = universe_series(REGISTRY[tag], W)
        ins[tag], outs[tag] = a, b
        details.append(d)
    W("")

    # ------------------------------------------------------------------
    # STEP 1 -- IN-SAMPLE ONLY. Printed before any held-out number exists.
    # ------------------------------------------------------------------
    pooled_in = pd.concat([ins["nifty100"], ins["midcap150"]])
    # n IS COUNTED FROM THE DATES, NOT FROM THE HELD-OUT SERIES. Section 3 asks for
    # "the number of held-out sessions actually available", and taking it from the
    # date index rather than from len() of a computed statistic keeps STEP 1 free
    # of anything derived from a held-out VALUE. The backtest necessarily produced
    # those values -- one run yields both halves -- but nothing below STEP 1 reads
    # them until the interval above is fixed and printed.
    n = sum(len(d["held"]) for d in details)
    mu_in = float(pooled_in.mean())
    sd_in = float(pooled_in.std(ddof=1))
    se = sd_in / np.sqrt(n) if n else float("nan")
    lo, hi = mu_in - 2 * se, mu_in + 2 * se
    bps = 1e4

    W("  STEP 1 -- COMPUTED FROM SESSIONS ON OR BEFORE 2026-05-29 ONLY")
    W(f"    in-sample sessions pooled : {len(pooled_in):,} "
      f"(n100 {len(ins['nifty100']):,} + mid {len(ins['midcap150']):,})")
    W(f"    mu_in                     : {mu_in*bps:+.4f} bps/session "
      f"({mu_in*252*100:+.2f}% annualised)")
    W(f"    sd_in                     : {sd_in*bps:.4f} bps/session")
    W(f"    n  (held-out, pooled)     : {n}")
    W(f"    se = sd_in / sqrt(n)      : {se*bps:.4f} bps/session")
    W("")
    W("  STEP 2 -- THE INTERVAL, FIXED BEFORE THE HELD-OUT WINDOW IS READ")
    W(f"    [ mu_in - 2*se , mu_in + 2*se ] = [ {lo*bps:+.4f} , {hi*bps:+.4f} ] bps/session")
    W("    PASS requires the held-out pooled mean to be POSITIVE and inside it.")
    W("")

    # ------------------------------------------------------------------
    # THE POWER LOSS -- ABOVE THE VERDICT, BY REQUIREMENT
    # ------------------------------------------------------------------
    ratio = np.sqrt(PREREG_ASSUMED_N / n) if n else float("nan")
    W("  " + "!" * 74)
    W("  READ THIS BEFORE THE VERDICT")
    W("  " + "!" * 74)
    W(f"    sessions this test actually has   n = {n}")
    W(f"    sessions section 3 assumed        ~ {PREREG_ASSUMED_N}")
    W(f"    se is sd_in/sqrt(n), so it is     {ratio:.2f}x WIDER than that arithmetic")
    W(f"                                      assumed, and the interval widens with it.")
    W("")
    W("    A WIDER INTERVAL IS EASIER TO FALL INSIDE. Nothing in the procedure")
    W("    checks n against the number it was designed around; se is computed from")
    W("    whatever n turns out to be. THE VERDICT BELOW IS NOT THE TEST THIS FILE")
    W("    DESIGNED. It is that test's procedure run on a fifth of its sessions,")
    W("    because a fifth is all the data that will ever exist.")
    W("")
    for d in details:
        W(f"    {d['tag']:<5} held-out sessions {len(d['held'])}: "
          + ", ".join(str(x.date()) for x in d["held"]))
    W("  " + "!" * 74)
    W("")

    # ------------------------------------------------------------------
    # THE HELD-OUT STATISTIC -- COMPUTED ONCE
    # ------------------------------------------------------------------
    pooled_out = pd.concat([outs["nifty100"], outs["midcap150"]])
    mu_out = float(pooled_out.mean())
    positive = mu_out > 0
    inside = lo <= mu_out <= hi
    verdict = "PASS" if (positive and inside) else "FAIL"
    why = ("positive and inside the interval" if verdict == "PASS" else
           ", ".join(([] if positive else ["negative"])
                     + ([] if inside else ["outside the interval"])))

    W("  THE HELD-OUT STATISTIC")
    W(f"    pooled mean excess        : {mu_out*bps:+.4f} bps/session "
      f"({mu_out*252*100:+.2f}% annualised, for readability only)")
    W(f"    positive?                 : {positive}")
    W(f"    inside [{lo*bps:+.4f}, {hi*bps:+.4f}]? : {inside}")
    W("")
    W("=" * 78)
    W(f" VERDICT: {verdict} ON {n} POOLED SESSIONS -- {why}.")
    W(f" NOT THE TEST SECTION 3 DESIGNED, WHICH ASSUMED ~{PREREG_ASSUMED_N} SESSIONS.")
    W(f" This verdict was computed with an interval {ratio:.2f}x wider than that.")
    if verdict == "PASS":
        W(" A PASS HERE IS NOT CONFIRMATION AND MUST NOT BE QUOTED AS VALIDATION.")
        W(" Section 4: it means the in-sample picture did not fall apart immediately")
        W(" outside its window, and at 12 sessions it means less than that sentence")
        W(" was written to describe.")
    W("=" * 78)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # naming: axis-free -- this file is the record of ONE run of a pre-registration
    # that may be run exactly once, so there is no axis for its name to vary over.
    # The arm, cadence and profile are fixed by section 1 and the run refuses if any
    # of them has moved; a second name here could only mean a second run, which the
    # sentinel above forbids.
    OUT.write_text("\n".join(lines) + "\n")

    # SPENDING THE WINDOW IS RECORDED IN THE FILE THAT DEFINED IT, as section 3
    # requires -- "THE VERDICT IS RECORDED WHICHEVER WAY IT FALLS" -- and as the
    # thing that makes the second-run refusal above true.
    with PREREG.open("a") as fh:
        fh.write("\n" + "=" * 80 + "\n")
        fh.write(f" {RESULT_MARKER}, appended by heldout_prereg_run.py\n")
        fh.write("=" * 80 + "\n")
        fh.write(f" commit {head}\n")
        for l in lines[4:]:
            fh.write(" " + l + "\n" if l else "\n")
        fh.write("=" * 80 + "\n")

    print(f"\nwritten -> {OUT.relative_to(ROOT)}")
    print(f"appended -> {PREREG.relative_to(ROOT)}  (the window is now spent)")
    print("\nSTILL TO DO BY HAND: experiments/EXPERIMENTS.md, as the next numbered")
    print("entry. This script does not write it -- those entries carry the narrative")
    print("of what was expected and what it means, and a generated paragraph there")
    print("would be the only entry in the file nobody wrote.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
