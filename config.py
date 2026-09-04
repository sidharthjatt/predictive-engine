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
        return perm
    if tmp is not None and _P(tmp).exists():
        return _P(tmp)
    raise FileNotFoundError(
        f"{what} not found.\n"
        f"  looked for permanent : {perm}\n"
        f"  looked for working   : {tmp}\n"
        f"  Neither exists. Run `python3 run_all.py` to build them; the permanent\n"
        f"  copy is written at the END of that run, so a script reading the\n"
        f"  permanent path cannot run standalone before the first full pipeline."
    )
