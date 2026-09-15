"""
seed_noise_measure.py -- how much does the result move when ONLY the seeds change?

SPEC: experiments/SEED_NOISE_SPEC.txt, written before this file existed.

WHY: the purge measurement reported +0.54 and -0.81 on the shipping arm and
judged them against a 0.5-point noise floor that was INVENTED, not measured.
This measures the floor. If the purge deltas sit inside it, that measurement is
inconclusive at its design and this run says so.

DESIGN: 40 distinct seeds fitted ONCE, every seed's scores stored separately, and
sub-ensembles of any size K formed afterwards by averaging K stored columns. Same
fitting cost as four separate 10-seed runs, but it yields an EMPIRICAL sigma(K)
curve instead of an assumed 1/sqrt(K) scaling.

The first 10 seeds are the production set, so the shipped result is reproducible
from the store and acts as an identity gate.

EVERYTHING EXCEPT THE SEEDS IS HELD FIXED, including the CURRENT production purge
-- deliberately, so the recorded production numbers are one draw from the
distribution being measured rather than an outside reference point.

PERSISTENCE: the per-seed score matrix is written the instant the fitting loop
ends, before any reshape. The 2026-09-02 failure that discarded 25 minutes of
refits is not repeated.
"""
import sys
import os
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import config, config_mid, config_n100
from engine_core import FEATS_V2, _fit_seed, PURGE, precompute, metrics
import test_exposure
from test_exposure import backtest_exposure
from universes.registry import REGISTRY
from v34_common import ann_vol_pct
import profiles as _prof            # the run's execution-realism profile

PROD_SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]
EXTRA_SEEDS = [1000 + i for i in range(30)]
SEEDS = PROD_SEEDS + EXTRA_SEEDS              # 40 total, production first
K_GRID = [1, 2, 3, 5, 10, 20, 40]
M_SUBSETS = 50
VOL_WIN = 60
ARMS = [("v1", "invvol", "none"), ("v2", "invvol", "breadth")]
REQUIRED_RAW = ["date", "symbol", "open", "close", "y_rank", "scorable"]

# THE RAW PANEL PATHS, THE METRICS DIRECTORY AND THE SYMBOL LIST come from
# universes/registry.py -- the single definition. The LABEL stays local: it is
# printed into diagnostics/seed_noise.txt, and this file uses the
# "NIFTY 100"/"MIDCAP150" spelling rather than the registry's descriptive one.
#
# THE SET OF UNIVERSES IS THE REGISTRY, not a literal pair. It used to be
# `(REGISTRY["n100"], REGISTRY["mid"])`, which would have raised KeyError the day
# either tag changed and would silently have measured the wrong two if a third
# universe were added. A universe with no LABELS entry is refused by name rather
# than dropped from the measurement.
LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}

_unlabelled = set(REGISTRY) - set(LABELS)
if _unlabelled:
    raise SystemExit(
        f"seed_noise_measure: no report label for universe(s) {sorted(_unlabelled)}. "
        f"Add one to LABELS -- the spelling is what goes into "
        f"diagnostics/seed_noise.txt, so it is written down rather than derived.")

UNIVERSES = {
    u.tag: {"raw": u.raw_cache, "raw_tmp": str(u.raw_tmp),
            "md": u.metrics_dir, "syms": u.symbols, "label": LABELS[u.tag]}
    for u in REGISTRY.values()
}


def assert_columns(df, required, what):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"{what}: required columns absent: {missing}\n"
                         f"  present: {list(df.columns)}")


