"""
leakage_check1_causality.py -- CHECK 1 of experiments/LEAKAGE_SPEC.txt.

For every feature in FEATS_V2: compute its value at day t on the real panel;
corrupt every row STRICTLY AFTER t; recompute; compare at day t, BIT-EXACT.

Any feature whose day-t value moves when only future rows changed is reading
forward. Two independent corruptions are applied because one could leave a value
unchanged by coincidence:
    (a) REPLACE  future rows get a synthetic random walk
    (b) SHUFFLE  future rows are permuted in time, per symbol

BOTH feature stages are recomputed, because add_market_relative_features derives
a market return at PANEL level -- a per-symbol-only test could not see a leak
entering through the market series.

Reports THE LIST, per feature, not a summary verdict. Nothing is fixed here.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd
import config
from features_v2 import FEATS_V2, add_stock_features, add_market_relative_features
from universes.registry import REGISTRY

N_DATES = 24
PRICE_COLS = ["open", "high", "low", "close"]

# The DATA DIRECTORY comes from universes/registry.py -- the single definition.
# The LABEL stays local: this file's "NIFTY 100"/"MIDCAP150" spelling is printed
# into diagnostics/leakage_check1_causality.txt, and the sibling scripts use two
# other spellings for the same two universes. Labels are presentation; paths are
# facts. Order is load-bearing -- the report is written universe by universe.
LABELS = {"nifty100": "NIFTY 100", "midcap150": "MIDCAP150"}
UNIVERSES = {u.tag: (u.data_dir, LABELS[u.tag])
             for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])}


def load_raw(d):
    frames = []
    for f in sorted(Path(d).glob("*.csv")):
        x = config.read_price_csv(f)[["date", "open", "high", "low", "close",
                                      "volume"]].dropna().sort_values("date")
        x["symbol"] = f.stem
        frames.append(x)
    return pd.concat(frames, ignore_index=True)


def pipeline(raw):
    """Exactly the two feature stages build_panel runs, in the same order."""
    out = [add_stock_features(g.sort_values("date").copy())
           for _, g in raw.groupby("symbol")]
    return add_market_relative_features(pd.concat(out, ignore_index=True))


def corrupt(raw, t, mode, seed):
    """Corrupt every row strictly after date t. Rows up to and including t are
    left byte-identical, so any change at t is the feature reaching forward."""
    rng = np.random.default_rng(seed)
    c = raw.copy()
    fut = c["date"] > t
    if mode == "replace":
        n = int(fut.sum())
        # A synthetic positive random walk: prices stay valid so that a NaN
        # cannot masquerade as agreement.
        base = rng.uniform(50, 5000, size=n)
        c.loc[fut, "close"] = base
        c.loc[fut, "open"] = base * rng.uniform(0.97, 1.03, size=n)
        c.loc[fut, "high"] = base * rng.uniform(1.00, 1.08, size=n)
        c.loc[fut, "low"] = base * rng.uniform(0.92, 1.00, size=n)
        c.loc[fut, "volume"] = rng.uniform(1e3, 1e8, size=n)
    elif mode == "shuffle":
        # Permute the future block in time, within each symbol.
        for sym, g in c[fut].groupby("symbol"):
            idx = g.index.to_numpy()
            perm = rng.permutation(idx)
            for col in PRICE_COLS + ["volume"]:
                c.loc[idx, col] = c.loc[perm, col].to_numpy()
    else:
        raise ValueError(mode)
    return c


def compare_at(ref, test, t):
    """Bit-exact comparison of every feature at date t, across all symbols."""
    a = ref[ref["date"] == t].sort_values("symbol")
    b = test[test["date"] == t].sort_values("symbol")
    if list(a["symbol"]) != list(b["symbol"]):
        raise SystemExit("symbol sets diverged at t -- the corruption changed rows it must not")
    res = {}
    for f in FEATS_V2:
        x = a[f].to_numpy(dtype=np.float64)
        y = b[f].to_numpy(dtype=np.float64)
        same = np.array_equal(x, y, equal_nan=True)
        if same:
            res[f] = (True, 0, 0.0)
        else:
            d = ~((x == y) | (np.isnan(x) & np.isnan(y)))
            with np.errstate(invalid="ignore"):
                mx = float(np.nanmax(np.abs(x[d] - y[d]))) if d.any() else 0.0
            res[f] = (False, int(d.sum()), mx)
    return res


def run(uni, d, label, W):
    raw = load_raw(d)
    ref = pipeline(raw)
    # Sample dates spread across the BACKTEST window, not the whole price panel.
    dates = sorted(x for x in ref["date"].unique()
                   if config.BT_START_DATE <= x <= config.BT_END_DATE)
    picks = [dates[i] for i in np.linspace(0, len(dates) - 1, N_DATES).astype(int)]
    nsym = ref["symbol"].nunique()

    W("=" * 100)
    W(f" CHECK 1 -- FEATURE CAUSALITY -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  symbols {nsym}   panel rows {len(ref):,}")
    W(f"  dates sampled {len(picks)} spread across "
      f"{picks[0].date()} .. {picks[-1].date()}")
    W(f"  cells compared per feature: {len(picks)} dates x {nsym} symbols x "
      f"2 corruptions = {len(picks)*nsym*2:,}")
    W("  corruption (a) replace: future rows overwritten with a synthetic random walk")
    W("  corruption (b) shuffle: future rows permuted in time within each symbol")
    W("  comparison: BIT-EXACT (np.array_equal with equal_nan)")
    W("")

    fail = {f: {"replace": [], "shuffle": []} for f in FEATS_V2}
    for i, t in enumerate(picks):
        for mode in ("replace", "shuffle"):
            res = compare_at(ref, pipeline(corrupt(raw, t, mode, seed=1000 + i)), t)
            for f, (ok, ncell, mx) in res.items():
                if not ok:
                    fail[f][mode].append((str(pd.Timestamp(t).date()), ncell, mx))

    W("-" * 100)
    W(f" {'feature':<24}{'(a) replace':>14}{'(b) shuffle':>14}   verdict")
    W("-" * 100)
    leaking = []
    for f in FEATS_V2:
        na, nb = len(fail[f]["replace"]), len(fail[f]["shuffle"])
        ok = (na == 0 and nb == 0)
        if not ok:
            leaking.append(f)
        W(f" {f:<24}{('bit-exact' if na==0 else f'{na} dates MOVED'):>14}"
          f"{('bit-exact' if nb==0 else f'{nb} dates MOVED'):>14}"
          f"   {'causal' if ok else 'READS FORWARD'}")
    W("-" * 100)
    W("")
    if leaking:
        W(f"  {len(leaking)} OF {len(FEATS_V2)} FEATURES MOVED WHEN ONLY FUTURE ROWS CHANGED:")
        for f in leaking:
            for mode in ("replace", "shuffle"):
                for dt, ncell, mx in fail[f][mode][:6]:
                    W(f"    {f:<22} {mode:<8} {dt}  cells {ncell:>4}  max|diff| {mx:.6g}")
    else:
        W(f"  ALL {len(FEATS_V2)} FEATURES BIT-EXACT UNDER BOTH CORRUPTIONS AT EVERY")
        W("  SAMPLED DATE. No feature's day-t value moved when only future rows changed.")
    W("")
    W("  WHAT THIS DOES NOT SAY: dates are sampled, so a leak confined to dates")
    W("  outside this sample would survive. It tests the feature stage only --")
    W("  the training mask and the label are CHECK 2.")
    W("")
    return leaking


def main():
    out = []
    bad = {}
    for uni, (d, label) in UNIVERSES.items():
        # THE FARM IS BUILT ON DEMAND under cache/<tag>/ since 2026-09-23;
        # u.data_dir is only its path and is empty on a fresh tree.
        d = REGISTRY[uni].prepare_data_dir()
        bad[uni] = run(uni, d, label, out.append)
        out.append("")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. `bad` was already
    # collected here and then dropped on the floor; nothing about the corruption
    # test, the sampled dates or the comparison changed. The pass condition is
    # the one the report already states -- no feature's day-t value may move when
    # only future rows change, on either universe.
    #
    # WHAT A PASS STILL DOES NOT SAY, and the report says this too: dates are
    # SAMPLED, so a leak confined to dates outside the sample survives this. A
    # green here is evidence, not proof.
    leaking = {u: v for u, v in bad.items() if v}
    if leaking:
        for u, v in leaking.items():
            out.append(f"  LEAKING on {u}: {', '.join(sorted(v))}")
        out.append(f"  RESULT: FAIL -- {sum(len(v) for v in leaking.values())} "
                   f"feature-universe pair(s) moved under a future-only corruption.")
        rc = 1
    else:
        out.append(f"  RESULT: PASS -- no feature moved on any sampled date, "
                   f"on {len(bad)} universe(s): {', '.join(sorted(bad))}.")
        rc = 0
    (ROOT / "diagnostics" / "leakage_check1_causality.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
