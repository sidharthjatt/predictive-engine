"""
n100_jackknife.py -- is the Nifty 100 edge concentrated in a few names, the way
MidCap150's is?

THE QUESTION
    mid beats its own equal-weight buy&hold by about 2 points, and removing one
    name (LLOYDSME) takes that to roughly zero. Nobody has measured whether n100
    behaves the same way, and n100 is the universe quoted publicly.

    Two tests, no more:
      [1] leave-one-out over all 99 names
      [2] 200 random removals of 8 names, as a control

EDGE is measured the same way throughout: strategy CAGR minus the CAGR of the
equal-weight buy&hold of the SAME reduced universe, so both sides see the same
names. Removing a big winner hurts both, and only the difference is reported.

THERE IS DELIBERATELY NO "CONTAMINATED NAMES" ARM
    mid_jackknife.py has a third arm that removes eight specific MidCap150 names
    flagged as carrying data artefacts, and reports where that sits in the random
    distribution. There is no n100 equivalent, and building one would mean picking
    names by size and then reporting that removing them hurts -- which is the exact
    circularity the random control exists to detect. So that arm is absent, and
    with it the verdict block that depended on it. This script reports; it does not
    grade.

WHY edge() IS COPIED FROM mid_jackknife.py RATHER THAN IMPORTED
    mid_jackknife.py builds its PANEL at module level (line 44), so importing it
    loads the MID panel as a side effect. There is no way to get the function
    without that. The logic below is a verbatim copy with the n100 panel swapped
    in. DO NOT "tidy" this into an import -- it would silently measure mid.
    mid_jackknife.py is the provenance of the published mid figures and is not
    modified by this file.

REMOVAL SIZE IS 8 FOR BOTH UNIVERSES, WHICH IS NOT THE SAME FRACTION
    8 of 99 is 8.1% of n100; 8 of 148 is 5.4% of mid. Held constant in absolute
    terms so the two random arms are directly comparable; the fraction difference
    is printed rather than corrected for.

Reads only. Writes nothing. Run:
    python3 n100_jackknife.py            # baseline gate + timing estimate, then stop
    python3 n100_jackknife.py --run      # the full measurement
"""
import sys, time, warnings
sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config
from engine_core import metrics, precompute, BT_START, BT_END
from test_exposure import backtest_exposure
import arms.registry as arm_reg
import profiles as _prof            # the run's execution-realism profile
from config import read_table  # the one CSV/parquet reader: config.read_table
from numerics import rolling_std  # platform-identical variance: results/numerics.py

VOL_WIN = 60
N_RANDOM = 200
SEED = 0
DROP_SIZE = 8

# The published n100 figures this run must reproduce before anything else is
# believed. Read from the artefact at run time, not hardcoded -- these are only
# here so a reader knows what to expect.
OFFICIAL = ROOT / "results_nifty100" / "metrics" / "v2FINAL_equity.csv"
TOLERANCE = 0.05          # percentage points, on strategy and on buy&hold

_P = None


def panel():
    """The nifty100 score panel, read on first use.

    NOT AT IMPORT. This was a module-level read until 2026-09-23, so importing
    the file (check_all GATE 1 imports every module) read a cache, and on a tree
    without the panel the import itself failed.
    """
    global _P
    if _P is None:
        from universes.registry import REGISTRY
        _P = read_table(config.require_cache(REGISTRY["nifty100"].score_cache,
                                              what="Nifty 100 score panel"),
                         parse_dates=["date"])
    return _P


def edge(drop=()):
    """(strategy CAGR, buy&hold CAGR, edge) with `drop` removed from the universe."""
    P = panel()
    q = P[~P["symbol"].isin(set(drop))] if len(drop) else P
    px = q.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = q.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = q.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    pc = precompute(px); mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See profiles.research_only.
    eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                     mode="breadth", target_vol=pv.loc[bd].median(), participation_cap=_prof.research_only(__name__))
    bh = 1_000_000 * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    s = metrics(eq, "s", tc, n)["CAGR%"]
    b = metrics(bh, "b")["CAGR%"]
    return s, b, s - b


def official():
    """(strategy CAGR, buy&hold CAGR, edge) as the pipeline recorded them."""
    eq = read_table(OFFICIAL, parse_dates=["date"]).set_index("date")
    s = metrics(arm_reg.equity_series(eq, "v2"), "s")["CAGR%"]
    b = metrics(eq["buyhold"], "b")["CAGR%"]
    return s, b, s - b


def pct(a, q):
    return float(np.percentile(a, q))