def fit_all_seeds(p, uni):
    """Fit every seed for every month, storing EACH seed's scores separately."""
    store = ROOT / "results" / f"SEEDNOISE_{uni}_scores.npy"
    if store.exists():
        print(f"      recovering per-seed store {store.name}", flush=True)
        return np.load(store)
    S = np.full((len(p), len(SEEDS)), np.nan, dtype=np.float32)
    months = sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique())
    t0 = time.time()
    for k, ym in enumerate(months):
        first = p.loc[p.ym == ym, "date"].min()
        cut = first - pd.Timedelta(days=PURGE)      # CURRENT production purge
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        te = (p["ym"] == ym) & p["scorable"]
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        Xtr = p.loc[tr, FEATS_V2].to_numpy()
        ytr = p.loc[tr, "y_rank"].to_numpy()
        Xte = p.loc[te, FEATS_V2].to_numpy()
        pr = Parallel(n_jobs=min(10, os.cpu_count() or 1),
                      backend="loky")(delayed(_fit_seed)(sd, Xtr, ytr, Xte)
                                      for sd in SEEDS)
        S[np.flatnonzero(te.to_numpy()), :] = np.asarray(pr, dtype=np.float32).T
        if k % 20 == 0:
            el = (time.time() - t0) / 60
            print(f"      [{uni}] month {k+1}/{len(months)} {ym} "
                  f"train {tr.sum():,}  elapsed {el:.1f} min", flush=True)
    # PERSIST FIRST. Nothing between the loop and this line.
    np.save(store, S)
    print(f"      [{uni}] fitting complete, persisted {store.name}", flush=True)
    return S


def make_backtester(p):
    """Pivot the price panel once; return a function that backtests a score vector."""
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = pv.loc[bd].median()
    di = {d: i for i, d in enumerate(px.index)}
    si = {s: i for i, s in enumerate(px.columns)}
    ri = p["date"].map(di).to_numpy()
    ci = p["symbol"].map(si).to_numpy()
    shape = (len(px.index), len(px.columns))

    def run(score_vec, sizing, mode):
        M = np.full(shape, np.nan, dtype=np.float64)
        M[ri, ci] = score_vec
        sc = pd.DataFrame(M, index=px.index, columns=px.columns)
        test_exposure.TOP_N, test_exposure.BUFFER = config.TOP_N, config.BUFFER
        # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
        # apply a participation cap even if one were selected; research_only()
        # makes that a statement rather than an accident, and STOPS the run if
        # --profile ever reaches here. See profiles.research_only.
        eq, tc, n, expo = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                            mode=mode, target_vol=tv, sizing=sizing, participation_cap=_prof.research_only(__name__))
        m = metrics(eq, "a", tc, n)
        yearly = {int(y): round(float((g.iloc[-1] / g.iloc[0] - 1) * 100), 2)
                  for y, g in eq.groupby(eq.index.year) if len(g) > 2}
        return {"CAGR%": float(m["CAGR%"]), "Sharpe": float(m["Sharpe"]),
                "MaxDD%": float(m["MaxDD%"]), "Trades": int(n),
                "AnnVol%": ann_vol_pct(eq), "yearly": yearly}
    return run


