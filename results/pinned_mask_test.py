"""pinned_mask_test.py -- does the price-perturbation displacement travel through
row admission?

THE DECISION RULE IS FIXED HERE, BEFORE ANY NUMBER EXISTS, and this file is
committed before the first run. That is the same discipline results/atom_measure.py
used, and the reason is the same: a threshold chosen after seeing the result is not
a test.

    MECHANISM FOUND if the mean reduction in displacement, across three noise
    seeds on each live universe, is >= 50%.

    reduction = 1 - (pinned - baseline) / (perturbed - baseline)

    Below 50% the channel does not carry it. There is no partial verdict and no
    fifth candidate: if this fails, the conclusion is that the mechanism is not
    findable by channel decomposition.

WHAT IS BEING TESTED, AND WHY THIS CANDIDATE

    engine_core.py gates every panel row on `p[FEATS_V2].notna().all(axis=1)` --
    a row is scored only if ALL SEVENTEEN features are present. That is why every
    feature in diagnostics/atoms.txt Part A reports an IDENTICAL non-null count:
    it is one row-level gate, not seventeen feature-level ones.

    Perturbation moves that count UP, and the count was recorded and left
    unexplained by the atom work:

        nifty100    441,155 -> 443,353   (+2,198)
        midcap150   523,059 -> 525,563   (+2,504)

    Three reasons this is the candidate rather than a fourth round of ruling
    things out:

      ONE-SIDED BY CONSTRUCTION. Noise destroys exact equalities and essentially
      never creates them, so recovered rows can only be ADDED. A systematic
      displacement needs a channel with a direction; ties and sort order are
      symmetric and were measured to be inert.

      THE REACH IS LARGER THAN ANYTHING LEFT. A newly admitted row does not only
      add a selection candidate. It joins the cross-sectional z-score PEER GROUP,
      so it moves every other name's normalised features on that date.

      IT CONNECTS TO MEASURED DEGENERACY. Consecutive closes are exactly equal on
      1.97% of nifty100 rows and 3.01% of midcap150 rows, falling to about 0.27%
      and 0.21% under sigma 0.01%. A zero-variance window is what makes a
      vol-scaled feature undefined.

THE INTERVENTION, AND THE ONE THING IT CANNOT DO

    The perturbed panel is rebuilt with `pin_scorable` set to the UNPERTURBED
    run's scorable pairs, so prices move but row admission cannot rise above the
    baseline set. Applied inside build_panel, before the z-score, so the peer
    group is pinned too.

    IT REMOVES ADMISSIONS AND CANNOT RESTORE LOSSES. The pinned mask is the
    INTERSECTION of the two scorable sets. A row the baseline scored and
    perturbation dropped stays dropped, because its features are NaN under
    perturbation and nothing can invent them. So this tests the ADMISSION channel
    specifically, which is the one the +2,198 and +2,504 counts describe. The
    net figures are dominated by admissions, but the churn in each direction is
    reported per run so the asymmetry is visible rather than assumed.

COST

    Baseline and perturbed CAGRs are NOT recomputed -- they are read from
    diagnostics/price_noise_runs.csv, which already holds sigma=0 and ten seeds at
    sigma=0.01% per universe. Only the pinned arm is run: 3 seeds x 2 universes,
    about 16-18 minutes each.
"""
import io
import sys
import json
import contextlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import config                                          # noqa: E402
import engine_core as _ec                              # noqa: E402
import price_noise_measure as pnm                      # noqa: E402
from universes.registry import REGISTRY                # noqa: E402

SEEDS_UNDER_TEST = (101, 202, 303)
SIGMA = 0.0001
RULE = 0.50
DIAG = ROOT / "diagnostics"
REPORT = DIAG / "pinned_mask.txt"


def scorable_pairs(data_dir):
    """The (date, symbol) pairs a panel built from `data_dir` marks scorable."""
    p = _ec.build_panel(_ec.HORIZON, data_dir=data_dir)
    m = p.loc[p["scorable"], ["date", "symbol"]]
    return set(zip(m["date"], m["symbol"]))


