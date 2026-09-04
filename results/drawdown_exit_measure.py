"""
drawdown_exit_measure.py -- portfolio drawdown exit, measured.

SPEC: experiments/DRAWDOWN_EXIT_SPEC.txt, written and frozen BEFORE this file
existed, including the nine predictions D1-D9 in its section 11.

READ THE SPEC'S GOVERNING CONSTRAINT BEFORE ANY NUMBER THIS SCRIPT PRODUCES.
The window contains ONE severe drawdown (March 2020). Five thresholds on one
crash is ONE observation, not five. A threshold that looks good is a threshold
that happened to fit March 2020.

THE RULE
    peak_t = max(pv_0..pv_t)                 running all-time high-water mark
    dd_t   = pv_t / peak_t - 1
    EXIT   when dd_t <= -THRESHOLD, evaluated on day t's CLOSE, FILLING AT DAY
           t+1's OPEN -- the engine's existing convention.
    RE-ENTER at the first scheduled rebalance where at least DD_RE_WAIT trading
           days have passed since the exit FILL and dd has recovered above
           -(DD_RE_DD_FRAC * THRESHOLD).
    DD_RE_WAIT = 20 and DD_RE_DD_FRAC = 0.5 are UNDERIVED. Spec section 5.

HOW THE RULE IS ADDED WITHOUT EDITING ANY ENGINE -- AND WHY NOT A REIMPLEMENTATION
    The rule needs a new branch inside the loop, which a module-attribute
    override cannot express. The obvious alternative -- copying the loop into
    this file -- WOULD CREATE A SIXTH INLINE REIMPLEMENTATION OF THE BACKTEST,
    which is the defect KNOWN_ISSUES.md records under "There are FIVE
    reimplementations of the backtest, not two". It is not done.

    Instead this script takes the SHIPPING function's own source at run time via
    inspect.getsource, applies three NAMED TEXTUAL PATCHES at asserted anchors,
    compiles it, and runs that. The patched function is DERIVED FROM the shipping
    engine rather than a copy of it: if test_exposure.py changes, the anchors
    fail loudly instead of drifting silently. NO FILE ON DISK IS MODIFIED.

    WITH DD_THRESHOLD = None EVERY PATCH IS INERT, so the patched function must
    reproduce the published v2 arm exactly. That is gate G1, and it is also the
    proof that the patching itself changes nothing.

THREE BLOCKING CORRECTNESS GATES. NONE IS ABOUT WHETHER THE RULE IS GOOD.
    G1 the control reproduces the published v2 row of v34_comparison.csv exactly
    G2 execution timing: every exit fills at the NEXT session's open, ZERO at any
       close, every fill exactly one session after its trigger
    G3 daily reconciliation: cash + holdings = equity on all 1,836 days
    ANY FAILURE STOPS THE RUN. Spec section 8.2.

NO ACCEPT RULE. NOTHING CAN BE PROMOTED BY THIS MEASUREMENT. There is no measured
noise floor for MaxDD on any arm and entry 28 could not distinguish MaxDD from a
random-selection null, so the rule's PRIMARY OBJECTIVE CANNOT BE JUDGED with any
measurement that exists today. Only the rule's COST (CAGR, which has a measured
floor) is inferable. Spec section 8.

Reads only. Writes diagnostics/drawdown_exit_*.
"""
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["PYTHONHASHSEED"] = "0"

import hashlib
import inspect
import sys
import textwrap
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd

import config, config_mid, config_n100
import test_exposure
from universes.registry import REGISTRY
from engine_core import precompute, metrics

# ---------------------------------------------------------------- constants
THRESHOLDS = [0.10, 0.125, 0.15, 0.20, 0.25]   # spec section 6, fixed in advance
WAITS = [5, 20, 40]                            # spec section 12, fixed in advance
DD_RE_DD_FRAC = 0.5                            # revision 1 only; unused in rev 2
VOL_WIN = 60
SEED_FLOOR = {"n100": 0.97, "mid": 1.39}       # entry 29, v2, CAGR ONLY

