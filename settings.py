"""
settings.py -- constants, directories, artefact paths and names, every run
setting, and the universe registry.

Sections, in the order they are defined:
  1. constants and directories   the backtest window, selection sizes, data dirs
  2. artefact paths              where each artefact is written
  3. run settings                one object per setting: cadence, profile_axis,
                                 tax, survivorship_axis, dd_axis, capital_axis,
                                 impact_axis, pcap_axis, fixed_axis, start_axis,
                                 shortfall_axis
  4. universe registry           Universe, REGISTRY, use_pit, universe_axis
  5. artefact naming             AXES, tail, name, path_tail, CARRIES

Each run setting is one object with set_selection(), selected(), is_default(),
suffix(), segment() and label(). run.py calls set_selection() once per run and
everything else reads the selection. The participation cap rules stay in
profiles.py and the buy-trim rule in buy_shortfall.py; reading files and the
score-cache keys stay in config.py.
"""
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

# Imported at module level because BT_START_DATE / BT_END_DATE below are
# Timestamps and are needed at import time.
import pandas as _pd


# ===========================================================================
# 1. CONSTANTS AND DIRECTORIES
# ===========================================================================
# ---------------------------------------------------------------------------
# Project root -- every path below is relative to this
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Symbols used by this project
# ---------------------------------------------------------------------------
SYMBOLS = [
    "HDFCBANK",
    "BRITANNIA",
    "ABB",
    "BAJFINANCE",
    "BOSCHLTD",
]

# Benchmark index for equity curve comparison
BENCHMARK_SYMBOL = "NIFTY50"

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"            # the cleaned source CSVs go here
PROCESSED_DATA_DIR = DATA_DIR / "processed"  # causal feature-engineered data is built here

# ---------------------------------------------------------------------------
# Model artifact paths
# ---------------------------------------------------------------------------
MODELS_DIR = PROJECT_ROOT / "models"
DT_MODELS_DIR = MODELS_DIR / "decision_tree"
GRU_MODELS_DIR = MODELS_DIR / "attention_gru"
TD3_MODELS_DIR = MODELS_DIR / "td3"

# ---------------------------------------------------------------------------
# Nautilus paths
# ---------------------------------------------------------------------------
NAUTILUS_DIR = PROJECT_ROOT / "nautilus"
CATALOG_DIR = NAUTILUS_DIR / "catalog"

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
RESULTS_DIR = PROJECT_ROOT / "results"
EQUITY_CURVES_DIR = RESULTS_DIR / "equity_curves"
METRICS_DIR = RESULTS_DIR / "metrics"

# CREATE THE OUTPUT DIRECTORIES AT IMPORT, so a FRESH CHECKOUT works from ANY
# entry point -- run_all.py or a script run standalone -- rather than only when
# these directories happen to survive from a previous run on this machine.
# The per-universe config modules (since folded into the universe registry) did
# this for their own metrics dirs; config.py did NOT, so STEP 2 (engine_core) crashed on the first
# to_csv into a non-existent results/metrics on the first fresh run ever
# attempted (2026-09-03). See KNOWN_ISSUES.md.
METRICS_DIR.mkdir(parents=True, exist_ok=True)
EQUITY_CURVES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# BACKTEST WINDOW -- the single definition. Every live site imports these.
# ---------------------------------------------------------------------------
# Inclusive on both ends. Price data runs to 2026-06-08, so this cut is real and
# drops six trading days: 2026-06-01 through 2026-06-08.
#
# THE NAMES CARRY _DATE AND ARE Timestamps: engine_core once defined BT_START and
# BT_END as year integers, and two constants with one name and two types is how a
# previous mismatch happened.
#
# THE START IS ONE SETTING SINCE 2026-10-22. BT_START_DEFAULT is the default and
# BT_START_DATE the value in force; run.py --start changes it through
# start_axis.set_selection, which also moves every registry row's window. Read
# BT_START_DATE at call time, never copy it at import. engine_core's integer
# year pair, which topn_test.py read, was removed the same day.
BT_START_DEFAULT = _pd.Timestamp("2019-01-01")
BT_START_DATE = BT_START_DEFAULT
BT_END_DATE = _pd.Timestamp("2026-05-29")

# ---------------------------------------------------------------------------
# SELECTION -- the single definition. Every live site imports these.
# ---------------------------------------------------------------------------
# TOP_N   how many names the buy set holds at each rebalance.
# BUFFER  the hold band: a held name is sold only when its rank falls below
#         this, so turnover does not rise with tighter selection.
#
# Centralised 2026-08-29 under experiments/TOPN_SPEC.txt Part A. Before that
# they were literals in TEN places with no single definition, and one of those
# ten had drifted: results/make_stats_both.py carried 12, 24 (that script was
# deleted 2026-09-04 -- dead outputs, drifted constants). Nothing could have
# caught it, because there was nothing for it to disagree with.
#
# THE RETIRED ENGINES DO NOT IMPORT THESE. engine_core.py, engine_v2_final.py,
# engine_v2_final74.py and make_cash_series.py (now in frozen/) keep their own
# literals so the retired universes' published numbers cannot move -- the same freeze
# the old year window carries. engine_core.py:90 therefore still defines TOP_N
# and BUFFER, and validate_sizing.py imports TOP_N from THERE, not from here.
# The two agree at 8 today and nothing enforces that. See KNOWN_ISSUES.md.
#
# No _DATE-style suffix is used. The window constants needed one because
# engine_core's BT_START/BT_END are year INTEGERS and a same-name/different-type
# collision had already caused a mismatch. Here both definitions are int 8 and
# int 16, so there is no type trap -- only the divergence risk noted above.
TOP_N = 8
BUFFER = 16

# A buy that cash cannot fully pay for: "trim" cuts it to the largest whole
# quantity that fits, if that is at least half the wanted quantity
# (buy_shortfall.MIN_FILL_PCT), "refuse" drops it. run.py --buy-shortfall overrides it for
# one run through shortfall_axis (section 3). The rule is buy_shortfall.py.
BUY_SHORTFALL = "trim"

# ---------------------------------------------------------------------------
# Train / Validation / Test split -- DELETED 2026-08-28
# ---------------------------------------------------------------------------
# TRAIN_START, TRAIN_END, VAL_START, VAL_END, TEST_START and TEST_END all had
# ZERO references anywhere in the repository, verified by raw grep rather than by
# a filtered count. They were placeholders from the earlier decision-tree / GRU /
# TD3 phase and described a split no current script uses.
#
# They were also inconsistent with the window that IS used: TEST_END read
# 2026-06-05, which matches neither the old year cut (to 2026-06-08) nor
# BT_END_DATE (2026-05-29). A dead date constant that disagrees with the live one
# is a trap for the next reader.
#
# The backtest window is BT_START_DATE / BT_END_DATE above, and the walk-forward
# split is not date constants at all -- it is the expanding monthly retrain with
# the trading-session purge of engine_core.training_set.

# ---------------------------------------------------------------------------
# Feature engineering window settings (CAUSAL ONLY -- only past data is used)
# ---------------------------------------------------------------------------
LOOKBACK_WINDOW = 20   # how many past days of context the model sees (legacy GRU/TD3)
RANDOM_SEED = 42

BUY_TC = 0.001187
SELL_TC = 0.001037
STCG_RATE = 0.22
LTCG_RATE = 0.125
LTCG_EXEMPT = 125000
MIN_HOLD_DAYS = 15
RETRAIN_FREQ = "monthly"

DT_MAX_DEPTH = 6
DT_MIN_SAMPLES_LEAF = 100
DT_CCP_ALPHA = 1e-3
GRU_HIDDEN = 64
GRU_LAYERS = 1
GRU_LOOKBACK = 30
TD3_GAMMA = 0.98
TD3_POLICY_DELAY = 2
TD3_TARGET_NOISE = 0.2
TD3_NOISE_CLIP = 0.5


# ===========================================================================
# 2. ARTEFACT PATHS
# ===========================================================================
# Where every artefact goes, derived once.
#
# WHAT THIS IS FOR
#     Output paths are currently written as literals at the point of use: a script
#     imports its universe's config module, binds its metrics directory to `M`,
#     and then writes `M / "v34_comparison.csv"`. That works, and it is why the
#     universes do not collide today -- the universe is in the DIRECTORY. But it
#     means the layout is not stated anywhere; it is implied by ninety-odd write
#     calls spread across the repository.
#
#     This module states it. Every function here returns the path that is ALREADY
#     produced today. It is a description, not a redesign.
#
# WHAT IT DOES NOT DO YET, DELIBERATELY
#     The survey proposed `runs/{universe}/{arm}/` so that two arms cannot overwrite
#     each other -- the collision that makes verify_v34_arms leave only the last
#     arm's Nautilus reports on disk. That change MOVES artefacts, so it is not part
#     of building the definition. `run_dir()` below records the proposed layout and
#     is not called by anything; adopting it is a separate, verifiable step.
#
#     Until then `metrics()` is the real answer and carries no arm, exactly as the
#     repository behaves now.

ROOT = PROJECT_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DIAGNOSTICS_DIR = ROOT / "diagnostics"


# ------------------------------------------------------------ listing a folder
# EVERY DIRECTORY LISTING IN THE REPOSITORY GOES THROUGH list_dir().
#
# On macOS, a file written to an exFAT or FAT drive gets a "._<name>" twin
# holding its extended attributes, and macOS attaches com.apple.provenance to
# every new file, so this cannot be prevented from Python. With the project on
# such a drive, the constituents farms built during a run held ._360ONE.csv
# beside 360ONE.csv, a bare glob("*.csv") counted the twin as a symbol, and
# prepare_data_dir() failed with "constituents directory does not match
# symbol_list" -- for a different universe on each run, since each run makes
# new twins. .DS_Store is Finder's equivalent on any drive.
#
# This module imports nothing from the repository at import time, so the
# registry and config can use list_dir() while they are themselves loading.
def is_os_metadata(name):
    """True for a macOS metadata file: an AppleDouble "._" twin or .DS_Store."""
    return name.startswith("._") or name == ".DS_Store"


def list_dir(directory, pattern="*", recursive=False):
    """Entries of `directory` matching `pattern`, sorted, without macOS metadata.

    glob(pattern), or rglob(pattern) when recursive. Files and directories are
    both returned; callers that want one kind filter with is_file()/is_dir(). An
    entry is dropped if any part of its path below `directory` is metadata. A
    missing directory yields [], as Path.glob does.
    """
    d = Path(directory)
    found = d.rglob(pattern) if recursive else d.glob(pattern)
    return sorted(p for p in found
                  if not any(is_os_metadata(x) for x in p.relative_to(d).parts))


# --------------------------------------------------------------- score panels
def score_cache(u):
    """The score panel, cache/<tag>/v_<tag>_expanding.csv. Written by build_scores."""
    return u.score_cache


def raw_cache(u):
    return u.raw_cache


# ------------------------------------------------------------------- outputs
def metrics(u):
    """The universe's artefact directory. THE UNIVERSE IS IN THE PATH; the arm is
    not, which is why all four arms share one v34_comparison.csv."""
    return u.metrics_dir


def artefact(u, name):
    """One named artefact for a universe, e.g. artefact(midcap150, 'v34_comparison.csv')."""
    return u.metrics_dir / name


def tagged_artefact(u, stem, ext="csv"):
    """The daily-audit family, which puts the tag in the FILENAME as well as the
    directory -- daily_holdings_midcap150.csv and so on. Belt and braces, and the only
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
    """A findings file. Some are per-universe (topn_midcap150.txt), some are combined
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
# four literal paths, two of which (the metrics dirs of two retired universes,
# deleted 2026-09-11) outlived the universes that wrote into them -- a run folder
# would still have gone looking for artefacts nothing could produce. A new
# universe's metrics dir is now collected the moment it is registered.
#
# results/metrics IS STILL LISTED, but no longer as any universe's output: it is
# the shared, non-universe artefact directory (stability_*, feature docs). See
# engine_core.refuse_universe_artefact().
#
# A FUNCTION, NOT A CONSTANT COMPUTED AT IMPORT. Computing it at import made this
# module import the registry, so the registry could not import this module.
def artefact_dirs():
    per_universe = tuple(
        str(u.metrics_dir.relative_to(ROOT)) for u in REGISTRY.values())
    return per_universe + ("results/metrics", "runs",
                           "nautilus/reports", "nautilus/data")



def run_folder_name(uni_tags, arm_names, rebal, when=None):
    """`20260906T1432_all_all_r20` -- one folder per invocation, named for it.

    THE NAME SAYS WHAT THE RUN WAS, not just when it happened. A timestamp alone
    sorts correctly and tells you nothing; the selection is what you actually
    search for six weeks later. "all" is used where an axis is fully selected,
    because midcap150-nifty100-nifty50-midcap50_v1-v2-v3-v4 is not more informative
    than "all", only longer.

    The cadence is always spelled, including the default, so that a folder name is
    never ambiguous about which cadence produced it -- unlike the ARTEFACT names,
    where an unsuffixed file must keep meaning the published default.
    """
    import datetime
    ts = (when or datetime.datetime.now()).strftime("%Y%m%dT%H%M%S")
    u = "all" if len(uni_tags) >= 4 else "-".join(uni_tags)
    # "all" only for exactly the core four; any selection with a stop arm in it,
    # or a core subset, is spelled out.
    from arms.registry import ARMS as _CORE
    a = "all" if set(arm_names) == set(_CORE) else "-".join(arm_names)
    return f"{ts}_{u or 'none'}_{a or 'none'}_r{int(rebal)}"


def run_dir(u, arm=None, rebal=None):
    """runs/{universe}/{arm}/ -- and {arm}@r{n} for a non-default cadence.

    THE CADENCE BELONGS IN THE PATH, AND ITS ABSENCE WAS A BUG. `--rebal 40`
    wrote its results straight into runs/midcap150/v1/, replacing the published
    cadence-20 artefacts with cadence-40 ones. params.json recorded `rebal: 40`,
    so the FILE said what it was while the PATH said something else -- and the
    next reader of runs/midcap150/v1/comparison.csv had no way to know. Verified by
    checksum before this change: one `--rebal 40` run changed that file.

    THE DEFAULT CADENCE IS UNSUFFIXED, so runs/midcap150/v1/ keeps meaning exactly what
    it has always meant and every published artefact under runs/ is untouched.
    Only a non-default cadence gets a name of its own: runs/midcap150/v1@r40/.

    "@" RATHER THAN "_" separates the two axes visually and cannot collide with an
    arm name: arm names are v1..v4 and never contain "@", so runs/midcap150/v1@r40 can
    only ever parse one way.
    """
    # THE PROFILE AND TAX AXES JOIN THE PATH, 2026-09-23, from path_tail,
    # the rule nautilus/reports already used. Until then a `--tax on` or
    # `--profile tradeable` arm run wrote into runs/<u>/<arm>/ over the research
    # run's chart.
    d = ROOT / "runs" / u.tag
    if arm is None:
        return d
    return d / (arm.name + path_tail(rebal))


# ===========================================================================
# 3. RUN SETTINGS
# ===========================================================================
# One object per setting, named as the module it replaces (cadence, tax,
# capital_axis, ...), so `from settings import cadence` replaces `import cadence`
# and every call site reads as before. run.py calls set_selection() once per
# run; everything else reads selected(). At the default, suffix() and segment()
# return "", so a default run writes the canonical published names, and each
# non-default setting appends its own code in naming order (AXES, section 5).
#
# The shared methods live once on _Axis. A setting overrides one only where its
# rule differs from the shared one.


class _Axis:
    """One run setting. DEFAULT is the value when nothing was selected."""
    DEFAULT = None
    _SELECTED = None

    def selected(self):
        return self.DEFAULT if self._SELECTED is None else self._SELECTED

    def is_default(self):
        return self.selected() == self.DEFAULT

    def _code(self):
        raise NotImplementedError

    def suffix(self):
        """"" at the default, else "_" + the setting's code -- the artefact name tail."""
        return "" if self.is_default() else "_" + self._code()

    def segment(self):
        """"" at the default, else "@" + the setting's code -- the directory segment tail."""
        return "" if self.is_default() else "@" + self._code()

    def label(self):
        """The chart-title fragment, "" at the default."""
        return ""


# --- cadence ---------------------------------------------------------------
# The rebalance cadence in trading days. Recorded here and handed to
# backtest_exposure(..., rebal=n) as an argument, never written into
# test_exposure as a module global: a global set by one in-process step leaks
# into the next (rebal_cadence_sweep.py once set test_exposure.REBAL and never
# restored it). The default is 20, which every engine's REBAL already was, so a
# default run passes rebal=20 and resolves to the same value. The suffix is "" at
# 20 and "_r40" otherwise. run.py refuses a non-default cadence for the retired
# universes (deleted 2026-09-11), whose engines and port were pinned to 20.
class _Cadence(_Axis):
    DEFAULT = 20

    def set_selection(self, n):
        """Record this run's cadence. Called once by run.py. None restores the default."""
        if n is None:
            self._SELECTED = None
            return
        n = int(n)
        if n < 1:
            raise ValueError(f"rebalance cadence must be >= 1 trading day, got {n}")
        self._SELECTED = n

    def _code(self):
        return f"r{self.selected()}"


cadence = _Cadence()


