"""
drawdown_stop.py -- the drawdown stop of v5 and v6, as one state machine.

experiments/DRAWDOWN_STOP_PREREG.txt states the rule. This file is the only
implementation of it. Three loops call it, each at the same four points of its
trading day:
    results/test_exposure.backtest_exposure   the engine every published arm runs
    nautilus/nt_attribution.run               the reference copy nt_verify compares with
    nautilus/nt_strategy.PredictiveEngineStrategy   the port
The caller owns its orders, cash and holdings. This class only decides when the
arm must sell everything, when it may place its normal order again, and when the
peak resets, and it writes down why.

STATES
    IN           the running peak of close equity is updated each close. A close at
                 or below (1 - threshold) x peak triggers an exit at the next open.
    LIQUIDATING  an order to sell every holding stands. What did not fill (a missing
                 open, the participation cap) is offered again at each next open.
    OUT          from the day the book is flat. No order for cooldown_cycles x rebal
                 trading days. Then, on each rebalance-grid day, breadth decides: at
                 reentry_breadth or more the arm's normal order is placed.
    REENTERED    the re-entry order filled at least one buy today; at this close the
                 peak resets to this close's equity and the state returns to IN.

THE CALLING SEQUENCE FOR ONE TRADING DAY, index i
    1. begin_day()
    2. after the morning's fills, if exit_pending or reentry_pending:
           after_fills(i, held_now, held_before, date_of)
    3. on a rebalance-grid day while state != "IN":
           allowed = grid_allows_order(i, breadth_fn)
       and, if allowed, after the caller's normal ordering:
           after_reentry_order(order_placed)
       while state == "IN" the caller rebalances as it always does.
    4. at the close:
           action = at_close(i, date, equity, order_placed_today, holdings_left, last)
       action "exit" means: replace any order placed today with an order to sell
       every holding at the next open. Then rows(date, equity) gives the day's events.
"""

IN, LIQUIDATING, OUT, REENTERED = "IN", "LIQUIDATING", "OUT", "REENTERED"


class StopState:
    def __init__(self, stop, rebal, n_days):
        # THE SEAL, checked here so that no loop can run the registered stop before
        # the band file is committed, however it was handed the stop.
        import sys as _sys
        from pathlib import Path as _P
        _root = str(_P(__file__).resolve().parents[1])
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        from arms.registry import require_unsealed
        require_unsealed(stop)
        self.stop = stop
        self.rebal = int(rebal)
        self.n_days = int(n_days)
        self.state = IN
        self.peak = None
        self.peak_date = None
        self.flat_i = None
        self.cool_end_i = None
        self.exit_pending = False      # an exit order fills at the next open
        self.reentry_pending = False   # a re-entry order fills at the next open
        self.events = []
        self.breadth = None

    def begin_day(self):
        self.events = []
        self.breadth = None

    def _ev(self, name, detail):
        self.events.append((name, detail))

    def after_fills(self, i, held_now, held_before, date_of):
        """Book what this morning's exit or re-entry order did."""
        if self.exit_pending:
            self.exit_pending = False
            sold = {k: int(q) - int(held_now.get(k, 0)) for k, q in held_before.items()
                    if int(held_now.get(k, 0)) < int(q)}
            self._ev("exit fills", f"sold {len(sold)} name(s) at this open: "
                     + (", ".join(f"{k} {q:,} sh" for k, q in sorted(sold.items()))
                        or "none"))
            if not held_now:
                self.state, self.flat_i = OUT, i
                self.cool_end_i = i + self.rebal * int(self.stop.cooldown_cycles)
                end = (date_of(self.cool_end_i) if self.cool_end_i < self.n_days
                       else "after the window")
                self._ev("flat", f"book flat at this open; cooldown until {end}")
            else:
                self._ev("exit partly filled",
                         f"{len(held_now)} name(s) still held: "
                         + ", ".join(f"{k} {int(q):,} sh" for k, q in sorted(held_now.items()))
                         + "; offered again at the next open")
        elif self.reentry_pending:
            self.reentry_pending = False
            if held_now:
                self.state = REENTERED
                self._ev("re-entry filled", f"{len(held_now)} name(s) bought; "
                         "peak resets to this close")
            else:
                self._ev("re-entry not filled",
                         "no buy filled; stays in cash, peak not reset")

    def grid_allows_order(self, i, breadth_fn):
        """On a rebalance-grid day while not IN: may the arm place its order today?

        breadth_fn() returns the day's breadth, computed the way the caller's
        mode="breadth" computes it. It is called only once the cooldown is over.
        """
        if self.state == OUT and i >= self.cool_end_i:
            self.breadth = float(breadth_fn())
            if self.breadth >= self.stop.reentry_breadth:
                return True
            self._ev("waiting", f"breadth {self.breadth:.4f} < "
                     f"{self.stop.reentry_breadth:.2f}; stays in cash")
        elif self.state == OUT:
            self._ev("cooldown", "rebalance day inside the cooldown; no order")
        else:
            self._ev("liquidating", "rebalance day while the exit is unfilled; no order")
        return False

    def after_reentry_order(self, order_placed):
        if order_placed:
            self.reentry_pending = True
            self._ev("re-entry order", f"breadth {self.breadth:.4f} >= "
                     f"{self.stop.reentry_breadth:.2f}; the arm's normal order fills "
                     "at the next open")
        else:
            self._ev("re-entry skipped", "breadth allows re-entry but no order was "
                     "placed (fewer than TOP_N rankable names)")

    def at_close(self, i, date, equity, order_placed_today, holdings_left, last):
        """-> "exit" when an order to sell everything must stand for the next open."""
        if self.state == REENTERED:
            self.state, self.peak, self.peak_date = IN, equity, date
            self._ev("peak reset", "peak reset to the re-entry day's close")
            return None
        if self.state == IN:
            if self.peak is None or equity > self.peak:
                self.peak, self.peak_date = equity, date
            if equity <= (1.0 - self.stop.threshold) * self.peak:
                if last:
                    self._ev("trigger on the last session", "no next open; nothing is sold")
                    return None
                if order_placed_today:
                    self._ev("order superseded", "this close's rebalance order is "
                             "replaced by the drawdown exit")
                self.state, self.exit_pending = LIQUIDATING, True
                self._ev("trigger", f"close equity {equity / self.peak - 1:+.2%} from "
                         "the peak; sell everything at the next open")
                return "exit"
            return None
        if self.state == LIQUIDATING and holdings_left and not last:
            self.exit_pending = True
            self._ev("exit retried", "remaining holdings offered at the next open")
            return "exit"
        return None

    def drawdown(self, equity):
        return equity / self.peak - 1 if self.peak else None

    def rows(self, date, equity):
        """The day's events as rows of daily_stop_events_<tag>.csv."""
        dd = self.drawdown(equity)
        return [{"date": date, "event": name, "state": self.state,
                 "peak": round(self.peak, 2) if self.peak is not None else None,
                 "peak_date": self.peak_date, "equity": round(equity, 2),
                 "drawdown_pct": round(dd * 100, 4) if dd is not None else None,
                 "breadth": round(self.breadth, 4) if self.breadth is not None else None,
                 "detail": detail}
                for name, detail in self.events]
