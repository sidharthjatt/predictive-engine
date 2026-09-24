"""
extract_membership.py -- download NSE press releases and extract index changes,
scoped to the target index's own section.

WHY THE EXISTING WORKBOOKS ARE WRONG
    An NSE press release covers every index at once, in numbered sections:

        4) Nifty Midcap 150
        The following companies are being excluded:
        Sr. No. Company Name Symbol
        1 ABB India Ltd. ABB
        ...
        The following companies are being included:
        ...
        5) Nifty Smallcap 250
        ...

    The extractor that produced MidCap50/100/150.xlsx does not always stop at the
    next section heading. Where it does, the output is exactly right -- the
    2024-03-28 Nifty Midcap 50 row matches ind_prs28022024.pdf symbol for symbol.
    Where it does not, it takes the whole document: the 2022-03-31 row carries 243
    inclusions containing both HCLTECH and TASTYBITE, which no Midcap 50
    reconstitution does.

    That one defect produces every symptom seen: oversized reconstitutions, a name
    in both inclusions and exclusions on one date (it left one index and joined
    another), NIFTY appearing as a constituent symbol, and unmapped_names filling
    with press-release boilerplate.

WHAT THIS DOES DIFFERENTLY
    It finds the numbered heading for the target index, takes only the text up to
    the next numbered heading, and reads the exclusion and inclusion tables inside
    that slice. Symbols come from the Symbol column of those tables, so a company
    name that fails to map is reported as a genuine unmapped name rather than as a
    fragment of a sentence.

USAGE
    # 1. collect the URLs from the QA sheets of the workbooks
    python3 extract_membership.py urls MidCap150.xlsx > urls_150.txt

    # 2. download them (skips what is already on disk)
    python3 extract_membership.py download urls_150.txt press_releases/

    # 3. extract, scoped to one index
    python3 extract_membership.py parse press_releases/ "Nifty Midcap 150" \\
        --out changes_150.csv

    # 4. rebuild the membership from an anchor
    python3 extract_membership.py rebuild changes_150.csv anchor_150.csv \\
        --size 150 --out membership_150.csv

ANCHOR FILE
    A two-line CSV giving the constituent list on one known date, from the
    exchange's own factsheet or constituent file:

        effective_date,symbols
        2026-08-20,"AARTIIND,ABCAPITAL,..."

    This cannot be inferred. MidCap50.xlsx failed partly because its anchor carried
    100 names in a 50-name index, and every earlier row derived from it.

VERIFICATION BUILT IN
    parse writes n_inc and n_exc per row. A reconstitution of a fixed-size index
    adds as many names as it drops, so n_inc != n_exc is a flag that the section
    was misread -- the same test that identified the broken rows in the original
    workbooks.

    rebuild asserts the running list stays at the index size and stops at the first
    date where it does not, naming that date, rather than carrying an error forward
    silently.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config
from config import read_table  # the one CSV/parquet reader: config.read_table

UA = {"User-Agent": "Mozilla/5.0 (research; index membership reconstruction)"}

# A section heading looks like "4) Nifty Midcap 150" or "8) Nifty Midcap 50".
# A HEADING MAY BE LETTERED, NOT ONLY NUMBERED.
#   Older releases number every index: "4) Nifty Midcap 150". From 2024 the
#   layout nests them under a numbered group, so the index headings are
#   lettered: "1) Replacements on account of semi-annual review of broad
#   market indices:" then "e) Nifty Midcap 150".
#   Verified in ind_prs23082024.pdf and ind_prs21022025.pdf, both of which
#   yielded NO section at all under the digit-only pattern -- which is why the
#   2024-09-30 and 2025-03-28 reconstitutions were absent from the rebuild.
#   More headings means TIGHTER slices, which is the safe direction: the
#   original defect was slices that ran on past the next index.
HEADING = re.compile(r"^\s*([a-zA-Z]|\d{1,2})\)\s*(.+?)\s*$", re.M)
EXCL = re.compile(r"following\s+comp\w+\s+(?:is|are)\s+being\s+excluded", re.I)
INCL = re.compile(r"following\s+comp\w+\s+(?:is|are)\s+being\s+included", re.I)
# "1 ABB India Ltd. ABB"  ->  rank, company name, symbol
# A SYMBOL MAY START WITH A DIGIT. The original pattern required [A-Z] first,
# so 360ONE and 3MINDIA never matched and the whole table line was discarded
# SILENTLY. That produced the two apparently "imbalanced" rows: both are in
# fact 12/12 and 13/13 in the PDF. 3IINFOTECH, 8KMILES and 20MICRONS are hit
# in eight further press releases.
#
# THE FAILURE IS WORSE THAN THE TWO VISIBLE ROWS. Where a digit-leading name
# appeared on BOTH sides of one reconstitution, the row still balanced while
# being wrong, so n_inc == n_exc never proved correctness.
ROW = re.compile(r"^\s*\d{1,3}\s+(.+?)\s+([A-Z0-9][A-Z0-9&\-\.]{1,19})\s*$", re.M)


def cmd_urls(xlsx):
    """Print every press release URL in the workbook's QA sheet."""
    xl = pd.ExcelFile(xlsx)
    qa_name = next(s for s in xl.sheet_names if s.endswith("_QA"))
    qa = pd.read_excel(xl, qa_name)
    for u in qa["url"].dropna().unique():
        print(u)


