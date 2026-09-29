"""survivorship_attribution.py -- how much of a run's profit came from names that were
not index members on the day they were held. Read-only; an estimate, not a backtest.

    ./venv/bin/python survivorship_attribution.py [--run=runs/<folder>] [cells...]

    cells are <universe>:<arm>; the default is the 15 cells supported by
    experiments/CLEANED_NOISE_PREREG.txt. The default run folder is the research
    tax-on run of 2026-09-27 on the cleaned prices, the sigma-0 run of that test.

Writes diagnostics/survivorship_attribution.txt, survivorship_attribution.csv,
survivorship_membership_coverage.csv and survivorship_pit_feasibility.csv.

WHAT IS CLASSIFIED. Every (symbol, date) the arm or its investable buy & hold held
over the window, using the supplier's membership files in data/raw/Survivorship_Bias:
  (a) member     -- the symbol was in the index on that date
  (b) not member -- it was not
  (c) unknown    -- the membership data cannot say
THE SYMBOLS COLUMN IS NOT USED. It is today's list edited backwards: the 2018 and
2019 rows of the Nifty 50 file list JIOFIN, listed in 2023, and TRENT, BEL, INDIGO
and MAXHEALTH, which joined in 2024 and 2025. Every file fails survivorship.validate.
Only the inclusions and exclusions columns are read, as dated events per symbol, with
one more anchor: every symbol in today's universe (the price folder) is a member at
the end of the window. Between two anchors of a symbol, the earlier says what it was
after (inclusion: member, exclusion: not) and the later says what it was before
(inclusion: not, exclusion or today: member):
  both agree       -> (a) or (b)
  they disagree    -> (c): an event of that symbol is missing from the file
  only a later anchor (before the symbol's first event) -> what it implies, unless a
      scheduled review the file does not record falls between the date and that
      anchor, in which case (c): the missing review may have added the symbol
  before the file's first row -> (c)
A scheduled review is the end-of-March or end-of-September reconstitution; it is
recorded when the file has a row with changes between the 25th of March or September
and the 5th of the next month. One-name replacements on other dates (a merger, a
suspension) are events like any other but do not count as the review. A review with no
change and a review the file omits look the same, so both count as unrecorded. Symbols are compared after the 15 renames validated in
diagnostics/membership/STATUS.md.
The LENIENT reading also reported assumes no event is missing: an unrecorded review is
ignored and a disagreement is read as the earlier anchor. It is a bound, not a result.

WHAT IS ATTRIBUTED. Position-day profit: the day's change in the position's value,
plus sale proceeds, minus purchases and charges, from daily_holdings and daily_trades.
Summed over symbols it reproduces the day's change in total equity except on tax
days; the residual is reported. Tax is allocated to groups within each financial year
in proportion to each group's positive profit on lots SOLD in that year (the realised
gain the tax is levied on), and reported separately.

THE ESTIMATE WITH (b) REMOVED is each equity curve minus its cumulative group (b)
profit net of its allocated tax, and the CAGR of that curve. It assumes the capital
held in (b) names would have earned nothing instead, and that nothing else about the
run changes. A run on point-in-time members would choose different names, size them
differently and pay different tax. This is not that run.
"""
import os
for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[v] = "1"
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "results"):
    sys.path.insert(0, str(p))
import numpy as np
import pandas as pd

import config
from config import read_table
from test_exposure import START_CAPITAL
from universes.registry import REGISTRY, check_tags

