"""
market_data.py -- everything between the raw price files and a feature panel.

Sections, in order:
  1. reading price and panel files (read_price_csv, read_table, write_panel)
  2. platform-identical variance (rolling_var, rolling_std, group_mean_std)
  3. features (FEATS_V2 and the three feature builders)
  4. prices, the trading calendar and the panel (canonical_price, build_panel)
  5. point-in-time membership (Membership, load, apply_to_panel, member_mask,
     MEMBERSHIP for the run)
  6. tradability: a name trades only on a session with a row (tradeable_on)

The model fit, monthly scoring and the score-cache keys are in model.py.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

import settings
from settings import PROJECT_ROOT, list_dir


# ======================================================================================
# READING PRICE AND PANEL FILES. From config.py (moved 2026-11-27).
# ======================================================================================

# ============================================================================
# CENTRAL DATE HANDLING -- read every raw data file through this.
# Whatever the format (ISO / M-D-Y / D-M-Y / D-Mon-Y), it is auto-detected and
# converted to datetime. For a new data source, use read_price_csv() and nothing
# else needs to change.
#
# Detection is driven by evidence, not by guessing:
#   a value above 12 in slot 1  -> that slot is the DAY  -> dayfirst=True
#   a value above 12 in slot 2  -> that slot is the DAY  -> dayfirst=False
#   above 12 in both slots      -> corrupt or mixed -> raise (never fail silently)
#   never above 12 anywhere     -> genuinely ambiguous -> warn and assume DD-MM
# ============================================================================


def smart_parse_dates(s, source=""):
    """Detect the date format from the data itself and return datetimes."""
    s = pd.Series(s).astype(str).str.strip()
    sample = s[s.ne("") & s.ne("nan")]
    if len(sample) == 0:
        return pd.to_datetime(s, errors="coerce")

    # ISO (YYYY-MM-DD) -- unambiguous, year first
    if sample.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}").mean() > 0.9:
        return pd.to_datetime(s, errors="coerce")

    parts = sample.str.extract(r"^(\d{1,4})[-/](\d{1,4})[-/]")
    if parts.isna().all().any():          # e.g. 03-Jan-2000
        return pd.to_datetime(s, errors="coerce", dayfirst=True)

    a = pd.to_numeric(parts[0], errors="coerce")
    b = pd.to_numeric(parts[1], errors="coerce")
    first_is_day, second_is_day = bool((a > 12).any()), bool((b > 12).any())

    if first_is_day and second_is_day:
        raise ValueError(
            f"Ambiguous/corrupt dates in {source or 'input'}: "
            "both first and second slot exceed 12. Check the file."
        )
    if first_is_day:
        return pd.to_datetime(s, errors="coerce", dayfirst=True)
    if second_is_day:
        return pd.to_datetime(s, errors="coerce", dayfirst=False)

    print(f"    [WARN] {source or 'input'}: date format ambiguous "
          "(no day > 12 anywhere) -- assuming DD-MM. Verify if this is new data.")
    return pd.to_datetime(s, errors="coerce", dayfirst=True)


# ---------------------------------------------------------------------------
# THE ONE READER FOR TABULAR DATA, AND THE ONE WRITER FOR PANELS
# ---------------------------------------------------------------------------
# MEASURED 2026-09-24 ON macOS arm64, Linux arm64 AND Linux amd64, same pandas
# 2.3.3: pandas' default read_csv float parser returns different last bits for
# the SAME bytes on macOS and on Linux (over a million cells of midcap50's raw
# panel), and on either platform it does not return the values the file was
# written from. float_precision="round_trip" is exact and identical on all
# three. A second checkout on another OS therefore read different scores from
# the same score panel. Every read of a CSV in this repository goes through
# read_table(); csv_reader_check.py fails on any pandas.read_csv call anywhere
# else.
#
# THE PANELS ARE PARQUET, not CSV: a binary column store round-trips float64
# exactly with no parsing at all. read_table() dispatches on the suffix, so a
# caller does not need to know which format a file is.
_PARQUET_KW = {"parse_dates", "usecols", "columns", "nrows"}


def read_table(path, **kw):
    """Read a CSV or parquet file exactly. CSV floats are parsed round-trip."""
    p = Path(path)
    if p.suffix == ".parquet":
        bad = set(kw) - _PARQUET_KW
        if bad:
            raise TypeError(f"read_table({p.name}): {sorted(bad)} has no meaning "
                            f"for a parquet file")
        cols = kw.get("usecols", kw.get("columns"))
        df = pd.read_parquet(p, columns=list(cols) if cols is not None else None)
        for c in kw.get("parse_dates") or []:
            if c in df.columns and not pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = pd.to_datetime(df[c])
        return df.head(kw["nrows"]) if kw.get("nrows") is not None else df
    if "float_precision" in kw:
        raise TypeError("read_table: float_precision is fixed to round_trip")
    return pd.read_csv(p, float_precision="round_trip", **kw)


def write_panel(df, path):
    """Write a score or raw panel as parquet. Integer columns are written as
    int64, the dtype the CSV panels were read back as before 2026-09-24."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_integer_dtype(df[c]) and df[c].dtype != "int64":
            df[c] = df[c].astype("int64")
    # naming: axis-free -- the path is a registry cache attribute; panels carry no run axis
    df.to_parquet(path, index=False)


def read_price_csv(path, date_col="date", **kw):
    """Read any raw price CSV; dates auto-normalised to datetime."""
    df = read_table(path, **kw)
    if date_col in df.columns:
        df[date_col] = smart_parse_dates(df[date_col], source=str(path))
    return df


# ======================================================================================
# PLATFORM-IDENTICAL VARIANCE. From numerics.py (moved 2026-11-27).
# ======================================================================================
# numerics.py -- variance and standard deviation that give the same bits on every
# platform this project is run on.
#
# WHY THIS EXISTS. Measured 2026-09-24 on macOS arm64, Linux arm64 and Linux
# amd64 with the same numpy 2.2.6 and pandas 2.3.3, on identical input:
#
#     pandas Series/DataFrame.rolling(w).std() and .var()   differ on amd64
#     pandas groupby(...).transform("var") and ("std")      differ on macOS
#     a two-pass variance built from pandas groupby sums    differs on amd64
#     numpy nanvar along an axis                            identical on all three
#     the two-pass sliding-window variance below            identical on all three
#
# pandas' compiled variance loops update a running sum of squares with a multiply
# and an add; whether the compiler fuses those into one rounding differs between
# the builds, which is the likely cause (not proven). numpy's nanvar and the
# function below compute the mean, then the deviations, then the sum of their
# squares, as separate array operations, and no fusion can happen across them.
#
# Before 2026-09-24 the feature builder and the engines used the pandas methods,
# and a Linux run gave CAGR 21.58% where macOS gave 21.41% on midcap50 v2.
#
# SEMANTICS MATCH pandas' defaults: sample variance (ddof=1), NaN ignored inside
# a window, NaN where fewer than max(min_periods, 2) values are present,
# min_periods defaulting to the window. The values are not bit-identical to the
# pandas methods -- the order of operations differs -- which is why every
# published figure was rebuilt when this module was adopted.


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


# ======================================================================================
# FEATURES. From features_v2.py (moved 2026-11-27).
# ======================================================================================
# features_v2.py -- Feature set v2: breaking the dependence on momentum
# =====================================================================
# Problem (identified by diagnose_alpha.py): around 10 of the previous 16 features
# were momentum. The model rested on a single factor, and when momentum broke down
# in 2022 and 2025 the IC went negative and the strategy died with it.
#
# Fix: five distinct factor families. Each measures something different, so when one
# family fails the others can carry the signal.
#
#   A) MOMENTUM (kept, but reduced)          -- trend continuation
#   B) REVERSAL                              -- short-term overreaction snap-back
#   C) VOLATILITY / RISK                     -- idio vol, beta, downside vol
#   D) LIQUIDITY / VOLUME                    -- Amihud illiquidity, turnover, vol-price divergence
#   E) QUALITY OF TREND                      -- consistency, path smoothness
#
# Everything is causal: only data up to time t, no lookahead anywhere.
# Beta and idiosyncratic vol are measured against the market, where the market is the
# equal-weight universe built from past prices only -- no external index is used.
#
# This file is only the feature builder. The engine imports it.


FEATS_V2 = [
    # --- A. Momentum (3 only, not 6) ---
    "mom_20", "mom_120", "mom_12_1",
    # --- B. Reversal ---
    "rev_5", "rev_1",
    # --- C. Volatility / Risk ---
    "vol_20", "vol_ratio", "idio_vol_60", "beta_60", "downside_vol_60",
    # --- D. Liquidity / Volume ---
    "amihud_20", "turnover_z", "vol_price_div",
    # --- E. Trend quality ---
    "trend_consistency_20", "path_smooth_60", "dist_high_252",
    # --- F. Cross-sectional context (added at panel level) ---
    "rsi_14",
]


# Daily-return bounds beyond which a move is treated as a DATA ARTEFACT, not a
# price move. Measured on a retired universe: 32 returns across 10 symbols exceed these, and
# 29 of the 32 fall on the 1st to 3rd of a month -- the signature of a series
# stitched across sources or frequencies, not of clean corporate actions.
#
# No split ratio is inferred. Without corporate-action data that would be
# guesswork, and a wrong ratio is worse than a gap. The return is set to NaN and
# the existing NaN handling takes over: vol_20, downside_vol_60, beta_60 and
# idio_vol_60 all go NaN across their windows, so dropna(subset=FEATS_V2) removes
# the contaminated rows outright.
#
# LIMITATION, STATED RATHER THAN HIDDEN: features built directly from `close`
# (mom_20, mom_120, mom_12_1, dist_high_252, path_smooth_60) still span the price
# level shift on rows far enough away to survive the drop. Only return-based
# features are fully protected. Repairing the level needs the corporate-action
# data this project does not have.
EXTREME_RET_HI = 0.55


EXTREME_RET_LO = -0.35


