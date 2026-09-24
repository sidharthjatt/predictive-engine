# Handoff — what ships, in the order you unpack it

## BLOCKER 1, ABOVE EVERYTHING ELSE: THE DATA IS NOT IN THIS REPOSITORY

**"Clone it, install requirements.txt, run it" does not work until the price
data is copied in, and nothing in the repository can fetch it.** The data comes
from the owner of this repository. README.md, "The price data", gives the exact
layout: one folder, `data/raw/Final_Without_Survivorship_Data/`, 876 MB, 1,392
CSVs in eight subfolders, one per universe. `data/raw/*` is excluded by
`.gitignore`.

Check a copy before running anything:

```
python3 check_data.py
```

It compares every file with the tracked manifest `data/RAW_DATA_SHA256.txt` and
exits 0 only when all 1,392 files match and no extra file is present.

**There is no fetch script and no licence.** The only downloader in the project,
`results/extract_membership.py`, retrieves NSE press releases for the
survivorship work, not prices. Nothing records what may be done with the data.

### The other blockers, in the order they will bite

2. **Python 3.12.13, every direct dependency pinned exactly** in
   `requirements.txt`, the rest in `installed_versions.txt` (section 6).
3. **Use `./venv/bin/python`, not `python3`**, for everything except
   `check_data.py`. On the machine this was built on, `python3` is 3.11 with no
   lightgbm.
4. **Windows is untested** (README, "Running it").

Closed and kept here so they are not rediscovered as open:

