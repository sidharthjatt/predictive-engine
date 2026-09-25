"""bh_held.py -- the investable buy & hold: equal-rupee lots bought once, never rebalanced.

One construction, two endings, used by bh_lots_after_tax.py and by
v34_common.run_arm so both report the same numbers:

    headline      the lots are held to the end and marked to market. Nothing is
                  sold, so no gain is realised, no capital-gains tax is due and no
                  sell charge is paid. This is the taxed buy & hold's headline
                  figure (owner's decision, 2026-09-25: no forced sale at the end,
                  for the strategy or for buy & hold).
    last_day      "sold on the last day": every lot is sold at the last session's
                  open (its close where the open is missing) less slippage, the
                  same calc_tc sell charge the strategy pays is deducted, and the
                  realised gain is taxed with tax_util.tax_for_fy for the financial
                  year of that session -- the document's netting and full annual
                  exemption, nothing else.

The purchase is the one bh_lots_after_tax.py has always made: every symbol priced
on the first session gets an equal rupee share of START_CAPITAL, bought at that
session's open plus slippage with the BUY charge. The untaxed published buy & hold
(`px.pct_change().mean(axis=1)`, a costless daily-rebalanced index) is a different
construction and stays the reference line.
"""
import numpy as np

import tax_util as T
from test_exposure import calc_tc, SLIPPAGE, START_CAPITAL


def held_lots(px, op, bd):
    """-> dict(eq_headline, eq_last_day, detail) for the equal-rupee held basket."""
    d0, dN = bd[0], bd[-1]
    o0 = op.loc[d0]
    syms = [s for s in o0.index if not np.isnan(o0[s]) and o0[s] > 0]
    per = START_CAPITAL / len(syms)
    shares, cash, buy_tc = {}, START_CAPITAL, 0.0
    for s in syms:
        pr = float(o0[s]) * (1 + SLIPPAGE)
        q = int(per // pr)
        if q < 1:
            continue
        tc = calc_tc(pr, q, "BUY")
        if cash < q * pr + tc:
            continue
        cash -= q * pr + tc
        buy_tc += tc
        shares[s] = (q, pr)
    held = px.loc[bd, list(shares)].ffill()
    qty = np.array([shares[s][0] for s in shares], dtype=float)
    eq_headline = (held * qty).sum(axis=1) + cash

    # THE LAST-DAY SALE, at the last session's open with the usual slippage.
    gain = proceeds = sell_tc = 0.0
    oN = op.loc[dN]
    for s, (q, bp) in shares.items():
        pr = float(oN.get(s, np.nan))
        if np.isnan(pr) or pr <= 0:
            pr = float(px.loc[dN, s])
        pr *= (1 - SLIPPAGE)
        proceeds += q * pr
        sell_tc += calc_tc(pr, q, "SELL")
        gain += q * (round(pr, 2) - round(bp, 2))   # section 3(C): price difference only
    held_days = (dN - d0).days
    fy = T.financial_year(dN)
    reg = T.regime_of(dN)
    b = dict.fromkeys(T.BUCKETS, 0.0)
    b[("long_" if held_days >= T.LTCG_HOLD_DAYS else "short_") + reg] = gain
    tx = T.tax_for_fy(fy, b)
    eq_last_day = eq_headline.copy()
    eq_last_day.iloc[-1] = cash + proceeds - sell_tc - tx["total_tax"]
    return {
        "eq_headline": eq_headline,
        "eq_last_day": eq_last_day,
        "shares": shares,
        "detail": dict(names=len(shares), held_days=held_days, fy=T.fy_label(fy),
                       regime=reg, gain=gain, tax=tx["total_tax"],
                       exemption=tx["exemption"], residual_cash=cash,
                       proceeds=proceeds, sell_tc=sell_tc, buy_tc=buy_tc,
                       tax_row=tx),
    }
