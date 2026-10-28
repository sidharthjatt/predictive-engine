"""
engine_tests.py -- the twelve synthetic and cache tests, one subcommand each.

    ./venv/bin/python engine_tests.py <case> [the old file's arguments]

    case                   was
    capital_axis           capital_axis_test.py [--quiet]
    dd_overlay             dd_overlay_test.py [--quiet]
    drawdown_stop          drawdown_stop_test.py [--quiet]
    fixed_capital          fixed_capital_test.py [--quiet]
    impact_pcap_axis       impact_pcap_axis_test.py [--quiet]
    tax_rules              tax_rules_test.py [--quiet]
    tax_total              tax_total_test.py [--quiet] [--module PATH]
    tradability_causality  tradability_causality_test.py [--quiet] [--real]
    cache_key              cache_key_test.py
    noise_harness          noise_harness_test.py
    buy_shortfall          (new, 2026-10-27)
    fill_open_sizing       (new, 2026-10-28)
    fill_price             (new, 2026-10-28)

Merged on 2026-10-18. The old files last exist at commit 24614bb. Each old file's
body is the function _<case> below, unchanged apart from one level of indentation
(the inside of multi-line strings is left as it was): its imports, sys.path setup,
warnings filter and constants run only when that case is chosen, as they did when
the file was run on its own. The file's `if __name__ == "__main__":` block is the
last statement of its function. Each function's docstring is the old file's.

ONE CASE PER PROCESS. check_all runs every case as its own subprocess, as it ran
the old files. Do not call two cases in one interpreter: cache_key and
noise_harness change the state of modules they import, and the other cases read
sys.argv for their own flags.
"""
import sys

def _capital_axis():
    """
capital_axis_test.py -- the starting-capital axis on a synthetic panel.

    ./venv/bin/python capital_axis_test.py          # every case, with its figures
    ./venv/bin/python capital_axis_test.py --quiet  # PASS/FAIL lines only

    1. validation: whole rupees, at least Rs 1,00,000
    2. names: "" at the default, "_cap<rupees>" and "@cap<rupees>" otherwise
    3. the default path: unset, and start_capital=1,000,000 passed, give the same curve
    4. the engine starts at the selected capital and reconciles to the paisa
       (cost_report.reconcile replays cash, charges and slippage fill by fill)
    5. the investable buy & hold (bh_held) is bought with the selected capital
    6. the one definition: every START_CAPITAL name is capital_axis.DEFAULT

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results", ROOT / "nautilus"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import capital_axis
    import cost_report
    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    SYMS = [f"S{k:02d}" for k in range(12)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def panel():
        idx = WARM.append(DATES)
        f = np.cumprod(np.r_[1.0, np.full(len(idx) - 1, 1.0007)])
        px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) * (1 + 0.002 * np.sin(np.arange(len(idx)) / (k + 3)))
                           for k, s in enumerate(SYMS)}, index=idx)
        sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
        return px, px.copy(), sc


    def run(px, op, sc, **kw):
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=20,
                                         participation_cap=None, drawdown_stop=None, **kw)
        return eq, tc, audit


    def main():
        # 1 ----------------------------------------------------------------------
        bad = []
        for v in (99_999, 2.5, 0, -1):
            try:
                capital_axis.set_selection(v)
                bad.append(v)
            except ValueError:
                pass
        capital_axis.set_selection(100_000)
        ok_min = capital_axis.selected() == 100_000
        capital_axis.set_selection(None)
        case("1 validation: below Rs 1 lakh or not whole rupees is refused", not bad and ok_min,
             f"accepted wrongly: {bad}")

        # 2 ----------------------------------------------------------------------
        names_default = (capital_axis.suffix(), capital_axis.segment(), capital_axis.label())
        capital_axis.set_selection(5_000_000)
        names_on = (capital_axis.suffix(), capital_axis.segment())
        capital_axis.set_selection(None)
        case("2 names", names_default == ("", "", "") and names_on == ("_cap5000000", "@cap5000000"),
             f"default {names_default}, at 5,000,000 {names_on}")

        # 3 ----------------------------------------------------------------------
        px, op, sc = panel()
        e0, _, _ = run(px, op, sc)
        e1, _, _ = run(px, op, sc, start_capital=1_000_000)
        case("3 default path: unset equals start_capital=1,000,000", bool((e0 == e1).all()))

        # 4 ----------------------------------------------------------------------
        capital_axis.set_selection(5_000_000)
        try:
            e5, tc5, a5 = run(px, op, sc)
            cost_report.reconcile(a5["costs"], a5["trades"], list(DATES), 5_000_000.0, tc5, 0.0, False)
            ok = abs(a5["costs"]["days"][0]["cash_open"] - 5_000_000) < 0.005
            case("4 engine starts at the selected capital and reconciles", ok,
                 f"first cash {a5['costs']['days'][0]['cash_open']:,.2f}, final {e5.iloc[-1]:,.2f} "
                 f"(Rs 10 lakh run final {e0.iloc[-1]:,.2f})")
        finally:
            capital_axis.set_selection(None)

        # 5 ----------------------------------------------------------------------
        import bh_held
        bd = DATES
        r1 = bh_held.held_lots(px, op, bd)
        capital_axis.set_selection(3_000_000)
        try:
            r3 = bh_held.held_lots(px, op, bd)
        finally:
            capital_axis.set_selection(None)
        q1 = sum(q for q, _ in r1["shares"].values())
        q3 = sum(q for q, _ in r3["shares"].values())
        case("5 buy & hold is bought with the selected capital", 2.9 * q1 < q3 < 3.1 * q1,
             f"shares at Rs 10 lakh {q1:,}, at Rs 30 lakh {q3:,}")

        # 6 ----------------------------------------------------------------------
        import test_exposure, engine_core, engine_v2_final, make_daily_log, nt_attribution, nt_run
        vals = {m.__name__: m.START_CAPITAL for m in (test_exposure, engine_core, engine_v2_final,
                                                      make_daily_log, nt_attribution, nt_run)}
        case("6 every START_CAPITAL is capital_axis.DEFAULT",
             all(v == capital_axis.DEFAULT for v in vals.values()), str(vals))

        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _dd_overlay():
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

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _drawdown_stop():
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
                           mode="none",
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

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _fixed_capital():
    """
