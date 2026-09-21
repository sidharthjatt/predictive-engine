"""
price_noise_measure.py -- does the arm survive a change too small to see?
=========================================================================

WHAT THIS ANSWERS, AND WHY IT WAS ASKED

    nifty100's shipping arm (v2, invvol, breadth-scaled) went from +0.43 CAGR
    points over its own basket to -5.15 when the universe was repointed from the
    kite panel to the supplier's on 2026-09-18. The repoint was assumed to be the
    cause until the loss was decomposed by name on 2026-09-20:

        53 of the 99 constituents carry 108% of the fall in final equity, and
        every one of those 53 has an in-window adj_close identical to the old
        panel's to within 0.01%. MAZDOCK alone carries 42.8% with 1,477 of 1,477
        in-window sessions unchanged and 26 days differing by at most 0.01%.
        The names whose prices genuinely moved were net POSITIVE.

    An output that moves 5.42 CAGR points when the inputs under it did not move
    is not being explained by the inputs. This measures the alternative directly:
    perturb the prices by amounts SMALLER than the difference between the two
    panels and see how far the published figures travel.

    THIS SCRIPT MEASURES A SPREAD. IT DOES NOT EXPLAIN ONE. Nothing here decides
    whether a wide spread means the arm is overfitted, the ensemble is
    underspecified, or the selection rule is discontinuous. It reports how far the
    numbers move and under what perturbation, and stops there.

THE NOISE CONSTRUCTION, EXACTLY

    adj_close' = adj_close * (1 + eps),  eps ~ Normal(0, sigma)

    drawn INDEPENDENTLY for every (symbol, date) pair. One numpy Generator per
    run, seeded by the run's noise seed, consumed in sorted filename order, so a
    (sigma, noise_seed) pair reproduces the perturbed farm byte for byte.

    ONLY adj_close IS WRITTEN. open, high, low, close and volume are copied
    through untouched. engine_core.canonical_price then resolves adj_close into
    `close` and rescales open/high/low by adj_close'/close, so the whole bar moves
    with the perturbation and the execution price moves with the signal. That is
    the existing load boundary, not something added here.

    THE PRICE-VALIDITY GUARD IS LEFT ALONE, AND IT FIRES MORE OFTEN UNDER NOISE.
    canonical_price treats adj_close as bad when it is <= 0, below the raw low or
    above the raw high, and falls back to the raw close. Measured 2026-09-20:

        baseline          nifty100    170 of 473,311 rows (0.036%)
                          midcap150    41 of 572,399 rows (0.007%)
        at sigma 0.01%    nifty100  6,133 rows (1.30%)
                          midcap150 13,216 rows (2.31%)

    The jump is not damage. adj_close sits EXACTLY on the high or the low on
    11,942 nifty100 rows and 26,328 midcap150 rows -- a session that closed at its
    extreme -- so any nudge in the wrong direction crosses the bound. On the rows
    that cross, the median |close - adj_close| / adj_close is 0.0000%: the
    fallback substitutes the same number and so CANCELS the perturbation on those
    rows. Only 47 nifty100 and 116 midcap150 rows differ by more than 1%.

    So the effective perturbation is slightly smaller than sigma, by about the
    crossing rate. The counts are recorded per run rather than corrected for, and
    the guard is not bypassed: a measurement that edits the engine to make its own
    noise land cleanly is measuring a different engine.

WHAT IS HELD FIXED

    Everything except adj_close. The production 10-seed ensemble, the purge mode
    read from the registry, the 20-day cadence, tax off, profile research (no
    participation cap), the same backtest window and the same calendar. The arm is
    v2 exactly as arms/registry.py defines it: mode="breadth", sizing="invvol".

THE IDENTITY GATE

    sigma = 0 is run FIRST and through the same code path as every perturbed run.
    It must reproduce the published v34_comparison.csv row for the universe. If it
    does not, the harness is measuring something other than the shipped arm and
    every spread below it is uninterpretable. Measured 2026-09-20 on nifty100:

        harness    CAGR 19.01  Sharpe 1.50  MaxDD -21.87  trades 940
                   final equity 3,628,639.83  AnnVol 12.33
        published  CAGR 19.01  Sharpe 1.50  MaxDD -21.87  trades 940
                   final equity 3,628,639.83  AnnVol 12.33

    Identical on every column. The gate is asserted at run time, not just recorded
    here, and a mismatch stops the grid.

COST -- READ THIS BEFORE STARTING A GRID

    Perturbing adj_close has to enter BEFORE build_panel, so every run rebuilds
    the feature panel and refits the 10-seed monthly ensemble. There is no way to
    do this on stored fills and still call it the full arm.

        nifty100   (99 names)   15.8 min/run, measured 2026-09-20
        midcap150 (148 names)   ~22 min/run, extrapolated from
                                diagnostics/build_scores_cost.txt

    The default grid is 4 levels x 5 seeds + 1 baseline = 21 runs per universe:
    about 5.5 hours for nifty100 and 8 for midcap150. IT IS RESUMABLE. Every
    finished run is appended to the CSV immediately and a (sigma, seed) already
    present is skipped, so an interrupted grid resumes where it stopped.

    NOTHING PUBLISHED IS TOUCHED. The perturbed price farm is built under --work
    (default /tmp), read once and deleted. No results_*/metrics file is opened for
    writing and no cache is consulted: the panel is rebuilt from CSVs every time,
    which is most of the cost and the whole point.

USAGE

    ./venv/bin/python results/price_noise_measure.py --universe nifty100
    ./venv/bin/python results/price_noise_measure.py --universe midcap150
    ./venv/bin/python results/price_noise_measure.py --report-only

    The run writes diagnostics/price_noise_runs.csv (one row per run, the record)
    and diagnostics/price_noise.txt (the report). --report-only rebuilds the
    report from the CSV without running anything.
"""
import argparse
import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                            # noqa: E402
import pandas as pd                                           # noqa: E402

