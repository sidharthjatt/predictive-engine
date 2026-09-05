# Known issues

Defects that are recorded but not fixed. Anything found and left alone belongs
here, with what it is, where it lives, and what a reader would wrongly conclude
because of it. Nothing in this file is a plan; it is a list of things that are
currently wrong.

---

## The documented commands are not verified against the machine they run on

Found 2026-08-30 by the `run_all.py` audit, and found AGAIN on 2026-09-02 by
accident while answering an unrelated question about which interpreter the
pipeline spawns. The specific instance below is now fixed. **The class is open,
and the rediscovery is the finding.**

**THE INSTANCE.** `run_all.py`'s docstring told the reader, three times, to run
`python3 run_all.py`. On the machine every published number was produced on,
`python3` is `/opt/homebrew/opt/python@3.11/bin/python3.11`, and the project runs
under `./venv/bin/python` at 3.12.13. **The documented command fails, twice over,
and both failures have the same cause — the wrong interpreter:**

| | `python3` (3.11.15) | `./venv/bin/python` (3.12.13) |
|---|---|---|
| `lightgbm` — the model, imported at `engine_core.py:42` | **missing** | 4.6.0 |
| `openpyxl` — the membership workbooks | **missing** | 3.1.5 |
| Python version against `nautilus_trader`'s **3.12 floor** | **3.11, below the floor** | 3.12.13, above it |
| everything else on the pipeline path | present | present |

The 3.12 floor is not an inference: `requirements.txt` has warned about it in its
own header the entire time, at the top of the same file that omitted `lightgbm`.
So the documented command was below a floor the documentation itself stated.

**AND THE WRONG INTERPRETER PROPAGATES.** `run_all.py:230` spawns every step with
`subprocess.run([sys.executable, ...])`. There is no fallback: whichever
interpreter is typed at the command line becomes the interpreter for all 32
steps. The launch command is load-bearing, which is what makes a wrong one in the
docstring a real defect rather than a typo.

**Fixed 2026-09-02**, in `run_all.py`'s docstring: the command now names
`./venv/bin/python` explicitly and states why the interpreter matters.

**WHY THIS IS FILED FOR THE CLASS AND NOT FOR THE TYPO.**

**It had already been found, written down, and left in place.**
`diagnostics/PIPELINE_AUDIT.txt`, dated 2026-08-30, records it under the heading
*"THE FIRST BREAK IS AT STEP 1 OR STEP 2, AND IT IS IN THE DOCUMENTATION"*, names
the cause exactly, and concludes *"It must be launched as ./venv/bin/python
run_all.py"* and *"This one is a reading-level certainty, not a guess."* **Three
days later the docstring still said `python3`, and the defect was rediscovered
from scratch by someone asking a different question.** Recording a defect in a
diagnostic is not the same as fixing it, and nothing connected the two.

**NOTHING CHECKS ANY OF THE OTHERS.** No test, no pipeline step and no audit runs
a documented command to see whether it works. Every command in this repository is
prose, verified by eye at the moment it was typed and never since. The instances
that remain, all of them still saying `python3`:

| where | command | status |
|---|---|---|
| `README.md:269` | `pip install -r requirements.txt`, then `python3 run_all.py` | **FIXED 2026-09-02** — now `./venv/bin/python run_all.py`, with the `sys.executable` mechanism and both failure modes stated |
| `config.py:242` | error message: ``Run `python3 run_all.py` to build them`` | **FIXED 2026-09-02** — now names the venv interpreter and says why it is not interchangeable. Rendered and read back rather than assumed correct |
| `run_all.py:81` | comment: `python3 results/build_scores_n100.py` | describes the determinism gap, not an instruction to follow |
| ~10 module docstrings, e.g. `results/engine_core.py:113`, `results/make_trading_calendar.py:29`, `results/validate_breadth_live.py:52-53` | `python3 results/<script>.py` | unverified; each fails the same way if the venv is not active |

**AMENDED 2026-09-02.** The two rows above read "still wrong, unfixed" when this
entry was written, because the task that found them was scoped to `run_all.py`
and changing files outside the task at hand needs asking first. Both were fixed
later the same day, on the reasoning that an error message handing the reader a
failing command is worse than the churn of changing it. **The original wording is
replaced rather than struck through, because it described a state that lasted
hours and no figure depends on it; the dating above is the record.**

**The remaining two rows are unverified, not fixed.** Nothing in this project runs
a documented command to see whether it works, which is the entry's actual
subject and is unchanged.

**Consequence.** A reader following the README on this machine gets
`ModuleNotFoundError: No module named 'lightgbm'` at STEP 1, from a project whose
own requirements file did not list lightgbm until 2026-09-02. Neither the error
nor the documentation points at the interpreter, which is the actual cause.

**Not fixed, as a class.** The fix is not more careful proofreading — that is what
failed twice. It would be a check that executes what the documentation claims:
at minimum, a step that asserts the running interpreter can import every module
in `requirements.txt`, and fails by name if it cannot. Nothing like that exists,
and designing it is out of scope for the pass that found this.

---

## requirements.txt does not install what the pipeline imports

Found 2026-09-02 by a fresh-checkout audit. **FIXED 2026-09-02 — see the closure
block at the end of this entry. The text below is the defect as found and is left
unedited.**

**`lightgbm` is absent from `requirements.txt`.** It is the model. Every score in
this project comes from `lgb.LGBMRegressor` at `engine_core.py:401`, and nothing
in the requirements file installs it.

| package | imported by | in requirements? |
|---|---|---|
| **`lightgbm`** | `engine_core.py`, `audit_leakage.py`, `stability_test.py`, `test_feature_pruning.py`, `diagnose_alpha.py` | **no** |
| **`scipy`** | `reality_check.py` (run_all STEP 6) | **no** |
| **`scikit-learn`** | via LightGBM's sklearn API | **no** |
| **`openpyxl`** | the `.xlsx` membership workbooks | **no** |
| `pandas`, `numpy`, `matplotlib`, `joblib`, `pyarrow`, `nautilus_trader` | throughout | yes |

**It also pins three packages the pipeline does not import.** `torch`,
`gymnasium` and `stable-baselines3` are required by the file and used by nothing
in `run_all.py`. The header describes a "DT + Attention-GRU + TD3" project —
**the file documents a previous incarnation of this project**, not the current one.

**Consequence.** `pip install -r requirements.txt` followed by `python3 run_all.py`
fails at STEP 1 with `ModuleNotFoundError: No module named 'lightgbm'`. Nothing in
the file or the run command warns of it.

**Not fixed.** Adding four packages is trivial; deciding what to pin them AT is
not, and it interacts with the reproducibility limit recorded above — an
unpinned LightGBM version is one of the reasons the headline is not reproducible
across machines.

**CLOSED 2026-09-02. `requirements.txt` was rewritten from the code.**

**How the list was derived, so it can be re-derived rather than trusted.** Every
script in `run_all.py`'s `PIPELINE_ORDER` was parsed with `ast` and its local
imports followed transitively — 32 steps, 41 modules reached — and the
third-party names collected. The result: `joblib`, `lightgbm`, `matplotlib`,
`nautilus_trader`, `numpy`, `pandas`, `scipy`.

**Two requirements do not appear as an import statement anywhere and would have
been missed by that scan alone.** Both are now listed with the reason in place:

- **`scikit-learn`.** `lgb.LGBMRegressor` is defined in `lightgbm.sklearn`, and
  lightgbm 4.6.0 declares scikit-learn only as an EXTRA
  (`scikit-learn>=0.24.2; extra == "scikit-learn"`), so installing lightgbm does
  not bring it in. Verified against the installed distribution's metadata.
- **`pyarrow`.** STEP 16 `nautilus/nt_export_scores.py:73,78` calls
  `df.to_parquet` and `pd.read_parquet`; pandas needs a parquet engine for both.

**`torch`, `gymnasium` and `stable-baselines3` were removed, and the removal was
checked rather than assumed.** A grep for `import torch`, `from torch`,
`import gymnasium`, `from gymnasium` and `stable_baselines3` across every `.py`
in the repository outside `venv/` returns **nothing**. The only two files in the
project that mention any of the three are `requirements.txt` itself and this
file.

**The header described a different project and now describes this one.** It read
"DT + Attention-GRU + TD3 + Nautilus"; that is the previous incarnation of this
repository and is the reason a missing `lightgbm` went unnoticed in a file whose
own title did not mention the model.

**`lightgbm` is pinned EXACTLY at 4.6.0, and the other packages are not.** The
pin is not a style choice: the published headline is the output of one specific
version's split arithmetic, and a one-bit float difference is already known to
move n100 v2 CAGR by 0.66 points — see *"The headline is not reproducible from
the artefacts on disk to better than about a point"* above. A floor would not
preserve that; a minor-version bump is free to change split behaviour.

**`openpyxl` is listed but marked as NOT on the `run_all.py` path.** It is the
engine `pandas.read_excel` uses in `results/extract_membership.py` and
`results/repair_membership.py`, which are survivorship tooling and are not in
`PIPELINE_ORDER`. `run_all.py` completes without it.

**A provenance block was added recording the versions the current published
numbers were produced under** — Python 3.12.13, lightgbm 4.6.0, scikit-learn
1.9.0, numpy 2.2.6, pandas 2.3.3, scipy 1.18.0, matplotlib 3.11.0, joblib 1.5.3,
pyarrow 24.0.0, nautilus_trader 1.228.0, openpyxl 3.1.5. **It is provenance, not
a pin, and it does not establish cross-machine reproducibility** — installing
those exact versions is necessary for reproducing the headline, not demonstrably
sufficient. Same-machine determinism was verified on 2026-09-02; nothing
equivalent has been run on a second machine.

**WHAT IS STILL NOT FIXED, AND IT IS THE HALF THAT MATTERS.** Nothing verifies
that this file is correct. It was wrong for as long as this project has existed,
and it was found by reading rather than by any check. `pip install -r
requirements.txt` succeeding still does not establish that `run_all.py` will run.
See *"The documented commands are not verified against the machine they run on"*
above, which is where that gap is recorded.

---

## The price data is not in this repository, and no source for it is recorded

Found 2026-09-02 by the same audit. Open. Recorded, not fixed.

`.gitignore` excludes `data/raw/*` — roughly 396 MB of vendor OHLCV CSVs — with
six small exceptions, none of which is price data. **A fresh clone gets ten
tracked files under `data/`**, all reference material: the trading calendar, the
symbol-rename map, the press-release manifest, the circular index, three
membership workbooks and one survivorship CSV.

| directory | files on disk | tracked | needed by |
|---|---|---|---|
| `data/raw/nifty50` | 58 | **0** | STEP 0, STEP 1 |
| `data/raw/Development_data_files` | 74 | **0** | STEP 8 |
| `data/raw/MidCap150/clean` | 149 | **0** | STEP 10a |
| `data/raw/nifty100_benchmark` | 100 | **0** | STEP 10e |

`.gitignore` states the position itself: the files are *"excluded for size, not
for irrelevance — the project cannot run without them, so they must be restored
from the backup archive, not from this repository."*

**THERE IS NO FETCH SCRIPT AND NO NAMED SOURCE.** The only downloader in the
project, `results/extract_membership.py`, retrieves NSE press releases for the
survivorship work — not prices. No file records where the OHLCV data came from,
how to obtain it again, or what "the backup archive" is. The vendor columns
(`source=kite`, `_dq_score`, `_gap_filled`, `_merged_at`) indicate a
pre-processed private extract rather than a public download.

**Consequence.** A clone cannot run, and cannot be made to run from anything the
repository contains. A copy of the working directory can, because it carries the
untracked data — so "clone" and "zip" are different artefacts with different
capabilities, and nothing states which one is intended to be shared.

---

## STEP 0 couples the live universes to the retired 58 universe

Found 2026-09-02 by the same audit. Open. Recorded, not fixed.

**Diagnosed in:** `diagnostics/PIPELINE_AUDIT.txt` section 8(1), **dated
2026-08-30**, which calls it *"THE STRONGEST SINGLE ARGUMENT AGAINST THE SPLIT AS
PROPOSED"* and states it *"must be resolved in any spec"*. Still open as of
2026-09-02.

`results/make_trading_calendar.py:42` sets

    SOURCE_DIR = config.RAW_DATA_DIR / "nifty50"

so the NSE trading calendar is derived from the **retired 58 universe's** raw
files. It writes `data/nse_trading_calendar.csv`, and
`engine_core._load_calendar()` raises `FileNotFoundError` if that artefact is
absent — **for every universe, including mid and n100**.

The calendar exists for a measured reason: 70 of 148 MidCap150 source files carry
rows on NSE holidays, putting 237 phantom dates into the mid union index, 107 of
them inside the backtest window. Deriving the calendar from mid itself is
therefore not viable, and the script's own docstring says so.

**Consequence, stated precisely.** `data/nse_trading_calendar.csv` **is tracked**,
so a checkout has one and `build_panel` will not raise. What requires the retired
universe is *regenerating* it — and it must be regenerated whenever the price data
extends, which is exactly when the live universes' window next moves. **So a
live-universes-only run is possible from the shipped calendar but not
maintainable without the 58's data.**

This also constrains any future split of the pipeline into live and archive
halves: STEP 0 cannot simply move to the archive side. Recorded in
`diagnostics/PIPELINE_AUDIT.txt` section 8 as the strongest argument against that
split.

