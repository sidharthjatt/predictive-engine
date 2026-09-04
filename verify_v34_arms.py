"""
verify_v34_arms.py -- the V34 correctness gate: nt_verify for all four arms.

experiments/V34_SPEC.txt requires VERIFIED at 92 of 92 rebalances for EVERY arm on
BOTH universes. If any arm fails, no performance number may be reported for it.

WHY A DRIVER RATHER THAN FOUR nt_verify INVOCATIONS
    nt_verify.py reads its universe from sys.argv at import time and does its work
    in main(). It has no per-arm entry point. This drives its pieces directly so
    all four arms are verified in one process against one panel.

THE STALE-CONFIG RISK, AND HOW IT IS PROVEN ABSENT
    Sizing used to be a module-level global in two places -- nt_strategy.SIZING and
    nt_attribution.SIZING -- and four arms in one process is exactly the setup where
    a value left over from the previous arm silently verifies the wrong rule and
    still prints 92 of 92. This file guarded that by asserting both globals held the
    intended value before each arm.

    That guard was weaker than it looked: it proved the global had been SET, never
    that the run USED it. The exposure mode proved the point -- there was none, so
    every arm ran at breadth exposure while the sizing asserts passed happily, and
    v1/v3 were verified as configurations that were never actually run.

    Both are now passed as arguments, and BOTH SIDES RECORD WHAT THEY ACTUALLY
    APPLIED, on the branch actually taken. This asserts against that recording and
    prints it. An arm whose configuration never reaches the decision point now fails
    here instead of passing.

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

from universes.registry import REGISTRY
from arms.registry import ARMS as ARM_REGISTRY

# BOTH REGISTRIES FEED THIS FILE, and it is the one place where that matters
# most: this is the correctness gate, so a name here that disagreed with the name
# the engine uses would verify the wrong thing and still print 92 of 92.
#
# ARMS carries each arm's MODE and SIZING, both taken from arms/registry.py rather
# than re-listed here, so the gate cannot drift from the definition the research
# engine uses.
# NOW CARRIES THE EXPOSURE MODE TOO. Until 2026-09-04 the port had no exposure
# mode -- it always used breadth -- so v1/v3 (mode="none", 100% invested) could not
# be expressed and this gate ran two configurations twice, printing 92 of 92 for
# four arms it had only two of. mode is threaded through now, so the four arms are
# four arms.
ARMS = [(a.name, a.mode, a.sizing) for a in ARM_REGISTRY.values()]
# ORDER IS LOAD-BEARING AND IS NOT registry.LIVE's ORDER. LIVE comes out in the
# registry's declaration order (58, 74, mid, n100 -> mid, n100), while this
# report -- like every other script here -- runs n100 first. Using LIVE swapped
# the two blocks in the output. The order is therefore stated explicitly.
UNIVERSES = [u.tag for u in (REGISTRY["n100"], REGISTRY["mid"])]


def verify_arm(universe, arm, mode, sizing):
    """Return (n_rebalances, n_identical, observed_port, observed_ref, detail).

    WHAT REPLACED THE GLOBAL ASSERT, AND WHY IT IS STRONGER. This used to set
    nt_strategy.SIZING and nt_attribution.SIZING and assert both had taken the
    value. That proved the global was SET; it never proved the run USED it -- and
    the exposure mode was being ignored entirely while those asserts passed.
    Both sides now take the configuration as an argument and record what they
    actually applied, on the branch actually taken. The assert reads that recording
    back, so an arm whose configuration never reached the decision point fails here
    instead of passing.
    """

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
            ref_applied = {"sizing": None, "mode": None}
            ref = nt_verify.arm(panel, dates, size_at_close=False,
                                value_at_open=True, tick_round=True,
                                sizing=sizing, mode=mode,
                                applied_out=ref_applied)
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
    # READ BACK WHAT EACH SIDE ACTUALLY APPLIED, not what it was asked to apply.
    port_applied, ref_a = strat.applied, ref_applied
    for who, got in (("nt_strategy", port_applied), ("nt_attribution", ref_a)):
        assert got["sizing"] == sizing, \
            f"{who} applied sizing {got['sizing']!r}, expected {sizing!r}"
        assert got["mode"] == mode, \
            f"{who} applied mode {got['mode']!r}, expected {mode!r}"
    obs_port = f"{port_applied['mode']}/{port_applied['sizing']}"
    obs_ref = f"{ref_a['mode']}/{ref_a['sizing']}"
    return n, n - mism, obs_port, obs_ref, detail


def main():
    unis = [u for u in UNIVERSES if f"--universe={u}" in sys.argv] or UNIVERSES
    print("=" * 100)
    print(" V34 CORRECTNESS GATE -- nt_verify, four arms, both universes")
    print("=" * 100)
    print(f"  window {config.BT_START_DATE.date()} to {config.BT_END_DATE.date()}"
          f"   (from config.py, shared by engine and port)")
    print("  the applied columns are what each side RECORDED at its decision point,")
    print("  not what it was asked to apply, so they cannot report a rule the code")
    print("  did not actually use.")

    failures = []
    for u in unis:
        print(f"\n  {u.upper()}")
        print(f"    {'arm':<5}{'intended':<16}{'port applied':<17}"
              f"{'reference applied':<20}{'result':<16}verdict")
        for arm, mode, sizing in ARMS:
            n, ok, ps, rs, detail = verify_arm(u, arm, mode, sizing)
            intended = f"{mode}/{sizing}"
            agree = (ps == intended == rs)
            verdict = "VERIFIED" if (ok == n and agree) else "NOT VERIFIED"
            if verdict != "VERIFIED":
                failures.append((u, arm, intended, n, ok, ps, rs, detail))
            print(f"    {arm:<5}{intended:<16}{ps:<17}{rs:<20}"
                  f"{f'{ok} of {n}':<16}{verdict}")

    print("\n" + "=" * 100)
    if failures:
        print(" GATE FAILED")
        print("=" * 100)
        for u, arm, intended, n, ok, ps, rs, detail in failures:
            print(f"\n  {u} {arm} (intended {intended}): {ok} of {n} identical")
            print(f"    port applied {ps!r}   reference applied {rs!r}")
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
