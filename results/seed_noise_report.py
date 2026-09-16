"""
seed_noise_report.py -- sub-ensemble analysis from the persisted per-seed store.

WHY THIS IS SEPARATE. seed_noise_measure.py fitted 40 seeds per universe and
persisted every seed's scores, then stopped at its identity gate: the production
10 seeds reproduced from the store did NOT match the recorded figures.

THE GATE WAS CORRECT AND THE CAUSE IS NOT THE SEEDS.
    build_scores_{n100,mid}.py call score_monthly on the IN-MEMORY panel. This
    store was fitted on the panel read back from raw_panel_*_cache.csv. The CSV
    round-trip differs from the in-memory float64 by one unit in the last place
    -- max 4.441e-16 across 2,638,259 cells -- and that is enough to change
    LightGBM split decisions, flip near-tied ranks and move headline CAGR.

    So the store sits at a slightly different BASELINE from production. It does
    not invalidate the SPREAD: all 40 seeds were fitted on one identical panel,
    so sub-ensembles drawn from the store differ from each other ONLY by seed.

    The baseline offset is reported explicitly rather than hidden, and no figure
    from this file is presented as reproducing the shipped numbers.
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
import config
from seed_noise_measure import (SEEDS, K_GRID, M_SUBSETS, ARMS, UNIVERSES,
                                make_backtester, REQUIRED_RAW, assert_columns)


def run(uni, cfg, W):
    store = ROOT / "results" / f"SEEDNOISE_{uni}_scores.npy"
    S = np.load(store)
    raw = pd.read_csv(config.require_cache(cfg["raw"], cfg["raw_tmp"],
                                           what=f"{uni} raw panel"),
                      parse_dates=["date"])
    assert_columns(raw, REQUIRED_RAW, f"{uni} raw panel")
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True)
    bt = make_backtester(p)

    W("=" * 100)
    W(f" SEED NOISE FLOOR -- {cfg['label']} ({uni})")
    W("=" * 100)
    W("")
    W(f"  seeds fitted {len(SEEDS)} (first 10 = production set), one identical panel")
    W(f"  purge: CURRENT production. Only the seeds vary between sub-ensembles.")
    W("")
    prod = bt(np.nanmean(S[:, :10].astype(np.float64), axis=1), "invvol", "breadth")
    v34 = pd.read_csv(Path(cfg["md"]) / "v34_comparison.csv")
    r = v34[v34["Config"].astype(str).str.startswith("v2")].iloc[0]
    W("  BASELINE OFFSET -- STATED, NOT HIDDEN")
    W(f"    production 10 seeds from this store : CAGR {prod['CAGR%']:.2f}  "
      f"Sharpe {prod['Sharpe']:.2f}  MaxDD {prod['MaxDD%']:.2f}")
    W(f"    recorded in v34_comparison.csv      : CAGR {float(r['CAGR%']):.2f}  "
      f"Sharpe {float(r['Sharpe']):.2f}  MaxDD {float(r['MaxDD%']):.2f}")
    W(f"    offset                              : CAGR "
      f"{prod['CAGR%']-float(r['CAGR%']):+.2f}")
    W("    CAUSE: production scores the IN-MEMORY panel; this store was fitted on")
    W("    the panel read back from CSV, which differs by ONE UNIT IN THE LAST")
    W("    PLACE (max 4.441e-16, 2,638,259 cells). That is enough to change split")
    W("    decisions and flip near-tied ranks. IT IS NOT A SEED EFFECT.")
    W("    The spread below is unaffected: every sub-ensemble uses this one panel.")
    W("")

    rng = np.random.default_rng(20260902)
    rows, yearly = [], []
    for K in K_GRID:
        subs = ([list(range(len(SEEDS)))] if K == len(SEEDS)
                else [sorted(rng.choice(len(SEEDS), K, replace=False))
                      for _ in range(M_SUBSETS)])
        for si_, idxs in enumerate(subs):
            sv = np.nanmean(S[:, idxs].astype(np.float64), axis=1)
            for tag, sizing, mode in ARMS:
                m = bt(sv, sizing, mode)
                rows.append({"K": K, "subset": si_, "arm": tag, "CAGR%": m["CAGR%"],
                             "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"]})
                if K == 10:
                    for y, v in m["yearly"].items():
                        yearly.append({"subset": si_, "arm": tag, "year": y, "ret%": v})
        print(f"      [{uni}] K={K} done", flush=True)

    D = pd.DataFrame(rows); Y = pd.DataFrame(yearly)
    D.to_csv(Path(cfg["md"]) / "seed_noise_headline.csv", index=False)
    Y.to_csv(Path(cfg["md"]) / "seed_noise_yearly.csv", index=False)

    W("-" * 100)
    W(" 1. HEADLINE SPREAD AT K = 10 -- the ensemble size that ships")
    W("-" * 100)
    W(f" {'arm':<4}{'metric':<9}{'min':>9}{'p5':>9}{'median':>9}{'p95':>9}"
      f"{'max':>9}{'sd':>8}{'range':>9}")
    k10 = D[D["K"] == 10]
    for tag, _, _ in ARMS:
        for met in ("CAGR%", "Sharpe", "MaxDD%"):
            a = k10[k10["arm"] == tag][met].to_numpy()
            W(f" {tag:<4}{met:<9}{a.min():>9.2f}{np.percentile(a,5):>9.2f}"
              f"{np.median(a):>9.2f}{np.percentile(a,95):>9.2f}{a.max():>9.2f}"
              f"{a.std(ddof=1):>8.2f}{a.max()-a.min():>9.2f}")
    W("")
    W("-" * 100)
    W(" 2. DOES THE PURGE RESULT CLEAR THE MEASURED FLOOR?")
    W("-" * 100)
    H = pd.read_csv(Path(cfg["md"]) / "purge_fix_headline.csv")
    for tag, _, _ in ARMS:
        a = k10[k10["arm"] == tag]["CAGR%"].to_numpy()
        d = float(H[H["arm"] == tag]["dCAGR"].iloc[0])
        frac = float((np.abs(a - np.median(a)) >= abs(d)).mean())
        W(f"  {tag}: purge dCAGR {d:+.2f}   seed sd {a.std(ddof=1):.2f}   "
          f"seed range {a.max()-a.min():.2f}")
        W(f"      {frac*100:.0f}% of seed draws deviate from their own median by "
          f">= |{abs(d):.2f}|")
        W(f"      -> the purge delta is "
          f"{'INSIDE the seed-change spread' if frac > 0.05 else 'OUTSIDE the seed-change spread'}")
    W("")
    W("-" * 100)
    W(" 3. YEAR-LEVEL SPREAD ACROSS SEED SETS, at K = 10")
    W("-" * 100)
    W(f" {'arm':<4}{'year':<7}{'min':>9}{'median':>9}{'max':>9}{'range':>9}{'sd':>8}")
    for tag, _, _ in ARMS:
        for y in sorted(Y["year"].unique()):
            a = Y[(Y["arm"] == tag) & (Y["year"] == y)]["ret%"].to_numpy()
            if len(a) < 2:
                continue
            W(f" {tag:<4}{y:<7}{a.min():>9.2f}{np.median(a):>9.2f}{a.max():>9.2f}"
              f"{a.max()-a.min():>9.2f}{a.std(ddof=1):>8.2f}")
    W("")
    W("-" * 100)
    W(" 4. sigma(K) CURVE and 5. SEEDS NEEDED FOR +/-0.5 POINT STABILITY")
    W("-" * 100)
    sig = []
    for tag, _, _ in ARMS:
        W(f"  {tag}")
        W(f"    {'K':>4}{'sd(CAGR)':>11}{'range':>10}   note")
        for K in K_GRID:
            a = D[(D["K"] == K) & (D["arm"] == tag)]["CAGR%"].to_numpy()
            sd = a.std(ddof=1) if len(a) > 1 else float("nan")
            rg = (a.max() - a.min()) if len(a) > 1 else float("nan")
            note = ("single subset, no spread" if K == len(SEEDS)
                    else "subsets overlap, sd biased DOWN" if K >= 20 else "")
            sig.append({"arm": tag, "K": K, "sd": sd, "range": rg, "universe": uni})
            W(f"    {K:>4}{sd:>11.3f}{rg:>10.3f}   {note}")
        sub = [s for s in sig if s["arm"] == tag and s["K"] < 20 and s["sd"] == s["sd"]]
        alpha, logc = np.polyfit(np.log([s["K"] for s in sub]),
                                 np.log([s["sd"] for s in sub]), 1)
        c = float(np.exp(logc))
        need = (c / 0.5) ** (-1.0 / alpha) if alpha < 0 else float("nan")
        met = [s["K"] for s in sig if s["arm"] == tag and s["sd"] <= 0.5]
        W(f"    fitted sd(K) = {c:.3f} * K^({alpha:.3f})   (fit on K < 20)")
        if met:
            W(f"    smallest TESTED K with sd <= 0.5: {min(met)}")
        else:
            W(f"    NO TESTED K reaches sd <= 0.5.")
            W(f"    EXTRAPOLATED seeds needed: {need:.0f}  -- AN EXTRAPOLATION,")
            W(f"    not a measurement, and it assumes the fitted exponent holds.")
        W("")
    pd.DataFrame(sig).to_csv(Path(cfg["md"]) / "seed_noise_sigma_k.csv", index=False)


def main():
    out = []
    for uni, cfg in UNIVERSES.items():
        run(uni, cfg, out.append)
        out.append("")
    (ROOT / "diagnostics" / "seed_noise.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
