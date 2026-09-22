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
