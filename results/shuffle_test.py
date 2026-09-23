"""
shuffle_test.py -- is the return in the model, or in the mechanics?

SPEC: experiments/SHUFFLE_SPEC.txt, written before this file existed. The
permutation, the seed count, the statistic, the 0.05 bar and the verdict rule
were all fixed there before any number was produced.

THE NULL
    For each date independently, the non-NaN scores are permuted across the
    symbols that have one. Distribution per date preserved, eligibility
    preserved, ONLY the symbol-to-score mapping destroyed. Everything else --
    prices, dates, window, TOP_N, BUFFER, sizing, costs, execution -- is held
    bit for bit.

BREADTH IS INVARIANT UNDER THE SHUFFLE
    test_exposure.py:149-150 computes exposure from mom20 alone and never reads
    a score. So the breadth arms deploy the same fraction on the same dates in
    the null as in the real arm. The shuffle tests SELECTION and nothing else.
    It cannot test breadth, and whatever breadth contributes is present on both
    sides of the comparison.

WHAT A PASS CANNOT SAY, restated here because it will be read here
    It does not correct for the 26-trial denominator; it does not address
    survivorship, because THE NULL CARRIES THE SAME BIAS -- random portfolios are
    drawn from the same backfilled universe; and it does not make the return
    tradable. See the spec.

English only. No verdict string is hardcoded.
"""
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd

import config
from engine_core import precompute, metrics
import test_exposure
from test_exposure import backtest_exposure
from universes.registry import REGISTRY
from v34_common import ann_vol_pct, _git_state
import profiles as _prof            # the run's execution-realism profile

N_SHUFFLES = 100
VOL_WIN = 60
ALPHA = 0.05                      # the bar, fixed in the spec before any number
ARMS = [("v1", "invvol", "none"), ("v2", "invvol", "breadth"),
        ("v3", "provol", "none"), ("v4", "provol", "breadth")]
GATED_ARMS = ("v1", "v2")         # v2 ships; v1 is the clean selection test

# PATHS AND SYMBOLS COME FROM universes/registry.py -- the single definition.
# The LABEL stays local: it is printed into diagnostics/shuffle_verdict.txt and
# written into shuffle_params.json, and the sibling scripts spell the same two
# universes two other ways. Labels are presentation; paths are facts.
# Order is load-bearing -- the verdict accumulates universe by universe.
LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {
    u.tag: {"perm": u.score_cache,
            "metrics_dir": u.metrics_dir, "symbols": u.symbols,
            "label": LABELS[u.tag]}
    for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])
}


def load_panel(cfg, uni):
    """Read the production panel and PROVE which universe it is, from the file."""
    # SAME GUARDS AS THE RUN THAT PRODUCED THE ARTEFACT THIS COMPARES
    # AGAINST. A script that recomputes and then checks itself against a
    # published row must run under the production guards, or it measures a
    # different engine. rebal_cadence_sweep.py failed exactly this way:
    # mid v3 AnnVol% recomputed 24.89 against 24.88 published.
    import engine_core as _ec
    from universes.registry import REGISTRY as _REG
    _ec.set_tradeability(_REG[uni])
    src = config.require_cache(cfg["perm"], what=f"{uni} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    got, want = set(p["symbol"].unique()), cfg["symbols"]()
    if got != want:
        raise SystemExit(
            f"{uni}: panel symbol set does not match the universe "
            f"({len(got)} vs {len(want)}). Refusing to report a verdict.")
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return src, px, op, sc


def permute_scores(sc, seed):
    """Cross-sectional permutation: shuffle scores across symbols within a date.

    Only the non-NaN entries of a row are permuted, so the SET of scorable names
    on each date is unchanged and the eligibility guard behaves identically.
    """
    rng = np.random.default_rng(seed)
    V = sc.to_numpy(dtype=np.float64, copy=True)
    for i in range(V.shape[0]):
        row = V[i]
        m = ~np.isnan(row)
        if m.sum() > 1:
            row[m] = rng.permutation(row[m])
    return pd.DataFrame(V, index=sc.index, columns=sc.columns)


def run_arm(sizing, mode, px, op, sc, bd, pc, mom20, port_vol, tv):
    test_exposure.TOP_N = config.TOP_N
    test_exposure.BUFFER = config.BUFFER
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See profiles.research_only.
    eq, tc, ntr, expo = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                          mode=mode, target_vol=tv, sizing=sizing, participation_cap=_prof.research_only(__name__))
    m = metrics(eq, "arm", tc, ntr)
    return {"CAGR%": float(m["CAGR%"]), "Sharpe": float(m["Sharpe"]),
            "MaxDD%": float(m["MaxDD%"]), "AnnVol%": ann_vol_pct(eq),
            "Trades": int(ntr), "Deployed%": round(float(expo) * 100, 1),
            "Final": float(eq.iloc[-1])}


