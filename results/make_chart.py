"""
make_chart.py -- the published chart and the printed record, for one universe.

THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
make_mid_chart.py and make_n100_chart.py. Step 6 of the collapse, and the most
divergent pair of the four: 204 code lines differed ignoring whitespace.

WHAT REACHED THE PNG, AND IS THEREFORE REGISTRY DATA, NOT A LITERAL HERE:
the output stem, the render dpi, the drawdown-panel legend font size, the
index-window end date, and whether the equal-weight line is labelled NOT
investable in the legend. universes/registry.py carries them as chart_text.

WHAT IS DERIVED RATHER THAN STORED: every label built from the tag or the index
name -- "<tag> buy&hold (equal-weight universe)", "<index> (cap-weighted index)".
Those were per-universe literals in the merged files and are per-universe facts
the registry already held.

THE EAGER-READ GUARD FROM e5654ac IS KEPT. before_tc is called only for arms the
selection actually contains:

    _sel = set(arm_reg.selected_names())
    b_v2 = ... if "v2" in _sel else None
    b_v1 = ... if "v1" in _sel else None

Without it `--universe mid --arm v3` demands v1's trade log and dies. That was
live for two days, it is the reason one of the two gate cells could not run, and
the merge must not lose it.

NOTHING IS UNIFIED. mid renders at dpi 140 and n100 at 150; mid prints an IC and
extreme-return diagnostic block that n100 has never had. Both are preserved as
declared per-universe data. Harmonising them moves published artefacts and belongs
in its own commit.

THE INDEX IS PLOTTED AS PUBLISHED. The universe's own index file is read directly.
No basket is built and called "the index".
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import arms.registry as arm_reg
import cadence
import profiles
import arm_sources
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
def cum(s): return (s/s.iloc[0]-1)*100
def dd(s):  return (s/s.cummax()-1)*100
def cagr(s):
    y = (s.index[-1]-s.index[0]).days/365.25
    return ((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100
def sharpe(s):
    r = s.pct_change().dropna()
    return r.mean()/r.std()*np.sqrt(252) if r.std() > 0 else 0.0
def before_tc(eq, log):
    """CAGR with the transaction-cost drag removed from the realised path:
    r_gross = r_net + tc/equity(t-1), compounded. Not a zero-cost re-run.

    A MISSING LOG IS FATAL HERE, AND IT USED TO BE A ZERO. Back-ported from
    make_n100_chart.py on 2026-09-13, where `baa5daa` fixed it on 2026-09-12.
    **mid has been substituting zeros for the intervening day, and for the whole
    life of the file before that.**

    It returned `(None, 0.0, 0)` when the file was absent -- a tuple
    indistinguishable from a real result of zero trades at zero cost. Two things
    follow, and the worse one is not the crash:

      - the step prints "trades 0, TC Rs 0" for an arm the engine reported
        hundreds of trades for, and
      - it dies about thirty lines later formatting the None into a chart
        subtitle, with `TypeError: unsupported format string passed to
        NoneType.__format__` and no mention of the file.

    THE CRASH IS THE LUCKY OUTCOME. The unlucky one is a chart rendering a curve
    labelled "0 trades, Rs 0" that a reader takes for a measurement. That is the
    same defect that surfaced as the STEP 10h crash on n100 -- it crashed there
    only because n100 reached the formatting line first.

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
            f"series from ARMS_ON.")
    tr = pd.read_csv(log, parse_dates=["date"])
    tc = tr.groupby("date")["tc"].sum().reindex(eq.index).fillna(0.0)
    g = (1 + eq.pct_change().fillna(0.0) + (tc/eq.shift(1)).fillna(0.0)).cumprod()*eq.iloc[0]
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
    import tax as _tax
    # THE TAX AXIS JOINS THE SIBLING'S NAME (2026-09-17): under tax=on the engine
    # wrote v2FINAL_equity_tax.csv, and reading the canonical file here would
    # plot an untaxed curve on a chart whose title says otherwise.
    if _cd.is_default() and _pf.is_default() and _tax.is_default():
        return path
    c = path.with_name(path.stem + _cd.suffix() + _pf.suffix() + _tax.suffix()
                       + path.suffix)
    return c if c.exists() else path


