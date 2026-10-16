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

THE RULE THE ENGINE APPLIES, SINCE 2026-10-16: sessions_with_row()
    A name is traded only on a session that has a row for it: a valid open and
    close, on the trading calendar. On any other session nothing in it is bought or
    sold. A held name keeps its position, valued at its last close, and a sale due
    on such a session waits for the next session with a row, at that session's
    open. engine_core.tradeable_on(symbol, dt) asks only whether `dt` itself has a
    row, so no decision reads a row dated after it.

    UNTIL 2026-10-16 THE ENGINE USED untradeable() BELOW, AND IT LOOKED AHEAD. It
    blocked a gap only when two or more sessions were missing, a length known only
    from the date of the next row, and test_exposure sold a holding at the open of
    the last session before the gap because the next session had no row. Both read
    rows dated after the decision day. untradeable() and gaps() are kept for the
    measurement scripts that report on gaps; no backtest reads them.

READ-ONLY AGAINST THE RAW DATA. Nothing here changes a price.
"""
from pathlib import Path

import config
from paths import list_dir

MIN_GAP = 2          # untradeable() only: gaps this long or longer are reported
WAIT = 0             # untradeable() only: sessions reported after the resumption

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
    for f in list_dir(data_dir, "*.csv"):
        d = config.read_price_csv(f)
        if "date" not in d.columns:
            continue
        out[f.stem] = sorted(x for x in d["date"] if x in cal)
    return out


def sessions_with_row(data_dir, cal):
    """{symbol: frozenset(sessions on which the symbol has a row)}.

    A row is a calendar session with an open and a close above zero: the rows
    engine_core.build_panel keeps as prices, measured equal to the panel's own
    (date, symbol) pairs on 2026-10-16. A symbol is tradeable on `dt` only if `dt`
    is in its set. The set is built once from the whole file, but the only
    question asked of it is about one date at a time, so no answer depends on a
    later row.
    """
    out = {}
    for f in list_dir(data_dir, "*.csv"):
        d = config.read_price_csv(f)
        if "date" not in d.columns:
            continue
        ok = d["date"].isin(cal)
        for c in ("open", "close"):
            if c in d.columns:
                ok &= d[c] > 0
        out[f.stem] = frozenset(d.loc[ok, "date"])
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
    for f in list_dir(data_dir, "*.csv"):
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

    THE `win` SESSIONS BEFORE `lo` ARE READ, and the result is then cut to `lo`
    onwards. Until 2026-10-14 the data was cut at `lo` before the rolling median,
    so no symbol had a median in the window's first `win` sessions and every
    first-rebalance buy went uncapped. The extra rows are all before the date they
    serve, so the shift still keeps the day's own volume out.
    """
    import pandas as pd
    out = {}
    for f in list_dir(data_dir, "*.csv"):
        d = config.read_price_csv(f)
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
