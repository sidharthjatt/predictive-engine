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

Migration executed 2026-09-18. The cold rebuild was
`runs/20260918T024833_mid-n100_all_r20/`, 178 artefacts. **That directory was
deleted on 2026-09-20** along with the other ten timestamped old-panel run
folders. The name and the count stay here because they are this migration's
provenance: they say which run the migration was executed from, and that remains
true whether or not the folder is still on disk. Nothing else cited it.

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

**midcap150's `chart_text["index_window_end"]` was wrong and is now FIXED;
WHY it was wrong is UNRESOLVED.** It read `2026-06-08`. The field's own
definition is "the last date this universe's index file carries", and
midcap150's index file ends `06-08-2026` -- **2026-08-06**. Corrected
2026-09-18.

**The correction is settled. The explanation is not, and the two readings are
recorded here unreconciled rather than one of them written up as the cause.**

*Reading 1 -- day/month transposition.* The OLD
`data/raw/MidCap150/clean/NIFTYMIDCAP150.csv` also ends `06-08-2026`, so the
value was already wrong before the repoint and this is not migration damage. The
two dates are the same eight characters with day and month exchanged, which is
what a `DD-MM-YYYY` file read as `MM-DD-YYYY` produces. n100's equivalent is the
contrast: it read `2026-06-22`, the old `NIFTY100.csv` ends `22-06-2026`, so
**n100's was correct until the repoint** and was corrected to `2026-08-06`
with it.

*Reading 2 -- the value is the panel cutoff, not a mangled index date.*
`2026-06-08` is EXACTLY the last date in the raw score panel, and not only
midcap150's: `raw_panel_midcap150_cache.csv`, `raw_panel_nifty100_cache.csv` and
`raw_panel_nifty50_cache.csv` all end `2026-06-08`. It is also the price-data
cutoff recorded elsewhere in this project. **Transposition does not predict that
coincidence** -- there is no reason a mangled `06-08-2026` should land on the
panel boundary shared by all three universes. Under this reading the field was
filled from the panel rather than from the index file, i.e. the wrong source for
its stated definition.

**Neither reading has been eliminated.** Reading 1 explains the character
pattern; reading 2 explains the value. Do not cite either as the cause in a
commit message or a code comment until one is ruled out. What would settle it:
the provenance of the literal when it was first written -- if n100's
`2026-06-22` also coincided with a panel or price boundary at that time,
reading 1 survives alone; if it did not, reading 2 needs an account of n100.

**Fixing midcap150's changes a published chart subtitle**, which is an artefact
change. The reader is display-only -- `make_chart.py` slices the INDEX series
for one console line and touches neither the score panel nor the engine -- so no
committed number moved with it.

**A universe's membership is read from the supplier directory at import, and a
change to it produces no diff in git.** `symbol_list` is
`_constituents(<source>, <index_name>)`, evaluated when `universes/registry.py`
is imported, so the 148, 99 and 50 names are nowhere written down in this
repository. `data/raw/` is gitignored apart from a `.gitkeep`. If the supplier
adds, removes or renames a CSV, the affected universe silently becomes a
different universe: `git status` is clean, every checker passes, and the only
visible trace is a constituent count in a chart subtitle that nobody diffs.

This is pre-existing design, not something the migration introduced -- the two
deleted config modules globbed their directories the same way, and the module
docstring's "a row whose data is gone is a registered universe with no symbols"
depends on it. It is recorded here because the migration makes it matter more:
the panel now comes from a supplier folder that this project does not control
and did not author, and there are six more such folders waiting to be wired.

**Palette distinctness is a MANUAL check, run when a universe is wired, and a
gate was declined rather than forgotten.** `palette_distance.py` measures
CIEDE2000 between every line the combined chart draws, under normal colour
vision and under Viénot 1999 deuteranopia and protanopia simulations. It reports
and exits 0, always. Run it by hand when a universe's `chart_colours` is chosen —
that is the only moment its answer can change:

