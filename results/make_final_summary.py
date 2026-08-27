"""
make_final_summary.py -- summary table for the FINAL system.
Only the current final lines: v2, v1 and the references. No rejected variants.
Every number is read from the actual output files.
"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, config74

M58, M74 = Path(config.METRICS_DIR), Path(config74.METRICS_DIR_74)
fair = pd.read_csv(M58 / "fair_comparison_table.csv")

# fair table row -> (variant, line)
meta = {
 "58 v2 (breadth)":   ("FINAL_system", "58 v2"),
 "58 v1 (inv-vol)":   ("FINAL_system", "58 v1"),
 "74 v2 (breadth)":   ("FINAL_system", "74 v2"),
 "74 v1 (inv-vol)":   ("FINAL_system", "74 v1"),
 # Labels follow make_final_chart_fair.py, which renamed these when the benchmark
 # was corrected. "Nifty100" used to be an equal-weighted basket of 99 constituents
 # -- not the Nifty 100, which is cap-weighted -- so the row now says which index it
 # actually is, and the buy&hold rows say they are equal-weight universe baskets.
 "58 buy&hold (equal-weight universe)":   ("REFERENCE", "58 buy&hold"),
 "74 buy&hold (equal-weight universe)":   ("REFERENCE", "74 buy&hold"),
 "NIFTY100 (cap-weighted index, 58 win)": ("REFERENCE", "NIFTY100 58win"),
 "NIFTY100 (cap-weighted index, 74 win)": ("REFERENCE", "NIFTY100 74win"),
}

rows = []
for _, r in fair.iterrows():
    name = str(r["Strategy"])
    if name not in meta:
        continue
    variant, line = meta[name]
    dd = float(r["MaxDD%"])
    rows.append({
        "variant": variant,
        "line": line,
        "CAGR%": round(float(r["CAGR%"]), 2),
        "Sharpe": round(float(r["Sharpe"]), 2),
        "MaxDD%": round(dd, 2),
        "Calmar": round(float(r["CAGR%"]) / abs(dd), 2) if dd != 0 else "",
        "Invested%": round(float(r["AvgInvested%"]), 1),
        "Cash%": round(float(r["AvgCash%"]), 1),
        "CAGR_per_InvestedCapital%": round(float(r["CAGR_per_InvestedCapital%"]), 2),
    })

order = ["58 v2", "58 v1", "74 v2", "74 v1",
         "58 buy&hold", "74 buy&hold", "Nifty100 58win", "Nifty100 74win"]
df = pd.DataFrame(rows)
df["_o"] = df["line"].map({k: i for i, k in enumerate(order)})
df = df.sort_values("_o").drop(columns="_o").reset_index(drop=True)

print("=" * 100)
print("FINAL SYSTEM  |  Rs 10L  |  2019 - Jun'26 (58) / Dec'25 (74)  |  after TC, before tax")
print("=" * 100)
print(df.to_string(index=False))
print("=" * 100)

out = M58 / "FINAL_SUMMARY_TABLE.csv"
df.to_csv(out, index=False)
print(f"\nsaved -> {out}")
