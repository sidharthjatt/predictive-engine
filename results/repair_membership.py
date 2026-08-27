"""
repair_membership.py -- triage and repair NSE index membership workbooks.

WHAT IS WRONG WITH THE SOURCE FILES
    An NSE press release covers every index at once, in numbered sections -- the
    Nifty Midcap 50 changes sit under a heading like "8) Nifty Midcap 50", after
    sections for Nifty 50, Nifty 500, Nifty Midcap 150 and twenty others.

    The extractor that produced these workbooks does not always scope to the
    target index's section. Where it does, the output is exactly right: the
    2024-03-28 Nifty Midcap 50 row matches press release ind_prs28022024.pdf
    symbol for symbol on both inclusions and exclusions. Where it does not, it
    takes the whole PDF: the 2022-03-31 row carries 243 inclusions containing both
    HCLTECH, COALINDIA and TATAPOWER, and SNOWMAN, TASTYBITE and BODALCHEM. No
    Midcap 50 reconstitution contains both -- those are Nifty 500 and Microcap 250
    names.

    That single defect produces four visible symptoms:
      - reconstitutions with far more inclusions than the index has members
      - a name in both `inclusions` and `exclusions` on one date, because it left
        one index and joined another the same day
      - `NIFTY` appearing as a constituent symbol, lifted from a heading
      - `unmapped_names` filling with PDF boilerplate rather than company names

WHAT THIS TOOL DOES
    It does not invent data. It separates what is trustworthy from what is not,
    repairs what can be repaired arithmetically, and produces an exact list of the
    rows that still need a human to read the press release.

    1. TRIAGE. A row is trusted when its symbol list has exactly the index's size.
       An index of 50 has 50 members on every date; a row with 243 does not.

    2. REBUILD. Between two trusted rows, walk forward applying
       symbols[t] = symbols[t-1] + inclusions[t] - exclusions[t].
       If the walk lands exactly on the next trusted row, every intermediate row
       is recovered and marked REBUILT. If it does not, the gap is left alone and
       marked NEEDS_EXTRACTION -- a rebuild that does not reconcile is a guess.

    3. REPORT. Per row: TRUSTED, REBUILT, or NEEDS_EXTRACTION with the reason.
       The NEEDS_EXTRACTION rows are the work list, with their press release URLs.

    4. EMIT. A CSV in the format survivorship.py expects, carrying only rows that
       are TRUSTED or REBUILT. Rows that could not be repaired are omitted rather
       than passed through wrong, and the omission is recorded in the report.

WHAT IT DELIBERATELY DOES NOT DO
    It does not repair a row by selecting a plausible subset of an oversized
    inclusion list. The correct subset is decided by NSE's ranking rules, and
    choosing one that happens to make the arithmetic work would produce a
    membership history that looks right and is fabricated.

    It does not supply a missing anchor. If a file's newest row has the wrong
    number of members -- as MidCap50's does, carrying 100 in a 50-name index --
    that anchor has to come from the exchange, not from inference.

Run:
    python3 repair_membership.py <workbook.xlsx> [--size N] [--out repaired.csv]
    python3 repair_membership.py --all      # all three MidCap workbooks
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Expected constituent count per index. NSE publishes these; they are not guesses.
INDEX_SIZE = {
    "niftymidcap50": 50,
    "niftymidcap100": 100,
    "niftymidcap150": 150,
    "nifty50": 50,
    "nifty100": 100,
    "nifty500": 500,
}


def split_symbols(cell) -> set:
    if pd.isna(cell):
        return set()
    return {s.strip().upper() for s in str(cell).split(",")
            if s.strip() and s.strip().lower() != "nan"}


def load(path):
    """Return (main_df, qa_df, index_key, declared_size)."""
    xl = pd.ExcelFile(path)
    main_name = next(s for s in xl.sheet_names
                     if s != "about" and not s.endswith("_QA"))
    qa_name = next((s for s in xl.sheet_names if s.endswith("_QA")), None)

    declared = None
    if "about" in xl.sheet_names:
        ab = pd.read_excel(xl, "about", header=None)
        for _, row in ab.iterrows():
            vals = [str(v) for v in row if pd.notna(v)]
            if "size" in vals:
                pass
        try:
            hdr = ab.iloc[5].tolist()
            val = ab.iloc[6].tolist()
            declared = int(dict(zip(hdr, val))["size"])
        except Exception:
            declared = None

    d = pd.read_excel(xl, main_name)
    d["effective_date"] = pd.to_datetime(d["effective_date"])
    d = d.sort_values("effective_date").reset_index(drop=True)  # oldest first
    qa = pd.read_excel(xl, qa_name) if qa_name else None
    return d, qa, main_name, declared


def triage(d, size):
    """Classify every row and rebuild what reconciles.

    Returns a list of dicts, one per row, in ascending date order."""
    L = [split_symbols(s) for s in d["symbols"]]
    I = [split_symbols(s) for s in d.get("inclusions", pd.Series([None] * len(d)))]
    E = [split_symbols(s) for s in d.get("exclusions", pd.Series([None] * len(d)))]

    rows = [{"i": i,
             "date": d["effective_date"][i],
             "n": len(L[i]),
             "n_inc": len(I[i]),
             "n_exc": len(E[i]),
             "symbols": set(L[i]),
             "status": None,
             "reason": ""} for i in range(len(d))]

    trusted = [i for i in range(len(d)) if len(L[i]) == size]
    for i in trusted:
        rows[i]["status"] = "TRUSTED"
        rows[i]["reason"] = f"symbol count is exactly {size}"

    # walk each gap between consecutive trusted rows
    for a, b in zip(trusted, trusted[1:]):
        if b - a == 1:
            continue
        cur = set(L[a])
        ok = True
        walked = []
        for k in range(a + 1, b + 1):
            if I[k] & E[k]:
                ok = False
                reason = (f"{len(I[k] & E[k])} names appear in both inclusions and "
                          f"exclusions ({', '.join(sorted(I[k] & E[k])[:4])}) -- the "
                          f"extractor merged sections for different indices")
                break
            if len(I[k]) > size:
                ok = False
                reason = (f"{len(I[k])} inclusions in an index of {size} -- the "
                          f"extractor took the whole press release, not this "
                          f"index's section")
                break
            cur = (cur | I[k]) - E[k]
            walked.append((k, set(cur)))
        else:
            if cur == L[b]:
                for k, snap in walked[:-1]:
                    rows[k]["status"] = "REBUILT"
                    rows[k]["symbols"] = snap
                    rows[k]["n"] = len(snap)
                    rows[k]["reason"] = (f"rebuilt from {rows[a]['date'].date()}; "
                                         f"chain reconciles to "
                                         f"{rows[b]['date'].date()}")
                continue
            ok = False
            reason = (f"chain from {rows[a]['date'].date()} does not reconcile to "
                      f"{rows[b]['date'].date()}: {len(cur ^ L[b])} symbols differ")
        for k in range(a + 1, b):
            if rows[k]["status"] is None:
                rows[k]["status"] = "NEEDS_EXTRACTION"
                rows[k]["reason"] = reason

    for r in rows:
        if r["status"] is None:
            if r["n_inc"] > size:
                r["reason"] = (f"{r['n_inc']} inclusions in an index of {size} -- "
                               f"whole press release taken")
            elif r["n"] != size:
                r["reason"] = f"symbol count {r['n']}, expected {size}"
            else:
                r["reason"] = "outside any reconcilable trusted span"
            r["status"] = "NEEDS_EXTRACTION"
    return rows


def report(path, size_override=None, out_csv=None):
    d, qa, key, declared = load(path)
    size = size_override or INDEX_SIZE.get(key) or declared
    name = Path(path).name

    print("=" * 78)
    print(f" {name}   index={key}   expected size={size}")
    print("=" * 78)

    dupes = d["effective_date"].value_counts()
    dupes = dupes[dupes > 1]
    if len(dupes):
        print("\n  DUPLICATE effective_date rows -- resolve before anything else:")
        for dt, n in dupes.items():
            print(f"    {dt.date()}  appears {n} times")

    newest = d.iloc[-1]
    n_new = len(split_symbols(newest["symbols"]))
    if n_new != size:
        print(f"\n  ANCHOR IS WRONG: newest row {newest['effective_date'].date()} "
              f"carries {n_new} symbols in an index of {size}.")
        print(f"  Every row derives from the anchor, so this must be replaced with "
              f"the exchange's own constituent list before any repair is final.")

    rows = triage(d, size)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(f"\n  TRIAGE of {len(rows)} rows")
    for k in ("TRUSTED", "REBUILT", "NEEDS_EXTRACTION"):
        print(f"    {k:<18}{counts.get(k, 0):>4}")

    need = [r for r in rows if r["status"] == "NEEDS_EXTRACTION"]
    if need:
        print(f"\n  WORK LIST -- {len(need)} rows need the press release re-read")
        url = {}
        if qa is not None and "effective_date" in qa.columns:
            q = qa.copy()
            q["effective_date"] = pd.to_datetime(q["effective_date"], errors="coerce")
            url = dict(zip(q["effective_date"], q["url"]))
        for r in need:
            u = url.get(r["date"], "")
            print(f"    {r['date'].date()}  inc={r['n_inc']:<4} exc={r['n_exc']:<3} "
                  f"symbols={r['n']:<4} {r['reason'][:72]}")
            if u:
                print(f"                {u}")

    if qa is not None:
        nod = qa[qa["effective_date"].isna()] if "effective_date" in qa.columns else []
        if len(nod):
            print(f"\n  PRESS RELEASES THAT DID NOT PARSE AT ALL -- {len(nod)}")
            for _, r in nod.iterrows():
                print(f"    {str(r['announcement_date'])[:10]}  {r['url']}")

    keep = [r for r in rows if r["status"] in ("TRUSTED", "REBUILT")]
    print(f"\n  USABLE HISTORY: {len(keep)} of {len(rows)} rows")
    if keep:
        print(f"    {keep[0]['date'].date()} -> {keep[-1]['date'].date()}")
        spans = []
        run = [keep[0]]
        for a, b in zip(keep, keep[1:]):
            if b["i"] == a["i"] + 1:
                run.append(b)
            else:
                spans.append(run)
                run = [b]
        spans.append(run)
        print(f"    contiguous spans: {len(spans)}")
        for s in spans:
            print(f"      {s[0]['date'].date()} -> {s[-1]['date'].date()}  "
                  f"({len(s)} rows)")

    if out_csv and keep:
        rec = []
        for j, r in enumerate(keep):
            prev = keep[j - 1]["symbols"] if j else set()
            inc = r["symbols"] - prev if j else set()
            exc = prev - r["symbols"] if j else set()
            rec.append({"effective_date": r["date"].strftime("%Y-%m-%d"),
                        "symbols": ",".join(sorted(r["symbols"])),
                        "inclusions": ",".join(sorted(inc)),
                        "exclusions": ",".join(sorted(exc)),
                        "provenance": r["status"]})
        pd.DataFrame(rec).to_csv(out_csv, index=False)
        print(f"\n  wrote {out_csv}  ({len(rec)} rows)")
        print("    NOTE: inclusions/exclusions are DERIVED from consecutive kept")
        print("    rows, so across a gap they describe the net change over the gap,")
        print("    not one reconstitution. The provenance column records which.")
    print()
    return rows


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--all":
        base = Path("/mnt/user-data/uploads")
        for f, n in [("MidCap50.xlsx", 50), ("MidCap100.xlsx", 100),
                     ("Midcap150.xlsx", 150)]:
            p = base / f
            if p.exists():
                report(str(p), n, out_csv=f"repaired_{p.stem.lower()}.csv")
    else:
        size = int(args[args.index("--size") + 1]) if "--size" in args else None
        out = args[args.index("--out") + 1] if "--out" in args else None
        report(args[0], size, out)
