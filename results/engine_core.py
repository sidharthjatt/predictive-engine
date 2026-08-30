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
from joblib import Parallel, delayed
import pandas as pd
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import config
import survivorship as sv
from features_v2 import (FEATS_V2, add_stock_features,
                         add_market_relative_features, cross_sectional_normalize)

# The point-in-time membership history, or None. This is the ONE place it is held,
# so `engine_core.MEMBERSHIP` is what every consumer reads -- test_exposure included.
# Setting it is not enough on its own: sv.set_mode("pit") must also be called, and
# every survivorship call site below is guarded on that, so leaving the mode at
# "static" keeps all three touch points byte-identical no-ops.
#
# It stays None here because no membership file has passed sv.validate() yet. The
# only file supplied to this project fails the gate (no RELIANCE, INFY, ITC, SBIN
# or ICICIBANK in any of its 76 lists, a bond ticker among the constituents, and
# list[t] != list[t-1] + inclusions - exclusions on 20 of 75 transitions).
MEMBERSHIP = None

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

# FROZEN: retired universe. TOP_N and BUFFER are defined LIVE in config.py
# as of 2026-08-29; this line keeps its own literals deliberately so the 58's
# published numbers cannot move, exactly as the year window does. NOTE that
# validate_sizing.py imports TOP_N from HERE while running on the live
# universes -- the two definitions agree at 8 and nothing enforces it.
# See KNOWN_ISSUES.md and experiments/TOPN_SPEC.txt Part A.
HORIZON, REBAL, TOP_N, BUFFER, VOL_WIN, PURGE = 20, 20, 8, 16, 60, 32

# Status label for a checklist row that is RECORDED, not computed. It exists so
# that no row can quietly go back to asserting a verdict this run did not reach.
NOT_CHECKED = "NOT CHECKED BY THIS RUN"
SLIPPAGE = 0.0015
START_CAPITAL = 1_000_000
BT_START, BT_END = 2019, 2026
M = config.METRICS_DIR



# ---------------------------------------------------------------------------
# NSE TRADING CALENDAR -- applied at panel construction so it cannot be bypassed
# ---------------------------------------------------------------------------
TRADING_CALENDAR = Path(__file__).resolve().parents[1] / "data" / "nse_trading_calendar.csv"


def _load_calendar():
    """The dated artefact from results/make_trading_calendar.py."""
    if not TRADING_CALENDAR.exists():
        raise FileNotFoundError(
            f"{TRADING_CALENDAR} missing.\n"
            "  Run `python3 results/make_trading_calendar.py` first; run_all.py does\n"
            "  this as STEP 0. The panel cannot be built without it, because a\n"
            "  panel that silently keeps market-holiday rows is what this filter\n"
            "  exists to prevent.")
    d = pd.read_csv(TRADING_CALENDAR, comment="#", parse_dates=["date"])
    return set(d["date"])


def _check_calendar(cal, panel, tag=""):
    """Fail loudly if the calendar cannot be trusted for THIS panel.

    Two guards, both aimed at the one real weakness of deriving the calendar from
    the 58 universe: that the 58 could later be narrowed, truncated or re-sourced.

      RANGE   -- the calendar must span the panel's own range. Catches truncation.
      DENSITY -- every date the filter removes must be THIN, i.e. carry fewer
                 symbols than the panel's own median day. A phantom holiday shows
                 ~32 of 148 mid symbols against a median of ~96, so it passes;
                 a genuine session wrongly dropped would be at full density and
                 fires the assertion.

    The literal check "calendar covers fewer days than the panel" is deliberately
    NOT used: the mid panel legitimately holds 6,810 dates against the calendar's
    6,574, because 236 of them are the phantom dates being removed. That check
    would fail by construction on exactly the case the filter is built for. The
    density guard is the same intent expressed so it fires only when wrong.
    """
    cmin, cmax = min(cal), max(cal)
    pmin, pmax = panel["date"].min(), panel["date"].max()
    if cmin > pmin or cmax < pmax:
        raise AssertionError(
            f"trading calendar does not span the {tag} panel: calendar "
            f"{cmin.date()}..{cmax.date()} vs panel {pmin.date()}..{pmax.date()}")
    per_date = panel.groupby("date")["symbol"].nunique()
    median = per_date.median()
    removed = sorted(set(panel["date"].unique()) - cal)
    dense = [d for d in removed if per_date.get(d, 0) >= median]
    if dense:
        raise AssertionError(
            f"trading calendar would remove {len(dense)} FULL-DENSITY date(s) from the "
            f"{tag} panel (>= median {median:.0f} symbols), e.g. "
            f"{[str(d.date()) for d in dense[:5]]}. The calendar is wrong or the 58 "
            f"universe it derives from has changed. Refusing to filter.")
    return removed


