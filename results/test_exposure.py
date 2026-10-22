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
  B. CONST: a fixed exposure, the control breadth is compared against.

The vol-target and min(breadth, vol-target) modes were removed on 2026-10-22: their
target was the median portfolio vol over the whole backtest window, a value no
decision could know on its own date, and no arm used them.

The experiment's own main(), which read a fixed /tmp/v5_expanding.csv from a
retired universe and wrote into results/metrics/, was removed on 2026-09-27;
nothing called it. What remains is backtest_exposure, the engine every arm runs.
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
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
except Exception as _e:
    # No fallback. A flat 0.11% here once replaced the charge library without a
    # word whenever its import failed, which moves every cost figure by about 9%.
    raise ImportError(
        f"qbeast_in_charges could not be imported ({type(_e).__name__}: {_e}). "
        f"calc_tc has no fallback rate; fix the import.") from _e

REBAL, VOL_WIN = 20, 60
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = config.TOP_N, config.BUFFER
_THIN_WARNED = set()      # see the len(s_) < TOP_N branch in backtest_exposure
# SLIPPAGE comes from slippage.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
from slippage import SLIPPAGE  # noqa: E402
import slippage as _sl  # noqa: E402
from config import read_table  # the one CSV/parquet reader: config.read_table
from numerics import rolling_std  # platform-identical variance: results/numerics.py
import capital_axis as _capital_axis  # noqa: E402
# THE DEFAULT, defined once in capital_axis.py. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
START_CAPITAL = _capital_axis.DEFAULT
CASH_YIELD = 0.0        # no yield assumed on idle cash
# BACKTEST WINDOW -- imported from config.py, the single definition.
# Date-based and inclusive. The old year cut (BT_START, BT_END = 2019, 2026)
# ran to 2026-06-08, six trading days beyond this window.
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
# vol20, so every `--profile tradeable` audit of midcap150 replayed the RESEARCH
# strategy and reconciled it against the TRADEABLE curve -- reported as
# "v1 MISMATCH Rs 3,851,027.09", which is the cap's whole effect to the paisa.
# Thirteen further callers had the same pairing and were saved only by the profile
# axis being unable to reach them.
_VOL20_REQUIRED = object()

# dd_overlay's default: read dd_axis.selected() at call time. A sentinel rather
# than None, because None is the explicit "off" a test or a caller may pass.
_DD_FROM_SELECTION = object()

# fixed_capital's default: read fixed_axis.selected() at call time, as dd_overlay.
_FIXED_FROM_SELECTION = object()


def breadth_momentum(mom20, dt):
    """The 20-day momentum breadth is computed over: mom20 on `dt`, present values.

    IN A PIT RUN, ONLY THE MEMBERS ON `dt`. The price panel holds every name in
    the pit folder, and a name is in that folder because it is a member on some
    date, possibly a later one; counting a non-member on `dt` would let a later
    membership change today's exposure. Before the first effective date, where no
    list is in force, the first list is used, the rule survivorship.member_mask
    applies there. Since 2026-10-22."""
    m = mom20.loc[dt].dropna()
    M = engine_core.MEMBERSHIP
    if sv.is_pit() and M is not None:
        _members = M.lists[0] if pd.Timestamp(dt) < pd.Timestamp(M.dates[0]) \
            else M.members_on(dt)
        m = m[[str(k).upper() in _members for k in m.index]]
    return m


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


