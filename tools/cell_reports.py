"""
cell_reports.py -- five reports over published cells, one subcommand each.

    ./venv/bin/python tools/cell_reports.py tax-on-all-arms
    ./venv/bin/python tools/cell_reports.py tradeable-tax-grid
    ./venv/bin/python tools/cell_reports.py tax-fix-old-new --old DIR
    ./venv/bin/python tools/cell_reports.py cell-table OUT.csv [--root DIR]
    ./venv/bin/python tools/cell_reports.py cell-compare OLD.csv NEW.csv OUT.csv

Merged on 2026-10-18 from results/tax_on_all_arms.py, results/tradeable_tax_grid.py,
tools/tax_fix_old_new.py, results/cell_table.py and results/cell_compare.py, which
last exist at commit 4a4b427. Each subcommand takes the old script's arguments,
writes the same files in the same format and returns the same exit code. Each old
docstring is kept below as the *_DOC constant of its section.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import arms.registry as arm_reg                                # noqa: E402
from config import read_table                                  # noqa: E402
from universes.registry import REGISTRY, gated                 # noqa: E402


def cagr(eq):
    """engine_core.metrics' CAGR, in percent, at full precision."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100)


# ---------------------------------------------------------------------------
# tax-on-all-arms (was results/tax_on_all_arms.py)
# ---------------------------------------------------------------------------
TAX_ON_ALL_ARMS_DOC = """
tax-on-all-arms -- every arm's tax-on headline CAGR against the investable taxed buy & hold.

    ./venv/bin/python tools/cell_reports.py tax-on-all-arms

Writes diagnostics/tax_on_all_arms.csv: 4 arms x 8 universes, research profile,
cadence 20, tax on, headline (nothing sold at the end, the last partial financial
year settled on the final session).

    arm_cagr   from that arm's column of results_<u>/metrics/v34_equity_tax.csv,
               engine_core.metrics' formula, rounded to 4 decimals -- the
               precision BH_LOTS_*.csv carries.
    bh_cagr    the investable taxed buy & hold headline, "bh_lots after tax" in
               BH_LOTS_<tag>_tax.csv. The basket is the same for every arm; the
               script checks that all four arms' BH_LOTS files agree on it.
    gap        arm_cagr - bh_cagr, from the unrounded arm CAGR.

CROSS-CHECK, NOT A SECOND SOURCE. Each arm's CAGR is also on the "<arm> after tax"
line of its own BH_LOTS file, from bh_lots_after_tax's separate taxed backtest.
The two must agree to 4 decimals, and the script exits 1 if any cell does not.
"""

TAX_ON_ALL_ARMS_OUT = ROOT / "diagnostics" / "tax_on_all_arms.csv"


def bh_lots(u, arm):
    tag = u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}"
    t = read_table(Path(u.metrics_dir) / f"BH_LOTS_{tag}_tax.csv").set_index("line")
    return t


