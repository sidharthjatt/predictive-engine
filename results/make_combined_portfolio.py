"""
make_combined_portfolio.py -- combined chart for the WHOLE PORTFOLIO
Cumulative arithmetic return + drawdown | strategy vs equal-rupee vs buy-hold
This is the actual result -- the whole strategy, not a single stock.
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
import config

M = config.METRICS_DIR
eq = pd.read_csv(M / "FINAL_equity.csv", parse_dates=["date"]).set_index("date")

def cum(s):   return (s / s.iloc[0] - 1) * 100
def dd(s):    return (s / s.cummax() - 1) * 100

strat, eqr, bh = eq["strategy"], eq["equal_rupee"], eq["buyhold"]

fig, ax = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[2, 1], sharex=True)

ax[0].plot(strat.index, cum(strat), lw=2.3, color="#1f77b4",
           label=f"Strategy (inverse-vol)  --  {cum(strat).iloc[-1]:+.1f}%")
ax[0].plot(eqr.index, cum(eqr), lw=1.6, color="#ff7f0e", alpha=.85,
           label=f"Strategy (equal-rupee)  --  {cum(eqr).iloc[-1]:+.1f}%")
ax[0].plot(bh.index, cum(bh), lw=2, ls="--", color="#2ca02c",
           label=f"Equal-weight buy & hold  --  {cum(bh).iloc[-1]:+.1f}%")
ax[0].axhline(0, color="k", lw=.7, alpha=.5)
ax[0].set_ylabel("Cumulative arithmetic return (%)")
ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[0].set_title("FULL PORTFOLIO -- cumulative return & drawdown  (backtest 2019-2026)\n"
                "Rs 10L start | real Zerodha costs + 0.15% slippage", fontsize=12)
ax[0].legend(loc="upper left", fontsize=10)
ax[0].grid(alpha=.3)

for s, c, ls, lab in [(strat, "#1f77b4", "-", "Strategy"),
                      (bh, "#2ca02c", "--", "Buy & hold")]:
    d = dd(s)
    ax[1].fill_between(d.index, d, 0, color=c, alpha=.25)
    ax[1].plot(d.index, d, lw=1.6, color=c, ls=ls, label=f"{lab}  (max {d.min():.1f}%)")
ax[1].set_ylabel("Drawdown (%)")
ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[1].legend(loc="lower left", fontsize=10)
ax[1].grid(alpha=.3)

plt.tight_layout()
plt.savefig(M / "combined_PORTFOLIO.png", dpi=140, bbox_inches="tight")
print("saved -> combined_PORTFOLIO.png")
