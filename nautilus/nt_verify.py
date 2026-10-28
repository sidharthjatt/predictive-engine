"""
nt_verify.py -- one command that reports the true state of the Nautilus port.

Runs the port, compares it against the reference engine on three levels, and
prints what matches, what does not, and by how much. Nothing here is hardcoded:
every number is produced by the run it describes.

Run: ./venv/bin/python nautilus/nt_verify.py --universe=nifty100 [--arm=v3] [--rebal=3]
                                             [--dd=20 [--dd-m=5] [--dd-floor=25]]
                                             [--capital=5000000]

--arm=NAME verifies that arm (default v2): the port runs with the arm's mode and
sizing, the reference copy (nt_attribution) takes the same, and the reference
files are the arm's own audit trail, named by audit_step.artefact_tag. Added
2026-09-26; before that every run verified v2.

--rebal=N at a non-default cadence REPORTS the port-vs-vectorised gap at that
cadence and exits 0. It does not gate: the share-level verdict below is the
default-cadence certification and is unchanged. See KNOWN_ISSUES.md for the gap
measured at cadences 20, 3 and 1 on 2026-09-23.

Both sides size every buy at the decision session's close (since 2026-10-28), so
neither values its book at the open. The quote-mid exemption that covered the
port's open valuation (added 2026-09-29, pass I) went with it.

--buy-shortfall=trim|refuse picks the buy rule (buy_shortfall.py) for the port,
the reference copy and the reference trail's name; the default is
config.BUY_SHORTFALL.

THE VERDICT. Both sides price every fill with slippage.fill_price, to the paisa.
The port and the reference copy must hold the same names and quantities at every
rebalance and fill the same orders (name, side, quantity) in every rebalance
period: n of n, with no exemption. Any period that differs is unexplained and
fails.

Since 2026-10-28 there is one run of each side. Until then the port quoted on
NSE's dated tick (0.05 for most of the window), and the verdict re-ran both sides
on a uniform 0.01 grid to separate tick rounding from logic. The dated tick took
its price band from the adjusted close, which carries later splits and bonuses,
so it was removed, and the paisa run is now the only one.
"""
import contextlib
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import nt_data
import nt_run

import nt_attribution
from config import read_table  # the one CSV/parquet reader: config.read_table

# Selected by --universe on the command line. THE CHOICES ARE THE REGISTRY, not a
# written-down tuple: the tuple used to name two retired universes, and the
# default was one of their tags, so this module raised KeyError at import the day
# they were deleted. The reference CSVs, the price panel and the score parquet all move
# together, because a verification is only meaningful when both sides read the same
# universe.
# An unknown tag, including a retired short tag, exits with the list of valid
# universes rather than falling back to the default.
from universes.registry import argv_universes, check_tags
_picked = check_tags(argv_universes(sys.argv), nt_run.UNIVERSES)
UNIVERSE = _picked[-1] if _picked else next(iter(nt_run.UNIVERSES))
U = nt_run.UNIVERSES[UNIVERSE]
M = U["metrics"]
TAG = U["tag"]
REBAL = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--rebal=")), None)

from arms.registry import ALL_ARMS as _ARMS
_ARM_NAME = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--arm=")), "v2")
if _ARM_NAME not in _ARMS:
    raise SystemExit(f"unknown arm {_ARM_NAME!r}; known: {', '.join(_ARMS)}")
ARM = _ARMS[_ARM_NAME]
# THE ARM'S OWN KWARGS: mode and sizing, and for v5/v6 the drawdown stop, which
# the port and the reference copy then both run. Sealed for a stop arm unless the
# test fixture is set (arms.registry.FIXTURE_ENV).
_ARM_KW = ARM.kwargs

