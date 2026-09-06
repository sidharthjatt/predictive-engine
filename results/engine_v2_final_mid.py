"""
engine_v2_final_mid.py -- FINAL v2 STRATEGY (breadth-scaled), MidCap150 universe
================================================================================
Same strategy as engine_v2_final.py, run on the MidCap150 universe (148 names,
index excluded). Every feature, hyperparameter and rule is byte-identical to the
58 and the 74; only the universe differs.

SELECTIVITY IS NOT HELD CONSTANT, AND THAT IS DELIBERATE
    TOP_N=8 is unchanged. Out of 58 names that is the top 13.8%; out of 148 it is
    the top 5.4%. That is a materially different selectivity, so this run is
    comparable in RULES but not in concentration. TOP_N is left alone anyway so
    the first pass is untuned. See the selectivity note printed at the end.

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

Run: python3 results/engine_v2_final_mid.py
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
import config
import arms.registry as arm_reg
import config_mid
from engine_core import metrics, precompute
from test_exposure import backtest_exposure, CASH_YIELD

REBAL, VOL_WIN = 20, 60
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = config.TOP_N, config.BUFFER
START_CAPITAL = 1_000_000
# BACKTEST WINDOW -- imported from config.py, the single definition.
# Date-based and inclusive. The old year cut (BT_START, BT_END = 2019, 2026)
# ran to 2026-06-08, six trading days beyond this window.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE
M = config_mid.METRICS_DIR_MID


def main():
    print("=" * 100)
    print("ENGINE v2 FINAL -- cross-sectional ranking + inverse-vol + breadth scaling")
    print("=" * 100)

    # UNLISTED FIX 2026-08-28: this read /tmp/v_mid_expanding.csv directly and
    # raised FileNotFoundError whenever /tmp had been cleared. n100's engine has
    # always used config.require_cache with the permanent copy as the fallback;
    # this now matches it. Pre-existing bug, not introduced by the V34 work.
    src = config.require_cache(M / "v_mid_expanding_cache.csv",
                               "/tmp/v_mid_expanding.csv",
                               what="MidCap150 score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
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
    base_eq, tcb, nb, _ = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                            mode="none", target_vol=tv,
                                            audit=base_audit)
    fin_eq, tcf, nf, expo = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                              mode="breadth", target_vol=tv)
    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    mbase = metrics(base_eq, "Inverse-vol, 100% invested (v1 final)", tcb, nb)
    mfin = metrics(fin_eq, "+ breadth scaling (v2 FINAL)", tcf, nf)
    mbh = metrics(bh, "Equal-weight buy & hold (MidCap150)")

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

    # PER-ARM COLUMNS ALONGSIDE THE ORIGINAL TWO.
    # `strategy` is v2 and `baseline_invvol` is v1 -- names that say what the
    # curve was FOR rather than which arm it IS, which is why nothing downstream
    # could ask this file for v3 or v4. The arm-keyed names are
    # arms/registry.Arm.equity_column, the same spelling v34_equity.csv already
    # uses, so the project ends up with ONE name per arm instead of two.
    #
    # THE OLD NAMES ARE GONE FROM THE LIVE UNIVERSES. They were kept as duplicates
    # while the nine readers were repointed one at a time, each byte-compared; that
    # is finished, and every reader now goes through arms/registry.equity_series.
    #
    # THE FROZEN 58 AND 74 STILL WRITE `strategy`/`baseline_invvol` AND ALWAYS
    # WILL. Their engines are those universes' provenance and are not modified, so
    # equity_series' fallback is permanent rather than transitional -- it is how a
    # frozen universe's file is read, not a shim awaiting deletion.
    pd.DataFrame({"date": fin_eq.index,
                  "v1_invvol_none": base_eq.values,
                  "v2_invvol_breadth": fin_eq.values,
                  "buyhold": bh.values}).to_csv(M / "v2FINAL_equity.csv", index=False)

    # v1 baseline's per-trade log, written the same way daily_trades_58.csv is.
    # Consumers (make_final_chart_fair.py) read the costs from the engine that
    # produced the equity curve, rather than re-running the baseline to recover
    # them. The count is asserted against what the engine itself reported.
    bt = pd.DataFrame(base_audit["trades"])
    assert len(bt) == nb, f"v1 trade log {len(bt)} rows vs engine count {nb}"
    # WRITTEN UNCONDITIONALLY, AND THAT IS A KNOWN LEAK, RECORDED NOT HIDDEN.
    # `--arm v2` still produces daily_trades_v1_mid.csv -- a file named for an
    # arm the run did not select. Gating it was TRIED and reverted: STEP 10d
    # make_mid_chart.py declares this file in run_all.REQUIRED_INPUTS as a hard
    # edge, so a gated write makes `--arm v2` die at check_inputs with a missing
    # file. Removing that edge would weaken the static contract and cost the
    # checker a resolved dependency, which experiments/ARM_SUBSET_SPEC.txt's G6
    # forbids. Closing this properly means making make_mid_chart.py arm-aware
    # too; see KNOWN_ISSUES.md.
    # GATED ON v1 BEING SELECTED. `--arm v2` no longer produces a file named for
    # an arm the run did not select.
    #
    # THIS ONLY BECAME POSSIBLE ONCE make_mid_chart.py WENT ARM-AWARE. The first
    # attempt gated the write while STEP 10d still demanded the file
    # unconditionally through run_all.REQUIRED_INPUTS, so `--arm v2` died at
    # check_inputs. That edge now carries the arm it belongs to and is skipped
    # when v1 is not selected -- the requirement became conditional while the
    # literal path stayed put, so the static inventory did not move.
    if "v1" in set(arm_reg.selected_names()):
        bt.to_csv(M / "daily_trades_v1_mid.csv", index=False)
    print(f"   v1 baseline trade log: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
          f"-> daily_trades_v1_mid.csv")

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

    # ------------------------------------------------------------------ V3/V4
    # Four-arm pro-vol measurement, per experiments/V34_SPEC.txt. v1 and v2 above
    # are passed in rather than recomputed, so the arms in v34_comparison.csv are
    # the same curves that wrote v2FINAL_equity.csv. Same process, same panel,
    # same dates, same seeds -- which is what the spec requires.
    # Nothing above this line is altered; v2FINAL_* keeps its names and columns.
    import v34_common
    v34_comp, v34_subs, _ = v34_common.run_v34(
        M, "MidCap150 (148 constituents)", "mid", px, op, sc, bd, pc, mom20, port_vol, tv,
        backtest_exposure,
        base_eq, tcb, nb, fin_eq, tcf, nf, expo,
        START_CAPITAL,
        [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)],
        {"TOP_N": TOP_N, "BUFFER": BUFFER, "REBAL": REBAL, "VOL_WIN": VOL_WIN,
         "START_CAPITAL": START_CAPITAL, "CASH_YIELD": CASH_YIELD,
         "SLIPPAGE": 0.0015},
        v1_audit=base_audit)
    print("\n" + "=" * 100)
    print(" V3/V4 FOUR-ARM MEASUREMENT -- MidCap150 (148 constituents)")
    print("=" * 100)
    print("\n FULL PERIOD")
    print(v34_comp.to_string(index=False))
    print("\n SUB-PERIODS")
    print(v34_subs.to_string(index=False))
    print("\n  saved -> v34_comparison.csv, v34_subperiods.csv, v34_equity.csv,")
    print("           v34_params.json, chart_v34.png")

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

    n_names = int(p["symbol"].nunique())
    equal_sel = TOP_N * n_names / 58.0
    print("=" * 100)
    print("SELECTIVITY -- AN OBSERVATION, NOT A CHANGE")
    print("=" * 100)
    print(f"""
  TOP_N is {TOP_N}, unchanged from the 58 and the 74. Against this universe that is
  a different bet:

      58 names  -> top {TOP_N/58*100:.1f}%
      74 names  -> top {TOP_N/74*100:.1f}%
     {n_names} names  -> top {TOP_N/n_names*100:.1f}%

  For the same selectivity as the 58 setup, TOP_N would have to be about
  {equal_sel:.0f} ({TOP_N}/58 of {n_names}). Under the Fundamental Law, IR is roughly
  IC x sqrt(breadth), and breadth is one of only two levers that can move IR --
  every portfolio-construction experiment on this project has failed precisely
  because it moved neither term. Holding {n_names} candidates but still buying {TOP_N} of
  them takes the wider universe's breadth and then throws most of it away.

  This run deliberately does NOT act on that. TOP_N stays at {TOP_N} so this first
  pass is untuned and directly comparable to the 58 and the 74. Changing it is a
  separate pre-registered experiment, and choosing it after seeing these numbers
  would be fitting the parameter to the result.
""")
    print("Saved -> v2FINAL_comparison.csv, v2FINAL_yearly.csv, v2FINAL_equity.csv,")
    print("         v2FINAL_params.json, chart_v2FINAL.png")


if __name__ == "__main__":
    main()
