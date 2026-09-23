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
# CACHE RESOLUTION -- one place, so a stale or missing cache fails loudly
# ---------------------------------------------------------------------------
# A PANEL'S IDENTITY IS THE CONTENT OF THE CSVs IT WAS BUILT FROM.
#
# Until 2026-09-18 it was the path alone, and a repointed universe went on
# reading the old vendor's 217 MB panel. From 2026-09-18 to 2026-09-23 it was
# the path plus the source DIRECTORY, which caught a repoint and nothing else:
# removing SUZLON.csv from midcap50's source left the directory unchanged, the
# cached panel passed, and the run exited 0 still trading SUZLON 38 times.
#
# SO THE SIDECAR RECORDS seed_cache_key.source_key() OVER THE CONSTITUENT FARM:
# every CSV name and the sha256 of its bytes. The farm is what build_panel
# globs, so it is exactly the set of files scored. A panel is current only if
# that key matches the farm as it is now. The directory is recorded beside it
# for a reader and is not compared: the same bytes in another checkout are the
# same panel, which is what lets a copied tree reuse its cache.
#
# WHAT A MISS DOES DEPENDS ON WHO ASKED. The builder (build_scores_step) prints
# the reason and rebuilds. A reader raises CacheSourceError naming the reason and
# the command that rebuilds: a reader that rebuilt a 70-minute panel in passing
# would hide the fact that its input changed. There is no flag to accept a stale
# panel.
SOURCE_SIDECAR_SUFFIX = ".source"


class CacheSourceError(RuntimeError):
    """A cache could not be shown to have been built on the current source."""


def cache_source_file(cache_path):
    """The sidecar recording the source key `cache_path` was built from."""
    p = Path(cache_path)
    return p.with_name(p.name + SOURCE_SIDECAR_SUFFIX)


def source_key_for(u):
    """seed_cache_key.source_key over u's constituent farm, built if needed."""
    from seed_cache_key import source_key
    if u.raw_data_dir is None:
        raise CacheSourceError(
            f"{u.tag}: a universe with no raw_data_dir has no panel to key.")
    return source_key(sorted(Path(u.prepare_data_dir()).glob("*.csv")))


def write_cache_source(cache_path, u, key):
    """Record `key` beside a cache. Called by whoever writes the cache.

    The key is taken BEFORE the build by the caller and passed in, so the
    sidecar describes the files that were read, not whatever is on disk after.
    """
    import json
    rel = root_relative(u.raw_data_dir)
    # naming: axis-free -- the sidecar's name is its cache's name plus a fixed
    # suffix, so it carries whatever axes that cache carries and adds none of
    # its own; there is no arm, cadence, profile or tax choice expressed here.
    cache_source_file(cache_path).write_text(json.dumps(
        {"universe": u.tag, "raw_data_dir": rel, "digest": key["digest"],
         "n_files": key["n_files"], "files": key["files"]}, indent=1) + "\n")


def _cache_owner(path):
    """The registered universe whose cache `path` is, or None.

    IMPORTED LAZILY. universes/registry.py imports this module at its own import
    time, so a module-level import here is a cycle.
    """
    from universes.registry import REGISTRY
    p = Path(path).resolve()
    for u in REGISTRY.values():
        for cand in (u.score_cache, u.raw_cache):
            if Path(cand).resolve() == p:
                return u
    return None


def cache_staleness(cache_path, u):
    """None if `cache_path` was built from u's current source, else the reason."""
    import json
    from seed_cache_key import key_difference
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return f"no panel at {cache_path}"
    side = cache_source_file(cache_path)
    if not side.exists():
        return f"no source sidecar ({side.name}), so what it was built from is unknown"
    try:
        rec = json.loads(side.read_text())
    except ValueError:
        return (f"{side.name} is in the pre-2026-09-23 format (a directory path "
                f"only), which cannot show whether a CSV was added or removed")
    cur = source_key_for(u)
    if rec.get("digest") == cur["digest"]:
        return None
    diff = key_difference(rec.get("files", {}), cur["files"])
    return (f"source changed since the panel was built ({rec.get('n_files')} -> "
            f"{cur['n_files']} files): {diff or 'digest differs'}")


