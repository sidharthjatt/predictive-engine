"""
portfolio.py -- what the strategy holds and how it trades, day by day.

Sections, in order:
  1. arms: Arm, ARMS, STOP_ARMS, the drawdown-stop seal, what a run selected
  2. the buy-shortfall rule: trim, largest_fit, MIN_FILL_PCT
  3. the drawdown-limit overlay: OverlayState, marginal_tax
  4. the drawdown stop of v5 and v6: StopState
  5. ranking, sizing, buy and sell decisions and the daily loop:
     breadth_momentum, the participation limit, backtest_exposure

The panel and point-in-time membership are in market_data.py, the model and
scores in model.py, slippage, charges and the tax rules in costs.py.
"""
import math
import os
import subprocess
import warnings
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

import costs        # the tax RULES; this file owns the cash
import market_data
import settings            # the run's execution-realism profile
from costs import calc_tc  # the one copy; see costs.py
# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from costs import SLIPPAGE
from settings import capital_axis as _capital_axis


# ======================================================================================
# ARMS: WHAT AN ARM IS, THE DRAWDOWN-STOP SEAL, WHAT A RUN SELECTED. From arms/registry.py (moved 2026-11-27).
# ======================================================================================
# arms/registry.py -- the single definition of what an ARM is.
# ============================================================
#
# WHY THIS IS SHORT, AND WHY IT STILL EARNS A FILE
#     Unlike universes, the arms were never duplicated: they are two keyword
#     arguments to `portfolio.backtest_exposure`, and backtest_runs.py already
#     assembles the four named combinations in one place. There is no nineteen-way
#     duplication to collapse here.
#
#     What IS scattered is the NAMING. "v1".."v4" appear as label strings in
#     v34_common, as a list of pairs in verify_v34_arms, and as column names in
#     v34_equity.csv -- and those three did not agree.
#
#     Until 2026-09-04 verify_v34_arms.ARMS listed only SIZING, pairing v1 with v2
#     and v3 with v4, because the Nautilus port had no exposure mode at all and
#     always ran at breadth: its "four arms" were two configurations run twice. The
#     port now takes mode, so the four arms are four arms and this module is the one
#     definition all of them read.
#
#     This module names the four arms once, in terms of the two parameters that
#     actually produce them, so a caller cannot invent a fifth spelling.
#
# NOTHING HERE CHANGES BEHAVIOUR. The values are exactly those v34_common passes.
#
# THE STOP ARMS, v5 AND v6 (2026-10-02, experiments/DRAWDOWN_STOP_PREREG.txt).
#     v5 is v1 plus the drawdown stop and v6 is v3 plus the stop. They live in
#     STOP_ARMS, not in ARMS. ARMS stays the core four: everything that iterates it,
#     `--arm all`, the full-selection test and the canonical v34_* files see exactly
#     what they saw before. A stop arm is selected by name and writes companion
#     v34_stop_* files. They join the core set only if the measurement accepts them.
#
#     THE STOP IS SEALED until the band file of the pre-registration is committed:
#     Arm.kwargs raises for a stop arm, and portfolio.StopState refuses
#     the registered threshold however it was passed, so no engine, port or audit
#     can run one at that threshold before then. One thing passes the seal: the test
#     fixture below, which replaces the threshold and is never a result.

_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DrawdownStop:
    """The stop of v5 and v6. Fixed by the pre-registration; never tuned.

    threshold        exit when close equity <= (1 - threshold) x running peak
    cooldown_cycles  rebalance cycles in cash, counted from the day the book is flat
    reentry_breadth  re-enter on a rebalance day whose breadth is at least this
    """
    threshold: float = 0.20
    cooldown_cycles: int = 1
    reentry_breadth: float = 0.50


REGISTERED_STOP = DrawdownStop()

# THE BAND FILE. The seal lifts when it is tracked by git at the checked-out commit.
BAND_FILE = _ROOT / "experiments" / "DRAWDOWN_STOP_BAND.csv"

# THE TEST FIXTURE. A threshold in (0, 1] given in this environment variable
# replaces the registered one for every stop arm in the process and its children.
# It exists for the gates of stage 3 (0.01 to force exits, 1.0 to force none) and
# for nothing else: a run under it is a test of the wiring, never a result.
FIXTURE_ENV = "DRAWDOWN_STOP_FIXTURE"


class StopSealed(RuntimeError):
    pass


def fixture_threshold():
    """The fixture threshold, or None when no fixture is set."""
    raw = os.environ.get(FIXTURE_ENV)
    if raw in (None, ""):
        return None
    t = float(raw)
    if not 0.0 < t <= 1.0:
        raise ValueError(f"{FIXTURE_ENV}={raw!r}: a fixture threshold must be in (0, 1]")
    if t == REGISTERED_STOP.threshold:
        raise StopSealed(f"{FIXTURE_ENV}={raw!r} is the registered threshold; a fixture "
                         "cannot be used to run the registered stop")
    return t


def stop_sealed():
    """True until BAND_FILE exists and git tracks it."""
    if not BAND_FILE.exists():
        return True
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(BAND_FILE)],
                       cwd=_ROOT, capture_output=True)
    return r.returncode != 0


def require_unsealed(stop):
    """Refuse to run the registered stop while it is sealed.

    Called by results/drawdown_stop.StopState for every stop any loop runs -- the
    engine, the reference copy and the port -- so the seal holds however the stop
    was obtained, not only through Arm.kwargs. A fixture threshold passes; the
    registered threshold passes only once BAND_FILE is tracked.
    """
    if stop.threshold != REGISTERED_STOP.threshold:
        return
    if stop_sealed():
        raise StopSealed(
            "the drawdown stop is sealed: no run at the registered threshold before "
            f"{BAND_FILE.relative_to(_ROOT)} is committed "
            "(experiments/DRAWDOWN_STOP_PREREG.txt, SEALING)")


def stop_in_force(stop):
    """The DrawdownStop a run uses: the fixture's threshold if set, else the
    registered stop, which is refused while sealed."""
    t = fixture_threshold()
    if t is not None:
        return replace(stop, threshold=t)
    if stop_sealed():
        raise StopSealed(
            "the drawdown stop is sealed: no v5 or v6 run at the registered "
            f"threshold before {BAND_FILE.relative_to(_ROOT)} is committed "
            "(experiments/DRAWDOWN_STOP_PREREG.txt, SEALING). For a wiring test "
            f"set {FIXTURE_ENV}=0.01; such a run is never a result.")
    return stop


@dataclass(frozen=True)
class Arm:
    """One arm = one (exposure mode, sizing rule) pair, optionally with the stop.

    `mode` and `sizing` are passed straight to test_exposure.backtest_exposure:
        mode   -- "none" (always 100% invested) | "breadth" (scale by breadth)
                  the function also accepts "const", which no named arm uses.
        sizing -- "invvol" (w = 1/vol) | "provol" (w = vol) | "equal"
    `stop` is None for the core four. For v5 and v6 it is REGISTERED_STOP and
    `parent` names the core arm the stop is added to.
    """
    name: str
    mode: str
    sizing: str
    label: str          # the exact string v34_common writes into its artefacts
    equity_column: str  # the exact column name in v34_equity.csv
    stop: DrawdownStop = None
    parent: str = None

    @property
    def kwargs(self):
        """What to hand backtest_exposure for this arm.

        The core four get exactly {"mode", "sizing"}, as before. A stop arm adds
        drawdown_stop, resolved through the seal and the fixture.
        """
        kw = {"mode": self.mode, "sizing": self.sizing}
        if self.stop is not None:
            kw["drawdown_stop"] = stop_in_force(self.stop)
        return kw


ARMS = {a.name: a for a in (
    Arm("v1", "none",    "invvol",
        "v1 invvol, 100% invested",  "v1_invvol_none"),
    Arm("v2", "breadth", "invvol",
        "v2 invvol, breadth-scaled", "v2_invvol_breadth"),
    Arm("v3", "none",    "provol",
        "v3 provol, 100% invested",  "v3_provol_none"),
    Arm("v4", "breadth", "provol",
        "v4 provol, breadth-scaled", "v4_provol_breadth"),
)}

STOP_ARMS = {a.name: a for a in (
    Arm("v5", "none", "invvol",
        "v5 invvol, 100% invested, drawdown stop", "v5_invvol_none_stop",
        stop=REGISTERED_STOP, parent="v1"),
    Arm("v6", "none", "provol",
        "v6 provol, 100% invested, drawdown stop", "v6_provol_none_stop",
        stop=REGISTERED_STOP, parent="v3"),
)}

# Every arm that can be named on the command line: the core four, then the stop arms.
ALL_ARMS = {**ARMS, **STOP_ARMS}

# The two that ship on every universe. v3 and v4 are computed only for the live
# universes, inside backtest_runs.run_v34.
SHIPPING = [ARMS["v1"], ARMS["v2"]]


# ---------------------------------------------------------------------------
# WHAT THIS RUN SELECTED -- the same distinction settings.py draws.
# ---------------------------------------------------------------------------
# ARMS answers "which arms exist". A run answers "which arms did the caller ask
# for". run_v34 conflated the two: it computed and wrote all four unconditionally,
# so `--arm v1,v3` still produced a v34_comparison.csv with v2 and v4 rows in it.
#
# THE DEFAULT IS ALL FOUR, which is exactly what run_v34 saw before this existed,
# so a full run and any standalone import behave as they always did.
#
# WHY THIS IS NOT THE WHOLE STORY, AND THAT IS DELIBERATE. v1 and v2 are not only
# measurement arms: they are the SHIPPING strategy and its control, computed by
# each engine and written as the `strategy` and `baseline_invvol` COLUMNS of
# v2FINAL_equity.csv. The daily audit trail asserts against that file, and the
# combined, fair-comparison and summary outputs read those two columns and know
# nothing of v3/v4. Selection therefore reaches the v34 MEASUREMENT artefacts and
# the per-arm run directories; making v2FINAL_* arm-aware means restructuring it
# into per-arm columns and re-baselining the seven identity gates, which is its
# own step. See KNOWN_ISSUES.md.
_SELECTED = None


def set_selection(names):
    """Record which arms this run selected. Called once by run.py.

    Unknown names raise rather than narrowing the selection silently. Passing
    None restores the default.
    """
    global _SELECTED
    if names is None:
        _SELECTED = None
        return
    want = [a.name if hasattr(a, "name") else a for a in names]
    unknown = [n for n in want if n not in ALL_ARMS]
    if unknown:
        raise KeyError(f"cannot select unknown arm(s) {', '.join(unknown)}; "
                       f"known: {', '.join(ALL_ARMS)}")
    _SELECTED = [n for n in ALL_ARMS if n in set(want)]


def selected_names():
    """The arm names this run is working on, in ALL_ARMS order. Defaults to the
    core four; a stop arm is in it only when selected by name."""
    return list(ARMS) if _SELECTED is None else list(_SELECTED)


def selected():
    """selected_names() as Arm objects."""
    return [ALL_ARMS[n] for n in selected_names()]


def selected_core():
    """The selected arms that are in the core set, as Arm objects."""
    return [a for a in selected() if a.name in ARMS]


def selected_stop():
    """The selected stop arms, as Arm objects."""
    return [a for a in selected() if a.name in STOP_ARMS]


def stop_selection_suffix(names=None):
    """"" when both stop arms are selected, "_v5" or "_v6" for one of them: the
    tail of the companion v34_stop_* artefacts, the counterpart of
    selection_suffix() for the core files."""
    n = selected_names() if names is None else [
        a.name if hasattr(a, "name") else a for a in names]
    s = [x for x in STOP_ARMS if x in set(n)]
    return "" if set(s) == set(STOP_ARMS) else "_" + "_".join(s)


