"""
atom_measure.py -- do the panel's repeated prices put point masses in the
features, and do the model's split thresholds sit on them?
=========================================================================

WHAT THIS ANSWERS, AND WHY IT WAS ASKED

    degeneracy_measure.py established on 2026-09-21 that the unperturbed price
    panel is degenerate -- 9,313 of 473,311 nifty100 rows and 17,224 of 572,399
    midcap150 rows carry a close EXACTLY equal to the previous row's, and a
    perturbation of 0.01% destroys almost all of them -- while neither path by
    which that could reach the result carries it:

        selection ties at the TOP_N cut        0 of 92 rebalances, both universes
        breadth's exact `m > 0` branch         0.00036 / 0.00041 of mean exposure
        the invvol guard `vs > 0.01`           0 of 736 top-8 slots

    One path was left untouched: the features and the model. A price repeated
    exactly puts an ATOM in the feature distribution -- a 20-day return of exactly
    0, a rolling std of exactly 0 -- and LightGBM is a piecewise-constant learner
    whose split thresholds are chosen from observed values. If a threshold
    separates an atom from its neighbouring value, every row in that atom sits on
    one side of a boundary that the smallest perturbation moves them across.

    THIS SCRIPT COUNTS ATOMS AND COUNTS THRESHOLDS. It does not establish that
    either causes the displacement. A high coincidence rate would say the model's
    decisions rest on values that noise disperses; it would still not measure how
    far the output moves as a result. The distinction is the same one
    price_noise_measure.py draws about spreads, and it is not blurred here.

PART A -- atom mass per feature

    For each of the 17 FEATS_V2 columns, per universe, on the unperturbed panel
    and on the sigma = 0.01% seed 101 panel that Part 4 of degeneracy_measure.py
    already used: the most common exact value and its share, the mass sitting in
    values that occur 100 or more times, the same at 1,000 or more, and how many
    distinct such values there are.

    An ATOM is a value occurring 100 or more times. The threshold is not chosen to
    flatter the count: it is min_child_samples, which is 100 in _fit_seed, so it is
    the smallest mass LightGBM will put in a leaf on its own. A value below that
    cannot hold a leaf and cannot be what a split is built around.

    A0 IS REPORTED FIRST BECAUSE THE ATOM COUNTS ARE READ WRONG WITHOUT IT.
    features_v2.cross_sectional_normalize z-scores every feature within each date,
    so an atom is a group of names sharing a raw value ON ONE DATE. Measured
    2026-09-21: fifteen of the seventeen features take a distinct value for ~98% of
    the names on a date and hold no atoms at all. vol_price_div takes a median of
    TWO, because it is np.sign(...) * np.sign(...) and has three possible raw
    values; trend_consistency_20 takes ten, being a mean of twenty booleans. Their
    point mass is a property of the feature definitions and would be there on a
    panel with no repeated prices in it.

PART B -- realised split thresholds against those atoms

    Every split actually realised by the fitted models is dumped through
    LightGBM's own trees_to_dataframe(), which reports the split feature, the
    threshold, and `count`, the number of training rows reaching that node.

    THE COINCIDENCE TEST, AND WHY THIS ONE.

        LightGBM does not split AT an observed value. It bins the feature and puts
        the threshold BETWEEN two adjacent values, so a test of `threshold == atom`
        is almost never true and would measure floating-point luck rather than
        model structure. It is reported anyway, as `exact`, precisely so the number
        it produces is visible rather than assumed.

        The test that matches the mechanism is ADJACENCY. A split `x <= t` sits on
        an atom when the atom is the greatest observed value at or below t, or the
        least observed value above t -- that is, when t is the boundary separating
        the atom from its immediate neighbour. That is exactly the configuration in
        which dispersing the atom moves its rows across the split, which is the
        thing being asked about. `neighbour` is that count.

    Both are reported. The decision rule was fixed on the row-weighted `neighbour`
    fraction before any of these numbers existed.

COST, AND THE ONE HARNESS SETTING THAT IS NOT PRODUCTION

    Part B needs the fitted boosters, and score_monthly's fast path fits the ten
    seeds in ten loky subprocesses whose models are discarded when they exit. This
    script sets engine_core.PARALLEL_SEEDS = False, which is the sequential path
    the same module documents as producing IDENTICAL scores -- "ensemble scores
    identical in both comparisons: max|diff| 0.000e+00", re-measured 2026-08-23 --
    at about four times the cost. Nothing about the fit changes: same seeds, same
    hyper-parameters, same training sets, same order.

    One scoring pass per universe, about 50 minutes each. No published cell is
    re-run and nothing published is written.

USAGE

    ./venv/bin/python results/atom_measure.py --part a
    ./venv/bin/python results/atom_measure.py --part b

    Part A writes diagnostics/atoms.txt and the atom sets Part B reads. Part B
    appends its own section to the same report.
"""
import argparse
import heapq
import json
import pathlib
import sys

