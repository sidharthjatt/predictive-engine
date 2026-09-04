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
from engine_core import build_panel, score_monthly, HORIZON
from features_v2 import FEATS_V2


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. This whole body used to run at module level,
    so importing this file started a 40-minute model fit as a side effect --
    which is why the pipeline could only ever spawn it as a subprocess.
    """
    # THE FROZEN GUARD MOVED IN HERE WITH THE WORK. At module level it fired on
    # IMPORT, so run.py could not even load this file without tripping it. It
    # guards the WRITE, so it belongs where the writing happens.
    _frozen_guard("58")   # refuses unless ALLOW_FROZEN_WRITE=1; run_all.py sets it

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
    scored = score_monthly(raw, SEEDS, purge_mode="calendar")
    scored[["date", "symbol", "open", "close", "score", "year"]].to_csv(
        "/tmp/v5_expanding.csv", index=False)
    print(f"    done {(time.time()-t0)/60:.1f} min", flush=True)
    print("DONE -- /tmp/v5_expanding.csv ready")


if __name__ == "__main__":
    main()
