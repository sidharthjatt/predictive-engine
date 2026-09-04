"""
leakage_check4_corpactions.py -- CHECK 4 of experiments/LEAKAGE_SPEC.txt.

Splits and bonuses. NOT a leakage check -- a data-correctness check, reported
separately, because it is the other way a backtest produces returns that are not
real, and it can push CAGR in EITHER direction.

STATED FROM SOURCE, BEFORE MEASURING
    engine_core.build_panel:180 selects ["date","open","high","low","close",
    "volume"]. The raw CSVs also carry adj_close. THE PANEL USES close AND
    IGNORES adj_close.

MEASURED HERE
    1. how often close and adj_close differ, and by how much
    2. the top 20 largest single-day close-to-close returns, each direction
    3. for each, whether the EXTREME_RET guard masks it, and whether adj_close
       shows the same move

WHAT IS MISSING, AND IT IS NOT AN EXCUSE
    THERE IS NO CORPORATE-ACTION DATASET ON DISK. data/reference/ holds NSE
    circulars, a press-release manifest and the symbol-rename map -- no split or
    bonus list. So moves cannot be confirmed against an authoritative source.
    adj_close is the only instrument available and ITS PROVENANCE IS UNVERIFIED.
    Every claim resting on it is labelled as such.
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
from features_v2 import EXTREME_RET_HI, EXTREME_RET_LO

UNIVERSES = {
    "n100": (config_n100.CONSTITUENTS_DIR_N100, "NIFTY 100"),
    "mid": (config_mid.CONSTITUENTS_DIR_MID, "MIDCAP150"),
}


def run(uni, d, label, W):
    rows = []
    n_files = n_with_adj = 0
    for f in sorted(Path(d).glob("*.csv")):
        n_files += 1
        x = config.read_price_csv(f)
        if "adj_close" not in x.columns:
            continue
        n_with_adj += 1
        x = x[["date", "close", "adj_close"]].dropna().sort_values("date")
        x["symbol"] = f.stem
        rows.append(x)
    P = pd.concat(rows, ignore_index=True)
    win = P[(P["date"] >= config.BT_START_DATE) & (P["date"] <= config.BT_END_DATE)]

    W("=" * 100)
    W(f" CHECK 4 -- CORPORATE ACTIONS -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  symbol files {n_files}, of which carry adj_close: {n_with_adj}")
    W(f"  rows in backtest window: {len(win):,}")
    W("")

    # ---- 1. does close differ from adj_close? ---------------------------
    rel = (win["close"] - win["adj_close"]).abs() / win["close"].abs().clip(lower=1e-9)
    diff = rel > 1e-9
    W("  1. close VERSUS adj_close, inside the backtest window")
    W(f"     rows where they differ at all : {int(diff.sum()):,} of {len(win):,} "
      f"({diff.mean()*100:.3f}%)")
    W(f"     symbols affected              : {win.loc[diff,'symbol'].nunique()} "
      f"of {win['symbol'].nunique()}")
    if diff.any():
        W(f"     max relative difference       : {rel.max()*100:.2f}%")
        W(f"     median relative difference    : {rel[diff].median()*100:.4f}%")
    W("")

    # ---- 2. largest single-day moves on the column the engine uses ------
    P = P.sort_values(["symbol", "date"])
    P["ret_close"] = P.groupby("symbol")["close"].pct_change()
    P["ret_adj"] = P.groupby("symbol")["adj_close"].pct_change()
    W_ = P[(P["date"] >= config.BT_START_DATE) & (P["date"] <= config.BT_END_DATE)]
    W_ = W_.dropna(subset=["ret_close"])

    for direction, asc in (("MOST NEGATIVE", True), ("MOST POSITIVE", False)):
        top = W_.sort_values("ret_close", ascending=asc).head(20)
        W(f"  2. TOP 20 {direction} SINGLE-DAY RETURNS on close "
          f"(the column the engine trades)")
        W(f"     {'symbol':<14}{'date':<12}{'ret_close':>11}{'ret_adj':>11}"
          f"{'guard':>9}   reading")
        for _, r in top.iterrows():
            masked = (r["ret_close"] > EXTREME_RET_HI) or (r["ret_close"] < EXTREME_RET_LO)
            ra = r["ret_adj"]
            # adj_close is the instrument: if close moves and adj_close does not,
            # the move is in the unadjusted column only.
            if pd.isna(ra):
                reading = "adj_close missing"
            elif abs(r["ret_close"] - ra) < 1e-6:
                reading = "same in adj_close"
            else:
                reading = f"adj_close shows {ra*100:+.1f}% -- DIFFERS"
            W(f"     {r['symbol']:<14}{str(r['date'].date()):<12}"
              f"{r['ret_close']*100:>10.1f}%{(ra*100 if pd.notna(ra) else float('nan')):>10.1f}%"
              f"{('masked' if masked else 'PASSES'):>9}   {reading}")
        W("")

    # ---- 3. the band the guard cannot catch ------------------------------
    W(f"  3. THE GUARD'S BAND. EXTREME_RET_LO = {EXTREME_RET_LO}, "
      f"EXTREME_RET_HI = {EXTREME_RET_HI}")
    W("     A 2-for-1 split is -50% and IS masked. A 5-for-4 bonus is -20% and is NOT.")
    uncaught = W_[(W_["ret_close"] <= -0.20) & (W_["ret_close"] > EXTREME_RET_LO)]
    W(f"     moves in the UNCAUGHT band -20% to {EXTREME_RET_LO*100:.0f}%: "
      f"{len(uncaught):,} rows, {uncaught['symbol'].nunique()} symbols")
    if len(uncaught):
        da = uncaught.dropna(subset=["ret_adj"])
        d2 = da[(da["ret_close"] - da["ret_adj"]).abs() > 1e-6]
        W(f"     of those, adj_close DISAGREES on {len(d2)} -- candidates for an")
        W("     unadjusted corporate action that the guard does not catch:")
        for _, r in d2.head(12).iterrows():
            W(f"       {r['symbol']:<14}{str(r['date'].date()):<12}"
              f"close {r['ret_close']*100:>7.1f}%   adj {r['ret_adj']*100:>7.1f}%")
    W("")
    W("  PROVENANCE. Every 'adj_close DIFFERS' line above rests on adj_close, whose")
    W("  provenance is UNVERIFIED -- there is no corporate-action dataset in this")
    W("  repository to confirm it against. The names and dates are listed so that a")
    W("  manual NSE lookup is possible; none was performed.")
    W("")


def main():
    out = []
    for uni, (d, label) in UNIVERSES.items():
        run(uni, d, label, out.append)
        out.append("")
    (ROOT / "diagnostics" / "leakage_check4_corpactions.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
