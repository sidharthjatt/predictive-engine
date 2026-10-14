"""
year_by_year.py -- calendar-year and sub-period returns of named cells against the
equal-weight basket and the NSE index.

    ./venv/bin/python tools/year_by_year.py --cells nifty200:v3,nifty200:v1,midcap100:v1

Reads only existing artefacts. For each cell, under pit, tradeable, tax on and under
static, tradeable, tax on (cadence 20):

    cell     the arm's column of v34_equity<sfx>.csv
    basket   the "buyhold" column of the same file: the equal-weight basket of that
             universe construction, untaxed, rebalanced daily
    index    the close of the universe's own NSE index file (a price index),
             forward-filled onto the same dates

A calendar year's return runs from the previous year's last close in the window (the
window's first value for its first year) to the year's last close; 2026 ends on
2026-05-29. Sub-periods: 2019-01-01 to 2022-12-30 and 2023-01-02 to 2026-05-29, as
CAGR. Writes diagnostics/year_by_year_<date>.csv and prints the tables.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd

import arms.registry as arm_reg
import config
from config import read_table
from universes.registry import REGISTRY

SETTINGS = (("pit, tradeable, tax on", "_tradeable_tax_pit"),
            ("static, tradeable, tax on", "_tradeable_tax"))
HALVES = (("2019-01-01 to 2022-12-30", "2019-01-01", "2022-12-30"),
          ("2023-01-02 to 2026-05-29", "2023-01-02", "2026-05-29"))


def cagr(s):
    y = (s.index[-1] - s.index[0]).days / 365.25
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1) * 100


def yearly(s):
    out, prev = {}, s.iloc[0]
    for y, g in s.groupby(s.index.year):
        out[int(y)] = (g.iloc[-1] / prev - 1) * 100
        prev = g.iloc[-1]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    cells = [tuple(c.split(":")) for c in ap.parse_args().cells.split(",") if c.strip()]
    rows = []
    for tag, arm in cells:
        u = REGISTRY[tag]
        idx = (config.read_price_csv(u.index_file)[["date", "close"]].dropna()
               .set_index("date")["close"].sort_index())
        for setting, sfx in SETTINGS:
            eq = read_table(Path(u.metrics_dir) / f"v34_equity{sfx}.csv",
                            parse_dates=["date"]).set_index("date")
            cell = eq[arm_reg.ARMS[arm].equity_column]
            bask = eq["buyhold"]
            ix = idx.reindex(eq.index.union(idx.index)).ffill().reindex(eq.index)
            yc, yb, yi = yearly(cell), yearly(bask), yearly(ix)
            for y in yc:
                rows.append({"universe": tag, "arm": arm, "setting": setting, "period": str(y),
                             "cell": yc[y], "basket": yb[y], "index": yi[y],
                             "cell_minus_basket": yc[y] - yb[y], "cell_minus_index": yc[y] - yi[y]})
            for name, a, b in HALVES:
                c, bb, ii = (cagr(x.loc[a:b]) for x in (cell, bask, ix))
                rows.append({"universe": tag, "arm": arm, "setting": setting,
                             "period": f"CAGR {name}", "cell": c, "basket": bb, "index": ii,
                             "cell_minus_basket": c - bb, "cell_minus_index": c - ii})
    df = pd.DataFrame(rows)
    out = ROOT / "diagnostics" / f"year_by_year_{time.strftime('%Y%m%d')}.csv"
    # naming: axis-free -- one measurement of named cells; the settings are a column
    df.to_csv(out, index=False, float_format="%.4f")
    for (tag, arm, setting), g in df.groupby(["universe", "arm", "setting"], sort=False):
        yrs = g[~g.period.str.startswith("CAGR")]
        print(f"\n{tag} {arm} -- {setting}")
        print(g[["period", "cell", "basket", "index", "cell_minus_basket", "cell_minus_index"]]
              .to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        print(f"  years above the basket: {int((yrs.cell_minus_basket > 0).sum())} of {len(yrs)}; "
              f"above the index: {int((yrs.cell_minus_index > 0).sum())} of {len(yrs)}")
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
