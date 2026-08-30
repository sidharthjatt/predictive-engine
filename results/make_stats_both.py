"""
make_stats_both.py -- 58 & 74: per-stock signals CSV + trade stats
Runs v2 backtest capturing trades, computes per-stock buy/sell summary + trade stats.
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, config74
from engine_core import precompute

REBAL, TOP_N, BUFFER, VOL_WIN = 20, 12, 24, 60
SLIP, START, CASH_Y = 0.0015, 1_000_000, 0.06
try:
    from qbeast_in_charges import compute_leg_charges, Broker, Segment, Product, Side as QS, Exchange
    from decimal import Decimal
    def tc(p,q,sd):
        if p<=0 or q<=0: return 0.0
        return float(compute_leg_charges(Broker.ZERODHA,Segment.EQUITY,Product.DELIVERY,
            QS.BUY if sd=="BUY" else QS.SELL,Decimal(str(round(p,2))),Decimal(str(round(q,4))),Exchange.NSE).total)
except Exception:
    def tc(p,q,sd): return p*q*0.0011

def run(cache, mdir, y_end):
    p = pd.read_csv(cache, parse_dates=["date"])
    px = p.pivot_table(index="date",columns="symbol",values="close").ffill()
    op = p.pivot_table(index="date",columns="symbol",values="open").ffill()
    sc = p.pivot_table(index="date",columns="symbol",values="score")
    # WINDOW FROZEN: retired universe -- serves only the retired 58/74. Their published
    # numbers must not move, so this window is deliberately left on the old
    # year cut while the live universes moved to config.BT_START_DATE/BT_END_DATE.
    bd = px.index[(px.index.year>=2019)&(px.index.year<=y_end)]
    pc = precompute(px)
    mom20 = px/px.shift(20)-1
    idx = (1+px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv = idx.pct_change().rolling(VOL_WIN).std()*np.sqrt(252)
    tv = pv.loc[bd].median()

    shares,cash,cum_tc,ntr = {},START,0.0,0
    pending=None; trades=[]
    cd=(1+CASH_Y)**(1/252)-1
    for i,dt in enumerate(bd):
        pr,opn=px.loc[dt],op.loc[dt]; cash*=(1+cd)
        if pending:
            tgt,keep=pending
            for sx in list(shares):
                if sx not in keep:
                    q=opn.get(sx,np.nan)
                    if np.isnan(q) or q<=0: continue
                    q2=q*(1-SLIP); sh=int(shares[sx]); t=tc(q2,sh,"SELL")
                    cash+=sh*q2-t; cum_tc+=t; ntr+=1
                    trades.append({"Date":dt,"Symbol":sx,"Action":"SELL","Price":q2,"Shares":sh,"TC_Rs":t})
                    del shares[sx]
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
                    cash-=qty*q2+t; cum_tc+=t; ntr+=1; shares[sx]=shares.get(sx,0)+qty
                    trades.append({"Date":dt,"Symbol":sx,"Action":"BUY","Price":q2,"Shares":qty,"TC_Rs":t})
            pending=None
        if i%REBAL==0 and i<len(bd)-1:
            m=mom20.loc[dt].dropna(); e=float((m>0).mean()) if len(m) else 1.0
            e=max(0,min(1,e))
            s_=sc.loc[dt].dropna(); s_=s_[[k for k in s_.index if not np.isnan(pr.get(k,np.nan))]]
            if len(s_)>=TOP_N:
                rk=s_.sort_values(ascending=False); top=list(rk.index[:TOP_N]); keep=set(rk.index[:BUFFER])
                v=pc["vol"].loc[dt]; w={}
                for sx in top:
                    vs=v.get(sx,np.nan); w[sx]=(1/vs) if (not np.isnan(vs) and vs>0.01) else 0
                tot=sum(w.values()); w={sx:(w[sx]/tot if tot>0 else 1/len(top)) for sx in top}; w["_e"]=e
                pending=(w,keep)
    tr=pd.DataFrame(trades)
    tr.to_csv(mdir/"v2_trades.csv",index=False)

    # per-stock summary
    rows=[]
    for sym,g in tr.groupby("Symbol"):
        b=(g.Action=="BUY").sum(); s=(g.Action=="SELL").sum()
        rows.append({"symbol":sym,"buys":int(b),"sells":int(s),"total_signals":int(b+s)})
    ps=pd.DataFrame(rows).sort_values("total_signals",ascending=False)
    ps.to_csv(mdir/"v2_per_stock_signals.csv",index=False)

    # trade stats (round trips)
    rts=[]
    for sym,g in tr.groupby("Symbol"):
        g=g.sort_values("Date"); st=[]
        for _,t in g.iterrows():
            if t.Action=="BUY": st.append([t.Price,t.Shares])
            else:
                q=t.Shares
                while q>0 and st:
                    bp,bs=st[0]; m=min(bs,q); rts.append((t.Price-bp)*m)
                    if bs>m: st[0][1]=bs-m
                    else: st.pop(0)
                    q-=m
    rt=np.array(rts)
    stats={"total_trades":ntr,"round_trips":len(rt),
           "win_rate_%":round((rt>0).mean()*100,1) if len(rt) else 0,
           "avg_win":round(rt[rt>0].mean(),0) if (rt>0).any() else 0,
           "avg_loss":round(rt[rt<0].mean(),0) if (rt<0).any() else 0,
           "profit_factor":round(rt[rt>0].sum()/abs(rt[rt<0].sum()),2) if (rt<0).any() else 0,
           "total_TC_Rs":round(cum_tc,0),"stocks_traded":tr.Symbol.nunique()}
    return stats

print("=== 74 ===")
s74=run("/tmp/v74_expanding.csv", config74.METRICS_DIR_74, 2025)
for k,v in s74.items(): print(f"  {k}: {v}")
pd.DataFrame([{"universe":"74",**s74}]).to_csv(
    config74.METRICS_DIR_74/"trade_stats_74.csv",index=False)
print("\nsaved -> 74 per_stock_signals + v2_trades + trade_stats_74.csv")
