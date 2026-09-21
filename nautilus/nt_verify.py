"""
nt_verify.py -- one command that reports the true state of the Nautilus port.

Runs the port, compares it against the reference engine on three levels, and
prints what matches, what does not, and by how much. Nothing here is hardcoded:
every number is produced by the run it describes.

Run: python3 nautilus/nt_verify.py
"""
import contextlib
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import nt_data
import nt_run

import nt_attribution

# Selected by --universe on the command line. THE CHOICES ARE THE REGISTRY, not a
# written-down tuple: the tuple used to name the 58 and the 74, and the default was
# the literal "58", so this module raised KeyError at import the day they were
# deleted. The reference CSVs, the price panel and the score parquet all move
# together, because a verification is only meaningful when both sides read the same
# universe.
UNIVERSE = next(iter(nt_run.UNIVERSES))
for _u in nt_run.UNIVERSES:
    if f"--universe={_u}" in sys.argv:
        UNIVERSE = _u
U = nt_run.UNIVERSES[UNIVERSE]
M = U["metrics"]
TAG = U["tag"]


def compare(a_all, b_all, dates):
    """Compare two {date: {symbol: qty}} maps over the same rebalance dates.

    Returns (mismatches, symbol-set mismatches, quantity-only mismatches, errors%).
    """
    mism = sym_mism = qty_only = 0
    worst = []
    for d in dates:
        a, b = a_all.get(d, {}), b_all.get(d, {})
        if a == b:
            continue
        mism += 1
        if set(a) != set(b):
            sym_mism += 1
        else:
            qty_only += 1
            for s in a:
                if a[s] != b[s]:
                    worst.append(abs(a[s] - b[s]) / max(b[s], 1) * 100)
    return mism, sym_mism, qty_only, worst


def report(label, stats, n):
    mism, sym_mism, qty_only, worst = stats
    print(f"\n  {label}")
    print(f"    identical holdings      : {n - mism} of {n}")
    print(f"    differing by symbol set : {sym_mism}")
    print(f"    differing by quantity   : {qty_only}")
    if worst:
        w = pd.Series(worst)
        print(f"    quantity error: median {w.median():.2f}%  max {w.max():.2f}%")


def port_holdings(strat):
    """{rebalance_date: {symbol: qty}} plus the rebalance dates themselves.

    THE REBALANCE DATES COME FROM `decisions`, NOT FROM `holdings_log`.
    holdings_log emits one row per HELD symbol, so a rebalance that starts from an
    empty portfolio -- 2019-01-01, the first one -- emits nothing at all. Counting
    its distinct dates therefore reported 92 against the reference's 93 and made a
    bookkeeping artefact look like a missing rebalance. There is no missing
    rebalance: the run itself reports 93.
    """
    dates = [pd.Timestamp(d["decided_on"]) for d in strat.decisions]
    hp = pd.DataFrame(strat.holdings_log)
    hp["date"] = pd.to_datetime(hp["date"])
    port = {d: {} for d in dates}
    for _, r in hp.iterrows():
        port[r["date"]][r["symbol"]] = int(r["qty"])
    return dates, port


def arm(panel, dates, **kwargs):
    """Holdings from one arm of the reference re-implementation, on `dates`."""
    out = {}
    nt_attribution.run(*panel, holdings_out=out, **kwargs)
    return {d: out.get(d, {}) for d in dates}


def tick_proof():
    """Re-run BOTH systems on a 0.01 grid instead of 0.05.

    A 0.05 tick is 0.19% of price on a Rs 27 stock like BEL, and quantity is a floor
    division by that price, so the grid alone moves share counts. Dropping both sides
    to 0.01 separates that quantization from any real difference: what survives is a
    genuine disagreement, what disappears was the grid.
    """
    # The proof needs the FINEST UNIFORM grid, not the realistic one. Its purpose
    # is to separate tick quantization from genuine logic differences, and the real
    # dated rule is 0.05 for most of the window -- five times coarser -- which
    # would confound exactly what this is meant to isolate.
    nt_data.set_tick_size("0.01"); nt_data.set_tick_mode("fixed")
    nt_attribution.set_tick("0.01"); nt_attribution.set_tick_mode("fixed")
    try:
        # This is a control run, not a result. Its own summary would land in the
        # middle of the report and read like the port's real numbers.
        with contextlib.redirect_stdout(io.StringIO()):
            strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"], quiet=True, universe=UNIVERSE)
        dates, port = port_holdings(strat)
        panel = nt_attribution.load_panel(U["cache"])
        return compare(port, arm(panel, dates, size_at_close=False,
                                 value_at_open=True, tick_round=True), dates), len(dates)
    finally:
        nt_data.set_tick_size("0.05"); nt_data.set_tick_mode("nse")
        nt_attribution.set_tick("0.05"); nt_attribution.set_tick_mode("nse")


