#!/usr/bin/env python3
"""tax_acceptance_check.py -- the tax axis is inert at its default. BOTH HALVES.

    run standalone; no caches, no engine, no network

WHY THIS IS TWO CONDITIONS AND NOT ONE
    The stated acceptance test for the tax axis is "with tax off, every existing
    artefact reproduces byte-exact". That test is necessary and it is NOT
    sufficient, for a reason naming.py already writes down about a different
    axis:

        AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE SAME STRING.

    At tax=off every composer contributes "", so a writer that carries the tax
    axis and a writer that has never heard of it emit identical paths. A
    completely empty implementation -- no tax.py, no composer edits, nothing --
    passes the byte-exactness test perfectly. It is passed by doing nothing,
    which is precisely how site 12 survived: a research-profile run and a
    profile-blind writer were byte-identical, and they differed only when
    somebody finally ran `tradeable`.

    So this check asks two questions:

      CONDITION 1  at the default, does every composer emit the SAME STRING it
                   emitted before the tax axis existed?   (nothing moved)
      CONDITION 2  off the default, does every composer MOVE, and does every
                   declared write site still honour its declaration?
                                                          (something is there)

    Condition 1 alone is satisfied by a no-op. Condition 2 alone is satisfied by
    an implementation that renames published files. Neither is the acceptance
    test; both together are.

    CONDITION 3 pins the 365-day long-term boundary. CONDITION 4 (2026-09-25)
    pins the end-of-window rules against hand-worked numbers: the last partial
    financial year settled on the final session; the investable buy & hold
    selling nothing in the headline and paying the strategy's own sell charge
    and tax when sold on the last day; the strategy keeping its holdings in the
    headline and ending flat with end_sale=True.

CONDITION 1 IS MEASURED AGAINST git HEAD, NOT AGAINST A TYPED-IN EXPECTATION
    A hardcoded list of expected default names would be a restatement of what
    this file's author believed the names were -- the same class of defect as a
    report that restates its output instead of deriving it. Instead the
    composers are called in a clean checkout of HEAD and again in the working
    tree, at an all-default selection, and the two strings are compared. A name
    that moves is reported with both spellings.

WHAT THIS DOES NOT COVER, STATED RATHER THAN IMPLIED
    It checks NAMES, not CONTENTS. Byte-exactness of a file's bytes is a
    property of the engine, and the gate that actually tests it is
    heldout_prereg_run.py's reproduction check against the shipped
    v2FINAL_equity.csv. This check cannot run that -- it needs score caches --
    and it says so rather than implying coverage it does not have.

    The retired-universe manifest (171 hashes, deleted from the tree on
    2026-09-24; git show 50562ed:RETIRED_UNIVERSES-manifest.txt) is not verified
    here: its paths are relative to forensic_snapshot_20260911T0100/, which is
    not present in this tree.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The probe body. Run verbatim in HEAD and in the working tree, so the two
# answers cannot diverge through the probe rather than through the composers.
PROBE = r'''
import sys, pathlib, itertools, tempfile, json
R = pathlib.Path(sys.argv[1])
for p in (R, R/"results", R/"nautilus"): sys.path.insert(0, str(p))
import cadence, profiles, arms.registry as arm_reg
try:
    import tax
    HAVE_TAX = True
except ImportError:
    HAVE_TAX = False

D = pathlib.Path(tempfile.mkdtemp())
for c in itertools.product(["","_r40"],["","_tradeable"],["","_tax"]):
    (D / f"v2FINAL_equity{''.join(c)}.csv").write_text("x")
for c in itertools.product(["","_v1"],["","_r40"],["","_tradeable"],["","_tax"]):
    (D / f"chart_midcap150_FINAL{''.join(c)}.png").write_text("x")

out = {}
import naming
out["naming.tail"] = naming.tail()
out["naming.name"] = naming.name("stem", ".csv")
out["selection_suffix"] = arm_reg.selection_suffix()

# SFX is an INLINE expression inside a function body, not a callable, so it is
# read out of the source and evaluated. Indentation is stripped line by line --
# a naive slice carries the function body's indent into eval() and fails with a
# syntax error that LOOKS like a moved name.
src = (R/"results"/"v34_common.py").read_text().splitlines()
i = next(n for n, l in enumerate(src) if l.strip().startswith("SFX = "))
buf, depth = [], 0
for l in src[i:]:
    buf.append(l.strip())
    depth += l.count("(") - l.count(")")
    if depth <= 0 and buf[-1]:
        break
expr = " ".join(buf)[len("SFX = "):].strip()
ns = {"arm_reg": arm_reg, "cadence": cadence, "profiles": profiles}
if HAVE_TAX: ns["_tax"] = tax
try: out["SFX"] = eval(expr, ns)
except Exception as e: out["SFX"] = f"EVALFAIL {type(e).__name__}: {e}"

import audit_step, engine_v2_final, make_chart
import make_combined_universes as mcu
class _U: tag = "midcap150"
out["artefact_tag"] = audit_step.artefact_tag(_U(), "v1")
out["_c"]   = str(engine_v2_final._c(D / "v2FINAL_equity.csv"))
out["_ci_chart"] = str(make_chart._ci(D / "v2FINAL_equity.csv"))
out["_ci_comb"]  = str(mcu._ci(D / "v2FINAL_equity.csv"))
out["chart_path"] = pathlib.Path(str(make_chart.chart_path(D, "chart_midcap150_FINAL", ["v2","v1"]))).name
out["combined_chart_path"] = pathlib.Path(
    str(mcu.combined_chart_path(D, ["midcap150","nifty100"]))).name
out["_c"] = pathlib.Path(out["_c"]).name
out["_ci_chart"] = pathlib.Path(out["_ci_chart"]).name
out["_ci_comb"]  = pathlib.Path(out["_ci_comb"]).name
print(json.dumps(out))
'''


def _run_probe(tree):
    """The probe's dict, evaluated inside `tree` at an all-default selection."""
    f = Path(tempfile.mkdtemp()) / "probe.py"
    # naming: axis-free -- this is the PROBE SOURCE, written to a throwaway temp
    # directory so it can be executed inside another checkout. It is not an
    # artefact, nothing reads it, and it is deleted with the temp dir. Declared
    # rather than left bare because this file was itself the 112th undeclared
    # write call when it landed -- the ratchet exists to stop exactly that, and a
    # checker that adds a violation while enforcing the rule is the worst kind.
    f.write_text(PROBE)
    r = subprocess.run([sys.executable, str(f), str(tree)],
                       capture_output=True, text=True, cwd=str(tree))
    if r.returncode != 0:
        raise RuntimeError(f"probe failed in {tree}:\n{r.stderr[-2000:]}")
    import json
    return json.loads(r.stdout.strip().splitlines()[-1])