**AMENDMENT, 2026-09-02. THE COUPLING WAS MEASURED AND IT IS NOT TRIVIALLY
REMOVABLE.**

The obvious candidate for decoupling — derive the calendar from a live universe
instead — was measured against n100. `SOURCE_DIR` was pointed at the n100 raw
data, a second calendar was built to a scratch path, and it was compared against
the tracked 58-derived artefact over the shared range. **The tracked artefact was
not written**: SHA256 `9ce2a4bd…f96f0` before and after.

    shared range 2000-01-03 .. 2026-06-08
    n100-derived    6,811 dates
    tracked-58      6,574 dates
    n100-only         237
    tracked-58-only     0

**THEY ARE NOT IDENTICAL, AND THE DIRECTION IS ONE-WAY.** The n100-derived
calendar carries **237 dates the 58-derived one does not**, and **not one** date
goes the other way. **107 of the 237 fall inside the 2019-01-01 to 2026-05-29
backtest window.** They span 2009 to 2026, 8 to 18 per year, every year, and none
is a weekend. Measured on both readings of "the n100 data" — the 100-file
benchmark directory and the 99-file constituents directory that
`build_scores_n100.py` actually scores — which agree with each other on all 237.

**NOTED WITHOUT BEING TESTED: THE 58 MAY BE ACTING AS A FILTER RATHER THAN MERELY
AS A SOURCE.** `results/make_trading_calendar.py`'s own docstring reports the same
two counts for MidCap150 — *"237 phantom dates into the mid union index (107
inside the backtest window)"* — and calls them phantom. The n100 comparison
produces 237 and 107. **Whether the two sets are the same dates is UNTESTED.** The
coincidence is recorded because it is the obvious next question, not because it
has been answered, and it must not be read as an established identity.

**NOTHING HERE ESTABLISHES WHICH SIDE IS CORRECT.** No external NSE calendar was
consulted. The 58's cleanliness is an assumption stated in the script's docstring
— *"58 large caps that trade every session"* — and this measurement does not test
it against any independent source; `DDQ_Latest/config/trading_calendar.yaml` was
rejected as an authority earlier and was not revisited. The measurement
establishes that the two disagree, by how much, and in which direction. It does
not establish that the 237 dates are spurious, nor that the 58 is complete.

**ALSO NOT ESTABLISHED.** That agreement over the shared range would imply
agreement outside it — the benchmark-directory reading extends to **2026-06-22,
fourteen days past the tracked calendar's end**, and those 10 dates sit outside
the comparison entirely. That anything can be predicted about a future data
delivery, which is the case that matters, since the calendar needs regeneration
exactly when the data extends. And what substituting a 237-date-larger calendar
would do to any panel, score or published figure — `build_panel` filters every
panel by this artefact and that consumer was not exercised.

**No decoupling is proposed and no production path was changed.** The entry stays
open, and the measurement narrows it: the coupling is not removable by simply
re-pointing `SOURCE_DIR`, because the two sources do not agree on what a trading
day is.

**SECOND AMENDMENT, 2026-09-03. THE OBVIOUS FIX WAS SPECIFIED, MEASURED AND
REFUTED. READ THIS BEFORE REACHING FOR A COVERAGE THRESHOLD.**

The natural repair for the 237-date gap above is a coverage filter: build from the
selected universe and drop any date carried by fewer than some fraction of the
files active that year. **It does not work, and it is not a matter of picking a
better fraction.**

It looked sound, and that is why it was specified: over 2019-01-01 to 2026-05-29 a
50% threshold reproduces the tracked 58-derived calendar **exactly**, identical
sets, both universes. **That range is 1,836 of ~6,574 dates.** Extended to the full
range the files cover, n100 comes out **2 dates short** and mid **22 dates short** —
all pre-2019, all one-directional, the filter dropping dates the calendar has.

**No threshold can fix it.** A threshold T reproduces the calendar only if
`max(coverage of excluded dates) < T ≤ min(coverage of included dates)`. Measured
over the full range that requires `24.24% < T ≤ 13.85%` on n100 and
`47.30% < T ≤ 4.35%` on mid. **Both intervals are empty**; the groups overlap by
10.40 and 42.95 points. The binding cases are calendar dates with very thin
coverage — 2017-12-02 (Sat, 4.35% on mid), 2003-03-22 (Sat, 13.85% / 4.92%),
2017-04-04 (Tue, 33.33% / 37.39%), and eighteen consecutive January 2003 sessions
at 47.54% on mid.

**It would have moved published numbers.** The missing dates are pre-2019 and so
are training rows rather than scored rows, but `build_panel` filters the whole
panel and training reaches back to 2001. `experiments/EXPERIMENTS.md` entry 28
measured a 0.01% training-row change moving n100 v2 CAGR by 0.54 points.

**None of this says the 58-derived calendar is right about those 24 dates.** No
external NSE source has been consulted; three of the binding dates are Saturdays
and whether they were genuine sessions is untested. And it does not say decoupling
is impossible — it refutes **one** design.

Full record: `experiments/EXPERIMENTS.md`, *"Decoupling the trading calendar by a
coverage threshold — REFUTED BEFORE IMPLEMENTATION"*. Spec, marked BLOCKED with the
refutation as PART 8: `experiments/CALENDAR_DECOUPLE_SPEC.txt`. Measurement:
`diagnostics/calendar_coverage_probe.txt`, script
`results/calendar_coverage_probe.py`.

## There are FIVE reimplementations of the backtest, not two

**Diagnosed in:** `diagnostics/PIPELINE_AUDIT.txt` section 4, **dated
2026-08-30**, which corrected the count from four to five by finding
`make_cash_series.py:42-70`. The count was repaired in this file; **the five
implementations themselves are unchanged as of 2026-09-02.**

Found 2026-08-28 as two. Corrected to four on 2026-08-29, then to **five** later
the same day by the `run_all.py` audit. **Four as of 2026-09-04**: the retired
audit engine was deleted in S2 (commit `9ced314`), after its output was confirmed
to have no consumers. The other four stand.

The count going DOWN does not retire this entry. The lesson below is about how
the count was arrived at, not about its value, and deleting one dead engine does
nothing about the three live ones.

**The count has now been wrong twice, in the same direction.** It was titled "The
validated engine and the shipping engine are two different implementations", then
"four", and both were undercounts found by looking rather than by any check. That
is the point of this entry: a repository that believes it has two engines does not
go looking for the third, and one that believes it has four does not look for the
fifth. **Treat five as a floor.**

| | function | used by |
|---|---|---|
| validated | `engine_core.backtest` | the four-test suite, `validate_sizing.py`, the jackknife scripts, `mid_topn_test.py`, `param_surface.py` |
| shipping | `test_exposure.backtest_exposure` | `engine_v2_final_*.py`, every published v1/v2/v3/v4 number, `validate_breadth_live.py`, the Nautilus port's reference |
| port reference | `nt_attribution.py`'s inline book | `nt_verify.py`, the 92-of-92 correctness gate |
| ~~retired audit~~ | ~~`results/make_stats_both.py`'s inline book~~ | **DELETED 2026-09-04 (S2, `9ced314`)** — had no consumers; see below |
| cash series | `results/make_cash_series.py:42-70` inline book | **`run_all.py` STEP 13 → STEP 14** — see its own entry below |

The port reference is a deliberate re-implementation: `nt_verify` compares the
Nautilus port against it, and a reference that imported the engine it is checking
would prove nothing. It is counted here because it is a fourth place the rules are
written down, not because its existence is a mistake.

`make_stats_both.py` and `make_cash_series.py` were counted for the opposite
reason: nothing justified either, and **both had already drifted** — the same
`CASH_Y = 0.06` in each. The difference between them was that
`make_stats_both.py`'s output was dead and `make_cash_series.py`'s is not, which
is why only the first one could simply be deleted. **`make_cash_series.py`'s 6%
is still there** (`frozen/make_cash_series.py:84`) and still reaches a consumer.

Arguably six: `nt_strategy.py` expresses the same rules a third time in Nautilus
terms. It is listed separately because it is the artefact *under test* — its
agreement with the reference is what `nt_verify` measures.

Full inventory and method: `diagnostics/PIPELINE_AUDIT.txt` section 4.

### The first two are the pair that matters for what is validated

**"Inverse-vol sizing was validated" and "v2 is what ships" are claims about
different code.** They are not the same backtester and they do not agree.

They differ structurally, not just numerically. `engine_core.backtest` sizes
against `avail = cash * 0.98` (`engine_core.py:308`) and has no breadth mode at
all. `test_exposure.backtest_exposure` sizes against
`invest_val = port_val * exposure * 0.98` (`test_exposure.py:106`), where
`port_val` includes the value of existing holdings.

**Measured disagreement on the 58, same universe, same sizing:** the validation
engine's inverse-vol arm reports 26.42% CAGR (`results/metrics/FINAL_comparison.csv`)
while `v2FINAL_equity.csv`'s always-invested inverse-vol column reports 24.62%.
**1.80 CAGR points apart.** That gap is by design and is not a bug in either file.

**Consequence, stated plainly.** The four-test validation suite — T1 baseline,
T2 seed robustness, T3 sub-period, T4 vol-window sensitivity — tests
`engine_core.backtest`. It does **not** test the engine that produces the
published numbers. So:

- The 2026-08-28 result "n100 passes 4 of 4, mid passes 1 of 4" is a statement
  about the validation engine, not about the shipping engine.
- `validate_sizing.py` already records that it cannot gate its baseline against a
  production artefact for exactly this reason. That limitation was written down;
  the broader consequence — that the validation does not cover what ships — was
  not, until then.

**CLOSED 2026-09-04 by `results/validate_engine.py`.** The four tests now run
against `test_exposure.backtest_exposure` — the engine that produces the
published numbers — and record their verdicts in
`diagnostics/validate_engine_{58,mid,n100}.txt`. The claim above that "no test
anywhere compares the two implementations directly" no longer holds, and neither
does "the validation does not cover what ships". `engine_core`'s own
`FINAL_val_*.csv` are untouched and still describe `engine_core.backtest`, so
both sets of verdicts exist side by side and each says which engine it is about.

**The shipping engine's verdicts are not the validation engine's, and the
difference is the point of this entry:**

| | 58 (retired) | mid | n100 |
|---|---|---|---|
| shipping engine, 2026-09-04 | **4 of 4** | **0 of 4** | **4 of 4** |
| mean book / trades | 8.15 / 734 | 7.98 / 845 | 8.01 / 831 |
| Sharpe, equal → invvol | 1.24 → 1.24 | 1.87 → **1.81** | 1.45 → 1.62 |

mid goes from "1 of 4" on the validation engine to **0 of 4** on the engine that
ships, and each of the four fails for its own reason rather than from one common
cause — T1 by 0.02 on mean book (7.98 against a [8, 16] range), T2 on 0 of 3 seed
sets, T3 in the 2019-2022 half, T4 on the vol window. The Sharpe column says why:
**on mid, inverse-vol does not beat equal-rupee** — 1.87 → 1.81 — so the tests
that ask "does inverse-vol still win" correctly answer no. Corroborated
independently on 2026-09-05: an equal-weight arm run through `run.py` on mid
returns 50.73% CAGR against inverse-vol's 45.87%.

T1 was redefined for this engine and the redefinition is not cosmetic:
`engine_core`'s T1 asserted mean positions within 0.2 of `TOP_N`, which tested for
a slot cap the shipping engine does not have. Its book floats in
`[TOP_N, BUFFER]` by design. Applying the old T1 unchanged would have failed the
shipping engine for working correctly.

### The fourth one had drifted, on three constants at once — RESOLVED BY DELETION

**`results/make_stats_both.py` was deleted on 2026-09-04 in S2 (`9ced314`), after
its zero-consumer status was re-verified rather than taken from the 2026-08-29
grep below. Its three orphaned outputs were removed with it.** The analysis is
kept because it is the evidence the deletion rested on, and because the
`make_cash_series.py` entry further down is still open and refers back to it.

It reimplemented the backtest inline — it did not import `backtest_exposure` —
and it disagreed with production on three constants:

| | `make_stats_both.py` | everywhere else |
|---|---|---|
| `TOP_N`, `BUFFER` | **12, 24** (line 14) | 8, 16 |
| cash yield | **`CASH_Y = 0.06`** (line 15) | `CASH_YIELD = 0.0` (`test_exposure.py:61`) |

The divergence is visible on disk, same universe and same window: its
`v2_trades.csv` holds **1,193 fills against 883** in `daily_trades_74.csv`. The
74's own engine, `engine_v2_final74.py`, imports the real `CASH_YIELD` and prints
"Idle cash earns 0%", so the 6% is this script's alone.

It ran as **STEP 10 of `run_all.py`** (`run_all.py:275`), so it executed on every
full pipeline run. It is no longer in `PIPELINE_ORDER`; the pipeline is 31 steps.

**WHY IT WAS NOT URGENT, WRITTEN DOWN SO THE NEXT READER NEED NOT RE-DERIVE IT.**
It was retired-universe only. Its docstring said "58 & 74" but there was no 58
call — the sole invocation was `make_stats_both.py:115`, against the 74. It wrote
exactly three files, all into `results74/metrics/`, and it was the sole writer of
all three: `v2_trades.csv`, `v2_per_stock_signals.csv`, `trade_stats_74.csv`.
All three were removed with it.

