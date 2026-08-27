"""
run_all.py -- the complete pipeline (58 + 74 + benchmark), from scratch, in one command.
=================================================================================
    python3 run_all.py              # uses cache if present (fast)
    python3 run_all.py --fresh      # everything from scratch (clears cache)

On a new machine or from nothing: `python3 run_all.py --fresh`
This rebuilds both universes, the benchmark comparison, and every chart and CSV.

ORDER:
  === 58 UNIVERSE ===
  1.  build_scores       -> 58 scores (SLOW ~40-65min)
  2.  engine_core        -> v1 + validation + leakage checks
  3.  engine_v2_final    -> v2 FINAL (breadth)
  4.  diagnose_decay     -> period breakdown
  5.  validate_breadth   -> breadth robustness
  6.  reality_check      -> real-money P&L, hit rate
  7.  per-stock charts (58)
  === 74 UNIVERSE ===
  8.  build_scores74     -> 74 scores (SLOW ~27min)
  9.  engine_v2_final74  -> 74 v2 FINAL
  10. make_stats_both    -> 74 trade stats + per-stock signals
  === MIDCAP150 UNIVERSE (third universe) ===
  build_scores_mid   -> MidCap150 scores (SLOW)
  engine_v2_final_mid-> MidCap150 v2 FINAL
  make_mid_audit     -> MidCap150 daily audit CSVs
  make_mid_chart     -> MidCap150 chart + cap-weighted index benchmark
  === BENCHMARK + FINAL ===
  11. make_cash_series      -> cash series (58 + 74)
  12. make_daily_audit      -> 58/74 daily audit CSVs  <- MUST precede step 13
  13. make_final_chart_fair -> Nifty100 benchmark + final 3-panel chart + fair table
  14. make_final_summary    -> FINAL summary table
  15. make_daily_log        -> forensic daily text log
  16. nt_export_scores      -> Nautilus score parquets

ORDERING IS LOAD-BEARING. A consumer must never be listed before its producer.
run_all.py enforces the non-obvious cases itself -- see REQUIRED_INPUTS below,
which fails with the missing filename and the owing step instead of a pandas
FileNotFoundError.
"""
import sys, subprocess, time, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent
R = ROOT / "results"
TMP = Path("/tmp")
FRESH = "--fresh" in sys.argv

# caches: both /tmp and the permanent copies
CACHE_TMP = [TMP / "v5_expanding.csv", TMP / "raw_panel_20.csv",
             TMP / "v74_expanding.csv", TMP / "raw_panel74_20.csv",
             TMP / "v_mid_expanding.csv", TMP / "raw_panel_mid_20.csv",
             TMP / "v_n100_expanding.csv", TMP / "raw_panel_n100_20.csv"] + \
            [TMP / f"FINAL_seed{i}.csv" for i in range(3)] + \
            [TMP / f"breadth_seed{i}.csv" for i in range(3)] + \
            [TMP / f"prune_{t}.csv" for t in ("all", "pruned", "random")]
CACHE_PERM = [R / "metrics" / "v5_expanding_cache.csv",
              R / "metrics" / "raw_panel_cache.csv",
              ROOT / "results74" / "metrics" / "v74_expanding_cache.csv",
              ROOT / "results74" / "metrics" / "raw_panel74_cache.csv",
              ROOT / "results_mid" / "metrics" / "v_mid_expanding_cache.csv",
              ROOT / "results_mid" / "metrics" / "raw_panel_mid_cache.csv",
              ROOT / "results_n100" / "metrics" / "v_n100_expanding_cache.csv",
              ROOT / "results_n100" / "metrics" / "raw_panel_n100_cache.csv"]

