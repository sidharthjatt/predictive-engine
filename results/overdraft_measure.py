"""overdraft_measure.py -- the cash overdraft on tax days, and what paying it would cost.

    ./venv/bin/python results/overdraft_measure.py

Read-only measurement; the engine and every published figure are unchanged. Writes
diagnostics/overdraft_on_tax_day.txt and .csv.

backtest_exposure deducts each financial year's tax from cash without a clamp, so on
an assessment day cash can go negative and stay there until later sales refill it.
For every universe and arm, tax on, cadence 20, under both profiles, this reports:
    - the deepest overdraft and its date, and how many sessions cash is below zero
      (from the published run itself);
    - the CAGR if the tax had to be paid by selling holdings on the assessment day.

THE VARIANT is derived from the shipping function's source (inspect.getsource) with
two named textual patches at asserted anchors, as results/drawdown_exit_measure.py
does. After each tax deduction, if cash is below zero, the book sells a pro-rata
slice of every holding at that day's open (the close where the open is missing),
with the usual slippage (slippage.sell_price, flat) and charges (calc_tc), enough
that cash is no longer negative. The gain on that sale goes to the tax ledger as any
sale does; where the sale day's financial year has already been assessed (a year
assessed on its own 31 March, or the final settlement), its gain is booked to the
next financial year instead, so the sale's tax falls in the year after. A gain booked
past the window is never assessed, and its tax is reported as left unpaid.

With no overdraft in a run the patches do nothing, and the variant must reproduce the
published curve exactly; the script checks that on every cell and aborts otherwise.
"""
import os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[_v] = "1"
import inspect
import math
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import numpy as np
import pandas as pd

import config
import engine_core
import profiles
import tax_util as T
import test_exposure
import arms.registry as arm_reg
from config import read_table
from engine_core import precompute
from universes.registry import REGISTRY

OUT = ROOT / "diagnostics" / "overdraft_on_tax_day"
KEYS = ("holdings", "summary", "trades", "ranking", "decisions", "skipped")

PATCH_PRE = (
    "                _tax_pre = _due\n",
    "                _tax_pre = _due\n"
    "                if cash < 0:\n"
    "                    cash, cum_tc, n_trades = _OD_SELL(dt, shares, cash, opens, prices,\n"
    "                                                      ledger, cum_tc, n_trades)\n")
PATCH_POST = (
    "                _tax_post = _due\n",
    "                _tax_post = _due\n"
    "                if cash < 0:\n"
    "                    cash, cum_tc, n_trades = _OD_SELL(dt, shares, cash, opens, prices,\n"
    "                                                      ledger, cum_tc, n_trades)\n")

EVENTS = []


def _od_sell(dt, shares, cash, opens, prices, ledger, cum_tc, n_trades):
    """Sell a pro-rata slice of every holding at today's open until cash >= 0."""
    sl, calc_tc = test_exposure._sl, test_exposure.calc_tc
    ref = {}
    for s in shares:
        r = opens.get(s, np.nan)
        if np.isnan(r) or r <= 0:
            r = prices.get(s, np.nan)
        if not (np.isnan(r) or r <= 0):
            ref[s] = r
    total = sum(shares[s] * ref[s] for s in ref)
    need = -cash
    if total <= 0:
        return cash, cum_tc, n_trades
    frac = min(1.0, need / total * 1.003)
    while True:
        plan = {s: min(int(shares[s]), int(math.ceil(shares[s] * frac))) for s in ref}
        net = 0.0
        for s, q in plan.items():
            if q > 0:
                pr = sl.sell_price(ref[s], q, None, None)
                net += q * pr - calc_tc(pr, q, "SELL")
        if net >= need or frac >= 1.0:
            break
        frac = min(1.0, frac * 1.01 + 1e-4)
    fy = T.financial_year(dt)
    shift = fy in ledger.assessed
    sold = charges = 0.0
    for s, q in plan.items():
        if q < 1:
            continue
        pr = sl.sell_price(ref[s], q, None, None)
        tc = calc_tc(pr, q, "SELL")
        cash += q * pr - tc
        cum_tc += tc
        n_trades += 1
        sold += q * pr
        charges += tc
        before = dict(ledger.realized.get(fy, dict.fromkeys(T.BUCKETS, 0.0)))
        n_rows = len(ledger.rows)
        ledger.sell(s, q, round(pr, 2), dt)
        if shift:
            now = ledger.realized[fy]
            nxt = ledger.realized.setdefault(fy + 1, dict.fromkeys(T.BUCKETS, 0.0))
            for k in T.BUCKETS:
                d = now[k] - before.get(k, 0.0)
                now[k] -= d
                nxt[k] += d
            for r in ledger.rows[n_rows:]:
                r["fy"] = fy + 1
        shares[s] -= q
        if shares[s] == 0:
            del shares[s]
    EVENTS.append({"date": dt, "overdraft": need, "sold": sold, "charges": charges,
                   "booked_to_next_fy": shift})
    return cash, cum_tc, n_trades


def build_patched():
    src = textwrap.dedent(inspect.getsource(test_exposure.backtest_exposure))
    for name, (anchor, repl) in (("PRE", PATCH_PRE), ("POST", PATCH_POST)):
        if src.count(anchor) != 1:
            raise SystemExit(f"ABORT: patch anchor {name} matched {src.count(anchor)} times, "
                             f"expected 1. test_exposure.backtest_exposure has changed; "
                             f"re-derive the patch.")
        src = src.replace(anchor, repl, 1)
    ns = dict(test_exposure.__dict__)
    ns["_OD_SELL"] = _od_sell
    exec(compile(src, "<overdraft backtest_exposure>", "exec"), ns)
    return ns["backtest_exposure"]