OUT = ROOT / "diagnostics" / "drawdown_exit.txt"
OUT_CELLS = ROOT / "diagnostics" / "drawdown_exit_cells.csv"
OUT_EVENTS = ROOT / "diagnostics" / "drawdown_exit_events.csv"
OUT_EQUITY = ROOT / "diagnostics" / "drawdown_exit_equity.csv"

# The METRICS DIRECTORY and the SCORE PANEL paths come from
# universes/registry.py -- the single definition. As in rebal_cadence_sweep.py,
# the third element is the cache FILENAME rather than a full path, because load()
# joins it to the metrics directory itself.
#
# The LABEL stays local: it is printed into diagnostics/drawdown_exit.txt.
# Order is load-bearing -- the measurement is reported universe by universe.
LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}
UNIVERSES = {
    u.tag: (LABELS[u.tag], u.metrics_dir, u.score_cache.name, str(u.score_tmp))
    for u in (REGISTRY["n100"], REGISTRY["mid"])
}

# ------------------------------------------------------- the three patches
# Each is (anchor, replacement). The anchor MUST appear exactly once in the
# shipping function's source or the run aborts -- that is what makes this a
# derivation rather than a copy.

PATCH_INIT = (
    "    eq, pending, expo_log = [], None, []",
    "    eq, pending, expo_log = [], None, []\n"
    "    _dd_peak = float('-inf'); _dd_flat = False; _dd_flat_since = None\n"
    "    _dd_events = []")

PATCH_REBAL = (
    "        if i % REBAL == 0 and i < len(dates) - 1:",
    # REVISION 2, spec section 12: re-entry is TIME-ONLY. The first scheduled
    # rebalance at least DD_RE_WAIT trading days after the exit FILL. THERE IS NO
    # DRAWDOWN CONDITION. Revision 1's drawdown condition was unsatisfiable by
    # construction -- entry 33 -- because the peak is never reset and cash earns
    # nothing, so dd could never recover while flat.
    "        if DD_THRESHOLD is not None and _dd_flat and i % REBAL == 0 \\\n"
    "                and i < len(dates) - 1:\n"
    "            if (i - _dd_flat_since) >= DD_RE_WAIT:\n"
    "                _pvn = sum(q * prices[s] for s, q in shares.items()\n"
    "                           if not np.isnan(prices.get(s, np.nan))) + cash\n"
    "                _ddn = (_pvn / _dd_peak - 1) if _dd_peak > 0 else 0.0\n"
    "                _dd_flat = False\n"
    # REVISION 3, spec section 13: THE PEAK IS RESET to the portfolio value at
    # re-entry. Revisions 1 and 2 both failed from ONE cause -- the peak was
    # never reset, so after a breach the rule was permanently in breach and could
    # never clear. WHAT THIS GIVES UP is stated in the spec: drawdown is no longer
    # measured from the strategy's all-time high, so consecutive resets compound
    # (0.85 x 0.85 = 27.75% true loss reported as two ordinary 15% breaches).
    "                _dd_peak = _pvn\n"
    "                _dd_events.append({'kind': 'REENTRY', 'trigger_date': dt,\n"
    "                                   'i': i, 'pv': _pvn, 'dd': _ddn,\n"
    "                                   'n_held': len(shares)})\n"
    "            else:\n"
    "                expo_log.append(0.0)\n"
    "        if (not _dd_flat) and i % REBAL == 0 and i < len(dates) - 1:")

