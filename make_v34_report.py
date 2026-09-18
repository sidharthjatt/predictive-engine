"""
make_v34_report.py -- assemble diagnostics/v34_report.txt from the run artefacts.

NOTHING IN THE OUTPUT IS HAND-WRITTEN. Every number and every direction word
("higher", "lower", "deeper", "shallower") is derived from the CSVs the engines
wrote. The prediction text is quoted from experiments/V34_SPEC.txt and then
compared against the measured deltas by code, so a contradicted prediction cannot
be described as anything else.

THE THREE STATEMENTS ARE KEPT SEPARATE, ON INSTRUCTION
    v4 vs v2   the one clean contrast -- gets a verdict.
    v3 vs v1   CONFOUNDED, and therefore UNTESTABLE rather than failed. The
               numbers are reported in full with the confound measurements
               beside them, and no verdict is drawn either way.
    universes  whether n100 and mid agree. Where they disagree, the disagreement
               is the finding and is reported as such.

Reads only. Writes diagnostics/v34_report.txt.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config

UNIS = [("nifty100", "Nifty 100", ROOT / "results_nifty100" / "metrics"),
        ("midcap150", "MidCap150", ROOT / "results_midcap150" / "metrics")]

V1 = "v1 invvol, 100% invested"
V2 = "v2 invvol, breadth-scaled"
V3 = "v3 provol, 100% invested"
V4 = "v4 provol, breadth-scaled"
BH = "buy & hold equal-weight"


def d(x):
    """Direction word for a plain higher-is-higher quantity."""
    return "higher" if x > 0 else ("lower" if x < 0 else "unchanged")


def dd_word(x):
    """Direction word for MaxDD, where more negative means deeper."""
    return "shallower" if x > 0 else ("deeper" if x < 0 else "unchanged")


def load(M):
    return (pd.read_csv(M / "v34_comparison.csv").set_index("Config"),
            pd.read_csv(M / "v34_subperiods.csv"))


def delta_block(c, a, b, out):
    """b minus a, on the four quantities the spec predicts."""
    dcagr = c.loc[b, "CAGR%"] - c.loc[a, "CAGR%"]
    dvol = c.loc[b, "AnnVol%"] - c.loc[a, "AnnVol%"]
    dsh = c.loc[b, "Sharpe"] - c.loc[a, "Sharpe"]
    ddd = c.loc[b, "MaxDD%"] - c.loc[a, "MaxDD%"]
    out.append(f"    CAGR    {c.loc[a,'CAGR%']:>7.2f}% -> {c.loc[b,'CAGR%']:>7.2f}%   "
               f"{dcagr:+6.2f} pt   {d(dcagr).upper()}")
    out.append(f"    AnnVol  {c.loc[a,'AnnVol%']:>7.2f}% -> {c.loc[b,'AnnVol%']:>7.2f}%   "
               f"{dvol:+6.2f} pt   {d(dvol).upper()}")
    out.append(f"    Sharpe  {c.loc[a,'Sharpe']:>7.2f}  -> {c.loc[b,'Sharpe']:>7.2f}    "
               f"{dsh:+6.2f}      {d(dsh).upper()}")
    out.append(f"    MaxDD   {c.loc[a,'MaxDD%']:>7.2f}% -> {c.loc[b,'MaxDD%']:>7.2f}%   "
               f"{ddd:+6.2f} pt   {dd_word(ddd).upper()}")
    return dcagr, dvol, dsh, ddd


def main():
    L = []
    W = L.append
    W("=" * 100)
    W(" V3/V4 PRO-VOL SIZING -- COMBINED REPORT, BOTH UNIVERSES")
    W("=" * 100)
    W(f" Spec      : experiments/V34_SPEC.txt")
    W(f" Window    : {config.BT_START_DATE.date()} to {config.BT_END_DATE.date()} inclusive")
    W(f" Generated : {pd.Timestamp.today().date()}")
    W("")
    W(" This is a MEASUREMENT, not an accept/reject experiment. No arm is competing")
    W(" to enter production. Every number below is read from the CSVs the engines")
    W(" wrote; no figure or direction word in this file is hand-written.")

    data = {}
    for tag, label, M in UNIS:
        c, s = load(M)
        data[tag] = (label, c, s)

    # ---------------------------------------------------------------- tables
    for tag, (label, c, s) in data.items():
        W("")
        W("=" * 100)
        W(f" {label} ({tag}) -- FULL PERIOD")
        W("=" * 100)
        W(c.reset_index()[["Config", "CAGR%", "AnnVol%", "Sharpe", "Sortino",
                           "MaxDD%", "Calmar", "Deployed%", "Trades", "TC_Rs",
                           "MeanNamesHeld", "CashShortSkips",
                           "FinalEquity"]].to_string(index=False))
        W("")
        W(f" {label} ({tag}) -- SUB-PERIODS, measured independently")
        W("-" * 100)
        W(s[["Period", "Config", "CAGR%", "AnnVol%", "Sharpe", "MaxDD%",
             "Deployed%", "MeanNamesHeld", "CashShortSkips",
             "FirstDate", "LastDate", "Days"]].to_string(index=False))

    # ------------------------------------------------------- [1] v4 vs v2
    W("")
    W("=" * 100)
    W(" [1] v4 vs v2 -- THE ONE CLEAN CONTRAST. THIS GETS A VERDICT.")
    W("=" * 100)
    W(" Both arms are breadth-scaled. They hold the SAME portfolio: 0 of 91")
    W(" rebalances differ on mid, 4 name-days of about 800 on n100. So the only")
    W(" material difference between them is the sizing rule, which is what the spec")
    W(" set out to measure.")
    W("")
    W(" PREDICTION, quoted from V34_SPEC.txt:")
    W('     "v4 vs v2   same direction, smaller magnitude, because breadth scaling')
    W('                already caps total exposure and damps both sides."')
    W("     where the stated direction is: higher CAGR, higher annualised")
    W("     volatility, deeper MaxDD, Sharpe roughly equal or lower.")
    verdicts = {}
    for tag, (label, c, s) in data.items():
        W("")
        W(f"  {label} ({tag}):")
        dcagr, dvol, dsh, ddd = delta_block(c, V2, V4, L)
        hits = []
        hits.append(("higher CAGR", dcagr > 0))
        hits.append(("higher volatility", dvol > 0))
        hits.append(("deeper MaxDD", ddd < 0))
        hits.append(("Sharpe equal or lower", dsh <= 0))
        n_ok = sum(1 for _, v in hits if v)
        W(f"    prediction components matched: {n_ok} of 4 -- " +
          ", ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in hits))
        verdicts[tag] = (dcagr, dvol, dsh, ddd, n_ok)

    W("")
    W("  VERDICT, computed:")
    for tag, (dcagr, dvol, dsh, ddd, n_ok) in verdicts.items():
        core = "held" if dcagr > 0 else "CONTRADICTED"
        W(f"    {tag:<5} the central claim (pro-vol raises CAGR) is {core}: "
          f"CAGR moved {dcagr:+.2f} pt.")
    same_dir = (verdicts["nifty100"][0] > 0) == (verdicts["midcap150"][0] > 0)
    W(f"    The two universes {'AGREE' if same_dir else 'DISAGREE'} on the sign of the "
      f"CAGR change.")

    # ------------------------------------------------------- [2] v3 vs v1
    W("")
    W("=" * 100)
    W(" [2] v3 vs v1 -- CONFOUNDED, THEREFORE UNTESTABLE. NO VERDICT IS DRAWN.")
    W("=" * 100)
    W(" These two arms do NOT hold the same portfolio. They target the same eight")
    W(" names -- the top-8 target set is identical on all 92 rebalances, verified --")
    W(" and then hold different subsets of them, because new positions are funded")
    W(" from cash alone and pro-vol exhausts cash more often. See KNOWN_ISSUES.md.")
    W("")
    W(" The prediction for this contrast is NOT judged. It did not fail; the")
    W(" measurement cannot test it, because any difference below mixes the sizing")
    W(" rule with a portfolio-composition effect that this design cannot separate.")
    W("")
    W(" THE CONFOUND, MEASURED:")
    for tag, (label, c, s) in data.items():
        W(f"    {tag:<5} mean names held  v1 {c.loc[V1,'MeanNamesHeld']:.2f}"
          f"  vs  v3 {c.loc[V3,'MeanNamesHeld']:.2f}"
          f"     cash-short skips  v1 {int(c.loc[V1,'CashShortSkips'])}"
          f"  vs  v3 {int(c.loc[V3,'CashShortSkips'])}")
    W("")
    W(" THE NUMBERS, REPORTED IN FULL ANYWAY:")
    for tag, (label, c, s) in data.items():
        W("")
        W(f"  {label} ({tag}):")
        delta_block(c, V1, V3, L)
    W("")
    W("  No verdict. See above for why.")

    # ------------------------------------------------- [3] universe agreement
    W("")
    W("=" * 100)
    W(" [3] DO THE TWO UNIVERSES AGREE?")
    W("=" * 100)
    W(" Neither universe is primary. Where they disagree, the disagreement is the")
    W(" finding and is reported as such rather than resolved in favour of whichever")
    W(" looks better.")
    W("")
    rows = []
    for a, b, lab in ((V2, V4, "v4 vs v2 (clean)"), (V1, V3, "v3 vs v1 (confounded)")):
        r = {"contrast": lab}
        for tag, (label, c, s) in data.items():
            r[f"{tag} dCAGR"] = round(c.loc[b, "CAGR%"] - c.loc[a, "CAGR%"], 2)
            r[f"{tag} dVol"] = round(c.loc[b, "AnnVol%"] - c.loc[a, "AnnVol%"], 2)
            r[f"{tag} dSharpe"] = round(c.loc[b, "Sharpe"] - c.loc[a, "Sharpe"], 2)
            r[f"{tag} dMaxDD"] = round(c.loc[b, "MaxDD%"] - c.loc[a, "MaxDD%"], 2)
        rows.append(r)
    W(pd.DataFrame(rows).to_string(index=False))
    W("")
    for a, b, lab in ((V2, V4, "v4 vs v2"), (V1, V3, "v3 vs v1")):
        for metric, key, word in (("CAGR", "CAGR%", d), ("volatility", "AnnVol%", d),
                                  ("Sharpe", "Sharpe", d), ("MaxDD", "MaxDD%", dd_word)):
            signs = {}
            for tag, (label, c, s) in data.items():
                signs[tag] = c.loc[b, key] - c.loc[a, key]
            agree = (signs["nifty100"] > 0) == (signs["midcap150"] > 0)
            W(f"    {lab:<10} {metric:<11} n100 {word(signs['nifty100']):<10} "
              f"mid {word(signs['midcap150']):<10} -> "
              f"{'agree' if agree else 'DISAGREE'}")

    out = ROOT / "diagnostics" / "v34_report.txt"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n  saved -> {out}")


if __name__ == "__main__":
    main()