import config                                                 # noqa: E402
import engine_core as _ec                                     # noqa: E402
from engine_core import (build_panel, score_monthly, HORIZON,  # noqa: E402
                         FEATS_V2, precompute, metrics)
from test_exposure import backtest_exposure                   # noqa: E402
from universes.registry import REGISTRY                       # noqa: E402
from v34_common import ann_vol_pct                            # noqa: E402
import arms.registry as arm_reg                               # noqa: E402

# THE PRODUCTION ENSEMBLE, NOT A CHOICE MADE HERE. Same ten seeds
# build_scores_step.py uses; if that list moves, this one must move with it or
# the baseline stops reproducing and the identity gate says so.
SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]

# THE GRID. The levels bracket the difference between the two panels: 53 of
# nifty100's 99 names differ by less than 0.01% in-window, so 0.0001 is a
# perturbation SMALLER than the repoint and 0.005 is larger than all but five.
NOISE_LEVELS = [0.0001, 0.0005, 0.001, 0.005]
NOISE_SEEDS = [101, 202, 303, 404, 505]

VOL_WIN = 60
DIAG = ROOT / "diagnostics"
RUNS_CSV = DIAG / "price_noise_runs.csv"
REPORT = DIAG / "price_noise.txt"

# The v2 row as published, per universe, for the identity gate. Read from the
# artefact at run time rather than written down here -- a literal would be one
# more number to keep in step with a re-run.
IDENTITY_COLS = ["CAGR%", "Sharpe", "MaxDD%", "Trades", "FinalEquity", "AnnVol%"]


