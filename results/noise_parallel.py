"""
noise_parallel.py -- price-noise draws in parallel, all four arms, both profiles, tax on.

    ./venv/bin/python results/noise_parallel.py run --universe midcap150 \\
        --seeds 101,202,303 --workers 2 --loky 5 --out /path/to/outdir
    ./venv/bin/python results/noise_parallel.py merge  --out /path/to/outdir
    ./venv/bin/python results/noise_parallel.py verify --out /path/to/outdir
    ./venv/bin/python results/noise_parallel.py one --universe midcap150 --seed 101 --loky 10 --out DIR
    ./venv/bin/python results/noise_parallel.py stage 1 --out noise_runs/cleaned
    ./venv/bin/python results/noise_parallel.py analyse --out noise_runs/cleaned

THE HARNESS OF experiments/CLEANED_NOISE_PREREG.txt, since 2026-09-27. `stage`
and `analyse` implement that pre-registration and nothing else; read it for the
accept rule. Until 2026-09-27 this was the harness of
experiments/FOUR_ARM_NOISE_PREREG.txt, measured on the uncleaned prices and
superseded; its records (diagnostics/four_arm_noise*.{txt,csv}) are not written
by this version. results/after_tax_noise.py is not touched.

STAGES, BASELINES AND THE ORDER OF WORK
    `stage N` runs the universes of STAGES[N] in that order, each as a sigma-0
    baseline followed by the ten noise seeds, two draws at a time with five loky
    workers each. A universe's draws start only after its baseline result exists
    and passed (baseline_check: every arm under both profiles and the investable
    buy & hold within BASELINE_TOL of the published figures). A universe whose
    baseline fails gets no draws. Work is taken in list order: the first job whose
    baseline condition is met starts next, so a later universe's baseline can run
    beside an earlier universe's draws. Re-running the same command resumes: every
    draw with a result file is skipped.

ANALYSE merges the draws, checks each universe (baseline passed, ten draws, one
harness hash), applies RULE to every cell and profile, labels each cell with its
nt_verify result, and writes diagnostics/cleaned_noise.txt and
diagnostics/cleaned_noise_runs.csv.

ONE PROCESS PER DRAW, EACH WITH A FIXED NUMBER OF LOKY WORKERS
    `run` starts up to --workers child processes, one per (universe, seed), each
    running `one`. Inside a draw, score_monthly fits its ten LightGBM seeds in loky
    worker processes exactly as the production path does; the only change is the
    pool size, which is --loky instead of os.cpu_count(). engine_core.Parallel is
    wrapped to set n_jobs; engine_core is not edited. Each fit is still
    engine_core._fit_seed with its default n_jobs=1, one thread, and BLAS/OpenMP
    are pinned to one thread before numpy is imported. The ensemble is the mean
    over the same seeds in the same order, so the pool size cannot change the
    scores; `verify` checks that against the recorded v2 draws.

    --workers x --loky must be at most 10, the machine's core count; `run`
    refuses anything larger.

    A first version (2026-09-26) fitted the seeds in sequence at n_jobs=1 per
    draw. One draw was then several times slower than the old harness's, so
    running draws side by side gained nothing; it was replaced before any draw
    finished.

    Each child is wrapped in /usr/bin/time -l, which records the draw process's
    own peak; `run` also samples the whole process tree, loky workers included
    (see cmd_run).

PER DRAW
    1. clean every constituent file, then perturb its adj_close, with
       perturb_cleaned_farm below, into the draw's own scratch folder
       <work>/<tag>_s<seed>/. The perturbation comes after the cleaning.
    2. rebuild the raw panel with build_panel(clean=False), so the farm is not
       cleaned a second time, and refit the production 10-seed monthly ensemble.
    3. on that one panel: the four arms of arms.registry, tax on, headline (nothing
       sold at the end, the last partial year settled), cadence 20, under the
       research profile (no cap) and the tradeable profile (profiles.PROFILES cap,
       vol20 from the universe's own farm; volume is not perturbed). Then the
       investable taxed buy & hold (bh_held.held_lots, eq_headline), which is the
       same for every arm and profile.
    4. write <out>/draws/<tag>_s<seed>.json atomically: a temporary file in the
       same directory, then os.replace. A draw with a result file is never re-run;
       a restart skips it.

    `verify` compared v2 with diagnostics/after_tax_noise_runs.csv, which was
    measured on the uncleaned prices; it is retired and exits 2.

MERGE writes <out>/noise_parallel_runs.csv, one row per (draw, arm, profile), from
the per-draw files, sorted. It reads only finished result files.
"""
import os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["PYTHONHASHSEED"] = "0"

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_SCRIPT_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]

