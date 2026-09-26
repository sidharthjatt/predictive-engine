"""
noise_parallel.py -- price-noise draws in parallel, all four arms, both profiles, tax on.

    ./venv/bin/python results/noise_parallel.py run --universe midcap150 \\
        --seeds 101,202,303 --workers 2 --loky 5 --out /path/to/outdir
    ./venv/bin/python results/noise_parallel.py merge  --out /path/to/outdir
    ./venv/bin/python results/noise_parallel.py verify --out /path/to/outdir
    ./venv/bin/python results/noise_parallel.py one --universe midcap150 --seed 101 --loky 10 --out DIR

A HARNESS, NOT A MEASUREMENT. No pre-registration names this file, and nothing it
writes is a published figure. It exists so that a later pre-registered test can
run every arm on every universe in a practical wall-clock time. It does not touch
results/after_tax_noise.py, which remains the harness of the pre-registered v2
measurement.

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
    1. perturb every constituent's adj_close with price_noise_measure.perturb_farm,
       unchanged, into the draw's own scratch folder <work>/<tag>_s<seed>/.
    2. rebuild the raw panel and refit the production 10-seed monthly ensemble, as
       results/after_tax_noise.one_run does.
    3. on that one panel: the four arms of arms.registry, tax on, headline (nothing
       sold at the end, the last partial year settled), cadence 20, under the
       research profile (no cap) and the tradeable profile (profiles.PROFILES cap,
       vol20 from the universe's own farm; volume is not perturbed). Then the
       investable taxed buy & hold (bh_held.held_lots, eq_headline), which is the
       same for every arm and profile.
    4. write <out>/draws/<tag>_s<seed>.json atomically: a temporary file in the
       same directory, then os.replace. A draw with a result file is never re-run;
       a restart skips it.

    The panel construction for v2 under research is the same code path as
    after_tax_noise.one_run, so v2 and the buy & hold must reproduce
    diagnostics/after_tax_noise_runs.csv exactly; `verify` checks that.

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
    from price_noise_measure import SEEDS, perturb_farm, script_fingerprint

    _loky_pool(ec, loky)
    u = REGISTRY[tag]
    t0 = time.time()
    src = u.prepare_data_dir()
    wd = Path(work) / draw_name(tag, seed)
    shutil.rmtree(wd, ignore_errors=True)
    try:
        rows, cross = perturb_farm(src, wd / "farm", sigma, seed)
        t_perturb = time.time()
        raw = build_panel(HORIZON, data_dir=wd / "farm")
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
            "script_sha256": _SCRIPT_SHA, "perturb_sha256": script_fingerprint()}


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


def cmd_one(a):
    res = one_draw(a.universe, a.seed, a.sigma, a.work, a.loky)
    write_atomic(result_path(a.out, a.universe, a.seed), json.dumps(res, indent=1))
    return 0


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
            if result_path(out, tag, s).exists():
                print(f"  skip {draw_name(tag, s)} (result file present)", flush=True)
                continue
            jobs.append((tag, s))
    running, peak, failed, done = {}, {}, [], []
    peak_all, t_start = 0, time.time()
    while jobs or running:
        while jobs and len(running) < a.workers:
            tag, s = jobs.pop(0)
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
    res = []
    for f in sorted((Path(out) / "draws").glob("*.json")):
        d = json.loads(f.read_text())
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
    """v2 research and the buy & hold must equal the recorded pre-registered draws."""
    import pandas as pd
    from config import read_table
    ref = read_table(ROOT / "diagnostics" / "after_tax_noise_runs.csv")
    bad, checked = [], 0
    for d in load_draws(a.out):
        r = ref[(ref["tag"] == d["tag"]) & (ref["noise_seed"] == d["noise_seed"])]
        if not len(r):
            continue
        r = r.iloc[0]
        v2 = d["arms"]["v2@research"]["cagr"]
        # The recorded CSV rounds CAGR to 6 decimals, so "full precision" is
        # equality after the same rounding, plus the unrounded final equity and
        # tax, which the CSV records to the paisa.
        same = (round(v2, 6) == float(r["v2_cagr"])
                and round(d["bh_cagr"], 6) == float(r["bh_cagr"])
                and round(d["arms"]["v2@research"]["final_equity"], 2) == float(r["v2_final_equity"])
                and round(d["arms"]["v2@research"]["tax"], 2) == float(r["v2_tax"])
                and d["rows"] == int(r["rows"]) and d["bound_crossings"] == int(r["bound_crossings"]))
        checked += 1
        line = (f"  {d['tag']:<10} seed {d['noise_seed']:>4}: v2 {v2:.6f} vs {r['v2_cagr']:.6f}  "
                f"bh {d['bh_cagr']:.6f} vs {r['bh_cagr']:.6f}  "
                f"final {d['arms']['v2@research']['final_equity']:.2f} vs {r['v2_final_equity']:.2f}  "
                f"{'MATCH' if same else 'DIFFERS'}")
        print(line)
        if not same:
            bad.append(f"{d['tag']} seed {d['noise_seed']}")
    print(f"  {checked} draw(s) checked, {len(bad)} differ" + (f": {', '.join(bad)}" if bad else ""))
    return 1 if bad or not checked else 0


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
    for n in ("merge", "verify"):
        s = sub.add_parser(n)
        s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    return {"one": cmd_one, "run": cmd_run, "merge": cmd_merge, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