def baseline_gate():
    """Reproduce the published n100 figures, or stop. Returns (edge, seconds)."""
    print("=" * 96)
    print(" BASELINE GATE -- does this script's reconstruction reproduce the pipeline?")
    print("=" * 96)
    t0 = time.perf_counter()
    s, b, e = edge()
    secs = time.perf_counter() - t0
    os_, ob_, oe_ = official()

    print(f"\n   {'':<20}{'this script':>14}{'v2FINAL_equity':>17}{'delta':>10}")
    print(f"   {'strategy CAGR':<20}{s:>13.2f}%{os_:>16.2f}%{s-os_:>+10.2f}")
    print(f"   {'buy & hold CAGR':<20}{b:>13.2f}%{ob_:>16.2f}%{b-ob_:>+10.2f}")
    print(f"   {'edge':<20}{e:>+13.2f} {oe_:>+16.2f} {e-oe_:>+10.2f}")

    bad = []
    if abs(s - os_) > TOLERANCE: bad.append(("strategy", s, os_, s - os_))
    if abs(b - ob_) > TOLERANCE: bad.append(("buy & hold", b, ob_, b - ob_))
    if bad:
        print("\n" + "!" * 96)
        print(" GATE FAILED -- the reconstruction does not reproduce the pipeline")
        print("!" * 96)
        for name, mine, off, d in bad:
            print(f"   {name}: this script {mine:.2f}%, artefact {off:.2f}%, "
                  f"difference {d:+.2f} pt (tolerance {TOLERANCE})")
        print("\n   Every leave-one-out number downstream is a difference between two")
        print("   curves built by THIS script. If its baseline is not the published")
        print("   strategy, those differences describe something else, and no")
        print("   concentration claim from them would be about the live n100.")
        print("   Stopping. This is a finding, not a tolerance to widen.")
        print("!" * 96, flush=True)
        sys.exit(1)

    print(f"\n   GATE PASSED -- both sides within {TOLERANCE} pt.")
    return e, secs


def main():
    syms = sorted(panel()["symbol"].unique())
    print("=" * 96)
    print(f" NIFTY 100 JACKKNIFE -- is the edge concentrated? ({len(syms)} names)")
    print("=" * 96)

    e0, secs = baseline_gate()

    n_calls = 1 + len(syms) + N_RANDOM
    print("\n" + "=" * 96)
    print(" COST")
    print("=" * 96)
    print(f"   one edge() call            : {secs:.1f} s")
    print(f"   full run                   : {n_calls} calls "
          f"(1 baseline + {len(syms)} leave-one-out + {N_RANDOM} random)")
    print(f"   estimate                   : {secs*n_calls/60:.0f} min "
          f"({secs*n_calls:.0f} s), assuming every call costs the baseline")
    print(f"   removal size {DROP_SIZE} is {DROP_SIZE/len(syms)*100:.1f}% of n100, "
          f"against {DROP_SIZE/148*100:.1f}% of mid's 148")

    if "--run" not in sys.argv:
        print("\n   Stopping here. Re-run with --run to execute the full measurement.")
        return

    # ---------------------------------------------------------- leave-one-out
    print("\n" + "-" * 96)
    print(f" [1] LEAVE-ONE-OUT over all {len(syms)} names")
    print("-" * 96)
    rows = []
    for i, s in enumerate(syms, 1):
        st, bh, ed = edge([s])
        rows.append({"symbol": s, "strategy": st, "buyhold": bh, "edge": ed})
        if i % 25 == 0:
            print(f"     ... {i}/{len(syms)}", flush=True)
    lo = pd.DataFrame(rows)
    e = lo["edge"].to_numpy()
    print(f"\n   edge distribution over {len(e)} single-name removals:")
    print(f"     min {e.min():+.2f}   p10 {pct(e,10):+.2f}   median {np.median(e):+.2f}   "
          f"p90 {pct(e,90):+.2f}   max {e.max():+.2f}")
    print(f"     removals that flip the edge negative: {int((e<0).sum())} of {len(e)} "
          f"({(e<0).mean()*100:.1f}%)")
    print("\n   most damaging single removals:")
    for _, r in lo.nsmallest(8, "edge").iterrows():
        print(f"     {r['symbol']:<13} edge {r['edge']:+6.2f}  drop {e0-r['edge']:+6.2f}  "
              f"(strategy {r['strategy']:.2f}%, buy&hold {r['buyhold']:.2f}%)")

    # ---------------------------------------------------------- random 8-name
    print("\n" + "-" * 96)
    print(f" [2] {N_RANDOM} RANDOM REMOVALS OF {DROP_SIZE} NAMES   (seed {SEED})")
    print("-" * 96)
    rng = np.random.default_rng(SEED)
    red = []
    for i in range(N_RANDOM):
        pick = list(rng.choice(syms, size=DROP_SIZE, replace=False))
        red.append(edge(pick)[2])
        if (i + 1) % 50 == 0:
            print(f"     ... {i+1}/{N_RANDOM}", flush=True)
    red = np.array(red)
    print(f"\n   edge distribution over {N_RANDOM} random {DROP_SIZE}-name removals:")
    print(f"     min {red.min():+.2f}   p10 {pct(red,10):+.2f}   median {np.median(red):+.2f}   "
          f"p90 {pct(red,90):+.2f}   max {red.max():+.2f}")
    print(f"     removals that flip the edge negative: {int((red<0).sum())} of {N_RANDOM} "
          f"({(red<0).mean()*100:.1f}%)")

    # ---------------------------------------------------------- summary
    worst = lo.nsmallest(1, "edge").iloc[0]
    print("\n" + "=" * 96)
    print(" SUMMARY -- reported, not graded")
    print("=" * 96)
    print(f"   baseline edge                        {e0:+.2f} pt")
    print(f"   largest single-name drop             {e0-worst['edge']:+.2f} pt "
          f"({worst['symbol']}, edge -> {worst['edge']:+.2f})")
    print(f"   single removals flipping it negative {int((e<0).sum())} of {len(e)}")
    print(f"   random-{DROP_SIZE} removals flipping it negative  "
          f"{int((red<0).sum())} of {N_RANDOM}")
    print("\n   This is a measurement, not a pre-registered experiment. There is no")
    print("   accept rule and no threshold to pass, so the numbers stand as they are.")


if __name__ == "__main__":
    main()
