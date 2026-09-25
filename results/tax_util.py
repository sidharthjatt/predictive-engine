"""
tax_util.py -- Indian capital-gains tax on a realised trade log. THE RULES ONLY.
===============================================================================

    axis: tax.py            engine hook: results/test_exposure.py
    spec: the reference document's section 3, implemented verbatim

UNPARKED 2026-09-17, AND WHY
    Parked 2026-08-13 because the comparison it produced was asymmetric: tax was
    charged to the strategy lines and not to the buy&hold or index lines, which
    have entirely different tax treatment. A 20-day-churn strategy realises
    everything at the short-term rate; an equal-weight buy&hold realises once
    after seven years at the long-term rate. Charging one and not the other
    overstates the strategy's disadvantage by the whole gap between those
    regimes.

    THAT IS RESOLVED BY APPLYING ONE RULE TO BOTH LINES, NOT BY WITHHOLDING IT
    FROM ONE. Strategy and buy&hold are taxed identically here: same lot
    matching, same holding-period test, same rates, same regime split at
    2024-07-23, same annual exemption per financial year.

    THE TWO LINES THEN PAY VERY DIFFERENT AMOUNTS, AND THAT DIFFERENCE IS THE
    RESULT -- NOT A DEFECT IN THE COMPARISON. Buy&hold realises once, at the end
    of the window, so almost all of its gain is long-term and much of what
    remains is covered by one annual exemption. The strategy realises 505 lots
    over 7.4 years, none held longer than 326 days, so every rupee it makes is
    short-term and is taxed in the year it is earned. The gap between the two
    bills IS THE TAX COST OF TURNOVER, measured rather than asserted.

    The earlier note was right that charging one line and not the other is
    unfair. It was wrong to conclude the answer was to charge neither. The
    answer is to charge both and report the difference, which is the number a
    reader actually wants.

    TWO THINGS THIS DOES NOT RESOLVE, RECORDED RATHER THAN HIDDEN.
      1. The benchmark's single terminal realisation lands in the two-month
         FY2026-27 stub and consumes one full annual allowance for 7.4 years of
         accrued gain. See THE STUB YEARS below.
      2. The published `bh` line is a daily-rebalanced equal-weight INDEX, not a
         held portfolio -- results/engine_v2_final.py:207 builds it from
         px.pct_change().mean(axis=1). It has no lots to tax. Giving it lots is
         a DIFFERENT CONSTRUCTION with a different CAGR, reported beside the
         original and never substituted for it.

WHY THIS IS A REWRITE AND NOT AN EXTENSION
    The parked file's single organising assumption -- one rate, applied to a
    running same-financial-year total -- was load-bearing in both of its public
    functions, and every one of the four things below had to displace it. What
    survives, deliberately and near-verbatim, is the shape that was right:
    log-driven rather than reconstructed, FIFO per symbol, None on a missing
    file, the Indian financial-year expression, and the no-refund clamp.

    Four defects the parked version carried, all fixed here:
      1. STCG_RATE = 0.20 flat. No long-term rate, no exemption, and NO REGIME
         SPLIT -- every pre-2024-07-23 gain was taxed at the post-change rate.
      2. `gain - float(t["tc"])` deducted the SELL leg's charges only; the buy
         leg's were silently dropped. Section 3(C) deducts NEITHER (see below),
         so the subtraction is gone entirely rather than corrected.
      3. No holding-period computation at all. Short versus long was never
         asked; it rested on a docstring claim that is wrongly reasoned (below).
      4. after_tax() applied tax as a return-series drag while its docstring
         claimed a cash deduction. Section 3(9) requires the cash deduction, so
         the claim is now what the code does -- and the code lives in the
         engine, not here. This module computes WHAT is owed and WHEN; it never
         touches an equity curve.

THE DOCSTRING CLAIM THAT WAS WRONG, AND WHY THE CONCLUSION SURVIVED ANYWAY
    The parked file said: "Every rebalance is 20 days. No position can reach the
    12-month threshold... That is a structural consequence of a 20-day
    rebalance, not a modelling assumption."

    IT IS NOT STRUCTURAL. Positions survive rebalances through the BUFFER=16
    rank band, so the 20-day cadence caps holding period at nothing in
    particular. MEASURED over the shipped trade logs (FIFO, per symbol):

        daily_trades_mid_tradeable.csv      505 lots   max hold 326 days
        daily_trades_n100.csv               478 lots   max hold 322 days
        daily_trades_mid_v1_tradeable.csv   426 lots   max hold 326 days

    THOSE THREE LOGS ARE HISTORICAL -- retired universes, and on them zero lots
    exceeded 365 days. "100% short-term" was true there. IT IS NOT TRUE NOW: the
    2026-09-18 four-universe runs put four lots past the threshold, on nifty100
    and nifty50, and max_holding_days()' own docstring lists them. What was
    empirical stayed empirical and then changed, which is what empirical means.

    So holding period is COMPUTED PER LOT and branched on, never hardcoded, and
    max_holding_days() exists so a check can fail loudly when a universe crosses
    365 rather than the long-term branch quietly beginning to fire.

TWO KEYS, TWO DIFFERENT CONDITIONS, AND FY2024-25 EXERCISES BOTH AT ONCE
    THE RATE is keyed on the SALE DATE (section 3(8)): old before 2024-07-23,
    new on or after it.
    THE EXEMPTION is keyed on the FINANCIAL YEAR (section 3(5)/(6)): Rs 1,00,000
    for FY < 2024, Rs 1,25,000 for FY >= 2024.

    These are NOT the same test and must not be collapsed into one. A lot sold
    on 2024-05-30 is inside FY2024-25 -- so it draws on the Rs 1,25,000
    exemption -- while its sale date is before the cutoff, so it is taxed at the
    OLD rate. The document's own worked table shows Rs 1,25,000 for FY2024-25,
    which is only consistent with the two being independent.

THE STUB YEARS, DECIDED IN THE OPEN
    The window 2019-01-01 .. 2026-05-29 covers nine financial years, seven full
    and two stubs: FY2018-19 is Q4 only and FY2026-27 is two months.

    EVERY FINANCIAL YEAR GETS THE FULL ANNUAL EXEMPTION, INCLUDING BOTH STUBS.
    The document is SILENT on stub years. Pro-rating is therefore not a rule
    taken from it -- it would be a modelling choice wearing a tax rule's
    clothes, and it is not invented here. An annual allowance is not earned by
    elapsed time in any statute.

    THE CONSEQUENCE, STATED RATHER THAN BURIED: it is inert on the strategy,
    whose long-term bucket is empty in every year, and it is entirely live on
    the benchmark, whose single terminal realisation lands in the two-month
    FY2026-27 stub and takes one full year's allowance against 7.4 years of
    accrued gain. Pro-rating would not fix that; only a staged liquidation
    would, and that is a different benchmark.

    THE LAST STUB IS SETTLED AT THE BACKTEST END, SINCE 2026-09-25. Section 3(9)
    assesses a financial year on the first trading day at or after 31 March. For
    FY2026-27 that date is in 2027, outside the backtest window, so until
    2026-09-25 its liability was computed and never deducted. By the owner's
    decision of 2026-09-25 it is now deducted from cash on the window's last
    session, after that day's fills, on the gains realised to that date, with the
    document's netting and exemption rules unchanged (Ledger.due_on,
    liability_schedule). The document says nothing about a window that ends
    mid-year; this settlement date is that decision, not a rule quoted from it.
    The FY2026-27 exemption is the full annual Rs 1,25,000, as for every other
    financial year: the document keys the exemption on the financial year and
    does not pro-rate, so neither does this.

TAX PARTIALLY DAMPS ITSELF, AND THE TWO NUMBERS MUST NOT BE SWAPPED
    The deduction shrinks cash, cash sizes every order, smaller positions realise
    smaller gains, and a smaller gain is a smaller bill. So a taxed run pays LESS
    than its own untaxed trade log implies -- tax partially damps itself.

    MEASURED ON midcap150, full window, v2 breadth arm:

        Rs 833,105   implied by the UNTAXED run's trade log
        Rs 798,365   actually charged by the TAXED run        (-4.2%)

    THE SECOND NUMBER IS THE ONLY ONE THAT MAY APPEAR IN FY_TAX_STATEMENT. It is
    what the portfolio paid, it reconciles with FY_EQUITY to the paisa, and the
    first describes a run that did not happen. The gap is an observation recorded
    here once, with both figures and which run produced each; it is not a
    statement column and no artefact carries it as a figure.

WHAT IS NOT MODELLED -- section 3(D), carried over verbatim in substance
    Carry-forward of a net loss: a net-loss year pays nil and the loss is
    DISCARDED, not carried forward. The code floors at zero and resets each
    financial year. Also absent: surcharge and cess (understates tax by >= 4%),
    s.112A grandfathering for pre-31-Jan-2018 acquisitions, and quarterly
    advance tax. The portfolio is treated as a standalone taxpayer, though the
    exemption is really per person across all holdings.

    AND CHARGES ARE NOT DEDUCTED FROM THE GAIN AT ALL -- section 3(C),
    treatment (ii): gain is the price difference only. This OVERSTATES the gain
    and therefore the tax, because real brokerage and exchange charges would
    reduce a taxable gain. It is CONSERVATIVE in the direction that matters: it
    cannot make the strategy look better than it is. Our charge engine persists
    a per-fill `tc` and could support the statutory split, in which STT is not
    deductible while brokerage and exchange charges are; that is deliberately
    not done here, because the document's rule is the rule being implemented.
"""
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# SECTION 3, ITEMS 1-8. Every constant below is the document's, not a default.
# ---------------------------------------------------------------------------
CGT_REGIME_CHANGE = pd.Timestamp("2024-07-23")   # item 8, the transfer-date cut
LTCG_HOLD_DAYS = 365                             # item 7, is_long = held >= 365

