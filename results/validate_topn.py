"""
validate_topn.py -- does the incumbent TOP_N=8 still hold on the live universes?

SPEC: experiments/TOPN_SPEC.txt Part B, written before this file existed.
This is a VALIDATION, not a search. Two arms, no sweep, nothing promoted.

THE CONTRAST
    TOP_N=8 (incumbent) against TOP_N=12 (the value it beat in EXPERIMENTS.md
    entry 10, the single acceptance in twenty-five trials). BUFFER is PINNED at
    16 in BOTH arms so only the size of the buy set moves.

    The pin handicaps the challenger on turnover: 8/16 leaves an eight-rank
    hysteresis band, 12/16 leaves four. That is a stated limit of the test, not a
    defect, and turnover is reported for both arms so its size is visible.

THE VERDICT RULE, FIXED IN THE SPEC BEFORE ANY NUMBER EXISTED
    A: Sharpe(8) >= Sharpe(12) on n100, full period
    B: Sharpe(8) >= Sharpe(12) on mid,  full period
    C: Sharpe(8) >= Sharpe(12) in BOTH halves of BOTH universes
    All three must hold. Ties hold for the incumbent, deliberately: the burden is
    on the challenger, which is the direction entry 10 imposed on 8 when 8 was
    the challenger. MaxDD, CAGR, volatility and turnover are REPORTED, NOT GATED.

THE OUTCOME HAS TWO HALVES AND THEY ARE REPORTED TOGETHER, ALWAYS
    A reader who takes only the first sentence must not be able to do so
    honestly, so this file never prints one without the other:

      1. TOP_N=8 is NOT CONTRADICTED on its pre-registered rule.
      2. In the SAME measurement TOP_N=12 had the shallower MaxDD in BOTH
         universes, on a dimension the rule does not gate.

    The second half is NOT a claim that 12 is better: its Sharpe is lower in
    every period and its turnover is far higher. And no drawdown criterion was
    pre-registered, so nothing here is a result about drawdown -- it is an
    ungated observation, recorded because the rule cannot see it.

    NO DRAWDOWN CRITERION IS ADDED. Adding one now would be fitting the rule to
    the data, which is exactly what documenting the Sharpe-only asymmetry rather
    than fixing it was meant to avoid.

THE OUTCOME WORD IS "NOT CONTRADICTED" OR "CONTRADICTED". NEVER "RE-EARNED".
    Entry 10 accepted 8 against 12 on the retired 58 and 74. The record does not
    state what BUFFER the 12-arm ran at -- searched across EXPERIMENTS.md, the
    pre-registrations, rejected_experiments_REPORT.txt, git history and every
    surviving script, all negative. So this cannot be shown to be entry 10's
    contrast, and a pass cannot re-earn that acceptance. See the spec.

WHICH ENGINE, AND WHY IT MATTERS
    test_exposure.backtest_exposure -- the SHIPPING engine, the same side of the
    split as validate_breadth_live.py. Per KNOWN_ISSUES.md the two engines sit
    1.80 CAGR points apart on the 58, so a TOP_N result measured on
    engine_core.backtest would not cover production.

CACHES
    This suite WRITES NO CACHE. TOP_N changes selection, not scoring, so both arms
    read the one production score panel. It is not trusted by path: the universe
    and the panel shape are asserted FROM THE FILE, and both arms are proven to
    have read an identical panel before any number is reported.

SUB-PERIODS ARE RE-RUN, NOT SLICED
    Each half is a fresh backtest over the half's dates, intersected with the
    backtest window -- the validate_sizing.py form, matching how the breadth
    suite's T2 measures its halves "independently". v34_common.sub_rows() slices
    the full curve instead, which carries the boundary portfolio into the second
    half. The two answer different questions and this file states which it asks.

English only. No verdict string is hardcoded; every criterion outcome is computed
from the run that prints it.
"""
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd

import config
import config_mid
import config_n100
from engine_core import precompute
import test_exposure
from test_exposure import backtest_exposure
from universes.registry import REGISTRY
from v34_common import arm_row, held_and_skips, _git_state

VOL_WIN = 60
BUFFER_PINNED = 16
INCUMBENT, CHALLENGER = 8, 12
HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]

