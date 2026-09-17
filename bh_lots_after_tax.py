"""bh_lots_after_tax.py -- v2 after tax against a GENUINE buy & hold after tax.

    ./venv/bin/python bh_lots_after_tax.py

READ THE CONCENTRATION WARNING BEFORE QUOTING THE mid NUMBERS. This script
prints it; it is repeated here because a figure gets copied out of a terminal
more often than a docstring gets read.

    mid  bh_lots terminal value is 53.0% ONE NAME (AIIL, 956x over the window),
         68.4% in three (AIIL, PATANJALI, LLOYDSME). The median name returns
         3.45x. The mid "benchmark" is therefore a single-stock bet wearing a
         116-name basket's name, and the universe is SURVIVORSHIP_MODE=static --
         today's MidCap150 members backfilled -- so AIIL is in the basket
         PRECISELY BECAUSE it went up 956x. Buy-and-hold is the most
         survivorship-exposed construction there is, and this is what that looks
         like. mid's bh_lots CAGR is not an achievable return and the v2-vs-mid
         comparison must not be quoted as a strategy result.

    n100 top name 8.1%, top three 18.8%, and bh_lots (23.97%) lands within 0.03
         points of the published daily-rebalanced bh (24.00%). That comparison
         is diversified and usable.

WHAT IT MEASURES

v2 after tax vs buy & hold after tax. bh_lots per Finding 1(a).

bh_lots: equal-rupee across every symbol priced on the first session, NO
rebalance, single realisation at BT_END_DATE. Same slippage and the same Zerodha
charge engine as v2, so the two lines differ in strategy and tax treatment and in
nothing else. The published `bh` line -- px.pct_change().mean(axis=1).cumprod() --
is a DAILY-REBALANCED costless index and is reported alongside for reference
only; it is a different construction and is never substituted for.
"""
import os
for v in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS",
          "VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"): os.environ[v]="1"
os.environ["PYTHONHASHSEED"]="0"
import sys; from pathlib import Path
ROOT=Path("/Users/sidharthchoudhary/Downloads/algo_trading_project")
for p in (ROOT,ROOT/"results",ROOT/"nautilus"): sys.path.insert(0,str(p))
import numpy as np, pandas as pd
import cadence, config, profiles, engine_core, tax_util as T
from engine_core import precompute
from test_exposure import backtest_exposure, calc_tc, SLIPPAGE, START_CAPITAL
from universes.registry import REGISTRY
VOL_WIN=60
HALVES=[("2019-2022",2019,2022),("2023-2026",2023,2026)]

