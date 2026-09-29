"""cost_report.py -- charges, slippage and tax for one run, reconciled to the paisa.

Called by results/audit_step.py for every (universe, arm) it audits, under every
cadence, profile and tax setting, and by cost_reconcile_check.py for the gate. It
reads the cost trail backtest_exposure records when its audit dict carries a
"costs" key, and changes nothing the engine computes.

WHAT IT WRITES, beside the daily_* files and named by the same artefact tag:
    COSTS_<tag>.csv           one row per fill: reference price, fill price,
                              quantity, slippage in rupees, each charge, total
    COST_LOTS_<tag>.csv       one row per lot a sell closes: buy date, days held,
                              short or long, old or new regime, the gain as the tax
                              rules compute it (price difference only)
    COST_TAX_YEARS_<tag>.csv  one row per financial year of the window: the four
                              buckets, the netting, the exemption available and
                              used, the tax at each rate, the total and the day it
                              left cash. Tax columns are zero when tax is off.
    COST_SUMMARY_<tag>.txt    the summary block run.py prints at the end of run.log

THE SLIPPAGE MODEL. Both profiles use slippage.py's flat rate: a BUY fills at the
reference price times (1 + SLIPPAGE), a SELL at (1 - SLIPPAGE), SLIPPAGE = 0.0015.
The reference price is the execution day's open from the score panel (the adjusted
price basis), or for the optional last-day sale the close where the open is
missing. The size-sensitive term (slippage.impact) exists but no production caller
passes impact_k, so it is zero in every run. The tradeable profile adds the
participation cap, which changes quantities, not the rate.

THE CHARGES are results/qbeast_in_charges.compute_leg_charges for Zerodha delivery
equity on NSE, called exactly as test_exposure.calc_tc calls it: on the fill price
rounded to two decimals, per fill. The reconciliation requires the itemised total to
equal the charge the engine deducted.

RECONCILIATION (reconcile below). A run that fails any check raises
CostReconciliationError naming the check, the first day and the gap:
    cash      every day: opening cash + interest + sale proceeds - purchase cost -
              charges - tax = closing cash, to the paisa, and each day opens at the
              previous day's close
    slippage  every fill: the model applied to the reference price and quantity
              gives (fill - reference) x quantity, to the paisa; the itemised
              charges equal the charge deducted; the fill matches the trades row
    tax       every financial year: the rules applied to the per-lot gains give the
              tax the run deducted, on the day it deducted it
    totals    per-fill and per-year sums equal the run's totals and the summary
"""
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tax_util as T                                      # noqa: E402
from slippage import SLIPPAGE                             # noqa: E402
from qbeast_in_charges import (compute_leg_charges, Broker, Segment,  # noqa: E402
                               Product, Side as QSide, Exchange)

PAISA = 0.005
CHARGES = (("brokerage", "brokerage"), ("stt_ctt", "STT"), ("exchange_txn", "exchange transaction"),
           ("sebi", "SEBI turnover fee"), ("stamp_duty", "stamp duty"), ("ipft", "IPFT"),
           ("dp", "DP charge"), ("gst", "GST"))

# The tax reference document's own list of what the tax model does not do
# (data/reference/TAX_AND_CHARGES.docx, section 5), one line each.
TAX_LEAVES_OUT = (
    "No cess or surcharge: the 4% health and education cess and any surcharge are not added, so tax is understated by at least 4%.",
    "No loss carry-forward: a net-loss year pays nil and the loss is discarded, where the law carries it forward for 8 years.",
    "No s.112A grandfathering: no cost step-up to the 31-Jan-2018 value; the window starts in 2019, so nothing is affected.",
    "No advance tax: each year is paid as one lump sum on its assessment day, not in quarterly instalments.",
    "The LTCG exemption is really per person across all holdings; here the portfolio gets the whole of it.",
)


class CostReconciliationError(RuntimeError):
    """A cost figure does not reconcile. The message names the check, day and gap."""


def charge_breakdown(fill_price, qty, side, numpy_round=True):
    """{charge: rupees} for one fill, as test_exposure.calc_tc computes the total."""
    # NUMPY SCALARS, AS IN THE ENGINE: its prices come out of a pandas row as
    # numpy float64, and round() on one can land a half-paisa the other way from
    # round() on a Python float (1607.585 -> 1607.58 against 1607.59). Rounding the
    # way the engine does is what makes the charge and the gain match it.
    # bh_held.held_lots prices in Python floats, so the buy & hold passes False.
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
    f = pd.DataFrame(costs["fills"], columns=["date", "side", "symbol", "qty", "reference_price",
                                              "fill_price", "charges", "kind"])
    if f.empty:
        for k, _ in CHARGES:
            f[k] = []
        f["slippage_rs"] = []
        f["charges_total"] = []
        return f
    sign = np.where(f["side"] == "BUY", 1.0, -1.0)
    f["slippage_rs"] = (f["fill_price"] - f["reference_price"]) * f["qty"] * sign
    br = [charge_breakdown(p, q, s) for p, q, s in zip(f["fill_price"], f["qty"], f["side"])]
    for k, _ in CHARGES:
        f[k] = [b[k] for b in br]
    f["charges_total"] = [b["total"] for b in br]
    return f