# --- profile ---------------------------------------------------------------
# The execution-realism profile: research (no participation cap, the default)
# or tradeable (cap 1.00 of prior-20-session median volume). The suffix is "" for
# research and "_tradeable" otherwise. What the cap does, and every function
# that reads it, is in profiles.py.
class _Profile(_Axis):
    PROFILES = {
        "research":  {"participation_cap": None},
        "tradeable": {"participation_cap": 1.00},
    }
    DEFAULT = "research"

    def set_selection(self, name):
        """Record this run's profile. Called once by run.py. None restores the default."""
        if name is None:
            self._SELECTED = None
            return
        if name not in self.PROFILES:
            raise ValueError(f"unknown profile {name!r}; known: {', '.join(self.PROFILES)}")
        self._SELECTED = name

    def _code(self):
        return self.selected()


profile_axis = _Profile()


# --- tax -------------------------------------------------------------------
# Whether a run charges capital-gains tax. The selection only: the rates,
# exemption and financial-year rules are in results/tax_util.py. Default off,
# and off is unsuffixed, so every path a tax-off run composes is the path it
# composed before the axis existed; "_tax" when on. Because an omitted axis and a
# default axis give the same string, only naming_declare_check.py's declarations
# reveal a writer that forgot the axis.
#
# One selection per run. run.py passes a bool; the None branch is for callers
# that restore the default (tax_acceptance_check.py, check_all's selection
# save and restore).
class TaxAxisError(Exception):
    """The tax selection is not a single value across this run."""


class _Tax(_Axis):
    DEFAULT = False
    TaxAxisError = TaxAxisError

    def set_selection(self, on):
        """Record this run's tax selection. None restores the default."""
        if on is None:
            self._SELECTED = None
            return
        if not isinstance(on, bool):
            raise TypeError(f"tax selection must be a bool, got {on!r}")
        self._SELECTED = on

    def _code(self):
        return "tax"

    def is_uniform_over_plan(self, plan):
        """True when this axis has one value across every invocation in `plan`.

        A `tax:` qualifier in run_all.PIPELINE_ORDER is evaluated against the
        run, which is correct only while the selection cannot vary within a run.
        Nothing can vary it today, so this returns True. It is the place that
        fails first if a per-invocation tax selection is ever added.
        """
        del plan          # no per-invocation tax state exists to disagree with
        return True


tax = _Tax()


# --- survivorship ----------------------------------------------------------
# Which universe construction a run uses:
#     static   today's index members backfilled to the window start, priced from
#              data/raw/Final_Without_Survivorship_Data. Every published figure.
#     pit      point-in-time membership from data/raw/Survivorship_Bias, priced
#              from data/raw/Final_With_Survivorship_Data, which also holds
#              dropped names.
# The selection itself is results/survivorship.py's SURVIVORSHIP_MODE, which the
# engine reads; this object sets and reads it and holds no copy. "_pit" goes
# after the tax suffix ("v34_equity_tax_pit.csv"), "@pit" after "@tax".
class _Survivorship(_Axis):
    DEFAULT = "static"
    CHOICES = ("static", "pit")

    @staticmethod
    def _sv():
        _res = str(PROJECT_ROOT / "results")
        if _res not in sys.path:
            sys.path.insert(0, _res)
        import survivorship
        return survivorship

    def set_selection(self, mode):
        """Record this run's selection. None restores the default."""
        self._sv().set_mode(self.DEFAULT if mode is None else mode)

    def selected(self):
        return self._sv().SURVIVORSHIP_MODE

    def _code(self):
        return "pit"


survivorship_axis = _Survivorship()


# --- drawdown limit --------------------------------------------------------
# When on, the engine scales every arm's book with the cushion rule of
# results/drawdown_overlay.py:
#
#     E = max(F, min(1, m * (W - (1 - L) * M) / W))
#
# W is the close equity, M its all-time peak since the start of the run (never
# reset), L the limit, m the multiplier (default 1 / L, fully invested at a
# peak) and F the exposure floor (default 25%), which keeps part of the book
# invested so the portfolio can recover. The suffix is "" when off and "_dd20"
# after "_pit" when on ("_dd20m3f10" when m or the floor is not the default).
# Exploratory: no result with the axis on has been validated. See README.
class _DrawdownLimit(_Axis):
    DEFAULT_FLOOR = 0.25      # 25 percent of the portfolio stays invested at most drawdowns
    BAND = 0.05               # no trade unless the invested fraction moves more than 5 points
    MAX_LIMIT = 0.50

    def make(self, limit_pct, m=None, floor_pct=None):
        """A DDLimit from command-line units: L and F in percent, m as a number."""
        L = float(limit_pct) / 100.0
        if not (0.0 < L <= self.MAX_LIMIT):
            raise ValueError(f"drawdown limit must be above 0 and at most {self.MAX_LIMIT:.0%}, "
                             f"got {limit_pct}")
        mm = 1.0 / L if m is None else float(m)
        if not mm > 0:
            raise ValueError(f"--dd-m must be above 0, got {m}")
        F = self.DEFAULT_FLOOR if floor_pct is None else float(floor_pct) / 100.0
        if not (0.0 < F <= 1.0):
            raise ValueError(f"--dd-floor must be above 0 and at most 100, got {floor_pct}")
        return DDLimit(L, mm, F)

    def set_selection(self, sel):
        """Record this run's selection: a DDLimit, or None for off. Called once by run.py."""
        if sel is not None and not isinstance(sel, DDLimit):
            raise TypeError(f"dd_axis.set_selection takes a DDLimit or None, got {sel!r}")
        self._SELECTED = sel

    def is_default(self):
        return self._SELECTED is None

    @staticmethod
    def _num(x):
        """12.5 -> "12p5", 20.0 -> "20": a number safe in a file name."""
        s = f"{x:.4g}"
        return s.replace(".", "p")

    def _code(self):
        s = self._SELECTED
        out = f"dd{self._num(s.limit * 100)}"
        if not s.m_is_default:
            out += f"m{self._num(s.m)}"
        if not s.floor_is_default:
            out += f"f{self._num(s.floor * 100)}"
        return out

    def label(self):
        if self.is_default():
            return ""
        s = self._SELECTED
        return (f"dd limit {s.limit * 100:g}% (m {s.m:.3g}, floor {s.floor * 100:g}%)")

    def params(self):
        """The params.json entry when on. Callers add the key only when the axis is on,
        so a run with the axis off writes the file it always wrote."""
        s = self._SELECTED
        return {"limit_pct": round(s.limit * 100, 6), "m": round(s.m, 6),
                "m_is_default": s.m_is_default, "floor_pct": round(s.floor * 100, 6),
                "band_pct": round(s.band * 100, 6), "check": "daily, at the close",
                "trades": "next open, proportional across holdings",
                "status": "exploratory, not validated"}

    @staticmethod
    def peak_warning(sel):
        """The warning line when m < 1/L, or None."""
        if sel.m < 1.0 / sel.limit - 1e-12:
            return (f"WARNING: --dd-m {sel.m:g} is below 1/L = {1.0 / sel.limit:g}: the portfolio "
                    f"will not be fully invested at a peak (exposure at a peak is "
                    f"{min(1.0, sel.m * sel.limit):.0%})")
        return None


@dataclass(frozen=True)
class DDLimit:
    """The selected drawdown limit, all as fractions of the portfolio."""
    limit: float           # L
    m: float               # cushion multiplier
    floor: float           # F
    band: float = _DrawdownLimit.BAND

    @property
    def m_is_default(self):
        return abs(self.m - 1.0 / self.limit) < 1e-12

    @property
    def floor_is_default(self):
        return abs(self.floor - _DrawdownLimit.DEFAULT_FLOOR) < 1e-12


_DrawdownLimit.DDLimit = DDLimit
dd_axis = _DrawdownLimit()


# --- starting capital ------------------------------------------------------
# DEFAULT is the starting capital of every published run, Rs 10,00,000. Every
# START_CAPITAL name in the engines is this value, and every code path a run
# takes reads selected(), so --capital reaches the engine, the buy & hold, the
# cost report, the daily log and the Nautilus port alike. "_cap5000000" (whole
# rupees) after the dd suffix, "@cap5000000" in directory segments.
class _Capital(_Axis):
    DEFAULT = 1_000_000
    MINIMUM = 100_000          # Rs 1 lakh

    def set_selection(self, rupees):
        """Record this run's capital. None restores the default. Called once by run.py."""
        if rupees is None:
            self._SELECTED = None
            return
        if int(rupees) != rupees or int(rupees) < self.MINIMUM:
            raise ValueError(f"starting capital must be a whole number of rupees, at least "
                             f"{self.MINIMUM:,}; got {rupees!r}")
        self._SELECTED = int(rupees)

    def _code(self):
        return f"cap{self.selected()}"

    def label(self):
        return "" if self.is_default() else f"capital Rs {self.selected():,}"

    def refusal(self, profile, impact_given):
        """Why run.py refuses this capital, or None.

        A capital other than DEFAULT is refused under the research profile, which has
        no participation cap and no market impact and so gives the same return at any
        size, and under the tradeable profile unless --impact is given, 0 included.
        The values listed are results/impact_sweep.py's K_VALUES."""
        if self.is_default():
            return None
        if profile == "research":
            return (f"--capital {self.selected():,} needs --profile tradeable: the research profile "
                    f"ignores capital size (it has no participation cap and no market impact, so "
                    f"every capital gives the same return). Use --profile tradeable with "
                    f"--impact K.")
        if not impact_given:
            return (f"--capital {self.selected():,} needs an explicit --impact K under the tradeable "
                    f"profile: no impact coefficient is assumed. Give --impact 0 for no market "
                    f"impact, or one of the values results/impact_sweep.py measures: "
                    f"{', '.join(f'{k:g}' for k in self.sweep_k_values())}.")
        return None

    @staticmethod
    def sweep_k_values():
        """results/impact_sweep.py's K_VALUES, read from its source without importing it
        (it imports the engine)."""
        import ast
        src = (PROJECT_ROOT / "results" / "impact_sweep.py").read_text()
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "K_VALUES"
                                                     for t in node.targets):
                return tuple(ast.literal_eval(node.value))
        raise RuntimeError("results/impact_sweep.py defines no K_VALUES")


capital_axis = _Capital()


# --- market impact ---------------------------------------------------------
# k is the coefficient of slippage.impact, the square-root model
#     impact = k * sqrt(order shares / prior-20-session median volume)
# added to the flat SLIPPAGE on every buy and every sell. k = 0 is the default
# and means the model is not run: backtest_exposure gets impact_k=None, the path
# every published run takes. The model needs the prior-20-session median volume,
# which only the tradeable profile loads, so a non-zero k under research is
# refused (check_profile). "_impact0p003" after the capital suffix.
class _Impact(_Axis):
    DEFAULT = 0.0

    def set_selection(self, k):
        """Record this run's k. None or 0 restores the default. Called once by run.py."""
        if k is None or float(k) == 0.0:
            self._SELECTED = None
            return
        k = float(k)
        if not k > 0:
            raise ValueError(f"impact k must be zero or positive; got {k!r}")
        self._SELECTED = k

    def is_default(self):
        return self._SELECTED is None

    def impact_k(self):
        """What backtest_exposure takes: None at the default, so the model never runs."""
        return None if self.is_default() else self._SELECTED

    def _code(self):
        return f"impact{self._SELECTED:g}".replace(".", "p")

    def label(self):
        return "" if self.is_default() else f"impact k {self._SELECTED:g}"

    def check_profile(self):
        """Refuse a non-zero k under the research profile. Called by run.py."""
        if not self.is_default() and profile_axis.is_default():
            raise ValueError(
                f"--impact {self._SELECTED:g} needs the tradeable profile: the impact model "
                f"sizes each fill against the prior-20-session median volume, which the "
                f"research profile does not load. Add --profile tradeable, or drop --impact.")


impact_axis = _Impact()


# --- participation cap -----------------------------------------------------
# --cap replaces the tradeable profile's participation cap (a fraction of the
# symbol's prior-20-session median volume, applied to buys and sells) for one
# run; profiles.participation_cap() returns it. Under research there is no cap
# and no volume to apply one to, so any --cap is refused (check_profile). The
# suffix is "" when the cap is the profile's own, including --cap 1.0 under
# tradeable; otherwise "_pcap0p1". "pcap", because "_cap" is the capital's.
class _ParticipationCap(_Axis):

    def set_selection(self, cap):
        """Record this run's cap. None restores the profile's. Called once by run.py."""
        if cap is None:
            self._SELECTED = None
            return
        cap = float(cap)
        if not cap > 0:
            raise ValueError(f"participation cap must be positive; got {cap!r}")
        self._SELECTED = cap

    @staticmethod
    def _profile_cap():
        return profile_axis.PROFILES[profile_axis.selected()]["participation_cap"]

    def is_default(self):
        return self._SELECTED is None or self._SELECTED == self._profile_cap()

    def _code(self):
        return f"pcap{self._SELECTED:g}".replace(".", "p")

    def label(self):
        return "" if self.is_default() else f"participation cap {self._SELECTED:g}"

    def check_profile(self):
        """Refuse any --cap under the research profile. Called by run.py."""
        if self._SELECTED is not None and profile_axis.is_default():
            raise ValueError(
                f"--cap {self._SELECTED:g} needs the tradeable profile: the research profile "
                f"has no participation cap and loads no volume to apply one to. Add "
                f"--profile tradeable, or drop --cap.")


pcap_axis = _ParticipationCap()


# --- fixed capital ---------------------------------------------------------
# Off (the default) is the compounded run every published figure comes from:
# each rebalance sizes its buys from the whole portfolio, profits included.
# On (--fixed-capital) is the non-compounded run ("don't reinvest"). The buys
# are sized from the decision close; at the rebalance open, after the morning's
# sells and any tax taken that morning (results/test_exposure.py):
#
#     book       = min(base, value at the decision close)    base is --capital
#     reserve    = max(0, value at this open - base)          never spent
#     invest_val = book * exposure * 0.98
#     the cash tests read spendable = cash - reserve
#
# So purchases never lift invested value above min(base, value at the fill
# open). Below the base the book is the equity, so losses are not topped up.
# Held names are never trimmed: a winner can carry invested value above the
# book, and only new purchases are held inside it. The idle reserve earns
# test_exposure.CASH_YIELD, which is 0. Refused with --dd and with the stop arms
# v5 and v6, which act on the running peak of compounded equity. Only
# backtest_exposure has the mode; engine_core.backtest and the Nautilus port do
# not. "_fixed" after the pcap suffix.
class _Fixed(_Axis):
    DEFAULT = False
    _SELECTED = False
    REFUSAL = ("--fixed-capital cannot run with {what}: {why} The fixed-capital book is "
               "min(base, equity), and the two rules would act on one account with two "
               "different ideas of its size. Drop one of the two.")

    def set_selection(self, on):
        """Record whether this run is fixed-capital. None or False restores the default."""
        if on is None:
            self._SELECTED = False
            return
        if not isinstance(on, bool):
            raise ValueError(f"fixed capital is on or off (a bool); got {on!r}")
        self._SELECTED = on

    def _code(self):
        return "fixed"

    def label(self):
        return "fixed capital, profits not reinvested" if self._SELECTED else ""

    def refusal(self, dd=False, stop_arms=()):
        """The message run.py prints when the flag meets --dd or a stop arm, or None."""
        if dd:
            return self.REFUSAL.format(
                what="--dd", why="the drawdown limit sizes the book from the running peak "
                                 "of compounded equity.")
        if stop_arms:
            return self.REFUSAL.format(
                what=f"the stop arm(s) {', '.join(stop_arms)}",
                why="the drawdown stop exits on a fall from the running peak of "
                    "compounded equity.")
        return None


fixed_axis = _Fixed()


# --- backtest start --------------------------------------------------------
# BT_START_DATE (section 1) is the one setting; set_selection changes it and
# moves every static registry row whose window starts at the current setting.
# Call it before use_pit: a pit row's start is the later of this and its first
# membership row, taken when the pit variant is made. Code that means "the
# backtest start" reads settings.BT_START_DATE at call time.
#
# The scoring floor follows the start: engine_core.score_floor() is the first
# day of the month SCORE_LEAD_YEARS before it, 2016-01-01 for the default start,
# which is the `year >= 2016` the scoring loop used until 2026-10-22. "_s20070924"
# after the fixed suffix.
class _Start(_Axis):
    DEFAULT = BT_START_DEFAULT
    SCORE_LEAD_YEARS = 3

    def set_selection(self, start):
        """Record this run's backtest start and apply it. None restores the default."""
        global BT_START_DATE
        new = self.DEFAULT if start is None else _pd.Timestamp(start)
        if new >= BT_END_DATE:
            raise ValueError(f"backtest start {new.date()} is not before the end "
                             f"{BT_END_DATE.date()}")
        import dataclasses
        old = BT_START_DATE
        for tag, u in list(REGISTRY.items()):
            d0, d1 = u.date_range
            if _pd.Timestamp(d0) == old:
                REGISTRY[tag] = dataclasses.replace(u, date_range=(new, d1))
        BT_START_DATE = new
        self._SELECTED = None if new == self.DEFAULT else new

    def selected(self):
        """The backtest start, a Timestamp."""
        return BT_START_DATE

    def is_default(self):
        return self._SELECTED is None

    def _code(self):
        return f"s{self._SELECTED:%Y%m%d}"

    def label(self):
        return "" if self.is_default() else f"start {self._SELECTED.date()}"

    def score_floor(self):
        """The first session month the scoring step scores: SCORE_LEAD_YEARS before
        the backtest start, from the first day of that month."""
        s = BT_START_DATE - _pd.DateOffset(years=self.SCORE_LEAD_YEARS)
        return _pd.Timestamp(s.year, s.month, 1)


