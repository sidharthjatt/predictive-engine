"""
engine_core.py -- the validation engine: comparison + validation + frozen config.

NOTE ON WHICH ENGINE THIS IS:
  This engine sizes new buys from leftover cash. It is the right tool for seed
  and sub-period validation, but its absolute CAGR is NOT the reported figure.
  The official system is engine_v2_final.py (portfolio-value sizing, breadth
  scaling). Do not quote numbers from this file as headline results.

WHAT WAS LEARNED ALONG THE WAY:
 1. The original model had no signal (IC 0.011, t=0.75): 10 of its 16 features were
    momentum. Fixed with 17 features across 5 families, cross-sectionally z-scored.
    IC rose to 0.036, t=2.10.
 2. LABEL LEAK worth 5.4% of CAGR. Labels from the last 20 days of a training window
    resolved inside the test window. Fixed by purging 32 days at every retrain.
 3. DEV SELECTION IS NOISE. Five seed sets produced three different winners, and the
    gap (0.05) was smaller than the noise (0.08). Dev selection was abandoned and the
    config fixed a priori.
 4. N=8 was wrong at this stage -- worst on every seed set. Moved to N=12.
    (The final system later moved to top-8 after the concentration test.)
 5. The slope regime rule failed: 14 fires, 4 correct. In COVID it avoided the crash
    but missed the recovery.
 6. The ABSOLUTE GATE addressed a real flaw but the fix did not work: Sharpe fell from
    1.03 to 0.76. The model's edge comes partly from mean reversion, which is exactly
    what the gate blocks.
 7. A BUG invalidated the first v6 run: the `slots` cap was dropped, giving 15.5 average
    positions instead of 12. The gate appeared to win (Sharpe 1.21) purely because of it.
    Lesson: always reconcile the baseline against the previous engine. If the control
    fails, everything downstream fails.
 8. WHAT ACTUALLY WORKED: inverse-vol sizing, weight = 1/vol.
    Sharpe 1.03 -> 1.09, MaxDD -37.8 -> -33.7, ahead of buy & hold on every metric.

VALIDATION (4 tests): baseline control, seed robustness, sub-period split, parameter
sensitivity.
"""
import sys, warnings, json
from pathlib import Path
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import settings
import market_data


from costs import calc_tc  # the one copy; see costs.py

# TOP_N and BUFFER are defined LIVE in config.py as of 2026-08-29; this line
# keeps its own literals, exactly as the year window does. NOTE that
# validate_sizing.py imports TOP_N from HERE while running on the live
# universes -- the two definitions agree at 8 and nothing enforces it.
# See KNOWN_ISSUES.md and experiments/TOPN_SPEC.txt Part A.
REBAL, TOP_N, BUFFER, VOL_WIN = 20, 8, 16, 60

# Status label for a checklist row that is RECORDED, not computed. It exists so
# that no row can quietly go back to asserting a verdict this run did not reach.
NOT_CHECKED = "NOT CHECKED BY THIS RUN"
# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from costs import SLIPPAGE, fill_price  # noqa: E402
from settings import capital_axis as _capital_axis  # noqa: E402
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
M = settings.METRICS_DIR


