"""
impact_pcap_axis_test.py -- the market-impact and participation-cap axes on a
synthetic panel.

    ./venv/bin/python impact_pcap_axis_test.py          # every case, with its figures
    ./venv/bin/python impact_pcap_axis_test.py --quiet  # PASS/FAIL lines only

    1. validation: k below 0 and a cap at or below 0 are refused; k 0 is the default
    2. names: "" at the defaults, "_impact0p003" / "@impact0p003" and
       "_pcap0p1" / "@pcap0p1" otherwise; --cap at the profile's own value is ""
    3. the research profile refuses a non-zero k and any cap, in check_profile and
       in profiles.cap_kwargs
    4. profiles.participation_cap: the profile's value, or --cap's under tradeable
    5. the default path: impact_k unset and impact_k=None give the same curve, and
       the cost trail carries no impact keys
    6. with impact on, every fill is slippage.impact on top of the flat rate, the
       run reconciles to the paisa, and impact is reported apart from slippage:
       flat slippage is exactly reference x SLIPPAGE x qty, and gross profit
       includes impact
    7. the summary block prints an impact row and summary_figures reads it back

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results"):
    sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd

import cost_report
import impact_axis
import pcap_axis
import profiles
import slippage
from engine_core import precompute
from test_exposure import backtest_exposure

QUIET = "--quiet" in sys.argv
RESULTS = []
SYMS = [f"S{k:02d}" for k in range(12)]
WARM = pd.bdate_range("2020-08-03", "2020-12-31")
DATES = pd.bdate_range("2021-01-01", "2021-12-31")
K = 0.003


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


def panel():
    idx = WARM.append(DATES)
    f = np.cumprod(np.r_[1.0, np.full(len(idx) - 1, 1.0007)])
    px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) * (1 + 0.002 * np.sin(np.arange(len(idx)) / (k + 3)))
                       for k, s in enumerate(SYMS)}, index=idx)
    sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
    # a median volume on every date of the window, different per symbol
    vol20 = {s: {d: 20_000.0 + 1_000.0 * k for d in DATES} for k, s in enumerate(SYMS)}
    return px, px.copy(), sc, vol20


def run(px, op, sc, **kw):
    audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    audit["costs"] = {"fills": [], "days": []}
    eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                     mode="none", sizing="invvol", audit=audit, rebal=20,
                                     drawdown_stop=None, **kw)
    return eq, tc, audit


def reset():
    impact_axis.set_selection(None)
    pcap_axis.set_selection(None)
    profiles.set_selection(None)


def main():
    # 1 ----------------------------------------------------------------------
    bad = []
    for v in (-0.001, float("nan")):
        try:
            impact_axis.set_selection(v)
            bad.append(("impact", v))
        except ValueError:
            pass
    for v in (0, -0.5):
        try:
            pcap_axis.set_selection(v)
            bad.append(("cap", v))
        except ValueError:
            pass
    impact_axis.set_selection(0)
    zero_is_default = impact_axis.is_default() and impact_axis.impact_k() is None
    reset()
    case("1 validation: k < 0 and cap <= 0 refused; k 0 is the default",
         not bad and zero_is_default, f"accepted wrongly: {bad}")

    # 2 ----------------------------------------------------------------------
    profiles.set_selection("tradeable")
    names_default = (impact_axis.suffix(), impact_axis.segment(), pcap_axis.suffix(),
                     pcap_axis.segment())
    impact_axis.set_selection(K)
    pcap_axis.set_selection(0.1)
    names_on = (impact_axis.suffix(), impact_axis.segment(), pcap_axis.suffix(),
                pcap_axis.segment())
    pcap_axis.set_selection(1.0)
    own_cap = pcap_axis.suffix()
    reset()
    case("2 names", names_default == ("", "", "", "")
         and names_on == ("_impact0p003", "@impact0p003", "_pcap0p1", "@pcap0p1") and own_cap == "",
         f"default {names_default}, on {names_on}, --cap 1.0 under tradeable {own_cap!r}")

    # 3 ----------------------------------------------------------------------
    refused = []
    impact_axis.set_selection(K)
    for what, fn in (("impact check_profile", impact_axis.check_profile),
                     ("cap_kwargs", lambda: profiles.cap_kwargs(None))):
        try:
            fn()
        except ValueError:
            refused.append(what)
    reset()
    pcap_axis.set_selection(0.1)
    try:
        pcap_axis.check_profile()
    except ValueError:
        refused.append("cap check_profile")
    reset()
    case("3 research refuses --impact and --cap", len(refused) == 3, f"refused: {refused}")

    # 4 ----------------------------------------------------------------------
    profiles.set_selection("tradeable")
    own = profiles.participation_cap()
    pcap_axis.set_selection(0.1)
    over = profiles.participation_cap()
    reset()
    case("4 participation_cap: profile's 1.0, --cap's 0.1", own == 1.0 and over == 0.1,
         f"own {own}, with --cap 0.1 {over}")

    # 5 ----------------------------------------------------------------------
    px, op, sc, vol20 = panel()
    e0, _, a0 = run(px, op, sc, participation_cap=1.0, vol20=vol20)
    e1, _, _ = run(px, op, sc, participation_cap=1.0, vol20=vol20, impact_k=None)
    keys = set().union(*(r.keys() for r in a0["costs"]["fills"]))
    case("5 default path unchanged, no impact keys in the cost trail",
         bool((e0 == e1).all()) and "impact_median" not in keys
         and "impact_rs" not in cost_report.fills_frame(a0["costs"]).columns)

    # 6 ----------------------------------------------------------------------
    eK, tcK, aK = run(px, op, sc, participation_cap=1.0, vol20=vol20, impact_k=K)
    fills, lots, years, days = cost_report.reconcile(aK["costs"], aK["trades"], list(DATES),
                                                     1_000_000.0, tcK, 0.0, False)
    want = [slippage.impact(int(r.qty), vol20[r.symbol][r.date], K) for r in fills.itertuples()]
    rate_ok = np.allclose(fills["impact_rate"], want, rtol=0, atol=1e-15)
    flat = fills["reference_price"] * slippage.SLIPPAGE * fills["qty"]
    flat_ok = bool((np.abs(fills["slippage_rs"] - flat) < 0.005).all())
    S = cost_report.strategy_totals(1_000_000.0, float(eK.iloc[-1]), fills, years)
    gross_ok = abs(S["gross"] - (S["final"] - 1_000_000.0 + S["charges"] + S["slippage"]
                                 + S["impact"] + S["tax"])) < 0.005
    case("6 impact on: fills reconcile, impact split from flat slippage",
         rate_ok and flat_ok and gross_ok and S["impact"] > 0 and eK.iloc[-1] < e0.iloc[-1],
         f"impact Rs {S['impact']:,.2f}, flat slippage Rs {S['slippage']:,.2f}, "
         f"final Rs {eK.iloc[-1]:,.2f} against Rs {e0.iloc[-1]:,.2f} without")

    # 7 ----------------------------------------------------------------------
    lines = cost_report.summary_block("synthetic v1", "tradeable", False, 20, 1_000_000.0, eK,
                                      fills, years, days, None)
    got = cost_report.summary_figures("\n".join(lines))
    case("7 summary prints impact and reads it back",
         got.get("strategy/impact") == f"{S['impact']:,.2f}",
         f"printed {got.get('strategy/impact')}")

    print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
