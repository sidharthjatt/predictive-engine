"""
costs.py -- what a trade costs: slippage and market impact, Indian transaction
charges, capital-gains tax and the tax ledger, the participation cap, and the
capacity measure.

Sections, in order:
  1. slippage and market impact (SLIPPAGE, fill_price, impact)
  2. transaction charges (compute_leg_charges, the rate card, the Nautilus fee
     model) and calc_tc, the one wrapper the engines call
  3. capital-gains tax rules and the Ledger
  4. the participation cap and the notices a non-research run carries
  5. capacity: buy fills against the stock's traded value, measured after a run

The run settings these read (profile, impact, cap) are in settings.py. The rule
for a buy that cash cannot fully pay for is in buy_shortfall.py.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from pathlib import Path
from typing import Dict, Set, Tuple

import numpy as np
import pandas as pd

from settings import profile_axis

# ======================================================================================
# SLIPPAGE AND MARKET IMPACT. From slippage.py (moved 2026-11-27).
# ======================================================================================
# slippage.py -- the execution slippage constant, in one place.
#
# WHY THIS EXISTS. SLIPPAGE = 0.0015 was written out SEVEN times:
#
#     results/test_exposure.py:61        results/engine_core.py:140
#     results/make_daily_log.py:37       results/check_b_exec_timing.py:44
#     nautilus/nt_run.py:73              nautilus/nt_attribution.py:64
#     depth_compare.py:40                (derived from nt_run, not a definition)
#
# nt_run's carried the comment "matches SLIPPAGE in results/test_exposure.py",
# which is a duplicate admitting it is one. This repository already records
# VOL_WIN = 60 having sixteen independent definitions and no central home, and four
# tables -- REQUIRED_INPUTS, PIPELINE_ORDER, REPORT_ORDER, FILES -- that each went
# stale as copies. An execution constant is a bad candidate for the next one.
#
# WHY IT MATTERS MORE THAN AN ORDINARY DUPLICATE. These seven live in engines that
# are CROSS-CHECKED AGAINST EACH OTHER. nt_verify reconciles the Nautilus port
# against nt_attribution and against test_exposure's holdings; make_daily_log
# reconciles a cash identity against the same fills; check_b_exec_timing asserts
# fill prices. A value changed in one and not the others does not produce a wrong
# number in that file -- it produces a reconciliation failure somewhere else, which
# is the shape this repository has spent real time chasing.
#
# THIS MODULE CHANGES NO BEHAVIOUR. The value is 0.0015, exactly what all seven
# carried. It is a move, not an edit. A size-sensitive model replacing the flat
# rate is a SEPARATE change, scoped to the `tradeable` profile so `research` stays
# byte-exact, and it belongs here once it exists.
#
# WHAT SLIPPAGE MEANS HERE. A fraction of the fill price, applied symmetrically and
# independent of order size: a BUY pays price * (1 + SLIPPAGE), a SELL receives
# price * (1 - SLIPPAGE). It does not vary with quantity, with the symbol's
# liquidity, or with the participation cap. That flatness is a known limitation of
# the execution model, not a property of the market.
#
# THE FILL PRICE IS ROUNDED TO THE PAISA by fill_price, the same rule as
# ~/Downloads/predictive-backtest's engine.fill_price. It is not placed on NSE's
# dated tick: the prices are split and bonus adjusted, so the tick and its price
# band cannot be known without the later corporate action (KNOWN_ISSUES.md).

# 0.0015 = 15 basis points each way. Unchanged from every site it replaces.
SLIPPAGE = 0.0015


class MissingVolume(Exception):
    """A size-sensitive fill had no prior-20-session median volume to size against.

    RAISED, NOT SWALLOWED, AND THAT IS THE WHOLE POINT. The alternative is to fall
    back to the flat rate for that fill, which produces a run whose output says
    "tradeable" and whose fills are partly research arithmetic, with nothing in
    the artefact saying which. This repository already has that defect recorded
    twice -- the cap that was passed without vol20 and silently applied to
    nothing, and the tradeable artefacts that were byte-identical to their
    research twins under a tradeable filename. A third instance is not wanted.
    """


def impact(qty, median_vol, k):
    """Square-root market impact as a fraction of price, on top of SLIPPAGE.

        impact = k * sqrt(qty / median_vol)

    `qty` is the order size in shares, `median_vol` the symbol's prior-20-session
    MEDIAN volume -- prior so it never uses the day's own volume, median so a
    single block trade does not licence a large fill. Both are the same inputs
    the participation cap already uses, deliberately: two different notions of
    "how big is this order relative to what trades" would be two things to keep
    in step.

    k IS NOT DEFAULTED HERE. It is swept, and a number nobody measured has no
    business being a default in an execution model.

    RAISES MissingVolume when `median_vol` is absent or non-positive. See above.

    THE TOTAL RATE IS SLIPPAGE + impact: a fixed spread cost plus a size term
    that vanishes for a small order. At k=0.002 an order at 10% of median volume
    pays 0.002*sqrt(0.1) = 6.3 bp on top of the 15 bp base; one at 100% of median
    pays 20 bp on top. That convexity is the point -- the flat rate charges the
    same 15 bp either way.
    """
    if median_vol is None or median_vol != median_vol or median_vol <= 0:
        raise MissingVolume(
            f"size-sensitive fill of {qty:,} share(s) has no usable prior-20d "
            f"median volume (got {median_vol!r}); refusing to fall back to the "
            f"flat rate, which would put research arithmetic in a tradeable "
            f"artefact")
    if qty <= 0:
        return 0.0
    return float(k) * (float(qty) / float(median_vol)) ** 0.5


def fill_price(raw, rate, buy):
    """The price a fill trades at: `raw` moved by `rate` against the trade, to the
    paisa. round(raw x (1 + rate), 2) for a buy, round(raw x (1 - rate), 2) for a
    sale, in float64 and rounded by NumPy (half to even on the binary value), as
    predictive-backtest's engine.fill_price does, so the two codebases price the
    same order the same way. 3450 x 0.9985 = 3444.825 gives 3444.82 here and
    3444.83 under Python's round."""
    x = np.float64(raw) * (1.0 + rate) if buy else np.float64(raw) * (1.0 - rate)
    return float(np.round(x, 2))


def buy_price(raw, qty, median_vol, k):
    """Fill price paid for a BUY. k=None is the flat model."""
    return fill_price(raw, SLIPPAGE + (0.0 if k is None else impact(qty, median_vol, k)), True)


def sell_price(raw, qty, median_vol, k):
    """Fill price received for a SELL. k=None is the flat model."""
    return fill_price(raw, SLIPPAGE + (0.0 if k is None else impact(qty, median_vol, k)), False)


def first_priced_date(vol20):
    """{symbol: earliest date at which it has a usable prior-20d median}.

    THE EXEMPTION IS DEFINED BY THIS, NOT BY OBSERVING WHICH FILLS FAILED. A fill
    before its symbol's first priced date has no denominator because the window
    does not exist yet -- `median_volume` is rolling(win).median().shift(1). Since
    2026-10-14 it reads the `win` sessions before the window start, so a symbol is
    exempt only where its own price file has fewer than `win` sessions before the
    fill (a late lister).

    A SYMBOL WITH NO USABLE MEDIAN ANYWHERE IS ABSENT FROM THIS MAP, and a fill on
    it therefore raises. That is the point of building the map rather than
    catching a missing median wherever it appears: "the window has not started"
    is a boundary, "this symbol has no volume data" is a defect, and a catch-all
    would price both at the flat rate and report neither.
    """
    out = {}
    for sym, series in (vol20 or {}).items():
        dates = [d for d, m in series.items() if m == m and m > 0]
        if dates:
            out[sym] = min(dates)
    return out


def resolve(sym, dt, vol20, first_priced):
    """(median, exempt) for one fill, or raise.

    Returns (median, False) when the symbol has a usable median on `dt`.
    Returns (None, True) ONLY when `dt` precedes the symbol's first priced date --
    the start-of-window boundary, which the caller charges at the flat rate and
    MUST count.
    Raises MissingVolume in every other case, including a symbol that never has a
    median and a hole after the window has started.
    """
    med = (vol20 or {}).get(sym, {}).get(dt, float("nan"))
    if med == med and med > 0:
        return med, False
    first = first_priced.get(sym)
    if first is not None and dt < first:
        return None, True
    if first is None:
        raise MissingVolume(
            f"{sym} has no usable prior-20d median on ANY date, so {dt} is not a "
            f"start-of-window boundary; this is missing volume data, not the "
            f"opening-session gap, and is not exempt")
    raise MissingVolume(
        f"{sym} has no prior-20d median on {dt}, which is ON OR AFTER its first "
        f"priced date {first}; the window had already started, so this is a hole "
        f"in the volume series and is not the opening-session exemption")


# ======================================================================================
# TRANSACTION CHARGES (Zerodha, Dhan, Upstox; NSE and BSE). From qbeast_in_charges.py (moved 2026-11-27).
# ======================================================================================
# qbeast_in_charges.py
# ====================================================================================
# QBEAST-AI.N | Indian broker transaction-charges engine (Dhan / Zerodha Kite / Upstox)
# Segments : EQUITY (delivery, intraday, futures, options) | COMMODITY (futures, options)
#            + CURRENCY (futures, options) bonus for Zerodha/Upstox
# Framework: framework-agnostic core + thin NautilusTrader `FeeModel` adapter
#
# ------------------------------------------------------------------------------------
# RATE PROVENANCE  (SPEC_LOCK below — version-lock before consuming downstream)
# ------------------------------------------------------------------------------------
# All *regulatory* legs (STT/CTT, exchange transaction charges, SEBI turnover fee,
# stamp duty, GST) are set by the exchange / government and are therefore IDENTICAL
# across all three brokers. Only BROKERAGE and DP (depository) charges differ.
#
# Rates verified June 2026 against the brokers' own published charge pages:
#   - Zerodha : https://zerodha.com/charges/        (primary source for exchange legs)
#   - Dhan    : https://dhan.co/pricing/
#   - Upstox  : https://upstox.com/brokerage-charges/
#
# >>> POLICY-SENSITIVE CALLOUT (treat as a DECISION-V1-NNN trigger on any change) <<<
#     Union Budget 2026-27 raised F&O STT effective 01-Apr-2026:
#         Equity Futures STT  : 0.0125% -> 0.02% (Oct'24) -> 0.05%  (Apr'26)  [SELL]
#         Equity Options STT  : 0.0625% -> 0.10% (Oct'24) -> 0.15%  (Apr'26)  [SELL, on premium]
#     These two numbers are the most likely to move at the next budget. Re-pin the
#     SPEC_LOCK hash and re-run the self-test (zero skips / zero xfails) when they do.
#
# NOTE on BSE equity transaction charges: BSE rates are scrip-GROUP dependent
# (A/B vs X/Z etc.). The 0.00375% used here is the standard A/B-group flat rate.
# Verify the group for illiquid scrips before trusting BSE equity cost figures.
# ====================================================================================

# ------------------------------------------------------------------ SPEC_LOCK ----
SPEC_LOCK = {
    "module": "qbeast_in_charges",
    "version": "V1-CHG-001",
    "rates_effective": "2026-04-01",   # post Budget-2026 F&O STT hike
    "verified_on": "2026-06-25",
    "gst_rate": "0.18",
}

# ------------------------------------------------------------------ enums --------
class Broker(str, Enum):
    ZERODHA = "ZERODHA"
    DHAN = "DHAN"
    UPSTOX = "UPSTOX"


class Segment(str, Enum):
    EQUITY = "EQUITY"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"


class Product(str, Enum):
    DELIVERY = "DELIVERY"     # EOD / CNC — equity only
    INTRADAY = "INTRADAY"     # MIS — equity only
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"