def is_full_selection(names=None):
    """True when every one of the four arms is in play.

    THE CANONICAL v34_* ARTEFACTS ARE WRITTEN ONLY ON A FULL SELECTION, and this
    is the predicate that decides it. v34_comparison.csv is the four-arm table
    that seven identity gates read -- six of them assert on its v2 row -- so
    overwriting it with a two-arm subset would leave those gates comparing against
    a table that no longer contains their reference, and they would find out later
    and elsewhere. A subset writes its own selection-named files instead.
    """
    n = selected_names() if names is None else [
        a.name if hasattr(a, "name") else a for a in names]
    return set(n) == set(ARMS)


def selection_suffix(names=None):
    """"" for a full selection, "_v1_v3" for a subset -- the artefact name tail."""
    if is_full_selection(names):
        return ""
    n = selected_names() if names is None else [
        a.name if hasattr(a, "name") else a for a in names]
    return "_" + "_".join(x for x in ALL_ARMS if x in set(n))


def get(name):
    try:
        return ALL_ARMS[name]
    except KeyError:
        raise KeyError(
            f"unknown arm {name!r}; known: {', '.join(ALL_ARMS)}") from None


# ---------------------------------------------------------------------------
# READING AN ARM'S CURVE OUT OF v2FINAL_equity.csv
# ---------------------------------------------------------------------------
# That file was written with columns named for what a curve was FOR, not for
# which arm it IS: `strategy` is v2 and `baseline_invvol` is v1. Nothing could
# ask it for v3 or v4, because those names have no slot. The live engines now
# also write the arm-keyed names (Arm.equity_column), and every reader goes
# through equity_series() below.
#
# THE RETIRED UNIVERSES (deleted 2026-09-11) WROTE ONLY THE OLD NAMES: their
# engines were those universes' provenance and were never modified. So the lookup
# tries the arm-keyed name and falls back to the legacy one. That fallback is not
# a transition shim to be deleted later -- it is how a frozen universe's file is
# read, permanently.
LEGACY_EQUITY_COLUMN = {"v1": "baseline_invvol", "v2": "strategy"}


def suffix(names):
    """"_v1_v3" for any set of arms, INCLUDING the full four.

    NOT selection_suffix(). That one is empty for a full selection because it
    names the CANONICAL v34 artefacts, which only a four-arm run may write. This
    one always names what is on the figure, because a chart drawn over all four
    arms is an additional file sitting beside the published two-arm one and needs
    a name of its own.
    """
    n = {a.name if hasattr(a, "name") else a for a in names}
    return "_" + "_".join(x for x in ALL_ARMS if x in n)


def equity_series(df, arm):
    """One arm's equity curve from a v2FINAL_equity.csv frame, or None.

    None means "this file does not carry that arm" -- asking a frozen universe
    for v3 is a legitimate question with the answer "there isn't one", and the
    caller decides whether that is a skip or an error. Raising here would make
    every caller wrap it in a try.
    """
    name = arm.name if hasattr(arm, "name") else arm
    if name not in ALL_ARMS:
        raise KeyError(f"unknown arm {name!r}; known: {', '.join(ALL_ARMS)}")
    for col in (ALL_ARMS[name].equity_column, LEGACY_EQUITY_COLUMN.get(name)):
        if col is not None and col in df.columns:
            return df[col]
    return None


# Core arms only: v5 and v6 share v1's and v3's (mode, sizing) and are told apart
# by their stop. path_segment takes the stop for that reason.
_BY_PARAMS = {(a.mode, a.sizing): a for a in ARMS.values()}
_STOP_BY_PARAMS = {(a.mode, a.sizing): a for a in STOP_ARMS.values()}


def by_params(mode, sizing):
    """The named arm for a (mode, sizing) pair, or None if it is not one of the four.

    backtest_exposure accepts a mode ("const") and a sizing
    ("equal") that no named arm uses, so this is deliberately partial: a caller that
    needs a name for an unnamed combination should say so in its own terms rather
    than have one invented here. See path_segment().
    """
    return _BY_PARAMS.get((mode, sizing))


def path_segment(mode, sizing, drawdown_stop=None):
    """A filesystem-safe directory name identifying one (mode, sizing) combination.

    A named arm gives its name -- "v3". Anything else gives "{mode}-{sizing}", which
    is still unique and still readable, so an exploratory combination writes beside
    the four named ones instead of into one of them. This is total by design: the
    point of the segment is that two different configurations cannot land in the
    same directory, and raising on the unnamed case would just push the collision
    back to whichever caller shrugged and passed a constant.
    """
    if drawdown_stop is not None:
        a = _STOP_BY_PARAMS.get((mode, sizing))
        return a.name if a is not None else f"{mode}-{sizing}-stop"
    a = by_params(mode, sizing)
    return a.name if a is not None else f"{mode}-{sizing}"


# ======================================================================================
# THE BUY-SHORTFALL RULE: TRIM OR REFUSE A BUY CASH CANNOT PAY FOR. From buy_shortfall.py (moved 2026-11-27).
# ======================================================================================
# buy_shortfall.py -- what a buy does when cash cannot pay for all of it.
#
#     trim    (default, settings.BUY_SHORTFALL) the buy is cut to the largest whole
#             quantity q with q x fill price + charges(q) <= the cash the rule
#             allows, and goes ahead only if q is at least MIN_FILL_PCT of the
#             wanted quantity. Below that, or at q = 0, it is refused.
#     refuse  the buy is refused whole, the rule before 2026-10-27.
#
# Every buy that sizes against cash goes through trim() below: the engine
# (portfolio.py), the reference copy nt_verify re-runs
# (nautilus/nt_attribution.py) and the Nautilus port (nautilus/nt_strategy.py).
# The drawdown-limit top-up keeps its own rule and does not use it.
#
# The selection (trim or refuse) is settings.shortfall_axis, the twelfth axis in
# settings.AXES. The suffix is "" at the default trim, so the canonical names hold
# trimmed runs; refuse is "_refuse" after every other suffix and "@refuse" in
# directory segments.

# THE MINIMUM FILL, a fixed constant and not a run setting. A trimmed buy of
# fewer than half the wanted shares is refused. Without it, trim left stubs of
# one or a few shares that the rule against resizing held names then kept at
# that size while the name stayed a target: on nifty100 tax off, 21 of v1's
# and 21 of v3's 88 trimmed holdings were still held as a target at a later
# rebalance, measured 2026-10-27.
MIN_FILL_PCT = 50

# The reason a buy refused by the minimum is logged under.
BELOW_MINIMUM = "cash short: below minimum fill"


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


# ======================================================================================
# THE DRAWDOWN-LIMIT OVERLAY. From results/drawdown_overlay.py (moved 2026-11-27).
# ======================================================================================
# drawdown_overlay.py -- the drawdown-limit axis (settings.dd_axis) as one state class.
#
# THE RULE. At each close, with W the close equity and M its all-time peak since
# the start of the run (never reset):
#
#     C = W - (1 - L) * M                      the cushion
#     E = max(F, min(1, m * C / W))            the overlay's exposure limit
#
# The arm still decides which names to hold and, for v2/v4, its own exposure A
# (1 for v1/v3). The overlay only cuts. With x the invested fraction at the close:
#
#     trim     when x > min(E, A) + band        to min(E, A)
#     top-up   only after a trim, when x < min(E, 0.98 A) - band, or, once E is 1,
#              when the gap is more than SNAP   to min(E, 0.98 A)
#
# 0.98 is the arm's own haircut on invest_value, so a top-up never buys more than
# the arm itself would. "Only after a trim" keeps the overlay from investing cash
# the arm chose to hold (v2/v4 breadth, cash-short residuals). The trim flag clears
# once the book is back within SNAP of the arm's own level, 0.98 A.
#
# TRADES. The order is placed at the close and filled at the next open. Each held
# name is resized by the same ratio r = target / x: floor(shares * (1 - r)) sold,
# or floor(shares * (r - 1)) bought. Quantities are fixed at the close; prices are
# the next open's. The caller fills them after the arm's own orders that morning,
# through its normal slippage, charges, participation cap and tax ledger, and skips
# a name the arm or a forced exit has already sold. Entrants bought that morning
# are sized at min(E, A) instead of A, so they are not bought full and trimmed the
# same morning (entry_factor).
#
# NO MULTIPLIER IS CARRIED BETWEEN DAYS. The first version tracked a multiplier k of
# the arm's book and inferred the arm's own exposure as x / k. Prices move the
# invested fraction without a trade, so that inference drifted: on a synthetic
# recovery k stayed at 0.79 with the book 99.9% invested. Every decision now reads
# the actual book.
#
# ONE CLASS, THREE LOOPS: portfolio.backtest_exposure,
# nautilus/nt_attribution.run and nautilus/nt_strategy.PredictiveEngineStrategy.
# This file decides; the callers own cash, holdings and fills.
#
# Exploratory: no result with the axis on has been validated.

SNAP = 0.01       # 1 point of the portfolio: the minimum move back to full once E is 1
HAIRCUT = 0.98    # the arm's own haircut on invest_value (test_exposure, nt_strategy)


