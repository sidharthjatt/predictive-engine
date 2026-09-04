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

import numpy as np
import pandas as pd
import config, config_mid, config_n100

SLIPPAGE = 0.0015
TICK = 0.05
TOL = 0.005    # 2-decimal storage; see tick() -- STRICTER than the spec's half-tick

UNIVERSES = {
    "n100": (ROOT / "nautilus" / "reports" / "n100" / "fills.csv",
             config_n100.METRICS_DIR_N100 / "v_n100_expanding_cache.csv",
             "/tmp/v_n100_expanding.csv",
             config_n100.METRICS_DIR_N100 / "daily_decisions_n100.csv", "NIFTY 100"),
    "mid": (ROOT / "nautilus" / "reports" / "mid" / "fills.csv",
            config_mid.METRICS_DIR_MID / "v_mid_expanding_cache.csv",
            "/tmp/v_mid_expanding.csv",
            config_mid.METRICS_DIR_MID / "daily_decisions_mid.csv", "MIDCAP150"),
}


def tick(x):
    """Reconstruct the fill price as the port stores it.

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
    W(f"  fills recorded  {len(F):,}")
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
    out = []
    for uni, (f, s, st, d, lab) in UNIVERSES.items():
        run(uni, f, s, st, d, lab, out.append)
        out.append("")
    (ROOT / "diagnostics" / "checkB_execution_timing.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
