"""
buy_shortfall.py -- what a buy does when cash cannot pay for all of it.

    trim    (default, config.BUY_SHORTFALL) the buy is cut to the largest whole
            quantity q with q x fill price + charges(q) <= the cash the rule
            allows, and goes ahead only if q is at least MIN_FILL_PCT of the
            wanted quantity. Below that, or at q = 0, it is refused.
    refuse  the buy is refused whole, the rule before 2026-10-27.

Every buy that sizes against cash goes through trim() below: the engine
(results/test_exposure.py), the reference copy nt_verify re-runs
(nautilus/nt_attribution.py) and the Nautilus port (nautilus/nt_strategy.py).
The drawdown-limit top-up keeps its own rule and does not use it.

The twelfth axis, appended after start in naming.AXES. The suffix is "" at the
default trim, so the canonical names now hold trimmed runs; refuse is "_refuse"
after every other suffix and "@refuse" in directory segments.
"""
import config

CHOICES = ("trim", "refuse")
DEFAULT = config.BUY_SHORTFALL
assert DEFAULT in CHOICES, f"config.BUY_SHORTFALL must be one of {CHOICES}"

_SELECTED = DEFAULT

# THE MINIMUM FILL, a fixed constant and not a run setting. A trimmed buy of
# fewer than half the wanted shares is refused. Without it, trim left stubs of
# one or a few shares that the rule against resizing held names then kept at
# that size while the name stayed a target: on nifty100 tax off, 21 of v1's
# and 21 of v3's 88 trimmed holdings were still held as a target at a later
# rebalance, measured 2026-10-27.
MIN_FILL_PCT = 50

# The reason a buy refused by the minimum is logged under.
BELOW_MINIMUM = "cash short: below minimum fill"


def set_selection(value):
    """Record this run's setting. None restores the default."""
    global _SELECTED
    if value is None:
        _SELECTED = DEFAULT
        return
    if value not in CHOICES:
        raise ValueError(f"buy_shortfall is one of {', '.join(CHOICES)}; got {value!r}")
    _SELECTED = value


def selected():
    return _SELECTED


def is_default():
    return _SELECTED == DEFAULT


def suffix():
    """"" at the default, else "_refuse" -- the artefact name tail."""
    return "" if is_default() else f"_{_SELECTED}"


def segment():
    """"" at the default, else "@refuse" -- the directory segment tail."""
    return "" if is_default() else f"@{_SELECTED}"


def label():
    """The chart-title fragment, "" at the default."""
    return "" if is_default() else "short buys refused"


def meets_minimum(q, q_wanted):
    """True when q is at least MIN_FILL_PCT of q_wanted, in exact integers."""
    return q * 100 >= MIN_FILL_PCT * q_wanted


def trim(q_wanted, cash_allowed, price_at, charges):
    """(q, fill price, charges, reason) for a buy cash cannot fully pay for.

    q is the largest quantity cash pays for (largest_fit) when that is at least
    MIN_FILL_PCT of q_wanted, and reason is None. Otherwise q is 0, the price
    and charges are those of the wanted quantity, and reason is "cash short"
    when not one share fits or BELOW_MINIMUM when some do but too few.
    """
    q, pr, tc = largest_fit(q_wanted, cash_allowed, price_at, charges)
    if q >= 1 and meets_minimum(q, q_wanted):
        return q, pr, tc, None
    reason = "cash short" if q == 0 else BELOW_MINIMUM
    pr = price_at(q_wanted)
    return 0, pr, charges(pr, q_wanted), reason


def largest_fit(q_wanted, cash_allowed, price_at, charges):
    """(q, fill price, charges) for the largest q <= q_wanted that cash can pay for.

    price_at(q) is the fill price of a buy of q shares; it does not depend on q
    under the flat slippage model and rises with q under market impact.
    charges(price, q) is the rupee charge for that leg. A buy of q costs
    q x price_at(q) + charges(price_at(q), q).

    That cost rises strictly with q: the price is non-decreasing in q, and every
    charge component is a rounded (to the rupee or the paisa, half up) multiple
    of the notional, so non-decreasing in it. So the largest q that fits is found
    by starting at an upper bound and stepping down one share at a time until the
    cost fits; the rounding of the charges decides the last step or two. The
    bound is q_wanted, or one more than floor(cash_allowed / price_at(1)) if that
    is smaller: no q above cash_allowed / price_at(1) can fit, since price_at(q)
    >= price_at(1), and the one share more covers a floating-point floor that
    lands one short (0.25 // 0.05 is 4.0, though five shares at Rs 0.05 cost
    exactly Rs 0.25).

    Returns q = 0 (price and charges of the wanted quantity) when not even one
    share fits, or when cash_allowed is not positive.
    """
    if q_wanted < 1:
        raise ValueError(f"largest_fit needs q_wanted >= 1; got {q_wanted}")
    if cash_allowed > 0:
        q = min(int(q_wanted), int(cash_allowed // price_at(1)) + 1)
        while q >= 1:
            pr = price_at(q)
            tc = charges(pr, q)
            if q * pr + tc <= cash_allowed:
                return q, pr, tc
            q -= 1
    pr = price_at(q_wanted)
    return 0, pr, charges(pr, q_wanted)
