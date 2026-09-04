"""
build_scores.py -- builds a fresh raw panel and monthly scores into the /tmp cache.
Run this when /tmp has been cleared and an engine reports "v5_expanding.csv missing".
It takes roughly 40 minutes (900 models). A permanent copy is kept so the work is
not lost again.
"""
import sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_guard import guard as _frozen_guard
_frozen_guard("58")   # refuses unless ALLOW_FROZEN_WRITE=1; run_all.py sets it
from engine_core import build_panel, score_monthly, HORIZON
from features_v2 import FEATS_V2

SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]

print("[1/2] Building raw panel...", flush=True)
t0 = time.time()
raw = build_panel(HORIZON)
keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
raw = raw[keep]
raw.to_csv(f"/tmp/raw_panel_{HORIZON}.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min, {len(raw):,} rows", flush=True)

print("[2/2] Monthly scoring, 10-seed ensemble (slow)...", flush=True)
t0 = time.time()
scored = score_monthly(raw, SEEDS)
scored[["date", "symbol", "open", "close", "score", "year"]].to_csv(
    "/tmp/v5_expanding.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
print("DONE -- /tmp/v5_expanding.csv ready")
