"""
fixed_capital_test.py -- the fixed-capital axis (fixed_axis.py).

    ./venv/bin/python fixed_capital_test.py          # every case, with its figures
    ./venv/bin/python fixed_capital_test.py --quiet  # PASS/FAIL lines only

    1. names and refusals: "" and "_fixed" / "@fixed"; the engine and run.py refuse
       the axis with --dd and with the stop arms v5 and v6
    2. the default path: fixed_capital unset and fixed_capital=False give the same run
    a. purchases never lift invested value above the book: on every execution day,
       after all fills, valued at that open, held value <= max(book, held value
       before that day's buys). nifty200, pit, tradeable, v1 to v4, tax off and on
   b1. nifty500 v4, pit, tradeable, tax off and on: the fixed and compounded runs
       are identical, every fill, cash and equity value, up to the session before
       the first execution day whose open equity is above the base. That day is
       found from the run.
   b2. a synthetic falling panel on which equity never passes the base: the two
       runs are identical over the whole window, v1 and v4, tax off and on
    c. every run above reconciles from its own fills: end equity = base + realised
       P&L + final unrealised P&L - charges - tax, within Rs 1. Realised P&L is on
       average cost; prices and charges come from the run's full-precision cost
       trail (audit["costs"]). The yearly table is checked as well, as a format
       check only: base + the sum of the yearly rupee P&L = end equity, in Decimal.

The real-data cases read the cached pit score panels (cache/), as the engines do;
nothing under data/ is read or written by this file, and nothing is written at all.
Exit 0 when every case passes, 1 otherwise.
"""
import contextlib
import io
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results", ROOT / "nautilus", ROOT / "tools"):
    sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd

import fixed_axis
import fixed_capital as fc
from engine_core import precompute
from numerics import rolling_std
from test_exposure import backtest_exposure

QUIET = "--quiet" in sys.argv
RESULTS = []
BASE = 1_000_000.0
TOL_RS = 1.0          # case c
TOL_BOOK = 0.01       # case a: rupees of float rounding in a sum over held names


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
          flush=True)


def blank():
    a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    a["costs"] = {"fills": [], "days": []}
    return a


# ---------------------------------------------------------------------------
# case c: reconcile a run from its own fills
# ---------------------------------------------------------------------------
def reconcile(audit, eq, px, base):
    """(gap in rupees, realised, unrealised, charges, tax) for one run."""
    held, cost = {}, {}
    realised = charges = 0.0
    for f in audit["costs"]["fills"]:
        s, q, p = f["symbol"], f["qty"], f["fill_price"]
        charges += f["charges"]
        if f["side"] == "BUY":
            cost[s] = cost.get(s, 0.0) + q * p
            held[s] = held.get(s, 0) + q
        else:
            avg = cost[s] / held[s]
            realised += q * (p - avg)
            cost[s] -= q * avg
            held[s] -= q
            if held[s] == 0:
                del held[s], cost[s]
    last = px.loc[eq.index[-1]]
    unrealised = sum(q * float(last[s]) - cost[s] for s, q in held.items()
                     if not np.isnan(last.get(s, np.nan)))
    tax = float(audit["tax"]["cum_tax"]) if "tax" in audit else 0.0
    gap = base + realised + unrealised - charges - tax - float(eq.iloc[-1])
    return gap, realised, unrealised, charges, tax


RECONCILED = []


def check_c(label, audit, eq, px, base=BASE):
    gap, r, u, c, t = reconcile(audit, eq, px, base)
    fmt_ok = fc.yearly_sum_check(eq, base)
    RECONCILED.append((label, abs(gap) <= TOL_RS and fmt_ok, gap, r, u, c, t, fmt_ok))


# ---------------------------------------------------------------------------
# real-data cells
# ---------------------------------------------------------------------------
class Cell:
    """One pit, tradeable universe, loaded as run.py --survivorship pit
    --profile tradeable loads it (tools/pit_noise_band.select_pit)."""

    def __init__(self, tag):
        import config
        import profiles
        from config import read_table
        with contextlib.redirect_stdout(io.StringIO()):
            import pit_noise_band
            self.u = u = pit_noise_band.select_pit(tag)
            p = read_table(config.require_cache(u.score_cache, what=f"{tag} pit"),
                           parse_dates=["date"])
        self.px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
        self.op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
        self.sc = p.pivot_table(index="date", columns="symbol", values="score")
        self.bd = u.trading_days(self.px.index)
        self.pc = precompute(self.px)
        self.mom20 = self.px / self.px.shift(20) - 1
        idx = (1 + self.px.pct_change().mean(axis=1).fillna(0)).cumprod()
        self.port_vol = rolling_std(idx.pct_change(), 60) * np.sqrt(252)
        self.tv = self.port_vol.loc[self.bd].median()
        with contextlib.redirect_stdout(io.StringIO()):
            self.capkw = profiles.cap_kwargs(u)

    def run(self, arm, tax, fixed):
        import arms.registry as ar
        a = ar.ARMS[arm]
        audit = blank()
        with contextlib.redirect_stdout(io.StringIO()):
            eq, tc, n, _ = backtest_exposure(
                self.px, self.op, self.sc, self.bd, self.pc, self.mom20, self.port_vol,
                target_vol=self.tv, rebal=20, tax_enabled=tax, audit=audit,
                mode=a.mode, sizing=a.sizing, drawdown_stop=None, dd_overlay=None,
                fixed_capital=fixed, start_capital=int(BASE), **self.capkw)
        return eq, audit


