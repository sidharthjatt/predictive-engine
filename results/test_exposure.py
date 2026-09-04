"""
test_exposure.py -- Crash protection via MARKET-LEVEL exposure scaling

PROBLEM: the model produces a relative rank. In a crash it ranks the stock that is
falling least at number one, and the strategy buys it -- even though that stock is
also down 25%.

WHAT FAILED BEFORE: the absolute gate (blocking individual stocks killed the
mean-reversion edge, Sharpe 1.03 -> 0.76), and the slope regime rule (lagging,
14 fires with 4 correct).

THIS APPROACH works at market level and never blocks an individual stock:
  A. BREADTH: invest the fraction of capital equal to the fraction of stocks with
     positive momentum; hold the rest in cash. In a crash breadth falls and cash
     rises, while good stocks are still bought.
  B. VOL-TARGET: high portfolio vol -> lower exposure. Vol tends to rise BEFORE a crash.
  C. BOTH: min(breadth, voltgt).

PROTOCOL: no threshold is tuned. Target vol is the median realised vol, which is
parameter-free. Crash periods are reported separately, to show whether the method
actually protected capital or merely cut returns.
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import survivorship as sv
import engine_core
from engine_core import metrics, precompute

try:
    from qbeast_in_charges import (compute_leg_charges, Broker, Segment,
                                   Product, Side as QSide, Exchange)
    from decimal import Decimal
    def calc_tc(price, qty, side):
        if price <= 0 or qty <= 0:
            return 0.0
        bd = compute_leg_charges(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                                 QSide.BUY if side == "BUY" else QSide.SELL,
                                 Decimal(str(round(price, 2))), Decimal(str(round(qty, 4))),
                                 Exchange.NSE)
        return float(bd.total)
except Exception:
    def calc_tc(price, qty, side):
        return price * qty * 0.0011

REBAL, VOL_WIN = 20, 60
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = config.TOP_N, config.BUFFER
SLIPPAGE = 0.0015
START_CAPITAL = 1_000_000
CASH_YIELD = 0.0        # no yield assumed on idle cash
# BACKTEST WINDOW -- imported from config.py, the single definition.
# Date-based and inclusive. The old year cut (BT_START, BT_END = 2019, 2026)
# ran to 2026-06-08, six trading days beyond this window.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE
M = config.METRICS_DIR


def backtest_exposure(px, op, sc, dates, pc, mom20, port_vol=None,
                      mode="none", target_vol=None, audit=None, sizing="invvol",
                      const_expo=None, value_at_open=True):
    """audit=None reproduces the original code path exactly: no overhead, and the
    official numbers are unchanged.
    Passing a dict with holdings/summary/trades/ranking/decisions/skipped keys logs
    a daily snapshot into it.

    value_at_open -- WHICH PRICE VALUES THE BOOK WHEN SIZING THE DAY'S BUYS.

        True (default, and the causally correct rule): the portfolio is valued at
        the EXECUTION day's OPEN, which is the price the orders themselves fill at.

        False: the portfolio is valued at the execution day's CLOSE. This is what
        this function did unconditionally until 2026-09-04, and it is LOOK-AHEAD --
        the order is placed at 09:15 against a valuation that does not exist until
        15:30. Selection is unaffected (ranks were fixed on the prior decision day),
        but the QUANTITY bought depends on information from later the same day.
        Measured on the 58, v1 arm: it flatters CAGR by 0.79 points (24.62 -> 23.83).

        WHY THE DEFAULT IS True RATHER THAN False. nautilus/nt_attribution.py has
        carried this same switch for longer, and every verification path already
        passes value_at_open=True -- nt_verify.py:119, nt_verify.py:163 and
        verify_v34_arms.py:82. The 92-of-92 correctness gate therefore already
        certifies the OPEN-valued rule. Defaulting to True brings this engine onto
        the basis its own gate verifies, instead of leaving the two disagreeing.

        WHO PASSES False, AND WHY. The retired 58 and 74 are frozen: their published
        numbers must not move. Their four callers pin value_at_open=False
        explicitly -- engine_v2_final.py, engine_v2_final74.py, make_daily_audit.py
        and validate_breadth.py. That is the same pattern build_scores.py already
        uses to pin the defective purge_mode="calendar" for those two universes
        while the live universes take the corrected default. A frozen universe opts
        OUT of a correction; it is never the correction that opts in."""
    shares, cash = {}, START_CAPITAL
    cum_tc, n_trades = 0.0, 0
    eq, pending, expo_log = [], None, []
    cash_daily = (1 + CASH_YIELD) ** (1 / 252) - 1

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        cash *= (1 + cash_daily)

        if pending is not None:
            targets, keep = pending
            for s in list(shares.keys()):
                if s not in keep:
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "no open price (NaN/<=0)", "detail": ""})
                        continue
                    pr *= (1 - SLIPPAGE)
                    q = int(shares[s]); tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    del shares[s]
            if targets:
                # THE BOOK IS VALUED AT THE PRICE THE ORDERS FILL AT.
                # `opens` is this morning's open -- the same price used two lines
                # below to size and fill every buy. `prices` is today's close, which
                # is not knowable when the order is sent. See value_at_open above.
                vp = opens if value_at_open else prices
                port_val = sum(q * vp[s] for s, q in shares.items()
                               if not np.isnan(vp.get(s, np.nan))) + cash
                invest_val = port_val * targets["_exposure"] * 0.98
                for s, w in targets.items():
                    if s == "_exposure" or s in shares:
                        continue
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "no open price (NaN/<=0)", "detail": ""})
                        continue
                    pr *= (1 + SLIPPAGE)
                    q = int((invest_val * w) // pr)
                    if q < 1:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "qty < 1 after sizing",
                                "detail": f"target Rs {invest_val*w:,.0f} / price {pr:,.2f}"})
                        continue
                    if cash < q * pr:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "cash short (before TC)",
                                "detail": f"need Rs {q*pr:,.0f}, have Rs {cash:,.0f}"})
                        continue
                    tc = calc_tc(pr, q, "BUY")
                    if cash < q * pr + tc:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "cash short (incl TC)",
                                "detail": f"need Rs {q*pr+tc:,.0f}, have Rs {cash:,.0f}"})
                        continue
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "BUY", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    shares[s] = shares.get(s, 0) + q
            pending = None

        if i % REBAL == 0 and i < len(dates) - 1:
            if mode == "none":
                expo = 1.0
            elif mode == "breadth":
                m = mom20.loc[dt].dropna()
                expo = float((m > 0).mean()) if len(m) else 1.0
            elif mode == "voltgt":
                pv = port_vol.loc[dt] if (port_vol is not None and dt in port_vol.index) else np.nan
                expo = min(1.0, target_vol / pv) if (not np.isnan(pv) and pv > 0) else 1.0
            elif mode == "const":
                # The T3 control of experiments/BREADTH_LIVE_SPEC.txt. Holds a
                # FIXED exposure so that breadth can be compared against the same
                # average cash level, isolating the timing from the level.
                # The caller supplies the level; it is read from the breadth
                # run's own realised mean and is never a literal in this file.
                if const_expo is None:
                    raise ValueError('mode="const" requires const_expo')
                expo = float(const_expo)
            elif mode == "both":
                m = mom20.loc[dt].dropna()
                b = float((m > 0).mean()) if len(m) else 1.0
                pv = port_vol.loc[dt] if (port_vol is not None and dt in port_vol.index) else np.nan
                v = min(1.0, target_vol / pv) if (not np.isnan(pv) and pv > 0) else 1.0
                expo = min(b, v)
            expo = max(0.0, min(1.0, expo))
            expo_log.append(expo)

            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            # TOUCH POINT 2 -- only names in the index on this date may be ranked.
            # engine_core.MEMBERSHIP is the single holder; see the note there.
            if sv.is_pit() and engine_core.MEMBERSHIP is not None:
                _members = engine_core.MEMBERSHIP.members_on(dt)
                s_ = s_[[k for k in s_.index if k in _members]]
            if len(s_) >= TOP_N:
                rk = s_.sort_values(ascending=False)
                top = list(rk.index[:TOP_N])
                keep = set(rk.index[:BUFFER])
                # TOUCH POINT 3 -- forced exits join the sell set. `to_sell` is
                # computed as `held - keep` above, so removing them from `keep` is
                # that union. Empty unless mode is pit AND exit policy is forced.
                if sv.is_pit() and engine_core.MEMBERSHIP is not None:
                    keep -= engine_core.MEMBERSHIP.forced_exits(set(shares.keys()), dt)
                # sizing="invvol" (default) reproduces the existing system exactly.
                # "equal" gives every one of the TOP_N positions the same share of
                # invest_value.
                # "provol" is the mirror of invvol: the raw vol instead of its
                # reciprocal, so a high-vol name gets the LARGE position. Same guard,
                # same normalisation, same fallback -- only the numerator differs.
                # Mirrored in nautilus/nt_strategy.py; the two must not drift.
                if sizing == "equal":
                    w = {s: 1.0 / len(top) for s in top}
                else:
                    v = pc["vol"].loc[dt]
                    w = {}
                    for s in top:
                        vs = v.get(s, np.nan)
                        ok = (not np.isnan(vs)) and vs > 0.01
                        if not ok:
                            w[s] = 0.0
                        elif sizing == "provol":
                            w[s] = vs
                        else:
                            w[s] = 1.0 / vs
                    tot = sum(w.values())
                    w = ({s: w[s] / tot for s in top} if tot > 0
                         else {s: 1.0/len(top) for s in top})
                w["_exposure"] = expo
                pending = (w, keep)

                if audit is not None:
                    pv_now = sum(q * prices[k] for k, q in shares.items()
                                 if not np.isnan(prices.get(k, np.nan))) + cash
                    held = set(shares.keys())
                    m_ = mom20.loc[dt].dropna()
                    npos, ntot = int((m_ > 0).sum()), int(len(m_))
                    audit["decisions"].append({
                        "decided_on": dt, "breadth_pos": npos, "breadth_total": ntot,
                        "breadth": round(npos/ntot, 4) if ntot else 1.0,
                        "exposure": round(expo, 4), "port_value": round(pv_now, 2),
                        "invest_value": round(pv_now*expo*0.98, 2),
                        "cash_before": round(cash, 2), "n_held_before": len(held),
                        "n_buy": len([x for x in top if x not in held]),
                        "n_sell": len([x for x in held if x not in keep])})
                    for rnk, (sym, scr) in enumerate(rk.items(), start=1):
                        if rnk > 25 and sym not in held: continue
                        vs_ = v.get(sym, np.nan)
                        act = ("BUY" if sym not in held else "HOLD-top") if sym in top \
                              else ("HOLD-buffer" if (sym in keep and sym in held)
                                    else ("SELL" if sym in held else "-"))
                        audit["ranking"].append({
                            "decided_on": dt, "rank": rnk, "symbol": sym,
                            "score": round(float(scr), 6),
                            "vol60": round(float(vs_), 4) if not np.isnan(vs_) else None,
                            "target_wt_pct": round(w.get(sym, 0.0)*100, 2) if sym in top else 0.0,
                            "held_before": sym in held, "action": act})

        mtm = sum(q * prices[s] for s, q in shares.items()
                  if not np.isnan(prices.get(s, np.nan)))
        pv = mtm + cash
        eq.append(pv)

        if audit is not None:
            for s_h, q_h in sorted(shares.items()):
                pr_h = prices.get(s_h, np.nan)
                if np.isnan(pr_h):
                    continue
                val = q_h * pr_h
                audit["holdings"].append({"date": dt, "symbol": s_h, "qty": int(q_h),
                    "price": round(float(pr_h), 2), "value": round(val, 2),
                    "weight_pct": round(val / pv * 100, 2) if pv > 0 else 0.0})
            audit["summary"].append({"date": dt, "n_stocks": len(shares),
                "cash": round(cash, 2), "mtm": round(mtm, 2), "total": round(pv, 2),
                "invested_pct": round(mtm / pv * 100, 2) if pv > 0 else 0.0,
                "cash_pct": round(cash / pv * 100, 2) if pv > 0 else 0.0,
                "cum_tc": round(cum_tc, 2), "cum_trades": n_trades})
    return (pd.Series(eq, index=dates), cum_tc, n_trades,
            np.mean(expo_log) if expo_log else 1.0)


def main():
    print("=" * 100)
    print("CRASH PROTECTION via MARKET-LEVEL EXPOSURE SCALING")
    print("=" * 100)
    print("  Don't block individual stocks (that killed the edge). Scale TOTAL")
    print("  exposure down when the whole market is weak.\n")

    cache = Path("/tmp/v5_expanding.csv")
    if not cache.exists():
        print("  ERROR: /tmp/v5_expanding.csv missing. Rebuild scores first.")
        return
    p = pd.read_csv(cache, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1

    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    target_vol = port_vol.loc[bd].median()
    print(f"  Vol-target = median realized vol = {target_vol*100:.1f}% (no tuning)\n")

    variants = [("Baseline (always 100% invested)", "none"),
                ("Breadth scaling", "breadth"),
                ("Vol-targeting", "voltgt"),
                ("Breadth + Vol (both)", "both")]

    rows, curves = [], {}
    for lab, mode in variants:
        eq, tc, ntr, avg_expo = backtest_exposure(
            px, op, sc, bd, pc, mom20, port_vol, mode=mode, target_vol=target_vol)
        m = metrics(eq, lab, tc, ntr)
        m["AvgExposure"] = round(avg_expo * 100, 0)
        rows.append(m); curves[lab] = eq
        print(f"  {lab:<38} CAGR {m['CAGR%']:>6.2f}%  Sharpe {m['Sharpe']:>5.2f}  "
              f"MaxDD {m['MaxDD%']:>7.2f}%  Calmar {m['Calmar']:>5.2f}  "
              f"avg-invested {avg_expo*100:>3.0f}%")

    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    mbh = metrics(bh, "Equal-weight buy & hold"); mbh["AvgExposure"] = 100
    rows.append(mbh); curves["Equal-weight buy & hold"] = bh
    print(f"  {'Equal-weight buy & hold':<38} CAGR {mbh['CAGR%']:>6.2f}%  "
          f"Sharpe {mbh['Sharpe']:>5.2f}  MaxDD {mbh['MaxDD%']:>7.2f}%  Calmar {mbh['Calmar']:>5.2f}")
    pd.DataFrame(rows).to_csv(M / "exposure_compare.csv", index=False)

    print("\n" + "=" * 100)
    print("CRASH PERIODS -- did exposure scaling protect? (return % in window)")
    print("=" * 100)
    crashes = [("COVID (Feb-Apr 2020)", "2020-02-01", "2020-04-30"),
               ("2022 selloff (H1)", "2022-01-01", "2022-06-30"),
               ("2025 H2 weakness", "2025-07-01", "2025-12-31"),
               ("2026 drawdown", "2026-01-01", "2026-06-30")]
    crows = []
    for cname, s, e in crashes:
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        row = {"Period": cname}
        for lab, eq in curves.items():
            mm = (eq.index >= s) & (eq.index <= e)
            if mm.sum() >= 3:
                row[lab] = round((eq[mm].iloc[-1] / eq[mm].iloc[0] - 1) * 100, 1)
        crows.append(row)
    cr = pd.DataFrame(crows).set_index("Period").T
    print(cr.to_string())
    cr.to_csv(M / "exposure_crashes.csv")

    fig, ax = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[2, 1])
    cols = {"Baseline (always 100% invested)": "#1f77b4", "Breadth scaling": "#ff7f0e",
            "Vol-targeting": "#9467bd", "Breadth + Vol (both)": "#d62728",
            "Equal-weight buy & hold": "#2ca02c"}
    rdf = pd.DataFrame(rows)
    for lab, eq in curves.items():
        cum = (eq / eq.iloc[0] - 1) * 100
        rr = rdf[rdf.Config == lab].iloc[0]
        ls = "--" if "buy & hold" in lab else "-"
        ax[0].plot(eq.index, cum, lw=2.1, ls=ls, color=cols[lab], alpha=.9,
                   label=f"{lab}  (CAGR {rr['CAGR%']}%, Sharpe {rr['Sharpe']}, MaxDD {rr['MaxDD%']}%)")
    ax[0].axhline(0, color="k", lw=.7, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title("Market-level exposure scaling for crash protection\n"
                    "Scales total exposure down in weak markets -- does NOT block individual stocks",
                    fontsize=12)
    ax[0].legend(loc="upper left", fontsize=8.5)
    ax[0].grid(alpha=.3)
    for lab, eq in curves.items():
        dd = (eq / eq.cummax() - 1) * 100
        ls = "--" if "buy & hold" in lab else "-"
        ax[1].plot(eq.index, dd, lw=1.4, color=cols[lab], alpha=.85, ls=ls)
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(M / "chart_exposure.png", dpi=140, bbox_inches="tight")
    print("\n  saved -> chart_exposure.png")

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    base = rdf[rdf.Config.str.startswith("Baseline")].iloc[0]
    print(f"  Baseline : CAGR {base['CAGR%']}%  Sharpe {base['Sharpe']}  MaxDD {base['MaxDD%']}%")
    for lab, _ in variants[1:]:
        v = rdf[rdf.Config == lab].iloc[0]
        d_cagr = v["CAGR%"] - base["CAGR%"]
        d_dd = v["MaxDD%"] - base["MaxDD%"]
        d_sh = v["Sharpe"] - base["Sharpe"]
        verdict = ("PROTECTS (less DD, Sharpe held)" if (d_dd > 3 and d_sh >= -0.05)
                   else "just cuts return" if (d_cagr < -2 and d_dd < 3) else "marginal")
        print(f"  {lab:<24}: dCAGR {d_cagr:+5.1f}  dMaxDD {d_dd:+5.1f}pts  dSharpe {d_sh:+.2f}  -> {verdict}")
    print("\n  Point of exposure scaling is NOT more return -- it's shallower drawdown")
    print("  in crashes without wrecking Sharpe. That matters for real money (less")
    print("  chance you panic-sell at the bottom). If it only cuts return with no DD")
    print("  benefit, drop it.")
    print("\nSaved -> exposure_compare.csv, exposure_crashes.csv, chart_exposure.png")


if __name__ == "__main__":
    main()
