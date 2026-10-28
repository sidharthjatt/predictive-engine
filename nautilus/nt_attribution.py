"""
nt_attribution.py -- explain the gap between the reference engine and Nautilus.

THE QUESTION
    The reference engine ends at Rs 31,01,677 and the Nautilus port at Rs 31,90,675
    -- a gap of about 2.9%, or 0.43 points of CAGR. Is that gap the KNOWN structural
    difference, or is it a bug?

SIZING
    Since 2026-10-28 the engine, this copy and the port all size a buy at the close
    of the decision session t, from the book at that close and the close price
    with slippage:
        q = (book_value(t close) * exposure * 0.98 * weight) // (close(t) * (1 + s))
    The open of t+1 sets only the fill price, the cash test and the trim. Until
    then the engine and this copy sized at the open of t+1 and the port matched
    them; the ARM B that sized at the close is gone with that difference.

THE TEST
    Run this copy on the port's data and scores. Both fill at the open with
    slippage, rounded to the paisa by slippage.fill_price, so the two final
    equities should agree; the gap printed is what remains.

This file does not modify the production engine. It re-implements the loop locally
so that results/ is untouched.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config
from config import read_table  # the one CSV/parquet reader: config.read_table
from numerics import rolling_std  # platform-identical variance: results/numerics.py

# Inlined from engine_core.precompute so this script does not need lightgbm.
VOL_WIN = 60
def precompute(px, vol_win=VOL_WIN):
    return {"vol": rolling_std(px.pct_change(), vol_win) * np.sqrt(252)}

try:
    from qbeast_in_charges import (Broker, Exchange, Product, Segment,
                                   Side as QSide, compute_leg_charges)
    from decimal import Decimal

    def calc_tc(price, qty, side):
        if price <= 0 or qty <= 0:
            return 0.0
        bd = compute_leg_charges(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                                 QSide.BUY if side == "BUY" else QSide.SELL,
                                 Decimal(str(round(price, 2))), Decimal(str(round(qty, 4))),
                                 Exchange.NSE)
        return float(bd.total)
except Exception as _e:
    # No fallback. A flat 0.11% here once replaced the charge library without a
    # word whenever its import failed, which moves every cost figure by about 9%.
    raise ImportError(
        f"qbeast_in_charges could not be imported ({type(_e).__name__}: {_e}). "
        f"calc_tc has no fallback rate; fix the import.") from _e

REBAL = 20
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = config.TOP_N, config.BUFFER
# SLIPPAGE comes from slippage.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from slippage import SLIPPAGE, fill_price  # noqa: E402
import capital_axis as _capital_axis  # noqa: E402
# THE DEFAULT, defined once in capital_axis.py. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
SAFETY = 0.98


def load_panel(cache_path):
    """The price/score panel every arm runs on. Shared with nt_verify.py so both
    scripts are provably reading the same input. cache_path selects the universe
    and is required: until 2026-09-24 it defaulted to the retired 58's panel,
    which no longer exists."""
    p = read_table(cache_path, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    # Window from config.py so the reference re-implementation cuts on exactly
    # the same dates as the engine. A year cut here against a date cut there
    # would make nt_verify fail on rebalance COUNT for a reason unrelated to
    # sizing or execution.
    bd = px.index[(px.index >= config.BT_START_DATE)
                  & (px.index <= config.BT_END_DATE)]
    return px, op, sc, bd, precompute(px), px / px.shift(20) - 1


# ---------------------------------------------------------------------------
# SIZING AND EXPOSURE MODE -- must mirror nt_strategy and test_exposure exactly
# ---------------------------------------------------------------------------
# This module is the REFERENCE side that nt_verify compares the port against. If
# it stayed on inverse-vol while the port ran pro-vol, every pro-vol arm would
# fail verification for a reason that has nothing to do with the port. Same guard
# (vol > 0.01), same zero on failure, same normalisation, same fallback.
# PASSED PER CALL, NOT SET AS A MODULE GLOBAL. run() already takes its other
# switches as keyword arguments; sizing and mode
# now join them. The globals they replace were process-wide, so a value
# left behind by one arm silently applied to the next, and asserting the global had
# been set never proved the run used it. See nt_strategy.py for the same change.
DEFAULT_SIZING = "invvol"
DEFAULT_MODE = "breadth"


def run(px, op, sc, dates, pc, mom20, holdings_out=None,
        sizing: str = DEFAULT_SIZING, mode: str = DEFAULT_MODE, applied_out=None,
        rebal: int = None, drawdown_stop=None, stop_events_out=None, dd_overlay=None,
        buy_shortfall: str = None, fills_out=None):
    """`holdings_out`, when a dict is passed, is filled with
    {rebalance_date: {symbol: qty}} -- the holdings standing at each decision, which
    is the same quantity the port records in strat.holdings_log and the same one
    the reference engine's daily_holdings file reports. It is an out-parameter
    rather than an extra return value so existing three-value callers keep
    working.

    `drawdown_stop` runs the stop of v5/v6 through results/drawdown_stop.py, the
    state machine the engine and the port also run; `stop_events_out`, a list,
    receives its events. Both None for the core arms, which then run the loop
    exactly as before.

    `dd_overlay`, a dd_axis.DDLimit, runs the drawdown-limit axis through
    results/drawdown_overlay.py, the class the engine and the port also run. None,
    the default, runs none of its code.

    `buy_shortfall`, "trim" or "refuse", is what a buy cash cannot fully pay for
    does, as in the engine (buy_shortfall.py). None reads buy_shortfall.selected().

    `fills_out`, a list, receives one row per fill in the port's strat.fills
    shape (date, action, symbol, qty, price). nt_verify compares it with the
    port's strat.fills."""
    import buy_shortfall as _bsf
    _shortfall = _bsf.selected() if buy_shortfall is None else buy_shortfall

    def _fill(dt, action, s, q, pr):
        if fills_out is not None:
            fills_out.append({"date": dt, "action": action, "symbol": s,
                              "qty": int(q), "price": float(pr)})

    def _afford(q, pr):
        """(q, charges) for a buy of q at fill price pr, cut to what cash pays for
        under trim; q is 0 when the buy is refused."""
        if cash >= q * pr:
            tc = calc_tc(pr, q, "BUY")
            if cash >= q * pr + tc:
                return q, tc
        if _shortfall != "trim":
            return 0, 0.0
        q, _, tc, _ = _bsf.trim(q, cash, lambda n: pr, lambda p_, n: calc_tc(p_, n, "BUY"))
        return q, tc

    # THE CADENCE, AS AN ARGUMENT. REBAL stays the module DEFAULT and is never
    # reassigned: module_state.py records that rebal_cadence_sweep.py:172 writes
    # test_exposure.REBAL and never restores it, and that every later step then
    # backtests on the wrong cadence with nothing saying so. A parameter cannot
    # leak into the next call; a global can, and did.
    #
    # THIS SIDE AND nt_strategy MUST MOVE TOGETHER. verify_v34_arms compares the
    # port against this reference at each rebalance date, so a cadence that
    # reached only one of them would fail the gate for a reason that has nothing
    # to do with the port -- the same trap the old SIZING global set.
    _reb = REBAL if rebal is None else int(rebal)
    if _reb < 1:
        raise ValueError(f"rebal must be >= 1, got {rebal!r}")
    if sizing not in ("invvol", "provol"):
        raise ValueError(f"sizing must be 'invvol' or 'provol', got {sizing!r}")
    if mode not in ("breadth", "none"):
        raise ValueError(f"mode must be 'breadth' or 'none', got {mode!r}")
    shares, cash = {}, float(_capital_axis.selected())
    eq, pending, n_trades, cum_tc = [], None, 0, 0.0
    _stop = drawdown_stop
    if _stop is not None:
        from drawdown_stop import StopState
        _st = StopState(_stop, _reb, len(dates))
        _EXIT = ({"_exposure": 0.0}, set())
    _dd = dd_overlay
    if _dd is not None:
        from drawdown_overlay import OverlayState
        _ds = OverlayState(_dd, _capital_axis.selected())
        _expo_last = 1.0

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        if _stop is not None:
            _st.begin_day()
            _held_before = dict(shares)

        if pending is not None:
            plan, keep = pending
            for s in list(shares.keys()):
                if s not in keep:
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        continue
                    pr = fill_price(pr, SLIPPAGE, False)
                    q = int(shares[s]); tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _fill(dt, "SELL", s, q, pr)
                    del shares[s]

            if plan:
                # Sized from the decision close: the book's value and each name's
                # close there, with slippage. This open sets only the fill price.
                invest_val = dec_val * plan["_exposure"] * SAFETY
                if _dd is not None:
                    invest_val *= _ds.entry_factor(plan["_exposure"])
                for s, w in plan.items():
                    if s == "_exposure" or s in shares:
                        continue
                    cp = dec_px.get(s, np.nan)
                    pr = opens.get(s, np.nan)
                    if np.isnan(cp) or cp <= 0 or np.isnan(pr) or pr <= 0:
                        continue
                    q = int((invest_val * w) // (cp * (1 + SLIPPAGE)))
                    pr = fill_price(pr, SLIPPAGE, True)
                    if q < 1:
                        continue
                    q, tc = _afford(q, pr)
                    if q < 1:
                        continue
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    _fill(dt, "BUY", s, q, pr)
                    shares[s] = shares.get(s, 0) + q
            pending = None
            if _stop is not None and (_st.exit_pending or _st.reentry_pending):
                _st.after_fills(i, shares, _held_before,
                                lambda k: pd.Timestamp(dates[k]).date())

        # THE DRAWDOWN-LIMIT ORDER, after the arm's fills: the engine's sequence
        # (results/test_exposure.py), without the cap, tax or impact this copy
        # never models.
        if _dd is not None and _ds.order is not None:
            _ord = _ds.order
            _before = {s: int(shares[s]) for s in _ord if s in shares}
            for s in sorted(_before):
                dq = _ord[s]
                if dq >= 0:
                    continue
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0:
                    continue
                pr = fill_price(pr, SLIPPAGE, False)
                q = min(-dq, int(shares[s]))
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _fill(dt, "SELL", s, q, pr)
                shares[s] -= q
                if shares[s] == 0:
                    del shares[s]
            _buys = [(s, _ord[s]) for s in sorted(_before) if _ord[s] > 0 and s in shares]
            _need = 0.0
            for s, dq in _buys:
                pr = opens.get(s, np.nan)
                if not (np.isnan(pr) or pr <= 0):
                    _need += dq * fill_price(pr, SLIPPAGE, True)
            _f = min(1.0, cash * SAFETY / _need) if _need > 0 else 1.0
            for s, dq in _buys:
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0:
                    continue
                pr = fill_price(pr, SLIPPAGE, True)
                q = int(dq * _f)
                if q < 1:
                    continue
                tc = calc_tc(pr, q, "BUY")
                if cash < q * pr + tc:
                    continue
                cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                _fill(dt, "BUY", s, q, pr)
                shares[s] += q
            _ds.cancel()

        _grid = i % _reb == 0 and i < len(dates) - 1
        _reentry = False
        if _grid and _stop is not None and _st.state != "IN":
            def _breadth():
                _m = mom20.loc[dt].dropna()
                return float((_m > 0).mean()) if len(_m) else 1.0
            _grid = _reentry = _st.grid_allows_order(i, _breadth)
        if _grid:
            m = mom20.loc[dt].dropna()
            expo = float((m > 0).mean()) if len(m) else 1.0
            expo = 1.0 if mode == "none" else max(0.0, min(1.0, expo))
            if _dd is not None:
                _expo_last = expo     # the engine's expo_log[-1]
            if applied_out is not None:
                applied_out["mode"] = mode
            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            if len(s_) >= TOP_N:
                rk = s_.sort_values(ascending=False)
                top, keep = list(rk.index[:TOP_N]), set(rk.index[:BUFFER])
                # Recorded at the same point in the sequence as the port's
                # holdings_log: the decision is going ahead, and these are the
                # positions standing when it is taken.
                if holdings_out is not None:
                    holdings_out[dt] = {s: int(q) for s, q in shares.items() if q}
                v = pc["vol"].loc[dt]
                w = {}
                for s in top:
                    vs = v.get(s, np.nan)
                    ok = (not np.isnan(vs)) and vs > 0.01
                    if not ok:
                        w[s] = 0.0
                    elif sizing == "provol":
                        w[s] = vs
                    else:
                        w[s] = 1.0 / vs
                tot = sum(w.values())
                w = ({s: w[s] / tot for s in top} if tot > 0
                     else {s: 1.0 / len(top) for s in top})
                if applied_out is not None:
                    applied_out["sizing"] = sizing

                w["_exposure"] = expo
                pending = (w, keep)
            if _reentry:
                _st.after_reentry_order(pending is not None)

        mtm = sum(q * prices[s] for s, q in shares.items()
                  if not np.isnan(prices.get(s, np.nan)))
        if _stop is not None:
            if _st.at_close(i, dt, cash + mtm, pending is not None, bool(shares),
                            i == len(dates) - 1) == "exit":
                pending = _EXIT
            if stop_events_out is not None:
                stop_events_out.extend(_st.rows(dt, cash + mtm))
        if _dd is not None:
            _ds.at_close(dt, cash + mtm, mtm, shares, i == len(dates) - 1, _expo_last)
        eq.append(cash + mtm)
        dec_val, dec_px = cash + mtm, prices

    return pd.Series(eq, index=dates), n_trades, cum_tc


if __name__ == "__main__":
    # Never hardcode the port's equity here: it goes stale the moment the port
    # changes, and a stale number in a verdict is how this project has been misled
    # before. Run it and read the result.
    import nt_run
    from universes.registry import CERTIFIED, argv_universes, check_tags
    _picked = check_tags(argv_universes(sys.argv), nt_run.UNIVERSES)
    _tag = _picked[-1] if _picked else CERTIFIED[0]
    _strat = nt_run.run(str(config.BT_START_DATE.date()), str(config.BT_END_DATE.date()),
                        universe=_tag)
    NAUTILUS_EQUITY = _strat.daily_equity[-1]["equity"]

    px, op, sc, bd, pc, mom20 = load_panel(nt_run.UNIVERSES[_tag]["cache"])

    print("=" * 74)
    print("ATTRIBUTION TEST -- is the Nautilus gap the known sizing difference?")
    print("=" * 74)

    a_eq, a_n, a_tc = run(px, op, sc, bd, pc, mom20)

    yrs = (bd[-1] - bd[0]).days / 365.25
    def cagr(e): return ((e.iloc[-1] / _capital_axis.selected()) ** (1 / yrs) - 1) * 100

    print(f"\n  reference copy, fills at the open : Rs {a_eq.iloc[-1]:>12,.0f}  "
          f"CAGR {cagr(a_eq):5.2f}%  trades {a_n}")
    print(f"  NAUTILUS                          : Rs {NAUTILUS_EQUITY:>12,.0f}")
    gap = (NAUTILUS_EQUITY - a_eq.iloc[-1]) / a_eq.iloc[-1] * 100
    print(f"\n  reference -> Nautilus             : {gap:+6.2f}%")
