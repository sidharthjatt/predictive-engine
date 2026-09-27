"""
selection_margin.py -- how close the scores are at the selection boundary, per cell and rebalance.

    ./venv/bin/python results/selection_margin.py OUT.csv [--root DIR --panels DIR]

Read-only. For every registered universe and arm, cadence 20, research profile, tax
off, at every decision date in daily_decisions_<tag>.csv:

    scored      the names with a score and a price that day, from the universe's
                score panel (cache/<tag>/v_<tag>_expanding.parquet)
    spread      max minus min of the day's scores over the scored names
    gap_8_9     score of rank 8 minus score of rank 9: the entry boundary TOP_N
                sets. It depends on the scores only, so it is the same for all four
                arms of a universe.
    held_gap    lowest score among the names held after the rebalance minus the
                highest score among scored names not held. Held means in
                daily_holdings_<tag>.csv on the first session after the decision.
                Negative when a held name sits below a name not held: a name kept
                inside the BUFFER, or a top-8 buy skipped for lack of cash.
    *_share     the same gap divided by the day's spread

--root points at a directory of results_<tag>/ folders and --panels at one of
<tag>/ folders holding the score parquet, for a copy taken before a rebuild; the
defaults are the live metrics directories and cache/.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import audit_step                                              # noqa: E402
from arms.registry import ARMS                                 # noqa: E402
from config import read_table                                  # noqa: E402
from engine_core import TOP_N                                  # noqa: E402
from universes.registry import gated                           # noqa: E402


def cell_rows(u, arm, mdir, panel):
    tag = audit_step.artefact_tag(u, arm)
    dec = read_table(mdir / f"daily_decisions_{tag}.csv", parse_dates=["decided_on"])
    hold = read_table(mdir / f"daily_holdings_{tag}.csv", parse_dates=["date"])
    held = {d: set(g["symbol"]) for d, g in hold.groupby("date")}
    hdates = sorted(held)
    sc = panel.pivot_table(index="date", columns="symbol", values="score")
    px = panel.pivot_table(index="date", columns="symbol", values="close").ffill()
    out = []
    for d in dec["decided_on"]:
        s = sc.loc[d].dropna()
        s = s[[k for k in s.index if pd.notna(px.loc[d].get(k))]].sort_values(ascending=False)
        nxt = next((x for x in hdates if x > d), None)
        if len(s) <= TOP_N or nxt is None:
            continue
        h = held[nxt] & set(s.index)
        spread = float(s.iloc[0] - s.iloc[-1])
        g89 = float(s.iloc[TOP_N - 1] - s.iloc[TOP_N])
        not_h = s[[k for k in s.index if k not in h]]
        hg = float(s[list(h)].min() - not_h.max()) if h and len(not_h) else float("nan")
        out.append({"universe": u.tag, "arm": arm, "decided_on": d.date(), "scored": len(s),
                    "spread": spread, "gap_8_9": g89, "gap_8_9_share": g89 / spread,
                    "held_gap": hg, "held_gap_share": hg / spread, "n_held": len(h)})
    return out


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else None
    panels = Path(argv[argv.index("--panels") + 1]) if "--panels" in argv else None
    rows = []
    for u in gated():
        mdir = Path(u.metrics_dir) if root is None else root / f"results_{u.tag}"
        pf = Path(u.score_cache) if panels is None else panels / u.tag / Path(u.score_cache).name
        panel = read_table(pf, parse_dates=["date"])
        for arm in ARMS:
            rows += cell_rows(u, arm, mdir, panel)
    d = pd.DataFrame(rows)
    d.to_csv(argv[0], index=False)
    print(f"wrote {argv[0]}: {len(d)} rebalance rows over "
          f"{d.groupby(['universe', 'arm']).ngroups} cells")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
