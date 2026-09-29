"""cost_reconcile_check.py -- the cost reconciliation on every cell, profile and tax setting.

    ./venv/bin/python cost_reconcile_check.py [--universe=<tag>[,<tag>...]]

A check_all delegate. For each registered universe, each arm, the research and
tradeable profiles, and tax off and on, at the default cadence: run the backtest
with the cost trail and apply results/cost_report.reconcile -- cash every day,
slippage and charges every fill, tax every financial year, and the totals. Writes
nothing. Exits 1 at the end if any combination failed, naming each with the check,
the first day and the gap; 0 if all reconcile.
"""
import os
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[_v] = "1"
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import config                                                    # noqa: E402
import cost_report                                               # noqa: E402
import engine_core                                               # noqa: E402
import profiles                                                  # noqa: E402
import arms.registry as arm_reg                                  # noqa: E402
from config import read_table                                    # noqa: E402
from engine_core import precompute                               # noqa: E402
from test_exposure import backtest_exposure, START_CAPITAL       # noqa: E402
from universes.registry import REGISTRY, argv_universes, check_tags  # noqa: E402

KEYS = ("holdings", "summary", "trades", "ranking", "decisions", "skipped")


def cell(u, arm, panel, profile, tax_on):
    px, op, sc, bd, pc, mom20 = panel
    profiles.set_selection(profile)
    try:
        audit = {k: [] for k in KEYS}
        audit["costs"] = {"fills": [], "days": []}
        _eq, tc, _n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, mode=arm.mode,
                                           sizing=arm.sizing, audit=audit, value_at_open=True,
                                           tax_enabled=tax_on, **profiles.cap_kwargs(u))
    finally:
        profiles.set_selection(None)
    tx = audit.get("tax")
    cost_report.reconcile(audit["costs"], audit["trades"], list(bd), float(START_CAPITAL), tc,
                          float(tx["cum_tax"]) if tx else 0.0, tax_on,
                          tx["lots"] if tx else None)
    return len(audit["trades"])


def main(argv):
    picked = check_tags(argv_universes(argv), REGISTRY) or list(REGISTRY)
    failed, n, t0 = [], 0, time.time()
    for tag in picked:
        u = REGISTRY[tag]
        engine_core.set_tradeability(u)
        p = read_table(config.require_cache(u.score_cache, what=tag), parse_dates=["date"])
        px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
        op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
        sc = p.pivot_table(index="date", columns="symbol", values="score")
        panel = (px, op, sc, u.trading_days(px.index), precompute(px), px / px.shift(20) - 1)
        for arm in arm_reg.ARMS.values():
            for profile in profiles.PROFILES:
                for tax_on in (False, True):
                    what = f"{tag} {arm.name} {profile} tax {'on' if tax_on else 'off'}"
                    try:
                        fills = cell(u, arm, panel, profile, tax_on)
                        print(f"  PASS  {what:<36} {fills:>5} fills", flush=True)
                    except cost_report.CostReconciliationError as e:
                        failed.append(f"{what}: {e}")
                        print(f"  FAIL  {what:<36} {e}", flush=True)
                    n += 1
    print(f"\n{n - len(failed)} of {n} combinations reconcile "
          f"({(time.time() - t0) / 60:.1f} min)")
    for f in failed:
        print(f"  FAILED {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