def add_stock_features(df):
    """Per-stock features. df needs: date, open, high, low, close, volume, raw_close.

    `close` is the adjusted price and every return-based feature uses it.
    `raw_close` is the unadjusted close, used only for amihud_20's rupee volume:
    adj_close is back-adjusted for dividends paid AFTER the row's date and volume
    is not, so a rupee volume built from adj_close would depend on later sessions.
    """
    df = df.sort_values("date").copy()
    c = df["close"]
    v = df["volume"]
    r = c.pct_change()
    # Flag before any feature consumes r, so nothing downstream sees the artefact.
    bad = (r > EXTREME_RET_HI) | (r < EXTREME_RET_LO)
    df["bad_ret"] = bad.fillna(False)
    r = r.mask(bad)
    df["ret_1d"] = r

    # ---------------- A. MOMENTUM (trimmed) ----------------
    df["mom_20"] = c / c.shift(20) - 1
    df["mom_120"] = c / c.shift(120) - 1
    # classic 12-1: 12-month momentum SKIPPING the last month, to avoid reversal
    df["mom_12_1"] = c.shift(21) / c.shift(252) - 1

    # ---------------- B. REVERSAL ----------------
    # short-term losers bounce back (a documented anomaly, the inverse of momentum)
    df["rev_5"] = -(c / c.shift(5) - 1)
    df["rev_1"] = -r

    # ---------------- C. VOLATILITY / RISK ----------------
    # Rolling std kept after testing EWMA both ways (see note below).
    # EWMA tested: RiskMetrics 0.94/0.97 and horizon-matched 0.9524/0.9836.
    # Both were worse on BOTH universes and broke inverse-vol validation
    # (T2 seed / T3 sub-period / T4 window all failed vs 4/4 PASS on rolling).
    df["vol_20"] = rolling_std(r, 20)
    vol_60 = rolling_std(r, 60)
    df["vol_ratio"] = df["vol_20"] / (vol_60 + 1e-9)      # is volatility expanding or contracting
    # downside vol: std of negative days only (asymmetric risk)
    df["downside_vol_60"] = rolling_std(r.where(r < 0), 60, min_periods=20)

    # ---------------- D. LIQUIDITY / VOLUME ----------------
    # Amihud illiquidity: |return| / rupee volume. High = illiquid = risk premium
    rupee_vol = df["raw_close"] * v
    df["amihud_20"] = (r.abs() / (rupee_vol + 1)).rolling(20).mean() * 1e9
    vm = v.rolling(60).mean()
    vs = rolling_std(v, 60)
    df["turnover_z"] = (v.rolling(5).mean() - vm) / (vs + 1e-9)
    # volume-price divergence: price up but volume down = weak move
    px_dir = np.sign(c / c.shift(5) - 1)
    vol_dir = np.sign(v.rolling(5).mean() / v.rolling(20).mean() - 1)
    df["vol_price_div"] = px_dir * vol_dir

    # ---------------- E. TREND QUALITY ----------------
    # what share of days were positive (a smooth uptrend vs a single-day jump)
    df["trend_consistency_20"] = (r > 0).rolling(20).mean()
    # path smoothness: net move / total absolute movement. 1 = straight line
    net = (c - c.shift(60)).abs()
    total = r.abs().rolling(60).sum() * c.shift(60)
    df["path_smooth_60"] = net / (total + 1e-9)
    df["dist_high_252"] = c / c.rolling(252).max() - 1

    # ---------------- RSI (kept, it's not pure momentum) ----------------
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi_14"] = 100 - 100 / (1 + up / (dn + 1e-9))

    return df


def add_market_relative_features(panel, member_col=None):
    """Beta and idiosyncratic volatility, measured against the market.
    Market = the equal-weight return of the universe (past-only, no lookahead).
    This has to happen at panel level because the market is built from all stocks.

    `member_col` names a boolean column; when given, the market on each date is
    the mean over the rows where it is True. build_panel passes the point-in-time
    membership, so in a pit run the market is the members on the date. None, or
    an all-True column, averages every row, as static mode does.
    """
    panel = panel.sort_values(["symbol", "date"]).copy()

    # market return: the mean of the available stocks each day (point-in-time)
    _in = panel if member_col is None else panel[panel[member_col].astype(bool)]
    mkt = _in.groupby("date")["ret_1d"].mean().rename("mkt_ret")
    panel = panel.merge(mkt, on="date", how="left")

    # beta = cov(y, x) / var(x) over 60d; idio_vol = std(y - beta*x) over 60d
    #
    # THE 60-DAY WINDOW RUNS OVER EACH SYMBOL'S OWN TRADING DATES, NOT THE UNION.
    #     An earlier version rolled over a wide pivot indexed by the UNION of every
    #     symbol's dates. On that index a symbol is NaN on any day it did not trade,
    #     and pandas' rolling(60) needs 60 non-NaN observations, so a single missing
    #     day voided that symbol's next 60 windows.
    #
    #     Harmless on the two retired universes, where essentially every name traded
    #     every day. Fatal on MidCap150, where median per-symbol coverage of the union
    #     index is 70.6%: beta_60 survived on 42.1% of rows and idio_vol_60 on
    #     35.7%, against 93.8-100% for the other fifteen features. Since the panel
    #     drops any row with a NaN feature, only 32.9% of rows survived, and the
    #     symbols that fell out were forward-filled to a flat price -- giving them
    #     exactly zero momentum, which silently pushed breadth from 0.550 to 0.202.
    #
    #     Computing per symbol removes the coupling: a gap in one name can no longer
    #     void windows in that name, and never could in any other. Where a symbol
    #     trades every union date the two are arithmetically identical, which is why
    #     a retired universe was the control for this change.
    #
    # The formulas, the window and the ddof convention below are unchanged. Only the
    # index the window runs over is different.
    W = 60
    y = panel.pivot(index="date", columns="symbol", values="ret_1d")
    x = mkt.reindex(y.index)

    betas, idios = {}, {}
    for sym in y.columns:
        ys = y[sym].dropna()                 # this symbol's own trading dates
        if len(ys) < W:
            continue
        xs = x.reindex(ys.index)             # the market on those same dates

        xm = xs.rolling(W).mean()
        xv = rolling_var(xs, W)
        ym = ys.rolling(W).mean()
        xy = (ys * xs).rolling(W).mean()
        cov = xy - ym * xm                                   # E[xy] - E[x]E[y]
        b = cov / (xv * (W - 1) / W + 1e-12)                 # match pandas ddof

        betas[sym] = b
        idios[sym] = rolling_std(ys - b * xs, W)

    beta = pd.DataFrame(betas).reindex(y.index)
    idio = pd.DataFrame(idios).reindex(y.index)

    b_long = beta.stack().rename("beta_60").reset_index()
    i_long = idio.stack().rename("idio_vol_60").reset_index()
    b_long.columns = ["date", "symbol", "beta_60"]
    i_long.columns = ["date", "symbol", "idio_vol_60"]
    panel = panel.merge(b_long, on=["date", "symbol"], how="left")
    panel = panel.merge(i_long, on=["date", "symbol"], how="left")
    return panel


def cross_sectional_normalize(panel, feats):
    """Z-score every feature across the cross-section, each day.
    Why: volatility levels in 2020 were nothing like 2016, so comparing absolute
    values across time is wrong. What matters is where a stock stands relative to
    its peers ON THAT DAY. This is the main fix for regime drift.
    """
    # THE MEAN AND STANDARD DEVIATION COME FROM numerics.group_mean_std, not
    # groupby().transform("mean"/"std"): pandas' grouped variance gave different
    # last bits on macOS and Linux, and every feature passes through here.
    out = panel.copy()
    for f in feats:
        mu, sd = group_mean_std(out[f].to_numpy(), out["date"].to_numpy())
        out[f] = ((out[f] - mu) / (sd + 1e-9)).clip(-3, 3)   # winsorize at 3 sigma
    return out


# ======================================================================================
# PRICES, TRADING CALENDAR AND THE PANEL. From engine_core.py (moved 2026-11-27).
# ======================================================================================

# ---------------------------------------------------------------------------
# THE CANONICAL PRICE COLUMN -- adj_close, repaired, applied at the load boundary
# ---------------------------------------------------------------------------
# adj_close IS THE PRICE. close is the fallback and nothing else.
#
# WHY THE FALLBACK EXISTS AND WHY IT IS NOT AN INTERPOLATION
#     adj_close is unusable on exactly 219 rows in three symbols: VEDL (170 rows,
#     2003, nifty100_benchmark), ASHOKLEY (41 rows, 2003, MidCap150/clean) and
#     MAZDOCK (8 rows, 2017-12 to 2018-07, nifty100_benchmark). On 216 of those it
#     is 0.00; on all 219 it sits outside its own session's [low, high], which is
#     provably wrong from the row alone. Those rows take `close`.
#
#     Nothing is interpolated, carried forward, or reconstructed from an inferred
#     ratio. A repaired price that LOOKS continuous is worse than an honest one:
#     it would hide the defect from every downstream check instead of surfacing it.
#     Fallback to close, or nothing.
#
# THE WHOLE BAR MOVES TOGETHER, NOT JUST THE CLOSE
#     `open` has no adjusted counterpart in the source data, and op is the FILL
#     PRICE for every buy and every sell (test_exposure.py:152) while px is what
#     the book is VALUED at. Leaving open on the raw basis while close moves to the
#     adjusted one puts the fill and the valuation on two different bases, and the
#     same-day open->close return is then wrong by exactly (ratio - 1) on every
#     affected row -- measured across midcap150 and nifty100: 5,974 rows in full history,
#     1,907 inside the backtest window, median |ratio-1| 2.18%, p95 10.5%,
#     max 150.3%. That is a manufactured P&L on any name filled that morning.
#
#     So open is scaled by the SAME per-row ratio, and so are high and low.
#     Scaling open alone would leave it outside its own [low, high] on 275 rows --
#     re-creating, in the traded column, precisely the defect the fallback above
#     exists to remove. high and low are loaded but consumed by nothing today
#     (no feature and no backtest reads them), so scaling them is numerically
#     inert; it is done anyway so the bar stays internally consistent for whoever
#     reads it next. Raw `open` lies inside its own [low, high] on 1,546,393 of
#     1,546,394 rows across all four universes, so a positive per-row scale
#     preserves that containment exactly.
#
# WHERE THE RATIO IS 1, THE ROW IS UNTOUCHED, BIT FOR BIT
#     ratio = price / close, and price == close on every fallback row and on every
#     row where the two columns already agree. Multiplying by a literal 1.0 is
#     exact in IEEE-754.
#
# THE COUNT IS LOGGED AT RUN TIME
#     A data refresh that quietly increased the number of unusable adj_close rows
#     would otherwise be absorbed in silence. build_panel prints the total and the
#     per-symbol breakdown, so an increase shows up in the run log.
PRICE_COLS = ["date", "open", "high", "low", "close", "adj_close", "volume"]


