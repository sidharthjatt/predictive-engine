"""
reports.py -- every report, chart and table written from a finished run.

Sections, in order:
  1. the cost report and its reconciliation (reconcile_costs)
  2. pipeline steps: tax_report, make_chart, make_combined_universes, make_daily_log
  3. cell and run summary lines (cell_lines, run_lines)
  4. reports run by hand through `run.py --report NAME [ARGS]`:
     readme_tax_tables, year_by_year, capital_ladder, cell_reports

The runs themselves are in backtest_runs.py; the dashboard in dashboard.py.
"""
import matplotlib
matplotlib.use("Agg")
import sys
from decimal import Decimal
from pathlib import Path
import numpy as np
import pandas as pd
import costs as _costs
from costs import SLIPPAGE
from costs import compute_leg_charges
from costs import Broker
from costs import Segment
from costs import Product
from costs import Side as QSide
from costs import Exchange
import csv
from settings import tax as _tax
import costs
from market_data import read_table
import json
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import market_data
import model
import settings
import portfolio as arm_reg
from settings import cadence
import warnings
from settings import REGISTRY
from settings import universe_axis
from settings import report_order
from settings import CERTIFIED as PAIR_CHART
from settings import list_dir
from settings import capital_axis as _capital_axis
from market_data import last_rows
from settings import has_pit
import argparse
import time
from settings import pit_variant
from settings import pit_refusal
from settings import gated

import io
import contextlib
import backtest_runs as engine_core
from portfolio import ARMS
from settings import impact_axis
from settings import pcap_axis
from portfolio import backtest_exposure
ROOT = Path(__file__).resolve().parent


# ======================================================================================
# COST REPORT AND RECONCILIATION. From results/cost_report.py (moved 2026-11-27).
# ======================================================================================
# cost_report -- charges, slippage and tax for one run, reconciled to the paisa.
#
# Called by backtest_runs.py for every (universe, arm) it audits, under every
# cadence, profile and tax setting, and by cost_reconcile_check.py for the gate. It
# reads the cost trail backtest_exposure records when its audit dict carries a
# "costs" key, and changes nothing the engine computes.
#
# WHAT IT WRITES, beside the daily_* files and named by the same artefact tag:
#     COSTS_<tag>.csv           one row per fill: reference price, fill price,
#                               quantity, slippage in rupees, each charge, total
#     COST_LOTS_<tag>.csv       one row per lot a sell closes: buy date, days held,
#                               short or long, old or new regime, the gain as the tax
#                               rules compute it (price difference only)
#     COST_TAX_YEARS_<tag>.csv  one row per financial year of the window: the four
#                               buckets, the netting, the exemption available and
#                               used, the tax at each rate, the total and the day it
#                               left cash. Tax columns are zero when tax is off.
#     COST_SUMMARY_<tag>.txt    the summary block run.py prints at the end of run.log
#
# THE SLIPPAGE MODEL. Both profiles use costs.py's flat rate: a BUY fills at the
# reference price times (1 + SLIPPAGE), a SELL at (1 - SLIPPAGE), SLIPPAGE = 0.0015,
# rounded to the paisa (costs.fill_price).
# The reference price is the execution day's open from the score panel (the adjusted
# price basis), or for the optional last-day sale the close where the open is
# missing. The size-sensitive term (costs.impact) runs only with run.py --impact
# (tradeable profile): a fill then pays SLIPPAGE + k x sqrt(qty / prior-20-session
# median volume), and the report shows the second part as "impact", apart from the
# flat slippage. Without --impact it is not run. The tradeable profile adds the
# participation cap (--cap replaces its value), which changes quantities, not the rate.
#
# THE CHARGES are costs.compute_leg_charges for Zerodha delivery
# equity on NSE, called exactly as portfolio.calc_tc calls it: on the fill price
# rounded to two decimals, per fill. The reconciliation requires the itemised total to
# equal the charge the engine deducted.
#
# RECONCILIATION (reconcile below). A run that fails any check raises
# CostReconciliationError naming the check, the first day and the gap:
#     cash      every day: opening cash + interest + sale proceeds - purchase cost -
#               charges - tax = closing cash, to the paisa, and each day opens at the
#               previous day's close
#     slippage  every fill: the model applied to the reference price and quantity
#               gives (fill - reference) x quantity, to the paisa; the itemised
#               charges equal the charge deducted; the fill matches the trades row
#     tax       every financial year: the rules applied to the per-lot gains give the
#               tax the run deducted, on the day it deducted it
#     totals    per-fill and per-year sums equal the run's totals and the summary

PAISA = 0.005
CHARGES = (("brokerage", "brokerage"), ("stt_ctt", "STT"), ("exchange_txn", "exchange transaction"),
           ("sebi", "SEBI turnover fee"), ("stamp_duty", "stamp duty"), ("ipft", "IPFT"),
           ("dp", "DP charge"), ("gst", "GST"))

# The tax reference document's own list of what the tax model does not do
# (data/reference/TAX_AND_CHARGES.docx, section 5), one line each.
TAX_LEAVES_OUT = (
    "No surcharge: it depends on the person's total income. The 4% cess is charged (since 2026-10-14).",
    "No basic exemption limit: the portfolio is taxed as if the person's other income used it up.",
    "Losses carry forward 8 years (since 2026-10-14), assuming every return is filed on time, which carry-forward requires.",
    "No s.112A grandfathering: no cost step-up to the 31-Jan-2018 value; the window starts in 2019, so nothing is affected.",
    "No advance tax: each year is paid as one lump sum on its assessment day, not in quarterly instalments.",
    "The LTCG exemption is really per person across all holdings; here the portfolio gets the whole of it.",
)


class CostReconciliationError(RuntimeError):
    """A cost figure does not reconcile. The message names the check, day and gap."""


def charge_breakdown(fill_price, qty, side, numpy_round=True):
    """{charge: rupees} for one fill, as portfolio.calc_tc computes the total."""
    # NUMPY SCALARS, AS IN THE ENGINE: its prices come out of a pandas row as
    # numpy float64, and round() on one can land a half-paisa the other way from
    # round() on a Python float (1607.585 -> 1607.58 against 1607.59). Rounding the
    # way the engine does is what makes the charge and the gain match it.
    # backtest_runs.held_lots prices in Python floats, so the buy & hold passes False.
    fill_price, qty = (np.float64(fill_price) if numpy_round else float(fill_price)), int(qty)
    if fill_price <= 0 or qty <= 0:
        return {k: 0.0 for k, _ in CHARGES} | {"total": 0.0}
    bd = compute_leg_charges(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                             QSide.BUY if side == "BUY" else QSide.SELL,
                             Decimal(str(round(fill_price, 2))), Decimal(str(round(qty, 4))),
                             Exchange.NSE)
    return {k: float(getattr(bd, k)) for k, _ in CHARGES} | {"total": float(bd.total)}


def _fail(check, date, gap, what):
    d = pd.Timestamp(date).date() if date is not None else "-"
    raise CostReconciliationError(f"COST RECONCILIATION FAILED -- {check}: first failure on "
                                  f"{d}, gap Rs {gap:+,.4f}. {what}")


def fills_frame(costs):
    """The per-fill table, with slippage and the itemised charges."""
    # IMPACT IS SPLIT FROM FLAT SLIPPAGE WHEN THE MODEL RAN (--impact). The engine
    # then records, per fill, k and the median volume the fill was priced against
    # (None where the model exempted it). The rate is recomputed here with
    # costs.impact, impact_rs = reference x rate x qty, and slippage_rs keeps
    # only the flat part. Without the model there are no such keys and no columns.
    has_imp = any("impact_median" in r for r in costs["fills"])
    f = pd.DataFrame(costs["fills"], columns=["date", "side", "symbol", "qty", "reference_price",
                                              "fill_price", "charges", "kind"]
                     + (["impact_k", "impact_median"] if has_imp else []))
    if f.empty:
        for k, _ in CHARGES:
            f[k] = []
        f["slippage_rs"] = []
        f["charges_total"] = []
        return f
    sign = np.where(f["side"] == "BUY", 1.0, -1.0)
    f["slippage_rs"] = (f["fill_price"] - f["reference_price"]) * f["qty"] * sign
    if has_imp:
        f["impact_rate"] = [0.0 if (m is None or m != m) else _costs.impact(int(q), float(m), float(k))
                            for q, m, k in zip(f["qty"], f["impact_median"], f["impact_k"])]
        f["impact_rs"] = f["reference_price"] * f["impact_rate"] * f["qty"]
        f["slippage_rs"] = f["slippage_rs"] - f["impact_rs"]
    br = [charge_breakdown(p, q, s) for p, q, s in zip(f["fill_price"], f["qty"], f["side"])]
    for k, _ in CHARGES:
        f[k] = [b[k] for b in br]
    f["charges_total"] = [b["total"] for b in br]
    return f


def replay_ledger(fills, dates):
    """Replay the tax rules on the recorded fills, in the engine's order.

    -> (lots frame, {date: tax due before fills}, {date: tax due after fills},
        {fy: date assessed}). costs.Ledger is the engine's own class, fed the
    same prices (the fill rounded to two decimals) in the same order."""
    led = _costs.Ledger(dates)
    pre, post, when = {}, {}, {}
    by_day = {d: g for d, g in fills.groupby("date")} if len(fills) else {}
    for d in dates:
        before = set(led.assessed)
        x = led.due_on(d)
        if x:
            pre[d] = x
        for fy in led.assessed - before:
            when[fy] = d
        g = by_day.get(d)
        if g is not None:
            for r in g.itertuples(index=False):
                if r.side == "BUY":
                    led.buy(r.symbol, int(r.qty), round(np.float64(r.fill_price), 2), d)
                else:
                    led.sell(r.symbol, int(r.qty), round(np.float64(r.fill_price), 2), d)
        before = set(led.assessed)
        x = led.due_on(d, after_fills=True)
        if x:
            post[d] = x
        for fy in led.assessed - before:
            when[fy] = d
    lots = pd.DataFrame(led.rows, columns=["symbol", "buy_date", "sell_date", "qty", "buy_price",
                                           "sell_price", "held_days", "is_long", "regime", "fy",
                                           "gain"])
    return lots, pre, post, when


def tax_years(lots, dates, when, tax_on):
    """One row per financial year of the window, with every intermediate the rules use."""
    buckets = _costs.realized_buckets(lots)
    # ONE PASS IN ASCENDING YEARS, so losses carry forward as the engine's ledger
    # carries them (costs.assess_years).
    assessed = _costs.assess_years(buckets, {_costs.financial_year(d) for d in dates})
    rows = []
    for fy in sorted({_costs.financial_year(d) for d in dates}):
        b = buckets.get(fy, dict.fromkeys(_costs.BUCKETS, 0.0))
        t = assessed[fy]
        r = {"fy": _costs.fy_label(fy), "tax": "on" if tax_on else "off",
             **{k: b[k] for k in _costs.BUCKETS},
             "stcg_net": t["stcg_net"], "stcg_taxable": t["stcg_taxable"],
             "stcg_old_taxed": t["stcg_old_taxed"], "stcg_old_rate": _costs.STCG_RATE["old"],
             "stcg_old_tax": t["stcg_old_taxed"] * _costs.STCG_RATE["old"],
             "stcg_new_taxed": t["stcg_new_taxed"], "stcg_new_rate": _costs.STCG_RATE["new"],
             "stcg_new_tax": t["stcg_new_taxed"] * _costs.STCG_RATE["new"],
             "stcg_tax": t["stcg_tax"],
             "stcl_set_off_vs_ltcg": t["stcl_set_off_vs_ltcg"],
             "bf_short_used": t["bf_short_used"], "bf_long_used": t["bf_long_used"],
             "cf_short_added": t["cf_short_added"], "cf_long_added": t["cf_long_added"],
             "ltcg_net": t["ltcg_net"], "ltcg_after_set_off": t["ltcg_after_set_off"],
             "exemption_available": t["exemption"],
             "exemption_used": t["exemption_used"],
             "ltcg_taxable": t["ltcg_taxable"],
             "ltcg_old_taxed": t["ltcg_old_taxed"], "ltcg_old_rate": _costs.LTCG_RATE["old"],
             "ltcg_old_tax": t["ltcg_old_taxed"] * _costs.LTCG_RATE["old"],
             "ltcg_new_taxed": t["ltcg_new_taxed"], "ltcg_new_rate": _costs.LTCG_RATE["new"],
             "ltcg_new_tax": t["ltcg_new_taxed"] * _costs.LTCG_RATE["new"],
             "ltcg_tax": t["ltcg_tax"], "cess": t["cess"], "total_tax": t["total_tax"],
             "deducted_on": when.get(fy), "net_loss_year": (t["stcg_net"] + t["ltcg_net"]) < 0}
        if not tax_on:
            for k in ("stcg_old_tax", "stcg_new_tax", "stcg_tax", "exemption_used",
                      "ltcg_old_tax", "ltcg_new_tax", "ltcg_tax", "cess", "total_tax"):
                r[k] = 0.0
            r["deducted_on"] = None
        rows.append(r)
    return pd.DataFrame(rows)


def reconcile_costs(costs, trades, dates, start_capital, engine_tc, engine_tax, tax_on, engine_lots=None):
    """Run the four checks. -> (fills, lots, years, days). Raises on the first failure."""
    fills = fills_frame(costs)
    days = pd.DataFrame(costs["days"])
    # --- trades rows: the cost trail must describe the same fills -------------
    t = pd.DataFrame(trades)
    if len(t) != len(fills):
        _fail("totals", None, float(len(fills) - len(t)),
              f"{len(fills)} fills in the cost trail against {len(t)} trades rows")
    for i in range(len(fills)):
        a, b = fills.iloc[i], t.iloc[i]
        if a["date"] != b["date"] or a["side"] != b["action"] or a["symbol"] != b["symbol"] \
                or a["qty"] != b["qty"]:
            _fail("totals", a["date"], float(a["qty"] - b["qty"]),
                  f"fill {i} ({a['side']} {a['symbol']}) is not the fill in trades row {i}")
        if round(np.float64(a["fill_price"]), 2) != b["price"]:
            _fail("slippage", a["date"], float(round(np.float64(a["fill_price"]), 2) - b["price"]),
                  f"fill {i} ({a['side']} {a['symbol']}): fill price differs from its trades row")
        if round(np.float64(a["charges"]), 2) != b["tc"]:
            _fail("slippage", a["date"], float(round(np.float64(a["charges"]), 2) - b["tc"]),
                  f"fill {i} ({a['side']} {a['symbol']}): charges differ from its trades row")
    # --- slippage and charges, every fill ------------------------------------
    if len(fills):
        # The model is costs.fill_price, the engine's own rule: the rate
        # applied to the reference price, rounded to the paisa.
        r = fills["impact_rate"] if "impact_rate" in fills.columns else 0.0 * fills["qty"]
        model = np.array([_costs.fill_price(ref, SLIPPAGE + rt, side == "BUY") for ref, rt, side
                          in zip(fills["reference_price"], r, fills["side"])])
        gap = (fills["fill_price"] - model) * fills["qty"]
        bad = np.flatnonzero(np.abs(gap) >= PAISA)
        if len(bad):
            j = bad[0]
            _fail("slippage", fills["date"].iloc[j], float(gap.iloc[j]),
                  f"{fills['side'].iloc[j]} {fills['symbol'].iloc[j]}: the slippage model "
                  f"(flat{', plus impact' if 'impact_rate' in fills.columns else ''}) does not "
                  f"give the recorded fill")
        cg = fills["charges_total"] - fills["charges"]
        bad = np.flatnonzero(np.abs(cg) >= PAISA)
        if len(bad):
            j = bad[0]
            _fail("slippage", fills["date"].iloc[j], float(cg.iloc[j]),
                  f"{fills['symbol'].iloc[j]}: the itemised charges do not sum to the charge deducted")
    # --- cash, every day -------------------------------------------------------
    flow = pd.Series(0.0, index=days["date"])
    if len(fills):
        v = fills["qty"] * fills["fill_price"] * np.where(fills["side"] == "SELL", 1.0, -1.0) - fills["charges"]
        flow = flow.add(v.groupby(fills["date"]).sum(), fill_value=0.0)
    exp = (days["cash_open"].to_numpy() + days["interest"].to_numpy() + flow.reindex(days["date"]).to_numpy()
           - days["tax_before_fills"].to_numpy() - days["tax_after_fills"].to_numpy())
    gap = days["cash_close"].to_numpy() - exp
    bad = np.flatnonzero(np.abs(gap) >= PAISA)
    if len(bad):
        _fail("cash", days["date"].iloc[bad[0]], float(gap[bad[0]]),
              "opening cash + interest + proceeds - purchases - charges - tax != closing cash")
    chain = days["cash_open"].to_numpy()[1:] - days["cash_close"].to_numpy()[:-1]
    bad = np.flatnonzero(np.abs(chain) >= PAISA)
    if len(bad):
        _fail("cash", days["date"].iloc[bad[0] + 1], float(chain[bad[0]]),
              "the day does not open at the previous day's closing cash")
    if abs(days["cash_open"].iloc[0] - start_capital) >= PAISA:
        _fail("cash", days["date"].iloc[0], float(days["cash_open"].iloc[0] - start_capital),
              "the first day does not open at the starting capital")
    # --- tax, every financial year ----------------------------------------------
    lots, pre, post, when = replay_ledger(fills, list(days["date"]))
    years = tax_years(lots, list(days["date"]), when, tax_on)
    rec_pre = dict(zip(days["date"], days["tax_before_fills"]))
    rec_post = dict(zip(days["date"], days["tax_after_fills"]))
    for d in days["date"]:
        want_pre = pre.get(d, 0.0) if tax_on else 0.0
        want_post = post.get(d, 0.0) if tax_on else 0.0
        g = (rec_pre[d] - want_pre) + (rec_post[d] - want_post)
        if abs(rec_pre[d] - want_pre) >= PAISA or abs(rec_post[d] - want_post) >= PAISA:
            _fail("tax", d, float(g), "the tax deducted is not the tax the rules give on the "
                  "per-lot gains realised to that day")
    if tax_on and engine_lots is not None and len(engine_lots):
        a = lots[["symbol", "qty", "gain"]].reset_index(drop=True)
        b = engine_lots[["symbol", "qty", "gain"]].reset_index(drop=True)
        if len(a) != len(b) or (a["symbol"] != b["symbol"]).any() or \
                (np.abs(a["gain"] - b["gain"]) >= PAISA).any():
            _fail("tax", None, float(a["gain"].sum() - b["gain"].sum()),
                  "the replayed lots differ from the engine's own ledger")
    # --- totals ---------------------------------------------------------------
    tot_tc = float(fills["charges"].sum()) if len(fills) else 0.0
    if abs(tot_tc - engine_tc) >= PAISA:
        _fail("totals", None, tot_tc - engine_tc, "per-fill charges do not sum to the run's total")
    tot_tax = float(days["tax_before_fills"].sum() + days["tax_after_fills"].sum())
    if abs(tot_tax - engine_tax) >= PAISA:
        _fail("totals", None, tot_tax - engine_tax, "per-day tax does not sum to the run's total")
    if abs(float(years["total_tax"].sum()) - tot_tax) >= PAISA:
        _fail("totals", None, float(years["total_tax"].sum()) - tot_tax,
              "per-year tax does not sum to the tax deducted")
    return fills, lots, years, days


# ---------------------------------------------------------------------------
# THE SUMMARY BLOCK
# ---------------------------------------------------------------------------
def _pct(x, base):
    return f"{x / base * 100:8.2f}%" if base > 0 else "     n/a"


def bh_costs(px, op, bd, start_capital, tax_on):
    """Charges, slippage and tax of the investable buy & hold (backtest_runs.held_lots),
    held to the end and sold on the last day, recomputed fill by fill and reconciled
    against held_lots to the paisa. Raises CostReconciliationError on a gap."""
    import backtest_runs as bh_held
    r = bh_held.held_lots(px, op, bd)
    det, d0, dN = r["detail"], bd[0], bd[-1]
    o0, oN = op.loc[d0], op.loc[dN]
    buy = {k: 0.0 for k, _ in CHARGES}
    sell = {k: 0.0 for k, _ in CHARGES}
    cash, buy_slip, sell_slip, proceeds, gain = float(start_capital), 0.0, 0.0, 0.0, 0.0
    for sym, (q, pr) in r["shares"].items():
        ref = float(o0[sym])
        b_ = charge_breakdown(pr, q, "BUY", numpy_round=False)
        for k, _ in CHARGES:
            buy[k] += b_[k]
        cash -= q * pr + b_["total"]
        buy_slip += (pr - ref) * q
        # the last-day sale, as held_lots prices it: the last open, or the close
        ref_n = float(oN.get(sym, np.nan))
        if np.isnan(ref_n) or ref_n <= 0:
            ref_n = float(px.loc[dN, sym])
        sp = _costs.fill_price(ref_n, SLIPPAGE, False)
        s_ = charge_breakdown(sp, q, "SELL", numpy_round=False)
        for k, _ in CHARGES:
            sell[k] += s_[k]
        sell_slip += (ref_n - sp) * q
        proceeds += q * sp
        gain += q * (round(sp, 2) - round(pr, 2))
    bucket = dict.fromkeys(_costs.BUCKETS, 0.0)
    bucket[("long_" if _costs.is_long_term(d0, dN) else "short_") + _costs.regime_of(dN)] = gain
    tx = _costs.tax_for_fy(_costs.financial_year(dN), bucket)
    held_final = cash + float((px.loc[bd, list(r["shares"])].ffill().iloc[-1]
                               * np.array([q for q, _ in r["shares"].values()], dtype=float)).sum())
    sold_final = cash + proceeds - sum(sell.values()) - tx["total_tax"]
    for got, want, what, day in (
            (cash, det["residual_cash"], "cash left after the buys", d0),
            (held_final, float(r["eq_headline"].iloc[-1]), "equity held to the end", dN),
            (sum(sell.values()), float(det["sell_tc"]), "last-day sell charges", dN),
            (tx["total_tax"], float(det["tax"]), "tax on the last-day sale", dN),
            (sold_final, float(r["eq_last_day"].iloc[-1]), "equity sold on the last day", dN)):
        if abs(got - want) >= PAISA:
            _fail("buy & hold", day, got - want, f"{what} does not reconcile with bh_held.held_lots")
    return {"names": det["names"], "buy_charges": buy, "buy_slippage": buy_slip,
            "held_final": held_final, "sell_charges": sell, "sell_slippage": sell_slip,
            "tax": tx["total_tax"] if tax_on else 0.0, "stcg_tax": tx["stcg_tax"] if tax_on else 0.0,
            "ltcg_tax": tx["ltcg_tax"] if tax_on else 0.0,
            "cess": tx["cess"] if tax_on else 0.0,
            "exemption_used": tx["exemption_used"] if tax_on else 0.0,
            "sold_final": sold_final if tax_on else sold_final + tx["total_tax"],
            "tax_if_on": tx["total_tax"]}


def strategy_totals(start_capital, final, fills, years):
    """The run's cost totals: the figures the summary block and the daily log print."""
    tot = {k: float(fills[k].sum()) if len(fills) else 0.0 for k, _ in CHARGES}
    charges = sum(tot.values())
    slip = float(fills["slippage_rs"].sum()) if len(fills) else 0.0
    stcg = float(years["stcg_tax"].sum())
    ltcg = float(years["ltcg_tax"].sum())
    # THE TAX TOTAL IS total_tax, THE FIGURE THE LEDGER DEDUCTED FROM CASH. It is
    # short + long + the 4% cess. Until 2026-10-16 this was stcg + ltcg, which left
    # the cess out of the printed total, the gross profit and every "of gross"
    # percentage from 2026-10-14, when the tax rules began charging the cess. A
    # COST_TAX_YEARS file from before then has no cess column and no cess.
    cess = float(years["cess"].sum()) if "cess" in years.columns else 0.0
    tax = float(years["total_tax"].sum())
    if "impact_rs" not in fills.columns:
        return {"final": final, "gross": final - start_capital + charges + slip + tax,
                "by_type": tot, "charges": charges, "slippage": slip, "tax": tax,
                "stcg": stcg, "ltcg": ltcg, "cess": cess,
                "exemption_used": float(years["exemption_used"].sum()),
                "all_costs": charges + slip + tax}
    imp = float(fills["impact_rs"].sum()) if len(fills) else 0.0
    return {"final": final, "gross": final - start_capital + charges + slip + imp + tax,
            "by_type": tot, "charges": charges, "slippage": slip, "impact": imp, "tax": tax,
            "stcg": stcg, "ltcg": ltcg, "cess": cess,
            "exemption_used": float(years["exemption_used"].sum()),
            "all_costs": charges + slip + imp + tax}


def bh_totals(bh, start_capital):
    """{"held": ..., "sold": ...}: bh_costs' figures in strategy_totals' shape, for the
    buy & hold held to the end and sold on the last day."""
    bc, bs = sum(bh["buy_charges"].values()), bh["buy_slippage"]
    sc_, ss = sum(bh["sell_charges"].values()), bh["sell_slippage"]
    held_costs = bc + bs
    sold_costs = bc + bs + sc_ + ss + bh["tax"]
    held = {"final": bh["held_final"], "gross": bh["held_final"] - start_capital + held_costs,
            "by_type": dict(bh["buy_charges"]), "charges": bc, "slippage": bs, "tax": 0.0,
            "stcg": 0.0, "ltcg": 0.0, "cess": 0.0, "exemption_used": 0.0, "all_costs": held_costs}
    sold = {"final": bh["sold_final"], "gross": bh["sold_final"] - start_capital + sold_costs,
            "by_type": {k: bh["buy_charges"][k] + bh["sell_charges"][k] for k, _ in CHARGES},
            "charges": bc + sc_, "slippage": bs + ss, "tax": bh["tax"], "stcg": bh["stcg_tax"],
            "ltcg": bh["ltcg_tax"], "cess": bh["cess"], "exemption_used": bh["exemption_used"],
            "all_costs": sold_costs}
    return {"held": held, "sold": sold}


def exit_costs(fills):
    """Charges plus slippage on the drawdown stop's sales (fill kind "drawdown exit")."""
    if not len(fills):
        return 0.0
    f = fills[fills["kind"] == "drawdown exit"]
    if not len(f):
        return 0.0
    out = float(f["charges_total"].sum() + f["slippage_rs"].sum())
    return out + float(f["impact_rs"].sum()) if "impact_rs" in f.columns else out


def dd_block(dd, fills, tax_on):
    """The drawdown-limit axis's own lines for the summary, [] when it is off.

    Its trims and top-ups are fill kinds "dd trim" and "dd top-up", so their
    charges and slippage are summed from the reconciled fills. Its tax is the
    marginal figure portfolio.marginal_tax computes."""
    if not dd:
        return []
    f = fills[fills["kind"].astype(str).str.startswith("dd ")] if len(fills) else fills
    n_trim = int((f["kind"] == "dd trim").sum()) if len(f) else 0
    n_top = int((f["kind"] == "dd top-up").sum()) if len(f) else 0
    ch = float(f["charges"].sum()) if len(f) else 0.0
    sl = float(f["slippage_rs"].sum()) if len(f) else 0.0
    tx = float(dd.get("marginal_tax", 0.0)) if tax_on else 0.0
    wd = dd["worst_date"]
    pk = dd["worst_peak_date"]
    L = ["", f"  DRAWDOWN LIMIT (exploratory, not validated): L {dd['limit_pct']:g}%, "
             f"m {dd['m']:.4g}, floor {dd['floor_pct']:g}%, band {dd['band_pct']:g} points",
         f"    worst close drawdown from the all-time peak  {dd['worst_dd_pct']:.2f}%"
         + (f" on {pd.Timestamp(wd).date()}" if wd is not None else "")
         + (f" (peak {pd.Timestamp(pk).date()})" if pk is not None else ""),
         f"    limit breached                               "
         + (f"yes, by {dd['breach_points']:.2f} points" if dd["breached"] else "no"),
         f"    sessions below the limit                     {dd['sessions_below_limit']:,}",
         f"    days at the floor                            {dd['days_at_floor']:,}",
         f"    orders / fills (trim, top-up)                {dd['orders']:,} / "
         f"{n_trim + n_top:,} ({n_trim:,}, {n_top:,})",
         f"    {'charges of its fills':<45}{ch:>16,.2f}",
         f"    {'slippage of its fills':<45}{sl:>16,.2f}",
         f"    {'tax, marginal':<45}{tx:>16,.2f}",
         f"    {'all three':<45}{ch + sl + tx:>16,.2f}",
         "    These are part of the totals above, not added to them. The marginal tax is each",
         "    year's bill less the bill without the gains its sales realised; losses set off",
         "    within a year, so it is not an exact attribution."]
    return L


