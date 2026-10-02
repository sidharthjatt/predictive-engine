"""
nt_mid_trace.py -- why an nt_verify cell fails: selection flip or valuation rounding.

    ./venv/bin/python nautilus/nt_mid_trace.py <universe>:<arm> [<universe>:<arm> ...]

The 2026-09-27 record traced the four cells that left the nt_verify gate that day;
the command that produced it is in diagnostics/nt_mid_trace.txt's first line.

Read-only. Writes diagnostics/nt_mid_trace.txt. For each cell:

  0.01 GRID, the grid nt_verify's reconciliation uses
    P   the port (nt_run), holdings at each rebalance
    D   the reference, open-valued, tick_round=True (what nt_verify compares P to)
    M   the reference with one change: the book valued at the port's quote mid,
        0.5 * (tick(open*(1+slippage)) + tick(open*(1-slippage))), instead of the
        open. nt_gate_diagnose.py documents that the port values its book this way.
    A failing rebalance is one where P != D other than nt_verify's one-share
    signature. For each: does the set of names differ, and does M equal P?

  0.05 GRID, the production grid (the Pass E trace, 2026-09-26)
    the port against the engine (tick_round=False), and whether the reference
    with tick_round=True reproduces the port's names wherever the two differ.
"""

import contextlib, io, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "results", ROOT / "nautilus"):
    sys.path.insert(0, str(p))
import numpy as np
import config, nt_data, nt_run, nt_attribution, nt_verify
from arms.registry import ARMS

S = nt_attribution.SLIPPAGE


def tick01(x):
    return np.round(np.round(x / 0.01) * 0.01, 4)


def trace(u, a):
    arm = ARMS[a]
    kw = arm.kwargs
    U = nt_run.UNIVERSES[u]
    nt_data.set_tick_size("0.01"); nt_data.set_tick_mode("fixed")
    nt_attribution.set_tick("0.01"); nt_attribution.set_tick_mode("fixed")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"], quiet=True,
                               universe=u, **kw)
        dates, P = nt_verify.port_holdings(strat)
        px, op, sc, bd, pc, mom20 = nt_attribution.load_panel(U["cache"])
        D = nt_verify.arm((px, op, sc, bd, pc, mom20), dates, size_at_close=False,
                          value_at_open=True, tick_round=True, **kw)
        mid = 0.5 * (tick01(op * (1 + S)) + tick01(op * (1 - S)))
        mid = mid.where(mid.notna(), px)
        outm = {}
        nt_attribution.run(mid, op, sc, bd, pc, mom20, size_at_close=False,
                           tick_round=True, value_at_open=False, holdings_out=outm, **kw)
        M = {d: outm.get(d, {}) for d in dates}
    finally:
        nt_data.set_tick_size("0.05"); nt_data.set_tick_mode("nse")
        nt_attribution.set_tick("0.05"); nt_attribution.set_tick_mode("nse")
    decisions = {str(d["decided_on"])[:10]: d for d in strat.decisions}
    rows, first_flip = [], None
    for d in dates:
        p, r = P.get(d, {}), D.get(d, {})
        if p == r:
            continue
        diffs = {s: p.get(s, 0) - r.get(s, 0) for s in set(p) | set(r) if p.get(s, 0) != r.get(s, 0)}
        quant = set(p) == set(r) and len(diffs) == 1 and list(diffs.values())[0] == -1
        flip = set(p) != set(r)
        if flip and first_flip is None:
            first_flip = d
        rows.append({
            "date": str(d.date()), "quantization": quant, "symbol_set_differs": flip,
            "port_only": sorted(set(p) - set(r)), "ref_only": sorted(set(r) - set(p)),
            "share_diffs": {s: int(v) for s, v in diffs.items() if s in p and s in r},
            "mid_valued_ref_equals_port": M.get(d, {}) == p,
            "mid_valued_ref_equals_ref": M.get(d, {}) == r,
            "after_first_flip": first_flip is not None and d > first_flip,
        })
    same_all = sum(M[d] == P[d] for d in dates)
    return {"cell": f"{u} {a}", "rebalances": len(dates), "rows": rows,
            "mid_valued_ref_equals_port_on": same_all}




def grid05(u, a):
    kw = ARMS[a].kwargs
    U = nt_run.UNIVERSES[u]
    with contextlib.redirect_stdout(io.StringIO()):
        strat = nt_run.run(str(config.BT_START_DATE.date()), U["end"], quiet=True, universe=u, **kw)
    dates, P = nt_verify.port_holdings(strat)
    panel = nt_attribution.load_panel(U["cache"])
    A = nt_verify.arm(panel, dates, size_at_close=False, value_at_open=True, tick_round=False, **kw)
    D = nt_verify.arm(panel, dates, size_at_close=False, value_at_open=True, tick_round=True, **kw)
    flips = [d for d in dates if set(P[d]) != set(A[d])]
    return [(str(d.date()), sorted(set(P[d]) - set(A[d])), sorted(set(A[d]) - set(P[d])),
             set(D[d]) == set(P[d])) for d in flips]


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    from universes.registry import check_tags
    cells = [tuple(x.split(":")) for x in argv]
    check_tags([u for u, _ in cells])
    for _u, a in cells:
        if a not in ARMS:
            raise SystemExit(f"unknown arm {a!r}; known: {', '.join(ARMS)}")
    L = ["nt_mid_trace -- ./venv/bin/python nautilus/nt_mid_trace.py " + " ".join(argv), ""]
    for u, a in cells:
        c = trace(u, a)
        bad = [r for r in c["rows"] if not r["quantization"]]
        diffs = [v for r in bad for v in r["share_diffs"].values()]
        L.append(f"{c['cell']}")
        L.append(f"  0.01 grid: {len(bad)} failing rebalance(s) of {c['rebalances']}; "
                 f"{sum(r['symbol_set_differs'] for r in bad)} with a different set of names; "
                 f"{len(diffs)} differing position(s), largest {max((abs(v) for v in diffs), default=0)} share(s), "
                 f"port higher on {sum(v > 0 for v in diffs)}, lower on {sum(v < 0 for v in diffs)}")
        L.append(f"  mid-valued reference equals the port on {sum(r['mid_valued_ref_equals_port'] for r in bad)} "
                 f"of {len(bad)} failing rebalance(s), {c['mid_valued_ref_equals_port_on']} of {c['rebalances']} overall")
        for r in bad:
            what = (f"names differ: port {r['port_only']} reference {r['ref_only']}" if r["symbol_set_differs"]
                    else "shares " + ", ".join(f"{s} {v:+d}" for s, v in sorted(r["share_diffs"].items())))
            L.append(f"    {r['date']}  {what}  mid-valued reference = port: {r['mid_valued_ref_equals_port']}")
        fl = grid05(u, a)
        L.append(f"  0.05 grid: {len(fl)} rebalance(s) where the port holds other names than the engine")
        for d, po, eo, rep in fl:
            L.append(f"    {d}  port {po} engine {eo}  reproduced by tick_round=True: {rep}")
        L.append("")
    out = ROOT / "diagnostics" / "nt_mid_trace.txt"
    # naming: axis-free -- a diagnosis of named (universe, arm) cells, each named inside.
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
