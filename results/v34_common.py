"""
v34_common.py -- the four-arm pro-vol measurement, shared by both live engines.

WHY THIS IS ONE MODULE AND NOT TWO COPIES
    engine_v2_final_n100.py and engine_v2_final_mid.py both need the identical
    four-arm block. Pasting it into each is how the engine and the Nautilus port
    drifted apart before. One implementation, imported twice, cannot drift.

    The spec (experiments/V34_SPEC.txt) requires the four arms to run in the SAME
    process on the SAME panel, dates and seeds. That is satisfied because each
    engine builds its panel once and hands the already-built objects to run_v34();
    nothing is re-read or re-derived here.

v1 AND v2 ARE NOT RECOMPUTED
    The caller has already run them to write v2FINAL_*. Those exact curves are
    passed in, so v1 and v2 in v34_comparison.csv are literally the same series as
    v2FINAL_equity.csv rather than a second run that happens to agree. Only v3 and
    v4 are computed here.

WHAT metrics() DOES NOT GIVE, AND WHY IT IS EXTENDED HERE RATHER THAN CHANGED
    engine_core.metrics() returns Config, CAGR%, Sharpe, Sortino, MaxDD%, Calmar,
    Trades, TC_Rs. The spec also wants annualised volatility%, average deployed%
    and final equity. metrics() is NOT modified: it writes v2FINAL_comparison.csv,
    whose columns must not move. The three extra columns are added on top here.

English only. Nothing printed here is hardcoded; every figure comes from the run.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from engine_core import metrics

TRADING_DAYS = 252


def ann_vol_pct(eq):
    """Annualised volatility of the daily returns of an equity curve, in percent."""
    r = eq.pct_change().dropna()
    return round(float(r.std() * np.sqrt(TRADING_DAYS) * 100), 2)


def arm_row(eq, label, tc=0, ntr=0, deployed_pct=100.0):
    """metrics() plus the three columns the spec asks for that it does not carry."""
    m = metrics(eq, label, tc, ntr)
    m["AnnVol%"] = ann_vol_pct(eq)
    m["Deployed%"] = round(float(deployed_pct), 1)
    m["FinalEquity"] = round(float(eq.iloc[-1]), 2)
    return m


def held_and_skips(audit, halves=None):
    """(mean names held per rebalance, cash-short skip count) from an audit dict.

    THESE TWO COLUMNS EXIST BECAUSE SIZING TURNED OUT TO CHANGE THE PORTFOLIO.
    Selection is rank-based and identical across arms -- verified, the top-8 target
    sets match on all 92 rebalances. But `invest_val` is computed over the WHOLE
    portfolio while new entrants are funded from CASH ALONE, so when the new names'
    combined target exceeds available cash the tail of the score-descending buy
    loop is skipped. Pro-vol hits that more often than inverse-vol. Without these
    columns a reader of v34_comparison.csv would assume v1 and v3 held the same
    names. They did not. See KNOWN_ISSUES.md.

    halves=None gives the full period; otherwise (y0, y1) restricts to one half.
    """
    dec = pd.DataFrame(audit["decisions"])
    hold = pd.DataFrame(audit["holdings"])
    skip = pd.DataFrame(audit["skipped"])
    if len(dec) == 0:
        return float("nan"), 0
    rb = pd.to_datetime(dec["decided_on"])
    if halves is not None:
        y0, y1 = halves
        rb = rb[(rb.dt.year >= y0) & (rb.dt.year <= y1)]
    if len(hold):
        h = hold[pd.to_datetime(hold["date"]).isin(rb)]
        mean_held = float(h.groupby("date")["symbol"].nunique().mean()) if len(h) else float("nan")
    else:
        mean_held = float("nan")
    if len(skip):
        s = skip[(skip["side"] == "BUY") & (skip["reason"] == "cash short (before TC)")]
        if halves is not None:
            sd = pd.to_datetime(s["date"])
            s = s[(sd.dt.year >= y0) & (sd.dt.year <= y1)]
        n_skip = int(len(s))
    else:
        n_skip = 0
    return mean_held, n_skip


def sub_rows(curves, halves, audits=None):
    """One row per (arm, half). Every cell carries CAGR and volatility.

    Each half is sliced FROM THE ARM'S OWN CURVE, which is already restricted to
    the backtest window, so the late half ends on the window's last day rather
    than on the last day of the price panel.
    """
    rows = []
    for hname, y0, y1 in halves:
        for label, eq, dep in curves:
            s = eq[(eq.index.year >= y0) & (eq.index.year <= y1)]
            if len(s) < 3:
                continue
            m = metrics(s, label)
            mh, nsk = (float("nan"), "")
            if audits and label in audits:
                mh, nsk = held_and_skips(audits[label], (y0, y1))
            rows.append({"Period": hname, "Config": label,
                         "CAGR%": m["CAGR%"], "AnnVol%": ann_vol_pct(s),
                         "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"],
                         "Deployed%": round(float(dep), 1),
                         "MeanNamesHeld": (round(mh, 2) if mh == mh else ""),
                         "CashShortSkips": nsk,
                         "FirstDate": str(s.index[0].date()),
                         "LastDate": str(s.index[-1].date()),
                         "Days": len(s)})
    return pd.DataFrame(rows)


def _git_state():
    """Describe the tree the run actually happened on, dirt included.

    Recording a bare commit hash was misleading: the working tree had roughly two
    dozen modified files, so the hash pointed at a tree that did not describe the
    run. A field pointing at the wrong tree is worse than an absent field, so this
    reports the commit AND whether the tree was dirty AND how many files differed.
    """
    def _run(args):
        try:
            r = subprocess.run(["git"] + args, capture_output=True, text=True,
                               timeout=10)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None

    head = _run(["rev-parse", "HEAD"])
    status = _run(["status", "--porcelain"])
    if head is None or status is None:
        return {"commit": None,
                "note": "git unavailable; the tree this ran on is not recorded"}
    modified = [l for l in status.splitlines() if l.strip()]
    dirty = len(modified) > 0
    return {"commit": head.strip(),
            "working_tree_dirty": dirty,
            "modified_or_untracked_files": len(modified),
            "note": ("the commit alone does NOT describe this run: the working "
                     "tree had uncommitted changes when it was produced"
                     if dirty else
                     "working tree clean; the commit describes this run exactly")}


def run_v34(M, universe_label, universe_tag, px, op, sc, bd, pc, mom20, port_vol,
            tv, backtest_exposure, v1_eq, v1_tc, v1_n, v2_eq, v2_tc, v2_n, v2_expo,
            start_capital, halves, consts, v1_audit=None):
    """Run v3 and v4, assemble all four arms plus buy & hold, write the outputs."""
    def _blank():
        return {k: [] for k in ("holdings", "summary", "trades",
                                "ranking", "decisions", "skipped")}

    # v2 is re-run purely to obtain its audit for the two diagnostic columns. This
    # is safe: passing an audit dict was verified to leave the equity curve, the
    # transaction cost and the trade count bit-identical, so the reported v2 row
    # still comes from the caller's original curve, not from this run.
    a2 = _blank()
    backtest_exposure(px, op, sc, bd, pc, mom20, port_vol, mode="breadth",
                      target_vol=tv, sizing="invvol", audit=a2)

    # --- the two new arms, same panel and dates as v1/v2 ---
    a3, a4 = _blank(), _blank()
    v3_eq, v3_tc, v3_n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                              mode="none", target_vol=tv,
                                              sizing="provol", audit=a3)
    v4_eq, v4_tc, v4_n, v4_expo = backtest_exposure(px, op, sc, bd, pc, mom20,
                                                    port_vol, mode="breadth",
                                                    target_vol=tv, sizing="provol",
                                                    audit=a4)
    bh = start_capital * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    curves = [
        ("v1 invvol, 100% invested", v1_eq, 100.0),
        ("v2 invvol, breadth-scaled", v2_eq, v2_expo * 100),
        ("v3 provol, 100% invested", v3_eq, 100.0),
        ("v4 provol, breadth-scaled", v4_eq, v4_expo * 100),
        ("buy & hold equal-weight", bh, 100.0),
    ]

    audits = {"v1 invvol, 100% invested": v1_audit,
              "v2 invvol, breadth-scaled": a2,
              "v3 provol, 100% invested": a3,
              "v4 provol, breadth-scaled": a4}
    audits = {k: v for k, v in audits.items() if v is not None}

    rows = [
        arm_row(v1_eq, "v1 invvol, 100% invested", v1_tc, v1_n, 100.0),
        arm_row(v2_eq, "v2 invvol, breadth-scaled", v2_tc, v2_n, v2_expo * 100),
        arm_row(v3_eq, "v3 provol, 100% invested", v3_tc, v3_n, 100.0),
        arm_row(v4_eq, "v4 provol, breadth-scaled", v4_tc, v4_n, v4_expo * 100),
        arm_row(bh, "buy & hold equal-weight", 0, 0, 100.0),
    ]
    for r in rows:
        if r["Config"] in audits:
            mh, nsk = held_and_skips(audits[r["Config"]])
            r["MeanNamesHeld"] = round(mh, 2)
            r["CashShortSkips"] = nsk
        else:
            # buy & hold holds the whole universe every day: not-applicable,
            # not unmeasured. Written as an empty cell so pandas does not
            # coerce the column to float and render it as NaN.
            r["MeanNamesHeld"] = ""
            r["CashShortSkips"] = ""
    comp = pd.DataFrame(rows)
    comp.to_csv(M / "v34_comparison.csv", index=False)

    subs = sub_rows(curves, halves, audits)
    subs.to_csv(M / "v34_subperiods.csv", index=False)

    pd.DataFrame({"date": bd,
                  "v1_invvol_none": v1_eq.values,
                  "v2_invvol_breadth": v2_eq.values,
                  "v3_provol_none": v3_eq.values,
                  "v4_provol_breadth": v4_eq.values,
                  "buyhold": bh.values}).to_csv(M / "v34_equity.csv", index=False)

    (M / "v34_params.json").write_text(json.dumps({
        "universe": universe_label,
        "universe_tag": universe_tag,
        "window_start": str(bd[0].date()),
        "window_end": str(bd[-1].date()),
        "trading_days": int(len(bd)),
        "arms": {"v1": "invvol + mode=none", "v2": "invvol + mode=breadth",
                 "v3": "provol + mode=none", "v4": "provol + mode=breadth"},
        "reference": "equal-weight buy & hold of the same universe, same panel",
        "constants": consts,
        "git_state": _git_state(),
        "run_date": str(pd.Timestamp.today().date()),
        "spec": "experiments/V34_SPEC.txt",
    }, indent=2))

    # --- chart: four arms plus the reference on one axis ---
    fig, ax = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[2, 1])
    style = [("#1f77b4", "-"), ("#d62728", "-"),
             ("#2ca02c", "-"), ("#9467bd", "-"), ("#7f7f7f", "--")]
    for (lab, eq, dep), (c, ls) in zip(curves, style):
        m = metrics(eq, lab)
        ax[0].plot(eq.index, (eq / eq.iloc[0] - 1) * 100, lw=1.8, color=c, ls=ls,
                   label=f"{lab}  [inv {dep:.0f}%]  CAGR {m['CAGR%']}%  "
                         f"vol {ann_vol_pct(eq)}%  Sharpe {m['Sharpe']}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(
        f"{universe_label} -- four sizing/exposure arms plus equal-weight buy & hold\n"
        f"{bd[0].date()} to {bd[-1].date()}, {len(bd)} trading days. "
        f"All figures after Zerodha costs plus 0.15% slippage.\n"
        f"v1/v3 hold 100% invested; v2/v4 scale exposure by breadth. "
        f"Sizing is the only other difference: 1/vol against vol.", fontsize=9)
    ax[0].legend(loc="upper left", fontsize=8)
    ax[0].grid(alpha=.3)

    for (lab, eq, dep), (c, ls) in zip(curves, style):
        d = (eq / eq.cummax() - 1) * 100
        ax[1].plot(eq.index, d, lw=1.2, color=c, ls=ls,
                   label=f"{lab} (max {d.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=7.5, ncol=2)
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(M / "chart_v34.png", dpi=150, bbox_inches="tight")
    plt.close()

    return comp, subs, curves
