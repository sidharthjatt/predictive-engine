"""
mid_jackknife.py -- is MidCap150's edge fragile, or ordinary concentration?

THE QUESTION
    Mid beats its own equal-weight buy&hold by 2.34 points. Removing 8 specific
    names flips that to -1.84. But those 8 were SELECTED because they carried data
    artefacts, and artefacts correlate with large level shifts, so removing them is
    not a neutral test -- it is removing the biggest movers by construction.

    The honest comparison is against removals that were not chosen for their size:
      leave-one-out over all 148 names, and 200 random removals of 8 names.

    If a random 8 also flips the edge negative most of the time, the mid result is
    ordinary concentration and the 8-name result says nothing special. If only
    these 8 do it, the edge is genuinely fragile.

EDGE is measured the same way throughout: strategy CAGR minus the CAGR of the
equal-weight buy&hold of the SAME reduced universe, so both sides see the same
names. Removing a big winner hurts both, and only the difference is reported.

Reads only. Writes nothing.
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
from test_exposure import backtest_exposure

VOL_WIN = 60
N_RANDOM = 200
SEED = 0
CONTAM = ["PATANJALI", "LLOYDSME", "LAURUSLABS", "AIIL",
          "GVT&D", "SUZLON", "PERSISTENT", "JSWENERGY"]

PANEL = config.require_cache(ROOT/"results_mid"/"metrics"/"v_mid_expanding_cache.csv",
                             "/tmp/v_mid_expanding.csv", what="MidCap150 score panel")
P = pd.read_csv(PANEL, parse_dates=["date"])


def edge(drop=()):
    """(strategy CAGR, buy&hold CAGR, edge) with `drop` removed from the universe."""
    q = P[~P["symbol"].isin(set(drop))] if len(drop) else P
    px = q.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = q.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = q.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    pc = precompute(px); mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                     mode="breadth", target_vol=pv.loc[bd].median())
    bh = 1_000_000 * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    s = metrics(eq, "s", tc, n)["CAGR%"]
    b = metrics(bh, "b")["CAGR%"]
    return s, b, s - b


def pct(a, q):
    return float(np.percentile(a, q))


def main():
    syms = sorted(P["symbol"].unique())
    print("=" * 96)
    print(" MIDCAP150 JACKKNIFE -- is the edge fragile or ordinarily concentrated?")
    print("=" * 96)

    s0, b0, e0 = edge()
    print(f"\n BASELINE   strategy {s0:.2f}%   buy&hold {b0:.2f}%   edge {e0:+.2f} pt "
          f"({len(syms)} names in the panel)")
    sc_, bc_, ec_ = edge(CONTAM)
    print(f" THE 8      strategy {sc_:.2f}%   buy&hold {bc_:.2f}%   edge {ec_:+.2f} pt "
          f"  <- the non-neutral test")

    # ---------------------------------------------------------- leave-one-out
    print(f"\n" + "-" * 96)
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
        mark = "  <- one of the 8" if r["symbol"] in CONTAM else ""
        print(f"     {r['symbol']:<13} edge {r['edge']:+6.2f}  "
              f"(strategy {r['strategy']:.2f}%, buy&hold {r['buyhold']:.2f}%){mark}")

    # ---------------------------------------------------------- random 8-name
    print(f"\n" + "-" * 96)
    print(f" [2] {N_RANDOM} RANDOM REMOVALS OF 8 NAMES   (seed {SEED})")
    print("-" * 96)
    rng = np.random.default_rng(SEED)
    red = []
    for i in range(N_RANDOM):
        pick = list(rng.choice(syms, size=8, replace=False))
        red.append(edge(pick)[2])
        if (i + 1) % 50 == 0:
            print(f"     ... {i+1}/{N_RANDOM}", flush=True)
    red = np.array(red)
    print(f"\n   edge distribution over {N_RANDOM} random 8-name removals:")
    print(f"     min {red.min():+.2f}   p10 {pct(red,10):+.2f}   median {np.median(red):+.2f}   "
          f"p90 {pct(red,90):+.2f}   max {red.max():+.2f}")
    print(f"     removals that flip the edge negative: {int((red<0).sum())} of {N_RANDOM} "
          f"({(red<0).mean()*100:.1f}%)")

    below = float((red <= ec_).mean())
    print(f"\n   WHERE THE ACTUAL 8 SIT: edge {ec_:+.2f} pt")
    print(f"     random draws at or below it: {int((red<=ec_).sum())} of {N_RANDOM} "
          f"(percentile {below*100:.1f})")

    print("\n" + "=" * 96)
    print(" VERDICT")
    print("=" * 96)
    frac_neg = (red < 0).mean()
    if frac_neg > 0.5:
        print(f"  ORDINARY CONCENTRATION. A random 8 flips the edge negative "
              f"{frac_neg*100:.0f}% of the time,")
        print("  so the 8-name result carries no special information about fragility.")
    elif below < 0.05:
        print(f"  GENUINE FRAGILITY. A random 8 flips the edge negative only "
              f"{frac_neg*100:.0f}% of the time,")
        print(f"  and the actual 8 sit at the {below*100:.1f}th percentile -- far into the tail.")
    else:
        print(f"  MIXED. A random 8 flips the edge negative {frac_neg*100:.0f}% of the time and")
        print(f"  the actual 8 sit at the {below*100:.1f}th percentile. Read both numbers together.")


if __name__ == "__main__":
    main()
