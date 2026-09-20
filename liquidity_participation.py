"""
liquidity_participation.py -- how much of the market each fill would actually be.

MEASUREMENT ONLY. Nothing is changed by this script.

THE VOLUME COLUMN IS NOT IN THE PANEL
    The task described using "the volume column already in the panel". It is not
    there: the score panel is date,symbol,open,close,score,year and the raw panel
    carries the 17 features, y_rank and scorable but no volume. build_panel never
    keeps it (build_scores_n100.py:44 lists the columns retained).

    Volume IS in the source CSVs, so the median is built from those.

ONE DEFINITION, AND IT IS THE CAP'S
    This file used to compute the median itself: the last 20 dated rows of the
    symbol's own file with volume > 0, taking whatever was there even if fewer than
    20. tradability.median_volume, which the participation cap actually consumes,
    does something different: rolling(20).median().shift(1) over the trading
    calendar, inside the backtest window, with no volume > 0 filter and no result
    at all until 20 sessions exist.

    Both called themselves "prior-20-session median volume" and they are not the
    same number. Measured 2026-09-20 on the midcap150 tradeable arms: they differ
    by more than 1% on 175 of 842 fills (v1) and 215 of 998 (v2), by more than 10%
    on 61 and 77, and by up to 140% on one fill. On v1 they even disagree about
    whether a fill clears a 0.10 cap, on n=1 fill of 842.

    So this file no longer has a definition. It calls tradability.median_volume.
    A measurement of the cap that used a different median than the cap would be
    measuring something nobody runs.

    TWO CONSEQUENCES, BOTH DELIBERATE. Fills in the first 20 sessions of the window
    (60 for the 60-day column) now have no median and are excluded rather than
    being given a short-window one -- the cap does not fire on them either. And the
    symbol folder is prepare_data_dir(), the constituents the cap reads, not
    raw_data_dir, which carries the index file as well.

    diagnostics/liquidity_participation.txt ON DISK PREDATES THIS CHANGE. Its
    figures, including the 1,614.52% quoted in EXPERIMENTS.md and DRAWDOWN_EXIT_
    SPEC.txt, were produced by the old definition. Regenerate before citing them
    again.

WHAT PARTICIPATION MEANS HERE
    order quantity / median daily volume over the prior N sessions, as a
    percentage. The median is taken over sessions STRICTLY BEFORE the fill date, so
    it is knowable at the time the order is sent. 20-day and 60-day windows are
    both reported.

CAPITAL SCALING
    The backtest runs Rs 10,00,000. Participation scales linearly with capital
    because every position is a fixed fraction of the portfolio, so the quantity at
    Rs 50,00,000 is 5x and at Rs 2,00,00,000 is 20x. The fills themselves are not
    re-simulated at those sizes -- doing so would change which names are affordable
    and confound the measurement. This reports what the SAME trades would represent
    at larger size, which is the question being asked.

    That linearity is exact only while the strategy's decisions are unchanged. At a
    size where participation is genuinely prohibitive, a real implementation would
    have to trade differently, so the large-capital figures are an upper bound on
    tradeability rather than a forecast of what would happen.
"""
import sys
import warnings

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))

import config
import tradability
from engine_core import _load_calendar
from universes.registry import REGISTRY

CAPITALS = [(1_000_000, "Rs 10,00,000  (the backtest)"),
            (5_000_000, "Rs 50,00,000"),
            (20_000_000, "Rs 2,00,00,000")]
BANDS = [("under Rs 10", 0, 10), ("Rs 10-50", 10, 50),
         ("Rs 50-250", 50, 250), ("above Rs 250", 250, np.inf)]
FLAG = 10.0          # participation percentage worth listing individually

# THE SAME THREE FACTS, FROM THE REGISTRY SINCE STEP 7. prepare_data_dir() is the
# folder the participation cap reads -- the constituents, without the index file
# raw_data_dir also holds. median_volume globs it, so no symbol list is needed to
# resolve names.
UNIV = [
    ("nifty100", REGISTRY["nifty100"].metrics_dir,
     REGISTRY["nifty100"].prepare_data_dir()),
    ("midcap150", REGISTRY["midcap150"].metrics_dir,
     REGISTRY["midcap150"].prepare_data_dir()),
]


def measure(tag, mdir, data_dir):
    """Fills joined to the cap's own median volume, at 20 and 60 sessions."""
    tr = pd.read_csv(Path(mdir) / f"daily_trades_{tag}.csv", parse_dates=["date"])
    cal = _load_calendar()
    med = {w: tradability.median_volume(data_dir, cal, config.BT_START_DATE,
                                        config.BT_END_DATE, win=w)
           for w in (20, 60)}

    rows = []
    missing = set()
    for _, t in tr.iterrows():
        sym, d, q = t["symbol"], t["date"], float(t["qty"])
        if sym not in med[20]:
            missing.add(sym)
            continue
        rows.append({"date": d, "symbol": sym, "action": t["action"], "qty": q,
                     "price": float(t["price"]),
                     "med20": med[20][sym].get(d, np.nan),
                     "med60": med[60][sym].get(d, np.nan)})
    f = pd.DataFrame(rows)
    if missing:
        print(f"    NOTE: no volume data for {len(missing)} symbols: "
              f"{', '.join(sorted(missing)[:8])}")
    return f


def band_of(p):
    for name, lo, hi in BANDS:
        if lo <= p < hi:
            return name
    return BANDS[-1][0]


