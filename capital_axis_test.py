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
                                     participation_cap=None, **kw)
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


if __name__ == "__main__":
    sys.exit(main())