def main():
    strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"], universe=UNIVERSE)

    eq = pd.DataFrame(strat.daily_equity)
    eq["date"] = pd.to_datetime(eq["date"])
    eq = eq.set_index("date")["equity"]
    ref_eq = pd.read_csv(M / f"daily_summary_{TAG}.csv", parse_dates=["date"]) \
               .set_index("date")["total"]

    # THE INTERSECTION USED TO HIDE A MISSING DAY, AND DID.
    #     `common` silently discards any date one side lacks, so when the port's
    #     series held 1,841 rows against the reference's 1,842 the comparison simply
    #     moved to the last date they shared and reported it as "final equity". The
    #     missing 2026-06-08 carried ten fills on the 58 and twelve on mid. Nothing
    #     in the output said so: the numbers looked like a clean 0.03% agreement.
    #
    #     A date index that does not match is a defect to report, not a set to
    #     narrow. The comparison below still runs -- it is diagnostic and refusing to
    #     print it would be less useful -- but the mismatch is stated first and the
    #     equity line is labelled with the date it actually describes.
    idx_ok = (len(eq.index) == len(ref_eq.index)
              and eq.index[0] == ref_eq.index[0]
              and eq.index[-1] == ref_eq.index[-1])
    common = eq.index.intersection(ref_eq.index)

    dates, port = port_holdings(strat)

    hr = pd.read_csv(M / f"daily_holdings_{TAG}.csv", parse_dates=["date"])
    ref = {d: {} for d in dates}
    for _, r in hr[hr["date"].isin(dates)].iterrows():
        ref[r["date"]][r["symbol"]] = int(r["qty"])

    panel = nt_attribution.load_panel(U["cache"])
    # ARM D: the reference engine re-run with the port's two documented differences
    # applied -- portfolio valued at the execution day's OPEN, prices on the 0.05
    # tick grid. Comparing against the close-valued reference alone charges the port
    # for a difference it is designed to have, so both baselines are reported.
    arm_d = arm(panel, dates, size_at_close=False, value_at_open=True, tick_round=True)
    # ARM A is the reference's own configuration. Its holdings must reproduce
    # daily_holdings_58.csv, and that is checked below rather than assumed -- it is
    # what licenses ARM D as a baseline at all.
    arm_a = arm(panel, dates, size_at_close=False)

    ref_stats = compare(port, ref, dates)
    d_stats = compare(port, arm_d, dates)
    a_check = compare(arm_a, ref, dates)

    fp = pd.DataFrame(strat.fills)
    fr = pd.read_csv(M / f"daily_trades_{TAG}.csv", parse_dates=["date"])

    n = len(dates)
    mism, sym_mism, qty_only, worst = ref_stats
    print("\n" + "=" * 72)
    print(f" NAUTILUS PORT -- VERIFICATION AGAINST THE REFERENCE ENGINE  [{TAG} universe]")
    print("=" * 72)
    if not idx_ok:
        print("\n  *** DATE INDEX MISMATCH -- the two series do not cover the same days ***")
        print(f"      port      {len(eq.index):>5} rows   "
              f"{eq.index[0].date()} -> {eq.index[-1].date()}")
        print(f"      reference {len(ref_eq.index):>5} rows   "
              f"{ref_eq.index[0].date()} -> {ref_eq.index[-1].date()}")
        only_ref = ref_eq.index.difference(eq.index)
        only_prt = eq.index.difference(ref_eq.index)
        if len(only_ref):
            print(f"      missing from the PORT      ({len(only_ref)}): "
                  f"{', '.join(str(d.date()) for d in only_ref[:8])}"
                  f"{' ...' if len(only_ref) > 8 else ''}")
        if len(only_prt):
            print(f"      missing from the REFERENCE ({len(only_prt)}): "
                  f"{', '.join(str(d.date()) for d in only_prt[:8])}"
                  f"{' ...' if len(only_prt) > 8 else ''}")
        print("      Every figure below is computed on the shared dates only, so it")
        print("      does NOT describe the full window. Fix the mismatch first.")

    # Labelled with the date it actually describes. This used to say "final equity"
    # while reporting the last SHARED day, which on a mismatched index is not the
    # final day of either series.
    _d = common[-1]
    _lab = "final equity" if idx_ok else "equity on last shared day"
    print(f"\n  {_lab}  ({_d.date()})")
    print(f"                 reference Rs {ref_eq.loc[_d]:>12,.0f}")
    print(f"                 port      Rs {eq.loc[_d]:>12,.0f}"
          f"   ({(eq.loc[_d] / ref_eq.loc[_d] - 1) * 100:+.2f}%)")
    # daily_holdings_58.csv has a row per day, not per rebalance, so count the
    # rebalance dates from the decisions file instead.
    n_ref = len(pd.read_csv(M / f"daily_decisions_{TAG}.csv"))
    print(f"\n  rebalances     reference {n_ref:>4}   port {n:>4}")
    # INFORMATIONAL ONLY -- the verdict below does not read these numbers. It
    # tests idx_ok, a_check[0], d_sym and t_stats[0], and nothing else. A large
    # divergence here is worth seeing, but it decides nothing on its own.
    print(f"  fills [FYI]    reference {len(fr):>4}   port {len(fp):>4}"
          f"   (not a pass/fail gate)")

    report("vs REFERENCE (valued at the execution day's close)", ref_stats, n)
    report("vs ARM D     (same engine, valued at the open, 0.05 ticks)", d_stats, n)
    print(f"\n  control: ARM A vs the reference's own holdings -- "
          f"{n - a_check[0]} of {n} identical")

    t_stats, t_n = tick_proof()
    print(f"\n  reconciliation on a 0.01 tick grid (both sides) -- "
          f"{t_n - t_stats[0]} of {t_n} identical")

    d_sym = d_stats[1]
    # THE EXIT STATUS, ADDED 2026-09-21. The five branches below are unchanged --
    # same conditions, same order, same text. Each now also sets `rc`, so a runner
    # can read the verdict this file has always printed. It exited 0 while
    # printing INCONCLUSIVE on midcap150, measured 2026-09-21.
    #
    # ONLY "VERIFIED" IS A PASS. INCONCLUSIVE is not a pass: the branch says ARM D
    # is not a trustworthy baseline, so the run established nothing and must not
    # be read as agreement.
    rc = 1
    print("\n" + "=" * 72)
    if not idx_ok:
        print("  NOT VERIFIED. The port and the reference do not cover the same set of")
        print("  trading days, so no figure above describes the same window on both")
        print("  sides. This is reported rather than intersected away because a silent")
        print("  intersection is what let a missing final day -- carrying ten fills on")
        print("  the 58 -- go unnoticed while the output read as a clean agreement.")
    elif a_check[0] != 0:
        print("  INCONCLUSIVE. ARM A does not reproduce the reference engine's own")
        print("  holdings, so ARM D is not a trustworthy baseline. Fix that first.")
    elif d_sym != 0:
        print("  NOT VERIFIED. Rebalances hold DIFFERENT SYMBOLS even against the")
        print("  open-valued baseline, which cannot be explained by sizing.")
    elif t_stats[0] == 0:
        print("  VERIFIED. On a 0.01 tick grid the port and the open-valued reference")
        print("  agree on every holding at every rebalance. So the two systems are")
        print("  identical in logic, and the differences reported above at the real")
        print("  0.05 grid are exactly two measured, documented things:")
        print("    - the reference values the portfolio at the execution day's CLOSE,")
        print("      which a strategy standing at 09:15 cannot know;")
        print("    - quantity is a floor division by a tick-snapped price, and one")
        print("      0.05 tick is 0.19% of a Rs 27 share.")
        print("  Neither is a bug, and nothing else remains unexplained.")
        rc = 0
    else:
        print("  NOT VERIFIED. Position SIZE still differs on a 0.01 grid, where tick")
        print("  quantization cannot be the cause, so something else is still wrong.")
        print("  Do not trade this.")
    print(f"\n  RESULT: {'PASS' if rc == 0 else 'FAIL'} -- universe {TAG}, "
          f"0.01-grid reconciliation {t_n - t_stats[0]} of {t_n} identical.")
    print("=" * 72)
    return rc


if __name__ == "__main__":
    sys.exit(main())
