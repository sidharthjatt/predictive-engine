"""
calendar_coverage_probe.py -- can a coverage threshold replace the 58-derived
trading calendar?

WHAT THIS PROBE DOES NOW. It reads data/nse_trading_calendar.csv and the raw
files of each selected universe, and asks whether any single coverage threshold
could reproduce the tracked calendar from those files. It writes one diagnostic,
diagnostics/calendar_coverage_probe.txt. It does not write the calendar, and it
hashes the file before and after its own run to prove that.

THE QUESTION IT WAS BUILT TO SETTLE, AND WHY THAT QUESTION IS CLOSED. The NSE
trading calendar was derived from the RETIRED 58 universe's raw files, by
results/make_trading_calendar.py -- a script DELETED ON 2026-09-11, commit
2fe48ff, along with the 58 and its raw files. engine_core._load_calendar() still
raises without the resulting artefact, for EVERY universe. The candidate
decoupling, specified in experiments/CALENDAR_DECOUPLE_SPEC.txt, was: build the
calendar from the selected universe's own files and drop any date carried by
fewer than COVERAGE_MIN of the files active that year.

That design was refuted by this probe before it was built, and the calendar is
now frozen tracked source data rather than a derived artefact. THE PROBE IS
STILL WORTH RUNNING: it is the standing evidence for why the calendar is frozen,
and it re-measures that evidence against whatever raw files are on disk today.

THE ANSWER THIS SCRIPT PRODUCES: THE DESIGN IS REFUTED, AND NOT BY A MARGIN THAT
A DIFFERENT THRESHOLD WOULD CLOSE. The verdict is computed from the measured
rows, not written here.

WHY A SINGLE THRESHOLD CANNOT WORK -- THE SHAPE OF THE TEST
    Split every date in a universe's union by whether the tracked 58-derived
    calendar contains it. A threshold T reproduces that calendar exactly if and
    only if

        max(coverage of the EXCLUDED dates)  <  T  <=  min(coverage of the
                                                        INCLUDED dates)

    If the two groups OVERLAP -- if some date the calendar contains is more
    thinly covered than some date it does not -- then no T exists. That is an
    empty-interval proof, and it settles the question for ALL thresholds at once
    rather than testing them one at a time.

WHAT THIS MEASURES, AND OVER WHAT RANGE
    The FULL range the files cover, roughly 2000 to 2026, not the backtest
    window. That distinction is the whole point: over 2019-01-01 .. 2026-05-29
    a 50% threshold DOES reproduce the calendar exactly, which is what made the
    design look sound. The pre-2019 region had never been compared, and it is
    where the design fails.

WHAT THIS DOES NOT ESTABLISH
    That the 58-derived calendar is CORRECT about the dates where they disagree.
    No external NSE source is consulted here or anywhere in this project. Three
    of the binding dates are Saturdays and whether they were genuine sessions is
    untested. This script establishes only that a coverage filter cannot
    REPRODUCE the existing calendar.

    That no decoupling is possible. It refutes ONE design -- a single global
    coverage threshold. Other designs were not measured and are not ruled out.

Reads only. Writes diagnostics/calendar_coverage_probe.txt. The tracked calendar
is read and hashed, never written.
"""
import hashlib
import sys
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import pandas as pd

import config
from universes.registry import REGISTRY
from config import read_table  # the one CSV/parquet reader: config.read_table

TRACKED = ROOT / "data" / "nse_trading_calendar.csv"
OUT = ROOT / "diagnostics" / "calendar_coverage_probe.txt"

# The threshold the spec proposed. Reported, not relied upon: the empty-interval
# proof below is threshold-independent and is what carries the verdict.
COVERAGE_MIN = 0.50

# The reported window, for the contrast between in-window and full-range results.
WIN_LO, WIN_HI = pd.Timestamp("2019-01-01"), pd.Timestamp("2026-05-29")