# --dd=L [--dd-m=m] [--dd-floor=F]: THE DRAWDOWN-LIMIT AXIS. The selection is set
# here, so the reference trail is found by the writer's own name (_ref_tag), and the
# overlay rides in _ARM_KW to the port and to both reference re-runs. This command
# runs at research profile and tax off only; a cell with the axis on under tax or
# the tradeable profile is outside port verification (the port has no tax ledger
# and no participation cap).
def _flag(name):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), None)


if _flag("dd") is not None:
    import dd_axis as _dda
    _DD = _dda.make(float(_flag("dd")),
                    float(_flag("dd-m")) if _flag("dd-m") is not None else None,
                    float(_flag("dd-floor")) if _flag("dd-floor") is not None else None)
    if ARM.stop is not None:
        raise SystemExit("--dd cannot be used with a stop arm (v5/v6)")
    _dda.set_selection(_DD)
    _ARM_KW = dict(ARM.kwargs, dd_overlay=_DD)
    print(f"  drawdown-limit axis: {_dda.label()} -- research profile, tax off")
elif _flag("dd-m") is not None or _flag("dd-floor") is not None:
    raise SystemExit("--dd-m and --dd-floor need --dd")

# --capital=RUPEES: THE STARTING-CAPITAL AXIS. Selected here, so the port's starting
# balance (nt_run), the reference copy's cash (nt_attribution) and the reference
# trail's name (_ref_tag) all follow it. Research profile, tax off, as every cell here.
if _flag("capital") is not None:
    import capital_axis as _capa
    _capa.set_selection(int(_flag("capital")))
    print(f"  starting capital: Rs {_capa.selected():,}")

# --buy-shortfall=trim|refuse: THE BUY RULE. Selected here, so the port
# (nt_strategy), the reference copy (nt_attribution) and the reference trail's
# name (_ref_tag, through audit_step.artefact_tag) all follow it.
import buy_shortfall as _bsf
if _flag("buy-shortfall") is not None:
    _bsf.set_selection(_flag("buy-shortfall"))
RULE = _bsf.selected()
# THE STOP'S DATES, compared exactly: these events on these days, on both sides.
STOP_KEY_EVENTS = ("trigger", "exit fills", "flat", "re-entry order", "re-entry filled",
                   "peak reset", "trigger on the last session")


def stop_dates(rows):
    """{(date, event)} for the stop's key events."""
    return {(pd.Timestamp(r["date"]).normalize(), r["event"]) for r in rows
            if r["event"] in STOP_KEY_EVENTS}


def _ref_tag():
    """The arm's audit-trail tag at the default cadence and profile, tax off.

    v2 is the unsuffixed TAG the reference files have always used; the other arms
    are suffixed by the writer's own rule."""
    sys.path.insert(0, str(ROOT / "results"))
    import audit_step
    from universes.registry import REGISTRY
    return audit_step.artefact_tag(REGISTRY[UNIVERSE], ARM)


def compare(a_all, b_all, dates):
    """Compare two {date: {symbol: qty}} maps over the same rebalance dates.

    Returns (mismatches, symbol-set mismatches, quantity-only mismatches, errors%).
    """
    mism = sym_mism = qty_only = 0
    worst = []
    for d in dates:
        a, b = a_all.get(d, {}), b_all.get(d, {})
        if a == b:
            continue
        mism += 1
        if set(a) != set(b):
            sym_mism += 1
        else:
            qty_only += 1
            for s in a:
                if a[s] != b[s]:
                    worst.append(abs(a[s] - b[s]) / max(b[s], 1) * 100)
    return mism, sym_mism, qty_only, worst


def report(label, stats, n):
    mism, sym_mism, qty_only, worst = stats
    print(f"\n  {label}")
    print(f"    identical holdings      : {n - mism} of {n}")
    print(f"    differing by symbol set : {sym_mism}")
    print(f"    differing by quantity   : {qty_only}")
    if worst:
        w = pd.Series(worst)
        print(f"    quantity error: median {w.median():.2f}%  max {w.max():.2f}%")