**Nothing reads any of them.** Grep across `*.py`, `*.md`, `*.txt` and `*.json`
returns zero consumers; the only other appearances are `run_all.py` invoking it and
stale run logs echoing its own print line. **No figure in any document comes from
it** — none of its outputs (1,193 trades, 588 round trips, 63.6% win rate, profit
factor 2.9, Rs 1,46,612 total TC) appears in `README.md`, `HANDOFF_SUMMARY.txt`,
this file, `EXPERIMENTS.md`, or any diagnostics file. Verified by grep on
2026-08-29, statically, against the tree as it then stood.

So it has been generating figures at 12/24 for as long as the repository has
existed, and nobody has ever been shown one.

**IT WAS NOT A ONE-LINE FIX, AND THAT IS WHY IT WAS RECORDED RATHER THAN
CORRECTED — AND THEN DELETED.** Editing `12, 24` to `8, 16` would have left the 6%
cash yield in place and produced a **third** set of numbers, agreeing with neither
the current artefact nor the 74's official run. A real fix had to decide the cash
yield too, and it moves a retired universe's artefacts, which the freeze policy
governs. It was also a fourth engine: correcting its constants would not have
stopped it drifting again — only deleting it or making it import the shipping
engine would. **Deletion is the option that was taken**, which is available
precisely because nothing read its output.

**How it survived.** `TOP_N` and `BUFFER` are defined by literal in ten places with
no single definition, so nothing could have caught it. `config_n100.py:8` and
`config_mid.py:9` both *assert* "TOP_N=8, BUFFER=16" in prose while setting
nothing. That is what `experiments/TOPN_SPEC.txt` Part A addresses; note that
centralising the constant does **not** merge the five engines and does not by
itself fix this script.

**The Nautilus gate does not close this.** It proves the port matches
`nt_attribution`'s reference re-implementation, and that reference mirrors
`test_exposure`. Nothing in the chain reaches `engine_core.backtest`.

**Not fixed.** Recorded first because it was previously stated only in
conversation and appeared nowhere in the repository, which is the worse failure.
Any fix is a decision about which engine is authoritative, not a code change.

---

## An artefact was used three times without checking it was the one the code reads

Found 2026-09-02, by causing it three times in one session. Open.

**THE RULE THAT WAS BROKEN EACH TIME:** verifying the artefact *in hand* is not the
same as verifying it is the artefact the code will *reach for*. Every instance
below passed a real check — universe membership, column presence, file existence —
and every one still used the wrong object.

| # | what was assumed | what was true | cost |
|---|---|---|---|
| 1 | `raw_panel_*_cache.csv` carries `high`, `low`, `volume` | it carries 24 columns and none of those three; they are consumed during feature construction and not retained | a `KeyError` **after** the scoring loop discarded ~25 min of refits |
| 2 | the raw panel cache is the scoring input | `build_scores_*.py` scores the **in-memory** panel and merely writes that CSV as a by-product; the two differ by one unit in the last place | an identity gate failed after a **130-minute** 40-seed run; recovered only because the store had been persisted |
| 3 | rebuilding scores updates what the engines read | `build_scores_*` writes to `/tmp`; `run_all.py` promotes `/tmp` to the permanent caches **at the end of a run**, and that step was omitted | a 36-minute rebuild produced correct panels that nothing read; the headline was reported unchanged and had to be retracted |

**`config.require_cache` IS THE PROXIMATE CAUSE OF (3), AND IT IS DOCUMENTED.**
It resolves permanent-first:

    perm = _P(perm)
    if perm.exists():
        return perm

so a stale permanent cache silently wins over a fresh `/tmp` one. Its own
docstring describes exactly this hazard and lists three past failures from it.
**That function was read earlier in the same session and the precedence was still
not applied.** Reading a guard is not the same as reasoning about it.

**THE RULE, STATED SO IT CAN BE APPLIED.** Before using an artefact, establish
which file the *consumer* will open — not which file is newest, best-named, or
already loaded. Where a resolver like `require_cache` stands between producer and
consumer, the resolver's precedence is part of the answer.

**Not fixed.** No code change is proposed here. `require_cache`'s precedence is
deliberate and its docstring argues for it; the failure was in use, not in the
function. Recorded because three instances in one session is a pattern, and the
next one will cost another run.

## The headline is not reproducible from the artefacts on disk to better than about a point

Found 2026-09-02, by an identity gate failing. Open.

**`build_scores_{n100,mid,74,}.py` call `score_monthly` on the IN-MEMORY panel.**
They write `raw_panel_*_cache.csv` one line earlier and never score from it —
e.g. `build_scores_n100.py:44` writes the CSV, `:47` scores `raw`. So the CSV is a
by-product, not the scoring input, and nothing in the repository says so.

**The two differ by one unit in the last place.** Rebuilding the panel in memory
and differencing it against the CSV read back:

| | max abs difference | cells affected |
|---|---|---|
| every one of the 17 features, and `y_rank` | **4.441e-16** | **2,638,259** |

That is the smallest possible non-zero perturbation of a float64 — a single bit.

**It moves the headline.** Fitting the production 10 seeds on the CSV-read panel,
everything else identical:

| | from the CSV panel | recorded | offset |
|---|---|---|---|
| n100 v2 CAGR | 26.15 | 25.49 | **+0.66** |
| n100 v2 Sharpe | 1.92 | 1.88 | +0.04 |
| n100 v2 MaxDD | −17.67 | −18.64 | +0.97 |
| mid v2 CAGR | 29.93 | 30.22 | **−0.29** |

**The mechanism is not mysterious.** A last-bit change to a feature can flip a
LightGBM split decision; a flipped split changes a predicted score by up to
3.45e-02 (measured); a changed score reorders near-tied names at the TOP_N=8
boundary; a different name enters the book. The chain from one bit to one CAGR
point is short and it is entirely deterministic.

**CONSEQUENCE, STATED PLAINLY. The published headline cannot be reproduced from
the artefacts in this repository to better than roughly one CAGR point.** Anyone
re-running the scoring from `raw_panel_*_cache.csv` — the only panel artefact on
disk — gets 26.15 on n100, not the published 25.49. Both are correct outputs of
the code; they differ because one scored a CSV and one scored memory.

**IT IS THE SAME PHENOMENON AS TWO OTHER ENTRIES, AT THREE SCALES OF
PERTURBATION.** These are not three defects; they are three measurements of one
property.

| perturbation | size | effect on headline CAGR | recorded in |
|---|---|---|---|
| one bit of float precision | 4.441e-16 relative | +0.66 (n100 v2) | this entry |
| training rows moved | 0.01% (41,380,868 → 41,376,648) | +0.54 / −0.81 | `experiments/EXPERIMENTS.md` entry 28 |
| model seeds redrawn | K=10 ensemble | sd 0.97–2.14, range 4.17–10.26 | `experiments/EXPERIMENTS.md` entry 29 |

See also *The 10-seed ensemble does not average away what it was built to average
away* below: the seed run measured why none of this washes out.

**Not fixed.** The options are not equivalent and the choice is a decision, not a
repair: score from the CSV so the artefact is the input (changes every published
number); write the panel at full precision in a binary format (changes every
published number); or state in the README that the panel artefact is a by-product
and the headline is reproducible only to about a point. Nothing here is a typo
fix, and picking one is out of scope for the run that found it.

---

## The 10-seed ensemble does not average away what it was built to average away

Found 2026-09-02 by `experiments/SEED_NOISE_SPEC.txt`. Open. **This is a design
finding about the ensemble, not a caveat on a number.**

An ensemble of K independent models has an error that falls as **K^(−0.5)**. That
is the entire reason to run ten seeds instead of one. Measured, by fitting 40
seeds and forming sub-ensembles of every size:

| universe | arm | fitted σ(K) | **exponent** | σ at K=1 | σ at K=10 |
|---|---|---|---|---|---|
| n100 | v1 | 2.180·K^(−0.150) | **−0.150** | 2.158 | 1.743 |
| n100 | v2 | 1.559·K^(−0.226) | **−0.226** | 1.568 | 0.968 |
| mid | v1 | 3.632·K^(−0.245) | **−0.245** | 3.845 | 2.137 |
| mid | v2 | 1.801·K^(−0.168) | **−0.168** | 1.876 | 1.393 |

**Every exponent is between −0.15 and −0.25, less than half of −0.5.** The
variation between seeds is therefore largely COMMON rather than independent —
ten models trained on the same panel make correlated errors, and averaging them
removes far less than the ensemble design assumes.

**What it costs in practice.** Going from one seed to ten buys a σ reduction from
1.57 to 0.97 on n100 v2 — a factor of 1.6 for ten times the compute, where
independence would have bought 3.2. On n100 v1 it buys a factor of 1.24.

**Extrapolated seeds for ±0.5-point stability**, assuming the fitted exponent
holds far outside the measured range: n100 v2 **152**, mid v2 **2,044**, mid v1
**3,310**, n100 v1 **17,889**. No tested K up to 40 approaches the bar. These are
extrapolations and are labelled as such; the defensible reading is "far more than
is practical", not a target.

**WHY IT IS A DESIGN FINDING.** `SEEDS = [7,42,99,1,2,3,11,22,33,101]` is
duplicated across all four `build_scores*.py` and appears in every params file as
part of the method. Ten was presumably chosen as enough to average out seed
noise. **It is not, and the shortfall is not marginal** — the ensemble is
operating in a regime where its central assumption does not hold. Whether the
answer is more seeds, a different ensembling scheme, bagged data rather than
bagged seeds, or accepting the variance and reporting intervals instead of point
estimates, is a design question this project has never asked.

**Not fixed, and not a number to caveat.** Every published figure remains a
legitimate draw. What this establishes is that the method's own variance-reduction
step is under-delivering by a factor of two or more in the exponent, and that no
figure from it is stable to better than about a point at K=10.

## STEP 2's leakage checklist performs no checks

**Diagnosed in:** `diagnostics/PIPELINE_AUDIT.txt` section 7, **dated
2026-08-30**. The false labels were repaired 2026-08-29; the six checks are
unbuilt as of 2026-09-02.

Found 2026-08-29 by the `run_all.py` audit. **The false labels were removed the
same day. The checks are still not implemented. OPEN.**

**What was fixed, 2026-08-29.** The six rows that printed a literal `PASS` now
print `NOT CHECKED BY THIS RUN`, and a label key was added above the rows saying
that exactly one row is computed, that a `NOT CHECKED BY THIS RUN` row prints the
same text whether or not the property still holds, and that
`results/audit_leakage.py` is not run by this pipeline. The status string is a
named constant, `engine_core.NOT_CHECKED`, so no row can quietly return to
asserting a verdict the run did not reach.

**What was NOT fixed.** None of the six properties is verified by anything in the
pipeline. **The defect that remains is the absence of the checks; the defect that
is gone is the false claim that they had been performed.** The specifications
below stay as the design for whenever they are built.

`engine_core.py` is frozen for the retired 58, so the edit was proved
byte-identical rather than argued to be harmless: 2 of 2 equity curves on the 58
and 8 of 8 on the live universes unchanged —
`diagnostics/leakage_labels_hashes.txt`, regenerable with
`results/hash_58_engine_core.py`.

### The defect as found

`results/engine_core.py:586-609` builds a ten-row table printed under the heading
`[3] LEAKAGE / OVERFIT CHECKLIST` at `run_all.py` STEP 2. **One row is computed.
Nine are string literals typed into the source.**

| row | was | is now | computed? |
|---|---|---|---|
| Label purging | `"PASS"` | `NOT_CHECKED` | no |
| Walk-forward | `"PASS"` | `NOT_CHECKED` | no |
| Execution timing | `"PASS"` | `NOT_CHECKED` | no |
| Feature causality | `"PASS"` | `NOT_CHECKED` | no |
| Shuffle test | `"PASS"` | `NOT_CHECKED` | no |
| **Baseline control** | `"PASS" if ok1 else "FAIL"` | unchanged | **yes** |
| Parameter selection | `"PASS"` | `NOT_CHECKED` | no |
| SURVIVORSHIP BIAS | `"NOT FIXED"` | unchanged | no |
| Market impact | `"NOT MODELLED"` | unchanged | no |
| Variant selection | `"PARTIAL"` | unchanged | no |

The three honest labels were left exactly as they were: they state a limitation
rather than claim a verdict, and they were never the problem.

**THIS IS A PRINTOUT THAT ASSERTS CHECKS WERE DONE. IT IS NOT A CHECK.** The six
rows reading `PASS` are the claim that purging, walk-forward construction,
execution timing, feature causality, the shuffle control and a priori parameter
selection all hold. Nothing in the run establishes any of them. **If any of those
six properties broke tomorrow, the row would print the same text**, because the
text is not derived from anything the run computed.

Anyone reading STEP 2's output would reasonably conclude the pipeline verifies
causality. It does not. The output is indistinguishable from one that had.

The three rows reading `NOT FIXED`, `NOT MODELLED` and `PARTIAL` are honest
labels rather than verdicts and are not the problem. **The six `PASS` rows are.**

**IT CONTRADICTS THIS PROJECT'S OWN RULE, INSIDE THIS PROJECT'S OWN CODE.**
Lesson 5 in `experiments/HANDOFF_SUMMARY.txt` §9 reads:

