"""
survivorship_sheet.py -- static against point-in-time, one table per arm, research profile.

    ./venv/bin/python results/survivorship_sheet.py

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import arms.registry as arm_reg                                # noqa: E402
from config import read_table                                  # noqa: E402
from universes.registry import REGISTRY                        # noqa: E402

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
WINDOW = (pd.Timestamp("2019-01-01"), pd.Timestamp("2026-05-29"))
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
    """The close series of u's own NSE index file over WINDOW."""
    d = read_table(u.index_file)
    d["date"] = pd.to_datetime(d["date"], dayfirst=True)
    c = d.sort_values("date").set_index("date")["close"]
    return c.loc[WINDOW[0]:WINDOW[1]]


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


if __name__ == "__main__":
    sys.exit(main())
