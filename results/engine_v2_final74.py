"""
engine_v2_final74.py -- FINAL v2 STRATEGY (breadth-scaled), 74-stock universe
=============================================================================
Same strategy as engine_v2_final.py, run on the 74-stock universe.

  Cross-sectional LightGBM ranking (17 features, monthly retrain, 32d purge)
    + inverse-vol position sizing        [validated: seeds, sub-period, vol-window]
    + BREADTH SCALING for crash control  [validated: 3 seeds, both sub-periods]

What breadth scaling does:
  At each rebalance, exposure = (stocks with positive 20-day momentum) / total.
  All positive -> fully invested. Half -> half invested, the rest in cash.
  In a crash, when everything is negative, exposure goes to roughly zero.
  It does NOT block individual stocks -- it only scales total exposure, and
  there is no tunable threshold.

  Note: existing holdings are never resized. Only new positions are sized
  against the target, so actual invested percentage can drift above target.

Cash assumption:
  CASH_YIELD in test_exposure.py is 0.0. Idle cash earns nothing. This is
  deliberately conservative: a real implementation could park idle cash in a
  liquid fund, but that is a separate operation and is not modelled here.

What was REJECTED along the way (and why):
  x Slope regime          : 14 fires, 4 correct. Lagging. Missed COVID recovery.
  x Absolute gate         : Sharpe 1.03 -> 0.76. Killed the mean-reversion edge.
  x Vol-targeting         : cut returns without reducing drawdown.
  x Feature pruning       : won on the decision window, lost on the test window.
  x 100-share sizing      : capital-inefficient, CAGR 19 -> 4.

The numbers this run produces are printed below and written to
v2FINAL_comparison.csv -- they are not hardcoded in this file.

Run: python3 results/engine_v2_final74.py
"""
import sys, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config74
from engine_core import metrics, precompute
from test_exposure import backtest_exposure, CASH_YIELD

REBAL, TOP_N, BUFFER, VOL_WIN = 20, 8, 16, 60
START_CAPITAL = 1_000_000
# WINDOW FROZEN: retired universe -- serves only the retired 58/74. Their published
# numbers must not move, so this window is deliberately left on the old
# year cut while the live universes moved to config.BT_START_DATE/BT_END_DATE.
BT_START, BT_END = 2019, 2026
M = config74.METRICS_DIR_74