# ---------------------------------------------------------------------------
# INPUT GUARD -- ordering bugs must fail by name, not as a pandas traceback
# ---------------------------------------------------------------------------
# Every entry is: consumer script -> [(file it reads, the step that writes it)].
#
# WHY THIS EXISTS. make_final_chart_fair.py read daily_trades_58.csv, which was
# produced two steps LATER. The pipeline appeared to work for months because the
# file survived in metrics/ from the previous run; the first run against a truly
# empty metrics/ died with a bare FileNotFoundError raised inside pandas, naming
# a path but not the step that owed it.
#
# ONLY NON-OBVIOUS DEPENDENCIES ARE LISTED -- the ones a reader would not catch
# by grepping, because the filename and the read() are in different places
# (helpers like tc_from_log() and before_tc() take a path argument, so the
# literal never appears next to a read_csv call).
#
# THIS GUARD DOES NOT MAKE ANY CONSUMER TOLERANT OF A MISSING FILE. A missing
# input is still fatal. It only replaces the traceback with a sentence that says
# which file is missing and who should have written it.
REQUIRED_INPUTS = {
    "make_final_chart_fair.py": [
        (R / "metrics" / "daily_trades_58.csv",
         "STEP 12 make_daily_audit.py (tag 58)"),
        (ROOT / "results74" / "metrics" / "daily_trades_74.csv",
         "STEP 12 make_daily_audit.py (tag 74)"),
        (R / "metrics" / "daily_trades_v1_58.csv",
         "STEP 3 engine_v2_final.py"),
        (ROOT / "results74" / "metrics" / "daily_trades_v1_74.csv",
         "STEP 9 engine_v2_final74.py"),
        (R / "metrics" / "cash_series_58.csv", "STEP 11 make_cash_series.py"),
        (ROOT / "results74" / "metrics" / "cash_series_74.csv",
         "STEP 11 make_cash_series.py"),
    ],
    "make_mid_chart.py": [
        (ROOT / "results_mid" / "metrics" / "daily_trades_mid.csv",
         "STEP 10c make_mid_audit.py"),
        (ROOT / "results_mid" / "metrics" / "daily_trades_v1_mid.csv",
         "STEP 10b engine_v2_final_mid.py"),
    ],
    "make_n100_chart.py": [
        (ROOT / "results_n100" / "metrics" / "daily_trades_n100.csv",
         "STEP 10g make_n100_audit.py"),
        (ROOT / "results_n100" / "metrics" / "daily_trades_v1_n100.csv",
         "STEP 10f engine_v2_final_n100.py"),
    ],
    "make_combined_n100_mid.py": [
        (ROOT / "results_mid" / "metrics" / "daily_trades_mid.csv",
         "STEP 10c make_mid_audit.py"),
        (ROOT / "results_n100" / "metrics" / "daily_trades_n100.csv",
         "STEP 10g make_n100_audit.py"),
    ],
    "make_final_summary.py": [
        (R / "metrics" / "fair_comparison_table.csv",
         "STEP 13 make_final_chart_fair.py"),
    ],
}


# Execution order, declared once so the static checker can read it. run() asserts
# every script it is handed appears here, so this list cannot silently drift out of
# step with main(). Steps 1/8/10a/10e are skipped at runtime when their panel is
# cached; that does not change the ORDER, which is what the checker reasons about.
PIPELINE_ORDER = [
    ("STEP 0", "make_trading_calendar.py"),
    ("STEP 1", "build_scores.py"),
    ("STEP 2", "engine_core.py"),
    ("STEP 3", "engine_v2_final.py"),
    ("STEP 4", "diagnose_decay.py"),
    ("STEP 5", "validate_breadth.py"),
    ("STEP 6", "reality_check.py"),
    ("STEP 7", "make_per_stock_charts.py"),
    ("STEP 7b", "make_combined_all.py"),
    ("STEP 7c", "make_final_table.py"),
    ("STEP 7d", "make_charts.py"),
    ("STEP 7e", "make_stock_chart.py"),
    ("STEP 7f", "make_combined_portfolio.py"),
    ("STEP 7g", "export_feature_docs.py"),
    ("STEP 8", "build_scores74.py"),
    ("STEP 9", "engine_v2_final74.py"),
    ("STEP 10", "make_stats_both.py"),
    ("STEP 10a", "build_scores_mid.py"),
    ("STEP 10b", "engine_v2_final_mid.py"),
    ("STEP 10c", "make_mid_audit.py"),
    ("STEP 10d", "make_mid_chart.py"),
    ("STEP 10e", "build_scores_n100.py"),
    ("STEP 10f", "engine_v2_final_n100.py"),
    ("STEP 10g", "make_n100_audit.py"),
    ("STEP 10h", "make_n100_chart.py"),
    ("STEP 10i", "make_combined_n100_mid.py"),
    ("STEP 11", "make_cash_series.py"),
    ("STEP 12", "make_daily_audit.py"),
    ("STEP 13", "make_final_chart_fair.py"),
    ("STEP 14", "make_final_summary.py"),
    ("STEP 15", "make_daily_log.py"),
    ("STEP 16", "nt_export_scores.py"),
]
_PIPELINE_SCRIPTS = {s for _, s in PIPELINE_ORDER}