# item 1-4, keyed on the SALE DATE via regime_of()
STCG_RATE = {"old": 0.15,  "new": 0.20}
LTCG_RATE = {"old": 0.10,  "new": 0.125}

# item 5-6, keyed on the FINANCIAL YEAR -- a DIFFERENT condition from the rates.
LTCG_EXEMPTION_OLD = 100_000.0     # FY < 2024
LTCG_EXEMPTION_NEW = 125_000.0     # FY >= 2024
LTCG_EXEMPTION_FY_CUT = 2024

BUCKETS = ("short_old", "short_new", "long_old", "long_new")


def financial_year(ts):
    """The Indian financial year containing `ts`, as its START year.

    1 April to 31 March, so 2024-05-30 and 2025-02-14 are both FY 2024.
    The expression is the parked file's, which was correct.
    """
    ts = pd.Timestamp(ts)
    return ts.year - (1 if ts.month < 4 else 0)


def fy_label(fy):
    """FY 2024 -> 'FY2024-25'. For reports; never used as a key."""
    return f"FY{fy}-{str(fy + 1)[2:]}"


def regime_of(sale_date):
    """'new' on or after the cutoff, else 'old'. Section 3(8), the SALE date."""
    return "new" if pd.Timestamp(sale_date) >= CGT_REGIME_CHANGE else "old"


