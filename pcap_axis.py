"""
pcap_axis.py -- the PARTICIPATION CAP axis. Default: the profile's own cap.

The cap limits a fill to a fraction of the symbol's prior-20-session median
volume (results/test_exposure.py, _participation_limit), on buys and sells. The
profile sets it: none under research, 1.00 under tradeable (profiles.PROFILES).
--cap replaces the tradeable profile's value for one run and changes nothing
else; profiles.participation_cap() returns it.

Under the research profile there is no cap and no volume series to apply one
to, so any --cap is refused (check_profile), not ignored.

The ninth axis, appended after impact in naming.AXES. The suffix is "" when the
cap is the profile's own, so no existing name moves, including a run that passes
--cap 1.0 under tradeable; otherwise "_pcap0p1" after every other suffix and
"@pcap0p1" in directory segments. "pcap", not "cap": "_cap" is the starting
capital's suffix.
"""
_SELECTED = None


def set_selection(cap):
    """Record this run's cap. None restores the profile's. Called once by run.py."""
    global _SELECTED
    if cap is None:
        _SELECTED = None
        return
    cap = float(cap)
    if not cap > 0:
        raise ValueError(f"participation cap must be positive; got {cap!r}")
    _SELECTED = cap


def selected():
    """The cap passed on the command line, or None when the profile's applies."""
    return _SELECTED


def _profile_cap():
    import profiles
    return profiles.PROFILES[profiles.selected()]["participation_cap"]


def is_default():
    return _SELECTED is None or _SELECTED == _profile_cap()


def _code():
    return f"pcap{_SELECTED:g}".replace(".", "p")


def suffix():
    """"" at the profile's cap, else "_pcap0p1" -- the artefact name tail."""
    return "" if is_default() else "_" + _code()


def segment():
    """"" at the profile's cap, else "@pcap0p1" -- the directory segment tail."""
    return "" if is_default() else "@" + _code()


def label():
    """The chart-title fragment, "" at the profile's cap."""
    return "" if is_default() else f"participation cap {_SELECTED:g}"


def check_profile():
    """Refuse any --cap under the research profile. Called by run.py."""
    import profiles
    if _SELECTED is not None and profiles.is_default():
        raise ValueError(
            f"--cap {_SELECTED:g} needs the tradeable profile: the research profile "
            f"has no participation cap and loads no volume to apply one to. Add "
            f"--profile tradeable, or drop --cap.")
