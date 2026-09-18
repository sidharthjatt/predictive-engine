"""
validate_engine.py -- the four-test validation suite, run against the SHIPPING engine.
=====================================================================================
    ./venv/bin/python results/validate_engine.py                  # 58 + mid + n100
    ./venv/bin/python results/validate_engine.py --universe=58    # one universe
    ./venv/bin/python results/validate_engine.py --fast           # skip T2 (no scoring)

WHY THIS FILE EXISTS
    The four-test suite (T1 baseline, T2 seed robustness, T3 sub-period, T4 vol-window)
    lives inside engine_core.main() and tests engine_core.backtest. That is NOT the
    engine that produces the published numbers -- those come from
    test_exposure.backtest_exposure. The two disagree by 1.80 CAGR points on the 58
    (26.42 vs 24.62), for three independent reasons measured on 2026-09-04:
      - sizing base   : cash * 0.98        vs  port_val * exposure * 0.98
      - weight base   : renormalised over new buys  vs  share of the whole book
      - slot cap      : buy at most TOP_N - len(held)  vs  no cap
    So "inverse-vol was validated" and "v2 is what ships" were claims about different
    code. This file closes that gap: same four tests, pointed at the engine that ships.

    engine_core.py IS NOT MODIFIED. Its suite stays exactly where it is, as the
    historical record of what was validated before. This is an addition, not a
    replacement, and the two can be compared row for row.

WHAT T1 MEANS HERE, AND WHY IT IS NOT THE OLD T1
    engine_core's T1 asserted `abs(mean_positions - TOP_N) < 0.2`, and its comment
    says positions == TOP_N proves "the slot-cap and buffer logic are intact". That
    test is defined in terms of a mechanism the shipping engine deliberately does not
    have. engine_core caps new buys at TOP_N - len(shares), which on the 58 refused
    149 of the model's own top-8 picks across 93 rebalances, holding rank-9..16
    incumbents in preference to rank-1..8 entrants.

    The shipping engine has no such cap, so its book floats between TOP_N and BUFFER:
    it sells a name only once it leaves the top BUFFER, and buys every top-TOP_N name
    it does not already hold. A book of exactly TOP_N would in fact be evidence the
    buffer had stopped working.

    T1 IS THEREFORE A RANGE CHECK ON THE SAME UNDERLYING QUESTION -- is selection
    still doing what it is specified to do -- expressed in terms this engine can
    satisfy: the mean book sits within [TOP_N, BUFFER], and the trade count is in the
    same 400-1400 band the old T1 used. This is a redefinition and is labelled as one
    everywhere it is reported. It is NOT the old T1 and its PASS is not the old PASS.

WHAT IS COMPARED, IN EVERY TEST
    Inverse-vol sizing against EQUAL-rupee sizing, both at mode="none" (100%
    invested). That is the same contrast engine_core drew -- its backtest has no
    exposure mode at all -- so the verdicts stay comparable. Breadth scaling is a
    separate question with its own validation (validate_breadth_live.py); mixing it
    in here would change what the four tests mean.

THE 58 IS INCLUDED FOR COMPARABILITY, NOT AS A LIVE RESULT
    It is a retired universe whose score panel was built with the defective calendar
    purge. It is run so the engine change can be read as the only moving part against
    engine_core's own published verdicts. mid and n100 are the live universes and are
    the ones whose verdicts describe what ships.

NOTHING PUBLISHED IS OVERWRITTEN
    Outputs use the v2val_ prefix. engine_core's FINAL_val_*.csv are left untouched,
    so the old and new verdicts sit side by side rather than one replacing the other.
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import config
from universes.registry import REGISTRY
from engine_core import metrics, precompute, score_monthly, HORIZON
from test_exposure import backtest_exposure, TOP_N, BUFFER, START_CAPITAL
import profiles as _prof            # the run's execution-realism profile

# The same three alternate seed sets engine_core's T2 uses, so T2 is a like-for-like
# comparison rather than a differently-seeded one.
SEED_SETS = [[5, 55, 555], [13, 26, 39], [101, 202, 303]]
VOL_WINDOWS = [40, 60, 90, 120]
HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
TRADE_BAND = (400, 1400)          # the band engine_core's T1 used; carried over as-is

# One entry per universe. `purge_mode` is per-universe on purpose: the retired 58's
# panel was built with the defective calendar purge, so its alternate-seed panels must
# be too or T2 would compare against a differently-purged panel. The live universes
# take the corrected default.
UNIVERSES = {
    "58": {
        "label": "58 (retired -- comparability only)",
        "metrics": config.METRICS_DIR,
        "perm": config.METRICS_DIR / "v5_expanding_cache.csv",
        "tmp": "/tmp/v5_expanding.csv",
        "raw_tmp": f"/tmp/raw_panel_{HORIZON}.csv",
        "raw_perm": config.METRICS_DIR / "raw_panel_cache.csv",
        # engine_core's own T2 wrote these. Reusing them keeps T2 identical to the
        # old T2 on everything except the engine under test, which is the point.
        "seed_cache": lambda si: Path(f"/tmp/FINAL_seed{si}.csv"),
        "purge_mode": "calendar",
        "y_end": 2026,
        "live": False,
    },
    "midcap150": {
        "label": "MidCap150 (live)",
        "metrics": REGISTRY["midcap150"].metrics_dir,
        "perm": REGISTRY["midcap150"].metrics_dir / "v_midcap150_expanding_cache.csv",
        "tmp": "/tmp/v_midcap150_expanding.csv",
        "raw_tmp": "/tmp/raw_panel_midcap150_20.csv",
        "raw_perm": REGISTRY["midcap150"].metrics_dir / "raw_panel_midcap150_cache.csv",
        "seed_cache": lambda si: Path(f"/tmp/V2VAL_mid_seed{si}.csv"),
        "purge_mode": "trading",
        "y_end": 2026,
        "live": True,
    },
    "nifty100": {
        "label": "Nifty 100 (live)",
        "metrics": REGISTRY["nifty100"].metrics_dir,
        "perm": REGISTRY["nifty100"].metrics_dir / "v_nifty100_expanding_cache.csv",
        "tmp": "/tmp/v_nifty100_expanding.csv",
        "raw_tmp": "/tmp/raw_panel_nifty100_20.csv",
        "raw_perm": REGISTRY["nifty100"].metrics_dir / "raw_panel_nifty100_cache.csv",
        "seed_cache": lambda si: Path(f"/tmp/V2VAL_n100_seed{si}.csv"),
        "purge_mode": "trading",
        "y_end": 2026,
        "live": True,
    },
}


def pivot(p):
    """Panel -> the objects backtest_exposure wants."""
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return px, op, sc


def arm(px, op, sc, dates, pc, mom20, sizing, audit=None):
    """One always-invested arm. mode="none" matches engine_core.backtest, which has
    no exposure concept, so the sizing contrast is the only thing being measured."""
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See profiles.research_only.
    return backtest_exposure(px, op, sc, dates, pc, mom20, port_vol=None,
                             mode="none", sizing=sizing, audit=audit, participation_cap=_prof.research_only(__name__))


def mean_book(audit):
    """Mean number of names held per day, from the audit's daily summary."""
    s = pd.DataFrame(audit["summary"])
    return float(s["n_stocks"].mean()) if len(s) else float("nan")


