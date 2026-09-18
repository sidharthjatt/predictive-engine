#!/usr/bin/env python3
"""measured_universes.py -- a probe DECLARES which universes it has measurements
for, and its own output says so.

WHAT THIS IS FOR, AND WHY IT IS NOT DERIVATION
    Three measurement probes carry per-universe MEASURED constants -- the noise
    floor, G4's expected tradability counts, the months a purge study cuts on.
    None of them can be computed from a registry row: they are results, produced by
    running something against real data, and a universe that has not been measured
    has no value that could be invented for it.

    So they are not derived. They are DECLARED, the same shape
    make_combined_universes.LIQUIDITY uses for NOT_MEASURED: presence is
    compulsory, and an absence is something somebody STATED rather than a gap
    nobody noticed.

THE DEFECT THIS CLOSES
    Each of the three built its working set from a hand-written pair:

        UNIVERSES = {u.tag: ... for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])}

    A THIRD UNIVERSE IS NOT A KeyError THERE. It is simply absent: the probe runs,
    reports on two universes, writes a diagnostic that looks complete, and says
    nothing about the third. A study covering 2 of 3 is indistinguishable from one
    covering 3 of 3 -- instance seven in KNOWN_ISSUES, in the tool set rather than
    the load-bearing set.

    THE CONSTANT THAT MAKES THIS WORTH A MODULE IS SEED_FLOOR. It is the measured
    noise floor. Its invented predecessor put every threshold in this project
    against half the real bar, and correcting it changed the conclusions. A probe
    that quietly narrows its universe coverage is that failure waiting to happen
    again, in the one measurement that moved everything else.

WHAT A DECLARATION BUYS, IN THREE PARTS
    1. THE SET THE PROBE ITERATES COMES FROM THE DECLARATION, so it cannot
       disagree with the constants the probe holds.
    2. A DECLARED UNIVERSE MISSING FROM A CONSTANT IS A REFUSAL naming the
       constant and the tag. That is a hole, not a default, and the probe stops
       before producing a diagnostic with a gap in it.
    3. A REGISTERED UNIVERSE THE PROBE HAS NO MEASUREMENT FOR IS CORRECT, and is
       PRINTED INTO THE PROBE'S OWN OUTPUT. The reader is told what the study does
       not cover instead of inferring it from which sections appear.

    rebal_cadence_sweep.SEED_FLOOR already does exactly this on the ARM axis --
    None means NEVER MEASURED and floor_verdict returns UNKNOWN rather than
    substituting a number. This is the same contract on the universe axis.

ORDER IS LOAD-BEARING AND COMES FROM THE DECLARATION. Each of the three probes
says so in its own comments: the report is written universe by universe, in the
order given. So `measured_for` is a SEQUENCE, not a set, and it is returned in the
order it was declared rather than sorted.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def declare(study, measured_for, constants, registry=None):
    """Validate a probe's universe declaration; return its coverage report lines.

    study        the probe's name, for the refusal messages and the report block
    measured_for tags this probe has measurements for, IN THE ORDER IT REPORTS
    constants    {"NAME": mapping} -- every mapping must hold a key per declared
                 tag. For a nested constant, pass the inner mappings by name:
                 {"SEED_FLOOR[v1]": SEED_FLOOR["v1"], ...}

    Raises SystemExit on a declaration that cannot be honoured. Both cases stop
    the probe rather than warning, because the output of a measurement probe is
    quoted -- a warning above a 100-line diagnostic is read once, and the
    diagnostic outlives the terminal it was printed in.
    """
    if registry is None:
        from universes.registry import REGISTRY as registry

    unknown = [t for t in measured_for if t not in registry]
    if unknown:
        raise SystemExit(
            f"{study}: declares measurements for universe(s) "
            f"{', '.join(unknown)}, which the registry does not define "
            f"({', '.join(registry)}).\n"
            f"  A study cannot measure a universe that does not exist. Either the "
            f"universe was removed and these constants are stale, or the tag is a "
            f"typo -- and a typo here would silently drop that universe from the "
            f"study, which is the failure this declaration exists to prevent.")

    holes = [(name, t) for name, mapping in constants.items()
             for t in measured_for if t not in mapping]
    if holes:
        raise SystemExit(
            f"{study}: declares measurements for "
            f"{', '.join(measured_for)}, but these constants do not carry them:\n"
            + "\n".join(f"    {name} has no entry for {t!r}" for name, t in holes)
            + "\n  A declared universe with no measured value is a HOLE, not a "
              "default. Add the measurement, or remove the tag from the "
              "declaration -- removing it is a statement that the study does not "
              "cover that universe, and the report will say so.")

    unmeasured = [t for t in registry if t not in measured_for]
    lines = [
        "  UNIVERSE COVERAGE OF THIS STUDY -- declared, not inferred from the "
        "sections below.",
        f"    measured  : {', '.join(measured_for)}"
        f"   ({', '.join(sorted(constants)) or 'no per-universe constants'})",
    ]
    if unmeasured:
        lines += [
            f"    NOT MEASURED: {', '.join(unmeasured)}",
            "    Those universes are registered and this study has no measurement "
            "for them.",
            "    NOTHING BELOW APPLIES TO THEM, and their absence from the tables "
            "is not a result.",
        ]
    else:
        lines.append("    NOT MEASURED: none -- every registered universe is "
                     "covered by this study.")
    return lines
