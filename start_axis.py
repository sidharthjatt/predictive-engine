"""
start_axis.py -- the BACKTEST START axis. Default 2019-01-01, and the default is
unsuffixed.

config.BT_START_DATE is the one setting. This module changes it: run.py --start
calls set_selection() once, before the plan is built and before pit variants are
made (universes.registry.use_pit takes each row's start from date_range), and
every static registry row's date_range is moved to the selected start. Code that
means "the backtest start" reads config.BT_START_DATE at call time.

THE SCORING FLOOR FOLLOWS THE START. engine_core.score_floor() is the first day of
the month SCORE_LEAD_YEARS before the start: 2016-01-01 for the default start,
which is exactly the `year >= 2016` the scoring loop used until 2026-10-22, so a
default run scores the same months. Scores before the start are read by no
backtest; the lead keeps the out-of-window scores param_surface.py's earlier
window and the IC diagnostics have always had.

The eleventh axis, appended after fixed in naming.AXES. The suffix is "" at the
default, so no existing name moves; otherwise "_s<yyyymmdd>" after every other
suffix and "@s<yyyymmdd>" in directory segments.
"""
import pandas as pd

import config

DEFAULT = config.BT_START_DEFAULT
SCORE_LEAD_YEARS = 3

_SELECTED = None


def set_selection(start):
    """Record this run's backtest start and apply it. None restores the default.

    Moves config.BT_START_DATE and the start of every registry row whose
    date_range starts at the current setting. Call it before use_pit: a pit row's
    start is the later of this and its first membership row, taken when the pit
    variant is made.
    """
    global _SELECTED
    new = DEFAULT if start is None else pd.Timestamp(start)
    if new >= config.BT_END_DATE:
        raise ValueError(f"backtest start {new.date()} is not before the end "
                         f"{config.BT_END_DATE.date()}")
    import dataclasses
    from universes.registry import REGISTRY
    old = config.BT_START_DATE
    for tag, u in list(REGISTRY.items()):
        d0, d1 = u.date_range
        if pd.Timestamp(d0) == old:
            REGISTRY[tag] = dataclasses.replace(u, date_range=(new, d1))
    config.BT_START_DATE = new
    _SELECTED = None if new == DEFAULT else new


def selected():
    """The backtest start, a Timestamp."""
    return config.BT_START_DATE


def is_default():
    return _SELECTED is None


def suffix():
    """"" at the default start, else "_s20070924" -- the artefact name tail."""
    return "" if is_default() else f"_s{_SELECTED:%Y%m%d}"


def segment():
    """"" at the default start, else "@s20070924" -- the directory segment tail."""
    return "" if is_default() else f"@s{_SELECTED:%Y%m%d}"


def label():
    """The chart-title fragment, "" at the default."""
    return "" if is_default() else f"start {_SELECTED.date()}"


def score_floor():
    """The first session month the scoring step scores: SCORE_LEAD_YEARS before
    the backtest start, from the first day of that month."""
    s = config.BT_START_DATE - pd.DateOffset(years=SCORE_LEAD_YEARS)
    return pd.Timestamp(s.year, s.month, 1)