start_axis = _Start()


# --- buy shortfall ---------------------------------------------------------
# What a buy does when cash cannot pay for all of it: "trim" (the default,
# BUY_SHORTFALL) or "refuse". The rule itself is buy_shortfall.py. The suffix is
# "" at trim, so the canonical names hold trimmed runs; refuse is "_refuse"
# after the start suffix.
class _BuyShortfall(_Axis):
    CHOICES = ("trim", "refuse")
    DEFAULT = BUY_SHORTFALL
    _SELECTED = BUY_SHORTFALL

    def set_selection(self, value):
        """Record this run's setting. None restores the default."""
        if value is None:
            self._SELECTED = self.DEFAULT
            return
        if value not in self.CHOICES:
            raise ValueError(f"buy_shortfall is one of {', '.join(self.CHOICES)}; got {value!r}")
        self._SELECTED = value

    def _code(self):
        return f"{self._SELECTED}"

    def label(self):
        return "" if self.is_default() else "short buys refused"


assert _BuyShortfall.DEFAULT in _BuyShortfall.CHOICES, \
    f"settings.BUY_SHORTFALL must be one of {_BuyShortfall.CHOICES}"
shortfall_axis = _BuyShortfall()


# ===========================================================================
# 4. UNIVERSE REGISTRY
# ===========================================================================
# The single definition of what a universe IS.
#
# WHY THIS EXISTS
#     Nineteen files independently declare a `UNIVERSES` dict mapping a tag to its
#     paths, under NINE mutually incompatible key vocabularies -- `perm`/`tmp` in
#     validate_topn and shuffle_test, `score_perm`/`score_tmp`/`raw_perm`/`raw_tmp`
#     in validate_sizing and validate_breadth_live, `sc`/`sc_tmp`/`raw`/`raw_tmp`/`md`
#     in purge_fix_measure, `cache`/`scores`/`metrics`/`tag`/`end` in nt_run, and so
#     on. They express the same handful of facts and cannot be checked against each
#     other. Adding a universe means editing nineteen files; deleting one means
#     finding all nineteen.
#
#     This module is that definition, once. It began as a DECLARATIVE reader of the
#     existing config modules; at step 7 it absorbed them, and the midcap150 and
#     nifty100 config modules were deleted in the same commit. Nothing about any
#     path changed in the move -- the values below are the values those files
#     computed, and every artefact was checksummed pre/post on the same panel to
#     prove it.
#
# A UNIVERSE IS NOW ONE ROW HERE, AND THAT IS HOW IT IS REMOVED
#     It used to be removable by deleting its config module, and _optional() existed
#     so that deleting one did not make this module unimportable and take the others
#     down with it. There is no config module to delete any more: a universe is added
#     by writing a row and removed by deleting one, in this file, and neither touches
#     the other rows. The property that mattered -- going through one universe to
#     reach another -- is what the registry exists to prevent, and it still holds.
#
#     DELETING A UNIVERSE'S DATA DOES NOT REMOVE THE UNIVERSE, and it did not before
#     either: the midcap150 config module globbed a directory that might not
#     exist, got an empty symbol list, and imported fine. A row whose data is
#     gone is a registered universe with no symbols, which is a broken checkout
#     rather than a removal.
#
# RAW_DATA_DIR IS THE PARENT OF EVERY UNIVERSE'S FOLDER
#     `RAW_DATA_DIR` is data/raw, which holds every universe's source
#     folder. Pointing a panel build at it would sweep in every universe at once,
#     which is one reason engine_core.build_panel takes data_dir with no default.
#
#     `SYMBOLS` is not any universe's symbol list -- it holds five names,
#     is used nowhere, and is vestigial. A universe's names are the symbol_list on
#     its row.
#
# THERE IS NO `frozen` FLAG ANY MORE, DELIBERATELY
#     Two retired universes carried `frozen=True`, which pinned
#     purge_mode="calendar", value_at_open=False and a year-cut window so their
#     published numbers could not move. Both were deleted on 2026-09-11 and the
#     flag went with them rather than being kept "for the next retirement": an
#     axis that is defined but drives nothing reads as live to the next person.
#     If a universe needs freezing again, the field comes back then, with a
#     universe actually setting it. See git history
#     (git show 50562ed:RETIRED_UNIVERSES.md).

HORIZON = 20          # engine_core.HORIZON; repeated here only to name the caches


class IndexFileError(RuntimeError):
    """A source directory does not name exactly one index file."""


class StaleConstituentFarm(RuntimeError):
    """A constituents directory holds links that do not come from its source."""


def normalise_stem(stem):
    """The spelling-insensitive key a file stem is compared under.

    WHY EQUALITY ON THE RAW STEM WAS NOT ENOUGH. The exclusion below is by name,
    and until 2026-09-18 by EXACT name. The supplier's directories spell the
    same index with spaces -- "NIFTY MIDCAP 150.csv", "NIFTY 100.csv" -- where
    this repository's own folders spelled it "NIFTYMIDCAP150.csv" and
    "NIFTY100.csv". Measured against the new folders before the change:
    _constituents(new_midcap150, "NIFTYMIDCAP150") returned 149 names and
    _constituents(new_nifty100, "NIFTY100") returned 100, each with the index among
    them, AND BOTH ASSERTS IN prepare_data_dir() PASSED -- the second one looks
    for the old spelling, which genuinely is not present, so the guard was
    satisfied by the very rename it exists to catch.

    Whitespace and case only. NOT punctuation, NOT digits, NOT a fuzzy match: a
    normaliser loose enough to pair two different instruments would silently
    delete a constituent, which is the same class of error pointing the other
    way. `IndexFileError` covers what this deliberately does not.
    """
    return "".join(stem.split()).casefold()


def _constituents(raw_dir, index_name):
    """The tradable names in a source folder: every CSV stem EXCEPT the index.

    THE INDEX FILE IS NOT A CONSTITUENT, and after step 7 this is the one place
    that says so. Both predecessors carried this expression and a paragraph
    explaining why it cannot be a bare glob, and the paragraph is the part worth
    keeping: engine_core.build_panel reads every CSV in whatever
    directory it is handed, and an earlier make_final_chart_fair.py swept
    NIFTY100.csv in as a 100th "stock" -- so the published index was averaged
    together with its own members and the resulting line was labelled the
    benchmark. The exclusion is BY NAME, never by position and never by a bare
    glob, and prepare_data_dir() asserts it rather than assuming it.

    A MISSING DIRECTORY YIELDS (), NOT AN ERROR, which is what the midcap150
    and nifty100 config modules did at import: Path.glob on a directory that
    does not exist simply produces nothing. See the module docstring on why that is a broken
    checkout rather than a universe removal.
    """
    files = list_dir(raw_dir, "*.csv")
    if not files:
        return ()
    if index_name is None:
        return tuple(f.stem for f in files)

    key = normalise_stem(index_name)
    hits = [f.stem for f in files if normalise_stem(f.stem) == key]
    if len(hits) != 1:
        raise IndexFileError(
            f"index_name {index_name!r} matches {len(hits)} files in {raw_dir}"
            + (f": {hits}" if hits else "")
            + ".\n"
            "  EXACTLY ONE IS REQUIRED. Zero means the exclusion below removes\n"
            "  nothing and every constituent list built from this directory is\n"
            "  one name too long, with the published index sitting in it as a\n"
            "  tradable stock. More than one means the directory does not say\n"
            "  which file is the index. Neither can be resolved by guessing:\n"
            "  correct index_name on the registry row, or correct the folder.")
    return tuple(f.stem for f in files if normalise_stem(f.stem) != key)


CACHE_DIR = ROOT / "cache"


def _fill_count(v, n):
    """Replace the "{n}" count token in a row's text, recursing into dicts.

    A callable (chart_text's subtitle and dd_label) is wrapped so the token is
    filled in what it returns. Plain str.replace, not str.format: several of
    these strings contain literal braces.
    """
    if isinstance(v, str):
        return v.replace("{n}", n)
    if isinstance(v, dict):
        return {k: _fill_count(x, n) for k, x in v.items()}
    if callable(v):
        return lambda *a, _f=v, **k: _fill_count(_f(*a, **k), n)
    return v


