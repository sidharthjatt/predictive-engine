"""
dd_overlay_test.py -- the drawdown-limit axis on a synthetic panel.

    ./venv/bin/python dd_overlay_test.py          # every case, with its figures
    ./venv/bin/python dd_overlay_test.py --quiet  # PASS/FAIL lines only

The axis adds the engine's only partial sells and its only top-ups of held names
(results/drawdown_overlay.py). Each case builds a price path that reaches one
behaviour, runs results/test_exposure.backtest_exposure with an explicit
dd_overlay and an audit dict, and asserts on the fills. Every case also passes the
cost trail through results/cost_report.reconcile, which replays cash, charges,
slippage and the tax ledger fill by fill and raises on a paisa of difference.

    1. no drawdown                 no dd fill, equity identical to the axis off
    2. a dip inside the band       no dd fill
    3. a crash                     next-open trims, every name by the same ratio
    4. the recovery                top-ups, every name by the same ratio, back to
                                   within 1 point of the arm's 98%
    5. participation cap on a trim the remainder stays held, k is what filled
    6. no open price on the trim day   that name is skipped, the rest are trimmed
    7. the floor                   invested fraction within the band of F
    8. an overnight gap            the limit is breached and the summary says so
    9. tax on                      trims realise gains, the ledger reconciles, the
                                   marginal tax is positive
   10. refusal with a stop arm

The rebalance cadence is longer than the panel, so the only trades after the first
morning are the overlay's. No real data, nothing written. Exit 0 when every case
passes, 1 otherwise.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results"):
    sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd

import dd_axis
from arms.registry import DrawdownStop
from engine_core import precompute
from test_exposure import backtest_exposure, START_CAPITAL
import cost_report

QUIET = "--quiet" in sys.argv
SYMS = [f"S{k:02d}" for k in range(12)]
WARM = pd.bdate_range("2020-08-03", "2020-12-31")
DATES = pd.bdate_range("2021-01-01", "2021-12-31")
REBAL = 10_000
DD20 = dd_axis.make(20)                      # L 20%, m 5, floor 25%


def panel(path):
    """`path(t)` is the day-t multiplier on the common price, t indexing DATES."""
    idx = WARM.append(DATES)
    n0 = len(WARM)
    f = np.ones(len(idx))
    for t in range(n0, len(idx)):
        f[t] = f[t - 1] * path(t - n0)
    px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) for k, s in enumerate(SYMS)}, index=idx)
    sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
    return px, px.copy(), sc


def run(px, op, sc, dd=DD20, cap=None, vol20=None, tax=False, stop=None):
    audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                             "skipped")}
    audit["costs"] = {"fills": [], "days": []}
    eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                     mode="none", sizing="invvol", audit=audit, rebal=REBAL,
                                     participation_cap=cap, vol20=vol20, tax_enabled=tax,
                                     dd_overlay=dd, drawdown_stop=stop)
    engine_tax = float(audit["tax"]["cum_tax"]) if tax else 0.0
    lots = audit["tax"]["lots"] if tax else None
    cost_report.reconcile(audit["costs"], audit["trades"], list(DATES), float(START_CAPITAL),
                          tc, engine_tax, tax, lots)
    fills = pd.DataFrame(audit["costs"]["fills"])
    return eq, audit, fills


def dd_fills(fills, kind=None):
    if not len(fills):
        return fills
    f = fills[fills["kind"].str.startswith("dd")]
    return f[f["kind"] == kind] if kind else f


def holdings_on(audit, d):
    h = pd.DataFrame(audit["holdings"])
    h = h[h["date"] == d]
    return dict(zip(h["symbol"], h["qty"]))


def proportional(audit, fills, kind):
    """Every dd fill of `kind` on each day resizes its name by the ordered ratio:
    qty == floor(held at the previous close x |1 - r|), r from the order event."""
    orders = [e for e in audit["dd_events"] if e["event"].endswith("order")]
    days = sorted(set(dd_fills(fills, kind)["date"]))
    bad = []
    for d in days:
        i = DATES.get_loc(d)
        prev = DATES[i - 1]
        ev = [e for e in orders if e["date"] == prev][-1]
        r = ev["target_invested_pct"] / ev["invested_pct"]
        held = holdings_on(audit, prev)
        for _, f in dd_fills(fills, kind)[dd_fills(fills, kind)["date"] == d].iterrows():
            want = int(np.floor(held[f["symbol"]] * abs(1 - r)))
            if int(f["qty"]) != want:
                bad.append((d, f["symbol"], int(f["qty"]), want))
    return days, bad


RESULTS = []


def case(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


def crash_path(day=40, crash=0.82, rec_from=None, rec=1.01):
    def p(t):
        if t == day:
            return crash
        if rec_from is not None and t >= rec_from:
            return rec
        return 1.001 if t < day else 0.999
    return p


def main():
    # 1. no drawdown: rising prices, the overlay must be inert
    px, op, sc = panel(lambda t: 1.001)
    eq_on, a1, f1 = run(px, op, sc)
    eq_off, _, _ = run(px, op, sc, dd=None)
    case("1 no drawdown: no dd fill and equity identical to the axis off",
         len(dd_fills(f1)) == 0 and bool((eq_on == eq_off).all()),
         f"dd fills {len(dd_fills(f1))}, max |diff| {float((eq_on - eq_off).abs().max()):.6f}")

    # 2. a 1% dip: E = 5 x (0.99 - 0.80) / 0.99 = 0.96, so k* = 0.96 / 0.98 and the
    #    invested fraction would move about 2 points, inside the 5-point band. Near
    #    a peak E moves about 4 points per 1% of drawdown at m = 1 / L, so a 2% dip
    #    is already outside it.
    px, op, sc = panel(lambda t: 0.995 if t in (30, 31) else 1.0005)
    _, a2, f2 = run(px, op, sc)
    case("2 a 1% dip stays inside the 5-point band", len(dd_fills(f2)) == 0,
         f"worst dd {a2['dd']['worst_dd_pct']:.2f}%, dd fills {len(dd_fills(f2))}")

    # 3. a crash of 18% on day 40: trims at the next open, proportional
    px, op, sc = panel(crash_path())
    _, a3, f3 = run(px, op, sc)
    days, bad = proportional(a3, f3, "dd trim")
    first = DATES[41]
    case("3 crash: trims fill at the next open, every name by the ordered ratio",
         len(days) > 0 and days[0] == first and not bad,
         f"trim days {[str(d.date()) for d in days[:3]]}, mismatches {bad[:3]}")
    s3 = pd.DataFrame(a3["summary"]).set_index("date")
    ev = [e for e in a3["dd_events"] if e["event"] == "trim order"][0]
    W, M = ev["equity"], ev["peak"]
    E = max(0.25, min(1.0, 5 * (W - 0.8 * M) / W))
    case("3 the target exposure is max(F, min(1, m (W - (1 - L) M) / W))",
         abs(ev["limit_exposure_pct"] / 100 - E) < 1e-12,
         f"E {ev['limit_exposure_pct'] / 100:.4f}, recomputed {E:.4f}, invested after "
         f"{s3.loc[first, 'invested_pct']:.2f}%")

    # 4. recovery by three jumps (+25%, +25%, +10%): the limit rises faster than
    #    the drift of the trimmed book, so top-ups fill. A smooth recovery mostly
    #    re-risks by drift alone: the invested fraction rises with prices about as
    #    fast as E does, and the gap stays inside the band.
    px, op, sc = panel(lambda t: {40: 0.82, 60: 1.25, 70: 1.25, 80: 1.10}.get(
        t, 1.001 if t < 40 else 1.0))
    _, a4, f4 = run(px, op, sc)
    days4, bad4 = proportional(a4, f4, "dd top-up")
    s4 = pd.DataFrame(a4["summary"]).set_index("date")
    case("4 recovery: top-ups by the ordered ratio, back to the arm's own level",
         len(days4) >= 2 and not bad4 and a4["dd"]["invested_final_pct"] >= 97
         and s4["invested_pct"].iloc[-1] > 95,
         f"top-up days {len(days4)}, mismatches {bad4[:3]}, "
         f"invested at the end "
         f"{s4['invested_pct'].iloc[-1]:.2f}%")

    # 5. participation cap on the trim: 50 shares a day per name, from day 30 so
    #    the first morning's buys are not cut
    px, op, sc = panel(crash_path())
    vol20 = {s: {d: 500.0 for d in DATES[30:]} for s in SYMS}
    _, a5, f5 = run(px, op, sc, cap=0.10, vol20=vol20)
    t5 = dd_fills(f5, "dd trim")
    capped = [r for r in a5["skipped"] if r["reason"] == "participation cap"
              and r["detail"].startswith("dd trim")]
    first_day = t5[t5["date"] == t5["date"].min()]
    case("5 cap on a trim: each sale is 50 sh, the rest stays held and is re-ordered",
         len(capped) > 0 and (first_day["qty"] == 50).all() and len(set(t5["date"])) > 1,
         f"capped legs {len(capped)}, first-day sizes {sorted(set(first_day['qty']))}, "
         f"trim days {len(set(t5['date']))}")

    # 6. no open on the trim day for S00
    px, op, sc = panel(crash_path())
    op.loc[DATES[41], "S00"] = np.nan
    _, a6, f6 = run(px, op, sc)
    t6 = dd_fills(f6, "dd trim")
    d6 = t6[t6["date"] == DATES[41]]
    skipped = [r for r in a6["skipped"] if r["reason"].startswith("dd trim: no open")]
    case("6 no open price: that name is skipped, the others are trimmed",
         "S00" not in set(d6["symbol"]) and len(d6) > 0 and len(skipped) == 1,
         f"trimmed {len(d6)} names on {DATES[41].date()}, skipped {[r['symbol'] for r in skipped]}")

    # 7. the floor: a 30% crash puts W below the limit; E is held at 25%
    px, op, sc = panel(crash_path(crash=0.70))
    _, a7, f7 = run(px, op, sc)
    s7 = pd.DataFrame(a7["summary"]).set_index("date")
    after = s7.loc[DATES[42]:, "invested_pct"]
    # The floor bounds E. The book itself may drift below it by up to the band
    # before a top-up is ordered.
    case("7 floor: days at the floor counted, invested within the band of F",
         a7["dd"]["days_at_floor"] > 0 and after.min() > 25 - 5 - 0.5,
         f"days at floor {a7['dd']['days_at_floor']}, min invested after the trim "
         f"{after.min():.2f}%")

    # 8. an overnight gap: 15% down, the trim, then a 35% gap the next session
    def gap(t):
        return {40: 0.85, 45: 0.65}.get(t, 1.001 if t < 40 else 1.0)
    px, op, sc = panel(gap)
    _, a8, _ = run(px, op, sc)
    d8 = a8["dd"]
    case("8 gap: the limit is breached and the summary reports it",
         d8["breached"] and d8["breach_points"] > 0 and d8["sessions_below_limit"] > 0,
         f"worst {d8['worst_dd_pct']:.2f}% on {pd.Timestamp(d8['worst_date']).date()}, "
         f"breached by {d8['breach_points']:.2f} points, sessions below {d8['sessions_below_limit']}")

    # 9. tax on: rise 40%, then crash; trims realise gains
    def taxed(t):
        return 1.003 if t < 120 else (0.80 if t == 120 else 1.0)
    px, op, sc = panel(taxed)
    _, a9, f9 = run(px, op, sc, tax=True)
    case("9 tax on: dd trims in the ledger, cost replay reconciles, marginal tax > 0",
         len(dd_fills(f9, "dd trim")) > 0 and a9["dd"]["marginal_tax"] > 0,
         f"dd trims {len(dd_fills(f9, 'dd trim'))}, marginal tax Rs {a9['dd']['marginal_tax']:,.2f}, "
         f"total tax Rs {float(a9['tax']['cum_tax']):,.2f}")

    # 10. refusal with a stop arm
    try:
        run(px, op, sc, stop=DrawdownStop(threshold=0.15, cooldown_cycles=1,
                                          reentry_breadth=0.5))
        ok = False
    except ValueError as e:
        ok = "stop arm" in str(e)
    case("10 the axis is refused on a stop arm", ok)

    n = len(RESULTS)
    print(f"\n  {sum(RESULTS)} of {n} passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