def port_holdings(strat):
    """{rebalance_date: {symbol: qty}} plus the rebalance dates themselves.

    THE REBALANCE DATES COME FROM `decisions`, NOT FROM `holdings_log`.
    holdings_log emits one row per HELD symbol, so a rebalance that starts from an
    empty portfolio -- 2019-01-01, the first one -- emits nothing at all. Counting
    its distinct dates therefore reported 92 against the reference's 93 and made a
    bookkeeping artefact look like a missing rebalance. There is no missing
    rebalance: the run itself reports 93.
    """
    dates = [pd.Timestamp(d["decided_on"]) for d in strat.decisions]
    # COLUMNS GIVEN, because a stop arm can take every decision from an empty book,
    # and then holdings_log has no rows at all.
    hp = pd.DataFrame(strat.holdings_log, columns=["date", "symbol", "qty"])
    hp["date"] = pd.to_datetime(hp["date"])
    port = {d: {} for d in dates}
    for _, r in hp.iterrows():
        port[r["date"]][r["symbol"]] = int(r["qty"])
    return dates, port


def arm(panel, dates, **kwargs):
    """Holdings from one arm of the reference re-implementation, on `dates`."""
    out = {}
    nt_attribution.run(*panel, holdings_out=out, **kwargs)
    return {d: out.get(d, {}) for d in dates}


def fills_by_period(rows, dates):
    """{rebalance date: {(symbol, side): (qty, price)}} from fill rows.

    A fill belongs to the last rebalance decided before its date, so a
    rebalance's period holds the orders it released the next morning. Partial
    fills of one order are summed; the price is their quantity-weighted mean."""
    ds = sorted(dates)
    out = {d: {} for d in ds}
    for r in rows:
        when = pd.Timestamp(r["date"]).normalize()
        prior = [d for d in ds if d < when]
        if not prior:
            raise ValueError(f"a fill on {when.date()} precedes the first rebalance")
        key = (r["symbol"], r["action"])
        q0, p0 = out[prior[-1]].get(key, (0, 0.0))
        q = q0 + int(r["qty"])
        out[prior[-1]][key] = (q, (q0 * p0 + int(r["qty"]) * float(r["price"])) / q)
    return out


def compare_fills(a, b):
    """[(rebalance date, rupees)] for every period whose fills differ, a against b.

    rupees is the value of the differing shares: |qty difference| per (symbol,
    side) at side a's price, or side b's where a has no such fill."""
    out = []
    for d in a:
        fa, fb = a[d], b.get(d, {})
        if {k: q for k, (q, _) in fa.items()} == {k: q for k, (q, _) in fb.items()}:
            continue
        rs = 0.0
        for k in set(fa) | set(fb):
            qa, pa = fa.get(k, (0, None))
            qb, pb = fb.get(k, (0, None))
            if qa != qb:
                rs += abs(qa - qb) * (pa if pa is not None else pb)
        out.append((d, rs))
    return out


def cadence_gap(rebal):
    """Port vs vectorised final equity at a non-default cadence. Reported, not gated.

    Both sides are v2 at `rebal`: the port run here, the vectorised reference from
    that cadence's daily_summary, named by the writer's own rule. The reference
    must already exist -- run `run.py --universe <u> --arm v2 --rebal <n>` first.
    """
    import cadence as _cd
    sys.path.insert(0, str(ROOT / "results"))
    import audit_step
    from arms.registry import ARMS
    from universes.registry import REGISTRY
    _cd.set_selection(rebal)
    ref_f = M / f"daily_summary_{audit_step.artefact_tag(REGISTRY[UNIVERSE], ARMS['v2'])}.csv"
    if not ref_f.exists():
        print(f"  no vectorised reference at {ref_f.name}; run "
              f"./venv/bin/python run.py --universe {UNIVERSE} --arm v2 --rebal {rebal}")
        return 1
    with contextlib.redirect_stdout(io.StringIO()):
        strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"], quiet=True,
                           universe=UNIVERSE, rebal=rebal)
    port = pd.DataFrame(strat.daily_equity).set_index("date")["equity"]
    ref = read_table(ref_f, parse_dates=["date"]).set_index("date")["total"]
    p_fin, r_fin = float(port.iloc[-1]), float(ref.iloc[-1])
    print(f"  cadence {rebal}  {UNIVERSE} v2")
    print(f"    Nautilus final equity   Rs {p_fin:,.2f}   ({strat.rebalances} rebalances, "
          f"{strat.orders_submitted} orders)")
    print(f"    vectorised final equity Rs {r_fin:,.2f}   ({ref_f.name})")
    print(f"    gap                     Rs {p_fin - r_fin:+,.2f}  "
          f"({(p_fin / r_fin - 1) * 100:+.3f}%)   REPORTED, NOT GATED")
    return 0


