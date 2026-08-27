"""
param_surface.py -- map the TOP_N x BUFFER surface. Diagnostic, not optimisation.

THE QUESTION
    TOP_N=8, BUFFER=16 predates this project's pre-registration discipline and
    there is no record of how it was chosen. That gap cannot be closed
    retrospectively, but it can be measured.

    READINGS FIXED BEFORE RUNNING:
      - If (8,16) sits near the median of the grid and its neighbourhood is flat,
        the base design is not tuned. That is the finding.
      - If (8,16) sits above the 90th percentile with sharp fall-off around it,
        the base design was likely selected on this data, and the headline numbers
        are optimistic by roughly the amount the grid spread indicates.

    NOTHING CHANGES EITHER WAY. If a cell beats (8,16) that is a data point about
    the surface, not a recommendation: switching to it would be selecting a
    parameter on the same data that produced the result, which is precisely the
    failure this measurement exists to detect.

BUFFER IS NOT LOCKED TO 2xTOP_N
    The live config ties them, so a grid that preserved the tie would not show
    whether the tie itself is load-bearing. BUFFER is swept independently as
    {1.0, 1.5, 2.0, 3.0} x TOP_N, rounded, skipping any cell whose BUFFER exceeds
    the universe size.

NEIGHBOURHOOD
    The grid is not a rectangular lattice in absolute (TOP_N, BUFFER), because
    BUFFER is defined as a ratio of TOP_N. Neighbours are therefore taken on the
    (TOP_N index, ratio index) lattice: for (8, 2.0x) they are (5, 2.0x),
    (12, 2.0x), (8, 1.5x) and (8, 3.0x).

Reads the existing clean panels. Writes nothing. Changes no default.
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
from engine_core import metrics, precompute
import test_exposure
from test_exposure import backtest_exposure

VOL_WIN = 60
TOPNS = [5, 8, 12, 16, 20]
RATIOS = [1.0, 1.5, 2.0, 3.0]
BASE = (8, 16)          # the incumbent, TOP_N=8 at the 2.0x ratio

UNIV = [
    ("58",       ROOT/"results"/"metrics"/"v5_expanding_cache.csv",   "/tmp/v5_expanding.csv",  2019, 2026),
    ("74",       ROOT/"results74"/"metrics"/"v74_expanding_cache.csv", "/tmp/v74_expanding.csv", 2019, 2025),
    ("mid 2019", ROOT/"results_mid"/"metrics"/"v_mid_expanding_cache.csv", "/tmp/v_mid_expanding.csv", 2019, 2026),
    ("mid 2016", ROOT/"results_mid"/"metrics"/"v_mid_expanding_cache.csv", "/tmp/v_mid_expanding.csv", 2016, 2026),
]


def load(perm, tmp):
    p = pd.read_csv(config.require_cache(perm, tmp, what="score panel"), parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return px, op, sc


def cell(px, op, sc, y0, y1, top_n, buf):
    test_exposure.TOP_N = top_n
    test_exposure.BUFFER = buf
    bd = px.index[(px.index.year >= y0) & (px.index.year <= y1)]
    pc = precompute(px); m20 = px / px.shift(20) - 1
    ix = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = ix.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, m20, pv, mode="breadth",
                                     target_vol=pv.loc[bd].median())
    bh = 1_000_000 * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    m = metrics(eq, "s", tc, n); mb = metrics(bh, "b")
    return dict(top_n=top_n, buffer=buf, cagr=m["CAGR%"], sharpe=m["Sharpe"],
                maxdd=m["MaxDD%"], trades=n, bh=mb["CAGR%"],
                edge=m["CAGR%"] - mb["CAGR%"])


def pctile_rank(vals, x):
    """Percentage of cells at or below x."""
    v = np.asarray(vals)
    return float((v <= x).mean() * 100)


def main():
    print("=" * 104)
    print(" TOP_N x BUFFER SURFACE -- diagnostic. No default is changed by this script.")
    print("=" * 104)

    for tag, perm, tmp, y0, y1 in UNIV:
        px, op, sc = load(perm, tmp)
        nsym = px.shape[1]
        rows = []
        for t in TOPNS:
            for r in RATIOS:
                b = int(round(t * r))
                if b > nsym:
                    continue
                rows.append(cell(px, op, sc, y0, y1, t, b))
        g = pd.DataFrame(rows)

        print("\n" + "=" * 104)
        print(f" {tag.upper()}   universe {nsym} names   window {y0}-{y1}   "
              f"{len(g)} cells   buy&hold {g['bh'].iloc[0]:.2f}%")
        print("=" * 104)
        print(f"\n {'TOP_N':>6}{'BUFFER':>8}{'ratio':>7}{'CAGR%':>9}{'Sharpe':>8}"
              f"{'MaxDD%':>9}{'trades':>8}{'edge':>8}")
        for _, x in g.iterrows():
            mark = "  <- current" if (x.top_n, x.buffer) == BASE else ""
            print(f" {int(x.top_n):>6}{int(x.buffer):>8}{x.buffer/x.top_n:>7.1f}"
                  f"{x.cagr:>9.2f}{x.sharpe:>8.2f}{x.maxdd:>9.2f}{int(x.trades):>8}"
                  f"{x.edge:>+8.2f}{mark}")

        base = g[(g.top_n == BASE[0]) & (g.buffer == BASE[1])]
        print(f"\n  DISTRIBUTION across {len(g)} cells")
        for col, lab in (("sharpe", "Sharpe"), ("edge", "edge"), ("cagr", "CAGR%")):
            q = g[col]
            print(f"    {lab:<7} min {q.min():>7.2f}  p25 {q.quantile(.25):>7.2f}  "
                  f"median {q.median():>7.2f}  p75 {q.quantile(.75):>7.2f}  "
                  f"max {q.max():>7.2f}  IQR {q.quantile(.75)-q.quantile(.25):>6.2f}")
        if len(base):
            b = base.iloc[0]
            print(f"\n  WHERE (8,16) SITS")
            print(f"    Sharpe {b.sharpe:.2f}  -> percentile {pctile_rank(g.sharpe, b.sharpe):.0f} "
                  f"(rank {int((g.sharpe > b.sharpe).sum())+1} of {len(g)}, 1 = best)")
            print(f"    edge   {b.edge:+.2f} -> percentile {pctile_rank(g.edge, b.edge):.0f} "
                  f"(rank {int((g.edge > b.edge).sum())+1} of {len(g)})")
            print(f"    CAGR   {b.cagr:.2f}  -> percentile {pctile_rank(g.cagr, b.cagr):.0f}")

            # neighbourhood on the (TOP_N index, ratio index) lattice
            ti, ri = TOPNS.index(8), RATIOS.index(2.0)
            nb = []
            for dt, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                a, c = ti + dt, ri + dr
                if 0 <= a < len(TOPNS) and 0 <= c < len(RATIOS):
                    t2, b2 = TOPNS[a], int(round(TOPNS[a] * RATIOS[c]))
                    m = g[(g.top_n == t2) & (g.buffer == b2)]
                    if len(m):
                        nb.append((t2, b2, m.iloc[0].sharpe, m.iloc[0].edge))
            print(f"\n  IMMEDIATE NEIGHBOURHOOD of (8,16) -- Sharpe {b.sharpe:.2f}, edge {b.edge:+.2f}")
            for t2, b2, s2, e2 in nb:
                print(f"    ({t2:>2},{b2:>2})  Sharpe {s2:>5.2f} ({s2-b.sharpe:+.2f})"
                      f"   edge {e2:>+6.2f} ({e2-b.edge:+.2f})")
            sp = [s for _, _, s, _ in nb]
            print(f"    Sharpe spread across the 4 neighbours: {max(sp)-min(sp):.2f} "
                  f"| max deviation from (8,16): {max(abs(s-b.sharpe) for s in sp):.2f}")
        else:
            print("\n  (8,16) not in this grid")


if __name__ == "__main__":
    main()
