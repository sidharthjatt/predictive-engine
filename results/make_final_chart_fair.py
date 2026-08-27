"""
make_final_chart_fair.py -- Final chart: return + drawdown + cash%
The legend shows invested %, and before/after transaction costs, so the
comparison is transparent.

THE BENCHMARK WAS WRONG AND IS NOW FIXED
    The previous version built its "Nifty100" line as the equal-weighted mean of
    every CSV in data/raw/nifty100_benchmark/. That was wrong twice over:

    1. glob("*.csv") swept NIFTY100.csv -- the published index itself -- into the
       basket as if it were a 100th constituent, so the index was averaged
       together with its own members.
    2. Even without that, an equal-weighted average of the 99 constituents is not
       the Nifty 100. Nifty 100 is free-float capitalisation-weighted; NSE
       publishes "Nifty100 Equal Weight" as a SEPARATE index with different
       returns. The basket also used today's membership backfilled to 2019, so it
       was survivorship-biased and not investable: it silently assumed you knew
       in 2019 which names would be in the index in 2026.

    The benchmark is now read directly from NIFTY100.csv, the genuine
    cap-weighted series (base 1-Jan-2003 = 1000; the file reads 1008.0 on
    2003-01-02, consistent with NSE's published methodology).

    The 99-name equal-weighted basket has been REMOVED rather than relabelled.
    Keeping it, even correctly labelled, leaves a survivorship-biased and
    non-investable line on a chart whose whole purpose is a fair comparison, and
    the mislabelled version of it is what produced the false subtitle claim this
    file used to carry.

WHAT THE CHART NOW CLAIMS
    Against the cap-weighted index the strategies win. Against an equal-weight
    buy&hold of their own universe they lose. The old subtitle -- "both beat
    benchmark per rupee invested" -- was measured against the EW basket and is
    not true of the index-plus-universe pair, so it has been rewritten to state
    both comparisons plainly rather than only the flattering one.

Writes chart PNGs and the fair-comparison table. Reads everything else.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, config74
import survivorship as sv

M58=config.METRICS_DIR; M74=config74.METRICS_DIR_74
N100=Path(__file__).resolve().parents[1]/"data"/"raw"/"nifty100_benchmark"
INDEX_FILE="NIFTY100.csv"
CAP=1_000_000
def cum(s): return (s/s.iloc[0]-1)*100
def dd(s): return (s/s.cummax()-1)*100
def cagr(s):
    y=(s.index[-1]-s.index[0]).days/365.25
    return ((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100

# ---------------------------------------------------------------- benchmark
# Read the published index directly. No basket, no averaging, no glob.
idx_raw=(config.read_price_csv(N100/INDEX_FILE)[["date","close"]].dropna()
         .set_index("date")["close"].sort_index())

def index_on(window_index):
    """The index over a strategy's own dates, rebased to the same starting
    capital so the lines are comparable on one axis."""
    s=idx_raw.reindex(window_index.union(idx_raw.index)).ffill().reindex(window_index)
    return CAP*s/s.iloc[0]

# ------------------------------------------------------------ strategy data
eq58=pd.read_csv(M58/"v2FINAL_equity.csv",parse_dates=["date"]).set_index("date")
eq74=pd.read_csv(M74/"v2FINAL_equity.csv",parse_dates=["date"]).set_index("date")
c58=pd.read_csv(M58/"cash_series_58.csv",parse_dates=["date"]).set_index("date")
c74=pd.read_csv(M74/"cash_series_74.csv",parse_dates=["date"]).set_index("date")
i58=100-c58.cash_pct.mean(); i74=100-c74.cash_pct.mean()

def before_tc(eq_series, tc_by_date):
    """CAGR with the transaction-cost drag removed from the realised path.

    Method: r_gross(t) = r_net(t) + tc(t)/equity(t-1), then compounded. This
    removes the cost drag day by day while holding the realised positions fixed.
    It is NOT a re-run with zero costs -- position sizes would differ then -- so
    it is reported as "cost drag removed" rather than as a separate backtest.
    """
    tc=tc_by_date.reindex(eq_series.index).fillna(0.0)
    r=eq_series.pct_change().fillna(0.0)+(tc/eq_series.shift(1)).fillna(0.0)
    g=(1+r).cumprod()*eq_series.iloc[0]
    # tc.sum() is the cost falling inside THIS window, so it shrinks correctly on
    # the matched-window chart. The trade COUNT comes from TC_SRC, not from here:
    # tc_by_date is grouped by date, so counting it would report rebalance days
    # (93) instead of trades (921).
    return cagr(g), tc.sum()


def tc_from_log(path):
    """Dated transaction costs from a saved per-trade log (the v2 strategies).
    Returns the per-date cost AND the per-trade dates, so a truncated window can
    report the trades that actually fall inside it."""
    tr=pd.read_csv(path,parse_dates=["date"])
    return tr.groupby("date")["tc"].sum(), tr["date"]


# Every cost series is READ, never recomputed. The v1 baseline's log used to be
# unavailable -- engine_v2_final.py kept only its totals -- so an earlier version of
# this file re-ran the baseline to recover the dated costs. The engines now persist
# daily_trades_v1_*.csv, so the numbers come from the run that produced the equity
# curve rather than from a reproduction of it, and this script needs no model
# libraries and does no backtesting.
TC_SRC={
 "58 v2": tc_from_log(M58/"daily_trades_58.csv"),
 "74 v2": tc_from_log(M74/"daily_trades_74.csv"),
 "58 v1": tc_from_log(M58/"daily_trades_v1_58.csv"),
 "74 v1": tc_from_log(M74/"daily_trades_v1_74.csv"),
}



def build_series(e58,e74,cash58,cash74):
    """The lines, for whichever windows e58/e74 cover. Invested% is recomputed
    from the cash series actually passed in, so the matched-window chart reports
    its own window's average rather than the full window's."""
    i58,i74=100-cash58.mean(),100-cash74.mean()

    def traded(s, key):
        """Legend text for a series that pays transaction costs. Counts only the
        trades inside this chart's window, so the matched chart is self-consistent."""
        b,tot=before_tc(s, TC_SRC[key][0])
        n=int((TC_SRC[key][1]<=s.index[-1]).sum())
        return (f"CAGR {b:.2f}% before TC / {cagr(s):.2f}% after TC  "
                f"[{n} trades, Rs {tot:,.0f}]")

    # Buy&hold and the index get an EXPLICIT no-TC statement rather than a blank.
    # A missing before-TC figure next to lines that have one reads as an oversight;
    # here it is a fact about the series. Buy&hold is bought once and held, so its
    # trade count in v2FINAL_comparison.csv is 0. The index is a published price
    # level, not a portfolio, so no cost applies to it at all.
    NOTC_BH="(buy once, hold: no TC)"
    NOTC_IX="(index level, not a portfolio: no TC)"
    return [
     (f"58 v2 (breadth)  [inv {i58:.0f}%]", e58["strategy"], "#ff9999","-", cash58,
      traded(e58["strategy"],"58 v2")),
     (f"58 v1 (inv-vol)  [inv 100%]", e58["baseline_invvol"], "#7fb3e0","-", None,
      traded(e58["baseline_invvol"],"58 v1")),
     (f"58 buy&hold (equal-weight universe)  [inv 100%]", e58["buyhold"], "#8fd08f","-", None,
      f"CAGR {cagr(e58['buyhold']):.2f}%  {NOTC_BH}"),
     (f"74 v2 (breadth)  [inv {i74:.0f}%]", e74["strategy"], "#c0392b","-", cash74,
      traded(e74["strategy"],"74 v2")),
     (f"74 v1 (inv-vol)  [inv 100%]", e74["baseline_invvol"], "#2e6da4","-", None,
      traded(e74["baseline_invvol"],"74 v1")),
     (f"74 buy&hold (equal-weight universe)  [inv 100%]", e74["buyhold"], "#3a9d3a","-", None,
      f"CAGR {cagr(e74['buyhold']):.2f}%  {NOTC_BH}"),
     # ONE index line, not two. The previous version drew the index over the 58
     # window and again over the 74 window; both rebase at the same start date, so
     # they are the identical series and merely stop on different days. Two
     # overlapping lines read as two different benchmarks. The window dependence is
     # real and worth showing, so it is stated in the label instead: the index's own
     # CAGR swings 10.93% vs 13.34% purely on where the window ends, which is the
     # reason the matched-window chart exists.
     ("NIFTY100 (cap-weighted index)  [inv 100%]", index_on(e58.index), "#000000","--", None,
      _index_label(e58,e74)),
    ]


