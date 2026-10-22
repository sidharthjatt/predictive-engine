"""
pit_noise_band.py -- seed-resampling spread for pit, tradeable, tax-on cells.

    ./venv/bin/python tools/pit_noise_band.py fit   --cells nifty200:v3,nifty200:v1,midcap100:v1
    ./venv/bin/python tools/pit_noise_band.py band  --cells nifty200:v3,nifty200:v1,midcap100:v1

THE METHOD IS experiments/DRAWDOWN_STOP_BAND.csv's (results/drawdown_stop_band.py),
applied to one cell at a time instead of to a stop-minus-parent difference:

  fit    20 seeds (the 10 production seeds and 1000-1009) are fitted once on the
         universe's PIT raw panel by results/seed_band_fit.fit_universe, unchanged,
         after universes.registry.use_pit swaps the registry row. The store goes to
         cache/<tag>/pit/. The production seeds' mean must reproduce the cached pit
         score panel bit for bit, or nothing is stored.
  band   50 distinct 10-seed subsets of the 20, drawn with numpy generator seed
         20261002 (drawdown_stop_band.subsets, the same 50). Each subset's panel is
         the pit score panel with the score replaced by the mean of that subset's
         seed columns. The cell's arm runs on it at cadence 20, tradeable profile,
         tax on, pit membership with forced index exits, exactly as the engine runs
         it (inputs built as results/engine_v2_final.py builds them).

SANITY CHECK FIRST. Before any draw, the production subset (seeds 0-9) must
reproduce the published equity curve of the cell, v34_equity_tradeable_tax_pit.csv,
exactly. If it does not, nothing is drawn.

The basket is the published pit equal-weight basket of the same file; it does not
depend on the seeds, so CAGR minus basket moves only with the cell's CAGR.

Writes diagnostics/pit_noise_band_<date>.csv: one row per (cell, subset).
"""
import argparse
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd

import config
from config import read_table

REBAL = 20


def select_pit(tag):
    """The selections a `run.py --survivorship pit --profile tradeable --tax on`
    run makes, and the universe's membership loaded as run._pit_setup loads it."""
    import survivorship_axis, profiles, tax
    import survivorship as sv
    import engine_core as ec
    from universes.registry import REGISTRY, use_pit
    survivorship_axis.set_selection("pit")
    profiles.set_selection("tradeable")
    tax.set_selection(True)
    use_pit([tag])
    u = REGISTRY[tag]
    m = sv.load(u.membership_file, index_name=u.tag, price_dir=u.raw_data_dir,
                allow_invalid=True)
    ec.PIT_MEMBERSHIPS[tag] = m
    ec.MEMBERSHIP = ec.membership_for(u)
    ec.set_tradeability(u)
    return u


def cmd_fit(tags):
    import seed_band_fit
    for tag in tags:
        select_pit(tag)
        rec = seed_band_fit.fit_universe(tag)
        print(f"  [{tag} pit] {rec['store']}  check {rec['check']['passed']}  "
              f"{rec['minutes_total']} min", flush=True)


class Cell:
    def __init__(self, tag):
        import profiles
        import seed_band_fit as sbf
        from engine_core import precompute
        self.u = u = select_pit(tag)
        if not sbf.is_done(u, sbf.inputs(u)):
            raise SystemExit(f"{tag}: no current, checked pit seed store; run `fit` first")
        p = read_table(config.require_cache(u.score_cache, what=f"{tag} pit"),
                       parse_dates=["date"])
        self.p = p.sort_values(["date", "symbol"]).reset_index(drop=True)
        self.S = np.load(sbf.store_path(u))
        if len(self.S) != len(self.p):
            raise SystemExit(f"{tag}: store rows {len(self.S)} != panel rows {len(self.p)}")
        self.px = self.p.pivot_table(index="date", columns="symbol", values="close").ffill()
        self.op = self.p.pivot_table(index="date", columns="symbol", values="open").ffill()
        self.bd = u.trading_days(self.px.index)
        self.pc = precompute(self.px)
        self.mom20 = self.px / self.px.shift(20) - 1
        self.capkw = profiles.cap_kwargs(u)

    def score_panel(self, cols):
        score = np.mean(np.ascontiguousarray(self.S[:, list(cols)].T), axis=0)
        q = self.p[["date", "symbol"]].copy()
        q["score"] = score
        return q.pivot_table(index="date", columns="symbol", values="score")

    def run(self, sc, arm):
        import arms.registry as arm_reg
        from test_exposure import backtest_exposure
        a = arm_reg.ARMS[arm]
        eq, *_ = backtest_exposure(self.px, self.op, sc, self.bd, self.pc, self.mom20,
                                   rebal=REBAL,
                                   tax_enabled=True, audit=None, mode=a.mode,
                                   sizing=a.sizing, drawdown_stop=None, **self.capkw)
        return eq


def metrics(eq):
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100
    dd = float(((eq - eq.cummax()) / eq.cummax()).min()) * 100
    return cagr, dd


def cmd_band(cells):
    import arms.registry as arm_reg
    from drawdown_stop_band import subsets
    rows = []
    by_tag = {}
    for tag, arm in cells:
        by_tag.setdefault(tag, []).append(arm)
    for tag, arms in by_tag.items():
        C = Cell(tag)
        M = Path(C.u.metrics_dir)
        pub = read_table(M / "v34_equity_tradeable_tax_pit.csv",
                         parse_dates=["date"]).set_index("date")
        comp = read_table(M / "v34_comparison_tradeable_tax_pit.csv").set_index("Config")
        basket = float(comp.loc["buy & hold equal-weight", "CAGR%"])
        prod = C.score_panel(range(10))
        for arm in arms:
            col = arm_reg.ARMS[arm].equity_column
            eq = C.run(prod, arm)
            same = bool(np.array_equal(eq.to_numpy(), pub[col].to_numpy()))
            print(f"  [{tag} {arm}] sanity: production subset reproduces the published "
                  f"curve exactly: {same}", flush=True)
            if not same:
                gap = float((eq - pub[col].reindex(eq.index)).abs().max())
                raise SystemExit(f"{tag} {arm}: production subset differs from "
                                 f"v34_equity_tradeable_tax_pit.csv by up to Rs {gap:,.2f}; "
                                 f"nothing drawn")
        t0 = time.time()
        for k, cols in enumerate(subsets()):
            sc = C.score_panel(cols)
            for arm in arms:
                c, d = metrics(C.run(sc, arm))
                rows.append({"universe": tag, "arm": arm, "subset": k,
                             "seeds": " ".join(str(x) for x in cols),
                             "cagr_pct": c, "maxdd_pct": d, "basket_cagr_pct": basket,
                             "cagr_minus_basket": c - basket})
            if k % 10 == 9:
                print(f"  [{tag}] {k + 1} of 50 subsets, {(time.time() - t0) / 60:.1f} min",
                      flush=True)
    out = ROOT / "diagnostics" / f"pit_noise_band_{time.strftime('%Y%m%d')}.csv"
    # naming: axis-free -- one measurement of named cells at fixed settings, stated in the file
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  wrote {out.relative_to(ROOT)} ({len(rows)} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("fit", "band"))
    ap.add_argument("--cells", required=True,
                    help="comma-separated universe:arm, e.g. nifty200:v3,midcap100:v1")
    a = ap.parse_args()
    cells = [tuple(c.split(":")) for c in a.cells.split(",") if c.strip()]
    if a.cmd == "fit":
        cmd_fit(sorted({t for t, _ in cells}))
    else:
        cmd_band(cells)
    return 0


if __name__ == "__main__":
    sys.exit(main())