class OverlayState:
    def __init__(self, cfg, start_capital):
        self.cfg = cfg
        self.peak = float(start_capital)       # M; the start is the first peak
        self.peak_date = None
        self.E = 1.0                           # the limit decided at the last close
        self.cut = False                       # True from a trim until the book is restored
        self.order = None                      # {symbol: signed qty} for the next open
        self.events = []                       # one dict per order and per fill
        self.worst_dd = 0.0                    # most negative W / M - 1 at a close
        self.worst_date = None
        self.worst_peak_date = None
        self.sessions_below = 0                # closes with W < (1 - L) * M
        self.days_at_floor = 0                 # closes where E was held up by the floor
        self.n_orders = 0
        self.last_invested = None

    # ------------------------------------------------------------------ rule
    def target(self, W):
        """E for close equity W against the current peak."""
        L, m, F = self.cfg.limit, self.cfg.m, self.cfg.floor
        if W <= 0:
            return F
        C = W - (1.0 - L) * self.peak
        raw = m * C / W
        # AT A PEAK m * C / W IS m * L, WHICH IS 1 AT THE DEFAULT m = 1 / L, but in
        # floating point it lands a rounding error above or below 1 depending on W.
        # The two sides of nt_verify carry W a few rupees apart, so one read E = 1
        # (the snap back to full) and the other 0.9999999999 (the band), and their
        # books parted on nifty50 v1 on 2019-03-14. Within 1e-9 of 1 is 1.
        if abs(raw - 1.0) < 1e-9:
            raw = 1.0
        return max(F, min(1.0, raw))

    def entry_factor(self, arm_expo):
        """Multiplier on the arm's invest_value for entrants at the next open:
        min(E, A) / A, from the E decided at the last close."""
        if arm_expo <= 0:
            return 1.0
        return min(1.0, self.E / arm_expo)

    # ------------------------------------------------------------ at the close
    def at_close(self, date, W, mtm, shares, last, arm_expo):
        """Update the peak and the drawdown record, and decide the next open's order.

        `shares` is {symbol: qty} at this close, `arm_expo` the arm's own exposure
        (A). Sets self.order (or None) and returns it. Nothing is ordered on the
        last session.
        """
        cfg = self.cfg
        L = cfg.limit
        if W > self.peak:
            self.peak, self.peak_date = float(W), date
        dd = W / self.peak - 1.0
        if dd < self.worst_dd:
            self.worst_dd, self.worst_date, self.worst_peak_date = dd, date, self.peak_date
        if W < (1.0 - L) * self.peak:
            self.sessions_below += 1
        E = self.target(W)
        raw = (cfg.m * (W - (1.0 - L) * self.peak) / W) if W > 0 else 0.0
        if raw < cfg.floor and E == cfg.floor:
            self.days_at_floor += 1
        self.E = E
        self.order = None
        x = (mtm / W) if W > 0 else 0.0
        self.last_invested = x
        if x <= 0:
            return None
        t_cut = min(E, arm_expo)
        t_up = min(E, HAIRCUT * arm_expo)
        kind, tgt = None, None
        if x - t_cut > cfg.band:
            kind, tgt = "trim", t_cut
        elif self.cut and t_up - x > (cfg.band if E < 1.0 else SNAP):
            kind, tgt = "top-up", t_up
        elif self.cut and x >= HAIRCUT * arm_expo - SNAP:
            # Restored to the arm's own level, not merely to the overlay's target:
            # right after a trim the book sits at its target, and clearing the flag
            # there stopped every later top-up.
            self.cut = False
        if kind is None or last:
            return None
        r = tgt / x
        order = {}
        for s, q in sorted(shares.items()):
            dq = math.floor(q * (1.0 - r)) if r < 1.0 else math.floor(q * (r - 1.0))
            if dq >= 1:
                order[s] = -int(dq) if r < 1.0 else int(dq)
        if kind == "trim":
            self.cut = True
        self.events.append({"date": date, "event": kind + " order", "equity": W,
                            "peak": self.peak, "drawdown_pct": dd * 100,
                            "limit_exposure_pct": E * 100, "arm_exposure_pct": arm_expo * 100,
                            "invested_pct": x * 100, "target_invested_pct": tgt * 100,
                            "names": len(order),
                            "detail": f"{kind} every holding by {abs(1.0 - r):.2%} at the next open"})
        self.n_orders += 1
        self.order = order or None
        return self.order

    # ---------------------------------------------------------- after the fills
    def after_fills(self, date, before, after):
        """Record what filled. `before` and `after` are {symbol: qty} for the names
        in the order, before and after the overlay's own fills."""
        moved = sum(abs(after.get(s, 0) - q) for s, q in before.items())
        self.events.append({"date": date, "event": "filled", "equity": None, "peak": self.peak,
                            "drawdown_pct": None, "limit_exposure_pct": None,
                            "arm_exposure_pct": None, "invested_pct": None,
                            "target_invested_pct": None, "names": len(before),
                            "detail": f"{moved:,} shares across {len(before)} names"})
        self.order = None

    def cancel(self):
        """The order is dropped (nothing it names is still held)."""
        self.order = None

    # ----------------------------------------------------------------- report
    def summary(self):
        L = self.cfg.limit
        breach = -self.worst_dd - L
        return {"limit_pct": L * 100, "m": self.cfg.m, "floor_pct": self.cfg.floor * 100,
                "band_pct": self.cfg.band * 100,
                "worst_dd_pct": self.worst_dd * 100, "worst_date": self.worst_date,
                "worst_peak_date": self.worst_peak_date,
                "breached": breach > 1e-12, "breach_points": max(0.0, breach) * 100,
                "sessions_below_limit": self.sessions_below,
                "days_at_floor": self.days_at_floor, "orders": self.n_orders,
                "invested_final_pct": (self.last_invested or 0.0) * 100}


def marginal_tax(ledger_rows, dd_row_ids):
    """Tax caused by the overlay's sales, as a marginal figure: each financial
    year's tax on every realised gain, less its tax with the gains realised by the
    overlay's sales left out. Losses are set off within a year, so this is not an
    exact attribution; it is what those sales added to the bills."""
    import pandas as pd
    import costs
    if not ledger_rows:
        return 0.0
    df = pd.DataFrame(ledger_rows)
    keep = df[[i not in dd_row_ids for i in range(len(df))]]

    def total(lots):
        return sum(t["total_tax"]
                   for t in costs.assess_years(costs.realized_buckets(lots)).values())
    return total(df) - total(keep)


EVENT_COLUMNS = ["date", "event", "equity", "peak", "drawdown_pct", "limit_exposure_pct",
                 "arm_exposure_pct", "invested_pct", "target_invested_pct", "names", "detail"]


# ======================================================================================
# THE DRAWDOWN STOP OF v5 AND v6. From results/drawdown_stop.py (moved 2026-11-27).
# ======================================================================================
# drawdown_stop.py -- the drawdown stop of v5 and v6, as one state machine.
#
# experiments/DRAWDOWN_STOP_PREREG.txt states the rule. This file is the only
# implementation of it. Three loops call it, each at the same four points of its
# trading day:
#     portfolio.backtest_exposure   the engine every published arm runs
#     nautilus/nt_attribution.run               the reference copy nt_verify compares with
#     nautilus/nt_strategy.PredictiveEngineStrategy   the port
# The caller owns its orders, cash and holdings. This class only decides when the
# arm must sell everything, when it may place its normal order again, and when the
# peak resets, and it writes down why.
#
# STATES
#     IN           the running peak of close equity is updated each close. A close at
#                  or below (1 - threshold) x peak triggers an exit at the next open.
#     LIQUIDATING  an order to sell every holding stands. What did not fill (a missing
#                  open, the participation cap) is offered again at each next open.
#     OUT          from the day the book is flat. No order for cooldown_cycles x rebal
#                  trading days. Then, on each rebalance-grid day, breadth decides: at
#                  reentry_breadth or more the arm's normal order is placed.
#     REENTERED    the re-entry order filled at least one buy today; at this close the
#                  peak resets to this close's equity and the state returns to IN.
#
# THE CALLING SEQUENCE FOR ONE TRADING DAY, index i
#     1. begin_day()
#     2. after the morning's fills, if exit_pending or reentry_pending:
#            after_fills(i, held_now, held_before, date_of)
#     3. on a rebalance-grid day while state != "IN":
#            allowed = grid_allows_order(i, breadth_fn)
#        and, if allowed, after the caller's normal ordering:
#            after_reentry_order(order_placed)
#        while state == "IN" the caller rebalances as it always does.
#     4. at the close:
#            action = at_close(i, date, equity, order_placed_today, holdings_left, last)
#        action "exit" means: replace any order placed today with an order to sell
#        every holding at the next open. Then rows(date, equity) gives the day's events.

IN, LIQUIDATING, OUT, REENTERED = "IN", "LIQUIDATING", "OUT", "REENTERED"


class StopState:
    def __init__(self, stop, rebal, n_days):
        # THE SEAL, checked here so that no loop can run the registered stop before
        # the band file is committed, however it was handed the stop.
        require_unsealed(stop)
        self.stop = stop
        self.rebal = int(rebal)
        self.n_days = int(n_days)
        self.state = IN
        self.peak = None
        self.peak_date = None
        self.flat_i = None
        self.cool_end_i = None
        self.exit_pending = False      # an exit order fills at the next open
        self.reentry_pending = False   # a re-entry order fills at the next open
        self.events = []
        self.breadth = None

    def begin_day(self):
        self.events = []
        self.breadth = None

    def _ev(self, name, detail):
        self.events.append((name, detail))

    def after_fills(self, i, held_now, held_before, date_of):
        """Book what this morning's exit or re-entry order did."""
        if self.exit_pending:
            self.exit_pending = False
            sold = {k: int(q) - int(held_now.get(k, 0)) for k, q in held_before.items()
                    if int(held_now.get(k, 0)) < int(q)}
            self._ev("exit fills", f"sold {len(sold)} name(s) at this open: "
                     + (", ".join(f"{k} {q:,} sh" for k, q in sorted(sold.items()))
                        or "none"))
            if not held_now:
                self.state, self.flat_i = OUT, i
                self.cool_end_i = i + self.rebal * int(self.stop.cooldown_cycles)
                end = (date_of(self.cool_end_i) if self.cool_end_i < self.n_days
                       else "after the window")
                self._ev("flat", f"book flat at this open; cooldown until {end}")
            else:
                self._ev("exit partly filled",
                         f"{len(held_now)} name(s) still held: "
                         + ", ".join(f"{k} {int(q):,} sh" for k, q in sorted(held_now.items()))
                         + "; offered again at the next open")
        elif self.reentry_pending:
            self.reentry_pending = False
            if held_now:
                self.state = REENTERED
                self._ev("re-entry filled", f"{len(held_now)} name(s) bought; "
                         "peak resets to this close")
            else:
                self._ev("re-entry not filled",
                         "no buy filled; stays in cash, peak not reset")

    def grid_allows_order(self, i, breadth_fn):
        """On a rebalance-grid day while not IN: may the arm place its order today?

        breadth_fn() returns the day's breadth, computed the way the caller's
        mode="breadth" computes it. It is called only once the cooldown is over.
        """
        if self.state == OUT and i >= self.cool_end_i:
            self.breadth = float(breadth_fn())
            if self.breadth >= self.stop.reentry_breadth:
                return True
            self._ev("waiting", f"breadth {self.breadth:.4f} < "
                     f"{self.stop.reentry_breadth:.2f}; stays in cash")
        elif self.state == OUT:
            self._ev("cooldown", "rebalance day inside the cooldown; no order")
        else:
            self._ev("liquidating", "rebalance day while the exit is unfilled; no order")
        return False

    def after_reentry_order(self, order_placed):
        if order_placed:
            self.reentry_pending = True
            self._ev("re-entry order", f"breadth {self.breadth:.4f} >= "
                     f"{self.stop.reentry_breadth:.2f}; the arm's normal order fills "
                     "at the next open")
        else:
            self._ev("re-entry skipped", "breadth allows re-entry but no order was "
                     "placed (fewer than TOP_N rankable names)")

    def at_close(self, i, date, equity, order_placed_today, holdings_left, last):
        """-> "exit" when an order to sell everything must stand for the next open."""
        if self.state == REENTERED:
            self.state, self.peak, self.peak_date = IN, equity, date
            self._ev("peak reset", "peak reset to the re-entry day's close")
            return None
        if self.state == IN:
            if self.peak is None or equity > self.peak:
                self.peak, self.peak_date = equity, date
            if equity <= (1.0 - self.stop.threshold) * self.peak:
                if last:
                    self._ev("trigger on the last session", "no next open; nothing is sold")
                    return None
                if order_placed_today:
                    self._ev("order superseded", "this close's rebalance order is "
                             "replaced by the drawdown exit")
                self.state, self.exit_pending = LIQUIDATING, True
                self._ev("trigger", f"close equity {equity / self.peak - 1:+.2%} from "
                         "the peak; sell everything at the next open")
                return "exit"
            return None
        if self.state == LIQUIDATING and holdings_left and not last:
            self.exit_pending = True
            self._ev("exit retried", "remaining holdings offered at the next open")
            return "exit"
        return None

    def drawdown(self, equity):
        return equity / self.peak - 1 if self.peak else None

    def rows(self, date, equity):
        """The day's events as rows of daily_stop_events_<tag>.csv."""
        dd = self.drawdown(equity)
        return [{"date": date, "event": name, "state": self.state,
                 "peak": round(self.peak, 2) if self.peak is not None else None,
                 "peak_date": self.peak_date, "equity": round(equity, 2),
                 "drawdown_pct": round(dd * 100, 4) if dd is not None else None,
                 "breadth": round(self.breadth, 4) if self.breadth is not None else None,
                 "detail": detail}
                for name, detail in self.events]