```
./venv/bin/python palette_distance.py            # report
./venv/bin/python palette_distance.py --write    # also writes the diagnostic
```

Two reasons it is not a gate, both recorded so the next person does not "fix"
the omission. First, **the threshold is reverse-engineered**: dE 10 is what
n50's palette was searched against, and it was chosen because it was the highest
round number achievable against mid's and n100's tuples *without moving them*. A
gate would write that number down and defend it as though it came from
colorimetry. It came from the palettes it would be judging. Second, **it would
ship pre-failed**: three pairs in the current palettes sit below it, so the gate
could only be green on its first day with an exception list naming all three. A
gate whose opening commit is its own exception list is a report with a non-zero
exit code, and an exception list is somewhere to put the thing nobody wanted to
fix.

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

## 7. THE NAMING MAP -- this repository holds two naming worlds

**Renamed 2026-09-18, commit `ab0ebd1`.** Code and live artefacts use the new
names. Records use the old ones, deliberately, and are listed below as records
rather than as things nobody got round to.

| old tag | new tag | what it is |
|---|---|---|
| `mid` | **`midcap150`** | Nifty MidCap 150, 148 constituents |
| `n100` | **`nifty100`** | Nifty 100, 99 constituents |
| `n50` | **`nifty50`** | Nifty 50, 50 constituents |

The five universes not yet wired will use `midcap50`, `midcap100`, `nifty200`,
`nifty500` and `smallcap250`. `.gitignore` already carries their metrics
directories under those names.

**`58` and `74` ARE NOT RENAMED AND WILL NOT BE.** They were deleted on
2026-09-11 and `RETIRED_UNIVERSES.md` is their terminal record; renaming a tag
in a record of something that no longer exists makes the record describe
something that never did. They keep their positions in
`universes/registry.REPORT_ORDER`, where a tag absent from the registry is
skipped rather than raised on.

### THE SECOND NAMING WORLD: STEP LABELS, adopted 2026-09-19

The tag map above is one pair of worlds. **Pipeline step labels are a second
pair, and they live here so there is ONE place to look when a spelling does not
match.** Two worlds with no map is how a week goes.

**NEW SCHEME, NEW UNIVERSES ONLY: `STEP 10.01`, `STEP 10.02`, ...**
zero-padded two digits, one per (universe x per-universe step), with
`STEP 17.01...` and `STEP 18.01...` for those blocks. It covers nine universes
in the 10-block using 36 of 99 slots, is fixed width, and cannot collide with
any existing label because every existing one is alphabetic.

**OLD LABELS STAY. NOTHING IS RENAMED.** `10a-10h`, `10m-10t`, `10u-10x`,
`10y/10z/10za/10zb`, `12b`, `15`, `15b`, `16`, `17`, `17e-17j`, `18a-18f` keep
their spellings. **This includes nifty200's `10y/10z/10za/10zb`**, wired hours
before this scheme: renaming those four would create a THIRD naming world to
save two awkward labels.

**WHY NOT RENAME EVERYTHING.** Surveyed 2026-09-19 before proposing: renaming
costs **101 prose mentions across 7 documents** -- KNOWN_ISSUES 75,
docs/HANDOFF 17, this file 3, docs/README 2, RETIRED_UNIVERSES 2, README 1,
EXPERIMENTS 1 -- plus comments in 22 Python files. Several of those sentences
are ABOUT the gaps, so they would need rewriting rather than find-replacing. It
buys consistency and nothing else.

**UNIQUENESS IS THE ONLY MACHINE CONTRACT. Labels are not parsed and not
sorted.**

- Execution order comes from LIST POSITION, never from the string:
  `check_plan_order.py:70` builds `pos` from `enumerate(pipeline)`, and
  `check_pipeline_order` keeps the earliest list index per script.
- Nothing extracts the number, the series or the letter. No regex reads a
  label. `run_all._step_label()` matches whole rows by **(script, tag)** and
  treats the label as opaque.