def _index_label(e58,e74):
    a,b=cagr(index_on(e58.index)),cagr(index_on(e74.index))
    notc="(index level, not a portfolio: no TC)"
    if e58.index[-1]==e74.index[-1]:
        return f"CAGR {a:.2f}%  {notc}"
    return (f"CAGR {a:.2f}% to {e58.index[-1].date()}  |  "
            f"{b:.2f}% to {e74.index[-1].date()}  {notc}")


def subtitle(e58,e74,cash58,cash74,win_note=""):
    """State BOTH comparisons. The strategies beat the cap-weighted index and
    lose to an equal-weight buy&hold of their own universe; saying only the first
    is what the previous subtitle did."""
    s58,s74=cagr(e58["strategy"]),cagr(e74["strategy"])
    h58,h74=cagr(e58["buyhold"]),cagr(e74["buyhold"])
    n58,n74=cagr(index_on(e58.index)),cagr(index_on(e74.index))
    nx=f"{n58:.2f}%" if e58.index[-1]==e74.index[-1] else f"{n58:.2f}% / {n74:.2f}%"
    d58,d74=s58*100/(100-cash58.mean()),s74*100/(100-cash74.mean())
    return ("Strategies + Buy&Hold + NIFTY100 cap-weighted index  |  [inv X%] = avg capital deployed  |  "
            "ALL NUMBERS AFTER TC (Zerodha + 0.15% slippage)"+win_note+"\n"
            f"vs INDEX: 58 v2 {s58:.2f}% and 74 v2 {s74:.2f}% both beat NIFTY100 ({nx}).  "
            f"vs OWN UNIVERSE: both LOSE to equal-weight buy&hold ({h58:.2f}% / {h74:.2f}%).\n"
            f"On deployed capital only, 58 v2 = {d58:.2f}% and 74 v2 = {d74:.2f}%; that adjusts for idle cash "
            f"but does not make the buy&hold comparison favourable."
            + _window_note(e58,e74)
            # Names the universe construction on the chart's own face. In static mode
            # this says the result carries survivorship bias, so nobody six months
            # from now reads a biased number as a clean one.
            + "\n" + sv.describe_state())