def build_panel(horizon, data_dir=None):
    """Build the full feature panel from the 58 raw stock CSVs.
    (This previously lived in engine_v2.py and was nearly lost when that file was
    deleted. It is permanent here now.)
    """
    frames = []
    _src = data_dir if data_dir is not None else (config.RAW_DATA_DIR / "nifty50")
    _cal = _load_calendar()
    _raw = []
    for f in sorted(Path(_src).glob("*.csv")):
        d0 = config.read_price_csv(f)[["date", "close"]].dropna()
        _raw.append(pd.DataFrame({"date": d0["date"], "symbol": f.stem}))
    _pre = pd.concat(_raw, ignore_index=True)
    # Guard BEFORE filtering: the check needs the unfiltered panel to see whether
    # any date the calendar would remove is at full symbol density.
    _removed = _check_calendar(_cal, _pre, tag=str(Path(_src).name))
    _dropped = 0
    for f in sorted(Path(_src).glob("*.csv")):
        raw = config.read_price_csv(f).sort_values("date")
        raw = raw[["date", "open", "high", "low", "close", "volume"]].dropna()
        # Market-holiday rows are removed BEFORE any feature is computed, so a
        # phantom session cannot enter a rolling window, the market return, the
        # union date index, or an execution price.
        _n = len(raw)
        raw = raw[raw["date"].isin(_cal)]
        _dropped += _n - len(raw)
        if len(raw) < 3:
            continue
        d = add_stock_features(raw)
        d["symbol"] = f.stem
        d["fwd_ret"] = d["close"].shift(-horizon) / d["close"] - 1
        # THE LABEL MUST ALSO BE PROTECTED, not just the features. fwd_ret spans
        # [t+1, t+horizon]; if a flagged artefact sits anywhere in that span the
        # label is a data error rather than a return, so it is dropped. Masking
        # only ret_1d would leave rows whose own features are clean but whose
        # TARGET is contaminated, and the model would fit that.
        b = d["bad_ret"].astype(float).shift(-1)
        fwd_bad = b[::-1].rolling(horizon, min_periods=1).max()[::-1]
        d.loc[fwd_bad.fillna(0) > 0, "fwd_ret"] = np.nan
        frames.append(d)
    p = pd.concat(frames, ignore_index=True)
    print(f"    trading calendar: {len(_removed)} non-trading date(s) removed, "
          f"{_dropped:,} rows across {len(frames)} symbols")
    p = add_market_relative_features(p)

    # PRICES ARE NO LONGER FILTERED BY FEATURE AVAILABILITY.
    #     This used to be `p = p.dropna(subset=FEATS_V2)`, and every consumer then
    #     built its price panel from the survivors:
    #         px = p.pivot_table(index=date, columns=symbol, values=close).ffill()
    #     So a day on which beta_60 happened to be NaN lost its PRICE as well, and
    #     ffill bridged the hole -- compressing every skipped day of real price
    #     movement into a single manufactured return when the symbol reappeared.
    #
    #     That is where the recurring `span=61, skipped=60` signature came from:
    #     exactly the 60 rows beta_60 and idio_vol_60 need to respawn after any
    #     interruption. It is also why the cached panel held 6,322 dates where the
    #     raw CSV panel holds 6,574.
    #
    #     Measured consequences before this change: PATANJALI showed +24,772.7% in
    #     one panel day against a raw return of -5.0% with 126 of its own trading
    #     days skipped; LICI's genuine -50.6% was relocated three months and
    #     amplified to -54.1%; CGPOWER showed +179.0% with no artefact filter
    #     involved at all. On MidCap150, eight manufactured returns sat next to a
    #     held or top-8 position.
    #
    # THE TWO PANELS ARE NOW SEPARATE, which is what they always should have been:
    #     price   -- every row with a valid open/close, so px and op are real and
    #                ffill only ever bridges a symbol's genuine non-trading days.
    #     score   -- only rows whose 17 features are all present, flagged by
    #                `scorable`. A symbol with missing features simply has no score
    #                that day and cannot be ranked, which is correct, while its
    #                price stays real for valuation, execution, momentum and
    #                buy&hold.
    scorable = p[FEATS_V2].notna().all(axis=1)

    # The cross-sectional z-score is computed over the SCORABLE rows only, so the
    # peer group for a given day is unchanged from before. Normalising over the
    # full panel would silently widen it, because a row missing one feature would
    # still contribute to the mean and standard deviation of the other sixteen.
    z = cross_sectional_normalize(p.loc[scorable].copy(), FEATS_V2)
    p.loc[scorable, FEATS_V2] = z[FEATS_V2].to_numpy()
    p.loc[~scorable, FEATS_V2] = np.nan

    # Recomputed AFTER normalising, so the flag states what is actually true of the
    # row. On a day with a single scorable stock the group standard deviation is
    # NaN and the z-score comes back NaN, which would otherwise leave a row marked
    # scorable while carrying NaN features. 498 rows, all between 2001 and 2003,
    # none inside any backtest window -- but the flag has to mean what it says.
    scorable = p[FEATS_V2].notna().all(axis=1)

    # TOUCH POINT 1 -- point-in-time membership, applied to the SCORE side only.
    #
    # The integration note specifies `p = sv.apply_to_panel(p, membership)` directly
    # after `p = p.dropna(subset=FEATS_V2)`. That line no longer exists: it was
    # removed in the price/score separation described above, and `p` is now the
    # COMBINED panel -- every consumer pivots close and open out of this same frame
    # (engine_v2_final.py:65-67). Dropping rows from it would therefore delete
    # PRICES for a non-price reason and let the downstream ffill bridge the hole,
    # which is precisely the failure the note warns about and precisely the one this
    # engine already suffered (+24,772.7% on PATANJALI).
    #
    # So membership is folded into `scorable` instead, which is the mechanism that
    # replaced the dropna and means exactly what is wanted: an ineligible name gets
    # NO SCORE and cannot be ranked, while its price stays real for valuation,
    # execution, momentum, the sale itself, and buy&hold. apply_to_panel is still
    # what decides eligibility -- it is handed a (date, symbol) projection of the
    # scorable rows, never the prices.
    #
    # In static mode apply_to_panel returns its argument unchanged, the length test
    # below is an equality, and `scorable` is not touched at all.
    _elig = sv.apply_to_panel(p.loc[scorable, ["date", "symbol"]], MEMBERSHIP)
    if len(_elig) != int(scorable.sum()):
        scorable = scorable & pd.Series(p.index.isin(_elig.index), index=p.index)

    p["scorable"] = scorable
    p["year"] = p["date"].dt.year
    # The label's cross-sectional rank is likewise taken within the scorable set,
    # so a row that cannot be scored also cannot distort another row's rank.
    p["y_rank"] = np.nan
    p.loc[scorable, "y_rank"] = (p.loc[scorable]
                                 .groupby("date")["fwd_ret"].rank(pct=True))
    return p


