"""
drawdown_stop_test.py -- the drawdown stop's edge cases on a synthetic panel.

    ./venv/bin/python drawdown_stop_test.py          # every case, with its log rows
    ./venv/bin/python drawdown_stop_test.py --quiet  # PASS/FAIL lines only

experiments/DRAWDOWN_STOP_PREREG.txt and section 3 of the approved design list how
the stop behaves at its edges. A run on real prices reaches only some of them, so
each one is built here on purpose: twelve symbols, one common price path, scores
fixed by name, and a crash placed on the day the case needs. Each case runs
results/test_exposure.backtest_exposure with an audit dict and asserts on its
stop events, skipped orders and fills. The cases without a cap or tax also run
nautilus/nt_attribution.run, the reference copy nt_verify compares the port with,
and require the same exit and re-entry dates.

    1. exit signal on a rebalance day       the order placed at that close is superseded
    2. exit sale cut by the participation cap   the remainder is held and offered again
    3. no open price on the exit day          the name stays held and is offered again
    4. exit on the tax assessment day         the sale is taxed with its own year
    5. exit on the penultimate and last day   sells at the last open / sells nothing
    6. re-entry where no buy fills            back to waiting, peak not reset
    7. breadth below 0.50                     the arm stays in cash until it recovers

No real data, no cache, nothing written. A second or two. Exit 0 when every case
passes, 1 otherwise.
"""
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results", ROOT / "nautilus"):
    sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd

from arms.registry import DrawdownStop
from engine_core import precompute
from test_exposure import backtest_exposure
import nt_attribution

QUIET = "--quiet" in sys.argv
# 0.15, NOT THE REGISTERED 0.20, which is sealed. The synthetic crashes are 25%, so
# every case triggers as it would at 0.20.
STOP = DrawdownStop(threshold=0.15, cooldown_cycles=1, reentry_breadth=0.50)
REBAL = 5
SYMS = [f"S{k:02d}" for k in range(12)]
WARM = pd.bdate_range("2020-08-03", "2020-12-31")
DATES = pd.bdate_range("2021-01-01", "2021-06-30")


def panel(crash_at, recover_at=None, crash=0.75):
    """Prices: flat to `crash_at` (an index into DATES), then x `crash` on that day,
    drifting down 0.5% a day until `recover_at`, then rising 1% a day."""
    idx = WARM.append(DATES)
    n0 = len(WARM)
    f = np.ones(len(idx))
    for t in range(n0 + crash_at, len(idx)):
        f[t] = f[t - 1] * (crash if t == n0 + crash_at else 0.995)
        if recover_at is not None and t >= n0 + recover_at:
            f[t] = f[t - 1] * 1.01
    px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) for k, s in enumerate(SYMS)}, index=idx)
    op = px.copy()
    sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
    return px, op, sc


def run(px, op, sc, cap=None, vol20=None, tax=False, dates=DATES):
    audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                             "skipped")}
    audit["costs"] = {"fills": [], "days": []}
    eq, *_ = backtest_exposure(px, op, sc, dates, precompute(px), px / px.shift(20) - 1,
                               mode="none", sizing="invvol", drawdown_stop=STOP,
                               audit=audit, rebal=REBAL, participation_cap=cap,
                               vol20=vol20, tax_enabled=tax)
    ev = pd.DataFrame(audit["stop_events"])
    return eq, audit, ev


def reference_events(px, op, sc, dates=DATES):
    out = []
    nt_attribution.run(px, op, sc, dates, precompute(px), px / px.shift(20) - 1,
                       size_at_close=False, value_at_open=True, mode="none",
                       sizing="invvol", rebal=REBAL, drawdown_stop=STOP,
                       stop_events_out=out)
    return out


KEY = ("trigger", "exit fills", "flat", "re-entry order", "re-entry filled",
       "re-entry not filled", "peak reset", "trigger on the last session")


def key_dates(rows):
    return sorted((str(pd.Timestamp(r["date"]).date()), r["event"]) for r in rows
                  if r["event"] in KEY)


def show(title, ev, extra=None):
    if QUIET:
        return
    print(f"\n  {title}")
    cols = ["date", "event", "state", "peak", "equity", "drawdown_pct", "breadth", "detail"]
    for _, r in ev[cols].iterrows():
        print(f"    {str(pd.Timestamp(r['date']).date())}  {r['event']:<27} {r['state']:<12}"
              f" dd {r['drawdown_pct'] if pd.notna(r['drawdown_pct']) else '':>9}"
              f"  breadth {r['breadth'] if pd.notna(r['breadth']) else '':>6}  {r['detail']}")
    for line in extra or []:
        print(f"    {line}")


