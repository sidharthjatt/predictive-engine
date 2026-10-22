"""
leakage_check2_trading_purge.py -- CHECK 2 of experiments/LEAKAGE_SPEC.txt: no
training label ends after the purge limit of the month it trains.
==============================================================================

WHAT IS CHECKED

    For every month score_monthly would train, the training rows are taken from
    engine_core.training_set -- the function score_monthly calls, not a copy of
    it -- on the universe's cached raw panel. For each row the date its label
    ends (`label_end`, the symbol's own row HORIZON rows ahead) is placed on the
    panel's calendar, and

        gap = position(first scored session) - position(latest label_end)

    in trading sessions. THE GATE IS gap >= PURGE_EMBARGO IN EVERY TRAINED MONTH
    ON EVERY GATED UNIVERSE. training_set promises that by construction; this
    checks the promise on the real panels.

    A second assertion: every training target is a rank within the training
    rows of its own date, so it lies in (0, 1]. A target ranked over labels that
    had not ended would still lie there, which is why the label-end test above is
    the gate and this one only catches a malformed target.

WHY IT WAS REWRITTEN ON 2026-10-22

    The previous version recovered the latest training DATE and added HORIZON
    sessions on the panel's calendar. That measures where a label ends for a
    symbol with no missing sessions only. A symbol's label is HORIZON of its own
    rows ahead, so across a gap it ends later; the old check passed on 252 of 252
    month-universe pairs while smallcap250 pit had labels ending up to 25
    sessions past the limit. The label end date is now in the panel and is read
    directly.

    The calendar-rule sibling, leakage_check2_purge.py, was deleted the same day
    with the calendar rule itself.

MONTHS THE ENGINE SKIPS ARE NOT INVENTED INTO THE COUNT. A month with no
qualifying cut, fewer than 5,000 training rows, or nothing scorable never trains;
those months are counted and reported as skipped.

USAGE

    python results/leakage_check2_trading_purge.py

    Writes diagnostics/leakage_check2_trading_purge.txt. Exits non-zero if any
    trained month on any gated universe has a label ending inside its purge window.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import numpy as np                                   # noqa: E402
import pandas as pd                                  # noqa: E402
import config                                        # noqa: E402
import engine_core as _ec                            # noqa: E402
from engine_core import HORIZON, PURGE_EMBARGO       # noqa: E402
from universes.registry import REGISTRY, gated              # noqa: E402
from config import read_table  # the one CSV/parquet reader: config.read_table

LABELS = {u.tag: u.display_name for u in gated()}
UNIVERSES = {u.tag: (u.raw_cache, LABELS[u.tag]) for u in gated()}


def run(uni, perm, label, W):
    src = config.require_cache(perm, what=f"{uni} raw panel")
    raw = read_table(src, parse_dates=["date", "label_end"])

    W("=" * 100)
    W(f" CHECK 2 (TRADING RULE) -- TRAINING LABELS AGAINST THE PURGE LIMIT -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  panel {src.name}   rows {len(raw):,}   symbols {raw['symbol'].nunique()}")
    W(f"  HORIZON = {HORIZON} rows of the symbol's own history   "
      f"PURGE_EMBARGO = {PURGE_EMBARGO} sessions")

    # The panel exactly as score_monthly orders it.
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True)
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}
    ym_col = p["date"].dt.to_period("M")
    months = sorted(ym_col[p["date"] >= _ec.score_floor()].unique())

    rows, skipped, bad_target = [], 0, 0
    for ym in months:
        first = p.loc[ym_col == ym, "date"].min()
        i = pos[np.datetime64(first)]
        ts = _ec.training_set(p, cal, i)
        te = (ym_col == ym) & p["scorable"]
        if ts is None or len(ts[1]) < 5000 or not te.any():
            skipped += 1
            continue
        tri, y = ts
        bad_target += int(((y <= 0) | (y > 1)).sum())
        latest_end = p.loc[tri, "label_end"].max()
        j = pos[np.datetime64(latest_end)]
        rows.append({"month": str(ym), "first_scored": str(first.date()),
                     "train_rows": len(y), "latest_label_end": str(latest_end.date()),
                     "gap_trading_days": i - j,
                     "gap_calendar_days": (first - latest_end).days})
    W(f"  scoring months considered: {len(months)}   trained: {len(rows)}   "
      f"skipped by the engine's rule: {skipped}")
    W("")

    D = pd.DataFrame(rows)
    if D.empty:
        W("  NO MONTH TRAINED. Nothing to assert.")
        return {"trained": 0, "below": 0, "bad_target": 0}

    g = D["gap_trading_days"]
    below = D[g < PURGE_EMBARGO]
    W("  WHERE THE LATEST TRAINING LABEL ENDS -- gap to the first scored session, in "
      "TRADING sessions")
    W(f"    min {g.min()}   p5 {np.percentile(g, 5):.0f}   median {g.median():.0f}"
      f"   p95 {np.percentile(g, 95):.0f}   max {g.max()}")
    W(f"    months with gap < {PURGE_EMBARGO} (a label ends inside the purge window): "
      f"{len(below)} of {len(D)}")
    W(f"    training targets outside (0, 1]: {bad_target}")
    W("")
    if len(below):
        W("    THE PURGE DOES NOT HOLD IN THESE MONTHS:")
        for _, r in below.iterrows():
            W(f"      {r['month']}  first scored {r['first_scored']}  latest label end "
              f"{r['latest_label_end']}  gap {r['gap_trading_days']} sessions")
        W("")
    W("  THE TIGHTEST MONTHS (smallest gaps):")
    W(f"  {'month':<10}{'first scored':<14}{'latest label':<14}{'gap td':>7}{'gap cal':>9}")
    for _, r in D.nsmallest(8, "gap_trading_days").iterrows():
        W(f"  {r['month']:<10}{r['first_scored']:<14}{r['latest_label_end']:<14}"
          f"{r['gap_trading_days']:>7}{r['gap_calendar_days']:>9}")
    W("")
    md = REGISTRY[uni].metrics_dir
    # naming: axis-free -- the per-month gap table for one universe under the
    # live purge rule. It describes the TRAINING MASK, not a strategy result, so
    # it varies over no arm, cadence, profile or tax selection; the universe is
    # carried by the directory it is written into.
    D.to_csv(md / "leakage_purge_gaps_trading.csv", index=False)
    W(f"  every month written to {md.name}/leakage_purge_gaps_trading.csv")
    W("")
    return {"trained": len(D), "below": len(below), "bad_target": bad_target}


def main():
    out = []
    res = {}
    for uni, (perm, label) in UNIVERSES.items():
        res[uni] = run(uni, perm, label, out.append)
        out.append("")

    tot_tr = sum(r["trained"] for r in res.values())
    bad = {u: r for u, r in res.items() if r["below"] or r["bad_target"]}
    out.append("  RULE TESTED: engine_core.training_set, the rule score_monthly runs: "
               "row date <= cal[i - HORIZON - PURGE_EMBARGO]")
    out.append("  and label_end <= cal[i - PURGE_EMBARGO], targets ranked within the "
               "qualifying rows of each date.")
    if bad:
        out.append("  RESULT: FAIL -- a training label ends inside the purge window, or "
                   "a target is malformed, on: "
                   + ", ".join(f"{u} ({r['below']} month(s), {r['bad_target']} target(s))"
                               for u, r in sorted(bad.items())) + ".")
        rc = 1
    else:
        per = ", ".join(f"{u} {r['trained']}" for u, r in sorted(res.items()))
        out.append(f"  RESULT: PASS -- the latest training label ends at least "
                   f"{PURGE_EMBARGO} sessions before the first scored session in every "
                   f"trained month, {tot_tr} month-universe pair(s) across "
                   f"{len(res)} universe(s) ({per}).")
        rc = 0
    # naming: axis-free -- one report on the training mask under the live purge
    # rule, covering every gated universe, which are named inside the file.
    (ROOT / "diagnostics" / "leakage_check2_trading_purge.txt").write_text(
        "\n".join(out) + "\n")
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