def run_universe(uni, cfg, W):
    # SAME GUARDS AS THE RUN THAT PRODUCED THE ARTEFACT THIS COMPARES
    # AGAINST. A script that recomputes and then checks itself against a
    # published row must run under the production guards, or it measures a
    # different engine. rebal_cadence_sweep.py failed exactly this way:
    # mid v3 AnnVol% recomputed 24.89 against 24.88 published.
    import engine_core as _ec
    from universes.registry import REGISTRY as _REG
    _ec.set_tradeability(_REG[uni])
    raw = pd.read_csv(config.require_cache(cfg["raw"], cfg["raw_tmp"],
                                           what=f"{uni} raw panel"),
                      parse_dates=["date"])
    assert_columns(raw, REQUIRED_RAW, f"{uni} raw panel")
    if set(raw["symbol"].unique()) != cfg["syms"]():
        raise SystemExit(f"{uni}: raw panel universe mismatch")
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True)
    p["ym"] = p["date"].dt.to_period("M")

    print(f"  [{uni}] fitting {len(SEEDS)} seeds...", flush=True)
    S = fit_all_seeds(p, uni)
    bt = make_backtester(p)

    W("=" * 100)
    W(f" SEED NOISE FLOOR -- {cfg['label']} ({uni})")
    W("=" * 100)
    W("")
    W(f"  seeds fitted {len(SEEDS)}  (first 10 = production set, rest new)")
    W(f"  purge: CURRENT production, {PURGE} calendar days -- deliberately not the")
    W("         corrected one, so the shipped result is one draw of this distribution")
    W(f"  sub-ensembles: K in {K_GRID}, {M_SUBSETS} random subsets per K (K=40 has one)")
    W("")

    # ---- identity gate: production seeds must reproduce the recorded figures --
    prod = bt(np.nanmean(S[:, :10], axis=1), "invvol", "breadth")
    v34 = pd.read_csv(Path(cfg["md"]) / "v34_comparison.csv")
    r = v34[v34["Config"].astype(str).str.startswith("v2")].iloc[0]
    gate = all(abs(prod[k] - float(r[k])) < 0.005 for k in ("CAGR%", "Sharpe", "MaxDD%"))
    W(f"  IDENTITY GATE -- production 10 seeds vs v34_comparison.csv: "
      f"{'ok' if gate else 'MISMATCH'}")
    for k in ("CAGR%", "Sharpe", "MaxDD%"):
        W(f"    {k:<8} from store {prod[k]:>9.2f}   recorded {float(r[k]):>9.2f}")
    W("")
    if not gate:
        W("  NO SPREAD IS REPORTED. The store does not reproduce the shipped result.")
        return None

    rng = np.random.default_rng(20260902)
    rows, yearly_rows = [], []
    for K in K_GRID:
        subsets = ([list(range(len(SEEDS)))] if K == len(SEEDS)
                   else [sorted(rng.choice(len(SEEDS), K, replace=False))
                         for _ in range(M_SUBSETS)])
        for si_, idxs in enumerate(subsets):
            sv = np.nanmean(S[:, idxs], axis=1)
            for tag, sizing, mode in ARMS:
                m = bt(sv, sizing, mode)
                rows.append({"K": K, "subset": si_, "arm": tag,
                             "CAGR%": m["CAGR%"], "Sharpe": m["Sharpe"],
                             "MaxDD%": m["MaxDD%"], "Trades": m["Trades"]})
                if K == 10:
                    for y, v in m["yearly"].items():
                        yearly_rows.append({"subset": si_, "arm": tag,
                                            "year": y, "ret%": v})
        print(f"      [{uni}] K={K} done", flush=True)

    D = pd.DataFrame(rows)
    Y = pd.DataFrame(yearly_rows)
    D.to_csv(Path(cfg["md"]) / "seed_noise_headline.csv", index=False)
    Y.to_csv(Path(cfg["md"]) / "seed_noise_yearly.csv", index=False)

    # ---- 1. spread at K=10 ------------------------------------------------
    W("-" * 100)
    W(" 1. HEADLINE SPREAD AT K = 10 -- the ensemble size that ships")
    W("-" * 100)
    W(f" {'arm':<4}{'metric':<9}{'min':>9}{'p5':>9}{'median':>9}{'p95':>9}"
      f"{'max':>9}{'sd':>8}{'range':>9}")
    k10 = D[D["K"] == 10]
    for tag, _, _ in ARMS:
        for met in ("CAGR%", "Sharpe", "MaxDD%"):
            a = k10[k10["arm"] == tag][met].to_numpy()
            W(f" {tag:<4}{met:<9}{a.min():>9.2f}{np.percentile(a,5):>9.2f}"
              f"{np.median(a):>9.2f}{np.percentile(a,95):>9.2f}{a.max():>9.2f}"
              f"{a.std(ddof=1):>8.2f}{a.max()-a.min():>9.2f}")
    W("")

    # ---- 2. does the purge delta clear it? -------------------------------
    W("-" * 100)
    W(" 2. DOES THE PURGE RESULT CLEAR THE MEASURED FLOOR?")
    W("-" * 100)
    pf = Path(cfg["md"]) / "purge_fix_headline.csv"
    if pf.exists():
        H = pd.read_csv(pf)
        for tag, _, _ in ARMS:
            a = k10[k10["arm"] == tag]["CAGR%"].to_numpy()
            base = float(H[H["arm"] == tag]["CAGR_current"].iloc[0])
            d = float(H[H["arm"] == tag]["dCAGR"].iloc[0])
            devs = a - np.median(a)
            frac = float((np.abs(devs) >= abs(d)).mean())
            W(f"  {tag}: purge dCAGR {d:+.2f}   seed sd {a.std(ddof=1):.2f}   "
              f"seed range {a.max()-a.min():.2f}")
            W(f"      fraction of seed draws deviating from their own median by")
            W(f"      AT LEAST |{abs(d):.2f}|: {frac*100:.0f}%")
            W(f"      -> the purge delta is {'INSIDE' if frac > 0.05 else 'OUTSIDE'}"
              f" the seed-change spread")
    else:
        W("  purge_fix_headline.csv absent -- comparison not made.")
    W("")

    # ---- 3. year-level spread --------------------------------------------
    W("-" * 100)
    W(" 3. YEAR-LEVEL SPREAD ACROSS SEED SETS, at K = 10")
    W("-" * 100)
    W(f" {'arm':<4}{'year':<7}{'min':>9}{'median':>9}{'max':>9}{'range':>9}{'sd':>8}")
    for tag, _, _ in ARMS:
        for y in sorted(Y["year"].unique()):
            a = Y[(Y["arm"] == tag) & (Y["year"] == y)]["ret%"].to_numpy()
            if len(a) < 2:
                continue
            W(f" {tag:<4}{y:<7}{a.min():>9.2f}{np.median(a):>9.2f}{a.max():>9.2f}"
              f"{a.max()-a.min():>9.2f}{a.std(ddof=1):>8.2f}")
    W("")

    # ---- 4/5. sigma(K) and the seeds needed ------------------------------
    W("-" * 100)
    W(" 4. THE sigma(K) CURVE, and 5. SEEDS NEEDED FOR +/-0.5 POINT STABILITY")
    W("-" * 100)
    sig_rows = []
    for tag, _, _ in ARMS:
        W(f"  {tag}")
        W(f"    {'K':>4}{'sd(CAGR)':>11}{'range':>10}   note")
        for K in K_GRID:
            a = D[(D["K"] == K) & (D["arm"] == tag)]["CAGR%"].to_numpy()
            sd = a.std(ddof=1) if len(a) > 1 else float("nan")
            note = ("single subset, no spread" if K == len(SEEDS)
                    else "subsets overlap, sd biased DOWN" if K >= 20 else "")
            sig_rows.append({"arm": tag, "K": K, "sd": sd,
                             "range": (a.max() - a.min()) if len(a) > 1 else float("nan")})
            W(f"    {K:>4}{sd:>11.3f}{(a.max()-a.min()) if len(a)>1 else float('nan'):>10.3f}   {note}")
        # fit sd = c * K^(-alpha) on the unbiased part of the curve
        sub = [r for r in sig_rows if r["arm"] == tag and r["K"] < 20 and r["sd"] == r["sd"]]
        lk = np.log([r["K"] for r in sub]); ls = np.log([r["sd"] for r in sub])
        alpha, logc = np.polyfit(lk, ls, 1)
        c = float(np.exp(logc))
        need = (c / 0.5) ** (-1.0 / alpha) if alpha < 0 else float("nan")
        met = [r["K"] for r in sig_rows if r["arm"] == tag and r["sd"] <= 0.5]
        W(f"    fitted sd(K) = {c:.3f} * K^({alpha:.3f})   "
          f"(fit on K < 20, where subsets barely overlap)")
        if met:
            W(f"    smallest TESTED K meeting sd <= 0.5: {min(met)}")
        else:
            W(f"    NO TESTED K meets sd <= 0.5.")
            W(f"    EXTRAPOLATED seeds needed for sd <= 0.5 points: {need:.0f}"
              f"   -- THIS IS AN EXTRAPOLATION, not a measurement")
        W("")
    pd.DataFrame(sig_rows).to_csv(Path(cfg["md"]) / "seed_noise_sigma_k.csv", index=False)
    return True


def main():
    t0 = time.time()
    out = []
    for uni, cfg in UNIVERSES.items():
        run_universe(uni, cfg, out.append)
        out.append("")
    el = time.time() - t0
    out.append(f"WALL CLOCK (in-script): {int(el//60)} min {int(el%60)} sec")
    (ROOT / "diagnostics" / "seed_noise.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    Path("/tmp/SEEDNOISE_DONE").write_text("ok\n")
    print("SENTINEL /tmp/SEEDNOISE_DONE written", flush=True)


if __name__ == "__main__":
    main()