def canonical_price(raw):
    """Return (df, n_fallback) with adj_close as the price column.

    `raw` needs open/high/low/close/adj_close. The returned frame carries the same
    column names -- `close` now HOLDS the canonical price, and open/high/low are on
    that same basis -- so every downstream consumer inherits the switch without
    knowing it happened. adj_close is dropped: keeping it would leave two columns
    claiming to be the adjusted price.
    """
    d = raw.copy()
    a, lo, hi = d["adj_close"], d["low"], d["high"]
    # Evaluated against the RAW low/high, which is the point: the test asks whether
    # adj_close belongs to the same session as the bar it is filed under. Scaling
    # first would make the comparison circular and always pass.
    bad = (a <= 0) | (a < lo) | (a > hi)
    price = a.where(~bad, d["close"])
    # close > 0 on every row of every universe (checked: 0 non-positive closes in
    # 1,546,394 rows), so this division cannot produce an inf through the fallback.
    ratio = price / d["close"]
    for c in ("open", "high", "low"):
        d[c] = d[c] * ratio
    d["close"] = price
    return d.drop(columns=["adj_close"]), int(bad.sum())


# ---------------------------------------------------------------------------
# NSE TRADING CALENDAR -- applied at panel construction so it cannot be bypassed
# ---------------------------------------------------------------------------
TRADING_CALENDAR = Path(__file__).resolve().parent / "data" / "nse_trading_calendar.csv"


def _load_calendar():
    """data/nse_trading_calendar.csv -- TRACKED SOURCE DATA, not a derived file."""
    if not TRADING_CALENDAR.exists():
        raise FileNotFoundError(
            f"{TRADING_CALENDAR} missing.\n"
            "\n"
            "  WHAT TO DO: restore it from git. It is TRACKED, frozen source data --\n"
            "    git checkout -- data/nse_trading_calendar.csv\n"
            "\n"
            "  DO NOT TRY TO REBUILD IT. There is nothing left to rebuild it from.\n"
            "  It was computed once, from a retired universe's raw files, by\n"
            "  results/make_trading_calendar.py. Both were deleted on 2026-09-11 in\n"
            "  commit 2fe48ff, so that script is not in the tree and restoring it\n"
            "  would not help: the raw files it read are gone too.\n"
            "\n"
            "  IF YOU NEED SESSIONS PAST 2026-06-08, that is a different problem and\n"
            "  this message is not the answer to it. Extending the file is an\n"
            "  APPEND-ONLY operation and NO TOOL IN THIS REPOSITORY PERFORMS IT --\n"
            "  the source for new sessions has not been decided. Do not hand-edit\n"
            "  the file: a wrong tail silently changes every backtest window.\n"
            "\n"
            "  The panel cannot be built without the calendar, because a panel that\n"
            "  silently keeps market-holiday rows is what this filter exists to\n"
            "  prevent. See the calendar file's own header.")
    d = read_table(TRADING_CALENDAR, comment="#", parse_dates=["date"])
    return set(d["date"])


def _check_calendar(cal, panel, tag=""):
    """Fail loudly if the calendar cannot be trusted for THIS panel.

    Two guards, both aimed at the one real weakness of a calendar derived from one
    retired universe's files: that it could be narrowed, truncated or re-sourced.

      RANGE   -- the calendar must span the panel's own range. Catches truncation.
      DENSITY -- every date the filter removes must be THIN, i.e. carry fewer
                 symbols than a normal day OF ITS OWN YEAR. A phantom holiday
                 shows ~32 of 148 midcap150 symbols against that year's ~96, so it
                 passes; a genuine session wrongly dropped would be AT FULL
                 DENSITY FOR ITS OWN ERA and fires the assertion.

    "FULL DENSITY" WAS UNQUALIFIED UNTIL 2026-09-19, AND THE OMISSION WAS THE
    WHOLE DEFECT. Full against what was never stated. The code compared against
    the median of the panel's ENTIRE history, 2000-2026, which is a good proxy
    for "a normal day" only while a panel's density is roughly flat across that
    span. smallcap250's is not: 125 symbols is its 26-year median and 237 is its
    2025 median, because most of its 248 names did not exist for most of those
    years. Twenty-three phantom holidays carrying 125-142 symbols cleared the
    26-year median and aborted the run, while sitting at 0.53-0.60 of their own
    era. The threshold is per-year now, and the sentence above says which.

    THIS IS A LOOSENING. Measured over seven universes on 2026-09-19, the
    per-year rule flags a SUBSET of what the global rule flagged -- it passes
    exactly those 23 dates and changes nothing else anywhere. It is not tighter
    and is not a correction of an unsound test; it is a deliberately weaker test
    with measured margin behind it. See KNOWN_ISSUES.md for the margin.

    The literal check "calendar covers fewer days than the panel" is deliberately
    NOT used: the midcap150 panel legitimately holds 6,810 dates against the calendar's
    6,574, because 236 of them are the phantom dates being removed. That check
    would fail by construction on exactly the case the filter is built for. The
    density guard is the same intent expressed so it fires only when wrong.
    """
    cmin, cmax = min(cal), max(cal)
    pmin, pmax = panel["date"].min(), panel["date"].max()
    if cmin > pmin or cmax < pmax:
        raise AssertionError(
            f"trading calendar does not span the {tag} panel: calendar "
            f"{cmin.date()}..{cmax.date()} vs panel {pmin.date()}..{pmax.date()}")
    per_date = panel.groupby("date")["symbol"].nunique()
    # PER-YEAR, NOT GLOBAL. A year with no dates cannot be indexed, so the
    # global median remains the fallback for a date whose year is somehow
    # absent -- which cannot happen for a date drawn from this panel, and is
    # written anyway rather than left to raise a KeyError inside a guard.
    era = per_date.groupby(per_date.index.year).median()
    gmed = per_date.median()
    removed = sorted(set(panel["date"].unique()) - cal)
    dense = [d for d in removed
             if per_date.get(d, 0) >= era.get(d.year, gmed)]
    if dense:
        worst = max(dense, key=lambda d: per_date.get(d, 0) / era.get(d.year, gmed))
        raise AssertionError(
            f"trading calendar would remove {len(dense)} date(s) from the {tag} "
            f"panel that are AT FULL DENSITY FOR THEIR OWN YEAR, e.g. "
            f"{[str(d.date()) for d in dense[:5]]}. Worst is {worst.date()} at "
            f"{per_date.get(worst, 0):.0f} symbols against a {worst.year} median "
            f"of {era.get(worst.year, gmed):.0f}. The calendar is wrong or this "
            f"panel's source data has changed. Refusing to filter.")
    return removed


# THE OTHER DIRECTION, REPORTED AND NEVER ACTED ON. _check_calendar asks whether
# the calendar removes a session the data has. This asks whether the data lacks a
# session the calendar has. The 2026-10-10 delivery has no row for 2020-01-07 in
# any file, so the panel skips that session and every later rebalance lands one
# session later (KNOWN_ISSUES.md). Nothing here changes a panel or a result.
THIN_SESSION_SHARE = 0.5


def thin_sessions(data_dir, lo=None, hi=None, share=THIN_SESSION_SHARE):
    """Calendar sessions in [lo, hi] where fewer than `share` of the names whose
    history spans the session have a row on it.

    A name spans a session when its first row is on or before it and its last row
    on or after it. Returns [(date, rows, spanning)], oldest first. Reads only the
    date column of each CSV in `data_dir`.
    """
    lo = settings.BT_START_DATE if lo is None else pd.Timestamp(lo)
    hi = settings.BT_END_DATE if hi is None else pd.Timestamp(hi)
    cal = pd.DatetimeIndex(sorted(d for d in _load_calendar() if lo <= d <= hi))
    if not len(cal):
        return []
    rows = np.zeros(len(cal), dtype=int)
    span = np.zeros(len(cal), dtype=int)
    for f in list_dir(data_dir, "*.csv"):
        d = smart_parse_dates(read_table(f, usecols=["date"])["date"],
                                     source=str(f)).dropna()
        if d.empty:
            continue
        a = cal.searchsorted(d.min(), side="left")
        b = cal.searchsorted(d.max(), side="right")
        span[a:b] += 1
        rows += cal.isin(d)
    return [(cal[i], int(rows[i]), int(span[i])) for i in range(len(cal))
            if span[i] and rows[i] < share * span[i]]


