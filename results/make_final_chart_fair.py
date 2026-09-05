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
import config
import survivorship as sv
from universes.registry import REGISTRY

# config74 is imported inside main() under the 74's guard. At module level a
# deleted config74.py would make this step unimportable, taking the 58's half of
# the chart down with the 74's.
def cum(s): return (s/s.iloc[0]-1)*100
def dd(s): return (s/s.cummax()-1)*100
def cagr(s):
    y=(s.index[-1]-s.index[0]).days/365.25
    return ((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100
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


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything here used to run at module level,
    so importing this file executed the whole step as a side effect -- which is
    why the pipeline could only ever spawn it as a subprocess.

    Imports, helper defs and import-time setup stay at module level; every
    other statement moved, constants included, so no dependency chain is split.
    """
    def subtitle(EQ,CASH,win_note=""):
        """State BOTH comparisons. The strategies beat the cap-weighted index and
        lose to an equal-weight buy&hold of their own universe; saying only the first
        is what the previous subtitle did.

        WRITTEN OVER WHICHEVER UNIVERSES ARE PRESENT, and reduced to the identical
        string when both are: "both beat" / "both LOSE" become "beats" / "LOSES" for
        one, and the joins collapse. Verified byte-identical against the two-universe
        baseline.
        """
        tags=list(EQ)
        sX={t:cagr(EQ[t]["strategy"]) for t in tags}
        hX={t:cagr(EQ[t]["buyhold"]) for t in tags}
        nX={t:cagr(index_on(EQ[t].index)) for t in tags}
        ends={EQ[t].index[-1] for t in tags}
        nx=(f"{nX[tags[0]]:.2f}%" if len(ends)==1
            else " / ".join(f"{nX[t]:.2f}%" for t in tags))
        dX={t:sX[t]*100/(100-CASH[t].mean()) for t in tags}
        both=len(tags)>1
        return ("Strategies + Buy&Hold + NIFTY100 cap-weighted index  |  [inv X%] = avg capital deployed  |  "
                "ALL NUMBERS AFTER TC (Zerodha + 0.15% slippage)"+win_note+"\n"
                f"vs INDEX: " + " and ".join(f"{t} v2 {sX[t]:.2f}%" for t in tags)
                + f" {'both beat' if both else 'beats'} NIFTY100 ({nx}).  "
                f"vs OWN UNIVERSE: {'both LOSE' if both else 'LOSES'} to equal-weight buy&hold ("
                + " / ".join(f"{hX[t]:.2f}%" for t in tags) + ").\n"
                f"On deployed capital only, "
                + " and ".join(f"{t} v2 = {dX[t]:.2f}%" for t in tags)
                + "; that adjusts for idle cash "
                f"but does not make the buy&hold comparison favourable."
                + _window_note(EQ)
                # Names the universe construction on the chart's own face. In static mode
                # this says the result carries survivorship bias, so nobody six months
                # from now reads a biased number as a clean one.
                + "\n" + sv.describe_state())
    # THESE HELPERS CLOSE OVER main()'s LOCALS, so they live inside it.
    # Leaving them at module level while the names they read moved in here
    # raised NameError at the first call -- the wrap is only sound if a
    # helper travels with the state it reads.
    def index_on(window_index):
        """The index over a strategy's own dates, rebased to the same starting
        capital so the lines are comparable on one axis."""
        s=idx_raw.reindex(window_index.union(idx_raw.index)).ffill().reindex(window_index)
        return CAP*s/s.iloc[0]
    def build_series(EQ,CASH):
        """The lines, for whichever windows EQ covers. Invested% is recomputed
        from the cash series actually passed in, so the matched-window chart reports
        its own window's average rather than the full window's."""
        iX={t:100-CASH[t].mean() for t in EQ}

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
        # THREE LINES PER UNIVERSE, IN REGISTRY ORDER, with that universe's colours.
        # Emitted as a loop so a removed universe takes exactly its own three lines
        # with it; the order and the colours are identical to the two hand-written
        # blocks this replaced.
        out=[]
        for t in EQ:
            c_v2,c_v1,c_bh = COLOURS[t]
            e=EQ[t]
            out += [
             (f"{t} v2 (breadth)  [inv {iX[t]:.0f}%]", e["strategy"], c_v2,"-", CASH[t],
              traded(e["strategy"],f"{t} v2")),
             (f"{t} v1 (inv-vol)  [inv 100%]", e["baseline_invvol"], c_v1,"-", None,
              traded(e["baseline_invvol"],f"{t} v1")),
             (f"{t} buy&hold (equal-weight universe)  [inv 100%]", e["buyhold"], c_bh,"-", None,
              f"CAGR {cagr(e['buyhold']):.2f}%  {NOTC_BH}"),
            ]
        return out + [
         # ONE index line, not two. The previous version drew the index over the 58
         # window and again over the 74 window; both rebase at the same start date, so
         # they are the identical series and merely stop on different days. Two
         # overlapping lines read as two different benchmarks. The window dependence is
         # real and worth showing, so it is stated in the label instead: the index's own
         # CAGR swings 10.93% vs 13.34% purely on where the window ends, which is the
         # reason the matched-window chart exists.
         ("NIFTY100 (cap-weighted index)  [inv 100%]",
          index_on(EQ[list(EQ)[0]].index), "#000000","--", None,
          _index_label(EQ)),
        ]
    def _index_label(EQ):
        tags=list(EQ)
        notc="(index level, not a portfolio: no TC)"
        vals={t:cagr(index_on(EQ[t].index)) for t in tags}
        if len({EQ[t].index[-1] for t in tags})==1:
            return f"CAGR {vals[tags[0]]:.2f}%  {notc}"
        return ("  |  ".join(f"CAGR {vals[t]:.2f}% to {EQ[t].index[-1].date()}" if i==0
                             else f"{vals[t]:.2f}% to {EQ[t].index[-1].date()}"
                             for i,t in enumerate(tags))
                + f"  {notc}")
    def _window_note(EQ):
        """The two universes stop on different days, and that alone moves the index
        CAGR by 2.4 points (10.93% to 2026-06-08 vs 13.34% to 2025-12-23) on the same
        series. A reader comparing 58 against 74 on this chart is therefore partly
        reading a calendar difference, and should not have to know that a second file
        exists to find that out.

        WITH ONE UNIVERSE THERE IS NO WINDOW DIFFERENCE, so this is empty -- the same
        answer it already gave when the two windows happened to coincide.
        """
        tags=list(EQ)
        if len({EQ[t].index[-1] for t in tags})==1:
            return ""
        t0,t1=tags[0],tags[-1]
        e58,e74=EQ[t0],EQ[t1]
        a,b=cagr(index_on(e58.index)),cagr(index_on(e74.index))
        return ("\nWINDOWS DIFFER: {} ends {} but {} ends {}. On the SAME index that end date alone moves CAGR "
                "{:.2f}% vs {:.2f}% ({:+.2f} pts), so {}-vs-{} here is not like-for-like.\n"
                "For the matched comparison see {}, where both are cut to {}."
                ).format(t0, e58.index[-1].date(), t1, e74.index[-1].date(), a, b, a-b,
                         t0, t1, MATCHED_NAME, e74.index[-1].date())
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
    def reported(u,v1):
        df=CMP[u]; row=df[df["Config"].str.contains("Inverse-vol" if v1 else "breadth scaling")]
        return int(row["Trades"].iloc[0]), float(row["TC_Rs"].iloc[0])
    # ---------------------------------------------------------------- universes
    # WHICHEVER OF 58 AND 74 IS REGISTERED. Unlike the combined n100/mid chart,
    # this one compares STRATEGY AGAINST BENCHMARK, which stays meaningful with a
    # single universe -- so it runs on what remains and only skips when both are
    # gone. Registry order is preserved, so with both present every series, colour
    # and label is in exactly the position it was.
    COLOURS={"58":("#ff9999","#7fb3e0","#8fd08f"),
             "74":("#c0392b","#2e6da4","#3a9d3a")}
    # M58 / M74 ARE ASSIGNED IN THE PLAIN `VAR = config*.METRICS_DIR*` SHAPE, and
    # every path below is built from them rather than from METRICS[t]. That is what
    # check_pipeline_order's DIR_ASSIGN recognises: a dict subscript resolves to
    # nothing, and routing the reads through one made this file's four producer
    # edges vanish -- 27 down to 24 -- without changing a line of behaviour. The
    # dict still exists for iteration; the literals exist for the checker.
    METRICS={}
    EQF={}; CMPF={}; CASHF={}; TRF={}
    if "58" in REGISTRY:
        M58=config.METRICS_DIR
        METRICS["58"]=M58
        EQF["58"]=M58/"v2FINAL_equity.csv"
        CMPF["58"]=M58/"v2FINAL_comparison.csv"
        CASHF["58"]=M58/"cash_series_58.csv"
        TRF["58 v2"]=M58/"daily_trades_58.csv"
        TRF["58 v1"]=M58/"daily_trades_v1_58.csv"
    if "74" in REGISTRY:
        import config74
        M74=config74.METRICS_DIR_74
        METRICS["74"]=M74
        EQF["74"]=M74/"v2FINAL_equity.csv"
        CMPF["74"]=M74/"v2FINAL_comparison.csv"
        CASHF["74"]=M74/"cash_series_74.csv"
        TRF["74 v2"]=M74/"daily_trades_74.csv"
        TRF["74 v1"]=M74/"daily_trades_v1_74.csv"
    if not METRICS:
        print("="*94)
        print(" FINAL fair chart SKIPPED -- neither 58 nor 74 is registered.")
        print(" This step compares those two retired universes against the NIFTY100")
        print(" index; with both removed there is nothing to chart and no")
        print(" fair_comparison_table.csv is written. make_final_summary.py, which")
        print(" reads that table, skips for the same reason.")
        print("="*94)
        return

    TAGS=list(METRICS)
    OUT_DIR=METRICS[TAGS[0]]
    CHART_NAME="chart_FINAL_"+"_".join(TAGS)+"_N100.png"
    MATCHED_NAME="chart_FINAL_"+"_".join(TAGS)+"_N100_matched.png"

    # ------------------------------------------------- the benchmark, and what it is NOT
    # NIFTY100 HERE IS A PRICE FILE, NOT THE n100 UNIVERSE. They share four
    # characters and nothing else:
    #   this          data/raw/nifty100_benchmark/NIFTY100.csv -- the published
    #                 cap-weighted index level, read directly, never averaged;
    #   the universe  REGISTRY["n100"] -- 99 equal-weighted constituents scored and
    #                 traded by the engine, whose metrics live in results_n100/.
    # Removing the n100 UNIVERSE must not touch this benchmark, and this step does
    # not consult REGISTRY for it. The project has already made the inverse mistake
    # once -- an equal-weighted basket of 99 names was labelled "Nifty100" and
    # reported as the index -- which is why the distinction is asserted here rather
    # than left to the reader.
    N100=Path(__file__).resolve().parents[1]/"data"/"raw"/"nifty100_benchmark"
    INDEX_FILE="NIFTY100.csv"
    assert N100.is_dir() and (N100/INDEX_FILE).exists(), (
        f"the NIFTY100 benchmark price file is missing: {N100/INDEX_FILE}. "
        "This is vendor index data under data/raw/, NOT the n100 universe -- "
        "removing REGISTRY['n100'] must never affect it, and it cannot be "
        "regenerated by the pipeline.")
    assert "results_n100" not in str(N100), (
        "the benchmark path resolved into the n100 UNIVERSE's metrics directory. "
        "The benchmark is the published cap-weighted index; the universe is an "
        "equal-weighted constituent basket. Confusing them is the exact error this "
        "chart was rebuilt to correct.")

    CAP=1_000_000
    idx_raw=(config.read_price_csv(N100/INDEX_FILE)[["date","close"]].dropna()
             .set_index("date")["close"].sort_index())
    EQ={t:pd.read_csv(EQF[t],parse_dates=["date"]).set_index("date") for t in TAGS}
    CASHDF={t:pd.read_csv(CASHF[t],parse_dates=["date"]).set_index("date") for t in TAGS}
    CASH={t:CASHDF[t].cash_pct for t in TAGS}
    TC_SRC={k:tc_from_log(v) for k,v in TRF.items()}
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
    for nm,e in ((f"{t} window",EQ[t]) for t in TAGS):
        s=index_on(e.index)
        print(f"    {nm}: {e.index[0].date()} -> {e.index[-1].date()}   index CAGR {cagr(s):.4f}%")
    print("\n" + "="*94)
    print(" CORRECTED NUMBERS")
    print("="*94)
    rows=[]
    EQ_FOR={}
    B={}
    for t in TAGS:
        EQ_FOR[f"{t} v2"]=EQ[t]["strategy"]; EQ_FOR[f"{t} v1"]=EQ[t]["baseline_invvol"]
        B[f"{t} v2"]=before_tc(EQ[t]["strategy"],TC_SRC[f"{t} v2"][0])
        B[f"{t} v1"]=before_tc(EQ[t]["baseline_invvol"],TC_SRC[f"{t} v1"][0])
    # THREE STRATEGY ROWS PER UNIVERSE FIRST, THEN ONE INDEX ROW PER UNIVERSE
    # WINDOW -- the order the two hand-written blocks produced, preserved so the
    # table is row-for-row identical when both universes are present.
    for t in TAGS:
        addrow(f"{t} v2 (breadth)",EQ[t]["strategy"],CASH[t].mean(),B[f"{t} v2"][0])
        addrow(f"{t} v1 (inv-vol)",EQ[t]["baseline_invvol"],0.0,B[f"{t} v1"][0])
        addrow(f"{t} buy&hold (equal-weight universe)",EQ[t]["buyhold"],0.0)
    for t in TAGS:
        addrow(f"NIFTY100 (cap-weighted index, {t} win)",index_on(EQ[t].index),0.0)
    tbl=pd.DataFrame(rows)
    print("\n"+tbl.to_string(index=False))
    CMP={t:pd.read_csv(CMPF[t]) for t in TAGS}
    print("\n  TRANSACTION COSTS -- every traded series, so each figure is checkable:")
    print(f"    {'series':<8} {'trades':>7} {'cum TC Rs':>11} {'before TC':>10} {'after TC':>9} "
          f"{'drag':>7}   vs v2FINAL_comparison.csv")
    ok=True
    for k in [f"{t} {v}" for t in TAGS for v in ("v2","v1")]:
        b,tot=B[k]; n=len(TC_SRC[k][1])
        a=cagr(EQ_FOR[k])
        rn,rt=reported(k.split()[0], k.endswith("v1"))
        match = (n==rn) and abs(tot-rt)<1.0
        ok &= match
        print(f"    {k:<8} {n:>7} {tot:>11,.0f} {b:>9.2f}% {a:>8.2f}% {b-a:>6.2f}pp   "
              f"{rn} / Rs {rt:,.0f}  {'MATCH' if match else '*** MISMATCH ***'}")
    print(f"    -> all {len(TAGS)*2} reconcile: {ok}")
    print("    Both sides are engine output: the per-trade logs and v2FINAL_comparison.csv")
    print("    are written by the same run, so this checks the log belongs to the curve.")
    print("    58/74 buy&hold: 0 trades, Rs 0 -- bought once and held.")
    print("    NIFTY100: a published index level, not a portfolio; no TC applies.")
    print("  before-TC = cost drag removed from the realised path, not a zero-cost re-run.")
    print("\n  REMOVED from this chart: the 99-name equal-weighted basket that was")
    print("  previously mislabelled 'Nifty100'. It is not the Nifty 100 (that index is")
    print("  cap-weighted), it used current membership backfilled to 2019, and it was")
    print("  therefore survivorship-biased and not investable.")
    draw(build_series(EQ,CASH), subtitle(EQ,CASH), OUT_DIR/CHART_NAME)

    # THE MATCHED CHART IS A TWO-UNIVERSE ARTEFACT. It exists to cut both universes
    # to their common end date, because the windows differ and that alone moves the
    # index CAGR by 2.4 points. With one universe there is no second window to match
    # to and the "matched" chart would be a byte-for-byte duplicate of the full one
    # under a name promising a comparison it does not contain -- the same reason the
    # combined n100/mid chart skips below two universes.
    if len(TAGS) < 2:
        print("\n" + "="*94)
        print(f" MATCHED-WINDOW chart SKIPPED -- only {TAGS[0]} is registered, so there is")
        print(" no second window to match to. The full-window chart above is the whole")
        print(" comparison; no _matched.png is written.")
        print("="*94)
    else:
        end=min(EQ[t].index[-1] for t in TAGS)
        EQm={t:EQ[t][EQ[t].index<=end] for t in TAGS}
        CASHm={t:CASH[t][CASH[t].index<=end] for t in TAGS}
        print("\n" + "="*94)
        print(f" MATCHED WINDOW -- both universes truncated to {end.date()}")
        print("="*94)
        mrows=[]
        pairs=[]
        for t in TAGS:
            pairs += [(f"{t} v2",EQm[t]["strategy"]),(f"{t} buy&hold",EQm[t]["buyhold"])]
        pairs.append(("NIFTY100 index",index_on(EQm[TAGS[0]].index)))
        for lab,s in pairs:
            mrows.append({"Series":lab,"CAGR%":round(cagr(s),2),"MaxDD%":round(dd(s).min(),2)})
        print("\n"+pd.DataFrame(mrows).to_string(index=False))
        draw(build_series(EQm,CASHm),
             subtitle(EQm,CASHm,f"  |  MATCHED WINDOW to {end.date()}"),
             OUT_DIR/MATCHED_NAME)
    # THE WRITE IS SPELLED OUT AGAINST M58 IN THE COMMON CASE, deliberately, so the
    # literal `M58 / "fair_comparison_table.csv"` sits on a to_csv line where
    # check_pipeline_order can see it. That is the producer edge for STEP 14
    # make_final_summary.py, which reads the table out of results/metrics; routed
    # only through OUT_DIR it resolved to nothing and STEP 14's dependency became
    # invisible. The else-branch is the same write for a 58-less run.
    if "58" in METRICS:
        tbl.to_csv(M58/"fair_comparison_table.csv",index=False)
    else:
        tbl.to_csv(OUT_DIR/"fair_comparison_table.csv",index=False)
    print("\nsaved -> fair_comparison_table.csv")


if __name__ == "__main__":
    main()
