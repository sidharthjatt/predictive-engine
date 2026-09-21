"""
nt_gate_diagnose.py -- why verify_v34_arms.py is red, and how much it is worth.
==============================================================================

WHAT THIS ANSWERS

    verify_v34_arms.py, the V34 correctness gate, fails on midcap150: v2 at 89 of
    92 rebalances and v3 at 23 of 92, measured 2026-09-21. The symbol sets agree on
    every rebalance; only the share counts differ.

    "A ONE-SHARE DIFFERENCE" DESCRIBES v2 AND NOT v3, and the gate's own output
    invites the wrong reading because it prints only the FIRST diverging rebalance
    -- JSL 1697 against 1698, MAHABANK 8989 against 8988. Measured over all 92:

        v2   3 positions differ, all by exactly 1 share, Rs 53.64 in total,
             CAGR -0.000030 points -- below the reporting precision of 2 decimals
        v3   219 positions differ, only 91 of them by 1, the largest by 415 shares,
             Rs 2,694,187.49 in total, CAGR -0.2057 points -- well above it

    So v3 is not a rounding curiosity and must not be reported as one.

    diagnostics/verify_v34_arms.txt records the gate PASSING. That file carries a
    pre-repoint banner and was produced before the universes were repointed at
    Final_Without_Survivorship_Data on 2026-09-18. It has not been re-run since.
    The disagreement is reported, not reconciled.

THE ARITHMETIC, AND WHERE THE TWO PATHS PART

    Both sides compute the same expression:

        port        nt_strategy.py:407    q = int((self._invest_val * weight) // px)
        reference   nt_attribution.py:231 q = int((invest_val * w) // pr)

    and both build invest_val the same way, as portfolio value x exposure x SAFETY
    (nt_strategy.py:382, nt_attribution.py:221). The BUY price agrees too: the
    port's nt_data._round_to and the reference's nt_attribution._tick return the
    same value on all 400,000 opens of the midcap150 panel, measured 2026-09-21.

    ONE INPUT DIFFERS -- THE PRICE THE PORTFOLIO IS VALUED AT.

        reference   nt_attribution.py:218   vp = opens            the RAW open
        port        nt_strategy.py:440      px = self._open_mid   the quote MID

    and the mid is built at nt_strategy.py:275 as

        self._open_mid[sym] = 0.5 * (bid + ask)

    under a comment that states the assumption exactly:

        "bid = open*(1-slippage) and ask = open*(1+slippage), so the mid is the
         raw open -- the price the reference engine values the portfolio at."

    THAT IS TRUE IN EXACT ARITHMETIC AND FALSE ON A TICK GRID. nt_data.py:348-349
    snaps each side to the grid INDEPENDENTLY before the strategy ever sees them:

        ask = _round_to(open * (1 + slippage), tick)
        bid = _round_to(open * (1 - slippage), tick)

    so the mid is the average of two independent rounding errors, not the open.
    Measured on the midcap150 panel, 400,000 opens, tick 0.01, 2026-09-21: the mid
    differs from the raw open on 100,873 of them (25.22%), by up to 0.005 rupees a
    share, with a mean signed error of +0.00002127 -- a bias, not just noise.

    That feeds portfolio value, then invest_val, then the floor division. Wherever
    (invest_val * weight) / price sits within that error of an integer, the two
    sides floor to different share counts. It is a latent difference: it produces
    an identical quantity until a price lands close enough to a boundary, which is
    why a repoint that changed the prices turned a passing gate red without
    anything in either path being edited.

WHAT THIS FILE DOES NOT DO

    It changes nothing and reconciles nothing. It runs both sides, counts the
    divergences, prices them, and reports the effect on final equity and CAGR.
    Which side is right is not decided here: the port cannot see the raw open at
    09:15 any more than it can see the close, and that is a design question with
    its own blast radius.

USAGE

    ./venv/bin/python nautilus/nt_gate_diagnose.py             # failing arms only
    ./venv/bin/python nautilus/nt_gate_diagnose.py --scope     # every arm-universe pair
    ./venv/bin/python nautilus/nt_gate_diagnose.py --coverage  # what check_all runs

    The first truncates diagnostics/gate_divergence.txt; the other two append, so
    the three run in that order build the report.

    THE MECHANISM ABOVE ACCOUNTS FOR v2 AND IS NOT SHOWN TO ACCOUNT FOR v3. The
    measured mid-against-open error is a mean 0.000253 rupees a share, which over
    an eight-name book shifts the pre-floor quotient by between 0.00001 and 0.0065
    shares depending on price and size -- enough to predict a handful of flips over
    92 rebalances, and v2 has three. It does not by itself produce a 415-share
    difference. What it does produce is a FIRST divergence, on v3 at 2019-06-27,
    after which the two books hold different quantities and therefore value
    differently, size differently and compound apart for the remaining 69
    rebalances. That compounding is structural, not a hypothesis; its MAGNITUDE on
    v3 is not measured here and no part of the -0.2057 is attributed to it.
"""
import argparse
import contextlib
import io
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
sys.path.insert(0, str(ROOT / "nautilus"))

