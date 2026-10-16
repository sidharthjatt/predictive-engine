"""stuck_positions.py -- holdings whose price file ends before the window does.

Under the row rule (results/tradability.py) a name is sold only on a session with
a row. A sale owed on a name whose file has ended never fills, so the name is held
to the window's end, valued at its last close (owner's decision, 2026-10-16). That
value is an assumption: the repository does not record why such a file ends.

For every cell that still holds such a name on its last session, this reports the
shares and the value they are held at, and the end equity, CAGR and maximum
drawdown if the position were valued at zero from the first session after its last
row. It is arithmetic on the cell's own daily_holdings and daily_summary files,
with the CAGR and drawdown formulas of engine_core.metrics; nothing is rerun. Tax
already charged is left as it is: the zero valuation changes no realised gain.

run.py prints these lines in the run log and writes them to RUN.txt. A cell with no
such holding gets no line, so every other RUN.txt is unchanged.
"""
from pathlib import Path

from config import read_table  # the one CSV/parquet reader: config.read_table


def last_rows(u):
    """{symbol: its last session with a row} for universe `u`."""
    import engine_core
    import tradability
    rows = tradability.sessions_with_row(u.prepare_data_dir(), engine_core._load_calendar())
    return {s: max(d) for s, d in rows.items() if d}


def _cagr(e):
    ny = (e.index[-1] - e.index[0]).days / 365.25
    return ((e.iloc[-1] / e.iloc[0]) ** (1 / ny) - 1) * 100


def _maxdd(e):
    return float(((e - e.cummax()) / e.cummax()).min() * 100)


def cell_lines(u, tag, last=None):
    """RUN.txt lines for one cell, named by its artefact tag; [] when nothing is stuck."""
    M = Path(u.metrics_dir)
    hf, sf = M / f"daily_holdings_{tag}.csv", M / f"daily_summary_{tag}.csv"
    if not hf.exists() or not sf.exists():
        return []
    h = read_table(hf, parse_dates=["date"])
    eq = read_table(sf, parse_dates=["date"]).set_index("date")["total"]
    end = eq.index[-1]
    last = last_rows(u) if last is None else last
    stuck = [r for r in h[h["date"] == end].itertuples()
             if r.symbol in last and last[r.symbol] < end]
    if not stuck:
        return []
    at_zero = eq.copy()
    out = []
    for r in stuck:
        lr = last[r.symbol]
        after = h[(h["symbol"] == r.symbol) & (h["date"] > lr)].set_index("date")["value"]
        at_zero = at_zero.sub(after.reindex(at_zero.index).fillna(0.0))
        out.append(f"stuck     : {tag} -- {r.symbol}: {int(r.qty):,} shares with no row "
                   f"after {lr.date()}, held at its last close {float(r.price):,.2f} = "
                   f"Rs {float(r.value):,.2f} on {end.date()}")
    out.append(f"at zero   : {tag} -- valued at zero from the session after its last row: "
               f"end equity Rs {at_zero.iloc[-1]:,.2f} (as run Rs {eq.iloc[-1]:,.2f}), "
               f"CAGR {_cagr(at_zero):.2f}% (as run {_cagr(eq):.2f}%), "
               f"MaxDD {_maxdd(at_zero):.2f}% (as run {_maxdd(eq):.2f}%)")
    return out


def run_lines(universes, arms):
    """The lines for every (universe, arm) cell of one run.py invocation."""
    import audit_step
    import survivorship_axis as _sva
    from universes import registry as R
    out = []
    for u in universes:
        if not _sva.is_default() and R.has_pit(u) and not u.is_pit:
            u = R.pit_variant(u)
        last = None
        for a in arms:
            if last is None:
                last = last_rows(u)
            out += cell_lines(u, audit_step.artefact_tag(u, a), last)
    return out
