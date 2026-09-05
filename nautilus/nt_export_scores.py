"""
nt_export_scores.py -- export model scores for the Nautilus strategy to consume.

THE BOUNDARY THIS FILE DEFINES
    Research and execution are kept strictly apart. No model is ever trained
    inside a Nautilus strategy. The research pipeline (features, labels,
    walk-forward training, purging, the 10-seed ensemble) runs offline exactly as
    it does today and its only output to the trading layer is this table:

        date | symbol | score

    The strategy reads that table and does nothing else with the model.

    This mirrors how the signal is actually produced: the score for a given month
    comes from a model trained only on data up to 32 days before that month, so by
    the time the strategy sees it, it is already a point-in-time value.

ONE EXPORT PER REGISTERED UNIVERSE, DERIVED, NOT LISTED
    Source and output both come from universes/registry.py --  u.score_cache in,
    paths.nautilus_scores(u) out -- so this file iterates REGISTRY rather than
    naming four universes. It was the last place a new universe still needed a
    hand-written line: everything else in the pipeline picked one up from the
    registry, and a universe that reached the Nautilus layer without a parquet
    would have failed there instead of here.

    The paths are also ABSOLUTE now, because the registry's are. The four
    hardcoded ones were relative ("results/metrics/..."), which worked only
    because run_all.py spawned this step with cwd=ROOT.

Source : u.score_cache        for every u in universes/registry.REGISTRY
Output : nautilus/data/{u.nautilus_scores}

Reads only. Nothing under results/, results74/, results_mid/ or results_n100/ is
modified.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config
import paths
from universes.registry import REGISTRY

OUT_DIR = Path(__file__).resolve().parent / "data"
# Date window from config.py. The old year cut emitted June-2026 rows that
# nt_run.py then re-filtered by date; one cut in one place is enough.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE


def export(cache_path: Path, out_path: Path, tag: str) -> pd.DataFrame:
    """`year_end` is gone. It was declared and never read -- the year cut moved to
    config.BT_START_DATE/BT_END_DATE ("one cut in one place is enough", above) and
    the parameter was left behind, so three call sites passed 2026 and one passed
    2025 to something that ignored all four. A dead argument that looks like a
    per-universe window is worse than none."""
    print(f"\n{'=' * 66}\n{tag} UNIVERSE\n{'=' * 66}")
    if not cache_path.exists():
        raise FileNotFoundError(f"{cache_path} missing -- run run_all.py first")

    df = pd.read_csv(cache_path, usecols=["date", "symbol", "score"], parse_dates=["date"])
    print(f"  cache rows        : {len(df):,}")

    df = df[(df["date"] >= BT_START_DATE) & (df["date"] <= BT_END_DATE)]
    df = df.dropna(subset=["score"]).sort_values(["date", "symbol"]).reset_index(drop=True)

    # --- checks: the strategy cannot rank what it cannot see ---
    assert df["score"].notna().all(), "null scores survived the filter"
    assert not df.duplicated(["date", "symbol"]).any(), "duplicate (date, symbol) rows"

    per_day = df.groupby("date")["symbol"].nunique()
    print(f"  exported rows     : {len(df):,}")
    print(f"  period            : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  trading days      : {df['date'].nunique():,}")
    print(f"  symbols           : {df['symbol'].nunique()}")
    print(f"  symbols per day   : min {per_day.min()}, median {int(per_day.median())}, "
          f"max {per_day.max()}")
    print(f"  score range       : {df['score'].min():.6f} to {df['score'].max():.6f}")

    thin = per_day[per_day < 10]
    if len(thin):
        print(f"  [WARN] {len(thin)} day(s) have fewer than 10 scored symbols; "
              f"first: {thin.index[0].date()} ({thin.iloc[0]} symbols)")
    else:
        print("  thin days         : none (every day has at least 10 scored symbols)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"  saved -> {out_path.relative_to(ROOT)} "
          f"({out_path.stat().st_size / 1e6:.2f} MB)")

    # --- round-trip check: what is written must be what is read back ---
    back = pd.read_parquet(out_path)
    assert back.equals(df), "parquet round-trip changed the data"
    print("  round-trip check  : OK")
    return df


def main():
    """STEP 16. Body moved out of the __main__ guard, unchanged.

    See make_daily_log.main() for why this was missed: a spawned step never needed
    a main(), so the S4 boundary was invisible-by-absence until run.py ran the
    pipeline in one process.

    The four hardcoded exports this replaced built their input paths as bare
    relatives, so this step -- alone in the pipeline -- depended on the working
    directory being ROOT. The registry's paths are absolute, so that dependency is
    gone. run.py still chdirs to ROOT, which is now belt and braces rather than the
    only thing holding this step up.
    """
    print("Exporting model scores for the Nautilus execution layer...")
    rows = {}
    for tag, u in REGISTRY.items():
        rows[tag] = len(export(Path(u.score_cache), paths.nautilus_scores(u), u.label))
    print(f"\n{'=' * 66}")
    print("Done. " + " | ".join(f"{t}: {n:,} rows" for t, n in rows.items()))
    print("These files are the ONLY input the Nautilus strategy takes from the model.")
    print("=" * 66)


if __name__ == "__main__":
    main()