RUN = ROOT / "runs" / "20260927T122131_all_all_r20"
MEMBERSHIP = ROOT / "data" / "raw" / "Survivorship_Bias"
MEMBERSHIP_FILE = {
    "nifty50": "Nifty50", "nifty100": "Nifty100", "nifty200": "Nifty200",
    "nifty500": "Nifty500", "midcap50": "Midcap50", "midcap100": "Midcap100",
    "midcap150": "Midcap150", "smallcap250": "SmallCap250",
}
# The 15 renames read against their circulars (diagnostics/membership/STATUS.md).
# The other 176 rows of nse_symbol_renames.csv are unchecked and are not used.
RENAMES = {
    "RNAM": "NAM-INDIA", "TATAGLOBAL": "TATACONSUM", "NIITTECH": "COFORGE",
    "INFRATEL": "INDUSTOWER", "ADANIGAS": "ATGL", "CADILAHC": "ZYDUSLIFE",
    "MOTHERSUMI": "MOTHERSON", "RUCHI": "PATANJALI", "MINDAIND": "UNOMINDA",
    "SRTRANSFIN": "SHRIRAMFIN", "IIFLWAM": "360ONE", "ADANITRANS": "ADANIENSOL",
    "L&TFH": "LTF", "GMRINFRA": "GMRAIRPORT", "TATAMOTORS": "TMPV",
}
SUPPORTED = [
    ("nifty50", "v3"), ("midcap150", "v4"), ("smallcap250", "v1"), ("smallcap250", "v3"),
    ("nifty200", "v1"), ("nifty500", "v1"), ("nifty500", "v2"),
    ("midcap100", "v1"), ("midcap100", "v3"), ("midcap150", "v1"), ("midcap150", "v3"),
    ("nifty200", "v3"), ("nifty200", "v4"), ("nifty500", "v3"), ("nifty500", "v4"),
]
GROUPS = ("a", "b", "c")


def _names(cell):
    if not isinstance(cell, str) or not cell.strip():
        return set()
    return {RENAMES.get(x.strip(), x.strip()) for x in cell.split(",") if x.strip()}


def membership(u):
    """-> (row dates, rows with changes, {symbol: [(date, +1 inclusion | -1 exclusion)]},
    unrecorded scheduled reviews as dates, coherent flag per row)."""
    df = pd.read_csv(MEMBERSHIP / f"{MEMBERSHIP_FILE[u]}_membership.csv", encoding="utf-8-sig")
    df["effective_date"] = pd.to_datetime(df["effective_date"])
    df = df.sort_values("effective_date").reset_index(drop=True)
    snaps = [_names(x) for x in df["symbols"]]
    events, changed = {}, []
    coherent = [True]
    for i, r in df.iterrows():
        inc, exc = _names(r["inclusions"]), _names(r["exclusions"])
        if i:
            coherent.append(snaps[i] == (snaps[i - 1] | inc) - exc)
        if inc or exc:
            changed.append(r["effective_date"])
        for x in inc:
            events.setdefault(x, []).append((r["effective_date"], +1))
        for x in exc:
            events.setdefault(x, []).append((r["effective_date"], -1))
    unrecorded = []
    for y in range(df["effective_date"].min().year, 2027):
        for m in (3, 9):
            lo, hi = pd.Timestamp(y, m, 25), pd.Timestamp(y, m + 1, 5)
            if hi < df["effective_date"].min() or lo > df["effective_date"].max():
                continue
            if not any(lo <= d <= hi for d in changed):
                unrecorded.append(pd.Timestamp(y, m, 28))
    return list(df["effective_date"]), changed, events, unrecorded, coherent


