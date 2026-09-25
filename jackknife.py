"""
jackknife.py -- is a universe's edge over its own buy & hold concentrated in a few names?

    ./venv/bin/python jackknife.py --universe=nifty100            # baseline gate + cost, then stop
    ./venv/bin/python jackknife.py --universe=nifty100 --run      # the full measurement
    ./venv/bin/python jackknife.py --universe=midcap150 --run \
        '--named-drop=PATANJALI,LLOYDSME,LAURUSLABS,AIIL,GVT&D,SUZLON,PERSISTENT,JSWENERGY'

Replaces mid_jackknife.py and n100_jackknife.py (2026-09-24). Their edge() was the
same function with a different panel; this file is that function once, with the
universe taken from --universe. git history keeps both originals.

THE QUESTION
    Two tests, and an optional third:
      [1] leave-one-out over every name in the universe
      [2] 200 random removals of 8 names, as a control
      [3] --named-drop: one removal of a named set, placed in the [2] distribution.
    The midcap150 command above is the third arm mid_jackknife.py ran: the eight
    names flagged as carrying data artefacts. Choosing names by size and then
    reporting that removing them hurts is circular, which is what the random
    control in [2] exists to detect, so [3] is only ever read against [2].

EDGE is measured the same way throughout: strategy CAGR minus the CAGR of the
equal-weight buy & hold of the SAME reduced universe, so both sides see the same
names. Removing a big winner hurts both, and only the difference is reported.

REMOVAL SIZE IS 8 FOR EVERY UNIVERSE, WHICH IS NOT THE SAME FRACTION. It is held
constant in absolute terms so the random arms are comparable across universes; the
fraction is printed rather than corrected for.

THE BASELINE GATE runs first on every universe: this script's reconstruction must
reproduce the pipeline's own v2 and buy & hold equity curves in v2FINAL_equity.csv
EXACTLY -- same dates, same values -- or it stops. mid_jackknife.py had no such
gate; n100_jackknife.py had one at 0.05 CAGR points.

THE WINDOW IS config.BT_START_DATE .. BT_END_DATE, THE PIPELINE'S, SINCE 2026-09-25.
Both originals cut the backtest with engine_core's integer years (2019..2026),
which runs to the calendar's last session, 2026-06-08: 1,842 sessions against the
pipeline's 1,836 to 2026-05-29. Those six extra days are the whole of the gap the
old gate reported (v2 19.29 against 19.40 on nifty100, 27.75 against 28.78 on
midcap150). Every concentration figure measured with the old window was measured
over those 1,842 sessions.

Reads only. Writes nothing.
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
import engine_core as _ec
from engine_core import metrics, precompute
from test_exposure import backtest_exposure
import arms.registry as arm_reg
import profiles as _prof            # the run's execution-realism profile
from config import read_table  # the one CSV/parquet reader: config.read_table
from numerics import rolling_std  # platform-identical variance: results/numerics.py

VOL_WIN = 60
N_RANDOM = 200
SEED = 0
DROP_SIZE = 8
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE

_U = None
_P = None


def universe():
    """The universe named by --universe. Required; an unknown tag exits 2."""
    global _U
    if _U is None:
        from universes.registry import REGISTRY, argv_universes, check_tags
        picked = check_tags(argv_universes(sys.argv))
        if len(picked) != 1:
            raise SystemExit("usage: jackknife.py --universe=<tag> [--run] "
                             "[--named-drop=SYM,SYM,...]\n  exactly one universe. "
                             f"Valid: {', '.join(REGISTRY)}")
        _U = REGISTRY[picked[0]]
    return _U


def panel():
    """The universe's score panel, read on first use, not at import."""
    global _P
    if _P is None:
        u = universe()
        _ec.set_tradeability(u)     # as engine_v2_final does, before any backtest
        _P = read_table(config.require_cache(u.score_cache, what=f"{u.name} score panel"),
                        parse_dates=["date"])
    return _P


def named_drop():
    """The --named-drop symbols, or () when the flag is absent."""
    for a in sys.argv:
        if a.startswith("--named-drop="):
            return tuple(s for s in a.split("=", 1)[1].split(",") if s)
    return ()


def curves(drop=()):
    """(v2 equity, buy & hold equity, trade cost, trade count) with `drop` removed."""
    P = panel()
    q = P[~P["symbol"].isin(set(drop))] if len(drop) else P
    px = q.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = q.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = q.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
    pc = precompute(px); mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See profiles.research_only.
    eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                     mode="breadth", target_vol=pv.loc[bd].median(),
                                     participation_cap=_prof.research_only(__name__))
    bh = 1_000_000 * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    return eq, bh, tc, n


def edge(drop=()):
    """(strategy CAGR, buy & hold CAGR, edge) with `drop` removed from the universe."""
    eq, bh, tc, n = curves(drop)
    s = metrics(eq, "s", tc, n)["CAGR%"]
    b = metrics(bh, "b")["CAGR%"]
    return s, b, s - b


def official():
    """(v2 equity, buy & hold equity) as the pipeline recorded them."""
    eq = read_table(universe().metrics_dir / "v2FINAL_equity.csv",
                    parse_dates=["date"]).set_index("date")
    return arm_reg.equity_series(eq, "v2"), eq["buyhold"]


def pct(a, q):
    return float(np.percentile(a, q))