RESULTS = []


def check(name, ok, why=""):
    RESULTS.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" -- {why}" if why and not ok else ""))


def skipped_on(audit, day, reason=None):
    return [r for r in audit["skipped"] if r["date"] == day
            and (reason is None or r["reason"] == reason)]


def window(ev, first, last):
    d = pd.to_datetime(ev["date"])
    return ev[(d >= first) & (d <= last)]


def case_1():
    k = 30                                   # DATES index 30 is a rebalance day (30 % 5 == 0)
    px, op, sc = panel(k)
    _, audit, ev = run(px, op, sc)
    day = DATES[k]
    sup = [d for d in audit["decisions"] if d["decided_on"] == day]
    show("1. exit signal on a rebalance day", window(ev, day, DATES[k + 1]),
         [f"decision row of {day.date()}: superseded = {sup[0].get('superseded') if sup else None}"])
    names = list(window(ev, day, day)["event"])
    check("1. exit on a rebalance day supersedes that close's order",
          names == ["order superseded", "trigger"] and sup and sup[0].get("superseded") == "drawdown exit",
          f"events {names}")
    check("1. reference copy has the same exit and re-entry dates",
          key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))


def case_2():
    k = 31
    px, op, sc = panel(k)
    fill_day = DATES[k + 1]
    big = {s: {d: 1e9 for d in px.index} for s in SYMS}
    big["S00"][fill_day] = 10.0              # the cap allows 10 shares of S00 that morning
    _, audit, ev = run(px, op, sc, cap=1.0, vol20=big)
    caps = skipped_on(audit, fill_day, "participation cap")
    sells = [t for t in audit["trades"] if t["date"] in (fill_day, DATES[k + 2])
             and t["symbol"] == "S00"]
    show("2. exit sale cut by the participation cap", window(ev, DATES[k], DATES[k + 2]),
         [f"skipped {fill_day.date()}: {c['side']} {c['symbol']} {c['reason']} [{c['detail']}]"
          for c in caps]
         + [f"trade {t['date'].date()}: SELL {t['symbol']} {t['qty']:,} sh at {t['price']:,.2f}"
            for t in sells])
    names = list(ev["event"])
    i = names.index("exit partly filled")
    check("2. a capped exit sale leaves the remainder held and offers it again",
          len(caps) == 1 and names[i + 1] == "exit retried" and "flat" in names[i + 1:i + 4]
          and [t["qty"] for t in sells][0] == 10 and len(sells) == 2,
          f"events {names[i:i + 4]}, sells {[t['qty'] for t in sells]}")


def case_3():
    k = 31
    px, op, sc = panel(k)
    fill_day = DATES[k + 1]
    op.loc[fill_day, "S03"] = np.nan
    _, audit, ev = run(px, op, sc)
    miss = skipped_on(audit, fill_day, "no open price (NaN/<=0)")
    later = [t for t in audit["trades"] if t["symbol"] == "S03" and t["date"] == DATES[k + 2]]
    show("3. no open price on the exit day", window(ev, DATES[k], DATES[k + 2]),
         [f"skipped {fill_day.date()}: {c['side']} {c['symbol']} {c['reason']}" for c in miss]
         + [f"trade {t['date'].date()}: SELL {t['symbol']} {t['qty']:,} sh" for t in later])
    names = list(window(ev, fill_day, DATES[k + 2])["event"])
    check("3. a name with no open stays held and is sold at the next open",
          len(miss) == 1 and len(later) == 1
          and names == ["exit fills", "exit partly filled", "exit retried", "exit fills", "flat"],
          f"events {names}")
    check("3. reference copy has the same exit and re-entry dates",
          key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))