# ------------------------------------------------------------- rounding ----------
_ZERO = Decimal("0")
_RUPEE = Decimal("1")
_PAISA = Decimal("0.01")


def _r_rupee(x: Decimal) -> Decimal:
    """STT/CTT and stamp duty round to the nearest rupee (HALF_UP, per broker note)."""
    return x.quantize(_RUPEE, rounding=ROUND_HALF_UP)


def _r_paisa(x: Decimal) -> Decimal:
    """All other charges round to 2 decimals (HALF_UP)."""
    return x.quantize(_PAISA, rounding=ROUND_HALF_UP)


# --------------------------------------------------- regulatory rate card --------
# Keyed by (Segment, Product). Rates are FRACTIONS of notional (price * qty).
# 'stt_rate'   : STT (equity/currency) or CTT (commodity), applied on 'stt_sides'.
# 'txn'        : exchange transaction charge per Exchange (both sides).
# 'sebi'       : SEBI turnover fee (both sides); overridden to 1/cr for agri commodity.
# 'stamp'      : stamp duty (BUY side only).
# 'dp'         : True only for equity delivery (charged on the SELL leg, per scrip/day).
RATE_CARD: Dict[Tuple[Segment, Product], dict] = {
    (Segment.EQUITY, Product.DELIVERY): {
        "stt_rate": "0.001",  "stt_sides": {Side.BUY, Side.SELL},
        "txn": {Exchange.NSE: "0.0000307", Exchange.BSE: "0.0000375"},
        "sebi": "0.000001", "stamp": "0.00015", "dp": True,
    },
    (Segment.EQUITY, Product.INTRADAY): {
        "stt_rate": "0.00025", "stt_sides": {Side.SELL},
        "txn": {Exchange.NSE: "0.0000307", Exchange.BSE: "0.0000375"},
        "sebi": "0.000001", "stamp": "0.00003", "dp": False,
    },
    (Segment.EQUITY, Product.FUTURES): {
        "stt_rate": "0.0005", "stt_sides": {Side.SELL},          # 0.05% (Apr-2026)
        "txn": {Exchange.NSE: "0.0000183", Exchange.BSE: "0"},
        "sebi": "0.000001", "stamp": "0.00002", "dp": False,
    },
    (Segment.EQUITY, Product.OPTIONS): {
        "stt_rate": "0.0015", "stt_sides": {Side.SELL},          # 0.15% on premium (Apr-2026)
        "txn": {Exchange.NSE: "0.0003553", Exchange.BSE: "0.000325"},
        "sebi": "0.000001", "stamp": "0.00003", "dp": False,
    },
    (Segment.COMMODITY, Product.FUTURES): {
        "stt_rate": "0.0001", "stt_sides": {Side.SELL},          # CTT 0.01% non-agri
        "txn": {Exchange.MCX: "0.000021", Exchange.NSE: "0.000001"},
        "sebi": "0.000001", "stamp": "0.00002", "dp": False,
    },
    (Segment.COMMODITY, Product.OPTIONS): {
        "stt_rate": "0.0005", "stt_sides": {Side.SELL},          # CTT 0.05%
        "txn": {Exchange.MCX: "0.000418", Exchange.NSE: "0.00001"},
        "sebi": "0.000001", "stamp": "0.00003", "dp": False,
    },
    (Segment.CURRENCY, Product.FUTURES): {
        "stt_rate": "0", "stt_sides": set(),                     # no STT on currency
        "txn": {Exchange.NSE: "0.0000035", Exchange.BSE: "0.0000045"},
        "sebi": "0.000001", "stamp": "0.000001", "dp": False,
    },
    (Segment.CURRENCY, Product.OPTIONS): {
        "stt_rate": "0", "stt_sides": set(),
        "txn": {Exchange.NSE: "0.000311", Exchange.BSE: "0.00001"},
        "sebi": "0.000001", "stamp": "0.000001", "dp": False,
    },
}

# ------------------------------------------------------- brokerage table ---------
# ('zero',) | ('flat', rupees) | ('pct_cap', rate, cap_rupees) -> min(rate*notional, cap)
_BK_DISCOUNT = {
    (Segment.EQUITY, Product.INTRADAY): ("pct_cap", "0.0003", "20"),
    (Segment.EQUITY, Product.FUTURES):  ("pct_cap", "0.0003", "20"),
    (Segment.EQUITY, Product.OPTIONS):  ("flat", "20"),
    (Segment.COMMODITY, Product.FUTURES): ("pct_cap", "0.0003", "20"),
    (Segment.COMMODITY, Product.OPTIONS): ("flat", "20"),
    (Segment.CURRENCY, Product.FUTURES):  ("pct_cap", "0.0003", "20"),
    (Segment.CURRENCY, Product.OPTIONS):  ("flat", "20"),
}

BROKERAGE: Dict[Broker, Dict[Tuple[Segment, Product], tuple]] = {
    Broker.ZERODHA: {
        (Segment.EQUITY, Product.DELIVERY): ("zero",),
        **_BK_DISCOUNT,
    },
    Broker.DHAN: {  # identical discount model to Zerodha; no currency segment
        (Segment.EQUITY, Product.DELIVERY): ("zero",),
        (Segment.EQUITY, Product.INTRADAY): ("pct_cap", "0.0003", "20"),
        (Segment.EQUITY, Product.FUTURES):  ("pct_cap", "0.0003", "20"),
        (Segment.EQUITY, Product.OPTIONS):  ("flat", "20"),
        (Segment.COMMODITY, Product.FUTURES): ("pct_cap", "0.0003", "20"),
        (Segment.COMMODITY, Product.OPTIONS): ("flat", "20"),
    },
    Broker.UPSTOX: {  # NOTE: Upstox charges delivery brokerage (capped at Rs 20) — NOT free
        (Segment.EQUITY, Product.DELIVERY): ("pct_cap", "0.025", "20"),   # SEBI cap 2.5%
        (Segment.EQUITY, Product.INTRADAY): ("pct_cap", "0.001", "20"),
        (Segment.EQUITY, Product.FUTURES):  ("pct_cap", "0.0005", "20"),
        (Segment.EQUITY, Product.OPTIONS):  ("flat", "20"),
        (Segment.COMMODITY, Product.FUTURES): ("pct_cap", "0.0005", "20"),
        (Segment.COMMODITY, Product.OPTIONS): ("flat", "20"),
        (Segment.CURRENCY, Product.FUTURES):  ("pct_cap", "0.0005", "20"),
        (Segment.CURRENCY, Product.OPTIONS):  ("flat", "20"),
    },
}

# DP (depository) base charge per scrip per day, EQUITY DELIVERY SELL only. Pre-GST.
# GST on DP is folded into the aggregated GST line (matches contract-note maths).
DP_BASE: Dict[Broker, str] = {
    Broker.ZERODHA: "13.00",   # 3.50 CDSL + 9.50 Zerodha  (-> 15.34 incl. GST)
    Broker.DHAN:    "12.50",   #                            (-> 14.75 incl. GST)
    Broker.UPSTOX:  "20.00",   # 3.50 CDSL + 16.50 Upstox   (-> 23.60 incl. GST)
}

GST_RATE = Decimal(SPEC_LOCK["gst_rate"])
_SEBI_AGRI = Decimal("0.0000001")  # Rs 1 / crore for agri commodities


# ----------------------------------------------------------- breakdown -----------
@dataclass(frozen=True)
class ChargeBreakdown:
    """All amounts in INR. `total` is the all-in cost for this single executed leg."""
    broker: str
    segment: str
    product: str
    side: str
    exchange: str
    notional: Decimal
    brokerage: Decimal
    stt_ctt: Decimal
    exchange_txn: Decimal
    sebi: Decimal
    stamp_duty: Decimal
    ipft: Decimal
    dp: Decimal
    gst: Decimal
    total: Decimal
    effective_pct: Decimal   # total / notional * 100

    def to_dict(self) -> dict:
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    def __str__(self) -> str:
        rows = [
            ("Brokerage", self.brokerage), ("STT/CTT", self.stt_ctt),
            ("Exchange txn", self.exchange_txn), ("SEBI", self.sebi),
            ("Stamp duty", self.stamp_duty), ("IPFT", self.ipft),
            ("DP charge", self.dp), ("GST", self.gst),
        ]
        head = (f"{self.broker} | {self.segment}/{self.product} {self.side} "
                f"@ notional Rs {self.notional:,.2f} ({self.exchange})")
        body = "\n".join(f"    {name:<14}: Rs {amt:>10,.2f}" for name, amt in rows)
        tail = (f"    {'-'*28}\n    {'TOTAL':<14}: Rs {self.total:>10,.2f}"
                f"   ({self.effective_pct:.4f}% of notional)")
        return f"{head}\n{body}\n{tail}"


# --------------------------------------------------------- brokerage calc --------
def _brokerage(broker: Broker, segment: Segment, product: Product,
               notional: Decimal, female: bool) -> Decimal:
    try:
        rule = BROKERAGE[broker][(segment, product)]
    except KeyError as exc:
        raise ValueError(
            f"{broker.value} does not support {segment.value}/{product.value}"
        ) from exc

    if rule[0] == "zero":
        bk = _ZERO
    elif rule[0] == "flat":
        bk = Decimal(rule[1])
    elif rule[0] == "pct_cap":
        rate, cap = Decimal(rule[1]), Decimal(rule[2])
        bk = min(notional * rate, cap)
    else:  # pragma: no cover  (guarded by tests)
        raise ValueError(f"Unknown brokerage rule {rule!r}")

    # Dhan gives a flat 50% brokerage discount to female account holders.
    if female and broker is Broker.DHAN:
        bk = bk * Decimal("0.5")
    return _r_paisa(bk)


# ----------------------------------------------------------- core API ------------
def compute_leg_charges(
    broker: Broker,
    segment: Segment,
    product: Product,
    side: Side,
    price,                       # per-unit price; OPTION PREMIUM for options
    quantity,                    # total units (lots * lot_size)
    exchange: Exchange,
    *,
    female: bool = False,        # Dhan female 50% brokerage discount
    is_agri: bool = False,       # agri commodity -> SEBI 1/crore (and verify CTT exemption)
    include_dp: bool = True,     # apply DP on equity-delivery sell legs
    include_ipft: bool = False,  # NSE IPFT (negligible: ~Rs 0.01/crore); off by default
    ipft_rate: str = "0.0000000001",
) -> ChargeBreakdown:
    """
    Compute all transaction charges for ONE executed leg (single side of a trade).

    `notional = price * quantity`. For options, pass the PREMIUM as `price`; the
    statutory legs (STT, txn, SEBI, stamp) are correctly levied on premium turnover.

    Returns a frozen `ChargeBreakdown`. Use `compute_roundtrip()` for buy+sell totals.
    """
    key = (segment, product)
    if key not in RATE_CARD:
        raise ValueError(f"Unsupported segment/product: {segment.value}/{product.value}")
    card = RATE_CARD[key]

    notional = Decimal(str(price)) * Decimal(str(quantity))
    if notional < 0:
        raise ValueError("notional must be non-negative (pass positive price and quantity)")

    # 1) Brokerage (broker-specific)
    brokerage = _brokerage(broker, segment, product, notional, female)

    # 2) STT / CTT — only on the applicable side(s)
    if side in card["stt_sides"]:
        stt = _r_rupee(notional * Decimal(card["stt_rate"]))
    else:
        stt = _ZERO

    # 3) Exchange transaction charge — both sides
    txn_rates = card["txn"]
    if exchange not in txn_rates:
        raise ValueError(
            f"{exchange.value} not valid for {segment.value}/{product.value}; "
            f"valid: {[e.value for e in txn_rates]}"
        )
    txn = _r_paisa(notional * Decimal(txn_rates[exchange]))

    # 4) SEBI turnover fee — both sides (agri commodity uses Rs 1/crore)
    sebi_rate = _SEBI_AGRI if (segment is Segment.COMMODITY and is_agri) else Decimal(card["sebi"])
    sebi = _r_paisa(notional * sebi_rate)

    # 5) Stamp duty — BUY side only
    stamp = _r_rupee(notional * Decimal(card["stamp"])) if side is Side.BUY else _ZERO

    # 6) IPFT (NSE) — optional, effectively negligible
    ipft = _r_paisa(notional * Decimal(ipft_rate)) if include_ipft else _ZERO

    # 7) DP charge — equity delivery SELL only, per scrip (pre-GST base)
    dp = Decimal(DP_BASE[broker]) if (card["dp"] and side is Side.SELL and include_dp) else _ZERO

    # 8) GST — 18% on (brokerage + txn + SEBI + DP + IPFT)
    gst = _r_paisa((brokerage + txn + sebi + dp + ipft) * GST_RATE)

    total = brokerage + stt + txn + sebi + stamp + ipft + dp + gst
    eff = (total / notional * Decimal("100")) if notional > 0 else _ZERO

    return ChargeBreakdown(
        broker=broker.value, segment=segment.value, product=product.value,
        side=side.value, exchange=exchange.value, notional=notional,
        brokerage=brokerage, stt_ctt=stt, exchange_txn=txn, sebi=sebi,
        stamp_duty=stamp, ipft=ipft, dp=dp, gst=gst, total=total,
        effective_pct=eff.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
    )