def replay_ledger(fills, dates):
    """Replay the tax rules on the recorded fills, in the engine's order.

    -> (lots frame, {date: tax due before fills}, {date: tax due after fills},
        {fy: date assessed}). tax_util.Ledger is the engine's own class, fed the
    same prices (the fill rounded to two decimals) in the same order."""
    led = T.Ledger(dates)
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
    buckets = T.realized_buckets(lots)
    rows = []
    for fy in sorted({T.financial_year(d) for d in dates}):
        b = buckets.get(fy, dict.fromkeys(T.BUCKETS, 0.0))
        t = T.tax_for_fy(fy, b)
        ltcg_pos = max(t["ltcg_net"], 0.0)
        r = {"fy": T.fy_label(fy), "tax": "on" if tax_on else "off",
             **{k: b[k] for k in T.BUCKETS},
             "stcg_net": t["stcg_net"], "stcg_taxable": t["stcg_taxable"],
             "stcg_old_taxed": t["stcg_old_taxed"], "stcg_old_rate": T.STCG_RATE["old"],
             "stcg_old_tax": t["stcg_old_taxed"] * T.STCG_RATE["old"],
             "stcg_new_taxed": t["stcg_new_taxed"], "stcg_new_rate": T.STCG_RATE["new"],
             "stcg_new_tax": t["stcg_new_taxed"] * T.STCG_RATE["new"],
             "stcg_tax": t["stcg_tax"],
             "ltcg_net": t["ltcg_net"], "exemption_available": t["exemption"],
             "exemption_used": min(ltcg_pos, t["exemption"]),
             "ltcg_taxable": t["ltcg_taxable"],
             "ltcg_old_taxed": t["ltcg_old_taxed"], "ltcg_old_rate": T.LTCG_RATE["old"],
             "ltcg_old_tax": t["ltcg_old_taxed"] * T.LTCG_RATE["old"],
             "ltcg_new_taxed": t["ltcg_new_taxed"], "ltcg_new_rate": T.LTCG_RATE["new"],
             "ltcg_new_tax": t["ltcg_new_taxed"] * T.LTCG_RATE["new"],
             "ltcg_tax": t["ltcg_tax"], "total_tax": t["total_tax"],
             "deducted_on": when.get(fy), "net_loss_year": (t["stcg_net"] + t["ltcg_net"]) < 0}
        if not tax_on:
            for k in ("stcg_old_tax", "stcg_new_tax", "stcg_tax", "exemption_used",
                      "ltcg_old_tax", "ltcg_new_tax", "ltcg_tax", "total_tax"):
                r[k] = 0.0
            r["deducted_on"] = None
        rows.append(r)
    return pd.DataFrame(rows)


def reconcile(costs, trades, dates, start_capital, engine_tc, engine_tax, tax_on, engine_lots=None):
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
        model = np.where(fills["side"] == "BUY", 1 + SLIPPAGE, 1 - SLIPPAGE) * fills["reference_price"]
        gap = (fills["fill_price"] - model) * fills["qty"]
        bad = np.flatnonzero(np.abs(gap) >= PAISA)
        if len(bad):
            j = bad[0]
            _fail("slippage", fills["date"].iloc[j], float(gap.iloc[j]),
                  f"{fills['side'].iloc[j]} {fills['symbol'].iloc[j]}: the flat model does not "
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
    """Charges, slippage and tax of the investable buy & hold (bh_held.held_lots),
    held to the end and sold on the last day, recomputed fill by fill and reconciled
    against held_lots to the paisa. Raises CostReconciliationError on a gap."""
    import bh_held
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
        sp = ref_n * (1 - SLIPPAGE)
        s_ = charge_breakdown(sp, q, "SELL", numpy_round=False)
        for k, _ in CHARGES:
            sell[k] += s_[k]
        sell_slip += (ref_n - sp) * q
        proceeds += q * sp
        gain += q * (round(sp, 2) - round(pr, 2))
    bucket = dict.fromkeys(T.BUCKETS, 0.0)
    bucket[("long_" if (dN - d0).days >= T.LTCG_HOLD_DAYS else "short_") + T.regime_of(dN)] = gain
    tx = T.tax_for_fy(T.financial_year(dN), bucket)
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
            "exemption_used": min(max(tx["ltcg_net"], 0.0), tx["exemption"]) if tax_on else 0.0,
            "sold_final": sold_final if tax_on else sold_final + tx["total_tax"],
            "tax_if_on": tx["total_tax"]}


