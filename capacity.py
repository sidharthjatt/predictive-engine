"""
capacity.py -- can the universe absorb the orders a run sent? One definition.

Measured after a run from its own artefacts and the universe's raw price files; it
changes no results file. run.py prints it into run.log and RUN.txt, and
dashboard/export_dashboard_data.py puts it in each run's "capacity" block.

    order % ADV   each buy fill's value (qty x fill price) as a percent of the
                  stock's average traded value (close x volume) over the 20
                  sessions before the fill, from the raw price files (the measure
                  of tools/capital_ladder.py)
    unfilled cap  the buy value the participation cap left unfilled, as a percent of
                  the buy value wanted: for each "participation cap" BUY row of
                  daily_skipped, (wanted - capped) shares at that day's close, over
                  that plus every buy fill's value

A WARNING is given when any threshold below is passed. They say when the run's
fills are large next to what the stock trades, which no profile prices in full: the
research profile has no cap and no impact, and the tradeable profile's cap allows a
whole day's median volume at impact k 0.
"""
import math
import re
from pathlib import Path

P95_PCT_ADV = 10.0         # 95th-percentile buy fill, percent of 20-day average traded value
MAX_PCT_ADV = 25.0         # any single buy fill
UNFILLED_CAP_PCT = 5.0     # buy value the participation cap left unfilled


def _raw(raw_dir, sym, cache):
    """(close, average traded value over the 20 sessions before each date) for one
    symbol, as Series indexed by date; None when the file is absent."""
    key = (str(raw_dir), sym)
    if key not in cache:
        import config
        f = Path(raw_dir) / f"{sym}.csv"
        if not f.exists():
            cache[key] = None
        else:
            d = config.read_price_csv(f).set_index("date").sort_index()
            cache[key] = (d["close"], (d["close"] * d["volume"]).rolling(20).mean().shift(1))
    return cache[key]


def _pct(values, q):
    """The q-quantile (0..1) of a sorted list, by linear interpolation; None if empty."""
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def measure(costs, skipped, raw_dir, cache=None):
    """The capacity figures of one run. `costs` is its COSTS_<tag>.csv and `skipped`
    its daily_skipped_<tag>.csv, as DataFrames with dates parsed; `raw_dir` is the
    universe's raw price directory. `cache` may be shared across runs of one call."""
    import pandas as pd
    cache = {} if cache is None else cache
    buys = costs[costs["side"] == "BUY"]
    pct, filled = [], 0.0
    for r in buys.itertuples(index=False):
        v = float(r.qty) * float(r.fill_price)
        filled += v
        s = _raw(raw_dir, r.symbol, cache)
        adv = s[1].get(pd.Timestamp(r.date), float("nan")) if s is not None else float("nan")
        if adv == adv and adv > 0:
            pct.append(v / adv * 100)
    unfilled = 0.0
    if skipped is not None and len(skipped):
        rows = skipped[(skipped["reason"] == "participation cap") & (skipped["side"] == "BUY")]
        for r in rows.itertuples(index=False):
            m = re.search(r"wanted ([\d,]+) sh, capped to ([\d,]+)", str(r.detail))
            s = _raw(raw_dir, r.symbol, cache)
            if m is None or s is None:
                continue
            w, q = (float(x.replace(",", "")) for x in m.groups())
            close = s[0].asof(pd.Timestamp(r.date))
            if close == close:
                unfilled += (w - q) * float(close)
    pct.sort()
    out = {"buy_fills": len(buys), "measured_fills": len(pct),
           "median_pct_adv": _pct(pct, 0.5), "p95_pct_adv": _pct(pct, 0.95),
           "max_pct_adv": pct[-1] if pct else None,
           "unfilled_cap_pct": unfilled / (filled + unfilled) * 100 if filled + unfilled else 0.0}
    out["warning"] = warning(out)
    return out


def warning(m):
    """The reasons a run passes a threshold, as one sentence, or None."""
    why = []
    if m["p95_pct_adv"] is not None and m["p95_pct_adv"] > P95_PCT_ADV:
        why.append(f"95th-percentile buy fill {m['p95_pct_adv']:.1f}% of 20-day average traded "
                   f"value (limit {P95_PCT_ADV:g}%)")
    if m["max_pct_adv"] is not None and m["max_pct_adv"] > MAX_PCT_ADV:
        why.append(f"largest buy fill {m['max_pct_adv']:.1f}% (limit {MAX_PCT_ADV:g}%)")
    if m["unfilled_cap_pct"] > UNFILLED_CAP_PCT:
        why.append(f"participation cap left {m['unfilled_cap_pct']:.1f}% of buy value unfilled "
                   f"(limit {UNFILLED_CAP_PCT:g}%)")
    return "; ".join(why) if why else None


def lines(name, m):
    """The run.log and RUN.txt lines for one universe and arm."""
    f = lambda x: "n/a" if x is None else f"{x:.2f}%"
    out = [f"capacity  : {name}: {m['buy_fills']:,} buy fills, of 20-day average traded value "
           f"median {f(m['median_pct_adv'])}, 95th percentile {f(m['p95_pct_adv'])}, largest "
           f"{f(m['max_pct_adv'])}; cap left {m['unfilled_cap_pct']:.2f}% of buy value unfilled"]
    if m["warning"]:
        out.append(f"CAPACITY WARNING: {name}: {m['warning']}. The universe may not absorb orders "
                   f"of this size; the return is not reliable at this capital.")
    return out
