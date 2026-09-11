"""
mid_topn_test.py -- does a larger TOP_N fix MidCap150's single-name concentration?

WHY
    Mid's edge over its own buy&hold rests on one name: removing LLOYDSME takes it
    from +1.99 to +0.02. TOP_N=8 out of 148 names is the top 5.4%, against 13.8%
    on the 58 universe where the parameter was originally chosen. Equal
    selectivity would be about TOP_N=20.

ACCEPT RULE, FIXED BEFORE ANY RESULT WAS SEEN
    A larger TOP_N replaces 8 only if it:
      (a) does not lower Sharpe,
      (b) does not worsen MaxDD by more than 2.0 points,
      (c) reduces the single-name concentration -- the leave-one-out edge drop for
          the largest contributor -- to under HALF its current value.
    If no value satisfies all three, keep 8 and record that concentration is a
    property of the design rather than something a parameter fixes.

    BUFFER scales with TOP_N (2x, as it is now). Nothing else changes.

CONCENTRATION IS MEASURED, NOT ASSUMED
    For every TOP_N the leave-one-out is run over all 148 names and the LARGEST
    edge drop is taken, so the "largest contributor" is identified by the test
    itself rather than carried over from TOP_N=8. Edge is always strategy CAGR
    minus the CAGR of the equal-weight buy&hold of the SAME reduced universe, so
    removing a big winner hurts both sides and only the difference is reported.

Nothing is written and no default is changed: TOP_N and BUFFER are set on the
test_exposure module in memory for the duration of each run.
"""
import sys, warnings
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
import test_exposure
from test_exposure import backtest_exposure
import profiles as _prof            # the run's execution-realism profile

VOL_WIN = 60
TOPNS = [8, 12, 16, 20]
MAX_DD_WORSE = 2.0
CONCENTRATION_FACTOR = 0.5

PANEL = config.require_cache(ROOT/"results_mid"/"metrics"/"v_mid_expanding_cache.csv",
                             "/tmp/v_mid_expanding.csv", what="MidCap150 score panel")
P = pd.read_csv(PANEL, parse_dates=["date"])


def run(drop=(), top_n=8):
    test_exposure.TOP_N = top_n
    test_exposure.BUFFER = 2 * top_n
    q = P[~P["symbol"].isin(set(drop))] if len(drop) else P
    px = q.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = q.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = q.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    pc = precompute(px); m20 = px / px.shift(20) - 1
    ix = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = ix.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, m20, pv, mode="breadth",
                                     target_vol=pv.loc[bd].median(), participation_cap=_prof.participation_cap())
    bh = 1_000_000 * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    m = metrics(eq, "s", tc, n); mb = metrics(bh, "b")
    return m, mb, m["CAGR%"] - mb["CAGR%"], n


def main():
    syms = sorted(P["symbol"].unique())
    print("=" * 96)
    print(" MIDCAP150 -- TOP_N test, gates fixed before running")
    print("=" * 96)

    base = {}
    print(f"\n {'TOP_N':<7}{'BUFFER':<8}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>9}"
          f"{'trades':>8}{'buy&hold':>10}{'edge':>8}")
    for t in TOPNS:
        m, mb, e, n = run(top_n=t)
        base[t] = (m, mb, e, n)
        print(f" {t:<7}{2*t:<8}{m['CAGR%']:>8.2f}{m['Sharpe']:>8.2f}{m['MaxDD%']:>9.2f}"
              f"{n:>8}{mb['CAGR%']:>10.2f}{e:>+8.2f}")

    print("\n" + "-" * 96)
    print(" LEAVE-ONE-OUT over all 148 names, per TOP_N -- largest single-name dependency")
    print("-" * 96)
    conc = {}
    for t in TOPNS:
        e0 = base[t][2]
        drops = []
        for s in syms:
            drops.append((s, e0 - run([s], top_n=t)[2]))
        drops.sort(key=lambda x: -x[1])
        conc[t] = drops
        top = drops[:3]
        print(f"\n  TOP_N={t:<3} baseline edge {e0:+.2f} pt")
        for s, d in top:
            print(f"     removing {s:<13} edge -> {e0-d:+6.2f}   drop {d:+.2f} pt")
        print(f"     largest drop {drops[0][1]:.2f} pt ({drops[0][0]})   "
              f"names whose removal flips the edge negative: "
              f"{sum(1 for _, d in drops if e0 - d < 0)} of {len(drops)}")

    print("\n" + "=" * 96)
    print(" GATES")
    print("=" * 96)
    b8, c8 = base[8], conc[8][0][1]
    print(f"\n  incumbent TOP_N=8: Sharpe {b8[0]['Sharpe']:.2f}, MaxDD {b8[0]['MaxDD%']:.2f}%, "
          f"largest LOO drop {c8:.2f} pt")
    print(f"  gate (c) threshold: drop must be < {c8*CONCENTRATION_FACTOR:.2f} pt "
          f"(half the incumbent's)")
    print(f"\n  {'TOP_N':<7}{'(a) Sharpe':>20}{'(b) MaxDD':>22}{'(c) largest LOO drop':>24}{'verdict':>10}")
    winners = []
    for t in TOPNS[1:]:
        m = base[t][0]
        d = conc[t][0][1]
        a = m["Sharpe"] >= b8[0]["Sharpe"]
        bb = (b8[0]["MaxDD%"] - m["MaxDD%"]) <= MAX_DD_WORSE
        c = d < c8 * CONCENTRATION_FACTOR
        ok = a and bb and c
        winners.append((t, ok))
        sh = f"{m['Sharpe']:.2f} vs {b8[0]['Sharpe']:.2f} {'ok' if a else 'FAIL'}"
        dd = f"{m['MaxDD%']:.2f} vs {b8[0]['MaxDD%']:.2f} {'ok' if bb else 'FAIL'}"
        cc = f"{d:.2f} vs <{c8*CONCENTRATION_FACTOR:.2f} {'ok' if c else 'FAIL'}"
        print(f"  {t:<7}{sh:>20}{dd:>22}{cc:>24}{'PASS' if ok else 'FAIL':>10}")
    print()
    if any(ok for _, ok in winners):
        print("  A larger TOP_N passes all three gates: " +
              ", ".join(str(t) for t, ok in winners if ok))
    else:
        print("  NO value of TOP_N satisfies all three gates. Keep TOP_N=8, and record")
        print("  that the concentration is a property of the design -- a cross-sectional")
        print("  ranking system holding the top few names of a universe whose returns are")
        print("  themselves concentrated -- rather than something this parameter fixes.")


if __name__ == "__main__":
    main()
