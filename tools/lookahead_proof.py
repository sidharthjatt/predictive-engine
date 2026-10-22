"""lookahead_proof.py -- no decision on or before a cut date T depends on any input after T.

    python tools/lookahead_proof.py --universe nifty100 --mode static \\
        --arms v1,v2,v3,v4 --cut 2019-09-30,2022-12-30,2026-03-31
    python tools/lookahead_proof.py ... --control leak     # must FAIL
    python tools/lookahead_proof.py ... --control label    # must FAIL
    python tools/lookahead_proof.py ... --mode pit --control member   # must FAIL
    python tools/lookahead_proof.py recompare --work <an earlier work folder>

WHAT IT RUNS. The decision path of a pipeline run, in-process, for one universe:
build_panel, score_monthly with the production seeds, and backtest_exposure for
each arm at the default cadence, profile and capital, tax off. It runs in these
variants, each in its own process:

    full    every input as delivered. Scores every month, as the pipeline does.
    cut     every price row dated after T removed, and in pit mode every
            membership row with an effective date after T.
    noise   every open, high, low, close, adj_close and volume value dated after
            T replaced by random positive numbers. Membership is unchanged.
    names   pit only: cut, and also every symbol removed that is not a member on
            any effective date on or before T and is not in the first list.

The NSE index file is not an input to any decision (it is read only for the
benchmark rows), so it is not loaded and has nothing to cut.

WHAT IS COMPARED, bit for bit: every model score on every date on or before T,
decision date or not; and for every decision date on or before T, per arm: the
scores on that date; the ranked list, the 8 selected names, the 16
kept and the target weights with the exposure (audit "orders", unrounded); the
audit ranking and decision rows; and the drawdown-stop and drawdown-limit
events dated on or before T, where the arm has them. The fills, holdings and
daily valuations dated on or before T are compared too, as one check per arm.

THREE THINGS THAT ARE NOT DATA AND ARE THE SAME IN EVERY VARIANT, stated:
  1. The cut variant's backtest dates end at T plus the next calendar session
     from data/nse_trading_calendar.csv, which carries no data. The engine makes
     no order on the last date of its window, so without that session the cut
     run would skip the decision on T for a reason that is not look-ahead.
  2. The cut and noise variants score only the months whose first session is on
     or before T (score_monthly's `through`). A month's model and scores do not
     depend on later months.
  3. The full variant's results are reused for every cut date of one invocation.

NEGATIVE CONTROLS, --control, applied in every variant of the invocation:
  leak    rev_1 is computed from the NEXT session's return, a 1-session leak.
  label   the training rule before 2026-10-22: rows up to the cut with any
          label, ranked once per date over every label. On data with no missing
          sessions that rule leaks nothing, so this control also plants a gap:
          for the first scorable symbol on the cut of T's month, its rows after
          that cut up to T are removed, so its label there ends after T. The same
          gap with --control gap and the current rule must PASS.
  member  pit only: survivorship.member_mask and test_exposure.breadth_momentum
          as before 2026-10-22, every row before the first effective date kept.
The full variant of a control scores only through the last cut date.

Writes only under --work (default: the system temp folder). Prints PASS or FAIL
per decision date and the first difference of each failure. Exits 0 when every
comparison passes, 1 otherwise.
"""
import argparse
import os
import pickle
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PRICE_FIELDS = ("open", "high", "low", "close", "adj_close", "volume")
TABLES = ("holdings", "summary", "trades", "skipped")
CONTROLS = ("none", "leak", "label", "gap", "member")


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def universe(tag, mode):
    from universes.registry import REGISTRY, pit_variant
    u = REGISTRY[tag]
    return pit_variant(u) if mode == "pit" else u


def source_dir(u, mode):
    return Path(u.survivorship_data_dir if mode == "pit" else u.raw_data_dir)


def stock_files(src, index_name):
    from universes.registry import normalise_stem
    key = normalise_stem(index_name) if index_name else None
    return sorted(f for f in src.glob("*.csv")
                  if not f.name.startswith("._") and normalise_stem(f.stem) != key)


