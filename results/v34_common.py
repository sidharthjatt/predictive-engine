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


def _window_label(eq=None):
    """One line naming the window every figure on the chart belongs to.

    ADDED 2026-09-02. Three different trade counts on three different windows
    once appeared on one chart with none of them labelled: 981 research fills on
    the 1,836-day window, 978 port fills on the same window, and 997 fills from a
    depth study on the retired 1,842-day window. A trade count without its window
    is not checkable, and a CAGR without its window has already been quoted
    against the wrong one in this project.
    """
    import config as _c
    n = f", {len(eq):,} trading days" if eq is not None else ""
    return (f"WINDOW {_c.BT_START_DATE.date()} to {_c.BT_END_DATE.date()}{n} -- "
            f"every CAGR, Sharpe, drawdown and TRADE COUNT on this page is on that "
            f"window and no other.")

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
    import arms.registry as arm_reg
    sel = set(arm_reg.selected_names())

    # GATED ON v2 BEING SELECTED, like v3 and v4 below. Its only purpose is v2's
    # MeanNamesHeld / CashShortSkips columns; with v2 deselected there is no v2
    # row to carry them and this is a whole backtest run for a discarded result.
    a2 = _blank()
    if "v2" in sel:
        backtest_exposure(px, op, sc, bd, pc, mom20, port_vol, mode="breadth",
                          target_vol=tv, sizing="invvol", audit=a2)

    # --- the two new arms, same panel and dates as v1/v2 ---
    # COMPUTED ONLY IF SELECTED. A run that asked for v1 and v3 has no use for
    # v4's curve, and running it would put a number in the process that must then
    # be filtered out of four separate artefacts -- the kind of thing that leaks.
    # ARM_SEL is read at CALL time, not at import, so run.py setting it after this
    # module is imported still takes effect.
    a3, a4 = _blank(), _blank()
    v3_eq = v3_tc = v3_n = None
    v4_eq = v4_tc = v4_n = None
    v4_expo = 0.0
    if "v3" in sel:
        v3_eq, v3_tc, v3_n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                                  mode="none", target_vol=tv,
                                                  sizing="provol", audit=a3)
    if "v4" in sel:
        v4_eq, v4_tc, v4_n, v4_expo = backtest_exposure(px, op, sc, bd, pc, mom20,
                                                        port_vol, mode="breadth",
                                                        target_vol=tv, sizing="provol",
                                                        audit=a4)
    bh = start_capital * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    # ONE TABLE DRIVES CURVES, AUDITS, ROWS AND THE EQUITY COLUMNS, so an arm
    # cannot be filtered out of one of them and left in another. Order is ARMS
    # order, which is the order the four-arm table has always been written in.
    ARM_DEF = [
        ("v1", "v1 invvol, 100% invested",  "v1_invvol_none",    v1_eq, v1_tc, v1_n, 100.0,          v1_audit),
        ("v2", "v2 invvol, breadth-scaled", "v2_invvol_breadth", v2_eq, v2_tc, v2_n, v2_expo * 100,  a2),
        ("v3", "v3 provol, 100% invested",  "v3_provol_none",    v3_eq, v3_tc, v3_n, 100.0,          a3),
        ("v4", "v4 provol, breadth-scaled", "v4_provol_breadth", v4_eq, v4_tc, v4_n, v4_expo * 100,  a4),
    ]
    ARM_ON = [a for a in ARM_DEF if a[0] in sel]

    curves = [(lab, eq, dep) for _, lab, _, eq, _, _, dep, _ in ARM_ON] \
        + [("buy & hold equal-weight", bh, 100.0)]

    audits = {lab: au for _, lab, _, _, _, _, _, au in ARM_ON if au is not None}

    rows = [arm_row(eq, lab, tc, n, dep)
            for _, lab, _, eq, tc, n, dep, _ in ARM_ON] \
        + [arm_row(bh, "buy & hold equal-weight", 0, 0, 100.0)]
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
    # THE CANONICAL v34_* FILES ARE WRITTEN ONLY ON A FULL FOUR-ARM SELECTION.
    # SFX is "" then, so those paths and their contents are exactly what they have
    # always been. A subset writes v34_comparison_v1_v3.csv and friends beside
    # them and leaves the canonical files untouched.
    #
    # THIS IS NOT TIDINESS, IT PROTECTS SEVEN GATES. purge_fix_measure,
    # seed_noise_measure, seed_noise_report, shuffle_test, validate_topn,
    # rebal_cadence_sweep and drawdown_exit_measure all read v34_comparison.csv,
    # and six of them assert their own control run against its v2 ROW. A two-arm
    # subset overwriting that file would leave every one of them comparing against
    # a table that no longer holds their reference -- and they would discover it
    # later, in a different script, as a missing row rather than as this run's
    # doing. The universe work set the same precedent: a narrower selection writes
    # its own file rather than silently rewriting the published one.
    SFX = arm_reg.selection_suffix()
    comp = pd.DataFrame(rows)
    comp.to_csv(M / f"v34_comparison{SFX}.csv", index=False)

    subs = sub_rows(curves, halves, audits)
    subs.to_csv(M / f"v34_subperiods{SFX}.csv", index=False)

    eq_cols = {"date": bd}
    for _, _, col, eq, _, _, _, _ in ARM_ON:
        eq_cols[col] = eq.values
    eq_cols["buyhold"] = bh.values
    pd.DataFrame(eq_cols).to_csv(M / f"v34_equity{SFX}.csv", index=False)

    (M / f"v34_params{SFX}.json").write_text(json.dumps({
        "universe": universe_label,
        "universe_tag": universe_tag,
        "window_start": str(bd[0].date()),
        "window_end": str(bd[-1].date()),
        "trading_days": int(len(bd)),
        # ONLY THE ARMS THIS RUN ACTUALLY MEASURED. On a full selection this is
        # the same four entries in the same order it has always carried.
        "arms": {n: f"{arm_reg.ARMS[n].sizing} + mode={arm_reg.ARMS[n].mode}"
                 for n, _, _, _, _, _, _, _ in ARM_ON},
        "reference": "equal-weight buy & hold of the same universe, same panel",
        "constants": consts,
        "git_state": _git_state(),
        "run_date": str(pd.Timestamp.today().date()),
        "spec": "experiments/V34_SPEC.txt",
    }, indent=2))

    # --- chart: four arms plus the reference on one axis ---
    fig, ax = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[2, 1])
    # COLOUR IS KEYED TO THE ARM, NOT TO POSITION. Zipping a fixed five-colour
    # list against `curves` gave v3 v2's colour the moment v2 was deselected, so
    # the same arm changed colour between two charts in the same directory.
    ARM_STYLE = {"v1": ("#1f77b4", "-"), "v2": ("#d62728", "-"),
                 "v3": ("#2ca02c", "-"), "v4": ("#9467bd", "-")}
    style = [ARM_STYLE[n] for n, *_ in ARM_ON] + [("#7f7f7f", "--")]
    for (lab, eq, dep), (c, ls) in zip(curves, style):
        m = metrics(eq, lab)
        ax[0].plot(eq.index, (eq / eq.iloc[0] - 1) * 100, lw=1.8, color=c, ls=ls,
                   label=f"{lab}  [inv {dep:.0f}%]  CAGR {m['CAGR%']}%  "
                         f"vol {ann_vol_pct(eq)}%  Sharpe {m['Sharpe']}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    # THE TITLE DESCRIBES THE ARMS ON THE CHART, DERIVED RATHER THAN ASSERTED.
    # It used to say "four ... v1/v3 hold 100% invested; v2/v4 scale exposure by
    # breadth" as a literal, which is a false statement on any subset. Derived
    # from ARM_ON it reproduces that sentence exactly when all four are present --
    # the always-invested arms ARE v1 and v3, the breadth-scaled ones ARE v2 and
    # v4 -- and tells the truth when they are not.
    _CNT = {1: "one", 2: "two", 3: "three", 4: "four"}
    _flat = "/".join(n for n, *_ in ARM_ON if arm_reg.ARMS[n].mode == "none")
    _brd = "/".join(n for n, *_ in ARM_ON if arm_reg.ARMS[n].mode == "breadth")
    _how = "; ".join(x for x in (f"{_flat} hold 100% invested" if _flat else "",
                                 f"{_brd} scale exposure by breadth" if _brd else "")
                     if x)
    _sizings = {arm_reg.ARMS[n].sizing for n, *_ in ARM_ON}
    _size_note = (" Sizing is the only other difference: 1/vol against vol."
                  if len(_sizings) > 1 else
                  f" All arms here size {'1/vol' if 'invvol' in _sizings else 'by vol'}.")
    ax[0].set_title(
        f"{universe_label} -- {_CNT.get(len(ARM_ON), len(ARM_ON))} sizing/exposure "
        f"arm{'s' if len(ARM_ON) != 1 else ''} plus equal-weight buy & hold\n"
        f"WINDOW {bd[0].date()} to {bd[-1].date()}, {len(bd)} trading days -- every "
        f"CAGR, Sharpe, drawdown and TRADE COUNT here is on that window and no other.\n"
        f"All figures after Zerodha costs plus 0.15% slippage.\n"
        f"{_how}.{_size_note}", fontsize=9)
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
    plt.savefig(M / f"chart_v34{SFX}.png", dpi=150, bbox_inches="tight")
    plt.close()

    return comp, subs, curves


# ---------------------------------------------------------------------------
# SINGLE-ARM EXECUTION
# ---------------------------------------------------------------------------
def run_arm(u, arm, rebal=None, out_dir=None):
    """Run ONE arm on ONE universe and write that combination's own artefacts.

    WHY THIS EXISTS ALONGSIDE run_v34, NOT INSTEAD OF IT.
        run_v34 computes all four arms in a single call and writes them as rows of
        v34_comparison.csv. That file is not just a report: SEVEN scripts read it as
        an IDENTITY GATE -- purge_fix_measure, seed_noise_measure, seed_noise_report,
        shuffle_test, validate_topn, drawdown_exit_measure and rebal_cadence_sweep
        each assert their own control run reproduces its published v2 row exactly,
        and make_v34_report indexes all five rows by Config. Replacing that table
        with per-arm files would break all seven.

        So this is ADDITIVE. run_v34 keeps producing the combined table when all
        four arms are run; this produces one arm's own output, into its own
        directory, so a single arm can be run on its own without touching anything
        the rest of the project reads.

    IT LOADS ITS OWN PANEL. run_v34 is handed already-built objects by an engine
    that has just used them; this is called directly by run.py for an arbitrary
    (universe, arm) pair, with no engine in the picture, so it builds what it needs.
    The construction is the same as the engines': close/open/score pivots, the
    universe's own window, precompute, 20-day momentum.
    """
    import config
    import paths
    from engine_core import precompute
    from test_exposure import backtest_exposure, START_CAPITAL

    out = Path(out_dir) if out_dir is not None else paths.run_dir(u, arm)
    out.mkdir(parents=True, exist_ok=True)

    src = config.require_cache(u.score_cache, str(u.score_tmp),
                               what=f"{u.label} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = u.trading_days(px.index)
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(60).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()

    audit = {k: [] for k in ("holdings", "summary", "trades",
                             "ranking", "decisions", "skipped")}
    eq, tc, ntr, expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, port_vol,
        mode=arm.mode, target_vol=tv, sizing=arm.sizing, audit=audit,
        # A frozen universe opts OUT of the valuation correction, exactly as its
        # engine does; keyed off the universe, not off which file is running.
        value_at_open=not u.frozen, rebal=rebal)

    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    dep = 100.0 if arm.mode == "none" else expo * 100
    rows = [arm_row(eq, arm.label, tc, ntr, dep),
            arm_row(bh, "buy & hold equal-weight", 0, 0, 100.0)]
    mh, nsk = held_and_skips(audit)
    rows[0]["MeanNamesHeld"], rows[0]["CashShortSkips"] = round(mh, 2), nsk
    rows[1]["MeanNamesHeld"], rows[1]["CashShortSkips"] = "", ""
    comp = pd.DataFrame(rows)
    comp.to_csv(out / "comparison.csv", index=False)

    halves = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
    curves = [(arm.label, eq, dep), ("buy & hold equal-weight", bh, 100.0)]
    sub_rows(curves, halves, {arm.label: audit}).to_csv(out / "subperiods.csv", index=False)

    pd.DataFrame({"date": bd, arm.equity_column: eq.values,
                  "buyhold": bh.values}).to_csv(out / "equity.csv", index=False)

    (out / "params.json").write_text(json.dumps({
        "universe": u.label, "universe_tag": u.tag,
        "arm": arm.name, "mode": arm.mode, "sizing": arm.sizing,
        "rebal": rebal if rebal is not None else 20,
        "frozen_universe": u.frozen, "value_at_open": not u.frozen,
        "purge_mode": u.purge_mode,
        "window_start": str(bd[0].date()), "window_end": str(bd[-1].date()),
        "trading_days": int(len(bd)),
        "deployed_pct": round(float(dep), 1),
        "git_state": _git_state(), "run_date": str(pd.Timestamp.today().date()),
    }, indent=2))

    fig, ax = plt.subplots(2, 1, figsize=(13, 8), height_ratios=[2, 1])
    for (lab, e, d), c in zip(curves, ("#1f77b4", "#7f7f7f")):
        m = metrics(e, lab)
        ax[0].plot(e.index, (e / e.iloc[0] - 1) * 100, lw=1.8, color=c,
                   ls="-" if c != "#7f7f7f" else "--",
                   label=f"{lab}  [inv {d:.0f}%]  CAGR {m['CAGR%']}%  "
                         f"vol {ann_vol_pct(e)}%  Sharpe {m['Sharpe']}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(f"{u.label} -- {arm.label}\n{_window_label(eq)}\n"
                    f"mode={arm.mode}  sizing={arm.sizing}  "
                    f"rebal={rebal if rebal is not None else 20}", fontsize=9)
    ax[0].legend(loc="upper left", fontsize=8); ax[0].grid(alpha=.3)
    for (lab, e, d), c in zip(curves, ("#1f77b4", "#7f7f7f")):
        dd = (e / e.cummax() - 1) * 100
        ax[1].plot(e.index, dd, lw=1.2, color=c, label=f"{lab} (max {dd.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=8); ax[1].grid(alpha=.3)
    plt.tight_layout(); plt.savefig(out / "chart.png", dpi=140, bbox_inches="tight")
    plt.close()
    return comp, out