def check_inputs(label, script):
    """Fail by name before a step runs, rather than from inside pandas."""
    missing = [(f, who) for f, who in REQUIRED_INPUTS.get(Path(script).name, [])
               if not f.exists()]
    if not missing:
        return
    print("\n" + "!" * 90)
    print(f"PIPELINE ORDERING ERROR -- cannot start {label}")
    print("!" * 90)
    print(f"\n  {Path(script).name} needs {len(missing)} file(s) that do not exist:\n")
    for f, who in missing:
        print(f"    MISSING  {f.relative_to(ROOT)}")
        print(f"      writer {who}")
    print("\n  Each of these is written by another pipeline step. If that step is")
    print("  listed AFTER this one in run_all.py, the order is wrong and the step")
    print("  must be moved earlier -- not made tolerant of the missing file.")
    print("  If the step ran and the file is still absent, that step failed quietly.")
    print("!" * 90, flush=True)
    sys.exit(1)


def run(label, script, cwd=None):
    print("\n" + "=" * 90)
    print(f">>> {label}")
    print("=" * 90, flush=True)
    # keeps PIPELINE_ORDER honest: a step added to main() but not to the list
    # would otherwise be invisible to the static ordering check.
    if Path(script).name not in _PIPELINE_SCRIPTS:
        print(f"\n!!! {Path(script).name} is not in PIPELINE_ORDER. Add it there,")
        print("    in its execution position, so the ordering check can see it.")
        sys.exit(1)
    check_inputs(label, script)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(R / script)], cwd=str(cwd or ROOT))
    if r.returncode != 0:
        print(f"\n!!! {script} FAILED (exit {r.returncode}). Stopping.")
        sys.exit(1)
    print(f"    [{label} done in {(time.time()-t0)/60:.1f} min]")

def restore_cache_to_tmp():
    """Restore permanent copies into /tmp so scripts run without rebuilding."""
    pairs = [("v5_expanding_cache.csv", "v5_expanding.csv", R/"metrics"),
             ("raw_panel_cache.csv", "raw_panel_20.csv", R/"metrics"),
             ("v74_expanding_cache.csv", "v74_expanding.csv", ROOT/"results74"/"metrics"),
             ("raw_panel74_cache.csv", "raw_panel74_20.csv", ROOT/"results74"/"metrics"),
             ("v_mid_expanding_cache.csv", "v_mid_expanding.csv", ROOT/"results_mid"/"metrics"),
             ("raw_panel_mid_cache.csv", "raw_panel_mid_20.csv", ROOT/"results_mid"/"metrics"),
             ("v_n100_expanding_cache.csv", "v_n100_expanding.csv", ROOT/"results_n100"/"metrics"),
             ("raw_panel_n100_cache.csv", "raw_panel_n100_20.csv", ROOT/"results_n100"/"metrics")]
    for perm_name, tmp_name, folder in pairs:
        perm = folder / perm_name
        if perm.exists() and not (TMP / tmp_name).exists():
            shutil.copy(perm, TMP / tmp_name)
            print(f"    restored {tmp_name} from permanent cache")