def _window_note(e58,e74):
    """The two universes stop on different days, and that alone moves the index
    CAGR by 2.4 points (10.93% to 2026-06-08 vs 13.34% to 2025-12-23) on the same
    series. A reader comparing 58 against 74 on this chart is therefore partly
    reading a calendar difference, and should not have to know that a second file
    exists to find that out."""
    if e58.index[-1]==e74.index[-1]:
        return ""
    a,b=cagr(index_on(e58.index)),cagr(index_on(e74.index))
    return ("\nWINDOWS DIFFER: 58 ends {} but 74 ends {}. On the SAME index that end date alone moves CAGR "
            "{:.2f}% vs {:.2f}% ({:+.2f} pts), so 58-vs-74 here is not like-for-like.\n"
            "For the matched comparison see chart_FINAL_58_74_N100_matched.png, where both are cut to {}."
            ).format(e58.index[-1].date(), e74.index[-1].date(), a, b, a-b, e74.index[-1].date())


def draw(series, title, outfile):
    fig,ax=plt.subplots(3,1,figsize=(16,14),height_ratios=[2,1,1])
    for lab,s,c,ls,_,extra in series:
        leg=f"{lab}  "+(extra if extra else f"CAGR {cagr(s):.2f}%")
        ax[0].plot(s.index,cum(s),lw=1.9,color=c,ls=ls,label=leg)
    ax[0].axhline(0,color="k",lw=.6,alpha=.5); ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(title,fontsize=10.5)
    ax[0].legend(loc="upper left",fontsize=8,ncol=2); ax[0].grid(alpha=.3)

    for lab,s,c,ls,_,_x in series:
        ax[1].plot(s.index,dd(s),lw=1.3,color=c,ls=ls,
                   label=f"{lab.split('[')[0].strip()} ({dd(s).min():.0f}%)")
    ax[1].set_ylabel("Drawdown (%)"); ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left",fontsize=7,ncol=2); ax[1].grid(alpha=.3)

    for lab,s,c,ls,cash,_x in series:
        if cash is not None:
            ax[2].plot(cash.index,cash,lw=1.6,color=c,
                       label=f"{lab.split('[')[0].strip()} (avg {cash.mean():.0f}%)")
            ax[2].fill_between(cash.index,cash,0,color=c,alpha=.15)
    ax[2].axhline(0,color="k",lw=1,alpha=.6)
    ax[2].text(0.02,0.9,"All other lines: 0% cash (100% invested)",
               transform=ax[2].transAxes,fontsize=8,color="grey")
    ax[2].set_ylabel("Unutilized cash (%)\ncash/(cash+mtm)")
    ax[2].yaxis.set_major_formatter(PercentFormatter(decimals=0)); ax[2].set_ylim(0,100)
    ax[2].legend(loc="upper right",fontsize=8); ax[2].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(outfile,dpi=140,bbox_inches="tight"); plt.close()
    print(f"saved -> {Path(outfile).name}")


