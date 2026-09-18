"""
validate_breadth_live.py -- breadth validation on the LIVE universes.

Governed by experiments/BREADTH_LIVE_SPEC.txt, written before this file existed.
Read that first; this module implements it and does not restate its reasoning.

WHY THIS IS A NEW FILE AND results/validate_breadth.py IS NOT TOUCHED
    validate_breadth.py is the provenance of the 58-stock result. Rewriting it to
    take a universe argument would destroy that record. It stays frozen. T1 and T2
    below are copied from it verbatim -- same seed sets, same criteria, same
    thresholds -- so that this is the SAME test applied to a different universe
    rather than a new test that happens to resemble it.

THE THREE TESTS
    T1  seed robustness   GATED   dSharpe > 0 and dMaxDD > 3 on all three seed sets
    T2  sub-period        GATED   dSharpe > 0 in both halves
    T3  constant-exposure control  NOT GATED, REPORTED ONLY

    T1 AND T2 ARE ASYMMETRIC AND THAT IS INHERITED, NOT CHOSEN. T1 gates on Sharpe
    AND drawdown; T2 gates on Sharpe ALONE. A rule that improved Sharpe in both
    halves while WORSENING drawdown in one of them would pass T2. The 58's suite
    was written that way and harmonising it here would be changing the test.

    THE dMaxDD > 3 BAR IS UNDERIVED. Nothing in validate_breadth.py derives it and
    nothing here does either -- it is a magic constant of the same class as T1's
    400-1400 trade range in validate_sizing.py. It is copied unchanged to both
    universes and is NOT recalibrated per universe.

T3 IS REPORTED, NEVER JUDGED
    T3 compares breadth against a FIXED exposure equal to breadth's own realised
    mean, so the deployment level is neutralised and only the timing differs. It
    therefore does NOT test whether breadth's chosen level is a good level, and
    the constant is not an independent benchmark -- it is read out of the arm it
    is compared against.

    T3 was added after v2's numbers were known, so gating on it would be choosing
    a criterion with the data in view. It prints differences and nothing else: no
    verdict word, no threshold, and never T1's 3-point bar, which belongs to a
    different comparison.

CACHES ARE NAMESPACED AND THERE IS NO FALLBACK
    validate_breadth.py:56-60 falls back to engine_core's /tmp/FINAL_seed{i}.csv.
    On the 58 that is sound -- same raw panel, same seeds. Carried here unchanged
    it would silently score a 58-stock panel and print a verdict for the wrong
    universe with no error at all. The caches here are
    /tmp/VALBREADTH_{universe}_seed{i}.csv and NOTHING ELSE IS READ. No cache
    written by another script is used, including /tmp/VALSIZE_* -- see the spec.

Reads the panels. Writes the /tmp seed caches, three CSVs into the universe's
metrics folder, and one report into diagnostics/.

    python3 results/validate_breadth_live.py --universe=n100          # cost only
    python3 results/validate_breadth_live.py --universe=n100 --run    # full run
"""
import json
import subprocess
import sys
import time
import warnings

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import config
from engine_core import (precompute, metrics, score_monthly, HORIZON, VOL_WIN,
                         START_CAPITAL)
from test_exposure import backtest_exposure
from universes.registry import REGISTRY
import profiles as _prof            # the run's execution-realism profile

# Date window from config.py, NOT engine_core's year ints -- see config.py.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE

# ALL FOUR PANEL PATHS AND THE METRICS DIRECTORY come from
# universes/registry.py -- the single definition. The LABEL stays local; this
# file uses the "Nifty 100"/"MidCap150" spelling, and it is written into
# breadth_live_params.json as well as printed, so it must not move.
LABELS = {"nifty100": "Nifty 100", "midcap150": "MidCap150"}
UNIVERSES = {
    u.tag: {"score_perm": u.score_cache, "score_tmp": str(u.score_tmp),
            "raw_perm": u.raw_cache, "raw_tmp": str(u.raw_tmp),
            "metrics": u.metrics_dir, "label": LABELS[u.tag]}
    for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])
}

# Verbatim from results/validate_breadth.py. Not reordered, not extended.
SEED_SETS = [[5, 55, 555], [13, 26, 39], [101, 202, 303]]
HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
DD_BAR = 3.0            # UNDERIVED. See the module docstring and the spec.


# ---------------------------------------------------------------- panel helpers
def panel_parts(p):
    """Pivot a scored panel into the objects backtest_exposure wants."""
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    return px, op, sc, pc, mom20, port_vol