# ---------------------------------------------------------------------------
# ONE GRID AT A TIME, ENFORCED RATHER THAN INTENDED
# ---------------------------------------------------------------------------
# TWO PROCESSES RUNNING THIS SCRIPT WOULD CORRUPT EACH OTHER, and not through the
# obvious path. Their --work directories can differ and their perturbed farms are
# separate, but three things are shared and two of them are WRITABLE:
#
#   diagnostics/price_noise_runs.csv   appended by both; interleaved rows cannot
#                                      afterwards be attributed to a process
#   u.prepare_data_dir()               unlinks and re-creates all 99 symlinks in
#                                      data/raw/<universe>_constituents ON EVERY
#                                      CALL. A second process globbing that
#                                      directory mid-rebuild copies a farm with
#                                      fewer names than the universe has, and the
#                                      run that follows is a different universe
#                                      with the right label on it.
#   the machine                        10 joblib workers each; two grids halve
#                                      each other's throughput and make the
#                                      per-run timing meaningless
#
# THE LOCK IS KEYED TO THE CHECKOUT, NOT TO --work, because the resources above
# belong to the checkout. It lives in the system temp directory rather than in
# the tree: a lock file inside the repository is a standing untracked file, and
# this project has already recorded what those cost -- an exception that never
# clears stops being read as an exception (see .gitignore on TAX_AND_CHARGES).
#
# A STALE LOCK IS CLEARED ONLY WHEN ITS PID IS PROVABLY GONE, and the clearing is
# announced. A lock that silently reaps itself is not a lock.
def _lock_path():
    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"price_noise_{key}.lock"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno != errno.ESRCH
    return True


def acquire_lock():
    p = _lock_path()
    me = {"pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
          "argv": sys.argv, "script_sha256": script_fingerprint(), "root": str(ROOT)}
    while True:
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                held = json.loads(p.read_text())
            except Exception:
                held = {}
            pid = int(held.get("pid", -1))
            if pid > 0 and _alive(pid):
                raise SystemExit(
                    f"REFUSING TO START -- another price-noise grid holds the "
                    f"lock on this checkout.\n"
                    f"  lock    {p}\n"
                    f"  pid     {pid}, alive, started {held.get('started')}\n"
                    f"  argv    {held.get('argv')}\n"
                    f"Two grids share diagnostics/price_noise_runs.csv and the "
                    f"constituents symlink farm, so the second one would corrupt "
                    f"both. Wait for it, or stop it and re-run -- the grid is "
                    f"resumable and loses only the cell in flight.")
            print(f"  clearing a STALE lock: pid {pid} from "
                  f"{held.get('started')} is not running", flush=True)
            p.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w") as fh:
            # naming: axis-free -- a mutual-exclusion file in the system temp
            # directory, keyed by the checkout path and deleted on exit. It
            # holds no measurement and is not an artefact, so it varies over
            # no axis.
            json.dump(me, fh)
        return p


# SNAPSHOTTED ONCE, AT IMPORT, AND THAT IS THE WHOLE POINT OF IT.
#
# This read the file on every call until 2026-09-20. A grid runs for hours;
# editing this script while one is in flight would then have stamped the NEW
# hash onto cells computed by the OLD code still resident in memory -- a
# provenance record that is wrong in exactly the case it exists to catch, and
# silently. It also made the script un-editable during a run, which is how the
# next person learns to edit it anyway.
#
# Reading once at import binds the hash to the bytes the interpreter actually
# compiled. Editing the file mid-run now changes nothing about what the running
# process records.
_SCRIPT_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def script_fingerprint():
    """sha256 of this file as it was when this process imported it.

    The git commit is not enough on its own: this script is edited and run before
    it is committed, which is exactly the window the first contaminated grid ran
    in. The content hash is true whether or not the tree is clean, and the commit
    is recorded beside it for the case where it is.
    """
    return _SCRIPT_SHA


def git_commit():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=10)
        return (out.stdout.strip() or "?") + ("+dirty" if dirty.stdout.strip() else "")
    except Exception:
        return "?"


def published_v2(u):
    """The published v2 row for a universe, or None if the artefact is absent."""
    f = Path(u.metrics_dir) / "v34_comparison.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    arm = arm_reg.ARMS["v2"]
    row = d.loc[d["Config"] == arm.label]
    if row.empty:
        return None
    return {c: float(row.iloc[0][c]) for c in IDENTITY_COLS}