def main():
    runs = pd.read_csv(DIAG / "price_noise_runs.csv")
    out = []
    W = out.append
    W("=" * 96)
    W(" PINNED-MASK COUNTERFACTUAL -- is the displacement carried by row admission?")
    W("=" * 96)
    W(f" rule fixed before the run: mechanism found if mean reduction >= {RULE:.0%}")
    W(f" sigma {SIGMA}, seeds {SEEDS_UNDER_TEST}, arm v2")
    W("")
    rows = []
    for tag in ("nifty100", "midcap150"):
        u = REGISTRY[tag]
        base_row = runs[(runs["tag"] == tag) & (runs["sigma"] == 0.0)]
        base = float(base_row["CAGR%"].iloc[0])
        work = Path(pnm.WORK) / tag if hasattr(pnm, "WORK") else None
        with contextlib.redirect_stdout(io.StringIO()):
            base_dir = u.prepare_data_dir()
            pinned_set = scorable_pairs(base_dir)
        W(f"  {tag}: baseline CAGR {base:.4f}, "
          f"{len(pinned_set):,} scorable pairs at sigma=0")
        for ns in SEEDS_UNDER_TEST:
            pr = runs[(runs["tag"] == tag) & (runs["sigma"] == SIGMA)
                      & (runs["noise_seed"] == ns)]
            pert = float(pr["CAGR%"].iloc[0])
            farm = Path("/tmp") / f"pinned_mask_{tag}_s{SIGMA}_n{ns}"
            with contextlib.redirect_stdout(io.StringIO()):
                pnm.perturb_farm(base_dir, farm, SIGMA, ns)
                pert_set = scorable_pairs(farm)
                expect = len(pert_set & pinned_set)
                # THE PIN IS THE INTERSECTION. See the module docstring.
                #
                # PATCHED ON price_noise_measure, NOT ON engine_core. That module
                # does `from engine_core import build_panel` at import, so the
                # name run_arm calls lives in ITS namespace; patching
                # engine_core.build_panel leaves that binding untouched and the
                # pinned arm silently reruns the unpinned one. The first run of
                # this test did exactly that and returned reduction +0.0% on all
                # six cells -- an intervention that never happened, reported to
                # four decimal places.
                seen = {}
                _orig = pnm.build_panel

                def _pinned(h, data_dir, _p=pinned_set, _o=_orig, _seen=seen):
                    panel = _o(h, data_dir=data_dir, pin_scorable=_p)
                    _seen["scorable"] = int(panel["scorable"].sum())
                    return panel

                pnm.build_panel = _pinned
                try:
                    m, _held = pnm.run_arm(u, farm)
                finally:
                    pnm.build_panel = _orig
            # THE INTERVENTION MUST BE PROVED TO HAVE BITTEN, EVERY CELL. A
            # no-op pin produces reduction 0% and looks like a clean negative.
            if "scorable" not in seen:
                raise RuntimeError(
                    f"{tag} seed {ns}: the pinned build_panel was never called")
            if seen["scorable"] != expect:
                raise RuntimeError(
                    f"{tag} seed {ns}: pinned panel has {seen['scorable']:,} "
                    f"scorable rows, expected {expect:,} (the intersection). "
                    f"The pin did not apply.")
            pin = float(m["CAGR%"])
            disp = pert - base
            resid = pin - base
            red = (1 - resid / disp) if disp else float("nan")
            added = len(pert_set - pinned_set)
            lost = len(pinned_set - pert_set)
            rows.append({"tag": tag, "seed": ns, "baseline": base,
                         "perturbed": pert, "pinned": pin,
                         "displacement": round(disp, 4),
                         "residual": round(resid, 4),
                         "reduction": round(red, 4),
                         "rows_added": added, "rows_lost": lost})
            W(f"    seed {ns}: perturbed {pert:.4f} (disp {disp:+.4f})  "
              f"pinned {pin:.4f} (resid {resid:+.4f})  reduction {red:+.1%}  "
              f"| admitted {added:,} lost {lost:,}")
        W("")
    df = pd.DataFrame(rows)
    df.to_csv(DIAG / "pinned_mask_runs.csv", index=False)
    mean_red = float(df["reduction"].mean())
    W("=" * 96)
    for tag, g in df.groupby("tag"):
        W(f"  {tag}: mean reduction {g['reduction'].mean():+.1%} over "
          f"{len(g)} seeds")
    W(f"  OVERALL MEAN REDUCTION: {mean_red:+.1%}   rule: >= {RULE:.0%}")
    W("")
    if mean_red >= RULE:
        W("  RESULT: the admission channel CARRIES the displacement by the rule")
        W("  fixed before this run. This is a measurement meeting a threshold; the")
        W("  mechanism still has to be described, not inferred from the number.")
        rc = 0
    else:
        W("  RESULT: the admission channel DOES NOT carry the displacement.")
        W("  Under the stopping point fixed before this run, no further candidate")
        W("  is proposed and the mechanism is not findable by channel")
        W("  decomposition.")
        rc = 1
    W("=" * 96)
    txt = "\n".join(out)
    print(txt)
    REPORT.write_text(txt + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
