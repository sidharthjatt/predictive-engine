#!/usr/bin/env python3
"""v34_provenance.py -- label every figure in v34_comparison.csv with n and a date.

WHY THIS EXISTS

    v34_comparison.csv holds five rows of point estimates and says nothing about
    how many runs produced them. For six of the eight universes the answer is one,
    and an unlabelled single run reads exactly like a stable number. For nifty100
    and midcap150 the answer is one for the published figure and ten for the
    price-perturbation draws around it, and those two spreads are the reason the
    label is needed at all: `results/price_noise_measure.py` moved nifty100's CAGR
    across 19.32 to 22.55 on a perturbation of one hundredth of a percent.

    So this writes the label beside the artefact. It measures nothing. Every
    number it prints is read from a file that already exists:

        <metrics_dir>/v34_params.json         run date, git state, constants
        diagnostics/price_noise_runs.csv      the stored perturbation draws

WHY IT IS A SIDECAR AND NOT A COLUMN

    Seven scripts read v34_comparison.csv as an identity gate -- purge_fix_measure,
    seed_noise_measure, seed_noise_report, shuffle_test, validate_topn,
    rebal_cadence_sweep and drawdown_exit_measure -- and several of them
    .set_index("Config") and take .max() over the non-buy&hold rows. Columns added
    to that file would pass through all seven without erroring and change what they
    compute. results/v34_common.py and results/tax_report.py both already took this
    decision on the same grounds; this follows them.

WHY THE TRACKED COPY IS IN diagnostics/

    Every results_*/metrics/ directory is in .gitignore, so a sidecar written there
    is not committed and does not survive a fresh checkout. The per-universe files
    are written anyway, because that is where a reader opens the CSV, but the
    record that is kept is diagnostics/v34_provenance.txt.

WHAT IS DECLARED RATHER THAN DERIVED

    PRICE_NOISE_SIGMA and PRICE_NOISE_N are measurements. A universe that has not
    been run through price_noise_measure has no value that could be invented for
    it, so the pair is declared through measured_universes.declare and an absence
    is printed as an absence. The two measured universes were measured because they
    are the two the README publishes; the other six were a deliberate decision not
    to spend the runs, recorded in KNOWN_ISSUES.md.
"""
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import measured_universes
from universes.registry import REGISTRY, report_order

STUDY = "v34_provenance"

# The draws this label quotes. Written by results/price_noise_measure.py, one row
# per completed run, and never edited by hand.
DRAWS = ROOT / "diagnostics" / "price_noise_runs.csv"
RECORD = ROOT / "diagnostics" / "v34_provenance.txt"

# The six columns price_noise_measure re-measures on every draw. They are its
# IDENTITY_COLS, and they are the only columns of v34_comparison.csv for which a
# perturbation spread exists.
SPREAD_COLS = ("CAGR%", "Sharpe", "MaxDD%", "Trades", "FinalEquity", "AnnVol%")

# The columns of v34_comparison.csv that carry NO spread at any sigma. They are
# point estimates and a reader must not inherit an error bar for them from the six
# above. Sortino, Calmar and Deployed% are the ones quoted in prose.
POINT_COLS = ("Sortino", "Calmar", "Deployed%", "TC_Rs", "MeanNamesHeld",
              "CashShortSkips")

# DECLARED, NOT DERIVED. sigma is the perturbation these draws were taken at; n is
# how many of them are stored. A universe absent from both mappings has never been
# measured, and declare() prints that rather than defaulting it.
PRICE_NOISE_SIGMA = {"nifty100": 0.0001, "midcap150": 0.0001}
PRICE_NOISE_N = {"nifty100": 10, "midcap150": 10}
MEASURED_FOR = ("nifty100", "midcap150")

CAVEAT = ("README.md, the block headed READ THIS BEFORE QUOTING ANY v2 FIGURE "
          "BELOW")


def params(u):
    """run_date and git state for a universe, from the artefact the run wrote."""
    f = Path(u.metrics_dir) / "v34_params.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def draws(tag, sigma):
    """The stored perturbation draws for one (universe, sigma), newest last."""
    if not DRAWS.exists():
        return []
    rows = [r for r in csv.DictReader(DRAWS.open(newline=""))
            if r["tag"] == tag and float(r["sigma"]) == sigma]
    return sorted(rows, key=lambda r: int(r["noise_seed"]))


def spread(rows, col):
    """mean/min/max/sd of one column over the draws, or None if there are none."""
    v = [float(r[col]) for r in rows]
    if len(v) < 2:
        return None
    return {"n": len(v), "mean": statistics.mean(v), "min": min(v),
            "max": max(v), "sd": statistics.stdev(v)}


def published(u, col):
    """The published v2 value of one column, read from v34_comparison.csv."""
    f = Path(u.metrics_dir) / "v34_comparison.csv"
    if not f.exists():
        return None
    for r in csv.DictReader(f.open(newline="")):
        if r["Config"].startswith("v2 "):
            return float(r[col])
    return None