import numpy as np
import pandas as pd

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "results"))

import config                                     # noqa: E402
import engine_core as _ec                         # noqa: E402
from engine_core import build_panel, HORIZON       # noqa: E402
from features_v2 import FEATS_V2                  # noqa: E402
from universes.registry import get as ureg_get    # noqa: E402

UNIVERSES = ("nifty100", "midcap150")
SIGMA, NOISE_SEED = 0.0001, 101

# THE PRODUCTION ENSEMBLE, NOT A CHOICE MADE HERE. Same ten seeds
# build_scores_step.py uses. It is restated rather than imported for the reason
# price_noise_measure.py restates it -- diagnostics/PIPELINE_AUDIT.txt records
# that this list already has four copies and no single owner. If that list moves,
# this one must move with it.
SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]

# min_child_samples in engine_core._fit_seed. A value carried by fewer rows than
# this cannot hold a leaf on its own, so it is not something a split is built
# around. The atom threshold is that number, not a number chosen here.
ATOM_MIN = 100
BIG_ATOM_MIN = 1000

WORK = pathlib.Path("/tmp/atom_measure")
ATOMS_JSON = WORK / "atoms.json"
REPORT = _ROOT / "diagnostics" / "atoms.txt"


def perturbed_farm(u, sigma, seed):
    """Rebuild price_noise_measure.py's perturbed farm, byte for byte.

    One numpy Generator per run, seeded by the noise seed, consumed in sorted
    filename order. Only adj_close is written. This is the same construction that
    file's `_perturb` uses and it must stay the same: degeneracy_measure.py checks
    it by asserting canonical_price's fallback counts against the recorded 170
    and 41.
    """
    src = pathlib.Path(u.prepare_data_dir())
    dst = WORK / f"{u.tag}_s{sigma}_n{seed}"
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    for f in sorted(src.glob("*.csv")):
        df = pd.read_csv(f)
        a = df["adj_close"].to_numpy(dtype=float)
        df["adj_close"] = a * (1.0 + rng.normal(0.0, sigma, size=len(df)))
        # naming: axis-free -- a scratch copy of the vendor's price farm under
        # /tmp, an input to one measurement and never an artefact, so it varies
        # over no published axis. Same classification as price_noise_measure.py's
        # own copy of this step.
        df.to_csv(dst / f.name, index=False)
    return dst


def atom_stats(s):
    """Point-mass statistics for one feature column."""
    s = s.dropna()
    n = len(s)
    if n == 0:
        return None
    vc = s.value_counts()
    atoms = vc[vc >= ATOM_MIN]
    big = vc[vc >= BIG_ATOM_MIN]
    return {
        "n_nonnull": int(n),
        "top_value": float(vc.index[0]),
        "top_count": int(vc.iloc[0]),
        "top_share": float(vc.iloc[0] / n),
        "atom_mass": int(atoms.sum()),
        "atom_share": float(atoms.sum() / n),
        "n_atoms": int(len(atoms)),
        "big_mass": int(big.sum()),
        "big_share": float(big.sum() / n),
        "n_big": int(len(big)),
        # the atom VALUES, for Part B. Capped so the file stays small; the cap is
        # far above the count any feature reaches here and is reported if hit.
        "atom_values": [float(v) for v in atoms.index[:5000]],
        "atom_values_truncated": bool(len(atoms) > 5000),
    }


def discreteness(out, tag, p):
    """How many distinct values does each feature take on a single date?

    THIS IS THE CONTROL THE ATOM COUNTS NEED, and without it they are read wrong.

    features_v2.cross_sectional_normalize z-scores every feature within each date
    and clips at 3 sigma, so an atom in the normalised panel is a group of names
    sharing a raw value ON ONE DATE, not a value repeated across the history. A
    feature that is CONTINUOUS gives one distinct value per name and no atoms. A
    feature that is DISCRETE BY CONSTRUCTION gives a handful of large groups every
    day, and it would do that on a panel with no repeated prices at all.

    vol_price_div is np.sign(...) * np.sign(...) -- three possible raw values. Its
    point mass is a property of the feature definition and has nothing to do with
    the degenerate panel this investigation started from.
    """
    n_sym = float(p.groupby("date")["symbol"].nunique().median())
    out(f"  {tag}: median {n_sym:.0f} names per date")
    out(f"    {'feature':<22}{'median distinct/date':>22}{'share of names':>18}")
    for f in FEATS_V2:
        d = p.groupby("date")[f].nunique()
        d = d[d > 0]
        if d.empty:
            continue
        out(f"    {f:<22}{d.median():>22.0f}{d.median()/n_sym:>17.1%}")
    out()


