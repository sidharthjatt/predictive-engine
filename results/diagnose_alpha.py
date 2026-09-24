"""
diagnose_alpha.py -- does the model have any alpha at all?
===========================================================
This has to be checked before any portfolio tuning. If the model's signal is weak,
no amount of tuning N, the buffer or the regime rule will help.

3 tests:
  1. RANK IC (Spearman): score against realised forward return, each day, averaged.
     The quant industry standard. IC above 0.03 is usable, above 0.05 is good.
     IR = mean(IC)/std(IC) measures how consistent it is.

  2. DECILE SPREAD: each day, sort stocks into 10 buckets by score.
     Take the top decile's average forward return minus the bottom decile's.
     It should be monotonic (D10 > D9 > ... > D1). If it looks random, there is
     no alpha.

  3. TC DRAG: how much of the gross return transaction costs consume.
     If gross alpha is smaller than TC, the strategy is structurally dead.

Run: python3 results/diagnose_alpha.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config
from numerics import rolling_std  # platform-identical variance: results/numerics.py

UNIVERSE_DIR = config.RAW_DATA_DIR / "nifty50"
FWD_H = 20
SEED_ENSEMBLE = [7, 42, 99]
SCORE_FROM = 2016

FEATS = ["ret_1d", "mom_5", "mom_10", "mom_20", "mom_60", "mom_120",
         "vol_20", "vol_60", "rsi_14", "ma_ratio_20_50", "ma_ratio_50_200",
         "dist_high_60", "dist_low_60", "vol_z_20", "range_20", "mom_20_lag20"]


def build_stock_frame(path):
    df = config.read_price_csv(path).sort_values("date")
    df = df[["date", "open", "close", "volume"]].dropna()
    c = df["close"]
    df["ret_1d"] = c.pct_change()
    for w in [5, 10, 20, 60, 120]:
        df[f"mom_{w}"] = c / c.shift(w) - 1
    df["mom_20_lag20"] = df["mom_20"].shift(20)
    df["vol_20"] = rolling_std(df["ret_1d"], 20)
    df["vol_60"] = rolling_std(df["ret_1d"], 60)
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi_14"] = 100 - 100 / (1 + up / (dn + 1e-9))
    df["ma_ratio_20_50"] = c.rolling(20).mean() / c.rolling(50).mean()
    df["ma_ratio_50_200"] = c.rolling(50).mean() / c.rolling(200).mean()
    df["dist_high_60"] = c / c.rolling(60).max() - 1
    df["dist_low_60"] = c / c.rolling(60).min() - 1
    vm = df["volume"].rolling(20).mean()
    vs = rolling_std(df["volume"], 20)
    df["vol_z_20"] = (df["volume"] - vm) / (vs + 1e-9)
    df["range_20"] = (c.rolling(20).max() - c.rolling(20).min()) / c
    df["fwd_ret"] = c.shift(-FWD_H) / c - 1
    return df


def build_panel():
    frames = []
    for f in sorted(UNIVERSE_DIR.glob("*.csv")):
        d = build_stock_frame(f)
        d["symbol"] = f.stem
        frames.append(d)
    p = pd.concat(frames, ignore_index=True)
    p = p.dropna(subset=FEATS)
    p["year"] = p["date"].dt.year
    p["y_rank"] = p.groupby("date")["fwd_ret"].rank(pct=True)
    return p


def walk_forward_scores(panel):
    panel = panel.sort_values(["date", "symbol"]).reset_index(drop=True)
    panel["score"] = np.nan
    for yr in range(SCORE_FROM, int(panel["year"].max()) + 1):
        tr = (panel["year"] < yr) & panel["y_rank"].notna()
        te = panel["year"] == yr
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        preds = []
        for sd in SEED_ENSEMBLE:
            m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, max_depth=6,
                                  num_leaves=48, subsample=0.8, colsample_bytree=0.8,
                                  min_child_samples=100, random_state=sd, verbose=-1)
            m.fit(panel.loc[tr, FEATS], panel.loc[tr, "y_rank"])
            preds.append(m.predict(panel.loc[te, FEATS]))
        panel.loc[te, "score"] = np.mean(preds, axis=0)
    return panel


def main():
    print("=" * 88)
    print("ALPHA DIAGNOSTIC -- does the model really carry a signal?")
    print("=" * 88)

    panel = build_panel()
    panel = walk_forward_scores(panel)
    d = panel.dropna(subset=["score", "fwd_ret"]).copy()
    d = d[d.year >= SCORE_FROM]

    # ---------------------------------------------------------- 1. RANK IC
    print("\n[1] RANK IC (Spearman correlation: score vs actual 20d fwd return)")
    print("    Benchmark: IC 0.02 = weak | 0.03-0.05 = usable | >0.05 = strong\n")

    def day_ic(g):
        if len(g) < 10:
            return np.nan
        return spearmanr(g["score"], g["fwd_ret"]).correlation

    ic = d.groupby("date").apply(day_ic).dropna()
    ic_mean, ic_std = ic.mean(), ic.std()
    ir = ic_mean / ic_std if ic_std > 0 else 0
    hit = (ic > 0).mean()
    # t-stat with Newey-West-ish haircut: overlapping 20d windows -> effective N /20
    n_eff = len(ic) / FWD_H
    tstat = ic_mean / (ic_std / np.sqrt(n_eff)) if ic_std > 0 else 0

    print(f"    Mean IC      : {ic_mean:+.4f}")
    print(f"    Std  IC      : {ic_std:.4f}")
    print(f"    IR (IC/std)  : {ir:+.3f}")
    print(f"    Hit rate     : {hit*100:.1f}% of days IC > 0")
    print(f"    t-stat       : {tstat:+.2f}  (overlap-adjusted, n_eff={n_eff:.0f})")
    print(f"    -> {'SIGNIFICANT' if abs(tstat) > 2 else 'NOT significant'} at 5%")

    # by year: is the signal decaying?
    print("\n    IC by year (decay check):")
    icy = ic.groupby(ic.index.year).mean()
    for y, v in icy.items():
        bar = "#" * max(0, int(v * 400))
        print(f"      {y}: {v:+.4f}  {bar}")

    # dev vs backtest
    ic_dev = ic[(ic.index.year >= 2016) & (ic.index.year <= 2018)].mean()
    ic_bt = ic[ic.index.year >= 2019].mean()
    print(f"\n    IC on DEV (2016-18)      : {ic_dev:+.4f}")
    print(f"    IC on BACKTEST (2019-26) : {ic_bt:+.4f}")
    if ic_bt < ic_dev * 0.5:
        print("    !! Signal decayed badly out of sample")

    # ------------------------------------------------------ 2. DECILE SPREAD
    print("\n[2] DECILE SPREAD (top vs bottom decile forward returns)")
    print("    This should be monotonic. A zigzag means the model is random.\n")
    d["decile"] = d.groupby("date")["score"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 10, labels=False, duplicates="drop") + 1)
    dec = d.groupby("decile")["fwd_ret"].agg(["mean", "count"])
    dec["mean_pct"] = (dec["mean"] * 100).round(3)
    for dd, r in dec.iterrows():
        bar = "#" * max(0, int(r["mean"] * 800))
        print(f"    D{int(dd):>2}: {r['mean_pct']:>+7.3f}%  (n={int(r['count']):>6,})  {bar}")
    spread = (dec.loc[10, "mean"] - dec.loc[1, "mean"]) * 100
    print(f"\n    D10 - D1 spread: {spread:+.3f}% per 20 days")
    print(f"    Annualized    : {spread * 12.6:+.2f}%  (12.6 non-overlapping 20d periods/yr)")

    # is the top decile actually the best, or is something in the middle better?
    monotone = dec["mean"].is_monotonic_increasing
    print(f"    Monotonic     : {monotone}")

    # top-8 out of ~55 = roughly top 15% -> compare vs universe mean
    uni_mean = d["fwd_ret"].mean() * 100
    top_dec = dec.loc[10, "mean"] * 100
    print(f"\n    Universe avg 20d fwd ret : {uni_mean:+.3f}%")
    print(f"    Top-decile avg           : {top_dec:+.3f}%")
    print(f"    GROSS EDGE (top - avg)   : {top_dec - uni_mean:+.3f}% per 20d")
    print(f"    -> annualized gross edge : {(top_dec - uni_mean) * 12.6:+.2f}%")

    # -------------------------------------------------------- 3. TC DRAG
    print("\n[3] TC DRAG -- is the edge larger than the cost?")
    print("    Zerodha delivery: ~0.12% buy + ~0.10% sell = ~0.22% round trip")
    print("    Plus slippage 0.15% each way = 0.30%")
    print("    TOTAL round trip cost ~= 0.52% of position value\n")

    rt_cost = 0.52
    # ~26 rebalances/yr, avg hold 32d -> position turns over ~7.9x/yr
    # but only ~3-4 of 8 positions change each rebalance
    turns_per_yr = 252 / 32
    annual_cost = rt_cost * turns_per_yr
    gross_ann = (top_dec - uni_mean) * 12.6
    print(f"    Position turnover     : ~{turns_per_yr:.1f}x per year (32d avg hold)")
    print(f"    Annual cost drag      : {annual_cost:.2f}%")
    print(f"    Annual gross edge     : {gross_ann:+.2f}%")
    print(f"    NET EDGE              : {gross_ann - annual_cost:+.2f}%")
    if gross_ann < annual_cost:
        print("\n    !! STRUCTURAL PROBLEM: cost > edge. Strategy cannot win as-is.")
        print("       Fix options: (a) longer holds  (b) fewer trades  (c) better signal")
    else:
        print(f"\n    OK: edge survives cost with {gross_ann - annual_cost:.2f}% to spare")

    # ------------------------------------------------- save
    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": ic.index, "ic": ic.values}).to_csv(
        config.METRICS_DIR / "diag_daily_ic.csv", index=False)
    dec.to_csv(config.METRICS_DIR / "diag_deciles.csv")
    print("\nSaved -> diag_daily_ic.csv, diag_deciles.csv")


if __name__ == "__main__":
    main()
