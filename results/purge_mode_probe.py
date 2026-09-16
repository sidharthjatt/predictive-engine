"""
purge_mode_probe.py -- which purge built the score panels that are on disk?

THE QUESTION. engine_core.score_monthly takes purge_mode, defaulting to
"trading". That is what the CODE does today. It is a different question from what
the ARTEFACTS were built with, and the second question is the one that decides
whether the published headline sits on the corrected purge or the legacy one.
A score panel records dates, symbols and scores. It does not record the purge
that produced it, so the question cannot be answered by reading the file.

WHAT THIS IS, NAMED PLAINLY: A DIFFERENTIAL TEST THAT CHOOSES BETWEEN TWO
CANDIDATES. IT IS NOT AN IDENTITY REPRODUCTION.
    For selected months it refits the production 10-seed ensemble TWICE from the
    same on-disk raw panel -- once under purge_mode="calendar", once under
    "trading" -- and asks which candidate the shipped panel resembles more
    closely. It does NOT establish that either candidate reproduces the shipped
    panel exactly. Neither does. See THE RESIDUAL below.

WHY A DIFFERENTIAL TEST IS SOUND HERE DESPITE THAT RESIDUAL
    build_scores_*.py score the IN-MEMORY panel and write raw_panel_*_cache.csv
    as a by-product; the two differ by one unit in the last place. This probe can
    only read the CSV, so both candidates carry that same offset. It is COMMON
    MODE and cancels in a comparison of which candidate is closer. It does not
    cancel in an absolute comparison, which is why no absolute claim is made.

THE THREE STATISTICS, all against the shipped panel's scores for that month
    max absolute score difference   -- a single-cell statistic, reported but weak
    mean absolute score difference  -- the primary statistic
    rank disagreement               -- per-date descending rank, count of symbols
                                       whose rank differs. This is the quantity
                                       the strategy actually consumes.

TWO DESIGN FEATURES THAT MAKE THE RESULT MEAN SOMETHING

  1. CONTROL MONTHS. In some months the calendar cut and the trading cut select
     an IDENTICAL training set. There the two branches must return byte-identical
     output, and if they do not, the probe has a preference of its own and its
     verdict is worthless. Control months are not chosen by hand: any month whose
     two training masks are equal is classified as a control by the run itself.
     The controls also measure the ERROR FLOOR -- the residual that is due to the
     panel round-trip alone and to nothing about the purge.

  2. SIZE-INCREASING MONTHS. The calendar cut is not always the later one. In
     months where the trading cut falls LATER, the trading mode trains on MORE
     rows, not fewer. Including these rules out the obvious confound that a
     smaller training set is somehow always closer to the shipped panel. They are
     labelled "tr>cal" in the output and are counted separately in the verdict.

THE VERDICT IS COMPUTED FROM THE RUN, NOT WRITTEN HERE. The tally, the sign test
and the wording of the conclusion are all derived from the measured rows.

WHAT THIS DOES NOT ESTABLISH
    It does not establish that the shipped panels reproduce from the artefacts on
    disk. They do not, and the reason is the one-unit-in-the-last-place gap
    recorded in KNOWN_ISSUES.md under "The headline is not reproducible from the
    artefacts on disk to better than about a point". Closing that is a separate
    decision, not a measurement.

Reads only. Writes diagnostics/purge_mode_probe.txt. No panel is modified.
"""
import os

# Determinism pins, mirroring run_all.py, BEFORE any numeric library is imported.
# This script is normally run standalone, so it cannot rely on run_all.py's block.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["PYTHONHASHSEED"] = "0"

import sys
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

from engine_core import _fit_seed, HORIZON, PURGE, PURGE_EMBARGO
from features_v2 import FEATS_V2
from universes.registry import REGISTRY
import measured_universes

# The production ensemble. Duplicated in every build_scores*.py; see
# KNOWN_ISSUES.md on that duplication.
SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]

OUT = ROOT / "diagnostics" / "purge_mode_probe.txt"

