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
    open. market_data.tradeable_on(symbol, dt) asks only whether `dt` itself has a
    row, so no decision reads a row dated after it.

    UNTIL 2026-10-16 THE ENGINE USED untradeable() BELOW, AND IT LOOKED AHEAD. It
    blocked a gap only when two or more sessions were missing, a length known only
    from the date of the next row, and test_exposure sold a holding at the open of
    the last session before the gap because the next session had no row. Both read
    rows dated after the decision day. untradeable(), gaps() and
    resumption_report() were deleted on 2026-10-22; nothing called them.

READ-ONLY AGAINST THE RAW DATA. Nothing here changes a price.
"""
import sys
from pathlib import Path

# The repository root, for settings, costs, market_data and model when this file runs as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings
from market_data import read_table  # the one CSV/parquet reader: market_data.read_table
from settings import list_dir
from market_data import last_rows


def _cagr(e):
    ny = (e.index[-1] - e.index[0]).days / 365.25
    return ((e.iloc[-1] / e.iloc[0]) ** (1 / ny) - 1) * 100


def _maxdd(e):
    return float(((e - e.cummax()) / e.cummax()).min() * 100)


def cell_lines(u, tag, last=None):
    """RUN.txt lines for one cell, named by its artefact tag; [] when nothing is stuck."""
    M = Path(u.metrics_dir)
    hf, sf = M / f"daily_holdings_{tag}.csv", M / f"daily_summary_{tag}.csv"
    if not hf.exists() or not sf.exists():
        return []
    h = read_table(hf, parse_dates=["date"])
    eq = read_table(sf, parse_dates=["date"]).set_index("date")["total"]
    end = eq.index[-1]
    last = last_rows(u) if last is None else last
    stuck = [r for r in h[h["date"] == end].itertuples()
             if r.symbol in last and last[r.symbol] < end]
    if not stuck:
        return []
    at_zero = eq.copy()
    out = []
    for r in stuck:
        lr = last[r.symbol]
        after = h[(h["symbol"] == r.symbol) & (h["date"] > lr)].set_index("date")["value"]
        at_zero = at_zero.sub(after.reindex(at_zero.index).fillna(0.0))
        out.append(f"stuck     : {tag} -- {r.symbol}: {int(r.qty):,} shares with no row "
                   f"after {lr.date()}, held at its last close {float(r.price):,.2f} = "
                   f"Rs {float(r.value):,.2f} on {end.date()}")
    out.append(f"at zero   : {tag} -- valued at zero from the session after its last row: "
               f"end equity Rs {at_zero.iloc[-1]:,.2f} (as run Rs {eq.iloc[-1]:,.2f}), "
               f"CAGR {_cagr(at_zero):.2f}% (as run {_cagr(eq):.2f}%), "
               f"MaxDD {_maxdd(at_zero):.2f}% (as run {_maxdd(eq):.2f}%)")
    return out


def run_lines(universes, arms):
    """The lines for every (universe, arm) cell of one run.py invocation."""
    import audit_step
    from settings import survivorship_axis as _sva
    import settings
    out = []
    for u in universes:
        if not _sva.is_default() and settings.has_pit(u) and not u.is_pit:
            u = settings.pit_variant(u)
        last = None
        for a in arms:
            if last is None:
                last = last_rows(u)
            out += cell_lines(u, audit_step.artefact_tag(u, a), last)
    return out
