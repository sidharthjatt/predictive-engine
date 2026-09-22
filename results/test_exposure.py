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
import tax_util as _tax_util        # the tax RULES; this file owns the cash

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
# SLIPPAGE comes from slippage.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from slippage import SLIPPAGE  # noqa: E402
import slippage as _sl  # noqa: E402
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

# AND THE CAP'S DATA HAS NO SILENT DEFAULT EITHER. `vol20=None` was the signature
# default from the day the cap was added, so a caller could pass the cap, satisfy
# _CAP_REQUIRED, and still be refused the cap by the `vol20 is not None` test three
# hundred lines below -- silently, with the run reporting the selected profile in
# every filename and every header.
#
# THAT IS THE EXACT FAILURE _CAP_REQUIRED WAS BUILT TO ABOLISH, and it abolished
# half of it. Measured 2026-09-15: results/audit_step.py passed the cap and no
# vol20, so every `--profile tradeable` audit of mid replayed the RESEARCH
# strategy and reconciled it against the TRADEABLE curve -- reported as
# "v1 MISMATCH Rs 3,851,027.09", which is the cap's whole effect to the paisa.
# Thirteen further callers had the same pairing and were saved only by the profile
# axis being unable to reach them.
_VOL20_REQUIRED = object()


def _participation_limit(sym, dt, participation_cap, vol20):
    """The cap in shares for one (symbol, date), or None when it does not apply.

    ONE DEFINITION, THREE CALL SITES -- the BUY, the forced exit and the
    rebalance exit. The cap was on the BUY path only until 2026-09-22, and the
    obvious way to add the sell side is to write the same four lines twice more.
    This repository has spent enough of its history on definitions that were
    copied and then drifted; the cap's semantics live here.

    `participation_cap` x the symbol's prior-20-session MEDIAN volume. Prior, so
    it never uses the day's own volume. Median, so one block trade does not
    licence a large fill. Returns None when no cap is selected, when no vol20 was
    supplied, or when this symbol has no usable median on this date -- the caller
    then transacts uncapped, which is the behaviour that shipped.
    """
    if participation_cap is None or vol20 is None:
        return None
    med = vol20.get(sym, {}).get(dt, float("nan"))
    if med != med or med <= 0:
        return None
    return int(participation_cap * med), med


def _median_volume(sym, dt, vol20):
    """The prior-20-session median for the impact model, or None."""
    if vol20 is None:
        return None
    med = vol20.get(sym, {}).get(dt, float("nan"))
    return None if (med != med or med <= 0) else med


