"""Group parsed rows by effective date, flag multi-source dates, scan for
postponements, and rebuild MidCap100/150 from their anchors.

Nothing is applied in arbitrary order: a date resolving to more than one source
file is REPORTED, and the ordering used is stated with its reason.
"""
import re, sys
from pathlib import Path
import pandas as pd
import pdfplumber

D = Path(__file__).resolve().parent
PDFS = D.parents[1] / "data" / "raw" / "press_releases"
S = lambda x: set(s.strip().upper() for s in str(x).split(",") if s.strip() and str(x) != "nan")

# The one multi-source date already established, from the documents themselves.
# ind_prs25092024.pdf is a Remarks table the section parser cannot read, and it
# says: "This press release should be read in consonance with the press release
# issued on August 23, 2024."
REVOKE = {150: ({"IDEA"}, {"CENTRALBK"}), 100: ({"IDEA"}, {"CENTRALBK"}),
          50:  ({"IDEA"}, {"SONACOMS"})}
REVOKE_DATE = pd.Timestamp("2024-09-30")


def multi_source(n):
    c = pd.read_csv(D / f"final3_{n}.csv")
    c["d"] = pd.to_datetime(c["effective_date"], errors="coerce")
    g = c.dropna(subset=["d"]).groupby("d")["source"].apply(list)
    return {d: v for d, v in g.items() if len(v) > 1}, c


def postponements():
    """Any document whose postponement language names Midcap 50/100/150."""
    hits = []
    for f in sorted(PDFS.glob("*.pdf")):
        try:
            t = "\n".join((p.extract_text() or "") for p in pdfplumber.open(f).pages)
        except Exception:
            continue
        for m in re.finditer(r"postpon\w*", t, re.I):
            seg = t[max(0, m.start() - 700): m.end() + 900]
            named = sorted(set(re.findall(r"Nifty Midcap (?:50|100|150)\b", seg)))
            hits.append({"file": f.name, "names_ours": named,
                         "snippet": re.sub(r"\s+", " ", seg[:300])})
    return hits


def walk(n):
    a = pd.read_csv(D / f"anchor_{n}.csv")
    cur = S(a.iloc[0]["symbols"]); ad = pd.Timestamp(a.iloc[0]["effective_date"])
    c = pd.read_csv(D / f"final3_{n}.csv"); c["d"] = pd.to_datetime(c["effective_date"], errors="coerce")
    c = c.dropna(subset=["d"]).sort_values("d")
    ch = {}
    for r in c.itertuples():
        inc, exc = S(r.inclusions), S(r.exclusions)
        if r.d in ch:                      # same date, another source: merge
            pi, pe, ps = ch[r.d]
            inc, exc, src = pi | inc, pe | exc, ps + "+" + r.source
        else:
            src = r.source
        if r.d == REVOKE_DATE and n in REVOKE:
            er, ir = REVOKE[n]; inc, exc = inc - ir, exc - er
        ch[r.d] = (inc, exc, src)
    dates = sorted([d for d in ch if d <= ad], reverse=True)
    hist = {ad: set(cur)}; rows = []
    for i, d in enumerate(dates):
        inc, exc, src = ch[d]
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        miss = inc - cur
        cur = (cur - inc) | exc
        lbl = str(nxt.date()) if nxt is not None else "(earliest)"
        rows.append((str(d.date()), lbl, len(cur), sorted(miss), src))
        if len(cur) != n:
            return hist, rows, (str(d.date()), len(cur), sorted(miss), src)
        if nxt is not None: hist[nxt] = set(cur)
    return hist, rows, None
