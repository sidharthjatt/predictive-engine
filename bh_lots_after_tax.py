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
# ROOT IS THIS FILE'S OWN DIRECTORY AND MUST STAY THAT WAY. It was an absolute
# literal naming one developer's checkout until 2026-09-20. Because the next line
# puts ROOT at sys.path[0], and check_all.py's GATE 1 imports every module in the
# repository, importing this file redirected every LATER `import config` and
# `import universes.registry` in that process to the other tree. Gates 6, 7 and 8
# run after gate 1, so a clone's gate suite read the literal's tree and reported
# on artefacts that were not its own. Measured 2026-09-20: a fresh clone reported
# "GATE 8  20 published artefact(s) checked" with no params file on its own disk.
ROOT=Path(__file__).resolve().parent
for p in (ROOT,ROOT/"results",ROOT/"nautilus"): sys.path.insert(0,str(p))
import numpy as np, pandas as pd
import cadence, config, profiles, engine_core, tax_util as T
from engine_core import precompute
from test_exposure import backtest_exposure, calc_tc, SLIPPAGE, START_CAPITAL
from universes.registry import REGISTRY
VOL_WIN=60
HALVES=[("2019-2022",2019,2022),("2023-2026",2023,2026)]

# ---------------------------------------------------------------------------
# THE CONCENTRATION LIMIT, AND WHY IT IS 11.62% AND NOT A ROUND NUMBER
# ---------------------------------------------------------------------------
# A benchmark is an INSTRUMENT. It can only resolve an effect larger than its own
# sensitivity to a single input. The effect this benchmark exists to measure is
# the after-tax edge swing -- MEASURED at -2.05 CAGR points on n100 (3f0ef05):
# v2 loses 3.77 points to tax, a held-lots buy & hold loses 1.72, and the 2.05
# between them is the turnover cost. If dropping ONE NAME from the basket moves
# the benchmark's CAGR by more than that, the instrument cannot see the effect,
# and any edge printed against it is noise wearing a decimal point.
#
# So the limit is the top-name weight at which a single name's removal would move
# the benchmark CAGR by exactly the effect size:
#
#     drop a name of weight w  ->  terminal multiple M becomes M(1-w)
#     dCAGR = (1 + CAGR) * [ (1-w)^(1/y) - 1 ]
#     set dCAGR = -0.0205, solve for w:
#         w_max = 1 - [ 1 - 0.0205/(1+CAGR) ]^y
#
# Evaluated on the two universes actually measured, over the 2,705-day window:
#
#     n100   CAGR 23.97%   ->  w_max 11.62%
#     mid    CAGR 44.34%   ->  w_max 10.05%
#
# THE LIMIT TAKES THE MORE PERMISSIVE OF THE TWO, 11.62%, ON PURPOSE. Taking the
# tighter one would be choosing the number that rejects mid most comfortably,
# which is tuning a test to a verdict already known. The looser bound still
# rejects mid by a factor of 4.6 and still admits n100 with 3.5 points of margin,
# so the conclusion does not depend on which of the two was used -- and that
# insensitivity is the reason it can be stated as a choice rather than a fit.
#
# WHAT IT DOES NOT CLAIM. Passing does not make a basket well-diversified: n100's
# top name at 8.1% still moves the benchmark CAGR by -1.41 points, which is most
# of the effect being measured. It is a floor on usability, not a certificate.
# The number is pinned to a 7.4-year window and to these CAGRs; a materially
# different window needs it recomputed, not carried over.
CONC_LIMIT = 0.1162
CONC_LIMIT_BASIS = ("2.05-point effect size (n100 after-tax edge swing, 3f0ef05) "
                    "over a 2,705-day window at 23.97% CAGR")

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


