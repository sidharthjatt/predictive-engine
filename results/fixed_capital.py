"""
fixed_capital.py -- the figures of a fixed-capital run (fixed_axis.py), and its
basket and index under the same rule.

A fixed-capital run does not reinvest its profits, so CAGR understates it: the
equity grows by the base times each period's return, not by the equity times it.
The figures here are the ones that describe such a run. `base` is --capital.

    AvgAnnRet%          (end equity - base) / base / years
    Year% <y>           that calendar year's rupee P&L / base. A year's P&L runs
                        from the previous year's last close (the base, for the
                        first year) to its own last close, so base + the sum of
                        the yearly P&L is the end equity.
    MeanFullYear%       arithmetic mean of Year% over the full calendar years in
                        the window; FullYears names them
    MaxDD_Rs            the largest fall from a running peak, in rupees
    MaxDD_base%         the largest (equity - running peak) / base
    MaxInvested_base%   the highest held market value / base, with its date. For
                        the strategy: at an execution-day open, after that day's
                        buys (backtest_exposure's audit["fixed"]). For the basket
                        and the index: at a grid-day close, before that day's reset.
    CAGR%               shown, and labelled as understating a fixed-capital run

years is calendar days / 365.25, as engine_core.metrics() computes it.

THE BASKET AND THE INDEX UNDER THE SAME RULE. On each of the strategy's grid days
(every `rebal`-th session from the first, the days the strategy decides a
rebalance) the invested amount is reset to min(base, equity) at that day's close;
the rest is idle cash that earns nothing. Between resets the invested amount moves
with the line's daily return, so it compounds inside a period, as the strategy's
positions do. Two differences from the strategy are stated, not modelled:
  - the strategy's reset happens at the NEXT session's open, so the benchmarks'
    reset is one session earlier; both series are close-only;
  - the index is the universe's NSE price index file, without dividends.
The reset also brings an invested amount above the base back to the base, which
the strategy does not do to its held names.
"""
from decimal import Decimal, localcontext

import numpy as np
import pandas as pd

STRATEGY, BASKET, INDEX = "strategy", "basket", "index"

CAGR_LABEL = "CAGR% (understates a fixed-capital run)"


def years_of(eq):
    return (eq.index[-1] - eq.index[0]).days / 365.25


def full_years(index, w0=None, w1=None):
    """Calendar years the window covers from 1 January to 31 December."""
    w0 = pd.Timestamp(index[0] if w0 is None else w0)
    w1 = pd.Timestamp(index[-1] if w1 is None else w1)
    return [int(y) for y in sorted(set(index.year))
            if w0 <= pd.Timestamp(f"{y}-01-01") and w1 >= pd.Timestamp(f"{y}-12-31")]


def yearly_pnl(eq, base):
    """{year: rupee P&L}, each year from the previous year's last close; the first
    year from the base."""
    out, prev = {}, float(base)
    for y, g in eq.groupby(eq.index.year):
        out[int(y)] = float(g.iloc[-1]) - prev
        prev = float(g.iloc[-1])
    return out


def yearly_sum_check(eq, base):
    """Format check: base + the sum of the yearly P&L = the end equity, in Decimal.

    Each float converts to Decimal exactly, so the sum telescopes exactly. It
    checks the yearly table is complete and anchored at the base; it cannot catch
    an engine error, which `engine_tests.py fixed_capital`'s trade-log reconciliation does."""
    with localcontext() as ctx:
        ctx.prec = 400          # wide enough that no float's exact value is rounded
        vals = [Decimal(float(base))]
        prev = Decimal(float(base))
        for _, g in eq.groupby(eq.index.year):
            last = Decimal(float(g.iloc[-1]))
            vals.append(last - prev)
            prev = last
        return sum(vals) == Decimal(float(eq.iloc[-1]))


def max_invested(rows, base):
    """(MaxInvested_base%, date) from audit["fixed"] rows, or (None, None)."""
    if not rows:
        return None, None
    best = max(rows, key=lambda r: r["held_after"])
    return best["held_after"] / base * 100, pd.Timestamp(best["date"])