> An output that hardcodes its own conclusion will eventually lie. Every printed
> verdict is computed from the run that prints it.

Six hardcoded verdicts sit in the pipeline step that exists to establish
correctness. The rule was written from experience elsewhere in the repository and
was never applied here. **A project rule violated inside the project's own code is
worth naming as such**, which is why this is its own entry and not a paragraph in
`diagnostics/PIPELINE_AUDIT.txt` section 7.

**The claims were true when written.** This is not an allegation that any of the
six properties is currently broken — the label-purge gap of 5.4% CAGR quoted in
the row is a real historical measurement, and `results/audit_leakage.py` exists
and does real work but **is not in `PIPELINE_ORDER` and is not run by
`run_all.py`**. The defect is that the printout has no dependency on whether the
properties still hold.

### What a real version would have to do — one line per row, so the size is on paper

| row | what an actual check would require |
|---|---|
| Label purging | assert the gap between each train window's end and its scoring month is ≥ `PURGE` days, measured inside `score_monthly`, on every fold of the run |
| Walk-forward | assert every training index is strictly earlier than the month being scored — an ordering assertion over the fold boundaries, cheap and the closest to free |
| Execution timing | assert every fill price came from day *t+1*'s open when the signal was day *t*'s close, cross-checked against the audit trail's own dates |
| Feature causality | per feature, assert that perturbing prices at *t+1* and beyond leaves the day-*t* value unchanged — 17 recomputations, the most expensive row by far |
| Shuffle test | re-run the backtest on randomised scores and assert the result stays near buy-and-hold; a full rescore-free backtest per shuffle, and it needs a stated tolerance and seed count it does not currently have |
| Parameter selection | not mechanisable as a run-time check — it is a claim about project history, and its honest form is a citation into `experiments/EXPERIMENTS.md`, not a `PASS` |

Five are assertions over the run; the sixth is not a check at all and should stop
pretending to be one. **The shuffle and causality rows are the expensive ones**,
and each needs its own design decision — tolerance, seed count, what "unchanged"
means numerically — before it could be written.

**Status.** The labels were corrected on 2026-08-29 — an unverified claim
labelled as unverified costs nothing and is not a lie. **The six checks are not
built**, each needs its own design, and the two expensive ones need tolerances
and seed counts that do not exist. This entry stays OPEN until they are: the
printout is fixed, the verification is not.

**A reader must not take the label change as progress on correctness.** Nothing
about the pipeline's actual leakage exposure changed on 2026-08-29. What changed
is that the output no longer claims otherwise.

### CORRECTION, 2026-09-02 — five of the six false-PASS rows now have artefacts

Appended, not rewritten. The entry above records the defect as found and the
label fix of 2026-08-29. **What has changed since is that the rows were actually
tested.** A statement made in conversation on 2026-09-02 — that Check B was "the
first of the six to gain real evidence and the other five do not" — was **wrong,
and backwards**. Checked against the record, row by row:

| # | row | status now | artefact |
|---|---|---|---|
| 1 | Label purging | **TESTED, FAILED, and REPAIRED for the live universes on 2026-09-02** | `diagnostics/leakage_check2_purge.txt` (the label reached into the scored month in 7 of 126 months and touched its first day in 21 more, both universes); `diagnostics/purge_fix_measure.txt` (corrected purge, min gap 2 on all 126); EXPERIMENTS entry 29 (return impact inconclusive against the seed floor) |
| 2 | Walk-forward | **TESTED, held** | `diagnostics/leakage_check2_purge.txt` — no training row dated on or after the scored month, all 126 months, both universes |
| 3 | Execution timing | **TESTED, held — re-run 2026-09-02 against the post-purge-fix fills** | `diagnostics/checkB_execution_timing.txt` — **977 of 978** (n100) and **961 of 963** (mid) fills at the fill day's open, **0 at any close**, all 1,941 one session after a recorded decision date. The earlier 976/977 and 971/973 described the pre-rebuild `fills.csv` and are superseded |
| 4 | Feature causality | **TESTED, held** | `diagnostics/leakage_check1_causality.txt` — 17 of 17 bit-exact under two independent future-corruptions, both universes; corroborated by `diagnostics/leakage_check3_normalisation.txt` |
| 5 | Shuffle test | **TESTED, held** | `diagnostics/shuffle_verdict.txt`, EXPERIMENTS entry 28 — 100-permutation null, 0 of 100 beat the real arm on either gated arm on either universe |
| 6 | Baseline control | computed in-run, unchanged | `"PASS" if ok1 else "FAIL"` — the one row that was always live |
| 7 | **Parameter selection** | **STILL A TYPED STRING WITH NOTHING BEHIND IT** | none. The claim is historical ("config fixed a priori"), which Check 3 recorded as not mechanisable. Entry 27 revalidated TOP_N=8, but that is one parameter's current standing, not this row's historical claim |
| 8 | SURVIVORSHIP BIAS | honest label, unchanged; limitation documented | `diagnostics/membership/STATUS.md` — point-in-time membership reaches 2024-03-28 against a 2019 start |
| 9 | Market impact | honest label, unchanged; participation measured | `diagnostics/liquidity_participation.txt`, `diagnostics/depth_compare.txt` |
| 10 | Variant selection | honest label; denominator now recorded | `experiments/EXPERIMENTS.md` — 29 entries, 28 run. The row's own text still says "~20 variants", which is stale |

**FIVE OF THE SIX rows that once printed a false `PASS` now have a named artefact.
ONE — parameter selection — does not.** One of the five, label purging, was tested
and **failed**, which is exactly the outcome the hardcoded `PASS` had concealed.

**Two things this correction does NOT change.**

1. **The labels in the source remain correct.** Every row still reads
   `NOT CHECKED BY THIS RUN`, and that is still accurate: the artefacts above come
   from separate scripts and **nothing in STEP 2 re-tests any of them**. A row
   backed by a standing artefact is not the same as a row computed by the run that
   prints it. This entry stays OPEN for that reason.
2. **The purge fix IS now applied — as of 2026-09-02, for the live universes
   only.** `engine_core.score_monthly` takes `purge_mode`, defaulting to
   `"trading"`: `cut = cal[i_first - HORIZON - 2]`, expressed in trading rows so
   it cannot underflow on a holiday cluster. Verified min = median = max = 2
   across all 126 months on both universes, zero months at or below zero.
   **The retired 58 and 74 are deliberately pinned to `purge_mode="calendar"`**
   at `build_scores.py`, `build_scores74.py`, `engine_core.main()` and
   `validate_breadth.py`, each with a frozen-universe comment, so their published
   numbers still reproduce. The default is the correct mode so anything new gets
   it right; legacy must be asked for by name.

**Two row texts are stale independently of their labels.** Row 5 still quotes
"9.7% CAGR vs 18.5% buy&hold" from retired-58-era work with no surviving artefact;
entry 28 reports different figures on different universes. Row 10 still says
"~20 variants" against a recorded 29.

## The audit flag's inertness was assumed across published figures — CLOSED 2026-09-03

Found 2026-09-03 while wiring per-day logging into the cadence sweep. **CLOSED the
same day by measurement.** Recorded because it was a live assumption underneath
published numbers, not because it turned out to be wrong.

**THE ASSUMPTION.** `results/test_exposure.py:72`, the docstring of
`backtest_exposure` — the shipping engine — states:

> "audit=None reproduces the original code path exactly: no overhead, and the
> official numbers are unchanged."

**That was a comment, and it had been one for as long as the parameter existed.**
Nothing tested it. `HANDOFF_SUMMARY.txt` section 9 lesson 10 says to verify
whether a diagnostic flag changes the numbers it observes rather than assuming it,
and this was an unverified instance of exactly that.

**WHY IT WAS NOT COSMETIC. SOME PUBLISHED ARTEFACTS WERE PRODUCED WITH THE FLAG ON
AND OTHERS WITH IT OFF.** `engine_v2_final_n100.py:93-98` passes a populated audit
dict for its baseline arm and `None` for the breadth arm in the same run;
`v34_common.run_v34` does the same across the four arms. So figures sitting side
by side in `v34_comparison.csv` were produced on different sides of a flag whose
inertness nobody had measured. **If the flag had perturbed anything, arms would
have been compared across it without anyone knowing.**

**CLOSED BY A 40-CELL A/B ON THE SHIPPING ENGINE.** The cadence grid of
`EXPERIMENTS.md` entry 31 had just produced a clean `audit=None` baseline, so the
same 40 cells — 4 arms × 5 cadences × 2 universes, 1,836 trading days each — were
re-run with a six-key audit dict and everything else held bit for bit.

| | result |
|---|---|
| equity curves | **byte-identical**; max absolute difference **0.0** across all 73,440 values; 0 of 40 columns differ |
| per-cell metrics CSV | **byte-identical**; 0 cells differ on trades, TC, CAGR, Sharpe, MaxDD or final equity |
| text diagnostic | identical on all 214 lines but for the run's own wall-clock line |

**Not "small" — zero.** The prediction was written in
`experiments/REBAL_CADENCE_SPEC.txt` PART 9 before the audit path was wired in,
with a stop condition that would have reported any movement as a defect in the
shipping engine. It did not fire.

**WHAT IS NOW ESTABLISHED, AND WHAT IS NOT.** The flag is inert **on those 40
cells, those two score panels, that window**. It is **not** proven inert in
general — not on other windows, other panels, or the retired universes — and
**nothing here touches the three other inline reimplementations of the backtest**
(`engine_core.backtest`, `nt_attribution.py`, `frozen/make_cash_series.py:39`),
each of which carries its own book. A fourth, `make_stats_both.py`, was deleted
in S2 (`9ced314`). See *There are FIVE reimplementations of the backtest, not
two* above.

**Full record:** `experiments/EXPERIMENTS.md` entry 32, *"The audit flag does not
change what it observes — a docstring claim, verified"*. Measurement:
`diagnostics/rebal_cadence_{sweep.txt,cells.csv,equity.csv}` and
`diagnostics/rebal_cadence_audit/`. Script: `results/rebal_cadence_sweep.py`.

**The docstring itself is unchanged.** Its wording was correct; what was missing
was evidence, and the evidence now exists outside the comment rather than inside
it.

---

## A fresh checkout could never have completed: config.py did not create its output directory — FIXED 2026-09-03

Found 2026-09-03 the first time the pipeline was ever run end to end from
nothing, on a repository stripped to `.py` files plus `data/raw`. **Fixed the same
day.** Recorded because the way it hid is the lesson, not the missing line.

**THE DEFECT.** `config.py:64` defined `METRICS_DIR = RESULTS_DIR / "metrics"` as a
bare path and never created the directory. STEP 2 `engine_core.py` computed the
entire 58 result correctly and then died on its first write:

    OSError: Cannot save file into a non-existent directory:
             '.../results/results/metrics'   (engine_core.py:535, comp.to_csv)

**config.py WAS THE ONLY ONE OF FOUR CONFIG MODULES THAT DID NOT CREATE ITS OWN
OUTPUT DIRECTORY.** The three siblings already did, at import:

    config74.py:21     METRICS_DIR_74.mkdir(parents=True, exist_ok=True)
    config_mid.py:44   METRICS_DIR_MID.mkdir(parents=True, exist_ok=True)
    config_n100.py:58  METRICS_DIR_N100.mkdir(parents=True, exist_ok=True)
    config.py          -- nothing --

So STEP 2, which uses `config.METRICS_DIR`, crashed, while STEPS 10b/f, which use
the sibling configs, would not have. The asymmetry IS the bug.

**THE DIRECTORY EXISTED ON THIS MACHINE ONLY AS AN ACCIDENT OF HISTORY.**
`results/metrics/` was present because it had been created at some point long ago
and never removed. Nothing in the code recreates it. **A fresh `git clone` on any
other machine has no `results/metrics/`, so the pipeline as published COULD NEVER
HAVE COMPLETED on a clean checkout** — the exact scenario the README describes
("take the code and the data") and the exact scenario nobody had tried. The bug
was invisible precisely because the one machine that ran the pipeline was the one
machine where the directory happened to survive.

**IT WENT UNDETECTED BECAUSE THE PIPELINE HAD NEVER BEEN RUN END TO END FROM
NOTHING.** Every prior run reused artefacts that were already on disk. The first
true `--fresh` run against an empty tree was 2026-09-03, and it found this at
STEP 2.

**PIPELINE_AUDIT.txt DID NOT CATCH IT EITHER, AND THAT IS THE LESSON.** Section 5
of that audit is headed "DOES run_all.py STILL RUN END TO END?" and answers, in
its own words: *"THIS IS INFERRED FROM READING. IT WAS NOT RUN."* A reading audit
can verify that every step names its inputs and that ordering is consistent — and
it did. **It cannot see a directory that must exist but that no code creates,
because nothing in the source is wrong to read; the defect is in the gap between
the source and the filesystem it assumes.** Only execution against an empty tree
exposes that gap. The distinction — read-verified versus run-verified — is the
finding here. A pipeline can pass every static check and still be unrunnable from
a clean state, and the only instrument that detects it is a fresh run.

**TWO LATENT INSTANCES OF THE SAME DEFECT, FIXED IN THE SAME PASS.** They had not
fired yet only because the run died at STEP 2 before reaching them:

    make_per_stock_charts.py:26  OUT.mkdir(exist_ok=True)   -- results/metrics/per_stock_charts
    make_combined_all.py:18      OUT.mkdir(exist_ok=True)   -- results/metrics/combined_charts

