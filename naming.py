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
import tax as _tax

# The axes, in the order they appear in a name. This order is LOAD-BEARING: it is
# the order v34_common.py has always used, and changing it renames every
# non-default artefact in the repository.
#
# TAX IS APPENDED, NEVER INSERTED (2026-09-17). Appending leaves every existing
# non-default name -- every _r40, every _tradeable, every arm suffix -- exactly
# where it was, because the tax suffix is empty at the default and lands after
# the other three when it is not. Inserting it anywhere else in this tuple
# renames artefacts that are pinned by SHA-256 in RETIRED_UNIVERSES-manifest.txt.
AXES = ("arm", "cadence", "profile", "tax")

_SUFFIX = {
    "arm": lambda: _arm.selection_suffix(),
    "cadence": lambda: _cadence.suffix(),
    "profile": lambda: _profiles.suffix(),
    "tax": lambda: _tax.suffix(),
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


def run_label(universe, arms):
    """The line every chart title starts with: universe, arm(s), cadence, tax, profile.

    Added 2026-09-23. A cadence-3 engine chart stated no cadence anywhere, and a
    chart that does not say which run drew it cannot be checked against the run.
    `universe` is a label or a list of labels; `arms` is an iterable of arm names.
    """
    uni = universe if isinstance(universe, str) else ", ".join(universe)
    arms = list(arms)
    return (f"{uni}  |  arm{'s' if len(arms) != 1 else ''} {', '.join(arms)}  |  "
            f"cadence {_cadence.selected()}  |  tax {'on' if _tax.selected() else 'off'}"
            f"  |  profile {_profiles.selected()}")


def path_tail(rebal=None):
    """The directory-segment tail for the current cadence, profile and tax:
    "" at every default, else "@r40", "@tradeable", "@tax" in AXES order.

    ONE RULE FOR BOTH PER-COMBINATION DIRECTORY TREES. nautilus/reports/<u>/<seg>
    (nt_run.reports_segment) carried all three axes; runs/<u>/<seg>
    (paths.run_dir) carried the cadence only, so a `--tax on` or `--profile
    tradeable` arm run wrote into the same runs/<u>/<arm>/ as a research run and
    replaced its chart. Both now take the tail from here.

    THE CADENCE IS THE ARGUMENT, NOT THE SELECTION: both callers are handed
    `rebal` explicitly, and None means the default, as reports_segment always
    treated it. Profile and tax are read from the selection.
    """
    r = _cadence.DEFAULT if rebal is None else int(rebal)
    seg = "" if r == _cadence.DEFAULT else f"@r{r}"
    if not _profiles.is_default():
        seg += f"@{_profiles.selected()}"
    if not _tax.is_default():
        seg += "@tax"
    return seg


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
# RE-PROBED 2026-09-17, when the TAX axis was added. Adding an axis invalidates
# every measurement in this table, so all of it was measured again rather than
# edited by inspection. Two probe artefacts had to be removed before the numbers
# meant anything, and both would have produced a WRONG table:
#
#   _ci is EXISTENCE-GATED -- `return c if c.exists() else path`. Probing it in a
#   directory without the sibling files measures the fallback, and both _ci
#   entries reported "(nothing)". The probe now pre-creates every sibling the
#   four axes can name before it measures.
#
#   artefact_tag and chart_path take the ARM AS AN ARGUMENT, not from the
#   registry selection. Varying arm_reg and holding the argument fixed reported
#   "NO ARM" for two composers that carry it fine. The probe now varies the
#   argument alongside the selection.
#
# Corrected result: the five legacy composers carried arm/cadence/profile exactly
# as recorded above and NONE of them carried tax, which is what the four edits of
# 2026-09-17 fixed. The table below is the post-edit measurement.
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
# EVERY VALUE IS AN EXPLICIT LITERAL. It used to be `frozenset(AXES)` on eight of
# the eleven entries, which reads as "carries everything" and is a LIVE REFERENCE
# to the axis tuple. Adding the tax axis on 2026-09-17 therefore handed those
# eight an instant, unmeasured green for an axis not one of them composed -- six
# of them wrongly. That is the precise failure this table was built to stop, and
# the table's own comment ("over-crediting one hands out an unearned green") was
# describing it two lines above the construct that caused it.
#
# A spelled-out set cannot do that. An axis added to AXES now appears in NO
# entry's value until somebody measures it and types it in, so the default for a
# new axis is "unproven", which is the only safe default an enforcement table has.
CARRIES = {
    "naming.name":       frozenset({"arm", "cadence", "profile", "tax"}),
    "naming.tail":       frozenset({"arm", "cadence", "profile", "tax"}),
    "SFX":               frozenset({"arm", "cadence", "profile", "tax"}),
    "artefact_tag":      frozenset({"arm", "cadence", "profile", "tax"}),
    "_c(":               frozenset({"cadence", "profile", "tax"}),
    "_ci(":              frozenset({"cadence", "profile", "tax"}),
    "selection_suffix":  frozenset({"arm"}),
    "nt_reports_segment": frozenset({"arm", "cadence", "profile", "tax"}),
    "reports_segment":   frozenset({"arm", "cadence", "profile", "tax"}),
    "chart_path":        frozenset({"arm", "cadence", "profile", "tax"}),
    "combined_chart_path": frozenset({"arm", "cadence", "profile", "tax"}),
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