SIGMA = 0.0001
VOL_WIN = 60
REBAL = 20
PROFILES = ("research", "tradeable")
PYTHON = str(ROOT / "venv" / "bin" / "python")
DEFAULT_WORK = "/tmp/noise_parallel"

# FIXED BY experiments/CLEANED_NOISE_PREREG.txt.
STAGES = {1: ("nifty50", "midcap50", "midcap100", "nifty100"),
          2: ("midcap150", "smallcap250", "nifty200"),
          3: ("nifty500",)}
NOISE_SEEDS = (101, 202, 303, 404, 505, 606, 707, 808, 909, 1010)
ARM_NAMES = ("v1", "v2", "v3", "v4")
STAGE_WORKERS, STAGE_LOKY = 2, 5
BASELINE_TOL = 0.0001
PUBLISHED_RESEARCH = ROOT / "diagnostics" / "tax_on_all_arms.csv"
PUBLISHED_TRADEABLE = ROOT / "diagnostics" / "tradeable_tax_all_arms.csv"
# nt_verify NOT VERIFIED cells on the cleaned prices, 2026-09-27
# (check_all.NT_VERIFY_UNGATED, diagnostics/nt_verify_all_arms_20260927.txt),
# copied so the label is fixed with the pre-registration. A supported cell in this
# set is reported as "supported, not port-verified".
NOT_VERIFIED = {
    ("midcap150", "v1"), ("midcap150", "v3"),
    ("midcap50", "v3"), ("midcap50", "v4"),
    ("midcap100", "v1"), ("midcap100", "v2"), ("midcap100", "v3"), ("midcap100", "v4"),
    ("nifty200", "v3"), ("nifty200", "v4"),
    ("nifty500", "v3"), ("nifty500", "v4"),
}
RULE = ("For each cell and profile, an after-tax edge is supported only if at least 9 "
        "of 10 draws have a gap strictly above zero and the mean gap exceeds one sample "
        "sd (ddof=1) of the gaps. A cell is reported as supported only if it passes "
        "under both research and tradeable. Anything else is not supported.")
REPORT = ROOT / "diagnostics" / "cleaned_noise.txt"
RUNS_CSV = ROOT / "diagnostics" / "cleaned_noise_runs.csv"


def cagr(eq):
    """engine_core.metrics' CAGR, in percent, at full precision."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100)


def draw_name(tag, seed):
    return f"{tag}_s{seed}"


def _loky_pool(engine_core, n):
    """Make score_monthly's seed pool n loky workers instead of os.cpu_count()."""
    orig = engine_core.Parallel

    def pool(*args, **kw):
        kw["n_jobs"] = n
        return orig(*args, **kw)

    engine_core.PARALLEL_SEEDS = True
    engine_core.Parallel = pool