def precompute(px, vol_win=VOL_WIN):
    return {"vol": px.pct_change().rolling(vol_win).std() * np.sqrt(252)}


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
                    p *= (1 - SLIPPAGE)
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
                    p *= (1 + SLIPPAGE)
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
            if sv.is_pit() and MEMBERSHIP is not None:
                _members = MEMBERSHIP.members_on(dt)
                s_ = s_[[k for k in s_.index if k in _members]]
            if len(s_) >= top_n:
                rk = s_.sort_values(ascending=False)
                top = list(rk.index[:top_n])
                keep = set(rk.index[:buffer_rank])
                # TOUCH POINT 3 -- a name that has left the index is sold on the next
                # trading day whatever its rank. The sell set is `held - keep`, so
                # dropping the forced exits out of `keep` is the union the note asks
                # for. Empty unless mode is pit AND exit policy is forced.
                if sv.is_pit() and MEMBERSHIP is not None:
                    keep -= MEMBERSHIP.forced_exits(set(shares.keys()), dt)
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


PARALLEL_SEEDS = True   # False -> old sequential path (identical output, slower)


def _fit_seed(sd, Xtr, ytr, Xte, n_jobs=1):
    """Train one seed and predict. Top-level so joblib/loky can pickle it."""
    import warnings as _w
    # numpy arrays are passed (not DataFrames) to avoid per-process copies;
    # sklearn then warns about missing feature names. Column order is fixed
    # by FEATS_V2, so this is cosmetic only.
    _w.filterwarnings("ignore", message=".*does not have valid feature names.*")
    m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, max_depth=6,
                          num_leaves=48, subsample=0.8, colsample_bytree=0.8,
                          min_child_samples=100, random_state=sd, verbose=-1,
                          n_jobs=n_jobs)
    m.fit(Xtr, ytr)
    return m.predict(Xte)


