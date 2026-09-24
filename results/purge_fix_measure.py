"""
purge_fix_measure.py -- what is the purge leak worth?

SPEC: experiments/PURGE_FIX_SPEC.txt, written before this file existed. The
corrected purge, the embargo of 2 trading rows and its reason, the confounds and
the written prediction were all fixed there before any number was produced.

THE CORRECTION, ENTIRELY IN TRADING ROWS ON THE PANEL'S OWN CALENDAR

    j_max = i_first - HORIZON - EMBARGO      cut = cal[j_max]

so gap(j) = i_first - (j + HORIZON) >= EMBARGO for every training row, BY
CONSTRUCTION rather than by luck of the holiday calendar.

EMBARGO = 2. One row makes the label stop strictly before the first scored date;
the second puts it strictly before the close at i_first - 1, which is the BASE
PRICE of the scored period's first return. Not larger, because a bigger embargo
removes training rows and would conflate "leak removed" with "trained on less".

engine_core.py IS NOT MODIFIED. The corrected walk is implemented here.

THE CURRENT-PURGE SIDE IS THE SHIPPED SCORE PANEL ITSELF, not a re-fit of it, so
the comparison is against the artefact the recorded numbers actually came from.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import os
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import config
from engine_core import (HORIZON, PURGE, FEATS_V2, _fit_seed, precompute,
                         metrics)
import test_exposure
from test_exposure import backtest_exposure
from universes.registry import REGISTRY, certified
from v34_common import ann_vol_pct
import profiles as _prof            # the run's execution-realism profile
from config import read_table  # the one CSV/parquet reader: config.read_table
from numerics import rolling_std  # platform-identical variance: results/numerics.py

SEEDS = [7, 42, 99, 1, 2, 3, 11, 22, 33, 101]
EMBARGO = 2
VOL_WIN = 60
ARMS = [("v1", "invvol", "none"), ("v2", "invvol", "breadth"),
        ("v3", "provol", "none"), ("v4", "provol", "breadth")]

# ALL FOUR PANEL PATHS, THE METRICS DIRECTORY AND THE SYMBOL LIST come from
# universes/registry.py -- the single definition. This registry had the widest
# key vocabulary of the nineteen (raw / raw_tmp / sc / sc_tmp / md / syms /
# label); the facts behind those seven names are four paths, a directory and a
# symbol list, and they are now named once.
#
# The LABEL stays local: it is printed into diagnostics/purge_fix_measure.txt.
# Order is load-bearing -- the measurement is reported universe by universe.
LABELS = {u.tag: u.display_name for u in certified()}
UNIVERSES = {
    u.tag: {"raw": u.raw_cache,
            "sc": u.score_cache,
            "md": u.metrics_dir, "syms": u.symbols, "label": LABELS[u.tag]}
    for u in certified()
}


def corrected_cut(cal, pos, first, horizon=HORIZON, embargo=EMBARGO):
    """Last usable training date, in TRADING ROWS. Cannot underflow."""
    j = pos[np.datetime64(first)] - horizon - embargo
    return pd.Timestamp(cal[j]) if j >= 0 else None


# The column set the shipping score panel carries. The corrected run writes the
# SAME schema, verified against the production artefact rather than assumed.
SCORE_PANEL_COLS = ["date", "symbol", "open", "close", "score"]
# Columns score_corrected must find in the raw panel to do its work at all.
REQUIRED_RAW_COLS = ["date", "symbol", "open", "close", "y_rank", "scorable"]


def assert_columns(df, required, what):
    """Verify the column set FROM THE FILE before using it.

    The first run of this script assumed the raw panel carried high, low and
    volume. It does not -- they are consumed during feature construction and not
    retained. The assumption was not checked, and the KeyError landed AFTER the
    scoring loop, discarding ~25 minutes of refits. Universe membership is
    verified from the file everywhere else in this project; columns now are too.
    """
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(
            f"{what}: required columns absent: {missing}\n"
            f"  present: {list(df.columns)}\n"
            f"  Refusing to run. A missing column must stop the job before the")
    return True


def score_corrected(p, cache, full_cache):
    """score_monthly with the trading-row purge. Same seeds, same fits, same
    ensemble mean -- only `cut` differs from engine_core.score_monthly.

    THE SCORED FRAME IS WRITTEN TO DISK THE INSTANT THE LOOP ENDS, before any
    reshape or column selection, so that a failure downstream cannot cost the
    refits again.
    """
    if Path(cache).exists():
        return read_table(cache, parse_dates=["date"])
    if Path(full_cache).exists():
        # The loop completed on a previous attempt; recover it rather than refit.
        print(f"      recovering completed scoring from {full_cache}", flush=True)
        p = read_table(full_cache, parse_dates=["date"])
        assert_columns(p, SCORE_PANEL_COLS, "recovered scored panel")
        out = p[SCORE_PANEL_COLS]
        out.to_csv(cache, index=False)
        return out
    assert_columns(p, REQUIRED_RAW_COLS, "raw panel")
    p = p.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["score"] = np.nan
    p["ym"] = p["date"].dt.to_period("M")
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}
    months = sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique())
    for k, ym in enumerate(months):
        first = p.loc[p.ym == ym, "date"].min()
        cut = corrected_cut(cal, pos, first)
        if cut is None:
            continue
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        te = (p["ym"] == ym) & p["scorable"]
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        Xtr = p.loc[tr, FEATS_V2].to_numpy()
        ytr = p.loc[tr, "y_rank"].to_numpy()
        Xte = p.loc[te, FEATS_V2].to_numpy()
        pr = Parallel(n_jobs=min(len(SEEDS), os.cpu_count() or 1),
                      backend="loky")(delayed(_fit_seed)(sd, Xtr, ytr, Xte)
                                      for sd in SEEDS)
        p.loc[te, "score"] = np.mean(pr, axis=0)
        if k % 20 == 0:
            print(f"      month {k+1}/{len(months)} {ym} train {tr.sum():,}",
                  flush=True)
    # PERSIST FIRST. Nothing between the end of the loop and this line.
    p.to_csv(full_cache, index=False)
    print(f"      scoring complete, persisted to {full_cache}", flush=True)
    # Only now reshape. A failure below costs a reshape, not the refits.
    assert_columns(p, SCORE_PANEL_COLS, "scored panel")
    out = p[SCORE_PANEL_COLS]
    out.to_csv(cache, index=False)
    return out


def arms_from_scores(sp, cfg):
    px = sp.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = sp.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = sp.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE)
                  & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
    tv = pv.loc[bd].median()
    out = {}
    for tag, sizing, mode in ARMS:
        test_exposure.TOP_N, test_exposure.BUFFER = config.TOP_N, config.BUFFER
        # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
        # apply a participation cap even if one were selected; research_only()
        # makes that a statement rather than an accident, and STOPS the run if
        # --profile ever reaches here. See profiles.research_only.
        eq, tc, n, expo = backtest_exposure(px, op, sc, bd, pc, mom20, pv,
                                            mode=mode, target_vol=tv,
                                            sizing=sizing, participation_cap=_prof.research_only(__name__))
        m = metrics(eq, tag, tc, n)
        yearly = {}
        for y, g in eq.groupby(eq.index.year):
            if len(g) > 2:
                yearly[int(y)] = round(float((g.iloc[-1] / g.iloc[0] - 1) * 100), 2)
        out[tag] = {"CAGR%": float(m["CAGR%"]), "Sharpe": float(m["Sharpe"]),
                    "MaxDD%": float(m["MaxDD%"]), "Trades": int(n),
                    "AnnVol%": ann_vol_pct(eq), "yearly": yearly}
    return out, bd


def verify_gaps(p, W, tag):
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}
    p = p.copy(); p["ym"] = p["date"].dt.to_period("M")
    rows = []
    for ym in sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique()):
        first = p.loc[p.ym == ym, "date"].min()
        i_first = pos[np.datetime64(first)]
        if tag == "current":
            cut = first - pd.Timedelta(days=PURGE)
        else:
            cut = corrected_cut(cal, pos, first)
            if cut is None:
                continue
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        if tr.sum() < 5000:
            continue
        latest = p.loc[tr, "date"].max()
        j = min(pos[np.datetime64(latest)] + HORIZON, len(cal) - 1)
        rows.append({"month": str(ym), "gap_trading_days": i_first - j,
                     "train_rows": int(tr.sum())})
    D = pd.DataFrame(rows)
    g = D["gap_trading_days"]
    W(f"    {tag:<10} months {len(D):>4}   min {g.min():>3}   median "
      f"{g.median():>5.1f}   max {g.max():>3}   "
      f"months<=0 {int((g <= 0).sum()):>3}   train rows total {D['train_rows'].sum():,}")
    return D


def run(uni, cfg, W):
    W("=" * 100)
    W(f" PURGE FIX -- {cfg['label']} ({uni})")
    W("=" * 100)
    W("")
    # SAME GUARDS AS THE RUN THAT PRODUCED THE ARTEFACT THIS COMPARES
    # AGAINST. A script that recomputes and then checks itself against a
    # published row must run under the production guards, or it measures a
    # different engine. rebal_cadence_sweep.py failed exactly this way:
    # midcap150 v3 AnnVol% recomputed 24.89 against 24.88 published.
    import engine_core as _ec
    from universes.registry import REGISTRY as _REG
    _ec.set_tradeability(_REG[uni])
    raw = read_table(config.require_cache(cfg["raw"],
                                           what=f"{uni} raw panel"),
                      parse_dates=["date"])
    got, want = set(raw["symbol"].unique()), cfg["syms"]()
    if got != want:
        raise SystemExit(f"{uni}: raw panel universe mismatch")
    cur_sp = read_table(config.require_cache(cfg["sc"],
                                              what=f"{uni} score panel"),
                         parse_dates=["date"])
    assert_columns(cur_sp, SCORE_PANEL_COLS, f"{uni} production score panel")
    assert_columns(raw, REQUIRED_RAW_COLS, f"{uni} raw panel")

    W("  PURGE VERIFICATION -- gap in TRADING ROWS, all scoring months")
    Dc = verify_gaps(raw, W, "current")
    Dn = verify_gaps(raw, W, "corrected")
    ok = (Dn["gap_trading_days"].min() >= EMBARGO)
    W(f"    EMBARGO = {EMBARGO}. corrected minimum >= embargo: "
      f"{'YES' if ok else 'NO'}")
    W("")

    print(f"  [{uni}] re-scoring with the corrected purge...", flush=True)
    new_sp = score_corrected(raw, f"/tmp/PURGEFIX_{uni}_scores.csv",
                             f"/tmp/PURGEFIX_{uni}_scored_full.csv")

    cur, bd = arms_from_scores(cur_sp, cfg)
    new, _ = arms_from_scores(new_sp, cfg)

    # identity gate against the recorded artefact
    v34 = read_table(Path(cfg["md"]) / "v34_comparison.csv")
    r = v34[v34["Config"].astype(str).str.startswith("v2")].iloc[0]
    gate = all(abs(cur["v2"][k] - float(r[k])) < 0.005
               for k in ("CAGR%", "Sharpe", "MaxDD%"))
    W(f"  IDENTITY GATE -- current-purge v2 vs v34_comparison.csv: "
      f"{'ok' if gate else 'MISMATCH'}")
    for k in ("CAGR%", "Sharpe", "MaxDD%"):
        W(f"    {k:<8} this run {cur['v2'][k]:>9.2f}   recorded {float(r[k]):>9.2f}")
    W("")
    if not gate:
        W("  NO DIFFERENCE IS REPORTED. The harness does not reproduce the")
        W("  recorded result, so any difference would be uninterpretable.")
        return None

    W("-" * 100)
    W(" HEADLINE -- current purge (32 calendar days) vs corrected (trading rows)")
    W("-" * 100)
    W(f" {'arm':<4}{'CAGR cur':>10}{'CAGR new':>10}{'dCAGR':>8}"
      f"{'Sh cur':>8}{'Sh new':>8}{'dSh':>7}"
      f"{'DD cur':>9}{'DD new':>9}{'dDD':>7}{'trd cur':>9}{'trd new':>9}")
    rows = []
    for tag, _, _ in ARMS:
        c, n = cur[tag], new[tag]
        rows.append({"arm": tag,
                     "CAGR_current": round(c["CAGR%"], 2), "CAGR_corrected": round(n["CAGR%"], 2),
                     "dCAGR": round(n["CAGR%"] - c["CAGR%"], 2),
                     "Sharpe_current": round(c["Sharpe"], 2), "Sharpe_corrected": round(n["Sharpe"], 2),
                     "dSharpe": round(n["Sharpe"] - c["Sharpe"], 2),
                     "MaxDD_current": round(c["MaxDD%"], 2), "MaxDD_corrected": round(n["MaxDD%"], 2),
                     "dMaxDD": round(n["MaxDD%"] - c["MaxDD%"], 2),
                     "Trades_current": c["Trades"], "Trades_corrected": n["Trades"]})
        W(f" {tag:<4}{c['CAGR%']:>10.2f}{n['CAGR%']:>10.2f}{n['CAGR%']-c['CAGR%']:>+8.2f}"
          f"{c['Sharpe']:>8.2f}{n['Sharpe']:>8.2f}{n['Sharpe']-c['Sharpe']:>+7.2f}"
          f"{c['MaxDD%']:>9.2f}{n['MaxDD%']:>9.2f}{n['MaxDD%']-c['MaxDD%']:>+7.2f}"
          f"{c['Trades']:>9}{n['Trades']:>9}")
    pd.DataFrame(rows).to_csv(Path(cfg["md"]) / "purge_fix_headline.csv", index=False)

    W("")
    W("-" * 100)
    W(" PER YEAR -- return %, current vs corrected. AFFECTED = a leaking month")
    W(" falls in that year (2019, 2020, 2021, 2023, 2026 inside the window).")
    W("-" * 100)
    affected = {2019, 2020, 2021, 2023, 2026}
    years = sorted(cur["v1"]["yearly"].keys())
    yrows = []
    for tag, _, _ in ARMS:
        if tag not in ("v1", "v2"):
            continue
        W(f"  {tag}")
        W(f"    {'year':<7}{'current':>10}{'corrected':>11}{'diff':>9}   flag")
        for y in years:
            c = cur[tag]["yearly"].get(y)
            n = new[tag]["yearly"].get(y)
            if c is None or n is None:
                continue
            yrows.append({"arm": tag, "year": y, "current": c, "corrected": n,
                          "diff": round(n - c, 2), "affected": y in affected})
            W(f"    {y:<7}{c:>10.2f}{n:>11.2f}{n-c:>+9.2f}   "
              f"{'AFFECTED' if y in affected else ''}")
    Y = pd.DataFrame(yrows)
    Y.to_csv(Path(cfg["md"]) / "purge_fix_yearly.csv", index=False)
    Dn.to_csv(Path(cfg["md"]) / "purge_fix_gaps.csv", index=False)

    W("")
    W("  IS THE DIFFERENCE CONCENTRATED IN THE AFFECTED YEARS?")
    for tag in ("v1", "v2"):
        s = Y[Y["arm"] == tag]
        a = s[s["affected"]]["diff"].abs().mean()
        u = s[~s["affected"]]["diff"].abs().mean()
        W(f"    {tag}  mean |diff| in AFFECTED years {a:.2f}   "
          f"in unaffected years {u:.2f}   ratio {a/u if u else float('nan'):.2f}")
    return {"cur": cur, "new": new, "yearly": Y}


def main():
    out = []
    res = {}
    for uni, cfg in UNIVERSES.items():
        res[uni] = run(uni, cfg, out.append)
        out.append("")
    (ROOT / "diagnostics" / "purge_fix_measure.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    # SENTINEL, written as the final action of a successful run. A waiter checks
    # for this rather than for a process name, so a crash cannot look like success.
    Path("/tmp/PURGEFIX_DONE").write_text("ok\n")
    print("SENTINEL /tmp/PURGEFIX_DONE written", flush=True)


if __name__ == "__main__":
    main()
