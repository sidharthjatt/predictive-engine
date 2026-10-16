"""
readme_tax_tables.py -- write README.md's current tax-on tables from the run artefacts.

    ./venv/bin/python tools/readme_tax_tables.py           # rewrite the block in README.md
    ./venv/bin/python tools/readme_tax_tables.py --print   # print it, write nothing

The block sits between the two marker lines below and is replaced whole; nothing
else in README.md is touched. Every figure is read from the files a run writes, for
every registered universe and arm v1-v4, cadence 20, under the four tax-on settings
(static and pit, research and tradeable):

    tax off CAGR, MaxDD        v34_comparison<sfx>.csv of the matching tax-off run
    tax on CAGR, MaxDD, Sharpe v34_comparison<sfx>_tax<pit>.csv, headline (nothing
                               sold at the end)
    sold on the last day       BH_LOTS_<tag>_tax<pit>.csv, "<arm> sold on the last day"
    investable buy & hold      BH_LOTS, "bh_lots after tax": whole shares of every
                               name bought at the first open and held, taxed
    gap                        tax-on headline CAGR minus that buy & hold

A missing file is written as "not on disk", never filled in.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import arms.registry as arm_reg
from config import read_table
from universes.registry import REGISTRY, has_pit

BEGIN = "<!-- tax-on tables: written by tools/readme_tax_tables.py; do not edit by hand -->"
END = "<!-- end of tax-on tables -->"
SETTINGS = (("static", "research", "", ""), ("static", "tradeable", "_tradeable", ""),
            ("pit", "research", "", "_pit"), ("pit", "tradeable", "_tradeable", "_pit"))


def row(metrics_dir, tag, arm, prof, pit):
    a = arm_reg.ARMS[arm]
    M = Path(metrics_dir)
    off_f = M / f"v34_comparison{prof}{pit}.csv"
    on_f = M / f"v34_comparison{prof}_tax{pit}.csv"
    bh_tag = tag if arm == "v2" else f"{tag}_{arm}"
    bh_f = M / f"BH_LOTS_{bh_tag}{prof}_tax{pit}.csv"
    cells = []
    if off_f.exists():
        r = read_table(off_f).set_index("Config").loc[a.label]
        cells += [f"{float(r['CAGR%']):.2f}", f"{float(r['MaxDD%']):.2f}"]
    else:
        cells += ["not on disk"] * 2
    if on_f.exists():
        r = read_table(on_f).set_index("Config").loc[a.label]
        on_cagr = float(r["CAGR%"])
        cells += [f"{on_cagr:.2f}", f"{float(r['MaxDD%']):.2f}", f"{float(r['Sharpe']):.2f}"]
    else:
        on_cagr = None
        cells += ["not on disk"] * 3
    if bh_f.exists():
        b = read_table(bh_f).set_index("line")
        last = float(b.loc[f"{arm} sold on the last day", "cagr_full"])
        inv = float(b.loc["bh_lots after tax", "cagr_full"])
        cells += [f"{last:.2f}", f"{inv:.2f}",
                  f"{on_cagr - inv:+.2f}" if on_cagr is not None else "not on disk"]
    else:
        cells += ["not on disk"] * 3
    return cells


def block():
    L = [BEGIN, "",
         "### Republished 2026-10-14 on the corrected tax ledger: every tax-on figure", "",
         "The tax ledger now follows the Income-tax Act in four places it did not before: "
         "the 4% cess, a short-term loss set off against long-term gains within a year, "
         "loss carry-forward for 8 years, and a holding period of more than twelve "
         "calendar months (KNOWN_ISSUES.md, \"The tax rules since 2026-10-14\"). Every "
         "tax-on figure below is on those rules; every tax-off figure is unchanged. Old "
         "against new for every cell is in diagnostics/tax_ledger_fix_20261014.csv and "
         "experiments/EXPERIMENTS.md. Cadence 20, one run per cell (n=1). The investable "
         "buy & hold is whole shares of every name bought at the first open and held, "
         "taxed; gap is the tax-on headline CAGR minus it. microcap250's pit window starts "
         "2021-10-29.", ""]
    head = ("| universe | arm | tax off: CAGR% | MaxDD% | tax on, headline: CAGR% | MaxDD% "
            "| Sharpe | tax on, sold on the last day: CAGR% | investable buy & hold, taxed: "
            "CAGR% | gap |")
    for surv, profile, prof, pit in SETTINGS:
        L += [f"**{surv}, {profile} profile**", "", head, "|---|---|" + "---:|" * 8]
        for tag, u in REGISTRY.items():
            if pit and not has_pit(u):
                # A STATIC-ONLY UNIVERSE HAS NO PIT ROW, and says so rather than
                # leaving a gap or a guess (registry.has_pit).
                L.append(f"| {tag} | v1-v4 | not available: no membership file for this "
                         f"supplier bucket |" + " |" * 7)
                continue
            for arm in arm_reg.ARMS:
                L.append("| " + " | ".join([tag, arm] + row(u.metrics_dir, tag, arm, prof, pit))
                         + " |")
        L.append("")
    L.append(END)
    return "\n".join(L)


def main():
    b = block()
    if "--print" in sys.argv:
        print(b)
        return 0
    readme = ROOT / "README.md"
    s = readme.read_text()
    if BEGIN in s:
        i, j = s.index(BEGIN), s.index(END) + len(END)
        s = s[:i] + b + s[j:]
    else:
        anchor = "### Republished 2026-10-10 on the supplier's new data delivery"
        if anchor not in s:
            raise SystemExit(f"README.md has neither the marker block nor the anchor {anchor!r}")
        i = s.index(anchor)
        s = s[:i] + b + "\n\n" + s[i:]
    # naming: axis-free -- README.md is one file; the block covers every setting
    readme.write_text(s)
    print(f"README.md: tax-on tables written ({b.count(chr(10)) + 1} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