PATCH_TRIGGER = (
    "        eq.append(pv)",
    # THE TRIGGER. Evaluated on day t's CLOSE (pv uses px.loc[dt]); the exit is
    # written to `pending`, which the loop consumes at day t+1's OPEN. A trigger
    # that filled at today's close would be look-ahead -- spec section 4.
    "        eq.append(pv)\n"
    "        if DD_THRESHOLD is not None:\n"
    "            if pv > _dd_peak:\n"
    "                _dd_peak = pv\n"
    "            _ddc = (pv / _dd_peak - 1) if _dd_peak > 0 else 0.0\n"
    "            if (not _dd_flat) and shares and _ddc <= -DD_THRESHOLD \\\n"
    "                    and i < len(dates) - 1:\n"
    "                pending = ({}, set())   # exit-all; fills at the NEXT open\n"
    "                _dd_flat = True\n"
    "                _dd_flat_since = i + 1   # counted from the FILL, spec 5\n"
    "                _dd_events.append({'kind': 'EXIT', 'trigger_date': dt,\n"
    "                                   'i': i, 'pv': pv, 'dd': _ddc,\n"
    "                                   'n_held': len(shares)})")

PATCH_RETURN = (
    "    return (pd.Series(eq, index=dates), cum_tc, n_trades,",
    "    globals()['_DD_EVENTS_OUT'] = _dd_events\n"
    "    return (pd.Series(eq, index=dates), cum_tc, n_trades,")


def build_patched():
    """Derive the drawdown-exit backtest from the SHIPPING function's source."""
    src = inspect.getsource(test_exposure.backtest_exposure)
    src = textwrap.dedent(src)
    applied = []
    for name, (anchor, repl) in [("INIT", PATCH_INIT), ("REBAL", PATCH_REBAL),
                                 ("TRIGGER", PATCH_TRIGGER), ("RETURN", PATCH_RETURN)]:
        if src.count(anchor) != 1:
            raise SystemExit(
                f"ABORT: patch anchor {name} matched {src.count(anchor)} times, "
                f"expected exactly 1. test_exposure.backtest_exposure has changed; "
                f"the patch must be re-derived rather than silently adapted.")
        src = src.replace(anchor, repl, 1)
        applied.append(name)
    ns = dict(test_exposure.__dict__)
    ns.update(DD_THRESHOLD=None, DD_RE_WAIT=WAITS[0], DD_RE_DD_FRAC=DD_RE_DD_FRAC)
    exec(compile(src, "<patched backtest_exposure>", "exec"), ns)
    return ns["backtest_exposure"], ns, applied, hashlib.sha256(src.encode()).hexdigest()


def load(tag):
    label, M, cache, tmp = UNIVERSES[tag]
    src = config.require_cache(M / cache, tmp, what=f"{label} score panel")
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    return label, M, px, op, sc, bd, pc, mom20, port_vol, port_vol.loc[bd].median()


def run(fn, ns, ctx, threshold, wait=None):
    label, M, px, op, sc, bd, pc, mom20, port_vol, tv = ctx
    ns["DD_THRESHOLD"] = threshold
    ns["DD_RE_WAIT"] = wait if wait is not None else WAITS[0]
    ns.pop("_DD_EVENTS_OUT", None)
    audit = {k: [] for k in ("holdings", "summary", "trades", "ranking",
                             "decisions", "skipped")}
    eq, tc, n, expo = fn(px, op, sc, bd, pc, mom20, port_vol, mode="breadth",
                         target_vol=tv, sizing="invvol", audit=audit)
    m = metrics(eq, f"v2 dd={threshold}", tc, n)
    r = eq.pct_change().dropna()
    return dict(threshold=threshold, wait=wait, cagr=float(m["CAGR%"]), sharpe=float(m["Sharpe"]),
                maxdd=float(m["MaxDD%"]),
                annvol=round(float(r.std() * np.sqrt(252) * 100), 2),
                trades=int(n), tc=float(tc), final=float(eq.iloc[-1]),
                deployed=float(expo) * 100, eq=eq, audit=audit,
                events=list(ns.get("_DD_EVENTS_OUT", [])))