def cagr(s):
    y=(s.index[-1]-s.index[0]).days/365.25
    return ((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100

def bh_lots(px,op,bd):
    """-> (equity series, terminal tax, detail). Buy once, hold, realise at end."""
    d0,dN=bd[0],bd[-1]
    o0=op.loc[d0]
    syms=[s for s in o0.index if not np.isnan(o0[s]) and o0[s]>0]
    per=START_CAPITAL/len(syms)
    shares,cash={},START_CAPITAL
    for s in syms:
        pr=float(o0[s])*(1+SLIPPAGE)
        q=int(per//pr)
        if q<1: continue
        tc=calc_tc(pr,q,"BUY")
        if cash < q*pr+tc: continue
        cash-=q*pr+tc; shares[s]=(q,pr)
    # mark to market every session, no rebalance, no further trade
    held=pd.DataFrame({s:px[s] for s in shares})
    qty=pd.Series({s:shares[s][0] for s in shares})
    eq=(held.loc[bd].fillna(method="ffill")*qty).sum(axis=1)+cash
    # the single realisation, at the last session's open with the usual slippage
    gain=0.0; proceeds=0.0; sell_tc=0.0
    oN=op.loc[dN]
    for s,(q,bp) in shares.items():
        pr=float(oN.get(s,np.nan))
        if np.isnan(pr) or pr<=0: pr=float(px.loc[dN,s])
        pr*=(1-SLIPPAGE)
        proceeds+=q*pr; sell_tc+=calc_tc(pr,q,"SELL")
        gain+=q*(round(pr,2)-round(bp,2))          # section 3(C): price diff only
    held_days=(dN-d0).days
    fy=T.financial_year(dN); reg=T.regime_of(dN)
    b=dict.fromkeys(T.BUCKETS,0.0)
    b[("long_" if held_days>=T.LTCG_HOLD_DAYS else "short_")+reg]=gain
    tx=T.tax_for_fy(fy,b)
    globals()["_SH"]=shares
    return eq,tx,dict(names=len(shares),held_days=held_days,fy=T.fy_label(fy),
                      regime=reg,gain=gain,tax=tx["total_tax"],
                      exemption=tx["exemption"],residual_cash=cash,
                      proceeds=proceeds,sell_tc=sell_tc)

print("="*96)
print(" v2 AFTER TAX vs BUY & HOLD AFTER TAX   (bh_lots: equal-rupee once, no rebalance, realise at end)")
print("="*96)
for tag,u in REGISTRY.items():
    engine_core.set_tradeability(u)
    p=pd.read_csv(config.require_cache(u.score_cache,str(u.score_tmp),what=tag),parse_dates=["date"])
    px=p.pivot_table(index="date",columns="symbol",values="close").ffill()
    op=p.pivot_table(index="date",columns="symbol",values="open").ffill()
    sc=p.pivot_table(index="date",columns="symbol",values="score")
    pc=precompute(px); mom20=px/px.shift(20)-1
    idx=(1+px.pct_change().mean(axis=1).fillna(0)).cumprod()
    pv=idx.pct_change().rolling(VOL_WIN).std()*np.sqrt(252)
    bd=px.index[(px.index>=config.BT_START_DATE)&(px.index<=config.BT_END_DATE)]
    kw=dict(mode="breadth",target_vol=pv.loc[bd].median(),rebal=cadence.selected(),
            participation_cap=profiles.participation_cap())
    v2_off,_,_,_=backtest_exposure(px,op,sc,bd,pc,mom20,pv,audit=None,tax_enabled=False,**kw)
    a={k:[] for k in ("holdings","summary","trades","ranking","decisions","skipped")}
    v2_on ,_,_,_=backtest_exposure(px,op,sc,bd,pc,mom20,pv,audit=a,tax_enabled=True,**kw)
    stmt,_=T.liability_schedule(a["tax"]["lots"],bd)
    v2_unassessed=float(stmt.loc[~stmt["assessed"],"total_tax"].sum())

    bh_eq,bh_tx,det=bh_lots(px,op,bd)
    bh_pub=START_CAPITAL*(1+px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    # SETTLED: every outstanding liability paid at the window's last session, for
    # BOTH lines. Without this the comparison is not like-for-like -- section 3(9)
    # assesses bh_lots' single realisation in 2027, outside the window, so an
    # unsettled bh_lots pays literally nothing.
    v2_settled=v2_on.copy();  v2_settled.iloc[-1]-=v2_unassessed
    bh_settled=bh_eq.copy();  bh_settled.iloc[-1]-=bh_tx["total_tax"]

    print(f"\n{'-'*96}\n {tag.upper()}   {bd[0].date()} .. {bd[-1].date()}   {len(bd):,} sessions")
    print(f"{'-'*96}")
    print(f"  bh_lots construction: {det['names']} names, equal-rupee, held {det['held_days']:,} days "
          f"({det['held_days']/365.25:.1f}y) -> LONG term")
    print(f"      single realisation in {det['fy']}, regime '{det['regime']}', gain Rs {det['gain']:,.0f}, "
          f"exemption Rs {det['exemption']:,.0f}")
    print(f"      LTCG due Rs {det['tax']:,.0f}   (rate {T.LTCG_RATE[det['regime']]*100:g}%)")
    print(f"  v2 tax charged in-loop Rs {a['tax']['cum_tax']:,.0f}; unassessed FY2026-27 Rs {v2_unassessed:,.0f}")

    rows=[("v2  before tax",v2_off),("v2  after tax (settled)",v2_settled),
          ("bh_lots before tax",bh_eq),("bh_lots after tax (settled)",bh_settled),
          ("bh published (costless, daily-rebal)",bh_pub)]
    print(f"\n  {'line':<38}{'FULL':>10}{'2019-2022':>12}{'2023-2026':>12}   final equity")
    res={}
    for lab,s in rows:
        full=cagr(s); res[lab]=full
        h=[cagr(s[(s.index.year>=y0)&(s.index.year<=y1)]) for _,y0,y1 in HALVES]
        print(f"  {lab:<38}{full:>9.2f}%{h[0]:>11.2f}%{h[1]:>11.2f}%   {s.iloc[-1]:>14,.0f}")
    e_pre =res["v2  before tax"]-res["bh_lots before tax"]
    e_post=res["v2  after tax (settled)"]-res["bh_lots after tax (settled)"]
    e_pub =res["v2  before tax"]-res["bh published (costless, daily-rebal)"]
    # CONCENTRATION, PRINTED BESIDE THE EDGE IT INVALIDATES. A basket whose
    # terminal value is one name is not a benchmark, and the number above is
    # meaningless without this line sitting next to it.
    _v={s_:q*float(px.loc[bd[-1],s_]) for s_,(q,_b) in _SH.items()}
    _t=sum(_v.values()); _top=sorted(_v.items(),key=lambda x:-x[1])
    print(f"\n  bh_lots concentration: top name {_top[0][0]} = {_top[0][1]/_t*100:.1f}% of "
          f"terminal value, top 3 = {sum(v for _,v in _top[:3])/_t*100:.1f}%"
          + ("   <-- NOT A USABLE BENCHMARK" if _top[0][1]/_t > 0.25 else ""))
    print(f"\n  EDGE  v2 - bh_lots   before tax {e_pre:+.2f} pts      after tax {e_post:+.2f} pts"
          f"      swing {e_post-e_pre:+.2f}")
    print(f"  EDGE  v2 - bh published (the +0.89/+0.43 baseline) {e_pub:+.2f} pts")
