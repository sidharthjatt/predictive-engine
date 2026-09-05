"""
reality_check.py -- the unvarnished picture, for a real-money decision.
Overall P&L, annual breakdown, per-stock rupee P&L, directional accuracy,
hit rate, and a verdict.

WHICH ENGINE THIS REPORTS ON -- read this before quoting any number here.
  This script reads FINAL_equity.csv and FINAL_trades.csv, which come from
  engine_core.py: the VALIDATION engine (v1, always fully invested, new buys
  sized from leftover cash). It is the right engine for seed and sub-period
  validation, but it is NOT the reported system.

  The OFFICIAL system is v2 from engine_v2_final.py (portfolio-value sizing,
  breadth-scaled exposure), whose equity curve is v2FINAL_equity.csv. Its final
  value is lower, because v2 sits partly in cash and idle cash earns nothing.

  Both figures are printed side by side in section 1 so they can never be
  confused. When quoting a headline number anywhere -- thesis, resume, a
  presentation -- quote the v2 figure.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
sys.path.append(str(Path(__file__).resolve().parents[1]))
import config
import arms.registry as arm_reg
from engine_core import TOP_N

M = config.METRICS_DIR
START_CAPITAL = 1_000_000
BT_START, BT_END = 2019, 2026


def main():
    print("=" * 90)
    print("REALITY CHECK -- can this take real money?")
    print("=" * 90)

    eq = pd.read_csv(M / "FINAL_equity.csv", parse_dates=["date"]).set_index("date")
    trades = pd.read_csv(M / "FINAL_trades.csv", parse_dates=["Date"])
    strat, bh = eq["strategy"], eq["buyhold"]

    print("\n" + "=" * 90)
    print("1. OVERALL P&L  (starting capital Rs 10,00,000)")
    print("   Source: FINAL_equity.csv / FINAL_trades.csv -- the VALIDATION engine (v1).")
    print("   This is NOT the official reported system. See section 1b.")
    print("=" * 90)
    fs, fb = strat.iloc[-1], bh.iloc[-1]
    yrs = (strat.index[-1] - strat.index[0]).days / 365.25
    print(f"   Period                : {strat.index[0].date()} to {strat.index[-1].date()} ({yrs:.1f} yrs)")
    print(f"   Strategy final value  : Rs {fs:>14,.0f}")
    print(f"   Strategy net P&L      : Rs {fs-START_CAPITAL:>14,.0f}   ({(fs/START_CAPITAL-1)*100:+.1f}%)")
    print(f"   Buy & hold final value: Rs {fb:>14,.0f}")
    print(f"   Buy & hold net P&L    : Rs {fb-START_CAPITAL:>14,.0f}   ({(fb/START_CAPITAL-1)*100:+.1f}%)")
    print(f"   Strategy EDGE over B&H: Rs {fs-fb:>14,.0f}   (extra money for all the work)")
    total_tc = trades["TC_Rs"].sum()
    print(f"\n   Total transaction cost: Rs {total_tc:>14,.0f}   ({total_tc/START_CAPITAL*100:.1f}% of capital)")
    print(f"   Number of trades      : {len(trades):>14,}")

    v2f = M / "v2FINAL_equity.csv"
    if v2f.exists():
        v2 = pd.read_csv(v2f, parse_dates=["date"]).set_index("date")
        # ASKED FOR BY ARM NAME. Note that `eq["strategy"]` a few lines above is a
        # DIFFERENT FILE -- FINAL_equity.csv, the validation engine's -- which
        # still legitimately has a column called `strategy` and is not touched by
        # the per-arm layout. Two files, one column name; only this one moves.
        fv2 = arm_reg.equity_series(v2, "v2").iloc[-1]
        print("\n" + "=" * 90)
        print("1b. THE OFFICIAL SYSTEM  (v2, breadth-scaled -- quote THIS one)")
        print("=" * 90)
        print(f"   Source                : v2FINAL_equity.csv (engine_v2_final.py)")
        print(f"   v2 final value        : Rs {fv2:>14,.0f}"
              f"   ({(fv2/START_CAPITAL-1)*100:+.1f}%)")
        print(f"   Validation engine     : Rs {fs:>14,.0f}"
              f"   ({(fs/START_CAPITAL-1)*100:+.1f}%)")
        print(f"   Difference            : Rs {fs-fv2:>14,.0f}")
        print("   The gap is not an error. The two engines size positions differently,")
        print("   and v2 holds cash whenever market breadth is weak.")
    else:
        print("\n   [WARN] v2FINAL_equity.csv not found -- run engine_v2_final.py first.")
        print("          Without it the official figure cannot be shown here.")

    print("\n" + "=" * 90)
    print("2. ANNUAL PROFIT / LOSS")
    print("=" * 90)
    sy, by = strat.resample("YE").last(), bh.resample("YE").last()
    syr, byr = sy.pct_change(), by.pct_change()
    syr.iloc[0] = sy.iloc[0]/START_CAPITAL - 1
    byr.iloc[0] = by.iloc[0]/START_CAPITAL - 1
    print(f"   {'Year':<6} {'Strategy':>11} {'Buy&Hold':>11} {'Edge':>9}  {'Strat Rs P&L':>16}")
    prev = START_CAPITAL
    for dt in sy.index:
        s_r, b_r = syr.loc[dt]*100, byr.loc[dt]*100
        pnl = sy.loc[dt] - prev
        flag = "" if s_r >= b_r else "  <- lost to B&H"
        print(f"   {dt.year:<6} {s_r:>+10.1f}% {b_r:>+10.1f}% {s_r-b_r:>+8.1f}%  Rs {pnl:>+13,.0f}{flag}")
        prev = sy.loc[dt]
    print(f"\n   Beat buy & hold in {(syr.values>byr.values).sum()} of {len(sy)} years")
    print(f"   Had a LOSING year {(syr<0).sum()} of {len(sy)} times")

    print("\n" + "=" * 90)
    print("3. PER-STOCK P&L  (actual rupee, round-trips + open MTM)")
    print("=" * 90)
    frames = {}
    for f in sorted((config.RAW_DATA_DIR / "nifty50").glob("*.csv")):
        d = config.read_price_csv(f)[["date", "close"]].dropna()
        frames[f.stem] = d.set_index("date")["close"]
    px = pd.DataFrame(frames).sort_index().ffill()
    last_px = px.iloc[-1]

    rows = []
    for sym, g in trades.groupby("Symbol"):
        g = g.sort_values("Date")
        pos, cost, realized, tc = 0, 0.0, 0.0, 0.0
        for _, tr in g.iterrows():
            tc += tr["TC_Rs"]
            if tr["Action"] == "BUY":
                pos += tr["Shares"]; cost += tr["Shares"]*tr["Price"]
            else:
                if pos > 0:
                    ac = cost/pos
                    realized += tr["Shares"]*(tr["Price"]-ac)
                    cost -= tr["Shares"]*ac; pos -= tr["Shares"]
        unreal = pos*(last_px[sym]-cost/pos) if (pos > 0 and sym in last_px) else 0.0
        rows.append({"symbol": sym, "realized_pnl": round(realized), "open_mtm": round(unreal),
                     "tc": round(tc), "net_pnl": round(realized+unreal-tc)})
    pnl_df = pd.DataFrame(rows).sort_values("net_pnl", ascending=False)

    print("   TOP 10 MONEY-MAKERS:")
    for _, r in pnl_df.head(10).iterrows():
        print(f"     {r['symbol']:<14} Rs {r['net_pnl']:>+12,.0f}")
    print("\n   TOP 10 MONEY-LOSERS:")
    for _, r in pnl_df.tail(10).iloc[::-1].iterrows():
        print(f"     {r['symbol']:<14} Rs {r['net_pnl']:>+12,.0f}")
    w = (pnl_df["net_pnl"] > 0).sum(); l = (pnl_df["net_pnl"] < 0).sum()
    print(f"\n   Stocks that MADE money : {w}")
    print(f"   Stocks that LOST money : {l}")
    print(f"   Net from winners       : Rs {pnl_df[pnl_df.net_pnl>0].net_pnl.sum():>+14,.0f}")
    print(f"   Net from losers        : Rs {pnl_df[pnl_df.net_pnl<0].net_pnl.sum():>+14,.0f}")
    pnl_df.to_csv(M / "reality_per_stock_pnl.csv", index=False)

    print("\n" + "=" * 90)
    print("4. DIRECTIONAL ACCURACY")
    print("=" * 90)
    cache = Path("/tmp/v5_expanding.csv")
    if cache.exists():
        p = pd.read_csv(cache, parse_dates=["date"])
        pf = p.pivot_table(index="date", columns="symbol", values="close").ffill()
        fwd = pf.shift(-20)/pf - 1
        fl = fwd.stack().rename("fwd_ret").reset_index()
        fl.columns = ["date", "symbol", "fwd_ret"]
        p = p.merge(fl, on=["date", "symbol"], how="left")
        d = p.dropna(subset=["score", "fwd_ret"])
        d = d[d["date"].dt.year >= BT_START]

        def bstats(g):
            g = g.sort_values("score", ascending=False)
            return pd.Series({"topN": g.head(TOP_N)["fwd_ret"].mean(),
                              "bottomN": g.tail(TOP_N)["fwd_ret"].mean(),
                              "all": g["fwd_ret"].mean()})
        bk = d.groupby("date")[["score","fwd_ret"]].apply(bstats).dropna()
        print(f"   (a) Did the top-N we buy actually beat the average stock (next 20d)?")
        print(f"         Top-N beat average : {(bk['topN']>bk['all']).mean()*100:.1f}% of rebalances")
        print(f"         Top-N beat bottom-N: {(bk['topN']>bk['bottomN']).mean()*100:.1f}% of rebalances")
        print(f"         (50% = coin flip, no skill)")
        ic = d.groupby("date")[["score","fwd_ret"]].apply(
            lambda g: spearmanr(g["score"], g["fwd_ret"]).correlation if len(g)>=10 else np.nan).dropna()
        print(f"\n   (b) Rank IC: mean {ic.mean():+.4f}, positive {(ic>0).mean()*100:.1f}% of the time")
        print(f"         -> right direction ~{(ic>0).mean()*100:.0f}% of rebalances, but each")
        print(f"            call only slightly better than a coin flip")
    else:
        print("   /tmp/v5_expanding.csv missing -- directional accuracy skipped.")
        print("   (Everything else above is still valid. Re-run training build to get this.)")

    print("\n" + "=" * 90)
    print("5. TRADE HIT RATE  (completed round-trips)")
    print("=" * 90)
    rts = []
    for sym, g in trades.groupby("Symbol"):
        g = g.sort_values("Date"); stack = []
        for _, tr in g.iterrows():
            if tr["Action"] == "BUY":
                stack.append([tr["Price"], tr["Shares"]])
            else:
                s = tr["Shares"]
                while s > 0 and stack:
                    bp, bs = stack[0]
                    m = min(bs, s)
                    rts.append((tr["Price"]-bp)*m)
                    if bs > m: stack[0][1] = bs-m
                    else: stack.pop(0)
                    s -= m
    rt = np.array(rts)
    if len(rt):
        wins, losses = rt[rt > 0], rt[rt < 0]
        print(f"   Completed round-trips : {len(rt)}")
        print(f"   Winning trades        : {len(wins)} ({len(wins)/len(rt)*100:.1f}%)")
        print(f"   Losing trades         : {len(losses)} ({len(losses)/len(rt)*100:.1f}%)")
        print(f"   Average WIN           : Rs {wins.mean():>+10,.0f}")
        print(f"   Average LOSS          : Rs {losses.mean():>+10,.0f}")
        print(f"   Win/Loss size ratio   : {abs(wins.mean()/losses.mean()):.2f}")
        print(f"   Profit factor         : {wins.sum()/abs(losses.sum()):.2f}  (>1 = profitable)")

    print("\n" + "=" * 90)
    print("6. THE REAL-MONEY VERDICT")
    print("   Figures below are the VALIDATION engine (v1). For the official system,")
    print("   see section 1b and FINAL_SUMMARY_TABLE.csv.")
    print("=" * 90)
    edge_rs = fs - fb
    edge_ann = ((fs/START_CAPITAL)**(1/yrs) - (fb/START_CAPITAL)**(1/yrs))*100
    bh_ann = (fb/START_CAPITAL)**(1/yrs)*100 - 100
    print(f"""
   - {yrs:.0f} years: strategy turned Rs 10L into Rs {fs:,.0f} (profit Rs {fs-START_CAPITAL:,.0f}).
   - Buy & hold: Rs 10L into Rs {fb:,.0f}.
   - Strategy's EDGE over buy & hold: Rs {edge_rs:,.0f} over {yrs:.0f} yrs ({edge_ann:+.1f}%/yr).

   Hard questions for real capital:
   1. Is {edge_ann:+.1f}%/yr worth it vs a Nifty index fund giving ~{bh_ann:.0f}%/yr for 0.2% fee?
   2. That edge is NOT statistically significant (t~0.8). Live it may be zero/negative.
   3. Edge is BEFORE taxes on {len(trades)} trades (STCG 15-20%), platform costs, and
      worse-than-modelled slippage at size. After these, edge likely vanishes.
   4. Survivorship bias inflates BOTH lines. Real point-in-time numbers are lower.

   Bottom line:
   - AS-IS this is NOT yet a product. Edge too small and uncertain for real money;
     after tax and real costs likely to trail a plain Nifty index fund.
   - What it IS: a clean, honest, validated pipeline proving you can pull a small
     real signal without leaking or overfitting. That is the hard 80%.
   - To be product-worthy the edge must get BIGGER -> less-efficient universe
     (mid/small caps) or new data (fundamentals, earnings revisions). NOT more tuning.
""")
    print("   Saved -> reality_per_stock_pnl.csv")


if __name__ == "__main__":
    main()