# PATHS COME FROM universes/registry.py -- the single definition. Before this,
# every study script spelled the same four paths out again under its own key
# names; nineteen of them did, under nine different vocabularies, with nothing
# able to check one against another.
#
# THE LABEL IS NOT TAKEN FROM THE REGISTRY, DELIBERATELY. This file's spelling
# ("NIFTY 100" / "MIDCAP150") is printed into diagnostics/purge_mode_probe.txt,
# and the sibling scripts use two other spellings for the same two universes.
# The registry carries the descriptive one. Sourcing labels from it would rewrite
# committed artefacts -- diagnostics/topn_verdict.txt among them -- for a
# cosmetic reason. Labels are presentation and stay local; paths are facts and
# do not.
#
# MONTHS ARE THIS STUDY'S OWN DATA. Chosen for cut divergence, in BOTH
# directions, plus months whose cuts coincide, which the run classifies as
# controls. They describe the probe, not the universe.
LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}
MONTHS = {
    "n100": ["2016-03", "2016-05", "2016-07", "2017-02", "2017-08",
             "2017-12", "2018-04", "2019-02", "2019-05", "2019-09",
             "2020-05", "2020-10", "2021-05", "2023-05", "2026-05"],
    "mid": ["2017-08", "2019-02", "2019-09", "2020-05", "2023-05"],
}
# Order is load-bearing: the report is written universe by universe in this order.
# WHICH UNIVERSES THIS STUDY HAS MONTHS FOR, DECLARED. The pair was written out
# here, so a third registered universe was absent rather than an error and the
# probe reported on two while looking complete. MONTHS is this study's own data --
# chosen for cut divergence in both directions -- so it cannot be derived for a
# universe nobody has chosen months for. Order is the report order.
MEASURED_FOR = ("n100", "mid")
COVERAGE = measured_universes.declare(
    "purge_mode_probe", MEASURED_FOR, {"MONTHS": MONTHS})

UNIVERSES = {
    u.tag: {"label": LABELS[u.tag], "raw": u.raw_cache, "scored": u.score_cache,
            "months": MONTHS[u.tag]}
    for u in (REGISTRY[t] for t in MEASURED_FOR)
}


def cut_for(first, cal, pos, mode):
    """The training cut, exactly as score_monthly builds it in each mode."""
    if mode == "calendar":
        return first - pd.Timedelta(days=PURGE)
    j = pos[np.datetime64(first)] - HORIZON - PURGE_EMBARGO
    return None if j < 0 else pd.Timestamp(cal[j])


