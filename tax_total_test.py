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


if __name__ == "__main__":
    sys.exit(main())