# EVERYTHING BELOW RAN AT IMPORT UNTIL 2026-09-18, AND THAT WAS A DEFECT RATHER
# THAN A STYLE. This loop calls config.require_cache() on EVERY registered
# universe, so the module could only be imported on a machine where every
# universe had already been run. Registering midcap50 -- a universe this file has
# nothing to say about, and which it would have reported on for the first time
# only after a full run -- made `import bh_lots_after_tax` raise
# FileNotFoundError, and check_all.py GATE 1 went red on a wiring commit that had
# not touched this file.
#
# A MODULE THAT READS CACHES AT IMPORT BREAKS EVERY TIME A UNIVERSE IS
# REGISTERED. The failure is not about the new universe and cannot be fixed by
# anything done to it: running the pipeline hides this once, and listing the
# module as known-unimportable green-washes the gate and then fails the day the
# run happens. Moving the work behind the guard is what stops it recurring, and
# it is why this fires for the last time here.
#
# Nothing imports this module -- checked 2026-09-18 across the repository -- so
# the move costs no caller. `./venv/bin/python bh_lots_after_tax.py` behaves
# exactly as before.
def main(u):
    """One universe's after-tax comparison, and the artefact STEP 18 reads.

    ARITY 1, LIKE tax_report's. This looped REGISTRY internally until 2026-09-19,
    which was fine for a script run by hand and wrong for a PIPELINE_ORDER row:
    a whole-run step would put run.py:_resolve_arity in the position of refusing a
    None tag, and check_plan_order could not see that STEP 18 depends on THIS
    universe's file rather than on the loop having happened.

    IT WRITES BH_LOTS_<tag>_tax.csv, which is the whole reason it is a step.
    tax_report composes TAX_TURNOVER from this plus its own FY_EQUITY, so the
    buy&hold side of that comparison comes from a REAL RUN rather than from an
    untaxed log with arithmetic applied -- tax_report.py:22 records that the
    implied and charged figures differ by about 4% and that "the implied one
    describes a run that did not happen".

    THE EARLY RETURN IS THE tax=off CONTRACT, the same one tax_report uses: the
    row is always in PIPELINE_ORDER and always invoked, and decides at run time
    to do nothing. The artefact is ABSENT at tax=off, not empty.
    """
    import tax as _tax
    if not _tax.selected():
        print(f"    tax=off -- no bh_lots artefact for {u.tag} "
              f"(absent, not empty)")
        return
    tag = u.tag
    print("="*96)
    print(" v2 AFTER TAX vs BUY & HOLD AFTER TAX   (bh_lots: equal-rupee once, "
          "no rebalance, realise at end)")
    print("="*96)
    if True:
        engine_core.set_tradeability(u)
        p=pd.read_csv(config.require_cache(u.score_cache,what=tag),parse_dates=["date"])
        px=p.pivot_table(index="date",columns="symbol",values="close").ffill()
        op=p.pivot_table(index="date",columns="symbol",values="open").ffill()
        sc=p.pivot_table(index="date",columns="symbol",values="score")
        pc=precompute(px); mom20=px/px.shift(20)-1
        idx=(1+px.pct_change().mean(axis=1).fillna(0)).cumprod()
        pv=idx.pct_change().rolling(VOL_WIN).std()*np.sqrt(252)
        bd=px.index[(px.index>=config.BT_START_DATE)&(px.index<=config.BT_END_DATE)]
        kw=dict(mode="breadth",target_vol=pv.loc[bd].median(),rebal=cadence.selected(),
                **profiles.cap_kwargs(u))
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

        # THE LABELS SAY *WHEN*, NOT ONLY *WHETHER*. "after tax (settled)" was true
        # but silent on the thing that separates the two lines: v2 paid across the
        # window and lost the use of that capital; bh_lots pays once, at the end.
        _nded=int(stmt["assessed"].sum())
        # THE LABELS ARE BOUND ONCE AND REUSED as the res{} keys below. Repeating the
        # literal at the lookup is what broke when the wording changed.
        L_V2_POST=f"v2  after tax  ({_nded} deductions in-loop, tail settled at end)"
        L_BH_POST="bh_lots after tax  (nil in-loop, entire liability settled at end)"
        L_V2_PRE="v2  before tax"; L_BH_PRE="bh_lots before tax"
        L_BH_PUB="bh published (costless, daily-rebal)"
        rows=[(L_V2_PRE,v2_off),(L_V2_POST,v2_settled),
              (L_BH_PRE,bh_eq),(L_BH_POST,bh_settled),
              (L_BH_PUB,bh_pub)]
        print(f"\n  WHEN THE TAX LEFT CASH -- the two lines are not comparable along the path")
        print(f"      v2       deducted in-loop  Rs {a['tax']['cum_tax']:>12,.0f}"
              f"      settled at end  Rs {v2_unassessed:>12,.0f}")
        print(f"      bh_lots  deducted in-loop  Rs {0:>12,.0f}"
              f"      settled at end  Rs {bh_tx['total_tax']:>12,.0f}")
        print(f"\n  {'line':<66}{'FULL':>10}{'2019-2022':>12}{'2023-2026':>12}   final equity")
        res={}
        for lab,s in rows:
            full=cagr(s); res[lab]=full
            h=[cagr(s[(s.index.year>=y0)&(s.index.year<=y1)]) for _,y0,y1 in HALVES]
            print(f"  {lab:<66}{full:>9.2f}%{h[0]:>11.2f}%{h[1]:>11.2f}%   {s.iloc[-1]:>14,.0f}")
        print()
        for _l in (
          "  v2's capital-gains tax leaves cash on the first trading day at or after 31",
          "  March of each financial year, so it is gone before the next morning's fills and",
          "  the capital it removes stops compounding for the rest of the run. bh_lots",
          "  realises once at BT_END_DATE, and its entire liability falls due in FY2026-27 --",
          "  outside the window -- so nothing is deducted in-loop and both lines are settled",
          "  together at the final session. The two curves are therefore comparable at the",
          "  endpoint but not along the path: v2 has been paying since 2020, bh_lots pays",
          "  once at the end. bh_lots keeps the use of that capital for the whole window,",
          "  which is not an artefact of the settlement -- it is the deferral a low-turnover",
          "  book actually earns, and it is already inside the after-tax gap below rather",
          "  than missing from it."):
            print(_l)
        e_pre =res[L_V2_PRE]-res[L_BH_PRE]
        e_post=res[L_V2_POST]-res[L_BH_POST]
        e_pub =res[L_V2_PRE]-res[L_BH_PUB]
        # THE GATE. A concentrated basket does not get to print an edge at all.
        # Annotating the number was not enough: a figure gets copied out of a
        # terminal far more often than the caveat beside it does, and this file's own
        # docstring says so. So the number is WITHHELD and the reason takes its place.
        _v={s_:q*float(px.loc[bd[-1],s_]) for s_,(q,_b) in _SH.items()}
        _t=sum(_v.values()); _top=sorted(_v.items(),key=lambda x:-x[1])
        _w=_top[0][1]/_t
        _yrs=(bd[-1]-bd[0]).days/365.25
        _impact=(1+res[L_BH_PRE]/100)*((1-_w)**(1/_yrs)-1)*100
        print(f"\n  bh_lots concentration: top name {_top[0][0]} = {_w*100:.1f}% of terminal "
              f"value, top 3 = {sum(v for _,v in _top[:3])/_t*100:.1f}%")
        print(f"      dropping that one name would move the benchmark CAGR by "
              f"{_impact:+.2f} pts   (limit {CONC_LIMIT*100:.2f}%)")
        if _w > CONC_LIMIT:
            print(f"\n  EDGE  ** WITHHELD **  top-name weight {_w*100:.1f}% exceeds the "
                  f"{CONC_LIMIT*100:.2f}% limit by {_w/CONC_LIMIT:.1f}x.")
            print(f"        This basket cannot resolve the effect it is being asked to")
            print(f"        measure: one name moves it {abs(_impact):.2f} pts, against an effect")
            print(f"        size of 2.05. The universe is SURVIVORSHIP_MODE=static -- today's")
            print(f"        members backfilled -- so {_top[0][0]} is in this basket because of the")
            print(f"        run it had. Any edge printed here would be that one name's history.")
            print(f"        Limit basis: {CONC_LIMIT_BASIS}.")
        else:
            print(f"\n  EDGE  v2 - bh_lots   before tax {e_pre:+.2f} pts      after tax {e_post:+.2f} pts"
                  f"      swing {e_post-e_pre:+.2f}")
        print(f"  EDGE  v2 - bh published (the +0.89/+0.43 baseline) {e_pub:+.2f} pts"
              f"   [costless daily-rebalanced index, untaxable -- reference only]")

        # ------------------------------------------------------------------
        # THE ARTEFACT. Five measured lines plus the three gap rows, which is
        # what this whole axis exists to produce.
        # ------------------------------------------------------------------
        # WITHHELD IS A ROW, NOT A MISSING ROW. The guard above refuses to PRINT
        # a number a concentrated basket cannot resolve; the file records the
        # refusal in its own column rather than omitting the line, because an
        # absent row reads as "not computed" and this was computed and rejected.
        # The step does NOT fail: a withheld edge is a correct outcome.
        _withheld = _w > CONC_LIMIT
        _reason = ("" if not _withheld else
                   f"top-name weight {_w*100:.1f}% exceeds the {CONC_LIMIT*100:.2f}% "
                   f"limit by {_w/CONC_LIMIT:.1f}x; {_top[0][0]} alone moves the "
                   f"benchmark {_impact:+.2f} pts against an effect size of 2.05, "
                   f"and the universe is SURVIVORSHIP_MODE=static so that name is "
                   f"in the basket because of the run it had")
        _v2_tax_total = float(a["tax"]["cum_tax"]) + v2_unassessed
        _lines = [
            ("v2 before tax",      L_V2_PRE,  v2_off,      0.0),
            ("v2 after tax",       L_V2_POST, v2_settled,  _v2_tax_total),
            ("bh_lots before tax", L_BH_PRE,  bh_eq,       0.0),
            ("bh_lots after tax",  L_BH_POST, bh_settled,  float(bh_tx["total_tax"])),
            ("bh published",       L_BH_PUB,  bh_pub,      float("nan")),
        ]
        _out = []
        for _key, _lab, _s, _paid in _lines:
            _h = [cagr(_s[(_s.index.year >= y0) & (_s.index.year <= y1)])
                  for _, y0, y1 in HALVES]
            _out.append({"line": _key, "cagr_full": round(res[_lab], 4),
                         "cagr_2019_2022": round(_h[0], 4),
                         "cagr_2023_2026": round(_h[1], 4),
                         "final_equity": round(float(_s.iloc[-1]), 2),
                         "tax_paid": ("" if _paid != _paid else round(_paid, 2)),
                         "withheld_reason": ""})
        _out.append({"line": "gap_before_tax", "cagr_full": round(e_pre, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "", "withheld_reason": ""})
        _out.append({"line": "gap_after_tax", "cagr_full": round(e_post, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "", "withheld_reason": ""})
        _out.append({"line": "TAX_COST_OF_TURNOVER",
                     "cagr_full": "" if _withheld else round(e_post - e_pre, 4),
                     "cagr_2019_2022": "", "cagr_2023_2026": "",
                     "final_equity": "", "tax_paid": "",
                     "withheld_reason": _reason})
        import audit_step as _as
        _atag = _as.artefact_tag(u, "v2")
        _p = Path(u.metrics_dir) / f"BH_LOTS_{_atag}.csv"
        # naming: arm,cadence,profile,tax via artefact_tag -- `_atag` is
        # audit_step.artefact_tag's output and already carries all four axes, so
        # the stem is appended and NOTHING else. Same rule, and the same reason,
        # as tax_report.py's four artefacts: this file exists only under tax=on.
        pd.DataFrame(_out).to_csv(_p, index=False)
        print(f"\n  saved -> {_p.name}"
              + ("   [TAX_COST_OF_TURNOVER withheld]" if _withheld else ""))


if __name__ == "__main__":
    # STANDALONE, BY TAG, like every other per-universe step.
    import sys as _s
    if len(_s.argv) != 2 or _s.argv[1] not in REGISTRY:
        raise SystemExit(f"usage: {Path(__file__).name} <universe>   "
                         f"known: {', '.join(sorted(REGISTRY))}")
    raise SystemExit(main(REGISTRY[_s.argv[1]]))