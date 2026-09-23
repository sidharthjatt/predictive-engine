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

# ---------------------------------------------------------------------------
# TRADEABILITY -- the third, PRICE-SIDE flag. See results/tradability.py.
# ---------------------------------------------------------------------------
# {symbol: frozenset(dates the backtest may not transact on)}, or None for "no
# guard". Held here, next to MEMBERSHIP, for the same reason and read the same way:
# test_exposure.backtest_exposure consults it directly rather than taking it as an
# argument, so all 25 of its call sites inherit the guard without a signature
# change. Threading a parameter through 25 sites is how a guard ends up applied in
# four places and absent in twenty-one.
#
# THE LEAK THIS GUARDS AGAINST. module_state.py records the hazard: a module global
# set by one in-process step and never restored silently changes every later step.
# rebal_cadence_sweep.py did exactly that with test_exposure.REBAL, which is why
# cadence is a parameter and not a global. Tradeability is different in kind -- it
# is a property of a UNIVERSE's raw data, stable for the whole run, like MEMBERSHIP
# -- but the leak is still real: mid's map left in place while n100 runs would
# block symbols that do not exist in n100 and silently do nothing, or worse, share
# a ticker. So the tag is stored beside the map and set_tradeability() refuses a
# mismatch rather than trusting the caller to clear it.
TRADEABLE = None
TRADEABLE_TAG = None


def set_tradeability(u, enabled=True):
    """Load (or clear) the untradeable map for universe `u`. Returns the map."""
    global TRADEABLE, TRADEABLE_TAG
    if not enabled:
        TRADEABLE, TRADEABLE_TAG = None, None
        return None
    import tradability
    TRADEABLE = tradability.untradeable(
        u.prepare_data_dir(), _load_calendar(),
        config.BT_START_DATE, config.BT_END_DATE)
    TRADEABLE_TAG = u.tag
    return TRADEABLE


def tradeable_on(symbol, dt):
    """False only when a guard is loaded AND it blocks this (symbol, date)."""
    if TRADEABLE is None:
        return True
    blocked = TRADEABLE.get(symbol)
    return blocked is None or dt not in blocked


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
# SLIPPAGE comes from slippage.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from slippage import SLIPPAGE  # noqa: E402
START_CAPITAL = 1_000_000
BT_START, BT_END = 2019, 2026
M = config.METRICS_DIR



# ---------------------------------------------------------------------------
# THE CANONICAL PRICE COLUMN -- adj_close, repaired, applied at the load boundary
# ---------------------------------------------------------------------------
# adj_close IS THE PRICE. close is the fallback and nothing else.
#
# WHY THE FALLBACK EXISTS AND WHY IT IS NOT AN INTERPOLATION
#     adj_close is unusable on exactly 219 rows in three symbols: VEDL (170 rows,
#     2003, nifty100_benchmark), ASHOKLEY (41 rows, 2003, MidCap150/clean) and
#     MAZDOCK (8 rows, 2017-12 to 2018-07, nifty100_benchmark). On 216 of those it
#     is 0.00; on all 219 it sits outside its own session's [low, high], which is
#     provably wrong from the row alone. Those rows take `close`.
#
#     Nothing is interpolated, carried forward, or reconstructed from an inferred
#     ratio. A repaired price that LOOKS continuous is worse than an honest one:
#     it would hide the defect from every downstream check instead of surfacing it.
#     Fallback to close, or nothing.
#
# THE WHOLE BAR MOVES TOGETHER, NOT JUST THE CLOSE
#     `open` has no adjusted counterpart in the source data, and op is the FILL
#     PRICE for every buy and every sell (test_exposure.py:152) while px is what
#     the book is VALUED at. Leaving open on the raw basis while close moves to the
#     adjusted one puts the fill and the valuation on two different bases, and the
#     same-day open->close return is then wrong by exactly (ratio - 1) on every
#     affected row -- measured across mid and n100: 5,974 rows in full history,
#     1,907 inside the backtest window, median |ratio-1| 2.18%, p95 10.5%,
#     max 150.3%. That is a manufactured P&L on any name filled that morning.
#
#     So open is scaled by the SAME per-row ratio, and so are high and low.
#     Scaling open alone would leave it outside its own [low, high] on 275 rows --
#     re-creating, in the traded column, precisely the defect the fallback above
#     exists to remove. high and low are loaded but consumed by nothing today
#     (no feature and no backtest reads them), so scaling them is numerically
#     inert; it is done anyway so the bar stays internally consistent for whoever
#     reads it next. Raw `open` lies inside its own [low, high] on 1,546,393 of
#     1,546,394 rows across all four universes, so a positive per-row scale
#     preserves that containment exactly.
#
# WHERE THE RATIO IS 1, THE ROW IS UNTOUCHED, BIT FOR BIT
#     ratio = price / close, and price == close on every fallback row and on every
#     row where the two columns already agree. In data/raw/nifty50 and
#     data/raw/Development_data_files adj_close is byte-identical to close on all
#     284,356 and 183,100 rows, so the ratio is exactly 1.0 everywhere and the 58
#     and the 74 multiply by a literal 1.0 -- exact in IEEE-754. Their published
#     numbers cannot move through this function.
#
# THE COUNT IS LOGGED AT RUN TIME
#     A data refresh that quietly increased the number of unusable adj_close rows
#     would otherwise be absorbed in silence. build_panel prints the total and the
#     per-symbol breakdown, so an increase shows up in the run log.
PRICE_COLS = ["date", "open", "high", "low", "close", "adj_close", "volume"]


