"""
universes/registry.py -- the single definition of what a universe IS.
=====================================================================

WHY THIS EXISTS
    Nineteen files independently declare a `UNIVERSES` dict mapping a tag to its
    paths, under NINE mutually incompatible key vocabularies -- `perm`/`tmp` in
    validate_topn and shuffle_test, `score_perm`/`score_tmp`/`raw_perm`/`raw_tmp`
    in validate_sizing and validate_breadth_live, `sc`/`sc_tmp`/`raw`/`raw_tmp`/`md`
    in purge_fix_measure, `cache`/`scores`/`metrics`/`tag`/`end` in nt_run, and so
    on. They express the same handful of facts and cannot be checked against each
    other. Adding a universe means editing nineteen files; deleting one means
    finding all nineteen.

    This module is that definition, once. It is DECLARATIVE ONLY -- it reads the
    existing config modules and reports what is already true. Nothing here changes
    a path, and adopting it in a caller must not change that caller's behaviour.

WHAT IS DELIBERATELY NOT DERIVED BY FORMULA
    The cache filenames look like they follow a rule -- v5_expanding /
    v74_expanding / v_mid_expanding -- but they do not, quite: the raw panel is
    `raw_panel_20.csv` on the 58 and `raw_panel74_20.csv` on the 74, while its
    permanent copy is `raw_panel_cache.csv` and `raw_panel74_cache.csv`. A clever
    stem rule would reproduce three of the four and silently invent the fourth.
    They are written out per universe instead, because a wrong path that LOOKS
    derived is worse than four explicit strings.

THE 58's DATA DIRECTORY IS NOT config.RAW_DATA_DIR
    engine_core.build_panel defaults to `config.RAW_DATA_DIR / "nifty50"`, which
    holds the 58 CSVs; `config.RAW_DATA_DIR` itself is the parent and contains the
    other universes' folders. Pointing a panel build at the parent would sweep in
    every universe at once.

    Note also that `config.SYMBOLS` is NOT the 58's symbol list -- it holds five
    names, is used nowhere, and is vestigial. The 58 is defined by its directory,
    which is why `symbols()` returns None for it: there is no authoritative list
    to check a built panel against, unlike mid and n100.

THERE IS NO `frozen` FLAG ANY MORE, DELIBERATELY
    The 58 and the 74 carried `frozen=True`, which pinned purge_mode="calendar",
    value_at_open=False and a year-cut window so their published numbers could not
    move. Both universes were deleted on 2026-09-11 and the flag went with them
    rather than being kept "for the next retirement": an axis that is defined but
    drives nothing reads as live to the next person. If a universe needs freezing
    again, the field comes back then, with a universe actually setting it.
    See RETIRED_UNIVERSES.md.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib

# config IS NOT A UNIVERSE'S CONFIG, IT IS THE PROJECT'S -- BT_START_DATE,
# BT_END_DATE, read_price_csv and require_cache all live in it and every universe
# uses them. Its absence is a broken checkout, not a universe removal, so it is
# imported unconditionally and fails loudly. (It also happens to hold the retired
# 58's paths; removing the 58 means dropping its entry below, not deleting
# config.py.)
import config


def _optional(name):
    """Import a per-universe config module, or None if it is not in the tree.

    A UNIVERSE MUST BE REMOVABLE BY DELETING ITS CONFIG AND ITS DATA. Importing
    all four unconditionally made that impossible: deleting config_n100.py made
    THIS module unimportable, and since almost everything imports the registry,
    removing one universe took down the other three. Going through one universe to
    reach another is exactly what the registry exists to prevent.

    Only ImportError is caught, and only for the module itself. A config that
    exists but raises -- a missing data directory, a bad symbol list -- is a real
    fault in a universe that is meant to be present, and is left to propagate.
    """
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


config_mid = _optional("config_mid")
config_n100 = _optional("config_n100")

HORIZON = 20          # engine_core.HORIZON; repeated here only to name the caches


@dataclass(frozen=True)
class Universe:
    """One universe, as the repository already defines it.

    Field names are chosen to be readable rather than to match any one of the
    nineteen existing vocabularies -- matching one would misdescribe the others.
    """
    tag: str                      # "58" | "74" | "mid" | "n100"
    label: str                    # for chart titles and report headers
    data_dir: Path                # what build_panel is pointed at
    metrics_dir: Path             # where this universe's artefacts live
    score_tmp: Path               # working score panel
    score_cache: Path             # permanent score panel
    raw_tmp: Path                 # working raw feature panel
    raw_cache: Path               # permanent raw feature panel
    nautilus_scores: str          # parquet filename under nautilus/data/
    nautilus_end: str             # backtest end date the port uses
    purge_mode: str               # "trading" -- purge measured in trading rows
    index_name: Optional[str]     # published index, excluded from the universe
    # THE PUBLISHED INDEX PRICE FILE, or None where the universe has no published
    # index at all. index_name has always recorded that a universe HAS one; this
    # records WHERE it is, so a step that plots the cap-weighted benchmark can ask
    # the universe instead of importing that universe's config module by name.
    # None for the retired 58 and 74: they are directory-defined baskets with no
    # published index series, which is a fact about them and not a missing path.
    index_file: Optional[Path]
    year_range: Optional[Tuple[int, int]]      # retired universes cut by year; None here
    date_range: Optional[Tuple[object, object]]  # live universes cut by date
    _symbols: Optional[Callable]  # authoritative symbol list, where one exists
    _prepare: Optional[Callable]  # brings data_dir into existence, where that is needed

    # ------------------------------------------------------------------
    # WHAT THE ENGINE REPORTS FOR THIS UNIVERSE
    # ------------------------------------------------------------------
    # Added 2026-09-15 with step 5, the engine merge. engine_v2_final_mid.py and
    # engine_v2_final_n100.py had diverged in 95 lines of code beyond their tags --
    # unlike the step 3 and step 4 pairs, which differed only in the tag -- and some
    # of that divergence REACHES PUBLISHED ARTEFACTS: v2FINAL_params.json carries a
    # different key set and key ORDER per universe, and chart_v2FINAL.png carries a
    # different title.
    #
    # IT IS PRESERVED AS DATA, NOT UNIFIED. A merge is verifiable by the gate; an
    # artefact change is a judgement, and putting both in one commit would leave a
    # moved byte with two possible causes. Unifying any of this is a separate,
    # declared change.
    #
    # validation_status IS DELIBERATELY NOT A UNIFORM SHAPE. mid carries a dict of
    # eight measured results; n100 carries a sentence saying the work was not done
    # on this universe. That asymmetry is the RECORD OF WHICH UNIVERSE GOT THE WORK,
    # and flattening both into one shape would read as though both were measured.
    # The type tells them apart: dict means measured, str means not.
    validation_status: object = None
    engine_params_keys: tuple = ()        # v2FINAL_params.json keys, IN ORDER
    engine_params_static: dict = None     # values for keys that are not computed
    engine_text: dict = None              # banner, chart title, console blocks

    # WHAT THE CHART STEP RENDERS FOR THIS UNIVERSE. Added 2026-09-15 with step 6.
    # make_mid_chart.py and make_n100_chart.py diverged in 204 code lines ignoring
    # whitespace, and SOME OF IT REACHES THE PNG: two render parameters, one legend
    # label, and the output stem itself. Preserved, not harmonised, for the same
    # reason as the engine's: a merge is verifiable by the gate, an artefact change
    # is a judgement, and they do not belong in one commit.
    #
    # Most of the pair's labels are NOT here because they derive from data the
    # registry already has -- "<tag> buy&hold (equal-weight universe)" from tag,
    # "<index> (cap-weighted index)" from index_name. Only what cannot be derived
    # is written down.
    chart_text: dict = None

    def symbols(self):
        """The tradable names, or None when the directory is the definition."""
        return None if self._symbols is None else self._symbols()

    def prepare_data_dir(self):
        """The directory build_panel should glob, READY TO USE.

        WHY THIS IS AN ACTION AND NOT JUST data_dir. For the 58 and the 74 the
        directory simply exists and this returns it. For mid and n100 it does not:
        their source folder holds the published INDEX alongside the constituents,
        and build_panel globs whatever directory it is handed, so pointing it at the
        source would sweep NIFTYMIDCAP150.csv or NIFTY100.csv in as one more
        tradable name. config_mid/config_n100 solve that by maintaining a symlink
        directory containing the constituents ONLY, and rebuilding it -- pruning
        anything stale -- each time it is asked for.

        That rebuild is the part `data_dir` cannot express. A merged build_scores
        that read data_dir and skipped the call would point build_panel at whatever
        symlinks happened to be on disk, and the index-exclusion guarantee would
        rest on luck rather than on a step that runs. So the universe carries how
        its directory comes into being, next to where it is.
        """
        return self.data_dir if self._prepare is None else self._prepare()

    def trading_days(self, index):
        """Restrict a price index to this universe's backtest window.

        ONLY THE DATE CUT IS LIVE. Every remaining universe cuts by DATE
        (config.BT_START_DATE..BT_END_DATE). The year-cut branch below is what the
        deleted 58 and 74 used (2019..2026 / 2019..2025, six trading days longer);
        no universe sets `year_range` any more, so it is currently unreachable.
        """
        if self.year_range is not None:
            y0, y1 = self.year_range
            return index[(index.year >= y0) & (index.year <= y1)]
        d0, d1 = self.date_range
        return index[(index >= d0) & (index <= d1)]


_MID = None
if config_mid is not None:
    _MID = Universe(
        tag="mid", label="MidCap150 (148 constituents)",
        data_dir=config_mid.CONSTITUENTS_DIR_MID,
        metrics_dir=config_mid.METRICS_DIR_MID,
        score_tmp=Path("/tmp/v_mid_expanding.csv"),
        score_cache=config_mid.METRICS_DIR_MID / "v_mid_expanding_cache.csv",
        raw_tmp=Path(f"/tmp/raw_panel_mid_{HORIZON}.csv"),
        raw_cache=config_mid.METRICS_DIR_MID / "raw_panel_mid_cache.csv",
        nautilus_scores="scores_mid.parquet",
        nautilus_end=str(config.BT_END_DATE.date()),
        purge_mode="trading",
        index_name=config_mid.INDEX_NAME_MID,
        index_file=config_mid.INDEX_FILE_MID,
        year_range=None, date_range=(config.BT_START_DATE, config.BT_END_DATE),
        _symbols=lambda: set(config_mid.SYMBOLS_MID),
        _prepare=config_mid.ensure_constituents_dir,
        # MEASURED. Eight results from the post density-fix panel. The inv-vol half
        # of the old blanket "validated" claim was FALSE as written, which is why
        # this is stated per test: a stale validation claim is worse than no claim.
        validation_status={
            "measured_on": "post density-fix panel, 2026-08-13, caches rebuilt",
            "breadth_T1_seed_robustness": ("FAIL 2 of 3 seed sets "
                                           "(+0.14, -0.02, +0.16); was PASS 3 of 3"),
            "breadth_T2_sub_period": "PASS both halves (+0.21, +0.36)",
            "inv_vol_T1_baseline_control": "PASS",
            "inv_vol_T2_seed_robustness": ("FAIL 0 of 3 seed sets "
                                           "(-0.05, -0.01, -0.10); was PASS 3 of 3"),
            "inv_vol_T3_sub_period": "FAIL both halves (-0.04, -0.10); was PASS",
            "inv_vol_T4_vol_window": ("FAIL 0 of 4 windows beat equal-rupee 1.06 "
                                      "(1.00/1.00/1.04/1.03); was PASS 4 of 4"),
        },
        # THE KEY ORDER IS THE ARTEFACT. json.dumps preserves insertion order, so
        # this tuple is what makes v2FINAL_params.json byte-identical across the
        # merge. mid has no "universe" and no "n_symbols"; n100 has both and lacks
        # "validated"/"rejected". Neither set is more correct -- they are what the
        # two engines happened to write, and unifying them is a separate change.
        engine_params_keys=(
            "model", "sizing", "exposure", "top_n", "buffer", "rebalance_days",
            "avg_exposure_pct", "sharpe", "maxdd_pct", "cagr_pct", "cash_yield",
            "survivorship", "vs_buyhold", "validated", "validation_status",
            "rejected"),
        engine_params_static={
            "validated": "see validation_status",
            "rejected": ["slope regime", "absolute gate", "vol-targeting",
                         "feature pruning", "100-share sizing"],
        },
        engine_text={
            "banner": "ENGINE v2 FINAL -- cross-sectional ranking + inverse-vol "
                      "+ breadth scaling",
            "panel_what": "MidCap150 score panel",
            "bh_label": "Equal-weight buy & hold (MidCap150)",
            "chart_title": ("FINAL v2 strategy: ranking + inverse-vol + "
                            "breadth-scaled exposure\n"
                            "Breadth cuts exposure in weak markets -> ~half the "
                            "drawdown, higher Sharpe\n"),
            "assert_index_absent": False,
        },
        chart_text={
            "stem": "chart_mid_FINAL",
            # THE INDEX WINDOW END IS A DATA BOUNDARY, not a market one: it is the
            # last date this universe's index file carries. mid and n100 differ.
            "index_window_end": "2026-06-08",
            "dpi": 140,
            "legend_fontsize": 8,
            "rule_width": 94,
            # mid's chart says the equal-weight line is NOT investable in the
            # legend itself; n100's says it only in the prose below the chart.
            # Both statements are true of both universes -- which is an argument
            # for unifying them, in a commit that declares the artefact change.
            "bh_not_investable": True,
            # THE IC / EXTREME-RETURN DIAGNOSTIC BLOCK, mid only. Console output,
            # no artefact, but it re-reads the score panel, so running it for n100
            # would be new work rather than new formatting.
            "diagnostics": True,
            # THE DRAWDOWN-PANEL LEGEND LABEL, and it reaches the PNG. The two
            # originals differed in three ways on ONE continuation line: the split
            # token ("[" vs "  ["), the word "max", and the precision (.0f vs .1f).
            # A keyword survey of render parameters missed it because the line it
            # sits on contains no render keyword -- the grep matched the ax[1].plot
            # call and never reached its argument. Checksum found it; grep did not.
            "dd_label": lambda lab, mn: f"{lab.split('[')[0].strip()} ({mn:.0f}%)",
            # THE CHART SUBTITLE REACHES THE PNG, and the two universes' subtitles
            # are different prose that reads different values -- mid's quotes the
            # panel-density figures that only its diagnostics block computes.
            # A CALLABLE, like _symbols and _prepare above, so make_chart.py stays
            # free of per-universe text. `v` is the values the step computed.
            "subtitle": lambda v: (
                f"MidCap150 panel density: {v['n_panel']} of {v['n_all']} names "
                f"scored, median {v['per_day_median']} priced per day.\n"
                f"MidCap150 universe ({v['n_all']} constituents, index excluded)  |  "
                f"v2 holds {v['inv']}% invested on average  |  ALL NUMBERS AFTER TC "
                f"(Zerodha + 0.15% slippage)\n"
                f"Benchmarks: {v['index_name']} is the published CAP-WEIGHTED index "
                f"(investable). Equal-weight buy&hold is the universe, and is NOT "
                f"investable.\n"
                f"SURVIVORSHIP: {v['n_late']} of {v['n_all']} names did not exist at "
                f"2019-01-01, and midcaps that left the index or delisted 2019-2026 "
                f"are absent from this file altogether.\n"
                f"Midcap churn far exceeds large-cap churn; the same bias measured "
                f"about 10 CAGR points on Nifty100. Do not read buy&hold as "
                f"achievable.\n"
                "LIQUIDITY AND MARKET-IMPACT FIGURES ARE NOT AVAILABLE FOR THIS "
                "WINDOW: the depth and participation studies were run on the old "
                "1,842-day window\n"
                "ending 2026-06-08 and have not been re-run. Every number here is a "
                "research backtest with a flat 0.15% slippage and no market-impact "
                "model.\n"),
        },
    )

_N100 = None
if config_n100 is not None:
    _N100 = Universe(
        tag="n100", label="Nifty 100 (99 constituents)",
        data_dir=config_n100.CONSTITUENTS_DIR_N100,
        metrics_dir=config_n100.METRICS_DIR_N100,
        score_tmp=Path("/tmp/v_n100_expanding.csv"),
        score_cache=config_n100.METRICS_DIR_N100 / "v_n100_expanding_cache.csv",
        raw_tmp=Path(f"/tmp/raw_panel_n100_{HORIZON}.csv"),
        raw_cache=config_n100.METRICS_DIR_N100 / "raw_panel_n100_cache.csv",
        nautilus_scores="scores_n100.parquet",
        nautilus_end=str(config.BT_END_DATE.date()),
        purge_mode="trading",
        index_name=config_n100.INDEX_NAME_N100,
        index_file=config_n100.INDEX_FILE_N100,
        year_range=None, date_range=(config.BT_START_DATE, config.BT_END_DATE),
        _symbols=lambda: set(config_n100.SYMBOLS_N100),
        _prepare=config_n100.ensure_constituents_dir,
        # NOT MEASURED, and a STRING rather than a dict so it cannot be mistaken
        # for mid's eight results. The seed-robustness and sub-period validations
        # on record were run elsewhere and are not claimed here.
        validation_status=("not measured on this universe. The seed-robustness "
                           "and sub-period validations on record were run on the "
                           "58 and the mid and are not claimed here."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty 100 (99 constituents, NIFTY100.csv excluded by name)",
        },
        engine_text={
            "banner": "ENGINE v2 FINAL -- Nifty 100 universe (99 names, index "
                      "excluded by name)",
            "panel_what": "Nifty 100 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 100, 99 names)",
            "chart_title": ("Nifty 100 universe -- ranking + inverse-vol + "
                            "breadth-scaled exposure\n"),
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_n100",
            "index_window_end": "2026-06-22",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "bh_not_investable": False,
            "diagnostics": False,
            "dd_label": lambda lab, mn: f"{lab.split('  [')[0]} (max {mn:.1f}%)",
            "subtitle": lambda v: (
                f"Nifty 100 universe ({v['n_all']} constituents, index excluded "
                f"by name)  |  v2 holds {v['inv']}% invested on average  |  ALL "
                f"NUMBERS AFTER TC (Zerodha + 0.15% slippage)\n"
                f"Benchmarks: NIFTY100 is the published CAP-WEIGHTED index "
                f"(investable, and NOT survivorship-biased). Equal-weight buy&hold "
                f"is the universe, and is NOT investable.\n"
                f"SURVIVORSHIP: these {v['n_all']} are TODAY'S index members "
                f"backfilled to 2019. Names dropped or delisted from the Nifty 100 "
                f"during the window are absent entirely,\nso both the strategy and "
                f"its equal-weight buy&hold are inflated. Do not read that buy&hold "
                f"as achievable.\n"
                "LIQUIDITY AND MARKET-IMPACT FIGURES ARE NOT AVAILABLE FOR THIS "
                "WINDOW: the depth and participation studies were run on the old "
                "1,842-day window\n"
                "ending 2026-06-08 and have not been re-run. Every number here is a "
                "research backtest with a flat 0.15% slippage and no market-impact "
                "model.\n"),
        },
    )

# ONLY THE UNIVERSES WHOSE CONFIG IS PRESENT. Declaration order is preserved, so
# a universe that is still here occupies the same position it always did -- LIVE's
# order is documented below as declaration order and callers rely on that.
REGISTRY = {u.tag: u for u in (_MID, _N100) if u is not None}

# The universes that ship. Eighteen of the nineteen hand-rolled registries carry
# exactly these two; only nt_run.py knows all four.
#
# ITS ORDER IS DECLARATION ORDER (mid, n100) AND IS NOT THE REPORTING ORDER. Every
# study script in this repository iterates n100 FIRST and accumulates a combined
# verdict in that sequence, so a caller whose OUTPUT depends on order must name
# the universes explicitly -- REGISTRY["n100"], REGISTRY["mid"] -- rather than
# iterate LIVE. Using LIVE for that swapped the two blocks of
# verify_v34_arms.py's report, which is how this note came to exist.
LIVE = list(REGISTRY.values())


# ---------------------------------------------------------------------------
# REPORTING ORDER -- the sequence a MULTI-UNIVERSE report puts universes in.
# ---------------------------------------------------------------------------
# THIS IS NOT REGISTRY ORDER AND MUST NOT BE. Registry order is declaration order
# (58, 74, mid, n100) and it is the right answer for selection, where the question
# is "which universes", a set. It is the WRONG answer for a report, where position
# is visible in a filename, a legend and a colour assignment.
#
# n100 BEFORE mid, because every study script in this repository iterates n100
# first -- the note on LIVE above says so -- and the published combined chart is
# chart_COMBINED_n100_mid.png. Sorting these two the other way would rename a
# figure that is already referenced in docs/README.md.
#
# LIVE BEFORE RETIRED, because the live pair is the project's current scope and a
# combined chart that leads with a retired universe misstates what is being
# reported. Within the retired pair, declaration order: 58 then 74.
#
# A TAG ABSENT FROM REGISTRY IS SIMPLY SKIPPED, so this stays correct as universes
# are removed. A registered tag absent from THIS tuple would be dropped silently
# from every combined report, which is why report_order() raises on one instead.
REPORT_ORDER = ("n100", "mid", "58", "74")


# ---------------------------------------------------------------------------
# WHAT THIS RUN SELECTED -- registration and selection are NOT the same thing.
# ---------------------------------------------------------------------------
# REGISTRY answers "which universes EXIST in this checkout". A run answers a
# narrower question: "which universes did the caller ASK FOR". Until now the two
# were conflated, because every multi-universe step gated on `"74" in REGISTRY`.
# That is correct for a REMOVED universe and wrong for an UNSELECTED one:
# `run.py --universe mid,58` would still put 74 on the fair-comparison chart,
# because 74 is registered even though nobody asked for it.
#
# A REPORT MUST NEVER SHOW A UNIVERSE THE CALLER DID NOT SELECT. So selection is
# recorded here, next to the registry, and the steps that build multi-universe
# output ask `selected_tags()` instead of `REGISTRY`.
#
# THE DEFAULT IS EVERY REGISTERED UNIVERSE, which is exactly what those steps saw
# before this existed. So a step run on its own -- `python results/<step>.py`, a
# test, an import from a notebook -- behaves as it always did, and a full
# `--universe all` run is unchanged. Verified byte-identical on all 281 artefacts.
_SELECTED = None


def set_selection(tags):
    """Record which universes this run selected. Called once by run.py.

    Unknown tags raise: silently narrowing a selection to nothing is how a run
    produces no output and reports success. Passing None restores the default.
    """
    global _SELECTED
    if tags is None:
        _SELECTED = None
        return
    want = [t.tag if hasattr(t, "tag") else t for t in tags]
    unknown = [t for t in want if t not in REGISTRY]
    if unknown:
        raise KeyError(f"cannot select unregistered universe(s) {', '.join(unknown)}; "
                       f"registered: {', '.join(REGISTRY)}")
    _SELECTED = [t for t in REGISTRY if t in set(want)]


def selected_tags():
    """The tags this run is working on, in REGISTRY order.

    Defaults to every registered universe when nothing has set a selection.
    Intersected with REGISTRY on every call, so a universe removed after the
    selection was set cannot come back through this door.
    """
    if _SELECTED is None:
        return list(REGISTRY)
    return [t for t in _SELECTED if t in REGISTRY]


def selected():
    """selected_tags() as Universe objects."""
    return [REGISTRY[t] for t in selected_tags()]


def report_order(tags):
    """`tags` in REPORT_ORDER sequence. Accepts any iterable of tags or Universes.

    Raises on a registered tag this tuple does not name, rather than dropping it:
    a new universe added to REGISTRY and forgotten here would otherwise vanish from
    every multi-universe chart with no error, which is the failure mode the whole
    registry exists to prevent.
    """
    want = [t.tag if hasattr(t, "tag") else t for t in tags]
    missing = [t for t in want if t not in REPORT_ORDER]
    if missing:
        raise KeyError(
            f"universes/registry.REPORT_ORDER does not name {', '.join(missing)}. "
            "Every registered universe must have a position there, or it would be "
            "dropped from combined reports without an error. Add it.")
    seen = set(want)
    return [t for t in REPORT_ORDER if t in seen]


def get(tag):
    """One universe by tag, with a message that lists the alternatives."""
    try:
        return REGISTRY[tag]
    except KeyError:
        raise KeyError(
            f"unknown universe {tag!r}; known: {', '.join(sorted(REGISTRY))}") from None


def from_argv(argv, default=None):
    """Read --universe=<tag> from a command line.

    Reproduces what nt_run.py, nt_verify.py, shuffle_test.py and validate_topn.py
    each do by hand, including the convention that no flag means "every live
    universe" rather than an error.
    """
    picked = [t for t in REGISTRY if f"--universe={t}" in argv]
    if picked:
        return [REGISTRY[t] for t in picked]
    return [REGISTRY[default]] if default else list(LIVE)
