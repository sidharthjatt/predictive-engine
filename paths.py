"""
paths.py -- where every artefact goes, derived once.
====================================================

WHAT THIS IS FOR
    Output paths are currently written as literals at the point of use: a script
    imports its universe's config module, binds `M = config_mid.METRICS_DIR_MID`,
    and then writes `M / "v34_comparison.csv"`. That works, and it is why the
    universes do not collide today -- the universe is in the DIRECTORY. But it
    means the layout is not stated anywhere; it is implied by ninety-odd write
    calls spread across the repository.

    This module states it. Every function here returns the path that is ALREADY
    produced today. It is a description, not a redesign.

WHAT IT DOES NOT DO YET, DELIBERATELY
    The survey proposed `runs/{universe}/{arm}/` so that two arms cannot overwrite
    each other -- the collision that makes verify_v34_arms leave only the last
    arm's Nautilus reports on disk. That change MOVES artefacts, so it is not part
    of building the definition. `run_dir()` below records the proposed layout and
    is not called by anything; adopting it is a separate, verifiable step.

    Until then `metrics()` is the real answer and carries no arm, exactly as the
    repository behaves now.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NAUTILUS_DIR = ROOT / "nautilus"
DIAGNOSTICS_DIR = ROOT / "diagnostics"


# --------------------------------------------------------------- score panels
def score_cache(u):
    """Permanent score panel. Written at the END of run_all.py, so a script that
    reads it cannot run standalone before the first full pipeline."""
    return u.score_cache


def score_tmp(u):
    """Working score panel in /tmp. NOTE this path carries no universe-and-run
    identity beyond the universe tag: two processes on the same universe share it
    and will overwrite each other."""
    return u.score_tmp


def raw_cache(u):
    return u.raw_cache


def raw_tmp(u):
    return u.raw_tmp


# ------------------------------------------------------------------- outputs
def metrics(u):
    """The universe's artefact directory. THE UNIVERSE IS IN THE PATH; the arm is
    not, which is why all four arms share one v34_comparison.csv."""
    return u.metrics_dir


def artefact(u, name):
    """One named artefact for a universe, e.g. artefact(mid, 'v34_comparison.csv')."""
    return u.metrics_dir / name


def tagged_artefact(u, stem, ext="csv"):
    """The daily-audit family, which puts the tag in the FILENAME as well as the
    directory -- daily_holdings_mid.csv and so on. Belt and braces, and the only
    place in the repository that does it."""
    return u.metrics_dir / f"{stem}_{u.tag}.{ext}"


# ------------------------------------------------------------------ nautilus
def nautilus_scores(u):
    """Score parquet the port reads. The universe is in the FILENAME here."""
    return NAUTILUS_DIR / "data" / u.nautilus_scores


def nautilus_reports(u, arm=None):
    """orders.csv / fills.csv / positions.csv for one universe and one arm.

    ONE DIRECTORY PER UNIVERSE AND ARM. A single shared reports/ once left only the
    last universe's files on disk; adding the universe fixed that and left the same
    hole one level down, so verify_v34_arms -- four arms over two universes -- kept
    only the last arm's reports while the directory still looked like the
    universe's. Both axes are in the path now.

    `arm` may be an Arm, an arm name, or None. None returns the universe directory
    itself, which is what a caller wants when it is listing every arm rather than
    naming one.
    """
    d = NAUTILUS_DIR / "reports" / u.tag
    if arm is None:
        return d
    return d / (arm if isinstance(arm, str) else arm.name)


# --------------------------------------------------------------- diagnostics
def diagnostic(name, u=None):
    """A findings file. Some are per-universe (topn_mid.txt), some are combined
    verdicts (topn_verdict.txt); both spellings already exist."""
    DIAGNOSTICS_DIR.mkdir(exist_ok=True)
    return DIAGNOSTICS_DIR / (f"{name}_{u.tag}.txt" if u else f"{name}.txt")


# ------------------------------------------------------- proposed, not in use
DEFAULT_REBAL = 20

# Directories a run's artefacts can land in. Used to collect a run folder; kept
# here beside run_dir() rather than in run.py so the two agree about what an
# artefact IS.
#
# THE PER-UNIVERSE HALF IS READ FROM THE REGISTRY, not written down. It used to be
# four literal paths, two of which (results74/metrics, and results/metrics as the
# 58's output home) outlived the universes that wrote into them -- a run folder
# would still have gone looking for artefacts nothing could produce. A new
# universe's metrics dir is now collected the moment it is registered.
#
# results/metrics IS STILL LISTED, but no longer as any universe's output: it is
# the shared, non-universe artefact directory (stability_*, feature docs). See
# RETIRED_UNIVERSES.md and engine_core.refuse_universe_artefact().
def _artefact_dirs():
    from universes.registry import REGISTRY
    per_universe = tuple(
        str(u.metrics_dir.relative_to(ROOT)) for u in REGISTRY.values())
    return per_universe + ("results/metrics", "runs",
                           "nautilus/reports", "nautilus/data")


ARTEFACT_DIRS = _artefact_dirs()


def run_folder_name(uni_tags, arm_names, rebal, when=None):
    """`20260906T1432_all_all_r20` -- one folder per invocation, named for it.

    THE NAME SAYS WHAT THE RUN WAS, not just when it happened. A timestamp alone
    sorts correctly and tells you nothing; the selection is what you actually
    search for six weeks later. "all" is used where an axis is fully selected,
    because 58-74-mid-n100_v1-v2-v3-v4 is not more informative than "all", only
    longer.

    The cadence is always spelled, including the default, so that a folder name is
    never ambiguous about which cadence produced it -- unlike the ARTEFACT names,
    where an unsuffixed file must keep meaning the published default.
    """
    import datetime
    ts = (when or datetime.datetime.now()).strftime("%Y%m%dT%H%M%S")
    u = "all" if len(uni_tags) >= 4 else "-".join(uni_tags)
    a = "all" if len(arm_names) >= 4 else "-".join(arm_names)
    return f"{ts}_{u or 'none'}_{a or 'none'}_r{int(rebal)}"


def run_dir(u, arm=None, rebal=None):
    """runs/{universe}/{arm}/ -- and {arm}@r{n} for a non-default cadence.

    THE CADENCE BELONGS IN THE PATH, AND ITS ABSENCE WAS A BUG. `--rebal 40`
    wrote its results straight into runs/mid/v1/, replacing the published
    cadence-20 artefacts with cadence-40 ones. params.json recorded `rebal: 40`,
    so the FILE said what it was while the PATH said something else -- and the
    next reader of runs/mid/v1/comparison.csv had no way to know. Verified by
    checksum before this change: one `--rebal 40` run changed that file.

    THE DEFAULT CADENCE IS UNSUFFIXED, so runs/mid/v1/ keeps meaning exactly what
    it has always meant and every published artefact under runs/ is untouched.
    Only a non-default cadence gets a name of its own: runs/mid/v1@r40/.

    "@" RATHER THAN "_" separates the two axes visually and cannot collide with an
    arm name: arm names are v1..v4 and never contain "@", so runs/mid/v1@r40 can
    only ever parse one way.
    """
    d = ROOT / "runs" / u.tag
    if arm is None:
        return d
    seg = arm.name
    if rebal is not None and int(rebal) != DEFAULT_REBAL:
        seg = f"{seg}@r{int(rebal)}"
    return d / seg
