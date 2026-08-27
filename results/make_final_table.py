import sys
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.append(str(Path(__file__).resolve().parents[1]))
import config

M = config.METRICS_DIR
df = pd.read_csv(M / "FINAL_comparison.csv")
yr = pd.read_csv(M / "FINAL_yearly.csv", index_col=0)

cols = ["Config", "CAGR%", "Sharpe", "Sortino", "MaxDD%", "Calmar", "Trades", "TC_Rs"]
d = df[cols].copy()
d["TC_Rs"] = d["TC_Rs"].apply(lambda x: f"{x:,.0f}")
d["Trades"] = d["Trades"].apply(lambda x: f"{int(x):,}")

fig, ax = plt.subplots(2, 1, figsize=(16, 8), height_ratios=[1, 1])

ax[0].axis("off")
t = ax[0].table(cellText=d.values, colLabels=d.columns, cellLoc="center", loc="center")
t.auto_set_font_size(False); t.set_fontsize(10); t.scale(1, 1.9)
for j in range(len(d.columns)):
    t[(0, j)].set_facecolor("#40466e"); t[(0, j)].set_text_props(color="w", weight="bold")
for i in range(len(d)+1):
    t[(i, 0)].set_width(0.32)
colors = ["#dcfce7", "#dbeafe", "#fce7f3"]  # invvol(final)=green, equal=blue, bh=pink
for i in range(len(d)):
    for j in range(len(d.columns)):
        t[(i+1, j)].set_facecolor(colors[i])
ax[0].set_title("FINAL RESULT -- Backtest 2019-2026 | Rs 10L start | real Zerodha costs + 0.15% slippage",
                fontsize=13, weight="bold", pad=18)

yr2 = yr.reset_index()
yr2.columns = ["Year"] + list(yr.columns)
yr2["Year"] = yr2["Year"].astype(int)
ax[1].axis("off")
t2 = ax[1].table(cellText=yr2.round(1).values, colLabels=yr2.columns, cellLoc="center", loc="center")
t2.auto_set_font_size(False); t2.set_fontsize(10); t2.scale(1, 1.7)
for j in range(len(yr2.columns)):
    t2[(0, j)].set_facecolor("#40466e"); t2[(0, j)].set_text_props(color="w", weight="bold")
for i in range(len(yr2)):
    for j in [1, 2]:  # Strategy%, BuyHold%
        v = yr2.iloc[i, j]
        t2[(i+1, j)].set_facecolor("#dcfce7" if v > 0 else "#fee2e2")
    t2[(i+1, 3)].set_facecolor("#dbeafe")  # Diff column neutral
ax[1].set_title("Year by year (%)  --  Strategy = inverse-vol sizing (FINAL)", fontsize=13, weight="bold", pad=18)

plt.tight_layout()
plt.savefig(M / "chart_FINAL_table.png", dpi=150, bbox_inches="tight")
print("saved -> chart_FINAL_table.png")
