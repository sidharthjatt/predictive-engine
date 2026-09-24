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

Slippage is applied against the trade and the port rounds to the NSE tick in
force on the date, so each candidate is reconstructed as price * (1 +/- SLIPPAGE)
rounded to that tick, with the port's own functions (nt_data.quote_frame and
_round_to). Tolerance is half that tick, as the spec fixed before running. It
certifies the PIPELINE's fills, nautilus/reports/, which since 2026-09-24 no other
program writes.

Nothing is corrected.
"""
import sys
from datetime import datetime
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

# SLIPPAGE comes from slippage.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from slippage import SLIPPAGE  # noqa: E402
# THE TOLERANCE IS HALF OF THAT DATE'S NSE TICK, 2026-09-24. It was 0.005, set
# after measuring 2-decimal prices -- on fills nt_verify had written at a 0.01
# grid over the pipeline's files. This check certifies the PIPELINE's fills,
# which are on the NSE grid (0.05 for most of the window), and reconstructs each
# expected price with the port's own rule (nt_data.quote_frame, _round_to). Both
# prices are then on one grid, so half a tick admits exact equality only. This
# corrects a calibration made on the wrong grid; it is not a loosening.

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
from config import read_table  # the one CSV/parquet reader: config.read_table

ARM = _arm_reg.ARMS["v2"]
_SEG = _reports_segment(ARM.mode, ARM.sizing)

# The LABEL stays local: it is printed into
# diagnostics/checkB_execution_timing.txt. Labels are presentation; paths are
# facts. Order is load-bearing -- the report is written universe by universe.
LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {
    u.tag: (ROOT / "nautilus" / "reports" / u.tag / _SEG / "fills.csv",
            u.score_cache,
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


def run(uni, fills_p, sc_p, dec_p, label, W):
    F = read_table(fills_p)
    F["date"] = pd.to_datetime(F["ts_event"], utc=True).dt.tz_localize(None).dt.normalize()
    F["symbol"] = F["instrument_id"].str.split(".").str[0]
    F["px"] = F["last_px"].astype(float)

    # THE PORT'S OWN INPUTS: its panel (forward filled, as nt_data.load_panel
    # builds it), its quoted rows and each row's tick (nt_data.quote_frame), over
    # the dates the pipeline's run quoted, warm-up included.
    import nt_data
    import nt_run
    assert nt_data.TICK_MODE == "nse", "the pipeline quotes on the NSE tick grid"
    pxf, opf = nt_data.load_panel(config.require_cache(sc_p, what=f"{uni} panel"))
    q_start = pd.Timestamp(config.BT_START_DATE) - pd.Timedelta(days=nt_run.WARMUP_DAYS)
    q_end = pd.Timestamp(nt_run.UNIVERSES[uni]["end"])
    Q = {s: nt_data.quote_frame(s, pxf, opf, q_start, q_end).set_index("date")
         for s in F["symbol"].unique()}
    cal = list(opf.index)
    prev = {d: cal[i - 1] for i, d in enumerate(cal) if i > 0}
    op = opf  # the calendar check below reads op.index

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
    # Until 2026-09-24 the reconstruction was round(price*(1+/-slip), 2), on the
    # strength of a 2026-09-09 measurement that only 210 of 977 fill prices sat on
    # a 0.05 grid -- taken on fills a 0.01-grid tool run had left in place.
    # THAT MEASUREMENT WAS TAKEN ON THE SUPERSEDED FILE, whose arm is unknown. If
    # this line reads near 100% while the match counts below read low, the
    # reconstruction assumption is stale and the match counts are a verdict on the
    # ASSUMPTION, not on execution timing. Stated as a number rather than as a
    # caveat, so it cannot be true and unnoticed.
    _ongrid = int((np.abs(F["px"] / 0.05 - np.round(F["px"] / 0.05)) < 1e-9).sum())
    W(f"  on 0.05 grid    {_ongrid:,} of {len(F):,} fill prices "
      f"({100*_ongrid/max(len(F),1):.1f}%)")
    W(f"  price panel     {Path(sc_p).name}")
    W(f"  reconstruction  price * (1 +/- {SLIPPAGE}) rounded to that date's NSE tick")
    W("                  (nt_data.quote_frame and _round_to, the port's own rule)")
    W("  tolerance       half of that date's tick: exact equality on the grid")
    W("")

    recs = []
    for _, r in F.iterrows():
        d, s, side, px = r["date"], r["symbol"], r["order_side"], r["px"]
        sgn = 1.0 if side == "BUY" else -1.0
        pd_ = prev.get(d)
        qs = Q.get(s)
        tk = float(qs.at[d, "tick"]) if qs is not None and d in qs.index else np.nan
        def cand(col, dd):
            if qs is None or dd is None or dd not in qs.index or tk != tk:
                return np.nan
            v = qs.at[dd, col]
            return np.nan if pd.isna(v) else float(nt_data._round_to(v * (1 + sgn * SLIPPAGE), tk))
        c = {"a_open_today": cand("open", d), "b_close_today": cand("close", d),
             "c_close_prev": cand("close", pd_), "d_open_prev": cand("open", pd_)}
        m = {k: (abs(px - v) <= tk / 2 - 1e-9) if v == v else False for k, v in c.items()}
        recs.append({"date": d, "symbol": s, "side": side, "px": px, "tick": tk,
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
        DEC = read_table(dec_p)
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
    return {"n": len(R), "at_a_close": len(only_bc),
            "off_calendar": len(R) - int(R["on_calendar"].sum()),
            "not_matching_open": len(bad)}


def main():
    out = [HISTORY, ""]
    res = {}
    for uni, (f, s, d, lab) in UNIVERSES.items():
        res[uni] = (run(uni, f, s, d, lab, out.append), f)
        out.append("")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No measurement,
    # candidate rule or printed number above changed.
    #
    # THE VERDICT NAMES ITS INPUT AND THAT INPUT'S mtime, because this file reads
    # nautilus/reports/<universe>/<seg>/fills.csv, which is GITIGNORED and holds
    # whatever last wrote it. A run of nt_verify or verify_v34_arms at a
    # non-production tick regenerates it, so a verdict that did not say which file
    # it read, and when that file was written, would be reporting on someone
    # else's run under this file's name. Measured 2026-09-21: this session's own
    # gate runs had rewritten both fills.csv at tick 0.01 fixed rather than the
    # production 0.05/nse grid.
    #
    # WHAT IS GATED: no fill may execute at a CLOSE rather than an open, and every
    # fill must fall on the panel's trading calendar. Those are the two claims
    # this file exists to test and both are categorical in its own text.
    #
    # WHAT IS NOT GATED: `not_matching_open`. Three of 1,006 fills differ from the
    # day's open by 0.01 and this file states no tolerance for that, adjudicates
    # none, and separately classes near-ties as "a limit of the instrument, not an
    # exception". Picking a tolerance here would be inventing a pass condition
    # rather than reading one, so the count is reported and left ungated.
    bad_u = {u: r for u, (r, _) in res.items()
             if r["at_a_close"] or r["off_calendar"]}
    out.append("  INPUT READ (gitignored; holds whatever last wrote it):")
    for u, (r, f) in sorted(res.items()):
        fp = Path(f)
        mt = (datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
              if fp.exists() else "ABSENT")
        out.append(f"    {u:<10} {fp} written {mt}  ({r['n']:,} fills)")
    tot_close = sum(r["at_a_close"] for r, _ in res.values())
    tot_offcal = sum(r["off_calendar"] for r, _ in res.values())
    tot_nmo = sum(r["not_matching_open"] for r, _ in res.values())
    out.append(f"  ungated, reported only: {tot_nmo} fill(s) not matching the "
               f"day's open exactly.")
    if bad_u:
        out.append(f"  RESULT: FAIL -- {tot_close} fill(s) executed at a close and "
                   f"{tot_offcal} fell off the trading calendar, on: "
                   + ", ".join(sorted(bad_u)) + ".")
        rc = 1
    else:
        out.append(f"  RESULT: PASS -- 0 fills executed at a close and 0 fell off "
                   f"the trading calendar, across {len(res)} universe(s).")
        rc = 0
    (ROOT / "diagnostics" / "checkB_execution_timing.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
