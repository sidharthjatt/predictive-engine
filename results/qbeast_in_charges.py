"""
qbeast_in_charges.py
====================================================================================
QBEAST-AI.N | Indian broker transaction-charges engine (Dhan / Zerodha Kite / Upstox)
Segments : EQUITY (delivery, intraday, futures, options) | COMMODITY (futures, options)
           + CURRENCY (futures, options) bonus for Zerodha/Upstox
Framework: framework-agnostic core + thin NautilusTrader `FeeModel` adapter

------------------------------------------------------------------------------------
RATE PROVENANCE  (SPEC_LOCK below — version-lock before consuming downstream)
------------------------------------------------------------------------------------
All *regulatory* legs (STT/CTT, exchange transaction charges, SEBI turnover fee,
stamp duty, GST) are set by the exchange / government and are therefore IDENTICAL
across all three brokers. Only BROKERAGE and DP (depository) charges differ.

Rates verified June 2026 against the brokers' own published charge pages:
  - Zerodha : https://zerodha.com/charges/        (primary source for exchange legs)
  - Dhan    : https://dhan.co/pricing/
  - Upstox  : https://upstox.com/brokerage-charges/

>>> POLICY-SENSITIVE CALLOUT (treat as a DECISION-V1-NNN trigger on any change) <<<
    Union Budget 2026-27 raised F&O STT effective 01-Apr-2026:
        Equity Futures STT  : 0.0125% -> 0.02% (Oct'24) -> 0.05%  (Apr'26)  [SELL]
        Equity Options STT  : 0.0625% -> 0.10% (Oct'24) -> 0.15%  (Apr'26)  [SELL, on premium]
    These two numbers are the most likely to move at the next budget. Re-pin the
    SPEC_LOCK hash and re-run the self-test (zero skips / zero xfails) when they do.

NOTE on BSE equity transaction charges: BSE rates are scrip-GROUP dependent
(A/B vs X/Z etc.). The 0.00375% used here is the standard A/B-group flat rate.
Verify the group for illiquid scrips before trusting BSE equity cost figures.
====================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Dict, Set, Tuple

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