# The DATA DIRECTORY comes from universes/registry.py -- the single definition.
# The LABEL stays local: it is printed into
# diagnostics/calendar_coverage_probe.txt, and the sibling scripts spell the same
# two universes differently. Labels are presentation; paths are facts.
# NOTE the tuple order here is (label, dir), the reverse of the leakage checks'
# (dir, label). That inconsistency is preserved rather than tidied, because
# changing it would touch this file's unpacking for no behavioural gain.
LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {u.tag: (LABELS[u.tag], u.data_dir)
             for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_universe(src):
    """Per-file sets of dates carrying a non-null close."""
    m = {}
    for f in sorted(Path(src).glob("*.csv")):
        d = config.read_price_csv(f)[["date", "close"]].dropna()
        m[f.stem] = set(d["date"])
    return m


def coverage(m):
    """date -> fraction of files ACTIVE THAT YEAR carrying it, plus per-year state.

    ACTIVE THAT YEAR: a file with at least one non-null close in that year. The
    denominator is per-year so a name listed only from 2025 does not drag down
    the fraction of every 2019 date.
    """
    by = defaultdict(lambda: {"cnt": Counter(), "syms": set()})
    for sym, ds in m.items():
        yrs = set()
        for d in ds:
            by[d.year]["cnt"][d] += 1
            yrs.add(d.year)
        for y in yrs:
            by[y]["syms"].add(sym)
    frac, peryear = {}, {}
    for y, v in by.items():
        ns = len(v["syms"])
        peryear[y] = ns
        for d, c in v["cnt"].items():
            frac[d] = c / ns
    return frac, peryear, {y: v["cnt"] for y, v in by.items()}


def main():
    t0 = time.time()
    lines = []
    def w(s=""):
        print(s, flush=True)
        lines.append(s)

    before = sha256(TRACKED)
    cal = set(pd.to_datetime(read_table(TRACKED, comment="#")["date"]))

    w("=" * 100)
    w(" CAN A COVERAGE THRESHOLD REPLACE THE 58-DERIVED TRADING CALENDAR?")
    w("=" * 100)
    w()
    w(f"  tracked calendar   {TRACKED.relative_to(ROOT)}")
    w(f"    {len(cal):,} dates   {min(cal).date()} .. {max(cal).date()}")
    w(f"    SHA256 {before}")
    w(f"  spec               experiments/CALENDAR_DECOUPLE_SPEC.txt")
    w(f"  threshold reported COVERAGE_MIN = {COVERAGE_MIN}")
    w(f"    The verdict below does NOT depend on this value. See the")
    w(f"    empty-interval test, which settles all thresholds at once.")

    verdicts = {}
    for tag, (label, src) in UNIVERSES.items():
        # THE FARM IS BUILT ON DEMAND under cache/<tag>/ since 2026-09-23;
        # u.data_dir is only its path and is empty on a fresh tree.
        src = REGISTRY[tag].prepare_data_dir()
        w(f"\n{'=' * 100}\n {label} ({tag})\n{'=' * 100}")
        m = load_universe(src)
        frac, peryear, cnt = coverage(m)
        w(f"  {len(m)} constituent files   union {len(frac):,} dates   "
          f"{min(frac).date()} .. {max(frac).date()}")

        # ---------------------------------------------------- per-year identity
        filt = {d for d, f in frac.items() if f >= COVERAGE_MIN}
        w(f"\n  PER-YEAR IDENTITY AT COVERAGE_MIN = {COVERAGE_MIN}")
        w(f"    {'year':6} {'active':>7} {'58 cal':>7} {'filtered':>9} "
          f"{'filt-only':>10} {'cal-only':>9}")
        years = sorted({d.year for d in cal} | {d.year for d in frac})
        fails = []
        for y in years:
            c = {d for d in cal if d.year == y}
            f_ = {d for d in filt if d.year == y}
            fo, co = sorted(f_ - c), sorted(c - f_)
            flag = "  <-- FAILS" if (fo or co) else ""
            w(f"    {y:6} {peryear.get(y, 0):7} {len(c):7} {len(f_):9} "
              f"{len(fo):10} {len(co):9}{flag}")
            if fo or co:
                fails.append((y, fo, co))

        fo_all, co_all = sorted(filt - cal), sorted(cal - filt)
        w(f"\n    FULL RANGE: filtered {len(filt):,}   tracked {len(cal):,}   "
          f"filtered-only {len(fo_all)}   calendar-only {len(co_all)}")
        inwin_f = {d for d in filt if WIN_LO <= d <= WIN_HI}
        inwin_c = {d for d in cal if WIN_LO <= d <= WIN_HI}
        w(f"    IN WINDOW {WIN_LO.date()} .. {WIN_HI.date()}: "
          f"filtered {len(inwin_f):,}   tracked {len(inwin_c):,}   "
          f"differences {len(inwin_f ^ inwin_c)}")

        # -------------------------------------------------- the differing dates
        if fo_all or co_all:
            w(f"\n  EVERY DIFFERING DATE, LISTED. Not characterised, listed.")
            for d in fo_all:
                w(f"    {d.date()} {d.strftime('%a')}  {frac[d]*100:6.2f}%  "
                  f"in FILTERED set, ABSENT from the 58 calendar")
            for d in co_all:
                if d in frac:
                    w(f"    {d.date()} {d.strftime('%a')}  {frac[d]*100:6.2f}%  "
                      f"in the 58 CALENDAR, ABSENT from filtered set")
                else:
                    w(f"    {d.date()} {d.strftime('%a')}     ----  "
                      f"in the 58 CALENDAR, NOT IN THIS UNIVERSE'S UNION AT ALL "
                      f"(missing data, not a filtering decision)")

        # ------------------------------------------ the threshold-independent test
        inc = sorted((frac[d], d) for d in frac if d in cal)
        exc = sorted((frac[d], d) for d in frac if d not in cal)
        w(f"\n  THE EMPTY-INTERVAL TEST -- settles ALL thresholds at once")
        w(f"    dates the calendar HAS   {len(inc):6,}   coverage "
          f"{inc[0][0]*100:6.2f}% .. {inc[-1][0]*100:6.2f}%")
        w(f"    dates the calendar LACKS {len(exc):6,}   coverage "
          f"{exc[0][0]*100:6.2f}% .. {exc[-1][0]*100:6.2f}%")
        w(f"    a threshold T reproduces the calendar iff "
          f"{exc[-1][0]*100:.2f}% < T <= {inc[0][0]*100:.2f}%")
        ok = exc[-1][0] < inc[0][0]
        if ok:
            w(f"    -> such a T EXISTS. Interval width "
              f"{(inc[0][0]-exc[-1][0])*100:.2f} points.")
        else:
            w(f"    -> THE INTERVAL IS EMPTY. The groups OVERLAP by "
              f"{(exc[-1][0]-inc[0][0])*100:.2f} points.")
            w(f"       NO VALUE OF COVERAGE_MIN REPRODUCES THE CALENDAR.")
        verdicts[tag] = ok

        w(f"\n    THE BINDING CASES -- calendar dates too thinly covered to keep:")
        for f_, d in inc[:4]:
            w(f"      {d.date()} {d.strftime('%a')}  {f_*100:6.2f}%  "
              f"the calendar HAS it")
        w(f"    against the most heavily covered dates the calendar LACKS:")
        for f_, d in exc[-3:][::-1]:
            w(f"      {d.date()} {d.strftime('%a')}  {f_*100:6.2f}%  "
              f"the calendar LACKS it")

    # ------------------------------------------------------------------ verdict
    w(f"\n{'=' * 100}")
    w(" VERDICT -- computed from the rows above, not written into this script")
    w(f"{'=' * 100}\n")
    for tag in UNIVERSES:
        w(f"  {tag:6} a reproducing threshold exists: {verdicts[tag]}")
    if not any(verdicts.values()):
        w(f"\n  DETERMINATION: THE DESIGN IS REFUTED IN BOTH UNIVERSES, AND IT IS NOT")
        w(f"  A TUNING PROBLEM. The included and excluded coverage ranges overlap, so")
        w(f"  no threshold separates them. Changing COVERAGE_MIN changes WHICH dates")
        w(f"  are wrong; it cannot make none of them wrong.")
    elif all(verdicts.values()):
        w(f"\n  DETERMINATION: a reproducing threshold exists in both universes.")
    else:
        w(f"\n  DETERMINATION: SPLIT RESULT. The universes disagree; read the rows.")

    w(f"\n  WHAT THIS DOES NOT ESTABLISH:")
    w(f"    - that the 58-derived calendar is CORRECT about the dates where they")
    w(f"      disagree. No external NSE source was consulted. Several of the")
    w(f"      binding dates are Saturdays and whether they were genuine sessions")
    w(f"      is untested.")
    w(f"    - that no decoupling is possible. This refutes ONE design, a single")
    w(f"      global coverage threshold. Others were not measured.")
    w(f"    - anything about panels, scores or published figures. No code that")
    w(f"      touches them was run.")

    after = sha256(TRACKED)
    w(f"\n  TRACKED CALENDAR UNCHANGED BY THIS RUN: {before == after}")
    w(f"  wall clock {time.time() - t0:.0f} sec")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwritten -> {OUT}")


if __name__ == "__main__":
    main()
