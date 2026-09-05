"""
make_trading_calendar.py -- derive the NSE trading calendar from the 58 universe.

WHY THIS ARTEFACT EXISTS RATHER THAN A RUN-TIME LOOKUP
    70 of 148 MidCap150 source files contain rows on NSE holidays, which put 237
    phantom dates into the mid union index (107 inside the backtest window). 5.0%
    of mid trades and 8.2% of mid rebalance decisions happened on days the market
    was shut. The 58 and 74 files are clean.

    The obvious fix, DDQ_Latest/config/trading_calendar.yaml, was verified and
    REJECTED -- see the note added at the top of that file. It claims 2000-2026
    coverage but parses to 2020-01-26 onward, lists 13 dates the market actually
    traded, and its weekend rule would delete 9 genuine special sessions.

    So the calendar is derived from the 58 universe's own observed dates, which
    are the NSE trading calendar as this project actually observes it: 58 large
    caps that trade every session, cross-checked against the 74.

    It is written to a FILE rather than read from the 58 panel at run time, so the
    dependency is explicit, dated, and reviewable. A silent run-time coupling
    would be invisible if the 58 universe were ever narrowed or re-sourced.

DERIVED FROM THE RAW FILES, NOT THE BUILT PANEL
    build_panel filters by this calendar, so deriving it from the built panel
    would be circular. Since build_panel keeps every row with a valid price, the
    58 panel's date index equals the union of the 58 raw files' dates -- verified
    below when the built panel is present.

Run: python3 results/make_trading_calendar.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config

SOURCE_DIR = config.RAW_DATA_DIR / "nifty50"
OUT = ROOT / "data" / "nse_trading_calendar.csv"
MIN_DAYS_PER_YEAR = 200      # NSE trades ~245-250; below 200 the calendar is broken


def build():
    dates = set()
    n_files = 0
    for f in sorted(SOURCE_DIR.glob("*.csv")):
        d = config.read_price_csv(f)[["date", "close"]].dropna()
        dates |= set(d["date"])
        n_files += 1
    return sorted(dates), n_files


def main():
    dates, n_files = build()
    print(f"derived {len(dates):,} trading days from {n_files} files in {SOURCE_DIR}")
    print(f"  range {dates[0].date()} -> {dates[-1].date()}")

    # Sanity: a year fully inside the range must have a plausible number of
    # sessions. This is an absolute bound, not a value tuned to any result.
    yrs = pd.Series([d.year for d in dates]).value_counts().sort_index()
    full = [y for y in yrs.index if y > dates[0].year and y < dates[-1].year]
    bad = [y for y in full if yrs[y] < MIN_DAYS_PER_YEAR]
    print(f"  sessions per full year: min {yrs[full].min()} ({yrs[full].idxmin()}), "
          f"max {yrs[full].max()} ({yrs[full].idxmax()})")
    if bad:
        raise SystemExit(f"ABORT: years with fewer than {MIN_DAYS_PER_YEAR} sessions: {bad}. "
                         "The 58 source data is incomplete; the calendar would be wrong.")

    # Cross-check against the built 58 panel when it exists: they must agree
    # exactly, which is what licenses deriving from the raw files.
    built = ROOT / "results" / "metrics" / "v5_expanding_cache.csv"
    if built.exists():
        b = set(pd.read_csv(built, usecols=["date"], parse_dates=["date"])["date"])
        if b != set(dates):
            raise SystemExit(f"ABORT: raw-derived calendar ({len(dates):,} dates) does not "
                             f"match the built 58 panel ({len(b):,} dates). "
                             f"only-raw {len(set(dates)-b)}, only-panel {len(b-set(dates))}")
        print(f"  cross-check vs built 58 panel: identical ({len(b):,} dates)")
    else:
        print("  cross-check vs built 58 panel: skipped (panel not built yet)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        # NO TIMESTAMP IN THIS HEADER, DELIBERATELY.
        #   This artefact is TRACKED in git, unlike results*/metrics/. A
        #   `generated_at: <now>` line made it a different file after every single
        #   pipeline run while all 6,574 dates stayed identical, so `git status`
        #   was never clean and the one line that could ever signal a real change
        #   was buried in noise that fired every time.
        #
        #   The file is now a pure function of its inputs: same raw CSVs in, same
        #   bytes out. When it changes, the calendar changed. When it was
        #   generated is what git already records, more reliably than the file
        #   could say about itself.
        #
        #   This also sharpens calendar_coverage_probe.py:132/251, which sha256s
        #   this file before and after its run and reports TRACKED CALENDAR
        #   UNCHANGED BY THIS RUN. That check could previously have failed on a
        #   timestamp alone.
        fh.write("# NSE trading calendar, derived artefact -- do not edit by hand.\n")
        fh.write(f"# generated_by: results/make_trading_calendar.py\n")
        fh.write(f"# derived_from: union of trading dates across {n_files} raw CSVs in\n")
        fh.write(f"#               {SOURCE_DIR.relative_to(ROOT)}  (the 58 universe)\n")
        fh.write(f"# rationale:    the 58 files contain no market-holiday rows, unlike 70 of\n")
        fh.write(f"#               the 148 MidCap150 files. DDQ_Latest/config/trading_calendar.yaml\n")
        fh.write(f"#               was verified and rejected; see the note at its head.\n")
        fh.write(f"# days: {len(dates)}   range: {dates[0].date()} to {dates[-1].date()}\n")
        fh.write("date\n")
        for d in dates:
            fh.write(f"{d.date()}\n")
    print(f"  wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