def one_draw(tag, seed, sigma, work, loky):
    """Run one draw. -> the result dict written to the draw's file."""
    import numpy as np
    import pandas as pd
    import config
    import engine_core as ec
    import arms.registry as arm_reg
    import bh_held
    import profiles
    import tradability
    from engine_core import build_panel, score_monthly, precompute, HORIZON, _load_calendar
    from features_v2 import FEATS_V2
    from numerics import rolling_std
    from test_exposure import backtest_exposure
    from universes.registry import REGISTRY
    from price_noise_measure import SEEDS

    _loky_pool(ec, loky)
    u = REGISTRY[tag]
    t0 = time.time()
    src = u.prepare_data_dir()
    key = config.run_key(u)
    wd = Path(work) / draw_name(tag, seed)
    shutil.rmtree(wd, ignore_errors=True)
    try:
        rows, cross = perturb_cleaned_farm(src, wd / "farm", sigma, seed)
        t_perturb = time.time()
        raw = build_panel(HORIZON, data_dir=wd / "farm", clean=False)
        keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
        p = score_monthly(raw[keep], SEEDS, purge_mode=u.purge_mode)
        del raw
        t_panel = time.time()
        p = p[["date", "symbol", "open", "close", "score", "year"]]
        ec.set_tradeability(u)
        px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
        op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
        sc = p.pivot_table(index="date", columns="symbol", values="score")
        bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
        pc = precompute(px)
        mom20 = px / px.shift(20) - 1
        idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
        pv = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
        tv = pv.loc[bd].median()
        vol20 = tradability.median_volume(src, _load_calendar(),
                                          config.BT_START_DATE, config.BT_END_DATE)
        cap_kw = {"research": {"participation_cap": None},
                  "tradeable": {"participation_cap": profiles.PROFILES["tradeable"]["participation_cap"],
                                "vol20": vol20}}
        arms = {}
        for prof in PROFILES:
            for name, arm in arm_reg.ARMS.items():
                ta = time.time()
                audit = {k: [] for k in ("holdings", "summary", "trades", "ranking",
                                         "decisions", "skipped")}
                eq, _tc, ntr, _ = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                                    target_vol=tv, audit=audit,
                                                    rebal=REBAL, tax_enabled=True,
                                                    **cap_kw[prof], **arm.kwargs)
                binds = sum(1 for r in audit["skipped"]
                            if r.get("reason") == "participation cap")
                arms[f"{name}@{prof}"] = {
                    "arm": name, "profile": prof, "cagr": cagr(eq),
                    "final_equity": float(eq.iloc[-1]),
                    "tax": float(audit["tax"]["cum_tax"]), "trades": int(ntr),
                    "cap_binds": int(binds), "seconds": round(time.time() - ta, 2)}
        tb = time.time()
        bh = bh_held.held_lots(px, op, bd)["eq_headline"]
        bh_s = round(time.time() - tb, 2)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    t_end = time.time()
    return {"tag": tag, "sigma": sigma, "noise_seed": seed, "bh_cagr": cagr(bh),
            "bh_final_equity": float(bh.iloc[-1]), "bh_seconds": bh_s,
            "arms": arms, "rows": rows, "bound_crossings": cross,
            "minutes_total": round((t_end - t0) / 60, 3),
            "minutes_perturb": round((t_perturb - t0) / 60, 3),
            "minutes_panel": round((t_panel - t_perturb) / 60, 3),
            "minutes_arms": round((t_end - t_panel) / 60, 3),
            "loky_workers": loky, "run_date": time.strftime("%Y-%m-%d %H:%M"),
            "script_sha256": _SCRIPT_SHA, "perturb_sha256": _SCRIPT_SHA,
            **key}


def perturb_cleaned_farm(src, dst, sigma, noise_seed):
    """Clean every price CSV, then perturb it, and write the farm. -> (rows, crossings).

    The order of experiments/CLEANED_NOISE_PREREG.txt: each file is cleaned with
    results/ratio_clean.clean on exactly the rows engine_core.build_panel would
    clean (PRICE_COLS, dropna, sorted by date, calendar sessions), and only then
    is adj_close multiplied by (1 + eps), eps ~ Normal(0, sigma). The generator is
    price_noise_measure.perturb_farm's: one numpy Generator per noise seed, one
    draw per row of each file in file order, files in sorted order.

    Each file gains a boolean `clean_exempt` column marking the cleaned rows, and
    the panel is built with build_panel(clean=False), which reads it as
    canonical_price's exemption and does not clean a second time. At sigma 0 the
    panel equals the published one; the baseline gate checks the figures.

    `crossings` counts rows whose perturbed adj_close leaves the raw [low, high]
    and is not exempt, so canonical_price will fall back to close there.
    """
    import numpy as np
    import config
    import ratio_clean
    from engine_core import PRICE_COLS, _load_calendar
    from config import read_table
    cal = _load_calendar()
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(noise_seed)
    n_rows = n_cross = 0
    for f in sorted(Path(src).glob("*.csv")):
        df = read_table(f)
        d = config.read_price_csv(f).sort_values("date")[PRICE_COLS].dropna()
        cleaned, exempt, _ev = ratio_clean.clean(d, cal)
        ex = np.zeros(len(df), dtype=bool)
        if exempt.any():
            rows = d.index[exempt]
            df.loc[rows, "adj_close"] = cleaned.loc[rows, "adj_close"]
            ex[df.index.get_indexer(rows)] = True
        if sigma > 0:
            a = df["adj_close"].to_numpy(dtype=float)
            a = a * (1.0 + rng.normal(0.0, sigma, size=len(df)))
            lo = df["low"].to_numpy(dtype=float)
            hi = df["high"].to_numpy(dtype=float)
            n_cross += int(np.sum(((a <= 0) | (a < lo) | (a > hi)) & ~ex))
            df["adj_close"] = a
        df["clean_exempt"] = ex
        n_rows += len(df)
        # naming: axis-free -- a scratch copy of the farm under --work, deleted
        # after the draw; an input to one measurement, never an artefact
        df.to_csv(dst / f.name, index=False)
    return n_rows, n_cross


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def result_path(out, tag, seed):
    return Path(out) / "draws" / f"{draw_name(tag, seed)}.json"


