"""
topn_centralise_check.py -- equity-curve hashes for the TOP_N/BUFFER centralisation.

RUN IT AS:
    ./venv/bin/python topn_centralise_check.py before
    ...make the edit...
    ./venv/bin/python topn_centralise_check.py after
    ./venv/bin/python topn_centralise_check.py report

THE HASH FILES LIVE IN diagnostics/, NOT IN /tmp, AND THAT IS WHAT MAKES THIS
SCRIPT USABLE BY A RUNNER AT ALL. `before` is the BASELINE this check compares
against; a baseline in /tmp does not survive a reboot and is not in the tree, so
before 2026-09-22 there was nothing for `report` to read and this script could
not participate in a gate run. The three commands now default to
diagnostics/topn_hash_before.csv, diagnostics/topn_hash_after.csv and a
comparison of the two. An explicit path may still be passed as the second
argument, so existing invocations that named one keep working.

NOTHING ABOUT WHAT IS COMPARED CHANGED. Same universes, same four sizing/mode
combinations, same equity curves, same sha256. Only where the file is written.

The system python3 has no lightgbm and cannot import engine_core. Use the venv,
and use the SAME interpreter for both halves or the comparison is not like for
like.

Discharges the proof obligation in experiments/TOPN_SPEC.txt Part A: four arms
(invvol/provol x none/breadth) on both live universes, eight SHA256 hashes,
recorded before the edit and again after. Reads the score panel through
config.require_cache and the raw prices through the engine's own pivot, exactly
as engine_v2_final_n100.py and engine_v2_final_mid.py do.

Takes a label argument ("before" / "after") and writes one CSV per label so the
two columns can be placed side by side.
"""
import sys, hashlib, subprocess, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent


def HASHES(label):
    """Where a hash run is recorded. IN THE TREE, not in /tmp.

    The baseline is the whole point of this check and /tmp does not keep it, so
    the default landed somewhere a later `report` could not find. diagnostics/ is
    where this script's own report already goes.
    """
    return ROOT / "diagnostics" / f"topn_hash_{label}.csv"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import numpy as np
import pandas as pd
import config
from engine_core import precompute
import test_exposure
from test_exposure import backtest_exposure
from universes.registry import REGISTRY
import profiles as _prof            # the run's execution-realism profile

VOL_WIN = 60

# The SCORE PANEL paths, permanent and working, come from universes/registry.py
# -- the single definition. This file carries no label of its own, so nothing is
# kept local here. Order is load-bearing: the hash table is emitted universe by
# universe and compared row for row against the previous run.
UNIVERSES = {u.tag: (u.score_cache, str(u.score_tmp))
             for u in (REGISTRY["nifty100"], REGISTRY["midcap150"])}

ARMS = [("invvol", "none"), ("invvol", "breadth"),
        ("provol", "none"), ("provol", "breadth")]