- The one sort, `sorted(unresolved)` at `check_pipeline_order.py:701`, orders an
  ERROR PRINTOUT.
- What the label must be is UNIQUE: it is a dict key in `check_plan_order`'s
  `pos` map and part of `check_all`'s GATE 2 / GATE 4 failure identity.

**A CORRECTION TO COMMIT `615e257`.** That commit justified `10za`/`10zb` with
"so nothing sorts after what it precedes." Lexicographic order IS the project's
stated readability rule and those labels do satisfy it -- but the commit
presented it as a requirement, and it is not one. Nothing in the tree would
have failed had they sorted wrongly. A readability convention stated as a
machine contract is the same error class as the entry on measurements written
up as properties.

**FROZEN LABEL SETS -- THESE MUST NOT BE REUSED OR RENAMED:**

| set | why |
|---|---|
| `STEP 11`-`STEP 14` | the deliberate gap from the 2026-09-11 retirement, left so a step's name still means what it meant in every older log. 5 prose mentions in KNOWN_ISSUES, plus `check_pipeline_order.py:80` on "a real STEP 13 -> 14 edge" and `run_all.py:358` on STEP 12 |
| `STEP 10i`-`10l` | burnt: `make_combined_universes`' labels before it moved to STEP 12b |
| `STEP 0`-`STEP 9` | the retired 58 and 74 |
| `RETIRED_UNIVERSES.md` + `-manifest.txt` | terminal records, SHA-256 pinned |

**`runs/` IS FREE, AND THIS WAS CHECKED RATHER THAN ASSUMED.** 49 run
directories: no step label appears in any folder name, in any `RUN.txt`, or in
any tracked run log. This was expected to be the expensive part of a rename and
it is not a constraint at all. Recorded because the next person to cost a
rename will assume the same thing and should not have to re-check it.

### If you are reading an old-named thing

**An old tag is not a missing universe.** `mid` in a document, a diagnostic or a
run folder is `midcap150` before 2026-09-18. Specifically, these still use the
old names and are correct to:

- `experiments/HELDOUT_PREREG.txt` and `diagnostics/heldout_prereg_result.txt`,
  including their SUPERSEDED headers -- a signed pre-registration and the record
  of its one spent run
- `RETIRED_UNIVERSES.md` and `RETIRED_UNIVERSES-manifest.txt`
- `pre_repoint_baseline/` and its `MANIFEST.txt`, 128 of whose 132 paths name
  `metrics_mid/` or `metrics_n100/`; renaming them would invalidate the only
  surviving copy of the pre-repoint figures
- every tracked file under `diagnostics/`
- `runs/*` folder names and everything inside them

**AN OLD-LOOKING NAME IS NOT EVIDENCE OF AN OLD-NAMED DUPLICATE. CHECK BEFORE
YOU DELETE.** Added 2026-09-20, after a cleanup nearly removed three directories
on the assumption that `runs/mid/`, `runs/n100/` and `runs/n50/` were the same
data as `runs/midcap150/`, `runs/nifty100/` and `runs/nifty50/` under the tags
those universes carried before the repoint. **They are not.** Measured on
2026-09-20, file by file: different inodes and different bytes on every one of
the sixteen files under `runs/mid/` against its `runs/midcap150/` counterpart,
and the same answer for the other two pairs. They hold PRE-REPOINT results. Their
canonical homes `results_mid/`, `results_n100/` and `results_n50/` no longer
exist, and `pre_repoint_baseline/` does not cover them -- it copies
`metrics_mid/` and `metrics_n100/`, not these `runs/` trees. **So these three are
the only copy of what they hold, on this machine or anywhere else, and they were
deliberately held back when the eleven timestamped old-panel run folders were
deleted on 2026-09-20.** Three point nine megabytes is not a reason to lose the
only copy of anything.