def perturb_farm(src, dst, sigma, noise_seed):
    """Write a perturbed copy of every price CSV. Returns (rows, crossings).

    `crossings` counts rows whose perturbed adj_close leaves [low, high] and will
    therefore be reverted to the raw close by canonical_price. It is measured
    here, where the perturbed value is in hand, rather than inferred later.
    """
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(noise_seed)
    n_rows = n_cross = 0
    for f in sorted(Path(src).glob("*.csv")):
        df = pd.read_csv(f)
        if sigma > 0:
            a = df["adj_close"].to_numpy(dtype=float)
            a = a * (1.0 + rng.normal(0.0, sigma, size=len(df)))
            lo = df["low"].to_numpy(dtype=float)
            hi = df["high"].to_numpy(dtype=float)
            n_cross += int(np.sum((a <= 0) | (a < lo) | (a > hi)))
            df["adj_close"] = a
        n_rows += len(df)
        # naming: axis-free -- a scratch copy of the vendor's price farm under
        # --work, deleted after the run; it is an input to one measurement and
        # never an artefact, so it varies over no published axis
        df.to_csv(dst / f.name, index=False)
    return n_rows, n_cross


def run_arm(u, data_dir):
    """Rebuild the panel from data_dir and run v2. Returns (metrics, holdings)."""
    raw = build_panel(HORIZON, data_dir=data_dir)
    keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
    raw = raw[keep]
    p = score_monthly(raw, SEEDS, purge_mode=u.purge_mode)
    p = p[["date", "symbol", "open", "close", "score", "year"]]

    # SAME GUARD AS THE RUN THAT PRODUCED THE ARTEFACT THIS REPRODUCES. A script
    # that recomputes and then checks itself against a published row must run
    # under the production guards or it measures a different engine --
    # rebal_cadence_sweep.py failed exactly this way.
    _ec.set_tradeability(u)
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = pv.loc[bd].median()

    audit = {k: [] for k in ("holdings", "summary", "trades", "ranking",
                             "decisions", "skipped")}
    arm = arm_reg.ARMS["v2"]
    eq, tc, n, _expo = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                         target_vol=tv, audit=audit, rebal=20,
                                         tax_enabled=False, participation_cap=None,
                                         **arm.kwargs)
    m = metrics(eq, arm.label, tc, n)
    held = {}
    for d, g in pd.DataFrame(audit["holdings"]).groupby("date"):
        held[str(pd.Timestamp(d).date())] = frozenset(g["symbol"])
    return ({"CAGR%": round(float(m["CAGR%"]), 4),
             "Sharpe": round(float(m["Sharpe"]), 4),
             "MaxDD%": round(float(m["MaxDD%"]), 4),
             "Trades": int(n),
             "FinalEquity": round(float(eq.iloc[-1]), 2),
             "AnnVol%": round(float(ann_vol_pct(eq)), 4),
             "n_days": int(len(bd))}, held)


def jaccard(a, b):
    """Mean daily Jaccard overlap of two holdings maps, over shared dates."""
    days = sorted(set(a) & set(b))
    if not days:
        return float("nan")
    tot = 0.0
    for d in days:
        u_ = a[d] | b[d]
        tot += (len(a[d] & b[d]) / len(u_)) if u_ else 1.0
    return round(tot / len(days), 4)


def load_runs():
    if RUNS_CSV.exists():
        return pd.read_csv(RUNS_CSV)
    return pd.DataFrame()


def append_run(rec):
    DIAG.mkdir(exist_ok=True)
    df = pd.DataFrame([rec])
    hdr = not RUNS_CSV.exists()
    # naming: axis-free -- the per-run record is keyed by (universe, sigma,
    # seed) INSIDE the file; one grid appends to one file across universes, so
    # the name varies over no axis this project spells into a filename
    df.to_csv(RUNS_CSV, mode="a", header=hdr, index=False)


