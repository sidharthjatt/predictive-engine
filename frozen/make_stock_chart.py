"""
make_stock_chart.py -- every stock's cumulative return, with the strategy highlighted

The chart shows:
  - 58 thin grey lines: each stock's own buy-and-hold cumulative return (backtest window)
  - 1 thick blue line: the strategy's cumulative return (FINAL, inverse-vol)
  - 1 thick green dashed line: equal-weight buy & hold (benchmark, the average of all 58)

This shows how the strategy compares against each individual stock.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_guard import guard as _frozen_guard
import config


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. This body used to run at module level, so
    importing this file executed the whole step as a side effect -- which is why
    the pipeline could only ever spawn it as a subprocess.
    """
    # THE FROZEN GUARD MOVED IN HERE WITH THE WORK. At module level it fired on
    # IMPORT, so run.py could not load this file at all. It guards the WRITE, so
    # it belongs where the writing happens.
    _frozen_guard("58")   # refuses unless ALLOW_FROZEN_WRITE=1; run_all.py sets it

    M = config.METRICS_DIR
    BT_START, BT_END = 2019, 2026
    final_eq = pd.read_csv(M / "FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    p = pd.read_csv("/tmp/v5_expanding.csv", parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    px = px.loc[bd]
    stock_cum = (px / px.bfill().iloc[0] - 1) * 100
    fig, ax = plt.subplots(figsize=(15, 9))
    for col in stock_cum.columns:
        ax.plot(stock_cum.index, stock_cum[col], lw=0.6, color="grey", alpha=0.35)
    final_vals = stock_cum.iloc[-1].dropna().sort_values()
    worst5 = final_vals.head(5)
    best5 = final_vals.tail(5)
    for sym, val in pd.concat([worst5, best5]).items():
        ax.annotate(sym, xy=(stock_cum.index[-1], val), fontsize=7, color="dimgrey",
                   xytext=(4, 0), textcoords="offset points", va="center")
    strat_cum = (final_eq["strategy"] / final_eq["strategy"].iloc[0] - 1) * 100
    bh_cum = (final_eq["buyhold"] / final_eq["buyhold"].iloc[0] - 1) * 100
    ax.plot(strat_cum.index, strat_cum, lw=3, color="#1f77b4",
            label=f"FINAL strategy (inverse-vol)  --  CAGR 19.36%, Sharpe 1.07")
    ax.plot(bh_cum.index, bh_cum, lw=2.5, ls="--", color="#2ca02c",
            label=f"Equal-weight buy & hold (58)  --  CAGR 18.65%, Sharpe 1.06")
    ax.axhline(0, color="k", lw=0.8, alpha=0.5)
    ax.set_ylabel("Cumulative return (%)")
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_title("All 58 individual stocks (grey) vs the strategy (blue) and benchmark (green)\n"
                "Backtest 2019-2026  |  labelled: 5 best and 5 worst performing individual stocks",
                fontsize=12)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(M / "chart_all_stocks.png", dpi=150, bbox_inches="tight")
    print("saved -> chart_all_stocks.png")
    n_years = (stock_cum.index[-1] - stock_cum.index[0]).days / 365.25
    stock_summary = pd.DataFrame({
        "symbol": stock_cum.columns,
        "total_return_%": stock_cum.iloc[-1].round(1).values,
    })
    stock_summary["CAGR_%"] = ((1 + stock_summary["total_return_%"] / 100) ** (1 / n_years) - 1) * 100
    stock_summary["CAGR_%"] = stock_summary["CAGR_%"].round(2)
    stock_summary = stock_summary.sort_values("CAGR_%", ascending=False)
    stock_summary.to_csv(M / "per_stock_returns.csv", index=False)
    print("saved -> per_stock_returns.csv")
    print(f"\nTop 5 stocks:\n{stock_summary.head(5).to_string(index=False)}")
    print(f"\nBottom 5 stocks:\n{stock_summary.tail(5).to_string(index=False)}")
    print(f"\nStrategy CAGR: 19.36%  |  Beat {(stock_summary['CAGR_%'] < 19.36).sum()} of "
          f"{len(stock_summary)} individual stocks")


if __name__ == "__main__":
    main()