def compute_roundtrip(
    broker: Broker, segment: Segment, product: Product,
    buy_price, sell_price, quantity, exchange: Exchange, **kw
) -> Dict[str, ChargeBreakdown | Decimal]:
    """
    Buy + sell round-trip. Returns {'buy', 'sell', 'total_charges', 'net_pnl'}.
    `net_pnl` = gross P&L (sell - buy on notional) minus all-in charges.
    """
    buy = compute_leg_charges(broker, segment, product, Side.BUY,
                              buy_price, quantity, exchange, **kw)
    sell = compute_leg_charges(broker, segment, product, Side.SELL,
                               sell_price, quantity, exchange, **kw)
    total_charges = buy.total + sell.total
    gross = (Decimal(str(sell_price)) - Decimal(str(buy_price))) * Decimal(str(quantity))
    return {
        "buy": buy,
        "sell": sell,
        "total_charges": _r_paisa(total_charges),
        "net_pnl": _r_paisa(gross - total_charges),
    }


# ============================================================ NautilusTrader =====
# Thin adapter so QBEAST strategies can plug Indian charges straight into the
# backtest engine via BacktestVenueConfig(fee_model=...).
#
# CAVEATS (read before wiring into M9+ live/backtest paths):
#   1. `get_commission` is invoked PER FILL. The discount-broker "Rs 20 per ORDER"
#      cap is per-order, not per-fill. For single-fill market orders this is exact;
#      for orders that fill in multiple partials it can over-count brokerage. Pin a
#      DECISION-V1-NNN on the chosen handling if you trade large/iceberg orders.
#   2. DP is a per-scrip-per-DAY depository charge, not a per-order one. It is
#      therefore OFF by default in the Nautilus path (include_dp=False) and should
#      be reconciled at EOD by the M9 Data Manager rather than booked per fill.
# --------------------------------------------------------------------------------
try:
    from nautilus_trader.backtest.models import FeeModel  # type: ignore
    from nautilus_trader.model.objects import Money, Currency  # type: ignore
    from nautilus_trader.model.enums import OrderSide  # type: ignore
    _HAS_NAUTILUS = True
except Exception:  # pragma: no cover  (core stays importable without the framework)
    _HAS_NAUTILUS = False
    FeeModel = object  # type: ignore


class QbeastIndianFeeModel(FeeModel):
    """
    NautilusTrader FeeModel returning the all-in Indian charge for each fill.

    Example
    -------
        from nautilus_trader.config import BacktestVenueConfig
        fee_model = QbeastIndianFeeModel(
            broker=Broker.ZERODHA, segment=Segment.EQUITY,
            product=Product.INTRADAY, exchange=Exchange.NSE,
        )
        venue = BacktestVenueConfig(name="NSE", fee_model=fee_model, ...)
    """

    def __init__(
        self,
        broker: Broker,
        segment: Segment,
        product: Product,
        exchange: Exchange,
        *,
        female: bool = False,
        is_agri: bool = False,
        include_dp: bool = False,     # OFF in the per-fill path (see caveat 2)
        include_ipft: bool = False,
        currency: str = "INR",
    ):
        if _HAS_NAUTILUS:
            super().__init__()
        self.broker = broker
        self.segment = segment
        self.product = product
        self.exchange = exchange
        self.female = female
        self.is_agri = is_agri
        self.include_dp = include_dp
        self.include_ipft = include_ipft
        self._ccy = currency

    # Cython-style parameter names per NautilusTrader's FeeModel base signature.
    def get_commission(self, Order_order, Quantity_fill_qty, Price_fill_px, Instrument_instrument):
        side = Side.SELL if Order_order.side == OrderSide.SELL else Side.BUY
        # str() on Price/Quantity yields an exact decimal string -> no float drift.
        price = Decimal(str(Price_fill_px))
        qty = Decimal(str(Quantity_fill_qty))

        bd = compute_leg_charges(
            self.broker, self.segment, self.product, side, price, qty, self.exchange,
            female=self.female, is_agri=self.is_agri,
            include_dp=self.include_dp, include_ipft=self.include_ipft,
        )

        ccy = getattr(Instrument_instrument, "quote_currency", None) or Currency.from_str(self._ccy)
        return Money(float(bd.total), ccy)


# ==================================================================== self-test ==
def _selftest() -> None:
    """Zero-skip / zero-xfail worked examples cross-checked vs broker calculators."""
    D = Decimal

    # --- Zerodha equity delivery, 10 sh @ 2800, NSE (buy 2800 / sell 2850) ---
    rt = compute_roundtrip(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                           2800, 2850, 10, Exchange.NSE)
    assert rt["buy"].stt_ctt == D("28"), rt["buy"].stt_ctt          # 0.1% * 28000
    assert rt["buy"].stamp_duty == D("4"), rt["buy"].stamp_duty     # 0.015% * 28000 = 4.2 -> 4
    assert rt["sell"].dp == D("13.00"), rt["sell"].dp               # Zerodha DP base
    assert rt["sell"].stamp_duty == _ZERO                           # no stamp on sell
    assert rt["buy"].brokerage == _ZERO and rt["sell"].brokerage == _ZERO

    # --- Zerodha NIFTY options SELL, premium 100, 75 qty, NSE ---
    opt = compute_leg_charges(Broker.ZERODHA, Segment.EQUITY, Product.OPTIONS,
                              Side.SELL, 100, 75, Exchange.NSE)
    assert opt.brokerage == D("20"), opt.brokerage
    assert opt.stt_ctt == D("11"), opt.stt_ctt                      # 0.15% * 7500 = 11.25 -> 11

    # --- Equity futures STT must reflect the Apr-2026 0.05% sell rate ---
    fut = compute_leg_charges(Broker.UPSTOX, Segment.EQUITY, Product.FUTURES,
                              Side.SELL, 2000, 100, Exchange.NSE)   # notional 200000
    assert fut.stt_ctt == D("100"), fut.stt_ctt                    # 0.05% * 200000 = 100

    # --- Upstox charges delivery brokerage (Rs 20 cap), Zerodha/Dhan do not ---
    ud = compute_leg_charges(Broker.UPSTOX, Segment.EQUITY, Product.DELIVERY,
                             Side.BUY, 500, 100, Exchange.NSE)      # notional 50000
    assert ud.brokerage == D("20"), ud.brokerage                   # min(2.5%*50000, 20)=20
    zd = compute_leg_charges(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                             Side.BUY, 500, 100, Exchange.NSE)
    assert zd.brokerage == _ZERO

    # --- Dhan female 50% intraday brokerage discount ---
    df = compute_leg_charges(Broker.DHAN, Segment.EQUITY, Product.INTRADAY,
                             Side.BUY, 1000, 100, Exchange.NSE, female=True)  # notional 100000
    assert df.brokerage == D("10.00"), df.brokerage                # min(0.03%*1e5,20)=20 ->*0.5=10

    # --- Commodity (MCX) futures CTT on sell ---
    com = compute_leg_charges(Broker.ZERODHA, Segment.COMMODITY, Product.FUTURES,
                              Side.SELL, 70000, 1, Exchange.MCX)    # e.g. 1 crude lot proxy
    assert com.stt_ctt == _r_rupee(D("70000") * D("0.0001")), com.stt_ctt  # 0.01% CTT

    # --- Unsupported combos must raise (Dhan has no currency segment) ---
    for seg, prod, brk in [(Segment.CURRENCY, Product.FUTURES, Broker.DHAN)]:
        try:
            compute_leg_charges(brk, seg, prod, Side.BUY, 80, 1000, Exchange.NSE)
            raise AssertionError("expected ValueError for unsupported combo")
        except ValueError:
            pass

    print("[qbeast_in_charges] self-test PASSED (0 skips / 0 xfails)\n")


def calc_tc(price, qty, side):
    """Zerodha equity-delivery charges on NSE for one fill, in rupees, as a float.

    The one copy. engine_core, test_exposure and nt_attribution each carried an
    identical body until 2026-11-27."""
    if price <= 0 or qty <= 0:
        return 0.0
    bd = compute_leg_charges(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                             Side.BUY if side == "BUY" else Side.SELL,
                             Decimal(str(round(price, 2))), Decimal(str(round(qty, 4))),
                             Exchange.NSE)
    return float(bd.total)


