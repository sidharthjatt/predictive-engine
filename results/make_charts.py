import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")
sys.path.append(str(Path(__file__).resolve().parents[1]))
import config

M = config.METRICS_DIR
eq = pd.read_csv(M / "FINAL_equity.csv", parse_dates=["date"]).set_index("date")
eq = eq.rename(columns={"strategy": "expanding", "buyhold": "buyhold", "equal_rupee": "yearly"})

cum = {c: (eq[c] / eq[c].iloc[0] - 1) * 100 for c in eq.columns}

fig, ax = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[2, 1])

styles = {
    "expanding":   ("#1f77b4", 2.2, "-",  "Monthly retrain - expanding window"),
    "rolling-5yr": ("#9467bd", 1.6, "-",  "Monthly retrain - rolling 5yr"),
    "rolling-3yr": ("#8c564b", 1.3, "-",  "Monthly retrain - rolling 3yr"),
    "yearly":      ("#ff7f0e", 1.6, "-",  "Yearly retrain (previous)"),
    "buyhold":     ("#2ca02c", 2.0, "--", "Equal-weight buy & hold (58)"),
}
for c, (col, lw, ls, lab) in styles.items():
    if c in cum:
        ax[0].plot(eq.index, cum[c], lw=lw, ls=ls, color=col, label=lab,
                   alpha=.9 if c in ("expanding", "buyhold") else .75)

ax[0].axhline(0, color="k", lw=0.8, alpha=.5)
ax[0].set_ylabel("Cumulative return (%)")
ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[0].set_title("Backtest 2019-2026 | monthly vs yearly retraining\n"
                "real Zerodha costs + 0.15% slippage | params fixed a priori", fontsize=11)
ax[0].legend(loc="upper left", fontsize=9)
ax[0].grid(alpha=.3)

for c, col, lab in [("expanding", "#1f77b4", "Strategy (monthly expanding)"),
                    ("buyhold", "#2ca02c", "Buy & hold")]:
    if c in eq:
        dd = (eq[c] / eq[c].cummax() - 1) * 100
        ax[1].fill_between(eq.index, dd, 0, alpha=.35, color=col, label=lab)
ax[1].set_ylabel("Drawdown (%)")
ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[1].legend(loc="lower left", fontsize=9)
ax[1].grid(alpha=.3)

plt.tight_layout()
plt.savefig(M / "chart_equity.png", dpi=150, bbox_inches="tight")
print("saved -> chart_equity.png  (cumulative %, monthly retrain)")
