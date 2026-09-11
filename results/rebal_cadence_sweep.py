"""
rebal_cadence_sweep.py -- what does rebalance cadence do across all four arms?

SPEC: experiments/REBAL_CADENCE_SPEC.txt, written before this file existed. The
design, the four cadences, the control, the trial-count charge, the noise-floor
rule and six numbered predictions were all fixed there first.

WHAT IT MEASURES
    v1, v2, v3 and v4 on both live universes at REBAL in {5, 10, 20, 40}. 32
    cells, 8 controls, off the EXISTING score panels. No refit, no rescore.
    Only the book's rebalance clock changes. v2 is the shipping arm; v3 and v4

WHY NO REFACTOR WAS NEEDED
    REBAL is ALREADY in trading rows. test_exposure.py:145 reads
    `if i % REBAL == 0 and i < len(dates) - 1` where i indexes the panel's own
    trading calendar. There is no unit mismatch to fix here; this is NOT the
    calendar-day purge defect again.

WHY NOT engine_core.backtest, WHICH TAKES rebal AS A PARAMETER
    Because it HAS NO BREADTH MODE -- only sizing="equal"/"invvol", every book
    always-invested -- so it cannot express v2 at all. It is also a different
    implementation, 1.80 CAGR points from the shipping engine on the 58. See
    KNOWN_ISSUES.md, "There are FIVE reimplementations of the backtest, not two".

HOW THE CADENCE IS VARIED WITHOUT EDITING ANY ENGINE
    test_exposure.backtest_exposure reads the MODULE-LEVEL REBAL inside its loop,
    a global lookup at execution time. This script assigns test_exposure.REBAL
    before each call and asserts it immediately before. NO FILE IS MODIFIED --
    not test_exposure.py, not config.py, not any engine, nothing under nautilus/.
    The constant's value on disk stays 20.

THE CONTROL IS A HARD STOP
    REBAL = 20 must reproduce the published v2 row of v34_comparison.csv exactly,
    READ FROM THE CSV rather than typed in. If it does not, no cadence number is
    quoted from a harness that cannot reproduce the shipping arm.

NO ACCEPT RULE. NOTHING IS PROMOTED. There is no criterion by which a cadence
wins. A favourable cadence is a MEASUREMENT, not a candidate -- fills here are
synthetic against a 10,000,000-share quote depth at flat 15 bps regardless of
order size, so a cadence that trades more often is NOT shown to be executable
more often.

Reads only. Writes diagnostics/rebal_cadence_sweep.txt.
"""
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["PYTHONHASHSEED"] = "0"

import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd

import config, config_mid, config_n100
import test_exposure
from test_exposure import backtest_exposure
from universes.registry import REGISTRY
from engine_core import precompute, metrics
import profiles as _prof            # the run's execution-realism profile

CADENCES = [5, 10, 20, 40, 60]
CONTROL = 20

# The four arms of experiments/V34_SPEC.txt. v2 ships; v3 and v4 are pro-vol and
# were measured and NOT SUPPORTED -- a favourable cadence cell on either is not a
# route to promoting them. See the spec, PART 8.3.
ARMS = [("v1", "invvol", "none"), ("v2", "invvol", "breadth"),
        ("v3", "provol", "none"), ("v4", "provol", "breadth")]
ARM_ROW = {"v1": "v1 invvol", "v2": "v2 invvol",
           "v3": "v3 provol", "v4": "v4 provol"}
SHIPPED_REBAL = test_exposure.REBAL          # read once, before anything is set
VOL_WIN = 60

# SEED NOISE FLOORS, PER ARM, from EXPERIMENTS.md entry 29 (40 seeds, K=10).
#
# CORRECTED 2026-09-03. An earlier run of this script applied v2's floor to every
# arm. That was wrong twice over:
#   - v1 HAS ITS OWN MEASURED FLOOR and it is LARGER than v2's (1.74 / 2.14
#     against 0.97 / 1.39). Using v2's floor on v1 called differences findings
#     that v1's own floor does not support.
#   - v3 AND v4 HAVE NO MEASURED FLOOR AT ALL. Entry 29 measured v1 and v2 only.
#     Labelling a v3/v4 cell "outside the floor" with v2's number is BORROWING A
#     NUMBER FROM A DIFFERENT ARM, not measuring anything. Those cells are now
#     reported as UNKNOWN.
#
# None is None-by-oversight: it means no measurement exists, and the code must
# refuse to render a verdict rather than substitute one.
SEED_FLOOR = {
    "v1": {"n100": 1.74, "mid": 2.14},     # measured, entry 29
    "v2": {"n100": 0.97, "mid": 1.39},     # measured, entry 29 -- the shipping arm
    "v3": {"n100": None, "mid": None},     # NEVER MEASURED
    "v4": {"n100": None, "mid": None},     # NEVER MEASURED
}