def case_4():
    assess = pd.Timestamp("2021-03-31")      # FY2020-21's assessment day
    k = list(DATES).index(assess) - 1        # trigger the close before, sell on it
    px, op, sc = panel(k, crash=0.75)
    # A GAIN TO TAX: every price is 60% higher from day 10 on, so the exit after the
    # 25% crash still sells above cost and realises a short-term gain.
    n0 = len(WARM)
    px.iloc[n0 + 10:] *= 1.60
    op = px.copy()
    _, audit, ev = run(px, op, sc, tax=True)
    tax_rows = [r for r in audit["skipped"] if r["side"] == "TAX" and r["date"] == assess]
    sells = [t for t in audit["trades"] if t["date"] == assess and t["action"] == "SELL"]
    lots = audit["tax"]["lots"]
    sold = lots[pd.to_datetime(lots["sell_date"]) == assess] if "sell_date" in lots else lots.iloc[0:0]
    show("4. exit on the tax assessment day", window(ev, DATES[k], assess),
         [f"{len(sells)} exit sale(s) on {assess.date()}"]
         + [f"skipped {r['date'].date()}: TAX {r['reason']} [{r['detail']}]" for r in tax_rows])
    check("4. an exit on 31 March is taxed after the day's fills, with its own year",
          len(sells) > 0 and len(tax_rows) == 1 and "after this day's fills" in tax_rows[0]["detail"],
          f"{len(sells)} sales, tax rows {[r['detail'] for r in tax_rows]}")


def case_5():
    n = len(DATES)
    px, op, sc = panel(n - 2)                # trigger at the penultimate close
    _, audit, ev = run(px, op, sc)
    last = DATES[-1]
    sells = [t for t in audit["trades"] if t["date"] == last and t["action"] == "SELL"]
    show("5a. exit triggered on the penultimate day", window(ev, DATES[-2], last),
         [f"{len(sells)} sale(s) at the last open, {last.date()}"])
    names = list(window(ev, DATES[-2], last)["event"])
    check("5a. a trigger at the penultimate close sells at the last open",
          names == ["trigger", "exit fills", "flat"] and len(sells) > 0, f"events {names}")
    px, op, sc = panel(n - 1)                # trigger at the last close
    _, audit, ev = run(px, op, sc)
    sells = [t for t in audit["trades"] if t["date"] == last and t["action"] == "SELL"]
    show("5b. exit triggered on the last day", window(ev, last, last),
         [f"{len(sells)} sale(s) on {last.date()}"])
    names = list(window(ev, last, last)["event"])
    check("5b. a trigger at the last close sells nothing",
          names == ["trigger on the last session"] and not sells, f"events {names}")
    check("5. reference copy has the same exit and re-entry dates",
          key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))


def case_6_7():
    k = 31
    px, op, sc = panel(k, recover_at=k + 25)
    _, audit, ev = run(px, op, sc)
    order = ev[ev["event"] == "re-entry order"]
    waiting = ev[ev["event"] == "waiting"]
    show("7. breadth below 0.50 keeps the arm in cash",
         ev[ev["event"].isin(["flat", "cooldown", "waiting", "re-entry order"])].head(12))
    check("7. breadth below 0.50 holds the arm in cash until breadth recovers",
          len(waiting) >= 2 and (waiting["breadth"] < 0.5).all() and len(order)
          and pd.to_datetime(order["date"]).iloc[0] > pd.to_datetime(waiting["date"]).max()
          and float(order["breadth"].iloc[0]) >= 0.5,
          f"{len(waiting)} waits, first order {list(order['date'][:1])}")
    check("7. reference copy has the same exit and re-entry dates",
          key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))
    first = pd.Timestamp(order["date"].iloc[0])
    fill = DATES[list(DATES).index(first) + 1]
    op2 = op.copy()
    op2.loc[fill, :] = np.nan                # no symbol has an open on the re-entry morning
    _, audit2, ev2 = run(px, op2, sc)
    miss = skipped_on(audit2, fill, "no open price (NaN/<=0)")
    show("6. re-entry where no buy fills", window(ev2, first, DATES[list(DATES).index(first) + 6]),
         [f"skipped {fill.date()}: {len(miss)} BUY order(s), reason no open price"])
    after = window(ev2, fill, DATES[-1])
    names = list(after["event"])
    reset_before = (ev2["event"] == "peak reset") & (pd.to_datetime(ev2["date"]) <= fill)
    check("6. a re-entry with no fill goes back to waiting without a peak reset",
          names[0] == "re-entry not filled" and after.iloc[0]["state"] == "OUT"
          and not reset_before.any() and "re-entry filled" in names,
          f"events {names[:4]}")
    check("6. reference copy has the same exit and re-entry dates",
          key_dates(ev2.to_dict("records")) == key_dates(reference_events(px, op2, sc)))


def main():
    for c in (case_1, case_2, case_3, case_4, case_5, case_6_7):
        c()
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\nRESULT: {'PASS' if not bad else 'FAIL'} -- {len(RESULTS) - len(bad)} of "
          f"{len(RESULTS)} checks" + (f"; failed: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