def main():
    import subprocess
    try:
        _commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.strip()
    except Exception:
        _commit = "unknown"
    print("=" * 108)
    print(" LIQUIDITY PARTICIPATION -- order quantity as a share of median daily volume")
    print(" Measurement only. Nothing is changed.")
    print("=" * 108)
    print(f" Generated {pd.Timestamp.today().date()} at commit {_commit}.")
    print(" MEDIAN VOLUME IS tradability.median_volume, the one the participation cap")
    print(" consumes: rolling(20).median().shift(1) over the trading calendar, inside")
    print(" the backtest window, no volume>0 filter, no value until 20 sessions exist.")
    print(" This file previously used a different median of its own -- last 20 dated")
    print(" rows with volume>0, however few -- and the two disagree by more than 1% on")
    print(" about a fifth of fills. Figures below are NOT comparable to a copy of this")
    print(" file generated before 2026-09-20.")
    print(" Fill counts also moved when the universes were repointed at")
    print(" Final_Without_Survivorship_Data on 2026-09-18, so both the definition and")
    print(" the underlying daily_trades differ from the superseded copy.")
    print(" WHICH OF THE TWO MOVED THE NUMBERS, measured 2026-09-20 on the CURRENT")
    print(" daily_trades so only the definition varies: on midcap150 (n=1006 fills)")
    print(" the old definition gives median 0.058% / p90 0.962% / p99 11.070% / max")
    print(" 34.458% and the new gives 0.057% / 0.928% / 11.128% / 34.458%, with 12")
    print(" fills above 10% either way. The aggregate barely moves. Per FILL the two")
    print(" differ by more than 1% on about a fifth of fills, which is why only one")
    print(" definition is kept, but it is NOT what changed the headline figures.")
    print(" THE 1,614.52% IS GONE BECAUSE ITS DATA IS GONE. That was AIIL SELL")
    print(" 2021-06-07, 29,465 shares against a 1,825-share median. AIIL's file now")
    print(" starts 2024-04-23, so the tree holds no 2021 row for it and no fill of")
    print(" that size exists in any current daily_trades. It was not recomputed to a")
    print(" smaller number; the run that produced it cannot be reproduced.")
    print("=" * 108)

    for tag, mdir, data_dir in UNIV:
        print(f"\n{'='*108}\n {tag.upper()}\n{'='*108}")
        f = measure(tag, mdir, data_dir)
        f["band"] = f["price"].apply(band_of)
        print(f"  fills measured {len(f):,} | symbols {f['symbol'].nunique()} | "
              f"window {f['date'].min().date()} -> {f['date'].max().date()}")
        print(f"  fills with a 20-session median: {int(f['med20'].notna().sum()):,} | "
              f"60-session: {int(f['med60'].notna().sum()):,}. A fill inside the first "
              f"20 (or 60) sessions of the window has none, and the cap does not fire "
              f"on it either.")

        for cap, lab in CAPITALS:
            mult = cap / 1_000_000
            print(f"\n  {'-'*104}")
            print(f"  CAPITAL {lab}   (quantity x{mult:g})")
            print(f"  {'-'*104}")
            for win, col in (("20d", "med20"), ("60d", "med60")):
                p = (f["qty"] * mult / f[col] * 100).replace([np.inf, -np.inf], np.nan)
                g = pd.DataFrame({"band": f["band"], "p": p}).dropna()
                print(f"\n    participation vs prior-{win} median daily volume")
                print(f"      {'band':<16}{'fills':>7}{'median':>10}{'p90':>10}"
                      f"{'p99':>10}{'max':>12}")
                for name, _, _ in BANDS:
                    s = g[g["band"] == name]["p"]
                    if not len(s):
                        print(f"      {name:<16}{0:>7}{'--':>10}{'--':>10}{'--':>10}{'--':>12}")
                        continue
                    print(f"      {name:<16}{len(s):>7}{s.median():>9.3f}%"
                          f"{s.quantile(.90):>9.3f}%{s.quantile(.99):>9.3f}%"
                          f"{s.max():>11.3f}%")
                s = g["p"]
                print(f"      {'ALL':<16}{len(s):>7}{s.median():>9.3f}%"
                      f"{s.quantile(.90):>9.3f}%{s.quantile(.99):>9.3f}%{s.max():>11.3f}%")
                over = g[g["p"] > FLAG]
                print(f"      fills above {FLAG:g}% participation: {len(over)} "
                      f"({len(over)/len(g)*100:.2f}% of fills)")

            # the individual list, on the 20-day window, for this capital
            p20 = (f["qty"] * mult / f["med20"] * 100).replace([np.inf, -np.inf], np.nan)
            hit = f.assign(part=p20)
            hit = hit[hit["part"] > FLAG].sort_values("part", ascending=False)
            if len(hit):
                print(f"\n    EVERY FILL ABOVE {FLAG:g}% PARTICIPATION (prior-20d median), "
                      f"{len(hit)} of {len(f)}")
                print(f"      {'date':<12}{'symbol':<13}{'side':<6}{'qty':>10}"
                      f"{'price':>10}{'med vol 20d':>14}{'part%':>9}")
                for _, x in hit.iterrows():
                    print(f"      {str(x['date'].date()):<12}{x['symbol']:<13}"
                          f"{x['action']:<6}{int(x['qty']*mult):>10,}{x['price']:>10.2f}"
                          f"{int(x['med20']):>14,}{x['part']:>8.2f}%")
            else:
                print(f"\n    No fill exceeds {FLAG:g}% participation at this capital.")


if __name__ == "__main__":
    main()