# PATHS AND SYMBOLS COME FROM universes/registry.py -- the single definition.
# The LABEL stays local: this file's spelling is printed into
# diagnostics/topn_verdict.txt, which is committed and cited by EXPERIMENTS.md,
# and the sibling scripts spell the same two universes two other ways. Labels are
# presentation; paths are facts.
#
# Order is load-bearing: run_universe() is called per universe in this order and
# the combined verdict accumulates in that sequence.
LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}
UNIVERSES = {
    u.tag: {"perm": u.score_cache, "tmp": str(u.score_tmp),
            "metrics_dir": u.metrics_dir, "symbols": u.symbols,
            "label": LABELS[u.tag]}
    for u in (REGISTRY["n100"], REGISTRY["mid"])
}


def load_panel(cfg, uni):
    """Read the production score panel and PROVE which universe it is.

    The path is not taken as evidence. A wrong-universe panel loaded silently is
    the failure BREADTH_LIVE_SPEC.txt calls the most dangerous part of that port,
    and it produces a verdict for the wrong universe with no error at all.
    """
    src = config.require_cache(cfg["perm"], cfg["tmp"], what=f"{uni} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    got, want = set(p["symbol"].unique()), cfg["symbols"]()
    if got != want:
        raise SystemExit(
            f"{uni}: score panel symbol set does not match the universe.\n"
            f"  source        : {src}\n"
            f"  panel symbols : {len(got)}\n"
            f"  universe      : {len(want)}\n"
            f"  only in panel : {sorted(got - want)[:10]}\n"
            f"  only in config: {sorted(want - got)[:10]}\n"
            f"  Refusing to report a verdict for a universe this panel may not be.")
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return src, px, op, sc


def panel_fingerprint(px, op, sc):
    """A value that changes if either arm were handed a different panel."""
    import hashlib
    h = hashlib.sha256()
    for frame in (px, op, sc):
        h.update(np.ascontiguousarray(
            np.nan_to_num(frame.to_numpy(dtype=np.float64), nan=-1.0)).tobytes())
        h.update(",".join(map(str, frame.columns)).encode())
    return h.hexdigest()


def run_arm(top_n, px, op, sc, dates, pc, mom20, port_vol, tv, label):
    """One arm over one date range. BUFFER is pinned for every call."""
    test_exposure.TOP_N = top_n
    test_exposure.BUFFER = BUFFER_PINNED
    audit = {k: [] for k in
             ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    eq, tc, ntr, expo = backtest_exposure(px, op, sc, dates, pc, mom20, port_vol,
                                          mode="breadth", target_vol=tv,
                                          audit=audit)
    # backtest_exposure returns the MEAN exposure already, as a scalar.
    dep = float(expo) * 100
    row = arm_row(eq, label, tc, ntr, dep)
    mh, nsk = held_and_skips(audit)
    row["MeanNamesHeld"] = round(mh, 2) if mh == mh else ""
    row["CashShortSkips"] = nsk
    row["TOP_N"] = top_n
    row["BUFFER"] = BUFFER_PINNED
    n_rb = len(pd.DataFrame(audit["decisions"])) if audit["decisions"] else 0
    row["Rebalances"] = n_rb
    row["TradesPerRebal"] = round(ntr / n_rb, 2) if n_rb else float("nan")
    years = (dates[-1] - dates[0]).days / 365.25
    row["TradesPerYear"] = round(ntr / years, 1) if years > 0 else float("nan")
    return row, eq


def shipped_v2(metrics_dir):
    """The published v2 figures, READ FROM THE ARTEFACT, never typed in."""
    f = Path(metrics_dir) / "v34_comparison.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    r = d[d["Config"].astype(str).str.startswith("v2")]
    if not len(r):
        return None
    r = r.iloc[0]
    return {"CAGR%": float(r["CAGR%"]), "Sharpe": float(r["Sharpe"]),
            "MaxDD%": float(r["MaxDD%"])}


def run_universe(uni, cfg, out):
    W = out.append
    src, px, op, sc = load_panel(cfg, uni)
    fp = panel_fingerprint(px, op, sc)

    bd = px.index[(px.index >= config.BT_START_DATE)
                  & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()

    W("=" * 100)
    W(f" TOP_N VALIDATION -- {cfg['label']} ({uni})")
    W("=" * 100)
    W("")
    W(f"  score panel   {src}")
    W(f"  symbol set    {px.shape[1]} names, asserted equal to the configured universe")
    W(f"  window        {bd[0].date()} .. {bd[-1].date()}   {len(bd)} trading days")
    W(f"  engine        test_exposure.backtest_exposure (SHIPPING)")
    W(f"  arms          TOP_N={INCUMBENT} vs TOP_N={CHALLENGER}, "
      f"BUFFER pinned at {BUFFER_PINNED} in both")
    W(f"  panel sha256  {fp}")
    W("")

    full, curves = {}, {}
    for tn in (INCUMBENT, CHALLENGER):
        row, eq = run_arm(tn, px, op, sc, bd, pc, mom20, port_vol, tv,
                          f"TOP_N={tn} BUFFER={BUFFER_PINNED}")
        full[tn], curves[tn] = row, eq

    # Both arms must have read one panel. Recomputed after the runs, because an
    # arm that mutated the panel in place would otherwise go undetected.
    fp_after = panel_fingerprint(px, op, sc)
    same_panel = (fp == fp_after)
    W(f"  IDENTICAL PANEL FOR BOTH ARMS: "
      f"{'yes' if same_panel else 'NO -- the panel changed between arms'}")
    if not same_panel:
        raise SystemExit(f"{uni}: the panel changed during the run; no verdict reported.")

    # --- identity gate: the incumbent arm must reproduce shipped v2 ------------
    ship = shipped_v2(cfg["metrics_dir"])
    gate_rows, gate_ok = [], True
    if ship is None:
        gate_ok = False
        W("\n  IDENTITY GATE: v34_comparison.csv not found -- cannot check the")
        W("  incumbent against the shipped v2. No verdict is reported.")
    else:
        W("")
        W("  IDENTITY GATE -- the TOP_N=8 arm must reproduce the shipped v2")
        W(f"  {'metric':<10}{'this run':>12}{'v34_comparison':>16}{'':>8}")
        for k in ("CAGR%", "Sharpe", "MaxDD%"):
            a, b = float(full[INCUMBENT][k]), ship[k]
            ok = abs(a - b) < 0.005
            gate_ok = gate_ok and ok
            gate_rows.append({"metric": k, "this_run": a, "shipped": b, "match": ok})
            W(f"  {k:<10}{a:>12.2f}{b:>16.2f}{('ok' if ok else 'MISMATCH'):>8}")

    # --- sub-periods, re-run independently ------------------------------------
    subs = []
    for hname, y0, y1 in HALVES:
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= config.BT_START_DATE)
                      & (px.index <= config.BT_END_DATE)]
        for tn in (INCUMBENT, CHALLENGER):
            row, _ = run_arm(tn, px, op, sc, hd, pc, mom20, port_vol, tv,
                             f"TOP_N={tn} BUFFER={BUFFER_PINNED}")
            row["Period"] = hname
            row["FirstDate"] = str(hd[0].date())
            row["LastDate"] = str(hd[-1].date())
            row["Days"] = len(hd)
            subs.append(row)

    # --- criteria -------------------------------------------------------------
    d_full = float(full[INCUMBENT]["Sharpe"]) - float(full[CHALLENGER]["Sharpe"])
    crit_full = d_full >= 0
    crit_halves = []
    for hname, _, _ in HALVES:
        a = [r for r in subs if r["Period"] == hname and r["TOP_N"] == INCUMBENT][0]
        b = [r for r in subs if r["Period"] == hname and r["TOP_N"] == CHALLENGER][0]
        d = float(a["Sharpe"]) - float(b["Sharpe"])
        crit_halves.append({"period": hname, "delta": round(d, 4), "holds": d >= 0})

    cols = ["TOP_N", "BUFFER", "CAGR%", "AnnVol%", "Sharpe", "MaxDD%", "Calmar",
            "Deployed%", "Trades", "TradesPerYear", "TradesPerRebal",
            "MeanNamesHeld", "CashShortSkips", "TC_Rs", "FinalEquity"]

    W("")
    W("-" * 100)
    W(" FULL PERIOD -- gated on Sharpe only. Everything else is reported, not gated.")
    W("-" * 100)
    W(f" {'TOP_N':>6}{'CAGR%':>8}{'AnnVol%':>9}{'Sharpe':>8}{'MaxDD%':>9}"
      f"{'Trades':>8}{'/year':>8}{'/rebal':>8}{'MeanHeld':>10}{'CashShort':>10}")
    for tn in (INCUMBENT, CHALLENGER):
        r = full[tn]
        W(f" {tn:>6}{r['CAGR%']:>8.2f}{r['AnnVol%']:>9.2f}{r['Sharpe']:>8.2f}"
          f"{r['MaxDD%']:>9.2f}{r['Trades']:>8}{r['TradesPerYear']:>8.1f}"
          f"{r['TradesPerRebal']:>8.2f}{str(r['MeanNamesHeld']):>10}"
          f"{r['CashShortSkips']:>10}")
    W("")
    W(f"  dSharpe (8 minus 12)          {d_full:+.4f}")
    W(f"  dCAGR   (8 minus 12)          "
      f"{float(full[INCUMBENT]['CAGR%'])-float(full[CHALLENGER]['CAGR%']):+.2f} pt")
    W(f"  dMaxDD  (8 minus 12)          "
      f"{float(full[INCUMBENT]['MaxDD%'])-float(full[CHALLENGER]['MaxDD%']):+.2f} pt")
    W("")
    W("  TURNOVER, AND THE SIZE OF THE PIN'S HANDICAP")
    W("    BUFFER is 16 in both arms, so the hysteresis band is "
      f"{BUFFER_PINNED-INCUMBENT} ranks wide at TOP_N={INCUMBENT} and "
      f"{BUFFER_PINNED-CHALLENGER} at TOP_N={CHALLENGER}.")
    ti, tc_ = full[INCUMBENT]["Trades"], full[CHALLENGER]["Trades"]
    W(f"    trades {ti} vs {tc_}   "
      f"({(tc_-ti)/ti*100:+.1f}% for the challenger)")
    W("    The challenger is handicapped by the pin. This test cannot separate")
    W("    '8 is a better concentration' from '16 suits 8 better than it suits 12'.")

    W("")
    W("-" * 100)
    W(" SUB-PERIODS -- each half re-run independently, intersected with the window")
    W("-" * 100)
    W(f" {'period':<12}{'TOP_N':>6}{'days':>6}{'CAGR%':>8}{'AnnVol%':>9}{'Sharpe':>8}"
      f"{'MaxDD%':>9}{'Trades':>8}{'MeanHeld':>10}{'CashShort':>10}")
    for r in subs:
        W(f" {r['Period']:<12}{r['TOP_N']:>6}{r['Days']:>6}{r['CAGR%']:>8.2f}"
          f"{r['AnnVol%']:>9.2f}{r['Sharpe']:>8.2f}{r['MaxDD%']:>9.2f}"
          f"{r['Trades']:>8}{str(r['MeanNamesHeld']):>10}{r['CashShortSkips']:>10}")
    W("")
    for c in crit_halves:
        W(f"  {c['period']}  dSharpe (8 minus 12)  {c['delta']:+.4f}")

    # --- the funding-defect prediction, on the record ------------------------
    W("")
    W("  THE FUNDING-DEFECT PREDICTION, TESTED")
    W("    TOPN_SPEC.txt records, before the run, an expectation that TOP_N=12")
    W("    would show HIGHER cash-short skips than TOP_N=8, because twelve targets")
    W("    funded from cash alone is more pressure on the same defect.")
    si = int(full[INCUMBENT]["CashShortSkips"])
    sc_ = int(full[CHALLENGER]["CashShortSkips"])
    W(f"    measured, full period:  TOP_N=8 {si}   TOP_N=12 {sc_}")
    W(f"    the prediction is {'BORNE OUT' if sc_ > si else 'NOT BORNE OUT'} on {uni}.")

    return {"uni": uni, "full": full, "subs": subs, "gate_ok": gate_ok,
            "gate_rows": gate_rows, "crit_full": crit_full, "d_full": d_full,
            "crit_halves": crit_halves, "cols": cols, "panel": str(src),
            "fingerprint": fp, "days": len(bd),
            "window": (str(bd[0].date()), str(bd[-1].date()))}


def write_artefacts(res, cfg):
    md = Path(cfg["metrics_dir"])
    pd.DataFrame([res["full"][INCUMBENT], res["full"][CHALLENGER]])[
        res["cols"]].to_csv(md / "topn_full.csv", index=False)
    pd.DataFrame(res["subs"])[["Period", "FirstDate", "LastDate", "Days"]
                              + res["cols"]].to_csv(md / "topn_subperiods.csv",
                                                    index=False)
    params = {
        "spec": "experiments/TOPN_SPEC.txt Part B",
        "universe": res["uni"],
        "window_start": res["window"][0], "window_end": res["window"][1],
        "trading_days": res["days"],
        "engine": "test_exposure.backtest_exposure (shipping)",
        "mode": "breadth", "sizing": "invvol",
        "incumbent_top_n": INCUMBENT, "challenger_top_n": CHALLENGER,
        "buffer_pinned": BUFFER_PINNED,
        "vol_win": VOL_WIN,
        "score_panel": res["panel"], "panel_sha256": res["fingerprint"],
        "identity_gate_passed": bool(res["gate_ok"]),
        "git": _git_state(),
    }
    (md / "topn_params.json").write_text(json.dumps(params, indent=2) + "\n")


def main():
    results, out_all = {}, []
    for uni, cfg in UNIVERSES.items():
        out = []
        res = run_universe(uni, cfg, out)
        write_artefacts(res, cfg)
        results[uni] = res
        (ROOT / "diagnostics" / f"topn_{uni}.txt").write_text("\n".join(out) + "\n")
        out_all += out + [""]

    # ---- combined verdict, computed ----------------------------------------
    W = out_all.append
    W("=" * 100)
    W(" VERDICT -- rule fixed in experiments/TOPN_SPEC.txt before any number existed")
    W("=" * 100)
    W("")
    gates_ok = all(r["gate_ok"] for r in results.values())
    if not gates_ok:
        W("  IDENTITY GATE FAILED. The TOP_N=8 arm did not reproduce the shipped v2")
        W("  in at least one universe, so the harness is wrong and NO verdict is")
        W("  reported for either arm. This is a correctness gate, not a performance")
        W("  gate: failure voids the run rather than producing a result.")
        (ROOT / "diagnostics" / "topn_verdict.txt").write_text("\n".join(out_all) + "\n")
        print("\n".join(out_all))
        return

    per_uni = {}
    for uni, r in results.items():
        halves_ok = all(c["holds"] for c in r["crit_halves"])
        per_uni[uni] = r["crit_full"] and halves_ok
        W(f"  {uni}")
        W(f"    full period      dSharpe {r['d_full']:+.4f}   "
          f"{'holds' if r['crit_full'] else 'does not hold'}")
        for c in r["crit_halves"]:
            W(f"    {c['period']}        dSharpe {c['delta']:+.4f}   "
              f"{'holds' if c['holds'] else 'does not hold'}")
    W("")
    all_hold = all(per_uni.values())
    any_hold = any(per_uni.values())
    outcome = "NOT CONTRADICTED" if all_hold else "CONTRADICTED"
    W(f"  TOP_N={INCUMBENT} IS {outcome}"
      + ("" if all_hold else " -- at least one criterion does not hold"))
    W("")
    # THE SECOND HALF OF THE OUTCOME, PRINTED WITH THE FIRST AND NOT BELOW IT.
    # Computed from the run, never asserted: if the challenger's drawdown were
    # not shallower, these lines would say so.
    dd = {u: (float(r["full"][INCUMBENT]["MaxDD%"]),
              float(r["full"][CHALLENGER]["MaxDD%"])) for u, r in results.items()}
    shallower = [u for u, (i, c) in dd.items() if c > i]
    if len(shallower) == len(dd):
        W(f"  AND IN THE SAME MEASUREMENT, TOP_N={CHALLENGER} HAD THE SHALLOWER MaxDD")
        W(f"  IN BOTH UNIVERSES, ON A DIMENSION THE RULE DOES NOT GATE.")
    elif shallower:
        W(f"  AND IN THE SAME MEASUREMENT, TOP_N={CHALLENGER} HAD THE SHALLOWER MaxDD")
        W(f"  ON {', '.join(shallower)}, ON A DIMENSION THE RULE DOES NOT GATE.")
    else:
        W(f"  TOP_N={INCUMBENT} ALSO HELD THE SHALLOWER MaxDD IN EVERY UNIVERSE,")
        W(f"  ON A DIMENSION THE RULE DOES NOT GATE.")
    for u, (i, c) in dd.items():
        W(f"    {u:<6} MaxDD  TOP_N={INCUMBENT} {i:.2f}   TOP_N={CHALLENGER} {c:.2f}")
    W("")
    sh_lo = all(float(results[u]["full"][CHALLENGER]["Sharpe"])
                < float(results[u]["full"][INCUMBENT]["Sharpe"]) for u in results)
    W(f"  THIS IS NOT A CLAIM THAT TOP_N={CHALLENGER} IS BETTER.")
    W(f"    Its Sharpe is lower in {'every period' if sh_lo else 'the periods gated above'},")
    tt = ", ".join(f"{u} {(float(results[u]['full'][CHALLENGER]['Trades'])/float(results[u]['full'][INCUMBENT]['Trades'])-1)*100:+.1f}%"
                   for u in results)
    W(f"    and its turnover is higher -- {tt}.")
    W("    NO DRAWDOWN CRITERION WAS PRE-REGISTERED, so nothing here is a result")
    W("    about drawdown. It is an ungated observation, recorded because the rule")
    W("    cannot see it.")
    W("")
    W("    NO DRAWDOWN CRITERION IS ADDED NOW. That would be fitting the rule to")
    W("    the data, which is what documenting the Sharpe-only asymmetry rather")
    W("    than fixing it was meant to avoid. It stays ungated and recorded.")
    W("")
    if all_hold:
        W("  WHAT THIS MEANS, AND ITS CEILING")
        W(f"    TOP_N={INCUMBENT} is not beaten by TOP_N={CHALLENGER} on either live")
        W("    universe, full period or either half, under entry 10's own criterion,")
        W("    measured on the shipping engine.")
        W("    IT DOES NOT RE-EARN entry 10's acceptance. The record does not state")
        W("    what BUFFER the original 12-arm ran at, so this cannot be shown to be")
        W("    entry 10's contrast. NOT CONTRADICTED is the ceiling in every outcome.")
        W(f"    IT DOES NOT MEAN {INCUMBENT} is optimal. Two arms cannot say that.")
    elif any_hold:
        held = [u for u, v in per_uni.items() if v]
        fell = [u for u, v in per_uni.items() if not v]
        W("  THE UNIVERSES DISAGREE, AND THE DISAGREEMENT IS THE FINDING.")
        W(f"    holds on {', '.join(held)}; does not hold on {', '.join(fell)}.")
        W("    It is NOT resolved toward either universe, NOT averaged, NOT called a")
        W("    hold with a caveat, and NOT re-run with a changed criterion. Neither")
        W("    universe is primary. Same handling as the v34 measurement.")
    else:
        W("  THE INCUMBENT IS CONTRADICTED ON BOTH LIVE UNIVERSES.")
        W("    The single acceptance in twenty-five trials does not reproduce on the")
        W(f"    universes that ship. This does NOT promote TOP_N={CHALLENGER}:")
        W("    promotion is a separate decision needing its own pre-registration.")
        W("    The immediate output is a KNOWN_ISSUES.md entry, not a config change.")
    W("")
    W("  NOT GATED, REPORTED ONLY: MaxDD, CAGR, volatility, turnover, mean names")
    W("  held and cash-short skips. Entry 10 gated on Sharpe alone and this")
    W("  inherits that. A challenger matching Sharpe while halving drawdown would")
    W("  not be detected by this rule.")
    W("")
    W("  THIS COUNTS AS A TRIAL and is entered in experiments/EXPERIMENTS.md.")
    W("  Calling it a validation constrains what may be DONE with the result --")
    W("  no promotion, no second value, no re-run at a changed criterion -- and")
    W("  that is the whole of the difference.")
    W("=" * 100)

    (ROOT / "diagnostics" / "topn_verdict.txt").write_text("\n".join(out_all) + "\n")
    print("\n".join(out_all))


if __name__ == "__main__":
    main()