def backtest_exposure(px, op, sc, dates, pc, mom20, port_vol=None,
                      mode="none", target_vol=None, audit=None, sizing="invvol",
                      const_expo=None, value_at_open=True, rebal=None,
                      funding="cash", participation_cap=_CAP_REQUIRED, vol20=_VOL20_REQUIRED,
                      tax_enabled=False, impact_k=None, impact_out=None):
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
    # THE SAME CONTRACT FOR THE IMPACT MODEL, CHECKED AT THE CALL. impact()
    # raises MissingVolume per fill if the median is absent, which is correct but
    # arrives 1,800 sessions in. A caller that passed a k and no volume series is
    # wrong before the first bar, so it is told here.
    if impact_k is not None and (vol20 is _VOL20_REQUIRED or vol20 is None):
        import inspect as _insp
        _f = _insp.stack()[1]
        raise TypeError(
            f"backtest_exposure(): impact_k={impact_k!r} was passed without "
            f"vol20, from {_f.filename}:{_f.lineno}.\n"
            f"  The size-sensitive rate is k * sqrt(qty / prior-20d median "
            f"volume). Without vol20 there is no denominator, and the model "
            f"CANNOT fall back to the flat rate -- that would put research "
            f"arithmetic in an artefact labelled tradeable, which is the defect "
            f"class this model exists inside.\n"
            f"  Pass vol20=tradability.median_volume(...), or impact_k=None.")
    # THE OTHER HALF OF THE SAME CONTRACT. A cap with no volume series is not a
    # cap; it is research arithmetic with a tradeable label on the output. The
    # caller is named because the failure is silent at every other level -- the
    # profile is right, the filenames are right, and only the numbers are wrong.
    if participation_cap is not None and vol20 is _VOL20_REQUIRED:
        import inspect as _insp
        _f = _insp.stack()[1]
        raise TypeError(
            f"backtest_exposure(): participation_cap={participation_cap!r} was "
            f"passed without vol20, from {_f.filename}:{_f.lineno}.\n"
            f"  The cap is applied only where a prior-20-session median volume "
            f"exists for the symbol, so without vol20 NO BUY IS EVER CAPPED and "
            f"this call measures the research strategy under a "
            f"'{__import__('profiles').selected()}' label.\n"
            f"  Pass vol20=tradability.median_volume(u.prepare_data_dir(), "
            f"_load_calendar(), BT_START_DATE, BT_END_DATE) as both engines and "
            f"v34_common do, or declare the intent with "
            f"profiles.research_only(__name__) if this caller is research-only.")
    # THE EXEMPTION MAP IS BUILT ONCE, FROM THE VOLUME SERIES, BEFORE ANY FILL.
    # Defining it by construction is requirement one: a fill that has no median
    # for any reason OTHER than "its symbol's window has not started" must still
    # raise, and a map built up front is what makes that distinguishable.
    _imp_first = _sl.first_priced_date(vol20) if impact_k is not None else {}
    _imp = {"priced": 0, "exempt": 0}

    def _fill_price(side, sym, dt_, raw, qty):
        """(fill price, pending record) for one leg.

        COUNTED ON COMMIT, NOT ON PRICING. A BUY is priced BEFORE the cash tests,
        so counting here would report fills that were then skipped cash-short --
        it read 1,008 priced against 1,006 trades on midcap150. The caller calls
        _commit_impact() once the trade is actually taken.
        """
        flat = (_sl.buy_price if side == "BUY" else _sl.sell_price)
        if impact_k is None:
            return flat(raw, qty, None, None), None
        med, exempt = _sl.resolve(sym, dt_, vol20, _imp_first)
        if exempt:
            return flat(raw, qty, None, None), {
                "date": dt_, "side": side, "symbol": sym, "qty": qty,
                "exempt": True}
        return flat(raw, qty, med, impact_k), {"exempt": False}

    def _commit_impact(pending):
        """Count a leg that was actually transacted, and log an exemption."""
        if pending is None:
            return
        if not pending["exempt"]:
            _imp["priced"] += 1
            return
        _imp["exempt"] += 1
        if audit is not None:
            sym = pending["symbol"]
            audit["skipped"].append({"date": pending["date"], "side": pending["side"],
                "symbol": sym,
                "reason": "impact: no prior-20d median",
                "detail": f"{pending['qty']:,} sh charged the flat rate; {sym}'s "
                          f"first priced date is {_imp_first.get(sym)}, so the "
                          f"prior-20-session window had not started"})

    if vol20 is _VOL20_REQUIRED:
        # research: the cap is None, so the volume series is genuinely unused.
        vol20 = None
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
    # THE TAX LEDGER. None at the default, and `ledger is None` is the only test
    # on the hot path -- the untaxed run does not construct it, does not record a
    # lot and does not evaluate a date. tax_enabled is a PARAMETER rather than a
    # read of tax.selected(), for the same reason rebal and participation_cap are:
    # the caller owns the selection and the engine stays callable from a test that
    # never touches the axis.
    ledger = _tax_util.Ledger(dates) if tax_enabled else None
    cum_tax = 0.0

    cash_daily = (1 + CASH_YIELD) ** (1 / 252) - 1

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        cash *= (1 + cash_daily)

        # TOUCH POINT 6 -- THE ANNUAL TAX LUMP SUM, section 3(9) of the tax
        # reference: each financial year is assessed EXACTLY ONCE, on the first
        # trading day at or after 31 March, and the whole bill leaves cash in one
        # deduction.
        #
        # BEFORE THIS DAY'S FILLS, DELIBERATELY, AND THAT ORDERING IS OURS. The
        # document says the deduction "reduces the capital available to trade the
        # following year", which is only true if the money is gone before the
        # morning's orders are sized -- `q = int((invest_val * w * f) // pr)` reads
        # cash further down. The document does not rule on the same-day case, so
        # this is a stated decision and not a quoted rule; see KNOWN_ISSUES.md.
        #
        # CASH MAY GO NEGATIVE HERE AND IS NOT CLAMPED. A clamp would forgive part
        # of a real liability and silently improve the result; an overdrawn book
        # buys nothing that morning, which is the honest consequence.
        if ledger is not None:
            _due = ledger.due_on(dt)
            if _due:
                cash -= _due
                cum_tax += _due
                if audit is not None:
                    audit["skipped"].append({"date": dt, "side": "TAX", "symbol": "",
                        "reason": f"capital-gains tax assessed, Rs {_due:,.2f}",
                        "detail": "section 3(9): one lump sum, before this day's fills"})

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
                # SYMMETRIC CAP -- same helper, same semantics as the BUY.
                # Until 2026-09-22 SELLs were uncapped: an exit sold the whole
                # holding whatever the symbol's median volume was, so a position
                # the cap would not have let you BUILD could always be unwound in
                # one session. What the cap cannot do is carry the remainder --
                # the engine has no order state -- so an uncapped remainder STAYS
                # HELD and is logged, rather than vanishing.
                q = int(shares[s])
                _capped = _participation_limit(s, dt, participation_cap, vol20)
                _left = 0
                if _capped is not None:
                    _lim, _med = _capped
                    if q > _lim:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "participation cap",
                                "detail": f"wanted {q:,} sh, capped to {_lim:,} "
                                          f"({participation_cap:.0%} of prior-20d "
                                          f"median {_med:,.0f}); remainder stays held"})
                        _left = q - _lim
                        q = _lim
                if q < 1:
                    continue
                pr, _pend = _fill_price("SELL", s, dt, pr, q)
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _commit_impact(_pend)
                if ledger is not None:
                    ledger.sell(s, q, round(pr, 2), dt)
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
                if _left:
                    shares[s] = _left
                else:
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
                    # SYMMETRIC CAP -- the same helper the BUY and the forced
                    # exit use. A name the cap would not let you build can no
                    # longer be unwound in one session either. The uncapped
                    # remainder STAYS HELD and is logged; the engine has no order
                    # state to carry it with.
                    q = int(shares[s])
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    _left = 0
                    if _capped is not None:
                        _lim, _med = _capped
                        if q > _lim:
                            if audit is not None:
                                audit["skipped"].append({"date": dt, "side": "SELL",
                                    "symbol": s,
                                    "reason": "participation cap",
                                    "detail": f"wanted {q:,} sh, capped to {_lim:,} "
                                              f"({participation_cap:.0%} of prior-20d "
                                              f"median {_med:,.0f}); remainder stays held"})
                            _left = q - _lim
                            q = _lim
                    if q < 1:
                        continue
                    pr, _pend = _fill_price("SELL", s, dt, pr, q)
                    tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.sell(s, q, round(pr, 2), dt)
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    if _left:
                        shares[s] = _left
                    else:
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
                    # SIZE AT THE BASE RATE, THEN CHARGE IMPACT ON THE SIZE.
                    # The size-sensitive rate depends on q and q depends on the
                    # rate, so the two cannot both be exact in one pass. The
                    # order is stated rather than left to be inferred: quantity
                    # is decided at the flat rate exactly as it always was, the
                    # cap then shrinks it, and the fill price charges impact on
                    # the quantity actually transacted. Under impact_k=None the
                    # second step is identity and the arithmetic is unchanged.
                    _raw_buy = pr
                    pr = _sl.buy_price(_raw_buy, 0, None, None)
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
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    if _capped is not None:
                        _lim, _med = _capped
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
                    # IMPACT ON THE QUANTITY ACTUALLY TRANSACTED, before the cash
                    # tests, so a buy that impact makes unaffordable is skipped as
                    # cash-short rather than overdrawn. Identity when impact_k is
                    # None. Raises MissingVolume rather than reverting to the flat
                    # rate when the model is on and the median is absent.
                    _pend = None
                    if impact_k is not None:
                        pr, _pend = _fill_price("BUY", s, dt, _raw_buy, q)
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
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.buy(s, q, round(pr, 2), dt)
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
                # kind="mergesort" IS STABLE; pandas' default "quicksort" is not.
                # Two names with the same score were ordered by whatever introsort
                # happened to leave, so nothing decided which of them was held.
                # Measured 2026-09-21 by results/degeneracy_measure.py: there are
                # no ties -- 0 at the TOP_N cut and 0 at the BUFFER cut on all 92
                # rebalances of both live universes, and no duplicate score
                # anywhere in either ranking. The two kinds return an IDENTICAL
                # full ranking on all 92, so this moves no published number. It is
                # here so that a tie arriving later is broken by panel order
                # rather than by the sort algorithm's internal state.
                rk = s_.sort_values(ascending=False, kind="mergesort")
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
    # THE LEDGER RIDES OUT ON THE AUDIT DICT, NOT ON THE RETURN TUPLE. Widening
    # the tuple would break every one of this function's callers, and all of them
    # are untaxed. A caller that wants the tax trail passes an audit dict and
    # finds it under "tax"; a caller that does not is unaffected, which is what
    # keeps tax=off byte-identical rather than merely equal.
    if audit is not None and ledger is not None:
        audit["tax"] = {"ledger": ledger, "cum_tax": cum_tax,
                        "lots": pd.DataFrame(ledger.rows), "leaked": ledger.leaked()}
    # THE COUNT GOES OUT WITH THE RUN. Requirement two: a headline figure from a
    # size-sensitive run must not be readable without the number of fills that
    # were priced at the flat rate instead. `impact_out` is an out-parameter for
    # the same reason `applied_out` is -- the return signature has 25 callers and
    # a module global is the leak cadence.py records.
    if impact_out is not None:
        impact_out.update({"k": impact_k, "priced": _imp["priced"],
                           "exempt": _imp["exempt"],
                           "fills": _imp["priced"] + _imp["exempt"],
                           "trades": n_trades})
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
        # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
        # apply a participation cap even if one were selected; research_only()
        # makes that a statement rather than an accident, and STOPS the run if
        # --profile ever reaches here. See profiles.research_only.
        eq, tc, ntr, avg_expo = backtest_exposure(
            px, op, sc, bd, pc, mom20, port_vol, mode=mode, target_vol=target_vol, participation_cap=_prof.research_only(__name__))
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