# ======================================================================================
# CAPITAL-GAINS TAX RULES AND THE TAX LEDGER. From tax_util.py (moved 2026-11-27).
# ======================================================================================
# tax_util.py -- Indian capital-gains tax on a realised trade log. THE RULES ONLY.
# ===============================================================================
#
#     axis: settings.tax            engine hook: results/test_exposure.py
#     spec: the reference document's section 3, implemented verbatim
#
# UNPARKED 2026-09-17, AND WHY
#     Parked 2026-08-13 because the comparison it produced was asymmetric: tax was
#     charged to the strategy lines and not to the buy&hold or index lines, which
#     have entirely different tax treatment. A 20-day-churn strategy realises
#     everything at the short-term rate; an equal-weight buy&hold realises once
#     after seven years at the long-term rate. Charging one and not the other
#     overstates the strategy's disadvantage by the whole gap between those
#     regimes.
#
#     THAT IS RESOLVED BY APPLYING ONE RULE TO BOTH LINES, NOT BY WITHHOLDING IT
#     FROM ONE. Strategy and buy&hold are taxed identically here: same lot
#     matching, same holding-period test, same rates, same regime split at
#     2024-07-23, same annual exemption per financial year.
#
#     THE TWO LINES THEN PAY VERY DIFFERENT AMOUNTS, AND THAT DIFFERENCE IS THE
#     RESULT -- NOT A DEFECT IN THE COMPARISON. Buy&hold realises once, at the end
#     of the window, so almost all of its gain is long-term and much of what
#     remains is covered by one annual exemption. The strategy realises 505 lots
#     over 7.4 years, none held longer than 326 days, so every rupee it makes is
#     short-term and is taxed in the year it is earned. The gap between the two
#     bills IS THE TAX COST OF TURNOVER, measured rather than asserted.
#
#     The earlier note was right that charging one line and not the other is
#     unfair. It was wrong to conclude the answer was to charge neither. The
#     answer is to charge both and report the difference, which is the number a
#     reader actually wants.
#
#     TWO THINGS THIS DOES NOT RESOLVE, RECORDED RATHER THAN HIDDEN.
#       1. The benchmark's single terminal realisation lands in the two-month
#          FY2026-27 stub and consumes one full annual allowance for 7.4 years of
#          accrued gain. See THE STUB YEARS below.
#       2. The published `bh` line is a daily-rebalanced equal-weight INDEX, not a
#          held portfolio -- results/engine_v2_final.py:207 builds it from
#          px.pct_change().mean(axis=1). It has no lots to tax. Giving it lots is
#          a DIFFERENT CONSTRUCTION with a different CAGR, reported beside the
#          original and never substituted for it.
#
# WHY THIS IS A REWRITE AND NOT AN EXTENSION
#     The parked file's single organising assumption -- one rate, applied to a
#     running same-financial-year total -- was load-bearing in both of its public
#     functions, and every one of the four things below had to displace it. What
#     survives, deliberately and near-verbatim, is the shape that was right:
#     log-driven rather than reconstructed, FIFO per symbol, None on a missing
#     file, the Indian financial-year expression, and the no-refund clamp.
#
#     Four defects the parked version carried, all fixed here:
#       1. STCG_RATE = 0.20 flat. No long-term rate, no exemption, and NO REGIME
#          SPLIT -- every pre-2024-07-23 gain was taxed at the post-change rate.
#       2. `gain - float(t["tc"])` deducted the SELL leg's charges only; the buy
#          leg's were silently dropped. Section 3(C) deducts NEITHER (see below),
#          so the subtraction is gone entirely rather than corrected.
#       3. No holding-period computation at all. Short versus long was never
#          asked; it rested on a docstring claim that is wrongly reasoned (below).
#       4. after_tax() applied tax as a return-series drag while its docstring
#          claimed a cash deduction. Section 3(9) requires the cash deduction, so
#          the claim is now what the code does -- and the code lives in the
#          engine, not here. This module computes WHAT is owed and WHEN; it never
#          touches an equity curve.
#
# THE DOCSTRING CLAIM THAT WAS WRONG, AND WHY THE CONCLUSION SURVIVED ANYWAY
#     The parked file said: "Every rebalance is 20 days. No position can reach the
#     12-month threshold... That is a structural consequence of a 20-day
#     rebalance, not a modelling assumption."
#
#     IT IS NOT STRUCTURAL. Positions survive rebalances through the BUFFER=16
#     rank band, so the 20-day cadence caps holding period at nothing in
#     particular. MEASURED over the shipped trade logs (FIFO, per symbol):
#
#         daily_trades_mid_tradeable.csv      505 lots   max hold 326 days
#         daily_trades_n100.csv               478 lots   max hold 322 days
#         daily_trades_mid_v1_tradeable.csv   426 lots   max hold 326 days
#
#     THOSE THREE LOGS ARE HISTORICAL -- retired universes, and on them zero lots
#     exceeded 365 days. "100% short-term" was true there. IT IS NOT TRUE NOW: the
#     2026-09-18 four-universe runs put four lots past the threshold, on nifty100
#     and nifty50, and max_holding_days()' own docstring lists them. What was
#     empirical stayed empirical and then changed, which is what empirical means.
#
#     So holding period is COMPUTED PER LOT and branched on, never hardcoded, and
#     max_holding_days() exists so a check can fail loudly when a universe crosses
#     365 rather than the long-term branch quietly beginning to fire.
#
# TWO KEYS, TWO DIFFERENT CONDITIONS, AND FY2024-25 EXERCISES BOTH AT ONCE
#     THE RATE is keyed on the SALE DATE (section 3(8)): old before 2024-07-23,
#     new on or after it.
#     THE EXEMPTION is keyed on the FINANCIAL YEAR (section 3(5)/(6)): Rs 1,00,000
#     for FY < 2024, Rs 1,25,000 for FY >= 2024.
#
#     These are NOT the same test and must not be collapsed into one. A lot sold
#     on 2024-05-30 is inside FY2024-25 -- so it draws on the Rs 1,25,000
#     exemption -- while its sale date is before the cutoff, so it is taxed at the
#     OLD rate. The document's own worked table shows Rs 1,25,000 for FY2024-25,
#     which is only consistent with the two being independent.
#
# THE STUB YEARS, DECIDED IN THE OPEN
#     The window 2019-01-01 .. 2026-05-29 covers nine financial years, seven full
#     and two stubs: FY2018-19 is Q4 only and FY2026-27 is two months.
#
#     EVERY FINANCIAL YEAR GETS THE FULL ANNUAL EXEMPTION, INCLUDING BOTH STUBS.
#     The document is SILENT on stub years. Pro-rating is therefore not a rule
#     taken from it -- it would be a modelling choice wearing a tax rule's
#     clothes, and it is not invented here. An annual allowance is not earned by
#     elapsed time in any statute.
#
#     THE CONSEQUENCE, STATED RATHER THAN BURIED: it is inert on the strategy,
#     whose long-term bucket is empty in every year, and it is entirely live on
#     the benchmark, whose single terminal realisation lands in the two-month
#     FY2026-27 stub and takes one full year's allowance against 7.4 years of
#     accrued gain. Pro-rating would not fix that; only a staged liquidation
#     would, and that is a different benchmark.
#
#     THE LAST STUB IS SETTLED AT THE BACKTEST END, SINCE 2026-09-25. Section 3(9)
#     assesses a financial year on the first trading day at or after 31 March. For
#     FY2026-27 that date is in 2027, outside the backtest window, so until
#     2026-09-25 its liability was computed and never deducted. By the owner's
#     decision of 2026-09-25 it is now deducted from cash on the window's last
#     session, after that day's fills, on the gains realised to that date, with the
#     document's netting and exemption rules unchanged (Ledger.due_on,
#     liability_schedule). The document says nothing about a window that ends
#     mid-year; this settlement date is that decision, not a rule quoted from it.
#     The FY2026-27 exemption is the full annual Rs 1,25,000, as for every other
#     financial year: the document keys the exemption on the financial year and
#     does not pro-rate, so neither does this.
#
# TAX PARTIALLY DAMPS ITSELF, AND THE TWO NUMBERS MUST NOT BE SWAPPED
#     The deduction shrinks cash, cash sizes every order, smaller positions realise
#     smaller gains, and a smaller gain is a smaller bill. So a taxed run pays LESS
#     than its own untaxed trade log implies -- tax partially damps itself.
#
#     MEASURED ON midcap150, full window, v2 breadth arm:
#
#         Rs 833,105   implied by the UNTAXED run's trade log
#         Rs 798,365   actually charged by the TAXED run        (-4.2%)
#
#     THE SECOND NUMBER IS THE ONLY ONE THAT MAY APPEAR IN FY_TAX_STATEMENT. It is
#     what the portfolio paid, it reconciles with FY_EQUITY to the paisa, and the
#     first describes a run that did not happen. The gap is an observation recorded
#     here once, with both figures and which run produced each; it is not a
#     statement column and no artefact carries it as a figure.
#
# WHAT IS NOT MODELLED -- section 3(D), carried over verbatim in substance
#     Carry-forward of a net loss: a net-loss year pays nil and the loss is
#     DISCARDED, not carried forward. The code floors at zero and resets each
#     financial year. Also absent: surcharge and cess (understates tax by >= 4%),
#     [SUPERSEDED 2026-10-14: losses are now carried forward and set off, and the
#     4% cess is charged; see THE 2026-10-14 RULES below. The paragraph is kept as
#     the record of what the figures before that date assumed.]
#     s.112A grandfathering for pre-31-Jan-2018 acquisitions, and quarterly
#     advance tax. The portfolio is treated as a standalone taxpayer, though the
#     exemption is really per person across all holdings.
#
#     AND CHARGES ARE NOT DEDUCTED FROM THE GAIN AT ALL -- section 3(C),
#     treatment (ii): gain is the price difference only. This OVERSTATES the gain
#     and therefore the tax, because real brokerage and exchange charges would
#     reduce a taxable gain. It is CONSERVATIVE in the direction that matters: it
#     cannot make the strategy look better than it is. Our charge engine persists
#     a per-fill `tc` and could support the statutory split, in which STT is not
#     deductible while brokerage and exchange charges are; that is deliberately
#     not done here, because the document's rule is the rule being implemented.

# ---------------------------------------------------------------------------
# SECTION 3, ITEMS 1-8. Every constant below is the document's, not a default.
# ---------------------------------------------------------------------------
CGT_REGIME_CHANGE = pd.Timestamp("2024-07-23")   # item 8, the transfer-date cut

# ---------------------------------------------------------------------------
# THE 2026-10-14 RULES, decided by the owner where the document departs from
# the Income-tax Act for listed equity under s.111A/112A:
#   holding period  long-term only when held MORE THAN TWELVE CALENDAR MONTHS
#                   (sale date after the buy date plus 12 months), not a day
#                   count; the document's `held_days >= 365` is retired.
#   within a year   a net short-term loss is set off against long-term gains.
#   carry-forward   a net short-term loss carries forward up to 8 financial
#                   years against later short- and long-term gains; a net
#                   long-term loss up to 8 years against later long-term gains
#                   only; oldest loss first; set off before the LTCG exemption.
#   cess            4% health and education cess on the tax.
# STILL LEFT OUT: surcharge (it depends on the person's total income), the basic
# exemption limit, advance-tax instalment timing; the timely return filing that
# carry-forward requires is assumed. See KNOWN_ISSUES.md.
# ---------------------------------------------------------------------------
LTCG_HOLD_MONTHS = 12
CARRY_FORWARD_YEARS = 8
CESS_RATE = 0.04

# item 1-4, keyed on the SALE DATE via regime_of()
STCG_RATE = {"old": 0.15,  "new": 0.20}
LTCG_RATE = {"old": 0.10,  "new": 0.125}

# item 5-6, keyed on the FINANCIAL YEAR -- a DIFFERENT condition from the rates.
LTCG_EXEMPTION_OLD = 100_000.0     # FY < 2024
LTCG_EXEMPTION_NEW = 125_000.0     # FY >= 2024
LTCG_EXEMPTION_FY_CUT = 2024

BUCKETS = ("short_old", "short_new", "long_old", "long_new")


def is_long_term(buy_date, sale_date):
    """True when the lot was held MORE than twelve calendar months: sold after the
    buy date plus 12 months. Bought 2023-01-31: 2024-01-31 is short, 2024-02-01 long."""
    return pd.Timestamp(sale_date) > (pd.Timestamp(buy_date)
                                      + pd.DateOffset(months=LTCG_HOLD_MONTHS))


def long_term_mask(lots):
    """is_long_term over a lots frame with buy_date and sell_date columns."""
    b = pd.to_datetime(lots["buy_date"])
    s = pd.to_datetime(lots["sell_date"] if "sell_date" in lots else lots["date"])
    return s > b + pd.DateOffset(months=LTCG_HOLD_MONTHS)


class CarryForward:
    """Losses brought forward, by the financial year they arose in.

    short  usable against later short-term, then long-term gains
    long   usable against later long-term gains only
    A loss from year f may be set off in years f+1 to f+8; the oldest goes first.
    The caller assesses years in ascending order with one instance.
    """

    def __init__(self):
        self.pools = {"short": [], "long": []}     # [fy, amount] each
        self.last_fy = None

    def start(self, fy):
        if self.last_fy is not None and fy <= self.last_fy:
            raise ValueError(f"carry-forward: FY {fy} assessed after FY {self.last_fy}; "
                             f"years must be assessed in ascending order")
        self.last_fy = fy
        for k in self.pools:
            self.pools[k] = [p for p in self.pools[k]
                             if fy - p[0] <= CARRY_FORWARD_YEARS and p[1] > 0]

    def use(self, kind, need):
        got = 0.0
        for p in self.pools[kind]:
            if got >= need:
                break
            t = min(p[1], need - got)
            p[1] -= t
            got += t
        return got

    def add(self, kind, fy, amount):
        if amount > 0:
            self.pools[kind].append([fy, amount])

    def balance(self):
        return {k: sum(p[1] for p in v) for k, v in self.pools.items()}


