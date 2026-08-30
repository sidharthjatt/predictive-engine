"""hash_58_engine_core.py -- equity-curve hash for the retired 58.

RUN IT AS:  ./venv/bin/python results/hash_58_engine_core.py
(the system python3 has no lightgbm and cannot import engine_core)

Guards the frozen 58 against edits to engine_core.py that are supposed to be
printed-string-only. Used for the 2026-08-29 leakage-label change.

The checklist edit is a printed-string change. This proves it moved no computed
value, same method as the TOP_N centralisation: SHA256 over the raw float64
bytes of the curve, before and after.
"""
import sys, hashlib, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))
import numpy as np, pandas as pd
import config
from engine_core import backtest, precompute, BT_START, BT_END

src = config.require_cache(ROOT/"results"/"metrics"/"v5_expanding_cache.csv",
                          "/tmp/v5_expanding.csv", what="58 score panel")
p = pd.read_csv(src, parse_dates=["date"])
px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
sc = p.pivot_table(index="date", columns="symbol", values="score")
bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
pc = precompute(px)
print(f"  panel {px.shape[1]} names, {len(bd)} backtest days  src={src.name}")
for sizing in ("equal", "invvol"):
    out = backtest(px, op, sc, bd, pc, sizing=sizing)
    eq = out[0]
    v = np.asarray(pd.Series(eq).values, dtype=np.float64)
    h = hashlib.sha256(v.tobytes()).hexdigest()
    print(f"  58 {sizing:<7} days {len(v):>5}  final {v[-1]:>14,.2f}  {h}")
