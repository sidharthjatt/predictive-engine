"""ratio_clean.py -- replace reverting adj_close / close ratio events with the previous ratio.

The rule is experiments/DATA_CLEANING_SPEC.txt. In short: for each symbol, walk its
sessions (rows on the NSE trading calendar) holding p, the previous session's
ratio r = adj_close / close. When r moves more than TOL away from p and comes back
within TOL of p within MAX_LEN sessions, every session of that excursion takes p.
A move that does not come back within MAX_LEN sessions is a lasting shift and is
left alone.

engine_core.build_panel calls clean() on each file's frame immediately before
canonical_price. That is the only call site in the pipeline. The raw files are
never written.

The rule is not causal: whether session t is cleaned depends on up to MAX_LEN
later sessions. See the spec.
"""
import numpy as np
import pandas as pd

TOL = 0.001
MAX_LEN = 5


def fallback_mask(d):
    """Rows canonical_price sends to its close fallback. Same test, same columns."""
    a = d["adj_close"]
    return ((a <= 0) | (a < d["low"]) | (a > d["high"])).to_numpy()


def scan(r, ok):
    """Reverting events in a ratio series, as [(start, length, p)] in positions.

    `r` is the ratio per session in date order and `ok` is False where the row is
    a canonical_price fallback row, which breaks the sequence (spec rule 4).
    """
    events = []
    n = len(r)
    p = None
    t = 0
    while t < n:
        if not ok[t]:
            p = None
            t += 1
            continue
        if p is None or abs(r[t] / p - 1) <= TOL:
            p = r[t]
            t += 1
            continue
        k_back = 0
        for k in range(1, MAX_LEN + 1):
            j = t + k
            if j >= n or not ok[j]:
                break
            if abs(r[j] / p - 1) <= TOL:
                k_back = k
                break
        if k_back:
            events.append((t, k_back, p))
            p = r[t + k_back]
            t += k_back + 1
        else:
            p = r[t]
            t += 1
    return events


def _sessions(d, cal):
    """Positions (in d) of the rows that are sessions, in date order."""
    return np.flatnonzero(d["date"].isin(cal).to_numpy())


def clean(d, cal):
    """Return (cleaned frame, exempt mask, events).

    `d` is the frame build_panel hands canonical_price: PRICE_COLS, dropna, sorted
    by date. The returned frame is a copy with adj_close = close * p on every
    session of every event; nothing else changes. `exempt` is a boolean array
    over d's rows, True on exactly those sessions, for canonical_price to skip its
    [low, high] fallback on (spec rule 6). `events` is [(date, length, p)].
    """
    pos = _sessions(d, cal)
    a = d["adj_close"].to_numpy(dtype=float)
    c = d["close"].to_numpy(dtype=float)
    ok = ~fallback_mask(d)
    ev = scan(a[pos] / c[pos], ok[pos])
    out = d.copy()
    exempt = np.zeros(len(d), dtype=bool)
    if not ev:
        return out, exempt, []
    adj = a.copy()
    dates = d["date"].to_numpy()
    events = []
    for s, k, p in ev:
        rows = pos[s:s + k]
        adj[rows] = c[rows] * p
        exempt[rows] = True
        events.append((pd.Timestamp(dates[rows[0]]), k, p))
    out["adj_close"] = adj
    return out, exempt, events


def remaining_events(canon, raw_close, raw_fallback, cal):
    """Reverting events left in a canonical frame, as [(date, length)].

    Re-runs the scan on the ratio the engine actually uses, canonical close over
    the raw close, so it checks the whole load path and not only clean().
    """
    pos = _sessions(canon, cal)
    r = canon["close"].to_numpy(dtype=float)[pos] / np.asarray(raw_close, dtype=float)[pos]
    ok = ~np.asarray(raw_fallback, dtype=bool)[pos]
    dates = canon["date"].to_numpy()
    return [(pd.Timestamp(dates[pos[s]]), k) for s, k, _ in scan(r, ok)]