def financial_year(ts):
    """The Indian financial year containing `ts`, as its START year.

    1 April to 31 March, so 2024-05-30 and 2025-02-14 are both FY 2024.
    The expression is the parked file's, which was correct.
    """
    ts = pd.Timestamp(ts)
    return ts.year - (1 if ts.month < 4 else 0)


def fy_label(fy):
    """FY 2024 -> 'FY2024-25'. For reports; never used as a key."""
    return f"FY{fy}-{str(fy + 1)[2:]}"


def regime_of(sale_date):
    """'new' on or after the cutoff, else 'old'. Section 3(8), the SALE date."""
    return "new" if pd.Timestamp(sale_date) >= CGT_REGIME_CHANGE else "old"


def exemption_for_fy(fy):
    """The LTCG annual exemption for a financial year. Section 3(5)/(6).

    KEYED ON THE FINANCIAL YEAR, NOT THE SALE DATE, and that is the whole reason
    this is a function rather than a branch inside the rate lookup. FY2024-25
    draws Rs 1,25,000 even for a lot sold in May 2024 at the OLD rate; the
    document's worked table shows exactly that.
    """
    return LTCG_EXEMPTION_NEW if fy >= LTCG_EXEMPTION_FY_CUT else LTCG_EXEMPTION_OLD


def closed_lots(path):
    """Every closed lot in a trade log, FIFO per symbol. None when absent.

    Returns a frame with one row per SELL-matched parcel:
        symbol, buy_date, sell_date, qty, buy_price, sell_price,
        held_days, is_long, regime, fy, gain

    READ FROM THE ENGINE'S OWN TRADE LOG, so tax is computed on the trades that
    actually happened rather than on a reconstruction of them. None when the log
    does not exist, so the caller reports the column as unavailable rather than
    silently as zero -- the parked file's behaviour, which was right.

    FIFO IS IMPLEMENTED AND CANNOT CURRENTLY BIND. The engine opens a position
    only when the symbol is absent (test_exposure.py:306) and always exits the
    whole position (test_exposure.py:260), so there is exactly one open lot per
    symbol and FIFO, LIFO and average-cost are identical. The loop is kept
    general because a future partial-exit rule would otherwise be silently
    mismatched, and a wrong basis does not raise -- it just reports.

    GAIN IS THE PRICE DIFFERENCE ONLY -- section 3(C), treatment (ii). Neither
    leg's charges are deducted. See the module docstring on why that is
    conservative.

    THE PRICE IS THE PERSISTED FILL PRICE, which is post-slippage and rounded to
    two decimals. That is the price the trade happened at and the price the cash
    account moved by; our slippage is a price move, not a cost, so there is no
    sense in which a clean price was ever paid.
    """
    from market_data import read_table  # lazy: this module is imported without the repo root on sys.path
    if not Path(path).exists():
        return None
    tr = read_table(path, parse_dates=["date"]).sort_values("date")
    lots, rows = {}, []
    for _, t in tr.iterrows():
        sym, q, px = t["symbol"], int(t["qty"]), float(t["price"])
        if t["action"] == "BUY":
            lots.setdefault(sym, []).append([q, px, t["date"]])
            continue
        need = q
        while need > 0 and lots.get(sym):
            lot = lots[sym][0]
            take = min(need, lot[0])
            held = (t["date"] - lot[2]).days
            rows.append({
                "symbol": sym,
                "buy_date": lot[2], "sell_date": t["date"],
                "qty": take, "buy_price": lot[1], "sell_price": px,
                "held_days": held,
                "is_long": is_long_term(lot[2], t["date"]),
                "regime": regime_of(t["date"]),
                "fy": financial_year(t["date"]),
                "gain": take * (px - lot[1]),
            })
            lot[0] -= take
            need -= take
            if lot[0] == 0:
                lots[sym].pop(0)
    if not rows:
        return pd.DataFrame(columns=[
            "symbol", "buy_date", "sell_date", "qty", "buy_price", "sell_price",
            "held_days", "is_long", "regime", "fy", "gain"])
    return pd.DataFrame(rows)


def max_holding_days(lots):
    """The longest holding period in a lot frame, or None when it is empty.

    EXISTS SO A GATE CAN WATCH THE LTCG CEILING, AND THE CEILING HAS BEEN
    CROSSED. This docstring used to say that every published figure in this
    repository rests on the long-term branch never firing. That is FALSE as of
    the four-universe runs of 2026-09-18, measured 2026-09-19:

        nifty100   SOLARINDS   2022-07-20 -> 2023-10-06   443 days
        nifty50    TATACONSUM  2019-05-30 -> 2020-08-17   445 days
        nifty50    TRENT       2019-07-26 -> 2021-03-05   588 days
        nifty50    TRENT       2022-08-19 -> 2023-09-06   383 days

    Four lots over 365 days. All four routed to a `long_` bucket, all four taxed
    at LTCG_RATE["old"] = 0.10 with the annual exemption applied ahead of them,
    and FY_TAX_STATEMENT carries the resulting long_old amounts -- nifty100
    FY2023-24 Rs 128,379.35, nifty50 FY2020-21 Rs 105,765.31 and FY2023-24
    Rs 71,676.15. The routing was correct throughout; only the prose was wrong.

    midcap150 (max 290) and midcap50 (max 322) are still entirely short-term,
    and that is a property of those two windows, not of the pipeline.

    THE FAILURE MODE THIS FUNCTION WAS WRITTEN AGAINST IS THE ONE THAT HAPPENED:
    the branch began firing and nothing said so, because this function had no
    caller for as long as it existed. It has one now -- check_all.py's
    LTCG-boundary condition. Do not leave it uncalled again; an uncalled guard
    is prose with a def in front of it.
    """
    if lots is None or lots.empty:
        return None
    return int(lots["held_days"].max())


def realized_buckets(lots):
    """{fy: {short_old, short_new, long_old, long_new}} -- section 3(A)'s cross.

    The four buckets are {short,long} x {old,new}: the holding-period test and
    the regime test are independent, so all four can be occupied in one year.
    Every financial year present in `lots` gets an entry, including zeroed ones,
    so a caller iterating years cannot silently skip a loss year.
    """
    out = {}
    if lots is None or lots.empty:
        return out
    for fy, g in lots.groupby("fy"):
        b = dict.fromkeys(BUCKETS, 0.0)
        for _, r in g.iterrows():
            key = ("long_" if r["is_long"] else "short_") + r["regime"]
            b[key] += float(r["gain"])
        out[int(fy)] = b
    return out


def tax_for_fy(fy, b, cf=None):
    """The tax owed for one financial year, and every intermediate.

    `b` holds the year's realised gains in the four buckets. `cf` is the
    CarryForward of the run, assessed in ascending years; None assesses the year
    alone (nothing brought forward, nothing carried out), which is right for a
    single sale. The steps, in the order the Act applies them:

      1. within each head the buckets net: short_old + short_new, long_old + long_new
      2. a net short-term loss is set off against this year's long-term gain
      3. brought-forward short losses against short-term gains, then long-term;
         brought-forward long losses against long-term gains; oldest first
      4. what is left of this year's losses is carried forward
      5. the LTCG exemption, on long-term gains left after set-off
      6. rates by sale date (old/new), split as section 3.4 splits them
      7. 4% cess on the tax
    """
    if cf is None:
        cf = CarryForward()
    cf.start(fy)
    # 1 ---------------------------------------------------------------------
    stcg_net = b["short_old"] + b["short_new"]
    ltcg_net = b["long_old"] + b["long_new"]
    st_left = max(stcg_net, 0.0)
    lt_left = max(ltcg_net, 0.0)
    st_loss = max(-stcg_net, 0.0)
    lt_loss = max(-ltcg_net, 0.0)
    # 2 ---------------------------------------------------------------------
    stcl_vs_ltcg = min(st_loss, lt_left)
    st_loss -= stcl_vs_ltcg
    lt_left -= stcl_vs_ltcg
    # 3 ---------------------------------------------------------------------
    bf_short_vs_st = cf.use("short", st_left)
    st_left -= bf_short_vs_st
    bf_short_vs_lt = cf.use("short", lt_left)
    lt_left -= bf_short_vs_lt
    bf_long_vs_lt = cf.use("long", lt_left)
    lt_left -= bf_long_vs_lt
    # 4 ---------------------------------------------------------------------
    cf.add("short", fy, st_loss)
    cf.add("long", fy, lt_loss)
    # 5, 6 -- STCG: no exemption; the old-rate part is taken first, as before
    stcg_taxable = st_left
    stcg_old_t = min(max(b["short_old"], 0.0), stcg_taxable)
    stcg_new_t = stcg_taxable - stcg_old_t
    stcg_tax = stcg_old_t * STCG_RATE["old"] + stcg_new_t * STCG_RATE["new"]
    # LTCG: the exemption on what set-off left; ltcg_new_t is taken FIRST out of
    # the taxable remainder, which leaves the exemption against the old-rate
    # gains (section 3.4, unchanged).
    exemption = exemption_for_fy(fy)
    exemption_used = min(lt_left, exemption)
    ltcg_taxable = max(lt_left - exemption, 0.0)
    ltcg_new_t = min(ltcg_taxable, max(b["long_new"], 0.0))
    ltcg_old_t = ltcg_taxable - ltcg_new_t
    ltcg_tax = ltcg_old_t * LTCG_RATE["old"] + ltcg_new_t * LTCG_RATE["new"]
    # 7 ---------------------------------------------------------------------
    tax_before_cess = stcg_tax + ltcg_tax
    cess = tax_before_cess * CESS_RATE
    left = cf.balance()
    return {
        "fy": fy, "fy_label": fy_label(fy),
        **{k: b[k] for k in BUCKETS},
        "stcg_net": stcg_net, "ltcg_net": ltcg_net,
        "stcl_set_off_vs_ltcg": stcl_vs_ltcg,
        "bf_short_used": bf_short_vs_st + bf_short_vs_lt, "bf_long_used": bf_long_vs_lt,
        "cf_short_added": st_loss, "cf_long_added": lt_loss,
        "cf_short_balance": left["short"], "cf_long_balance": left["long"],
        "stcg_taxable": stcg_taxable,
        "stcg_old_taxed": stcg_old_t, "stcg_new_taxed": stcg_new_t,
        "stcg_tax": stcg_tax,
        "exemption": exemption, "ltcg_after_set_off": lt_left,
        "exemption_used": exemption_used,
        "ltcg_taxable": ltcg_taxable,
        "ltcg_old_taxed": ltcg_old_t, "ltcg_new_taxed": ltcg_new_t,
        "ltcg_tax": ltcg_tax,
        "tax_before_cess": tax_before_cess, "cess": cess,
        "total_tax": tax_before_cess + cess,
    }


def assess_years(buckets_by_fy, fys=None):
    """{fy: tax_for_fy(...)} for every year, assessed in ascending order with one
    CarryForward. `fys` adds years with no realised gain (they still age losses)."""
    cf = CarryForward()
    years = sorted(set(buckets_by_fy) | set(fys or ()))
    return {fy: tax_for_fy(fy, buckets_by_fy.get(fy, dict.fromkeys(BUCKETS, 0.0)), cf)
            for fy in years}


