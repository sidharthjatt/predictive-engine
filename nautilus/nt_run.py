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
# THE DEFAULT UNIVERSE IS THE FIRST REGISTERED ONE, not a literal tag. It was
# UNIVERSES["58"], which raised KeyError at IMPORT the moment the 58 was deleted --
# taking nt_verify, nt_daily_compare, nt_holdings_compare and depth_compare with
# it, none of which mention a universe themselves.
_DEFAULT_UNIVERSE = next(iter(UNIVERSES))
PRICE_CACHE = UNIVERSES[_DEFAULT_UNIVERSE]["cache"]
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


def reports_segment(mode, sizing, rebal=None):
    """The leaf directory identifying one (arm, cadence, profile) combination.

    A NAMED FUNCTION SO IT CAN BE MEASURED. This was eleven lines inline inside
    run(), which is why naming_declare_check could not verify it: the check asks
    which axes a composer carries by varying one axis at a time and watching the
    output, and it cannot call code buried in the middle of a function that boots
    a backtest engine. Inline composition is exactly how the profile went missing
    here for as long as it did -- nothing could interrogate it.

    Registered in naming.CARRIES as carrying all three axes, measured, not assumed.
    """
    # THE CADENCE JOINS THE PATH, on the same rule the research side uses: the
    # default is unsuffixed so nautilus/reports/mid/v1/ keeps meaning what it has
    # always meant, and a non-default cadence gets v1@r40 of its own rather than
    # overwriting it.
    # AND THE PROFILE JOINS IT TOO -- SITE 12, fixed 2026-09-12. This path carried
    # the universe, then the arm, then the cadence, each added after the axis
    # before it had already collided. The profile was the one axis left, and it
    # had ALREADY fired: `tradeable` caps fills at the symbol's prior-20-session
    # median volume, so a tradeable run produces different orders, different fills
    # and different positions -- and wrote all of them over the research run's
    # reports, in place, under a directory name that still said `mid/v2`. Two
    # tradeable v34 runs are on record, so this destroyed reports rather than
    # risking it.
    #
    # SAME DEFAULT-IS-UNSUFFIXED RULE as every other axis: research is the default
    # and stays unsuffixed, so nautilus/reports/mid/v2/ keeps meaning exactly what
    # it has always meant and no existing path moves.
    from arms.registry import path_segment
    import cadence as _cad
    import profiles as _pf
    import tax as _tax
    seg = path_segment(mode, sizing)
    r = _cad.DEFAULT if rebal is None else int(rebal)
    if r != _cad.DEFAULT:
        seg = f"{seg}@r{r}"
    # THE PROFILE GOES INTO THE PATH AND NOWHERE ELSE. This segment keeps a
    # tradeable run from overwriting a research run's reports, which is what it
    # was added for and all it does. NOTHING DOWNSTREAM OF THIS LINE READS THE
    # PROFILE: nt_strategy.py sizes at :391 with no participation cap, and
    # `participation_cap`, `vol20` and `median_volume` appear nowhere under
    # nautilus/. So `@tradeable` in a report path records which profile the run
    # SELECTED, not which one it APPLIED -- the fills beneath it are uncapped.
    # Recorded 2026-09-20 as the current limitation; see the note at the sizing
    # line in nt_strategy.py and the note files in the two @tradeable directories
    # on disk.
    if not _pf.is_default():
        seg = f"{seg}@{_pf.selected()}"
    # THE TAX AXIS, 2026-09-17, CARRIED HERE EVEN THOUGH NAUTILUS DOES NOT MODEL
    # TAX -- and that is the point. Site 12 is on record precisely because an
    # axis that had ALREADY fired was absent from this path, so a run wrote over
    # another run's reports in place under a directory name that did not
    # distinguish them. Carrying an axis Nautilus ignores costs one empty string
    # at the default and cannot destroy anything; omitting one it later honours
    # is the defect this comment block exists to describe.
    if not _tax.is_default():
        seg = f"{seg}@tax"
    return seg