# ------------------------------------------------- verification, before plotting
print("="*94)
print(" BENCHMARK VERIFICATION -- printed before anything is plotted")
print("="*94)
print(f"\n  index file        : {INDEX_FILE}  (read directly, NOT averaged into a basket)")
print(f"  constituent CSVs  : {len(list(N100.glob('*.csv')))-1} constituents + 1 index file "
      f"= {len(list(N100.glob('*.csv')))} CSVs in folder")
print(f"  base check        : {idx_raw.index[0].date()} = {idx_raw.iloc[0]:,.2f}  "
      f"(NSE base 1-Jan-2003 = 1000)")
print(f"  full series       : {idx_raw.index[0].date()} -> {idx_raw.index[-1].date()}, "
      f"{len(idx_raw):,} rows")
_w=idx_raw[idx_raw.index>=pd.Timestamp('2019-01-01')]
_y=(_w.index[-1]-_w.index[0]).days/365.25
print(f"\n  VERIFIED WINDOW 2019-01-01 -> {_w.index[-1].date()}:")
print(f"    {_w.iloc[0]:,.2f} -> {_w.iloc[-1]:,.2f}  = {_w.iloc[-1]/_w.iloc[0]:.4f}x  "
      f"over {_y:.4f}y  = CAGR {((_w.iloc[-1]/_w.iloc[0])**(1/_y)-1)*100:.4f}%")
print("    expected: 11,148.80 -> 25,209.55 = 2.26x = 11.54% CAGR")

print("\n  NOTE: the strategy windows END EARLIER than the index series, so the")
print("  index CAGR quoted on each chart is measured over that strategy's own")
print("  window and differs from the 11.54% full-window figure above:")
for nm,e in (("58 window",eq58),("74 window",eq74)):
    s=index_on(e.index)
    print(f"    {nm}: {e.index[0].date()} -> {e.index[-1].date()}   index CAGR {cagr(s):.4f}%")

