"""
build_scores_mid.py -- scores for the MidCap150 universe (third universe)
========================================================================
A copy of build_scores74.py, differing only in:
  - Data: data/raw/MidCap150/constituents/ (148 stocks, index excluded)
  - Output cache: /tmp/v_mid_expanding.csv (separate from the 58 and 74 caches)
Model, features and seeds are identical to the 58 and the 74, so the comparison
stays fair. Only the universe differs.

THE INDEX IS EXCLUDED, AND THAT IS ASSERTED RATHER THAN ASSUMED
    build_panel globs its data_dir, so it is pointed at the constituents directory
    config_mid builds, which contains the 148 stocks and not NIFTYMIDCAP150.csv.
    The panel's symbol set is then checked against config_mid.SYMBOLS_MID. A bare
    glob over clean/ would have made the index the 149th tradable name.
"""
import sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_core import build_panel, score_monthly, HORIZON
from features_v2 import FEATS_V2
import config_mid

SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]
DATA_MID = config_mid.ensure_constituents_dir()

print(f"[1/2] Building raw panel for {len(config_mid.SYMBOLS_MID)} MidCap150 stocks...",
      flush=True)
t0 = time.time()
raw = build_panel(HORIZON, data_dir=DATA_MID)     # <-- constituents only

got = set(raw["symbol"].unique())
assert config_mid.INDEX_NAME_MID not in got, \
    "the index entered the panel as a tradable symbol"
missing = set(config_mid.SYMBOLS_MID) - got
print(f"    symbols in panel: {len(got)} of {len(config_mid.SYMBOLS_MID)}"
      + (f" | dropped for insufficient history: {sorted(missing)}" if missing else ""))

keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
raw = raw[keep]
raw.to_csv(f"/tmp/raw_panel_mid_{HORIZON}.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min, {len(raw):,} rows", flush=True)

print("[2/2] Monthly scoring, 10-seed ensemble (slow)...", flush=True)
t0 = time.time()
scored = score_monthly(raw, SEEDS)
scored[["date", "symbol", "open", "close", "score", "year"]].to_csv(
    "/tmp/v_mid_expanding.csv", index=False)
print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
print(f"DONE -- /tmp/v_mid_expanding.csv ready ({len(got)} stocks)")