def condition_1():
    """Nothing moved at the default. Measured against a clean checkout of HEAD."""
    print("\n  CONDITION 1 -- at tax=off, no composed name moved")
    with tempfile.TemporaryDirectory() as td:
        head = Path(td) / "head"
        r = subprocess.run(["git", "worktree", "add", "--detach", str(head), "HEAD"],
                           cwd=str(ROOT), capture_output=True, text=True)
        if r.returncode != 0:
            print("    UNAVAILABLE: could not create a HEAD worktree")
            print(f"    {r.stderr.strip()}")
            return None
        try:
            before = _run_probe(head)
            after = _run_probe(ROOT)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(head)],
                           cwd=str(ROOT), capture_output=True)
    keys = sorted(set(before) | set(after))
    moved = [(k, before.get(k), after.get(k)) for k in keys
             if before.get(k) != after.get(k)]
    for k in keys:
        mark = "MOVED" if before.get(k) != after.get(k) else "same "
        print(f"    {mark}  {k:<22} {after.get(k)!r}")
    if moved:
        print(f"\n    FAIL: {len(moved)} composed name(s) moved at the default:")
        for k, b, a in moved:
            print(f"      {k}: HEAD {b!r}  ->  working tree {a!r}")
        return False
    print(f"    PASS: {len(keys)} composers, every default name character-identical to HEAD")
    return True


