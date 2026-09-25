"""
after_tax_noise.py -- the after-tax edge of v2 over the investable buy & hold, under price noise.

    ./venv/bin/python results/after_tax_noise.py --universe midcap150
    ./venv/bin/python results/after_tax_noise.py --universe nifty500
    ./venv/bin/python results/after_tax_noise.py --report-only

The measurement experiments/AFTER_TAX_PREREG.txt pre-registers, and nothing
else. Read that file for the accept rule; this one implements it.

PER DRAW
    1. perturb every constituent's adj_close by (1 + eps), eps ~ Normal(0, sigma),
       with results/price_noise_measure.perturb_farm, unchanged: one numpy
       Generator per noise seed, consumed in sorted filename order.
    2. rebuild the raw panel and refit the production 10-seed monthly ensemble
       from the perturbed farm (engine_core.build_panel, score_monthly).
    3. run v2 exactly as published under tax on: mode breadth, sizing invvol,
       cadence 20, research profile, the in-loop tax ledger with the last
       partial financial year settled on the final session, nothing sold at the
       end (the headline).
    4. build the investable taxed buy & hold on the SAME perturbed panel
       (results/bh_held.held_lots, eq_headline): equal rupees of every name on
       the first session, held, nothing realised, nil tax.
    5. gap = CAGR% of 3 minus CAGR% of 4, both at full precision with
       engine_core.metrics' formula, (end / start) ** (365.25 / days) - 1.

THE IDENTITY BASELINE (sigma 0) runs first. It must reproduce the published v2
tax-on headline CAGR and the investable buy & hold headline CAGR, both read from
results_<universe>/metrics/BH_LOTS_<universe>_tax.csv, to within 0.005 points.
If it does not, the run stops and no draw is recorded. The baseline is not one
of the ten draws.

RECORD: diagnostics/after_tax_noise_runs.csv, one row per run, appended as each
run finishes, so an interrupted grid resumes where it stopped (a run is fully
deterministic in its seed, so re-running an interrupted seed recomputes the
same draw; it is not a new draw). REPORT: diagnostics/after_tax_noise.txt.
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["PYTHONHASHSEED"] = "0"

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import config                                                 # noqa: E402
import engine_core as _ec                                     # noqa: E402
import arms.registry as arm_reg                               # noqa: E402
import bh_held                                                # noqa: E402
from config import read_table                                 # noqa: E402
from engine_core import build_panel, score_monthly, precompute, HORIZON  # noqa: E402
from features_v2 import FEATS_V2                              # noqa: E402
from numerics import rolling_std                              # noqa: E402
from test_exposure import backtest_exposure                   # noqa: E402
from universes.registry import REGISTRY, check_tags           # noqa: E402
from price_noise_measure import SEEDS, perturb_farm, script_fingerprint as _pn_fp  # noqa: E402

# FIXED BY experiments/AFTER_TAX_PREREG.txt. Not arguments, so a run cannot
# measure anything the pre-registration did not name.
UNIVERSES = ("midcap150", "nifty500")
SIGMA = 0.0001
NOISE_SEEDS = [101, 202, 303, 404, 505, 606, 707, 808, 909, 1010]
VOL_WIN = 60
RUNS = ROOT / "diagnostics" / "after_tax_noise_runs.csv"
REPORT = ROOT / "diagnostics" / "after_tax_noise.txt"
GATE_TOL = 0.005

RULE = ("An after-tax edge is supported for a universe only if at least 9 of 10 "
        "draws beat the investable buy & hold, and the mean gap exceeds one sd of "
        "the gaps. Anything else is reported as not supported.")


def cagr(eq):
    """engine_core.metrics' CAGR, in percent, at full precision."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100)


def published(u):
    """(v2 tax-on headline CAGR, investable buy & hold headline CAGR) from BH_LOTS."""
    f = Path(u.metrics_dir) / f"BH_LOTS_{u.tag}_tax.csv"
    t = read_table(f).set_index("line")
    return float(t.loc["v2 after tax", "cagr_full"]), float(t.loc["bh_lots after tax", "cagr_full"])


def one_run(u, data_dir):
    """Rebuild the panel from data_dir; return (v2 CAGR, bh CAGR, v2 tax, v2 final)."""
    raw = build_panel(HORIZON, data_dir=data_dir)
    keep = ["date", "symbol", "open", "close", "year", "y_rank", "scorable"] + FEATS_V2
    p = score_monthly(raw[keep], SEEDS, purge_mode=u.purge_mode)
    p = p[["date", "symbol", "open", "close", "score", "year"]]
    _ec.set_tradeability(u)
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
    audit = {k: [] for k in ("holdings", "summary", "trades", "ranking",
                             "decisions", "skipped")}
    arm = arm_reg.ARMS["v2"]
    eq, _tc, _n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                       target_vol=pv.loc[bd].median(), audit=audit,
                                       rebal=20, tax_enabled=True, participation_cap=None,
                                       **arm.kwargs)
    bh = bh_held.held_lots(px, op, bd)["eq_headline"]
    return cagr(eq), cagr(bh), float(audit["tax"]["cum_tax"]), float(eq.iloc[-1])


def load_runs():
    return read_table(RUNS) if RUNS.exists() else pd.DataFrame()


