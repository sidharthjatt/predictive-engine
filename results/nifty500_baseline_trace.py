"""nifty500_baseline_trace.py -- where the sigma-0 run and each noise draw first hold
different names, and why. Read-only; writes diagnostics/nifty500_baseline_trace.txt.

    ./venv/bin/python results/nifty500_baseline_trace.py [--universe=nifty500]
        [--end=2019-12-31] [--seeds=101,202,...] [--loky=10] [--causal=101]
        [--run=runs/<research tax-on run folder>]

In experiments/CLEANED_NOISE_PREREG.txt nifty500's unperturbed run sits below all ten
of its draws on every arm. This rebuilds each draw's panel exactly as
results/noise_parallel.one_draw does (clean, perturb, build_panel(clean=False)),
scores it with the production ensemble only up to --end (every month to --end is
fitted exactly as a full run fits it; later months are not fitted), runs the four
arms, research profile, tax on, and compares the names held each day with the same
backtest on the unperturbed panel.

For each draw and arm it reports the first day the names differ, the decision behind
it, the names that differ, their ranks and scores on both sides, and three checks:
  ties      -- is either side's score of a swapped name exactly equal to another
               name's score (a tie broken by symbol order in the stable sort)?
  exempt    -- does a clean_exempt row fall in the swapped names' 252-session
               feature window?
  features  -- for every feature, the swapped names' change against sigma 0 on the
               decision day, in units of that feature's cross-sectional sd.
It also counts, over the whole panel, how each feature moves between sigma 0 and the
draw, and how many close-to-close returns are exactly zero at sigma 0: a zero return
is not "up" in trend_consistency_20 = mean(r > 0), and every draw gives it a sign.

--causal=SEED rescoring: the sigma-0 panel with one feature, trend_consistency_20,
taken from that draw, everything else unperturbed; scored to --end. If the arms'
first divergence moves to the draw's, that feature carries it.
"""
import os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["PYTHONHASHSEED"] = "0"
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import numpy as np
import pandas as pd

import noise_parallel as NP
from paths import list_dir
from config import read_table  # the one CSV/parquet reader: config.read_table

OUT = ROOT / "diagnostics" / "nifty500_baseline_trace.txt"
WORK = Path("/tmp/nifty500_baseline_trace")


def args(argv):
    a = dict(universe="nifty500", end="2019-12-31", seeds=",".join(map(str, NP.NOISE_SEEDS)),
             loky="10", causal="", run="runs/20260927T122131_all_all_r20")
    for x in argv:
        k, _, v = x.lstrip("-").partition("=")
        a[k] = v
    return a


def panel(tag, sigma, seed, work):
    """-> raw feature panel of the farm cleaned then perturbed, as one_draw builds it."""
    from engine_core import build_panel, HORIZON
    from universes.registry import REGISTRY
    u = REGISTRY[tag]
    src = u.prepare_data_dir()
    wd = work / NP.draw_name(tag, seed)
    shutil.rmtree(wd, ignore_errors=True)
    try:
        NP.perturb_cleaned_farm(src, wd / "farm", sigma, seed)
        exempt = {}
        for f in list_dir(wd / "farm", "*.csv"):
            d = read_table(f, usecols=["date", "clean_exempt"])
            d = d[d["clean_exempt"]]
            if len(d):
                exempt[f.stem] = set(pd.to_datetime(d["date"], dayfirst=True))
        raw = build_panel(HORIZON, data_dir=wd / "farm", clean=False)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return raw, exempt


# naming: delegated -- `cache` is built by main() under WORK and names universe, seed and end
def score(raw, tag, end, cache=None):
    """Scores to `end`; read from `cache` (a parquet path under WORK) when it exists,
    so a failure after the fit does not cost the fit again."""
    if cache is not None and Path(cache).exists():
        return pd.read_parquet(cache)
    s = _score(raw, tag, end)
    if cache is not None:
        s.to_parquet(cache)
    return s