def condition_2():
    """Something is actually there. The axis moves, and declarations honour it."""
    print("\n  CONDITION 2 -- off the default, the axis is real and declared")
    sys.path.insert(0, str(ROOT))
    import naming, tax, cadence, profiles
    import arms.registry as arm_reg

    for m in (cadence, profiles, arm_reg, tax):
        m.set_selection(None)
    base = naming.tail()
    tax.set_selection(True)
    on = naming.tail()
    tax.set_selection(None)
    ok_axis = (base == "" and on == "_tax" and "tax" in naming.AXES)
    print(f"    tail at default {base!r} -> at tax=on {on!r}   "
          f"{'PASS' if ok_axis else 'FAIL'}")

    # tax must be LAST, or every existing non-default artefact is renamed.
    ok_last = naming.AXES[-1] == "tax"
    print(f"    tax is the LAST axis in naming.AXES              "
          f"{'PASS' if ok_last else 'FAIL -- appending is what keeps _r40/_tradeable in place'}")

    # No entry may credit an axis by live reference to AXES.
    # CODE ONLY. The prose above CARRIES quotes the construct it replaced, so a
    # bare substring search over the whole file matches the explanation and
    # reports the defect it is explaining. Comments and docstrings are stripped.
    import io, tokenize
    src = (ROOT / "naming.py").read_text()
    code = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            code.append(tok.string)
    ok_lit = "frozenset(AXES)" not in "".join(code).replace(" ", "")
    print(f"    CARRIES holds no frozenset(AXES) live reference   "
          f"{'PASS' if ok_lit else 'FAIL -- a new axis would be auto-credited unmeasured'}")

    # Every composer a site may name must be measured for tax.
    unmeasured = [k for k, v in naming.CARRIES.items() if "tax" not in v
                  and k != "selection_suffix"]
    ok_meas = not unmeasured
    print(f"    every composer measured for tax                  "
          f"{'PASS' if ok_meas else 'FAIL ' + str(unmeasured)}")

    # THE FROZEN ENGINE MUST STAY OFF THIS AXIS, AND THIS IS HOW IT IS ENFORCED.
    #
    # The phase-1 design said run.py should refuse --tax on for the two retired
    # universes, taken from cadence.py's docstring, which records exactly such a
    # refusal for the cadence axis. THAT IS NOT IMPLEMENTABLE: both were deleted on
    # 2026-09-11, universes/registry.py then held only midcap150 and nifty100, and
    # run.py:396 records that the cadence skip-list was itself dropped because "every
    # universe honours every cadence now". There is no selection left to refuse.
    #
    # What the design was actually protecting is still real -- results/
    # engine_core.py is the frozen engine behind the hash-pinned artefacts and
    # must not grow a tax path. So the refusal is replaced by an assertion on the
    # file itself, which is stronger: it cannot be satisfied by a selection that
    # nobody makes, and it fires on the edit rather than on the run.
    eng = (ROOT / "results" / "engine_core.py").read_text()
    eng_clean = not any(t in eng for t in ("import tax", "tax_util", "tax_enabled",
                                           "Ledger", "CGT_REGIME"))
    print(f"    engine_core.py carries no tax path                "
          f"{'PASS' if eng_clean else 'FAIL -- the frozen engine must stay off this axis'}")

    # The declaration gate must exercise tax, and no declared site may break.
    r = subprocess.run([sys.executable, str(ROOT / "naming_declare_check.py")],
                       capture_output=True, text=True, cwd=str(ROOT))
    txt = r.stdout
    ok_probe = "tax=True" in txt and "_tradeable_tax'" in txt
    nothon = [l for l in txt.splitlines() if "NOT honoured" in l]
    ok_hon = bool(nothon) and nothon[0].strip().endswith("0")
    print(f"    naming_declare_check honour probe carries tax    "
          f"{'PASS' if ok_probe else 'FAIL'}")
    print(f"    declared sites still honour their axes           "
          f"{'PASS' if ok_hon else 'FAIL'}   ({nothon[0].strip() if nothon else 'not reported'})")
    return all([ok_axis, ok_last, ok_lit, ok_meas, eng_clean, ok_probe, ok_hon])


