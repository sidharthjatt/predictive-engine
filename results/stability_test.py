"""
stability_test.py -- can dev selection be trusted at all?
Sandbox (2 seeds) ne chuna H=40 rb=10 N=15 -> backtest Sharpe 1.33
Mac     (3 seeds) ne chuna H=20 rb=20 N=12 -> backtest Sharpe 0.63
Changing only the seed flipped the result. So is dev selection just noise?
This script runs every config across 5 seed sets and checks which one is consistent.
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import config
from features_v2 import FEATS_V2
from engine_v2 import backtest, metrics, build_panel

DEV_START, DEV_END = 2016, 2018
SEED_SETS = [[7, 42, 99], [1, 2, 3], [11, 22, 33], [101, 202, 303], [5, 55, 555]]


def score_with_seeds(panel, horizon, seeds):
    p = panel.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["score"] = np.nan
    for yr in range(2016, DEV_END + 1):
        tr = (p["year"] < yr) & p["y_rank"].notna()
        if tr.sum() == 0:
            continue
        cut = p.loc[p["year"] < yr, "date"].max() - pd.Timedelta(days=horizon * 1.6)
        tr = tr & (p["date"] <= cut)
        te = p["year"] == yr
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        pr = []
        for sd in seeds:
            m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, max_depth=6,
                                  num_leaves=48, subsample=0.8, colsample_bytree=0.8,
                                  min_child_samples=100, random_state=sd, verbose=-1)
            m.fit(p.loc[tr, FEATS_V2], p.loc[tr, "y_rank"])
            pr.append(m.predict(p.loc[te, FEATS_V2]))
        p.loc[te, "score"] = np.mean(pr, axis=0)
    return p


def main():
    print("=" * 96)
    print("STABILITY TEST -- is any config genuinely best on dev, or is it all noise?")
    print("=" * 96)

    raw = {}
    for h in [20, 40, 60]:
        cache = Path(f"/tmp/raw_panel_{h}.csv")
        if cache.exists():
            raw[h] = pd.read_csv(cache, parse_dates=["date"])
            print(f"  loaded raw panel h={h}")
        else:
            print(f"  building raw panel h={h} ...", flush=True)
            p = build_panel(h)
            keep = ["date", "symbol", "open", "close", "year", "y_rank"] + FEATS_V2
            p[keep].to_csv(cache, index=False)
            raw[h] = p[keep]

    CONFIGS = [(h, rb, n) for h in [20, 40, 60] for rb in [10, 20] for n in [8, 12, 15]]

    rows = []
    for si, seeds in enumerate(SEED_SETS):
        print(f"\n--- seed set {si+1}/{len(SEED_SETS)}: {seeds} ---", flush=True)
        scored = {h: score_with_seeds(raw[h], h, seeds) for h in [20, 40, 60]}
        for (h, rb, n) in CONFIGS:
            p = scored[h]
            px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
            op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
            sc = p.pivot_table(index="date", columns="symbol", values="score")
            dd = px.index[(px.index.year >= DEV_START) & (px.index.year <= DEV_END)]
            eq, tc, ntr, tl, _ = backtest(px, op, sc, dd, n, 2 * n, rb)
            m = metrics(eq, "", tc, ntr)
            rows.append({"seedset": si, "cfg": f"H{h}_rb{rb}_N{n}",
                         "devSharpe": m["Sharpe"], "devCAGR": m["CAGR%"],
                         "devMaxDD": m["MaxDD%"]})
        print(f"    done ({len(CONFIGS)} configs)", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(config.METRICS_DIR / "stability_raw.csv", index=False)

    print("\n" + "=" * 96)
    print("DEV SHARPE ACROSS 5 SEED SETS")
    print("=" * 96)
    agg = df.groupby("cfg").agg(
        mean_Sharpe=("devSharpe", "mean"), std_Sharpe=("devSharpe", "std"),
        min_Sharpe=("devSharpe", "min"), max_Sharpe=("devSharpe", "max"),
        mean_CAGR=("devCAGR", "mean"), std_CAGR=("devCAGR", "std"),
    ).round(2).sort_values("mean_Sharpe", ascending=False)
    agg["range"] = (agg.max_Sharpe - agg.min_Sharpe).round(2)
    print(agg.to_string())
    agg.to_csv(config.METRICS_DIR / "stability_summary.csv")

    print("\n" + "=" * 96)
    print("WHICH CONFIG WINS ON EACH SEED SET?")
    print("=" * 96)
    wins = df.loc[df.groupby("seedset")["devSharpe"].idxmax()]
    for _, r in wins.iterrows():
        print(f"    seedset {r.seedset}: winner = {r.cfg:<16} (Sharpe {r.devSharpe})")
    n_unique = wins.cfg.nunique()
    print(f"\n    {n_unique} DIFFERENT winners across {len(SEED_SETS)} seed sets.")

    print("\n" + "=" * 96)
    print("VERDICT")
    print("=" * 96)
    best, best_mean = agg.index[0], agg.iloc[0].mean_Sharpe
    gap = best_mean - agg.iloc[1].mean_Sharpe
    noise = agg.std_Sharpe.mean()
    print(f"    Best avg config : {best} (Sharpe {best_mean} +/- {agg.iloc[0].std_Sharpe})")
    print(f"    Gap to 2nd      : {gap:.2f}")
    print(f"    Typical noise   : {noise:.2f}")
    if n_unique >= 3 or gap < noise:
        print("\n    -> DEV SELECTION IS NOT RELIABLE. Different seeds -> different winners,")
        print("       and config-to-config gap is smaller than seed-to-seed noise.")
        print("       ACTION: do not select on dev. Fix config a priori, or ensemble.")
    else:
        print(f"\n    -> {best} is stably best (gap {gap:.2f} > noise {noise:.2f}).")


if __name__ == "__main__":
    main()