def pval(null_vals, real, higher_is_better=True):
    """One-sided permutation p-value with the finite-sample +1 correction.

    Without the correction a zero count reports p = 0, which no permutation test
    of finite N can support.
    """
    a = np.asarray(null_vals, dtype=float)
    beat = int((a >= real).sum()) if higher_is_better else int((a <= real).sum())
    return (1 + beat) / (len(a) + 1), beat


def quant(a):
    a = np.asarray(a, dtype=float)
    q = np.percentile(a, [0, 5, 25, 50, 75, 95, 100])
    return dict(zip(["min", "p5", "p25", "median", "p75", "p95", "max"],
                    [round(float(x), 2) for x in q]))


def shipped_v2(metrics_dir):
    """Published v2 figures, READ FROM THE ARTEFACT, never typed in."""
    f = Path(metrics_dir) / "v34_comparison.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    r = d[d["Config"].astype(str).str.startswith("v2")]
    if not len(r):
        return None
    r = r.iloc[0]
    return {"CAGR%": float(r["CAGR%"]), "Sharpe": float(r["Sharpe"]),
            "MaxDD%": float(r["MaxDD%"])}


def run_universe(uni, cfg, out):
    W = out.append
    src, px, op, sc = load_panel(cfg, uni)
    bd = px.index[(px.index >= config.BT_START_DATE)
                  & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()
    bh = 1_000_000 * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    mbh = metrics(bh, "bh")

    W("=" * 100)
    W(f" SHUFFLE TEST -- {cfg['label']} ({uni})")
    W("=" * 100)
    W("")
    W(f"  score panel   {src}")
    W(f"  symbol set    {px.shape[1]} names, asserted equal to the configured universe")
    W(f"  window        {bd[0].date()} .. {bd[-1].date()}   {len(bd)} trading days")
    W(f"  engine        test_exposure.backtest_exposure (SHIPPING)")
    W(f"  null          {N_SHUFFLES} cross-sectional score permutations, seeds 0..{N_SHUFFLES-1}")
    W(f"  bar           p < {ALPHA} on CAGR, one-sided, fixed in the spec")
    W("")

    real = {tag: run_arm(sz, md, px, op, sc, bd, pc, mom20, port_vol, tv)
            for tag, sz, md in ARMS}

    ship = shipped_v2(cfg["metrics_dir"])
    gate_ok = ship is not None
    if ship is None:
        W("  IDENTITY GATE: v34_comparison.csv absent -- cannot check the real v2")
        W("  against the shipped figure. No shuffle result is reported.")
    else:
        W("  IDENTITY GATE -- the real v2 arm must reproduce the shipped v2")
        for k in ("CAGR%", "Sharpe", "MaxDD%"):
            ok = abs(real["v2"][k] - ship[k]) < 0.005
            gate_ok = gate_ok and ok
            W(f"    {k:<8} this run {real['v2'][k]:>9.2f}   shipped {ship[k]:>9.2f}"
              f"   {'ok' if ok else 'MISMATCH'}")
    if not gate_ok:
        return {"uni": uni, "gate_ok": False}

    # ---- the null ---------------------------------------------------------
    draws = []
    for s in range(N_SHUFFLES):
        shuf = permute_scores(sc, s)
        for tag, sz, md in ARMS:
            r = run_arm(sz, md, px, op, shuf, bd, pc, mom20, port_vol, tv)
            r.update({"seed": s, "arm": tag})
            draws.append(r)
    D = pd.DataFrame(draws)

    W("")
    W(f"  equal-weight buy & hold (100% invested, same panel and window):")
    W(f"    CAGR {mbh['CAGR%']:.2f}%   Sharpe {mbh['Sharpe']:.2f}   MaxDD {mbh['MaxDD%']:.2f}%")
    W("")
    W("-" * 100)
    W(" CAGR -- THE GATED STATISTIC")
    W("-" * 100)
    W(f" {'arm':<5}{'real':>9}{'null med':>10}{'null p5':>9}{'null p95':>10}"
      f"{'null max':>10}{'beat':>7}{'p':>9}{'effect':>9}{'gated':>7}")
    rows = []
    for tag, sz, md in ARMS:
        a = D[D["arm"] == tag]["CAGR%"].to_numpy()
        q = quant(a)
        p, beat = pval(a, real[tag]["CAGR%"])
        eff = real[tag]["CAGR%"] - q["median"]
        rows.append({"arm": tag, "sizing": sz, "mode": md,
                     "real_CAGR%": round(real[tag]["CAGR%"], 2),
                     "null_median_CAGR%": q["median"], "null_p5": q["p5"],
                     "null_p95": q["p95"], "null_max": q["max"],
                     "n_beat": beat, "p_CAGR": round(p, 4),
                     "effect_pt": round(eff, 2),
                     "gated": tag in GATED_ARMS})
        W(f" {tag:<5}{real[tag]['CAGR%']:>9.2f}{q['median']:>10.2f}{q['p5']:>9.2f}"
          f"{q['p95']:>10.2f}{q['max']:>10.2f}{beat:>7}{p:>9.4f}{eff:>+9.2f}"
          f"{('yes' if tag in GATED_ARMS else 'no'):>7}")

    W("")
    W("-" * 100)
    W(" REPORTED, NOT GATED -- Sharpe and MaxDD")
    W("-" * 100)
    W(f" {'arm':<5}{'realSh':>9}{'nullSh med':>12}{'p(Sh)':>9}"
      f"{'realDD':>9}{'nullDD med':>12}{'p(DD)':>9}{'deploy%':>9}")
    for tag, sz, md in ARMS:
        sa = D[D["arm"] == tag]["Sharpe"].to_numpy()
        da = D[D["arm"] == tag]["MaxDD%"].to_numpy()
        ps, _ = pval(sa, real[tag]["Sharpe"])
        pd_, _ = pval(da, real[tag]["MaxDD%"], higher_is_better=True)
        i = [r for r in rows if r["arm"] == tag][0]
        i.update({"real_Sharpe": round(real[tag]["Sharpe"], 2),
                  "null_median_Sharpe": round(float(np.median(sa)), 2),
                  "p_Sharpe": round(ps, 4),
                  "real_MaxDD%": round(real[tag]["MaxDD%"], 2),
                  "null_median_MaxDD%": round(float(np.median(da)), 2),
                  "p_MaxDD": round(pd_, 4),
                  "Deployed%": real[tag]["Deployed%"]})
        W(f" {tag:<5}{real[tag]['Sharpe']:>9.2f}{np.median(sa):>12.2f}{ps:>9.4f}"
          f"{real[tag]['MaxDD%']:>9.2f}{np.median(da):>12.2f}{pd_:>9.4f}"
          f"{real[tag]['Deployed%']:>9.1f}")

    # -- prediction 3, tested: does the null keep breadth's drawdown edge? ---
    W("")
    W("  PREDICTION 3, TESTED -- does the null keep breadth's drawdown advantage?")
    W("    The spec predicted it would, because exposure is score-independent.")
    n1 = float(np.median(D[D["arm"] == "v1"]["MaxDD%"]))
    n2 = float(np.median(D[D["arm"] == "v2"]["MaxDD%"]))
    W(f"    shuffled v1 median MaxDD {n1:.2f}   shuffled v2 median MaxDD {n2:.2f}")
    W(f"    the prediction is {'BORNE OUT' if n2 > n1 else 'NOT BORNE OUT'} on {uni}.")

    # -- prediction 4, reported: do shuffled arms beat buy & hold? ----------
    W("")
    W("  PREDICTION 4, REPORTED, NOT GATED -- do the MECHANICS carry return?")
    for tag, sz, md in ARMS:
        med = float(np.median(D[D["arm"] == tag]["CAGR%"]))
        W(f"    shuffled {tag} median CAGR {med:>7.2f}  vs buy & hold "
          f"{mbh['CAGR%']:>6.2f}   {'above' if med > mbh['CAGR%'] else 'below'}")
    W("    NOTE, AND IT MATTERS FOR HOW THIS IS READ: the breadth arms deploy")
    W(f"    about {real['v2']['Deployed%']:.0f}% while buy & hold is 100% invested, so a")
    W("    breadth arm below buy & hold on CAGR is not evidence of anything on")
    W("    its own. The null, which holds deployment identical, is the comparison")
    W("    that controls for this. Buy & hold is context, not a benchmark here.")

    md_ = Path(cfg["metrics_dir"])
    pd.DataFrame(rows).to_csv(md_ / "shuffle_summary.csv", index=False)
    D.to_csv(md_ / "shuffle_draws.csv", index=False)
    (md_ / "shuffle_params.json").write_text(json.dumps({
        "spec": "experiments/SHUFFLE_SPEC.txt", "universe": uni,
        "n_shuffles": N_SHUFFLES, "seeds": f"0..{N_SHUFFLES-1}",
        "alpha": ALPHA, "gated_statistic": "CAGR%", "gated_arms": list(GATED_ARMS),
        "permutation": "cross-sectional, non-NaN scores permuted within each date",
        "engine": "test_exposure.backtest_exposure (shipping)",
        "window_start": str(bd[0].date()), "window_end": str(bd[-1].date()),
        "trading_days": len(bd), "top_n": config.TOP_N, "buffer": config.BUFFER,
        "identity_gate_passed": True, "git": _git_state(),
    }, indent=2) + "\n")

    return {"uni": uni, "gate_ok": True, "rows": rows, "real": real,
            "bh": {"CAGR%": float(mbh["CAGR%"]), "Sharpe": float(mbh["Sharpe"])}}


def main():
    results, out_all = {}, []
    for uni, cfg in UNIVERSES.items():
        out = []
        res = run_universe(uni, cfg, out)
        results[uni] = res
        (ROOT / "diagnostics" / f"shuffle_{uni}.txt").write_text("\n".join(out) + "\n")
        out_all += out + [""]

    W = out_all.append
    W("=" * 100)
    W(" VERDICT -- rule fixed in experiments/SHUFFLE_SPEC.txt before any number existed")
    W("=" * 100)
    W("")
    if not all(r.get("gate_ok") for r in results.values()):
        W("  IDENTITY GATE FAILED. No shuffle result is reported.")
        (ROOT / "diagnostics" / "shuffle_verdict.txt").write_text("\n".join(out_all) + "\n")
        print("\n".join(out_all))
        return

    crit = []
    for uni, r in results.items():
        for row in r["rows"]:
            if row["arm"] in GATED_ARMS:
                crit.append({"uni": uni, "arm": row["arm"], "p": row["p_CAGR"],
                             "holds": row["p_CAGR"] < ALPHA,
                             "real": row["real_CAGR%"],
                             "median": row["null_median_CAGR%"],
                             "eff": row["effect_pt"], "beat": row["n_beat"]})
    W(f"  GATED: CAGR permutation p < {ALPHA}, one-sided, N = {N_SHUFFLES}")
    W("")
    W(f"  {'universe':<10}{'arm':<5}{'real CAGR':>11}{'null median':>13}"
      f"{'effect':>9}{'beat':>7}{'p':>9}{'':>6}")
    for c in crit:
        W(f"  {c['uni']:<10}{c['arm']:<5}{c['real']:>11.2f}{c['median']:>13.2f}"
          f"{c['eff']:>+9.2f}{c['beat']:>7}{c['p']:>9.4f}"
          f"{('holds' if c['holds'] else 'FAILS'):>6}")
    W("")
    all_hold = all(c["holds"] for c in crit)
    any_hold = any(c["holds"] for c in crit)
    W(f"  {sum(c['holds'] for c in crit)} of {len(crit)} gated criteria hold.")
    W("")
    if all_hold:
        W("  THE RETURN IS NOT REPRODUCED BY RANDOM SELECTION.")
        W("  Random scores, with every mechanic held identical, do not match the")
        W("  strategy's return on either gated arm on either universe.")
        W("")
        W("  THE CEILING, AND IT IS LOW. This does NOT validate the strategy:")
        W("    1. IT DOES NOT CORRECT FOR THE TRIAL DENOMINATOR. This configuration")
        W("       was chosen after at least 26 recorded trials on this same data.")
        W("       A small p here is NOT the probability that the strategy is noise.")
        W("    2. IT DOES NOT ADDRESS SURVIVORSHIP. THE NULL CARRIES THE SAME BIAS --")
        W("       every shuffled portfolio is drawn from the same backfilled index")
        W("       membership. This test passes just as easily on an inflated universe.")
        W("    3. IT DOES NOT MAKE THE RETURN TRADABLE. Synthetic fills, no market")
        W("       impact, no capital gains tax.")
        W("    4. IT DOES NOT TEST BREADTH. Exposure is invariant under the shuffle.")
    elif any_hold:
        f_ = [f"{c['uni']} {c['arm']}" for c in crit if not c["holds"]]
        h_ = [f"{c['uni']} {c['arm']}" for c in crit if c["holds"]]
        W("  SPLIT RESULT. THE DISAGREEMENT IS THE FINDING.")
        W(f"    holds: {', '.join(h_)}")
        W(f"    FAILS: {', '.join(f_)}")
        W("    Reported as a disagreement between arms and universes. NOT resolved")
        W("    toward whichever looks better, NOT averaged, NOT re-run at a changed")
        W("    bar. Where an arm fails, random selection reproduces its return and")
        W("    the alpha in that arm is not in the model.")
    else:
        W("  RANDOMISED SCORES REPRODUCE THE STRATEGY'S RETURNS ON EVERY GATED ARM.")
        W("  THE ALPHA IS NOT IN THE MODEL. The return is coming from the mechanics")
        W("  -- concentration into 8 names, inverse-vol sizing, breadth exposure and")
        W("  the universe itself -- all of which a random selector gets for free.")
        W("  No second shuffle design is run. The spec forbids searching for a null")
        W("  that stops rejecting.")
    W("")
    W("  THIS COUNTS AS A TRIAL and is entered in experiments/EXPERIMENTS.md")
    W("  whichever way it fell.")
    W("=" * 100)

    (ROOT / "diagnostics" / "shuffle_verdict.txt").write_text("\n".join(out_all) + "\n")
    print("\n".join(out_all))


if __name__ == "__main__":
    main()