_KEYS = {}


def current_key(tag):
    """config.run_key for `tag`, computed once per process."""
    if tag not in _KEYS:
        import config
        from universes.registry import REGISTRY
        _KEYS[tag] = config.run_key(REGISTRY[tag])
    return _KEYS[tag]


def draw_state(out, tag, seed):
    """"missing", "current" or "stale" for one draw file.

    STALE MEANS THE FILE WAS WRITTEN FROM OTHER CODE OR OTHER DATA: its
    panel_code or source_digest differs from the current config.run_key, or it
    predates those fields. A stale draw is reported and re-run, never reused.
    Until 2026-09-27 a file's existence was enough, so stage 1's draws on the
    uncleaned prices would have been read back after the cleaning as current.
    """
    import config
    f = result_path(out, tag, seed)
    if not f.exists():
        return "missing"
    rec = json.loads(f.read_text())
    return "current" if config.run_key_matches(rec, current_key(tag)) else "stale"


def baseline_check(res):
    """-> (ok, failures): the sigma-0 run against the published full-precision figures."""
    from config import read_table
    pr = read_table(PUBLISHED_RESEARCH)
    pt = read_table(PUBLISHED_TRADEABLE)
    tag, fails = res["tag"], []
    want = [("bh", res["bh_cagr"], float(pr[pr.universe == tag].bh_cagr.iloc[0]))]
    for a in ARM_NAMES:
        want.append((f"{a}@research", res["arms"][f"{a}@research"]["cagr"],
                     float(pr[(pr.universe == tag) & (pr.arm == a)].arm_cagr.iloc[0])))
        want.append((f"{a}@tradeable", res["arms"][f"{a}@tradeable"]["cagr"],
                     float(pt[(pt.universe == tag) & (pt.arm == a)].tradeable_cagr.iloc[0])))
    for name, got, pub in want:
        if abs(got - pub) > BASELINE_TOL:
            fails.append(f"{name}: {got:.6f} against published {pub:.4f}")
    return not fails, fails


def cmd_one(a):
    res = one_draw(a.universe, a.seed, a.sigma, a.work, a.loky)
    if a.seed == 0:
        ok, fails = baseline_check(res)
        res["baseline"] = {"ok": ok, "failures": fails, "tolerance": BASELINE_TOL}
    write_atomic(result_path(a.out, a.universe, a.seed), json.dumps(res, indent=1))
    return 0


def _baseline_state(out, tag):
    """None if no current baseline result yet, else True/False for pass/fail.

    A stale baseline file counts as none: its verdict describes other code or data.
    """
    if draw_state(out, tag, 0) != "current":
        return None
    f = result_path(out, tag, 0)
    return bool(json.loads(f.read_text()).get("baseline", {}).get("ok", False))


