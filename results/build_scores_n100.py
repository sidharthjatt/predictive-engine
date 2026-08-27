"""
build_scores_n100.py -- scores for the Nifty 100 universe (fourth universe)
==========================================================================
A copy of build_scores_mid.py, differing only in:
  - Data: data/raw/N100_constituents/     (99 stocks, index excluded by name)
  - Output cache: /tmp/v_n100_expanding.csv  (separate from every other cache)
Model, features and seeds are identical to the other universes, so the comparison
stays fair. Only the universe differs.

THE INDEX IS EXCLUDED, AND THAT IS ASSERTED RATHER THAN ASSUMED
    build_panel globs its data_dir, so it is pointed at the constituents directory
    config_n100 builds, which contains the 99 stocks and not NIFTY100.csv. The
    panel's symbol set is then checked against config_n100.SYMBOLS_N100. A bare
    glob over nifty100_benchmark/ would have made the index the 100th tradable
    name -- which is precisely the error this project made once before, when the
    index was averaged into its own constituent basket and the result was labelled
    as the benchmark.
"""
import sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_core import build_panel, score_monthly, HORIZON
from features_v2 import FEATS_V2
import config_n100

SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]
DATA_N100 = config_n100.ensure_constituents_dir()

print(f"[1/2] Building raw panel for {len(config_n100.SYMBOLS_N100)} Nifty 100 stocks...",
      flush=True)
t0 = time.time()
raw = build_panel(HORIZON, data_dir=DATA_N100)     # <-- constituents only

got = set(raw["symbol"].unique())
assert config_n100.INDEX_NAME_N100 not in got, \
    "the index entered the panel as a tradable symbol"
missing = set(config_n100.SYMBOLS_N100) - got
print(f"    symbols in panel: {len(got)} of {len(config_n100.SYMBOLS_N100)}"
      + (f" | dropped for insufficient history: {sorted(missing)}" if missing else ""))

keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
raw = raw[keep]
raw.to_csv(f"/tmp/raw_panel_n100_{HORIZON}.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min, {len(raw):,} rows", flush=True)

print("[2/2] Monthly scoring, 10-seed ensemble (slow)...", flush=True)
t0 = time.time()
scored = score_monthly(raw, SEEDS)
scored[["date", "symbol", "open", "close", "score", "year"]].to_csv(
    "/tmp/v_n100_expanding.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
print(f"DONE -- /tmp/v_n100_expanding.csv ready ({len(got)} stocks)")
