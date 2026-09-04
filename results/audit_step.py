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
from engine_core import precompute               # noqa: E402
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


def run(u):
    """Write the daily audit trail for one universe."""
    if u.frozen:
        # Guards the WRITE. Frozen artefacts are gitignored and exist in one copy.
        _frozen_guard(u.tag)

    print(f"\n{'='*74}\n{u.tag} UNIVERSE\n{'='*74}")
    p = pd.read_csv(panel_path(u), parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    bd = u.trading_days(px.index)

    audit = {"holdings": [], "summary": [], "trades": [],
             "ranking": [], "decisions": [], "skipped": []}
    eq, tc, ntr, expo = backtest_exposure(
        px, op, sc, bd, pc, mom20, mode="breadth", audit=audit,
        # frozen: keep the close-valued sizing so published numbers cannot move
        value_at_open=not u.frozen)

    # ---- SAFETY: does this match the official equity curve? ----
    M = Path(u.metrics_dir)
    off = pd.read_csv(M / "v2FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    diff = float((eq - off["strategy"].reindex(eq.index)).abs().max())
    status = "MATCH" if diff < 0.01 else f"*** MISMATCH Rs {diff:.2f} ***"
    print(f"  equity vs official v2FINAL_equity.csv : {status}")
    if diff >= 0.01:
        print("  !! audit logging changed something -- do not go further")
        return

    tag = u.tag
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
