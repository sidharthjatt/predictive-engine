"""
fixed_axis.py -- the FIXED-CAPITAL axis. Default off, and off is unsuffixed.

Off (the default) is the compounded run every published figure comes from: each
rebalance sizes its buys from the whole portfolio, profits included.

On (--fixed-capital) is the non-compounded run that RealTest and Wealth-Lab call
"don't reinvest". At each rebalance open, after the morning's sells and any tax
taken that morning (results/test_exposure.py, backtest_exposure):

    book       = min(base, port_val)        base is --capital
    reserve    = max(0, port_val - base)    profit above the base, never spent
    invest_val = book * exposure * 0.98
    the cash tests read spendable = cash - reserve

Below the base the book is the equity, so losses are not topped up. Held names
are never trimmed, as in the compounded run: a winner can carry the invested
value above the book, and only new purchases are held inside it. Tax, charges
and slippage are paid from the account, as in every run. The idle reserve earns
test_exposure.CASH_YIELD, which is 0.

Refused together with --dd and with the stop arms v5 and v6: both act on the
running peak of compounded equity. Only backtest_exposure has the mode;
engine_core.backtest and the Nautilus port do not.

The tenth axis, appended after pcap in naming.AXES. The suffix is "" when off,
so no existing name moves; otherwise "_fixed" after every other suffix and
"@fixed" in directory segments.
"""
_SELECTED = False


def set_selection(on):
    """Record whether this run is fixed-capital. None or False restores the default."""
    global _SELECTED
    if on is None:
        _SELECTED = False
        return
    if not isinstance(on, bool):
        raise ValueError(f"fixed capital is on or off (a bool); got {on!r}")
    _SELECTED = on


def selected():
    """True when this run is fixed-capital."""
    return _SELECTED


def is_default():
    return not _SELECTED


def suffix():
    """"" when off, else "_fixed" -- the artefact name tail."""
    return "_fixed" if _SELECTED else ""


def segment():
    """"" when off, else "@fixed" -- the directory segment tail."""
    return "@fixed" if _SELECTED else ""


def label():
    """The chart-title fragment, "" when off."""
    return "fixed capital, profits not reinvested" if _SELECTED else ""


REFUSAL = ("--fixed-capital cannot run with {what}: {why} The fixed-capital book is "
           "min(base, equity), and the two rules would act on one account with two "
           "different ideas of its size. Drop one of the two.")


def refusal(dd=False, stop_arms=()):
    """The message run.py prints when the flag meets --dd or a stop arm, or None."""
    if dd:
        return REFUSAL.format(
            what="--dd", why="the drawdown limit sizes the book from the running peak "
                             "of compounded equity.")
    if stop_arms:
        return REFUSAL.format(
            what=f"the stop arm(s) {', '.join(stop_arms)}",
            why="the drawdown stop exits on a fall from the running peak of "
                "compounded equity.")
    return None
