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
import cadence


def _axes(*, for_arm_subset=False):
    """This run's artefact name tail: cadence AND profile AND tax, never a subset.

    ALL THREE OR NONE. The profile was absent here while `cadence` was present,
    which is the whole shape of the bug this function was rewritten to remove --
    and then the TAX term was absent while both of the others were present, which
    is the same bug a second time in the same function.

    MEASURED 2026-09-18, BEFORE THE FIX: under `--tax on` this returned
    v2FINAL_equity.csv, daily_trades_midcap50.csv and v34_equity.csv -- byte-
    identical paths to the tax=off selection. This is make_chart's source lookup
    (STEP 10t), so chart_<tag>_..._tax.png was drawn with a correct name over
    UNTAXED arm series, while make_chart.py:161's own _ci() composed all four
    axes. ONE STEP, TWO CONVENTIONS, and the chart that came out of it was
    part-taxed rather than wrong in a way anybody would notice.

    THE RULE THIS FUNCTION NOW FOLLOWS is make_chart.py:161's, which is the same
    chain in the same order. See KNOWN_ISSUES.md instance 6: this is the fourth
    time a hand-composed chain has been under-specified, and the reason the list
    of thirteen such sites is worth reading before adding a fifth axis.
    """
    import profiles as _pf
    import tax as _tax
    sfx = cadence.suffix() + _pf.suffix() + _tax.suffix()
    return (arm_reg.selection_suffix() + sfx) if for_arm_subset else sfx


def describe(path, n=None, unit="rows"):
    """A provenance line naming the file a figure was actually read from.

    FORMAT TAKEN FROM `diagnostics/attribution_v2.txt`, which already prints
    `source daily_trades_n100.csv, 978 fills, mtime 2026-09-04 14:02 (local)`.
    The precedent and the format both existed; nothing else used them.
    """
    from datetime import datetime
    path = Path(path)
    try:
        mt = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        mt = "unknown"
    count = f", {n:,} {unit}" if n is not None else ""
    return f"source {path.name}{count}, mtime {mt} (local)"


def equity_path_and_series(M, tag, arm_name):
    """(source file, curve) for one arm, or (None, None) if THIS RUN did not write one.

    FAIL-CLOSED. THERE IS NO FALLBACK TO A DIFFERENT FILE, BY DESIGN.
    This function used to compose `v2FINAL_equity{cadence}.csv`, and when that did
    not exist fall through to the unsuffixed `v2FINAL_equity.csv`. The v34 chain
    fell through twice, ending at a bare `v34_equity.csv`. Neither rung composed
    the PROFILE at all.

    WHAT THAT COST, MEASURED. The engines suffix their output by cadence AND
    profile (`engine_v2_final_mid.py:_c`). So under `--profile tradeable` the
    engine wrote `v2FINAL_equity_tradeable.csv`, this function looked for
    `v2FINAL_equity.csv`, found the RESEARCH file, and returned research curves to
    a caller drawing a chart titled tradeable. Silently, and with the substitution
    unrecorded: the caller received the path and discarded it.

    THIS IS NOT HYPOTHETICAL AND IT IS NOT NEW. `make_combined_universes.py`'s
    `_ci` carried exactly this defect -- cadence composed, profile omitted, silent
    fall-through to the canonical file -- and it fed THESE SAME THREE CHARTS. It
    was found and fixed on 2026-09-12. This function is the same defect in the same
    repository on the same code path, and it survived that fix because the audit
    measured writers and nothing measured readers.

    THE PATTERN IS `audit_step.py:160-176`, three files away, which has composed
    both axes and returned None rather than substituting since the profile existed.
    Its docstring records the measured cost of the cadence half: reconciling a
    cadence-40 trail against a cadence-20 curve reported v1 MISMATCH Rs 2,923,934
    and v2 MISMATCH Rs 1,825,210 on mid. Returning None there made it safe BY
    DESIGN rather than by accident. This does the same.

    None means THIS RUN did not write a curve for this arm. The caller reports that
    and plots nothing, which is the correct outcome: a chart with a curve missing
    is a visible defect, and a chart with the wrong curve is not.
    """
    from config import read_table  # lazy: this module is imported without the repo root on sys.path
    M = Path(M)
    # ONE NAME PER CHAIN. Not a candidate list -- a candidate list IS the fallback.
    f = M / f"v2FINAL_equity{_axes()}.csv"
    if f.exists():
        df = read_table(f, parse_dates=["date"]).set_index("date")
        s = arm_reg.equity_series(df, arm_name)
        if s is not None:
            return f, s
    # v3/v4 are measurement arms and live in the v34 panel. The arm-subset suffix is
    # part of the composed name, not a rung above a canonical one: an arm-subset run
    # writes v34_equity_v1_v3.csv, and the four-arm file left over from an earlier
    # run describes a selection this run did not make. At a full selection
    # selection_suffix() is "" and this IS the canonical name.
    g = M / f"v34_equity{_axes(for_arm_subset=True)}.csv"
    if g.exists():
        df = read_table(g, parse_dates=["date"]).set_index("date")
        col = arm_reg.ARMS[arm_name].equity_column
        if col in df.columns:
            return g, df[col]
    return None, None


def trades_path(M, tag, arm_name):
    """The per-trade log THIS RUN wrote for one arm, or None. Fail-closed.

    THE THREE SPELLINGS ARE HISTORICAL AND ARE NOT UNIFIED HERE. v2's log is
    unsuffixed in its BODY because the Nautilus verification reads that exact name;
    v1's is written by the engine under its own older spelling; v3 and v4 use the
    per-arm audit trail. Renaming any of them is a separate change with its own gate.

    WHAT WAS REMOVED. Each spelling used to be tried twice -- once with the cadence
    suffix and once without -- so a run whose composed log was absent silently read
    the unsuffixed one. As with the curve above, the profile was never composed at
    all, so a tradeable run read the research trade log and computed a before-TC
    figure from costs that were never incurred. The axis tail is now composed once
    and there is no second rung.
    """
    M = Path(M)
    sfx = _axes()
    for cand in ({"v1": f"daily_trades_v1_{tag}{sfx}.csv",
                  "v2": f"daily_trades_{tag}{sfx}.csv"}.get(arm_name),
                 f"daily_trades_{tag}_{arm_name}{sfx}.csv"):
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
