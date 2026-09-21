"""
degeneracy_measure.py -- why does the published figure sit in the tail of its own
perturbed draws?
==============================================================================

WHAT THIS ANSWERS, AND WHY IT WAS ASKED

    price_noise_measure.py established, over 50 full re-runs on 2026-09-20/21:

        43 of 50 perturbed cells came in ABOVE their own unperturbed baseline
        (p = 1.0e-07 against a fair coin), 19 of 20 at sigma = 0.01%, and
        nifty100's published CAGR sits BELOW THE MINIMUM of its ten 0.01% draws
        by 0.31 points.

    A baseline below the minimum of its own draws is not a spread. A spread puts
    the unperturbed value somewhere inside the cloud. That says something
    DEGENERATE happens on the unperturbed input which any perturbation, however
    small, removes.

    THE MIDCAP150 HALF OF THAT READING DID NOT SURVIVE ITS OWN EXTENSION. At
    n = 5 its 27.80 was 0.23 below the minimum of its draws. Taking the block to
    n = 10 on 2026-09-21 -- which is what this investigation queued first, so the
    control would carry the same weight as nifty100 -- returned 27.69 on seed 909.
    So on midcap150 the published figure is an extreme draw, not an unreachable
    one, and the "below the minimum" framing now rests on nifty100 alone. The
    displacement itself is unchanged and is still strongly one-sided; it is the
    stronger of the two claims that went.

    This script counts the degeneracies. It does not remove them and it does not
    change the engine. Three candidate channels were named and all three are
    measured here:

        Part A  ties at the selection boundary
        Part B  exact-equality and threshold branches on the live path
        Part C  degenerate rows in the price panel itself

    WHAT IT FOUND, MEASURED 2026-09-21 ON BOTH UNIVERSES, 92 REBALANCES EACH:

        A and B are EMPTY or NEGLIGIBLE. C is LARGE. No channel was found that
        carries C to the output at the magnitude the displacement requires.

    THIS SCRIPT COUNTS. IT DOES NOT EXPLAIN. Nothing here establishes that the
    degeneracy in Part C causes the displacement; Part C is measured in the
    panel, and the only two paths by which it could reach the result -- A and B --
    are counted and come back too small. The gap between those two statements is
    the open question, and it is left open rather than filled with a story.

WHAT IS READ, AND WHAT IS NOT RE-RUN

    Parts A and B read the PUBLISHED score panel, u.score_cache, which is the
    panel the shipping artefacts were built from. They do not refit the ensemble:
    scoring is 15 of the 16 minutes of a run and nothing in A or B depends on
    re-deriving a score that is already on disk.

    Part C reads the vendor price farm directly and applies engine_core's own
    canonical_price to it, so the "close" it counts is the close the engine uses,
    not the raw adj_close. The perturbed farm is regenerated in place with the
    same construction price_noise_measure.py uses -- one numpy Generator per run,
    seeded by the noise seed, consumed in sorted filename order -- so a
    (sigma, seed) pair reproduces that harness's farm exactly.

    THE REPLICATION IS CHECKED, NOT ASSUMED. canonical_price's fallback count is
    printed on every scan. Unperturbed it must read 170 (nifty100) and 41
    (midcap150), which are the figures price_noise_measure.py's own docstring
    records from 2026-09-20. If those two numbers move, this script is reading a
    different farm and every count below it is uninterpretable.

    NO PERTURBED SCORE PANEL EXISTS. price_noise_measure.py deletes its work farm
    after each run and persists only metrics and a holdings overlap, so the five
    sigma = 0.01% runs cannot be re-interrogated for Part A without refitting the
    ensemble. That refit was NOT run, because Part A's unperturbed count is zero:
    a perturbed count can only also be zero, and would decide nothing.

USAGE

    ./venv/bin/python results/degeneracy_measure.py
    ./venv/bin/python results/degeneracy_measure.py --sigma 0.0001 --seed 101

    Writes diagnostics/degeneracy.txt. Nothing published is touched and no cache
    is written.
"""
import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "results"))

import config                                    # noqa: E402
from universes.registry import get as ureg_get   # noqa: E402
from engine_core import canonical_price, precompute  # noqa: E402

# Read from engine_core rather than restated, so a change there cannot leave this
# measurement quietly describing the wrong boundary.
from engine_core import TOP_N, BUFFER, REBAL     # noqa: E402

UNIVERSES = ("nifty100", "midcap150")

# The fallback counts price_noise_measure.py recorded on 2026-09-20. They are the
# check that this script is reading the same farm, not a target to reproduce.
EXPECTED_FALLBACK = {"nifty100": 170, "midcap150": 41}


