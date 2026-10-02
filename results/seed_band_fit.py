"""
seed_band_fit.py -- stages 1 and 2 of experiments/DRAWDOWN_STOP_PREREG.txt.

    ./venv/bin/python results/seed_band_fit.py fit            # all six, in order
    ./venv/bin/python results/seed_band_fit.py fit --universe midcap50
    ./venv/bin/python results/seed_band_fit.py check          # re-check stored files
    scripts/run_seed_band_fit.sh                              # the same as `fit`, under caffeinate

WHAT IT DOES
    For each judged universe, fits the 20 seeds of SEEDS20 once on the cached raw
    panel, month by month exactly as engine_core.score_monthly does, and stores every
    seed's scores separately in cache/<tag>/seed_scores_<tag>_20.npy: float64, one
    row per row of the raw panel sorted by (date, symbol), one column per seed in
    SEEDS20 order, NaN where score_monthly leaves the score NaN. A JSON sidecar of
    the same name records the inputs, the seeds, the check result and the time.

    It computes no backtest and no arm. The band itself (stage 3) is a separate
    script, written after v5 and v6 exist.

REPRODUCTION CHECK, EVERY UNIVERSE
    The first 10 columns are the production seeds in production order. Their mean,
    taken the way score_monthly takes it (np.mean over a (10, rows) array, axis 0),
    must equal the score column of the cached score panel bit for bit on every row,
    NaN in the same places. If it does not, the universe's file is not written and
    the run stops: no later universe is fitted. Stage 1 is midcap50 alone, so a
    failure there stops the whole band before any other fit.

    The month loop below is a copy of score_monthly's, not a call to it, because
    score_monthly keeps only the mean. The check is what proves the copy computes
    the same thing.

ATOMIC AND RESUMABLE
    Each universe is written to a temporary file in its own cache folder and moved
    into place with os.replace, then its sidecar the same way. A universe whose
    sidecar records the current raw panel, score panel, seeds and fitting code, and
    a passed check, is skipped. An interrupted run repeats only the universe it was
    fitting.
"""
import os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import argparse
import hashlib
import inspect
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import config
from engine_core import _fit_seed, HORIZON, PURGE_EMBARGO
from features_v2 import FEATS_V2
from build_scores_step import SEEDS as PROD_SEEDS
from universes.registry import REGISTRY

# FIXED BY experiments/DRAWDOWN_STOP_PREREG.txt.
UNIVERSES = ("midcap50", "nifty50", "midcap100", "nifty100", "midcap150", "smallcap250")
EXTRA_SEEDS = tuple(range(1000, 1010))
SEEDS20 = tuple(PROD_SEEDS) + EXTRA_SEEDS
assert len(PROD_SEEDS) == 10 and not set(PROD_SEEDS) & set(EXTRA_SEEDS), \
    "the production seeds must be 10 and must not overlap 1000-1009"
WORKERS = 10


def store_path(u):
    return u.score_cache.parent / f"seed_scores_{u.tag}_20.npy"


def sidecar_path(u):
    return store_path(u).with_suffix(".json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fit_code_key():
    """sha256 of the code that decides the stored numbers: fit_seeds and _fit_seed."""
    src = inspect.getsource(fit_seeds) + inspect.getsource(_fit_seed)
    return hashlib.sha256(src.encode()).hexdigest()


def inputs(u):
    """What the stored file depends on, as recorded in its sidecar."""
    raw = config.require_cache(u.raw_cache, what=f"{u.tag} raw panel")
    score = config.require_cache(u.score_cache, what=f"{u.tag} score panel")
    return {"universe": u.tag, "purge_mode": u.purge_mode,
            "raw_panel": config.root_relative(raw), "raw_panel_sha256": sha256_file(raw),
            "score_panel": config.root_relative(score),
            "score_panel_sha256": sha256_file(score),
            "seeds": list(SEEDS20), "fit_code_sha256": fit_code_key()}


def fit_seeds(p, purge_mode):
    """score_monthly's month loop, keeping each seed's predictions. -> (rows, 20)."""
    if purge_mode != "trading":
        raise SystemExit(f"purge_mode {purge_mode!r}: only 'trading' is copied here")
    S = np.full((len(p), len(SEEDS20)), np.nan)
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}
    months = sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique())
    t0 = time.time()
    for k, ym in enumerate(months, start=1):
        first = p.loc[p.ym == ym, "date"].min()
        j = pos[np.datetime64(first)] - HORIZON - PURGE_EMBARGO
        if j < 0:
            continue
        cut = pd.Timestamp(cal[j])
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        te = (p["ym"] == ym) & p["scorable"]
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        Xtr = p.loc[tr, FEATS_V2].to_numpy()
        ytr = p.loc[tr, "y_rank"].to_numpy()
        Xte = p.loc[te, FEATS_V2].to_numpy()
        pr = Parallel(n_jobs=WORKERS, backend="loky")(
            delayed(_fit_seed)(sd, Xtr, ytr, Xte) for sd in SEEDS20)
        S[np.flatnonzero(te.to_numpy()), :] = np.column_stack(pr)
        el = (time.time() - t0) / 60
        print(f"      month {k}/{len(months)} {ym}: {len(SEEDS20)} seeds fitted, "
              f"{el:.1f} min elapsed, ~{el / k * (len(months) - k):.1f} min left", flush=True)
    return S