def measure(tag, work):
    u = REGISTRY[tag]
    done = load_runs()
    have = set()
    if len(done):
        have = {int(s) for s in done[done["tag"] == tag]["noise_seed"]}
    src = u.prepare_data_dir()
    for sigma, ns in [(0.0, 0)] + [(SIGMA, s) for s in NOISE_SEEDS]:
        if ns in have:
            print(f"  skip {tag} seed {ns} (recorded)", flush=True)
            continue
        wd = Path(work) / f"farm_{tag}"
        shutil.rmtree(wd, ignore_errors=True)
        t0 = time.time()
        rows, cross = perturb_farm(src, wd, sigma, ns)
        v2, bh, tax, fin = one_run(u, wd)
        shutil.rmtree(wd, ignore_errors=True)
        if sigma == 0.0:
            pv2, pbh = published(u)
            if abs(v2 - pv2) > GATE_TOL or abs(bh - pbh) > GATE_TOL:
                raise SystemExit(
                    f"IDENTITY GATE FAILED for {tag}: harness v2 {v2:.4f} bh {bh:.4f}, "
                    f"published v2 {pv2:.4f} bh {pbh:.4f}. No draw is recorded.")
            print(f"  identity gate PASSES: v2 {v2:.4f} (published {pv2:.4f}), "
                  f"bh {bh:.4f} (published {pbh:.4f})", flush=True)
        rec = {"tag": tag, "sigma": sigma, "noise_seed": ns,
               "v2_cagr": round(v2, 6), "bh_cagr": round(bh, 6),
               "gap": round(v2 - bh, 6), "v2_tax": round(tax, 2),
               "v2_final_equity": round(fin, 2), "rows": rows,
               "bound_crossings": cross,
               "minutes": round((time.time() - t0) / 60, 2),
               "run_date": time.strftime("%Y-%m-%d %H:%M"),
               "script_sha256": _fingerprint(), "perturb_sha256": _pn_fp()}
        df = load_runs()
        df = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)
        # naming: axis-free -- the pre-registered record of one measurement,
        # fixed to tax on, cadence 20, research; it varies over no published axis
        df.to_csv(RUNS, index=False)
        print(f"  {tag} sigma {sigma} seed {ns}: v2 {v2:.4f}  bh {bh:.4f}  "
              f"gap {v2 - bh:+.4f}  ({rec['minutes']} min)", flush=True)
    write_report()


def _fingerprint():
    import hashlib
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def verdict(gaps):
    """The pre-registered rule, applied mechanically. -> (supported, above, mean, sd)."""
    g = np.asarray(gaps, dtype=float)
    above = int((g > 0).sum())
    mean = float(g.mean())
    sd = float(g.std(ddof=1)) if len(g) > 1 else 0.0
    return (len(g) == 10 and above >= 9 and mean > sd), above, mean, sd


def write_report():
    df = load_runs()
    L = ["AFTER-TAX EDGE UNDER PRICE NOISE -- experiments/AFTER_TAX_PREREG.txt",
         "=" * 78,
         f"v2 tax-on headline minus the investable taxed buy & hold headline, CAGR points.",
         f"sigma {SIGMA} (0.01%), noise seeds {NOISE_SEEDS[0]} to {NOISE_SEEDS[-1]}, n=10.",
         f"RULE (verbatim): {RULE}", ""]
    for tag in UNIVERSES:
        g = df[df["tag"] == tag] if len(df) else df
        if not len(g):
            L += [f"{tag}: not run", ""]
            continue
        base = g[g["sigma"] == 0.0]
        draws = g[g["sigma"] > 0].sort_values("noise_seed")
        L.append(f"{tag}")
        if len(base):
            b = base.iloc[0]
            L.append(f"  identity baseline (not a draw): v2 {b['v2_cagr']:.4f}  "
                     f"bh {b['bh_cagr']:.4f}  gap {b['gap']:+.4f}")
        for _, r in draws.iterrows():
            L.append(f"  seed {int(r['noise_seed']):>4}: v2 {r['v2_cagr']:8.4f}  "
                     f"bh {r['bh_cagr']:8.4f}  gap {r['gap']:+8.4f}")
        if len(draws) == 10:
            ok, above, mean, sd = verdict(draws["gap"])
            L += [f"  gaps: mean {mean:+.4f}  sd {sd:.4f} (ddof=1)  min "
                  f"{draws['gap'].min():+.4f}  max {draws['gap'].max():+.4f}  "
                  f"draws above zero {above} of 10",
                  f"  verdict: {'SUPPORTED' if ok else 'NOT SUPPORTED'} "
                  f"({above} of 10 draws beat the investable buy & hold, needed 9; "
                  f"mean gap {mean:+.4f} {'exceeds' if mean > sd else 'does not exceed'} "
                  f"one sd {sd:.4f})"]
        else:
            L.append(f"  {len(draws)} of 10 draws recorded; no verdict until all 10 are in")
        L.append("")
    # naming: axis-free -- the pre-registered report, see RUNS above
    REPORT.write_text("\n".join(L) + "\n")
    print("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--universe")
    ap.add_argument("--work", default="/tmp/after_tax_noise")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args(argv)
    if a.report_only:
        write_report()
        return 0
    if not a.universe:
        raise SystemExit("give --universe midcap150 or --universe nifty500")
    check_tags([a.universe], UNIVERSES)
    measure(a.universe, a.work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
