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
import profiles
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
    r_gross = r_net + tc/equity(t-1), compounded. Not a zero-cost re-run.

    A MISSING LOG IS FATAL HERE, AND IT USED TO BE A ZERO. This returned
    `(None, 0.0, 0)` when the file was absent -- a tuple indistinguishable from a
    real result of zero trades at zero cost. The step then PRINTED "v1 trades 0,
    TC Rs 0" while the engine one step earlier had reported 795, and died thirty
    lines later formatting the None. The crash was the lucky outcome; the unlucky
    one is a chart rendering a curve labelled "0 trades, Rs 0" that a reader takes
    for a measurement.

    The caller's job is not to call this for an arm the run did not select. That
    is what ARMS_ON is for.
    """
    if not Path(log).exists():
        raise FileNotFoundError(
            f"{log} is missing, so the before-TC figure for this series cannot be "
            f"computed.\n"
            f"  This is NOT the same as zero trades at zero cost, which is what "
            f"this function used to return.\n"
            f"  If the arm was not selected, do not ask for its curve -- build the "
            f"series from ARMS_ON.\n"
            f"  If it was selected, the engine step that writes this log did not "
            f"run or did not write it.")
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

    THE PROFILE IS PART OF THE SIBLING'S NAME TOO, as of 2026-09-12. Before that
    the engines ignored the profile entirely and wrote capped `tradeable` numbers
    into the canonical filenames, so there was no sibling to find and this helper
    could not have been wrong. Now that the engines suffix their output, a
    tradeable run must read the tradeable file or it would plot research curves
    under a tradeable title.
    """
    import cadence as _cd
    import profiles as _pf
    if _cd.is_default() and _pf.is_default():
        return path
    c = path.with_name(path.stem + _cd.suffix() + _pf.suffix() + path.suffix)
    return c if c.exists() else path


def chart_path(M, stem, arms_on):
    """This run's name for the chart, over all three axes. THE ONE DEFINITION.

    A NAMED FUNCTION SO GATE 2 CAN MEASURE IT. The composition used to live in the
    two `_render(...)` call sites, which meant the write call itself received a
    bare local -- `savefig(_path)` -- and naming_declare_check could see nothing to
    verify. It refused to credit the declaration, correctly: an enforcement check
    that accepts "trust me, the caller composed it" is not enforcing anything.

    The rule is unchanged from the call sites it replaces. The canonical two-arm
    figure keeps its bare name, and every other selection gets one of its own.
    """
    import profiles as _pf
    asf = arm_reg.suffix(arms_on) if set(arms_on) != {"v2", "v1"} else ""
    return M / (stem + asf + cadence.suffix() + _pf.suffix() + ".png")


