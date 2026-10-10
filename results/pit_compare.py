"""
pit_compare.py -- static against point-in-time, cell by cell, over the pit window.

    ./venv/bin/python results/pit_compare.py OUT.csv [universe ...]

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
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import arms.registry as arm_reg                                # noqa: E402
from config import read_table                                  # noqa: E402
from universes.registry import REGISTRY, check_tags            # noqa: E402

PROFILES = ("research", "tradeable")
ARMS = ("v1", "v2", "v3", "v4")


def cagr(eq):
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return ((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100


def maxdd(eq):
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
                 "static_cagr_off": cagr(so), "static_maxdd_off": maxdd(so),
                 "static_cagr_on": cagr(sn), "static_maxdd_on": maxdd(sn),
                 "pit_cagr_off": cagr(q_off[col]), "pit_maxdd_off": maxdd(q_off[col]),
                 "pit_cagr_on": cagr(q_on[col]), "pit_maxdd_on": maxdd(q_on[col]),
                 "static_bh": sbh, "pit_bh": pbh}
            if same:
                assert round(r["static_cagr_off"], 2) == comp.iloc[i]["CAGR%"], \
                    f"{u.tag} {a} {prof}: cut CAGR differs from v34_comparison"
            r["static_gap"] = r["static_cagr_on"] - sbh
            r["pit_gap"] = r["pit_cagr_on"] - pbh
            r["beats_static_not_pit"] = bool(r["static_gap"] > 0 and r["pit_gap"] <= 0)
            out.append(r)
    return out


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
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
    sys.exit(main(sys.argv[1:]))