@dataclass(frozen=True)
class Universe:
    """One universe, as the repository already defines it.

    Field names are chosen to be readable rather than to match any one of the
    nineteen existing vocabularies -- matching one would misdescribe the others.
    """
    tag: str                      # "nifty100", "midcap150", ... -- see REGISTRY
    label: str                    # for chart titles and report headers; "{n}" is the count
    metrics_dir: Path             # where this universe's artefacts live
    nautilus_scores: str          # parquet filename under nautilus/data/
    nautilus_end: str             # backtest end date the port uses
    purge_mode: str               # "trading" -- purge measured in trading rows
    index_name: Optional[str]     # published index, excluded from the universe
    # THE PUBLISHED INDEX PRICE FILE, or None where the universe has no published
    # index at all. index_name has always recorded that a universe HAS one; this
    # records WHERE it is, so a step that plots the cap-weighted benchmark can ask
    # the universe instead of importing that universe's config module by name.
    # None for a universe with no published index series: a directory-defined
    # basket, which two retired universes were. That is a fact about such a
    # universe and not a missing path.
    index_file: Optional[Path]
    year_range: Optional[Tuple[int, int]]      # retired universes cut by year; None here
    date_range: Optional[Tuple[object, object]]  # live universes cut by date

    # THE SOURCE FOLDER AS DELIVERED -- constituents AND the published index in one
    # directory. Arrived at step 7 from the midcap150 and nifty100 config modules. It is
    # NOT data_dir: data_dir is what build_panel may be pointed at, and pointing it
    # here would sweep the index in as one more tradable name.
    #
    # None MEANS THE DIRECTORY IS THE DEFINITION, as on two retired universes:
    # a basket with no published index and no authoritative symbol list, where
    # data_dir simply exists and symbols() answers None. That shape is kept
    # expressible because it was a real shape, not because a universe uses it now.
    raw_data_dir: Optional[Path]

    # WHAT THIS UNIVERSE'S MEMBERSHIP MEANS FOR ITS NUMBERS -- no default, so a row
    # that omits it fails at construction. The precedent is d3ae8ec, which made
    # DISPLAY, COLOURS and LIQUIDITY Universe fields for the same reason: a fact
    # that matters to every reader must not be omittable by a new row.
    #
    # ONE SENTENCE CARRYING BOTH THE MEANING AND THE PROVENANCE, and deliberately
    # NOT a "static" | "pit" enum. results/survivorship.py:117 already holds
    # SURVIVORSHIP_MODE as a process-wide global; a per-row enum would be a second
    # authority for the same word, and a row disagreeing with the global would have
    # no resolution rule. This field says what the FOLDER's membership means, which
    # the global cannot express per universe and the folder name does not carry.
    #
    # IT EXISTS BECAUSE ONE OF THOSE FOLDER NAMES READS BACKWARDS. A universe
    # sourced from data/raw/Final_Without_Survivorship_Data must say so in terms:
    # "Without_Survivorship" means without survivorship DATA -- current
    # constituents only -- not without survivorship BIAS.
    #
    # NOT DERIVED FROM, AND DOES NOT DERIVE, the SURVIVORSHIP: sentences in
    # chart_text and engine_text. Those interpolate live run values (midcap150's
    # n_late) and carry a per-universe benchmark carve-out (nifty100's cap-weighted
    # index), so a shared static string would either drop the computed figure or
    # become a template -- and a template with run-time interpolation stops being a
    # declaration. ONE AUTHORITY, TWO RENDERINGS: this field is the declaration and
    # is what fails the build; those are rendered prose for their own figures. If
    # they are ever unified, the chart text CITES this field rather than restating
    # it, and that is separate work.
    survivorship: str
    # THE TRADABLE NAMES, SORTED, INDEX EXCLUDED. Computed by _constituents() when
    # the row is built -- eagerly, exactly as the midcap150 config module
    # computed its symbol list at import -- so a mid-run change to the source
    # folder cannot move it.
    # () when raw_data_dir is None.
    symbol_list: Tuple[str, ...]

    # ------------------------------------------------------------------
    # WHAT THE COMBINED CHART SHOWS FOR THIS UNIVERSE -- phase 2, 2026-09-16
    # ------------------------------------------------------------------
    # THREE TABLES IN results/make_combined_universes.py, MOVED HERE VERBATIM.
    # They were keyed by tag, so adding a universe meant finding all three; two of
    # the three refused loudly when one was missing and one did not.
    #
    # NO DEFAULTS, AND THAT IS THE POINT RATHER THAN A STYLE CHOICE. A field with
    # no default cannot be forgotten: a row that omits one fails at CONSTRUCTION
    # with a TypeError naming the field. A checker has to remember to look, and
    # three of registry_coverage_check.py's tables stop being NEEDED rather than
    # being silenced.

    # THE CHART TITLE'S SPELLING, WHICH IS NEITHER index_name NOR label. The title
    # has always said "NIFTY 100" (with a space) and "MIDCAP150" (without the
    # NIFTY prefix), while index_name holds the FILE's name -- "NIFTY100",
    # "NIFTYMIDCAP150" -- which is what the per-universe legend rows use. Deriving
    # one from the other would silently retitle a published chart.
    display_name: str

    # FOUR COLOURS PER UNIVERSE PLUS TWO. Slots 0-3 are v2, v1, buy&hold, index and
    # are UNCHANGED -- the published chart depends on them. Slots 4 and 5 are v3
    # and v4, appended rather than inserted so every existing index keeps pointing
    # at the same colour. A new universe adds a tuple that does not collide with
    # these; a chart that picks a colour by accident is not reproducible.
    # WHAT THIS FIELD ACTUALLY GOVERNS, AND WHAT IT DOES NOT. Measured
    # 2026-09-18 by resolving every reader in the repository. It has exactly TWO
    # consumers: make_combined_universes.py:365, which draws the COMBINED chart,
    # and palette_distance.py, which measures the same lines.
    #
    # THE PER-UNIVERSE CHART DOES NOT READ IT. make_chart.py hardcodes six
    # colours -- #c0392b v2, #2e6da4 v1, #1b9e77 v3, #e6ab02 v4, #3a9d3a
    # buy&hold, #000000 index -- and draws EVERY universe in them. So
    # chart_<tag>.png looks the same whatever this tuple says, and a palette
    # searched here is not visible until two or more universes are selected and
    # STEP 12b actually renders. midcap50's was measured to dE2000 >= 10 on
    # 2026-09-18 and HAS STILL NEVER BEEN DRAWN: its first run selected one
    # universe, so STEP 12b skipped.
    #
    # Whether the per-universe charts SHOULD use this tuple is a real question
    # and is deliberately not answered here.
    chart_colours: Tuple[str, ...]

    # THE LIQUIDITY PARAGRAPH, WHICH IS A MEASURED RESULT AND NOT CHART FURNITURE.
    # Fill sizes against prior-20-day median volume, and what a realistic depth
    # model costs in CAGR points. It cannot be invented for a universe nobody has
    # measured, so None is the DECLARATION that it was not -- the shape LIQUIDITY's
    # NOT_MEASURED had, with the constructor now enforcing presence instead of a
    # checker.
    #
    # EVERY NUMBER IN A NOTE IS STAMPED WITH THE ENGINE THAT MEASURED IT. These
    # were measured before adj_close became the canonical price and before the
    # interior-gap guard, and the headline figures they quote have since moved.
    # They are kept as the liquidity finding, which is about fill sizes rather than
    # about CAGR, and marked rather than silently re-quoted under numbers they were
    # not measured against. Re-measure and restamp, or set None; do not edit them.
    liquidity_note: Optional[str]

    # ------------------------------------------------------------------
    # WHAT THE ENGINE REPORTS FOR THIS UNIVERSE
    # ------------------------------------------------------------------
    # Added 2026-09-15 with step 5, the engine merge. The midcap150 and nifty100
    # engine scripts had diverged in 95 lines of code beyond their tags --
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
    # validation_status IS DELIBERATELY NOT A UNIFORM SHAPE. midcap150 carries a dict of
    # eight measured results; nifty100 carries a sentence saying the work was not done
    # on this universe. That asymmetry is the RECORD OF WHICH UNIVERSE GOT THE WORK,
    # and flattening both into one shape would read as though both were measured.
    # The type tells them apart: dict means measured, str means not.
    # THREE OF THESE HAVE NO DEFAULT, AS OF 2026-09-18, AND THAT IS THE POINT.
    #
    # engine_params_keys defaulted to (), engine_text and chart_text to None.
    # Measured on a Universe constructed without them, before the change:
    #
    #   engine_params_keys = ()   ->  engine_v2_final.py:333 writes
    #       json.dumps({k: _vals[k] for k in u.engine_params_keys}, indent=2)
    #       which is the two bytes "{}". Valid JSON. No exception, no warning.
    #       v2FINAL_params.json exists, is well-formed, and says NOTHING -- and
    #       it is the file that records which arm, which sizing, which CAGR and
    #       which validation status produced the run beside it.
    #
    #   engine_text = None        ->  TypeError at engine_v2_final.py:138
    #   chart_text  = None        ->  TypeError at make_chart.py:176
    #       Loud, but not until STEP 10n and STEP 10p -- after build_scores has
    #       already spent its time on the panel.
    #
    # A FIELD WITH NO DEFAULT CANNOT BE FORGOTTEN, because the row fails at
    # CONSTRUCTION with a TypeError naming the field, before anything imports a
    # checker. That is the same argument registry_coverage_check.py's docstring
    # makes about DISPLAY, COLOURS and LIQUIDITY leaving its table: those three
    # stopped being NEEDED rather than being silenced. These three join them.
    #
    # THE ORDER OF THESE LINES IS A DATACLASS CONSTRAINT, not a preference: a
    # field with no default cannot follow one that has a default, so the three
    # required fields sit above the two that remain optional.
    engine_params_keys: tuple             # v2FINAL_params.json keys, IN ORDER
    engine_text: dict                     # banner, chart title, console blocks

    # WHAT THE CHART STEP RENDERS FOR THIS UNIVERSE. Added 2026-09-15 with step 6.
    # The midcap150 and nifty100 chart scripts diverged in 204 code lines ignoring
    # whitespace, and SOME OF IT REACHES THE PNG: two render parameters, one legend
    # label, and the output stem itself. Preserved, not harmonised, for the same
    # reason as the engine's: a merge is verifiable by the gate, an artefact change
    # is a judgement, and they do not belong in one commit.
    #
    # Most of the pair's labels are NOT here because they derive from data the
    # registry already has -- "<tag> buy&hold (equal-weight universe)" from tag,
    # "<index> (cap-weighted index)" from index_name. Only what cannot be derived
    # is written down.
    chart_text: dict

    # THE TWO THAT KEEP A DEFAULT, AND WHY EACH IS DIFFERENT FROM THE THREE ABOVE.
    #
    # engine_params_static: absent means "no key takes a static value". It is
    # consumed as `_vals.update(u.engine_params_static or {})` and then read as
    # `_vals[k]` for every key in engine_params_keys, so a row that omits it
    # while naming a key that needed it raises KeyError. It fails LOUDLY on the
    # only path where its absence matters, which is what the three above did not.
    #
    # validation_status JOINED THE REQUIRED FIELDS ON 2026-09-18, one commit after
    # the other three, once the decision was taken. Its default was None, and
    # None IS REACHABLE AS AN ARTEFACT VALUE: engine_v2_final.py:329 puts this
    # field straight into v2FINAL_params.json, so a row that left it alone wrote
    #
    #     "validation_status": null
    #
    # which is valid JSON and indistinguishable from a deliberate statement. A
    # universe nobody had validated and a universe whose validation status was
    # never considered produced the same four bytes.
    #
    # NOTHING WAS WRITING null WHEN THIS CHANGED -- all three live rows set the
    # field explicitly -- so this commit moves no byte. It closes the way the
    # next row could.
    #
    # THE SHAPE IS STILL DELIBERATELY NOT UNIFORM. midcap150 carries a dict of eight
    # measured results; the other rows carry sentences saying the work was not done
    # on those universes. The type tells them apart: dict means measured, str
    # means not. Requiring the field does not require a shape, and flattening the
    # two would read as though both were measured.
    validation_status: object

    # THE POINT-IN-TIME SOURCES, 2026-10-10. Required, like the fields above, so a
    # new row cannot forget them. Read only by pit_variant(), i.e. only by a
    # --survivorship pit run; a static run never opens either path.
    #
    # None ON A STATIC-ONLY ROW (2026-10-16): the three market-cap buckets came
    # with no membership file and no with-survivorship prices. Still required, so
    # None is written on the row as a statement. pit_variant() refuses such a row
    # with PitNotAvailable; see has_pit().
    membership_file: Optional[Path]          # data/raw/Survivorship_Bias/<Index>_membership.csv
    survivorship_data_dir: Optional[Path]    # data/raw/Final_With_Survivorship_Data/<folder>

    # THE ONE FIELD THAT KEEPS A DEFAULT, and it is different in kind. It is read
    # as `u.engine_params_static or {}` and then as `_vals[k]` for every key in
    # engine_params_keys, so a row that omits it while naming a key that needed a
    # static value raises KeyError. It fails LOUDLY on the only path where its
    # absence matters, which is exactly what the four fields above did not.
    engine_params_static: dict = None     # values for keys that are not computed

    # THE BIAS LABEL OF A UNIVERSE WHOSE RESULTS CARRY A BIAS THAT CANNOT BE
    # MEASURED (2026-10-16). None on the nine index universes, whose bias is
    # measured by their pit runs. Where set, run.py prints it in the plan and
    # RUN.txt, the engine prints it in run.log and writes it to the params files,
    # and the dashboard and the survivorship sheet show it. "{n}" is filled.
    bias_note: Optional[str] = None

    # DERIVED FROM THE TAG, NOT WRITTEN PER ROW. Until 2026-09-23 each row spelled
    # five paths: a symlink farm under data/raw/, a working panel pair under /tmp
    # and a permanent pair under results*/metrics/. /tmp is shared by every
    # checkout on a machine, so a second checkout read the first one's panels,
    # and the farm's absolute links shipped inside data/ pointing at the first
    # checkout. All three are derived data and now live under cache/<tag>/,
    # which is gitignored:
    #     cache/<tag>/constituents/                 hard links (or copies), index excluded
    #     cache/<tag>/v_<tag>_expanding.parquet         score panel  (+ .source)
    #     cache/<tag>/raw_panel_<tag>_<HORIZON>.parquet raw panel    (+ .source)
    # PARQUET SINCE 2026-09-24, CSV BEFORE: see config.read_table.
    # ONE COPY OF EACH PANEL. The /tmp working copy and the metrics/ permanent
    # copy existed because /tmp does not survive a reboot; a panel in the
    # project does, so the pair collapsed to one file and the copy steps
    # between them (run_all.restore_cache_to_tmp, STEP 15b) were deleted.
    data_dir: Path = field(init=False)        # what build_panel is pointed at
    score_cache: Path = field(init=False)     # the score panel
    raw_cache: Path = field(init=False)       # the raw feature panel
    # The row's text fields before the "{n}" count is filled, so pit_variant()
    # can rebuild them for a different symbol list.
    _templates: dict = field(init=False, repr=False, compare=False)

    @property
    def name(self):
        """The label without its constituent count: "Nifty 100", "MidCap150"."""
        return self.label.split(" (")[0]

    @property
    def is_pit(self):
        """True for the variant pit_variant() builds: its prices come from the
        with-survivorship folder."""
        return self.raw_data_dir is not None and self.raw_data_dir == self.survivorship_data_dir

    def __post_init__(self):
        # A PIT VARIANT CACHES UNDER cache/<tag>/pit/, so its farm and panels can
        # never be read as, or overwrite, the static ones.
        d = CACHE_DIR / self.tag / "pit" if self.is_pit else CACHE_DIR / self.tag
        object.__setattr__(self, "data_dir", d / "constituents")
        object.__setattr__(self, "score_cache", d / f"v_{self.tag}_expanding.parquet")
        object.__setattr__(self, "raw_cache", d / f"raw_panel_{self.tag}_{HORIZON}.parquet")
        # THE CONSTITUENT COUNT IS COMPUTED, NEVER TYPED. Rows write "{n}" where
        # a count of names belongs; it is filled here from symbol_list, which is
        # the set of CSVs the farm links and build_panel scores. A typed count
        # said "49 constituents" on a run that scored 48.
        n = str(len(self.symbol_list))
        _fields = ("label", "survivorship", "validation_status",
                   "engine_text", "chart_text", "engine_params_static", "bias_note")
        object.__setattr__(self, "_templates", {f: getattr(self, f) for f in _fields})
        for f in _fields:
            object.__setattr__(self, f, _fill_count(getattr(self, f), n))

    def symbols(self):
        """The tradable names as a SET, or None when the directory is the definition.

        A set, because that is the shape every caller compares a built panel's
        symbol index against, and it is what the two lambdas this replaced returned.
        `symbol_list` is the sorted tuple, for callers that iterate.
        """
        return None if self.raw_data_dir is None else set(self.symbol_list)

    def prepare_data_dir(self):
        """The directory build_panel should glob, READY TO USE.

        WHY THIS IS AN ACTION AND NOT JUST data_dir. For a universe with no
        raw_data_dir the directory simply exists and this returns it. For every
        registered universe it does not:
        their source folder holds the published INDEX alongside the constituents,
        and build_panel globs whatever directory it is handed, so pointing it at the
        source would sweep NIFTYMIDCAP150.csv or NIFTY100.csv in as one more
        tradable name. The answer is a symlink directory holding the constituents
        ONLY, rebuilt -- pruning anything stale -- each time it is asked for.

        That rebuild is the part `data_dir` cannot express. A merged build_scores
        that read data_dir and skipped the call would point build_panel at whatever
        symlinks happened to be on disk, and the index-exclusion guarantee would
        rest on luck rather than on a step that runs. So the universe carries how
        its directory comes into being, next to where it is.

        THE BODY IS ensure_constituents_dir(), WHICH BOTH PREDECESSORS CARRIED. With
        prose stripped and universe names normalised their two copies were
        line-for-line identical, so this is one implementation rather than a merge
        of two: LINKS, NOT COPIES, because the price data keeps a single source of
        truth in the source folder; and the two asserts are the guarantee, not
        decoration -- the first catches a farm that does not match the symbol list,
        the second catches the index leaking in.
        """
        if self.raw_data_dir is None:
            return self.data_dir
        src = self.raw_data_dir.resolve()

        # THE INDEX CHECK RUNS BEFORE ANY LINK IS WRITTEN, not only in the
        # asserts at the bottom. Those still stand, but they fire after the farm
        # has been built, so a poisoned symbol_list left 149 links on disk -- the
        # index among them -- and only then raised. A guard that refuses after
        # creating the thing it refuses is a guard the next reader has to clean
        # up after.
        if self.index_name is not None:
            key = normalise_stem(self.index_name)
            leaked = [x for x in self.symbol_list if normalise_stem(x) == key]
            if leaked:
                raise IndexFileError(
                    f"{self.tag}: symbol_list holds the index under "
                    f"{leaked} while index_name is {self.index_name!r}.\n"
                    "  These are the same name once whitespace and case are\n"
                    "  removed, so the published index would be linked into the\n"
                    "  constituents directory and averaged with its own members.\n"
                    "  Nothing has been written.")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        wanted = set(self.symbol_list)

        for entry in list_dir(self.data_dir, "*.csv"):       # drop anything stale
            if entry.stem not in wanted:
                entry.unlink()

        # HARD LINKS, NOT SYMLINKS, SINCE 2026-09-24. A symlink needs Developer
        # Mode or administrator rights on Windows; a hard link on NTFS needs
        # neither, and on every platform it costs no space and holds exactly the
        # source file's bytes. Where a hard link cannot be made -- the data on
        # another volume, or a file system without them -- the file is COPIED,
        # with its modification time, and recopied when size or mtime differ.
        #
        # DERIVED FROM raw_data_dir ON EVERY CALL. Each entry is checked against
        # the source and replaced if it is not the same file, so a repointed
        # universe gets the new source's files here, and the panel's content key
        # (config.cache_staleness) then names the change and forces a rebuild.
        # The check this replaced refused a farm of links into another
        # directory; with the farm rebuilt from the current source every time,
        # that state cannot persist.
        for sym in self.symbol_list:
            target = self.raw_data_dir / f"{sym}.csv"
            if not target.exists():
                raise StaleConstituentFarm(
                    f"{self.tag}: {target} does not exist, so the farm cannot be\n"
                    f"  derived from raw_data_dir. symbol_list and the source\n"
                    f"  directory disagree.")
            entry = self.data_dir / f"{sym}.csv"
            if entry.exists() and not entry.is_symlink():
                if os.path.samefile(entry, target):
                    continue
                ts, es = target.stat(), entry.stat()
                if (ts.st_size, ts.st_mtime_ns) == (es.st_size, es.st_mtime_ns):
                    continue
            if entry.exists() or entry.is_symlink():
                entry.unlink()
            try:
                os.link(target, entry)
            except OSError:
                shutil.copy2(target, entry)

        present = tuple(sorted(f.stem for f in list_dir(self.data_dir, "*.csv")))
        assert present == self.symbol_list, \
            f"{self.tag}: constituents directory does not match symbol_list"
        assert not any(f.is_symlink() for f in list_dir(self.data_dir, "*.csv")), \
            f"{self.tag}: a symlink survived in the constituent farm"
        # NORMALISED, so the index cannot re-enter under a different spelling of
        # its own name. See normalise_stem().
        assert (self.index_name is None
                or normalise_stem(self.index_name)
                not in {normalise_stem(x) for x in present}), \
            f"{self.tag}: the index leaked into the constituent set"
        return self.data_dir

    def trading_days(self, index):
        """Restrict a price index to this universe's backtest window.

        ONLY THE DATE CUT IS LIVE. Every remaining universe cuts by DATE
        (BT_START_DATE..BT_END_DATE). The year-cut branch below is what two
        retired universes used (deleted 2026-09-11; six trading days longer);
        no universe sets `year_range` any more, so it is currently unreachable.
        """
        if self.year_range is not None:
            y0, y1 = self.year_range
            return index[(index.year >= y0) & (index.year <= y1)]
        d0, d1 = self.date_range
        return index[(index >= d0) & (index <= d1)]


# ---------------------------------------------------------------------------
# WHERE EACH UNIVERSE'S DATA IS AND WHERE ITS ARTEFACTS GO -- arrived at step 7
# ---------------------------------------------------------------------------
# FROM THE midcap150 AND nifty100 CONFIG MODULES, deleted in the same commit.
# Those two modules were 71 and 85 lines. With prose stripped and universe names
# normalised their CODE differed in exactly two expressions, both path shapes:
# the source folder and the constituent farm. The farm is now derived from the
# tag (cache/<tag>/constituents, see Universe.data_dir). The source folder is
# still written out per universe, because the supplier's folder names are not
# derivable from the tag (midcap150 is Final_NIFTYMidCap150_EoD_Data, nifty100
# is Final_NIFTY100_EoD_Data), and a rule that guessed one wrong would point a
# universe at a missing folder, which yields an empty symbol list rather than
# an error (see _constituents).
#
# THE TWO MODULES' RESULTS_DIR CONSTANTS DO NOT BECOME FIELDS. Both predecessors
# defined one and nothing outside those two files ever read either: they were
# local intermediates on the way to METRICS_DIR. A field that nothing drives reads
# as live to the next person -- see the note on the `frozen` flag above.
_RAW = ROOT / "data" / "raw"

# REPOINTED 2026-09-18. midcap150 and nifty100 keep their metrics
# directories and their history; what changed underneath them is the panel.
# Both now read the supplier's without-survivorship set, and the spelling of
# the index file changed with it -- "NIFTYMIDCAP150" -> "NIFTY MIDCAP 150",
# "NIFTY100" -> "NIFTY 100". The constituent NAMES are identical across the
# move (148 and 99, nothing added, nothing dropped); the PRICES are not, and
# neither is the per-name history: 35 midcap150 names and 16 nifty100 names now
# begin later than they did, and 8 midcap150 names and 2 nifty100 names now begin after
# BT_START_DATE where they did not before. See PANEL_MIGRATION.md.
_WITHOUT_SURV = _RAW / "Final_Without_Survivorship_Data"

# THE POINT-IN-TIME SOURCES, read only by a --survivorship pit run (pit_variant).
# The with-survivorship folders hold today's members and the names that left the
# index; the membership files say who was in it from each effective date until
# the next. Both are supplier data and are never edited (owner, 2026-10-10).
_WITH_SURV = _RAW / "Final_With_Survivorship_Data"
_MEMBERSHIP = _RAW / "Survivorship_Bias"

_MIDCAP150_SOURCE = _WITHOUT_SURV / "Final_NIFTYMidCap150_EoD_Data"
_MIDCAP150_METRICS = ROOT / "results_midcap150" / "metrics"
_MIDCAP150_INDEX = "NIFTY MIDCAP 150"

_NIFTY100_SOURCE = _WITHOUT_SURV / "Final_NIFTY100_EoD_Data"
_NIFTY100_METRICS = ROOT / "results_nifty100" / "metrics"
_NIFTY100_INDEX = "NIFTY 100"

