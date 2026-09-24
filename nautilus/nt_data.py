"""
nt_data.py -- build Nautilus instruments and market data from the project's raw CSVs.

EXECUTION MODEL (established by verify_next_open_execution.py):
    each trading day is fed as separate events, so that the execution price is
    explicit rather than an artefact of how the exchange decomposes a bar
    internally:

        09:15  QuoteTick   bid = open * (1 - SLIPPAGE)
                           ask = open * (1 + SLIPPAGE)
                           both sides sized QUOTE_DEPTH  <- orders execute here
        15:30  Bar         the day's RAW OHLC, untouched by the tick grid
                                                         <- signals come from here

    Under DEPTH_MODE="volume" one further event precedes the quote:
    OrderBookDeltas carrying DEPTH_LEVELS priced levels, each sized from the
    symbol's own median volume. See the DEPTH MODE block below. The DEFAULT is
    "unlimited", which emits exactly the two events above.

    NO TradeTick IS CONSTRUCTED HERE, AND NONE EVER WAS.
        This docstring read "09:15 TradeTick at the day's OPEN" until 2026-08-23.
        The code has always built a QuoteTick (see the construction below),
        because execution needs a TWO-SIDED price: a single traded price makes
        slippage adverse for buys and favourable for sells. TradeTick is not even
        imported by this module.

    THE NEXT-OPEN RULE IS NOT ENFORCED BY LATENCY.
        This docstring previously credited "a LatencyModel on the venue".
        nt_run.py sets LATENCY_NS = 0, so the latency model delays nothing. The
        rule is enforced by the STRATEGY: it plans at on_daily_close (15:30) and
        releases the orders from on_market_open at 09:16 the next trading day.
        See nt_strategy.on_market_open.

PRICE SOURCE -- this must match the reference engine exactly
    The reference engine reads its price panel from results/metrics/v5_expanding_cache.csv,
    NOT from the raw CSVs. Both hold the same prices per symbol, but the PANEL is
    the union of every symbol's dates and is forward filled, so a different set of
    dates shifts what "20 rows back" means for every symbol at once.

    That path is the 58 universe's. There are now four universes and the cache is
    a PARAMETER -- load_panel(cache_path) -- with the per-universe paths held in
    nt_run.UNIVERSES. The rule is unchanged whichever universe is loaded: the port
    reads the same cache its reference engine reads.

    Reading raw CSVs here produced a 6,574-row panel against the engine's 6,322,
    and on 2019-01-01 that gave breadth 27/53 where the engine had 17/53 -- exposure
    51% instead of 32%. The port then ran roughly twice as invested for seven years.

    So the loader reads the same cache the engine reads. Reconciliation between two
    systems is only meaningful when both are fed identical input.

This module reads from results/ but never writes there. The existing pipeline is
untouched.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import (Bar, BarType, BookOrder,
                                        OrderBookDelta, OrderBookDeltas,
                                        QuoteTick)
from nautilus_trader.model.enums import BookAction, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity
from config import read_table  # the one CSV/parquet reader: config.read_table

VENUE = Venue("NSE")
OPEN_TIME = pd.Timedelta(hours=9, minutes=15)    # NSE open
CLOSE_TIME = pd.Timedelta(hours=15, minutes=30)  # NSE close
# NSE's real tick size for these price bands is 0.05. The reference engine does not
# round prices at all, so a run at 0.05 will not reconcile exactly with it -- on a
# Rs 27 stock one tick is 0.18%, which changes the share count.
# TICK_SIZE is therefore configurable: run at 0.01 to prove the two systems are
# otherwise identical, then at 0.05 for the number that could actually be traded.
TICK_SIZE = "0.05"
# The bars carry RAW historical prices (see the Bar construction below), and those
# are not all two-decimal: 10.7% of the MidCap150 panel's opens and closes have more
# precision than that, and its cheapest observation is 0.0128. A precision of 2 would
# therefore re-introduce, as a formatting artefact, exactly the rounding noise that
# removing the bar tick is meant to eliminate -- and on the same sub-Rs-10 names.
# 1e-6 is 0.008% of the cheapest price in any panel, i.e. negligible against a daily
# return. Quote prices are unaffected in value: a tick-rounded 2.54 expressed at this
# precision is 2.540000, the identical number.
PRICE_PRECISION = 6
QUOTE_DEPTH = 10_000_000   # shares available at the opening quote

# ---------------------------------------------------------------------------
# DEPTH MODE -- how much size the opening quote actually offers
# ---------------------------------------------------------------------------
# "unlimited" (default)  QUOTE_DEPTH shares at one price. Every order fills in
#                        full at open*(1 +/- SLIPPAGE). This is what the whole
#                        reconciliation rests on: the reference engine also fills
#                        everything at that single price, so any depth model would
#                        make the two disagree by construction. nt_verify MUST run
#                        in this mode, and does.
#
# "volume"               Depth tied to the symbol's own liquidity. The top level
#                        offers 10% of its prior-20-day median daily volume, and
#                        two further levels sit behind it at progressively worse
#                        prices, so a large order WALKS instead of being rejected.
#
# LEVEL SPACING IS ONE SLIPPAGE STEP, AND THAT IS NOT AN ARBITRARY NUMBER.
#     The levels are placed at open*(1 +/- 1*SLIPPAGE), *(1 +/- 2*SLIPPAGE) and
#     *(1 +/- 3*SLIPPAGE) -- 0.15% apart, the project's existing flat slippage
#     constant. Chosen so the two models line up at the boundary: an order that
#     fits inside the top level pays exactly what the flat model charged it, and
#     only the excess pays more. Any other spacing would move every fill, mixing a
#     re-calibration of the base cost into a measurement of size impact.
#
# THREE LEVELS, NOT TWO OR TEN. Three covers 30% of median daily volume in total,
# which is far beyond anything a real execution would attempt in one print, so an
# order that exhausts all three is genuinely untradeable rather than merely
# expensive -- and those are reported rather than silently clipped.
DEPTH_MODE = "unlimited"        # "unlimited" | "volume"
DEPTH_FRACTION = 0.10           # top-level depth as a share of median daily volume
DEPTH_LEVELS = 3
DEPTH_VOL_WIN = 20              # trading days in the median-volume lookback


def set_depth_mode(mode: str):
    """Set the depth model. Raises rather than silently accepting a typo."""
    global DEPTH_MODE
    if mode not in ("unlimited", "volume"):
        raise ValueError(f"depth mode must be 'unlimited' or 'volume', got {mode!r}")
    DEPTH_MODE = mode


# {symbol: Series of daily volume}. Populated by set_volume_source(); empty in
# "unlimited" mode, where it is never consulted.
_VOLUME = {}


def set_volume_source(raw_dir, symbols=None):
    """Load daily volume for the universe from its source CSVs.

    Volume is NOT in the price panel -- build_panel keeps open/close and the
    features and drops it -- so the depth model reads the same source files
    nt_data already reads bars from.
    """
    global _VOLUME
    import config as _cfg
    _VOLUME = {}
    raw_dir = Path(raw_dir)
    for f in sorted(raw_dir.glob("*.csv")):
        if symbols is not None and f.stem not in symbols:
            continue
        try:
            d = _cfg.read_price_csv(f)
        except Exception:
            continue
        if "volume" not in d.columns:
            continue
        s = d[["date", "volume"]].dropna().set_index("date")["volume"].sort_index()
        _VOLUME[f.stem] = s[s > 0]
    return len(_VOLUME)


# ---------------------------------------------------------------------------
# NSE CASH-SEGMENT TICK SIZE, FROM NSE'S OWN CIRCULARS
# ---------------------------------------------------------------------------
# Established from primary sources, not memory. Both PDFs and their extracted
# text are kept in diagnostics/.
#
#   NSE/CMTR/62174, dated 24 May 2024, effective TRADE DATE 10 June 2024
#     "Exchange is pleased to introduce price linked tick size in the Capital
#      Market Segment ... against the current tick size Rs 0.05"
#     "If the reference price is less than Rs 250 the tick size will be Rs 0.01
#      else regular tick size of Rs 0.05 will be applicable"
#
#   NSE/CMTR/67133, dated 13 March 2025, effective TRADE DATE 15 April 2025
#     Below 250 -> 0.01 (unchanged) | >=250 to 1,000 -> 0.05 (unchanged)
#     >1,000 to 5,000 -> 0.10 | >5,000 to 10,000 -> 0.50
#     >10,000 to 20,000 -> 1.00 | >20,000 -> 5.00
#
# TWO CONSEQUENCES THAT MATTER, BOTH AGAINST THE ASSUMPTION THIS REPLACES:
#   1. Rs 0.01 is the FINEST tick NSE defines. There is nothing below one paisa,
#      so a sub-Rs-10 stock does NOT trade on a finer grid than 0.01.
#   2. The sub-Rs-250 rule POST-DATES the backtest start by five and a half
#      years. From 2019-01-01 to 2024-06-09 every cash-segment security,
#      including a Rs 2 stock, traded on Rs 0.05. Applying today's rule to those
#      years would be an anachronism that flatters the backtest.
#
# The tick for a month is set by the PREVIOUS month's closing price, per the
# circular: "revised tick size (if any) will be applicable from first trading
# day of the month which will be determined by the latest available closing
# price on the last trading day of the previous trading month."
TICK_RULE_2024 = pd.Timestamp("2024-06-10")     # CMTR/62174 effective date
TICK_RULE_2025 = pd.Timestamp("2025-04-15")     # CMTR/67133 effective date

# "fixed" reproduces the previous behaviour exactly (uniform TICK_SIZE) and is
# what the reconciliation proof uses, because that proof needs the FINEST grid to
# separate quantization from genuine logic differences. "nse" applies the real
# dated rule and is what a realistic run should use.
TICK_MODE = "nse"


def set_tick_mode(mode):
    global TICK_MODE
    TICK_MODE = mode


def nse_tick(ref_price, date):
    """The exchange tick in force for `ref_price` on `date`."""
    if date < TICK_RULE_2024:
        return 0.05                      # uniform, pre-June-2024
    if ref_price < 250:
        return 0.01
    if date < TICK_RULE_2025:
        return 0.05                      # everything else, June 2024 - April 2025
    if ref_price <= 1000:
        return 0.05
    if ref_price <= 5000:
        return 0.10
    if ref_price <= 10000:
        return 0.50
    if ref_price <= 20000:
        return 1.00
    return 5.00


def _px(x) -> str:
    """Format a price at the instrument's precision, WITHOUT snapping it to a tick."""
    return f"{float(x):.{PRICE_PRECISION}f}"