def measure(tag, work, levels=None, seeds=None):
    """Run the grid for one universe.

    `levels` and `seeds` narrow it. They exist so that a level can be EXTENDED --
    taken from five seeds to ten -- without editing NOISE_SEEDS, which would
    silently re-scope every other level in the same file and make the already
    recorded cells describe a grid that no longer exists. The defaults are the
    full grid, so an unqualified run is unchanged.
    """
    levels = NOISE_LEVELS if levels is None else levels
    seeds = NOISE_SEEDS if seeds is None else seeds
    u = REGISTRY[tag]
    pub = published_v2(u)
    src = u.prepare_data_dir()
    done = set()
    prev = load_runs()
    if len(prev):
        for _, r in prev[prev["tag"] == tag].iterrows():
            done.add((float(r["sigma"]), int(r["noise_seed"])))

    base_held = None
    base_path = Path(work) / f"holdings_{tag}_base.json"
    if base_path.exists():
        base_held = {k: frozenset(v)
                     for k, v in json.loads(base_path.read_text()).items()}

    jobs = [(0.0, 0)] + [(s, ns) for s in levels for ns in seeds]
    for sigma, ns in jobs:
        if (sigma, ns) in done and (sigma > 0 or base_held is not None):
            print(f"  skip sigma={sigma} seed={ns} (already recorded)", flush=True)
            continue
        wd = Path(work) / f"farm_{tag}"
        shutil.rmtree(wd, ignore_errors=True)
        t0 = time.time()
        rows, cross = perturb_farm(src, wd, sigma, ns)
        res, held = run_arm(u, wd)
        shutil.rmtree(wd, ignore_errors=True)

        if sigma == 0.0:
            base_held = held
            Path(work).mkdir(parents=True, exist_ok=True)
            # naming: axis-free -- the baseline's daily holdings, cached under
            # --work so a resumed grid can still compute the overlap column
            # without re-running sigma 0. Scratch, keyed by universe in the
            # filename, and it varies over no published axis.
            base_path.write_text(json.dumps({k: sorted(v)
                                             for k, v in held.items()}))
            # THE IDENTITY GATE, ASSERTED. A baseline that does not reproduce the
            # published row means the harness is not running the shipped arm, and
            # every spread measured after it would be a spread around the wrong
            # centre. Stop rather than record it.
            if pub is not None:
                bad = [c for c in IDENTITY_COLS
                       if abs(res[c] - pub[c]) > (0.005 if c != "FinalEquity" else 0.5)]
                if bad:
                    raise SystemExit(
                        f"IDENTITY GATE FAILED for {tag} on {bad}\n"
                        f"  harness   {[res[c] for c in IDENTITY_COLS]}\n"
                        f"  published {[pub[c] for c in IDENTITY_COLS]}\n"
                        f"The sigma=0 run must reproduce v34_comparison.csv's v2 "
                        f"row. Until it does, no spread below it means anything.")
                print(f"  identity gate PASSES against {u.metrics_dir}/"
                      f"v34_comparison.csv", flush=True)
            else:
                print(f"  identity gate NOT CHECKED -- no v34_comparison.csv for "
                      f"{tag}; the baseline is unanchored", flush=True)

        rec = dict(res)
        rec.update({"tag": tag, "sigma": sigma, "noise_seed": ns,
                    "rows": rows, "bound_crossings": cross,
                    "holdings_overlap_vs_base": (1.0 if sigma == 0.0
                                                 else jaccard(base_held, held)),
                    "minutes": round((time.time() - t0) / 60, 2),
                    "run_date": time.strftime("%Y-%m-%d"),
                    # EVERY CELL NAMES THE CODE AND THE PROCESS THAT PRODUCED IT.
                    # A grid assembled from two script versions, or from two
                    # processes, is not a spread -- and without these columns that
                    # cannot be established after the fact, only argued about.
                    "script_sha256": script_fingerprint(),
                    "git_commit": git_commit(),
                    "pid": os.getpid()})
        if (sigma, ns) not in done:
            append_run(rec)
        print(f"  sigma={sigma} seed={ns}  CAGR {rec['CAGR%']}  "
              f"MaxDD {rec['MaxDD%']}  overlap "
              f"{rec['holdings_overlap_vs_base']}  {rec['minutes']} min",
              flush=True)


def _stats(g, col):
    v = g[col].to_numpy(dtype=float)
    return v.mean(), v.min(), v.max(), (v.std(ddof=1) if len(v) > 1 else 0.0)