def _peak_rss(time_file):
    """Peak resident set size in bytes from /usr/bin/time -l output, or None."""
    try:
        for line in Path(time_file).read_text().splitlines():
            if "maximum resident set size" in line:
                return int(line.split()[0])
    except OSError:
        pass
    return None


def _tree_rss():
    """{pid: resident bytes of that process and all its descendants}, from ps."""
    rows = subprocess.run(["ps", "-axo", "pid=,ppid=,rss="], capture_output=True,
                          text=True).stdout.split("\n")
    kids, own = {}, {}
    for r in rows:
        f = r.split()
        if len(f) != 3:
            continue
        pid, ppid, kb = int(f[0]), int(f[1]), int(f[2])
        own[pid] = kb * 1024
        kids.setdefault(ppid, []).append(pid)

    def total(pid):
        return own.get(pid, 0) + sum(total(c) for c in kids.get(pid, []))
    return total


def cmd_run(a):
    """Schedule draws, at most --workers at a time; skip draws already written.

    MEMORY IS SAMPLED OVER EACH DRAW'S WHOLE PROCESS TREE. /usr/bin/time -l
    reports the draw's own process only, and its seed fits run in loky worker
    processes it does not count. Every 2 s the resident size of each running
    draw's tree is summed from ps; the per-draw peak goes to logs/<draw>.mem and
    the peak of all draws together to the run summary. Sampling can miss a peak
    shorter than 2 s.
    """
    from universes.registry import REGISTRY
    if a.workers * a.loky > 10:
        raise SystemExit(f"--workers {a.workers} x --loky {a.loky} = {a.workers * a.loky}, "
                         f"more than the machine's 10 cores")
    out = Path(a.out)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    jobs = []
    for tag in a.universe.split(","):
        # The symlink farm is shared by every draw of a universe. Build it here,
        # once, before any child starts, so no two children race to create it.
        REGISTRY[tag].prepare_data_dir()
        seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else []
        if a.baseline:
            seeds = [0] + seeds
        for s in seeds:
            st = draw_state(out, tag, s)
            if st == "current":
                print(f"  skip {draw_name(tag, s)} (current result file present)", flush=True)
                continue
            if st == "stale":
                print(f"  STALE {draw_name(tag, s)}: its panel_code or source_digest is "
                      f"not the current one; re-running it", flush=True)
            jobs.append((tag, s))
    running, peak, failed, done = {}, {}, [], []
    peak_all, t_start = 0, time.time()
    gate = a.baseline
    while jobs or running:
        while len(running) < a.workers:
            # With --baseline, a universe's noise draws wait for its baseline to
            # exist and pass; a failed baseline drops them. Otherwise first come.
            pick = None
            for i, (tag, s) in enumerate(list(jobs)):
                st = _baseline_state(out, tag) if (gate and s != 0) else True
                if st is False:
                    print(f"  drop {draw_name(tag, s)}: {tag} baseline failed", flush=True)
                    jobs.remove((tag, s))
                    continue
                if st:
                    pick = jobs.index((tag, s))
                    break
            if pick is None:
                break
            tag, s = jobs.pop(pick)
            name = draw_name(tag, s)
            sigma = 0.0 if s == 0 else SIGMA
            log = open(out / "logs" / f"{name}.log", "w")
            cmd = ["/usr/bin/time", "-l", "-o", str(out / "logs" / f"{name}.time"),
                   PYTHON, str(Path(__file__).resolve()), "one", "--universe", tag,
                   "--seed", str(s), "--sigma", repr(sigma), "--loky", str(a.loky),
                   "--out", str(out), "--work", a.work]
            running[name] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                              cwd=str(ROOT)), log, time.time())
            peak[name] = 0
            print(f"  start {name}  ({len(running)} running, {len(jobs)} queued)", flush=True)
        if not running and jobs:
            print(f"  STOPPED: {len(jobs)} draw(s) wait on a baseline that has no result "
                  f"(its process failed; see {out / 'logs'}). Re-run to retry it.", flush=True)
            failed.append("baseline missing")
            break
        time.sleep(2)
        total = _tree_rss()
        now = 0
        for name, (proc, _log, _t0) in running.items():
            m = total(proc.pid)
            peak[name] = max(peak[name], m)
            now += m
        peak_all = max(peak_all, now)
        for name, (proc, log, t0) in list(running.items()):
            rc = proc.poll()
            if rc is None:
                continue
            log.close()
            del running[name]
            mins = (time.time() - t0) / 60
            write_atomic(out / "logs" / f"{name}.mem",
                         json.dumps({"peak_tree_rss_bytes": peak[name], "minutes": mins}))
            print(f"  done  {name}  exit {rc}  {mins:.1f} min  "
                  f"peak tree RSS {peak[name] / 2**30:.2f} GB", flush=True)
            (failed if rc != 0 else done).append(name)
    hours = (time.time() - t_start) / 3600
    summary = {"workers": a.workers, "loky": a.loky, "draws": done, "failed": failed,
               "wall_hours": hours, "draws_per_hour": len(done) / hours if hours else None,
               "peak_all_draws_bytes": peak_all,
               "started": time.strftime("%Y-%m-%d %H:%M", time.localtime(t_start))}
    write_atomic(out / "logs" / f"run_{int(t_start)}.json", json.dumps(summary, indent=1))
    print(f"  run: {len(done)} draw(s) in {hours:.2f} h, "
          f"{summary['draws_per_hour'] or 0:.2f} per hour, peak of all draws together "
          f"{peak_all / 2**30:.2f} GB", flush=True)
    if failed:
        print(f"  FAILED: {', '.join(failed)} (see {out / 'logs'})", flush=True)
        return 1
    return 0