import config                                    # noqa: E402
import nt_data                                   # noqa: E402
import nt_run                                    # noqa: E402
import nt_attribution                            # noqa: E402
import nt_verify                                 # noqa: E402
from universes.registry import REGISTRY          # noqa: E402
from arms.registry import ARMS as ARM_REGISTRY   # noqa: E402

ARMS = [(a.name, a.mode, a.sizing) for a in ARM_REGISTRY.values()]

# The two the gate actually runs. Stated here the way verify_v34_arms.py states
# them, so the difference between what is covered and what exists is visible
# rather than implied.
GATE_UNIVERSES = ["nifty100", "midcap150"]
ALL_UNIVERSES = sorted(REGISTRY)

REPORT = ROOT / "diagnostics" / "gate_divergence.txt"


def run_pair(universe, arm, mode, sizing):
    """Run both sides of one arm-universe pair under the gate's own settings."""
    U = nt_run.UNIVERSES[universe]
    nt_data.set_tick_size("0.01"); nt_data.set_tick_mode("fixed")
    nt_attribution.set_tick("0.01"); nt_attribution.set_tick_mode("fixed")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"],
                               quiet=True, universe=universe,
                               sizing=sizing, mode=mode)
            dates, port = nt_verify.port_holdings(strat)
            panel = nt_attribution.load_panel(U["cache"])
            ref = nt_verify.arm(panel, dates, size_at_close=False,
                                value_at_open=True, tick_round=True,
                                sizing=sizing, mode=mode)
    finally:
        nt_data.set_tick_size("0.05"); nt_data.set_tick_mode("nse")
        nt_attribution.set_tick("0.05"); nt_attribution.set_tick_mode("nse")
    return dates, port, ref, strat, U


def magnitude(out, universe, arm, mode, sizing):
    """Count and price every divergence for one pair, and value its effect."""
    dates, port, ref, strat, U = run_pair(universe, arm, mode, sizing)

    # The divergence is priced at the reference's own valuation price -- the raw
    # open -- so the rupee figure is on the basis the reference engine uses.
    op_ = nt_attribution.load_panel(U["cache"])[1]

    n_reb = len(dates)
    n_diff_reb = n_diff_pos = 0
    share_diffs, rupee_diffs = [], []
    for d in dates:
        a, b = port.get(d, {}), ref.get(d, {})
        if a == b:
            continue
        n_diff_reb += 1
        for s in set(a) | set(b):
            qa, qb = a.get(s, 0), b.get(s, 0)
            if qa == qb:
                continue
            n_diff_pos += 1
            share_diffs.append(qa - qb)
            o = op_.loc[d].get(s, np.nan) if d in op_.index else np.nan
            rupee_diffs.append(abs(qa - qb) * (0.0 if np.isnan(o) else float(o)))

    sd = np.array(share_diffs) if share_diffs else np.array([0])
    rd = np.array(rupee_diffs) if rupee_diffs else np.array([0.0])

    out(f"  {universe} {arm} ({mode}/{sizing}): "
        f"{n_reb - n_diff_reb} of {n_reb} rebalances identical")
    out(f"    rebalances with any divergence        : {n_diff_reb}")
    out(f"    positions differing                   : {n_diff_pos}")
    if n_diff_pos:
        out(f"    share difference, min / max           : {sd.min():+d} / {sd.max():+d}")
        out(f"    positions differing by exactly 1      : "
            f"{int((np.abs(sd) == 1).sum())} of {n_diff_pos}")
        out(f"    largest single divergence             : Rs {rd.max():,.2f}")
        out(f"    total absolute rupee divergence       : Rs {rd.sum():,.2f}")
        out(f"    port shares above reference           : {int((sd > 0).sum())}")
        out(f"    port shares below reference           : {int((sd < 0).sum())}")
    return n_reb, n_reb - n_diff_reb


