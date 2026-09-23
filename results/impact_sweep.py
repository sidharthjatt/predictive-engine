"""impact_sweep.py -- what the participation cap costs, and what market impact costs,
measured separately.

WHY SEPARATELY. Lowering the cap and charging size-sensitive slippage both reduce
the return, and a single combined figure cannot say which did it. The grid below
holds one of the two fixed in every comparison:

    research            cap None,  k None      the published arithmetic
    cap 1.00, k None    cap only               measured: binds on nothing
    cap 0.10, k None    cap only               the cap's own contribution
    cap 1.00, k = x     slippage only          cap is a no-op at 1.00, so this
                                               isolates impact
    cap 0.10, k = x     both                   the combined figure

`cap 1.00` is carried even though it is a no-op precisely so that the no-op is on
the record. A row that changes nothing is evidence; an assumption that it changes
nothing is not.

THE BIND COUNTS ARE PART OF THE RESULT, NOT DIAGNOSTICS. A CAGR that moved while
the cap bound 200 times means something different from one that moved while it
bound twice. Every cell carries its BUY and SELL cap-bind counts and its
impact-exemption count.

NO k IS SELECTED HERE. The sweep shows how sensitive the answer is to k. Picking
one is a separate decision that needs a reason this file cannot supply.
"""
import io
import sys
import contextlib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import config                                    # noqa: E402
import engine_core                               # noqa: E402
import tradability                               # noqa: E402
from test_exposure import backtest_exposure      # noqa: E402
from universes.registry import REGISTRY          # noqa: E402

K_VALUES = (0.001, 0.002, 0.003, 0.005)
CAPS = (1.00, 0.10)
UNIVERSES = ("nifty100", "midcap150")
# The shipping arm: v2 is mode="breadth", sizing="invvol".
MODE, SIZING = "breadth", "invvol"


def panel(tag):
    u = REGISTRY[tag]
    src = config.require_cache(u.score_cache, what=f"{tag} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = engine_core.precompute(px)
    mom20 = px / px.shift(20) - 1
    v20 = tradability.median_volume(u.prepare_data_dir(), sorted(px.index),
                                    config.BT_START_DATE, config.BT_END_DATE)
    return px, op, sc, bd, pc, mom20, v20


def cell(px, op, sc, bd, pc, mom20, v20, cap, k):
    aud = {x: [] for x in ("holdings", "summary", "trades", "ranking",
                           "decisions", "skipped")}
    iout = {}
    eq, tc, ntr, _ = backtest_exposure(
        px, op, sc, bd, pc, mom20, mode=MODE, sizing=SIZING,
        participation_cap=cap, vol20=(None if cap is None and k is None else v20),
        impact_k=k, audit=aud, impact_out=iout)
    m = engine_core.metrics(eq, "cell", tc, ntr)
    sk = pd.DataFrame(aud["skipped"])
    caprows = sk[sk["reason"] == "participation cap"] if len(sk) else sk
    by_side = caprows.groupby("side").size().to_dict() if len(caprows) else {}
    return {
        "cap": "none" if cap is None else f"{cap:.2f}",
        "k": "none" if k is None else f"{k:.3f}",
        "CAGR%": m["CAGR%"], "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"],
        "trades": ntr, "final": round(float(eq.iloc[-1]), 2),
        "cap_BUY": by_side.get("BUY", 0), "cap_SELL": by_side.get("SELL", 0),
        "k_priced": iout.get("priced", 0), "k_exempt": iout.get("exempt", 0),
    }


def main():
    out = {}
    for tag in UNIVERSES:
        with contextlib.redirect_stdout(io.StringIO()):
            P = panel(tag)
        rows = [cell(*P, None, None)]
        for cap in CAPS:
            rows.append(cell(*P, cap, None))
        for cap in CAPS:
            for k in K_VALUES:
                rows.append(cell(*P, cap, k))
        df = pd.DataFrame(rows)
        base = df.iloc[0]
        df["dCAGR"] = (df["CAGR%"] - base["CAGR%"]).round(2)
        out[tag] = df
        dest = ROOT / "diagnostics" / f"impact_sweep_{tag}.csv"
        # naming: DEFECT arm -- the name carries the universe and nothing else,
        # and MODE/SIZING at line 48 is the arm. Editing those two constants to
        # sweep v1, v3 or v4 writes over this file with no name change and no
        # error: the reader of impact_sweep_nifty100.csv cannot tell which arm
        # produced it, and the run that produced the old one is gone. The cap and
        # k axes ARE carried, as columns, because the sweep is over them; the arm
        # is fixed per run and is the one axis that should be in the name.
        df.to_csv(dest, index=False)
        print("=" * 100)
        print(f" IMPACT SWEEP -- {tag}   arm {MODE}/{SIZING}   "
              f"window {config.BT_START_DATE.date()} -> {config.BT_END_DATE.date()}")
        print("=" * 100)
        print(df.to_string(index=False))
        print(f"  saved -> {dest.relative_to(ROOT)}")
        print()
    return out


if __name__ == "__main__":
    main()