def load_draws(out):
    """Every current draw under `out`. Stale draws are named and left out."""
    import config
    res = []
    for f in sorted((Path(out) / "draws").glob("*.json")):
        d = json.loads(f.read_text())
        if not config.run_key_matches(d, current_key(d["tag"])):
            print(f"  STALE {f.name}: not the current panel_code or source_digest; "
                  f"left out", flush=True)
            continue
        d["peak_rss_bytes"] = _peak_rss(Path(out) / "logs" / f"{f.stem}.time")
        mem = Path(out) / "logs" / f"{f.stem}.mem"
        d["peak_tree_rss_bytes"] = (json.loads(mem.read_text())["peak_tree_rss_bytes"]
                                    if mem.exists() else None)
        res.append(d)
    return res


def cmd_merge(a):
    import pandas as pd
    rows = []
    for d in load_draws(a.out):
        for k, r in d["arms"].items():
            rows.append({"tag": d["tag"], "sigma": d["sigma"], "noise_seed": d["noise_seed"],
                         "arm": r["arm"], "profile": r["profile"], "cagr": r["cagr"],
                         "bh_cagr": d["bh_cagr"], "gap": r["cagr"] - d["bh_cagr"],
                         "tax": r["tax"], "final_equity": r["final_equity"],
                         "trades": r["trades"], "cap_binds": r["cap_binds"],
                         "rows": d["rows"], "bound_crossings": d["bound_crossings"],
                         "minutes_total": d["minutes_total"],
                         "minutes_panel": d["minutes_panel"],
                         "minutes_arms": d["minutes_arms"],
                         "peak_rss_bytes": d["peak_rss_bytes"],
                         "peak_tree_rss_bytes": d["peak_tree_rss_bytes"],
                         "loky_workers": d.get("loky_workers"), "run_date": d["run_date"],
                         "script_sha256": d["script_sha256"],
                         "perturb_sha256": d["perturb_sha256"]})
    df = pd.DataFrame(rows).sort_values(["tag", "noise_seed", "profile", "arm"])
    f = Path(a.out) / "noise_parallel_runs.csv"
    write_atomic(f, df.to_csv(index=False))
    print(f"  merged {len(df)} rows from {df[['tag', 'noise_seed']].drop_duplicates().shape[0]} "
          f"draws -> {f}")
    return 0


def cmd_verify(a):
    """Retired 2026-09-27: it compared v2 with a record measured on the uncleaned prices."""
    print("  verify is retired: diagnostics/after_tax_noise_runs.csv was measured on the "
          "uncleaned prices (experiments/CLEANED_NOISE_PREREG.txt)")
    return 2


