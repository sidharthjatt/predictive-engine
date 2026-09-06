"""
cadence.py -- the rebalance cadence this run selected.

WHY THIS IS NOT A MODULE GLOBAL ON test_exposure
    module_state.py already names the hazard, by file and line:

        THE SHARPEST ONE IS rebal_cadence_sweep.py:172. It sets
        test_exposure.REBAL to each cadence it sweeps and NEVER RESTORES IT. Run
        in-process before anything else, every later step would silently backtest
        on the wrong rebalance cadence and nothing would say so -- the numbers
        would simply be wrong.

    So the cadence is never written into test_exposure. It is recorded here and
    handed to `backtest_exposure(..., rebal=n)` as an ARGUMENT, which that
    function has accepted since the cadence work began. A parameter cannot leak
    into the next step; a global can, and once did.

WHAT THE DEFAULT MEANS
    20 trading days. `selected()` returns 20 when nothing set a cadence, which is
    what every engine's hardcoded REBAL already was -- so a default run passes
    rebal=20 where it used to pass nothing, and `_rebal = REBAL if rebal is None
    else int(rebal)` resolves both to the same 20. Byte-identical by construction.

THE FROZEN UNIVERSES HAVE EXACTLY ONE CADENCE
    58 and 74 are retired: their published numbers must not move, their engines
    pin REBAL=20, and the Nautilus port that certifies them is pinned to 20 too.
    run.py refuses a non-default cadence for them rather than running it, so
    nothing here needs to special-case them -- but the reason is recorded because
    the refusal looks arbitrary without it.
"""
DEFAULT = 20

_SELECTED = None


def set_selection(n):
    """Record this run's cadence. Called once by run.py. None restores the default."""
    global _SELECTED
    if n is None:
        _SELECTED = None
        return
    n = int(n)
    if n < 1:
        raise ValueError(f"rebalance cadence must be >= 1 trading day, got {n}")
    _SELECTED = n


def selected():
    """The cadence in trading days. DEFAULT when nothing set one."""
    return DEFAULT if _SELECTED is None else _SELECTED


def is_default():
    return selected() == DEFAULT


def suffix():
    """"" at the default cadence, "_r40" otherwise -- the artefact name tail.

    THE DEFAULT IS UNSUFFIXED so every published filename keeps the name it has
    always had, and only a non-default cadence writes a file of its own. Same rule
    the universe and arm axes use.
    """
    return "" if is_default() else f"_r{selected()}"
