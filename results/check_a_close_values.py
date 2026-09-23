"""
check_a_close_values.py -- CHECK A of experiments/DATA_EXEC_SPEC.txt.

Which column carries the bad value on a close/adj_close disagreement day?

It is not symmetric: build_panel selects `close` and ignores `adj_close`, so a
bad value in close is IN THE FEATURES AND IN THE RETURNS, while one in adj_close
is inert.

PRIMARY TEST, DECISIVE, NO EXTERNAL TRUTH REQUIRED
    A closing price must lie inside its own session's range: low <= x <= high.
    A value outside its own row's bounds is provably bad from the row itself.

CORROBORATING TEST, NOT DECISIVE
    A single bad price spikes on day d and reverts on d+1. Reversal ratio
    -r(d+1)/r(d) near +1 with a large |r(d)| is that signature. A genuine crash
    and rebound looks the same, so this never condemns a value on its own.

Nothing is corrected.
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
import config
from features_v2 import EXTREME_RET_HI, EXTREME_RET_LO
from universes.registry import REGISTRY

# The DATA DIRECTORY and METRICS DIRECTORY come from universes/registry.py --
# the single definition. The LABEL stays local: it is printed into
# diagnostics/checkA_close_bad_values.txt. Labels are presentation; paths are
# facts. Order is load-bearing -- the report is written universe by universe.
LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {u.tag: (u.data_dir, u.metrics_dir, LABELS[u.tag])
             for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])}
TOL = 1e-9


def run(uni, ddir, mdir, label, W):
    rows = []
    for f in sorted(Path(ddir).glob("*.csv")):
        x = config.read_price_csv(f)
        need = ["date", "open", "high", "low", "close", "adj_close"]
        if any(c not in x.columns for c in need):
            continue
        x = x[need].dropna().sort_values("date").reset_index(drop=True)
        x["symbol"] = f.stem
        x["r_close"] = x["close"].pct_change()
        x["r_adj"] = x["adj_close"].pct_change()
        x["r_close_next"] = x["r_close"].shift(-1)
        x["r_adj_next"] = x["r_adj"].shift(-1)
        rows.append(x)
    P = pd.concat(rows, ignore_index=True)

    rel = (P["close"] - P["adj_close"]).abs() / P["close"].abs().clip(lower=1e-9)
    P["disagree"] = rel > 1e-9
    D = P[P["disagree"]].copy()
    inwin = (D["date"] >= config.BT_START_DATE) & (D["date"] <= config.BT_END_DATE)

    # PRIMARY: does each column sit inside its OWN row's high/low?
    for col in ("close", "adj_close"):
        lo = D[col] < D["low"] - TOL
        hi = D[col] > D["high"] + TOL
        D[f"{col}_out"] = lo | hi
        D[f"{col}_viol_pct"] = np.where(
            lo, (D["low"] - D[col]) / D[col].abs().clip(lower=1e-9) * 100,
            np.where(hi, (D[col] - D["high"]) / D[col].abs().clip(lower=1e-9) * 100, 0.0))
    D["reversal_close"] = -D["r_close_next"] / D["r_close"].replace(0, np.nan)
    D["reversal_adj"] = -D["r_adj_next"] / D["r_adj"].replace(0, np.nan)

    W("=" * 100)
    W(f" CHECK A -- WHICH COLUMN CARRIES THE BAD VALUE -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  rows in file set        {len(P):,}")
    W(f"  close/adj_close disagree {len(D):,}   of which inside the backtest "
      f"window {int(inwin.sum()):,}")
    W("")
    W("  PRIMARY TEST -- does the value sit inside its OWN session's high/low?")
    nc = int(D["close_out"].sum())
    na = int(D["adj_close_out"].sum())
    W(f"    close      outside its own [low, high] : {nc:,} of {len(D):,}")
    W(f"    adj_close  outside its own [low, high] : {na:,} of {len(D):,}")
    W(f"    neither out of bounds                  : "
      f"{int((~D['close_out'] & ~D['adj_close_out']).sum()):,}")
    W(f"    both out of bounds                     : "
      f"{int((D['close_out'] & D['adj_close_out']).sum()):,}")
    W("")

    bad_close = D[D["close_out"]]
    if len(bad_close):
        W(f"  *** {len(bad_close):,} BAD VALUES IN close -- THE COLUMN THE ENGINE")
        W("  *** USES FOR FEATURES, RETURNS AND EXECUTION PRICES.")
        bw = bad_close[(bad_close["date"] >= config.BT_START_DATE)
                       & (bad_close["date"] <= config.BT_END_DATE)]
        W(f"      inside the backtest window: {len(bw):,}")
        W(f"      symbols affected: {bad_close['symbol'].nunique()}")
        W("")
        W(f"      {'symbol':<14}{'date':<12}{'close':>10}{'low':>10}{'high':>10}"
          f"{'viol%':>8}{'ret':>9}{'guard':>9}{'window':>8}")
        for _, r in bad_close.nlargest(min(40, len(bad_close)), "close_viol_pct").iterrows():
            masked = (r["r_close"] > EXTREME_RET_HI) or (r["r_close"] < EXTREME_RET_LO)
            W(f"      {r['symbol']:<14}{str(r['date'].date()):<12}{r['close']:>10.2f}"
              f"{r['low']:>10.2f}{r['high']:>10.2f}{r['close_viol_pct']:>8.2f}"
              f"{r['r_close']*100:>8.1f}%{('masked' if masked else 'PASSES'):>9}"
              f"{('in' if config.BT_START_DATE <= r['date'] <= config.BT_END_DATE else 'out'):>8}")
    else:
        W("  NO close VALUE ON ANY DISAGREEMENT ROW FALLS OUTSIDE ITS OWN SESSION'S")
        W("  RANGE. By this test the traded column is internally consistent on every")
        W("  row where the two columns disagree.")
    W("")

    if na:
        W(f"  adj_close out of bounds on {na:,} rows. Worst 10 by magnitude:")
        W(f"      {'symbol':<14}{'date':<12}{'adj_close':>11}{'low':>10}{'high':>10}{'viol%':>8}")
        for _, r in D[D["adj_close_out"]].nlargest(min(10, na), "adj_close_viol_pct").iterrows():
            W(f"      {r['symbol']:<14}{str(r['date'].date()):<12}{r['adj_close']:>11.2f}"
              f"{r['low']:>10.2f}{r['high']:>10.2f}{r['adj_close_viol_pct']:>8.2f}")
        W("")

    W("  CORROBORATING TEST -- spike and revert on the disagreement day")
    W("    A ratio near +1 with a large |r(d)| is the signature of a bad value.")
    W("    It is NOT decisive: a genuine crash and rebound looks identical.")
    for col, rc, rr in (("close", "r_close", "reversal_close"),
                        ("adj_close", "r_adj", "reversal_adj")):
        s = D[(D[rc].abs() > 0.05) & D[rr].notna()]
        if len(s):
            near1 = int(((s[rr] > 0.7) & (s[rr] < 1.3)).sum())
            W(f"    {col:<10} rows with |r(d)| > 5%: {len(s):>5}   "
              f"of which reversal ratio in [0.7, 1.3]: {near1:>5} "
              f"({near1/len(s)*100:.0f}%)")
        else:
            W(f"    {col:<10} no rows with |r(d)| > 5%")
    W("")
    D.to_csv(Path(mdir) / "checkA_disagreements.csv", index=False)
    W(f"  every disagreement row written to {Path(mdir).name}/checkA_disagreements.csv")
    W("")
    # nc and na are the PRIMARY TEST counts computed above; returning them adds no
    # measurement, it only stops them being discarded.
    return {"close_out": nc, "adj_close_out": na, "rows": len(D)}


def main():
    out = []
    res = {}
    for uni, (ddir, mdir, label) in UNIVERSES.items():
        # THE FARM IS BUILT ON DEMAND under cache/<tag>/ since 2026-09-23;
        # u.data_dir is only its path and is empty on a fresh tree.
        ddir = REGISTRY[uni].prepare_data_dir()
        res[uni] = run(uni, ddir, mdir, label, out.append)
        out.append("")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No count, bound,
    # extreme-return constant or printed row changed.
    #
    # WHAT IS GATED IS THIS FILE'S OWN PRIMARY TEST, and only the traded column.
    # The report already states the condition categorically -- "NO close VALUE ON
    # ANY DISAGREEMENT ROW FALLS OUTSIDE ITS OWN SESSION'S RANGE ... the traded
    # column is internally consistent" -- so a close outside its own [low, high]
    # is a failure by the file's own words, not by a threshold chosen here.
    #
    # adj_close IS REPORTED AND NOT GATED. It is out of bounds on 170 nifty100 and
    # 41 midcap150 rows, measured 2026-09-21, and that is the exact population
    # engine_core.canonical_price already falls back to the raw close on. Gating
    # it would fail the run for a condition the engine is documented to handle,
    # and this file states no tolerance for it.
    bad = {u: r for u, r in res.items() if r["close_out"]}
    tot_close = sum(r["close_out"] for r in res.values())
    tot_adj = sum(r["adj_close_out"] for r in res.values())
    out.append(f"  ungated, reported only: adj_close outside its own [low, high] "
               f"on {tot_adj:,} row(s); canonical_price falls back to close there.")
    if bad:
        out.append(f"  RESULT: FAIL -- the traded column is outside its own "
                   f"session range on {tot_close:,} row(s), on: "
                   + ", ".join(sorted(bad)) + ".")
        rc = 1
    else:
        out.append(f"  RESULT: PASS -- no close value on any disagreement row "
                   f"falls outside its own session range, across "
                   f"{len(res)} universe(s).")
        rc = 0
    (ROOT / "diagnostics" / "checkA_close_bad_values.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
