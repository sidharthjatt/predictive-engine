# PANEL MIGRATION -- the kite panel is gone, 2026-09-18

**Every number this repository produced before this line was computed on a price
panel that is no longer present.** Not a corrected version of it, not a
superseded revision of it -- a different vendor's extraction, with different
prices on most days and different per-name history. This file is the record of
that boundary.

If you are reading a figure in `README.md`, `KNOWN_ISSUES.md`,
`experiments/EXPERIMENTS.md`, `docs/HANDOFF.md`, `RETIRED_UNIVERSES.md`, any
tracked file under `diagnostics/`, or any `experiments/*_SPEC.txt`, and nothing
beside it says otherwise: it is a pre-migration figure and the panel it was
measured on is not in this checkout.

---

## 1. What changed

| | before | after |
|---|---|---|
| mid source | `data/raw/MidCap150/clean` | `data/raw/Final_Without_Survivorship_Data/Final_NIFTYMidCap150_EoD_Data` |
| n100 source | `data/raw/nifty100_benchmark` | `data/raw/Final_Without_Survivorship_Data/Final_NIFTY100_EoD_Data` |
| mid index file | `NIFTYMIDCAP150.csv` | `NIFTY MIDCAP 150.csv` |
| n100 index file | `NIFTY100.csv` | `NIFTY 100.csv` |
| vendor (`source` column) | `kite` | `upstox` |
| extraction timestamp (`_merged_at`) | 2026-07/08 | 2026-08-29 |

**The tags did not change.** `mid` is still `mid`, `n100` is still `n100`, their
metrics directories are the same directories, and their git history is
continuous. That is a deliberate choice and it is the reason this file has to
exist: nothing in a filename, a tag or a path distinguishes a pre-migration
artefact from a post-migration one.

Migration executed 2026-09-18. The cold rebuild is
`runs/20260918T024833_mid-n100_all_r20/`, 178 artefacts.

## 2. What did NOT change

- **The constituent names.** 148 for mid, 99 for n100, nothing added and nothing
  dropped. The only differing line in either directory listing is the index
  file's own name.
- **The backtest window.** 1,836 sessions, 2019-01-01 .. 2026-05-29, both
  universes, before and after.
- **The index series inside the window.** mid's index file is byte-identical
  old to new. n100's is identical across its whole overlap and gains 32 rows at
  the end (2026-06-23 .. 2026-08-06), all of them past `BT_END_DATE`.

## 3. What changed underneath, and is easy to miss

**Prices.** On dates both vendors carry, inside the window, `close`/`adj_close`
differ for **139 of 148** mid names and **90 of 99** n100 names. Nine names in
each universe are byte-identical. The worst cases run to more than 1,800 of
1,842 in-window dates differing (TRENT, VEDL on n100; M&MFIN, IDEA on mid).

**Per-name history.** 35 mid names and 16 n100 names now begin *later* than they
did. **Every one moved later; none moved earlier.** Names that now begin after
`BT_START_DATE` where they did not before:

- **mid (8):** `360ONE` 2015-01-01 -> 2019-09-19, `AIIL` 2015-06-11 ->
  2024-04-23, `DALBHARAT` 2018-12-21 -> 2019-01-22, `HEXT` 2011-01-03 ->
  2025-02-19, `LLOYDSME` 2003-09-05 -> 2023-07-17, `MEDANTA` 2016-04-21 ->
  2022-11-16, `PATANJALI` 2008-01-01 -> 2020-01-27, `SBICARD` 2015-01-01 ->
  2020-03-16
- **n100 (2):** `MAZDOCK` 2017-12-04 -> 2020-10-12, `NESTLEIND` 2003-09-05 ->
  **2023-08-01**

`NESTLEIND` is the conspicuous one: a continuously-listed large cap whose new
extraction begins mid-window. It is in n100 and in n50.

Coverage at `BT_START_DATE` fell from 120/148 to **112/148** (mid) and from
90/99 to **88/99** (n100).

## 4. The figures, and why they are not a reproduction

**These two columns are two vendors' prices for the same names over the same
window. Neither column is a check on the other.** Nothing here is a regression,
a validation, or evidence that anything held.

