"""
nt_trace_one_fill.py -- trace ONE order end to end to find where the fill price
comes from.

WHY THIS EXISTS
    The port has correct timing (decision at 15:31 on day t, fill at 09:15 on day
    t+1) and a correct rebalance schedule (93, matching the reference engine), but
    fill PRICES do not match. A buy that should fill at open*1.0015 is landing
    somewhere else entirely, scattered up to 5% away.

    Four hypotheses were tried and none held. So this script stops guessing and
    prints the actual objects: the quote that was generated, every data event the
    instrument received that day, and the fill event itself.

WHAT TO READ IN THE OUTPUT
    Section 1 -- the quote this project generated for that day.
    Section 2 -- every event the engine received for that instrument that day.
    Section 3 -- the fill: its price, and what it should have been.
    Section 4 -- the verdict.

Run: python3 nautilus/nt_trace_one_fill.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import nt_run
from nt_data import VENUE, load_universe
from nt_strategy import PredictiveEngineStrategy

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money

TRADE_START = "2019-01-01"
TRADE_END = "2019-01-10"          # only need the first rebalance and its fill
FILL_DAY = "2019-01-02"


def main():
    warm = (pd.Timestamp(TRADE_START) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    instruments, events = load_universe(config.RAW_DATA_DIR / "nifty50",
                                        warm, TRADE_END, slippage=nt_run.SLIPPAGE)
    scores = pd.read_parquet(Path(__file__).resolve().parent / "data" / "scores_58.parquet")
    scores = scores[(scores["date"] >= TRADE_START) & (scores["date"] <= TRADE_END)]

    eng = BacktestEngine(config=BacktestEngineConfig(
        logging=LoggingConfig(bypass_logging=True)))
    eng.add_venue(VENUE, OmsType.NETTING, AccountType.CASH,
                  starting_balances=[Money(1_000_000, INR)], base_currency=INR,
                  latency_model=LatencyModel(base_latency_nanos=nt_run.LATENCY_NS),
                  fee_model=nt_run.FEE_MODEL, bar_execution=False)
    for i in instruments:
        eng.add_instrument(i)
    eng.add_data(events)
    strat = PredictiveEngineStrategy()
    strat.configure(scores, instruments, TRADE_START)
    eng.add_strategy(strat)
    eng.run()

    filled = [o for o in eng.cache.orders() if o.status_string() == "FILLED"]
    if not filled:
        print("No filled orders. Nothing to trace.")
        return
    order = filled[0]
    sym = order.instrument_id.symbol.value
    print("=" * 78)
    print(f"TRACING: {sym}  {order.side.name}  qty {order.quantity}")
    print("=" * 78)

    # ---- 1. the raw data and the quote we built from it ----
    csv = config.RAW_DATA_DIR / "nifty50" / f"{sym}.csv"
    raw = config.read_price_csv(csv)
    row = raw[raw["date"] == pd.Timestamp(FILL_DAY)]
    print(f"\n[1] RAW CSV for {sym} on {FILL_DAY}")
    if row.empty:
        print("    no row on that date")
    else:
        r = row.iloc[0]
        print(f"    open={r['open']}  high={r['high']}  low={r['low']}  close={r['close']}")
        print(f"    expected ask (open * 1.0015) = {r['open'] * 1.0015:.4f}")
        print(f"    expected bid (open * 0.9985) = {r['open'] * 0.9985:.4f}")

    # ---- 2. every event this instrument received that day ----
    day = pd.Timestamp(FILL_DAY)
    print(f"\n[2] EVENTS the engine received for {sym} on {FILL_DAY}")
    n = 0
    for e in events:
        iid = (e.instrument_id if isinstance(e, QuoteTick)
               else e.bar_type.instrument_id if isinstance(e, Bar) else None)
        if iid is None or iid.symbol.value != sym:
            continue
        ts = pd.Timestamp(e.ts_init, tz="UTC")
        if ts.normalize().tz_localize(None) != day:
            continue
        n += 1
        if isinstance(e, QuoteTick):
            print(f"    {ts}  QUOTE  bid={e.bid_price} ask={e.ask_price} "
                  f"bid_size={e.bid_size} ask_size={e.ask_size}")
        else:
            print(f"    {ts}  BAR    O={e.open} H={e.high} L={e.low} C={e.close}")
    if n == 0:
        print("    NONE -- the instrument received no data that day")

    # ---- 3. the fill ----
    print(f"\n[3] THE FILL")
    print(f"    submitted at : {pd.Timestamp(order.ts_init, tz='UTC')}")
    print(f"    filled at    : {pd.Timestamp(order.ts_last, tz='UTC')}")
    print(f"    avg fill px  : {order.avg_px}")
    for ev in order.events:
        if type(ev).__name__ == "OrderFilled":
            print(f"    OrderFilled  : px={ev.last_px} qty={ev.last_qty} "
                  f"liquidity={ev.liquidity_side.name} commission={ev.commission}")

    # ---- 4. verdict ----
    print(f"\n[4] VERDICT")
    if row.empty:
        print("    cannot judge: no raw row")
        return
    op = float(row.iloc[0]["open"])
    exp = op * (1.0015 if order.side.name == "BUY" else 0.9985)
    got = float(order.avg_px)
    print(f"    expected {exp:.4f}   got {got:.4f}   deviation {(got/exp-1)*100:+.3f}%")
    if abs(got / exp - 1) < 0.001:
        print("    -> fills are landing on the generated quote. Price model is correct.")
    else:
        print("    -> the fill did NOT come from the generated quote.")
        print("       Compare section [2]: if a BAR appears, execution is still using")
        print("       bar data. If no QUOTE appears, the quote was never delivered.")
    eng.dispose()


if __name__ == "__main__":
    main()