def classifier(u, dates, lenient=False):
    """-> function(symbol) -> np.array of 'a'/'b'/'c' over `dates`."""
    eff, _changed, events, unrecorded, _coh = membership(u)
    today = set(REGISTRY[u].symbol_list)
    D = pd.DatetimeIndex(dates)
    first_row = eff[0]
    end = D[-1] + pd.Timedelta(days=1)
    unrec = np.array(sorted(unrecorded), dtype="datetime64[ns]")

    def f(sym):
        out = np.full(len(D), "c", dtype="<U1")
        anchors = sorted(events.get(sym, []))
        # the end-of-window anchor: a member today (in the universe) or not
        anchors.append((end, -1 if sym in today else +1))
        prev = None
        for (d, kind) in anchors:
            lo = first_row if prev is None else prev[0]
            mask = (D >= lo) & (D < d)
            before = "a" if kind == -1 else "b"      # what the later anchor implies
            if prev is None:
                if lenient:
                    out[mask] = before
                else:
                    # a scheduled review the file does not record, between the date and
                    # this anchor, may have changed the symbol unrecorded
                    for j in np.where(mask)[0]:
                        t = D[j].to_datetime64()
                        out[j] = "c" if ((unrec > t) & (unrec < np.datetime64(d))).any() else before
            else:
                after = "a" if prev[1] == +1 else "b"
                out[mask] = after if (after == before or lenient) else "c"
            prev = (d, kind)
        out[D < first_row] = "c"
        return out
    return f


def cagr(eq):
    y = (eq.index[-1] - eq.index[0]).days / 365.25
    return ((eq.iloc[-1] / eq.iloc[0]) ** (1 / y) - 1) * 100


def arm_pnl(u, arm, run):
    """Position-day profit of the arm from the run's audit trail.

    -> (pnl frame date x symbol, total equity series, tax paid per date, lots)."""
    tag = f"{u}_tax" if arm == "v2" else f"{u}_{arm}_tax"
    m = run / f"results_{u}" / "metrics"
    h = read_table(m / f"daily_holdings_{tag}.csv", parse_dates=["date"])
    t = read_table(m / f"daily_trades_{tag}.csv", parse_dates=["date"])
    s = read_table(m / f"daily_summary_{tag}.csv", parse_dates=["date"]).set_index("date")
    lots = read_table(m / f"HOLDING_PERIOD_LOTS_{tag}.csv", parse_dates=["buy_date", "sell_date"])
    dates = s.index
    val = h.pivot_table(index="date", columns="symbol", values="value", aggfunc="sum") \
           .reindex(dates).fillna(0.0)
    t["flow"] = np.where(t["action"] == "SELL", t["value"], -t["value"]) - t["tc"]
    flow = t.pivot_table(index="date", columns="symbol", values="flow", aggfunc="sum") \
            .reindex(index=dates, columns=val.columns.union(t["symbol"].unique())).fillna(0.0)
    val = val.reindex(columns=flow.columns).fillna(0.0)
    pnl = val.diff().fillna(val) + flow
    resid = s["total"].diff().fillna(s["total"].iloc[0] - START_CAPITAL) - pnl.sum(axis=1)
    return pnl, s["total"], resid, lots


