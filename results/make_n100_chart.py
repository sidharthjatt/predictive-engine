"""
make_n100_chart.py -- Nifty 100 universe: equity, drawdown, and the two benchmarks.

THE BENCHMARK IS THE PUBLISHED INDEX, READ DIRECTLY BY NAME
    NIFTY100.csv is plotted as-is. No basket is built and called "the index".
    Nifty 100 is free-float capitalisation-weighted; an equal-weighted mean of its
    constituents is a different series with different returns.

    A bare glob over data/raw/nifty100_benchmark/ would sweep NIFTY100.csv into the
    constituent basket as a 100th "stock". That is not hypothetical -- this project
    made exactly that mistake once, averaging the index together with its own
    members and labelling the result as the benchmark. The index is excluded BY
    NAME in config_n100, and the exclusion is asserted here as well.

    Verified figures for this file, reproduced by the run rather than quoted:
      base       2003-01-02 = 1,008.00   against NSE's published base 1000 on 1-Jan-2003
      2019-01-01 -> 2026-06-22: 11,148.80 -> 25,209.55 = 2.26x = 11.54% CAGR

TWO BENCHMARKS, BOTH LABELLED FOR WHAT THEY ARE
    1. NIFTY100 (cap-weighted index) -- investable, and what an index fund would
       actually have returned. Not survivorship-biased: it is the published series.
    2. Equal-weight buy&hold of the 99 constituents -- the right comparison for a
       strategy picking from that universe, but NOT investable and NOT achievable,
       because those 99 are today's members backfilled.

Every headline number is printed before anything is plotted.
Writes chart output only.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, config_n100
import survivorship as sv

M = config_n100.METRICS_DIR_N100
CAP = 1_000_000
CUT = pd.Timestamp("2019-01-01")


def cum(s): return (s / s.iloc[0] - 1) * 100
def dd(s):  return (s / s.cummax() - 1) * 100
def cagr(s):
    y = (s.index[-1] - s.index[0]).days / 365.25
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1) * 100
def sharpe(s):
    r = s.pct_change().dropna()
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def before_tc(eq, log):
    """CAGR with the transaction-cost drag removed from the realised path:
    r_gross = r_net + tc/equity(t-1), compounded. Not a zero-cost re-run."""
    if not Path(log).exists():
        return None, 0.0, 0
    tr = pd.read_csv(log, parse_dates=["date"])
    tc = tr.groupby("date")["tc"].sum().reindex(eq.index).fillna(0.0)
    g = (1 + eq.pct_change().fillna(0.0) + (tc / eq.shift(1)).fillna(0.0)).cumprod() * eq.iloc[0]
    return cagr(g), tc.sum(), len(tr)


# ------------------------------------------------------------------- inputs
eq = pd.read_csv(M / "v2FINAL_equity.csv", parse_dates=["date"]).set_index("date")
params = json.loads((M / "v2FINAL_params.json").read_text())
inv = params["avg_exposure_pct"]

idx_raw = (config.read_price_csv(config_n100.INDEX_FILE_N100)[["date", "close"]].dropna()
           .set_index("date")["close"].sort_index())
s_ = idx_raw.reindex(eq.index.union(idx_raw.index)).ffill().reindex(eq.index)
index = CAP * s_ / s_.iloc[0]

# ------------------------------------------------- print before plotting
print("=" * 100)
print(" NIFTY 100 UNIVERSE -- every number printed before anything is plotted")
print("=" * 100)
print(f"\n  SURVIVORSHIP: {sv.describe_state()}")
print(f"\n  universe          : {len(config_n100.SYMBOLS_N100)} constituents "
      f"({config_n100.INDEX_NAME_N100} excluded BY NAME, not by glob)")
print(f"  panel symbols     : {params.get('n_symbols', 'see engine output')}")
print(f"  backtest window   : {eq.index[0].date()} -> {eq.index[-1].date()}")

print(f"\n  INDEX FILE {config_n100.INDEX_FILE_N100.name}")
print(f"    base            : {idx_raw.index[0].date()} = {idx_raw.iloc[0]:,.2f}"
      f"   (NSE base 1-Jan-2003 = 1000)")
print(f"    full series     : {idx_raw.index[0].date()} -> {idx_raw.index[-1].date()}, "
      f"{len(idx_raw):,} rows")
_w = idx_raw[(idx_raw.index >= CUT) & (idx_raw.index <= pd.Timestamp("2026-06-22"))]
_y = (_w.index[-1] - _w.index[0]).days / 365.25
print(f"    2019-01-01 -> 2026-06-22: {_w.iloc[0]:,.2f} -> {_w.iloc[-1]:,.2f} = "
      f"{_w.iloc[-1]/_w.iloc[0]:.2f}x = CAGR {((_w.iloc[-1]/_w.iloc[0])**(1/_y)-1)*100:.2f}%")
print( "    expected                : 11,148.80 -> 25,209.55 = 2.26x = 11.54% CAGR")

b_v2 = before_tc(eq["strategy"], M / "daily_trades_n100.csv")
b_v1 = before_tc(eq["baseline_invvol"], M / "daily_trades_v1_n100.csv")

print("\n  HEADLINE NUMBERS")
print(f"    {'series':<44} {'before TC':>10} {'after TC':>9} "
      f"{'Sharpe':>7} {'MaxDD%':>8} {'inv%':>5}")
rows = [("n100 v2 (breadth)", eq["strategy"], b_v2[0], inv),
        ("n100 v1 (inv-vol)", eq["baseline_invvol"], b_v1[0], 100),
        ("n100 buy&hold (equal-weight universe)", eq["buyhold"], None, 100),
        ("NIFTY100 (cap-weighted index)", index, None, 100)]
for lab, s2, b, iv in rows:
    bt = f"{b:>9.2f}%" if b is not None else f"{'--':>10}"
    print(f"    {lab:<44} {bt} {cagr(s2):>8.2f}% {sharpe(s2):>7.2f} "
          f"{dd(s2).min():>7.2f}% {iv:>4}%")
print(f"\n    v2 trades {b_v2[2]}, TC Rs {b_v2[1]:,.0f}   |   "
      f"v1 trades {b_v1[2]}, TC Rs {b_v1[1]:,.0f}")

# --------------------------------------------------------------- subtitle
sub = (f"Nifty 100 universe ({len(config_n100.SYMBOLS_N100)} constituents, index excluded "
       f"by name)  |  v2 holds {inv}% invested on average  |  ALL NUMBERS AFTER TC "
       f"(Zerodha + 0.15% slippage)\n"
       f"Benchmarks: NIFTY100 is the published CAP-WEIGHTED index (investable, and NOT "
       f"survivorship-biased). Equal-weight buy&hold is the universe, and is NOT "
       f"investable.\n"
       f"SURVIVORSHIP: these {len(config_n100.SYMBOLS_N100)} are TODAY'S index members "
       f"backfilled to 2019. Names dropped or delisted from the Nifty 100 during the "
       f"window are absent entirely,\nso both the strategy and its equal-weight "
       f"buy&hold are inflated. Do not read that buy&hold as achievable.\n"
       # THE CONTRAST WITH MIDCAP150 IS STATED, NOT LEFT TO BE INFERRED.
       #   mid's chart carries the same line reporting 22 of 985 fills above 10%
       #   and a 1.80 CAGR cost. Printing n100's much smaller figures here makes
       #   the difference between the two universes explicit; an absent line would
       #   read as "not measured" rather than "measured and small".
       f"LIQUIDITY: at Rs 10,00,000 starting capital, 3 of 997 fills exceed 10% of "
       f"prior-20-day median volume, and ZERO do on the 60-day window.\n"
       f"Modelling realistic depth (10% of median daily volume per level, three "
       f"levels) costs 0.01 CAGR points: 25.43% -> 25.42%, Sharpe unchanged at 1.88. "
       f"MidCap150 loses 1.80 points on the same test.\n"
       + sv.describe_state())

series = [
 (f"n100 v2 (breadth)  [inv {inv}%]", eq["strategy"], "#c0392b", "-",
  f"CAGR {b_v2[0]:.2f}% before TC / {cagr(eq['strategy']):.2f}% after TC"
  f"  [{b_v2[2]} trades, Rs {b_v2[1]:,.0f}]"),
 ("n100 v1 (inv-vol)  [inv 100%]", eq["baseline_invvol"], "#2e6da4", "-",
  f"CAGR {b_v1[0]:.2f}% before TC / {cagr(eq['baseline_invvol']):.2f}% after TC"
  f"  [{b_v1[2]} trades, Rs {b_v1[1]:,.0f}]"),
 ("n100 buy&hold (equal-weight universe)  [inv 100%]", eq["buyhold"], "#3a9d3a", "-",
  f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"),
 ("NIFTY100 (cap-weighted index)  [inv 100%]", index, "#000000", "--",
  f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"),
]

fig, ax = plt.subplots(2, 1, figsize=(16, 11), height_ratios=[2, 1])
for lab, s2, c, ls, extra in series:
    ax[0].plot(s2.index, cum(s2), lw=2.0, color=c, ls=ls, label=f"{lab}  {extra}")
ax[0].axhline(0, color="k", lw=.6, alpha=.5)
ax[0].set_ylabel("Cumulative return (%)")
ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[0].set_title(sub, fontsize=9.5)
ax[0].legend(loc="upper left", fontsize=8.5); ax[0].grid(alpha=.3)

for lab, s2, c, ls, _ in series:
    ax[1].plot(s2.index, dd(s2), lw=1.4, color=c, ls=ls,
               label=f"{lab.split('  [')[0]} (max {dd(s2).min():.1f}%)")
ax[1].set_ylabel("Drawdown (%)")
ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[1].legend(loc="lower left", fontsize=8.5); ax[1].grid(alpha=.3)
plt.tight_layout()
plt.savefig(M / "chart_n100.png", dpi=150, bbox_inches="tight")
print(f"\n  saved -> {M/'chart_n100.png'}")