def main():
    import cadence as _cd
    if REBAL is not None and REBAL != _cd.DEFAULT:
        return cadence_gap(REBAL)
    strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"], universe=UNIVERSE,
                       **_ARM_KW)
    TAG = _ref_tag()

    eq = pd.DataFrame(strat.daily_equity)
    eq["date"] = pd.to_datetime(eq["date"])
    eq = eq.set_index("date")["equity"]
    ref_eq = read_table(M / f"daily_summary_{TAG}.csv", parse_dates=["date"]) \
               .set_index("date")["total"]

    # THE INTERSECTION USED TO HIDE A MISSING DAY, AND DID.
    #     `common` silently discards any date one side lacks, so when the port's
    #     series held 1,841 rows against the reference's 1,842 the comparison simply
    #     moved to the last date they shared and reported it as "final equity". The
    #     missing 2026-06-08 carried ten fills on a retired universe and twelve on
    #     midcap150. Nothing in the output said so: the numbers looked like a clean
    #     0.03% agreement.
    #
    #     A date index that does not match is a defect to report, not a set to
    #     narrow. The comparison below still runs -- it is diagnostic and refusing to
    #     print it would be less useful -- but the mismatch is stated first and the
    #     equity line is labelled with the date it actually describes.
    idx_ok = (len(eq.index) == len(ref_eq.index)
              and eq.index[0] == ref_eq.index[0]
              and eq.index[-1] == ref_eq.index[-1])
    common = eq.index.intersection(ref_eq.index)

    dates, port = port_holdings(strat)

    hr = read_table(M / f"daily_holdings_{TAG}.csv", parse_dates=["date"])
    ref = {d: {} for d in dates}
    for _, r in hr[hr["date"].isin(dates)].iterrows():
        ref[r["date"]][r["symbol"]] = int(r["qty"])

    panel = nt_attribution.load_panel(U["cache"])
    # THE REFERENCE COPY: the engine's loop re-implemented in nt_attribution and run
    # on the port's panel and scores, with the same fill price rule. The port is
    # gated against it. Its own holdings must keep the engine's selection
    # (daily_holdings_{TAG}.csv), which is checked below rather than assumed: it is
    # what licenses the copy as the baseline.
    _r_hold, r_fills, r_ev = {}, [], []
    nt_attribution.run(*panel, holdings_out=_r_hold, fills_out=r_fills,
                       stop_events_out=r_ev, **_ARM_KW)
    arm_r = {d: _r_hold.get(d, {}) for d in dates}

    ref_stats = compare(port, ref, dates)
    r_stats = compare(port, arm_r, dates)
    a_check = compare(arm_r, ref, dates)
    o_diff = compare_fills(fills_by_period(strat.fills, dates), fills_by_period(r_fills, dates))
    h_diff = [d for d in dates if port.get(d, {}) != arm_r.get(d, {})]
    unexplained = sorted(set(h_diff) | {d for d, _ in o_diff})

    fp = pd.DataFrame(strat.fills)
    fr = read_table(M / f"daily_trades_{TAG}.csv", parse_dates=["date"])

    n = len(dates)
    print("\n" + "=" * 72)
    print(f" NAUTILUS PORT -- VERIFICATION AGAINST THE REFERENCE ENGINE  [{UNIVERSE} universe, arm {ARM.name}]")
    print("=" * 72)
    print(f"  buy rule: {RULE} -- fills to the paisa on both sides; holdings and "
          f"orders identical on every rebalance")
    if not idx_ok:
        print("\n  *** DATE INDEX MISMATCH -- the two series do not cover the same days ***")
        print(f"      port      {len(eq.index):>5} rows   "
              f"{eq.index[0].date()} -> {eq.index[-1].date()}")
        print(f"      reference {len(ref_eq.index):>5} rows   "
              f"{ref_eq.index[0].date()} -> {ref_eq.index[-1].date()}")
        only_ref = ref_eq.index.difference(eq.index)
        only_prt = eq.index.difference(ref_eq.index)
        if len(only_ref):
            print(f"      missing from the PORT      ({len(only_ref)}): "
                  f"{', '.join(str(d.date()) for d in only_ref[:8])}"
                  f"{' ...' if len(only_ref) > 8 else ''}")
        if len(only_prt):
            print(f"      missing from the REFERENCE ({len(only_prt)}): "
                  f"{', '.join(str(d.date()) for d in only_prt[:8])}"
                  f"{' ...' if len(only_prt) > 8 else ''}")
        print("      Every figure below is computed on the shared dates only, so it")
        print("      does NOT describe the full window. Fix the mismatch first.")

    # Labelled with the date it actually describes. This used to say "final equity"
    # while reporting the last SHARED day, which on a mismatched index is not the
    # final day of either series.
    _d = common[-1]
    _lab = "final equity" if idx_ok else "equity on last shared day"
    print(f"\n  {_lab}  ({_d.date()})")
    print(f"                 reference Rs {ref_eq.loc[_d]:>12,.0f}")
    print(f"                 port      Rs {eq.loc[_d]:>12,.0f}"
          f"   ({(eq.loc[_d] / ref_eq.loc[_d] - 1) * 100:+.2f}%)")
    # daily_holdings_{TAG}.csv has a row per day, not per rebalance, so count the
    # rebalance dates from the decisions file instead.
    n_ref = len(read_table(M / f"daily_decisions_{TAG}.csv"))
    print(f"\n  rebalances     reference {n_ref:>4}   port {n:>4}")
    # INFORMATIONAL ONLY -- the verdict below does not read these numbers.
    print(f"  fills [FYI]    reference {len(fr):>4}   port {len(fp):>4}"
          f"   (not a pass/fail gate)")

    report("vs REFERENCE (the engine's own audit trail, not gated)", ref_stats, n)
    report("vs the reference copy (gated)", r_stats, n)
    # THE CONTROL GATES SELECTION AND MEASURES SIZING. nt_attribution.run and
    # test_exposure.backtest_exposure are two of this repository's backtest
    # reimplementations. Selection is gated; their integer sizing is reported only.
    # See KNOWN_ISSUES.md, "There are FIVE reimplementations of the backtest".
    _a_mism, _a_sym, _a_qty, _a_worst = a_check
    print(f"\n  control: the reference copy vs the reference's own holdings")
    print(f"           SELECTION (gated)  -- {n - _a_sym} of {n} rebalances hold "
          f"the same symbol set")
    print(f"           SIZING (not gated) -- {_a_qty} of {n} differ in quantity "
          f"only" + (f", worst {max(_a_worst):.2f}% on a single position"
                     if _a_worst else ""))

    print(f"\n  port vs the reference copy, to the paisa")
    print(f"    holdings at each rebalance (name, quantity) -- "
          f"{n - len(h_diff)} of {n} identical")
    print(f"    orders filled per rebalance period (name, side, quantity) -- "
          f"{n - len(o_diff)} of {n} identical")
    for d, rs in o_diff[:20]:
        print(f"      differs: {d.date()}  Rs {rs:,.2f} of differing shares  UNEXPLAINED")
    if len(o_diff) > 20:
        print(f"      ... {len(o_diff) - 20} more")
    for d in [d for d in h_diff if d not in {x for x, _ in o_diff}][:20]:
        print(f"      holdings differ: {d.date()}  UNEXPLAINED")

    # THE EXIT STATUS. ONLY "VERIFIED" IS A PASS. INCONCLUSIVE is not a pass: it
    # says the reference copy is not a trustworthy baseline, so the run
    # established nothing and must not be read as agreement.
    rc = 1
    print("\n" + "=" * 72)
    if not idx_ok:
        print("  NOT VERIFIED. The port and the reference do not cover the same set of")
        print("  trading days, so no figure above describes the same window on both")
        print("  sides. This is reported rather than intersected away because a silent")
        print("  intersection is what let a missing final day -- carrying ten fills on")
        print("  a retired universe -- go unnoticed while the output read as a clean")
        print("  agreement.")
    elif a_check[1] != 0:
        print("  INCONCLUSIVE. The reference copy does not reproduce the reference")
        print("  engine's own SELECTION -- the two engines hold different symbols, so")
        print("  the copy is not a trustworthy baseline for the port. Fix that first.")
    elif unexplained:
        print(f"  NOT VERIFIED. {len(unexplained)} rebalance(s) differ between the port")
        print("  and the reference copy in holdings or in the orders filled. Both price")
        print("  every fill to the paisa with one function, so nothing explains a")
        print("  difference. Do not trade this.")
    else:
        print("  VERIFIED. The port and the reference copy hold the same names and")
        print("  quantities at every rebalance and fill the same orders in every")
        print("  rebalance period, with every fill priced to the paisa on both sides.")
        rc = 0
    # THE STOP ARM'S EXITS AND RE-ENTRIES, port against the engine's own record.
    if ARM.stop is not None:
        _sf = M / f"daily_stop_events_{TAG}.csv"
        eng_ev = (read_table(_sf, parse_dates=["date"]).to_dict("records")
                  if _sf.exists() else [])
        p_set, e_set = stop_dates(strat.stop_events), stop_dates(eng_ev)
        a_set = stop_dates(r_ev)
        _common = eq.index.intersection(ref_eq.index)
        _gap = float(((eq.loc[_common] / ref_eq.loc[_common]) - 1).abs().max() * 100)
        print(f"\n  DRAWDOWN STOP -- {len(e_set)} key events in {_sf.name}")
        print(f"    port vs engine        : {len(p_set & e_set)} shared, "
              f"{len(p_set - e_set)} port only, {len(e_set - p_set)} engine only")
        print(f"    copy vs engine        : {len(a_set & e_set)} shared, "
              f"{len(a_set - e_set)} copy only, {len(e_set - a_set)} engine only")
        for d, e in sorted(p_set ^ e_set)[:20]:
            print(f"      differs: {d.date()} {e}  ({'port' if (d, e) in p_set else 'engine'} only)")
        print(f"    daily equity, port vs engine: largest gap {_gap:.4f}% over "
              f"{len(_common)} days (reported, not gated, as for every arm)")
        print(f"    exits {sum(1 for _, e in e_set if e == 'trigger')}, re-entries "
              f"{sum(1 for _, e in e_set if e == 're-entry filled')}")
        if not e_set or p_set != e_set:
            print("  NOT VERIFIED. The port's exit and re-entry dates are not the engine's.")
            rc = 1
    print(f"\n  RESULT: {'PASS' if rc == 0 else 'FAIL'} -- universe {UNIVERSE}, arm {ARM.name}, "
          f"buy rule {RULE}, holdings {n - len(h_diff)} of {n} identical, "
          f"orders {n - len(o_diff)} of {n} identical, "
          f"{len(unexplained)} unexplained.")
    print("=" * 72)
    return rc


if __name__ == "__main__":
    sys.exit(main())
