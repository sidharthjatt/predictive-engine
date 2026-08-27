"""
sizing_test.py -- equal-rupee sizing against inverse-vol, pre-registered.

WHY THIS IS BEING TESTED
    Inverse-vol sizing's justification rested on a validation that passed 4/4 on a
    panel degraded by the beta_60/idio_vol_60 density bug. On the corrected panel
    it went to 1/4: it beat equal-rupee on no seed set (-0.05, -0.01, -0.10), in
    neither sub-period (-0.04, -0.10), and at no vol window. A component carrying
    real money should not stay in on the strength of evidence that has since been
    withdrawn.

ACCEPT RULE, FIXED BEFORE ANY RESULT WAS SEEN
    A. Equal-rupee must not be worse on Sharpe in any of the three universes.
    B. It must not be worse on MaxDD by more than 2.0 points in any universe.
    C. Both sub-periods must hold in all three universes.
    D. The existing 4-part inverse-vol validation must be re-run with equal-rupee
       as the challenger, and equal-rupee must win at least 3 of 4.

    Pass all four -> switch to equal-rupee, because it is simpler and the
    incumbent has no positive evidence behind it.
    Fail any -> keep inverse-vol, and record that its justification is now the
    absence of a better alternative rather than a positive result.

    ONE BATCH. No risk-parity, no vol-targeting, no variants afterwards.

Only the weighting changes. Ranking, buffer, breadth exposure, costs, execution
timing and every parameter are identical between the two arms.
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
import config, config74, config_mid
from engine_core import metrics, precompute, BT_START, BT_END
from test_exposure import backtest_exposure

VOL_WIN = 60
MAX_DD_WORSE = 2.0          # gate B, points
UNIV = {
    "58":  (config.require_cache(ROOT/"results"/"metrics"/"v5_expanding_cache.csv",
                                 "/tmp/v5_expanding.csv", what="58 panel"),
            [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]),
    "74":  (config.require_cache(ROOT/"results74"/"metrics"/"v74_expanding_cache.csv",
                                 "/tmp/v74_expanding.csv", what="74 panel"),
            [("2019-2022", 2019, 2022), ("2023-2025", 2023, 2025)]),
    "mid": (config.require_cache(ROOT/"results_mid"/"metrics"/"v_mid_expanding_cache.csv",
                                 "/tmp/v_mid_expanding.csv", what="mid panel"),
            [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]),
}


def run(cache, sizing):
    p = pd.read_csv(cache, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    pc = precompute(px); mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, pv, mode="breadth",
                                     target_vol=pv.loc[bd].median(), sizing=sizing)
    return eq, tc, n


def sub(eq, y0, y1):
    s = eq[(eq.index.year >= y0) & (eq.index.year <= y1)]
    return metrics(s, "sub")


def main():
    print("=" * 100)
    print(" SIZING TEST -- equal-rupee (challenger) vs inverse-vol (incumbent)")
    print(" gates A-D fixed before running; one batch, no variants")
    print("=" * 100)

    res = {}
    print(f"\n {'universe':<6} {'sizing':<10} {'CAGR%':>7} {'Sharpe':>7} {'MaxDD%':>8} {'trades':>7}")
    for u, (cache, _) in UNIV.items():
        for sz in ("invvol", "equal"):
            eq, tc, n = run(cache, sz)
            m = metrics(eq, sz, tc, n)
            res[(u, sz)] = (eq, m)
            print(f" {u:<6} {sz:<10} {m['CAGR%']:>7.2f} {m['Sharpe']:>7.2f} "
                  f"{m['MaxDD%']:>8.2f} {n:>7}")

    print("\n" + "-" * 100)
    print(" GATE A -- equal-rupee not worse on Sharpe in ANY universe")
    print("-" * 100)
    A = {}
    for u in UNIV:
        i, e = res[(u, "invvol")][1], res[(u, "equal")][1]
        A[u] = e["Sharpe"] >= i["Sharpe"]
        print(f"   {u:<5} invvol {i['Sharpe']:.2f} -> equal {e['Sharpe']:.2f}  "
              f"({e['Sharpe']-i['Sharpe']:+.2f})   {'pass' if A[u] else 'FAIL'}")
    print(f"   -> Gate A {'PASS' if all(A.values()) else 'FAIL'}")

    print("\n" + "-" * 100)
    print(f" GATE B -- MaxDD not worse by more than {MAX_DD_WORSE} points in any universe")
    print("-" * 100)
    B = {}
    for u in UNIV:
        i, e = res[(u, "invvol")][1], res[(u, "equal")][1]
        worse = i["MaxDD%"] - e["MaxDD%"]      # positive = equal is deeper
        B[u] = worse <= MAX_DD_WORSE
        print(f"   {u:<5} invvol {i['MaxDD%']:.2f}% -> equal {e['MaxDD%']:.2f}%  "
              f"(worse by {worse:+.2f} pt)   {'pass' if B[u] else 'FAIL'}")
    print(f"   -> Gate B {'PASS' if all(B.values()) else 'FAIL'}")

    print("\n" + "-" * 100)
    print(" GATE C -- both sub-periods hold in all three universes")
    print("       'hold' = equal-rupee Sharpe not lower and CAGR not lower in that sub-period")
    print("-" * 100)
    C = {}
    for u, (_, periods) in UNIV.items():
        for lab, y0, y1 in periods:
            a = sub(res[(u, "invvol")][0], y0, y1)
            b = sub(res[(u, "equal")][0], y0, y1)
            ok = (b["Sharpe"] >= a["Sharpe"]) and (b["CAGR%"] >= a["CAGR%"])
            C[f"{u} {lab}"] = ok
            print(f"   {u:<5} {lab:<10} CAGR {a['CAGR%']:>7.2f} -> {b['CAGR%']:>7.2f}   "
                  f"Sharpe {a['Sharpe']:.2f} -> {b['Sharpe']:.2f}   {'pass' if ok else 'FAIL'}")
    print(f"   -> Gate C {'PASS' if all(C.values()) else 'FAIL'}")

    print("\n" + "-" * 100)
    print(" GATE D -- the 4-part validation, equal-rupee as challenger, must win 3 of 4")
    print("-" * 100)
    print("   Run separately: python3 results/engine_core.py")
    print("   Its T1-T4 already compare equal-rupee against inverse-vol directly.")
    print("   Reported alongside this table in the summary.")

    print("\n" + "=" * 100)
    print(f" GATES: A={'PASS' if all(A.values()) else 'FAIL'}  "
          f"B={'PASS' if all(B.values()) else 'FAIL'}  "
          f"C={'PASS' if all(C.values()) else 'FAIL'}  D=see engine_core")
    print("=" * 100)


if __name__ == "__main__":
    main()
