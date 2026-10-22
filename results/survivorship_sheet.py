"""
survivorship_sheet.py -- static against point-in-time, one table per arm, research profile.

    ./venv/bin/python results/survivorship_sheet.py
    ./venv/bin/python results/survivorship_sheet.py pit-compare OUT.csv [universe ...]

The second form is the old results/pit_compare.py, merged here on 2026-10-18; its
description is PIT_COMPARE_DOC below.

Read-only: reads existing artefacts and runs nothing. Writes
diagnostics/survivorship_sheet_research.csv (one block per arm, v1 to v4) and
diagnostics/survivorship_sheet_research.xlsx (one sheet per arm). Columns are the
universes in COLUMNS order; rows, all in percent to two decimals:

    pit, tax off: CAGR                 v34_equity_pit.csv
    pit, tax on: CAGR                  v34_equity_tax_pit.csv
    static, tax off: CAGR              v34_equity.csv
    static, tax on: CAGR               v34_equity_tax.csv
    NSE index: CAGR                    the close column of the universe's own index
    NSE index: MaxDD                   file (Universe.index_file, e.g. "NIFTY 100.csv")
    static, tax off: MaxDD             v34_equity.csv
    static, tax off: average drawdown  the same
    pit, tax off: MaxDD                v34_equity_pit.csv
    pit, tax off: average drawdown     the same
    equal-weight basket (untaxed, daily rebalanced): CAGR
    equal-weight basket (untaxed, daily rebalanced): MaxDD
                                       the buyhold column of v34_equity.csv

THE NSE INDEX rows are the published index itself, read from its file's close
column. These files are PRICE indices, not total-return indices: the Nifty 50
file closes at 10,910.10 on 2019-01-01, the price index's level that day, and
adjusted_close equals close on every row. Dividends are not in them.

THE EQUAL-WEIGHT BASKET is the README's "buy & hold, reference (untaxed,
daily-rebalanced index)": the costless equal-weight basket of the static universe,
the "buy & hold equal-weight" row of v34_comparison.csv.

WINDOWS. Static, NSE index and basket rows use the published static window, 2019-01-01 to
2026-05-29, for every universe, microcap250 included; they are the static run's own
curves, not cut. Pit rows use each universe's pit window. microcap250's pit window
starts on 2021-10-29, and its pit cells say so ("from 2021-10-29"); every other
pit window equals the static one.

THE THREE MARKET-CAP BUCKETS (2026-10-16) follow microcap250. They are static only:
the supplier delivered no membership file for them, so every pit row reads "not
available: no membership file for this supplier bucket" and is never filled. Their
static figures carry the bias label in universes/registry.py (Universe.bias_note),
which the sheet prints in a NOTES block below each table.

AVERAGE DRAWDOWN is the mean, over every trading day in the window, of
equity / running peak - 1, so a day at a peak counts as 0.

EVERY CAGR AND MaxDD IS CHECKED against the published figure, rounded to two
decimals: static against v34_comparison.csv and v34_comparison_tax.csv, pit against
their _pit counterparts, the equal-weight basket against the static buy & hold row.
The NSE index has no published figure to check against. The script stops before
writing anything if one differs.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import arms.registry as arm_reg                                # noqa: E402
import config                                                  # noqa: E402
from config import read_table                                  # noqa: E402
from universes.registry import REGISTRY, check_tags            # noqa: E402

COLUMNS = ("smallcap250", "midcap150", "midcap100", "midcap50", "nifty500",
           "nifty200", "nifty100", "nifty50", "microcap250",
           "mcap1500to5000", "mcap5001to10000", "mcapover10000")
NO_PIT = "not available: no membership file for this supplier bucket"
ARMS = ("v1", "v2", "v3", "v4")
ROWS = ("pit, tax off: CAGR", "pit, tax on: CAGR",
        "static, tax off: CAGR", "static, tax on: CAGR",
        "NSE index: CAGR", "NSE index: MaxDD",
        "static, tax off: MaxDD", "static, tax off: average drawdown",
        "pit, tax off: MaxDD", "pit, tax off: average drawdown",
        "equal-weight basket (untaxed, daily rebalanced): CAGR",
        "equal-weight basket (untaxed, daily rebalanced): MaxDD")
BH_ROW = "buy & hold equal-weight"
OUT_CSV = ROOT / "diagnostics" / "survivorship_sheet_research.csv"
OUT_XLSX = ROOT / "diagnostics" / "survivorship_sheet_research.xlsx"


def cagr(eq):
    """engine_core.metrics' formula, in percent, unrounded."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return ((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100


