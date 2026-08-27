import sys, warnings; sys.dont_write_bytecode=True; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0,'.'); sys.path.insert(0,'results')
from features_v2 import FEATS_V2
U=[("58","results/metrics/raw_panel_cache.csv","results/metrics/v5_expanding_cache.csv",2026),
   ("74","results74/metrics/raw_panel74_cache.csv","results74/metrics/v74_expanding_cache.csv",2025),
   ("mid","results_mid/metrics/raw_panel_mid_cache.csv","results_mid/metrics/v_mid_expanding_cache.csv",2026)]
def dic(df,col):
    out=[]
    for _,g in df.groupby("date"):
        h=g[[col,"y_rank"]].dropna()
        if len(h)<10: continue
        r=spearmanr(h[col],h["y_rank"]).statistic
        if not np.isnan(r): out.append(r)
    return np.mean(out) if out else np.nan
print("TASK 2 -- standalone raw-feature IC vs the model's own IC, by year")
print("Target: y_rank, the 20-day forward cross-sectional rank. Scorable rows only.\n")
for tag,rawf,scf,yend in U:
    raw=pd.read_csv(rawf,parse_dates=["date"],usecols=["date","symbol","y_rank","scorable"]+FEATS_V2)
    raw=raw[raw["scorable"]==True]
    sco=pd.read_csv(scf,parse_dates=["date"],usecols=["date","symbol","score"])
    m=raw.merge(sco,on=["date","symbol"],how="left")
    m=m[(m["date"].dt.year>=2019)&(m["date"].dt.year<=yend)]
    yrs=sorted(m["date"].dt.year.unique())
    T=pd.DataFrame({f:{y:dic(m[m["date"].dt.year==y],f) for y in yrs}
                    for f in FEATS_V2+["score"]}).T
    print("="*100); print(f" {tag.upper()} universe"); print("="*100)
    print(f"\n{'feature':<22}"+"".join(f"{y:>9}" for y in yrs))
    for f in FEATS_V2: print(f"{f:<22}"+"".join(f"{T.loc[f,y]:>+9.4f}" for y in yrs))
    print("-"*(22+9*len(yrs)))
    print(f"{'MODEL score':<22}"+"".join(f"{T.loc['score',y]:>+9.4f}" for y in yrs))
    fi=T.loc[FEATS_V2]
    print(f"\n{'mean |feature IC|':<22}"+"".join(f"{fi[y].abs().mean():>9.4f}" for y in yrs))
    print(f"{'model |IC|':<22}"+"".join(f"{abs(T.loc['score',y]):>9.4f}" for y in yrs))
    base=np.sign(fi[yrs[0]])
    print(f"{'sign matches 2019':<22}"+"".join(f"{int((np.sign(fi[y])==base).sum()):>9}" for y in yrs))
    cons=int(((fi[yrs]>0).all(axis=1)|(fi[yrs]<0).all(axis=1)).sum())
    print(f"\n  features holding ONE sign across all {len(yrs)} years: {cons} of 17")
    print(f"  mean |feature IC| 2019 {fi[yrs[0]].abs().mean():.4f} -> "
          f"{yrs[-1]} {fi[yrs[-1]].abs().mean():.4f}")
    print(f"  model IC          2019 {T.loc['score',yrs[0]]:+.4f} -> "
          f"{yrs[-1]} {T.loc['score',yrs[-1]]:+.4f}\n")