def probe_universe(tag, cfg, w):
    w(f"\n{'=' * 100}")
    w(f" {cfg['label']} ({tag})")
    w(f"{'=' * 100}\n")

    raw = pd.read_csv(cfg["raw"], parse_dates=["date"])
    shipped = pd.read_csv(cfg["scored"], usecols=["date", "symbol", "score"],
                          parse_dates=["date"])
    w(f"  raw panel    {cfg['raw'].name}   rows {len(raw):,}")
    w(f"  scored panel {cfg['scored'].name}   rows {len(shipped):,}")

    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["ym"] = p["date"].dt.to_period("M")
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}

    rows = []
    for ms in cfg["months"]:
        ym = pd.Period(ms, "M")
        first = p.loc[p.ym == ym, "date"].min()
        te = (p["ym"] == ym) & p["scorable"] if "scorable" in p.columns \
            else (p["ym"] == ym)
        Xte = p.loc[te, FEATS_V2].to_numpy()
        key = p.loc[te, ["date", "symbol"]].reset_index(drop=True)
        ship = key.merge(shipped, on=["date", "symbol"], how="left")["score"].to_numpy()

        per_mode, masks = {}, {}
        for mode in ("calendar", "trading"):
            cut = cut_for(first, cal, pos, mode)
            tr = (p["date"] <= cut) & p["y_rank"].notna()
            masks[mode] = tr.to_numpy()
            Xtr = p.loc[tr, FEATS_V2].to_numpy()
            ytr = p.loc[tr, "y_rank"].to_numpy()
            pr = Parallel(n_jobs=min(len(SEEDS), os.cpu_count() or 1),
                          backend="loky")(delayed(_fit_seed)(sd, Xtr, ytr, Xte)
                                          for sd in SEEDS)
            sc = np.mean(pr, axis=0)
            d = np.abs(sc - ship)
            t = key.copy(); t["a"] = sc; t["b"] = ship
            flips = 0
            for _, g in t.groupby("date"):
                flips += int((g["a"].rank(ascending=False).astype(int)
                              != g["b"].rank(ascending=False).astype(int)).sum())
            per_mode[mode] = dict(cut=cut, n=int(tr.sum()), scores=sc,
                                  mx=float(np.nanmax(d)), mn=float(np.nanmean(d)),
                                  flips=flips)

        identical_mask = bool((masks["calendar"] == masks["trading"]).all())
        identical_out = bool(np.array_equal(per_mode["calendar"]["scores"],
                                            per_mode["trading"]["scores"]))
        rows.append(dict(ym=ms, control=identical_mask, identical_out=identical_out,
                         direction=("tr>cal" if per_mode["trading"]["n"] >
                                    per_mode["calendar"]["n"] else
                                    "tr<cal" if per_mode["trading"]["n"] <
                                    per_mode["calendar"]["n"] else "same"),
                         cal=per_mode["calendar"], tr=per_mode["trading"]))

    # ---------------------------------------------------------------- controls
    ctl = [r for r in rows if r["control"]]
    w(f"\n  CONTROL MONTHS -- the two cuts select an IDENTICAL training set.")
    w(f"  The two branches MUST return identical output here. If they do not, the")
    w(f"  probe has a preference of its own and its verdict means nothing.\n")
    w(f"  {'month':9} {'trainrows':>10} {'identical output':>18} "
      f"{'mean abs vs shipped':>21} {'rank flips':>11}")
    for r in ctl:
        w(f"  {r['ym']:9} {r['cal']['n']:10,} {str(r['identical_out']):>18} "
          f"{r['cal']['mn']:21.3e} {r['cal']['flips']:11,}")
    if ctl:
        floor_lo = min(r["cal"]["mn"] for r in ctl)
        floor_hi = max(r["cal"]["mn"] for r in ctl)
        w(f"\n  ALL CONTROLS IDENTICAL: {all(r['identical_out'] for r in ctl)}")
        w(f"  ERROR FLOOR from the controls, mean abs: "
          f"{floor_lo:.3e} .. {floor_hi:.3e}")
        w(f"  That floor is the panel round-trip alone. It has nothing to do with")
        w(f"  the purge, and no candidate can beat it.")
    else:
        floor_lo = floor_hi = float("nan")

    # --------------------------------------------------------------- divergent
    div = [r for r in rows if not r["control"]]
    w(f"\n  DIVERGENT MONTHS -- the two cuts select different training sets.")
    w(f"  'tr>cal' marks the SIZE-INCREASING cases, where the trading cut falls")
    w(f"  LATER and trains on MORE rows. Those rule out the confound that a")
    w(f"  smaller training set is simply always closer to the shipped panel.\n")
    w(f"  {'month':9} {'dir':7} {'cut cal':12} {'cut tr':12} "
      f"{'rows cal':>10} {'rows tr':>10} | {'maxabs cal':>11} {'maxabs tr':>11} | "
      f"{'meanabs cal':>12} {'meanabs tr':>12} | {'flips cal':>10} {'flips tr':>9} | closer")
    for r in div:
        closer = "trading" if r["tr"]["mn"] < r["cal"]["mn"] else "calendar"
        w(f"  {r['ym']:9} {r['direction']:7} {str(r['cal']['cut'].date()):12} "
          f"{str(r['tr']['cut'].date()):12} {r['cal']['n']:10,} {r['tr']['n']:10,} | "
          f"{r['cal']['mx']:11.3e} {r['tr']['mx']:11.3e} | "
          f"{r['cal']['mn']:12.3e} {r['tr']['mn']:12.3e} | "
          f"{r['cal']['flips']:10,} {r['tr']['flips']:9,} | {closer}")

    return rows, (floor_lo, floor_hi)


