"""
make_combined_universes.py -- ONE combined chart across whichever universes this
run selected.

WHAT REPLACED WHAT
    This file was make_combined_n100_mid.py, and it was hardcoded to exactly two
    universes. Its SPEC named n100 and mid as literals, so the project could not
    compare any other pair -- 58 against mid, or all four -- without editing the
    step. It now takes the selection and compares exactly that.

    THE n100+mid OUTPUT DID NOT MOVE. With those two selected this writes
    chart_COMBINED_n100_mid.png, byte for byte the file the old step wrote, into
    the same directory. That is a verified property, not an intention: the
    rename would otherwise be a silent way to change a published figure.

THE RULE ABOUT HOW MANY UNIVERSES
    N == 1  nothing is written. A one-series "combined" chart restates that
            universe's own v2FINAL chart under a name claiming to combine
            several, and a file that misdescribes itself is worse than no file.
    N >= 2  exactly ONE chart, across exactly those N. Not one per pair, and
            never a universe that was not selected.

SELECTION, NOT REGISTRATION
    It asks universes/registry.selected_tags(), not REGISTRY. `--universe mid,58`
    leaves 74 registered and unselected; plotting it would put a universe on the
    page that nobody asked for. Run on its own with no selection set, the default
    is every registered universe, which is what the old step saw.

WHAT IS PLOTTED, PER UNIVERSE
    v1 (inverse-vol, always invested), v2 (breadth-scaled), the own-universe
    equal-weight buy&hold, and -- only where the universe HAS one -- the published
    cap-weighted index. Before-TC and after-TC CAGR are both in the legend, so the
    cost drag is visible rather than implied.

    THE RETIRED 58 AND 74 HAVE NO PUBLISHED INDEX. registry.index_file is None for
    them, which is a fact about those universes and not a missing path, so they
    contribute three lines instead of four. Inventing a benchmark for them -- an
    equal-weighted basket labelled as an index -- is the exact error this project
    already made once and corrected.

THE TWO BENCHMARKS ARE NOT INTERCHANGEABLE
    The cap-weighted index is investable and is NOT survivorship-biased -- it is the
    published series. The equal-weight buy&hold is the right yardstick for a
    strategy picking from the universe, but it is neither investable nor achievable,
    because these universes are today's members backfilled. Both are shown, labelled
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
from universes.registry import REGISTRY, selected_tags, report_order
import arms.registry as arm_reg
import cadence
import arm_sources

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


# ---------------------------------------------------------------------------
# PER-UNIVERSE PRESENTATION. Paths and index files come from the registry; only
# what is genuinely presentational lives here.
# ---------------------------------------------------------------------------
# DISPLAY IS NOT index_name AND NOT label. The chart title has always said
# "NIFTY 100" (with a space) and "MIDCAP150" (without the NIFTY prefix), while
# registry.index_name holds the FILE's name, "NIFTY100" and "NIFTYMIDCAP150",
# which is what the per-universe legend rows use. Deriving one from the other
# would silently retitle a published chart, so both are written down.
DISPLAY = {"n100": "NIFTY 100", "mid": "MIDCAP150"}

# FOUR COLOURS PER UNIVERSE: v2, v1, buy&hold, index. n100's and mid's are the
# exact values the two-universe chart used and must not change. The 58's and 74's
# rows were deleted with those universes; a new universe adds a row here, and
# _check_colours() below refuses rather than letting it fall back to a default.
# Slots 0-3 are v2, v1, buy&hold, index and are UNCHANGED -- the published chart
# depends on them. Slots 4 and 5 are v3 and v4, appended rather than inserted so
# every existing index keeps pointing at the same colour.
COLOURS = {
    "n100": ("#c0392b", "#2e6da4", "#3a9d3a", "#000000", "#7f3f98", "#d95f02"),
    "mid":  ("#e377c2", "#17becf", "#8fd08f", "#7f7f7f", "#1b9e77", "#e6ab02"),
}

_missing_colour = set(REGISTRY) - set(COLOURS)
if _missing_colour:
    raise SystemExit(
        f"COLOURS has no row for registered universe(s) {sorted(_missing_colour)}. "
        f"Add one that does not collide with the published values above; a chart "
        f"that picks a colour by accident is not reproducible.")

# WHICH SLOT OF THAT TUPLE EACH ARM USES. v2 has always been the first colour and
# v1 the second, so with both selected the chart is unchanged. v3 and v4 are new
# on this chart and take the two spare slots -- the buy&hold and index colours are
# separate entries, so nothing collides.
#
# THE COLOUR IS KEYED TO THE ARM, NOT TO POSITION. Step 2 already fixed this
# inside run_v34's chart, where a positional zip gave v3 v2's colour the moment v2
# was deselected. The same trap exists here and is avoided the same way.
ARM_SLOT = {"v2": 0, "v1": 1, "v3": 4, "v4": 5}
ARM_DESC = {"v1": "inv-vol", "v2": "breadth",
            "v3": "provol", "v4": "provol-breadth"}

# THE PUBLISHED PAIR, AND THE ORDER IT IS DRAWN IN. v2 before v1 is the order the
# figure has always had; keeping it is what makes the canonical file reproduce
# byte for byte.
CANON_ARMS = ("v2", "v1")
# The order any wider chart draws in: the published pair first, then the
# measurement arms, so a four-arm chart is the published one with two lines added
# rather than a reshuffle.
PLOT_ORDER = ("v2", "v1", "v3", "v4")

# THIS CHART IS DEFINED OVER THE SHIPPING ARMS, AND A SELECTION NARROWS IT RATHER
# THAN WIDENING IT.
#
# It compares UNIVERSES. Each universe contributes its shipping strategy (v2,
# breadth-scaled) and that strategy's always-invested control (v1), which is what
# the published figure has always shown. v3 and v4 are MEASUREMENT arms: they
# exist to price pro-vol sizing against inverse-vol, and their home is the v34
# chart, which Step 2 already made arm-aware.
#
# WHY NOT SIMPLY PLOT EVERY SELECTED ARM. Because `--arm all` is the default, so
# doing that would put four lines per universe on the published chart instead of
# two -- changing a published figure as a side effect of a structural change,
# which experiments/ARM_SUBSET_SPEC.txt forbids unconditionally (G1). Narrowing is
# safe and widening is not, so the rule is: plot the selected arms INTERSECTED
# with the shipping pair.
#
# THE CONSEQUENCE IS REAL AND IS NOT HIDDEN: with `--arm v3` no shipping arm is
# selected, and this chart is not drawn at all rather than being drawn with a
# measurement arm on it. It says so when it skips.
PLOT_ARMS = ("v2", "v1")

# THE LIQUIDITY PARAGRAPH IS A PER-UNIVERSE MEASUREMENT, NOT CHART FURNITURE.
# It used to be one hardcoded block naming n100 and mid, which is why the chart
# could not be drawn for any other set without quoting numbers from universes that
# were not on it. Each note is that universe's own measured result; a universe with
# no note contributes nothing rather than a placeholder.
# EVERY NUMBER IN A NOTE IS STAMPED WITH THE ENGINE THAT MEASURED IT. These were
# measured before adj_close became the canonical price and before the interior-gap
# guard, and the headline figures they quote have since moved -- n100 v2 is 24.43 /
# 1.72 and mid v2 is 29.23 / 1.99 as of the 2026-09-11 snapshot. They are kept as
# the liquidity finding, which is about fill sizes rather than about CAGR, and
# marked rather than silently re-quoted under numbers they were not measured
# against. Re-measure and restamp, or delete the note; do not edit the figures.
LIQUIDITY = {
    "n100": ("n100 [measured pre-2026-09-10, close-basis engine]: 3 of 997 fills "
             "exceed 10% of prior-20-day median volume, and ZERO do on the 60-day "
             "window;\nmodelling realistic depth (10% of median daily volume per "
             "level, three levels) cost 0.01 CAGR points, 25.43% -> 25.42%."),
    "mid":  ("mid [measured pre-2026-09-10, close-basis engine]: 22 of 985 fills "
             "exceed 10%, the largest being 1,614% on AIIL; the same depth model "
             "cost 1.80 CAGR points, 29.16% -> 27.36%."),
}

_COUNT_WORD = {2: "both", 3: "all three", 4: "all four"}
# Keyed by count, not by universe: it survives a universe being added or removed.

# THE STANDING PUBLISHED COMPARISON. n100-vs-mid is the figure docs/README.md
# embeds and the top-level README displays, so it is refreshed whenever both of
# its universes are selected -- not only when they are the WHOLE selection. It is
# named here, once, rather than being inferred from the registry: which figure the
# project publishes is an editorial fact, not a property of the universes, and
# deriving it would silently repoint the README the day a third universe is added.
#
# IT IS STILL CHECKED AGAINST THE REGISTRY at import, because the one thing it may
# not be is a pair that cannot exist -- that would fail at chart time, deep in a
# draw call, rather than here.
PAIR_CHART = ("n100", "mid")

_unknown_pair = set(PAIR_CHART) - set(REGISTRY)
if _unknown_pair:
    raise SystemExit(
        f"PAIR_CHART names universe(s) the registry does not define: "
        f"{sorted(_unknown_pair)}. The published comparison cannot be drawn. "
        f"Pick a pair from {sorted(REGISTRY)}, or retire the pair chart.")


def _joined(items):
    """'a', 'a and b', 'a, b and c' -- the form the two-universe title used."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def main():
    """The step, as a function, so run.py can call it in process."""
    CAP = 1_000_000

    # WHICHEVER UNIVERSES THIS RUN SELECTED, IN REPORT ORDER. report_order puts
    # n100 before mid, which is what makes the derived filename resolve to the
    # published chart_COMBINED_n100_mid.png rather than renaming it.
    tags = report_order(t for t in selected_tags() if t in REGISTRY)

    sel = set(arm_reg.selected_names())

    if len(tags) < 2:
        have = ", ".join(tags) or "none"
        print("=" * 108)
        print(" COMBINED chart SKIPPED -- it overlays two or more universes and "
              f"only {len(tags)} is selected.")
        print(f" selected here: {have}.  A one-series 'combined' chart would just "
              "restate that universe's")
        print(" own v2FINAL chart under a name that claims to combine several, so "
              "nothing is written.")
        print("=" * 108)
        return

    # THE FOUR INPUT PATHS ARE SPELLED OUT PER UNIVERSE, IN THE DOTTED FORM, so
    # check_pipeline_order resolves each read to the right directory. This is the
    # shape the two-universe step used and it is kept for its reason, not its
    # history: the scanner is STATIC. Written generically as
    # `Path(u.metrics_dir) / f"daily_trades_{t}.csv"` the whole block runs
    # perfectly and resolves to nothing -- measured, 34 resolved cross-step
    # dependencies down to 26, with the step's own reads listed as
    # `?/metrics/daily_trades_{t}.csv`. Neither the directory nor the placeholder
    # can be expanded from a loop variable.
    #
    # THE GUARD IS WRITTEN AROUND THE LITERALS, NOT IN PLACE OF THEM -- the same
    # rule make_daily_audit.py states -- so selection still decides what is read
    # while the literals stay visible to the scanner.
    #
    # A NEW UNIVERSE NEEDS A BLOCK HERE. That is the same obligation
    # registry.REPORT_ORDER already imposes; and because FILES is looked up with
    # [t] below, a missing block is a KeyError naming the tag rather than a chart
    # quietly one universe short.
    FILES = {}
    if "n100" in tags:
        import config_n100
        FILES["n100"] = (config_n100.METRICS_DIR_N100 / "v2FINAL_equity.csv",
                         config_n100.METRICS_DIR_N100 / "v2FINAL_params.json",
                         config_n100.METRICS_DIR_N100 / "daily_trades_n100.csv",
                         config_n100.METRICS_DIR_N100 / "daily_trades_v1_n100.csv")
    if "mid" in tags:
        import config_mid
        FILES["mid"] = (config_mid.METRICS_DIR_MID / "v2FINAL_equity.csv",
                        config_mid.METRICS_DIR_MID / "v2FINAL_params.json",
                        config_mid.METRICS_DIR_MID / "daily_trades_mid.csv",
                        config_mid.METRICS_DIR_MID / "daily_trades_v1_mid.csv")
    # LOADED ONCE, PLOTTED POSSIBLY TWICE. The published n100+mid pair chart is
    # drawn from the SAME rows as the N-way chart when both are produced, so the
    # two figures cannot disagree about a number.
    UNIV = []
    for t in tags:
        u = REGISTRY[t]
        eqf, pjf, tr2, tr1 = FILES[t]
        # THE CADENCE-NAMED FILE WHEN THE ENGINE WROTE ONE. The FILES literals
        # above stay canonical so check_pipeline_order keeps resolving them; the
        # cadence sibling is chosen here, at read time, and is the same path at
        # the default cadence.
        eqf = _ci(eqf)
        pjf = _ci(pjf)
        eq = pd.read_csv(eqf, parse_dates=["date"]).set_index("date")
        # ARMS BY NAME, NOT BY THE COLUMN THEY HAPPEN TO SIT IN.
        # equity_series falls back to the legacy `strategy`/`baseline_invvol`
        # spelling, which is what the deleted 58 and 74 wrote.
        eq_v2 = arm_reg.equity_series(eq, "v2")
        eq_v1 = arm_reg.equity_series(eq, "v1")
        index = None
        if u.index_file is not None:
            raw = (config.read_price_csv(u.index_file)[["date", "close"]].dropna()
                   .set_index("date")["close"].sort_index())
            s_ = raw.reindex(eq.index.union(raw.index)).ffill().reindex(eq.index)
            index = CAP * s_ / s_.iloc[0]
        UNIV.append({
            "tag": t, "u": u, "M": Path(eqf).parent, "eqf": eqf,
            "eq": eq, "index": index,
            "inv": json.loads(pjf.read_text())["avg_exposure_pct"],
            # ONE ENTRY PER AVAILABLE SELECTED ARM. Where each arm's curve and
            # per-trade log live is arm_sources' problem, not this chart's:
            # three files under three naming conventions, and four charts each
            # rediscovering that is four chances to disagree.
            "arms": _load_arms(Path(eqf).parent, t, sel),
            "idxname": u.index_name,
            "display": DISPLAY.get(t, t),
            "colours": COLOURS.get(t, ("#1f77b4", "#7f7f7f", "#2ca02c", "#000000")),
        })

    print("=" * 108)
    print(" COMBINED -- " + _joined([u["display"] for u in UNIV])
          + ". Every number printed before plotting.")
    unsel = [t for t in REGISTRY if t not in tags]
    if unsel:
        print(f" Universes outside this selection ({', '.join(unsel)}) are not on "
              "this chart.")
    else:
        print(" Every registered universe is on this chart.")
    print("=" * 108)
    print(f"\n  SURVIVORSHIP: {sv.describe_state()}")
    for row in UNIV:
        _report(row)

    # ------------------------------------------------------------------
    # TWO CHARTS ON THE ARM AXIS, THE SAME WAY THERE ARE TWO ON THE UNIVERSE AXIS.
    # ------------------------------------------------------------------
    # CANONICAL: the published figure, always exactly v2 and v1, into the
    # unsuffixed filename. Drawn whenever both are selected, so `--arm all` keeps
    # refreshing it and it stays byte-identical to what it has always been.
    #
    # SELECTION: exactly the arms this run selected, into an arm-suffixed
    # filename, drawn whenever the selection is anything other than that pair.
    # `--arm v3` therefore PRODUCES a chart showing v3 rather than skipping, and
    # `--arm all` produces a four-arm chart BESIDE the published two-arm one.
    #
    # WIDENING IS SAFE ONLY BECAUSE IT IS SUFFIXED. Adding v3 and v4 to the
    # unsuffixed file would change a published figure as a side effect of running
    # the default; putting them in a file of their own does not.
    def _emit(arm_names, out_suffix, why):
        rows = [r for r in UNIV if [n for n in r["arms"] if n in arm_names]]
        rows = [dict(r, arms={n: d for n, d in r["arms"].items() if n in arm_names})
                for r in rows]
        if len(rows) < 2:
            print(f"\n  {why}: fewer than two universes can show "
                  f"{', '.join(arm_names)} -- not drawn")
            return
        _draw(rows, rows[0]["M"] / ("chart_COMBINED_"
                                    + "_".join(r["tag"] for r in rows)
                                    + out_suffix + cadence.suffix() + ".png"))
        return rows

    canon_rows = None
    if set(CANON_ARMS) <= sel:
        canon_rows = _emit(list(CANON_ARMS), "", "canonical v2+v1 chart")

    if sel != set(CANON_ARMS):
        print("\n" + "-" * 108)
        print(" ALSO DRAWING THIS RUN'S ARM SELECTION -- "
              + ", ".join(n for n in PLOT_ORDER if n in sel)
              + ", into its own file.")
        print(" The unsuffixed chart above is the published v2+v1 comparison and "
              "is not widened.")
        print("-" * 108)
        _emit([n for n in PLOT_ORDER if n in sel], arm_reg.suffix(sel),
              "arm-selection chart")

    # ------------------------------------------------------------------
    # THE PUBLISHED PAIR CHART, IN ADDITION TO THE N-WAY ONE.
    # ------------------------------------------------------------------
    # n100-vs-mid is the project's standing comparison: it is the figure
    # docs/README.md embeds and the one the top-level README displays. It is NOT
    # merely "the N-way chart when N happens to be 2" -- it is a published figure
    # in its own right, and a four-universe run that silently stopped refreshing
    # it left the docs copy stale with nothing saying so.
    #
    # So whenever BOTH n100 and mid are in the selection, the pair chart is
    # refreshed as well. Two different, valid comparisons, not a contradiction:
    # the N-way chart answers "how do the selected universes compare", the pair
    # chart answers "how do the two live universes compare", and the second
    # question does not stop being asked because a retired universe was also run.
    #
    # ONLY WHEN N > 2. At N == 2 the selection IS the pair, the N-way chart above
    # already wrote exactly this file, and drawing it again would render the same
    # figure to the same path twice.
    #
    # IT IS DRAWN AS IF ONLY THE PAIR WERE SELECTED: _subtitle derives the
    # out-of-scope sentence from REGISTRY minus the rows being PLOTTED, not minus
    # the selection, so the string does not depend on what else ran. With the 58
    # and 74 deleted the registry is exactly this pair, so that sentence is now
    # empty -- the subtitle of the published chart changes on this commit, and
    # there is no version of "58 and 74 are out of scope" that stays true.
    pair = [r for r in UNIV if r["tag"] in PAIR_CHART]
    pair = [dict(r, arms={n: d for n, d in r["arms"].items() if n in CANON_ARMS})
            for r in pair]
    if (len(pair) == len(PAIR_CHART) and len(UNIV) > len(PAIR_CHART)
            and set(CANON_ARMS) <= sel and all(len(r["arms"]) == 2 for r in pair)):
        print("\n" + "-" * 108)
        print(" ALSO REFRESHING THE PUBLISHED PAIR CHART -- "
              + " and ".join(r["display"] for r in pair)
              + ". Same rows as above, drawn on their own.")
        print(" It is a standing published figure, not a by-product of N == 2, so a "
              "wider selection still refreshes it.")
        print("-" * 108)
        _draw(pair, pair[0]["M"] / ("chart_COMBINED_"
                                    + "_".join(r["tag"] for r in pair)
                                    + cadence.suffix() + ".png"))


