"""
make_combined_all.py -- one combined chart per stock (return + drawdown), 58 charts
Folder: results/metrics/combined_charts/
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
_frozen_guard("58")   # refuses unless ALLOW_FROZEN_WRITE=1; run_all.py sets it
import config

M = config.METRICS_DIR
OUT = M / "combined_charts"
OUT.mkdir(exist_ok=True)
# WINDOW FROZEN: retired universe -- serves only the retired 58/74. Their published
# numbers must not move, so this window is deliberately left on the old
# year cut while the live universes moved to config.BT_START_DATE/BT_END_DATE.
BT_START, BT_END = 2019, 2026

frames = {}
for f in sorted((config.RAW_DATA_DIR / "nifty50").glob("*.csv")):
    d = config.read_price_csv(f)[["date", "close"]].dropna()
    frames[f.stem] = d.set_index("date")["close"]
px = pd.DataFrame(frames).sort_index().ffill()
bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
px = px.loc[bd]

trades = pd.read_csv(M / "FINAL_trades.csv", parse_dates=["Date"])
trades["D"] = trades["Date"].dt.normalize()

def dd_of(cum):
    lvl = 1 + cum/100
    return (lvl/lvl.cummax() - 1) * 100

symbols = sorted(px.columns)
print(f"Building {len(symbols)} combined charts...\n")

for i, sym in enumerate(symbols):
    price = px[sym]
    own_cum = (price / price.iloc[0] - 1) * 100
    st = trades[trades["Symbol"] == sym].sort_values("Date")
    by_day = {k: v for k, v in st.groupby("D")} if len(st) else {}

    strat = pd.Series(0.0, index=bd)
    buys, sells = [], []
    holding, entry, realized = False, None, 0.0
    for dt in bd:
        todays = by_day.get(dt.normalize())
        if todays is not None:
            for _, tr in todays.iterrows():
                if tr["Action"] == "BUY":
                    holding, entry = True, tr["Price"]; buys.append(dt)
                elif tr["Action"] == "SELL" and holding:
                    realized += (tr["Price"]/entry - 1)*100
                    holding, entry = False, None; sells.append(dt)
        strat.loc[dt] = realized + ((price.loc[dt]/entry - 1)*100 if holding and entry else 0)

    own_dd, strat_dd = dd_of(own_cum), dd_of(strat)

    fig, ax = plt.subplots(2, 1, figsize=(13, 8.5), height_ratios=[2, 1], sharex=True)
    ax[0].plot(own_cum.index, own_cum, lw=1.5, color="#2ca02c", ls="--",
               label=f"{sym} buy & hold  --  {own_cum.iloc[-1]:+.1f}%")
    ax[0].plot(strat.index, strat, lw=2.1, color="#1f77b4",
               label=f"Strategy's return from {sym}  --  {strat.iloc[-1]:+.1f}%")
    if buys:
        ax[0].scatter(buys, [strat.loc[d] for d in buys], marker="^", color="#2ca02c",
                      s=70, zorder=5, edgecolors="k", linewidths=.5, label=f"BUY ({len(buys)})")
    if sells:
        ax[0].scatter(sells, [strat.loc[d] for d in sells], marker="v", color="#d62728",
                      s=70, zorder=5, edgecolors="k", linewidths=.5, label=f"SELL ({len(sells)})")
    ax[0].axhline(0, color="k", lw=.7, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(f"{sym}  --  return & drawdown  (2019-2026)   "
                    f"|  blue flat = not held", fontsize=11)
    ax[0].legend(loc="upper left", fontsize=8.5)
    ax[0].grid(alpha=.3)

    ax[1].fill_between(own_dd.index, own_dd, 0, color="#2ca02c", alpha=.22)
    ax[1].plot(own_dd.index, own_dd, lw=1.2, color="#2ca02c", ls="--",
               label=f"{sym} B&H  (max {own_dd.min():.1f}%)")
    ax[1].fill_between(strat_dd.index, strat_dd, 0, color="#1f77b4", alpha=.22)
    ax[1].plot(strat_dd.index, strat_dd, lw=1.5, color="#1f77b4",
               label=f"Strategy  (max {strat_dd.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=8.5)
    ax[1].grid(alpha=.3)

    plt.tight_layout()
    plt.savefig(OUT / f"{sym}.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  [{i+1:>2}/{len(symbols)}] {sym}")

print(f"\nSaved {len(symbols)} charts -> {OUT}")