def cmd_stage(a):
    """Run one pre-registered stage, then print how many draws each universe has."""
    if a.n not in STAGES:
        raise SystemExit(f"stage must be one of {sorted(STAGES)}")
    out = Path(a.out)
    args = argparse.Namespace(universe=",".join(STAGES[a.n]),
                              seeds=",".join(str(x) for x in NOISE_SEEDS), baseline=True,
                              workers=STAGE_WORKERS, loky=STAGE_LOKY, out=str(out),
                              work=str(out / "work"))
    rc = cmd_run(args)
    print(f"\n  STAGE {a.n}: finished draws per universe (baseline + 10 seeds = 11)")
    for tag in STAGES[a.n]:
        n = sum(draw_state(out, tag, sd) == "current" for sd in (0,) + NOISE_SEEDS)
        b = _baseline_state(out, tag)
        bl = "no baseline yet" if b is None else ("baseline PASSED" if b else "baseline FAILED")
        print(f"    {tag:<12} {n:>2} of 11   {bl}")
    return rc


def verdict(gaps):
    """RULE for one cell and profile. -> (supported, above, mean, sd)."""
    import numpy as np
    g = np.asarray(gaps, dtype=float)
    above = int((g > 0).sum())
    mean = float(g.mean())
    sd = float(g.std(ddof=1))
    return (len(g) == 10 and above >= 9 and mean > sd), above, mean, sd