Both create a CHILD of `results/metrics` with `exist_ok=True` but WITHOUT
`parents=True`, so on a fresh checkout each would have raised
`FileNotFoundError` the moment its parent did not exist — STEP 7 and STEP 7b,
one and two steps after the STEP 2 crash. Left unfixed they would have been
discovered one at a time over the length of a three-hour run. Both were changed to
`mkdir(parents=True, exist_ok=True)` in the same pass.

**THE FIX.** `config.py` now creates `METRICS_DIR` and `EQUITY_CURVES_DIR` at
import, matching the three sibling configs:

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    EQUITY_CURVES_DIR.mkdir(parents=True, exist_ok=True)

**Import-time in the config, NOT a block in run_all.py, and the choice is
deliberate.** Every pipeline script and every standalone script imports its config
module; almost none imports run_all.py. A block in run_all.py would fix only the
run_all entry point and leave `python results/engine_core.py` on a fresh checkout
crashing identically. Creating the directory where the path is DEFINED makes a
fresh checkout work for ANY entry point.

**THE COMPLETE WRITE-TARGET MAP, so the next person need not re-derive it.** Every
directory the 32-step pipeline writes to, and who creates it:

| directory | created by | status |
|---|---|---|
| `results/metrics` | `config.py` | FIXED 2026-09-03 |
| `results/equity_curves` | `config.py` | created (defined, unused by pipeline) |
| `results74/metrics` | `config74.py` import | already OK |
| `results_mid/metrics` | `config_mid.py` import | already OK |
| `results_n100/metrics` | `config_n100.py` import | already OK |
| `results/metrics/per_stock_charts` | `make_per_stock_charts.py` | hardened (parents=True) |
| `results/metrics/combined_charts` | `make_combined_all.py` | hardened (parents=True) |
| `nautilus/data` | `nt_export_scores.py:72` | already OK |
| `data/nse_trading_calendar.csv` (STEP 0) | `make_trading_calendar.py:86` | already OK |

The pipeline never writes to `diagnostics/`, `docs/`, `nautilus/reports` or
`nautilus/catalog` — references to `diagnostics/` in four pipeline scripts are in
comments only, and the charts in `docs/` are copied there manually outside the
pipeline. So `results/metrics` was the single missing-directory defect, plus the
two latent child-dir cases above.

---

## The score caches can be neither safely deleted nor safely regenerated

Found 2026-09-03 during a repository cleanup survey. **This is a constraint on the
project, not a housekeeping note.** Open, and there is no action that resolves it.

**THE FILES.** 610.5 MB across four universes, every one nominally an output of a
step in `PIPELINE_ORDER`:

| file | MB | producer | in PIPELINE_ORDER |
|---|---|---|---|
| `results_mid/metrics/raw_panel_mid_cache.csv` | 206.9 | STEP 10a `build_scores_mid.py` | yes |
| `results_n100/metrics/raw_panel_n100_cache.csv` | 169.9 | STEP 10e `build_scores_n100.py` | yes |
| `results/metrics/raw_panel_cache.csv` | 100.3 | STEP 1 `build_scores.py` | yes |
| `results74/metrics/raw_panel74_cache.csv` | 62.7 | STEP 8 `build_scores74.py` | yes |
| `results_mid/metrics/v_mid_expanding_cache.csv` | 26.9 | STEP 10a | yes |
| `results_n100/metrics/v_n100_expanding_cache.csv` | 21.7 | STEP 10e | yes |
| `results/metrics/v5_expanding_cache.csv` | 12.7 | STEP 1 | yes |
| `results74/metrics/v74_expanding_cache.csv` | 9.5 | STEP 8 | yes |

**BY THE ORDINARY TEST THEY ARE DISPOSABLE.** Every one has a named producer, and
every producer is a live pipeline step. Any cleanup that classifies files as
"regenerable if a pipeline step writes them" will mark all eight for deletion.
**That classification is wrong here, and the reason is recorded elsewhere in this
file rather than anywhere near the caches themselves.**

**WHY DELETING THEM IS NOT REVERSIBLE.** `build_scores_*.py` call `score_monthly`
on the **in-memory** panel and write `raw_panel_*_cache.csv` one line earlier as a
**by-product**. The CSV is not the scoring input. The two differ by one unit in the
last place — max 4.441e-16 across 2,638,259 cells — and that is enough to flip a
LightGBM split, reorder near-tied names at the TOP_N=8 boundary, and move the
headline:

| | rebuilt from the CSV panel | published | offset |
|---|---|---|---|
| n100 v2 CAGR | 26.15 | 25.49 | **+0.66** |
| mid v2 CAGR | 29.93 | 30.22 | **−0.29** |

See *The headline is not reproducible from the artefacts on disk to better than
about a point* above, and `EXPERIMENTS.md` entry 29.

**SO THE PUBLISHED NUMBERS DEPEND ON THESE PARTICULAR FILES, NOT ON THE CODE THAT
MADE THEM.** Deleting them does not cost 36 minutes of rebuild. It costs the
ability to reproduce `v34_comparison.csv`, and every entry in `EXPERIMENTS.md` that
quotes from it. The retired 58 and 74 caches carry the same property with the
freeze policy on top: regenerating them is precisely what the freeze exists to
prevent.

**THE CONSTRAINT, STATED PLAINLY.**

- **They cannot be deleted**, because the numbers cannot be reproduced without them.
- **They cannot be regenerated**, because regenerating changes the numbers.
- **They cannot be verified**, because there is nothing to verify them against —
  the in-memory panel that produced the scores was never written.
- **They are 610.5 MB of untracked, unbacked, single-copy state that the entire
  published record rests on.** `.gitignore` excludes the raw data for size; these
  are not in version control either. There is no second copy anywhere.

**THIS IS THE MOST FRAGILE THING IN THE REPOSITORY.** A disk failure, an
accidental `rm`, or a well-meaning cleanup would not degrade the project — it
would end the reproducibility of every published figure, permanently, with the
code intact and blameless.

**Not fixed, and the options are not equivalent.** Write the panel at full
precision in a binary format (changes every published number); score from the CSV
so the artefact is the input (changes every published number); back the caches up
outside the repository and record where (changes nothing, resolves nothing, but
removes the single-copy exposure). **The first two are the same decision recorded
above as open; only the third is available without moving a number, and it is not
a fix.**

---

## An orphan-finder gives the wrong answer on this repository, and the wrong answer is 48

Found 2026-09-03, by getting it wrong first. Open — this is a property of the
repository that will mislead the next person, not a defect to repair.

**THE NAIVE SCAN.** Parse every `.py` outside `venv/`, build the import graph, check
membership in `PIPELINE_ORDER`. Result: 96 files, 32 in the pipeline, 17 imported by
something, **48 in neither — apparently dead.**

**48 IS WRONG. THE REAL NUMBER IS 5.** Two corrections are needed, in order:

**(1) Documentation references.** Grepping all 208 `.py`/`.md`/`.txt`/`.json` files
for each script's own name moves **29** of the 48 out of the dead pile: they are
named in `EXPERIMENTS.md`, `KNOWN_ISSUES.md`, the specs, or `HANDOFF_SUMMARY.txt`
as the script behind a recorded measurement. `run_all.py` is also in the 48, being
the entry point nothing imports.

**(2) THE ONE THAT ACTUALLY MATTERS: A SCRIPT'S OUTPUT CAN BE CITED WHEN ITS NAME
IS NOT.** Of the 18 files with no textual reference anywhere, **13 are the
producers of diagnostics that entries cite as evidence.** Deleting them leaves the
`.txt` on disk with no way to regenerate it — the evidence survives and becomes
unreproducible, which is worse than either keeping or losing both.

| script | produces | cited in |
|---|---|---|
| `results/check_a_close_values.py` | `checkA_close_bad_values.txt` | EXPERIMENTS.md, DATA_EXEC_SPEC.txt |
| `results/check_b_exec_timing.py` | `checkB_execution_timing.txt` | 5 documents |
| `results/leakage_check1_causality.py` | `leakage_check1_causality.txt` | KNOWN_ISSUES.md, LEAKAGE_SPEC.txt, EXPERIMENTS.md |
| `results/leakage_check2_purge.py` | `leakage_check2_purge.txt`, `leakage_purge_gaps.csv` | 5 documents |
| `results/leakage_check4_corpactions.py` | `leakage_check4_corpactions.txt` | LEAKAGE_SPEC.txt, DATA_EXEC_SPEC.txt, LEAKAGE_AUDIT.txt |
| `make_v34_report.py` | `v34_report.txt`, `v34_comparison.csv` | 14 documents |
| `liquidity_participation.py` | `liquidity_participation.txt` — the 1,614.52% figure | DRAWDOWN_EXIT_SPEC.txt, EXPERIMENTS.md |
| `verify_v34_arms.py` | `verify_v34_arms.txt` | V34_SPEC.txt |
| `results/save_ewma_comparison.py` | `ewma_vs_rolling_REPORT.txt` | EXPERIMENTS.md, rejected_experiments_REPORT.txt |
| `depth_compare.py` | depth/fills comparison | KNOWN_ISSUES.md, NAUTILUS_STATUS.md |
| `results/diagnose_cash_drag.py` | reads `cash_series_{58,74}.csv` | the cash-yield entry |
| `data_artefact_report.py` | cache inventory | — reads cited caches |
| `diagnostics/task2_ic_decay.py` | `task2_ic_decay.txt` | present in diagnostics/ |

**Several write via stdout redirection rather than `to_csv`, so even a
write-detecting scan misses them.** `liquidity_participation.py` and
`verify_v34_arms.py` contain no `to_csv`, no `savefig` and no `open(...,'w')` — their
diagnostics were produced by redirecting output. **A scan for "what does this file
write" returns nothing for both, and both are load-bearing for cited figures.**

**THE FIVE THAT ARE GENUINELY DEAD**, deleted 2026-09-03 after this check:
`density_fix_lookahead.py`, `nautilus/nt_trace_one_fill.py`,
`diagnostics/membership/analyse.py`,
`diagnostics/membership/extract_membership_fixed.py`. Each writes nothing, is named
nowhere, and is superseded by a later file or by a diagnostic that covers the same
ground.

**A FIFTH WAS DELETED IN ERROR AND RESTORED THE SAME MINUTE.**
`results/hash_58_engine_core.py` was added to the delete list on the judgement that
it was "superseded by the hash artefacts" — **without running the check that had
just been applied to the other four.** It is referenced twice:
`KNOWN_ISSUES.md:646` and `diagnostics/leakage_labels_hashes.txt:28`, the latter as
*"Regenerate with: ./venv/bin/python results/hash_58_engine_core.py"* — it is the
named regeneration path for a cited hash artefact, the exact pattern the table
above documents. It was tracked in git and was restored intact.

**THE LESSON IS NOT "BE MORE CAREFUL".** It is that the check must be mechanical
and applied to every candidate without exception, because the one file exempted by
judgement was the one that failed. Recorded here so the next cleanup runs the check
rather than repeating the reasoning.

**THE PROCEDURE, FOR THE NEXT PERSON.** A file is dead only if all four hold:
(1) not in `PIPELINE_ORDER`; (2) not imported by any `.py`; (3) its **name** appears
in no `.md`/`.txt`/`.json` outside `venv/` and `diagnostics/INVENTORY.csv`; and
(4) **the files it writes — including via stdout redirection — are cited nowhere.**
Test (4) is the one an orphan-finder will not have, and it is the one that moves
the answer from 48 to 5.

**`diagnostics/INVENTORY.csv` must be excluded from test (3).** It is a
whole-repository file listing, so it matches every filename and makes every file
look referenced. It is also now stale with respect to the 2026-09-03 deletions.

---

## VOL_WIN = 60 has sixteen independent definitions and no central home

**Diagnosed in `diagnostics/PIPELINE_AUDIT.txt` section 6, 2026-08-30, as TEN
definitions. Filed here 2026-09-02, when a re-count found SIXTEEN.** Open.

Distinct from a site diverging from `config.py`: **there is nothing in
`config.py` for these to diverge from.** `config.py` defines `BT_START_DATE`,
`BT_END_DATE`, and since 2026-08-29 `TOP_N` and `BUFFER`. It defines no
`VOL_WIN`.

The volatility lookback governs inverse-vol sizing, which is the production
sizing rule. Every definition currently reads 60, and **nothing enforces that**.

    results/engine_core.py:90            results/test_exposure.py:56
    frozen/engine_v2_final.py:56         frozen/engine_v2_final74.py:56
    results/engine_v2_final_mid.py:62    results/engine_v2_final_n100.py:58
    frozen/make_cash_series.py:83        frozen/validate_breadth.py:35
    results/validate_topn.py:94          results/purge_fix_measure.py:49
    results/seed_noise_measure.py:54     results/shuffle_test.py:55
    experiments/sizing_test.py:44        nautilus/nt_strategy.py:85
    nautilus/nt_attribution.py:40

Fifteen sites, re-verified 2026-09-05: every one reads 60. The list above was
itself stale in ten of its sixteen entries -- four files moved to `frozen/` in
S2, five line numbers had shifted, and `make_stats_both.py:14` was deleted --
which is the same failure this entry is about, one level up. A roll-call of
literals maintained by hand drifts exactly like the literals do.

