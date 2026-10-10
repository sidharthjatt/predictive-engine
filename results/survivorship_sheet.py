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
    reference index: CAGR              the buyhold column of v34_equity.csv
    reference index: MaxDD             the same
    static, tax off: MaxDD             v34_equity.csv
    static, tax off: average drawdown  the same
    pit, tax off: MaxDD                v34_equity_pit.csv
    pit, tax off: average drawdown     the same

THE REFERENCE INDEX is the README's "buy & hold, reference (untaxed,
daily-rebalanced index)": the costless equal-weight basket of the static universe,
the "buy & hold equal-weight" row of v34_comparison.csv. It is not the cap-weighted
published index.

WINDOWS. Static and reference rows use the published static window, 2019-01-01 to
2026-05-29, for every universe, microcap250 included; they are the static run's own
curves, not cut. Pit rows use each universe's pit window. microcap250's pit window
starts on 2021-10-29, and its pit cells say so ("from 2021-10-29"); every other
pit window equals the static one.

AVERAGE DRAWDOWN is the mean, over every trading day in the window, of
equity / running peak - 1, so a day at a peak counts as 0.

EVERY CAGR AND MaxDD IS CHECKED against the published figure, rounded to two
decimals: static against v34_comparison.csv and v34_comparison_tax.csv, pit against
their _pit counterparts, the reference index against the static buy & hold row. The
script stops before writing anything if one differs.
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
           "nifty200", "nifty100", "nifty50", "microcap250")
ARMS = ("v1", "v2", "v3", "v4")
ROWS = ("pit, tax off: CAGR", "pit, tax on: CAGR",
        "static, tax off: CAGR", "static, tax on: CAGR",
        "reference index: CAGR", "reference index: MaxDD",
        "static, tax off: MaxDD", "static, tax off: average drawdown",
        "pit, tax off: MaxDD", "pit, tax off: average drawdown")
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


def check(what, got, want):
    if round(got, 2) != want:
        raise SystemExit(f"MISMATCH {what}: computed {got:.4f}, published {want}. "
                         f"Nothing written.")


def universe_block(u):
    """{arm: {row: value}} for one universe, every figure checked."""
    M = Path(u.metrics_dir)
    eq = {s: read_table(M / f"v34_equity{s}.csv", parse_dates=["date"]).set_index("date")
          for s in ("", "_tax", "_pit", "_tax_pit")}
    pit_start = eq["_pit"].index[0]
    static_start = eq[""].index[0]
    ref = eq[""]["buyhold"]
    check(f"{u.tag} reference CAGR", cagr(ref), published(M, "", BH_ROW)[0])
    check(f"{u.tag} reference MaxDD", maxdd(ref), published(M, "", BH_ROW)[1])
    out = {}
    for a in ARMS:
        col, lab = arm_reg.ARMS[a].equity_column, arm_reg.ARMS[a].label
        so, sn, po, pn = (eq[s][col] for s in ("", "_tax", "_pit", "_tax_pit"))
        for s, e in (("", so), ("_tax", sn), ("_pit", po), ("_tax_pit", pn)):
            c, d = published(M, s, lab)
            check(f"{u.tag} {a} v34_comparison{s} CAGR", cagr(e), c)
            check(f"{u.tag} {a} v34_comparison{s} MaxDD", maxdd(e), d)
        out[a] = {"pit, tax off: CAGR": cagr(po), "pit, tax on: CAGR": cagr(pn),
                  "static, tax off: CAGR": cagr(so), "static, tax on: CAGR": cagr(sn),
                  "reference index: CAGR": cagr(ref), "reference index: MaxDD": maxdd(ref),
                  "static, tax off: MaxDD": maxdd(so),
                  "static, tax off: average drawdown": avgdd(so),
                  "pit, tax off: MaxDD": maxdd(po),
                  "pit, tax off: average drawdown": avgdd(po)}
    return out, pit_start != static_start, pit_start


def tables():
    """{arm: DataFrame rows x universes}, values as two-decimal strings."""
    blocks = {t: universe_block(REGISTRY[t]) for t in COLUMNS}
    out = {}
    for a in ARMS:
        t = pd.DataFrame(index=list(ROWS), columns=list(COLUMNS), dtype=object)
        for u, (vals, late, start) in blocks.items():
            for r in ROWS:
                s = f"{vals[a][r]:.2f}"
                if late and r.startswith("pit"):
                    s += f" (from {start.date()})"
                t.loc[r, u] = s
        out[a] = t
    return out


def main():
    tabs = tables()
    lines = []
    for a, t in tabs.items():
        lines.append(f"arm {a} ({arm_reg.ARMS[a].label}), research profile")
        lines.append(",".join(["row"] + list(t.columns)))
        lines += [",".join([r] + [str(v) for v in t.loc[r]]) for r in t.index]
        lines.append("")
    # naming: axis-free -- one fixed export of the research profile, static and pit
    OUT_CSV.write_text("\n".join(lines))
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
        for a, t in tabs.items():
            # naming: axis-free -- one sheet per arm in the fixed export above
            t.to_excel(xw, sheet_name=a, index_label="row")
    print(f"wrote {OUT_CSV.relative_to(ROOT)} and {OUT_XLSX.relative_to(ROOT)}: "
          f"{len(tabs)} arms x {len(ROWS)} rows x {len(COLUMNS)} universes, every "
          f"CAGR and MaxDD equal to the published figure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
