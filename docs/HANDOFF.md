# Handoff — what ships, in the order you unpack it

## BLOCKER 1, ABOVE EVERYTHING ELSE: THE DATA IS NOT IN THIS REPOSITORY

**"Clone it, install requirements.txt, run it" DOES NOT WORK, and the reason has
nothing to do with the code.** 172 MB of price data is excluded from git by
`.gitignore:71` (`data/raw/*`) and must be copied separately:

```
data/raw/MidCap150/clean/          149 files    95 MB   148 constituents + NIFTYMIDCAP150.csv
data/raw/nifty100_benchmark/       100 files    77 MB    99 constituents + NIFTY100.csv
```

**THERE IS NO FETCH SCRIPT.** The only downloader in the project,
`results/extract_membership.py`, retrieves NSE press releases for the survivorship
work, not prices. **Nothing in this repository can re-acquire this data.** If you
lose it, it is gone, and a `git clone` gives you a pipeline with nothing to run on.

**THERE IS NO LICENCE.** Nothing records what may be done with it. The rows carry
their own vendor provenance -- `dhan`, `kite`, `upstox`, mixed within single files
-- and no grant of any kind accompanies them.

**DO NOT READ THIS REPOSITORY AS NEARLY PORTABLE.** Every other blocker below --
the two stale citations in `requirements.txt`, the `/tmp` hardcoding, the Python
floor, the symlink farms -- is a half-hour of work. This one is an acquisition
problem and it is the whole problem. A reader who fixes the others still cannot
produce a number.

### The other blockers, in the order they will bite

They are listed here so "below" in the paragraph above means something. None is
large; all are real.

2. **`requirements.txt` cites two files that do not exist** -- `diagnose_decay.py`
   and `reality_check.py`. Checked 2026-09-15 by resolving every `.py` named in
   that file: the other five resolve. A reader following either citation finds
   nothing and cannot tell whether the dependency is spurious or the file is lost.
3. **`/tmp` is hardcoded in 37 places** and needs about 1.5 GB free. It is a POSIX
   assumption, not a configurable path.
4. **Python 3.12 or newer is a hard floor**, set by `nautilus_trader`.
5. **The symlink farms must ship EMPTY.** A copy that preserves absolute symlinks
   pointing at the source machine fails in a way that looks like missing data
   rather than a bad copy. `rsync` without `-L` and `zip` both do this.
6. **`--profile tradeable` cannot complete a run.** It reconciles through STEP 15b
   and dies at STEP 16 on a profile-suffixed score-panel name that should not
   exist. See `KNOWN_ISSUES.md`, "No component owns which axes an artefact
   carries".
7. **Cross-machine reproducibility is untested** -- the next section is about
   exactly this, and names the four axes nobody has varied.

---

## Read this paragraph before anything else

**Cross-machine reproducibility has never been tested.** Nobody has run this
pipeline on a second machine and compared the numbers. On 2026-09-12 a cold
rebuild reproduced both universes' published figures byte-identically on every
field — but that was the **same machine, the same `venv`, the same interpreter**.
It is evidence that the one pinned dependency is pinned in the right place. It is
not evidence that you will get the same numbers, and it should not be quoted as
if it were.

Expect to reproduce the *structure* — the shape of the equity curve, the trade
count within a few, the drawdown within a point. If you reproduce the headline
CAGR to two decimal places on different hardware, that is a stronger result than
this project has ever demonstrated, and it is worth reporting back.

Before trusting any number you produce, read `KNOWN_ISSUES.md` from the top. The
first entry is the one that matters: the strategy's return edge over a
fully-invested benchmark is smaller than the noise it is measured through, and
its drawdown advantage does not survive the control that holds exposure fixed.

---

## 1. The code

Every `.py` file — **84** of them, all tracked. Ship the directory layout exactly
as it is:

```
run.py  run_all.py  paths.py  config.py  config_mid.py  config_n100.py
cadence.py  profiles.py  module_state.py  check_pipeline_order.py  (+ root tools)
results/     the engine, the steps, and the shared libraries
nautilus/    the execution port (STEP 16, STEP 17)
universes/   registry.py — the single definition of what a universe is
arms/        registry.py — the single definition of what an arm is
experiments/ specs and pre-registrations (not executed by the pipeline)
diagnostics/ findings files (not executed by the pipeline)
```