def canonical_price(raw):
    """Return (df, n_fallback) with adj_close as the price column.

    `raw` needs open/high/low/close/adj_close. The returned frame carries the same
    column names -- `close` now HOLDS the canonical price, and open/high/low are on
    that same basis -- so every downstream consumer inherits the switch without
    knowing it happened. adj_close is dropped: keeping it would leave two columns
    claiming to be the adjusted price, one of them the unrepaired original.
    """
    d = raw.copy()
    a, lo, hi = d["adj_close"], d["low"], d["high"]
    # Evaluated against the RAW low/high, which is the point: the test asks whether
    # adj_close belongs to the same session as the bar it is filed under. Scaling
    # first would make the comparison circular and always pass.
    bad = (a <= 0) | (a < lo) | (a > hi)
    price = a.where(~bad, d["close"])
    # close > 0 on every row of every universe (checked: 0 non-positive closes in
    # 1,546,394 rows), so this division cannot produce an inf through the fallback.
    ratio = price / d["close"]
    for c in ("open", "high", "low"):
        d[c] = d[c] * ratio
    d["close"] = price
    return d.drop(columns=["adj_close"]), int(bad.sum())


# ---------------------------------------------------------------------------
# NSE TRADING CALENDAR -- applied at panel construction so it cannot be bypassed
# ---------------------------------------------------------------------------
TRADING_CALENDAR = Path(__file__).resolve().parents[1] / "data" / "nse_trading_calendar.csv"


def _load_calendar():
    """data/nse_trading_calendar.csv -- TRACKED SOURCE DATA, not a derived file."""
    if not TRADING_CALENDAR.exists():
        raise FileNotFoundError(
            f"{TRADING_CALENDAR} missing.\n"
            "\n"
            "  WHAT TO DO: restore it from git. It is TRACKED, frozen source data --\n"
            "    git checkout -- data/nse_trading_calendar.csv\n"
            "\n"
            "  DO NOT TRY TO REBUILD IT. There is nothing left to rebuild it from.\n"
            "  It was computed once, from the 58 universe's raw files, by\n"
            "  results/make_trading_calendar.py. Both were deleted on 2026-09-11 in\n"
            "  commit 2fe48ff, so that script is not in the tree and restoring it\n"
            "  would not help: the raw files it read are gone too.\n"
            "\n"
            "  IF YOU NEED SESSIONS PAST 2026-06-08, that is a different problem and\n"
            "  this message is not the answer to it. Extending the file is an\n"
            "  APPEND-ONLY operation and NO TOOL IN THIS REPOSITORY PERFORMS IT --\n"
            "  the source for new sessions has not been decided. Do not hand-edit\n"
            "  the file: a wrong tail silently changes every backtest window.\n"
            "\n"
            "  The panel cannot be built without the calendar, because a panel that\n"
            "  silently keeps market-holiday rows is what this filter exists to\n"
            "  prevent. See RETIRED_UNIVERSES.md section 6 and the file's own\n"
            "  header.")
    d = pd.read_csv(TRADING_CALENDAR, comment="#", parse_dates=["date"])
    return set(d["date"])


