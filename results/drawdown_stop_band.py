"""
drawdown_stop_band.py -- the sealed band writer of experiments/DRAWDOWN_STOP_PREREG.txt.

    ./venv/bin/python results/drawdown_stop_band.py --check   # sanity check only
    ./venv/bin/python results/drawdown_stop_band.py           # check, then write the band

WHAT IT DOES
    For each judged universe, 50 distinct 10-seed subsets are drawn from the 20
    stored seeds (results/seed_band_fit.py) with numpy generator seed 20261002, one
    generator for the whole run, so every universe uses the same 50 subsets. A
    subset's panel is the cached score panel with the score replaced by the mean of
    that subset's seed columns, taken as score_monthly takes a mean (axis 0 of a
    (10, rows) array, columns in ascending seed order). On each subset panel, v1,
    v3, v5 and v6 run at cadence 20 under research and tradeable, tax off and on,
    exactly as the engine runs them (the panel, prices, momentum, portfolio vol and
    cap are built as results/engine_v2_final.py builds them). For each comparison,
    v5 - v1 and v6 - v3, and each metric, d is the stop arm's metric minus the
    parent's, and the band is 2 x sqrt(2) x sd(d), ddof=1.

    Metrics are those of engine_core.metrics, unrounded: CAGR% and MaxDD% in
    percent, Sharpe and Calmar as ratios. MaxDD% is negative, so d > 0 means the
    stop arm's drawdown is shallower than its parent's.

SEALED
    This is the only code that may run v5 or v6 at the registered threshold before
    experiments/DRAWDOWN_STOP_BAND.csv is tracked: it calls
    arms.registry.open_seal_for_band_writer(), which refuses any other caller and
    refuses once the band file is tracked. Per-draw values, mean differences and
    stop-arm metrics stay in memory and are never written or printed. The only file
    written is the band file. Nothing temporary is written.

THE SANITY CHECK, PUBLIC NUMBERS ONLY
    Before any stop arm runs, the production subset (seeds 0 to 9 in production
    order) must reproduce the cached score panel bit for bit, and v1 and v3 on it
    must reproduce the published v34_equity curves exactly and the published
    v34_comparison rows, under all four settings. If any differs, nothing is run.
"""
import os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import argparse
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

import config
import arms.registry as arm_reg
from config import read_table
from numerics import rolling_std
from seed_band_fit import UNIVERSES, SEEDS20, store_path, inputs, is_done

GEN_SEED = 20261002
N_SUBSETS = 10 + 40   # 50 distinct subsets of 10 seeds
SUBSET_SIZE = 10
REBAL = 20
VOL_WIN = 60
SETTINGS = (("research", False), ("research", True), ("tradeable", False), ("tradeable", True))
COMPARISONS = (("v5", "v1"), ("v6", "v3"))
METRICS = ("MaxDD%", "CAGR%", "Sharpe", "Calmar")
FACTOR = 2.0 * np.sqrt(2.0)


def subsets():
    """The 50 distinct subsets, each a sorted tuple of seed columns."""
    rng = np.random.default_rng(GEN_SEED)
    out = []
    while len(out) < N_SUBSETS:
        s = tuple(sorted(int(x) for x in rng.choice(len(SEEDS20), SUBSET_SIZE, replace=False)))
        if s not in out:
            out.append(s)
    return out


def setting_suffix(profile, tax):
    return ("_tradeable" if profile == "tradeable" else "") + ("_tax" if tax else "")


def raw_metrics(eq):
    """engine_core.metrics' CAGR%, MaxDD%, Sharpe and Calmar, unrounded."""
    r = eq.pct_change().dropna()
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0
    dd = ((eq - eq.cummax()) / eq.cummax()).min()
    return {"CAGR%": cagr * 100, "MaxDD%": dd * 100, "Sharpe": sh,
            "Calmar": cagr / abs(dd) if dd else 0.0}