# ======================================================================================
# RANKING, SIZING, BUY AND SELL DECISIONS AND THE DAILY LOOP. From results/test_exposure.py (moved 2026-11-27).
# ======================================================================================
# test_exposure.py -- Crash protection via MARKET-LEVEL exposure scaling
#
# PROBLEM: the model produces a relative rank. In a crash it ranks the stock that is
# falling least at number one, and the strategy buys it -- even though that stock is
# also down 25%.
#
# WHAT FAILED BEFORE: the absolute gate (blocking individual stocks killed the
# mean-reversion edge, Sharpe 1.03 -> 0.76), and the slope regime rule (lagging,
# 14 fires with 4 correct).
#
# THIS APPROACH works at market level and never blocks an individual stock:
#   A. BREADTH: invest the fraction of capital equal to the fraction of stocks with
#      positive momentum; hold the rest in cash. In a crash breadth falls and cash
#      rises, while good stocks are still bought.
#   B. CONST: a fixed exposure, the control breadth is compared against.
#
# The vol-target and min(breadth, vol-target) modes were removed on 2026-10-22: their
# target was the median portfolio vol over the whole backtest window, a value no
# decision could know on its own date, and no arm used them.
#
# The experiment's own main(), which read a fixed /tmp/v5_expanding.csv from a
# retired universe and wrote into results/metrics/, was removed on 2026-09-27;
# nothing called it. What remains is backtest_exposure, the engine every arm runs.

warnings.filterwarnings("ignore")

REBAL, VOL_WIN = 20, 60
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = settings.TOP_N, settings.BUFFER
_THIN_WARNED = set()      # see the len(s_) < TOP_N branch in backtest_exposure
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
CASH_YIELD = 0.0        # no yield assumed on idle cash
# BACKTEST WINDOW -- imported from config.py, the single definition.
# Date-based and inclusive. The old year cut (BT_START, BT_END = 2019, 2026)
# ran to 2026-06-08, six trading days beyond this window.
M = settings.METRICS_DIR


# THE CAP HAS NO DEFAULT, DELIBERATELY. `participation_cap=None` used to be the
# signature default, so a caller that simply forgot it silently got `research`
# behaviour -- an uncapped fill -- and nothing in the output said which profile
# produced the number. None is still a legal VALUE (it is what `research`
# resolves to); what is refused is not saying which.
_CAP_REQUIRED = object()

# AND THE CAP'S DATA HAS NO SILENT DEFAULT EITHER. `vol20=None` was the signature
# default from the day the cap was added, so a caller could pass the cap, satisfy
# _CAP_REQUIRED, and still be refused the cap by the `vol20 is not None` test three
# hundred lines below -- silently, with the run reporting the selected profile in
# every filename and every header.
#
# THAT IS THE EXACT FAILURE _CAP_REQUIRED WAS BUILT TO ABOLISH, and it abolished
# half of it. Measured 2026-09-15: backtest_runs.py passed the cap and no
# vol20, so every `--profile tradeable` audit of midcap150 replayed the RESEARCH
# strategy and reconciled it against the TRADEABLE curve -- reported as
# "v1 MISMATCH Rs 3,851,027.09", which is the cap's whole effect to the paisa.
# Thirteen further callers had the same pairing and were saved only by the profile
# axis being unable to reach them.
_VOL20_REQUIRED = object()

# dd_overlay's default: read dd_axis.selected() at call time. A sentinel rather
# than None, because None is the explicit "off" a test or a caller may pass.
_DD_FROM_SELECTION = object()

# fixed_capital's default: read fixed_axis.selected() at call time, as dd_overlay.
_FIXED_FROM_SELECTION = object()


def breadth_momentum(mom20, dt):
    """The 20-day momentum breadth is computed over: mom20 on `dt`, present values.

    IN A PIT RUN, ONLY THE MEMBERS ON `dt`. The price panel holds every name in
    the pit folder, and a name is in that folder because it is a member on some
    date, possibly a later one; counting a non-member on `dt` would let a later
    membership change today's exposure. Before the first effective date, where no
    list is in force, the first list is used, the rule market_data.member_mask
    applies there. Since 2026-10-22."""
    m = mom20.loc[dt].dropna()
    M = market_data.MEMBERSHIP
    if market_data.is_pit() and M is not None:
        _members = M.lists[0] if pd.Timestamp(dt) < pd.Timestamp(M.dates[0]) \
            else M.members_on(dt)
        m = m[[str(k).upper() in _members for k in m.index]]
    return m


def _participation_limit(sym, dt, participation_cap, vol20):
    """The cap in shares for one (symbol, date), or None when it does not apply.

    ONE DEFINITION, THREE CALL SITES -- the BUY, the forced exit and the
    rebalance exit. The cap was on the BUY path only until 2026-09-22, and the
    obvious way to add the sell side is to write the same four lines twice more.
    This repository has spent enough of its history on definitions that were
    copied and then drifted; the cap's semantics live here.

    `participation_cap` x the symbol's prior-20-session MEDIAN volume. Prior, so
    it never uses the day's own volume. Median, so one block trade does not
    licence a large fill. Returns None when no cap is selected, when no vol20 was
    supplied, or when this symbol has no usable median on this date -- the caller
    then transacts uncapped, which is the behaviour that shipped.
    """
    if participation_cap is None or vol20 is None:
        return None
    med = vol20.get(sym, {}).get(dt, float("nan"))
    if med != med or med <= 0:
        return None
    return int(participation_cap * med), med


def _median_volume(sym, dt, vol20):
    """The prior-20-session median for the impact model, or None."""
    if vol20 is None:
        return None
    med = vol20.get(sym, {}).get(dt, float("nan"))
    return None if (med != med or med <= 0) else med