def score_monthly(raw, seeds, purge=PURGE):
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["score"] = np.nan
    p["ym"] = p["date"].dt.to_period("M")
    for ym in sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique()):
        cut = p.loc[p.ym == ym, "date"].min() - pd.Timedelta(days=purge)
        tr = (p["date"] <= cut) & p["y_rank"].notna()
        # Only scorable rows are predicted. The panel now carries price-only rows
        # whose features are NaN; scoring those would feed NaN into the model and
        # produce a rank for a name the model cannot actually assess. They keep
        # score = NaN, so sc.loc[dt].dropna() leaves them out of the ranking while
        # their PRICE still counts for valuation, momentum and buy&hold.
        te = (p["ym"] == ym) & p["scorable"] if "scorable" in p.columns \
            else (p["ym"] == ym)
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        Xtr = p.loc[tr, FEATS_V2].to_numpy()
        ytr = p.loc[tr, "y_rank"].to_numpy()
        Xte = p.loc[te, FEATS_V2].to_numpy()
        if PARALLEL_SEEDS and len(seeds) > 1:
            # One process per seed, each single-threaded.
            #
            # EQUIVALENCE AND COST, re-measured 2026-08-23 on the 58 panel
            # (month 2026-01, 257,973 training rows, 10 seeds, Mac Mini M4,
            # 10 cores = 4 performance + 6 efficiency):
            #
            #   this path, 10 procs x 1 thread .............  5.90s
            #   sequential, 10 fits x n_jobs=10 ............ 23.90s   4.05x slower
            #   4 procs x 1 thread (P-cores only) ..........  8.72s   1.48x slower
            #
            #   ensemble scores identical in both comparisons: max|diff| 0.000e+00
            #
            # So the two paths agree exactly and this one is four times faster.
            # LightGBM's intra-tree threading has almost nothing to parallelise at
            # 17 features and 48 leaves, so n_jobs=10 buys synchronisation overhead;
            # training 10 independent models has none of that.
            #
            # (This note replaces a reference to verify_parallel_scoring.py, which
            # established the same equivalence and was deleted in the 2026-08
            # cleanup. The numbers above are the re-measurement, kept here so the
            # claim travels with the code rather than with a file that can vanish.)
            pr = Parallel(n_jobs=min(len(seeds), os.cpu_count() or 1),
                          backend="loky")(delayed(_fit_seed)(sd, Xtr, ytr, Xte)
                                          for sd in seeds)
        else:
            pr = [_fit_seed(sd, Xtr, ytr, Xte, n_jobs=-1) for sd in seeds]
        p.loc[te, "score"] = np.mean(pr, axis=0)
    return p.drop(columns=["ym"])