Exactly one site does it correctly: `results/validate_breadth_live.py:74` imports
`VOL_WIN` from `engine_core` rather than redeclaring it.

**THE COUNT GREW AFTER THE DIAGNOSIS, AND THAT IS THE POINT OF FILING IT.** The
audit listed ten on 2026-08-30. Six have appeared since, and **three of those six
are the measurement scripts written on 2026-09-01 and 2026-09-02** —
`shuffle_test.py`, `seed_noise_measure.py`, `purge_fix_measure.py`. The
duplication was correctly diagnosed and then reproduced three more times, by work
that post-dates the diagnosis, because the diagnosis lived in a diagnostics file
that nothing consults.

**Consequence.** `make_stats_both.py:14` was the proof that this drifts rather
than the hypothesis: on the same line it carried `TOP_N, BUFFER = 12, 24` against
8 and 16 everywhere else. The same line shape, in the same file, had already
drifted on two of its four constants.

**Deleting that file in S2 removed the instance, not the exposure.** The evidence
is still readable at `git show 9ced314^:results/make_stats_both.py`, and the
fifteen surviving definitions are still fifteen hand-maintained literals with
nothing enforcing agreement. Nothing would catch `VOL_WIN` going the same way,
and a divergence there would silently change position sizing in whichever script
carried it. Losing the one site that had already drifted makes this entry easier
to dismiss, not less true.

**Not fixed, and the deferral has a stated reason that this entry does not
override.** `PIPELINE_AUDIT.txt` section 6 records the section 6 constants as
"recorded, not fixed" by decision: centralising `TOP_N` and `BUFFER` required an
eight-curve byte-identity proof (`diagnostics/topn_centralise_hashes.txt`), and
each remaining constant needs its own. That reason stands. **What is filed here is
the record, not a proposal to act.**

---

## Five validation tables are regenerated on every run and read by nothing

**Diagnosed in `diagnostics/PIPELINE_AUDIT.txt` section 1, 2026-08-30. Filed here
2026-09-02.** Open.

    results/metrics/FINAL_val_seeds.csv      written by engine_core.py:591
    results/metrics/FINAL_val_periods.csv    written by engine_core.py:611
    results/metrics/FINAL_val_volwin.csv     written by engine_core.py:625
    results/metrics/breadth_val_seeds.csv    written by validate_breadth.py:86
    results/metrics/breadth_val_periods.csv  written by validate_breadth.py:116

**These are the evidence behind validation verdicts.** `FINAL_val_*` holds the
per-seed, per-sub-period and per-vol-window results of the four-test inverse-vol
sizing suite — the suite whose outcome this project quotes as "4 of 4 PASS on
n100, 1 of 4 on mid". `breadth_val_*` holds the equivalent for the breadth suite
on the retired 58.

**No code reads any of the three `FINAL_val_*` files, and no document cites one.**
A repository-wide search for each filename outside `venv/` returns exactly one
mention each — `PIPELINE_AUDIT.txt` itself, which is what noticed.

**WHY THIS IS WORSE THAN AN UNUSED OUTPUT.** A verdict is quoted; its evidence is
written to a file nobody opens. If a table disagreed with the verdict printed
beside it, nothing in the project would surface the disagreement. The tables are
regenerated on every run, so they are not even a fixed record — they are
overwritten each time by whatever the current code produces, with no reader and
no comparison against what they held before.

**They are also stale, which nothing announces.** All five are dated
**2026-08-23** — before the 2026-08-28 window change and before the 2026-09-02
purge correction. See *Twenty-two of the thirty-two pipeline steps have not run
since 2026-08-23* below.

**Not fixed.** Three options and they are not equivalent: have something read them
and assert the verdict against them; stop writing them; or keep them as a dated
archive rather than an overwritten output. Which is right depends on whether the
retired path is a build or an archive, which
`diagnostics/PIPELINE_AUDIT.txt` section 9 raises and does not settle.

---

## Twenty-two of the thirty-two pipeline steps have not run since 2026-08-23

**Diagnosed in `diagnostics/PIPELINE_AUDIT.txt` section 5, 2026-08-30, as an
inference from reading. Filed here 2026-09-02 with the file timestamps that
confirm it.** Open.

The audit stated: *"TWENTY-TWO OF THE THIRTY-TWO STEPS HAVE NOT BEEN RE-RUN SINCE
THE WINDOW CHANGE, because that work touched only the live scripts. Their inputs
and expectations have been drifting with nothing exercising them."* It could not
verify this, because verifying it means running the pipeline.

**The artefacts confirm it.** Every output of the retired 58 and 74 chain carries
the same date:

| directory | files | last written |
|---|---|---|
| `results/metrics/*.csv` (58) | 40+ | **2026-08-23**, all of them |
| `results74/metrics/*.csv` (74) | all | **2026-08-23** |
| `results_n100/metrics/`, `results_mid/metrics/` (live) | — | 2026-09-02 |

Including `v5_expanding_cache.csv` and `v74_expanding_cache.csv` — the score
panels themselves — and `FINAL_comparison.csv`, `v2FINAL_equity.csv`,
`fair_comparison_table.csv` and `FINAL_SUMMARY_TABLE.csv`.

**WHAT THIS MEANS AND WHAT IT DOES NOT.** It does **not** mean those steps are
broken; nobody has run them, so nobody knows. That is the finding. Twenty-two
steps execute on every `run_all.py` invocation, write into shared directories, and
have not been exercised across two changes to the code they share with the live
path — the window change of 2026-08-28 and the purge correction of 2026-09-02.
The retired numbers are correctly frozen; the freeze applies to the **artefacts**.
It has been applied in practice to the **scripts**, which is a different thing: a
frozen artefact is a record, a frozen script that still runs is an unmaintained
process with write access.

**It is not hypothetical that they can break.** The documented launch command
crashed at STEP 1 for an unknown period and nobody noticed, because nobody had run
the pipeline end to end. See *The documented commands are not verified against the
machine they run on* above.

**Not fixed.** Establishing the current state costs one full `--fresh` run, of
order three hours, and would rewrite every retired artefact — which the freeze
policy governs and which is precisely why it has not been done. That circularity
is the defect: the policy that protects the retired numbers is the same thing
preventing anyone from learning whether the code that produces them still works.
`diagnostics/PIPELINE_AUDIT.txt` section 9 proposes a split as the way out and
explicitly does not execute it.

---

## make_cash_series.py runs a 6% cash yield, and its output reaches a consumer

Found 2026-08-29 by the `run_all.py` audit. Open.