def condition_3():
    """The LTCG holding-period boundary, asserted rather than assumed.

    WHY THIS FIXTURE EXISTS. The rationale below was rewritten 2026-09-19,
    because the one it replaced had been overtaken by the data.

    IT USED TO SAY THE PANEL COULD NOT REACH THE BOUNDARY. It said no run of
    this pipeline ever exercises `is_long = held >= LTCG_HOLD_DAYS` in its True
    state, citing the longest real lot at 326 days with 39 days of headroom, and
    it justified the synthetic lots on that ground -- they were needed BECAUSE
    the real data could not get there. **The panel reached it.** The 2026-09-18
    four-universe runs contain four lots over 365 days:

        nifty100   SOLARINDS   443 days      nifty50   TRENT       588 days
        nifty50    TATACONSUM  445 days      nifty50   TRENT       383 days

    all four routed to `long_old` and taxed at LTCG_RATE["old"]. The True state
    is exercised in production now, on two of four universes.

    THE FIXTURES STAY, AND THE REASON IS A BETTER ONE THAN THE OLD REASON.
    Synthetic lots at 364/365/366 test the boundary DETERMINISTICALLY: exactly
    one day either side, every run, independent of which universes are wired,
    which arm is selected, what the cadence is, or whether any real lot happens
    to land near 365 this month. Real lots at 383 and 588 days exercise the long
    branch but say nothing about where the branch begins -- they would pass
    identically under `>`, under `>= 364` and under `>= 380`. A boundary test
    has to sit ON the boundary, and nothing in the panel is placed there on
    purpose.

    So the old justification is gone and the fixtures are not: they were never
    really a substitute for unreachable data, they were a boundary test, and a
    boundary test does not become unnecessary when the region beyond it becomes
    occupied.

    364 -> short, 365 -> long, 366 -> long.  The comparison is `>=`, so 365 is
    the FIRST long-term day, not the last short-term one. An edit to `>` would
    move every 365-day lot from 12.5% to 20% and no existing artefact would
    change, because no artefact has a lot at EXACTLY 365 days in it -- the four
    real long lots are at 383 and beyond and would survive the edit untouched.
    This condition is still the only thing that would notice.
    """
    import pandas as pd
    sys.path.insert(0, str(ROOT / "results"))
    import tax_util as T

    dates = [pd.Timestamp("2020-01-01"), pd.Timestamp("2027-04-01")]
    buy = pd.Timestamp("2020-01-01")
    cases = ((364, False, "short"), (365, True, "long"), (366, True, "long"))

    print("\n  CONDITION 3 -- the 365-day LTCG boundary (synthetic lots)")
    ok_all = True
    for days, want_long, want_arm in cases:
        led = T.Ledger(dates)
        sell = buy + pd.Timedelta(days=days)
        led.buy("FIXTURE", 10, 100.0, buy)
        led.sell("FIXTURE", 10, 110.0, sell)
        row = led.rows[-1]
        got_arm = ("long_" if row["is_long"] else "short_") + T.regime_of(sell)
        ok = (row["is_long"] is want_long or bool(row["is_long"]) == want_long) \
             and got_arm.startswith(want_arm)
        ok_all = ok_all and ok
        print(f"    held {days:>3}d  is_long={str(bool(row['is_long'])):<5} "
              f"bucket={got_arm:<11} expect {want_arm:<5} "
              f"{'PASS' if ok else 'FAIL'}")
        assert bool(row["is_long"]) == want_long, (
            f"LTCG boundary moved: a lot held {days} days reported "
            f"is_long={bool(row['is_long'])}, expected {want_long}. "
            f"tax_util.LTCG_HOLD_DAYS={T.LTCG_HOLD_DAYS}, comparison must stay "
            f">=. Real lots now cross 365 (four of them, nifty100 and nifty50) "
            f"but none sits AT it -- the nearest is 383 -- so nothing else in "
            f"the tree would have caught a one-day move in the boundary.")
        assert got_arm.startswith(want_arm), (
            f"LTCG boundary bucket wrong: {days} days -> {got_arm}, "
            f"expected a {want_arm}_* bucket.")

    assert T.LTCG_HOLD_DAYS == 365, (
        f"LTCG_HOLD_DAYS is {T.LTCG_HOLD_DAYS}, not 365. Section 3.2 of the "
        f"reference document fixes it at 365 "
        f"(is_long = held_days >= LTCG_HOLD_DAYS).")
    print(f"    LTCG_HOLD_DAYS == 365                            PASS")
    return ok_all


