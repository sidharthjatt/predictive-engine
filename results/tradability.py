"""tradability.py -- which (symbol, date) pairs the backtest may transact on.

WHAT THIS EXISTS TO STOP
    px and op are pivots with .ffill() applied -- 41 such pivots across 37 files.
    A symbol that did not trade on a date still carries a price: the last one it
    had. A fill at that price is a fill at a price nobody quoted, and a holding
    marked at it is marked at a stale mark.

    Measured before this module existed, on MidCap150:
      PATANJALI  51 sessions with no raw row, ffill froze it at Rs 1.10, and the
                 resumption row is Rs 5.35 -- a +386% single-day return that the
                 EXTREME_RET guard flags but that px/op still trade through.
      AIIL       73 sessions with no raw row across 44 separate gaps, on a stock
                 whose median day is Rs 900,042 of turnover.
      HEXT       1,069 sessions -- Hexaware delisted in 2020 and relisted in 2025 --
                 and the resumption close is 762.55 against a pre-delisting close
                 of 762.55, an exact match across 4.3 years.

    NONE of these are visible to the existing guards. They never trip the +-55%
    EXTREME_RET scan (AIIL and HEXT move less than that), and they never trip
    "no open price (NaN/<=0)" because ffill supplies a price -- that reason fires
    ZERO times across every midcap150 and nifty100 trail. Asking whether a RAW ROW EXISTED
    is the only thing that finds them.

WHY A SEPARATE, PRICE-SIDE FLAG AND NOT bad_ret OR scorable
    bad_ret feeds the feature mask and the fwd_ret label; it is return-side.
    scorable is deliberately SCORE-side (engine_core.py:325, :340, :366) -- the
    price/score separation exists because the old `dropna(subset=FEATS_V2)` deleted
    PRICES for a feature reason and ffill then bridged the hole, which is where the
    +24,772.7% PATANJALI figure came from. Widening scorable would re-introduce
    exactly that. This is a third flag and it gates TRANSACTING, not ranking.

THE WINDOW
    Untradeable from the FIRST MISSING SESSION through the RESUMPTION SESSION
    inclusive, plus `wait` further sessions. The last raw row before the gap is NOT
    included: it has a real price and is precisely where a forced exit fills. The
    resumption session IS included, because its own close is the one cell most
    likely to be fabricated -- see resumption_report() below.

READ-ONLY AGAINST THE RAW DATA. Nothing here changes a price.
"""
from pathlib import Path

import config

MIN_GAP = 2          # a gap of this many missing sessions or more is guarded
WAIT = 0             # further sessions blocked after the resumption session

# Axis c is a REPORT, not a repair. A resumption close that matches the
# pre-gap close is only suspicious when a coincidence is implausible: 20 of the 21
# exact matches in midcap150+nifty100 are AIIL between Rs 0.40 and Rs 2.90, where the tick is
# Rs 0.05 and only a handful of prices are reachable. Conditioning on a long gap
# leaves exactly one flag -- HEXT -- instead of 21.
REPORT_MIN_GAP = 20
REPORT_TOL = 0.001   # 0.1%


def _rows(data_dir, cal):
    """{symbol: [dates with a raw row, ascending]} -- calendar-restricted.

    config.read_price_csv routes through config.smart_parse_dates: the retired universes' files
    and the midcap150/nifty100 files use different date formats and a hardcoded strptime
    silently drops whole universes.

    The calendar restriction matters in both directions. 70 of the 148 MidCap150
    files carry market-holiday rows that are not sessions; counting one of those as
    "a raw row exists" would hide a real gap.
    """
    out = {}
    for f in sorted(Path(data_dir).glob("*.csv")):
        d = config.read_price_csv(f)
        if "date" not in d.columns:
            continue
        out[f.stem] = sorted(x for x in d["date"] if x in cal)
    return out


def gaps(data_dir, cal, lo=None, hi=None):
    """[(symbol, last_raw, first_after, n_missing)] for every INTERIOR gap.

    INTERIOR is the point: counting sessions absent from the whole window makes
    every 2025 IPO look like a 1,700-session hole. Only sessions missing BETWEEN a
    symbol's own first and last row are gaps.
    """
    cals = sorted(cal)
    ci = {d: i for i, d in enumerate(cals)}
    out = []
    for sym, ds in _rows(data_dir, cal).items():
        ds = [d for d in ds if (lo is None or d >= lo) and (hi is None or d <= hi)]
        for a, b in zip(ds, ds[1:]):
            n = ci[b] - ci[a] - 1
            if n > 0:
                out.append((sym, a, b, n))
    return out


def untradeable(data_dir, cal, lo=None, hi=None, min_gap=MIN_GAP, wait=WAIT):
    """{symbol: frozenset(dates the backtest may not transact on)}."""
    cals = sorted(cal)
    ci = {d: i for i, d in enumerate(cals)}
    out = {}
    for sym, a, b, n in gaps(data_dir, cal, lo, hi):
        if n < min_gap:
            continue
        blocked = out.setdefault(sym, set())
        for k in range(ci[a] + 1, min(ci[b] + wait + 1, len(cals))):
            blocked.add(cals[k])
    return {k: frozenset(v) for k, v in out.items() if v}


def resumption_report(data_dir, cal, lo=None, hi=None,
                      min_gap=REPORT_MIN_GAP, tol=REPORT_TOL):
    """[(symbol, last, first, n, prev_close, new_close, pct)] worth a human look.

    REPORT ONLY. The true close is unknowable, so nothing is repaired; the gap
    guard above already makes the symbol untradeable across the hole.
    """
    hits = []
    for f in sorted(Path(data_dir).glob("*.csv")):
        d = config.read_price_csv(f)
        if "close" not in d.columns:
            continue
        d = d[d["date"].isin(cal)].sort_values("date")
        if lo is not None:
            d = d[d["date"] >= lo]
        if hi is not None:
            d = d[d["date"] <= hi]
        d = d.reset_index(drop=True)
        cals = sorted(cal)
        ci = {x: i for i, x in enumerate(cals)}
        for i in range(1, len(d)):
            n = ci[d["date"][i]] - ci[d["date"][i - 1]] - 1
            if n < min_gap:
                continue
            pc, nc = float(d["close"][i - 1]), float(d["close"][i])
            if pc and abs(nc / pc - 1) <= tol:
                hits.append((f.stem, d["date"][i - 1], d["date"][i], n, pc, nc,
                             (nc / pc - 1) * 100))
    return hits


def median_volume(data_dir, cal, lo=None, hi=None, win=20):
    """{symbol: {date: prior-`win`-session MEDIAN volume}} -- the cap's denominator.

    PRIOR, so the cap never uses the day's own volume -- that would be look-ahead
    on the very quantity the cap exists to constrain. MEDIAN rather than mean,
    because one block trade should not licence a large fill: AIIL's mean is dragged
    up by occasional 300,000-share days against a median of 1,272.
    """
    import pandas as pd
    out = {}
    for f in sorted(Path(data_dir).glob("*.csv")):
        d = config.read_price_csv(f)
        if "volume" not in d.columns:
            continue
        d = d[d["date"].isin(cal)].sort_values("date")
        if lo is not None:
            d = d[d["date"] >= lo]
        if hi is not None:
            d = d[d["date"] <= hi]
        med = d["volume"].rolling(win).median().shift(1)
        out[f.stem] = dict(zip(d["date"], med))
    return out