def summary_block(label, profile, tax_on, rebal, start_capital, equity, fills, years, days, bh,
                  cap_cuts=0, stop_arm=False, dd=None):
    """The text block, as a list of lines. `stop_arm` adds the "of which drawdown
    exits" row; it is False for the core arms, whose block is unchanged."""
    S = strategy_totals(start_capital, float(equity.iloc[-1]), fills, years)
    final, gross, tot, charges = S["final"], S["gross"], S["by_type"], S["charges"]
    slip, stcg, ltcg, tax, exu = S["slippage"], S["stcg"], S["ltcg"], S["tax"], S["exemption_used"]
    cess = S["cess"]
    has_imp = "impact" in S
    L = ["=" * 90, f" COSTS -- {label}   cadence {rebal}, profile {profile}, tax {'on' if tax_on else 'off'}",
         "=" * 90,
         f"  starting capital Rs {start_capital:,.2f}   final equity Rs {final:,.2f}",
         f"  gross profit Rs {gross:,.2f} = final equity - starting capital + charges + slippage"
         + (" + impact" if has_imp else "") + " + tax",
         "",
         f"  {'':<34}{'Rs':>16}{'of capital':>12}{'of gross':>11}"]

    def row(name, x, ind=2):
        L.append(f"  {' ' * ind}{name:<{34 - ind}}{x:>16,.2f}{_pct(x, start_capital):>12}{_pct(x, gross):>11}")
    row("charges, total", charges, 0)
    for k, nm in CHARGES:
        row(nm, tot[k])
    row("slippage", slip, 0)
    if has_imp:
        row("impact", S["impact"], 0)
    row("tax, total", tax, 0)
    row("short-term", stcg)
    row("long-term", ltcg)
    row("cess", cess)
    row("LTCG exemption used (not a cost)", exu)
    row("all costs", S["all_costs"], 0)
    if stop_arm:
        row("of which drawdown exits", exit_costs(fills))
    # per financial year, on a cash basis: a cost belongs to the year it left cash,
    # so each year's gross profit is its change in equity plus what it paid
    L += ["", "  per financial year, as paid (Rs; last column % of the year's gross profit)",
          f"  {'FY':<11}{'gross profit':>15}{'charges':>13}{'slippage':>12}"
          + (f"{'impact':>12}" if has_imp else "")
          + f"{'short tax':>12}{'long tax':>11}{'cess':>11}{'exempt used':>13}{'costs % gross':>15}"]
    paid = years.dropna(subset=["deducted_on"]).copy()
    paid["paid_fy"] = paid["deducted_on"].map(_costs.financial_year)
    fyof = pd.Series([_costs.financial_year(d) for d in equity.index], index=equity.index)
    ffy = fills["date"].map(_costs.financial_year) if len(fills) else pd.Series(dtype=int)
    prev, sums, imp_sum = start_capital, np.zeros(6), 0.0
    for fy in sorted(fyof.unique()):
        end = float(equity.loc[fyof[fyof == fy].index[-1]])
        fl = fills[ffy == fy] if len(fills) else fills
        c = float(fl["charges"].sum()) if len(fl) else 0.0
        s_ = float(fl["slippage_rs"].sum()) if len(fl) else 0.0
        y = paid[paid["paid_fy"] == fy]
        st, lt, ex = (float(y[k].sum()) for k in ("stcg_tax", "ltcg_tax", "exemption_used"))
        ce = float(y["cess"].sum()) if "cess" in y.columns else 0.0
        if has_imp:
            i_ = float(fl["impact_rs"].sum()) if len(fl) else 0.0
            g = end - prev + c + s_ + i_ + st + lt + ce
            L.append(f"  {_costs.fy_label(fy):<11}{g:>15,.2f}{c:>13,.2f}{s_:>12,.2f}{i_:>12,.2f}"
                     f"{st:>12,.2f}{lt:>11,.2f}{ce:>11,.2f}{ex:>13,.2f}"
                     f"{_pct(c + s_ + i_ + st + lt + ce, g):>15}"
                     + (f"   tax settles {', '.join(y['fy'])}" if len(y) else ""))
            imp_sum += i_
        else:
            g = end - prev + c + s_ + st + lt + ce
            settles = ", ".join(y["fy"]) if len(y) else ""
            L.append(f"  {_costs.fy_label(fy):<11}{g:>15,.2f}{c:>13,.2f}{s_:>12,.2f}{st:>12,.2f}{lt:>11,.2f}"
                     f"{ce:>11,.2f}{ex:>13,.2f}{_pct(c + s_ + st + lt + ce, g):>15}"
                     + (f"   tax settles {settles}" if settles else ""))
        sums += (g, c, s_, st, lt, ce)
        prev = end
    if has_imp and abs(imp_sum - S["impact"]) >= PAISA:
        _fail("totals", None, imp_sum - S["impact"], "per-year impact does not sum to the summary total")
    for got, want, what in ((sums[0], gross, "gross profit"), (sums[1], charges, "charges"),
                            (sums[2], slip, "slippage"), (sums[3] + sums[4] + sums[5], tax, "tax")):
        if abs(got - want) >= PAISA:
            _fail("totals", None, got - want, f"per-year {what} does not sum to the summary total")
    L.append("  Tax is shown in the year it left cash; COST_TAX_YEARS gives the year each amount was "
             "levied on.")
    # buy & hold, held to the end and sold on the last day
    if bh is not None:
        B = bh_totals(bh, start_capital)
        bc, bs, held_costs, g_held = (B["held"][k] for k in ("charges", "slippage", "all_costs", "gross"))
        sold_costs, g_sold = B["sold"]["all_costs"], B["sold"]["gross"]
        L += ["", f"  investable buy & hold ({bh['names']} names bought at the first open)",
              f"  {'':<34}{'held to the end':>18}{'sold on the last day':>22}",
              f"  {'final equity':<34}{bh['held_final']:>18,.2f}{bh['sold_final']:>22,.2f}",
              f"  {'gross profit':<34}{g_held:>18,.2f}{g_sold:>22,.2f}"]
        for nm, x, y in (("charges", bc, B["sold"]["charges"]), ("slippage", bs, B["sold"]["slippage"]),
                         ("tax, total", 0.0, bh["tax"]), ("  short-term", 0.0, bh["stcg_tax"]),
                         ("  long-term", 0.0, bh["ltcg_tax"]), ("  cess", 0.0, bh["cess"]),
                         ("  LTCG exemption used (not a cost)", 0.0, bh["exemption_used"]),
                         ("all costs", held_costs, sold_costs)):
            L.append(f"  {nm:<34}{x:>18,.2f}{y:>22,.2f}")
        L.append(f"  {'all costs, % of gross profit':<34}{_pct(held_costs, g_held):>18}"
                 f"{_pct(sold_costs, g_sold):>22}")
        L.append("  Held to the end is the headline buy & hold: it never sells, so it pays no tax "
                 "under either setting.")
        if not tax_on:
            L.append(f"  Tax is off, so the last-day sale pays none here; with tax on it would pay "
                     f"Rs {bh['tax_if_on']:,.2f}.")
        L += ["", f"  all costs: arm Rs {S['all_costs']:,.2f}; buy & hold held Rs {held_costs:,.2f}, "
                  f"sold on the last day Rs {sold_costs:,.2f}"]
    L += dd_block(dd, fills, tax_on)
    # zeros, stated
    L += ["", "  zero components and why:"]
    if tot["brokerage"] == 0:
        L.append("    brokerage is zero: Zerodha charges no brokerage on delivery equity.")
    if tot["ipft"] == 0:
        L.append("    IPFT is zero: the charge engine leaves the NSE IPFT levy out (about Rs 0.01 a crore).")
    if has_imp:
        k_ = float(fills["impact_k"].iloc[0]) if len(fills) else 0.0
        n_ex = int(fills["impact_median"].isna().sum()) if len(fills) else 0
        L.append(f"    slippage is the flat {SLIPPAGE:.2%} of the reference price; impact is the size-"
                 f"sensitive term on top of it, k {k_:g} x sqrt(order / prior-20-session median "
                 f"volume), on buys and sells. {n_ex:,} fill(s) had no prior-20-session median and "
                 f"paid the flat rate only.")
    else:
        L.append(f"    slippage is the flat {SLIPPAGE:.2%} of the reference price in both profiles; the size-"
                 f"sensitive term is not used, so no fill pays more than the flat rate.")
    if profile == "research":
        L.append("    research profile: no participation cap, so no order was cut for volume.")
    else:
        L.append(f"    {profile} profile: the participation cap cut {cap_cuts:,} order(s) to a share of "
                 f"prior-20-session median volume; it changes quantities, not the slippage rate.")
    if not tax_on:
        L.append("    TAX IS OFF for this run: every tax figure is zero because of the tax setting, not the gains.")
    if stop_arm:
        L.append("    of which drawdown exits: the charges and slippage of the stop's sales. Their tax is "
                 "not separable; it is part of each year's bill above.")
    L += ["", "  what the tax model leaves out (data/reference/TAX_AND_CHARGES.docx, section 5):"]
    L += [f"    - {x}" for x in TAX_LEAVES_OUT]
    L += ["", f"  reconciled to the paisa: cash on {len(days):,} days, slippage"
              + (", impact" if has_imp else "") + f" and charges on "
              f"{len(fills):,} fills, tax on {len(years)} financial years, the totals above, and "
              f"the buy & hold held and sold.",
          "=" * 90]
    return L


# ---------------------------------------------------------------------------
# THE DAILY LOG'S TOTALS BLOCK
# ---------------------------------------------------------------------------
# make_daily_log calls daily_log_totals once per log. The strategy's figures are
# strategy_totals over the COSTS_ and COST_TAX_YEARS_ files write() saved, and
# the buy & hold's are bh_totals over bh_costs, so no figure is computed a second
# way. Every figure COST_SUMMARY_<tag>.txt also prints is then compared with it,
# as printed, and any difference fails the run.
BOOK_TITLES = {"held": "buy & hold, held to the end",
               "sold": "buy & hold, sold on the last day"}


def read_run_costs(M, tag):
    """(fills, years) as write() saved them for `tag`, in the frames strategy_totals reads."""
    M = Path(M)
    from market_data import read_table
    # `tag` is backtest_runs.artefact_tag(u, arm), passed in by make_daily_log
    fills = read_table(M / f"COSTS_{tag}.csv", parse_dates=["date"]).rename(columns={"stt": "stt_ctt"})
    # `tag` is backtest_runs.artefact_tag(u, arm), passed in by make_daily_log
    years = read_table(M / f"COST_TAX_YEARS_{tag}.csv")
    return fills, years


def _book_figures(book, T_):
    out = {f"{book}/{k}": T_[k] for k in ("final", "gross", "charges", "slippage", "tax", "stcg",
                                          "ltcg", "cess", "exemption_used", "all_costs")}
    if "impact" in T_:
        out[f"{book}/impact"] = T_["impact"]
    out.update({f"{book}/{k}": T_["by_type"][k] for k, _ in CHARGES})
    return out


def summary_figures(text):
    """{"<book>/<figure>": "1,234.56"} for every rupee figure the summary block prints
    in its totals: the strategy table and the buy & hold table, as printed."""
    import re
    lines = text.splitlines()
    out = {}
    m = re.search(r"final equity Rs ([-\d,.]+)", text)
    out["strategy/final"] = m.group(1)
    out["strategy/gross"] = re.search(r"gross profit Rs ([-\d,.]+) =", text).group(1)
    names = {"charges, total": "charges", "charges": "charges", "slippage": "slippage",
             "impact": "impact",
             "tax, total": "tax", "short-term": "stcg", "long-term": "ltcg", "cess": "cess",
             "LTCG exemption used (not a cost)": "exemption_used", "all costs": "all_costs",
             "final equity": "final", "gross profit": "gross",
             "of which drawdown exits": "exit_costs"}
    names.update({nm: k for k, nm in CHARGES})
    # EACH FIGURE IS READ WHOLE, AT ANY WIDTH. The label is the fixed 34 characters
    # after the indent; the figures follow it. A figure is printed with ",.2f", so
    # it always ends in exactly two decimals, which separates two figures even when
    # a wide one fills its column and touches the next. The percent columns end in
    # "%" and are not rupee figures. Until 2026-10-20 the figures were sliced at
    # fixed columns (36:52, 36:54, 54:76), which cut any figure wider than its
    # column: from Rs 1,000 crore up a run failed its reconciliation on a
    # truncated copy of a correct figure.
    rupees = re.compile(r"-?\d{1,3}(?:,\d{3})*\.\d{2}(?![\d%])")
    i = next(j for j, x in enumerate(lines) if x.rstrip().endswith("of gross"))
    for x in lines[i + 1:]:
        if not x.strip():
            break
        out[f"strategy/{names[x[2:36].strip()]}"] = rupees.findall(x[36:])[0]
    i = next((j for j, x in enumerate(lines) if x.rstrip().endswith("sold on the last day")
              and "held to the end" in x), None)
    if i is not None:
        for x in lines[i + 1:]:
            if x.startswith("  all costs, % of gross profit"):
                break
            k = names[x[2:36].strip()]
            out[f"held/{k}"], out[f"sold/{k}"] = rupees.findall(x[36:])[:2]
    m = re.search(r"with tax on it would pay Rs ([-\d,.]+)\.", text)
    if m:
        out["sold/tax_if_on"] = m.group(1)
    return out


def check_tax_total(lines, years, engine_tax):
    """The printed tax total must be COST_TAX_YEARS total_tax summed and the ledger's
    final cum_tax, within Rs 0.01. Raises CostReconciliationError otherwise.

    ADDED 2026-10-16. The block's own checks compared the per-year tax with the
    summary total, and both were short + long, so a total that left the 4% cess out
    agreed with itself. This compares the printed figure with the two sources that
    carry what cash actually paid."""
    printed = float(summary_figures("\n".join(lines))["strategy/tax"].replace(",", ""))
    for want, what in ((float(years["total_tax"].sum()), "COST_TAX_YEARS total_tax summed"),
                       (float(engine_tax), "the ledger's final cum_tax")):
        if abs(printed - want) > 0.01:
            _fail("totals", None, printed - want,
                  f"the printed tax total Rs {printed:,.2f} is not {what}, Rs {want:,.2f}")


def daily_log_totals(M, tag, arm_name, final, bh, start_capital, tax_on, width,
                     summary_text=None):
    """The totals block that ends DAILY_LOG_<tag>.txt, as a list of lines.

    `final` is the arm's final equity from the engine's curve and `bh` is bh_costs'
    result for the universe. Raises CostReconciliationError if any figure differs
    from COST_SUMMARY_<tag>.txt, or from `summary_text` when given (the rebuild in
    tools/rebuild_costs_block.py passes the block it is about to write)."""
    M = Path(M)
    fills, years = read_run_costs(M, tag)
    books = {"strategy": strategy_totals(start_capital, final, fills, years),
             **bh_totals(bh, start_capital)}
    mine = {}
    for b, T_ in books.items():
        mine.update(_book_figures(b, T_))
    mine["sold/tax_if_on"] = bh["tax_if_on"]
    import portfolio as _ar
    _stop_arm = _ar.get(arm_name).stop is not None
    if _stop_arm:
        mine["strategy/exit_costs"] = exit_costs(fills)
    # `tag` is backtest_runs.artefact_tag(u, arm), passed in by make_daily_log
    summ = M / f"COST_SUMMARY_{tag}.txt"
    if summary_text is None:
        if not summ.exists():
            _fail("daily log", None, 0.0, f"{summ.name} is absent, so the totals cannot be checked")
        summary_text = summ.read_text()
    theirs = summary_figures(summary_text)
    for k, v in theirs.items():
        got = f"{mine[k]:,.2f}"
        if got != v:
            _fail("daily log", None, float(got.replace(",", "")) - float(v.replace(",", "")),
                  f"the daily log's {k.replace('/', ' ')} is Rs {got}, {summ.name} prints Rs {v}")
    has_imp = "impact" in books["strategy"]
    L = ["", "=" * width,
         " COST TOTALS -- charges, slippage"
         + (", impact" if has_imp else "") + " and capital-gains tax over the whole run",
         "=" * width,
         f"   starting capital Rs {start_capital:,.2f}.   gross profit = final equity - starting capital"
         f" + charges + slippage" + (" + impact" if has_imp else "") + " + tax",
         f"   From results/cost_report.py: the strategy from COSTS_{tag}.csv and COST_TAX_YEARS_{tag}.csv,",
         "   the buy & hold from bh_costs."]
    for b, T_ in books.items():
        title = f"strategy ({arm_name})" if b == "strategy" else BOOK_TITLES[b]
        L += ["", f"   {title}   final equity Rs {T_['final']:,.2f}   gross profit Rs {T_['gross']:,.2f}",
              f"   {'':<34}{'Rs':>16}{'of capital':>12}{'of gross':>11}"]

        def row(name, x, ind=2):
            L.append(f"   {' ' * ind}{name:<{34 - ind}}{x:>16,.2f}{_pct(x, start_capital):>12}"
                     f"{_pct(x, T_['gross']):>11}")
        row("charges, total", T_["charges"], 0)
        for k, nm in CHARGES:
            row(nm, T_["by_type"][k])
        row("slippage", T_["slippage"], 0)
        if "impact" in T_:
            row("impact", T_["impact"], 0)
        row("tax, total", T_["tax"], 0)
        row("short-term", T_["stcg"])
        row("long-term", T_["ltcg"])
        row("cess", T_["cess"])
        row("LTCG exemption used (not a cost)", T_["exemption_used"])
        row("all costs", T_["all_costs"], 0)
        if b == "strategy" and _stop_arm:
            row("of which drawdown exits", mine["strategy/exit_costs"])
    L += ["", "   Held to the end, the buy & hold never sells, so it pays no tax under either setting."]
    if not tax_on:
        L += ["   Tax is off for this run, so every tax figure above is zero.",
              f"   Sold on the last day with tax on, the buy & hold would pay Rs {bh['tax_if_on']:,.2f}."]
    L += [f"   checked against {summ.name}: all {len(theirs)} figures it prints agree to the paisa",
          "=" * width]
    return L


def write(u, arm, tag, audit, equity, engine_tc, px, op, bd, start_capital, profile, tax_on, rebal):
    """Reconcile, write the four files and print the summary block. Raises on a failure."""
    M = Path(u.metrics_dir)
    engine_tax = float(audit["tax"]["cum_tax"]) if (tax_on and "tax" in audit) else 0.0
    engine_lots = audit["tax"]["lots"] if (tax_on and "tax" in audit) else None
    fills, lots, years, days = reconcile_costs(audit["costs"], audit["trades"], list(bd), start_capital,
                                         engine_tc, engine_tax, tax_on, engine_lots)
    cols = ["date", "side", "kind", "symbol", "qty", "reference_price", "fill_price", "slippage_rs"] + \
        (["impact_k", "impact_median", "impact_rs"] if "impact_rs" in fills.columns else []) + \
        [k for k, _ in CHARGES] + ["charges_total"]
    out = fills[cols].rename(columns={"stt_ctt": "stt"})
    lo = lots.rename(columns={"sell_date": "date", "held_days": "days_held"})
    lo["term"] = np.where(lo["is_long"], "long", "short")
    lo = lo[["date", "symbol", "qty", "buy_date", "buy_price", "sell_price", "days_held", "term",
             "regime", "fy", "gain"]]
    lo["fy"] = lo["fy"].map(_costs.fy_label)
    bh = bh_costs(px, op, bd, start_capital, tax_on)
    lines = summary_block(f"{u.tag} {getattr(arm, 'name', arm)}", profile, tax_on, rebal,
                          start_capital, equity, fills, years, days, bh,
                          cap_cuts=sum(1 for r in audit["skipped"] if r.get("reason") == "participation cap"),
                          stop_arm=getattr(arm, "stop", None) is not None,
                          dd=audit.get("dd"))
    check_tax_total(lines, years, engine_tax)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is backtest_runs.artefact_tag(u, arm)
    out.to_csv(M / f"COSTS_{tag}.csv", index=False)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is backtest_runs.artefact_tag(u, arm)
    lo.to_csv(M / f"COST_LOTS_{tag}.csv", index=False)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is backtest_runs.artefact_tag(u, arm)
    years.to_csv(M / f"COST_TAX_YEARS_{tag}.csv", index=False)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is backtest_runs.artefact_tag(u, arm)
    (M / f"COST_SUMMARY_{tag}.txt").write_text("\n".join(lines) + "\n")
    print(f"\n  costs reconciled and saved -> COSTS_{tag}.csv / COST_LOTS_{tag}.csv / "
          f"COST_TAX_YEARS_{tag}.csv / COST_SUMMARY_{tag}.txt")
    return lines


# ======================================================================================
# STEP: TAX REPORT. From results/tax_report.py (moved 2026-11-27).
# ======================================================================================
# tax_report -- the four tax artefacts. Written only when tax=on.
# ===============================================================================
#
#     FY_TAX_STATEMENT_<tag>.csv    per financial year: buckets, netting, tax
#     FY_EQUITY_<tag>.csv           equity at each financial-year boundary
#     HOLDING_PERIOD_<tag>.csv      the holding-period distribution
#     HOLDING_PERIOD_LOTS_<tag>.csv every closed lot, one row each
#
# WHY THESE ARE FOUR FILES AND NOT FOUR COLUMNS ON AN EXISTING ONE
#     Adding tax columns to daily_trades_<tag>.csv or v34_comparison<SFX>.csv would
#     put them in front of gates that read those files and compute over their
#     non-benchmark rows without erroring. The companion-file decision is the same
#     one backtest_runs.py made for the profile axis, for the same reason.
#
#     AND IT KEEPS HASHED FILES STABLE. Sixteen retired-universe artefacts, trade
#     logs among them, were pinned by SHA-256 in the retired-universe manifest
#     (deleted 2026-09-24; git show 50562ed:RETIRED_UNIVERSES-manifest.txt). A new
#     column on one of those file shapes is a hash break for artefacts that cannot
#     be regenerated.
#
# THE NUMBERS HERE ARE THE TAXED RUN'S OWN, NEVER THE UNTAXED LOG'S
#     FY_TAX_STATEMENT reports what the taxed portfolio ACTUALLY PAID, read from
#     the in-loop ledger that charged it. It is not recomputed from a trade log,
#     and in particular it is not the figure an untaxed run's log implies -- those
#     differ by about 4% (midcap150: Rs 833,105 implied against Rs 798,365 charged, see
#     costs.py, TAX PARTIALLY DAMPS ITSELF), and the implied one describes a run
#     that did not happen.
#
#     THE CONSEQUENCE IS THAT FY_TAX_STATEMENT RECONCILES WITH FY_EQUITY TO THE
#     PAISA, and reconcile() checks exactly that before anything is written: the
#     sum of the per-year tax must equal the cumulative tax the engine deducted.
#     A mismatch raises rather than writing two files that disagree.
#
# THE UNASSESSED YEAR IS A ROW, NOT AN OMISSION
#     Section 3(9) assesses a financial year on the first trading day at or after
#     31 March. FY2026-27's falls in 2027, outside the window, so its liability is
#     computed and never deducted. It appears in FY_TAX_STATEMENT with
#     assessed=False, its full liability in the tax column, and assessed_note
#     spelling out that the window's final sessions are untaxed and that the
#     untaxed tail includes the held-out sessions. It is excluded from the
#     reconciliation total, because no cash moved for it.

# The four stems. Composed through settings.name() -- the only composer measured to
# carry all four axes without modification (settings.CARRIES, re-probed 2026-09-17).
STEMS = ("FY_TAX_STATEMENT", "FY_EQUITY", "HOLDING_PERIOD", "HOLDING_PERIOD_LOTS")


def artefact_name(stem, tag, ext=".csv"):
    """<stem>_<tag><ext>, e.g. FY_TAX_STATEMENT_midcap150_v1_tradeable_tax.csv

    `tag` IS ALREADY THE FULL COMPOSITION. backtest_runs.artefact_tag() returns the
    universe, the arm, and then cadence.suffix() + profile_axis.suffix() +
    tax.suffix() -- all four axes, which is why settings.CARRIES credits it with
    all four. So this appends the stem and NOTHING ELSE.

    IT USED TO CALL settings.name() HERE AND THAT WAS A DOUBLE COMPOSITION.
    settings.name() appends the same four-axis tail that artefact_tag has already
    applied, so a taxed run wrote FY_TAX_STATEMENT_mid_tax_tax.csv -- the suffix
    twice. It did not show when this module was first written because the
    then-caller passed a BARE tag ("midcap150") rather than artefact_tag's output, so
    exactly one composition happened and the name looked right. Wiring the step
    supplied the real tag and the second suffix appeared.

    THE LESSON IS THE ONE settings.py OPENS WITH: the composition rule was never
    the problem, retyping it at a second site is. Here the second site was this
    function, applying a tail to a string that already had one.
    """
    return f"{stem}_{tag}{ext}"


def fy_equity(eq, fys):
    """Equity on each financial year's last session, and the year's return.

    THE BOUNDARY IS THE LAST SESSION AT OR BEFORE 31 MARCH, not 31 March itself,
    which is frequently not a trading day. `close_date` says which session was
    used so a reader is never left inferring it.
    """
    rows = []
    for fy in sorted(fys):
        end = pd.Timestamp(year=fy + 1, month=3, day=31)
        s = eq[eq.index <= end]
        if s.empty:
            continue
        start = eq[eq.index <= pd.Timestamp(year=fy, month=4, day=1)]
        open_v = float(start.iloc[-1]) if len(start) else float(eq.iloc[0])
        rows.append({"fy": fy, "fy_label": costs.fy_label(fy),
                     "close_date": s.index[-1], "open_equity": open_v,
                     "close_equity": float(s.iloc[-1]),
                     "fy_return_pct": (float(s.iloc[-1]) / open_v - 1) * 100
                     if open_v else np.nan})
    return pd.DataFrame(rows)


def holding_period(lots):
    """The distribution, and the ceiling the long-term branch is measured against.

    `max_held_days` is the number `costs.max_holding_days()` reads and the
    LTCG-boundary condition in checks.py asserts on.

    NO HEADROOM NUMBER IS CARRIED IN THIS DOCSTRING, DELIBERATELY. Whether the
    long-term branch fires is a PER-UNIVERSE property of the window, not a
    constant of this repository. A number was carried here once -- "an empirical
    326-day maximum with 39 days of headroom" -- and by the time it was read it
    was wrong on two of the four universes, which had 443 and 588 day lots. The
    figure belongs in the artefact, which is measured, and not in prose, which
    is not. `note` below is computed from the lots in hand, every clause of it.
    """
    if lots is None or lots.empty:
        return pd.DataFrame()
    h = lots["held_days"]
    mx = int(h.max())
    # THE ROUTING PREDICATE: more than twelve calendar months (costs.is_long_term, 2026-10-14).
    # headroom_days is how many more days the lot nearest the line needed to be
    # long-term (positive), or how far past the line the furthest lot went
    # (negative or zero).
    line = pd.to_datetime(lots["buy_date"]) + pd.DateOffset(months=costs.LTCG_HOLD_MONTHS)
    sold = pd.to_datetime(lots["sell_date"] if "sell_date" in lots else lots["date"])
    n_long = int(costs.long_term_mask(lots).sum())
    margin = int(((line - sold).dt.days + 1).min())
    # THE WHOLE SENTENCE IS COMPUTED, INCLUDING WHICH SENTENCE IT IS. The
    # previous version interpolated the margin into a hardcoded "does not fire",
    # so nifty50 wrote "does not fire; the margin is -223 days" -- an artefact
    # contradicting its own adjacent column. A claim beside a computed number
    # has to be computed from the same data or it will eventually disagree
    # with it.
    if n_long > 0:
        verb = "is" if n_long == 1 else "are"
        claim = (f"the long-term branch FIRES on this window: {n_long} of "
                 f"{len(lots)} lots {verb} held more than {costs.LTCG_HOLD_MONTHS} "
                 f"calendar months, the longest {mx} days, and LTCG_RATE applies to "
                 f"those lots")
    else:
        claim = (f"the long-term branch does not fire on this window; the "
                 f"margin is {margin} days")
    return pd.DataFrame([{
        "lots": int(len(lots)),
        "max_held_days": mx, "min_held_days": int(h.min()),
        "mean_held_days": round(float(h.mean()), 2),
        "median_held_days": float(h.median()),
        "p95_held_days": float(h.quantile(0.95)),
        "long_term_rule": f"held more than {costs.LTCG_HOLD_MONTHS} calendar months",
        "lots_long_term": n_long,
        "headroom_days": margin,
        "note": claim + (" -- EMPIRICAL, not structural: a cadence or buffer "
                         "change moves it, in either direction"),
    }])


def reconcile_tax(stmt, cum_tax, tol=0.01):
    """Assessed tax in the statement must equal what the engine deducted.

    RAISES RATHER THAN WRITING. Two artefacts that disagree about how much tax
    was paid are worse than neither, because each looks authoritative alone. The
    unassessed year is excluded: its liability is real and reported, but no cash
    moved for it, so it cannot appear in a total that reconciles against cash.
    """
    charged = float(stmt.loc[stmt["assessed"], "total_tax"].sum())
    if abs(charged - float(cum_tax)) > tol:
        raise AssertionError(
            f"FY_TAX_STATEMENT does not reconcile with the engine's deductions:\n"
            f"    statement (assessed years) Rs {charged:,.2f}\n"
            f"    engine cum_tax             Rs {float(cum_tax):,.2f}\n"
            f"    difference                 Rs {charged - float(cum_tax):,.2f}\n"
            f"  Nothing written. FY_TAX_STATEMENT must report what the TAXED run\n"
            f"  actually paid, and it must agree with FY_EQUITY to the paisa.")
    return charged


def write_all(M, tag, eq, tax_audit, dates):
    """Write the four artefacts. Returns the paths, in the order written.

    `tax_audit` is audit["tax"] from backtest_exposure -- the in-loop ledger that
    actually charged the tax, not a recomputation.
    """
    lots = tax_audit["lots"]
    stmt, _due = costs.liability_schedule(lots, dates)
    reconcile_tax(stmt, tax_audit["cum_tax"])

    # FY_EQUITY ENDS AT THE FINAL SESSION. The statement has a row only for a year
    # with a realised lot. nifty50 v5 sold everything on 2026-03-16 and bought
    # back on 2026-05-08, so it realised nothing in the last, partial year; the
    # last row was then 2026-03-30 and the check below failed by Rs 60,402.08.
    # When the last year already has a row the set is unchanged; every v1 to v4
    # tax run has passed the check below, so each already has that row.
    fys = sorted(set(stmt["fy"]) | {costs.financial_year(dates[-1])})
    wrote = []
    for stem, df in (("FY_TAX_STATEMENT", stmt),
                     ("FY_EQUITY", fy_equity(eq, fys)),
                     ("HOLDING_PERIOD", holding_period(lots)),
                     ("HOLDING_PERIOD_LOTS", lots)):
        p = M / artefact_name(stem, tag)
        # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is
        # backtest_runs.artefact_tag's output and carries all four axes; these four
        # artefacts exist only under tax=on. The directive sits on the WRITE,
        # not on the path expression: Gate 2 reads the call it annotates, and a
        # directive parked above an intermediate assignment annotates nothing.
        df.to_csv(p, index=False)
        wrote.append(p)

    leaked = tax_audit.get("leaked", [])
    if leaked:
        print(f"  !! {len(leaked)} realised gain(s) fell into an already-assessed "
              f"financial year and were never taxed -- see KNOWN_ISSUES.md on the "
              f"before-fills ordering. This is not a guard; the figures stand.")
    return wrote