def _panel(tag):
    """The published score panel, pivoted the way the engine pivots it."""
    u = ureg_get(tag)
    p = pd.read_csv(u.score_cache, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    return u, px, sc, bd


def _rebalances(px, sc, bd):
    """Yield (date, ranked scores) for every date the arm actually ranks on.

    The membership filter of TOUCH POINT 2 is omitted: both live universes run
    survivorship mode 'none', so MEMBERSHIP is None and the filter is a no-op.
    """
    for i, dt in enumerate(bd):
        if not (i % REBAL == 0 and i < len(bd) - 1):
            continue
        prices = px.loc[dt]
        s_ = sc.loc[dt].dropna()
        s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
        if len(s_) >= TOP_N:
            yield dt, s_


def part_a(out, tag):
    """Ties at the selection boundary, and how wide the boundary actually is.

    THE TIE IS RESOLVED AT results/test_exposure.py:456 --

        rk = s_.sort_values(ascending=False)

    pandas' default kind is 'quicksort', which is NOT stable, so equal scores are
    left in whatever order numpy's introsort happens to leave them. That is
    deterministic for a given input but it is not a rule: nothing decides which of
    two tied names is held. The count below says how often it is asked to.
    """
    u, px, sc, bd = _panel(tag)
    rows = []
    for dt, s_ in _rebalances(px, sc, bd):
        v = np.sort(s_.to_numpy())[::-1]
        rows.append({
            "date": str(dt.date()), "n_ranked": len(v),
            "tie_at_top": int(v[TOP_N - 1] == v[TOP_N]) if len(v) > TOP_N else 0,
            "tie_at_buffer": int(v[BUFFER - 1] == v[BUFFER]) if len(v) > BUFFER else 0,
            "dup_anywhere": len(v) - len(np.unique(v)),
            "gap_top": v[TOP_N - 1] - v[TOP_N] if len(v) > TOP_N else np.nan,
            "gap_buffer": v[BUFFER - 1] - v[BUFFER] if len(v) > BUFFER else np.nan,
        })
    d = pd.DataFrame(rows)
    out(f"  {tag}: {len(d)} rebalances, {int(d.n_ranked.sum())} ranked (name, rebalance) cells")
    out(f"    ties at the TOP_N={TOP_N} cut            : {int(d.tie_at_top.sum())}")
    out(f"    ties at the BUFFER={BUFFER} cut           : {int(d.tie_at_buffer.sum())}")
    out(f"    duplicate scores anywhere in the rank : {int(d.dup_anywhere.sum())}")
    out(f"    score gap at the TOP_N cut, min       : {d.gap_top.min():.3e}")
    out(f"    score gap at the TOP_N cut, median    : {d.gap_top.median():.3e}")
    out(f"    rebalances with that gap below 1e-4   : {int((d.gap_top < 1e-4).sum())}")
    return d


def part_b(out, tag):
    """The exact-equality and threshold branches the shipping arm actually reaches.

    Two sites, both on the v2 path (mode='breadth', sizing='invvol', research
    profile so participation_cap is None):

      test_exposure.py:426  expo = float((m > 0).mean())
          Exposure IS the fraction of names with strictly positive 20-day
          momentum. A name whose price is exactly unchanged over 20 sessions
          scores mom20 == 0.0 and is counted as NOT positive. Any perturbation
          moves it off zero, and roughly half of those land positive -- so this
          branch is one-sided and points the RIGHT way. The count says by how
          much, and the answer is: not nearly enough.

      test_exposure.py:485  ok = (not np.isnan(vs)) and vs > 0.01
          A name whose 60-day vol fails the guard gets weight 0 and is bought in
          no size at all.

    The third exact-equality site, canonical_price's `bad` mask at
    engine_core.py:213, is counted in Part C where the prices are in hand. It was
    already measured on 2026-09-20 and displaces delivered noise DOWNWARD while
    every outcome moved up, so it points the wrong way.
    """
    u, px, sc, bd = _panel(tag)
    mom20 = px / px.shift(20) - 1
    pc = precompute(px)
    n_cell = n_zero = n_slot = n_volfail = n_volzero = 0
    lift = []
    days = 0
    for dt, s_ in _rebalances(px, sc, bd):
        days += 1
        m = mom20.loc[dt].dropna()
        n, z, pos = len(m), int((m == 0.0).sum()), int((m > 0).sum())
        n_cell += n
        n_zero += z
        if n:
            lift.append(((pos + z / 2.0) / n) - (pos / n))
        v = pc["vol"].loc[dt]
        for s in list(s_.sort_values(ascending=False).index[:TOP_N]):
            vs = v.get(s, np.nan)
            n_slot += 1
            if np.isnan(vs) or not vs > 0.01:
                n_volfail += 1
            if (not np.isnan(vs)) and vs == 0.0:
                n_volzero += 1
    out(f"  {tag}: {days} rebalances")
    out(f"    breadth `m > 0` (test_exposure.py:426)")
    out(f"      (name, rebalance) cells tested        : {n_cell}")
    out(f"      mom20 EXACTLY 0.0, counted as not-up  : {n_zero}")
    out(f"      mean exposure lift if half flip up    : {np.mean(lift):.6f}")
    out(f"    invvol guard `vs > 0.01` (test_exposure.py:485)")
    out(f"      top-{TOP_N} slots tested                   : {n_slot}")
    out(f"      slots failing the guard, weight 0     : {n_volfail}")
    out(f"      vol60 EXACTLY 0.0                     : {n_volzero}")
    return n_zero, float(np.mean(lift))


def part_c(out, tag, sigma, seed):
    """Degenerate rows in the price panel, unperturbed and under one perturbed run.

    Counted on the canonical close -- the price the engine uses -- not on the raw
    adj_close, because canonical_price's fallback REINTRODUCES exact equality on
    the rows it reverts, and counting before it would miss that.
    """
    u = ureg_get(tag)
    files = sorted(pathlib.Path(u.prepare_data_dir()).glob("*.csv"))
    rng = np.random.default_rng(seed)
    n_rows = n_eq = n_gap = n_fallback = 0
    frames = []
    for f in files:
        df = pd.read_csv(f, parse_dates=["date"])
        if sigma > 0:
            a = df["adj_close"].to_numpy(dtype=float)
            df["adj_close"] = a * (1.0 + rng.normal(0.0, sigma, size=len(df)))
        n_rows += len(df)
        cp, bad = canonical_price(
            df[["date", "open", "high", "low", "close", "adj_close", "volume"]].copy())
        n_fallback += bad
        c = cp["close"].to_numpy(dtype=float)
        n_eq += int(np.sum(c[1:] == c[:-1]))
        if "_gap_filled" in df.columns:
            n_gap += int(pd.to_numeric(df["_gap_filled"], errors="coerce")
                         .fillna(0).astype(bool).sum())
        frames.append(pd.DataFrame({"date": cp["date"], "close": c}))
    allp = pd.concat(frames, ignore_index=True)
    g = allp.groupby("date")["close"]
    n_shared = int((g.transform("size") - g.transform("nunique")).gt(0).sum())
    n_dates = int((g.nunique() < g.size()).sum())
    label = "unperturbed" if sigma == 0 else f"sigma={sigma} seed={seed}"
    out(f"  {tag}, {label}: {n_rows:,} rows across {len(files)} symbols")
    out(f"    consecutive closes EXACTLY equal      : {n_eq:,}  ({100*n_eq/n_rows:.3f}%)")
    out(f"    rows the vendor flags _gap_filled     : {n_gap:,}  ({100*n_gap/n_rows:.3f}%)")
    out(f"    cells sharing a close with another")
    out(f"      symbol on the same date             : {n_shared:,}")
    out(f"      on this many dates                  : {n_dates:,} of {allp['date'].nunique():,}")
    out(f"    canonical_price fallback rows         : {n_fallback:,}")
    if sigma == 0 and n_fallback != EXPECTED_FALLBACK[tag]:
        out(f"    *** FALLBACK COUNT DISAGREES with the {EXPECTED_FALLBACK[tag]} recorded "
            f"2026-09-20. This script is not reading the same farm; the counts "
            f"above do not describe the shipped run.")
    return n_eq, n_shared, n_fallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sigma", type=float, default=0.0001,
                    help="perturbation level for the Part C comparison")
    ap.add_argument("--seed", type=int, default=101,
                    help="noise seed for the Part C comparison")
    a = ap.parse_args()

    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=" * 78)
    out("DEGENERACY ON THE UNPERTURBED INPUT")
    out("=" * 78)
    out(f"TOP_N={TOP_N}  BUFFER={BUFFER}  REBAL={REBAL}  "
        f"window {config.BT_START_DATE.date()} to {config.BT_END_DATE.date()}")
    out()
    out("PART A -- ties at the selection boundary")
    out()
    for t in UNIVERSES:
        part_a(out, t)
    out()
    out("PART B -- exact-equality and threshold branches on the live path")
    out()
    for t in UNIVERSES:
        part_b(out, t)
    out()
    out("PART C -- degenerate rows in the price panel")
    out()
    for t in UNIVERSES:
        part_c(out, t, 0.0, 0)
        part_c(out, t, a.sigma, a.seed)
    out()
    out("=" * 78)

    p = _ROOT / "diagnostics" / "degeneracy.txt"
    p.parent.mkdir(exist_ok=True)
    # naming: axis-free -- one count of the panel's own degeneracy. It reports on
    # the INPUT, not on a strategy result, so it varies over no arm, cadence,
    # profile or tax selection; both universes are named inside the file rather
    # than spelled into its name, as price_noise.txt does for the same reason.
    p.write_text("\n".join(lines) + "\n")
    print(f"written {p}")


if __name__ == "__main__":
    main()
