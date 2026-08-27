"""
test_v1_v2_blend.py -- capital split between v1 (fully invested) and v2 (breadth).
This is NOT tuning: both components are already validated. It only splits capital.
  the v1 sleeve gives full participation in rising markets
  the v2 sleeve gives cash protection in falling markets
Blend returns = w*r_v1 + (1-w)*r_v2 (transaction costs already included in both).
Monthly rebalancing between sleeves assumed cost-free (chhota flow).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, config74

def metrics(eq):
    r = eq.pct_change().dropna()
    yrs = len(r)/252
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1
    sh = r.mean()/r.std()*np.sqrt(252)
    dd = ((eq-eq.cummax())/eq.cummax()).min()
    return cagr*100, sh, dd*100, (cagr*100)/abs(dd*100)

def run(mdir, label, inv_v2=0.646):
    eq = pd.read_csv(Path(mdir)/"v2FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    r1 = eq["baseline_invvol"].pct_change().fillna(0)   # v1
    r2 = eq["strategy"].pct_change().fillna(0)          # v2
    print(f"\n{'#'*76}\n{label}\n{'#'*76}")
    print(f"  {'mix (v1/v2)':<14} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} {'~invested':>10}")
    for w in [0.0, 0.25, 0.50, 0.75, 1.0]:
        rb = w*r1 + (1-w)*r2
        e = (1+rb).cumprod()*1_000_000
        c, s, d, cal = metrics(e)
        inv = w*1.0 + (1-w)*inv_v2
        tag = " <- v2 (current)" if w==0 else (" <- v1" if w==1 else "")
        print(f"  {int(w*100):>3}/{int((1-w)*100):<3}       {c:>6.2f}% {s:>7.2f} {d:>7.2f}% {cal:>7.2f} {inv*100:>9.1f}%{tag}")
    # sub-periods for 50/50
    print("  -- 50/50 sub-period Sharpe --")
    for lo, hi in [(2019,2022),(2023,2030)]:
        m = (eq.index.year>=lo)&(eq.index.year<=hi)
        rb = (0.5*r1[m] + 0.5*r2[m])
        if len(rb) < 100: continue
        e = (1+rb).cumprod()
        r = e.pct_change().dropna()
        print(f"    {lo}-{min(hi,eq.index.year.max())}: {r.mean()/r.std()*np.sqrt(252):.2f}")

run(config.METRICS_DIR, "58 UNIVERSE", 0.646)
run(config74.METRICS_DIR_74, "74 UNIVERSE", 0.645)
print("\nNOTE: this is a capital ALLOCATION choice, not a new strategy. Both sleeves\n      are already validated.")
print("In practice this means two separate buckets: one following the v1 rules,\n      the other following v2.")