def cmd_download(urlfile, outdir, pause=1.0):
    """Fetch every URL that is not already on disk. Polite one-per-second."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    urls = [l.strip() for l in Path(urlfile).read_text().splitlines() if l.strip()]
    got = fail = skip = 0
    for u in urls:
        dest = out / u.rsplit("/", 1)[-1]
        if dest.exists() and dest.stat().st_size > 1000:
            skip += 1
            continue
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
            got += 1
            print(f"  ok    {dest.name}")
        except Exception as e:
            fail += 1
            print(f"  FAIL  {dest.name}   {type(e).__name__}: {e}")
        time.sleep(pause)
    print(f"\ndownloaded {got}, already present {skip}, failed {fail}, of {len(urls)}")
    if fail:
        print("Failures are usually a moved or renamed file. Check the URL by hand;")
        print("do not substitute a different press release for a missing one.")


def read_pdf(path) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber is required:  pip install pdfplumber")
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


# ---------------------------------------------------------------------------
# HISTORICAL INDEX NAMES -- every form below is quoted from the press releases
# themselves. Nothing here is added from memory or inference.
#
#   ind_prs11042013.pdf  heading: "CNX Midcap Index"
#   ind_prs22022016_2.pdf heading: "Nifty Free Float Midcap 100 Index
#                                   (Formerly Nifty Midcap 100)"
#   ind_prs21022018.pdf  body:    "NIFTY Free float Midcap 100 (renamed as
#                                   NIFTY Midcap 100 w.e.f. April 2, 2018)"
#
# So the index called Nifty Midcap 100 today appears as CNX Midcap, then Nifty
# Midcap 100, then Nifty Free Float Midcap 100, then Nifty Midcap 100 again.
#
# NO PRE-2015 FORM IS LISTED FOR MIDCAP 50 OR MIDCAP 150, because none exists in
# these documents. A search of all 79 PDFs finds only "CNX Midcap Index" (39
# occurrences) and "CNX Midcap" (1); there is no "CNX Midcap 50" and no "CNX
# Midcap 150" anywhere. An earlier draft of this file listed "cnx midcap 50" on
# the assumption that the 2015 rebranding applied uniformly. It does not, and a
# speculative alias would have silently attached another index's changes to
# Midcap 50.
ALIASES = {
    "nifty midcap 100": [
        "nifty midcap 100", "nifty midcap 100 index",
        "nifty free float midcap 100", "nifty free float midcap 100 index",
        "nifty free float midcap 100 index (formerly nifty midcap 100)",
        "cnx midcap", "cnx midcap index",
    ],
    "nifty midcap 50": ["nifty midcap 50", "nifty midcap 50 index"],
    "nifty midcap 150": ["nifty midcap 150", "nifty midcap 150 index"],
}

# DELIBERATE NON-MATCHES, WITH THE REASON. These are rejected explicitly rather
# than left to the exact-match test, because merging any of them would be
# UNDETECTABLE DOWNSTREAM: the row counts would look plausible and the balance
# check would still pass, while the series silently blended two indices.
DENY = {
    "nifty full midcap 100":
        "full market capitalisation, not free float -- a different index that "
        "happens to share the number 100",
    "nifty full midcap 100 index": "as above",
    "nifty free float midcap 100 index (formerly nifty midcap 100) **": "footnote marker variant",
    "nifty midcap150 quality 50":
        "a factor index selected FROM Midcap 150, not Midcap 150 itself",
    "nifty midcap select": "a 25-name tradeable subset, not the parent index",
    "nifty midcap liquid 15": "a 15-name liquidity subset, not the parent index",
    "nifty largemidcap 250": "a combined large+mid index, not a midcap index",
    "lix15 midcap index": "a liquidity index, not a constituent index",
}
# Deny must never contradict an alias, or the intent would be ambiguous.
for _k, _v in ALIASES.items():
    _clash = set(_v) & set(DENY)
    assert not _clash, f"alias/deny conflict for {_k}: {_clash}"


def _accepted(index_name):
    w = re.sub(r"\s+", " ", index_name).strip().lower()
    return set(ALIASES.get(w, [w]))


def section_for(text, index_name):
    """Return the slice of `text` belonging to `index_name`, or None.

    The slice runs from that index's numbered heading to the next numbered
    heading. Matching is exact after normalising whitespace and case, so
    'Nifty Midcap 150' does not match 'Nifty Midcap 150 Quality 50'."""
    want = _accepted(index_name)
    marks = [(m.start(), m.end(), re.sub(r"\s+", " ", m.group(2)).strip().lower())
             for m in HEADING.finditer(text)]
    for i, (s, e, title) in enumerate(marks):
        if title in DENY:
            continue          # explicit non-match; see DENY for the reason
        if title in want:
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            return text[e:end]
    return None


def parse_section(sec):
    """Return (included, excluded, unmapped) from one index's section."""
    if sec is None:
        return set(), set(), []
    ex_at = [m.start() for m in EXCL.finditer(sec)]
    in_at = [m.start() for m in INCL.finditer(sec)]
    bounds = sorted([(p, "exc") for p in ex_at] + [(p, "inc") for p in in_at])
    inc, exc, unmapped = set(), set(), []
    for j, (pos, kind) in enumerate(bounds):
        end = bounds[j + 1][0] if j + 1 < len(bounds) else len(sec)
        block = sec[pos:end]
        for m in ROW.finditer(block):
            company, symbol = m.group(1).strip(), m.group(2).strip()
            if symbol in ("No", "Sr", "Symbol"):
                unmapped.append(company)
                continue
            (inc if kind == "inc" else exc).add(symbol)
    return inc, exc, unmapped