def chart_path(M, stem, arms_on):
    """This run's name for the chart, over all four axes. THE ONE DEFINITION.

    A NAMED FUNCTION SO GATE 2 CAN MEASURE IT. The composition used to live in the
    two `_render(...)` call sites, which meant the write call itself received a
    bare local -- `savefig(_path)` -- and naming_declare_check could see nothing to
    verify. It refused to credit the declaration, correctly: an enforcement check
    that accepts "trust me, the caller composed it" is not enforcing anything.

    The rule is unchanged from the call sites it replaces. The canonical two-arm
    figure keeps its bare name, and every other selection gets one of its own.
    """
    import profiles as _pf
    import tax as _tax
    asf = arm_reg.suffix(arms_on) if set(arms_on) != {"v2", "v1"} else ""
    return M / (stem + asf + cadence.suffix() + _pf.suffix() + _tax.suffix()
                + ".png")


def main(u):
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything here used to run at module level,
    so importing this file executed the whole step as a side effect -- which is
    why the pipeline could only ever spawn it as a subprocess.
    """
    # EVERY PER-UNIVERSE VALUE COMES FROM THE REGISTRY. `tag` is a plain local and
    # is used in f-strings as "{tag}" because check_pipeline_order substitutes that
    # placeholder and no other.
    tag = u.tag
    _CT = u.chart_text
    _RULE = "=" * _CT["rule_width"]
    # THESE HELPERS CLOSE OVER main()'s LOCALS, so they live inside it.
    # Leaving them at module level while the names they read moved in here
    # raised NameError at the first call -- the wrap is only sound if a
    # helper travels with the state it reads.
    def score_panel_path():
        """This universe's score panel, resolved through the shared guard so a
        missing cache reports which file is absent instead of crashing mid-run."""
        return config.require_cache(M / f"v_{tag}_expanding_cache.csv",
                                    str(u.score_tmp),
                                    what=u.engine_text["panel_what"])
    M = Path(u.metrics_dir)
    CAP = 1_000_000
    CUT = pd.Timestamp("2019-01-01")
    eq = pd.read_csv(_ci(M/"v2FINAL_equity.csv"), parse_dates=["date"]).set_index("date")
    # THE TWO ARMS THIS CHART SHOWS, ASKED FOR BY NAME rather than by the column
    # each happened to be stored under. arms/registry.equity_series falls back to
    # the legacy `strategy`/`baseline_invvol` names, so this reads a frozen
    # universe's file too.
    _v2 = arm_reg.equity_series(eq, "v2")
    _v1 = arm_reg.equity_series(eq, "v1")
    params = json.loads((_ci(M/"v2FINAL_params.json")).read_text())
    inv = params["avg_exposure_pct"]
    idx_raw = (config.read_price_csv(u.index_file)[["date","close"]].dropna()
               .set_index("date")["close"].sort_index())
    s = idx_raw.reindex(eq.index.union(idx_raw.index)).ffill().reindex(eq.index)
    index = CAP*s/s.iloc[0]
    late, alive = [], 0
    # SORTED, because the registry hands back a SET. The per-universe config lists
    # were ordered and this loop only prints, so the sole effect is the order of
    # the late-lister list in the console. No artefact reads it.
    _syms = sorted(u.symbols())
    _raw = u.prepare_data_dir()
    for sym in _syms:
        d = config.read_price_csv(_raw/f"{sym}.csv")[["date","close"]].dropna()
        if d["date"].min() > CUT:
            late.append(sym)
        else:
            alive += 1
    n_all, n_late = len(_syms), len(late)
    print(_RULE)
    print(f" {u.label} -- every number printed before anything is plotted")
    print(_RULE)
    print(f"\n  universe          : {n_all} constituents "
          f"(index {u.index_name} excluded by name, not by glob)")
    print(f"  panel symbols     : {params.get('n_symbols', 'see engine output')}")
    print(f"  backtest window   : {eq.index[0].date()} -> {eq.index[-1].date()}")
    print(f"\n  INDEX FILE {u.index_file.name}")
    print(f"    base            : {idx_raw.index[0].date()} = {idx_raw.iloc[0]:,.2f}"
          f"   (NSE base 1-Apr-2005 = 1000)")
    print(f"    full series     : {idx_raw.index[0].date()} -> {idx_raw.index[-1].date()}, "
          f"{len(idx_raw):,} rows")
    _w = idx_raw[(idx_raw.index >= CUT) & (idx_raw.index <= pd.Timestamp(_CT["index_window_end"]))]
    _y = (_w.index[-1]-_w.index[0]).days/365.25
    print(f"    2019-01-01 -> 2026-06-08: {_w.iloc[0]:,.2f} -> {_w.iloc[-1]:,.2f} = "
          f"{_w.iloc[-1]/_w.iloc[0]:.4f}x = CAGR {((_w.iloc[-1]/_w.iloc[0])**(1/_y)-1)*100:.4f}%")
    print( "    expected                : 6,342 -> 21,926 = 3.46x = 18.16% CAGR")
    # THE CADENCE-NAMED LOGS. The literals stay in the call for
    # check_pipeline_order; _ci picks the _r40 sibling when the engine wrote one.
    # Reading the canonical logs under --rebal 40 gave before_tc a file that does
    # not exist, and it returns (None, 0, 0) silently -- a legend reading
    # "CAGR None% before TC" rather than a crash.
    # COMPUTED ONLY FOR SELECTED ARMS. The literals stay in the call so
    # check_pipeline_order still reads this step's edges out of the source; the
    # GUARD is what changed, exactly as the engine's write is guarded -- and
    # exactly as make_n100_chart has done since baa5daa.
    #
    # 905e598 BACK-PORTED HALF OF baa5daa AND SAID SO WRONGLY. It brought the
    # fatality (a missing log raises instead of returning a fake zero) and left
    # the arm-awareness behind, then reasoned: "The --arm v3 path does not ask
    # for v1's curve, so the regression run does not exercise the changed
    # branch." The line above it asked for v1's curve unconditionally, so the
    # v3 path reached the new raise and died there. `--universe mid --arm v3`
    # was unrunnable from 905e598 until this commit, and the claim that it
    # could not reach the branch is why nobody looked.
    _sel = set(arm_reg.selected_names())
    b_v2 = before_tc(_v2, _ci(M/f"daily_trades_{tag}.csv")) if "v2" in _sel else None
    b_v1 = before_tc(_v1, _ci(M/f"daily_trades_v1_{tag}.csv")) if "v1" in _sel else None
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
            _src, _e = arm_sources.equity_path_and_series(M, tag, _n)
            _lg = arm_sources.trades_path(M, tag, _n)
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
    print(f"    {'series':<42} {'before TC':>10} {'after TC':>9} "
          f"{'Sharpe':>7} {'MaxDD%':>8} {'inv%':>5}")
    rows = [(f"{tag} {_n} ({_AD[_n]})", _d[0], _d[1][0], _d[3])
            for _n, _d in ARMS_ON.items()] + [
            (f"{tag} buy&hold (equal-weight universe)", eq["buyhold"], None, 100),
            (f"{u.index_name} (cap-weighted index)", index, None, 100)]
    for lab, s_, b, iv in rows:
        bt = f"{b:>9.2f}%" if b is not None else f"{'--':>10}"
        print(f"    {lab:<42} {bt} {cagr(s_):>8.2f}% {sharpe(s_):>7.2f} "
              f"{dd(s_).min():>7.2f}% {iv:>4}%")
    # THE IC / EXTREME-RETURN DIAGNOSTIC BLOCK, mid only, and declared as such.
    # Console output with no artefact, but it RE-READS THE SCORE PANEL, so
    # running it for a universe that never had it is new work rather than new
    # formatting. Preserved as per-universe data; switching it on for n100 is a
    # change to what that run does and belongs in its own commit.
    if _CT["diagnostics"]:
        ic = pd.read_csv(score_panel_path(), usecols=["date","symbol"], parse_dates=["date"])
        ic = ic[ic["date"].dt.year >= 2019]
        per_day = ic.groupby("date")["symbol"].nunique()
        n_panel = ic["symbol"].nunique()
        print("\n  PANEL DENSITY -- the blocker that made the first MidCap150 run invalid")
        print(f"    symbols in the scored panel      : {n_panel} of {n_all}")
        print(f"    symbols priced on a given day    : min {per_day.min()}, median "
              f"{int(per_day.median())}, max {per_day.max()}")
        print( "    RESOLVED 2026-08-13. idio_vol_60 and beta_60 were computed by rolling(60)")
        print( "    over the UNION date index, so every day a midcap did not trade voided its")
        print( "    next 60 windows and those rows were dropped. Coverage was 35.7% and 42.1%")
        print( "    against 93.8-100% for the other 15 features, only 65 of 148 names were ever")
        print( "    scored, breadth read 0.202 against 0.550 on the 58, and deployment collapsed")
        print( "    to about 20%. Both features are now computed on each symbol's own trading")
        print( "    index; coverage is 97.0% and 98.5%. The first MidCap150 result (CAGR 9.06%)")
        print( "    was an artefact of that bug and must not be quoted.")
        _px = pd.read_csv(score_panel_path(), parse_dates=["date"]) \
                .pivot_table(index="date", columns="symbol", values="close").ffill()
        _bd = _px.index[(_px.index >= config.BT_START_DATE)
                        & (_px.index <= config.BT_END_DATE)]
        _r = _px.pct_change().loc[_bd]
        _ext = _r.stack(); _ext = _ext[_ext.abs() > 0.55].sort_values(key=abs, ascending=False)
        _m = _r.mean(axis=1)
        _y = (_bd[-1]-_bd[0]).days/365.25
        # TWO NEUTRALISATIONS, AND THEY ANSWER DIFFERENT QUESTIONS. Until 2026-09-13
        # only the second existed and it was printed immediately after the artefact
        # count, in the next sentence, so it read as the artefact effect. It is not:
        # the two day-sets have ZERO overlap and should, because one symbol at +548.8%
        # carries 1/148 of an equal-weight index and moves it about 3.7%, while the
        # largest benchmark days are broad COVID-rebound moves.
        #
        # That conflation was read off this output and transcribed into KNOWN_ISSUES,
        # where it was then "corrected" in the wrong direction. See KNOWN_ISSUES.md,
        # "The mid benchmark is better defined than this file said".
        _art = sorted({_d for (_d, _s) in _ext.index})          # the artefact days
        _m_art = _m.copy()
        for _d in _art:
            if _d in _m_art.index: _m_art.loc[_d] = 0.0
        _bh_art = ((1+_m_art).prod())**(1/_y)*100-100
        _top = _m.sort_values(ascending=False).head(6).index    # largest benchmark days
        _m_ex = _m.copy()
        for _d in _top: _m_ex.loc[_d] = 0.0
        _bh_ex = ((1+_m_ex).prod())**(1/_y)*100-100
        print("\n  *** DO NOT QUOTE THE BUY&HOLD NUMBER WITHOUT THIS ***")
        print(f"    The PRICE panel still contains {len(_ext)} single-day moves above 55% inside the")
        print( "    backtest window. The extreme-return filter masks ret_1d, which protects the")
        print( "    FEATURES and the LABEL, but buy&hold and the execution prices are computed")
        print( "    from `close` directly, so the filter cannot reach them.")
        # ALL OF THEM, NOT head(4). Printing four under a count of six invited the
        # reader to match the list against the six-day neutralisation below, which is
        # a different six entirely.
        for (_d, _s), _v in _ext.items():
            print(f"      {_d.date()}  {_s:<12} {_v:+,.1%}")
        print(f"    Worse, masking a return DROPS that row, and the ffill then releases the whole")
        print( "    accumulated level shift as one day when the symbol reappears. PATANJALI")
        print( "    (formerly Ruchi Soya) moved ~250x between Jan and Jul 2020 on a tiny post-")
        print( "    insolvency float; the drop concentrated that into a single +24,773% day.")
        print(f"    Effect on the benchmark -- TWO DIFFERENT NEUTRALISATIONS, both stated")
        print(f"    because they answer different questions and their day-sets do not overlap:")
        print(f"      buy&hold as computed                                  {cagr(eq['buyhold']):.2f}%")
        print(f"      with the {len(_art)} ARTEFACT days above neutralised          {_bh_art:.2f}%"
              f"   <- the artefact sensitivity")
        print(f"      with the 6 largest BENCHMARK days neutralised         {_bh_ex:.2f}%"
              f"   <- NOT an artefact figure")
        print(f"    The second set is {', '.join(str(_d.date()) for _d in sorted(_top))},")
        print(f"    which contains none of the artefact days. It measures how much of the")
        print(f"    benchmark rests on its six best days, which is a different question.")
        print(f"    The cap-weighted index returns {cagr(index):.2f}%, which is the number to trust.")
        print( "    FIXING THIS NEEDS A DECISION, NOT A THRESHOLD: a symbol's history before a")
        print( "    corporate event of this size is effectively a different security and should")
        print( "    probably be truncated, not stitched. That is a data-handling choice and is")
        print( "    left open rather than made silently.")
    print(f"\n  SURVIVORSHIP -- read the buy&hold line with this in mind")
    print(f"    {n_late} of {n_all} constituents have NO data at 2019-01-01 "
          f"(listed later): {', '.join(late[:8])}{' ...' if n_late > 8 else ''}")
    print(f"    {alive} of {n_all} existed on 2019-01-01.")
    print( "    More important than the late listers: midcaps that FELL OUT of the index")
    print( "    or delisted between 2019 and 2026 are absent from this file entirely, and")
    print( "    midcap churn is far higher than large-cap churn. The equal-weight buy&hold")
    print( "    line is therefore an upper bound on a portfolio nobody could have held.")
    print( "    Measured on the Nifty100 equivalent, this bias was worth about 10 points")
    print( "    of CAGR. The buy&hold number below is NOT achievable.")
    # THE SUBTITLE IS PER-UNIVERSE PROSE AND IT REACHES THE PNG, so it lives in the
    # registry as a callable and this step only supplies the values. The previous
    # version of this merge inlined mid's subtitle for both universes; it read
    # n_panel and per_day, which only mid's diagnostics block binds, so n100 died
    # with UnboundLocalError at STEP 10h and wrote neither its chart nor its daily
    # log. gate_compare's UNCLASSIFIED branch is what caught it.
    _vals = {"n_all": n_all, "n_late": n_late, "alive": alive,
             "inv": inv, "index_name": u.index_name}
    if _CT["diagnostics"]:
        _vals.update(n_panel=n_panel, per_day_median=int(per_day.median()))
    sub = _window_label(eq) + "\n" + _CT["subtitle"](_vals) + sv.describe_state()
    # ONE LINE PER SELECTED ARM, in published order, each with its own colour.
    # v2 and v1 keep the exact colours and label shapes they have always had, so
    # the default chart is unchanged.
    # THE CHARTS THIS RUN ACTUALLY WROTE. Both _render calls below are CONDITIONAL
    # and neither is guaranteed, so nothing outside this list can say what exists.
    _rendered = []

    def _render(_arms, _path):
        """Build and save the chart for exactly these arms."""
        series = [
         (f"{tag} {_n} ({_AD[_n]})  [inv {_d[3]}%]", _d[0], _d[2], "-",
          f"CAGR {_d[1][0]:.2f}% before TC / {cagr(_d[0]):.2f}% after TC"
          f"  [{_d[1][2]} trades, Rs {_d[1][1]:,.0f}]")
         for _n, _d in _arms.items()] + [
         (f"{tag} buy&hold (equal-weight universe"
          f"{', NOT investable' if _CT['bh_not_investable'] else ''})  [inv 100%]", eq["buyhold"],
          "#3a9d3a", "-", f"CAGR {cagr(eq['buyhold']):.2f}%  (buy once, hold: no TC)"),
         (f"{u.index_name} (cap-weighted index)  [inv 100%]", index, "#000000", "--",
          f"CAGR {cagr(index):.2f}%  (index level, not a portfolio: no TC)"),
        ]
        fig, ax = plt.subplots(2, 1, figsize=(16, 11), height_ratios=[2, 1])
        for lab, s_, c, ls, extra in series:
            ax[0].plot(s_.index, cum(s_), lw=2.0, color=c, ls=ls, label=f"{lab}  {extra}")
        ax[0].axhline(0, color="k", lw=.6, alpha=.5)
        ax[0].set_ylabel("Cumulative return (%)")
        ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax[0].set_title(sub, fontsize=9.5)
        ax[0].legend(loc="upper left", fontsize=8.5); ax[0].grid(alpha=.3)
        for lab, s_, c, ls, _ in series:
            ax[1].plot(s_.index, dd(s_), lw=1.4, color=c, ls=ls,
                       label=_CT["dd_label"](lab, dd(s_).min()))
        ax[1].set_ylabel("Drawdown (%)")
        ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax[1].legend(loc="lower left", fontsize=_CT["legend_fontsize"]); ax[1].grid(alpha=.3)
        plt.tight_layout()
        # naming: arm,cadence,profile via chart_path -- _render receives a path
        # compose from arm_reg.suffix(), cadence.suffix() and profiles.suffix();
        # the canonical two-arm figure is written only at an all-default selection.
        plt.savefig(_path, dpi=_CT["dpi"], bbox_inches="tight"); plt.close()
        _rendered.append(_path)

    # ------------------------------------------------------------------
    # TWO CHARTS, THE SAME RULE THE COMBINED CHART ALREADY USES.
    # ------------------------------------------------------------------
    # A COLD RUN FOUND THIS, AND NO WARM ONE COULD HAVE. The canonical
    # savefig was gated on the selection BEING exactly {v2, v1}, so the
    # DEFAULT `--arm all` wrote only chart_mid_FINAL_v1_v2_v3_v4.png and never
    # wrote chart_mid_FINAL.png at all. Every byte-comparison passed, because the
    # canonical file was still on disk from before the change and nothing
    # overwrote it. Only a run from an empty tree showed it absent.
    #
    # CANONICAL: always exactly v2 and v1, drawn whenever both are selected.
    _canon = {n: d for n, d in ARMS_ON.items() if n in ("v2", "v1")}
    if len(_canon) == 2 and cadence.is_default() and profiles.is_default():
        _render(_canon, M / f"{_CT['stem']}.png")

    # SELECTION: exactly what this run selected, into its own name.
    if set(ARMS_ON) != {"v2", "v1"} or not cadence.is_default() or not profiles.is_default():
        _asf = arm_reg.suffix(ARMS_ON) if set(ARMS_ON) != {"v2", "v1"} else ""
        _render(ARMS_ON, chart_path(M, _CT["stem"], ARMS_ON))
    # WHAT WAS WRITTEN, WHICH IS NOT THE CANONICAL NAME AND SOMETIMES IS NO NAME.
    # This printed `<stem>.png` unconditionally -- the canonical figure -- while
    # BOTH renders above are conditional on the selection. Under `--rebal 200` the
    # canonical branch does not run at all, and the line still announced
    # chart_mid_FINAL.png: a gated file this step had not touched, named as though
    # it had just been written. The comment that stood here said the n100 half had
    # once "named a literal rather than what was written", so the defect was known
    # in one direction and reintroduced in the other.
    #
    # A RUN THAT RENDERS NOTHING SAYS SO. Silence would read as success, and an
    # empty list is exactly the case a reader needs told.
    if _rendered:
        print("\nsaved -> " + ", ".join(q.name for q in _rendered))
    else:
        print("\nsaved -> nothing: no chart was rendered for this selection")


if __name__ == "__main__":
    # STANDALONE, BY TAG. There is no longer a file per universe to imply which.
    from universes.registry import REGISTRY
    if len(sys.argv) != 2 or sys.argv[1] not in REGISTRY:
        raise SystemExit(f"usage: {Path(__file__).name} <universe>   "
                         f"known: {', '.join(sorted(REGISTRY))}")
    main(REGISTRY[sys.argv[1]])