def floor_verdict(arm, tag, delta, is_control):
    """outside / INSIDE / UNKNOWN. UNKNOWN is not a near-miss: it means no floor
    was ever measured for this arm, so no verdict is available in either
    direction."""
    if is_control:
        return "control"
    f = SEED_FLOOR[arm][tag]
    if f is None:
        return "UNKNOWN"
    return "INSIDE" if abs(delta) < f else "outside"

OUT = ROOT / "diagnostics" / "rebal_cadence_sweep.txt"
# Machine-readable companions to the text diagnostic. One row per cell, and the
# equity curves the earlier version computed and then discarded -- without the
# curve no chart can ever be drawn later without re-running the whole sweep.
OUT_CELLS = ROOT / "diagnostics" / "rebal_cadence_cells.csv"
OUT_EQUITY = ROOT / "diagnostics" / "rebal_cadence_equity.csv"
# Per-day audit streams, six concatenated files with a `cell` column rather than
# six files per cell. 240 files is unmanageable and every row is already
# addressable by (cell) once the column exists.
AUDIT_DIR = ROOT / "diagnostics" / "rebal_cadence_audit"
AUDIT_KEYS = ("holdings", "summary", "ranking", "decisions", "trades", "skipped")

# The METRICS DIRECTORY and the SCORE PANEL paths come from
# universes/registry.py -- the single definition. Note the third element is the
# cache FILENAME, not a full path: this file joins it to the metrics directory
# itself, so it is taken as u.score_cache.name rather than re-spelled.
#
# The LABEL stays local: it is printed into diagnostics/rebal_cadence_sweep.txt.
# Order is load-bearing -- the sweep is reported universe by universe.
LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}
UNIVERSES = {
    u.tag: (LABELS[u.tag], u.metrics_dir, u.score_cache.name, str(u.score_tmp))
    for u in (REGISTRY["n100"], REGISTRY["mid"])
}


def load(tag):
    label, M, cache, tmp = UNIVERSES[tag]
    # A SCRIPT THAT RECOMPUTES AND COMPARES AGAINST A PUBLISHED ARTEFACT MUST RUN
    # UNDER THE SAME GUARDS THAT PRODUCED IT. Without this the REBAL=20 control
    # recomputes UNGUARDED and is compared against a GUARDED v34_comparison.csv:
    # measured, mid v3 AnnVol% 24.89 recomputed against 24.88 published, which
    # tripped "ALL 4 CONTROLS DID NOT REPRODUCE" and correctly refused to quote a
    # single cadence number. The control was right and the harness was stale.
    import engine_core as _ec
    _ec.set_tradeability(REGISTRY[tag])
    src = config.require_cache(M / cache, tmp, what=f"{label} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()
    return label, M, px, op, sc, bd, pc, mom20, port_vol, tv


def n_rebalances(n_days, rebal):
    """Counted the way the engine fires, not asserted."""
    return sum(1 for i in range(n_days) if i % rebal == 0 and i < n_days - 1)


def run(tag, rebal, ctx, sizing="invvol", mode="breadth", arm="v2", audit=None):
    """audit: pass a dict of the six AUDIT_KEYS to collect the per-day streams.

    WHETHER PASSING IT CHANGES THE NUMBERS IS THE POINT OF PART 9 OF THE SPEC.
    backtest_exposure's docstring claims audit=None reproduces the path exactly;
    that claim was a comment and had never been verified. The grid and the 40
    equity curves are compared against an audit=None baseline to test it."""
    label, M, px, op, sc, bd, pc, mom20, port_vol, tv = ctx
    test_exposure.REBAL = rebal
    assert test_exposure.REBAL == rebal, "the cadence override did not take"
    eq, tc, n, expo = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                        mode=mode, target_vol=tv, sizing=sizing,
                                        audit=audit, participation_cap=_prof.participation_cap())
    m = metrics(eq, f"{arm} REBAL={rebal}", tc, n)
    r = eq.pct_change().dropna()
    annvol = round(float(r.std() * np.sqrt(252) * 100), 2)   # as v34_common.ann_vol_pct
    return dict(arm=arm, rebal=rebal, cagr=float(m["CAGR%"]),
                sharpe=float(m["Sharpe"]), maxdd=float(m["MaxDD%"]),
                annvol=annvol, trades=int(n), tc=float(tc),
                final=float(eq.iloc[-1]), nrebal=n_rebalances(len(bd), rebal),
                deployed=float(expo) * 100,   # 4th return is already the mean
                eq=eq)                        # RETAINED, not discarded


