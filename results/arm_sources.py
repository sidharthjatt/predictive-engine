"""
arm_sources.py -- where each arm's curve and per-trade log live, for one universe.

WHY THIS IS ONE MODULE AND NOT FOUR COPIES
    make_combined_universes, make_final_chart_fair, make_mid_chart and
    make_n100_chart each need the same three facts about an arm: its equity
    curve, its per-trade log, and whether it is deployed below 100%. Those facts
    are spread over three files with three naming conventions:

        v1, v2   equity in v2FINAL_equity.csv     (arm-keyed on the live
                 universes, `strategy`/`baseline_invvol` on the frozen ones)
        v3, v4   equity in v34_equity.csv
        v1       trades in daily_trades_v1_<tag>.csv   -- written by the engine
        v2       trades in daily_trades_<tag>.csv      -- the v2 audit trail
        v3, v4   trades in daily_trades_<tag>_<arm>.csv -- the per-arm trails

    Four charts each rediscovering that is four chances to disagree. They ask
    here instead.

AVAILABILITY IS A FACT, NOT AN ERROR
    A frozen universe has no v3 or v4 at all, and an arm-subset run has no files
    for an arm it did not measure. available() answers which arms this universe
    can actually show, and the caller decides what to do about the rest. That is
    why nothing here raises.
"""
from pathlib import Path

import pandas as pd

import arms.registry as arm_reg


def equity_path_and_series(M, tag, arm_name):
    """(source file, curve) for one arm, or (None, None) if it is not recorded."""
    M = Path(M)
    f = M / "v2FINAL_equity.csv"
    if f.exists():
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date")
        s = arm_reg.equity_series(df, arm_name)
        if s is not None:
            return f, s
    # v3/v4 are measurement arms and live in the v34 panel. The suffixed name is
    # tried first because an arm-subset run writes v34_equity_v1_v3.csv and leaves
    # the canonical four-arm file from an earlier run in place -- reading the
    # canonical one there would show a curve this run did not produce.
    for name in (f"v34_equity{arm_reg.selection_suffix()}.csv", "v34_equity.csv"):
        g = M / name
        if g.exists():
            df = pd.read_csv(g, parse_dates=["date"]).set_index("date")
            col = arm_reg.ARMS[arm_name].equity_column
            if col in df.columns:
                return g, df[col]
    return None, None


def trades_path(M, tag, arm_name):
    """The per-trade log for one arm, or None if it was not written.

    THE THREE CONVENTIONS ARE HISTORICAL AND ARE NOT UNIFIED HERE. v2's log is
    unsuffixed because the Nautilus verification reads that exact name; v1's is
    written by the engine under its own older spelling; v3 and v4 use the per-arm
    audit trail. Renaming any of them is a separate change with its own gate.
    """
    M = Path(M)
    for cand in ({"v1": f"daily_trades_v1_{tag}.csv",
                  "v2": f"daily_trades_{tag}.csv"}.get(arm_name),
                 f"daily_trades_{tag}_{arm_name}.csv"):
        if cand is not None and (M / cand).exists():
            return M / cand
    return None


def available(M, tag, names=None):
    """The arms this universe can actually show, in ARMS order.

    An arm counts only when BOTH its curve and its per-trade log are on disk: the
    charts quote a before-TC CAGR, which is the curve with the cost drag removed,
    so a curve without its costs would be plotted with a silently wrong legend.
    """
    want = arm_reg.selected_names() if names is None else [
        a.name if hasattr(a, "name") else a for a in names]
    out = []
    for n in arm_reg.ARMS:
        if n not in want:
            continue
        _, s = equity_path_and_series(M, tag, n)
        if s is not None and trades_path(M, tag, n) is not None:
            out.append(n)
    return out


def deployed_pct(arm_name, breadth_inv):
    """Average deployed capital for an arm, in percent.

    The breadth-scaled arms (v2, v4) deploy `breadth_inv`; the always-invested
    ones (v1, v3) deploy 100. v2 and v4 share a number because breadth is
    mean(mom20 > 0) and does not depend on the sizing rule -- the two arms differ
    in how they split the money, not in how much of it they put to work.
    """
    return breadth_inv if arm_reg.ARMS[arm_name].mode == "breadth" else 100