print("\n" + "="*94)
print(" CORRECTED NUMBERS")
print("="*94)
rows=[]
def addrow(lab,s,cashpct,btc=None):
    r=s.pct_change().dropna(); y=(s.index[-1]-s.index[0]).days/365.25
    cg=((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100
    sh=r.mean()/r.std()*(252**0.5) if r.std()>0 else 0
    ddv=((s-s.cummax())/s.cummax()).min()*100
    inv=100-cashpct
    # Column names "Strategy" and "CAGR%" are the schema make_final_summary.py
    # reads; they are kept exactly. CAGR% remains the AFTER-TC figure it always
    # was, and before-TC is added as a new column rather than by renaming.
    rows.append({"Strategy":lab,"CAGR%":round(cg,2),
                 "CAGR%_beforeTC":round(btc,2) if btc is not None else None,
                 "Sharpe":round(sh,2),"MaxDD%":round(ddv,2),
                 "AvgInvested%":round(inv,1),"AvgCash%":round(cashpct,1),
                 "CAGR_per_InvestedCapital%":round(cg*100/inv,2) if inv>0 else None})
EQ_FOR={"58 v2":eq58["strategy"],"58 v1":eq58["baseline_invvol"],
        "74 v2":eq74["strategy"],"74 v1":eq74["baseline_invvol"]}
B={k:before_tc(s,TC_SRC[k][0]) for k,s in
   (("58 v2",eq58["strategy"]),("58 v1",eq58["baseline_invvol"]),
    ("74 v2",eq74["strategy"]),("74 v1",eq74["baseline_invvol"]))}
addrow("58 v2 (breadth)",eq58["strategy"],c58.cash_pct.mean(),B["58 v2"][0])
addrow("58 v1 (inv-vol)",eq58["baseline_invvol"],0.0,B["58 v1"][0])
addrow("58 buy&hold (equal-weight universe)",eq58["buyhold"],0.0)
addrow("74 v2 (breadth)",eq74["strategy"],c74.cash_pct.mean(),B["74 v2"][0])
addrow("74 v1 (inv-vol)",eq74["baseline_invvol"],0.0,B["74 v1"][0])
addrow("74 buy&hold (equal-weight universe)",eq74["buyhold"],0.0)
addrow("NIFTY100 (cap-weighted index, 58 win)",index_on(eq58.index),0.0)
addrow("NIFTY100 (cap-weighted index, 74 win)",index_on(eq74.index),0.0)
tbl=pd.DataFrame(rows)
print("\n"+tbl.to_string(index=False))

# Cross-check the trade logs against the engines' own reported totals. Both sides
# are engine output: the per-trade logs and v2FINAL_comparison.csv are written by
# the same run, so a disagreement means the log does not belong to the curve.
CMP={u:pd.read_csv(m/"v2FINAL_comparison.csv") for u,m in (("58",M58),("74",M74))}
def reported(u,v1):
    df=CMP[u]; row=df[df["Config"].str.contains("Inverse-vol" if v1 else "breadth scaling")]
    return int(row["Trades"].iloc[0]), float(row["TC_Rs"].iloc[0])

print("\n  TRANSACTION COSTS -- every traded series, so each figure is checkable:")
print(f"    {'series':<8} {'trades':>7} {'cum TC Rs':>11} {'before TC':>10} {'after TC':>9} "
      f"{'drag':>7}   vs v2FINAL_comparison.csv")
ok=True
for k in ("58 v2","58 v1","74 v2","74 v1"):
    b,tot=B[k]; n=len(TC_SRC[k][1])
    a=cagr(eq58["strategy"] if k=="58 v2" else eq58["baseline_invvol"] if k=="58 v1"
           else eq74["strategy"] if k=="74 v2" else eq74["baseline_invvol"])
    rn,rt=reported(k[:2], k.endswith("v1"))
    match = (n==rn) and abs(tot-rt)<1.0
    ok &= match
    print(f"    {k:<8} {n:>7} {tot:>11,.0f} {b:>9.2f}% {a:>8.2f}% {b-a:>6.2f}pp   "
          f"{rn} / Rs {rt:,.0f}  {'MATCH' if match else '*** MISMATCH ***'}")
print(f"    -> all four reconcile: {ok}")
print("    Both sides are engine output: the per-trade logs and v2FINAL_comparison.csv")
print("    are written by the same run, so this checks the log belongs to the curve.")
print("    58/74 buy&hold: 0 trades, Rs 0 -- bought once and held.")
print("    NIFTY100: a published index level, not a portfolio; no TC applies.")
print("  before-TC = cost drag removed from the realised path, not a zero-cost re-run.")
print("\n  REMOVED from this chart: the 99-name equal-weighted basket that was")
print("  previously mislabelled 'Nifty100'. It is not the Nifty 100 (that index is")
print("  cap-weighted), it used current membership backfilled to 2019, and it was")
print("  therefore survivorship-biased and not investable.")

# ------------------------------------------------------------------- chart 1
draw(build_series(eq58,eq74,c58.cash_pct,c74.cash_pct),
     subtitle(eq58,eq74,c58.cash_pct,c74.cash_pct), M58/"chart_FINAL_58_74_N100.png")

# ------------------------------------------- chart 2: matched window (58 cut to 74)
end=min(eq58.index[-1],eq74.index[-1])
e58m=eq58[eq58.index<=end]; e74m=eq74[eq74.index<=end]
c58m=c58[c58.index<=end].cash_pct; c74m=c74[c74.index<=end].cash_pct
print("\n" + "="*94)
print(f" MATCHED WINDOW -- both universes truncated to {end.date()}")
print("="*94)
mrows=[]
for lab,s in (("58 v2",e58m["strategy"]),("58 buy&hold",e58m["buyhold"]),
              ("74 v2",e74m["strategy"]),("74 buy&hold",e74m["buyhold"]),
              ("NIFTY100 index",index_on(e58m.index))):
    mrows.append({"Series":lab,"CAGR%":round(cagr(s),2),"MaxDD%":round(dd(s).min(),2)})
print("\n"+pd.DataFrame(mrows).to_string(index=False))
draw(build_series(e58m,e74m,c58m,c74m),
     subtitle(e58m,e74m,c58m,c74m,f"  |  MATCHED WINDOW to {end.date()}"),
     M58/"chart_FINAL_58_74_N100_matched.png")

tbl.to_csv(M58/"fair_comparison_table.csv",index=False)
print("\nsaved -> fair_comparison_table.csv")
