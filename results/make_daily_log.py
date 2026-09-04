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

W = 118

# Mirrors the constants in test_exposure.py -- needed for reconciliation only.
SLIPPAGE = 0.0015
CASH_YIELD = 0.0        # must match test_exposure.py
START_CAPITAL = 1_000_000
CASH_DAILY = (1 + CASH_YIELD) ** (1 / 252) - 1

TOL_CASH = 0.50      # rupees; CSVs are rounded to 2 decimals, so a few paise of
                     # noise is expected (max observed 0.03). A real error would
                     # be orders of magnitude larger.
TOL_EQ = 0.05

LEGEND = """\
 HOW TO READ THIS FILE
 ------------------------------------------------------------------------------------------------------------------
 Each trading day is one block. The order of events matches the order in the code:

   1. the cash balance is carried forward (with yield, if a cash yield is configured)
   2. yesterday's order fills at TODAY's OPEN -- all SELLs first, then all BUYs
   3. positions are marked to market at TODAY's CLOSE
   4. if today is a rebalance day (every 20 trading days), a new order is created from
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

 WHY SOLD   A stock is sold only when its rank falls below 16 (the buffer). Ranks 9-16 are
            held, which avoids unnecessary turnover at every rebalance.
 WHY BOUGHT It entered the top 8 and was not already held.
 EXPOSURE   Breadth is the fraction of stocks with positive 20-day momentum. That same
            fraction of the portfolio is invested; the remainder stays in cash. There is
            no indicator and no tuned threshold.
 NOTE       Existing holdings are never resized. Only new positions are sized against the
            target exposure, so the actual invested percentage can drift from the target.
"""


def load(M, tag):
    r = lambda f, c: pd.read_csv(M / f"{f}_{tag}.csv", parse_dates=[c])
    sk = M / f"daily_skipped_{tag}.csv"
    skipped = pd.read_csv(sk, parse_dates=["date"]) if sk.exists() else pd.DataFrame()
    if len(skipped) == 0:
        skipped = pd.DataFrame(columns=["date", "side", "symbol", "reason", "detail"])
    return (r("daily_holdings", "date"), r("daily_summary", "date"),
            r("daily_trades", "date"), r("daily_ranking", "decided_on"),
            r("daily_decisions", "decided_on"), skipped)


def build(mdir, tag):
    M = Path(mdir)
    h, s, t, rk, dc, sk = load(M, tag)

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
         f" PREDICTIVE ENGINE -- FORENSIC DAILY LOG  |  {tag} UNIVERSE  |  v2 FINAL (breadth-scaled)",
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
         "=" * W, LEGEND, "=" * W]

    ok_cash = ok_eq = ok_sh = 0
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
                why = act_of.get(src, {}).get(o["symbol"], (None, None))
                if o["action"] == "SELL":
                    rt = roundtrip.get((d, o["symbol"]))
                    wtxt = (f'rank {why[0]} -- fell out of the buffer (16)' if why[0]
                            else "fell out of the buffer")
                    if rt:
                        L.append(f'          -> {wtxt}  |  entered {rt["buy_date"].date()} at '
                                 f'{rt["buy_px"]:,.2f}, held {rt["days"]} days  |  '
                                 f'round trip {rt["pct"]:+.2f}%, net P&L Rs {rt["net"]:+,.0f}')
                    else:
                        L.append(f'          -> {wtxt}')
                else:
                    L.append(f'          -> rank {why[0] if why[0] else "?"} -- entered the '
                             f'top 8 and was not already held')
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

        c_ok, e_ok, s_ok = abs(d_cash) <= TOL_CASH, abs(d_eq) <= TOL_EQ, len(bad_sh) == 0
        ok_cash += c_ok; ok_eq += e_ok; ok_sh += s_ok
        if not (c_ok and e_ok and s_ok):
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
                st = ("top 8" if act in ("BUY", "HOLD-top") else
                      "buffer" if act == "HOLD-buffer" else
                      "exiting" if act == "SELL" else "-")
                L.append(f'      {x["symbol"]:<13}{int(x["qty"]):>7}{str(edt):>12}'
                         f'{epx:>10,.2f}{x["price"]:>10,.2f}{x["value"]:>14,.2f}'
                         f'{x["weight_pct"]:>7.2f}%{unre:>8.2f}%{days:>6}'
                         f'{(rnk if rnk else "-"):>6}  {st}')
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
            L.append(f'      breadth       : {int(x["breadth_pos"])}/{int(x["breadth_total"])} stocks '
                     f'with positive 20-day momentum  =  {x["breadth"]:.4f}')
            L.append(f'      exposure      : {x["exposure"]*100:.2f}%  (equal to breadth -- no threshold)')
            L.append(f'      portfolio     : Rs {x["port_value"]:,.2f}   '
                     f'(of which cash Rs {x["cash_before"]:,.2f})')
            L.append(f'      invest value  : Rs {x["invest_value"]:,.2f}   '
                     f'= portfolio x exposure x 0.98 safety factor')
            L.append(f'      plan          : {int(x["n_buy"])} BUY, {int(x["n_sell"])} SELL   '
                     f'({int(x["n_held_before"])} stocks currently held)')
            act_inv = float(r["invested_pct"])
            L.append(f'      target vs held: target exposure {x["exposure"]*100:.2f}% against '
                     f'{act_inv:.2f}% currently invested   '
                     f'(gap {act_inv - x["exposure"]*100:+.2f} pts -- existing holdings are '
                     f'not resized)')
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
                L.append("      (ranks 1-8 are bought or held, 9-16 are held in the buffer, "
                         "17+ are sold)")
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
          f"   orders filled               : {len(t):,}  (every one is shown above)",
          f"   orders skipped              : {len(sk):,}  (each shown with its reason)",
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
    import config, config74, config_mid
    print("Building forensic daily logs...")
    build(config.METRICS_DIR, "58")
    build(config74.METRICS_DIR_74, "74")
    # MidCap150 uses the same build() and therefore the same four-section format;
    # only the metrics folder and the tag differ. The 58 and 74 logs are produced
    # by the identical code path and are unchanged by this addition.
    build(config_mid.METRICS_DIR_MID, "mid")
    # Nifty 100 (fourth universe) uses the identical build(), so it gets the same
    # four sections and the same daily reconciliation as every other universe.
    import config_n100
    build(config_n100.METRICS_DIR_N100, "n100")


if __name__ == "__main__":
    main()
