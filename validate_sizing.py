"""
validate_sizing.py -- run engine_core.py's inverse-vol validation suite on a
live universe rather than the retired one it was written for.

WHY THIS EXISTS
    The four-test suite that lived in engine_core.main() ([2] VALIDATION; main()
    was deleted 2026-09-24) is the only evidence that inverse-vol sizing is real
    rather than cherry-picked. It only ever ran on a retired universe. Inverse-vol is the default sizing in
    production on both live universes and has never been validated on either:
    engine_v2_final_n100.py says so in its own params file --
    "not measured on this universe".

    This script runs the same four tests on nifty100 or midcap150. It changes none
    of them.

THE FOUR TESTS ARE RE-IMPLEMENTED HERE, not called, because every path in
engine_core.main() was a hardcoded literal for a retired universe --
/tmp/v5_expanding.csv, /tmp/raw_panel_20.csv, M = config.METRICS_DIR -- with no
universe parameter. The CRITERIA are copied verbatim; only the paths move.

IMPORTING engine_core IS SAFE, AND THAT WAS VERIFIED RATHER THAN ASSUMED
    An AST walk over every module-level statement found no I/O: lines 49-50 edit
    sys.path, 88 and 95 construct Path objects without reading them, 68 is a try
    that only selects a cost function, and a __main__ guard kept main() -- which
    held every retired-universe path -- from running on import (both deleted
    2026-09-24). Confirmed empirically with /tmp cleared. Note that importing
    binds engine_core.M to results/metrics, the shared non-universe directory;
    nothing here writes through it.

THE T2 CACHE IS CONTENT-ADDRESSED, AND WAS NOT UNTIL 2026-09-22
    engine_core.main() cached seed scores at /tmp/FINAL_seed{i}.csv, with no
    universe in the name. A nifty100 run reusing that path would silently load the
    retired universe's scores and report a pass or a fail on the wrong data, with no error anywhere.
    The caches here carry a different prefix, so that collision is impossible.

    THE PREFIX WAS NOT ENOUGH. Until 2026-09-22 the name was
    /tmp/VALSIZE_{universe}_seed{i}.csv -- universe and seed-set index and
    nothing else -- so the key could not miss on a code change or a panel
    change. The same universe fit by a different engine against a different
    panel landed on the same path and was read back as if current. A --slow run
    on 2026-09-22 finished both universes in 0.0 and 0.1 min against caches
    written the day before, which is how it was found.

    The name is now /tmp/VALSIZE_{universe}_seed{i}_{key}.csv, where key is a
    sha256 over engine_core.py, this file, config.py, the raw panel's CONTENT
    and the seed list. See _t2_cache_key. A stale cache no longer collides with
    a live one; it is simply a file nothing asks for.

T1'S TRADE RANGE IS UNCHANGED AND DELIBERATELY NOT RECALIBRATED
    400-1400 was calibrated on the retired universe, which produced 706. Re-fitting it per
    universe would be changing the test. It stays, and the measured count is
    printed beside it so a universe falling outside becomes visible rather than
    failing a structural check for a reason nobody looks at.

THE SEED LOOP IS SEQUENTIAL, MATCHING engine_core.py
    T2 runs three seed sets one after another, three processes of ten cores, as
    engine_core does. Running the sets concurrently would be roughly three times
    faster and is deliberately not done: if a result differs from the original suite's, that
    must be the universe and not the harness.

WHAT CANNOT BE CHECKED HERE
    There is no artefact to gate the baseline against. engine_core.backtest is a
    separate implementation from the production test_exposure.backtest_exposure --
    on the retired universe they disagreed by design, 26.42% against 24.62% for
    the same sizing.
    So this script cannot prove it reproduces anything published. The strongest
    available check is T1's own structural test, and its numbers are printed.

Reads the panels. Writes only the /tmp seed caches -- nothing in the repository.

    python3 validate_sizing.py --universe=nifty100      # cost estimate, then stop
    python3 validate_sizing.py --universe=nifty100 --run # run the suite
"""
import sys, time, warnings
sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config
from engine_core import (backtest, precompute, metrics, score_monthly,
                         TOP_N, START_CAPITAL, HORIZON)
