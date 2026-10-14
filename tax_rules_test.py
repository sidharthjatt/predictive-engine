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


if __name__ == "__main__":
    rc = main()
    print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
    sys.exit(rc)
