"""
config74.py -- separate config for the 74-stock universe
=====================================================
This does not touch the 58-stock system at all. It only overrides paths for the 74:
  - Data: data/raw/Development_data_files/ (74 CSVs)
  - Output: results74/metrics/ (kept apart from the 58)

Everything else (features, model settings) stays identical to the 58-stock setup,
so that the comparison is fair: only the universe differs.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# 74-stock data folder, in the layout it was delivered in
RAW_DATA_DIR_74 = PROJECT_ROOT / "data" / "raw" / "Development_data_files"

# Outputs for the 74 universe -- separate folder, never mixed with the 58
RESULTS_DIR_74 = PROJECT_ROOT / "results74"
METRICS_DIR_74 = RESULTS_DIR_74 / "metrics"
METRICS_DIR_74.mkdir(parents=True, exist_ok=True)
