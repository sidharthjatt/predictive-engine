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
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Arm:
    """One arm = one (exposure mode, sizing rule) pair.

    `mode` and `sizing` are passed straight to test_exposure.backtest_exposure:
        mode   -- "none" (always 100% invested) | "breadth" (scale by breadth)
                  the function also accepts "voltgt", "const" and "both", which
                  no named arm uses.
        sizing -- "invvol" (w = 1/vol) | "provol" (w = vol) | "equal"
    """
    name: str
    mode: str
    sizing: str
    label: str          # the exact string v34_common writes into its artefacts
    equity_column: str  # the exact column name in v34_equity.csv

    @property
    def kwargs(self):
        """What to hand backtest_exposure for this arm."""
        return {"mode": self.mode, "sizing": self.sizing}


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

# The two that ship on every universe. v3 and v4 are computed only for the live
# universes, inside v34_common.run_v34 -- the 58 and the 74 have no v3/v4 at all.
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
    unknown = [n for n in want if n not in ARMS]
    if unknown:
        raise KeyError(f"cannot select unknown arm(s) {', '.join(unknown)}; "
                       f"known: {', '.join(ARMS)}")
    _SELECTED = [n for n in ARMS if n in set(want)]


def selected_names():
    """The arm names this run is working on, in ARMS order. Defaults to all four."""
    return list(ARMS) if _SELECTED is None else list(_SELECTED)


def selected():
    """selected_names() as Arm objects."""
    return [ARMS[n] for n in selected_names()]


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
    return "_" + "_".join(x for x in ARMS if x in set(n))


def get(name):
    try:
        return ARMS[name]
    except KeyError:
        raise KeyError(
            f"unknown arm {name!r}; known: {', '.join(ARMS)}") from None


# ---------------------------------------------------------------------------
# READING AN ARM'S CURVE OUT OF v2FINAL_equity.csv
# ---------------------------------------------------------------------------
# That file was written with columns named for what a curve was FOR, not for
# which arm it IS: `strategy` is v2 and `baseline_invvol` is v1. Nothing could
# ask it for v3 or v4, because those names have no slot. The live engines now
# also write the arm-keyed names (Arm.equity_column), and every reader goes
# through equity_series() below.
#
# THE FROZEN 58 AND 74 STILL WRITE ONLY THE OLD NAMES, and always will: their
# engines are those universes' provenance and are not modified. So the lookup
# tries the arm-keyed name and falls back to the legacy one. That fallback is not
# a transition shim to be deleted later -- it is how a frozen universe's file is
# read, permanently.
LEGACY_EQUITY_COLUMN = {"v1": "baseline_invvol", "v2": "strategy"}


def equity_series(df, arm):
    """One arm's equity curve from a v2FINAL_equity.csv frame, or None.

    None means "this file does not carry that arm" -- asking a frozen universe
    for v3 is a legitimate question with the answer "there isn't one", and the
    caller decides whether that is a skip or an error. Raising here would make
    every caller wrap it in a try.
    """
    name = arm.name if hasattr(arm, "name") else arm
    if name not in ARMS:
        raise KeyError(f"unknown arm {name!r}; known: {', '.join(ARMS)}")
    for col in (ARMS[name].equity_column, LEGACY_EQUITY_COLUMN.get(name)):
        if col is not None and col in df.columns:
            return df[col]
    return None


_BY_PARAMS = {(a.mode, a.sizing): a for a in ARMS.values()}


def by_params(mode, sizing):
    """The named arm for a (mode, sizing) pair, or None if it is not one of the four.

    backtest_exposure accepts modes ("voltgt", "const", "both") and a sizing
    ("equal") that no named arm uses, so this is deliberately partial: a caller that
    needs a name for an unnamed combination should say so in its own terms rather
    than have one invented here. See path_segment().
    """
    return _BY_PARAMS.get((mode, sizing))


def path_segment(mode, sizing):
    """A filesystem-safe directory name identifying one (mode, sizing) combination.

    A named arm gives its name -- "v3". Anything else gives "{mode}-{sizing}", which
    is still unique and still readable, so an exploratory combination writes beside
    the four named ones instead of into one of them. This is total by design: the
    point of the segment is that two different configurations cannot land in the
    same directory, and raising on the unnamed case would just push the collision
    back to whichever caller shrugged and passed a constant.
    """
    a = by_params(mode, sizing)
    return a.name if a is not None else f"{mode}-{sizing}"
