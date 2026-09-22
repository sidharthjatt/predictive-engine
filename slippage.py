"""slippage.py -- the execution slippage constant, in one place.

WHY THIS EXISTS. SLIPPAGE = 0.0015 was written out SEVEN times:

    results/test_exposure.py:61        results/engine_core.py:140
    results/make_daily_log.py:37       results/check_b_exec_timing.py:44
    nautilus/nt_run.py:73              nautilus/nt_attribution.py:64
    depth_compare.py:40                (derived from nt_run, not a definition)

nt_run's carried the comment "matches SLIPPAGE in results/test_exposure.py",
which is a duplicate admitting it is one. This repository already records
VOL_WIN = 60 having sixteen independent definitions and no central home, and four
tables -- REQUIRED_INPUTS, PIPELINE_ORDER, REPORT_ORDER, FILES -- that each went
stale as copies. An execution constant is a bad candidate for the next one.

WHY IT MATTERS MORE THAN AN ORDINARY DUPLICATE. These seven live in engines that
are CROSS-CHECKED AGAINST EACH OTHER. nt_verify reconciles the Nautilus port
against nt_attribution and against test_exposure's holdings; make_daily_log
reconciles a cash identity against the same fills; check_b_exec_timing asserts
fill prices. A value changed in one and not the others does not produce a wrong
number in that file -- it produces a reconciliation failure somewhere else, which
is the shape this repository has spent real time chasing.

THIS MODULE CHANGES NO BEHAVIOUR. The value is 0.0015, exactly what all seven
carried. It is a move, not an edit. A size-sensitive model replacing the flat
rate is a SEPARATE change, scoped to the `tradeable` profile so `research` stays
byte-exact, and it belongs here once it exists.

WHAT SLIPPAGE MEANS HERE. A fraction of the fill price, applied symmetrically and
independent of order size: a BUY pays price * (1 + SLIPPAGE), a SELL receives
price * (1 - SLIPPAGE). It does not vary with quantity, with the symbol's
liquidity, or with the participation cap. That flatness is a known limitation of
the execution model, not a property of the market.
"""

# 0.0015 = 15 basis points each way. Unchanged from every site it replaces.
SLIPPAGE = 0.0015


class MissingVolume(Exception):
    """A size-sensitive fill had no prior-20-session median volume to size against.

    RAISED, NOT SWALLOWED, AND THAT IS THE WHOLE POINT. The alternative is to fall
    back to the flat rate for that fill, which produces a run whose output says
    "tradeable" and whose fills are partly research arithmetic, with nothing in
    the artefact saying which. This repository already has that defect recorded
    twice -- the cap that was passed without vol20 and silently applied to
    nothing, and the tradeable artefacts that were byte-identical to their
    research twins under a tradeable filename. A third instance is not wanted.
    """


def impact(qty, median_vol, k):
    """Square-root market impact as a fraction of price, on top of SLIPPAGE.

        impact = k * sqrt(qty / median_vol)

    `qty` is the order size in shares, `median_vol` the symbol's prior-20-session
    MEDIAN volume -- prior so it never uses the day's own volume, median so a
    single block trade does not licence a large fill. Both are the same inputs
    the participation cap already uses, deliberately: two different notions of
    "how big is this order relative to what trades" would be two things to keep
    in step.

    k IS NOT DEFAULTED HERE. It is swept, and a number nobody measured has no
    business being a default in an execution model.

    RAISES MissingVolume when `median_vol` is absent or non-positive. See above.

    THE TOTAL RATE IS SLIPPAGE + impact: a fixed spread cost plus a size term
    that vanishes for a small order. At k=0.002 an order at 10% of median volume
    pays 0.002*sqrt(0.1) = 6.3 bp on top of the 15 bp base; one at 100% of median
    pays 20 bp on top. That convexity is the point -- the flat rate charges the
    same 15 bp either way.
    """
    if median_vol is None or median_vol != median_vol or median_vol <= 0:
        raise MissingVolume(
            f"size-sensitive fill of {qty:,} share(s) has no usable prior-20d "
            f"median volume (got {median_vol!r}); refusing to fall back to the "
            f"flat rate, which would put research arithmetic in a tradeable "
            f"artefact")
    if qty <= 0:
        return 0.0
    return float(k) * (float(qty) / float(median_vol)) ** 0.5


def buy_price(raw, qty, median_vol, k):
    """Fill price paid for a BUY. k=None is the flat model, unchanged."""
    return raw * (1 + SLIPPAGE + (0.0 if k is None else impact(qty, median_vol, k)))


def sell_price(raw, qty, median_vol, k):
    """Fill price received for a SELL. k=None is the flat model, unchanged."""
    return raw * (1 - SLIPPAGE - (0.0 if k is None else impact(qty, median_vol, k)))