**Diagnosed in:** `diagnostics/PIPELINE_AUDIT.txt` section 3 (*"THE
make_cash_series.py FINDING IS THE ONE THAT MATTERS"*) and section 9, **dated
2026-08-30**. Still open as of 2026-09-05. The same audit section records the
`make_stats_both.py:14-15` drift — `TOP_N, BUFFER = 12, 24` and `CASH_Y = 0.06`
against 8, 16 and 0.0 everywhere else — which was **resolved by deleting that
file** in S2 (`9ced314`), an option available only because its outputs were dead.
**This entry is the one that could not be closed that way**: the same 6% literal
lives on at `frozen/make_cash_series.py:84` and its output does reach a consumer.
See *There are FIVE reimplementations of the backtest, not two*.

`results/make_cash_series.py:16` sets

    SLIP,CAP,CASH_Y=0.0015,1_000_000,0.06

against `CASH_YIELD = 0.0` in `results/test_exposure.py:61` and everywhere else.
It is applied at line 42 as `cd=(1+CASH_Y)**(1/252)-1` and compounded onto cash
every day of the run. It was the **same 6% literal** that `make_stats_both.py:15`
carried, in a second script — that script is gone, this one is not.

**UNLIKE `make_stats_both.py`, THIS OUTPUT IS LIVE.** That is the whole
difference between the two, and it is why this has its own entry, and why this
one could not be closed by deleting it. **Still open.**

| step | what happens |
|---|---|
| STEP 11 | `make_cash_series.py` writes `cash_series_58.csv`, `cash_series_74.csv` |
| STEP 13 | `make_final_chart_fair.py:74-76` reads both |
| | `:119-123` and `:182` use `cash_pct` for average deployment and the "on deployed capital only" return |
| | writes `fair_comparison_table.csv` and the final chart's subtitle |
| STEP 14 | `make_final_summary.py:13` reads `fair_comparison_table.csv` |

A 6% yield inflates the cash leg, so those deployment percentages describe a
portfolio earning interest the shipping engine does not pay. **This is a wrong
number reaching a consumer**, which the `make_stats_both.py` defect never was —
and the reason that one could be closed by deletion and this one cannot.

**It is confined to the retired 58/74 chain.** It does not touch either live
universe and no README figure derives from it — `README.md` embeds
`docs/chart_COMBINED_n100_mid.png` and `docs/chart_decay.png`, neither of which
is in this chain.

**BUT THE CONFINEMENT IS CIRCUMSTANTIAL, NOT BY DESIGN.** Nothing in the code
scopes this to the retired universes. It is confined only because the live
universes happen to have their own audit and chart steps (`make_mid_audit` /
`make_mid_chart`, `make_n100_audit` / `make_n100_chart`) that do not read the
cash series. Had the live charts been built on the 58/74 pattern — which is the
pattern they were added alongside — the 6% would be in the published figures.
Nothing prevented that; it did not happen.

**It is also the fifth inline reimplementation of the backtest.** Lines 42-70
carry their own `shares`/`cash`/`pending` ledger with transaction costs,
slippage, the buffer rule and inverse-vol sizing, importing no engine. See *There
are FIVE reimplementations of the backtest, not two* above.

**Not fixed.** Correcting the constant alone is not obviously right: it would
move a retired universe's published deployment figures and the fair comparison
table, which the freeze policy governs, and it would leave a fifth engine in
place to drift again. The choice is between correcting the constant, making the
script import `backtest_exposure`, and removing it from the pipeline — and that
is a decision about what the retired path is for. `diagnostics/PIPELINE_AUDIT.txt`
section 9 is the argument for the third.

## Live documents reference code by line number, and line numbers shift

Found 2026-08-29, by causing it. Open.

`KNOWN_ISSUES.md`, `experiments/HANDOFF_SUMMARY.txt`, `config.py`'s comments and
several script comments cite code as `file.py:NNN`. That is precise and clickable
and it is why the convention exists. **It also breaks on any insertion above the
cited line, including an insertion that changes no behaviour at all.**

**Measured, not hypothesised.** A six-line comment added above
`engine_core.py:84` and a two-line import added at `test_exposure.py:56` — one of
them comment-only, neither altering a single literal — invalidated **six
references that had each been exactly right**:

| reference | was | now | cited by |
|---|---|---|---|
| `BT_START, BT_END` | `engine_core.py:87` | `:93` | `config.py`, `HANDOFF_SUMMARY.txt` |
| `avail = cash * 0.98` | `engine_core.py:302` | `:308` | this file |
| T3's half-window | `engine_core.py:537` | `:543` | this file, `validate_sizing.py` comment |
| `CASH_YIELD` | `test_exposure.py:59` | `:61` | this file |
| `invest_val` | `test_exposure.py:100` | `:106` | this file |
| the funding mechanism | `test_exposure.py:97-136` | `:103-142` | this file |

All six were repaired in the same pass. The point is not that they broke, it is
that **nothing would have caught them if they had not been.** A stale line number
does not fail; it silently points at a different line, and the reader who follows
it lands somewhere plausible and wrong. This is the same failure shape as a stale
cache: no error, wrong answer.

**Referencing by SYMBOL NAME would not have this failure mode.** `engine_core`'s
`BT_START` definition, or `test_exposure`'s `invest_val` assignment, survives any
insertion anywhere in the file, and a rename that broke such a reference would be
found by the same grep that maintains it. Line numbers are stable only against
edits that never happen.

**PRE-REGISTRATIONS ARE EXCLUDED AND STAY STALE BY DESIGN.**
`experiments/BREADTH_LIVE_SPEC.txt:173` still cites `test_exposure.py:143-157` and
`experiments/V34_SPEC.txt:85` still cites `nt_strategy.py:480`. Both were accurate
when written; both were already stale before the 2026-08-29 edit, moved by the
`mode="const"` branch and the `SIZING` switch that those very specs authorised.
They are documents of record. Editing a prereg to keep its line numbers current is
the same act as rewriting `validate_breadth.py` to run on a new universe, and it is
refused for the same reason. **A prereg's staleness is evidence of when it was
written. A live document's staleness is a defect.**

**Not fixed.** Converting the live references to symbol names is a sweep across
four documents and several script comments, it touches files outside any current
task, and it is a judgement about citation style rather than a correction. Recorded
so the next person to insert a line above a cited one knows to grep for references
into that file first.

## New positions are funded from cash alone, so the target book is not always filled

Found 2026-08-28, during the V34 four-arm measurement. Open, and left open by
decision rather than by oversight.

**The mechanism**, at `results/test_exposure.py:103-142`:

    port_val   = value of existing holdings + cash
    invest_val = port_val * exposure * 0.98

`invest_val` is computed over the WHOLE portfolio. But the buy loop skips any name
already held (`if s == "_exposure" or s in shares: continue`), and existing
holdings are never resized. So the money for new entrants comes from **cash
alone**, while their targets are a share of a number that includes the value of
positions that will not be sold.

When the new names' combined target exceeds available cash, the loop runs out. It
iterates score-descending, so it is the **lowest-ranked** of the eight that get
dropped, logged as `cash short (before TC)`.

### What actually makes it bind: PER-ENTRANT SLICE SIZE, not the number of targets

Corrected 2026-08-29 by the TOP_N validation (`EXPERIMENTS.md` entry 27). **The
description above was written from the v1-against-v3 observation alone, and that
observation does not identify the mechanism** — it shows only that one arm skips
more than another at a fixed `TOP_N`.

`experiments/TOPN_SPEC.txt` predicted, in advance, that `TOP_N=12` would skip
**more** than `TOP_N=8`, on the reasoning that twelve targets funded from cash
alone is more pressure than eight. **That prediction was contradicted, and in the
opposite direction:**

| universe | cash-short skips at TOP_N=8 | at TOP_N=12 |
|---|---|---|
| n100 | 7 | **0** |
| mid | 1 | **0** |

**Why.** `invest_val` is a single portfolio-wide number, and it is split `TOP_N`
ways. Raising `TOP_N` does not raise the total to be funded — it **shrinks each
entrant's slice**, so every individual buy is easier to cover from cash and the
score-descending loop exhausts it less often. The binding quantity is the size of
one entrant's target against available cash, not the count of entrants.

**A second effect points the same way.** A larger `TOP_N` against a pinned
`BUFFER=16` holds a fuller book — mean names held rises 9.54 → 12.88 on n100 and
9.23 → 12.88 on mid — so more of the target set is already held and **skipped by
the buy loop**, leaving fewer new entrants to fund at each rebalance. Both effects
reduce pressure as `TOP_N` rises.

**Consequence for how this defect is read.** It is not a "too many names" problem
and it does not get worse as the book widens. It is a **concentration** problem:
it bites hardest when few, large positions must be bought out of cash, which is
the regime the shipping configuration runs in. That is why v1 — always invested,
eight names — is the arm that hits it 119 and 92 times, and why breadth scaling
masks it rather than fixing it.

**Measured, both live universes, 92 rebalances, window 2019-01-01 to 2026-05-29:**

| universe | arm | cash-short skips | mean names held | rebalances holding < 8 |
|---|---|---|---|---|
| n100 | v1 invvol, 100% invested | 119 | 8.01 | 12 |
| n100 | v2 invvol, breadth-scaled | 7 | 9.54 | 1 |
| n100 | v3 provol, 100% invested | 140 | 7.78 | 24 |
| n100 | v4 provol, breadth-scaled | 9 | 9.52 | 1 |
| mid | v1 invvol, 100% invested | 92 | 8.04 | 14 |
| mid | v2 invvol, breadth-scaled | 1 | 9.23 | 0 |
| mid | v3 provol, 100% invested | 129 | 7.63 | 34 |
| mid | v4 provol, breadth-scaled | 1 | 9.23 | 0 |

The skipped name's rank is median 7 or 8 of 8 in every arm — the tail of the buy
loop, as the mechanism predicts. `qty < 1 after sizing` is **zero** for v1 and v3
in both universes, so this is not a rounding-to-zero effect; it is cash exhaustion.

**IT AFFECTS THE PRODUCTION BASELINE, INDEPENDENTLY OF ANY OF THIS.** v1 is the
always-invested inverse-vol arm that ships. It fails to fill its own eight-name
target on **12 of 91 rebalances on n100 and 14 of 91 on mid**, and it does so 119
and 92 times at the individual-name level. That had never been measured before
2026-08-28. It is not caused by pro-vol and does not go away when pro-vol does.

Breadth scaling largely masks it: v2 and v4 deploy only 54–56%, so cash is rarely
binding — 7 and 1 skips against 119 and 92.

**Left unfixed by decision.** Fixing it means changing how inverse-vol sizing
funds new positions, which would move the published v1 and v2 numbers, and it is
out of scope by the explicit statement at `experiments/V34_SPEC.txt:125` that no
held position is ever topped up or resized. The decision was to record it rather
than change behaviour mid-measurement.

**It is visible in the artefacts, not only here.** `v34_comparison.csv` and
`v34_subperiods.csv` in both universes carry `MeanNamesHeld` and `CashShortSkips`
columns for every arm, so a reader of those tables alone can see that v1 and v3
did not hold the same portfolio.

### 2026-09-04: WHY IT CANNOT BE FIXED WITHOUT CHANGING THE STRATEGY

Measured after the valuation fix (`value_at_open=True`), v1 arm, window
2019-01-01 to 2026-06-08, 93 rebalances, on the same three panels used throughout.

**THE CAUSE IS ARITHMETIC, NOT A FUNDING-ORDER BUG.** The `TOP_N` target weights
sum to 1.0, so `invest_val` alone commits 98% of portfolio value to eight names.
Buffer names — the up-to-eight more held because they are still inside `BUFFER`,
which is what stops the book churning — **carry no target weight at all** and yet
hold capital. So whenever a buffer name is held the book is over-committed by
construction and cash MUST be short. Reordering the buy loop cannot fix that; the
only levers are to give buffer names a target, to trim them, or to drop them.

**Five funding models were measured. The two that close the gap both cost
performance on every universe:**

| model | mid CAGR / blocked | n100 CAGR / blocked | 58 CAGR / blocked | trades |
|---|---|---|---|---|
| current — cash only | 44.69 / 93 | 34.60 / 120 | 23.83 / 137 | baseline |
| A trim over-target top-N only | 44.28 / 81 | 33.32 / 106 | 24.82 / 128 | +8-11% |
| B2 full target-weight, entrants first | 45.41 / 88 | 33.72 / 111 | 24.44 / 140 | +23-27% |
| B full target-weight, top-ups first | 46.73 / 100 | 31.80 / 123 | 24.00 / 154 | +25% |
| C also trim buffer names | 38.10 / **22** | 31.93 / **24** | 22.45 / **17** | +26-48% |
| D strict target-weight, no buffer | 42.37 / **0** | 27.94 / **0** | 20.33 / **0** | **+50%** |

Read it in three parts.

**Only C and D close the gap, and both are consistently worse.** D — the literal
`trade_i = target_i - current_i` across all held names, where a buffer name's
target is zero — reaches exactly zero skipped buys on all three universes. It does
so by dissolving the buffer, and costs **-2.32, -6.66 and -3.50 CAGR points** with
50% more trades. C keeps the buffer but trims it to fund entrants, which sells
drifted-up winners to buy lower-ranked entrants; it costs **-6.59, -2.67, -1.38**.

**The buffer-preserving models barely move the gap.** A, B and B2 change skipped
buys by about ±10%, because there is not enough over-target excess *inside* the
top eight to fund the entrants. **B is counterproductive**: topping up incumbents
before funding entrants raises skips from 93 to 100 on mid.

**And their CAGR effect has no consistent sign** — A is -0.41/-1.28/+0.99, B2 is
+0.72/-0.88/+0.61 across mid/n100/58. That is inside the seed-noise floor this
project measured at sd 0.97-2.14 CAGR points (`EXPERIMENTS.md` entry 29).

**One thing the gap does cost, measurably.** It is why the shipping engine holds a
mean book of 7.98 on mid — BELOW `TOP_N` — which is the failure
`results/validate_engine.py` reports as T1 on that universe. A, B2, C and D all lift
it back into `[TOP_N, BUFFER]`; B does not.

**Decision, 2026-09-04: not implemented.** This is a trade-off between churn
control and full funding, not a defect with a correct repair. Every model that
closes the gap degrades performance on all three universes, so selecting one after
seeing these numbers would be fitting the strategy to the result. If it is taken
up, it belongs in `experiments/` as a pre-registration with its gates written
first. `results/test_exposure.py` is unchanged by this entry.

---

## Breadth is validated on both live universes; sizing still is not

Found 2026-08-28. Breadth CLOSED 2026-08-29. The sizing half remains open.

Breadth sets total exposure at every rebalance — `expo = mean(mom_20 > 0)`, which
is why average deployment sits at 54–56% rather than 100% — and every published v2
and v4 figure depends on it entirely. Until 2026-08-29 it had been validated only
on the retired 58, by `results/validate_breadth.py`, which has never run on n100 or
mid.

**Closed by `results/validate_breadth_live.py`**, run on both universes on
2026-08-29 under `experiments/BREADTH_LIVE_SPEC.txt`. T1 and T2 are copied verbatim
from the 58's suite, thresholds included; the underived `dMaxDD > 3` bar was not
recalibrated for either universe.

    n100   3 of 3 gated criteria   PASS
    mid    3 of 3 gated criteria   PASS

Both universes pass, so the split-result clause of the spec did not fire.

**IT ALSO REPRODUCES SHIPPING v2 EXACTLY.** Its breadth arm returns CAGR 25.49 /
Sharpe 1.88 / MaxDD −18.64 on n100 and 30.22 / 2.06 / −18.98 on mid — identical to
v2 in `v34_comparison.csv` on all three headline figures in both universes.

**THIS IS THE IMPORTANT CONTRAST, AND IT DOES NOT APPLY TO SIZING.**
See *There are FIVE reimplementations of the backtest, not two* above for the
split itself; the point here is which side of it each validation sits on.

| | engine it runs on | covers production? |
|---|---|---|
| `validate_sizing.py` | `engine_core.backtest` | **NO** |
| `results/validate_breadth_live.py` | `test_exposure.backtest_exposure` | **YES** |

`validate_breadth_live.py` imports the SHIPPING engine and reproduces v2 to the
last printed digit, so its PASS is a statement about the code that actually runs.
`validate_sizing.py` imports the validation engine, which differs structurally from
production, so its 4-of-4 on n100 and 1-of-4 on mid say nothing directly about the
shipped inverse-vol sizing. **A reader must not generalise the breadth result to
the sizing result: they are validated against different engines.**

**Still open.** Bringing the sizing validation onto the shipping engine, and the
constant-exposure control (T3) remaining ungated by design — it was added after
v2's numbers were known, so gating on it would be choosing a criterion with the
data in view. Whether T3 ever becomes a gate is a separate pre-registered decision.

`results/validate_breadth.py` stays frozen on the 58 as the provenance of that
result, and keeps its `WINDOW FROZEN: retired universe` comment.

---

## engine_core.py's T3 splits the late half from the full panel, not the window

Found 2026-08-28. Open. Retired 58 only.

`engine_core.py:543`:

    hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)]

`px` is the whole panel, so the 2023-2026 half runs to the last date in the price
data rather than to the end of the backtest window. On the 58 that is 2026-06-08.
The full-period figures printed a few lines above come from `bd`, which is the
window. **So T3's late half and the full period end on different days in the same
report**, and nothing in the output says so.

The first half is unaffected — 2019-2022 is fully interior to any window in use.

**Not fixed, on instruction.** `engine_core.py` is the retired 58's provenance and
its published numbers must not move. The window there stays on the old year cut.

**The live equivalent WAS fixed.** `validate_sizing.py:225` now intersects the
half with the backtest window:

    hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                  & (px.index >= BT_START_DATE) & (px.index <= BT_END_DATE)]

so on n100 and mid the full period and the 2023-2026 half end on the same day.
The two files therefore differ deliberately, and this entry is the record of why —
without it, someone comparing them would reasonably conclude one was a mistake.

---

## The −0.30 concentration figure has no script behind it

Found 2026-08-27. Open. This is a provenance gap, not a wrong number.

`README.md` states that MidCap150's edge over its own buy & hold falls from 1.99
points to 0.02 when LLOYDSME is removed, and to −0.30 when TATAINVEST is removed as
well. It cites `experiments/EXP21_EXP22_PREREG.txt:84-85`, which is where the
figures are recorded. The prereg was written before the run that used them, so the
numbers are contemporaneous and there is no reason to doubt them.

**But nothing currently in the repository regenerates them.** The −0.30 is a
*cumulative* two-name removal, LLOYDSME and TATAINVEST together. Two scripts do
leave-one-out concentration work and neither performs that:

- `mid_jackknife.py:90` calls `edge([s])` — one name at a time, across all 148.
- `mid_topn_test.py:98` calls `run([s], top_n=t)` — also one at a time.

The script that almost certainly produced the pair was `exp21_exp22.py`, deleted in
the August 2026 experiment cleanup along with `diagnostics/exp21_exp22.txt`. Both
deletions are recorded in `experiments/EXPERIMENTS.md`.

**The capability survives; the invocation does not.** `mid_jackknife.edge()` takes
an arbitrary list, so `edge(["LLOYDSME", "TATAINVEST"])` is one line away. What is
gone is any recorded call, and with it the guarantee that such a call today would
return −0.30 at all: `mid_jackknife.py`'s own docstring quotes a baseline edge of
2.34 points against the current 1.99, so the panel underneath has moved since these
figures were taken. Re-running the removal now would produce a number, but it would
be a new measurement rather than a reproduction, and it should be recorded as one.

**Consequence.** A reader who wants to check the README's concentration claim
cannot, from this repository alone. The claim rests on a pre-registration rather
than on a re-runnable artefact. That is weaker evidence than everything around it
in that section, and the README does not currently say so.

### CORRECTION, 2026-09-02 — the concentration is now measured, and it names a different stock