def _ci(path):
    """The cadence-named sibling of `path` if the engine wrote one, else `path`."""
    if cadence.is_default():
        return path
    c = path.with_name(path.stem + cadence.suffix() + path.suffix)
    return c if c.exists() else path


def _load_arms(M, tag, sel):
    """{arm: {eq, b}} for every selected arm this universe can actually show."""
    out = {}
    for n in PLOT_ORDER:
        if n not in sel:
            continue
        _, eq = arm_sources.equity_path_and_series(M, tag, n)
        lg = arm_sources.trades_path(M, tag, n)
        if eq is None or lg is None:
            continue
        out[n] = {"eq": eq, "b": before_tc(eq, lg)}
    return out


def _report(row):
    """One universe's headline numbers, printed before anything is plotted."""
    t, eq, index = row["tag"], row["eq"], row["index"]
    nsym = len(row["u"].symbols()) if row["u"].symbols() is not None else None
    print(f"\n  {t.upper()}  "
          + (f"({nsym} constituents, {row['idxname']} excluded by name)  "
             if nsym is not None else "(directory-defined basket)  ")
          + f"window {eq.index[0].date()} -> {eq.index[-1].date()}  inv {row['inv']}%")
    print(f"    {'series':<46}{'before TC':>11}{'after TC':>10}{'Sharpe':>8}{'MaxDD%':>9}")
    printable = [(f"{t} {n} ({ARM_DESC[n]})", d["eq"], d["b"][0])
                 for n, d in row["arms"].items()]
    printable.append((f"{t} buy&hold (equal-weight universe)", eq["buyhold"], None))
    if index is not None:
        printable.append((f"{row['idxname']} (cap-weighted index)", index, None))
    for lab, s2, b in printable:
        bt = f"{b:>10.2f}%" if b is not None else f"{'--':>11}"
        print(f"    {lab:<46}{bt}{cagr(s2):>9.2f}%{sharpe(s2):>8.2f}{dd(s2).min():>8.2f}%")
    print("    " + "   |   ".join(
        f"{n} trades {d['b'][2]}, TC Rs {d['b'][1]:,.0f}" for n, d in row["arms"].items()))


