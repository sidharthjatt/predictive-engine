"""
make_combined_n100_mid.py -- the combined chart for the two universes still in scope.

58 AND 74 ARE DELIBERATELY ABSENT
    Project scope narrowed to Nifty 100 and MidCap150. Leaving the dropped
    universes on a chart titled "combined" would misrepresent what the project is,
    so they are removed rather than greyed out.

WHAT IS PLOTTED, PER UNIVERSE
    v1 (inverse-vol, always invested), v2 (breadth-scaled), the own-universe
    equal-weight buy&hold, and the published cap-weighted index. Before-TC and
    after-TC CAGR are both in the legend, so the cost drag is visible rather than
    implied.

THE TWO BENCHMARKS ARE NOT INTERCHANGEABLE
    The cap-weighted index is investable and is NOT survivorship-biased -- it is the
    published series. The equal-weight buy&hold is the right yardstick for a
    strategy picking from the universe, but it is neither investable nor achievable,
    because both universes are today's members backfilled. Both are shown, labelled
    for what they are.

Every headline number is printed before anything is plotted.
Reads only. Writes one PNG.
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
import config, config_mid, config_n100
import survivorship as sv

CAP = 1_000_000
OUT = config_n100.METRICS_DIR_N100 / "chart_COMBINED_n100_mid.png"


def cum(s): return (s / s.iloc[0] - 1) * 100
def dd(s):  return (s / s.cummax() - 1) * 100
def cagr(s):
    y = (s.index[-1] - s.index[0]).days / 365.25
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1) * 100
def sharpe(s):
    r = s.pct_change().dropna()
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def before_tc(eq, log):
    """CAGR with the cost drag removed from the realised path. Not a zero-cost re-run."""
    if not Path(log).exists():
        return None, 0.0, 0
    tr = pd.read_csv(log, parse_dates=["date"])
    tc = tr.groupby("date")["tc"].sum().reindex(eq.index).fillna(0.0)
    g = (1 + eq.pct_change().fillna(0.0) + (tc / eq.shift(1)).fillna(0.0)).cumprod() * eq.iloc[0]
    return cagr(g), tc.sum(), len(tr)


UNIV = [
    ("n100", config_n100.METRICS_DIR_N100, config_n100.INDEX_FILE_N100,
     "NIFTY100", len(config_n100.SYMBOLS_N100), "#c0392b", "#2e6da4", "#3a9d3a", "#000000"),
    ("mid", config_mid.METRICS_DIR_MID, config_mid.INDEX_FILE_MID,
     "NIFTYMIDCAP150", len(config_mid.SYMBOLS_MID), "#e377c2", "#17becf", "#8fd08f", "#7f7f7f"),
]

print("=" * 108)
print(" COMBINED -- NIFTY 100 and MIDCAP150. Every number printed before plotting.")
print(" 58 and 74 are out of scope and are not on this chart.")
print("=" * 108)
print(f"\n  SURVIVORSHIP: {sv.describe_state()}")

series = []
for tag, M, idxfile, idxname, nsym, c_v2, c_v1, c_bh, c_ix in UNIV:
    eq = pd.read_csv(M / "v2FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    params = json.loads((M / "v2FINAL_params.json").read_text())
    inv = params["avg_exposure_pct"]
    raw = (config.read_price_csv(idxfile)[["date", "close"]].dropna()
           .set_index("date")["close"].sort_index())
    s_ = raw.reindex(eq.index.union(raw.index)).ffill().reindex(eq.index)
    index = CAP * s_ / s_.iloc[0]

    b_v2 = before_tc(eq["strategy"], M / f"daily_trades_{tag}.csv")
    b_v1 = before_tc(eq["baseline_invvol"], M / f"daily_trades_v1_{tag}.csv")

    print(f"\n  {tag.upper()}  ({nsym} constituents, {idxname} excluded by name)  "
          f"window {eq.index[0].date()} -> {eq.index[-1].date()}  inv {inv}%")
    print(f"    {'series':<46}{'before TC':>11}{'after TC':>10}{'Sharpe':>8}{'MaxDD%':>9}")
    for lab, s2, b in ((f"{tag} v2 (breadth)", eq["strategy"], b_v2[0]),
                       (f"{tag} v1 (inv-vol)", eq["baseline_invvol"], b_v1[0]),
                       (f"{tag} buy&hold (equal-weight universe)", eq["buyhold"], None),
                       (f"{idxname} (cap-weighted index)", index, None)):
        bt = f"{b:>10.2f}%" if b is not None else f"{'--':>11}"
        print(f"    {lab:<46}{bt}{cagr(s2):>9.2f}%{sharpe(s2):>8.2f}{dd(s2).min():>8.2f}%")
    print(f"    v2 trades {b_v2[2]}, TC Rs {b_v2[1]:,.0f}   |   "
          f"v1 trades {b_v1[2]}, TC Rs {b_v1[1]:,.0f}")

    series += [
        (f"{tag} v2 (breadth)  [inv {inv}%]", eq["strategy"], c_v2, "-",
         f"CAGR {b_v2[0]:.2f}% before TC / {cagr(eq['strategy']):.2f}% after TC"
         f"  [{b_v2[2]} trades, Rs {b_v2[1]:,.0f}]"),
        (f"{tag} v1 (inv-vol)  [inv 100%]", eq["baseline_invvol"], c_v1, "-",
         f"CAGR {b_v1[0]:.2f}% before TC / {cagr(eq['baseline_invvol']):.2f}% after TC"
         f"  [{b_v1[2]} trades, Rs {b_v1[1]:,.0f}]"),
        (f"{tag} buy&hold (equal-weight universe)  [inv 100%]", eq["buyhold"], c_bh, "--",
         f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"),
        (f"{idxname} (cap-weighted index)  [inv 100%]", index, c_ix, ":",
         f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"),
    ]

sub = ("NIFTY 100 and MIDCAP150 -- v1, v2, own-universe equal-weight buy&hold, and the "
       "published cap-weighted index for each\n"
       "ALL STRATEGY NUMBERS AFTER TC (Zerodha + 0.15% slippage); before-TC also shown "
       "in the legend.  58 and 74 are out of scope and are not plotted.\n"
       "The cap-weighted index is investable and is NOT survivorship-biased. The "
       "equal-weight buy&hold is neither investable nor achievable: both universes are\n"
       "today's index members backfilled, so names dropped or delisted during the window "
       "are absent entirely and both strategy and buy&hold are inflated.\n"
       # LIQUIDITY BELONGS HERE MOST OF ALL.
       #   Both individual charts carry their own liquidity line, but this is the
       #   only page where the two universes appear together, and the contrast is
       #   the whole point: the same depth model costs n100 0.01 CAGR points and
       #   mid 1.80. Reading mid's 29.18% next to n100's 25.36% without that is
       #   reading a gap of 3.8 points that realistic execution more than halves.
       "LIQUIDITY, at Rs 10,00,000 starting capital. n100: 3 of 997 fills exceed 10% "
       "of prior-20-day median volume, and ZERO do on the 60-day window; modelling\n"
       "realistic depth (10% of median daily volume per level, three levels) costs "
       "0.01 CAGR points, 25.43% -> 25.42%, Sharpe unchanged at 1.88.\n"
       "mid: 22 of 985 fills exceed 10%, the largest being 1,614% on AIIL; the same "
       "depth model costs 1.80 CAGR points, 29.16% -> 27.36%, Sharpe 2.00 -> 1.90.\n"
       + sv.describe_state())

fig, ax = plt.subplots(2, 1, figsize=(17, 12), height_ratios=[2, 1])
for lab, s2, c, ls, extra in series:
    ax[0].plot(s2.index, cum(s2), lw=1.9, color=c, ls=ls, label=f"{lab}  {extra}")
ax[0].axhline(0, color="k", lw=.6, alpha=.5)
ax[0].set_ylabel("Cumulative return (%)")
ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[0].set_title(sub, fontsize=9)
ax[0].legend(loc="upper left", fontsize=8); ax[0].grid(alpha=.3)

for lab, s2, c, ls, _ in series:
    ax[1].plot(s2.index, dd(s2), lw=1.3, color=c, ls=ls,
               label=f"{lab.split('  [')[0]} (max {dd(s2).min():.1f}%)")
ax[1].set_ylabel("Drawdown (%)")
ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
ax[1].legend(loc="lower left", fontsize=7.5, ncol=2); ax[1].grid(alpha=.3)
plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"\n  saved -> {OUT}")