def sharpe_exact(eq):
    """Annualised Sharpe at full precision.

    EVERY VERDICT IN THIS FILE IS DECIDED ON THIS, NOT ON metrics()["Sharpe"].
    metrics() rounds to 2dp for display. Comparing rounded values makes a verdict
    depend on which side of a decimal a number falls: on the 58, T4's vol_win=60 arm
    scores 1.242330 against an equal-rupee reference of 1.240205 -- it BEATS the
    reference by +0.002125, but both round to 1.24 and a rounded ">" therefore
    reports FAIL. engine_core's suite compares rounded values too; it never bit there
    only because its margins happened to be wider. The rounded figures are still
    written to the CSVs for readability, alongside the exact ones.

    A MARGIN IS REPORTED WITH EVERY VERDICT. A pass of +0.002 Sharpe is arithmetically
    a pass and is not evidence of anything: EXPERIMENTS.md entry 29 measured this
    project's seed-noise floor at sd 0.97-2.14 CAGR points. No Sharpe noise threshold
    has been measured here, so none is invented -- the margin is printed and the
    reader judges it.
    """
    r = eq.pct_change().dropna()
    return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0


def run_universe(tag, cfg, W, fast=False):
    W("=" * 104)
    W(f" VALIDATION SUITE vs THE SHIPPING ENGINE -- {cfg['label']}")
    W("=" * 104)
    W(f"  engine      test_exposure.backtest_exposure "
      f"(value_at_open default = causally clean sizing)")
    W(f"  contrast    inverse-vol vs equal-rupee, mode=\"none\" (100% invested)")
    W(f"  TOP_N={TOP_N}  BUFFER={BUFFER}  purge_mode=\"{cfg['purge_mode']}\"")

    src = config.require_cache(cfg["perm"], cfg["tmp"], what=f"{tag} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px, op, sc = pivot(p)
    bd = px.index[(px.index.year >= 2019) & (px.index.year <= cfg["y_end"])]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    W(f"  panel       {len(bd)} trading days, {px.shape[1]} symbols, "
      f"{bd[0].date()} -> {bd[-1].date()}")

    passed, tables = {}, {}

    # ---------------------------------------------------------------- T1
    W("\n  T1. BASELINE STRUCTURE -- is selection doing what it is specified to do?")
    W("      REDEFINED for this engine. engine_core's T1 asserted mean positions was")
    W(f"      within 0.2 of TOP_N, which tested for its slot cap. The shipping engine")
    W(f"      has no cap, so its book floats in [TOP_N, BUFFER] = [{TOP_N}, {BUFFER}] by")
    W("      design. A book pinned at TOP_N would mean the buffer had stopped working.")
    # NO AUDIT ON THE EQUAL ARM. backtest_exposure(sizing="equal", audit=<dict>)
    # raises UnboundLocalError: `v` (the vol series) is bound only in the non-equal
    # branch at test_exposure.py:198, but the audit's ranking block reads v.get(...)
    # at :231 unconditionally. That defect is PRE-EXISTING -- it is in git HEAD and is
    # not introduced by the valuation fix -- and it is reported rather than patched
    # here, because repairing the shipping engine is not this file's job. Only the
    # inverse-vol arm's book size is needed for T1, so the equal arm runs unaudited
    # and the bug is simply not triggered.
    a_iv = {k: [] for k in ("holdings", "summary", "trades", "ranking",
                            "decisions", "skipped")}
    eq_e, tc_e, n_e, _ = arm(px, op, sc, bd, pc, mom20, "equal")
    eq_i, tc_i, n_i, _ = arm(px, op, sc, bd, pc, mom20, "invvol", audit=a_iv)
    m_e, m_i = metrics(eq_e, "equal-rupee", tc_e, n_e), metrics(eq_i, "inverse-vol", tc_i, n_i)
    sh_ref = sharpe_exact(eq_e)          # the T4 reference, at full precision
    book_i = mean_book(a_iv)
    in_range = TOP_N <= book_i <= BUFFER
    in_band = TRADE_BAND[0] <= n_i <= TRADE_BAND[1]
    ok1 = in_range and in_band
    W(f"      structural target : mean book in [{TOP_N}, {BUFFER}]  and  "
      f"{TRADE_BAND[0]}-{TRADE_BAND[1]} trades")
    W(f"      got               : mean book {book_i:.2f} ({'in range' if in_range else 'OUT OF RANGE'}), "
      f"{n_i} trades ({'in band' if in_band else 'OUT OF BAND'})")
    W(f"      reference         : equal-rupee CAGR {m_e['CAGR%']}%, Sharpe {m_e['Sharpe']} | "
      f"inverse-vol CAGR {m_i['CAGR%']}%, Sharpe {m_i['Sharpe']}")
    W(f"      CAGR is not checked -- it moves +/-0.5% per refit. Structure is.")
    W(f"      -> {'PASS' if ok1 else 'FAIL -- selection or buffer logic is not behaving as specified'}")
    passed["T1 baseline structure (REDEFINED)"] = ok1

    # ---------------------------------------------------------------- T2
    if fast:
        W("\n  T2. SEED ROBUSTNESS -- SKIPPED (--fast). Not a PASS and not a FAIL.")
        passed["T2 seed robustness"] = None
    else:
        W("\n  T2. SEED ROBUSTNESS -- does inverse-vol still win on OTHER score seeds?")
        raw_src = config.require_cache(cfg["raw_perm"], cfg["raw_tmp"],
                                       what=f"{tag} raw panel")
        raw = pd.read_csv(raw_src, parse_dates=["date"])
        t2_rows = []
        for si, seeds in enumerate(SEED_SETS):
            cache = cfg["seed_cache"](si)
            if cache.exists():
                ps = pd.read_csv(cache, parse_dates=["date"])
                W(f"      seed set {si+1}/3 from cache {cache.name}")
            else:
                W(f"      seed set {si+1}/3 -- scoring (refits the model, slow) ...")
                ps = score_monthly(raw, seeds, purge_mode=cfg["purge_mode"])
                ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
            pxs, ops, scs = pivot(ps)
            bds = pxs.index[(pxs.index.year >= 2019) & (pxs.index.year <= cfg["y_end"])]
            pcs = precompute(pxs)
            m20s = pxs / pxs.shift(20) - 1
            e_e, _, _, _ = arm(pxs, ops, scs, bds, pcs, m20s, "equal")
            e_i, _, _, _ = arm(pxs, ops, scs, bds, pcs, m20s, "invvol")
            me, mi = metrics(e_e, "eq"), metrics(e_i, "iv")
            d_exact = sharpe_exact(e_i) - sharpe_exact(e_e)
            t2_rows.append({"seedset": si, "seeds": str(seeds),
                            "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                            "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                            "delta_exact": round(d_exact, 6),
                            "eq_MaxDD": me["MaxDD%"], "iv_MaxDD": mi["MaxDD%"],
                            "eq_CAGR": me["CAGR%"], "iv_CAGR": mi["CAGR%"]})
            W(f"        equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {d_exact:+.4f} exact) | "
              f"MaxDD {me['MaxDD%']:.1f}% -> {mi['MaxDD%']:.1f}%")
        t2 = pd.DataFrame(t2_rows)
        tables["seeds"] = t2
        ok2 = bool((t2["delta_exact"] > 0).all())
        W(f"      -> improved on {(t2['delta_exact']>0).sum()}/{len(t2)} seed sets "
          f"(smallest margin {t2['delta_exact'].min():+.4f} Sharpe). "
          f"{'PASS' if ok2 else 'FAIL -- seed-dependent'}")
        passed["T2 seed robustness"] = ok2

    # ---------------------------------------------------------------- T3
    W("\n  T3. SUB-PERIOD SPLIT -- does it work in BOTH halves independently?")
    t3_rows = []
    for hname, y0, y1 in HALVES:
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)]
        if len(hd) < 30:
            continue
        e_e, _, _, _ = arm(px, op, sc, hd, pc, mom20, "equal")
        e_i, _, _, _ = arm(px, op, sc, hd, pc, mom20, "invvol")
        bhh = START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        me, mi, mb = metrics(e_e, "eq"), metrics(e_i, "iv"), metrics(bhh, "bh")
        d_exact = sharpe_exact(e_i) - sharpe_exact(e_e)
        t3_rows.append({"period": hname, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "bh_Sharpe": mb["Sharpe"],
                        "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                        "delta_exact": round(d_exact, 6),
                        "iv_CAGR": mi["CAGR%"], "bh_CAGR": mb["CAGR%"],
                        "iv_MaxDD": mi["MaxDD%"], "bh_MaxDD": mb["MaxDD%"],
                        "days": len(hd)})
        W(f"      {hname}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
          f"(delta {d_exact:+.4f} exact) | buy&hold {mb['Sharpe']:.2f}")
    t3 = pd.DataFrame(t3_rows)
    tables["periods"] = t3
    ok3 = bool((t3["delta_exact"] > 0).all()) if len(t3) else False
    W(f"      -> {'PASS' if ok3 else 'FAIL -- only works in one sub-period'}"
      f"   (smallest margin {t3['delta_exact'].min():+.4f} Sharpe)")
    passed["T3 sub-period"] = ok3

    # ---------------------------------------------------------------- T4
    W("\n  T4. PARAMETER SENSITIVITY -- does the vol window matter?")
    t4_rows = []
    for vw in VOL_WINDOWS:
        pcv = precompute(px, vol_win=vw)
        e_i, tcv, nv, _ = arm(px, op, sc, bd, pcv, mom20, "invvol")
        mi = metrics(e_i, f"vol_win={vw}", tcv, nv)
        mi["Sharpe_exact"] = round(sharpe_exact(e_i), 6)
        mi["margin_vs_equal"] = round(sharpe_exact(e_i) - sh_ref, 6)
        t4_rows.append(mi)
        W(f"      vol_win={vw:>3}: CAGR {mi['CAGR%']:>6.2f}%  Sharpe {mi['Sharpe']:>5.2f}  "
          f"MaxDD {mi['MaxDD%']:>7.2f}%   margin vs equal-rupee "
          f"{mi['margin_vs_equal']:+.4f}")
    t4 = pd.DataFrame(t4_rows)
    tables["volwin"] = t4
    ok4 = bool((t4["margin_vs_equal"] > 0).all())
    W(f"      reference: equal-rupee Sharpe {sh_ref:.6f} (exact)")
    W(f"      -> all four beat equal-rupee? "
      f"{'PASS' if ok4 else 'FAIL -- depends on the exact window'}"
      f"   (smallest margin {t4['margin_vs_equal'].min():+.4f} Sharpe)")
    passed["T4 param sensitivity"] = ok4

    # ---------------------------------------------------------------- verdict
    W("\n  " + "-" * 100)
    counted = {k: v for k, v in passed.items() if v is not None}
    n_pass = sum(1 for v in counted.values() if v)
    for k, v in passed.items():
        W(f"    {k:<42s} {'PASS' if v else ('SKIPPED' if v is None else 'FAIL')}")
    W(f"    {'':<42s} {n_pass} of {len(counted)} tests passed")
    W("  " + "-" * 100)

    tables["summary"] = pd.DataFrame(
        [{"test": k, "verdict": ("SKIPPED" if v is None else ("PASS" if v else "FAIL"))}
         for k, v in passed.items()])
    return passed, tables, {"mean_book": round(book_i, 2), "trades": int(n_i),
                            "eq_Sharpe": m_e["Sharpe"], "iv_Sharpe": m_i["Sharpe"],
                            "eq_CAGR": m_e["CAGR%"], "iv_CAGR": m_i["CAGR%"]}


