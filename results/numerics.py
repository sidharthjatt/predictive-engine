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

    Replaces groupby(groups).transform("mean") / ("std"). NaN is ignored; a group
    with no value has mean NaN and one with fewer than two has sd NaN. Returns two
    arrays aligned with `values`.

    EACH GROUP DEPENDS ON ITS OWN VALUES ONLY, SINCE 2026-10-22. Until then the
    values were laid out as one (group x position) matrix as wide as the LARGEST
    group and reduced with nanmean and nanvar along rows. numpy's pairwise
    summation splits a row by the row's length, so the last bits of every date's
    mean and sd depended on the widest cross-section of any date, later dates
    included: tools/lookahead_proof.py found the z-scored features of 2009 changed
    when data after 2019 was removed. Now each group's sum is math.fsum, the
    correctly rounded sum, which depends only on the group's values (not their
    order or any other group), and is the same on every platform.
    """
    import math
    v = np.asarray(values, dtype="float64")
    gcode, _ = pd.factorize(np.asarray(groups), sort=True)
    order = np.argsort(gcode, kind="stable")
    counts = np.bincount(gcode)
    bounds = np.concatenate([[0], np.cumsum(counts)])
    mu_g = np.full(len(counts), np.nan)
    sd_g = np.full(len(counts), np.nan)
    sv = v[order]
    for g in range(len(counts)):
        x = sv[bounds[g]:bounds[g + 1]]
        x = x[~np.isnan(x)]
        n = len(x)
        if n == 0:
            continue
        m = math.fsum(x.tolist()) / n
        mu_g[g] = m
        if n > 1:
            d = x - m
            sd_g[g] = math.sqrt(math.fsum((d * d).tolist()) / (n - 1))
    return mu_g[gcode], sd_g[gcode]