def build_panel(horizon, data_dir, pin_scorable=None):
    """Build the full feature panel from one universe's raw stock CSVs.

    `data_dir` IS REQUIRED, AND THAT IS THE POINT. It used to default to None and
    fall back to a retired universe's folder, so any caller that forgot to pass a
    universe silently built a DIFFERENT universe's panel and reported it under the
    caller's name. Nothing failed; the numbers were simply another universe's.
    That folder no longer exists, so the fallback would now be a confusing
    FileNotFoundError deep in a glob; this raises at the call instead, naming what
    is missing.

    (This previously lived in engine_v2.py and was nearly lost when that file was
    deleted. It is permanent here now.)

    NO SESSION'S PRICE DEPENDS ON A LATER SESSION. Until 2026-10-22 each file was
    passed through results/ratio_clean.py first, which decided whether to repair
    session t by looking up to five sessions ahead. That repair is gone: adj_close
    is used as delivered, with the close fallback of canonical_price only.

    THE LABEL CARRIES THE DATE IT ENDS ON. `fwd_ret` is the close `horizon` of the
    symbol's own rows ahead, and `label_end` is that row's date. A symbol with
    missing sessions has a label that ends later than `horizon` sessions after its
    row; score_monthly uses a row for training only once `label_end` has passed
    the purge limit (training_set). No training rank is computed here.

    IN A PIT RUN THE CROSS-SECTIONS ARE THE MEMBERS ON THE DATE. The equal-weight
    market behind beta_60 and idio_vol_60 and the z-score peer group take only the
    rows survivorship.member_mask keeps: members on the date, and every row before
    the first effective date (where no membership is defined). In static mode the
    mask keeps every row.
    """
    if data_dir is None:
        raise ValueError(
            "build_panel(horizon, data_dir): data_dir is required and must name "
            "the universe's raw directory -- pass REGISTRY[tag].prepare_data_dir() "
            "or u.data_dir. It used to default to a retired universe's folder, "
            "which meant a caller that omitted it silently built and reported "
            "the wrong universe. See settings.py.")
    frames = []
    _src = data_dir
    _cal = _load_calendar()
    _raw = []
    for f in list_dir(_src, "*.csv"):
        d0 = read_price_csv(f)[["date", "close"]].dropna()
        _raw.append(pd.DataFrame({"date": d0["date"], "symbol": f.stem}))
    _pre = pd.concat(_raw, ignore_index=True)
    # Guard BEFORE filtering: the check needs the unfiltered panel to see whether
    # any date the calendar would remove is at full symbol density.
    _removed = _check_calendar(_cal, _pre, tag=str(Path(_src).name))
    _dropped = 0
    _fallback = {}
    for f in list_dir(_src, "*.csv"):
        raw = read_price_csv(f).sort_values("date")
        # THE LOAD BOUNDARY. adj_close is selected here and resolved into `close`
        # by canonical_price immediately, so the panel below -- and therefore every
        # px/op pivot every consumer builds from it -- is on the adjusted basis.
        # This is the ONLY place the choice is made. The unadjusted close is kept
        # as raw_close for amihud_20 alone: adj_close is back-adjusted for
        # dividends paid after the row's date, so a rupee volume built from it
        # would depend on later sessions.
        raw = raw[PRICE_COLS].dropna()
        raw["raw_close"] = raw["close"]
        raw, _nfb = canonical_price(raw)
        if _nfb:
            _fallback[f.stem] = _nfb
        # Market-holiday rows are removed BEFORE any feature is computed, so a
        # phantom session cannot enter a rolling window, the market return,
        # the union date index, or an execution price.
        _n = len(raw)
        raw = raw[raw["date"].isin(_cal)]
        _dropped += _n - len(raw)
        if len(raw) < 3:
            continue
        d = add_stock_features(raw)
        d["symbol"] = f.stem
        d["fwd_ret"] = d["close"].shift(-horizon) / d["close"] - 1
        d["label_end"] = d["date"].shift(-horizon)
        # THE LABEL MUST ALSO BE PROTECTED, not just the features. fwd_ret spans
        # [t+1, t+horizon]; if a flagged artefact sits anywhere in that span the
        # label is a data error rather than a return, so it is dropped. Masking
        # only ret_1d would leave rows whose own features are clean but whose
        # TARGET is contaminated, and the model would fit that.
        b = d["bad_ret"].astype(float).shift(-1)
        fwd_bad = b[::-1].rolling(horizon, min_periods=1).max()[::-1]
        d.loc[fwd_bad.fillna(0) > 0, "fwd_ret"] = np.nan
        frames.append(d.drop(columns=["raw_close"]))
    p = pd.concat(frames, ignore_index=True)
    print(f"    trading calendar: {len(_removed)} non-trading date(s) removed, "
          f"{_dropped:,} rows across {len(frames)} symbols")
    # PRINTED EVERY RUN, INCLUDING WHEN IT IS ZERO. A silent zero and a silently
    # grown count look identical in a log that only speaks up on trouble, and the
    # whole point of the count is to notice a data refresh that made adj_close
    # worse. Per symbol, because a new offender matters more than a bigger total.
    _tfb = sum(_fallback.values())
    print(f"    canonical price: adj_close on {len(p) - _tfb:,} rows, "
          f"close fallback on {_tfb:,} "
          f"({', '.join(f'{k} {v}' for k, v in sorted(_fallback.items())) or 'none'})")
    # Point-in-time membership, per row. All True in static mode.
    p["member"] = member_mask(p, MEMBERSHIP)
    p = add_market_relative_features(p, member_col="member")

    # PRICES ARE NO LONGER FILTERED BY FEATURE AVAILABILITY.
    #     This used to be `p = p.dropna(subset=FEATS_V2)`, and every consumer then
    #     built its price panel from the survivors:
    #         px = p.pivot_table(index=date, columns=symbol, values=close).ffill()
    #     So a day on which beta_60 happened to be NaN lost its PRICE as well, and
    #     ffill bridged the hole -- compressing every skipped day of real price
    #     movement into a single manufactured return when the symbol reappeared.
    #
    #     That is where the recurring `span=61, skipped=60` signature came from:
    #     exactly the 60 rows beta_60 and idio_vol_60 need to respawn after any
    #     interruption. It is also why the cached panel held 6,322 dates where the
    #     raw CSV panel holds 6,574.
    #
    #     Measured consequences before this change: PATANJALI showed +24,772.7% in
    #     one panel day against a raw return of -5.0% with 126 of its own trading
    #     days skipped; LICI's genuine -50.6% was relocated three months and
    #     amplified to -54.1%; CGPOWER showed +179.0% with no artefact filter
    #     involved at all. On MidCap150, eight manufactured returns sat next to a
    #     held or top-8 position.
    #
    # THE TWO PANELS ARE NOW SEPARATE, which is what they always should have been:
    #     price   -- every row with a valid open/close, so px and op are real and
    #                ffill only ever bridges a symbol's genuine non-trading days.
    #     score   -- only rows whose 17 features are all present, flagged by
    #                `scorable`. A symbol with missing features simply has no score
    #                that day and cannot be ranked, which is correct, while its
    #                price stays real for valuation, execution, momentum and
    #                buy&hold.
    scorable = p[FEATS_V2].notna().all(axis=1)

    # MEASUREMENT HOOK, INERT BY DEFAULT. `pin_scorable` is a set of
    # (date, symbol) pairs; when given, a row is scorable only if it is ALSO in
    # that set. It exists for the pinned-mask counterfactual in
    # results/pinned_mask_test.py, which asks whether the price-perturbation
    # displacement is carried by rows that perturbation ADMITS to the scorable
    # set.
    #
    # IT IS APPLIED HERE, BEFORE THE Z-SCORE, AND THAT IS THE WHOLE REASON IT IS
    # A PARAMETER RATHER THAN A POST-HOC EDIT. The cross-sectional normalisation
    # two lines below takes its peer group from `scorable`, so a mask pinned
    # AFTER build_panel would leave every incumbent name already z-scored against
    # the wider perturbed peer group -- it would test the selection channel while
    # silently leaving the larger one in.
    #
    # None is identity: no caller that omits it can behave differently.
    if pin_scorable is not None:
        _pin = pd.Series(
            list(zip(p["date"], p["symbol"])), index=p.index).isin(pin_scorable)
        scorable = scorable & _pin

    # TOUCH POINT 1 -- point-in-time membership, applied to the SCORE side only,
    # and BEFORE the z-score, so a name that is not a member on the date is
    # neither scored nor part of the peer group the members are scored against.
    # Rows are never dropped: `p` is also the price panel every consumer pivots,
    # and deleting prices for a non-price reason lets the downstream ffill bridge
    # the hole (+24,772.7% on PATANJALI). In static mode `member` is all True.
    scorable = scorable & p["member"]

    # The cross-sectional z-score is computed over the SCORABLE rows only.
    # Normalising over the full panel would silently widen the peer group, because
    # a row missing one feature would still contribute to the mean and standard
    # deviation of the other sixteen.
    z = cross_sectional_normalize(p.loc[scorable].copy(), FEATS_V2)
    p.loc[scorable, FEATS_V2] = z[FEATS_V2].to_numpy()
    p.loc[~scorable, FEATS_V2] = np.nan

    # Recomputed AFTER normalising, so the flag states what is actually true of the
    # row. On a day with a single scorable stock the group standard deviation is
    # NaN and the z-score comes back NaN, which would otherwise leave a row marked
    # scorable while carrying NaN features. 498 rows, all between 2001 and 2003,
    # none inside any backtest window -- but the flag has to mean what it says.
    scorable = p[FEATS_V2].notna().all(axis=1)

    p["scorable"] = scorable
    p["year"] = p["date"].dt.year
    return p


# THE COLUMNS score_monthly NEEDS FROM A build_panel PANEL, and the columns the
# raw panel cache keeps. One list, read by every caller that trims a panel before
# scoring it.
SCORE_INPUT_COLS = (["date", "symbol", "open", "close", "year", "fwd_ret", "label_end",
                     "scorable"] + FEATS_V2)


VOL_WIN = 60


def precompute(px, vol_win=VOL_WIN):
    return {"vol": rolling_std(px.pct_change(), vol_win) * np.sqrt(252)}


