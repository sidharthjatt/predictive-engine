"""
leakage_check2_trading_purge.py -- CHECK 2 of experiments/LEAKAGE_SPEC.txt,
asked of the purge rule PRODUCTION ACTUALLY USES.
==============================================================================

WHY THIS FILE EXISTS

    leakage_check2_purge.py builds the training cut the CALENDAR way,
    `first - Timedelta(days=PURGE)`, and reports that it does not hold in 7 of
    105 months on each live universe. engine_core.score_monthly has defaulted to
    purge_mode="trading" since the leakage fix and both live universes are
    registered with purge_mode='trading', so that check describes a path
    production does not take. Measured 2026-09-21 and recorded in
    diagnostics/gate_verdicts.txt: THE LIVE PURGE RULE WAS TESTED BY NO SCRIPT IN
    THIS TREE. This is that test.

    leakage_check2_purge.py IS NOT MODIFIED AND IS NOT REPLACED. It stays as the
    record of what the calendar rule does, which is the reason the trading rule
    exists. The two are siblings, not versions.

    IT IS NOT CALLED "CHECK 3". experiments/LEAKAGE_SPEC.txt:140 already assigns
    CHECK 3 to NORMALISATION SCOPE, and that check's script is absent from this
    tree -- the spec names diagnostics/leakage_check3_normalisation.txt at line
    254 and nothing writes it. Taking the number would hide that gap.

THE RULE IS READ FROM THE ENGINE, NOT REIMPLEMENTED -- AND HERE IS THE EXACT
CLAIM, BECAUSE IT IS NOT "score_monthly WAS CALLED AND ASKED FOR ITS CUT".

    engine_core.score_monthly computes the cut INLINE inside its month loop
    (engine_core.py:657-661) and never returns, stores or exposes it:

        _j  = _pos[np.datetime64(_first)] - HORIZON - PURGE_EMBARGO
        cut = pd.Timestamp(_cal[_j])
        tr  = (p["date"] <= cut) & p["y_rank"].notna()

    There is no entry point that yields the cut, so it cannot be called directly
    for this purpose. What is called instead is score_monthly ITSELF, unmodified,
    with the real panel and the universe's registered purge_mode -- so the three
    lines above are the ones that execute. Only the model fit is replaced, by a
    stub that returns zeros in place of engine_core._fit_seed.

    WHY STUBBING THE FIT IS SAFE HERE. The cut, the training mask and the month
    loop are computed BEFORE _fit_seed is reached and do not depend on it or on
    the seeds. Replacing the fit changes how long the run takes and the scores it
    produces; it cannot change which rows were selected for training, which is the
    only thing this check reads. The scores are discarded.

    HOW THE CUT IS RECOVERED, EXACTLY. The stub records len(ytr), the number of
    training rows the engine actually selected for that month. score_monthly sorts
    the panel by (date, symbol) and the mask is `date <= cut AND y_rank notna`, so
    those rows are the first len(ytr) eligible rows in date order and the LAST
    TRAINING ROW'S DATE is element len(ytr)-1 of the date-sorted eligible dates.
    That recovery is exact, and it is the latest training date -- not the cut --
    that decides whether a label reaches into the scored month.

WHAT IS MEASURED, PER SCORING MONTH THAT ACTUALLY TRAINED

    latest_train    the date of the last row the engine put in the training set
    label_observes  where that row's label lands: HORIZON trading rows later on
                    the panel's own calendar, the same arithmetic
                    leakage_check2_purge.py uses
    gap             first scored date minus that, in TRADING days

    gap > 0   the purge holds.
    gap == 0  the label observes the first scored day.
    gap < 0   THE LABEL REACHES INTO THE SCORED MONTH -- leakage, of that size.

    THE GATE IS gap > 0 IN EVERY MONTH ON EVERY LIVE UNIVERSE, which is the
    condition leakage_check2_purge.py already calls "purge holds". The margin
    against PURGE_EMBARGO is reported but NOT gated: score_monthly's docstring
    claims gap >= PURGE_EMBARGO by construction, and reporting where that claim
    sits is useful, but failing the run on it would be gating a stronger
    condition than the one that defines leakage.

    MONTHS THE ENGINE SKIPS ARE NOT INVENTED INTO THE COUNT. score_monthly skips
    a month when _j < 0, when fewer than 5,000 training rows survive, or when
    nothing is scorable; those months never train and never produce a label that
    could reach anywhere. They are counted and reported as skipped.

USAGE

    ./venv/bin/python results/leakage_check2_trading_purge.py

    Writes diagnostics/leakage_check2_trading_purge.txt. Exits non-zero if the
    purge does not hold in any month on any live universe.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import numpy as np                                   # noqa: E402
import pandas as pd                                  # noqa: E402
import config                                        # noqa: E402
import engine_core as _ec                            # noqa: E402
from engine_core import HORIZON, PURGE_EMBARGO       # noqa: E402
from universes.registry import REGISTRY              # noqa: E402
from config import read_table  # the one CSV/parquet reader: config.read_table

LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {u.tag: (u.raw_cache, u.purge_mode, LABELS[u.tag])
             for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])}

# One seed. The training mask does not depend on the seed list and the fit is
# stubbed, so more seeds would repeat the same month loop for nothing.
PROBE_SEEDS = [7]


def run(uni, perm, purge_mode, label, W):
    src = config.require_cache(perm, what=f"{uni} raw panel")
    raw = read_table(src, parse_dates=["date"])

    W("=" * 100)
    W(f" CHECK 2 (TRADING RULE) -- TRAINING MASK AND PURGE -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  panel {src.name}   rows {len(raw):,}   symbols {raw['symbol'].nunique()}")
    W(f"  purge_mode from the registry: {purge_mode!r}      "
      f"HORIZON = {HORIZON} TRADING rows   PURGE_EMBARGO = {PURGE_EMBARGO}")
    if purge_mode != "trading":
        W(f"  THIS UNIVERSE IS NOT REGISTERED FOR THE TRADING RULE. Reported and "
          f"not skipped, so the disagreement is visible.")

    # The panel exactly as score_monthly orders it, so recovered positions match.
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True)
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}
    elig_dates = p.loc[p["y_rank"].notna(), "date"].to_numpy()

    ym_col = p["date"].dt.to_period("M")
    months = sorted(ym_col[p["date"].dt.year >= 2016].unique())

    seen = []
    orig = _ec._fit_seed

    def _stub(sd, Xtr, ytr, Xte, n_jobs=1):
        # len(ytr) recovers the cut; len(Xte) identifies WHICH month this was.
        seen.append((int(len(ytr)), int(len(Xte))))
        return np.zeros(len(Xte))

    _par = _ec.PARALLEL_SEEDS
    _ec.PARALLEL_SEEDS = False
    _ec._fit_seed = _stub
    try:
        _ec.score_monthly(raw, PROBE_SEEDS, purge_mode=purge_mode)
    finally:
        _ec._fit_seed = orig
        _ec.PARALLEL_SEEDS = _par

    # WHICH MONTHS TRAINED IS MATCHED, NOT ASSUMED. score_monthly calls the fit
    # once per trained month in month order and silently skips the rest, so the
    # trained set is a SUBSEQUENCE of the candidates and its position is not known
    # in advance. Each call's len(Xte) is that month's scorable-row count, which is
    # computable here from the panel alone, so the calls are aligned to months by
    # walking the candidates in order and matching that count. An alignment that
    # does not consume every call is a failure of this harness and says so rather
    # than reporting a month's gap under another month's name.
    scorable = p["scorable"] if "scorable" in p.columns else pd.Series(True, index=p.index)
    trained_months, k = [], 0
    for ym in months:
        if k >= len(seen):
            break
        if int(((ym_col == ym) & scorable).sum()) == seen[k][1]:
            trained_months.append(ym)
            k += 1
    if k != len(seen):
        raise SystemExit(
            f"{uni}: aligned {k} of {len(seen)} fit calls to months. This harness "
            f"cannot say which month each training set belonged to; no gap is "
            f"reported rather than reporting one against the wrong month.")
    n_trained, n_cand = len(seen), len(months)
    W(f"  scoring months considered: {n_cand}   trained: {n_trained}   "
      f"skipped by the engine: {n_cand - n_trained}")
    W("")

    rows = []
    for ym, (n_tr, _n_te) in zip(trained_months, seen):
        first = p.loc[ym_col == ym, "date"].min()
        latest = pd.Timestamp(elig_dates[n_tr - 1])
        i = pos[np.datetime64(latest)]
        j = min(i + HORIZON, len(cal) - 1)
        observed = pd.Timestamp(cal[j])
        rows.append({"month": str(ym), "first_scored": str(first.date()),
                     "train_rows": n_tr, "latest_train": str(latest.date()),
                     "label_observes": str(observed.date()),
                     "gap_trading_days": pos[np.datetime64(first)] - j,
                     "gap_calendar_days": (first - observed).days})

    D = pd.DataFrame(rows)
    if D.empty:
        W("  NO MONTH TRAINED. Nothing to assert.")
        return {"trained": 0, "neg": 0, "zero": 0, "below_embargo": 0}

    g = D["gap_trading_days"]
    neg, zero = D[g < 0], D[g == 0]
    W("  WHERE THE LABEL ACTUALLY REACHES -- gap distribution, in TRADING days")
    W(f"    min {g.min()}   p5 {np.percentile(g,5):.0f}   median {g.median():.0f}"
      f"   p95 {np.percentile(g,95):.0f}   max {g.max()}")
    W("")
    W(f"    months with gap <  0 (label reaches INTO the scored month): {len(neg)}")
    W(f"    months with gap == 0 (label observes the first scored day):  {len(zero)}")
    W(f"    months with gap >  0 (purge holds):                          "
      f"{len(D) - len(neg) - len(zero)}")
    W("")
    if len(neg):
        W("    THE PURGE DOES NOT HOLD IN THESE MONTHS:")
        for _, r in neg.iterrows():
            W(f"      {r['month']}  first scored {r['first_scored']}  "
              f"latest train {r['latest_train']}  label observes "
              f"{r['label_observes']}  overlap {-r['gap_trading_days']} trading days")
        W("")
    below = D[g < PURGE_EMBARGO]
    W(f"  REPORTED, NOT GATED -- score_monthly's docstring claims the gap is at "
      f"least PURGE_EMBARGO ({PURGE_EMBARGO}) by construction.")
    W(f"    months with gap < {PURGE_EMBARGO}: {len(below)} of {len(D)}"
      + (f"   tightest: {', '.join(below.nsmallest(5,'gap_trading_days')['month'])}"
         if len(below) else ""))
    W("")
    W("  THE TIGHTEST MONTHS (smallest gaps):")
    W(f"  {'month':<10}{'first scored':<14}{'latest train':<14}"
      f"{'label observes':<16}{'gap td':>7}{'gap cal':>9}")
    for _, r in D.nsmallest(8, "gap_trading_days").iterrows():
        W(f"  {r['month']:<10}{r['first_scored']:<14}{r['latest_train']:<14}"
          f"{r['label_observes']:<16}{r['gap_trading_days']:>7}"
          f"{r['gap_calendar_days']:>9}")
    W("")
    md = REGISTRY[uni].metrics_dir   # not the panel's directory: panels live under cache/ since 2026-09-23
    # naming: axis-free -- the per-month gap table for one universe under the
    # live purge rule. It describes the TRAINING MASK, not a strategy result, so
    # it varies over no arm, cadence, profile or tax selection; the universe is
    # carried by the directory it is written into, as its calendar-rule sibling
    # leakage_purge_gaps.csv already is.
    D.to_csv(md / "leakage_purge_gaps_trading.csv", index=False)
    W(f"  every month written to {md.name}/leakage_purge_gaps_trading.csv")
    W("")
    return {"trained": len(D), "neg": len(neg), "zero": len(zero),
            "below_embargo": len(below)}


def main():
    out = []
    res = {}
    for uni, (perm, pm, label) in UNIVERSES.items():
        res[uni] = run(uni, perm, pm, label, out.append)
        out.append("")

    tot_neg = sum(r["neg"] for r in res.values())
    tot_zero = sum(r["zero"] for r in res.values())
    tot_tr = sum(r["trained"] for r in res.values())
    bad = {u: r for u, r in res.items() if r["neg"] or r["zero"]}
    out.append("  RULE TESTED: the TRADING purge, "
               "cut = cal[pos(first) - HORIZON - PURGE_EMBARGO], which is what")
    out.append("  engine_core.score_monthly runs for both live universes. The "
               "calendar rule is the sibling check.")
    if bad:
        out.append(f"  RESULT: FAIL -- the purge does not hold in "
                   f"{tot_neg} month(s) with a label reaching into the scored "
                   f"month and {tot_zero} month(s) at gap 0, of {tot_tr} trained "
                   f"month-universe pair(s), on: " + ", ".join(sorted(bad)) + ".")
        rc = 1
    else:
        per = ", ".join(f"{u} {r['trained']}" for u, r in sorted(res.items()))
        out.append(f"  RESULT: PASS -- the purge holds in every trained month: "
                   f"{tot_tr} month-universe pair(s) across "
                   f"{len(res)} universe(s) ({per}).")
        rc = 0
    # naming: axis-free -- one report on the training mask under the live purge
    # rule, covering both universes, which are named inside the file. It varies
    # over no published axis, exactly as leakage_check2_purge.txt does.
    (ROOT / "diagnostics" / "leakage_check2_trading_purge.txt").write_text(
        "\n".join(out) + "\n")
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