def _dates(lines, source):
    """The parsed date of each data line, as read_price_csv parses the column."""
    import pandas as pd
    import config
    first = pd.Series([ln.split(",", 1)[0] for ln in lines])
    return config.smart_parse_dates(first, source=source)


def write_farm(u, mode, variant, T, dst, gap=None, drop=frozenset(), seed=0):
    """The variant's constituent folder. Kept lines are the source's own bytes."""
    import numpy as np
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    for f in stock_files(source_dir(u, mode), u.index_name):
        if f.stem in drop:
            continue
        g = gap if gap is not None and gap[0] == f.stem else None
        if variant == "full" and g is None:
            (dst / f.name).symlink_to(f)
            continue
        text = f.read_text().splitlines()
        head, rows = text[0], [ln for ln in text[1:] if ln.strip()]
        cols = head.split(",")
        d = _dates(rows, str(f))
        out = [head]
        for ln, dt in zip(rows, d):
            if g is not None and g[1] < dt <= g[2]:
                continue
            if variant in ("cut", "names") and dt > T:
                continue
            if variant == "noise" and dt > T:
                v = ln.split(",")
                if len(v) != len(cols):
                    raise SystemExit(f"{f.name}: a line has {len(v)} fields, the header "
                                     f"{len(cols)}; cannot rewrite it safely")
                base = float(rng.uniform(1.0, 5000.0))
                vals = {"open": base * rng.uniform(0.97, 1.03),
                        "high": base * rng.uniform(1.03, 1.08),
                        "low": base * rng.uniform(0.92, 0.97),
                        "close": base, "adj_close": base * rng.uniform(0.98, 1.0),
                        "volume": float(rng.integers(1, 10_000_000))}
                for k, x in vals.items():
                    if k in cols:
                        v[cols.index(k)] = repr(float(x))
                ln = ",".join(v)
            out.append(ln)
        # naming: axis-free -- a scratch copy of one constituent file under --work,
        # an input to one proof variant and never an artefact
        (dst / f.name).write_text("\n".join(out) + "\n")


def write_membership(u, T, dst):
    """The membership file with every row whose effective date is after T removed.
    Kept rows keep their delivered text, so they parse as the original does."""
    import pandas as pd
    import config
    df = config.read_table(u.membership_file, dtype=str, keep_default_na=False)
    col = {c.lower().strip(): c for c in df.columns}["effective_date"]
    raw = df[col].astype(str)
    d = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    d = d.fillna(pd.to_datetime(raw, dayfirst=True, errors="coerce"))
    # naming: axis-free -- a scratch copy of the membership file under --work
    df[(d <= T).to_numpy()].to_csv(dst, index=False)
    return dst


def late_names(u, T):
    """Pit symbols that are not a member on any effective date up to T and are not
    in the first list."""
    import survivorship as sv
    m = sv.load(u.membership_file, index_name=u.index_name, allow_invalid=True)
    known = set(m.lists[0])
    for d, L in zip(m.dates, m.lists):
        if d <= T:
            known |= set(L)
    return {f.stem for f in stock_files(source_dir(u, "pit"), u.index_name)
            if f.stem.upper() not in known}


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------
def apply_control(control):
    import numpy as np
    import pandas as pd
    import engine_core as ec
    import features_v2 as fv
    if control == "leak":
        orig = fv.add_stock_features

        def leaked(df):
            d = orig(df)
            c = d["close"]
            d["rev_1"] = -(c.shift(-1) / c - 1)
            return d
        ec.add_stock_features = leaked
    elif control == "label":
        def old_training_set(p, cal, i_first, horizon=ec.HORIZON, embargo=ec.PURGE_EMBARGO):
            j = i_first - horizon - embargo
            if j < 0:
                return None
            if "_old_rank" not in p.columns:
                lab = p["scorable"] & p["fwd_ret"].notna()
                p["_old_rank"] = np.nan
                p.loc[lab, "_old_rank"] = p.loc[lab].groupby("date")["fwd_ret"].rank(pct=True)
            ok = (p["date"] <= pd.Timestamp(cal[j])) & p["_old_rank"].notna()
            return p.index[ok], p.loc[ok, "_old_rank"].to_numpy()
        ec.training_set = old_training_set
    elif control == "member":
        import survivorship as sv
        import test_exposure as te

        def old_mask(panel, membership, date_col="date", symbol_col="symbol"):
            if not sv.is_pit() or membership is None or panel.empty:
                return np.ones(len(panel), dtype=bool)
            pos = membership._pos(panel[date_col])
            syms = panel[symbol_col].astype(str).str.upper().values
            return np.array([q < 0 or s in membership.lists[q] for q, s in zip(pos, syms)])

        def old_breadth(mom20, dt):
            m = mom20.loc[dt].dropna()
            M = ec.MEMBERSHIP
            if sv.is_pit() and M is not None:
                mem = M.members_on(dt)
                if mem:
                    m = m[[str(k).upper() in mem for k in m.index]]
            return m
        sv.member_mask = old_mask
        te.breadth_momentum = old_breadth


