"""
numerics.py -- variance and standard deviation that give the same bits on every
platform this project is run on.

WHY THIS EXISTS. Measured 2026-09-24 on macOS arm64, Linux arm64 and Linux
amd64 with the same numpy 2.2.6 and pandas 2.3.3, on identical input:

    pandas Series/DataFrame.rolling(w).std() and .var()   differ on amd64
    pandas groupby(...).transform("var") and ("std")      differ on macOS
    a two-pass variance built from pandas groupby sums    differs on amd64
    numpy nanvar along an axis                            identical on all three
    the two-pass sliding-window variance below            identical on all three

pandas' compiled variance loops update a running sum of squares with a multiply
and an add; whether the compiler fuses those into one rounding differs between
the builds, which is the likely cause (not proven). numpy's nanvar and the
function below compute the mean, then the deviations, then the sum of their
squares, as separate array operations, and no fusion can happen across them.

Before 2026-09-24 the feature builder and the engines used the pandas methods,
and a Linux run gave CAGR 21.58% where macOS gave 21.41% on midcap50 v2.

SEMANTICS MATCH pandas' defaults: sample variance (ddof=1), NaN ignored inside
a window, NaN where fewer than max(min_periods, 2) values are present,
min_periods defaulting to the window. The values are not bit-identical to the
pandas methods -- the order of operations differs -- which is why every
published figure was rebuilt when this module was adopted.
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def _rolling_var_1d(x, window, min_periods):
    x = np.asarray(x, dtype="float64")
    n = len(x)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    # PAD THE FRONT so the first window-1 positions are partial windows, as in
    # pandas, which computes them when min_periods < window.
    xp = np.concatenate([np.full(window - 1, np.nan), x])
    win = sliding_window_view(xp, window)
    ok = ~np.isnan(win)
    cnt = ok.sum(axis=1)
    mean = np.where(ok, win, 0.0).sum(axis=1) / np.maximum(cnt, 1)
    dev = np.where(ok, win - mean[:, None], 0.0)
    ss = (dev * dev).sum(axis=1)
    need = max(min_periods, 2)
    return np.where(cnt >= need, ss / np.maximum(cnt - 1, 1), np.nan)


def rolling_var(obj, window, min_periods=None):
    """Sample variance over a trailing window, for a Series or each DataFrame column."""
    mp = window if min_periods is None else min_periods
    if isinstance(obj, pd.DataFrame):
        return pd.DataFrame({c: _rolling_var_1d(obj[c].to_numpy(), window, mp)
                             for c in obj.columns}, index=obj.index)[obj.columns]
    return pd.Series(_rolling_var_1d(obj.to_numpy(), window, mp),
                     index=obj.index, name=obj.name)


def rolling_std(obj, window, min_periods=None):
    """Square root of rolling_var. sqrt is correctly rounded, so it adds no drift."""
    return np.sqrt(rolling_var(obj, window, min_periods))


def group_mean_std(values, groups):
    """Per-row mean and sample standard deviation of `values` within `groups`.

    Replaces groupby(groups).transform("mean") / ("std"). The values are laid
    out as a (group x position) matrix and reduced with numpy nanmean and
    nanvar along rows. Returns two arrays aligned with `values`.
    """
    v = np.asarray(values, dtype="float64")
    gcode, _ = pd.factorize(np.asarray(groups), sort=True)
    order = np.argsort(gcode, kind="stable")
    counts = np.bincount(gcode)
    pos = np.empty(len(v), dtype=np.int64)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    pos[order] = np.arange(len(v)) - np.repeat(starts, counts)
    M = np.full((len(counts), counts.max() if len(counts) else 0), np.nan)
    M[gcode, pos] = v
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mu = np.nanmean(M, axis=1)
            sd = np.sqrt(np.nanvar(M, axis=1, ddof=1))
    return mu[gcode], sd[gcode]