def main():
    fast = "--fast" in sys.argv
    unis = [u for u in UNIVERSES if f"--universe={u}" in sys.argv] or list(UNIVERSES)
    diag = ROOT / "diagnostics"
    diag.mkdir(exist_ok=True)

    all_out, results, heads = [], {}, {}
    for tag in unis:
        cfg = UNIVERSES[tag]
        out = []
        W = out.append
        passed, tables, head = run_universe(tag, cfg, W, fast=fast)
        results[tag], heads[tag] = passed, head
        md = Path(cfg["metrics"])
        for name, df in tables.items():
            df.to_csv(md / f"v2val_{name}.csv", index=False)
        W(f"\n  saved -> {md.name}/v2val_summary.csv, v2val_periods.csv, "
          f"v2val_volwin.csv" + (", v2val_seeds.csv" if "seeds" in tables else ""))
        (diag / f"validate_engine_{tag}.txt").write_text("\n".join(out) + "\n")
        print("\n".join(out))
        all_out += out + [""]

    # ------------------------------------------------------------ combined
    L = []
    L.append("=" * 104)
    L.append(" COMBINED VERDICT -- the shipping engine against the four tests")
    L.append("=" * 104)
    L.append("  Every verdict below is on test_exposure.backtest_exposure. engine_core's")
    L.append("  own FINAL_val_*.csv are untouched and still describe engine_core.backtest.")
    L.append("")
    names = sorted({k for r in results.values() for k in r})
    L.append(f"  {'test':<42s}" + "".join(f"{u:>12s}" for u in unis))
    for n in names:
        row = f"  {n:<42s}"
        for u in unis:
            v = results[u].get(n)
            row += f"{('SKIPPED' if v is None else ('PASS' if v else 'FAIL')):>12s}"
        L.append(row)
    L.append("")
    L.append(f"  {'mean book / trades':<42s}" +
             "".join(f"{str(heads[u]['mean_book'])+' / '+str(heads[u]['trades']):>12s}"
                     for u in unis))
    L.append(f"  {'Sharpe equal -> invvol':<42s}" +
             "".join(f"{str(heads[u]['eq_Sharpe'])+'->'+str(heads[u]['iv_Sharpe']):>12s}"
                     for u in unis))
    L.append("")
    live = [u for u in unis if UNIVERSES[u]["live"]]
    if live:
        L.append("  THE LIVE UNIVERSES ARE THE ONES THAT DESCRIBE WHAT SHIPS:")
        for u in live:
            c = {k: v for k, v in results[u].items() if v is not None}
            L.append(f"    {u:<6s} {sum(1 for v in c.values() if v)} of {len(c)} passed")
    L.append("=" * 104)
    (diag / "validate_engine_verdict.txt").write_text("\n".join(L) + "\n")
    print("\n" + "\n".join(L))


if __name__ == "__main__":
    main()
