"""
nautilus_port.py -- the strategy on NautilusTrader, the second execution engine.

Sections, in order:
  1. the Indian fee model the venue charges (QbeastIndianFeeModel, from costs.py)
  2. nt_data      the bars, quotes and book the port reads
  3. nt_strategy  the strategy (PredictiveEngineStrategy)
  4. nt_run       one backtest per (universe, arm, settings)
  5. nt_execute   pipeline STEP 17: run the port for every selected combination
  6. nt_export_scores  pipeline STEP 16: the score parquet the port reads
  7. nt_daily_compare, nt_holdings_compare, depth_compare: diagnostics, by hand

    ./venv/bin/python nautilus_port.py TOOL [ARGS]

Only the two pipeline steps and the checks that compare the port with the engine
import this file; a run that never reaches STEP 16 never imports nautilus_trader.
Reports and data stay under nautilus/.
"""
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import pandas as pd
import model
import settings
from settings import list_dir
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import BookOrder
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import BookAction
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from market_data import read_table
from costs import fill_price
import numpy as np
from costs import Broker
from costs import Exchange
from costs import Product
from costs import Segment
from costs import Side as QSide
from costs import compute_leg_charges
from nautilus_trader.trading.strategy import Strategy
import portfolio as _bsf
from costs import SLIPPAGE
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.objects import Money
from settings import REGISTRY
from settings import capital_axis as _capital_axis
from settings import cadence
import portfolio as arm_reg
import contextlib
import io
import warnings
from backtest_runs import metrics
from settings import certified
from costs import (Broker, Exchange, Product, Segment, Side,
                   compute_leg_charges)


# ======================================================================================
# THE FEE MODEL. From costs.py (moved 2026-11-27).
# ======================================================================================
# ============================================================ NautilusTrader =====
# Thin adapter so QBEAST strategies can plug Indian charges straight into the
# backtest engine via BacktestVenueConfig(fee_model=...).
#
# CAVEATS (read before wiring into M9+ live/backtest paths):
#   1. `get_commission` is invoked PER FILL. The discount-broker "Rs 20 per ORDER"
#      cap is per-order, not per-fill. For single-fill market orders this is exact;
#      for orders that fill in multiple partials it can over-count brokerage. Pin a
#      DECISION-V1-NNN on the chosen handling if you trade large/iceberg orders.
#   2. DP is a per-scrip-per-DAY depository charge, not a per-order one. It is
#      therefore OFF by default in the Nautilus path (include_dp=False) and should
#      be reconciled at EOD by the M9 Data Manager rather than booked per fill.
# --------------------------------------------------------------------------------
try:
    from nautilus_trader.backtest.models import FeeModel  # type: ignore
    from nautilus_trader.model.objects import Money, Currency  # type: ignore
    from nautilus_trader.model.enums import OrderSide  # type: ignore
    _HAS_NAUTILUS = True
except Exception:  # pragma: no cover  (core stays importable without the framework)
    _HAS_NAUTILUS = False
    FeeModel = object  # type: ignore


class QbeastIndianFeeModel(FeeModel):
    """
    NautilusTrader FeeModel returning the all-in Indian charge for each fill.

    Example
    -------
        from nautilus_trader.config import BacktestVenueConfig
        fee_model = QbeastIndianFeeModel(
            broker=Broker.ZERODHA, segment=Segment.EQUITY,
            product=Product.INTRADAY, exchange=Exchange.NSE,
        )
        venue = BacktestVenueConfig(name="NSE", fee_model=fee_model, ...)
    """

    def __init__(
        self,
        broker: Broker,
        segment: Segment,
        product: Product,
        exchange: Exchange,
        *,
        female: bool = False,
        is_agri: bool = False,
        include_dp: bool = False,     # OFF in the per-fill path (see caveat 2)
        include_ipft: bool = False,
        currency: str = "INR",
    ):
        if _HAS_NAUTILUS:
            super().__init__()
        self.broker = broker
        self.segment = segment
        self.product = product
        self.exchange = exchange
        self.female = female
        self.is_agri = is_agri
        self.include_dp = include_dp
        self.include_ipft = include_ipft
        self._ccy = currency

    # Cython-style parameter names per NautilusTrader's FeeModel base signature.
    def get_commission(self, Order_order, Quantity_fill_qty, Price_fill_px, Instrument_instrument):
        side = Side.SELL if Order_order.side == OrderSide.SELL else Side.BUY
        # str() on Price/Quantity yields an exact decimal string -> no float drift.
        price = Decimal(str(Price_fill_px))
        qty = Decimal(str(Quantity_fill_qty))

        bd = compute_leg_charges(
            self.broker, self.segment, self.product, side, price, qty, self.exchange,
            female=self.female, is_agri=self.is_agri,
            include_dp=self.include_dp, include_ipft=self.include_ipft,
        )

        ccy = getattr(Instrument_instrument, "quote_currency", None) or Currency.from_str(self._ccy)
        return Money(float(bd.total), ccy)


# ======================================================================================
# nt_data. From nautilus/nt_data.py (moved 2026-11-27).
# ======================================================================================
# nt_data -- build Nautilus instruments and market data from the project's raw CSVs.
#
# EXECUTION MODEL (established by checks.py verify_next_open_execution):
#     each trading day is fed as separate events, so that the execution price is
#     explicit rather than an artefact of how the exchange decomposes a bar
#     internally:
#
#         09:15  QuoteTick   bid = open * (1 - SLIPPAGE), to the paisa
#                            ask = open * (1 + SLIPPAGE), to the paisa
#                            both sides sized QUOTE_DEPTH  <- orders execute here
#         15:30  Bar         the day's OHLC as the panel holds it, unrounded
#                                                          <- signals come from here
#
#     Under DEPTH_MODE="volume" one further event precedes the quote:
#     OrderBookDeltas carrying DEPTH_LEVELS priced levels, each sized from the
#     symbol's own median volume. See the DEPTH MODE block below. The DEFAULT is
#     "unlimited", which emits exactly the two events above.
#
#     NO TradeTick IS CONSTRUCTED HERE, AND NONE EVER WAS.
#         This docstring read "09:15 TradeTick at the day's OPEN" until 2026-08-23.
#         The code has always built a QuoteTick (see the construction below),
#         because execution needs a TWO-SIDED price: a single traded price makes
#         slippage adverse for buys and favourable for sells. TradeTick is not even
#         imported by this module.
#
#     THE NEXT-OPEN RULE IS NOT ENFORCED BY LATENCY.
#         This docstring previously credited "a LatencyModel on the venue".
#         nautilus_port.py nt_run sets LATENCY_NS = 0, so the latency model delays nothing. The
#         rule is enforced by the STRATEGY: it plans at on_daily_close (15:30) and
#         releases the orders from on_market_open at 09:16 the next trading day.
#         See nautilus_port.on_market_open.
#
# PRICE SOURCE -- this must match the reference engine exactly
#     The reference engine reads its price panel from results/metrics/v5_expanding_cache.csv,
#     NOT from the raw CSVs. Both hold the same prices per symbol, but the PANEL is
#     the union of every symbol's dates and is forward filled, so a different set of
#     dates shifts what "20 rows back" means for every symbol at once.
#
#     That path belongs to a retired universe (deleted 2026-09-11). There are now
#     four universes and the cache is a PARAMETER -- load_panel(cache_path) -- with
#     the per-universe paths held in nautilus_port.UNIVERSES. The rule is unchanged
#     whichever universe is loaded: the port reads the same cache its reference engine reads.
#
#     Reading raw CSVs here produced a 6,574-row panel against the engine's 6,322,
#     and on 2019-01-01 that gave breadth 27/53 where the engine had 17/53 -- exposure
#     51% instead of 32%. The port then ran roughly twice as invested for seven years.
#
#     So the loader reads the same cache the engine reads. Reconciliation between two
#     systems is only meaningful when both are fed identical input.
#
# This module reads from results/ but never writes there. The existing pipeline is
# untouched.

VENUE = Venue("NSE")
OPEN_TIME = pd.Timedelta(hours=9, minutes=15)    # NSE open
CLOSE_TIME = pd.Timedelta(hours=15, minutes=30)  # NSE close
# The bars carry RAW historical prices (see the Bar construction below), and those
# are not all two-decimal: 10.7% of the MidCap150 panel's opens and closes have more
# precision than that, and its cheapest observation is 0.0128. A precision of 2 would
# therefore round the bars, which carry no fill rounding -- and on the same
# sub-Rs-10 names. 1e-6 is 0.008% of the cheapest price in any panel, i.e.
# negligible against a daily return. Quote prices are unaffected in value: a
# paisa-rounded 2.54 expressed at this precision is 2.540000, the identical number.
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
    import market_data
    import settings
    _VOLUME = {}
    raw_dir = Path(raw_dir)
    for f in list_dir(raw_dir, "*.csv"):
        if symbols is not None and f.stem not in symbols:
            continue
        try:
            d = market_data.read_price_csv(f)
        except Exception:
            continue
        if "volume" not in d.columns:
            continue
        s = d[["date", "volume"]].dropna().set_index("date")["volume"].sort_index()
        _VOLUME[f.stem] = s[s > 0]
    return len(_VOLUME)


def _px(x) -> str:
    """Format a price at the instrument's precision, without rounding it."""
    return f"{float(x):.{PRICE_PRECISION}f}"