fixed_capital_test.py -- the fixed-capital axis (fixed_axis.py).

    ./venv/bin/python fixed_capital_test.py          # every case, with its figures
    ./venv/bin/python fixed_capital_test.py --quiet  # PASS/FAIL lines only

    1. names and refusals: "" and "_fixed" / "@fixed"; the engine and run.py refuse
       the axis with --dd and with the stop arms v5 and v6
    2. the default path: fixed_capital unset and fixed_capital=False give the same run
    a. purchases never lift invested value above the book: on every execution day,
       after all fills, valued at that open, held value <= max(book, held value
       before that day's buys). nifty200, pit, tradeable, v1 to v4, tax off and on
   b1. nifty500 v4, pit, tradeable, tax off and on: the fixed and compounded runs
       are identical, every fill, cash and equity value, up to the session before
       the first execution day whose open equity is above the base. That day is
       found from the run.
   b2. a synthetic falling panel on which equity never passes the base: the two
       runs are identical over the whole window, v1 and v4, tax off and on
    c. every run above reconciles from its own fills: end equity = base + realised
       P&L + final unrealised P&L - charges - tax, within Rs 1. Realised P&L is on
       average cost; prices and charges come from the run's full-precision cost
       trail (audit["costs"]). The yearly table is checked as well, as a format
       check only: base + the sum of the yearly rupee P&L = end equity, in Decimal.

The real-data cases read the cached pit score panels (cache/), as the engines do;
nothing under data/ is read or written by this file, and nothing is written at all.
Exit 0 when every case passes, 1 otherwise.
"""
    import contextlib
    import io
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results", ROOT / "nautilus", ROOT / "tools"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import fixed_axis
    import fixed_capital as fc
    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    BASE = 1_000_000.0
    TOL_RS = 1.0          # case c
    TOL_BOOK = 0.01       # case a: rupees of float rounding in a sum over held names


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
              flush=True)


    def blank():
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        a["costs"] = {"fills": [], "days": []}
        return a


    # ---------------------------------------------------------------------------
    # case c: reconcile a run from its own fills
    # ---------------------------------------------------------------------------
    def reconcile(audit, eq, px, base):
        """(gap in rupees, realised, unrealised, charges, tax) for one run."""
        held, cost = {}, {}
        realised = charges = 0.0
        for f in audit["costs"]["fills"]:
            s, q, p = f["symbol"], f["qty"], f["fill_price"]
            charges += f["charges"]
            if f["side"] == "BUY":
                cost[s] = cost.get(s, 0.0) + q * p
                held[s] = held.get(s, 0) + q
            else:
                avg = cost[s] / held[s]
                realised += q * (p - avg)
                cost[s] -= q * avg
                held[s] -= q
                if held[s] == 0:
                    del held[s], cost[s]
        last = px.loc[eq.index[-1]]
        unrealised = sum(q * float(last[s]) - cost[s] for s, q in held.items()
                         if not np.isnan(last.get(s, np.nan)))
        tax = float(audit["tax"]["cum_tax"]) if "tax" in audit else 0.0
        gap = base + realised + unrealised - charges - tax - float(eq.iloc[-1])
        return gap, realised, unrealised, charges, tax


    RECONCILED = []


    def check_c(label, audit, eq, px, base=BASE):
        gap, r, u, c, t = reconcile(audit, eq, px, base)
        fmt_ok = fc.yearly_sum_check(eq, base)
        RECONCILED.append((label, abs(gap) <= TOL_RS and fmt_ok, gap, r, u, c, t, fmt_ok))


    # ---------------------------------------------------------------------------
    # real-data cells
    # ---------------------------------------------------------------------------
    class Cell:
        """One pit, tradeable universe, loaded as run.py --survivorship pit
    --profile tradeable loads it (tools/pit_noise_band.select_pit)."""

        def __init__(self, tag):
            import config
            import profiles
            from config import read_table
            with contextlib.redirect_stdout(io.StringIO()):
                import pit_noise_band
                self.u = u = pit_noise_band.select_pit(tag)
                p = read_table(config.require_cache(u.score_cache, what=f"{tag} pit"),
                               parse_dates=["date"])
            self.px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
            self.op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
            self.sc = p.pivot_table(index="date", columns="symbol", values="score")
            self.bd = u.trading_days(self.px.index)
            self.pc = precompute(self.px)
            self.mom20 = self.px / self.px.shift(20) - 1
            with contextlib.redirect_stdout(io.StringIO()):
                self.capkw = profiles.cap_kwargs(u)

        def run(self, arm, tax, fixed):
            import arms.registry as ar
            a = ar.ARMS[arm]
            audit = blank()
            with contextlib.redirect_stdout(io.StringIO()):
                eq, tc, n, _ = backtest_exposure(
                    self.px, self.op, self.sc, self.bd, self.pc, self.mom20, rebal=20, tax_enabled=tax, audit=audit,
                    mode=a.mode, sizing=a.sizing, drawdown_stop=None, dd_overlay=None,
                    fixed_capital=fixed, start_capital=int(BASE), **self.capkw)
            return eq, audit


    def case_a():
        C = Cell("nifty200")
        worst, n_days, n_res, n_short = [], 0, 0, 0
        for arm in ("v1", "v2", "v3", "v4"):
            for tax in (False, True):
                eq, au = C.run(arm, tax, True)
                rows = au["fixed"]
                over = [r for r in rows
                        if r["held_after"] > max(r["book"], r["held_before_buys"]) + TOL_BOOK]
                n_days += len(rows)
                n_res += sum(1 for r in rows if r["reserve"] > 0)
                n_short += sum(1 for s in au["skipped"] if "fixed-capital reserve" in s["detail"])
                margin = max(r["held_after"] - max(r["book"], r["held_before_buys"]) for r in rows)
                worst.append((arm, tax, len(over), margin))
                case(f"a nifty200 pit tradeable {arm} tax {'on' if tax else 'off'}: purchases "
                     f"never lift invested value above the book", not over and len(rows) > 0,
                     f"{len(rows)} execution days, {len(over)} over; largest held_after - "
                     f"max(book, held before) Rs {margin:,.2f}; reserve > 0 on "
                     f"{sum(1 for r in rows if r['reserve'] > 0)} days")
                check_c(f"nifty200 {arm} tax {'on' if tax else 'off'} fixed", au, eq, C.px)
        case("a the reserve bites: some day holds profit back and some buy is refused for it",
             n_res > 0 and n_short > 0,
             f"{n_res} execution days with a reserve, {n_short} buys skipped because of it, "
             f"over {n_days} execution days in 8 runs")


    def _first_above(rows, base):
        for r in rows:
            if r["port_val"] > base:
                return pd.Timestamp(r["date"])
        return None


    def _same_prefix(e0, a0, e1, a1, cut):
        """Every fill, every day's cash and every equity value before `cut`."""
        pre = e0.index < cut
        eq_ok = bool((e0[pre].to_numpy() == e1[pre].to_numpy()).all())
        f0 = [f for f in a0["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
        f1 = [f for f in a1["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
        d0 = [d for d in a0["costs"]["days"] if pd.Timestamp(d["date"]) < cut]
        d1 = [d for d in a1["costs"]["days"] if pd.Timestamp(d["date"]) < cut]
        return eq_ok and f0 == f1 and d0 == d1, int(pre.sum()), len(f0)


    def case_b1():
        C = Cell("nifty500")
        for tax in (False, True):
            e0, a0 = C.run("v4", tax, False)
            e1, a1 = C.run("v4", tax, True)
            cut = _first_above(a1["fixed"], BASE)
            if cut is None:
                case(f"b1 nifty500 v4 tax {'on' if tax else 'off'}", False,
                     "open equity never passed the base; the case has no cut")
                continue
            same, n_days, n_fills = _same_prefix(e0, a0, e1, a1, cut)
            after = int((e0[e0.index >= cut] != e1[e1.index >= cut]).sum())
            n_exec = sum(1 for r in a1["fixed"] if pd.Timestamp(r["date"]) < cut)
            case(f"b1 nifty500 pit tradeable v4 tax {'on' if tax else 'off'}: identical up to "
                 f"the session before {cut.date()}", same and n_days > 0,
                 f"{n_days} sessions, {n_exec} execution days, {n_fills} fills identical; "
                 f"{after} of {int((e0.index >= cut).sum())} later sessions differ")
            check_c(f"nifty500 v4 tax {'on' if tax else 'off'} compounded", a0, e0, C.px)
            check_c(f"nifty500 v4 tax {'on' if tax else 'off'} fixed", a1, e1, C.px)


    # ---------------------------------------------------------------------------
    # synthetic panels
    # ---------------------------------------------------------------------------
    SYMS = [f"S{k:02d}" for k in range(40)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")


    def falling_panel():
        idx = WARM.append(DATES)
        rng = np.random.default_rng(7)
        out = {}
        for k, s in enumerate(SYMS):
            r = -0.0012 - 0.00002 * k + 0.004 * rng.standard_normal(len(idx))
            out[s] = 100.0 * (1 + 0.02 * k) * np.cumprod(1 + r)
        px = pd.DataFrame(out, index=idx)
        op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
        # Scores redrawn every session, so each rebalance turns the book over.
        sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=SYMS)
        return px, op, sc


    def synth_run(px, op, sc, mode, sizing, tax, fixed):
        audit = blank()
        kw = {} if fixed is None else {"fixed_capital": fixed}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode=mode, sizing=sizing, audit=audit, rebal=20,
                                         participation_cap=None, drawdown_stop=None,
                                         dd_overlay=None, tax_enabled=tax,
                                         start_capital=int(BASE), **kw)
        return eq, audit


    def case_b2():
        px, op, sc = falling_panel()
        for mode, sizing, arm in (("none", "invvol", "v1"), ("breadth", "provol", "v4")):
            for tax in (False, True):
                e0, a0 = synth_run(px, op, sc, mode, sizing, tax, False)
                e1, a1 = synth_run(px, op, sc, mode, sizing, tax, True)
                never = (all(r["port_val"] <= BASE for r in a1["fixed"])
                         and bool((e1 <= BASE).all()))
                same, n_days, n_fills = _same_prefix(e0, a0, e1, a1, DATES[-1] + pd.Timedelta(days=1))
                case(f"b2 synthetic falling panel {arm} tax {'on' if tax else 'off'}: equity never "
                     f"passes the base and the two runs are identical", never and same and n_fills > 0,
                     f"{n_days} sessions, {n_fills} fills; end equity Rs {e1.iloc[-1]:,.2f}; "
                     f"highest open equity Rs {max(r['port_val'] for r in a1['fixed']):,.2f}")
                check_c(f"synthetic {arm} tax {'on' if tax else 'off'} compounded", a0, e0, px)
                check_c(f"synthetic {arm} tax {'on' if tax else 'off'} fixed", a1, e1, px)


    def case_names_refusals():
        d = (fixed_axis.suffix(), fixed_axis.segment(), fixed_axis.label())
        fixed_axis.set_selection(True)
        on = (fixed_axis.suffix(), fixed_axis.segment())
        fixed_axis.set_selection(None)
        case("1 names", d == ("", "", "") and on == ("_fixed", "@fixed"), f"off {d}, on {on}")

        px, op, sc = falling_panel()
        import arms.registry as ar
        import dd_axis
        refused = []
        for name, stop, dd in (("drawdown_stop", ar.DrawdownStop(threshold=0.5), None),
                               ("dd_overlay", None, dd_axis.make(20))):
            try:
                backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                  mode="none", rebal=20, participation_cap=None,
                                  fixed_capital=True, drawdown_stop=stop, dd_overlay=dd)
            except ValueError:
                refused.append(name)
        import run
        cli = []
        for argv in (["--fixed-capital", "--dd", "20", "--list"],
                     ["--fixed-capital", "--arm", "v5", "--list"]):
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    run.main(argv)
            except SystemExit as e:
                if e.code == 2 and "--fixed-capital cannot run with" in err.getvalue():
                    cli.append(argv[1])
        # run.main records the selections it parsed before refusing; restore them.
        fixed_axis.set_selection(None)
        dd_axis.set_selection(None)
        case("1 refusals: the engine and run.py refuse the axis with --dd and the stop arms",
             refused == ["drawdown_stop", "dd_overlay"] and cli == ["--dd", "--arm"],
             f"engine refused {refused}; run.py refused {cli}")


    def case_default():
        px, op, sc = falling_panel()
        e0, a0 = synth_run(px, op, sc, "none", "invvol", False, None)
        e1, a1 = synth_run(px, op, sc, "none", "invvol", False, False)
        case("2 default path: fixed_capital unset equals fixed_capital=False",
             bool((e0.to_numpy() == e1.to_numpy()).all()) and a0["costs"] == a1["costs"]
             and "fixed" not in a0)


    def main():
        case_names_refusals()
        case_default()
        case_b2()
        case_a()
        case_b1()
        for label, ok, gap, r, u, c, t, fmt_ok in RECONCILED:
            case(f"c {label}: end equity = base + realised + unrealised - charges - tax", ok,
                 f"gap Rs {gap:+.4f}; realised {r:,.2f}, unrealised {u:,.2f}, charges "
                 f"{c:,.2f}, tax {t:,.2f}; yearly table sums to end equity: {fmt_ok}")
        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _impact_pcap_axis():
    """
impact_pcap_axis_test.py -- the market-impact and participation-cap axes on a
synthetic panel.

    ./venv/bin/python impact_pcap_axis_test.py          # every case, with its figures
    ./venv/bin/python impact_pcap_axis_test.py --quiet  # PASS/FAIL lines only

    1. validation: k below 0 and a cap at or below 0 are refused; k 0 is the default
    2. names: "" at the defaults, "_impact0p003" / "@impact0p003" and
       "_pcap0p1" / "@pcap0p1" otherwise; --cap at the profile's own value is ""
    3. the research profile refuses a non-zero k and any cap, in check_profile and
       in profiles.cap_kwargs
    4. profiles.participation_cap: the profile's value, or --cap's under tradeable
    5. the default path: impact_k unset and impact_k=None give the same curve, and
       the cost trail carries no impact keys
    6. with impact on, every fill is slippage.impact on top of the flat rate, the
       run reconciles to the paisa, and impact is reported apart from slippage:
       flat slippage is exactly reference x SLIPPAGE x qty, and gross profit
       includes impact
    7. the summary block prints an impact row and summary_figures reads it back

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
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

    import cost_report
    import impact_axis
    import pcap_axis
    import profiles
    import slippage
    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    SYMS = [f"S{k:02d}" for k in range(12)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")
    K = 0.003


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def panel():
        idx = WARM.append(DATES)
        f = np.cumprod(np.r_[1.0, np.full(len(idx) - 1, 1.0007)])
        px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) * (1 + 0.002 * np.sin(np.arange(len(idx)) / (k + 3)))
                           for k, s in enumerate(SYMS)}, index=idx)
        sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
        # a median volume on every date of the window, different per symbol
        vol20 = {s: {d: 20_000.0 + 1_000.0 * k for d in DATES} for k, s in enumerate(SYMS)}
        return px, px.copy(), sc, vol20


    def run(px, op, sc, **kw):
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=20,
                                         drawdown_stop=None, **kw)
        return eq, tc, audit


    def reset():
        impact_axis.set_selection(None)
        pcap_axis.set_selection(None)
        profiles.set_selection(None)


    def main():
        # 1 ----------------------------------------------------------------------
        bad = []
        for v in (-0.001, float("nan")):
            try:
                impact_axis.set_selection(v)
                bad.append(("impact", v))
            except ValueError:
                pass
        for v in (0, -0.5):
            try:
                pcap_axis.set_selection(v)
                bad.append(("cap", v))
            except ValueError:
                pass
        impact_axis.set_selection(0)
        zero_is_default = impact_axis.is_default() and impact_axis.impact_k() is None
        reset()
        case("1 validation: k < 0 and cap <= 0 refused; k 0 is the default",
             not bad and zero_is_default, f"accepted wrongly: {bad}")

        # 2 ----------------------------------------------------------------------
        profiles.set_selection("tradeable")
        names_default = (impact_axis.suffix(), impact_axis.segment(), pcap_axis.suffix(),
                         pcap_axis.segment())
        impact_axis.set_selection(K)
        pcap_axis.set_selection(0.1)
        names_on = (impact_axis.suffix(), impact_axis.segment(), pcap_axis.suffix(),
                    pcap_axis.segment())
        pcap_axis.set_selection(1.0)
        own_cap = pcap_axis.suffix()
        reset()
        case("2 names", names_default == ("", "", "", "")
             and names_on == ("_impact0p003", "@impact0p003", "_pcap0p1", "@pcap0p1") and own_cap == "",
             f"default {names_default}, on {names_on}, --cap 1.0 under tradeable {own_cap!r}")

        # 3 ----------------------------------------------------------------------
        refused = []
        impact_axis.set_selection(K)
        for what, fn in (("impact check_profile", impact_axis.check_profile),
                         ("cap_kwargs", lambda: profiles.cap_kwargs(None))):
            try:
                fn()
            except ValueError:
                refused.append(what)
        reset()
        pcap_axis.set_selection(0.1)
        try:
            pcap_axis.check_profile()
        except ValueError:
            refused.append("cap check_profile")
        reset()
        case("3 research refuses --impact and --cap", len(refused) == 3, f"refused: {refused}")

        # 4 ----------------------------------------------------------------------
        profiles.set_selection("tradeable")
        own = profiles.participation_cap()
        pcap_axis.set_selection(0.1)
        over = profiles.participation_cap()
        reset()
        case("4 participation_cap: profile's 1.0, --cap's 0.1", own == 1.0 and over == 0.1,
             f"own {own}, with --cap 0.1 {over}")

        # 5 ----------------------------------------------------------------------
        px, op, sc, vol20 = panel()
        e0, _, a0 = run(px, op, sc, participation_cap=1.0, vol20=vol20)
        e1, _, _ = run(px, op, sc, participation_cap=1.0, vol20=vol20, impact_k=None)
        keys = set().union(*(r.keys() for r in a0["costs"]["fills"]))
        case("5 default path unchanged, no impact keys in the cost trail",
             bool((e0 == e1).all()) and "impact_median" not in keys
             and "impact_rs" not in cost_report.fills_frame(a0["costs"]).columns)

        # 6 ----------------------------------------------------------------------
        eK, tcK, aK = run(px, op, sc, participation_cap=1.0, vol20=vol20, impact_k=K)
        fills, lots, years, days = cost_report.reconcile(aK["costs"], aK["trades"], list(DATES),
                                                         1_000_000.0, tcK, 0.0, False)
        want = [slippage.impact(int(r.qty), vol20[r.symbol][r.date], K) for r in fills.itertuples()]
        rate_ok = np.allclose(fills["impact_rate"], want, rtol=0, atol=1e-15)
        # The fill is rounded to the paisa, so the flat part carries up to half a
        # paisa a share of rounding.
        flat = fills["reference_price"] * slippage.SLIPPAGE * fills["qty"]
        flat_ok = bool((np.abs(fills["slippage_rs"] - flat) <= 0.005 * fills["qty"] + 1e-6).all())
        S = cost_report.strategy_totals(1_000_000.0, float(eK.iloc[-1]), fills, years)
        gross_ok = abs(S["gross"] - (S["final"] - 1_000_000.0 + S["charges"] + S["slippage"]
                                     + S["impact"] + S["tax"])) < 0.005
        case("6 impact on: fills reconcile, impact split from flat slippage",
             rate_ok and flat_ok and gross_ok and S["impact"] > 0 and eK.iloc[-1] < e0.iloc[-1],
             f"impact Rs {S['impact']:,.2f}, flat slippage Rs {S['slippage']:,.2f}, "
             f"final Rs {eK.iloc[-1]:,.2f} against Rs {e0.iloc[-1]:,.2f} without")

        # 7 ----------------------------------------------------------------------
        lines = cost_report.summary_block("synthetic v1", "tradeable", False, 20, 1_000_000.0, eK,
                                          fills, years, days, None)
        got = cost_report.summary_figures("\n".join(lines))
        case("7 summary prints impact and reads it back",
             got.get("strategy/impact") == f"{S['impact']:,.2f}",
             f"printed {got.get('strategy/impact')}")

        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _tax_rules():
    """
tax_rules_test.py -- the tax rules of 2026-10-14, each on a hand-worked case.

    ./venv/bin/python tax_rules_test.py          # every case, with its arithmetic
    ./venv/bin/python tax_rules_test.py --quiet  # PASS/FAIL lines only

results/tax_util.py charges capital-gains tax on listed equity as the Income-tax
Act does for s.111A/112A, with these rules added on 2026-10-14:

    holding period   long-term only when held more than twelve calendar months
    within a year    a net short-term loss is set off against long-term gains
    carry-forward    a net short-term loss for up to 8 years against later short-
                     and long-term gains; a net long-term loss for up to 8 years
                     against later long-term gains only; oldest first; before the
                     LTCG exemption
    cess             4% on the tax

Each case below states its arithmetic and is checked to the paisa (0.005). The
last case runs the same years through tax_util.Ledger, the class the engine uses,
so the in-loop path is checked as well as the function. No data, nothing written.
Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    sys.path.insert(0, str(ROOT / "results"))

    import pandas as pd

    import tax_util as T

    QUIET = "--quiet" in sys.argv
    PAISA = 0.005
    RESULTS = []


    def B(**kw):
        b = dict.fromkeys(T.BUCKETS, 0.0)
        b.update({k: float(v) for k, v in kw.items()})
        return b


    def case(name, got, want, how):
        ok = abs(got - want) < PAISA
        RESULTS.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got:,.2f} (hand-worked {want:,.2f})"
              + ("" if QUIET else f"\n          {how}"))


    def years(by_fy):
        return T.assess_years(by_fy)


    def main():
        # 1. cess on a plain short-term gain
        t = T.tax_for_fy(2025, B(short_new=10_000))
        case("1 cess", t["total_tax"], 2_080.00,
             "10,000 x 20% = 2,000; cess 4% = 80; 2,080")

        # 2. within a year: a net short-term loss against a long-term gain, before the exemption
        t = T.tax_for_fy(2021, B(short_old=-30_000, long_old=150_000))
        case("2 short loss against this year's long gain", t["total_tax"], 2_080.00,
             "150,000 - 30,000 = 120,000; less exemption 1,00,000 = 20,000 x 10% = 2,000; +4% = 2,080")

        # 3. carry-forward of a short loss against a later short gain
        y = years({2020: B(short_old=-10_000), 2021: B(short_old=30_000)})
        case("3 short loss carried to a later short gain", y[2021]["total_tax"], 3_120.00,
             "FY2021: 30,000 - 10,000 brought forward = 20,000 x 15% = 3,000; +4% = 3,120")

        # 4. carry-forward of a short loss against a later long gain, before the exemption
        y = years({2020: B(short_old=-50_000), 2021: B(long_old=200_000)})
        case("4 short loss carried to a later long gain", y[2021]["total_tax"], 5_200.00,
             "200,000 - 50,000 = 150,000; less 1,00,000 = 50,000 x 10% = 5,000; +4% = 5,200")

        # 5. a long loss is not set off against short gains
        y = years({2020: B(long_old=-40_000), 2021: B(short_old=40_000, long_old=120_000)})
        case("5 long loss carried: long gains only", y[2021]["total_tax"], 6_240.00,
             "short 40,000 x 15% = 6,000 (the long loss cannot touch it); long 120,000 - "
             "40,000 = 80,000 < 1,00,000, nil; 6,000 + 4% = 6,240")

        # 6. eight years and no more
        y = years({2015: B(short_old=-10_000), 2023: B(short_old=10_000)})
        case("6a a loss usable in its 8th year", y[2023]["total_tax"], 0.00,
             "FY2015 loss, FY2023 gain (8 years on): 10,000 - 10,000 = 0")
        y = years({2015: B(short_old=-10_000), 2024: B(short_new=10_000)})
        case("6b a loss expired in its 9th year", y[2024]["total_tax"], 2_080.00,
             "FY2015 loss expired by FY2024: 10,000 x 20% = 2,000; +4% = 2,080")

        # 7. oldest loss first
        y = years({2020: B(short_old=-5_000), 2021: B(short_old=-5_000),
                   2029: B(short_new=10_000)})
        case("7 oldest loss first, and expiry by year of origin", y[2029]["total_tax"], 1_040.00,
             "FY2020's 5,000 expired by FY2029; FY2021's 5,000 is usable: 10,000 - 5,000 = "
             "5,000 x 20% = 1,000; +4% = 1,040")

        # 8. a partly used loss carries its remainder
        y = years({2020: B(short_old=-30_000), 2021: B(short_old=10_000),
                   2022: B(short_old=50_000)})
        case("8a remainder after partial use, FY2021", y[2021]["total_tax"], 0.00,
             "10,000 - 10,000 of the 30,000 = 0; 20,000 left")
        case("8b remainder after partial use, FY2022", y[2022]["total_tax"], 4_680.00,
             "50,000 - 20,000 = 30,000 x 15% = 4,500; +4% = 4,680")

        # 9. holding period by calendar months
        for buy, sell, want in (("2023-01-31", "2024-01-31", 0.0), ("2023-01-31", "2024-02-01", 1.0),
                                ("2023-03-01", "2024-02-29", 0.0), ("2023-03-01", "2024-03-02", 1.0)):
            got = 1.0 if T.is_long_term(pd.Timestamp(buy), pd.Timestamp(sell)) else 0.0
            case(f"9 bought {buy}, sold {sell}: long", got, want,
                 "long-term only when sold after the buy date plus 12 calendar months")

        # 10. the engine's Ledger, in its own order, against the function
        dates = pd.bdate_range("2020-04-01", "2023-06-30")
        led = T.Ledger(dates)
        led.buy("A", 100, 100.0, pd.Timestamp("2020-05-04"))
        led.sell("A", 100, 70.0, pd.Timestamp("2020-06-01"))      # FY2020 short -3,000
        led.buy("B", 100, 100.0, pd.Timestamp("2021-05-03"))
        led.sell("B", 100, 150.0, pd.Timestamp("2021-06-01"))     # FY2021 short +5,000
        paid = 0.0
        for d in dates:
            paid += led.due_on(d) + led.due_on(d, after_fills=True)
        case("10 the Ledger carries the loss forward", paid, 312.00,
             "FY2020: -3,000, nil, carried; FY2021 (sold before 2024-07-23, 15%): "
             "5,000 - 3,000 = 2,000 x 15% = 300; +4% = 312")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    rc = main()
    print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
    sys.exit(rc)


def _tax_total():
    """
tax_total_test.py -- the COSTS block's tax figures against what cash paid.

    ./venv/bin/python tax_total_test.py                    # every case, with its figures
    ./venv/bin/python tax_total_test.py --quiet            # PASS/FAIL lines only
    ./venv/bin/python tax_total_test.py --module FILE.py   # test another copy of cost_report

A synthetic tax-on run with gains, reconciled by results/cost_report.py, then its
summary block read back as printed:

    1. the printed tax total equals COST_TAX_YEARS total_tax summed and the ledger's
       final cum_tax, within Rs 0.01
    2. short-term + long-term + cess, as printed, equal the printed tax total
    3. the printed gross profit is final equity - starting capital + charges +
       slippage + the tax total
    4. the per-year table's short tax, long tax and cess add up to the tax total
    5. the buy & hold sold on the last day: short + long + cess = its tax total
    6. cost_report.check_tax_total refuses a block whose tax total leaves the cess out

The block is parsed here with its own regular expressions, not with cost_report's
summary_figures, so the test reads what a person reads. --module points it at any
copy of cost_report.py: the copy at commit 6ab7c55, from before the fix, fails 1 to 5.
No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import importlib.util
    import re
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    BASE = 1_000_000.0
    SYMS = [f"S{k:02d}" for k in range(30)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2022-06-30")


    def load_cost_report():
        if "--module" in sys.argv:
            path = Path(sys.argv[sys.argv.index("--module") + 1]).resolve()
            spec = importlib.util.spec_from_file_location("cost_report_under_test", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, str(path)
        import cost_report
        return cost_report, "results/cost_report.py"


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def panel():
        idx = WARM.append(DATES)
        rng = np.random.default_rng(11)
        r = 0.0012 + 0.006 * rng.standard_normal((len(idx), len(SYMS)))
        px = pd.DataFrame(100.0 * np.cumprod(1 + r, axis=0), index=idx, columns=SYMS)
        op = px.shift(1).fillna(px)
        # Scores redrawn every session, so each rebalance sells and realises gains.
        sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=SYMS)
        return px, op, sc


    def rs(text, label):
        """The rupee figure of the first block row named `label`, as printed."""
        m = re.search(rf"^  {re.escape(label)}\s+([-\d,]+\.\d\d)", text, re.M)
        return float(m.group(1).replace(",", "")) if m else None


    def main():
        cr, where = load_cost_report()
        print(f"  cost_report under test: {where}")
        px, op, sc = panel()
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=20,
                                         participation_cap=None, drawdown_stop=None, dd_overlay=None,
                                         fixed_capital=False, tax_enabled=True,
                                         start_capital=int(BASE))
        cum_tax = float(audit["tax"]["cum_tax"])
        fills, lots, years, days = cr.reconcile(audit["costs"], audit["trades"], list(DATES), BASE,
                                                tc, cum_tax, True, audit["tax"]["lots"])
        bh = cr.bh_costs(px, op, DATES, BASE, True)
        lines = cr.summary_block("synthetic v1", "research", True, 20, BASE, eq, fills, years, days, bh)
        text = "\n".join(lines)
        total_tax = float(years["total_tax"].sum())
        cess_due = float(years["cess"].sum())

        tax = rs(text, "tax, total")
        case("1 printed tax total = COST_TAX_YEARS total_tax summed = ledger cum_tax, within Rs 0.01",
             tax is not None and abs(tax - total_tax) <= 0.01 and abs(tax - cum_tax) <= 0.01,
             f"printed {tax:,.2f}; total_tax {total_tax:,.2f}; cum_tax {cum_tax:,.2f}; "
             f"cess due {cess_due:,.2f}")

        st, lt, ce = rs(text, "  short-term"), rs(text, "  long-term"), rs(text, "  cess")
        parts = (st or 0.0) + (lt or 0.0) + (ce or 0.0)
        case("2 short-term + long-term + cess = tax total, as printed",
             ce is not None and tax is not None and abs(parts - tax) <= 0.02,
             f"{st} + {lt} + {ce} = {parts:,.2f} against {tax}")

        m = re.search(r"gross profit Rs ([-\d,.]+) =", text)
        gross = float(m.group(1).replace(",", ""))
        want = float(eq.iloc[-1]) - BASE + rs(text, "charges, total") + rs(text, "slippage") + total_tax
        case("3 gross profit = final - start + charges + slippage + tax total",
             abs(gross - want) <= 0.03, f"printed {gross:,.2f}; from the parts {want:,.2f}")

        i = text.index("per financial year")
        head = text[i:].splitlines()[1]
        rows = [r for r in text[i:].splitlines()[2:] if re.match(r"^  FY\d{4}-\d\d", r)]
        per_year = 0.0
        for r in rows:
            v = [x.replace(",", "") for x in r.split()[1:]]
            # gross, charges, slippage, short tax, long tax, then cess when the header has it
            per_year += float(v[3]) + float(v[4]) + (float(v[5]) if "cess" in head else 0.0)
        case("4 per-year short tax + long tax + cess = tax total",
             "cess" in head and tax is not None and abs(per_year - tax) <= 0.01 * max(len(rows), 1),
             f"{len(rows)} years sum to {per_year:,.2f} against {tax}; header: {head.strip()}")

        j = text.index("investable buy & hold")
        bt = text[j:]

        def bh_row(label):
            m_ = re.search(rf"^  {re.escape(label)}\s+[-\d,]+\.\d\d\s+([-\d,]+\.\d\d)", bt, re.M)
            return float(m_.group(1).replace(",", "")) if m_ else None
        b_tax, b_st, b_lt, b_ce = (bh_row(x) for x in ("tax, total", "  short-term",
                                                         "  long-term", "  cess"))
        case("5 buy & hold sold on the last day: short + long + cess = its tax total",
             None not in (b_tax, b_ce) and abs((b_st or 0) + (b_lt or 0) + b_ce - b_tax) <= 0.02,
             f"{b_st} + {b_lt} + {b_ce} against {b_tax}")

        import cost_report as current
        short = [x.replace(f"{tax:>16,.2f}", f"{tax - cess_due:>16,.2f}") if x.startswith("  tax, total")
                 else x for x in lines] if tax is not None else lines
        try:
            current.check_tax_total(short, years, cum_tax)
            refused = False
        except current.CostReconciliationError:
            refused = True
        case("6 check_tax_total refuses a tax total without the cess", refused)

        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _tradability_causality():
    """
tradability_causality_test.py -- no trade on day i may depend on a row dated after day i.

    ./venv/bin/python tradability_causality_test.py          # every case, with its figures
    ./venv/bin/python tradability_causality_test.py --quiet  # PASS/FAIL lines only
    ./venv/bin/python tradability_causality_test.py --real   # also the KAMAHOLD replay

A synthetic universe of 20 names on real NSE calendar sessions, written as price
files to a temporary folder and loaded through engine_core.set_tradeability, the
way every engine run loads it. Each case runs test_exposure.backtest_exposure.

    1. causality: a held name has no row on two sessions. Removing every row of that
       name dated after day i must leave every trade and holding up to day i
       unchanged, for each day i around the gap and around each case below. The
       engine before 2026-10-16 fails this: it sold the name at the open of the
       session before the gap, because the next session had no row.
    2. a sale due on a session with no row is owed, and fills at the open of the
       next session with a row; that session is the first row after a gap
    3. a capped owed sale leaves the rest owed; the next decision that keeps the
       name cancels it, and the rest stays held
    4. a name whose file ends is never sold and is held at its last close
    5. a buy due on a session with no row is not made, and is logged
    6. with no rule loaded, the engine is unchanged (every session tradeable)

--real replays mcap5001to10000 v1 on the delivered data: KAMAHOLD has no row on
2019-03-18 and 2019-03-19. Cutting its file after 2019-03-15 must leave every trade
up to 2019-03-15 unchanged. Needs data/raw and the cached panel; about 2 minutes.

Nothing in the repository is written. Exit 0 when every case passes, 1 otherwise.
"""
    import shutil
    import sys
    import tempfile
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results", ROOT / "nautilus"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import engine_core
    from config import read_table  # the one CSV/parquet reader: config.read_table
    import slippage
    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    SYMS = [f"S{k:02d}" for k in range(20)]
    CAL = sorted(d for d in engine_core._load_calendar()
                 if pd.Timestamp("2020-06-01") <= d <= pd.Timestamp("2021-12-31"))
    DATES = [d for d in CAL if d >= pd.Timestamp("2021-01-01")]


    def D(i):
        return DATES[i]


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    class _Fixture:
        """A universe for engine_core.set_tradeability: a tag and a folder of price files."""
        def __init__(self, tag, folder):
            self.tag, self._folder = tag, Path(folder)

        def prepare_data_dir(self):
            return self._folder


    def frames():
        """Every name's full rows: close, open and a score, on every session of CAL."""
        n = len(CAL)
        t = np.arange(n)
        out = {}
        for k, s in enumerate(SYMS):
            close = 100.0 * (1 + 0.01 * k) * np.cumprod(np.r_[1.0, np.full(n - 1, 1.0004)]) \
                * (1 + 0.02 * np.sin(t / (k + 3)))
            out[s] = pd.DataFrame({"date": CAL, "open": close * 0.999, "close": close,
                                   "score": float(len(SYMS) - k)})
        return out


    def special(fr):
        """The cases' rows and scores, by the indices into DATES named in the docstring."""
        def drop(s, idx):
            fr[s] = fr[s][~fr[s]["date"].isin([D(i) for i in idx])]

        def score(s, lo, hi, v):
            m = (fr[s]["date"] >= D(lo)) & (fr[s]["date"] <= D(hi))
            fr[s].loc[m, "score"] = v
        drop("S00", [30, 31])                    # case 1: held through a two-session gap
        score("S01", 35, len(DATES) - 1, -1.0)   # case 2: ranked out at decision 40 ...
        drop("S01", [41, 42])                    # ... whose execution day has no row
        score("S02", 95, 114, -2.0)              # case 3: out at decision 100, back at 120
        drop("S02", [101])
        fr["S03"] = fr["S03"][fr["S03"]["date"] <= D(150)]  # case 4: the file ends
        score("S12", 60, 60, 100.0)              # case 5: a buy due on D61 ...
        drop("S12", [61])                        # ... which has no row
        return fr


    VOL20 = {"S02": {d: 10.0 for d in DATES[99:]}}   # case 3's cap: 10 shares a session


    def truncate(fr, sym, i):
        """The same rows with every row of `sym` dated after D(i) removed."""
        out = dict(fr)
        out[sym] = fr[sym][fr[sym]["date"] <= D(i)]
        return out


    # naming: axis-free -- fixture price files in a temporary folder, removed after the run
    def write(fr, folder):
        for s, f in fr.items():
            pd.DataFrame({"date": f["date"].dt.strftime("%d-%m-%Y"), "open": f["open"],
                          "high": f[["open", "close"]].max(axis=1),
                          "low": f[["open", "close"]].min(axis=1), "close": f["close"],
                          "adj_close": f["close"], "volume": 1_000_000.0}).to_csv(
                Path(folder) / f"{s}.csv", index=False)


    def run(fr, rule=True):
        """(audit, equity) for one fixture. The rule is loaded from the written files."""
        long = pd.concat([f.assign(symbol=s) for s, f in fr.items()])
        px = long.pivot_table(index="date", columns="symbol", values="close").reindex(CAL).ffill()
        op = long.pivot_table(index="date", columns="symbol", values="open").reindex(CAL).ffill()
        sc = long.pivot_table(index="date", columns="symbol", values="score").reindex(CAL)
        tmp = tempfile.mkdtemp(prefix="causality_")
        try:
            write(fr, tmp)
            if rule:
                engine_core.set_tradeability(_Fixture("causality", tmp))
            else:
                engine_core.set_tradeability(None, enabled=False)
            audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                     "skipped")}
            eq, *_ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                       mode="none", sizing="invvol", audit=audit, rebal=20,
                                       participation_cap=1.0, vol20=VOL20,
                                       drawdown_stop=None, dd_overlay=None,
                                       fixed_capital=False)
            return audit, eq, op
        finally:
            engine_core.set_tradeability(None, enabled=False)
            shutil.rmtree(tmp, ignore_errors=True)


    def upto(rows, cut):
        return [tuple(sorted(r.items())) for r in rows if pd.Timestamp(r["date"]) <= cut]


    def trades(audit, sym):
        return [r for r in audit["trades"] if r["symbol"] == sym]


    def main():
        fr = special(frames())
        full, eq, op = run(fr)

        # 1 ----------------------------------------------------------------------
        cuts = [("S00", i) for i in range(25, 36)] + [("S01", i) for i in (39, 40, 41, 42)] \
            + [("S02", i) for i in (100, 101, 102, 119, 120)] + [("S12", i) for i in (59, 60, 61)]
        bad = []
        for sym, i in cuts:
            cut, _, _ = run(truncate(fr, sym, i))
            for k in ("trades", "holdings"):
                if upto(full[k], D(i)) != upto(cut[k], D(i)):
                    bad.append(f"{sym} after {D(i).date()} ({k})")
                    break
        case("1 causality: rows after day i change nothing up to day i", not bad,
             f"{len(cuts)} cuts; differing: {bad[:4]}")

        # 2 ----------------------------------------------------------------------
        t = trades(full, "S01")
        sells = [r for r in t if r["action"] == "SELL"]
        want = round(slippage.sell_price(float(op.loc[D(43), "S01"]), 0, None, None), 2)
        owed = [r for r in full["skipped"] if r["symbol"] == "S01"
                and str(r["reason"]).startswith("untradeable: no row this session, sale owed")]
        case("2 owed sale fills at the next row's open",
             len(sells) == 1 and pd.Timestamp(sells[0]["date"]) == D(43)
             and sells[0]["price"] == want and [pd.Timestamp(r["date"]) for r in owed] == [D(41)],
             f"sells {[(str(pd.Timestamp(r['date']).date()), r['price']) for r in sells]}, "
             f"expected {D(43).date()} at {want}; owed logged on {[str(pd.Timestamp(r['date']).date()) for r in owed]}")

        # 3 ----------------------------------------------------------------------
        t = trades(full, "S02")
        s3 = [r for r in t if r["action"] == "SELL"]
        held_after = [r for r in full["holdings"] if r["symbol"] == "S02"
                      and pd.Timestamp(r["date"]) == D(121)]
        ok3 = (s3 and all(r["qty"] == 10 for r in s3)
               and all(D(102) <= pd.Timestamp(r["date"]) <= D(120) for r in s3)
               and len(held_after) == 1 and held_after[0]["qty"] > 0)
        case("3 capped owed sale: rest stays owed, cancelled when kept again", ok3,
             f"{len(s3)} sells of {[r['qty'] for r in s3][:3]}... from "
             f"{pd.Timestamp(s3[0]['date']).date() if s3 else '-'} to "
             f"{pd.Timestamp(s3[-1]['date']).date() if s3 else '-'}; held on {D(121).date()}: "
             f"{held_after[0]['qty'] if held_after else 0}")

        # 4 ----------------------------------------------------------------------
        t = trades(full, "S03")
        late = [r for r in t if pd.Timestamp(r["date"]) > D(150)]
        end = [r for r in full["holdings"] if r["symbol"] == "S03"
               and pd.Timestamp(r["date"]) == DATES[-1]]
        last_close = round(float(fr["S03"]["close"].iloc[-1]), 2)
        case("4 a name whose file ends is held at its last close",
             not late and len(end) == 1 and round(float(end[0]["price"]), 2) == last_close,
             f"trades after {D(150).date()}: {len(late)}; held at the end: "
             f"{end[0]['qty'] if end else 0} at {end[0]['price'] if end else '-'} "
             f"(last close {last_close})")

        # 5 ----------------------------------------------------------------------
        refused = [r for r in full["skipped"] if r["symbol"] == "S12" and r["side"] == "BUY"
                   and str(r["reason"]).startswith("untradeable: no row this session")]
        bought = [r for r in trades(full, "S12") if r["action"] == "BUY"
                  and pd.Timestamp(r["date"]) == D(61)]
        case("5 a buy due on a session with no row is not made",
             not bought and [pd.Timestamp(r["date"]) for r in refused] == [D(61)],
             f"refused on {[str(pd.Timestamp(r['date']).date()) for r in refused]}")

        # 6 ----------------------------------------------------------------------
        base = frames()
        a_rule, e_rule, _ = run(base)
        a_none, e_none, _ = run(base, rule=False)
        case("6 every session has a row: the rule changes nothing",
             bool((e_rule == e_none).all()) and a_rule["trades"] == a_none["trades"],
             f"final equity {e_rule.iloc[-1]:,.2f} and {e_none.iloc[-1]:,.2f}")

        if "--real" in sys.argv:
            real()

        print(f"\nRESULT: {'PASS' if all(RESULTS) else 'FAIL'} -- {sum(RESULTS)} of {len(RESULTS)} cases")
        return 0 if all(RESULTS) else 1


    def real():
        """mcap5001to10000 v1 on the delivered data, KAMAHOLD cut after 2019-03-15."""
        import audit_step
        from arms.registry import ARMS
        from universes.registry import REGISTRY
        u = REGISTRY["mcap5001to10000"]
        px, op, sc, bd = audit_step.prices(u)
        cut_day = pd.Timestamp("2019-03-15")

        def one(farm, px_, op_, sc_):
            engine_core.set_tradeability(_Fixture(u.tag, farm))
            try:
                audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                         "skipped")}
                backtest_exposure(px_, op_, sc_, bd, precompute(px_), px_ / px_.shift(20) - 1,
                                  audit=audit, **ARMS["v1"].kwargs,
                                  tax_enabled=False, rebal=20, participation_cap=None,
                                  drawdown_stop=None, dd_overlay=None, fixed_capital=False)
                return audit
            finally:
                engine_core.set_tradeability(None, enabled=False)

        full = one(u.prepare_data_dir(), px, op, sc)
        tmp = Path(tempfile.mkdtemp(prefix="kamahold_"))
        try:
            for f in Path(u.prepare_data_dir()).glob("*.csv"):
                if f.stem != "KAMAHOLD":
                    (tmp / f.name).symlink_to(f.resolve())
            k = read_table(Path(u.prepare_data_dir()) / "KAMAHOLD.csv")
            kd = pd.to_datetime(k["date"], format="%d-%m-%Y")
            # naming: axis-free -- a cut copy of one raw file in a temporary folder
            k[kd <= cut_day].to_csv(tmp / "KAMAHOLD.csv", index=False)
            px_c, op_c, sc_c = px.copy(), op.copy(), sc.copy()
            after = px_c.index > cut_day
            px_c.loc[after, "KAMAHOLD"] = px.loc[cut_day, "KAMAHOLD"]
            op_c.loc[after, "KAMAHOLD"] = op.loc[cut_day, "KAMAHOLD"]
            sc_c.loc[sc_c.index > cut_day, "KAMAHOLD"] = np.nan
            cut = one(tmp, px_c, op_c, sc_c)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        same = upto(full["trades"], cut_day) == upto(cut["trades"], cut_day)
        kama = [r for r in full["trades"] if r["symbol"] == "KAMAHOLD"
                and pd.Timestamp(r["date"]) <= pd.Timestamp("2019-05-31")]
        case("real: mcap5001to10000 v1, KAMAHOLD cut after 2019-03-15", same,
             f"KAMAHOLD trades to 2019-05-31 on the full data: "
             f"{[(str(pd.Timestamp(r['date']).date()), r['action'], r['qty'], r['price']) for r in kama]}")

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _cache_key():
    """cache_key_test.py -- a cache or record from other code or other data must be refused.

    ./venv/bin/python cache_key_test.py

Each case writes a record the way its harness does, once with the current key and
once with a changed or missing one, into a temporary directory, and asserts that
the harness reuses the first and refuses the second. Nothing under the repository
is written. Exit 1 names every case that failed.

    noise_parallel      draw_state, _baseline_state and load_draws on draw JSONs
    price_noise_measure current_runs on runs-CSV rows
    after_tax_noise     current_runs on runs-CSV rows
    seed_cache_key      the /tmp fit caches (validate_engine, validate_sizing,
                        validate_breadth_live, purge_fix_measure) change name when
                        the panel's content changes by one byte
"""
    import io
    import json
    import sys
    import tempfile
    from contextlib import redirect_stdout
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    import pandas as pd                                            # noqa: E402

    import config                                                  # noqa: E402
    from universes.registry import REGISTRY                        # noqa: E402

    TAG = "nifty50"
    FAILS = []


    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            FAILS.append(name)


    def quiet(fn, *a):
        with redirect_stdout(io.StringIO()):
            return fn(*a)


    def noise_parallel_cases(key, tmp):
        import noise_parallel as npar
        out = tmp / "np"
        (out / "draws").mkdir(parents=True)
        base = {"tag": TAG, "sigma": 0.0, "noise_seed": 0, "baseline": {"ok": True}}
        npar.write_atomic(npar.result_path(out, TAG, 0), json.dumps({**base, **key}))
        npar.write_atomic(npar.result_path(out, TAG, 101),
                          json.dumps({**base, "noise_seed": 101, **key,
                                      "panel_code": "sha256:other"}))
        npar.write_atomic(npar.result_path(out, TAG, 202),
                          json.dumps({**base, "noise_seed": 202}))
        check("noise_parallel: a draw with the current key is current",
              npar.draw_state(out, TAG, 0) == "current")
        check("noise_parallel: a draw with another panel_code is stale",
              npar.draw_state(out, TAG, 101) == "stale")
        check("noise_parallel: a draw without key fields is stale",
              npar.draw_state(out, TAG, 202) == "stale")
        check("noise_parallel: a missing draw is missing",
              npar.draw_state(out, TAG, 303) == "missing")
        check("noise_parallel: a current passing baseline passes",
              npar._baseline_state(out, TAG) is True)
        npar.write_atomic(npar.result_path(out, TAG, 0),
                          json.dumps({**base, **key, "source_digest": "sha256:other"}))
        check("noise_parallel: a stale baseline counts as no baseline, even marked ok",
              npar._baseline_state(out, TAG) is None)
        got = quiet(npar.load_draws, out)
        check("noise_parallel: load_draws leaves every stale draw out", got == [])


    def runs_csv_cases(key, tmp):
        import price_noise_measure as pnm
        import after_tax_noise as atn
        rows = [{"tag": TAG, "sigma": 0.0001, "noise_seed": 101, **key},
                {"tag": TAG, "sigma": 0.0001, "noise_seed": 202, **key,
                 "source_digest": "sha256:other"},
                {"tag": TAG, "sigma": 0.0001, "noise_seed": 303,
                 "panel_code": None, "source_digest": None}]
        for mod, attr, label in ((pnm, "RUNS_CSV", "price_noise_measure"),
                                 (atn, "RUNS", "after_tax_noise")):
            f = tmp / f"{label}_runs.csv"
            pd.DataFrame(rows).to_csv(f, index=False)
            old = getattr(mod, attr)
            setattr(mod, attr, f)
            try:
                got = quiet(mod.current_runs)
            finally:
                setattr(mod, attr, old)
            check(f"{label}: only the row with the current key is reused",
                  sorted(got["noise_seed"].astype(int)) == [101])


    def fit_cache_cases(tmp):
        import validate_breadth_live as vbl
        from seed_cache_key import seed_cache_key
        a, b = tmp / "panel_a.csv", tmp / "panel_b.csv"
        a.write_text("date,symbol,close\n2020-01-01,X,1.00\n")
        b.write_text("date,symbol,close\n2020-01-01,X,1.01\n")
        check("validate_breadth_live: the T1 cache name changes with the panel content",
              vbl._t1_cache(TAG, 0, [5, 55, 555], a) != vbl._t1_cache(TAG, 0, [5, 55, 555], b))
        code = [ROOT / "results" / "engine_core.py", ROOT / "config.py"]
        check("seed_cache_key: one byte of panel content changes the key",
              seed_cache_key(code, a, (TAG,)) != seed_cache_key(code, b, (TAG,)))


    def main():
        print("cache_key_test -- stale caches and records must be refused")
        key = config.run_key(REGISTRY[TAG])
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            noise_parallel_cases(key, tmp)
            runs_csv_cases(key, tmp)
            fit_cache_cases(tmp)
        if FAILS:
            print(f"RESULT: FAIL -- {len(FAILS)} case(s): " + "; ".join(FAILS))
            return 1
        print("RESULT: PASS -- every stale record and cache was refused, every current one reused")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _noise_harness():
    """noise_harness_test.py -- results/noise_parallel.py on synthetic draws.

    ./venv/bin/python noise_harness_test.py

Runs the harness's real scheduler (cmd_run), baseline gate, resume, stale-key
check and analysis (cmd_analyse) on fabricated draws in a temporary directory.
subprocess.Popen inside noise_parallel is replaced by a stub that writes the
draw's result file at once instead of computing it; nothing is fitted and nothing
under the repository is written. Exit 1 names every case that failed.

    failed baseline   a universe whose baseline fails gets none of its draws
    resume            a second identical run starts nothing
    stale key         a draw or baseline with another panel_code is re-run
    void              a draw with another harness hash voids its universe
    verdicts          the rule and the nt_verify label, on a supported cell that
                      verifies and one that does not
"""
    import io
    import json
    import sys
    import tempfile
    from contextlib import redirect_stdout
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    import argparse                                                # noqa: E402

    import noise_parallel as npar                                  # noqa: E402

    FAILS = []
    LAUNCHED = []
    # universe -> (baseline passes?, v1 gap under both profiles on every draw)
    PLAN = {"nifty50": (True, 0.5), "midcap50": (False, 0.5), "midcap100": (True, 0.5)}


    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            FAILS.append(name)


    def fabricate(tag, seed):
        ok, v1_gap = PLAN[tag]
        bh = 20.0
        arms = {}
        for prof in npar.PROFILES:
            for i, a in enumerate(npar.ARM_NAMES):
                # v1 beats the buy & hold by v1_gap plus a small seed-dependent wiggle;
                # the other arms lose to it.
                gap = (v1_gap + 0.01 * (seed % 7)) if a == "v1" else (-1.0 - i)
                arms[f"{a}@{prof}"] = {"arm": a, "profile": prof, "cagr": bh + gap,
                                       "final_equity": 1e6, "tax": 0.0, "trades": 1,
                                       "cap_binds": 0, "seconds": 0.0}
        rec = {"tag": tag, "sigma": 0.0 if seed == 0 else npar.SIGMA, "noise_seed": seed,
               "bh_cagr": bh, "bh_final_equity": 1e6, "bh_seconds": 0.0, "arms": arms,
               "rows": 1, "bound_crossings": 0, "minutes_total": 0.0, "minutes_perturb": 0.0,
               "minutes_panel": 0.0, "minutes_arms": 0.0, "loky_workers": 1,
               "run_date": "synthetic", "script_sha256": npar._SCRIPT_SHA,
               "perturb_sha256": npar._SCRIPT_SHA, **npar.current_key(tag)}
        if seed == 0:
            rec["baseline"] = {"ok": ok, "failures": [] if ok else ["synthetic failure"],
                               "tolerance": npar.BASELINE_TOL}
        return rec


    class FakeProc:
        pid = 0

        def poll(self):
            return 0


    def fake_popen(cmd, stdout=None, stderr=None, cwd=None):
        i = cmd.index("one")
        tag = cmd[cmd.index("--universe", i) + 1]
        seed = int(cmd[cmd.index("--seed", i) + 1])
        out = cmd[cmd.index("--out", i) + 1]
        LAUNCHED.append((tag, seed))
        npar.write_atomic(npar.result_path(out, tag, seed), json.dumps(fabricate(tag, seed)))
        return FakeProc()


    def run(out, tags):
        LAUNCHED.clear()
        a = argparse.Namespace(universe=",".join(tags),
                               seeds=",".join(str(s) for s in npar.NOISE_SEEDS),
                               baseline=True, workers=2, loky=1, out=str(out),
                               work=str(out / "work"))
        with redirect_stdout(io.StringIO()):
            npar.cmd_run(a)
        return list(LAUNCHED)


    def analyse(out, tmp):
        npar.REPORT, npar.RUNS_CSV = tmp / "report.txt", tmp / "runs.csv"
        with redirect_stdout(io.StringIO()):
            npar.cmd_analyse(argparse.Namespace(out=str(out)))
        return npar.REPORT.read_text()


    def main():
        print("noise_harness_test -- the cleaned-noise harness on synthetic draws")
        npar.subprocess.Popen = fake_popen
        npar._tree_rss = lambda: (lambda pid: 0)
        npar.time.sleep = lambda s: None
        tags = list(PLAN)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            out = tmp / "out"
            first = run(out, tags)
            check("failed baseline: midcap50 ran its baseline and none of its draws",
                  [x for x in first if x[0] == "midcap50"] == [("midcap50", 0)])
            check("passing baselines: nifty50 and midcap100 ran the baseline and 10 draws each",
                  all(sum(1 for x in first if x[0] == u) == 11 for u in ("nifty50", "midcap100")))
            check("a baseline runs before its universe's draws",
                  all(first.index((u, 0)) < min(first.index((u, s)) for s in npar.NOISE_SEEDS)
                      for u in ("nifty50", "midcap100")))
            check("resume: an identical second run starts nothing", run(out, tags) == [])

            f = npar.result_path(out, "nifty50", 303)
            rec = json.loads(f.read_text()); rec["panel_code"] = "sha256:other"
            f.write_text(json.dumps(rec))
            check("stale key: exactly the stale draw is re-run",
                  run(out, tags) == [("nifty50", 303)])
            f = npar.result_path(out, "midcap100", 0)
            rec = json.loads(f.read_text()); rec["source_digest"] = "sha256:other"
            f.write_text(json.dumps(rec))
            check("stale key: a stale baseline is re-run and its draws are not",
                  run(out, tags) == [("midcap100", 0)])

            text = analyse(out, tmp)
            check("verdict: nifty50 v1 is SUPPORTED (verifies in nt_verify)",
                  "v1 VERDICT: SUPPORTED (research passes, tradeable passes; nt_verify VERIFIED)"
                  in text.split("nifty50\n", 1)[1].split("\n\n", 1)[0])
            check("verdict: midcap100 v1 is SUPPORTED, NOT PORT-VERIFIED",
                  "v1 VERDICT: SUPPORTED, NOT PORT-VERIFIED" in
                  text.split("midcap100\n", 1)[1].split("\n\n", 1)[0])
            check("verdict: an arm that loses to the buy & hold is NOT SUPPORTED",
                  "v2 VERDICT: NOT SUPPORTED" in text.split("nifty50\n", 1)[1])
            check("failed baseline: midcap50 is reported as stopped",
                  "baseline FAILED" in text.split("midcap50\n", 1)[1].split("\n\n", 1)[0])
            check("the registration's two statements are in the report",
                  "32 cells are tested" in text and "not to be read as an edge" in text
                  and "UNGATED" in text)

            f = npar.result_path(out, "nifty50", 505)
            rec = json.loads(f.read_text()); rec["script_sha256"] = "0000000000000000"
            f.write_text(json.dumps(rec))
            text = analyse(out, tmp)
            check("void: a draw with another harness hash voids its universe",
                  "VOID" in text.split("nifty50\n", 1)[1].split("\n\n", 1)[0]
                  and "VOID" not in text.split("midcap100\n", 1)[1].split("\n\n", 1)[0])
        if FAILS:
            print(f"RESULT: FAIL -- {len(FAILS)} case(s): " + "; ".join(FAILS))
            return 1
        print("RESULT: PASS -- scheduler, baseline gate, resume, stale key, void and verdicts "
              "behave as registered")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())



