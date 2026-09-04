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


def nautilus_reports(u):
    """orders.csv / fills.csv / positions.csv for one universe.

    ONE DIRECTORY PER UNIVERSE, because a single shared reports/ once left only
    the last universe's files on disk. The ARM is still missing from this path,
    which is why verify_v34_arms -- looping four arms over two universes -- leaves
    only the last arm's reports behind. Recorded, not yet fixed.
    """
    return NAUTILUS_DIR / "reports" / u.tag


# --------------------------------------------------------------- diagnostics
def diagnostic(name, u=None):
    """A findings file. Some are per-universe (topn_mid.txt), some are combined
    verdicts (topn_verdict.txt); both spellings already exist."""
    DIAGNOSTICS_DIR.mkdir(exist_ok=True)
    return DIAGNOSTICS_DIR / (f"{name}_{u.tag}.txt" if u else f"{name}.txt")


# ------------------------------------------------------- proposed, not in use
def run_dir(u, arm=None):
    """THE PROPOSED LAYOUT -- runs/{universe}/{arm}/. Nothing calls this yet.

    It exists so the target shape is written down next to the current one rather
    than only in a report. Adopting it means moving artefacts and repointing every
    reader, which is its own step with its own verification.
    """
    d = ROOT / "runs" / u.tag
    return d / arm.name if arm is not None else d
