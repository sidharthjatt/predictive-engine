"""
make_daily_log.py -- forensic DAILY LOG.

A complete record of every trading day, in four sections:
  [A] ORDER EXECUTION   the previous rebalance order, filled at TODAY's OPEN
  [B] RECONCILIATION    whether the arithmetic ties out (cash, equity, share count)
  [C] POSITIONS         what is held at TODAY's CLOSE, and when it was bought
  [D] ORDER CREATION    on a rebalance day, the new ranking from TODAY's CLOSE

Everything is read from the audit CSVs. No backtest number is recomputed here;
section [B] only checks the figures that were already written.

Timing (verified against test_exposure.backtest_exposure):
  each day the cash balance is carried forward first, then the pending order is
  filled (all SELLs, then all BUYs), then positions are marked at the CLOSE, and
  finally a new order is created if today is a rebalance day. An order always
  fills at the OPEN of the next trading day.
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import survivorship as sv
import config

W = 118

# TOP_N AND BUFFER ARE READ, NOT TYPED. The legend and sections [A], [C] and [D]
# spelled "top 8", "buffer (16)" and "ranks 1-8 ... 9-16 ... 17+" as literals. They
# happen to match config today; a change to either constant would have left this
# file describing a selection rule the engine no longer used.
TOP_N, BUFFER = config.TOP_N, config.BUFFER

# Mirrors the constants in test_exposure.py -- needed for reconciliation only.
SLIPPAGE = 0.0015
CASH_YIELD = 0.0        # must match test_exposure.py
START_CAPITAL = 1_000_000
CASH_DAILY = (1 + CASH_YIELD) ** (1 / 252) - 1

TOL_CASH = 0.50      # rupees; CSVs are rounded to 2 decimals, so a few paise of
                     # noise is expected (max observed 0.03). A real error would
                     # be orders of magnitude larger.
TOL_EQ = 0.05
# The same 1 paisa audit_step.run() uses to decide whether to write the trail at
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
            Capital gains tax is NOT modelled anywhere in this system.

 SECTION B  This is the proof that the arithmetic is correct. Three checks run daily:
              CASH    opening cash + yield + sale proceeds - purchases - fees = closing cash
              EQUITY  cash + market value of holdings = total portfolio value
              SHARES  for every symbol: opening quantity +/- today's trade = closing quantity
            Each check is marked OK or *** FAIL ***. A full tally appears at the end of the file.

 WHY SOLD   A stock is sold only when its rank falls below {buffer} (the buffer). Ranks {top1}-{buffer} are
            held, which avoids unnecessary turnover at every rebalance.
 WHY BOUGHT It entered the top {top} and was not already held.
{exposure_para}
{sizing_para}
 SKIPS      An order that was created but did not fill is listed under the day it should
            have filled, with the reason and the actual numbers. Four reasons exist:
              no open price (NaN/<=0)  the symbol had no usable open price that morning
              qty < 1 after sizing     the target was smaller than one share
              cash short (before TC)   the funding defect below
              cash short (incl TC)     the same, once transaction costs are added
 FUNDING    invest value is a share of the WHOLE portfolio, but new positions are paid for
            out of CASH ALONE, and a name already held is never resized. So whenever a
            buffer name is holding capital the book is over-committed by construction and
            the tail of the score-descending buy loop is skipped. That is what the
            cash-short skips are. A 100%-invested arm hits it constantly; a breadth-scaled
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


def legend_for(arm):
    """LEGEND_TEMPLATE with the arm-dependent paragraphs resolved."""
    if arm.mode == "breadth":
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
    import cadence as _cd
    return LEGEND_TEMPLATE.format(exposure_para=exposure_para, sizing_para=sizing_para,
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
# times across every mid and n100 trail, while PATANJALI's 2019-11-27 SELL of
# 33,575 shares filled at 1.1483 on a date with no raw row at all. ffill is
# precisely what prevents the skip, so surfacing skips can never surface this.
#
# READ-ONLY. Nothing here changes a price or a fill; it is a reporting flag.
def raw_row_index(u):
    """{symbol: set of dates that have a RAW price row}, restricted to the calendar.

    Dates come from config.read_price_csv, which routes through
    config.smart_parse_dates -- the 58/74 files and the mid/n100 files use
    different date formats and a hardcoded strptime silently drops whole universes.

    The calendar restriction matters in both directions: 70 of the 148 MidCap150
    files carry market-holiday rows that are not sessions, and counting one of
    those as "a raw row exists" would hide a genuine gap.
    """
    from engine_core import _load_calendar
    cal = _load_calendar()
    idx = {}
    try:
        src = Path(u.prepare_data_dir())
    except Exception:
        return None, None
    for f in sorted(src.glob("*.csv")):
        try:
            d = config.read_price_csv(f)
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
    r = lambda f, c: pd.read_csv(M / f"{f}_{tag}.csv", parse_dates=[c])
    sk = M / f"daily_skipped_{tag}.csv"
    skipped = pd.read_csv(sk, parse_dates=["date"]) if sk.exists() else pd.DataFrame()
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


def build(mdir, tag, arm, raw_idx=None, cal_sorted=None):
    """One forensic log for one already-written audit trail, named by `tag`.

    THIS USED TO REFUSE UNLESS THE RUN WAS v2 AT THE DEFAULT CADENCE, because it
    reconstructed the unsuffixed daily_*_{universe}.csv names itself rather than
    asking for the writer's rule. Under `--arm v3` or `--rebal 200` the trail it
    wanted did not exist, so it printed a skip and produced no forensic log at all
    -- the behaviour this change removes. The caller now resolves the tag through
    audit_step.artefact_tag(), the one definition, and passes it in.
    """
    M = Path(mdir)
    h, s, t, rk, dc, sk = load(M, tag)

    # THE ARM'S OWN PUBLISHED CURVE, resolved by audit_step's lookup -- imported,
    # not reimplemented. It already picks v2FINAL_equity{suffix}.csv for v1/v2 and
    # v34_equity{suffix}.csv for v3/v4, with the cadence fallbacks, and getting
    # that resolution subtly different here would reconcile against another arm's
    # or another cadence's curve and report a confident MISMATCH of millions.
    #
    # THIS IS VISIBILITY, NOT A NEW SAFETY PROPERTY. audit_step.run() already
    # compares the re-run against this same curve and RETURNS WITHOUT WRITING any
    # of the six CSVs when the max absolute difference is 1 paisa or more. So a
    # trail only exists on disk if this check has already passed upstream; showing
    # it here makes the log self-contained for a reader who has only the log.
    import audit_step as _as
    # NAMED ref_curve, NOT ref. Section [A] below already binds `ref` to the
    # derived open price of each fill, inside the day loop -- a curve called `ref`
    # survived exactly until the first execution day and then became a float.
    ref_curve = _as._reference_curve(M, arm.name)
    # Names the COLUMN, not the file: _reference_curve chooses between several
    # candidate files and does not report which, and guessing the filename here
    # would be a second copy of that resolution -- the thing this import avoids.
    ref_name = f"engine curve [{arm.equity_column}]"

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

    # Order IDs: on each execution day, SELLs are S1..Sn and BUYs are B1..Bn.
    oid = {}
    for d in sorted(tg):
        rno = rebal_no.get(prev_dec(d), 0)
        g = tg[d]
        for n, (_, o) in enumerate(g[g.action == "SELL"].iterrows(), 1):
            oid[(d, o["symbol"])] = f"R{rno:03d}-S{n}"
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
         f" Capital         : Rs {START_CAPITAL:,}  ->  Rs {s['total'].iloc[-1]:,.0f}",
         f" Total fees paid : Rs {s['cum_tc'].iloc[-1]:,.2f}",
         # Stated in the header of every universe's log, so a reader who opens this
         # file six months from now sees how the universe was constructed before
         # they see a single number from it.
         f" Survivorship    : {sv.describe_state()}",
         "=" * W, legend_for(arm), "=" * W]

    ok_cash = ok_eq = ok_sh = 0
    ok_ref = n_ref = 0
    n_stale_fill = n_stale_hold = n_hold_rows = 0
    stale_syms = {}
    fail_lines = []
    prev_cash, prev_tc = float(START_CAPITAL), 0.0
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
        cum_ret = (total / START_CAPITAL - 1) * 100

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
        if is_exe:
            L.append(f"  >>> [A] ORDER EXECUTION      created at the CLOSE of "
                     f"{src.date() if src is not None else '?'}, filled at TODAY's OPEN")
            L.append(f'      {"OrderID":<10}{"Side":<6}{"Symbol":<13}{"Qty":>7}'
                     f'{"Open(der)":>12}{"FillPx":>11}{"Slip Rs":>10}{"Value":>14}{"TxnFee":>9}')
            slip_total = 0.0
            for _, o in pd.concat([g[g.action == "SELL"], g[g.action == "BUY"]]).iterrows():
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
                    if rt:
                        L.append(f'          -> {wtxt}  |  entered {rt["buy_date"].date()} at '
                                 f'{rt["buy_px"]:,.2f}, held {rt["days"]} days  |  '
                                 f'round trip {rt["pct"]:+.2f}%, net P&L Rs {rt["net"]:+,.0f}')
                    else:
                        L.append(f'          -> {wtxt}')
                else:
                    L.append(f'          -> rank {why[0] if why[0] else "?"} -- entered the '
                             f'top {TOP_N} and was not already held')
            b, sl = g[g.action == "BUY"], g[g.action == "SELL"]
            L.append(f'      TOTAL   BUY {len(b)} Rs {b["value"].sum():>12,.0f}   |   '
                     f'SELL {len(sl)} Rs {sl["value"].sum():>12,.0f}')
            L.append(f'      fees    BUY Rs {b["tc"].sum():,.2f}   +   '
                     f'SELL Rs {sl["tc"].sum():,.2f}   =   Rs {g["tc"].sum():,.2f}'
                     f'   |   slippage cost Rs {slip_total:,.0f}')
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
        exp_cash = prev_cash + yield_amt + sell_v - buy_v - fees_today
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

        prev_cash, prev_tc, prev_qty = cash, float(r["cum_tc"]), qty_now

    # ---------------- FINAL VERIFICATION ----------------
    n = len(all_days)
    allok = (ok_cash == n and ok_eq == n and ok_sh == n)
    L += ["", "=" * W,
          " VERIFICATION SUMMARY -- arithmetic checks across the whole file",
          "=" * W,
          f"   trading days checked        : {n:,}",
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
    L += [
          f"   final equity                : Rs {s['total'].iloc[-1]:,.2f}",
          ""]
    if fail_lines:
        L += ["   MISMATCHED DAYS:"] + fail_lines + [""]
    L += [f"   VERDICT: {'every day reconciles.' if allok else 'some days failed -- see above.'}",
          "=" * W]

    out = M / f"DAILY_LOG_{tag}.txt"
    out.write_text("\n".join(L))
    print(f"  {tag}: {n:,} days, {len(L):,} lines -> {out.name}")
    print(f"       reconciliation  cash {ok_cash}/{n}  equity {ok_eq}/{n}  shares {ok_sh}/{n}"
          f"  {'ALL OK' if allok else '*** CHECK FAILURES ***'}")
    return out


def main():
    """STEP 15. Body moved out of the __main__ guard, unchanged.

    S4 gave every pipeline step a function boundary so run.py could call it in
    process; this file and nt_export_scores.py were missed, and nothing noticed
    because run_all.py still SPAWNED each step, and a subprocess runs the __main__
    guard whether or not a main() exists. The first full in-process run stopped
    here with AttributeError. The statements below are the guard's, in order.
    """
    import config
    from universes.registry import REGISTRY, selected_tags
    print("Building forensic daily logs...")

    # FOUR INDEPENDENT LOGS, ONE PER UNIVERSE. build() is the same code for all of
    # them -- only the metrics folder and the tag differ -- and DAILY_LOG_{tag}.txt
    # has no consumer, so nothing downstream depends on any particular one being
    # present. Each is therefore guarded on its own universe and skipped with a
    # reason rather than taking the others down with it.
    #
    # THE METRICS DIRECTORY COMES FROM THE UNIVERSE, not from a per-tag
    # `import config_x` under a per-tag `if`. That shape was four hand-written
    # branches, two of which named the 58 and the 74; when those universes were
    # deleted the branches would have gone on importing a config module that no
    # longer exists. u.metrics_dir is the same path the config module defines,
    # read from the registry entry that already holds it.
    #
    # SELECTION, NOT REGISTRATION. `--universe 58` leaves 74 registered but
    # unselected, and this step used to do 74's work anyway -- writing artefacts
    # for a universe the caller did not ask for. selected_tags() defaults to every
    # registered universe, so a standalone run of this file is unchanged.
    # THE SCANNER LOSES ITS LITERALS HERE, KNOWINGLY. check_pipeline_order used
    # the literal REGISTRY["<tag>"] subscripts to resolve this step's outputs; a
    # loop over REGISTRY reads the same at runtime and leaves the checker blind to
    # them. That is the cost of not naming universes in four branches, and this
    # step's outputs (DAILY_LOG_*.txt) have no downstream consumer for the checker
    # to order against.
    # ONE LOG PER (UNIVERSE, SELECTED ARM), not one per universe. The tag comes
    # from audit_step.artefact_tag -- the same call the writer uses -- so the
    # reader cannot drift from the writer's naming.
    import arms.registry as _ar
    import audit_step

    def _logs_for(u, mdir):
        # ONCE PER UNIVERSE, not once per arm: this reads every raw CSV in the
        # universe, and all four arms share the same answer.
        raw_idx, cal_sorted = raw_row_index(u)
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
            build(mdir, tag, _arm, raw_idx, cal_sorted)

    SEL = set(selected_tags())
    for _t in REGISTRY:
        if _t in SEL:
            _logs_for(REGISTRY[_t], REGISTRY[_t].metrics_dir)
        else:
            print(f"  {_t} not selected for this run -- skipping its daily log")


# THE GUARD THAT WAS NOT HERE. main()'s own docstring records that this file's
# body was moved out of the __main__ guard when the pipeline stopped spawning
# subprocesses -- and the guard was deleted rather than left calling main(). The
# result: `./venv/bin/python results/make_daily_log.py` imported the module,
# defined main(), called nothing, wrote nothing and EXITED 0. A regeneration pass
# during the 2026-09-18 rename "succeeded" that way and changed not one byte; it
# was caught by diffing the output against copies saved beforehand.
#
# check_all.py GATE 3 now refuses any pipeline script without a live __main__
# block, by AST rather than by text -- the string "__main__" appears in main()'s
# docstring above, so a grep passes this file.
if __name__ == "__main__":
    raise SystemExit(main())
