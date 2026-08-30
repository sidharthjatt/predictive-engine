# Known issues

Defects that are recorded but not fixed. Anything found and left alone belongs
here, with what it is, where it lives, and what a reader would wrongly conclude
because of it. Nothing in this file is a plan; it is a list of things that are
currently wrong.

---

## There are FIVE reimplementations of the backtest, not two

Found 2026-08-28 as two. Corrected to four on 2026-08-29, then to **five** later
the same day by the `run_all.py` audit. Open.

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
| retired audit | `results/make_stats_both.py`'s inline book | nothing reads its output — see below |
| cash series | `results/make_cash_series.py:42-70` inline book | **`run_all.py` STEP 13 → STEP 14** — see its own entry below |

The port reference is a deliberate re-implementation: `nt_verify` compares the
Nautilus port against it, and a reference that imported the engine it is checking
would prove nothing. It is counted here because it is a fourth place the rules are
written down, not because its existence is a mistake.

`make_stats_both.py` and `make_cash_series.py` are counted for the opposite
reason: nothing justifies either, and **both have already drifted** — the same
`CASH_Y = 0.06` in each. The difference between them is that
`make_stats_both.py`'s output is dead and `make_cash_series.py`'s is not.

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
- No test anywhere compares the two implementations directly. Their agreement is
  assumed, and the one place it was measured they were 1.80 points apart.
- `validate_sizing.py` already records that it cannot gate its baseline against a
  production artefact for exactly this reason. That limitation was written down;
  the broader consequence — that the validation does not cover what ships — was
  not, until now.

### The fourth one has drifted, on three constants at once

`results/make_stats_both.py` reimplements the backtest inline — it does not import
`backtest_exposure` — and it disagrees with production on three constants:

| | `make_stats_both.py` | everywhere else |
|---|---|---|
| `TOP_N`, `BUFFER` | **12, 24** (line 14) | 8, 16 |
| cash yield | **`CASH_Y = 0.06`** (line 15) | `CASH_YIELD = 0.0` (`test_exposure.py:61`) |

The divergence is visible on disk, same universe and same window: its
`v2_trades.csv` holds **1,193 fills against 883** in `daily_trades_74.csv`. The
74's own engine, `engine_v2_final74.py`, imports the real `CASH_YIELD` and prints
"Idle cash earns 0%", so the 6% is this script's alone.

It runs as **STEP 10 of `run_all.py`** (`run_all.py:275`), so it executes on every
full pipeline run.

**WHY IT IS NOT URGENT, WRITTEN DOWN SO THE NEXT READER NEED NOT RE-DERIVE IT.**
It is retired-universe only. Its docstring says "58 & 74" but there is no 58 call —
the sole invocation is `make_stats_both.py:115`, against the 74. It writes exactly
three files, all into `results74/metrics/`, and it is the sole writer of all three:
`v2_trades.csv`, `v2_per_stock_signals.csv`, `trade_stats_74.csv`.

**Nothing reads any of them.** Grep across `*.py`, `*.md`, `*.txt` and `*.json`
returns zero consumers; the only other appearances are `run_all.py` invoking it and
stale run logs echoing its own print line. **No figure in any document comes from
it** — none of its outputs (1,193 trades, 588 round trips, 63.6% win rate, profit
factor 2.9, Rs 1,46,612 total TC) appears in `README.md`, `HANDOFF_SUMMARY.txt`,
this file, `EXPERIMENTS.md`, or any diagnostics file. Verified by grep on
2026-08-29, statically, against the tree as it then stood.

So it has been generating figures at 12/24 for as long as the repository has
existed, and nobody has ever been shown one.

**IT IS NOT A ONE-LINE FIX, AND THAT IS WHY IT IS RECORDED RATHER THAN CORRECTED.**
Editing `12, 24` to `8, 16` would leave the 6% cash yield in place and produce a
**third** set of numbers, agreeing with neither the current artefact nor the 74's
official run. A real fix has to decide the cash yield too, and it moves a retired
universe's artefacts, which the freeze policy governs. It is also a fourth engine:
correcting its constants does not stop it from drifting again, only deleting it or
making it import the shipping engine would.

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

## STEP 2's leakage checklist performs no checks

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

## make_cash_series.py runs a 6% cash yield, and its output reaches a consumer

Found 2026-08-29 by the `run_all.py` audit. Open.

`results/make_cash_series.py:16` sets

    SLIP,CAP,CASH_Y=0.0015,1_000_000,0.06

against `CASH_YIELD = 0.0` in `results/test_exposure.py:61` and everywhere else.
It is applied at line 42 as `cd=(1+CASH_Y)**(1/252)-1` and compounded onto cash
every day of the run. It is the **same 6% literal** that `make_stats_both.py:15`
carries, in a second script.

**UNLIKE `make_stats_both.py`, THIS OUTPUT IS LIVE.** That is the whole
difference between the two, and it is why this has its own entry.

| step | what happens |
|---|---|
| STEP 11 | `make_cash_series.py` writes `cash_series_58.csv`, `cash_series_74.csv` |
| STEP 13 | `make_final_chart_fair.py:74-76` reads both |
| | `:119-123` and `:182` use `cash_pct` for average deployment and the "on deployed capital only" return |
| | writes `fair_comparison_table.csv` and the final chart's subtitle |
| STEP 14 | `make_final_summary.py:13` reads `fair_comparison_table.csv` |

A 6% yield inflates the cash leg, so those deployment percentages describe a
portfolio earning interest the shipping engine does not pay. **This is a wrong
number reaching a consumer**, which the `make_stats_both.py` defect is not.

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