def _verified(cache_path, what):
    """Return `cache_path` only if it was built from its universe's current source."""
    u = _cache_owner(cache_path)
    if u is None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  This path is not the score or raw cache of any registered\n"
            f"  universe, so which source it was built from cannot be\n"
            f"  established. A panel of unknown provenance is not usable as\n"
            f"  evidence. Add the row that owns it, or delete the file.")
    why = cache_staleness(cache_path, u)
    if why is not None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  STALE PANEL -- refusing to return it: {why}.\n"
            f"  Every number computed from it would describe other data. Rebuild:\n"
            f"      ./venv/bin/python run.py --universe {u.tag} --steps pipeline")
    return cache_path


# ---------------------------------------------------------------------------
# THE SAME QUESTION, ONE LAYER UP: WHAT DATA DID A PUBLISHED ARTEFACT COME FROM
# ---------------------------------------------------------------------------
# The sidecar above protects CACHES. _cache_owner() matches only score_cache,
# raw_cache, score_tmp and raw_tmp, so a daily_trades or a v34_params -- the files
# people read and quote -- is covered by nothing.
#
# MEASURED 2026-09-20, WHICH IS WHY THIS EXISTS. midcap150's two tradeable
# artefacts were written 2026-09-17 against data/raw/MidCap150/clean. The universe
# was repointed at Final_Without_Survivorship_Data on 2026-09-18. Neither artefact
# said which source it came from, no gate compared one against the other, and the
# only reason it surfaced at all was someone reconstructing a median by hand. All
# seven gates were green throughout.
#
# WHOLE FILE, NOT A ROW COUNT. A row count catches a truncated or extended
# history and nothing else. The participation cap eats the VOLUME column, and a
# supplier that revised volume while leaving dates and prices untouched would pass
# a row count, pass a date-range check and pass a re-derivation of fill prices --
# every test available before this one. Hashing every byte catches it. It costs
# 0.11 s over midcap150's 96 MB and 0.30 s over nifty500's 312 MB, measured, which
# is small enough that there is no argument for a cheaper and weaker answer.
#
# THE LINK FARM IS WHAT IS HASHED, not raw_data_dir, because the farm is what
# build_panel globs. raw_data_dir is recorded beside it: if the two ever disagree
# the artefact carries both halves and the difference is readable.
def root_relative(p):
    """`p` resolved, as a path relative to the project root when it is inside it.
    A relative `p` is taken as already relative to the root, not to the cwd."""
    q = Path(p)
    q = (q if q.is_absolute() else PROJECT_ROOT / q).resolve()
    try:
        return str(q.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(q)


def data_fingerprint(data_dir, raw_data_dir):
    """What a published artefact records about the price data it was built from.

    Returns a dict with the resolved link directory, the resolved raw_data_dir,
    where the symlinks actually point, the file count, and
    seed_cache_key.source_key's digest over every CSV in the farm -- the same
    digest a panel's sidecar records.
    """
    from seed_cache_key import source_key
    d = Path(data_dir)
    files = sorted(d.glob("*.csv"))
    targets = {str(f.resolve().parent) for f in files}
    if len(targets) == 1:
        target = targets.pop()
    elif not targets:
        target = None
    else:
        target = f"MIXED: {len(targets)} directories"
    key = source_key(files)
    # PATHS ARE RECORDED RELATIVE TO THE PROJECT ROOT, 2026-09-23. They were
    # absolute, so the same data in a second checkout wrote a different
    # v34_params*.json. GATE 8 compares through root_relative() on both sides,
    # so artefacts written with absolute paths before this still compare.
    return {
        "link_dir": root_relative(d),
        "link_target_dir": root_relative(target) if target and not target.startswith("MIXED") else target,
        "raw_data_dir": root_relative(raw_data_dir) if raw_data_dir else None,
        "n_files": key["n_files"],
        "digest": key["digest"],
        "digest_covers": ("every byte of every CSV in link_dir, the volume column "
                          "included; recompute with config.data_fingerprint()"),
    }


def require_cache(path, what="score panel"):
    """Return `path` if it exists and is current, or raise with the remedy.

    ONE LOCATION PER PANEL SINCE 2026-09-23. There used to be a working copy in
    /tmp and a permanent copy under results*/metrics/, and this took both. /tmp
    is shared by every checkout on a machine, so a second checkout read the
    first one's panel. Both copies are now one file under cache/<tag>/.
    """
    p = Path(path)
    if p.exists():
        return _verified(p, what)
    u = _cache_owner(p)
    tag = u.tag if u is not None else "<universe>"
    raise FileNotFoundError(
        f"{what} not found at {p}.\n"
        f"  Build it with\n"
        f"      ./venv/bin/python run.py --universe {tag} --steps pipeline\n"
        f"  using the venv interpreter; see requirements.txt.")