def _buy_shortfall():
    """
buy_shortfall -- a buy cash cannot fully pay for: trimmed or refused (buy_shortfall.py).

    ./venv/bin/python engine_tests.py buy_shortfall [--quiet]

    1. names: "" at the default trim, "_refuse" / "@refuse" otherwise; an unknown
       value is refused
    2. largest_fit() returns the largest q that fits, checked against every q
       from 0 to the wanted quantity, at prices from Rs 0.95 to Rs 48,000 and cash
       on both sides of each boundary; trim() returns that q when it is at least
       MIN_FILL_PCT of the wanted quantity and 0 otherwise
    3. a case the rounding of charges decides: 5 shares at Rs 100.00 cost Rs 500 and
       Rs 0.50 of STT, which rounds up to Rs 1. Cash of that cost less Rs 0.01 buys 4,
       though the unrounded charges would let 5 fit
    4. not one share fits: q is 0, reason "cash short", and the engine refuses
       the buy as cash short
    5. the engine on a synthetic panel, v1 to v4, tax off and on, trim against
       refuse:
       a. refuse trims nothing: no trade row has wanted_qty, every cash-short skip
          has one of the two reasons it always had, and buy_shortfall=None with the
          selection at refuse gives the same run as buy_shortfall="refuse"
       b. the two runs are identical, every fill, every day's cash and every
          equity value, up to the first trimmed buy; an arm that is never short of
          cash under refuse trims nothing and is identical over the whole window
       c. each trimmed buy, replayed from the run's own cost trail, is the largest
          q whose cost and charges fit the cash in hand at that point of the
          morning: q fits and q + 1 does not
       d. every trimmed buy fills at least MIN_FILL_PCT of its wanted quantity,
          and every buy refused below the minimum is logged `cash short: below
          minimum fill` with a fill share under it
    6. the minimum fill at its boundary, Rs 100 a share: wanted 10 with cash
       for exactly 5 (50%) fills 5 and with cash for 6 fills 6, while cash
       one paisa short of 5 refuses (4 is 40%); wanted 9, where 50% is 4.5,
       fills 5 (55.6%) and refuses 4 (44.4%); wanted 1,000 fills 500 and
       refuses 499
    7. a floating-point floor that lands one share short: at Rs 0.05 with Rs 0.25
       of cash and no charges, 0.25 // 0.05 is 4.0 but five shares fit, and
       largest_fit() returns 5

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
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

    import buy_shortfall as bsf
    from engine_core import precompute
    from test_exposure import backtest_exposure, calc_tc

    QUIET = "--quiet" in sys.argv
    RESULTS = []

    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
              flush=True)

    def cost(pr, q):
        return q * pr + calc_tc(pr, q, "BUY")

    def charges(p_, n):
        return calc_tc(p_, n, "BUY")

    # 1. names
    d = (bsf.selected(), bsf.suffix(), bsf.segment(), bsf.label())
    bsf.set_selection("refuse")
    on = (bsf.suffix(), bsf.segment())
    bsf.set_selection(None)
    try:
        bsf.set_selection("shrink")
        bad = False
    except ValueError:
        bad = True
    bsf.set_selection(None)
    case("1 names and validation", d == ("trim", "", "", "") and on == ("_refuse", "@refuse") and bad,
         f"default {d}, refuse {on}, unknown value refused {bad}")

    # 2. the largest q, against every q
    worst, n_checked = [], 0
    for pr in (0.95, 13.37, 100.0, 251.35, 1999.99, 48000.0):
        for q_w in (1, 7, 40, 333):
            for full in range(0, q_w + 1, max(1, q_w // 20)):
                for eps in (-0.01, 0.0, 0.01):
                    cash = (cost(pr, full) if full else pr) + eps
                    want = max([0] + [k for k in range(1, q_w + 1) if cost(pr, k) <= cash])
                    got = bsf.largest_fit(q_w, cash, lambda n: pr, charges)[0]
                    t = bsf.trim(q_w, cash, lambda n: pr, charges)[0]
                    n_checked += 1
                    if got != want or t != (want if want * 2 >= q_w else 0):
                        worst.append((pr, q_w, round(cash, 2), want, got, t))
    case("2 largest_fit returns the largest q that fits, trim applies the minimum", not worst,
         f"{n_checked} (price, wanted, cash) cases" + (f"; wrong: {worst[:3]}" if worst else ""))

    # 3. rounding of the charges decides q
    pr = 100.0
    c5 = cost(pr, 5)
    unrounded_5 = 500 + 500 * 0.001 + (c5 - 500 - 1.0)   # STT exact, the rest as charged
    cash = c5 - 0.01
    got = bsf.trim(5, cash, lambda n: pr, charges)
    case("3 the rounding of charges decides q", got[0] == 4 and unrounded_5 <= cash and c5 > cash,
         f"cost of 5 Rs {c5:,.2f} (STT Rs {calc_tc(pr, 5, 'BUY') - (c5 - 500 - 1.0):.2f} as "
         f"charged), cash Rs {cash:,.2f}, unrounded cost of 5 Rs {unrounded_5:,.3f}; trim gave {got[0]}")

    # 4. not one share
    got = bsf.trim(10, 99.0, lambda n: 100.0, charges)
    neg = bsf.trim(10, -5_000.0, lambda n: 100.0, charges)
    case("4 not one share fits: q is 0", got[0] == 0 and neg[0] == 0
         and got[3] == "cash short" and neg[3] == "cash short",
         f"cash Rs 99 at Rs 100 -> {got[0]} ({got[3]}); cash -Rs 5,000 -> {neg[0]} ({neg[3]})")

    # 5. the engine
    syms = [f"S{k:02d}" for k in range(40)]
    idx = pd.bdate_range("2020-08-03", "2021-12-31")
    dates = pd.bdate_range("2021-01-01", "2021-12-31")
    rng = np.random.default_rng(11)
    px = pd.DataFrame({s: 100.0 * (1 + 0.05 * k) * np.cumprod(1 + 0.0004 + 0.012 * rng.standard_normal(len(idx)))
                       for k, s in enumerate(syms)}, index=idx)
    op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=syms)

    def blank():
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        a["costs"] = {"fills": [], "days": []}
        return a

    def run(mode, sizing, tax, rule):
        a = blank()
        eq, _, _, _ = backtest_exposure(px, op, sc, dates, precompute(px), px / px.shift(20) - 1,
                                        mode=mode, sizing=sizing, audit=a, rebal=20,
                                        participation_cap=None, drawdown_stop=None,
                                        dd_overlay=None, fixed_capital=False, tax_enabled=tax,
                                        start_capital=1_000_000, buy_shortfall=rule)
        return eq, a

    def first_trim(a):
        t = [r for r in a["trades"] if "wanted_qty" in r]
        return (pd.Timestamp(t[0]["date"]), t[0]) if t else (None, None)

    def replay_ok(a):
        """(trimmed buys checked, failures): each trimmed buy against the cash in hand."""
        trims = {(pd.Timestamp(r["date"]), r["symbol"]) for r in a["trades"] if "wanted_qty" in r}
        days = {pd.Timestamp(x["date"]): x for x in a["costs"]["days"]}
        cash, cur, n, bad = None, None, 0, []
        for f in a["costs"]["fills"]:
            dt = pd.Timestamp(f["date"])
            if dt != cur:
                cur = dt
                x = days[dt]
                cash = x["cash_open"] + x["interest"] - x["tax_before_fills"]
            q, pr, tc = f["qty"], f["fill_price"], f["charges"]
            if f["side"] == "BUY":
                if (dt, f["symbol"]) in trims:
                    n += 1
                    if not (cost(pr, q) <= cash < cost(pr, q + 1)):
                        bad.append((str(dt.date()), f["symbol"], q))
                cash -= q * pr + tc
            else:
                cash += q * pr - tc
        return n, bad

    reasons_old = {"cash short (before TC)", "cash short (incl TC)"}
    for mode, sizing, arm in (("none", "invvol", "v1"), ("breadth", "invvol", "v2"),
                              ("none", "provol", "v3"), ("breadth", "provol", "v4")):
        for tax in (False, True):
            lab = f"{arm} tax {'on' if tax else 'off'}"
            e0, a0 = run(mode, sizing, tax, "refuse")
            bsf.set_selection("refuse")
            e0s, a0s = run(mode, sizing, tax, None)
            bsf.set_selection(None)
            rs = {r["reason"] for r in a0["skipped"] if r["reason"].startswith("cash short")}
            case(f"5a {lab}: refuse trims nothing and keeps its reasons",
                 not any("wanted_qty" in r for r in a0["trades"]) and rs <= reasons_old
                 and a0["buy_shortfall"]["trimmed"] == 0
                 and bool((e0 == e0s).all()) and a0["trades"] == a0s["trades"],
                 f"{a0['buy_shortfall']['refused']} refused, reasons {sorted(rs)}")
            e1, a1 = run(mode, sizing, tax, "trim")
            cut, row = first_trim(a1)
            if cut is None:
                n_ref = a0["buy_shortfall"]["refused"]
                case(f"5b {lab}: never short of cash, so trim and refuse are the same run",
                     n_ref == 0 and bool((e0 == e1).all()) and a0["costs"] == a1["costs"],
                     f"{n_ref} refused under refuse, 0 trimmed, {len(a1['costs']['fills'])} fills")
                continue
            pre = e0.index < cut
            f0 = [f for f in a0["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
            f1 = [f for f in a1["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
            same = bool((e0[pre].to_numpy() == e1[pre].to_numpy()).all()) and f0 == f1
            case(f"5b {lab}: identical up to the first trimmed buy, {cut.date()}",
                 same and pre.sum() > 0,
                 f"{int(pre.sum())} sessions, {len(f0)} fills; first trim {row['symbol']} "
                 f"wanted {row['wanted_qty']:,}, filled {row['qty']:,}, short Rs "
                 f"{row['cash_shortfall']:,.2f}; {a1['buy_shortfall']['trimmed']} trimmed, "
                 f"{a1['buy_shortfall']['refused']} refused")
            n, bad = replay_ok(a1)
            case(f"5c {lab}: each trimmed buy is the largest q the cash in hand pays for",
                 n > 0 and not bad, f"{n} trimmed buys replayed" + (f"; wrong {bad[:3]}" if bad else ""))
            tr = [r for r in a1["trades"] if "wanted_qty" in r]
            low = [r for r in tr if r["qty"] * 100 < bsf.MIN_FILL_PCT * r["wanted_qty"]]
            bm = [r for r in a1["skipped"] if r["reason"] == bsf.BELOW_MINIMUM]
            bm_bad = [r for r in bm
                      if not float(r["detail"].split("(")[1].split("%")[0]) < bsf.MIN_FILL_PCT]
            case(f"5d {lab}: trimmed buys fill at least {bsf.MIN_FILL_PCT}%, the rest are refused",
                 not low and not bm_bad,
                 f"{len(tr)} trimmed, smallest fill "
                 f"{min((r['qty'] / r['wanted_qty'] * 100 for r in tr), default=float('nan')):.1f}%; "
                 f"{len(bm)} refused below the minimum")

    # 6. the minimum fill at its boundary
    pr = 100.0
    got = {}
    for q_w, fit, eps in ((10, 5, 0.0), (10, 6, 0.0), (10, 5, -0.01),
                          (9, 5, 0.0), (9, 4, 0.0), (1000, 500, 0.0), (1000, 499, 0.0)):
        r = bsf.trim(q_w, cost(pr, fit) + eps, lambda n: pr, charges)
        got[(q_w, fit, eps)] = (r[0], r[3])
    want = {(10, 5, 0.0): (5, None), (10, 6, 0.0): (6, None),
            (10, 5, -0.01): (0, bsf.BELOW_MINIMUM), (9, 5, 0.0): (5, None),
            (9, 4, 0.0): (0, bsf.BELOW_MINIMUM), (1000, 500, 0.0): (500, None),
            (1000, 499, 0.0): (0, bsf.BELOW_MINIMUM)}
    case(f"6 minimum fill {bsf.MIN_FILL_PCT}%: at, just above and just below", got == want,
         "; ".join(f"wanted {k[0]}, cash for {k[1]}{' less Rs 0.01' if k[2] else ''} -> "
                   f"{v[0]}{' (' + v[1] + ')' if v[1] else ''}" for k, v in got.items()))

    # 7. a floor that lands one share short
    floor_q = 0.25 // 0.05
    got7 = bsf.largest_fit(10, 0.25, lambda n: 0.05, lambda p_, n: 0.0)[0]
    case("7 0.25 // 0.05 floors to 4.0, five shares fit, largest_fit returns 5",
         floor_q == 4.0 and 5 * 0.05 <= 0.25 and got7 == 5,
         f"0.25 // 0.05 = {floor_q}, 5 x 0.05 = {5 * 0.05}, largest_fit -> {got7}")

    n_fail = RESULTS.count(False)
    print(f"RESULT: {'PASS' if not n_fail else 'FAIL'} -- {len(RESULTS) - n_fail} of {len(RESULTS)} cases")
    sys.exit(1 if n_fail else 0)



def _fill_open_sizing():
    """
