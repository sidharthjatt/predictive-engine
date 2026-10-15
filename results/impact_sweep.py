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
no fill. Measured 2026-10-10, on that day's data delivery, over every core arm of the
nine universes (microcap250 without PRIVISCL), it binds in 13 of 36 CSVs (cap 1.00,
k none row; BUY + SELL binds, CAGR change).

    nifty100 v1     1 + 0   +0.22        smallcap250 v1   4 + 1   -0.71
    midcap50 v1     1 + 0   -0.05        smallcap250 v3   2 + 0   -3.08
    midcap50 v3     1 + 0   -0.03        nifty500 v1      3 + 0   -0.18
    midcap100 v1    1 + 0   -0.02        nifty500 v3      1 + 0   +0.28
    midcap100 v3    1 + 0   -0.05        microcap250 v1  12 + 9   -0.67
    microcap250 v2  3 + 2   +0.15        microcap250 v3  16 + 11  -4.79
    microcap250 v4  3 + 1   +0.04

Read each CSV's cap_BUY and cap_SELL columns before treating its cap 1.00 rows as
impact only.

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
import impact_axis                               # noqa: E402
import pcap_axis                                 # noqa: E402
import profiles                                  # noqa: E402
from test_exposure import backtest_exposure      # noqa: E402
from universes.registry import REGISTRY          # noqa: E402
from config import read_table  # the one CSV/parquet reader: config.read_table

K_VALUES = (0.001, 0.002, 0.003, 0.005)
CAPS = (1.00, 0.10)

# THE SETTINGS, NOT A COPY OF THEM (2026-10-15). Each cell selects the profile,
# --cap and --impact exactly as run.py does and takes its keywords from
# profiles.cap_kwargs, so the volume series, the cap and k reach backtest_exposure
# by the path every run takes. Until then this file loaded its own volume series,
# on the score panel's dates rather than the engine's calendar, and passed cap and
# k by hand.


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
    # the tradeable profile's volume series, loaded once and reused by every cell
    _select(1.00, None)
    v20 = profiles.cap_kwargs(u)["vol20"]
    _select(None, None)
    return u, px, op, sc, bd, pc, mom20, v20


def _select(cap, k):
    """Select what run.py would for this cell: research when cap is None, else
    --profile tradeable --cap cap --impact k (k None is --impact 0)."""
    profiles.set_selection(None if cap is None else "tradeable")
    pcap_axis.set_selection(cap)
    impact_axis.set_selection(k)


def cell(u, px, op, sc, bd, pc, mom20, v20, arm, cap, k):
    aud = {x: [] for x in ("holdings", "summary", "trades", "ranking",
                           "decisions", "skipped")}
    iout = {}
    _select(cap, k)
    try:
        kw = profiles.cap_kwargs(u, vol20=v20)
    finally:
        _select(None, None)
    eq, tc, ntr, _ = backtest_exposure(
        px, op, sc, bd, pc, mom20, drawdown_stop=None, **arm.kwargs,
        audit=aud, impact_out=iout, **kw)
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
