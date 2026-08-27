"""
validate_breadth.py -- is breadth scaling a real effect, or luck?

Breadth scaling looked good on one backtest. One backtest proves nothing, so it
gets the same two tests that inverse-vol had to pass:
  T1. SEED ROBUSTNESS : does the benefit show up on 3 independent score-seed sets?
  T2. SUB-PERIOD      : does it hold in 2019-22 AND 2023-26 separately?

Breadth has no tunable threshold (exposure is simply the fraction of stocks with
positive 20-day momentum), so the overfit risk is lower than for a gate -- but a
robustness check is still required before it goes into the strategy.

All figures below are computed by this run. Nothing is hardcoded.
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from engine_core import build_panel, score_monthly, metrics, precompute, HORIZON
from features_v2 import FEATS_V2
from test_exposure import backtest_exposure

BT_START, BT_END = 2019, 2026
VOL_WIN = 60
M = config.METRICS_DIR


def eval_window(px, op, sc, pc, mom20, port_vol, target_vol, y0, y1):
    dd = px.index[(px.index.year >= y0) & (px.index.year <= y1)]
    base_eq, tc, ntr, _ = backtest_exposure(px, op, sc, dd, pc, mom20, port_vol,
                                            mode="none", target_vol=target_vol)
    br_eq, tc2, ntr2, expo = backtest_exposure(px, op, sc, dd, pc, mom20, port_vol,
                                               mode="breadth", target_vol=target_vol)
    return metrics(base_eq, "b", tc, ntr), metrics(br_eq, "r", tc2, ntr2), expo


def main():
    print("=" * 96)
    print("VALIDATE BREADTH SCALING -- real or luck?")
    print("=" * 96)
    raw = pd.read_csv(f"/tmp/raw_panel_{HORIZON}.csv", parse_dates=["date"])

    print("\n" + "=" * 96)
    print("T1. SEED ROBUSTNESS -- breadth beats baseline on 3 independent seed sets?")
    print("=" * 96)
    t1_rows = []
    for si, seeds in enumerate([[5, 55, 555], [13, 26, 39], [101, 202, 303]]):
        cache = Path(f"/tmp/breadth_seed{si}.csv")
        # engine_core builds the SAME thing (same raw panel, same seeds, same
        # score_monthly call) at /tmp/FINAL_seed{si}.csv -- reuse it if present.
        shared = Path(f"/tmp/FINAL_seed{si}.csv")
        src = cache if cache.exists() else (shared if shared.exists() else None)
        if src is not None:
            ps = pd.read_csv(src, parse_dates=["date"])
        else:
            print(f"   scoring seed set {si+1}/3 ...", flush=True)
            ps = score_monthly(raw, seeds)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
        px = ps.pivot_table(index="date", columns="symbol", values="close").ffill()
        op = ps.pivot_table(index="date", columns="symbol", values="open").ffill()
        sc = ps.pivot_table(index="date", columns="symbol", values="score")
        pc = precompute(px)
        mom20 = px / px.shift(20) - 1
        idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
        port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
        bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
        tv = port_vol.loc[bd].median()
        mb, mr, expo = eval_window(px, op, sc, pc, mom20, port_vol, tv, BT_START, BT_END)
        t1_rows.append({"seedset": si+1, "base_Sharpe": mb["Sharpe"], "breadth_Sharpe": mr["Sharpe"],
                        "dSharpe": round(mr["Sharpe"]-mb["Sharpe"], 2),
                        "base_MaxDD": mb["MaxDD%"], "breadth_MaxDD": mr["MaxDD%"],
                        "dMaxDD": round(mr["MaxDD%"]-mb["MaxDD%"], 1),
                        "base_CAGR": mb["CAGR%"], "breadth_CAGR": mr["CAGR%"]})
        print(f"   seed {si+1}: Sharpe {mb['Sharpe']:.2f}->{mr['Sharpe']:.2f} "
              f"(d{mr['Sharpe']-mb['Sharpe']:+.2f})  MaxDD {mb['MaxDD%']:.1f}%->{mr['MaxDD%']:.1f}% "
              f"(d{mr['MaxDD%']-mb['MaxDD%']:+.1f})  invested {expo*100:.0f}%")
    t1 = pd.DataFrame(t1_rows); t1.to_csv(M / "breadth_val_seeds.csv", index=False)
    ok_sharpe = (t1["dSharpe"] > 0).all()
    ok_dd = (t1["dMaxDD"] > 3).all()
    print(f"\n   Sharpe up on all 3? {'YES' if ok_sharpe else 'NO'}   "
          f"MaxDD shallower(>3pts) on all 3? {'YES' if ok_dd else 'NO'}")
    print(f"   -> T1 {'PASS' if (ok_sharpe and ok_dd) else 'FAIL'}")

    print("\n" + "=" * 96)
    print("T2. SUB-PERIOD SPLIT -- breadth works in BOTH halves?")
    print("=" * 96)
    p = pd.read_csv("/tmp/v5_expanding.csv", parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    tv = port_vol.loc[bd].median()
    t2_rows = []
    for name, y0, y1 in [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]:
        mb, mr, expo = eval_window(px, op, sc, pc, mom20, port_vol, tv, y0, y1)
        t2_rows.append({"period": name, "base_Sharpe": mb["Sharpe"], "breadth_Sharpe": mr["Sharpe"],
                        "dSharpe": round(mr["Sharpe"]-mb["Sharpe"], 2),
                        "base_MaxDD": mb["MaxDD%"], "breadth_MaxDD": mr["MaxDD%"],
                        "dMaxDD": round(mr["MaxDD%"]-mb["MaxDD%"], 1)})
        print(f"   {name}: Sharpe {mb['Sharpe']:.2f}->{mr['Sharpe']:.2f} "
              f"(d{mr['Sharpe']-mb['Sharpe']:+.2f})  MaxDD {mb['MaxDD%']:.1f}%->{mr['MaxDD%']:.1f}% "
              f"(d{mr['MaxDD%']-mb['MaxDD%']:+.1f})")
    t2 = pd.DataFrame(t2_rows); t2.to_csv(M / "breadth_val_periods.csv", index=False)
    ok2 = (t2["dSharpe"] > 0).all()
    print(f"\n   Sharpe up in both halves? {'YES' if ok2 else 'NO'}")
    print(f"   -> T2 {'PASS' if ok2 else 'FAIL'}")

    print("\n" + "=" * 96)
    print("VERDICT")
    print("=" * 96)
    if ok_sharpe and ok_dd and ok2:
        print("   ALL PASS. Breadth's benefit holds across seeds and sub-periods.")
        print("   Real effect, not luck. Safe to make it part of the strategy.")
        print(f"\n   Typical: Sharpe {t1['dSharpe'].mean():+.2f}, MaxDD "
              f"{t1['dMaxDD'].mean():+.1f}pts shallower, cost ~"
              f"{(t1['base_CAGR']-t1['breadth_CAGR']).mean():.1f} pts CAGR.")
        print("   For real money: much lower drawdown, higher risk-adjusted return.")
    else:
        print("   NOT all passed. Read failures above -- benefit not reliable enough")
        print("   to bet real money on if it only works in one seed/period.")
    print("\n   NOTE: breadth has no tuned threshold (no knob to overfit). Residual risk:")
    print("   'positive 20d momentum' as the breadth definition is itself a choice.")
    print("\nSaved -> breadth_val_seeds.csv, breadth_val_periods.csv")


if __name__ == "__main__":
    main()