class Universe:
    """One universe's fixed inputs: the panel without its score, and the seed store."""

    def __init__(self, tag):
        import engine_core as ec
        import profiles
        from engine_core import precompute
        from universes.registry import REGISTRY
        self.u = u = REGISTRY[tag]
        self.tag = tag
        if not is_done(u, inputs(u)):
            raise SystemExit(f"{tag}: the seed store is absent, stale or unchecked; run "
                             f"results/seed_band_fit.py first")
        ec.set_tradeability(u)
        p = read_table(config.require_cache(u.score_cache, what=tag), parse_dates=["date"])
        self.p = p.sort_values(["date", "symbol"]).reset_index(drop=True)
        self.S = np.load(store_path(u))
        if len(self.S) != len(self.p):
            raise SystemExit(f"{tag}: store rows {len(self.S)} != panel rows {len(self.p)}")
        self.px = self.p.pivot_table(index="date", columns="symbol", values="close").ffill()
        self.op = self.p.pivot_table(index="date", columns="symbol", values="open").ffill()
        self.bd = self.px.index[(self.px.index >= config.BT_START_DATE)
                                & (self.px.index <= config.BT_END_DATE)]
        self.pc = precompute(self.px)
        self.mom20 = self.px / self.px.shift(20) - 1
        idx = (1 + self.px.pct_change().mean(axis=1).fillna(0)).cumprod()
        self.port_vol = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
        self.tv = self.port_vol.loc[self.bd].median()
        self.capkw = {}
        for prof in ("research", "tradeable"):
            profiles.set_selection(prof)
            try:
                self.capkw[prof] = profiles.cap_kwargs(u)
            finally:
                profiles.set_selection(None)

    def score_panel(self, cols):
        """The score pivot for the mean of these seed columns, as score_monthly averages."""
        score = np.mean(np.ascontiguousarray(self.S[:, list(cols)].T), axis=0)
        q = self.p[["date", "symbol"]].copy()
        q["score"] = score
        return q.pivot_table(index="date", columns="symbol", values="score"), score

    def run(self, sc, arm, profile, tax):
        from test_exposure import backtest_exposure
        a = arm_reg.ALL_ARMS[arm]
        kw = {"mode": a.mode, "sizing": a.sizing,
              "drawdown_stop": a.stop if a.stop is not None else None}
        eq, *_ = backtest_exposure(self.px, self.op, sc, self.bd, self.pc, self.mom20,
                                   self.port_vol, target_vol=self.tv, rebal=REBAL,
                                   tax_enabled=tax, audit=None, **kw,
                                   **self.capkw[profile])
        return eq


def sanity(tag):
    """-> list of (setting, arm, check, ok) on public numbers only. v1 and v3 only."""
    U = Universe(tag)
    sc, score = U.score_panel(range(10))
    cached = U.p["score"].to_numpy(dtype=float)
    out = [("all", "panel", "production subset score equals the cached score panel",
            bool(np.array_equal(np.isnan(score), np.isnan(cached))
                 and np.array_equal(score[~np.isnan(cached)], cached[~np.isnan(cached)])))]
    from engine_core import metrics
    M = U.u.metrics_dir
    for profile, tax in SETTINGS:
        sfx = setting_suffix(profile, tax)
        peq = read_table(M / f"v34_equity{sfx}.csv", parse_dates=["date"]).set_index("date")
        comp = read_table(M / f"v34_comparison{sfx}.csv").set_index("Config")
        for arm in ("v1", "v3"):
            a = arm_reg.ARMS[arm]
            eq = U.run(sc, arm, profile, tax)
            same_eq = bool(np.array_equal(eq.to_numpy(), peq[a.equity_column].to_numpy()))
            m = metrics(eq, a.label)
            pub = comp.loc[a.label]
            same_m = all(float(m[k]) == float(pub[k]) for k in ("CAGR%", "Sharpe", "Sortino",
                                                               "MaxDD%", "Calmar"))
            out.append((f"{profile}, tax {'on' if tax else 'off'}", arm,
                        f"equity curve equals v34_equity{sfx}.csv; metrics equal "
                        f"v34_comparison{sfx}.csv (CAGR {pub['CAGR%']}, Sharpe {pub['Sharpe']}, "
                        f"MaxDD {pub['MaxDD%']}, Calmar {pub['Calmar']})",
                        same_eq and same_m))
    return tag, out