def block(tag):
    """The provenance label for one universe, as a list of lines."""
    u = REGISTRY[tag]
    p = params(u)
    L = [f"UNIVERSE: {tag}"]
    if p is None:
        L += ["  v34_params.json is absent -- this universe's run date is not",
              "  recorded and no label can be written for it."]
        return L

    git = p.get("git_state", {})
    L += [f"  run date : {p['run_date']}",
          f"  git      : {git.get('commit', 'unrecorded')[:12]}"
          f"{'  WORKING TREE DIRTY' if git.get('working_tree_dirty') else ''}",
          f"  window   : {p['window_start']} to {p['window_end']}, "
          f"{p['trading_days']} trading days"]

    if tag not in PRICE_NOISE_SIGMA:
        L += ["",
              "  EVERY FIGURE IN v34_comparison.csv FOR THIS UNIVERSE IS n = 1.",
              f"  One run, on {p['run_date']}. No price-perturbation distribution",
              "  has been measured for this universe and none is implied by the",
              "  two that have. A figure here is a single draw of a distribution",
              "  whose width is not known.",
              f"  The perturbation caveat is in {CAVEAT}.",
              "  Why this universe was not measured: KNOWN_ISSUES.md, the entry",
              "  headed 'Measuring the six unmeasured universes is costed and",
              "  deferred'."]
        return L

    sigma, rows = PRICE_NOISE_SIGMA[tag], draws(tag, PRICE_NOISE_SIGMA[tag])
    if len(rows) != PRICE_NOISE_N[tag]:
        raise SystemExit(
            f"{STUDY}: {tag} declares n = {PRICE_NOISE_N[tag]} at sigma "
            f"{sigma}, and {DRAWS.name} holds {len(rows)}.\n"
            f"  The declaration and the draws must agree. Either draws were added "
            f"without updating PRICE_NOISE_N, or the file is not the one the "
            f"declaration was written against -- and a label quoting the wrong n "
            f"is the thing this module exists to prevent.")

    L += ["",
          f"  PRICE-PERTURBATION SPREAD, NOT SEED SPREAD. n = {len(rows)} at",
          f"  sigma = {sigma:.2%}, measured "
          f"{min(r['run_date'] for r in rows)} to "
          f"{max(r['run_date'] for r in rows)} by",
          "  results/price_noise_measure.py. The ten production seeds are held",
          "  fixed across all of them, so this is on top of the seed noise, not",
          "  the same quantity. The seed spread is in KNOWN_ISSUES.md, the entry",
          "  headed 'The 10-seed ensemble does not average away what it was built",
          "  to average away'.",
          "",
          "  THE v2 ROW, PUBLISHED FIGURE AGAINST ITS OWN DRAWS:",
          f"    {'column':<14}{'published':>16}{'n':>4}{'mean':>16}"
          f"{'min':>16}{'max':>16}{'sd':>14}"]
    for c in SPREAD_COLS:
        s, pub = spread(rows, c), published(u, c)
        if s is None or pub is None:
            continue
        L.append(f"    {c:<14}{pub:>16,.2f}{s['n']:>4}{s['mean']:>16,.2f}"
                 f"{s['min']:>16,.2f}{s['max']:>16,.2f}{s['sd']:>14,.2f}")

    L += ["",
          "  NO SPREAD EXISTS FOR THESE, AND THEY DO NOT INHERIT ONE:",
          f"    {', '.join(POINT_COLS)}",
          "  They are point estimates from the single published run of",
          f"  {p['run_date']}, n = 1. price_noise_measure does not recompute them,",
          "  so nothing above bounds them.",
          "",
          "  EVERY ROW OTHER THAN v2 IS n = 1. v1, v3, v4 and buy & hold were run",
          f"  once, on {p['run_date']}. price_noise_measure hardcodes the v2 arm,",
          "  so no other arm has been perturbed -- see KNOWN_ISSUES.md, the entry",
          "  headed 'price_noise_measure is arm-general in name only'.",
          f"  The perturbation caveat is in {CAVEAT}."]
    return L


# naming: axis-free -- both writes below label the CANONICAL v34_comparison.csv,
# which exists only at the all-default selection: four arms, cadence 20,
# research profile, tax off. A non-default selection writes a suffixed companion
# and does not produce the file these labels are about, so there is no axis for
# either name to carry. The per-universe name varies over the UNIVERSE, which is
# a directory, not a filename axis.
def main():
    tags = report_order(REGISTRY)
    cover = measured_universes.declare(
        STUDY, MEASURED_FOR,
        {"PRICE_NOISE_SIGMA": PRICE_NOISE_SIGMA, "PRICE_NOISE_N": PRICE_NOISE_N})

    head = ["v34_comparison.csv -- PROVENANCE AND SPREAD LABELS",
            "=" * 70,
            "",
            "Written by results/v34_provenance.py. Nothing here is measured by that",
            "script: every figure is read from v34_params.json, v34_comparison.csv",
            "and diagnostics/price_noise_runs.csv, which already existed.",
            ""] + cover + [""]

    out, wrote = list(head), []
    for tag in tags:
        lines = block(tag)
        out += lines + [""]
        side = Path(REGISTRY[tag].metrics_dir) / "v34_comparison_PROVENANCE.txt"
        if side.parent.exists():
            side.write_text("\n".join(
                ["v34_comparison.csv -- PROVENANCE AND SPREAD LABEL",
                 "Written by results/v34_provenance.py. Not committed: this",
                 "directory is in .gitignore. The kept copy is",
                 "diagnostics/v34_provenance.txt.", ""] + lines) + "\n")
            wrote.append(side)

    RECORD.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"wrote {RECORD.relative_to(ROOT)}")
    for w in wrote:
        print(f"wrote {w.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
