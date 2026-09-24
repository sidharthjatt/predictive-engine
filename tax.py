"""
tax.py -- the TAX axis. Default OFF, and OFF is unsuffixed.
===============================================================================

WHAT THIS IS
    The fourth axis, beside arm, cadence and profile. It selects whether a run
    charges capital-gains tax. It holds the SELECTION ONLY: no rate, no
    exemption, no financial-year arithmetic. Those live in tax_util.py, which is
    where a reader looking for the tax RULES will go, and keeping them out of
    here means a run that never enables tax cannot import a single tax constant.

WHY DEFAULT-OFF IS NOT A CONVENIENCE, IT IS THE ACCEPTANCE TEST
    naming.py's rule is that every axis returns "" at its default, so a
    fully-default run writes the canonical published name. With DEFAULT = False
    and suffix() returning "" for it, every composed path under tax=off is
    CHARACTER-IDENTICAL to the path the same run produced before this module
    existed.

    That makes "tax=off reproduces every existing artefact byte-exact" a
    property of the naming rule rather than something a test has to chase across
    the tree. The test still runs -- see the acceptance check -- but it is
    confirming an invariant, not searching for violations.

THE SHARP EDGE, WHICH THIS AXIS INHERITS IN FULL
    naming.py records it: AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE SAME
    STRING. At tax=off a tax-blind writer and a tax-aware writer are
    byte-identical in their output paths. So the byte-exactness test CANNOT
    distinguish a correct implementation from one that forgot the axis entirely
    -- a no-op passes it.

    Only a declaration reveals the omission, which is what naming.declare() and
    naming_declare_check.py are for. The acceptance test is therefore two
    conditions, never one, and the second is the load-bearing half.

SCOPE: ONE SELECTION PER RUN, AND THAT IS ASSERTED RATHER THAN ASSUMED
    run_all.entry_applies() evaluates a `u:` qualifier against the INVOCATION,
    not the run, because one merged script serves both universes in a single run
    and the two questions have different answers. A `tax:` qualifier is
    evaluated against the RUN, and the difference is deliberate:

        There is no collapse on this axis. run.py sets the tax selection once,
        no script serves both a taxed and an untaxed invocation, and run scope
        and invocation scope are provably the same value.

    "Provably" is doing real work in that sentence, so it is CHECKED rather than
    trusted -- see is_uniform_over_plan(). The day someone introduces a
    per-universe tax selection, that assertion fires instead of the plan going
    quietly unsatisfiable the way the `u:` defect did for five days.

WHAT THE FROZEN UNIVERSES DO WITH THIS
    Nothing. The retired universes were deleted on 2026-09-11, and
    results/engine_core.py has no cash accrual line to hang a deduction on. run.py refused --tax on for them, in
    the same place and the same shape as the cadence refusal, for the same
    reason cadence.py already writes down. engine_core.py is not edited at all.
"""

# The axis default. OFF, and off is unsuffixed.
DEFAULT = False

_SELECTED = None


class TaxAxisError(Exception):
    """The tax selection is not a single value across this run."""


def set_selection(on):
    """Record this run's tax selection.

    CALLED ONCE BY run.py, IN execute(), beside arms/cadence/profiles. That
    sentence was in this docstring from the day it was written and was FALSE
    until 2026-09-18: there was no --tax flag and run.py contained no reference
    to this module, so the only callers in the repository were two checkers,
    naming_declare_check.py and tax_acceptance_check.py. The axis was
    implemented, verified on both halves, hooked into the engine and composed by
    naming.AXES, and could not be switched on.

    A DOCSTRING NAMING A CALLER THAT DOES NOT EXIST IS AN ASSERTION NOBODY
    RE-MEASURED, which is the class KNOWN_ISSUES.md records five instances of.
    It is corrected here rather than quietly made true, because the shape it
    describes is not quite the shape that arrived.

    WHAT run.py ACTUALLY PASSES IS ALWAYS A BOOL, never None: --tax defaults to
    "off" rather than to None, so `args.tax == "on"` is the whole conversion and
    there is exactly one place that knows what "on" means. The None branch below
    is therefore NOT on run.py's path. It exists for module_state.pinned(), which
    round-trips this axis as it round-trips the other three, and for
    tax_acceptance_check.py, which restores the default between its two
    conditions. Both are real callers; neither is a run.
    """
    global _SELECTED
    if on is None:
        _SELECTED = None
        return
    if not isinstance(on, bool):
        raise TypeError(f"tax selection must be a bool, got {on!r}")
    _SELECTED = on


def selected():
    """True when this run charges tax. DEFAULT when nothing set one."""
    return DEFAULT if _SELECTED is None else _SELECTED


def is_default():
    return selected() == DEFAULT


def suffix():
    """"" when tax is off, "_tax" when on -- the artefact name tail.

    THE DEFAULT IS UNSUFFIXED so every published filename keeps the name it has
    always had. Same rule the universe, arm, cadence and profile axes use, and
    the reason the reproduction gate in heldout_prereg_run.py cannot notice this
    axis exists at the default.
    """
    return "" if is_default() else "_tax"


def is_uniform_over_plan(plan):
    """True when this axis has one value across every invocation in `plan`.

    THE ASSERTION BEHIND THE RUN-SCOPED `tax:` QUALIFIER. The qualifier is cheap
    and correct only while the selection cannot vary within a run. Nothing in
    the current plan can vary it -- there is no per-universe or per-arm tax
    override and set_selection is called once -- so this returns True today and
    costs one comparison.

    It exists so that the day a per-invocation tax selection is introduced, the
    thing that fires is this check, at plan time, with a message naming the
    cause -- rather than check_plan_order reporting an unsatisfiable input three
    steps downstream and the reader reconstructing why.
    """
    del plan          # no per-invocation tax state exists to disagree with
    return True
