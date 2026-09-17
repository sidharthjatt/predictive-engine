"""
tax_report.py -- the four tax artefacts. Written only when tax=on.
===============================================================================

    FY_TAX_STATEMENT_<tag>.csv    per financial year: buckets, netting, tax
    FY_EQUITY_<tag>.csv           equity at each financial-year boundary
    HOLDING_PERIOD_<tag>.csv      the holding-period distribution
    HOLDING_PERIOD_LOTS_<tag>.csv every closed lot, one row each

WHY THESE ARE FOUR FILES AND NOT FOUR COLUMNS ON AN EXISTING ONE
    Adding tax columns to daily_trades_<tag>.csv or v34_comparison<SFX>.csv would
    put them in front of gates that read those files and compute over their
    non-benchmark rows without erroring. The companion-file decision is the same
    one v34_common.py made for the profile axis, for the same reason.

    AND IT PROTECTS THE MANIFEST. daily_trades_74.csv and fifteen of its
    siblings are pinned by SHA-256 in RETIRED_UNIVERSES-manifest.txt. A new
    column on that file is a hash break for artefacts that cannot be regenerated.

THE NUMBERS HERE ARE THE TAXED RUN'S OWN, NEVER THE UNTAXED LOG'S
    FY_TAX_STATEMENT reports what the taxed portfolio ACTUALLY PAID, read from
    the in-loop ledger that charged it. It is not recomputed from a trade log,
    and in particular it is not the figure an untaxed run's log implies -- those
    differ by about 4% (mid: Rs 833,105 implied against Rs 798,365 charged, see
    tax_util's TAX PARTIALLY DAMPS ITSELF), and the implied one describes a run
    that did not happen.

    THE CONSEQUENCE IS THAT FY_TAX_STATEMENT RECONCILES WITH FY_EQUITY TO THE
    PAISA, and reconcile() checks exactly that before anything is written: the
    sum of the per-year tax must equal the cumulative tax the engine deducted.
    A mismatch raises rather than writing two files that disagree.

THE UNASSESSED YEAR IS A ROW, NOT AN OMISSION
    Section 3(9) assesses a financial year on the first trading day at or after
    31 March. FY2026-27's falls in 2027, outside the window, so its liability is
    computed and never deducted. It appears in FY_TAX_STATEMENT with
    assessed=False, its full liability in the tax column, and assessed_note
    spelling out that the window's final sessions are untaxed and that the
    untaxed tail includes the held-out sessions. It is excluded from the
    reconciliation total, because no cash moved for it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pandas as pd

import tax as _tax
import tax_util as T

# The four stems. Composed through naming.name() -- the only composer measured to
# carry all four axes without modification (naming.CARRIES, re-probed 2026-09-17).
STEMS = ("FY_TAX_STATEMENT", "FY_EQUITY", "HOLDING_PERIOD", "HOLDING_PERIOD_LOTS")


def artefact_name(stem, tag, ext=".csv"):
    """<stem>_<tag><ext>, e.g. FY_TAX_STATEMENT_mid_v1_tradeable_tax.csv

    `tag` IS ALREADY THE FULL COMPOSITION. audit_step.artefact_tag() returns the
    universe, the arm, and then cadence.suffix() + profiles.suffix() +
    tax.suffix() -- all four axes, which is why naming.CARRIES credits it with
    all four. So this appends the stem and NOTHING ELSE.

    IT USED TO CALL naming.name() HERE AND THAT WAS A DOUBLE COMPOSITION.
    naming.name() appends the same four-axis tail that artefact_tag has already
    applied, so a taxed run wrote FY_TAX_STATEMENT_mid_tax_tax.csv -- the suffix
    twice. It did not show when this module was first written because the
    then-caller passed a BARE tag ("mid") rather than artefact_tag's output, so
    exactly one composition happened and the name looked right. Wiring the step
    supplied the real tag and the second suffix appeared.

    THE LESSON IS THE ONE naming.py OPENS WITH: the composition rule was never
    the problem, retyping it at a second site is. Here the second site was this
    function, applying a tail to a string that already had one.
    """
    return f"{stem}_{tag}{ext}"


def fy_equity(eq, fys):
    """Equity on each financial year's last session, and the year's return.

    THE BOUNDARY IS THE LAST SESSION AT OR BEFORE 31 MARCH, not 31 March itself,
    which is frequently not a trading day. `close_date` says which session was
    used so a reader is never left inferring it.
    """
    rows = []
    for fy in sorted(fys):
        end = pd.Timestamp(year=fy + 1, month=3, day=31)
        s = eq[eq.index <= end]
        if s.empty:
            continue
        start = eq[eq.index <= pd.Timestamp(year=fy, month=4, day=1)]
        open_v = float(start.iloc[-1]) if len(start) else float(eq.iloc[0])
        rows.append({"fy": fy, "fy_label": T.fy_label(fy),
                     "close_date": s.index[-1], "open_equity": open_v,
                     "close_equity": float(s.iloc[-1]),
                     "fy_return_pct": (float(s.iloc[-1]) / open_v - 1) * 100
                     if open_v else np.nan})
    return pd.DataFrame(rows)


def holding_period(lots):
    """The distribution, and the ceiling the long-term branch is measured against.

    `max_held_days` is the number a gate watches: every published figure in this
    repository rests on the long-term branch never firing, and that rests on an
    empirical 326-day maximum with 39 days of headroom -- not on a structural
    property. See tax_util's note on the parked docstring that got this wrong.
    """
    if lots is None or lots.empty:
        return pd.DataFrame()
    h = lots["held_days"]
    return pd.DataFrame([{
        "lots": int(len(lots)),
        "max_held_days": int(h.max()), "min_held_days": int(h.min()),
        "mean_held_days": round(float(h.mean()), 2),
        "median_held_days": float(h.median()),
        "p95_held_days": float(h.quantile(0.95)),
        "long_term_threshold_days": T.LTCG_HOLD_DAYS,
        "lots_long_term": int(lots["is_long"].sum()),
        "headroom_days": int(T.LTCG_HOLD_DAYS - h.max()),
        "note": ("the long-term branch does not fire on this window; the margin "
                 f"is {int(T.LTCG_HOLD_DAYS - h.max())} days and is EMPIRICAL, "
                 "not structural -- a cadence or buffer change can cross it"),
    }])


def reconcile(stmt, cum_tax, tol=0.01):
    """Assessed tax in the statement must equal what the engine deducted.

    RAISES RATHER THAN WRITING. Two artefacts that disagree about how much tax
    was paid are worse than neither, because each looks authoritative alone. The
    unassessed year is excluded: its liability is real and reported, but no cash
    moved for it, so it cannot appear in a total that reconciles against cash.
    """
    charged = float(stmt.loc[stmt["assessed"], "total_tax"].sum())
    if abs(charged - float(cum_tax)) > tol:
        raise AssertionError(
            f"FY_TAX_STATEMENT does not reconcile with the engine's deductions:\n"
            f"    statement (assessed years) Rs {charged:,.2f}\n"
            f"    engine cum_tax             Rs {float(cum_tax):,.2f}\n"
            f"    difference                 Rs {charged - float(cum_tax):,.2f}\n"
            f"  Nothing written. FY_TAX_STATEMENT must report what the TAXED run\n"
            f"  actually paid, and it must agree with FY_EQUITY to the paisa.")
    return charged


def write_all(M, tag, eq, tax_audit, dates):
    """Write the four artefacts. Returns the paths, in the order written.

    `tax_audit` is audit["tax"] from backtest_exposure -- the in-loop ledger that
    actually charged the tax, not a recomputation.
    """
    lots = tax_audit["lots"]
    stmt, _due = T.liability_schedule(lots, dates)
    reconcile(stmt, tax_audit["cum_tax"])

    wrote = []
    for stem, df in (("FY_TAX_STATEMENT", stmt),
                     ("FY_EQUITY", fy_equity(eq, stmt["fy"])),
                     ("HOLDING_PERIOD", holding_period(lots)),
                     ("HOLDING_PERIOD_LOTS", lots)):
        p = M / artefact_name(stem, tag)
        # naming: arm,cadence,profile,tax via artefact_tag -- `tag` is
        # audit_step.artefact_tag's output and carries all four axes; these four
        # artefacts exist only under tax=on. The directive sits on the WRITE,
        # not on the path expression: Gate 2 reads the call it annotates, and a
        # directive parked above an intermediate assignment annotates nothing.
        df.to_csv(p, index=False)
        wrote.append(p)

    leaked = tax_audit.get("leaked", [])
    if leaked:
        print(f"  !! {len(leaked)} realised gain(s) fell into an already-assessed "
              f"financial year and were never taxed -- see KNOWN_ISSUES.md on the "
              f"before-fills ordering. This is not a guard; the figures stand.")
    return wrote


# ---------------------------------------------------------------------------
# THE STEP -- STEP 18a (mid) / STEP 18b (n100), arity 1
# ---------------------------------------------------------------------------
def main(u):
    """The step, as a function, so run.py can call it in process.

    ARITY 1 BECAUSE ALL FOUR ARTEFACTS ARE PER-UNIVERSE. The tag is in every
    filename and the content is one universe's lots; a whole-run step would have
    to loop the selection internally and would put run.py:_resolve_arity in the
    position of refusing a None tag against a main(u) signature.

    IT RE-RUNS THE BACKTEST, AND THAT IS NOT AVOIDABLE. Nothing upstream produces
    a TAXED run: tax_enabled defaults to False and no other PIPELINE_ORDER row
    passes True. The ledger and cum_tax live in audit["tax"], a Python object
    inside backtest_exposure, so they cannot cross a subprocess boundary or be
    read back off an artefact. The alternative -- having make_audit run a second
    taxed backtest -- was considered and rejected: that step's docstring calls
    itself a check rather than a producer, and it already reconciles an untaxed
    re-run against the engine's curve. Two jobs in a step that says it has one is
    how the cost gets hidden.

    ITS POSITION IS THE END OF THE PIPELINE. The only input is the score panel,
    and running after STEP 15b means the PERMANENT copy exists rather than
    relying on config.require_cache's /tmp fallback.
    """
    # THE EARLY RETURN IS THE WHOLE tax=off CONTRACT, and it uses the mechanism
    # this pipeline already has rather than a new one. run_all.py:166 records it
    # for the scoring step: "Steps 10a/10e are skipped at runtime when their
    # panel is cached; that does not change the ORDER, which is what the checker
    # reasons about." Same shape here -- the row is ALWAYS in PIPELINE_ORDER and
    # always invoked, and decides at run time to do nothing.
    #
    # CONDITIONAL MEMBERSHIP WAS NOT USED, DELIBERATELY. run_all.py:270 records
    # that the old SKIP list was removed ("NOTHING IS SKIPPED HERE ANY MORE");
    # making this row's presence depend on the selection would reintroduce
    # exactly the thing that was taken out, and it would make the plan differ
    # between two selections that check_plan_order should see identically.
    #
    # THE ARTEFACTS ARE ABSENT AT tax=off, NOT EMPTY. This returns before
    # write_all is reached, so no file is opened and none is created.
    if not _tax.selected():
        print(f"    tax=off -- no tax artefacts for {u.tag} "
              f"(the four are absent, not empty)")
        return

    # Imported here rather than at module scope: this module is imported by
    # run.py's arity probe, and pulling the engine in at import time would make
    # a --list or --dry-run pay for a backtest it never runs.
    import cadence
    import config
    import engine_core
    import profiles
    from engine_core import precompute
    from test_exposure import backtest_exposure
    import audit_step

    engine_core.set_tradeability(u)
    src = config.require_cache(u.score_cache, str(u.score_tmp),
                               what=f"{u.tag} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(60).std() * np.sqrt(252)
    bd = px.index[(px.index >= config.BT_START_DATE)
                  & (px.index <= config.BT_END_DATE)]

    audit = {k: [] for k in
             ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    eq, _tc, _ntr, _expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, port_vol, mode="breadth",
        target_vol=port_vol.loc[bd].median(), rebal=cadence.selected(),
        participation_cap=profiles.participation_cap(), audit=audit,
        tax_enabled=True)

    # THE TAG COMES FROM audit_step.artefact_tag, NOT FROM u.tag ALONE, so these
    # four sit beside the trail they describe under every axis combination.
    tag = audit_step.artefact_tag(u, "v2")
    wrote = write_all(Path(u.metrics_dir), tag, eq, audit["tax"], bd)
    print(f"    tax artefacts for {u.tag}: cum_tax Rs {audit['tax']['cum_tax']:,.2f}")
    for w in wrote:
        print(f"      saved -> {w.name}")


if __name__ == "__main__":
    # STANDALONE, BY TAG -- the same contract make_audit.py uses.
    from universes.registry import REGISTRY
    if len(sys.argv) != 2 or sys.argv[1] not in REGISTRY:
        raise SystemExit(f"usage: {Path(__file__).name} <universe>   "
                         f"known: {', '.join(sorted(REGISTRY))}")
    main(REGISTRY[sys.argv[1]])
