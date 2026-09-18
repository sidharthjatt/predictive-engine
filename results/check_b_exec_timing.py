"""
check_b_exec_timing.py -- CHECK B of experiments/DATA_EXEC_SPEC.txt.

Did every Nautilus fill execute at the NEXT session's open, as the design claims?

The claim -- signal at the close of day t, fill at the open of day t+1 -- is
stated in HANDOFF_SUMMARY and was asserted as a hardcoded PASS in engine_core's
leakage checklist until 2026-08-29. NOTHING HAS EVER VERIFIED IT AGAINST THE FILL
RECORD. This does.

THE FILL PRICE IS THE INSTRUMENT. Each fill is tested against FOUR candidates,
not one, so that "matches the open" can be distinguished from "matches everything
because the tolerance is loose":
    (a) that day's OPEN            -- the design
    (b) that day's CLOSE           -- same-day close execution
    (c) the PREVIOUS session's CLOSE -- signal-day close execution
    (d) the PREVIOUS session's OPEN

Slippage is applied against the trade and the port rounds to a 0.05 tick grid, so
each candidate is reconstructed as tick(price * (1 +/- SLIPPAGE)). Tolerance is
half a tick, 0.025, fixed in the spec before running.

Nothing is corrected.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))
# nautilus/ TOO, because the fills path comes from nt_run.reports_segment --
# the writer's own rule rather than a second copy of it. See the block below.
sys.path.insert(0, str(ROOT / "nautilus"))

import numpy as np
import pandas as pd
import config
from universes.registry import REGISTRY
import paths

SLIPPAGE = 0.0015
TICK = 0.05
TOL = 0.005    # 2-decimal storage; see tick() -- STRICTER than the spec's half-tick

# ---------------------------------------------------------------------------
# WHICH FILL RECORD THIS READS, AND WHY IT HAS TO SAY SO
# ---------------------------------------------------------------------------
# THIS READ A PATH NOTHING HAD WRITTEN FOR ELEVEN DAYS. It asked for
# `nautilus/reports/<universe>/fills.csv`, and the port stopped writing that at
# 8568b78 (2026-09-05 02:33), which added an arm segment. The previous diagnostic
# was committed at 13:34 THE SAME DAY, from a leftover file that nothing was
# writing any more -- the warm-tree failure, in its purest form: it passed because
# the old file had not been cleaned up. Once it was, this died with
# FileNotFoundError, loudly, and nobody noticed because nobody ran it.
#
# WORSE THAN THE PATH: THE OLD FILE HAD NO ARM. One shared fills.csv per universe
# held whichever arm ran LAST, unlabelled, so the finding could not be attributed
# to anything. That is what this block fixes -- not just where to read, but the
# record of WHAT was read.
#
# THE SEGMENT COMES FROM THE WRITER'S OWN DEFINITION. nt_run.reports_segment() is
# what builds the directory the port writes into, carrying arm, cadence and
# profile; re-spelling that rule here would be a second definition that can
# disagree with the first, which is how the path went stale the first time.
# Importing nt_run costs about 1.4 s and pulls nautilus_trader; that is the price
# of having one rule instead of two, and this is a hand-run probe.
#
# ONE ARM, DECLARED. v2 is the SHIPPING arm -- breadth-scaled inverse-vol, the
# strategy every published figure comes from -- so it is the one whose execution
# timing is worth checking. v1, v3 and v4 sit at sibling paths and are not read.
# The arm is printed in the report header, because "whichever ran last" is exactly
# what made the old numbers unusable.
import arms.registry as _arm_reg
from nt_run import reports_segment as _reports_segment

ARM = _arm_reg.ARMS["v2"]
_SEG = _reports_segment(ARM.mode, ARM.sizing)

# The LABEL stays local: it is printed into
# diagnostics/checkB_execution_timing.txt. Labels are presentation; paths are
# facts. Order is load-bearing -- the report is written universe by universe.
LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {
    u.tag: (ROOT / "nautilus" / "reports" / u.tag / _SEG / "fills.csv",
            u.score_cache,
            str(u.score_tmp),
            paths.tagged_artefact(u, "daily_decisions"),
            LABELS[u.tag])
    for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])
}


# ---------------------------------------------------------------------------
# THE RECORD OF WHAT THE PORT DID UNDER THE OLD LAYOUT, CARRIED INTO EVERY RERUN
# ---------------------------------------------------------------------------
# A HEADER ADDED TO THE FILE BY HAND WOULD BE ERASED BY THE NEXT RUN. The previous
# diagnostic was marked stale in place on 2026-09-16, and that marking only
# survives if the probe itself emits it. So it does. The old finding is not
# withdrawn: it measured the port's execution semantics, which is not a fact about
# where its reports live.
HISTORY = """\
--------------------------------------------------------------------------------
 SUPERSEDED MEASUREMENT, KEPT AS THE RECORD OF WHAT THE PORT DID BEFORE 2026-09-05