def bh_pnl(u):
    """Position-day profit of the investable buy & hold, rebuilt with bh_held.held_lots
    on the same score panel the run read. -> (pnl frame, headline equity)."""
    import bh_held
    urow = REGISTRY[u]
    p = read_table(config.require_cache(urow.score_cache, what=u), parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    bd = px.index[(px.index >= config.BT_START_DATE) & (px.index <= config.BT_END_DATE)]
    r = bh_held.held_lots(px, op, bd)
    sh = r["shares"]
    syms = list(sh)
    q = pd.Series({s: sh[s][0] for s in syms}, dtype=float)
    v = px.loc[bd, syms].ffill() * q
    pnl = v.diff()
    from test_exposure import calc_tc
    first = pd.Series({s: v.iloc[0][s] - sh[s][0] * sh[s][1] - calc_tc(sh[s][1], sh[s][0], "BUY")
                       for s in syms})
    pnl.iloc[0] = first
    return pnl, r["eq_headline"]


def split(pnl, cls_of):
    """-> {group: profit}, and a frame of group per (date, symbol)."""
    g = pd.DataFrame({s: cls_of(s) for s in pnl.columns}, index=pnl.index)
    out = {k: float(pnl.where(g == k).sum().sum()) for k in GROUPS}
    return out, g


def tax_by_group(lots, groups, resid):
    """Allocate each FY's tax (the negative residual on tax days) to groups by each
    group's positive realised gain on lots sold that FY. A lot's gain is assigned to
    groups in proportion to the number of its held days in each group."""
    tax = (-resid.clip(upper=0))
    tax = tax[tax > 0.5]
    alloc = dict.fromkeys(GROUPS, 0.0)
    daily = pd.Series(0.0, index=resid.index)
    per_group_daily = {k: pd.Series(0.0, index=resid.index) for k in GROUPS}
    if tax.empty:
        return alloc, per_group_daily
    lots = lots.copy()
    lots["fy"] = lots["fy"].astype(int)
    gains = {}
    for _, L in lots.iterrows():
        if L["symbol"] not in groups.columns:
            continue
        span = groups.loc[(groups.index >= L["buy_date"]) & (groups.index <= L["sell_date"]),
                          L["symbol"]]
        if span.empty:
            continue
        w = span.value_counts(normalize=True)
        for k, share in w.items():
            gains.setdefault(L["fy"], dict.fromkeys(GROUPS, 0.0))[k] += L["gain"] * share
    for d, amount in tax.items():
        fy = d.year if d.month >= 4 else d.year - 1
        # A tax deducted on 1 April or later settles the year that just closed.
        if d.month == 4 and d.day <= 5:
            fy -= 1
        g = gains.get(fy) or gains.get(fy - 1) or {}
        pos = {k: max(v, 0.0) for k, v in g.items()}
        tot = sum(pos.values())
        for k in GROUPS:
            share = pos.get(k, 0.0) / tot if tot > 0 else (1.0 if k == "a" else 0.0)
            alloc[k] += amount * share
            per_group_daily[k].loc[d] += amount * share
    return alloc, per_group_daily


def coverage(u, dates):
    """Per half-year of the window: is the scheduled review recorded, and how many rows."""
    eff, changed, _events, unrecorded, coh = membership(u)
    rows = []
    for y in sorted({d.year for d in dates}):
        for m, h in ((3, "Mar"), (9, "Sep")):
            rev = pd.Timestamp(y, m, 28)
            if rev > dates[-1] + pd.Timedelta(days=5) or rev < dates[0] - pd.Timedelta(days=200):
                continue
            rows.append(dict(universe=u, review=f"{y}-{h}", recorded=rev not in unrecorded))
    return rows


_PRICE_FILES = None


def _price_files():
    """{symbol: [csv paths]} over every supplier price folder under data/raw."""
    global _PRICE_FILES
    if _PRICE_FILES is None:
        _PRICE_FILES = {}
        for top in ("Final_Without_Survivorship_Data", "Final_With_Survivorship_Data"):
            for f in (ROOT / "data" / "raw" / top).glob("*/*.csv"):
                _PRICE_FILES.setdefault(RENAMES.get(f.stem, f.stem), []).append(f)
    return _PRICE_FILES


def _has_rows_in(f, lo, hi):
    d = pd.to_datetime(pd.read_csv(f, usecols=[0]).iloc[:, 0], errors="coerce", dayfirst=True)
    return bool(((d >= lo) & (d <= hi)).any())


def pit_possible(u, dates):
    """Could a run restricted to point-in-time members be built from this data?"""
    eff, changed, events, unrecorded, coh = membership(u)
    lo, hi = dates[0], dates[-1]
    now = set(REGISTRY[u].symbol_list)
    left = sorted(s for s, ev in events.items()
                  if any(lo <= d <= hi for d, _k in ev) and s not in now)
    files = _price_files()
    priced, unpriced = [], []
    for s in left:
        ok = any(_has_rows_in(f, lo, hi) for f in files.get(s, ()))
        (priced if ok else unpriced).append(s)
    unrec = [d for d in unrecorded if lo - pd.Timedelta(days=200) <= d <= hi]
    return dict(universe=u, changed_in_window_not_in_universe=len(left),
                of_them_priced=len(priced), of_them_no_price=len(unpriced),
                unrecorded_reviews_in_window=len(unrec),
                unrecorded=",".join(d.strftime("%Y-%m") for d in unrec),
                unpriced_examples=",".join(unpriced[:8]))


def attribute(u, arm, run, lenient, bh_cache):
    pnl, total, resid, lots = arm_pnl(u, arm, run)
    dates = total.index
    cls_of = classifier(u, dates, lenient=lenient)
    arm_g, groups = split(pnl, cls_of)
    tax_g, tax_daily = tax_by_group(lots, groups, resid)
    key = (u, lenient)
    if key not in bh_cache:
        bpnl, beq = bh_pnl(u) if u not in {k[0] for k in bh_cache} else \
            next(v[:2] for k, v in bh_cache.items() if k[0] == u)
        bpnl = bpnl.reindex(dates).fillna(0.0)
        beq = beq.reindex(dates).ffill()
        bh_g, bgroups = split(bpnl, cls_of)
        bh_cache[key] = (bpnl, beq, bh_g, bgroups)
    bpnl, beq, bh_g, bgroups = bh_cache[key]
    start = total.iloc[0] - pnl.iloc[0].sum() - resid.iloc[0]
    arm_profit = total.iloc[-1] - start
    bh_profit = beq.iloc[-1] - (beq.iloc[0] - bpnl.iloc[0].sum())
    # CAGR as the run reports it: first session to last session of the window.
    gap = cagr(total) - cagr(beq)
    arm_b = pnl.where(groups == "b").sum(axis=1).cumsum() - tax_daily["b"].cumsum()
    bh_b = bpnl.where(bgroups == "b").sum(axis=1).cumsum()
    gap_nb = cagr(total - arm_b) - cagr(beq - bh_b)
    net = {k: arm_g[k] - tax_g[k] for k in GROUPS}
    held = pnl != 0
    return dict(universe=u, arm=arm, reading="lenient" if lenient else "strict",
                arm_profit=round(arm_profit, 2), arm_tax=round(sum(tax_g.values()), 2),
                residual_not_tax=round(float(resid[resid.abs() > 0.5].clip(lower=0).sum()), 2),
                **{f"arm_posdays_{k}": int(((groups == k) & held).sum().sum()) for k in GROUPS},
                **{f"arm_share_{k}": round(net[k] / arm_profit * 100, 2) for k in GROUPS},
                **{f"bh_posdays_{k}": int((bgroups == k).sum().sum()) for k in GROUPS},
                **{f"bh_share_{k}": round(bh_g[k] / bh_profit * 100, 2) for k in GROUPS},
                gap=round(gap, 4), gap_b_removed_estimate=round(gap_nb, 4),
                arm_cagr=round(cagr(total), 4), bh_cagr=round(cagr(beq), 4))


def main(argv):
    run = RUN
    cells = []
    for a in argv:
        if a.startswith("--run="):
            run = ROOT / a.split("=", 1)[1]
        else:
            cells.append(tuple(a.split(":")))
    cells = cells or SUPPORTED
    check_tags(sorted({u for u, _ in cells}))
    rows, cov_rows, pit_rows, bh_cache = [], [], {}, {}
    for u, arm in cells:
        for lenient in (False, True):
            rows.append(attribute(u, arm, run, lenient, bh_cache))
        if u not in pit_rows:
            dates = pd.DatetimeIndex(sorted(bh_cache[(u, False)][1].index))
            cov_rows += coverage(u, dates)
            pit_rows[u] = pit_possible(u, dates)
    L = ["SURVIVORSHIP ATTRIBUTION -- ESTIMATE, NOT A BACKTEST", "=" * 84,
         f"run: {run.relative_to(ROOT)} (research profile, tax on, cadence 20, sigma 0)",
         f"membership: {MEMBERSHIP.relative_to(ROOT)}/<Index>_membership.csv (supplier), events only",
         "groups: (a) index member on the day held, (b) not a member, (c) the data cannot say",
         "gap = arm tax-on headline CAGR minus investable buy & hold headline CAGR, points",
         "'gap, (b) removed' subtracts each curve's cumulative (b) profit, net of its allocated",
         "tax, and recomputes both CAGRs. It is an estimate, not a backtest.",
         "strict: (c) where the file cannot say. lenient: assumes no event is missing (a bound).", ""]
    for reading in ("strict", "lenient"):
        L.append(f"Share of profit by group, per cent, {reading} reading "
                 "(arm net of allocated tax; buy & hold pays none)")
        L.append(f"{'cell':<16}{'arm a':>8}{'arm b':>8}{'arm c':>8}  {'b&h a':>8}{'b&h b':>8}{'b&h c':>8}"
                 f"  {'gap':>8}{'gap, (b) removed':>18}")
        for r in (r for r in rows if r["reading"] == reading):
            L.append(f"{r['universe'] + ' ' + r['arm']:<16}{r['arm_share_a']:>8.1f}{r['arm_share_b']:>8.1f}"
                     f"{r['arm_share_c']:>8.1f}  {r['bh_share_a']:>8.1f}{r['bh_share_b']:>8.1f}"
                     f"{r['bh_share_c']:>8.1f}  {r['gap']:>+8.2f}{r['gap_b_removed_estimate']:>+18.2f}")
        L.append("")
    L.append("Held position-days by group, strict reading (arm; buy & hold)")
    for r in (r for r in rows if r["reading"] == "strict"):
        L.append(f"  {r['universe'] + ' ' + r['arm']:<16} arm a {r['arm_posdays_a']:>6} b {r['arm_posdays_b']:>6} "
                 f"c {r['arm_posdays_c']:>6}   b&h a {r['bh_posdays_a']:>7} b {r['bh_posdays_b']:>7} c {r['bh_posdays_c']:>7}")
    L.append("")
    L.append("Accounting check: position-day profit summed over symbols against the day's change")
    L.append("in total equity. The residual is tax on tax days and nothing else if the sum is right.")
    for r in (r for r in rows if r["reading"] == "strict"):
        L.append(f"  {r['universe'] + ' ' + r['arm']:<16} tax allocated Rs {r['arm_tax']:>13,.2f}   "
                 f"positive residual (should be 0) Rs {r['residual_not_tax']:>10,.2f}")
    L.append("")
    L.append("Scheduled reviews in the window the membership file records (a row with changes")
    L.append("between the 25th of March or September and the 5th of the next month); x = not recorded")
    cov = pd.DataFrame(cov_rows)
    for u in cov["universe"].unique():
        c = cov[cov["universe"] == u]
        L.append(f"  {u:<12} " + " ".join(f"{rv}{'' if ok else ' x'}" for rv, ok in zip(c.review, c.recorded)))
    L.append("")
    L.append("Could a run restricted to point-in-time members be built from this data?")
    for u, p in pit_rows.items():
        L.append(f"  {u:<12} unrecorded reviews {p['unrecorded_reviews_in_window']} ({p['unrecorded']}); "
                 f"names changed in the window and not in today's universe {p['changed_in_window_not_in_universe']}, "
                 f"with prices in the window {p['of_them_priced']}, "
                 f"no price file {p['of_them_no_price']}")
        if p["unpriced_examples"]:
            L.append(f"  {'':<12} unpriced, e.g. {p['unpriced_examples']}")
    out = ROOT / "diagnostics"
    pd.DataFrame(rows).to_csv(out / "survivorship_attribution.csv", index=False)
    cov.to_csv(out / "survivorship_membership_coverage.csv", index=False)
    pd.DataFrame(list(pit_rows.values())).to_csv(out / "survivorship_pit_feasibility.csv", index=False)
    (out / "survivorship_attribution.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