def cmd_analyse(a):
    """Apply experiments/CLEANED_NOISE_PREREG.txt to every finished universe."""
    import pandas as pd
    draws = load_draws(a.out)
    order = [t for n in sorted(STAGES) for t in STAGES[n]]
    rows = []
    for d in draws:
        for r in d["arms"].values():
            rows.append({"tag": d["tag"], "sigma": d["sigma"], "noise_seed": d["noise_seed"],
                         "arm": r["arm"], "profile": r["profile"], "cagr": round(r["cagr"], 6),
                         "bh_cagr": round(d["bh_cagr"], 6),
                         "gap": round(r["cagr"] - d["bh_cagr"], 6),
                         "tax": round(r["tax"], 2), "final_equity": round(r["final_equity"], 2),
                         "trades": r["trades"], "cap_binds": r["cap_binds"],
                         "rows": d["rows"], "bound_crossings": d["bound_crossings"],
                         "minutes_total": d["minutes_total"], "run_date": d["run_date"],
                         "script_sha256": d["script_sha256"],
                         "perturb_sha256": d["perturb_sha256"]})
    df = pd.DataFrame(rows)
    if len(df):
        df["_o"] = df["tag"].map({t: i for i, t in enumerate(order)})
        df = df.sort_values(["_o", "noise_seed", "profile", "arm"]).drop(columns="_o")
    # naming: axis-free -- the pre-registered record of one measurement, fixed to
    # tax on, cadence 20 and both profiles; it varies over no published axis
    write_atomic(RUNS_CSV, df.to_csv(index=False))

    by = {(d["tag"], d["noise_seed"]): d for d in draws}
    L = ["AFTER-TAX EDGE UNDER PRICE NOISE, CLEANED PRICES -- experiments/CLEANED_NOISE_PREREG.txt",
         "=" * 86,
         "Arm tax-on headline CAGR minus the investable taxed buy & hold headline CAGR, points,",
         f"on the same perturbed panel. sigma {SIGMA} (0.01%), seeds {NOISE_SEEDS[0]} to "
         f"{NOISE_SEEDS[-1]}, n=10, research and tradeable profiles.",
         f"RULE (verbatim): {RULE}",
         "32 cells are tested: 4 arms x 8 universes. Every cell is reported, under both profiles.",
         "A single supported cell on its own is not to be read as an edge.",
         "The tradeable profile is UNGATED: nothing replays what the port does under it.",
         "nt_verify: the result on the cleaned prices, 2026-09-27. A supported cell that is NOT",
         "VERIFIED there is reported as SUPPORTED, NOT PORT-VERIFIED.", ""]
    supported, decided = [], 0
    for tag in order:
        base = by.get((tag, 0))
        got = [s for s in NOISE_SEEDS if (tag, s) in by]
        L.append(f"{tag}")
        if base is None:
            L += ["  not run", ""]
            continue
        b = base.get("baseline", {})
        if not b.get("ok"):
            L += [f"  baseline FAILED: {'; '.join(b.get('failures', []))}",
                  "  measurement stopped for this universe; no draw counts", ""]
            continue
        L.append(f"  baseline PASSED (every arm, both profiles, and the buy & hold within "
                 f"{BASELINE_TOL} of the published figures); buy & hold {base['bh_cagr']:.4f}")
        if len(got) < 10:
            L += [f"  {len(got)} of 10 draws recorded; no verdict until all 10 are in", ""]
            continue
        shas = {by[(tag, s)]["script_sha256"] for s in (0,) + NOISE_SEEDS}
        if shas != {_SCRIPT_SHA}:
            L += [f"  VOID: draws carry harness hash(es) {sorted(shas)}, the committed harness "
                  f"is {_SCRIPT_SHA}", ""]
            continue
        for arm in ARM_NAMES:
            ntv = "NOT VERIFIED" if (tag, arm) in NOT_VERIFIED else "VERIFIED"
            res = {}
            for prof in PROFILES:
                gaps = [by[(tag, s)]["arms"][f"{arm}@{prof}"]["cagr"] - by[(tag, s)]["bh_cagr"]
                        for s in NOISE_SEEDS]
                ok, above, mean, sd = verdict(gaps)
                res[prof] = ok
                L.append(f"  {arm} {prof:<9} gaps " + " ".join(f"{g:+.4f}" for g in gaps))
                L.append(f"  {arm} {prof:<9} mean {mean:+.4f}  sd {sd:.4f}  min {min(gaps):+.4f}  "
                         f"max {max(gaps):+.4f}  draws above zero {above} of 10  -> "
                         f"{'passes' if ok else 'fails'}")
            decided += 1
            cell_ok = res["research"] and res["tradeable"]
            if cell_ok:
                supported.append(f"{tag} {arm}" + ("" if ntv == "VERIFIED" else " (not port-verified)"))
            label = ("NOT SUPPORTED" if not cell_ok else
                     "SUPPORTED" if ntv == "VERIFIED" else "SUPPORTED, NOT PORT-VERIFIED")
            L.append(f"  {arm} VERDICT: {label} "
                     f"(research {'passes' if res['research'] else 'fails'}, tradeable "
                     f"{'passes' if res['tradeable'] else 'fails'}; nt_verify {ntv})"
                     + (" -- one of 32 cells tested" if cell_ok else ""))
        L.append("")
    L.append(f"SUMMARY: {decided} cell(s) decided so far, of 32 tested; supported: "
             + (", ".join(supported) + " (32 cells were tested; a single supported cell "
                "on its own is not to be read as an edge)" if supported else "none"))
    text = "\n".join(L) + "\n"
    # naming: axis-free -- the pre-registered report, see RUNS_CSV above
    write_atomic(REPORT, text)
    print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one")
    o.add_argument("--universe", required=True)
    o.add_argument("--seed", type=int, required=True)
    o.add_argument("--sigma", type=float, default=SIGMA)
    o.add_argument("--loky", type=int, required=True, help="loky workers for the seed fits")
    o.add_argument("--out", required=True)
    o.add_argument("--work", default=DEFAULT_WORK)
    r = sub.add_parser("run")
    r.add_argument("--universe", required=True, help="tag or comma-separated tags")
    r.add_argument("--seeds", default="")
    r.add_argument("--baseline", action="store_true", help="also run sigma 0 (seed 0)")
    r.add_argument("--workers", type=int, required=True, help="draws at once")
    r.add_argument("--loky", type=int, required=True, help="loky workers per draw")
    r.add_argument("--out", required=True)
    r.add_argument("--work", default=DEFAULT_WORK)
    for n in ("merge", "verify", "analyse"):
        s = sub.add_parser(n)
        s.add_argument("--out", required=True)
    st = sub.add_parser("stage")
    st.add_argument("n", type=int)
    st.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    return {"one": cmd_one, "run": cmd_run, "merge": cmd_merge, "verify": cmd_verify,
            "stage": cmd_stage, "analyse": cmd_analyse}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