def _round_to(x, tick):
    # round(..., 2) only clears binary float error in the multiplication; the value
    # is already on the tick grid by then, so it is not a second rounding step.
    return _px(round(round(float(x) / tick) * tick, 2))


def set_tick_size(value: str):
    """Override the tick size before loading data (used by the reconciliation run)."""
    global TICK_SIZE
    TICK_SIZE = value


def make_instrument(symbol: str) -> Equity:
    return Equity(
        instrument_id=InstrumentId(Symbol(symbol), VENUE),
        raw_symbol=Symbol(symbol),
        currency=INR,
        price_precision=PRICE_PRECISION,
        # In "nse" mode the grid varies by date and price band, so the instrument
        # must be able to EXPRESS the finest of them (0.01). The actual grid is
        # imposed when the quotes are generated, which is where the rule lives.
        price_increment=Price.from_str(_px("0.01" if TICK_MODE == "nse" else TICK_SIZE)),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def bar_type_for(instrument_id: InstrumentId) -> BarType:
    return BarType.from_str(f"{instrument_id}-1-DAY-LAST-EXTERNAL")


def _round_tick(x: float) -> str:
    """Snap a price to the tick grid the instrument declares."""
    t = float(TICK_SIZE)
    return _px(round(round(float(x) / t) * t, 2))


def load_panel(cache_path):
    """The engine's price panel: union date index, forward filled, exactly as
    engine_v2_final.py builds it."""
    p = read_table(cache_path, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    return px, op


def _depth_for(symbol, date) -> int:
    """Shares offered at each level: DEPTH_FRACTION of prior-20d median volume.

    Uses days STRICTLY BEFORE `date`, so the depth an order meets is knowable when
    the order is sent. Falls back to 1 share when a symbol has no volume history --
    deliberately punitive rather than silently unlimited, and it shows up in the
    walked/unfilled counts rather than hiding.
    """
    s = _VOLUME.get(symbol)
    if s is None or not len(s):
        return 1
    prior = s[s.index < pd.Timestamp(date)]
    if not len(prior):
        return 1
    med = float(prior.tail(DEPTH_VOL_WIN).median())
    return max(int(med * DEPTH_FRACTION), 1)


def quote_frame(symbol, px, op, start, end):
    """The rows the port quotes for one symbol, and the tick each row is rounded to.

    ONE DEFINITION FOR THE PORT AND FOR ITS CHECK. load_symbol_from_panel builds
    its opening quotes from these rows; results/check_b_exec_timing.py
    reconstructs the expected fill price from the same rows and the same tick.
    Until 2026-09-24 the check assumed 2-decimal prices at a 0.01 grid, which is
    what nt_verify's run produces and not what the pipeline's is.

    `tick` is the NSE tick in force on the date for the symbol's reference price
    (the close on the last trading day of the previous month, as the circular
    specifies) under TICK_MODE "nse", and TICK_SIZE under "fixed".
    """
    idx = px.index[(px.index >= start) & (px.index <= end)]
    df = pd.DataFrame({"date": idx,
                       "open": op.loc[idx, symbol].values,
                       "close": px.loc[idx, symbol].values}).dropna()
    df = df[(df[["open", "close"]] > 0).all(axis=1)]
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    df["volume"] = 1
    df = df.reset_index(drop=True)
    _m = pd.to_datetime(df["date"]).dt.to_period("M")
    _last = df.groupby(_m)["close"].last()
    _ref = _m.map(_last.shift(1)).ffill().bfill().to_numpy()
    if TICK_MODE == "nse":
        df["tick"] = [nse_tick(float(_ref[k]), pd.Timestamp(d))
                      for k, d in enumerate(df["date"])]
    else:
        df["tick"] = float(TICK_SIZE)
    return df


def load_symbol_from_panel(symbol, px, op, start, end, slippage=0.0):
    """Return (instrument, [data events]) for one stock, taken from the panel."""
    df = quote_frame(symbol, px, op, start, end)
    inst = make_instrument(symbol)
    bt = bar_type_for(inst.id)

    events = []
    for i, r in enumerate(df.itertuples(index=False)):
        # quote_frame's tick: the NSE tick for the date, or TICK_SIZE under
        # "fixed". _round_to(x, TICK_SIZE) is exactly what _round_tick did.
        rt = lambda x, _t=float(r.tick): _round_to(x, _t)
        day = pd.Timestamp(r.date).tz_localize("UTC")
        t_open = int((day + OPEN_TIME).value)
        t_close = int((day + CLOSE_TIME).value)
        # THE BAR IS SIGNAL INPUT AND CARRIES THE RAW PRICE -- NO TICK.
        # These OHLC values used to be snapped with rt() like the quote below, and
        # that was a bug. A historical close is already an actual traded price; a
        # tick governs what price an order may be PLACED at, so applying it a second
        # time to a recorded price models nothing and only injects noise. The
        # strategy reads these bars to estimate 60-day volatility for its
        # inverse-vol weights, and on a Rs 2.59 share one 0.01 tick is 0.4% of price
        # -- the same order as the daily return being measured. That perturbed the
        # weights, which is why the port and the reference engine sized differently
        # on cheap names even on a 0.01 grid, where execution rounding is identical
        # on both sides. The reference engine reads raw closes for this reason.
        # The quote below KEEPS its tick: that is a price an order fills against.
        o, h, l, c = _px(r.open), _px(r.high), _px(r.low), _px(r.close)
        vol = max(int(r.volume), 1)

        # The tradeable opening quote. Slippage MUST be modelled as a two-sided
        # spread around the open, not as one price: a single adverse level would be
        # adverse for buys but FAVOURABLE for sells. Buys lift the ask, sells hit
        # the bid, so both sides pay, exactly as the reference engine does with
        # open*(1+s) on buys and open*(1-s) on sells.
        if DEPTH_MODE == "unlimited":
            ask = rt(float(r.open) * (1.0 + slippage))
            bid = rt(float(r.open) * (1.0 - slippage))
            # Size deep enough that an order never walks. With a size of 1 share, a
            # 100-share order consumed the level and then filled at progressively
            # worse prices, scattering fills up to 5% from the open. Depth here
            # represents "the open is available in size", which is the same
            # assumption the reference engine makes -- which is why reconciliation
            # requires this mode.
            events.append(QuoteTick(
                inst.id, Price.from_str(bid), Price.from_str(ask),
                Quantity.from_int(QUOTE_DEPTH), Quantity.from_int(QUOTE_DEPTH),
                t_open, t_open))
        else:
            # A REAL L2 BOOK, NOT A SEQUENCE OF QUOTES.
            #     A first attempt emitted three QuoteTicks a nanosecond apart at
            #     progressively worse prices. That does NOT build a book: each quote
            #     REPLACES top-of-book, so the last one emitted -- the worst -- was
            #     the prevailing market when the strategy sent its order at 09:16.
            #     Every order then paid 3x slippage regardless of its size, which is
            #     a flat cost increase wearing a liquidity model's clothes. It
            #     showed up as 998 of 1000 fills "walking", which is what prompted
            #     looking again rather than reporting it.
            #
            #     OrderBookDeltas with BookType.L2_MBP is the native mechanism, and
            #     the venue walks it for us: an order consumes level 1, then level
            #     2, then level 3, and each portion fills at its own price.
            depth = _depth_for(symbol, r.date)
            deltas = [OrderBookDelta(inst.id, BookAction.CLEAR,
                                     BookOrder(OrderSide.BUY, Price.from_str(_px(0.01)),
                                               Quantity.from_int(1), 0),
                                     0, 0, t_open, t_open)]
            for lv in range(1, DEPTH_LEVELS + 1):
                s_lv = slippage * lv
                a = rt(float(r.open) * (1.0 + s_lv))
                b = rt(float(r.open) * (1.0 - s_lv))
                for side, prc in ((OrderSide.BUY, b), (OrderSide.SELL, a)):
                    deltas.append(OrderBookDelta(
                        inst.id, BookAction.ADD,
                        BookOrder(side, Price.from_str(prc),
                                  Quantity.from_int(depth), lv * 10 + int(side)),
                        0, 0, t_open, t_open))
            events.append(OrderBookDeltas(inst.id, deltas))
            # The strategy still needs a price to size against, and it reads that
            # from on_quote_tick. It sees the TOP level only -- which is exactly the
            # real situation: you size against the price on the screen and discover
            # the rest of the book when you trade.
            events.append(QuoteTick(
                inst.id,
                Price.from_str(rt(float(r.open) * (1.0 - slippage))),
                Price.from_str(rt(float(r.open) * (1.0 + slippage))),
                Quantity.from_int(depth), Quantity.from_int(depth),
                t_open, t_open))
        # the daily bar, stamped at the close
        events.append(Bar(
            bt, Price.from_str(o), Price.from_str(h), Price.from_str(l),
            Price.from_str(c), Quantity.from_int(vol), t_close, t_close))
    return inst, events


def load_universe(cache_path, start, end, symbols=None, slippage: float = 0.0):
    """Load the whole universe from the engine's price cache.
    Returns (instruments, events sorted by time)."""
    px, op = load_panel(cache_path)
    syms = sorted(px.columns) if symbols is None else [s for s in sorted(px.columns)
                                                       if s in set(symbols)]
    instruments, events = [], []
    for sym in syms:
        inst, ev = load_symbol_from_panel(sym, px, op, start, end, slippage=slippage)
        if not ev:
            print(f"    [skip] {sym}: no rows in range")
            continue
        instruments.append(inst)
        events.extend(ev)
    events.sort(key=lambda e: e.ts_init)
    return instruments, events


if __name__ == "__main__":
    # Smoke test: 3 stocks, one month. Verifies parsing, tick snapping and ordering.
    cache = Path("results/metrics/v5_expanding_cache.csv")
    px, _ = load_panel(cache)
    syms = sorted(px.columns)[:3]
    print(f"Smoke test on {syms}, Jan 2020\n")
    insts, evs = load_universe(cache, "2020-01-01", "2020-01-31", symbols=syms)

    print(f"  instruments : {len(insts)}  -> {[str(i.id) for i in insts]}")
    print(f"  events      : {len(evs)}")
    bars = [e for e in evs if isinstance(e, Bar)]
    quotes = [e for e in evs if isinstance(e, QuoteTick)]
    print(f"  bars        : {len(bars)}")
    print(f"  quotes      : {len(quotes)}   (must equal bars)")
    # One opening QuoteTick per daily Bar. True in BOTH depth modes: "volume" adds
    # an OrderBookDeltas event per day but still emits exactly one QuoteTick.
    assert len(bars) == len(quotes), "each bar needs exactly one opening quote"

    ordered = all(evs[i].ts_init <= evs[i + 1].ts_init for i in range(len(evs) - 1))
    print(f"  time-ordered: {ordered}")
    assert ordered, "events must be sorted by time"

    print("\n  first six events:")
    for e in evs[:6]:
        ts = pd.Timestamp(e.ts_init, tz="UTC")
        if isinstance(e, QuoteTick):
            print(f"    {ts}  QUOTE {e.instrument_id}  "
                  f"bid={e.bid_price} ask={e.ask_price}")
        else:
            print(f"    {ts}  BAR  {e.bar_type.instrument_id}  "
                  f"O={e.open} H={e.high} L={e.low} C={e.close}")

    d = pd.Timestamp(bars[0].ts_init, tz="UTC")
    print(f"\n  sanity: first bar {bars[0].bar_type.instrument_id} on {d.date()} "
          f"at {d.time()} (should be 15:30), its quote at 09:15")
    print("\n  PASS")