def part_a(out):
    WORK.mkdir(parents=True, exist_ok=True)
    store = {}
    out("  A0 -- distinct values per date, unperturbed. A feature near 100% is")
    out("        continuous; one far below it is discrete by construction.")
    out()
    for tag in UNIVERSES:
        discreteness(out, tag, build_panel(HORIZON, data_dir=ureg_get(tag).prepare_data_dir()))
    out("  A1 -- atom mass per feature")
    out()
    for tag in UNIVERSES:
        u = ureg_get(tag)
        panels = {"unperturbed": build_panel(HORIZON, data_dir=u.prepare_data_dir())}
        panels[f"sigma={SIGMA} seed={NOISE_SEED}"] = build_panel(
            HORIZON, data_dir=perturbed_farm(u, SIGMA, NOISE_SEED))
        for label, p in panels.items():
            out(f"  {tag}, {label}: {len(p):,} panel rows")
            out(f"    {'feature':<22}{'n':>10}{'top count':>12}{'top share':>11}"
                f"{'>=100 share':>13}{'atoms':>8}{'>=1000 share':>14}")
            for f in FEATS_V2:
                st = atom_stats(p[f])
                if st is None:
                    out(f"    {f:<22}{'all null':>10}")
                    continue
                out(f"    {f:<22}{st['n_nonnull']:>10,}{st['top_count']:>12,}"
                    f"{st['top_share']:>10.3%}{st['atom_share']:>13.3%}"
                    f"{st['n_atoms']:>8,}{st['big_share']:>14.3%}")
                if label == "unperturbed":
                    store.setdefault(tag, {})[f] = st
            out()
    # naming: axis-free -- the unperturbed atom sets, handed from Part A to Part B
    # under /tmp. It is an intermediate of one measurement and never an artefact,
    # so it varies over no published axis.
    ATOMS_JSON.write_text(json.dumps(store))
    out(f"  atom sets for Part B written to {ATOMS_JSON}")


