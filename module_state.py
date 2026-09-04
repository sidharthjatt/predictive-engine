"""
module_state.py -- save and restore the module-level globals that scripts reassign.
===================================================================================

WHY THIS EXISTS
    Every pipeline step now has a function boundary, so run.py can call them in one
    process instead of spawning thirty-one subprocesses. A subprocess got a clean
    interpreter every time and could not carry anything into the next step. One
    process cannot: whatever a step leaves behind in a shared module is what the
    next step sees.

    Nine scripts in this repository reassign a shared module's globals to steer a
    measurement, and they do it by writing straight into the module object:

        test_exposure.TOP_N     = top_n        validate_topn.py:154
        test_exposure.BUFFER    = BUFFER_PINNED
        test_exposure.REBAL     = rebal        rebal_cadence_sweep.py:172
        nt_strategy.set_sizing("provol")       verify_v34_arms.py
        nt_attribution.set_sizing("provol")
        nt_data.set_tick_size("0.01") / set_tick_mode("fixed") / set_depth_mode(...)
        survivorship.set_mode(...) / set_exit_policy(...)

    THE SHARPEST ONE IS rebal_cadence_sweep.py:172. It sets test_exposure.REBAL to
    each cadence it sweeps and NEVER RESTORES IT. Run in-process before anything
    else, every later step would silently backtest on the wrong rebalance cadence
    and nothing would say so -- the numbers would simply be wrong.

    None of those nine is a pipeline step today, so run.py does not hit this yet.
    That is exactly why the guard goes in now, while the property is true, rather
    than after something has quietly depended on it.

WHAT IT DOES NOT DO
    It does not stop a script mutating a global -- that is how these measurements
    are steered and several of them could not work otherwise. It restores the value
    afterwards, so the mutation cannot outlive the step that made it.

    It also does not cover state that is not a module global: an open matplotlib
    figure, a populated engine_core.MEMBERSHIP built from a file, a pandas option.
    MEMBERSHIP is listed below because it IS a module global; the rest are out of
    scope and stay out of scope rather than being half-covered.

USAGE
    from module_state import pinned
    with pinned():
        step.main()

    Nothing is imported eagerly: a module absent from this tree (nautilus_trader is
    a heavy optional dependency) is skipped, and the guard covers what is loaded.
"""
import sys
from contextlib import contextmanager

# module name -> the globals a caller is known to reassign.
# Recorded per module rather than guessed, so a name added later is a deliberate
# edit here rather than a silent gap.
WATCHED = {
    "test_exposure":  ("TOP_N", "BUFFER", "REBAL", "VOL_WIN", "SLIPPAGE",
                       "START_CAPITAL", "CASH_YIELD"),
    "engine_core":    ("MEMBERSHIP", "TOP_N", "BUFFER", "REBAL"),
    "survivorship":   ("SURVIVORSHIP_MODE", "EXIT_POLICY"),
    "nt_strategy":    ("SIZING", "TOP_N", "BUFFER", "REBAL"),
    "nt_attribution": ("SIZING", "TICK", "TICK_MODE", "TOP_N", "BUFFER", "REBAL"),
    "nt_data":        ("DEPTH_MODE", "TICK_SIZE", "TICK_MODE", "_VOLUME"),
}


def snapshot():
    """Current values of every watched global, for modules that are loaded.

    ONLY ALREADY-IMPORTED MODULES ARE READ. Importing one here to snapshot it would
    make the guard itself a side effect -- nt_data pulls in nautilus_trader, which
    is exactly the kind of cost a step that never touches Nautilus should not pay.
    """
    state = {}
    for name, attrs in WATCHED.items():
        mod = sys.modules.get(name)
        if mod is None:
            continue
        for a in attrs:
            if hasattr(mod, a):
                state[(name, a)] = getattr(mod, a)
    return state


def restore(state):
    """Put every snapshotted value back. Returns what it actually changed."""
    changed = []
    for (name, a), old in state.items():
        mod = sys.modules.get(name)
        if mod is None:
            continue
        new = getattr(mod, a, None)
        if new is not old and new != old:
            setattr(mod, a, old)
            changed.append((name, a, new, old))
    return changed


@contextmanager
def pinned(report=None, on_uncovered=None):
    """Run a step, then put every watched global back the way it was.

    THE GUARANTEE IS LIMITED TO MODULES ALREADY IMPORTED WHEN THE BLOCK OPENS, and
    that limit is real rather than incidental. A module first imported INSIDE the
    block has no entry snapshot, so there is no recorded value to restore it to --
    by the time this code runs again the mutation has already happened and its
    original value is gone. An earlier version of this docstring claimed such a
    module was covered; it was not, and the test for it failed. The claim is
    removed rather than the test weakened.

    What happens instead is that a watched module which appears during the block is
    REPORTED as uncovered, via `on_uncovered`, so the gap is visible at the moment
    it opens rather than discovered later in a wrong number.

    The practical remedy is for the caller to import the shared modules before
    entering the block -- which run.py does anyway, since it must import a step to
    call it.

    `report` takes the list of globals actually restored, so a caller that wants a
    leak to be loud can print it instead of only undoing it.
    """
    before = snapshot()
    loaded_at_entry = {n for n in WATCHED if n in sys.modules}
    try:
        yield
    finally:
        changed = restore(before)
        appeared = {n for n in WATCHED if n in sys.modules} - loaded_at_entry
        if changed and report is not None:
            report(changed)
        if appeared and on_uncovered is not None:
            on_uncovered(sorted(appeared))