def _score(raw, tag, end):
    from engine_core import score_monthly
    from features_v2 import FEATS_V2
    from price_noise_measure import SEEDS
    from universes.registry import REGISTRY
    keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
    r = raw.loc[raw["date"] <= pd.Timestamp(end), keep]
    return score_monthly(r, SEEDS, purge_mode=REGISTRY[tag].purge_mode)


def backtests(raw, scored, tag, end):
    """-> {arm: (names held per day to end, decisions, ranking)}. Prices from the full
    panel, scores only to end."""
    import config
    import engine_core as ec
    import arms.registry as arm_reg
    from engine_core import precompute
    from numerics import rolling_std
    from test_exposure import backtest_exposure
    from universes.registry import REGISTRY
    ec.set_tradeability(REGISTRY[tag])
    px = raw.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = raw.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = scored.pivot_table(index="date", columns="symbol", values="score").reindex(px.index)
    sc = sc.reindex(columns=px.columns)
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = rolling_std(idx.pct_change(), NP.VOL_WIN) * np.sqrt(252)
    tv = pv.loc[bd].median()
    out = {}
    for name, arm in arm_reg.ARMS.items():
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        backtest_exposure(px, op, sc, bd, pc, mom20, pv, target_vol=tv, audit=audit,
                          rebal=NP.REBAL, tax_enabled=True, participation_cap=None, **arm.kwargs)
        h = pd.DataFrame(audit["holdings"])
        h = h[h["date"] <= pd.Timestamp(end)]
        names = h.groupby("date")["symbol"].apply(frozenset)
        dec = [d["decided_on"] for d in audit["decisions"] if d["decided_on"] <= pd.Timestamp(end)]
        rk = pd.DataFrame(audit["ranking"])
        out[name] = (names, dec, rk)
    return out


def first_divergence(a, b):
    """First date the held names differ, and the names on each side."""
    na, nb = a[0], b[0]
    for d in na.index.union(nb.index):
        x, y = na.get(d, frozenset()), nb.get(d, frozenset())
        if x != y:
            return d, sorted(x - y), sorted(y - x)
    return None, [], []


def feature_delta(raw0, rawd, date, syms):
    from features_v2 import FEATS_V2
    a = raw0[raw0["date"] == date].set_index("symbol")
    b = rawd[rawd["date"] == date].set_index("symbol")
    out = {}
    for f in FEATS_V2:
        sd = a[f].std()
        out[f] = {s: (float(b.at[s, f] - a.at[s, f]) / sd if sd and s in a.index and s in b.index
                      else np.nan) for s in syms}
    return out