def exemption_for_fy(fy):
    """The LTCG annual exemption for a financial year. Section 3(5)/(6).

    KEYED ON THE FINANCIAL YEAR, NOT THE SALE DATE, and that is the whole reason
    this is a function rather than a branch inside the rate lookup. FY2024-25
    draws Rs 1,25,000 even for a lot sold in May 2024 at the OLD rate; the
    document's worked table shows exactly that.
    """
    return LTCG_EXEMPTION_NEW if fy >= LTCG_EXEMPTION_FY_CUT else LTCG_EXEMPTION_OLD


def closed_lots(path):
    """Every closed lot in a trade log, FIFO per symbol. None when absent.

    Returns a frame with one row per SELL-matched parcel:
        symbol, buy_date, sell_date, qty, buy_price, sell_price,
        held_days, is_long, regime, fy, gain

    READ FROM THE ENGINE'S OWN TRADE LOG, so tax is computed on the trades that
    actually happened rather than on a reconstruction of them. None when the log
    does not exist, so the caller reports the column as unavailable rather than
    silently as zero -- the parked file's behaviour, which was right.

    FIFO IS IMPLEMENTED AND CANNOT CURRENTLY BIND. The engine opens a position
    only when the symbol is absent (test_exposure.py:306) and always exits the
    whole position (test_exposure.py:260), so there is exactly one open lot per
    symbol and FIFO, LIFO and average-cost are identical. The loop is kept
    general because a future partial-exit rule would otherwise be silently
    mismatched, and a wrong basis does not raise -- it just reports.

    GAIN IS THE PRICE DIFFERENCE ONLY -- section 3(C), treatment (ii). Neither
    leg's charges are deducted. See the module docstring on why that is
    conservative.

    THE PRICE IS THE PERSISTED FILL PRICE, which is post-slippage and rounded to
    two decimals. That is the price the trade happened at and the price the cash
    account moved by; our slippage is a price move, not a cost, so there is no
    sense in which a clean price was ever paid.
    """
    from config import read_table  # lazy: this module is imported without the repo root on sys.path
    if not Path(path).exists():
        return None
    tr = read_table(path, parse_dates=["date"]).sort_values("date")
    lots, rows = {}, []
    for _, t in tr.iterrows():
        sym, q, px = t["symbol"], int(t["qty"]), float(t["price"])
        if t["action"] == "BUY":
            lots.setdefault(sym, []).append([q, px, t["date"]])
            continue
        need = q
        while need > 0 and lots.get(sym):
            lot = lots[sym][0]
            take = min(need, lot[0])
            held = (t["date"] - lot[2]).days
            rows.append({
                "symbol": sym,
                "buy_date": lot[2], "sell_date": t["date"],
                "qty": take, "buy_price": lot[1], "sell_price": px,
                "held_days": held,
                "is_long": held >= LTCG_HOLD_DAYS,
                "regime": regime_of(t["date"]),
                "fy": financial_year(t["date"]),
                "gain": take * (px - lot[1]),
            })
            lot[0] -= take
            need -= take
            if lot[0] == 0:
                lots[sym].pop(0)
    if not rows:
        return pd.DataFrame(columns=[
            "symbol", "buy_date", "sell_date", "qty", "buy_price", "sell_price",
            "held_days", "is_long", "regime", "fy", "gain"])
    return pd.DataFrame(rows)


