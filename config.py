"""
config.py
=========
All phases (data prep, model training, backtest) take their
Every phase (data prep, model training, backtest) imports its shared constants
from this file. Symbol list, paths and date splits live in one place so that
nothing is hardcoded anywhere else.

When raw CSVs are added to RAW_DATA_DIR, their filenames must match the entries
in the SYMBOLS list below.
"""

from pathlib import Path

# Imported at module level, not beside its first user further down, because
# BT_START_DATE / BT_END_DATE below are Timestamps and are needed at import time.
import pandas as _pd

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
# config74.py, config_mid.py and config_n100.py already do this for their own
# metrics dirs; config.py did NOT, so STEP 2 (engine_core) crashed on the first
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
# THE NAMES ARE DELIBERATELY NOT BT_START / BT_END.
#   engine_core.py:93 defines BT_START, BT_END as YEAR INTEGERS (2019, 2026) and
#   is deliberately not changed -- it is the retired 58 universe's provenance.
#   Two constants with the same name and different types in one repository is
#   how a previous mismatch happened, so these carry _DATE and are Timestamps.
#
# Scripts that import the int form from engine_core (mid_jackknife.py,
# n100_jackknife.py, mid_topn_test.py, experiments/sizing_test.py) therefore keep
# the OLD year window and keep running. Their outputs stay internally consistent
# but describe a different window from anything using the constants below.
BT_START_DATE = _pd.Timestamp("2019-01-01")
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
# literals so the 58's and 74's published numbers cannot move -- the same freeze
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
# split is not date constants at all -- it is the expanding monthly retrain with a
# 32-day purge in engine_core.score_monthly().

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

# ============================================================================
# CENTRAL DATE HANDLING -- read every raw data file through this.
# Whatever the format (ISO / M-D-Y / D-M-Y / D-Mon-Y), it is auto-detected and
# converted to datetime. For a new data source, use read_price_csv() and nothing
# else needs to change.
#
# Detection is driven by evidence, not by guessing:
#   a value above 12 in slot 1  -> that slot is the DAY  -> dayfirst=True
#   a value above 12 in slot 2  -> that slot is the DAY  -> dayfirst=False
#   above 12 in both slots      -> corrupt or mixed -> raise (never fail silently)
#   never above 12 anywhere     -> genuinely ambiguous -> warn and assume DD-MM
# ============================================================================


def smart_parse_dates(s, source=""):
    """Detect the date format from the data itself and return datetimes."""
    s = _pd.Series(s).astype(str).str.strip()
    sample = s[s.ne("") & s.ne("nan")]
    if len(sample) == 0:
        return _pd.to_datetime(s, errors="coerce")

    # ISO (YYYY-MM-DD) -- unambiguous, year first
    if sample.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}").mean() > 0.9:
        return _pd.to_datetime(s, errors="coerce")

    parts = sample.str.extract(r"^(\d{1,4})[-/](\d{1,4})[-/]")
    if parts.isna().all().any():          # e.g. 03-Jan-2000
        return _pd.to_datetime(s, errors="coerce", dayfirst=True)

    a = _pd.to_numeric(parts[0], errors="coerce")
    b = _pd.to_numeric(parts[1], errors="coerce")
    first_is_day, second_is_day = bool((a > 12).any()), bool((b > 12).any())

    if first_is_day and second_is_day:
        raise ValueError(
            f"Ambiguous/corrupt dates in {source or 'input'}: "
            "both first and second slot exceed 12. Check the file."
        )
    if first_is_day:
        return _pd.to_datetime(s, errors="coerce", dayfirst=True)
    if second_is_day:
        return _pd.to_datetime(s, errors="coerce", dayfirst=False)

    print(f"    [WARN] {source or 'input'}: date format ambiguous "
          "(no day > 12 anywhere) -- assuming DD-MM. Verify if this is new data.")
    return _pd.to_datetime(s, errors="coerce", dayfirst=True)


def read_price_csv(path, date_col="date", **kw):
    """Read any raw price CSV; dates auto-normalised to datetime."""
    df = _pd.read_csv(path, **kw)
    if date_col in df.columns:
        df[date_col] = smart_parse_dates(df[date_col], source=str(path))
    return df


# ---------------------------------------------------------------------------
# CACHE RESOLUTION -- one place, so a missing cache fails loudly and early
# ---------------------------------------------------------------------------
# A CACHE'S IDENTITY IS ITS PATH *AND* THE SOURCE DIRECTORY IT WAS BUILT FROM.
#
# Until 2026-09-18 it was the path alone: require_cache() asked `perm.exists()`
# and returned it. That is the right question only while a universe's raw data
# never moves. The moment mid and n100 were repointed at the supplier's panel,
# the caches keyed by tag -- v_mid_expanding_cache.csv, raw_panel_mid_cache.csv
# and their n100 pair -- kept their names and their homes, so every consumer
# went on reading 217 MB of the OLD vendor's prices and reporting the result as
# a number computed on the new one.
#
# MEASURED BEFORE THE FIX, not argued: raw_panel_mid_cache.csv carried 256 rows
# for 360ONE dated before 2019-09-19, and the new source's 360ONE.csv begins ON
# 2019-09-19 -- 256 rows that the directory the universe now names cannot
# produce. On a date both vendors carry, the cache read M&MFIN 2019-01-01
# close=287.8653, the old source 287.8653 and the new source 287.6314.
#
# SO THE SOURCE TRAVELS WITH THE CACHE, in a sidecar written by whoever writes
# the cache, and it is CHECKED on every resolution. The expected value is not
# supplied by the caller: it is read from the registry row that owns the cache
# path, so a caller cannot satisfy the check by asserting the wrong source.
#
# THERE IS NO WAY TO TURN THIS OFF. No parameter, no default, no environment
# variable -- a flag that restores the old return would be the old bug with a
# name. A cache whose provenance cannot be established is REFUSED, and the
# refusal is a raise that leaves the interpreter non-zero. Refusing is the whole
# point: a rebuild fallback here would silently discard the operator's evidence
# that something is wrong, which is how the stale panel survived in the first
# place.
SOURCE_SIDECAR_SUFFIX = ".source"