# naming: axis-free -- one diagnosis of named draws, research profile, tax on, cadence 20
def main(argv):
    a = args(argv)
    tag, end, loky = a["universe"], a["end"], int(a["loky"])
    # THE PUBLISHED RUN THE SIGMA-0 RECONSTRUCTION IS CHECKED AGAINST, checked
    # before any panel is built rather than after an hour of fitting.
    run_dir = ROOT / a["run"]
    if not (run_dir / f"results_{tag}" / "metrics").is_dir():
        raise SystemExit(f"nifty500_baseline_trace: run folder {run_dir} has no results_{tag}/metrics.\n"
                         f"  Pass the research tax-on run to check against: --run=runs/<folder>")
    seeds = [int(s) for s in a["seeds"].split(",") if s]
    import engine_core as ec
    from features_v2 import FEATS_V2
    NP._loky_pool(ec, loky)
    WORK.mkdir(parents=True, exist_ok=True)
    L = [f"nifty500 baseline trace -- ./venv/bin/python results/nifty500_baseline_trace.py "
         + " ".join(argv), f"universe {tag}; scores fitted to {end}; research profile, tax on, cadence 20", ""]
    t0 = time.time()
    raw0, ex0 = panel(tag, 0.0, 0, WORK)
    r = raw0.sort_values(["symbol", "date"])
    ret = r.groupby("symbol")["close"].pct_change()
    win = (r["date"] >= pd.Timestamp("2019-01-01")) & ret.notna()
    L.append(f"sigma 0: {int((ret[win] == 0).sum()):,} of {int(win.sum()):,} close-to-close returns "
             f"in the window are exactly zero ({(ret[win] == 0).mean() * 100:.2f}%); "
             f"clean_exempt rows {sum(len(v) for v in ex0.values()):,} in {len(ex0)} files")
    s0 = score(raw0, tag, end, WORK / f"scores_{tag}_s0_{end}.parquet")
    bt0 = backtests(raw0, s0, tag, end)
    L.append(f"sigma 0 panel and scores: {(time.time() - t0) / 60:.1f} min")
    # The reconstruction must reproduce the published run's names to --end.
    run = run_dir / f"results_{tag}" / "metrics"
    for arm in bt0:
        t = f"{tag}_tax" if arm == "v2" else f"{tag}_{arm}_tax"
        ph = read_table(run / f"daily_holdings_{t}.csv", parse_dates=["date"])
        ph = ph[ph["date"] <= pd.Timestamp(end)].groupby("date")["symbol"].apply(frozenset)
        same = all(ph.get(d, frozenset()) == bt0[arm][0].get(d, frozenset())
                   for d in ph.index.union(bt0[arm][0].index))
        L.append(f"  sigma-0 reconstruction, {arm}: names equal the published run's on every day "
                 f"to {end}: {same}")
        if not same:
            raise SystemExit("\n".join(L) + "\nthe sigma-0 reconstruction does not reproduce the run")
    L.append("")
    rows = []
    causal_seed = int(a["causal"]) if a["causal"] else None
    for seed in seeds:
        t1 = time.time()
        rawd, exd = panel(tag, NP.SIGMA, seed, WORK)
        m = raw0[["date", "symbol"] + FEATS_V2].merge(rawd[["date", "symbol"] + FEATS_V2],
                                                       on=["date", "symbol"], suffixes=("_0", "_d"))
        m = m[m["date"] >= pd.Timestamp("2019-01-01")]
        L.append(f"seed {seed}: feature change against sigma 0 over the window "
                 "(mean change / cross-sectional sd, share of rows changed by more than 0.01 sd)")
        parts = []
        for f in FEATS_V2:
            sd = m[f + "_0"].std()
            dlt = (m[f + "_d"] - m[f + "_0"]) / sd
            parts.append(f"{f} {dlt.mean():+.4f} {(dlt.abs() > 0.01).mean() * 100:.1f}%")
        for i in range(0, len(parts), 4):
            L.append("    " + "; ".join(parts[i:i + 4]))
        # The panel's features are cross-sectionally z-scored, so a change to a few
        # names moves every name's value a little. The raw quantity behind
        # trend_consistency_20 is the sign of each close-to-close return.
        rd = rawd.sort_values(["symbol", "date"])
        retd = rd.groupby("symbol")["close"].pct_change()
        j = pd.DataFrame({"date": r["date"].to_numpy(), "symbol": r["symbol"].to_numpy(),
                          "r0": ret.to_numpy()}).merge(
            pd.DataFrame({"date": rd["date"].to_numpy(), "symbol": rd["symbol"].to_numpy(),
                          "rd": retd.to_numpy()}), on=["date", "symbol"])
        j = j[(j["date"] >= pd.Timestamp("2019-01-01")) & j["r0"].notna() & j["rd"].notna()]
        flip = (j["r0"] > 0) != (j["rd"] > 0)
        up0 = (j["r0"] > 0).astype(float).groupby(j["symbol"]).transform(lambda x: x.rolling(20).mean())
        upd = (j["rd"] > 0).astype(float).groupby(j["symbol"]).transform(lambda x: x.rolling(20).mean())
        L.append(f"    up-day sign of the return differs from sigma 0 on {int(flip.sum()):,} of {len(j):,} "
                 f"returns ({flip.mean() * 100:.2f}%); {int((flip & (j['r0'] == 0)).sum()):,} of them are exactly "
                 f"zero at sigma 0. Raw 20-day up-day share differs on {((up0 - upd).abs() > 1e-12).mean() * 100:.1f}% "
                 f"of rows, mean change {(upd - up0).mean():+.5f}")
        sd = score(rawd, tag, end, WORK / f"scores_{tag}_s{seed}_{end}.parquet")
        btd = backtests(rawd, sd, tag, end)
        for arm in bt0:
            d, only0, onlyd = first_divergence(bt0[arm], btd[arm])
            if d is None:
                L.append(f"  {arm}: same names on every day to {end}")
                rows.append(dict(seed=seed, arm=arm, first_day=None))
                continue
            dec = max(x for x in bt0[arm][1] if x < d)
            k0 = bt0[arm][2][bt0[arm][2]["decided_on"] == dec].set_index("symbol")
            kd = btd[arm][2][btd[arm][2]["decided_on"] == dec].set_index("symbol")
            sc0 = s0[s0["date"] == dec].set_index("symbol")["score"]
            scd = sd[sd["date"] == dec].set_index("symbol")["score"]
            sw = only0 + onlyd
            tie0 = any((sc0 == sc0.get(s)).sum() > 1 for s in sw if s in sc0)
            tied = any((scd == scd.get(s)).sum() > 1 for s in sw if s in scd)
            lo = dec - pd.Timedelta(days=380)
            exe = [s for s in sw if any(lo <= x <= dec for x in ex0.get(s, ()))]
            fd = feature_delta(raw0, rawd, dec, sw)
            top = sorted(FEATS_V2, key=lambda f: -np.nan_to_num(
                np.nanmax(np.abs(np.array(list(fd[f].values()), dtype=float)), initial=0.0)))[:3]
            rk0 = {s: (int(k0.at[s, "rank"]) if s in k0.index else None) for s in sw}
            rkd = {s: (int(kd.at[s, "rank"]) if s in kd.index else None) for s in sw}
            L.append(f"  {arm}: first differs {d.date()} (decided {dec.date()}); sigma 0 only {only0}, "
                     f"draw only {onlyd}")
            L.append(f"      ranks sigma 0 {rk0}  draw {rkd}")
            L.append(f"      scores sigma 0 " + ", ".join(f"{s} {sc0.get(s, np.nan):.6f}" for s in sw)
                     + "  draw " + ", ".join(f"{s} {scd.get(s, np.nan):.6f}" for s in sw))
            L.append(f"      exact score tie: sigma 0 {tie0}, draw {tied}; clean_exempt row in the "
                     f"swapped names' last 380 days: {exe or 'none'}")
            L.append("      largest feature moves (sd): " + "; ".join(
                f"{f} " + ",".join(f"{s} {v:+.3f}" for s, v in fd[f].items()) for f in top))
            rows.append(dict(seed=seed, arm=arm, first_day=str(d.date()), decided=str(dec.date()),
                             sigma0_only=" ".join(only0), draw_only=" ".join(onlyd),
                             score_tie_sigma0=tie0, score_tie_draw=tied, exempt_in_window=" ".join(exe),
                             top_features=" ".join(top)))
        if seed == causal_seed:
            mix = raw0.copy()
            k = rawd.set_index(["date", "symbol"])["trend_consistency_20"]
            mix["trend_consistency_20"] = k.reindex(pd.MultiIndex.from_frame(mix[["date", "symbol"]])).to_numpy()
            sm = score(mix, tag, end, WORK / f"scores_{tag}_mix{seed}_{end}.parquet")
            btm = backtests(raw0, sm, tag, end)
            L.append(f"  causal test, seed {seed}: sigma-0 panel with the draw's trend_consistency_20 only")
            for arm in bt0:
                dm, o0, om = first_divergence(bt0[arm], btm[arm])
                dd, _, _ = first_divergence(bt0[arm], btd[arm])
                L.append(f"    {arm}: first differs from sigma 0 {dm.date() if dm is not None else 'never'}"
                         f" (draw: {dd.date() if dd is not None else 'never'}); sigma 0 only {o0}, mixed only {om}")
        L.append(f"  seed {seed}: {(time.time() - t1) / 60:.1f} min")
        L.append("")
        OUT.write_text("\n".join(L) + "\n")
        pd.DataFrame(rows).to_csv(OUT.with_suffix(".csv"), index=False)
        print("\n".join(L[-12:]), flush=True)
    OUT.write_text("\n".join(L) + "\n")
    pd.DataFrame(rows).to_csv(OUT.with_suffix(".csv"), index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
