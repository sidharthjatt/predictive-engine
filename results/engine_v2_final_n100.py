"""
engine_v2_final_n100.py -- FINAL v2 STRATEGY (breadth-scaled), Nifty 100 universe
================================================================================
Same strategy as engine_v2_final.py, run on the Nifty 100 universe (99 names,
index excluded by name). Every feature, hyperparameter and rule is byte-identical
to the other universes; only the universe differs.

  Cross-sectional LightGBM ranking (17 features, monthly retrain, 32d purge)
    + inverse-vol position sizing
    + BREADTH SCALING for crash control

  At each rebalance, exposure = (stocks with positive 20-day momentum) / total.
  All positive -> fully invested. Half -> half invested, the rest in cash. It does
  NOT block individual stocks, and there is no tunable threshold.

  Existing holdings are never resized. Only new positions are sized against the
  target, so the actual invested percentage can drift above target.

CASH
    CASH_YIELD in test_exposure.py is 0.0. Idle cash earns nothing. Deliberately
    conservative: parking idle cash in a liquid fund is a separate operation and is
    not modelled here.

SURVIVORSHIP -- STATED, NOT IMPLIED
    The 99 constituents are TODAY'S Nifty 100 members backfilled to 2019. Names
    that were in the index during the window and were later dropped or delisted are
    absent from this file entirely, so BOTH the strategy and its equal-weight
    buy&hold benchmark are inflated. The cap-weighted NIFTY100 index line does not
    have this problem -- it is the published series -- which is exactly why it is
    plotted alongside. survivorship.describe_state() is printed below and in the
    chart subtitle.

VALIDATION IS NOT INHERITED FROM ANOTHER UNIVERSE
    The seed-robustness and sub-period validations recorded for the 58 and the mid
    were measured on those universes. They are not re-stated here as though they
    applied to this one. This run reports its own numbers and makes no validation
    claim it has not measured.

Run: python3 results/engine_v2_final_n100.py
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
import config, config_n100
import survivorship as sv
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
M = config_n100.METRICS_DIR_N100


def main():
    print("=" * 100)
    print("ENGINE v2 FINAL -- Nifty 100 universe (99 names, index excluded by name)")
    print("=" * 100)
    print(f"  SURVIVORSHIP: {sv.describe_state()}")

    src = config.require_cache(M / "v_n100_expanding_cache.csv",
                               "/tmp/v_n100_expanding.csv",
                               what="Nifty 100 score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    assert config_n100.INDEX_NAME_N100 not in set(p["symbol"].unique()), \
        "the index is in the score panel as a tradable name"

    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()

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
    mbh = metrics(bh, "Equal-weight buy & hold (Nifty 100, 99 names)")

    out = pd.DataFrame([mfin, mbase, mbh])
    print("\n" + out.to_string(index=False))
    print(f"\n   v2 FINAL average exposure: {expo*100:.0f}% invested "
          f"(rest in cash at {CASH_YIELD*100:g}% yield)")
    out.to_csv(M / "v2FINAL_comparison.csv", index=False)

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

    bt = pd.DataFrame(base_audit["trades"])
    assert len(bt) == nb, f"v1 trade log {len(bt)} rows vs engine count {nb}"
    # WRITTEN UNCONDITIONALLY, AND THAT IS A KNOWN LEAK, RECORDED NOT HIDDEN.
    # `--arm v2` still produces daily_trades_v1_n100.csv -- a file named for an
    # arm the run did not select. Gating it was TRIED and reverted: STEP 10d
    # make_n100_chart.py declares this file in run_all.REQUIRED_INPUTS as a hard
    # edge, so a gated write makes `--arm v2` die at check_inputs with a missing
    # file. Removing that edge would weaken the static contract and cost the
    # checker a resolved dependency, which experiments/ARM_SUBSET_SPEC.txt's G6
    # forbids. Closing this properly means making make_n100_chart.py arm-aware
    # too; see KNOWN_ISSUES.md.
    bt.to_csv(M / "daily_trades_v1_n100.csv", index=False)
    print(f"   v1 baseline trade log: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
          f"-> daily_trades_v1_n100.csv")

    (M / "v2FINAL_params.json").write_text(json.dumps({
        "universe": "Nifty 100 (99 constituents, NIFTY100.csv excluded by name)",
        "model": "cross-sectional LightGBM, 17 feats, 10-seed, monthly, 32d purge",
        "sizing": "inverse-volatility (1/vol60)",
        "exposure": "breadth scaling = fraction of positive-20d-momentum stocks",
        "top_n": TOP_N, "buffer": BUFFER, "rebalance_days": REBAL,
        "avg_exposure_pct": round(expo*100),
        "n_symbols": int(p["symbol"].nunique()),
        "sharpe": mfin["Sharpe"], "maxdd_pct": mfin["MaxDD%"], "cagr_pct": mfin["CAGR%"],
        "cash_yield": CASH_YIELD,
        "survivorship": sv.describe_state(),
        "vs_buyhold": (f"Sharpe {mfin['Sharpe']} vs {mbh['Sharpe']}, "
                       f"MaxDD {mfin['MaxDD%']}% vs {mbh['MaxDD%']}%, "
                       f"CAGR {mfin['CAGR%']}% vs {mbh['CAGR%']}%"),
        "validation_status": ("not measured on this universe. The seed-robustness "
                              "and sub-period validations on record were run on the "
                              "58 and the mid and are not claimed here."),
    }, indent=2))

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
    ax[0].set_title("Nifty 100 universe -- ranking + inverse-vol + breadth-scaled exposure\n"
                    + sv.describe_state(), fontsize=10)
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
        M, "Nifty 100 (99 constituents)", "n100", px, op, sc, bd, pc, mom20, port_vol, tv,
        backtest_exposure,
        base_eq, tcb, nb, fin_eq, tcf, nf, expo,
        START_CAPITAL,
        [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)],
        {"TOP_N": TOP_N, "BUFFER": BUFFER, "REBAL": REBAL, "VOL_WIN": VOL_WIN,
         "START_CAPITAL": START_CAPITAL, "CASH_YIELD": CASH_YIELD,
         "SLIPPAGE": 0.0015},
        v1_audit=base_audit)
    print("\n" + "=" * 100)
    print(" V3/V4 FOUR-ARM MEASUREMENT -- Nifty 100 (99 constituents)")
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
    print(f"""
  Versus equal-weight buy & hold over the same period:
    Sharpe   {mfin['Sharpe']:>6.2f} vs {mbh['Sharpe']:>6.2f}   ({mfin['Sharpe']-mbh['Sharpe']:+.2f})
    MaxDD    {mfin['MaxDD%']:>6.2f}% vs {mbh['MaxDD%']:>6.2f}%   ({mfin['MaxDD%']-mbh['MaxDD%']:+.2f} pts)
    CAGR     {mfin['CAGR%']:>6.2f}% vs {mbh['CAGR%']:>6.2f}%   ({mfin['CAGR%']-mbh['CAGR%']:+.2f} pts)

  The strategy holds {expo*100:.0f}% invested on average, so raw CAGR is not the right
  comparison on its own -- return per deployed rupee and drawdown are. Idle cash
  earns {CASH_YIELD*100:g}%, so none of the return above comes from interest.

  The equal-weight buy&hold above is NOT investable: it is 99 of today's index
  members backfilled. The cap-weighted NIFTY100 index, which does not have that
  problem, is plotted in make_n100_chart.py.
""")

    n_names = int(p["symbol"].nunique())
    print("=" * 100)
    print("SELECTIVITY -- AN OBSERVATION, NOT A CHANGE")
    print("=" * 100)
    print(f"""
  TOP_N is {TOP_N}, unchanged from every other universe. Against this one that is
  the top {TOP_N/n_names*100:.1f}% of {n_names} names, against {TOP_N/58*100:.1f}% of the 58.
  For equal selectivity TOP_N would be about {TOP_N*n_names/58.0:.0f}. This run does NOT act on
  that: TOP_N stays at {TOP_N} so the first pass is untuned and directly comparable.
  Changing it after seeing these numbers would be fitting the parameter to the result.
""")
    print("Saved -> v2FINAL_comparison.csv, v2FINAL_yearly.csv, v2FINAL_equity.csv,")
    print("         v2FINAL_params.json, chart_v2FINAL.png")


if __name__ == "__main__":
    main()