from universes.registry import REGISTRY
from seed_cache_key import seed_cache_key
from config import read_table  # the one CSV/parquet reader: config.read_table
# Date window from config.py, NOT engine_core's year ints -- see config.py.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE

# ALL FOUR PANEL PATHS come from universes/registry.py -- the single definition.
# The label is u.name, the "Nifty 100"/"MidCap150" spelling this file has always
# written into its committed artefacts.
from universes.registry import certified
UNIVERSES = {
    u.tag: {"score_perm": u.score_cache,
            "raw_perm": u.raw_cache,
            "label": u.name}
    for u in certified()
}

# Verbatim from engine_core.py:506 and :536 and :555. Not tuned, not reordered.
SEED_SETS = [[5, 55, 555], [13, 26, 39], [101, 202, 303]]
HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
VOL_WINDOWS = [40, 60, 90, 120]
TRADE_LO, TRADE_HI = 400, 1400      # engine_core.py:495, unchanged


# THE T2 CACHE KEY LIVES IN seed_cache_key.py, shared with validate_engine's T2,
# which had the identical defect. See that file for what goes into the key and
# why there is no override flag. What this file contributes is its own source --
# it chooses SEED_SETS and the columns written to the cache -- plus the universe
# tag and the seed values of the set being fit.
def _t2_cache_key(u, seeds, raw_path):
    return seed_cache_key(
        code_files=[ROOT / "results" / "engine_core.py",
                    ROOT / "validate_sizing.py",
                    ROOT / "config.py"],
        panel_path=raw_path,
        parts=(u, sorted(seeds)))


def sharpe_exact(eq):
    """Annualised Sharpe at full precision.

    T2, T3 AND T4 ARE DECIDED ON THIS, NOT ON metrics()["Sharpe"]. metrics()
    rounds to 2dp for display, and until 2026-09-22 every verdict in this file
    compared those rounded values -- T2 and T3 on `round(iv - eq, 2)`, T4 on
    `t4["Sharpe"] > eq_sh` with both sides already rounded. A difference smaller
    than half a hundredth therefore read as 0.00 and failed a strict `> 0`
    whatever its true sign.

    results/validate_engine.py's sharpe_exact has recorded this trap since it was
    written, including the sentence "engine_core's suite compares rounded values
    too; it never bit there only because its margins happened to be wider". It
    bit. Measured 2026-09-22 on nifty100, three results that are genuinely
    positive and were being counted as failures:

        T3 2023-2026   exact +0.002156   printed +0.00   1.38 vs 1.38
        T4 vol_win= 60 exact +0.000122   1.27 vs 1.27
        T4 vol_win=120 exact +0.007148   1.27 vs 1.27

    THE THRESHOLD IS UNCHANGED AND STILL STRICT `> 0`. This is a precision
    correction, not a wider bar, and it moves no verdict: all four T3/T4 verdicts
    still FAIL. What it stops is T4 claiming three of four vol windows fail on
    nifty100 when one does. The rounded figures stay in the printed tables for
    readability, next to the exact margins.

    NO NOISE BAND IS APPLIED. A margin of +0.0001 is arithmetically a pass and is
    not evidence of anything; the margin is printed beside every verdict and the
    reader judges it. EXPERIMENTS.md entry 29 measured this project's seed floor
    in CAGR points, not Sharpe, so there is no measured Sharpe floor to use and
    none is invented.
    """
    r = eq.pct_change().dropna()
    return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0


def universe_from_argv():
    from universes.registry import argv_universes, check_tags
    picked = check_tags(argv_universes(sys.argv), UNIVERSES)
    if picked:
        return picked[-1]
    print(f"usage: validate_sizing.py --universe=<{'|'.join(UNIVERSES)}> [--run]")
    print("  no default -- the universe must be named explicitly.")
    sys.exit(2)