def case_a():
    C = Cell("nifty200")
    worst, n_days, n_res, n_short = [], 0, 0, 0
    for arm in ("v1", "v2", "v3", "v4"):
        for tax in (False, True):
            eq, au = C.run(arm, tax, True)
            rows = au["fixed"]
            over = [r for r in rows
                    if r["held_after"] > max(r["book"], r["held_before_buys"]) + TOL_BOOK]
            n_days += len(rows)
            n_res += sum(1 for r in rows if r["reserve"] > 0)
            n_short += sum(1 for s in au["skipped"] if "fixed-capital reserve" in s["detail"])
            margin = max(r["held_after"] - max(r["book"], r["held_before_buys"]) for r in rows)
            worst.append((arm, tax, len(over), margin))
            case(f"a nifty200 pit tradeable {arm} tax {'on' if tax else 'off'}: purchases "
                 f"never lift invested value above the book", not over and len(rows) > 0,
                 f"{len(rows)} execution days, {len(over)} over; largest held_after - "
                 f"max(book, held before) Rs {margin:,.2f}; reserve > 0 on "
                 f"{sum(1 for r in rows if r['reserve'] > 0)} days")
            check_c(f"nifty200 {arm} tax {'on' if tax else 'off'} fixed", au, eq, C.px)
    case("a the reserve bites: some day holds profit back and some buy is refused for it",
         n_res > 0 and n_short > 0,
         f"{n_res} execution days with a reserve, {n_short} buys skipped because of it, "
         f"over {n_days} execution days in 8 runs")


def _first_above(rows, base):
    for r in rows:
        if r["port_val"] > base:
            return pd.Timestamp(r["date"])
    return None


