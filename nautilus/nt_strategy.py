"""
nt_strategy.py -- the Predictive Engine execution logic as a Nautilus Strategy.

WHAT THIS FILE DOES AND DOES NOT DO
    It reproduces the EXECUTION layer only: ranking, buffer, inverse-vol sizing,
    breadth-scaled exposure, and order submission. No model is trained here. The
    scores arrive precomputed from nt_export_scores.py, which is the only channel
    between research and execution.

EXECUTION TIMING
    Each day is fed as a QuoteTick at 09:15 (bid/ask around the open) and a Bar at
    15:30 (OHLC).

        15:31 on day t   -- a timer fires once every symbol's bar has landed. The
                            rebalance decision is taken here and the orders are
                            PLANNED but not sent.
        09:15 on day t+1 -- each instrument's opening quote arrives. The moment an
                            instrument's own quote lands, its planned order is sent
                            and fills against that quote.

    An earlier version submitted at 15:31 and relied on a LatencyModel to delay the
    fill. That was wrong and it was caught by tracing a single order: the resting
    order matched the STALE book before the new quote updated it, so it filled at
    the PREVIOUS day's open. The date looked right while the price was a day old.
    Measured on SUNPHARMA: fill 433.15, which is open(01-01) 432.50 * 1.0015 -- the
    wrong day's open, not the 431.15 expected from open(01-02).

    Planning at the close and sending at the next open removes the dependence on
    latency entirely, and matches the stated rule directly: signal at close of t,
    execution at the open of t+1.

WARM-UP
    mom20 needs 21 closes and vol60 needs 61, so data must start before the trading
    window. The strategy ignores every day before `trading_start` while still
    consuming its bars to fill the rolling buffers.

FEATURE WINDOWS MUST USE THE UNION DATE INDEX  (a bug that was found and fixed)
    The reference engine builds a panel whose index is the UNION of every symbol's
    trading dates, forward-filled. So px.shift(20) means "20 union dates ago", not
    "20 of this symbol's own bars ago". Those differ whenever a symbol has a gap.

    The first version of this strategy kept a per-symbol deque of closes and looked
    back 20 entries. On 2019-01-01 that produced breadth 27/53 where the reference
    produced 17/53 -- exposure 51% instead of 32%, i.e. the portfolio ran roughly
    twice as invested for seven years and the equity curve was about 8% adrift.

    The fix is to hold a shared list of observed trading dates plus a per-symbol
    date -> close map with forward fill, and to index the momentum and volatility
    windows by position in that shared list. This reproduces the panel exactly.

ONE KNOWN DIFFERENCE FROM THE REFERENCE ENGINE  (documented, not hidden)
    The reference engine sizes buys at the NEXT day's open: it sells first,
    recomputes portfolio value at t+1 open prices, then does
        q = (invest_value * weight) // open_price_at_t+1
    A Nautilus strategy must submit at the close of t, so quantity is computed from
    t's close prices and the portfolio value at t's close. The two differ by the
    overnight gap. This changes individual trade sizes slightly and is the main
    reason the two equity curves will not match to the rupee. It is measured rather
    than assumed -- see the reconciliation step.
"""
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
from qbeast_in_charges import (Broker, Exchange, Product, Segment, Side as QSide,
                               compute_leg_charges)

from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

