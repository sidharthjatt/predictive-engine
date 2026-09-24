"""
engine_v2_final.py -- FINAL v2 STRATEGY (breadth-scaled), for one universe

THE PER-UNIVERSE ENTRY POINT, for every universe. Merged 2026-09-15 from
engine_v2_final_mid.py and engine_v2_final_n100.py. Step 5 of the collapse, and
the largest of the eight: unlike the step 3 and step 4 pairs, which differed only
in the tag, these two had diverged in 95 lines of code after universe names were
normalised, and some of that divergence REACHED PUBLISHED ARTEFACTS.

EVERYTHING THAT DIVERGED IS NOW REGISTRY DATA, NOT CODE. universes/registry.py
carries, per universe: validation_status, engine_params_keys (the exact ordered
key list for v2FINAL_params.json), engine_params_static, and engine_text (banner,
panel description, buy&hold label, chart title, and whether the index-absent
assertion applies). The merge is therefore artefact-neutral by construction, and
the gate proves it rather than the author asserting it.

NOTHING HERE IS UNIFIED. midcap150's params carry "validated" and "rejected" and no
"universe"/"n_symbols"; nifty100's carry the opposite. midcap150's chart title is two lines
and nifty100's is one. Neither set is more correct -- they are what the two engines
happened to write -- and changing either is a judgement about a published
artefact, which belongs in its own commit where a moved byte has one possible
cause.

validation_status IS DELIBERATELY ASYMMETRIC. midcap150's dict of eight measured
results and nifty100's sentence saying the work was not done here are a record of
which universe got the validation, not drift. Type tells them apart.

Same strategy, same features, same hyperparameters for every universe; only the
universe differs.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import cadence
import arms.registry as arm_reg
from engine_core import metrics, precompute
from test_exposure import backtest_exposure, CASH_YIELD
import profiles as _prof            # the run's execution-realism profile
# SURVIVORSHIP REPORTING, BACK-PORTED FROM engine_v2_final_n100.py 2026-09-13.
# midcap150 has run under the SAME static-membership bias as nifty100 since it existed --
# 148 of TODAY'S index members backfilled to 2019 -- and said nothing about it in
# any output it wrote. nifty100's engine has reported it all along. The bias was never
# universe-specific; only the disclosure was.
import survivorship as sv
import naming
from config import read_table  # the one CSV/parquet reader: config.read_table
from numerics import rolling_std  # platform-identical variance: results/numerics.py

REBAL, VOL_WIN = 20, 60
# REBAL ABOVE IS THE DEFAULT AND STAYS 20. The cadence this RUN selected is read
# from cadence.selected() at call time and passed to backtest_exposure as an
# argument; the module constant is never reassigned, because a reassigned global
# leaks into the next step (module_state.py names the case).
# SELECTION -- imported from config.py, the single definition.
TOP_N, BUFFER = config.TOP_N, config.BUFFER
START_CAPITAL = 1_000_000
# BACKTEST WINDOW -- imported from config.py, the single definition.
# Date-based and inclusive. The old year cut (BT_START, BT_END = 2019, 2026)
# ran to 2026-06-08, six trading days beyond this window.
BT_START_DATE, BT_END_DATE = config.BT_START_DATE, config.BT_END_DATE


# THE PATHS THIS RUN COMPOSED, IN THE ORDER IT WROTE THEM. Filled by _c() and read
# only by the two report lines at the end of main(). A list rather than a set so
# the order the reader sees is the order the files appeared on disk, and DEDUPED
# at the point of reporting rather than here.
#
# WHY A PATH APPEARS TWICE. daily_trades_v1_<tag>.csv is composed twice -- once in
# the to_csv call and once in the print that names it -- because the literal has
# to stay inside the write call for check_pipeline_order to resolve the edge, so
# the print cannot reuse a local. That is ONE file written once. Reporting it
# twice is the same defect this list exists to close, one turn smaller, and the
# `--arm all` gate run is what showed it: "v2FINAL_equity.csv,
# daily_trades_v1_mid.csv, daily_trades_v1_mid.csv, v2FINAL_params.json".
_WROTE = []


def _c(path):
    """This run's name for an output whose content depends on the cadence.

    THE LITERAL STAYS IN THE CALL. Writers are spelled `_c(M / "<name>.csv")`
    rather than routed through a precomputed variable, because check_pipeline_order
    reads the `M / "<literal>"` shape out of the source to resolve this step's
    edges -- and a computed name made three of them vanish once already.

    At the default cadence this returns the path unchanged, so every published
    filename is exactly what it has always been. A non-default cadence gets
    v2FINAL_equity_r40.csv beside it and never replaces the published file.
    
    THE PROFILE IS PART OF THIS NAME. `tradeable` caps fills at the symbol's
    prior-20-session median volume, which changes every number this step writes.
    Until 2026-09-12 only audit_step.py and v34_common.py consulted the profile,
    so the pipeline half wrote CAPPED numbers into the CANONICAL filenames -- the
    same defect the cadence suffix was introduced to fix, on a third axis, and
    silent rather than fatal. See KNOWN_ISSUES.md.
    """
    import profiles as _pf
    import tax as _tax
    # THE TAX AXIS IS PART OF THIS NAME TOO (2026-09-17). tax=on deducts a
    # lump sum from cash on a payment date, which changes the cash path, the
    # integer share counts sized from it and therefore every number this step
    # writes -- exactly the way `tradeable` does. Writing those into the
    # canonical filenames would be the same defect on a fourth axis.
    _all_default = cadence.is_default() and _pf.is_default() and _tax.is_default()
    _sfx = "" if _all_default else cadence.suffix() + _pf.suffix() + _tax.suffix()
    out = path if not _sfx else path.with_name(path.stem + _sfx + path.suffix)
    # WHAT THIS RUN ACTUALLY WROTE, RECORDED HERE BECAUSE HERE IS WHERE THE NAME
    # IS DECIDED. The step used to end by printing a hardcoded list of the
    # CANONICAL names -- "Saved -> v2FINAL_equity.csv, chart_v2FINAL.png" -- which
    # under `--rebal 200` named five gated files it had not touched and did not
    # name the five it had. A reader went looking for an overwrite that had not
    # happened. A report that misnames its own output is the same class as a check
    # that misdescribes what it checked, so the report is now derived from the
    # composer instead of restating it.
    #
    # RECORDED AT COMPOSE TIME, NOT AFTER THE WRITE, and that is sound here: every
    # caller is `<writer>(_c(...))`, and the summary line is only reached if all of
    # them returned. A write that raises kills the step before anything is printed.
    _WROTE.append(out)
    return out


def main(u):
    # EVERY PER-UNIVERSE VALUE COMES FROM THE REGISTRY, none from this file.
    # `tag` is spelled as a plain local and used in f-strings as "{tag}" because
    # check_pipeline_order substitutes THAT placeholder and no other: an f-string
    # written "{u.tag}" is not a word-character placeholder and every path built
    # from it would fall into unresolved, taking this step's producer edges with it.
    tag = u.tag
    M = Path(u.metrics_dir)
    _T = u.engine_text
    print("=" * 100)
    print(_T["banner"])
    print("=" * 100)
    print("ENGINE v2 FINAL -- cross-sectional ranking + inverse-vol + breadth scaling")
    print("=" * 100)
    print(f"  SURVIVORSHIP: {sv.describe_state()}")

    # UNLISTED FIX 2026-08-28: this read /tmp/v_midcap150_expanding.csv directly and
    # raised FileNotFoundError whenever /tmp had been cleared. nifty100's engine has
    # always used config.require_cache with the permanent copy as the fallback;
    # this now matches it. Pre-existing bug, not introduced by the V34 work.
    # Guard loaded per universe -- see engine_core.set_tradeability.
    import engine_core as _ec
    _ec.set_tradeability(u)
    src = config.require_cache(u.score_cache, what=_T["panel_what"])
    p = read_table(src, parse_dates=["date"])
    # THE INDEX MUST NOT BE IN THE PANEL AS A TRADABLE NAME, where the universe
    # declares that check. nifty100's engine has always asserted it; midcap150's never did.
    # Preserved as declared per-universe data rather than switched on for both --
    # turning it on for midcap150 is a behaviour change and belongs in its own commit.
    if _T.get("assert_index_absent") and u.index_name:
        assert u.index_name not in set(p["symbol"].unique()), \
            "the index is in the score panel as a tradable name"
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = rolling_std(idx.pct_change(), VOL_WIN) * np.sqrt(252)
    tv = port_vol.loc[bd].median()

    # baseline (inv-vol, always invested) and final (breadth-scaled)
    # The baseline's per-trade log is captured and persisted below. v1 rebalances
    # every 20 days and pays real costs -- more than v2 does, because it is always
    # 100% invested and so trades in larger size -- but only its TOTALS used to
    # survive, in v2FINAL_comparison.csv. A total cannot support a per-date
    # analysis, which left make_final_chart_fair.py treating v1 as costless.
    # `audit` only appends to lists; it changes no arithmetic, and the equity
    # curve is asserted identical to the un-audited baseline below.
    base_audit = {k: [] for k in
                  ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    # THE RUN'S CADENCE, PASSED AS AN ARGUMENT. `_reb` is 20 by default, which is
    # what REBAL already was, and `_rebal = REBAL if rebal is None else int(rebal)`
    # resolves both to the same 20 -- so the default path is byte-identical.
    _reb = cadence.selected()
    # THE TAX SELECTION, READ ONCE AND PASSED AS AN ARGUMENT -- exactly as _reb
    # above and participation_cap below. backtest_exposure's tax_enabled is a
    # PARAMETER by design (test_exposure.py:203 gives the reason: same as rebal
    # and participation_cap), so it stays one; what was missing was any caller on
    # the PUBLISHED path passing it.
    #
    # UNTIL 2026-09-18 NO SUCH CALLER EXISTED. tax_enabled defaulted to False at
    # every one of the 31 call sites except tax_report.py's and
    # bh_lots_after_tax.py's, so `--tax on` moved filenames and nothing else: 36
    # of 40 suffixed artefacts were BYTE-IDENTICAL to their untaxed twins and the
    # other 4 differed only in a header label. The axis renamed; it did not charge.
    import tax as _tax_axis
    _taxon = _tax_axis.selected()
    # THE PROFILE'S CAP, RESOLVED ONCE AND PASSED AS AN ARGUMENT.
    # profiles.py records why this is not a global on test_exposure: cadence.py
    # documents rebal_cadence_sweep.py setting test_exposure.REBAL and never
    # restoring it, so every later in-process step silently used the wrong cadence.
    # None under profile="research", so `q` is untouched and the published history
    # is exact.
    import profiles as _prof
    _capkw = _prof.cap_kwargs(u)
    base_eq, tcb, nb, _ = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                            mode="none", target_vol=tv,
                                            audit=base_audit, rebal=_reb,
                                            tax_enabled=_taxon, **_capkw)
    fin_eq, tcf, nf, expo = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                              mode="breadth", target_vol=tv,
                                              rebal=_reb, tax_enabled=_taxon,
                                              **_capkw)
    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

    mbase = metrics(base_eq, "Inverse-vol, 100% invested (v1 final)", tcb, nb)
    mfin = metrics(fin_eq, "+ breadth scaling (v2 FINAL)", tcf, nf)
    mbh = metrics(bh, _T["bh_label"])

    out = pd.DataFrame([mfin, mbase, mbh])
    print("\n" + out.to_string(index=False))
    print(f"\n   v2 FINAL average exposure: {expo*100:.0f}% invested "
          f"(rest in cash at {CASH_YIELD*100:g}% yield)")
    out.to_csv(_c(M / "v2FINAL_comparison.csv"), index=False)

    # yearly
    yr = pd.DataFrame({
        "Strategy%": (fin_eq.resample("YE").last().pct_change().dropna()*100).round(1),
        "BuyHold%": (bh.resample("YE").last().pct_change().dropna()*100).round(1)})
    yr.index = yr.index.year
    yr["Diff"] = (yr["Strategy%"] - yr["BuyHold%"]).round(1)
    print("\n--- YEAR BY YEAR ---")
    print(yr.to_string())
    yr.to_csv(_c(M / "v2FINAL_yearly.csv"))

    # PER-ARM COLUMNS ALONGSIDE THE ORIGINAL TWO.
    # `strategy` is v2 and `baseline_invvol` is v1 -- names that say what the
    # curve was FOR rather than which arm it IS, which is why nothing downstream
    # could ask this file for v3 or v4. The arm-keyed names are
    # arms/registry.Arm.equity_column, the same spelling v34_equity.csv already
    # uses, so the project ends up with ONE name per arm instead of two.
    #
    # THE OLD NAMES ARE GONE FROM THE LIVE UNIVERSES. They were kept as duplicates
    # while the nine readers were repointed one at a time, each byte-compared; that
    # is finished, and every reader now goes through arms/registry.equity_series.
    #
    # THE RETIRED UNIVERSES' FILES CARRY `strategy`/`baseline_invvol` AND ALWAYS
    # WILL. They are those universes' provenance and are not modified, so
    # equity_series' fallback is permanent rather than transitional -- it is how a
    # frozen universe's file is read, not a shim awaiting deletion.
    pd.DataFrame({"date": fin_eq.index,
                  "v1_invvol_none": base_eq.values,
                  "v2_invvol_breadth": fin_eq.values,
                  "buyhold": bh.values}).to_csv(_c(M / "v2FINAL_equity.csv"), index=False)

    # v1 baseline's per-trade log, written the same way daily_trades_<tag>.csv is.
    # Consumers (make_final_chart_fair.py) read the costs from the engine that
    # produced the equity curve, rather than re-running the baseline to recover
    # them. The count is asserted against what the engine itself reported.
    bt = pd.DataFrame(base_audit["trades"])
    assert len(bt) == nb, f"v1 trade log {len(bt)} rows vs engine count {nb}"
    # WRITTEN UNCONDITIONALLY, AND THAT IS A KNOWN LEAK, RECORDED NOT HIDDEN.
    # `--arm v2` still produces daily_trades_v1_<tag>.csv -- a file named for an
    # arm the run did not select. Gating it was TRIED and reverted: STEP 10d
    # make_mid_chart.py declares this file in run_all.REQUIRED_INPUTS as a hard
    # edge, so a gated write makes `--arm v2` die at check_inputs with a missing
    # file. Removing that edge would weaken the static contract and cost the
    # checker a resolved dependency, which experiments/ARM_SUBSET_SPEC.txt's G6
    # forbids. Closing this properly means making make_mid_chart.py arm-aware
    # too; see KNOWN_ISSUES.md.
    # GATED ON v1 BEING SELECTED. `--arm v2` no longer produces a file named for
    # an arm the run did not select.
    #
    # THIS ONLY BECAME POSSIBLE ONCE make_mid_chart.py WENT ARM-AWARE. The first
    # attempt gated the write while STEP 10d still demanded the file
    # unconditionally through run_all.REQUIRED_INPUTS, so `--arm v2` died at
    # check_inputs. That edge now carries the arm it belongs to and is skipped
    # when v1 is not selected -- the requirement became conditional while the
    # literal path stayed put, so the static inventory did not move.
    # THE PRINT IS INSIDE THE CONDITION NOW. It used to sit outside it and name
    # the file unconditionally, so `--arm v3` logged
    #     "v1 baseline trade log: 852 trades, TC Rs 839,393 -> daily_trades_v1_mid.csv"
    # and wrote no such file. Two concrete numbers and a filename, all three read
    # as a completed write, for an arm the run did not select. That is an
    # assertion of completion the step never verified, and the file it names is
    # the one make_mid_chart then fails on.
    #
    # THE COUNTS ARE STILL REPORTED when the write is skipped, because they are a
    # real measurement of the baseline arm -- only the claim about the file is
    # conditional. And the printed name is the COMPOSED one, so a non-default
    # cadence or profile logs the filename it actually wrote rather than the
    # canonical spelling.
    if "v1" in set(arm_reg.selected_names()):
        bt.to_csv(_c(M / f"daily_trades_v1_{tag}.csv"), index=False)
        print(f"   v1 baseline trade log: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
              f"-> {_c(M / f'daily_trades_v1_{tag}.csv').name}")
    else:
        print(f"   v1 baseline: {len(bt)} trades, TC Rs {bt['tc'].sum():,.0f} "
              f"-- trade log NOT WRITTEN, v1 is not in this run's arm selection")

    # THE KEY SET AND KEY ORDER ARE PER-UNIVERSE DATA, and json.dumps preserves
    # insertion order, so this loop is what keeps v2FINAL_params.json byte-identical
    # across the merge. midcap150 writes no "universe" and no "n_symbols"; nifty100 writes
    # both and writes no "validated"/"rejected". Neither set is more correct --
    # they are what the two engines happened to write. Unifying them would move a
    # published artefact, which is a judgement and belongs in its own commit.
    _vals = {
        "model": "cross-sectional LightGBM, 17 feats, 10-seed, monthly, 32d purge",
        "sizing": "inverse-volatility (1/vol60)",
        "exposure": "breadth scaling = fraction of positive-20d-momentum stocks",
        # THE CADENCE THIS RUN ACTUALLY USED, not the module default. Writing
        # REBAL here produced v2FINAL_params_r40.json saying rebalance_days: 20 --
        # a file named for one cadence whose contents claimed another, which is
        # the worst of the two possible errors because the name looks right.
        "top_n": TOP_N, "buffer": BUFFER, "rebalance_days": _reb,
        "avg_exposure_pct": round(expo*100),
        "n_symbols": int(p["symbol"].nunique()),
        "sharpe": mfin["Sharpe"], "maxdd_pct": mfin["MaxDD%"], "cagr_pct": mfin["CAGR%"],
        "cash_yield": CASH_YIELD,
        # STATED IN THE ARTEFACT, not only on the chart, so a reader of
        # v2FINAL_params.json alone knows which membership basis produced it.
        "survivorship": sv.describe_state(),
        "vs_buyhold": (f"Sharpe {mfin['Sharpe']} vs {mbh['Sharpe']}, "
                       f"MaxDD {mfin['MaxDD%']}% vs {mbh['MaxDD%']}%, "
                       f"CAGR {mfin['CAGR%']}% vs {mbh['CAGR%']}%"),
        # A DICT MEANS MEASURED, A STRING MEANS NOT MEASURED ON THIS UNIVERSE.
        # The asymmetry is the record of which universe got the validation work;
        # see universes/registry.py, where it is kept deliberately un-flattened.
        "validation_status": u.validation_status,
    }
    _vals.update(u.engine_params_static or {})
    (_c(M / "v2FINAL_params.json")).write_text(json.dumps(
        {k: _vals[k] for k in u.engine_params_keys}, indent=2))

    # chart
    fig, ax = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[2, 1])
    for s, c, ls, lab in [
            (fin_eq, "#d62728", "-", f"v2 FINAL: + breadth scaling  "
                                     f"(CAGR {mfin['CAGR%']}%, Sharpe {mfin['Sharpe']}, "
                                     f"MaxDD {mfin['MaxDD%']}%)"),
            (base_eq, "#1f77b4", "-", f"v1: inverse-vol, always invested  "
                                      f"(CAGR {mbase['CAGR%']}%, Sharpe {mbase['Sharpe']}, "
                                      f"MaxDD {mbase['MaxDD%']}%)"),
            (bh, "#2ca02c", "--", f"Equal-weight buy & hold  "
                                  f"(CAGR {mbh['CAGR%']}%, Sharpe {mbh['Sharpe']}, "
                                  f"MaxDD {mbh['MaxDD%']}%)")]:
        ax[0].plot(s.index, (s/s.iloc[0]-1)*100, lw=2.2, color=c, ls=ls, alpha=.9, label=lab)
    ax[0].axhline(0, color="k", lw=.7, alpha=.5)
    ax[0].set_ylabel("Cumulative return (%)")
    ax[0].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    # THE TITLE REACHES chart_v2FINAL.png, so it is per-universe data rather than
    # a literal here: midcap150's two lines and nifty100's one are different published
    # artefacts, and unifying them would move a byte for a reason unrelated to
    # this merge.
    ax[0].set_title(naming.run_label(u.label, ["v1", "v2"]) + "\n"
                    + _T["chart_title"] + sv.describe_state(), fontsize=10)
    ax[0].legend(loc="upper left", fontsize=9)
    ax[0].grid(alpha=.3)
    for s, c, ls, lab in [(fin_eq, "#d62728", "-", "v2 FINAL"),
                          (bh, "#2ca02c", "--", "Buy & hold")]:
        dd = (s/s.cummax()-1)*100
        ax[1].fill_between(s.index, dd, 0, color=c, alpha=.22)
        ax[1].plot(s.index, dd, lw=1.5, color=c, ls=ls, label=f"{lab} (max {dd.min():.1f}%)")
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax[1].legend(loc="lower left", fontsize=9)
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(_c(M / "chart_v2FINAL.png"), dpi=150, bbox_inches="tight", metadata={"Title": ax[0].get_title().split("\n")[0]})
    print(f"\n  saved -> {_WROTE[-1].name}")

    # ------------------------------------------------------------------ V3/V4
    # Four-arm pro-vol measurement, per experiments/V34_SPEC.txt. v1 and v2 above
    # are passed in rather than recomputed, so the arms in v34_comparison.csv are
    # the same curves that wrote v2FINAL_equity.csv. Same process, same panel,
    # same dates, same seeds -- which is what the spec requires.
    # Nothing above this line is altered; v2FINAL_* keeps its names and columns.
    import v34_common
    v34_comp, v34_subs, _ = v34_common.run_v34(
        M, u.label, tag, px, op, sc, bd, pc, mom20, port_vol, tv,
        backtest_exposure,
        base_eq, tcb, nb, fin_eq, tcf, nf, expo,
        START_CAPITAL,
        [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)],
        {"TOP_N": TOP_N, "BUFFER": BUFFER, "REBAL": REBAL, "VOL_WIN": VOL_WIN,
         "START_CAPITAL": START_CAPITAL, "CASH_YIELD": CASH_YIELD,
         "SLIPPAGE": 0.0015},
        v1_audit=base_audit)
    print("\n" + "=" * 100)
    print(f" V3/V4 FOUR-ARM MEASUREMENT -- {u.label}")
    print("=" * 100)
    print("\n FULL PERIOD")
    print(v34_comp.to_string(index=False))
    print("\n SUB-PERIODS")
    print(v34_subs.to_string(index=False))
    # NO "saved ->" LINE FOR THE v34 FAMILY HERE. Those five files are written by
    # v34_common.run_v34, which composes their names over THREE axes -- arm,
    # cadence and profile -- none of which this step can see from the literals it
    # used to print. run_v34 reports its own writes; a step reporting another
    # step's output was how the wrong five names came to be printed.

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    print(f"  v2 FINAL   : CAGR {mfin['CAGR%']:>6.2f}%  Sharpe {mfin['Sharpe']:>5.2f}  "
          f"MaxDD {mfin['MaxDD%']:>7.2f}%  Calmar {mfin['Calmar']}")
    print(f"  Buy & hold : CAGR {mbh['CAGR%']:>6.2f}%  Sharpe {mbh['Sharpe']:>5.2f}  "
          f"MaxDD {mbh['MaxDD%']:>7.2f}%  Calmar {mbh['Calmar']}")
    d_sh = mfin["Sharpe"] - mbh["Sharpe"]
    d_dd = mfin["MaxDD%"] - mbh["MaxDD%"]
    d_cagr = mfin["CAGR%"] - mbh["CAGR%"]
    sh_word = "ahead of" if d_sh > 0 else "behind"
    print(f"""
  Versus equal-weight buy & hold over the same period:
    Sharpe   {mfin['Sharpe']:>6.2f} vs {mbh['Sharpe']:>6.2f}   ({d_sh:+.2f})  -- {sh_word} buy & hold
    MaxDD    {mfin['MaxDD%']:>6.2f}% vs {mbh['MaxDD%']:>6.2f}%   ({d_dd:+.2f} pts)
    CAGR     {mfin['CAGR%']:>6.2f}% vs {mbh['CAGR%']:>6.2f}%   ({d_cagr:+.2f} pts)

  The strategy holds {expo*100:.0f}% invested on average, so raw CAGR is not the
  right comparison on its own -- return per deployed rupee and drawdown are.
  Idle cash earns {CASH_YIELD*100:g}%, so none of the return above comes from interest.
  EVERY FIGURE ABOVE IS BEFORE TAX. Against a held-lots buy & hold taxed by the
  same rule, nifty100's edge is +0.46 before tax and -1.59 after -- a -2.05 swing,
  the turnover cost of 478 annual short-term realisations against one deferred
  long-term one. See KNOWN_ISSUES.md and ./venv/bin/python bh_lots_after_tax.py.