def equity_effect(out, universe, arm, mode, sizing):
    """Final equity and CAGR on each side of the same pair."""
    U = nt_run.UNIVERSES[universe]
    nt_data.set_tick_size("0.01"); nt_data.set_tick_mode("fixed")
    nt_attribution.set_tick("0.01"); nt_attribution.set_tick_mode("fixed")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"],
                               quiet=True, universe=universe,
                               sizing=sizing, mode=mode)
            pe = pd.DataFrame(strat.daily_equity).set_index("date")["equity"]
            panel = nt_attribution.load_panel(U["cache"])
            re_ = nt_attribution.run(*panel, size_at_close=False,
                                     value_at_open=True, tick_round=True,
                                     sizing=sizing, mode=mode)[0]
    finally:
        nt_data.set_tick_size("0.05"); nt_data.set_tick_mode("nse")
        nt_attribution.set_tick("0.05"); nt_attribution.set_tick_mode("nse")

    def cagr(e):
        ny = (e.index[-1] - e.index[0]).days / 365.25
        return ((e.iloc[-1] / e.iloc[0]) ** (1 / ny) - 1) * 100

    pf, rf = float(pe.iloc[-1]), float(re_.iloc[-1])
    pc_, rc = cagr(pe), cagr(re_)
    out(f"    final equity  port Rs {pf:>14,.2f}   reference Rs {rf:>14,.2f}")
    out(f"                  difference Rs {pf - rf:>+14,.2f}  ({(pf/rf - 1)*100:+.4f}%)")
    out(f"    CAGR          port {pc_:>8.4f}%   reference {rc:>8.4f}%   "
        f"difference {pc_ - rc:+.4f} points")
    if abs(round(pc_, 2) - round(rc, 2)) == 0:
        out(f"    The CAGR difference is BELOW THE REPORTING PRECISION of 2 decimals.")
        out(f"    It is not zero: at full precision it is {pc_ - rc:+.6f} points.")


def coverage(out):
    """Which gate-like scripts does check_all.py actually invoke?

    The test is against check_all.DELEGATES, the tuple it really runs, NOT against
    the file's text. tax_acceptance_check.py appears in a docstring at
    check_all.py:462 and a substring search over the file reports it as covered;
    it is not invoked.
    """
    import re
    src = (ROOT / "check_all.py").read_text()
    m = re.search(r"DELEGATES = \(([^)]*)\)", src, re.S)
    delegates = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()

    cands = sorted(
        p.relative_to(ROOT).as_posix()
        for d in (ROOT, ROOT / "nautilus", ROOT / "results")
        for p in d.glob("*.py")
        if re.search(r"check|verify|gate|valid|acceptance", p.name)
        and p.name not in ("check_all.py", "nt_gate_diagnose.py"))

    called = [c for c in cands if pathlib.Path(c).name in delegates]
    missed = [c for c in cands if pathlib.Path(c).name not in delegates]
    out(f"  check_all.py invokes {len(called)} of {len(cands)} gate-like scripts, "
        f"through its DELEGATES tuple at check_all.py:115.")
    out()
    out("  INVOKED:")
    for c in called:
        out(f"    {c}")
    out()
    out(f"  NOT INVOKED BY check_all.py ({len(missed)}):")
    for c in missed:
        out(f"    {c}")
    out()
    out("  A green check_all.py therefore says nothing about any of the scripts in")
    out("  the second list. verify_v34_arms.py is one of them, which is why it was")
    out("  red from 2026-09-18 to 2026-09-21 with every gate reporting PASS.")
    out()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", action="store_true",
                    help="run every arm on every universe the gate could cover")
    ap.add_argument("--coverage", action="store_true",
                    help="list gate scripts check_all.py does not call")
    a = ap.parse_args()

    lines = []

    def out(s=""):
        print(s, flush=True)
        lines.append(s)

    out("=" * 88)
    out("V34 GATE DIVERGENCE -- diagnosis, not reconciliation")
    out("=" * 88)
    out(f"window {config.BT_START_DATE.date()} to {config.BT_END_DATE.date()}, "
        f"tick 0.01 fixed on both sides (the gate's own setting)")
    out()

    if a.coverage:
        out("  PART 4 -- what check_all.py actually runs")
        out()
        coverage(out)
    elif a.scope:
        out(f"  SCOPE. {len(ARM_REGISTRY)} arms x {len(ALL_UNIVERSES)} registered "
            f"universes = {len(ARM_REGISTRY)*len(ALL_UNIVERSES)} possible pairs.")
        out(f"  verify_v34_arms.py hardcodes {GATE_UNIVERSES} at line 90, so it runs "
            f"{len(ARM_REGISTRY)*len(GATE_UNIVERSES)} of them.")
        out(f"  Universes never verified by any arm: "
            f"{[u for u in ALL_UNIVERSES if u not in GATE_UNIVERSES]}")
        out()
        for u in GATE_UNIVERSES:
            for name, mode, sizing in ARMS:
                n, ok = magnitude(out, u, name, mode, sizing)
                out(f"    verdict: {'VERIFIED' if ok == n else 'NOT VERIFIED'}")
                out()
    else:
        for u, name, mode, sizing in (("midcap150", "v2", "breadth", "invvol"),
                                      ("midcap150", "v3", "none", "provol")):
            magnitude(out, u, name, mode, sizing)
            equity_effect(out, u, name, mode, sizing)
            out()

    out("=" * 88)
    REPORT.parent.mkdir(exist_ok=True)
    mode_ = "w" if not (a.scope or a.coverage) else "a"
    # naming: axis-free -- one diagnosis of a disagreement between two engines.
    # It reports on the PORT and the REFERENCE, not on a strategy result, and
    # every arm and universe it covers is named inside the file.
    with open(REPORT, mode_) as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"written {REPORT}")


if __name__ == "__main__":
    main()
