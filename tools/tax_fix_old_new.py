"""
tax_fix_old_new.py -- every tax-on cell before and after the tax-ledger fix of 2026-10-14.

    ./venv/bin/python tools/tax_fix_old_new.py --old DIR

DIR holds results_<tag>/metrics/ copies of the tax-on artefacts taken before the
rerun. The new figures are the live metrics directories. For every registered
universe, arm v1-v4, cadence 20, static and pit, research and tradeable, tax on:

    total_tax     sum of total_tax in COST_TAX_YEARS_<tag>.csv
    cagr, maxdd, final_equity   the arm's row of v34_comparison<sfx>.csv

Writes diagnostics/tax_ledger_fix_20261014.csv and prints the summary.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd

import arms.registry as arm_reg
from config import read_table
from universes.registry import REGISTRY

SETTINGS = (("static", "research", "_tax"), ("static", "tradeable", "_tradeable_tax"),
            ("pit", "research", "_tax_pit"), ("pit", "tradeable", "_tradeable_tax_pit"))
OUT = ROOT / "diagnostics" / "tax_ledger_fix_20261014.csv"


def figures(M, tag, arm, sfx):
    a = arm_reg.ARMS[arm]
    ct = tag if arm == "v2" else f"{tag}_{arm}"
    years = read_table(M / f"COST_TAX_YEARS_{ct}{sfx}.csv")
    c = read_table(M / f"v34_comparison{sfx}.csv").set_index("Config").loc[a.label]
    return {"total_tax": float(years["total_tax"].sum()), "cagr": float(c["CAGR%"]),
            "maxdd": float(c["MaxDD%"]), "final_equity": float(c["FinalEquity"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    old_root = Path(ap.parse_args().old)
    rows = []
    for tag, u in REGISTRY.items():
        new_M = Path(u.metrics_dir)
        old_M = old_root / new_M.relative_to(ROOT)
        for surv, profile, sfx in SETTINGS:
            for arm in arm_reg.ARMS:
                o, n = figures(old_M, tag, arm, sfx), figures(new_M, tag, arm, sfx)
                rows.append({"universe": tag, "arm": arm, "survivorship": surv,
                             "profile": profile,
                             **{f"{k}_old": o[k] for k in o}, **{f"{k}_new": n[k] for k in n},
                             "tax_change": n["total_tax"] - o["total_tax"],
                             "cagr_change": n["cagr"] - o["cagr"],
                             "maxdd_change": n["maxdd"] - o["maxdd"],
                             "final_equity_change": n["final_equity"] - o["final_equity"]})
    df = pd.DataFrame(rows)
    # naming: axis-free -- one dated comparison over every tax-on cell, the settings are columns
    df.to_csv(OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(df)} cells")
    for k in ("tax_change", "cagr_change", "maxdd_change", "final_equity_change"):
        print(f"  {k:<20} min {df[k].min():>14,.2f}  median {df[k].median():>14,.2f}  "
              f"max {df[k].max():>14,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