def summary_block(label, profile, tax_on, rebal, start_capital, equity, fills, years, days, bh,
                  cap_cuts=0):
    """The text block, as a list of lines."""
    final = float(equity.iloc[-1])
    tot = {k: float(fills[k].sum()) if len(fills) else 0.0 for k, _ in CHARGES}
    charges = sum(tot.values())
    slip = float(fills["slippage_rs"].sum()) if len(fills) else 0.0
    stcg = float(years["stcg_tax"].sum())
    ltcg = float(years["ltcg_tax"].sum())
    tax = stcg + ltcg
    exu = float(years["exemption_used"].sum())
    gross = final - start_capital + charges + slip + tax
    L = ["=" * 90, f" COSTS -- {label}   cadence {rebal}, profile {profile}, tax {'on' if tax_on else 'off'}",
         "=" * 90,
         f"  starting capital Rs {start_capital:,.2f}   final equity Rs {final:,.2f}",
         f"  gross profit Rs {gross:,.2f} = final equity - starting capital + charges + slippage + tax",
         "",
         f"  {'':<34}{'Rs':>16}{'of capital':>12}{'of gross':>11}"]

    def row(name, x, ind=2):
        L.append(f"  {' ' * ind}{name:<{34 - ind}}{x:>16,.2f}{_pct(x, start_capital):>12}{_pct(x, gross):>11}")
    row("charges, total", charges, 0)
    for k, nm in CHARGES:
        row(nm, tot[k])
    row("slippage", slip, 0)
    row("tax, total", tax, 0)
    row("short-term", stcg)
    row("long-term", ltcg)
    row("LTCG exemption used (not a cost)", exu)
    row("all costs", charges + slip + tax, 0)
    # per financial year, on a cash basis: a cost belongs to the year it left cash,
    # so each year's gross profit is its change in equity plus what it paid
    L += ["", "  per financial year, as paid (Rs; last column % of the year's gross profit)",
          f"  {'FY':<11}{'gross profit':>15}{'charges':>13}{'slippage':>12}{'short tax':>12}{'long tax':>11}"
          f"{'exempt used':>13}{'costs % gross':>15}"]
    paid = years.dropna(subset=["deducted_on"]).copy()
    paid["paid_fy"] = paid["deducted_on"].map(T.financial_year)
    fyof = pd.Series([T.financial_year(d) for d in equity.index], index=equity.index)
    ffy = fills["date"].map(T.financial_year) if len(fills) else pd.Series(dtype=int)
    prev, sums = start_capital, np.zeros(5)
    for fy in sorted(fyof.unique()):
        end = float(equity.loc[fyof[fyof == fy].index[-1]])
        fl = fills[ffy == fy] if len(fills) else fills
        c = float(fl["charges"].sum()) if len(fl) else 0.0
        s_ = float(fl["slippage_rs"].sum()) if len(fl) else 0.0
        y = paid[paid["paid_fy"] == fy]
        st, lt, ex = (float(y[k].sum()) for k in ("stcg_tax", "ltcg_tax", "exemption_used"))
        g = end - prev + c + s_ + st + lt
        settles = ", ".join(y["fy"]) if len(y) else ""
        L.append(f"  {T.fy_label(fy):<11}{g:>15,.2f}{c:>13,.2f}{s_:>12,.2f}{st:>12,.2f}{lt:>11,.2f}"
                 f"{ex:>13,.2f}{_pct(c + s_ + st + lt, g):>15}"
                 + (f"   tax settles {settles}" if settles else ""))
        sums += (g, c, s_, st, lt)
        prev = end
    for got, want, what in ((sums[0], gross, "gross profit"), (sums[1], charges, "charges"),
                            (sums[2], slip, "slippage"), (sums[3] + sums[4], tax, "tax")):
        if abs(got - want) >= PAISA:
            _fail("totals", None, got - want, f"per-year {what} does not sum to the summary total")
    L.append("  Tax is shown in the year it left cash; COST_TAX_YEARS gives the year each amount was "
             "levied on.")
    # buy & hold, held to the end and sold on the last day
    if bh is not None:
        bc, bs = sum(bh["buy_charges"].values()), bh["buy_slippage"]
        sc_, ss = sum(bh["sell_charges"].values()), bh["sell_slippage"]
        held_costs = bc + bs
        sold_costs = bc + bs + sc_ + ss + bh["tax"]
        g_held = bh["held_final"] - start_capital + held_costs
        g_sold = bh["sold_final"] - start_capital + sold_costs
        L += ["", f"  investable buy & hold ({bh['names']} names bought at the first open)",
              f"  {'':<34}{'held to the end':>18}{'sold on the last day':>22}",
              f"  {'final equity':<34}{bh['held_final']:>18,.2f}{bh['sold_final']:>22,.2f}",
              f"  {'gross profit':<34}{g_held:>18,.2f}{g_sold:>22,.2f}"]
        for nm, x, y in (("charges", bc, bc + sc_), ("slippage", bs, bs + ss),
                         ("tax, total", 0.0, bh["tax"]), ("  short-term", 0.0, bh["stcg_tax"]),
                         ("  long-term", 0.0, bh["ltcg_tax"]),
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
        L += ["", f"  all costs: arm Rs {charges + slip + tax:,.2f}; buy & hold held Rs {held_costs:,.2f}, "
                  f"sold on the last day Rs {sold_costs:,.2f}"]
    # zeros, stated
    L += ["", "  zero components and why:"]
    if tot["brokerage"] == 0:
        L.append("    brokerage is zero: Zerodha charges no brokerage on delivery equity.")
    if tot["ipft"] == 0:
        L.append("    IPFT is zero: the charge engine leaves the NSE IPFT levy out (about Rs 0.01 a crore).")
    L.append(f"    slippage is the flat {SLIPPAGE:.2%} of the reference price in both profiles; the size-"
             f"sensitive term is not used, so no fill pays more than the flat rate.")
    if profile == "research":
        L.append("    research profile: no participation cap, so no order was cut for volume.")
    else:
        L.append(f"    {profile} profile: the participation cap cut {cap_cuts:,} order(s) to a share of "
                 f"prior-20-session median volume; it changes quantities, not the slippage rate.")
    if not tax_on:
        L.append("    TAX IS OFF for this run: every tax figure is zero because of the tax setting, not the gains.")
    L += ["", "  what the tax model leaves out (data/reference/TAX_AND_CHARGES.docx, section 5):"]
    L += [f"    - {x}" for x in TAX_LEAVES_OUT]
    L += ["", f"  reconciled to the paisa: cash on {len(days):,} days, slippage and charges on "
              f"{len(fills):,} fills, tax on {len(years)} financial years, the totals above, and "
              f"the buy & hold held and sold.",
          "=" * 90]
    return L


def write(u, arm, tag, audit, equity, engine_tc, px, op, bd, start_capital, profile, tax_on, rebal):
    """Reconcile, write the four files and print the summary block. Raises on a failure."""
    M = Path(u.metrics_dir)
    engine_tax = float(audit["tax"]["cum_tax"]) if (tax_on and "tax" in audit) else 0.0
    engine_lots = audit["tax"]["lots"] if (tax_on and "tax" in audit) else None
    fills, lots, years, days = reconcile(audit["costs"], audit["trades"], list(bd), start_capital,
                                         engine_tc, engine_tax, tax_on, engine_lots)
    cols = ["date", "side", "kind", "symbol", "qty", "reference_price", "fill_price", "slippage_rs"] + \
        [k for k, _ in CHARGES] + ["charges_total"]
    out = fills[cols].rename(columns={"stt_ctt": "stt"})
    lo = lots.rename(columns={"sell_date": "date", "held_days": "days_held"})
    lo["term"] = np.where(lo["is_long"], "long", "short")
    lo = lo[["date", "symbol", "qty", "buy_date", "buy_price", "sell_price", "days_held", "term",
             "regime", "fy", "gain"]]
    lo["fy"] = lo["fy"].map(T.fy_label)
    bh = bh_costs(px, op, bd, start_capital, tax_on)
    lines = summary_block(f"{u.tag} {getattr(arm, 'name', arm)}", profile, tax_on, rebal,
                          start_capital, equity, fills, years, days, bh,
                          cap_cuts=sum(1 for r in audit["skipped"] if r.get("reason") == "participation cap"))
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is audit_step.artefact_tag(u, arm)
    out.to_csv(M / f"COSTS_{tag}.csv", index=False)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is audit_step.artefact_tag(u, arm)
    lo.to_csv(M / f"COST_LOTS_{tag}.csv", index=False)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is audit_step.artefact_tag(u, arm)
    years.to_csv(M / f"COST_TAX_YEARS_{tag}.csv", index=False)
    # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is audit_step.artefact_tag(u, arm)
    (M / f"COST_SUMMARY_{tag}.txt").write_text("\n".join(lines) + "\n")
    print(f"\n  costs reconciled and saved -> COSTS_{tag}.csv / COST_LOTS_{tag}.csv / "
          f"COST_TAX_YEARS_{tag}.csv / COST_SUMMARY_{tag}.txt")
    return lines
