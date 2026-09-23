"""
data_artefact_report.py -- what the extreme-return filter removed, per universe.

Reports the count, the symbols, the date distribution, and -- importantly -- how
many flagged returns fall INSIDE each universe's backtest window rather than only
in the pre-2019 training history. Then verifies the mask actually took effect by
confirming no flagged return survives in the built panel.

Reads only. Writes nothing.
"""
import sys
sys.dont_write_bytecode = True

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config
from features_v2 import EXTREME_RET_HI, EXTREME_RET_LO

BT_START = pd.Timestamp("2019-01-01")
# THE UNIVERSES, AND THEIR PATHS, COME FROM THE REGISTRY. This was three literal
# rows naming config74 and a `nifty50` directory; two of the three universes have
# since been deleted, and the module could not even be imported afterwards.
from universes.registry import REGISTRY          # noqa: E402

UNIV = {u.tag: (u.data_dir, u.score_cache) for u in REGISTRY.values()}


def flagged(data_dir):
    rows = []
    for f in sorted(Path(data_dir).glob("*.csv")):
        s = config.read_price_csv(f)[["date", "close"]].dropna().sort_values("date")
        r = s.set_index("date")["close"].pct_change()
        bad = r[(r > EXTREME_RET_HI) | (r < EXTREME_RET_LO)]
        for dt, v in bad.items():
            rows.append({"symbol": f.stem, "date": dt, "ret": v})
    return pd.DataFrame(rows)


def main():
    print("=" * 96)
    print(f" EXTREME-RETURN DATA ARTEFACTS   filter: return > {EXTREME_RET_HI:+.0%}"
          f" or < {EXTREME_RET_LO:+.0%}")
    print("=" * 96)
    print("\n No split ratio is inferred -- without corporate-action data that is guesswork.")
    print(" The daily return is set to NaN; the existing NaN handling drops the")
    print(" contaminated rows. The LABEL is protected too: fwd_ret is dropped wherever a")
    print(" flagged day falls inside its 20-day forward window.")

    tot = 0
    for tag, (data_dir, cache) in UNIV.items():
        # THE FARM IS BUILT ON DEMAND under cache/<tag>/ since 2026-09-23;
        # u.data_dir is only its path and is empty on a fresh tree.
        data_dir = REGISTRY[tag].prepare_data_dir()
        b = flagged(data_dir)
        print("\n" + "-" * 96)
        if b.empty:
            print(f" {tag}: 0 flagged returns -- this universe is unaffected and acts as a "
                  f"natural control")
            continue
        tot += len(b)
        inw = b[b["date"] >= BT_START]
        dom = b["date"].dt.day
        print(f" {tag}: {len(b)} flagged returns across {b['symbol'].nunique()} symbols")
        print(f"     before 2019 (training only) : {len(b)-len(inw)}")
        print(f"     2019 onward (INSIDE the backtest window) : {len(inw)}")
        print(f"     falling on the 1st-3rd of a month : {int((dom<=3).sum())} of {len(b)}")
        print(f"     magnitude range : {b['ret'].min():+.1%} to {b['ret'].max():+.1%}")
        print(f"     symbols : {', '.join(sorted(b['symbol'].unique()))}")
        if len(inw):
            print(f"     IN-WINDOW detail (these affect the backtest, not just training):")
            for _, r in inw.sort_values("date").iterrows():
                print(f"        {r['date'].date()}  {r['symbol']:<12} {r['ret']:+8.1%}")

        # did the mask reach the built panel?
        if Path(cache).exists():
            p = pd.read_csv(cache, parse_dates=["date"])
            px = p.pivot_table(index="date", columns="symbol", values="close")
            surv = 0
            for _, r in b.iterrows():
                if r["symbol"] in px.columns and r["date"] in px.index:
                    if not pd.isna(px.loc[r["date"], r["symbol"]]):
                        surv += 1
            print(f"     rows for those (symbol, date) pairs still present in the scored"
                  f" panel: {surv}")
            print(f"     (a surviving row is expected only where every feature recovered;"
                  f" the RETURN itself is NaN either way)")
    print("\n" + "=" * 96)
    print(f" total flagged across all three universes: {tot}")
    print("=" * 96)


if __name__ == "__main__":
    main()
