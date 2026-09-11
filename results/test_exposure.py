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
import profiles as _prof            # the run's execution-realism profile

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


# THE CAP HAS NO DEFAULT, DELIBERATELY. `participation_cap=None` used to be the
# signature default, so a caller that simply forgot it silently got `research`
# behaviour -- an uncapped fill -- and nothing in the output said which profile
# produced the number. None is still a legal VALUE (it is what `research`
# resolves to); what is refused is not saying which.
_CAP_REQUIRED = object()


def backtest_exposure(px, op, sc, dates, pc, mom20, port_vol=None,
                      mode="none", target_vol=None, audit=None, sizing="invvol",
                      const_expo=None, value_at_open=True, rebal=None,
                      funding="cash", participation_cap=_CAP_REQUIRED, vol20=None):
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

        NOBODY PASSES False ANY MORE. The four callers that did -- the retired
        58's and 74's engines, their audit and their breadth validation -- were
        deleted with those universes on 2026-09-11. The parameter is kept because
        the choice it names is real, but every live caller is now on the
        open-valued rule that the 92-of-92 gate verifies.

    funding -- HOW THE DAY'S NEW POSITIONS ARE PAID FOR.

        "cash" (default, and the rule this function has always used): each entrant
        is sized at its full whole-portfolio target and paid for out of cash, in
        score-descending order, until cash runs out. The tail is then dropped and
        logged `cash short (before TC)`.

        THAT IS A REAL DEFECT AND IT AFFECTS THE SHIPPING ARM. `invest_val` is a
        share of the WHOLE portfolio and the TOP_N weights sum to 1.0, but a name
        already held is skipped and never resized, and BUFFER names hold capital
        while carrying no target weight at all. So whenever a buffer name is held
        the book is over-committed by construction and cash MUST be short. On this
        repo's own panels it drops 92 to 165 buys per run and leaves the mean book
        below TOP_N. See KNOWN_ISSUES.md and experiments/FUNDING_SPEC.txt.

        "prorata": the entrants are scaled down TOGETHER by a single factor
        f = min(1, cash * 0.98 / total entrant target) instead of the tail being
        dropped one at a time. It changes nothing else. `invest_val` keeps its
        whole-portfolio base, the relative inverse-vol proportions among entrants
        are preserved because f is one scalar applied to all of them, no held
        position is topped up or resized -- experiments/V34_SPEC.txt line 125 --
        and no buffer name is trimmed. The 0.98 is the haircut this function
        already applies to `invest_val`; no new constant is introduced.

        WHY THE DEFAULT IS STILL "cash". Flipping it moves every published v1-v4
        figure and re-baselines the seven identity gates that read
        v34_comparison.csv. FUNDING_SPEC.txt gates the model but does not authorise
        that flip, which is a separate decision with its own blast radius. Note
        also that nautilus/nt_strategy.py mirrors this sizing rule; the mirror is
        exact only while the default is unchanged, so a flip must update the port
        in the same commit."""
    if participation_cap is _CAP_REQUIRED:
        raise TypeError(
            "backtest_exposure(): participation_cap is required. Pass "
            "profiles.participation_cap() -- None under the 'research' profile, a "
            "fraction of prior-20-session median volume under 'tradeable'. It had "
            "a None default, which meant a caller that omitted it silently "
            "measured the research profile whatever the run had selected.")
    # REBALANCE CADENCE. None means "use the module value", which is what every
    # caller relied on when this was only a module global -- so omitting it is
    # byte-identical to the previous behaviour, and rebal_cadence_sweep.py's
    # `test_exposure.REBAL = n` override still works because the module value is
    # read HERE, at call time, not bound at import.
    _rebal = REBAL if rebal is None else int(rebal)
    if _rebal < 1:
        raise ValueError(f"rebal must be >= 1, got {rebal!r}")
    if funding not in ("cash", "prorata"):
        raise ValueError(f'funding must be "cash" or "prorata", got {funding!r}')
    shares, cash = {}, START_CAPITAL
    cum_tc, n_trades = 0.0, 0
    eq, pending, expo_log = [], None, []
    cash_daily = (1 + CASH_YIELD) ** (1 / 252) - 1

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        cash *= (1 + cash_daily)

        # TOUCH POINT 4 -- FORCED EXIT ON A SYMBOL GOING UNTRADEABLE.
        #
        # THIS CANNOT LIVE IN THE SELL BRANCH BELOW. That branch runs only inside
        # `if pending is not None`, i.e. on an EXECUTION day, so a symbol that goes
        # untradeable mid-cycle would not be sold until the next rebalance -- by
        # which time its price is already the frozen ffill. Measured with the exit
        # in the sell branch: dCAGR +0.00 on every arm, because PATANJALI's forced
        # exit landed on 2019-11-27, the day the strategy sold it anyway.
        #
        # BLOCKING ENTRY IS NOT ENOUGH ON ITS OWN, and NaN-ing the price is worse
        # than the defect: the sell branch's `if np.isnan(pr) or pr <= 0: continue`
        # would skip the position and strand it at a frozen mark for the whole gap
        # -- for HEXT that is 1,069 sessions holding a delisted company at 762.55.
        #
        # SELLS ON THE LAST DAY THAT STILL HAS A REAL PRICE, at today's OPEN with
        # the usual slippage, which is the same rule every other sell uses. The map
        # marks the gap from the FIRST MISSING session, so today's open is real.
        if engine_core.TRADEABLE is not None and i + 1 < len(dates):
            _nxt = dates[i + 1]
            for s in [x for x in shares if not engine_core.tradeable_on(x, _nxt)]:
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0:
                    continue
                pr *= (1 - SLIPPAGE)
                q = int(shares[s]); tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                if audit is not None:
                    audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                        "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                        "tc": round(tc, 2)})
                    # LOGGED ON BOTH SIDES. The trade row makes the cash move
                    # reconcile; the skipped row is what makes the REASON visible
                    # in the daily log's section [A] and its run-level tally.
                    audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                        "reason": "forced exit: untradeable from next session",
                        "detail": f"no raw price row from {_nxt.date()}"})
                del shares[s]

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
                # PRO-RATA ENTRANT SCALING (funding="prorata"). See the `funding`
                # note in the docstring and experiments/FUNDING_SPEC.txt.
                #
                # The entrant block is committed `invest_val * sum(w)` by a
                # whole-portfolio calculation but paid for out of cash alone, so
                # when a buffer name holds capital the block cannot fit and the
                # score-descending loop below drops its tail. `f` scales the whole
                # block to what cash can actually carry, so every entrant is filled
                # small rather than the lowest-ranked ones not at all.
                #
                # THE DEFAULT PATH DOES NOT EXECUTE THIS. funding="cash" leaves f
                # at exactly 1.0 without computing anything, and `invest_val * w`
                # is then multiplied by a literal 1.0, which is exact in IEEE-754.
                # The shipped numbers cannot move.
                f = 1.0
                if funding == "prorata":
                    # Entrants only, and only those the loop below could actually
                    # buy: a name with no usable open price is skipped there, so
                    # counting it here would shrink f for money that is never spent.
                    tgt_sum = 0.0
                    for s, w in targets.items():
                        if s == "_exposure" or s in shares:
                            continue
                        pr_ = opens.get(s, np.nan)
                        if np.isnan(pr_) or pr_ <= 0:
                            continue
                        tgt_sum += w
                    need = invest_val * tgt_sum
                    # cash * 0.98 reuses the haircut applied to invest_val above;
                    # it is the allowance for transaction costs and for the
                    # integer-flooring of every quantity. No new constant.
                    if need > 0:
                        f = min(1.0, cash * 0.98 / need)
                for s, w in targets.items():
                    if s == "_exposure" or s in shares:
                        continue
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "no open price (NaN/<=0)", "detail": ""})
                        continue
                    # TOUCH POINT 5 -- BLOCKED ENTRY. The other half of the forced
                    # exit above: never buy into a hole. This reason exists because
                    # "no open price (NaN/<=0)" cannot fire here -- ffill always
                    # supplies a price, which is why that reason fires ZERO times
                    # across every mid and n100 trail while PATANJALI still filled
                    # 33,575 shares on a date with no raw row.
                    if not engine_core.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "untradeable: no raw price row",
                                "detail": "inside a gap in the symbol's own history"})
                        continue
                    pr *= (1 + SLIPPAGE)
                    q = int((invest_val * w * f) // pr)
                    # PARTICIPATION CAP -- profiles.py. None at the default profile,
                    # so `q` is untouched and the published history is exact.
                    #
                    # APPLIED BEFORE THE CASH TEST BELOW, deliberately: the cap
                    # shrinks the order and the cash test then sees the smaller
                    # number. Measured, mid v3 at cap=1.00: mean names held 7.60 ->
                    # 7.72 and cash-short skips 131 -> 123, because shrinking an
                    # early oversized name frees cash for the tail the loop used to
                    # drop. The two constraints cannot both bind harmfully.
                    #
                    # THE REMAINDER STAYS IN CASH. Reallocating it to the next name
                    # would change selection; carrying it to the next session needs
                    # order state the engine does not have.
                    if participation_cap is not None and vol20 is not None:
                        _med = vol20.get(s, {}).get(dt, np.nan)
                        if _med == _med and _med > 0:
                            _lim = int(participation_cap * _med)
                            if q > _lim:
                                if audit is not None:
                                    audit["skipped"].append({"date": dt, "side": "BUY",
                                        "symbol": s,
                                        "reason": "participation cap",
                                        "detail": f"wanted {q:,} sh, capped to {_lim:,} "
                                                  f"({participation_cap:.0%} of prior-20d "
                                                  f"median {_med:,.0f})"})
                                q = _lim
                    if q < 1:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "qty < 1 after sizing",
                                "detail": f"target Rs {invest_val*w*f:,.0f} / price {pr:,.2f}"})
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

        if i % _rebal == 0 and i < len(dates) - 1:
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
                # v IS READ BY THE AUDIT BLOCK BELOW, ON EVERY PATH, so it is
                # bound here rather than inside the else. It used to be bound only
                # where it was USED FOR SIZING, which made sizing="equal" with an
                # audit dict raise UnboundLocalError at the vol60 column -- the one
                # sizing rule that could not be measured was the simplest one.
                # Hoisting changes nothing for invvol/provol: same expression, same
                # dt, one line earlier, and nothing in between touches v or pc.
                v = pc["vol"].loc[dt]
                if sizing == "equal":
                    w = {s: 1.0 / len(top) for s in top}
                else:
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
            px, op, sc, bd, pc, mom20, port_vol, mode=mode, target_vol=target_vol, participation_cap=_prof.participation_cap())
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