def tax_on_all_arms_main():
    rows, bad = [], []
    for u in gated():
        eq = read_table(Path(u.metrics_dir) / "v34_equity_tax.csv",
                        parse_dates=["date"]).set_index("date")
        bh_seen = set()
        for arm in arm_reg.ARMS.values():
            c = cagr(eq[arm.equity_column])
            t = bh_lots(u, arm)
            bh = float(t.loc["bh_lots after tax", "cagr_full"])
            bh_seen.add(bh)
            other = float(t.loc[f"{arm.name} after tax", "cagr_full"])
            if round(c, 4) != other:
                bad.append(f"{u.tag} {arm.name}: v34_equity_tax {c:.4f}, BH_LOTS {other:.4f}")
            rows.append({"universe": u.tag, "arm": arm.name, "label": arm.label,
                         "arm_cagr": round(c, 4), "bh_cagr": bh,
                         "gap": round(c - bh, 4),
                         "arm_final_equity": round(float(eq[arm.equity_column].iloc[-1]), 2),
                         "arm_tax_paid": float(t.loc[f"{arm.name} after tax", "tax_paid"])})
        if len(bh_seen) != 1:
            bad.append(f"{u.tag}: the four BH_LOTS files disagree on the buy & hold: {sorted(bh_seen)}")
    df = pd.DataFrame(rows)
    # naming: axis-free -- a record fixed to research, cadence 20, tax on; it
    # varies over no published axis
    df.to_csv(TAX_ON_ALL_ARMS_OUT, index=False, quoting=csv.QUOTE_MINIMAL)
    print(df.to_string(index=False))
    if bad:
        print("\nCROSS-CHECK FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"\n{len(df)} cells; every arm CAGR agrees with its BH_LOTS line to 4 decimals. -> {TAX_ON_ALL_ARMS_OUT}")
    return 0


# ---------------------------------------------------------------------------
# tradeable-tax-grid (was results/tradeable_tax_grid.py)
# ---------------------------------------------------------------------------
TRADEABLE_TAX_GRID_DOC = """
tradeable-tax-grid -- research against tradeable, tax on, all 32 cells.

    ./venv/bin/python tools/cell_reports.py tradeable-tax-grid

Reads the artefacts of two pipeline runs at cadence 20, tax on:
    research   run.py --universe all --arm all --tax on
    tradeable  run.py --universe all --arm all --tax on --profile tradeable
and writes diagnostics/tradeable_tax_all_arms.csv, one row per (universe, arm).

    research_cagr, tradeable_cagr   that arm's column of v34_equity_tax.csv and
                                    v34_equity_tradeable_tax.csv, full precision,
                                    rounded to 4 decimals
    diff                            tradeable - research
    cap_binds                       rows with reason "participation cap" in the
                                    tradeable run's own daily_skipped artefact
    bh_research, bh_tradeable       "bh_lots after tax" from each profile's
                                    BH_LOTS file; the basket takes no cap, so the
                                    two must be equal, and the script checks it
    gap_research, gap_tradeable     arm minus the investable taxed buy & hold

The tradeable profile is UNGATED (profiles.UNGATED_NOTICE): nothing replays what
the port does under it. These are engine figures, not certified ones.
"""

TRADEABLE_TAX_GRID_OUT = ROOT / "diagnostics" / "tradeable_tax_all_arms.csv"


def tag(u, arm, sfx):
    return (u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}") + sfx


def tradeable_tax_grid_main():
    rows, bad = [], []
    for u in gated():
        M = Path(u.metrics_dir)
        eq_r = read_table(M / "v34_equity_tax.csv", parse_dates=["date"]).set_index("date")
        eq_t = read_table(M / "v34_equity_tradeable_tax.csv", parse_dates=["date"]).set_index("date")
        for arm in arm_reg.ARMS.values():
            r = cagr(eq_r[arm.equity_column])
            t = cagr(eq_t[arm.equity_column])
            bh_r = float(read_table(M / f"BH_LOTS_{tag(u, arm, '_tax')}.csv")
                         .set_index("line").loc["bh_lots after tax", "cagr_full"])
            bh_t = float(read_table(M / f"BH_LOTS_{tag(u, arm, '_tradeable_tax')}.csv")
                         .set_index("line").loc["bh_lots after tax", "cagr_full"])
            if bh_r != bh_t:
                bad.append(f"{u.tag} {arm.name}: buy & hold research {bh_r} tradeable {bh_t}")
            sk = read_table(M / f"daily_skipped_{tag(u, arm, '_tradeable_tax')}.csv")
            binds = int((sk["reason"] == "participation cap").sum()) if len(sk) else 0
            rows.append({"universe": u.tag, "arm": arm.name,
                         "research_cagr": round(r, 4), "tradeable_cagr": round(t, 4),
                         "diff": round(t - r, 4), "cap_binds": binds,
                         "bh_cagr": bh_r,
                         "gap_research": round(r - bh_r, 4),
                         "gap_tradeable": round(t - bh_t, 4)})
    df = pd.DataFrame(rows)
    # naming: axis-free -- a record of one fixed comparison (cadence 20, tax on,
    # research against tradeable); it varies over no published axis
    df.to_csv(TRADEABLE_TAX_GRID_OUT, index=False)
    print(df.to_string(index=False))
    if bad:
        print("\nCHECK FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"\n{len(df)} cells -> {TRADEABLE_TAX_GRID_OUT}")
    return 0


# ---------------------------------------------------------------------------
# tax-fix-old-new (was tools/tax_fix_old_new.py)
# ---------------------------------------------------------------------------
TAX_FIX_OLD_NEW_DOC = """
tax-fix-old-new -- every tax-on cell before and after the tax-ledger fix of 2026-10-14.

    ./venv/bin/python tools/cell_reports.py tax-fix-old-new --old DIR

DIR holds results_<tag>/metrics/ copies of the tax-on artefacts taken before the
rerun. The new figures are the live metrics directories. For every registered
universe, arm v1-v4, cadence 20, static and pit, research and tradeable, tax on:

    total_tax     sum of total_tax in COST_TAX_YEARS_<tag>.csv
    cagr, maxdd, final_equity   the arm's row of v34_comparison<sfx>.csv

Writes diagnostics/tax_ledger_fix_20261014.csv and prints the summary.
"""

SETTINGS = (("static", "research", "_tax"), ("static", "tradeable", "_tradeable_tax"),
            ("pit", "research", "_tax_pit"), ("pit", "tradeable", "_tradeable_tax_pit"))

TAX_FIX_OLD_NEW_OUT = ROOT / "diagnostics" / "tax_ledger_fix_20261014.csv"


def figures(M, tag, arm, sfx):
    a = arm_reg.ARMS[arm]
    ct = tag if arm == "v2" else f"{tag}_{arm}"
    years = read_table(M / f"COST_TAX_YEARS_{ct}{sfx}.csv")
    c = read_table(M / f"v34_comparison{sfx}.csv").set_index("Config").loc[a.label]
    return {"total_tax": float(years["total_tax"].sum()), "cagr": float(c["CAGR%"]),
            "maxdd": float(c["MaxDD%"]), "final_equity": float(c["FinalEquity"])}


def tax_fix_old_new_main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    old_root = Path(ap.parse_args(argv).old)
    rows = []
    for tag, u in REGISTRY.items():
        new_M = Path(u.metrics_dir)
        old_M = old_root / new_M.relative_to(ROOT)
        for surv, profile, sfx in SETTINGS:
            for arm in arm_reg.ARMS:
                o, n = figures(old_M, tag, arm, sfx), figures(new_M, tag, arm, sfx)
                rows.append({"universe": tag, "arm": arm, "survivorship": surv,
                             "profile": profile,
                             **{f"{k}_old": o[k] for k in o}, **{f"{k}_new": n[k] for k in n},
                             "tax_change": n["total_tax"] - o["total_tax"],
                             "cagr_change": n["cagr"] - o["cagr"],
                             "maxdd_change": n["maxdd"] - o["maxdd"],
                             "final_equity_change": n["final_equity"] - o["final_equity"]})
    df = pd.DataFrame(rows)
    # naming: axis-free -- one dated comparison over every tax-on cell, the settings are columns
    df.to_csv(TAX_FIX_OLD_NEW_OUT, index=False, float_format="%.6f")
    print(f"wrote {TAX_FIX_OLD_NEW_OUT.relative_to(ROOT)}: {len(df)} cells")
    for k in ("tax_change", "cagr_change", "maxdd_change", "final_equity_change"):
        print(f"  {k:<20} min {df[k].min():>14,.2f}  median {df[k].median():>14,.2f}  "
              f"max {df[k].max():>14,.2f}")
    return 0


# ---------------------------------------------------------------------------
# cell-table (was results/cell_table.py)
# ---------------------------------------------------------------------------
CELL_TABLE_DOC = """
cell-table -- one row per (universe, arm, profile) from the tax-on artefacts.

    ./venv/bin/python tools/cell_reports.py cell-table OUT.csv [--root DIR]

Reads, for every registered universe, arm and profile (research, tradeable), cadence
20, the BH_LOTS file a tax-on run writes (bh_lots_after_tax.py) and the two
v34_comparison files (tax off and tax on). --root points at a directory holding
results_<tag>/ folders of metrics, for a copy taken before a rebuild; the default
is each universe's live metrics directory.

    cagr_off                 "<arm> before tax": the arm with tax off
    cagr_on                  "<arm> after tax": tax on, headline
    cagr_last_day            "<arm> sold on the last day"
    bh_reference             "bh published": the untaxed daily-rebalanced index
    bh_investable            "bh_lots after tax": held lots, taxed, headline
    bh_investable_last_day   "bh_lots sold on the last day"
    gap_on                   cagr_on - bh_investable, as the BH_LOTS file states it
    gap_last_day             cagr_last_day - bh_investable_last_day
    maxdd_off, sharpe_off, maxdd_on, sharpe_on   from v34_comparison

The tax-off MaxDD and Sharpe come from the tax-off run's v34_comparison file, so
they are empty for a profile whose tax-off run was not made.
"""

PROFILES = ("research", "tradeable")


def _cmp(M, sfx, label):
    p = M / f"v34_comparison{sfx}.csv"
    if not p.exists():
        return None, None
    t = read_table(p).set_index("Config")
    if label not in t.index:
        return None, None
    return float(t.loc[label, "MaxDD%"]), float(t.loc[label, "Sharpe"])


def rows(root=None):
    out = []
    for u in gated():
        M = Path(u.metrics_dir) if root is None else Path(root) / f"results_{u.tag}"
        for prof in PROFILES:
            ps = "" if prof == "research" else "_tradeable"
            for arm in arm_reg.ARMS.values():
                tag = u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}"
                t = read_table(M / f"BH_LOTS_{tag}{ps}_tax.csv").set_index("line")
                c = t["cagr_full"]
                a = arm.name
                dd_off, sh_off = _cmp(M, ps, arm.label)
                dd_on, sh_on = _cmp(M, f"{ps}_tax", arm.label)
                out.append({
                    "universe": u.tag, "arm": a, "profile": prof,
                    "cagr_off": c[f"{a} before tax"], "cagr_on": c[f"{a} after tax"],
                    "cagr_last_day": c[f"{a} sold on the last day"],
                    "bh_reference": c["bh published"],
                    "bh_investable": c["bh_lots after tax"],
                    "bh_investable_last_day": c["bh_lots sold on the last day"],
                    "gap_on": c["gap_after_tax"],
                    "gap_last_day": c["gap_sold_on_the_last_day"],
                    "maxdd_off": dd_off, "sharpe_off": sh_off,
                    "maxdd_on": dd_on, "sharpe_on": sh_on,
                })
    return pd.DataFrame(out)


def cell_table_main(argv):
    if not argv or argv[0].startswith("--"):
        print(CELL_TABLE_DOC)
        return 2
    root = argv[argv.index("--root") + 1] if "--root" in argv else None
    d = rows(root)
    d.to_csv(argv[0], index=False)
    print(f"wrote {argv[0]}: {len(d)} rows")
    return 0


# ---------------------------------------------------------------------------
# cell-compare (was results/cell_compare.py)
# ---------------------------------------------------------------------------
CELL_COMPARE_DOC = """
cell-compare -- old against new for every cell, from two cell-table CSVs.

    ./venv/bin/python tools/cell_reports.py cell-compare OLD.csv NEW.csv OUT.csv

One row per (universe, arm, profile): each CAGR and gap column from both files and
their difference, plus sign_change_on and sign_change_last_day, True where the gap
against the investable taxed buy & hold has a different sign old and new.
"""

KEY = ["universe", "arm", "profile"]

COLS = ["cagr_off", "cagr_on", "cagr_last_day", "bh_reference", "bh_investable",
        "bh_investable_last_day", "gap_on", "gap_last_day"]


def compare(old, new):
    o = old.set_index(KEY)[COLS]
    n = new.set_index(KEY)[COLS]
    if set(o.index) != set(n.index):
        raise SystemExit("the two tables do not hold the same cells")
    n = n.loc[o.index]
    out = pd.DataFrame(index=o.index)
    for c in COLS:
        out[f"{c}_old"] = o[c]
        out[f"{c}_new"] = n[c]
        out[f"{c}_diff"] = (n[c] - o[c]).round(4)
    for g in ("gap_on", "gap_last_day"):
        out[f"sign_change_{g[4:]}"] = (o[g] > 0) != (n[g] > 0)
    return out.reset_index()


def cell_compare_main(argv):
    if len(argv) != 3:
        print(CELL_COMPARE_DOC)
        return 2
    d = compare(read_table(argv[0]), read_table(argv[1]))
    d.to_csv(argv[2], index=False)
    print(f"wrote {argv[2]}: {len(d)} cells, gap sign changes: "
          f"headline {int(d.sign_change_on.sum())}, last day {int(d.sign_change_last_day.sum())}")
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
COMMANDS = {
    "tax-on-all-arms": lambda argv: tax_on_all_arms_main(),
    "tradeable-tax-grid": lambda argv: tradeable_tax_grid_main(),
    "tax-fix-old-new": tax_fix_old_new_main,
    "cell-table": cell_table_main,
    "cell-compare": cell_compare_main,
}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
