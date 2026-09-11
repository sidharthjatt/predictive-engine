"""
nt_attribution.py -- explain the gap between the reference engine and Nautilus.

THE QUESTION
    The reference engine ends at Rs 31,01,677 and the Nautilus port at Rs 31,90,675
    -- a gap of about 2.9%, or 0.43 points of CAGR. Is that gap the KNOWN structural
    difference, or is it a bug?

THE KNOWN DIFFERENCE
    Reference engine: decides at the close of day t, then sizes at the OPEN of t+1.
        It sells first, revalues the portfolio at t+1 open prices, and only then
        computes  q = (invest_value * weight) // open_price(t+1).
    Nautilus: a strategy must submit at the close of t, so quantity has to come from
        day t's close prices and the portfolio value at day t's close.
    The two differ by the overnight gap.

THE TEST
    Run the reference engine twice on identical data and identical scores:
        ARM A -- sizing at the next open   (this is the official system)
        ARM B -- sizing at the decision close (what Nautilus is forced to do)
    Nothing else changes. If ARM B lands close to the Nautilus result, the gap is
    attributed to sizing timing. If ARM B stays near ARM A, the gap is something
    else and must be found.

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

# Inlined from engine_core.precompute so this script does not need lightgbm.
VOL_WIN = 60
def precompute(px, vol_win=VOL_WIN):
    return {"vol": px.pct_change().rolling(vol_win).std() * np.sqrt(252)}

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
except Exception:
    def calc_tc(price, qty, side):
        return price * qty * 0.0011

REBAL = 20
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = config.TOP_N, config.BUFFER
SLIPPAGE = 0.0015
START_CAPITAL = 1_000_000
SAFETY = 0.98


TICK = 0.05
TICK_MODE = "nse"          # "nse" = the dated exchange rule; "fixed" = uniform TICK

# Effective dates from NSE/CMTR/62174 and NSE/CMTR/67133. See the block in
# nautilus/nt_data.py and the circular text in diagnostics/.
_T2024 = pd.Timestamp("2024-06-10")
_T2025 = pd.Timestamp("2025-04-15")


def set_tick(value):
    """Match the grid nt_data is loading with. The reconciliation run drops both to
    a uniform 0.01 to separate tick quantization from any real difference."""
    global TICK
    TICK = float(value)


def set_tick_mode(mode):
    global TICK_MODE
    TICK_MODE = mode


def nse_tick(ref_price, date):
    """The exchange tick in force for `ref_price` on `date`. Mirrors nt_data."""
    if date < _T2024:
        return 0.05
    if ref_price < 250:
        return 0.01
    if date < _T2025:
        return 0.05
    if ref_price <= 1000:
        return 0.05
    if ref_price <= 5000:
        return 0.10
    if ref_price <= 10000:
        return 0.50
    if ref_price <= 20000:
        return 1.00
    return 5.00


def _tick(x, date=None, ref=None):
    """Snap to the grid in force. In "nse" mode the grid depends on the date and
    the price band; in "fixed" mode it is the uniform TICK."""
    if TICK_MODE == "nse" and date is not None:
        t = nse_tick(float(x) if ref is None else float(ref), date)
        return round(round(float(x) / t) * t, 4)
    return round(round(float(x) / TICK) * TICK, 4)


def load_panel(cache_path=None):
    """The price/score panel every arm runs on. Shared with nt_verify.py so both
    scripts are provably reading the same input. cache_path selects the universe;
    the 58 panel stays the default so existing callers are unchanged."""
    if cache_path is None:
        cache_path = ROOT / "results" / "metrics" / "v5_expanding_cache.csv"
    p = pd.read_csv(cache_path, parse_dates=["date"])
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
# switches as keyword arguments (size_at_close, tick_round, value_at_open); sizing
# and mode now join them. The globals they replace were process-wide, so a value
# left behind by one arm silently applied to the next, and asserting the global had
# been set never proved the run used it. See nt_strategy.py for the same change.
DEFAULT_SIZING = "invvol"
DEFAULT_MODE = "breadth"


def run(px, op, sc, dates, pc, mom20, size_at_close: bool, tick_round: bool = False,
        value_at_open: bool = False, holdings_out=None,
        sizing: str = DEFAULT_SIZING, mode: str = DEFAULT_MODE, applied_out=None,
        rebal: int = None):
    """`holdings_out`, when a dict is passed, is filled with
    {rebalance_date: {symbol: qty}} -- the holdings standing at each decision, which
    is the same quantity the port records in strat.holdings_log and the same one
    daily_holdings_58.csv reports. It is an out-parameter rather than an extra
    return value so existing three-value callers keep working."""
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
    shares, cash = {}, float(START_CAPITAL)
    eq, pending, n_trades, cum_tc = [], None, 0, 0.0

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]

        if pending is not None:
            plan, keep = pending
            for s in list(shares.keys()):
                if s not in keep:
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        continue
                    pr *= (1 - SLIPPAGE)
                    if tick_round:
                        pr = _tick(pr, dt)
                    q = int(shares[s]); tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    del shares[s]

            if plan:
                if size_at_close:
                    # ARM B: quantities were already fixed on the decision day.
                    for s, q in plan.items():
                        if s == "_exposure" or s in shares or q < 1:
                            continue
                        pr = opens.get(s, np.nan)
                        if np.isnan(pr) or pr <= 0:
                            continue
                        pr *= (1 + SLIPPAGE)
                        if tick_round:
                            pr = _tick(pr, dt)
                        tc = calc_tc(pr, q, "BUY")
                        if cash < q * pr + tc:
                            continue
                        cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                        shares[s] = shares.get(s, 0) + q
                else:
                    # ARM A: size now, at this morning's open.
                    vp = opens if value_at_open else prices
                    port_val = sum(q * vp[s] for s, q in shares.items()
                                   if not np.isnan(vp.get(s, np.nan))) + cash
                    invest_val = port_val * plan["_exposure"] * SAFETY
                    for s, w in plan.items():
                        if s == "_exposure" or s in shares:
                            continue
                        pr = opens.get(s, np.nan)
                        if np.isnan(pr) or pr <= 0:
                            continue
                        pr *= (1 + SLIPPAGE)
                        if tick_round:
                            pr = _tick(pr, dt)
                        q = int((invest_val * w) // pr)
                        if q < 1 or cash < q * pr:
                            continue
                        tc = calc_tc(pr, q, "BUY")
                        if cash < q * pr + tc:
                            continue
                        cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                        shares[s] = shares.get(s, 0) + q
            pending = None

        if i % _reb == 0 and i < len(dates) - 1:
            m = mom20.loc[dt].dropna()
            expo = float((m > 0).mean()) if len(m) else 1.0
            expo = 1.0 if mode == "none" else max(0.0, min(1.0, expo))
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

                if size_at_close:
                    pv = sum(q * prices[s] for s, q in shares.items()
                             if not np.isnan(prices.get(s, np.nan))) + cash
                    iv = pv * expo * SAFETY
                    plan = {}
                    for s in top:
                        cp = prices.get(s, np.nan)
                        plan[s] = int((iv * w[s]) // cp) if (not np.isnan(cp) and cp > 0) else 0
                    plan["_exposure"] = expo
                    pending = (plan, keep)
                else:
                    w["_exposure"] = expo
                    pending = (w, keep)

        mtm = sum(q * prices[s] for s, q in shares.items()
                  if not np.isnan(prices.get(s, np.nan)))
        eq.append(cash + mtm)

    return pd.Series(eq, index=dates), n_trades, cum_tc


if __name__ == "__main__":
    # Never hardcode the port's equity here: it goes stale the moment the port
    # changes, and a stale number in a verdict is how this project has been misled
    # before. Run it and read the result.
    import nt_run
    _strat = nt_run.run(str(config.BT_START_DATE.date()), str(config.BT_END_DATE.date()))
    NAUTILUS_EQUITY = _strat.daily_equity[-1]["equity"]

    px, op, sc, bd, pc, mom20 = load_panel()

    print("=" * 74)
    print("ATTRIBUTION TEST -- is the Nautilus gap the known sizing difference?")
    print("=" * 74)

    a_eq, a_n, a_tc = run(px, op, sc, bd, pc, mom20, size_at_close=False)
    b_eq, b_n, b_tc = run(px, op, sc, bd, pc, mom20, size_at_close=True)
    c_eq, c_n, c_tc = run(px, op, sc, bd, pc, mom20, size_at_close=True, tick_round=True)
    # ARM D: the reference engine with the port's two documented differences applied
    # -- portfolio valued at the execution day's OPEN rather than its close, and
    # prices on the 0.05 tick grid the Nautilus instrument declares. This is the
    # baseline the port should reconcile against; see nt_verify.py.
    d_eq, d_n, d_tc = run(px, op, sc, bd, pc, mom20, size_at_close=False,
                          value_at_open=True, tick_round=True)

    yrs = (bd[-1] - bd[0]).days / 365.25
    def cagr(e): return ((e.iloc[-1] / START_CAPITAL) ** (1 / yrs) - 1) * 100

    print(f"\n  ARM A  size at next open  (official)  : Rs {a_eq.iloc[-1]:>12,.0f}  "
          f"CAGR {cagr(a_eq):5.2f}%  trades {a_n}")
    print(f"  ARM B  size at decision close         : Rs {b_eq.iloc[-1]:>12,.0f}  "
          f"CAGR {cagr(b_eq):5.2f}%  trades {b_n}")
    print(f"  ARM C  + prices snapped to 0.05 ticks : Rs {c_eq.iloc[-1]:>12,.0f}  "
          f"CAGR {cagr(c_eq):5.2f}%  trades {c_n}")
    print(f"  ARM D  value at open + 0.05 ticks     : Rs {d_eq.iloc[-1]:>12,.0f}  "
          f"CAGR {cagr(d_eq):5.2f}%  trades {d_n}")
    print(f"  NAUTILUS                              : Rs {NAUTILUS_EQUITY:>12,.0f}")

    gap_ab = (b_eq.iloc[-1] - a_eq.iloc[-1]) / a_eq.iloc[-1] * 100
    gap_bn = (NAUTILUS_EQUITY - b_eq.iloc[-1]) / b_eq.iloc[-1] * 100
    gap_bc = (c_eq.iloc[-1] - b_eq.iloc[-1]) / b_eq.iloc[-1] * 100
    gap_cn = (NAUTILUS_EQUITY - c_eq.iloc[-1]) / c_eq.iloc[-1] * 100
    gap_an = (NAUTILUS_EQUITY - a_eq.iloc[-1]) / a_eq.iloc[-1] * 100

    print(f"\n  A -> B  (the sizing change alone)     : {gap_ab:+6.2f}%")
    print(f"  A -> Nautilus (total gap)             : {gap_an:+6.2f}%")
    print(f"  B -> C  (tick rounding alone)         : {gap_bc:+6.2f}%")
    print(f"  C -> Nautilus (unexplained remainder) : {gap_cn:+6.2f}%")

    print("\n" + "=" * 74)
    if abs(gap_cn) < 1.0:
        print("  VERDICT: sizing timing and tick rounding together account for the")
        print("  gap. The port is explained.")
    elif abs(gap_cn) < abs(gap_an) / 2:
        print("  VERDICT: they explain most of it. A remainder is still open.")
    else:
        print("  VERDICT: NOT explained. Something else differs and must be found.")
    print("=" * 74)
