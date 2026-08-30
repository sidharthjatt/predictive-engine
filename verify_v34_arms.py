"""
verify_v34_arms.py -- the V34 correctness gate: nt_verify for all four arms.

experiments/V34_SPEC.txt requires VERIFIED at 92 of 92 rebalances for EVERY arm on
BOTH universes. If any arm fails, no performance number may be reported for it.

WHY A DRIVER RATHER THAN FOUR nt_verify INVOCATIONS
    nt_verify.py reads its universe from sys.argv at import time and does its work
    in main(). It has no per-arm entry point. This drives its pieces directly so
    all four arms are verified in one process against one panel.

THE STALE-GLOBAL RISK, AND HOW IT IS PROVEN ABSENT
    Sizing is a module-level global in TWO places -- nt_strategy.SIZING for the
    port and nt_attribution.SIZING for the reference side. Four arms in one
    process is exactly the setup where a global left over from the previous arm
    silently verifies the wrong rule and still prints 92 of 92.

    So before each arm this asserts BOTH globals equal the arm's intended sizing,
    and prints the observed values beside that arm's result. The printed line is
    read back from the modules at the moment of the run, not from the loop
    variable, so the log cannot claim a rule the code was not using.

    Both sides must move together. If only the port switched, a pro-vol arm would
    be compared against an inverse-vol reference and would fail for a reason that
    has nothing to do with the port.

Nothing is hardcoded: the 92 comes from the run's own rebalance count.
Reads the panels, writes nothing in the repository.

    python3 verify_v34_arms.py                 # both universes, four arms each
    python3 verify_v34_arms.py --universe=mid  # one universe
"""
import contextlib
import io
import sys
import warnings

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
sys.path.insert(0, str(ROOT / "nautilus"))

import config
import nt_data
import nt_run
import nt_strategy
import nt_attribution
import nt_verify

ARMS = [("v1", "invvol"), ("v2", "invvol"), ("v3", "provol"), ("v4", "provol")]
UNIVERSES = ["n100", "mid"]


def set_both(mode):
    """Move the port and the reference together, then read both back."""
    nt_strategy.set_sizing(mode)
    nt_attribution.set_sizing(mode)
    return nt_strategy.SIZING, nt_attribution.SIZING


def verify_arm(universe, arm, sizing):
    """Return (n_rebalances, n_identical, observed_port, observed_ref, detail)."""
    port_sz, ref_sz = set_both(sizing)
    assert port_sz == sizing, f"nt_strategy.SIZING is {port_sz!r}, expected {sizing!r}"
    assert ref_sz == sizing, f"nt_attribution.SIZING is {ref_sz!r}, expected {sizing!r}"

    U = nt_run.UNIVERSES[universe]
    nt_data.set_tick_size("0.01"); nt_data.set_tick_mode("fixed")
    nt_attribution.set_tick("0.01"); nt_attribution.set_tick_mode("fixed")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"],
                               quiet=True, universe=universe)
            dates, port = nt_verify.port_holdings(strat)
            panel = nt_attribution.load_panel(U["cache"])
            ref = nt_verify.arm(panel, dates, size_at_close=False,
                                value_at_open=True, tick_round=True)
        stats = nt_verify.compare(port, ref, dates)
    finally:
        nt_data.set_tick_size("0.05"); nt_data.set_tick_mode("nse")
        nt_attribution.set_tick("0.05"); nt_attribution.set_tick_mode("nse")

    mism, sym_mism, qty_only, worst = stats
    n = len(dates)
    detail = None
    if mism:
        for d in dates:
            if port.get(d, {}) != ref.get(d, {}):
                detail = (d, port.get(d, {}), ref.get(d, {}))
                break
    return n, n - mism, nt_strategy.SIZING, nt_attribution.SIZING, detail


def main():
    unis = [u for u in UNIVERSES if f"--universe={u}" in sys.argv] or UNIVERSES
    print("=" * 100)
    print(" V34 CORRECTNESS GATE -- nt_verify, four arms, both universes")
    print("=" * 100)
    print(f"  window {config.BT_START_DATE.date()} to {config.BT_END_DATE.date()}"
          f"   (from config.py, shared by engine and port)")
    print("  the SIZING column is read back from the modules at run time, not from")
    print("  the loop variable, so it cannot report a rule the code did not use.")

    failures = []
    for u in unis:
        print(f"\n  {u.upper()}")
        print(f"    {'arm':<5}{'intended':<10}{'nt_strategy':<13}{'nt_attribution':<16}"
              f"{'result':<16}verdict")
        for arm, sizing in ARMS:
            n, ok, ps, rs, detail = verify_arm(u, arm, sizing)
            agree = (ps == sizing == rs)
            verdict = "VERIFIED" if (ok == n and agree) else "NOT VERIFIED"
            if verdict != "VERIFIED":
                failures.append((u, arm, sizing, n, ok, ps, rs, detail))
            print(f"    {arm:<5}{sizing:<10}{ps:<13}{rs:<16}"
                  f"{f'{ok} of {n}':<16}{verdict}")

    print("\n" + "=" * 100)
    if failures:
        print(" GATE FAILED")
        print("=" * 100)
        for u, arm, sizing, n, ok, ps, rs, detail in failures:
            print(f"\n  {u} {arm} ({sizing}): {ok} of {n} identical")
            print(f"    nt_strategy.SIZING={ps!r}  nt_attribution.SIZING={rs!r}")
            if detail:
                d, pd_, rd_ = detail
                syms = sorted(set(pd_) | set(rd_))
                print(f"    first diverging rebalance: {pd.Timestamp(d).date()}")
                print(f"      {'symbol':<14}{'port':>10}{'reference':>12}")
                for s in syms:
                    a, b = pd_.get(s, 0), rd_.get(s, 0)
                    mark = "" if a == b else "   <-- differs"
                    print(f"      {s:<14}{a:>10}{b:>12}{mark}")
        print("\n  Per the spec, NO performance number is reported for a failing arm.")
        sys.exit(1)
    print(" GATE PASSED -- every arm VERIFIED on every universe run")
    print("=" * 100)


if __name__ == "__main__":
    main()