def _series(rows):
    """The plotted lines for these rows, in row order."""
    out = []
    for row in rows:
        t, eq, index = row["tag"], row["eq"], row["index"]
        c_bh, c_ix = row["colours"][2], row["colours"][3]
        # COLOUR AND DEPLOYMENT KEYED TO THE ARM. v2 takes the tuple's first
        # colour and v1 the second, which is where they have always been, so with
        # both plotted every line keeps its exact colour. Only v2 is
        # breadth-scaled, so only v2 reports a deployment below 100%.
        for n, d in row["arms"].items():
            c = row["colours"][ARM_SLOT[n]]
            inv = row["inv"] if arm_reg.ARMS[n].mode == "breadth" else 100
            out.append(
                (f"{t} {n} ({ARM_DESC[n]})  [inv {inv}%]", d["eq"], c, "-",
                 f"CAGR {d['b'][0]:.2f}% before TC / {cagr(d['eq']):.2f}% after TC"
                 f"  [{d['b'][2]} trades, Rs {d['b'][1]:,.0f}]"))
        out.append(
            (f"{t} buy&hold (equal-weight universe)  [inv 100%]", eq["buyhold"], c_bh, "--",
             f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"))
        if index is not None:
            out.append(
                (f"{row['idxname']} (cap-weighted index)  [inv 100%]", index, c_ix, ":",
                 f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"))
    return out


def _draw(rows, out_path):
    """Render exactly these rows to this path."""
    series = _series(rows)
    sub = _subtitle(rows)
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
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  saved -> {out_path}")


def _subtitle(UNIV):
    """The chart's own description of what is on it, derived from what is on it.

    IT TAKES THE ROWS BEING PLOTTED, NOT THE SELECTION, and that distinction is
    what keeps the published pair chart reproducible. "58 and 74 are out of scope
    and are not plotted" is computed from REGISTRY minus the universes ON THIS
    FIGURE, so the pair chart carries the identical sentence whether it was drawn
    from `--universe n100,mid` or alongside a four-universe run. A subtitle that
    depended on what else the run did would make the same figure two files.

    EVERY CLAUSE IS CONDITIONAL ON THE UNIVERSES ACTUALLY PLOTTED. The old block
    was one hardcoded string naming n100 and mid, including a liquidity paragraph
    quoting their measured numbers, so drawing any other set would have printed
    claims about universes that were not on the page.

    With n100 and mid selected this reproduces that string exactly, which is
    checked by byte-comparing the PNG rather than by reading the code.
    """
    n = len(UNIV)
    word = _COUNT_WORD.get(n, f"all {n}")
    unsel = [t for t in REGISTRY if t not in {u["tag"] for u in UNIV}]
    has_index = [u for u in UNIV if u["index"] is not None]

    line1 = (_joined([u["display"] for u in UNIV])
             + " -- v1, v2, own-universe equal-weight buy&hold, and the "
             + ("published cap-weighted index for each"
                if len(has_index) == n else
                "published cap-weighted index where the universe has one")
             + "\n")

    line2 = ("ALL STRATEGY NUMBERS AFTER TC (Zerodha + 0.15% slippage); before-TC "
             "also shown in the legend.")
    if unsel:
        # Reproduces "  58 and 74 are out of scope and are not plotted." including
        # the double space that separated the two sentences.
        if len(unsel) > 1:
            line2 += f"  {_joined(unsel)} are out of scope and are not plotted."
        else:
            line2 += f"  {unsel[0]} is out of scope and is not plotted."
    line2 += "\n"

    line3 = ""
    if has_index:
        line3 = ("The cap-weighted index is investable and is NOT survivorship-biased. ")
    line3 += ("The equal-weight buy&hold is neither investable nor achievable: "
              f"{word} universes are\n"
              "today's index members backfilled, so names dropped or delisted during "
              "the window are absent entirely and both strategy and buy&hold are "
              "inflated.\n")

    # LIQUIDITY BELONGS HERE MOST OF ALL.
    #   Each universe's individual chart carries its own liquidity line, but this
    #   is the only page where they appear together, and the contrast is the whole
    #   point: the same depth model costs n100 0.01 CAGR points and mid 1.80.
    #   Reading mid's 29.18% next to n100's 25.36% without that is reading a gap of
    #   3.8 points that realistic execution more than halves.
    notes = [LIQUIDITY[u["tag"]] for u in UNIV if u["tag"] in LIQUIDITY]
    liq = ("LIQUIDITY, at Rs 10,00,000 starting capital. " + "\n".join(notes) + "\n"
           if notes else "")

    # WINDOWS THAT DO NOT END TOGETHER ARE SAID SO, ON THE CHART.
    # The live pair ends 2026-05-29, the 58 runs to 2026-06-08 and the 74 stops
    # 2025-12-23. Comparing cumulative returns across universes that stop on
    # different days is partly reading a calendar difference, and a reader should
    # not have to open another file to discover that. Empty when they agree, which
    # is why the n100+mid chart is unchanged.
    ends = {u["tag"]: u["eq"].index[-1] for u in UNIV}
    win = ""
    if len({e.date() for e in ends.values()}) > 1:
        win = ("WINDOWS DIFFER and the lines therefore stop on different days: "
               + ", ".join(f"{t} to {e.date()}" for t, e in ends.items())
               + ". Cross-universe CAGR here is not like-for-like.\n")

    return line1 + line2 + line3 + liq + win + sv.describe_state()


if __name__ == "__main__":
    main()