- **CLOSED 2026-09-24 -- cross-machine reproducibility.** A midcap50 v2 run was
  byte-identical on macOS arm64, Linux arm64 and Linux amd64 (README, "Running
  it"), and a fresh clone of origin/main reproduced midcap50 v2 byte for byte,
  tax off and on, on 2026-09-24.
- **CLOSED 2026-09-24 -- the farms no longer ship.** They live under the
  gitignored `cache/`, hold hard links (or copies) instead of symlinks, and are
  rebuilt from `data/raw/` on demand.
- **CLOSED 2026-09-16 -- `--profile tradeable` completes.** Completing is not
  being validated: no gate cell covers what STEP 16 and STEP 17 produce under
  that profile.
- **CLOSED -- `requirements.txt` cited two files that do not exist.** The file
  now says so itself (its lines 69-70).

---

## Read this paragraph before anything else

Before trusting any number you produce, read `KNOWN_ISSUES.md` from the top. The
first entry is the one that matters: the strategy's return edge over a
fully-invested benchmark is smaller than the noise it is measured through, and
its drawdown advantage does not survive the control that holds exposure fixed.
Reproducing a published figure to the last digit (which the fresh-clone check
above did) shows the pipeline is deterministic; it does not show the figure is
stable. `diagnostics/price_noise.txt` measures how far a figure moves under a
0.01% price perturbation.

---

## 1. The code

Every `.py` file, **101** of them on 2026-09-24, all tracked. Ship the directory
layout exactly as it is:

```
run.py  run_all.py  paths.py  config.py  check_all.py  check_data.py
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

    steps    build_scores          build_scores_step      engine_v2_final
             make_audit            audit_step             make_chart
             make_combined_universes                      make_daily_log
             (one of each since the collapse; each takes a Universe. The list
             was measured 2026-09-13 with the per-universe pairs, since merged.)
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
historical record of what those files did**, the same treatment the retired
universes' scripts got in RETIRED_UNIVERSES.md (now in git history), and the same rule that
left STEPS 0-9 and 11-14 as numbering gaps: a name means what it meant when it was
written. Each merged module's docstring names its predecessors, so the trail greps
from either end. **Do not "repair" them.**

### THE COLLAPSE — the whole plan, because until now it was not written down

> **THE COLLAPSE IS COMPLETE AND IS NOT REOPENED.** Adding a universe costs **7
> hand-written entries against a floor of 5**; the two entries above the floor are
> the `FILES` block in `results/make_combined_universes.py` (Phase 3, deferred with
> its reason below) and the `PIPELINE_ORDER` row for `tax_report.py`. Step 1 is
> undefined and stays undefined. Neither is a backlog item, and neither should be
> reopened on momentum.
>
> **IT WAS 6 UNTIL 2026-09-17.** Wiring `results/tax_report.py` into the pipeline
> added a fifth `PIPELINE_ORDER` row per universe. That is not collapse work
> reopening — it is a new step arriving, and a new step costs a row. The number is
> updated here rather than left at 6 because it is a MEASUREMENT and it moved, and
> a stale count in an opening line is exactly the defect KNOWN_ISSUES.md records
> under "A gate count measured before the change it describes".

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
- **Phase 2, `d3ae8ec`.** `make_combined_universes`' `DISPLAY`, `COLOURS` and
  `LIQUIDITY` become `Universe` fields with no default, so a row that omits one
  fails at construction. `registry_coverage_check` drops 13 tables to 10 and says
  so. **9 → 6.**
- **Step 8, `a32ef28`.** Ten hand-written `REQUIRED_INPUTS` tuples become a
  comprehension over `REGISTRY`. Paths from `paths.py`, the step label looked up
  from `PIPELINE_ORDER` by `(script, universe)` and never restated. **14 → 9.**
- **Step 7, `5c8cda9`.** The first merge where neither side was a superset.
  The two configs' code differed in exactly two expressions, both path shapes, and
  both are registry data. `check_pipeline_order.REG_ASSIGN` arrived with it,
  because the old spelling it resolved writes through no longer exists.

**WHAT REMAINS AFTER STEP 7.**

> **LAST VERIFIED 2026-09-17 against HEAD `e79506e`, file by file.** The original
> block was written 2026-09-16 and labelled "measured, not estimated" — but it
> carried a measurement date with no commit to check it against, so there was no
> way to tell it had gone stale within a day. It had. Three of its four bullets
> were wrong by the time they were read. Anyone re-reading this block after HEAD
> has moved should re-verify it and replace this line; a date alone is not enough.

This is the inventory whoever defines the next step should start from; it is not
a claim about what that step is.

- **`REQUIRED_INPUTS` derived from the registry — DONE, `a32ef28`.**
  `run_all.py:424` is `REQUIRED_INPUTS = _required_inputs()`, and
  `run_all.py:346-366` loops `for u in REGISTRY.values()` building 4-tuples from
  `paths.tagged_artefact(u, ...)` and `_step_label(...)`. No literal
  `ROOT / "results_mid" / "metrics" / ...` path remains in `run_all.py`.

  **THE CORRECTION IS RECORDED RATHER THAN MADE SILENTLY.** This bullet previously
  read "deriving from the registry is separate work and is not a line in step 8",
  describing as pending the work that **Step 8, `a32ef28`, two bullets above it in
  this same document, had already performed**. The doc contradicted itself on the
  page, and briefs were written from it. That is the failure this block's new
  verification line exists to catch.

  Still true from the old bullet, and still worth knowing: the claim that the
  literal path shape is what keeps `check_pipeline_order` resolving the edge is
  wrong as written — `run_all.py` is never scanned, only `PIPELINE_ORDER`'s step
  scripts and their `STEP_HELPERS` are.

- **`results/make_combined_universes.py` — 2 of 3 done.** `DISPLAY` and `COLOURS`
  are `Universe` fields as of phase 2, `d3ae8ec`, and so is `LIQUIDITY`, which this
  block previously called editorial. The file says so at its own line 90: "THE
  DISPLAY NAME AND THE COLOURS ARE REGISTRY FIELDS -- phase 2, 2026-09-16", and
  again at line 140 for `LIQUIDITY`.

  **Genuinely remaining:** the `FILES` block, built locally at line 239, and
  `PAIR_CHART = ("n100", "mid")` hand-written at line 159 — the latter already
  guarded by an `_unknown_pair` check against `REGISTRY`, so it fails loudly on an
  unknown tag rather than silently.

  Still true: step 7 did **not** reduce this file's count — it went 14 to 16,
  because the registry lookups that replaced the config imports are themselves
  named sites. What step 7 removed was the second DEFINITION of a universe's paths,
  not the hand-written tags.

- **`PIPELINE_ORDER` — NOT STARTED, and the count is 8, not 4.** `run_all.py:188-196`
  spells out both universes:

  ```
  ("STEP 10a", "build_scores.py",    "mid"),   ...   ("STEP 10d", "make_chart.py", "mid"),
  ("STEP 10e", "build_scores.py",    "n100"),  ...   ("STEP 10h", "make_chart.py", "n100"),
  ```

  The old bullet's "4 `PIPELINE_ORDER` rows (10a–10d)" was a **per-universe** figure
  and reads as a total. There are eight rows, four per universe.

- **The `results/` move — 26 probes out of `results/`, 58 path-form citations
  across 23 of them.** Sequenced after the collapse; see the paragraph above.

  **THESE TWO FIGURES ARE UNCOUNTED, carried unchanged from the 2026-09-16 block
  and NOT re-verified on 2026-09-17.** The three bullets above were re-counted file
  by file; this one was not, and it must not inherit their standing by sitting
  beneath them. Re-count before using it.

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
- **`87ba029` EARNED ITS KEEP, AND THIS IS THE RECORD OF IT.** It was the ungated
  commit let through on argument: it made the `PROVENANCE` verdict name the fields
  that actually moved instead of all four excluded ones. On 2026-09-16 a post pass
  started clean and was dirtied while its first cell ran; the pass reported PASS,
  and the ONLY sign was that one cell said `git_state.commit` and the other said
  all four. Without that commit both cells would have printed all four and the
  invalid pass would have been indistinguishable from a valid one. The gate is now
  enforced by `gate_compare.dirty_stamp()` rather than by that detail line being
  read carefully — but the detail line is what found it.
- **Documentation-only commits are not gated and are not listed individually**
  — `9a5a1ed`, `77d2a54`, `d90e1c1` and this paragraph change no code. Stating that
  once is what keeps this note finite; stating each would make it a changelog.

### WHAT IS DEFINED NEXT — written before any of it is started

**THE RULE, AND IT IS WHY THIS BLOCK EXISTS.** A step whose definition lives only
in a conversation does not exist, and steps 1 and 8 spent six days proving it.
Everything below was written down before the first line of its code.

**ADDING A UNIVERSE COST 14 HAND-WRITTEN ENTRIES ON THE MORNING OF 2026-09-16**,
measured by registering a throwaway universe and wiring it until
`registry_coverage_check.py` passed: 1 `REPORT_ORDER` + 1 `DISPLAY` + 1 `COLOURS`
+ 1 `LIQUIDITY` + 1 `FILES` block + 4 `PIPELINE_ORDER` rows + 5 `REQUIRED_INPUTS`
tuples.

**IT COSTS 7 NOW.** Step 8 (`a32ef28`) derived the 5 `REQUIRED_INPUTS` tuples;
Phase 2 (`d3ae8ec`) moved `DISPLAY`, `COLOURS` and `LIQUIDITY` into the row itself,
taking it to 6; wiring `tax_report.py` on 2026-09-17 added a fifth
`PIPELINE_ORDER` row per universe, taking it to 7. Its `REQUIRED_INPUTS` entry
costs nothing — step 8's comprehension emits it from `REGISTRY` like the rest.
What remains is **1 `REPORT_ORDER` + 1 `FILES` block + 5 `PIPELINE_ORDER` rows**,
and of those the `FILES` block is Phase 3, deferred below. **The floor is 5**, and
those five are decisions rather than duplication — every one refuses loudly if
skipped, `REPORT_ORDER` and `PIPELINE_ORDER` through `registry_coverage_check`,
the three former tables now through the `Universe` constructor itself.

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

#### PHASE 2 — **LANDED, `d3ae8ec`.** `DISPLAY`, `COLOURS`, `LIQUIDITY` became registry row fields. **−3 of 9, leaving 6.**

`results/make_combined_universes.py` carries three per-universe tables. Each moves
to a `Universe` field with **no default**:

| table | field | what it holds |
|---|---|---|
| `DISPLAY` | `display_name` | the chart title's spelling — `"NIFTY 100"`, not `index_name`'s `"NIFTY100"` |
| `COLOURS` | `chart_colours` | the six-colour tuple, slots 0–5 = v2, v1, buy&hold, index, v3, v4 |
| `LIQUIDITY` | `liquidity_note` | the measured fill-size note, or `None` for not measured |

**THE DATACLASS KNOCK-ON IS THE PRIZE, NOT THE −3.** As fields with no default, a
row that omits one fails at construction with a `TypeError` naming the field.
**Three of `registry_coverage_check.py`'s tables stop being NEEDED rather than
being silenced** — a field with no default cannot be forgotten, while a checker has
to remember to look. The checker must SAY its table count dropped and why, not
quietly shrink: a check that covers less than it did is the thing this repository
keeps catching.

`LIQUIDITY`'s `NOT_MEASURED` declaration survives the move as `liquidity_note=None`
— presence compulsory (the constructor sees to it), absence declarable.

**CORRECTING SOMETHING I WROTE HERE ON 2026-09-16.** This section previously said
`LABELS = {"n100": "NIFTY 100", "mid": "MIDCAP150"}` "appears verbatim in 16 files"
and that "one `display_name` field retires all of them". Both halves are wrong, and
counted rather than argued:

- **14 files carry it verbatim. Two carry `{"n100": "Nifty 100", "mid":
  "MidCap150"}`** — different case, different spelling. 16 files have a `LABELS`
  dict; they are not 16 copies of one string.
- **The probes have a standing reason to keep theirs local, and it is written
  down.** `results/purge_mode_probe.py` says: sourcing labels from the registry
  "would rewrite committed artefacts — `diagnostics/topn_verdict.txt` among them —
  for a cosmetic reason. Labels are presentation and stay local; paths are facts
  and do not."

**So the probes are OUT of Phase 2's scope.** Phase 2 is the three tables in
`make_combined_universes.py`, which is a load-bearing step, and nothing else.

**GATE.** The artefact checksum on `mid all research` and `n100 all research`, both
passes clean — display names, colours and the liquidity prose all reach the
combined PNG, so **this is the phase that can move a published figure.** Plus the
edge inventory diff, the naming gate, and `registry_coverage_check` reporting its
own reduced table count.

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
the last date present in the deleted universe's files. See RETIRED_UNIVERSES.md
section 6 in git history (`git show 50562ed:RETIRED_UNIVERSES.md`).

## 3. The price data: 876 MB, untracked, from the repository owner

```
data/raw/Final_Without_Survivorship_Data/     1,392 files   876 MB   eight folders, one per universe
```

The folder names, file counts and index file of each universe are in README.md,
"The price data", and every file's SHA-256 is in `data/RAW_DATA_SHA256.txt`
(`python3 check_data.py` verifies a copy). A universe's constituents are the CSVs
in its folder (`universes/registry.py`, each row's `raw_data_dir`), so an extra or
missing file changes the universe. Other folders the owner's copy may hold under
`data/raw/` (`MidCap150/`, `nifty100_benchmark/`, `EQUITY/` and others from earlier
vendors) are read by no pipeline step.

Every price row carries its own provenance in columns nothing in the pipeline
reads: `source` (the vendor), `exchange`, `_dq_score` (0.62 to 1.00),
`_gap_filled` (the vendor's synthetic-row flag), `_merged_at`, and the fetch
window. `KNOWN_ISSUES.md` records the consequences of `_dq_score` and
`_gap_filled` going unread.

Column contract: `date, open, high, low, close, adj_close, volume, open_interest`
at minimum. `adj_close` is the canonical price and is resolved into `close` at the
single load boundary in `engine_core.build_panel`.

## 4. The symlink farms and the panels -- derived, under cache/, never shipped

Since 2026-09-23 each universe's constituent farm is `cache/<tag>/constituents/`,
built on demand by `Universe.prepare_data_dir()` -- hard links to the source CSVs
since 2026-09-24, copies where a hard link cannot be made, relative symlinks for
one day before that -- and its score and raw panels are
`cache/<tag>/v_<tag>_expanding.parquet` and `cache/<tag>/raw_panel_<tag>_20.parquet`
(CSV until 2026-09-24). `cache/` is gitignored. Copying `data/`
alone is enough for a second machine: nothing under `data/` is a link any more.
Before that date the farms were absolute symlinks under `data/raw/` and a copied
tree pointed back at the source checkout.

## 5. Tooling data — ships, but the pipeline does not read it

```
data/reference/*.csv                  3 files, 9.6 MB   membership tooling
```

Not on the pipeline path. The point-in-time membership files that
`SURVIVORSHIP_MODE = "pit"` would read are not in the repository; no pipeline step
sets that mode, and the default is `"static"`, today's constituents backfilled.

## 6. The environment

**Python 3.12.13.** A hard floor of 3.12 is set by `nautilus_trader`; the exact
patch release is what the byte-identical cross-platform runs used.

**Every direct dependency is pinned exactly (`==`) in `requirements.txt`**, and
`installed_versions.txt` is `pip freeze` of a venv built from it, passed as a
constraints file so the transitive versions are fixed too:

```
./venv/bin/python -m pip install -r requirements.txt -c installed_versions.txt
```

Every score comes from `lgb.LGBMRegressor`, and a one-bit float difference is
enough to reorder near-tied names at the `TOP_N=8` boundary, so a range would let
two machines produce different numbers from the same file.

**The panels are under `cache/`, not `/tmp`, since 2026-09-23.** Two checkouts on
one machine shared `/tmp`, and the second read the first one's panels.

**Nothing else outside the repository is read.** No absolute paths, no home
directory, no environment variable is ever read — `PYTHONHASHSEED` and the
thread-count caps are set by the code, never consulted from outside.

## 7. First run

```bash
python3 check_data.py                                    # the data matches the manifest
python3.12 -m venv venv
./venv/bin/python -m pip install -r requirements.txt -c installed_versions.txt
./venv/bin/python run.py --list                          # resolved plan, runs nothing
./venv/bin/python run.py --universe midcap50 --arm v2    # the README's first command
```

These are README.md's steps. Every step runs in `sys.executable`, so the launching
interpreter propagates to every child.

**The first run of a universe builds its score panel, which dominates**: midcap50
took 6.5 to 8.5 minutes on a Mac mini M4, nifty500 about 75 (README, "How long it
takes"). Once a panel exists under `cache/` and its content key matches the source
CSVs and the code, a repeat run of one combination takes tens of seconds.

## 8. What is not settled, and what you should not assume

- **SURVIVORSHIP IS PERMANENT, NOT OUTSTANDING. Decided 2026-09-16.** It was
  recorded as "deferred with a known next step": acquire price history for the
  **186 dropped names** that `full_100.csv` / `full_150.csv` already enumerate.
  **There is no vendor access and none is coming.** The price data is fixed at
  2026-06-08 and no further acquisition is possible, so those 186 names will never
  arrive and the point-in-time membership work cannot be completed.
  **This is now a standing property of every number this repository produces, not
  a task on a list.** Both universes are today's index constituents backfilled;
  names that left before the window ended are absent from every result, every
  chart and every comparison. What was measured about it stands and is not
  re-litigated: the bias runs in **both** directions (PIT membership took midcap150 v1
  from +19.03 to +9.68; adding synthetic dropped losers took it to +30.11 or
  +5.10 depending on whether the model sees them), v2's risk advantage survives
  PIT untouched, and **there is no point-in-time membership for nifty100 at all** —
  `rebuilt_100.csv` is the MidCap150, overlapping nifty100 by 8 of 100 names.
  Do not read any figure here as survivorship-corrected, and do not re-open this
  as work.
- **Cross-machine reproducibility.** Established on 2026-09-24 for macOS arm64,
  Linux arm64 and Linux amd64 (README, "Running it"). Windows is untested.
- **Combination coverage.** Of roughly 540 nominal selection combinations
  (universe × arm × cadence × profile × steps), a small minority have ever been
  run. Nine of fifteen arm subsets have never been exercised; the `tradeable`
  profile appears in two runs out of fifty-five. Three separate axes have now
  produced the same class of bug — a hardcoded name where a selection-derived one
  belonged — on the cadence, arm and profile axes in turn.
- **The numbers themselves.** `KNOWN_ISSUES.md` is long and it is the honest
  half of this repository. Read it before the README.