def write_report():
    df = load_runs()
    if not len(df):
        raise SystemExit("no runs recorded yet")
    L = []
    W = L.append
    W("=" * 100)
    W(" PRICE NOISE -- how far the shipping arm moves when the prices barely do")
    W("=" * 100)
    W("")
    W("v2 (invvol, breadth-scaled), full re-run per row: panel rebuilt, 10-seed")
    W("ensemble refitted, backtest re-executed. Nothing reused from stored fills.")
    W("")
    W("NOISE: adj_close' = adj_close * (1 + eps), eps ~ Normal(0, sigma), drawn")
    W("independently per (symbol, date). open/high/low/close/volume untouched;")
    W("canonical_price rescales the bar by adj_close'/close as it always does.")
    W("See results/price_noise_measure.py for the full construction and for what")
    W("the bound-crossing column means.")
    W("")
    for tag, g0 in df.groupby("tag"):
        base = g0[g0["sigma"] == 0.0]
        W("-" * 100)
        W(f" {tag}   n={int(g0['n_days'].iloc[0])} sessions   "
          f"run_date {g0['run_date'].iloc[0]}")
        W("-" * 100)
        if len(base):
            b = base.iloc[0]
            W(f"  baseline (sigma 0, identity gate): CAGR {b['CAGR%']:.2f}  "
              f"Sharpe {b['Sharpe']:.2f}  MaxDD {b['MaxDD%']:.2f}  "
              f"trades {int(b['Trades'])}  final {b['FinalEquity']:,.2f}")
        W("")
        W(f"  {'sigma':>8}{'runs':>6}{'CAGR mean':>11}{'min':>9}{'max':>9}"
          f"{'sd':>8}{'spread':>9}{'DD mean':>10}{'DD min':>9}{'DD max':>9}"
          f"{'overlap':>9}{'cross%':>8}")
        for sig, g in g0[g0["sigma"] > 0].groupby("sigma"):
            cm, cmin, cmax, csd = _stats(g, "CAGR%")
            dm, dmin, dmax, _ = _stats(g, "MaxDD%")
            ov = g["holdings_overlap_vs_base"].mean()
            cr = 100.0 * g["bound_crossings"].mean() / g["rows"].mean()
            W(f"  {sig*100:>7.2f}%{len(g):>6}{cm:>11.2f}{cmin:>9.2f}{cmax:>9.2f}"
              f"{csd:>8.2f}{cmax-cmin:>9.2f}{dm:>10.2f}{dmin:>9.2f}{dmax:>9.2f}"
              f"{ov:>9.3f}{cr:>7.2f}%")
        W("")
        W(f"  {'sigma':>8}{'equity mean':>16}{'min':>16}{'max':>16}{'sd':>14}")
        for sig, g in g0[g0["sigma"] > 0].groupby("sigma"):
            em, emin, emax, esd = _stats(g, "FinalEquity")
            W(f"  {sig*100:>7.2f}%{em:>16,.0f}{emin:>16,.0f}{emax:>16,.0f}"
              f"{esd:>14,.0f}")
        W("")
    W("=" * 100)
    DIAG.mkdir(exist_ok=True)
    # naming: axis-free -- one findings file for the whole measurement; every
    # universe, level and seed is a ROW inside it, not a filename variant
    REPORT.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwritten {REPORT}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--universe", help="registry tag, e.g. nifty100")
    ap.add_argument("--work", default="/tmp/price_noise",
                    help="scratch root for the perturbed price farm")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild the report from the CSV, run nothing")
    ap.add_argument("--levels", help="comma-separated sigmas, e.g. 0.0001; "
                                     "default is the full grid")
    ap.add_argument("--seeds", help="comma-separated noise seeds; default is "
                                    "the five in NOISE_SEEDS. Use it to EXTEND "
                                    "a level rather than editing that list")
    a = ap.parse_args(argv)
    if a.report_only:
        write_report()
        return
    if not a.universe:
        ap.error("--universe is required unless --report-only")
    lock = acquire_lock()
    print(f"  lock held: {lock} (pid {os.getpid()}, script "
          f"{script_fingerprint()}, tree {git_commit()})", flush=True)
    try:
        measure(a.universe, a.work,
                levels=[float(x) for x in a.levels.split(",")] if a.levels else None,
                seeds=[int(x) for x in a.seeds.split(",")] if a.seeds else None)
    finally:
        # RELEASED EVEN ON FAILURE. A grid that dies holding its lock makes the
        # next start refuse for the wrong reason, and the operator then learns to
        # delete lock files, which is the end of the lock.
        lock.unlink(missing_ok=True)
    write_report()


if __name__ == "__main__":
    main()
