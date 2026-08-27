# NSE Midcap membership reconstruction — status

Last updated: 2026-08-22. Built from the NSE press-release archive and the NSE
listing-circular API. `SURVIVORSHIP_MODE` remains `static`; nothing is wired into
the engine. MidCap50 is out of scope until its anchor is replaced.

---

## THE HONEST HEADLINE — UNCHANGED AFTER THE FULL DOWNLOAD

| | |
|---|---|
| backtest window starts | **2019-01-01** |
| rebuilt coverage | **2024-03-28 → 2026-09-30** |
| shortfall | **5 years 3 months uncovered** |

**Downloading the complete non-bond archive did not extend coverage by a single
day.** 438 further press releases were fetched (667 total on disk, zero failures)
and they produced **exactly the same 43 and 41 parsed rows** as the keyword-filtered
set. The keyword filter was unsafe in principle and was right to remove; removing
it changed nothing in practice.

The symbol rename map DID fix one of the two blockers. The walk no longer breaks on
GMRINFRA. It still breaks on IREDA, one step earlier than the backtest needs.

**This still does not solve the survivorship problem.** 2024 onward is the last 2.5
years of a 7.6-year backtest.

---

## What was built this round

**1. Symbol rename map — `data/reference/nse_symbol_renames.csv`**

NSE issues renames as listing circulars, not index press releases. The circular
listing page is NOT browsable (2 links in served HTML), but the API is:

    https://www.nseindia.com/api/circulars?fromDate=..&toDate=..&mode=Equities

41,146 circulars for 2019-2026, of which **243 are name/symbol changes**. 241
downloaded; 1 failed and is reported below. 191 distinct renames extracted, 190
with an effective date.

Every entry is EVIDENCED BY A CIRCULAR, not inferred from price continuity. Route 2
(inferring renames from adjacent price files) was not needed and was not used.

**The 15 renames touching our universes**, each with its circular:

| old | new | effective | circular |
|---|---|---|---|
| RNAM | NAM-INDIA | 2020-01-23 | CML43292 |
| TATAGLOBAL | TATACONSUM | 2020-02-27 | CML43619 |
| NIITTECH | COFORGE | 2020-08-20 | CML45340 |
| INFRATEL | INDUSTOWER | 2020-12-18 | CML46631 |
| ADANIGAS | ATGL | 2021-01-13 | CML46937 |
| CADILAHC | ZYDUSLIFE | 2022-03-07 | CML51455 |
| MOTHERSUMI | MOTHERSON | 2022-06-09 | CML52507 |
| RUCHI | PATANJALI | 2022-07-13 | CML52890 |
| MINDAIND | UNOMINDA | 2022-08-05 | CML53163 |
| SRTRANSFIN | SHRIRAMFIN | 2022-12-20 | CML54812 |
| IIFLWAM | 360ONE | 2023-01-23 | CML55278 |
| ADANITRANS | ADANIENSOL | 2023-08-24 | CML58016 |
| L&TFH | LTF | 2024-04-23 | CML61613 |
| **GMRINFRA** | **GMRAIRPORT** | **2024-12-11** | **CML65429** |
| TATAMOTORS | TMPV | 2025-10-24 | CML70875 |

GMRINFRA verified verbatim: *"Members of the Exchange are hereby informed that name
and symbol of GMR Airports Infrastructure Limited will be changed w.e.f. December
11, 2024 ... 1 GMRINFRA GMRAIRPORT GMR Airports Infrastructure Limited GMR Airports
Limited"*. The effective date is AFTER 2024-03-28, which is exactly why the walk
broke there: the press release says GMRINFRA, the anchor says GMRAIRPORT.

**THE MAP IS ONLY VALIDATED FOR THESE 15.** The other 176 entries are unchecked and
the extractor is known to produce mis-parses on wrapped lines — `ANDHRA -> PAPER`
is one, a fragment of the Andhra Paper circular rather than a rename. 57 of the 241
circulars yielded no parseable row at all. Before any entry outside the 15 is
relied on, it must be read against its circular. A wrong rename silently merges two
companies' histories, which is worse than a gap.

**2. Complete non-bond press-release set.** 622 entries from 2016 pass the
content-type filter (`Fixed Income|G-Sec|SDL|Bond|Gilt|Money Market|T-Bill|
Treasury|Corporate Debt` excluded — 513 of 1,135). 438 downloaded this round, zero
failures. No include-side keyword filtering: every non-bond release goes to the
parser and the parser decides.

## Download failures

One, and it is not a real document:

    FAIL https://nsearchives.nseindia.com/content/circulars/null63258.null http=404

NSE's own API returned a null filename for that record. Nothing was substituted.

## The walk, with renames canonicalised

Every symbol is resolved to its current form before comparison, transitively (188
map entries, 6 chained).

```
  MIDCAP 100   100 100 100 100 100, then 2024-03-28 -> 101   inc absent: IREDA
  MIDCAP 150   150 150 150 150 150, then 2024-03-28 -> 151   inc absent: IREDA
```

GMRINFRA is gone from the failure. IREDA remains, in both indices.

## IREDA — a bounded, specific gap

IREDA is listed as an INCLUSION on BOTH 2024-03-28 and 2024-09-30. The 2024-03-28
entry is in the hand-verified reference cases; the 2024-09-30 entry was read
directly from ind_prs23082024.pdf, where IREDA appears seven times across different
index sections. Both are genuine.

A name cannot be included twice without leaving in between, so an exclusion exists
that we do not have. **With the complete non-bond archive from 2016 now on disk, it
is not in any press release.** That bounds the problem: it is not a filtering
failure and not a parser failure. The exclusion is either in a bond-classified
release, in a listing circular rather than a press release, or was never announced
as a standalone document.

## Everything else, unchanged from the previous round

Multi-source dates, the 2024-09-30 two-document revocation, the postponement scan
(19 PDFs contain postponement language, none names our three indices), and the
three parser fixes are as previously recorded. All five hand-checked reference
cases still match after every change.

## Next steps

1. Resolve IREDA specifically — search the listing-circular API for it, the same
   route that produced the rename map. That is one query, not a sweep.
2. Validate the remaining 176 rename entries before any of them is used.
3. Only then is it meaningful to ask how far back coverage reaches.
4. MidCap50 stays out until a verified 50-name anchor exists.

## Rule followed throughout

No URL was constructed from a filename pattern. Press releases came from the
archive listing's own links; circulars came from the API's own `circFilelink`
field. `results/extract_membership.py` and `results/repair_membership.py` are
UNMODIFIED.