**There is no `__init__.py` anywhere.** `results/`, `nautilus/`, `universes/` and
`arms/` are plain directories that work because every entry point manipulates
`sys.path`. Flattening the layout, or turning them into packages, breaks imports
in ways that will not be obvious.

### NAVIGATING `results/` — 21 of its 47 modules are load-bearing, 26 are not

**THE DIRECTORY DOES NOT REFLECT THIS, AND THAT IS THE SINGLE MOST MISLEADING
THING ABOUT THIS REPOSITORY.** Pipeline steps and one-off measurement probes sit
side by side in one directory, so everything looks load-bearing and nothing
indicates which files a run actually touches. Measured 2026-09-13 by resolving
`PIPELINE_ORDER` and taking the transitive import closure.

**LOAD-BEARING (21).** `PIPELINE_ORDER` invokes these, or something it invokes
imports them. Changing one changes a run.

    steps    build_scores_mid      build_scores_n100      build_scores_step
             engine_v2_final_mid   engine_v2_final_n100
             make_mid_audit        make_n100_audit        audit_step
             make_mid_chart        make_n100_chart        make_combined_universes
             make_daily_log        save_caches_step
    libs     engine_core  test_exposure  v34_common  features_v2
             arm_sources  survivorship   tradability  qbeast_in_charges

**MEASUREMENT TOOLS AND PROBES (26).** **The pipeline never runs any of these.**
Every one is cited as evidence in a tracked document, so none is dead — but none
executes unless a person runs it by hand.

    attribution_v2          audit_leakage           calendar_coverage_probe
    check_a_close_values    check_b_exec_timing     diagnose_alpha
    drawdown_exit_measure   extract_membership      leakage_check1_causality
    leakage_check2_purge    leakage_check4_corpactions
    purge_fix_measure       purge_mode_probe        rebal_cadence_sweep
    repair_membership       save_ewma_comparison    seed_noise_measure
    seed_noise_report       shuffle_test            stability_test
    tax_util                test_feature_pruning    test_survivorship
    validate_breadth_live   validate_engine         validate_topn

**THE DEPENDENCY RUNS ONE WAY, and that is what makes the distinction safe to
rely on: NOTHING in the load-bearing set imports anything from the tool set.**
Seventeen of the twenty-six import back the other way -- `engine_core` in ten of
them, `test_exposure` in eight -- which is why they all carry their own
`sys.path.insert(ROOT / "results")`.

**A MOVE IS PLANNED AND HAS NOT HAPPENED.** The tools are to be relocated out of
`results/`, leaving only what `PIPELINE_ORDER` reaches. It is sequenced AFTER the
per-universe module collapse, because steps 2-8 merge or rename several of the
load-bearing files and moving first would stale the same document citations
twice. The engineering is one tuple -- `run_all.STEP_DIRS` searches by filename
across a list of directories and would gain the new one; `check_pipeline_order`
and `naming_declare_check` resolve by that same list or by whole-tree walk, and
nothing anywhere scans `results/` to find modules. The real cost is **58
path-form citations across 23 of the 26**, in `KNOWN_ISSUES.md`,
`experiments/`, `diagnostics/` and `requirements.txt`.

**Until it happens, use the two lists above rather than the directory.**

**A CITATION NAMING A FILE THAT NO LONGER EXISTS IS DELIBERATE, NOT A BUG TO FIX.**
The collapse (steps 3-8) merges the per-universe step pairs, and each merge leaves
prose in `KNOWN_ISSUES.md`, `experiments/`, `diagnostics/` and this file naming a
predecessor -- `build_scores_mid.py` and `build_scores_n100.py` went at step 3,
eleven citations with them, and steps 4-7 will add more. **They are left as
historical record of what those files did**, the same treatment
`RETIRED_UNIVERSES.md` gives the 58's and 74's scripts, and the same rule that
left STEPS 0-9 and 11-14 as numbering gaps: a name means what it meant when it was
written. Each merged module's docstring names its predecessors, so the trail greps
from either end. **Do not "repair" them.**

### THE COLLAPSE — the whole plan, because until now it was not written down

**THIS SECTION EXISTS BECAUSE ITS ABSENCE WAS A DEFECT, NOT A MISSING NICETY.**
Until 2026-09-16 the collapse was referred to by step number in two places —
`docs/HANDOFF.md` ("steps 3-8") and `KNOWN_ISSUES.md` ("steps 4-8") — and **no file
in this repository said what any step was.** The numbers were legible only to
someone who had been in the conversation where they were agreed. Six steps had
already landed under them.

