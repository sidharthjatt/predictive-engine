"""
make_cash_series.py -- builds cash_series_58.csv and cash_series_74.csv.
Runs the v2 backtest and records cash/(cash+mtm) for every day.
In run_all.py this must run BEFORE the final chart, otherwise the chart stalls.
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_guard import guard as _frozen_guard
import config
from engine_core import precompute
from universes.registry import REGISTRY, selected_tags

# config74 IS IMPORTED INSIDE main(), UNDER THE 74's GUARD, not here. A top-level
# import makes this whole module unloadable once config74.py is deleted, which
# would take the 58's cash series down with the 74's -- going through one universe
# to reach another. The literal `config74.METRICS_DIR_74 / "cash_series_74.csv"`
# stays exactly as written below so check_pipeline_order still resolves the edge.
def cache(tmp,perm):
    if Path(perm).exists(): return perm
    if Path(tmp).exists(): return tmp
    raise FileNotFoundError(f"{perm}/{tmp} missing -- run build_scores first")


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. This body used to run at module level, so
    importing this file executed the whole step as a side effect -- which is why
    the pipeline could only ever spawn it as a subprocess.
    """
    def run_with_cash(cache_path,y_end):
        p=pd.read_csv(cache_path,parse_dates=["date"])
        px=p.pivot_table(index="date",columns="symbol",values="close").ffill()
        op=p.pivot_table(index="date",columns="symbol",values="open").ffill()
        sc=p.pivot_table(index="date",columns="symbol",values="score")
        # WINDOW FROZEN: retired universe -- serves only the retired 58/74. Their published
        # numbers must not move, so this window is deliberately left on the old
        # year cut while the live universes moved to config.BT_START_DATE/BT_END_DATE.
        bd=px.index[(px.index.year>=2019)&(px.index.year<=y_end)]
        pc=precompute(px); mom20=px/px.shift(20)-1
        shares,cash={},CAP; pending=None; recs=[]; cd=(1+CASH_Y)**(1/252)-1
        for i,dt in enumerate(bd):
            pr,opn=px.loc[dt],op.loc[dt]; cash*=(1+cd)
            if pending:
                tgt,keep=pending
                for sx in list(shares):
                    if sx not in keep:
                        q=opn.get(sx,np.nan)
                        if np.isnan(q) or q<=0: continue
                        q2=q*(1-SLIP); sh=int(shares[sx]); t=tc(q2,sh,"SELL")
                        cash+=sh*q2-t; del shares[sx]
                if tgt:
                    pval=sum(s*pr[k] for k,s in shares.items() if not np.isnan(pr.get(k,np.nan)))+cash
                    iv=pval*tgt["_e"]*0.98
                    for sx,w in tgt.items():
                        if sx=="_e" or sx in shares: continue
                        q=opn.get(sx,np.nan)
                        if np.isnan(q) or q<=0: continue
                        q2=q*(1+SLIP); qty=int((iv*w)//q2)
                        if qty<1 or cash<qty*q2: continue
                        t=tc(q2,qty,"BUY")
                        if cash<qty*q2+t: continue
                        cash-=qty*q2+t; shares[sx]=shares.get(sx,0)+qty
                pending=None
            if i%REBAL==0 and i<len(bd)-1:
                m=mom20.loc[dt].dropna(); e=max(0,min(1,float((m>0).mean()) if len(m) else 1.0))
                s_=sc.loc[dt].dropna(); s_=s_[[k for k in s_.index if not np.isnan(pr.get(k,np.nan))]]
                if len(s_)>=TOP_N:
                    rk=s_.sort_values(ascending=False); top=list(rk.index[:TOP_N]); keep=set(rk.index[:BUFFER])
                    v=pc["vol"].loc[dt]; w={}
                    for sx in top:
                        vs=v.get(sx,np.nan); w[sx]=(1/vs) if (not np.isnan(vs) and vs>0.01) else 0
                    tot=sum(w.values()); w={sx:(w[sx]/tot if tot>0 else 1/len(top)) for sx in top}; w["_e"]=e
                    pending=(w,keep)
            mtm=sum(s*pr[k] for k,s in shares.items() if not np.isnan(pr.get(k,np.nan)))
            recs.append({"date":dt,"cash":cash,"mtm":mtm,"total":cash+mtm})
        df=pd.DataFrame(recs).set_index("date")
        df["cash_pct"]=df["cash"]/df["total"]*100
        return df
    # THE FROZEN GUARD MOVED IN HERE WITH THE WORK. At module level it fired on
    # IMPORT, so run.py could not load this file at all. It guards the WRITE, so
    # it belongs where the writing happens.
    _frozen_guard("58/74")   # refuses unless ALLOW_FROZEN_WRITE=1; run_all.py sets it

    REBAL,TOP_N,BUFFER,VOL_WIN=20,8,16,60
    SLIP,CAP,CASH_Y=0.0015,1_000_000,0.06
    try:
        from qbeast_in_charges import compute_leg_charges,Broker,Segment,Product,Side as QS,Exchange
        from decimal import Decimal
        def tc(p,q,s):
            if p<=0 or q<=0: return 0.0
            return float(compute_leg_charges(Broker.ZERODHA,Segment.EQUITY,Product.DELIVERY,
                QS.BUY if s=="BUY" else QS.SELL,Decimal(str(round(p,2))),Decimal(str(round(q,4))),Exchange.NSE).total)
    except Exception:
        def tc(p,q,s): return p*q*0.0011
    # EACH UNIVERSE INDEPENDENTLY. The two halves share only run_with_cash(); one
    # being absent has no bearing on the other, so each is guarded on its own and
    # says so rather than being skipped silently.
    done = []
    # SELECTION, NOT REGISTRATION. `--universe 58` leaves 74 registered but
    # unselected, and this step used to do 74's work anyway -- writing artefacts
    # for a universe the caller did not ask for. selected_tags() defaults to every
    # registered universe, so a standalone run of this file is unchanged.
    # The literal REGISTRY["<tag>"] subscripts below are kept deliberately:
    # check_pipeline_order reads them to resolve this step's outputs, and only the
    # GUARD moved to the selection, not the subscript.
    SEL = set(selected_tags())
    if "58" in SEL:
        print("Building 58 cash series...")
        c58=run_with_cash(cache("/tmp/v5_expanding.csv","results/metrics/v5_expanding_cache.csv"),2026)
        c58.to_csv(config.METRICS_DIR/"cash_series_58.csv")
        print(f"  58 avg cash%: {c58.cash_pct.mean():.1f}%")
        done.append("cash_series_58.csv")
    else:
        print("  58 not selected for this run -- skipping its cash series")
    if "74" in SEL:
        import config74
        print("Building 74 cash series...")
        c74=run_with_cash(cache("/tmp/v74_expanding.csv","results74/metrics/v74_expanding_cache.csv"),2025)
        c74.to_csv(config74.METRICS_DIR_74/"cash_series_74.csv")
        print(f"  74 avg cash%: {c74.cash_pct.mean():.1f}%")
        done.append("cash_series_74.csv")
    else:
        print("  74 not selected for this run -- skipping its cash series")
    print("Done -> " + (", ".join(done) if done else "nothing (neither 58 nor 74 selected)"))


if __name__ == "__main__":
    main()