def _same_prefix(e0, a0, e1, a1, cut):
    """Every fill, every day's cash and every equity value before `cut`."""
    pre = e0.index < cut
    eq_ok = bool((e0[pre].to_numpy() == e1[pre].to_numpy()).all())
    f0 = [f for f in a0["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
    f1 = [f for f in a1["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
    d0 = [d for d in a0["costs"]["days"] if pd.Timestamp(d["date"]) < cut]
    d1 = [d for d in a1["costs"]["days"] if pd.Timestamp(d["date"]) < cut]
    return eq_ok and f0 == f1 and d0 == d1, int(pre.sum()), len(f0)


def case_b1():
    C = Cell("nifty500")
    for tax in (False, True):
        e0, a0 = C.run("v4", tax, False)
        e1, a1 = C.run("v4", tax, True)
        cut = _first_above(a1["fixed"], BASE)
        if cut is None:
            case(f"b1 nifty500 v4 tax {'on' if tax else 'off'}", False,
                 "open equity never passed the base; the case has no cut")
            continue
        same, n_days, n_fills = _same_prefix(e0, a0, e1, a1, cut)
        after = int((e0[e0.index >= cut] != e1[e1.index >= cut]).sum())
        n_exec = sum(1 for r in a1["fixed"] if pd.Timestamp(r["date"]) < cut)
        case(f"b1 nifty500 pit tradeable v4 tax {'on' if tax else 'off'}: identical up to "
             f"the session before {cut.date()}", same and n_days > 0,
             f"{n_days} sessions, {n_exec} execution days, {n_fills} fills identical; "
             f"{after} of {int((e0.index >= cut).sum())} later sessions differ")
        check_c(f"nifty500 v4 tax {'on' if tax else 'off'} compounded", a0, e0, C.px)
        check_c(f"nifty500 v4 tax {'on' if tax else 'off'} fixed", a1, e1, C.px)


# ---------------------------------------------------------------------------
# synthetic panels
# ---------------------------------------------------------------------------
SYMS = [f"S{k:02d}" for k in range(40)]
WARM = pd.bdate_range("2020-08-03", "2020-12-31")
DATES = pd.bdate_range("2021-01-01", "2021-12-31")


def falling_panel():
    idx = WARM.append(DATES)
    rng = np.random.default_rng(7)
    out = {}
    for k, s in enumerate(SYMS):
        r = -0.0012 - 0.00002 * k + 0.004 * rng.standard_normal(len(idx))
        out[s] = 100.0 * (1 + 0.02 * k) * np.cumprod(1 + r)
    px = pd.DataFrame(out, index=idx)
    op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
    # Scores redrawn every session, so each rebalance turns the book over.
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=SYMS)
    return px, op, sc


def synth_run(px, op, sc, mode, sizing, tax, fixed):
    audit = blank()
    kw = {} if fixed is None else {"fixed_capital": fixed}
    eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                     mode=mode, sizing=sizing, audit=audit, rebal=20,
                                     participation_cap=None, drawdown_stop=None,
                                     dd_overlay=None, tax_enabled=tax,
                                     start_capital=int(BASE), **kw)
    return eq, audit


def case_b2():
    px, op, sc = falling_panel()
    for mode, sizing, arm in (("none", "invvol", "v1"), ("breadth", "provol", "v4")):
        for tax in (False, True):
            e0, a0 = synth_run(px, op, sc, mode, sizing, tax, False)
            e1, a1 = synth_run(px, op, sc, mode, sizing, tax, True)
            never = (all(r["port_val"] <= BASE for r in a1["fixed"])
                     and bool((e1 <= BASE).all()))
            same, n_days, n_fills = _same_prefix(e0, a0, e1, a1, DATES[-1] + pd.Timedelta(days=1))
            case(f"b2 synthetic falling panel {arm} tax {'on' if tax else 'off'}: equity never "
                 f"passes the base and the two runs are identical", never and same and n_fills > 0,
                 f"{n_days} sessions, {n_fills} fills; end equity Rs {e1.iloc[-1]:,.2f}; "
                 f"highest open equity Rs {max(r['port_val'] for r in a1['fixed']):,.2f}")
            check_c(f"synthetic {arm} tax {'on' if tax else 'off'} compounded", a0, e0, px)
            check_c(f"synthetic {arm} tax {'on' if tax else 'off'} fixed", a1, e1, px)


def case_names_refusals():
    d = (fixed_axis.suffix(), fixed_axis.segment(), fixed_axis.label())
    fixed_axis.set_selection(True)
    on = (fixed_axis.suffix(), fixed_axis.segment())
    fixed_axis.set_selection(None)
    case("1 names", d == ("", "", "") and on == ("_fixed", "@fixed"), f"off {d}, on {on}")

    px, op, sc = falling_panel()
    import arms.registry as ar
    import dd_axis
    refused = []
    for name, stop, dd in (("drawdown_stop", ar.DrawdownStop(threshold=0.5), None),
                           ("dd_overlay", None, dd_axis.make(20))):
        try:
            backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                              mode="none", rebal=20, participation_cap=None,
                              fixed_capital=True, drawdown_stop=stop, dd_overlay=dd)
        except ValueError:
            refused.append(name)
    import run
    cli = []
    for argv in (["--fixed-capital", "--dd", "20", "--list"],
                 ["--fixed-capital", "--arm", "v5", "--list"]):
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                run.main(argv)
        except SystemExit as e:
            if e.code == 2 and "--fixed-capital cannot run with" in err.getvalue():
                cli.append(argv[1])
    # run.main records the selections it parsed before refusing; restore them.
    fixed_axis.set_selection(None)
    dd_axis.set_selection(None)
    case("1 refusals: the engine and run.py refuse the axis with --dd and the stop arms",
         refused == ["drawdown_stop", "dd_overlay"] and cli == ["--dd", "--arm"],
         f"engine refused {refused}; run.py refused {cli}")


def case_default():
    px, op, sc = falling_panel()
    e0, a0 = synth_run(px, op, sc, "none", "invvol", False, None)
    e1, a1 = synth_run(px, op, sc, "none", "invvol", False, False)
    case("2 default path: fixed_capital unset equals fixed_capital=False",
         bool((e0.to_numpy() == e1.to_numpy()).all()) and a0["costs"] == a1["costs"]
         and "fixed" not in a0)


def main():
    case_names_refusals()
    case_default()
    case_b2()
    case_a()
    case_b1()
    for label, ok, gap, r, u, c, t, fmt_ok in RECONCILED:
        case(f"c {label}: end equity = base + realised + unrealised - charges - tax", ok,
             f"gap Rs {gap:+.4f}; realised {r:,.2f}, unrealised {u:,.2f}, charges "
             f"{c:,.2f}, tax {t:,.2f}; yearly table sums to end equity: {fmt_ok}")
    print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
