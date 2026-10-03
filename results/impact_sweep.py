"""impact_sweep.py -- what the participation cap costs, and what market impact costs,
measured separately.

WHY SEPARATELY. Lowering the cap and charging size-sensitive slippage both reduce
the return, and a single combined figure cannot say which did it. The grid below
holds one of the two fixed in every comparison:

    research            cap None,  k None      the published arithmetic
    cap 1.00, k None    cap only               the loosest cap
    cap 0.10, k None    cap only               the cap's own contribution
    cap 1.00, k = x     slippage plus the      isolates impact only where
                        loosest cap            cap 1.00 binds on nothing
    cap 0.10, k = x     both                   the combined figure

`cap 1.00` is NOT a no-op everywhere. On v2 of nifty100 and midcap150 it binds on
no fill. Measured 2026-10-03 over every core arm and universe, it binds in 10 of
32 CSVs, all but one on v1 or v3, and moves CAGR by up to -1.99 points
(smallcap250 v3). Read each CSV's cap_BUY and cap_SELL columns before treating
its cap 1.00 rows as impact only.

THE BIND COUNTS ARE PART OF THE RESULT, NOT DIAGNOSTICS. A CAGR that moved while
the cap bound 200 times means something different from one that moved while it
bound twice. Every cell carries its BUY and SELL cap-bind counts and its
impact-exemption count.

NO k IS SELECTED HERE. The sweep shows how sensitive the answer is to k. Picking
one is a separate decision that needs a reason this file cannot supply.

EVERY CORE ARM ON EVERY UNIVERSE. The arms come from arms.registry.ARMS (v1 to v4)
and the universes from universes.registry.REGISTRY; nothing here names either.
Each pair writes diagnostics/impact_sweep_<universe>_<arm>.csv. The no-cap, k-none
row is the research profile, tax off, cadence 20 (test_exposure.REBAL), which is
what the published v34_comparison.csv rows are, and is compared against them by
the caller.
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
from arms.registry import ARMS                   # noqa: E402
import tradability                               # noqa: E402
from test_exposure import backtest_exposure      # noqa: E402
from universes.registry import REGISTRY          # noqa: E402
from config import read_table  # the one CSV/parquet reader: config.read_table

K_VALUES = (0.001, 0.002, 0.003, 0.005)
CAPS = (1.00, 0.10)


def panel(tag):
    u = REGISTRY[tag]
    # The untradeable-name guard the engines load for this universe.
    engine_core.set_tradeability(u)
    src = config.require_cache(u.score_cache, what=f"{tag} score panel")
    p = read_table(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = engine_core.precompute(px)
    mom20 = px / px.shift(20) - 1
    v20 = tradability.median_volume(u.prepare_data_dir(), sorted(px.index),
                                    config.BT_START_DATE, config.BT_END_DATE)
    return px, op, sc, bd, pc, mom20, v20


def cell(px, op, sc, bd, pc, mom20, v20, arm, cap, k):
    aud = {x: [] for x in ("holdings", "summary", "trades", "ranking",
                           "decisions", "skipped")}
    iout = {}
    eq, tc, ntr, _ = backtest_exposure(
        px, op, sc, bd, pc, mom20, drawdown_stop=None, **arm.kwargs,
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
    for tag in REGISTRY:
        with contextlib.redirect_stdout(io.StringIO()):
            P = panel(tag)
        for arm in ARMS.values():
            rows = [cell(*P, arm, None, None)]
            for cap in CAPS:
                rows.append(cell(*P, arm, cap, None))
            for cap in CAPS:
                for k in K_VALUES:
                    rows.append(cell(*P, arm, cap, k))
            df = pd.DataFrame(rows)
            base = df.iloc[0]
            df["dCAGR"] = (df["CAGR%"] - base["CAGR%"]).round(2)
            out[(tag, arm.name)] = df
            dest = ROOT / "diagnostics" / f"impact_sweep_{tag}_{arm.name}.csv"
            # naming: axis-free -- every core arm and universe is written, each under
            # its registry names; run.py's arm, cadence, profile and tax selections
            # do not reach this script. The cap and k axes are columns, because the
            # sweep is over them.
            df.to_csv(dest, index=False)
            print("=" * 100)
            print(f" IMPACT SWEEP -- {tag}   arm {arm.name} ({arm.mode}/{arm.sizing})   "
                  f"window {config.BT_START_DATE.date()} -> {config.BT_END_DATE.date()}")
            print("=" * 100)
            print(df.to_string(index=False))
            print(f"  saved -> {dest.relative_to(ROOT)}")
            print()
    return out


if __name__ == "__main__":
    main()