# ---------------------------------------------------------------------------
# THE STEP -- STEP 18a (midcap150) / STEP 18b (nifty100), arity 1
# ---------------------------------------------------------------------------
def tax_report(u):
    """The step, as a function, so run.py can call it in process.

    ARITY 1 BECAUSE ALL FOUR ARTEFACTS ARE PER-UNIVERSE. The tag is in every
    filename and the content is one universe's lots; a whole-run step would have
    to loop the selection internally and would put run.py:_resolve_arity in the
    position of refusing a None tag against a main(u) signature.

    IT RE-RUNS THE BACKTEST, AND THAT IS NOT AVOIDABLE. Nothing upstream produces
    a TAXED run: tax_enabled defaults to False and no other PIPELINE_ORDER row
    passes True. The ledger and cum_tax live in audit["tax"], a Python object
    inside backtest_exposure, so they cannot cross a subprocess boundary or be
    read back off an artefact. The alternative -- having make_audit run a second
    taxed backtest -- was considered and rejected: that step's docstring calls
    itself a check rather than a producer, and it already reconciles an untaxed
    re-run against the engine's curve. Two jobs in a step that says it has one is
    how the cost gets hidden.

    ITS POSITION IS THE END OF THE PIPELINE. The only input is the score panel,
    and running after STEP 15b means the PERMANENT copy exists rather than
    relying on model.require_cache's /tmp fallback.
    """
    # THE EARLY RETURN IS THE WHOLE tax=off CONTRACT, and it uses the mechanism
    # this pipeline already has rather than a new one. backtest_runs.py records it
    # for the scoring step: "Steps 10a/10e are skipped at runtime when their
    # panel is cached; that does not change the ORDER, which is what the checker
    # reasons about." Same shape here -- the row is ALWAYS in PIPELINE_ORDER and
    # always invoked, and decides at run time to do nothing.
    #
    # CONDITIONAL MEMBERSHIP WAS NOT USED, DELIBERATELY. backtest_runs.py records
    # that the old SKIP list was removed ("NOTHING IS SKIPPED HERE ANY MORE");
    # making this row's presence depend on the selection would reintroduce
    # exactly the thing that was taken out, and it would make the plan differ
    # between two selections that check_plan_order should see identically.
    #
    # THE ARTEFACTS ARE ABSENT AT tax=off, NOT EMPTY. This returns before
    # write_all is reached, so no file is opened and none is created.
    if not _tax.selected():
        print(f"    tax=off -- no tax artefacts for {u.tag} "
              f"(the four are absent, not empty)")
        return

    # Imported here rather than at module scope: this module is imported by
    # run.py's arity probe, and pulling the engine in at import time would make
    # a --list or --dry-run pay for a backtest it never runs.
    from settings import cadence
    import model
    import settings
    import market_data
    import costs
    from market_data import precompute
    from portfolio import backtest_exposure
    import backtest_runs as audit_step

    market_data.set_tradeability(u)
    src = model.require_cache(u.score_cache,
                               what=f"{u.tag} score panel")
    p = read_table(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    bd = u.trading_days(px.index)   # the universe's window; see engine_v2_final

    # EVERY SELECTED ARM, SINCE 2026-09-26. This ran v2 alone and wrote v2's four
    # artefacts; v1, v3 and v4 were charged tax in-loop by the engine and nothing
    # reconciled their ledgers. Each arm now gets its own taxed backtest, its own
    # four artefacts under backtest_runs.artefact_tag (v2 unsuffixed, the others
    # _v1/_v3/_v4), the same reconcile() to the paisa, and its own TAX_TURNOVER
    # from its own BH_LOTS file.
    import portfolio as arm_reg
    M = Path(u.metrics_dir)
    for arm in arm_reg.selected():
        _one_arm(u, arm, M, px, op, sc, bd, pc, mom20,
                 cadence, costs, backtest_exposure, audit_step)


def _one_arm(u, arm, M, px, op, sc, bd, pc, mom20,
             cadence, costs, backtest_exposure, audit_step):
    """One arm's taxed backtest, its four artefacts and its TAX_TURNOVER."""
    an = arm.name
    audit = {k: [] for k in
             ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    eq, _tc, _ntr, _expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, **arm.kwargs,
        rebal=cadence.selected(),
        audit=audit, tax_enabled=True, **costs.cap_kwargs(u))

    # THE TAG COMES FROM backtest_runs.artefact_tag, NOT FROM u.tag ALONE, so these
    # four sit beside the trail they describe under every axis combination.
    tag = audit_step.artefact_tag(u, arm)
    wrote = write_all(M, tag, eq, audit["tax"], bd)
    print(f"    tax artefacts for {u.tag} {an}: cum_tax Rs {audit['tax']['cum_tax']:,.2f}")
    for w in wrote:
        print(f"      saved -> {w.name}")

    # ----------------------------------------------------------------------
    # TAX_TURNOVER -- the side-by-side this axis exists to produce
    # ----------------------------------------------------------------------
    # BOTH TAXED COLUMNS COME FROM REAL RUNS. The strategy's from the taxed
    # backtest above and from STEP 17e-h's, the benchmark's from STEP 17e-h's
    # bh_lots basket. NEITHER is computed from an untaxed log: the docstring at
    # the top of this module records that the implied and charged figures differ
    # by about 4% and that "the implied one describes a run that did not happen".
    #
    # IT IS A SEPARATE FILE, not columns on v34_comparison.csv or
    # daily_trades_*, for the reason this module already gives: gates read those
    # and sixteen of them were pinned by SHA-256 in the retired-universe manifest.
    bh = M / f"BH_LOTS_{tag}.csv"
    if not bh.exists():
        print(f"      TAX_TURNOVER not written: {bh.name} is absent -- the "
              f"bh_lots step (bh_lots_after_tax.py) did not run for {u.tag} {an}")
        return
    rows_bh = list(csv.DictReader(open(bh, newline="")))
    fy_close = float(read_table(wrote[1])["close_equity"].iloc[-1])
    BASIS = {
        f"{an} before tax":      ("v34_equity.csv (engine, tax=off)" if an == "v2" else
                                  "untaxed backtest of the same arm (tax=off)"),
        f"{an} after tax":       "taxed backtest, last partial FY settled in-loop at the final session; nothing sold at the end",
        f"{an} sold on the last day": "taxed backtest with every holding sold on the final session (sell charges and tax paid)",
        "bh_lots before tax": "bh_lots equal-rupee basket, held, untaxed",
        "bh_lots after tax":  "bh_lots equal-rupee basket held to the end: nothing realised, nil tax, no sell charge",
        "bh_lots sold on the last day": "bh_lots sold on the final session: sell charges and tax on the realised gain",
        "bh published":       "costless daily-rebalanced index -- untaxable, reference only",
    }
    out_rows = []
    for r in rows_bh:
        r = dict(r)
        r["basis"] = BASIS.get(r["line"], "derived from the rows above")
        out_rows.append(r)
    tt = M / f"TAX_TURNOVER_{tag}.csv"
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` already carries
    # all four axes, so the stem is appended and nothing else. Same rule as the
    # four artefacts above; this file exists only under tax=on.
    pd.DataFrame(out_rows).to_csv(tt, index=False)
    _cost = [r for r in out_rows if r["line"] == "TAX_COST_OF_TURNOVER"]
    _c = _cost[0] if _cost else {}
    if _c.get("cagr_full", "") == "":
        print(f"      saved -> {tt.name}   TAX_COST_OF_TURNOVER WITHHELD")
        print(f"        {_c.get('withheld_reason','')[:110]}")
    else:
        print(f"      saved -> {tt.name}   TAX_COST_OF_TURNOVER "
              f"{float(_c['cagr_full']):+.2f} pts")
    # SINCE 2026-09-25 THE TWO TAXED FIGURES ARE THE SAME NUMBER. The engine
    # settles the last partial financial year in-loop, so FY_EQUITY's close and
    # bh_lots' "<arm> after tax" are one curve's endpoint. A difference is a defect.
    _post = [r for r in out_rows if r["line"] == f"{an} after tax"]
    if not _post:
        raise AssertionError(f"{bh.name} has no '{an} after tax' line")
    _d = fy_close - float(_post[0]["final_equity"])
    print(f"        FY_EQUITY close Rs {fy_close:,.2f}; bh_lots' {an}-after-tax line "
          f"differs by Rs {_d:,.2f}")
    if abs(_d) > 0.01:
        raise AssertionError(
            f"FY_EQUITY close and BH_LOTS '{an} after tax' disagree by Rs {_d:,.2f}; "
            f"both are the same in-loop taxed curve since 2026-09-25")


# ======================================================================================
# STEP: PER-UNIVERSE CHART. From results/make_chart.py (moved 2026-11-27).
# ======================================================================================
# make_chart -- the published chart and the printed record, for one universe.
#
# THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
# make_mid_chart.py and make_n100_chart.py. Step 6 of the collapse, and the most
# divergent pair of the four: 204 code lines differed ignoring whitespace.
#
# WHAT REACHED THE PNG, AND IS THEREFORE REGISTRY DATA, NOT A LITERAL HERE:
# the output stem, the render dpi, the drawdown-panel legend font size, the
# index-window end date. settings.py carries them as chart_text. The
# subtitle, the drawdown labels and the buy&hold legend are built here, once, for
# every universe, since 2026-09-30; they were per-universe registry text and had
# gone stale in different ways on different rows.
#
# WHAT IS DERIVED RATHER THAN STORED: every label built from the tag or the index
# name -- "<tag> buy&hold (equal-weight universe)", "<index> (cap-weighted index)".
# Those were per-universe literals in the merged files and are per-universe facts
# the registry already held.
#
# THE EAGER-READ GUARD FROM e5654ac IS KEPT. before_tc is called only for arms the
# selection actually contains:
#
#     _sel = set(arm_reg.selected_names())
#     b_v2 = ... if "v2" in _sel else None
#     b_v1 = ... if "v1" in _sel else None
#
# Without it `--universe midcap150 --arm v3` demands v1's trade log and dies. That was
# live for two days, it is the reason one of the two gate cells could not run, and
# the merge must not lose it.
#
# NOTHING IS UNIFIED. midcap150 renders at dpi 140 and nifty100 at 150; midcap150 prints an IC and
# extreme-return diagnostic block that nifty100 has never had. Both are preserved as
# declared per-universe data. Harmonising them moves published artefacts and belongs
# in its own commit.
#
# THE INDEX IS PLOTTED AS PUBLISHED. The universe's own index file is read directly.
# No basket is built and called "the index".

# ---------------------------------------------------------------------------
# ARM SOURCES. Was results/arm_sources.py until 2026-10-18 (last at aebf1da).
# ---------------------------------------------------------------------------
# arm_sources.py -- where each arm's curve and per-trade log live, for one universe.
#
# WHY THIS IS ONE MODULE AND NOT FOUR COPIES
#     make_combined_universes, make_final_chart_fair, make_mid_chart and
#     make_n100_chart each need the same three facts about an arm: its equity
#     curve, its per-trade log, and whether it is deployed below 100%. Those facts
#     are spread over three files with three naming conventions:
#
#         v1, v2   equity in v2FINAL_equity.csv     (arm-keyed on the live
#                  universes, `strategy`/`baseline_invvol` on the frozen ones)
#         v3, v4   equity in v34_equity.csv
#         v1       trades in daily_trades_v1_<tag>.csv   -- written by the engine
#         v2       trades in daily_trades_<tag>.csv      -- the v2 audit trail
#         v3, v4   trades in daily_trades_<tag>_<arm>.csv -- the per-arm trails
#
#     Four charts each rediscovering that is four chances to disagree. They ask
#     here instead.
#
# AVAILABILITY IS A FACT, NOT AN ERROR
#     A frozen universe has no v3 or v4 at all, and an arm-subset run has no files
#     for an arm it did not measure. available() answers which arms this universe
#     can actually show, and the caller decides what to do about the rest. That is
#     why nothing here raises.

def _axes(*, for_arm_subset=False):
    """This run's artefact name tail: cadence AND profile AND tax, never a subset.

    ALL THREE OR NONE. The profile was absent here while `cadence` was present,
    which is the whole shape of the bug this function was rewritten to remove --
    and then the TAX term was absent while both of the others were present, which
    is the same bug a second time in the same function.

    MEASURED 2026-09-18, BEFORE THE FIX: under `--tax on` this returned
    v2FINAL_equity.csv, daily_trades_midcap50.csv and v34_equity.csv -- byte-
    identical paths to the tax=off selection. This is make_chart's source lookup
    (STEP 10t), so chart_<tag>_..._tax.png was drawn with a correct name over
    UNTAXED arm series, while reports.py's own _ci() composed all four
    axes. ONE STEP, TWO CONVENTIONS, and the chart that came out of it was
    part-taxed rather than wrong in a way anybody would notice.

    THE RULE THIS FUNCTION NOW FOLLOWS is reports.py's, which is the same
    chain in the same order. See KNOWN_ISSUES.md instance 6: this is the fourth
    time a hand-composed chain has been under-specified, and the reason the list
    of thirteen such sites is worth reading before adding a fifth axis.
    """
    import settings
    from settings import tax as _tax
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    sfx = cadence.suffix() + settings.profile_axis.suffix() + _tax.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix()
    # THE CORE PART OF THE SELECTION names the v34 files: a stop arm in the
    # selection goes to v34_stop_* and does not rename them.
    core = [n for n in arm_reg.selected_names() if n in arm_reg.ARMS]
    return (arm_reg.selection_suffix(core) + sfx) if for_arm_subset else sfx


def describe(path, n=None, unit="rows"):
    """A provenance line naming the file a figure was actually read from.

    FORMAT TAKEN FROM `diagnostics/attribution_v2.txt`, which already prints
    `source daily_trades_n100.csv, 978 fills, mtime 2026-09-04 14:02 (local)`.
    The precedent and the format both existed; nothing else used them.
    """
    from datetime import datetime
    path = Path(path)
    try:
        mt = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        mt = "unknown"
    count = f", {n:,} {unit}" if n is not None else ""
    return f"source {path.name}{count}, mtime {mt} (local)"


def equity_path_and_series(M, tag, arm_name):
    """(source file, curve) for one arm, or (None, None) if THIS RUN did not write one.

    FAIL-CLOSED. THERE IS NO FALLBACK TO A DIFFERENT FILE, BY DESIGN.
    This function used to compose `v2FINAL_equity{cadence}.csv`, and when that did
    not exist fall through to the unsuffixed `v2FINAL_equity.csv`. The v34 chain
    fell through twice, ending at a bare `v34_equity.csv`. Neither rung composed
    the PROFILE at all.

    WHAT THAT COST, MEASURED. The engines suffix their output by cadence AND
    profile (`engine_v2_final_mid.py:_c`). So under `--profile tradeable` the
    engine wrote `v2FINAL_equity_tradeable.csv`, this function looked for
    `v2FINAL_equity.csv`, found the RESEARCH file, and returned research curves to
    a caller drawing a chart titled tradeable. Silently, and with the substitution
    unrecorded: the caller received the path and discarded it.

    THIS IS NOT HYPOTHETICAL AND IT IS NOT NEW. `reports.py`'s
    `_ci` carried exactly this defect -- cadence composed, profile omitted, silent
    fall-through to the canonical file -- and it fed THESE SAME THREE CHARTS. It
    was found and fixed on 2026-09-12. This function is the same defect in the same
    repository on the same code path, and it survived that fix because the audit
    measured writers and nothing measured readers.

    THE PATTERN IS `backtest_runs.py`, three files away, which has composed
    both axes and returned None rather than substituting since the profile existed.
    Its docstring records the measured cost of the cadence half: reconciling a
    cadence-40 trail against a cadence-20 curve reported v1 MISMATCH Rs 2,923,934
    and v2 MISMATCH Rs 1,825,210 on midcap150. Returning None there made it safe BY
    DESIGN rather than by accident. This does the same.

    None means THIS RUN did not write a curve for this arm. The caller reports that
    and plots nothing, which is the correct outcome: a chart with a curve missing
    is a visible defect, and a chart with the wrong curve is not.
    """
    from market_data import read_table  # lazy: this module is imported without the repo root on sys.path
    M = Path(M)
    # A STOP ARM'S CURVE IS IN THE COMPANION FILE, and only there.
    if arm_name in arm_reg.STOP_ARMS:
        g = M / f"v34_stop_equity{arm_reg.stop_selection_suffix()}{_axes()}.csv"
        if g.exists():
            df = read_table(g, parse_dates=["date"]).set_index("date")
            col = arm_reg.STOP_ARMS[arm_name].equity_column
            if col in df.columns:
                return g, df[col]
        return None, None
    # ONE NAME PER CHAIN. Not a candidate list -- a candidate list IS the fallback.
    f = M / f"v2FINAL_equity{_axes()}.csv"
    if f.exists():
        df = read_table(f, parse_dates=["date"]).set_index("date")
        s = arm_reg.equity_series(df, arm_name)
        if s is not None:
            return f, s
    # v3/v4 are measurement arms and live in the v34 panel. The arm-subset suffix is
    # part of the composed name, not a rung above a canonical one: an arm-subset run
    # writes v34_equity_v1_v3.csv, and the four-arm file left over from an earlier
    # run describes a selection this run did not make. At a full selection
    # selection_suffix() is "" and this IS the canonical name.
    g = M / f"v34_equity{_axes(for_arm_subset=True)}.csv"
    if g.exists():
        df = read_table(g, parse_dates=["date"]).set_index("date")
        col = arm_reg.ARMS[arm_name].equity_column
        if col in df.columns:
            return g, df[col]
    return None, None


def trades_path(M, tag, arm_name):
    """The per-trade log THIS RUN wrote for one arm, or None. Fail-closed.

    THE THREE SPELLINGS ARE HISTORICAL AND ARE NOT UNIFIED HERE. v2's log is
    unsuffixed in its BODY because the Nautilus verification reads that exact name;
    v1's is written by the engine under its own older spelling; v3 and v4 use the
    per-arm audit trail. Renaming any of them is a separate change with its own gate.

    WHAT WAS REMOVED. Each spelling used to be tried twice -- once with the cadence
    suffix and once without -- so a run whose composed log was absent silently read
    the unsuffixed one. As with the curve above, the profile was never composed at
    all, so a tradeable run read the research trade log and computed a before-TC
    figure from costs that were never incurred. The axis tail is now composed once
    and there is no second rung.
    """
    M = Path(M)
    sfx = _axes()
    for cand in ({"v1": f"daily_trades_v1_{tag}{sfx}.csv",
                  "v2": f"daily_trades_{tag}{sfx}.csv"}.get(arm_name),
                 f"daily_trades_{tag}_{arm_name}{sfx}.csv"):
        if cand is not None and (M / cand).exists():
            return M / cand
    return None


def available(M, tag, names=None):
    """The arms this universe can actually show, in ARMS order.

    An arm counts only when BOTH its curve and its per-trade log are on disk: the
    charts quote a before-TC CAGR, which is the curve with the cost drag removed,
    so a curve without its costs would be plotted with a silently wrong legend.
    """
    want = arm_reg.selected_names() if names is None else [
        a.name if hasattr(a, "name") else a for a in names]
    out = []
    for n in arm_reg.ALL_ARMS:
        if n not in want:
            continue
        _, s = equity_path_and_series(M, tag, n)
        if s is not None and trades_path(M, tag, n) is not None:
            out.append(n)
    return out


def deployed_pct(arm_name, breadth_inv, summary=None):
    """Average deployed capital for an arm, in percent.

    The breadth-scaled arms (v2, v4) deploy `breadth_inv`; the always-invested
    ones (v1, v3) deploy 100. v2 and v4 share a number because breadth is
    mean(mom20 > 0) and does not depend on the sizing rule -- the two arms differ
    in how they split the money, not in how much of it they put to work.

    A STOP ARM (v5, v6) IS MEASURED, not assumed: the share of days on which it
    held any stock, from its daily_summary frame passed as `summary`.
    """
    a = arm_reg.get(arm_name)
    if a.stop is not None:
        if summary is None:
            raise ValueError(f"{arm_name}: a stop arm's deployed share needs its daily summary")
        return int(round(100 * float((summary["n_stocks"] > 0).mean())))
    return breadth_inv if a.mode == "breadth" else 100
def _window_label(eq=None):
    """One line naming the window every figure on the chart belongs to.

    ADDED 2026-09-02. Three different trade counts on three different windows
    once appeared on one chart with none of them labelled: 981 research fills on
    the 1,836-day window, 978 port fills on the same window, and 997 fills from a
    depth study on the retired 1,842-day window. A trade count without its window
    is not checkable, and a CAGR without its window has already been quoted
    against the wrong one in this project.
    """
    import settings
    n = f", {len(eq):,} trading days" if eq is not None else ""
    return (f"WINDOW {settings.BT_START_DATE.date()} to {settings.BT_END_DATE.date()}{n} -- "
            f"every CAGR, Sharpe, drawdown and TRADE COUNT on this page is on that "
            f"window and no other.")
def cum(s): return (s/s.iloc[0]-1)*100
def dd(s):  return (s/s.cummax()-1)*100
def cagr(s):
    y = (s.index[-1]-s.index[0]).days/365.25
    return ((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100
def sharpe(s):
    r = s.pct_change().dropna()
    return r.mean()/r.std()*np.sqrt(252) if r.std() > 0 else 0.0
def before_tc(eq, log):
    """CAGR with the transaction-cost drag removed from the realised path:
    r_gross = r_net + tc/equity(t-1), compounded. Not a zero-cost re-run.

    A MISSING LOG IS FATAL HERE, AND IT USED TO BE A ZERO. Back-ported from
    make_n100_chart.py on 2026-09-13, where `baa5daa` fixed it on 2026-09-12.
    **midcap150 has been substituting zeros for the intervening day, and for the whole
    life of the file before that.**

    It returned `(None, 0.0, 0)` when the file was absent -- a tuple
    indistinguishable from a real result of zero trades at zero cost. Two things
    follow, and the worse one is not the crash:

      - the step prints "trades 0, TC Rs 0" for an arm the engine reported
        hundreds of trades for, and
      - it dies about thirty lines later formatting the None into a chart
        subtitle, with `TypeError: unsupported format string passed to
        NoneType.__format__` and no mention of the file.

    THE CRASH IS THE LUCKY OUTCOME. The unlucky one is a chart rendering a curve
    labelled "0 trades, Rs 0" that a reader takes for a measurement. That is the
    same defect that surfaced as the STEP 10h crash on nifty100 -- it crashed there
    only because nifty100 reached the formatting line first.

    The caller's job is not to call this for an arm the run did not select. That
    is what ARMS_ON is for.
    """
    if not Path(log).exists():
        raise FileNotFoundError(
            f"{log} is missing, so the before-TC figure for this series cannot be "
            f"computed.\n"
            f"  This is NOT the same as zero trades at zero cost, which is what "
            f"this function used to return.\n"
            f"  If the arm was not selected, do not ask for its curve -- build the "
            f"series from ARMS_ON.")
    tr = read_table(log, parse_dates=["date"])
    tc = tr.groupby("date")["tc"].sum().reindex(eq.index).fillna(0.0)
    g = (1 + eq.pct_change().fillna(0.0) + (tc/eq.shift(1)).fillna(0.0)).cumprod()*eq.iloc[0]
    return cagr(g), tc.sum(), len(tr)


def _ci(path):
    """This run's cadence-, profile- and tax-named sibling of `path`.

    THE LITERAL STAYS IN THE CALL -- `_ci(M / "<name>")` -- so
    check_pipeline_order still reads this step's edges out of the source. At the
    default cadence the suffix is empty and this returns the path unchanged.

    Under --rebal 40 the engine wrote v2FINAL_equity_r40.csv and left the
    canonical cadence-20 file alone; reading the canonical one here would plot a
    cadence-20 curve on a chart whose title says 40.

    THE PROFILE IS PART OF THE SIBLING'S NAME TOO, as of 2026-09-12. Before that
    the engines ignored the profile entirely and wrote capped `tradeable` numbers
    into the canonical filenames, so there was no sibling to find and this helper
    could not have been wrong. Now that the engines suffix their output, a
    tradeable run must read the tradeable file or it would plot research curves
    under a tradeable title.
    """
    from settings import cadence as _cd
    import settings
    from settings import tax as _tax
    # THE TAX AXIS JOINS THE SIBLING'S NAME (2026-09-17): under tax=on the engine
    # wrote v2FINAL_equity_tax.csv, and reading the canonical file here would
    # plot an untaxed curve on a chart whose title says otherwise.
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    if (_cd.is_default() and settings.profile_axis.is_default() and _tax.is_default() and _sva.is_default()
            and _dda.is_default() and _capa.is_default() and _impa.is_default() and _pca.is_default() and _fxa.is_default() and _sta.is_default() and settings.shortfall_axis.is_default()):
        return path
    c = path.with_name(path.stem + _cd.suffix() + settings.profile_axis.suffix() + _tax.suffix()
                       + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix() + path.suffix)
    # NO FALLBACK TO THE CANONICAL FILE, 2026-09-23. This returned `path` when
    # the sibling was absent, so a missing non-default artefact was silently
    # replaced by the published cadence-20 research one and plotted under this
    # run's title. The sibling's name is returned whether or not it exists, and a
    # missing one fails at the read, naming the file this run should have made.
    return c


def chart_path(M, stem, arms_on):
    """This run's name for the chart, over all four axes. THE ONE DEFINITION.

    A NAMED FUNCTION SO GATE 2 CAN MEASURE IT. The composition used to live in the
    two `_render(...)` call sites, which meant the write call itself received a
    bare local -- `savefig(_path)` -- and naming_declare_check could see nothing to
    verify. It refused to credit the declaration, correctly: an enforcement check
    that accepts "trust me, the caller composed it" is not enforcing anything.

    The rule is unchanged from the call sites it replaces. The canonical two-arm
    figure keeps its bare name, and every other selection gets one of its own.
    """
    import settings
    from settings import tax as _tax
    asf = arm_reg.suffix(arms_on) if set(arms_on) != {"v2", "v1"} else ""
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    import settings
    return M / (stem + asf + cadence.suffix() + settings.profile_axis.suffix() + _tax.suffix()
                + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix() + ".png")


def make_chart(u):
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything here used to run at module level,
    so importing this file executed the whole step as a side effect -- which is
    why the pipeline could only ever spawn it as a subprocess.
    """
    # EVERY PER-UNIVERSE VALUE COMES FROM THE REGISTRY. `tag` is a plain local and
    # is used in f-strings as "{tag}" because check_pipeline_order substitutes that
    # placeholder and no other.
    tag = u.tag
    _CT = u.chart_text
    _RULE = "=" * _CT["rule_width"]
    # THESE HELPERS CLOSE OVER main()'s LOCALS, so they live inside it.
    # Leaving them at module level while the names they read moved in here
    # raised NameError at the first call -- the wrap is only sound if a
    # helper travels with the state it reads.
    def score_panel_path():
        """This universe's score panel, resolved through the shared guard so a
        missing cache reports which file is absent instead of crashing mid-run."""
        return model.require_cache(u.score_cache,
                                    what=u.engine_text["panel_what"])
    M = Path(u.metrics_dir)
    CAP = 1_000_000
    CUT = settings.BT_START_DATE
    eq = read_table(_ci(M/"v2FINAL_equity.csv"), parse_dates=["date"]).set_index("date")
    # THE TWO ARMS THIS CHART SHOWS, ASKED FOR BY NAME rather than by the column
    # each happened to be stored under. arms/registry.equity_series falls back to
    # the legacy `strategy`/`baseline_invvol` names, so this reads a frozen
    # universe's file too.
    _v2 = arm_reg.equity_series(eq, "v2")
    _v1 = arm_reg.equity_series(eq, "v1")
    params = json.loads((_ci(M/"v2FINAL_params.json")).read_text())
    inv = params["avg_exposure_pct"]
    idx_raw = (market_data.read_price_csv(u.index_file)[["date","close"]].dropna()
               .set_index("date")["close"].sort_index())
    s = idx_raw.reindex(eq.index.union(idx_raw.index)).ffill().reindex(eq.index)
    index = CAP*s/s.iloc[0]
    late, alive = [], 0
    # SORTED, because the registry hands back a SET. The per-universe config lists
    # were ordered and this loop only prints, so the sole effect is the order of
    # the late-lister list in the console. No artefact reads it.
    _syms = sorted(u.symbols())
    _raw = u.prepare_data_dir()
    for sym in _syms:
        d = market_data.read_price_csv(_raw/f"{sym}.csv")[["date","close"]].dropna()
        if d["date"].min() > CUT:
            late.append(sym)
        else:
            alive += 1
    n_all, n_late = len(_syms), len(late)
    print(_RULE)
    print(f" {u.label} -- every number printed before anything is plotted")
    print(_RULE)
    print(f"\n  universe          : {n_all} constituents "
          f"(index {u.index_name} excluded by name, not by glob)")
    print(f"  panel symbols     : {params.get('n_symbols', 'see engine output')}")
    print(f"  backtest window   : {eq.index[0].date()} -> {eq.index[-1].date()}")
    print(f"\n  INDEX FILE {u.index_file.name}")
    print(f"    base            : {idx_raw.index[0].date()} = {idx_raw.iloc[0]:,.2f}"
          f"   (NSE base 1-Apr-2005 = 1000)")
    print(f"    full series     : {idx_raw.index[0].date()} -> {idx_raw.index[-1].date()}, "
          f"{len(idx_raw):,} rows")
    _w = idx_raw[(idx_raw.index >= CUT) & (idx_raw.index <= pd.Timestamp(_CT["index_window_end"]))]
    _y = (_w.index[-1]-_w.index[0]).days/365.25
    # THE LABEL IS DERIVED FROM THE SLICE, NOT RETYPED BESIDE IT. This read
    # `2019-01-01 -> 2026-06-08` as a hardcoded literal while the upper bound came
    # from chart_text["index_window_end"], so the two could -- and did -- diverge:
    # the literal was midcap150's, and nifty100 (bound 2026-08-06) and nifty50
    # (bound 2026-08-26) both printed 2026-06-08 over numbers measured to their
    # own bound. Taking the endpoints off _w itself makes divergence impossible,
    # and reports the sessions actually measured rather than the bound requested --
    # a bound landing on a holiday is not the last row in the slice.
    print(f"    {_w.index[0].date()} -> {_w.index[-1].date()}: "
          f"{_w.iloc[0]:,.2f} -> {_w.iloc[-1]:,.2f} = "
          f"{_w.iloc[-1]/_w.iloc[0]:.4f}x = CAGR {((_w.iloc[-1]/_w.iloc[0])**(1/_y)-1)*100:.4f}%")
    # THE `expected` LINE WAS DELETED HERE, AND MUST NOT COME BACK AS A DERIVED
    # VALUE. It printed a hardcoded "6,342 -> 21,926 = 3.46x = 18.16% CAGR" for
    # EVERY universe -- midcap150's figure, shown beneath nifty100's 2.3103x and
    # nifty50's 2.2188x. It was right for one of three, and since 43fbd2f moved
    # midcap150's window bound to 2026-08-06 it was right for none.
    #
    # DERIVING IT FROM `_w` WOULD MAKE IT AGREE BY CONSTRUCTION. A cross-check fed
    # by its own subject is a tautology: it would print a green-looking line that
    # cannot fail, which is worse than no line. The only thing that earns a
    # registry field here is the INDEX PROVIDER'S OWN PUBLISHED RETURN for this
    # span, per universe, and this repository does not have it. Until it does,
    # there is no check to make -- so none is printed.
    # THE CADENCE-NAMED LOGS. The literals stay in the call for
    # check_pipeline_order; _ci picks the _r40 sibling when the engine wrote one.
    # Reading the canonical logs under --rebal 40 gave before_tc a file that does
    # not exist, and it returns (None, 0, 0) silently -- a legend reading
    # "CAGR None% before TC" rather than a crash.
    # COMPUTED ONLY FOR SELECTED ARMS. The literals stay in the call so
    # check_pipeline_order still reads this step's edges out of the source; the
    # GUARD is what changed, exactly as the engine's write is guarded -- and
    # exactly as make_n100_chart has done since baa5daa.
    #
    # 905e598 BACK-PORTED HALF OF baa5daa AND SAID SO WRONGLY. It brought the
    # fatality (a missing log raises instead of returning a fake zero) and left
    # the arm-awareness behind, then reasoned: "The --arm v3 path does not ask
    # for v1's curve, so the regression run does not exercise the changed
    # branch." The line above it asked for v1's curve unconditionally, so the
    # v3 path reached the new raise and died there. `--universe midcap150 --arm v3`
    # was unrunnable from 905e598 until this commit, and the claim that it
    # could not reach the branch is why nobody looked.
    _sel = set(arm_reg.selected_names())
    b_v2 = before_tc(_v2, _ci(M/f"daily_trades_{tag}.csv")) if "v2" in _sel else None
    b_v1 = before_tc(_v1, _ci(M/f"daily_trades_v1_{tag}.csv")) if "v1" in _sel else None
    # EVERY SELECTED ARM THIS UNIVERSE CAN SHOW, in published order. The two
    # literals above are kept: check_pipeline_order resolves this step's inputs
    # from them, and they are also v2's and v1's own entries below.
    # ARMS is {name: (curve, before_tc tuple, colour, deployed%)}.
    ARMS_ON = {}
    # THE STOP ARMS' DAYS IN CASH, shaded on the chart: {arm: [(first, last), ...]}.
    CASH_SPANS = {}
    for _n in ("v2", "v1", "v3", "v4", "v5", "v6"):
        if _n not in set(arm_reg.selected_names()):
            continue
        if _n == "v2":
            _e, _b, _c = _v2, b_v2, "#c0392b"
        elif _n == "v1":
            _e, _b, _c = _v1, b_v1, "#2e6da4"
        else:
            # THE PATH IS KEPT AND PRINTED, not discarded. It used to be bound
            # to `_` here, so when the reader silently substituted a different
            # file nothing in the output said which file had been plotted. The
            # reader is fail-closed now; naming the source is what makes that
            # visible rather than merely true.
            _src, _e = equity_path_and_series(M, tag, _n)
            _lg = trades_path(M, tag, _n)
            if _e is None or _lg is None:
                print(f"    {_n}: no curve or trade log written by THIS run's "
                      f"axes -- not plotted")
                continue
            print(f"    {_n}: {describe(_src, len(_e), 'sessions')}")
            print(f"    {_n}: {describe(_lg)}")
            _b = before_tc(_e, _lg)
            _c = {"v3": "#1b9e77", "v4": "#e6ab02", "v5": "#08306b", "v6": "#00441b"}[_n]
        _summ = None
        if arm_reg.get(_n).stop is not None:
            import backtest_runs as _as
            _summ = read_table(M / f"daily_summary_{_as.artefact_tag(u, _n)}.csv",
                               parse_dates=["date"])
            _out = (_summ["n_stocks"] == 0).to_numpy()
            _spans, _start = [], None
            for _k, _o in enumerate(_out):
                if _o and _start is None:
                    _start = _k
                if (not _o or _k == len(_out) - 1) and _start is not None:
                    _end = _k if _o else _k - 1
                    _spans.append((_summ["date"].iloc[_start], _summ["date"].iloc[_end]))
                    _start = None
            CASH_SPANS[_n] = _spans
        ARMS_ON[_n] = (_e, _b, _c, deployed_pct(_n, inv, _summ))
    _AD = {"v1": "inv-vol", "v2": "breadth", "v3": "provol", "v4": "provol-breadth",
           "v5": "inv-vol + stop", "v6": "provol + stop"}
    print("\n  HEADLINE NUMBERS")
    print(f"    {'series':<42} {'before TC':>10} {'after TC':>9} "
          f"{'Sharpe':>7} {'MaxDD%':>8} {'inv%':>5}")
    rows = [(f"{tag} {_n} ({_AD[_n]})", _d[0], _d[1][0], _d[3])
            for _n, _d in ARMS_ON.items()] + [
            (f"{tag} buy&hold (equal-weight universe)", eq["buyhold"], None, 100),
            (f"{u.index_name} (cap-weighted index)", index, None, 100)]
    for lab, s_, b, iv in rows:
        bt = f"{b:>9.2f}%" if b is not None else f"{'--':>10}"
        print(f"    {lab:<42} {bt} {cagr(s_):>8.2f}% {sharpe(s_):>7.2f} "
              f"{dd(s_).min():>7.2f}% {iv:>4}%")
    # THE IC / EXTREME-RETURN DIAGNOSTIC BLOCK, midcap150 only, and declared as such.
    # Console output with no artefact, but it RE-READS THE SCORE PANEL, so
    # running it for a universe that never had it is new work rather than new
    # formatting. Preserved as per-universe data; switching it on for nifty100 is a
    # change to what that run does and belongs in its own commit.
    if _CT["diagnostics"]:
        ic = read_table(score_panel_path(), usecols=["date","symbol"], parse_dates=["date"])
        ic = ic[ic["date"] >= settings.BT_START_DATE]
        per_day = ic.groupby("date")["symbol"].nunique()
        n_panel = ic["symbol"].nunique()
        print("\n  PANEL DENSITY -- the blocker that made the first MidCap150 run invalid")
        print(f"    symbols in the scored panel      : {n_panel} of {n_all}")
        print(f"    symbols priced on a given day    : min {per_day.min()}, median "
              f"{int(per_day.median())}, max {per_day.max()}")
        print( "    RESOLVED 2026-08-13. idio_vol_60 and beta_60 were computed by rolling(60)")
        print( "    over the UNION date index, so every day a midcap did not trade voided its")
        print( "    next 60 windows and those rows were dropped. Coverage was 35.7% and 42.1%")
        print( "    against 93.8-100% for the other 15 features, only 65 of 148 names were ever")
        print( "    scored, breadth read 0.202, and deployment collapsed")
        print( "    to about 20%. Both features are now computed on each symbol's own trading")
        print( "    index. The first MidCap150 result (CAGR 9.06%)")
        print( "    was an artefact of that bug and must not be quoted.")
        _px = read_table(score_panel_path(), parse_dates=["date"]) \
                .pivot_table(index="date", columns="symbol", values="close").ffill()
        _bd = _px.index[(_px.index >= settings.BT_START_DATE)
                        & (_px.index <= settings.BT_END_DATE)]
        _r = _px.pct_change().loc[_bd]
        _ext = _r.stack(); _ext = _ext[_ext.abs() > 0.55].sort_values(key=abs, ascending=False)
        _m = _r.mean(axis=1)
        _y = (_bd[-1]-_bd[0]).days/365.25
        # TWO NEUTRALISATIONS, AND THEY ANSWER DIFFERENT QUESTIONS. Until 2026-09-13
        # only the second existed and it was printed immediately after the artefact
        # count, in the next sentence, so it read as the artefact effect. It is not:
        # the two day-sets have ZERO overlap and should, because one symbol at +548.8%
        # carries 1/148 of an equal-weight index and moves it about 3.7%, while the
        # largest benchmark days are broad COVID-rebound moves.
        #
        # That conflation was read off this output and transcribed into KNOWN_ISSUES,
        # where it was then "corrected" in the wrong direction. See KNOWN_ISSUES.md,
        # "The midcap150 benchmark is better defined than this file said".
        _art = sorted({_d for (_d, _s) in _ext.index})          # the artefact days
        _m_art = _m.copy()
        for _d in _art:
            if _d in _m_art.index: _m_art.loc[_d] = 0.0
        _bh_art = ((1+_m_art).prod())**(1/_y)*100-100
        _top = _m.sort_values(ascending=False).head(6).index    # largest benchmark days
        _m_ex = _m.copy()
        for _d in _top: _m_ex.loc[_d] = 0.0
        _bh_ex = ((1+_m_ex).prod())**(1/_y)*100-100
        print("\n  *** DO NOT QUOTE THE BUY&HOLD NUMBER WITHOUT THIS ***")
        print(f"    The PRICE panel still contains {len(_ext)} single-day moves above 55% inside the")
        print( "    backtest window. The extreme-return filter masks ret_1d, which protects the")
        print( "    FEATURES and the LABEL, but buy&hold and the execution prices are computed")
        print( "    from `close` directly, so the filter cannot reach them.")
        # ALL OF THEM, NOT head(4). Printing four under a count of six invited the
        # reader to match the list against the six-day neutralisation below, which is
        # a different six entirely.
        for (_d, _s), _v in _ext.items():
            print(f"      {_d.date()}  {_s:<12} {_v:+,.1%}")
        print(f"    Worse, masking a return DROPS that row, and the ffill then releases the whole")
        print( "    accumulated level shift as one day when the symbol reappears. PATANJALI")
        print( "    (formerly Ruchi Soya) moved ~250x between Jan and Jul 2020 on a tiny post-")
        print( "    insolvency float; the drop concentrated that into a single +24,773% day.")
        print(f"    Effect on the benchmark -- TWO DIFFERENT NEUTRALISATIONS, both stated")
        print(f"    because they answer different questions and their day-sets do not overlap:")
        print(f"      buy&hold as computed                                  {cagr(eq['buyhold']):.2f}%")
        print(f"      with the {len(_art)} ARTEFACT days above neutralised          {_bh_art:.2f}%"
              f"   <- the artefact sensitivity")
        print(f"      with the 6 largest BENCHMARK days neutralised         {_bh_ex:.2f}%"
              f"   <- NOT an artefact figure")
        print(f"    The second set is {', '.join(str(_d.date()) for _d in sorted(_top))},")
        print(f"    which contains none of the artefact days. It measures how much of the")
        print(f"    benchmark rests on its six best days, which is a different question.")
        print(f"    The cap-weighted index returns {cagr(index):.2f}%, which is the number to trust.")
        print( "    FIXING THIS NEEDS A DECISION, NOT A THRESHOLD: a symbol's history before a")
        print( "    corporate event of this size is effectively a different security and should")
        print( "    probably be truncated, not stitched. That is a data-handling choice and is")
        print( "    left open rather than made silently.")
    print(f"\n  SURVIVORSHIP -- read the buy&hold line with this in mind")
    print(f"    {n_late} of {n_all} constituents have NO data at 2019-01-01 "
          f"(listed later): {', '.join(late[:8])}{' ...' if n_late > 8 else ''}")
    print(f"    {alive} of {n_all} existed on 2019-01-01.")
    # ONE PARAGRAPH FOR EVERY UNIVERSE, SINCE 2026-09-30. This was a per-universe
    # registry field, churn_note. midcap150's and nifty100's said "midcaps that
    # FELL OUT of the index" and quoted "about 10 points of CAGR" from a
    # measurement nothing in the repository records; the other six said
    # "NOTHING HAS BEEN MEASURED", which survivorship_attribution.py has since
    # made untrue. What is true of all eight is stated once, from the window.
    _y0, _y1 = settings.BT_START_DATE.year, settings.BT_END_DATE.year
    for _line in (
            f"Names that left the index or delisted between {_y0} and {_y1} are absent",
            "from this file entirely: the universe is today's members backfilled. They",
            "may have done better or worse than the names that stayed, so the sign of",
            "this bias is not known from this data. diagnostics/survivorship_attribution.txt",
            "estimates how much of a run's profit came from names held while not index",
            "members. The equal-weight buy&hold line is a portfolio nobody could have",
            "held, and is NOT achievable."):
        print(f"    {_line}")
    # THE SUBTITLE IS PER-UNIVERSE PROSE AND IT REACHES THE PNG, so it lives in the
    # registry as a callable and this step only supplies the values. The previous
    # version of this merge inlined midcap150's subtitle for both universes; it read
    # n_panel and per_day, which only midcap150's diagnostics block binds, so nifty100 died
    # with UnboundLocalError at STEP 10h and wrote neither its chart nor its daily
    # log. gate_compare's UNCLASSIFIED branch is what caught it.
    _vals = {"n_all": n_all, "n_late": n_late, "alive": alive,
             "inv": inv, "index_name": u.index_name}
    # WHICH ARMS ARE INVESTED HOW MUCH IS SAID PER CHART, from the arms on it.
    # The subtitle said "v2 holds X% invested" on every chart, including a
    # v4-only chart where X was v2's exposure. 2026-09-23.
    def _sub(arms):
        held = ", ".join(f"{n} holds {d[3]:.0f}% invested" for n, d in arms.items())
        return (_window_label(eq) + "\n" + _subtitle(dict(_vals, held=held))
                + market_data.describe_state())

    # ONE SUBTITLE FOR EVERY UNIVERSE, from the registry and this run's axes.
    # The eight per-universe versions it replaces claimed a direction for the
    # survivorship bias ("inflated"), quoted "about 10 CAGR points" from an
    # unrecorded measurement, said no liquidity study existed where one does
    # (diagnostics/liquidity_participation.txt covers all eight), and printed
    # "research ... flat 0.15% slippage" on tradeable and taxed charts.
    def _subtitle(v):
        import textwrap
        val = ("Validation on record for this universe: validation_status in "
               "v2FINAL_params.json."
               if isinstance(u.validation_status, dict) else
               "No seed, sub-period, shuffle or top-N validation has been run on "
               "this universe (validation_status in v2FINAL_params.json).")
        paras = [
            f"{u.label}, index excluded by name  |  {v['held']} on average  |  "
            f"{settings.cost_basis()}",
            f"Benchmarks: {v['index_name']} is the published CAP-WEIGHTED index "
            f"(investable, and NOT survivorship-biased). Equal-weight buy&hold is "
            f"the universe, and is NOT investable.",
            f"SURVIVORSHIP: these {v['n_all']} are TODAY'S index members backfilled "
            f"to {settings.BT_START_DATE.year}, and {v['n_late']} of them did not exist "
            f"at the start. Names that left during the window are absent entirely, "
            f"so the sign of the bias is not known. Do not read that buy&hold as "
            f"achievable.",
            val + " Slippage has no market-impact model; fill sizes against "
            "volume are in diagnostics/liquidity_participation.txt."]
        return "".join(textwrap.fill(p, 175) + "\n" for p in paras)
    # ONE LINE PER SELECTED ARM, in published order, each with its own colour.
    # v2 and v1 keep the exact colours and label shapes they have always had, so
    # the default chart is unchanged.
    # THE CHARTS THIS RUN ACTUALLY WROTE. Both _render calls below are CONDITIONAL
    # and neither is guaranteed, so nothing outside this list can say what exists.
    _rendered = []

    def _render(_arms, _path):
        """Build and save the chart for exactly these arms."""
        series = [
         (f"{tag} {_n} ({_AD[_n]})  [inv {_d[3]}%]", _d[0], _d[2], "-",
          f"CAGR {_d[1][0]:.2f}% before TC / {cagr(_d[0]):.2f}% after TC"
          f"  [{_d[1][2]} trades, Rs {_d[1][1]:,.0f}]")
         for _n, _d in _arms.items()] + [
         (f"{tag} buy&hold (equal-weight universe"
          f", NOT investable)  [inv 100%]", eq["buyhold"],
          "#3a9d3a", "-", f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"),
         (f"{u.index_name} (cap-weighted index)  [inv 100%]", index, "#000000", "--",
          f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"),
        ]
        fig, ax = plt.subplots(2, 1, figsize=(16, 11), height_ratios=[2, 1])
        for lab, s_, c, ls, extra in series:
            ax[0].plot(s_.index, cum(s_), lw=2.0, color=c, ls=ls, label=f"{lab}  {extra}")
        for _n in _arms:
            for _a, _b in CASH_SPANS.get(_n, []):
                ax[0].axvspan(_a, _b, color=_arms[_n][2], alpha=.08, lw=0)
        ax[0].axhline(0, color="k", lw=.6, alpha=.5)
        ax[0].set_ylabel("Cumulative return (%)")
        ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax[0].set_title(settings.run_label(u.label, _arms) + "\n" + _sub(_arms), fontsize=9.5)
        ax[0].legend(loc="upper left", fontsize=8.5); ax[0].grid(alpha=.3)
        for lab, s_, c, ls, _ in series:
            ax[1].plot(s_.index, dd(s_), lw=1.4, color=c, ls=ls,
                       label=f"{lab.split('  [')[0]} (max {dd(s_).min():.1f}%)")
        ax[1].set_ylabel("Drawdown (%)")
        ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax[1].legend(loc="lower left", fontsize=_CT["legend_fontsize"]); ax[1].grid(alpha=.3)
        plt.tight_layout()
        # naming: arm,cadence,profile via chart_path -- _render receives a path
        # compose from arm_reg.suffix(), cadence.suffix() and settings.profile_axis.suffix();
        # the canonical two-arm figure is written only at an all-default selection.
        plt.savefig(_path, dpi=_CT["dpi"], bbox_inches="tight", metadata={"Title": ax[0].get_title().split("\n")[0]}); plt.close()
        _rendered.append(_path)

    # ------------------------------------------------------------------
    # TWO CHARTS, THE SAME RULE THE COMBINED CHART ALREADY USES.
    # ------------------------------------------------------------------
    # A COLD RUN FOUND THIS, AND NO WARM ONE COULD HAVE. The canonical
    # savefig was gated on the selection BEING exactly {v2, v1}, so the
    # DEFAULT `--arm all` wrote only chart_midcap150_FINAL_v1_v2_v3_v4.png and never
    # wrote chart_midcap150_FINAL.png at all. Every byte-comparison passed, because the
    # canonical file was still on disk from before the change and nothing
    # overwrote it. Only a run from an empty tree showed it absent.
    #
    # CANONICAL: always exactly v2 and v1, drawn whenever both are selected.
    # THE TAX AXIS IS IN BOTH CONDITIONS, 2026-09-23. It was missing from both,
    # so a `--tax on` run with default cadence and profile drew TAXED curves into
    # the canonical chart_<stem>.png and wrote no taxed chart of its own.
    from settings import tax as _tax
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    # THE SURVIVORSHIP AXIS JOINS BOTH CONDITIONS, 2026-10-10, for the reason tax
    # did: without it a pit run drew pit curves into the canonical chart.
    _axes_default = (cadence.is_default() and settings.profile_axis.is_default() and _tax.is_default()
                     and _sva.is_default() and _dda.is_default()
            and _capa.is_default() and _impa.is_default() and _pca.is_default() and _fxa.is_default() and _sta.is_default() and settings.shortfall_axis.is_default())
    _canon = {n: d for n, d in ARMS_ON.items() if n in ("v2", "v1")}
    if len(_canon) == 2 and _axes_default:
        _render(_canon, M / f"{_CT['stem']}.png")

    # SELECTION: exactly what this run selected, into its own name.
    if set(ARMS_ON) != {"v2", "v1"} or not _axes_default:
        _asf = arm_reg.suffix(ARMS_ON) if set(ARMS_ON) != {"v2", "v1"} else ""
        _render(ARMS_ON, chart_path(M, _CT["stem"], ARMS_ON))
    # WHAT WAS WRITTEN, WHICH IS NOT THE CANONICAL NAME AND SOMETIMES IS NO NAME.
    # This printed `<stem>.png` unconditionally -- the canonical figure -- while
    # BOTH renders above are conditional on the selection. Under `--rebal 200` the
    # canonical branch does not run at all, and the line still announced
    # chart_midcap150_FINAL.png: a gated file this step had not touched, named as though
    # it had just been written. The comment that stood here said the nifty100 half had
    # once "named a literal rather than what was written", so the defect was known
    # in one direction and reintroduced in the other.
    #
    # A RUN THAT RENDERS NOTHING SAYS SO. Silence would read as success, and an
    # empty list is exactly the case a reader needs told.
    if _rendered:
        print("\nsaved -> " + ", ".join(q.name for q in _rendered))
    else:
        print("\nsaved -> nothing: no chart was rendered for this selection")


# ======================================================================================
# STEP: COMBINED UNIVERSES CHART. From results/make_combined_universes.py (moved 2026-11-27).
# ======================================================================================
# make_combined_universes -- ONE combined chart across whichever universes this
# run selected.
#
# WHAT REPLACED WHAT
#     This file replaced a step hardcoded to exactly two universes, so the project
#     could not compare any other set without editing the step. It now takes the
#     selection and compares exactly that. The output is
#     chart_COMBINED_<tag>_<tag>....png, tags in registry.REPORT_ORDER; with the
#     certified pair selected that is chart_COMBINED_nifty100_midcap150.png.
#
# THE RULE ABOUT HOW MANY UNIVERSES
#     N == 1  nothing is written. A one-series "combined" chart restates that
#             universe's own v2FINAL chart under a name claiming to combine
#             several, and a file that misdescribes itself is worse than no file.
#     N >= 2  exactly ONE chart, across exactly those N. Not one per pair, and
#             never a universe that was not selected.
#
# SELECTION, NOT REGISTRATION
#     It asks settings.universe_axis.selected_tags(), not REGISTRY.
#     `--universe midcap150,nifty100` leaves six universes registered and
#     unselected; plotting them would put universes on the page nobody asked for. Run on its own with no selection set, the default
#     is every registered universe, which is what the old step saw.
#
# WHAT IS PLOTTED, PER UNIVERSE
#     v1 (inverse-vol, always invested), v2 (breadth-scaled), the own-universe
#     equal-weight buy&hold, and -- only where the universe HAS one -- the published
#     cap-weighted index. Before-TC and after-TC CAGR are both in the legend, so the
#     cost drag is visible rather than implied.
#
#     A UNIVERSE WITH NO PUBLISHED INDEX (registry.index_file is None) contributes
#     three lines instead of four. Inventing a benchmark for it -- an equal-weighted
#     basket labelled as an index -- is the exact error this project already made
#     once and corrected. Every registered universe has an index today.
#
# THE TWO BENCHMARKS ARE NOT INTERCHANGEABLE
#     The cap-weighted index is investable and is NOT survivorship-biased -- it is the
#     published series. The equal-weight buy&hold is the right yardstick for a
#     strategy picking from the universe, but it is neither investable nor achievable,
#     because these universes are today's members backfilled. Both are shown, labelled
#     for what they are.
#
# Every headline number is printed before anything is plotted.
# Reads only. Writes one PNG.

warnings.filterwarnings("ignore")
def before_tc_combined(eq, log):
    """CAGR with the cost drag removed from the realised path. Not a zero-cost re-run."""
    if not Path(log).exists():
        return None, 0.0, 0
    tr = read_table(log, parse_dates=["date"])
    tc = tr.groupby("date")["tc"].sum().reindex(eq.index).fillna(0.0)
    g = (1 + eq.pct_change().fillna(0.0) + (tc / eq.shift(1)).fillna(0.0)).cumprod() * eq.iloc[0]
    return cagr(g), tc.sum(), len(tr)


# ---------------------------------------------------------------------------
# PER-UNIVERSE PRESENTATION. Paths and index files come from the registry; only
# what is genuinely presentational lives here.
# ---------------------------------------------------------------------------
# THE DISPLAY NAME AND THE COLOURS ARE REGISTRY FIELDS -- phase 2, 2026-09-16.
# They were two dicts keyed by tag here, DISPLAY and COLOURS, plus a _missing_colour
# guard that refused at import. Both are now `u.display_name` and `u.chart_colours`,
# fields with NO DEFAULT: a universe that omits one fails when its row is
# CONSTRUCTED, with a TypeError naming the field, which is a stronger guarantee
# than a guard in a consumer that has to remember to look. The values moved
# verbatim and were compared field by field before the originals were deleted.

# WHICH SLOT OF THAT TUPLE EACH ARM USES. v2 has always been the first colour and
# v1 the second, so with both selected the chart is unchanged. v3 and v4 are new
# on this chart and take the two spare slots -- the buy&hold and index colours are
# separate entries, so nothing collides.
#
# THE COLOUR IS KEYED TO THE ARM, NOT TO POSITION. Step 2 already fixed this
# inside run_v34's chart, where a positional zip gave v3 v2's colour the moment v2
# was deselected. The same trap exists here and is avoided the same way.
ARM_SLOT = {"v2": 0, "v1": 1, "v3": 4, "v4": 5}
ARM_DESC = {"v1": "inv-vol", "v2": "breadth",
            "v3": "provol", "v4": "provol-breadth"}

# THE PUBLISHED PAIR, AND THE ORDER IT IS DRAWN IN. v2 before v1 is the order the
# figure has always had; keeping it is what makes the canonical file reproduce
# byte for byte.
CANON_ARMS = ("v2", "v1")
# The order any wider chart draws in: the published pair first, then the
# measurement arms, so a four-arm chart is the published one with two lines added
# rather than a reshuffle.
PLOT_ORDER = ("v2", "v1", "v3", "v4")

# THIS CHART IS DEFINED OVER THE SHIPPING ARMS, AND A SELECTION NARROWS IT RATHER
# THAN WIDENING IT.
#
# It compares UNIVERSES. Each universe contributes its shipping strategy (v2,
# breadth-scaled) and that strategy's always-invested control (v1), which is what
# the published figure has always shown. v3 and v4 are MEASUREMENT arms: they
# exist to price pro-vol sizing against inverse-vol, and their home is the v34
# chart, which Step 2 already made arm-aware.
#
# WHY NOT SIMPLY PLOT EVERY SELECTED ARM. Because `--arm all` is the default, so
# doing that would put four lines per universe on the published chart instead of
# two -- changing a published figure as a side effect of a structural change,
# which experiments/ARM_SUBSET_SPEC.txt forbids unconditionally (G1). Narrowing is
# safe and widening is not, so the rule is: plot the selected arms INTERSECTED
# with the shipping pair.
#
# THE CONSEQUENCE IS REAL AND IS NOT HIDDEN: with `--arm v3` no shipping arm is
# selected, and this chart is not drawn at all rather than being drawn with a
# measurement arm on it. It says so when it skips.
PLOT_ARMS = ("v2", "v1")

# THE LIQUIDITY PARAGRAPH IS A REGISTRY FIELD -- phase 2, 2026-09-16.
# It was a dict here, with NOT_MEASURED as its declared absence. It is
# `u.liquidity_note` now: a measured note, or None meaning nobody has measured this
# universe. Presence is enforced by the constructor rather than by
# registry_coverage_check, and the note travels with the universe it describes.

_COUNT_WORD = {2: "both", 3: "all three", 4: "all four"}
# Keyed by count, not by universe: it survives a universe being added or removed.
# THE STANDING COMPARISON PAIR. It is refreshed whenever both of its universes
# are selected -- not only when they are the WHOLE selection. It is the certified
# pair, registry.CERTIFIED, declared once in the registry (2026-09-24; it was a
# second hand-written copy of the same two tags here). Which pair is shown is an
# editorial decision recorded there, not something inferred from the rows.
#
# IT IS STILL CHECKED AGAINST THE REGISTRY at import, because the one thing it may
# not be is a pair that cannot exist -- that would fail at chart time, deep in a
# draw call, rather than here.

# THE REGISTRY SIZE THIS PAIR WAS LAST CONFIRMED AGAINST. Widened 2026-09-18, when
# the registry was about to go from 2 universes to 10.
#
# THE GUARD BELOW HAS ALWAYS CAUGHT A PAIR NAMING A UNIVERSE THAT DOES NOT EXIST.
# It could not catch the failure the comment above predicts -- a pair that stays
# VALID while quietly ceasing to be the published figure, because the registry grew
# around it. That failure is silent by construction: every name still resolves and
# every chart still draws.
#
# IT RAISES RATHER THAN WARNS, BY DECISION. PAIR_CHART is the figure the README
# publishes; a warning scrolls past and one wrong figure shipped silently costs
# more than confirming a line once per registry change.
# RE-CONFIRMED AT 3 ON 2026-09-18, AND THE PAIR DID NOT MOVE. nifty50 was wired
# and run that day; it is NOT in the pair and should not be. Nothing on that
# universe has been validated -- no seed, sub-period, shuffle or top-N test -- and
# a standing figure is not the place to introduce a universe whose only property
# so far is that it produced numbers. (nifty100, midcap150) stays.
#
# The guard did its job: it stopped a run rather than letting the pair be read as
# still-confirmed while the registry grew around it. Bumping this is the record
# that somebody looked, which is the whole content of the constant.
#
# RE-CONFIRMED AT 9 ON 2026-10-10, AND THE PAIR DID NOT MOVE. microcap250 was
# added that day and nothing on it has been run or validated.
#
# RE-CONFIRMED AT 12 ON 2026-10-16, AND THE PAIR DID NOT MOVE. The three static-only
# market-cap buckets were added that day.
PAIR_CHART_REGISTRY_SIZE = 12

_unknown_pair = set(PAIR_CHART) - set(REGISTRY)
if _unknown_pair:
    raise SystemExit(
        f"PAIR_CHART names universe(s) the registry does not define: "
        f"{sorted(_unknown_pair)}. The published comparison cannot be drawn. "
        f"Pick a pair from {sorted(REGISTRY)}, or retire the pair chart.")

if len(REGISTRY) != PAIR_CHART_REGISTRY_SIZE:
    raise SystemExit(
        f"PAIR_CHART has not been re-confirmed since the registry changed size.\n"
        f"  registry now holds {len(REGISTRY)} universes: {sorted(REGISTRY)}\n"
        f"  PAIR_CHART_REGISTRY_SIZE says it was last confirmed at "
        f"{PAIR_CHART_REGISTRY_SIZE}\n"
        f"  PAIR_CHART is currently {PAIR_CHART}\n"
        f"\n"
        f"  WHAT TO DO, in results/make_combined_universes.py around line 159:\n"
        f"    1. Decide whether {PAIR_CHART} is still the pair the README should\n"
        f"       publish now that {sorted(set(REGISTRY) - set(PAIR_CHART))} also\n"
        f"       exist. CHANGING THE PAIR IS OPTIONAL -- keeping it is a valid and\n"
        f"       expected answer.\n"
        f"    2. Set PAIR_CHART_REGISTRY_SIZE = {len(REGISTRY)}. THIS IS REQUIRED\n"
        f"       EITHER WAY. Bumping it is the record that a human looked; it is\n"
        f"       not bookkeeping and it is not derived, because deriving it would\n"
        f"       restore exactly the silence this check exists to break.\n"
        f"\n"
        f"  PAIR_CHART IS DELIBERATELY NOT DERIVED FROM THE REGISTRY. Which figure\n"
        f"  the project publishes is an editorial fact, not a property of the\n"
        f"  universes -- see the comment above this constant.")


def _joined(items):
    """'a', 'a and b', 'a, b and c' -- the form the two-universe title used."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def make_combined_universes():
    """The step, as a function, so run.py can call it in process."""
    CAP = 1_000_000

    # WHICHEVER UNIVERSES THIS RUN SELECTED, IN REPORT ORDER. report_order puts
    # nifty100 before midcap150, so the pair's filename is
    # chart_COMBINED_nifty100_midcap150.png whatever order they were typed in.
    tags = report_order(t for t in universe_axis.selected_tags() if t in REGISTRY)

    sel = set(arm_reg.selected_names())

    if len(tags) < 2:
        have = ", ".join(tags) or "none"
        print("=" * 108)
        print(" COMBINED chart SKIPPED -- it overlays two or more universes and "
              f"only {len(tags)} is selected.")
        print(f" selected here: {have}.  A one-series 'combined' chart would just "
              "restate that universe's")
        print(" own v2FINAL chart under a name that claims to combine several, so "
              "nothing is written.")
        print("=" * 108)
        return

    # THE FOUR INPUT PATHS, ONE LOOP OVER THE SELECTED UNIVERSES. Until 2026-09-24
    # this was eight hand-written blocks, one per universe, because the static
    # scanner in check_pipeline_order could not resolve a directory bound from a
    # loop variable. It now can (REG_LOOP_ASSIGN): `M = REGISTRY[tag].metrics_dir`
    # expands over the row's declared span with {tag} substituted per universe,
    # so this loop resolves to the same producer edges the blocks did. A new
    # universe needs no code here, only a registry row.
    #
    # EVERY INPUT THROUGH _ci, so each name carries this run's axis suffixes and
    # the chart's provenance is recoverable from its inputs (withdrawn from README
    # on 2026-09-12 for lacking exactly that). The loop variable must stay named
    # `tag` and the literals must stay in the call: the scanner reads the
    # `M / "<literal>"` shape out of this source.
    FILES = {}
    for tag in tags:
        M = REGISTRY[tag].metrics_dir
        FILES[tag] = (_ci_combined(M / "v2FINAL_equity.csv"),
                      _ci_combined(M / "v2FINAL_params.json"),
                      _ci_combined(M / f"daily_trades_{tag}.csv"),
                      _ci_combined(M / f"daily_trades_v1_{tag}.csv"))
    # LOADED ONCE, PLOTTED POSSIBLY TWICE. The nifty100+midcap150 pair chart is
    # drawn from the SAME rows as the N-way chart when both are produced, so the
    # two figures cannot disagree about a number.
    UNIV = []
    for t in tags:
        u = REGISTRY[t]
        # THE FILES ENTRIES ARE ALREADY THIS RUN'S NAMES: each is _ci() of a
        # literal, the shape check_pipeline_order resolves. They were passed
        # through _ci() a second time here until 2026-09-24, which asked for
        # v2FINAL_equity_tax_tax.csv; the old _ci() fell back to the canonical
        # name when that was missing, so the double suffix went unseen until the
        # fallback was removed and the first multi-universe taxed run failed.
        eqf, pjf, tr2, tr1 = FILES[t]
        eq = read_table(eqf, parse_dates=["date"]).set_index("date")
        # ARMS BY NAME, NOT BY THE COLUMN THEY HAPPEN TO SIT IN.
        # equity_series falls back to the legacy `strategy`/`baseline_invvol`
        # spelling, which is what the retired universes wrote.
        eq_v2 = arm_reg.equity_series(eq, "v2")
        eq_v1 = arm_reg.equity_series(eq, "v1")
        index = None
        if u.index_file is not None:
            raw = (market_data.read_price_csv(u.index_file)[["date", "close"]].dropna()
                   .set_index("date")["close"].sort_index())
            s_ = raw.reindex(eq.index.union(raw.index)).ffill().reindex(eq.index)
            index = CAP * s_ / s_.iloc[0]
        UNIV.append({
            "tag": t, "u": u, "M": Path(eqf).parent, "eqf": eqf,
            "eq": eq, "index": index,
            "inv": json.loads(pjf.read_text())["avg_exposure_pct"],
            # ONE ENTRY PER AVAILABLE SELECTED ARM. Where each arm's curve and
            # per-trade log live is make_chart's problem, not this chart's:
            # three files under three naming conventions, and four charts each
            # rediscovering that is four chances to disagree.
            "arms": _load_arms(Path(eqf).parent, t, sel),
            "idxname": u.index_name,
            "display": u.display_name,
            # NO FALLBACK, AND THERE WAS ONE. This read
            # COLOURS.get(t, ("#1f77b4", "#7f7f7f", "#2ca02c", "#000000")) -- a
            # four-colour default sitting behind a guard that refused at import for
            # exactly the case the default existed to serve. Either the guard fires
            # and the default is dead, or someone removes the guard and a chart
            # silently picks colours nobody chose; the pair is the silent-fallback
            # family, in one file, facing both ways. The field has no default and
            # the row cannot be constructed without it.
            "colours": u.chart_colours,
        })

    print("=" * 108)
    print(" COMBINED -- " + _joined([u["display"] for u in UNIV])
          + ". Every number printed before plotting.")
    unsel = [t for t in REGISTRY if t not in tags]
    if unsel:
        print(f" Universes outside this selection ({', '.join(unsel)}) are not on "
              "this chart.")
    else:
        print(" Every registered universe is on this chart.")
    print("=" * 108)
    print(f"\n  SURVIVORSHIP: {market_data.describe_state()}")
    for row in UNIV:
        _report(row)

    # ------------------------------------------------------------------
    # TWO CHARTS ON THE ARM AXIS, THE SAME WAY THERE ARE TWO ON THE UNIVERSE AXIS.
    # ------------------------------------------------------------------
    # CANONICAL: the published figure, always exactly v2 and v1, into the
    # unsuffixed filename. Drawn whenever both are selected, so `--arm all` keeps
    # refreshing it and it stays byte-identical to what it has always been.
    #
    # SELECTION: exactly the arms this run selected, into an arm-suffixed
    # filename, drawn whenever the selection is anything other than that pair.
    # `--arm v3` therefore PRODUCES a chart showing v3 rather than skipping, and
    # `--arm all` produces a four-arm chart BESIDE the published two-arm one.
    #
    # WIDENING IS SAFE ONLY BECAUSE IT IS SUFFIXED. Adding v3 and v4 to the
    # unsuffixed file would change a published figure as a side effect of running
    # the default; putting them in a file of their own does not.
    def _emit(arm_names, out_suffix, why):
        rows = [r for r in UNIV if [n for n in r["arms"] if n in arm_names]]
        rows = [dict(r, arms={n: d for n, d in r["arms"].items() if n in arm_names})
                for r in rows]
        if len(rows) < 2:
            print(f"\n  {why}: fewer than two universes can show "
                  f"{', '.join(arm_names)} -- not drawn")
            return
        _draw(rows, combined_chart_path(rows[0]["M"],
                                        [r["tag"] for r in rows], out_suffix))
        return rows

    canon_rows = None
    if set(CANON_ARMS) <= sel:
        canon_rows = _emit(list(CANON_ARMS), "", "canonical v2+v1 chart")

    if sel != set(CANON_ARMS):
        print("\n" + "-" * 108)
        print(" ALSO DRAWING THIS RUN'S ARM SELECTION -- "
              + ", ".join(n for n in PLOT_ORDER if n in sel)
              + ", into its own file.")
        print(" The unsuffixed chart above is the published v2+v1 comparison and "
              "is not widened.")
        print("-" * 108)
        _emit([n for n in PLOT_ORDER if n in sel], arm_reg.suffix(sel),
              "arm-selection chart")

    # ------------------------------------------------------------------
    # THE PUBLISHED PAIR CHART, IN ADDITION TO THE N-WAY ONE.
    # ------------------------------------------------------------------
    # nifty100-vs-midcap150 is the project's standing comparison. It is NOT
    # merely "the N-way chart when N happens to be 2" -- it is a published figure
    # in its own right, and a four-universe run that silently stopped refreshing
    # it left the docs copy stale with nothing saying so.
    #
    # So whenever BOTH are in the selection, the pair chart is
    # refreshed as well. Two different, valid comparisons, not a contradiction:
    # the N-way chart answers "how do the selected universes compare", the pair
    # chart answers "how do the two certified universes compare", and the second
    # question does not stop being asked because other universes were also run.
    #
    # ONLY WHEN N > 2. At N == 2 the selection IS the pair, the N-way chart above
    # already wrote exactly this file, and drawing it again would render the same
    # figure to the same path twice.
    #
    # IT IS DRAWN AS IF ONLY THE PAIR WERE SELECTED: _subtitle derives the
    # out-of-scope sentence from REGISTRY minus the rows being PLOTTED, not minus
    # the selection, so the string does not depend on what else ran.
    pair = [r for r in UNIV if r["tag"] in PAIR_CHART]
    pair = [dict(r, arms={n: d for n, d in r["arms"].items() if n in CANON_ARMS})
            for r in pair]
    if (len(pair) == len(PAIR_CHART) and len(UNIV) > len(PAIR_CHART)
            and set(CANON_ARMS) <= sel and all(len(r["arms"]) == 2 for r in pair)):
        print("\n" + "-" * 108)
        print(" ALSO REFRESHING THE PUBLISHED PAIR CHART -- "
              + " and ".join(r["display"] for r in pair)
              + ". Same rows as above, drawn on their own.")
        print(" It is a standing published figure, not a by-product of N == 2, so a "
              "wider selection still refreshes it.")
        print("-" * 108)
        _draw(pair, combined_chart_path(pair[0]["M"],
                                        [r["tag"] for r in pair]))


def _ci_combined(path):
    """This run's cadence-, profile- and tax-named sibling of `path`.

    THE PROFILE WAS MISSING HERE AND PRESENT IN THE OTHER TWO. The two per-universe
    chart scripts (since merged into reports.py) each carried a `_ci` that composed
    cadence.suffix() + settings.profile_axis.suffix(); this one composed the cadence alone. So
    under `--profile tradeable` the engines wrote v2FINAL_equity_tradeable.csv and
    this helper looked for a file that did not exist, fell through to `path`, and
    loaded the RESEARCH curve into a chart drawn under a tradeable title.

    Measured 2026-09-12 by the naming-authority audit, which probes each composer
    one axis at a time: this one reported `cadence` where its two same-named
    siblings reported `cadence, profile`.
    """
    import settings
    from settings import tax as _tax
    # THE TAX AXIS, 2026-09-17. This helper is the one that was found composing
    # one axis fewer than its two same-named siblings; it gets the fourth at the
    # same time they do, so the three cannot drift apart again.
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    if (cadence.is_default() and settings.profile_axis.is_default() and _tax.is_default()
            and _sva.is_default() and _dda.is_default()
            and _capa.is_default() and _impa.is_default() and _pca.is_default() and _fxa.is_default() and _sta.is_default() and settings.shortfall_axis.is_default()):
        return path
    c = path.with_name(path.stem + cadence.suffix() + settings.profile_axis.suffix()
                       + _tax.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix() + path.suffix)
    # NO FALLBACK TO THE CANONICAL FILE, 2026-09-23. This returned `path` when
    # the sibling was absent, so a missing non-default artefact was silently
    # replaced by the published cadence-20 research one and plotted under this
    # run's title. The sibling's name is returned whether or not it exists, and a
    # missing one fails at the read, naming the file this run should have made.
    return c


def _load_arms(M, tag, sel):
    """{arm: {eq, b}} for every selected arm this universe can actually show."""
    out = {}
    for n in PLOT_ORDER:
        if n not in sel:
            continue
        # THE SOURCE FILE IS RECORDED, for the reason the withdrawal of this very
        # chart established: a figure that cannot say what it read cannot be
        # checked after the fact.
        src, eq = equity_path_and_series(M, tag, n)
        lg = trades_path(M, tag, n)
        if eq is None or lg is None:
            print(f"    {tag}/{n}: no curve or trade log for this run's axes "
                  f"-- not plotted")
            continue
        print(f"    {tag}/{n}: {describe(src, len(eq), 'sessions')}")
        print(f"    {tag}/{n}: {describe(lg)}")
        out[n] = {"eq": eq, "b": before_tc_combined(eq, lg), "src": src, "log": lg}
    return out


def _report(row):
    """One universe's headline numbers, printed before anything is plotted."""
    t, eq, index = row["tag"], row["eq"], row["index"]
    nsym = len(row["u"].symbols()) if row["u"].symbols() is not None else None
    print(f"\n  {t.upper()}  "
          + (f"({nsym} constituents, {row['idxname']} excluded by name)  "
             if nsym is not None else "(directory-defined basket)  ")
          + f"window {eq.index[0].date()} -> {eq.index[-1].date()}  inv {row['inv']}%")
    print(f"    {'series':<46}{'before TC':>11}{'after TC':>10}{'Sharpe':>8}{'MaxDD%':>9}")
    printable = [(f"{t} {n} ({ARM_DESC[n]})", d["eq"], d["b"][0])
                 for n, d in row["arms"].items()]
    printable.append((f"{t} buy&hold (equal-weight universe)", eq["buyhold"], None))
    if index is not None:
        printable.append((f"{row['idxname']} (cap-weighted index)", index, None))
    for lab, s2, b in printable:
        bt = f"{b:>10.2f}%" if b is not None else f"{'--':>11}"
        print(f"    {lab:<46}{bt}{cagr(s2):>9.2f}%{sharpe(s2):>8.2f}{dd(s2).min():>8.2f}%")
    print("    " + "   |   ".join(
        f"{n} trades {d['b'][2]}, TC Rs {d['b'][1]:,.0f}" for n, d in row["arms"].items()))


def _series(rows):
    """The plotted lines for these rows, in row order."""
    out = []
    for row in rows:
        t, eq, index = row["tag"], row["eq"], row["index"]
        c_bh, c_ix = row["colours"][2], row["colours"][3]
        # COLOUR AND DEPLOYMENT KEYED TO THE ARM. v2 takes the tuple's first
        # colour and v1 the second, which is where they have always been, so with
        # both plotted every line keeps its exact colour. Only v2 is
        # breadth-scaled, so only v2 reports a deployment below 100%.
        for n, d in row["arms"].items():
            c = row["colours"][ARM_SLOT[n]]
            inv = row["inv"] if arm_reg.ARMS[n].mode == "breadth" else 100
            out.append(
                (f"{t} {n} ({ARM_DESC[n]})  [inv {inv}%]", d["eq"], c, "-",
                 f"CAGR {d['b'][0]:.2f}% before TC / {cagr(d['eq']):.2f}% after TC"
                 f"  [{d['b'][2]} trades, Rs {d['b'][1]:,.0f}]"))
        out.append(
            (f"{t} buy&hold (equal-weight universe)  [inv 100%]", eq["buyhold"], c_bh, "--",
             f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"))
        if index is not None:
            out.append(
                (f"{row['idxname']} (cap-weighted index)  [inv 100%]", index, c_ix, ":",
                 f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"))
    return out


def combined_chart_path(M, tags, out_suffix=""):
    """The combined chart's name, over all three axes. THE ONE DEFINITION.

    Named for the same reason chart_path is: the two call sites composed this
    inline, so the write call saw only `out_path` and Gate 2 had nothing to
    measure. Rule unchanged -- universe tags, then the arm suffix the caller
    chose, then cadence and profile.
    """
    import settings
    from settings import tax as _tax
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    return M / ("chart_COMBINED_" + "_".join(tags) + out_suffix
                + cadence.suffix() + settings.profile_axis.suffix() + _tax.suffix() + _sva.suffix() + _dda.suffix() + _capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix()
                + ".png")


def _draw(rows, out_path):
    """Render exactly these rows to this path."""
    series = _series(rows)
    sub = _subtitle(rows)
    fig, ax = plt.subplots(2, 1, figsize=(17, 12), height_ratios=[2, 1])
    for lab, s2, c, ls, extra in series:
        ax[0].plot(s2.index, cum(s2), lw=1.9, color=c, ls=ls, label=f"{lab}  {extra}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(settings.run_label([r["u"].label for r in rows],
                                     sorted({n for r in rows for n in r["arms"]}))
                    + "\n" + sub, fontsize=9)
    ax[0].legend(loc="upper left", fontsize=8); ax[0].grid(alpha=.3)
    for lab, s2, c, ls, _ in series:
        ax[1].plot(s2.index, dd(s2), lw=1.3, color=c, ls=ls,
                   label=f"{lab.split('  [')[0]} (max {dd(s2).min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=7.5, ncol=2); ax[1].grid(alpha=.3)
    plt.tight_layout()
    # naming: arm,cadence,profile via combined_chart_path -- composed by the
    # (reports.py and :398) from the universe tags plus the
    # arm suffix, cadence.suffix() and settings.profile_axis.suffix(). The OUTPUT side of this
    # step was already axis-complete; it was the INPUT side, the FILES dict, that
    # named canonical files and could not say what it had read.
    plt.savefig(out_path, dpi=150, bbox_inches="tight", metadata={"Title": ax[0].get_title().split("\n")[0]})
    plt.close(fig)
    print(f"\n  saved -> {out_path}")


def _subtitle(UNIV):
    """The chart's own description of what is on it, derived from what is on it.

    IT TAKES THE ROWS BEING PLOTTED, NOT THE SELECTION, and that distinction is
    what keeps the published pair chart reproducible: the out-of-scope sentence is
    computed from REGISTRY minus the universes ON THIS FIGURE, so a subtitle cannot
    depend on what else the run did and make the same figure two files.

    The clause is omitted, not rendered empty, when nothing is out of scope.

    EVERY CLAUSE IS CONDITIONAL ON THE UNIVERSES ACTUALLY PLOTTED. The old block
    was one hardcoded string naming two universes, including a liquidity paragraph
    quoting their measured numbers, so drawing any other set would have printed
    claims about universes that were not on the page.

    """
    n = len(UNIV)
    word = _COUNT_WORD.get(n, f"all {n}")
    unsel = [t for t in REGISTRY if t not in {u["tag"] for u in UNIV}]
    has_index = [u for u in UNIV if u["index"] is not None]

    # THE ARMS AND THE COST BASIS ARE READ FROM THE FIGURE AND THE RUN, since
    # 2026-09-30. line1 said "v1, v2" on the arm-selection chart too, which can
    # carry v3 and v4, and line2 said "Zerodha + 0.15% slippage" on taxed and
    # tradeable charts.
    arms = sorted({a for u in UNIV for a in u["arms"]})
    line1 = (_joined([u["display"] for u in UNIV])
             + f" -- {', '.join(arms)}, own-universe equal-weight buy&hold, and the "
             + ("published cap-weighted index for each"
                if len(has_index) == n else
                "published cap-weighted index where the universe has one")
             + "\n")

    line2 = ("ALL STRATEGY NUMBERS " + settings.cost_basis()[len("ALL NUMBERS "):]
             + "; before-TC also shown in the legend.")
    if unsel:
        # A COUNT, NOT A LIST, SINCE 2026-09-18. This named every registered
        # universe not on the figure, so the PUBLISHED PAIR CHART's caption grew
        # by one name per universe added, and would have listed six by the end of
        # the migration.
        # A published figure whose text churns every time something unrelated is
        # registered cannot be compared with its own previous version.
        #
        # THE SENTENCE IS KEPT, because the reader does need to know the figure
        # is a selection rather than everything there is. What is dropped is
        # WHICH universes -- that is a fact about the registry, not about this
        # chart, and it is one `registry_coverage_check.py` prints in full.
        # The double space that separated the two sentences is preserved.
        n_out = len(unsel)
        line2 += (f"  {n_out} other registered universe"
                  f"{'s are' if n_out > 1 else ' is'} out of scope and "
                  f"{'are' if n_out > 1 else 'is'} not plotted.")
    line2 += "\n"

    line3 = ""
    if has_index:
        line3 = ("The cap-weighted index is investable and is NOT survivorship-biased. ")
    line3 += ("The equal-weight buy&hold is neither investable nor achievable: "
              f"{word} universes are\n"
              "today's index members backfilled, so names dropped or delisted during "
              "the window are absent entirely and the sign of the bias is not "
              "known.\n")

    # LIQUIDITY BELONGS HERE MOST OF ALL.
    #   Each universe's individual chart carries its own liquidity line, but this
    #   is the only page where they appear together, and the contrast is the whole
    #   point: the depth model's cost differs by universe (see each universe's
    #   liquidity_note in settings.py).
    # None CONTRIBUTES NOTHING, exactly as an absent key used to. The difference is
    # upstream: the field must be supplied, so "this universe has no note" is a
    # statement somebody made rather than a gap nobody noticed.
    notes = [REGISTRY[u["tag"]].liquidity_note for u in UNIV
             if REGISTRY[u["tag"]].liquidity_note is not None]
    liq = ("LIQUIDITY, at Rs 10,00,000 starting capital. " + "\n".join(notes) + "\n"
           if notes else "")

    # WINDOWS THAT DO NOT END TOGETHER ARE SAID SO, ON THE CHART.
    # Comparing cumulative returns across universes that stop on different days is
    # partly reading a calendar difference, and a reader should not have to open
    # another file to discover that. Empty when they agree, which every registered
    # universe does today (2026-05-29).
    ends = {u["tag"]: u["eq"].index[-1] for u in UNIV}
    win = ""
    if len({e.date() for e in ends.values()}) > 1:
        win = ("WINDOWS DIFFER and the lines therefore stop on different days: "
               + ", ".join(f"{t} to {e.date()}" for t, e in ends.items())
               + ". Cross-universe CAGR here is not like-for-like.\n")

    return line1 + line2 + line3 + liq + win + market_data.describe_state()


# ======================================================================================
# STEP: DAILY LOG. From results/make_daily_log.py (moved 2026-11-27).
# ======================================================================================
# make_daily_log -- forensic DAILY LOG.
#
# A complete record of every trading day, in four sections:
#   [A] ORDER EXECUTION   the previous rebalance order, filled at TODAY's OPEN
#   [B] RECONCILIATION    whether the arithmetic ties out (cash, equity, share count)
#   [C] POSITIONS         what is held at TODAY's CLOSE, and when it was bought
#   [D] ORDER CREATION    on a rebalance day, the new ranking from TODAY's CLOSE
#
# Everything is read from the audit CSVs. No backtest number is recomputed here;
# section [B] only checks the figures that were already written.
#
# Timing (verified against portfolio.backtest_exposure):
#   each day the cash balance is carried forward first, then the pending order is
#   filled (all SELLs, then all BUYs), then positions are marked at the CLOSE, and
#   finally a new order is created if today is a rebalance day. An order always
#   fills at the OPEN of the next trading day.

W = 118

# TOP_N AND BUFFER ARE READ, NOT TYPED. The legend and sections [A], [C] and [D]
# spelled "top 8", "buffer (16)" and "ranks 1-8 ... 9-16 ... 17+" as literals. They
# happen to match config today; a change to either constant would have left this
# file describing a selection rule the engine no longer used.
TOP_N, BUFFER = settings.TOP_N, settings.BUFFER
# Mirrors the constants in portfolio.py -- needed for reconciliation only.
# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
CASH_YIELD = 0.0        # must match portfolio.py
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
CASH_DAILY = (1 + CASH_YIELD) ** (1 / 252) - 1

TOL_CASH = 0.50      # rupees; CSVs are rounded to 2 decimals, so a few paise of
                     # noise is expected (max observed 0.03). A real error would
                     # be orders of magnitude larger.
TOL_EQ = 0.05
# The same 1 paisa backtest_runs.run() uses to decide whether to write the trail at
# all, so this log cannot disagree with the gate that let the trail exist.
TOL_CURVE = 0.01

LEGEND_TEMPLATE = """\
 HOW TO READ THIS FILE
 ------------------------------------------------------------------------------------------------------------------
 Each trading day is one block. The order of events matches the order in the code:

   1. the cash balance is carried forward (with yield, if a cash yield is configured)
   2. yesterday's order fills at TODAY's OPEN -- all SELLs first, then all BUYs
   3. positions are marked to market at TODAY's CLOSE
   4. if today is a rebalance day (every {rebal} trading days), a new order is created from
      today's CLOSE signal, to be filled at TOMORROW's OPEN

 DAY TYPE
   REBALANCE DAY          an order was created today; it fills tomorrow
   EXECUTION DAY          a pending order filled today; no new order created
   EXECUTION + REBALANCE  both -- the old order filled and a new one was created
   HOLD DAY               no activity; only prices moved

 ORDER ID   R007-S2 is the second SELL of rebalance number 7. R007-B1 is its first BUY.
            The same ID appears in the order creation section (D) and in the execution
            section (A) of the following day, so any order can be traced end to end.

 PRICES     Open (derived) is the underlying open price, backed out from the fill price.
            The fill differs from it because slippage of 0.15% is always applied against
            the trade: BUYs fill higher, SELLs fill lower.
            Value = quantity x fill price. TxnFee is charged separately.

 TXNFEE     Actual Zerodha delivery-equity charges for the trade: brokerage, STT,
            stamp duty, exchange transaction charge, SEBI turnover fee and GST.
            These are transaction-level costs and taxes debited on the contract note.
            Capital-gains tax is not one of them: with tax on it is deducted once a
            year, on the assessment day, and shown in section B's cash line.

 SECTION B  This is the proof that the arithmetic is correct. Three checks run daily:
              CASH    opening cash + yield + sale proceeds - purchases - fees
                      - capital-gains tax (on an assessment day, tax on only) = closing cash
              EQUITY  cash + market value of holdings = total portfolio value
              SHARES  for every symbol: opening quantity +/- today's trade = closing quantity
            Each check is marked OK or *** FAIL ***. A full tally appears at the end of the file.

 WHY SOLD   A stock is sold only when its rank falls below {buffer} (the buffer). Ranks {top1}-{buffer} are
            held, which avoids unnecessary turnover at every rebalance.
 WHY BOUGHT It entered the top {top} and was not already held.
{exposure_para}
{sizing_para}
 SKIPS      An order that was created but did not fill is listed under the day it should
            have filled, with the reason and the actual numbers. The reasons:
              no open price (NaN/<=0)  the symbol had no usable open price that morning
              qty < 1 after sizing     the target was smaller than one share
              cash short (before TC)   the funding defect below
              cash short (incl TC)     the same, once transaction costs are added{trim_skip}
              participation cap        cut or refused by the tradeable profile's volume cap
              untradeable              no raw price row, or a forced exit before a gap
              impact                   no prior-20-session median to price impact against
            Two further entries are not skipped orders: the capital-gains tax assessed on
            an assessment day (tax on), and the sale of every holding on the last day
            when a run asks for it.{stop_skip}
 FUNDING    invest value is a share of the WHOLE portfolio, but new positions are paid for
            out of CASH ALONE, and a name already held is never resized. So whenever a
            buffer name is holding capital the book is over-committed by construction and
            the tail of the score-descending buy loop {funding_tail} A 100%-invested arm hits it constantly; a breadth-scaled
            arm holds cash anyway and rarely does. The per-rebalance counts below make the
            difference visible.
 NOTE       Existing holdings are never resized. Only new positions are sized against the
            target exposure, so the actual invested percentage can drift from the target.
"""


# ---------------------------------------------------------------------------
# THE ARM DECIDES WHAT IS TRUE IN THE PROSE, NOT JUST THE FILENAME
# ---------------------------------------------------------------------------
# The legend and section [D] used to describe v2 unconditionally: "that same
# fraction of the portfolio is invested" is FALSE for v1 and v3, which pin
# exposure at 1.0 and ignore breadth entirely. Their decisions file still carries
# a breadth column -- it is computed for every arm and used only by the
# breadth-scaled ones -- so a log that printed it without qualification implied it
# drove the book when it did not.
#
# SIZING IS NAMED IN WORDS, not as a formula. v1 and v3 differ ONLY in invvol
# versus provol, and "1/vol" against "vol" is easy to misread at a glance; the
# whole point of these logs is reading two arms side by side.
SIZING_PROSE = {
    "invvol": ("inverse volatility (w = 1/vol) -- the LARGER position goes to the "
               "CALMER name"),
    "provol": ("proportional volatility (w = vol) -- the LARGER position goes to the "
               "MORE VOLATILE name"),
    "equal":  "equal weight -- every position gets the same share of invest value",
}


def arm_reg_fixture():
    """The drawdown stop's test-fixture threshold, or None."""
    import portfolio as _ar
    return _ar.fixture_threshold()


def legend_for(arm):
    """LEGEND_TEMPLATE with the arm-dependent paragraphs resolved."""
    if arm.stop is not None:
        _st = arm.kwargs["drawdown_stop"]
        exposure_para = (
            f" EXPOSURE   This arm is {arm.parent} plus a DRAWDOWN STOP. While invested it is 100%\n"
            f"            invested, exactly as {arm.parent}. When close equity falls {_st.threshold:.0%} or more\n"
            f"            below its running peak, every holding is sold at the next open through the\n"
            f"            normal sell path (cap, slippage, charges, tax). From the day the book is\n"
            f"            flat it stays in cash for {_st.cooldown_cycles} rebalance cycle(s); then, on each rebalance\n"
            f"            day, it re-enters with the normal {arm.parent} order once breadth is {_st.reentry_breadth:.2f}\n"
            f"            or more, and the peak resets at the re-entry close. Section [A] shows each\n"
            f"            exit and section [D] each cooldown, wait and re-entry day.")
        if arm_reg_fixture() is not None:
            exposure_para += ("\n            THIS LOG WAS PRODUCED UNDER A TEST FIXTURE THRESHOLD "
                              f"({_st.threshold:.2%}). IT IS A\n            TEST OF THE WIRING, NOT A RESULT.")
    elif arm.mode == "breadth":
        exposure_para = (
            " EXPOSURE   Breadth is the fraction of stocks with positive 20-day momentum. That same\n"
            "            fraction of the portfolio is invested; the remainder stays in cash. There is\n"
            "            no indicator and no tuned threshold.")
    else:
        exposure_para = (
            " EXPOSURE   This arm is ALWAYS 100% INVESTED. It has no breadth scaling and no cash\n"
            "            rule. Breadth is still reported each rebalance as an OBSERVED DIAGNOSTIC --\n"
            "            it is what a breadth-scaled arm would have done on that day -- but it does\n"
            "            not affect this book at all.")
    sizing_para = (f" SIZING     {SIZING_PROSE.get(arm.sizing, arm.sizing)}.\n"
                   f"            Existing holdings are never resized, so realised weights drift from target.")
    # THE CADENCE IS READ, NOT TYPED. "every 20 trading days" was a literal, so a
    # --rebal 200 log contradicted its own header, which said 10 rebalances.
    from settings import cadence as _cd
    # ONLY A STOP ARM'S LEGEND NAMES ITS EXTRA ENTRY, so a core arm's log is
    # byte-identical to the one written before the stop arms existed.
    stop_skip = ("" if arm.stop is None else
                 ' A stop arm adds a third: "drawdown exit", on the\n'
                 '            close that triggered the exit.')
    # ONLY A TRIMMED RUN'S LEGEND DESCRIBES THE TRIM, so a refuse run's log is
    # byte-identical to the one written before buy_shortfall existed.
    import portfolio as _bsf
    import settings
    if settings.shortfall_axis.selected() == "trim":
        trim_skip = ("\n            Under buy_shortfall trim a buy cash cannot fully pay for is cut to"
                     "\n            the largest whole quantity that fits and marked TRIMMED; a"
                     f"\n            buy of which fewer than {_bsf.MIN_FILL_PCT}% of the wanted shares fit is"
                     "\n            skipped as cash short.")
        funding_tail = ("is short of cash.\n            Each such buy is trimmed to what "
                        f"fits, or skipped when fewer than\n            {_bsf.MIN_FILL_PCT}% of the "
                        "wanted shares fit. That is what the TRIMMED buys\n            and the "
                        "cash-short skips are.")
    else:
        trim_skip = ""
        funding_tail = ("is skipped. That is what the\n            cash-short skips are.")
    return LEGEND_TEMPLATE.format(exposure_para=exposure_para, sizing_para=sizing_para,
                                  stop_skip=stop_skip, trim_skip=trim_skip,
                                  funding_tail=funding_tail,
                                  top=TOP_N, top1=TOP_N + 1, buffer=BUFFER,
                                  rebal=_cd.selected())


# ---------------------------------------------------------------------------
# STALE-PRICE DETECTION -- WAS THERE A RAW ROW FOR THIS SYMBOL ON THIS DATE?
# ---------------------------------------------------------------------------
# px and op are pivots with .ffill() applied, so a symbol that did not trade on a
# date still carries a price: the last one it had. A fill at that price is a fill
# at a price nobody quoted, and a holding marked at it is marked at a stale mark.
#
# THIS CANNOT BE FOUND FROM daily_skipped. The engine skips an order only when the
# open is NaN or <= 0, and ffill guarantees it is neither -- so the guard never
# trips and the skip never happens. Measured: "no open price (NaN/<=0)" fires ZERO
# times across every midcap150 and nifty100 trail, while PATANJALI's 2019-11-27 SELL of
# 33,575 shares filled at 1.1483 on a date with no raw row at all. ffill is
# precisely what prevents the skip, so surfacing skips can never surface this.
#
# READ-ONLY. Nothing here changes a price or a fill; it is a reporting flag.
def raw_row_index(u):
    """{symbol: set of dates that have a RAW price row}, restricted to the calendar.

    Dates come from market_data.read_price_csv, which routes through
    market_data.smart_parse_dates -- the supplier folders do not all use one date
    format, and a hardcoded strptime silently drops whole universes.

    The calendar restriction matters in both directions: 70 of the 148 MidCap150
    files carry market-holiday rows that are not sessions, and counting one of
    those as "a raw row exists" would hide a genuine gap.
    """
    from market_data import _load_calendar
    cal = _load_calendar()
    idx = {}
    try:
        src = Path(u.prepare_data_dir())
    except Exception:
        return None, None
    for f in list_dir(src, "*.csv"):
        try:
            d = market_data.read_price_csv(f)
        except Exception:
            continue
        if "date" not in d.columns:
            continue
        idx[f.stem] = {x for x in d["date"] if x in cal}
    return idx, sorted(cal)


def stale_note(raw_idx, cal_sorted, sym, d):
    """"carried forward from YYYY-MM-DD, N sessions back", or None if not stale."""
    if raw_idx is None:
        return None
    have = raw_idx.get(sym)
    if have is None or d in have:
        return None
    prior = [x for x in have if x < d]
    if not prior:
        return "no raw row on or before this date"
    src = max(prior)
    try:
        n = cal_sorted.index(d) - cal_sorted.index(src)
    except ValueError:
        n = -1
    return (f"STALE -- no raw row today; price carried forward from "
            f"{src.date()}, {n} session{'' if n == 1 else 's'} back")


def load(M, tag):
    r = lambda f, c: read_table(M / f"{f}_{tag}.csv", parse_dates=[c])
    sk = M / f"daily_skipped_{tag}.csv"
    skipped = read_table(sk, parse_dates=["date"]) if sk.exists() else pd.DataFrame()
    if len(skipped) == 0:
        skipped = pd.DataFrame(columns=["date", "side", "symbol", "reason", "detail"])
    return (r("daily_holdings", "date"), r("daily_summary", "date"),
            r("daily_trades", "date"), r("daily_ranking", "decided_on"),
            r("daily_decisions", "decided_on"), skipped)


TRAIL_FILES = ("daily_holdings", "daily_summary", "daily_trades",
               "daily_ranking", "daily_decisions")


def missing_trail(M, tag):
    """Which of the trail files this log needs are absent. daily_skipped is not
    listed: load() already tolerates its absence and substitutes an empty frame."""
    return [f for f in TRAIL_FILES if not (Path(M) / f"{f}_{tag}.csv").exists()]


def tax_due_by_date(summary_dates, trades):
    """{date: rupees} the engine deducted from cash, or {} when tax is off.

    WHY THIS EXISTS. Section [B]'s cash identity was written before the tax axis
    and reads
        opening + yield + sales - purchases - fees = closing
    which is the whole of the engine's cash movement UNDER tax=off and is short
    one term under tax=on. portfolio.backtest_exposure does
    `cash -= ledger.due_on(dt)` on each assessment date, so on those six-or-so
    days the recorded closing cash is legitimately BELOW what this identity
    predicts. The log then reported "*** FAIL ***" on correct data and closed
    with "VERDICT: some days failed" -- on every taxed run, of every universe,
    of every arm. THE DATA WAS NEVER WRONG; THE IDENTITY WAS INCOMPLETE.

    THE RUPEES ARE NOT RECONSTRUCTED HERE AND NO TAX ARITHMETIC IS REPEATED.
    costs.Ledger is the class the engine itself uses, `due_on` is the method
    the engine itself calls, and this replays the run's own filled trades
    through it in the run's own order -- SELLs then BUYs, and `due_on(d)` asked
    BEFORE the day's fills, exactly as touch point 6 orders them. Reimplementing
    FIFO lot matching, bucket netting, the exemption or the rate schedule in
    this file would be a second copy of costs.py that could drift
    from the first, which is the defect this repository keeps finding.

    NOT READ FROM FY_TAX_STATEMENT, and the reason is coverage rather than
    taste: that artefact is written once per universe, for the v2 tag only, and
    this log is built for FOUR arms per universe. Three of the four would have
    had no source. The skipped-order trail does carry a per-arm "TAX" row, but
    its rupees are a formatted string rounded to paise -- parsing a rendered
    number back out is reconstruction of the worst kind.

    VERIFIED AGAINST THE ENGINE, not asserted: the amounts this returns were
    compared with the TAX rows the engine wrote into daily_skipped_<tag>.csv
    across all 32 taxed (universe, arm) trails on 2026-09-20 -- 32 tags, 0
    mismatches, agreeing to the paisa on every assessment date.

    RETURNS {} WHEN THE TAX AXIS IS OFF, which is what keeps every untaxed log
    byte-identical: no term is subtracted, no line is printed, and the caller
    takes the same branch it always took.
    """
    from settings import tax as _taxaxis
    if not _taxaxis.selected():
        return {}
    from costs import Ledger, fy_label
    led = Ledger(summary_dates)
    tg = {d: g for d, g in trades.groupby("date")}
    due, label = {}, {}
    for d in summary_dates:
        owed = led.due_on(d)
        if owed:
            due[d] = owed
            label[d] = ", ".join(fy_label(f) for f in led.assess_on.get(pd.Timestamp(d), []))
        g = tg.get(d)
        if g is not None:
            _replay_fills(led, g, d)
        # THE SECOND PHASE, as the engine orders it: a year assessed on a day
        # inside that year is charged after the day's fills. See
        # costs.Ledger.due_on.
        late = led.due_on(d, after_fills=True)
        if late:
            due[d] = due.get(d, 0.0) + late
            fys = list(led.assess_on.get(pd.Timestamp(d), []))
            if led.end is not None and pd.Timestamp(d) == led.end:
                fys += sorted(led.settled_at_end)
            label[d] = ", ".join(fy_label(f) for f in fys)
    return {"due": due, "label": label}


def _replay_fills(led, g, d):
    """Feed one day's filled trades to the ledger, in the engine's order."""
    # SELLs BEFORE BUYs, because the engine fills them in that order and a
    # same-day buy-then-sell of one symbol would otherwise match the wrong
    # lot and bucket the gain into the wrong holding period.
    for _, o in g[g.action == "SELL"].iterrows():
        led.sell(o["symbol"], int(o["qty"]), float(o["price"]), d)
    for _, o in g[g.action == "BUY"].iterrows():
        led.buy(o["symbol"], int(o["qty"]), float(o["price"]), d)


def build(mdir, tag, arm, bh, raw_idx=None, cal_sorted=None, op=None):
    """One forensic log for one already-written audit trail, named by `tag`.

    `bh` is reports.bh_costs' result for the universe, for the totals block.
    `op` is the panel's opens, the price each fill was moved from; without it the
    open is derived from the fill price, which is rounded to the paisa and so
    gives the open only to within half a paisa.

    THIS USED TO REFUSE UNLESS THE RUN WAS v2 AT THE DEFAULT CADENCE, because it
    reconstructed the unsuffixed daily_*_{universe}.csv names itself rather than
    asking for the writer's rule. Under `--arm v3` or `--rebal 200` the trail it
    wanted did not exist, so it printed a skip and produced no forensic log at all
    -- the behaviour this change removes. The caller now resolves the tag through
    backtest_runs.artefact_tag(), the one definition, and passes it in.
    """
    M = Path(mdir)
    h, s, t, rk, dc, sk = load(M, tag)

    # THE ARM'S OWN PUBLISHED CURVE, resolved by audit_step's lookup -- imported,
    # not reimplemented. It already picks v2FINAL_equity{suffix}.csv for v1/v2 and
    # v34_equity{suffix}.csv for v3/v4, with the cadence fallbacks, and getting
    # that resolution subtly different here would reconcile against another arm's
    # or another cadence's curve and report a confident MISMATCH of millions.
    #
    # THIS IS VISIBILITY, NOT A NEW SAFETY PROPERTY. backtest_runs.run() already
    # compares the re-run against this same curve and RETURNS WITHOUT WRITING any
    # of the six CSVs when the max absolute difference is 1 paisa or more. So a
    # trail only exists on disk if this check has already passed upstream; showing
    # it here makes the log self-contained for a reader who has only the log.
    import backtest_runs as _as
    # NAMED ref_curve, NOT ref. Section [A] below already binds `ref` to the
    # derived open price of each fill, inside the day loop -- a curve called `ref`
    # survived exactly until the first execution day and then became a float.
    ref_curve = _as._reference_curve(M, arm.name)
    # Names the COLUMN, not the file: _reference_curve chooses between several
    # candidate files and does not report which, and guessing the filename here
    # would be a second copy of that resolution -- the thing this import avoids.
    ref_name = f"engine curve [{arm.equity_column}]"

    # THE DRAWDOWN STOP'S OWN RECORD, for a stop arm: its events, and the lots and
    # tax years that give each exit's realised gains and the bill they fall in.
    stop_ev_by_day, exit_trigger, exit_lots, exit_years = {}, {}, None, None
    if arm.stop is not None:
        _f = M / f"daily_stop_events_{tag}.csv"
        _ev = (read_table(_f, parse_dates=["date"]) if _f.exists()
               else pd.DataFrame(columns=["date", "event"]))
        stop_ev_by_day = {d: g for d, g in _ev.groupby("date")}
        _trig = None
        for _, e in _ev.iterrows():
            if e["event"] == "trigger":
                _trig = e
            elif e["event"] == "exit fills":
                exit_trigger[e["date"]] = _trig
        _f = M / f"COST_LOTS_{tag}.csv"
        exit_lots = read_table(_f, parse_dates=["date"]) if _f.exists() else None
        _f = M / f"COST_TAX_YEARS_{tag}.csv"
        exit_years = read_table(_f) if _f.exists() else None

    sg = s.set_index("date")
    hg = {d: g for d, g in h.groupby("date")}
    tg = {d: g for d, g in t.groupby("date")}
    rg = {d: g for d, g in rk.groupby("decided_on")}
    kg = {d: g for d, g in sk.groupby("date")} if len(sk) else {}
    skipped_set = {(row["date"], row["symbol"]) for _, row in sk.iterrows()}
    dg = dc.set_index("decided_on")

    all_days = sorted(s["date"])
    dec_days = sorted(dc["decided_on"])
    rebal_no = {d: i + 1 for i, d in enumerate(dec_days)}

    # For an execution day, the source order was created on the last decision day.
    def prev_dec(d):
        p = [x for x in dec_days if x < d]
        return p[-1] if p else None

    # Rank and action per symbol on each decision day -- explains why it was traded.
    act_of = {}
    for d, g in rg.items():
        act_of[d] = {row["symbol"]: (int(row["rank"]), row["action"]) for _, row in g.iterrows()}

    # Order IDs: on each execution day, SELLs are S1..Sn and BUYs are B1..Bn. A stop
    # arm's exit sales are not part of a rebalance and are numbered X<n>-S1..Sn, n
    # counting the exit fill days.
    oid = {}
    exit_no = {d: k + 1 for k, d in enumerate(sorted(exit_trigger))}
    for d in sorted(tg):
        rno = rebal_no.get(prev_dec(d), 0)
        g = tg[d]
        for n, (_, o) in enumerate(g[g.action == "SELL"].iterrows(), 1):
            oid[(d, o["symbol"])] = (f"X{exit_no[d]:03d}-S{n}" if d in exit_no
                                     else f"R{rno:03d}-S{n}")
        for n, (_, o) in enumerate(g[g.action == "BUY"].iterrows(), 1):
            oid[(d, o["symbol"])] = f"R{rno:03d}-B{n}"

    # A symbol is never bought again while still held (the engine skips it), so each
    # position has exactly one entry price and round-trip P&L is unambiguous.
    entry, roundtrip = {}, {}
    for d in sorted(tg):
        g = tg[d]
        for _, o in g[g.action == "SELL"].iterrows():
            e = entry.pop(o["symbol"], None)
            if e is not None:
                net = (o["value"] - e["value"]) - e["tc"] - o["tc"]
                roundtrip[(d, o["symbol"])] = {
                    "buy_date": e["date"], "buy_px": e["price"],
                    "days": (d - e["date"]).days,
                    "pct": (o["price"] / e["price"] - 1) * 100 if e["price"] else 0.0,
                    "net": net}
        for _, o in g[g.action == "BUY"].iterrows():
            entry[o["symbol"]] = {"date": d, "price": o["price"],
                                  "value": o["value"], "tc": o["tc"]}

    # Replay entries so each day knows the entry date/price of what it currently holds.
    entry_at, cur = {}, {}
    for d in all_days:
        if d in tg:
            g = tg[d]
            for _, o in g[g.action == "SELL"].iterrows():
                cur.pop(o["symbol"], None)
            for _, o in g[g.action == "BUY"].iterrows():
                cur[o["symbol"]] = {"date": d, "price": o["price"]}
        entry_at[d] = dict(cur)

    L = ["=" * W,
         f" PREDICTIVE ENGINE -- FORENSIC DAILY LOG  |  {tag}  |  {arm.label}",
         "=" * W,
         f" Period          : {s['date'].min().date()} to {s['date'].max().date()}"
         f"   ({len(s):,} trading days)",
         f" Rebalances      : {len(dc)}   |  orders filled: {len(t):,}   |  orders skipped: {len(sk):,}",
         f" Capital         : Rs {_capital_axis.selected():,}  ->  Rs {s['total'].iloc[-1]:,.0f}",
         f" Total fees paid : Rs {s['cum_tc'].iloc[-1]:,.2f}",
         # Stated in the header of every universe's log, so a reader who opens this
         # file six months from now sees how the universe was constructed before
         # they see a single number from it.
         f" Survivorship    : {market_data.describe_state()}",
         "=" * W, legend_for(arm), "=" * W]

    # THE MISSING TERM IN THE CASH IDENTITY. Empty dict under tax=off.
    _tx = tax_due_by_date(all_days, t)
    tax_due = _tx.get("due", {}) if _tx else {}
    tax_fy = _tx.get("label", {}) if _tx else {}

    ok_cash = ok_eq = ok_sh = 0
    ok_ref = n_ref = 0
    n_stale_fill = n_stale_hold = n_hold_rows = 0
    stale_syms = {}
    fail_lines = []
    prev_cash, prev_tc = float(_capital_axis.selected()), 0.0
    prev_qty, peak, last_dec = {}, 0.0, None

    for dn, d in enumerate(all_days, 1):
        r = sg.loc[d]
        is_dec, is_exe = d in dg.index, d in tg
        if is_dec and is_exe:
            dtype = "EXECUTION + REBALANCE"
        elif is_dec:
            dtype = "REBALANCE DAY"
        elif is_exe:
            dtype = "EXECUTION DAY"
        else:
            dtype = "HOLD DAY"

        g = tg[d] if is_exe else None
        nb = int((g.action == "BUY").sum()) if is_exe else 0
        ns = int((g.action == "SELL").sum()) if is_exe else 0
        buy_fees_today = float(g[g.action == "BUY"]["tc"].sum()) if is_exe else 0.0
        sell_fees_today = float(g[g.action == "SELL"]["tc"].sum()) if is_exe else 0.0
        fees_today = buy_fees_today + sell_fees_today
        total = float(r["total"])
        peak = max(peak, total)
        dd = (total / peak - 1) * 100 if peak > 0 else 0.0
        cum_ret = (total / _capital_axis.selected() - 1) * 100

        L += ["", "#" * W,
              f"# [{d.date()}]  {d.strftime('%A'):<9} |  trading day {dn:,} of {len(all_days):,}"
              f"  |  {dtype}",
              f"#   holding {int(r['n_stocks'])} stocks  |  invested {r['invested_pct']}%"
              f"  |  cash {r['cash_pct']}%  |  equity Rs {total:,.0f}"
              f"  |  cumulative return {cum_ret:+.1f}%  |  drawdown {dd:.1f}%",
              f"#   today: {nb} BUY, {ns} SELL  |  fees today Rs {fees_today:,.2f}"
              f"  (BUY {buy_fees_today:,.2f} + SELL {sell_fees_today:,.2f})"
              f"  |  cumulative fees Rs {r['cum_tc']:,.2f}  ({int(r['cum_trades'])} orders to date)",
              "#" * W]

        # ---------------- [A] EXECUTION ----------------
        L.append("")
        src = prev_dec(d)
        _exit = exit_trigger.get(d)
        if is_exe and _exit is not None:
            src = all_days[dn - 2]
            L.append(f"  >>> DRAWDOWN EXIT -- triggered at the CLOSE of "
                     f"{pd.Timestamp(_exit['date']).date()}: peak Rs {_exit['peak']:,.2f} on "
                     f"{pd.Timestamp(_exit['peak_date']).date()}, equity Rs "
                     f"{_exit['equity']:,.2f}, drawdown {_exit['drawdown_pct']:+.2f}%")
        if is_exe:
            L.append(f"  >>> [A] ORDER EXECUTION      created at the CLOSE of "
                     f"{src.date() if src is not None else '?'}, filled at TODAY's OPEN")
            L.append(f'      {"OrderID":<10}{"Side":<6}{"Symbol":<13}{"Qty":>7}'
                     f'{("Open" if op is not None else "Open(der)"):>12}{"FillPx":>11}{"Slip Rs":>10}'
                     f'{"Value":>14}{"TxnFee":>9}')
            slip_total = 0.0
            for _, o in pd.concat([g[g.action == "SELL"], g[g.action == "BUY"]]).iterrows():
                if op is not None:
                    ref = float(op.at[pd.Timestamp(d), o["symbol"]])
                else:
                    sgn = (1 - SLIPPAGE) if o["action"] == "SELL" else (1 + SLIPPAGE)
                    ref = o["price"] / sgn
                slip = abs(ref - o["price"]) * int(o["qty"])
                slip_total += slip
                L.append(f'      {oid.get((d, o["symbol"]), "-"):<10}{o["action"]:<6}'
                         f'{o["symbol"]:<13}{int(o["qty"]):>7}{ref:>12,.2f}{o["price"]:>11,.2f}'
                         f'{slip:>10,.0f}{o["value"]:>14,.2f}{o["tc"]:>9,.2f}')
                _sn = stale_note(raw_idx, cal_sorted, o["symbol"], d)
                if _sn:
                    n_stale_fill += 1
                    stale_syms[o["symbol"]] = stale_syms.get(o["symbol"], 0) + 1
                    L.append(f'          !! {_sn}  -- this fill is at a price that '
                             f'did not trade today')
                why = act_of.get(src, {}).get(o["symbol"], (None, None))
                if o["action"] == "SELL":
                    rt = roundtrip.get((d, o["symbol"]))
                    wtxt = (f'rank {why[0]} -- fell out of the buffer ({BUFFER})' if why[0]
                            else "fell out of the buffer")
                    if _exit is not None:
                        wtxt = "drawdown exit -- every holding is sold"
                    if rt:
                        L.append(f'          -> {wtxt}  |  entered {rt["buy_date"].date()} at '
                                 f'{rt["buy_px"]:,.2f}, held {rt["days"]} days  |  '
                                 f'round trip {rt["pct"]:+.2f}%, net P&L Rs {rt["net"]:+,.0f}')
                    else:
                        L.append(f'          -> {wtxt}')
                else:
                    L.append(f'          -> rank {why[0] if why[0] else "?"} -- entered the '
                             f'top {TOP_N} and was not already held')
                    if pd.notna(o.get("wanted_qty", float("nan"))):
                        L.append(f'          -> TRIMMED: wanted {int(o["wanted_qty"]):,} sh, '
                                 f'filled {int(o["qty"]):,} sh; cash was short by Rs '
                                 f'{float(o["cash_shortfall"]):,.2f}')
            b, sl = g[g.action == "BUY"], g[g.action == "SELL"]
            L.append(f'      TOTAL   BUY {len(b)} Rs {b["value"].sum():>12,.0f}   |   '
                     f'SELL {len(sl)} Rs {sl["value"].sum():>12,.0f}')
            L.append(f'      fees    BUY Rs {b["tc"].sum():,.2f}   +   '
                     f'SELL Rs {sl["tc"].sum():,.2f}   =   Rs {g["tc"].sum():,.2f}'
                     f'   |   slippage cost Rs {slip_total:,.0f}')
            if _exit is not None:
                L.append(f'      exit    proceeds Rs {sl["value"].sum():,.2f}   charges Rs '
                         f'{sl["tc"].sum():,.2f}   slippage Rs {slip_total:,.2f}')
                if exit_lots is not None and len(exit_lots):
                    _lt = exit_lots[exit_lots["date"] == d]
                    _st_g = float(_lt.loc[_lt["term"] == "short", "gain"].sum())
                    _lt_g = float(_lt.loc[_lt["term"] == "long", "gain"].sum())
                    L.append(f'      gains   realised by these sales: short-term Rs {_st_g:,.2f}, '
                             f'long-term Rs {_lt_g:,.2f}')
                    _fy = _lt["fy"].iloc[0] if len(_lt) else None
                    _y = (exit_years[exit_years["fy"] == _fy]
                          if exit_years is not None and _fy is not None else None)
                    if _y is not None and len(_y) and str(_y["tax"].iloc[0]) == "on":
                        _due = _y["deducted_on"].iloc[0]
                        L.append(f'      tax     on these gains is part of {_fy}\'s bill, Rs '
                                 f'{float(_y["total_tax"].iloc[0]):,.2f}, due on '
                                 f'{pd.Timestamp(_due).date() if pd.notna(_due) else "the backtest end"}')
                    else:
                        L.append("      tax     not charged in this run (tax off)")
        elif is_dec:
            L.append("  >>> [A] ORDER EXECUTION      none -- an order is created today and "
                     "fills tomorrow")
        else:
            L.append("  >>> [A] ORDER EXECUTION      none -- no order was pending")

        if d in kg:
            L.append("")
            L.append("      SKIPPED ORDERS (created but not filled):")
            for _, x in kg[d].iterrows():
                det = f'  [{x["detail"]}]' if isinstance(x["detail"], str) and x["detail"] else ""
                L.append(f'      {"":<10}{x["side"]:<6}{x["symbol"]:<13}  reason: {x["reason"]}{det}')

        # ---------------- [B] RECONCILIATION ----------------
        cash, mtm = float(r["cash"]), float(r["mtm"])
        yield_amt = prev_cash * CASH_DAILY
        sell_v = float(g[g.action == "SELL"]["value"].sum()) if is_exe else 0.0
        buy_v = float(g[g.action == "BUY"]["value"].sum()) if is_exe else 0.0
        tax_today = float(tax_due.get(d, 0.0))
        exp_cash = prev_cash + yield_amt + sell_v - buy_v - fees_today - tax_today
        d_cash, d_eq = exp_cash - cash, (cash + mtm) - total

        hh = hg.get(d)
        qty_now = {row["symbol"]: int(row["qty"]) for _, row in hh.iterrows()} if hh is not None else {}
        traded = {}
        if is_exe:
            for _, o in g.iterrows():
                traded[o["symbol"]] = traded.get(o["symbol"], 0) + \
                    (int(o["qty"]) if o["action"] == "BUY" else -int(o["qty"]))
        bad_sh = [sy for sy in set(list(qty_now) + list(prev_qty) + list(traded))
                  if prev_qty.get(sy, 0) + traded.get(sy, 0) != qty_now.get(sy, 0)]

        ref_v = (float(ref_curve.get(d))
                 if (ref_curve is not None and d in ref_curve.index) else None)
        r_ok = ref_v is None or abs(total - ref_v) <= TOL_CURVE
        if ref_v is not None:
            n_ref += 1
            ok_ref += r_ok
        c_ok, e_ok, s_ok = abs(d_cash) <= TOL_CASH, abs(d_eq) <= TOL_EQ, len(bad_sh) == 0
        ok_cash += c_ok; ok_eq += e_ok; ok_sh += s_ok
        if not (c_ok and e_ok and s_ok and r_ok):
            fail_lines.append(f"  {d.date()}  cash {d_cash:+.2f}  equity {d_eq:+.2f}  "
                              f"shares {'OK' if s_ok else ','.join(bad_sh)}")

        L.append("")
        L.append("  >>> [B] RECONCILIATION       (does the arithmetic tie out)")
        L.append(f'      CASH    opening Rs {prev_cash:>14,.2f}  + yield {yield_amt:>9,.2f}'
                 f'  + sales {sell_v:>12,.2f}')
        if tax_today:
            # THE TOTAL MOVES TO THE TAX LINE so that "= Rs <exp_cash>" is never
            # printed beside a subtotal that has not had the tax taken out yet.
            L.append(f'              - purchases {buy_v:>12,.2f}  - fees {fees_today:>12,.2f}'
                     f'  (BUY {buy_fees_today:,.2f} + SELL {sell_fees_today:,.2f})')
            L.append(f'              - capital-gains tax {tax_today:>12,.2f}'
                     f'  ({tax_fy.get(d, "")} assessed today, section 3(9): one lump'
                     f' sum, before this day\'s fills)'
                     f'  = Rs {exp_cash:>14,.2f}')
        else:
            L.append(f'              - purchases {buy_v:>12,.2f}  - fees {fees_today:>12,.2f}'
                     f'  (BUY {buy_fees_today:,.2f} + SELL {sell_fees_today:,.2f})'
                     f'  = Rs {exp_cash:>14,.2f}')
        L.append(f'              recorded Rs {cash:>14,.2f}   |   difference Rs {d_cash:+.2f}   '
                 f'{"OK" if c_ok else "*** FAIL ***"}')
        L.append(f'      EQUITY  cash {cash:>14,.2f}  + holdings {mtm:>14,.2f}'
                 f'  = {cash + mtm:>14,.2f}  |  recorded {total:>14,.2f}   '
                 f'{"OK" if e_ok else "*** FAIL ***"}')
        L.append(f'      SHARES  {len(qty_now)} symbols: opening quantity +/- today\'s trade '
                 f'= closing quantity   '
                 f'{"OK" if s_ok else "*** FAIL: " + ", ".join(bad_sh) + " ***"}')
        if ref_v is not None:
            L.append(f'      CURVE   this trail {total:>14,.2f}  |  {ref_name} {ref_v:>14,.2f}'
                     f'  |  difference Rs {total - ref_v:+.2f}   '
                     f'{"OK" if r_ok else "*** FAIL ***"}')
        if abs(prev_tc + fees_today - float(r["cum_tc"])) > TOL_CASH:
            L.append(f'      FEES    *** FAIL *** cumulative fees moved by '
                     f'{float(r["cum_tc"]) - prev_tc:,.2f} but today\'s fees were '
                     f'{fees_today:,.2f}')

        # ---------------- [C] POSITIONS ----------------
        L.append("")
        L.append("  >>> [C] POSITIONS            at TODAY's CLOSE, after execution")
        if hh is None or len(hh) == 0:
            L.append("      <fully in cash -- no positions held>")
        else:
            ea = entry_at[d]
            ranks = act_of.get(last_dec, {})
            L.append(f'      {"Symbol":<13}{"Qty":>7}{"Entry":>12}{"EntryPx":>10}{"ClosePx":>10}'
                     f'{"Value":>14}{"Wt%":>8}{"Unreal":>9}{"Days":>6}{"Rank":>6}  Status')
            for _, x in hh.sort_values("value", ascending=False).iterrows():
                e = ea.get(x["symbol"])
                epx = e["price"] if e else float("nan")
                edt = e["date"].date() if e else "-"
                unre = (x["price"] / epx - 1) * 100 if e and epx else 0.0
                days = (d - e["date"]).days if e else 0
                rnk, act = ranks.get(x["symbol"], (None, ""))
                st = (f"top {TOP_N}" if act in ("BUY", "HOLD-top") else
                      "buffer" if act == "HOLD-buffer" else
                      "exiting" if act == "SELL" else "-")
                _sn = stale_note(raw_idx, cal_sorted, x["symbol"], d)
                n_hold_rows += 1
                if _sn:
                    n_stale_hold += 1
                    stale_syms[x["symbol"]] = stale_syms.get(x["symbol"], 0) + 1
                L.append(f'      {x["symbol"]:<13}{int(x["qty"]):>7}{str(edt):>12}'
                         f'{epx:>10,.2f}{x["price"]:>10,.2f}{x["value"]:>14,.2f}'
                         f'{x["weight_pct"]:>7.2f}%{unre:>8.2f}%{days:>6}'
                         f'{(rnk if rnk else "-"):>6}  {st}'
                         + (f'   !! {_sn}' if _sn else ''))
            L.append(f'      {"TOTAL":<13}{"":>7}{"":>12}{"":>10}{"":>10}'
                     f'{hh["value"].sum():>14,.2f}{hh["weight_pct"].sum():>7.2f}%')
        L.append(f'      Invested Rs {mtm:,.2f} ({r["invested_pct"]}%)   |   '
                 f'Cash Rs {cash:,.2f} ({r["cash_pct"]}%)   |   TOTAL Rs {total:,.2f}')

        # ---------------- [D] ORDER CREATION ----------------
        if is_dec:
            x = dg.loc[d]
            L.append("")
            L.append(f"  >>> [D] ORDER CREATION       rebalance #{rebal_no[d]} -- signal taken at "
                     f"TODAY's CLOSE, fills at TOMORROW's OPEN")
            # BREADTH IS PRINTED FOR EVERY ARM, but only a breadth-scaled arm may
            # claim it drove the book. For mode="none" it is an OBSERVED
            # DIAGNOSTIC -- what a breadth-scaled arm would have done today -- and
            # is labelled as such, so a v1 log showing breadth collapsing while the
            # book stays fully invested reads correctly side by side with v2's.
            if arm.mode == "breadth":
                L.append(f'      breadth       : {int(x["breadth_pos"])}/{int(x["breadth_total"])} stocks '
                         f'with positive 20-day momentum  =  {x["breadth"]:.4f}')
                L.append(f'      exposure      : {x["exposure"]*100:.2f}%  '
                         f'(equal to breadth -- no threshold)')
            elif arm.stop is not None:
                L.append(f'      breadth       : {int(x["breadth_pos"])}/{int(x["breadth_total"])} stocks '
                         f'with positive 20-day momentum  =  {x["breadth"]:.4f}   '
                         f'[USED ONLY BY THE STOP, TO DECIDE RE-ENTRY]')
                L.append(f'      exposure      : {x["exposure"]*100:.2f}%  '
                         f'(100% while invested; the stop decides when it is out)')
            else:
                L.append(f'      breadth       : {int(x["breadth_pos"])}/{int(x["breadth_total"])} stocks '
                         f'with positive 20-day momentum  =  {x["breadth"]:.4f}   '
                         f'[OBSERVED ONLY -- NOT USED BY THIS ARM]')
                L.append(f'      exposure      : {x["exposure"]*100:.2f}%  '
                         f'(this arm is always 100% invested; breadth is ignored)')
            L.append(f'      sizing        : {SIZING_PROSE.get(arm.sizing, arm.sizing)}')
            L.append(f'      portfolio     : Rs {x["port_value"]:,.2f}   '
                     f'(of which cash Rs {x["cash_before"]:,.2f})')
            L.append(f'      invest value  : Rs {x["invest_value"]:,.2f}   '
                     f'= portfolio x exposure x 0.98 safety factor')
            L.append(f'      plan          : {int(x["n_buy"])} BUY, {int(x["n_sell"])} SELL   '
                     f'({int(x["n_held_before"])} stocks currently held)')
            act_inv = float(r["invested_pct"])
            gap = act_inv - float(x["exposure"]) * 100
            if arm.mode == "breadth":
                L.append(f'      target vs held: target exposure {x["exposure"]*100:.2f}% against '
                         f'{act_inv:.2f}% currently invested   '
                         f'(gap {gap:+.2f} pts -- existing holdings are not resized)')
            else:
                # AT A PINNED 100% THE GAP IS NOT AN EXPOSURE GAP. There is no
                # exposure decision to miss; the shortfall is uninvested cash the
                # funding rule could not deploy -- the defect described under
                # FUNDING in the legend. Calling it an exposure gap here was the
                # misleading half of this line.
                L.append(f'      invested      : {act_inv:.2f}% of the book is in stock; the '
                         f'{-gap:.2f} pts of cash is NOT an exposure decision --')
                L.append(f'                      this arm targets 100%, and the shortfall is '
                         f'capital the funding rule could not deploy (see FUNDING).')
            if float(x["invest_value"]) <= 0:
                L.append("      NOTE          : invest value is zero -- no BUY will fill tomorrow, "
                         "only SELLs.")
            gg = rg.get(d)
            if gg is not None:
                nxt = [z for z in all_days if z > d]
                nxt = nxt[0] if nxt else None
                L.append("")
                L.append(f'      {"Rank":>5}  {"Symbol":<13}{"Score":>12}{"Vol60":>9}{"TgtWt%":>9}'
                         f'{"Held":>6}  {"Action":<12}OrderID')
                for _, y in gg.sort_values("rank").iterrows():
                    v = f'{y["vol60"]:.4f}' if pd.notna(y["vol60"]) else "-"
                    myid = oid.get((nxt, y["symbol"]), "") if nxt is not None else ""
                    myid = myid if y["action"] in ("BUY", "SELL") else ""
                    if not myid and y["action"] in ("BUY", "SELL") and \
                            (nxt, y["symbol"]) in skipped_set:
                        myid = "SKIPPED (see section A of the next day)"
                    L.append(f'      {int(y["rank"]):>5}  {y["symbol"]:<13}{y["score"]:>12.6f}'
                             f'{v:>9}{y["target_wt_pct"]:>8.2f}%'
                             f'{"Y" if y["held_before"] else "N":>6}  {y["action"]:<12}{myid}')
                L.append(f"      (ranks 1-{TOP_N} are bought or held, {TOP_N+1}-{BUFFER} are "
                         f"held in the buffer, {BUFFER+1}+ are sold)")
            # WHAT THIS ORDER ACTUALLY DID, counted by reason. The per-day list in
            # section [A] of tomorrow shows each skipped order; this is the tally
            # for the order created today, so a reader sees at the point of
            # DECISION how much of the plan will not survive to execution.
            nxt_d = [z for z in all_days if z > d]
            skg = kg.get(nxt_d[0]) if nxt_d else None
            if skg is not None and len(skg):
                vc = skg["reason"].value_counts()
                L.append(f'      skips tomorrow: {len(skg)} of {int(x["n_buy"]) + int(x["n_sell"])} '
                         f'orders will not fill  ('
                         + ", ".join(f"{k} x{v}" for k, v in vc.items()) + ')')
            L.append("      -> the order is pending and fills at the next trading day's OPEN")
            last_dec = d

        # ---------------- [D] DRAWDOWN STOP ----------------
        _sev = stop_ev_by_day.get(d)
        if _sev is not None:
            L.append("")
            L.append("  >>> [D] DRAWDOWN STOP")
            for _, e in _sev.iterrows():
                _dd = "" if pd.isna(e["drawdown_pct"]) else f'  drawdown {e["drawdown_pct"]:+.2f}%'
                _pk = "" if pd.isna(e["peak"]) else f'  peak Rs {e["peak"]:,.2f}'
                L.append(f'      {e["event"].upper():<28} {e["detail"]}')
                L.append(f'      {"":<28} state {e["state"]}{_pk}  equity Rs '
                         f'{e["equity"]:,.2f}{_dd}')
            if is_dec and "superseded" in dg.columns and pd.notna(dg.loc[d].get("superseded")):
                L.append("      the rebalance order above is superseded by the drawdown exit "
                         "and is not sent")

        prev_cash, prev_tc, prev_qty = cash, float(r["cum_tc"]), qty_now

    # ---------------- FINAL VERIFICATION ----------------
    n = len(all_days)
    allok = (ok_cash == n and ok_eq == n and ok_sh == n)
    L += ["", "=" * W,
          " VERIFICATION SUMMARY -- arithmetic checks across the whole file",
          "=" * W,
          f"   trading days checked        : {n:,}",] + ([] if not tax_due else [
          # ONLY UNDER tax=on, so every untaxed log is byte-identical to the one
          # this file produced before the tax term existed.
          f"   TAX deducted (section 3(9)) : {len(tax_due):,} assessment day(s),"
          f" Rs {sum(tax_due.values()):,.2f} total",
          f"   {'':<28}  these days are IN the cash identity above, not exempted"
          f" from it",
    ]) + [
          f"   CASH identity passed        : {ok_cash:,} / {n:,}"
          f"   {'OK' if ok_cash == n else '*** FAIL ***'}",
          f"   EQUITY identity passed      : {ok_eq:,} / {n:,}"
          f"   {'OK' if ok_eq == n else '*** FAIL ***'}",
          f"   SHARE-COUNT identity passed : {ok_sh:,} / {n:,}"
          f"   {'OK' if ok_sh == n else '*** FAIL ***'}",
          (f"   ENGINE-CURVE agreement      : {ok_ref:,} / {n_ref:,}"
           f"   {'OK' if ok_ref == n_ref else '*** FAIL ***'}   (vs {ref_name})"
           if n_ref else
           "   ENGINE-CURVE agreement      : NOT CHECKED -- no published curve for "
           "this arm and cadence on disk"),
          f"   orders filled               : {len(t):,}  (every one is shown above)",
          *([f"   of which trimmed to fit cash: {int(t['wanted_qty'].notna().sum()):,}"
             f"  (marked TRIMMED above)"] if "wanted_qty" in t.columns else []),
          f"   orders skipped              : {len(sk):,}  (each shown with its reason)"]
    # BY REASON, NOT JUST A TOTAL. The mix is the diagnosis: a 100%-invested arm is
    # dominated by cash-short (the funding defect), a breadth-scaled arm barely
    # registers it, and "no open price" means a symbol had no usable open that
    # morning. A bare count hides which of those happened.
    if raw_idx is not None:
        L.append(f"   fills on a STALE price      : {n_stale_fill:,} / {len(t):,}"
                 f"   {'OK' if n_stale_fill == 0 else '*** see the !! lines in [A] ***'}")
        L.append(f"   holding rows on a STALE mark: {n_stale_hold:,} / {n_hold_rows:,}"
                 f"   {'OK' if n_stale_hold == 0 else '*** see the !! lines in [C] ***'}")
        if stale_syms:
            L.append("     symbols affected          : "
                     + ", ".join(f"{k} x{v}" for k, v in sorted(stale_syms.items())))
    else:
        L.append("   STALE-PRICE CHECK           : NOT RUN -- raw price directory unavailable")
    if len(sk):
        for _rsn, _n in sk["reason"].value_counts().items():
            L.append(f"     - {_rsn:<26}: {_n:,}")
    else:
        L.append("     - none")
    if arm.stop is not None:
        _all_ev = (pd.concat(stop_ev_by_day.values()) if stop_ev_by_day
                   else pd.DataFrame(columns=["event", "drawdown_pct"]))
        _tr = _all_ev[_all_ev["event"] == "trigger"]
        L.append(f"   drawdown exits              : {len(_tr):,}"
                 + (f"   deepest trigger {_tr['drawdown_pct'].min():+.2f}%" if len(_tr) else ""))
        L.append(f"   re-entries                  : "
                 f"{int((_all_ev['event'] == 're-entry filled').sum()):,}")
        L.append(f"   days with no holding        : {int((s['n_stocks'] == 0).sum()):,}")
    L += [
          f"   final equity                : Rs {s['total'].iloc[-1]:,.2f}",
          ""]
    if fail_lines:
        L += ["   MISMATCHED DAYS:"] + fail_lines + [""]
    L += [f"   VERDICT: {'every day reconciles.' if allok else 'some days failed -- see above.'}",
          "=" * W]

    # THE COST TOTALS END THE LOG. Every figure comes from reports.py,
    # and daily_log_totals raises, failing the run, if any differs from
    # COST_SUMMARY_<tag>.txt. Final equity is the engine's curve at full
    # precision, the value cost_report was given; daily_summary's total is rounded
    # to the paisa and would move gross profit.
    from settings import tax as _tax_axis
    _cap = _capital_axis.selected()
    if ref_curve is None:
        raise CostReconciliationError(
            f"{tag}: no engine curve on disk for {arm.name}, so the cost totals have no final equity")
    L += daily_log_totals(M, tag, arm.name, float(ref_curve.loc[all_days[-1]]), bh,
                                      float(_cap), bool(_tax_axis.selected()), W)

    out = M / f"DAILY_LOG_{tag}.txt"
    out.write_text("\n".join(L))
    print(f"  {tag}: {n:,} days, {len(L):,} lines -> {out.name}")
    print(f"       reconciliation  cash {ok_cash}/{n}  equity {ok_eq}/{n}  shares {ok_sh}/{n}"
          f"  {'ALL OK' if allok else '*** CHECK FAILURES ***'}")
    return out


def make_daily_log():
    """STEP 15. Body moved out of the __main__ guard, unchanged.

    S4 gave every pipeline step a function boundary so run.py could call it in
    process; this file and nautilus_port.py nt_export_scores were missed, and nothing noticed
    because run.py still SPAWNED each step, and a subprocess runs the __main__
    guard whether or not a main() exists. The first full in-process run stopped
    here with AttributeError. The statements below are the guard's, in order.
    """
    import settings
    from settings import REGISTRY, universe_axis
    print("Building forensic daily logs...")

    # FOUR INDEPENDENT LOGS, ONE PER UNIVERSE. build() is the same code for all of
    # them -- only the metrics folder and the tag differ -- and DAILY_LOG_{tag}.txt
    # has no consumer, so nothing downstream depends on any particular one being
    # present. Each is therefore guarded on its own universe and skipped with a
    # reason rather than taking the others down with it.
    #
    # THE METRICS DIRECTORY COMES FROM THE UNIVERSE, not from a per-tag
    # `import config_x` under a per-tag `if`. That shape was four hand-written
    # branches, two of them for universes since deleted, which would have gone on
    # importing a config module that no longer exists. u.metrics_dir is the same path the config module defines,
    # read from the registry entry that already holds it.
    #
    # SELECTION, NOT REGISTRATION. `--universe nifty50` leaves seven universes
    # registered but unselected, and this step used to do their work anyway --
    # writing artefacts for universes the caller did not ask for. universe_axis.selected_tags() defaults to every
    # registered universe, so a standalone run of this file is unchanged.
    # THE SCANNER LOSES ITS LITERALS HERE, KNOWINGLY. check_pipeline_order used
    # the literal REGISTRY["<tag>"] subscripts to resolve this step's outputs; a
    # loop over REGISTRY reads the same at runtime and leaves the checker blind to
    # them. That is the cost of not naming universes in four branches, and this
    # step's outputs (DAILY_LOG_*.txt) have no downstream consumer for the checker
    # to order against.
    # ONE LOG PER (UNIVERSE, SELECTED ARM), not one per universe. The tag comes
    # from backtest_runs.artefact_tag -- the same call the writer uses -- so the
    # reader cannot drift from the writer's naming.
    import portfolio as _ar
    import backtest_runs as audit_step

    def _logs_for(u, mdir):
        # ONCE PER UNIVERSE, not once per arm: this reads every raw CSV in the
        # universe, and all four arms share the same answer.
        raw_idx, cal_sorted = raw_row_index(u)
        # THE BUY & HOLD'S COSTS, ALSO ONCE PER UNIVERSE: every arm's log shows the
        # same basket. reports.bh_costs is the call write() makes for
        # COST_SUMMARY, on the prices audit_step replays.
        from settings import tax as _tax_axis
        _cap = _capital_axis.selected()
        bh = None
        for _arm in _ar.selected():
            tag = audit_step.artefact_tag(u, _arm)
            gone = missing_trail(mdir, tag)
            if gone:
                # NEVER SILENTLY NOTHING. A combination with no trail on disk says
                # so, by name, in run.py's NOT RUN style -- the whole point of this
                # change was to stop producing no log and no explanation.
                print(f"  NOT RUN  {tag}: no audit trail on disk "
                      f"({', '.join(g + '_' + tag + '.csv' for g in gone)}). "
                      f"{u.label} has no {_arm.name} trail.")
                continue
            if bh is None:
                px, op, _, bd = audit_step.prices(u)
                bh = bh_costs(px, op, bd, float(_cap), bool(_tax_axis.selected()))
            build(mdir, tag, _arm, bh, raw_idx, cal_sorted, op)

    SEL = set(universe_axis.selected_tags())
    for _t in REGISTRY:
        if _t in SEL:
            # PIT RUNS: this step loops over universes itself, so it sets each
            # universe's membership here; None in a static run.
            market_data.MEMBERSHIP = market_data.membership_for(REGISTRY[_t])
            _logs_for(REGISTRY[_t], REGISTRY[_t].metrics_dir)
        else:
            print(f"  {_t} not selected for this run -- skipping its daily log")


# ======================================================================================
# CELL AND RUN SUMMARY LINES. From results/tradability.py (moved 2026-11-27).
# ======================================================================================
# tradability -- which (symbol, date) pairs the backtest may transact on.
#
# WHAT THIS EXISTS TO STOP
#     px and op are pivots with .ffill() applied -- 41 such pivots across 37 files.
#     A symbol that did not trade on a date still carries a price: the last one it
#     had. A fill at that price is a fill at a price nobody quoted, and a holding
#     marked at it is marked at a stale mark.
#
#     Measured before this module existed, on MidCap150:
#       PATANJALI  51 sessions with no raw row, ffill froze it at Rs 1.10, and the
#                  resumption row is Rs 5.35 -- a +386% single-day return that the
#                  EXTREME_RET guard flags but that px/op still trade through.
#       AIIL       73 sessions with no raw row across 44 separate gaps, on a stock
#                  whose median day is Rs 900,042 of turnover.
#       HEXT       1,069 sessions -- Hexaware delisted in 2020 and relisted in 2025 --
#                  and the resumption close is 762.55 against a pre-delisting close
#                  of 762.55, an exact match across 4.3 years.
#
#     NONE of these are visible to the existing guards. They never trip the +-55%
#     EXTREME_RET scan (AIIL and HEXT move less than that), and they never trip
#     "no open price (NaN/<=0)" because ffill supplies a price -- that reason fires
#     ZERO times across every midcap150 and nifty100 trail. Asking whether a RAW ROW EXISTED
#     is the only thing that finds them.
#
# WHY A SEPARATE, PRICE-SIDE FLAG AND NOT bad_ret OR scorable
#     bad_ret feeds the feature mask and the fwd_ret label; it is return-side.
#     scorable is deliberately SCORE-side (the panel build in market_data.py) -- the
#     price/score separation exists because the old `dropna(subset=FEATS_V2)` deleted
#     PRICES for a feature reason and ffill then bridged the hole, which is where the
#     +24,772.7% PATANJALI figure came from. Widening scorable would re-introduce
#     exactly that. This is a third flag and it gates TRANSACTING, not ranking.
#
# THE RULE THE ENGINE APPLIES, SINCE 2026-10-16: sessions_with_row()
#     A name is traded only on a session that has a row for it: a valid open and
#     close, on the trading calendar. On any other session nothing in it is bought or
#     sold. A held name keeps its position, valued at its last close, and a sale due
#     on such a session waits for the next session with a row, at that session's
#     open. market_data.tradeable_on(symbol, dt) asks only whether `dt` itself has a
#     row, so no decision reads a row dated after it.
#
#     UNTIL 2026-10-16 THE ENGINE USED untradeable() BELOW, AND IT LOOKED AHEAD. It
#     blocked a gap only when two or more sessions were missing, a length known only
#     from the date of the next row, and test_exposure sold a holding at the open of
#     the last session before the gap because the next session had no row. Both read
#     rows dated after the decision day. untradeable(), gaps() and
#     resumption_report() were deleted on 2026-10-22; nothing called them.
#
# READ-ONLY AGAINST THE RAW DATA. Nothing here changes a price.

def _cagr(e):
    ny = (e.index[-1] - e.index[0]).days / 365.25
    return ((e.iloc[-1] / e.iloc[0]) ** (1 / ny) - 1) * 100


def _maxdd(e):
    return float(((e - e.cummax()) / e.cummax()).min() * 100)


def cell_lines(u, tag, last=None):
    """RUN.txt lines for one cell, named by its artefact tag; [] when nothing is stuck."""
    M = Path(u.metrics_dir)
    hf, sf = M / f"daily_holdings_{tag}.csv", M / f"daily_summary_{tag}.csv"
    if not hf.exists() or not sf.exists():
        return []
    h = read_table(hf, parse_dates=["date"])
    eq = read_table(sf, parse_dates=["date"]).set_index("date")["total"]
    end = eq.index[-1]
    last = last_rows(u) if last is None else last
    stuck = [r for r in h[h["date"] == end].itertuples()
             if r.symbol in last and last[r.symbol] < end]
    if not stuck:
        return []
    at_zero = eq.copy()
    out = []
    for r in stuck:
        lr = last[r.symbol]
        after = h[(h["symbol"] == r.symbol) & (h["date"] > lr)].set_index("date")["value"]
        at_zero = at_zero.sub(after.reindex(at_zero.index).fillna(0.0))
        out.append(f"stuck     : {tag} -- {r.symbol}: {int(r.qty):,} shares with no row "
                   f"after {lr.date()}, held at its last close {float(r.price):,.2f} = "
                   f"Rs {float(r.value):,.2f} on {end.date()}")
    out.append(f"at zero   : {tag} -- valued at zero from the session after its last row: "
               f"end equity Rs {at_zero.iloc[-1]:,.2f} (as run Rs {eq.iloc[-1]:,.2f}), "
               f"CAGR {_cagr(at_zero):.2f}% (as run {_cagr(eq):.2f}%), "
               f"MaxDD {_maxdd(at_zero):.2f}% (as run {_maxdd(eq):.2f}%)")
    return out


def run_lines(universes, arms):
    """The lines for every (universe, arm) cell of one run.py invocation."""
    import backtest_runs as audit_step
    from settings import survivorship_axis as _sva
    import settings
    out = []
    for u in universes:
        if not _sva.is_default() and settings.has_pit(u) and not u.is_pit:
            u = settings.pit_variant(u)
        last = None
        for a in arms:
            if last is None:
                last = last_rows(u)
            out += cell_lines(u, audit_step.artefact_tag(u, a), last)
    return out


# ======================================================================================
# REPORT: README TAX-ON TABLES. From tools/readme_tax_tables.py (moved 2026-11-27).
# ======================================================================================
# readme_tax_tables -- write README.md's current tax-on tables from the run artefacts.
#
#     ./venv/bin/python run.py --report readme_tax_tables           # rewrite the block in README.md
#     ./venv/bin/python run.py --report readme_tax_tables --print   # print it, write nothing
#
# The block sits between the two marker lines below and is replaced whole; nothing
# else in README.md is touched. Every figure is read from the files a run writes, for
# every registered universe and arm v1-v4, cadence 20, under the four tax-on settings
# (static and pit, research and tradeable):
#
#     tax off CAGR, MaxDD        v34_comparison<sfx>.csv of the matching tax-off run
#     tax on CAGR, MaxDD, Sharpe v34_comparison<sfx>_tax<pit>.csv, headline (nothing
#                                sold at the end)
#     sold on the last day       BH_LOTS_<tag>_tax<pit>.csv, "<arm> sold on the last day"
#     investable buy & hold      BH_LOTS, "bh_lots after tax": whole shares of every
#                                name bought at the first open and held, taxed
#     gap                        tax-on headline CAGR minus that buy & hold
#
# A missing file is written as "not on disk", never filled in.

BEGIN = "<!-- tax-on tables: written by run.py --report readme_tax_tables; do not edit by hand -->"
END = "<!-- end of tax-on tables -->"
README_TABLE_SETTINGS = (("static", "research", "", ""), ("static", "tradeable", "_tradeable", ""),
            ("pit", "research", "", "_pit"), ("pit", "tradeable", "_tradeable", "_pit"))


def row(metrics_dir, tag, arm, prof, pit):
    a = arm_reg.ARMS[arm]
    M = Path(metrics_dir)
    off_f = M / f"v34_comparison{prof}{pit}.csv"
    on_f = M / f"v34_comparison{prof}_tax{pit}.csv"
    bh_tag = tag if arm == "v2" else f"{tag}_{arm}"
    bh_f = M / f"BH_LOTS_{bh_tag}{prof}_tax{pit}.csv"
    cells = []
    if off_f.exists():
        r = read_table(off_f).set_index("Config").loc[a.label]
        cells += [f"{float(r['CAGR%']):.2f}", f"{float(r['MaxDD%']):.2f}"]
    else:
        cells += ["not on disk"] * 2
    if on_f.exists():
        r = read_table(on_f).set_index("Config").loc[a.label]
        on_cagr = float(r["CAGR%"])
        cells += [f"{on_cagr:.2f}", f"{float(r['MaxDD%']):.2f}", f"{float(r['Sharpe']):.2f}"]
    else:
        on_cagr = None
        cells += ["not on disk"] * 3
    if bh_f.exists():
        b = read_table(bh_f).set_index("line")
        last = float(b.loc[f"{arm} sold on the last day", "cagr_full"])
        inv = float(b.loc["bh_lots after tax", "cagr_full"])
        cells += [f"{last:.2f}", f"{inv:.2f}",
                  f"{on_cagr - inv:+.2f}" if on_cagr is not None else "not on disk"]
    else:
        cells += ["not on disk"] * 3
    return cells


def block():
    L = [BEGIN, "",
         "### Republished 2026-10-14 on the corrected tax ledger: every tax-on figure", "",
         "The tax ledger now follows the Income-tax Act in four places it did not before: "
         "the 4% cess, a short-term loss set off against long-term gains within a year, "
         "loss carry-forward for 8 years, and a holding period of more than twelve "
         "calendar months (KNOWN_ISSUES.md, \"The tax rules since 2026-10-14\"). Every "
         "tax-on figure below is on those rules; every tax-off figure is unchanged. Old "
         "against new for every cell is in diagnostics/tax_ledger_fix_20261014.csv and "
         "experiments/EXPERIMENTS.md. Cadence 20, one run per cell (n=1). The investable "
         "buy & hold is whole shares of every name bought at the first open and held, "
         "taxed; gap is the tax-on headline CAGR minus it. microcap250's pit window starts "
         "2021-10-29.", ""]
    head = ("| universe | arm | tax off: CAGR% | MaxDD% | tax on, headline: CAGR% | MaxDD% "
            "| Sharpe | tax on, sold on the last day: CAGR% | investable buy & hold, taxed: "
            "CAGR% | gap |")
    for surv, profile, prof, pit in README_TABLE_SETTINGS:
        L += [f"**{surv}, {profile} profile**", "", head, "|---|---|" + "---:|" * 8]
        for tag, u in REGISTRY.items():
            if pit and not has_pit(u):
                # A STATIC-ONLY UNIVERSE HAS NO PIT ROW, and says so rather than
                # leaving a gap or a guess (registry.has_pit).
                L.append(f"| {tag} | v1-v4 | not available: no membership file for this "
                         f"supplier bucket |" + " |" * 7)
                continue
            for arm in arm_reg.ARMS:
                L.append("| " + " | ".join([tag, arm] + row(u.metrics_dir, tag, arm, prof, pit))
                         + " |")
        L.append("")
    L.append(END)
    return "\n".join(L)


def readme_tax_tables():
    b = block()
    if "--print" in sys.argv:
        print(b)
        return 0
    readme = ROOT / "README.md"
    s = readme.read_text()
    if BEGIN in s:
        i, j = s.index(BEGIN), s.index(END) + len(END)
        s = s[:i] + b + s[j:]
    else:
        anchor = "### Republished 2026-10-10 on the supplier's new data delivery"
        if anchor not in s:
            raise SystemExit(f"README.md has neither the marker block nor the anchor {anchor!r}")
        i = s.index(anchor)
        s = s[:i] + b + "\n\n" + s[i:]
    # naming: axis-free -- README.md is one file; the block covers every setting
    readme.write_text(s)
    print(f"README.md: tax-on tables written ({b.count(chr(10)) + 1} lines)")
    return 0


# ======================================================================================
# REPORT: YEAR BY YEAR. From tools/year_by_year.py (moved 2026-11-27).
# ======================================================================================
# year_by_year -- calendar-year and sub-period returns of named cells against the
# equal-weight basket and the NSE index.
#
#     ./venv/bin/python run.py --report year_by_year --cells nifty200:v3,nifty200:v1,midcap100:v1
#
# Reads only existing artefacts. For each cell, under pit, tradeable, tax on and under
# static, tradeable, tax on (cadence 20):
#
#     cell     the arm's column of v34_equity<sfx>.csv
#     basket   the "buyhold" column of the same file: the equal-weight basket of that
#              universe construction, untaxed, rebalanced daily
#     index    the close of the universe's own NSE index file (a price index),
#              forward-filled onto the same dates
#
# A calendar year's return runs from the previous year's last close in the window (the
# window's first value for its first year) to the year's last close; 2026 ends on
# 2026-05-29. Sub-periods: 2019-01-01 to 2022-12-30 and 2023-01-02 to 2026-05-29, as
# CAGR. Writes diagnostics/year_by_year_<date>.csv and prints the tables.

YEAR_BY_YEAR_SETTINGS = (("pit, tradeable, tax on", "_tradeable_tax_pit"),
            ("static, tradeable, tax on", "_tradeable_tax"))
HALVES = (("2019-01-01 to 2022-12-30", "2019-01-01", "2022-12-30"),
          ("2023-01-02 to 2026-05-29", "2023-01-02", "2026-05-29"))


def yearly(s):
    out, prev = {}, s.iloc[0]
    for y, g in s.groupby(s.index.year):
        out[int(y)] = (g.iloc[-1] / prev - 1) * 100
        prev = g.iloc[-1]
    return out


def year_by_year():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    cells = [tuple(c.split(":")) for c in ap.parse_args().cells.split(",") if c.strip()]
    rows = []
    for tag, arm in cells:
        u = REGISTRY[tag]
        idx = (market_data.read_price_csv(u.index_file)[["date", "close"]].dropna()
               .set_index("date")["close"].sort_index())
        for setting, sfx in YEAR_BY_YEAR_SETTINGS:
            eq = read_table(Path(u.metrics_dir) / f"v34_equity{sfx}.csv",
                            parse_dates=["date"]).set_index("date")
            cell = eq[arm_reg.ARMS[arm].equity_column]
            bask = eq["buyhold"]
            ix = idx.reindex(eq.index.union(idx.index)).ffill().reindex(eq.index)
            yc, yb, yi = yearly(cell), yearly(bask), yearly(ix)
            for y in yc:
                rows.append({"universe": tag, "arm": arm, "setting": setting, "period": str(y),
                             "cell": yc[y], "basket": yb[y], "index": yi[y],
                             "cell_minus_basket": yc[y] - yb[y], "cell_minus_index": yc[y] - yi[y]})
            for name, a, b in HALVES:
                c, bb, ii = (cagr(x.loc[a:b]) for x in (cell, bask, ix))
                rows.append({"universe": tag, "arm": arm, "setting": setting,
                             "period": f"CAGR {name}", "cell": c, "basket": bb, "index": ii,
                             "cell_minus_basket": c - bb, "cell_minus_index": c - ii})
    df = pd.DataFrame(rows)
    out = ROOT / "diagnostics" / f"year_by_year_{time.strftime('%Y%m%d')}.csv"
    # naming: axis-free -- one measurement of named cells; the settings are a column
    df.to_csv(out, index=False, float_format="%.4f")
    for (tag, arm, setting), g in df.groupby(["universe", "arm", "setting"], sort=False):
        yrs = g[~g.period.str.startswith("CAGR")]
        print(f"\n{tag} {arm} -- {setting}")
        print(g[["period", "cell", "basket", "index", "cell_minus_basket", "cell_minus_index"]]
              .to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        print(f"  years above the basket: {int((yrs.cell_minus_basket > 0).sum())} of {len(yrs)}; "
              f"above the index: {int((yrs.cell_minus_index > 0).sum())} of {len(yrs)}")
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


# ======================================================================================
# REPORT: CAPITAL LADDER. From tools/capital_ladder.py (moved 2026-11-27).
# ======================================================================================
# capital_ladder -- named cells at several starting capitals, from their run artefacts.
#
#     ./venv/bin/python run.py --report capital_ladder --cells nifty200:v3,nifty200:v1,midcap100:v1 \
#         --capitals 500000,1000000,2500000,5000000,10000000,20000000,50000000
#
# Reads the artefacts of `run.py --survivorship pit --profile tradeable --tax on
# --capital C --impact K [--cap F]` runs (cadence 20, no --dd), already made; it
# runs nothing. run.py needs --impact with any capital but the default, 0 included,
# so the k-0 rows come from `--impact 0`. --impacts and --pcaps (default 0 and 1.0, the tradeable defaults)
# add those axes to the grid. Per cell, capital, k and cap:
#
#     cagr, maxdd           the arm's row of v34_comparison<sfx>.csv
#     cagr_minus_basket     minus that file's "buy & hold equal-weight" CAGR
#     slippage, charges     COSTS_<tag>.csv, summed over every fill
#     impact                COSTS_<tag>.csv impact_rs, summed; 0 when the run had k 0
#     tax                   COST_TAX_YEARS_<tag>.csv, total_tax summed
#     capped_fills          daily_skipped rows with reason "participation cap"
#     cash_short_skips      daily_skipped rows with reason "cash short ..."
#     share_too_dear        daily_skipped rows with reason "qty < 1 after sizing": one
#                           share cost more than the position's rupee target
#     avg_cash_pct          mean of daily_summary cash_pct
#     max_order_pct_adv     the largest fill as a percent of that stock's mean daily
#                           traded value (close x volume) over the 20 sessions before
#                           the fill, from the universe's raw pit price files
#
# Writes diagnostics/capital_ladder_<date>.csv and prints it.

def adv_value(raw_dir, sym, cache={}):
    """Series: mean close x volume over the 20 sessions before each date."""
    if sym not in cache:
        d = market_data.read_price_csv(Path(raw_dir) / f"{sym}.csv").set_index("date").sort_index()
        tv = (d["close"] * d["volume"])
        cache[sym] = tv.rolling(20).mean().shift(1)
    return cache[sym]


def capital_ladder():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    ap.add_argument("--capitals", required=True)
    ap.add_argument("--impacts", default="0")
    ap.add_argument("--pcaps", default="1.0")
    ap.add_argument("--append", action="store_true",
                    help="merge into today's file: rows for the same cell, capital, k and "
                         "cap are replaced, every other row is kept")
    a = ap.parse_args()
    cells = [tuple(c.split(":")) for c in a.cells.split(",")]
    caps = [int(x) for x in a.capitals.split(",")]
    ks = [float(x) for x in a.impacts.split(",")]
    pcs = [float(x) for x in a.pcaps.split(",")]
    from settings import capital_axis, impact_axis, pcap_axis
    import settings
    settings.profile_axis.set_selection("tradeable")

    def tail(cap, k, pc):
        """The capital, impact and cap suffixes, from the axes' own composers."""
        capital_axis.set_selection(cap)
        impact_axis.set_selection(k)
        pcap_axis.set_selection(pc)
        t = capital_axis.suffix() + impact_axis.suffix() + pcap_axis.suffix()
        capital_axis.set_selection(None); impact_axis.set_selection(None)
        pcap_axis.set_selection(None)
        return t
    by_u = {}
    for t, arm in cells:
        by_u.setdefault(t, []).append(arm)
    rows = []
    for tag, arms in by_u.items():
        if not has_pit(REGISTRY[tag]):
            raise SystemExit(pit_refusal(REGISTRY[tag]) + " The ladder reads pit cells only.")
        u = pit_variant(REGISTRY[tag])
        M = Path(u.metrics_dir)
        sel = "_" + "_".join(x for x in arm_reg.ARMS if x in arms)
        for pc, k, cap in ((pc, k, cap) for pc in pcs for k in ks for cap in caps):
            cs = tail(cap, k, pc)
            # the published run (every axis at its default) holds all four arms and
            # has no selection suffix
            comp_f = M / (f"v34_comparison_tradeable_tax_pit.csv" if cs == ""
                          else f"v34_comparison{sel}_tradeable_tax_pit{cs}.csv")
            comp = read_table(comp_f).set_index("Config")
            basket = float(comp.loc["buy & hold equal-weight", "CAGR%"])
            for arm in arms:
                A = arm_reg.ARMS[arm]
                at = f"{tag}_{arm}_tradeable_tax_pit{cs}"
                costs = read_table(M / f"COSTS_{at}.csv", parse_dates=["date"])
                years = read_table(M / f"COST_TAX_YEARS_{at}.csv")
                sk = read_table(M / f"daily_skipped_{at}.csv")
                sm = read_table(M / f"daily_summary_{at}.csv")
                best, where = 0.0, ""
                for r in costs.itertuples(index=False):
                    adv = adv_value(u.raw_data_dir, r.symbol).get(r.date, float("nan"))
                    if adv == adv and adv > 0:
                        pct = r.qty * r.fill_price / adv * 100
                        if pct > best:
                            best, where = pct, f"{r.symbol} {r.side} {r.date.date()}"
                c = comp.loc[A.label]
                rows.append({
                    "universe": tag, "arm": arm, "capital": cap, "impact_k": k, "pcap": pc,
                    "cagr": float(c["CAGR%"]), "maxdd": float(c["MaxDD%"]),
                    "cagr_minus_basket": float(c["CAGR%"]) - basket,
                    "slippage": float(costs["slippage_rs"].sum()),
                    "charges": float(costs["charges_total"].sum()),
                    "impact": float(costs["impact_rs"].sum()) if "impact_rs" in costs else 0.0,
                    "tax": float(years["total_tax"].sum()),
                    "capped_fills": int((sk["reason"] == "participation cap").sum()),
                    "cash_short_skips": int(sk["reason"].astype(str).str.startswith("cash short").sum()),
                    "share_too_dear": int((sk["reason"] == "qty < 1 after sizing").sum()),
                    "avg_cash_pct": float(sm["cash_pct"].mean()),
                    "max_order_pct_adv": best, "max_order": where})
    df = pd.DataFrame(rows)
    out = ROOT / "diagnostics" / f"capital_ladder_{time.strftime('%Y%m%d')}.csv"
    if a.append and out.exists():
        key = ["universe", "arm", "capital", "impact_k", "pcap"]
        old = read_table(out)
        keep = old.merge(df[key], on=key, how="left", indicator=True)
        old = old[(keep["_merge"] == "left_only").to_numpy()]
        df = pd.concat([old, df], ignore_index=True)
    # naming: axis-free -- one measurement over named cells; capital is a column
    df.to_csv(out, index=False, float_format="%.4f")
    print(df.to_string(index=False))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


# ======================================================================================
# REPORT: CELL REPORTS. From tools/cell_reports.py (moved 2026-11-27).
# ======================================================================================
# cell_reports -- five reports over published cells, one subcommand each.
#
#     ./venv/bin/python run.py --report cell_reports tax-on-all-arms
#     ./venv/bin/python run.py --report cell_reports tradeable-tax-grid
#     ./venv/bin/python run.py --report cell_reports tax-fix-old-new --old DIR
#     ./venv/bin/python run.py --report cell_reports cell-table OUT.csv [--root DIR]
#     ./venv/bin/python run.py --report cell_reports cell-compare OLD.csv NEW.csv OUT.csv
#
# Merged on 2026-10-18 from results/tax_on_all_arms.py, results/tradeable_tax_grid.py,
# tools/tax_fix_old_new.py, results/cell_table.py and results/cell_compare.py, which
# last exist at commit 4a4b427. Each subcommand takes the old script's arguments,
# writes the same files in the same format and returns the same exit code. Each old
# docstring is kept below as the *_DOC constant of its section.

def _cell_cagr(eq):
    """backtest_runs.metrics' CAGR, in percent, at full precision."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100)


# ---------------------------------------------------------------------------
# tax-on-all-arms (was results/tax_on_all_arms.py)
# ---------------------------------------------------------------------------
TAX_ON_ALL_ARMS_DOC = """
tax-on-all-arms -- every arm's tax-on headline CAGR against the investable taxed buy & hold.

    ./venv/bin/python run.py --report cell_reports tax-on-all-arms

Writes diagnostics/tax_on_all_arms.csv: 4 arms x 8 universes, research profile,
cadence 20, tax on, headline (nothing sold at the end, the last partial financial
year settled on the final session).

    arm_cagr   from that arm's column of results_<u>/metrics/v34_equity_tax.csv,
               engine_core.metrics' formula, rounded to 4 decimals -- the
               precision BH_LOTS_*.csv carries.
    bh_cagr    the investable taxed buy & hold headline, "bh_lots after tax" in
               BH_LOTS_<tag>_tax.csv. The basket is the same for every arm; the
               script checks that all four arms' BH_LOTS files agree on it.
    gap        arm_cagr - bh_cagr, from the unrounded arm CAGR.

CROSS-CHECK, NOT A SECOND SOURCE. Each arm's CAGR is also on the "<arm> after tax"
line of its own BH_LOTS file, from bh_lots_after_tax's separate taxed backtest.
The two must agree to 4 decimals, and the script exits 1 if any cell does not.
"""

TAX_ON_ALL_ARMS_OUT = ROOT / "diagnostics" / "tax_on_all_arms.csv"


def bh_lots(u, arm):
    tag = u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}"
    t = read_table(Path(u.metrics_dir) / f"BH_LOTS_{tag}_tax.csv").set_index("line")
    return t


def tax_on_all_arms_main():
    rows, bad = [], []
    for u in gated():
        eq = read_table(Path(u.metrics_dir) / "v34_equity_tax.csv",
                        parse_dates=["date"]).set_index("date")
        bh_seen = set()
        for arm in arm_reg.ARMS.values():
            c = _cell_cagr(eq[arm.equity_column])
            t = bh_lots(u, arm)
            bh = float(t.loc["bh_lots after tax", "cagr_full"])
            bh_seen.add(bh)
            other = float(t.loc[f"{arm.name} after tax", "cagr_full"])
            if round(c, 4) != other:
                bad.append(f"{u.tag} {arm.name}: v34_equity_tax {c:.4f}, BH_LOTS {other:.4f}")
            rows.append({"universe": u.tag, "arm": arm.name, "label": arm.label,
                         "arm_cagr": round(c, 4), "bh_cagr": bh,
                         "gap": round(c - bh, 4),
                         "arm_final_equity": round(float(eq[arm.equity_column].iloc[-1]), 2),
                         "arm_tax_paid": float(t.loc[f"{arm.name} after tax", "tax_paid"])})
        if len(bh_seen) != 1:
            bad.append(f"{u.tag}: the four BH_LOTS files disagree on the buy & hold: {sorted(bh_seen)}")
    df = pd.DataFrame(rows)
    # naming: axis-free -- a record fixed to research, cadence 20, tax on; it
    # varies over no published axis
    df.to_csv(TAX_ON_ALL_ARMS_OUT, index=False, quoting=csv.QUOTE_MINIMAL)
    print(df.to_string(index=False))
    if bad:
        print("\nCROSS-CHECK FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"\n{len(df)} cells; every arm CAGR agrees with its BH_LOTS line to 4 decimals. -> {TAX_ON_ALL_ARMS_OUT}")
    return 0


# ---------------------------------------------------------------------------
# tradeable-tax-grid (was results/tradeable_tax_grid.py)
# ---------------------------------------------------------------------------
TRADEABLE_TAX_GRID_DOC = """
tradeable-tax-grid -- research against tradeable, tax on, all 32 cells.

    ./venv/bin/python run.py --report cell_reports tradeable-tax-grid

Reads the artefacts of two pipeline runs at cadence 20, tax on:
    research   run.py --universe all --arm all --tax on
    tradeable  run.py --universe all --arm all --tax on --profile tradeable
and writes diagnostics/tradeable_tax_all_arms.csv, one row per (universe, arm).

    research_cagr, tradeable_cagr   that arm's column of v34_equity_tax.csv and
                                    v34_equity_tradeable_tax.csv, full precision,
                                    rounded to 4 decimals
    diff                            tradeable - research
    cap_binds                       rows with reason "participation cap" in the
                                    tradeable run's own daily_skipped artefact
    bh_research, bh_tradeable       "bh_lots after tax" from each profile's
                                    BH_LOTS file; the basket takes no cap, so the
                                    two must be equal, and the script checks it
    gap_research, gap_tradeable     arm minus the investable taxed buy & hold

The tradeable profile is UNGATED (costs.UNGATED_NOTICE): nothing replays what
the port does under it. These are engine figures, not certified ones.
"""

TRADEABLE_TAX_GRID_OUT = ROOT / "diagnostics" / "tradeable_tax_all_arms.csv"


def tag(u, arm, sfx):
    return (u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}") + sfx


def tradeable_tax_grid_main():
    rows, bad = [], []
    for u in gated():
        M = Path(u.metrics_dir)
        eq_r = read_table(M / "v34_equity_tax.csv", parse_dates=["date"]).set_index("date")
        eq_t = read_table(M / "v34_equity_tradeable_tax.csv", parse_dates=["date"]).set_index("date")
        for arm in arm_reg.ARMS.values():
            r = _cell_cagr(eq_r[arm.equity_column])
            t = _cell_cagr(eq_t[arm.equity_column])
            bh_r = float(read_table(M / f"BH_LOTS_{tag(u, arm, '_tax')}.csv")
                         .set_index("line").loc["bh_lots after tax", "cagr_full"])
            bh_t = float(read_table(M / f"BH_LOTS_{tag(u, arm, '_tradeable_tax')}.csv")
                         .set_index("line").loc["bh_lots after tax", "cagr_full"])
            if bh_r != bh_t:
                bad.append(f"{u.tag} {arm.name}: buy & hold research {bh_r} tradeable {bh_t}")
            sk = read_table(M / f"daily_skipped_{tag(u, arm, '_tradeable_tax')}.csv")
            binds = int((sk["reason"] == "participation cap").sum()) if len(sk) else 0
            rows.append({"universe": u.tag, "arm": arm.name,
                         "research_cagr": round(r, 4), "tradeable_cagr": round(t, 4),
                         "diff": round(t - r, 4), "cap_binds": binds,
                         "bh_cagr": bh_r,
                         "gap_research": round(r - bh_r, 4),
                         "gap_tradeable": round(t - bh_t, 4)})
    df = pd.DataFrame(rows)
    # naming: axis-free -- a record of one fixed comparison (cadence 20, tax on,
    # research against tradeable); it varies over no published axis
    df.to_csv(TRADEABLE_TAX_GRID_OUT, index=False)
    print(df.to_string(index=False))
    if bad:
        print("\nCHECK FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"\n{len(df)} cells -> {TRADEABLE_TAX_GRID_OUT}")
    return 0


# ---------------------------------------------------------------------------
# tax-fix-old-new (was tools/tax_fix_old_new.py)
# ---------------------------------------------------------------------------
TAX_FIX_OLD_NEW_DOC = """
tax-fix-old-new -- every tax-on cell before and after the tax-ledger fix of 2026-10-14.

    ./venv/bin/python run.py --report cell_reports tax-fix-old-new --old DIR

DIR holds results_<tag>/metrics/ copies of the tax-on artefacts taken before the
rerun. The new figures are the live metrics directories. For every registered
universe, arm v1-v4, cadence 20, static and pit, research and tradeable, tax on:

    total_tax     sum of total_tax in COST_TAX_YEARS_<tag>.csv
    cagr, maxdd, final_equity   the arm's row of v34_comparison<sfx>.csv

Writes diagnostics/tax_ledger_fix_20261014.csv and prints the summary.
"""

CELL_REPORT_SETTINGS = (("static", "research", "_tax"), ("static", "tradeable", "_tradeable_tax"),
            ("pit", "research", "_tax_pit"), ("pit", "tradeable", "_tradeable_tax_pit"))

TAX_FIX_OLD_NEW_OUT = ROOT / "diagnostics" / "tax_ledger_fix_20261014.csv"


def figures(M, tag, arm, sfx):
    a = arm_reg.ARMS[arm]
    ct = tag if arm == "v2" else f"{tag}_{arm}"
    years = read_table(M / f"COST_TAX_YEARS_{ct}{sfx}.csv")
    c = read_table(M / f"v34_comparison{sfx}.csv").set_index("Config").loc[a.label]
    return {"total_tax": float(years["total_tax"].sum()), "cagr": float(c["CAGR%"]),
            "maxdd": float(c["MaxDD%"]), "final_equity": float(c["FinalEquity"])}


def tax_fix_old_new_main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    old_root = Path(ap.parse_args(argv).old)
    rows = []
    for tag, u in REGISTRY.items():
        new_M = Path(u.metrics_dir)
        old_M = old_root / new_M.relative_to(ROOT)
        for surv, profile, sfx in CELL_REPORT_SETTINGS:
            for arm in arm_reg.ARMS:
                o, n = figures(old_M, tag, arm, sfx), figures(new_M, tag, arm, sfx)
                rows.append({"universe": tag, "arm": arm, "survivorship": surv,
                             "profile": profile,
                             **{f"{k}_old": o[k] for k in o}, **{f"{k}_new": n[k] for k in n},
                             "tax_change": n["total_tax"] - o["total_tax"],
                             "cagr_change": n["cagr"] - o["cagr"],
                             "maxdd_change": n["maxdd"] - o["maxdd"],
                             "final_equity_change": n["final_equity"] - o["final_equity"]})
    df = pd.DataFrame(rows)
    # naming: axis-free -- one dated comparison over every tax-on cell, the settings are columns
    df.to_csv(TAX_FIX_OLD_NEW_OUT, index=False, float_format="%.6f")
    print(f"wrote {TAX_FIX_OLD_NEW_OUT.relative_to(ROOT)}: {len(df)} cells")
    for k in ("tax_change", "cagr_change", "maxdd_change", "final_equity_change"):
        print(f"  {k:<20} min {df[k].min():>14,.2f}  median {df[k].median():>14,.2f}  "
              f"max {df[k].max():>14,.2f}")
    return 0


# ---------------------------------------------------------------------------
# cell-table (was results/cell_table.py)
# ---------------------------------------------------------------------------
CELL_TABLE_DOC = """
cell-table -- one row per (universe, arm, profile) from the tax-on artefacts.

    ./venv/bin/python run.py --report cell_reports cell-table OUT.csv [--root DIR]

Reads, for every registered universe, arm and profile (research, tradeable), cadence
20, the BH_LOTS file a tax-on run writes (bh_lots_after_tax.py) and the two
v34_comparison files (tax off and tax on). --root points at a directory holding
results_<tag>/ folders of metrics, for a copy taken before a rebuild; the default
is each universe's live metrics directory.

    cagr_off                 "<arm> before tax": the arm with tax off
    cagr_on                  "<arm> after tax": tax on, headline
    cagr_last_day            "<arm> sold on the last day"
    bh_reference             "bh published": the untaxed daily-rebalanced index
    bh_investable            "bh_lots after tax": held lots, taxed, headline
    bh_investable_last_day   "bh_lots sold on the last day"
    gap_on                   cagr_on - bh_investable, as the BH_LOTS file states it
    gap_last_day             cagr_last_day - bh_investable_last_day
    maxdd_off, sharpe_off, maxdd_on, sharpe_on   from v34_comparison

The tax-off MaxDD and Sharpe come from the tax-off run's v34_comparison file, so
they are empty for a profile whose tax-off run was not made.
"""

PROFILES = ("research", "tradeable")


def _cmp(M, sfx, label):
    p = M / f"v34_comparison{sfx}.csv"
    if not p.exists():
        return None, None
    t = read_table(p).set_index("Config")
    if label not in t.index:
        return None, None
    return float(t.loc[label, "MaxDD%"]), float(t.loc[label, "Sharpe"])


def rows(root=None):
    out = []
    for u in gated():
        M = Path(u.metrics_dir) if root is None else Path(root) / f"results_{u.tag}"
        for prof in PROFILES:
            ps = "" if prof == "research" else "_tradeable"
            for arm in arm_reg.ARMS.values():
                tag = u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}"
                t = read_table(M / f"BH_LOTS_{tag}{ps}_tax.csv").set_index("line")
                c = t["cagr_full"]
                a = arm.name
                dd_off, sh_off = _cmp(M, ps, arm.label)
                dd_on, sh_on = _cmp(M, f"{ps}_tax", arm.label)
                out.append({
                    "universe": u.tag, "arm": a, "profile": prof,
                    "cagr_off": c[f"{a} before tax"], "cagr_on": c[f"{a} after tax"],
                    "cagr_last_day": c[f"{a} sold on the last day"],
                    "bh_reference": c["bh published"],
                    "bh_investable": c["bh_lots after tax"],
                    "bh_investable_last_day": c["bh_lots sold on the last day"],
                    "gap_on": c["gap_after_tax"],
                    "gap_last_day": c["gap_sold_on_the_last_day"],
                    "maxdd_off": dd_off, "sharpe_off": sh_off,
                    "maxdd_on": dd_on, "sharpe_on": sh_on,
                })
    return pd.DataFrame(out)


def cell_table_main(argv):
    if not argv or argv[0].startswith("--"):
        print(CELL_TABLE_DOC)
        return 2
    root = argv[argv.index("--root") + 1] if "--root" in argv else None
    d = rows(root)
    d.to_csv(argv[0], index=False)
    print(f"wrote {argv[0]}: {len(d)} rows")
    return 0


# ---------------------------------------------------------------------------
# cell-compare (was results/cell_compare.py)
# ---------------------------------------------------------------------------
CELL_COMPARE_DOC = """
cell-compare -- old against new for every cell, from two cell-table CSVs.

    ./venv/bin/python run.py --report cell_reports cell-compare OLD.csv NEW.csv OUT.csv

One row per (universe, arm, profile): each CAGR and gap column from both files and
their difference, plus sign_change_on and sign_change_last_day, True where the gap
against the investable taxed buy & hold has a different sign old and new.
"""

KEY = ["universe", "arm", "profile"]

COLS = ["cagr_off", "cagr_on", "cagr_last_day", "bh_reference", "bh_investable",
        "bh_investable_last_day", "gap_on", "gap_last_day"]


def compare(old, new):
    o = old.set_index(KEY)[COLS]
    n = new.set_index(KEY)[COLS]
    if set(o.index) != set(n.index):
        raise SystemExit("the two tables do not hold the same cells")
    n = n.loc[o.index]
    out = pd.DataFrame(index=o.index)
    for c in COLS:
        out[f"{c}_old"] = o[c]
        out[f"{c}_new"] = n[c]
        out[f"{c}_diff"] = (n[c] - o[c]).round(4)
    for g in ("gap_on", "gap_last_day"):
        out[f"sign_change_{g[4:]}"] = (o[g] > 0) != (n[g] > 0)
    return out.reset_index()


def cell_compare_main(argv):
    if len(argv) != 3:
        print(CELL_COMPARE_DOC)
        return 2
    d = compare(read_table(argv[0]), read_table(argv[1]))
    d.to_csv(argv[2], index=False)
    print(f"wrote {argv[2]}: {len(d)} cells, gap sign changes: "
          f"headline {int(d.sign_change_on.sum())}, last day {int(d.sign_change_last_day.sum())}")
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
COMMANDS = {
    "tax-on-all-arms": lambda argv: tax_on_all_arms_main(),
    "tradeable-tax-grid": lambda argv: tradeable_tax_grid_main(),
    "tax-fix-old-new": tax_fix_old_new_main,
    "cell-table": cell_table_main,
    "cell-compare": cell_compare_main,
}


def cell_reports(argv):
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]](argv[1:])


# ======================================================================================
# impact_sweep. From results/impact_sweep.py (moved 2026-11-27).
# ======================================================================================
# impact_sweep -- what the participation cap costs, and what market impact costs,
# measured separately.
#
# WHY SEPARATELY. Lowering the cap and charging size-sensitive slippage both reduce
# the return, and a single combined figure cannot say which did it. The grid below
# holds one of the two fixed in every comparison:
#
#     research            cap None,  k None      the published arithmetic
#     cap 1.00, k None    cap only               the loosest cap
#     cap 0.10, k None    cap only               the cap's own contribution
#     cap 1.00, k = x     slippage plus the      isolates impact only where
#                         loosest cap            cap 1.00 binds on nothing
#     cap 0.10, k = x     both                   the combined figure
#
# `cap 1.00` is NOT a no-op everywhere. On v2 of nifty100 and midcap150 it binds on
# no fill. Measured 2026-10-10, on that day's data delivery, over every core arm of the
# nine universes (microcap250 without PRIVISCL), it binds in 13 of 36 CSVs (cap 1.00,
# k none row; BUY + SELL binds, CAGR change).
#
#     nifty100 v1     1 + 0   +0.22        smallcap250 v1   4 + 1   -0.71
#     midcap50 v1     1 + 0   -0.05        smallcap250 v3   2 + 0   -3.08
#     midcap50 v3     1 + 0   -0.03        nifty500 v1      3 + 0   -0.18
#     midcap100 v1    1 + 0   -0.02        nifty500 v3      1 + 0   +0.28
#     midcap100 v3    1 + 0   -0.05        microcap250 v1  12 + 9   -0.67
#     microcap250 v2  3 + 2   +0.15        microcap250 v3  16 + 11  -4.79
#     microcap250 v4  3 + 1   +0.04
#
# Read each CSV's cap_BUY and cap_SELL columns before treating its cap 1.00 rows as
# impact only.
#
# THE BIND COUNTS ARE PART OF THE RESULT, NOT DIAGNOSTICS. A CAGR that moved while
# the cap bound 200 times means something different from one that moved while it
# bound twice. Every cell carries its BUY and SELL cap-bind counts and its
# impact-exemption count.
#
# NO k IS SELECTED HERE. The sweep shows how sensitive the answer is to k. Picking
# one is a separate decision that needs a reason this file cannot supply.
#
# EVERY CORE ARM ON EVERY UNIVERSE. The arms come from portfolio.ARMS (v1 to v4)
# and the universes from settings.REGISTRY; nothing here names either.
# Each pair writes diagnostics/impact_sweep_<universe>_<arm>.csv. The no-cap, k-none
# row is the research profile, tax off, cadence 20 (portfolio.REBAL), which is
# what the published v34_comparison.csv rows are, and is compared against them by
# the caller.

K_VALUES = (0.001, 0.002, 0.003, 0.005)
CAPS = (1.00, 0.10)

# THE SETTINGS, NOT A COPY OF THEM (2026-10-15). Each cell selects the profile,
# --cap and --impact exactly as run.py does and takes its keywords from
# costs.cap_kwargs, so the volume series, the cap and k reach backtest_exposure
# by the path every run takes. Until then this file loaded its own volume series,
# on the score panel's dates rather than the engine's calendar, and passed cap and
# k by hand.


def panel(tag):
    u = REGISTRY[tag]
    # The row rule the engines load for this universe (reports.py).
    market_data.set_tradeability(u)
    src = model.require_cache(u.score_cache, what=f"{tag} score panel")
    p = read_table(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= settings.BT_START_DATE) & (px.index <= settings.BT_END_DATE)]
    pc = market_data.precompute(px)
    mom20 = px / px.shift(20) - 1
    # the tradeable profile's volume series, loaded once and reused by every cell
    _select(1.00, None)
    v20 = costs.cap_kwargs(u)["vol20"]
    _select(None, None)
    return u, px, op, sc, bd, pc, mom20, v20


def _select(cap, k):
    """Select what run.py would for this cell: research when cap is None, else
    --profile tradeable --cap cap --impact k (k None is --impact 0)."""
    settings.profile_axis.set_selection(None if cap is None else "tradeable")
    pcap_axis.set_selection(cap)
    impact_axis.set_selection(k)


def cell(u, px, op, sc, bd, pc, mom20, v20, arm, cap, k):
    aud = {x: [] for x in ("holdings", "summary", "trades", "ranking",
                           "decisions", "skipped")}
    iout = {}
    _select(cap, k)
    try:
        kw = costs.cap_kwargs(u, vol20=v20)
    finally:
        _select(None, None)
    eq, tc, ntr, _ = backtest_exposure(
        px, op, sc, bd, pc, mom20, drawdown_stop=None, **arm.kwargs,
        audit=aud, impact_out=iout, **kw)
    m = engine_core.metrics(eq, "cell", tc, ntr)
    sk = pd.DataFrame(aud["skipped"])
    caprows = sk[sk["reason"] == "participation cap"] if len(sk) else sk
    by_side = caprows.groupby("side").size().to_dict() if len(caprows) else {}
    return {
        "cap": "none" if cap is None else f"{cap:.2f}",
        "k": "none" if k is None else f"{k:.3f}",
        "CAGR%": m["CAGR%"], "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"],
        "trades": ntr, "final": round(float(eq.iloc[-1]), 2),
        "cap_BUY": by_side.get("BUY", 0), "cap_SELL": by_side.get("SELL", 0),
        "k_priced": iout.get("priced", 0), "k_exempt": iout.get("exempt", 0),
    }


def impact_sweep():
    out = {}
    for tag in REGISTRY:
        with contextlib.redirect_stdout(io.StringIO()):
            P = panel(tag)
        for arm in ARMS.values():
            rows = [cell(*P, arm, None, None)]
            for cap in CAPS:
                rows.append(cell(*P, arm, cap, None))
            for cap in CAPS:
                for k in K_VALUES:
                    rows.append(cell(*P, arm, cap, k))
            df = pd.DataFrame(rows)
            base = df.iloc[0]
            df["dCAGR"] = (df["CAGR%"] - base["CAGR%"]).round(2)
            out[(tag, arm.name)] = df
            dest = ROOT / "diagnostics" / f"impact_sweep_{tag}_{arm.name}.csv"
            # naming: axis-free -- every core arm and universe is written, each under
            # its registry names; run.py's arm, cadence, profile and tax selections
            # do not reach this script. The cap and k axes are columns, because the
            # sweep is over them.
            df.to_csv(dest, index=False)
            print("=" * 100)
            print(f" IMPACT SWEEP -- {tag}   arm {arm.name} ({arm.mode}/{arm.sizing})   "
                  f"window {settings.BT_START_DATE.date()} -> {settings.BT_END_DATE.date()}")
            print("=" * 100)
            print(df.to_string(index=False))
            print(f"  saved -> {dest.relative_to(ROOT)}")
            print()
    return out


def _cli_impact_sweep():
    """`python reports.py impact_sweep [ARGS]`: what running results/impact_sweep.py did."""
    impact_sweep()
