"""
capacity.py -- can the universe absorb the orders a run sent? One definition.

Measured after a run from its own artefacts and the universe's raw price files; it
changes no results file. run.py prints it into run.log and RUN.txt, and
dashboard/export_dashboard_data.py puts it in each run's "capacity" block.

    order % ADV   each buy fill's value (qty x fill price) as a percent of the
                  stock's average traded value (close x volume) over the 20
                  sessions before the fill, from the raw price files, counting
                  NSE rows only (exchange == NSE) and averaging over the NSE rows
                  inside those 20 sessions
    not measurable  a buy fill with no NSE row in its 20 sessions; never estimated,
                  counted and shown as a number and a share of the buy fills
    unfilled cap  the buy value the participation cap left unfilled, as a percent of
                  the buy value wanted: for each "participation cap" BUY row of
                  daily_skipped, (wanted - capped) shares at that day's close, over
                  that plus every buy fill's value

WHY NSE ROWS ONLY. The supplier's price files mix NSE and BSE rows day by day, and a
BSE row's volume is BSE's alone, a small fraction of NSE's for most names
(KNOWN_ISSUES.md, "The price files mix NSE and BSE rows"). The engine, the
participation cap and the model features still read every row; only this measure
leaves the BSE rows out.

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
    symbol, as Series indexed by date; None when the file is absent. The traded
    value counts NSE rows only and is averaged over the NSE rows among those 20
    sessions; it is missing when there is none. A file with no exchange column has
    no NSE row. The close is every row's."""
    key = (str(raw_dir), sym)
    if key not in cache:
        import config
        f = Path(raw_dir) / f"{sym}.csv"
        if not f.exists():
            cache[key] = None
        else:
            d = config.read_price_csv(f).set_index("date").sort_index()
            nse = (d["exchange"] == "NSE") if "exchange" in d.columns else False
            tv = (d["close"] * d["volume"]).where(nse)
            cache[key] = (d["close"], tv.rolling(20, min_periods=1).mean().shift(1))
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
    n_out = len(buys) - len(pct)
    out = {"buy_fills": len(buys), "measured_fills": len(pct),
           "not_measurable_fills": n_out,
           "not_measurable_pct": n_out / len(buys) * 100 if len(buys) else 0.0,
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
           f"(NSE rows only) median {f(m['median_pct_adv'])}, 95th percentile "
           f"{f(m['p95_pct_adv'])}, largest {f(m['max_pct_adv'])}; "
           f"{m['not_measurable_fills']:,} not measurable ({m['not_measurable_pct']:.1f}%, no NSE "
           f"row in their 20 sessions); cap left {m['unfilled_cap_pct']:.2f}% of buy value unfilled"]
    if m["warning"]:
        out.append(f"CAPACITY WARNING: {name}: {m['warning']}. The universe may not absorb orders "
                   f"of this size; the return is not reliable at this capital.")
    return out
