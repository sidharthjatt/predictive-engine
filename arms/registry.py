"""
arms/registry.py -- the single definition of what an ARM is.
============================================================

WHY THIS IS SHORT, AND WHY IT STILL EARNS A FILE
    Unlike universes, the arms were never duplicated: they are two keyword
    arguments to `test_exposure.backtest_exposure`, and v34_common.py already
    assembles the four named combinations in one place. There is no nineteen-way
    duplication to collapse here.

    What IS scattered is the NAMING. "v1".."v4" appear as label strings in
    v34_common, as a list of pairs in verify_v34_arms, and as column names in
    v34_equity.csv -- and those three did not agree.

    Until 2026-09-04 verify_v34_arms.ARMS listed only SIZING, pairing v1 with v2
    and v3 with v4, because the Nautilus port had no exposure mode at all and
    always ran at breadth: its "four arms" were two configurations run twice. The
    port now takes mode, so the four arms are four arms and this module is the one
    definition all of them read.

    This module names the four arms once, in terms of the two parameters that
    actually produce them, so a caller cannot invent a fifth spelling.

NOTHING HERE CHANGES BEHAVIOUR. The values are exactly those v34_common passes.

THE STOP ARMS, v5 AND v6 (2026-10-02, experiments/DRAWDOWN_STOP_PREREG.txt).
    v5 is v1 plus the drawdown stop and v6 is v3 plus the stop. They live in
    STOP_ARMS, not in ARMS. ARMS stays the core four: everything that iterates it,
    `--arm all`, the full-selection test and the canonical v34_* files see exactly
    what they saw before. A stop arm is selected by name and writes companion
    v34_stop_* files. They join the core set only if the measurement accepts them.

    THE STOP IS SEALED until the band file of the pre-registration is committed:
    Arm.kwargs raises for a stop arm, so no engine, port or audit can run one at
    the registered threshold before then. The only way past the seal is the test
    fixture below, which replaces the threshold and is never a result.
"""
import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


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
    return t


def stop_sealed():
    """True until BAND_FILE exists and git tracks it."""
    if not BAND_FILE.exists():
        return True
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(BAND_FILE)],
                       cwd=_ROOT, capture_output=True)
    return r.returncode != 0


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
                  the function also accepts "voltgt", "const" and "both", which
                  no named arm uses.
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
# universes, inside v34_common.run_v34.
SHIPPING = [ARMS["v1"], ARMS["v2"]]


# ---------------------------------------------------------------------------
# WHAT THIS RUN SELECTED -- the same distinction universes/registry.py draws.
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

    backtest_exposure accepts modes ("voltgt", "const", "both") and a sizing
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
