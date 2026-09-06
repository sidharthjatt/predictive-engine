"""
make_final_summary.py -- summary table for the FINAL system.
Only the current final lines: v2, v1 and the references. No rejected variants.
Every number is read from the actual output files.
"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from universes.registry import REGISTRY, selected_tags
import arms.registry as arm_reg

# config74 WAS IMPORTED HERE AND NEVER USED -- M74 was assigned from it and read
# nowhere. Dropped rather than guarded: an import that exists only to be assigned
# to a dead local is a dependency this file does not have, and it would have made
# the step unloadable the moment config74.py was deleted.

def main():
    """The step, as a function, so run.py can call it in process.

    IMPORT MUST NOT DO THE WORK. Everything below used to run at module
    level, so importing this file executed the whole step as a side effect.
    That is why the pipeline could only ever spawn it as a subprocess.
    """
    M58 = Path(config.METRICS_DIR)

    # THIS STEP IS DOWNSTREAM OF make_final_chart_fair.py AND SKIPS WITH IT.
    # That step writes fair_comparison_table.csv and skips entirely when neither 58
    # nor 74 is SELECTED; with no table there is nothing to summarise. The two
    # conditions are checked independently rather than one inferred from the other,
    # so a missing table for any OTHER reason still reports honestly instead of
    # crashing inside pandas.
    # SELECTION, NOT REGISTRATION -- the same condition make_final_chart_fair.py
    # now uses, so the two cannot disagree about whether a table was written.
    if not ({"58", "74"} & set(selected_tags())):
        print("FINAL summary SKIPPED -- neither 58 nor 74 is in this run's "
              "selection, so make_final_chart_fair.py wrote no "
              "fair_comparison_table.csv.")
        return
    # THE SAME SUFFIX make_final_chart_fair.py wrote. A narrowed arm selection
    # produces fair_comparison_table_v1.csv, and summarising the canonical table
    # instead would report arms this run did not select.
    # THE SAME SUFFIX make_final_chart_fair.py wrote, computed the same way.
    # NOT arm_reg.selection_suffix(): that is empty only for all FOUR arms, and
    # this table is over the SHIPPING PAIR, so the full case here is {v2, v1}.
    # Using the four-arm predicate would look for fair_comparison_table_v1_v2.csv
    # on a default run and skip because it does not exist.
    _PLOT = ("v2", "v1")
    _sel = [a for a in _PLOT if a in set(arm_reg.selected_names())]
    if not _sel:
        print("FINAL summary SKIPPED -- this run selected none of the shipping "
              "arms (v2, v1), so make_final_chart_fair.py wrote no table.")
        return
    _asfx = "" if set(_sel) == set(_PLOT) else "_" + "_".join(_sel)
    # THE CANONICAL NAME AS A LITERAL on the common path, for the same reason the
    # writer spells it out: this is the STEP 13 -> STEP 14 edge the checker reads.
    src = (M58 / "fair_comparison_table.csv" if _asfx == ""
           else M58 / ("fair_comparison_table" + _asfx + ".csv"))
    if not src.exists():
        print(f"FINAL summary SKIPPED -- {src} does not exist. It is written by "
              "STEP 13 make_final_chart_fair.py.")
        return
    fair = pd.read_csv(src)

    # fair table row -> (variant, line)
    meta = {
     "58 v2 (breadth)":   ("FINAL_system", "58 v2"),
     "58 v1 (inv-vol)":   ("FINAL_system", "58 v1"),
     "74 v2 (breadth)":   ("FINAL_system", "74 v2"),
     "74 v1 (inv-vol)":   ("FINAL_system", "74 v1"),
     # Labels follow make_final_chart_fair.py, which renamed these when the benchmark
     # was corrected. "Nifty100" used to be an equal-weighted basket of 99 constituents
     # -- not the Nifty 100, which is cap-weighted -- so the row now says which index it
     # actually is, and the buy&hold rows say they are equal-weight universe baskets.
     "58 buy&hold (equal-weight universe)":   ("REFERENCE", "58 buy&hold"),
     "74 buy&hold (equal-weight universe)":   ("REFERENCE", "74 buy&hold"),
     "NIFTY100 (cap-weighted index, 58 win)": ("REFERENCE", "NIFTY100 58win"),
     "NIFTY100 (cap-weighted index, 74 win)": ("REFERENCE", "NIFTY100 74win"),
    }

    rows = []
    for _, r in fair.iterrows():
        name = str(r["Strategy"])
        if name not in meta:
            continue
        variant, line = meta[name]
        dd = float(r["MaxDD%"])
        rows.append({
            "variant": variant,
            "line": line,
            "CAGR%": round(float(r["CAGR%"]), 2),
            "Sharpe": round(float(r["Sharpe"]), 2),
            "MaxDD%": round(dd, 2),
            "Calmar": round(float(r["CAGR%"]) / abs(dd), 2) if dd != 0 else "",
            "Invested%": round(float(r["AvgInvested%"]), 1),
            "Cash%": round(float(r["AvgCash%"]), 1),
            "CAGR_per_InvestedCapital%": round(float(r["CAGR_per_InvestedCapital%"]), 2),
        })

    # ORDER, OVER WHICHEVER UNIVERSES ARE PRESENT. The strategy lines first, then
    # the buy&hold references, then one index line per universe window -- the same
    # sequence the literal list carried, derived so a removed universe simply takes
    # its own entries out.
    #
    # The literal list said "Nifty100 58win" while meta produces "NIFTY100 58win".
    # Those never matched, so both index rows got a NaN sort key and landed last by
    # accident -- which happened to be where they belonged. Spelled correctly here;
    # the resulting order is unchanged, and that was verified byte-for-byte against
    # the previous FINAL_SUMMARY_TABLE.csv rather than assumed.
    tags = [t for t in ("58", "74") if t in REGISTRY]
    order = ([f"{t} {v}" for t in tags for v in ("v2", "v1")]
             + [f"{t} buy&hold" for t in tags]
             + [f"NIFTY100 {t}win" for t in tags])
    df = pd.DataFrame(rows)
    df["_o"] = df["line"].map({k: i for i, k in enumerate(order)})
    df = df.sort_values("_o").drop(columns="_o").reset_index(drop=True)

    print("=" * 100)
    print("FINAL SYSTEM  |  Rs 10L  |  2019 - Jun'26 (58) / Dec'25 (74)  |  after TC, before tax")
    print("=" * 100)
    print(df.to_string(index=False))
    print("=" * 100)

    # THE SUFFIX FOLLOWS THE TABLE THIS SUMMARY WAS BUILT FROM.
    # It read fair_comparison_table_v1.csv and wrote the CANONICAL
    # FINAL_SUMMARY_TABLE.csv, so `--arm v1` silently replaced the published
    # summary with a one-arm one. The canonical name is a literal on the common
    # path, for check_pipeline_order, with the suffixed form in the else branch.
    if _asfx == "":
        out = M58 / "FINAL_SUMMARY_TABLE.csv"
    else:
        out = M58 / ("FINAL_SUMMARY_TABLE" + _asfx + ".csv")
    df.to_csv(out, index=False)
    print(f"\nsaved -> {out}")

if __name__ == "__main__":
    main()