# ======================================================================================
# POINT-IN-TIME MEMBERSHIP. From survivorship.py and engine_core.py (moved 2026-11-27).
# ======================================================================================
# survivorship.py -- point-in-time index membership, behind a switch.
#
# WHY THIS EXISTS
#     Every universe in this project is built from a list of TODAY'S index members,
#     backfilled to the start of the backtest. That is survivorship bias: a name only
#     appears in the list because it survived and performed well enough to still be in
#     the index now. Companies that were in the index and were later dropped or
#     delisted are absent entirely, so the strategy is choosing from a set it could not
#     have known in advance.
#
#     This module removes that bias when a valid membership file is available, and
#     leaves the existing behaviour untouched when it is not. Nothing else changes.
#
# THE SWITCH
#     SURVIVORSHIP_MODE = "static"  -- today's members, backfilled. The existing
#                                      behaviour. This is the default.
#     SURVIVORSHIP_MODE = "pit"     -- point-in-time. At every rebalance the eligible
#                                      set is the membership in force on that date.
#
#     Set it in config, or per-run:
#
#         import survivorship as sv
#         sv.set_mode("pit")
#
# WHY THERE IS A VALIDATION GATE, AND WHY IT REFUSES RATHER THAN WARNS
#     The first membership file supplied to this project was broken in a way that
#     looked fine at a glance: 76 dated rows, 100 symbols each, inclusions and
#     exclusions columns, and price data for 203 names including many that had been
#     dropped. It parsed cleanly.
#
#     It also contained no RELIANCE. Nor INFY, ITC, SBIN, ICICIBANK, HDFCBANK,
#     KOTAKBANK or SUNPHARMA -- eight of the largest companies in the Indian market,
#     absent from all 76 lists, in an index they have been in continuously. And
#     list[t] = list[t-1] + inclusions - exclusions failed on 20 of 75 transitions,
#     so the columns disagreed with each other.
#
#     A backtest run on that file would have produced a survivorship-free-looking
#     number from a strategy that could never buy Reliance, compared against an index
#     largely made of Reliance. It would have looked like the answer and been the least
#     trustworthy figure in the project.
#
#     So load() raises. It does not warn and continue. A caveat gets dropped when
#     a number is copied into a slide; a raised exception does not.
#
#     PIT RUNS ARE THE ONE EXCEPTION, BY THE OWNER'S DECISION OF 2026-10-10. Every
#     supplier membership file in data/raw/Survivorship_Bias fails validate(), and
#     the owner ruled them final as delivered. run.py --survivorship pit loads them
#     with allow_invalid=True and writes the verdict, the residual-survivorship
#     warning and LOOKAHEAD_NOTE into every pit run's log, RUN.txt and params JSON
#     (pit_record). A pit figure must be quoted with that verdict.
#
# HOW A NAME LEAVING THE INDEX IS HANDLED
#     Forced exit on the exclusion date, not a buffer exit at the next rebalance.
#     The shipping engine (results/test_exposure.py, beside touch point 4) sells a
#     held name at the open of the first session on or after the effective date of
#     the first row that does not list it. Index changes are announced weeks ahead,
#     so that order could be placed in time.
#
#     The point of a point-in-time universe is that the portfolio never holds what it
#     could not have held. Letting the buffer carry a name past its exclusion date
#     reintroduces exactly the bias this module exists to remove. The cost is extra
#     turnover on the reconstitution dates, which is the correct price to pay -- and a
#     real index-tracking mandate pays it too.
#
#     EXIT_POLICY = "forced"  -- sell on the first session on or after exclusion (default)
#     EXIT_POLICY = "buffer"  -- let the normal buffer rule handle it
#
#     "buffer" exists so the two can be measured against each other. It is not the
#     honest default.
#
# EXPECTED FILE FORMAT
#     A CSV with one row per reconstitution date:
#
#         effective_date,symbols,inclusions,exclusions
#         2019-03-29,"RELIANCE,TCS,INFY,...","ABC,DEF","XYZ"
#
#     effective_date : the date the change takes effect
#     symbols        : comma-separated full membership list in force from that date
#     inclusions     : comma-separated names added on that date (optional)
#     exclusions     : comma-separated names removed on that date (optional)
#
#     Only effective_date and symbols are required. If inclusions/exclusions are
#     present they are cross-checked against symbols, and a disagreement is an error,
#     because it means the file has no single coherent membership series.
#
#     MEMBERSHIP IS BUILT FROM THE symbols COLUMN ONLY: the row's list is the
#     membership from its effective_date until the next row. inclusions and
#     exclusions are read by validate() and nowhere else (owner's decision,
#     2026-10-10).
#
# USAGE
#
#     import survivorship as sv
#
#     # 1. Check a file before trusting it. Run this first, always.
#     print(sv.validation_report("data/raw/index_membership_nifty100.csv",
#                                price_dir="data/raw/Final_Without_Survivorship_Data/Final_NIFTY100_EoD_Data"))
#
#     # 2. Load it. Raises if it does not validate.
#     m = sv.load("data/raw/index_membership_nifty100.csv")
#
#     # 3. Ask what was eligible on a date.
#     m.members_on("2021-06-15")            # -> set of symbols
#
#     # 4. Filter a panel to point-in-time membership.
#     panel = sv.apply_to_panel(panel, m)   # no-op when mode is "static"
#
#     # 5. Names to force out at a rebalance, given what is held.
#     m.forced_exits(held_symbols, decision_date)
#
# COMMAND LINE: removed 2026-11-27 with results/survivorship.py. validate(),
# Membership.members_on() and residual_survivorship() are the same calls from Python,
# and results/test_survivorship.py exercises them.

# ---------------------------------------------------------------------------
# switches
# ---------------------------------------------------------------------------

SURVIVORSHIP_MODE = "static"     # "static" | "pit"


EXIT_POLICY = "forced"           # "forced" | "buffer"


# THE 15 RENAMES READ AGAINST THEIR NSE CIRCULARS (diagnostics/membership/STATUS.md),
# old symbol -> the symbol the price files use. The other 176 rows of
# data/reference/nse_symbol_renames.csv are unchecked and are not used. Applied by
# load() to the membership lists it returns, never to the file and never inside
# validate(), so the validator's checks see the file exactly as delivered.
RENAMES = {
    "RNAM": "NAM-INDIA", "TATAGLOBAL": "TATACONSUM", "NIITTECH": "COFORGE",
    "INFRATEL": "INDUSTOWER", "ADANIGAS": "ATGL", "CADILAHC": "ZYDUSLIFE",
    "MOTHERSUMI": "MOTHERSON", "RUCHI": "PATANJALI", "MINDAIND": "UNOMINDA",
    "SRTRANSFIN": "SHRIRAMFIN", "IIFLWAM": "360ONE", "ADANITRANS": "ADANIENSOL",
    "L&TFH": "LTF", "GMRINFRA": "GMRAIRPORT", "TATAMOTORS": "TMPV",
}


# WRITTEN INTO EVERY PIT RUN'S RECORD. Measured by survivorship_attribution.py on
# the supplier's files: the 2018 and 2019 rows of the Nifty 50 file list JIOFIN,
# listed in 2023, and TRENT, BEL, INDIGO and MAXHEALTH, which joined in 2024 and
# 2025. Read as membership, such a row makes a later member eligible early.
LOOKAHEAD_NOTE = (
    "The symbols column reads like today's member list edited backwards (the 2018 "
    "and 2019 rows of the Nifty 50 file list JIOFIN, listed in 2023, and TRENT, BEL, "
    "INDIGO and MAXHEALTH, which joined in 2024 and 2025). It is used as membership "
    "by the owner's decision, so some look-ahead remains in pit results.")


def set_mode(mode: str) -> None:
    """Set the survivorship mode for this process."""
    global SURVIVORSHIP_MODE
    if mode not in ("static", "pit"):
        raise ValueError(f"mode must be 'static' or 'pit', got {mode!r}")
    SURVIVORSHIP_MODE = mode


def set_exit_policy(policy: str) -> None:
    """Set how a name leaving the index is handled."""
    global EXIT_POLICY
    if policy not in ("forced", "buffer"):
        raise ValueError(f"policy must be 'forced' or 'buffer', got {policy!r}")
    EXIT_POLICY = policy


def is_pit() -> bool:
    return SURVIVORSHIP_MODE == "pit"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class MembershipError(Exception):
    """Raised when a membership file cannot be trusted. Never downgraded to a warning."""


# Names that must appear somewhere in a genuine history of these indices. If a file
# claims to be Nifty 100 membership and contains no Reliance, the file is wrong --
# there is no reading of the data under which that is a coverage gap.
SANITY_ANCHORS = {
    "nifty100": ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "ITC", "SBIN"],
    "nifty50": ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "ITC", "SBIN"],
    "midcap150": [],   # no single name is guaranteed present across a midcap history
}


# A constituent symbol is an equity ticker. These patterns are debt or derivative
# identifiers that appeared in the first broken file (e.g. "722HPCL29" = 7.22% HPCL
# 2029, a debenture) and cannot be index constituents.
def _looks_non_equity(sym: str) -> bool:
    """Flag debt identifiers without flagging equities that start with a digit.

    A first version rejected anything beginning with a digit, which is wrong:
    3MINDIA (3M India) and 8KMILES (8K Miles Software) are ordinary NSE equities.
    A bond identifier is a coupon followed by an issuer and a maturity year --
    722HPCL29 is 7.22% HPCL 2029 -- so it carries THREE OR MORE leading digits and
    ends in a two-digit year. That pattern is what is rejected, not the leading
    digit alone."""
    if not sym:
        return True
    if len(sym) > 20:
        return True
    lead = len(sym) - len(sym.lstrip("0123456789"))
    if lead >= 3 and sym[-2:].isdigit():
        return True               # 722HPCL29, 1025GOI30, 828GS2027
    # Issuer code followed by a FOUR-digit year, with no coupon prefix: GS2027.
    # Four trailing digits forming a plausible year is a debt signature, and no NSE
    # equity ticker ends that way. Kept deliberately narrow -- see the note below on
    # what is NOT claimed.
    if re.fullmatch(r"[A-Z&\-]{2,8}(19|20)\d{2}", sym):
        return True
    # NOT DETECTED, AND DELIBERATELY SO: an issuer code plus a TWO-digit year with no
    # coupon prefix (NHAI31, IRFC24, IIFL27 in shape). Rejecting every symbol that
    # ends in two digits would be the only way to catch those, and that cannot be
    # done safely -- it is indistinguishable from an equity ticker by pattern alone,
    # and a false positive here rejects a whole valid membership file. Verified
    # against 938 real tickers drawn from this repo's price files and the membership
    # file itself: zero equities are rejected by the rules above.
    return False