def plant_gap(u, mode, T):
    """(symbol, after, through): the label control's gap for cut date T."""
    import io
    import contextlib
    import numpy as np
    import pandas as pd
    import engine_core as ec
    farm = Path(tempfile.mkdtemp(prefix="lookahead_gap_"))
    write_farm(u, mode, "full", T, farm)
    with contextlib.redirect_stdout(io.StringIO()):
        p = ec.build_panel(ec.HORIZON, data_dir=farm)
    cal = np.array(sorted(p["date"].unique()))
    first = p.loc[p["date"].dt.to_period("M") == pd.Timestamp(T).to_period("M"), "date"].min()
    i = int(np.searchsorted(cal, np.datetime64(first)))
    cut = pd.Timestamp(cal[i - ec.HORIZON - ec.PURGE_EMBARGO])
    sym = sorted(p.loc[(p["date"] == cut) & p["scorable"] & p["fwd_ret"].notna(), "symbol"])[0]
    return sym, cut, pd.Timestamp(T)


# ---------------------------------------------------------------------------
# one variant, in its own process
# ---------------------------------------------------------------------------
def run_variant(a):
    import io
    import contextlib
    import numpy as np
    import pandas as pd
    import engine_core as ec
    import survivorship as sv
    import tradability
    import profiles
    import arms.registry as arm_reg
    from build_scores_step import SEEDS
    from test_exposure import backtest_exposure

    T = pd.Timestamp(a.T)
    u = universe(a.universe, a.mode)
    apply_control(a.control)
    work = Path(a.work)
    farm = work / "farm"
    gap = None
    if a.control in ("label", "gap"):
        gap = pickle.loads(Path(a.gap).read_bytes())
    drop = late_names(u, T) if a.variant == "names" else frozenset()
    write_farm(u, a.mode, a.variant, T, farm, gap=gap, drop=drop, seed=a.noise_seed)
    if a.mode == "pit":
        mfile = (u.membership_file if a.variant in ("full", "noise")
                 else write_membership(u, T, work / "membership.csv"))
        sv.set_mode("pit")
        ec.MEMBERSHIP = sv.load(mfile, index_name=u.index_name, allow_invalid=True)
    cal = ec._load_calendar()
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        raw = ec.build_panel(ec.HORIZON, data_dir=farm)
    t_panel = time.time()
    through = None if (a.variant == "full" and a.through is None) else pd.Timestamp(a.through or T)
    with contextlib.redirect_stdout(io.StringIO()):
        p = ec.score_monthly(raw[ec.SCORE_INPUT_COLS], SEEDS, purge_mode=u.purge_mode,
                             through=through)
    t_score = time.time()
    ec.TRADEABLE = tradability.sessions_with_row(farm, cal)
    ec.TRADEABLE_TAG = u.tag
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    # Reindexed to the price dates: a variant scored only through T has no score
    # row after it. For the full variant every price date has a score row already.
    sc = p.pivot_table(index="date", columns="symbol", values="score").reindex(px.index)
    bd = u.trading_days(px.index)
    if a.variant in ("cut", "names"):
        nxt = sorted(d for d in cal if d > T)[0]
        bd = bd.append(pd.DatetimeIndex([nxt]))
        px = px.reindex(px.index.union(bd)).ffill()
        op = op.reindex(op.index.union(bd)).ffill()
        sc = sc.reindex(sc.index.union(bd))
    pc = ec.precompute(px)
    mom20 = px / px.shift(20) - 1
    out = {"scores": p.loc[p["score"].notna(), ["date", "symbol", "score"]].reset_index(drop=True),
           "arms": {}, "bd": bd,
           "seconds": {"panel": round(t_panel - t0, 1), "score": round(t_score - t_panel, 1)}}
    for name in a.arms.split(","):
        arm = arm_reg.ALL_ARMS[name]
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                 "skipped")}
        with contextlib.redirect_stdout(io.StringIO()):
            eq, _tc, _n, _e = backtest_exposure(px, op, sc, bd, pc, mom20, audit=audit,
                                                tax_enabled=False, **arm.kwargs,
                                                **profiles.cap_kwargs(u))
        audit.pop("tax", None)
        out["arms"][name] = {"audit": audit, "equity": eq}
    out["seconds"]["backtest"] = round(time.time() - t_score, 1)
    # naming: axis-free -- one variant's decisions, a scratch file under --work
    (work / "result.pkl").write_bytes(pickle.dumps(out))


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------
def same(x, y):
    """Exact equality: floats bit for bit (NaN equal to NaN), recursively."""
    import math
    import numpy as np
    if isinstance(x, float) or isinstance(y, float):
        if not (isinstance(x, (float, int, np.floating)) and isinstance(y, (float, int, np.floating))):
            return False
        if math.isnan(x) and math.isnan(y):
            return True
        return float(x) == float(y) and np.float64(x).tobytes() == np.float64(y).tobytes()
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(same(x[k], y[k]) for k in x)
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        return len(x) == len(y) and all(same(a, b) for a, b in zip(x, y))
    return x == y


