"""
dd_axis.py -- the DRAWDOWN LIMIT axis. Default off, and off is unsuffixed.

The sixth axis, after arm, cadence, profile, tax and survivorship. When on, the
engine scales every arm's book with the cushion rule of
results/drawdown_overlay.py:

    E = max(F, min(1, m * (W - (1 - L) * M) / W))

W is the close equity, M its all-time peak since the start of the run (never
reset), L the limit, m the multiplier (default 1 / L, fully invested at a peak)
and F the exposure floor (default 25%), which keeps part of the book invested so
the portfolio can recover after the limit is reached.

APPENDED AFTER SURVIVORSHIP IN naming.AXES. The suffix is "" when off, so no
existing name moves; when on, "_dd20" lands after "_pit" ("_dd20m3f10" when m
or the floor is not the default) and "@dd20" after "@pit" in directory segments.

Exploratory: no result with the axis on has been validated. See README.
"""
from dataclasses import dataclass

DEFAULT_FLOOR = 0.25      # 25 percent of the portfolio stays invested at most drawdowns
BAND = 0.05               # no trade unless the invested fraction moves more than 5 points
MAX_LIMIT = 0.50


@dataclass(frozen=True)
class DDLimit:
    """The selected drawdown limit, all as fractions of the portfolio."""
    limit: float           # L
    m: float               # cushion multiplier
    floor: float           # F
    band: float = BAND

    @property
    def m_is_default(self):
        return abs(self.m - 1.0 / self.limit) < 1e-12

    @property
    def floor_is_default(self):
        return abs(self.floor - DEFAULT_FLOOR) < 1e-12


_SELECTED = None


def make(limit_pct, m=None, floor_pct=None):
    """A DDLimit from command-line units: L and F in percent, m as a number."""
    L = float(limit_pct) / 100.0
    if not (0.0 < L <= MAX_LIMIT):
        raise ValueError(f"drawdown limit must be above 0 and at most {MAX_LIMIT:.0%}, "
                         f"got {limit_pct}")
    mm = 1.0 / L if m is None else float(m)
    if not mm > 0:
        raise ValueError(f"--dd-m must be above 0, got {m}")
    F = DEFAULT_FLOOR if floor_pct is None else float(floor_pct) / 100.0
    if not (0.0 < F <= 1.0):
        raise ValueError(f"--dd-floor must be above 0 and at most 100, got {floor_pct}")
    return DDLimit(L, mm, F)


def set_selection(sel):
    """Record this run's selection: a DDLimit, or None for off. Called once by run.py."""
    global _SELECTED
    if sel is not None and not isinstance(sel, DDLimit):
        raise TypeError(f"dd_axis.set_selection takes a DDLimit or None, got {sel!r}")
    _SELECTED = sel


def selected():
    """The DDLimit of this run, or None when the axis is off."""
    return _SELECTED


def is_default():
    return _SELECTED is None


def _num(x):
    """12.5 -> "12p5", 20.0 -> "20": a number safe in a file name."""
    s = f"{x:.4g}"
    return s.replace(".", "p")


def _code():
    s = _SELECTED
    out = f"dd{_num(s.limit * 100)}"
    if not s.m_is_default:
        out += f"m{_num(s.m)}"
    if not s.floor_is_default:
        out += f"f{_num(s.floor * 100)}"
    return out


def suffix():
    """"" when off, else "_dd20" (plus "m<m>" and "f<F>" when not the default)."""
    return "" if is_default() else "_" + _code()


def segment():
    """"" when off, else "@dd20" -- the directory segment tail."""
    return "" if is_default() else "@" + _code()


def label():
    """The chart-title fragment, "" when off."""
    if is_default():
        return ""
    s = _SELECTED
    return (f"dd limit {s.limit * 100:g}% (m {s.m:.3g}, floor {s.floor * 100:g}%)")


def params():
    """The params.json entry when on. Callers add the key only when the axis is on,
    so a run with the axis off writes the file it always wrote."""
    s = _SELECTED
    return {"limit_pct": round(s.limit * 100, 6), "m": round(s.m, 6),
            "m_is_default": s.m_is_default, "floor_pct": round(s.floor * 100, 6),
            "band_pct": round(s.band * 100, 6), "check": "daily, at the close",
            "trades": "next open, proportional across holdings",
            "status": "exploratory, not validated"}


def peak_warning(sel):
    """The warning line when m < 1/L, or None."""
    if sel.m < 1.0 / sel.limit - 1e-12:
        return (f"WARNING: --dd-m {sel.m:g} is below 1/L = {1.0 / sel.limit:g}: the portfolio "
                f"will not be fully invested at a peak (exposure at a peak is "
                f"{min(1.0, sel.m * sel.limit):.0%})")
    return None