The eleven that were deleted were safe for the opposite reason, and it was
checked rather than assumed: every file in them was hard-linked from somewhere
that survives, `runs/mid/` included -- `runs/mid/v1/comparison.csv` and
`runs/20260917T011812_mid_all_r20/runs/mid/v1/comparison.csv` were the same
inode, 71786073. **Deleting a hard link is not deleting data, and deleting the
last hard link is. The difference is the whole question, and `du` will not tell
you which one you are looking at:** `du` on those eleven folders reported 135 MB,
and the disk got back 23 MB.
- the frozen specs under `experiments/`
- all prose, everywhere, until the prose pass

### Three artefacts still carry an old tag, and each is deferred on purpose

**1. `"universe_tag"` inside SIX `v34_params*.json`** still reads `"mid"` or
`"n100"`. Those files are written by `engine_v2_final` at STEP 10n, not by the
STEP 15 daily-log pass that the rename commit ran.

**THE COUNT ABOVE WAS "seven `v34_params*.json` and one `v2FINAL_params.json`"
AND BOTH HALVES WERE WRONG.** Measured on disk 2026-09-18 by parsing every
`results_*/metrics/*params*.json` and reading the key rather than globbing
filenames:

- **Seven `v34_params*.json` exist; SIX carry a stale tag.** The seventh,
  `results_nifty50/metrics/v34_params.json`, reads `"nifty50"` -- correct,
  because nifty50 was registered under its current name and never renamed. The
  old count was the count of FILES MATCHING THE GLOB, not of files needing
  correction.
- **No `v2FINAL_params.json` carries a `universe_tag` at all.** All four
  (midcap150, midcap150 `_tradeable`, nifty100, nifty50) lack the key entirely;
  they carry no universe field of any kind. The claimed eighth file cannot be
  stale because it holds nothing to be stale.

The six, in full: `results_midcap150/metrics/v34_params.json`,
`v34_params_v1_tradeable.json`, `v34_params_v2_tradeable.json`,
`v34_params_v3.json`; `results_nifty100/metrics/v34_params.json`,
`v34_params_v2.json`.

**THE DEFERRAL'S STATED REASON -- "the tax work will re-run it anyway" -- IS
FALSE.** A tax run cannot rewrite these files. `tax.suffix()` returns `""` at the
default and `"_tax"` when on, and `run.py` sets the tax selection ONCE per run
with no script serving both a taxed and an untaxed invocation (`run_all.py`,
the `tax:` branch). So `--tax on` writes `*_tax`-suffixed artefacts ALONGSIDE
these six; every one of the six is an UNSUFFIXED default name, which a tax=on
run never opens. The deferral was pointed at a collection point that does not
exist, and left alone these six persist indefinitely.

**CLOSED 2026-09-18 -- (b) TAKEN, the six corrected on their own.** The
alternative, (a), was to give the tax plan an explicit default-arm re-run and let
the tax work collect these as a side effect.

**Why (b): a run exists to produce numbers, and using one as a carrier for a
naming fix is how the fix gets dropped when the run is rescheduled.** That is not
hypothetical here -- it is what already happened. This entry's original reason
attached the correction to the tax work, the tax work has not run, and the six
sat stale through four commits. Attaching it to a *different* future run would
have repeated the mistake with a new date on it. A naming fix that depends on
nothing should wait for nothing.

**What was done, exactly.** `universe_tag` alone, one value per file, six files;
`"mid"` -> `"midcap150"` and `"n100"` -> `"nifty100"`. No other byte moved.
Nothing reads the field back -- the only occurrences in any module are the
`run_v34` parameter and the registry lookup at WRITE time -- so this corrects a
label, not an input.

**TWO CONSEQUENCES, RECORDED BECAUSE THEY ARE THE COST OF (b) RATHER THAN
OBJECTIONS TO IT:**

