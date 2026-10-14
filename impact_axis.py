"""
impact_axis.py -- the MARKET IMPACT axis. Default 0, and 0 is unsuffixed.

k is the coefficient of slippage.impact, the square-root model

    impact = k * sqrt(order shares / prior-20-session median volume)

added to the flat SLIPPAGE on every buy and every sell. The formula is
slippage.py's and nothing here changes it. k = 0 is the default and means the
impact model is not run at all: backtest_exposure gets impact_k=None, the path
every published run takes, so a default run is the run it always was.

No k is chosen here. The value is the caller's, as in results/impact_sweep.py.

The impact model needs the prior-20-session median volume, which only the
tradeable profile loads. A non-zero k under the research profile is refused
(check_profile), not ignored.

The eighth axis, appended after capital in naming.AXES. The suffix is "" at the
default, so no existing name moves; otherwise "_impact0p003" after every other
suffix but the participation cap's, and "@impact0p003" in directory segments.
"""
DEFAULT = 0.0

_SELECTED = None


def set_selection(k):
    """Record this run's k. None or 0 restores the default. Called once by run.py."""
    global _SELECTED
    if k is None or float(k) == 0.0:
        _SELECTED = None
        return
    k = float(k)
    if not k > 0:
        raise ValueError(f"impact k must be zero or positive; got {k!r}")
    _SELECTED = k


def selected():
    """The run's k, a float. DEFAULT when nothing set one."""
    return DEFAULT if _SELECTED is None else _SELECTED


def is_default():
    return _SELECTED is None


def impact_k():
    """What backtest_exposure takes: None at the default, so the model never runs."""
    return None if is_default() else _SELECTED


def _code():
    return f"impact{_SELECTED:g}".replace(".", "p")


def suffix():
    """"" at the default, else "_impact0p003" -- the artefact name tail."""
    return "" if is_default() else "_" + _code()


def segment():
    """"" at the default, else "@impact0p003" -- the directory segment tail."""
    return "" if is_default() else "@" + _code()


def label():
    """The chart-title fragment, "" at the default."""
    return "" if is_default() else f"impact k {_SELECTED:g}"


def check_profile():
    """Refuse a non-zero k under the research profile. Called by run.py."""
    import profiles
    if not is_default() and profiles.is_default():
        raise ValueError(
            f"--impact {_SELECTED:g} needs the tradeable profile: the impact model "
            f"sizes each fill against the prior-20-session median volume, which the "
            f"research profile does not load. Add --profile tradeable, or drop --impact.")
