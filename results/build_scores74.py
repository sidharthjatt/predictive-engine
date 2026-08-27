"""
build_scores74.py -- scores for the 74-stock universe (kept apart from the 58)
==================================================================
A copy of build_scores.py for the 58, differing only in:
  - Data: Development_data_files/ (74 stocks)
  - Output cache: /tmp/v74_expanding.csv  (separate from the 58's /tmp/v5_expanding.csv)
Model, features and seeds are identical to the 58, so the comparison stays fair.
~40-45 min (74 stocks, 10 seeds, monthly walk-forward).
"""
import sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_core import build_panel, score_monthly, HORIZON
from features_v2 import FEATS_V2
import config74

SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]
DATA74 = config74.RAW_DATA_DIR_74

print("[1/2] Building raw panel for 74 stocks...", flush=True)
t0 = time.time()
raw = build_panel(HORIZON, data_dir=DATA74)   # <-- 74 folder
keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
raw = raw[keep]
raw.to_csv(f"/tmp/raw_panel74_{HORIZON}.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min, {len(raw):,} rows", flush=True)

print("[2/2] Monthly scoring, 10-seed ensemble (slow)...", flush=True)
t0 = time.time()
scored = score_monthly(raw, SEEDS)
scored[["date", "symbol", "open", "close", "score", "year"]].to_csv(
    "/tmp/v74_expanding.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
print("DONE -- /tmp/v74_expanding.csv ready (74 stocks)")