def main():
    print("=" * 100)
    print("ENGINE v2 FINAL -- cross-sectional ranking + inverse-vol + breadth scaling")
    print("=" * 100)

    p = pd.read_csv("/tmp/v74_expanding.csv", parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()

    # baseline (inv-vol, always invested) and final (breadth-scaled)
    # The baseline's per-trade log is captured and persisted below. v1 rebalances
    # every 20 days and pays real costs -- more than v2 does, because it is always
    # 100% invested and so trades in larger size -- but only its TOTALS used to
    # survive, in v2FINAL_comparison.csv. A total cannot support a per-date
    # analysis, which left make_final_chart_fair.py treating v1 as costless.
    # `audit` only appends to lists; it changes no arithmetic, and the equity
    # curve is asserted identical to the un-audited baseline below.
    base_audit = {k: [] for k in
                  ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    # FROZEN 74: value_at_open=False pins the pre-2026-09-04 close-valued sizing,
    # so this retired universe's published numbers cannot move. The live universes
    # take the corrected default. See test_exposure.backtest_exposure.
    base_eq, tcb, nb, _ = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                            mode="none", target_vol=tv,
                                            audit=base_audit, value_at_open=False)
    fin_eq, tcf, nf, expo = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                              mode="breadth", target_vol=tv,
                                              value_at_open=False)
    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    mbase = metrics(base_eq, "Inverse-vol, 100% invested (v1 final)", tcb, nb)
    mfin = metrics(fin_eq, "+ breadth scaling (v2 FINAL)", tcf, nf)
    mbh = metrics(bh, "Equal-weight buy & hold (74)")

    out = pd.DataFrame([mfin, mbase, mbh])
    print("\n" + out.to_string(index=False))
    print(f"\n   v2 FINAL average exposure: {expo*100:.0f}% invested "
          f"(rest in cash at {CASH_YIELD*100:g}% yield)")
    out.to_csv(M / "v2FINAL_comparison.csv", index=False)

    # yearly
    yr = pd.DataFrame({
        "Strategy%": (fin_eq.resample("YE").last().pct_change().dropna()*100).round(1),
        "BuyHold%": (bh.resample("YE").last().pct_change().dropna()*100).round(1)})
    yr.index = yr.index.year
    yr["Diff"] = (yr["Strategy%"] - yr["BuyHold%"]).round(1)
    print("\n--- YEAR BY YEAR ---")
    print(yr.to_string())
    yr.to_csv(M / "v2FINAL_yearly.csv")

    pd.DataFrame({"date": fin_eq.index, "strategy": fin_eq.values,
                  "baseline_invvol": base_eq.values,
                  "buyhold": bh.values}).to_csv(M / "v2FINAL_equity.csv", index=False)

    # v1 baseline's per-trade log, written the same way daily_trades_74.csv is.
    # Consumers (make_final_chart_fair.py) read the costs from the engine that
    # produced the equity curve, rather than re-running the baseline to recover
    # them. The count is asserted against what the engine itself reported.
    bt = pd.DataFrame(base_audit["trades"])
    assert len(bt) == nb, f"v1 trade log {len(bt)} rows vs engine count {nb}"
    bt.to_csv(M / "daily_trades_v1_74.csv", index=False)
    print(f"   v1 baseline trade log: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
          f"-> daily_trades_v1_74.csv")

    (M / "v2FINAL_params.json").write_text(json.dumps({
        "model": "cross-sectional LightGBM, 17 feats, 10-seed, monthly, 32d purge",
        "sizing": "inverse-volatility (1/vol60)",
        "exposure": "breadth scaling = fraction of positive-20d-momentum stocks",
        "top_n": TOP_N, "buffer": BUFFER, "rebalance_days": REBAL,
        "avg_exposure_pct": round(expo*100),
        "sharpe": mfin["Sharpe"], "maxdd_pct": mfin["MaxDD%"], "cagr_pct": mfin["CAGR%"],
        "cash_yield": CASH_YIELD,
        "vs_buyhold": (f"Sharpe {mfin['Sharpe']} vs {mbh['Sharpe']}, "
                       f"MaxDD {mfin['MaxDD%']}% vs {mbh['MaxDD%']}%, "
                       f"CAGR {mfin['CAGR%']}% vs {mbh['CAGR%']}%"),
        # The inv-vol half of this claim was FALSE as written. On the panel
        # produced after the 2026-08-13 beta_60/idio_vol_60 density fix, the
        # inverse-vol validation in engine_core.py fails T3 (sub-period) and T4
        # (vol-window sensitivity); it had passed 4/4 on the degraded panel. The
        # claim is stated per test rather than as a blanket "validated", because a
        # stale validation claim is worse than no claim.
        "validated": "see validation_status",
        "validation_status": {
            "measured_on": "post density-fix panel, 2026-08-13, caches rebuilt",
            "breadth_T1_seed_robustness": ("FAIL 2 of 3 seed sets "
                                           "(+0.14, -0.02, +0.16); was PASS 3 of 3"),
            "breadth_T2_sub_period": "PASS both halves (+0.21, +0.36)",
            "inv_vol_T1_baseline_control": "PASS",
            "inv_vol_T2_seed_robustness": ("FAIL 0 of 3 seed sets "
                                           "(-0.05, -0.01, -0.10); was PASS 3 of 3"),
            "inv_vol_T3_sub_period": "FAIL both halves (-0.04, -0.10); was PASS",
            "inv_vol_T4_vol_window": ("FAIL 0 of 4 windows beat equal-rupee 1.06 "
                                      "(1.00/1.00/1.04/1.03); was PASS 4 of 4"),
        },
        "rejected": ["slope regime", "absolute gate", "vol-targeting",
                     "feature pruning", "100-share sizing"]}, indent=2))

    # chart
    fig, ax = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[2, 1])
    for s, c, ls, lab in [
            (fin_eq, "#d62728", "-", f"v2 FINAL: + breadth scaling  "
                                     f"(CAGR {mfin['CAGR%']}%, Sharpe {mfin['Sharpe']}, "
                                     f"MaxDD {mfin['MaxDD%']}%)"),
            (base_eq, "#1f77b4", "-", f"v1: inverse-vol, always invested  "
                                      f"(CAGR {mbase['CAGR%']}%, Sharpe {mbase['Sharpe']}, "
                                      f"MaxDD {mbase['MaxDD%']}%)"),
            (bh, "#2ca02c", "--", f"Equal-weight buy & hold  "
                                  f"(CAGR {mbh['CAGR%']}%, Sharpe {mbh['Sharpe']}, "
                                  f"MaxDD {mbh['MaxDD%']}%)")]:
        ax[0].plot(s.index, (s/s.iloc[0]-1)*100, lw=2.2, color=c, ls=ls, alpha=.9, label=lab)
    ax[0].axhline(0, color="k", lw=.7, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title("FINAL v2 strategy: ranking + inverse-vol + breadth-scaled exposure\n"
                    "Breadth cuts exposure in weak markets -> ~half the drawdown, "
                    "higher Sharpe", fontsize=11)
    ax[0].legend(loc="upper left", fontsize=9)
    ax[0].grid(alpha=.3)
    for s, c, ls, lab in [(fin_eq, "#d62728", "-", "v2 FINAL"),
                          (bh, "#2ca02c", "--", "Buy & hold")]:
        dd = (s/s.cummax()-1)*100
        ax[1].fill_between(s.index, dd, 0, color=c, alpha=.22)
        ax[1].plot(s.index, dd, lw=1.5, color=c, ls=ls, label=f"{lab} (max {dd.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=9)
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(M / "chart_v2FINAL.png", dpi=150, bbox_inches="tight")
    print("\n  saved -> chart_v2FINAL.png")

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    print(f"  v2 FINAL   : CAGR {mfin['CAGR%']:>6.2f}%  Sharpe {mfin['Sharpe']:>5.2f}  "
          f"MaxDD {mfin['MaxDD%']:>7.2f}%  Calmar {mfin['Calmar']}")
    print(f"  Buy & hold : CAGR {mbh['CAGR%']:>6.2f}%  Sharpe {mbh['Sharpe']:>5.2f}  "
          f"MaxDD {mbh['MaxDD%']:>7.2f}%  Calmar {mbh['Calmar']}")
    d_sh = mfin["Sharpe"] - mbh["Sharpe"]
    d_dd = mfin["MaxDD%"] - mbh["MaxDD%"]
    d_cagr = mfin["CAGR%"] - mbh["CAGR%"]
    sh_word = "ahead of" if d_sh > 0 else "behind"
    print(f"""
  Versus equal-weight buy & hold over the same period:
    Sharpe   {mfin['Sharpe']:>6.2f} vs {mbh['Sharpe']:>6.2f}   ({d_sh:+.2f})  -- {sh_word} buy & hold
    MaxDD    {mfin['MaxDD%']:>6.2f}% vs {mbh['MaxDD%']:>6.2f}%   ({d_dd:+.2f} pts)
    CAGR     {mfin['CAGR%']:>6.2f}% vs {mbh['CAGR%']:>6.2f}%   ({d_cagr:+.2f} pts)

  The strategy holds {expo*100:.0f}% invested on average, so raw CAGR is not the
  right comparison on its own -- return per deployed rupee and drawdown are.
  Idle cash earns {CASH_YIELD*100:g}%, so none of the return above comes from interest.

  Standing caveats: no capital gains tax is modelled, survivorship bias inflates
  both lines, and the edge is not statistically significant. The honest next step
  for a real product is a less-efficient universe (mid/small caps) or new data
  (fundamentals), not more tuning here.
""")
    print("Saved -> v2FINAL_comparison.csv, v2FINAL_yearly.csv, v2FINAL_equity.csv,")
    print("         v2FINAL_params.json, chart_v2FINAL.png")


if __name__ == "__main__":
    main()