def figures(eq, base, line, label, invested=(None, None), w0=None, w1=None):
    """One row of fixed-capital figures for an equity series."""
    eq = eq.astype(float)
    ny = years_of(eq)
    yp = yearly_pnl(eq, base)
    fy = full_years(eq.index, w0, w1)
    gap = eq - eq.cummax()
    i_dd = int(np.argmin(gap.to_numpy()))
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100
    mi, mi_d = invested
    row = {"Line": line, "Config": label,
           "AvgAnnRet%": round((float(eq.iloc[-1]) - base) / base / ny * 100, 2),
           "MeanFullYear%": (round(float(np.mean([yp[y] / base * 100 for y in fy])), 2)
                             if fy else None),
           "FullYears": " ".join(str(y) for y in fy),
           "MaxDD_Rs": round(float(gap.min()), 2),
           "MaxDD_base%": round(float(gap.min()) / base * 100, 2),
           "MaxDD_trough": str(eq.index[i_dd].date()),
           "MaxInvested_base%": None if mi is None else round(mi, 2),
           "MaxInvested_date": None if mi_d is None else str(mi_d.date()),
           CAGR_LABEL: round(cagr, 2),
           "Base": round(float(base), 2),
           "FinalEquity": round(float(eq.iloc[-1]), 2),
           "Years": round(ny, 4)}
    return row


def year_rows(eq, base, line, label):
    """One row per calendar year: rupee P&L and that as % of base."""
    return [{"Line": line, "Config": label, "Year": y, "PnL_Rs": round(v, 2),
             "Year%": round(v / base * 100, 2)}
            for y, v in yearly_pnl(eq.astype(float), base).items()]


def fixed_curve(values, reset_mask, base, prior=None):
    """A line's equity under min(base, equity), reset at the closes in reset_mask.

    `values` is the line's daily value series on the run's dates, any scale.
    `prior` is its value the session before the first date; None means the line
    starts at the first date with no return on it. Returns (equity, held value
    at each reset close before the reset, as a Series on the reset dates)."""
    v = values.astype(float).to_numpy()
    reset = np.asarray(reset_mask, dtype=bool)
    eq = np.empty(len(v))
    pre = {}
    held = float(base)
    cash = 0.0
    last = float(v[0] if prior is None else prior)
    for t in range(len(v)):
        held *= v[t] / last
        last = v[t]
        eq[t] = held + cash
        if reset[t]:
            pre[values.index[t]] = held
            held = min(float(base), eq[t])
            cash = eq[t] - held
    return pd.Series(eq, index=values.index), pd.Series(pre, dtype=float)


def grid_mask(dates, rebal):
    """The strategy's grid days: backtest_exposure decides on i % rebal == 0,
    except the last session, on which no order can fill."""
    n = len(dates)
    return [(i % rebal == 0 and i < n - 1) for i in range(n)]


def index_values(u, dates):
    """The universe's NSE price index close, forward-filled onto `dates`, or None."""
    import config
    from pathlib import Path
    if getattr(u, "index_file", None) is None or not Path(u.index_file).exists():
        return None
    s = (config.read_price_csv(u.index_file)[["date", "close"]].dropna()
         .set_index("date")["close"].sort_index())
    ix = s.reindex(s.index.union(dates)).ffill().reindex(dates)
    return None if ix.isna().any() else ix.astype(float)


def benchmark_rows(bh, u, dates, base, rebal, w0=None, w1=None):
    """(figure rows, year rows, curves) for the basket and the index under the rule.

    `bh` is the run's compounded basket, base * cumprod(1 + daily mean return);
    its value the session before the window is the base."""
    mask = grid_mask(dates, rebal)
    rows, years, curves = [], [], {}
    lines = [(BASKET, "buy & hold equal-weight, fixed capital", bh, float(base))]
    ix = index_values(u, dates)
    if ix is not None:
        lines.append((INDEX, f"{getattr(u, 'index_name', 'index')} price index, fixed "
                             f"capital", ix, None))
    for line, label, ser, prior in lines:
        eq, pre = fixed_curve(ser, mask, base, prior)
        if len(pre):
            d = pre.idxmax()
            inv = (float(pre.max()) / base * 100, pd.Timestamp(d))
        else:
            inv = (None, None)
        rows.append(figures(eq, base, line, label, inv, w0, w1))
        years += year_rows(eq, base, line, label)
        curves[line] = eq
    return rows, years, curves


NOTES = (
    "Fixed capital: positions are sized from min(base, equity) at each rebalance "
    "open; profit above the base is held as idle cash at 0% and never used to buy; "
    "held names are not trimmed. CAGR understates such a run. The basket and the "
    "index are reset to min(base, equity) at the close of each of the strategy's "
    "grid days, one session before the strategy's own reset at the next open; the "
    "index is a price index without dividends.")
