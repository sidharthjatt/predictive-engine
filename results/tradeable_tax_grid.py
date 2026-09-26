"""
tradeable_tax_grid.py -- research against tradeable, tax on, all 32 cells.

    ./venv/bin/python results/tradeable_tax_grid.py

Reads the artefacts of two pipeline runs at cadence 20, tax on:
    research   run.py --universe all --arm all --tax on
    tradeable  run.py --universe all --arm all --tax on --profile tradeable
and writes diagnostics/tradeable_tax_all_arms.csv, one row per (universe, arm).

    research_cagr, tradeable_cagr   that arm's column of v34_equity_tax.csv and
                                    v34_equity_tradeable_tax.csv, full precision,
                                    rounded to 4 decimals
    diff                            tradeable - research
    cap_binds                       rows with reason "participation cap" in the
                                    tradeable run's own daily_skipped artefact
    bh_research, bh_tradeable       "bh_lots after tax" from each profile's
                                    BH_LOTS file; the basket takes no cap, so the
                                    two must be equal, and the script checks it
    gap_research, gap_tradeable     arm minus the investable taxed buy & hold

The tradeable profile is UNGATED (profiles.UNGATED_NOTICE): nothing replays what
the port does under it. These are engine figures, not certified ones.
"""
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

OUT = ROOT / "diagnostics" / "tradeable_tax_all_arms.csv"


def cagr(eq):
    """engine_core.metrics' CAGR, in percent, at full precision."""
    ny = (eq.index[-1] - eq.index[0]).days / 365.25
    return float(((eq.iloc[-1] / eq.iloc[0]) ** (1 / ny) - 1) * 100)


def tag(u, arm, sfx):
    return (u.tag if arm.name == "v2" else f"{u.tag}_{arm.name}") + sfx


def main():
    rows, bad = [], []
    for u in gated():
        M = Path(u.metrics_dir)
        eq_r = read_table(M / "v34_equity_tax.csv", parse_dates=["date"]).set_index("date")
        eq_t = read_table(M / "v34_equity_tradeable_tax.csv", parse_dates=["date"]).set_index("date")
        for arm in arm_reg.ARMS.values():
            r = cagr(eq_r[arm.equity_column])
            t = cagr(eq_t[arm.equity_column])
            bh_r = float(read_table(M / f"BH_LOTS_{tag(u, arm, '_tax')}.csv")
                         .set_index("line").loc["bh_lots after tax", "cagr_full"])
            bh_t = float(read_table(M / f"BH_LOTS_{tag(u, arm, '_tradeable_tax')}.csv")
                         .set_index("line").loc["bh_lots after tax", "cagr_full"])
            if bh_r != bh_t:
                bad.append(f"{u.tag} {arm.name}: buy & hold research {bh_r} tradeable {bh_t}")
            sk = read_table(M / f"daily_skipped_{tag(u, arm, '_tradeable_tax')}.csv")
            binds = int((sk["reason"] == "participation cap").sum()) if len(sk) else 0
            rows.append({"universe": u.tag, "arm": arm.name,
                         "research_cagr": round(r, 4), "tradeable_cagr": round(t, 4),
                         "diff": round(t - r, 4), "cap_binds": binds,
                         "bh_cagr": bh_r,
                         "gap_research": round(r - bh_r, 4),
                         "gap_tradeable": round(t - bh_t, 4)})
    df = pd.DataFrame(rows)
    # naming: axis-free -- a record of one fixed comparison (cadence 20, tax on,
    # research against tradeable); it varies over no published axis
    df.to_csv(OUT, index=False)
    print(df.to_string(index=False))
    if bad:
        print("\nCHECK FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"\n{len(df)} cells -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