{_T.get("bh_caveat", "")}  Standing caveats: no capital gains tax is modelled, survivorship bias inflates
  both lines, and the edge is not statistically significant. The honest next step
  for a real product is a less-efficient universe (mid/small caps) or new data
  (fundamentals), not more tuning here.
""")

    n_names = int(p["symbol"].nunique())
    equal_sel = TOP_N * n_names / 58.0
    print("=" * 100)
    print("SELECTIVITY -- AN OBSERVATION, NOT A CHANGE")
    print("=" * 100)
    print(f"""
  TOP_N is {TOP_N}, unchanged from the two retired universes. Against this universe that is
  a different bet:

      58 names  -> top {TOP_N/58*100:.1f}%
      74 names  -> top {TOP_N/74*100:.1f}%
     {n_names} names  -> top {TOP_N/n_names*100:.1f}%

  For the same selectivity as the retired 58-name setup, TOP_N would have to be about
  {equal_sel:.0f} ({TOP_N}/58 of {n_names}). Under the Fundamental Law, IR is roughly
  IC x sqrt(breadth), and breadth is one of only two levers that can move IR --
  every portfolio-construction experiment on this project has failed precisely
  because it moved neither term. Holding {n_names} candidates but still buying {TOP_N} of
  them takes the wider universe's breadth and then throws most of it away.

  This run deliberately does NOT act on that. TOP_N stays at {TOP_N} so this first
  pass is untuned and directly comparable to the retired universes. Changing it is a
  separate pre-registered experiment, and choosing it after seeing these numbers
  would be fitting the parameter to the result.
""")
    # WHAT WAS WRITTEN, NOT WHAT IS USUALLY WRITTEN. Under the default axes this
    # prints exactly the five names it always did, plus daily_trades_v1_<tag>.csv
    # when v1 is selected -- which this step writes and the old line never
    # mentioned. Under `--rebal 200` it prints the _r200 names, which are the files
    # that exist.
    print("Saved -> " + ", ".join(dict.fromkeys(q.name for q in _WROTE)))


if __name__ == "__main__":
    # STANDALONE, BY TAG. There is no longer a file per universe to imply which.
    from universes.registry import REGISTRY
    if len(sys.argv) != 2 or sys.argv[1] not in REGISTRY:
        raise SystemExit(f"usage: {Path(__file__).name} <universe>   "
                         f"known: {', '.join(sorted(REGISTRY))}")
    main(REGISTRY[sys.argv[1]])
