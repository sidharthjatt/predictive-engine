"""
survivorship_axis.py -- the SURVIVORSHIP axis. Default static, and static is unsuffixed.

The fifth axis, after arm, cadence, profile and tax. It selects which universe
construction a run uses:

    static   today's index members backfilled to the window start, priced from
             data/raw/Final_Without_Survivorship_Data. Every published figure.
    pit      point-in-time membership from data/raw/Survivorship_Bias, priced from
             data/raw/Final_With_Survivorship_Data, which also holds dropped names.

ONE AUTHORITY. The selection is results/survivorship.py's SURVIVORSHIP_MODE, which
the engine's touch points already read. This module does not hold a second copy:
set_selection() calls survivorship.set_mode() and selected() reads the mode back.

APPENDED AFTER TAX IN naming.AXES, never inserted. The suffix is "" at static, so
every existing name, including every _tax name, is unchanged; a pit run writes
"_pit" after the tax suffix ("v34_equity_tax_pit.csv") and "@pit" after "@tax" in
directory segments.
"""
import sys
from pathlib import Path

_RESULTS = Path(__file__).resolve().parent / "results"
if str(_RESULTS) not in sys.path:
    sys.path.insert(0, str(_RESULTS))
import survivorship as _sv  # noqa: E402

DEFAULT = "static"
CHOICES = ("static", "pit")


def set_selection(mode):
    """Record this run's selection. None restores the default."""
    _sv.set_mode(DEFAULT if mode is None else mode)


def selected():
    return _sv.SURVIVORSHIP_MODE


def is_default():
    return selected() == DEFAULT


def suffix():
    """"" when static, "_pit" when pit -- the artefact name tail."""
    return "" if is_default() else "_pit"


def segment():
    """"" when static, "@pit" when pit -- the directory segment tail."""
    return "" if is_default() else "@pit"