def make_instrument(symbol: str) -> Equity:
    return Equity(
        instrument_id=InstrumentId(Symbol(symbol), VENUE),
        raw_symbol=Symbol(symbol),
        currency=INR,
        price_precision=PRICE_PRECISION,
        # Fill prices are in whole paise (costs.fill_price).
        price_increment=Price.from_str(_px("0.01")),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def bar_type_for(instrument_id: InstrumentId) -> BarType:
    return BarType.from_str(f"{instrument_id}-1-DAY-LAST-EXTERNAL")


def load_panel(cache_path):
    """The engine's price panel: union date index, forward filled, exactly as
    backtest_runs.py builds it."""
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
    """The rows the port quotes for one symbol.

    ONE DEFINITION FOR THE PORT AND FOR ITS CHECK. load_symbol_from_panel builds
    its opening quotes from these rows; checks.py check_b_exec_timing
    reconstructs the expected fill price from the same rows with
    costs.fill_price.
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
    return df


def load_symbol_from_panel(symbol, px, op, start, end, slippage=0.0):
    """Return (instrument, [data events]) for one stock, taken from the panel."""
    df = quote_frame(symbol, px, op, start, end)
    inst = make_instrument(symbol)
    bt = bar_type_for(inst.id)

    events = []
    for i, r in enumerate(df.itertuples(index=False)):
        # A quote price: the open moved by `rate` against the trade, to the paisa.
        rt = lambda rate, buy: _px(fill_price(r.open, rate, buy))
        day = pd.Timestamp(r.date).tz_localize("UTC")
        t_open = int((day + OPEN_TIME).value)
        t_close = int((day + CLOSE_TIME).value)
        # THE BAR IS SIGNAL INPUT AND IS NOT ROUNDED.
        # These OHLC values used to be snapped to the tick like the quote below, and
        # that was a bug. A historical close is already an actual traded price; a
        # tick governs what price an order may be PLACED at, so applying it a second
        # time to a recorded price models nothing and only injects noise. The
        # strategy reads these bars to estimate 60-day volatility for its
        # inverse-vol weights, and on a Rs 2.59 share one 0.01 tick is 0.4% of price
        # -- the same order as the daily return being measured. That perturbed the
        # weights, which is why the port and the reference engine sized differently
        # on cheap names even on a 0.01 grid, where execution rounding is identical
        # on both sides. The reference engine reads raw closes for this reason.
        # The quote below is rounded to the paisa: that is a price an order fills against.
        o, h, l, c = _px(r.open), _px(r.high), _px(r.low), _px(r.close)
        vol = max(int(r.volume), 1)

        # The tradeable opening quote. Slippage MUST be modelled as a two-sided
        # spread around the open, not as one price: a single adverse level would be
        # adverse for buys but FAVOURABLE for sells. Buys lift the ask, sells hit
        # the bid, so both sides pay, exactly as the reference engine does with
        # open*(1+s) on buys and open*(1-s) on sells.
        if DEPTH_MODE == "unlimited":
            ask = rt(slippage, True)
            bid = rt(slippage, False)
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
                a = rt(s_lv, True)
                b = rt(s_lv, False)
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
                Price.from_str(rt(slippage, False)),
                Price.from_str(rt(slippage, True)),
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


def _cli_nt_data():
    """`python nautilus_port.py nt_data [ARGS]`: what running nautilus/nt_data.py did."""
    global evs
    import model
    import settings
    from settings import certified
    _u = certified()[0]
    cache = model.require_cache(_u.score_cache, what=f"{_u.tag} score panel")
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


# ======================================================================================
# nt_strategy. From nautilus/nt_strategy.py (moved 2026-11-27).
# ======================================================================================
# nt_strategy -- the Predictive Engine execution logic as a Nautilus Strategy.
#
# WHAT THIS FILE DOES AND DOES NOT DO
#     It reproduces the EXECUTION layer only: ranking, buffer, volatility sizing
#     (inverse-vol or pro-vol, and breadth-scaled or fully-invested exposure, both
#     set through configure()),
#     breadth-scaled exposure, and order submission. No model is trained here. The
#     scores arrive precomputed from nautilus_port.py nt_export_scores, which is the only channel
#     between research and execution.
#
# EXECUTION TIMING
#     Each day is fed as a QuoteTick at 09:15 (bid/ask around the open) and a Bar at
#     15:30 (OHLC).
#
#         15:31 on day t   -- a timer fires once every symbol's bar has landed. The
#                             rebalance decision is taken here and the orders are
#                             PLANNED but not sent.
#         09:15 on day t+1 -- each instrument's opening quote arrives. The moment an
#                             instrument's own quote lands, its planned order is sent
#                             and fills against that quote.
#
#     An earlier version submitted at 15:31 and relied on a LatencyModel to delay the
#     fill. That was wrong and it was caught by tracing a single order: the resting
#     order matched the STALE book before the new quote updated it, so it filled at
#     the PREVIOUS day's open. The date looked right while the price was a day old.
#     Measured on SUNPHARMA: fill 433.15, which is open(01-01) 432.50 * 1.0015 -- the
#     wrong day's open, not the 431.15 expected from open(01-02).
#
#     Planning at the close and sending at the next open removes the dependence on
#     latency entirely, and matches the stated rule directly: signal at close of t,
#     execution at the open of t+1.
#
# WARM-UP
#     mom20 needs 21 closes and vol60 needs 61, so data must start before the trading
#     window. The strategy ignores every day before `trading_start` while still
#     consuming its bars to fill the rolling buffers.
#
# FEATURE WINDOWS MUST USE THE UNION DATE INDEX  (a bug that was found and fixed)
#     The reference engine builds a panel whose index is the UNION of every symbol's
#     trading dates, forward-filled. So px.shift(20) means "20 union dates ago", not
#     "20 of this symbol's own bars ago". Those differ whenever a symbol has a gap.
#
#     The first version of this strategy kept a per-symbol deque of closes and looked
#     back 20 entries. On 2019-01-01 that produced breadth 27/53 where the reference
#     produced 17/53 -- exposure 51% instead of 32%, i.e. the portfolio ran roughly
#     twice as invested for seven years and the equity curve was about 8% adrift.
#
#     The fix is to hold a shared list of observed trading dates plus a per-symbol
#     date -> close map with forward fill, and to index the momentum and volatility
#     windows by position in that shared list. This reproduces the panel exactly.
#
# SIZING, AS IN THE REFERENCE ENGINE
#     A buy's quantity is set at the close of t, from the book's value at that close
#     and the name's close with slippage:
#         q = (book_value(t) * exposure * 0.98 * weight) // (close(t) * (1 + slippage))
#     The opening quote of t+1 sets only the fill price and, through free cash, the
#     cash test and the trim. Since 2026-10-28; until then both sides sized at the
#     open of t+1.

# SELECTION -- imported from settings.py, the single definition.
TOP_N, BUFFER = settings.TOP_N, settings.BUFFER
REBAL = 20
VOL_WIN = 60
MOM_WIN = 20
SAFETY = 0.98
TRADING_DAYS = 252

# ---------------------------------------------------------------------------
# SIZING AND EXPOSURE MODE -- mirror portfolio.py's `sizing` and `mode` arguments
# ---------------------------------------------------------------------------
# "invvol" (default)  w = 1/vol   -- low vol gets the large position
# "provol"            w = vol     -- high vol gets the large position
#
# THESE ARE PER-STRATEGY CONFIGURATION, NOT MODULE SWITCHES ANY MORE.
# They used to be module globals set by set_sizing() before a run, mirroring how
# nautilus_port.py nt_data handles DEPTH_MODE. Two things were wrong with that. A global is
# process-wide, so verify_v34_arms had to assert both modules agreed before every
# arm to catch a stale value left by the previous one -- and that assert only ever
# proved the global had been SET, never that the run USED it. Second, there was no
# exposure mode at all: exposure was breadth, always, so mode="none" could not be
# expressed and v1/v3 were not representable. See KNOWN_ISSUES.md.
#
# Both now arrive through configure() and are recorded on the instance AT THE POINT
# OF USE, so a caller can read back what the run actually applied rather than what
# it was asked to apply.
#
#   sizing  "invvol" w = 1/vol  (low vol, large position)  | "provol" w = vol
#   mode    "breadth" exposure = fraction with positive 20d momentum | "none" = 1.0
#
# THE RULES MUST MATCH portfolio.py EXACTLY. Same guard (vol > 0.01), same zero
# weight when it fails, same normalisation, same equal-weight fallback, and the same
# two exposure modes. If these drift, nt_verify stops reconciling and the divergence
# looks like an execution bug.
DEFAULT_SIZING = "invvol"
DEFAULT_MODE = "breadth"


def leg_charges(price, qty, side):
    """Charges for one executed leg, used to keep the strategy's own cash arithmetic
    in step with what the venue will actually deduct.

    This is the SAME calculator the venue's QbeastIndianFeeModel calls, with the same
    include_dp setting, so it is not an estimate or a guessed headroom -- an earlier
    version of this port guessed a 5% cash buffer and it shrank every buy.
    """
    if price <= 0 or qty <= 0:
        return 0.0
    bd = compute_leg_charges(
        Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
        QSide.BUY if side == "BUY" else QSide.SELL,
        Decimal(str(round(price, 2))), Decimal(str(int(qty))), Exchange.NSE,
        include_dp=True)
    return float(bd.total)


class PredictiveEngineStrategy(Strategy):
    """Cross-sectional ranking strategy with breadth-scaled exposure."""

    def __init__(self, config=None):
        super().__init__(config)
        self.scores = None            # DataFrame: date, symbol, score
        self.instruments = []         # list[Instrument]
        self.trading_start = None     # pd.Timestamp; ignore days before this
        self.dates = []               # union of trading dates seen, in order
        self.series = {}              # symbol -> {date -> close}
        self.last_close = {}          # symbol -> latest close (forward filled)
        self.day_index = -1           # counts trading days from trading_start
        self.rebalances = 0
        self.orders_submitted = 0
        self.decisions = []           # audit trail, mirrors daily_decisions_*.csv
        self.skipped = []             # mirrors daily_skipped_*.csv
        self._plan = {}               # symbol -> (side, qty, weight, invest_val)
        self._queue = []              # this morning's orders, released one at a time
        self._dec_val = None          # the book's value at the decision close
        self._dec_px = {}             # symbol -> its close on the decision session
        self._exposure = 0.0          # exposure decided at the close, applied at the open
        self.sizing = DEFAULT_SIZING  # set by configure(); "invvol" | "provol"
        self.mode = DEFAULT_MODE      # set by configure(); "breadth" | "none"
        # What the run ACTUALLY applied, recorded on the branch taken rather than
        # copied from the config. verify_v34_arms reads this back.
        self.applied = {"sizing": None, "mode": None}
        self._open_px = {}            # symbol -> this morning's ask (the BUY fill price)
        self._open_bid = {}           # symbol -> this morning's bid (the SELL fill price)
        self._open_day = {}           # symbol -> the date its latest quote belongs to
        self._quote_day = None        # date of the most recent opening quote seen
        self.daily_equity = []        # one row per trading day, for reconciliation
        self.daily_holdings = []      # one row per (trading day, held symbol)
        self.fills = []               # every fill, for reconciliation
        self.holdings_log = []        # holdings at each rebalance, for reconciliation
        self.dd_stop = None          # set by configure(); the drawdown stop of v5/v6.
                                      # Not `stop`: Strategy.stop() is nautilus's own method.
        self.stop_events = []         # mirrors daily_stop_events_*.csv
        self.dd = None                # set by configure(); the drawdown-limit axis
        self._dd_order = None         # {symbol: signed qty} decided at the last close
        self._dd_pending = None       # that order, taken at the open it fills at
        self._dd_before = {}          # the order's names held when its legs were queued

    # ---------------------------------------------------------------- setup
    def configure(self, scores: pd.DataFrame, instruments, trading_start: str,
                  sizing: str = DEFAULT_SIZING, mode: str = DEFAULT_MODE,
                  rebal: int = None, drawdown_stop=None, dd_overlay=None,
                  start_capital=None):
        """Called before the engine runs. Keeps __init__ free of heavy objects.

        `sizing` and `mode` default to the values every existing caller relied on
        when they were module globals, so a caller that passes neither gets exactly
        the previous behaviour. Both raise on a typo rather than accepting it.
        """
        if sizing not in ("invvol", "provol"):
            raise ValueError(f"sizing must be 'invvol' or 'provol', got {sizing!r}")
        if mode not in ("breadth", "none"):
            raise ValueError(f"mode must be 'breadth' or 'none', got {mode!r}")
        # THE CADENCE, AS AN ARGUMENT, for the reason checks.nt_attribution_run states at
        # length: REBAL stays the module default and is never reassigned, and this
        # side moves in the same change as the reference so the gate compares two
        # systems running the same cadence.
        self.rebal = REBAL if rebal is None else int(rebal)
        if self.rebal < 1:
            raise ValueError(f"rebal must be >= 1, got {rebal!r}")
        self.sizing, self.mode = sizing, mode
        self.scores = scores.copy()
        self.scores["date"] = pd.to_datetime(self.scores["date"])
        self._scores_by_day = {d: g.set_index("symbol")["score"]
                               for d, g in self.scores.groupby("date")}
        self.instruments = list(instruments)
        self.trading_start = pd.Timestamp(trading_start)
        # THE DRAWDOWN STOP, the same state machine the engine runs
        # (portfolio.py). None for the core arms: nothing below runs.
        self.dd_stop = None
        if drawdown_stop is not None:
            from portfolio import StopState
            _days = sorted(d for d in self._scores_by_day if d >= self.trading_start)
            self._stop_days = _days
            self.dd_stop = StopState(drawdown_stop, self.rebal, len(_days))
            self._held_at_exit = {}
        # THE DRAWDOWN-LIMIT AXIS (portfolio.py), the class the
        # engine and nt_attribution also run. None without --dd: nothing below runs.
        self.dd = None
        if dd_overlay is not None:
            if drawdown_stop is not None:
                raise ValueError("the drawdown-limit axis cannot run on a stop arm (v5/v6)")
            if start_capital is None:
                raise ValueError("dd_overlay needs start_capital, the run's first peak")
            from portfolio import OverlayState
            self.dd = OverlayState(dd_overlay, start_capital)

    def on_start(self):
        for inst in self.instruments:
            self.series[inst.id.symbol.value] = {}
            self.subscribe_bars(BarType.from_str(f"{inst.id}-1-DAY-LAST-EXTERNAL"))
            self.subscribe_quote_ticks(inst.id)   # the opening quote is the fill price
        # fire just after every opening quote has landed at 09:15
        self.clock.set_timer(
            name="market_open",
            interval=pd.Timedelta(days=1),
            start_time=self.clock.utc_now().normalize() + pd.Timedelta(hours=9, minutes=16),
            callback=self.on_market_open,
        )
        # fire just after the daily bars land at 15:30
        self.clock.set_timer(
            name="daily_close",
            interval=pd.Timedelta(days=1),
            start_time=self.clock.utc_now().normalize() + pd.Timedelta(hours=15, minutes=31),
            callback=self.on_daily_close,
        )
        self.log.info(f"started with {len(self.instruments)} instruments, "
                      f"trading from {self.trading_start.date()}")

    # ------------------------------------------------------------- data in
    def on_bar(self, bar):
        sym = bar.bar_type.instrument_id.symbol.value
        c = float(bar.close)
        day = pd.Timestamp(bar.ts_init, tz="UTC").tz_localize(None).normalize()
        if not self.dates or self.dates[-1] != day:
            if not self.dates or day > self.dates[-1]:
                self.dates.append(day)
        self.series[sym][day] = c
        self.last_close[sym] = c

    def _close_at(self, sym, idx):
        """Close for `sym` at union-date position `idx`, forward filled -- the
        same value the reference panel would hold at that row."""
        if idx < 0 or idx >= len(self.dates):
            return None
        ser = self.series.get(sym)
        if not ser:
            return None
        for j in range(idx, -1, -1):          # walk back to the last observation
            v = ser.get(self.dates[j])
            if v is not None:
                return v
        return None

    def on_order_filled(self, event):
        self.fills.append({
            "date": pd.Timestamp(event.ts_event, tz="UTC").tz_localize(None).normalize(),
            "action": event.order_side.name,
            "symbol": event.instrument_id.symbol.value,
            "qty": int(event.last_qty),
            "price": float(event.last_px),
            "value": round(int(event.last_qty) * float(event.last_px), 2),
            "tc": float(event.commission.as_double())})
        self._pump()          # this order is settled, so the next one can go out

    def on_order_denied(self, event):
        """A denial still has to advance the queue, or one rejected order would
        strand every order behind it for the rest of the backtest."""
        self.log.warning(f"order denied: {event.instrument_id} {event.reason}")
        self._pump()

    def on_quote_tick(self, tick):
        """Record this morning's open. Nothing is submitted here -- see
        on_market_open for why the plan cannot be flushed one instrument at a time."""
        sym = tick.instrument_id.symbol.value
        bid, ask = float(tick.bid_price), float(tick.ask_price)
        self._open_px[sym] = ask
        self._open_bid[sym] = bid
        day = pd.Timestamp(tick.ts_init, tz="UTC").tz_localize(None).normalize()
        self._open_day[sym] = day
        self._quote_day = day

    # ------------------------------------------------- 09:16 order release
    def on_market_open(self, event):
        """Release the planned orders: every SELL first, then the BUYs.

        SELLS MUST GO FIRST, AND THIS WAS A BUG THAT KILLED THE RUN
            The earlier version submitted each planned order from on_quote_tick, so
            the sequence was the order the quotes happened to arrive in, which is
            alphabetical by instrument. On 2019-10-29 that meant BUY ASIANPAINT,
            BAJFINANCE, BHARTIARTL and BPCL drained free cash from 208,612.23 to
            4,760.83 before a single SELL was sent. The venue runs with
            allow_cash_borrowing=False, so the risk engine then DENIED the sells:
                CUM_NOTIONAL_EXCEEDS_FREE_BALANCE: free=4760.83, cum_notional=79243.45
            Denied sells mean the positions were never released, so the cash never
            came back, so every order from that day to the end of the backtest was
            denied too: 1,333 orders submitted, 103 filled, the last one in October
            2019. The reference engine sells first and funds the buys with the
            proceeds, which is what this release order now does.

        WHY 09:16 AND NOT ON THE QUOTE ITSELF
            A market order fills against the instrument's CURRENT book. Sending a
            SELL before that instrument's own 09:15 quote has landed would match the
            STALE book, i.e. the previous day's open -- the exact bug the plan/submit
            split was introduced to remove. By 09:16 every instrument's opening quote
            has arrived, so ordering the sells ahead of the buys costs nothing in
            price: both still fill at today's open.
        """
        now = pd.Timestamp(self.clock.timestamp_ns(), tz="UTC").tz_localize(None).normalize()
        if not self._plan and not self._dd_order:
            return
        # No quotes today means this is not a trading day. Flushing here would fill
        # against the previous session's book, so the plan waits for the next open.
        if self._quote_day != now:
            return

        plan, self._plan = self._plan, {}
        # Sells go first (alphabetically -- they do not compete for cash, so the
        # order among them cannot change an outcome).
        #
        # BUYS GO IN RANK ORDER, HIGHEST SCORE FIRST, AND THAT IS NOT COSMETIC.
        # When cash runs short the trailing buys are skipped, so the sequence decides
        # WHICH name gets dropped. The reference engine iterates `top`, which is
        # score-descending (checks.py nt_attribution,158), so it funds its best ideas
        # first. Sorting alphabetically here made the port buy JSWSTEEL 413 on
        # 2020-08-17 and skip NESTLEIND, where the reference bought NESTLEIND 222 and
        # never held JSWSTEEL -- a different set of holdings out of pure iteration
        # order.
        self._queue = (
            [(sy, OrderSide.SELL, plan[sy][1], 0.0)
             for sy in sorted(sy for sy, p in plan.items() if p[0] == OrderSide.SELL)]
            + [(sy, OrderSide.BUY, 0, plan[sy][2])
               for sy in sorted((sy for sy, p in plan.items() if p[0] == OrderSide.BUY),
                                key=lambda sy: plan[sy][3])])
        # THE DRAWDOWN-LIMIT LEGS GO LAST, after the arm's own buys, as in the
        # engine. Two markers: the first expands into the trims of the names still
        # held when it is reached; the second, reached once those have settled,
        # sizes the top-ups from free cash.
        if self._dd_order:
            self._dd_pending, self._dd_order = self._dd_order, None
            self._queue += [("__DD_SELL__", None, 0, 0.0), ("__DD_BUY__", None, 0, 0.0)]
        self._pump()

    def _pump(self):
        """Submit exactly ONE queued order, then return. The next one goes out when
        this one reports back.

        ONE AT A TIME IS NOT A STYLE CHOICE -- BATCHING BREAKS TWO SEPARATE THINGS
            Every submit_order issued inside a single callback is QUEUED and only
            matched once that callback returns. So a batch loses both of the things
            the cash arithmetic depends on:

            1. The risk engine checks each order against the account as it stands at
               submit time, which for a batch is the PRE-SELL balance for all of
               them. On 2020-09-14 that denied five buys with
               CUM_NOTIONAL_EXCEEDS_FREE_BALANCE: free=108051.34, cum_notional=177919.35
               even though the sell proceeds landing moments later covered them.
            2. self.portfolio reports that same stale state, so every buy in the
               batch is sized off it. On 2020-08-17 all six buys were sized against
               one pre-sell valuation and the fills drove the account to
               -77,885.60 INR, which stopped the backtest outright.

            Draining the queue on fills fixes both at once: by the time a buy is
            submitted, the sells above it have settled in the account, so the risk
            check and the valuation both see real cash. Fills are instantaneous here
            (no latency model), so the whole queue still executes at 09:16 against
            this morning's opens.
        """
        while self._queue:
            sy, side, qty, weight = self._queue.pop(0)
            if sy == "__DD_SELL__":
                self._queue[0:0] = self._dd_sell_legs()
                continue
            if sy == "__DD_BUY__":
                self._queue[0:0] = self._dd_buy_legs()
                continue
            inst = self._inst(sy)
            if inst is None:
                continue
            # A symbol that did not quote this morning has no book to match against.
            # Submitting anyway left the order resting with the queue stalled behind
            # it. The reference engine skips a symbol whose open is NaN, so this does
            # the same rather than trading it at some other day's price.
            if self._open_day.get(sy) != self._quote_day:
                continue

            if side == OrderSide.SELL:
                if qty < 1:
                    continue
                self._send(inst, OrderSide.SELL, qty)
                return

            # A drawdown-limit top-up carries its own quantity (weight None).
            if weight is None:
                px = self._open_px.get(sy)
                if qty < 1 or not px or px <= 0:
                    continue
                if self._free_cash() < qty * px + leg_charges(px, qty, "BUY"):
                    continue
                self._send(inst, OrderSide.BUY, qty)
                return

            px = self._open_px.get(sy)
            cp = self._dec_px.get(sy)
            if not px or px <= 0 or not cp or cp <= 0:
                continue
            # THE QUANTITY COMES FROM THE DECISION CLOSE, as in the reference engine:
            # the book's value and this name's close there, with slippage. This
            # morning's quote sets only the fill price and, through free cash, the
            # trim below.
            #
            # NO PARTICIPATION CAP IS APPLIED HERE, AND THAT IS THE CURRENT STATE
            # OF THIS PORT, not a plan. The reference engine caps a buy at
            # costs.participation_cap() x the symbol's prior-20-session median
            # volume (portfolio.py, _participation_limit). This line has
            # no equivalent: `participation_cap`, `vol20` and `median_volume` appear
            # nowhere in nautilus/, and the strategy is handed scores, not
            # quantities, so no capped size reaches it by another route either.
            #
            # THE CONSEQUENCE IS A LABEL THAT OVERSTATES WHAT RAN. nautilus_port.py nt_run
            # puts the selected profile in the report directory's name, so
            # `--profile tradeable` writes nautilus/reports/<universe>/<arm>@tradeable/
            # -- and every quantity in it came from this uncapped line. A
            # tradeable-labelled report from this file is a research-strategy
            # report. The two such directories on disk, midcap150 v1@tradeable and
            # v2@tradeable written 2026-09-17, each carry a note saying so.
            invest_val = self._dec_val * self._exposure * SAFETY
            if self.dd is not None:
                invest_val *= self.dd.entry_factor(self._exposure)
            q = int((invest_val * weight) // (cp * (1 + SLIPPAGE)))
            if q < 1:
                continue
            # A buy cash cannot fully pay for is cut to the largest whole quantity
            # that fits, or refused, by the reference engine's rule
            # (portfolio.py, the same trim function). leg_charges is the same
            # calculator the venue will deduct with, so this is not a guessed
            # headroom; an earlier version of this port guessed 5% and it shrank
            # every buy.
            free = self._free_cash()
            if free < q * px + leg_charges(px, q, "BUY"):
                if settings.shortfall_axis.selected() != "trim":
                    continue
                q, _, _, _ = _bsf.trim(q, free, lambda n: px,
                                       lambda p_, n: leg_charges(p_, n, "BUY"))
                if q < 1:
                    continue
            self._send(inst, OrderSide.BUY, q)
            return

    def _free_cash(self):
        return float(self.portfolio.account(self.instruments[0].id.venue)
                     .balance_free(self.instruments[0].quote_currency).as_double())

    def _send(self, inst, side, qty):
        # SELLS ARE REDUCE-ONLY, and that flag is load-bearing rather than cosmetic.
        # The venue carries base_currency=INR, so RiskEngine._check_order takes the
        # `account.base_currency is not None` branch and compares a SELL's notional
        # against free CASH -- which denies a sale of shares already owned whenever
        # the account is fully invested. On 2021-03-05 that denied the CIPLA sell
        # with free=171,275.57 against cum_notional=209,378.00. The same function
        # exempts reduce-only orders from that check (risk/engine.pyx:825), which is
        # the intended escape hatch: these sells do close an existing long.
        self.submit_order(self.order_factory.market(
            inst.id, side, Quantity.from_int(int(qty)),
            reduce_only=(side == OrderSide.SELL)))
        self.orders_submitted += 1

    # ------------------------------------------------- end-of-day decision
    def _record_equity(self, day) -> bool:
        """Append one equity row for `day`, valued at that day's closes.

        IDEMPOTENT BY DESIGN. It is called from two places -- the 15:31 daily-close
        timer and on_stop -- and on_stop must be able to run unconditionally without
        risking a duplicate final row if the timer did fire. Returns True if a row
        was actually written."""
        if self.daily_equity and self.daily_equity[-1]["date"] == day:
            return False
        cash = float(self.portfolio.account(self.instruments[0].id.venue)
                     .balance_free(self.instruments[0].quote_currency).as_double())
        mtm = 0.0
        for inst in self.instruments:
            q = self.portfolio.net_position(inst.id)
            sy = inst.id.symbol.value
            if q and float(q) > 0 and sy in self.last_close:
                mtm += float(q) * self.last_close[sy]
        self.daily_equity.append({"date": day, "cash": round(cash, 2),
                                  "mtm": round(mtm, 2),
                                  "equity": round(cash + mtm, 2)})
        return True

    def _record_daily_holdings(self, day):
        """Append one row per HELD symbol for `day`, valued at that day's closes.

        THE GROUND TRUTH, NOT A RECONSTRUCTION. Daily holdings could be replayed
        from fills.csv, and that replay would be a second implementation of the
        thing it is meant to check -- the same trap this project hit when a
        reference engine was compared against a reimplementation of itself. This
        reads the EXECUTION ENGINE'S OWN position book, which is what actually
        settled.

        PURELY ADDITIVE, AND THAT IS DELIBERATE. It appends to a list and touches
        no decision, no order and no quantity. It is called from the same
        idempotent daily hook that already writes daily_equity, AFTER that row is
        written, so it cannot change what the 92-of-92 gate compares. Proven, not
        argued: the gate was re-run immediately after this went in.

        Shape mirrors the reference engine's daily_holdings_<tag>.csv -- one row
        per (date, symbol) with qty, price and value -- so the two can be diffed
        directly rather than through a shim.
        """
        for inst in self.instruments:
            q = self.portfolio.net_position(inst.id)
            sy = inst.id.symbol.value
            if q and float(q) > 0 and sy in self.last_close:
                px = self.last_close[sy]
                self.daily_holdings.append({"date": day, "symbol": sy,
                                            "qty": int(float(q)),
                                            "price": round(px, 2),
                                            "value": round(float(q) * px, 2)})

    def on_daily_close(self, event):
        now = pd.Timestamp(self.clock.timestamp_ns(), tz="UTC").tz_localize(None).normalize()
        if now < self.trading_start:
            return
        if not self.last_close:                      # no bars seen yet today
            return
        day = now.normalize()
        if day not in self._scores_by_day:           # not a trading day
            return

        # record equity every trading day so the curve can be compared day by day
        self._record_equity(day)
        # AND THE HOLDINGS, gated on the equity row having been written so the two
        # can never disagree about which days exist. Both are pure appends.
        self._record_daily_holdings(day)

        self.day_index += 1
        if self.dd_stop is None:
            if self.day_index % self.rebal == 0:
                self.rebalance(day)
            if self.dd is not None:
                self._dd_close(day, last=False)
            return
        self._stop_day(day, last=False)

    def _stop_day(self, day, last):
        """One trading day's close for a stop arm, in the engine's sequence."""
        st, i = self.dd_stop, self.day_index
        st.begin_day()
        if st.exit_pending or st.reentry_pending:
            st.after_fills(i, self._held(), self._held_at_exit,
                           lambda k: self._stop_days[k].date())
        placed = False
        if not last and i % self.rebal == 0:
            if st.state == "IN":
                placed = bool(self.rebalance(day))
            elif st.grid_allows_order(i, self._stop_breadth):
                placed = bool(self.rebalance(day))
                st.after_reentry_order(placed)
        equity = self.daily_equity[-1]["equity"]
        held_now = self._held()
        act = st.at_close(i, day, equity, placed, bool(held_now), last)
        if act == "exit":
            if placed and self.decisions:
                self.decisions[-1]["superseded"] = "drawdown exit"
            self._plan_exit()
        self.stop_events.extend(st.rows(day, equity))

    def _stop_breadth(self):
        """The stop's re-entry breadth, EXACTLY AS THE ENGINE'S v2 COMPUTES IT.

        experiments/DRAWDOWN_STOP_PREREG.txt registers breadth as v2 computes it in
        the engine: (mom20.loc[dt].dropna() > 0).mean() on a forward-filled panel, so
        a name with no bar today still counts at its last close. _momentum() above
        drops such a name, which is this port's own breadth for v2 and v4 and is left
        as it is. 1.0 when no name has momentum, as in the engine.
        """
        i_now = len(self.dates) - 1
        n = pos = 0
        for sym in self.series:
            a = self._close_at(sym, i_now)
            b = self._close_at(sym, i_now - MOM_WIN)
            if a is None or b is None or b <= 0:
                continue
            n += 1
            pos += (a / b - 1.0) > 0
        return pos / n if n else 1.0

    # ---------------------------------------------------------- rebalance
    def _momentum(self):
        """{symbol: 20-day momentum} over the stocks with enough history today."""
        # Momentum is measured across union dates, exactly as px.shift(20) does.
        i_now = len(self.dates) - 1
        mom = {}
        for sym in self.series:
            a = self._close_at(sym, i_now)
            b = self._close_at(sym, i_now - MOM_WIN)
            # a symbol only counts once it has a real observation on this date
            if a is None or b is None or b <= 0:
                continue
            if self.series[sym].get(self.dates[i_now]) is None:
                continue
            mom[sym] = a / b - 1.0
        return mom

    def _held(self):
        held = {}
        for inst in self.instruments:
            q = self.portfolio.net_position(inst.id)
            if q and float(q) > 0:
                held[inst.id.symbol.value] = int(float(q))
        return held

    def _plan_exit(self):
        """An order to sell every holding at the next open, and nothing else."""
        held = self._held()
        self._held_at_exit = held
        self._plan.clear()
        self._queue.clear()
        for sy, q in held.items():
            if self._inst(sy) is not None:
                self._plan[sy] = (OrderSide.SELL, q, 0.0, 0.0)
        self._exposure = 0.0

    def rebalance(self, day):
        """Plan the next open's orders. -> True when an order was planned."""
        # --- breadth over the stocks that actually have enough history ---
        i_now = len(self.dates) - 1
        mom = self._momentum()
        if not mom:
            return False
        n_pos = sum(1 for v in mom.values() if v > 0)
        breadth = n_pos / len(mom)
        # THE `if not mom: return` GUARD ABOVE IS DELIBERATELY UNCHANGED. Under
        # mode="none" test_exposure never consults momentum at all, so on a
        # rebalance date where no symbol has momentum data it would trade while this
        # returns early. With WARMUP_DAYS=200 that case is not expected to arise;
        # it is documented rather than silently altered, because changing the guard
        # would change WHEN rebalances happen, which is a larger change than adding
        # the exposure mode. See KNOWN_ISSUES.md.
        exposure = 1.0 if self.mode == "none" else max(0.0, min(1.0, breadth))
        self.applied["mode"] = self.mode

        # --- ranking, restricted to names we have a price for today ---
        s = self._scores_by_day[day]
        s = s[[k for k in s.index if k in self.last_close]]
        if len(s) < TOP_N:
            return False
        ranked = s.sort_values(ascending=False)
        top = list(ranked.index[:TOP_N])
        keep = set(ranked.index[:BUFFER])

        # --- current portfolio ---
        held = {}
        for inst in self.instruments:
            q = self.portfolio.net_position(inst.id)
            if q and float(q) > 0:
                held[inst.id.symbol.value] = int(float(q))

        cash = float(self.portfolio.account(self.instruments[0].id.venue)
                     .balance_free(self.instruments[0].quote_currency).as_double())
        holdings_value = sum(q * self.last_close[sy] for sy, q in held.items()
                             if sy in self.last_close)
        port_val = cash + holdings_value
        invest_val = port_val * exposure * SAFETY
        # The book and the closes the next open's buys are sized from.
        self._dec_val = port_val
        self._dec_px = {sy: self.last_close[sy] for sy in top if sy in self.last_close}

        # --- volatility weights over the top-N, direction set by self.sizing ---
        w = {}
        for sy in top:
            arr = [self._close_at(sy, k) for k in range(i_now - VOL_WIN, i_now + 1)]
            if any(v is None or v <= 0 for v in arr):
                w[sy] = 0.0
                continue
            arr = np.asarray(arr, dtype=float)
            rets = arr[1:] / arr[:-1] - 1.0
            vol = float(np.std(rets, ddof=1) * np.sqrt(TRADING_DAYS))
            if vol <= 0.01:
                w[sy] = 0.0
            elif self.sizing == "provol":
                w[sy] = vol
            else:
                w[sy] = 1.0 / vol
        self.applied["sizing"] = self.sizing
        tot = sum(w.values())
        w = ({k: v / tot for k, v in w.items()} if tot > 0
             else {k: 1.0 / len(top) for k in top})

        # --- sells: anything held that dropped out of the buffer ---
        self._plan.clear()            # nothing may survive into a new rebalance
        self._queue.clear()
        n_sell = n_buy = 0
        for sy, q in held.items():
            if sy in keep:
                continue
            inst = self._inst(sy)
            if inst is None:
                continue
            self._plan[sy] = (OrderSide.SELL, q, 0.0, 0.0)
            n_sell += 1

        # --- buys: targets not already held ---
        # No cash arithmetic is done here. The venue runs with
        # allow_cash_borrowing=False, so an order that would overdraw the account is
        # DENIED by Nautilus rather than silently overdrawing or aborting the run.
        # An earlier version guessed a 5% headroom instead, which shrank every buy
        # and pushed the port away from the reference engine.
        for rank, sy in enumerate(top):        # `top` is score-descending
            if sy in held:
                continue
            inst = self._inst(sy)
            if inst is None or sy not in self.last_close:
                continue
            # The quantity is computed at the morning release from this close's
            # book and price (_dec_val, _dec_px), after the drawdown limit's
            # decision at this close, which sets the entry factor. The rank is
            # carried through so the morning release can fund the highest-scoring
            # names first -- see on_market_open.
            self._plan[sy] = (OrderSide.BUY, 0, w[sy], rank)
            n_buy += 1

        self._exposure = exposure
        self.rebalances += 1
        for sy, q in sorted(held.items()):
            self.holdings_log.append({"date": day, "symbol": sy, "qty": int(q)})
        self.decisions.append({
            "decided_on": day, "breadth_pos": n_pos, "breadth_total": len(mom),
            "breadth": round(breadth, 4), "exposure": round(exposure, 4),
            "port_value": round(port_val, 2), "cash_before": round(cash, 2),
            "invest_value": round(invest_val, 2), "n_held_before": len(held),
            "n_buy": n_buy, "n_sell": n_sell})
        return True

    # ------------------------------------------------- drawdown-limit axis
    def _equity_now(self):
        """(cash, mtm) at this close, unrounded: _record_equity's arithmetic."""
        cash = self._free_cash()
        mtm = 0.0
        for inst in self.instruments:
            q = self.portfolio.net_position(inst.id)
            sy = inst.id.symbol.value
            if q and float(q) > 0 and sy in self.last_close:
                mtm += float(q) * self.last_close[sy]
        return cash, mtm

    def _dd_close(self, day, last):
        """The overlay's decision at this close, after the arm's own rebalance."""
        cash, mtm = self._equity_now()
        self._dd_order = self.dd.at_close(day, cash + mtm, mtm, self._held(), last,
                                          self._exposure if self.rebalances else 1.0)

    def _dd_sell_legs(self):
        """The trims of the standing order, for the names still held."""
        held = self._held()
        order = self._dd_pending or {}
        self._dd_before = {s: held[s] for s in order if s in held}
        return [(s, OrderSide.SELL, min(-order[s], self._dd_before[s]), 0.0)
                for s in sorted(self._dd_before) if order[s] < 0]

    def _dd_buy_legs(self):
        """The top-ups, scaled together to free cash with the engine's haircut."""
        held = self._held()
        order = self._dd_pending or {}
        self._dd_pending = None
        buys = [(s, order[s]) for s in sorted(self._dd_before)
                if order[s] > 0 and s in held]
        need = sum(dq * self._open_px[s] for s, dq in buys
                   if self._open_day.get(s) == self._quote_day and self._open_px.get(s))
        f = min(1.0, self._free_cash() * SAFETY / need) if need > 0 else 1.0
        return [(s, OrderSide.BUY, int(dq * f), None) for s, dq in buys]

    # ------------------------------------------------------------ helpers
    def _inst(self, symbol):
        for inst in self.instruments:
            if inst.id.symbol.value == symbol:
                return inst
        return None

    def on_stop(self):
        # THE FINAL TRADING DAY USED TO BE MISSING FROM daily_equity.
        #     on_daily_close is driven by a timer set for 15:31, and the daily bar is
        #     stamped 15:30 (nautilus_port.py nt_data CLOSE_TIME). The backtest clock stops at the
        #     last data event, so on the final day it reaches the 09:16 market-open
        #     timer -- which executed that day's rebalance -- and then stops before
        #     15:31 is ever reached. The fills happened; the equity row did not.
        #
        #     Measured cost: the port's series held 1,841 rows against the reference's
        #     1,842 on a retired universe, and the missing 2026-06-08 carried TEN
        #     fills that moved Rs 1.1m out of positions into cash. Equity read
        #     3,236,727.28 (05 June) where the true final figure is 3,214,422.58
        #     (08 June). On midcap150 the missing day carried twelve fills and Rs 106,221 of difference. Every statistic
        #     taken from the series -- CAGR, Sharpe, MaxDD -- silently omitted it.
        #
        # RECORDED HERE RATHER THAN BY MOVING THE TIMER TO 15:30.
        #     Moving it would make the equity snapshot coincide with bar arrival on
        #     EVERY one of the 1,842 days, so the recorded value would depend on
        #     whether the timer or the last bar is delivered first -- an ordering
        #     dependency introduced across the whole history to fix one day. on_stop
        #     touches only the case that is actually missing and leaves the other
        #     1,841 days byte-identical. _record_equity is idempotent, so if the timer
        #     does fire on the last day this is a no-op.
        now = pd.Timestamp(self.clock.timestamp_ns(), tz="UTC").tz_localize(None).normalize()
        if (self.last_close and now >= self.trading_start
                and now in self._scores_by_day and self._record_equity(now)):
            # _record_equity returned True, so this day was NOT already recorded
            # and the holdings row cannot duplicate either.
            self._record_daily_holdings(now)
            self.log.info(f"final trading day {now.date()} recorded on stop "
                          f"(the 15:31 timer cannot fire after the 15:30 close bar)")
            # THE STOP'S LAST DAY: book this morning's exit or re-entry fills; a
            # trigger at this close sells nothing, exactly as the engine.
            if self.dd_stop is not None:
                self.day_index += 1
                self._stop_day(now, last=True)
            elif self.dd is not None:
                self._dd_close(now, last=True)
        self.log.info(f"rebalances={self.rebalances} orders={self.orders_submitted}")


# ======================================================================================
# nt_run. From nautilus/nt_run.py (moved 2026-11-27).
# ======================================================================================
# nt_run -- assemble and run the Nautilus backtest of the Predictive Engine.
#
# Usage:
#     python3 nautilus_port.py nt_run                 # short smoke window
#     python3 nautilus_port.py nt_run --full          # the full 2019-2026 backtest

# The same panel the reference engine uses. Feeding raw CSVs instead produced a
# different union date index and therefore different momentum windows.
#
# One entry per universe: price panel, score parquet, metrics folder holding the
# reference engine's audit CSVs, and the last backtest year. Adding the MidCap150
# universe is a registry entry, not a new code path -- the strategy, the venue and
# the verification are shared, so whatever is proven on one is proven the same way
# on the others.
# PATHS COME FROM settings.py -- the single definition, shared with the
# research side. This registry was the most complete of the nineteen: it is the
# only one that knew all FOUR universes, and its per-universe backtest END DATE
# lived nowhere else in the repository. That end date is now u.nautilus_end, so
# the port and the research scripts read one definition.
#
# EVERY REGISTERED UNIVERSE ENDS AT settings.BT_END_DATE. The constituents stop
# before the index does, so the panel and therefore the backtest stop there too.
# The end date is still a per-universe field because two retired universes
# (deleted 2026-09-11) carried frozen end dates of their own; a universe that
# needs a different end sets it in its registry entry, not here.
UNIVERSES = {
    u.tag: {"cache": u.score_cache,
            "scores": u.nautilus_scores,
            "metrics": u.metrics_dir,
            "tag": u.tag,
            "end": u.nautilus_end}
    for u in REGISTRY.values()
}
# THE DEFAULT UNIVERSE IS THE FIRST REGISTERED ONE, not a literal tag. It was
# a retired universe's tag, which raised KeyError at IMPORT the moment that
# universe was deleted --
# taking nt_verify, nt_daily_compare, nt_holdings_compare and depth_compare with
# it, none of which mention a universe themselves.
_DEFAULT_UNIVERSE = next(iter(UNIVERSES))
PRICE_CACHE = UNIVERSES[_DEFAULT_UNIVERSE]["cache"]
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
WARMUP_DAYS = 200          # calendar days of history before trading begins
# No latency. The strategy now plans at the close and sends at the next open, so
# nothing depends on delaying a resting order.
LATENCY_NS = 0
# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.

# Real Zerodha delivery-equity charges: brokerage, STT, stamp duty, exchange,
# SEBI turnover fee and GST. Same calculator the reference engine uses, so the
# two systems are charged identically rather than approximately.
# include_dp defaults to False in the per-fill path, because the DP charge is
# levied per scrip per DAY and charging it on every fill could double count. Here
# each scrip trades at most once per rebalance, so per-fill equals per-scrip-per-day
# and it must be on -- otherwise every SELL is undercharged by about Rs 15.34
# against the reference engine, which calls compute_leg_charges with DP included.
FEE_MODEL = QbeastIndianFeeModel(
    broker=Broker.ZERODHA, segment=Segment.EQUITY,
    product=Product.DELIVERY, exchange=Exchange.NSE,
    include_dp=True,
)


def reports_segment(mode, sizing, rebal=None, drawdown_stop=None):
    """The leaf directory identifying one (arm, cadence, profile) combination.

    A NAMED FUNCTION SO IT CAN BE MEASURED. This was eleven lines inline inside
    run(), which is why naming_declare_check could not verify it: the check asks
    which axes a composer carries by varying one axis at a time and watching the
    output, and it cannot call code buried in the middle of a function that boots
    a backtest engine. Inline composition is exactly how the profile went missing
    here for as long as it did -- nothing could interrogate it.

    Registered in settings.CARRIES as carrying all three axes, measured, not assumed.
    """
    # THE CADENCE JOINS THE PATH, on the same rule the research side uses: the
    # default is unsuffixed so nautilus/reports/midcap150/v1/ keeps meaning what it has
    # always meant, and a non-default cadence gets v1@r40 of its own rather than
    # overwriting it.
    # AND THE PROFILE JOINS IT TOO -- SITE 12, fixed 2026-09-12. This path carried
    # the universe, then the arm, then the cadence, each added after the axis
    # before it had already collided. The profile was the one axis left, and it
    # had ALREADY fired: `tradeable` caps fills at the symbol's prior-20-session
    # median volume, so a tradeable run produces different orders, different fills
    # and different positions -- and wrote all of them over the research run's
    # reports, in place, under a directory name that still said `mid/v2`. Two
    # tradeable v34 runs are on record, so this destroyed reports rather than
    # risking it.
    #
    # SAME DEFAULT-IS-UNSUFFIXED RULE as every other axis: research is the default
    # and stays unsuffixed, so nautilus/reports/midcap150/v2/ keeps meaning exactly what
    # it has always meant and no existing path moves.
    from portfolio import path_segment
    import settings
    # THE CADENCE, PROFILE AND TAX TAIL COMES FROM settings.path_tail, the one rule
    # settings.run_dir uses too. The history of each axis joining this path is in
    # the git log of this function; NOTHING DOWNSTREAM OF IT READS THE PROFILE
    # (nt_strategy sizes with no participation cap), so `@tradeable` records
    # which profile the run SELECTED, not which one it APPLIED.
    # A STOP ARM GETS ITS OWN LEAF. v5 has v1's mode and sizing, so without the
    # stop in the segment its reports would overwrite v1's.
    return path_segment(mode, sizing, drawdown_stop) + settings.path_tail(rebal)


# WHERE A RUN'S REPORTS GO. ONLY THE PIPELINE WRITES nautilus/reports/.
# Until 2026-09-24 every caller of run() wrote there, so nt_verify, verify_v34_arms,
# depth_compare and the attribution tools overwrote the pipeline's own fills --
# at a 0.01 tick grid where the pipeline then used the NSE grid -- and
# check_b_exec_timing certified whichever program had run last. nt_execute (STEP
# 17) passes PIPELINE_REPORTS; every other caller gets TOOL_REPORTS by default.
PIPELINE_REPORTS = Path(__file__).resolve().parent / "nautilus" / "reports"
TOOL_REPORTS = Path(__file__).resolve().parent / "nautilus" / "tool_reports"


# naming: arm,cadence,profile via reports_segment -- every report this step
# writes lands in `out`, which carries the universe as a directory and the
# arm, cadence and profile as its leaf segment (reports_segment above). The
# axes are in the PATH here, not in the filenames, which is why the
# filenames beneath it are bare literals.
def run(trading_start, trading_end, symbols=None, quiet=True,
        universe=None,
        sizing="invvol", mode="breadth", rebal=None, reports_root=None,
        drawdown_stop=None, dd_overlay=None):
    # THE REPORT DIRECTORY TAKES THE dd SEGMENT FROM THE SELECTION (settings.path_tail),
    # so an overlay passed without the selection, or the selection without the
    # overlay, would write a report under the wrong name. Refused.
    from settings import dd_axis as _dda
    if (dd_overlay is None) != _dda.is_default() or (
            dd_overlay is not None and dd_overlay != _dda.selected()):
        raise ValueError(f"nt_run.run: dd_overlay={dd_overlay!r} does not match the "
                         f"dd selection {_dda.selected()!r}")
    warm_start = (pd.Timestamp(trading_start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    print(f"data from {warm_start} (warm-up) | trading {trading_start} to {trading_end}")

    U = UNIVERSES[universe if universe is not None else _DEFAULT_UNIVERSE]
    instruments, events = load_universe(U["cache"], warm_start, trading_end,
                                        symbols=symbols, slippage=SLIPPAGE)
    print(f"  instruments {len(instruments)} | events {len(events):,}")

    scores = pd.read_parquet(Path(__file__).resolve().parent / "nautilus" / "data" / U["scores"])
    if symbols is not None:
        scores = scores[scores["symbol"].isin(set(symbols))]
    scores = scores[(scores["date"] >= trading_start) & (scores["date"] <= trading_end)]
    print(f"  score rows  {len(scores):,} over {scores['date'].nunique()} days")

    eng = BacktestEngine(config=BacktestEngineConfig(
        trader_id="PREDENG-001",
        logging=LoggingConfig(bypass_logging=quiet)))
    eng.add_venue(VENUE, OmsType.NETTING, AccountType.CASH,
                  starting_balances=[Money(_capital_axis.selected(), INR)],
                  base_currency=INR,
                  latency_model=LatencyModel(base_latency_nanos=LATENCY_NS),
                  # Orders execute against the 09:15 QUOTE and nothing else. With the
                  # default bar_execution=True an order that found no quote to match
                  # rested until the 15:30 bar and filled at that day's CLOSE: on
                  # 2021-03-05 the LTF sell was sent at 09:16 and filled at 15:30.
                  bar_execution=False,
                  # A GENUINE L2 BOOK ONLY WHEN THE DEPTH MODEL ASKS FOR ONE.
                  #   In "unlimited" mode the venue keeps its default L1 book and
                  #   the run is byte-for-byte what it was, which is what lets
                  #   nt_verify keep reconciling. In "volume" mode nt_data emits
                  #   OrderBookDeltas and the venue needs L2_MBP to hold them, so
                  #   a large order walks the levels natively instead of filling
                  #   the whole size at top of book.
                  book_type=(BookType.L2_MBP
                             if DEPTH_MODE == "volume" else BookType.L1_MBP),
                  fee_model=FEE_MODEL)
    for inst in instruments:
        eng.add_instrument(inst)
    eng.add_data(events)

    strat = PredictiveEngineStrategy()
    # sizing/mode default to what every caller relied on when these were module
    # globals, so an existing call site behaves exactly as before.
    strat.configure(scores, instruments, trading_start, sizing=sizing, mode=mode,
                    rebal=rebal, drawdown_stop=drawdown_stop, dd_overlay=dd_overlay,
                    start_capital=_capital_axis.selected())
    eng.add_strategy(strat)

    eng.run()

    # Nautilus's own reports -- these carry the real order status (FILLED, DENIED,
    # CANCELED) rather than anything reconstructed by hand.
    # ONE DIRECTORY PER UNIVERSE. This used to be a single shared `reports/`, so a
    # verification loop over three universes left only the LAST one on disk and
    # silently overwrote the other two -- the files looked current while describing
    # a run nobody asked about. The universe is part of the path now, so all three
    # persist side by side and a directory cannot be mistaken for another's output.
    #
    # AND ONE DIRECTORY PER ARM UNDER IT, for exactly the same reason one level up.
    # run() gained sizing/mode as arguments on 2026-09-04, which made the collision
    # the universe split had just fixed reappear on the other axis:
    # checks.py verify_v34_arms runs four arms per universe in a loop, and all four wrote
    # here, so nautilus/reports/<universe>/ described whichever arm happened to run last
    # while looking like the universe's report. The arm name comes from
    # arms.registry, so the directory and the arm cannot drift apart, and a
    # combination that is not one of the four named arms gets "{mode}-{sizing}"
    # rather than being folded into one that is.
    _seg = reports_segment(mode, sizing, rebal, drawdown_stop)
    out = (TOOL_REPORTS if reports_root is None else Path(reports_root)) / universe / _seg
    out.mkdir(parents=True, exist_ok=True)
    # THREE REPORTS, AND TWO OF THEM ARE ABOUT ORDERS. The distinction is the
    # whole reason both exist:
    #
    #   orders_all.csv    generate_orders_report() -- EVERY order the strategy
    #                     submitted, whatever became of it. A DENIED or CANCELED
    #                     order appears here and NOWHERE ELSE. This is the file to
    #                     read when asking "did the engine try something that did
    #                     not happen".
    #   order_fills.csv   generate_order_fills_report() -- one row per order that
    #                     produced a fill, so its row count necessarily matches
    #                     fills.csv. A rejected order is invisible here.
    #
    # order_fills.csv WAS CALLED orders.csv, WHICH WAS A LIE THE FILE ITSELF
    # ADMITTED: the old comment said "orders.csv IS NOT AN ORDERS REPORT" and kept
    # the name on the grounds that downstream scripts read it. Nothing reads it --
    # grepped across .py, .md and .txt, the only other mentions are two docstrings.
    # Now that a real orders report sits beside it, a name that means
    # "fill-producing orders" is worth more than a name that was never accurate.
    orders_all_rep = eng.trader.generate_orders_report()
    order_fills_rep = eng.trader.generate_order_fills_report()
    fills_rep = eng.trader.generate_fills_report()
    pos_rep = eng.trader.generate_positions_report()
    orders_all_rep.to_csv(out / "orders_all.csv")
    order_fills_rep.to_csv(out / "order_fills.csv")
    fills_rep.to_csv(out / "fills.csv")
    pos_rep.to_csv(out / "positions.csv")

    # THE DAILY PORTFOLIO STATE, PERSISTED. The strategy has recorded one row per
    # trading day all along -- date, cash, mtm, equity -- and nt_daily_compare
    # consumed it IN PROCESS and then threw it away. Nothing on disk described
    # what the execution engine thought the book was worth day by day.
    if getattr(strat, "daily_equity", None):
        pd.DataFrame(strat.daily_equity).to_csv(out / "daily_equity.csv", index=False)
    if getattr(strat, "daily_holdings", None):
        pd.DataFrame(strat.daily_holdings).to_csv(out / "daily_holdings.csv", index=False)
    print(f"\n  reports -> nautilus/{out.parent.parent.name}/{universe}/{out.name}/  "
          f"[{U['tag']} universe, arm {out.name}: mode={mode} sizing={sizing}]  "
          f"(orders_all {len(orders_all_rep)}, order_fills {len(order_fills_rep)}, "
          f"fills {len(fills_rep)}, positions {len(pos_rep)})")

    acct = eng.cache.account_for_venue(VENUE)
    cash = float(acct.balance_free(INR).as_double())
    pos_val = 0.0
    open_pos = 0
    for pos in eng.cache.positions_open():
        sy = pos.instrument_id.symbol.value
        if sy in strat.last_close:
            pos_val += float(pos.quantity) * strat.last_close[sy]
            open_pos += 1
    equity = cash + pos_val
    filled = [o for o in eng.cache.orders() if o.status_string() == "FILLED"]
    print(f"\n  rebalances       : {strat.rebalances}")
    print(f"  orders submitted : {strat.orders_submitted}")
    print(f"  orders filled    : {len(filled)}")
    print(f"  open positions   : {open_pos}")
    print(f"  cash             : Rs {cash:,.2f}")
    print(f"  positions value  : Rs {pos_val:,.2f}")
    print(f"  EQUITY           : Rs {equity:,.2f}   (from Rs {_capital_axis.selected():,})")
    if strat.decisions:
        d = pd.DataFrame(strat.decisions)
        print(f"\n  first 3 rebalance decisions:")
        print(d.head(3).to_string(index=False))
    eng.dispose()
    return strat


def _cli_nt_run():
    """`python nautilus_port.py nt_run [ARGS]`: what running nautilus/nt_run.py did."""
    from settings import argv_universes, check_tags
    _picked = check_tags(argv_universes(sys.argv), UNIVERSES)
    uni = _picked[-1] if _picked else _DEFAULT_UNIVERSE
    if "--full" in sys.argv:
        run(str(settings.BT_START_DATE.date()), UNIVERSES[uni]["end"], universe=uni)
    else:
        _s = settings.BT_START_DATE
        print(f"SMOKE TEST: full {uni} universe, one year from {_s.date()}\n")
        run(str(_s.date()), str((_s + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()),
            universe=uni)


# ======================================================================================
# nt_execute. From nautilus/nt_execute.py (moved 2026-11-27).
# ======================================================================================
# nt_execute -- run the Nautilus execution engine for every selected combination.
#
# WHY THIS IS A PIPELINE STEP AND nautilus_port.py nt_run IS NOT
#     nautilus_port.run() is a function that backtests ONE (universe, arm, cadence). Until
#     this file existed, nothing in the pipeline called it: Nautilus execution
#     happened only when somebody ran checks.py verify_v34_arms or nautilus_port.py nt_run by hand, and
#     only for the arms those scripts happened to name. A normal `run.py` invocation
#     produced Nautilus INPUT (STEP 16 exports the score parquet) and no Nautilus
#     OUTPUT at all.
#
#     That mattered because Nautilus is the execution engine with exact accounting --
#     order lifecycle, fees, paisa prices, latency -- so its output is the ground truth
#     for what actually happened, day by day. Having it for one arm at one cadence
#     meant having it for one twelfth of what the pipeline produces.
#
# WHAT IT WRITES, PER COMBINATION
#     nautilus/reports/<universe>/<arm>[@r<n>]/
#         orders_all.csv     EVERY order submitted, whatever became of it. A DENIED
#                            or CANCELED order appears here and nowhere else.
#         order_fills.csv    one row per order that produced a fill
#         fills.csv          every fill
#         positions.csv      position lifecycle records
#         daily_equity.csv   date, cash, mtm, equity -- one row per trading day
#         daily_holdings.csv date, symbol, qty, price, value -- the position book
#
# WHAT IT SKIPS, AND WHY IT SAYS SO
#     A frozen universe has no v3/v4 path -- its engine never calls v34_common -- and
#     runs only at the default cadence. Those combinations are reported as NOT RUN
#     with the reason rather than silently omitted, exactly as run.py reports them
#     for the research side.
#
# RUNTIME
#     Measured at 4.3 s (a retired universe) to 7.5 s (midcap150) per backtest, so
#     the twelve combinations of a full run cost about ninety seconds. It is a pipeline step because that is
#     affordable, not because it is free.

def nt_execute():
    """The step, as a function, so run.py can call it in process."""

    reb = cadence.selected()
    ran, skipped = [], []

    print("=" * 96)
    print(" NAUTILUS EXECUTION -- the order book, the trade book and the daily "
          "portfolio state,")
    print(" for every selected combination. This is the execution engine's own "
          "accounting, not")
    print(" the research engine's: exact fees, paisa prices, latency and order "
          "lifecycle.")
    print("=" * 96)

    for u in settings.universe_axis.selected():
        for a in arm_reg.selected():
            # run.py's arm_steps applies no refusals any more -- the two it had
            # were for the retired universes -- so neither does this, and the two
            # halves of a run still cannot disagree about what is possible.
            U = UNIVERSES[u.tag]
            from settings import dd_axis
            strat = run(str(settings.BT_START_DATE.date()), U["end"],
                               universe=u.tag, rebal=reb,
                               reports_root=PIPELINE_REPORTS,
                               dd_overlay=dd_axis.selected(), **a.kwargs)
            ran.append((u.tag, a.name, strat.rebalances))

    print("\n" + "=" * 96)
    print(f" NAUTILUS EXECUTION COMPLETE -- {len(ran)} combination(s) run at "
          f"cadence {reb}")
    for tag, arm, n in ran:
        print(f"    {tag:<6} {arm:<4} {n} rebalances")
    if skipped:
        print(f"\n NOT RUN ({len(skipped)}):")
        for tag, arm, why in skipped:
            print(f"    {tag:<6} {arm:<4} {why}")
    print("=" * 96)


def _cli_nt_execute():
    """`python nautilus_port.py nt_execute [ARGS]`: what running nautilus/nt_execute.py did."""
    nt_execute()


# ======================================================================================
# nt_export_scores. From nautilus/nt_export_scores.py (moved 2026-11-27).
# ======================================================================================
# nt_export_scores -- export model scores for the Nautilus strategy to consume.
#
# THE BOUNDARY THIS FILE DEFINES
#     Research and execution are kept strictly apart. No model is ever trained
#     inside a Nautilus strategy. The research pipeline (features, labels,
#     walk-forward training, purging, the 10-seed ensemble) runs offline exactly as
#     it does today and its only output to the trading layer is this table:
#
#         date | symbol | score
#
#     The strategy reads that table and does nothing else with the model.
#
#     This mirrors how the signal is actually produced: the score for a given month
#     comes from a model trained only on data up to 32 days before that month, so by
#     the time the strategy sees it, it is already a point-in-time value.
#
# ONE EXPORT PER REGISTERED UNIVERSE, DERIVED, NOT LISTED
#     Source and output both come from settings.py --  u.score_cache in,
#     settings.nautilus_scores(u) out -- so this file iterates REGISTRY rather than
#     naming four universes. It was the last place a new universe still needed a
#     hand-written line: everything else in the pipeline picked one up from the
#     registry, and a universe that reached the Nautilus layer without a parquet
#     would have failed there instead of here.
#
#     The paths are also ABSOLUTE now, because the registry's are. The four
#     hardcoded ones were relative ("results/metrics/..."), which worked only
#     because backtest_runs.py spawned this step with cwd=ROOT.
#
# Source : u.score_cache        for every u in settings.REGISTRY
# Output : nautilus/data/{u.nautilus_scores}
#
# Reads only. Nothing under results/ or any results_<tag>/ directory is modified.

OUT_DIR = Path(__file__).resolve().parent / "nautilus" / "data"
# Date window from settings.py. The old year cut emitted June-2026 rows that
# nautilus_port.py nt_run then re-filtered by date; one cut in one place is enough.


def export(cache_path: Path, out_path: Path, tag: str) -> pd.DataFrame:
    """`year_end` is gone. It was declared and never read -- the year cut moved to
    settings.BT_START_DATE/settings.BT_END_DATE ("one cut in one place is enough", above) and
    the parameter was left behind, so three call sites passed 2026 and one passed
    2025 to something that ignored all four. A dead argument that looks like a
    per-universe window is worse than none."""
    print(f"\n{'=' * 66}\n{tag} UNIVERSE\n{'=' * 66}")
    if not cache_path.exists():
        raise FileNotFoundError(f"{cache_path} missing -- run run_all.py first")

    df = read_table(cache_path, usecols=["date", "symbol", "score"], parse_dates=["date"])
    print(f"  cache rows        : {len(df):,}")

    df = df[(df["date"] >= settings.BT_START_DATE) & (df["date"] <= settings.BT_END_DATE)]
    df = df.dropna(subset=["score"]).sort_values(["date", "symbol"]).reset_index(drop=True)

    # --- checks: the strategy cannot rank what it cannot see ---
    assert df["score"].notna().all(), "null scores survived the filter"
    assert not df.duplicated(["date", "symbol"]).any(), "duplicate (date, symbol) rows"

    per_day = df.groupby("date")["symbol"].nunique()
    print(f"  exported rows     : {len(df):,}")
    print(f"  period            : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  trading days      : {df['date'].nunique():,}")
    print(f"  symbols           : {df['symbol'].nunique()}")
    print(f"  symbols per day   : min {per_day.min()}, median {int(per_day.median())}, "
          f"max {per_day.max()}")
    print(f"  score range       : {df['score'].min():.6f} to {df['score'].max():.6f}")

    thin = per_day[per_day < 10]
    if len(thin):
        print(f"  [WARN] {len(thin)} day(s) have fewer than 10 scored symbols; "
              f"first: {thin.index[0].date()} ({thin.iloc[0]} symbols)")
    else:
        print("  thin days         : none (every day has at least 10 scored symbols)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"  saved -> {out_path.relative_to(ROOT)} "
          f"({out_path.stat().st_size / 1e6:.2f} MB)")

    # --- round-trip check: what is written must be what is read back ---
    back = pd.read_parquet(out_path)
    assert back.equals(df), "parquet round-trip changed the data"
    print("  round-trip check  : OK")
    return df


def nt_export_scores():
    """STEP 16. Body moved out of the __main__ guard, unchanged.

    See reports.make_daily_log() for why this was missed: a spawned step never needed
    a main(), so the S4 boundary was invisible-by-absence until run.py ran the
    pipeline in one process.

    The four hardcoded exports this replaced built their input paths as bare
    relatives, so this step -- alone in the pipeline -- depended on the working
    directory being ROOT. The registry's paths are absolute, so that dependency is
    gone. run.py still chdirs to ROOT, which is now belt and braces rather than the
    only thing holding this step up.
    """
    print("Exporting model scores for the Nautilus execution layer...")
    rows = {}
    # ONLY THE SELECTED UNIVERSES. Iterating all of REGISTRY meant `--universe
    # midcap150` tried to export panels for three universes this run never built --
    # which from a warm tree silently exported STALE parquet from an earlier run,
    # and from a cold one had nothing to read.
    import settings
    _sel_u = set(settings.universe_axis.selected_tags())
    for tag, u in REGISTRY.items():
        if tag not in _sel_u:
            print(f"  {tag}: not in this run's selection -- not exported")
            continue
        # model.require_cache, LIKE EVERY OTHER CONSUMER OF A PERMANENT PANEL.
        # v34_common, validate_engine, make_chart, engine_v2_final
        # and eight study scripts all resolve the two locations through it; this
        # file was the one hold-out, reading u.score_cache with no fallback, and
        # that is what crashed the first cold run at STEP 16.
        #
        # THIS IS THE GUARD, NOT THE FIX. require_cache prefers the PERMANENT copy,
        # so on a run that rebuilt panels it would happily read a stale one -- the
        # third failure named in its own docstring. STEP 15b persisting the panels
        # before this step is what makes the permanent copy the fresh one. The
        # fallback only matters if that ordering is ever broken again, and then it
        # produces correct output from /tmp instead of stopping the pipeline.
        src = model.require_cache(u.score_cache,
                                   what=f"{u.label} score panel")
        rows[tag] = len(export(Path(src), settings.nautilus_scores(u), u.label))
    print(f"\n{'=' * 66}")
    print("Done. " + " | ".join(f"{t}: {n:,} rows" for t, n in rows.items()))
    print("These files are the ONLY input the Nautilus strategy takes from the model.")
    print("=" * 66)


def _cli_nt_export_scores():
    """`python nautilus_port.py nt_export_scores [ARGS]`: what running nautilus/nt_export_scores.py did."""
    nt_export_scores()


# ======================================================================================
# nt_daily_compare. From nautilus/nt_daily_compare.py (moved 2026-11-27).
# ======================================================================================
# nt_daily_compare -- find the FIRST day the Nautilus port diverges from the
# reference engine, and show what traded on that day in each system.
#
# WHY THIS EXISTS
#     Chasing a gap by looking at the final equity and guessing at causes failed
#     three times in a row. Every cause that was actually found came from tracing one
#     thing end to end: the momentum mismatch showed up on the first rebalance, and
#     the execution bug showed up in a single order.
#
#     So this compares the two equity curves day by day, stops at the first day where
#     they separate by more than a threshold, and prints both systems' trades for
#     that day. Whatever is different will be visible there.
#
# REFERENCE  results_<universe>/metrics/daily_summary_<universe>.csv  (results/make_audit.py)
# PORT       recorded by the strategy during the run
#
# Run: ./venv/bin/python nautilus_port.py nt_daily_compare --universe=nifty100

def nt_daily_compare__universe():
    """The universe named by --universe=<tag>; defaults to the first certified one.

    An unknown tag, including a retired short tag, exits 2 with the valid list.
    Until 2026-09-24 this tool read the retired 58's artefacts from
    results/metrics/ and could not run on any universe that exists.
    """
    from settings import CERTIFIED, REGISTRY, argv_universes, check_tags
    picked = check_tags(argv_universes(sys.argv), UNIVERSES)
    return REGISTRY[picked[-1] if picked else CERTIFIED[0]]

THRESHOLD_PCT = 0.5      # first day the curves differ by more than this


def nt_daily_compare():
    u = nt_daily_compare__universe()
    strat = run(str(settings.BT_START_DATE.date()), UNIVERSES[u.tag]["end"], universe=u.tag)

    port = pd.DataFrame(strat.daily_equity)
    if port.empty:
        print("The strategy recorded no daily equity. Nothing to compare.")
        return
    port["date"] = pd.to_datetime(port["date"])
    port = port.set_index("date")["equity"]

    ref_path = settings.tagged_artefact(u, "daily_summary")
    ref = read_table(ref_path, parse_dates=["date"]).set_index("date")["total"]

    common = port.index.intersection(ref.index)
    print(f"\n{'=' * 74}")
    print(f"DAILY COMPARISON  ({len(common):,} common trading days)")
    print("=" * 74)

    p, r = port.loc[common], ref.loc[common]
    dev = (p / r - 1) * 100

    print(f"  final reference : Rs {r.iloc[-1]:>12,.0f}")
    print(f"  final port      : Rs {p.iloc[-1]:>12,.0f}   ({dev.iloc[-1]:+.2f}%)")

    bad = dev[dev.abs() > THRESHOLD_PCT]
    if bad.empty:
        print(f"\n  The curves never separate by more than {THRESHOLD_PCT}%.")
        return

    d0 = bad.index[0]
    i = list(common).index(d0)
    print(f"\n  FIRST divergence beyond {THRESHOLD_PCT}%: {d0.date()}  "
          f"({dev.loc[d0]:+.2f}%)")
    print(f"\n  equity around that day:")
    print(f"      {'date':<12}{'reference':>14}{'port':>14}{'dev %':>9}")
    for k in range(max(0, i - 3), min(len(common), i + 3)):
        d = common[k]
        print(f"      {str(d.date()):<12}{r.loc[d]:>14,.0f}{p.loc[d]:>14,.0f}"
              f"{dev.loc[d]:>8.2f}%")

    # what traded, in each system, on and just before that day
    lo = common[max(0, i - 3)]
    rt = read_table(settings.tagged_artefact(u, "daily_trades"),
                     parse_dates=["date"])
    rt = rt[(rt["date"] >= lo) & (rt["date"] <= d0)]
    print(f"\n  REFERENCE trades {lo.date()} .. {d0.date()}  ({len(rt)})")
    if len(rt):
        print(rt[["date", "action", "symbol", "qty", "price", "value", "tc"]]
              .to_string(index=False))

    pt = pd.DataFrame(strat.fills)
    if not pt.empty:
        pt["date"] = pd.to_datetime(pt["date"])
        pt = pt[(pt["date"] >= lo) & (pt["date"] <= d0)]
    print(f"\n  PORT trades {lo.date()} .. {d0.date()}  ({len(pt)})")
    if len(pt):
        print(pt.to_string(index=False))

    print("\n" + "=" * 74)
    print("  Compare the two trade lists above: a symbol present in one and not the")
    print("  other, or the same symbol at a different quantity or price, is the cause.")
    print("=" * 74)


def _cli_nt_daily_compare():
    """`python nautilus_port.py nt_daily_compare [ARGS]`: what running nautilus/nt_daily_compare.py did."""
    nt_daily_compare()


# ======================================================================================
# nt_holdings_compare. From nautilus/nt_holdings_compare.py (moved 2026-11-27).
# ======================================================================================
# nt_holdings_compare -- find the FIRST rebalance where the port's holdings stop
# matching the reference engine's.
#
# WHY
#     Comparing daily equity showed the curves separating around May 2020, but the
#     trades that day already differed in a way that only makes sense if the two
#     portfolios were ALREADY holding different things. So the daily view was showing
#     a symptom, not the cause.
#
#     This compares the two portfolios at every rebalance date and stops at the first
#     one where the held symbols or their quantities differ. That is the origin.
#
# REFERENCE  results_<universe>/metrics/daily_holdings_<universe>.csv  (results/make_audit.py)
# PORT       recorded by the strategy during the run
#
# Run: ./venv/bin/python nautilus_port.py nt_holdings_compare --universe=nifty100

def nt_holdings_compare__universe():
    """The universe named by --universe=<tag>; defaults to the first certified one.

    An unknown tag, including a retired short tag, exits 2 with the valid list.
    Until 2026-09-24 this tool read the retired 58's artefacts from
    results/metrics/ and could not run on any universe that exists.
    """
    from settings import CERTIFIED, REGISTRY, argv_universes, check_tags
    picked = check_tags(argv_universes(sys.argv), UNIVERSES)
    return REGISTRY[picked[-1] if picked else CERTIFIED[0]]


def nt_holdings_compare():
    u = nt_holdings_compare__universe()
    strat = run(str(settings.BT_START_DATE.date()), UNIVERSES[u.tag]["end"], universe=u.tag)

    port = pd.DataFrame(strat.holdings_log)
    if port.empty:
        print("No holdings were recorded. Nothing to compare.")
        return
    port["date"] = pd.to_datetime(port["date"])

    ref = read_table(settings.tagged_artefact(u, "daily_holdings"),
                      parse_dates=["date"])

    dates = sorted(port["date"].unique())
    print(f"\n{'=' * 74}")
    print(f"HOLDINGS COMPARISON at {len(dates)} rebalance dates")
    print("=" * 74)

    first_bad = None
    for d in dates:
        p = {r["symbol"]: int(r["qty"]) for _, r in port[port["date"] == d].iterrows()}
        g = ref[ref["date"] == d]
        r = {row["symbol"]: int(row["qty"]) for _, row in g.iterrows()}
        if p != r:
            first_bad = (pd.Timestamp(d), p, r)
            break

    if first_bad is None:
        print("\n  Holdings match at every rebalance date.")
        return

    d, p, r = first_bad
    i = dates.index(d)
    prev = pd.Timestamp(dates[i - 1]) if i > 0 else None
    print(f"\n  FIRST mismatch: {d.date()}   (rebalance {i + 1} of {len(dates)})")
    if prev is not None:
        print(f"  Previous rebalance {prev.date()} matched exactly.")

    syms = sorted(set(p) | set(r))
    print(f"\n      {'symbol':<13}{'reference':>11}{'port':>9}{'diff':>9}")
    for s in syms:
        a, b = r.get(s, 0), p.get(s, 0)
        flag = "" if a == b else "   <--"
        print(f"      {s:<13}{a:>11}{b:>9}{b - a:>9}{flag}")

    # the fills that produced this state, in both systems
    lo = prev if prev is not None else d
    rt = read_table(settings.tagged_artefact(u, "daily_trades"),
                     parse_dates=["date"])
    rt = rt[(rt["date"] > lo) & (rt["date"] <= d)]
    pt = pd.DataFrame(strat.fills)
    if not pt.empty:
        pt["date"] = pd.to_datetime(pt["date"])
        pt = pt[(pt["date"] > lo) & (pt["date"] <= d)]

    print(f"\n  REFERENCE fills after {lo.date()} up to {d.date()}  ({len(rt)})")
    if len(rt):
        print(rt[["date", "action", "symbol", "qty", "price"]].to_string(index=False))
    print(f"\n  PORT fills after {lo.date()} up to {d.date()}  ({len(pt)})")
    if len(pt):
        print(pt[["date", "action", "symbol", "qty", "price"]].to_string(index=False))

    print("\n" + "=" * 74)
    print("  A symbol whose quantity differs by a small amount points at sizing.")
    print("  A symbol present in one list only points at a skipped or denied order.")
    print("=" * 74)


def _cli_nt_holdings_compare():
    """`python nautilus_port.py nt_holdings_compare [ARGS]`: what running nautilus/nt_holdings_compare.py did."""
    nt_holdings_compare()


# ======================================================================================
# depth_compare. From depth_compare.py (moved 2026-11-27).
# ======================================================================================
# depth_compare -- the port under "unlimited" depth versus "volume" depth.
#
# Runs nifty100 and midcap150 twice each and reports what changes when the quote
# stops being infinitely deep. Changes no default: DEPTH_MODE is set on the module for the
# duration of a run and restored afterwards.
#
# WHAT IS COUNTED
#     walked   an order that filled at more than one level, i.e. it consumed
#              level 1 and met level 2 or 3. Detected as an order id with more
#              than one fill event.
#     unfilled orders the strategy submitted that never produced a fill. Under
#              unlimited depth this is always zero; under volume depth it is the
#              number that could not be executed at all, which is the figure that
#              decides whether the strategy is tradeable at this size.

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

DEPTH_COMPARE_SLIPPAGE = SLIPPAGE

# THE SOURCE FOLDER, NOT data_dir, AND THE SORTED SYMBOL LIST. Both came from
# the per-universe config modules until step 7; both are registry fields now and
# carry the same values. `symbol_list` is the sorted tuple the configs' SYMBOLS_* were,
# so the volume panel is loaded in the same order it always was.
UNIV = [(u.tag, u.raw_data_dir, u.symbol_list) for u in certified()]


def perf_from_strat(strat, tag):
    eq = pd.DataFrame(strat.daily_equity)
    eq["date"] = pd.to_datetime(eq["date"])
    e = eq.set_index("date")["equity"]
    tc = sum(f["tc"] for f in strat.fills)
    m = metrics(e, tag, tc, len(strat.fills))
    return m, e


def run_mode(u, mode, raw_dir, syms):
    set_depth_mode(mode)
    if mode == "volume":
        n = set_volume_source(raw_dir, set(syms))
        print(f"    volume loaded for {n} symbols", flush=True)
    U = UNIVERSES[u]
    with contextlib.redirect_stdout(io.StringIO()):
        s = run(str(settings.BT_START_DATE.date()), U["end"], quiet=True, universe=u)
    set_depth_mode("unlimited")
    return s


def depth_compare():
    import subprocess, datetime
    import model
    import settings
    try:
        _commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.strip()
    except Exception:
        _commit = "unknown"
    print("=" * 104)
    print(" DEPTH MODEL -- 'unlimited' (default, unchanged) vs 'volume'")
    print(f" levels {DEPTH_LEVELS} | top-level depth "
          f"{DEPTH_FRACTION:.0%} of prior-{DEPTH_VOL_WIN}d median "
          f"daily volume | spacing {DEPTH_COMPARE_SLIPPAGE:.2%} per level")
    print("=" * 104)
    print(f" Generated {datetime.date.today()} at commit {_commit}.")
    for _t, _rd, _ in UNIV:
        _u = REGISTRY[_t]
        _fp = model.data_fingerprint(_u.prepare_data_dir(), _u.raw_data_dir)
        print(f"   {_t}: {_fp.get('n_files')} files, {_fp.get('digest')}")
        print(f"     {_fp.get('raw_data_dir')}")
    print(" SUPERSEDES THE COPY DATED 2026-09-17, which was produced before the")
    print(" universes were repointed at Final_Without_Survivorship_Data on")
    print(" 2026-09-18. That run reported midcap150 unlimited 29.16 / volume 27.36,")
    print(" a depth cost of 1.80 CAGR points over 985 fills with 19 orders walking,")
    print(" and nifty100 25.43 / 25.42 over 997 fills. Those figures are superseded.")
    print(" WHAT MOVED AND WHAT IS NOT KNOWN. The depth cost on midcap150 is now")
    print(" 0.04 CAGR points, not 1.80. The unlimited BASELINE moved too (29.16 ->")
    print(" 27.79), so the change is not confined to the depth model: the backtest")
    print(" underneath it is running on different prices and produces 1,006 fills")
    print(" rather than 985. The depth model's own volume source is NOT the cause --")
    print(" measured 2026-09-20, holding today's prices fixed and swapping only the")
    print(" volume source between the old data/raw/MidCap150/clean and today's")
    print(" constituents gives 27.75 and 1,020 fill events either way, identical.")
    print(" Beyond that the move is NOT ATTRIBUTED. Reproducing the 2026-09-17 run")
    print(" would need both its data and its code, and the code has moved since.")
    print(" AIIL. The old run's 19 walked orders are not recorded individually, so")
    print(" this cannot be measured from the depth diagnostic. What is on record:")
    print(" the liquidity diagnostic of the same era and data listed 22 midcap150")
    print(" fills above 10% participation and 13 of them were AIIL; today's list has")
    print(" 12 fills and none is AIIL. AIIL's price file now starts 2024-04-23")
    print(" against 2015-06-11 before the repoint, so its 2021 orders are gone.")
    print(" That is consistent with AIIL having driven the old figure and is not a")
    print(" measurement of it.")
    print("=" * 104)

    for u, raw_dir, syms in UNIV:
        print(f"\n{'='*104}\n {u.upper()}\n{'='*104}", flush=True)
        res = {}
        for mode in ("unlimited", "volume"):
            print(f"  running {mode} ...", flush=True)
            s = run_mode(u, mode, raw_dir, syms)
            m, e = perf_from_strat(s, u)
            f = pd.DataFrame(s.fills)
            # COUNTED PER ORDER, NOT PER FILL EVENT.
            #   A walking order emits one fill event per level it consumes, so
            #   `orders_submitted - len(fills)` is not an unfilled count -- it went
            #   NEGATIVE on the first attempt, which is what exposed the error.
            #   client_order_id from the venue's own fills report is the order
            #   identity, so distinct ids that produced any fill is what "filled"
            #   means, and an id appearing more than once is an order that walked.
            # The arm is part of the reports path now (a run's sizing/mode chose
            # the directory). This script never passes either, so nt_run's own
            # defaults apply -- named through arms.registry rather than spelled
            # "v2" here, so the two cannot drift.
            import inspect
            from portfolio import path_segment
            _d = {k: v.default for k, v in inspect.signature(run).parameters.items()}
            # nautilus_port.run() writes a tool's reports under TOOL_REPORTS, not the
            # pipeline's nautilus/reports/ (2026-09-24).
            rep = (TOOL_REPORTS / u
                   / path_segment(_d["mode"], _d["sizing"]) / "fills.csv")
            fr = read_table(rep)
            per_order = fr.groupby("client_order_id").size()
            filled_orders = int(len(per_order))
            walked = int((per_order > 1).sum())
            walked_levels = per_order[per_order > 1]
            unfilled = int(s.orders_submitted - filled_orders)
            res[mode] = dict(m=m, fills=len(f), orders=filled_orders,
                             walked=walked, unfilled=unfilled,
                             submitted=s.orders_submitted,
                             lv=walked_levels)
            print(f"    CAGR {m['CAGR%']:>7.2f}  Sharpe {m['Sharpe']:>5.2f}  "
                  f"MaxDD {m['MaxDD%']:>7.2f}  submitted {s.orders_submitted:>4}  "
                  f"orders filled {filled_orders:>4}  fill events {len(f):>4}  "
                  f"walked {walked:>4}  unfilled {unfilled:>3}", flush=True)
            if walked:
                d = walked_levels.value_counts().sort_index()
                print(f"      fills per walking order: "
                      + ", ".join(f"{k} levels x{v}" for k, v in d.items()), flush=True)

        a, b = res["unlimited"], res["volume"]
        print(f"\n  {'':<12}{'CAGR%':>9}{'Sharpe':>9}{'MaxDD%':>9}{'trades':>8}"
              f"{'fills':>8}{'walked':>8}{'unfilled':>10}")
        for lab, r in (("unlimited", a), ("volume", b)):
            print(f"  {lab:<12}{r['m']['CAGR%']:>9.2f}{r['m']['Sharpe']:>9.2f}"
                  f"{r['m']['MaxDD%']:>9.2f}{r['m']['Trades']:>8}{r['orders']:>8}"
                  f"{r['walked']:>8}{r['unfilled']:>10}")
        print(f"  {'delta':<12}{b['m']['CAGR%']-a['m']['CAGR%']:>+9.2f}"
              f"{b['m']['Sharpe']-a['m']['Sharpe']:>+9.2f}"
              f"{b['m']['MaxDD%']-a['m']['MaxDD%']:>+9.2f}"
              f"{b['m']['Trades']-a['m']['Trades']:>+8}{b['fills']-a['fills']:>+8}")


def _cli_depth_compare():
    """`python nautilus_port.py depth_compare [ARGS]`: what running depth_compare.py did."""
    depth_compare()


# ======================================================================================
# THE COMMAND LINE. `python nautilus_port.py TOOL [ARGS]` runs one tool as its own
# file used to run, with ARGS as its command line.
# ======================================================================================
TOOLS = {
    "nt_data": _cli_nt_data,
    "nt_run": _cli_nt_run,
    "nt_execute": _cli_nt_execute,
    "nt_export_scores": _cli_nt_export_scores,
    "nt_daily_compare": _cli_nt_daily_compare,
    "nt_holdings_compare": _cli_nt_holdings_compare,
    "depth_compare": _cli_depth_compare,
}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in TOOLS:
        _tool = sys.argv.pop(1)
        sys.argv[0] = f"nautilus_port.py {_tool}"
        TOOLS[_tool]()
    else:
        raise SystemExit(f"usage: python nautilus_port.py {{{','.join(TOOLS)}}} [ARGS]")