def max_holding_days(lots):
    """The longest holding period in a lot frame, or None when it is empty.

    EXISTS SO A GATE CAN WATCH THE LTCG CEILING, AND THE CEILING HAS BEEN
    CROSSED. This docstring used to say that every published figure in this
    repository rests on the long-term branch never firing. That is FALSE as of
    the four-universe runs of 2026-09-18, measured 2026-09-19:

        nifty100   SOLARINDS   2022-07-20 -> 2023-10-06   443 days
        nifty50    TATACONSUM  2019-05-30 -> 2020-08-17   445 days
        nifty50    TRENT       2019-07-26 -> 2021-03-05   588 days
        nifty50    TRENT       2022-08-19 -> 2023-09-06   383 days

    Four lots over 365 days. All four routed to a `long_` bucket, all four taxed
    at LTCG_RATE["old"] = 0.10 with the annual exemption applied ahead of them,
    and FY_TAX_STATEMENT carries the resulting long_old amounts -- nifty100
    FY2023-24 Rs 128,379.35, nifty50 FY2020-21 Rs 105,765.31 and FY2023-24
    Rs 71,676.15. The routing was correct throughout; only the prose was wrong.

    midcap150 (max 290) and midcap50 (max 322) are still entirely short-term,
    and that is a property of those two windows, not of the pipeline.

    THE FAILURE MODE THIS FUNCTION WAS WRITTEN AGAINST IS THE ONE THAT HAPPENED:
    the branch began firing and nothing said so, because this function had no
    caller for as long as it existed. It has one now -- check_all.py's
    LTCG-boundary condition. Do not leave it uncalled again; an uncalled guard
    is prose with a def in front of it.
    """
    if lots is None or lots.empty:
        return None
    return int(lots["held_days"].max())


