"""
make_n100_chart.py -- Nifty 100 universe: equity, drawdown, and the two benchmarks.

THE BENCHMARK IS THE PUBLISHED INDEX, READ DIRECTLY BY NAME
    NIFTY100.csv is plotted as-is. No basket is built and called "the index".
    Nifty 100 is free-float capitalisation-weighted; an equal-weighted mean of its
    constituents is a different series with different returns.

    A bare glob over data/raw/nifty100_benchmark/ would sweep NIFTY100.csv into the
    constituent basket as a 100th "stock". That is not hypothetical -- this project
    made exactly that mistake once, averaging the index together with its own
    members and labelling the result as the benchmark. The index is excluded BY
    NAME in config_n100, and the exclusion is asserted here as well.

    Verified figures for this file, reproduced by the run rather than quoted:
      base       2003-01-02 = 1,008.00   against NSE's published base 1000 on 1-Jan-2003
      2019-01-01 -> 2026-06-22: 11,148.80 -> 25,209.55 = 2.26x = 11.54% CAGR

TWO BENCHMARKS, BOTH LABELLED FOR WHAT THEY ARE
    1. NIFTY100 (cap-weighted index) -- investable, and what an index fund would
       actually have returned. Not survivorship-biased: it is the published series.
    2. Equal-weight buy&hold of the 99 constituents -- the right comparison for a
       strategy picking from that universe, but NOT investable and NOT achievable,
       because those 99 are today's members backfilled.

Every headline number is printed before anything is plotted.
Writes chart output only.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import arms.registry as arm_reg
import cadence
import arm_sources, config_n100
import survivorship as sv
def _window_label(eq=None):
    """One line naming the window every figure on the chart belongs to.

    ADDED 2026-09-02. Three different trade counts on three different windows
    once appeared on one chart with none of them labelled: 981 research fills on
    the 1,836-day window, 978 port fills on the same window, and 997 fills from a
    depth study on the retired 1,842-day window. A trade count without its window
    is not checkable, and a CAGR without its window has already been quoted
    against the wrong one in this project.
    """
    import config as _c
    n = f", {len(eq):,} trading days" if eq is not None else ""
    return (f"WINDOW {_c.BT_START_DATE.date()} to {_c.BT_END_DATE.date()}{n} -- "
            f"every CAGR, Sharpe, drawdown and TRADE COUNT on this page is on that "
            f"window and no other.")
def cum(s): return (s / s.iloc[0] - 1) * 100
def dd(s):  return (s / s.cummax() - 1) * 100
def cagr(s):
    y = (s.index[-1] - s.index[0]).days / 365.25
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1) * 100
def sharpe(s):
    r = s.pct_change().dropna()
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0
def before_tc(eq, log):
    """CAGR with the transaction-cost drag removed from the realised path:
    r_gross = r_net + tc/equity(t-1), compounded. Not a zero-cost re-run."""
    if not Path(log).exists():
        return None, 0.0, 0
    tr = pd.read_csv(log, parse_dates=["date"])
    tc = tr.groupby("date")["tc"].sum().reindex(eq.index).fillna(0.0)
    g = (1 + eq.pct_change().fillna(0.0) + (tc / eq.shift(1)).fillna(0.0)).cumprod() * eq.iloc[0]
    return cagr(g), tc.sum(), len(tr)


def _ci(path):
    """The cadence-named sibling of `path` if it exists, else `path` itself.

    THE LITERAL STAYS IN THE CALL -- `_ci(M / "<name>")` -- so
    check_pipeline_order still reads this step's edges out of the source. At the
    default cadence the suffix is empty and this returns the path unchanged.

    Under --rebal 40 the engine wrote v2FINAL_equity_r40.csv and left the
    canonical cadence-20 file alone; reading the canonical one here would plot a
    cadence-20 curve on a chart whose title says 40.
    """
    import cadence as _cd
    if _cd.is_default():
        return path
    c = path.with_name(path.stem + _cd.suffix() + path.suffix)
    return c if c.exists() else path


def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything here used to run at module level,
    so importing this file executed the whole step as a side effect -- which is
    why the pipeline could only ever spawn it as a subprocess.

    Imports, helper defs and import-time setup stay at module level; every
    other statement moved, constants included, so no dependency chain is split.
    """
    M = config_n100.METRICS_DIR_N100
    CAP = 1_000_000
    CUT = pd.Timestamp("2019-01-01")
    eq = pd.read_csv(_ci(M / "v2FINAL_equity.csv"), parse_dates=["date"]).set_index("date")
    # THE TWO ARMS THIS CHART SHOWS, ASKED FOR BY NAME rather than by the column
    # each happened to be stored under. arms/registry.equity_series falls back to
    # the legacy `strategy`/`baseline_invvol` names, so this reads a frozen
    # universe's file too.
    _v2 = arm_reg.equity_series(eq, "v2")
    _v1 = arm_reg.equity_series(eq, "v1")
    params = json.loads((_ci(M / "v2FINAL_params.json")).read_text())
    inv = params["avg_exposure_pct"]
    idx_raw = (config.read_price_csv(config_n100.INDEX_FILE_N100)[["date", "close"]].dropna()
               .set_index("date")["close"].sort_index())
    s_ = idx_raw.reindex(eq.index.union(idx_raw.index)).ffill().reindex(eq.index)
    index = CAP * s_ / s_.iloc[0]
    print("=" * 100)
    print(" NIFTY 100 UNIVERSE -- every number printed before anything is plotted")
    print("=" * 100)
    print(f"\n  SURVIVORSHIP: {sv.describe_state()}")
    print(f"\n  universe          : {len(config_n100.SYMBOLS_N100)} constituents "
          f"({config_n100.INDEX_NAME_N100} excluded BY NAME, not by glob)")
    print(f"  panel symbols     : {params.get('n_symbols', 'see engine output')}")
    print(f"  backtest window   : {eq.index[0].date()} -> {eq.index[-1].date()}")
    print(f"\n  INDEX FILE {config_n100.INDEX_FILE_N100.name}")
    print(f"    base            : {idx_raw.index[0].date()} = {idx_raw.iloc[0]:,.2f}"
          f"   (NSE base 1-Jan-2003 = 1000)")
    print(f"    full series     : {idx_raw.index[0].date()} -> {idx_raw.index[-1].date()}, "
          f"{len(idx_raw):,} rows")
    _w = idx_raw[(idx_raw.index >= CUT) & (idx_raw.index <= pd.Timestamp("2026-06-22"))]
    _y = (_w.index[-1] - _w.index[0]).days / 365.25
    print(f"    2019-01-01 -> 2026-06-22: {_w.iloc[0]:,.2f} -> {_w.iloc[-1]:,.2f} = "
          f"{_w.iloc[-1]/_w.iloc[0]:.2f}x = CAGR {((_w.iloc[-1]/_w.iloc[0])**(1/_y)-1)*100:.2f}%")
    print( "    expected                : 11,148.80 -> 25,209.55 = 2.26x = 11.54% CAGR")
    b_v2 = before_tc(_v2, M / "daily_trades_n100.csv")
    b_v1 = before_tc(_v1, M / "daily_trades_v1_n100.csv")
    # EVERY SELECTED ARM THIS UNIVERSE CAN SHOW, in published order. The two
    # literals above are kept: check_pipeline_order resolves this step's inputs
    # from them, and they are also v2's and v1's own entries below.
    # ARMS is {name: (curve, before_tc tuple, colour, deployed%)}.
    ARMS_ON = {}
    for _n in ("v2", "v1", "v3", "v4"):
        if _n not in set(arm_reg.selected_names()):
            continue
        if _n == "v2":
            _e, _b, _c = _v2, b_v2, "#c0392b"
        elif _n == "v1":
            _e, _b, _c = _v1, b_v1, "#2e6da4"
        else:
            _, _e = arm_sources.equity_path_and_series(M, "n100", _n)
            _lg = arm_sources.trades_path(M, "n100", _n)
            if _e is None or _lg is None:
                continue
            _b = before_tc(_e, _lg)
            _c = {"v3": "#1b9e77", "v4": "#e6ab02"}[_n]
        ARMS_ON[_n] = (_e, _b, _c, arm_sources.deployed_pct(_n, inv))
    _AD = {"v1": "inv-vol", "v2": "breadth", "v3": "provol", "v4": "provol-breadth"}
    print("\n  HEADLINE NUMBERS")
    print(f"    {'series':<44} {'before TC':>10} {'after TC':>9} "
          f"{'Sharpe':>7} {'MaxDD%':>8} {'inv%':>5}")
    rows = [(f"n100 {_n} ({_AD[_n]})", _d[0], _d[1][0], _d[3])
            for _n, _d in ARMS_ON.items()] + [
            ("n100 buy&hold (equal-weight universe)", eq["buyhold"], None, 100),
            ("NIFTY100 (cap-weighted index)", index, None, 100)]
    for lab, s2, b, iv in rows:
        bt = f"{b:>9.2f}%" if b is not None else f"{'--':>10}"
        print(f"    {lab:<44} {bt} {cagr(s2):>8.2f}% {sharpe(s2):>7.2f} "
              f"{dd(s2).min():>7.2f}% {iv:>4}%")
    print(f"\n    v2 trades {b_v2[2]}, TC Rs {b_v2[1]:,.0f}   |   "
          f"v1 trades {b_v1[2]}, TC Rs {b_v1[1]:,.0f}")
    sub = (_window_label(eq) + "\n"
           f"Nifty 100 universe ({len(config_n100.SYMBOLS_N100)} constituents, index excluded "
           f"by name)  |  v2 holds {inv}% invested on average  |  ALL NUMBERS AFTER TC "
           f"(Zerodha + 0.15% slippage)\n"
           f"Benchmarks: NIFTY100 is the published CAP-WEIGHTED index (investable, and NOT "
           f"survivorship-biased). Equal-weight buy&hold is the universe, and is NOT "
           f"investable.\n"
           f"SURVIVORSHIP: these {len(config_n100.SYMBOLS_N100)} are TODAY'S index members "
           f"backfilled to 2019. Names dropped or delisted from the Nifty 100 during the "
           f"window are absent entirely,\nso both the strategy and its equal-weight "
           f"buy&hold are inflated. Do not read that buy&hold as achievable.\n"
           # LIQUIDITY FIGURES REMOVED 2026-09-02. They were hardcoded literals
           # measured on the OLD 1,842-day window ending 2026-06-08 -- see the
           # headers of diagnostics/liquidity_participation.txt and
           # depth_compare.txt. The current window is 1,836 days ending
           # 2026-05-29. They are NOT replaced with recomputed values because no
           # liquidity or depth study has been run on the current window.
           f"LIQUIDITY AND MARKET-IMPACT FIGURES ARE NOT AVAILABLE FOR THIS WINDOW: the "
           f"depth and participation studies were run on the old 1,842-day window\n"
           f"ending 2026-06-08 and have not been re-run. Every number here is a research "
           f"backtest with a flat 0.15% slippage and no market-impact model.\n"
           + sv.describe_state())
    series = [
     (f"n100 v2 (breadth)  [inv {inv}%]", _v2, "#c0392b", "-",
      f"CAGR {b_v2[0]:.2f}% before TC / {cagr(_v2):.2f}% after TC"
      f"  [{b_v2[2]} trades, Rs {b_v2[1]:,.0f}]"),
     ("n100 v1 (inv-vol)  [inv 100%]", _v1, "#2e6da4", "-",
      f"CAGR {b_v1[0]:.2f}% before TC / {cagr(_v1):.2f}% after TC"
      f"  [{b_v1[2]} trades, Rs {b_v1[1]:,.0f}]"),
     ("n100 buy&hold (equal-weight universe)  [inv 100%]", eq["buyhold"], "#3a9d3a", "-",
      f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"),
     ("NIFTY100 (cap-weighted index)  [inv 100%]", index, "#000000", "--",
      f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"),
    ]
    fig, ax = plt.subplots(2, 1, figsize=(16, 11), height_ratios=[2, 1])
    for lab, s2, c, ls, extra in series:
        ax[0].plot(s2.index, cum(s2), lw=2.0, color=c, ls=ls, label=f"{lab}  {extra}")
    ax[0].axhline(0, color="k", lw=.6, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[0].set_title(sub, fontsize=9.5)
    ax[0].legend(loc="upper left", fontsize=8.5); ax[0].grid(alpha=.3)
    for lab, s2, c, ls, _ in series:
        ax[1].plot(s2.index, dd(s2), lw=1.4, color=c, ls=ls,
                   label=f"{lab.split('  [')[0]} (max {dd(s2).min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=8.5); ax[1].grid(alpha=.3)
    plt.tight_layout()
    # THE PUBLISHED NAME IS A LITERAL ON THE COMMON PATH, and a narrowed or
    # widened arm selection writes its own file beside it rather than replacing
    # it -- the same rule the universe axis and the combined chart both use.
    # BOTH AXES IN THE OUTPUT NAME. The published file is the v2+v1 pair at the
    # default cadence and keeps its literal name; any other arm selection or any
    # non-default cadence writes its own file beside it.
    if set(ARMS_ON) == {"v2", "v1"} and cadence.is_default():
        plt.savefig(M / "chart_n100.png", dpi=150, bbox_inches="tight")
    else:
        _asf = arm_reg.suffix(ARMS_ON) if set(ARMS_ON) != {"v2", "v1"} else ""
        plt.savefig(M / ("chart_n100" + _asf + cadence.suffix() + ".png"),
                    dpi=150, bbox_inches="tight")
    print(f"\n  saved -> {M/'chart_n100.png'}")


if __name__ == "__main__":
    main()