1. **Each file's `git_state` block now describes a run that did not produce every
   byte of it.** The file says it came from commit `0b021ae` (or `8e32551`,
   `556f910`) with the tree in a stated condition; that is still true of every
   measured number in it and is no longer true of `universe_tag`. A hand-edited
   run artefact is the weaker form of provenance, and it is the price of not
   waiting for a run.
2. **`gate_compare.py` accepts exactly one non-identical field set, `git_state`,
   and says so as data rather than as a review-time argument.** A params file that
   moves in any other field is DIFFERS. These six have now moved in another field.
   A pre/post comparison spanning this commit will therefore flag them, and that
   is the comparator working correctly -- it is not an exception to add. The
   condition is self-clearing: `universe_tag` is written from `u.tag`, the
   registry now says `midcap150`/`nifty100`, so the NEXT engine run at STEP 10n
   rewrites these files with the correct tag from the code path, and the
   hand-edited state disappears.

**`results_nifty50/metrics/v34_params.json` was correct and was left alone.** It
reads `"nifty50"` because nifty50 was registered under its current name and has
never been renamed -- it was wired at `2a6f8a0`, after the tags `mid` and `n100`
were already in use and before the rename that retired them, so it never held an
old tag to correct. It is the seventh file the old count included and the reason
that count and the count of work were different numbers.

**The `pre_repoint_baseline/` copies keep their old tags and MUST.** Four
`metrics_mid/` and two `metrics_n100/` params files are pinned by SHA-256 in
`pre_repoint_baseline/MANIFEST.txt`; they are the only surviving record of the
pre-repoint figures, and an old tag in a historical record is the record, not a
defect. Hashes verified unchanged by this commit.

It was the sharpest of the three: an artefact naming a universe the registry no
longer defines is the shape of inconsistency this project keeps closing.

**2. Two `_tradeable` daily logs** still read `mid_tradeable`.
`make_daily_log` regenerates for the CURRENT execution-realism profile, and
those were produced under `--profile tradeable`. **Deferred to the next
tradeable run**, which will rewrite them as a side effect of doing its own work.

**3. Registry prose** -- `liquidity_note` opens `"mid [measured
pre-2026-09-10 ...]"` and nifty100's `validation_status` reads `"... run on the
58 and the mid ..."`. Both reach a chart caption. **Deferred to the prose pass**,
which is being done one file at a time under review, because `mid` as an English
word and `mid` as a tag cannot be separated by any pattern -- see §4 above.

### Two defects the rename itself surfaced

**`run_all.PIPELINE_ORDER`'s script column contains digits.**
`engine_v2_final.py` does, so a `"[a-z_]+\.py"` pattern matches 12 of the 15
per-universe rows and silently skips three. It happened twice -- once in the
survey probe and once in the rename itself -- and both times the only thing that
caught it was an `assert n == 15` before the write. A regex over this table that
does not assert its own match count will produce a half-renamed pipeline that
imports fine until `_step_label` cannot name a producer.

**`results/make_daily_log.py` has no `__main__` guard.** Its body moved into
`main()` when the pipeline stopped spawning subprocesses, and nothing calls
`main()` when the file is run directly. `./venv/bin/python results/make_daily_log.py`
does nothing, writes nothing, prints nothing and **exits 0** -- a silent success,
which is the failure mode this repository has named more often than any other.
The first daily-log regeneration in the rename commit "succeeded" that way and
changed not one byte; it was caught only by diffing the output against the
saved copies. Call `main()` explicitly, or check that the file you expected to
change actually changed.

## 8. What this migration did not touch

Registry strings that the repoint made false and that were deliberately left
for a commit that declares the artefact change:

- `_MID.survivorship` still reads "Source: data/raw/MidCap150/clean"
- `_N100.survivorship` still reads "Source: data/raw/nifty100_benchmark"
- `_N100.engine_params_static["universe"]` still says "NIFTY100.csv excluded by
  name"; the file is now `NIFTY 100.csv`

Each is text that reaches an artefact. None of them changes a number.