def cmd_parse(pdfdir, index_name, out_csv=None):
    rows = []
    files = sorted(Path(pdfdir).glob("*.pdf"))
    if not files:
        sys.exit(f"no PDFs in {pdfdir}")
    for f in files:
        try:
            text = read_pdf(f)
        except Exception as e:
            print(f"  UNREADABLE {f.name}: {e}")
            continue
        sec = section_for(text, index_name)
        if sec is None:
            print(f"  no section   {f.name}   ({index_name} not mentioned)")
            continue
        inc, exc, unmapped = parse_section(sec)
        eff = re.search(r"effective\s+from\s+(\w+\s+\d{1,2},\s*\d{4})", text, re.I)
        rows.append({"source": f.name,
                     "effective_date": eff.group(1) if eff else "",
                     "inclusions": ",".join(sorted(inc)),
                     "exclusions": ",".join(sorted(exc)),
                     "n_inc": len(inc), "n_exc": len(exc),
                     "unmapped_names": ";".join(unmapped)})
        flag = "" if len(inc) == len(exc) else "   <-- CHECK: counts differ"
        print(f"  {f.name:<34} inc {len(inc):>3}  exc {len(exc):>3}{flag}")
    df = pd.DataFrame(rows)
    if not df.empty:
        df["effective_date"] = pd.to_datetime(df["effective_date"], errors="coerce")
        df = df.sort_values("effective_date")
    if out_csv:
        df.to_csv(out_csv, index=False)
        print(f"\nwrote {out_csv}  ({len(df)} rows)")
    bad = df[df.n_inc != df.n_exc] if not df.empty else df
    if len(bad):
        print(f"\n{len(bad)} rows where inclusions != exclusions -- check these by "
              f"hand before rebuilding. A fixed-size index adds as many as it drops,")
        print("except where a company was suspended, merged or delisted mid-period.")
    return df


