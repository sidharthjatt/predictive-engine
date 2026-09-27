"""
cell_table.py -- one row per (universe, arm, profile) from the tax-on artefacts.

    ./venv/bin/python results/cell_table.py OUT.csv [--root DIR]

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import arms.registry as arm_reg                                # noqa: E402
from config import read_table                                  # noqa: E402
from universes.registry import gated                           # noqa: E402

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


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    root = argv[argv.index("--root") + 1] if "--root" in argv else None
    d = rows(root)
    d.to_csv(argv[0], index=False)
    print(f"wrote {argv[0]}: {len(d)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
