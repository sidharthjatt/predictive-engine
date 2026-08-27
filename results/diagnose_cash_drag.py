"""
diagnose_cash_drag.py -- where is cash sitting, and what does it cost or save?
This fixes nothing; it only measures. The problem has to be understood before it
can be addressed.
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, config74


def run(metrics_dir, cash_file, label):
    M = Path(metrics_dir)
    cf, ef = M / cash_file, M / "v2FINAL_equity.csv"
    if not cf.exists() or not ef.exists():
        print(f"\n  {label}: files missing ({cf.name} / {ef.name}), skip")
        return

    c = pd.read_csv(cf, parse_dates=["date"]).set_index("date")
    eq = pd.read_csv(ef, parse_dates=["date"]).set_index("date")

    bh = eq["buyhold"]                          # market proxy
    df = pd.DataFrame({
        "mkt": bh.pct_change(),
        "inv": (100 - c["cash_pct"].reindex(bh.index).ffill()) / 100,
    }).dropna()

    trend = bh.reindex(df.index).ffill()
    df["up"] = (trend > trend.rolling(120).mean()).values

    print(f"\n{'='*74}\n{label}\n{'='*74}")
    print(f"  Overall avg invested : {df['inv'].mean()*100:5.1f}%   "
          f"(cash {100-df['inv'].mean()*100:.1f}%)")
    print(f"  Days invested < 50%  : {(df['inv']<0.5).mean()*100:5.1f}% of days")
    print(f"  Days invested > 90%  : {(df['inv']>0.9).mean()*100:5.1f}% of days")

    net = {}
    for lab, mask in [("RISING market (above 120d avg)", df["up"]),
                      ("FALLING / flat market", ~df["up"])]:
        d = df[mask]
        if len(d) < 20:
            continue
        yrs = len(d) / 252
        mkt_ann = (1 + d["mkt"]).prod() ** (1/yrs) - 1
        cap_ann = (1 + d["mkt"] * d["inv"]).prod() ** (1/yrs) - 1
        gap = (cap_ann - mkt_ann) * 100
        net[lab] = gap
        tag = "COST (drag)" if gap < 0 else "BENEFIT (protection)"
        print(f"\n  {lab}:  {len(d)} days ({len(d)/len(df)*100:.0f}% of time)")
        print(f"     avg invested       : {d['inv'].mean()*100:6.1f}%")
        print(f"     market annualised  : {mkt_ann*100:+6.2f}%")
        print(f"     we captured        : {cap_ann*100:+6.2f}%")
        print(f"     difference         : {gap:+6.2f} pts   <- {tag}")

    if len(net) == 2:
        vals = list(net.values())
        print(f"\n  NET (protection + drag) : {sum(vals):+.2f} pts")
        print("     ", "protection > drag -> breadth is paying off"
              if sum(vals) > 0 else
              "drag > protection -> rising-market drag is worth attacking")

    fwd20 = df["mkt"].rolling(20).sum().shift(-20)
    print(f"\n  Exposure vs NEXT-20d market return, correlation: "
          f"{df['inv'].corr(fwd20):+.4f}")
    print("     (positive = exposure moves up and down at the right times)")


run(config.METRICS_DIR,        "cash_series_58.csv", "58 UNIVERSE")
run(config74.METRICS_DIR_74,   "cash_series_74.csv", "74 UNIVERSE")
print("\nNOTE: this is diagnostic only -- no strategy change is made here.")