@dataclass
class ValidationResult:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def __str__(self) -> str:
        lines = ["=" * 74,
                 "MEMBERSHIP FILE VALIDATION",
                 "=" * 74]
        for k, v in self.stats.items():
            lines.append(f"  {k:<44}{v}")
        if self.errors:
            lines.append("")
            lines.append("  ERRORS -- the file cannot be used:")
            for e in self.errors:
                lines.append(f"    - {e}")
        if self.warnings:
            lines.append("")
            lines.append("  WARNINGS -- usable, but the result carries these caveats:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        lines.append("")
        lines.append("  VERDICT: " + ("PASS" if self.ok else "FAIL"))
        lines.append("=" * 74)
        return "\n".join(lines)


def _read_raw(path) -> pd.DataFrame:
    df = read_table(path)
    cols = {c.lower().strip(): c for c in df.columns}
    if "effective_date" not in cols or "symbols" not in cols:
        raise MembershipError(
            f"{path}: required columns 'effective_date' and 'symbols' not found. "
            f"Columns present: {list(df.columns)}")
    df = df.rename(columns={cols["effective_date"]: "effective_date",
                            cols["symbols"]: "symbols"})
    for opt in ("inclusions", "exclusions"):
        if opt in cols:
            df = df.rename(columns={cols[opt]: opt})
        else:
            df[opt] = ""
    # Try ISO first, then day-first. Doing it in this order avoids pandas warning
    # on ISO input, and avoids silently reading 03/02/2019 as 2 March.
    raw = df["effective_date"].astype(str)
    parsed = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        alt = pd.to_datetime(raw, dayfirst=True, errors="coerce")
        parsed = parsed.fillna(alt)
    df["effective_date"] = parsed
    if df["effective_date"].isna().any():
        n = int(df["effective_date"].isna().sum())
        raise MembershipError(f"{path}: {n} rows have an unparseable effective_date")
    return df.sort_values("effective_date").reset_index(drop=True)


def _split(cell) -> set:
    if pd.isna(cell):
        return set()
    return {s.strip().upper() for s in str(cell).split(",") if s.strip()
            and s.strip().lower() != "nan"}


def validate(path, index_name: str = "nifty100", price_dir=None,
             expected_size: int | None = None) -> ValidationResult:
    """Check a membership file without loading it into the engine.

    Returns a ValidationResult. Does not raise -- use load() for that, or check
    result.ok yourself. price_dir is optional; when given, price coverage is
    measured and reported as a warning rather than an error, because a coverage
    gap is a limitation to disclose, not a reason the file is wrong.
    """
    res = ValidationResult(ok=True)
    df = _read_raw(path)
    lists = [_split(s) for s in df["symbols"]]
    all_syms = set().union(*lists) if lists else set()

    res.stats["rows (reconstitution dates)"] = len(df)
    res.stats["date range"] = (f"{df.effective_date.min().date()} -> "
                               f"{df.effective_date.max().date()}")
    res.stats["distinct symbols ever a member"] = len(all_syms)
    sizes = [len(L) for L in lists]
    res.stats["members per date (min/median/max)"] = (
        f"{min(sizes)} / {int(np.median(sizes))} / {max(sizes)}")

    # --- 1. dates strictly increasing, no duplicates -----------------------
    if df["effective_date"].duplicated().any():
        res.errors.append("duplicate effective_date rows")
    if not df["effective_date"].is_monotonic_increasing:
        res.errors.append("effective_date is not sorted ascending after sorting")

    # --- 2. anchors: names that must be present ----------------------------
    anchors = SANITY_ANCHORS.get(index_name.lower(), [])
    missing = [a for a in anchors if a not in all_syms]
    if missing:
        res.errors.append(
            f"{len(missing)} anchor names appear in ZERO of the {len(df)} lists: "
            f"{', '.join(missing)}. These are among the largest constituents of "
            f"{index_name} and cannot be absent from a genuine history. This is the "
            f"exact failure mode of the first file supplied to this project.")
    present = {a: sum(a in L for L in lists) for a in anchors if a in all_syms}
    if present:
        res.stats["anchor presence (of %d dates)" % len(df)] = ", ".join(
            f"{k} {v}" for k, v in present.items())

    # --- 3. non-equity identifiers -----------------------------------------
    junk = sorted(s for s in all_syms if _looks_non_equity(s))
    if junk:
        res.errors.append(
            f"{len(junk)} symbols are not equity tickers: {', '.join(junk[:8])}"
            f"{' ...' if len(junk) > 8 else ''}. An equity index cannot contain "
            f"bonds or debentures.")

    # --- 4. self-consistency of inclusions/exclusions ----------------------
    have_incexc = (df["inclusions"].astype(str).str.strip().ne("").any() or
                   df["exclusions"].astype(str).str.strip().ne("").any())
    if have_incexc:
        bad = []
        for i in range(1, len(df)):
            inc = _split(df.iloc[i]["inclusions"])
            exc = _split(df.iloc[i]["exclusions"])
            expected = (lists[i - 1] | inc) - exc
            if expected != lists[i]:
                bad.append(str(df.iloc[i]["effective_date"].date()))
        res.stats["transitions checked"] = len(df) - 1
        res.stats["transitions failing list[t]=list[t-1]+inc-exc"] = len(bad)
        if bad:
            res.errors.append(
                f"inclusions/exclusions disagree with the symbols column on "
                f"{len(bad)} of {len(df)-1} transitions (first: {bad[0]}). The file "
                f"has no single coherent membership series.")
    else:
        res.warnings.append(
            "no inclusions/exclusions columns -- membership is taken from the "
            "symbols column alone and cannot be cross-checked.")

    # --- 4b. cumulative-list detection -------------------------------------
    # A membership list is a snapshot, not a running total. If each row is a
    # superset of the one before, the generating script accumulated names instead
    # of removing exclusions -- the second real file supplied to this project did
    # exactly that, reaching 854 names for a 100-name index.
    # AN EARLIER VERSION OF THIS CHECK COUNTED NON-STRICT SUPERSETS AND FIRED ON
    # LEGITIMATE FILES. Two false positives were measured against it:
    #   (a) a stable history whose membership barely changes -- consecutive rows are
    #       IDENTICAL, and a set is a superset of itself, so 9 of 11 transitions
    #       counted as "cumulative". It reported a file that "grows from 100 to 100
    #       names" as a running total, which is self-evidently not what it is.
    #   (b) a genuine index expansion, Nifty 50 -> Nifty 100 partway through the
    #       history: every transition is a (non-strict) superset, so it fired at
    #       11 of 11. An index that genuinely widens is not a broken file.
    #
    # Three conditions now have to hold together, and they are what actually
    # distinguishes accumulation from both of those:
    #   - the list has to GROW substantially end to end (rules out (a));
    #   - growth has to be SUSTAINED across several separate reconstitutions, not
    #     one step (rules out (b), which grows exactly once);
    #   - names must almost never LEAVE. This is the real signature: a snapshot
    #     history removes roughly as many names as it adds over time, while an
    #     accumulating script removes almost none.
    grew = [i for i in range(1, len(lists)) if lists[i - 1] < lists[i]]
    added = sum(len(lists[i] - lists[i - 1]) for i in range(1, len(lists)))
    removed = sum(len(lists[i - 1] - lists[i]) for i in range(1, len(lists)))
    if (len(lists) > 3 and max(sizes) >= 1.5 * sizes[0]
            and len(grew) >= 3 and removed <= 0.25 * added):
        res.errors.append(
            f"the symbols column looks CUMULATIVE: it grows from {sizes[0]} to "
            f"{max(sizes)} names across {len(grew)} separate reconstitutions, adding "
            f"{added} names while only ever removing {removed}. A membership list is "
            f"a snapshot of who is in the index on that date, not a running total of "
            f"everyone who has ever been in it. The generating script is adding "
            f"inclusions without removing exclusions.")

    # Excluded names must actually leave the list they were excluded from.
    if have_incexc:
        still, checked = 0, 0
        both, total_exc = 0, 0
        for i in range(1, len(df)):
            inc_i = _split(df.iloc[i]["inclusions"])
            for e in _split(df.iloc[i]["exclusions"]):
                total_exc += 1
                # A name listed in BOTH inclusions and exclusions on the same date is
                # the one legitimate way an excluded name can still be in that row's
                # symbols -- removed and re-added in the same reconstitution. Counting
                # it as an unremoved exclusion would be a false positive, so it is
                # excluded from that count and checked separately below: rare is
                # plausible, routine is a defect in its own right.
                if e in inc_i:
                    both += 1
                    continue
                checked += 1
                if e in lists[i]:
                    still += 1
        if total_exc:
            res.stats["names in both inclusions and exclusions"] = \
                f"{both} of {total_exc}"
        # BOTH conditions, not either: an absolute floor so a one-off re-add in a
        # small file stays a warning, and a proportional floor so a handful of them
        # in a long history does not become an error on volume alone.
        if both >= 3 and both >= 0.05 * total_exc:
            res.errors.append(
                f"{both} of {total_exc} exclusion entries name a symbol that the SAME "
                f"row also lists as an inclusion. A reconstitution adds a name or "
                f"drops it, not both on one date, so at this frequency the two "
                f"columns are not describing a single index event -- most likely the "
                f"generating script is merging rows from more than one source list.")
        elif both:
            res.warnings.append(
                f"{both} of {total_exc} exclusion entries are also listed as an "
                f"inclusion on the same date (removed and re-added in one "
                f"reconstitution). Rare but not impossible; worth confirming.")
        if checked:
            res.stats["exclusions still present in same row"] = f"{still} of {checked}"
        if still:
            res.errors.append(
                f"{still} of {checked} names listed in `exclusions` are STILL in the "
                f"symbols column of the same row. An excluded name must be absent "
                f"from the membership that takes effect on its exclusion date.")

    # --- 5. size plausibility ----------------------------------------------
    if expected_size:
        off = [i for i, n in enumerate(sizes) if abs(n - expected_size) > 2]
        if off:
            res.warnings.append(
                f"{len(off)} dates have a member count more than 2 away from the "
                f"expected {expected_size}.")

    # --- 6. churn plausibility ---------------------------------------------
    years = max((df.effective_date.max() - df.effective_date.min()).days / 365.25, 1)
    turnover = (len(all_syms) - int(np.median(sizes))) / years
    res.stats["names added per year (implied)"] = f"{turnover:.1f}"
    if turnover < 2.0 and years > 5:
        res.warnings.append(
            f"implied turnover of {turnover:.1f} names/year is low for an index of "
            f"this size over {years:.0f} years; verify the history is complete.")

    # --- 7. price coverage (a disclosure, not an error) --------------------
    if price_dir is not None:
        files = {p.stem.upper() for p in list_dir(price_dir, "*.csv")}
        have = all_syms & files
        missing_px = all_syms - files
        res.stats["symbols with a price file"] = f"{len(have)} of {len(all_syms)}"
        if missing_px:
            last = lists[-1] if lists else set()
            ever_out = all_syms - last
            miss_out = len(missing_px & ever_out)
            miss_in = len(missing_px & last)
            res.warnings.append(
                f"{len(missing_px)} of {len(all_syms)} members have no price file. "
                f"Of those, {miss_out} were dropped from the index at some point and "
                f"{miss_in} are current members. The gap is biased toward dropped "
                f"names, so RESIDUAL SURVIVORSHIP REMAINS even in pit mode. Report "
                f"this alongside any result.")

    res.ok = not res.errors
    return res


def validation_report(path, index_name="nifty100", price_dir=None,
                      expected_size=None) -> str:
    """Human-readable validation output. Run this before trusting a file."""
    return str(validate(path, index_name, price_dir, expected_size))


# ---------------------------------------------------------------------------
# the membership object
# ---------------------------------------------------------------------------

@dataclass
class Membership:
    """Point-in-time index membership, validated at construction."""
    dates: list                  # sorted effective dates (pd.Timestamp)
    lists: list                  # parallel list of symbol sets
    exclusions: dict             # effective_date -> set removed on that date
    source: str
    validation: ValidationResult

    def __post_init__(self):
        # np.searchsorted against a LIST of Timestamps works on some pandas/numpy
        # combinations and raises TypeError on others ("'<' not supported between
        # instances of 'Timestamp' and 'int'"). A real datetime64 array behaves
        # identically everywhere, so the comparison basis is fixed once here rather
        # than depending on the environment.
        object.__setattr__(self, "_dates64",
                           np.array(self.dates, dtype="datetime64[ns]"))

    def _pos(self, when):
        """Index of the membership list in force at each date in `when`.
        -1 where the date precedes the first effective date."""
        vals = pd.DatetimeIndex(pd.to_datetime(when)).values
        return np.searchsorted(self._dates64, vals, side="right") - 1

    def members_on(self, date) -> set:
        """The membership in force on `date` -- the most recent effective_date at
        or before it. Empty before the first effective date, which is correct: the
        universe is not defined before the history starts."""
        i = int(self._pos([pd.Timestamp(date)])[0])
        if i < 0:
            return set()
        return self.lists[i]

    def is_member(self, symbol, date) -> bool:
        return symbol.upper() in self.members_on(date)

    def forced_exits(self, held, date) -> set:
        """Of the names currently held, those no longer in the index on `date`.

        Under EXIT_POLICY="forced" these are sold regardless of their rank or
        buffer status. Under "buffer" this returns an empty set and the normal
        buffer rule applies."""
        if EXIT_POLICY != "forced":
            return set()
        m = self.members_on(date)
        if not m:
            return set()
        return {s for s in held if s.upper() not in m}

    def eligible_mask(self, panel_dates, symbols) -> pd.DataFrame:
        """Boolean DataFrame [date x symbol], True where the symbol was a member.

        Use this to mask scores before ranking, so a name is only ever selectable
        on dates it was actually in the index."""
        idx = pd.DatetimeIndex(pd.to_datetime(panel_dates))
        cols = [s.upper() for s in symbols]
        out = pd.DataFrame(False, index=idx, columns=cols)
        pos = self._pos(idx)
        for i, p in enumerate(pos):
            if p < 0:
                continue
            members = self.lists[p] & set(cols)
            if members:
                out.iloc[i, out.columns.get_indexer(list(members))] = True
        return out

    def coverage_table(self, price_dir) -> pd.DataFrame:
        """Per reconstitution date: members in force, members with price data,
        and the coverage percentage. Report this with any pit-mode result."""
        files = {p.stem.upper() for p in list_dir(price_dir, "*.csv")}
        rows = []
        for d, L in zip(self.dates, self.lists):
            have = len(L & files)
            rows.append({"effective_date": d, "members": len(L),
                         "with_price": have,
                         "coverage_pct": round(have / len(L) * 100, 1) if L else np.nan})
        return pd.DataFrame(rows)


def load(path, index_name="nifty100", price_dir=None,
         expected_size=None, allow_invalid=False) -> Membership:
    """Load and validate a membership file.

    Raises MembershipError if validation fails. allow_invalid=True bypasses that.
    PIT RUNS USE IT: every supplier membership file fails validation, and the owner
    decided on 2026-10-10 that pit runs go ahead on those files as delivered. A
    figure computed under allow_invalid must be quoted with the validator's verdict,
    which pit_record() puts into every pit run's log, RUN.txt and params JSON.

    The returned lists carry RENAMES applied, so they name the symbols the price
    files use. The validation result describes the file as delivered.
    """
    res = validate(path, index_name, price_dir, expected_size)
    if not res.ok and not allow_invalid:
        raise MembershipError(
            f"{path} failed validation and will not be loaded.\n\n{res}\n\n"
            f"Fix the file rather than bypassing this. A number produced from an "
            f"invalid membership history looks more authoritative than the biased "
            f"one it replaces, which makes it worse.")
    df = _read_raw(path)
    lists = [{RENAMES.get(x, x) for x in _split(s)} for s in df["symbols"]]
    excl = {d: {RENAMES.get(x, x) for x in _split(e)}
            for d, e in zip(df["effective_date"], df["exclusions"])}
    return Membership(dates=list(df["effective_date"]), lists=lists,
                      exclusions=excl, source=str(path), validation=res)


# ---------------------------------------------------------------------------
# panel integration
# ---------------------------------------------------------------------------

def apply_to_panel(panel: pd.DataFrame, membership: Membership | None,
                   date_col="date", symbol_col="symbol") -> pd.DataFrame:
    """Restrict a long-format panel to point-in-time membership.

    In "static" mode this returns the panel unchanged, so the call can sit
    permanently in the pipeline. In "pit" mode it drops every (date, symbol) row
    where the symbol was not in the index on that date.

    ROWS BEFORE THE FIRST EFFECTIVE DATE ARE KEPT FOR THE FIRST LIST'S SYMBOLS.
    No list is in force there, and the model needs history to train on before the
    first pit rebalance; keeping every symbol would choose rows by later
    membership (member_mask). They are never traded: a pit universe's backtest
    window starts at the first session on or after the first effective date
    (settings.pit_variant).

    PRICES ARE NOT DROPPED FROM THE EXECUTION PATH BY THIS FUNCTION. Apply it to
    the SCORE panel -- the set of names that may be ranked and bought. A name being
    sold after exclusion still needs its price on the sale date, and this project
    has already been bitten once by filtering prices for a non-price reason: the
    dropna(subset=FEATS_V2) that fed ffill and manufactured returns of up to
    +24,773%. Keep price and eligibility separate.
    """
    if not is_pit() or membership is None:
        return panel
    if panel.empty:
        return panel
    return panel[member_mask(panel, membership, date_col, symbol_col)].copy()


def member_mask(panel, membership, date_col="date", symbol_col="symbol"):
    """Boolean array over `panel`'s rows: True where the row is a member on its date.

    The rule apply_to_panel applies, as a mask: True for every row in static mode
    or with no membership; in pit mode True where the symbol is in the list in
    force on the row's date, and, before the first effective date, where the
    symbol is in the FIRST list. build_panel uses it for the market return, the
    z-score peer group and the scorable flag.

    BEFORE THE FIRST DATE, THE FIRST LIST, SINCE 2026-10-22. No list is in force
    there. Until then every row before it was kept, and those symbols are in the
    pit folder only because they are members on some later date, so the training
    set and the cross-sections before the first date were chosen by later
    membership. A pit run never decides before the first effective date, so the
    first list is known whenever a decision uses a row from before it.
    """
    if not is_pit() or membership is None or panel.empty:
        return np.ones(len(panel), dtype=bool)
    pos = membership._pos(panel[date_col])
    syms = panel[symbol_col].astype(str).str.upper().values
    keep = np.zeros(len(panel), dtype=bool)
    for i, (p, s) in enumerate(zip(pos, syms)):
        if s in membership.lists[max(p, 0)]:
            keep[i] = True
    return keep


def buyhold_columns(columns, first_date, membership):
    """The names the buy & hold holds: all of `columns`, or in pit mode the
    members on `first_date`, the first pit rebalance (owner's decision 2026-10-10).

    Static mode returns `columns` itself, so a static buy & hold is computed from
    the same object it always was.
    """
    if not is_pit() or membership is None:
        return columns
    m = membership.members_on(first_date)
    return [c for c in columns if str(c).upper() in m]


def buyhold_prices(px, first_date, membership):
    """`px` restricted to buyhold_columns(). Static mode returns `px` itself."""
    if not is_pit() or membership is None:
        return px
    return px[buyhold_columns(list(px.columns), first_date, membership)]


def residual_survivorship(membership, price_dir, current, lo=None, hi=None):
    """Members in force at any point of [lo, hi] that have no price file in
    `price_dir`, split into those not in `current` (dropped from the index) and
    those in it (current members). Uses the renamed lists."""
    files = {p.stem.upper() for p in list_dir(price_dir, "*.csv")}
    i0 = 0 if lo is None else max(int(membership._pos([pd.Timestamp(lo)])[0]), 0)
    i1 = (len(membership.lists) - 1 if hi is None
          else int(membership._pos([pd.Timestamp(hi)])[0]))
    seen = set().union(*membership.lists[i0:i1 + 1]) if i1 >= i0 else set()
    missing = sorted(seen - files)
    cur = {c.upper() for c in current}
    return {"members_in_window": len(seen),
            "no_price_file": len(missing),
            "no_price_file_dropped": [s for s in missing if s not in cur],
            "no_price_file_current": [s for s in missing if s in cur]}


def pit_record(membership, price_dir, current, lo, hi):
    """What every pit run must carry: the validator verdict, the residual
    survivorship and the look-ahead note. A dict, for the params JSON; lines()
    renders it for the log and RUN.txt."""
    v = membership.validation
    res = residual_survivorship(membership, price_dir, current, lo, hi)
    try:
        src = Path(membership.source).resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        src = membership.source
    return {"membership_file": src,
            "validator_verdict": "PASS" if v.ok else "FAIL",
            "validator_errors": list(v.errors),
            "validator_warnings": list(v.warnings),
            "residual_survivorship": res,
            "residual_warning": (
                f"{res['no_price_file']} of {res['members_in_window']} members in the "
                f"window have no price file ({len(res['no_price_file_dropped'])} dropped "
                f"from the index, {len(res['no_price_file_current'])} current): they "
                f"could not be held, so residual survivorship bias remains"),
            "lookahead_note": LOOKAHEAD_NOTE,
            "exit_policy": EXIT_POLICY}


def params_fields(tag):
    """The params JSON entry a pit run adds: {"survivorship": the pit record}.
    {} in a static run, so a static params file keeps its exact key set."""
    if not is_pit():
        return {}
    return {"survivorship": {"state": describe_state(),
                             **PIT_RECORDS.get(tag, {})}}


def pit_record_lines(rec):
    """pit_record as text, for run.log and RUN.txt."""
    res = rec["residual_survivorship"]
    out = [f"membership file     : {rec['membership_file']}",
           f"validator verdict   : {rec['validator_verdict']} (used anyway, by the "
           f"owner's decision; quote pit figures with this verdict)"]
    out += [f"  error   : {e}" for e in rec["validator_errors"]]
    out += [f"  warning : {w}" for w in rec["validator_warnings"]]
    out += [f"residual survivorship: {rec['residual_warning']}",
            f"  dropped, no price : {', '.join(res['no_price_file_dropped']) or 'none'}",
            f"  current, no price : {', '.join(res['no_price_file_current']) or 'none'}",
            f"look-ahead          : {rec['lookahead_note']}",
            f"exit policy         : {rec['exit_policy']}"]
    return out


def describe_state() -> str:
    """One line naming the current configuration, for logs and chart subtitles."""
    if not is_pit():
        return ("SURVIVORSHIP_MODE=static -- universe is today's members backfilled; "
                "results carry survivorship bias")
    return (f"SURVIVORSHIP_MODE=pit, EXIT_POLICY={EXIT_POLICY} -- universe is "
            f"point-in-time membership")


# The point-in-time membership history, or None. This is the ONE place it is held,
# so `market_data.MEMBERSHIP` is what every consumer reads -- test_exposure included.
# Setting it is not enough on its own: sv.set_mode("pit") must also be called, and
# every survivorship call site below is guarded on that, so leaving the mode at
# "static" keeps all three touch points byte-identical no-ops.
#
# It stays None here because no membership file has passed sv.validate() yet. The
# only file supplied to this project fails the gate (no RELIANCE, INFY, ITC, SBIN
# or ICICIBANK in any of its 76 lists, a bond ticker among the constituents, and
# list[t] != list[t-1] + inclusions - exclusions on 20 of 75 transitions).
MEMBERSHIP = None


# PIT RUNS ONLY: {tag: Membership}, filled once by run.py when --survivorship pit
# is selected. run.py sets MEMBERSHIP from it before each universe's step and arm
# run; a step that loops over universes itself (make_daily_log) calls
# membership_for(u) per universe. Empty in a static run, so membership_for() is
# None and every touch point stays a no-op.
PIT_MEMBERSHIPS = {}


# {tag: market_data.pit_record(...)} for the same universes, read by the params
# JSON writers so every pit artefact carries its verdict.
PIT_RECORDS = {}


def membership_for(u):
    """u's membership in a pit run, else None."""
    return PIT_MEMBERSHIPS.get(u.tag) if is_pit() else None


# ======================================================================================
# TRADABILITY: A NAME TRADES ONLY ON A SESSION WITH A ROW. From tradability.py and engine_core.py (moved 2026-11-27).
# ======================================================================================
# tradability.py -- which (symbol, date) pairs the backtest may transact on.
#
# WHAT THIS EXISTS TO STOP
#     px and op are pivots with .ffill() applied -- 41 such pivots across 37 files.
#     A symbol that did not trade on a date still carries a price: the last one it
#     had. A fill at that price is a fill at a price nobody quoted, and a holding
#     marked at it is marked at a stale mark.
#
#     Measured before this module existed, on MidCap150:
#       PATANJALI  51 sessions with no raw row, ffill froze it at Rs 1.10, and the
#                  resumption row is Rs 5.35 -- a +386% single-day return that the
#                  EXTREME_RET guard flags but that px/op still trade through.
#       AIIL       73 sessions with no raw row across 44 separate gaps, on a stock
#                  whose median day is Rs 900,042 of turnover.
#       HEXT       1,069 sessions -- Hexaware delisted in 2020 and relisted in 2025 --
#                  and the resumption close is 762.55 against a pre-delisting close
#                  of 762.55, an exact match across 4.3 years.
#
#     NONE of these are visible to the existing guards. They never trip the +-55%
#     EXTREME_RET scan (AIIL and HEXT move less than that), and they never trip
#     "no open price (NaN/<=0)" because ffill supplies a price -- that reason fires
#     ZERO times across every midcap150 and nifty100 trail. Asking whether a RAW ROW EXISTED
#     is the only thing that finds them.
#
# WHY A SEPARATE, PRICE-SIDE FLAG AND NOT bad_ret OR scorable
#     bad_ret feeds the feature mask and the fwd_ret label; it is return-side.
#     scorable is deliberately SCORE-side (engine_core.py:325, :340, :366) -- the
#     price/score separation exists because the old `dropna(subset=FEATS_V2)` deleted
#     PRICES for a feature reason and ffill then bridged the hole, which is where the
#     +24,772.7% PATANJALI figure came from. Widening scorable would re-introduce
#     exactly that. This is a third flag and it gates TRANSACTING, not ranking.
#
# THE RULE THE ENGINE APPLIES, SINCE 2026-10-16: sessions_with_row()
#     A name is traded only on a session that has a row for it: a valid open and
#     close, on the trading calendar. On any other session nothing in it is bought or
#     sold. A held name keeps its position, valued at its last close, and a sale due
#     on such a session waits for the next session with a row, at that session's
#     open. market_data.tradeable_on(symbol, dt) asks only whether `dt` itself has a
#     row, so no decision reads a row dated after it.
#
#     UNTIL 2026-10-16 THE ENGINE USED untradeable() BELOW, AND IT LOOKED AHEAD. It
#     blocked a gap only when two or more sessions were missing, a length known only
#     from the date of the next row, and test_exposure sold a holding at the open of
#     the last session before the gap because the next session had no row. Both read
#     rows dated after the decision day. untradeable(), gaps() and
#     resumption_report() were deleted on 2026-10-22; nothing called them.
#
# READ-ONLY AGAINST THE RAW DATA. Nothing here changes a price.


def sessions_with_row(data_dir, cal):
    """{symbol: frozenset(sessions on which the symbol has a row)}.

    A row is a calendar session with an open and a close above zero: the rows
    market_data.build_panel keeps as prices, measured equal to the panel's own
    (date, symbol) pairs on 2026-10-16. A symbol is tradeable on `dt` only if `dt`
    is in its set. The set is built once from the whole file, but the only
    question asked of it is about one date at a time, so no answer depends on a
    later row.
    """
    out = {}
    for f in list_dir(data_dir, "*.csv"):
        d = read_price_csv(f)
        if "date" not in d.columns:
            continue
        ok = d["date"].isin(cal)
        for c in ("open", "close"):
            if c in d.columns:
                ok &= d[c] > 0
        out[f.stem] = frozenset(d.loc[ok, "date"])
    return out


def median_volume(data_dir, cal, lo=None, hi=None, win=20):
    """{symbol: {date: prior-`win`-session MEDIAN volume}} -- the cap's denominator.

    PRIOR, so the cap never uses the day's own volume -- that would be look-ahead
    on the very quantity the cap exists to constrain. MEDIAN rather than mean,
    because one block trade should not licence a large fill: AIIL's mean is dragged
    up by occasional 300,000-share days against a median of 1,272.

    THE `win` SESSIONS BEFORE `lo` ARE READ, and the result is then cut to `lo`
    onwards. Until 2026-10-14 the data was cut at `lo` before the rolling median,
    so no symbol had a median in the window's first `win` sessions and every
    first-rebalance buy went uncapped. The extra rows are all before the date they
    serve, so the shift still keeps the day's own volume out.
    """
    import pandas as pd
    out = {}
    for f in list_dir(data_dir, "*.csv"):
        d = read_price_csv(f)
        if "volume" not in d.columns:
            continue
        d = d[d["date"].isin(cal)].sort_values("date")
        if hi is not None:
            d = d[d["date"] <= hi]
        if lo is not None:
            d = pd.concat([d[d["date"] < lo].tail(win), d[d["date"] >= lo]])
        med = d["volume"].rolling(win).median().shift(1)
        if lo is not None:
            keep = (d["date"] >= lo).to_numpy()
            d, med = d[keep], med[keep]
        out[f.stem] = dict(zip(d["date"], med))
    return out


# ---------------------------------------------------------------------------
# STUCK POSITIONS. Was results/stuck_positions.py until 2026-10-18 (last at aebf1da).
# ---------------------------------------------------------------------------
# stuck_positions.py -- holdings whose price file ends before the window does.
#
# Under the row rule (results/tradability.py) a name is sold only on a session with
# a row. A sale owed on a name whose file has ended never fills, so the name is held
# to the window's end, valued at its last close (owner's decision, 2026-10-16). That
# value is an assumption: the repository does not record why such a file ends.
#
# For every cell that still holds such a name on its last session, this reports the
# shares and the value they are held at, and the end equity, CAGR and maximum
# drawdown if the position were valued at zero from the first session after its last
# row. It is arithmetic on the cell's own daily_holdings and daily_summary files,
# with the CAGR and drawdown formulas of engine_core.metrics; nothing is rerun. Tax
# already charged is left as it is: the zero valuation changes no realised gain.
#
# run.py prints these lines in the run log and writes them to RUN.txt. A cell with no
# such holding gets no line, so every other RUN.txt is unchanged.

def last_rows(u):
    """{symbol: its last session with a row} for universe `u`."""
    rows = sessions_with_row(u.prepare_data_dir(), _load_calendar())
    return {s: max(d) for s, d in rows.items() if d}


# ---------------------------------------------------------------------------
# TRADEABILITY -- the third, PRICE-SIDE flag. See results/tradability.py.
# ---------------------------------------------------------------------------
# {symbol: frozenset(sessions with a row)}, or None for "no rule". Held here, next
# to MEMBERSHIP, for the same reason and read the same way:
# test_exposure.backtest_exposure consults it directly rather than taking it as an
# argument, so all 25 of its call sites inherit the rule without a signature
# change. Threading a parameter through 25 sites is how a rule ends up applied in
# four places and absent in twenty-one.
#
# THE RULE, SINCE 2026-10-16 (results/tradability.py). A name is traded only on a
# session with a row for it. tradeable_on(symbol, dt) answers that for `dt` alone,
# so no decision on day i reads a row dated after day i. Until 2026-10-16 this held
# a map of blocked sessions built from gaps of two or more sessions, whose length
# is known only from the next row, and test_exposure sold a holding the session
# before such a gap. tradability_causality_test.py fails on that code.
#
# THE LEAK THIS GUARDS AGAINST. module_state.py records the hazard: a module global
# set by one in-process step and never restored silently changes every later step.
# rebal_cadence_sweep.py did exactly that with test_exposure.REBAL, which is why
# cadence is a parameter and not a global. Tradeability is different in kind -- it
# is a property of a UNIVERSE's raw data, stable for the whole run, like MEMBERSHIP
# -- but the leak is still real: midcap150's sets left in place while nifty100 runs
# would block every nifty100 name, or worse, share a ticker. So the tag is stored
# beside the sets.
TRADEABLE = None


TRADEABLE_TAG = None


def set_tradeability(u, enabled=True):
    """Load (or clear) the sessions-with-a-row sets for universe `u`. Returns them."""
    global TRADEABLE, TRADEABLE_TAG
    if not enabled:
        TRADEABLE, TRADEABLE_TAG = None, None
        return None
    TRADEABLE = sessions_with_row(u.prepare_data_dir(), _load_calendar())
    TRADEABLE_TAG = u.tag
    return TRADEABLE


def tradeable_on(symbol, dt):
    """True when no rule is loaded, or when `symbol` has a row on `dt` itself.

    Only `dt` is looked up. A symbol with no file has no rows and is never
    tradeable."""
    if TRADEABLE is None:
        return True
    rows = TRADEABLE.get(symbol)
    return rows is not None and dt in rows