def condition_4():
    """The end-of-window rules of 2026-09-25, each against a hand-worked number.

      4a  the last, partial financial year is SETTLED on the final session, after
          its fills, on realised gains, with the document's netting and the full
          annual exemption; an earlier year is still assessed under section 3(9)
      4b  the investable buy & hold: the headline sells nothing, so it pays no
          tax and no sell charge; "sold on the last day" pays the strategy's own
          sell charge (calc_tc) and long-term tax on the realised gain
      4c  the strategy: the headline keeps its holdings at the end; end_sale=True
          ends with none, and its tax is exactly tax_for_fy over what it realised

    Synthetic data only: no caches, no panel, no network.
    """
    import numpy as np
    import pandas as pd
    for p in (ROOT, ROOT / "results"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import tax_util as T
    import bh_held
    import test_exposure as TE
    from engine_core import precompute

    print("\n  CONDITION 4 -- end-of-window settlement and the last-day sale")

    # ---- 4a. Partial-year settlement, worked by hand ------------------------
    dates = pd.bdate_range("2026-03-02", "2026-05-29")
    led = T.Ledger(dates)
    fills = {   # date -> [(side, sym, qty, price)]
        pd.Timestamp("2026-03-10"): [("SELL", "D", 10, 150.0)],
        pd.Timestamp("2026-04-06"): [("BUY", "A", 100, 100.0), ("BUY", "C", 50, 200.0)],
        pd.Timestamp("2026-05-04"): [("SELL", "A", 100, 110.0), ("SELL", "B", 1000, 400.0)],
        pd.Timestamp("2026-05-05"): [("SELL", "C", 50, 190.0)],
    }
    led.buy("D", 10, 100.0, pd.Timestamp("2025-04-10"))      # FY2025-26, short
    led.buy("B", 1000, 100.0, pd.Timestamp("2025-01-15"))    # held 474 days, long
    paid = {}
    for d in dates:
        due = led.due_on(d)
        for side, sym, q, pr in fills.get(d, []):
            (led.buy if side == "BUY" else led.sell)(sym, q, pr, d)
        due += led.due_on(d, after_fills=True)
        if due:
            paid[d] = due
    # FY2025-26: short_new +500 -> 500 x 20% = 100, assessed 2026-03-31 (a
    #   Tuesday, inside FY2025-26, so after that day's fills).
    # FY2026-27: short_new +1,000 - 500 = 500 -> 100; long_new 300,000 less the
    #   Rs 1,25,000 exemption = 175,000 x 12.5% = 21,875; total 21,975, settled
    #   on the last session 2026-05-29.
    want = {pd.Timestamp("2026-03-31"): 100.0, pd.Timestamp("2026-05-29"): 21_975.0}
    ok_a = (set(paid) == set(want)
            and all(abs(paid[d] - want[d]) < 1e-6 for d in want)
            and led.settled_at_end == {2026})
    stmt, _ = T.liability_schedule(pd.DataFrame(led.rows), dates)
    r26 = stmt[stmt["fy"] == 2026].iloc[0]
    ok_a = ok_a and bool(r26["assessed"]) and r26["assessed_basis"] == "backtest end" \
        and abs(float(r26["total_tax"]) - 21_975.0) < 1e-6
    print(f"    4a partial year: paid {dict((str(k.date()), round(v, 2)) for k, v in paid.items())}"
          f"  expect {{'2026-03-31': 100.0, '2026-05-29': 21975.0}}  "
          f"{'PASS' if ok_a else 'FAIL'}")
    assert ok_a, f"end-of-window settlement: paid {paid}, expected {want}"

    # ---- 4b. Buy & hold, headline and last-day sale, worked by hand ---------
    bd = pd.bdate_range("2025-05-01", "2026-05-29")
    px = pd.DataFrame({"X": 100.0, "Y": 200.0}, index=bd)
    op = px.copy()
    px.iloc[-1] = [140.0, 170.0]
    op.iloc[-1] = [150.0, 180.0]
    r = bh_held.held_lots(px, op, bd)
    s = TE.SLIPPAGE
    cash = TE.START_CAPITAL
    qty, bpx = {}, {}
    # The construction's own rule: equal rupees per name, a name skipped when
    # the cash left cannot pay for it and its charge. Here X's buy charge leaves
    # too little for Y, so only X is held -- the hand calculation follows suit.
    for sym, p0 in (("X", 100.0), ("Y", 200.0)):
        pr = p0 * (1 + s)
        q = int((TE.START_CAPITAL / 2) // pr)
        cost = q * pr + TE.calc_tc(pr, q, "BUY")
        if cash < cost:
            continue
        cash -= cost
        qty[sym], bpx[sym] = q, pr
    close_n = {"X": 140.0, "Y": 170.0}
    head = cash + sum(qty[k] * close_n[k] for k in qty)
    proceeds = sell_tc = gain = 0.0
    for sym, pN in ((k, {"X": 150.0, "Y": 180.0}[k]) for k in qty):
        pr = pN * (1 - s)
        proceeds += qty[sym] * pr
        sell_tc += TE.calc_tc(pr, qty[sym], "SELL")
        gain += qty[sym] * (round(pr, 2) - round(bpx[sym], 2))
    tax = max(gain - 125_000.0, 0.0) * 0.125     # held 393 days: long, new rate
    last = cash + proceeds - sell_tc - tax
    ok_b = (abs(r["eq_headline"].iloc[-1] - head) < 1e-6
            and abs(r["eq_last_day"].iloc[-1] - last) < 1e-6
            and abs(r["detail"]["sell_tc"] - sell_tc) < 1e-9 and sell_tc > 0
            and abs(r["detail"]["tax"] - tax) < 1e-6 and tax > 0
            and bh_held.calc_tc is TE.calc_tc)
    print(f"    4b buy & hold: headline {r['eq_headline'].iloc[-1]:,.2f} (expect {head:,.2f}, "
          f"no tax, no sell charge); last day {r['eq_last_day'].iloc[-1]:,.2f} (expect "
          f"{last:,.2f}: sell charges {sell_tc:,.2f}, tax {tax:,.2f})  "
          f"{'PASS' if ok_b else 'FAIL'}")
    assert ok_b, "buy & hold headline or last-day figure does not match the hand-worked case"

    # ---- 4c. The strategy engine, headline against last-day sale ------------
    bd = pd.bdate_range("2026-01-01", "2026-05-29")
    # Ten names, so a TOP_N=8 selection is possible; constant scores, so the
    # engine buys once and never sells until the end; every price rises, so the
    # last-day sale realises a short-term gain inside FY2026-27.
    syms = [f"S{k}" for k in range(10)]
    steps = np.arange(len(bd))
    px = pd.DataFrame({sym: 100.0 * (1 + (k + 1) * 0.0005) ** steps
                       for k, sym in enumerate(syms)}, index=bd)
    op = px.shift(1).fillna(px.iloc[0])
    sc = pd.DataFrame({sym: float(10 - k) for k, sym in enumerate(syms)}, index=bd)
    pc = precompute(px, vol_win=5)
    pc["vol"] = pc["vol"].fillna(0.2).replace(0, 0.2)
    mom20 = px / px.shift(20) - 1
    out = {}
    for end_sale in (False, True):
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        eq, tc, n, _ = TE.backtest_exposure(px, op, sc, bd, pc, mom20, mode="none",
                                            audit=a, tax_enabled=True, end_sale=end_sale,
                                            participation_cap=None)
        led = a["tax"]["ledger"]
        want_tax = sum(T.tax_for_fy(fy, b)["total_tax"] for fy, b in led.realized.items())
        out[end_sale] = dict(held=a["summary"][-1]["n_stocks"], tax=a["tax"]["cum_tax"],
                             want=want_tax, cash=a["summary"][-1]["cash"], final=eq.iloc[-1])
    h, l = out[False], out[True]
    ok_c = (h["held"] > 0 and l["held"] == 0
            and abs(h["tax"] - h["want"]) < 1e-6 and abs(l["tax"] - l["want"]) < 1e-6
            and l["tax"] > h["tax"] and abs(l["final"] - l["cash"]) < 0.01)
    print(f"    4c strategy: headline holds {h['held']} at the end, tax {h['tax']:,.2f}; "
          f"last day holds {l['held']}, tax {l['tax']:,.2f} = tax_for_fy over realised "
          f"{l['want']:,.2f}  {'PASS' if ok_c else 'FAIL'}")
    assert ok_c, f"engine end-of-window behaviour wrong: {out}"
    return ok_a and ok_b and ok_c


def main():
    print("=" * 78)
    print(" TAX AXIS ACCEPTANCE -- inert at default, real off it")
    print("=" * 78)
    c1 = condition_1()
    c2 = condition_2()
    c3 = condition_3()
    c4 = condition_4()

    print("\n  NOT COVERED BY THIS CHECK, AND NOT IMPLIED:")
    print("    - file CONTENTS. This checks names. The contents gate is")
    print("      heldout_prereg_run.py's reproduction check against the shipped")
    print("      v2FINAL_equity.csv, which needs score caches and is not run here.")
    print("    - the retired-universe manifest's 171 hashes: not checked (the "
          "manifest was deleted from the tree on 2026-09-24).")

    ok = (c1 is not False) and c2 and c3 and c4
    print("\n" + "=" * 78)
    print(f" RESULT: {'PASS' if ok else 'FAIL'}"
          + ("   (condition 1 UNAVAILABLE -- see above)" if c1 is None else ""))
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