def window_dates(px, y0=None, y1=None):
    """The backtest window, optionally narrowed to a year range."""
    m = (px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)
    if y0 is not None:
        m &= (px.index.year >= y0) & (px.index.year <= y1)
    return px.index[m]


def run_mode(parts, dd, mode, const_expo=None):
    """One backtest. Returns (metrics dict, realised mean exposure)."""
    px, op, sc, pc, mom20, port_vol = parts
    target_vol = port_vol.loc[dd].median()
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See profiles.research_only.
    eq, tc, ntr, expo = backtest_exposure(px, op, sc, dd, pc, mom20, port_vol,
                                          mode=mode, target_vol=target_vol,
                                          const_expo=const_expo, participation_cap=_prof.research_only(__name__))
    return metrics(eq, mode, tc, ntr), float(expo)


def compare(parts, dd, mode_a, mode_b, const_expo=None):
    """mode_b minus mode_a on Sharpe and MaxDD, plus both realised exposures."""
    ma, ea = run_mode(parts, dd, mode_a, const_expo if mode_a == "const" else None)
    mb, eb = run_mode(parts, dd, mode_b, const_expo if mode_b == "const" else None)
    return {"Sharpe_a": ma["Sharpe"], "Sharpe_b": mb["Sharpe"],
            "dSharpe": round(mb["Sharpe"] - ma["Sharpe"], 4),
            "MaxDD_a": ma["MaxDD%"], "MaxDD_b": mb["MaxDD%"],
            "dMaxDD": round(mb["MaxDD%"] - ma["MaxDD%"], 4),
            "CAGR_a": ma["CAGR%"], "CAGR_b": mb["CAGR%"],
            "dCAGR": round(mb["CAGR%"] - ma["CAGR%"], 4),
            "expo_a": round(ea * 100, 2), "expo_b": round(eb * 100, 2)}


def _git_state():
    """The tree this ran on, dirt included. Mirrors v34_common._git_state."""
    def _run(args):
        try:
            r = subprocess.run(["git"] + args, capture_output=True, text=True,
                               timeout=10, cwd=str(ROOT))
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
    head, status = _run(["rev-parse", "HEAD"]), _run(["status", "--porcelain"])
    if head is None or status is None:
        return {"commit": None,
                "note": "git unavailable; the tree this ran on is not recorded"}
    modified = [l for l in status.splitlines() if l.strip()]
    return {"commit": head.strip(),
            "working_tree_dirty": len(modified) > 0,
            "modified_or_untracked_files": len(modified),
            "note": ("the commit alone does NOT describe this run: the working "
                     "tree had uncommitted changes when it was produced"
                     if modified else
                     "working tree clean; the commit describes this run exactly")}


def universe_from_argv():
    for u in UNIVERSES:
        if f"--universe={u}" in sys.argv:
            return u
    print("usage: validate_breadth_live.py --universe=n100|mid [--run]")
    print("  no default -- the universe must be named explicitly.")
    sys.exit(2)


