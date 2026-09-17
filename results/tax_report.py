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
import numpy as np
import pandas as pd

import naming
import tax_util as T

# The four stems. Composed through naming.name() -- the only composer measured to
# carry all four axes without modification (naming.CARRIES, re-probed 2026-09-17).
STEMS = ("FY_TAX_STATEMENT", "FY_EQUITY", "HOLDING_PERIOD", "HOLDING_PERIOD_LOTS")


def artefact_name(stem, tag, ext=".csv"):
    """<stem>_<tag><axis tail><ext>, e.g. FY_TAX_STATEMENT_mid_v1_tradeable_tax.csv

    `tag` already carries the universe and the arm (audit_step.artefact_tag),
    which is why the arm axis is not composed again here.
    """
    return naming.name(f"{stem}_{tag}", ext)


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
        # naming: arm,cadence,profile,tax via naming.name -- every one of these
        # four artefacts exists only under tax=on and carries the full tail.
        # The directive sits on the WRITE, not on the path expression: Gate 2
        # reads the call it annotates, and a directive parked above an
        # intermediate assignment annotates nothing.
        df.to_csv(p, index=False)
        wrote.append(p)

    leaked = tax_audit.get("leaked", [])
    if leaked:
        print(f"  !! {len(leaked)} realised gain(s) fell into an already-assessed "
              f"financial year and were never taxed -- see KNOWN_ISSUES.md on the "
              f"before-fills ordering. This is not a guard; the figures stand.")
    return wrote
