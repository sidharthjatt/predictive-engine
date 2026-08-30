"""
config_mid.py -- separate config for the MidCap150 universe (third universe)
===========================================================================
This touches neither the 58-stock system nor the 74. It overrides paths and the
symbol list only:
  - Data:   data/raw/MidCap150/clean/       (149 CSVs = 148 constituents + 1 index)
  - Output: results_mid/metrics/            (kept apart from results/ and results74/)

Everything else -- 17 features, TOP_N and BUFFER (defined in config.py, currently
8 and 16), HORIZON=REBAL=20, 32-day purge,
the same 10 seeds, SAFETY=0.98, CASH_YIELD=0.0 -- stays byte-identical to the 58
setup, so that only the universe differs and the comparison stays fair.

THE INDEX FILE IS NOT A CONSTITUENT
    NIFTYMIDCAP150.csv in that folder is the published index, not a stock. It is
    excluded from SYMBOLS_MID and must never enter the ranking universe.

    This is not hypothetical. engine_core.build_panel takes a data_dir and does
    Path(_src).glob("*.csv"), which would sweep the index in as a 149th "stock" --
    the same bare-glob mistake that put NIFTY100.csv into the constituent basket in
    make_final_chart_fair.py. Because build_panel lives in results/ and is not to be
    modified, the exclusion is handled here instead: CONSTITUENTS_DIR holds links to
    the 148 constituents only, and callers assert the panel's symbol set equals
    SYMBOLS_MID.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Source data as delivered: 148 constituents plus the index, in one folder.
RAW_DATA_DIR_MID = PROJECT_ROOT / "data" / "raw" / "MidCap150" / "clean"

# The published cap-weighted index. Benchmark only, never a tradable name.
# Base 1-Apr-2005 = 1000, which the file reproduces exactly.
INDEX_FILE_MID = RAW_DATA_DIR_MID / "NIFTYMIDCAP150.csv"
INDEX_NAME_MID = "NIFTYMIDCAP150"

# Constituents only. Built by ensure_constituents_dir() below.
CONSTITUENTS_DIR_MID = PROJECT_ROOT / "data" / "raw" / "MidCap150" / "constituents"

# Outputs for the MidCap150 universe -- separate folder, never mixed with 58 or 74
RESULTS_DIR_MID = PROJECT_ROOT / "results_mid"
METRICS_DIR_MID = RESULTS_DIR_MID / "metrics"
METRICS_DIR_MID.mkdir(parents=True, exist_ok=True)

# The 148 tradable names, index excluded, resolved from the source folder.
SYMBOLS_MID = sorted(f.stem for f in RAW_DATA_DIR_MID.glob("*.csv")
                     if f.stem != INDEX_NAME_MID)


def ensure_constituents_dir():
    """Populate CONSTITUENTS_DIR_MID with links to the 148 constituent CSVs.

    build_panel globs a directory, so the only way to feed it a filtered universe
    without editing results/ is to give it a directory that already excludes the
    index. Links, not copies: the data has a single source of truth in clean/.
    Returns the directory.
    """
    CONSTITUENTS_DIR_MID.mkdir(parents=True, exist_ok=True)
    wanted = set(SYMBOLS_MID)
    for link in CONSTITUENTS_DIR_MID.glob("*.csv"):     # drop anything stale
        if link.stem not in wanted:
            link.unlink()
    for sym in SYMBOLS_MID:
        link = CONSTITUENTS_DIR_MID / f"{sym}.csv"
        if not link.exists():
            link.symlink_to(RAW_DATA_DIR_MID / f"{sym}.csv")
    present = sorted(f.stem for f in CONSTITUENTS_DIR_MID.glob("*.csv"))
    assert present == SYMBOLS_MID, "constituents directory does not match SYMBOLS_MID"
    assert INDEX_NAME_MID not in present, "the index leaked into the constituent set"
    return CONSTITUENTS_DIR_MID
