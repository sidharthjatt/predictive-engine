"""
verify_next_open_execution.py -- PROOF that Nautilus reproduces the project's execution rule.

THE RULE (from the existing engine, and from the leakage checklist):
    signal at the CLOSE of day t  ->  order fills at the OPEN of day t+1
    Same-day close execution is a look-ahead and must never happen.

WHAT WAS MEASURED (three configurations, day 4 has OPEN=150 and CLOSE=152):

    1. Bars only, no latency          -> filled at 104.00  = the CLOSE of day 3
                                         SAME-DAY EXECUTION. This is look-ahead.
    2. Bars + latency, no open tick   -> filled at 152.00  = the CLOSE of day 4
                                         Right day, wrong price.
    3. Bars + latency + open tick     -> filled at 150.00  = the OPEN of day 4
                                         CORRECT.

WHY BOTH PIECES ARE REQUIRED:
    - Without a latency model, a market order is immediately marketable and fills
      against the book as it stands at submission, i.e. the current bar's close.
    - Without an explicit open-price tick, the next price the exchange sees is the
      following bar, which resolves to its close.
    Supplying the open as its own data point makes the execution price explicit
    rather than an artefact of how bars are decomposed internally.

CONCLUSION: feed each trading day as TWO events --
    09:15  TradeTick  at the day's OPEN   (this is what orders execute against)
    15:30  Bar        with the day's OHLC (this is what signals are computed from)
and attach a LatencyModel so orders cannot fill inside the bar that created them.

Run: python3 verify_next_open_execution.py
"""
import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, AggressorSide
from nautilus_trader.model.identifiers import Venue, TradeId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.backtest.models import LatencyModel

VENUE = Venue("SIM"); inst = TestInstrumentProvider.equity(symbol="AAA", venue="SIM")
BT = BarType.from_str(f"{inst.id}-1-DAY-LAST-EXTERNAL")

class T(Strategy):
    def on_start(self):
        self.subscribe_bars(BT); self.n = 0
    def on_bar(self, bar):
        self.n += 1
        print(f"  [close] bar {self.n}: O={bar.open} C={bar.close}")
        if self.n == 3:
            print("  --> BUY submitted at CLOSE of bar 3 (price 104)")
            self.submit_order(self.order_factory.market(inst.id, OrderSide.BUY, Quantity.from_int(10)))
    def on_order_filled(self, e):
        print(f"  *** FILLED at {e.last_px}")
        FILLS.append(float(e.last_px))

FILLS = []
TARGET_PX = 150.00

eng = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
eng.add_venue(VENUE, OmsType.NETTING, AccountType.CASH,
              starting_balances=[Money(1_000_000, USD)], base_currency=USD,
              latency_model=LatencyModel(base_latency_nanos=int(3600*1e9)))
eng.add_instrument(inst)

prices=[(100,101,99,100),(102,103,101,102),(104,105,103,104),(150,155,149,152),(160,161,159,160)]
d0=pd.Timestamp("2020-01-01", tz="UTC"); data=[]
for i,(o,h,l,c) in enumerate(prices):
    day = d0 + pd.Timedelta(days=i)
    t_open  = int((day + pd.Timedelta(hours=9,minutes=15)).value)   # opening print
    t_close = int((day + pd.Timedelta(hours=15,minutes=30)).value)  # daily bar stamped at close
    data.append(TradeTick(inst.id, Price.from_str(f"{o}.00"), Quantity.from_int(100),
                          AggressorSide.NO_AGGRESSOR, TradeId(f"O{i}"), t_open, t_open))
    data.append(Bar(BT, Price.from_str(f"{o}.00"), Price.from_str(f"{h}.00"),
                    Price.from_str(f"{l}.00"), Price.from_str(f"{c}.00"),
                    Quantity.from_int(1000), t_close, t_close))
eng.add_data(sorted(data, key=lambda x: x.ts_init))
eng.add_strategy(T(None))
print(f"Target: fill at {TARGET_PX:.2f} = OPEN of day 4\n")
eng.run()

# THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. The engine, the venue,
# the latency model, the five bars and the order are untouched; the only addition
# is that the fill price the strategy already printed is now also collected and
# compared against the target this file already declares one line above eng.run().
#
# THE TARGET IS NOT INVENTED HERE. It is this file's own stated purpose -- an
# order signalled at the close of bar 3 must fill at the OPEN of day 4, 150.00,
# not at 104.00 (same-bar fill, no latency model) and not at 152.00 (next close,
# no opening tick). Those two wrong answers are named in the header as the
# failures this configuration exists to rule out.
#
# THIS COVERS NO UNIVERSE AND NO ARM. It is a synthetic five-bar probe of
# Nautilus execution semantics on invented prices, and a pass says the port's
# execution assumption holds in the engine, not that any strategy is correct.
print()
if len(FILLS) != 1:
    print(f"  RESULT: FAIL -- expected exactly 1 fill, got {len(FILLS)}: {FILLS}")
    raise SystemExit(1)
if abs(FILLS[0] - TARGET_PX) > 1e-9:
    print(f"  RESULT: FAIL -- filled at {FILLS[0]:.2f}, expected {TARGET_PX:.2f} "
          f"(the OPEN of day 4). A fill at 104.00 means the order filled inside "
          f"the bar that created it; 152.00 means it filled at the next CLOSE.")
    raise SystemExit(1)
print(f"  RESULT: PASS -- single fill at {FILLS[0]:.2f}, the OPEN of day 4, "
      f"as the next-open execution rule requires.")
