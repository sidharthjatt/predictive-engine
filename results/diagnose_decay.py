"""
diagnose_decay.py -- why has the strategy stopped working after 2023?

T3 FAIL:
    2019-2022 : strategy Sharpe 1.24  |  buy&hold 1.05   -> jeet
    2023-2026 : strategy Sharpe 0.73  |  buy&hold 1.15   -> HAAR

TEEN HYPOTHESES + EK CONTROL:
  H0. Is the gap even statistically real? (check this first)
  H1. SIGNAL DECAY -- has the model's edge been arbitraged away?
  H2. VOL DISPERSION -- is there anything left for inverse-vol to work with?
  H3. FACTOR ROTATION -- which factors still predict?
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import config
from features_v2 import FEATS_V2

HORIZON = 20
M = config.METRICS_DIR


def main():
    print("=" * 100)
    print("WHY DID THE STRATEGY STOP WORKING AFTER 2023?")
    print("=" * 100)

    p = pd.read_csv("/tmp/v5_expanding.csv", parse_dates=["date"])
    raw = pd.read_csv(f"/tmp/raw_panel_{HORIZON}.csv", parse_dates=["date"])
    raw = raw.sort_values(["symbol", "date"])
    if "fwd_ret" not in raw.columns:
        raw["fwd_ret"] = raw.groupby("symbol")["close"].shift(-HORIZON) / raw["close"] - 1
    if "fwd_ret" not in p.columns:
        p = p.merge(raw[["date", "symbol", "fwd_ret"]], on=["date", "symbol"], how="left")

    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()

    print("\n[H0] IS THE GAP EVEN STATISTICALLY REAL?")
    print("     Before explaining a difference, check it isn't noise.\n")
    eqdf = pd.read_csv(M / "FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    for name, y0, y1 in [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]:
        m = (eqdf.index.year >= y0) & (eqdf.index.year <= y1)
        rs = eqdf.loc[m, "strategy"].pct_change().dropna()
        rb = eqdf.loc[m, "buyhold"].pct_change().dropna()
        diff = rs - rb
        n = len(diff); yrs = n / 252
        t = diff.mean() / (diff.std() / np.sqrt(n)) if diff.std() > 0 else 0
        ann_excess = diff.mean() * 252 * 100
        sr_s = rs.mean() / rs.std() * np.sqrt(252)
        sr_b = rb.mean() / rb.std() * np.sqrt(252)
        se_sr = np.sqrt((1 + 0.5 * sr_s ** 2) / yrs)
        print(f"     {name} ({yrs:.1f} yrs):")
        print(f"        Sharpe   strategy {sr_s:.2f}  vs  buy&hold {sr_b:.2f}   (gap {sr_s-sr_b:+.2f})")
        print(f"        Std error on a Sharpe over {yrs:.1f} yrs = +/- {se_sr:.2f}")
        print(f"        Annualised excess {ann_excess:+.2f}%,  t-stat {t:+.2f}  "
              f"-> {'SIGNIFICANT' if abs(t) > 2 else 'NOT significant'}\n")
    print("     If the standard error on a Sharpe exceeds the gap, the 2023-26 'failure'")
    print("     may just be noise. Don't build a story on an insignificant difference.")

    print("\n" + "=" * 100)
    print("[H1] SIGNAL DECAY -- did the model's edge disappear?")
    print("=" * 100)
    d = p.dropna(subset=["score", "fwd_ret"])
    d = d[d["date"].dt.year >= 2019]
    ic = d.groupby("date").apply(
        lambda g: spearmanr(g["score"], g["fwd_ret"]).correlation
        if len(g) >= 10 else np.nan).dropna()
    icy = ic.groupby(ic.index.year).agg(["mean", "std", "count"])
    icy["t"] = icy["mean"] / (icy["std"] / np.sqrt(icy["count"] / HORIZON))
    print(f"\n     {'Year':<6} {'IC':>9} {'t-stat':>8}")
    for y, r in icy.iterrows():
        bar = "#" * max(0, int(r["mean"] * 500))
        neg = "-" * max(0, int(-r["mean"] * 500))
        print(f"     {y:<6} {r['mean']:>+9.4f} {r['t']:>8.2f}   {bar}{neg}")
    ic_early = ic[(ic.index.year >= 2019) & (ic.index.year <= 2022)].mean()
    ic_late = ic[ic.index.year >= 2023].mean()
    print(f"\n     IC 2019-2022 : {ic_early:+.4f}")
    print(f"     IC 2023-2026 : {ic_late:+.4f}")
    if ic_late < ic_early * 0.5:
        print("     -> Signal decayed substantially. H1 SUPPORTED.")
    elif ic_late < ic_early:
        print("     -> Signal weaker but not gone. H1 PARTIALLY supported.")
    else:
        print("     -> Signal has NOT decayed. H1 REJECTED -- the underperformance is not")
        print("        coming from the model. Look at sizing/portfolio instead.")

    print("\n" + "=" * 100)
    print("[H2] VOL DISPERSION -- does inverse-vol still have anything to work with?")
    print("=" * 100)
    print("     Inv-vol only helps when stocks have DIFFERENT vols. If all vols converge,")
    print("     inv-vol collapses to equal-weight and adds nothing.\n")
    vol = px.pct_change().rolling(60).std() * np.sqrt(252)
    disp = (vol.std(axis=1) / vol.mean(axis=1))
    disp = disp[disp.index.year >= 2019].dropna()
    dy = disp.groupby(disp.index.year).mean()
    vsub = vol[vol.index.year >= 2019]
    vy = vsub.mean(axis=1).groupby(vsub.index.year).mean()
    print(f"     {'Year':<6} {'Avg vol':>9} {'Dispersion':>12}")
    for y in dy.index:
        bar = "#" * int(dy[y] * 100)
        print(f"     {y:<6} {vy[y]*100:>8.1f}% {dy[y]:>11.3f}   {bar}")
    d_early = dy[(dy.index >= 2019) & (dy.index <= 2022)].mean()
    d_late = dy[dy.index >= 2023].mean()
    print(f"\n     Dispersion 2019-2022 : {d_early:.3f}")
    print(f"     Dispersion 2023-2026 : {d_late:.3f}   ({(d_late/d_early-1)*100:+.1f}%)")
    if d_late < d_early * 0.85:
        print("     -> Dispersion collapsed. Inv-vol has less to exploit. H2 SUPPORTED.")
    else:
        print("     -> Dispersion broadly unchanged. H2 REJECTED.")

    print("\n" + "=" * 100)
    print("[H3] FACTOR ROTATION -- which raw factors still predict?")
    print("=" * 100)
    print("     IC of each feature family directly vs forward returns (bypasses the model).\n")
    fam = {
        "Momentum": ["mom_20", "mom_120", "mom_12_1"],
        "Reversal": ["rev_5", "rev_1"],
        "Risk": ["vol_20", "vol_ratio", "beta_60", "idio_vol_60", "downside_vol_60"],
        "Liquidity": ["amihud_20", "turnover_z", "vol_price_div"],
        "TrendQuality": ["trend_consistency_20", "path_smooth_60", "dist_high_252"],
    }
    rawd = raw.dropna(subset=["fwd_ret"])
    rawd = rawd[rawd["date"].dt.year >= 2019]
    rows = []
    for fname, feats in fam.items():
        for period, y0, y1 in [("2019-22", 2019, 2022), ("2023-26", 2023, 2026)]:
            sub = rawd[(rawd["date"].dt.year >= y0) & (rawd["date"].dt.year <= y1)]
            ics = []
            for f in feats:
                if f not in sub.columns:
                    continue
                g = sub.dropna(subset=[f])
                if len(g) < 1000:
                    continue
                daily = g.groupby("date").apply(
                    lambda x: spearmanr(x[f], x["fwd_ret"]).correlation
                    if len(x) >= 10 else np.nan).dropna()
                ics.append(daily.mean())
            if ics:
                rows.append({"family": fname, "period": period, "mean_IC": round(np.mean(ics), 4)})
    fdf = pd.DataFrame(rows).pivot(index="family", columns="period", values="mean_IC")
    fdf["change"] = (fdf["2023-26"] - fdf["2019-22"]).round(4)
    fdf["still_works"] = fdf["2023-26"].abs() > 0.01
    print(fdf.to_string())
    fdf.to_csv(M / "decay_factor_ic.csv")
    alive = fdf[fdf["still_works"]].index.tolist()
    dead = fdf[~fdf["still_works"]].index.tolist()
    print(f"\n     Still predictive in 2023-26 : {alive if alive else 'NONE'}")
    print(f"     Dead in 2023-26             : {dead if dead else 'none'}")

    fig, ax = plt.subplots(3, 1, figsize=(13, 12))
    icm = ic.resample("QE").mean()
    ax[0].bar(icm.index, icm.values, width=70,
              color=["#2ca02c" if v > 0 else "#d62728" for v in icm.values], alpha=.8)
    ax[0].axhline(0, color="k", lw=1)
    ax[0].axvline(pd.Timestamp("2023-01-01"), color="k", ls="--", lw=1.5)
    ax[0].set_ylabel("Rank IC (quarterly)")
    ax[0].set_title(f"H1: Has the signal decayed?   IC 2019-22 = {ic_early:+.4f}  |  "
                    f"IC 2023-26 = {ic_late:+.4f}", fontsize=11)
    ax[0].grid(alpha=.3)

    dq = disp.resample("QE").mean()
    ax[1].plot(dq.index, dq.values, lw=2, color="#1f77b4")
    ax[1].axvline(pd.Timestamp("2023-01-01"), color="k", ls="--", lw=1.5)
    ax[1].axhline(d_early, color="#2ca02c", ls=":", lw=1.5, label=f"2019-22 = {d_early:.3f}")
    ax[1].axhline(d_late, color="#d62728", ls=":", lw=1.5, label=f"2023-26 = {d_late:.3f}")
    ax[1].set_ylabel("Vol dispersion")
    ax[1].set_title("H2: Is there still vol dispersion for inverse-vol to exploit?", fontsize=11)
    ax[1].legend(fontsize=9)
    ax[1].grid(alpha=.3)

    x = np.arange(len(fdf))
    ax[2].bar(x - 0.2, fdf["2019-22"], 0.4, label="2019-22", color="#2ca02c", alpha=.85)
    ax[2].bar(x + 0.2, fdf["2023-26"], 0.4, label="2023-26", color="#d62728", alpha=.85)
    ax[2].axhline(0, color="k", lw=1)
    ax[2].set_xticks(x); ax[2].set_xticklabels(fdf.index, fontsize=9)
    ax[2].set_ylabel("Mean rank IC")
    ax[2].set_title("H3: Which factor families still predict?", fontsize=11)
    ax[2].legend(fontsize=9); ax[2].grid(axis="y", alpha=.3)
    plt.tight_layout()
    plt.savefig(M / "chart_decay.png", dpi=150, bbox_inches="tight")
    print("\n  saved -> chart_decay.png")

    print("\n" + "=" * 100)
    print("WHAT TO DO ABOUT IT")
    print("=" * 100)
    print("  1. REPORT IT. Full-period numbers beat buy & hold, but that comes entirely")
    print("     from 2019-2022. Say so. A result that works in half your sample is a")
    print("     finding, not a failure -- provided you report it.")
    print()
    print("  2. DO NOT 'FIX' IT BY TUNING. The temptation now is to add a filter or")
    print("     re-weight features until 2023-26 looks better. That is fitting to the")
    print("     second half -- exactly the mistake this project has spent weeks avoiding.")
    print()
    print("  3. If IC is still positive in 2023-26, the strategy hasn't broken -- it has")
    print("     had a bad stretch. Every strategy does. 3.5 years settles nothing.")
    print()
    print("  4. If IC has gone to zero, the honest conclusion is that price/volume features")
    print("     no longer extract alpha from NIFTY-50, and the answer is NEW DATA, not new")
    print("     parameters.")
    print("\nSaved -> decay_factor_ic.csv, chart_decay.png")


if __name__ == "__main__":
    main()