def backtest_exposure(px, op, sc, dates, pc, mom20,
                      mode="none", audit=None, sizing="invvol",
                      const_expo=None, value_at_open=True, rebal=None,
                      funding="cash", participation_cap=_CAP_REQUIRED, vol20=_VOL20_REQUIRED,
                      tax_enabled=False, impact_k=None, impact_out=None,
                      end_sale=False, drawdown_stop=None, dd_overlay=_DD_FROM_SELECTION,
                      start_capital=None, fixed_capital=_FIXED_FROM_SELECTION):
    """audit=None reproduces the original code path exactly: no overhead, and the
    official numbers are unchanged.

    fixed_capital -- THE FIXED-CAPITAL AXIS (fixed_axis.py). Left unset, it is read
        from fixed_axis.selected(), which is False unless run.py was given
        --fixed-capital, and False runs none of the code that reads it. When on, at
        each rebalance open, after the morning's sells and any tax taken that
        morning: book = min(start capital, port_val), reserve = max(0, port_val -
        start capital), invest_val = book * exposure * 0.98, and the cash tests read
        cash - reserve. Held names are not trimmed. With an audit dict, each
        execution day's open valuation is written to audit["fixed"]. Refused
        together with drawdown_stop, dd_overlay and funding="prorata".

    dd_overlay -- THE DRAWDOWN-LIMIT AXIS (dd_axis.py, results/drawdown_overlay.py).
        Left unset, it is read from dd_axis.selected(), which is None unless
        run.py was given --dd, and None runs none of the code that reads it. A
        DDLimit passed explicitly (tests) overrides the selection. When on, the
        invested fraction is cut to the cushion rule's limit: decided at each
        close, filled at the next open after the arm's own orders, fill kinds
        "dd trim" and "dd top-up". Refused together with drawdown_stop.

    drawdown_stop -- THE STOP OF v5 AND v6 (experiments/DRAWDOWN_STOP_PREREG.txt).
        None, the default, runs none of the code below that reads it, so v1 to v4
        are exactly what they were. An object with `threshold`, `cooldown_cycles`
        and `reentry_breadth` (arms.registry.DrawdownStop) runs this state machine
        on top of the arm's normal rebalancing:
          IN           the running peak of close equity is updated each day. At a
                       close at or below (1 - threshold) x peak, an order to sell
                       everything is placed for the next open and the state is
                       LIQUIDATING. A rebalance order placed at the same close is
                       superseded. A trigger at the last close sells nothing.
          LIQUIDATING  the exit goes through the ordinary sell branch, so the cap,
                       a missing open, slippage, charges and the tax ledger apply
                       exactly as to any sale. Whatever is left is offered again at
                       each next open until the book is flat.
          OUT          from the day the book is flat. For cooldown_cycles x rebal
                       trading days no order is placed. After that, on each
                       rebalance-grid day, breadth is computed exactly as
                       mode="breadth" computes it; at reentry_breadth or more the
                       arm's normal order is placed, below it the arm stays in cash.
          re-entry     if at least one buy fills, the peak resets to that day's
                       close and the state is IN. If none fills, the state stays OUT.
        Every transition is written to audit["stop_events"] when an audit dict is
        passed.

    end_sale -- SELL EVERYTHING ON THE LAST SESSION (2026-09-25). False, the
        default and the headline: positions still held at the end are marked to
        market and never sold, so no gain is realised on them and no sell charge
        is paid. True gives the "sold on the last day" figure: after that day's
        ordinary fills every remaining holding is sold at that day's open, or its
        close where the open is missing, with the same slippage and calc_tc as any
        sell, and the gains enter the tax ledger before the end-of-window
        settlement. The sale is NOT participation-capped: it is a full
        liquidation by definition. False leaves every run exactly as it was.
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
        Measured on a retired universe, v1 arm: it flatters CAGR by 0.79 points (24.62 -> 23.83).

        WHY THE DEFAULT IS True RATHER THAN False. nautilus/nt_attribution.py has
        carried this same switch for longer, and every verification path already
        passes value_at_open=True -- nt_verify.py:119, nt_verify.py:163 and
        verify_v34_arms.py:82. The 92-of-92 correctness gate therefore already
        certifies the OPEN-valued rule. Defaulting to True brings this engine onto
        the basis its own gate verifies, instead of leaving the two disagreeing.

        NOBODY PASSES False ANY MORE. The four callers that did -- the retired
        two retired universes' engines, their audit and their breadth validation -- were
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
            f"_load_calendar(), config.BT_START_DATE, config.BT_END_DATE) as both engines and "
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
                "exempt": True, "med": None}
        return flat(raw, qty, med, impact_k), {"exempt": False, "med": med}

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
    # THE STARTING CAPITAL: capital_axis.selected() unless a caller passes one.
    _cap0 = _capital_axis.selected() if start_capital is None else start_capital
    shares, cash = {}, _cap0
    # SALES WAITING FOR A ROW: {symbol: the session the sale fell due}. See
    # touch point 4.
    _owed = {}
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
    # THE COST TRAIL (results/cost_report.py). Filled only when the caller's audit
    # dict carries a "costs" key, with every fill and every day's cash at full
    # precision. It records what the loop already computed and feeds nothing back,
    # so a run without the key, and every figure of a run with it, is unchanged.
    _costs = audit.get("costs") if audit is not None else None

    # WITH THE IMPACT MODEL ON, each fill also records the median volume it was
    # priced against (None for a fill the model exempted), so cost_report can
    # recompute the impact rate with slippage.impact and split it from the flat
    # slippage. Without the model the record has no such key and is unchanged.
    def _cost_fill(dt_, side, sym, q_, ref, fill, tc_, kind, pend=None):
        if _costs is not None:
            rec = {"date": dt_, "side": side, "symbol": sym, "qty": int(q_),
                   "reference_price": float(ref), "fill_price": float(fill),
                   "charges": float(tc_), "kind": kind}
            if impact_k is not None:
                rec["impact_k"] = float(impact_k)
                rec["impact_median"] = (None if pend is None or pend["med"] is None
                                        else float(pend["med"]))
            _costs["fills"].append(rec)

    cash_daily = (1 + CASH_YIELD) ** (1 / 252) - 1

    # THE DRAWDOWN STOP (results/drawdown_stop.py). Nothing here exists when
    # drawdown_stop is None.
    _stop = drawdown_stop
    if _stop is not None:
        from drawdown_stop import StopState
        _st = StopState(_stop, _rebal, len(dates))
        _stop_log = audit.setdefault("stop_events", []) if audit is not None else None
        _EXIT_ORDER = ({"_exposure": 0.0}, set())   # sell every holding, buy nothing

    # THE DRAWDOWN-LIMIT AXIS (results/drawdown_overlay.py). Nothing below that
    # reads _dd runs when it is None, which is every run without --dd.
    if dd_overlay is _DD_FROM_SELECTION:
        import dd_axis as _dd_axis
        dd_overlay = _dd_axis.selected()
    _dd = dd_overlay
    # THE FIXED-CAPITAL AXIS (fixed_axis.py). Nothing below that reads _fixed runs
    # when it is False, which is every run without --fixed-capital.
    if fixed_capital is _FIXED_FROM_SELECTION:
        import fixed_axis as _fixed_axis
        fixed_capital = _fixed_axis.selected()
    _fixed = bool(fixed_capital)
    if _fixed:
        if _stop is not None or _dd is not None:
            raise ValueError(
                "fixed capital cannot run with the drawdown stop (v5/v6) or the "
                "drawdown limit (--dd): both act on the running peak of compounded "
                "equity, and the fixed-capital book is min(base, equity)")
        if funding != "cash":
            raise ValueError('fixed capital is defined for funding="cash" only')
        _fixed_log = audit.setdefault("fixed", []) if audit is not None else None
    # The idle profit ring-fenced at this morning's open. 0.0 off the axis, and
    # cash - 0.0 is cash exactly, so the cash tests below are unchanged.
    _reserve = 0.0
    if _dd is not None:
        if _stop is not None:
            raise ValueError("the drawdown-limit axis cannot run on a stop arm (v5/v6)")
        from drawdown_overlay import OverlayState
        _ds = OverlayState(_dd, _cap0)
        _dd_rows = set()          # ledger row indices realised by the overlay's sales
        _dd_invested = []         # mtm / equity at each close: Deployed% with the axis on

    for i, dt in enumerate(dates):
        if _stop is not None:
            _st.begin_day()
        prices, opens = px.loc[dt], op.loc[dt]
        _cash_open = cash
        cash *= (1 + cash_daily)
        _cash_int, _tax_pre, _tax_post = cash - _cash_open, 0.0, 0.0

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
                _tax_pre = _due
                if audit is not None:
                    audit["skipped"].append({"date": dt, "side": "TAX", "symbol": "",
                        "reason": f"capital-gains tax assessed, Rs {_due:,.2f}",
                        "detail": "section 3(9): one lump sum, before this day's fills"})

        # TOUCH POINT 4 -- A SALE THAT WAITED FOR A ROW (since 2026-10-16).
        #
        # A name is traded only on a session that has a row for it
        # (engine_core.tradeable_on, results/tradability.py). A sale that fell due
        # on a session with no row was recorded in _owed instead of filling at the
        # forward-filled open, a price nobody quoted. Here, at each session's open,
        # every owed name that has a row today is sold at today's open, the rule
        # every other sell uses. One with no row today stays owed; a name whose
        # file has ended is never sold and stays valued at its last close.
        #
        # This replaces the forced exit that sold a holding on the session BEFORE a
        # gap of two or more sessions. That exit read whether the next session had
        # a row and how long the gap ran, both dated after the decision, and so
        # looked ahead (KNOWN_ISSUES.md).
        #
        # The participation cap applies as to every sell; a capped leftover stays
        # owed and is tried again the next session. A name back in the keep list
        # at the next decision is no longer owed (see the decision below).
        for s in [x for x in list(_owed) if x in shares]:
            if not engine_core.tradeable_on(s, dt):
                continue
            pr = opens.get(s, np.nan)
            if np.isnan(pr) or pr <= 0:
                continue
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
                                      f"median {_med:,.0f}); remainder stays owed"})
                    _left = q - _lim
                    q = _lim
            if q < 1:
                continue
            _ref = pr
            pr, _pend = _fill_price("SELL", s, dt, pr, q)
            tc = calc_tc(pr, q, "SELL")
            cash += q * pr - tc; cum_tc += tc; n_trades += 1
            _cost_fill(dt, "SELL", s, q, _ref, pr, tc, "owed sale", _pend)
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
                del _owed[s]
        for s in [x for x in list(_owed) if x not in shares]:
            del _owed[s]

        # TOUCH POINT 7 -- FORCED EXIT ON A NAME LEAVING THE INDEX. Pit mode only;
        # in static mode, or with no membership loaded, nothing here runs.
        #
        # BESIDE TOUCH POINT 4, FOR THE SAME REASON: a name that leaves between
        # rebalances must not be held until the next one. Each session, a held name
        # that is not in the membership in force today is sold at today's OPEN --
        # the first session on or after the effective date of the row that drops
        # it. Index changes are announced weeks ahead, so that order could be
        # placed in time. Same fill, slippage, charges, participation cap and tax
        # ledger as every other sell; a capped remainder stays held and is retried
        # the next session, as is a name with no raw price row today. The cash is
        # not reinvested until the next rebalance. Touch point 3 still removes the
        # same names from `keep` at a rebalance, which is then a no-op.
        if sv.is_pit() and engine_core.MEMBERSHIP is not None and sv.EXIT_POLICY == "forced":
            _members = engine_core.MEMBERSHIP.members_on(dt)
            for s in [x for x in shares if _members and x.upper() not in _members]:
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0 or not engine_core.tradeable_on(s, dt):
                    continue
                q = int(shares[s])
                _capped = _participation_limit(s, dt, participation_cap, vol20)
                _left = 0
                if _capped is not None and q > _capped[0]:
                    _left, q = q - _capped[0], _capped[0]
                    if audit is not None:
                        audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                            "reason": "participation cap",
                            "detail": f"index exit capped to {q:,} sh; remainder stays held"})
                if q < 1:
                    continue
                _ref = pr
                pr, _pend = _fill_price("SELL", s, dt, pr, q)
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _cost_fill(dt, "SELL", s, q, _ref, pr, tc, "index exit", _pend)
                _commit_impact(_pend)
                if ledger is not None:
                    ledger.sell(s, q, round(pr, 2), dt)
                if audit is not None:
                    audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                        "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                        "tc": round(tc, 2)})
                    audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                        "reason": "forced exit: left the index",
                        "detail": "not in the membership in force on this session"})
                if _left:
                    shares[s] = _left
                else:
                    del shares[s]

        if pending is not None:
            targets, keep = pending
            # The fill kind of this morning's sells: "rebalance" unless the order
            # is a drawdown exit.
            _sell_kind = ("drawdown exit" if _stop is not None and _st.exit_pending
                          else "rebalance")
            if _stop is not None:
                _held_before = dict(shares)
            for s in list(shares.keys()):
                if s not in keep:
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "no open price (NaN/<=0)", "detail": ""})
                        continue
                    # NO ROW TODAY: THE SALE IS OWED, NOT FILLED at the forward-filled
                    # open. Touch point 4 sells it at the open of its next session
                    # with a row. setdefault keeps the session it first fell due.
                    if not engine_core.tradeable_on(s, dt):
                        if s not in _owed and audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "untradeable: no row this session, sale owed",
                                "detail": "sold at the open of the next session with a row"})
                        _owed.setdefault(s, dt)
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
                    _ref = pr
                    pr, _pend = _fill_price("SELL", s, dt, pr, q)
                    tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "SELL", s, q, _ref, pr, tc, _sell_kind, _pend)
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
                # A HELD NAME WITH NO ROW TODAY has no open; it is valued at its
                # last close, which `prices` carries forward. With a row, or with
                # no rule loaded, this is vp[s] exactly as before.
                def _vp(s_):
                    return vp.get(s_, np.nan) if engine_core.tradeable_on(s_, dt) \
                        else prices.get(s_, np.nan)
                port_val = sum(q * _vp(s) for s, q in shares.items()
                               if not np.isnan(_vp(s))) + cash
                if _fixed:
                    # THE FIXED-CAPITAL RING-FENCE (fixed_axis.py). Profit above the
                    # base is held back from every purchase; below the base the book
                    # is the equity, so a loss is not topped up.
                    _book = min(_cap0, port_val)
                    _reserve = max(0.0, port_val - _cap0)
                    _held_open = sum(q_ * _vp(s_) for s_, q_ in shares.items()
                                     if not np.isnan(_vp(s_)))
                    invest_val = _book * targets["_exposure"] * 0.98
                else:
                    invest_val = port_val * targets["_exposure"] * 0.98
                if _dd is not None:
                    # ENTRANTS ARE SIZED AT min(E, A) INSTEAD OF A, from the E
                    # decided at the last close, so they are not bought full and
                    # trimmed the same morning.
                    invest_val *= _ds.entry_factor(targets["_exposure"])
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
                        if np.isnan(pr_) or pr_ <= 0 or not engine_core.tradeable_on(s, dt):
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
                    # TOUCH POINT 5 -- NO BUY ON A SESSION WITH NO ROW. The buy is
                    # dropped, not carried forward. This reason exists because
                    # "no open price (NaN/<=0)" cannot fire here -- ffill always
                    # supplies a price, which is why that reason fires ZERO times
                    # across every midcap150 and nifty100 trail while PATANJALI still filled
                    # 33,575 shares on a date with no raw row. Since 2026-10-16 any
                    # session with no row blocks the buy, however long the gap, and
                    # the first row after a gap is tradeable.
                    if not engine_core.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "untradeable: no row this session",
                                "detail": "no trade in a name on a session without a row"})
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
                    # number. Measured, midcap150 v3 at cap=1.00: mean names held 7.60 ->
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
                    if cash - _reserve < q * pr:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "cash short (before TC)",
                                "detail": f"need Rs {q*pr:,.0f}, have Rs {cash:,.0f}"
                                          + (f", of which Rs {_reserve:,.0f} is the fixed-"
                                             f"capital reserve" if _fixed else "")})
                        continue
                    tc = calc_tc(pr, q, "BUY")
                    if cash - _reserve < q * pr + tc:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "cash short (incl TC)",
                                "detail": f"need Rs {q*pr+tc:,.0f}, have Rs {cash:,.0f}"
                                          + (f", of which Rs {_reserve:,.0f} is the fixed-"
                                             f"capital reserve" if _fixed else "")})
                        continue
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "BUY", s, q, _raw_buy, pr, tc, "rebalance", _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.buy(s, q, round(pr, 2), dt)
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "BUY", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    shares[s] = shares.get(s, 0) + q
                if _fixed and _fixed_log is not None:
                    # THIS MORNING'S OPEN VALUATION, for MaxInvested_base% and for
                    # fixed_capital_test.py: held value before and after the buys,
                    # both at the open the orders filled at.
                    _fixed_log.append({
                        "date": dt, "port_val": port_val, "book": _book,
                        "reserve": _reserve, "held_before_buys": _held_open,
                        "held_after": sum(q_ * _vp(s_) for s_, q_ in shares.items()
                                          if not np.isnan(_vp(s_))),
                        "cash_after": cash})
                _reserve = 0.0
            pending = None
            if _stop is not None and (_st.exit_pending or _st.reentry_pending):
                _st.after_fills(i, shares, _held_before,
                                lambda k: pd.Timestamp(dates[k]).date())

        # THE DRAWDOWN-LIMIT ORDER placed at the last close, after the arm's own
        # fills. See results/drawdown_overlay.py. Each name the order still finds
        # held is resized by the same ratio: sells first, then top-ups funded from
        # cash with the usual 0.98 haircut, scaled down together when cash is short.
        if _dd is not None and _ds.order is not None:
            _ord = _ds.order
            _before = {s: int(shares[s]) for s in _ord if s in shares}
            if not _before:
                _ds.cancel()
            else:
                for s in sorted(_before):
                    dq = _ord[s]
                    if dq >= 0:
                        continue
                    raw = opens.get(s, np.nan)
                    if np.isnan(raw) or raw <= 0 or not engine_core.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "dd trim: no open price (NaN/<=0)", "detail": ""})
                        continue
                    q = min(-dq, int(shares[s]))
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    if _capped is not None and q > _capped[0]:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                                "reason": "participation cap",
                                "detail": f"dd trim wanted {q:,} sh, capped to {_capped[0]:,}"})
                        q = _capped[0]
                    if q < 1:
                        continue
                    pr, _pend = _fill_price("SELL", s, dt, raw, q)
                    tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "SELL", s, q, raw, pr, tc, "dd trim", _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        _n0 = len(ledger.rows)
                        ledger.sell(s, q, round(pr, 2), dt)
                        _dd_rows.update(range(_n0, len(ledger.rows)))
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    shares[s] -= q
                    if shares[s] == 0:
                        del shares[s]
                _buys = [(s, _ord[s]) for s in sorted(_before) if _ord[s] > 0 and s in shares]
                _need = 0.0
                for s, dq in _buys:
                    raw = opens.get(s, np.nan)
                    if not (np.isnan(raw) or raw <= 0):
                        _need += dq * _sl.buy_price(raw, 0, None, None)
                _f = min(1.0, cash * 0.98 / _need) if _need > 0 else 1.0
                for s, dq in _buys:
                    raw = opens.get(s, np.nan)
                    if np.isnan(raw) or raw <= 0 or not engine_core.tradeable_on(s, dt):
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "dd top-up: no open price or untradeable",
                                "detail": ""})
                        continue
                    pr = _sl.buy_price(raw, 0, None, None)
                    q = int(dq * _f)
                    _capped = _participation_limit(s, dt, participation_cap, vol20)
                    if _capped is not None and q > _capped[0]:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "participation cap",
                                "detail": f"dd top-up wanted {q:,} sh, capped to {_capped[0]:,}"})
                        q = _capped[0]
                    if q < 1:
                        continue
                    _pend = None
                    if impact_k is not None:
                        pr, _pend = _fill_price("BUY", s, dt, raw, q)
                    tc = calc_tc(pr, q, "BUY")
                    if cash < q * pr + tc:
                        if audit is not None:
                            audit["skipped"].append({"date": dt, "side": "BUY", "symbol": s,
                                "reason": "dd top-up: cash short",
                                "detail": f"need Rs {q*pr+tc:,.0f}, have Rs {cash:,.0f}"})
                        continue
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    _cost_fill(dt, "BUY", s, q, raw, pr, tc, "dd top-up", _pend)
                    _commit_impact(_pend)
                    if ledger is not None:
                        ledger.buy(s, q, round(pr, 2), dt)
                    if audit is not None:
                        audit["trades"].append({"date": dt, "action": "BUY", "symbol": s,
                            "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                            "tc": round(tc, 2)})
                    shares[s] += q
                _ds.after_fills(dt, _before, {s: int(shares.get(s, 0)) for s in _before})

        # THE LAST-DAY SALE -- see end_sale in the docstring. After the day's
        # ordinary fills and before the end-of-window tax settlement below.
        if end_sale and i == len(dates) - 1:
            for s in list(shares.keys()):
                # No row on the last session: not sold, valued at its last close.
                if not engine_core.tradeable_on(s, dt):
                    continue
                raw = opens.get(s, np.nan)
                if np.isnan(raw) or raw <= 0:
                    raw = prices.get(s, np.nan)
                q = int(shares[s])
                if np.isnan(raw) or raw <= 0 or q < 1:
                    continue
                pr, _pend = _fill_price("SELL", s, dt, raw, q)
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _cost_fill(dt, "SELL", s, q, raw, pr, tc, "last-day sale", _pend)
                _commit_impact(_pend)
                if ledger is not None:
                    ledger.sell(s, q, round(pr, 2), dt)
                if audit is not None:
                    audit["trades"].append({"date": dt, "action": "SELL", "symbol": s,
                        "qty": q, "price": round(pr, 2), "value": round(q*pr, 2),
                        "tc": round(tc, 2)})
                    audit["skipped"].append({"date": dt, "side": "SELL", "symbol": s,
                        "reason": "sold on the last day",
                        "detail": "end_sale=True: full liquidation on the final session"})
                del shares[s]

        _grid = i % _rebal == 0 and i < len(dates) - 1
        _reentry_check = False
        if _grid and _stop is not None and _st.state != "IN":
            # NO NORMAL REBALANCE WHILE THE STOP HOLDS THE ARM OUT. Breadth, when
            # the stop asks for it, is computed exactly as mode="breadth" does.
            def _breadth():
                _m = breadth_momentum(mom20, dt)
                return float((_m > 0).mean()) if len(_m) else 1.0
            _grid = _reentry_check = _st.grid_allows_order(i, _breadth)
            if not _grid:
                expo_log.append(0.0)
        if _grid:
            if mode == "none":
                expo = 1.0
            elif mode == "breadth":
                m = breadth_momentum(mom20, dt)
                expo = float((m > 0).mean()) if len(m) else 1.0
            elif mode == "const":
                # The T3 control of experiments/BREADTH_LIVE_SPEC.txt. Holds a
                # FIXED exposure so that breadth can be compared against the same
                # average cash level, isolating the timing from the level.
                # The caller supplies the level; it is read from the breadth
                # run's own realised mean and is never a literal in this file.
                if const_expo is None:
                    raise ValueError('mode="const" requires const_expo')
                expo = float(const_expo)
            else:
                raise ValueError(f"mode must be 'none', 'breadth' or 'const', got {mode!r}")
            expo = max(0.0, min(1.0, expo))
            expo_log.append(expo)

            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            # TOUCH POINT 2 -- only names in the index on this date may be ranked.
            # engine_core.MEMBERSHIP is the single holder; see the note there.
            if sv.is_pit() and engine_core.MEMBERSHIP is not None:
                _members = engine_core.MEMBERSHIP.members_on(dt)
                s_ = s_[[k for k in s_.index if k in _members]]
            if len(s_) < TOP_N:
                # THIS REBALANCE IS SKIPPED, AND IT USED TO BE SKIPPED SILENTLY.
                # With fewer rankable names than TOP_N the branch below does not
                # run, so no order is planned and the previous holdings carry
                # on. That is the existing behaviour and it is kept -- changing it
                # would move published numbers -- but it is now said, with the
                # date and the count. Once per (date, count, universe width) per
                # process, so four arms over one panel print it once.
                _k = (dt, len(s_), sc.shape[1])
                if _k not in _THIN_WARNED:
                    _THIN_WARNED.add(_k)
                    print(f"    WARNING {pd.Timestamp(dt).date()}: {len(s_)} rankable "
                          f"names < TOP_N={TOP_N}; rebalance skipped, previous "
                          f"holdings kept", flush=True)
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
                # The order exactly as planned, unrounded, for tools/lookahead_proof.py.
                # Audit only: nothing reads it back.
                if audit is not None:
                    audit.setdefault("orders", []).append(
                        {"decided_on": dt, "ranked": list(rk.index), "weights": dict(w),
                         "keep": sorted(keep)})
                # AN OWED SALE IS CANCELLED when this decision keeps the name: the
                # newer decision wins (owner's decision, 2026-10-16).
                for s_ in [x for x in _owed if x in keep]:
                    del _owed[s_]

                if audit is not None:
                    pv_now = sum(q * prices[k] for k, q in shares.items()
                                 if not np.isnan(prices.get(k, np.nan))) + cash
                    held = set(shares.keys())
                    m_ = breadth_momentum(mom20, dt)
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

            if _reentry_check:
                _st.after_reentry_order(pending is not None)

        # TOUCH POINT 6, SECOND HALF -- a year assessed on a day still inside
        # that year (31 March) is charged AFTER the day's fills, so a sell that
        # day is taxed with its own year. See tax_util.Ledger.due_on.
        if ledger is not None:
            _due = ledger.due_on(dt, after_fills=True)
            if _due:
                cash -= _due
                cum_tax += _due
                _tax_post = _due
                if audit is not None:
                    _end = (ledger.end is not None and pd.Timestamp(dt) == ledger.end
                            and ledger.settled_at_end)
                    audit["skipped"].append({"date": dt, "side": "TAX", "symbol": "",
                        "reason": f"capital-gains tax assessed, Rs {_due:,.2f}",
                        "detail": ("settled at the backtest end, after this day's "
                                   "fills, on gains realised to date" if _end else
                                   "section 3(9): one lump sum, after this day's fills "
                                   "(assessment day inside the assessed year)")})

        mtm = sum(q * prices[s] for s, q in shares.items()
                  if not np.isnan(prices.get(s, np.nan)))
        pv = mtm + cash
        if _stop is not None:
            _act = _st.at_close(i, dt, pv, pending is not None, bool(shares),
                                i == len(dates) - 1)
            if _act == "exit":
                if pending is not None and pending is not _EXIT_ORDER \
                        and audit is not None and audit["decisions"]:
                    audit["decisions"][-1]["superseded"] = "drawdown exit"
                if audit is not None and _st.events and _st.events[-1][0] == "trigger":
                    audit["skipped"].append({"date": dt, "side": "STOP", "symbol": "",
                        "reason": "drawdown exit",
                        "detail": f"close equity Rs {pv:,.2f} is {_st.drawdown(pv):+.2%} "
                                  f"from the peak of Rs {_st.peak:,.2f} on "
                                  f"{pd.Timestamp(_st.peak_date).date()}; every holding "
                                  f"is sold at the next open"})
                pending = _EXIT_ORDER
            if _stop_log is not None:
                _stop_log.extend(_st.rows(dt, pv))
        if _dd is not None:
            _dd_invested.append(mtm / pv if pv > 0 else 0.0)
            # A, the arm's own exposure: its last rebalance decision (1.0 for
            # mode "none").
            _ds.at_close(dt, pv, mtm, shares, i == len(dates) - 1,
                         expo_log[-1] if expo_log else 1.0)
        if _costs is not None:
            _costs["days"].append({"date": dt, "cash_open": _cash_open, "interest": _cash_int,
                                   "tax_before_fills": _tax_pre, "tax_after_fills": _tax_post,
                                   "cash_close": cash})
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
    if _dd is not None and audit is not None:
        from drawdown_overlay import marginal_tax
        audit["dd_events"] = _ds.events
        audit["dd"] = dict(_ds.summary(), marginal_tax=(
            marginal_tax(ledger.rows, _dd_rows) if ledger is not None else 0.0))
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
    # THE FOURTH VALUE IS WHAT Deployed% AND avg_exposure_pct REPORT. Without the
    # drawdown limit it is the arm's mean decided exposure, as it always was. With
    # it, the arm's exposure no longer describes the book, so it is the mean
    # invested fraction at the close, after the limit's trims and top-ups.
    if _dd is not None:
        return (pd.Series(eq, index=dates), cum_tc, n_trades,
                float(np.mean(_dd_invested)) if _dd_invested else 1.0)
    return (pd.Series(eq, index=dates), cum_tc, n_trades,
            np.mean(expo_log) if expo_log else 1.0)