def drawdown(eq):
    return eq / eq.cummax() - 1


def maxdd(eq):
    return drawdown(eq).min() * 100


def avgdd(eq):
    return drawdown(eq).mean() * 100


def published(M, sfx, label):
    """(CAGR%, MaxDD%) of one row of v34_comparison{sfx}.csv."""
    c = read_table(M / f"v34_comparison{sfx}.csv").set_index("Config")
    return float(c.loc[label, "CAGR%"]), float(c.loc[label, "MaxDD%"])


def nse_index(u):
    """The close series of u's own NSE index file over the backtest window."""
    d = read_table(u.index_file)
    d["date"] = pd.to_datetime(d["date"], dayfirst=True)
    c = d.sort_values("date").set_index("date")["close"]
    return c.loc[config.BT_START_DATE:config.BT_END_DATE]


def check(what, got, want):
    if round(got, 2) != want:
        raise SystemExit(f"MISMATCH {what}: computed {got:.4f}, published {want}. "
                         f"Nothing written.")


def universe_block(u):
    """{arm: {row: value}} for one universe, every figure checked."""
    M = Path(u.metrics_dir)
    from universes.registry import has_pit
    pit = has_pit(u)
    sfx = ("", "_tax", "_pit", "_tax_pit") if pit else ("", "_tax")
    eq = {s: read_table(M / f"v34_equity{s}.csv", parse_dates=["date"]).set_index("date")
          for s in sfx}
    pit_start = eq["_pit"].index[0] if pit else eq[""].index[0]
    static_start = eq[""].index[0]
    ref = eq[""]["buyhold"]
    check(f"{u.tag} equal-weight basket CAGR", cagr(ref), published(M, "", BH_ROW)[0])
    check(f"{u.tag} equal-weight basket MaxDD", maxdd(ref), published(M, "", BH_ROW)[1])
    nse = nse_index(u)
    out = {}
    for a in ARMS:
        col, lab = arm_reg.ARMS[a].equity_column, arm_reg.ARMS[a].label
        so, sn = eq[""][col], eq["_tax"][col]
        po, pn = (eq["_pit"][col], eq["_tax_pit"][col]) if pit else (None, None)
        for s, e in (("", so), ("_tax", sn), ("_pit", po), ("_tax_pit", pn)):
            if e is None:
                continue
            c, d = published(M, s, lab)
            check(f"{u.tag} {a} v34_comparison{s} CAGR", cagr(e), c)
            check(f"{u.tag} {a} v34_comparison{s} MaxDD", maxdd(e), d)
        if not pit:
            out[a] = {"pit, tax off: CAGR": NO_PIT, "pit, tax on: CAGR": NO_PIT,
                      "static, tax off: CAGR": cagr(so), "static, tax on: CAGR": cagr(sn),
                      "NSE index: CAGR": cagr(nse), "NSE index: MaxDD": maxdd(nse),
                      "static, tax off: MaxDD": maxdd(so),
                      "static, tax off: average drawdown": avgdd(so),
                      "pit, tax off: MaxDD": NO_PIT, "pit, tax off: average drawdown": NO_PIT,
                      "equal-weight basket (untaxed, daily rebalanced): CAGR": cagr(ref),
                      "equal-weight basket (untaxed, daily rebalanced): MaxDD": maxdd(ref)}
            continue
        out[a] = {"pit, tax off: CAGR": cagr(po), "pit, tax on: CAGR": cagr(pn),
                  "static, tax off: CAGR": cagr(so), "static, tax on: CAGR": cagr(sn),
                  "NSE index: CAGR": cagr(nse), "NSE index: MaxDD": maxdd(nse),
                  "static, tax off: MaxDD": maxdd(so),
                  "static, tax off: average drawdown": avgdd(so),
                  "pit, tax off: MaxDD": maxdd(po),
                  "pit, tax off: average drawdown": avgdd(po),
                  "equal-weight basket (untaxed, daily rebalanced): CAGR": cagr(ref),
                  "equal-weight basket (untaxed, daily rebalanced): MaxDD": maxdd(ref)}
    return out, pit_start != static_start, pit_start