def realized_buckets(lots):
    """{fy: {short_old, short_new, long_old, long_new}} -- section 3(A)'s cross.

    The four buckets are {short,long} x {old,new}: the holding-period test and
    the regime test are independent, so all four can be occupied in one year.
    Every financial year present in `lots` gets an entry, including zeroed ones,
    so a caller iterating years cannot silently skip a loss year.
    """
    out = {}
    if lots is None or lots.empty:
        return out
    for fy, g in lots.groupby("fy"):
        b = dict.fromkeys(BUCKETS, 0.0)
        for _, r in g.iterrows():
            key = ("long_" if r["is_long"] else "short_") + r["regime"]
            b[key] += float(r["gain"])
        out[int(fy)] = b
    return out


def tax_for_fy(fy, b):
    """The tax owed for one financial year. Section 3.4, verbatim.

    Returns a dict carrying every intermediate the document names, so a reader
    can check the arithmetic against the spec line by line instead of trusting
    a single total.
    """
    # ---- STCG: no exemption, buckets net against each other -----------------
    stcg_net = b["short_old"] + b["short_new"]
    stcg_taxable = max(stcg_net, 0.0)
    stcg_old_t = min(max(b["short_old"], 0.0), stcg_taxable)
    stcg_new_t = stcg_taxable - stcg_old_t
    stcg_tax = stcg_old_t * STCG_RATE["old"] + stcg_new_t * STCG_RATE["new"]

    # ---- LTCG: annual exemption, consumed by the OLD-rate gains first -------
    # ltcg_new_t is taken FIRST out of the taxable remainder, which is what
    # leaves the exemption sitting against the old-rate gains. The document
    # states the intent ("consumed by the pre-cutoff gains FIRST") and gives the
    # formulas; the formulas are what is implemented.
    exemption = exemption_for_fy(fy)
    ltcg_net = b["long_old"] + b["long_new"]
    ltcg_taxable = max(ltcg_net - exemption, 0.0)
    ltcg_new_t = min(ltcg_taxable, max(b["long_new"], 0.0))
    ltcg_old_t = ltcg_taxable - ltcg_new_t
    ltcg_tax = ltcg_old_t * LTCG_RATE["old"] + ltcg_new_t * LTCG_RATE["new"]

    return {
        "fy": fy, "fy_label": fy_label(fy),
        **{k: b[k] for k in BUCKETS},
        "stcg_net": stcg_net, "stcg_taxable": stcg_taxable,
        "stcg_old_taxed": stcg_old_t, "stcg_new_taxed": stcg_new_t,
        "stcg_tax": stcg_tax,
        "exemption": exemption,
        "ltcg_net": ltcg_net, "ltcg_taxable": ltcg_taxable,
        "ltcg_old_taxed": ltcg_old_t, "ltcg_new_taxed": ltcg_new_t,
        "ltcg_tax": ltcg_tax,
        "total_tax": stcg_tax + ltcg_tax,
    }


def assess_dates(fys, trading_days):
    """{fy: assessment date or None} -- section 3(9).

    "Each financial year is assessed EXACTLY ONCE, on the first trading day at
    or after 31 March, and the whole tax is deducted from cash as a SINGLE LUMP
    SUM."

    None means NO TRADING DAY IN THE WINDOW SATISFIES THAT RULE, which is not a
    hypothetical: FY2026-27 is assessed on the first trading day at or after
    31-Mar-2027 and the backtest ends 2026-05-29, so its liability is computed
    and never deducted. Returning None rather than silently dropping the year is
    the point -- a liability that vanishes without being reported flatters the
    result, and the caller is expected to say so out loud.
    """
    days = pd.DatetimeIndex(sorted(pd.DatetimeIndex(trading_days)))
    out = {}
    for fy in sorted(fys):
        due = pd.Timestamp(year=fy + 1, month=3, day=31)
        later = days[days >= due]
        out[int(fy)] = (later[0] if len(later) else None)
    return out