def assess_dates(fys, trading_days):
    """{fy: assessment date or None} -- section 3(9).

    "Each financial year is assessed EXACTLY ONCE, on the first trading day at
    or after 31 March, and the whole tax is deducted from cash as a SINGLE LUMP
    SUM."

    None means NO TRADING DAY IN THE WINDOW SATISFIES THAT RULE, which is not a
    hypothetical: FY2026-27 is assessed on the first trading day at or after
    31-Mar-2027 and the backtest ends 2026-05-29, so its liability is computed
    and never deducted. Returning None rather than silently dropping the year is
    the point -- a liability that vanishes without being reported flatters the
    result, and the caller is expected to say so out loud.
    """
    days = pd.DatetimeIndex(sorted(pd.DatetimeIndex(trading_days)))
    out = {}
    for fy in sorted(fys):
        due = pd.Timestamp(year=fy + 1, month=3, day=31)
        later = days[days >= due]
        out[int(fy)] = (later[0] if len(later) else None)
    return out


def liability_schedule(lots, trading_days):
    """-> (DataFrame of per-FY tax, {date: rupees due}) for the engine hook.

    The frame is FY_TAX_STATEMENT's content. The dict is what the in-loop
    deduction consumes: one entry per assessed financial year, keyed by the
    trading day the lump sum comes out of cash.

    A YEAR SECTION 3(9) WOULD ASSESS AFTER THE WINDOW IS SETTLED ON ITS LAST
    SESSION (since 2026-09-25, matching Ledger.due_on), so every year is in the
    dict and `assessed_basis` says which rule dated it. Nothing here deducts
    anything or touches an equity curve; results/test_exposure.py moves the cash.
    """
    buckets = realized_buckets(lots)
    rows = list(assess_years(buckets).values())
    when = assess_dates(buckets.keys(), trading_days)
    last = pd.Timestamp(max(pd.DatetimeIndex(trading_days)))
    for r in rows:
        d = when[r["fy"]]
        # THE NOTE IS A COLUMN, NOT A FOOTNOTE ON THE RENDERER, so a reader
        # scanning FY_TAX_STATEMENT sees from the row itself which rule dated it.
        if d is not None:
            r["assessed_on"] = d
            r["assessed"] = True
            r["assessed_basis"] = "section 3(9)"
            r["assessed_note"] = ""
        else:
            due_d = pd.Timestamp(year=r["fy"] + 1, month=3, day=31)
            r["assessed_on"] = last
            r["assessed"] = True
            r["assessed_basis"] = "backtest end"
            r["assessed_note"] = (
                f"SETTLED AT THE BACKTEST END -- section 3(9) would assess "
                f"{r['fy_label']} on the first trading day at or after "
                f"{due_d.date()}, outside the window. Settled on {last.date()}, "
                f"after that day's fills, on gains realised to that date, with the "
                f"same set-off, carry-forward, full annual exemption and cess (decision "
                f"of 2026-09-25; the document is silent on a window ending mid-year).")
    due = {r["assessed_on"]: r["total_tax"]
           for r in rows if r["assessed"] and r["total_tax"] > 0}
    return pd.DataFrame(rows), due


# ---------------------------------------------------------------------------
# THE IN-LOOP LEDGER -- because the liability and the trades are circular
# ---------------------------------------------------------------------------
# TAX CANNOT BE COMPUTED FROM A FINISHED RUN AND THEN DEDUCTED FROM IT. The
# deduction reduces cash; cash sizes every order through `int(... // pr)`; the
# orders are what produce the gains; the gains are the liability. Running
# untaxed, computing the bill from that log and charging it back is not a
# conservative approximation -- it charges a bill the taxed portfolio would never
# have incurred, because after the first deduction it is holding different names
# in different sizes. A second pass does not converge to anything meaningful and
# a fixed-point iteration would be a rule the document does not contain.
#
# SO THE LEDGER ACCRUES AS THE RUN GOES. Every SELL is bucketed the moment it
# happens, from the position the engine is actually holding, and each financial
# year's assessment reads only what had been realised by that date. One pass,
# self-consistent, and it is what section 3(9)'s sentence describes: the bill
# for a year reduces the capital available to trade the following one.
#
# THIS CLASS HOLDS NO CASH AND MOVES NONE. It is told about fills and asked what
# is due; results/test_exposure.py owns the cash and does the subtraction.
class Ledger:
    """Realised-gain accumulator with per-financial-year assessment.

    buy(sym, qty, price, date)     record an opened lot
    sell(sym, qty, price, date)    -> realised gain, and bucket it
    due_on(date, after_fills)      -> rupees to deduct before (or, for a year
                                      assessed inside itself, after) the fills
    """

    def __init__(self, dates):
        self.lots = {}
        self.realized = {}
        self.assessed = set()
        self.rows = []
        # WHEN EACH YEAR FALLS DUE, PRECOMPUTED FROM THE RUN'S OWN CALENDAR.
        # Section 3(9): the first trading day at or after 31 March. A year whose
        # date never arrives is simply absent here and is never assessed -- which
        # is FY2026-27 on this window, and liability_schedule() is what reports
        # that rather than this.
        d = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dates)))
        # THE LAST SESSION, on which every year still unassessed is settled
        # (due_on, after_fills=True). None for an empty calendar.
        self.end = d[-1] if len(d) else None
        self.settled_at_end = set()
        # LOSSES BROUGHT FORWARD, one pool for the run. Years are assessed in
        # ascending order (each on its own due date, the rest at the end), which
        # CarryForward.start enforces.
        self.cf = CarryForward()
        self.assess_on = {}
        for fy in sorted({financial_year(x) for x in d}):
            later = d[d >= pd.Timestamp(year=fy + 1, month=3, day=31)]
            if len(later):
                self.assess_on.setdefault(later[0], []).append(fy)

    def buy(self, sym, qty, price, date):
        self.lots.setdefault(sym, []).append([int(qty), float(price), date])

    def sell(self, sym, qty, price, date):
        """Realise `qty` of `sym` FIFO. Returns the gain; buckets it by FY."""
        need, gain = int(qty), 0.0
        while need > 0 and self.lots.get(sym):
            lot = self.lots[sym][0]
            take = min(need, lot[0])
            held = (date - lot[2]).days
            g = take * (float(price) - lot[1])
            fy = financial_year(date)
            is_long = is_long_term(lot[2], date)
            key = ("long_" if is_long else "short_") + regime_of(date)
            self.realized.setdefault(fy, dict.fromkeys(BUCKETS, 0.0))[key] += g
            self.rows.append({
                "symbol": sym, "buy_date": lot[2], "sell_date": date,
                "qty": take, "buy_price": lot[1], "sell_price": float(price),
                "held_days": held, "is_long": is_long,
                "regime": regime_of(date), "fy": fy, "gain": g})
            gain += g
            lot[0] -= take
            need -= take
            if lot[0] == 0:
                self.lots[sym].pop(0)
        return gain

    def due_on(self, date, after_fills=False):
        """Rupees due on `date`, or 0.0. Each financial year assessed ONCE.

        TWO PHASES, 2026-09-23. The engine calls this before the day's fills
        (after_fills=False) and again after them (after_fills=True). A year whose
        assessment day is still INSIDE that year -- 31 March falling on a trading
        day -- is assessed in the second call, so a sell that day is taxed with
        its own year. Every other year is assessed in the first call, as before.
        The leak described below is therefore closed rather than detected: the
        combination sweep hit it on all eight tax-on cells at cadence 1, where a
        rebalance runs every day, and tax_report's reconciliation refused them.
        No published cadence-20 run has a fill on those days, measured across
        all eight universes, so no published number moves.

        THE SAME-DAY LEAK IS DETECTED, NOT ASSUMED AWAY. Section 3(9) can put a
        year's assessment on the last day of that same year -- FY2019-20 falls
        due 2020-03-31, which is inside FY2019-20 -- and the deduction happens
        before that day's fills. A sell later the same day lands in a year that
        has already been assessed exactly once, so its gain is never taxed.

        It does not happen on the current window: no sell falls on an assessment
        date belonging to its own financial year (checked across both universes,
        2026-09-17; the one sell that does land on an assessment date is
        2024-04-01, which is FY2024-25 being assessed for FY2023-24). It is
        calendar luck, not a property, so `leaked` records it instead of the run
        losing a gain in silence.
        """
        fys = self.assess_on.get(pd.Timestamp(date), [])
        total = 0.0
        for fy in fys:
            if (financial_year(date) == fy) != after_fills:
                continue
            if fy in self.assessed:
                continue
            self.assessed.add(fy)
            b = self.realized.get(fy)
            if b:
                total += tax_for_fy(fy, b, self.cf)["total_tax"]
        # SETTLEMENT AT THE BACKTEST END, 2026-09-25. On the last session, after
        # its fills, every financial year with realised gains that section 3(9)
        # would assess after the window is settled now, on what was realised by
        # this date, with the same tax_for_fy. On this window that is FY2026-27.
        if after_fills and self.end is not None and pd.Timestamp(date) == self.end:
            for fy in sorted(self.realized):
                if fy in self.assessed:
                    continue
                self.assessed.add(fy)
                self.settled_at_end.add(fy)
                total += tax_for_fy(fy, self.realized[fy], self.cf)["total_tax"]
        return total

    def leaked(self):
        """Gains realised into a financial year that was already assessed.

        Empty is the expected answer. A non-empty list means a gain was realised
        AFTER its own year's assessment and escaped tax entirely. A sale ON a
        same-year assessment day is not one: that year is assessed after the
        day's fills (due_on, 2026-09-23), so the sale is in its bill.
        """
        out = []
        for r in self.rows:
            for d, fys in self.assess_on.items():
                if r["fy"] in fys and r["sell_date"] > d:
                    out.append(r)
                    break
        return out