def first_diff(x, y, path=""):
    import math
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y), key=str):
            if k not in x or k not in y:
                return f"{path}.{k}: present in only one ({'full' if k in x else 'variant'})"
            d = first_diff(x[k], y[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        for i, (a, b) in enumerate(zip(x, y)):
            d = first_diff(a, b, f"{path}[{i}]")
            if d:
                return d
        return None if len(x) == len(y) else f"{path}: length {len(x)} vs {len(y)}"
    return None if same(x, y) else f"{path}: full {x!r} vs variant {y!r}"


def _on(rows, key, T):
    import pandas as pd
    return [r for r in rows if pd.Timestamp(r[key]) <= T]


def compare(full, var, T, label):
    """Lines of the report for one variant against full; returns (lines, failures)."""
    import numpy as np
    import pandas as pd
    L, fails = [], 0
    fs = full["scores"][full["scores"]["date"] <= T].set_index(["date", "symbol"])["score"]
    vs = var["scores"][var["scores"]["date"] <= T].set_index(["date", "symbol"])["score"]
    # EVERY SCORE ON OR BEFORE T, decision date or not. A leak that reaches only
    # the last sessions before T changes no decision when T is not a rebalance
    # date, and must still fail.
    why = None
    if list(fs.index) != list(vs.index):
        only = sorted(set(fs.index) ^ set(vs.index))[:3]
        why = (f"different (date, symbol) pairs scored, {len(set(fs.index) ^ set(vs.index))} "
               f"in all, e.g. {[(str(d.date()), s) for d, s in only]}")
    elif not np.array_equal(fs.to_numpy(), vs.to_numpy(), equal_nan=True):
        k = int(np.flatnonzero(fs.to_numpy() != vs.to_numpy())[0])
        d, sym = fs.index[k]
        why = f"score of {sym} on {d.date()}: full {fs.iloc[k]!r} vs variant {vs.iloc[k]!r}"
    fails += why is not None
    L.append(f"    {label:<6} all   every model score on every date to {T.date()} "
             f"({len(fs):,} scores)  " + ("PASS" if why is None else f"FAIL  first difference: {why}"))
    for name in full["arms"]:
        fa, va = full["arms"][name]["audit"], var["arms"][name]["audit"]
        f_orders = {pd.Timestamp(o["decided_on"]): o for o in _on(fa.get("orders", []), "decided_on", T)}
        v_orders = {pd.Timestamp(o["decided_on"]): o for o in _on(va.get("orders", []), "decided_on", T)}
        dates = sorted(set(f_orders) | set(v_orders)
                       | {pd.Timestamp(r["decided_on"]) for r in _on(fa["decisions"], "decided_on", T)})
        n_pass = 0
        for d in dates:
            why = None
            a = fs.xs(d, level="date") if d in fs.index.get_level_values(0) else pd.Series(dtype=float)
            b = vs.xs(d, level="date") if d in vs.index.get_level_values(0) else pd.Series(dtype=float)
            if list(a.index) != list(b.index):
                only = sorted(set(a.index) ^ set(b.index))[:5]
                why = f"scores: different scored names, e.g. {only}"
            elif not np.array_equal(a.to_numpy(), b.to_numpy(), equal_nan=True):
                k = int(np.flatnonzero(a.to_numpy() != b.to_numpy())[0])
                why = (f"score of {a.index[k]}: full {a.iloc[k]!r} vs variant {b.iloc[k]!r}")
            if why is None:
                why = first_diff(f_orders.get(d), v_orders.get(d), "order")
            for tab in ("ranking", "decisions"):
                if why is None:
                    why = first_diff([r for r in fa[tab] if pd.Timestamp(r["decided_on"]) == d],
                                     [r for r in va[tab] if pd.Timestamp(r["decided_on"]) == d], tab)
            if why is None:
                n_pass += 1
                L.append(f"    {label:<6} {name}  {d.date()}  PASS")
            else:
                fails += 1
                L.append(f"    {label:<6} {name}  {d.date()}  FAIL  first difference: {why}")
        for tab, key in (("stop_events", "date"), ("dd_events", "date")):
            if tab in fa or tab in va:
                why = first_diff(_on(fa.get(tab, []), key, T), _on(va.get(tab, []), key, T), tab)
                fails += why is not None
                L.append(f"    {label:<6} {name}  drawdown state ({tab}) to {T.date()}  "
                         + ("PASS" if why is None else f"FAIL  first difference: {why}"))
        why = None
        for tab in TABLES:
            key = "date"
            why = why or first_diff(_on(fa[tab], key, T), _on(va[tab], key, T), tab)
        fails += why is not None
        L.append(f"    {label:<6} {name}  fills, holdings and valuation to {T.date()}  "
                 + ("PASS" if why is None else f"FAIL  first difference: {why}"))
        L.append(f"    {label:<6} {name}  {n_pass} of {len(dates)} decision dates on or before "
                 f"{T.date()} identical")
    return L, fails


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def spawn(args, variant, T, work, through=None, gap=None):
    work.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), "_variant",
           "--universe", args.universe, "--mode", args.mode, "--arms", args.arms,
           "--control", args.control, "--variant", variant, "--T", str(T.date()),
           "--work", str(work), "--noise-seed", str(args.noise_seed)]
    if through is not None:
        cmd += ["--through", str(through.date())]
    if gap is not None:
        cmd += ["--gap", str(gap)]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONHASHSEED="0"))
    if r.returncode != 0:
        raise SystemExit(f"variant {variant} at {T.date()} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    res = pickle.loads((work / "result.pkl").read_bytes())
    print(f"  ran {variant:<6} cut {T.date()}  panel {res['seconds']['panel']:.0f}s  "
          f"scores {res['seconds']['score']:.0f}s  backtests {res['seconds']['backtest']:.0f}s  "
          f"total {time.time() - t0:.0f}s", flush=True)
    return res


def recompare(base):
    """Compare the saved results of an earlier invocation again: `base` is its work
    folder (<universe>_<mode>_<control>_<time>). Nothing is recomputed."""
    import pandas as pd
    full = pickle.loads((base / "full" / "result.pkl").read_bytes())
    print(f"RECOMPARE  {base.name}  (saved results, nothing recomputed)")
    total = 0
    runs = sorted((d for d in base.iterdir() if d.is_dir() and d.name != "full"),
                  key=lambda d: (d.name.rsplit("_", 1)[1], d.name))
    for d in runs:
        v, T = d.name.rsplit("_", 1)
        T = pd.Timestamp(T)
        res = pickle.loads((d / "result.pkl").read_bytes())
        print(f"\n  CUT DATE {T.date()}  variant {v}")
        lines, fails = compare(full, res, T, v)
        print("\n".join(lines))
        total += fails
    print(f"\nRESULT: {'PASS' if total == 0 else f'FAIL ({total} comparison(s) differ)'}"
          f"  -- {base.name}")
    return 0 if total == 0 else 1


def main(argv=None):
    import pandas as pd
    ap = argparse.ArgumentParser(description="Prove no decision on or before T reads data after T.")
    ap.add_argument("cmd", nargs="?", default="prove", choices=("prove", "_variant", "recompare"))
    ap.add_argument("--universe")
    ap.add_argument("--mode", choices=("static", "pit"), default="static")
    ap.add_argument("--arms", default="v1,v2,v3,v4")
    ap.add_argument("--cut", help="comma-separated cut dates")
    ap.add_argument("--control", choices=CONTROLS, default="none")
    ap.add_argument("--work", default=str(Path(tempfile.gettempdir()) / "lookahead_proof"))
    ap.add_argument("--noise-seed", type=int, default=12345)
    # _variant only
    ap.add_argument("--variant")
    ap.add_argument("--T")
    ap.add_argument("--through")
    ap.add_argument("--gap")
    a = ap.parse_args(argv)
    if a.cmd == "_variant":
        return run_variant(a)
    if a.cmd == "recompare":
        return recompare(Path(a.work))
    if not a.universe:
        ap.error("--universe is required")

    if a.control == "member" and a.mode != "pit":
        ap.error("--control member needs --mode pit")
    cuts = [pd.Timestamp(x) for x in a.cut.split(",")]
    variants = ["cut", "noise"] + (["names"] if a.mode == "pit" else [])
    base = Path(a.work) / f"{a.universe}_{a.mode}_{a.control}_{time.strftime('%Y%m%dT%H%M%S')}"
    print(f"LOOK-AHEAD PROOF  universe {a.universe}  mode {a.mode}  arms {a.arms}  "
          f"control {a.control}  cut dates {', '.join(str(c.date()) for c in cuts)}")
    print(f"  python {sys.version.split()[0]} at {sys.executable}; work folder {base}")
    total = 0
    if a.control in ("label", "gap"):
        if len(cuts) != 1:
            ap.error("--control label and gap take one cut date: the gap is planted for it")
    full_through = None if a.control == "none" else max(cuts)
    gapfile = None
    if a.control in ("label", "gap"):
        gap = plant_gap(universe(a.universe, a.mode), a.mode, cuts[0])
        base.mkdir(parents=True, exist_ok=True)
        gapfile = base / "gap.pkl"
        # naming: axis-free -- the planted gap for this invocation, under --work
        gapfile.write_bytes(pickle.dumps(gap))
        print(f"  planted gap: {gap[0]} has no rows after {gap[1].date()} up to {gap[2].date()}")
    full = spawn(a, "full", max(cuts), base / "full", through=full_through, gap=gapfile)
    for T in cuts:
        print(f"\n  CUT DATE {T.date()}")
        for v in variants:
            res = spawn(a, v, T, base / f"{v}_{T.date()}", gap=gapfile)
            lines, fails = compare(full, res, T, v)
            print("\n".join(lines))
            total += fails
    verdict = "PASS" if total == 0 else f"FAIL ({total} comparison(s) differ)"
    print(f"\nRESULT: {verdict}  -- universe {a.universe}, mode {a.mode}, control {a.control}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