_MIDCAP150 = Universe(
        tag="midcap150", label="MidCap150 ({n} constituents)",
        raw_data_dir=_MIDCAP150_SOURCE,
        membership_file=_MEMBERSHIP / "Midcap150_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTYMidcap150_EoD_Data",
        survivorship=(
            "STATIC. {n} names are TODAY'S MidCap150 members backfilled to "
            "2019-01-01. Midcaps that left the index or delisted during the window "
            "are absent entirely, so both the strategy and its equal-weight "
            "buy&hold are inflated. Source: data/raw/Final_Without_Survivorship_Data/"
            "Final_NIFTYMidCap150_EoD_Data."),
        symbol_list=_constituents(_MIDCAP150_SOURCE, _MIDCAP150_INDEX),
        metrics_dir=_MIDCAP150_METRICS,
        nautilus_scores="scores_midcap150.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_MIDCAP150_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable name.
        # Base 1-Apr-2005 = 1000, which the file reproduces exactly.
        index_file=_MIDCAP150_SOURCE / f"{_MIDCAP150_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="MIDCAP150",
        chart_colours=("#e377c2", "#17becf", "#8fd08f", "#7f7f7f",
                       "#1b9e77", "#e6ab02"),
        liquidity_note=(
            "midcap150 [re-measured 2026-09-20]: 12 of 998 fills with a "
            "prior-20-session median exceed 10% (n=1,006 fills), the largest "
            "34.46% on TATAINVEST 2019-12-26. SUPERSEDES [pre-2026-09-10, "
            "close-basis engine]: 22 of 985 fills exceed 10%, largest 1,614% on "
            "AIIL -- that order is in no current daily_trades, because AIIL's "
            "price file now starts 2024-04-23. The depth-model figure is "
            "unrestated and still from the older run: 1.80 CAGR points, "
            "29.16% -> 27.36%."),
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
        # merge. midcap150 has no "universe" and no "n_symbols"; nifty100 has both
        # and lacks "validated"/"rejected". Neither set is more correct -- they are
        # what the two engines happened to write, and unifying them is a separate
        # change.
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
            "panel_what": "MidCap150 score panel",
            "bh_label": "Equal-weight buy & hold (MidCap150)",
            "assert_index_absent": False,
        },
        chart_text={
            "stem": "chart_midcap150_FINAL",
            # THE INDEX WINDOW END IS A DATA BOUNDARY, not a market one: it is the
            # last date this universe's index file carries. It differs per universe.
            #
            # CORRECTED 2026-09-18 FROM 2026-06-08. `NIFTY MIDCAP 150.csv` ends
            # 2026-08-06; the old value cut the printed index window 10 sessions
            # short of the file. It was display-only -- the sole reader is
            # make_chart.py, which slices the INDEX series for one console line
            # and never the score panel or the engine -- so no committed number
            # moved. WHY it was wrong is recorded as OPEN in PANEL_MIGRATION.md
            # section 6: the transposition reading does not explain the value
            # also landing exactly on the raw panel cutoff.
            "index_window_end": "2026-08-06",
            "dpi": 140,
            "legend_fontsize": 8,
            "rule_width": 94,
            # THE IC / EXTREME-RETURN DIAGNOSTIC BLOCK, midcap150 only. Console output,
            # no artefact, but it re-reads the score panel, so running it for nifty100
            # would be new work rather than new formatting.
            "diagnostics": True,
        },
    )

_NIFTY100 = Universe(
        tag="nifty100", label="Nifty 100 ({n} constituents)",
        raw_data_dir=_NIFTY100_SOURCE,
        membership_file=_MEMBERSHIP / "Nifty100_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTY100_EoD_Data",
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty 100 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. The published NIFTY100 index line is cap-weighted and is "
            "NOT survivorship-biased. Source: "
            "data/raw/Final_Without_Survivorship_Data/Final_NIFTY100_EoD_Data."),
        symbol_list=_constituents(_NIFTY100_SOURCE, _NIFTY100_INDEX),
        metrics_dir=_NIFTY100_METRICS,
        nautilus_scores="scores_nifty100.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_NIFTY100_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable name.
        # Base 1-Jan-2003 = 1000; the file reads 1,008.00 on 2003-01-02, consistent
        # with NSE's published methodology. Verified, not assumed.
        index_file=_NIFTY100_SOURCE / f"{_NIFTY100_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY 100",
        chart_colours=("#c0392b", "#2e6da4", "#3a9d3a", "#000000",
                       "#7f3f98", "#d95f02"),
        liquidity_note=(
            "nifty100 [re-measured 2026-09-20]: 3 of 932 fills with a "
            "prior-20-session median exceed 10% (n=940 fills), and ZERO do on the "
            "60-day window. SUPERSEDES [pre-2026-09-10, close-basis engine]: 3 of "
            "997 fills.\nThe depth figure is unrestated and still from the older "
            "run: modelling realistic depth (10% of median daily volume per level, "
            "three levels) cost 0.01 CAGR points, 25.43% -> 25.42%."),
        # SURVIVORSHIP. These 99 names are TODAY'S index members backfilled to the
        # start of the backtest; companies that were in the Nifty 100 during the
        # window and were later dropped or delisted are absent entirely. It is
        # stated in the chart subtitle and in the forensic log header rather than
        # left to be inferred, and results/survivorship.py stays at "static".
        # NOT MEASURED, and a STRING rather than a dict so it cannot be mistaken
        # for midcap150's eight results. The seed-robustness and sub-period validations
        # on record were run elsewhere and are not claimed here.
        validation_status=("not measured on this universe. The seed-robustness "
                           "and sub-period validations on record were run on "
                           "midcap150, not on these {n} names, and are not "
                           "claimed here."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty 100 ({n} constituents, NIFTY100.csv excluded by name)",
        },
        engine_text={
            "panel_what": "Nifty 100 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 100, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_nifty100",
            # CORRECTED 2026-09-18, with the repoint that made it stale. The old
            # nifty100_benchmark/NIFTY100.csv ended 22-06-2026, so this value
            # was RIGHT until the source changed; Final_NIFTY100_EoD_Data's
            # index file carries 32 further rows and ends 06-08-2026. All 32
            # are past BT_END_DATE, so no number moved -- what was wrong was
            # the sentence under the chart saying where the benchmark stops.
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
    )


# ---------------------------------------------------------------------------
# nifty50 -- THE FIRST OF THE SUPPLIER'S OTHER SIX, ADDED 2026-09-18
# ---------------------------------------------------------------------------
# WHY THIS ONE FIRST, AND WHY ONE AT A TIME. Every one of nifty50's 50 names is
# already in nifty100, measured on the supplier's directories: nifty50 is a STRICT
# SUBSET of nifty100, which was rebuilt on this same vendor panel over the same
# 1,836 sessions at 9d717b0. So nifty50 introduces no name this repository
# has not already priced, and a surprise in its output is attributable to the
# wiring rather than to data nobody has looked at.
#
# It also has the best coverage of the eight: 46 of 50 names are present at
# BT_START_DATE (92.0%, against nifty100's 88.9% and midcap150's 75.7%), and its latest
# first date is 2023-08-21 -- it is the only new universe with no name starting
# in the last two years. The four that start late are MAXHEALTH (2020-08-21),
# ETERNAL (2021-07-23), NESTLEIND (2023-08-01) and JIOFIN (2023-08-21), all four
# already among nifty100's eleven.
#
# NOTHING HAS BEEN RUN ON THIS UNIVERSE. No panel, no cache, no artefact, no
# chart. liquidity_note is None and validation_status says so in words, because
# a placeholder number here would be a claim nobody has earned.
_NIFTY50_SOURCE = _WITHOUT_SURV / "Final_NIFTY50_EoD_Data"
_NIFTY50_METRICS = ROOT / "results_nifty50" / "metrics"
# THE SUPPLIER SPELLS THIS ONE IN TITLE CASE. Seven of the eight index files
# shout -- "NIFTY 100", "NIFTY MIDCAP 150", "NIFTY SMLCAP 250" -- and this one
# is "Nifty 50.csv". It is handled by normalise_stem() like any other spelling,
# and it is written out here rather than derived for exactly that reason.
_NIFTY50_INDEX = "Nifty 50"

_NIFTY50 = Universe(
        tag="nifty50", label="Nifty 50 ({n} constituents)",
        raw_data_dir=_NIFTY50_SOURCE,
        membership_file=_MEMBERSHIP / "Nifty50_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTY50_EoD_Data",
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty 50 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. 4 of the {n} did not exist at BT_START_DATE. The published "
            "Nifty 50 index line is cap-weighted and is NOT survivorship-biased. "
            "Source: data/raw/Final_Without_Survivorship_Data/"
            "Final_NIFTY50_EoD_Data."),
        symbol_list=_constituents(_NIFTY50_SOURCE, _NIFTY50_INDEX),
        metrics_dir=_NIFTY50_METRICS,
        nautilus_scores="scores_nifty50.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_NIFTY50_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable name.
        # NO BASE VALUE IS CLAIMED HERE: the file begins on 03-01-2000 at 1,592.20,
        # which is a mid-series value, so unlike midcap150's and nifty100's rows
        # there is no base-date reading in this file to verify a methodology
        # against. Stating one would be repeating NSE's documentation rather than
        # checking it. On the 2026-10-10 delivery the file carries 6,612 rows,
        # 03-01-2000..06-08-2026.
        index_file=_NIFTY50_SOURCE / f"{_NIFTY50_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY 50",
        # MEASURED, NOT PICKED. The first tuple here was matplotlib's tab10
        # head, chosen by eye, and it collided three ways against nifty100 in NORMAL
        # colour vision on the combined chart: buy&hold #2ca02c vs nifty100's
        # #3a9d3a at dE2000 2.13 -- below the 2.3 just-noticeable difference --
        # the index #111111 vs nifty100's #000000 at 2.96, and this universe's
        # SHIPPING line #1f77b4 vs nifty100's control #2e6da4 at 4.18. Under
        # protanopia it also collided with itself, #ff7f0e against #2ca02c at
        # 1.90.
        #
        # These six were searched out of a 12,015-colour in-gamut Lab grid (L*
        # 35-72, C* 28-95, so a line reads on white rather than merely scoring well)
        # under the constraint that midcap150's and nifty100's tuples do not move.
        # Every one clears dE2000 >= 10 against all twelve of their slots and
        # against each other, in normal vision, deuteranopia and protanopia (Vienot
        # 1999). Achieved minimum 11.24 overall; 15.29 among the four slots the
        # CANONICAL combined chart draws, which is the published figure and is where
        # the margin was spent.
        #
        # SLOT ORDER IS SEMANTIC, not the search's output order: buy&hold stays
        # green as it is on midcap150 and nifty100, and the index stays the darkest
        # of the six. It is dark red rather than neutral, because a neutral would
        # have had to clear nifty100's black and midcap150's grey and nothing in the
        # readable band does. NOTHING CHECKS ANY OF THIS -- see KNOWN_ISSUES.md.
        chart_colours=("#7f4b70", "#4176fc", "#34c2a5", "#932d41",
                       "#1551e7", "#046e59"),
        # NOT MEASURED. None is the declaration, not a hole -- no depth or
        # participation study has been run on this panel, and the combined chart
        # drops the note rather than printing an empty one.
        liquidity_note=None,
        # NOT MEASURED, and a STRING rather than a dict, by the same rule nifty100
        # follows: the type tells a measured universe from an unmeasured one.
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        # THE KEY SET AND ORDER FOLLOW nifty100's, not midcap150's. nifty50 is a
        # strict subset of nifty100 and is read against it, so a params file whose
        # keys are in a different order would make the two awkward to diff for no
        # gain.
        engine_params_static={
            "universe": "Nifty 50 ({n} constituents, 'Nifty 50.csv' excluded "
                        "by name)",
        },
        engine_text={
            "panel_what": "Nifty 50 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 50, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_nifty50",
            # THE LAST DATE THIS UNIVERSE'S INDEX FILE CARRIES, read off the
            # file: "Nifty 50.csv" ends 26-08-2026. That is twenty days later
            # than every other supplier index file, which end 06-08-2026.
            "index_window_end": "2026-08-26",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
    )

# ONLY THE UNIVERSES WHOSE CONFIG IS PRESENT. Declaration order is preserved, so
# a universe that is still here occupies the same position it always did -- LIVE's
# order is documented below as declaration order and callers rely on that.
#
# nifty50 IS APPENDED, NEVER INSERTED, so midcap150 and nifty100 keep positions
# 0 and 1 and every caller relying on declaration order sees what it saw before. Same
# constraint as AXES, same reason: position is load-bearing somewhere the
# row itself does not mention.
_MIDCAP50_SOURCE = _WITHOUT_SURV / "Final_NIFTYMidCap50_EoD_Data"
_MIDCAP50_METRICS = ROOT / "results_midcap50" / "metrics"
# THE SUPPLIER SHOUTS THIS ONE, like six of the eight: "NIFTY MIDCAP 50.csv".
# Written out rather than derived, for the reason nifty50's row gives.
_MIDCAP50_INDEX = "NIFTY MIDCAP 50"

_MIDCAP50 = Universe(
        tag="midcap50", label="MidCap50 ({n} constituents)",
        raw_data_dir=_MIDCAP50_SOURCE,
        membership_file=_MEMBERSHIP / "Midcap50_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTYMidCap50_EoD_Data",
        # midcap50's OWN NUMBERS, MEASURED 2026-09-18. NOT nifty50's paragraph
        # with the nouns changed: the late-lister rate here is 8 of 49, which is
        # DOUBLE nifty50's 4 of 50 in a universe a third the size, and a reader
        # who is handed nifty50's "4 of 50" for this panel is being told the bias
        # is smaller than it is.
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty MidCap 50 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. 8 OF THE {n} did not exist at BT_START_DATE -- POLYCAB "
            "(2019-04-16), SBICARD (2020-03-16), NYKAA (2021-11-10), POLICYBZR "
            "(2021-11-15), PAYTM (2021-11-18), MANKIND (2023-05-09), WAAREEENER "
            "(2024-10-28) and SWIGGY (2024-11-13) -- which is 16.3% of the "
            "universe against 8.0% on nifty50. The published Nifty MidCap 50 "
            "index line is cap-weighted and is NOT survivorship-biased. "
            "Source: data/raw/Final_Without_Survivorship_Data/"
            "Final_NIFTYMidCap50_EoD_Data."),
        symbol_list=_constituents(_MIDCAP50_SOURCE, _MIDCAP50_INDEX),
        metrics_dir=_MIDCAP50_METRICS,
        nautilus_scores="scores_midcap50.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_MIDCAP50_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. NO BASE VALUE IS CLAIMED: the file begins 01-01-2004, a
        # mid-series value, so like nifty50's row there is no base-date reading
        # here to check a methodology against. 5,588 rows, 01-01-2004..06-08-2026.
        index_file=_MIDCAP50_SOURCE / f"{_MIDCAP50_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY MIDCAP 50",
        # MEASURED, NOT PICKED, and the margin is THINNER THAN nifty50's -- which
        # is the finding, not a footnote. Searched under the constraint that
        # midcap150's, nifty100's and nifty50's tuples do not move. 369 pairs
        # evaluated: these six against all EIGHTEEN existing slots and against
        # each other, in normal vision, deuteranopia and protanopia (Vienot 1999).
        #
        # ACHIEVED MINIMUM 10.28, against nifty50's 11.24 when it was third. The
        # tightest five are midcap50/v4 vs midcap150/v1 (10.28, deutan),
        # midcap50/bh vs nifty50/ix (10.29, deutan), midcap50/v3 vs midcap150/v2
        # (10.40, deutan), midcap50/v1 vs midcap50/ix (10.48, normal) and
        # midcap50/v3 vs midcap150/v2 (10.59, protan).
        #
        # THIS COMMENT USED TO END "NO COLLISION IS TOLERATED HERE: every pair
        # clears dE2000 >= 10." THAT IS FALSE AND WAS FALSE WHEN WRITTEN.
        # Corrected 2026-09-19. The 10.28 figure is scoped to the pairs this
        # search covered -- CROSS-UNIVERSE pairs. Five WITHIN-universe pairs
        # already ship below 10, and all five co-appear on one image under
        # `--arm all`:
        #
        #     dE 3.26  nifty100/v1  vs nifty100/v3      dE 7.55  nifty100/v2  vs nifty100/bh
        #     dE 4.24  midcap150/v2 vs midcap150/v1     dE 7.88  midcap150/v3 vs midcap150/ix
        #     dE 7.35  nifty100/v4  vs nifty100/bh
        #
        # So the project's real worst pair is 3.26, not 10.28, and a sentence
        # claiming otherwise made the next universe's palette look like a
        # regression against a standard nothing actually meets. The measured
        # ceiling for a fifth universe inside the readable band is dE 8.712634,
        # not 10 -- see diagnostics/palette_ceiling.txt.
        #
        # THE READABLE BAND IS NOW FULL, AND THIS IS THE NUMBER TO QUOTE WHEN A
        # FIFTH UNIVERSE IS COSTED. Restricting the search to L* 30-72 -- where a
        # line reads on white, which is the band nifty50's palette was drawn from
        # -- the BEST ACHIEVABLE minimum against the existing eighteen is 9.33,
        # BELOW the dE 10 review threshold. These six clear 10 only by spending
        # L* 25.4 to 67.8, four of them darker than any slot nifty50 uses. A
        # fifth universe cannot be given a readable palette at this threshold
        # without moving an existing tuple or lowering the threshold, and both of
        # those are decisions rather than searches.
        chart_colours=("#100fdc", "#5c2c49", "#721e16", "#6f0d64",
                       "#5a8e9e", "#46acfb"),
        # NOT MEASURED. None is the declaration, not a hole.
        liquidity_note=None,
        # NOT MEASURED, and a STRING rather than a dict, by the rule nifty100 and
        # nifty50 follow: the type tells a measured universe from an unmeasured one.
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        # KEY SET AND ORDER FOLLOW nifty100's, as nifty50's does: midcap50 is read
        # against midcap150 and against nifty50, and a third key order would make
        # every such diff awkward for no gain.
        engine_params_static={
            "universe": "Nifty MidCap 50 ({n} constituents, "
                        "'NIFTY MIDCAP 50.csv' excluded by name)",
        },
        engine_text={
            "panel_what": "Nifty MidCap 50 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty MidCap 50, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_midcap50",
            # THE LAST DATE THIS UNIVERSE'S INDEX FILE CARRIES, read off the
            # file: "NIFTY MIDCAP 50.csv" ends 06-08-2026, with the other six.
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
)


