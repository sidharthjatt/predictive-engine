"""
drawdown_overlay.py -- the drawdown-limit axis (dd_axis.py) as one state class.

THE RULE. At each close, with W the close equity and M its all-time peak since
the start of the run (never reset):

    C = W - (1 - L) * M                      the cushion
    E = max(F, min(1, m * C / W))            the overlay's exposure limit

The arm still decides which names to hold and, for v2/v4, its own exposure A
(1 for v1/v3). The overlay only cuts. With x the invested fraction at the close:

    trim     when x > min(E, A) + band        to min(E, A)
    top-up   only after a trim, when x < min(E, 0.98 A) - band, or, once E is 1,
             when the gap is more than SNAP   to min(E, 0.98 A)

0.98 is the arm's own haircut on invest_value, so a top-up never buys more than
the arm itself would. "Only after a trim" keeps the overlay from investing cash
the arm chose to hold (v2/v4 breadth, cash-short residuals). The trim flag clears
once the book is back within SNAP of the arm's own level, 0.98 A.

TRADES. The order is placed at the close and filled at the next open. Each held
name is resized by the same ratio r = target / x: floor(shares * (1 - r)) sold,
or floor(shares * (r - 1)) bought. Quantities are fixed at the close; prices are
the next open's. The caller fills them after the arm's own orders that morning,
through its normal slippage, charges, participation cap and tax ledger, and skips
a name the arm or a forced exit has already sold. Entrants bought that morning
are sized at min(E, A) instead of A, so they are not bought full and trimmed the
same morning (entry_factor).

NO MULTIPLIER IS CARRIED BETWEEN DAYS. The first version tracked a multiplier k of
the arm's book and inferred the arm's own exposure as x / k. Prices move the
invested fraction without a trade, so that inference drifted: on a synthetic
recovery k stayed at 0.79 with the book 99.9% invested. Every decision now reads
the actual book.

ONE CLASS, THREE LOOPS: results/test_exposure.backtest_exposure,
nautilus/nt_attribution.run and nautilus/nt_strategy.PredictiveEngineStrategy.
This file decides; the callers own cash, holdings and fills.

Exploratory: no result with the axis on has been validated.
"""
import math

SNAP = 0.01       # 1 point of the portfolio: the minimum move back to full once E is 1
HAIRCUT = 0.98    # the arm's own haircut on invest_value (test_exposure, nt_strategy)