def production_mean(S):
    """The first 10 columns averaged as score_monthly averages: axis 0 of (10, rows)."""
    return np.mean(np.ascontiguousarray(S[:, :10].T), axis=0)


def reproduction_check(u, p, S):
    """-> dict. Passed only if the first-10 mean equals the cached score bit for bit."""
    v = config.read_table(u.score_cache)
    v = v.sort_values(["date", "symbol"]).reset_index(drop=True)
    same_rows = (len(v) == len(p)
                 and (v["date"].to_numpy() == p["date"].to_numpy()).all()
                 and (v["symbol"].to_numpy() == p["symbol"].to_numpy()).all())
    if not same_rows:
        return {"passed": False, "reason": "the score panel's rows are not the raw panel's rows"}
    cached = v["score"].to_numpy(dtype=float)
    ens = production_mean(S)
    nan_same = bool((np.isnan(cached) == np.isnan(ens)).all())
    scored = ~np.isnan(cached)
    exact = bool(nan_same and np.array_equal(ens[scored], cached[scored]))
    diff = float(np.nanmax(np.abs(ens - cached))) if scored.any() else 0.0
    return {"passed": exact, "rows": int(len(p)), "scored_rows": int(scored.sum()),
            "nan_positions_identical": nan_same,
            "scored_rows_bit_identical": int((ens[scored] == cached[scored]).sum()),
            "max_abs_diff": diff}


def is_done(u, want):
    side = sidecar_path(u)
    if not (side.exists() and store_path(u).exists()):
        return False
    rec = json.loads(side.read_text())
    return (rec.get("inputs") == want and rec.get("check", {}).get("passed") is True
            and rec.get("store_sha256") == sha256_file(store_path(u)))


def write_atomic_npy(path, arr):
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with open(tmp, "wb") as fh:
        np.save(fh, arr)
    os.replace(tmp, path)


def write_atomic_json(path, rec):
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    # naming: axis-free -- a per-universe seed store's sidecar; no arm, cadence, profile or tax
    tmp.write_text(json.dumps(rec, indent=1))
    os.replace(tmp, path)


def fit_universe(tag):
    """Fit, check, store. -> the sidecar record. Exits the run on a failed check."""
    u = REGISTRY[tag]
    want = inputs(u)
    if is_done(u, want):
        rec = json.loads(sidecar_path(u).read_text())
        print(f"  [{tag}] already stored and checked, skipped", flush=True)
        return rec
    print(f"  [{tag}] fitting {len(SEEDS20)} seeds on {want['raw_panel']}", flush=True)
    t0 = time.time()
    p = config.read_table(u.raw_cache)
    p = p.sort_values(["date", "symbol"]).reset_index(drop=True)
    p["ym"] = p["date"].dt.to_period("M")
    S = fit_seeds(p, u.purge_mode)
    minutes_fit = (time.time() - t0) / 60
    check = reproduction_check(u, p, S)
    print(f"  [{tag}] reproduction check: {'PASSED' if check['passed'] else 'FAILED'} "
          f"{json.dumps(check)}", flush=True)
    if not check["passed"]:
        raise SystemExit(f"{tag}: the production seeds do not reproduce the cached score "
                         f"panel. Nothing is stored for {tag} and the band stops here.")
    write_atomic_npy(store_path(u), S)
    rec = {"inputs": want, "check": check, "store": config.root_relative(store_path(u)),
           "store_sha256": sha256_file(store_path(u)),
           "store_bytes": store_path(u).stat().st_size, "shape": list(S.shape),
           "minutes_fit": round(minutes_fit, 2),
           "minutes_total": round((time.time() - t0) / 60, 2),
           "run_date": time.strftime("%Y-%m-%d %H:%M")}
    write_atomic_json(sidecar_path(u), rec)
    print(f"  [{tag}] stored {rec['store']} ({rec['store_bytes']:,} bytes) "
          f"in {rec['minutes_total']:.1f} min", flush=True)
    return rec


def cmd_fit(tags):
    for tag in tags:
        fit_universe(tag)


def cmd_check(tags):
    """Re-run the reproduction check on stored files without fitting."""
    bad = 0
    for tag in tags:
        u = REGISTRY[tag]
        if not store_path(u).exists():
            print(f"  [{tag}] not stored")
            bad += 1
            continue
        p = config.read_table(u.raw_cache)
        p = p.sort_values(["date", "symbol"]).reset_index(drop=True)
        check = reproduction_check(u, p, np.load(store_path(u)))
        print(f"  [{tag}] {'PASSED' if check['passed'] else 'FAILED'} {json.dumps(check)}")
        bad += not check["passed"]
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("fit", "check"))
    ap.add_argument("--universe", default=",".join(UNIVERSES))
    a = ap.parse_args()
    tags = [t.strip() for t in a.universe.split(",") if t.strip()]
    unknown = [t for t in tags if t not in UNIVERSES]
    if unknown:
        raise SystemExit(f"not a judged universe of the pre-registration: {unknown}")
    if a.cmd == "fit":
        cmd_fit(tags)
        return 0
    return cmd_check(tags)


if __name__ == "__main__":
    sys.exit(main())