`results/attribution_v2.py` computed per-symbol realised P&L for the shipping v2
arm on both live universes, by FIFO round-trip matching of the existing trade
logs. **No refit and no re-score**; window 2019-01-01 to 2026-05-29, 1,836
trading days, on the post-purge-fix artefacts of 2026-09-02.

**THE RECORDED CLAIM DESCRIBES A DIFFERENT NAME FROM TODAY'S TOP CONTRIBUTOR.**
The entry above is built on LLOYDSME as mid's dominant name. Measured:

| rank | symbol | net realised P&L | share of realised P&L |
|---|---|---|---|
| 1 | **TATAINVEST** | Rs 5,65,841 | **9.49%** |
| 2 | GVT&D | Rs 5,51,466 | 9.25% |
| 3 | APARINDS | Rs 5,35,822 | 8.99% |
| 4 | GODFRYPHLP | Rs 4,85,757 | 8.15% |
| 5 | AIIL | Rs 4,53,334 | 7.60% |
| **6** | **LLOYDSME** | Rs 4,31,669 | **7.24%** |

LLOYDSME is **sixth**, not first. **THE −0.30 FIGURE IS NOT RESTATED HERE AND
DOES NOT APPLY TO THIS MEASUREMENT.** It was a cumulative two-name edge removal
against buy & hold, on a different window and a different panel, with no
surviving script — all of which the entry above already records. The numbers in
this correction are a different quantity (share of realised P&L, not edge over
buy & hold) and neither supersedes nor confirms it.

**THE MEASURED CONCENTRATION, BOTH UNIVERSES.**

| | top 1 | top 3 | top 5 | top 10 | symbols traded |
|---|---|---|---|---|---|
| n100 | 11.67% | 27.76% | 39.61% | **61.24%** | 93 |
| **mid** | 9.49% | 27.73% | **43.48%** | **68.94%** | 122 |

**mid is roughly 8 points more concentrated than n100 at both the top-5 and
top-10 cuts, on a universe 50% larger** (148 names against 99). That is the
direction the record has always asserted, now with a number attached. It is also
the first time either universe's concentration has been quantified at all.

**WHAT THIS MEASUREMENT IS NOT.** Removing the top contributor arithmetically —
mid's realised P&L falls 9.5% without TATAINVEST, n100's falls 11.7% without
MAZDOCK — **is not the strategy re-run without that name.** The model would have
selected differently and the capital would have gone elsewhere. A true
leave-one-out requires re-running the engine, which `mid_jackknife.py` does and
this does not. The two must not be quoted interchangeably.

Artefacts: `diagnostics/attribution_v2.txt`,
`results_{n100,mid}/metrics/attribution_v2_per_symbol.csv` and
`attribution_v2_round_trips.csv`.

---

## The MidCap150 chart declares itself invalid, and is not

Found 2026-08-27. Open.

`results_mid/metrics/chart_mid_FINAL.png` renders with this as its first line:

> NOT A VALID RESULT -- PANEL DENSITY BLOCKER: only 148 of 148 names are scored,
> median 130 priced per day. idio_vol_60/beta_60 use rolling(60) on the UNION date
> index, so midcap non-trading days void 60 windows each; 32.9% of rows survive.
> Unpriced names forward-fill flat, so breadth reads 0.202 vs 0.550 on the 58 and
> deployment collapses to ~20%.

That text is built at `results/make_mid_chart.py:185-189`. The figures `32.9%`,
`0.202`, `0.550` and `~20%` are hardcoded string literals. They describe the panel
as it was before the `beta_60` / `idio_vol_60` density fix of 2026-08-13, which is
recorded in `nautilus/NAUTILUS_STATUS.md` and in `experiments/EXPERIMENTS.md`.

It contradicts its own chart. Two lines further down, at
`make_mid_chart.py:191`, the same subtitle prints `v2 holds {inv}% invested on
average`, and `inv` is read from the params file at run time. On the current
artefact that renders as 54%. So the image says deployment collapsed to about 20%
and then says it is 54%, in adjacent sentences.

What makes it worse: the surrounding text is live. `only 148 of 148 names are
scored` and `median 130 priced per day` are computed from the actual run. A reader
has no way to tell which half of the sentence is measured and which half is a
three-week-old literal, so the stale numbers borrow credibility from the live ones.

**Consequence.** Anyone who opens that PNG concludes the MidCap150 results are
void. The project treats them as valid — mid is one of the two live universes, it
reconciles against the Nautilus port on 93 of 93 rebalances, and its numbers are in
the README. The chart is the only thing in the repository still saying otherwise,
and it says it in 14-point type at the top of the image.

**Not fixed deliberately.** The stale text is evidence of when the density fix
landed and what it changed, and editing it away would remove that. Fixing it
properly means deciding whether the blocker note should be recomputed from the
current panel, rewritten as a dated historical note, or deleted — that is a
judgement about what the chart is for, not a typo correction.

**Consequence for the README.** `chart_mid_FINAL.png` is not embedded in
`README.md` while this stands. The published figure is
`docs/chart_COMBINED_n100_mid.png`, which covers mid and n100 together and carries
no stale text. If the mid chart is ever wanted on its own, this has to be resolved
first.

---

## A committed diagnostics artefact had gone stale against the panel it names

Found 2026-09-04, while verifying the registry conversions. The artefact is
corrected by this commit; **the class is open.**

`diagnostics/topn_verdict.txt`, `topn_n100.txt` and `topn_mid.txt` are the TOP_N
validation's evidence and are cited by `experiments/EXPERIMENTS.md`. Each one
prints the sha256 of the score panel it was computed from. **Those hashes did not
match the panels in the repository.**

| universe | panel sha256 in the committed artefact | panel sha256 today |
|---|---|---|
| n100 | `af9a28ac9e58032c...` | `163927a65e89165d...` |
| mid  | `aa277d1bd2c86774...` | `1e2d85df4d8fee73...` |

So the numbers on record were computed from a panel that is no longer the one
`results_n100/metrics/v_n100_expanding_cache.csv` and
`results_mid/metrics/v_mid_expanding_cache.csv` hold.

**THE PANELS DID NOT MOVE; THE ARTEFACT DID NOT KEEP UP.** Every
`results*/metrics/` directory was archived before any of this session's work
began, and both score panels compare **byte-identical** between that archive and
the tree afterwards. The staleness therefore predates this session and has nothing
to do with the registry conversions, the `frozen/` move or the valuation fix --
re-running `results/validate_topn.py` to verify a conversion is only what exposed
it. The artefact was regenerated at some point without the panel behind it being
regenerated too, or the reverse.

**What the refresh changes.** The verdict text does not move: TOP_N=8 is still
NOT CONTRADICTED on both live universes, and TOP_N=12 still holds the shallower
drawdown in the same measurement. The figures do:

| | n100 was | n100 now | mid was | mid now |
|---|---|---|---|---|
| CAGR% (TOP_N=8) | 25.49 | **25.78** | 30.22 | **29.70** |
| Sharpe | 1.88 | **1.86** | 2.06 | **2.03** |
| MaxDD% | −18.64 | **−19.87** | −18.98 | **−18.88** |
| dSharpe (8 minus 12) | +0.1900 | **+0.2000** | +0.1200 | **+0.0400** |
| trades | 981 | 978 | 973 | 963 |

**The mid dSharpe is the one to look at.** TOP_N=8's Sharpe advantage over
TOP_N=12 on the MidCap150 falls from +0.12 to **+0.04**. The pre-registered rule
in `experiments/TOPN_SPEC.txt` is not a threshold on that margin, so the verdict
stands as written -- but +0.04 is inside the seed-noise floor this project
measured at sd 0.97 to 2.14 CAGR points (`EXPERIMENTS.md` entry 29), and anyone
quoting the mid TOP_N result as evidence of a margin should quote this number
rather than the old one.

**Why this is filed as a class and not just a correction.** Nothing checks that a
diagnostics artefact still matches the panel it names, even though every one of
these three files prints the hash that would make the check trivial. The hash is
recorded and then never compared. The same gap is described from the other
direction in *An artefact was used three times without checking it was the one the
code reads*.

---

## chart_COMBINED_n100_mid.png is not byte-reproducible across sessions

Found 2026-09-04. `make_combined_n100_mid.py` saves with `bbox_inches="tight"`, and
the tight bounding box has been observed to differ by two pixels of height (1764 vs
1766) between sessions on identical inputs and identical code. The same file run
twice in one session is stable, so this is not run-to-run noise -- it drifts across
process invocations over time. The trigger was not identified; the matplotlib font
cache predates both runs. Nothing else about the chart changes and every printed
figure is identical. It matters only for byte-comparison: this PNG cannot be used
as a fixture.

---

## The 74's backtest window was the 58's, and agreed only by accident

Found and corrected 2026-09-04, while mapping the engine family onto
universes/registry.py.

`engine_v2_final74.py` cut its backtest window with `BT_START, BT_END = 2019, 2026`.
That 2026 is the **58's** end year. The file is a copy of `engine_v2_final.py` --
its own docstring says "Same strategy as engine_v2_final.py, run on the 74-stock
universe" -- and it carried the 58's literal for as long as it has existed.

**Everywhere the 74's window is stated per-universe, it says 2025**:
`make_cash_series.py` passes `2025`, `nt_run.py` records `"2025-12-23"` with a
comment explaining why, the daily audit passed `y_end=2025`, and
`universes/registry.py` records `year_range=(2019, 2025)`.

**The two rules agreed only by accident of the data.** The 74 panel ends
2025-12-23, so a 2019..2026 cut and a 2019..2025 cut select the same **1,732
trading days**. The discrepancy could not show itself, and would have diverged
silently the first time any 2026 row appeared for this universe -- from a data
refresh, or from the panel being rebuilt against a later source.

**Corrected to 2025.** Verified: `v2FINAL_comparison.csv`, `v2FINAL_equity.csv`,
`v2FINAL_yearly.csv`, `v2FINAL_params.json`, `daily_trades_v1_74.csv` and
`chart_v2FINAL.png` are all byte-identical after the change. No published 74 number
moves, which is what makes this safe to fix rather than something to leave recorded.

**The class is what matters.** A window literal copied between universes is
invisible while the shorter panel hides it. The other `BT_START, BT_END = 2019,
2026` sites -- `engine_core.py`, `engine_v2_final.py`, `reality_check.py`,
`validate_breadth.py`, `make_combined_all.py`, `make_stock_chart.py`,
`make_per_stock_charts.py` -- all serve the 58, whose panel really does end
2026-06-08, and are correct as they stand. This was checked rather than assumed.

---

## The Nautilus gate verified four arms it only had two of -- FIXED 2026-09-04

Found 2026-09-04 while surveying the port. **The gate now passes on four genuinely
distinct configurations; before this it did not have four to test.**

`nt_strategy.py` and `nt_attribution.py` both computed exposure as
`max(0, min(1, breadth))` unconditionally. There was no exposure mode, so
`mode="none"` -- the always-invested rule behind v1 and v3 -- could not be
expressed on the port side at all. `verify_v34_arms.ARMS` listed only the SIZING
rule, pairing v1 with v2 ("invvol") and v3 with v4 ("provol"), and ran each pair
twice. It printed `92 of 92 VERIFIED` for four arms while exercising two.

**The safety check in place could not catch it.** It set `nt_strategy.SIZING` and
`nt_attribution.SIZING` and asserted both globals held the intended value. That
proves the global was SET, never that the run USED it -- and the ignored exposure
mode is exactly the case that slips through: every sizing assert passed while the
mode was discarded.

**A NOTE ON PROVENANCE.** Comments in `verify_v34_arms.py` and `arms/registry.py`
cited "the fact recorded in KNOWN_ISSUES.md" for this. It was not recorded here --
the citation was written on the assumption it had been. This entry is that record,
created after the fact.

**What changed.** `sizing` and `mode` are passed as arguments --
`PredictiveEngineStrategy.configure(sizing=, mode=)` and
`nt_attribution.run(sizing=, mode=)` -- with the module globals removed. Defaults
are `invvol`/`breadth`, so every previous caller behaves exactly as before. Both
sides RECORD what they actually applied, on the branch actually taken, and the gate
asserts against that recording rather than against a global it set beforehand. An
arm whose configuration never reaches the decision point now fails.

**The 8-of-8 pass is real, and was checked for vacuity.** A port-versus-reference
gate would still pass if both sides changed identically and mode did nothing, so
v1 was measured against v2 directly on the n100:

| | v1 (`mode="none"`) | v2 (`mode="breadth"`) |
|---|---|---|
| mean exposure | **1.000000** | **0.565910** |
| final equity | Rs 9,197,640 | Rs 5,470,189 |
| orders submitted | 819 | 978 |
| rebalances holding identical positions | **1 of 92** | |

v1 and v2 are different portfolios on 91 of 92 rebalances. Both universes verify
92 of 92 on all four arms.

**ONE DIVERGENCE IS DOCUMENTED RATHER THAN FIXED.** `nt_strategy.rebalance()`
returns early when no symbol has momentum data (`if not mom: return`). Under
`mode="none"` the research engine never consults momentum, so on such a date it
would rebalance where the port skips. With `WARMUP_DAYS = 200` the case is not
expected to arise. The guard was left untouched deliberately: changing it would
change WHEN rebalances happen, which is a larger change than adding the exposure
mode, and it would have been made while changing something else.
