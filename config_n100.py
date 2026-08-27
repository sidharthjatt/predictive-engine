"""
config_n100.py -- separate config for the Nifty 100 universe (fourth universe)
=============================================================================
Mirrors config_mid.py exactly. It overrides paths and the symbol list only:
  - Data:   data/raw/nifty100_benchmark/    (100 CSVs = 99 constituents + 1 index)
  - Output: results_n100/metrics/           (kept apart from every other universe)

Everything else -- 17 features, TOP_N=8, BUFFER=16, HORIZON=REBAL=20, 32-day purge,
the same 10 seeds, SAFETY=0.98, CASH_YIELD=0.0 -- stays byte-identical to the other
universes, so only the universe differs and the comparison stays fair.

THE INDEX FILE IS NOT A CONSTITUENT
    NIFTY100.csv in that folder is the published cap-weighted index, not a stock.
    It is excluded from SYMBOLS_N100 BY NAME and must never enter the ranking
    universe.

    This is the exact mistake this project has already made once. An earlier
    make_final_chart_fair.py did glob("*.csv") over this very directory and swept
    NIFTY100.csv into the constituent basket as a 100th "stock", so the index was
    averaged together with its own members and the resulting line was labelled as
    the benchmark. The exclusion here is by name, never by a bare glob, and it is
    asserted rather than assumed.

    engine_core.build_panel takes a data_dir and does Path(_src).glob("*.csv"),
    which would sweep the index straight back in. build_panel lives in results/ and
    is not to be modified, so the exclusion is handled here: CONSTITUENTS_DIR_N100
    holds links to the 99 constituents only, and callers assert that the built
    panel's symbol set equals SYMBOLS_N100.

SURVIVORSHIP
    These 99 names are TODAY'S index members backfilled to the start of the
    backtest. Companies that were in the Nifty 100 during the window and were later
    dropped or delisted are absent entirely, so this universe carries the same
    survivorship bias as the other three. It is stated in the chart subtitle and in
    the forensic log header rather than left to be inferred. The survivorship switch
    (results/survivorship.py) is wired into the engine and stays at "static".
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Source data as delivered: 99 constituents plus the index, in one folder.
RAW_DATA_DIR_N100 = PROJECT_ROOT / "data" / "raw" / "nifty100_benchmark"

# The published cap-weighted index. Benchmark only, never a tradable name.
# Base 1-Jan-2003 = 1000; the file reads 1,008.00 on 2003-01-02, consistent with
# NSE's published methodology. Verified, not assumed.
INDEX_FILE_N100 = RAW_DATA_DIR_N100 / "NIFTY100.csv"
INDEX_NAME_N100 = "NIFTY100"

# Constituents only. Built by ensure_constituents_dir() below.
CONSTITUENTS_DIR_N100 = PROJECT_ROOT / "data" / "raw" / "N100_constituents"

# Outputs for the Nifty 100 universe -- separate folder, never mixed with the others
RESULTS_DIR_N100 = PROJECT_ROOT / "results_n100"
METRICS_DIR_N100 = RESULTS_DIR_N100 / "metrics"
METRICS_DIR_N100.mkdir(parents=True, exist_ok=True)

# The 99 tradable names, index excluded BY NAME, resolved from the source folder.
SYMBOLS_N100 = sorted(f.stem for f in RAW_DATA_DIR_N100.glob("*.csv")
                      if f.stem != INDEX_NAME_N100)


def ensure_constituents_dir():
    """Populate CONSTITUENTS_DIR_N100 with links to the 99 constituent CSVs.

    build_panel globs a directory, so the only way to feed it a filtered universe
    without editing results/ is to hand it a directory that already excludes the
    index. Links, not copies: the data keeps a single source of truth.
    Returns the directory.
    """
    CONSTITUENTS_DIR_N100.mkdir(parents=True, exist_ok=True)
    wanted = set(SYMBOLS_N100)
    for link in CONSTITUENTS_DIR_N100.glob("*.csv"):        # drop anything stale
        if link.stem not in wanted:
            link.unlink()
    for sym in SYMBOLS_N100:
        link = CONSTITUENTS_DIR_N100 / f"{sym}.csv"
        if not link.exists():
            link.symlink_to(RAW_DATA_DIR_N100 / f"{sym}.csv")
    present = sorted(f.stem for f in CONSTITUENTS_DIR_N100.glob("*.csv"))
    assert present == SYMBOLS_N100, "constituents directory does not match SYMBOLS_N100"
    assert INDEX_NAME_N100 not in present, "the index leaked into the constituent set"
    return CONSTITUENTS_DIR_N100