# midcap100 IS APPENDED, NEVER INSERTED, same constraint as every row above it.
_MIDCAP100_SOURCE = _WITHOUT_SURV / "Final_NIFTYMidCap100_EoD_Data"
_MIDCAP100_METRICS = ROOT / "results_midcap100" / "metrics"
# THE SUPPLIER SHOUTS THIS ONE TOO: "NIFTY MIDCAP 100.csv".
_MIDCAP100_INDEX = "NIFTY MIDCAP 100"

_MIDCAP100 = Universe(
        tag="midcap100", label="MidCap100 ({n} constituents)",
        raw_data_dir=_MIDCAP100_SOURCE,
        membership_file=_MEMBERSHIP / "Midcap100_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTYMidCap100_EoD_Data",
        # midcap100's OWN NUMBERS, MEASURED 2026-09-19 by reading the first
        # dated row of all 98 constituent files. NOT midcap50's paragraph with
        # the count changed: THE LATE-LISTER RATE HERE IS 21.4%, against
        # midcap50's 16.3% and nifty50's 8.0%, and a reader
        # handed either of those for this panel is being told the bias is
        # roughly half what it is.
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty MidCap 100 members backfilled "
            "to 2019-01-01. Names dropped or delisted during the window are "
            "absent entirely, so both the strategy and its equal-weight "
            "buy&hold are inflated. 21 OF THE {n} did not exist at "
            "BT_START_DATE -- RVNL (2019-04-11), POLYCAB (2019-04-16), "
            "KPITTECH (2019-04-22), 360ONE (2019-09-19), IRCTC (2019-10-14), "
            "PATANJALI (2020-01-27), SBICARD (2020-03-16), POWERINDIA "
            "(2020-03-30), KALYANKJIL (2021-03-26), NYKAA (2021-11-10), "
            "POLICYBZR (2021-11-15), PAYTM (2021-11-18), MANKIND (2023-05-09), "
            "IREDA (2023-11-29), PREMIERENE (2024-09-03), WAAREEENER "
            "(2024-10-28), SWIGGY (2024-11-13), VMM (2024-12-18), LGEINDIA "
            "(2025-10-14), LENSKART (2025-11-10) and GROWW (2025-11-12) -- "
            "which is 21.4% of the universe. The published Nifty MidCap 100 "
            "index line is "
            "cap-weighted and is NOT survivorship-biased. Source: "
            "data/raw/Final_Without_Survivorship_Data/"
            "Final_NIFTYMidCap100_EoD_Data."),
        symbol_list=_constituents(_MIDCAP100_SOURCE, _MIDCAP100_INDEX),
        metrics_dir=_MIDCAP100_METRICS,
        nautilus_scores="scores_midcap100.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_MIDCAP100_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. NO BASE VALUE IS CLAIMED: the file begins 01-01-2001, a
        # mid-series value, so like midcap50's row there is no base-date
        # reading here to check a methodology against. 6,361 rows,
        # 01-01-2001..06-08-2026.
        index_file=_MIDCAP100_SOURCE / f"{_MIDCAP100_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY MIDCAP 100",
        # MEASURED, NOT PICKED, AND IT DOES NOT CLEAR dE 10 -- WHICH IS THE
        # FINDING, NOT A COMPROMISE. Full method, both candidate tuples and the
        # rejection are in diagnostics/palette_ceiling.txt.
        #
        # THE CEILING IS dE2000 = 8.712634, binary searched to 1e-4 inside the
        # readable band L* 30-72, against all 24 existing slots AND against
        # each other, under normal vision, deuteranopia and protanopia (Vienot
        # 1999). dE 10 IS NOT ACHIEVABLE IN THE BAND AT ALL: of the colours
        # that clear 10 against the 24, ZERO lie in L* 30-72; on a step-4 grid
        # exactly four in-band colours clear it and all four are the same olive
        # green, mutually closer than 10. Largest separated subset: 1. Six are
        # needed.
        #
        # WORST PAIRS FOR THIS TUPLE: 10.449 normal (midcap100/5 vs
        # nifty100/0), 8.849 deutan (midcap100/2 vs midcap150/4), 8.713 protan
        # (midcap100/4 vs nifty50/3).
        #
        # AND 8.713 IS 2.7x BETTER THAN WHAT ALREADY SHIPS. Five WITHIN-universe
        # pairs are below 10 today, the worst at dE 3.26 (nifty100/v1 vs
        # nifty100/v3, deutan), and all five co-appear under `--arm all`. The
        # "every pair clears 10" sentence that used to sit on midcap50's row was
        # false when written; it is corrected there.
        #
        # THE BAND IS THE REQUIREMENT AND dE IS THE PROXY, so the band was not
        # left. A tuple clearing dE 10 exists outside it -- four of its six
        # colours near-white, L* 5 to 95 -- and was rejected, as was a
        # normal-vision-only optimum at T = 20.655653 whose deutan collision is
        # 2.560, WORSE than anything shipping. Optimising on the vision that is
        # not binding produces a number, not a ceiling.
        chart_colours=("#5c804c", "#d89094", "#a05464", "#fc606c",
                       "#2c503c", "#9c2000"),
        # NOT MEASURED. None is the declaration, not a hole.
        liquidity_note=None,
        # NOT MEASURED, and a STRING rather than a dict, by the rule nifty100,
        # nifty50 and midcap50 follow: the type tells a measured universe from an
        # unmeasured one.
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        # KEY SET AND ORDER FOLLOW nifty100's, as every row above does.
        engine_params_static={
            "universe": "Nifty MidCap 100 ({n} constituents, "
                        "'NIFTY MIDCAP 100.csv' excluded by name)",
        },
        engine_text={
            "panel_what": "Nifty MidCap 100 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty MidCap 100, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_midcap100",
            # THE LAST DATE THIS UNIVERSE'S INDEX FILE CARRIES, read off the
            # file: "NIFTY MIDCAP 100.csv" ends 06-08-2026, with the other six.
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
)


# midcap50 IS APPENDED, NEVER INSERTED, for the reason nifty50's line gives:
# midcap150, nifty100 and nifty50 keep positions 0, 1 and 2 and every caller
# relying on declaration order sees what it saw before.
# nifty200 IS APPENDED, NEVER INSERTED, same constraint as every row above it.
_NIFTY200_SOURCE = _WITHOUT_SURV / "Final_NIFTY200_EoD_Data"
_NIFTY200_METRICS = ROOT / "results_nifty200" / "metrics"
_NIFTY200_INDEX = "NIFTY 200"

_NIFTY200 = Universe(
        tag="nifty200", label="Nifty200 ({n} constituents)",
        raw_data_dir=_NIFTY200_SOURCE,
        membership_file=_MEMBERSHIP / "Nifty200_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTY200_EoD_Data",
        # nifty200's OWN NUMBERS, MEASURED 2026-09-19 by reading the first dated
        # row of all 197 constituent files. 32 OF 197 IS 16.2% -- essentially
        # midcap50's rate (16.3%) in a universe four times the size, and well
        # BELOW midcap100's 21.4%. The rate does not track universe size, which
        # is why every row here carries its own count rather than inheriting a
        # neighbour's paragraph.
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty 200 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. 32 OF THE {n} did not exist at BT_START_DATE -- RVNL "
            "(2019-04-11), POLYCAB (2019-04-16), KPITTECH (2019-04-22), 360ONE "
            "(2019-09-19), IRCTC (2019-10-14), PATANJALI (2020-01-27), SBICARD "
            "(2020-03-16), POWERINDIA (2020-03-30), MAXHEALTH (2020-08-21), "
            "MAZDOCK (2020-10-12), IRFC (2021-01-29), KALYANKJIL (2021-03-26), "
            "LODHA (2021-04-19), ETERNAL (2021-07-23), NYKAA (2021-11-10), "
            "POLICYBZR (2021-11-15), PAYTM (2021-11-18), MANKIND (2023-05-09), "
            "NESTLEIND (2023-08-01), JIOFIN (2023-08-21), IREDA (2023-11-29), "
            "PREMIERENE (2024-09-03), HYUNDAI (2024-10-22), WAAREEENER "
            "(2024-10-28), SWIGGY (2024-11-13), VMM (2024-12-18), ENRIN "
            "(2025-06-19), TATACAP (2025-10-13), LGEINDIA (2025-10-14), "
            "LENSKART (2025-11-10), GROWW (2025-11-12) and TMCV (2025-11-12) -- "
            "which is 16.2% of the universe, against midcap100's 21.4% and "
            "nifty50's 8.0%. The published Nifty 200 index line is cap-weighted "
            "and is NOT survivorship-biased. Source: "
            "data/raw/Final_Without_Survivorship_Data/Final_NIFTY200_EoD_Data."),
        symbol_list=_constituents(_NIFTY200_SOURCE, _NIFTY200_INDEX),
        metrics_dir=_NIFTY200_METRICS,
        nautilus_scores="scores_nifty200.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_NIFTY200_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. NO BASE VALUE IS CLAIMED: the file begins 01-01-2004, a
        # mid-series value. 5,609 rows, 01-01-2004..06-08-2026.
        index_file=_NIFTY200_SOURCE / f"{_NIFTY200_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY 200",
        # MEASURED 2026-09-19, AGAINST THIRTY SLOTS. dE2000 = 7.484141, binary
        # searched to 1e-4 inside the readable band L* 30-72, against all 30
        # existing slots AND against each other, in normal vision, deuteranopia
        # and protanopia. Method and the ceiling series: see
        # diagnostics/palette_ceiling.txt.
        #
        # WORST PAIRS: 7.705 normal (nifty200/5 vs midcap50/4), 7.484 deutan
        # (nifty200/2 vs midcap150/0), 7.496 protan (nifty200/2 vs midcap100/1).
        #
        # THE CEILING IS FALLING AND THE CURVE IS NOW RECORDED RATHER THAN
        # RE-DERIVED: 8.712634 against 24 slots, 7.484141 against 30. The best
        # single in-band colour clears only 8.55 now, against 10.2452 one
        # universe ago. smallcap250 and nifty500 should be costed against that
        # curve.
        #
        # STILL 2.3x THE WORST PAIR ALREADY SHIPPING (3.26, nifty100/v1 vs
        # nifty100/v3 under deutan). The band was not left.
        chart_colours=("#886884", "#6c18a4", "#80a0a4", "#9870c8",
                       "#d8a85c", "#4080a0"),
        liquidity_note=None,
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty 200 ({n} constituents, "
                        "'NIFTY 200.csv' excluded by name)",
        },
        engine_text={
            "panel_what": "Nifty 200 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 200, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_nifty200",
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
)


# smallcap250 IS APPENDED, NEVER INSERTED, same constraint as every row above.
_SMALLCAP250_SOURCE = _WITHOUT_SURV / "Final_NIFTYSmallCap250_EoD_Data"
_SMALLCAP250_METRICS = ROOT / "results_smallcap250" / "metrics"
# THE SUPPLIER ABBREVIATES THIS ONE, and it is the only one of the eight that
# does: "NIFTY SMLCAP 250.csv", not "NIFTY SMALLCAP 250.csv". Written out rather
# than derived, which is what every row here does and is why the abbreviation
# cost nothing.
_SMALLCAP250_INDEX = "NIFTY SMLCAP 250"

_SMALLCAP250 = Universe(
        tag="smallcap250", label="SmallCap250 ({n} constituents)",
        raw_data_dir=_SMALLCAP250_SOURCE,
        membership_file=_MEMBERSHIP / "SmallCap250_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTYSmallCap250_EoD_Data",
        # smallcap250's OWN NUMBERS, MEASURED 2026-09-19. 90 OF 248 IS 36.3%,
        # THE HIGHEST RATE OF THE SEVEN AND NEARLY DOUBLE midcap100's 21.4%.
        # THE NINETY NAMES ARE IN diagnostics/smallcap250_late_listers.txt
        # rather than inline. Every other row names its late listers here --
        # nifty50 4, midcap50 8, midcap100 21, nifty200 32 -- and ninety does
        # not fit a row a person reads. Truncating the list would make the
        # record incomplete in the universe where it matters most, so the row
        # carries the count, the rate and the pointer, and the file carries the
        # names. NOTHING IS OMITTED; it is relocated, and this comment is where
        # a reader is told so.
        #
        # THIS RATE CAUSES THREE SEPARATE THINGS, and they were each diagnosed
        # alone before the common cause was visible: the calendar density guard
        # fired here (global median 125 against a 2025 median of 237), the
        # symbol-count cost model for build_scores broke here by 31%, and this
        # panel holds FEWER ROWS than nifty200 despite 51 more names. All three
        # are "a third of the symbols have a fraction of a history". See
        # KNOWN_ISSUES.md, the build_scores entry.
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty SmallCap 250 members "
            "backfilled to 2019-01-01. Names dropped or delisted during the "
            "window are absent entirely, so both the strategy and its "
            "equal-weight buy&hold are inflated. 90 OF THE {n} did not exist at "
            "BT_START_DATE -- 36.3%, THE HIGHEST RATE OF ANY UNIVERSE WIRED "
            "HERE, against midcap100's 21.4%, nifty200's 16.2% and nifty50's "
            "8.0%. MORE THAN A THIRD OF THIS PANEL IS NAMES THAT LISTED DURING "
            "THE WINDOW, and 21 of them first traded in 2025. The ninety are "
            "named in diagnostics/smallcap250_late_listers.txt. The published "
            "Nifty SmallCap 250 index line is cap-weighted and is NOT "
            "survivorship-biased. Source: data/raw/"
            "Final_Without_Survivorship_Data/Final_NIFTYSmallCap250_EoD_Data."),
        symbol_list=_constituents(_SMALLCAP250_SOURCE, _SMALLCAP250_INDEX),
        metrics_dir=_SMALLCAP250_METRICS,
        nautilus_scores="scores_smallcap250.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_SMALLCAP250_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. NO BASE VALUE IS CLAIMED: the file begins 01-04-2005, a
        # mid-series value. 5,294 rows, 01-04-2005..06-08-2026.
        index_file=_SMALLCAP250_SOURCE / f"{_SMALLCAP250_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY SMALLCAP 250",
        # MEASURED 2026-09-19, AGAINST THIRTY-SIX SLOTS. dE2000 = 6.801402,
        # binary searched to 1e-4 inside the readable band L* 30-72, against all
        # 36 existing slots AND against each other, over normal vision,
        # deuteranopia and protanopia. The ceiling series is in
        # diagnostics/palette_ceiling.txt.
        #
        # WORST PAIRS: 6.900 normal (smallcap250/5 vs midcap150/4), 6.980 deutan
        # (smallcap250/2 vs midcap50/5), 6.801 protan (smallcap250/5 vs
        # midcap150/4).
        #
        # THE CEILING IS STILL FALLING: best single in-band colour 10.2452 at 24
        # slots, 8.5514 at 30, 7.2555 at 36; T 8.712634, 7.484141, 6.801402.
        # Still 2.1x the worst pair already shipping (3.26, nifty100/v1 vs
        # nifty100/v3 under deutan). The band was not left.
        chart_colours=("#fc8cc4", "#5464d0", "#4890fc", "#487030",
                       "#c00074", "#3ca464"),
        liquidity_note=None,
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty SmallCap 250 ({n} constituents, "
                        "'NIFTY SMLCAP 250.csv' excluded by name)",
        },
        engine_text={
            "panel_what": "Nifty SmallCap 250 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty SmallCap 250, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_smallcap250",
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
)


# nifty500 IS APPENDED, NEVER INSERTED. It is the EIGHTH and last supplier
# folder: with this row wired, every universe on disk is in the registry.
_NIFTY500_SOURCE = _WITHOUT_SURV / "Final_NIFTY500_EoD_Data"
_NIFTY500_METRICS = ROOT / "results_nifty500" / "metrics"
# THE SUPPLIER SPELLS THIS ONE WITH NO SPACE: "NIFTY500.csv". A THIRD
# CONVENTION, against "NIFTY 200.csv" (spaced) and "NIFTY MIDCAP 100.csv"
# (spaced, multi-word), and against smallcap250's abbreviated "NIFTY SMLCAP
# 250.csv". FOUR SUPPLIER SPELLINGS ACROSS EIGHT FOLDERS.
#
# IT IS RECORDED AND NOT NORMALISED, DELIBERATELY. _constituents() EXCLUDES THE
# INDEX BY NAME, so this string is the only thing standing between the index
# series and the tradable universe. Renaming the file on disk to match a
# convention would make this row's literal correct about a file the supplier
# does not ship, and the next re-download would silently put the index back as
# a constituent -- a 496th "stock" that is the benchmark. That is the
# silent-failure site this project has already closed once, and the fix was to
# write the supplier's spelling out rather than derive it.
_NIFTY500_INDEX = "NIFTY500"