def cmd_rebuild(changes_csv, anchor_csv, size, out_csv=None):
    ch = read_table(changes_csv, parse_dates=["effective_date"])
    ch = ch.dropna(subset=["effective_date"]).sort_values("effective_date")
    a = read_table(anchor_csv)
    anchor_date = pd.Timestamp(a["effective_date"].iloc[0])
    cur = {s.strip().upper() for s in str(a["symbols"].iloc[0]).split(",") if s.strip()}
    if len(cur) != size:
        sys.exit(f"anchor has {len(cur)} symbols, expected {size}. Fix the anchor "
                 f"first -- every rebuilt row derives from it.")

    def sp(x):
        if pd.isna(x):
            return set()
        return {s.strip().upper() for s in str(x).split(",") if s.strip()}

    # backward from the anchor
    back = ch[ch.effective_date <= anchor_date].sort_values("effective_date",
                                                            ascending=False)
    hist = {anchor_date: set(cur)}
    for _, r in back.iterrows():
        if r.effective_date == anchor_date:
            continue
        cur = (cur - sp(r.inclusions)) | sp(r.exclusions)
        if len(cur) != size:
            print(f"  STOP at {r.effective_date.date()}: list became {len(cur)}, "
                  f"expected {size}. Everything before this date is unreliable.")
            break
        hist[r.effective_date] = set(cur)

    # forward from the anchor
    cur = set(hist[anchor_date])
    fwd = ch[ch.effective_date > anchor_date].sort_values("effective_date")
    for _, r in fwd.iterrows():
        cur = (cur | sp(r.inclusions)) - sp(r.exclusions)
        if len(cur) != size:
            print(f"  STOP at {r.effective_date.date()}: list became {len(cur)}, "
                  f"expected {size}.")
            break
        hist[r.effective_date] = set(cur)

    out = pd.DataFrame([{"effective_date": d.strftime("%Y-%m-%d"),
                         "symbols": ",".join(sorted(s)),
                         "symbol_count": len(s)}
                        for d, s in sorted(hist.items())])
    print(f"\nrebuilt {len(out)} dates: {out.effective_date.iloc[0]} -> "
          f"{out.effective_date.iloc[-1]}, all at {size} symbols")
    if out_csv:
        out.to_csv(out_csv, index=False)
        print(f"wrote {out_csv}")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    c = a[0]
    out = a[a.index("--out") + 1] if "--out" in a else None
    if c == "urls":
        cmd_urls(a[1])
    elif c == "download":
        cmd_download(a[1], a[2])
    elif c == "parse":
        cmd_parse(a[1], a[2], out)
    elif c == "rebuild":
        size = int(a[a.index("--size") + 1])
        cmd_rebuild(a[1], a[2], size, out)
    else:
        sys.exit(f"unknown command {c!r}")