def liability_schedule(lots, trading_days):
    """-> (DataFrame of per-FY tax, {date: rupees due}) for the engine hook.

    The frame is FY_TAX_STATEMENT's content. The dict is what the in-loop
    deduction consumes: one entry per assessed financial year, keyed by the
    trading day the lump sum comes out of cash.

    A YEAR SECTION 3(9) WOULD ASSESS AFTER THE WINDOW IS SETTLED ON ITS LAST
    SESSION (since 2026-09-25, matching Ledger.due_on), so every year is in the
    dict and `assessed_basis` says which rule dated it. Nothing here deducts
    anything or touches an equity curve; results/test_exposure.py moves the cash.
    """
    buckets = realized_buckets(lots)
    rows = [tax_for_fy(fy, b) for fy, b in sorted(buckets.items())]
    when = assess_dates(buckets.keys(), trading_days)
    last = pd.Timestamp(max(pd.DatetimeIndex(trading_days)))
    for r in rows:
        d = when[r["fy"]]
        # THE NOTE IS A COLUMN, NOT A FOOTNOTE ON THE RENDERER, so a reader
        # scanning FY_TAX_STATEMENT sees from the row itself which rule dated it.
        if d is not None:
            r["assessed_on"] = d
            r["assessed"] = True
            r["assessed_basis"] = "section 3(9)"
            r["assessed_note"] = ""
        else:
            due_d = pd.Timestamp(year=r["fy"] + 1, month=3, day=31)
            r["assessed_on"] = last
            r["assessed"] = True
            r["assessed_basis"] = "backtest end"
            r["assessed_note"] = (
                f"SETTLED AT THE BACKTEST END -- section 3(9) would assess "
                f"{r['fy_label']} on the first trading day at or after "
                f"{due_d.date()}, outside the window. Settled on {last.date()}, "
                f"after that day's fills, on gains realised to that date, with the "
                f"document's netting and full annual exemption (decision of "
                f"2026-09-25; the document is silent on a window ending mid-year).")
    due = {r["assessed_on"]: r["total_tax"]
           for r in rows if r["assessed"] and r["total_tax"] > 0}
    return pd.DataFrame(rows), due