class CacheSourceError(RuntimeError):
    """A cache could not be shown to have been built on the current source."""


def cache_source_file(cache_path):
    """The sidecar recording which raw directory `cache_path` was built from."""
    p = Path(cache_path)
    return p.with_name(p.name + SOURCE_SIDECAR_SUFFIX)


def write_cache_source(cache_path, raw_data_dir):
    """Record the source directory beside a cache. Called by whoever writes it.

    RESOLVED, NOT AS GIVEN, because the two sides of the later comparison are
    reached by different routes -- one from a registry row, one from a string on
    disk -- and a symlinked or relative spelling of the same directory must not
    read as a different directory.
    """
    if raw_data_dir is None:
        raise CacheSourceError(
            f"refusing to record a null source for {cache_path}: a universe "
            f"with no raw_data_dir has no panel to cache.")
    # naming: axis-free -- the sidecar's name is its cache's name plus a fixed
    # suffix, so it carries whatever axes that cache carries and adds none of
    # its own; there is no arm, cadence, profile or tax choice expressed here.
    cache_source_file(cache_path).write_text(
        str(Path(raw_data_dir).resolve()) + "\n")


def _cache_owner(path):
    """The registered universe whose cache `path` is, or None.

    IMPORTED LAZILY. universes/registry.py imports this module at its own import
    time, so a module-level import here is a cycle. The lazy import is not a
    style choice and removing it will not fail at edit time -- it fails at the
    first import of config.py.
    """
    from universes.registry import REGISTRY
    p = Path(path).resolve()
    for u in REGISTRY.values():
        for cand in (u.score_cache, u.raw_cache, u.score_tmp, u.raw_tmp):
            if Path(cand).resolve() == p:
                return u
    return None


def _verified(cache_path, what):
    """Return `cache_path` only if its recorded source is the current one."""
    u = _cache_owner(cache_path)
    if u is None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  This path is not the score or raw cache of any registered\n"
            f"  universe, so which raw directory it was built from cannot be\n"
            f"  established. A panel of unknown provenance is not usable as\n"
            f"  evidence. Add the row that owns it, or delete the file.")

    expected = Path(u.raw_data_dir).resolve()
    side = cache_source_file(cache_path)
    if not side.exists():
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  No source sidecar ({side.name}), so this cache predates source\n"
            f"  recording and cannot be shown to match the universe's current\n"
            f"  raw directory:\n"
            f"      universe     {u.tag}\n"
            f"      raw_data_dir {expected}\n"
            f"  DELETE the cache and rebuild it with\n"
            f"      ./venv/bin/python run_all.py\n"
            f"  This is not rebuilt for you: a cache that disappears and\n"
            f"  reappears during someone else's run is how a wrong panel gets\n"
            f"  read as a right one.")

    actual = Path(side.read_text().strip()).resolve()
    if actual != expected:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  CACHE SOURCE MISMATCH -- refusing to return it.\n"
            f"      universe          {u.tag}\n"
            f"      built from        {actual}\n"
            f"      universe now uses {expected}\n"
            f"  Every number computed from this file would be a number about\n"
            f"  the first directory, reported under a universe that names the\n"
            f"  second. DELETE the cache and its sidecar and rebuild with\n"
            f"      ./venv/bin/python run_all.py")
    return cache_path


def require_cache(perm, tmp=None, what="score panel"):
    """Return whichever cache exists, or raise with an actionable message.

    WHY THIS EXISTS
        run_all.py copies /tmp to the permanent caches only at the END of a run,
        so any script reading a permanent path executes BEFORE that copy on a
        fresh run. Three separate failures came from this in two days:
          - make_mid_chart.py read results_mid/metrics/v_mid_expanding_cache.csv
            unconditionally and crashed the pipeline at step 10d;
          - nt_export_scores.py was scheduled before the cache-save block and
            crashed at step 16;
          - and earlier, a stale permanent cache was read silently, which made
            nt_verify report NOT VERIFIED with 91 symbol-set differences that had
            nothing to do with the port.

        Crashing mid-pipeline and silently falling back are both wrong. Silent
        fallback is worse: it produces a number from the wrong input. This
        resolves the two locations explicitly and, if neither is present, says
        which file is missing and what to run.
    """
    from pathlib import Path as _P
    perm = _P(perm)
    if perm.exists():
        return _verified(perm, what)
    if tmp is not None and _P(tmp).exists():
        return _verified(_P(tmp), what)
    raise FileNotFoundError(
        f"{what} not found.\n"
        f"  looked for permanent : {perm}\n"
        f"  looked for working   : {tmp}\n"
        f"  Neither exists. Run `./venv/bin/python run_all.py` to build them; the\n"
        f"  permanent copy is written at the END of that run, so a script reading\n"
        f"  the permanent path cannot run standalone before the first full\n"
        f"  pipeline.\n"
        f"  THE INTERPRETER MATTERS. run_all.py spawns every step with\n"
        f"  sys.executable, so whatever launches it is used for all 32 steps.\n"
        f"  `python3` is not interchangeable here: on the machine this project\n"
        f"  was built on it is Python 3.11 with no lightgbm, and below\n"
        f"  nautilus_trader's 3.12 floor. Corrected 2026-09-02; this message\n"
        f"  previously named `python3`."
    )
