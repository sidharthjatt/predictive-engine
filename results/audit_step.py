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
        score panel     u.score_cache
        output dir      u.metrics_dir
        filename tag    u.tag

SIZING IS VALUED AT THE OPEN, WITH NO OPT-OUT
    The deleted 58 and 74 passed value_at_open=False here -- the pre-2026-09-04
    close-valued sizing -- because they were frozen and their published numbers
    could not move. Nothing opts out any more: every universe is valued at the
    open, and this file no longer reads a per-universe flag to decide.

    That pin must stay in lockstep with engine_v2_final_*.py, because the SAFETY
    check below compares this curve against v2FINAL_equity.csv and would fail if
    only one side moved.

THE ENTRY POINTS STAY SEPARATE, DELIBERATELY
    make_mid_audit.py and make_n100_audit.py remain as thin per-universe entry
    points rather than collapsing into one script with two
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
for _p in (str(ROOT), str(ROOT / "results")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config                                    # noqa: E402
from engine_core import precompute
import arms.registry as arm_reg
import cadence               # noqa: E402
from test_exposure import backtest_exposure      # noqa: E402
import profiles as _prof            # the run's execution-realism profile
from config import read_table  # the one CSV/parquet reader: config.read_table


def panel_path(u):
    """The score panel, through config.require_cache.

    Until 2026-09-23 this returned whichever copy existed WITHOUT checking what it
    was built from, so the audit was the one reader a stale panel passed
    silently. It now goes through the same content-key check as every other.
    """
    return config.require_cache(u.score_cache, what=f"{u.tag} score panel")


def artefact_tag(u, arm):
    """The filename tag for one (universe, arm, cadence) -- THE ONE DEFINITION.

    WHY THIS IS A FUNCTION AND NOT A LINE INSIDE run().
        It used to be two lines in run(), and run() is the WRITER. make_daily_log
        is a READER of the same files and had no way to ask for the rule, so it
        hardcoded the unsuffixed `daily_*_{u.tag}.csv` names instead and returned
        early whenever they did not exist -- which is every selection except v2 at
        the default cadence. A reader that reconstructs a writer's naming rule
        drifts from it the moment either changes. There is now one rule and both
        sides call it.

    v2 KEEPS THE UNSUFFIXED FILENAMES. nt_verify.py, nt_daily_compare.py and
    nt_holdings_compare.py read daily_summary_{tag}.csv, daily_holdings_{tag}.csv
    and daily_trades_{tag}.csv by those exact names, and they are the 92-of-92
    correctness gate. Suffixing v2 would break the gate that certifies the engine.
    DAILY_LOG_{tag}.txt inherits the same rule, and README cites DAILY_LOG_mid.txt
    and DAILY_LOG_n100.txt by name. Every other arm is suffixed.

    THE CADENCE JOINS THE FILENAME, empty at the default, so v2's unsuffixed names
    are untouched by a default run.

    `arm` may be an Arm or a bare name, because callers hold both.
    """
    import profiles
    import tax as _tax
    name = getattr(arm, "name", arm)
    tag = u.tag if name == "v2" else f"{u.tag}_{name}"
    # THE PROFILE JOINS THE TAG for the same reason the cadence does: a
    # profile="tradeable" run must not overwrite the research trail that the
    # Nautilus comparison scripts and the daily log read by name. Empty at the
    # default, so v2's unsuffixed names are untouched.
    # AND THE TAX AXIS, for the same reason again: a tax=on run must not
    # overwrite the trail the Nautilus comparison scripts and the daily log read
    # by name. Empty at tax=off, so the unsuffixed names are untouched.
    return tag + cadence.suffix() + profiles.suffix() + _tax.suffix()


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
    #
    # AT A NON-DEFAULT CADENCE THERE IS NO FALLBACK TO THE UNSUFFIXED FILE.
    # Both chains used to end at one -- v2FINAL_equity.csv and v34_equity.csv --
    # which is a cadence-20 curve. Reaching either from a --rebal 200 run would
    # reconcile a cadence-200 trail against a cadence-20 curve: exactly the
    # mispairing measured above (v1 Rs 2,923,934, v2 Rs 1,825,210 on mid at
    # --rebal 40). It failed safe only by accident, because audit_step.run()
    # happens to refuse a trail whose difference exceeds a paisa. Returning None
    # here makes it safe BY DESIGN: the caller reports that there is no reference
    # curve for this arm at this cadence and writes nothing.
    #
    # AT THE DEFAULT CADENCE NOTHING CHANGES, and provably so: cadence.suffix() is
    # "" there, so f"v2FINAL_equity{suffix}.csv" IS "v2FINAL_equity.csv" and
    # f"v34_equity{suffix}.csv" IS "v34_equity.csv". The removed lines were a
    # no-op at the default and a hazard everywhere else.
    # THE PROFILE SUFFIX JOINS THE CADENCE ONE. A profile="tradeable" run writes
    # v34_equity_tradeable.csv; resolving to the research curve here would report a
    # MISMATCH of the cap's whole effect and refuse to write the trail -- the same
    # class of mispairing as the cadence one above, with the same failure mode.
    import profiles as _prof
    # THE TAX SUFFIX JOINS THE OTHER TWO, 2026-09-18, and it is the same hazard a
    # third time. This expression was written 2026-09-10 (0ce8ed5) and the tax
    # axis landed 2026-09-17 (7846f67), so for as long as the axis has existed
    # this resolved to the UNSUFFIXED curve on a taxed run -- v2FINAL_equity.csv
    # rather than v2FINAL_equity_tax.csv. The comments above record the identical
    # mispairing being fixed for cadence and then for profile; nobody added the
    # fourth axis, and the reconciliation below therefore compared an untaxed
    # re-run against an untaxed curve left on disk by an EARLIER, DIFFERENT run
    # and reported MATCH. It could not fail.
    import tax as _tax_axis
    _cad = cadence.suffix() + _prof.suffix() + _tax_axis.suffix()
    f = M / f"v2FINAL_equity{_cad}.csv"
    if f.exists():
        df = read_table(f, parse_dates=["date"]).set_index("date")
        s = _ar.equity_series(df, arm_name)
        if s is not None:
            return s
    for name in (f"v34_equity{_ar.selection_suffix()}{_cad}.csv",
                 f"v34_equity{_cad}.csv"):
        g = M / name
        if g.exists():
            df = read_table(g, parse_dates=["date"]).set_index("date")
            col = _ar.ARMS[arm_name].equity_column
            if col in df.columns:
                return df[col]
    return None


# naming: arm,cadence,profile via artefact_tag -- every daily_* artefact is
# artefact_tag() (audit_step.py:108), which appends cadence.suffix() and
# profiles.suffix(); the arm is in the tag body. nt_verify and make_daily_log
# read these by the same rule.
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
    _hdr = u.tag if (arm is None or (arm.name if hasattr(arm, "name") else arm) == "v2") \
        else f"{u.tag} / {arm.name if hasattr(arm, 'name') else arm}"
    print(f"\n{'='*74}\n{_hdr} UNIVERSE\n{'='*74}")
    # THE TRAIL MUST BE PRODUCED UNDER THE SAME GUARD AS THE CURVE IT IS CHECKED
    # AGAINST. This step re-runs the backtest with logging on and reconciles the
    # result against the engine's published curve to within a paisa, refusing to
    # write anything if it disagrees. The engine now loads the tradeability guard;
    # a trail built without it would differ by the forced exit and this step would
    # correctly refuse to write -- so the audit would vanish for a reason that is
    # not a fault.
    import engine_core as _ec
    _ec.set_tradeability(u)
    p = read_table(panel_path(u), parse_dates=["date"])
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
    # THE CAP AND THE DATA IT NEEDS, TOGETHER. This step passed
    # participation_cap() alone until 2026-09-15. backtest_exposure applies the cap
    # only where vol20 supplies a prior-20-session median, so a tradeable audit
    # replayed the RESEARCH strategy and reconciled it against the TRADEABLE curve:
    # "v1 MISMATCH Rs 3,851,027.09" on mid, which is the cap's whole effect to the
    # paisa. The trail was then refused -- correctly, for the wrong reason -- and
    # mid, the only universe where the cap binds, has never had a tradeable audit.
    #
    # THE SAME EXPRESSION THE ENGINES USE, deliberately. engine_v2_final_*.py and
    # v34_common.py build vol20 exactly this way; the audit must replay what the
    # engine ran, so it reads the volume from the same place by the same call
    # rather than by an equivalent-looking one.
    _capkw = _prof.cap_kwargs(u)
    # THE RUN'S TAX SELECTION. The audit must replay what the engine ran, and
    # after 21c6624 the engine charges tax; an untaxed re-run would now differ
    # from the taxed curve by the whole tax effect and refuse to write the trail.
    import tax as _tax_axis
    eq, tc, ntr, expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, mode=_arm.mode, sizing=_arm.sizing, audit=audit,
        value_at_open=True, tax_enabled=_tax_axis.selected(),
        # THE RUN'S CADENCE. A trail built at 20 while the engine ran at 40 would
        # fail the reconciliation below -- which is the check working, but the fix
        # is to audit the cadence that was actually run.
        rebal=cadence.selected(), **_capkw)

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

    # The naming rule lives in artefact_tag() above, so make_daily_log reads the
    # same files this writes instead of reconstructing the rule and drifting.
    tag = artefact_tag(u, _arm)
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
