"""
leakage_check2_purge.py -- CHECK 2 of experiments/LEAKAGE_SPEC.txt.

Does the 32-day purge actually purge?

WHAT THE CODE DOES
    engine_core.score_monthly:413-415
        cut = p.loc[p.ym == ym, "date"].min() - pd.Timedelta(days=purge)
        tr  = (p["date"] <= cut) & p["y_rank"].notna()
    engine_core:189
        d["fwd_ret"] = d["close"].shift(-horizon) / d["close"] - 1

    PURGE = 32 is CALENDAR days. HORIZON = 20 is TRADING ROWS. The units do not
    match, so the realised margin is variable and whether it is ever negative is
    an empirical question, not a reasoning one.

WHAT IS MEASURED, PER SCORING MONTH
    1. the training mask exactly as score_monthly builds it
    2. that no training row is dated on or after the scoring month's first date
    3. where the LATEST training row's label actually reaches -- the date
       HORIZON trading rows later on that symbol's own calendar
    4. GAP = scoring month's first date minus that observed date

    gap > 0  purge holds.   gap = 0  the label observes the first scored day.
    gap < 0  THE LABEL REACHES INTO THE SCORED MONTH -- leakage, of that size.

Nothing is fixed here.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd
import config, config_mid, config_n100
from engine_core import HORIZON, PURGE
from universes.registry import REGISTRY

# The RAW PANEL paths -- permanent and working -- come from
# universes/registry.py, the single definition. Note the working path is the one
# that nearly follows a filename rule and does not: raw_panel_20.csv on the 58
# against raw_panel_mid_20.csv here, with permanent copies named
# raw_panel_cache.csv and raw_panel_mid_cache.csv. The registry writes all four
# out rather than deriving them, for exactly that reason.
#
# The LABEL stays local: it is printed into diagnostics/leakage_check2_purge.txt.
# Order is load-bearing -- the report is written universe by universe.
LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}
UNIVERSES = {u.tag: (u.raw_cache, str(u.raw_tmp), LABELS[u.tag])
             for u in (REGISTRY["n100"], REGISTRY["mid"])}


def run(uni, perm, tmp, label, W):
    src = config.require_cache(perm, tmp, what=f"{uni} raw panel")
    p = pd.read_csv(src, parse_dates=["date"])
    p = p.sort_values(["date", "symbol"]).reset_index(drop=True)
    p["ym"] = p["date"].dt.to_period("M")

    # The trading calendar as the panel itself observes it.
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}

    W("=" * 100)
    W(f" CHECK 2 -- TRAINING MASK AND PURGE -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  panel {src.name}   rows {len(p):,}   symbols {p['symbol'].nunique()}")
    W(f"  PURGE = {PURGE} CALENDAR days      HORIZON = {HORIZON} TRADING rows")
    W(f"  panel trading days {len(cal)}  {pd.Timestamp(cal[0]).date()} .. "
      f"{pd.Timestamp(cal[-1]).date()}")
    W("")

    rows, violations = [], []
    for ym in sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique()):
        first = p.loc[p.ym == ym, "date"].min()
        cut = first - pd.Timedelta(days=PURGE)
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        if tr.sum() < 5000:
            continue
        td = p.loc[tr, "date"]
        latest = td.max()
        # a training row dated on/after the scored month would be a direct breach
        if (td >= first).any():
            violations.append((str(ym), int((td >= first).sum())))
        # where the latest training row's label reaches, on the real calendar
        i = pos[np.datetime64(latest)]
        j = min(i + HORIZON, len(cal) - 1)
        observed = pd.Timestamp(cal[j])
        gap_td = pos[np.datetime64(first)] - j          # trading days
        gap_cal = (first - observed).days               # calendar days
        rows.append({"month": str(ym), "first_scored": str(first.date()),
                     "cut": str(cut.date()), "train_rows": int(tr.sum()),
                     "latest_train": str(latest.date()),
                     "label_observes": str(observed.date()),
                     "gap_trading_days": gap_td, "gap_calendar_days": gap_cal})

    D = pd.DataFrame(rows)
    W(f"  scoring months measured: {len(D)}")
    W("")
    W("  DIRECT BREACH -- any training row dated on or after the scored month:")
    if violations:
        W(f"    FOUND in {len(violations)} month(s): {violations[:10]}")
    else:
        W("    NONE. In every month, every training row predates the scored month.")
    W("")
    W("  WHERE THE LABEL ACTUALLY REACHES -- gap distribution, in TRADING days")
    g = D["gap_trading_days"]
    W(f"    min {g.min()}   p5 {np.percentile(g,5):.0f}   median {g.median():.0f}"
      f"   p95 {np.percentile(g,95):.0f}   max {g.max()}")
    W(f"    calendar days: min {D['gap_calendar_days'].min()}   "
      f"median {D['gap_calendar_days'].median():.0f}   "
      f"max {D['gap_calendar_days'].max()}")
    W("")
    neg = D[D["gap_trading_days"] < 0]
    zero = D[D["gap_trading_days"] == 0]
    W(f"    months with gap <  0 (label reaches INTO the scored month): {len(neg)}")
    W(f"    months with gap == 0 (label observes the first scored day):  {len(zero)}")
    W(f"    months with gap >  0 (purge holds):                          "
      f"{len(D) - len(neg) - len(zero)}")
    W("")
    if len(neg):
        W("    THE PURGE DOES NOT HOLD IN THESE MONTHS:")
        for _, r in neg.iterrows():
            W(f"      {r['month']}  first scored {r['first_scored']}  "
              f"latest train {r['latest_train']}  label observes "
              f"{r['label_observes']}  overlap {-r['gap_trading_days']} trading days")
    W("")
    W("  THE TIGHTEST MONTHS (smallest gaps):")
    W(f"  {'month':<10}{'first scored':<14}{'latest train':<14}"
      f"{'label observes':<16}{'gap td':>7}{'gap cal':>9}")
    for _, r in D.nsmallest(8, "gap_trading_days").iterrows():
        W(f"  {r['month']:<10}{r['first_scored']:<14}{r['latest_train']:<14}"
          f"{r['label_observes']:<16}{r['gap_trading_days']:>7}"
          f"{r['gap_calendar_days']:>9}")
    W("")
    md = Path(perm).parent
    D.to_csv(md / "leakage_purge_gaps.csv", index=False)
    return D


def main():
    out = []
    for uni, (perm, tmp, label) in UNIVERSES.items():
        run(uni, perm, tmp, label, out.append)
        out.append("")
    (ROOT / "diagnostics" / "leakage_check2_purge.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
