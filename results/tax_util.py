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

    Zero lots exceed 365 days, so "100% short-term" is TRUE today -- by 39 days,
    empirically, on this window and these arms. It is not a guarantee, and a
    cadence change, a wider buffer or a longer window could break it silently.

    So holding period is COMPUTED PER LOT and branched on, never hardcoded, and
    max_holding_days() exists so a gate can fail loudly the day that 326 crosses
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

    AND ONE STUB IS NEVER ASSESSED AT ALL. Section 3(9) assesses a financial
    year on the first trading day at or after 31 March. For FY2026-27 that date
    is in 2027, outside the backtest window, so its liability is COMPUTED and
    NEVER DEDUCTED. assess_dates() reports it as unassessed rather than
    dropping it, because a liability that silently vanishes flatters the result.

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
    if not Path(path).exists():
        return None
    tr = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
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

    EXISTS SO A GATE CAN WATCH THE 326-DAY CEILING. Every published figure in
    this repository rests on the long-term branch never firing, and that is an
    EMPIRICAL property with 39 days of headroom, not a structural one. A cadence
    change or a wider buffer could cross it, and the failure mode is silent: the
    long-term rate simply starts applying and every tax figure moves.
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

    UNASSESSED YEARS ARE IN THE FRAME AND NOT IN THE DICT, and the frame says
    which. Nothing here deducts anything or touches an equity curve; this module
    computes what is owed and when, and results/test_exposure.py moves the cash.
    """
    buckets = realized_buckets(lots)
    rows = [tax_for_fy(fy, b) for fy, b in sorted(buckets.items())]
    when = assess_dates(buckets.keys(), trading_days)
    last = pd.Timestamp(max(pd.DatetimeIndex(trading_days)))
    for r in rows:
        d = when[r["fy"]]
        r["assessed_on"] = d
        r["assessed"] = d is not None
        # THE NOTE IS A COLUMN, NOT A FOOTNOTE ON THE RENDERER. An unassessed
        # year's liability is real, computed, and never deducted; a reader
        # scanning FY_TAX_STATEMENT must see WHY from the row itself rather than
        # from prose somewhere else that a later edit can drift away from.
        if r["assessed"]:
            r["assessed_note"] = ""
        else:
            due_d = pd.Timestamp(year=r["fy"] + 1, month=3, day=31)
            r["assessed_note"] = (
                f"NOT DEDUCTED -- section 3(9) assesses {r['fy_label']} on the "
                f"first trading day at or after {due_d.date()}, which is outside "
                f"the backtest window (ends {last.date()}). The liability is real "
                f"and is reported here; no cash was taken for it, so the final "
                f"sessions of the window are effectively untaxed -- and that "
                f"untaxed tail includes the held-out sessions.")
    due = {r["assessed_on"]: r["total_tax"]
           for r in rows if r["assessed"] and r["total_tax"] > 0}
    return pd.DataFrame(rows), due