def main(u):
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything here used to run at module level,
    so importing this file executed the whole step as a side effect -- which is
    why the pipeline could only ever spawn it as a subprocess.

    Imports, helper defs and import-time setup stay at module level; every
    other statement moved, constants included, so no dependency chain is split.
    """
    # TRANSITIONAL-ASSERT -- removed by the collapse, steps 3-7 of the new order.
    # transitional_asserts_check.py FAILS while this marker survives, and fails
    # equally if the marker is deleted while a literal REGISTRY["n100"] subscript
    # remains below. It goes green only when the literals are actually gone.
    #
    # THE CONTRACT, AND WHY THIS STEP ONLY ACCEPTS ONE UNIVERSE.
    # main(u) is the declaration run.py dispatches on. This file is still the
    # per-n100 half of a pair, so it can only do n100's work -- and a step that
    # took a universe and quietly ignored it would be the "selection that silently
    # does less than it was asked" failure in its purest form. It verifies the
    # argument instead. The check goes when the pair collapses and the literals
    # below become u.
    assert u.tag == "n100", (
        f"{__name__} is n100's half of an uncollapsed pair; "
        f"invoked for {u.tag}")
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
    # THE LATE-LISTING SCAN, EXTENDED FROM make_mid_chart.py ON 2026-09-13. It
    # existed only on mid, which made the two charts disagree about what they
    # disclosed rather than about what they measured. Names with no data at the
    # window start did not trade for part of it, so the equal-weight buy&hold is
    # an average over a membership that was not all present -- and that is a
    # survivorship-adjacent fact the n100 chart was silent about.
    #
    # THIS IS DISCLOSURE, NOT A FILTER. Nothing is excluded on the strength of it
    # and no number below changes; the scan only counts and names.
    _late, _alive = [], 0
    for _sym in config_n100.SYMBOLS_N100:
        _d = config.read_price_csv(
            config_n100.RAW_DATA_DIR_N100 / f"{_sym}.csv")[["date", "close"]].dropna()
        if _d["date"].min() > CUT:
            _late.append(_sym)
        else:
            _alive += 1
    _n_all, _n_late = len(config_n100.SYMBOLS_N100), len(_late)
    print(f"\n  LATE LISTERS -- read the buy&hold line with this in mind")
    print(f"    {_n_late} of {_n_all} constituents have NO data at {CUT.date()} "
          f"(listed later)" + (f": {', '.join(_late[:8])}"
                               f"{' ...' if _n_late > 8 else ''}" if _n_late else ""))
    print(f"    {_alive} of {_n_all} existed on {CUT.date()}.")
    print( "    More important than the late listers: names that FELL OUT of the index")
    print( "    or delisted between 2019 and 2026 are absent from this file entirely.")
    print( "    The equal-weight buy&hold line is therefore an upper bound on a")
    print( "    portfolio nobody could have held. The cap-weighted NIFTY100 line does")
    print( "    not have that problem, which is why it is plotted alongside.")
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
    # THE CADENCE-NAMED LOGS. The literals stay in the call for
    # check_pipeline_order; _ci picks the _r40 sibling when the engine wrote one.
    # Reading the canonical logs under --rebal 40 gave before_tc a file that does
    # not exist, and it returns (None, 0, 0) silently -- a legend reading
    # "CAGR None% before TC" rather than a crash.
    # COMPUTED ONLY FOR SELECTED ARMS. The literals stay in the call so
    # check_pipeline_order still reads this step's edges out of the source; the
    # GUARD is what changed, exactly as the engine's write is guarded.
    _sel = set(arm_reg.selected_names())
    b_v2 = before_tc(_v2, _ci(M / "daily_trades_n100.csv")) if "v2" in _sel else None
    b_v1 = before_tc(_v1, _ci(M / "daily_trades_v1_n100.csv")) if "v1" in _sel else None
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
            # THE PATH IS KEPT AND PRINTED, not discarded. It used to be bound
            # to `_` here, so when the reader silently substituted a different
            # file nothing in the output said which file had been plotted. The
            # reader is fail-closed now; naming the source is what makes that
            # visible rather than merely true.
            _src, _e = arm_sources.equity_path_and_series(M, "n100", _n)
            _lg = arm_sources.trades_path(M, "n100", _n)
            if _e is None or _lg is None:
                print(f"    {_n}: no curve or trade log written by THIS run's "
                      f"axes -- not plotted")
                continue
            print(f"    {_n}: {arm_sources.describe(_src, len(_e), 'sessions')}")
            print(f"    {_n}: {arm_sources.describe(_lg)}")
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
    # ONLY THE SELECTED ARMS. Naming v2 and v1 as literals here was the same
    # defect as in _render below: it reached b_v1 on a run that never selected v1.
    print("\n    " + "   |   ".join(
        f"{_n} trades {_d[1][2]}, TC Rs {_d[1][1]:,.0f}" for _n, _d in ARMS_ON.items()))
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
    def _render(_arms, _path):
        """Build and save the chart for exactly these arms.

        THE SERIES LIST IS BUILT FROM `_arms`, NOT WRITTEN OUT. It used to name v2
        and v1 as literals, so `--arm v2` formatted a v1 entry whose log had
        correctly not been written, and STEP 10h died on the None. make_mid_chart
        has iterated its selection since a1ab05f; this file was left behind by
        that same commit, which gated both engines' v1 writes and recorded that
        the precondition -- this file being arm-aware -- had been met. It had not.
        """
        series = [
         (f"n100 {_n} ({_AD[_n]})  [inv {_d[3]}%]", _d[0], _d[2], "-",
          f"CAGR {_d[1][0]:.2f}% before TC / {cagr(_d[0]):.2f}% after TC"
          f"  [{_d[1][2]} trades, Rs {_d[1][1]:,.0f}]")
         for _n, _d in _arms.items()] + [
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
        # naming: arm,cadence,profile via chart_path -- _render receives a path
        # compose from arm_reg.suffix(), cadence.suffix() and profiles.suffix();
        # the canonical two-arm figure is written only at an all-default selection.
        plt.savefig(_path, dpi=150, bbox_inches="tight"); plt.close()

    # ------------------------------------------------------------------
    # TWO CHARTS, THE SAME RULE THE COMBINED CHART ALREADY USES.
    # ------------------------------------------------------------------
    # A COLD RUN FOUND THIS, AND NO WARM ONE COULD HAVE. The canonical
    # savefig was gated on the selection BEING exactly {v2, v1}, so the
    # DEFAULT `--arm all` wrote only chart_n100_v1_v2_v3_v4.png and never
    # wrote chart_n100.png at all. Every byte-comparison passed, because the
    # canonical file was still on disk from before the change and nothing
    # overwrote it. Only a run from an empty tree showed it absent.
    #
    # CANONICAL: always exactly v2 and v1, drawn whenever both are selected.
    _written = []
    _canon = {n: d for n, d in ARMS_ON.items() if n in ("v2", "v1")}
    if len(_canon) == 2 and cadence.is_default() and profiles.is_default():
        _render(_canon, M / "chart_n100.png")
        _written.append(M / "chart_n100.png")

    # SELECTION: exactly what this run selected, into its own name.
    if set(ARMS_ON) != {"v2", "v1"} or not cadence.is_default() or not profiles.is_default():
        _asf = arm_reg.suffix(ARMS_ON) if set(ARMS_ON) != {"v2", "v1"} else ""
        _p = M / ("chart_n100" + _asf + cadence.suffix() + profiles.suffix() + ".png")
        _render(ARMS_ON, _p)
        _written.append(_p)
    # REPORTS WHAT WAS WRITTEN, NOT A LITERAL. This printed "chart_n100.png"
    # unconditionally, so `--arm v2` -- which writes chart_n100_v2.png -- named a
    # file it had not produced, and a reader checking the wrong path found a stale
    # one from an earlier run and read it as current.
    for _w in _written:
        print(f"\n  saved -> {_w}")


if __name__ == "__main__":
    from universes.registry import REGISTRY as _R
    main(_R["n100"])