# ======================================================================================
# PARTICIPATION CAP AND PROFILE NOTICES. From profiles.py (moved 2026-11-27).
# ======================================================================================
# profiles.py -- what the execution-realism profile does to a run: the
# participation cap, the cap keywords for backtest_exposure, and the notices a
# non-research run carries. The selection itself is settings.profile_axis
# (research or tradeable).
#
# TWO PROFILES, NOT A BARE PARAMETER
#     research   participation_cap = None   (the default)
#     tradeable  participation_cap = 1.00
#
# WHY A PROFILE AND NOT A NUMBER
#     A single default cannot serve both readers. `research` must reproduce the
#     published history EXACTLY -- it is what every gate and every document compares
#     against, and v34_comparison.csv is byte-identical under it. `tradeable` is the
#     question "what does this return if I can actually transact", and it should be
#     one flag rather than a number somebody has to remember to pass.
#
# WHY THIS IS SEPARATE FROM THE DATA GUARDS
#     The row rule (results/tradability.py) corrects something that is
#     WRONG: a fill at a price that did not trade. There is no version of the
#     strategy that wanted it, so it applies unconditionally.
#
#     The participation cap is different in kind. Nothing in the data is wrong when
#     AIIL fills at 2,131% of its median volume -- the price is real and the date is
#     real. What is wrong is that the backtest was never told it could not transact
#     that size. Capping makes the number more REALISTIC, but it also changes what
#     strategy is being measured, so it is opt-in.
#
# WHY THIS IS NOT A MODULE GLOBAL ON test_exposure
#     settings.cadence records the hazard by file and line: rebal_cadence_sweep.py set
#     test_exposure.REBAL and never restored it, so every later in-process step would
#     have backtested the wrong cadence with nothing to say so. The cap is recorded
#     here and handed to backtest_exposure as an ARGUMENT. A parameter cannot leak
#     into the next step; a global can, and once did.
#
# WHAT THE CAP MEANS
#     A BUY is capped at `participation_cap` x the symbol's prior-20-session MEDIAN
#     volume. Prior, so the cap never uses the day's own volume. Median rather than
#     mean, because a single block trade should not licence a large fill.
#
#     THE REMAINDER STAYS IN CASH. It is not reallocated to the next name -- that
#     would change SELECTION and make the cap a strategy redesign rather than a
#     realism constraint -- and it is not carried to the next session, which would
#     need an order-state concept the engine does not have.
#
#     Measured consequence, and it is the opposite of the obvious guess: capping
#     INCREASES the mean number of names held and REDUCES cash-short skips. On the
#     2026-10-10 data, research against tradeable, tax off, in the four v1 and v3 cells
#     of the eight universes where the cap changes either count: smallcap250 v1 7.84 ->
#     7.86 names and 120 -> 119 skips, smallcap250 v3 7.89 -> 7.89 and 119 -> 118,
#     nifty500 v1 7.76 -> 7.77 and 109 -> 108, nifty500 v3 7.82 -> 7.84 and 109 -> 108.
#     The cap partially relieves the funding defect rather than compounding it.
#
#     THAT DIRECTION HAS TWO SOURCES, NOT ONE. CORRECTED 2026-09-23. This paragraph
#     used to end "...because the buy loop runs in score-descending order and
#     shrinking an early oversized name frees cash for the tail it used to drop",
#     naming one channel as the whole explanation. It predicted the right direction
#     from an incomplete mechanism, which is worse than saying nothing: a correct
#     prediction reads as confirmation and nobody looks again.
#
#     CHANNEL 2 -- THE TAIL. The buy loop runs in score-descending order, so
#     shrinking an early oversized name frees cash for names further down that the
#     loop used to drop. This is the one this paragraph named.
#
#     CHANNEL 3 -- AFFORDABILITY. The shrink does not free money for a LATER name; it
#     brings THIS name inside the budget. A capped order can cost less than the cash
#     on hand when the uncapped order cost more, so an order the research run refused
#     for cash executes under the cap.
#
#         nifty100 v1, 2019-01-30. Both runs intend 3,373 VBL shares against a
#         2,312-share prior-20-session median, 145.9% of it.
#           research:  needs Rs 158,161, has Rs 109,926 -> cash short, no fill.
#           tradeable: capped to 2,312 sh = Rs 108,410  -> BUYS.
#         The research run never holds VBL that day. The capped run does, and that
#         cell finishes AHEAD of its twin: CAGR 25.77 -> 25.88.
#
#     SO THE TRADEABLE PROFILE IS NOT A COST-ONLY TRANSFORM OF THE RESEARCH RUN. It
#     changes which trades happen, in both directions. Measured over the full
#     universe x arm grid on 2026-09-23 from runs of 2026-09-22: of 32 cells, 7
#     diverge from their research twin; 3 of those 7 contain at least one channel-3
#     bind, and 4 of the 16 binds across them are channel 3. One of the 7 finishes
#     ahead. Channel 3 does NOT imply a gain -- two of the three cells carrying it
#     finish behind. Those are counts on one date at the backtest's Rs 10,00,000, not
#     properties of the cap.
#
#     THE REMAINDER RULE (channel 1) IS UNCHANGED BY ANY OF THIS. Nothing is
#     reallocated and nothing is carried forward; channels 2 and 3 are both about
#     cash that was already there.
#

def participation_cap():
    """The cap as a fraction of prior-20-session median volume, or None.

    The profile's own value unless run.py was given --cap (settings.pcap_axis), which
    replaces it for the run. --cap under research is refused before this is read.
    """
    from settings import pcap_axis
    if pcap_axis.selected() is not None and not profile_axis.is_default():
        return pcap_axis.selected()
    return profile_axis.PROFILES[profile_axis.selected()]["participation_cap"]


def cap_kwargs(u, vol20=None):
    """The participation-cap keywords for backtest_exposure on universe `u`.

    {"participation_cap": None} under research; the cap plus vol20 -- the
    prior-20-session median volume from the universe's own farm -- otherwise.
    ALWAYS CARRIES THE CAP, EVEN WHEN None: backtest_exposure refuses to guess
    which profile a caller meant.

    ONE DEFINITION, 2026-09-23. v34_common (twice), engine_v2_final and
    audit_step each built this dict by hand, and bh_lots_after_tax built it
    without vol20, so `--tax on --profile tradeable` died at STEP 17h on every
    universe. The engines and the audit must read the volume from the same place
    by the same call, which is now true by construction.

    THE IMPACT MODEL RIDES HERE TOO (settings.impact_axis, 2026-10-15). It needs the
    same vol20, so every caller that honours the cap honours --impact. The key is
    added only when --impact is non-zero, so a default call is unchanged; under
    research a non-zero k is refused rather than dropped.

    `vol20`, when given, is a series this function returned earlier for the same
    universe; it is reused instead of reading every price file again. Only a
    caller that runs many settings on one universe (results/impact_sweep.py)
    passes it.
    """
    from settings import impact_axis as _imp
    cap = participation_cap()
    if cap is None:
        _imp.check_profile()
        return {"participation_cap": None}
    import settings as _cfg
    import market_data
    from market_data import _load_calendar
    if vol20 is None:
        vol20 = market_data.median_volume(u.prepare_data_dir(), _load_calendar(),
                                  _cfg.BT_START_DATE, _cfg.BT_END_DATE)
    kw = {"participation_cap": cap, "vol20": vol20}
    if not _imp.is_default():
        kw["impact_k"] = _imp.impact_k()
    return kw


def research_only(caller):
    """Declare that `caller` measures the research profile, and REFUSE if the run
    selected another one. Returns the research cap, which is None.

    WHY A DECLARATION AND NOT JUST `participation_cap=None`. Thirteen measurement
    tools passed `participation_cap()` and never passed the `vol20` the cap needs,
    so under `tradeable` they would have measured research and labelled it
    tradeable. They never did, but only because the profile axis cannot reach them
    today: none is in PIPELINE_ORDER, none accepts --profile, none calls
    set_selection, and no load-bearing module imports them. Verified 2026-09-15,
    all four routes.

    THOSE ARE PROPERTIES OF TODAY'S TREE, AND THE TREE IS BEING REWRITTEN. Safe by
    construction lasts until someone adds a flag; safe by declaration lasts. A tool
    that says `research_only(__name__)` and is later handed `--profile tradeable`
    STOPS, and the message names it. A tool that merely passes None goes on quietly
    measuring research under a tradeable label -- which is the whole defect, moved
    one file along.

    Use this ONLY where research is the intended measurement. A caller that should
    honour the selected profile passes participation_cap() and the vol20 that goes
    with it; see backtest_exposure's refusal.
    """
    if profile_axis.selected() != profile_axis.DEFAULT:
        raise SystemExit(
            f"{caller} is declared research-only, but this run selected "
            f"profile '{profile_axis.selected()}'.\n"
            f"  It passes no vol20, so the participation cap could not be applied "
            f"even though the profile asks for it, and the result would be a "
            f"research measurement wearing a '{profile_axis.selected()}' label.\n"
            f"  Either run it without --profile, or give it the vol20 that "
            f"backtest_exposure needs and drop this declaration.")
    return profile_axis.PROFILES[profile_axis.DEFAULT]["participation_cap"]


# ---------------------------------------------------------------------------
# A NON-RESEARCH PROFILE IS UNGATED, AND MUST SAY SO WHEREVER IT PUBLISHES
# ---------------------------------------------------------------------------
# `--profile tradeable` could not complete until 2026-09-16; the input guard
# blocked STEP 16. It completes now. THAT IS NOT THE SAME AS BEING VERIFIED, and
# the distance between the two is exactly the kind a reader closes by accident:
# a run that finishes, writes every artefact and exits 0 looks like a run that was
# checked.
#
# IT HAS NEVER BEEN CHECKED. gate_compare.STANDING_GATE's two tradeable cells are
# [PARTIAL] and stop at STEP 10d/12b/15b; STEP 16 and STEP 17 had never executed
# under this profile before 2026-09-16, and no cell compares what they produce
# against anything. Until a gate cell exists, every tradeable number is a number
# nothing has replayed.
#
# SO THE STATEMENT TRAVELS WITH THE NUMBERS, not just with the run: run.py banners
# it at the start and end of a non-default-profile run, and v34_common writes it
# into v34_params{SFX}.json. One definition here so the two cannot drift, and so
# deleting the caveat is one edit that shows up in a diff rather than three.
UNGATED_NOTICE = (
    "UNGATED: no gate cell covers this profile. It completes end to end, which is "
    "not the same as being verified -- STEP 16 and STEP 17 first ran under it on "
    "2026-09-16 and nothing replays what they produce. Do not publish these "
    "numbers as checked."
)

# A TRADEABLE FILENAME DOES NOT MEAN THE CAP CHANGED ANYTHING. Measured 2026-09-20
# at commit 7dd37d6, and the wording is deliberate: this is what the cap did on
# those runs, not a property of the cap or of the universe.
#
# On midcap150 the cap fired on NO fill in either arm. daily_skipped_midcap150_v1_
# tradeable.csv and daily_skipped_midcap150_tradeable.csv carry zero rows with
# reason "participation cap" (n=850 and n=1006 fills). The highest participation
# any fill reached was 0.709 of its prior-20-session median on v1 and 0.345 on v2,
# against a cap of 1.00. All eight of {trades, skipped, holdings, summary} x {v1,
# v2} are BYTE-IDENTICAL to their unsuffixed research twins.
#
# nifty100 was already recorded as inert in KNOWN_ISSUES.md. So as of this commit
# neither published universe has a run in which the cap bound.
#
# THIS IS A DATED MEASUREMENT AND IT WILL ROT. It depends on the capital, the
# universe and the data, all of which move. Re-measure by counting "participation
# cap" rows in the run's own daily_skipped artefact; do not carry this sentence
# forward on trust.
# RE-MEASURED 2026-09-22, WITH THE SELL SIDE NOW CAPPED TOO. The notice below was
# written when only BUYs were capped. Both sides are capped as of 2026-09-22, and
# at cap=1.00 the cap still binds on NO fill of either universe on either side --
# nifty100 954 fills, midcap150 973, zero rows with reason "participation cap"
# (re-measured 2026-10-10 on that day's data delivery; the cap 1.00, k none row of
# each v2 sweep CSV).
# So the inertness above survived the sell side being added, and the
# research/tradeable byte-identity it describes is a property of THE CAP VALUE,
# not of the cap.
#
# AT cap=0.10 THE IDENTITY ENDS, BY DESIGN AND MEASURED (re-measured 2026-10-10 on
# that day's data delivery; the cap 0.10, k none row of each v2 sweep CSV):
#
#     nifty100    2 BUY + 1 SELL binds of 955 fills    CAGR 21.82 -> 21.65  (-0.17)
#     midcap150  10 BUY + 5 SELL binds of 978 fills    CAGR 33.74 -> 33.10  (-0.64)
#
# A tradeable artefact that differs from its research twin is then the cap doing
# its job, not a regression. Anything reading the notice below as "tradeable always
# equals research" is reading a statement about 1.00.
#
# The full grid, with per-cell bind counts and the cap/slippage split, is
# diagnostics/impact_sweep_{universe}_{arm}.csv from results/impact_sweep.py.
# CAP_INERT_NOTICE WAS A STORED CLAIM AND IS GONE. SUPERSEDED 2026-09-22.
#
# IT READ, VERBATIM:
#
#     "CAP DID NOT BIND: measured 2026-09-20 at commit 7dd37d6, the participation
#     cap fired on no fill of midcap150 v1 (n=850) or v2 (n=1006) -- zero rows with
#     reason 'participation cap' in the run's daily_skipped artefact, highest
#     participation 0.709 and 0.345 against a cap of 1.00 -- and every midcap150
#     tradeable artefact is byte-identical to its research twin. nifty100 is
#     recorded inert too. These are not capped results; they are research results
#     under a tradeable filename. Count the 'participation cap' rows in THIS run's
#     daily_skipped artefact before repeating that."
#
# WHY IT WAS REMOVED RATHER THAN EDITED. On 2026-09-22 six tradeable cells were
# run in which the cap DID bind -- nifty500 v1 and v3, midcap100 v1 and v3,
# smallcap250 v1 and v3 -- and this banner printed "CAP DID NOT BIND" over every
# one of them. Its last sentence told the reader to count the rows themselves,
# which is honest and is not what a reader takes from a headline in exclamation
# marks.
#
# THIS IS THE STALE-ASSERTION CLASS, THIRD INSTANCE. gate_compare's register
# described its cells as cap-binding after they stopped being so, and this notice
# was itself written to correct that. A measurement about two universes, stored as
# a sentence, printed over runs of universes it never measured, is the same defect
# one turn later. The cure is not a better sentence: a banner that can be wrong
# about the run it heads must not be a stored claim at all.
#
# WHAT REPLACED IT: cap_report() below, which reads THIS run's own daily_skipped
# artefacts and reports what they contain. The one thing still stored is
# UNGATED_NOTICE, which is a property of the tree -- no gate cell covers this
# profile -- and not a measurement of any run.