--------------------------------------------------------------------------------
  The version of this diagnostic committed at 40b938e read
      nautilus/reports/<universe>/fills.csv
  and found, on n100, 977 of 978 fills reconstructing as that day's OPEN to
  within 0.005, with one exception (CHOLAFIN, 2020-05-22) and zero fills
  executing at a close.

  THAT FILE'S ARM IS UNKNOWN. Under the old layout one shared fills.csv per
  universe held whichever arm ran LAST, unlabelled, so the 978 fills cannot be
  attributed to a strategy. Read it as a property of the port, not of an arm.

  The port stopped writing that path at 8568b78, 2026-09-05 02:33. The
  superseded diagnostic was committed eleven hours later, from a file nothing
  was writing any more.
--------------------------------------------------------------------------------
"""


def tick(x):
    """Reconstruct the fill price as the port stores it.

    THE MEASUREMENT BELOW WAS TAKEN ON AN ORPHANED FILE, and what that is worth
    is recorded next to the spec it departs from -- experiments/DATA_EXEC_SPEC.txt,
    "ADDENDUM 2026-09-16". Read that before changing anything here: the 977 fills
    came from a path the port had already stopped writing, holding whichever arm
    ran last. Today's fills are 95.9% on the 0.05 grid, which is what the spec
    says and what this function does not assume.

    CORRECTED AFTER THE FIRST RUN, and the original is named rather than
    silently replaced. The spec assumed the port rounds the fill price to the
    0.05 tick grid, because nt_verify.py passes tick_round=True. Measured: only
    210 of 977 fill prices lie on a 0.05 grid, and the un-rounded
    open*(1+/-slip) matches every fill to within EXACTLY 0.005 -- the signature
    of 2-decimal storage, not tick rounding. tick_round governs the reference
    arm's SIZING, not the recorded fill price.

    So the reconstruction is open*(1+/-slip) rounded to 2 decimals, and the
    tolerance drops from half a tick to 0.005 accordingly. THE TOLERANCE WAS
    TIGHTENED, NOT WIDENED: the corrected test is stricter than the spec's.
    """
    return np.round(np.asarray(x, dtype=float), 2)


def run(uni, fills_p, sc_p, sc_tmp, dec_p, label, W):
    F = pd.read_csv(fills_p)
    F["date"] = pd.to_datetime(F["ts_event"], utc=True).dt.tz_localize(None).dt.normalize()
    F["symbol"] = F["instrument_id"].str.split(".").str[0]
    F["px"] = F["last_px"].astype(float)

    P = pd.read_csv(config.require_cache(sc_p, sc_tmp, what=f"{uni} panel"),
                    parse_dates=["date"])
    op = P.pivot_table(index="date", columns="symbol", values="open")
    cl = P.pivot_table(index="date", columns="symbol", values="close")
    cal = list(op.index)
    prev = {d: cal[i - 1] for i, d in enumerate(cal) if i > 0}

    W("=" * 100)
    W(f" CHECK B -- EXECUTION TIMING FROM THE FILL RECORD -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  fills file      {fills_p.relative_to(ROOT)}")
    # THE ARM IS NAMED, AND THAT IS THE POINT OF THE REPOINT. The superseded
    # version of this file read a shared fills.csv holding whichever arm ran last,
    # so its 978 fills belonged to nothing in particular.
    W(f"  arm             {ARM.name} -- {ARM.label}   (segment '{_SEG}',")
    W(f"                  from nt_run.reports_segment, the writer's own rule)")
    W(f"  fills recorded  {len(F):,}")
    # HOW MANY FILL PRICES LIE ON THE 0.05 TICK GRID -- MEASURED, ALWAYS PRINTED.
    # tick() below reconstructs as round(price*(1+/-slip), 2), on the strength of a
    # 2026-09-09 measurement that only 210 of 977 fill prices sat on a 0.05 grid.
    # THAT MEASUREMENT WAS TAKEN ON THE SUPERSEDED FILE, whose arm is unknown. If
    # this line reads near 100% while the match counts below read low, the
    # reconstruction assumption is stale and the match counts are a verdict on the
    # ASSUMPTION, not on execution timing. Stated as a number rather than as a
    # caveat, so it cannot be true and unnoticed.
    _ongrid = int((np.abs(F["px"] / 0.05 - np.round(F["px"] / 0.05)) < 1e-9).sum())
    W(f"  on 0.05 grid    {_ongrid:,} of {len(F):,} fill prices "
      f"({100*_ongrid/max(len(F),1):.1f}%)")
    W(f"  price panel     {Path(sc_p).name}")
    W(f"  reconstruction  round(price * (1 +/- {SLIPPAGE}), 2)  -- 2-decimal storage")
    W(f"  tolerance       {TOL} -- TIGHTENED from the spec's half-tick 0.025;")
    W("                  see tick() for why the spec's assumption was wrong")
    W("")

    recs = []
    for _, r in F.iterrows():
        d, s, side, px = r["date"], r["symbol"], r["order_side"], r["px"]
        sgn = 1.0 if side == "BUY" else -1.0
        pd_ = prev.get(d)
        def cand(frame, dd):
            if dd is None or dd not in frame.index or s not in frame.columns:
                return np.nan
            v = frame.at[dd, s]
            return np.nan if pd.isna(v) else float(tick(v * (1 + sgn * SLIPPAGE)))
        c = {"a_open_today": cand(op, d), "b_close_today": cand(cl, d),
             "c_close_prev": cand(cl, pd_), "d_open_prev": cand(op, pd_)}
        m = {k: (abs(px - v) <= TOL) if v == v else False for k, v in c.items()}
        recs.append({"date": d, "symbol": s, "side": side, "px": px,
                     "on_calendar": d in op.index, **c,
                     **{f"m_{k}": v for k, v in m.items()},
                     "n_match": sum(m.values())})
    R = pd.DataFrame(recs)

    W("  MATCHES, PER CANDIDATE (a fill may match more than one)")
    for k, lab in (("a_open_today", "(a) that day's OPEN      -- the design"),
                   ("b_close_today", "(b) that day's CLOSE     -- same-day close"),
                   ("c_close_prev", "(c) previous CLOSE       -- signal-day close"),
                   ("d_open_prev", "(d) previous OPEN")):
        W(f"    {lab:<45} {int(R[f'm_{k}'].sum()):>5} of {len(R):,}")
    W("")
    W(f"  fills matching (a): {int(R['m_a_open_today'].sum()):,} of {len(R):,}")
    W(f"  fills matching NOTHING: {int((R['n_match'] == 0).sum()):,}")
    W(f"  fills matching (a) UNIQUELY: {int((R['m_a_open_today'] & (R['n_match'] == 1)).sum()):,}")
    amb = R[R["m_a_open_today"] & (R["n_match"] > 1)]
    W(f"  fills matching (a) AND another candidate (ambiguous, prices within half a")
    W(f"    tick of each other -- a limit of the instrument, not an exception): {len(amb):,}")
    W("")

    bad = R[~R["m_a_open_today"]]
    W(f"  EXCEPTIONS -- fills NOT matching the fill day's open: {len(bad):,}")
    if len(bad):
        W(f"    {'date':<12}{'symbol':<14}{'side':<6}{'fill px':>10}"
          f"{'(a) open':>10}{'(b) close':>11}{'(c) prevC':>11}{'(d) prevO':>11}")
        for _, r in bad.iterrows():
            W(f"    {str(r['date'].date()):<12}{r['symbol']:<14}{r['side']:<6}"
              f"{r['px']:>10.2f}{r['a_open_today']:>10.2f}{r['b_close_today']:>11.2f}"
              f"{r['c_close_prev']:>11.2f}{r['d_open_prev']:>11.2f}")
    W("")

    only_bc = R[(~R["m_a_open_today"]) & (R["m_b_close_today"] | R["m_c_close_prev"])]
    W(f"  FILLS EXECUTING AT A CLOSE RATHER THAN AN OPEN: {len(only_bc):,}")
    W("")
    W(f"  every fill date on the panel's trading calendar: "
      f"{int(R['on_calendar'].sum()):,} of {len(R):,}")

    if Path(dec_p).exists():
        DEC = pd.read_csv(dec_p)
        # column name verified from the file, not assumed
        cands = [c for c in DEC.columns if "date" in c.lower() or "decid" in c.lower()]
        if not cands:
            raise SystemExit(f"{dec_p}: no date-like column. present: {list(DEC.columns)}")
        dcol = cands[0]
        dec_days = set(pd.to_datetime(DEC[dcol]).dt.normalize())
        nxt = {prev[d] : d for d in prev}
        ok = sum(1 for d in R["date"] if prev.get(d) in dec_days)
        W(f"  fills whose PREVIOUS session is a recorded decision date: "
          f"{ok:,} of {len(R):,}")
    else:
        W(f"  decision file {Path(dec_p).name} absent -- the 'right open' check")
        W("  could not be run, only the 'an open' check above.")
    W("")


def main():
    out = [HISTORY, ""]
    for uni, (f, s, st, d, lab) in UNIVERSES.items():
        run(uni, f, s, st, d, lab, out.append)
        out.append("")
    (ROOT / "diagnostics" / "checkB_execution_timing.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
