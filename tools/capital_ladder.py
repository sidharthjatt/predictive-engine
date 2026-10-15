"""
capital_ladder.py -- named cells at several starting capitals, from their run artefacts.

    ./venv/bin/python tools/capital_ladder.py --cells nifty200:v3,nifty200:v1,midcap100:v1 \\
        --capitals 500000,1000000,2500000,5000000,10000000,20000000,50000000

Reads the artefacts of `run.py --survivorship pit --profile tradeable --tax on
--capital C [--impact K] [--cap F]` runs (cadence 20, no --dd), already made; it
runs nothing. --impacts and --pcaps (default 0 and 1.0, the tradeable defaults)
add those axes to the grid. Per cell, capital, k and cap:

    cagr, maxdd           the arm's row of v34_comparison<sfx>.csv
    cagr_minus_basket     minus that file's "buy & hold equal-weight" CAGR
    slippage, charges     COSTS_<tag>.csv, summed over every fill
    impact                COSTS_<tag>.csv impact_rs, summed; 0 when the run had k 0
    tax                   COST_TAX_YEARS_<tag>.csv, total_tax summed
    capped_fills          daily_skipped rows with reason "participation cap"
    cash_short_skips      daily_skipped rows with reason "cash short ..."
    share_too_dear        daily_skipped rows with reason "qty < 1 after sizing": one
                          share cost more than the position's rupee target
    avg_cash_pct          mean of daily_summary cash_pct
    max_order_pct_adv     the largest fill as a percent of that stock's mean daily
                          traded value (close x volume) over the 20 sessions before
                          the fill, from the universe's raw pit price files

Writes diagnostics/capital_ladder_<date>.csv and prints it.
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
from universes.registry import REGISTRY, pit_variant


def adv_value(raw_dir, sym, cache={}):
    """Series: mean close x volume over the 20 sessions before each date."""
    if sym not in cache:
        d = config.read_price_csv(Path(raw_dir) / f"{sym}.csv").set_index("date").sort_index()
        tv = (d["close"] * d["volume"])
        cache[sym] = tv.rolling(20).mean().shift(1)
    return cache[sym]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    ap.add_argument("--capitals", required=True)
    ap.add_argument("--impacts", default="0")
    ap.add_argument("--pcaps", default="1.0")
    a = ap.parse_args()
    cells = [tuple(c.split(":")) for c in a.cells.split(",")]
    caps = [int(x) for x in a.capitals.split(",")]
    ks = [float(x) for x in a.impacts.split(",")]
    pcs = [float(x) for x in a.pcaps.split(",")]
    import capital_axis, impact_axis, pcap_axis, profiles
    profiles.set_selection("tradeable")

    def tail(cap, k, pc):
        """The capital, impact and cap suffixes, from the axes' own composers."""
        capital_axis.set_selection(cap)
        impact_axis.set_selection(k)
        pcap_axis.set_selection(pc)
        t = capital_axis.suffix() + impact_axis.suffix() + pcap_axis.suffix()
        capital_axis.set_selection(None); impact_axis.set_selection(None)
        pcap_axis.set_selection(None)
        return t
    by_u = {}
    for t, arm in cells:
        by_u.setdefault(t, []).append(arm)
    rows = []
    for tag, arms in by_u.items():
        u = pit_variant(REGISTRY[tag])
        M = Path(u.metrics_dir)
        sel = "_" + "_".join(x for x in arm_reg.ARMS if x in arms)
        for pc, k, cap in ((pc, k, cap) for pc in pcs for k in ks for cap in caps):
            cs = tail(cap, k, pc)
            # the published run (every axis at its default) holds all four arms and
            # has no selection suffix
            comp_f = M / (f"v34_comparison_tradeable_tax_pit.csv" if cs == ""
                          else f"v34_comparison{sel}_tradeable_tax_pit{cs}.csv")
            comp = read_table(comp_f).set_index("Config")
            basket = float(comp.loc["buy & hold equal-weight", "CAGR%"])
            for arm in arms:
                A = arm_reg.ARMS[arm]
                at = f"{tag}_{arm}_tradeable_tax_pit{cs}"
                costs = read_table(M / f"COSTS_{at}.csv", parse_dates=["date"])
                years = read_table(M / f"COST_TAX_YEARS_{at}.csv")
                sk = read_table(M / f"daily_skipped_{at}.csv")
                sm = read_table(M / f"daily_summary_{at}.csv")
                best, where = 0.0, ""
                for r in costs.itertuples(index=False):
                    adv = adv_value(u.raw_data_dir, r.symbol).get(r.date, float("nan"))
                    if adv == adv and adv > 0:
                        pct = r.qty * r.fill_price / adv * 100
                        if pct > best:
                            best, where = pct, f"{r.symbol} {r.side} {r.date.date()}"
                c = comp.loc[A.label]
                rows.append({
                    "universe": tag, "arm": arm, "capital": cap, "impact_k": k, "pcap": pc,
                    "cagr": float(c["CAGR%"]), "maxdd": float(c["MaxDD%"]),
                    "cagr_minus_basket": float(c["CAGR%"]) - basket,
                    "slippage": float(costs["slippage_rs"].sum()),
                    "charges": float(costs["charges_total"].sum()),
                    "impact": float(costs["impact_rs"].sum()) if "impact_rs" in costs else 0.0,
                    "tax": float(years["total_tax"].sum()),
                    "capped_fills": int((sk["reason"] == "participation cap").sum()),
                    "cash_short_skips": int(sk["reason"].astype(str).str.startswith("cash short").sum()),
                    "share_too_dear": int((sk["reason"] == "qty < 1 after sizing").sum()),
                    "avg_cash_pct": float(sm["cash_pct"].mean()),
                    "max_order_pct_adv": best, "max_order": where})
    df = pd.DataFrame(rows)
    out = ROOT / "diagnostics" / f"capital_ladder_{time.strftime('%Y%m%d')}.csv"
    # naming: axis-free -- one measurement over named cells; capital is a column
    df.to_csv(out, index=False, float_format="%.4f")
    print(df.to_string(index=False))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