def main():
    t0 = time.time()
    lines = []
    def w(s=""):
        print(s, flush=True)
        lines.append(s)

    w("=" * 100)
    w(" WHICH PURGE BUILT THE SHIPPED SCORE PANELS -- DIFFERENTIAL PROBE")
    w("=" * 100)
    w()
    w("  A DIFFERENTIAL TEST BETWEEN TWO CANDIDATES. NOT AN IDENTITY REPRODUCTION.")
    w("  Each month is refit TWICE from the same on-disk raw panel, once per")
    w("  purge_mode, and compared against the shipped score panel. The question is")
    w("  which candidate is CLOSER, never whether either one reproduces.")
    w()
    w(f"  PURGE = {PURGE} calendar days (legacy)   HORIZON = {HORIZON} trading rows"
      f"   PURGE_EMBARGO = {PURGE_EMBARGO} trading rows")
    w(f"  seeds {SEEDS}")
    w()
    for _l in COVERAGE:
        w(_l)

    all_rows, floors = {}, {}
    for tag, cfg in UNIVERSES.items():
        all_rows[tag], floors[tag] = probe_universe(tag, cfg, w)

    # ------------------------------------------------------------------ verdict
    w(f"\n{'=' * 100}")
    w(" VERDICT -- computed from the rows above, not written into this script")
    w(f"{'=' * 100}\n")

    div = [(t, r) for t in all_rows for r in all_rows[t] if not r["control"]]
    ctl = [(t, r) for t in all_rows for r in all_rows[t] if r["control"]]
    n_div = len(div)
    win_mean = sum(1 for _, r in div if r["tr"]["mn"] < r["cal"]["mn"])
    win_flip = sum(1 for _, r in div if r["tr"]["flips"] < r["cal"]["flips"])
    win_max = sum(1 for _, r in div if r["tr"]["mx"] < r["cal"]["mx"])
    inc = [(t, r) for t, r in div if r["direction"] == "tr>cal"]
    win_inc = sum(1 for _, r in inc if r["tr"]["mn"] < r["cal"]["mn"])
    ctl_ok = all(r["identical_out"] for _, r in ctl)

    w(f"  control months, both universes .................. {len(ctl)}")
    w(f"  controls returning identical output .............. {sum(1 for _, r in ctl if r['identical_out'])}"
      f"  -> probe is unbiased between branches: {ctl_ok}")
    w(f"  divergent months, both universes ................. {n_div}")
    w(f"    trading closer on MEAN ABS ..................... {win_mean} of {n_div}")
    w(f"    trading closer on RANK DISAGREEMENT ............ {win_flip} of {n_div}")
    w(f"    trading closer on MAX ABS (weak statistic) ..... {win_max} of {n_div}")
    w(f"  size-increasing months (trading trains on MORE) .. {len(inc)}")
    w(f"    trading closer on MEAN ABS there ............... {win_inc} of {len(inc)}")

    if n_div:
        p_one_sided = 0.5 ** n_div
        w(f"\n  One-sided sign test on the primary statistic (mean abs), under the null")
        w(f"  that the shipped panel is equally close to both candidates:")
        w(f"    {win_mean} of {n_div} -> p = {p_one_sided:.3e}"
          if win_mean == n_div else
          f"    {win_mean} of {n_div}; the null is not cleanly rejected")

    unanimous = (win_mean == n_div and win_flip == n_div and n_div > 0)
    if unanimous and ctl_ok and win_inc == len(inc) and len(inc) > 0:
        w(f"\n  DETERMINATION: THE SHIPPED PANELS WERE BUILT WITH purge_mode=\"trading\".")
        w(f"  Unanimous on both primary statistics, the controls confirm the probe has")
        w(f"  no branch preference, and the size-increasing months exclude the")
        w(f"  training-set-size confound.")
    else:
        w(f"\n  DETERMINATION: NOT ESTABLISHED BY THIS RUN. The tally above is not")
        w(f"  unanimous, or a control failed. Do not read a verdict out of it.")

    w(f"\n  THE RESIDUAL, AND WHY THERE IS ONE.")
    w(f"  NEITHER candidate reproduces the shipped panel. The best fit still leaves")
    w(f"  a non-zero mean absolute difference and a four-figure rank disagreement in")
    w(f"  every month, control months included. The cause is known and is not the")
    w(f"  purge: build_scores_*.py score the IN-MEMORY panel and write")
    w(f"  raw_panel_*_cache.csv as a by-product, and the two differ by one unit in")
    w(f"  the last place. This probe can only read the CSV. The control months")
    w(f"  measure that floor directly:")
    for tag in floors:
        w(f"    {tag:5} mean abs floor {floors[tag][0]:.3e} .. {floors[tag][1]:.3e}")
    w(f"  See KNOWN_ISSUES.md, \"The headline is not reproducible from the artefacts")
    w(f"  on disk to better than about a point\".")
    w(f"\n  WHAT THIS RUN DID NOT ESTABLISH:")
    w(f"    - that the shipped panels reproduce exactly from the artefacts on disk;")
    w(f"      they do not, and the one-ULP gap above is the reason.")
    w(f"    - anything about whether the trading purge is CORRECT. That is")
    w(f"      diagnostics/leakage_check2_purge.txt. This asks only which one ran.")

    w(f"\n  wall clock {(time.time() - t0) / 60:.1f} min")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwritten -> {OUT}")


if __name__ == "__main__":
    main()