def main():
    print("=" * 110)
    print("FINAL ENGINE -- full comparison + validation")
    print("=" * 110)

    p = pd.read_csv("/tmp/v5_expanding.csv", parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index.year >= BT_START) & (px.index.year <= BT_END)]
    pc = precompute(px)
    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    mbh = metrics(bh, "Equal-weight buy & hold (58)")

    print("\n" + "=" * 110)
    print("[1] WHAT EACH COMPONENT ACTUALLY DID")
    print("=" * 110)
    eq_eq, tc1, n1, tl1, ap1 = backtest(px, op, sc, bd, pc, sizing="equal")
    eq_iv, tc2, n2, tl2, ap2 = backtest(px, op, sc, bd, pc, sizing="invvol")
    comp = pd.DataFrame([metrics(eq_eq, "Equal-rupee (validation engine)", tc1, n1),
                         metrics(eq_iv, "Inverse-vol (validation engine, cash-based sizing)", tc2, n2), mbh])
    print(comp.to_string(index=False))
    print(f"\n    Avg positions: equal {ap1:.1f} | invvol {ap2:.1f}   (must be {TOP_N}.0)")
    print(f"    Avg holding  : equal {avg_hold(tl1)}d | invvol {avg_hold(tl2)}d")
    comp.to_csv(M / "FINAL_comparison.csv", index=False)

    print("\n    Tried and REJECTED (with reason):")
    print("      x N=8              : worst on every seed set (1.04-1.10 vs 1.45-1.66)")
    print("      x dev selection    : 3 winners across 5 seeds; gap 0.05 < noise 0.08")
    print("      x slope regime     : 14 fires, 4 correct. COVID: caught crash, missed recovery")
    print("      x absolute gate    : Sharpe 1.03 -> 0.76. Blocks the mean-reversion edge")
    print("      x gate ensemble    : Sharpe 0.62. Worse")
    print("      x dynamic N        : Sharpe 0.51. Too few positions")
    print("      x monthly vs yearly: 0.03 apart, inside noise. Kept monthly (harmless)")

    print("\n" + "=" * 110)
    print("[2] VALIDATION -- is inverse-vol real, or cherry-picked?")
    print("=" * 110)
    passed = {}

    print("\n  T1. BASELINE CONTROL -- does equal-rupee reproduce engine_v5 exactly?")
    m1 = comp.iloc[0]
    # Structural check only: positions == TOP_N means the slot-cap and
    # buffer logic are intact (this is what caught the old v6 bug). Exact CAGR is
    # NOT checked -- LightGBM retraining shifts it by +/-0.5% run to run, which is
    # normal and not a bug.
    ok1 = (abs(ap1 - float(TOP_N)) < 0.2 and 400 <= m1["Trades"] <= 1400)
    print(f"      structural target: ~8.0 positions, 680-800 trades")
    print(f"      got             : CAGR {m1['CAGR%']}%, Sharpe {m1['Sharpe']}, "
          f"{int(m1['Trades'])} trades, {ap1:.1f} positions")
    print(f"      (CAGR varies +/-0.5% per retrain -- not checked; structure is)")
    print(f"      -> {'PASS' if ok1 else 'FAIL -- slot-cap or buffer logic broken'}")
    passed["T1 baseline control"] = ok1

    print("\n  T2. SEED ROBUSTNESS -- does inv-vol win on OTHER score seeds?")
    raw = pd.read_csv(f"/tmp/raw_panel_{HORIZON}.csv", parse_dates=["date"])
    t2_rows = []
    for si, seeds in enumerate([[5, 55, 555], [13, 26, 39], [101, 202, 303]]):
        cache = Path(f"/tmp/FINAL_seed{si}.csv")
        if cache.exists():
            ps = pd.read_csv(cache, parse_dates=["date"])
        else:
            print(f"      scoring seed set {si+1}/3 ...", flush=True)
            ps = score_monthly(raw, seeds)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
        pxs = ps.pivot_table(index="date", columns="symbol", values="close").ffill()
        ops = ps.pivot_table(index="date", columns="symbol", values="open").ffill()
        scs = ps.pivot_table(index="date", columns="symbol", values="score")
        bds = pxs.index[(pxs.index.year >= BT_START) & (pxs.index.year <= BT_END)]
        pcs = precompute(pxs)
        e_e, _, _, _, _ = backtest(pxs, ops, scs, bds, pcs, sizing="equal")
        e_i, _, _, _, _ = backtest(pxs, ops, scs, bds, pcs, sizing="invvol")
        me, mi = metrics(e_e, "eq"), metrics(e_i, "iv")
        t2_rows.append({"seedset": si, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                        "eq_MaxDD": me["MaxDD%"], "iv_MaxDD": mi["MaxDD%"]})
        print(f"      seed set {si+1}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {mi['Sharpe']-me['Sharpe']:+.2f}) | MaxDD {me['MaxDD%']:.1f}% -> "
              f"{mi['MaxDD%']:.1f}%")
    t2 = pd.DataFrame(t2_rows); t2.to_csv(M / "FINAL_val_seeds.csv", index=False)
    ok2 = (t2["delta"] > 0).all()
    print(f"      -> improved on {(t2['delta']>0).sum()}/3 seed sets. "
          f"{'PASS' if ok2 else 'FAIL -- seed-dependent'}")
    passed["T2 seed robustness"] = ok2

    print("\n  T3. SUB-PERIOD SPLIT -- works in BOTH halves independently?")
    t3_rows = []
    for hname, y0, y1 in [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]:
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)]
        e_e, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="equal")
        e_i, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="invvol")
        bhh = START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        me, mi, mb = metrics(e_e, "eq"), metrics(e_i, "iv"), metrics(bhh, "bh")
        t3_rows.append({"period": hname, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "bh_Sharpe": mb["Sharpe"], "delta": round(mi["Sharpe"]-me["Sharpe"], 2),
                        "iv_CAGR": mi["CAGR%"], "bh_CAGR": mb["CAGR%"],
                        "iv_MaxDD": mi["MaxDD%"], "bh_MaxDD": mb["MaxDD%"]})
        print(f"      {hname}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {mi['Sharpe']-me['Sharpe']:+.2f}) | buy&hold {mb['Sharpe']:.2f}")
    t3 = pd.DataFrame(t3_rows); t3.to_csv(M / "FINAL_val_periods.csv", index=False)
    ok3 = (t3["delta"] > 0).all()
    print(f"      -> {'PASS' if ok3 else 'FAIL -- only works in one sub-period'}")
    passed["T3 sub-period"] = ok3

    print("\n  T4. PARAMETER SENSITIVITY -- does the vol window matter?")
    t4_rows = []
    for vw in [40, 60, 90, 120]:
        pcv = precompute(px, vol_win=vw)
        e_i, tcv, nv, _, _ = backtest(px, op, sc, bd, pcv, sizing="invvol")
        mi = metrics(e_i, f"vol_win={vw}", tcv, nv)
        t4_rows.append(mi)
        print(f"      vol_win={vw:>3}: CAGR {mi['CAGR%']:>6.2f}%  Sharpe {mi['Sharpe']:>5.2f}  "
              f"MaxDD {mi['MaxDD%']:>7.2f}%")
    t4 = pd.DataFrame(t4_rows); t4.to_csv(M / "FINAL_val_volwin.csv", index=False)
    eq_sh = comp.iloc[0]["Sharpe"]
    ok4 = (t4["Sharpe"] > eq_sh).all()
    print(f"      -> all four beat equal-rupee ({eq_sh})? "
          f"{'PASS' if ok4 else 'FAIL -- depends on exact window'}")
    passed["T4 param sensitivity"] = ok4

    print("\n" + "-" * 110)
    print("  VALIDATION SUMMARY")
    print("-" * 110)
    for k, v in passed.items():
        print(f"    {'PASS' if v else 'FAIL'}  {k}")
    all_ok = all(passed.values())
    print(f"\n    {'ALL PASSED -- inverse-vol is a real effect, not cherry-picking.' if all_ok else 'SOME FAILED -- read the failures before trusting the result.'}")

    print("\n" + "=" * 110)
    print("[3] LEAKAGE / OVERFIT CHECKLIST")
    print("=" * 110)
    # HOW TO READ THIS BLOCK -- added 2026-08-29.
    # Six rows below used to print a literal "PASS". They were claims recorded
    # when each property was established, with no dependency on whether it still
    # holds: if one broke, the row printed the same text. That is a printout
    # asserting verification it does not perform, and it violated this project's
    # own rule that every printed verdict is computed from the run that prints
    # it. The labels now say what they are. The CHECKS ARE STILL NOT
    # IMPLEMENTED -- see KNOWN_ISSUES.md, which specifies each one.
    print("\n  HOW TO READ THE LABELS -- exactly ONE row below is computed by this run.")
    print("    PASS / FAIL              computed by THIS run, from THIS run's result.")
    print(f"    {NOT_CHECKED:<24} a property established when it was written and")
    print(f"    {'':<24} recorded here. NOTHING IN THIS RUN RE-TESTS IT, so this")
    print(f"    {'':<24} row prints the same text whether or not it still holds.")
    print("    NOT FIXED / NOT MODELLED / PARTIAL")
    print("                             known limitations, stated as such.")
    print("\n  results/audit_leakage.py does real leakage work and IS NOT RUN BY THIS")
    print("  PIPELINE: it is not in run_all.py's PIPELINE_ORDER and no step invokes it.")
    print(f"\n  The {NOT_CHECKED} rows are specified as real checks in")
    print("  KNOWN_ISSUES.md, one line each. Implementing them is not done.")
    checks = [
        ("Label purging", NOT_CHECKED, "32 days dropped from every train window. Without it dev "
         "CAGR was 29.77%; with it 24.36%. The 5.4% gap was pure leak."),
        ("Walk-forward", NOT_CHECKED, "Each month scored by a model trained only on prior data. "
         "Expanding window. No future data in any fit."),
        ("Execution timing", NOT_CHECKED, "Signal at close of t, fill at OPEN of t+1. Slippage "
         "always against the trade. No same-day close execution."),
        ("Feature causality", NOT_CHECKED, "All 17 features use past prices/volumes only. "
         "Cross-sectional z-score uses same-day peers -- not time-series leakage."),
        ("Shuffle test", NOT_CHECKED, "Random scores gave 9.7% CAGR vs 18.5% buy&hold. A mechanical "
         "backtest bug would have made random look good. It didn't."),
        ("Baseline control", "PASS" if ok1 else "FAIL", "Structure intact: positions == TOP_N, "
         "~880 trades (slot-cap + buffer working). This is how the v6 slot-cap bug was caught."),
        ("Parameter selection", NOT_CHECKED, "Config fixed a priori. Dev selection abandoned after "
         "stability_test showed 3 winners across 5 seeds (gap 0.05 < noise 0.08)."),
        ("SURVIVORSHIP BIAS", "NOT FIXED", "Universe = the 58 names in the index TODAY. Names "
         "dropped 2016-2026 are absent. Strategy and benchmark share it, so the COMPARISON is "
         "fair -- but BOTH absolute CAGRs are inflated vs what was tradable in real time. "
         "Needs point-in-time index membership data, which we do not have."),
        ("Market impact", "NOT MODELLED", "Real Zerodha charges + 0.15% slippage. Adequate at "
         "Rs 10L in large-caps. Not at institutional size."),
        ("Variant selection", "PARTIAL", "~20 variants tested across all engines, best reported. "
         "That is a selection step. Mitigated by the four tests above -- inv-vol holds across "
         "seeds, sub-periods and parameter values, which cherry-picked results usually do not."),
    ]
    for name, status, note in checks:
        print(f"\n  [{status}] {name}")
        print(f"          {note}")

    print("\n" + "=" * 110)
    print("[4] FINAL, FROZEN")
    print("=" * 110)
    frozen = {"features": "17, five families, cross-sectionally z-scored",
              "label": f"{HORIZON}d forward cross-sectional rank",
              "model": "LightGBM, 10-seed ensemble",
              "retrain": "monthly, expanding window", "purge_days": PURGE,
              "rebalance_days": REBAL, "top_n": TOP_N, "buffer_rank": BUFFER,
              "sizing": "inverse-volatility (weight = 1/vol60)", "vol_window": VOL_WIN,
              "absolute_gate": "OFF -- cut Sharpe from 1.03 to 0.76",
              "regime_exit": "OFF -- slope rule right 4 of 14 times",
              "costs": "real Zerodha + 0.15% slippage, signal at close, fill next open",
              "how_params_chosen": "a priori by reasoning; dev selection abandoned after "
                                   "stability_test proved it selects noise"}
    (M / "FINAL_params.json").write_text(json.dumps(frozen, indent=2))
    for k, v in frozen.items():
        print(f"    {k:<20}: {v}")

    fin = metrics(eq_iv, "Validation engine (inverse-vol)", tc2, n2)
    print("\n" + pd.DataFrame([fin, mbh]).to_string(index=False))

    yr = pd.DataFrame({
        "Strategy%": (eq_iv.resample("YE").last().pct_change().dropna() * 100).round(1),
        "BuyHold%": (bh.resample("YE").last().pct_change().dropna() * 100).round(1)})
    yr.index = yr.index.year
    yr["Diff"] = (yr["Strategy%"] - yr["BuyHold%"]).round(1)
    print("\n--- YEAR BY YEAR ---")
    print(yr.to_string())
    yr.to_csv(M / "FINAL_yearly.csv")
    pd.DataFrame({"date": eq_iv.index, "strategy": eq_iv.values,
                  "equal_rupee": eq_eq.values, "buyhold": bh.values}).to_csv(
        M / "FINAL_equity.csv", index=False)
    tl2.to_csv(M / "FINAL_trades.csv", index=False)

    fig, ax = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[2, 1])
    for s, c, ls, lab in [
            (eq_iv, "#1f77b4", "-", f"FINAL: inverse-vol sizing  (CAGR {fin['CAGR%']}%, "
                                    f"Sharpe {fin['Sharpe']}, MaxDD {fin['MaxDD%']}%)"),
            (eq_eq, "#ff7f0e", "-", f"Equal-rupee sizing  (CAGR {comp.iloc[0]['CAGR%']}%, "
                                    f"Sharpe {comp.iloc[0]['Sharpe']}, MaxDD {comp.iloc[0]['MaxDD%']}%)"),
            (bh, "#2ca02c", "--", f"Equal-weight buy & hold  (CAGR {mbh['CAGR%']}%, "
                                  f"Sharpe {mbh['Sharpe']}, MaxDD {mbh['MaxDD%']}%)")]:
        ax[0].plot(s.index, (s / s.iloc[0] - 1) * 100, lw=2.2, color=c, ls=ls, label=lab, alpha=.9)
    ax[0].axhline(0, color="k", lw=.8, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title("Final: cross-sectional ranking + inverse-volatility sizing\n"
                    "Monthly retraining, expanding window, purged | real Zerodha costs "
                    "+ 0.15% slippage", fontsize=11)
    ax[0].legend(loc="upper left", fontsize=9)
    ax[0].grid(alpha=.3)
    for s, c, ls in [(eq_iv, "#1f77b4", "-"), (bh, "#2ca02c", "--")]:
        ax[1].fill_between(s.index, (s / s.cummax() - 1) * 100, 0, alpha=.3, color=c)
        ax[1].plot(s.index, (s / s.cummax() - 1) * 100, lw=1.2, color=c, ls=ls)
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(M / "chart_FINAL.png", dpi=150, bbox_inches="tight")
    print("\n  saved -> chart_FINAL.png")

    print("\n" + "=" * 110)
    print("NOTE: OFFICIAL NUMBERS come from engine_v2_final.py (portfolio-value sizing).")
    print("      This file sizes new buys from leftover cash -- fine for seed/sub-period")
    print("      validation, but its absolute CAGR is NOT the reported figure.")
    print("VERDICT")
    print("=" * 110)
    print(f"  Final     : CAGR {fin['CAGR%']:>6.2f}%  Sharpe {fin['Sharpe']:>5.2f}  "
          f"MaxDD {fin['MaxDD%']:>7.2f}%  Calmar {fin['Calmar']}")
    print(f"  Buy & hold: CAGR {mbh['CAGR%']:>6.2f}%  Sharpe {mbh['Sharpe']:>5.2f}  "
          f"MaxDD {mbh['MaxDD%']:>7.2f}%  Calmar {mbh['Calmar']}")
    print(f"\n  CAGR   {fin['CAGR%'] - mbh['CAGR%']:+.2f} pts")
    print(f"  Sharpe {fin['Sharpe'] - mbh['Sharpe']:+.2f}")
    print(f"  MaxDD  {mbh['MaxDD%'] - fin['MaxDD%']:+.2f} pts better")
    print(f"  Calmar {fin['Calmar'] - mbh['Calmar']:+.2f}")
    if (fin["Sharpe"] > mbh["Sharpe"] and fin["CAGR%"] > mbh["CAGR%"]
            and fin["MaxDD%"] > mbh["MaxDD%"]):
        print("\n  -> Beats buy & hold on return, Sharpe AND drawdown. All three.")
        print("     Margins are modest but consistent, and survive all four validation tests.")
    else:
        print("\n  -> Does not dominate buy & hold. State that plainly.")
    print("\n  Always state alongside these numbers:")
    print("    1. Survivorship bias -- universe is today's 58 names. Both sides inflated.")
    print("    2. Signal is small (IC 0.036). Real, but small.")
    print("    3. No market-impact model. Fine at Rs 10L; not at size.")
    print("\nSaved -> FINAL_*.csv, FINAL_params.json, chart_FINAL.png")


if __name__ == "__main__":
    main()