# ------------------------------------------------------------------- gates
def gate_timing(res, ctx, w):
    """G2. Every exit fill at the NEXT session's OPEN, zero at any close, and
    exactly one session after its trigger. Four candidate prices are tested, not
    one, so 'matches the open' can be told apart from 'matches everything'."""
    label, M, px, op, sc, bd, pc, mom20, port_vol, tv = ctx
    cal = list(bd)
    pos = {d: i for i, d in enumerate(cal)}
    SLIP = test_exposure.SLIPPAGE
    n_ok = n_close = n_bad = n_tot = 0
    offsets = []
    for ev in res["events"]:
        if ev["kind"] != "EXIT":
            continue
        i_trig = ev["i"]
        d_fill = cal[i_trig + 1]
        tr = pd.DataFrame(res["audit"]["trades"])
        fills = tr[(tr["date"] == d_fill) & (tr["action"] == "SELL")]
        for _, f in fills.iterrows():
            n_tot += 1
            s = f["symbol"]; fp = float(f["price"])
            cands = {
                "open_t1": op.loc[d_fill].get(s, np.nan) * (1 - SLIP),
                "close_t1": px.loc[d_fill].get(s, np.nan) * (1 - SLIP),
                "close_t0": px.loc[cal[i_trig]].get(s, np.nan) * (1 - SLIP),
                "open_t0": op.loc[cal[i_trig]].get(s, np.nan) * (1 - SLIP)}
            hit = {k: (not np.isnan(v)) and abs(round(v, 2) - fp) <= 0.005
                   for k, v in cands.items()}
            if hit["open_t1"]:
                n_ok += 1
            else:
                n_bad += 1
            if (hit["close_t1"] or hit["close_t0"]) and not hit["open_t1"]:
                n_close += 1
        offsets.append(pos[d_fill] - i_trig)
    ok = (n_bad == 0 and n_close == 0 and all(o == 1 for o in offsets))
    w(f"      exit fills tested {n_tot:5}   at the fill day's OPEN {n_ok:5}   "
      f"NOT at the open {n_bad:3}   at a CLOSE and not the open {n_close:3}   "
      f"trigger->fill offsets {sorted(set(offsets)) if offsets else '[]'}   "
      f"{'PASS' if ok else 'FAIL'}")
    return ok