**THE RULE THIS SECTION IS WRITTEN UNDER: a step whose definition exists only
because somebody said it in chat does not exist.** Two entries below say exactly
that, and they are not placeholders to be filled in from memory.

| step | what it is | commit | state |
|---|---|---|---|
| 1 | **NOT ON DISK** | — | **undefined** |
| 2 | the invocation contract | `5c636cf` | landed |
| 3 | `build_scores_mid` + `build_scores_n100` → `build_scores(u)` | `e60f5e3` | landed |
| 4 | `make_mid_audit` + `make_n100_audit` → `make_audit(u)` | `535d6f1` | landed |
| 5 | the engine pair → `engine_v2_final(u)` | `f533082` | landed |
| 6 | the chart pair → `make_chart(u)` | `ad7632a` | landed |
| 7 | `config_mid.py` + `config_n100.py` → registry rows | `5c8cda9` | landed |
| 8 | `REQUIRED_INPUTS` derived from the registry | `a32ef28` | landed |

**STEP 1 IS GENUINELY UNRECORDED.** No commit subject or body names
either; no document defines either. `5c636cf` calls itself "Step 2 in the new
order", which establishes that a step 1 was intended and that an earlier `S1`..`S5`
numbering was replaced — `6f7967f` ("S5: collapse the audit and build_scores clone
families onto the registry") is from that older scheme and is **not** step 5.
Do not map the two schemes onto each other from the titles; they do not line up.
**Step 8 was in the same state until 2026-09-16.** It was defined below first and
implemented afterwards, which is the only reason it exists as a step at all.

**WHAT EACH LANDED STEP ACTUALLY DID**

- **Step 2, `5c636cf` — the invocation contract.** The precondition for every merge
  that follows: steps 3 through 7 all hit the `main()`-takes-no-arguments wall.
  A step now declares its arity in its own signature — `def main()` is a whole-run
  step, `def main(u)` is per-universe — and `run.py` reads that with `ast`. WHICH
  universe comes from `run_all.PIPELINE_ORDER`'s third field. `STEP_UNIVERSES` and
  `SCORE_BUILD_STEPS`, the fifth and sixth hardcoded lists in this repository,
  retired with nothing replacing them.
- **Step 3, `e60f5e3`.** The two files differed in the registry key they passed and
  the filenames their docstrings quoted. Nothing else. First time one script
  appeared at two `PIPELINE_ORDER` positions, which broke `check_pipeline_order`'s
  `order` map — it now takes the earliest position.
- **Step 4, `535d6f1`.** The audit pair. The writes moved into
  `results/audit_step.py`, which is why `STEP_HELPERS` exists.
- **Step 5, `f533082`.** The largest merge and the only pair that had genuinely
  diverged: 95 code lines with prose stripped, and some of it reached published
  artefacts. `v2FINAL_params.json` carries a different key SET and key ORDER per
  universe. Preserved as registry data — `validation_status`, `engine_params_keys`,
  `engine_params_static`, `engine_text` — **not unified.**
- **Step 6, `ad7632a`.** The most divergent pair, 204 code lines. `chart_text`
  carries the output stem, dpi, legend font size, index-window end, two booleans,
  and the subtitle and drawdown legend label as CALLABLES. Transitional asserts
  reached zero. Two defects introduced and caught here; see the commit.
- **Step 8, `a32ef28`.** Ten hand-written `REQUIRED_INPUTS` tuples become a
  comprehension over `REGISTRY`. Paths from `paths.py`, the step label looked up
  from `PIPELINE_ORDER` by `(script, universe)` and never restated. **14 → 9.**
- **Step 7, `5c8cda9`.** The first merge where neither side was a superset.
  The two configs' code differed in exactly two expressions, both path shapes, and
  both are registry data. `check_pipeline_order.REG_ASSIGN` arrived with it,
  because the old spelling it resolved writes through no longer exists.

**WHAT REMAINS AFTER STEP 7 — measured 2026-09-16, not estimated.** This is the
inventory whoever defines step 8 should start from; it is not a claim about what
step 8 is.

- **`run_all.py`, 9 hand-written entries per universe**: 4 `PIPELINE_ORDER` rows
  (10a–10d) and 5 `REQUIRED_INPUTS` tuples, spread across `make_chart.py`,
  `make_combined_universes.py`, `nt_execute.py` and `nt_export_scores.py`.
- **`results/make_combined_universes.py`, 3 required edits per universe**:
  `DISPLAY`, `COLOURS`, and the `FILES` block. `LIQUIDITY` and `PAIR_CHART` are
  editorial. Note that step 7 did **not** reduce this file's count — it went 14 to
  16, because the registry lookups that replaced the config imports are themselves
  named sites. What step 7 removed was the second DEFINITION of a universe's paths,
  not the hand-written tags.
- **`REQUIRED_INPUTS` deriving from the registry is separate work and is not a line
  in step 8.** Its entries are literal `ROOT / "results_mid" / "metrics" / ...`
  paths. Deriving them moves a guard table four consumers read and needs its own
  pre/post edge-inventory diff. (The comment above the `make_chart.py` entries
  claims the literal shape is what keeps `check_pipeline_order` resolving the edge.
  That claim is wrong as written: `run_all.py` is never scanned — only
  `PIPELINE_ORDER`'s step scripts and their `STEP_HELPERS` are.)
- **The `results/` move** — 26 probes out of `results/`, 58 path-form citations
  across 23 of them. Sequenced after the collapse; see the paragraph above.

**THE GATE EVERY STEP OF THIS COLLAPSE IS HELD TO** is `gate_compare.py`'s
`STANDING_GATE`, six cells, run pre and post **on the same panel and from a clean
tree**. Checksum is the gate; a survey of what differed is not evidence. The one
accepted non-identical field set is `gate_compare.PROVENANCE_FIELDS` — four fields
inside `git_state` — and it is enforced by the comparator rather than argued at
review time (`ebdbf8a`).

**ONE COMMIT IN THAT RANGE IS UNGATED, BY ARGUMENT RATHER THAN BY OVERSIGHT.** The
artefact gate covers `5c8cda9` -> `6d618ac`. `87ba029` is comparator reporting
only — it changes what the gate prints about a difference, not which differences it
accepts — so no artefact was re-run for it. Said here because the next reader takes
a hash range and assumes coverage across all of it.

**THE SECOND AND THIRD UNGATED COMMITS, ON THE SAME PRINCIPLE.** The later gate
covers `fddc560` -> `d90e1c1`. Within and around it:

- `fddc560` (item A, the probes) was **not** artefact-gated, and the reason is
  mechanical rather than argued: **no load-bearing module imports any of the three
  probes or `measured_universes.py`**, checked by resolving every import of the 19
  load-bearing modules, and none of the three is in `PIPELINE_ORDER`. There is no
  path by which it reaches an artefact.
- **Documentation-only commits are not gated and are not listed individually**
  — `9a5a1ed`, `77d2a54`, `d90e1c1` and this paragraph change no code. Stating that
  once is what keeps this note finite; stating each would make it a changelog.

### WHAT IS DEFINED NEXT — written before any of it is started

**THE RULE, AND IT IS WHY THIS BLOCK EXISTS.** A step whose definition lives only
in a conversation does not exist, and steps 1 and 8 spent six days proving it.
Everything below was written down before the first line of its code.

**ADDING A UNIVERSE COSTS 14 HAND-WRITTEN ENTRIES TODAY**, measured 2026-09-16 by
registering a throwaway universe and wiring it until `registry_coverage_check.py`
passed: 1 `REPORT_ORDER` + 1 `DISPLAY` + 1 `COLOURS` + 1 `LIQUIDITY` + 1 `FILES`
block + 4 `PIPELINE_ORDER` rows + 5 `REQUIRED_INPUTS` tuples. **The target is 5,
not 1**, and the five that stay are decisions rather than duplication.

---

#### ITEM A — the probes declare which universes they have measurements for. **LANDED, `fddc560`.**

**BEFORE STEP 8, and the ordering is deliberate.** Three measurement probes carry
per-universe MEASURED constants and iterate a hand-written
`(REGISTRY["n100"], REGISTRY["mid"])` pair:

| probe | constant | what it holds |
|---|---|---|
| `results/drawdown_exit_measure.py` | `SEED_FLOOR` | the measured noise floor, v2, CAGR |
| | `TRADABILITY_EXPECT` | G4's exact expected counts |
| `results/rebal_cadence_sweep.py` | `SEED_FLOOR` | the floor per arm per universe |
| `results/purge_mode_probe.py` | `MONTHS` | the months this study cuts on |

**A THIRD UNIVERSE IS INVISIBLE TO ALL THREE.** Not a `KeyError` — the pair is
written out, so the probe simply reports on two universes and says nothing about
the third. That is instance seven in the tool set: a study that covers 2 of 3 and
is indistinguishable from one that covers 3 of 3.

**WHY THIS ONE GOES FIRST.** `SEED_FLOOR` is the measured noise floor. Its
invented predecessor put every threshold in this project against half the real
bar, and correcting it changed the project's conclusions. A probe that quietly
narrows its universe coverage is that failure waiting to happen again, in the one
measurement that moved everything else.

**THESE ARE NOT DERIVED. THEY ARE DECLARED.** A measurement cannot be computed
from a registry row. The shape is `LIQUIDITY`'s `NOT_MEASURED`:

- each probe declares the universes it has measurements for, in the order its
  report is written (that order is load-bearing and stated in each file);
- `UNIVERSES` is built from that declaration instead of a hand-written pair, so
  the set the probe iterates cannot disagree with the constants it holds;
- a declared universe missing from any of the probe's measured constants is a
  REFUSAL naming the constant — a hole, not a default;
- **a registered universe the probe has no measurement for is CORRECT and is
  PRINTED IN THE PROBE'S OWN OUTPUT**, so the diagnostic states its own coverage
  rather than leaving the reader to infer it from which sections appear.

`rebal_cadence_sweep.SEED_FLOOR` already does exactly this on the ARM axis —
`None` means NEVER MEASURED and `floor_verdict` returns `UNKNOWN` rather than
substituting a number. The universe axis is what is missing.

**GATE.** Run a probe with one universe's constants removed and show the output
NAMES THE GAP rather than quietly narrowing. Probes write into tracked files under
`diagnostics/`, so any demonstration run must be reverted and the tree left clean.

---

#### ITEM B — STEP 8: `REQUIRED_INPUTS` derived from the registry. **−5 of 14. LANDED, `a32ef28`.**

All five tuples are `<that universe's metrics_dir> / <filename carrying its tag>`,
produced by a named step. Pure duplication of what the registry already holds.

**THE STEP LABEL IS LOOKED UP, NOT RESTATED.** The third element of each tuple is
`"STEP 10c make_audit.py"` for mid and `"STEP 10g make_audit.py"` for n100 — a
`PIPELINE_ORDER` label. Restating it here would be the seventh hardcoded list in
this repository; it is resolved from `PIPELINE_ORDER` by `(script, universe)`.

**IT GOES BEFORE THE OTHER PHASES BECAUSE IT HAS NO ARTEFACT SURFACE.**
`REQUIRED_INPUTS` is a guard table. Nothing in it reaches a PNG or a CSV. Its only
observables are the `covered` set handed to `check_pipeline_order.enforce` and
`check_inputs`' refusal behaviour.

**GATE.** The `covered` set identical pre/post; the edge inventory diff empty;
artefacts byte-identical on `mid all research` and `n100 all research`, both
passes from a clean tree; **plus a deletion demonstration** — remove a produced
input and show the guard still names the file and the step that owes it, which is
the whole reason the table exists.

---

#### PHASE 2 — wanted, not yet started. `DISPLAY`, `COLOURS`, `LIQUIDITY` become registry row fields. **−3.**

**THE DATACLASS KNOCK-ON IS THE PRIZE, NOT THE −3.** As fields with no default, a
row that omits one fails at construction with a `TypeError` naming the field.
**Three of `registry_coverage_check.py`'s tables stop being NEEDED rather than
being silenced** — a field with no default cannot be forgotten, while a checker has
to remember to look. That is a strictly stronger guarantee than the one this
project just finished building, and it is the argument for doing it.

Second reason, independently sufficient: **`LABELS = {"n100": "NIFTY 100", "mid":
"MIDCAP150"}` appears verbatim in 16 files** — a seventeenth copy of `DISPLAY`,
spread across the probes. One `display_name` field retires all of them.

Not first, because colours, display names and the liquidity prose all reach the
combined PNG: this is the phase that can move a published figure, and it is held
to the artefact checksum.

---

#### PHASE 3 — DEFERRED, and this is the reason, not an omission

The `FILES` block in `make_combined_universes.py`. **−1 of 14: the smallest gain
of the three, on the most delicate machinery in the repository.**

The four filenames per universe are derivable (`daily_trades_{tag}.csv`), but the
literal has to stay in the call: `check_pipeline_order` reads `DIR / "<literal>"`
out of the source, and **a computed name already made three edges vanish once.**
Doing it means teaching the scanner to expand a `{tag}` placeholder against a loop
over selected universes — the same class of work as step 7's `REG_ASSIGN`, for one
fifth of its payoff.

**REVISIT ONLY IF SOMETHING ELSE NEEDS THAT SCANNER WORK ANYWAY.** Deferred by
decision on 2026-09-16, not left undone by oversight.

---

#### NOT WORTH DOING — 5 of the 14 stay, by design

- **`REPORT_ORDER` (1).** Where a universe sits in a combined report is editorial:
  position is visible in a filename, a legend and a colour assignment. The registry
  docstring argues against deriving it and `report_order()` already raises by name.
- **`PIPELINE_ORDER` (4).** `5c636cf` settled this — "PIPELINE_ORDER is a
  declaration with no other source; it is the ordering itself, written down."
  Deriving the rows means generating the labels, and `STEP 10a`..`10h` are
  load-bearing for identity: that rule is what let "10h crashed" in a six-day-old
  document be read without ambiguity. Generating them for new universes while
  pinning the existing ones trades four rows for a label map, which is one table
  for another. **The correct fix was making the silence loud, and it shipped in
  `6d618ac`.**

---

## 2. The trading calendar — ships, and cannot be rebuilt

```
data/nse_trading_calendar.csv     6,574 sessions, 2000-01-03 to 2026-06-08
```

**Tracked, required by every panel build, and there is no longer any code that
can regenerate it.** It was derived from a universe called "the 58", which was
deleted on 2026-09-11 along with `results/make_trading_calendar.py`. The file is
now source data in the same sense as a raw price file. If you lose it, restore it
from git; nothing can recompute it.

Its end date, 2026-06-08, is a **data** boundary, not a market one — it is simply
the last date present in the deleted universe's files. See
`RETIRED_UNIVERSES.md` section 6.

## 3. The price data — 172 MB, untracked, three vendors, no licence

```
data/raw/MidCap150/clean/          149 files    95 MB   148 constituents + NIFTYMIDCAP150.csv
data/raw/nifty100_benchmark/       100 files    77 MB    99 constituents + NIFTY100.csv
```

**A `git clone` does not produce a runnable repository.** These directories are
excluded from git and must be copied separately.

**CORRECTED 2026-09-13. This section previously said "no source, vendor, download
date or licence is recorded anywhere for this data." That was wrong**, and it was
wrong in the direction that mattered: it told a reader not to look. Every price row
carries its own provenance, in columns nothing in the pipeline reads:

| column | what it holds |
|---|---|
| `source` / `_source` | the vendor: **`dhan`, `kite`, `upstox`** — three of them, mixed within single files |
| `exchange` / `_exchange` | `NSE` or `BSE` |
| `product_class` | `EQUITY` |
| `_window`, `_window_freq`, `_window_start`, `_window_end` | the fetch window, monthly |
| `_dq_score` | a per-row data-quality score, **0.62 to 1.00** |
| `_gap_filled` | 0/1, the vendor's own synthetic-row flag |
| `_merged_at` | full ISO timestamp of the merge |

**THE MERGE VINTAGES DIFFER BY UNIVERSE, and nothing else records this:**

    mid                 _merged_at  2026-08-11
    n100                _merged_at  2026-07-20
    N100_Survivorship   _merged_at  2026-07-23 and 2026-07-30

**The two live universes' price data were extracted three weeks apart.** Any
cross-universe comparison in this project spans that gap, and no result states it.

**WHAT IS GENUINELY MISSING, which is still enough to matter:**

- **No licence.** Nothing records what may be done with this data.
- **No fetch script.** The only downloader in the project,
  `results/extract_membership.py`, retrieves NSE press releases for the
  survivorship work, not prices. There is no way to re-acquire the data from
  anything the repository contains, so **if you lose it, it is gone.**
- **No prose describing the columns.** The contract above was recovered by reading
  the files on 2026-09-13, not from any document.

Read alongside `KNOWN_ISSUES.md`, which now carries the same correction and the
measured consequences of `_dq_score` and `_gap_filled` going unread.

Column contract: `date, open, high, low, close, adj_close, volume, open_interest`
at minimum. `adj_close` is the canonical price and is resolved into `close` at the
single load boundary in `engine_core.build_panel`.

## 4. The symlink farms — ship them empty, never broken

```
data/raw/MidCap150/constituents/
data/raw/N100_constituents/
```

These contain **symlinks**, not files. They are rebuilt on import by
`config_mid.ensure_constituents_dir()` and `config_n100.ensure_constituents_dir()`,
so shipping them empty is correct and costs nothing.

**Shipping them containing stale absolute symlinks is not.** A copy that
preserves broken links pointing at the source machine's paths will fail in ways
that look like missing data rather than like a bad copy. `rsync` without `-L`,
and `zip` without care, both do this. Delete the contents and let the code
rebuild them.

## 5. Tooling data — ships, but the pipeline does not read it

```
data/reference/*.csv                  3 files, 9.6 MB   membership tooling
data/raw/membership_workbooks/*.xlsx  4 files, 116 KB   survivorship tooling
data/raw/N100_Survivorship/…          160 MB            point-in-time membership
```

None of this is on the pipeline path. The survivorship membership file is read
only when `SURVIVORSHIP_MODE = "pit"`, which **no pipeline step sets** — the
default is `"static"`, today's constituents backfilled. Ship it if you intend to
work on survivorship; the pipeline runs without it.

## 6. The environment

**Python 3.12 or newer.** A hard floor, set by `nautilus_trader`, not a
preference.

**`requirements.txt` pins exactly one thing, deliberately:**

```
lightgbm==4.6.0
```

Every score in this project comes from `lgb.LGBMRegressor`. A one-bit float
difference is enough to flip a split decision, reorder near-tied names at the
`TOP_N=8` boundary, and move the headline CAGR by two thirds of a point — that is
measured, not feared; see `KNOWN_ISSUES.md`, *"The headline is not reproducible
from the artefacts on disk to better than about a point"*. A minor-version bump
is free to change split arithmetic, so a floor would not preserve the numbers.

Everything else is a range, with the versions present at the last published
headline recorded in `requirements.txt` as provenance. There is one data point on
what that looseness costs: on 2026-09-12, five of those libraries had drifted from
the recorded versions (`scipy`, `scikit-learn`, `joblib`, `matplotlib`,
`nautilus_trader`) while `lightgbm`, `numpy` and `pandas` matched — and the
numbers reproduced byte-identically. One observation, same machine.

**`/tmp` must exist and be writable, with about 1.5 GB free.** It is hardcoded in
37 places as the working directory for the score and raw panels. This is a POSIX
assumption, not a configurable path.

**Nothing else outside the repository is read.** No absolute paths, no home
directory, no environment variable is ever read — `PYTHONHASHSEED` and the
thread-count caps are set by the code, never consulted from outside.

## 7. First run

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

# Confirm the real cost model is active, not the 0.11% fallback.
# If this prints FALLBACK, every cost figure will differ by about 9%.
./venv/bin/python -c "import sys;sys.path.insert(0,'results');\
import engine_core,inspect;\
print('REAL' if 'compute_leg_charges' in inspect.getsource(engine_core.calc_tc) else 'FALLBACK')"

./venv/bin/python run.py --list                     # resolved plan, runs nothing
./venv/bin/python run.py --universe mid --arm v2    # ~20 min, most of it scoring
```

Use `./venv/bin/python`, not `python3`. Every step is spawned with
`sys.executable`, so the launching interpreter propagates to every child.

**Expect about 35 minutes for a cold two-universe run**, of which 34 is the two
LightGBM scoring steps (measured 2026-09-12: 18.5 min for mid, 15.7 for n100).
Every other step is seconds. Once the panels exist in `/tmp`, or have been
persisted by STEP 15b, scoring is skipped and a full run is a couple of minutes.

## 8. What is not settled, and what you should not assume

- **Cross-machine reproducibility.** Untested. This is the open item this file
  exists to flag: nothing in this repository can answer whether anyone else can
  reproduce these numbers, and nobody has tried. It is the first thing a new
  holder of this code is in a position to establish, and it would be worth more
  than any further backtest.
- **Combination coverage.** Of roughly 540 nominal selection combinations
  (universe × arm × cadence × profile × steps), a small minority have ever been
  run. Nine of fifteen arm subsets have never been exercised; the `tradeable`
  profile appears in two runs out of fifty-five. Three separate axes have now
  produced the same class of bug — a hardcoded name where a selection-derived one
  belonged — on the cadence, arm and profile axes in turn.
- **The numbers themselves.** `KNOWN_ISSUES.md` is long and it is the honest
  half of this repository. Read it before the README.