def main():
    u = universe_from_argv()
    U = UNIVERSES[u]
    t_start = time.perf_counter()

    print("=" * 110)
    print(f" SIZING VALIDATION -- is inverse-vol real, or cherry-picked?   "
          f"[{U['label']} / {u}]")
    print("=" * 110)
    print("  The four tests below are engine_core.py's, unchanged. Only the panel")
    print("  paths differ. engine_core.py itself is not modified by this script.")

    score_path = config.require_cache(U["score_perm"],
                                      what=f"{U['label']} score panel")
    p = read_table(score_path, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
    pc = precompute(px)
    print(f"\n  score panel : {score_path}")
    print(f"                {px.shape[1]} symbols, {len(px)} dates, "
          f"{len(bd)} in the backtest window")

    # ---------------------------------------------------------------- [1] arms
    print("\n" + "=" * 110)
    print("[1] THE TWO SIZING ARMS")
    print("=" * 110)
    eq_eq, tc1, n1, tl1, ap1 = backtest(px, op, sc, bd, pc, sizing="equal")
    eq_iv, tc2, n2, tl2, ap2 = backtest(px, op, sc, bd, pc, sizing="invvol")
    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    comp = pd.DataFrame([metrics(eq_eq, "Equal-rupee (validation engine)", tc1, n1),
                         metrics(eq_iv, "Inverse-vol (validation engine)", tc2, n2),
                         metrics(bh, f"Equal-weight buy & hold ({u})")])
    print(comp.to_string(index=False))

    if "--run" not in sys.argv:
        n_months = len(sorted(read_table(U["raw_perm"], usecols=["date"],
                                          parse_dates=["date"])
                              .query("date.dt.year >= 2016")["date"]
                              .dt.to_period("M").unique()))
        print("\n" + "=" * 110)
        print(" COST")
        print("=" * 110)
        print(f"   T1, T3, T4 are backtests only          : seconds")
        print(f"   T2 REFITS the model: {n_months} months x 3 seeds x "
              f"{len(SEED_SETS)} sets = {n_months*3*len(SEED_SETS):,} LightGBM fits")
        print(f"   measured on nifty100 at 3.57 s/month   : ~22.7 min")
        print(f"   seed sets run SEQUENTIALLY (3 procs of 10 cores), matching")
        print(f"   engine_core.py -- comparability over speed")
        print("\n   Stopping here. Re-run with --run to execute the suite.")
        return

    print("\n" + "=" * 110)
    print("[2] VALIDATION -- is inverse-vol real, or cherry-picked?")
    print("=" * 110)
    passed = {}

    # ------------------------------------------------------------------- T1
    print("\n  T1. BASELINE CONTROL -- does equal-rupee reproduce the engine?")
    m1 = comp.iloc[0]
    ok1 = (abs(ap1 - float(TOP_N)) < 0.2 and TRADE_LO <= m1["Trades"] <= TRADE_HI)
    print(f"      structural target: ~{float(TOP_N):.1f} positions, "
          f"trades within {TRADE_LO}-{TRADE_HI}")
    print(f"      got             : CAGR {m1['CAGR%']}%, Sharpe {m1['Sharpe']}, "
          f"{int(m1['Trades'])} trades, {ap1:.1f} positions")
    inside = TRADE_LO <= m1["Trades"] <= TRADE_HI
    print(f"      trade count {int(m1['Trades'])} is "
          f"{'INSIDE' if inside else 'OUTSIDE'} the {TRADE_LO}-{TRADE_HI} range "
          f"(range unchanged from the retired universe, which produced 706)")
    print(f"      (CAGR varies +/-0.5% per retrain -- not checked; structure is)")
    print(f"      -> {'PASS' if ok1 else 'FAIL -- slot-cap or buffer logic broken'}")
    passed["T1 baseline control"] = ok1

    # ------------------------------------------------------------------- T2
    print("\n  T2. SEED ROBUSTNESS -- does inv-vol win on OTHER score seeds?")
    raw_path = config.require_cache(U["raw_perm"],
                                    what=f"{U['label']} raw feature panel")
    raw = read_table(raw_path, parse_dates=["date"])
    t2_rows = []
    for si, seeds in enumerate(SEED_SETS):
        key = _t2_cache_key(u, seeds, raw_path)
        cache = Path(f"/tmp/VALSIZE_{u}_seed{si}_{key}.csv")
        if cache.exists():
            ps = read_table(cache, parse_dates=["date"])
            print(f"      seed set {si+1}/3 from cache {cache.name} "
                  f"(key {key}: engine_core + validate_sizing + config + raw "
                  f"panel content + seeds)", flush=True)
        else:
            print(f"      scoring seed set {si+1}/3 (refits the model) ...", flush=True)
            ps = score_monthly(raw, seeds)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
        pxs = ps.pivot_table(index="date", columns="symbol", values="close").ffill()
        ops = ps.pivot_table(index="date", columns="symbol", values="open").ffill()
        scs = ps.pivot_table(index="date", columns="symbol", values="score")
        bds = pxs.index[(pxs.index >= BT_START_DATE) & (pxs.index <= BT_END_DATE)]
        pcs = precompute(pxs)
        e_e, _, _, _, _ = backtest(pxs, ops, scs, bds, pcs, sizing="equal")
        e_i, _, _, _, _ = backtest(pxs, ops, scs, bds, pcs, sizing="invvol")
        me, mi = metrics(e_e, "eq"), metrics(e_i, "iv")
        t2_rows.append({"seedset": si, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                        "delta_exact": round(sharpe_exact(e_i) - sharpe_exact(e_e), 6),
                        "eq_MaxDD": me["MaxDD%"], "iv_MaxDD": mi["MaxDD%"]})
        print(f"      seed set {si+1}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {mi['Sharpe']-me['Sharpe']:+.2f}) | MaxDD {me['MaxDD%']:.1f}% -> "
              f"{mi['MaxDD%']:.1f}%", flush=True)
    t2 = pd.DataFrame(t2_rows)
    ok2 = bool((t2["delta_exact"] > 0).all())
    print(f"      -> improved on {(t2['delta_exact']>0).sum()}/3 seed sets "
          f"(smallest margin {t2['delta_exact'].min():+.6f} Sharpe). "
          f"{'PASS' if ok2 else 'FAIL -- seed-dependent'}")
    passed["T2 seed robustness"] = ok2

    # ------------------------------------------------------------------- T3
    print("\n  T3. SUB-PERIOD SPLIT -- works in BOTH halves independently?")
    t3_rows = []
    for hname, y0, y1 in HALVES:
        # INTERSECTED WITH THE BACKTEST WINDOW, not sliced from the full panel.
        # Slicing px.index by year alone let the late half run to the end of the
        # price data (2026-06-08) while the full period stopped at BT_END_DATE,
        # so the two ended on different days in the same report. engine_core.main()
        # had that bug; it affected only a retired universe, is recorded in
        # KNOWN_ISSUES.md, and went with main() on 2026-09-24.
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
        e_e, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="equal")
        e_i, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="invvol")
        bhh = START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        me, mi, mb = metrics(e_e, "eq"), metrics(e_i, "iv"), metrics(bhh, "bh")
        t3_rows.append({"period": hname, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "bh_Sharpe": mb["Sharpe"], "delta": round(mi["Sharpe"]-me["Sharpe"], 2),
                        "delta_exact": round(sharpe_exact(e_i) - sharpe_exact(e_e), 6)})
        print(f"      {hname}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {sharpe_exact(e_i)-sharpe_exact(e_e):+.6f} exact) "
              f"| buy&hold {mb['Sharpe']:.2f}")
    t3 = pd.DataFrame(t3_rows)
    ok3 = bool((t3["delta_exact"] > 0).all())
    print(f"      -> {'PASS' if ok3 else 'FAIL -- only works in one sub-period'}"
          f"   (smallest margin {t3['delta_exact'].min():+.6f} Sharpe)")
    passed["T3 sub-period"] = ok3

    # ------------------------------------------------------------------- T4
    print("\n  T4. PARAMETER SENSITIVITY -- does the vol window matter?")
    t4_rows = []
    for vw in VOL_WINDOWS:
        pcv = precompute(px, vol_win=vw)
        e_i, tcv, nv, _, _ = backtest(px, op, sc, bd, pcv, sizing="invvol")
        mi = metrics(e_i, f"vol_win={vw}", tcv, nv)
        mi["Sharpe_exact"] = round(sharpe_exact(e_i), 6)
        t4_rows.append(mi)
        print(f"      vol_win={vw:>3}: CAGR {mi['CAGR%']:>6.2f}%  Sharpe {mi['Sharpe']:>5.2f}  "
              f"MaxDD {mi['MaxDD%']:>7.2f}%  margin vs equal-rupee "
              f"{sharpe_exact(e_i)-sharpe_exact(eq_eq):+.6f}")
    t4 = pd.DataFrame(t4_rows)
    # THE REFERENCE IS THE EXACT SHARPE OF THE SAME equal-rupee CURVE T1 REPORTS,
    # not comp's rounded column. Comparing a rounded arm against a rounded
    # reference is what made vol_win=60 and 120 read as failures on nifty100 at
    # +0.000122 and +0.007148.
    eq_sh_exact = sharpe_exact(eq_eq)
    ok4 = bool((t4["Sharpe_exact"] > eq_sh_exact).all())
    print(f"      -> all four beat equal-rupee ({eq_sh_exact:.6f} exact)? "
          f"{'PASS' if ok4 else 'FAIL -- depends on exact window'}"
          f"   (smallest margin {(t4['Sharpe_exact']-eq_sh_exact).min():+.6f} Sharpe)")
    passed["T4 param sensitivity"] = ok4

    # ------------------------------------------------- SUB-PERIOD TABLE (added)
    # ADDED TABLE, NOT A CHANGE TO THE SUITE. The four tests above and their
    # pass/fail criteria are untouched; nothing below feeds back into `passed`.
    #
    # It uses the same HALVES constant and the same window intersection as T3, so
    # the late half ends on BT_END_DATE rather than on the last day of the price
    # panel. Every arm the script already runs appears, plus equal-weight buy &
    # hold of the same universe as a constant reference line carrying the same
    # columns.
    print("\n" + "=" * 110)
    print("[3] SUB-PERIODS -- reported, not graded")
    print("=" * 110)
    sp_rows = []
    for hname, y0, y1 in HALVES:
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
        e_e, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="equal")
        e_i, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="invvol")
        bhh = START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        for lab, e in (("Equal-rupee (validation engine)", e_e),
                       ("Inverse-vol (validation engine)", e_i),
                       (f"Equal-weight buy & hold ({u})", bhh)):
            m = metrics(e, lab)
            r = e.pct_change().dropna()
            sp_rows.append({"Period": hname, "Config": lab,
                            "CAGR%": m["CAGR%"],
                            "AnnVol%": round(float(r.std() * np.sqrt(252) * 100), 2),
                            "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"],
                            "FirstDate": str(hd[0].date()),
                            "LastDate": str(hd[-1].date()), "Days": len(hd)})
    sp = pd.DataFrame(sp_rows)
    print(sp.to_string(index=False))

    # -------------------------------------------------------------- summary
    print("\n" + "-" * 110)
    print("  VALIDATION SUMMARY")
    print("-" * 110)
    for k, v in passed.items():
        print(f"    {'PASS' if v else 'FAIL'}  {k}")
    n_ok = sum(passed.values())
    print(f"\n    {n_ok} of {len(passed)} passed.")
    if n_ok < len(passed):
        print("    SOME FAILED -- read the failures before trusting the result.")
    print(f"\n  runtime: {(time.perf_counter()-t_start)/60:.1f} min")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No test, threshold
    # or printed number above this point changed. The pass condition is the one
    # the summary already applies -- every one of the four tests must pass -- and
    # it is restated here only so a runner can read it from the exit code. This
    # printed "SOME FAILED" and exited 0, so nothing calling it could tell.
    rc = 0 if n_ok == len(passed) else 1
    print(f"\n  RESULT: {'PASS' if rc == 0 else 'FAIL'} -- "
          f"{n_ok} of {len(passed)} tests passed on {U['label']}.")
    print("=" * 110)
    return rc


if __name__ == "__main__":
    sys.exit(main())