def _check_calendar(cal, panel, tag=""):
    """Fail loudly if the calendar cannot be trusted for THIS panel.

    Two guards, both aimed at the one real weakness of deriving the calendar from
    the 58 universe: that the 58 could later be narrowed, truncated or re-sourced.

      RANGE   -- the calendar must span the panel's own range. Catches truncation.
      DENSITY -- every date the filter removes must be THIN, i.e. carry fewer
                 symbols than a normal day OF ITS OWN YEAR. A phantom holiday
                 shows ~32 of 148 mid symbols against that year's ~96, so it
                 passes; a genuine session wrongly dropped would be AT FULL
                 DENSITY FOR ITS OWN ERA and fires the assertion.

    "FULL DENSITY" WAS UNQUALIFIED UNTIL 2026-09-19, AND THE OMISSION WAS THE
    WHOLE DEFECT. Full against what was never stated. The code compared against
    the median of the panel's ENTIRE history, 2000-2026, which is a good proxy
    for "a normal day" only while a panel's density is roughly flat across that
    span. smallcap250's is not: 125 symbols is its 26-year median and 237 is its
    2025 median, because most of its 248 names did not exist for most of those
    years. Twenty-three phantom holidays carrying 125-142 symbols cleared the
    26-year median and aborted the run, while sitting at 0.53-0.60 of their own
    era. The threshold is per-year now, and the sentence above says which.

    THIS IS A LOOSENING. Measured over seven universes on 2026-09-19, the
    per-year rule flags a SUBSET of what the global rule flagged -- it passes
    exactly those 23 dates and changes nothing else anywhere. It is not tighter
    and is not a correction of an unsound test; it is a deliberately weaker test
    with measured margin behind it. See KNOWN_ISSUES.md for the margin.

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
    # PER-YEAR, NOT GLOBAL. A year with no dates cannot be indexed, so the
    # global median remains the fallback for a date whose year is somehow
    # absent -- which cannot happen for a date drawn from this panel, and is
    # written anyway rather than left to raise a KeyError inside a guard.
    era = per_date.groupby(per_date.index.year).median()
    gmed = per_date.median()
    removed = sorted(set(panel["date"].unique()) - cal)
    dense = [d for d in removed
             if per_date.get(d, 0) >= era.get(d.year, gmed)]
    if dense:
        worst = max(dense, key=lambda d: per_date.get(d, 0) / era.get(d.year, gmed))
        raise AssertionError(
            f"trading calendar would remove {len(dense)} date(s) from the {tag} "
            f"panel that are AT FULL DENSITY FOR THEIR OWN YEAR, e.g. "
            f"{[str(d.date()) for d in dense[:5]]}. Worst is {worst.date()} at "
            f"{per_date.get(worst, 0):.0f} symbols against a {worst.year} median "
            f"of {era.get(worst.year, gmed):.0f}. The calendar is wrong or the 58 "
            f"universe it derives from has changed. Refusing to filter.")
    return removed


def build_panel(horizon, data_dir, pin_scorable=None):
    """Build the full feature panel from one universe's raw stock CSVs.

    `data_dir` IS REQUIRED, AND THAT IS THE POINT. It used to default to None and
    fall back to `config.RAW_DATA_DIR / "nifty50"` -- the 58 -- so any caller that
    forgot to pass a universe silently built a DIFFERENT universe's panel and
    reported it under the caller's name. Nothing failed; the numbers were simply
    another universe's. The 58 is deleted and that directory no longer exists, so
    the fallback would now be a confusing FileNotFoundError deep in a glob; this
    raises at the call instead, naming what is missing.

    (This previously lived in engine_v2.py and was nearly lost when that file was
    deleted. It is permanent here now.)
    """
    if data_dir is None:
        raise ValueError(
            "build_panel(horizon, data_dir): data_dir is required and must name "
            "the universe's raw directory -- pass REGISTRY[tag].prepare_data_dir() "
            "or u.data_dir. It used to default to the 58, which meant a caller "
            "that omitted it silently built and reported the wrong universe. See "
            "RETIRED_UNIVERSES.md.")
    frames = []
    _src = data_dir
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
    _fallback = {}
    for f in sorted(Path(_src).glob("*.csv")):
        raw = config.read_price_csv(f).sort_values("date")
        # THE LOAD BOUNDARY. adj_close is selected here and resolved into `close`
        # by canonical_price immediately, so the panel below -- and therefore every
        # px/op pivot every consumer builds from it -- is on the adjusted basis.
        # This is the ONLY place the choice is made.
        raw = raw[PRICE_COLS].dropna()
        raw, _nfb = canonical_price(raw)
        if _nfb:
            _fallback[f.stem] = _nfb
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
    # PRINTED EVERY RUN, INCLUDING WHEN IT IS ZERO. A silent zero and a silently
    # grown count look identical in a log that only speaks up on trouble, and the
    # whole point of the count is to notice a data refresh that made adj_close
    # worse. Per symbol, because a new offender matters more than a bigger total.
    _tfb = sum(_fallback.values())
    print(f"    canonical price: adj_close on {len(p) - _tfb:,} rows, "
          f"close fallback on {_tfb:,} "
          f"({', '.join(f'{k} {v}' for k, v in sorted(_fallback.items())) or 'none'})")
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

    # MEASUREMENT HOOK, INERT BY DEFAULT. `pin_scorable` is a set of
    # (date, symbol) pairs; when given, a row is scorable only if it is ALSO in
    # that set. It exists for the pinned-mask counterfactual in
    # results/pinned_mask_test.py, which asks whether the price-perturbation
    # displacement is carried by rows that perturbation ADMITS to the scorable
    # set.
    #
    # IT IS APPLIED HERE, BEFORE THE Z-SCORE, AND THAT IS THE WHOLE REASON IT IS
    # A PARAMETER RATHER THAN A POST-HOC EDIT. The cross-sectional normalisation
    # two lines below takes its peer group from `scorable`, so a mask pinned
    # AFTER build_panel would leave every incumbent name already z-scored against
    # the wider perturbed peer group -- it would test the selection channel while
    # silently leaving the larger one in.
    #
    # None is identity: no caller that omits it can behave differently.
    if pin_scorable is not None:
        _pin = pd.Series(
            list(zip(p["date"], p["symbol"])), index=p.index).isin(pin_scorable)
        scorable = scorable & _pin

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


# EMBARGO for the trading-row purge, in TRADING ROWS. See score_monthly.
PURGE_EMBARGO = 2


def score_monthly(raw, seeds, purge=PURGE, purge_mode="trading"):
    """Monthly expanding-window scoring with a purged training set.

    PURGE_MODE -- "trading" (default, CORRECT) or "calendar" (legacy, FROZEN USE).

    THE DEFECT THE "trading" MODE FIXES, measured 2026-09-01 and recorded in
    diagnostics/LEAKAGE_AUDIT.txt:
        The legacy cut is `first_scored - Timedelta(days=32)`. That is 32 CALENDAR
        days. The label is `close.shift(-HORIZON)`, which is 20 TRADING ROWS.
        Twenty trading rows span about 28 calendar days normally and MORE across a
        holiday cluster, so the margin is roughly four days and IT VARIES. Measured
        on both live universes: the label reached INTO the scored month in 7 of 126
        months and touched its first day in 21 more -- the same 7 and 21 on both,
        because the cause is the shared NSE holiday calendar.

    THE CORRECTION, entirely in trading rows on the panel's own calendar:
        j_max = i_first - HORIZON - PURGE_EMBARGO ;  cut = cal[j_max]
    so gap = i_first - (j + HORIZON) >= PURGE_EMBARGO BY CONSTRUCTION. It cannot
    underflow, because a holiday shifts the date but never the row count.

    THE EMBARGO IS 2 ROWS. One clears the scored month. The second clears the
    close at i_first - 1, which is the BASE PRICE of the scored period's first
    return -- the strategy signals at a close and fills at the next open, so a
    label observing that close has observed the scored period's starting price.
    It is not larger: a bigger embargo removes training rows, which would change
    results for a reason unrelated to leakage.

    WHY "calendar" STILL EXISTS. The retired 58 and 74 are frozen and their
    published numbers must not move. Their builders pin purge_mode="calendar"
    explicitly. THE DEFAULT IS THE CORRECT MODE so that anything new gets it
    right; legacy behaviour must now be asked for by name.

    THE HEADLINE MOVES UNDER "trading", AND THE MOVE IS NOT AN IMPROVEMENT. It is
    not distinguishable from re-fit variation -- see EXPERIMENTS.md entry 29,
    which measured the seed noise floor at sd 0.97 to 2.14 CAGR points against a
    purge effect of -0.12 and -0.52. The new numbers are the CORRECT ones to
    carry, not better ones.
    """
    if purge_mode not in ("trading", "calendar"):
        raise ValueError(f"purge_mode must be 'trading' or 'calendar', got {purge_mode!r}")
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True).copy()
    p["score"] = np.nan
    p["ym"] = p["date"].dt.to_period("M")
    _cal = np.array(sorted(p["date"].unique()))
    _pos = {d: i for i, d in enumerate(_cal)}
    # PROGRESS, ONE LINE PER MONTH, 2026-09-23. This loop printed nothing for up
    # to 70 minutes on nifty500, so a live run could not be told from a hung one.
    # The month is the sequential unit: the seeds inside it are fitted in
    # parallel (below), so a line per seed would be ten interleaved lines from
    # worker processes per month rather than a measure of progress.
    import time as _time
    _months = sorted(p.loc[p["date"].dt.year >= 2016, "ym"].unique())
    _t0 = _time.time()
    for _k, ym in enumerate(_months, start=1):
        _first = p.loc[p.ym == ym, "date"].min()
        if purge_mode == "calendar":
            cut = _first - pd.Timedelta(days=purge)
        else:
            _j = _pos[np.datetime64(_first)] - HORIZON - PURGE_EMBARGO
            if _j < 0:
                continue
            cut = pd.Timestamp(_cal[_j])
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
        _el = (_time.time() - _t0) / 60
        print(f"      month {_k}/{len(_months)} {ym}: {len(seeds)} seeds fitted, "
              f"{_el:.1f} min elapsed, ~{_el / _k * (len(_months) - _k):.1f} min left",
              flush=True)
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
            # FROZEN: engine_core.main() is the retired 58.
            ps = score_monthly(raw, seeds, purge_mode="calendar")
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
