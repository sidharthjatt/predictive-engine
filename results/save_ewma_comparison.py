"""
save_ewma_comparison.py -- EWMA vs rolling volatility test record.
Numbers come from three full --fresh runs (logs: run_all_fresh_log, run_all_ewma_log,
run_all_ewma2_log). This file is a record only; it computes nothing.

WHY THIS WRITES TO experiments/ AND NOT results/metrics/
    It used to write to config.METRICS_DIR. That was wrong, and it nearly cost the
    project the record: results*/metrics/ is owned by the pipeline and is rebuilt
    from scratch on every run, so a blanket "clear everything under results*/metrics/"
    is a reasonable instruction that would silently destroy a document no run can
    regenerate the reasoning for. On 2026-08-22 exactly that happened, and
    ewma_vs_rolling_REPORT.txt was recovered only because a backup existed.

    A record is not a computation. Every output below is a hardcoded literal typed
    from three completed runs -- rerunning this script recomputes nothing, it only
    re-types what is already here. Records live in experiments/, which no pipeline
    step touches.

REFUSE-TO-OVERWRITE
    This script will NOT replace an existing output file. The copy on disk is the
    authoritative one and may have been edited or corrected by hand since it was
    generated; this file's literals are not a safe substitute for it. If an output
    already exists, the script reports it and exits without writing.

    To deliberately regenerate: delete the file yourself, then re-run.
"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

OUT_DIR = Path(__file__).resolve().parents[1] / "experiments"


def guard(paths):
    """Exit rather than overwrite any existing record."""
    existing = [p for p in paths if p.exists()]
    if existing:
        print("REFUSING TO WRITE. These records already exist on disk:")
        for p in existing:
            print(f"  {p}")
        print("\nThe copy on disk is authoritative. This script holds hardcoded")
        print("literals and regenerates no reasoning, so overwriting can only lose")
        print("information, never add it. Delete the file(s) by hand if you really")
        print("intend to regenerate, then re-run.")
        sys.exit(1)

rows = [
    # variant, line, CAGR, Sharpe, MaxDD, Calmar, deployed_CAGR
    ("A_rolling_std",          "58 v2", 18.80, 1.54, -16.63, 1.13, 29.12),
    ("A_rolling_std",          "58 v1", 24.14, 1.27, -32.88, 0.73, 24.14),
    ("A_rolling_std",          "74 v2", 16.94, 1.45, -17.02, 1.00, 26.24),
    ("A_rolling_std",          "74 v1", 19.42, 1.08, -29.90, 0.65, 19.42),
    ("B_ewma_0.94_0.97",       "58 v2", 15.54, 1.36, -18.20, 0.85, 25.43),
    ("B_ewma_0.94_0.97",       "58 v1", 18.63, 1.00, -36.82, 0.51, 18.63),
    ("B_ewma_0.94_0.97",       "74 v2", 13.83, 1.20, -19.24, 0.72, 20.51),
    ("B_ewma_0.94_0.97",       "74 v1", 16.41, 0.89, -39.95, 0.41, 16.41),
    ("C_ewma_matched_.952_.984","58 v2", 16.76, 1.45, -18.24, 0.92, 26.63),
    ("C_ewma_matched_.952_.984","58 v1", 20.06, 1.07, -39.00, 0.51, 20.06),
    ("C_ewma_matched_.952_.984","74 v2", 15.03, 1.28, -16.69, 0.90, 22.25),
    ("C_ewma_matched_.952_.984","74 v1", 18.44, 1.01, -36.76, 0.50, 18.44),
    ("REFERENCE",              "58 buy&hold",      18.65, 1.06, -39.80, 0.47, 18.65),
    ("REFERENCE",              "74 buy&hold",      23.97, 1.29, -38.29, 0.63, 23.97),
    ("REFERENCE",              "Nifty100 58win",   23.05, 1.29, -36.51, 0.63, 23.05),
    ("REFERENCE",              "Nifty100 74win",   25.04, 1.39, -36.51, 0.69, 25.04),
]
df = pd.DataFrame(rows, columns=["variant","line","CAGR%","Sharpe","MaxDD%","Calmar",
                                 "CAGR_per_InvestedCapital%"])

val = pd.DataFrame([
    ("A_rolling_std",           "PASS","PASS","PASS","PASS","4/4"),
    ("B_ewma_0.94_0.97",        "PASS","FAIL","FAIL","FAIL","1/4"),
    ("C_ewma_matched_.952_.984","PASS","FAIL","FAIL","FAIL","1/4"),
], columns=["variant","T1_baseline","T2_seed_robustness","T3_sub_period",
            "T4_param_sensitivity","score"])

out = OUT_DIR
out.mkdir(parents=True, exist_ok=True)
f_csv = out / "ewma_vs_rolling_metrics.csv"
f_val = out / "ewma_vs_rolling_validation.csv"
f_txt = out / "ewma_vs_rolling_REPORT.txt"
guard([f_csv, f_val, f_txt])

df.to_csv(f_csv, index=False)
val.to_csv(f_val, index=False)

txt = f"""EWMA vs ROLLING VOLATILITY -- TEST RECORD
=========================================
Request: use EWMA instead of rolling for vol_20 / vol_60, lambda 0.94.

WHY TWO EWMA VARIANTS WERE TESTED
  A single lambda on both windows makes vol_20 identical to vol_60
  (EWMA has no window -- only lambda), which would make vol_ratio a
  constant 1 and kill that feature. So two lambdas were needed.

  B) RiskMetrics pair 0.94 (daily) / 0.97 (monthly).
     Problem found afterwards: centre-of-mass = lambda/(1-lambda)
       0.94 -> 15.7 days   (was 20)
       0.97 -> 32.3 days   (was 60)  <-- long window silently halved
     So B changed weighting AND horizon at once -- not a clean test.

  C) Horizon-matched: lambda = W/(W+1)
       20 -> 0.9524 (CoM exactly 20d)
       60 -> 0.9836 (CoM exactly 60d)
     Same horizon as rolling, only the weighting changes. Clean test.

RESULT (both universes, full --fresh run each, ~142 min per run)
{df.to_string(index=False)}

INVERSE-VOL VALIDATION
{val.to_string(index=False)}

READING
  C improved on B (58 v2 Sharpe 1.36 -> 1.45), which confirms part of B's
  damage came from the shortened horizon. But C is still behind rolling on
  every metric on both universes except 74 MaxDD.

  The bigger issue is validation. With rolling, inverse-vol sizing passes
  seed robustness, sub-period split and window sensitivity. With either EWMA
  variant all three fail -- the sizing edge becomes seed- and window-dependent.

  Also, on deployed capital 74 v2 falls from 26.24% (rolling, above the
  25.04% benchmark) to 22.25% (EWMA, below it).

  Breadth validation passed in all three variants, so the loss is in the
  model's ranking, not in the exposure overlay.

DECISION
  Rolling std kept. EWMA is the better tool for risk measurement (that is
  what RiskMetrics designed it for), but here the features feed a
  cross-sectional ranking model, and the fixed-window definition appears to
  compare more cleanly across stocks.

  Logs: run_all_fresh_log.txt (A), run_all_ewma_log.txt (B),
        run_all_ewma2_log.txt (C)
"""
f_txt.write_text(txt)
print(txt)
print(f"\nSaved -> {f_csv}")
print(f"Saved -> {f_val}")
print(f"Saved -> {f_txt}")