def cap_report(cells):
    """What the participation cap actually did, read from this run's artefacts.

    `cells` is an iterable of (universe_tag, arm_name). Returns a list of lines.

    NOTHING HERE IS STORED. Every number is counted out of the
    daily_skipped_<artefact_tag>.csv this run just wrote. A cell whose
    artefact is absent is reported absent rather than assumed inert -- that is the
    distinction the notice this replaces could not make.
    """
    import csv
    from pathlib import Path
    from settings import REGISTRY

    if profile_axis.is_default():
        return []
    out, total, unread = [], 0, 0
    # THE FILE IS NAMED BY THE WRITER'S RULE, audit_step.artefact_tag, since
    # 2026-09-26. It was composed here from the profile alone, so a --tax on
    # (or non-default cadence) run counted the tax-off, default-cadence file of
    # an earlier run: on 2026-09-26 the tax-on tradeable banner reported
    # smallcap250 v1 5 capped fills, read from a 2026-09-22 file, where the
    # run's own file holds 4.
    import sys as _sys
    _res = str(Path(__file__).resolve().parent / "results")
    if _res not in _sys.path:
        _sys.path.insert(0, _res)
    import audit_step
    for tag, arm in cells:
        f = (Path(REGISTRY[tag].metrics_dir)
             / f"daily_skipped_{audit_step.artefact_tag(REGISTRY[tag], arm)}.csv")
        if not f.exists():
            out.append(f"    {tag} {arm}: daily_skipped artefact not written "
                       f"({f.name}) -- NOT MEASURED, not inert")
            unread += 1
            continue
        n = sum(1 for r in csv.DictReader(f.open(newline=""))
                if r["reason"].strip().lower() == "participation cap")
        total += n
        out.append(f"    {tag} {arm}: {n} fill(s) capped"
                   f"{'' if n else '  -- cap inert on this cell, this run'}")
    head = (f" PARTICIPATION CAP, COUNTED FROM THIS RUN'S OWN daily_skipped: "
            f"{total} capped fill(s) across {len(out) - unread} cell(s)"
            + (f", {unread} NOT MEASURED" if unread else ""))
    return [head] + out


def gate_status():
    """The gate caveat for this run's profile, or None when it is gated.

    `research` is the profile every gate cell uses and every document compares
    against, so it returns None and nothing is added to a research artefact -- the
    byte-identical gate depends on that.
    """
    return None if profile_axis.is_default() else (
        f"{UNGATED_NOTICE} THE CAP'S EFFECT ON THIS RUN IS NOT ASSERTED HERE: it "
        f"is counted from this run's own daily_skipped artefacts and printed in "
        f"the closing banner. No stored sentence in this file says whether the cap "
        f"bound, because one used to and it was wrong about six runs on "
        f"2026-09-22.")


# ======================================================================================
# CAPACITY. From capacity.py (moved 2026-11-27).
# ======================================================================================
# capacity.py -- can the universe absorb the orders a run sent? One definition.
#
# Measured after a run from its own artefacts and the universe's raw price files; it
# changes no results file. run.py prints it into run.log and RUN.txt, and
# dashboard/export_dashboard_data.py puts it in each run's "capacity" block.
#
#     order % ADV   each buy fill's value (qty x fill price) as a percent of the
#                   stock's average traded value (close x volume) over the 20
#                   sessions before the fill, from the raw price files, counting
#                   NSE rows only (exchange == NSE) and averaging over the NSE rows
#                   inside those 20 sessions
#     not measurable  a buy fill with no NSE row in its 20 sessions; never estimated,
#                   counted and shown as a number and a share of the buy fills
#     unfilled cap  the buy value the participation cap left unfilled, as a percent of
#                   the buy value wanted: for each "participation cap" BUY row of
#                   daily_skipped, (wanted - capped) shares at that day's close, over
#                   that plus every buy fill's value
#
# WHY NSE ROWS ONLY. The supplier's price files mix NSE and BSE rows day by day, and a
# BSE row's volume is BSE's alone, a small fraction of NSE's for most names
# (KNOWN_ISSUES.md, "The price files mix NSE and BSE rows"). The engine, the
# participation cap and the model features still read every row; only this measure
# leaves the BSE rows out.
#
# A WARNING is given when any threshold below is passed. They say when the run's
# fills are large next to what the stock trades, which no profile prices in full: the
# research profile has no cap and no impact, and the tradeable profile's cap allows a
# whole day's median volume at impact k 0.

P95_PCT_ADV = 10.0         # 95th-percentile buy fill, percent of 20-day average traded value
MAX_PCT_ADV = 25.0         # any single buy fill
UNFILLED_CAP_PCT = 5.0     # buy value the participation cap left unfilled


def _capacity_raw(raw_dir, sym, cache):
    """(close, average traded value over the 20 sessions before each date) for one
    symbol, as Series indexed by date; None when the file is absent. The traded
    value counts NSE rows only and is averaged over the NSE rows among those 20
    sessions; it is missing when there is none. A file with no exchange column has
    no NSE row. The close is every row's."""
    key = (str(raw_dir), sym)
    if key not in cache:
        import market_data
        import settings
        f = Path(raw_dir) / f"{sym}.csv"
        if not f.exists():
            cache[key] = None
        else:
            d = market_data.read_price_csv(f).set_index("date").sort_index()
            nse = (d["exchange"] == "NSE") if "exchange" in d.columns else False
            tv = (d["close"] * d["volume"]).where(nse)
            cache[key] = (d["close"], tv.rolling(20, min_periods=1).mean().shift(1))
    return cache[key]


def _capacity_pct(values, q):
    """The q-quantile (0..1) of a sorted list, by linear interpolation; None if empty."""
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def capacity_measure(costs, skipped, raw_dir, cache=None):
    """The capacity figures of one run. `costs` is its COSTS_<tag>.csv and `skipped`
    its daily_skipped_<tag>.csv, as DataFrames with dates parsed; `raw_dir` is the
    universe's raw price directory. `cache` may be shared across runs of one call."""
    import pandas as pd
    cache = {} if cache is None else cache
    buys = costs[costs["side"] == "BUY"]
    pct, filled = [], 0.0
    for r in buys.itertuples(index=False):
        v = float(r.qty) * float(r.fill_price)
        filled += v
        s = _capacity_raw(raw_dir, r.symbol, cache)
        adv = s[1].get(pd.Timestamp(r.date), float("nan")) if s is not None else float("nan")
        if adv == adv and adv > 0:
            pct.append(v / adv * 100)
    unfilled = 0.0
    if skipped is not None and len(skipped):
        rows = skipped[(skipped["reason"] == "participation cap") & (skipped["side"] == "BUY")]
        for r in rows.itertuples(index=False):
            m = re.search(r"wanted ([\d,]+) sh, capped to ([\d,]+)", str(r.detail))
            s = _capacity_raw(raw_dir, r.symbol, cache)
            if m is None or s is None:
                continue
            w, q = (float(x.replace(",", "")) for x in m.groups())
            close = s[0].asof(pd.Timestamp(r.date))
            if close == close:
                unfilled += (w - q) * float(close)
    pct.sort()
    n_out = len(buys) - len(pct)
    out = {"buy_fills": len(buys), "measured_fills": len(pct),
           "not_measurable_fills": n_out,
           "not_measurable_pct": n_out / len(buys) * 100 if len(buys) else 0.0,
           "median_pct_adv": _capacity_pct(pct, 0.5), "p95_pct_adv": _capacity_pct(pct, 0.95),
           "max_pct_adv": pct[-1] if pct else None,
           "unfilled_cap_pct": unfilled / (filled + unfilled) * 100 if filled + unfilled else 0.0}
    out["warning"] = capacity_warning(out)
    return out


def capacity_warning(m):
    """The reasons a run passes a threshold, as one sentence, or None."""
    why = []
    if m["p95_pct_adv"] is not None and m["p95_pct_adv"] > P95_PCT_ADV:
        why.append(f"95th-percentile buy fill {m['p95_pct_adv']:.1f}% of 20-day average traded "
                   f"value (limit {P95_PCT_ADV:g}%)")
    if m["max_pct_adv"] is not None and m["max_pct_adv"] > MAX_PCT_ADV:
        why.append(f"largest buy fill {m['max_pct_adv']:.1f}% (limit {MAX_PCT_ADV:g}%)")
    if m["unfilled_cap_pct"] > UNFILLED_CAP_PCT:
        why.append(f"participation cap left {m['unfilled_cap_pct']:.1f}% of buy value unfilled "
                   f"(limit {UNFILLED_CAP_PCT:g}%)")
    return "; ".join(why) if why else None


def capacity_lines(name, m):
    """The run.log and RUN.txt lines for one universe and arm."""
    f = lambda x: "n/a" if x is None else f"{x:.2f}%"
    out = [f"capacity  : {name}: {m['buy_fills']:,} buy fills, of 20-day average traded value "
           f"(NSE rows only) median {f(m['median_pct_adv'])}, 95th percentile "
           f"{f(m['p95_pct_adv'])}, largest {f(m['max_pct_adv'])}; "
           f"{m['not_measurable_fills']:,} not measurable ({m['not_measurable_pct']:.1f}%, no NSE "
           f"row in their 20 sessions); cap left {m['unfilled_cap_pct']:.2f}% of buy value unfilled"]
    if m["warning"]:
        out.append(f"CAPACITY WARNING: {name}: {m['warning']}. The universe may not absorb orders "
                   f"of this size; the return is not reliable at this capital.")
    return out


if __name__ == "__main__":
    _selftest()

    print("=" * 84)
    print(f"SPEC_LOCK {SPEC_LOCK['version']} | rates effective {SPEC_LOCK['rates_effective']} "
          f"| verified {SPEC_LOCK['verified_on']}")
    print("=" * 84, "\n")

    demo = compute_roundtrip(Broker.ZERODHA, Segment.EQUITY, Product.DELIVERY,
                             2800, 2850, 10, Exchange.NSE)
    print(demo["buy"], "\n")
    print(demo["sell"], "\n")
    print(f"  Round-trip charges : Rs {demo['total_charges']:,.2f}")
    print(f"  Net P&L after costs: Rs {demo['net_pnl']:,.2f}")
