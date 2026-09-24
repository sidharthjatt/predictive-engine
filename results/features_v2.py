"""
features_v2.py -- Feature set v2: breaking the dependence on momentum
=====================================================================
Problem (identified by diagnose_alpha.py): around 10 of the previous 16 features
were momentum. The model rested on a single factor, and when momentum broke down
in 2022 and 2025 the IC went negative and the strategy died with it.

Fix: five distinct factor families. Each measures something different, so when one
family fails the others can carry the signal.

  A) MOMENTUM (kept, but reduced)          -- trend continuation
  B) REVERSAL                              -- short-term overreaction snap-back
  C) VOLATILITY / RISK                     -- idio vol, beta, downside vol
  D) LIQUIDITY / VOLUME                    -- Amihud illiquidity, turnover, vol-price divergence
  E) QUALITY OF TREND                      -- consistency, path smoothness

Everything is causal: only data up to time t, no lookahead anywhere.
Beta and idiosyncratic vol are measured against the market, where the market is the
equal-weight universe built from past prices only -- no external index is used.

This file is only the feature builder. The engine imports it.
"""
import numpy as np
import pandas as pd
from numerics import group_mean_std, rolling_std, rolling_var  # platform-identical variance: results/numerics.py


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
# price move. Measured on the 58: 32 returns across 10 symbols exceed these, and
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
    """Per-stock features. df needs: date, open, high, low, close, volume."""
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
    rupee_vol = c * v
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


def add_market_relative_features(panel):
    """Beta and idiosyncratic volatility, measured against the market.
    Market = the equal-weight return of the universe (past-only, no lookahead).
    This has to happen at panel level because the market is built from all stocks.
    """
    panel = panel.sort_values(["symbol", "date"]).copy()

    # market return: the mean of all available stocks each day (point-in-time)
    mkt = panel.groupby("date")["ret_1d"].mean().rename("mkt_ret")
    panel = panel.merge(mkt, on="date", how="left")

    # beta = cov(y, x) / var(x) over 60d; idio_vol = std(y - beta*x) over 60d
    #
    # THE 60-DAY WINDOW RUNS OVER EACH SYMBOL'S OWN TRADING DATES, NOT THE UNION.
    #     An earlier version rolled over a wide pivot indexed by the UNION of every
    #     symbol's dates. On that index a symbol is NaN on any day it did not trade,
    #     and pandas' rolling(60) needs 60 non-NaN observations, so a single missing
    #     day voided that symbol's next 60 windows.
    #
    #     Harmless on the 58 and the 74, where essentially every name trades every
    #     day. Fatal on MidCap150, where median per-symbol coverage of the union
    #     index is 70.6%: beta_60 survived on 42.1% of rows and idio_vol_60 on
    #     35.7%, against 93.8-100% for the other fifteen features. Since the panel
    #     drops any row with a NaN feature, only 32.9% of rows survived, and the
    #     symbols that fell out were forward-filled to a flat price -- giving them
    #     exactly zero momentum, which silently pushed breadth from 0.550 to 0.202.
    #
    #     Computing per symbol removes the coupling: a gap in one name can no longer
    #     void windows in that name, and never could in any other. Where a symbol
    #     trades every union date the two are arithmetically identical, which is why
    #     the 58 is the control for this change.
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