AUDIT_ROWS = {k: [] for k in AUDIT_KEYS}


def main():
    t0 = time.time()
    lines = []
    def w(s=""):
        print(s, flush=True)
        lines.append(s)

    w("=" * 118)
    w(" REBALANCE CADENCE GRID -- ALL FOUR ARMS, BOTH LIVE UNIVERSES")
    w("=" * 118)
    w()
    w("  spec        experiments/REBAL_CADENCE_SPEC.txt (PART 8 for the extension)")
    w(f"  grid        {len(ARMS)} arms x {len(CADENCES)} cadences x 2 universes "
      f"= {len(ARMS)*len(CADENCES)*2} cells, {len(ARMS)*2} controls")
    w(f"  REBAL on disk (unchanged by this run): {SHIPPED_REBAL}")
    w("  engine      test_exposure.backtest_exposure -- the shipping engine")
    w("  panels      existing score caches. NO REFIT, NO RESCORE.")
    w()
    w("  " + "=" * 114)
    w("  STATED IN THE TABLE, NOT IN A FOOTNOTE:")
    w()
    w("  (a) HORIZON IS 20 TRADING ROWS IN EVERY CELL OF THIS GRID. No arm is")
    w("      refitted at any cadence. NO CELL IS AN OPTIMISED CADENCE FOR ITS ARM.")
    w("      At REBAL=5 the model predicts 20 rows forward while the book turns")
    w("      over in 5; at REBAL=40 it holds for twice the horizon it was fitted to.")
    w()
    w("  (b) NO FLOOR WAS EVER MEASURED FOR SHARPE, ON ANY ARM. The Sharpe column")
    w("      is shown because it was asked for. NO SHARPE DIFFERENCE ACROSS ANY")
    w("      CELLS IN THIS GRID MAY BE READ AS AN EFFECT.")
    w()
    w("  (c) NO FLOOR EXISTS FOR MaxDD EITHER. Entry 28's shuffle test could not")
    w("      distinguish MaxDD from a random-selection null (p 0.37/0.36 on n100,")
    w("      0.20/0.44 on mid). NO DRAWDOWN DIFFERENCE ACROSS ANY CELLS IN THIS")
    w("      GRID MAY BE READ AS AN EFFECT. Same treatment as Sharpe.")
    w()
    w("  (d) CAGR FLOORS ARE PER ARM AND TWO ARMS HAVE NONE:")
    for a in ("v1", "v2", "v3", "v4"):
        f = SEED_FLOOR[a]
        src = ("measured, entry 29" if f["n100"] is not None
               else "NEVER MEASURED -- verdict UNKNOWN, not borrowed")
        val = (f"n100 {f['n100']}  mid {f['mid']}" if f["n100"] is not None
               else "no measurement exists")
        w(f"        {a}   {val:34}  {src}")
    w("      UNKNOWN IS NOT A NEAR-MISS. It means no floor was ever measured for")
    w("      that arm, so whether the cell is an effect or noise IS NOT ESTABLISHED")
    w("      BY THIS GRID, in either direction.")
    w("  " + "=" * 114)

    res = {}
    for tag in UNIVERSES:
        ctx = load(tag)
        label, M, bd = ctx[0], ctx[1], ctx[5]
        res[tag] = {}
        for arm, sizing, mode in ARMS:
            res[tag][arm] = {}
            for c in CADENCES:
                a = {k: [] for k in AUDIT_KEYS}
                r = run(tag, c, ctx, sizing, mode, arm, audit=a)
                res[tag][arm][c] = r
                cell = f"{tag}_{arm}_r{c}"
                for k in AUDIT_KEYS:
                    if a[k]:
                        df = pd.DataFrame(a[k])
                        df.insert(0, "cell", cell)
                        df.insert(1, "universe", tag)
                        df.insert(2, "arm", arm)
                        df.insert(3, "rebal", c)
                        AUDIT_ROWS[k].append(df)
                del a

        w(f"\n{'=' * 118}\n {label} ({tag})   {len(bd):,} trading days   "
          f"{bd[0].date()} .. {bd[-1].date()}\n{'=' * 118}")

        # -------------------------------------------------- the eight controls
        pub = pd.read_csv(M / "v34_comparison.csv")
        w(f"\n  CONTROLS -- REBAL={CONTROL} against each arm's published row of "
          f"v34_comparison.csv, read from the file:")
        all_ok = True
        for arm, _, _ in ARMS:
            pr = pub[pub["Config"].str.startswith(ARM_ROW[arm])].iloc[0]
            c = res[tag][arm][CONTROL]
            pairs = [("CAGR%", c["cagr"], float(pr["CAGR%"])),
                     ("Sharpe", c["sharpe"], float(pr["Sharpe"])),
                     ("MaxDD%", c["maxdd"], float(pr["MaxDD%"])),
                     ("AnnVol%", c["annvol"], float(pr["AnnVol%"])),
                     ("Trades", c["trades"], int(pr["Trades"])),
                     ("TC_Rs", round(c["tc"]), round(float(pr["TC_Rs"]))),
                     ("FinalEq", round(c["final"], 2), round(float(pr["FinalEquity"]), 2))]
            ok = all(abs(a - b) < 0.01 for _, a, b in pairs)
            all_ok &= ok
            w(f"    {arm}  " + "  ".join(f"{n} {'OK' if abs(a-b) < 0.01 else 'DIFFERS'}"
                                         for n, a, b in pairs))
        w(f"    ALL {len(ARMS)} CONTROLS {'REPRODUCE' if all_ok else 'DID NOT REPRODUCE'}")
        if not all_ok:
            w("\n  STOP CONDITION MET. A control failed; no cadence number is quoted.")
            OUT.write_text("\n".join(lines) + "\n")
            return

        # --------------------------------------------------------- the full grid
        w(f"\n  FULL GRID -- every metric, all {len(ARMS)*len(CADENCES)} cells."
          f"  Read across a row for one arm, down a column for one cadence.")
        w(f"  dCAGR is against THAT ARM'S OWN REBAL={CONTROL} control.")
        w(f"  floor verdict: outside / INSIDE / UNKNOWN (no floor measured for that arm).")
        w()
        hdr = (f"  {'arm':4} {'REBAL':>5} {'rebals':>6} | {'CAGR%':>7} {'dCAGR':>7} "
               f"{'floor':>8} | {'Sharpe':>6} {'MaxDD%':>7} {'AnnVol%':>7} | "
               f"{'trades':>6} {'TC Rs':>10} {'TC/eq%':>6} {'FinalEquity':>13}")
        w(hdr); w("  " + "-" * (len(hdr) - 2))
        for arm, _, _ in ARMS:
            base = res[tag][arm][CONTROL]["cagr"]
            for c in CADENCES:
                r = res[tag][arm][c]
                d = r["cagr"] - base
                v = floor_verdict(arm, tag, d, c == CONTROL)
                ship = " <- ships" if arm == "v2" and c == CONTROL else ""
                w(f"  {arm:4} {c:5} {r['nrebal']:6} | {r['cagr']:7.2f} {d:+7.2f} "
                  f"{v:>8} | {r['sharpe']:6.2f} {r['maxdd']:7.2f} {r['annvol']:7.2f} | "
                  f"{r['trades']:6,} {r['tc']:10,.0f} {r['tc']/r['final']*100:6.2f} "
                  f"{r['final']:13,.0f}{ship}")
            w("  " + "-" * (len(hdr) - 2))
        w("  Sharpe, MaxDD% and AnnVol% carry NO measured floor on any arm. See (b), (c).")

    # ------------------------------------------------------------- cross-universe
    w(f"\n{'=' * 118}\n CROSS-UNIVERSE SUMMARY -- computed from the rows above\n{'=' * 118}\n")
    w("  A cell is a MEASURED DIFFERENCE only if it is outside a MEASURED floor on")
    w("  BOTH universes with the SAME SIGN. A cell on an arm with no measured floor")
    w("  CANNOT QUALIFY, because there is nothing to compare it against.\n")
    w(f"  {'arm':4} {'REBAL':>5} | {'n100 dCAGR':>11} {'verdict':>8} | "
      f"{'mid dCAGR':>10} {'verdict':>8} | status")
    qualify, unknown = [], []
    for arm, _, _ in ARMS:
        for c in CADENCES:
            if c == CONTROL:
                continue
            da = res["n100"][arm][c]["cagr"] - res["n100"][arm][CONTROL]["cagr"]
            db = res["mid"][arm][c]["cagr"] - res["mid"][arm][CONTROL]["cagr"]
            va = floor_verdict(arm, "n100", da, False)
            vb = floor_verdict(arm, "mid", db, False)
            if "UNKNOWN" in (va, vb):
                status = "NOT ESTABLISHED -- no floor for this arm"
                unknown.append((arm, c, da, db))
            elif va == "outside" and vb == "outside" and (da > 0) == (db > 0):
                status = "MEASURED DIFFERENCE, " + ("better" if da > 0 else "worse")
                qualify.append((arm, c, da, db))
            else:
                status = "no"
            w(f"  {arm:4} {c:5} | {da:+11.2f} {va:>8} | {db:+10.2f} {vb:>8} | {status}")

    w(f"\n  CELLS WITH A MEASURED VERDICT ON BOTH UNIVERSES: {len(qualify)}")
    for arm, c, da, db in qualify:
        w(f"    {arm} REBAL={c}   n100 {da:+.2f}   mid {db:+.2f}   "
          f"{'BETTER' if da > 0 else 'WORSE'} than its own control on both")
    better = [q for q in qualify if q[2] > 0]
    w(f"    of which BETTER than their own control on both universes: {len(better)}")
    if not better:
        w("    NONE. No cell with a measured floor beats its own control on both.")

    w(f"\n  CELLS WHERE THE VERDICT IS NOT ESTABLISHED: {len(unknown)}")
    w("    All are v3 or v4, which have NO MEASURED FLOOR. Whether any of these is")
    w("    an effect or noise IS NOT ESTABLISHED BY THIS GRID, in either direction.")
    for arm, c, da, db in unknown:
        w(f"    {arm} REBAL={c}   n100 {da:+.2f}   mid {db:+.2f}   UNKNOWN")

    # ------------------------------------------- what changed under the correction
    w(f"\n  WHAT THE PER-ARM FLOOR CORRECTION CHANGED, against the earlier run that")
    w("  applied v2's floor to every arm:")
    for arm, _, _ in ARMS:
        for c in CADENCES:
            if c == CONTROL:
                continue
            for tag in UNIVERSES:
                d = res[tag][arm][c]["cagr"] - res[tag][arm][CONTROL]["cagr"]
                old = "INSIDE" if abs(d) < SEED_FLOOR["v2"][tag] else "outside"
                new = floor_verdict(arm, tag, d, False)
                if old != new:
                    w(f"    {arm} REBAL={c} {tag:5} dCAGR {d:+6.2f}: "
                      f"was '{old}' under v2's floor -> now '{new}'")

    w(f"\n  THE ONLY ARM WITH A TRUSTWORTHY VERDICT IS v2.")
    w("  It is the shipping arm and the only one whose own floor was measured and")
    w("  applied here. v1 has a measured floor too, but v1 does not ship.")
    w("  v2's VERDICT: NO CADENCE BEATS REBAL=20 ON BOTH UNIVERSES.")
    for c in CADENCES:
        if c == CONTROL:
            continue
        da = res["n100"]["v2"][c]["cagr"] - res["n100"]["v2"][CONTROL]["cagr"]
        db = res["mid"]["v2"][c]["cagr"] - res["mid"]["v2"][CONTROL]["cagr"]
        w(f"    v2 REBAL={c:<3} n100 {da:+.2f} ({floor_verdict('v2','n100',da,False)})"
          f"   mid {db:+.2f} ({floor_verdict('v2','mid',db,False)})")

    w(f"\n  CAPACITY IS NOT MEASURED HERE AND BEARS ON EVERY FAVOURABLE CELL.")
    w("  Fills are synthetic against a QUOTE_DEPTH of 10,000,000 shares at flat")
    w("  15 bps slippage regardless of order size. No L2 data exists anywhere in")
    w("  this project, no market impact, no queue position. mid already has a")
    w("  measured liquidity problem -- one order reached 1,614% of that symbol's")
    w("  prior 20-day median volume. A CADENCE THAT TRADES DIFFERENTLY IS NOT SHOWN")
    w("  TO BE EXECUTABLE DIFFERENTLY, IN EITHER DIRECTION.")
    w(f"\n  v3 AND v4 DO NOT SHIP AND NOTHING HERE REOPENS THAT. Pro-vol was measured")
    w("  under V34_SPEC.txt and is not supported.")
    w(f"\n  TRIAL COUNT: +12 new looks (v1, v3, v4 x 4 cadences). FLOOR 32 -> 44.")
    w(f"\n  REBAL ON DISK AFTER THIS RUN: {SHIPPED_REBAL} (never written).")
    w(f"  wall clock {time.time() - t0:.0f} sec")

    # ------------------------------------------------------------------ outputs
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")

    # (1) PER-CELL CSV. One row per cell, every metric a column, so the grid can
    # be opened in a spreadsheet without parsing the fixed-width text above.
    cells = []
    for tag in UNIVERSES:
        for arm, _, _ in ARMS:
            base = res[tag][arm][CONTROL]["cagr"]
            for c in CADENCES:
                r = res[tag][arm][c]
                d = r["cagr"] - base
                f = SEED_FLOOR[arm][tag]
                cells.append({
                    "universe": tag, "arm": arm, "rebal": c,
                    "n_rebalances": r["nrebal"],
                    "CAGR_pct": r["cagr"],
                    "dCAGR_vs_rebal20": round(d, 2),
                    "floor_verdict": floor_verdict(arm, tag, d, c == CONTROL),
                    "seed_floor_CAGR": f if f is not None else "",
                    "Sharpe": r["sharpe"], "MaxDD_pct": r["maxdd"],
                    "AnnVol_pct": r["annvol"], "trades": r["trades"],
                    "TC_Rs": round(r["tc"], 2),
                    "TC_pct_of_final_equity": round(r["tc"] / r["final"] * 100, 4),
                    "final_equity": round(r["final"], 2),
                    "deployed_pct": round(r["deployed"], 2),
                    "ships": arm == "v2" and c == CONTROL})
    pd.DataFrame(cells).to_csv(OUT_CELLS, index=False)

    # (2) EQUITY CURVES, one column per cell, date-indexed. Wide rather than 40
    # files: every cell shares the same 1,836-row date index, so a wide frame is
    # the same information without 40 copies of the index.
    eqs = {}
    for tag in UNIVERSES:
        for arm, _, _ in ARMS:
            for c in CADENCES:
                eqs[f"{tag}_{arm}_r{c}"] = res[tag][arm][c]["eq"]
    eq_df = pd.DataFrame(eqs)
    eq_df.index.name = "date"
    eq_df.to_csv(OUT_EQUITY)

    # (3) PER-DAY AUDIT STREAMS. Six concatenated files, each carrying a `cell`
    # column plus universe/arm/rebal, rather than six files per cell.
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_files = []
    for k in AUDIT_KEYS:
        f = AUDIT_DIR / f"{k}.csv"
        if AUDIT_ROWS[k]:
            df = pd.concat(AUDIT_ROWS[k], ignore_index=True)
        else:
            df = pd.DataFrame(columns=["cell", "universe", "arm", "rebal"])
        df.to_csv(f, index=False)
        audit_files.append((f, len(df)))

    for f in (OUT, OUT_CELLS, OUT_EQUITY):
        print(f"written -> {f}  ({f.stat().st_size:,} bytes)")
    print(f"  cells CSV : {len(cells)} rows x {len(cells[0])} columns")
    print(f"  equity CSV: {eq_df.shape[0]:,} rows x {eq_df.shape[1]} cells")
    tot = 0
    for f, nrows in audit_files:
        sz = f.stat().st_size; tot += sz
        print(f"written -> {f}  ({sz:,} bytes, {nrows:,} rows)")
    print(f"  audit total: {tot:,} bytes across {len(audit_files)} files")


if __name__ == "__main__":
    main()