class OverlayState:
    def __init__(self, cfg, start_capital):
        self.cfg = cfg
        self.peak = float(start_capital)       # M; the start is the first peak
        self.peak_date = None
        self.E = 1.0                           # the limit decided at the last close
        self.cut = False                       # True from a trim until the book is restored
        self.order = None                      # {symbol: signed qty} for the next open
        self.events = []                       # one dict per order and per fill
        self.worst_dd = 0.0                    # most negative W / M - 1 at a close
        self.worst_date = None
        self.worst_peak_date = None
        self.sessions_below = 0                # closes with W < (1 - L) * M
        self.days_at_floor = 0                 # closes where E was held up by the floor
        self.n_orders = 0
        self.last_invested = None

    # ------------------------------------------------------------------ rule
    def target(self, W):
        """E for close equity W against the current peak."""
        L, m, F = self.cfg.limit, self.cfg.m, self.cfg.floor
        if W <= 0:
            return F
        C = W - (1.0 - L) * self.peak
        raw = m * C / W
        # AT A PEAK m * C / W IS m * L, WHICH IS 1 AT THE DEFAULT m = 1 / L, but in
        # floating point it lands a rounding error above or below 1 depending on W.
        # The two sides of nt_verify carry W a few rupees apart, so one read E = 1
        # (the snap back to full) and the other 0.9999999999 (the band), and their
        # books parted on nifty50 v1 on 2019-03-14. Within 1e-9 of 1 is 1.
        if abs(raw - 1.0) < 1e-9:
            raw = 1.0
        return max(F, min(1.0, raw))

    def entry_factor(self, arm_expo):
        """Multiplier on the arm's invest_value for entrants at the next open:
        min(E, A) / A, from the E decided at the last close."""
        if arm_expo <= 0:
            return 1.0
        return min(1.0, self.E / arm_expo)

    # ------------------------------------------------------------ at the close
    def at_close(self, date, W, mtm, shares, last, arm_expo):
        """Update the peak and the drawdown record, and decide the next open's order.

        `shares` is {symbol: qty} at this close, `arm_expo` the arm's own exposure
        (A). Sets self.order (or None) and returns it. Nothing is ordered on the
        last session.
        """
        cfg = self.cfg
        L = cfg.limit
        if W > self.peak:
            self.peak, self.peak_date = float(W), date
        dd = W / self.peak - 1.0
        if dd < self.worst_dd:
            self.worst_dd, self.worst_date, self.worst_peak_date = dd, date, self.peak_date
        if W < (1.0 - L) * self.peak:
            self.sessions_below += 1
        E = self.target(W)
        raw = (cfg.m * (W - (1.0 - L) * self.peak) / W) if W > 0 else 0.0
        if raw < cfg.floor and E == cfg.floor:
            self.days_at_floor += 1
        self.E = E
        self.order = None
        x = (mtm / W) if W > 0 else 0.0
        self.last_invested = x
        if x <= 0:
            return None
        t_cut = min(E, arm_expo)
        t_up = min(E, HAIRCUT * arm_expo)
        kind, tgt = None, None
        if x - t_cut > cfg.band:
            kind, tgt = "trim", t_cut
        elif self.cut and t_up - x > (cfg.band if E < 1.0 else SNAP):
            kind, tgt = "top-up", t_up
        elif self.cut and x >= HAIRCUT * arm_expo - SNAP:
            # Restored to the arm's own level, not merely to the overlay's target:
            # right after a trim the book sits at its target, and clearing the flag
            # there stopped every later top-up.
            self.cut = False
        if kind is None or last:
            return None
        r = tgt / x
        order = {}
        for s, q in sorted(shares.items()):
            dq = math.floor(q * (1.0 - r)) if r < 1.0 else math.floor(q * (r - 1.0))
            if dq >= 1:
                order[s] = -int(dq) if r < 1.0 else int(dq)
        if kind == "trim":
            self.cut = True
        self.events.append({"date": date, "event": kind + " order", "equity": W,
                            "peak": self.peak, "drawdown_pct": dd * 100,
                            "limit_exposure_pct": E * 100, "arm_exposure_pct": arm_expo * 100,
                            "invested_pct": x * 100, "target_invested_pct": tgt * 100,
                            "names": len(order),
                            "detail": f"{kind} every holding by {abs(1.0 - r):.2%} at the next open"})
        self.n_orders += 1
        self.order = order or None
        return self.order

    # ---------------------------------------------------------- after the fills
    def after_fills(self, date, before, after):
        """Record what filled. `before` and `after` are {symbol: qty} for the names
        in the order, before and after the overlay's own fills."""
        moved = sum(abs(after.get(s, 0) - q) for s, q in before.items())
        self.events.append({"date": date, "event": "filled", "equity": None, "peak": self.peak,
                            "drawdown_pct": None, "limit_exposure_pct": None,
                            "arm_exposure_pct": None, "invested_pct": None,
                            "target_invested_pct": None, "names": len(before),
                            "detail": f"{moved:,} shares across {len(before)} names"})
        self.order = None

    def cancel(self):
        """The order is dropped (nothing it names is still held)."""
        self.order = None

    # ----------------------------------------------------------------- report
    def summary(self):
        L = self.cfg.limit
        breach = -self.worst_dd - L
        return {"limit_pct": L * 100, "m": self.cfg.m, "floor_pct": self.cfg.floor * 100,
                "band_pct": self.cfg.band * 100,
                "worst_dd_pct": self.worst_dd * 100, "worst_date": self.worst_date,
                "worst_peak_date": self.worst_peak_date,
                "breached": breach > 1e-12, "breach_points": max(0.0, breach) * 100,
                "sessions_below_limit": self.sessions_below,
                "days_at_floor": self.days_at_floor, "orders": self.n_orders,
                "invested_final_pct": (self.last_invested or 0.0) * 100}


def marginal_tax(ledger_rows, dd_row_ids):
    """Tax caused by the overlay's sales, as a marginal figure: each financial
    year's tax on every realised gain, less its tax with the gains realised by the
    overlay's sales left out. Losses are set off within a year, so this is not an
    exact attribution; it is what those sales added to the bills."""
    import pandas as pd
    import tax_util as T
    if not ledger_rows:
        return 0.0
    df = pd.DataFrame(ledger_rows)
    keep = df[[i not in dd_row_ids for i in range(len(df))]]

    def total(lots):
        return sum(T.tax_for_fy(fy, b)["total_tax"]
                   for fy, b in T.realized_buckets(lots).items())
    return total(df) - total(keep)


EVENT_COLUMNS = ["date", "event", "equity", "peak", "drawdown_pct", "limit_exposure_pct",
                 "arm_exposure_pct", "invested_pct", "target_invested_pct", "names", "detail"]
