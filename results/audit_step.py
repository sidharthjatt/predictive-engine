"""
audit_step.py -- the daily audit trail, once, for any universe.
==============================================================

WHAT THIS REPLACES
    Three files carried this same ~60-line body: make_daily_audit.py (58 and 74),
    make_mid_audit.py and make_n100_audit.py. The mid and n100 pair were 98.4%
    identical -- one differing code line each side -- and both were, by their own
    docstrings, copies of the 58/74 script with the tail call changed.

    Every difference between them turned out to be a universe property that
    universes/registry.py already records. Nothing needed inventing:

        window          u.trading_days(index)   -- the retired 58/74 cut by YEAR
                                                   (2019..2026 / 2019..2025) and the
                                                   live pair cut by DATE. Verified to
                                                   reproduce all four exactly:
                                                   1842 / 1732 / 1836 / 1836 days.
        score panel     u.score_tmp, u.score_cache
        output dir      u.metrics_dir
        filename tag    u.tag
        frozen pins     u.frozen  -- see below

FROZEN UNIVERSES OPT OUT OF THE CORRECTION, THEY DO NOT OPT IN
    The 58 and 74 are retired and their published numbers must not move, so for them
    this passes value_at_open=False -- the pre-2026-09-04 close-valued sizing -- and
    calls the frozen-write guard. Both are keyed off u.frozen rather than off which
    file is running, so a universe's freeze travels with the universe.

    That pin must stay in lockstep with engine_v2_final*.py, because the SAFETY check
    below compares this curve against v2FINAL_equity.csv and would fail if only one
    side moved. It is the same coupling the old make_daily_audit.py carried in a
    comment; it is now enforced by both reading u.frozen.

THE ENTRY POINTS STAY SEPARATE, DELIBERATELY
    make_mid_audit.py, make_n100_audit.py and frozen/make_daily_audit.py remain as
    thin per-universe entry points rather than collapsing into one script with three
    PIPELINE_ORDER entries. check_pipeline_order.analyse keys its ordering dicts BY
    SCRIPT NAME (`order = {scr: i ...}`), so three entries sharing one name collapse
    to a single position and the 10c-before-10d ordering it exists to enforce becomes
    invisible. Duplicating a name to save two files would disable a safety check to
    tidy a directory listing.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "results"), str(ROOT / "frozen")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config                                    # noqa: E402
from engine_core import precompute
import arms.registry as arm_reg
import cadence               # noqa: E402
from test_exposure import backtest_exposure      # noqa: E402
from _frozen_guard import guard as _frozen_guard  # noqa: E402


def panel_path(u):
    """The score panel: permanent copy first, working copy second.

    Same precedence the three siblings used, restated once. It is NOT
    config.require_cache: that raises a different message, and this audit's message
    names run_all.py as the fix.
    """
    if Path(u.score_cache).exists():
        return u.score_cache
    if Path(u.score_tmp).exists():
        return u.score_tmp
    raise FileNotFoundError(
        f"{u.score_cache} / {u.score_tmp} missing -- run run_all.py first")


def _reference_curve(M, arm_name):
    """The engine's own recorded equity curve for this arm, or None.

    THE AUDIT IS A CHECK, NOT A DUMP, and this is what it checks against. The
    trail is produced by re-running the backtest with logging on; if that re-run
    disagreed with the curve the engine published, the trail would describe a
    portfolio nobody reported. So every arm's trail is reconciled against the
    engine's own number for that arm.

    TWO FILES, BECAUSE THE ENGINE WRITES TWO. v1 and v2 are the shipping strategy
    and its control and live in v2FINAL_equity.csv; v3 and v4 are measurement arms
    and live in v34_equity.csv. Both are written by the engine step that runs
    immediately before this one, so both are on disk by now.

    None means the engine did not record that arm on this run -- a frozen
    universe has no v3/v4 at all, and an arm-subset run has no file for an arm it
    did not measure. The caller reports that rather than asserting against nothing.
    """
    import arms.registry as _ar
    # SPELLED `M / "..."`, NOT `Path(M) / "..."`. check_pipeline_order matches the
    # bare `<dir> / "<literal>"` shape; wrapping the directory in Path() made this
    # read invisible to the scanner and the edge vanished from its inventory.
    M = Path(M)
    # THE CADENCE-NAMED FILE FIRST. Under --rebal 40 the engine wrote
    # v2FINAL_equity_r40.csv and left the canonical cadence-20 file alone;
    # reconciling a cadence-40 trail against the cadence-20 curve reports a
    # MISMATCH of millions of rupees and refuses to write the trail. That is the
    # check working, but it is checking the wrong pair -- measured, before this
    # line existed: v1 MISMATCH Rs 2,923,934 and v2 MISMATCH Rs 1,825,210 on mid
    # at --rebal 40.
    f = M / f"v2FINAL_equity{cadence.suffix()}.csv"
    if not f.exists():
        f = M / "v2FINAL_equity.csv"
    if f.exists():
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date")
        s = _ar.equity_series(df, arm_name)
        if s is not None:
            return s
    for name in (f"v34_equity{_ar.selection_suffix()}{cadence.suffix()}.csv",
                 f"v34_equity{cadence.suffix()}.csv",
                 "v34_equity.csv"):
        g = M / name
        if g.exists():
            df = pd.read_csv(g, parse_dates=["date"]).set_index("date")
            col = _ar.ARMS[arm_name].equity_column
            if col in df.columns:
                return df[col]
    return None


def run(u, arm=None):
    """Write the daily audit trail for one universe and one arm.

    arm=None means v2 -- the arm this step has always audited, and the one whose
    filenames the Nautilus verification reads. Passing None reproduces the old
    behaviour exactly, which is why every existing caller keeps working.

    FILENAMES. v2 writes the unsuffixed daily_*_{tag}.csv it always has, because
    nt_verify.py, nt_daily_compare.py and nt_holdings_compare.py read those exact
    names and they are the 92-of-92 correctness gate. Every other arm writes
    daily_*_{tag}_{arm}.csv. v2 is therefore NOT special-cased in what it
    measures, only in what its files are called -- and that is a compatibility
    fact about the Nautilus port, recorded here rather than inferred.
    """
    if u.frozen:
        # Guards the WRITE. Frozen artefacts are gitignored and exist in one copy.
        _frozen_guard(u.tag)

    _hdr = u.tag if (arm is None or (arm.name if hasattr(arm, "name") else arm) == "v2") \
        else f"{u.tag} / {arm.name if hasattr(arm, 'name') else arm}"
    print(f"\n{'='*74}\n{_hdr} UNIVERSE\n{'='*74}")
    p = pd.read_csv(panel_path(u), parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    bd = u.trading_days(px.index)

    # THE ARM'S OWN PARAMETERS, not a hardcoded breadth/invvol pair. The default
    # is v2, which is the arm this step has always run, so mode and sizing below
    # are the same two values it always passed.
    _arm = arm_reg.ARMS["v2"] if arm is None else (
        arm if hasattr(arm, "name") else arm_reg.ARMS[arm])
    audit = {"holdings": [], "summary": [], "trades": [],
             "ranking": [], "decisions": [], "skipped": []}
    eq, tc, ntr, expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, mode=_arm.mode, sizing=_arm.sizing, audit=audit,
        # frozen: keep the close-valued sizing so published numbers cannot move
        value_at_open=not u.frozen,
        # THE RUN'S CADENCE. A trail built at 20 while the engine ran at 40 would
        # fail the reconciliation below -- which is the check working, but the fix
        # is to audit the cadence that was actually run.
        rebal=cadence.selected())

    # ---- SAFETY: does this match the official equity curve FOR THIS ARM? ----
    # The check is the point of the step. Auditing an arm against another arm's
    # curve would report MATCH only by accident, so the reference is looked up by
    # arm name -- v1/v2 from v2FINAL_equity.csv, v3/v4 from v34_equity.csv.
    M = Path(u.metrics_dir)
    _ref = _reference_curve(M, _arm.name)
    if _ref is None:
        # NOT AN ASSERTION FAILURE, AND NOT SILENT EITHER. It means the engine did
        # not record this arm on this run, so there is nothing to reconcile
        # against and writing an unchecked trail would be worse than writing none.
        print(f"  {u.tag}/{_arm.name}: the engine recorded no equity curve for this "
              f"arm, so its trail cannot be checked -- not written")
        return
    diff = float((eq - _ref.reindex(eq.index)).abs().max())
    status = "MATCH" if diff < 0.01 else f"*** MISMATCH Rs {diff:.2f} ***"
    print(f"  {_arm.name} equity vs the engine's recorded curve : {status}")
    if diff >= 0.01:
        print("  !! audit logging changed something -- do not go further")
        return

    # v2 KEEPS THE UNSUFFIXED FILENAMES. nt_verify.py, nt_daily_compare.py and
    # nt_holdings_compare.py read daily_summary_{tag}.csv, daily_holdings_{tag}.csv
    # and daily_trades_{tag}.csv by those exact names, and they are the 92-of-92
    # correctness gate. Suffixing v2 would break the gate that certifies the
    # engine. Every other arm is suffixed.
    tag = u.tag if _arm.name == "v2" else f"{u.tag}_{_arm.name}"
    # THE CADENCE JOINS THE FILENAME, empty at the default so v2's unsuffixed
    # names -- the ones the Nautilus verification reads -- are untouched.
    tag = tag + cadence.suffix()
    h = pd.DataFrame(audit["holdings"]); s = pd.DataFrame(audit["summary"])
    t = pd.DataFrame(audit["trades"])
    h.to_csv(M / f"daily_holdings_{tag}.csv", index=False)
    s.to_csv(M / f"daily_summary_{tag}.csv", index=False)
    t.to_csv(M / f"daily_trades_{tag}.csv", index=False)
    rkdf = pd.DataFrame(audit["ranking"]); dcdf = pd.DataFrame(audit["decisions"])
    rkdf.to_csv(M / f"daily_ranking_{tag}.csv", index=False)
    dcdf.to_csv(M / f"daily_decisions_{tag}.csv", index=False)
    skdf = pd.DataFrame(audit["skipped"])
    skdf.to_csv(M / f"daily_skipped_{tag}.csv", index=False)
    if len(skdf):
        print(f"  SKIPPED orders: {len(skdf)}")
        print(skdf["reason"].value_counts().to_string().replace("\n", "\n    "))
    else:
        print("  SKIPPED orders: 0")
    print(f"  rebalance (decision) days: {len(dcdf)} | ranking rows: {len(rkdf):,}")

    print(f"  trades logged : {len(t):,}   (engine reported {ntr:,})"
          f"   {'OK' if len(t)==ntr else '*** COUNT MISMATCH ***'}")
    print(f"  daily rows    : {len(s):,} days | holdings rows {len(h):,}")
    print(f"  avg stocks held: {s['n_stocks'].mean():.1f} | "
          f"avg cash {s['cash_pct'].mean():.1f}% | final Rs {s['total'].iloc[-1]:,.0f}")
    print(f"\n  saved -> daily_holdings_{tag}.csv / daily_summary_{tag}.csv / daily_trades_{tag}.csv")

    print(f"\n  --- SAMPLE: latest day ({s['date'].iloc[-1].date()}) ---")
    last = h[h["date"] == h["date"].max()]
    print(last[["symbol", "qty", "price", "value", "weight_pct"]].to_string(index=False))
    r = s.iloc[-1]
    print(f"  cash Rs {r['cash']:,.0f} ({r['cash_pct']}%) | holdings Rs {r['mtm']:,.0f} "
          f"({r['invested_pct']}%) | TOTAL Rs {r['total']:,.0f}")
