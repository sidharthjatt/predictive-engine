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

Source : results/metrics/v5_expanding_cache.csv      (58 universe)
         results74/metrics/v74_expanding_cache.csv   (74 universe)
         results_mid/metrics/v_mid_expanding_cache.csv (MidCap150 universe)
Output : nautilus/data/scores_58.parquet, scores_74.parquet, scores_mid.parquet

Reads only. Nothing under results/, results74/ or results_mid/ is modified.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import config74
import config_mid

OUT_DIR = Path(__file__).resolve().parent / "data"
# Date window from config.py. The old year cut emitted June-2026 rows that
# nt_run.py then re-filtered by date; one cut in one place is enough.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE


def export(cache_path: Path, out_path: Path, tag: str, year_end: int) -> pd.DataFrame:
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
    print(f"  saved -> {out_path.relative_to(Path(__file__).resolve().parents[1])} "
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

    THE PATHS BELOW ARE RELATIVE, AND THAT NOW MATTERS. run_all.run() spawned each
    step with cwd=ROOT explicitly; in process there is no such thing, so run.py
    chdirs to ROOT for the same reason. Left alone, running run.py from any other
    directory would have failed here, on this step only.
    """
    print("Exporting model scores for the Nautilus execution layer...")
    d58 = export(Path("results/metrics/v5_expanding_cache.csv"),
                 OUT_DIR / "scores_58.parquet", "58", 2026)
    d74 = export(Path("results74/metrics/v74_expanding_cache.csv"),
                 OUT_DIR / "scores_74.parquet", "74", 2025)
    dmid = export(Path("results_mid/metrics/v_mid_expanding_cache.csv"),
                  OUT_DIR / "scores_mid.parquet", "MIDCAP150", 2026)
    dn100 = export(Path("results_n100/metrics/v_n100_expanding_cache.csv"),
                   OUT_DIR / "scores_n100.parquet", "NIFTY100", 2026)
    print(f"\n{'=' * 66}")
    print(f"Done. 58: {len(d58):,} rows | 74: {len(d74):,} rows | "
          f"mid: {len(dmid):,} rows | n100: {len(dn100):,} rows")
    print("These files are the ONLY input the Nautilus strategy takes from the model.")
    print("=" * 66)


if __name__ == "__main__":
    main()
