"""
nt_run.py -- assemble and run the Nautilus backtest of the Predictive Engine.

Usage:
    python3 nautilus/nt_run.py                 # short smoke window
    python3 nautilus/nt_run.py --full          # the full 2019-2026 backtest
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.objects import Money

import nt_data
from nt_data import VENUE, load_universe

# The project's own Zerodha charge calculator already ships a Nautilus FeeModel.
sys.path.insert(0, str(ROOT / "results"))
from qbeast_in_charges import (Broker, Exchange, Product, QbeastIndianFeeModel, Segment)
from nt_strategy import PredictiveEngineStrategy
from universes.registry import REGISTRY
import paths

# The same panel the reference engine uses. Feeding raw CSVs instead produced a
# different union date index and therefore different momentum windows.
#
# One entry per universe: price panel, score parquet, metrics folder holding the
# reference engine's audit CSVs, and the last backtest year. Adding the MidCap150
# universe is a registry entry, not a new code path -- the strategy, the venue and
# the verification are shared, so whatever is proven on one is proven the same way
# on the others.
# PATHS COME FROM universes/registry.py -- the single definition, shared with the
# research side. This registry was the most complete of the nineteen: it is the
# only one that knew all FOUR universes, and its per-universe backtest END DATE
# lived nowhere else in the repository. That end date is now u.nautilus_end, so
# the port and the research scripts read one definition.
#
# WHY THE END DATES DIFFER, PRESERVED EXACTLY:
#   58  2026-06-08  frozen -- retired universe, its published numbers must not move
#   74  2025-12-23  frozen -- likewise
#   mid/n100        config.BT_END_DATE; the constituents stop before the index does,
#                   so the panel and therefore the backtest stop there too.
UNIVERSES = {
    u.tag: {"cache": u.score_cache,
            "scores": u.nautilus_scores,
            "metrics": u.metrics_dir,
            "tag": u.tag,
            "end": u.nautilus_end}
    for u in REGISTRY.values()
}
PRICE_CACHE = UNIVERSES["58"]["cache"]
START_CAPITAL = 1_000_000
WARMUP_DAYS = 200          # calendar days of history before trading begins
# No latency. The strategy now plans at the close and sends at the next open, so
# nothing depends on delaying a resting order.
LATENCY_NS = 0
SLIPPAGE = 0.0015              # matches SLIPPAGE in results/test_exposure.py

# Real Zerodha delivery-equity charges: brokerage, STT, stamp duty, exchange,
# SEBI turnover fee and GST. Same calculator the reference engine uses, so the
# two systems are charged identically rather than approximately.
# include_dp defaults to False in the per-fill path, because the DP charge is
# levied per scrip per DAY and charging it on every fill could double count. Here
# each scrip trades at most once per rebalance, so per-fill equals per-scrip-per-day
# and it must be on -- otherwise every SELL is undercharged by about Rs 15.34
# against the reference engine, which calls compute_leg_charges with DP included.
FEE_MODEL = QbeastIndianFeeModel(
    broker=Broker.ZERODHA, segment=Segment.EQUITY,
    product=Product.DELIVERY, exchange=Exchange.NSE,
    include_dp=True,
)


def run(trading_start, trading_end, symbols=None, quiet=True, universe="58"):
    warm_start = (pd.Timestamp(trading_start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    print(f"data from {warm_start} (warm-up) | trading {trading_start} to {trading_end}")

    U = UNIVERSES[universe]
    instruments, events = load_universe(U["cache"], warm_start, trading_end,
                                        symbols=symbols, slippage=SLIPPAGE)
    print(f"  instruments {len(instruments)} | events {len(events):,}")

    scores = pd.read_parquet(Path(__file__).resolve().parent / "data" / U["scores"])
    if symbols is not None:
        scores = scores[scores["symbol"].isin(set(symbols))]
    scores = scores[(scores["date"] >= trading_start) & (scores["date"] <= trading_end)]
    print(f"  score rows  {len(scores):,} over {scores['date'].nunique()} days")

    eng = BacktestEngine(config=BacktestEngineConfig(
        trader_id="PREDENG-001",
        logging=LoggingConfig(bypass_logging=quiet)))
    eng.add_venue(VENUE, OmsType.NETTING, AccountType.CASH,
                  starting_balances=[Money(START_CAPITAL, INR)],
                  base_currency=INR,
                  latency_model=LatencyModel(base_latency_nanos=LATENCY_NS),
                  # Orders execute against the 09:15 QUOTE and nothing else. With the
                  # default bar_execution=True an order that found no quote to match
                  # rested until the 15:30 bar and filled at that day's CLOSE: on
                  # 2021-03-05 the LTF sell was sent at 09:16 and filled at 15:30.
                  bar_execution=False,
                  # A GENUINE L2 BOOK ONLY WHEN THE DEPTH MODEL ASKS FOR ONE.
                  #   In "unlimited" mode the venue keeps its default L1 book and
                  #   the run is byte-for-byte what it was, which is what lets
                  #   nt_verify keep reconciling. In "volume" mode nt_data emits
                  #   OrderBookDeltas and the venue needs L2_MBP to hold them, so
                  #   a large order walks the levels natively instead of filling
                  #   the whole size at top of book.
                  book_type=(BookType.L2_MBP
                             if nt_data.DEPTH_MODE == "volume" else BookType.L1_MBP),
                  fee_model=FEE_MODEL)
    for inst in instruments:
        eng.add_instrument(inst)
    eng.add_data(events)

    strat = PredictiveEngineStrategy()
    strat.configure(scores, instruments, trading_start)
    eng.add_strategy(strat)

    eng.run()

    # Nautilus's own reports -- these carry the real order status (FILLED, DENIED,
    # CANCELED) rather than anything reconstructed by hand.
    # ONE DIRECTORY PER UNIVERSE. This used to be a single shared `reports/`, so a
    # verification loop over 58, 74 and mid left only the LAST universe on disk and
    # silently overwrote the other two -- the files looked current while describing
    # a run nobody asked about. The universe is part of the path now, so all three
    # persist side by side and a directory cannot be mistaken for another's output.
    out = Path(__file__).resolve().parent / "reports" / universe
    out.mkdir(parents=True, exist_ok=True)
    # orders.csv IS NOT AN ORDERS REPORT. It is written by
    # generate_order_fills_report(), which emits one row per order THAT PRODUCED A
    # FILL -- so it necessarily has the same row count as fills.csv, and orders
    # that were DENIED or CANCELED never appear in it. The name is kept because
    # downstream scripts read it. generate_orders_report(), which would list every
    # order regardless of outcome, is NOT called anywhere in this project.
    orders_rep = eng.trader.generate_order_fills_report()
    fills_rep = eng.trader.generate_fills_report()
    pos_rep = eng.trader.generate_positions_report()
    orders_rep.to_csv(out / "orders.csv")
    fills_rep.to_csv(out / "fills.csv")
    pos_rep.to_csv(out / "positions.csv")
    print(f"\n  reports -> nautilus/reports/{universe}/  [{U['tag']} universe]  "
          f"(orders {len(orders_rep)}, fills {len(fills_rep)}, positions {len(pos_rep)})")

    acct = eng.cache.account_for_venue(VENUE)
    cash = float(acct.balance_free(INR).as_double())
    pos_val = 0.0
    open_pos = 0
    for pos in eng.cache.positions_open():
        sy = pos.instrument_id.symbol.value
        if sy in strat.last_close:
            pos_val += float(pos.quantity) * strat.last_close[sy]
            open_pos += 1
    equity = cash + pos_val
    filled = [o for o in eng.cache.orders() if o.status_string() == "FILLED"]
    print(f"\n  rebalances       : {strat.rebalances}")
    print(f"  orders submitted : {strat.orders_submitted}")
    print(f"  orders filled    : {len(filled)}")
    print(f"  open positions   : {open_pos}")
    print(f"  cash             : Rs {cash:,.2f}")
    print(f"  positions value  : Rs {pos_val:,.2f}")
    print(f"  EQUITY           : Rs {equity:,.2f}   (from Rs {START_CAPITAL:,})")
    if strat.decisions:
        d = pd.DataFrame(strat.decisions)
        print(f"\n  first 3 rebalance decisions:")
        print(d.head(3).to_string(index=False))
    eng.dispose()
    return strat


if __name__ == "__main__":
    uni = "58"
    for u in UNIVERSES:
        if f"--universe={u}" in sys.argv:
            uni = u
    if "--full" in sys.argv:
        run("2019-01-01", UNIVERSES[uni]["end"], universe=uni)
    else:
        print(f"SMOKE TEST: full {uni} universe, 2019 only\n")
        run("2019-01-01", "2019-12-31", universe=uni)