def cagr(eq):
    y = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / y) - 1) * 100)


# naming: axis-free -- one measurement over every universe, arm and profile; each is a row
def main():
    patched = build_patched()
    rows = []
    for tag, u in REGISTRY.items():
        engine_core.set_tradeability(u)
        p = read_table(config.require_cache(u.score_cache, what=tag), parse_dates=["date"])
        px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
        op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
        sc = p.pivot_table(index="date", columns="symbol", values="score")
        bd = u.trading_days(px.index)
        pc, mom20 = precompute(px), px / px.shift(20) - 1
        for arm in arm_reg.ARMS.values():
            for profile in profiles.PROFILES:
                profiles.set_selection(profile)
                try:
                    kw = dict(value_at_open=True, tax_enabled=True, **arm.kwargs,
                              **profiles.cap_kwargs(u))
                    audit = {k: [] for k in KEYS}
                    eq0, *_ = test_exposure.backtest_exposure(px, op, sc, bd, pc, mom20,
                                                              audit=audit, **kw)
                    EVENTS.clear()
                    a1 = {k: [] for k in KEYS}
                    eq1, *_ = patched(px, op, sc, bd, pc, mom20, audit=a1, **kw)
                finally:
                    profiles.set_selection(None)
                cash = pd.DataFrame(audit["summary"]).set_index("date")["cash"]
                neg = cash[cash < 0]
                if not EVENTS and not eq1.equals(eq0):
                    raise SystemExit(f"ABORT: {tag} {arm.name} {profile}: no forced sale, "
                                     f"yet the variant's curve differs from the engine's")
                led = a1["tax"]["ledger"]
                unpaid = sum(T.tax_for_fy(fy, b)["total_tax"] for fy, b in led.realized.items()
                             if fy not in led.assessed)
                rows.append({
                    "universe": tag, "arm": arm.name, "profile": profile,
                    "published_cagr": round(cagr(eq0), 4), "tax_paid_by_selling_cagr": round(cagr(eq1), 4),
                    "change": round(cagr(eq1) - cagr(eq0), 4),
                    "deepest_overdraft": round(float(neg.min()), 2) if len(neg) else 0.0,
                    "deepest_on": str(neg.idxmin().date()) if len(neg) else "",
                    "days_negative": int(len(neg)),
                    "forced_sale_days": len(EVENTS),
                    "sold_rs": round(sum(e["sold"] for e in EVENTS), 2),
                    "sale_charges_rs": round(sum(e["charges"] for e in EVENTS), 2),
                    "sale_tax_left_unpaid_rs": round(unpaid, 2)})
                r = rows[-1]
                print(f"  {tag:<12}{arm.name}  {profile:<9}  overdraft {r['deepest_overdraft']:>13,.2f}  "
                      f"days {r['days_negative']:>3}  CAGR {r['published_cagr']:>8.4f} -> "
                      f"{r['tax_paid_by_selling_cagr']:>8.4f} ({r['change']:+.4f})", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT.with_suffix(".csv"), index=False)
    hit = df[df["days_negative"] > 0]
    L = ["CASH OVERDRAFT ON TAX DAYS -- results/overdraft_measure.py",
         "=" * 88,
         "Tax on, cadence 20, every universe and arm, research and tradeable. Read-only: the",
         "published figures are the engine's; the second CAGR is a variant in which the tax is",
         "paid by selling a pro-rata slice of every holding at the assessment day's open",
         "(usual slippage and charges), with any gain on that sale taxed in the next financial",
         "year. Rows: diagnostics/overdraft_on_tax_day.csv.",
         "",
         f"cells with cash below zero on at least one day: {len(hit)} of {len(df)}",
         f"deepest overdraft: Rs {df['deepest_overdraft'].min():,.2f} "
         f"({df.loc[df['deepest_overdraft'].idxmin(), 'universe']} "
         f"{df.loc[df['deepest_overdraft'].idxmin(), 'arm']} "
         f"{df.loc[df['deepest_overdraft'].idxmin(), 'profile']}, "
         f"{df.loc[df['deepest_overdraft'].idxmin(), 'deepest_on']})",
         f"longest run below zero: {df['days_negative'].max()} sessions in one cell "
         f"(days_negative counts every session below zero over the window)",
         f"CAGR change, paying by selling: {df['change'].min():+.4f} to {df['change'].max():+.4f} points "
         f"(mean {hit['change'].mean() if len(hit) else 0:+.4f} over the overdrawn cells)",
         "",
         f"{'cell':<26}{'deepest Rs':>14}{'on':>12}{'days':>6}{'published':>11}{'by selling':>12}"
         f"{'change':>9}{'sold Rs':>14}"]
    for r in df.itertuples():
        L.append(f"{r.universe + ' ' + r.arm + ' ' + r.profile:<26}{r.deepest_overdraft:>14,.2f}"
                 f"{r.deepest_on:>12}{r.days_negative:>6}{r.published_cagr:>11.4f}"
                 f"{r.tax_paid_by_selling_cagr:>12.4f}{r.change:>+9.4f}{r.sold_rs:>14,.2f}")
    OUT.with_suffix(".txt").write_text("\n".join(L) + "\n")
    print("\n".join(L[:14]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