_NIFTY500 = Universe(
        tag="nifty500", label="Nifty500 ({n} constituents)",
        raw_data_dir=_NIFTY500_SOURCE,
        membership_file=_MEMBERSHIP / "Nifty500_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NIFTY500_EoD_Data",
        # nifty500's OWN NUMBERS, MEASURED 2026-09-19. 137 of 495 is 27.7% --
        # BELOW smallcap250's 36.3% despite being twice the size, because the
        # Nifty 500 reaches up into the large caps as well as down. The rate
        # tracks how far down the capitalisation ladder an index reaches, not
        # how many names it holds.
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty 500 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. 137 OF THE {n} did not exist at BT_START_DATE -- 27.7%, "
            "between smallcap250's 36.3% and midcap100's 21.4%. The published "
            "Nifty 500 index line is cap-weighted and is NOT "
            "survivorship-biased. Source: data/raw/"
            "Final_Without_Survivorship_Data/Final_NIFTY500_EoD_Data."),
        symbol_list=_constituents(_NIFTY500_SOURCE, _NIFTY500_INDEX),
        metrics_dir=_NIFTY500_METRICS,
        nautilus_scores="scores_nifty500.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_NIFTY500_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. NO BASE VALUE IS CLAIMED: the file begins 03-01-2000, a
        # mid-series value. 6,612 rows, 03-01-2000..06-08-2026 -- with nifty50's,
        # the longest index series of the nine.
        index_file=_NIFTY500_SOURCE / f"{_NIFTY500_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY 500",
        # MEASURED 2026-09-19, AGAINST FORTY-TWO SLOTS -- the last palette this
        # registry needs. dE2000 = 6.136133, binary searched to 1e-4 inside the
        # readable band L* 30-72, against all 42 existing slots AND against each
        # other, over normal vision, deuteranopia and protanopia.
        #
        # WORST PAIRS: 6.143 normal (nifty500/2 vs midcap100/4), 6.143 deutan
        # (nifty500/1 vs midcap50/1), 6.136 protan (nifty500/4 vs midcap150/4).
        #
        # THE SERIES CLOSES, AND ITS DECREMENTS FLATTENED RATHER THAN
        # ACCELERATED: T 8.712634 -> 7.484141 -> 6.801402 -> 6.136133, falling
        # by 1.23, 0.68, 0.67. Best single in-band colour 10.2452 -> 8.5514 ->
        # 7.2555 -> 6.5910. A ninth universe is not costed here, but the band
        # was not exhausted by the eighth. Still 1.9x the worst pair already
        # shipping (3.26, nifty100/v1 vs nifty100/v3 under deutan).
        chart_colours=("#fc6834", "#30505c", "#2c5850", "#682c84",
                       "#70a890", "#84508c"),
        liquidity_note=None,
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty 500 ({n} constituents, "
                        "'NIFTY500.csv' excluded by name -- no space, the "
                        "supplier's spelling)",
        },
        engine_text={
            "panel_what": "Nifty 500 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 500, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_nifty500",
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
)


# microcap250 IS APPENDED, NEVER INSERTED. ADDED 2026-10-10 with the supplier's
# delivery of that date, which brought this ninth folder.
_MICROCAP250_SOURCE = _WITHOUT_SURV / "Final_NiftyMicroCap250_EoD_Data"
_MICROCAP250_METRICS = ROOT / "results_microcap250" / "metrics"
# THE SUPPLIER'S SPELLING, RECORDED AND NOT NORMALISED: "NIFTY MICROCAP250.csv",
# spaced after NIFTY and not before 250. _constituents() excludes the index by
# this name; see the note on _NIFTY500_INDEX.
_MICROCAP250_INDEX = "NIFTY MICROCAP250"

