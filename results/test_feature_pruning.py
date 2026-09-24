"""
test_feature_pruning.py -- does removing harmful features actually improve results?

diagnose_decay.py (H3) showed this in the raw factor IC, independent of the model:
    Risk         +0.0037 -> +0.0377   10x better
    Liquidity    +0.0077 -> +0.0277   3.6x better
    Reversal     +0.0096 -> +0.0082   still works
    Momentum     -0.0081 -> -0.0104   inverted, in both periods
    TrendQuality -0.0153 -> -0.0088   inverted, in both periods

PROTOCOL (this is the entire point):
    DECIDE on 2019-2022 IC.  TEST on 2023-2026.
    The test half was not used in the decision. So if 2023-26 improves, that is
    genuine out-of-sample evidence rather than another round of fitting.

CONTROL: also test dropping 6 features at random. If a random drop improves things
just as much, the "harmful features" story is wrong.
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import config
from features_v2 import FEATS_V2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_core import backtest, metrics, precompute
from config import read_table  # the one CSV/parquet reader: config.read_table

HORIZON, PURGE = 20, 32
SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]
START_CAPITAL = 1_000_000
M = config.METRICS_DIR

MOMENTUM = ["mom_20", "mom_120", "mom_12_1"]
TRENDQ = ["trend_consistency_20", "path_smooth_60", "dist_high_252"]
DROP = MOMENTUM + TRENDQ
KEEP = [f for f in FEATS_V2 if f not in DROP]


def score_monthly(raw, feats, seeds, purge=PURGE):
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["score"] = np.nan
    p["ym"] = p["date"].dt.to_period("M")
    for ym in sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique()):
        cut = p.loc[p.ym == ym, "date"].min() - pd.Timedelta(days=purge)
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        te = p["ym"] == ym
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        pr = []
        for sd in seeds:
            m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, max_depth=6,
                                  num_leaves=48, subsample=0.8, colsample_bytree=0.8,
                                  min_child_samples=100, random_state=sd, verbose=-1)
            m.fit(p.loc[tr, feats], p.loc[tr, "y_rank"])
            pr.append(m.predict(p.loc[te, feats]))
        p.loc[te, "score"] = np.mean(pr, axis=0)
    return p.drop(columns=["ym"])


def evaluate(p, raw, label, y0, y1):
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    dd = px.index[(px.index.year >= y0) & (px.index.year <= y1)]
    pc = precompute(px)
    eq, tc, ntr, tl, ap = backtest(px, op, sc, dd, pc, sizing="invvol")
    m = metrics(eq, label, tc, ntr)
    pm = (p.merge(raw[["date", "symbol", "fwd_ret"]], on=["date", "symbol"], how="left")
          if "fwd_ret" not in p.columns else p)
    d = pm.dropna(subset=["score", "fwd_ret"])
    d = d[(d["date"].dt.year >= y0) & (d["date"].dt.year <= y1)]
    ic = d.groupby("date").apply(
        lambda g: spearmanr(g["score"], g["fwd_ret"]).correlation
        if len(g) >= 10 else np.nan).dropna()
    n_eff = len(ic) / HORIZON
    m["IC"] = round(ic.mean(), 4)
    m["IC_t"] = round(ic.mean() / (ic.std() / np.sqrt(n_eff)), 2) if ic.std() > 0 else 0
    return m, eq


def main():
    print("=" * 104)
    print("FEATURE PRUNING -- drop the families that predict BACKWARDS")
    print("=" * 104)
    print("\n  PROTOCOL:  DECIDE on 2019-2022.  TEST on 2023-2026.")
    print("  The test half did not inform the decision. That is what makes any")
    print("  improvement there real out-of-sample evidence, not more fitting.\n")
    print(f"  Dropping: {MOMENTUM + TRENDQ}")
    print(f"  Keeping {len(KEEP)}: {KEEP}\n")

    raw = read_table(f"/tmp/raw_panel_{HORIZON}.csv", parse_dates=["date"])
    raw = raw.sort_values(["symbol", "date"])
    if "fwd_ret" not in raw.columns:
        raw["fwd_ret"] = raw.groupby("symbol")["close"].shift(-HORIZON) / raw["close"] - 1

    rng = np.random.default_rng(0)
    rand_drop = list(rng.choice(FEATS_V2, size=6, replace=False))
    variants = {
        "ALL 17 features (current)": FEATS_V2,
        "PRUNED 11 (no momentum/trendq)": KEEP,
        "RANDOM drop 6 (control)": [f for f in FEATS_V2 if f not in rand_drop],
    }

    scored = {}
    for name, feats in variants.items():
        tag = name.split()[0].lower()
        cache = Path(f"/tmp/prune_{tag}.csv")
        if cache.exists():
            print(f"  loading cached: {name}")
            scored[name] = read_table(cache, parse_dates=["date"])
        else:
            print(f"  scoring: {name} ({len(feats)} features) ...", flush=True)
            ps = score_monthly(raw, feats, SEEDS)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
            scored[name] = ps

    print("\n" + "=" * 104)
    print("[1] DECISION WINDOW 2019-2022 (choice was made here -- improvement proves nothing)")
    print("=" * 104)
    rows = [evaluate(ps, raw, name, 2019, 2022)[0] for name, ps in scored.items()]
    d1 = pd.DataFrame(rows)[["Config", "CAGR%", "Sharpe", "MaxDD%", "Calmar", "IC", "IC_t"]]
    print(d1.to_string(index=False))

    print("\n" + "=" * 104)
    print("[2] TEST WINDOW 2023-2026  <-- THE REAL TEST")
    print("=" * 104)
    rows, curves = [], {}
    for name, ps in scored.items():
        m, eq = evaluate(ps, raw, name, 2023, 2026)
        rows.append(m); curves[name] = eq
    d2 = pd.DataFrame(rows)[["Config", "CAGR%", "Sharpe", "MaxDD%", "Calmar", "IC", "IC_t"]]
    px = scored["ALL 17 features (current)"].pivot_table(
        index="date", columns="symbol", values="close").ffill()
    hd = px.index[(px.index.year >= 2023) & (px.index.year <= 2026)]
    bh = START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
    mbh = metrics(bh, "Equal-weight buy & hold"); mbh["IC"] = np.nan; mbh["IC_t"] = np.nan
    d2 = pd.concat([d2, pd.DataFrame([mbh])[["Config", "CAGR%", "Sharpe", "MaxDD%",
                                             "Calmar", "IC", "IC_t"]]])
    print(d2.to_string(index=False))

    print("\n" + "=" * 104)
    print("[3] FULL PERIOD 2019-2026 (for the record)")
    print("=" * 104)
    rows = [evaluate(ps, raw, name, 2019, 2026)[0] for name, ps in scored.items()]
    d3 = pd.DataFrame(rows)[["Config", "CAGR%", "Sharpe", "MaxDD%", "Calmar", "IC", "IC_t"]]
    fd = px.index[(px.index.year >= 2019) & (px.index.year <= 2026)]
    bhf = START_CAPITAL * (1 + px.pct_change().loc[fd].mean(axis=1).fillna(0)).cumprod()
    mbf = metrics(bhf, "Equal-weight buy & hold"); mbf["IC"] = np.nan; mbf["IC_t"] = np.nan
    d3 = pd.concat([d3, pd.DataFrame([mbf])[["Config", "CAGR%", "Sharpe", "MaxDD%",
                                             "Calmar", "IC", "IC_t"]]])
    print(d3.to_string(index=False))

    d1.to_csv(M / "prune_decision_window.csv", index=False)
    d2.to_csv(M / "prune_test_window.csv", index=False)
    d3.to_csv(M / "prune_full_period.csv", index=False)

    print("\n" + "=" * 104)
    print("VERDICT")
    print("=" * 104)
    a = d2[d2.Config.str.startswith("ALL")].iloc[0]
    pr = d2[d2.Config.str.startswith("PRUNED")].iloc[0]
    rd = d2[d2.Config.str.startswith("RANDOM")].iloc[0]
    bhx = d2[d2.Config.str.startswith("Equal")].iloc[0]
    d_sh = pr["Sharpe"] - a["Sharpe"]
    d_ic = pr["IC"] - a["IC"]
    r_sh = rd["Sharpe"] - a["Sharpe"]

    print(f"\n  TEST window (2023-2026), which did not inform the decision:")
    print(f"    All 17 features : Sharpe {a['Sharpe']:>5.2f}  IC {a['IC']:+.4f}  CAGR {a['CAGR%']:>6.2f}%")
    print(f"    Pruned to 11    : Sharpe {pr['Sharpe']:>5.2f}  IC {pr['IC']:+.4f}  CAGR {pr['CAGR%']:>6.2f}%")
    print(f"    Random drop 6   : Sharpe {rd['Sharpe']:>5.2f}  IC {rd['IC']:+.4f}  CAGR {rd['CAGR%']:>6.2f}%  <- control")
    print(f"    Buy & hold      : Sharpe {bhx['Sharpe']:>5.2f}                  CAGR {bhx['CAGR%']:>6.2f}%")
    print(f"\n    Pruning effect  : Sharpe {d_sh:+.2f},  IC {d_ic:+.4f}")
    print(f"    Random effect   : Sharpe {r_sh:+.2f}   <- if similar, the story is wrong\n")

    if d_sh > 0.10 and d_sh > r_sh + 0.05:
        print("  -> PRUNING WORKS, and beats the random-drop control. Decision made on the")
        print("     first half, held up on the second. Genuine out-of-sample evidence.")
    elif d_sh > 0.10:
        print("  -> Pruning improved things, BUT so did dropping six features at random.")
        print("     The gain is from a simpler model, not from removing 'harmful' features.")
        print("     Describe it as regularisation, not factor selection.")
    elif abs(d_sh) <= 0.10:
        print("  -> No meaningful effect. Momentum/trend-quality had negative raw IC, but")
        print("     gradient boosting was evidently already discounting them. Keep all 17.")
    else:
        print("  -> Pruning HURT. The negative raw IC was misleading -- those features must")
        print("     carry information in interaction with others. Keep all 17.")

    print("\n  What this does and does not prove:")
    print("    One out-of-sample window of 3.5 years. The standard error on a Sharpe over")
    print("    that span was measured at +/- 0.66 earlier in this project. So a Sharpe gap")
    print("    below ~0.30 should not be treated as real, however tempting.")
    print("\nSaved -> prune_*.csv")


if __name__ == "__main__":
    main()
