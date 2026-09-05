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
import config
from universes.registry import REGISTRY

# config_mid / config_n100 are imported INSIDE main(), under the guard that checks
# the universe is registered. At module level, deleting either would make this step
# unimportable rather than skippable.
import survivorship as sv
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


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything here used to run at module level,
    so importing this file executed the whole step as a side effect -- which is
    why the pipeline could only ever spawn it as a subprocess.

    Imports, helper defs and import-time setup stay at module level; every
    other statement moved, constants included, so no dependency chain is split.
    """
    CAP = 1_000_000

    # THIS STEP IS AN OVERLAY OF TWO UNIVERSES, AND ONE IS NOT AN OVERLAY.
    # Its entire purpose is the side-by-side comparison; with a single series it
    # would reproduce that universe's own v2FINAL chart under a name claiming to
    # combine two. So below two registered universes it does not run, and says so.
    # That is a deliberate difference from make_final_chart_fair.py, which compares
    # strategy against benchmark and stays meaningful with one universe.
    #
    # ORDER IS THE DECLARATION ORDER BELOW (n100, then mid) AND IS LOAD-BEARING:
    # it sets the plotting order and the derived filename. It is written here
    # rather than taken from REGISTRY iteration for that reason.
    SPEC = [
        ("n100", "NIFTY100",       "#c0392b", "#2e6da4", "#3a9d3a", "#000000"),
        ("mid",  "NIFTYMIDCAP150", "#e377c2", "#17becf", "#8fd08f", "#7f7f7f"),
    ]
    present = [row for row in SPEC if row[0] in REGISTRY]
    if len(present) < 2:
        have = ", ".join(r[0] for r in present) or "none"
        print("=" * 108)
        print(" COMBINED chart SKIPPED -- it overlays two universes and fewer than two "
              "are registered.")
        print(f" registered here: {have}.  A one-series 'combined' chart would just "
              "restate that universe's")
        print(" own v2FINAL chart under a name that claims to combine two, so nothing "
              "is written.")
        print("=" * 108)
        return

    # THE FOUR INPUT PATHS ARE SPELLED OUT PER UNIVERSE, IN THE DOTTED FORM, so
    # check_pipeline_order resolves each to the right directory. Written as
    # `M / "v2FINAL_equity.csv"` inside the loop below they cannot be: the loop
    # variable is one name for two directories, and the scanner is static. Before
    # this, the whole file resolved to results_n100 by accident -- one metrics dir
    # appeared in an assignment and became the default -- so mid's reads were
    # attributed to n100's directory and collapsed onto the same keys. These are
    # the real paths the loop uses, not decoration.
    FILES = {}
    if "n100" in REGISTRY:
        import config_n100
        FILES["n100"] = (config_n100.METRICS_DIR_N100 / "v2FINAL_equity.csv",
                         config_n100.METRICS_DIR_N100 / "v2FINAL_params.json",
                         config_n100.METRICS_DIR_N100 / "daily_trades_n100.csv",
                         config_n100.METRICS_DIR_N100 / "daily_trades_v1_n100.csv",
                         config_n100.INDEX_FILE_N100, len(config_n100.SYMBOLS_N100))
    if "mid" in REGISTRY:
        import config_mid
        FILES["mid"] = (config_mid.METRICS_DIR_MID / "v2FINAL_equity.csv",
                        config_mid.METRICS_DIR_MID / "v2FINAL_params.json",
                        config_mid.METRICS_DIR_MID / "daily_trades_mid.csv",
                        config_mid.METRICS_DIR_MID / "daily_trades_v1_mid.csv",
                        config_mid.INDEX_FILE_MID, len(config_mid.SYMBOLS_MID))

    UNIV = []
    for tag, idxname, c_v2, c_v1, c_bh, c_ix in present:
        eqf, pjf, tr2, tr1, idxfile, nsym = FILES[tag]
        UNIV.append((tag, eqf, pjf, tr2, tr1, idxfile, idxname, nsym,
                     c_v2, c_v1, c_bh, c_ix))

    # THE FILENAME NAMES WHAT IS ACTUALLY ON THE CHART. It was the literal
    # "chart_COMBINED_n100_mid.png"; a file with that name containing only mid is
    # worse than no file. Derived from the universes actually plotted, in plotting
    # order, so with n100 and mid present it still resolves to exactly
    # chart_COMBINED_n100_mid.png -- byte-identical output, honest name.
    # UNIV rows are (tag, eq, params, trades_v2, trades_v1, indexfile, indexname,
    # nsym, 4 colours). Named here because the row grew when the four input paths
    # became explicit, and a positional read of the old layout printed a PosixPath
    # where the index name belonged.
    I_TAG, I_EQ, I_IDXNAME = 0, 1, 6
    OUT = UNIV[0][I_EQ].parent / (
        "chart_COMBINED_" + "_".join(u[I_TAG] for u in UNIV) + ".png")
    print("=" * 108)
    print(" COMBINED -- " + " and ".join(u[I_IDXNAME] for u in UNIV)
          + ". Every number printed before plotting.")
    print(" Universes outside this overlay are out of scope and are not on this chart.")
    print("=" * 108)
    print(f"\n  SURVIVORSHIP: {sv.describe_state()}")
    series = []
    for tag, eqf, pjf, tr2, tr1, idxfile, idxname, nsym, c_v2, c_v1, c_bh, c_ix in UNIV:
        eq = pd.read_csv(eqf, parse_dates=["date"]).set_index("date")
        params = json.loads(pjf.read_text())
        inv = params["avg_exposure_pct"]
        raw = (config.read_price_csv(idxfile)[["date", "close"]].dropna()
               .set_index("date")["close"].sort_index())
        s_ = raw.reindex(eq.index.union(raw.index)).ffill().reindex(eq.index)
        index = CAP * s_ / s_.iloc[0]

        b_v2 = before_tc(eq["strategy"], tr2)
        b_v1 = before_tc(eq["baseline_invvol"], tr1)

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


if __name__ == "__main__":
    main()