def backtest(px, op, sc, dates, pc, top_n=TOP_N, buffer_rank=BUFFER,
             rebal=REBAL, sizing="equal"):
    shares, cash = {}, START_CAPITAL
    cum_tc, n_trades = 0.0, 0
    eq, tl, pending, npos = [], [], None, []

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        if pending is not None:
            top, keep, weights = pending
            for s in list(shares.keys()):
                if s not in keep:
                    p = opens.get(s, np.nan)
                    if np.isnan(p) or p <= 0:
                        continue
                    p = fill_price(p, SLIPPAGE, False)
                    q = int(shares[s]); tc = calc_tc(p, q, "SELL")
                    cash += q * p - tc; cum_tc += tc; n_trades += 1
                    tl.append({"Date": dt.date(), "Symbol": s, "Action": "SELL",
                               "Price": round(p, 2), "Shares": q, "TC_Rs": round(tc, 2)})
                    del shares[s]
            slots = top_n - len(shares)          # <-- the cap that v6 lost
            cands = [s for s in top if s not in shares][:slots]
            if slots > 0 and cands:
                w = {s: weights.get(s, 1.0) for s in cands}
                wsum = sum(w.values()); avail = cash * 0.98
                for s in cands:
                    p = opens.get(s, np.nan)
                    if np.isnan(p) or p <= 0:
                        continue
                    p = fill_price(p, SLIPPAGE, True)
                    q = int((avail * (w[s] / wsum)) // p)
                    if q < 1:
                        continue
                    tc = calc_tc(p, q, "BUY")
                    if cash < q * p + tc:
                        continue
                    cash -= q * p + tc; cum_tc += tc; n_trades += 1
                    shares[s] = shares.get(s, 0) + q
                    tl.append({"Date": dt.date(), "Symbol": s, "Action": "BUY",
                               "Price": round(p, 2), "Shares": q, "TC_Rs": round(tc, 2)})
            pending = None

        if i % rebal == 0 and i < len(dates) - 1:
            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            # TOUCH POINT 2 -- only names in the index on this date may be ranked.
            if market_data.is_pit() and market_data.MEMBERSHIP is not None:
                _members = market_data.MEMBERSHIP.members_on(dt)
                s_ = s_[[k for k in s_.index if k in _members]]
            if len(s_) >= top_n:
                rk = s_.sort_values(ascending=False)
                top = list(rk.index[:top_n])
                keep = set(rk.index[:buffer_rank])
                # TOUCH POINT 3 -- a name that has left the index is sold on the next
                # trading day whatever its rank. The sell set is `held - keep`, so
                # dropping the forced exits out of `keep` is the union the note asks
                # for. Empty unless mode is pit AND exit policy is forced.
                if market_data.is_pit() and market_data.MEMBERSHIP is not None:
                    keep -= market_data.MEMBERSHIP.forced_exits(set(shares.keys()), dt)
                if sizing == "invvol":
                    v = pc["vol"].loc[dt]
                    w = {}
                    for s in top:
                        vs = v.get(s, np.nan)
                        w[s] = (1.0 / vs) if (not np.isnan(vs) and vs > 0.01) else 0.0
                    if sum(w.values()) == 0:
                        w = {s: 1.0 for s in top}
                else:
                    w = {s: 1.0 for s in top}
                pending = (top, keep, w)

        pv = sum(q * prices[s] for s, q in shares.items()
                 if not np.isnan(prices.get(s, np.nan))) + cash
        eq.append(pv); npos.append(len(shares))
    return pd.Series(eq, index=dates), cum_tc, n_trades, pd.DataFrame(tl), np.mean(npos)


def metrics(eq, label, tc=0, ntr=0):
    r = eq.pct_change().dropna()
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0
    dd = ((eq - eq.cummax()) / eq.cummax()).min()
    dn = r[r < 0].std()
    so = r.mean() / dn * np.sqrt(252) if dn > 0 else 0
    return {"Config": label, "CAGR%": round(cagr * 100, 2), "Sharpe": round(sh, 2),
            "Sortino": round(so, 2), "MaxDD%": round(dd * 100, 2),
            "Calmar": round(cagr / abs(dd), 2) if dd else 0,
            "Trades": ntr, "TC_Rs": round(tc, 0)}


def avg_hold(tl):
    if tl.empty:
        return np.nan
    op_, hd = {}, []
    for _, r in tl.sort_values("Date").iterrows():
        if r.Action == "BUY":
            op_[r.Symbol] = pd.Timestamp(r.Date)
        elif r.Symbol in op_:
            hd.append((pd.Timestamp(r.Date) - op_.pop(r.Symbol)).days)
    return round(np.mean(hd), 1) if hd else np.nan