def tables():
    """{arm: DataFrame rows x universes}, values as two-decimal strings."""
    blocks = {t: universe_block(REGISTRY[t]) for t in COLUMNS}
    out = {}
    for a in ARMS:
        t = pd.DataFrame(index=list(ROWS), columns=list(COLUMNS), dtype=object)
        for u, (vals, late, start) in blocks.items():
            for r in ROWS:
                v = vals[a][r]
                if isinstance(v, str):
                    t.loc[r, u] = v
                    continue
                s = f"{v:.2f}"
                if late and r.startswith("pit"):
                    s += f" (from {start.date()})"
                t.loc[r, u] = s
        out[a] = t
    return out


def main():
    import csv
    import io
    tabs = tables()
    # THE csv MODULE QUOTES. Two labels contain commas ("v1 invvol, 100% invested",
    # "equal-weight basket (untaxed, daily rebalanced)"), and a joined line would
    # split each into an extra column.
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    notes = [(t_, REGISTRY[t_].bias_note) for t_ in COLUMNS if REGISTRY[t_].bias_note]
    for a, t in tabs.items():
        w.writerow([f"arm {a} ({arm_reg.ARMS[a].label}), research profile"])
        w.writerow(["row"] + list(t.columns))
        for r in t.index:
            w.writerow([r] + [str(v) for v in t.loc[r]])
        w.writerow([])
    if notes:
        w.writerow(["NOTES"])
        for t_, n_ in notes:
            w.writerow([t_, n_])
        w.writerow([])
    # naming: axis-free -- one fixed export of the research profile, static and pit
    OUT_CSV.write_text(buf.getvalue())
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
        for a, t in tabs.items():
            # naming: axis-free -- one sheet per arm in the fixed export above
            t.to_excel(xw, sheet_name=a, index_label="row")
            if notes:
                # The bias label of each static-only universe, below its table.
                # naming: axis-free -- part of the same sheet
                pd.DataFrame({"row": [f"NOTE {t_}" for t_, _ in notes],
                              "text": [n_ for _, n_ in notes]}).to_excel(
                    xw, sheet_name=a, index=False, startrow=len(t) + 2)
    print(f"wrote {OUT_CSV.relative_to(ROOT)} and {OUT_XLSX.relative_to(ROOT)}: "
          f"{len(tabs)} arms x {len(ROWS)} rows x {len(COLUMNS)} universes, every "
          f"CAGR and MaxDD equal to the published figure")
    return 0


# ---------------------------------------------------------------------------
# pit-compare (was results/pit_compare.py, which last exists at 4a4b427)
# ---------------------------------------------------------------------------
# Its maxdd is ((eq - peak) / peak).min(), which can differ from this file's
# maxdd in the last bit, so it keeps its own copy as pit_compare_maxdd.
PIT_COMPARE_DOC = """
pit-compare -- static against point-in-time, cell by cell, over the pit window.

    ./venv/bin/python results/survivorship_sheet.py pit-compare OUT.csv [universe ...]

Read-only. For every registered universe (or those named), arms v1 to v4, both
profiles, cadence 20, reads the artefacts of the static runs and of the
--survivorship pit runs and writes one row per (universe, arm, profile):

    window_start, window_end      the pit window, from v34_params_tax_pit.json
    static_cagr_off, static_maxdd_off, static_cagr_on, static_maxdd_on
                                  the static run's curves (v34_equity[_tradeable][_tax]
                                  .csv) cut to the pit window
    pit_cagr_off, pit_maxdd_off, pit_cagr_on, pit_maxdd_on
                                  the pit run's curves (the same names with _pit)
    static_bh, pit_bh             the investable held-lots buy & hold, taxed, headline
                                  (nothing sold, so no tax): pit from
                                  BH_LOTS_<tag>[_tradeable]_tax_pit.csv; static from
                                  bh_held.held_lots on the static panel over the pit
                                  window
    static_gap, pit_gap           tax-on headline CAGR minus that buy & hold, the gap
                                  the README publishes
    beats_static_not_pit          static_gap > 0 and pit_gap <= 0

A STATIC FIGURE OVER A SHORTER WINDOW IS A CUT, NOT A RUN. Where the pit window starts
later than the static one (microcap250, 2021-10-29), the static curve is cut at the
pit start and rebased by the CAGR formula. It keeps the static run's holdings, its
rebalance dates and its tax paid before the cut. Where the windows are the same the
cut is the whole curve, and the script checks that every static figure equals the
published one (v34_comparison and BH_LOTS) before writing anything.

Figures use engine_core.metrics' formulas, unrounded; the CSV rounds to 4 decimals.
"""