def gate_reconcile(res, w):
    """G3. Cash + holdings = equity, every day.

    THE ROUNDING BUDGET IS STATED RATHER THAN ABSORBED. audit["summary"] stores
    round(mtm,2), round(cash,2) and round(pv,2) as THREE INDEPENDENT roundings,
    so round(mtm,2)+round(cash,2) can differ from round(mtm+cash,2) by up to one
    paisa BY CONSTRUCTION. An earlier version of this gate tested > 0.01 and
    failed on the UNMODIFIED SHIPPING ARM for that reason alone -- measured max
    difference 0.0100000007, zero days above 0.011. That was a defect in the
    gate, not in the engine, and the tolerance below is derived from the storage
    format rather than chosen to make the gate pass.

    Part (c) is rounding-free and is the reconciliation that actually matters:
    the equity curve is stored unrounded, so total must equal it to half a paisa.
    """
    s = pd.DataFrame(res["audit"]["summary"])
    h = pd.DataFrame(res["audit"]["holdings"])

    # (a) components against the stored total. Budget: 2 roundings x 0.005,
    #     plus float slack.
    a_bad = int((s["mtm"] + s["cash"] - s["total"]).abs().gt(0.0101).sum())

    # (b) the holdings stream against mtm. Each row's value is rounded to 2dp,
    #     so the budget scales with the number of names held that day.
    if len(h):
        byday = h.groupby("date")["value"].sum()
        m = s.set_index("date")["mtm"]
        nper = h.groupby("date").size().reindex(m.index).fillna(0)
        budget = 0.005 * nper + 0.0101
        common = m.index.intersection(byday.index)
        diff = (byday.reindex(m.index).fillna(0.0) - m).abs()
        b_bad = int((diff > budget).sum())
    else:
        b_bad = 0

    # (c) ROUNDING-FREE: the stored total against the unrounded equity curve.
    c_max = float(np.abs(s["total"].to_numpy() - res["eq"].to_numpy()).max())
    c_bad = int(c_max > 0.005)

    ok = (a_bad == 0 and b_bad == 0 and c_bad == 0)
    w(f"      days {len(s):,}   (a) mtm+cash vs total: {a_bad} over budget   "
      f"(b) holdings vs mtm: {b_bad} over budget   "
      f"(c) total vs equity curve: max {c_max:.6f}   {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    t0 = time.time()
    lines = []
    def w(s=""):
        print(s, flush=True)
        lines.append(s)

    fn, ns, applied, srchash = build_patched()
    CELLS = [(th, wt) for th in THRESHOLDS for wt in WAITS]

    w("=" * 120)
    w(" PORTFOLIO DRAWDOWN EXIT -- REVISION 3, PEAK RESET AT RE-ENTRY")
    w("=" * 120)
    w()
    w("  spec  experiments/DRAWDOWN_EXIT_SPEC.txt section 13 (F1-F8 frozen before this file changed)")
    w(f"  patches applied to the SHIPPING function's own source: {', '.join(applied)}")
    w(f"  patched source SHA256 {srchash}")
    w(f"  thresholds {THRESHOLDS}")
    w(f"  re-entry waits {WAITS} trading days -- SWEPT so the wait is not a single chosen number")
    w(f"  grid {len(CELLS)} cells per universe + control   arm v2   REBAL=20   both live universes")
    w()
    w("  WHAT CHANGED FROM REVISION 2. THE PEAK IS NOW RESET to the portfolio")
    w("  value at re-entry. Revisions 1 and 2 failed from ONE cause -- the peak was")
    w("  never reset, so after the March 2020 breach the rule was permanently in")
    w("  breach: rev 1 could never re-enter (entry 33), rev 2 re-entered while")
    w("  still in breach and oscillated for six years (entry 34).")
    w()
    w("  WHAT THE RESET GIVES UP, STATED BEFORE THE NUMBERS. Drawdown is no longer")
    w("  measured from the strategy's ALL-TIME high. A book that falls THRESHOLD,")
    w("  re-enters, and falls THRESHOLD again has lost far more than THRESHOLD from")
    w("  its true peak while the rule sees two ordinary breaches: at 15%, two")
    w("  resets reach a 27.75% true drawdown, three reach 38.6%. THE RULE NOW")
    w("  LIMITS THE LOSS PER EPISODE, NOT THE LOSS OVERALL. It also breaks the")
    w("  coherence argued for in spec section 2: reported MaxDD is still all-time,")
    w("  the trigger is not, and no comparison between them is drawn here.")
    w()
    w("  " + "=" * 116)
    w("  THE GOVERNING CONSTRAINT IS UNCHANGED. The window contains ONE severe")
    w("  drawdown (March 2020). REPEATED FIRINGS WITHIN THAT ONE EPISODE ARE NOT")
    w("  REPEATED TESTS OF THE RULE. Whatever this grid shows, it is readings of")
    w("  one event.")
    w()
    w("  NO ACCEPT RULE. NOTHING CAN BE PROMOTED. MaxDD has NO measured noise floor")
    w("  on any arm and entry 28 could not distinguish it from a random null, so the")
    w("  rule's PRIMARY OBJECTIVE REMAINS UNJUDGEABLE. Only CAGR cost is inferable:")
    w(f"  measured floors n100 {SEED_FLOOR['n100']}, mid {SEED_FLOOR['mid']}.")
    w("  " + "=" * 116)

    res, gates_ok = {}, True
    for tag in UNIVERSES:
        ctx = load(tag)
        label, M, bd = ctx[0], ctx[1], ctx[5]
        w(f"\n{'=' * 120}\n {label} ({tag})   {len(bd):,} trading days   "
          f"{bd[0].date()} .. {bd[-1].date()}\n{'=' * 120}")

        res[tag] = {"control": run(fn, ns, ctx, None)}
        for th, wt in CELLS:
            res[tag][(th, wt)] = run(fn, ns, ctx, th, wt)

        pub = pd.read_csv(M / "v34_comparison.csv")
        pr = pub[pub["Config"].str.startswith("v2 invvol")].iloc[0]
        c = res[tag]["control"]
        pairs = [("CAGR%", c["cagr"], float(pr["CAGR%"])),
                 ("Sharpe", c["sharpe"], float(pr["Sharpe"])),
                 ("MaxDD%", c["maxdd"], float(pr["MaxDD%"])),
                 ("AnnVol%", c["annvol"], float(pr["AnnVol%"])),
                 ("Trades", c["trades"], int(pr["Trades"])),
                 ("TC_Rs", round(c["tc"]), round(float(pr["TC_Rs"]))),
                 ("FinalEq", round(c["final"], 2), round(float(pr["FinalEquity"]), 2))]
        g1 = all(abs(a - b) < 0.01 for _, a, b in pairs)
        w(f"\n  GATE G1 -- control (DD_THRESHOLD=None) vs the published v2 row, read from the CSV")
        for n_, a, b in pairs:
            w(f"    {n_:9} patched {a:>15}   published {b:>15}   "
              f"{'MATCH' if abs(a - b) < 0.01 else 'DIFFERS'}")
        w(f"    G1 {'PASS' if g1 else 'FAIL'}")

        w(f"\n  GATE G2 -- execution timing of every exit fill, four candidate prices")
        g2 = True
        for th, wt in CELLS:
            if not [e for e in res[tag][(th, wt)]["events"] if e["kind"] == "EXIT"]:
                continue
            w(f"    threshold {th}  wait {wt}")
            g2 &= gate_timing(res[tag][(th, wt)], ctx, w)
        w(f"    G2 {'PASS' if g2 else 'FAIL'}")

        w(f"\n  GATE G3 -- daily reconciliation, cash + holdings = equity")
        g3 = gate_reconcile(res[tag]["control"], w)
        for th, wt in CELLS:
            g3 &= gate_reconcile(res[tag][(th, wt)], w)
        w(f"    G3 {'PASS' if g3 else 'FAIL'}  (control + {len(CELLS)} cells)")
        gates_ok &= (g1 and g2 and g3)

    if not gates_ok:
        w(f"\n{'=' * 120}\n STOP CONDITION MET. A CORRECTNESS GATE FAILED.")
        w(" No threshold result is quoted from a harness that cannot pass its own gates.")
        w(f"{'=' * 120}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines) + "\n")
        print(f"\nwritten -> {OUT}")
        return 1

    w(f"\n{'=' * 120}\n ALL CORRECTNESS GATES PASS ON BOTH UNIVERSES\n{'=' * 120}")

    for tag in UNIVERSES:
        base = res[tag]["control"]
        fl = SEED_FLOOR[tag]
        w(f"\n{'=' * 120}\n {UNIVERSES[tag][0]} ({tag}) -- RESULTS\n{'=' * 120}\n")
        w(f"  {'thresh':>7} {'wait':>5} {'CAGR%':>7} {'dCAGR':>7} {'floor':>8} "
          f"{'Sharpe':>7} {'MaxDD%':>8} {'AnnVol%':>8} {'trades':>7} {'TC Rs':>10} "
          f"{'FinalEquity':>13} {'fires':>6} {'exits':>6} {'reent':>6} "
          f"{'days flat':>10} {'%flat':>6}")
        r = base
        w(f"  {'control':>7} {'-':>5} {r['cagr']:7.2f} {0.0:+7.2f} {'control':>8} "
          f"{r['sharpe']:7.2f} {r['maxdd']:8.2f} {r['annvol']:8.2f} {r['trades']:7,} "
          f"{r['tc']:10,.0f} {r['final']:13,.0f} {0:6} {0:6} {0:6} {0:10,} {0.0:6.1f}")
        for th, wt in CELLS:
            r = res[tag][(th, wt)]
            d = r["cagr"] - base["cagr"]
            ex = [e for e in r["events"] if e["kind"] == "EXIT"]
            re_ = [e for e in r["events"] if e["kind"] == "REENTRY"]
            flat = flat_days(r["events"], 1836)
            v = "INSIDE" if abs(d) < fl else "outside"
            w(f"  {th:7} {wt:5} {r['cagr']:7.2f} {d:+7.2f} {v:>8} {r['sharpe']:7.2f} "
              f"{r['maxdd']:8.2f} {r['annvol']:8.2f} {r['trades']:7,} {r['tc']:10,.0f} "
              f"{r['final']:13,.0f} {len(r['events']):6} {len(ex):6} {len(re_):6} "
              f"{flat:10,} {flat / 1836 * 100:6.1f}")
        w(f"\n  'fires' is the TOTAL number of rule actions (exits + re-entries).")
        w(f"  dCAGR is against the control. INSIDE means smaller than the measured")
        w(f"  CAGR floor of {fl} and IS NOT A FINDING in either direction.")
        w(f"  MaxDD AND Sharpe CARRY NO MEASURED FLOOR. No difference in those")
        w(f"  columns may be read as an effect. Spec section 8.")

        w(f"\n  EVERY EXIT AND EVERY RE-ENTRY, WITH DATES AND DAYS FLAT PER EPISODE")
        allyears = []
        for th, wt in CELLS:
            r = res[tag][(th, wt)]
            evs = sorted(r["events"], key=lambda e: e["i"])
            ex = [e for e in evs if e["kind"] == "EXIT"]
            re_ = [e for e in evs if e["kind"] == "REENTRY"]
            w(f"\n    threshold {th}  wait {wt}  --  {len(ex)} exit(s), {len(re_)} re-entry(ies)")
            if not evs:
                w(f"      NEVER FIRED in 1,836 trading days")
                continue
            cal = list(r["eq"].index)
            open_at = None
            for e in evs:
                if e["kind"] == "EXIT":
                    fill = cal[e["i"] + 1]
                    open_at = e["i"] + 1
                    w(f"      EXIT     trigger {e['trigger_date'].date()} (close)  "
                      f"fill {fill.date()} (next open)  dd {e['dd']*100:7.2f}%  "
                      f"held {e['n_held']:2}  pv {e['pv']:12,.0f}")
                    allyears.append(e["trigger_date"].year)
                else:
                    nd = (e["i"] - open_at) if open_at is not None else 0
                    w(f"      REENTRY  {e['trigger_date'].date()}                        "
                      f"        dd {e['dd']*100:7.2f}%  pv {e['pv']:12,.0f}  "
                      f"FLAT {nd} trading day(s)")
                    open_at = None
            if open_at is not None:
                w(f"      (still flat at the window end: {1836 - open_at} trading day(s))")
        w(f"\n    TRIGGER YEARS, all cells pooled:")
        if allyears:
            vc = pd.Series(allyears).value_counts().sort_index()
            for y, n_ in vc.items():
                w(f"      {y}: {n_}")
            w(f"\n    IS ALL THE ACTIVITY A SINGLE CLUSTER? {'YES' if len(vc) == 1 else 'NO'}")
            if len(vc) == 1:
                w(f"      EVERY EXIT ACROSS EVERY CELL FALLS IN {vc.index[0]}. EVERY SUMMARY")
                w(f"      METRIC ABOVE IS A RESTATEMENT OF ONE EPISODE. Repeated firings")
                w(f"      WITHIN that episode are not repeated tests of the rule.")
        else:
            w(f"      NONE -- the rule never fired in any cell.")

    write_outputs(res, CELLS, w)
    w(f"\n  TRIAL COUNT: {len(CELLS)} cells + the control = {len(CELLS)+1} new looks. FLOOR 54 -> 70.")
    w(f"\n  CAPACITY IS NOT MEASURED AND WHIPSAW MAKES IT WORSE, NOT BETTER. Each")
    w("  oscillation sells the ENTIRE book and rebuys it, against a synthetic")
    w("  QUOTE_DEPTH of 10,000,000 shares at flat 15 bps regardless of order size.")
    w("  diagnostics/liquidity_participation.txt records a mid SELL at 1,614.52% of")
    w("  its symbol's prior-20-day median volume. NOTHING HERE CAN SAY WHAT")
    w("  REPEATED FULL LIQUIDATIONS IN MARCH 2020 WOULD ACTUALLY HAVE FILLED AT.")
    w(f"\n  wall clock {time.time() - t0:.0f} sec")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwritten -> {OUT}")
    return 0


def flat_days(events, n_days):
    """Trading days between an exit FILL and the next re-entry (or window end)."""
    tot, open_at = 0, None
    for e in sorted(events, key=lambda x: x["i"]):
        if e["kind"] == "EXIT" and open_at is None:
            open_at = e["i"] + 1
        elif e["kind"] == "REENTRY" and open_at is not None:
            tot += e["i"] - open_at
            open_at = None
    if open_at is not None:
        tot += n_days - open_at
    return tot


def write_outputs(res, CELLS, w):
    cells, events, eqs = [], [], {}
    for tag in UNIVERSES:
        base = res[tag]["control"]
        for key in ["control"] + CELLS:
            r = res[tag][key]
            d = r["cagr"] - base["cagr"]
            fl = SEED_FLOOR[tag]
            ex = [e for e in r["events"] if e["kind"] == "EXIT"]
            re_ = [e for e in r["events"] if e["kind"] == "REENTRY"]
            flat = flat_days(r["events"], 1836)
            cells.append({
                "universe": tag,
                "threshold": ("control" if key == "control" else key[0]),
                "re_entry_wait": ("" if key == "control" else key[1]),
                "CAGR_pct": r["cagr"], "dCAGR_vs_control": round(d, 2),
                "floor_verdict": ("control" if key == "control"
                                  else ("INSIDE" if abs(d) < fl else "outside")),
                "seed_floor_CAGR": fl, "Sharpe": r["sharpe"], "MaxDD_pct": r["maxdd"],
                "AnnVol_pct": r["annvol"], "trades": r["trades"],
                "TC_Rs": round(r["tc"], 2),
                "TC_pct_of_final_equity": round(r["tc"] / r["final"] * 100, 4),
                "final_equity": round(r["final"], 2),
                "deployed_pct": round(r["deployed"], 2),
                "n_fires": len(r["events"]),
                "n_exits": len(ex), "n_reentries": len(re_),
                "days_flat": flat, "pct_of_window_flat": round(flat / 1836 * 100, 2)})
            cal = list(r["eq"].index)
            for e in r["events"]:
                events.append({
                    "universe": tag,
                    "threshold": ("control" if key == "control" else key[0]),
                    "re_entry_wait": ("" if key == "control" else key[1]),
                    "kind": e["kind"],
                    "trigger_date": e["trigger_date"].date(),
                    "fill_date": (cal[e["i"] + 1].date() if e["kind"] == "EXIT"
                                  else ""),
                    "drawdown_pct": round(e["dd"] * 100, 4),
                    "portfolio_value": round(e["pv"], 2), "n_held": e["n_held"]})
            eqs[f"{tag}_" + ("control" if key == "control"
                              else f"th{key[0]}_w{key[1]}")] = r["eq"]
    pd.DataFrame(cells).to_csv(OUT_CELLS, index=False)
    pd.DataFrame(events).to_csv(OUT_EVENTS, index=False)
    e = pd.DataFrame(eqs); e.index.name = "date"; e.to_csv(OUT_EQUITY)
    w(f"\n  OUTPUTS")
    for f in (OUT_CELLS, OUT_EVENTS, OUT_EQUITY):
        w(f"    {f.name:34} {f.stat().st_size:>10,} bytes")


if __name__ == "__main__":
    sys.exit(main())