```
--- mid ---
Config                              CAGR old  CAGR new   delta   DD old   DD new
v1 invvol, 100% invested               50.12     36.85  -13.27  -35.88   -40.84
v2 invvol, breadth-scaled              29.23     27.80   -1.43  -15.68   -20.01
v3 provol, 100% invested               52.69     39.78  -12.91  -29.60   -54.10
v4 provol, breadth-scaled              33.23     34.21   +0.98  -16.76   -24.56
buy & hold equal-weight                28.34     25.46   -2.88  -36.54   -37.73

--- n100 ---
v1 invvol, 100% invested               30.56     25.77   -4.79  -31.92   -36.03
v2 invvol, breadth-scaled              24.43     19.01   -5.42  -18.38   -21.87
v3 provol, 100% invested               23.14     27.29   +4.15  -41.57   -41.07
v4 provol, breadth-scaled              21.36     21.33   -0.03  -22.32   -24.54
buy & hold equal-weight                24.00     24.16   +0.16  -37.79   -38.65
```

Three of ten arms moved up. **Every arm's drawdown worsened on both universes,
buy & hold included** -- uniform in a way the CAGR column is not. mid v3's
-29.60 -> -54.10 is the largest single move and has not been investigated.

**The old column is preserved outside git.** `results_mid/metrics/` and
`results_n100/metrics/` are gitignored, so nothing in version control ever held
those numbers. 132 files were snapshotted before the caches were deleted;
manifest digest
`1ff07205562cd0e0a5521f6067f293f063273b7f03339c8ea040a893639ed212`.

## 5. What is superseded

`experiments/HELDOUT_PREREG.txt` and `diagnostics/heldout_prereg_result.txt`
carry SUPERSEDED headers as of this migration. The held-out run's own
precondition was a reproduction gate against the shipped `v2FINAL_equity.csv` at
a 1e-12 tolerance; on this panel that gate cannot pass. The window is spent --
the sentinel is written -- so the statistic cannot legitimately be recomputed.
Neither file has been deleted and neither will be re-run.

## 6. Decisions recorded here, so their absence is not read as an oversight

**`pit_data_dir` was deliberately not added.** The supplier ships each universe
twice: `Final_Without_Survivorship_Data/`, which every registry row points at,
and `Final_With_Survivorship_Data/`, which carries names that left the index. A
field naming the second one was drafted and then dropped. Survivorship work is
blocked on the supplier and has been recorded as permanent, not deferred; a
registry field that drives nothing invites the next reader to treat its presence
as a capability and fill it in. **This repository has no point-in-time data
wired up, and adding the field would not change that.** When a consumer exists,
the field arrives with it.

**mid's `chart_text["index_window_end"]` is a standing defect.** It reads
`2026-06-08`. The field's own definition is "the last date this universe's index
file carries", and mid's index file ends `06-08-2026` -- **2026-08-06**.

The evidence that this is *not* migration damage: the OLD
`data/raw/MidCap150/clean/NIFTYMIDCAP150.csv` also ends `06-08-2026`, so the
value was already wrong before the repoint. The two dates are the same eight
characters with day and month exchanged, which is what a `DD-MM-YYYY` file read
as `MM-DD-YYYY` produces. n100's equivalent is the contrast that makes the case:
it read `2026-06-22`, the old `NIFTY100.csv` ends `22-06-2026`, so **n100's was
correct until the repoint** and was corrected to `2026-08-06` with it.

**Fixing mid's changes a published chart subtitle**, which is an artefact change
and is why it was not folded into the migration commits. It is wrong on disk
today.

**`naming_declare_check.py` reports 111 undeclared write calls**, and reported
111 before any of this work began. Verified by stashing the changes and
re-running. Nothing in this migration introduced or repaired it; one write added
along the way carries a directive so the count did not move. Inside `run_all.py`
the same gate is configured as reporting-only and does not block.

**`naming_declare_check.py` walks `ROOT.rglob("*.py")` and does not consult
`.gitignore`.** It honours only its own `SKIP_DIRS` and
`SKIP_PREFIX = ("forensic_snapshot_",)`. A gitignored directory is therefore
still scanned: `pre_repoint_baseline/` is invisible to it only because it holds
no `.py` files. Anything executable dropped into an ignored directory will be
audited as project source.

## 7. What this migration did not touch

Registry strings that the repoint made false and that were deliberately left
for a commit that declares the artefact change:

- `_MID.survivorship` still reads "Source: data/raw/MidCap150/clean"
- `_N100.survivorship` still reads "Source: data/raw/nifty100_benchmark"
- `_N100.engine_params_static["universe"]` still says "NIFTY100.csv excluded by
  name"; the file is now `NIFTY 100.csv`

Each is text that reaches an artefact. None of them changes a number.