PROFILES = ("research", "tradeable")


def pit_compare_maxdd(eq):
    return ((eq - eq.cummax()) / eq.cummax()).min() * 100


def curves(M, sfx):
    e = read_table(M / f"v34_equity{sfx}.csv", parse_dates=["date"]).set_index("date")
    return e


def bh_lots_headline(path):
    t = read_table(path)
    return float(t.loc[t["line"] == "bh_lots after tax", "cagr_full"].iloc[0])


def static_bh(u, w0, w1):
    """The static investable buy & hold over [w0, w1], from the static panel."""
    import audit_step
    import bh_held
    px, op, _, bd = audit_step.prices(u)
    bd = bd[(bd >= w0) & (bd <= w1)]
    return cagr(bh_held.held_lots(px, op, bd)["eq_headline"])


def rows_for(u):
    M = Path(u.metrics_dir)
    w = json.loads((M / "v34_params_tax_pit.json").read_text())
    w0, w1 = pd.Timestamp(w["window_start"]), pd.Timestamp(w["window_end"])
    same = pd.Timestamp(json.loads((M / "v34_params_tax.json").read_text())
                        ["window_start"]) == w0
    sbh = static_bh(u, w0, w1)
    out = []
    for prof in PROFILES:
        p = "_tradeable" if prof == "tradeable" else ""
        s_off, s_on = curves(M, p), curves(M, p + "_tax")
        q_off, q_on = curves(M, p + "_pit"), curves(M, p + "_tax_pit")
        pbh = bh_lots_headline(M / f"BH_LOTS_{u.tag}{p}_tax_pit.csv")
        if same:
            pub = bh_lots_headline(M / f"BH_LOTS_{u.tag}{p}_tax.csv")
            assert abs(sbh - pub) < 5e-5, f"{u.tag}: static buy & hold {sbh} != {pub}"
            comp = read_table(M / f"v34_comparison{p}.csv")
        for i, a in enumerate(ARMS):
            col = arm_reg.ARMS[a].equity_column
            so, sn = s_off[col].loc[w0:w1], s_on[col].loc[w0:w1]
            r = {"universe": u.tag, "arm": a, "profile": prof,
                 "window_start": str(w0.date()), "window_end": str(w1.date()),
                 "static_cagr_off": cagr(so), "static_maxdd_off": pit_compare_maxdd(so),
                 "static_cagr_on": cagr(sn), "static_maxdd_on": pit_compare_maxdd(sn),
                 "pit_cagr_off": cagr(q_off[col]), "pit_maxdd_off": pit_compare_maxdd(q_off[col]),
                 "pit_cagr_on": cagr(q_on[col]), "pit_maxdd_on": pit_compare_maxdd(q_on[col]),
                 "static_bh": sbh, "pit_bh": pbh}
            if same:
                assert round(r["static_cagr_off"], 2) == comp.iloc[i]["CAGR%"], \
                    f"{u.tag} {a} {prof}: cut CAGR differs from v34_comparison"
            r["static_gap"] = r["static_cagr_on"] - sbh
            r["pit_gap"] = r["pit_cagr_on"] - pbh
            r["beats_static_not_pit"] = bool(r["static_gap"] > 0 and r["pit_gap"] <= 0)
            out.append(r)
    return out


def pit_compare_main(argv):
    if not argv or argv[0].startswith("--"):
        print(PIT_COMPARE_DOC)
        return 2
    tags = check_tags(argv[1:]) if len(argv) > 1 else list(REGISTRY)
    rows = []
    for t in tags:
        rows += rows_for(REGISTRY[t])
    d = pd.DataFrame(rows).round(4)
    # naming: axis-free -- the output path is the caller's argument
    d.to_csv(argv[0], index=False)
    print(f"wrote {argv[0]}: {len(d)} rows over {len(tags)} universe(s)")
    return 0



if __name__ == "__main__":
    if sys.argv[1:2] == ["pit-compare"]:
        sys.exit(pit_compare_main(sys.argv[2:]))
    sys.exit(main())