TOP_N = 8
BUFFER = 16
REBAL = 20
VOL_WIN = 60
MOM_WIN = 20
SAFETY = 0.98
TRADING_DAYS = 252


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
        self._invest_val = None       # fixed once the sells are done, then shared by the buys
        self._exposure = 0.0          # exposure decided at the close, applied at the open
        self._open_px = {}            # symbol -> this morning's ask (the BUY fill price)
        self._open_bid = {}           # symbol -> this morning's bid (the SELL fill price)
        self._open_mid = {}           # symbol -> this morning's raw open, for valuation
        self._open_day = {}           # symbol -> the date its latest quote belongs to
        self._quote_day = None        # date of the most recent opening quote seen
        self.daily_equity = []        # one row per trading day, for reconciliation
        self.fills = []               # every fill, for reconciliation
        self.holdings_log = []        # holdings at each rebalance, for reconciliation

    # ---------------------------------------------------------------- setup
    def configure(self, scores: pd.DataFrame, instruments, trading_start: str):
        """Called before the engine runs. Keeps __init__ free of heavy objects."""
        self.scores = scores.copy()
        self.scores["date"] = pd.to_datetime(self.scores["date"])
        self._scores_by_day = {d: g.set_index("symbol")["score"]
                               for d, g in self.scores.groupby("date")}
        self.instruments = list(instruments)
        self.trading_start = pd.Timestamp(trading_start)

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
        # bid = open*(1-slippage) and ask = open*(1+slippage), so the mid is the raw
        # open -- the price the reference engine values the portfolio at.
        self._open_mid[sym] = 0.5 * (bid + ask)
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
        if not self._plan:
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
        # score-descending (nt_attribution.py:143,158), so it funds its best ideas
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
        self._invest_val = None
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

            # Every sell has settled by the time the first buy is reached, so the
            # portfolio value is computed once here -- the same point in the sequence
            # at which the reference engine computes it.
            if self._invest_val is None:
                self._invest_val = self._portfolio_at_open() * self._exposure * SAFETY
            px = self._open_px.get(sy)
            if not px or px <= 0:
                continue
            # Sized against the price the order will actually fill at, which is what
            # the reference engine does when it sizes at the next open. Sizing at the
            # previous close instead left every quantity slightly off (LT 52 vs 51,
            # LTFOODS 790 vs 770 on the first rebalance) and those errors compounded
            # across 93 rebalances.
            q = int((self._invest_val * weight) // px)
            if q < 1:
                continue
            # Unaffordable buys are SKIPPED, never shrunk -- the reference engine's
            # rule. leg_charges is the same calculator the venue will deduct with, so
            # this is not a guessed headroom; an earlier version of this port guessed
            # 5% and it shrank every buy.
            if self._free_cash() < q * px + leg_charges(px, q, "BUY"):
                continue
            self._send(inst, OrderSide.BUY, q)
            return

    def _free_cash(self):
        return float(self.portfolio.account(self.instruments[0].id.venue)
                     .balance_free(self.instruments[0].quote_currency).as_double())

    def _portfolio_at_open(self):
        """Cash plus holdings valued at this morning's raw open.

        Valuing at the OPEN is a deliberate, permanent difference. The reference
        values at the execution day's CLOSE; verified by hand on 2019-01-30,
        portfolio 973,921.51 -> invest value 144,025.46 -> BEL 613 shares, which is
        what it filled, where the open gives 612. But a strategy standing at 09:15
        cannot know that day's close, and reproducing it would mean feeding the
        strategy future data. Measured cost of the reference's look-ahead:
        +0.01% of final equity (attribution ARM A vs ARM D).
        """
        mtm = 0.0
        for inst in self.instruments:
            q = self.portfolio.net_position(inst.id)
            if not q or float(q) <= 0:
                continue
            sy = inst.id.symbol.value
            px = self._open_mid.get(sy) or self.last_close.get(sy)
            if px:
                mtm += float(q) * px
        return self._free_cash() + mtm

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

        self.day_index += 1
        if self.day_index % REBAL != 0:
            return
        self.rebalance(day)

    # ---------------------------------------------------------- rebalance
    def rebalance(self, day):
        # --- breadth over the stocks that actually have enough history ---
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
        if not mom:
            return
        n_pos = sum(1 for v in mom.values() if v > 0)
        breadth = n_pos / len(mom)
        exposure = max(0.0, min(1.0, breadth))

        # --- ranking, restricted to names we have a price for today ---
        s = self._scores_by_day[day]
        s = s[[k for k in s.index if k in self.last_close]]
        if len(s) < TOP_N:
            return
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

        # --- inverse-volatility weights over the top-N ---
        w = {}
        for sy in top:
            arr = [self._close_at(sy, k) for k in range(i_now - VOL_WIN, i_now + 1)]
            if any(v is None or v <= 0 for v in arr):
                w[sy] = 0.0
                continue
            arr = np.asarray(arr, dtype=float)
            rets = arr[1:] / arr[:-1] - 1.0
            vol = float(np.std(rets, ddof=1) * np.sqrt(TRADING_DAYS))
            w[sy] = (1.0 / vol) if vol > 0.01 else 0.0
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
            # Neither quantity NOR invest value is fixed here. Both are computed
            # next morning from open prices, which is what the reference engine
            # does: it revalues the portfolio on the execution day before sizing.
            # The rank is carried through so the morning release can fund the
            # highest-scoring names first -- see on_market_open.
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

    # ------------------------------------------------------------ helpers
    def _inst(self, symbol):
        for inst in self.instruments:
            if inst.id.symbol.value == symbol:
                return inst
        return None

    def on_stop(self):
        # THE FINAL TRADING DAY USED TO BE MISSING FROM daily_equity.
        #     on_daily_close is driven by a timer set for 15:31, and the daily bar is
        #     stamped 15:30 (nt_data.py CLOSE_TIME). The backtest clock stops at the
        #     last data event, so on the final day it reaches the 09:16 market-open
        #     timer -- which executed that day's rebalance -- and then stops before
        #     15:31 is ever reached. The fills happened; the equity row did not.
        #
        #     Measured cost: the port's series held 1,841 rows against the reference's
        #     1,842 on the 58, and the missing 2026-06-08 carried TEN fills that moved
        #     Rs 1.1m out of positions into cash. Equity read 3,236,727.28 (05 June)
        #     where the true final figure is 3,214,422.58 (08 June). On mid the missing
        #     day carried twelve fills and Rs 106,221 of difference. Every statistic
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
            self.log.info(f"final trading day {now.date()} recorded on stop "
                          f"(the 15:31 timer cannot fire after the 15:30 close bar)")
        self.log.info(f"rebalances={self.rebalances} orders={self.orders_submitted}")