_MICROCAP250 = Universe(
        tag="microcap250", label="MicroCap250 ({n} constituents)",
        raw_data_dir=_MICROCAP250_SOURCE,
        membership_file=_MEMBERSHIP / "MicroCap250_membership.csv",
        survivorship_data_dir=_WITH_SURV / "Final_Survivorship_NiftyMicroCap250_EoD_Data",
        # MEASURED 2026-10-10. 102 of 242 names have no price row before
        # BT_START_DATE -- 42.1%, the highest rate of the nine; 37 of them start
        # after 2024-01-01.
        survivorship=(
            "STATIC. {n} names are TODAY'S Nifty Microcap 250 members backfilled "
            "to 2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. 102 OF THE {n} did not exist at BT_START_DATE -- 42.1%, "
            "the highest of the nine universes. The published Nifty Microcap 250 "
            "index line is cap-weighted and is NOT survivorship-biased. Source: "
            "data/raw/Final_Without_Survivorship_Data/"
            "Final_NiftyMicroCap250_EoD_Data."),
        symbol_list=_constituents(_MICROCAP250_SOURCE, _MICROCAP250_INDEX),
        metrics_dir=_MICROCAP250_METRICS,
        nautilus_scores="scores_microcap250.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_MICROCAP250_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. 5,282 rows, 01-04-2005..06-08-2026; the first row is 1000.0.
        index_file=_MICROCAP250_SOURCE / f"{_MICROCAP250_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name="NIFTY MICROCAP 250",
        # MEASURED 2026-10-10, AGAINST FORTY-EIGHT SLOTS. Greedy maximin search
        # over 6,000 random sRGB colours with L* 30-72 (generator seed 20261010),
        # CIEDE2000 under normal vision, deuteranopia and protanopia: the closest
        # of these six to any existing slot is dE 5.48, the closest pair among
        # the six is 6.21. Below nifty500's 6.14 against 42 slots; nothing is
        # near the JND of 2.3. Re-run palette_distance.py for the full report.
        chart_colours=("#b85c68", "#5050bc", "#c08080", "#4c9490",
                       "#94082c", "#2438d0"),
        liquidity_note=None,
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty Microcap 250 ({n} constituents, "
                        "'NIFTY MICROCAP250.csv' excluded by name -- the "
                        "supplier's spelling)",
        },
        engine_text={
            "panel_what": "Nifty Microcap 250 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty Microcap 250, {n} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_microcap250",
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
)


# THE THREE MARKET-CAP BUCKETS ARE APPENDED, NEVER INSERTED (2026-10-16). The
# supplier delivered them as folders of stocks grouped by market capitalisation,
# with no membership history and no with-survivorship prices, so they are static
# only and pit_variant() refuses them. The bucket bounds are the supplier's folder
# names; no unit is written anywhere until the owner confirms it with the supplier.
#
# THE INDEX IN ALL THREE IS "NIFTY 500.csv", spaced, byte-identical to
# Final_NIFTY500_EoD_Data/NIFTY500.csv (SHA-256 02548e3c...b75b3). It is the broad
# Nifty 500, not an index of any bucket. SCI.csv is in both mcap1500to5000 and
# mcapover10000, the same bytes in each.
#
# {k} IN THE LABEL, MEASURED 2026-10-16 from the price files: names whose last row is
# before BT_END_DATE (2026-05-29). mcap1500to5000: CIGNITITEC 2025-12-23, SANGHIIND
# 2026-04-02. mcap5001to10000: none. mcapover10000: GSPL 2025-12-23, AIRTELPP
# 2026-02-05. Names starting after BT_START_DATE: 184 of 477, 79 of 216, 158 of 538.
#
# mcap1500to5000 WAS DELIVERED WITH 478 NAMES. The owner removed ELCIDIN on
# 2026-10-16 (KNOWN_ISSUES.md); {n} is counted from the folder, so it is 477.
_MCAP_INDEX = "NIFTY 500"


def _bias_label(k):
    return ("STATIC AND NOT AN INDEX. The supplier delivered these {n} names as a "
            f"market-cap bucket, with no membership history. Only {k} of the {{n}} "
            "stop trading before the window ends, so the list appears to hold the "
            "bucket's members near the time of delivery, not the members at each "
            "date. A stock that left the bucket or was delisted is likely missing; "
            "a stock that grew into it is present for the whole window. Both the "
            "strategy and its buy & hold therefore likely carry survivorship and "
            "look-ahead bias, which cannot be measured without membership files. "
            "The benchmark index is the broad NIFTY 500, not a bucket index.")


def _mcap_row(tag, folder, bounds, k, colours):
    src = _WITHOUT_SURV / folder
    label = _bias_label(k)
    return Universe(
        tag=tag, label=f"Market cap {bounds} bucket ({{n}} constituents)",
        raw_data_dir=src,
        membership_file=None,
        survivorship_data_dir=None,
        survivorship=label + " Source: data/raw/Final_Without_Survivorship_Data/" + folder + ".",
        symbol_list=_constituents(src, _MCAP_INDEX),
        metrics_dir=ROOT / f"results_{tag}" / "metrics",
        nautilus_scores=f"scores_{tag}.parquet",
        nautilus_end=str(BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_MCAP_INDEX,
        # THE PUBLISHED CAP-WEIGHTED NIFTY 500. Benchmark only, never a tradable
        # name. 6,612 rows, 03-01-2000..06-08-2026, as nifty500's.
        index_file=src / f"{_MCAP_INDEX}.csv",
        year_range=None, date_range=(BT_START_DATE, BT_END_DATE),
        display_name=f"MARKET CAP {bounds}",
        # MEASURED 2026-10-16, AGAINST FIFTY-FOUR SLOTS. Greedy maximin search over
        # 6,000 random sRGB colours with L* 30-72 (generator seed 20261016),
        # CIEDE2000 under normal vision, deuteranopia and protanopia, 18 colours for
        # the three buckets in turn: the closest of the 18 to any existing slot is
        # dE 4.66, the closest pair among them 4.77. Above the JND of 2.3, below
        # microcap250's 5.48. Re-run palette_distance.py for the full report.
        chart_colours=colours,
        liquidity_note=None,
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these {n} names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status", "bias_note"),
        engine_params_static={
            "universe": f"Market cap {bounds} bucket ({{n}} constituents, "
                        f"'NIFTY 500.csv' excluded by name -- the supplier's spelling)",
            "bias_note": label,
        },
        engine_text={
            "panel_what": f"Market cap {bounds} bucket score panel",
            "bh_label": f"Equal-weight buy & hold (market cap {bounds} bucket, {{n}} names)",
            "assert_index_absent": True,
        },
        chart_text={
            "stem": f"chart_{tag}",
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "diagnostics": False,
        },
        bias_note=label,
    )


_MCAP1500TO5000 = _mcap_row(
    "mcap1500to5000", "Final_Universe_MarcketCap_1500_5000", "1500 to 5000", 2,
    ("#3460fc", "#dc280c", "#f84850", "#8c9cd8", "#a4b084", "#24808c"))
_MCAP5001TO10000 = _mcap_row(
    "mcap5001to10000", "Final_Universe_MarcketCap_5001_10000", "5001 to 10000", 0,
    ("#ac185c", "#4c10fc", "#749cac", "#18c4b8", "#50482c", "#845c48"))
_MCAPOVER10000 = _mcap_row(
    "mcapover10000", "Final_Universe_MarcketCap_GT_10000", "over 10000", 2,
    ("#80b4ec", "#cc3cb0", "#2c6478", "#e0448c", "#449454", "#0488e0"))


def _pit_constituents(raw_dir, index_name):
    """The tradable names in a with-survivorship folder, the index excluded.

    LIKE _constituents, EXCEPT THAT NO INDEX FILE IS ALLOWED. microcap250's
    with-survivorship folder has none; the index line is read from index_file,
    which points into the without-survivorship folder in both modes. More than one
    file matching the index name still refuses.
    """
    files = list_dir(raw_dir, "*.csv")
    if index_name is None:
        return tuple(f.stem for f in files)
    key = normalise_stem(index_name)
    hits = [f.stem for f in files if normalise_stem(f.stem) == key]
    if len(hits) > 1:
        raise IndexFileError(f"index_name {index_name!r} matches {len(hits)} files "
                             f"in {raw_dir}: {hits}")
    return tuple(f.stem for f in files if normalise_stem(f.stem) != key)


def first_membership_date(u):
    """The first effective date in u's membership file, as a Timestamp."""
    import sys as _sys
    _res = ROOT / "results"
    if str(_res) not in _sys.path:
        _sys.path.insert(0, str(_res))
    import survivorship as _sv
    return _sv._read_raw(u.membership_file)["effective_date"].min()


class PitNotAvailable(ValueError):
    """--survivorship pit asked of a universe that has no point-in-time sources."""


def has_pit(u):
    """True when u has a membership file and with-survivorship prices."""
    return u.membership_file is not None and u.survivorship_data_dir is not None


def pit_refusal(u):
    """The sentence every caller prints when pit is asked of a static-only row."""
    return (f"{u.tag} is static only: the supplier delivered no membership file and no "
            f"with-survivorship prices for this market-cap bucket, so --survivorship pit "
            f"cannot run it.")


def pit_variant(u):
    """The point-in-time version of a static row. ONE RULE FOR EVERY UNIVERSE.

      prices      survivorship_data_dir, which also holds names that left the index
      caches      cache/<tag>/pit/ (Universe.__post_init__)
      window      starts at the later of the static start and the first membership
                  row, so the first pit rebalance is the first session on or after
                  that row (owner's decision, 2026-10-10)
      metrics     the same directory; every pit artefact carries the _pit suffix
    """
    import dataclasses
    import pandas as _pd
    if not has_pit(u):
        raise PitNotAvailable(pit_refusal(u))
    d0, d1 = u.date_range
    start = max(_pd.Timestamp(d0), first_membership_date(u))
    t = u._templates
    return dataclasses.replace(
        u, raw_data_dir=u.survivorship_data_dir,
        symbol_list=_pit_constituents(u.survivorship_data_dir, u.index_name),
        date_range=(start, d1),
        label=t["label"], validation_status=t["validation_status"],
        engine_text=t["engine_text"], chart_text=t["chart_text"],
        engine_params_static=t["engine_params_static"],
        survivorship=(
            "POINT-IN-TIME membership from " + str(u.membership_file.relative_to(ROOT))
            + ", priced from " + str(u.survivorship_data_dir.relative_to(ROOT))
            + " ({n} names, current and dropped). The membership file fails "
            "survivorship.validate and is used by the owner's decision; members with "
            "no price file leave residual survivorship bias, and the symbols column "
            "carries some look-ahead. See the run's RUN.txt."))


def use_pit(tags):
    """Replace REGISTRY's rows for `tags` with their pit variants, IN PLACE.

    Called once by run.py, before the plan is built, when --survivorship pit is
    selected. In place because every consumer looks a universe up in this dict.
    """
    for t in tags:
        if not has_pit(REGISTRY[t]):
            raise PitNotAvailable(pit_refusal(REGISTRY[t]))
    for t in tags:
        if not REGISTRY[t].is_pit:
            REGISTRY[t] = pit_variant(REGISTRY[t])


REGISTRY = {u.tag: u for u in (_MIDCAP150, _NIFTY100, _NIFTY50, _MIDCAP50, _MIDCAP100, _NIFTY200, _SMALLCAP250, _NIFTY500,
                                  _MICROCAP250, _MCAP1500TO5000, _MCAP5001TO10000, _MCAPOVER10000)}

# THE METRICS DIRECTORY IS CREATED AT IMPORT, exactly as the midcap150 and
# nifty100 config modules did with METRICS_DIR.mkdir(parents=True,
# exist_ok=True) at module level. Steps write into it without checking it
# exists, so the side effect has to survive the merge or the first write on a
# fresh checkout fails.
for _u in REGISTRY.values():
    _u.metrics_dir.mkdir(parents=True, exist_ok=True)

# The universes that ship: every registered universe, in declaration order.
#
# DECLARATION ORDER IS NOT THE REPORTING ORDER. Rows are appended as universes
# are added, so LIVE runs midcap150, nifty100, nifty50, midcap50, midcap100,
# nifty200, smallcap250, nifty500. A caller whose OUTPUT depends on order must
# use report_order() or certified(), or name the universes explicitly, rather
# than iterate LIVE. Iterating LIVE for an ordered report once swapped the two
# blocks of verify_v34_arms.py's report, which is how this note came to exist.
LIVE = list(REGISTRY.values())


# ---------------------------------------------------------------------------
# REPORTING ORDER -- the sequence a MULTI-UNIVERSE report puts universes in.
# ---------------------------------------------------------------------------
# THIS IS NOT REGISTRY ORDER AND MUST NOT BE. Registry order is declaration order
# (see LIVE) and it is the right answer for selection, where the question is
# "which universes", a set. It is the WRONG answer for a report, where position
# is visible in a filename, a legend and a colour assignment.
#
# THE LARGE-CAP INDICES COME FIRST, widest to narrowest (nifty500, nifty200,
# nifty100, nifty50), then the midcap indices, widest to narrowest (midcap150,
# midcap100, midcap50), then smallcap250. nifty50 sits next to nifty100
# because it is a strict subset of it, so the two large-cap lines are adjacent
# in every combined report.
#
# FILENAMES DEPEND ON THIS ORDER. make_combined_universes.py names the combined
# chart from the selected tags in this sequence, so the certified pair is
# chart_COMBINED_nifty100_midcap150.png whatever order the tags were typed in.
# Reordering this tuple renames every combined figure.
#
# A TAG ABSENT FROM REGISTRY IS SIMPLY SKIPPED, so this stays correct as universes
# are removed. A registered tag absent from THIS tuple would be dropped silently
# from every combined report, which is why report_order() raises on one instead.
REPORT_ORDER = ("nifty500", "nifty200", "nifty100", "nifty50", "midcap150", "midcap100", "midcap50", "smallcap250",
                "microcap250", "mcapover10000", "mcap5001to10000", "mcap1500to5000")


# ---------------------------------------------------------------------------
# THE CERTIFIED UNIVERSES -- the ones the verification gates measure.
# ---------------------------------------------------------------------------
# The sizing, breadth, top-N and shuffle checks were built and measured on these
# two universes, and the Nautilus port is certified on them (nt_verify). Until
# 2026-09-24 each of those scripts wrote the pair out by hand as
# (REGISTRY["nifty100"], REGISTRY["midcap150"]); this is that pair, once. ORDER IS
# LOAD-BEARING: every one of those reports runs nifty100 first, and their committed
# outputs are in that order. The leakage and execution-timing checks (GATE 9) run
# on every universe since 2026-09-25 through gated(), below. nt_verify fails on
# four of the other six (KNOWN_ISSUES.md, "GATE 9 runs on all 8 universes"), so
# adding a tag here is not free.
CERTIFIED = ("nifty100", "midcap150")


def certified():
    """The CERTIFIED universes as Universe objects, in CERTIFIED order."""
    return [REGISTRY[t] for t in CERTIFIED]


def gated():
    """Every registered universe, the CERTIFIED ones first and in their order.

    The universes check_all's GATE 9 (next-open fills, feature causality, purge)
    runs on since 2026-09-25. CERTIFIED first so the two blocks those reports
    always carried keep their place; the rest follow in registry order.
    """
    return certified() + [u for t, u in REGISTRY.items() if t not in CERTIFIED]


# ---------------------------------------------------------------------------
# WHAT THIS RUN SELECTED -- registration and selection are NOT the same thing.
# ---------------------------------------------------------------------------
# REGISTRY answers "which universes EXIST in this checkout". A run answers a
# narrower question: "which universes did the caller ASK FOR". Until now the two
# were conflated: every multi-universe step gated on whether a universe was in
# REGISTRY. That is correct for a REMOVED universe and wrong for an UNSELECTED
# one: a run that selected two universes still drew a third on the
# fair-comparison chart, because it was registered though nobody asked for it.
#
# A REPORT MUST NEVER SHOW A UNIVERSE THE CALLER DID NOT SELECT. So selection is
# recorded here, next to the registry, and the steps that build multi-universe
# output ask `selected_tags()` instead of `REGISTRY`.
#
# THE DEFAULT IS EVERY REGISTERED UNIVERSE, which is exactly what those steps saw
# before this existed. So a step run on its own -- `python results/<step>.py`, a
# test, an import from a notebook -- behaves as it always did, and a full
# `--universe all` run is unchanged. Verified byte-identical on all 281 artefacts.
class _UniverseSelection:
    """Which registered universes this run works on. run.py sets it once."""
    _SELECTED = None

    def set_selection(self, tags):
        """Record which universes this run selected. Called once by run.py.

        Unknown tags raise: silently narrowing a selection to nothing is how a run
        produces no output and reports success. Passing None restores the default.
        """
        if tags is None:
            self._SELECTED = None
            return
        want = [t.tag if hasattr(t, "tag") else t for t in tags]
        unknown = [t for t in want if t not in REGISTRY]
        if unknown:
            raise KeyError(f"cannot select unregistered universe(s) {', '.join(unknown)}; "
                           f"registered: {', '.join(REGISTRY)}")
        self._SELECTED = [t for t in REGISTRY if t in set(want)]

    def selected_tags(self):
        """The tags this run is working on, in REGISTRY order.

        Defaults to every registered universe when nothing has set a selection.
        Intersected with REGISTRY on every call, so a universe removed after the
        selection was set cannot come back through this door.
        """
        if self._SELECTED is None:
            return list(REGISTRY)
        return [t for t in self._SELECTED if t in REGISTRY]

    def selected(self):
        """selected_tags() as Universe objects."""
        return [REGISTRY[t] for t in self.selected_tags()]


universe_axis = _UniverseSelection()


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
            f"settings.REPORT_ORDER does not name {', '.join(missing)}. "
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


RETIRED_TAGS = ("mid", "n100", "n50", "58", "74")


def unknown_universe_message(tags, choices=None):
    """The one error text for a universe tag that is not registered.

    Names every valid universe. The short tags were renamed on 2026-09-18 and the
    58 and 74 were deleted on 2026-09-11; none of them is accepted as an alias,
    because an alias that silently maps an old name keeps the old name alive.
    """
    choices = list(REGISTRY) if choices is None else list(choices)
    old = [t for t in tags if t in RETIRED_TAGS]
    msg = (f"unknown universe(s) {', '.join(repr(t) for t in tags)}. "
           f"Valid universes: {', '.join(choices)}.")
    if old:
        msg += (" The short tags mid, n100 and n50 were renamed on 2026-09-18 "
                "(midcap150, nifty100, nifty50) and the 58 and 74 universes were "
                "deleted on 2026-09-11; none of them is accepted.")
    return msg


def check_tags(tags, choices=None):
    """Exit with status 2 and unknown_universe_message() if any tag is unknown.

    `choices` narrows the valid set for a tool that supports only some
    universes; it defaults to every registered universe. "all" is not a tag and
    is left to the caller.
    """
    choices = list(REGISTRY) if choices is None else list(choices)
    unknown = [t for t in tags if t not in choices]
    if unknown:
        import sys
        print(unknown_universe_message(unknown, choices), file=sys.stderr)
        raise SystemExit(2)
    return list(tags)


def argv_universes(argv):
    """Every universe named on a command line by --universe=<t> or --universe <t>.

    Comma-separated values are split. The values are returned as given, in
    order, and are NOT validated here; pass them to check_tags().
    """
    vals = []
    for i, a in enumerate(argv):
        if a.startswith("--universe="):
            vals.append(a.split("=", 1)[1])
        elif a == "--universe" and i + 1 < len(argv):
            vals.append(argv[i + 1])
    return [t for v in vals for t in v.split(",") if t]


def from_argv(argv, default=None, choices=None):
    """Read --universe=<tag> from a command line, refusing any unknown tag.

    No flag means `default` if given, else every registered universe. An
    unknown tag, including a retired short tag, exits with status 2 and a
    message naming the valid universes; it is never ignored and never mapped to
    a current name.
    """
    picked = check_tags(argv_universes(argv), choices)
    if picked:
        return [REGISTRY[t] for t in picked]
    return [REGISTRY[default]] if default else list(LIVE)


# ===========================================================================
# 5. ARTEFACT NAMING
# ===========================================================================
# The single naming authority. One place composes an artefact's name.
#
# WHY THIS EXISTS
#     The same bug has now been found on three axes in turn: a hardcoded artefact
#     name where a selection-derived one belonged, on the CADENCE axis, then the
#     ARM axis, then the PROFILE axis. Each was fixed at its own call site. That is
#     why it kept recurring -- there was no single place to fix it, so each new axis
#     re-opened the same hole somewhere else.
#
#     The composition rule itself was never the problem. It is four lines, and
#     `results/v34_common.py:300` already writes them correctly:
#
#         SFX = arm_reg.selection_suffix() + cadence.suffix() + profiles.suffix()
#
#     The problem is that those four lines are RETYPED at every site, and a site
#     that retypes three of the four axes is indistinguishable, by reading, from one
#     that legitimately varies over three. This module makes the composition callable
#     once and the omission declarable -- so that leaving an axis out becomes a
#     statement a reader can check, rather than an absence nobody can see.
#
# WHAT IT DOES NOT DO
#     It does not rename anything. `tail()` returns exactly the string the existing
#     sites already build, in the existing order, with the existing default-is-empty
#     rule on every axis. Adopting it at a site is a refactor with no artefact churn;
#     if a filename moves, that is a bug in this module, not an intended migration.
#
# THE DEFAULT-IS-UNSUFFIXED RULE, AND ITS ONE SHARP EDGE
#     Every axis returns "" at its default, so a fully-default run writes the
#     canonical published name. That is what keeps the seven v34_comparison gates
#     reading one file. It also means AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE
#     SAME STRING -- which is precisely how site 12 went unnoticed: a research-profile
#     run and a profile-blind writer are byte-identical in their output paths, and
#     they differ only when someone finally runs `tradeable`. The name cannot reveal
#     the omission. Only a declaration can, which is what `declare()` is for.

import arms.registry as _arm  # noqa: E402

# The axes, in the order they appear in a name. This order is LOAD-BEARING: it is
# the order v34_common.py has always used, and changing it renames every
# non-default artefact in the repository.
#
# SURVIVORSHIP IS APPENDED AFTER TAX (2026-10-10), for the same reason: "" at
# static, so no existing name moves, and "_pit" lands after "_tax" when it is not.
#
# THE DRAWDOWN LIMIT IS APPENDED AFTER SURVIVORSHIP (2026-10-13): "" when off,
# "_dd20" after "_pit" when on. No existing name moves.
#
# STARTING CAPITAL IS APPENDED AFTER dd (2026-10-14): "" at Rs 10,00,000,
# "_cap5000000" after every other suffix otherwise.
#
# MARKET IMPACT, THEN THE PARTICIPATION CAP, ARE APPENDED AFTER CAPITAL
# (2026-10-15): "" at k 0 and at the profile's own cap; "_impact0p003" and
# "_pcap0p1" otherwise.
#
# FIXED CAPITAL IS APPENDED AFTER THE PARTICIPATION CAP (2026-10-16): "" when off,
# "_fixed" after every other suffix when on. No existing name moves.
#
# THE BACKTEST START IS APPENDED AFTER FIXED CAPITAL (2026-10-22): "" at
# 2019-01-01, "_s20070924" after every other suffix otherwise. No existing name
# moves.
#
# THE BUY-SHORTFALL RULE IS APPENDED AFTER THE START (2026-10-27): "" at the
# default trim, "_refuse" after every other suffix otherwise. No name moves, but
# the unsuffixed names now hold trimmed runs; refuse is the rule they held before.
#
# TAX IS APPENDED, NEVER INSERTED (2026-09-17). Appending leaves every existing
# non-default name -- every _r40, every _tradeable, every arm suffix -- exactly
# where it was, because the tax suffix is empty at the default and lands after
# the other three when it is not. Inserting it anywhere else in this tuple
# renames artefacts whose names are recorded by SHA-256 in the retired-universe
# manifest (deleted 2026-09-24; git show 50562ed:RETIRED_UNIVERSES-manifest.txt).
AXES = ("arm", "cadence", "profile", "tax", "survivorship", "dd", "capital", "impact",
        "pcap", "fixed", "start", "buy_shortfall")

_SUFFIX = {
    "arm": lambda: _arm.selection_suffix(),
    "cadence": lambda: cadence.suffix(),
    "profile": lambda: profile_axis.suffix(),
    "tax": lambda: tax.suffix(),
    "survivorship": lambda: survivorship_axis.suffix(),
    "dd": lambda: dd_axis.suffix(),
    "capital": lambda: capital_axis.suffix(),
    "impact": lambda: impact_axis.suffix(),
    "pcap": lambda: pcap_axis.suffix(),
    "fixed": lambda: fixed_axis.suffix(),
    "start": lambda: start_axis.suffix(),
    "buy_shortfall": lambda: shortfall_axis.suffix(),
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


def cost_basis():
    """What a run's figures are net of, from the selected profile and tax.

    One phrase for chart subtitles, so a --profile tradeable or --tax on chart
    does not carry the research, before-tax wording every chart used to print.
    """
    from slippage import SLIPPAGE
    import profiles
    cap = profiles.participation_cap()
    s = f"ALL NUMBERS AFTER Zerodha charges and a flat {SLIPPAGE*100:g}% slippage"
    if cap is not None:
        s += f", with fills capped at {cap*100:g}% of prior-20-session median volume"
    if not impact_axis.is_default():
        s += (f", plus square-root impact k {impact_axis.selected():g} x sqrt(order / "
              f"prior-20-session median volume)")
    return s + (", and AFTER capital-gains tax" if tax.selected() else ", BEFORE tax")


def run_label(universe, arms):
    """The line every chart title starts with: universe, arm(s), cadence, tax, profile.

    Added 2026-09-23. A cadence-3 engine chart stated no cadence anywhere, and a
    chart that does not say which run drew it cannot be checked against the run.
    `universe` is a label or a list of labels; `arms` is an iterable of arm names.
    """
    uni = universe if isinstance(universe, str) else ", ".join(universe)
    arms = list(arms)
    return (f"{uni}  |  arm{'s' if len(arms) != 1 else ''} {', '.join(arms)}  |  "
            f"cadence {cadence.selected()}  |  tax {'on' if tax.selected() else 'off'}"
            f"  |  profile {profile_axis.selected()}"
            + ("" if survivorship_axis.is_default() else f"  |  survivorship {survivorship_axis.selected()}")
            + ("" if dd_axis.is_default() else f"  |  {dd_axis.label()}")
            + ("" if capital_axis.is_default() else f"  |  {capital_axis.label()}")
            + ("" if impact_axis.is_default() else f"  |  {impact_axis.label()}")
            + ("" if pcap_axis.is_default() else f"  |  {pcap_axis.label()}")
            + ("" if fixed_axis.is_default() else f"  |  {fixed_axis.label()}")
            + ("" if start_axis.is_default() else f"  |  {start_axis.label()}")
            + ("" if shortfall_axis.is_default() else f"  |  {shortfall_axis.label()}"))


def path_tail(rebal=None):
    """The directory-segment tail for the current cadence, profile and tax:
    "" at every default, else "@r40", "@tradeable", "@tax" in AXES order.

    ONE RULE FOR BOTH PER-COMBINATION DIRECTORY TREES. nautilus/reports/<u>/<seg>
    (nt_run.reports_segment) carried all three axes; runs/<u>/<seg>
    (run_dir) carried the cadence only, so a `--tax on` or `--profile
    tradeable` arm run wrote into the same runs/<u>/<arm>/ as a research run and
    replaced its chart. Both now take the tail from here.

    THE CADENCE IS THE ARGUMENT, NOT THE SELECTION: both callers are handed
    `rebal` explicitly, and None means the default, as reports_segment always
    treated it. Profile and tax are read from the selection.
    """
    r = cadence.DEFAULT if rebal is None else int(rebal)
    seg = "" if r == cadence.DEFAULT else f"@r{r}"
    if not profile_axis.is_default():
        seg += f"@{profile_axis.selected()}"
    if not tax.is_default():
        seg += "@tax"
    return (seg + survivorship_axis.segment() + dd_axis.segment() + capital_axis.segment() + impact_axis.segment()
            + pcap_axis.segment() + fixed_axis.segment() + start_axis.segment() + shortfall_axis.segment())


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
#   settings.name / settings.tail             arm, cadence, profile   SOUND
#   SFX            v34_common.py:300      arm, cadence, profile   SOUND
#   artefact_tag   audit_step.py:108      arm, cadence, profile   SOUND
#                                          (arm rides in the tag body: v3 -> midcap150_v3)
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
# RE-PROBED 2026-10-10 FOR THE SURVIVORSHIP AXIS, one composer at a time with only
# that axis off its default (survivorship_axis.set_selection("pit")): every entry
# but selection_suffix gained "_pit" or "@pit". selection_suffix carries the arm
# alone, as before.
#
# RE-PROBED 2026-10-13 FOR THE DRAWDOWN-LIMIT AXIS, the same way, with only
# dd_axis.set_selection(dd_axis.make(20)) off its default: every entry but
# selection_suffix gained "_dd20" or "@dd20".
#
# RE-PROBED 2026-10-14 FOR THE CAPITAL AXIS, with only
# capital_axis.set_selection(5_000_000) off its default: every entry but
# selection_suffix gained "_cap5000000" or "@cap5000000".
#
# RE-PROBED 2026-10-15 FOR THE IMPACT AND PARTICIPATION-CAP AXES, with only
# impact_axis.set_selection(0.003) and pcap_axis.set_selection(0.1) off their
# defaults under the tradeable profile: every entry but selection_suffix gained
# "_impact0p003_pcap0p1" or "@impact0p003@pcap0p1".
#
# RE-PROBED 2026-10-16 FOR THE FIXED-CAPITAL AXIS, with only
# fixed_axis.set_selection(True) off its default: every entry but selection_suffix
# gained "_fixed" or "@fixed".
#
# RE-PROBED 2026-10-22 FOR THE BACKTEST-START AXIS, with only
# start_axis.set_selection("2007-09-24") off its default: every entry but
# selection_suffix gained "_s20070924" or "@s20070924".
#
# RE-PROBED 2026-10-27 FOR THE BUY-SHORTFALL AXIS, with only
# buy_shortfall.set_selection("refuse") off its default: every entry but
# selection_suffix gained "_refuse" or "@refuse".
#
# A spelled-out set cannot do that. An axis added to AXES now appears in NO
# entry's value until somebody measures it and types it in, so the default for a
# new axis is "unproven", which is the only safe default an enforcement table has.
CARRIES = {
    "settings.name":       frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                    "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "settings.tail":       frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                    "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "SFX":               frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                    "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "artefact_tag":      frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                    "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "_c(":               frozenset({"cadence", "profile", "tax", "survivorship", "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "_ci(":              frozenset({"cadence", "profile", "tax", "survivorship", "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "selection_suffix":  frozenset({"arm"}),
    "nt_reports_segment": frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                     "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "reports_segment":   frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                    "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "chart_path":        frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                    "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
    "combined_chart_path": frozenset({"arm", "cadence", "profile", "tax", "survivorship",
                                      "dd", "capital", "impact", "pcap", "fixed", "start",
                                    "buy_shortfall"}),
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