# naming: arm,cadence,profile via reports_segment -- every report this step
# writes lands in `out`, which carries the universe as a directory and the
# arm, cadence and profile as its leaf segment (reports_segment above). The
# axes are in the PATH here, not in the filenames, which is why the
# filenames beneath it are bare literals.
def run(trading_start, trading_end, symbols=None, quiet=True,
        universe=None,
        sizing="invvol", mode="breadth", rebal=None):
    warm_start = (pd.Timestamp(trading_start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    print(f"data from {warm_start} (warm-up) | trading {trading_start} to {trading_end}")

    U = UNIVERSES[universe if universe is not None else _DEFAULT_UNIVERSE]
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
    # sizing/mode default to what every caller relied on when these were module
    # globals, so an existing call site behaves exactly as before.
    strat.configure(scores, instruments, trading_start, sizing=sizing, mode=mode,
                    rebal=rebal)
    eng.add_strategy(strat)

    eng.run()

    # Nautilus's own reports -- these carry the real order status (FILLED, DENIED,
    # CANCELED) rather than anything reconstructed by hand.
    # ONE DIRECTORY PER UNIVERSE. This used to be a single shared `reports/`, so a
    # verification loop over 58, 74 and mid left only the LAST universe on disk and
    # silently overwrote the other two -- the files looked current while describing
    # a run nobody asked about. The universe is part of the path now, so all three
    # persist side by side and a directory cannot be mistaken for another's output.
    #
    # AND ONE DIRECTORY PER ARM UNDER IT, for exactly the same reason one level up.
    # run() gained sizing/mode as arguments on 2026-09-04, which made the collision
    # the universe split had just fixed reappear on the other axis:
    # verify_v34_arms.py runs four arms per universe in a loop, and all four wrote
    # here, so nautilus/reports/mid/ described whichever arm happened to run last
    # while looking like the universe's report. The arm name comes from
    # arms.registry, so the directory and the arm cannot drift apart, and a
    # combination that is not one of the four named arms gets "{mode}-{sizing}"
    # rather than being folded into one that is.
    _seg = reports_segment(mode, sizing, rebal)
    out = Path(__file__).resolve().parent / "reports" / universe / _seg
    out.mkdir(parents=True, exist_ok=True)
    # THREE REPORTS, AND TWO OF THEM ARE ABOUT ORDERS. The distinction is the
    # whole reason both exist:
    #
    #   orders_all.csv    generate_orders_report() -- EVERY order the strategy
    #                     submitted, whatever became of it. A DENIED or CANCELED
    #                     order appears here and NOWHERE ELSE. This is the file to
    #                     read when asking "did the engine try something that did
    #                     not happen".
    #   order_fills.csv   generate_order_fills_report() -- one row per order that
    #                     produced a fill, so its row count necessarily matches
    #                     fills.csv. A rejected order is invisible here.
    #
    # order_fills.csv WAS CALLED orders.csv, WHICH WAS A LIE THE FILE ITSELF
    # ADMITTED: the old comment said "orders.csv IS NOT AN ORDERS REPORT" and kept
    # the name on the grounds that downstream scripts read it. Nothing reads it --
    # grepped across .py, .md and .txt, the only other mentions are two docstrings.
    # Now that a real orders report sits beside it, a name that means
    # "fill-producing orders" is worth more than a name that was never accurate.
    orders_all_rep = eng.trader.generate_orders_report()
    order_fills_rep = eng.trader.generate_order_fills_report()
    fills_rep = eng.trader.generate_fills_report()
    pos_rep = eng.trader.generate_positions_report()
    orders_all_rep.to_csv(out / "orders_all.csv")
    order_fills_rep.to_csv(out / "order_fills.csv")
    fills_rep.to_csv(out / "fills.csv")
    pos_rep.to_csv(out / "positions.csv")

    # THE DAILY PORTFOLIO STATE, PERSISTED. The strategy has recorded one row per
    # trading day all along -- date, cash, mtm, equity -- and nt_daily_compare
    # consumed it IN PROCESS and then threw it away. Nothing on disk described
    # what the execution engine thought the book was worth day by day.
    if getattr(strat, "daily_equity", None):
        pd.DataFrame(strat.daily_equity).to_csv(out / "daily_equity.csv", index=False)
    if getattr(strat, "daily_holdings", None):
        pd.DataFrame(strat.daily_holdings).to_csv(out / "daily_holdings.csv", index=False)
    print(f"\n  reports -> nautilus/reports/{universe}/{out.name}/  "
          f"[{U['tag']} universe, arm {out.name}: mode={mode} sizing={sizing}]  "
          f"(orders_all {len(orders_all_rep)}, order_fills {len(order_fills_rep)}, "
          f"fills {len(fills_rep)}, positions {len(pos_rep)})")

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
    uni = _DEFAULT_UNIVERSE
    for u in UNIVERSES:
        if f"--universe={u}" in sys.argv:
            uni = u
    if "--full" in sys.argv:
        run("2019-01-01", UNIVERSES[uni]["end"], universe=uni)
    else:
        print(f"SMOKE TEST: full {uni} universe, 2019 only\n")
        run("2019-01-01", "2019-12-31", universe=uni)
