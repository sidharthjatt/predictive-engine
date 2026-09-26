"""
tax_on_all_arms.py -- every arm's tax-on headline CAGR against the investable taxed buy & hold.

    ./venv/bin/python results/tax_on_all_arms.py

Writes diagnostics/tax_on_all_arms.csv: 4 arms x 8 universes, research profile,
cadence 20, tax on, headline (nothing sold at the end, the last partial financial
year settled on the final session).

    arm_cagr   from that arm's column of results_<u>/metrics/v34_equity_tax.csv,
               engine_core.metrics' formula, rounded to 4 decimals -- the
               precision BH_LOTS_*.csv carries.
    bh_cagr    the investable taxed buy & hold headline, "bh_lots after tax" in
               BH_LOTS_<tag>_tax.csv. The basket is the same for every arm; the
               script checks that all four arms' BH_LOTS files agree on it.
    gap        arm_cagr - bh_cagr, from the unrounded arm CAGR.

CROSS-CHECK, NOT A SECOND SOURCE. Each arm's CAGR is also on the "<arm> after tax"
line of its own BH_LOTS file, from bh_lots_after_tax's separate taxed backtest.
The two must agree to 4 decimals, and the script exits 1 if any cell does not.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd                                            # noqa: E402

import arms.registry as arm_reg                                 # noqa: E402
from config import read_table                                  # noqa: E402
from universes.registry import gated                           # noqa: E402

OUT = ROOT / "diagnostics" / "tax_on_all_arms.csv"


def cagr(eq):
    """engine_core.metrics' CAGR, in percent, at full precision."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100)


def bh_lots(u, arm):
    tag = u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}"
    t = read_table(Path(u.metrics_dir) / f"BH_LOTS_{tag}_tax.csv").set_index("line")
    return t


def main():
    rows, bad = [], []
    for u in gated():
        eq = read_table(Path(u.metrics_dir) / "v34_equity_tax.csv",
                        parse_dates=["date"]).set_index("date")
        bh_seen = set()
        for arm in arm_reg.ARMS.values():
            c = cagr(eq[arm.equity_column])
            t = bh_lots(u, arm)
            bh = float(t.loc["bh_lots after tax", "cagr_full"])
            bh_seen.add(bh)
            other = float(t.loc[f"{arm.name} after tax", "cagr_full"])
            if round(c, 4) != other:
                bad.append(f"{u.tag} {arm.name}: v34_equity_tax {c:.4f}, BH_LOTS {other:.4f}")
            rows.append({"universe": u.tag, "arm": arm.name, "label": arm.label,
                         "arm_cagr": round(c, 4), "bh_cagr": bh,
                         "gap": round(c - bh, 4),
                         "arm_final_equity": round(float(eq[arm.equity_column].iloc[-1]), 2),
                         "arm_tax_paid": float(t.loc[f"{arm.name} after tax", "tax_paid"])})
        if len(bh_seen) != 1:
            bad.append(f"{u.tag}: the four BH_LOTS files disagree on the buy & hold: {sorted(bh_seen)}")
    df = pd.DataFrame(rows)
    # naming: axis-free -- a record fixed to research, cadence 20, tax on; it
    # varies over no published axis
    df.to_csv(OUT, index=False, quoting=csv.QUOTE_MINIMAL)
    print(df.to_string(index=False))
    if bad:
        print("\nCROSS-CHECK FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"\n{len(df)} cells; every arm CAGR agrees with its BH_LOTS line to 4 decimals. -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