fill_open_sizing -- a buy's quantity does not read the fill session's open.

    ./venv/bin/python engine_tests.py fill_open_sizing [--quiet]

Since 2026-10-28 the engine sizes every buy at the decision session's close. On a
synthetic panel, for v1 to v4, tax off and on, the open of one fill session is
moved by +7% and by -7% for every name, and nothing else changes:
    1. every run is identical, every equity value, before that session
    2. every buy decided for that session has the same wanted quantity in all
       three runs (the filled quantity, or wanted_qty for a trimmed buy, or the
       wanted quantity of a buy refused below the minimum fill)
    3. the buys' fill prices on that session moved with the open, so the open
       did reach the run

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import re
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import buy_shortfall as bsf
    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []

    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
              flush=True)

    syms = [f"S{k:02d}" for k in range(40)]
    idx = pd.bdate_range("2020-08-03", "2021-12-31")
    dates = pd.bdate_range("2021-01-01", "2021-12-31")
    rng = np.random.default_rng(11)
    px = pd.DataFrame({s: 100.0 * (1 + 0.05 * k) * np.cumprod(1 + 0.0004 + 0.012 * rng.standard_normal(len(idx)))
                       for k, s in enumerate(syms)}, index=idx)
    op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=syms)
    pc, mom = precompute(px), px / px.shift(20) - 1

    def run(op_, mode, sizing, tax):
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        a["costs"] = {"fills": [], "days": []}
        eq, _, _, _ = backtest_exposure(px, op_, sc, dates, pc, mom, mode=mode, sizing=sizing,
                                        audit=a, rebal=20, participation_cap=None,
                                        drawdown_stop=None, dd_overlay=None, fixed_capital=False,
                                        tax_enabled=tax, start_capital=1_000_000)
        return eq, a

    def wanted(a, day):
        """{symbol: wanted quantity} of every buy decided for `day`."""
        out = {}
        for r in a["trades"]:
            if r["action"] == "BUY" and pd.Timestamp(r["date"]) == day:
                out[r["symbol"]] = int(r.get("wanted_qty", r["qty"]))
        for r in a["skipped"]:
            if (r["side"] == "BUY" and pd.Timestamp(r["date"]) == day
                    and r["reason"] == bsf.BELOW_MINIMUM):
                out[r["symbol"]] = int(re.match(r"wanted ([\d,]+) sh", r["detail"])
                                       .group(1).replace(",", ""))
        return out

    def prices(a, day):
        return {r["symbol"]: r["price"] for r in a["trades"]
                if r["action"] == "BUY" and pd.Timestamp(r["date"]) == day}

    for arm, mode, sizing in (("v1", "none", "invvol"), ("v2", "breadth", "invvol"),
                              ("v3", "none", "provol"), ("v4", "breadth", "provol")):
        for tax in (False, True):
            eq0, a0 = run(op, mode, sizing, tax)
            # The second session with buys: by then the book holds names, so the
            # sells and the decision-close valuation of a held book are exercised.
            buy_days = sorted({pd.Timestamp(r["date"]) for r in a0["trades"] if r["action"] == "BUY"})
            day = buy_days[1]
            runs = {}
            for move in (1.07, 0.93):
                op_m = op.copy()
                op_m.loc[day] = op_m.loc[day] * move
                runs[move] = run(op_m, mode, sizing, tax)
            tag = f"{arm} tax {'on' if tax else 'off'}"
            pre = eq0.index < day
            same_pre = all(bool((e[pre].to_numpy() == eq0[pre].to_numpy()).all())
                           for e, _ in runs.values())
            case(f"1 {tag}: identical before {day.date()}", same_pre and pre.sum() > 0,
                 f"{int(pre.sum())} sessions")
            w0 = wanted(a0, day)
            ws = {m: wanted(a, day) for m, (_, a) in runs.items()}
            case(f"2 {tag}: wanted quantities on {day.date()} unchanged with the open +7% and -7%",
                 len(w0) > 0 and all(w == w0 for w in ws.values()),
                 f"{len(w0)} buys; " + ", ".join(f"{k} {v}" for k, v in sorted(w0.items())[:4]))
            p0 = prices(a0, day)
            moved = all(all(abs(prices(a, day)[k] / p0[k] - m) < 0.001
                            for k in p0 if k in prices(a, day))
                        for m, (_, a) in runs.items())
            case(f"3 {tag}: fill prices on {day.date()} moved with the open", len(p0) > 0 and moved,
                 f"{len(p0)} fills")

    n_fail = RESULTS.count(False)
    print(f"RESULT: {'PASS' if not n_fail else 'FAIL'} -- {len(RESULTS) - n_fail} of {len(RESULTS)} cases")
    sys.exit(1 if n_fail else 0)


