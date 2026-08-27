"""
density_fix_lookahead.py -- does the per-symbol beta/idio computation look ahead?

The density fix made the 58's numbers free to move, and if they move UPWARD that is
the pleasant direction and therefore the one to distrust. Three independent checks:

  1. NO FILL IN THE ALIGNMENT. beta_60/idio_vol_60 must be non-NaN on exactly the
     dates where the symbol has a return, never on a date it did not trade. A
     back-fill would put a value on a date before it could be computed; a forward
     fill would carry a stale value onto a non-trading date. reindex() without a
     method argument does neither, and this asserts it rather than trusting it.

  2. CAUSALITY BY TRUNCATION. The value at date t computed on the FULL history must
     equal the value at t computed on history truncated at t. If any future row
     influenced it, these differ. This is the same test EXP14 used for its Gate 3.

  3. WINDOW DIRECTION. Every rolling window must end at the current observation.
     Checked by construction against a hand-rolled trailing window on one symbol.

Reads raw CSVs only. Writes nothing.
"""
import sys
sys.dont_write_bytecode = True

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
import config, config_mid
from features_v2 import add_stock_features, add_market_relative_features

W = 60
N_SYMBOLS = 40          # the gappiest names, where a look-ahead would show first
N_DATES = 8


def build(files, upto=None):
    """THE SYMBOL SET MUST BE IDENTICAL IN BOTH BUILDS.

    An earlier version of this test dropped symbols with fewer than W+5 rows. That
    filter behaves differently under truncation -- AIIL, MEDANTA and SBICARD have
    sparse early data and fell out of the truncated build -- and since the market
    return is the cross-sectional mean over whatever symbols are present, dropping
    them changed the market on 55 dates and moved every beta by up to 1.06e-01.
    That was the test perturbing its own control, not the feature looking ahead.
    Every symbol with enough rows to difference is now kept in both builds.
    """
    frames = []
    for f in files:
        r = config.read_price_csv(f).sort_values("date")
        r = r[["date", "open", "high", "low", "close", "volume"]].dropna()
        if upto is not None:
            r = r[r["date"] <= upto]
        if len(r) < 3:
            continue
        d = add_stock_features(r); d["symbol"] = f.stem
        frames.append(d)
    return add_market_relative_features(pd.concat(frames, ignore_index=True))


def main():
    all_files = sorted(config_mid.ensure_constituents_dir().glob("*.csv"))
    # rank by gappiness: fewest rows relative to their own span
    gappy = []
    for f in all_files:
        d = config.read_price_csv(f)[["date", "close"]].dropna()
        if len(d) < 400:
            continue
        span = (d["date"].max() - d["date"].min()).days / 365.25 * 252
        gappy.append((len(d)/span if span > 0 else 1.0, f))
    files = [f for _, f in sorted(gappy)[:N_SYMBOLS]]
    print(f"testing on the {len(files)} gappiest MidCap150 names "
          f"(density {sorted(gappy)[0][0]:.2f} to {sorted(gappy)[len(files)-1][0]:.2f} "
          f"of their own span)")

    full = build(files)
    print(f"full panel: {len(full):,} rows, {full['symbol'].nunique()} symbols, "
          f"{full['date'].min().date()} -> {full['date'].max().date()}")

    # ---------------------------------------------------------------- check 1
    print("\n[1] NO FILL IN THE ALIGNMENT")
    bad = 0
    for sym, g in full.groupby("symbol"):
        has_ret = g["ret_1d"].notna()
        for col in ("beta_60", "idio_vol_60"):
            leaked = g[col].notna() & ~has_ret
            bad += int(leaked.sum())
    print(f"    rows where beta/idio exist but the symbol has no return: {bad}")
    print(f"    -> {'PASS' if bad == 0 else 'FAIL'} "
          f"(no back-fill and no forward-fill onto non-trading dates)")

    # ---------------------------------------------------------------- check 2
    print("\n[2] CAUSALITY BY TRUNCATION -- value at t must not depend on t+1..")
    dates = sorted(full["date"].unique())
    picks = [dates[int(len(dates)*q)] for q in (0.55, 0.62, 0.69, 0.76, 0.83, 0.90, 0.95, 0.98)][:N_DATES]
    worst = 0.0; n_cmp = 0; missing = 0
    for t in picks:
        tr = build(files, upto=pd.Timestamp(t))
        a = full[full["date"] == t].set_index("symbol")[["beta_60", "idio_vol_60"]]
        b = tr[tr["date"] == t].set_index("symbol")[["beta_60", "idio_vol_60"]]
        common = a.index.intersection(b.index)
        for col in ("beta_60", "idio_vol_60"):
            x1, x2 = a.loc[common, col], b.loc[common, col]
            both = x1.notna() & x2.notna()
            n_cmp += int(both.sum())
            missing += int((x1.notna() != x2.notna()).sum())
            if both.any():
                worst = max(worst, float((x1[both]-x2[both]).abs().max()))
        print(f"    {pd.Timestamp(t).date()}: {len(common)} symbols compared, "
              f"running max abs diff {worst:.3e}")
    print(f"    values compared: {n_cmp:,} | defined-vs-undefined mismatches: {missing}")
    ok2 = worst < 1e-9 and missing == 0
    print(f"    -> {'PASS' if ok2 else 'FAIL'} (max abs diff {worst:.3e})")

    # ---------------------------------------------------------------- check 3
    print("\n[3] WINDOW DIRECTION -- rolling must be trailing, not centred/leading")
    sym = full["symbol"].value_counts().index[0]
    g = full[full["symbol"] == sym].sort_values("date")
    ys = g.set_index("date")["ret_1d"].dropna()
    mkt = full.groupby("date")["ret_1d"].mean()
    xs = mkt.reindex(ys.index)
    i = len(ys) - 5
    w_y, w_x = ys.iloc[i-W+1:i+1], xs.iloc[i-W+1:i+1]      # trailing window, ends at i
    cov = (w_y*w_x).mean() - w_y.mean()*w_x.mean()
    var = w_x.var()*(W-1)/W
    manual = cov/(var + 1e-12)
    engine = g.set_index("date")["beta_60"].reindex(ys.index).iloc[i]
    print(f"    {sym} at {ys.index[i].date()}: hand-rolled trailing beta {manual:.10f}")
    print(f"    {'':<{len(sym)}}   engine beta                    {engine:.10f}")
    ok3 = abs(manual-engine) < 1e-9
    print(f"    -> {'PASS' if ok3 else 'FAIL'} (diff {abs(manual-engine):.3e})")

    print("\n" + "="*70)
    allok = bad == 0 and ok2 and ok3
    print("  NO LOOK-AHEAD DETECTED" if allok else "  LOOK-AHEAD SUSPECTED -- investigate")
    print("="*70)


if __name__ == "__main__":
    main()