def baseline_gate():
    """Reproduce the published figures, or stop. Returns (edge, seconds)."""
    u = universe()
    print("=" * 96)
    print(" BASELINE GATE -- does this script's reconstruction reproduce the pipeline?")
    print("=" * 96)
    t0 = time.perf_counter()
    eq, bh, tc, n = curves()
    secs = time.perf_counter() - t0
    oeq, obh = official()
    s, b = metrics(eq, "s", tc, n)["CAGR%"], metrics(bh, "b")["CAGR%"]
    os_, ob_ = metrics(oeq, "s")["CAGR%"], metrics(obh, "b")["CAGR%"]
    e, oe_ = s - b, os_ - ob_

    print(f"\n   {'':<20}{'this script':>14}{'v2FINAL_equity':>17}{'delta':>10}")
    print(f"   {'strategy CAGR':<20}{s:>13.2f}%{os_:>16.2f}%{s-os_:>+10.2f}")
    print(f"   {'buy & hold CAGR':<20}{b:>13.2f}%{ob_:>16.2f}%{b-ob_:>+10.2f}")
    print(f"   {'edge':<20}{e:>+13.2f} {oe_:>+16.2f} {e-oe_:>+10.2f}")
    print(f"   sessions            {len(eq):>13}  {len(oeq):>15}  "
          f"({eq.index[0].date()} .. {eq.index[-1].date()})")

    bad = []
    for name, mine, off in (("strategy", eq, oeq), ("buy & hold", bh, obh)):
        same = (len(mine) == len(off) and (mine.index == off.index).all()
                and np.array_equal(mine.to_numpy(), off.to_numpy()))
        if not same:
            n_common = len(mine.index.intersection(off.index))
            bad.append((name, len(mine), len(off), n_common))
    if bad:
        print("\n" + "!" * 96)
        print(" GATE FAILED -- the reconstruction does not reproduce the pipeline exactly")
        print("!" * 96)
        for name, nm, no, nc in bad:
            print(f"   {name}: this script {nm} sessions, artefact {no}, {nc} dates in "
                  f"common; the curves are not identical")
        print("\n   Every leave-one-out number downstream is a difference between two")
        print("   curves built by THIS script. If its baseline is not the published")
        print("   strategy, those differences describe something else, and no")
        print(f"   concentration claim from them would be about the live {u.tag}.")
        print("   Stopping. This is a finding, not a tolerance to widen.")
        print("!" * 96, flush=True)
        sys.exit(1)

    print("\n   GATE PASSED -- v2 and buy & hold curves identical to v2FINAL_equity.csv.")
    return e, secs


def main():
    u = universe()
    named = named_drop()
    syms = sorted(panel()["symbol"].unique())
    unknown = [s for s in named if s not in syms]
    if unknown:
        raise SystemExit(f"--named-drop names symbols not in {u.tag}: {', '.join(unknown)}")
    print("=" * 96)
    print(f" {u.name.upper()} JACKKNIFE -- is the edge concentrated? ({len(syms)} names)")
    print("=" * 96)

    e0, secs = baseline_gate()

    n_calls = 1 + len(syms) + N_RANDOM + (1 if named else 0)
    print("\n" + "=" * 96)
    print(" COST")
    print("=" * 96)
    print(f"   one edge() call            : {secs:.1f} s")
    print(f"   full run                   : {n_calls} calls "
          f"(1 baseline + {len(syms)} leave-one-out + {N_RANDOM} random"
          f"{' + 1 named' if named else ''})")
    print(f"   estimate                   : {secs*n_calls/60:.0f} min "
          f"({secs*n_calls:.0f} s), assuming every call costs the baseline")
    print(f"   removal size {DROP_SIZE} is {DROP_SIZE/len(syms)*100:.1f}% of {u.tag}")

    if "--run" not in sys.argv:
        print("\n   Stopping here. Re-run with --run to execute the full measurement.")
        return

    if named:
        sn, bn, en = edge(named)
        print(f"\n NAMED DROP ({len(named)})  strategy {sn:.2f}%   buy&hold {bn:.2f}%   "
              f"edge {en:+.2f} pt   <- the non-neutral test")

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
        mark = "  <- in the named drop" if r["symbol"] in named else ""
        print(f"     {r['symbol']:<13} edge {r['edge']:+6.2f}  drop {e0-r['edge']:+6.2f}  "
              f"(strategy {r['strategy']:.2f}%, buy&hold {r['buyhold']:.2f}%){mark}")

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

    if named:
        below = float((red <= en).mean())
        frac_neg = (red < 0).mean()
        print(f"\n   WHERE THE NAMED DROP SITS: edge {en:+.2f} pt")
        print(f"     random draws at or below it: {int((red<=en).sum())} of {N_RANDOM} "
              f"(percentile {below*100:.1f})")
        print("\n" + "=" * 96)
        print(" VERDICT ON THE NAMED DROP")
        print("=" * 96)
        if frac_neg > 0.5:
            print(f"  ORDINARY CONCENTRATION. A random {DROP_SIZE} flips the edge negative "
                  f"{frac_neg*100:.0f}% of the time,")
            print("  so the named-drop result carries no special information about fragility.")
        elif below < 0.05:
            print(f"  GENUINE FRAGILITY. A random {DROP_SIZE} flips the edge negative only "
                  f"{frac_neg*100:.0f}% of the time,")
            print(f"  and the named drop sits at the {below*100:.1f}th percentile -- far into the tail.")
        else:
            print(f"  MIXED. A random {DROP_SIZE} flips the edge negative {frac_neg*100:.0f}% "
                  "of the time and")
            print(f"  the named drop sits at the {below*100:.1f}th percentile. Read both numbers together.")
    else:
        print("\n   This is a measurement, not a pre-registered experiment. There is no")
        print("   accept rule and no threshold to pass, so the numbers stand as they are.")


if __name__ == "__main__":
    main()
