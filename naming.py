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