# ------------------------------------------------------------------------ main
def main():
    u = universe_from_argv()
    U = UNIVERSES[u]
    L = []

    def W(s=""):
        L.append(s)
        print(s, flush=True)

    W("=" * 104)
    W(f" BREADTH VALIDATION ON A LIVE UNIVERSE -- {U['label']} ({u})")
    W("=" * 104)
    W(f"  spec    experiments/BREADTH_LIVE_SPEC.txt")
    W(f"  window  {BT_START_DATE.date()} to {BT_END_DATE.date()} inclusive")
    W("  T1 and T2 are copied verbatim from results/validate_breadth.py, which")
    W("  stays frozen. T3 is new and is REPORTED, NOT GATED.")

    score_path = config.require_cache(U["score_perm"], U["score_tmp"],
                                      what=f"{U['label']} score panel")
    prod = pd.read_csv(score_path, parse_dates=["date"])
    parts = panel_parts(prod)
    bd = window_dates(parts[0])
    W(f"\n  score panel  {score_path}")
    W(f"               {parts[0].shape[1]} symbols, {len(bd)} days in the window")

    raw_path = config.require_cache(U["raw_perm"], U["raw_tmp"],
                                    what=f"{U['label']} raw feature panel")

    if "--run" not in sys.argv:
        n_months = len(pd.read_csv(raw_path, usecols=["date"], parse_dates=["date"])
                       .query("date.dt.year >= 2016")["date"].dt.to_period("M")
                       .unique())
        cached = sum(Path(f"/tmp/VALBREADTH_{u}_seed{i}.csv").exists()
                     for i in range(len(SEED_SETS)))
        W("\n" + "=" * 104)
        W(" COST -- nothing has been run")
        W("=" * 104)
        W(f"   T1 refits the model: {n_months} months x {len(SEED_SETS[0])} seeds "
          f"x {len(SEED_SETS)} sets = "
          f"{n_months*len(SEED_SETS[0])*len(SEED_SETS):,} LightGBM fits")
        W(f"   seed caches already present: {cached} of {len(SEED_SETS)}")
        W("   T2 and T3 are backtests on the production panel: seconds")
        W("\n   re-run with --run to execute")
        return

    t_start = time.perf_counter()

    # -------------------------------------------------------------------- T1
    W("\n" + "=" * 104)
    W(" T1. SEED ROBUSTNESS -- does breadth beat 100% invested on 3 independent"
      " seed sets?")
    W("=" * 104)
    W("  GATED on BOTH: dSharpe > 0 and dMaxDD > 3 points, on ALL three sets.")
    raw = pd.read_csv(raw_path, parse_dates=["date"])
    t1_rows = []
    for si, seeds in enumerate(SEED_SETS):
        cache = Path(f"/tmp/VALBREADTH_{u}_seed{si}.csv")
        if cache.exists():
            ps = pd.read_csv(cache, parse_dates=["date"])
            W(f"    seed set {si+1}/{len(SEED_SETS)} {seeds} from cache {cache.name}")
        else:
            W(f"    seed set {si+1}/{len(SEED_SETS)} {seeds} scoring "
              f"(refits the model) ...")
            ps = score_monthly(raw, seeds)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
        sp = panel_parts(ps)
        r = compare(sp, window_dates(sp[0]), "none", "breadth")
        r = {"seedset": si, "seeds": str(seeds), **r}
        t1_rows.append(r)
        W(f"      Sharpe {r['Sharpe_a']:.2f} -> {r['Sharpe_b']:.2f} "
          f"({r['dSharpe']:+.2f})    "
          f"MaxDD {r['MaxDD_a']:.2f}% -> {r['MaxDD_b']:.2f}% "
          f"({r['dMaxDD']:+.2f} pt)    deployed {r['expo_b']:.1f}%")
    t1 = pd.DataFrame(t1_rows)
    ok_sharpe = bool((t1["dSharpe"] > 0).all())
    ok_dd = bool((t1["dMaxDD"] > DD_BAR).all())
    W(f"\n    Sharpe improved on {(t1['dSharpe'] > 0).sum()}/{len(t1)} seed sets"
      f"  -> {'PASS' if ok_sharpe else 'FAIL'}")
    W(f"    MaxDD improved by more than {DD_BAR:.0f} points on "
      f"{(t1['dMaxDD'] > DD_BAR).sum()}/{len(t1)} seed sets"
      f"  -> {'PASS' if ok_dd else 'FAIL'}")

    # -------------------------------------------------------------------- T2
    W("\n" + "=" * 104)
    W(" T2. SUB-PERIOD STABILITY -- does breadth hold in both halves?")
    W("=" * 104)
    W("  GATED on dSharpe > 0 in both halves. THERE IS NO DRAWDOWN CRITERION HERE.")
    W("  That asymmetry with T1 is inherited from the 58's suite, not chosen: a")
    W("  rule improving Sharpe in both halves while worsening drawdown in one")
    W("  would pass T2. MaxDD is printed below but does NOT gate.")
    t2_rows = []
    for lab, y0, y1 in HALVES:
        dd = window_dates(parts[0], y0, y1)
        r = {"period": lab, "first": str(dd[0].date()), "last": str(dd[-1].date()),
             "days": len(dd), **compare(parts, dd, "none", "breadth")}
        t2_rows.append(r)
        W(f"    {lab}  ({r['first']} to {r['last']}, {r['days']} days)")
        W(f"      Sharpe {r['Sharpe_a']:.2f} -> {r['Sharpe_b']:.2f} "
          f"({r['dSharpe']:+.2f})    "
          f"MaxDD {r['MaxDD_a']:.2f}% -> {r['MaxDD_b']:.2f}% "
          f"({r['dMaxDD']:+.2f} pt, not gated)    deployed {r['expo_b']:.1f}%")
    t2 = pd.DataFrame(t2_rows)
    ok2 = bool((t2["dSharpe"] > 0).all())
    W(f"\n    Sharpe improved in {(t2['dSharpe'] > 0).sum()}/{len(t2)} halves"
      f"  -> {'PASS' if ok2 else 'FAIL'}")

    # -------------------------------------------------------------------- T3
    W("\n" + "=" * 104)
    W(" T3. CONSTANT-EXPOSURE CONTROL -- REPORTED, NOT GATED, NO VERDICT")
    W("=" * 104)
    W("  Breadth against a FIXED exposure set to breadth's OWN realised mean over")
    W("  the same window, so the average cash level is identical in both arms and")
    W("  only the timing differs.")
    W("  The constant is read from the breadth run itself; it is never a literal.")
    W("  It is therefore NOT an independent benchmark, and this does NOT test")
    W("  whether the level breadth picks is a good level -- that is unmeasured.")
    W("  No criterion is applied to any number below.")
    t3_rows = []
    for lab, dd in [("full", bd)] + [(l, window_dates(parts[0], a, b))
                                     for l, a, b in HALVES]:
        _, expo_b = run_mode(parts, dd, "breadth")
        r = {"period": lab, "const_level_pct": round(expo_b * 100, 2),
             "first": str(dd[0].date()), "last": str(dd[-1].date()),
             **compare(parts, dd, "const", "breadth", const_expo=expo_b)}
        t3_rows.append(r)
        W(f"    {lab:<10} constant held at {r['const_level_pct']:.2f}% "
          f"(breadth's own realised mean over this window)")
        W(f"      Sharpe  const {r['Sharpe_a']:.2f}  breadth {r['Sharpe_b']:.2f}"
          f"   difference {r['dSharpe']:+.2f}")
        W(f"      MaxDD   const {r['MaxDD_a']:.2f}%  breadth {r['MaxDD_b']:.2f}%"
          f"   difference {r['dMaxDD']:+.2f} points")
        W(f"      CAGR    const {r['CAGR_a']:.2f}%  breadth {r['CAGR_b']:.2f}%"
          f"   difference {r['dCAGR']:+.2f} points")
    t3 = pd.DataFrame(t3_rows)

    # --------------------------------------------------------------- verdict
    passed = {"T1 seed robustness (Sharpe)": ok_sharpe,
              f"T1 seed robustness (MaxDD > {DD_BAR:.0f} pt)": ok_dd,
              "T2 sub-period stability (Sharpe)": ok2}
    n_ok = sum(passed.values())
    W("\n" + "=" * 104)
    W(f" VERDICT -- {U['label']} ({u})")
    W("=" * 104)
    for k, v in passed.items():
        W(f"    {'PASS' if v else 'FAIL'}   {k}")
    W(f"\n    {n_ok} of {len(passed)} gated criteria hold.")
    W(f"    {'PASS' if n_ok == len(passed) else 'FAIL'} on this universe.")
    W("    T3 did not enter this verdict.")
    if n_ok != len(passed):
        W("\n    A FAIL means the mechanism setting deployment for every published")
        W("    v2 and v4 number on this universe is not robust here. Per the spec,")
        W("    a disagreement between universes is reported as a disagreement and")
        W("    is not resolved toward whichever universe looks better.")

    M = U["metrics"]
    t1.to_csv(M / "breadth_live_t1.csv", index=False)
    t2.to_csv(M / "breadth_live_t2.csv", index=False)
    t3.to_csv(M / "breadth_live_t3.csv", index=False)
    params = {"universe": u, "label": U["label"],
              "window": [str(BT_START_DATE.date()), str(BT_END_DATE.date())],
              "seed_sets": SEED_SETS, "dd_bar_points": DD_BAR,
              "dd_bar_note": "underived; copied from the 58's suite, not recalibrated",
              "criteria": {k: bool(v) for k, v in passed.items()},
              "verdict": "PASS" if n_ok == len(passed) else "FAIL",
              "t3_gated": False,
              "runtime_sec": round(time.perf_counter() - t_start, 1),
              "git": _git_state()}
    (M / "breadth_live_params.json").write_text(json.dumps(params, indent=2))
    out = ROOT / "diagnostics" / f"breadth_live_{u}.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(f"\n  saved -> {M/'breadth_live_t1.csv'}")
    print(f"           {M/'breadth_live_t2.csv'}")
    print(f"           {M/'breadth_live_t3.csv'}")
    print(f"           {M/'breadth_live_params.json'}")
    print(f"           {out}")
    print(f"  runtime {params['runtime_sec']/60:.1f} min")


if __name__ == "__main__":
    main()