def part_b(out):
    """Dump every realised split and test it against Part A's atoms.

    The models are the ones score_monthly fits: one per (month, seed), ten seeds,
    400 trees each. They are not stored -- there are about 1,260 of them per
    universe -- so the coincidence counts are accumulated as each model is fitted
    and the booster is dropped.
    """
    import lightgbm as lgb
    store = json.loads(ATOMS_JSON.read_text())

    for tag in UNIVERSES:
        u = ureg_get(tag)
        raw = build_panel(HORIZON, data_dir=u.prepare_data_dir())
        atoms = {f: np.array(sorted(store[tag][f]["atom_values"])) for f in FEATS_V2}
        # The observed distinct values, per feature, over the whole panel. The
        # adjacency test needs the neighbour of a threshold, not just the atoms.
        obs = {f: np.unique(raw[f].dropna().to_numpy(dtype=float)) for f in FEATS_V2}

        tot = {"splits": 0, "rows": 0, "exact": 0, "exact_rows": 0,
               "neigh": 0, "neigh_rows": 0}
        top = []

        def record(booster):
            """Accumulate, per model, and drop the booster.

            Vectorised per feature: there are about 38,000 splits in each of the
            ~1,260 models per universe, so a Python loop over them would dominate
            the scoring pass it is measuring. `top` is bounded by a heap for the
            same reason -- the hit list would otherwise run to millions of rows.
            """
            df = booster.trees_to_dataframe()
            df = df[df["split_feature"].notna()]
            if df.empty:
                return
            thr_all = df["threshold"].to_numpy(dtype=float)
            cnt_all = df["count"].to_numpy(dtype=np.int64)
            tot["splits"] += int(thr_all.size)
            tot["rows"] += int(cnt_all.sum())
            # score_monthly fits on numpy arrays, not DataFrames, so LightGBM has
            # no feature names and reports positional ones. The position IS the
            # FEATS_V2 index: _fit_seed is handed p.loc[tr, FEATS_V2].to_numpy(),
            # so column order is fixed by that list.
            feats = df["split_feature"].to_numpy()
            for fi, f in enumerate(FEATS_V2):
                sel = feats == f"Column_{fi}"
                if not sel.any():
                    continue
                thr, cnt = thr_all[sel], cnt_all[sel]
                av, o = atoms[f], obs[f]
                if av.size:
                    e = np.isin(thr, av)
                    tot["exact"] += int(e.sum())
                    tot["exact_rows"] += int(cnt[e].sum())
                if not o.size or not av.size:
                    continue
                # The adjacency test: is the observed value immediately below the
                # threshold, or immediately above it, an atom?
                j = np.searchsorted(o, thr, side="right")
                hit = np.zeros(thr.shape, dtype=bool)
                hitval = np.full(thr.shape, np.nan)
                has_lo = j > 0
                if has_lo.any():
                    lo = o[np.clip(j - 1, 0, o.size - 1)]
                    m = has_lo & np.isin(lo, av)
                    hit |= m
                    hitval[m] = lo[m]
                has_hi = j < o.size
                if has_hi.any():
                    hi = o[np.clip(j, 0, o.size - 1)]
                    m = has_hi & ~hit & np.isin(hi, av)
                    hit |= m
                    hitval[m] = hi[m]
                if hit.any():
                    tot["neigh"] += int(hit.sum())
                    tot["neigh_rows"] += int(cnt[hit].sum())
                    for c, t_, h_ in zip(cnt[hit], thr[hit], hitval[hit]):
                        item = (int(c), f, float(t_), float(h_))
                        if len(top) < 10:
                            heapq.heappush(top, item)
                        elif item[0] > top[0][0]:
                            heapq.heapreplace(top, item)

        _orig = _ec._fit_seed

        def _fit_and_record(sd, Xtr, ytr, Xte, n_jobs=1):
            import warnings as _w
            _w.filterwarnings("ignore", message=".*does not have valid feature names.*")
            m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, max_depth=6,
                                  num_leaves=48, subsample=0.8, colsample_bytree=0.8,
                                  min_child_samples=100, random_state=sd, verbose=-1,
                                  n_jobs=n_jobs)
            m.fit(Xtr, ytr)
            record(m.booster_)
            return m.predict(Xte)

        # The sequential path, which engine_core documents as bit-identical to the
        # parallel one. It is used because loky discards the boosters.
        _ec.PARALLEL_SEEDS = False
        _ec._fit_seed = _fit_and_record
        try:
            _ec.score_monthly(raw, SEEDS, purge_mode=u.purge_mode)
        finally:
            _ec._fit_seed = _orig
            _ec.PARALLEL_SEEDS = True

        s, r = tot["splits"], tot["rows"]
        out(f"  {tag}: {s:,} realised splits, {r:,} row-visits at those nodes")
        out(f"    threshold EXACTLY equal to an atom      : {tot['exact']:,} "
            f"({tot['exact']/s:.3%} of splits, {tot['exact_rows']/r:.3%} of rows)")
        out(f"    threshold ADJACENT to an atom           : {tot['neigh']:,} "
            f"({tot['neigh']/s:.3%} of splits, {tot['neigh_rows']/r:.3%} of rows)")
        out(f"    ROW-WEIGHTED ADJACENCY FRACTION         : {tot['neigh_rows']/r:.4%}")
        out("    ten highest-row-count splits sitting on an atom:")
        for cnt, f, thr, hit in sorted(top, reverse=True):
            out(f"      {cnt:>10,} rows  {f:<22} threshold {thr:>14.8g}  atom {hit:>14.8g}")
        out()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("a", "b"), required=True)
    a = ap.parse_args()

    lines = []

    def out(s=""):
        print(s, flush=True)
        lines.append(s)

    out("=" * 96)
    out(f"ATOMS IN THE FEATURES, AND THE SPLITS THAT SIT ON THEM -- PART {a.part.upper()}")
    out("=" * 96)
    out(f"atom = a value occurring {ATOM_MIN}+ times (min_child_samples in _fit_seed)")
    out(f"window {config.BT_START_DATE.date()} to {config.BT_END_DATE.date()}")
    out()
    (part_a if a.part == "a" else part_b)(out)
    out("=" * 96)

    REPORT.parent.mkdir(exist_ok=True)
    mode = "w" if a.part == "a" else "a"
    # naming: axis-free -- one count of the feature panel's point masses and of
    # the model structure sitting on them. It reports on the INPUT and the fitted
    # model, not on a strategy result, so it varies over no arm, cadence, profile
    # or tax selection; both universes are named inside the file.
    with open(REPORT, mode) as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"written {REPORT}")


if __name__ == "__main__":
    main()
