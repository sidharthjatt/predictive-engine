"""
tax_util.py -- after-tax CAGR. PARKED AND UNUSED, kept for when it can be applied
fairly.

WHY IT IS PARKED (2026-08-13)
    The arithmetic below is sound, but the comparison it produced was asymmetric:
    tax was charged to the strategy lines and not to the buy&hold or index lines,
    which have entirely different tax treatment. A 20-day-churn strategy realises
    everything at 20% STCG; an equal-weight buy&hold realises once after seven
    years at 12.5% LTCG. Charging one and not the other overstates the strategy's
    disadvantage by the whole gap between those regimes.

    Applying tax fairly therefore requires giving the benchmark lines LTCG
    treatment -- a deferred single realisation at the end of the window, with its
    own rate and its own exemption -- which is a separate piece of work rather
    than a column. Until that exists, the reported figures are before-TC and
    after-TC only, and nothing here is imported by any chart.

-- original notes follow --

after-tax CAGR, shared by every universe's chart.

REPORTED ALONGSIDE, NEVER INSTEAD OF. Before-tax is the standard convention for
comparing strategies, because tax depends on the investor: their slab, their
other gains, losses available to offset, and whether they hold personally,
through a company, or inside a fund. The official number stays before-tax. This
is a third column so a reader can see the size of the gap rather than guess it.

WHY THE FULL SHORT-TERM RATE APPLIES TO EVERYTHING
    Every rebalance is 20 days. No position can reach the 12-month threshold for
    long-term treatment, so 100% of gains are short-term and the 20% STCG rate on
    listed Indian equity applies to all of them. That is a structural consequence
    of a 20-day rebalance, not a modelling assumption.

WHAT IS AND IS NOT MODELLED
    Modelled: FIFO lot matching per symbol, transaction costs deducted from the
    gain before tax, losses offsetting gains inside the same Indian financial
    year (1 April to 31 March).
    Not modelled: carry-forward of a net loss into the following year (it needs a
    filed return and is capped), surcharge and cess above the base rate, and any
    set-off against gains from outside this portfolio. The first omission makes
    this reading conservative; the second makes it optimistic for high earners.

This module lives in one place so the 58/74 chart and the MidCap150 chart cannot
drift apart on the tax arithmetic.
"""
from pathlib import Path

import pandas as pd

STCG_RATE = 0.20        # India, short-term capital gains on listed equity


def _cagr(s):
    y = (s.index[-1] - s.index[0]).days / 365.25
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1) * 100


def realised_pnl(path):
    """Per-SELL realised profit, FIFO against that symbol's earlier BUYs.

    Read from the engine's own trade log, so tax is computed on the trades that
    actually happened rather than on a reconstruction of them. Returns None when
    the log does not exist, and the caller reports the column as unavailable
    rather than silently as zero.
    """
    if not Path(path).exists():
        return None
    tr = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
    lots, rows = {}, []
    for _, t in tr.iterrows():
        sym, q, px = t["symbol"], int(t["qty"]), float(t["price"])
        if t["action"] == "BUY":
            lots.setdefault(sym, []).append([q, px])
            continue
        gain, need = 0.0, q
        while need > 0 and lots.get(sym):
            lot = lots[sym][0]
            take = min(need, lot[0])
            gain += take * (px - lot[1])
            lot[0] -= take
            need -= take
            if lot[0] == 0:
                lots[sym].pop(0)
        rows.append({"date": t["date"], "pnl": gain - float(t["tc"])})
    return pd.DataFrame(rows)


def after_tax(eq_series, pnl):
    """(CAGR after TC and tax, total tax paid) for one equity curve.

    Tax is deducted from the realised path on the day it is incurred, exactly as
    a transaction cost is, so the drag compounds the way it would in practice.
    """
    if pnl is None or pnl.empty:
        return None, 0.0
    g = pnl.copy()
    # Indian financial year: 1 April to 31 March.
    g["fy"] = g["date"].dt.year - (g["date"].dt.month < 4).astype(int)
    tax_by_date = {}
    for _fy, grp in g.groupby("fy"):
        running = 0.0
        for _, row in grp.sort_values("date").iterrows():
            prev = running
            running += row["pnl"]
            # Tax only the increase in the year's cumulative POSITIVE gains, so a
            # loss reduces the liability but never creates a refund.
            due = max(running, 0.0) * STCG_RATE - max(prev, 0.0) * STCG_RATE
            if abs(due) > 1e-9:
                tax_by_date[row["date"]] = tax_by_date.get(row["date"], 0.0) + due
    tax = pd.Series(tax_by_date).reindex(eq_series.index).fillna(0.0)
    r = eq_series.pct_change().fillna(0.0) - (tax / eq_series.shift(1)).fillna(0.0)
    return _cagr((1 + r).cumprod() * eq_series.iloc[0]), float(tax.sum())
