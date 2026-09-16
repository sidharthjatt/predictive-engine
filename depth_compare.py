"""
depth_compare.py -- the port under "unlimited" depth versus "volume" depth.

Runs n100 and mid twice each and reports what changes when the quote stops being
infinitely deep. Changes no default: DEPTH_MODE is set on the module for the
duration of a run and restored afterwards.

WHAT IS COUNTED
    walked   a fill that occurred at a price worse than the top level, i.e. the
             order consumed level 1 and met level 2 or 3. Detected by comparing
             the fill price against open*(1 +/- 1*SLIPPAGE), which is the top
             level, with a tolerance of half a tick.
    unfilled orders the strategy submitted that never produced a fill. Under
             unlimited depth this is always zero; under volume depth it is the
             number that could not be executed at all, which is the figure that
             decides whether the strategy is tradeable at this size.
"""
import contextlib
import io
import sys
import warnings

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "nautilus"))
sys.path.insert(0, str(ROOT / "results"))

import nt_data, nt_run
from engine_core import metrics
from universes.registry import REGISTRY

SLIPPAGE = nt_run.SLIPPAGE

# THE SOURCE FOLDER, NOT data_dir, AND THE SORTED SYMBOL LIST. Both came from
# config_n100 / config_mid until step 7; both are registry fields now and carry
# the same values. `symbol_list` is the sorted tuple the configs' SYMBOLS_* were,
# so the volume panel is loaded in the same order it always was.
UNIV = [("n100", REGISTRY["n100"].raw_data_dir, REGISTRY["n100"].symbol_list),
        ("mid", REGISTRY["mid"].raw_data_dir, REGISTRY["mid"].symbol_list)]


def perf_from_strat(strat, tag):
    eq = pd.DataFrame(strat.daily_equity)
    eq["date"] = pd.to_datetime(eq["date"])
    e = eq.set_index("date")["equity"]
    tc = sum(f["tc"] for f in strat.fills)
    m = metrics(e, tag, tc, len(strat.fills))
    return m, e


def run_mode(u, mode, raw_dir, syms):
    nt_data.set_depth_mode(mode)
    if mode == "volume":
        n = nt_data.set_volume_source(raw_dir, set(syms))
        print(f"    volume loaded for {n} symbols", flush=True)
    U = nt_run.UNIVERSES[u]
    with contextlib.redirect_stdout(io.StringIO()):
        s = nt_run.run("2019-01-01", U["end"], quiet=True, universe=u)
    nt_data.set_depth_mode("unlimited")
    return s


def main():
    print("=" * 104)
    print(" DEPTH MODEL -- 'unlimited' (default, unchanged) vs 'volume'")
    print(f" levels {nt_data.DEPTH_LEVELS} | top-level depth "
          f"{nt_data.DEPTH_FRACTION:.0%} of prior-{nt_data.DEPTH_VOL_WIN}d median "
          f"daily volume | spacing {SLIPPAGE:.2%} per level")
    print("=" * 104)

    for u, raw_dir, syms in UNIV:
        print(f"\n{'='*104}\n {u.upper()}\n{'='*104}", flush=True)
        res = {}
        for mode in ("unlimited", "volume"):
            print(f"  running {mode} ...", flush=True)
            s = run_mode(u, mode, raw_dir, syms)
            m, e = perf_from_strat(s, u)
            f = pd.DataFrame(s.fills)
            # COUNTED PER ORDER, NOT PER FILL EVENT.
            #   A walking order emits one fill event per level it consumes, so
            #   `orders_submitted - len(fills)` is not an unfilled count -- it went
            #   NEGATIVE on the first attempt, which is what exposed the error.
            #   client_order_id from the venue's own fills report is the order
            #   identity, so distinct ids that produced any fill is what "filled"
            #   means, and an id appearing more than once is an order that walked.
            # The arm is part of the reports path now (a run's sizing/mode chose
            # the directory). This script never passes either, so nt_run's own
            # defaults apply -- named through arms.registry rather than spelled
            # "v2" here, so the two cannot drift.
            import inspect
            from arms.registry import path_segment
            _d = {k: v.default for k, v in inspect.signature(nt_run.run).parameters.items()}
            rep = (Path("nautilus") / "reports" / u
                   / path_segment(_d["mode"], _d["sizing"]) / "fills.csv")
            fr = pd.read_csv(rep)
            per_order = fr.groupby("client_order_id").size()
            filled_orders = int(len(per_order))
            walked = int((per_order > 1).sum())
            walked_levels = per_order[per_order > 1]
            unfilled = int(s.orders_submitted - filled_orders)
            res[mode] = dict(m=m, fills=len(f), orders=filled_orders,
                             walked=walked, unfilled=unfilled,
                             submitted=s.orders_submitted,
                             lv=walked_levels)
            print(f"    CAGR {m['CAGR%']:>7.2f}  Sharpe {m['Sharpe']:>5.2f}  "
                  f"MaxDD {m['MaxDD%']:>7.2f}  submitted {s.orders_submitted:>4}  "
                  f"orders filled {filled_orders:>4}  fill events {len(f):>4}  "
                  f"walked {walked:>4}  unfilled {unfilled:>3}", flush=True)
            if walked:
                d = walked_levels.value_counts().sort_index()
                print(f"      fills per walking order: "
                      + ", ".join(f"{k} levels x{v}" for k, v in d.items()), flush=True)

        a, b = res["unlimited"], res["volume"]
        print(f"\n  {'':<12}{'CAGR%':>9}{'Sharpe':>9}{'MaxDD%':>9}{'trades':>8}"
              f"{'fills':>8}{'walked':>8}{'unfilled':>10}")
        for lab, r in (("unlimited", a), ("volume", b)):
            print(f"  {lab:<12}{r['m']['CAGR%']:>9.2f}{r['m']['Sharpe']:>9.2f}"
                  f"{r['m']['MaxDD%']:>9.2f}{r['m']['Trades']:>8}{r['orders']:>8}"
                  f"{r['walked']:>8}{r['unfilled']:>10}")
        print(f"  {'delta':<12}{b['m']['CAGR%']-a['m']['CAGR%']:>+9.2f}"
              f"{b['m']['Sharpe']-a['m']['Sharpe']:>+9.2f}"
              f"{b['m']['MaxDD%']-a['m']['MaxDD%']:>+9.2f}"
              f"{b['m']['Trades']-a['m']['Trades']:>+8}{b['fills']-a['fills']:>+8}")


if __name__ == "__main__":
    main()