def main():
    t_start = time.time()
    # Stated once at the top of every pipeline run, so the log itself records which
    # universe construction produced the numbers below it.
    sys.path.insert(0, str(R))
    import survivorship as sv
    print(f"SURVIVORSHIP: {sv.describe_state()}\n")
    if FRESH:
        print("--fresh: deleting ALL cached scores (tmp + permanent)...")
        for c in CACHE_TMP + CACHE_PERM:
            if c.exists():
                c.unlink()
        print("cache cleared. Full rebuild (~3 hours).\n")
    else:
        print("normal mode: using cache if available. (--fresh for full scratch)\n")
        restore_cache_to_tmp()

    # STATIC ORDERING CHECK -- runs before any step, costs milliseconds.
    # Derives consumer/producer edges from the source rather than from the
    # hand-maintained REQUIRED_INPUTS list above, and fails on any inversion.
    # REQUIRED_INPUTS still earns its place: it produces a better message at the
    # exact moment of failure, and it catches a producer that ran but wrote
    # nothing. This catches the case nobody remembered to add to it.
    import check_pipeline_order as cpo
    cpo.enforce(PIPELINE_ORDER,
                covered={f.name for lst in REQUIRED_INPUTS.values() for f, _ in lst})

    # ===== TRADING CALENDAR (must precede every panel build) =====
    # build_panel refuses to run without it, so this cannot be skipped or bypassed.
    run("STEP 0  NSE trading calendar (derived from the 58 universe)",
        "make_trading_calendar.py")

    # ===== 58 UNIVERSE =====
    if not (TMP / "v5_expanding.csv").exists():
        run("STEP 1  Build 58 scores (SLOW)", "build_scores.py")
    else:
        print(">>> STEP 1  58 scores cached (skip)")
    run("STEP 2  Engine core (v1 + validation + leakage)", "engine_core.py")
    run("STEP 3  Engine v2 FINAL (breadth)", "engine_v2_final.py")
    run("STEP 4  Decay diagnostic", "diagnose_decay.py")
    run("STEP 5  Validate breadth", "validate_breadth.py")
    run("STEP 6  Reality check", "reality_check.py")
    run("STEP 7  Per-stock charts (58)", "make_per_stock_charts.py")
    run("STEP 7b Combined per-stock (58)", "make_combined_all.py")
    run("STEP 7c Final table chart", "make_final_table.py")
    run("STEP 7d Equity chart", "make_charts.py")
    run("STEP 7e All-stocks overview", "make_stock_chart.py")
    run("STEP 7f Portfolio combined", "make_combined_portfolio.py")
    run("STEP 7g Feature docs (dictionary + panel sample)", "export_feature_docs.py")

    # ===== 74 UNIVERSE =====
    if not (TMP / "v74_expanding.csv").exists():
        run("STEP 8  Build 74 scores (SLOW)", "build_scores74.py")
    else:
        print(">>> STEP 8  74 scores cached (skip)")
    run("STEP 9  Engine v2 FINAL 74", "engine_v2_final74.py")
    run("STEP 10 Trade stats + per-stock (74)", "make_stats_both.py")

    # ===== MIDCAP150 UNIVERSE (third universe) =====
    if not (TMP / "v_mid_expanding.csv").exists():
        run("STEP 10a Build MidCap150 scores (SLOW)", "build_scores_mid.py")
    else:
        print(">>> STEP 10a MidCap150 scores cached (skip)")
    run("STEP 10b Engine v2 FINAL MidCap150", "engine_v2_final_mid.py")
    run("STEP 10c Daily audit CSVs (MidCap150)", "make_mid_audit.py")
    run("STEP 10d MidCap150 chart + cap-weighted index", "make_mid_chart.py")

    # ===== NIFTY 100 UNIVERSE (fourth universe) =====
    if not (TMP / "v_n100_expanding.csv").exists():
        run("STEP 10e Build Nifty 100 scores (SLOW)", "build_scores_n100.py")
    else:
        print(">>> STEP 10e Nifty 100 scores cached (skip)")
    run("STEP 10f Engine v2 FINAL Nifty 100", "engine_v2_final_n100.py")
    run("STEP 10g Daily audit CSVs (Nifty 100)", "make_n100_audit.py")
    run("STEP 10h Nifty 100 chart + cap-weighted index", "make_n100_chart.py")
    run("STEP 10i Combined chart: Nifty 100 + MidCap150", "make_combined_n100_mid.py")

    # ===== BENCHMARK + FINAL CHART =====
    run("STEP 11 Cash series (58 + 74)", "make_cash_series.py")

    # ORDERING, AND WHY IT IS THIS WAY.
    #   make_daily_audit.py writes daily_trades_58.csv and daily_trades_74.csv.
    #   make_final_chart_fair.py READS both, through tc_from_log(), to get the
    #   dated transaction costs for the v2 arms.
    #
    #   The audit used to run at STEP 14, AFTER the chart. That never worked from
    #   scratch: it only ever succeeded because the two CSVs were left behind by a
    #   previous run and were still sitting in metrics/ when the chart ran. The
    #   first genuinely empty metrics/ exposed it as a FileNotFoundError from
    #   inside pandas at STEP 12.
    #
    #   The mid and n100 universes already had this right -- make_mid_audit runs
    #   at 10c before make_mid_chart at 10d, and make_n100_audit at 10g before
    #   make_n100_chart at 10h. This makes 58/74 match that pattern.
    #
    #   The audit depends only on v2FINAL_equity.csv (STEPS 3 and 9) and the /tmp
    #   panels, so it is free to move anywhere after STEP 9.
    run("STEP 12 Daily audit CSVs (58 + 74: holdings/trades/ranking)",
        "make_daily_audit.py")
    run("STEP 13 Nifty100 benchmark + final chart + fair table",
        "make_final_chart_fair.py")
    run("STEP 14 FINAL summary table", "make_final_summary.py")
    run("STEP 15 Forensic daily text log", "make_daily_log.py")

    # save permanent caches for next time
    print("\nSaving permanent caches...")
    pairs = [("v5_expanding.csv", R/"metrics"/"v5_expanding_cache.csv"),
             ("raw_panel_20.csv", R/"metrics"/"raw_panel_cache.csv"),
             ("v74_expanding.csv", ROOT/"results74"/"metrics"/"v74_expanding_cache.csv"),
             ("raw_panel74_20.csv", ROOT/"results74"/"metrics"/"raw_panel74_cache.csv"),
             ("v_mid_expanding.csv", ROOT/"results_mid"/"metrics"/"v_mid_expanding_cache.csv"),
             ("raw_panel_mid_20.csv", ROOT/"results_mid"/"metrics"/"raw_panel_mid_cache.csv"),
             ("v_n100_expanding.csv", ROOT/"results_n100"/"metrics"/"v_n100_expanding_cache.csv"),
             ("raw_panel_n100_20.csv", ROOT/"results_n100"/"metrics"/"raw_panel_n100_cache.csv")]
    for tmp_name, perm in pairs:
        if (TMP / tmp_name).exists():
            shutil.copy(TMP / tmp_name, perm)
    print("caches saved (restart-proof).")

    # AFTER the caches are persisted, not before: nt_export_scores.py reads the
    # PERMANENT panels, which do not exist on a fresh run until the block above
    # copies them. Placing this earlier crashed the pipeline with
    # "v5_expanding_cache.csv missing -- run run_all.py first".
    #
    # The parquets are derived from the score panels and go STALE the moment those
    # are rebuilt. Leaving this out of the pipeline once made nt_verify report NOT
    # VERIFIED on the 58 and mid with 91 and 92 symbol-set differences, entirely
    # because the port was reading last run's scores.
    run("STEP 16 Export Nautilus score parquets (58 + 74 + mid)",
        str(ROOT / "nautilus" / "nt_export_scores.py"))

    print("\n" + "=" * 90)
    print(f"ALL DONE in {(time.time()-t_start)/60:.1f} min.")
    print("58 outputs:  results/metrics/")
    print("74 outputs:  results74/metrics/")
    print("Final chart: results/metrics/chart_FINAL_58_74_N100.png")
    print("=" * 90)

if __name__ == "__main__":
    main()