def backtest_exposure(px, op, sc, dates, pc, mom20,
                      mode="none", audit=None, sizing="invvol",
                      const_expo=None, rebal=None,
                      funding="cash", participation_cap=_CAP_REQUIRED, vol20=_VOL20_REQUIRED,
                      tax_enabled=False, impact_k=None, impact_out=None,
                      end_sale=False, drawdown_stop=None, dd_overlay=_DD_FROM_SELECTION,
                      start_capital=None, fixed_capital=_FIXED_FROM_SELECTION,
                      buy_shortfall=None):
    """audit=None reproduces the original code path exactly: no overhead, and the
    official numbers are unchanged.

    fixed_capital -- THE FIXED-CAPITAL AXIS (settings.fixed_axis). Left unset, it is read
        from fixed_axis.selected(), which is False unless run.py was given
        --fixed-capital, and False runs none of the code that reads it. When on, at
        each rebalance open, after the morning's sells and any tax taken that
        morning: book = min(start capital, port_val), with port_val the
        decision-close value, invest_val = book * exposure * 0.98, reserve =
        max(0, value at this open - start capital), the value at this open being
        cash plus the names held, and the cash tests read cash - reserve. Held
        names are not trimmed. With an audit dict, each
        execution day's open valuation is written to audit["fixed"]. Refused
        together with drawdown_stop, dd_overlay and funding="prorata".

    dd_overlay -- THE DRAWDOWN-LIMIT AXIS (settings.dd_axis, results/drawdown_overlay.py).
        Left unset, it is read from dd_axis.selected(), which is None unless
        run.py was given --dd, and None runs none of the code that reads it. A
        DDLimit passed explicitly (tests) overrides the selection. When on, the
        invested fraction is cut to the cushion rule's limit: decided at each
        close, filled at the next open after the arm's own orders, fill kinds
        "dd trim" and "dd top-up". Refused together with drawdown_stop.

    drawdown_stop -- THE STOP OF v5 AND v6 (experiments/DRAWDOWN_STOP_PREREG.txt).
        None, the default, runs none of the code below that reads it, so v1 to v4
        are exactly what they were. An object with `threshold`, `cooldown_cycles`
        and `reentry_breadth` (arms.registry.DrawdownStop) runs this state machine
        on top of the arm's normal rebalancing:
          IN           the running peak of close equity is updated each day. At a
                       close at or below (1 - threshold) x peak, an order to sell
                       everything is placed for the next open and the state is
                       LIQUIDATING. A rebalance order placed at the same close is
                       superseded. A trigger at the last close sells nothing.
          LIQUIDATING  the exit goes through the ordinary sell branch, so the cap,
                       a missing open, slippage, charges and the tax ledger apply
                       exactly as to any sale. Whatever is left is offered again at
                       each next open until the book is flat.
          OUT          from the day the book is flat. For cooldown_cycles x rebal
                       trading days no order is placed. After that, on each
                       rebalance-grid day, breadth is computed exactly as
                       mode="breadth" computes it; at reentry_breadth or more the
                       arm's normal order is placed, below it the arm stays in cash.
          re-entry     if at least one buy fills, the peak resets to that day's
                       close and the state is IN. If none fills, the state stays OUT.
        Every transition is written to audit["stop_events"] when an audit dict is
        passed.

    buy_shortfall -- A BUY CASH CANNOT FULLY PAY FOR (buy_shortfall.py). None,
        the default, reads buy_shortfall.selected(), which is settings.BUY_SHORTFALL
        ("trim") unless run.py was given --buy-shortfall. "trim" cuts the buy to the
        largest whole quantity whose cost and charges fit the cash left at that
        point of the morning, and refuses it when that is 0 or below
        buy_shortfall.MIN_FILL_PCT of the wanted quantity, logged `cash short:
        below minimum fill` in the second case. "refuse" refuses
        it whole, the rule before 2026-10-27. A buy that fits is filled the same
        way under both. With an audit dict, the counts are in
        audit["buy_shortfall"], and each trimmed trade row carries wanted_qty and
        cash_shortfall.

    end_sale -- SELL EVERYTHING ON THE LAST SESSION (2026-09-25). False, the
        default and the headline: positions still held at the end are marked to
        market and never sold, so no gain is realised on them and no sell charge
        is paid. True gives the "sold on the last day" figure: after that day's
        ordinary fills every remaining holding is sold at that day's open, or its
        close where the open is missing, with the same slippage and calc_tc as any
        sell, and the gains enter the tax ledger before the end-of-window
        settlement. The sale is NOT participation-capped: it is a full
        liquidation by definition. False leaves every run exactly as it was.
    Passing a dict with holdings/summary/trades/ranking/decisions/skipped keys logs
    a daily snapshot into it.

    A BUY'S QUANTITY IS SET AT THE DECISION SESSION'S CLOSE (since 2026-10-28), as
    it would be live, where the order is placed before the next open is known:

        q = int((V x exposure x 0.98 x w x f) // (close x (1 + slippage)))

    V is the book at that close, cash plus every holding at its close (the names
    about to be sold included), less the tax deducted before the fill session's
    fills, which comes from gains realised by the decision session. The fill
    session's open decides only what fills: the fill price, the cash test and the
    trim. Until 2026-10-28 the quantity came from the fill session's open and the
    book valued at it, after the morning's sells.

    funding -- HOW THE DAY'S NEW POSITIONS ARE PAID FOR.

        "cash" (default, and the rule this function has always used): each entrant
        is sized at its full whole-portfolio target and paid for out of cash, in
        score-descending order, until cash runs out. Each buy cash cannot fully
        pay for is trimmed to the largest quantity that fits (buy_shortfall=
        "trim", the default since 2026-10-27) and refused, logged `cash short
        (before TC)` or `(incl TC)`, when not one share fits, or `cash short:
        below minimum fill` when fewer than half the wanted shares fit; under
        buy_shortfall="refuse" it is refused whole.

        THAT IS A REAL DEFECT AND IT AFFECTS THE SHIPPING ARM. `invest_val` is a
        share of the WHOLE portfolio and the TOP_N weights sum to 1.0, but a name
        already held is skipped and never resized, and BUFFER names hold capital
        while carrying no target weight at all. So whenever a buffer name is held
        the book is over-committed by construction and cash MUST be short. On this
        repo's own panels it drops 92 to 165 buys per run and leaves the mean book
        below TOP_N. See KNOWN_ISSUES.md and experiments/FUNDING_SPEC.txt.

        "prorata": the entrants are scaled down TOGETHER by a single factor
        f = min(1, cash * 0.98 / total entrant target) instead of the tail being
        dropped one at a time. It changes nothing else. `invest_val` keeps its
        whole-portfolio base, the relative inverse-vol proportions among entrants
        are preserved because f is one scalar applied to all of them, no held
        position is topped up or resized -- experiments/V34_SPEC.txt line 125 --
        and no buffer name is trimmed. The 0.98 is the haircut this function
        already applies to `invest_val`; no new constant is introduced.

        WHY THE DEFAULT IS STILL "cash". Flipping it moves every published v1-v4
        figure and re-baselines the seven identity gates that read
        v34_comparison.csv. FUNDING_SPEC.txt gates the model but does not authorise
        that flip, which is a separate decision with its own blast radius. Note
        also that nautilus/nt_strategy.py mirrors this sizing rule; the mirror is
        exact only while the default is unchanged, so a flip must update the port
        in the same commit."""
    if participation_cap is _CAP_REQUIRED:
        raise TypeError(
            "backtest_exposure(): participation_cap is required. Pass "
            "costs.participation_cap() -- None under the 'research' profile, a "
            "fraction of prior-20-session median volume under 'tradeable'. It had "
            "a None default, which meant a caller that omitted it silently "
            "measured the research profile whatever the run had selected.")
    # THE SAME CONTRACT FOR THE IMPACT MODEL, CHECKED AT THE CALL. impact()
    # raises MissingVolume per fill if the median is absent, which is correct but
    # arrives 1,800 sessions in. A caller that passed a k and no volume series is
    # wrong before the first bar, so it is told here.
    if impact_k is not None and (vol20 is _VOL20_REQUIRED or vol20 is None):
        import inspect as _insp
        _f = _insp.stack()[1]
        raise TypeError(
            f"backtest_exposure(): impact_k={impact_k!r} was passed without "
            f"vol20, from {_f.filename}:{_f.lineno}.\n"
            f"  The size-sensitive rate is k * sqrt(qty / prior-20d median "
            f"volume). Without vol20 there is no denominator, and the model "
            f"CANNOT fall back to the flat rate -- that would put research "
            f"arithmetic in an artefact labelled tradeable, which is the defect "
            f"class this model exists inside.\n"
            f"  Pass vol20=tradability.median_volume(...), or impact_k=None.")
    # THE OTHER HALF OF THE SAME CONTRACT. A cap with no volume series is not a
    # cap; it is research arithmetic with a tradeable label on the output. The
    # caller is named because the failure is silent at every other level -- the
    # profile is right, the filenames are right, and only the numbers are wrong.
    if participation_cap is not None and vol20 is _VOL20_REQUIRED:
        import inspect as _insp
        _f = _insp.stack()[1]
        raise TypeError(
            f"backtest_exposure(): participation_cap={participation_cap!r} was "
            f"passed without vol20, from {_f.filename}:{_f.lineno}.\n"
            f"  The cap is applied only where a prior-20-session median volume "
            f"exists for the symbol, so without vol20 NO BUY IS EVER CAPPED and "
            f"this call measures the research strategy under a "
            f"'{settings.profile_axis.selected()}' label.\n"
            f"  Pass vol20=tradability.median_volume(u.prepare_data_dir(), "
            f"_load_calendar(), settings.BT_START_DATE, settings.BT_END_DATE) as both engines and "
            f"v34_common do, or declare the intent with "
            f"costs.research_only(__name__) if this caller is research-only.")
    # THE EXEMPTION MAP IS BUILT ONCE, FROM THE VOLUME SERIES, BEFORE ANY FILL.
    # Defining it by construction is requirement one: a fill that has no median
    # for any reason OTHER than "its symbol's window has not started" must still
    # raise, and a map built up front is what makes that distinguishable.
    _imp_first = costs.first_priced_date(vol20) if impact_k is not None else {}
    _imp = {"priced": 0, "exempt": 0}

    def _fill_price(side, sym, dt_, raw, qty):
        """(fill price, pending record) for one leg.

        COUNTED ON COMMIT, NOT ON PRICING. A BUY is priced BEFORE the cash tests,
        so counting here would report fills that were then skipped cash-short --
        it read 1,008 priced against 1,006 trades on midcap150. The caller calls
        _commit_impact() once the trade is actually taken.
        """
        flat = (costs.buy_price if side == "BUY" else costs.sell_price)
        if impact_k is None:
            return flat(raw, qty, None, None), None
        med, exempt = costs.resolve(sym, dt_, vol20, _imp_first)
        if exempt:
            return flat(raw, qty, None, None), {
                "date": dt_, "side": side, "symbol": sym, "qty": qty,
                "exempt": True, "med": None}
        return flat(raw, qty, med, impact_k), {"exempt": False, "med": med}

    def _commit_impact(pending):
        """Count a leg that was actually transacted, and log an exemption."""
        if pending is None:
            return
        if not pending["exempt"]:
            _imp["priced"] += 1
            return
        _imp["exempt"] += 1
        if audit is not None:
            sym = pending["symbol"]
            audit["skipped"].append({"date": pending["date"], "side": pending["side"],
                "symbol": sym,
                "reason": "impact: no prior-20d median",
                "detail": f"{pending['qty']:,} sh charged the flat rate; {sym}'s "
                          f"first priced date is {_imp_first.get(sym)}, so the "
                          f"prior-20-session window had not started"})

    if vol20 is _VOL20_REQUIRED:
        # research: the cap is None, so the volume series is genuinely unused.
        vol20 = None
    # REBALANCE CADENCE. None means "use the module value", which is what every
    # caller relied on when this was only a module global -- so omitting it is
    # byte-identical to the previous behaviour, and rebal_cadence_sweep.py's
    # `portfolio.REBAL = n` override still works because the module value is
    # read HERE, at call time, not bound at import.
    _rebal = REBAL if rebal is None else int(rebal)
    if _rebal < 1:
        raise ValueError(f"rebal must be >= 1, got {rebal!r}")
    if funding not in ("cash", "prorata"):
        raise ValueError(f'funding must be "cash" or "prorata", got {funding!r}')
    # THE STARTING CAPITAL: capital_axis.selected() unless a caller passes one.
    _cap0 = _capital_axis.selected() if start_capital is None else start_capital
    shares, cash = {}, _cap0
    # SALES WAITING FOR A ROW: {symbol: the session the sale fell due}. See
    # touch point 4.
    _owed = {}
    cum_tc, n_trades = 0.0, 0
    eq, pending, expo_log = [], None, []
    # THE DECISION SESSION'S CLOSE, which sizes the next session's buys: the
    # book's value and the closes at the end of the previous session.
    _dec_val, _dec_px = None, None
    # THE TAX LEDGER. None at the default, and `ledger is None` is the only test
    # on the hot path -- the untaxed run does not construct it, does not record a
    # lot and does not evaluate a date. tax_enabled is a PARAMETER rather than a
    # read of tax.selected(), for the same reason rebal and participation_cap are:
    # the caller owns the selection and the engine stays callable from a test that
    # never touches the axis.
    ledger = costs.Ledger(dates) if tax_enabled else None
    cum_tax = 0.0
    # THE COST TRAIL (reports.py). Filled only when the caller's audit
    # dict carries a "costs" key, with every fill and every day's cash at full
    # precision. It records what the loop already computed and feeds nothing back,
    # so a run without the key, and every figure of a run with it, is unchanged.
    _costs = audit.get("costs") if audit is not None else None

    # WITH THE IMPACT MODEL ON, each fill also records the median volume it was
    # priced against (None for a fill the model exempted), so cost_report can
    # recompute the impact rate with costs.impact and split it from the flat
    # slippage. Without the model the record has no such key and is unchanged.
    def _cost_fill(dt_, side, sym, q_, ref, fill, tc_, kind, pend=None):
        if _costs is not None:
            rec = {"date": dt_, "side": side, "symbol": sym, "qty": int(q_),
                   "reference_price": float(ref), "fill_price": float(fill),
                   "charges": float(tc_), "kind": kind}
            if impact_k is not None:
                rec["impact_k"] = float(impact_k)
                rec["impact_median"] = (None if pend is None or pend["med"] is None
                                        else float(pend["med"]))
            _costs["fills"].append(rec)

    cash_daily = (1 + CASH_YIELD) ** (1 / 252) - 1

    # THE DRAWDOWN STOP (portfolio.py). Nothing here exists when
    # drawdown_stop is None.
    _stop = drawdown_stop
    if _stop is not None:
        _st = StopState(_stop, _rebal, len(dates))
        _stop_log = audit.setdefault("stop_events", []) if audit is not None else None
        _EXIT_ORDER = ({"_exposure": 0.0}, set())   # sell every holding, buy nothing

    # THE DRAWDOWN-LIMIT AXIS (portfolio.py). Nothing below that
    # reads _dd runs when it is None, which is every run without --dd.
    if dd_overlay is _DD_FROM_SELECTION:
        from settings import dd_axis as _dd_axis
        dd_overlay = _dd_axis.selected()
    _dd = dd_overlay
    # THE FIXED-CAPITAL AXIS (settings.fixed_axis). Nothing below that reads _fixed runs
    # when it is False, which is every run without --fixed-capital.
    if fixed_capital is _FIXED_FROM_SELECTION:
        from settings import fixed_axis as _fixed_axis
        fixed_capital = _fixed_axis.selected()
    _fixed = bool(fixed_capital)
    if _fixed:
        if _stop is not None or _dd is not None:
            raise ValueError(
                "fixed capital cannot run with the drawdown stop (v5/v6) or the "
                "drawdown limit (--dd): both act on the running peak of compounded "
                "equity, and the fixed-capital book is min(base, equity)")
        if funding != "cash":
            raise ValueError('fixed capital is defined for funding="cash" only')
        _fixed_log = audit.setdefault("fixed", []) if audit is not None else None
    # The idle profit ring-fenced at this morning's open. 0.0 off the axis, and
    # cash - 0.0 is cash exactly, so the cash tests below are unchanged.
    _reserve = 0.0
    # A BUY CASH CANNOT FULLY PAY FOR: trimmed or refused (portfolio.py).
    if buy_shortfall is None:
        buy_shortfall = settings.shortfall_axis.selected()
    if buy_shortfall not in settings.shortfall_axis.CHOICES:
        raise ValueError(f"buy_shortfall must be one of {settings.shortfall_axis.CHOICES}, got {buy_shortfall!r}")
    _shortfall = buy_shortfall
    _n_trimmed = _n_refused = 0
    if _dd is not None:
        if _stop is not None:
            raise ValueError("the drawdown-limit axis cannot run on a stop arm (v5/v6)")
        _ds = OverlayState(_dd, _cap0)
        _dd_rows = set()          # ledger row indices realised by the overlay's sales
        _dd_invested = []         # mtm / equity at each close: Deployed% with the axis on

    for i, dt in enumerate(dates):
        if _stop is not None:
            _st.begin_day()
        prices, opens = px.loc[dt], op.loc[dt]
        _cash_open = cash
        cash *= (1 + cash_daily)
        _cash_int, _tax_pre, _tax_post = cash - _cash_open, 0.0, 0.0

        # TOUCH POINT 6 -- THE ANNUAL TAX LUMP SUM, section 3(9) of the tax
        # reference: each financial year is assessed EXACTLY ONCE, on the first
        # trading day at or after 31 March, and the whole bill leaves cash in one
        # deduction.
        #
        # BEFORE THIS DAY'S FILLS, DELIBERATELY, AND THAT ORDERING IS OURS. The
        # document says the deduction "reduces the capital available to trade the
        # following year", which is only true if the money is gone before the
        # morning's orders are sized -- `q = int((invest_val * w * f) // pr)` reads
        # cash further down. The document does not rule on the same-day case, so
        # this is a stated decision and not a quoted rule; see KNOWN_ISSUES.md.
        #
        # CASH MAY GO NEGATIVE HERE AND IS NOT CLAMPED. A clamp would forgive part
        # of a real liability and silently improve the result; an overdrawn book
        # buys nothing that morning, which is the honest consequence.
        if ledger is not None:
            _due = ledger.due_on(dt)
            if _due:
                cash -= _due
                cum_tax += _due
                _tax_pre = _due
                if audit is not None:
                    audit["skipped"].append({"date": dt, "side": "TAX", "symbol": "",
                        "reason": f"capital-gains tax assessed, Rs {_due:,.2f}",
                        "detail": "section 3(9): one lump sum, before this day's fills"})

        # TOUCH POINT 4 -- A SALE THAT WAITED FOR A ROW (since 2026-10-16).
        #
        # A name is traded only on a session that has a row for it
        # (market_data.tradeable_on, reports.py). A sale that fell due
        # on a session with no row was recorded in _owed instead of filling at the
        # forward-filled open, a price nobody quoted. Here, at each session's open,
        # every owed name that has a row today is sold at today's open, the rule
        # every other sell uses. One with no row today stays owed; a name whose
        # file has ended is never sold and stays valued at its last close.
        #
        # This replaces the forced exit that sold a holding on the session BEFORE a
        # gap of two or more sessions. That exit read whether the next session had
        # a row and how long the gap ran, both dated after the decision, and so
        # looked ahead (KNOWN_ISSUES.md).
        #
        # The participation cap applies as to every sell; a capped leftover stays
        # owed and is tried again the next session. A name back in the keep list
        # at the next decision is no longer owed (see the decision below).
        for s in [x for x in list(_owed) if x in shares]:
            if not market_data.tradeable_on(s, dt):
                continue
            pr = opens.get(s, np.nan)
            if np.isnan(pr) or pr <= 0:
                continue
            q = int(shares[s])
            _capped = _participation_limit(s, dt, participation_cap, vol20)
            _left = 0
            if _capped is not None:
                _lim, _med = _capped
                if q > _lim:
                    if audit is not None:
                        audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                            "reason": "participation cap",
                            "detail": f"wanted {q:,} sh, capped to {_lim:,} "
                                      f"({participation_cap:.0%} of prior-20d "
                                      f"median {_med:,.0f}); remainder stays owed"})
                    _left = q - _lim
                    q = _lim
            if q < 1:
                continue
            _ref = pr
            pr, _pend = _fill_price("SELL", s, dt, pr, q)
            tc = calc_tc(pr, q, "SELL")
            cash += q * pr - tc; cum_tc += tc; n_trades += 1
            _cost_fill(dt, "SELL", s, q, _ref, pr, tc, "owed sale", _pend)
            _commit_impact(_pend)
            if ledger is not None:
                ledger.sell(s, q, round(pr, 2), dt)
            if audit is not None:
                audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                    "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                    "tc": round(tc, 2)})
            if _left:
                shares[s] = _left
            else:
                del shares[s]
                del _owed[s]
        for s in [x for x in list(_owed) if x not in shares]:
            del _owed[s]

        # TOUCH POINT 7 -- FORCED EXIT ON A NAME LEAVING THE INDEX. Pit mode only;
        # in static mode, or with no membership loaded, nothing here runs.
        #
        # BESIDE TOUCH POINT 4, FOR THE SAME REASON: a name that leaves between
        # rebalances must not be held until the next one. Each session, a held name
        # that is not in the membership in force today is sold at today's OPEN --
        # the first session on or after the effective date of the row that drops
        # it. Index changes are announced weeks ahead, so that order could be
        # placed in time. Same fill, slippage, charges, participation cap and tax
        # ledger as every other sell; a capped remainder stays held and is retried
        # the next session, as is a name with no raw price row today. The cash is
        # not reinvested until the next rebalance. Touch point 3 still removes the
        # same names from `keep` at a rebalance, which is then a no-op.
        if market_data.is_pit() and market_data.MEMBERSHIP is not None and market_data.EXIT_POLICY == "forced":
            _members = market_data.MEMBERSHIP.members_on(dt)
            for s in [x for x in shares if _members and x.upper() not in _members]:
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0 or not market_data.tradeable_on(s, dt):
                    continue
                q = int(shares[s])
                _capped = _participation_limit(s, dt, participation_cap, vol20)
                _left = 0
                if _capped is not None and q > _capped[0]:
                    _left, q = q - _capped[0], _capped[0]
                    if audit is not None:
                        audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                            "reason": "participation cap",
                            "detail": f"index exit capped to {q:,} sh; remainder stays held"})
                if q < 1:
                    continue
                _ref = pr
                pr, _pend = _fill_price("SELL", s, dt, pr, q)
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _cost_fill(dt, "SELL", s, q, _ref, pr, tc, "index exit", _pend)
                _commit_impact(_pend)
                if ledger is not None:
                    ledger.sell(s, q, round(pr, 2), dt)
                if audit is not None:
                    audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                        "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                        "tc": round(tc, 2)})
                    audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                        "reason": "forced exit: left the index",
                        "detail": "not in the membership in force on this session"})
                if _left:
                    shares[s] = _left
                else:
                    del shares[s]

        if pending is not None:
            targets, keep = pending
            # The fill kind of this morning's sells: "rebalance" unless the order
            # is a drawdown exit.
            _sell_kind = ("drawdown exit" if _stop is not None and _st.exit_pending
                          else "rebalance")
            if _stop is not None:
                _held_before = dict(shares)
            for s in list(shares.keys()):
                if s not in keep:
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "no open price (NaN/<=0)", "detail": ""})
                        continue
                    # NO ROW TODAY: THE SALE IS OWED, NOT FILLED at the forward-filled
                    # open. Touch point 4 sells it at the open of its next session
                    # with a row. setdefault keeps the session it first fell due.
                    if not market_data.tradeable_on(s, dt):
                        if s not in _owed and audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "untradeable: no row this session, sale owed",
                                "detail": "sold at the open of the next session with a row"})
                        _owed.setdefault(s, dt)
                        continue
                    # SYMMETRIC CAP -- the same helper the BUY and the forced
                    # exit use. A name the cap would not let you build can no
                    # longer be unwound in one session either. The uncapped
                    # remainder STAYS HELD and is logged; the engine has no order
                    # state to carry it with.
                    q = int(shares[s])
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    _left = 0
                    if _capped is not None:
                        _lim, _med = _capped
                        if q > _lim:
                            if audit is not None:
                                audit["skipped"].append({"date": dt, "side": "SELL",
                                    "symbol": s,
                                    "reason": "participation cap",
                                    "detail": f"wanted {q:,} sh, capped to {_lim:,} "
                                              f"({participation_cap:.0%} of prior-20d "
                                              f"median {_med:,.0f}); remainder stays held"})
                            _left = q - _lim
                            q = _lim
                    if q < 1:
                        continue
                    _ref = pr
                    pr, _pend = _fill_price("SELL", s, dt, pr, q)
                    tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "SELL", s, q, _ref, pr, tc, _sell_kind, _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.sell(s, q, round(pr, 2), dt)
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    if _left:
                        shares[s] = _left
                    else:
                        del shares[s]
            if targets:
                # THE BOOK THE BUYS ARE SIZED FROM IS THE ONE AT THE DECISION CLOSE,
                # less the tax taken before this morning's fills (from gains realised
                # by then, so known at that close). See the docstring.
                port_val = _dec_val - _tax_pre
                # A HELD NAME WITH NO ROW TODAY has no open; it is valued at its
                # last close, which `prices` carries forward. Used only for the
                # fixed-capital log below.
                def _vp(s_):
                    return opens.get(s_, np.nan) if market_data.tradeable_on(s_, dt) \
                        else prices.get(s_, np.nan)
                if _fixed:
                    # THE FIXED-CAPITAL RING-FENCE (settings.fixed_axis). Profit above the
                    # base is held back from every purchase; below the base the book
                    # is the equity, so a loss is not topped up.
                    _book = min(_cap0, port_val)
                    _held_open = sum(q_ * _vp(s_) for s_, q_ in shares.items()
                                     if not np.isnan(_vp(s_)))
                    # THE RESERVE IS MEASURED AT THIS OPEN, before the buys: cash
                    # after the morning's sells and tax, plus the names held,
                    # valued as _vp values them. The quantities above still come
                    # from the decision-close book. From afadfc0 (2026-10-28) until
                    # 2026-11-27 the reserve came from the decision close as well,
                    # so an overnight rise was spent on purchases and invested
                    # value went above the base (engine_tests fixed_capital case a).
                    _reserve = max(0.0, cash + _held_open - _cap0)
                    invest_val = _book * targets["_exposure"] * 0.98
                else:
                    invest_val = port_val * targets["_exposure"] * 0.98
                if _dd is not None:
                    # ENTRANTS ARE SIZED AT min(E, A) INSTEAD OF A, from the E
                    # decided at the last close, so they are not bought full and
                    # trimmed the same morning.
                    invest_val *= _ds.entry_factor(targets["_exposure"])
                # PRO-RATA ENTRANT SCALING (funding="prorata"). See the `funding`
                # note in the docstring and experiments/FUNDING_SPEC.txt.
                #
                # The entrant block is committed `invest_val * sum(w)` by a
                # whole-portfolio calculation but paid for out of cash alone, so
                # when a buffer name holds capital the block cannot fit and the
                # score-descending loop below drops its tail. `f` scales the whole
                # block to what cash can actually carry, so every entrant is filled
                # small rather than the lowest-ranked ones not at all.
                #
                # THE DEFAULT PATH DOES NOT EXECUTE THIS. funding="cash" leaves f
                # at exactly 1.0 without computing anything, and `invest_val * w`
                # is then multiplied by a literal 1.0, which is exact in IEEE-754.
                # The shipped numbers cannot move.
                f = 1.0
                if funding == "prorata":
                    # Entrants only, from the decision close: every entrant with a
                    # close there. The cash is what that close leaves for buys:
                    # the book less the names kept, valued at their closes.
                    tgt_sum = 0.0
                    for s, w in targets.items():
                        if s == "_exposure" or s in shares:
                            continue
                        pr_ = _dec_px.get(s, np.nan)
                        if np.isnan(pr_) or pr_ <= 0:
                            continue
                        tgt_sum += w
                    need = invest_val * tgt_sum
                    _cash_dec = port_val - sum(
                        q_ * _dec_px[s_] for s_, q_ in shares.items()
                        if not np.isnan(_dec_px.get(s_, np.nan)))
                    # cash * 0.98 reuses the haircut applied to invest_val above;
                    # it is the allowance for transaction costs and for the
                    # integer-flooring of every quantity. No new constant.
                    if need > 0:
                        f = min(1.0, _cash_dec * 0.98 / need)
                for s, w in targets.items():
                    if s == "_exposure" or s in shares:
                        continue
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "no open price (NaN/<=0)", "detail": ""})
                        continue
                    # TOUCH POINT 5 -- NO BUY ON A SESSION WITH NO ROW. The buy is
                    # dropped, not carried forward. This reason exists because
                    # "no open price (NaN/<=0)" cannot fire here -- ffill always
                    # supplies a price, which is why that reason fires ZERO times
                    # across every midcap150 and nifty100 trail while PATANJALI still filled
                    # 33,575 shares on a date with no raw row. Since 2026-10-16 any
                    # session with no row blocks the buy, however long the gap, and
                    # the first row after a gap is tradeable.
                    if not market_data.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "untradeable: no row this session",
                                "detail": "no trade in a name on a session without a row"})
                        continue
                    # THE QUANTITY, FROM THE DECISION CLOSE AT THE FLAT RATE,
                    # unrounded; the cap then shrinks it, and the fill price, at
                    # this open, charges impact on the quantity actually
                    # transacted. Under impact_k=None the fill price is the open
                    # at the flat rate, to the paisa (costs.fill_price).
                    _size_px = _dec_px.get(s, np.nan) * (1 + SLIPPAGE)
                    if np.isnan(_size_px) or _size_px <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "no close on the decision session", "detail": ""})
                        continue
                    _raw_buy = pr
                    pr = costs.buy_price(_raw_buy, 0, None, None)
                    q = int((invest_val * w * f) // _size_px)
                    # PARTICIPATION CAP -- costs.py. None at the default profile,
                    # so `q` is untouched and the published history is exact.
                    #
                    # APPLIED BEFORE THE CASH TEST BELOW, deliberately: the cap
                    # shrinks the order and the cash test then sees the smaller
                    # number. Measured, midcap150 v3 at cap=1.00: mean names held 7.60 ->
                    # 7.72 and cash-short skips 131 -> 123, because shrinking an
                    # early oversized name frees cash for the tail the loop used to
                    # drop. The two constraints cannot both bind harmfully.
                    #
                    # THE REMAINDER STAYS IN CASH. Reallocating it to the next name
                    # would change selection; carrying it to the next session needs
                    # order state the engine does not have.
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    if _capped is not None:
                        _lim, _med = _capped
                        if q > _lim:
                            if audit is not None:
                                audit["skipped"].append({"date": dt, "side": "BUY",
                                    "symbol": s,
                                    "reason": "participation cap",
                                    "detail": f"wanted {q:,} sh, capped to {_lim:,} "
                                              f"({participation_cap:.0%} of prior-20d "
                                              f"median {_med:,.0f})"})
                            q = _lim
                    if q < 1:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "qty < 1 after sizing",
                                "detail": f"target Rs {invest_val*w*f:,.0f} / price {_size_px:,.2f}"})
                        continue
                    # IMPACT ON THE QUANTITY ACTUALLY TRANSACTED, before the cash
                    # tests, so a buy that impact makes unaffordable is skipped as
                    # cash-short rather than overdrawn. Identity when impact_k is
                    # None. Raises MissingVolume rather than reverting to the flat
                    # rate when the model is on and the median is absent.
                    _pend = None
                    if impact_k is not None:
                        pr, _pend = _fill_price("BUY", s, dt, _raw_buy, q)
                    # A BUY CASH CANNOT FULLY PAY FOR (portfolio.py). A buy that
                    # fits is filled exactly as before. One that does not is cut to
                    # the largest whole quantity that fits under "trim" and refused
                    # under "refuse"; under trim it is refused when that quantity is
                    # 0 or below portfolio.MIN_FILL_PCT of the wanted quantity.
                    # The cash is what is left at this point of the morning, after
                    # the sells, any tax taken today and the higher-ranked buys.
                    _short = cash - _reserve < q * pr
                    tc = None if _short else calc_tc(pr, q, "BUY")
                    _short = _short or cash - _reserve < q * pr + tc
                    _trim = _below_min = None
                    if _short and _shortfall == "trim":
                        _q, _pr, _tc, _why = trim(
                            q, cash - _reserve,
                            (lambda n: pr) if impact_k is None
                            else (lambda n: _fill_price("BUY", s, dt, _raw_buy, n)[0]),
                            lambda p_, n: calc_tc(p_, n, "BUY"))
                        if _q >= 1:
                            _trim = {"wanted_qty": q,
                                     "cash_shortfall": round(q * pr + calc_tc(pr, q, "BUY")
                                                             - (cash - _reserve), 2)}
                            if impact_k is not None:
                                pr, _pend = _fill_price("BUY", s, dt, _raw_buy, _q)
                            q, tc, _short = _q, _tc, False
                        elif _why == BELOW_MINIMUM:
                            _below_min = largest_fit(
                                q, cash - _reserve,
                                (lambda n: pr) if impact_k is None
                                else (lambda n: _fill_price("BUY", s, dt, _raw_buy, n)[0]),
                                lambda p_, n: calc_tc(p_, n, "BUY"))[0]
                    if _short and _below_min is not None:
                        _n_refused += 1
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": BELOW_MINIMUM,
                                "detail": f"wanted {q:,} sh, cash pays for {_below_min:,} sh "
                                          f"({_below_min / q * 100:.1f}%), minimum "
                                          f"{MIN_FILL_PCT}%; have Rs {cash:,.0f}"
                                          + (f", of which Rs {_reserve:,.0f} is the fixed-"
                                             f"capital reserve" if _fixed else "")})
                        continue
                    if _short:
                        _n_refused += 1
                        if audit is not None:
                            _before = cash - _reserve < q * pr
                            _need = q * pr if _before else q * pr + tc
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": ("cash short (before TC)" if _before
                                           else "cash short (incl TC)"),
                                "detail": f"need Rs {_need:,.0f}, have Rs {cash:,.0f}"
                                          + (f", of which Rs {_reserve:,.0f} is the fixed-"
                                             f"capital reserve" if _fixed else "")})
                        continue
                    if _trim is not None:
                        _n_trimmed += 1
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "BUY", s, q, _raw_buy, pr, tc, "rebalance", _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.buy(s, q, round(pr, 2), dt)
                    if audit is not None:
                        # A trimmed buy carries the quantity it wanted and the cash it
                        # was short by; qty is what filled. No other row has them.
                        audit["trades"].append({"date": dt, "action": "BUY", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2), **(_trim or {})})
                    shares[s] = shares.get(s, 0) + q
                if _fixed and _fixed_log is not None:
                    # For MaxInvested_base% and engine_tests fixed_capital: the
                    # decision-close book the buys were sized from, and held value
                    # before and after the buys at the open the orders filled at.
                    _fixed_log.append({
                        "date": dt, "port_val": port_val, "book": _book,
                        "reserve": _reserve, "held_before_buys": _held_open,
                        "held_after": sum(q_ * _vp(s_) for s_, q_ in shares.items()
                                          if not np.isnan(_vp(s_))),
                        "cash_after": cash})
                _reserve = 0.0
            pending = None
            if _stop is not None and (_st.exit_pending or _st.reentry_pending):
                _st.after_fills(i, shares, _held_before,
                                lambda k: pd.Timestamp(dates[k]).date())

        # THE DRAWDOWN-LIMIT ORDER placed at the last close, after the arm's own
        # fills. See portfolio.py. Each name the order still finds
        # held is resized by the same ratio: sells first, then top-ups funded from
        # cash with the usual 0.98 haircut, scaled down together when cash is short.
        if _dd is not None and _ds.order is not None:
            _ord = _ds.order
            _before = {s: int(shares[s]) for s in _ord if s in shares}
            if not _before:
                _ds.cancel()
            else:
                for s in sorted(_before):
                    dq = _ord[s]
                    if dq >= 0:
                        continue
                    raw = opens.get(s, np.nan)
                    if np.isnan(raw) or raw <= 0 or not market_data.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "dd trim: no open price (NaN/<=0)", "detail": ""})
                        continue
                    q = min(-dq, int(shares[s]))
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    if _capped is not None and q > _capped[0]:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "participation cap",
                                "detail": f"dd trim wanted {q:,} sh, capped to {_capped[0]:,}"})
                        q = _capped[0]
                    if q < 1:
                        continue
                    pr, _pend = _fill_price("SELL", s, dt, raw, q)
                    tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "SELL", s, q, raw, pr, tc, "dd trim", _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        _n0 = len(ledger.rows)
                        ledger.sell(s, q, round(pr, 2), dt)
                        _dd_rows.update(range(_n0, len(ledger.rows)))
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    shares[s] -= q
                    if shares[s] == 0:
                        del shares[s]
                _buys = [(s, _ord[s]) for s in sorted(_before) if _ord[s] > 0 and s in shares]
                _need = 0.0
                for s, dq in _buys:
                    raw = opens.get(s, np.nan)
                    if not (np.isnan(raw) or raw <= 0):
                        _need += dq * costs.buy_price(raw, 0, None, None)
                _f = min(1.0, cash * 0.98 / _need) if _need > 0 else 1.0
                for s, dq in _buys:
                    raw = opens.get(s, np.nan)
                    if np.isnan(raw) or raw <= 0 or not market_data.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "dd top-up: no open price or untradeable",
                                "detail": ""})
                        continue
                    pr = costs.buy_price(raw, 0, None, None)
                    q = int(dq * _f)
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    if _capped is not None and q > _capped[0]:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "participation cap",
                                "detail": f"dd top-up wanted {q:,} sh, capped to {_capped[0]:,}"})
                        q = _capped[0]
                    if q < 1:
                        continue
                    _pend = None
                    if impact_k is not None:
                        pr, _pend = _fill_price("BUY", s, dt, raw, q)
                    tc = calc_tc(pr, q, "BUY")
                    if cash < q * pr + tc:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "dd top-up: cash short",
                                "detail": f"need Rs {q*pr+tc:,.0f}, have Rs {cash:,.0f}"})
                        continue
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "BUY", s, q, raw, pr, tc, "dd top-up", _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.buy(s, q, round(pr, 2), dt)
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "BUY", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    shares[s] += q
                _ds.after_fills(dt, _before, {s: int(shares.get(s, 0)) for s in _before})

        # THE LAST-DAY SALE -- see end_sale in the docstring. After the day's
        # ordinary fills and before the end-of-window tax settlement below.
        if end_sale and i == len(dates) - 1:
            for s in list(shares.keys()):
                # No row on the last session: not sold, valued at its last close.
                if not market_data.tradeable_on(s, dt):
                    continue
                raw = opens.get(s, np.nan)
                if np.isnan(raw) or raw <= 0:
                    raw = prices.get(s, np.nan)
                q = int(shares[s])
                if np.isnan(raw) or raw <= 0 or q < 1:
                    continue
                pr, _pend = _fill_price("SELL", s, dt, raw, q)
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _cost_fill(dt, "SELL", s, q, raw, pr, tc, "last-day sale", _pend)
                _commit_impact(_pend)
                if ledger is not None:
                    ledger.sell(s, q, round(pr, 2), dt)
                if audit is not None:
                    audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                        "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                        "tc": round(tc, 2)})
                    audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                        "reason": "sold on the last day",
                        "detail": "end_sale=True: full liquidation on the final session"})
                del shares[s]

        _grid = i % _rebal == 0 and i < len(dates) - 1
        _reentry_check = False
        if _grid and _stop is not None and _st.state != "IN":
            # NO NORMAL REBALANCE WHILE THE STOP HOLDS THE ARM OUT. Breadth, when
            # the stop asks for it, is computed exactly as mode="breadth" does.
            def _breadth():
                _m = breadth_momentum(mom20, dt)
                return float((_m > 0).mean()) if len(_m) else 1.0
            _grid = _reentry_check = _st.grid_allows_order(i, _breadth)
            if not _grid:
                expo_log.append(0.0)
        if _grid:
            if mode == "none":
                expo = 1.0
            elif mode == "breadth":
                m = breadth_momentum(mom20, dt)
                expo = float((m > 0).mean()) if len(m) else 1.0
            elif mode == "const":
                # The T3 control of experiments/BREADTH_LIVE_SPEC.txt. Holds a
                # FIXED exposure so that breadth can be compared against the same
                # average cash level, isolating the timing from the level.
                # The caller supplies the level; it is read from the breadth
                # run's own realised mean and is never a literal in this file.
                if const_expo is None:
                    raise ValueError('mode="const" requires const_expo')
                expo = float(const_expo)
            else:
                raise ValueError(f"mode must be 'none', 'breadth' or 'const', got {mode!r}")
            expo = max(0.0, min(1.0, expo))
            expo_log.append(expo)

            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            # TOUCH POINT 2 -- only names in the index on this date may be ranked.
            # market_data.MEMBERSHIP is the single holder; see the note there.
            if market_data.is_pit() and market_data.MEMBERSHIP is not None:
                _members = market_data.MEMBERSHIP.members_on(dt)
                s_ = s_[[k for k in s_.index if k in _members]]
            if len(s_) < TOP_N:
                # THIS REBALANCE IS SKIPPED, AND IT USED TO BE SKIPPED SILENTLY.
                # With fewer rankable names than TOP_N the branch below does not
                # run, so no order is planned and the previous holdings carry
                # on. That is the existing behaviour and it is kept -- changing it
                # would move published numbers -- but it is now said, with the
                # date and the count. Once per (date, count, universe width) per
                # process, so four arms over one panel print it once.
                _k = (dt, len(s_), sc.shape[1])
                if _k not in _THIN_WARNED:
                    _THIN_WARNED.add(_k)
                    print(f"    WARNING {pd.Timestamp(dt).date()}: {len(s_)} rankable "
                          f"names < TOP_N={TOP_N}; rebalance skipped, previous "
                          f"holdings kept", flush=True)
            if len(s_) >= TOP_N:
                # kind="mergesort" IS STABLE; pandas' default "quicksort" is not.
                # Two names with the same score were ordered by whatever introsort
                # happened to leave, so nothing decided which of them was held.
                # Measured 2026-09-21 by results/degeneracy_measure.py: there are
                # no ties -- 0 at the TOP_N cut and 0 at the BUFFER cut on all 92
                # rebalances of both live universes, and no duplicate score
                # anywhere in either ranking. The two kinds return an IDENTICAL
                # full ranking on all 92, so this moves no published number. It is
                # here so that a tie arriving later is broken by panel order
                # rather than by the sort algorithm's internal state.
                rk = s_.sort_values(ascending=False, kind="mergesort")
                top = list(rk.index[:TOP_N])
                keep = set(rk.index[:BUFFER])
                # TOUCH POINT 3 -- forced exits join the sell set. `to_sell` is
                # computed as `held - keep` above, so removing them from `keep` is
                # that union. Empty unless mode is pit AND exit policy is forced.
                if market_data.is_pit() and market_data.MEMBERSHIP is not None:
                    keep -= market_data.MEMBERSHIP.forced_exits(set(shares.keys()), dt)
                # sizing="invvol" (default) reproduces the existing system exactly.
                # "equal" gives every one of the TOP_N positions the same share of
                # invest_value.
                # "provol" is the mirror of invvol: the raw vol instead of its
                # reciprocal, so a high-vol name gets the LARGE position. Same guard,
                # same normalisation, same fallback -- only the numerator differs.
                # Mirrored in nautilus/nt_strategy.py; the two must not drift.
                # v IS READ BY THE AUDIT BLOCK BELOW, ON EVERY PATH, so it is
                # bound here rather than inside the else. It used to be bound only
                # where it was USED FOR SIZING, which made sizing="equal" with an
                # audit dict raise UnboundLocalError at the vol60 column -- the one
                # sizing rule that could not be measured was the simplest one.
                # Hoisting changes nothing for invvol/provol: same expression, same
                # dt, one line earlier, and nothing in between touches v or pc.
                v = pc["vol"].loc[dt]
                if sizing == "equal":
                    w = {s: 1.0 / len(top) for s in top}
                else:
                    w = {}
                    for s in top:
                        vs = v.get(s, np.nan)
                        ok = (not np.isnan(vs)) and vs > 0.01
                        if not ok:
                            w[s] = 0.0
                        elif sizing == "provol":
                            w[s] = vs
                        else:
                            w[s] = 1.0 / vs
                    tot = sum(w.values())
                    w = ({s: w[s] / tot for s in top} if tot > 0
                         else {s: 1.0/len(top) for s in top})
                w["_exposure"] = expo
                pending = (w, keep)
                # The order exactly as planned, unrounded, for tools/lookahead_proof.py.
                # Audit only: nothing reads it back.
                if audit is not None:
                    audit.setdefault("orders", []).append(
                        {"decided_on": dt, "ranked": list(rk.index), "weights": dict(w),
                         "keep": sorted(keep)})
                # AN OWED SALE IS CANCELLED when this decision keeps the name: the
                # newer decision wins (owner's decision, 2026-10-16).
                for s_ in [x for x in _owed if x in keep]:
                    del _owed[s_]

                if audit is not None:
                    pv_now = sum(q * prices[k] for k, q in shares.items()
                                 if not np.isnan(prices.get(k, np.nan))) + cash
                    held = set(shares.keys())
                    m_ = breadth_momentum(mom20, dt)
                    npos, ntot = int((m_ > 0).sum()), int(len(m_))
                    audit["decisions"].append({
                        "decided_on": dt, "breadth_pos": npos, "breadth_total": ntot,
                        "breadth": round(npos/ntot, 4) if ntot else 1.0,
                        "exposure": round(expo, 4), "port_value": round(pv_now, 2),
                        "invest_value": round(pv_now*expo*0.98, 2),
                        "cash_before": round(cash, 2), "n_held_before": len(held),
                        "n_buy": len([x for x in top if x not in held]),
                        "n_sell": len([x for x in held if x not in keep])})
                    for rnk, (sym, scr) in enumerate(rk.items(), start=1):
                        if rnk > 25 and sym not in held: continue
                        vs_ = v.get(sym, np.nan)
                        act = ("BUY" if sym not in held else "HOLD-top") if sym in top \
                              else ("HOLD-buffer" if (sym in keep and sym in held)
                                    else ("SELL" if sym in held else "-"))
                        audit["ranking"].append({
                            "decided_on": dt, "rank": rnk, "symbol": sym,
                            "score": round(float(scr), 6),
                            "vol60": round(float(vs_), 4) if not np.isnan(vs_) else None,
                            "target_wt_pct": round(w.get(sym, 0.0)*100, 2) if sym in top else 0.0,
                            "held_before": sym in held, "action": act})

            if _reentry_check:
                _st.after_reentry_order(pending is not None)

        # TOUCH POINT 6, SECOND HALF -- a year assessed on a day still inside
        # that year (31 March) is charged AFTER the day's fills, so a sell that
        # day is taxed with its own year. See costs.Ledger.due_on.
        if ledger is not None:
            _due = ledger.due_on(dt, after_fills=True)
            if _due:
                cash -= _due
                cum_tax += _due
                _tax_post = _due
                if audit is not None:
                    _end = (ledger.end is not None and pd.Timestamp(dt) == ledger.end
                            and ledger.settled_at_end)
                    audit["skipped"].append({"date": dt, "side": "TAX", "symbol": "",
                        "reason": f"capital-gains tax assessed, Rs {_due:,.2f}",
                        "detail": ("settled at the backtest end, after this day's "
                                   "fills, on gains realised to date" if _end else
                                   "section 3(9): one lump sum, after this day's fills "
                                   "(assessment day inside the assessed year)")})

        mtm = sum(q * prices[s] for s, q in shares.items()
                  if not np.isnan(prices.get(s, np.nan)))
        pv = mtm + cash
        if _stop is not None:
            _act = _st.at_close(i, dt, pv, pending is not None, bool(shares),
                                i == len(dates) - 1)
            if _act == "exit":
                if pending is not None and pending is not _EXIT_ORDER \
                        and audit is not None and audit["decisions"]:
                    audit["decisions"][-1]["superseded"] = "drawdown exit"
                if audit is not None and _st.events and _st.events[-1][0] == "trigger":
                    audit["skipped"].append({"date": dt, "side": "STOP", "symbol": "",
                        "reason": "drawdown exit",
                        "detail": f"close equity Rs {pv:,.2f} is {_st.drawdown(pv):+.2%} "
                                  f"from the peak of Rs {_st.peak:,.2f} on "
                                  f"{pd.Timestamp(_st.peak_date).date()}; every holding "
                                  f"is sold at the next open"})
                pending = _EXIT_ORDER
            if _stop_log is not None:
                _stop_log.extend(_st.rows(dt, pv))
        if _dd is not None:
            _dd_invested.append(mtm / pv if pv > 0 else 0.0)
            # A, the arm's own exposure: its last rebalance decision (1.0 for
            # mode "none").
            _ds.at_close(dt, pv, mtm, shares, i == len(dates) - 1,
                         expo_log[-1] if expo_log else 1.0)
        if _costs is not None:
            _costs["days"].append({"date": dt, "cash_open": _cash_open, "interest": _cash_int,
                                   "tax_before_fills": _tax_pre, "tax_after_fills": _tax_post,
                                   "cash_close": cash})
        eq.append(pv)
        _dec_val, _dec_px = pv, prices

        if audit is not None:
            for s_h, q_h in sorted(shares.items()):
                pr_h = prices.get(s_h, np.nan)
                if np.isnan(pr_h):
                    continue
                val = q_h * pr_h
                audit["holdings"].append({"date": dt, "symbol": s_h, "qty": int(q_h),
                    "price": round(float(pr_h), 2), "value": round(val, 2),
                    "weight_pct": round(val / pv * 100, 2) if pv > 0 else 0.0})
            audit["summary"].append({"date": dt, "n_stocks": len(shares),
                "cash": round(cash, 2), "mtm": round(mtm, 2), "total": round(pv, 2),
                "invested_pct": round(mtm / pv * 100, 2) if pv > 0 else 0.0,
                "cash_pct": round(cash / pv * 100, 2) if pv > 0 else 0.0,
                "cum_tc": round(cum_tc, 2), "cum_trades": n_trades})
    # THE LEDGER RIDES OUT ON THE AUDIT DICT, NOT ON THE RETURN TUPLE. Widening
    # the tuple would break every one of this function's callers, and all of them
    # are untaxed. A caller that wants the tax trail passes an audit dict and
    # finds it under "tax"; a caller that does not is unaffected, which is what
    # keeps tax=off byte-identical rather than merely equal.
    if _dd is not None and audit is not None:
        audit["dd_events"] = _ds.events
        audit["dd"] = dict(_ds.summary(), marginal_tax=(
            marginal_tax(ledger.rows, _dd_rows) if ledger is not None else 0.0))
    if audit is not None:
        audit["buy_shortfall"] = {"rule": _shortfall, "trimmed": _n_trimmed,
                                  "refused": _n_refused}
    if audit is not None and ledger is not None:
        audit["tax"] = {"ledger": ledger, "cum_tax": cum_tax,
                        "lots": pd.DataFrame(ledger.rows), "leaked": ledger.leaked()}
    # THE COUNT GOES OUT WITH THE RUN. Requirement two: a headline figure from a
    # size-sensitive run must not be readable without the number of fills that
    # were priced at the flat rate instead. `impact_out` is an out-parameter for
    # the same reason `applied_out` is -- the return signature has 25 callers and
    # a module global is the leak settings.cadence records.
    if impact_out is not None:
        impact_out.update({"k": impact_k, "priced": _imp["priced"],
                           "exempt": _imp["exempt"],
                           "fills": _imp["priced"] + _imp["exempt"],
                           "trades": n_trades})
    # THE FOURTH VALUE IS WHAT Deployed% AND avg_exposure_pct REPORT. Without the
    # drawdown limit it is the arm's mean decided exposure, as it always was. With
    # it, the arm's exposure no longer describes the book, so it is the mean
    # invested fraction at the close, after the limit's trims and top-ups.
    if _dd is not None:
        return (pd.Series(eq, index=dates), cum_tc, n_trades,
                float(np.mean(_dd_invested)) if _dd_invested else 1.0)
    return (pd.Series(eq, index=dates), cum_tc, n_trades,
            np.mean(expo_log) if expo_log else 1.0)