def _fill_price():
    """
fill_price -- every fill price is the open moved by the slippage, to the paisa.

    ./venv/bin/python engine_tests.py fill_price [--quiet]

Since 2026-10-28 slippage.fill_price prices every fill, as
~/Downloads/predictive-backtest's engine.fill_price does: round(open x (1 +/-
rate), 2) in float64, rounded by NumPy.
    1. a buy and a sale of a price already in paise round to the paisa
    2. half a paisa rounds as NumPy rounds: 3450 x 0.9985 = 3444.825 gives 3444.82
    3. buy_price and sell_price are fill_price at SLIPPAGE, with and without impact
    4. on a synthetic panel every fill of v1 to v4, tax off and on, is in whole
       paise and equals fill_price of its reference price

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
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

    import slippage as sl
    from engine_core import precompute
    from test_exposure import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []

    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))

    b, s_ = sl.fill_price(123.45, 0.0015, True), sl.fill_price(123.45, 0.0015, False)
    case("1 Rs 123.45 buys at 123.64 and sells at 123.26", b == 123.64 and s_ == 123.26,
         f"buy {b}, sell {s_}")
    h = sl.fill_price(3450, 0.0015, False)
    case("2 3450 x 0.9985 = 3444.825 sells at 3444.82", h == 3444.82, f"got {h}")
    imp = sl.impact(1000, 50_000, 0.002)
    ok3 = (sl.buy_price(987.65, 0, None, None) == sl.fill_price(987.65, sl.SLIPPAGE, True)
           and sl.sell_price(987.65, 0, None, None) == sl.fill_price(987.65, sl.SLIPPAGE, False)
           and sl.buy_price(987.65, 1000, 50_000, 0.002)
           == sl.fill_price(987.65, sl.SLIPPAGE + imp, True))
    case("3 buy_price and sell_price are fill_price at SLIPPAGE", ok3)

    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2020-01-01", periods=420)
    syms = [f"S{k:02d}" for k in range(24)]
    px = pd.DataFrame({s: 37.0 * (1 + 0.31 * k) * np.cumprod(1 + 0.0004 + 0.013 * rng.standard_normal(len(idx)))
                       for k, s in enumerate(syms)}, index=idx)
    op = px.shift(1).bfill() * (1 + 0.002 * rng.standard_normal(px.shape))
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=syms)
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    dates = list(idx[80:])
    import arms.registry as AR
    for name in ("v1", "v2", "v3", "v4"):
        arm = AR.ARMS[name]
        for tax in (False, True):
            audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                     "skipped")}
            audit["costs"] = {"fills": [], "days": []}
            backtest_exposure(px, op, sc, dates, pc, mom20, sizing=arm.sizing, mode=arm.mode,
                              audit=audit, rebal=20, participation_cap=None,
                              drawdown_stop=None, tax_enabled=tax)
            f = audit["costs"]["fills"]
            off = [r for r in f if abs(r["fill_price"] * 100 - round(r["fill_price"] * 100)) > 1e-6]
            bad = [r for r in f if r["fill_price"] != sl.fill_price(
                r["reference_price"], sl.SLIPPAGE, r["side"] == "BUY")]
            case(f"4 {name} tax {'on' if tax else 'off'}: fills in whole paise, each fill_price "
                 f"of its reference", len(f) > 0 and not off and not bad,
                 f"{len(f)} fills, {len(off)} off the paisa, {len(bad)} not fill_price")

    n_fail = RESULTS.count(False)
    print(f"RESULT: {'PASS' if not n_fail else 'FAIL'} -- {len(RESULTS) - n_fail} of {len(RESULTS)} cases")
    sys.exit(1 if n_fail else 0)


CASES = {name[1:]: fn for name, fn in list(globals().items())
         if name.startswith("_") and callable(fn) and name[1:] in (
             "capital_axis", "dd_overlay", "drawdown_stop", "fixed_capital",
             "impact_pcap_axis", "tax_rules", "tax_total", "tradability_causality",
             "cache_key", "noise_harness", "buy_shortfall", "fill_open_sizing",
             "fill_price")}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CASES:
        print(__doc__)
        sys.exit(2)
    CASES[sys.argv[1]]()