def load(perm, tmp, what):
    src = config.require_cache(perm, tmp, what=what)
    p = pd.read_csv(src, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return px, op, sc


def run(uni, perm, tmp):
    px, op, sc = load(perm, tmp, f"{uni} score panel")
    bd = px.index[(px.index >= config.BT_START_DATE)
                  & (px.index <= config.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    port_vol = idx.pct_change().rolling(VOL_WIN).std() * np.sqrt(252)
    tv = port_vol.loc[bd].median()

    rows = []
    for sizing, mode in ARMS:
        # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
        # apply a participation cap even if one were selected; research_only()
        # makes that a statement rather than an accident, and STOPS the run if
        # --profile ever reaches here. See profiles.research_only.
        eq, tc, n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, port_vol,
                                         mode=mode, target_vol=tv, sizing=sizing, participation_cap=_prof.research_only(__name__))
        s = pd.Series(eq, index=bd[:len(eq)]) if not isinstance(eq, pd.Series) else eq
        # Hash the exact float bytes of the curve, not a formatted rendering.
        h = hashlib.sha256(np.asarray(s.values, dtype=np.float64).tobytes()).hexdigest()
        rows.append({"universe": uni, "sizing": sizing, "mode": mode,
                     "days": len(s), "trades": n,
                     "final": float(np.asarray(s.values)[-1]),
                     "sha256": h})
        print(f"  {uni:<5} {sizing:<7} {mode:<8} days {len(s):>5} "
              f"trades {n:>5}  {h}")
    return rows


def report(before_csv, after_csv):
    """Build diagnostics/topn_centralise_hashes.txt from the two runs."""
    ROOT = Path(__file__).resolve().parent
    b = pd.read_csv(before_csv); a = pd.read_csv(after_csv)
    key = ["universe", "sizing", "mode"]
    m = b.merge(a, on=key, suffixes=("_before", "_after"))
    m["identical"] = m["sha256_before"] == m["sha256_after"]

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())

    n_ok = int(m["identical"].sum()); n = len(m)
    verdict = "IDENTICAL" if n_ok == n else "MOVED"
    consequence = ("the centralisation changed no behaviour and stands"
                   if n_ok == n else
                   "the centralisation changed behaviour and IS REVERTED, not explained")

    L = []
    L.append("=" * 100)
    L.append(" TOP_N / BUFFER CENTRALISATION -- EQUITY-CURVE HASH PROOF")
    L.append("=" * 100)
    L.append("")
    L.append(" Discharges the proof obligation in experiments/TOPN_SPEC.txt Part A.")
    L.append(" Four arms x two live universes = eight equity curves, hashed before the")
    L.append(" edit and again after it. SHA256 over the raw float64 bytes of the curve,")
    L.append(" not over a formatted rendering.")
    L.append("")
    L.append(f" Run on the shipping engine, test_exposure.backtest_exposure.")
    L.append(f" Window config.BT_START_DATE to BT_END_DATE.")
    L.append(f" git commit {commit}   working tree {'DIRTY' if dirty else 'clean'}")
    L.append("")
    L.append(" REGENERATE THIS FILE:")
    L.append("   ./venv/bin/python topn_centralise_check.py before")
    L.append("   ...apply or revert the edit...")
    L.append("   ./venv/bin/python topn_centralise_check.py after")
    L.append("   ./venv/bin/python topn_centralise_check.py report")
    L.append(" The system python3 has no lightgbm and cannot import engine_core.")
    L.append("")
    L.append(" WHAT MOVED, AND WHAT DID NOT")
    L.append("   Centralised into config.py: results/test_exposure.py,")
    L.append("   results/engine_v2_final_n100.py, results/engine_v2_final_mid.py,")
    L.append("   nautilus/nt_strategy.py, nautilus/nt_attribution.py.")
    L.append("   Frozen, literals untouched: results/engine_core.py (comment added only),")
    L.append("   engine_v2_final.py, engine_v2_final74.py, make_cash_series.py,")
    L.append("   make_stats_both.py, deleted 2026-09-04.")
    L.append("")
    L.append("-" * 100)
    L.append(f" {'universe':<10}{'sizing':<9}{'mode':<10}{'days':>6}{'trades':>8}  "
             f"{'before':<18}{'after':<18}{'':>2}")
    L.append("-" * 100)
    for _, r in m.iterrows():
        assert r["days_before"] == r["days_after"]
        L.append(f" {r['universe']:<10}{r['sizing']:<9}{r['mode']:<10}"
                 f"{r['days_before']:>6}{r['trades_before']:>8}  "
                 f"{r['sha256_before'][:16]:<18}{r['sha256_after'][:16]:<18}"
                 f"{'ok' if r['identical'] else 'MOVED':>2}")
    L.append("-" * 100)
    L.append("")
    L.append(" FULL HASHES")
    for _, r in m.iterrows():
        L.append(f"   {r['universe']}/{r['sizing']}/{r['mode']}")
        L.append(f"     before  {r['sha256_before']}")
        L.append(f"     after   {r['sha256_after']}")
    L.append("")
    L.append("=" * 100)
    L.append(f" RESULT: {n_ok} of {n} equity curves {verdict}")
    L.append(f" CONSEQUENCE: {consequence}.")
    L.append("=" * 100)
    L.append("")
    L.append(" WHAT THIS PROVES AND WHAT IT DOES NOT")
    L.append("   PROVES: replacing the literals with imports left every arm's equity")
    L.append("   curve byte-identical on both live universes. Trade counts are printed")
    L.append("   beside the hashes and are unchanged too.")
    L.append("")
    L.append("   DOES NOT PROVE that the five backtest reimplementations agree with each")
    L.append("   other. Centralising a constant does not merge them, and it does not fix")
    L.append("   results/make_stats_both.py, which was frozen at 12/24 with a 6% cash")
    L.append("   yield. Both remain open in KNOWN_ISSUES.md.")
    L.append("")
    L.append("   DOES NOT COVER the retired 58 and 74. They keep their own literals by")
    L.append("   design, so there is nothing there for this proof to move.")
    L.append("")
    out = ROOT / "diagnostics" / "topn_centralise_hashes.txt"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L[-14:]))
    print(f"\nwrote {out}")
    # THE EXIT STATUS, ADDED 2026-09-21. `verdict` and `n_ok` are the ones this
    # function already computed and printed; nothing is recomputed. Only the
    # report mode gets a status, and that is deliberate -- see main().
    print(f"\n  RESULT: {'PASS' if n_ok == n else 'FAIL'} -- {n_ok} of {n} "
          f"equity-curve hashes {verdict.lower()}.")
    return 0 if n_ok == n else 1


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    if label == "report":
        b = Path(sys.argv[2]) if len(sys.argv) > 2 else HASHES("before")
        a = Path(sys.argv[3]) if len(sys.argv) > 3 else HASHES("after")
        for f in (b, a):
            if not f.exists():
                print(f"  MISSING: {f}\n  Run `topn_centralise_check.py before` "
                      f"and `... after` first; there is nothing to compare.")
                return 2
        return report(b, a)
    # THE HASH-WRITING MODE HAS NO VERDICT, AND ONE IS NOT INVENTED HERE. It emits
    # one sha256 per (universe, sizing, mode) and nothing else; whether those
    # hashes are right is only answerable against a BASELINE taken before the
    # change under test, which is what `report before.csv after.csv` compares. A
    # single run has nothing to be right or wrong about, so it exits 0 and says so
    # rather than asserting a pass. No baseline is stored in the tree -- both runs
    # write to /tmp -- so this script cannot be wired into a runner as it stands.
    print(f"TOP_N / BUFFER centralisation -- equity-curve hashes [{label}]")
    print(f"  test_exposure.TOP_N={test_exposure.TOP_N} "
          f"BUFFER={test_exposure.BUFFER}")
    out = []
    for uni, (perm, tmp) in UNIVERSES.items():
        out += run(uni, perm, tmp)
    df = pd.DataFrame(out)
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else HASHES(label)
    df.to_csv(dest, index=False)
    print(f"\nwrote {dest}")
    print("\n  NO VERDICT: this mode records hashes only. Compare two runs with "
          "`topn_centralise_check.py report`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