def band_rows(tag):
    """The band for one universe. Every per-draw value stays inside this function."""
    arm_reg.open_seal_for_band_writer()
    U = Universe(tag)
    d = {(p, t, s, m): [] for p, t in SETTINGS for s, _ in COMPARISONS for m in METRICS}
    t0 = time.time()
    for cols in subsets():
        sc, _ = U.score_panel(cols)
        for profile, tax in SETTINGS:
            mets = {arm: raw_metrics(U.run(sc, arm, profile, tax))
                    for arm in ("v1", "v3", "v5", "v6")}
            for stop, parent in COMPARISONS:
                for m in METRICS:
                    d[(profile, tax, stop, m)].append(mets[stop][m] - mets[parent][m])
    rows = []
    for (profile, tax, stop, m), v in d.items():
        if len(v) != N_SUBSETS:
            raise SystemExit(f"{tag}: {len(v)} draws for {stop} {m}, expected {N_SUBSETS}")
        parent = dict(COMPARISONS)[stop]
        rows.append({"universe": tag, "profile": profile, "tax": "on" if tax else "off",
                     "comparison": f"{stop} - {parent}", "metric": m,
                     "band": FACTOR * float(np.std(v, ddof=1))})
    return rows, round((time.time() - t0) / 60, 1)


HEADER = [
    "# The noise band of experiments/DRAWDOWN_STOP_PREREG.txt, written by",
    "# results/drawdown_stop_band.py. band = 2 x sqrt(2) x sd(d), ddof=1, over 50 distinct",
    "# 10-of-20 seed subsets (generator seed 20261002), d = stop arm metric - parent metric,",
    "# cadence 20. CAGR% and MaxDD% are in percent points, Sharpe and Calmar are ratios.",
    "# MaxDD% is negative (a 30% drawdown is -30.0), so d > 0 means the stop arm's drawdown is",
    "# shallower than its parent's and d < 0 means deeper. The band is a width, always >= 0.",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="the sanity check only")
    a = ap.parse_args()
    from concurrent.futures import ProcessPoolExecutor
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=len(UNIVERSES)) as ex:
        checks = list(ex.map(sanity, UNIVERSES))
    bad = 0
    print("SANITY CHECK -- the production 10-seed subset, v1 and v3, public numbers only")
    for tag, out in checks:
        for setting, arm, what, ok in out:
            bad += not ok
            print(f"  {'OK  ' if ok else 'FAIL'} {tag:<12} {setting:<22} {arm:<5} {what}")
    print(f"  {sum(len(o) for _, o in checks) - bad} of {sum(len(o) for _, o in checks)} "
          f"checks pass ({(time.time() - t0) / 60:.1f} min)")
    if bad:
        print("NOTHING IS RUN: the production subset does not reproduce the published figures.")
        return 1
    if a.check:
        return 0
    if not arm_reg.stop_sealed():
        print(f"{arm_reg.BAND_FILE.relative_to(ROOT)} is already tracked; the band is not rewritten.")
        return 1
    t1 = time.time()
    with ProcessPoolExecutor(max_workers=len(UNIVERSES)) as ex:
        results = list(ex.map(band_rows, UNIVERSES))
    rows = [r for rs, _ in results for r in rs]
    for tag, (_, mins) in zip(UNIVERSES, results):
        print(f"  {tag:<12} {N_SUBSETS} subsets x {len(SETTINGS)} settings x 4 arms: {mins} min")
    df = pd.DataFrame(rows)
    text = "\n".join(HEADER) + "\n" + df.to_csv(index=False, float_format="%.6f")
    out = arm_reg.BAND_FILE
    tmp = out.with_name(f".{out.name}.tmp.{os.getpid()}")
    # naming: axis-free -- the one band file of the pre-registration; every axis is a column
    tmp.write_text(text)
    os.replace(tmp, out)
    print(f"wrote {out.relative_to(ROOT)}: {len(df)} rows ({(time.time() - t1) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
