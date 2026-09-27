"""
cell_compare.py -- old against new for every cell, from two cell_table.py CSVs.

    ./venv/bin/python results/cell_compare.py OLD.csv NEW.csv OUT.csv

One row per (universe, arm, profile): each CAGR and gap column from both files and
their difference, plus sign_change_on and sign_change_last_day, True where the gap
against the investable taxed buy & hold has a different sign old and new.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import read_table  # noqa: E402  the one CSV/parquet reader

KEY = ["universe", "arm", "profile"]
COLS = ["cagr_off", "cagr_on", "cagr_last_day", "bh_reference", "bh_investable",
        "bh_investable_last_day", "gap_on", "gap_last_day"]


def compare(old, new):
    o = old.set_index(KEY)[COLS]
    n = new.set_index(KEY)[COLS]
    if set(o.index) != set(n.index):
        raise SystemExit("the two tables do not hold the same cells")
    n = n.loc[o.index]
    out = pd.DataFrame(index=o.index)
    for c in COLS:
        out[f"{c}_old"] = o[c]
        out[f"{c}_new"] = n[c]
        out[f"{c}_diff"] = (n[c] - o[c]).round(4)
    for g in ("gap_on", "gap_last_day"):
        out[f"sign_change_{g[4:]}"] = (o[g] > 0) != (n[g] > 0)
    return out.reset_index()


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    d = compare(read_table(argv[0]), read_table(argv[1]))
    d.to_csv(argv[2], index=False)
    print(f"wrote {argv[2]}: {len(d)} cells, gap sign changes: "
          f"headline {int(d.sign_change_on.sum())}, last day {int(d.sign_change_last_day.sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
