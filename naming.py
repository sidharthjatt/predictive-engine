"""
naming.py -- the single naming authority. One place composes an artefact's name.
===============================================================================

WHY THIS EXISTS
    The same bug has now been found on three axes in turn: a hardcoded artefact
    name where a selection-derived one belonged, on the CADENCE axis, then the
    ARM axis, then the PROFILE axis. Each was fixed at its own call site. That is
    why it kept recurring -- there was no single place to fix it, so each new axis
    re-opened the same hole somewhere else.

    The composition rule itself was never the problem. It is four lines, and
    `results/v34_common.py:300` already writes them correctly:

        SFX = arm_reg.selection_suffix() + cadence.suffix() + profiles.suffix()

    The problem is that those four lines are RETYPED at every site, and a site
    that retypes three of the four axes is indistinguishable, by reading, from one
    that legitimately varies over three. This module makes the composition callable
    once and the omission declarable -- so that leaving an axis out becomes a
    statement a reader can check, rather than an absence nobody can see.

WHAT IT DOES NOT DO
    It does not rename anything. `tail()` returns exactly the string the existing
    sites already build, in the existing order, with the existing default-is-empty
    rule on every axis. Adopting it at a site is a refactor with no artefact churn;
    if a filename moves, that is a bug in this module, not an intended migration.

THE DEFAULT-IS-UNSUFFIXED RULE, AND ITS ONE SHARP EDGE
    Every axis returns "" at its default, so a fully-default run writes the
    canonical published name. That is what keeps the seven v34_comparison gates
    reading one file. It also means AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE
    SAME STRING -- which is precisely how site 12 went unnoticed: a research-profile
    run and a profile-blind writer are byte-identical in their output paths, and
    they differ only when someone finally runs `tradeable`. The name cannot reveal
    the omission. Only a declaration can, which is what `declare()` is for.
"""
import arms.registry as _arm
import cadence as _cadence
import profiles as _profiles

# The axes, in the order they appear in a name. This order is LOAD-BEARING: it is
# the order v34_common.py has always used, and changing it renames every
# non-default artefact in the repository.
AXES = ("arm", "cadence", "profile")

_SUFFIX = {
    "arm": lambda: _arm.selection_suffix(),
    "cadence": lambda: _cadence.suffix(),
    "profile": lambda: _profiles.suffix(),
}


class UndeclaredAxis(Exception):
    """A site composed a name without saying what it varies over."""


def tail(axes=AXES):
    """The artefact name tail for the CURRENT selection, over the given axes.

    tail() with no argument is the full four-axis composition and is what almost
    every site wants. Passing a subset is the explicit, greppable way to say "this
    artefact genuinely does not vary over the profile" -- and every such call is
    expected to carry a comment saying why.
    """
    unknown = [a for a in axes if a not in _SUFFIX]
    if unknown:
        raise UndeclaredAxis(
            f"unknown axis {unknown!r}; known axes are {', '.join(AXES)}")
    return "".join(_SUFFIX[a]() for a in AXES if a in axes)


def name(stem, ext, axes=AXES):
    """A full artefact filename: stem + tail + ext. `ext` carries its own dot."""
    return f"{stem}{tail(axes)}{ext}"


# ---------------------------------------------------------------------------
# THE LEGACY COMPOSERS, AND EXACTLY WHICH AXES EACH ONE CARRIES
# ---------------------------------------------------------------------------
# This replaces a MEMBERSHIP list. Gate 2 used to accept a site if its write
# expression mentioned any of a set of blessed helper names -- which asked "is
# this composer on the list?" and never "does this composer carry the axes the
# site just declared?". A helper that composes wrongly got a green, and a green
# from an enforcement check reads as proof. That is worse than no check.
#
# MEASURED, NOT ASSUMED. Every entry below was probed by varying one axis off
# its default at a time and observing whether the composed name changed
# (2026-09-12). Six of the eight entries on the old list turned out NOT to carry
# the three axes a site could freely declare beside them:
#
#   naming.name / naming.tail             arm, cadence, profile   SOUND
#   SFX            v34_common.py:300      arm, cadence, profile   SOUND
#   artefact_tag   audit_step.py:108      arm, cadence, profile   SOUND
#                                          (arm rides in the tag body: v3 -> mid_v3)
#   _c             engine_v2_final_mid    cadence, profile        NO ARM
#   _c             engine_v2_final_n100   cadence, profile        NO ARM
#   _ci            make_mid_chart         cadence, profile        NO ARM
#   _ci            make_n100_chart        cadence, profile        NO ARM
#   _ci            make_combined_universes  cadence               NO ARM, NO PROFILE
#   selection_suffix  arms/registry.py    arm                     NO CADENCE, NO PROFILE
#
# The two _c composers and the two chart _ci composers carrying no arm is not
# necessarily a defect: v2FINAL_equity.csv holds every arm as COLUMNS, so the arm
# is legitimately not in that filename. What was a defect is that a site could
# declare `arm,cadence,profile` beside any of them and pass.
#
# Gate 2 now compares DECLARED against CARRIED and fails on anything the composer
# cannot support. An unknown composer carries nothing and fails, which is the
# right default: a new helper must be measured before it can certify anything.
#
# RETIREMENT. Each entry leaves this table when its sites route through name()
# instead. The table is a migration ledger, not a permanent fixture -- when it is
# empty, delete it.
CARRIES = {
    "naming.name":       frozenset(AXES),
    "naming.tail":       frozenset(AXES),
    "SFX":               frozenset(AXES),
    "artefact_tag":      frozenset(AXES),
    "_c(":               frozenset({"cadence", "profile"}),
    "_ci(":              frozenset({"cadence", "profile"}),
    "selection_suffix":  frozenset({"arm"}),
    "nt_reports_segment": frozenset(AXES),   # nt_run.reports_segment()
    "reports_segment":   frozenset(AXES),
    "chart_path":        frozenset(AXES),
    "combined_chart_path": frozenset(AXES),
}

# `_ci` is three different functions and a textual check cannot tell them apart,
# so the entry is pinned to the WEAKEST of the three. It read `cadence` alone
# until 2026-09-12, when make_combined_universes' copy was brought up to the
# cadence+profile composition its two siblings already had -- so the three now
# agree and the pin costs nothing. If they ever diverge again this entry drops to
# the weakest of them: under-crediting a composer costs a comment, over-crediting
# one hands out an unearned green.
CARRIES_NOTE = "_ci( is pinned to the weakest of three same-named composers"


def carried_axes(expr):
    """The axes a write expression can actually support, from CARRIES."""
    got = set()
    for token, axes in CARRIES.items():
        if token in expr:
            got |= set(axes)
    return got
