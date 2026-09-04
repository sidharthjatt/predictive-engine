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


def get(name):
    try:
        return ARMS[name]
    except KeyError:
        raise KeyError(
            f"unknown arm {name!r}; known: {', '.join(ARMS)}") from None
