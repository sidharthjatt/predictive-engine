"""
make_per_stock_charts.py -- one chart per stock (58 charts)

Each chart shows:
  1. The stock's own cumulative price return (green dashed)
  2. The strategy's cumulative P&L from that same stock (blue), flat while not held
  3. BUY markers (green triangle up) / SELL markers (red triangle down)

Date-matching bug fix: trade dates are normalised so Timestamps are
compared consistently. (Previously a Timestamp was compared against a python date,
which never matches, so every stock showed +0.0%.)
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
OUT = M / "per_stock_charts"
OUT.mkdir(exist_ok=True)
# WINDOW FROZEN: retired universe -- serves only the retired 58/74. Their published
# numbers must not move, so this window is deliberately left on the old
# year cut while the live universes moved to config.BT_START_DATE/BT_END_DATE.
BT_START, BT_END = 2019, 2026


def main():
    print("Loading data...")
    trades = pd.read_csv(M / "FINAL_trades.csv", parse_dates=["Date"])
    trades["D"] = trades["Date"].dt.normalize()

    # prices come straight from the raw CSVs -- this chart does not need scores
    frames = {}
    for f in sorted((config.RAW_DATA_DIR / "nifty50").glob("*.csv")):
        d = config.read_price_csv(f)[["date", "close"]].dropna()
        frames[f.stem] = d.set_index("date")["close"]
    px = pd.DataFrame(frames).sort_index().ffill()
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    px = px.loc[bd]

    symbols = sorted(px.columns)          # ALL 58
    print(f"{len(symbols)} stocks total. Building charts...\n")

    summary_rows = []
    for i, sym in enumerate(symbols):
        price = px[sym]
        own_cum = (price / price.bfill().iloc[0] - 1) * 100

        sym_trades = trades[trades["Symbol"] == sym].sort_values("Date")
        by_day = {k: v for k, v in sym_trades.groupby("D")} if len(sym_trades) else {}

        strat_ret = pd.Series(0.0, index=bd)
        buy_pts, sell_pts = [], []        # (date, y-value on strategy line)
        holding, entry_price, realized = False, None, 0.0

        for dt in bd:
            todays = by_day.get(dt.normalize())
            if todays is not None:
                for _, tr in todays.iterrows():
                    if tr["Action"] == "BUY":
                        holding, entry_price = True, tr["Price"]
                        buy_pts.append(dt)
                    elif tr["Action"] == "SELL" and holding:
                        realized += (tr["Price"] / entry_price - 1) * 100
                        holding, entry_price = False, None
                        sell_pts.append(dt)
            if holding and entry_price:
                strat_ret.loc[dt] = realized + (price.loc[dt] / entry_price - 1) * 100
            else:
                strat_ret.loc[dt] = realized

        n_buys = len(buy_pts)
        final_own, final_strat = own_cum.iloc[-1], strat_ret.iloc[-1]

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(own_cum.index, own_cum, lw=1.6, color="#2ca02c", ls="--", alpha=.85,
                label=f"{sym} price (buy & hold)  --  {final_own:+.1f}%")
        ax.plot(strat_ret.index, strat_ret, lw=2.2, color="#1f77b4",
                label=f"Strategy's return from {sym}  --  {final_strat:+.1f}%")
        if buy_pts:
            ax.scatter(buy_pts, [strat_ret.loc[d] for d in buy_pts], marker="^",
                       color="#2ca02c", s=70, zorder=5, edgecolors="k", linewidths=.5,
                       label=f"BUY ({len(buy_pts)})")
        if sell_pts:
            ax.scatter(sell_pts, [strat_ret.loc[d] for d in sell_pts], marker="v",
                       color="#d62728", s=70, zorder=5, edgecolors="k", linewidths=.5,
                       label=f"SELL ({len(sell_pts)})")
        ax.axhline(0, color="k", lw=.7, alpha=.5)
        ax.set_ylabel("Cumulative return (%)")
        ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax.set_title(f"{sym}  --  {n_buys} entries over backtest 2019-2026\n"
                     f"Blue flat sections = stock not held (money was elsewhere)",
                     fontsize=11)
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(alpha=.3)
        plt.tight_layout()
        plt.savefig(OUT / f"{sym}.png", dpi=130, bbox_inches="tight")
        plt.close(fig)

        summary_rows.append({"symbol": sym, "own_return_%": round(final_own, 1),
                             "strategy_return_%": round(final_strat, 1),
                             "entries": n_buys})
        print(f"  [{i+1:>2}/{len(symbols)}] {sym:<15} own {final_own:>+8.1f}%   "
              f"strategy {final_strat:>+7.1f}%   ({n_buys} entries)")

    sm = pd.DataFrame(summary_rows).sort_values("strategy_return_%", ascending=False)
    sm.to_csv(M / "per_stock_charts_summary.csv", index=False)
    print(f"\nSaved {len(symbols)} charts -> {OUT}")
    print(f"Saved -> per_stock_charts_summary.csv")


if __name__ == "__main__":
    main()