# ---------------------------------------------------------------------------
# THE IN-LOOP LEDGER -- because the liability and the trades are circular
# ---------------------------------------------------------------------------
# TAX CANNOT BE COMPUTED FROM A FINISHED RUN AND THEN DEDUCTED FROM IT. The
# deduction reduces cash; cash sizes every order through `int(... // pr)`; the
# orders are what produce the gains; the gains are the liability. Running
# untaxed, computing the bill from that log and charging it back is not a
# conservative approximation -- it charges a bill the taxed portfolio would never
# have incurred, because after the first deduction it is holding different names
# in different sizes. A second pass does not converge to anything meaningful and
# a fixed-point iteration would be a rule the document does not contain.
#
# SO THE LEDGER ACCRUES AS THE RUN GOES. Every SELL is bucketed the moment it
# happens, from the position the engine is actually holding, and each financial
# year's assessment reads only what had been realised by that date. One pass,
# self-consistent, and it is what section 3(9)'s sentence describes: the bill
# for a year reduces the capital available to trade the following one.
#
# THIS CLASS HOLDS NO CASH AND MOVES NONE. It is told about fills and asked what
# is due; results/test_exposure.py owns the cash and does the subtraction.
class Ledger:
    """Realised-gain accumulator with per-financial-year assessment.

    buy(sym, qty, price, date)     record an opened lot
    sell(sym, qty, price, date)    -> realised gain, and bucket it
    due_on(date, after_fills)      -> rupees to deduct before (or, for a year
                                      assessed inside itself, after) the fills
    """

    def __init__(self, dates):
        self.lots = {}
        self.realized = {}
        self.assessed = set()
        self.rows = []
        # WHEN EACH YEAR FALLS DUE, PRECOMPUTED FROM THE RUN'S OWN CALENDAR.
        # Section 3(9): the first trading day at or after 31 March. A year whose
        # date never arrives is simply absent here and is never assessed -- which
        # is FY2026-27 on this window, and liability_schedule() is what reports
        # that rather than this.
        d = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dates)))
        # THE LAST SESSION, on which every year still unassessed is settled
        # (due_on, after_fills=True). None for an empty calendar.
        self.end = d[-1] if len(d) else None
        self.settled_at_end = set()
        self.assess_on = {}
        for fy in sorted({financial_year(x) for x in d}):
            later = d[d >= pd.Timestamp(year=fy + 1, month=3, day=31)]
            if len(later):
                self.assess_on.setdefault(later[0], []).append(fy)

    def buy(self, sym, qty, price, date):
        self.lots.setdefault(sym, []).append([int(qty), float(price), date])

    def sell(self, sym, qty, price, date):
        """Realise `qty` of `sym` FIFO. Returns the gain; buckets it by FY."""
        need, gain = int(qty), 0.0
        while need > 0 and self.lots.get(sym):
            lot = self.lots[sym][0]
            take = min(need, lot[0])
            held = (date - lot[2]).days
            g = take * (float(price) - lot[1])
            fy = financial_year(date)
            key = ("long_" if held >= LTCG_HOLD_DAYS else "short_") + regime_of(date)
            self.realized.setdefault(fy, dict.fromkeys(BUCKETS, 0.0))[key] += g
            self.rows.append({
                "symbol": sym, "buy_date": lot[2], "sell_date": date,
                "qty": take, "buy_price": lot[1], "sell_price": float(price),
                "held_days": held, "is_long": held >= LTCG_HOLD_DAYS,
                "regime": regime_of(date), "fy": fy, "gain": g})
            gain += g
            lot[0] -= take
            need -= take
            if lot[0] == 0:
                self.lots[sym].pop(0)
        return gain

    def due_on(self, date, after_fills=False):
        """Rupees due on `date`, or 0.0. Each financial year assessed ONCE.

        TWO PHASES, 2026-09-23. The engine calls this before the day's fills
        (after_fills=False) and again after them (after_fills=True). A year whose
        assessment day is still INSIDE that year -- 31 March falling on a trading
        day -- is assessed in the second call, so a sell that day is taxed with
        its own year. Every other year is assessed in the first call, as before.
        The leak described below is therefore closed rather than detected: the
        combination sweep hit it on all eight tax-on cells at cadence 1, where a
        rebalance runs every day, and tax_report's reconciliation refused them.
        No published cadence-20 run has a fill on those days, measured across
        all eight universes, so no published number moves.

        THE SAME-DAY LEAK IS DETECTED, NOT ASSUMED AWAY. Section 3(9) can put a
        year's assessment on the last day of that same year -- FY2019-20 falls
        due 2020-03-31, which is inside FY2019-20 -- and the deduction happens
        before that day's fills. A sell later the same day lands in a year that
        has already been assessed exactly once, so its gain is never taxed.

        It does not happen on the current window: no sell falls on an assessment
        date belonging to its own financial year (checked across both universes,
        2026-09-17; the one sell that does land on an assessment date is
        2024-04-01, which is FY2024-25 being assessed for FY2023-24). It is
        calendar luck, not a property, so `leaked` records it instead of the run
        losing a gain in silence.
        """
        fys = self.assess_on.get(pd.Timestamp(date), [])
        total = 0.0
        for fy in fys:
            if (financial_year(date) == fy) != after_fills:
                continue
            if fy in self.assessed:
                continue
            self.assessed.add(fy)
            b = self.realized.get(fy)
            if b:
                total += tax_for_fy(fy, b)["total_tax"]
        # SETTLEMENT AT THE BACKTEST END, 2026-09-25. On the last session, after
        # its fills, every financial year with realised gains that section 3(9)
        # would assess after the window is settled now, on what was realised by
        # this date, with the same tax_for_fy. On this window that is FY2026-27.
        if after_fills and self.end is not None and pd.Timestamp(date) == self.end:
            for fy in sorted(self.realized):
                if fy in self.assessed:
                    continue
                self.assessed.add(fy)
                self.settled_at_end.add(fy)
                total += tax_for_fy(fy, self.realized[fy])["total_tax"]
        return total

    def leaked(self):
        """Gains realised into a financial year that was already assessed.

        Empty is the expected answer. A non-empty list means a gain was realised
        AFTER its own year's assessment and escaped tax entirely. A sale ON a
        same-year assessment day is not one: that year is assessed after the
        day's fills (due_on, 2026-09-23), so the sale is in its bill.
        """
        out = []
        for r in self.rows:
            for d, fys in self.assess_on.items():
                if r["fy"] in fys and r["sell_date"] > d:
                    out.append(r)
                    break
        return out
