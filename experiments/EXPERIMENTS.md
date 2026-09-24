# EXPERIMENTS — the complete record

> **THE 58 AND THE 74 WERE DELETED ON 2026-09-11.** Both universes, their raw
> data, their registry entries and the 26 scripts that served them are gone from
> this repository. Every reference to them below is **historical**: it records what
> was measured and when, and none of it can be re-run. The figures are preserved at
> full precision, with a SHA-256 manifest of every surviving artefact, in
> [RETIRED_UNIVERSES.md](../RETIRED_UNIVERSES.md). Where a passage names a deleted file, it is
> describing what that file did, not something you can run.

This is the only experiment record. It replaces the per-experiment scripts and
result files, which are deleted. Everything needed to understand what was tried,
why, under what rule, and with what result is here.

Written 2026-08-22.

**Read this before proposing anything.** The point of this file is that no idea
below is retried without a new pre-registration that carries the full trial count.
A rejected idea is not a shelf item waiting for a better day; it is a closed
question with evidence attached.

---

## Contents

- [How to read this file](#how-to-read-this-file)
- [The system these were run against](#the-system-these-were-run-against)
- [Three standing conclusions](#three-standing-conclusions)
- [The trial count, and why it does not reconcile](#the-trial-count-and-why-it-does-not-reconcile)
- [Summary table](#summary-table)
- [The experiments, 1 to 26](#the-experiments-1-to-26)
- [What is closed, and what is not](#what-is-closed-and-what-is-not)
- [Provenance of every number in this file](#provenance-of-every-number-in-this-file)

---

## How to read this file

Each entry has the same six parts:

1. **What it did** — the mechanism, in enough detail to reimplement without the
   script.
2. **Why it was worth testing** — the reasoning as it stood at the time, not
   hindsight.
3. **The accept rule** — quoted verbatim from the pre-registration where one
   survives, paraphrased and marked as such where none does.
4. **The result** — measured numbers.
5. **Verdict** — and which gate failed.
6. **What it taught** — the part that outlives the verdict.

Where evidence is thin, the entry says so in bold rather than filling the gap
with a plausible reconstruction. Three early entries (1, 2, 8) are named in
`HANDOFF_SUMMARY.txt` but have no surviving mechanism or numbers, and two
(15, 16) were recovered from a session transcript rather than from an original
report. These are flagged individually.

---

## The system these were run against

Every experiment below is a change to one part of this and nothing else. Where an
experiment says "everything else unchanged", this is what was unchanged.

| | |
|---|---|
| model | LightGBM, cross-sectional ranking |
| features | 17 (`FEATS_V2`) |
| ensemble | 10 seeds |
| walk-forward | monthly, expanding window |
| purge | 32 days |
| selection | `TOP_N=8` held, `BUFFER=16` (a held name is sold only when it falls out of the top 16) |
| horizon / rebalance | `HORIZON=REBAL=20` trading days |
| sizing v1 | inverse-vol, always 100% invested |
| sizing v2 | inverse-vol, scaled by breadth exposure |
| vol window | `VOL_WIN=60` |
| exposure (v2) | at every 20th day, `expo = mean(mom_20 > 0)` across the universe, clipped to [0,1] |
| cash | `SAFETY=0.98`, `CASH_YIELD=0.0` |
| costs | Zerodha schedule + `SLIPPAGE=0.0015` |
| capital | `START_CAPITAL=1,000,000` |

Two properties of the baseline matter repeatedly below:

- **Existing holdings are never resized.** Only new positions are sized against
  the target exposure, so actual invested percentage drifts from target. This is
  the mechanism behind entry 25.
- **Average deployment is about 55%**, because breadth is usually well below 1.
  This is the complaint that motivated entries 3–9, 15, 16 and 17, and it was
  never fixed.

### A note that applies to entries 1–17

All verdicts up to and including EXP17 were measured on a panel produced **before
the `beta_60` / `idio_vol_60` feature-density fix of 2026-08-13**. That bug
computed both features with `rolling(60)` over the union date index, so a symbol
that did not trade on a union date lost its next 60 windows and those rows were
dropped from training. The baseline moved when it was fixed:

```
58 universe : CAGR 16.45% -> 13.16%   Sharpe 1.36 -> 1.11
74 universe : CAGR 14.65% -> 15.22%   Sharpe 1.27 -> 1.35
```

**The verdicts are not withdrawn.** Both arms of every experiment used the same
panel, so each comparison stays internally valid; what moved is the baseline they
sit against, not the contrast between arms.

**They are deliberately not re-run.** Re-testing seventeen hypotheses on a new
panel to see whether any now passes is exactly the multiple-testing failure that
pre-registration exists to prevent. Any re-test needs its own pre-registration,
written before the numbers are seen, carrying the full trial count.

### A note on universes

The project ran on four universes over its life: **58** (a Nifty-50-derived set),
**74**, **mid** (MidCap150) and **n100** (Nifty 100). Entries 1–17 were tested on
58 and 74. **58 and 74 were dropped from the project during EXP18**, which is why
EXP18 has an unmeasured gate and why EXP20 onward report only mid and n100. That
scope change is a project decision, not an experimental result, and it is
recorded in the entries it affected.

---

## Three standing conclusions

These are the conclusions that survive all twenty-five tests, recorded verbatim.

> The exposure and portfolio-construction family is closed. Twelve early ideas
> plus EXP15, 16 and 17 all failed. The Fundamental Law explains why:
> IR ≈ IC × √BR, and exposure timing changes neither term.

> EXP22's premise was refuted, not just rejected — no position ever reached 20%
> of portfolio value (max 19.69%), so no weight cap at any threshold can address
> mid's concentration. That closes an entire remedy family.

> EXP18 fixed the IC inversion exactly as predicted and made performance worse,
> so a positive IC does not imply better performance in this system.

And a fourth, which qualifies the other three:

> The pre-registrations' own trial counts do not reconcile with each other. The
> true number of looks at this dataset is **at least 25**, not the 23 the later
> preregs assumed — the count understates by **at least two** — and the
> discrepancy runs toward **more** looks rather than fewer, so every
> multiple-testing argument in this project was made against an understated
> denominator.

---

## The trial count, and why it does not reconcile

The pre-registrations maintained a running trial count, and **it drifted**. The
counts each document claims for itself:

| document | claims |
|---|---|
| `rejected_experiments_REPORT.txt` | "OVERALL: 11 rejected, 1 accepted" (12) |
| `HANDOFF_SUMMARY.txt` §4 | "Total: 12 REJECTED, 1 ACCEPTED" (13) |
| `EXP14_PREREG.txt` | "This is the 14th tested idea (13 so far)" |
| `EXP14_REPORT.txt` | "(17th idea tested" |
| `EXP17_PREREG.txt` | "the 18th tested idea. 17 tested so far" |
| `EXP18_EXP19_PREREG.txt` | "the 20th and 21st. 19 tested so far" |
| `EXP20_PREREG.txt` | "the 21st. 20 tested so far" (EXP19 never ran, so EXP20 took slot 21) |
| `EXP21_EXP22_PREREG.txt` | "the 22nd and 23rd. 21 tested so far" |

**This file lists 29 entries, of which 28 were actually run.** Entry 27 was added
2026-08-29 and counts like any other: a validation is still a trial. The excess
over the
preregs' final "23" is not an error in the preregs so much as an accounting
difference with three identifiable causes:

1. **EXP14's count jumped by four, not one** (14th → 17th), because its four
   candidate features were charged as four trials rather than one experiment.
   Everything after inherits that jump.
2. **Three early ideas are named in `HANDOFF_SUMMARY.txt` but never entered the
   `rejected_experiments_REPORT.txt` tally**: the fraction rule, the long-short
   variant, and "percentile + smoothing". They were tested; they were not counted.
3. **The sizing test (entry 26) was never counted at all.** It is a
   pre-registered experiment with a four-gate accept rule, run around 2026-08-13,
   and no prereg written afterwards includes it in its running total. It was found
   on 2026-08-23 during a cleanup audit, in a script that had already been deleted
   once and was restored from backup.

The direction of the discrepancy is the one that matters:
**the real number of looks at this dataset is at least 25, not 23.** The
multiple-testing bar is therefore higher than every pre-registration assumed,
never lower. No verdict changes — every rejection stays a rejection, and the one
acceptance (entry 10) was an early trial when the count was low.

"At least" is meant literally. Two of the twenty-nine entries have no surviving
mechanism (1, 8), one has no surviving verdict (26), and the count was
demonstrably wrong three separate times. **Treat 28 as a floor, not a
measurement.**

---

## Summary table

| # | Name | Family | Verdict | Failed at |
|---|---|---|---|---|
| 1 | Fraction rule | exposure | REJECT | *no record* |
| 2 | Long-short | construction | REJECT | *no record (2526% CAGR bug)* |
| 3 | sqrt breadth | exposure | REJECT | Sharpe + drawdown |
| 4 | Median breadth | exposure | REJECT | Sharpe + drawdown |
| 5 | Conditional cut 0.20 | exposure | REJECT | Sharpe, both universes |
| 6 | Conditional cut 0.30 | exposure | REJECT | Sharpe, both universes |
| 7 | Percentile exposure | exposure | REJECT | mixed across universes |
| 8 | Percentile + smoothing | exposure | REJECT | *no record* |
| 9 | Breadth delta k=1/2/3 | exposure | REJECT | Sharpe + sub-periods |
| **10** | **Top-8 from top-12** | **concentration** | **ACCEPT** | **— passed all** |
| 11 | Dynamic IC concentration | concentration | REJECT | Sharpe, both universes |
| 12 | EWMA vol 0.94 / 0.97 | features | REJECT | Sharpe + validation 4/4→1/4 |
| 13 | EWMA horizon-matched | features | REJECT | validation still 1/4 |
| 14 | Multi-signal equal weight | signal comb. | REJECT | combined IC negative |
| 15 | IC-weighted combination | signal comb. | REJECT | IC far below the model |
| 16 | Training scheme 2×2 | training | REJECT | expanding + uniform already best |
| 17 | EXP14 high/low intraday | features | REJECT | Gate 2 (standalone raw IC) |
| 18 | EXP15 panic exit | exposure | REJECT | Sharpe and MaxDD on 58 |
| 19 | EXP16 index trend gate | exposure | REJECT | Sharpe at every N; MaxDD flat |
| 20 | EXP17 dispersion tilt | exposure | REJECT | Gates B and C |
| 21 | EXP18 sign-stability filter | ranking | REJECT | Gate B (all three universes) |
| 22 | EXP19 sign-corrected features | ranking | **NOT RUN** | — |
| 23 | EXP20 tradeability filter | execution | REJECT | Gate C (2023–2026 sub-period) |
| 24 | EXP21 redeploy unfilled cash | execution | REJECT | Gate D (shortfall) |
| 25 | EXP22 position trim at 20% | construction | REJECT | Gate D (premise refuted) |
| 26 | Sizing: equal-rupee vs inverse-vol | sizing | **VERDICT UNKNOWN** | never recorded |
| 27 | TOP_N=8 revalidation vs 12 | concentration | **NOT CONTRADICTED** | held 6 of 6; 12 had shallower MaxDD, ungated |
| 28 | Shuffle test (permutation null) | significance | **PASS** | 4 of 4 gated, p = 0.0099, 0 of 100 beat |
| 29 | Seed noise floor (40 seeds, sub-ensembles) | stability | **FLOOR MEASURED** | sd 0.97-2.14 CAGR at K=10; purge result inconclusive |
| 30 | Rebalance cadence sweep, v2, REBAL 5/10/20/40 | cadence | **NO CADENCE QUALIFIES** | none beats 20 outside the seed floor on both universes; universes disagree on sign at 10 and 40 |
| 31 | Cadence grid, all four arms, REBAL 5/10/20/40/60 | cadence | **ONLY v2 HAS A VERDICT** | 8 of 8 controls reproduce; 0 cells with a measured floor beat control on both; 6 v3/v4 cells UNKNOWN (no floor ever measured) |
| 32 | Audit flag A/B on the shipping engine | verification | **CLAIM VERIFIED** | max abs difference 0.0 across 73,440 equity values, 40 cells; a docstring comment became a measurement |
| 33 | Portfolio drawdown exit, 10/12.5/15/20/25% | risk rule | **SPEC WAS WRONG** | re-entry unsatisfiable by construction: one exit, zero re-entries, 84% of the window flat; CAGR −24.6 to −31.5; every trigger in one week of March 2020 |
| 34 | Drawdown exit rev 2, time-only re-entry, waits 5/20/40 | risk rule | **OSCILLATES SIX YEARS** | 77 exits / 76 re-entries; re-enters while still in breach; WORSE than rev 1 on n100 — sitting out the bull market beat whipsawing through it |
| 35 | Drawdown exit rev 3, peak reset at re-entry | risk rule | **NON-DEGENERATE, STILL UNJUDGEABLE** | 77 exits → 4; flat 84% → 1-10%; CAGR within ~2 points, 10 of 30 cells INSIDE the floor; 4 positive cells are inside the floor and are NOT findings; MaxDD still has no floor on any arm |

One acceptance in twenty-eight trials, and one trial whose outcome was never
written down. Entry 27 is not a second acceptance: it revalidates entry 10's
choice and promotes nothing.

---

## The experiments, 1 to 26

---

### 1. Fraction rule

**EVIDENCE IS THIN.** This idea is named in `HANDOFF_SUMMARY.txt` under "EARLIER
SESSIONS" and nowhere else. No mechanism, no accept rule and no numbers survive.

**What it did.** Not recoverable. The name indicates an exposure rule expressed as
a fraction of capital rather than the breadth mapping, but the exact form is
**not recorded and is not reconstructed here.**

**Why it was worth testing.** Not recorded. It predates the pre-registration
discipline.

**The accept rule.** None survives. It predates pre-registration.

**The result.** Not recorded, beyond the verdict.

**Verdict.** REJECTED.

**What it taught.** Nothing that can be stated from evidence. Its value in this
record is negative rather than positive: it is a look at the dataset that the
running trial count never charged, which is part of why the count in the preregs
understates the multiple-testing burden. If the idea recurs, it must be treated
as untested and pre-registered fresh — not as "already rejected", because there
is no evidence to reject it with.

---

### 2. Long-short

**EVIDENCE IS THIN.** Named in `HANDOFF_SUMMARY.txt` as "long-short (the 2526%
CAGR bug)". The verdict and the bug survive; the mechanism and gates do not.

**What it did.** Took short positions in the bottom of the cross-sectional
ranking alongside the long book, rather than holding cash. **The exact
construction — how many shorts, how sized, whether market-neutral — is not
recorded and is not reconstructed here.**

**Why it was worth testing.** A ranking model produces a full ordering. Using only
the top of it discards the information in the bottom. A long-short book uses both
ends and, in principle, doubles the breadth term in IR ≈ IC × √BR without needing
a larger universe.

**The accept rule.** None survives. It predates pre-registration.

**The result.** The implementation produced a CAGR of **2,526%**, which is not a
result but a bug signature. The number is recorded because the episode is the
origin of a rule that governs everything after it.

**Verdict.** REJECTED, on a broken implementation. Note carefully: **this is a
rejection of an implementation, not a refutation of long-short as an idea.** The
question of whether a long-short book helps was never answered on this dataset.

**What it taught.** This is the most consequential entry in the early record, and
the lesson is procedural rather than empirical. A result that looks spectacular is
evidence of a bug, not of an edge, and it must be treated that way before it is
treated as a finding. Every pre-registration written afterwards puts sanity checks
and causality evidence *before* performance numbers, and several say so explicitly
— `EXP14_PREREG.txt` orders its gates "sanity checks before performance numbers,
per the lesson from the long-short bug and the EWMA episode". The 2526% number is
why EXP18 and EXP20 can be declared VOID on causality evidence alone, before any
Sharpe is computed.

---

### 3. sqrt breadth

**What it did.** Replaced the exposure map `expo = breadth` with
`expo = sqrt(breadth)`. Recomputed at every 20-day rebalance, clipped to [0,1].
Nothing else changed.

**Why it was worth testing.** Breadth is a fraction in [0,1] and averages about
0.55, so the linear map leaves the system roughly half in cash across the whole
backtest. A concave map raises exposure everywhere except at the extremes — at
breadth 0.36, sqrt gives 0.60 — so it recovers deployment while preserving the
ordering of the signal. If breadth's information is in its *ranking* of market
states rather than its *level*, any monotone map should do as well, and the
concave one deploys more capital.

**The accept rule.** No standalone prereg survives. The rule stated in
`rejected_experiments_REPORT.txt` for the whole early block, verbatim:

> Accept rule pehle se tay: dono universe pe Sharpe behtar + dono halves pass.
>
> *(Accept rule fixed in advance: Sharpe better on both universes + both halves
> pass.)*

`HANDOFF_SUMMARY.txt` records the exposure family's rule with the drawdown clause:
"Sharpe must not fall in either universe, both sub-periods must pass, drawdown
must not worsen."

**The result.** 58 universe: **Sharpe 1.43 → 1.19**, MaxDD **−20% → −27%**.

**Verdict.** REJECTED. Sharpe fell hard and drawdown worsened by 7 points.

**What it taught.** The extra deployment was not free. Raising exposure in
low-breadth states is raising it in exactly the states breadth was flagging as
bad, and the drawdown cost of that exceeded the return gain by a wide margin.
The level of breadth carries information, not just its ordering.

---

### 4. Median breadth

**What it did.** Mapped exposure through breadth's position relative to its own
trailing median rather than its raw level. **The precise functional form is not
recorded** beyond the name; the report gives only the outcome.

**Why it was worth testing.** Direct successor to entry 3. If the raw level of
breadth is regime-dependent — if 0.5 means something different in 2019 than in
2023 — then a relative measure is the scale-free version of the same signal and
should be more stable across the backtest.

**The accept rule.** As entry 3 (the early-block rule).

**The result.** 58 universe: **Sharpe 1.43 → 1.13**, MaxDD **−30%**.

**Verdict.** REJECTED. Worse than entry 3 on both metrics.

**What it taught.** Normalising breadth against its own history destroyed more
than it fixed. A trailing median is itself a slow signal, so the rule spends long
stretches on the wrong side of a stale threshold, and the drawdown at −30% is
nearly double the baseline's −16.63%.

---

### 5. Conditional cut at 0.20

**What it did.** Kept the linear breadth map, but added a conditional gate: below
a breadth percentile of 0.20, exposure is cut. **The size of the cut is not
recorded**; the mechanism is a percentile gate, not a level gate.

**Why it was worth testing.** Entries 3 and 4 changed the map everywhere. This
changes it only in the tail, where the measured evidence is strongest: low-breadth
states genuinely precede bad returns. A rule that only acts in the worst 20% of
states makes a smaller claim and risks less.

**The accept rule.** As entry 3.

**The result.** 58: **Sharpe 1.54 → 1.50.** 74: **Sharpe 1.45 → 1.37**, drawdown
**−21.3%**.

**Verdict.** REJECTED. Sharpe fell in both universes.

**What it taught.** Even a rule confined to the tail lost. Cutting exposure in the
worst states removes the recovery as well as the decline, and the recoveries out
of low-breadth states are sharp enough that missing them costs more than the
decline avoided.

---

### 6. Conditional cut at 0.30

**What it did.** Entry 5 with the percentile gate at 0.30 instead of 0.20.

**Why it was worth testing.** Entry 5 acted too rarely to help; widening the gate
tests whether the mechanism was right and the trigger merely too rare. Recorded
honestly: **this is the one entry in the early block that is a threshold variant
of its predecessor**, which is the pattern later pre-registrations forbid
("no variants", "one batch").

**The accept rule.** As entry 3.

**The result.** 58: **Sharpe 1.54 → 1.50.** 74: **Sharpe 1.45 → 1.43.**

**Verdict.** REJECTED. Sharpe fell in both universes.

**What it taught.** Widening the gate moved the answer barely at all — 74 went
from 1.37 to 1.43, still below 1.45. The failure was not the threshold. That
result is the empirical basis for the later rule that threshold variants are not
run: the two thresholds agreed, and both lost.

---

### 7. Percentile exposure

**What it did.** Exposure set to breadth's causal percentile rank within its own
trailing history, rather than to breadth itself.

**Why it was worth testing.** The scale-free version of entry 4 done properly —
a full percentile rank rather than a median split, so the rule uses the whole
distribution and spans [0,1] by construction.

**The accept rule.** As entry 3.

**The result.** 58: **Sharpe 1.54 → 1.52.** 74: **Sharpe 1.45 → 1.50.**
Mixed — one universe up, one down.

**Verdict.** REJECTED. The rule requires improvement in *both* universes;
disagreement across universes is a rejection.

**What it taught.** This is the record's first clean instance of **disagreement
across universes as a noise signature**, and the reason the two-universe rule
exists. A change that helps one universe and hurts the other is not a small
positive result — it is a draw from noise, and accepting it would be selecting the
universe that agreed. The same signature reappears at entries 18 and 20.

A diagnostic run alongside this attempt settled a separate question, recorded here
because it is load-bearing:

> minInv 0.0%, maxInv 99.6%. The system ALREADY uses the full 0-100% range.
> 64.6% is only the 7.4-year average. The problem is timing, not range.

That removed "the system is structurally under-invested" as a hypothesis. Every
later exposure attempt is a timing claim, not a range claim.

---

### 8. Percentile + smoothing

**EVIDENCE IS THIN.** Named in `HANDOFF_SUMMARY.txt`'s exposure list. No numbers
survive in any document.

**What it did.** Entry 7's percentile exposure with the resulting series smoothed
before use. **The smoothing window and method are not recorded.**

**Why it was worth testing.** Entry 7 was the closest of the exposure attempts —
58 fell only 0.02 and 74 rose. If the residual loss was turnover-driven jitter in
the exposure series rather than a defect in the signal, smoothing removes it
without changing the signal.

**The accept rule.** As entry 3.

**The result.** Not recorded beyond the verdict.

**Verdict.** REJECTED.

**What it taught.** Nothing statable from evidence. Like entry 1, its role here is
to be counted: it is a look at the dataset that the running tally missed.

---

### 9. Breadth delta, k = 1 / 2 / 3

**What it did.** Set exposure from breadth's *level* and its *direction* together:
the change in breadth over the previous k rebalances is added to the level, with
k tested at 1, 2 and 3.

**Why it was worth testing.** Every attempt so far used breadth's level at a point
in time. Its first difference is genuinely new information from the same series —
breadth at 0.5 and rising is a different state from breadth at 0.5 and falling —
and it costs no new data.

**The accept rule.** As entry 3.

**The result.** 58 Sharpe **1.54 → 1.53 / 1.47 / 1.43** for k = 1 / 2 / 3.
On 74, the baseline won in **both** sub-periods (2.30 vs 1.98 in the stronger one).

**Verdict.** REJECTED. Monotonically worse as k grows.

**What it taught.** This was declared the last exposure attempt, and the report
says so at the time:

> (6th and final attempt on exposure. Breadth signal is fully extracted;
> linear mapping is its optimal use. Question closed.)

The monotonicity is the informative part: performance degrades smoothly as more
weight goes on the delta, which is what a pure-noise addition looks like. There is
no k at which it turns.

**The closure did not hold.** Entries 18, 19 and 20 (EXP15, EXP16, EXP17) reopened
the exposure question three more times, and all three failed. That is worth
knowing when reading any future "question closed" in this project.

---

### 10. Top-8 from top-12 — **ACCEPTED**

**What it did.** Reduced the held book from the top 12 ranked names to the top 8,
with `BUFFER=16` — a held name is sold only when it drops out of the top 16, so
turnover does not rise with the tighter selection. This is the current production
setting.

**Why it was worth testing.** The model's IC is a property of its *ranking*. If
the ranking has real information, the top 8 should be better than names 9–12, and
holding those four dilutes the book with the model's weakest convictions. The
counter-argument is breadth: fewer names means less diversification and, by
IR ≈ IC × √BR, a lower √BR. The test asks which term dominates at this scale.

**The accept rule.** As entry 3 — Sharpe better in both universes, both halves
pass.

**The result.** 58: **Sharpe 1.43 → 1.54.** 74: **Sharpe 1.28 → 1.45.**

**Verdict.** **ACCEPTED.** The only acceptance in twenty-eight trials. Both
universes improved, and by a large margin — 0.11 and 0.17 of Sharpe.

**What it taught.** The concentration gain beat the diversification loss, which
says the model's ranking is genuinely informative at the top and that names 9–12
were diluting it. Note where this acceptance sits: it is an early trial, tested
before the count grew large, and it improved both universes substantially rather
than marginally. Compare with entry 7, which moved 58 by 0.02 in the wrong
direction and 74 by 0.05 in the right one and was rejected. **The one thing that
worked did not need a fine judgement call.** That is the shape of a real effect in
this project, and it is the calibration to hold everything else against.

---

### 11. Dynamic concentration (IC-based)

**What it did.** Varied the number of held names over time according to the
model's recent IC — hold more names when IC is low, fewer when it is high.

**Why it was worth testing.** The direct extension of entry 10. If concentrating
to 8 helps because the ranking is informative, then concentration should track
*how* informative the ranking currently is. When IC is high, lean into the top;
when IC decays, spread out. This is the theoretically correct version of what
entry 10 did with a fixed number.

**The accept rule.** As entry 3.

**The result.** 58: **Sharpe 1.54 → 1.39.** 74: **Sharpe 1.45 → 1.27.**

**Verdict.** REJECTED. Both universes fell, and by more than entry 10 gained.

**What it taught.** The theoretically better version of an accepted idea lost to
the fixed rule. The reason is measurement: trailing IC is estimated from a short
window and is itself extremely noisy, so the rule spends its time reacting to
estimation error rather than to real changes in signal quality. **A parameter
that should be adaptive in theory is better fixed when the quantity it adapts to
cannot be measured precisely.** This is a general result about this system and it
recurs — entry 21 (EXP18) fails for a related reason.

---

### 12. EWMA volatility, λ = 0.94 / 0.97

**What it did.** Replaced the rolling standard deviation in `vol_20` and `vol_60`
with an exponentially weighted moving standard deviation, using the RiskMetrics
pair: λ = 0.94 for the short window, λ = 0.97 for the long one.

Two λ values were required, not one, and the reason is recorded because it is not
obvious: **EWMA has no window, only a decay.** A single λ applied to both features
makes `vol_20` and `vol_60` identical, which makes the derived `vol_ratio` a
constant 1 and destroys that feature outright.

**Why it was worth testing.** EWMA is the standard tool for volatility estimation
and is what RiskMetrics designed for the purpose. A rolling window weights a
60-day-old observation exactly as heavily as yesterday's, then drops it entirely
on day 61 — a step function that produces artefacts when a large move rolls out of
the window. Exponential weighting is smooth and gives recent data more weight,
which is what volatility clustering says it should have.

**The accept rule.** As entry 3, plus the standing inverse-vol validation suite:
T1 baseline, T2 seed robustness, T3 sub-period split, T4 parameter sensitivity,
scored out of 4.

**The result.** Full runs on both universes, ~142 minutes each.

| variant | line | CAGR% | Sharpe | MaxDD% | Calmar | CAGR/invested% |
|---|---|---|---|---|---|---|
| A rolling std | 58 v2 | 18.80 | 1.54 | −16.63 | 1.13 | 29.12 |
| A rolling std | 58 v1 | 24.14 | 1.27 | −32.88 | 0.73 | 24.14 |
| A rolling std | 74 v2 | 16.94 | 1.45 | −17.02 | 1.00 | 26.24 |
| A rolling std | 74 v1 | 19.42 | 1.08 | −29.90 | 0.65 | 19.42 |
| **B EWMA .94/.97** | 58 v2 | **15.54** | **1.36** | −18.20 | 0.85 | 25.43 |
| B EWMA .94/.97 | 58 v1 | 18.63 | 1.00 | −36.82 | 0.51 | 18.63 |
| **B EWMA .94/.97** | 74 v2 | **13.83** | **1.20** | −19.24 | 0.72 | 20.51 |
| B EWMA .94/.97 | 74 v1 | 16.41 | 0.89 | −39.95 | 0.41 | 16.41 |

Validation: **A scored 4/4. B scored 1/4** — T1 pass, T2 seed robustness FAIL,
T3 sub-period FAIL, T4 parameter sensitivity FAIL.

**Verdict.** REJECTED. Worse on every metric in both universes, and the
inverse-vol sizing edge stopped validating.

**What it taught.** A defect in the test itself was found *after* the run, and it
is why entry 13 exists. Centre-of-mass for an EWMA is λ/(1−λ):

```
0.94 -> 15.7 days   (was 20)
0.97 -> 32.3 days   (was 60)   <-- the long window was silently halved
```

So variant B changed the weighting **and the horizon** at once. It is not a clean
test of exponential weighting; it is a test of exponential weighting confounded
with a halved long window. **The result cannot be attributed.** That is what
prompted the horizon-matched re-run.

---

### 13. EWMA volatility, horizon-matched λ = 0.9524 / 0.9836

**What it did.** The same substitution as entry 12, with λ chosen as W/(W+1) so
the centre of mass matches the rolling window exactly: λ = 0.9524 gives a 20-day
centre of mass, λ = 0.9836 gives 60 days. Same horizon as rolling; **only the
weighting changes.** This is the clean test that entry 12 was not.

**Why it was worth testing.** Entry 12's result was uninterpretable because two
things changed together. This isolates the one that was actually being proposed.

**The accept rule.** As entry 12.

**The result.**

| variant | line | CAGR% | Sharpe | MaxDD% | Calmar | CAGR/invested% |
|---|---|---|---|---|---|---|
| **C EWMA matched** | 58 v2 | 16.76 | **1.45** | −18.24 | 0.92 | 26.63 |
| C EWMA matched | 58 v1 | 20.06 | 1.07 | −39.00 | 0.51 | 20.06 |
| **C EWMA matched** | 74 v2 | 15.03 | **1.28** | **−16.69** | 0.90 | 22.25 |
| C EWMA matched | 74 v1 | 18.44 | 1.01 | −36.76 | 0.50 | 18.44 |

Reference points from the same run: 58 buy&hold 18.65 / 1.06 / −39.80;
74 buy&hold 23.97 / 1.29 / −38.29; Nifty100 over the 58 window 23.05 / 1.29;
over the 74 window 25.04 / 1.39.

Validation: **C also scored 1/4** — T1 pass, T2, T3 and T4 all FAIL.

**Verdict.** REJECTED. C beat B (58 v2 Sharpe 1.36 → 1.45), confirming that part
of B's damage came from the shortened horizon — but C is still behind rolling on
every metric in both universes **except** 74's MaxDD.

**What it taught.** Three things, and the second is the durable one.

1. The confound was real and measurable. Isolating it recovered 0.09 of Sharpe
   on 58. Diagnosing a confounded test and re-running it clean is worth doing even
   when the verdict does not change.
2. **The headline numbers were not what decided it — the validation suite was.**
   With rolling volatility, inverse-vol sizing passes seed robustness, sub-period
   split and window sensitivity. With *either* EWMA variant, all three fail: the
   sizing edge becomes seed- and window-dependent. A Sharpe of 1.45 that does not
   survive a change of seed is not a Sharpe of 1.45.
3. On deployed capital, 74 v2 falls from 26.24% (rolling, above the 25.04%
   benchmark) to 22.25% (EWMA, below it) — it crosses from beating its benchmark
   to losing to it.

Breadth validation passed in all three variants, which locates the loss precisely:
**in the model's ranking, not in the exposure overlay.**

The decision recorded at the time:

> Rolling std kept. EWMA is the better tool for risk measurement (that is what
> RiskMetrics designed it for), but here the features feed a cross-sectional
> ranking model, and the fixed-window definition appears to compare more cleanly
> across stocks.

That last clause is the real finding. **A better estimator of a quantity is not
automatically a better feature for a cross-sectional model.** The model does not
consume the volatility estimate; it consumes the *ordering* of volatility
estimates across stocks on a given day. A fixed window applies the identical
transformation to every stock; an exponential weighting's effective sample depends
on each stock's own history of gaps and non-trading days, so the cross-section
becomes less comparable even as each individual estimate improves.

---

### 14. Multi-signal equal-weight combination

**What it did.** Combined several standalone signals into a composite score by
equal weighting, and ranked on the composite instead of the LightGBM output.

**Why it was worth testing.** Simplicity and robustness. An equal-weight composite
has no parameters to fit and cannot overfit, and there is a long literature saying
such composites often match or beat fitted models out of sample. If it matched
LightGBM, the system would become far simpler and its edge far more defensible.

**The accept rule.** As entry 3, with IC as the primary measurement.

**The result.** **Combined IC −0.003** — negative. The report's diagnosis:
"negative factors drag".

**Verdict.** REJECTED. A negative combined IC is not a marginal failure.

**What it taught.** Equal weighting assumes every component points the same way.
Here some factors have negative standalone IC, so equal weighting adds them with
the wrong sign and they cancel the good ones almost exactly. The composite is not
weak; it is *directionless*.

This is the first appearance of the sign problem that dominates entries 21 and 22
(EXP18 and EXP19): **in this feature set, signs are not stable and not uniform,
and any method that implicitly assumes they are will fail.**

---

### 15. IC-weighted combination

**What it did.** The same composite as entry 14, with each signal weighted by its
own historical IC rather than equally — which sets both the magnitude and the sign
of each contribution.

**Why it was worth testing.** The direct fix for entry 14's diagnosis. If the
problem was that negative-IC factors entered with a positive sign, IC weighting
corrects the sign and scales by reliability at the same time. It is still a linear
model with no fitting beyond the IC estimates, so it keeps entry 14's robustness
argument.

**The accept rule.** As entry 3, measured on IC against LightGBM's IC.

**The result.** **IC 0.0174, against LightGBM's 0.036.** The fix worked — the
composite went from −0.003 to clearly positive — but it recovered less than half
the model's IC.

**Verdict.** REJECTED.

**What it taught.** Two things.

1. The sign diagnosis from entry 14 was correct and the correction worked. That
   confirms the mechanism rather than just replacing one failure with another.
2. **Roughly half of LightGBM's IC is not available to any linear combination of
   the same features.** The model is not merely weighting the features; it is
   capturing interactions and non-linearities worth about 0.019 of IC. That is a
   direct measurement of what the model adds over its inputs, and it is the reason
   `EXP18_EXP19_PREREG.txt` could later state that replacing LightGBM with a
   different learner is not the lever — the learner is doing real work, and the
   problem is elsewhere.

---

### 16. Training scheme — a 2 × 2 design

**What it did.** Two independent questions about how the model is trained, run as
a clean 2 × 2 rather than as a search.

- **Q1, "Does more data help?"** — expanding window against rolling windows of
  1, 2 and 3 years.
- **Q2, "Does fading old data help?"** — `sample_weight = λ^(age in months)`, with
  λ ∈ {0.95, 0.98, 0.995} against uniform weighting.

**Why it was worth testing.** Both questions have a real argument on each side.
More data reduces estimation error, but markets change and old data may describe a
regime that no longer exists. Fading is the continuous version of the same
trade-off and does not require choosing a cut-off. If the model's decay on recent
data is a staleness problem, this is the natural remedy.

**The accept rule.** As entry 3, plus a pre-declared **litmus test**: λ = 0.995
gives an effective sample of 399 months ≈ 33 years, far longer than the 8-year
dataset, so it is effectively uniform. If λ = 0.995 does *not* reproduce the
uniform result, the harness itself is broken and no verdict may be read from it.

**The result.**

Q1 — Sharpe by training window:

| universe | expanding | 3y | 2y | 1y |
|---|---|---|---|---|
| 58 | **1.54** | 1.32 | 0.97 | 1.13 |
| 74 | **1.45** | 1.30 | 1.11 | 1.26 |

Q2 — Sharpe by fade:

| universe | uniform | λ = 0.95 | λ = 0.98 | λ = 0.995 |
|---|---|---|---|---|
| 58 | **1.54** | 1.34 | 1.48 | 1.56 |
| 74 | **1.45** | 1.09 | 1.40 | 1.44 |

**Litmus PASSED**: λ = 0.995 reproduced uniform almost exactly (1.56 vs 1.54;
1.44 vs 1.45), confirming the harness was sound.

**Verdict.** REJECTED, in the specific sense that the existing scheme —
expanding window, uniform weighting — already wins both questions. There was
nothing to adopt.

**What it taught.** Four things.

1. **More data is better.** Expanding beats every rolling window in both
   universes, and 2-year rolling on 58 collapses to 0.97. Data from 2016–18 is
   still relevant in 2026.
2. **Fading is monotonically harmful.** More fade, worse result, in both
   universes. There is no λ at which it turns.
3. **The litmus test earned its place.** A negative result on a method that
   *should* be a no-op at one extreme is worthless unless you have checked that
   the no-op reproduces. Building the degenerate case into the design is cheap
   and it is what makes this a finding rather than an unfalsifiable negative.
4. This result closes the door on "the model needs to adapt faster" as a remedy —
   which matters at entry 21, where `EXP18_EXP19_PREREG.txt` cites it explicitly
   to argue that EXP18's *fewer features* lever is the opposite of the already
   failed *shorter effective sample* lever, and therefore not a repeat.

---

### 17. EXP14 — high/low intraday features

*Pre-registration: `experiments/EXP14_PREREG.txt` (kept). Report: `EXP14_REPORT.txt` (deleted; content reproduced here).*
*The prereg calls this the 14th idea; the report calls it the 17th, having charged
the four candidate features as four trials.*

**What it did.** Added four new features built from the OHLC columns the system
was not using, then gated them through four sequential tests before any backtest.

The four candidates:

| feature | definition |
|---|---|
| `close_pos_20` | 20-day mean of (close − low) / (high − low) |
| `gap_20` | 20-day mean of (open / prev_close − 1) |
| `true_range_20` | 20-day mean of max(high−low, \|high−prev_close\|, \|low−prev_close\|) / close |
| `range_ratio` | `true_range_20` / `true_range_60` |

All four use data up to and including day *t* only.

**Why it was worth testing.** Verified by grep on the codebase at the time:
`OPEN` was used for execution fills only, `CLOSE` by all 17 features, `VOLUME` by
the three liquidity features, and **`HIGH` and `LOW` were loaded in
`engine_core.py` and used by nothing.** This was the only untouched data already
on disk. The prereg's framing:

> Under the Fundamental Law of Active Management, IR is approximately IC times the
> square root of breadth. Portfolio construction changes neither term; it only
> redistributes the same IR across return and drawdown. That is why the six
> exposure experiments and the five training-scheme experiments all failed, and
> why they were always going to fail. Those questions are closed.
>
> Only two levers remain: raise IC, or raise breadth. Breadth is blocked on Sir's
> point-in-time universe data. IC can be raised only by new information.

These features capture what close-to-close data structurally cannot see: what
happened *inside* the trading day, and what happened *between* days.

**The accept rule — verbatim, and note the ordering.** Four gates, sanity before
performance:

> **GATE 1 — REDUNDANCY** (runs first, before any performance number)
> RULE: any candidate whose absolute correlation with an existing feature exceeds
> 0.80 is DROPPED before testing. A feature that duplicates an existing one cannot
> add IC and only adds dilution.
> Expected casualty: true_range_20 against vol_20. If it goes, it goes.
>
> **GATE 2 — STANDALONE RAW IC** (runs second, still before the model)
> RULE: a feature must show |IC| above 0.005 in BOTH halves with a CONSISTENT
> SIGN. A feature that predicts in one half and reverses in the other is noise,
> and adding it to the model will only let the model fit that noise.
>
> This ordering is deliberate: sanity checks before performance numbers, per the
> lesson from the long-short bug and the EWMA episode.
>
> **GATE 3 — LEAKAGE.** RULE: any feature that touches data from t+1 onward is a
> build error and is fixed or dropped. Not negotiable.
>
> **GATE 4 — FULL BACKTEST, WITH A NOISE CONTROL.** ACCEPT only if ALL of the
> following hold: a) Sharpe does not fall in EITHER universe; b) Sharpe improves
> in BOTH sub-periods, in BOTH universes — four checks, all must pass; c) MaxDD
> does not worsen by more than 1.0 percentage point in either universe; d) the
> improvement exceeds the noise control by a clear margin; e) Rank IC rises above
> the current +0.0365.
>
> REJECT if any one fails. Partial passes are rejections. Three of five is a
> rejection, not "promising".

And the budget, fixed in advance:

> BUDGET: four candidate features. One batch. No second round of variants
> regardless of outcome.

**The result.**

- **Gate 1:** `true_range_20` DROPPED — correlation **0.85** against `vol_20`,
  exactly the casualty the prereg predicted. Three survived.
- **Gate 2:** all three failed.

| feature | IC 2019–2022 | IC 2023–2026 | why it failed |
|---|---|---|---|
| `close_pos_20` | −0.003 | −0.014 | below the 0.005 bar in the first half |
| `gap_20` | −0.038 | +0.006 | sign flip |
| `range_ratio` | −0.037 | +0.017 | sign flip |

Nothing survived Gate 2, so there was nothing to test for leakage and nothing to
put in a backtest. **No Sharpe number was computed for these features, by
design.**

**Verdict.** REJECTED at Gate 2 of 4.

**What it taught.** Three things.

1. **The rejection arrived one gate earlier than predicted, and for a worse
   reason.** The prereg expected "weak but consistent IC at Gate 2" and a
   wash at Gate 4. What actually happened is that two of three features *reverse
   sign between halves*. Weak is disappointing; reversing is disqualifying, and it
   is the same failure mode that appears at entries 20 and 21.
2. **The gate ordering saved the experiment from itself.** Had Gate 4 run first,
   there would now be a Sharpe number for a feature set containing two sign-
   flipping features, and that number would have been argued about. Putting the
   cheap structural checks first meant the experiment cost a fraction of a full
   backtest and produced a cleaner answer.
3. **The price-and-volume avenue is closed.** High and low were the last unused
   columns on disk, and they carry no stable 20-day cross-sectional signal in
   these universes. Per the prereg's budget, no variant was attempted — no
   dropping `close_pos_20` and retrying the other two, no changing the window from
   20 to 10, no re-testing `true_range_20` with a different denominator to get it
   under 0.80. From the report:

> The remaining levers are the ones the pre-registration named: new data
> (fundamentals), or a wider and less efficient universe. Both are blocked on the
> same point-in-time universe data.

---

### 18. EXP15 — panic exit

**RECOVERED FROM A SESSION TRANSCRIPT, NOT FROM AN ORIGINAL REPORT.** The
`EXP15` prereg and report did not survive to this session. The content below was
supplied verbatim by the operator from a transcript and is recorded as such. It is
the weakest-provenance entry that still has numbers.

**What it did.** Below a breadth threshold, liquidate everything to cash. Tested
at thresholds **0.08 and 0.12**.

**Why it was worth testing.** The exposure family had been declared closed at
entry 9, but every attempt in it had been a *continuous* re-mapping of breadth.
This is a discrete rule aimed at the tail only, and its target is drawdown rather
than return — a different objective from anything tried before. If breadth's
information is concentrated in its extreme low readings, a rule that only fires
there makes the smallest possible claim.

**The accept rule** *(recovered, paraphrased — no verbatim prereg survives)*:
Sharpe not lower in either universe; both sub-periods passing in both universes;
MaxDD improving by **more than 1.0 point**; and **thresholds 0.08 and 0.12
agreeing**.

**The result.**

| universe | arm | CAGR% | Sharpe | MaxDD% |
|---|---|---|---|---|
| 58 | baseline | 16.45 | 1.36 | −17.09 |
| 58 | panic | 15.97 | **1.34** | **−18.15** |
| 74 | baseline | 14.65 | 1.27 | −17.71 |
| 74 | panic | 14.89 | 1.29 | −17.62 |

**Verdict.** REJECTED. Recorded reason, verbatim:

> Sharpe fell on 58, and MaxDD worsened on 58, which was the rule's entire
> purpose. The universes disagreed in direction, which is a noise signature.

**What it taught.** The rule failed *on its own objective*. It was built to reduce
drawdown, and on 58 drawdown got worse by 1.06 points. A rule that moves its
target metric the wrong way is not a rule that needs a better threshold. And the
two universes disagreed in direction — the same noise signature first identified
at entry 7.

The 0.08/0.12 agreement clause deserves note as good design: it is a
pre-registered robustness requirement that prevents a single lucky threshold from
being read as a result, and it is the correct answer to the pattern that entries
5 and 6 fell into by accident.

---

### 19. EXP16 — index trend gate

**RECOVERED FROM A SESSION TRANSCRIPT, NOT FROM AN ORIGINAL REPORT.** Same
provenance caveat as entry 18.

**What it did.** Exposure goes to **zero** when the index is below its own N-day
moving average. Tested at N ∈ {100, 150, 200}.

**Why it was worth testing.** The oldest and most widely used trend filter there
is, and it uses a source the system does not otherwise consult: the index level,
rather than the cross-section of its members. If the system's drawdowns are
market drawdowns, a market-level filter should catch them, and the fact that it is
well known is an argument in its favour rather than against — it has survived
outside this dataset.

**The accept rule** *(recovered, paraphrased — no verbatim prereg survives)*:
Sharpe not lower in either universe; MaxDD improving by **more than 2.0 points**;
**N ∈ {100, 150, 200} agreeing**; both sub-periods passing.

**The result**, on 58:

| arm | CAGR% | Sharpe | MaxDD% |
|---|---|---|---|
| baseline | 16.45 | 1.36 | −17.09 |
| MA(100) | 13.53 | 1.30 | −17.08 |
| MA(150) | 11.67 | 1.15 | −17.03 |
| MA(200) | 11.41 | 1.06 | −17.09 |

**Verdict.** REJECTED. Recorded reason, verbatim:

> Sharpe fell at every N in both universes and MaxDD did not move at all. CAGR
> fell 4.8 points for no drawdown benefit. The reason recorded then: breadth
> already gates exposure, so an index MA gate carries no new information and only
> cuts upside.

**What it taught.** Look at the MaxDD column: **−17.09, −17.08, −17.03, −17.09.**
Three trend filters spanning a factor of two in lookback moved maximum drawdown by
six basis points. That is not a weak effect — it is the signature of a filter that
is *redundant with something already in the system*. Breadth is the fraction of
the universe with positive 20-day momentum; the index being below its moving
average is very nearly the same statement, arrived at by a slower route. The gate
fires when breadth has already cut exposure, so it removes upside without removing
any of the downside breadth had not already handled.

The monotone CAGR decline across N (13.53 → 11.67 → 11.41) is the same shape as
entry 9's k = 1/2/3: a smooth degradation with no turning point, which is what a
pure cost with no offsetting benefit looks like.

---

### 20. EXP17 — dispersion tilt as a second regime input

*Pre-registration: `experiments/EXP17_PREREG.txt` (kept). Report: `EXP17_REPORT.txt` (deleted; content reproduced here).*

**What it did.** Added a second regime signal alongside breadth, multiplicatively:

```
dispersion_60 = 60-day mean of the cross-sectional standard deviation of
                daily returns across the universe
d_pct         = causal percentile rank of dispersion_60 within its own trailing
                3 years, in [0, 1]
tilt          = 0.5 + d_pct                      -> range [0.5, 1.5]
exposure      = clip(breadth * tilt, 0.0, 1.0)
```

The functional form was fixed in the prereg before any run, with reasons given for
each choice: multiplicative so that zero breadth forces zero exposure (the second
signal may scale the first, never override it); percentile rather than raw level
so no absolute threshold is fitted; the [0.5, 1.5] band symmetric about 1.0 so the
rule cannot raise average deployment by construction; a trailing 3-year percentile
window because it is the same order as the existing 252-day windows.

**How it was injected without touching `results/`** — worth recording, because it
is a reusable technique. `results/` was read-only and `backtest_exposure` has no
caller-supplied exposure hook, so the `voltgt` branch was used as one: that branch
computes `expo = min(1, target_vol/port_vol)`, so `target_vol=1.0` with a
synthetic `port_vol` of `1/desired` reproduces any exposure in [0,1] exactly.
**Proven before use:** injecting the plain breadth path reproduced the official
`v2FINAL_equity.csv` strategy curve with a maximum gap of **Rs 0.0000** in both
universes, so the engine being driven is demonstrably the official one.

**Why it was worth testing.** Measured behaviour of the existing breadth rule:

```
breadth < 0.35 (18 of 93 rebalances) -> next 20 days average +0.36%, up 44%
breadth > 0.65 (31 of 93 rebalances) -> next 20 days average +2.76%, up 81%
Spearman IC of breadth vs next 20-day return: +0.19
```

So breadth carries real information; the complaint was deployment. EXP15 and EXP16
both tried to fix that by **re-shaping the same signal**, and both failed. This
was the first attempt to add an **independent** one, which is a genuinely
different question.

**The candidate was chosen from a screen of six**, and the prereg declared that
openly, along with the problem it creates:

| signal | corr w/ breadth | IC vs fwd20 | \|t\| |
|---|---|---|---|
| **dispersion_60** | **+0.12** | **+0.221** | **2.16** |
| skew_60 | −0.12 | −0.217 | 2.13 |
| idx_vol_60 | +0.05 | +0.132 | 1.27 |
| downside_ratio | −0.43 | −0.143 | 1.38 |
| breadth_ma200 | +0.46 | −0.022 | 0.21 |
| vol_of_vol | +0.11 | +0.006 | 0.06 |

> THE HONEST PROBLEM WITH THAT: it was selected as the best of six on the same 93
> observations it will now be tested on. A |t| of 2.16 is not impressive after six
> looks — a Bonferroni-style correction would want roughly 2.9. The screen is
> therefore treated as hypothesis generation, not evidence, and Gate D below
> exists specifically to catch the case where this is noise.

Economic reading: high dispersion means stocks are moving apart, which is the
condition under which a cross-sectional ranking system has something to rank. Low
dispersion means everything moves together and selection cannot add value. That is
a different claim from breadth, which measures direction, not spread.

**The accept rule — verbatim.**

> ACCEPT only if ALL FOUR hold:
>
> **A.** Sharpe is not lower in EITHER universe (58 and 74).
>
> **B.** CAGR improves by more than 1.0 pt in BOTH universes.
> Rationale: the whole point is deployment, so a return improvement is the claim
> being made. A Sharpe-only gain does not pass — EXP15 and EXP16 both produced
> small Sharpe wobbles in one universe while failing the other.
>
> **C.** Both sub-periods pass in both universes: 58: 2019-2022 and 2023-2026;
> 74: 2019-2022 and 2023-2025. "Pass" means Sharpe not lower and CAGR not lower in
> that sub-period.
>
> **D.** NOISE CONTROL. Re-run with the dispersion series randomly shuffled across
> rebalance dates, 20 independent shuffles, same seed set recorded. The real
> signal's CAGR improvement must exceed the 90th percentile of the shuffled
> improvements in BOTH universes. If shuffled dispersion produces a similar gain,
> the gain is not information. This gate exists because the candidate was chosen
> from a screen of six.
>
> REJECT on any single failure. One batch. No re-runs with a different tilt band,
> a different percentile window, or skew_60 substituted in.
>
> skew_60 is NOT tested here and is NOT a fallback. If EXP17 is rejected, testing
> the runner-up from the same screen is simply continuing to mine the same data.

**The result.**

| | 58 universe | 74 universe |
|---|---|---|
| baseline | CAGR 16.45%, Sharpe 1.36 | CAGR 14.65%, Sharpe 1.27 |
| candidate | CAGR 17.22%, Sharpe 1.43 | CAGR 14.62%, Sharpe 1.32 |
| MaxDD | −17.09% → −17.90% | −17.71% → −17.84% |
| exposure moved >5 pts | 68 of 93 rebalances | 54 of 87 rebalances |

- **Gate A — PASS.** 58: 1.36 → 1.43. 74: 1.27 → 1.32.
- **Gate B — FAIL.** 58: +0.77 pt, below the 1.0 pt bar. 74: **−0.03 pt**, no
  improvement at all.
- **Gate C — FAIL**, and it is a clean regime flip with the same shape in both
  universes:

| | CAGR | Sharpe | |
|---|---|---|---|
| 58 2019-2022 | 20.93 → 25.29 | 1.53 → 1.74 | pass |
| 58 2023-2026 | 11.33 → **8.44** | 1.13 → **0.96** | **FAIL** |
| 74 2019-2022 | 15.95 → 17.91 | 1.29 → 1.46 | pass |
| 74 2023-2025 | 13.00 → **10.42** | 1.26 → **1.09** | **FAIL** |

- **Gate D — PASS**, but not uniformly, and this is the interesting part.
  - **58: real +0.77 pt vs shuffled p90 −0.23 pt. 0 of 20 shuffles beat it
    (empirical p = 0.00.)** Distribution: min −4.02, p25 −2.32, median −1.43,
    p75 −0.79, max +0.22, mean −1.55.
  - **74: real −0.03 pt vs shuffled p90 −0.05 pt. 2 of 20 beat it (p = 0.10).**
    Distribution: min −3.40, p25 −2.09, median −1.14, p75 −0.64, max +0.89,
    mean −1.27.

  On 58 that is a genuine pass — the benefit is attributable to *when* the tilt
  was applied, not to its shape, and dispersion does appear to carry real timing
  information there. **On 74 the pass is degenerate**: the real signal delivers
  −0.03, and it clears the bar only because random tilts are even worse. Gate D
  compares improvements, so "slightly negative" beats "clearly negative" and the
  gate technically passes. It is not evidence that the tilt adds return on 74,
  because it does not.

**Verdict.** REJECTED at Gates B and C. Per the prereg, one failure is a
rejection; two of four certainly is.

**What it taught.** Three things, and the first is the one to carry forward.

1. **A symmetric tilt is not a neutral tilt.** The prereg reasoned that a band
   symmetric around 1.0 "cannot raise average deployment by construction — it must
   earn any gain by timing." That is correct about the *tilt* and wrong about the
   *outcome*. The rule made the system **less** invested, which is the opposite of
   its stated motivation: deployment went **55.0% → 50.5%** on 58 and
   **57.2% → 50.5%** on 74. Two measured causes:
   - Dispersion over 2019–2026 sat in the lower part of its own trailing 3-year
     range, so the tilt was below 1 more often than not — 58: mean `d_pct` 0.449,
     mean tilt 0.949, tilt < 1 on 52 of 93 rebalances; 74: mean `d_pct` 0.362,
     mean tilt 0.862, tilt < 1 on 44 of 87.
   - **The final `clip(·, 0, 1)` truncates the upside half of the tilt but not the
     downside.** Clipping bound on 8 of 93 (58) and 5 of 87 (74) rebalances,
     discarding 119 and 81 exposure points — about 1 point per rebalance.

   This is why the shuffled controls average about −1.4 pt of CAGR: **the shuffled
   distribution is measuring the cost of the functional form, not the absence of
   dispersion information.** Any experiment with a one-sided clip has this
   property, and the control distribution being centred below zero is the tell.

2. **A full-period Sharpe gain can be the average of a large early gain and a
   later loss.** Gate A passed on both universes. Gate C shows the gain is
   entirely in 2019–2022 and reverses afterwards, in both universes, on both
   metrics. Without the sub-period gate this would have been recorded as a
   Sharpe improvement. It is the same failure mode as EXP14's `gap_20` and
   `range_ratio` — works in one half, reverses in the other.

3. **Gate D was written specifically to catch a candidate mined from a screen of
   six, and it is the gate the candidate passed.** The experiment failed on the
   plain performance gates instead. That is worth sitting with: the sophisticated
   control cleared it and the simple requirement — "actually be better" — did not.

Per the prereg, no variant was attempted: no different tilt band, no different
percentile window, and **`skew_60` was not substituted in**, because testing the
runner-up from the same six-signal screen is continuing to mine the same 93
observations.

**The exposure question is now closed after 8 recorded attempts** — and this time
it stayed closed. Nothing after EXP17 touches exposure.

---

### 21. EXP18 — sign-stability feature filter

*Pre-registration: `experiments/EXP18_EXP19_PREREG.txt` (kept). Result:
`diagnostics/EXP18_RESULT.txt` (deleted; content reproduced here).*

**What it did.** For each feature, computed its rolling 24-month standalone
Spearman IC against 20-day forward cross-sectional rank. A feature is
**sign-stable** at time *t* if the sign of that rolling IC has been the same in at
least **70%** of the rolling windows ending at or before *t*. The model is then
retrained on the sign-stable subset only.

Everything else — the model and its hyperparameters, the 10 seeds, the 32-day
purge, the monthly expanding walk-forward, `TOP_N`, `BUFFER`, breadth, sizing —
unchanged. **The only change is which feature columns are handed to LightGBM at
each month.**

The 70% and 24-month choices were fixed in the prereg and not tuned: 24 months
because it is two full annual cycles and matches the order of the existing 252-day
windows; 70% because it is a clear majority without demanding near-perfect
stability, which only 1 of 17 features achieves.

**Why it was worth testing.** A specific, measured, mechanical problem. Per-year
mean absolute standalone feature IC against the model's own IC, on 58:

| | 2019 | 2023 | 2026 |
|---|---|---|---|
| features | 0.0340 | 0.0497 | 0.0344 |
| **MODEL** | **+0.0464** | **+0.0897** | **−0.0441** |

**The features have not decayed** — mean absolute feature IC in 2026 (0.0344) is
essentially identical to 2019 (0.0340), and individual features are strong:
`beta_60` +0.1200, `amihud_20` +0.0682, `downside_vol_60` +0.0678, `vol_20`
+0.0557. The *model* went from +0.0897 to −0.0441. By 2026 it was not merely
failing to extract the signal; it was extracting it with the **wrong sign**.

The mechanism was visible in the same diagnostic: only 1 of 17 features holds a
single sign across all eight years, and agreement with 2019's signs falls from 17
to between 7 and 10. `beta_60` runs −0.0554 in 2019 to +0.1200 in 2026 — a full
reversal. An expanding-window model weights all history equally, so it learns each
feature's historical *average* sign, and for a reversed feature that average is
wrong for the present.

The prereg also recorded, in advance, why two obvious alternatives were not being
tried:

> **WHY NOT A DIFFERENT MODEL.** Replacing LightGBM with a sequence model, a
> transformer, or a larger ensemble does not address this. Any learner fed
> features whose sign reverses will learn the historical average sign. The problem
> is the feature set's stability, not the function approximator.
>
> **WHAT HAS ALREADY FAILED, SO IS NOT RETRIED.** Faster adaptation.
> Decay-weighted training was tested and was monotonically worse. […] Decay
> shrinks the effective sample. EXP18 keeps the full sample and reduces the number
> of features instead — the opposite lever, which is why it is not a repeat of
> that test.

**The accept rule — verbatim.**

> **A.** Model IC over 2024-2026 is positive in ALL THREE universes. This is the
> point of the experiment. A Sharpe improvement without an IC improvement would
> mean something else caused it.
>
> **B.** Sharpe is not lower in ANY universe.
>
> **C.** Both sub-periods pass in all three universes (2019-2022 and 2023 onward):
> Sharpe not lower and CAGR not lower in each.
>
> **D.** NOISE CONTROL. Re-run with a randomly chosen feature subset of the SAME
> SIZE as the stable set in each period, 20 independent draws, seeds recorded. The
> real filter's Sharpe improvement must exceed the 90th percentile of the random
> draws in ALL THREE universes. If choosing any n features does as well as
> choosing the stable n, the stability criterion carries no information and the
> gain is from having fewer features, not the right ones.
>
> REJECT on any single failure. One batch. No variants — no 80% threshold, no
> 36-month window, no "stable plus the two best unstable ones".

And the causality requirement, which the prereg singled out:

> **CAUSALITY — THE PART THAT MUST NOT BE GOT WRONG.** The filter is recomputed at
> every rebalance using ONLY data available at that date. A feature that becomes
> unstable in 2024 is still included in the 2020 model. Selecting the stable set
> once over the full history and applying it backwards would be look-ahead of the
> most flattering kind […] Report, per year, which features were in the stable
> set. If the set is identical in every year, the filter is not causal and the run
> is void.

**The result.**

| universe | arm | CAGR% | Sharpe | MaxDD% | IC 2024-2026 |
|---|---|---|---|---|---|
| 58 | baseline | 17.01 | 1.39 | −14.34 | −0.0070 |
| 58 | EXP18 | 15.07 | 1.24 | −20.28 | **+0.0088** |
| 58 | delta | −1.94 | **−0.15** | −5.94 | +0.0158 |
| 74 | baseline | 16.25 | 1.43 | −17.85 | +0.0055 |
| 74 | EXP18 | 13.68 | 1.24 | −19.39 | +0.0086 |
| 74 | delta | −2.57 | **−0.19** | −1.54 | +0.0031 |
| mid | baseline | 29.18 | 2.00 | −18.98 | +0.0396 |
| mid | EXP18 | 27.85 | 1.96 | −17.04 | **+0.0346** |
| mid | delta | −1.33 | **−0.04** | +1.94 | **−0.0050** |

- **Gate A — PASS** on the letter. 58 −0.0070 → +0.0088; 74 +0.0055 → +0.0086;
  mid +0.0396 → +0.0346, still positive but **fell**.
- **Gate B — FAIL on all three universes.** 1.24 vs 1.39; 1.24 vs 1.43;
  1.96 vs 2.00.
- **Gate C — FAIL.** 58 2019-2022: ΔSharpe −0.230, ΔCAGR −3.10. 58 2023–:
  ΔSharpe −0.050, ΔCAGR −0.62. (mid: 2019-2022 ΔSharpe −0.010 ΔCAGR −1.41;
  2023– ΔSharpe −0.080 ΔCAGR −1.40.)
- **Gate D — PASS on 58.** Real −0.150 vs p90 −0.176; **beats 18 of 20** random
  8-feature subsets.

**Gate D, in full.** These are Sharpe *gains* against the 58 baseline of 1.39, one
per random same-size feature subset, draws 00–19 in order. Preserved here because
the per-draw cache they came from is deleted and four hours of scoring cannot be
recovered:

```
-0.250  -0.440  -0.600  -0.480  -0.460  -0.190  -0.720  -0.580  -0.240  -0.530
-0.210  -0.270  -0.400  -0.060  -0.800  -0.770  -0.180  -0.370  -0.140  -0.380
```

| | |
|---|---|
| real filter (EXP18 Sharpe 1.24) | **−0.150** |
| min | −0.800 |
| p25 | −0.567 |
| median | −0.390 |
| p75 | −0.217 |
| **p90** | **−0.176** |
| max | −0.060 |
| mean | −0.404 |
| draws matching or beating the real filter | **2 of 20** (empirical p = 0.10) |

**74's partial Gate D — recovered from the cache, and it does not agree with 58.**
`EXP18_RESULT.txt` states that eight of 74's twenty draws completed before the
scope change stopped them. **The cache in fact held twelve.** Those twelve, as
Sharpe gains against the 74 baseline of 1.43 (EXP18 real: 1.24, a gain of −0.190):

```
-0.220  -0.240  -0.150  -0.310  -0.160  -0.040  -0.200  -0.100  -0.080  -0.150
-0.430  +0.130
```

min −0.430, p25 −0.235, median −0.155, p75 −0.085, max **+0.130**, mean −0.163,
p90 −0.044. **Seven of the twelve match or beat the real filter's −0.190.**

**No Gate D verdict is claimed for 74**, and none may be: twelve draws is not the
pre-registered test of twenty, and a partial sample stopped for an unrelated
reason is not a result. But the direction is recorded because it cuts against the
conclusion drawn below, and because the evidence for it is now gone. On 58 the
stable subset beat 18 of 20 random subsets; on 74's partial sample it beat 5 of
12 — that is, it did no better than chance. **The claim that the stability
criterion selects a genuinely better subset than chance rests on one universe,
not two**, and the one universe where it was also partially measured points the
other way.

**Causality evidence (the gate that could have voided the run).** The stable set
is **not** identical across years. Distinct year-opening sets: 5 of 11 years on
58, 7 of 10 on 74, 5 of 11 on mid; 5, 17 and 8 distinct sets across all scored
months.

```
58   size 7 to 9 of 17
     2019  mom_20, mom_12_1, rev_5, rev_1, amihud_20,
           trend_consistency_20, path_smooth_60, rsi_14
     2026  the same plus idio_vol_60
     beta_60 is in the set in 2016, drops out, and never returns.
74   size 0 to 17. Empty in 2019-01 and 2019-02, 16 features in 2020-21,
     down to 8 by 2024 as the reversals accumulate.
mid  size 11 to 14. beta_60 present throughout -- the most stable of the three,
     which matches mid being the universe where the model still adds value.
```

Two causality details worth preserving, because both are the kind of thing that
silently invalidates a result:

> **A CAUSALITY DETAIL THE PRE-REGISTRATION LEFT IMPLICIT.** A daily IC dated *d*
> is measured against the return from *d* to *d+20*, so it is not knowable at *d*.
> Using every IC dated on or before the rebalance would leak about a month of
> forward returns into the feature-selection decision. The filter's history is
> therefore cut at the model's own training cut — first date of the scored month
> minus the 32-day purge — so the filter sees exactly what the model may see and
> no more. This is stricter than a loose reading of "data available at that date".
>
> **AN EMPTY STABLE SET, WHICH THE PRE-REGISTRATION DID NOT COVER.** On 74 the
> stable set is empty in 2019-01 and 2019-02. With 10 and 11 rolling windows
> available at those dates that is a real result — no feature held its sign in 70%
> of them — not a shortage of history. "Retrain the model on the sign-stable
> subset only", taken literally, means an empty subset produces no model and
> therefore no scores, so those names are unrankable and the strategy does not
> trade. That is the reading used. It is the conservative one: it costs EXP18 two
> months of trading on 74 rather than granting it a fallback to the full feature
> set. Falling back to all 17 would have been the flattering choice, and choosing
> between the two after seeing which scored better would be the tuning this
> experiment forbids, so only the literal reading was run.

**Verdict.** REJECTED at Gate B, on all three universes.

**What it taught.** This is the most informative rejection in the record.

**THE MECHANISM WORKED EXACTLY AS PREDICTED, AND THE STRATEGY GOT WORSE ANYWAY.**
The prereg claimed that a feature whose sign reverses is noise the model is being
asked to memorise, and that training only on sign-stable features would produce a
model whose IC does not invert. That is precisely what happened: on 58 the model's
2024–2026 IC went from −0.0070 to +0.0088, and the inversion — the specific
measured problem EXP18 existed to fix — is gone. On 74 it improved too. **And
Sharpe fell in both, in both sub-periods on 58, with drawdown nearly six points
deeper.**

**Gate D is what makes this informative rather than merely negative.** Every one
of the 20 random 8-feature subsets did *worse* than the real stable 8 (median
−0.390 against the real −0.150; the real filter beat 18 of 20). So the stability
criterion is not a dressed-up way of using fewer features — it selects a genuinely
better subset than chance does, by a wide margin. **And all 17 features still beat
the stable 8.** Both statements are true at once, and together they say something
specific:

*(Read that first sentence against 74's partial Gate D above, where the stable
subset beat only 5 of 12. The "wide margin" is a one-universe result.)*

> **DROPPING REVERSING FEATURES LOSES MORE SIGNAL THAN THE REVERSAL COSTS.** The
> reversed features are not noise. `beta_60`, whose IC ran −0.0554 in 2019 to
> +0.1200 in 2026, is carrying real information in both regimes; a model fed all
> 17 extracts more from it, wrong average sign and all, than a model denied it.

**Mid is the case that confirms the diagnosis rather than repeating it.** On 58
and 74 the model's IC was broken — inverted on 58, barely above zero on 74 — and
the filter *raised* it. On mid the model was never broken, and the same filter
*lowered* the IC. So the filter does not improve model IC as such; it removes
features whose sign is unstable, and that helps only where instability was
actively hurting. **The direction of the IC change flips with whether the model
was broken to begin with**, which is what a genuine signal-versus-noise trade-off
looks like and not what a general improvement would look like.

Noted for completeness and explicitly not offered as a rescue: on mid, drawdown
improved 1.94 points (−18.98 → −17.04) for a 0.04 Sharpe cost. Gate B is a Sharpe
gate, it was written before the result was seen, and it failed.

**What was not completed, and why.** **Mid's Gate D noise control was not run**,
and neither was 74's. The project's universe scope changed *while the experiment
was running* — 58 and 74 were dropped — and the random draws were stopped because
they would have cost several hours measuring a gate whose verdict could not
change, EXP18 already being rejected on two universes. The result was already
known and already negative when they were stopped; stopping them could not and did
not improve it. **Mid's Gate D is simply unmeasured**, and this record says so
rather than leaving a gap for a later reader to fill in charitably.

`EXP18_RESULT.txt` records that eight of 74's twenty draws completed. **Twelve had
completed** — the report undercounted its own cache. All twelve are preserved
above. The undercount made no difference to the verdict, which had already failed
Gate B on three universes, but it is corrected here because the file that would
have settled it is now deleted.

**How it was verified.** The all-17 baseline was not re-scored; it is the cached
scored panel the live pipeline produced, and the harness was checked against the
published headline figures **before** any comparison was made: 58 CAGR 17.01 /
Sharpe 1.39 / MaxDD −14.34 / 929 trades; 74 16.25 / 1.43 / −17.85 / 883; mid 29.18
/ 2.00 / −18.98 / 985 — all reproduced exactly. The per-year model IC also
reproduces the figures quoted in the prereg itself. The vectorised Spearman was
checked against `scipy.stats.spearmanr` over 120 spot comparisons per universe:
maximum absolute difference **1.1e-16**.

---

### 22. EXP19 — sign-corrected features — **NOT RUN**

*Pre-registration: `experiments/EXP18_EXP19_PREREG.txt` (kept), section EXP19.*

**This experiment was never run.** It is recorded in full because it is
pre-registered, because its conditional trigger has fired, and because the
decision not to run it is an operator decision that should not be lost.

**What it would do.** At each rebalance, for each feature, compute the sign of its
trailing 24-month standalone IC using only data available at that date, and
multiply the feature by that sign before it enters the model. **All 17 features
are retained** — none is dropped. Everything else unchanged. Same causality
requirement as EXP18: sign computed from trailing data only, recomputed at every
rebalance, per-year sign vector reported, and an identical sign vector across all
years voids the run.

**Why it was worth testing.**

> Dropping a reversed feature discards information. `beta_60`'s IC in 2026 is
> +0.1200 — the strongest single feature in the universe. It is not useless; its
> direction has changed. Orienting each feature by its own recent relationship,
> rather than dropping it, keeps the information and fixes the sign.

**The accept rule — verbatim.**

> **A.** Model IC over 2024-2026 is positive in ALL THREE universes.
> **B.** Sharpe is not lower in ANY universe.
> **C.** Both sub-periods pass in all three universes.
> **D.** NOISE CONTROL. Re-run with RANDOM signs — each feature multiplied by +1
> or −1 drawn at random, 20 independent draws, seeds recorded. The real
> sign-correction must exceed the 90th percentile in ALL THREE universes. A random
> sign flip changes the feature set the model sees. If that does as well, the gain
> is from perturbation, not from getting the direction right.
>
> REJECT on any single failure. One batch. No variants.

**Its own honest expectation, recorded in advance:**

> Lower than EXP18. Sign-flipping a feature on a 24-month trailing window will
> itself be unstable near a reversal, and the flip arrives after the reversal has
> already cost something. It is a lagging correction to a lagging problem.

**Status.** The prereg makes EXP19 conditional on EXP18 being rejected, which it
is. **The trigger has fired and the experiment has not been authorised.** The
decision belongs to the operator and has not been given.

**What it taught, without being run.** EXP18's Gate D result cuts both ways on
EXP19, and the EXP18 report says so:

> if dropping a reversed feature costs more than the reversal, the case for
> re-orienting it rather than dropping it is stronger

That is the strongest argument for running it. Against it stands the prereg's own
`IF BOTH ARE REJECTED` section, which anticipates the outcome and calls it an
answer rather than a prompt for a third attempt:

> It would mean the features carry standalone predictive power that no
> causally-available reweighting of them converts into model IC on recent data —
> which is a finding about this feature set on this dataset, and a more useful
> thing to be able to state than another rejected variant.
>
> The remaining lever at that point is breadth, not IC: a larger universe raises
> BR in IR = IC × √BR. That is what the survivorship work unlocks, and it is a
> different axis from anything tested here.

**If EXP19 is ever run, it must be run under the prereg above, unmodified.** It is
the only pre-registered, unexecuted experiment in the project.

---

### 23. EXP20 — tradeability filter

*Pre-registration: `experiments/EXP20_PREREG.txt` (kept). Result:
`diagnostics/exp20_result.txt` (deleted; content reproduced here).*

**What it did.** At each rebalance, a name is **ineligible** if a full target
position would exceed 10% of its prior-20-day median daily volume, at starting
capital:

```
full target position value = START_CAPITAL / TOP_N = 10,00,000 / 8 = Rs 1,25,000
shares required            = 1,25,000 / price on the decision date
ineligible if                shares required > 0.10 x median(volume, prior 20 days)
```

Ineligible names are removed from the candidate set **before** the top-8 is taken.
Everything else unchanged.

**Implementation note, reusable.** No engine file was modified. An ineligible name
has its **score set to NaN** on that date; `backtest_exposure` already drops NaN
scores before ranking (`s_ = sc.loc[dt].dropna()`), so a NaN score is exactly "not
a candidate" — the same mechanism the survivorship switch uses. The rolling median
is shifted by one day so it uses days strictly before the decision date, and
`min_periods=20` means a name with fewer than 20 prior observations has no median
and is ineligible, which is the conservative direction.

**Why it was worth testing.** The liquidity measurement found that the MidCap150
strategy holds positions it could not have entered at the price the backtest
assumes, **at the backtest's own size of Rs 10,00,000**:

- maximum participation **1,614%** of prior-20-day median daily volume, on AIIL
- four AIIL fills above 100% of prior-20-day MDV
- p90 of **282%** in the under-Rs-10 price band
- **22 of 985 fills** above 10% participation

  *Superseded 2026-09-20. Re-measured on midcap150 at the same Rs 10,00,000:
  **12 of 998** fills with a prior-20-session median exceed 10% (n=1,006 in all),
  the under-Rs-10 band's p90 is **0.325%** over 18 fills, and **no AIIL fill
  exceeds 10%** — AIIL's four current fills are all 2025-2026. AIIL's price file
  now starts 2024-04-23, so the 2021 orders behind the old bullets are not in the
  tree. Kept visible because the three bullets are what EXP20 was pre-registered
  against.*

And modelling depth natively rather than as flat slippage costs mid **1.80 CAGR
points and 0.10 Sharpe** (29.16% → 27.36%, Sharpe 2.00 → 1.90, 19 orders walking
the book), against **0.01 points** for n100.

> *Superseded 2026-09-20. `depth_compare.py` re-run on the repointed data reports
> midcap150 **0.04 CAGR points and 0.01 Sharpe** (27.79% → 27.75%, Sharpe 1.90 →
> 1.89, 11 orders walking, n=1,006 fills) and nifty100 **0.00 points** (19.00% →
> 19.00%, 3 orders walking, n=940). The unlimited baseline moved as well, 29.16 →
> 27.79, so this is not a depth-model change alone. The move is NOT attributed:
> holding today's prices fixed and swapping only the depth model's volume source
> between the pre-repoint `clean` folder and today's constituents gives 27.75 and
> 1,020 fill events either way, so the volume panel is ruled out; reproducing the
> 2026-09-17 run would need both its data and its code, and the code has moved. The
> result tables below are left as they were recorded -- they are what those runs
> produced.*

> An order for sixteen days of a stock's median volume does not execute at the
> opening price. It moves the price, or it does not execute.
>
> Excluding names that cannot absorb a full position is a TRADEABILITY CONSTRAINT
> of the same category as transaction costs, not a parameter choice. Costs are
> already modelled; capacity is not. A backtest that reports returns from positions
> it could not have entered is reporting something other than a strategy.

**The accept rule — verbatim.**

> **A.** mid's CAGR under `DEPTH_MODE="volume"` IMPROVES. The filter must earn its
> place under realistic depth, not under the unlimited-depth assumption it exists
> to escape. This is the point of the experiment: if it only looks good when depth
> is assumed infinite, it has not addressed the problem it was built for.
>
> **B.** mid's Sharpe is not lower under "volume" mode.
>
> **C.** Both sub-periods pass, 2019-2022 and 2023 onward: Sharpe not lower AND
> CAGR not lower in each.
>
> **D.** Maximum fill participation falls below 50% of prior-20-day MDV, and NO
> fill exceeds 100%.
>
> **E.** n100 is unchanged to within 0.10 CAGR. It has only 3 fills above 10%
> participation, so a filter that moves it materially is doing something other than
> removing untradeable names, and the something else would be unmeasured.
>
> REJECT on any single failure. One batch. No variants — no 5% or 20% cap, no
> price-based cut-off substituted in.

**The result.** Causality passed first: the per-year eligible count varies in both
universes (8 distinct yearly counts of 8 in both), so the filter is demonstrably
recomputed from trailing data.

| universe | arm | depth | CAGR | Sharpe | MaxDD | trades | max participation |
|---|---|---|---|---|---|---|---|
| mid | unfiltered | unlimited | 29.16 | 2.00 | −18.95 | 985 | **1620.5%** |
| mid | unfiltered | volume | 27.36 | 1.90 | −18.94 | 1011 | 15.7% |
| mid | FILTERED | unlimited | 28.43 | 1.96 | −15.59 | 989 | 90.5% |
| mid | **FILTERED** | **volume** | **28.06** | **1.94** | −17.04 | 1001 | **10.0%** |
| n100 | unfiltered | unlimited | 25.43 | 1.88 | −18.61 | 997 | 29.4% |
| n100 | unfiltered | volume | 25.42 | 1.88 | −18.61 | 1002 | 10.0% |
| n100 | FILTERED | unlimited | 25.37 | 1.87 | −18.55 | 1001 | 13.1% |
| n100 | FILTERED | volume | 25.38 | 1.87 | −18.55 | 1003 | 10.0% |

Benchmarks, with the buy&hold **recomputed on the filtered universe** as the
prereg required (comparing a filtered strategy against an unfiltered buy&hold
would credit the filter with a difference that is partly just a different basket):

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| mid buy&hold, unfiltered universe | 23.70 | 1.31 | −38.27 |
| mid buy&hold, filtered universe | 23.45 | 1.29 | −38.47 |
| NIFTYMIDCAP150 (cap-weighted) | 18.16 | 1.01 | −38.67 |
| n100 buy&hold, unfiltered universe | 22.01 | 1.24 | −36.85 |
| n100 buy&hold, filtered universe | 22.00 | 1.24 | −36.85 |
| NIFTY100 (cap-weighted) | 10.93 | 0.69 | −38.10 |

Gates:

```
A. mid CAGR improves under 'volume': 27.36 -> 28.06                     PASS
B. mid Sharpe not lower under 'volume': 1.90 -> 1.94                    PASS
C. mid 2019-2022: Sharpe 1.58->1.68  CAGR 22.17->23.85                  PASS
C. mid 2023-2026: Sharpe 2.25->2.23  CAGR 33.57->33.05                  FAIL
D. mid max participation < 50% and none > 100%: max 10.0%, 0 above 100% PASS
E. n100 unchanged within 0.10 CAGR: 25.42 -> 25.38 (delta 0.04)         PASS
```

**Verdict.** REJECTED. Gate C failed — one sub-period, by **0.02 of Sharpe and
0.52 of CAGR**.

**What it taught.** This is the closest any idea came to passing after entry 10,
and how it failed is the lesson.

1. **It answered its own central question in the affirmative.** The prereg framed
   the real test precisely: mid's unlimited-depth CAGR *will* fall, because the
   cheap thin names carry real return; the question is whether it falls by less
   than the 1.80 points that realistic depth already costs. It does. Unlimited
   depth 29.16 → 28.43, a give-up of **0.73 points**, against the 1.80 points of
   depth cost avoided. Under volume mode — the mode that matters — it *improved*,
   27.36 → 28.06. And Gate D, the tradeability objective itself, passed
   emphatically: max participation 1620.5% → 10.0%.
2. **And it was rejected anyway, on 0.02 of Sharpe in one sub-period.** That is
   the pre-registration doing exactly its job. Four of five gates passed; the
   prereg says "REJECT on any single failure" and it was written before the
   numbers were seen. Had the rule been "four of five", or had Gate C been
   written as "not lower by more than 0.05", this would have been an acceptance —
   and the difference between those rules is a judgement that must be made in
   advance or not at all.
3. **The honest reading of the evidence is that this is a near-miss, not a
   refutation.** The tradeability concern is real, the filter addresses it, and
   the cost is smaller than the problem. What the experiment did *not* establish
   is that the improvement is stable, and the failing sub-period is the direct
   evidence against stability. Anyone revisiting this must re-register it,
   carrying the full trial count, and must not simply loosen Gate C to the value
   that would have let it through.
4. Note the participation column under "volume" mode: every row reads exactly
   **10.0%**, filtered and unfiltered alike. That is the depth model capping
   participation by construction, not a property of the filter — which is why the
   prereg required Gate D to be measured per *order* rather than per fill event.

---

### 24. EXP21 — redeploy unfilled cash

*Pre-registration: `experiments/EXP21_EXP22_PREREG.txt` (kept). Result:
`diagnostics/exp21_final.txt` (deleted; content reproduced here).*

**What it did.** When an order fills short of its target quantity, the unfilled
**rupee value** is offered to the next-ranked eligible name not already held, in
strict rank order, subject to the same depth constraint. **At most two
redeployment attempts per rebalance**; after that the residual stays in cash.

> Two attempts is fixed here and no other value will be tried. It is chosen as the
> smallest number that allows a second failure to be absorbed rather than ending
> the chain, without turning the rule into an unbounded search down the ranking.

**Why it was worth testing.** Under `DEPTH_MODE="volume"`, mid has 5 partially
filled orders with a shortfall of **50,551 shares** that never fill. The capital
behind that shortfall sits idle until the next rebalance, 20 trading days later.

> A real system would not leave it idle. It would route the money to the next name
> it could actually buy. Leaving it in cash is an artefact of the backtest
> submitting one order per name and never looking again.

The prereg pre-empted the obvious objection, and the pre-emption is worth keeping:

> **NOT A VARIANT OF EXP20.** EXP20 excluded untradeable names from the candidate
> set outright and was rejected on Gate C. This does the opposite: it keeps every
> name, fills what the book allows, and redeploys only the remainder. The two are
> different mechanisms answering different questions, and this is recorded here so
> that running it after EXP20's rejection is not mistaken for retrying a rejected
> idea with a new threshold.

**The accept rule — verbatim.**

> **A.** mid CAGR under "volume" improves.
> **B.** mid Sharpe under "volume" not lower.
> **C.** Both sub-periods pass, 2019-2022 and 2023 onward: Sharpe not lower AND
> CAGR not lower in each.
> **D.** Unfilled shortfall falls by more than half.
> **E.** n100 unchanged to within 0.10 CAGR. It has zero partial fills, so
> material movement means something other than redeployment is happening.
>
> REJECT on any single failure. One batch. No variants.

**The result.**

| universe | arm | depth | CAGR | Sharpe | MaxDD | trades | days | partial | shortfall | redeployed |
|---|---|---|---|---|---|---|---|---|---|---|
| mid | baseline | unlimited | 29.16 | 2.00 | −18.95 | 985 | 1842 | 0 | 0 | 0 |
| mid | baseline | volume | 27.36 | 1.90 | −18.94 | 1011 | 1842 | 5 | 50,551 | 0 |
| mid | EXP21 | unlimited | 29.16 | 2.00 | −18.95 | 985 | 1842 | 0 | 0 | 0 |
| mid | **EXP21** | **volume** | **28.44** | **1.95** | −18.93 | 1025 | 1842 | 6 | **50,698** | 8 |
| n100 | baseline | unlimited | 25.43 | 1.88 | −18.61 | 997 | 1842 | 0 | 0 | 0 |
| n100 | baseline | volume | 25.42 | 1.88 | −18.61 | 1002 | 1842 | 0 | 0 | 0 |
| n100 | EXP21 | unlimited | 25.43 | 1.88 | −18.61 | 997 | 1842 | 0 | 0 | 0 |
| n100 | EXP21 | volume | 25.42 | 1.88 | −18.61 | 1002 | 1842 | 0 | 0 | 0 |

All 8 runs reached the full 1,842-day window; none truncated.

```
A. mid CAGR improves under volume: 27.36 -> 28.44         PASS
B. mid Sharpe not lower:           1.90 -> 1.95           PASS
C. mid 2019-2022: Sharpe 1.58->1.68  CAGR 22.17->24.09    PASS
C. mid 2023-2026: Sharpe 2.25->2.25  CAGR 33.57->33.59    PASS
D. shortfall falls by >half: 50,551 -> 50,698             FAIL
E. n100 within 0.10 CAGR: 25.42 -> 25.42 (delta 0.00)     PASS
```

All eight redeployments that fired:

```
2019-09-26  LINDEINDIA    qty     86  px    520.75  Rs     44,784
2019-10-29  BLUESTARCO    qty     10  px    425.35  Rs      4,254
2020-09-14  TIINDIA       qty     86  px    629.95  Rs     54,176
2021-02-05  COROMANDEL    qty    175  px    781.05  Rs    136,684
2021-05-07  PERSISTENT    qty    303  px  1,106.15  Rs    335,163
2021-06-07  COFORGE       qty    242  px    739.95  Rs    179,068
2021-07-05  THERMAX       qty    171  px  1,493.30  Rs    255,354
2022-06-22  POWERINDIA    qty     63  px  3,119.95  Rs    196,557
```

**Verdict.** REJECTED. **Gate D failed** — four of five passed, including all
three performance gates.

**What it taught.** Two things, and the second is a correction that matters more
than the experiment.

**1. Gate D failed for a reason internal to the rule, not an artefact.** Shortfall
went 50,551 → **50,698**, slightly *up*.

> Redeployment does not reduce the shortfall of the order that fell short: the
> original order stays working with its leaves intact, and the redeployment is an
> ADDITIONAL order in a different name. Gate D asked whether the unfilled quantity
> falls by more than half; it does not fall at all, because nothing in the rule
> cancels or reduces the order that could not fill.
>
> Redeploying the CAPITAL and reducing the unfilled QUANTITY are different things,
> and the rule as written does only the first.

Gate D was written expecting to "pass mechanically". It measured the wrong
quantity for the mechanism proposed — and the pre-registration discipline means
that is a rejection, not a footnote. The performance gates all passed; the
experiment still fails.

**2. A recorded correction: my first explanation of the crash was wrong.** The
first EXP21 implementation stopped at 2021-06-07. The cause was reported as: "a
working BUY locks its full notional on a CASH account, and roughly 51,000 unfilled
AIIL shares lock the balance permanently, so every later order is unaffordable."

> **THAT WAS WRONG**, and it was wrong in the exact way the project keeps warning
> about — I inferred a mechanism from order statuses without checking the field
> that would have settled it.
>
> The measurement that refuted it: `balance_locked` is **ZERO on all 1,842 trading
> days** in both universes, while working orders exist on 1,661 of those days. No
> cash was ever locked. The account never withheld a rupee.
>
> The actual cause, from the engine log:
> `2021-06-07T09:16:00 [ERROR] BacktestEngine: Stopping backtest from
> AccountBalanceNegative(balance=-134744.79, INR)`
>
> The failure was the OPPOSITE of what I described. Because `balance_locked` stays
> zero, the account reports cash as FREE while it is already committed to a
> resting order. My redeployment sized against `_free_cash()` and so spent the
> same rupees twice, overdrew the account, and the engine halted the backtest.

The fix — `_committed_notional()` sums `leaves_qty × price` over open BUY orders,
and the redeployment sizes against `(_free_cash() - _committed_notional())` —
is a correctness requirement of the venue's accounting, not a parameter. **It was
chosen from the crash log rather than from what made a gate pass, and Gate D still
fails after it.** The correctness control confirms it changed nothing it should
not: under `DEPTH_MODE="unlimited"` there are zero partial fills and EXP21 is
identical to baseline at 29.16 / 2.00 / −18.95 / 985 trades / 1,842 days.

**A third thing, about an earlier abandoned attempt.** Before the crash was
diagnosed, a version of EXP21 produced mid volume CAGR 22.17 / Sharpe 1.65 with
**379 trades** against the baseline's 1,011 — it had silently broken the
one-order-at-a-time invariant. **The unlimited-depth control is what caught it**:
that arm should have been bit-identical to baseline and was. A control arm whose
only job is to reproduce a known number is cheap and it is the thing that catches
implementation errors masquerading as results. It caught this one twice.

---

### 25. EXP22 — position trim at 20%

*Pre-registration: `experiments/EXP21_EXP22_PREREG.txt` (kept). Result:
`diagnostics/exp21_exp22.txt` (deleted; content reproduced here).*

**What it did.** At each rebalance, any held position whose weight exceeds **20%
of portfolio value** is trimmed back to 20%. Proceeds go to cash and are available
to that rebalance's buys. Applies to held names **regardless of rank** — a
top-ranked name is trimmed the same as a buffer-ranked one, because the rule is
about size, not conviction.

> 20% is fixed here and no other threshold will be tried. With TOP_N=8 the equal
> weight is 12.5%, so 20% is 1.6x equal weight — chosen as a clear excess rather
> than a tuned value.

**Why it was worth testing.** The measured problem, in the forensic log's own
legend: *"Existing holdings are never resized. Only new positions are sized
against the target exposure, so the actual invested percentage can drift from the
target."*

> LLOYDSME ran from Rs 13.90 to Rs 1,711.20, roughly 123x, and its weight grew
> without limit. That is the direct mechanism behind mid's concentration: removing
> LLOYDSME takes mid's edge over its own buy&hold from +1.99 to +0.02, and removing
> TATAINVEST takes it to −0.30.
>
> TOP_N was tested and failed its concentration gate. TOP_N changes how many names
> are held, not how large any one may become. This targets the size directly, which
> nothing tested so far has done.
>
> This was flagged as a pending design question early in this project and never
> tested. It is being tested now rather than left as a note.

**The accept rule — verbatim.** Note Gate D, which is the whole experiment:

> **A.** mid Sharpe not lower, in BOTH depth modes.
> **B.** mid MaxDD not worse by more than 2.0 points.
> **C.** Both sub-periods pass, 2019-2022 and 2023 onward.
> **D.** THE CONCENTRATION TEST IMPROVES MATERIALLY. Removing the single largest
> PnL contributor must leave the edge above +1.00, against the current +0.02.
> **THIS IS THE POINT OF THE EXPERIMENT. A CAGR GAIN WITHOUT A CONCENTRATION
> IMPROVEMENT IS NOT A PASS, AND D CANNOT BE TRADED OFF AGAINST A OR B.**
> **E.** n100 unchanged to within 0.10 CAGR.
>
> REJECT on any single failure. One batch. No variants.

And the expectation, recorded before the run:

> CAGR falls, because trimming a 123x winner cuts the thing that produced the
> return. The question is whether Gate D improves enough to justify it.
> REJECTION IS MORE LIKELY THAN ACCEPTANCE, and that is recorded before the run so
> a rejection cannot later be presented as an unexpected disappointment.

**The result.** Every arm is **bit-identical to its baseline**:

| universe | arm | depth | CAGR | Sharpe | MaxDD | trades | trims |
|---|---|---|---|---|---|---|---|
| mid | baseline | unlimited | 29.16 | 2.00 | −18.95 | 985 | 0 |
| mid | baseline | volume | 27.36 | 1.90 | −18.94 | 1011 | 0 |
| mid | **EXP22** | unlimited | 29.16 | 2.00 | −18.95 | 985 | **0** |
| mid | **EXP22** | volume | 27.36 | 1.90 | −18.94 | 1011 | **0** |
| n100 | baseline | unlimited | 25.43 | 1.88 | −18.61 | 997 | 0 |
| n100 | baseline | volume | 25.42 | 1.88 | −18.61 | 1002 | 0 |
| n100 | EXP22 | unlimited | 25.43 | 1.88 | −18.61 | 997 | 0 |
| n100 | EXP22 | volume | 25.42 | 1.88 | −18.61 | 1002 | 0 |

**Zero trims fired, in either universe, in either depth mode, across 1,842 trading
days.** The largest position weight ever reached was **19.69%**, below the 20%
threshold. *(The 19.69% figure was measured during the run and reported in
session; it does not appear in a surviving result file, and is recorded here on
that basis.)*

**Verdict.** REJECTED at Gate D. The concentration test cannot improve when the
rule never fires — the edge stays at +0.02 by construction.

**What it taught.** This is the only entry in the record whose **premise was
refuted rather than whose remedy was rejected**, and that distinction is the whole
value of it.

The reasoning going in was: LLOYDSME went up 123x, its weight grew without limit,
therefore mid's concentration is a position-size problem, therefore a weight cap
addresses it. The measurement says the second step is false. **No position ever
reached 20% of portfolio value.** The maximum was 19.69%, and it got there once.

Why the intuition failed: the portfolio has 8 positions and rebalances every 20
days with `BUFFER=16`. A name that runs up hard does grow relative to its
neighbours — but it is also being sold when it drops out of the top 16, and the
rest of the book is compounding alongside it. Both effects cap the weight well
below where the naive "123x therefore huge weight" reasoning puts it. **The 123x
happened across multiple entries and exits, not as one position held throughout.**

The consequence is larger than one rejected rule:

> EXP22's premise was refuted, not just rejected — no position ever reached 20% of
> portfolio value (max 19.69%), so no weight cap at any threshold can address mid's
> concentration. That closes an entire remedy family.

Note what "at any threshold" rests on. A cap at 15% or 10% *would* fire. But the
concentration being complained about — that removing LLOYDSME collapses mid's edge
from +1.99 to +0.02 — is not produced by any single position being outsized at any
moment. It is produced by one name contributing most of the PnL *over time*,
through repeated position lifecycles. A weight cap is a point-in-time constraint
on a phenomenon that is not point-in-time. That is why the family closes rather
than the threshold moving.

**The methodological point.** Gate D was pre-registered as untradeable against A
and B, in capitals, before the run. That mattered here in a way that is easy to
miss: EXP22 is *costless* — every performance number is identical to baseline, so
Gates A, B, C and E all pass trivially. An accept rule that summed gate passes, or
that allowed a strong showing on A/B to carry a weak D, would have **accepted a
rule that does nothing at all**. The gate that says "this is the point of the
experiment" is what prevents a no-op from being recorded as a success.

---

### 26. Sizing — equal-rupee against inverse-vol — **VERDICT UNKNOWN**

*Pre-registration: `experiments/sizing_test.py` (**deleted 2026-09-11**; its accept
rule is quoted verbatim below, which is now the only copy) — the accept rule is in the
script's own docstring, and the script is the only surviving artefact.*

**Read the numbering note first.** Chronologically this belongs between entries 20
(EXP17) and 21 (EXP18): the script is dated 2026-08-13, the same day as the
density fix that motivated it and six days before EXP18. It is numbered 26 rather
than inserted in sequence because renumbering would break every cross-reference in
this file, and a stable reference is worth more than a tidy chronology. **It is
not the last experiment the project ran; it is the last one found.**

It was found on 2026-08-23, during a cleanup audit, in a script that had already
been deleted once and was restored from the 2026-08-22 backup. No pre-registration
written after it counts it in its running total.

**What it did.** Replaced inverse-vol position sizing with equal-rupee sizing —
every position takes the same rupee amount rather than an amount inversely
proportional to its trailing volatility. Run on all three universes (58, 74, mid)
through `backtest_exposure(..., mode="breadth", sizing=...)`, with
`target_vol` = median realised portfolio vol and `VOL_WIN=60`.

> Only the weighting changes. Ranking, buffer, breadth exposure, costs, execution
> timing and every parameter are identical between the two arms.

**Why it was worth testing — and this is the part that still matters.** Inverse-vol
was in production carrying real money on the strength of a validation that had
since been withdrawn:

> Inverse-vol sizing's justification rested on a validation that passed 4/4 on a
> panel degraded by the beta_60/idio_vol_60 density bug. On the corrected panel it
> went to 1/4: it beat equal-rupee on no seed set (-0.05, -0.01, -0.10), in
> neither sub-period (-0.04, -0.10), and at no vol window. A component carrying
> real money should not stay in on the strength of evidence that has since been
> withdrawn.

**That motivating measurement survives independently**, and is not reliant on this
entry. It is recorded verbatim in the `validation_status` block of
`results/engine_v2_final.py:144-155` and its three siblings, from which it is
written into each universe's `v2FINAL_params.json` on every run:

```
"measured_on": "post density-fix panel, 2026-08-13, caches rebuilt",
"inv_vol_T1_baseline_control": "PASS",
"inv_vol_T2_seed_robustness":  "FAIL 0 of 3 seed sets (-0.05, -0.01, -0.10); was PASS 3 of 3",
"inv_vol_T3_sub_period":       "FAIL both halves (-0.04, -0.10); was PASS",
"inv_vol_T4_vol_window":       "FAIL 0 of 4 windows beat equal-rupee 1.06 (1.00/1.00/1.04/1.03); was PASS 4 of 4",
```

The engines' own comment on why it is phrased per test rather than as a blanket
claim: *"a stale validation claim is worse than no claim."*

**The accept rule — verbatim from the script.**

> **ACCEPT RULE, FIXED BEFORE ANY RESULT WAS SEEN**
>
> **A.** Equal-rupee must not be worse on Sharpe in any of the three universes.
> **B.** It must not be worse on MaxDD by more than 2.0 points in any universe.
> **C.** Both sub-periods must hold in all three universes.
> **D.** The existing 4-part inverse-vol validation must be re-run with
> equal-rupee as the challenger, and equal-rupee must win at least 3 of 4.
>
> Pass all four -> switch to equal-rupee, because it is simpler and the incumbent
> has no positive evidence behind it.
> Fail any -> keep inverse-vol, and record that its justification is now the
> absence of a better alternative rather than a positive result.
>
> ONE BATCH. No risk-parity, no vol-targeting, no variants afterwards.

Sub-periods as coded: 58 and mid split 2019-2022 / 2023-2026; 74 splits
2019-2022 / 2023-2025.

**The result. NOT RECORDED.** No result file, no captured stdout, no summary line
in any surviving document. The script writes nothing — it prints — and its output
was never redirected to a file that survived.

**Verdict. UNKNOWN.**

**It cannot be inferred from the fact that inverse-vol is still in use.** That
inference is available and it is not sound. The accept rule has two branches and
the project's state is consistent with either: the experiment may have failed a
gate, or it may never have been run to completion at all, or it may have been run
and the switch simply never made. Nothing on disk distinguishes these. Recording
"REJECTED" here because production still uses the incumbent would be exactly the
plausible reconstruction this project forbids — the same error as the locked-cash
explanation in entry 24, which was also a confident mechanism inferred from an
observable state rather than measured.

**What it teaches, without a verdict.** Three things, and the first is the live
one.

1. **Inverse-vol sizing has no positive evidence behind it.** This is not
   contingent on the missing verdict — it comes from the engines' own
   `validation_status` block. Whatever the sizing test concluded, the incumbent's
   4/4 became 1/4 on the corrected panel, and the one branch of the accept rule
   the project can be certain about is that inverse-vol's justification is now
   *"the absence of a better alternative rather than a positive result."*
   **That sentence was written before the run and is true regardless of how it
   came out.** Anyone relying on inverse-vol should know this.
2. **A pre-registered experiment can be lost simply by printing instead of
   writing.** Ten of the project's one-off diagnostics printed to stdout, and the
   three whose output happened to be redirected are the three whose findings
   survived. That is a filing accident, not a decision. Every experiment from
   EXP14 onward wrote a result file, and every one of those verdicts survives.
3. **The trial count was wrong and nothing caught it for ten days.** The
   pre-registration discipline is only as good as the register, and this
   experiment sat outside it from the day it was run.

**If the sizing question is ever revisited, it must be re-registered, not
re-run under the rule above.** The rule was written against the 2026-08-13 panel;
the trial count it would carry today is 25, not the 21 the era assumed; and
re-running an experiment whose original outcome is unknown, then keeping the new
result, is selection on the second draw.

---

### 27. TOP_N=8 revalidated against 12 on the live universes — **NOT CONTRADICTED**

> **The outcome has two halves and they belong together.** TOP_N=8 is NOT
> CONTRADICTED on its pre-registered rule. **In the same measurement TOP_N=12
> had the shallower MaxDD in both universes** — −15.99 against −18.64 on n100,
> −16.65 against −18.98 on mid — on a dimension the rule does not gate. That is
> **not** a claim that 12 is better: its Sharpe is lower in every period and its
> turnover is 40.8% and 48.1% higher. And **no drawdown criterion was
> pre-registered**, so nothing here is a result about drawdown. A reader who
> takes only the first sentence cannot do so honestly.

*Pre-registration: `experiments/TOPN_SPEC.txt` Part B (kept), written before the
code existed. The verdict rule, the single challenger, the BUFFER pin and the
written expectation were all fixed there before any number was produced.*

**Why it counts as a trial.** It runs one value of TOP_N other than 8. Calling it
a validation rather than a search constrains what may be DONE with the result —
no promotion, no second value, no re-run at a changed criterion — and that is the
whole of the difference. It does not exempt it from the denominator.

**What it did.** Ran TOP_N=8 against TOP_N=12 with **BUFFER pinned at 16 in both
arms**, on both live universes, on the current 1,836-day window, through the
SHIPPING engine `test_exposure.backtest_exposure` — the same side of the engine
split as `validate_breadth_live.py`, not `engine_core.backtest`. Both arms in one
process on one panel, proven by a panel hash taken before and after the arms.

**Why 12 and nothing else.** Entry 10 accepted 8 against **12 specifically**, on
the 58 and the 74. Both are now retired, so the honest re-test is that one
contrast on the universes that ship. 5, 6, 10, 16 and 20 were excluded: none was
part of the acceptance, and adding them makes this a sweep. `param_surface.py` and
`mid_topn_test.py` were neither re-run nor edited.

**The accept rule, inherited from entry 10 and inverted to the incumbent's side.**
Sharpe(8) ≥ Sharpe(12) on n100 full, mid full, and both halves of both universes.
Ties hold for the incumbent — deliberately, since the burden is on the challenger,
which is the direction entry 10 imposed on 8 when 8 was the challenger.

**The result. Six of six criteria hold; no split.**

| universe | period | Sharpe 8 | Sharpe 12 | dSharpe | holds |
|---|---|---|---|---|---|
| n100 | full | 1.88 | 1.69 | +0.19 | yes |
| n100 | 2019–2022 | 1.84 | 1.73 | +0.11 | yes |
| n100 | 2023–2026 | 1.65 | 1.54 | +0.11 | yes |
| mid | full | 2.06 | 1.94 | +0.12 | yes |
| mid | 2019–2022 | 1.77 | 1.61 | +0.16 | yes |
| mid | 2023–2026 | 1.96 | 1.74 | +0.22 | yes |

**Verdict. NOT CONTRADICTED — and, in the same measurement, TOP_N=12 held the
shallower drawdown in both universes on an ungated dimension (see the note at
the head of this entry).** That is the ceiling and it is the ceiling in every
outcome, because **the record does not state what BUFFER entry 10's 12-arm ran
at**. Searched across this file, the pre-registrations, `rejected_experiments_
REPORT.txt`, git history — the initial commit already carries `8, 16`, so version
control begins after the acceptance — and every surviving script. All negative. So
this cannot be shown to be entry 10's contrast, and **RE-EARNED is not available
and does not appear in the report.**

**REPORTED, NOT GATED — and one of these runs against the incumbent.** Entry 10
gated on Sharpe alone and this inherits that asymmetry.

| universe | dCAGR (8−12) | dMaxDD (8−12) | trades 8 | trades 12 |
|---|---|---|---|---|
| n100 | +7.10 pt | **−2.65 pt** | 981 | 1,381 |
| mid | +6.36 pt | **−2.33 pt** | 973 | 1,441 |

**TOP_N=12 has the SHALLOWER drawdown in both universes.** The rule does not see
it, because it gates on Sharpe. This is exactly the hole the spec named in advance
— "a challenger that matched Sharpe while halving drawdown would not be detected
by this rule" — and it is recorded here rather than left in the artefact.

**NO DRAWDOWN CRITERION IS ADDED.** Adding one now, with these numbers in view,
would be fitting the rule to the data — the precise thing that documenting the
Sharpe-only asymmetry rather than harmonising it was meant to avoid. It stays
ungated and recorded, on the same footing as T3 in `BREADTH_LIVE_SPEC.txt`.

**THE WRITTEN EXPECTATION WAS WRONG ON TWO OF ITS FOUR POINTS.** Recorded as a
contradiction of a written prediction, not smoothed over.

1. Predicted a hold on n100 with moderate-to-high confidence — **correct**.
2. Predicted the closest call would be on **mid**, in a sub-period. **Wrong.** The
   two tightest margins are both on n100 (+0.11 in each half); mid's halves came
   in at +0.16 and +0.22.
3. Predicted TOP_N=12 would show **higher** cash-short skips than 8, since twelve
   targets funded from cash alone is more pressure on the funding defect.
   **WRONG, AND IN THE OPPOSITE DIRECTION.** TOP_N=12 records **zero** skips in
   both universes against 7 on n100 and 1 on mid for the incumbent. The spec said
   in advance that if this failed, "my model of that defect is wrong and that is
   worth more than the TOP_N result". It failed. The mechanism binds on
   PER-NAME TARGET SIZE, not on the count of targets: `invest_val` is split
   TOP_N ways, so each new entrant at 12 needs a smaller slice of cash than at 8,
   and the score-descending loop exhausts cash less often. Mean names held moves
   9.54 → 12.88 on n100 and 9.23 → 12.88 on mid, so the fuller book also leaves
   fewer new entrants to fund each rebalance.
4. Predicted a split as the single likeliest outcome — **wrong**, both universes
   held.

**What it did NOT establish.** That 8 is optimal — two arms cannot say that.
That the pin is neutral — 8/16 leaves an eight-rank hysteresis band and 12/16
leaves four, so the challenger runs +40.8% and +48.1% more trades, and this test
cannot separate "8 is a better concentration" from "16 suits 8 better than it
suits 12". Nothing about BUFFER, which was pinned and never varied. And no
significance test: two Sharpe ratios were compared by inequality, and nothing here
says a +0.11 gap is larger than noise.

**Artefacts.** `results_{n100,mid}/metrics/topn_full.csv`, `topn_subperiods.csv`,
`topn_params.json`; `diagnostics/topn_{n100,mid}.txt` and
`diagnostics/topn_verdict.txt`. Script: `results/validate_topn.py`. The incumbent
arm reproduces the shipped v2 on CAGR, Sharpe and MaxDD in both universes, read
from `v34_comparison.csv` rather than typed in, as a correctness gate that voids
the run on failure.

---

### 28. Shuffle test — randomised scores against the real model — **PASS**

*Pre-registration: `experiments/SHUFFLE_SPEC.txt`, written 2026-09-01 before any
code existed. The permutation, N, the statistic, the 0.05 bar, the gated arms and
the written expectation were all fixed there before any number was produced.*

**THE FIRST SIGNIFICANCE TEST THIS PROJECT HAS EVER RUN.** The `[PASS] Shuffle
test` rows in the old run logs were hardcoded string literals, removed from
`engine_core.py` on 2026-08-29. Nothing was re-run; this is the first time.

**What it did.** For each date independently, permuted the non-NaN scores across
the symbols that had one — preserving the per-date score distribution and the set
of scorable names, destroying only the symbol→score mapping. Everything else held
bit for bit. 100 permutations × 4 arms × 2 universes = 800 backtests on the
shipping engine, 77 seconds.

**Gated:** one-sided CAGR permutation p < 0.05 on v1 and v2, both universes.

| universe | arm | real CAGR | null median | effect | shuffles beating real | p |
|---|---|---|---|---|---|---|
| n100 | v1 | 35.13 | 15.44 | **+19.69 pt** | **0 of 100** | 0.0099 |
| n100 | v2 | 25.49 | 11.42 | **+14.07 pt** | **0 of 100** | 0.0099 |
| mid | v1 | 45.87 | 15.80 | **+30.07 pt** | **0 of 100** | 0.0099 |
| mid | v2 | 30.22 | 11.28 | **+18.94 pt** | **0 of 100** | 0.0099 |

0.0099 is the floor at N=100, i.e. `(1+0)/101`. **Not one permutation out of 100
matched the real arm on any gated arm.** The ungated arms agree: v4 p = 0.0099 on
both; v3 p = 0.0297 on n100 (2 of 100 beat it) and 0.0099 on mid. Sharpe, reported
not gated, gives p = 0.0099 for v1 and v2 on both universes.

**THE MECHANICS DO NOT CARRY THE RETURN — THEY COST IT.** Random 8-name selection
at 100% invested returns a median 15.44% on n100 against 23.74% for equal-weight
buy & hold of the same 99 names, and 15.80% against 27.77% on mid. **Concentration
into 8 names plus turnover is worth roughly −8 and −12 CAGR points against simply
holding the universe.** The model is not merely beating a random selector; it is
overcoming a substantial drag that the random selector also pays.

**MaxDD is NOT distinguishable from the null** — p = 0.37 and 0.36 for v1 and v2
on n100, 0.20 and 0.44 on mid. The drawdown profile is a property of the
mechanics, not of the model's selection. For the breadth arms that is expected and
was predicted; for v1 it is worth stating plainly.

**THE WRITTEN EXPECTATION WAS WRONG ON ITS MOST SPECIFIC POINT.**

1. v1 passes on both, comfortably — **correct**.
2. Predicted n100 v2 as "the most likely failure in the suite", confidence "a
   little under even" that it fails. **WRONG, and not marginally**: 0 of 100, the
   minimum attainable p. **The reasoning error is identifiable and worth keeping.**
   The prediction anchored on v2's 1.75-point edge over equal-weight buy & hold —
   but buy & hold is 100% invested and v2 deploys 56.6%. The correct null holds
   deployment identical, and random selection at 56.6% returns 11.42%, not 23.74%.
   **A 100%-invested benchmark was being used to reason about a 56%-invested arm.**
3. Shuffled breadth arms keep the drawdown advantage — **correct**, −19.77 against
   −37.06 on n100 and −19.76 against −37.96 on mid.
4. Predicted shuffled arms might beat buy & hold — **wrong**, all eight land below
   it, which is the concentration-drag finding above.

**What this does NOT establish, and the ceiling is low.** It does not correct for
the ≥26-trial denominator: this configuration was chosen after 26 recorded passes
over the same data, and a p of 0.0099 is **not** the probability that the strategy
is noise. **It does not address survivorship — the null carries the same bias**,
since every shuffled portfolio draws from the same backfilled membership; this test
would pass just as easily on an inflated universe. It does not test breadth, which
is invariant under the shuffle. It does not make the return tradable.

**Artefacts.** `results_{n100,mid}/metrics/shuffle_{summary,draws,params}`;
`diagnostics/shuffle_{n100,mid}.txt` and `diagnostics/shuffle_verdict.txt`.
Script: `results/shuffle_test.py`. The real v2 arm reproduced the shipped figure on
CAGR, Sharpe and MaxDD in both universes as a correctness gate, read from
`v34_comparison.csv` rather than typed in.

---

### 29. The seed noise floor — **MEASURED, AND IT SWALLOWS THE PURGE RESULT**

*Pre-registration: `experiments/SEED_NOISE_SPEC.txt`, written 2026-09-02 before
any code existed. The design, the K grid, the subset count, the limits and the
written prediction were fixed there before any number was produced.*

**Why it was run.** Entry 28's purge measurement reported shipping-arm deltas of
+0.54 (n100) and −0.81 (mid) and judged them against a **0.5-point noise floor
that was invented, not measured**. It was pre-registered, which made it honest,
but not correct. This measures the floor.

**Design.** 40 distinct seeds fitted once per universe, **every seed's scores
stored separately**, sub-ensembles of size K formed afterwards by averaging K
stored columns. Same fitting cost as four separate 10-seed runs, but it yields an
empirical σ(K) curve rather than an assumed 1/√K scaling. First 10 seeds are the
production set. Everything except the seeds held fixed, including the **current**
production purge, so the shipped configuration is one draw of the distribution
being measured. K ∈ {1,2,3,5,10,20,40}, 50 random subsets per K. Wall clock
**130 min 16 sec** for the fitting, **2 min** for the sub-ensemble analysis.

**The floor, at K = 10 — the ensemble size that ships.**

| universe | arm | CAGR sd | CAGR range | Sharpe sd | MaxDD sd |
|---|---|---|---|---|---|
| n100 | v1 | 1.74 | 7.68 | 0.07 | 1.57 |
| n100 | **v2** | **0.97** | **4.17** | 0.06 | 1.62 |
| mid | v1 | 2.14 | 10.26 | 0.07 | 1.34 |
| mid | **v2** | **1.39** | **6.12** | 0.08 | 0.88 |

**THE PURGE RESULT IS INCONCLUSIVE AT ITS DESIGN. All four deltas sit inside the
spread.**

| universe | arm | purge dCAGR | seed sd | % of seed draws deviating by ≥ \|delta\| | verdict |
|---|---|---|---|---|---|
| n100 | v1 | +1.42 | 1.74 | 36% | INSIDE |
| n100 | v2 | +0.54 | 0.97 | **60%** | INSIDE |
| mid | v1 | −1.70 | 2.14 | 48% | INSIDE |
| mid | v2 | −0.81 | 1.39 | 50% | INSIDE |

On n100 v2, **60% of seed draws move further from their own median than the entire
purge effect did**. The purge correction is real and the leak it fixes is real —
see the leakage audit — but its measured return impact cannot be distinguished
from ordinary re-fit variation. Entry 28's headline deltas should not be quoted as
effects.

**σ(K) IS NEARLY FLAT, AND THAT IS THE MOST IMPORTANT NUMBER HERE.**

| universe | arm | fitted σ(K) | exponent |
|---|---|---|---|
| n100 | v1 | 2.180·K^(−0.150) | −0.150 |
| n100 | v2 | 1.559·K^(−0.226) | −0.226 |
| mid | v1 | 3.632·K^(−0.245) | −0.245 |
| mid | v2 | 1.801·K^(−0.168) | −0.168 |

Independent noise averages down at K^(−0.5). **Every observed exponent is between
−0.15 and −0.25, less than half of that.** The seed-to-seed variation is largely
*common*, not independent, so adding seeds barely helps: n100 v2 falls only from
1.57 at K=1 to 0.97 at K=10.

**Seeds required for ±0.5-point stability — extrapolated, and the extrapolation is
the point:** n100 v2 **152**, mid v2 **2,044**, mid v1 **3,310**, n100 v1
**17,889**. No tested K up to 40 comes close. These assume the fitted exponent
holds far outside the measured range and should be read as "far more than is
practical", not as targets.

**Year-level spread confirms this is one phenomenon, not two.** At K=10, changing
only the seeds moves individual years by:

| universe | arm | worst year | range |
|---|---|---|---|
| n100 | v1 | 2021 | 34.16 pt |
| n100 | v2 | 2023 | 19.95 pt |
| mid | v1 | 2021 | **48.06 pt** |
| mid | v2 | 2021 | 27.72 pt |

The purge run's 21-point year swings were **never evidence about the purge**.
Seed changes alone produce swings of the same size and larger. **This and the
purge run's year-level result are ONE finding about model stability.**

**A THIRD INSTANCE, AND THE SMALLEST PERTURBATION YET.** The identity gate in this
run FAILED and correctly refused to report anything: the production 10 seeds
reproduced from the store gave CAGR 26.15 on n100 against 25.49 recorded. Cause,
diagnosed and measured: `build_scores_*.py` calls `score_monthly` on the
**in-memory** panel, while this store was fitted on `raw_panel_*_cache.csv` read
back from disk. The two differ by **one unit in the last place — max 4.441e-16
across 2,638,259 cells**. That is enough to change LightGBM split decisions, flip
near-tied ranks, and move headline CAGR by **+0.66 on n100 and −0.29 on mid**.

**A last-bit float difference moves the shipping arm more than the purge fix did.**
The spread above is unaffected — all 40 seeds share one panel — and the baseline
offset is stated in `diagnostics/seed_noise.txt` rather than hidden. This finding
warrants its own `KNOWN_ISSUES.md` entry; none was added, as this task was scoped
to the experiment record only.

> **CORRECTION, 2026-09-02.** The last sentence above is now false and is left
> standing rather than rewritten. **A `KNOWN_ISSUES.md` entry was subsequently
> added**: *"The headline is not reproducible from the artefacts on disk to better
> than about a point"*, dated 2026-09-02 and attributed to this run's identity gate
> failing. It carries the 4.441e-16 maximum difference across 2,638,259 cells, the
> +0.66 / −0.29 headline offsets, and the three options for closing it. It also
> places this finding alongside the other two perturbation scales — training rows
> moved, and seeds redrawn — as three measurements of one property rather than
> three defects. **No figure in this entry is amended by this correction**; only
> the claim that no entry existed was wrong.

**Predictions, judged.**

1. σ(CAGR) ≈ 1–2 on v2, range 3–6 — **correct** (0.97/4.17 and 1.39/6.12).
2. Purge deltas inside the spread, measurement inconclusive — **correct**, and it
   was recorded in advance precisely because it retracts a result reported hours
   earlier.
3. Year-level spread in double digits, one finding not two — **correct**.
4. Seeds needed 50–250 — **correct for n100 v2 (152), badly wrong for the other
   three** (2,044 to 17,889). The error was assuming an exponent near −0.5; the
   measured exponents are −0.15 to −0.25, which is itself the finding.
5. v1 noisier than v2 — **correct** in every case.
6. Published headlines unchanged — **correct**; the production seeds remain a
   legitimate draw.

**What this does not say.** It does not say the strategy is wrong; a wide spread
is a statement about resolution, not about the mean. It does not retroactively
re-judge past experiments — but **any past decision resting on a difference
smaller than ~1 CAGR point was resting on less than it appeared to**, and
identifying which is a separate task not undertaken here.

**Artefacts.** `results_{n100,mid}/metrics/seed_noise_{headline,yearly,sigma_k}.csv`;
`diagnostics/seed_noise.txt`. Scripts: `results/seed_noise_measure.py` (fitting),
`results/seed_noise_report.py` (sub-ensembles). Per-seed stores retained at
`results/SEEDNOISE_{uni}_scores.npy`.

---

## The purge correction was applied, and the headline moved. 2026-09-02.

Not an experiment and not a trial — a **correctness repair** with a measured
consequence. It carries no accept rule because nothing was being accepted.

**Why it was applied.** The calendar-day purge is wrong by construction: 32
CALENDAR days against a label spanning 20 TRADING rows, so the margin varies with
the holiday calendar and underflows. Measured in `diagnostics/LEAKAGE_AUDIT.txt`:
the label reached into the scored month in 7 of 126 months and touched its first
day in 21 more, identically on both universes. **It was repaired because it is
defective, NOT because of any return impact.**

**What changed.** `engine_core.score_monthly` gained `purge_mode`, defaulting to
`"trading"` — `cut = cal[i_first - HORIZON - 2]`, in trading rows, which cannot
underflow. Verified **min = median = max = 2 on all 126 months, both universes,
zero months at or below zero**. The retired 58 and 74 are pinned to
`purge_mode="calendar"` so their frozen numbers still reproduce.

**The new headline. Window 2019-01-01 to 2026-05-29, 1,836 trading days.**

| universe | arm | CAGR was | CAGR now | Δ | Sharpe now | MaxDD now | Trades now |
|---|---|---|---|---|---|---|---|
| n100 | v1 | 35.13 | 35.01 | −0.12 | 1.64 | −35.50 | 813 |
| n100 | **v2 (ships)** | 25.49 | **25.78** | **+0.29** | 1.87 | −19.96 | 978 |
| n100 | v3 | 27.91 | 29.09 | +1.18 | 1.23 | −45.58 | 788 |
| n100 | v4 | 23.89 | 22.86 | −1.03 | 1.41 | −22.08 | 980 |
| mid | v1 | 45.87 | 45.92 | +0.05 | 1.84 | −34.68 | 833 |
| mid | **v2 (ships)** | 30.22 | **29.71** | **−0.51** | 2.03 | −18.93 | 963 |
| mid | v3 | 48.98 | 49.54 | +0.56 | 1.79 | −35.76 | 792 |
| mid | v4 | 32.74 | 32.31 | −0.43 | 1.92 | −17.50 | 961 |

Equal-weight buy & hold is unchanged in both (23.74 and 27.77), as it must be —
it does not depend on scores.

**NEITHER MOVE IS TO BE QUOTED AS AN EFFECT.** Entry 29 measured the seed noise
floor at **sd 0.97 (n100 v2) and 1.39 (mid v2)**, with ranges of 4.17 and 6.12
across 50 ten-seed draws. **+0.29 and −0.51 sit well inside that.** They move in
opposite directions on the two universes. Nothing here says the strategy improved
or worsened; these are simply the numbers the corrected code produces.

### The three purge-effect figures, reconciled — carry the third

Three different deltas have been reported for the same change. They differ
because they were measured on different panels, and only one describes the path
that ships.

| figure | n100 v2 | mid v2 | what it actually compared | status |
|---|---|---|---|---|
| first reported | +0.54 | −0.81 | in-memory panel + old purge **vs CSV panel + new purge** | **CONTAMINATED** — mixes the purge change with the one-bit CSV round-trip, which alone is worth +0.66 on n100 |
| second | −0.12 | −0.52 | CSV panel, old vs new purge | like-for-like but on a panel that **does not ship** |
| **third** | **+0.29** | **−0.51** | **in-memory panel, old vs new purge** | **CARRY THIS ONE** |

The third is the one to carry because `build_scores_*.py` scores the **in-memory**
panel — that is the production path, and both sides of the comparison sit on it.
The first is superseded and should not be requoted anywhere; it was reported
before the CSV round-trip defect had been found. All three sit inside the seed
floor, so the reconciliation changes the number without changing the conclusion.

**Artefacts.** `results_{n100,mid}/metrics/v34_comparison.csv`, `v2FINAL_*`,
`chart_v34.png`, `chart_COMBINED_n100_mid.png`, all regenerated 2026-09-02 15:06.
Nautilus gate re-run and **VERIFIED at 92 of 92 rebalances on both universes** on
the 0.01 tick grid, with the ARM A control at 92 of 92. Execution timing re-checked
against the new `fills.csv`: 977 of 978 and 961 of 963 at the fill day's open, zero
at any close. Measured wall clock: **36 min 07 sec** to re-score, under 1 min
downstream, 1 min for the gate.

**Chart captions.** Three hardcoded liquidity blocks carrying void 1,842-day
figures were removed rather than recomputed — no liquidity or depth study has been
run on the current window, and substituting an unsourced number would be worse
than the staleness. Every chart now opens with its window and states that every
CAGR, Sharpe, drawdown and trade count on it belongs to that window.

---

### 30. Rebalance cadence sweep on the shipping arm — **NO CADENCE QUALIFIES; THE UNIVERSES DISAGREE**

*Pre-registration: `experiments/REBAL_CADENCE_SPEC.txt`, written 2026-09-03
before any code existed. The four cadences, the control, the trial-count charge,
the noise-floor rule and seven numbered predictions were all fixed there first.*

**NO ACCEPT RULE. NOTHING IS PROMOTED.** This is a survey of a parameter's effect,
not a selection procedure. It has no gate and no criterion by which a cadence
wins.

**Why it could be run at all.** `REBAL` is **already** counted in trading rows —
`test_exposure.py:145` reads `if i % REBAL == 0 and i < len(dates) - 1` where `i`
indexes the panel's own trading calendar. There is no unit mismatch here and this
is **not** the calendar-day purge defect again. No refactor was needed.

**Method.** v2 (inverse-vol, `mode="breadth"`, the shipping arm), both live
universes, `REBAL` in {5, 10, 20, 40}, off the **existing** score panels — no
refit, no rescore. Only the book's rebalance clock changed.

**THE OBVIOUS ROUTE WAS WRONG AND WAS CAUGHT BEFORE THE RUN.**
`engine_core.backtest` takes `rebal` as a parameter but **has no breadth mode** —
only `sizing="equal"/"invvol"`, every book always-invested — so it cannot express
v2 at all, and it is a different implementation 1.80 CAGR points from the shipping
engine on the 58. The cadence was instead varied by assigning
`test_exposure.REBAL` as a module attribute at runtime. **No file on disk was
modified**; SHA256 of `test_exposure.py` verified identical before and after, and
the constant is still 20.

**HORIZON STAYED AT 20 ROWS AT EVERY CADENCE.** At REBAL=5 the model predicts 20
rows forward while the book turns over in 5; at REBAL=40 it holds for twice the
horizon it was fitted to predict. The mismatch is deliberate — cadence measured
alone — and **no cell here is an optimised cadence**. `HORIZON` and `REBAL` are
independent in the code (`engine_core.py:90`) and equal at 20 by coincidence of
value, not construction.

**THE CONTROL REPRODUCED EXACTLY**, all five quantities on both universes, read
from `v34_comparison.csv` rather than typed in: n100 25.78 / 1.87 / −19.96 / 978 /
245,816 and mid 29.71 / 2.03 / −18.93 / 963 / 229,916.

**NIFTY 100** — seed floor 0.97

| REBAL | rebals | CAGR% | Sharpe | MaxDD% | trades | TC Rs | TC/eq% | dCAGR | vs floor |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 367 | 17.79 | 1.39 | −18.50 | 2,439 | 4,26,566 | 12.69 | −7.99 | outside |
| 10 | 184 | 22.64 | 1.72 | −18.69 | 1,524 | 3,12,485 | 6.89 | −3.14 | outside |
| **20** | 92 | **25.78** | **1.87** | **−19.96** | **978** | **2,45,816** | 4.50 | control | control |
| 40 | 46 | 22.26 | 1.68 | −25.61 | 533 | 1,11,125 | 2.51 | −3.52 | outside |

**MIDCAP150** — seed floor 1.39

| REBAL | rebals | CAGR% | Sharpe | MaxDD% | trades | TC Rs | TC/eq% | dCAGR | vs floor |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 367 | 27.87 | 1.90 | −16.53 | 2,468 | 5,69,996 | 9.23 | −1.84 | outside |
| 10 | 184 | 30.05 | 1.96 | −16.49 | 1,577 | 4,10,533 | 5.86 | +0.34 | **INSIDE** |
| **20** | 92 | **29.71** | **2.03** | **−18.93** | **963** | **2,29,916** | 3.35 | control | control |
| 40 | 46 | 32.72 | 2.12 | −18.01 | 560 | 1,53,703 | 1.89 | +3.01 | outside |

**THE UNIVERSES DISAGREE ON THE SIGN AT TWO OF THE THREE NON-CONTROL CADENCES** —
REBAL=10 (−3.14 against +0.34) and REBAL=40 (−3.52 against +3.01). Only REBAL=5
agrees, and it is worse on both. **No cadence beats REBAL=20 by more than the seed
floor on both universes simultaneously.**

**THE ONE FAVOURABLE CELL, STATED AS A MEASUREMENT AND NOT AS A CANDIDATE.**
REBAL=40 on mid returns 32.72 against 29.71, +3.01, outside the 1.39 floor, at
Sharpe 2.12 against 2.03. **n100 contradicts it by 3.52 points in the opposite
direction**, outside its own floor. Under this project's own standard a result the
two universes disagree on in sign is the finding, not the number.

**AND CAPACITY IS NOT MEASURED HERE AT ALL, WHICH BEARS DIRECTLY ON THAT CELL.**
Fills are synthetic against a `QUOTE_DEPTH` of 10,000,000 shares at a flat 15 bps
slippage regardless of order size; no L2 data exists anywhere in this project, no
market impact, no queue position. **mid already has a measured liquidity problem —
one order reached 1,614% of that symbol's prior 20-day median volume.** REBAL=40
trades less often but in **larger clips per rebalance** — TC per rebalance 3,341
against 2,499 at the control, the highest in the sweep — so it concentrates rather
than relieves that exposure. **A cadence that trades differently is not shown to be
executable differently, in either direction.**

**PREDICTIONS, JUDGED. Six of seven correct; P5 wrong.**

1. **P1** control reproduces exactly — **CORRECT**, all ten quantities.
2. **P2** rebalance counts 367 / 184 / 92 / 46 — **CORRECT**, exactly, both
   universes. Arithmetic, judged anyway because a disagreement would have flagged
   a harness fault.
3. **P3** trades rise sublinearly, 2× to 3.5× at REBAL=5 — **CORRECT, at the
   bottom of the stated range**: 2.49× and 2.56× against 4× the rebalances. The
   predicted mechanism — `BUFFER = 16` hysteresis leaving more rebalances finding
   the book already correct — is what produced it. Predicted 2,000–3,400 trades on
   n100 against a naive ~3,900; actual 2,439.
4. **P4** CAGR falls at REBAL=5 on both universes by more than the seed floor —
   **CORRECT. It held.** n100 −7.99, mid −1.84, both outside, same sign. This was
   flagged in the spec as the prediction most likely to be wrong, on the reasoning
   that scores vary daily within a scored month so a shorter cadence acts on
   genuinely fresher information. **That reservation was unnecessary**: TC reaches
   12.69% of final equity at REBAL=5 on n100 against 4.50% at the control, and the
   fresher scores did not come close to paying for it.
5. **P5** REBAL=40 lands inside the seed floor on at least one universe —
   **WRONG.** It is outside on both: −3.52 on n100 and +3.01 on mid. The reasoning
   was that halved TC and increased staleness would partly cancel. Instead
   REBAL=40 produced the largest single divergence in the sweep on mid and a large
   one on n100, **in opposite directions**.
6. **P6** the universes disagree on the sign of at least one cadence change —
   **CORRECT**, at two of three. A prediction about this project rather than about
   cadence; lesson 3 held again.
7. **P7** no cadence beats REBAL=20 by more than the floor on both universes
   simultaneously — **CORRECT**. Nothing qualifies.

**TRIAL COUNT. This sweep is charged as FOUR looks at the shipping arm**, taking
this file's floor from 28 to 32. The control is charged too: it is a control, not
a free observation — the sweep still looked at the data with it in hand. The
argument for charging 3 was available and was not taken, because this project's
count has understated at least three times and the error always runs toward more
looks. **No result here is corrected for that denominator.**

**WHAT THIS DOES NOT ESTABLISH.** Not an optimal cadence — the label is pinned at
20 rows. Not a joint cadence-and-horizon result — no refit was performed at any
cadence. **Nothing about drawdown**: there is no measured noise floor for MaxDD and
entry 28 could not distinguish it from a random-selection null, so no drawdown
difference in the tables above may be read as an effect. Nothing about capacity.
Nothing about whether any cadence ranking survives redrawing the seeds — one
ten-seed panel was used, and entry 29 established that redrawing them moves the
shipping arm by sd 0.97 to 1.39 on its own.

**Artefacts.** `diagnostics/rebal_cadence_sweep.txt`. Script:
`results/rebal_cadence_sweep.py`, which asserts the override before each call and
reads every control value from `v34_comparison.csv` rather than carrying it. Wall
clock **2 sec**, eight backtests, no refit.

---

### 31. Rebalance cadence across all four arms — **ONLY v2 HAS A TRUSTWORTHY VERDICT, AND IT IS: NO CADENCE BEATS REBAL=20**

*Pre-registration: `experiments/REBAL_CADENCE_SPEC.txt` PART 8, written 2026-09-03
after entry 30's v2 result and **before any four-arm number existed**. The grid,
the eight controls, the trial charge, the floor rules and eight numbered
predictions Q1–Q8 were all fixed there first.*

**NO ACCEPT RULE. NOTHING IS PROMOTED.** Extends entry 30 from v2 alone to all
four arms of `V34_SPEC.txt`, both live universes, `REBAL` in {5, 10, 20, 40} —
**32 cells, 8 controls**. Off the existing score panels: no refit, no rescore.
Cadence varied by assigning `test_exposure.REBAL` at runtime; **no file on disk
modified**, SHA256 of `test_exposure.py` identical before and after, constant
still 20.

**ALL EIGHT CONTROLS REPRODUCED**, on seven quantities each — CAGR, Sharpe,
MaxDD, AnnVol, Trades, TC and FinalEquity — read from `v34_comparison.csv` rather
than typed in.

---

**THREE THINGS THAT BELONG WITH THE TABLE, NOT UNDER IT**

1. **HORIZON IS 20 TRADING ROWS IN EVERY CELL.** No arm is refitted at any
   cadence. **No cell in this grid is an optimised cadence for its arm.** At
   REBAL=5 the model predicts 20 rows forward while the book turns over in 5; at
   REBAL=40 it holds for twice the horizon it was fitted to predict.
2. **NO FLOOR WAS EVER MEASURED FOR SHARPE, ON ANY ARM.** The Sharpe column is
   reported because it was asked for. **No Sharpe difference across any cells in
   this grid may be read as an effect.**
3. **NO FLOOR EXISTS FOR MaxDD EITHER.** Entry 28's shuffle test could not
   distinguish MaxDD from a random-selection null (p 0.37/0.36 on n100, 0.20/0.44
   on mid). **No drawdown difference across any cells may be read as an effect.**
   AnnVol likewise has no floor.

**CAGR FLOORS ARE PER ARM, AND TWO ARMS HAVE NONE.** Entry 29 measured v1 and v2
only:

| arm | n100 | mid | status |
|---|---|---|---|
| v1 | 1.74 | 2.14 | measured |
| **v2** | **0.97** | **1.39** | measured — the shipping arm |
| v3 | — | — | **NEVER MEASURED** |
| v4 | — | — | **NEVER MEASURED** |

**UNKNOWN IS NOT A NEAR-MISS.** It means no floor was ever measured for that arm,
so whether the cell is an effect or noise **is not established by this grid**, in
either direction.

---

**NIFTY 100** — 1,836 trading days

| arm | REBAL | rebals | CAGR% | dCAGR | floor | Sharpe | MaxDD% | AnnVol% | trades | TC Rs | TC/eq% | FinalEquity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 | 5 | 367 | 27.74 | −7.27 | outside | 1.39 | −26.94 | 19.30 | 1,807 | 8,05,138 | 13.13 | 61,30,186 |
| v1 | 10 | 184 | 33.51 | −1.50 | INSIDE | 1.62 | −32.09 | 19.29 | 1,177 | 6,33,441 | 7.45 | 85,01,373 |
| v1 | **20** | 92 | 35.01 | +0.00 | control | 1.64 | −35.50 | 19.81 | 813 | 5,08,341 | 5.50 | 92,36,608 |
| v1 | 40 | 46 | 30.28 | −4.73 | outside | 1.50 | −35.17 | 19.11 | 457 | 2,41,329 | 3.40 | 70,92,575 |
| **v2** | 5 | 367 | 17.79 | −7.99 | outside | 1.39 | −18.50 | 12.59 | 2,439 | 4,26,566 | 12.69 | 33,61,128 |
| **v2** | 10 | 184 | 22.64 | −3.14 | outside | 1.72 | −18.69 | 12.55 | 1,524 | 3,12,485 | 6.89 | 45,33,937 |
| **v2** | **20** | 92 | **25.78** | +0.00 | control | 1.87 | −19.96 | 12.96 | 978 | 2,45,816 | 4.50 | **54,65,550** (ships) |
| **v2** | 40 | 46 | 22.26 | −3.52 | outside | 1.68 | −25.61 | 12.67 | 533 | 1,11,125 | 2.51 | 44,30,597 |
| v3 | 5 | 367 | 31.43 | +2.34 | **UNKNOWN** | 1.33 | −30.01 | 22.98 | 1,800 | 8,81,107 | 11.64 | 75,67,064 |
| v3 | 10 | 184 | 33.98 | +4.89 | **UNKNOWN** | 1.42 | −37.70 | 22.88 | 1,160 | 6,27,954 | 7.19 | 87,28,602 |
| v3 | **20** | 92 | 29.09 | +0.00 | control | 1.23 | −45.58 | 23.39 | 788 | 3,99,707 | 6.03 | 66,25,976 |
| v3 | 40 | 46 | 31.19 | +2.10 | **UNKNOWN** | 1.36 | −39.74 | 22.10 | 432 | 2,32,194 | 3.11 | 74,67,360 |
| v4 | 5 | 367 | 20.64 | −2.22 | **UNKNOWN** | 1.32 | −22.57 | 15.34 | 2,435 | 4,40,809 | 10.98 | 40,13,618 |
| v4 | 10 | 184 | 23.95 | +1.09 | **UNKNOWN** | 1.50 | −22.02 | 15.38 | 1,534 | 3,12,189 | 6.37 | 49,04,148 |
| v4 | **20** | 92 | 22.86 | +0.00 | control | 1.41 | −22.08 | 15.71 | 980 | 2,15,835 | 4.70 | 45,94,334 |
| v4 | 40 | 46 | 24.25 | +1.39 | **UNKNOWN** | 1.50 | −28.53 | 15.54 | 529 | 1,17,222 | 2.35 | 49,92,010 |

**MIDCAP150** — 1,836 trading days

| arm | REBAL | rebals | CAGR% | dCAGR | floor | Sharpe | MaxDD% | AnnVol% | trades | TC Rs | TC/eq% | FinalEquity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 | 5 | 367 | 39.67 | −6.25 | outside | 1.69 | −37.31 | 21.49 | 1,858 | 12,12,791 | 10.21 | 1,18,72,717 |
| v1 | 10 | 184 | 44.26 | −1.66 | INSIDE | 1.81 | −35.80 | 21.97 | 1,247 | 10,68,830 | 7.08 | 1,50,91,267 |
| v1 | **20** | 92 | 45.92 | +0.00 | control | 1.84 | −34.68 | 22.24 | 833 | 6,82,235 | 4.15 | 1,64,19,894 |
| v1 | 40 | 46 | 41.94 | −3.98 | outside | 1.78 | −34.98 | 21.35 | 460 | 3,37,145 | 2.52 | 1,33,77,258 |
| **v2** | 5 | 367 | 27.87 | −1.84 | outside | 1.90 | −16.53 | 13.65 | 2,468 | 5,69,996 | 9.23 | 61,75,084 |
| **v2** | 10 | 184 | 30.05 | +0.34 | INSIDE | 1.96 | −16.49 | 14.19 | 1,577 | 4,10,533 | 5.86 | 70,01,699 |
| **v2** | **20** | 92 | **29.71** | +0.00 | control | 2.03 | −18.93 | 13.51 | 963 | 2,29,916 | 3.35 | **68,64,240** (ships) |
| **v2** | 40 | 46 | 32.72 | +3.01 | outside | 2.12 | −18.01 | 14.06 | 560 | 1,53,703 | 1.89 | 81,35,706 |
| v3 | 5 | 367 | 42.58 | −6.96 | **UNKNOWN** | 1.61 | −30.36 | 24.24 | 1,816 | 14,94,166 | 10.80 | 1,38,33,758 |
| v3 | 10 | 184 | 50.13 | +0.59 | **UNKNOWN** | 1.78 | −39.81 | 25.07 | 1,211 | 13,34,475 | 6.58 | 2,02,73,311 |
| v3 | **20** | 92 | 49.54 | +0.00 | control | 1.79 | −35.76 | 24.53 | 792 | 8,14,788 | 4.14 | 1,96,91,257 |
| v3 | 40 | 46 | 59.62 | +10.08 | **UNKNOWN** | 2.09 | −28.49 | 24.17 | 448 | 7,05,733 | 2.21 | 3,19,24,845 |
| v4 | 5 | 367 | 29.54 | −2.77 | **UNKNOWN** | 1.77 | −19.00 | 15.58 | 2,470 | 5,87,538 | 8.64 | 67,98,550 |
| v4 | 10 | 184 | 36.25 | +3.94 | **UNKNOWN** | 2.01 | −15.94 | 16.36 | 1,575 | 5,06,021 | 5.12 | 98,80,841 |
| v4 | **20** | 92 | 32.31 | +0.00 | control | 1.92 | −17.50 | 15.48 | 961 | 2,53,221 | 3.18 | 79,52,034 |
| v4 | 40 | 46 | 40.63 | +8.32 | **UNKNOWN** | 2.18 | −21.53 | 16.55 | 558 | 2,09,583 | 1.68 | 1,24,94,519 |

Rebalance counts are 367 / 184 / 92 / 46 in every cell, identical across arms —
the clock does not depend on the arm.

---

**THE CORRECTION THAT PRODUCED THIS TABLE. 2026-09-03.**

An earlier run applied **v2's floor to every arm**. That was wrong twice:

- **v1 has its own measured floor and it is LARGER than v2's** (1.74/2.14 against
  0.97/1.39). Two cells change status: **v1 REBAL=10 moves from `outside` to
  `INSIDE` on both universes** (−1.50 and −1.66).
- **v3 and v4 have no measured floor at all.** Labelling their cells `outside`
  with v2's number is **borrowing a number from a different arm, not measuring
  anything**. All twelve v3/v4 non-control labels change to **UNKNOWN**.

**WHAT SURVIVES A MEASURED FLOOR: three cells, and all three are WORSE.**

| cell | n100 | mid | |
|---|---|---|---|
| v1 REBAL=5 | −7.27 | −6.25 | worse on both |
| v1 REBAL=40 | −4.73 | −3.98 | worse on both |
| v2 REBAL=5 | −7.99 | −1.84 | worse on both |

**ZERO cells with a measured floor beat their own control on both universes.**

**Six cells are NOT ESTABLISHED** — every one v3 or v4, including the three that
the earlier labelling called favourable: **v3 R=40 (+2.10 / +10.08), v4 R=10
(+1.09 / +3.94), v4 R=40 (+1.39 / +8.32)**. Whether any of these is an effect or
noise **is not established by this grid**.

---

**THE ONLY ARM WITH A TRUSTWORTHY VERDICT IS v2.** It is the shipping arm and the
only one whose own measured floor was applied to a decision here. v1 has a
measured floor but does not ship; v3 and v4 have none.

**v2's VERDICT: NO CADENCE BEATS REBAL=20 ON BOTH UNIVERSES.**

    REBAL=5    n100 -7.99 outside   mid -1.84 outside    worse on both
    REBAL=10   n100 -3.14 outside   mid +0.34 INSIDE     no verdict on mid
    REBAL=40   n100 -3.52 outside   mid +3.01 outside    OPPOSITE SIGNS

---

**PREDICTIONS Q1–Q8, JUDGED.**

1. **Q1** all eight controls reproduce — **CORRECT**, seven quantities each.
2. **Q2** rebalance counts 367/184/92/46, identical across arms — **CORRECT**.
3. **Q3** always-invested arms trade fewer than breadth arms at every cadence,
   both universes — **CORRECT, 16 of 16 comparisons.**
4. **Q4** REBAL=5 worse than control on all four n100 arms — **WRONG.** Three of
   four held; **v3 is +2.34, better.** The direction claim fails independently of
   any floor labelling.
5. **Q5** on mid, REBAL=40 beats control on more than one arm — **CORRECT**, on
   three (v2 +3.01, v3 +10.08, v4 +8.32). So the mid REBAL=40 effect is not
   specific to the breadth arm, which was the alternative named in the spec.
6. **Q6** the universes disagree on the REBAL=40 sign on at least two of four arms
   — **WRONG.** Only **one** does: v2 (−3.52 / +3.01). v1, v3 and v4 all agree.
   Signs do not depend on floors.
7. **Q7** no cell beats its own control by more than the floor on both universes —
   **JUDGED WRONG IN THE FIRST PASS, THEN WITHDRAWN UNDER THE PER-ARM FLOOR
   CORRECTION. Both the original judgement and its retraction are recorded here
   rather than the retraction alone.**
   **WHY IT WAS WITHDRAWN:** all three counterexamples were v3/v4 cells whose
   "outside" label came from a floor borrowed from v2, and **"beats by more than
   the floor" is undefined on an arm with no measured floor.** Q7 now reads: holds
   on every arm where a floor exists (v1, v2); untestable on v3 and v4.
8. **Q8** the arm ranking at REBAL=20 is not preserved at every cadence —
   **CORRECT, but on one universe only.** On n100 the control is the odd one out:
   v1 > v3 at REBAL=20, and v3 > v1 at 5, 10 and 40. **On mid the ranking is
   perfectly stable** — v3 > v1 > v4 > v2 at all four cadences.

**Score: five correct (Q1, Q2, Q3, Q5, Q8), two wrong (Q4, Q6), one withdrawn
(Q7).**

---

**CAPACITY IS NOT MEASURED HERE AND BEARS ON EVERY FAVOURABLE CELL.** Fills are
synthetic against a `QUOTE_DEPTH` of 10,000,000 shares at a flat 15 bps slippage
regardless of order size. No L2 data exists anywhere in this project, no market
impact, no queue position. **mid already has a measured liquidity problem — one
order reached 1,614% of that symbol's prior 20-day median volume**, and every
UNKNOWN cell draws the bulk of its apparent edge from mid. **A cadence that trades
differently is not shown to be executable differently, in either direction.**

**v3 AND v4 DO NOT SHIP AND NOTHING HERE REOPENS THAT.** Pro-vol was measured
under `V34_SPEC.txt` and is not supported: on n100 it lowered CAGR by 2.92 **and**
Sharpe by 0.46 against v2, and the universes disagree on the sign. A cadence
observation on an arm already rejected on its own measurement is not a route to
promoting it. **No floor measurement for v3 or v4 is proposed** — they do not ship
and entry 29's cost was 130 minutes per measurement.

**TRIAL COUNT, NOT UNDERCOUNTED.** Entry 30 charged 4 looks for the v2 sweep,
taking the floor 28 → 32. This grid adds v1, v3 and v4 at four cadences each =
**12 new looks**. v2's four cells are re-run identically and are not charged
twice. **NEW FLOOR: 44.** No result here is corrected for that denominator.

**WHAT THIS DOES NOT ESTABLISH.** No optimal cadence for any arm — HORIZON is
pinned at 20 rows. No joint cadence-and-horizon result — nothing was refitted.
Nothing about Sharpe, drawdown or volatility differences, none of which has a
floor. Nothing about capacity. Nothing about whether any ranking survives
redrawing the seeds: one ten-seed panel was used, and entry 29 established that
redrawing them moves v1 and v2 by sd 0.97 to 2.14 CAGR points on their own.

**Artefacts.** `diagnostics/rebal_cadence_sweep.txt`. Script:
`results/rebal_cadence_sweep.py`, which carries the per-arm floors as a table with
`None` meaning "never measured", refuses to render a verdict where none exists,
and reads every control value from `v34_comparison.csv`. Wall clock **4 sec**, 32
backtests, no refit. Spec: `experiments/REBAL_CADENCE_SPEC.txt` PART 8.

**AMENDMENT, 2026-09-03. THE GRID WAS EXTENDED TO REBAL=60, AND THE SWEEP NOW
WRITES MACHINE-READABLE OUTPUTS. The tables above are not amended — they are the
four-cadence grid as measured, and this block carries the fifth column.**

**REBAL=60 gives 31 rebalances** over 1,836 trading days (i = 0, 60, … 1800;
1800 < 1835), against 46 / 92 / 184 / 367 at the other cadences. **All 8 controls
at REBAL=20 reproduced again**, unchanged.

| universe | arm | CAGR% | dCAGR | floor | Sharpe | MaxDD% | AnnVol% | trades | TC Rs | TC/eq% | FinalEquity |
|---|---|---|---|---|---|---|---|---|---|---|---|
| n100 | v1 | 28.13 | −6.88 | outside | 1.39 | −31.13 | 19.46 | 305 | 1,27,914 | 2.04 | 62,68,952 |
| n100 | **v2** | 19.51 | −6.27 | outside | 1.48 | −15.60 | 12.78 | 362 | 69,127 | 1.85 | 37,43,262 |
| n100 | v3 | 29.28 | +0.19 | **UNKNOWN** | 1.22 | −39.65 | 23.73 | 300 | 1,36,762 | 2.04 | 66,98,450 |
| n100 | v4 | 18.64 | −4.22 | **UNKNOWN** | 1.23 | −25.68 | 15.02 | 358 | 63,400 | 1.79 | 35,45,471 |
| mid | v1 | 42.88 | −3.04 | outside | 1.73 | −37.76 | 22.48 | 318 | 3,06,949 | 2.18 | 1,40,51,702 |
| mid | **v2** | 32.89 | +3.18 | outside | 2.02 | −23.70 | 14.84 | 371 | 1,19,726 | 1.46 | 82,12,692 |
| mid | v3 | 45.58 | −3.96 | **UNKNOWN** | 1.70 | −41.72 | 24.14 | 294 | 3,14,918 | 1.95 | 1,61,43,310 |
| mid | v4 | 34.71 | +2.40 | **UNKNOWN** | 1.88 | −26.98 | 16.93 | 371 | 1,29,361 | 1.42 | 90,84,553 |

**Cross-universe at REBAL=60:** v1 **worse on both** (−6.88 / −3.04, a measured
difference). **v2 disagrees in sign** (−6.27 / +3.18) — no verdict. v3 and v4
**UNKNOWN**, no floor.

**v2's VERDICT IS UNCHANGED BY THE FIFTH COLUMN: no cadence beats REBAL=20 on
both universes.** REBAL=5 worse on both; 10 inside the floor on mid; **40 and 60
both opposite signs**.

**ONE OBSERVATION THAT IS NOT A FINDING.** n100 v2 at REBAL=60 has the shallowest
MaxDD in its entire row — **−15.60 against −19.96** at the control. **MaxDD has no
measured floor on any arm** and entry 28 could not distinguish it from a
random-selection null, so this is precisely the comparison the rule forbids. It is
recorded so a later reader does not find it unremarked, not because it means
anything.

**TRIAL COUNT: +4 new looks** (4 arms × 1 cadence, matching the convention entries
30 and 31 use — universes are not multiplied). **FLOOR 44 → 48.**

**THE SWEEP NOW WRITES MACHINE-READABLE OUTPUTS, so a later reader need not re-run
it to get at the numbers, the curves or the per-day detail:**

| file | size | contents |
|---|---|---|
| `diagnostics/rebal_cadence_sweep.txt` | 16,288 B | the text diagnostic |
| `diagnostics/rebal_cadence_cells.csv` | 4,099 B | **40 rows × 17 columns**, one row per cell: universe, arm, rebal, n_rebalances, CAGR, dCAGR, floor verdict, seed floor, Sharpe, MaxDD, AnnVol, trades, TC_Rs, TC as % of final equity, final equity, deployed%, ships |
| `diagnostics/rebal_cadence_equity.csv` | 1,346,406 B | **1,836 × 40** equity curves, date-indexed, one column per cell (`{universe}_{arm}_r{rebal}`) |
| `diagnostics/rebal_cadence_audit/` | **61 MB, 6 files** | per-day streams, each with `cell`/`universe`/`arm`/`rebal` columns: `holdings.csv` 633,895 rows, `ranking.csv` 158,901, `summary.csv` 73,440, `trades.csv` 41,862, `decisions.csv` 5,760, `skipped.csv` 4,657 |

`seed_floor_CAGR` is **empty for every v3 and v4 row** rather than carrying a
borrowed number, so sorting on it shows at a glance which cells have no floor.
Three internal cross-checks hold: `summary.csv` = 40 × 1,836 rows exactly;
`decisions.csv` = 5,760 = the summed rebalance counts; `trades.csv` = 41,862,
matching the grid's trade counts.

**THE EQUITY CURVES WERE PREVIOUSLY COMPUTED AND DISCARDED.** `run()` read
`eq` for its metrics and let it go out of scope, so no chart could ever be drawn
without re-running the whole sweep. They are now retained.

**ADDING THESE OUTPUTS MOVED NO NUMBER.** Proved rather than assumed: the
diagnostic was byte-identical across the run that added the two CSVs, and the
audit streams were then verified against the same baseline — see **entry 32**,
which used this grid as the A/B for the engine's `audit=None` claim.



---

### 32. The audit flag does not change what it observes — **A DOCSTRING CLAIM, VERIFIED**

*Pre-registration: `experiments/REBAL_CADENCE_SPEC.txt` PART 9, written 2026-09-03
**before the audit path was wired in and before any comparison was run**. The
baseline files, their byte counts, three numbered predictions R1–R3 and a
non-negotiable stop condition were all fixed there first.*

Not an experiment and not a trial — **a verification of an assumption the code has
been making about itself.** It has no accept rule because nothing was being
accepted.

**WHAT WAS CLAIMED.** `results/test_exposure.py:72` — the docstring of
`backtest_exposure`, the shipping engine:

> "audit=None reproduces the original code path exactly: no overhead, and the
> official numbers are unchanged."

**THAT WAS A COMMENT, AND IT HAD BEEN ONE FOR AS LONG AS THE PARAMETER HAD
EXISTED.** Nothing had ever tested it. `HANDOFF_SUMMARY.txt` section 9 lesson 10
says in terms: verify whether a diagnostic flag changes the numbers it observes,
rather than assuming it. This is that check, and it was possible at no extra cost
because entry 31's cadence grid had just produced a clean `audit=None` baseline.

**THE A/B DESIGN.** The same 40 cells run twice, once with `audit=None` and once
with a six-key audit dict, everything else bit for bit identical:

    4 arms (v1, v2, v3, v4)  x  5 cadences (5, 10, 20, 40, 60)  x  2 universes
      = 40 cells, 1,836 trading days each = 73,440 equity values per side

    baseline, fixed before the change and hashed:
      diagnostics/rebal_cadence_sweep.txt     16,287 bytes
      diagnostics/rebal_cadence_equity.csv  1,346,406 bytes   1,836 x 40
      diagnostics/rebal_cadence_cells.csv       4,099 bytes   40 x 17

**THE RESULT. NOTHING MOVED.**

| prediction | outcome |
|---|---|
| **R1** grid byte-identical | **CORRECT.** The only differing line in 214 is `wall clock 5 sec` → `wall clock 10 sec`, the run's own elapsed time and not a measured quantity. Excluding it, `diff` returns identical — all 40 cells, all 8 controls, every metric. |
| **R2** all 40 curves match to full precision | **CORRECT.** `cmp` on the 1,346,406-byte equity file: **byte-identical**. Numerically **max absolute difference 0.0 across all 73,440 values**; 0 of 40 columns show any non-zero difference; `DataFrame.equals` True. |
| **R3** trade counts and TC unchanged in all 40 cells | **CORRECT.** The cells CSV is byte-identical; 0 cells differ on trades, TC_Rs, CAGR, Sharpe, MaxDD or final_equity. |

Not "small" — **zero**. The stop condition in PART 9 did not fire.

**WHY IT MATTERED BEYOND THIS SWEEP.** Several published artefacts were produced
**with** audit enabled — the v34 and v2FINAL runs pass audit dicts — and others
without. Those figures were being compared across a flag whose inertness was
assumed and never measured. **It is no longer assumed.**

**THE CEILING, AND IT IS NARROW.** This holds **on these 40 cells, on these two
score panels, in this window**. It does **not** prove the flag is inert in
general: not on other arms, other windows, other panels, or the retired
universes. And it says **nothing about the four other inline reimplementations of
the backtest** — `engine_core.backtest`, `nt_attribution.py`'s book,
`make_stats_both.py`'s book and `make_cash_series.py:42-70` — none of which was
touched. See `KNOWN_ISSUES.md`, "There are FIVE reimplementations of the backtest,
not two". What was converted is one comment into one measurement with a stated
scope.

**Cost.** Wall clock 5 sec → 10 sec with audit on. The audit streams are 61 MB
across six files; see entry 31 for the layout.

**Artefacts.** `diagnostics/rebal_cadence_sweep.txt`,
`diagnostics/rebal_cadence_cells.csv`, `diagnostics/rebal_cadence_equity.csv` and
`diagnostics/rebal_cadence_audit/`. Script: `results/rebal_cadence_sweep.py`.
Spec: `experiments/REBAL_CADENCE_SPEC.txt` PART 9.

---

### 33. Portfolio drawdown exit — **SPECIFIED IN ADVANCE, IMPLEMENTED CORRECTLY, AND THE SPECIFICATION WAS WRONG**

*Pre-registration: `experiments/DRAWDOWN_EXIT_SPEC.txt`, written and frozen
2026-09-03 **before the measurement script existed** — the rule, the five
thresholds, the two underived re-entry constants, three blocking correctness
gates, a governing constraint, and nine numbered predictions D1–D9.*

**NO ACCEPT RULE. NOTHING COULD BE PROMOTED BY THIS MEASUREMENT**, by design: the
rule's primary objective is drawdown reduction, and **there is no measured noise
floor for MaxDD on any arm**. Only the rule's *cost* was ever inferable.

---

## THE CENTRAL FINDING: THE RE-ENTRY CONDITION IS UNSATISFIABLE BY CONSTRUCTION

**The rule exits once and never returns. Across every threshold that fired, on
both universes, there are ZERO re-entries and the book is flat for 1,536–1,540 of
1,836 days — 84% of the window.**

The mechanism, and it follows directly from two choices in the spec:

- **§5.2 the peak is never reset** on exit or re-entry — it stays the all-time
  high of portfolio value;
- **§5.4 cash earns nothing while flat** — `CASH_YIELD = 0.0`.

So once flat, portfolio value is frozen at the exit proceeds while the peak stays
where it was. **Drawdown measured against that peak therefore cannot recover**,
the re-entry condition `dd > −(0.5 × THRESHOLD)` can never become true, and the
latch never clears. The rule does not "exit and wait". **It terminates the
strategy.**

**THIS IS A DESIGN ERROR IN SECTION 5 OF THE SPEC. IT IS THE SPEC AUTHOR'S, NOT
THE IMPLEMENTATION'S.** Every gate passed; the code did exactly what was written.
Both offending choices were argued for in advance and both are individually
defensible — §5.2 prevents the rule re-arming at a lower bar after each firing,
§5.4 refuses to credit a cash yield the engine does not pay. **Their interaction
was not considered, and the spec was frozen before anyone noticed.** Writing the
rule down in advance did not prevent the error; it made the error legible
afterwards, which is the whole argument for pre-registration and is the only
thing that went right here.

---

## RESULTS

**NIFTY 100** — measured CAGR floor 0.97

| thresh | CAGR% | dCAGR | floor | Sharpe | MaxDD% | AnnVol% | trades | TC Rs | FinalEquity | exits | re-ent | days flat | %flat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 25.78 | +0.00 | control | 1.87 | −19.96 | 12.96 | 978 | 2,45,816 | 54,65,550 | 0 | 0 | 0 | 0.0 |
| 0.10 | 0.78 | **−25.00** | outside | 0.20 | −14.97 | 4.44 | 158 | 12,979 | 10,59,335 | 1 | **0** | 1,540 | **83.9** |
| 0.125 | 1.16 | **−24.62** | outside | 0.29 | −12.58 | 4.40 | 158 | 13,010 | 10,89,119 | 1 | **0** | 1,538 | 83.8 |
| **0.15** | 0.12 | **−25.66** | outside | 0.05 | −19.04 | 4.70 | 158 | 12,926 | 10,08,692 | 1 | **0** | 1,536 | 83.7 |
| 0.20 | 25.78 | +0.00 | INSIDE | 1.87 | −19.96 | 12.96 | 978 | 2,45,816 | 54,65,550 | **0** | 0 | 0 | 0.0 |
| 0.25 | 25.78 | +0.00 | INSIDE | 1.87 | −19.96 | 12.96 | 978 | 2,45,816 | 54,65,550 | **0** | 0 | 0 | 0.0 |

**MIDCAP150** — measured CAGR floor 1.39

| thresh | CAGR% | dCAGR | floor | Sharpe | MaxDD% | AnnVol% | trades | TC Rs | FinalEquity | exits | re-ent | days flat | %flat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 29.71 | +0.00 | control | 2.03 | −18.93 | 13.51 | 963 | 2,29,916 | 68,64,240 | 0 | 0 | 0 | 0.0 |
| 0.10 | −1.54 | **−31.25** | outside | −0.32 | −17.90 | 4.64 | 186 | 13,295 | 8,91,731 | 1 | **0** | 1,540 | 83.9 |
| 0.125 | −0.91 | **−30.62** | outside | −0.21 | −13.94 | 4.09 | 186 | 13,340 | 9,34,871 | 1 | **0** | 1,538 | 83.8 |
| **0.15** | −1.79 | **−31.50** | outside | −0.40 | −19.48 | 4.40 | 186 | 13,279 | 8,74,610 | 1 | **0** | 1,536 | 83.7 |
| 0.20 | 29.71 | +0.00 | INSIDE | 2.03 | −18.93 | 13.51 | 963 | 2,29,916 | 68,64,240 | **0** | 0 | 0 | 0.0 |
| 0.25 | 29.71 | +0.00 | INSIDE | 2.03 | −18.93 | 13.51 | 963 | 2,29,916 | 68,64,240 | **0** | 0 | 0 | 0.0 |

**THE ONLY INFERENTIAL CLAIM THE DESIGN SUPPORTS: the rule costs return, by
twenty to thirty times the measured floor.** Final equity falls from 54.7 lakh to
10.1 lakh on n100 and from 68.6 lakh to 8.7 lakh on mid.

## EVERY FIRING, IN FULL — AND IT IS ONE WEEK

| threshold | n100 trigger → fill | dd | mid trigger → fill | dd |
|---|---|---|---|---|
| 0.10 | 2020-03-12 → 2020-03-13 | −11.34% | 2020-03-12 → 2020-03-13 | −12.49% |
| 0.125 | 2020-03-16 → 2020-03-17 | −12.52% | 2020-03-16 → 2020-03-17 | −13.94% |
| 0.15 | 2020-03-18 → 2020-03-19 | −17.15% | 2020-03-18 → 2020-03-19 | −17.17% |
| 0.20 | **NEVER FIRED** in 1,836 days | — | **NEVER FIRED** | — |
| 0.25 | **NEVER FIRED** in 1,836 days | — | **NEVER FIRED** | — |

Trigger years pooled: **2020 only**. The measurement's own clustering check
answers YES. The spec's governing constraint — written at its head before any
number existed — held exactly: **five thresholds on one crash is one observation,
and these thresholds were tested once, in a single week of March 2020.**

---

## PREDICTIONS D1–D9, JUDGED

1. **D1** control reproduces — **CORRECT**, seven quantities, both universes.
2. **D2** execution timing passes — **CORRECT**. 9 of 9 exit fills on n100 and 10
   of 10 on mid at the fill day's OPEN, **zero at any close**, trigger→fill offset
   exactly 1 session in every case. Four candidate prices tested, not one.
3. **D3** daily reconciliation holds — **CORRECT**, 1,836 of 1,836 days at every
   threshold. See the gate note below; the first version of this gate was wrong.
4. **D4** every threshold lowers CAGR on both universes, and 0.10/0.125 exceed the
   floor — **CORRECT WHERE THE RULE FIRED, VACUOUS WHERE IT DID NOT.** At 0.10,
   0.125 and 0.15 the fall is 24.6–31.5 points, far beyond the floor. At 0.20 and
   0.25 CAGR is *identical* to the control because the rule never fired — which
   satisfies "does not improve" but not "lowers". Recorded as partially correct
   rather than correct.
5. **D5** MaxDD improves at every threshold — **UNTESTABLE BY DESIGN, AND NOT
   CLAIMED.** MaxDD is shallower at 0.125 on both universes and *deeper* at 0.15
   on mid, but there is no floor and entry 28 could not distinguish MaxDD from a
   random null. No verdict is drawn. Recorded as predicted, not as judged.
6. **D6** firing is a single cluster in March 2020 at 0.15/0.20/0.25, with extra
   firings at 0.10 and 0.125 — **HALF CORRECT, AND THE HALF THAT FAILED IS THE
   MORE INTERESTING.** The cluster claim is **CORRECT and stronger than
   predicted**: every trigger at every threshold on both universes falls in one
   week. The extra-firings claim is **WRONG**: 0.10 and 0.125 fired once each, not
   more, because after the single exit the rule was permanently flat and could
   never fire again. **The zero-re-entry defect is why this half failed.**
7. **D7** days flat under 10% at 0.15 and above — **WRONG, AND BY THE LARGEST
   MARGIN OF ANY PREDICTION HERE.** Measured **83.7%**, not under 10%. Predicted
   on the assumption that re-entry would occur roughly a month after the exit; it
   never occurred at all.
8. **D8** the universes agree in sign at every threshold — **CORRECT**, and it was
   flagged in the spec as the prediction most likely to be wrong because it
   predicts against this project's base rate of universe disagreement. Both fell
   together in March 2020 and the rule acted on both identically.
9. **D9** no threshold improves CAGR by more than the floor on both universes —
   **CORRECT**. None improves it at all.

**Score: four correct (D1, D2, D3, D8), two wrong (D6-part, D7), one partially
correct (D4), one untestable by design (D5), one whose cluster half was correct
and firing half wrong (D6).** The prediction flagged in advance as most likely to
be wrong (D8) was correct; the two that failed (D7, and D6's count) both failed
for the *same* unforeseen reason, which is the design error above.

---

## THE G3 EPISODE — A GATE THAT FAILED FOR ITS OWN REASONS

**The first version of gate G3 FAILED ON THE UNMODIFIED CONTROL** — 47 of 1,836
days on n100, with no drawdown rule active at all. That is a claim of a
reconciliation defect in the **shipping engine**, and it was investigated before
being reported rather than after.

**The cause was the gate, not the engine.** `audit["summary"]` stores
`round(mtm,2)`, `round(cash,2)` and `round(pv,2)` as **three independent
roundings**, so `round(mtm,2) + round(cash,2)` can differ from `round(mtm+cash,2)`
by one paisa **by construction**. Measured on the shipping arm with the rule off:
**maximum difference 0.0100000007, and ZERO days above 0.011.** The gate tested
`> 0.01`, which float representation pushes just over.

**WHY THE REWRITTEN GATE IS NOT A LOOSENED TOLERANCE.** Loosening would mean
raising a threshold until a failure disappears. Instead:

- the budget is **derived from the storage format** — two roundings at half a
  paisa each — and is stated in the function's docstring with the measured
  numbers, so a later reader can check the derivation rather than trust it;
- a **second** check was added that the original lacked: the holdings stream
  summed per day against `mtm`, with a budget that scales as `0.005 × names_held`
  because each row is independently rounded;
- a **third, rounding-free** check was added and is the one that actually
  reconciles: the stored total against the **unrounded** equity curve, which must
  agree to half a paisa. Measured max **0.005**.

The rewritten gate is **stricter in substance** than the original — three checks
where there was one, including a rounding-free one — while being correct about
what the audit's own storage format permits. **No defect in `backtest_exposure`
was found, and none is alleged.**

---

## WHAT IS NOT ESTABLISHED

- **NOTHING ABOUT DRAWDOWN.** No measured seed noise floor exists for MaxDD on any
  arm, and the one measurement on that axis is negative — entry 28's shuffle test
  could not distinguish MaxDD from a random-selection null (p 0.37/0.36 on n100,
  0.20/0.44 on mid). **The rule's entire purpose is unmeasurable with what this
  project has.** The MaxDD column above is reported because it was asked for.
- **NOTHING ABOUT 0.20 AND 0.25. THEY NEVER FIRED, SO THEY ARE UNTESTED RATHER
  THAN SAFE.** Their identity with the control is an absence of evidence, not
  evidence of harmlessness. A wider threshold has not been shown to be a better
  choice; it has been shown not to have been exercised.
- **NOTHING BEYOND MARCH 2020.** Every trigger across every threshold and both
  universes falls in the same week. The next drawdown will not have 2020's shape
  or speed — a slow grinding decline of the same depth would trigger at a
  different time, sell into different liquidity, and follow a different path.
  **The window does not contain that case.**
- **NOTHING ABOUT CAPACITY, AND THIS RULE IS THE WORST CASE FOR THE FILL MODEL.**
  An exit sells the entire book in one session, into a falling market, against a
  synthetic `QUOTE_DEPTH` of 10,000,000 shares at flat 15 bps regardless of order
  size. `diagnostics/liquidity_participation.txt` recorded a midcap150 SELL at
  **1,614.52%** of its symbol's prior-20-day median volume. *Superseded 2026-09-20:
  that fill was AIIL 2021-06-07, and AIIL's price file now begins 2024-04-23, so no
  current `daily_trades` holds it. The largest participation now measured on
  midcap150 is **34.46%** (TATAINVEST, 2019-12-26, n=1,006 fills). The point the
  sentence is making survives at the smaller number: an exit still sells the whole
  book in one session against a synthetic depth of 10,000,000 shares.* Nothing here
  can say what a full liquidation on 13 March 2020 would actually have filled at.
- **NOTHING ABOUT A POSITION-LEVEL STOP**, which is a different rule the spec
  explicitly does not address.
- **NOTHING ABOUT SEED STABILITY.** One ten-seed panel; entry 29 established that
  redrawing the seeds moves v2 by sd 0.97–1.39 on its own.

**THE RULE AS SPECIFIED IS NOT A CANDIDATE FOR ANYTHING.** Not because it lost on
a metric, but because the specification contained an error that makes its
behaviour degenerate. A corrected rule — one whose re-entry condition can actually
be satisfied — is a **new pre-registration with its own trial charge**, and
nothing in this entry constitutes evidence about it.

**TRIAL COUNT: 5 thresholds + the control = 6 new looks. FLOOR 48 → 54.** The
control is charged by the convention adopted 2026-09-03: one rule rather than a
per-experiment judgement about what counts.

**Artefacts.** `diagnostics/drawdown_exit.txt`, `drawdown_exit_cells.csv` (12
rows), `drawdown_exit_events.csv` (6 rows), `drawdown_exit_equity.csv`
(1,836 × 12). Script: `results/drawdown_exit_measure.py`, which derives the rule
by patching the **shipping function's own source** at four asserted anchors rather
than reimplementing the loop — a sixth inline backtest was explicitly avoided —
and aborts if any anchor fails to match exactly once. Spec:
`experiments/DRAWDOWN_EXIT_SPEC.txt`.

---

### 34. Drawdown exit, revision 2 — **TIME-ONLY RE-ENTRY OSCILLATES FOR SIX YEARS, AND IS WORSE THAN SITTING OUT THE ENTIRE BULL MARKET**

*Pre-registration: `experiments/DRAWDOWN_EXIT_SPEC.txt` section 12, written
2026-09-03 **after** entry 33's result and **before** the script was modified.
The grid, the three waits, the trial charge and eight predictions E1–E8 were all
fixed there first. **Whipsaw was predicted, not discovered** — the spec named it
the headline prediction and the obvious failure mode of a time-only re-entry.*

**NO ACCEPT RULE. NOTHING PROMOTED.** MaxDD still has no measured noise floor on
any arm, so the rule's primary objective remains unjudgeable. Only CAGR cost is
inferable.

**WHAT CHANGED FROM REVISION 1.** Re-entry became TIME-ONLY: the first scheduled
rebalance at least `RE_ENTRY_WAIT` trading days after the exit fill, **with no
drawdown condition**. Everything else identical, including — and this is the
point — **the peak is still never reset**.

**GATES.** G1 control reproduces the published v2 row on seven quantities, both
universes. G2 **617 / 313 / 209 exit fills** per wait setting, every one at the
fill day's open, **zero at any close**, trigger→fill offset exactly 1 throughout.
G3 1,836 of 1,836 days on the control and all 15 cells. All pass.

---

## THE CENTRAL FINDING: THE RULE OSCILLATES FOR SIX YEARS

**77 exits and 76 re-entries at wait=5. The oscillation begins in March 2020 and
never stops.**

Because the peak is never reset and cash earns nothing, the book **re-enters while
still in breach of its own threshold**, and the trigger fires again at that same
day's close. n100, threshold 0.15, wait 5 — the first four cycles:

    EXIT     2020-03-18 -> fill 03-19   dd -17.15%   pv 10,32,253
    REENTRY  2020-04-22                 dd -19.04%   FLAT 20 days
    EXIT     2020-04-23 -> fill 04-24   dd -19.61%   pv 10,01,560
    REENTRY  2020-05-21                 dd -20.20%   FLAT 18 days
    EXIT     2020-05-22 -> fill 05-26   dd -20.73%   pv  9,87,663
    REENTRY  2020-06-19                 dd -20.44%   FLAT 18 days
    EXIT     2020-06-22 -> fill 06-23   dd -21.16%   pv  9,82,297

**THE DRAWDOWN DEEPENS MONOTONICALLY, AND TRANSACTION COSTS ARE THE ONLY CAUSE.**
−17.15% at the first trigger, −21.16% four cycles later; portfolio value falls
from 10.32 lakh to 9.82 lakh on friction alone. Each cycle buys the whole book and
sells it one day later. **The rule digs its own hole deeper every cycle and the
peak it is measured against never moves, so it can never climb out.**

**Trigger years pooled, n100: 2020: 60, 2021: 69, 2022: 66, 2023: 66, 2024: 75,
2025: 66, 2026: 24.** The clustering check answers NO — but **this is not the rule
finding new drawdowns.** It is the same March 2020 breach, never resolved,
grinding through to the end of the window.

---

## REVISION 2 IS WORSE THAN REVISION 1 ON n100

| n100, threshold 0.15 | CAGR% | final equity |
|---|---|---|
| control | 25.78 | 54,65,550 |
| **revision 1** (drawdown re-entry, never re-entered, 84% flat) | **0.12** | 10,08,692 |
| **revision 2**, wait 5 | **−3.24** | 7,83,520 |
| revision 2, wait 20 | −1.14 | 9,18,773 |
| revision 2, wait 40 | −0.44 | 9,67,685 |

**SITTING OUT THE ENTIRE BULL MARKET BEAT WHIPSAWING THROUGH IT.** Revision 1
missed the whole 2020–2026 recovery in cash and still finished ahead of revision 2
at every wait on n100. This was predicted as E6 and predicted the *other way*; its
failure is a genuine finding rather than an accounting artefact. On mid revision 2
is the less bad of the two, so the two universes disagree about which failure mode
is worse.

---

## RESULTS

**NIFTY 100** — measured CAGR floor 0.97

| thresh | wait | CAGR% | dCAGR | floor | Sharpe | MaxDD% | trades | TC Rs | FinalEquity | fires | exits | reent | %flat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | – | 25.78 | +0.00 | control | 1.87 | −19.96 | 978 | 2,45,816 | 54,65,550 | 0 | 0 | 0 | 0.0 |
| 0.10 | 5 | −2.59 | −28.37 | outside | −0.51 | −33.89 | 1,374 | 1,10,258 | 8,23,613 | 153 | 77 | 76 | 75.6 |
| 0.10 | 20 | −0.49 | −26.27 | outside | −0.08 | −22.63 | 766 | 64,832 | 9,64,502 | 77 | 39 | 38 | 79.7 |
| 0.10 | 40 | 0.23 | −25.55 | outside | 0.07 | −18.38 | 558 | 48,422 | 10,16,854 | 51 | 26 | 25 | 81.2 |
| 0.125 | 5 | −2.21 | −27.99 | outside | −0.43 | −31.98 | 1,374 | 1,12,793 | 8,47,421 | 153 | 77 | 76 | 75.5 |
| 0.125 | 20 | −0.11 | −25.89 | outside | −0.00 | −20.46 | 766 | 66,178 | 9,91,630 | 77 | 39 | 38 | 79.6 |
| 0.125 | 40 | 0.60 | −25.18 | outside | 0.16 | −16.08 | 558 | 49,358 | 10,45,542 | 51 | 26 | 25 | 81.0 |
| 0.15 | 5 | −3.24 | −29.02 | outside | −0.61 | −37.11 | 1,374 | 1,05,965 | 7,83,520 | 153 | 77 | 76 | 75.4 |
| 0.15 | 20 | −1.14 | −26.92 | outside | −0.21 | −26.30 | 766 | 62,476 | 9,18,773 | 77 | 39 | 38 | 79.5 |
| 0.15 | 40 | −0.44 | −26.22 | outside | −0.07 | −22.33 | 558 | 46,823 | 9,67,685 | 51 | 26 | 25 | 80.9 |
| 0.20 / 0.25 | all | 25.78 | +0.00 | INSIDE | 1.87 | −19.96 | 978 | 2,45,816 | 54,65,550 | **0** | 0 | 0 | 0.0 |

**MIDCAP150** — measured CAGR floor 1.39. dCAGR **−31.40 to −33.29** at every
firing cell; fires 153 / 77 / 51 at waits 5 / 20 / 40; 0.20 and 0.25 identical to
the control at every wait.

---

## PREDICTIONS E1–E8, JUDGED

1. **E1** the three gates pass — **CORRECT**.
2. **E2** whipsaw — **CORRECT ON THE MECHANISM, WRONG ON EVERY MAGNITUDE.**
   (a) predicted "high single digits to low tens" firings; measured **77 exits** —
   wrong by an order of magnitude. (b) trade counts above the control at tighter
   thresholds — **CORRECT**, 1,374 against 978. (c) predicted the oscillation
   persists "a matter of months"; it persists **six years** — **WRONG, and this is
   the failure that mattered**: the prediction did not see that TC-driven decay
   makes recovery to the frozen peak impossible. (d) days flat below revision 1's
   84% — **CORRECT**, 75.4%.
3. **E3** firing counts ordered wait 5 ≥ 20 ≥ 40 — **CORRECT**, 153 / 77 / 51,
   strictly ordered, no inversion.
4. **E4** 0.20 and 0.25 never fire and are identical to the control — **CORRECT**,
   all six cells on both universes. It was stated in advance as a logical
   consequence rather than a guess, and it held as one.
5. **E5** every firing threshold lowers CAGR beyond the measured floor —
   **CORRECT**, by 25.2–29.0 points on n100 and 31.4–33.3 on mid.
6. **E6** revision 2 beats revision 1 on CAGR at every firing cell — **WRONG ON
   n100, CORRECT ON mid.** The spec flagged this as the second most likely to be
   wrong and said its failure would be a genuine finding. **It is: whipsaw costs
   more than sitting out a six-year bull market.**
7. **E7** every trigger still within 2020 — **WRONG.** Triggers span 2020–2026 —
   not because the rule found new drawdowns, but because it never resolved the
   first one. The prediction was wrong for a reason that makes the result worse,
   not better.
8. **E8** the universes agree in sign at every firing cell — **CORRECT**.

**Score: five correct (E1, E3, E4, E5, E8), two wrong (E6, E7), one correct in
mechanism and wrong in every magnitude (E2).**

---

## THE ROOT CAUSE IS COMMON TO BOTH REVISIONS

**REVISIONS 1 AND 2 HAVE ONE CAUSE AND TWO SYMPTOMS: THE PEAK IS NEVER RESET.**
After the March 2020 breach the rule is permanently in breach and can never clear.

- **Revision 1** could not re-enter, because drawdown could not recover while the
  book sat in cash at 0% against a frozen peak. Symptom: one exit, zero
  re-entries, 84% flat.
- **Revision 2** re-entered on a timer while still in breach, and exited again the
  next close. Symptom: 77 exits, six years of oscillation.

Neither is a defect in the implementation; both follow from spec section 5.2,
which fixed the peak as all-time and never reset. **That choice was argued for in
advance — it prevents the rule re-arming at a lower bar after each firing — and it
is the direct cause of both failures.**

---

## WHAT IS NOT ESTABLISHED

- **NOTHING ABOUT DRAWDOWN.** No measured floor for MaxDD on any arm; entry 28
  could not distinguish it from a random-selection null. The MaxDD column is
  reported because it was asked for.
- **NOTHING ABOUT 0.20 AND 0.25.** They never fired at any wait, so they are
  **untested rather than safe**. Their identity with the control is an absence of
  evidence.
- **NOTHING ABOUT CAPACITY, AND WHIPSAW MAKES IT WORSE.** 77 full liquidations and
  76 full re-entries, against a synthetic `QUOTE_DEPTH` of 10,000,000 shares at
  flat 15 bps regardless of size, when
  `diagnostics/liquidity_participation.txt` recorded a midcap150 SELL at **1,614.52%** of
  its symbol's prior-20-day median volume. *Superseded 2026-09-20: that fill is not
  in any current `daily_trades` (AIIL's data now starts 2024-04-23); the largest on
  midcap150 today is 34.46%, n=1,006 fills.*
- **NOTHING BEYOND THE ONE 2020 EPISODE.** The 2021–2026 triggers are the
  unresolved 2020 breach, not new events. **Repeated firings within one episode
  are not repeated tests of the rule.**

**TRIAL COUNT: 15 cells + the control = 16 new looks. FLOOR 54 → 70.**

**Artefacts.** `diagnostics/drawdown_exit.txt`, `drawdown_exit_cells.csv` (32
rows), `drawdown_exit_events.csv` (95 KB, every exit and re-entry with dates and
days flat), `drawdown_exit_equity.csv` (1,836 × 32). Script:
`results/drawdown_exit_measure.py`, which patches the shipping function's own
source at four asserted anchors rather than reimplementing the loop.

---

### 35. Drawdown exit, revision 3 — **NON-DEGENERATE AT LAST, AND STILL UNJUDGEABLE**

*Pre-registration: `experiments/DRAWDOWN_EXIT_SPEC.txt` section 13, written
2026-09-03 **after** entry 34's result and **before** the script was modified.
The change, the trial charge, what the change GIVES UP, and eight predictions
F1–F8 were all fixed there first.*

**NO ACCEPT RULE. NOTHING PROMOTED.**

**THE CHANGE, AND IT IS ONE LINE OF BEHAVIOUR.** On re-entry the peak is reset to
that day's portfolio value; the high-water mark starts fresh and drawdown is
measured from the new peak. Everything else is unchanged.

**GATES.** G1 the control reproduces the published v2 row on seven quantities,
both universes. G2 every exit fills at the next session's open, zero at any close,
trigger→fill offset exactly 1. G3 1,836 of 1,836 days on the control and all 15
cells. All pass.

---

## THE PEAK RESET FIXES THE COMMON ROOT CAUSE OF ENTRIES 33 AND 34

Entries 33 and 34 were **one cause with two symptoms**: the peak was never reset,
so after the March 2020 breach the rule was permanently in breach and could never
clear.

| revision | re-entry rule | symptom | n100 @ 0.15 CAGR |
|---|---|---|---|
| 1 (entry 33) | drawdown must recover | **could never re-enter** — 1 exit, 0 re-entries, 84% flat | 0.12 |
| 2 (entry 34) | time-only | **re-entered while still in breach**, exited next close — 77 exits, six years of oscillation | −3.24 (wait 5) |
| **3 (this entry)** | time-only **+ peak reset** | **non-degenerate** — 1 exit, 20 days flat | **25.11** |

**77 exits became 4. Days flat went from 75–84% to 1.1–9.8%. CAGR went from 25–33
points below the control to within two points of it.** The degeneracy is gone, and
it went for the reason predicted: after a reset the book re-enters at a fresh peak
and is no longer in breach, so it cannot exit again until a genuinely new decline.

---

## RESULTS

**NIFTY 100** — measured CAGR floor 0.97

| thresh | wait | CAGR% | dCAGR | floor | Sharpe | MaxDD% | trades | TC Rs | FinalEquity | fires | exits | %flat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | – | 25.78 | +0.00 | control | 1.87 | −19.96 | 978 | 2,45,816 | 54,65,550 | 0 | 0 | 0.0 |
| 0.10 | 5 | 24.16 | −1.62 | outside | 1.81 | −19.13 | 963 | 2,33,794 | 49,65,012 | 8 | 4 | 4.4 |
| 0.10 | 20 | 23.02 | −2.76 | outside | 1.74 | −19.13 | 951 | 2,20,065 | 46,39,007 | 8 | 4 | 5.4 |
| 0.10 | 40 | 23.68 | −2.10 | outside | 1.86 | −15.71 | 907 | 2,19,042 | 48,25,820 | 8 | 4 | 9.8 |
| 0.125 | 5 | 26.44 | **+0.66** | **INSIDE** | 1.93 | −16.85 | 980 | 2,55,192 | 56,82,475 | 2 | 1 | 1.2 |
| 0.125 | 20 | 26.44 | **+0.66** | **INSIDE** | 1.93 | −16.85 | 980 | 2,55,192 | 56,82,475 | 2 | 1 | 1.2 |
| 0.125 | 40 | 26.60 | **+0.82** | **INSIDE** | 1.97 | −13.34 | 972 | 2,56,445 | 57,37,362 | 2 | 1 | 2.3 |
| 0.15 | 5 | 25.11 | −0.67 | INSIDE | 1.83 | −22.99 | 980 | 2,37,444 | 52,55,965 | 2 | 1 | 1.1 |
| 0.15 | 20 | 25.11 | −0.67 | INSIDE | 1.83 | −22.99 | 980 | 2,37,444 | 52,55,965 | 2 | 1 | 1.1 |
| 0.15 | 40 | 25.28 | −0.50 | INSIDE | 1.87 | −19.74 | 972 | 2,38,695 | 53,08,021 | 2 | 1 | 2.2 |
| 0.20 / 0.25 | all | 25.78 | +0.00 | INSIDE | 1.87 | −19.96 | 978 | 2,45,816 | 54,65,550 | **0** | 0 | 0.0 |

**MIDCAP150** — measured CAGR floor 1.39

| thresh | wait | CAGR% | dCAGR | floor | Sharpe | MaxDD% | trades | FinalEquity | exits | %flat |
|---|---|---|---|---|---|---|---|---|---|---|
| control | – | 29.71 | +0.00 | control | 2.03 | −18.93 | 963 | 68,64,240 | 0 | 0.0 |
| 0.10 | 5 | 29.26 | −0.45 | INSIDE | 2.01 | −18.81 | 969 | 66,89,215 | 3 | 2.7 |
| 0.10 | 20 | 29.25 | −0.46 | INSIDE | 2.02 | −18.81 | 943 | 66,87,355 | 3 | 4.9 |
| 0.10 | 40 | 27.10 | −2.61 | outside | 1.92 | −18.34 | 913 | 59,04,365 | 3 | 8.2 |
| 0.125 | 5 | 30.23 | **+0.52** | **INSIDE** | 2.07 | −14.88 | 953 | 70,71,436 | 1 | 1.2 |
| 0.125 | 20 | 30.23 | **+0.52** | **INSIDE** | 2.07 | −14.88 | 953 | 70,71,436 | 1 | 1.2 |
| 0.125 | 40 | 29.88 | **+0.17** | **INSIDE** | 2.07 | −14.39 | 941 | 69,34,141 | 1 | 2.3 |
| 0.15 | 5 | 29.04 | −0.67 | INSIDE | 1.99 | −20.37 | 953 | 66,07,033 | 1 | 1.1 |
| 0.15 | 20 | 29.04 | −0.67 | INSIDE | 1.99 | −20.37 | 953 | 66,07,033 | 1 | 1.1 |
| 0.15 | 40 | 28.73 | −0.98 | INSIDE | 1.99 | −19.91 | 941 | 64,91,437 | 1 | 2.2 |
| 0.20 / 0.25 | all | 29.71 | +0.00 | INSIDE | 2.03 | −18.93 | 963 | 68,64,240 | **0** | 0.0 |

### THE FOUR POSITIVE CELLS ARE INSIDE THE FLOOR AND ARE THEREFORE NOT FINDINGS

n100 0.125 at **+0.66 / +0.66 / +0.82** and mid 0.125 at **+0.52 / +0.52 / +0.17**
are the only cells where the rule beats its control. **Every one is INSIDE the
measured CAGR floor** — 0.97 on n100, 1.39 on mid — which means it **cannot be
distinguished from ordinary re-fit variation in either direction**. Reading +0.66
as an improvement is exactly what the floor rule forbids, and it is the mistake
entry 28's retracted purge deltas were made of. **THEY ARE NOT EVIDENCE THAT 0.125
IS A GOOD THRESHOLD.** They are cells where the rule's cost was too small to
measure.

---

## PREDICTIONS F1–F8, JUDGED

1. **F1** the three gates pass — **CORRECT**.
2. **F2** the oscillation stops, firings in the low single digits — **CORRECT**.
   4 exits at 0.10, 1 at 0.125 and 0.15, against revision 2's 77.
3. **F3** days flat collapses to under 15% — **CORRECT**, 1.1% to 9.8%.
4. **F4** better than revisions 1 and 2 at every firing cell, **but still short of
   the control by more than the floor** — **FIRST HALF CORRECT, SECOND HALF
   WRONG.** Ten of the thirty firing cells land INSIDE the floor and four are
   positive. The spec flagged this as the prediction most likely to be wrong and
   said a cell inside the floor was entirely possible; it was.
5. **F5** 0.20 and 0.25 never fire and stay identical to the control — **CORRECT**,
   all twelve cells. Stated in advance as a logical consequence, and it held as one.
6. **F6** no cell shows two or more exits inside a single decline — **CORRECT.**
   The 4-exit cell fires in **2020, 2022, 2025 and 2026**, years apart, each fully
   recovered between. See the caveat below: this is a statement about the window.
7. **F7** reported MaxDD worsens at some cells relative to revision 1 —
   **CORRECT AS REPORTED, NOT JUDGED.** n100 0.15 shows −22.99 against the
   control's −19.96. MaxDD has no measured floor, so no claim is drawn.
8. **F8** the universes agree in sign at every firing cell — **WRONG.** At 0.10
   wait 5, n100 is −1.62 (outside) while mid is −0.45 (INSIDE): the two universes
   disagree on whether there is a measurable effect at all.

**Score: six correct (F1, F2, F3, F5, F6, F7-as-reported), one half-wrong (F4),
one wrong (F8).**

---

## THE STATE, PLAINLY

**THE RULE IS NOW NON-DEGENERATE AND COSTS LITTLE. WHETHER IT HELPS IS STILL
UNMEASURABLE.**

- Non-degenerate: 4 exits, not 77; 1.1–9.8% flat, not 84%; CAGR within about two
  points of the control across every firing cell, and inside the floor in ten of
  thirty.
- Unmeasurable: **MaxDD has NO measured seed noise floor on any arm**, and entry
  28's shuffle test could not distinguish MaxDD from a random-selection null
  (p 0.37/0.36 on n100, 0.20/0.44 on mid). **Drawdown reduction is the rule's
  entire purpose.** The shallower drawdowns at 0.125 — −16.85 against −19.96 on
  n100, −14.88 against −18.93 on mid — are **not evidence**, by the same rule that
  disqualifies the four positive CAGR cells.

**THREE REVISIONS ESTABLISHED WHAT THE RULE DOES, NOT WHETHER IT WORKS.** What was
learned is mechanical: how it fails when the peak is frozen (two distinct ways),
and that it stops failing when the peak is reset. Nothing across entries 33, 34 and
35 bears on the question the rule exists to answer.

**WHAT WOULD CHANGE THAT: a measured seed noise floor for MaxDD on v2**, by entry
29's method, of order 130 minutes per universe. **IT IS NOT PROPOSED HERE.** It is
named so a later reader knows precisely which missing measurement stands between
this rule and a verdict.

---

## THE PEAK-RESET GIVE-UP IS LIVE AND UNTESTED

The spec stated before the run what the reset costs: **the rule no longer measures
drawdown from the strategy's all-time high.** A book that falls THRESHOLD,
re-enters, and falls THRESHOLD again has lost far more than THRESHOLD from its true
peak while the rule sees two ordinary breaches. At 15%, two chained resets reach a
**27.75%** true drawdown; three reach **38.6%**. **The rule now limits the loss per
episode, not the loss overall.**

**F6 HELD — AND IT HELD FOR A REASON THAT DOES NOT GENERALISE.** No cell chained,
because this window's one severe drawdown is **fast-down-fast-up**: a near-vertical
March 2020 fall followed by a rapid recovery, with the other firings years apart
and fully recovered between. **A SLOW GRINDING DECLINE IS THE CASE THAT WOULD
CHAIN — repeated THRESHOLD-sized falls with insufficient recovery between them,
each resetting the peak lower — AND THAT CASE IS NOT IN THE DATA.** F6 is a
statement about 2019–2026, not about the rule, and the spec said so in advance.

**It also breaks the coherence argued for in spec section 2.** That section chose
the all-time peak partly so the trigger and `engine_core.py:370`'s reported MaxDD
would mean the same thing. After revision 3 they do not: reported MaxDD is still
all-time, the trigger is not. No comparison between them is drawn here, and a later
reader must not draw one.

---

## WHAT IS NOT ESTABLISHED

- **Nothing about drawdown**, on any cell, in any revision. No floor exists.
- **Nothing about 0.20 and 0.25**, which never fired at any wait in any revision.
  They are **untested rather than safe**; their identity with the control is an
  absence of evidence.
- **Nothing about the chained-reset case**, per above.
- **Nothing about capacity.** Fills are synthetic against a `QUOTE_DEPTH` of
  10,000,000 shares at flat 15 bps regardless of size, and an exit still sells the
  entire book in one session; `diagnostics/liquidity_participation.txt` recorded a
  midcap150 SELL at **1,614.52%** of its symbol's prior-20-day median volume. *Superseded
  2026-09-20: not in any current `daily_trades` (AIIL's data now starts
  2024-04-23); largest on midcap150 today is 34.46%, n=1,006 fills.*
- **Nothing about seed stability.** One ten-seed panel. Entry 29 established that
  redrawing the seeds moves v2 by sd 0.97–1.39 on its own — the same magnitude as
  every INSIDE cell above.
- **The governing constraint applies in full**: the window contains ONE severe
  drawdown, and the next will not have 2020's shape or speed.

**TRIAL COUNT: 15 cells + the control = 16 new looks. FLOOR 70 → 86.**

**Artefacts.** `diagnostics/drawdown_exit.txt`, `drawdown_exit_cells.csv` (32
rows), `drawdown_exit_events.csv` (every exit and re-entry with dates and days
flat), `drawdown_exit_equity.csv` (1,836 × 32). Script:
`results/drawdown_exit_measure.py`. Spec: `experiments/DRAWDOWN_EXIT_SPEC.txt`
section 13.

---

### 36. The held-out pre-registration, spent — **sd_in IS 16.84x mu_in, SO 12 SESSIONS RESOLVE ALMOST NOTHING; THE PASS IS A CONSEQUENCE OF THAT**

*Pre-registration: `experiments/HELDOUT_PREREG.txt`, written 2026-09-12, BEFORE
any data after 2026-05-29 was examined. The frozen 11-parameter configuration,
the excess statistic, the consistency interval and the pass/fail rule were all
fixed there first. An addendum dated 2026-09-16 records three findings about what
running it would measure and explicitly changes no line of sections 1–6.*

**THE HEADLINE IS THE DISPERSION.** Pooled over 3,670 in-sample sessions
(n100 1,835 + mid 1,835):

```
mu_in  : +3.0093 bps/session   (+7.58% annualised)
sd_in  : 50.6780 bps/session
```

**`sd_in / mu_in` = 16.84.** The per-session edge is one seventeenth of the noise
it sits in. Everything below follows from that ratio, and no verdict computed on
12 sessions can escape it.

**THE SAMPLE IS A FIFTH OF THE DESIGN, AND THE INTERVAL WIDENED TO MATCH.**
Section 3 reasoned about power on "roughly 65 pooled sessions". The window that
actually exists is 6 sessions per universe, 12 pooled — 2026-06-01 to 2026-06-08
on both. Because `se = sd_in / sqrt(n)` is computed from whatever `n` turns out to
be, the interval was not held fixed against the shortfall:

```
n (held-out, pooled)      : 12
se = sd_in / sqrt(n)      : 14.6295 bps/session
interval                  : [ -26.2497 , +32.2682 ] bps/session
```

**That is 2.33x wider than the arithmetic section 3 assumed.** The run's own
output states the consequence rather than leaving it to a reader:

> A WIDER INTERVAL IS EASIER TO FALL INSIDE. Nothing in the procedure
> checks n against the number it was designed around; se is computed from
> whatever n turns out to be. THE VERDICT BELOW IS NOT THE TEST THIS FILE
> DESIGNED. It is that test's procedure run on a fifth of its sessions,
> because a fifth is all the data that will ever exist.

**The accept rule**, quoted verbatim from section 3 of the pre-registration:

> PASS   the held-out pooled mean excess is POSITIVE and falls inside that
>        interval.
> FAIL   it is negative, or it falls outside the interval in EITHER direction.
>
> A RESULT THAT IS TOO GOOD IS ALSO A FAIL, and that is deliberate. An
> out-of-sample edge several times the in-sample one is evidence that something
> changed -- a data refresh, a corporate action, a look-ahead -- not evidence of
> skill. The interval is two-sided on magnitude and one-sided on sign.

**THE RESULT.**

| quantity | value |
|---|---|
| held-out pooled mean excess | **+0.3515 bps/session** (+0.89% annualised, readability only) |
| positive? | True |
| inside [−26.2497, +32.2682]? | True |
| **verdict** | **PASS on 12 pooled sessions** |

**The verdict is PASS, and it is recorded as PASS.** It is not softened here. But
the interval it fell inside spans 58.5 bps and the statistic is 0.35 bps — the
observation sits at 1.2% of the interval's half-width from the centre. An interval
that wide would have admitted almost any small positive number, which is what
"the PASS is a consequence of the width" means concretely. The pre-registration's
own section 4 says it plainly:

> A PASS HERE IS NOT CONFIRMATION AND MUST NOT BE QUOTED AS VALIDATION.

**WHAT IT DOES ESTABLISH.** That the in-sample picture did not fall apart
immediately outside its window. Nothing more. It does not correct the 26 prior
contaminated trials — section 5 is explicit that this is "one clean observation
appended to a record of 26 contaminated ones. That is an improvement in kind, not
a repair of what came before."

**THE WINDOW IS SPENT AND CANNOT BE RE-RUN.** `heldout_prereg_run.py:125-131`
refuses a second run on the `[HELDOUT-PREREG-RESULT-BLOCK]` sentinel now present
in the pre-registration. There is no larger `n` available: the price data is fixed
at 2026-06-08.

**NUMBERING — TWO INDEPENDENT SCHEMES, DO NOT RECONCILE THEM.**
`HELDOUT_PREREG.txt:249-250` directs that the verdict be recorded "in this file
and in experiments/EXPERIMENTS.md, **as trial 27**". That is the running
*multiple-testing trial count*, not an entry number. This is **entry 36**.
**Entry 27 is a different thing entirely** — the TOP_N=8 revalidation. A reader
who tries to make trial 27 and entry 27 agree will be reconciling two counters
that were never the same counter.

**Artefacts.** `diagnostics/heldout_prereg_result.txt` (the full output),
`experiments/HELDOUT_PREREG.txt` (pre-registration plus the appended result
block). Script: `heldout_prereg_run.py`. Run at HEAD
`4558ddab0692fca7cf10752c950a26d9d2ea44cb`, working tree clean, against
pre-registered commit `806a7fbba9a41a954e0ac75bc5a8064ecbabd414` (an ancestor),
all 11 frozen parameters matching section 1 and the real charge model active.
Committed as `0b021ae`. The reproduction gate ran before any held-out figure was
read: max relative difference 2.219e-16 (n100) and 2.172e-16 (mid) against the
shipped `v2FINAL_equity.csv`, tolerance 1e-12.

---

## Which purge the shipped panels were built with, measured. 2026-09-02.

Not an experiment and not a trial — a **measurement on the artefacts**, run
because two statements in this file contradicted each other about a live code
path and the question could not be settled by reading either one.

**THE QUESTION, AND WHY IT NEEDED A MEASUREMENT.** `engine_core.score_monthly`
takes `purge_mode`, defaulting to `"trading"`. That is what the code does *today*.
It is a different question from what the score panels **on disk** were built with,
and the second question is the one that decides whether the headline in
`HANDOFF_SUMMARY.txt` section 2 sits on the corrected purge or the legacy one. A
score panel records dates, symbols and scores. **It does not record the purge that
produced it**, so the question cannot be answered by reading the file.

**WHAT IT IS, NAMED PLAINLY: A DIFFERENTIAL TEST THAT CHOSE BETWEEN TWO
CANDIDATES. IT IS NOT AN IDENTITY REPRODUCTION.** For selected months the
production 10-seed ensemble was refit **twice** from the same on-disk raw panel —
once under `purge_mode="calendar"`, once under `"trading"` — and each candidate
compared against the shipped panel's own scores for that month. The question asked
was only ever *which candidate is closer*. Neither reproduces the shipped panel,
and no claim is made that either does.

**WHY A DIFFERENTIAL TEST IS SOUND DESPITE THAT.** `build_scores_*.py` score the
**in-memory** panel and write `raw_panel_*_cache.csv` as a by-product; the two
differ by one unit in the last place. The probe can only read the CSV, so **both
candidates carry that same offset**. It is common mode and cancels in a comparison
of which is closer. It does not cancel in an absolute comparison, which is exactly
why no absolute claim is made.

**Statistics**, all against the shipped scores: max absolute difference (a
single-cell statistic, reported but weak), **mean absolute difference** (primary),
and **per-date rank disagreement** — the quantity the strategy actually consumes.

**TWO DESIGN FEATURES WITHOUT WHICH THE RESULT WOULD MEAN NOTHING.**

1. **CONTROL MONTHS.** In some months the two cuts select an *identical* training
   set. There the two branches must return byte-identical output — if they did
   not, the probe would have a preference of its own. Controls are **classified by
   the run**, by comparing the two training masks, not chosen by hand. **4 of 4
   controls returned identical output on both universes.** They also measure the
   **error floor**: mean abs 2.052e-03 to 2.318e-03 on n100, 2.077e-03 on mid.
2. **SIZE-INCREASING MONTHS.** The calendar cut is not always the later one. In
   **5 of the 16** divergent months the trading cut falls later and trains on
   **more** rows. These exclude the confound that a smaller training set is simply
   always closer. **Trading won all 5.**

**THE RESULT — 16 OF 16.**

| statistic | trading closer |
|---|---|
| mean absolute difference (primary) | **16 of 16** |
| per-date rank disagreement | **16 of 16** |
| max absolute difference (weak) | 14 of 16 |
| mean abs, size-increasing months only | **5 of 5** |

One-sided sign test on the primary statistic, under the null that the shipped
panel is equally close to both candidates: **p = 1.526e-05**. On the divergent
months the trading candidate lands **at or below** the control error floor while
the calendar candidate lands **above** it.

**DETERMINATION. The shipped n100 and mid score panels were built with
`purge_mode="trading"`.** Two independent lines agree with it and neither was
relied on for the verdict: `engine_core.py` was modified at 14:28:25 on 2026-09-02
and both live panels were written at 15:06:19, against a measured re-score cost of
36 min 07 sec; and `shuffle_summary.csv` (2026-09-01 23:47) carries n100 v2 at
25.49 while `v34_comparison.csv` (2026-09-02 15:16) carries 25.78, so the panel
demonstrably changed between those timestamps.

**THE RESIDUAL, AND WHAT THIS DID NOT ESTABLISH.** The best-fitting candidate
still leaves a non-zero mean absolute difference and a four-figure rank
disagreement in **every** month, controls included. **This measurement did NOT
establish that the shipped panels reproduce from the artefacts on disk — they do
not.** The cause is the one-unit-in-the-last-place gap between the in-memory panel
and its CSV, recorded in `KNOWN_ISSUES.md` under *"The headline is not reproducible
from the artefacts on disk to better than about a point"*, and the control months
measure it directly. It also establishes **nothing about whether the trading purge
is correct** — that is `diagnostics/leakage_check2_purge.txt`. It asks only which
one ran.

**Artefacts.** `diagnostics/purge_mode_probe.txt`. Script:
`results/purge_mode_probe.py`, which computes its own verdict from the measured
rows rather than carrying one. 20 months probed across both universes, 40 refits
of the production 10 seeds, wall clock **5.1 min**.

---

## Decoupling the trading calendar by a coverage threshold — REFUTED BEFORE IMPLEMENTATION. 2026-09-03.

*Pre-registration: `experiments/CALENDAR_DECOUPLE_SPEC.txt`, written 2026-09-03
before any code. The design, the threshold, the predictions and the four
verification gates were all fixed there first.*

Not an experiment and not a trial — a **design refuted by measurement**, recorded
because the refutation is the useful artefact. **No code was written and no
production path changed.**

**THE DESIGN TESTED.** `make_trading_calendar.py` derived the NSE calendar from
the **retired 58 universe's** raw files, and `engine_core._load_calendar()` raises
without that artefact for every universe. **The script was deleted on 2026-09-11,
commit `2fe48ff`, with the retired universe itself** -- after this entry was written, and eight
days after the measurement below. The calendar is now frozen tracked source data;
see `RETIRED_UNIVERSES.md` section 6. Nothing in the measurement changes. The candidate: build the calendar from
the **selected universe's own files**, and drop any date carried by fewer than a
**single global coverage threshold** of the files active that year — `COVERAGE_MIN
= 0.50`, named in the spec as an underived constant.

**WHY IT LOOKED SOUND.** Over 2019-01-01 to 2026-05-29, filtering at 50%
reproduces the tracked 58-derived calendar **exactly** — identical sets, 1,836
dates, zero either way, in **both** universes. Coverage there is bimodal with an
empty 35.5-point band (low group 15.4–47.3%, kept group 82.8–100%).

**IT IS REFUTED, AND IT IS NOT ADJUSTABLE.** The in-window result covers 1,836 of
~6,574 dates. Extended to the full range the files cover:

| universe | filtered | 58 calendar | filtered-only | calendar-only |
|---|---|---|---|---|
| n100 | 6,572 | 6,574 | **0** | **2** |
| mid | 6,552 | 6,574 | **0** | **22** |

Every window year reproduces exactly; **all failures are pre-2019**. The
difference is one-directional throughout — the filter never invents a date, it
only drops dates the calendar has.

**THE EMPTY-INTERVAL PROOF, WHICH SETTLES ALL THRESHOLDS AT ONCE.** A threshold T
reproduces the calendar if and only if `max(coverage of excluded dates) < T ≤
min(coverage of included dates)`. Measured:

| universe | calendar HAS | calendar LACKS | required interval | result |
|---|---|---|---|---|
| n100 | 6,574 at 13.85%–100% | 237 at 1.27%–24.24% | `24.24% < T ≤ 13.85%` | **EMPTY — overlap 10.40 pt** |
| mid | 6,573 at 4.35%–100% | 237 at 1.16%–47.30% | `47.30% < T ≤ 4.35%` | **EMPTY — overlap 42.95 pt** |

**No value of `COVERAGE_MIN` works, in either universe.** Changing it changes
*which* dates are wrong; it cannot make none of them wrong. This is a property of
the data, not of the chosen value.

**THE FOUR BINDING CASES** — calendar dates too thinly covered for any threshold
that also excludes the 237:

| date | day | n100 coverage | mid coverage |
|---|---|---|---|
| **2017-12-02** | Sat | above 50% | **5/115 = 4.35%** |
| **2003-03-22** | Sat | **9/65 = 13.85%** | **3/61 = 4.92%** |
| **2017-04-04** | Tue | **29/87 = 33.33%** | **43/115 = 37.39%** |
| **2003-01-01 .. 2003-01-24** | 18 consecutive sessions | above 50% | **29/61 = 47.54%**, 2.46 pt under the line |

A fifth difference is not a filtering decision at all: **2000-01-03** is absent
from mid's union entirely, because mid's data starts 2000-01-04.

**THE EMPTY MIDDLE IS A PROPERTY OF THE RECENT YEARS, NOT OF THE DATA.** Per-year
band edges narrow sharply before 2019: mid 2003 gap **19.7 points** (low tops at
49.2%), mid 2016 kept side at **exactly 50.0%**, n100 2017 gap 31.0. For 2019–2026
the kept side never falls below 82.8%. The spec's insensitivity argument — every
threshold in (0.473, 0.828] partitions identically — is true **only** for the
range it was measured on.

**THE PREDICTIONS, JUDGED HONESTLY.**

1. **P1 and P2 were not predictions.** They said the n100- and mid-derived
   calendars would be identical to the tracked one **over 2019-01-01 to
   2026-05-29** — a range where the identity had *already been measured* two days
   earlier. They were correct, and worthless. **Scoping a prediction to data you
   have already measured is not a prediction**, and the spec now says so in place.
   The extension to the full range is what mattered, and it is **FALSE**.
2. **P3, P4 and P5 were never tested.** They covered published figures, panel
   byte-identity and the retired artefacts. **No code ran**, so no panel, no arm
   and no retired artefact was produced or compared. They are neither confirmed
   nor refuted and must not be reported as passing.

**WHY THE FAILURE WOULD HAVE MATTERED.** The 24 missing dates are all pre-2019, so
they are **training rows, not scored rows** — but `build_panel` filters the whole
panel and training reaches back to 2001. Entry 28 measured a 0.01% change in
training rows moving n100 v2 CAGR by 0.54 points. A calendar 22 dates short is a
larger perturbation in the same place. **The change would have moved published
numbers in a project whose entire justification for it was that nothing moves.**
Gates 2 and 3 of the spec were designed to catch this; they were never needed,
because the measurement caught it first, for four seconds of compute.

**WHAT THIS DOES NOT ESTABLISH.**

- **NOT that the 58-derived calendar is right about those 24 dates.** No external
  NSE source was consulted, here or anywhere in this project. Three of the binding
  dates are Saturdays. Whether 2003-03-22, 2017-12-02 and 2017-04-04 were genuine
  sessions is **untested**. The measurement establishes only that a coverage
  filter cannot *reproduce* the existing calendar, not that the existing calendar
  is correct.
- **NOT that no decoupling is possible.** It refutes **one** design — a single
  global coverage threshold. Other designs were not measured and nothing here
  rules them out.
- **Nothing about panels, scores or published figures.** No code that touches them
  was run.

**Artefacts.** `diagnostics/calendar_coverage_probe.txt`. Script:
`results/calendar_coverage_probe.py`, which computes its verdict from the measured
rows rather than carrying one, and hashes the tracked calendar before and after to
prove it was not written. Wall clock **4 sec**. Spec, with the refutation appended
as PART 8 and a BLOCKED banner at its head:
`experiments/CALENDAR_DECOUPLE_SPEC.txt`.

**The coupling stays open** — `KNOWN_ISSUES.md`, *"STEP 0 couples the live
universes to the retired 58 universe"* — now with one candidate design measured
and refuted before implementation.

---

## Entries 27, 28, 29 and C were run on pre-purge-fix scores. 2026-09-02.

The purge correction of 2026-09-02 rebuilt the n100 and mid score panels. **Every
validation and measurement run before that date used the superseded scores.** This
is recorded once, as a state of the record, rather than as a list of tasks.

**AFFECTED, AND WHAT EACH USED**

| entry | what it established | superseded diagnostics |
|---|---|---|
| **27** TOP_N revalidation | TOP_N=8 NOT CONTRADICTED, 6 of 6 criteria | `topn_n100.txt`, `topn_mid.txt`, `topn_verdict.txt` |
| **28** Shuffle test | 0 of 100 permutations beat the real arm, p = 0.0099 | `shuffle_n100.txt`, `shuffle_mid.txt`, `shuffle_verdict.txt` |
| **29** Seed noise floor | sd 0.97–2.14 CAGR at K=10; sigma(K) exponent −0.15 to −0.25 | `seed_noise.txt` |
| **C** Breadth live validation | 3 of 3 gated criteria PASS on both universes | `breadth_live_n100.txt`, `breadth_live_mid.txt` |

Also superseded: `v34_report.txt`, `validate_sizing_{n100,mid}.txt`,
`n100_jackknife.txt`, `nt_verify_n100.txt`, `nt_reports_verify.txt`, and the
`purge_fix_measure.txt` / `leakage_check2_purge.txt` pair, which describe the
defect before it was repaired.

NOT affected: `leakage_check1_causality.txt` and `leakage_check3_normalisation.txt`
test the FEATURE stage, which the purge does not touch; `checkA_close_bad_values.txt`
reads raw CSVs; `membership/STATUS.md` is independent of scoring. Retired-universe
artefacts are correctly unchanged — the 58 and 74 are pinned to the legacy purge.

**WHAT THIS CHANGES, AND WHAT IT DOES NOT.**

**The conclusions stand.** The purge effect on the shipping arm was **+0.29 on
n100 and −0.51 on mid**, both inside the seed noise floor measured in entry 29
(sd 0.97 and 1.39). A perturbation smaller than the measurement's own resolution
cannot reverse a verdict that did not turn on a fraction of a CAGR point:

- entry 27 held on Sharpe margins of +0.11 to +0.22;
- entry 28 had **zero** of 100 permutations beating the real arm, against effect
  sizes of +14 to +30 CAGR points;
- entry C passed 3 of 3 gated criteria;
- entry 29's finding is about the SHAPE of sigma(K), which is a property of the
  ensemble rather than of any particular score panel.

**The exact figures do not stand.** Every number in those entries describes scores
that no longer ship. A reader quoting "25.49" or "0 of 100 on the current panel"
is quoting a superseded artefact. **The entries are not amended**, because their
numbers were correct when produced and rewriting them would destroy the record;
this section is the pointer that they are historical.

**WHAT A FULL REFRESH WOULD COST**, measured where known, so the decision is a
costed one:

| work | cost | basis |
|---|---|---|
| Seed noise floor (entry 29) | **130 min** | measured 2026-09-02; 40 seeds x 126 months x 2 universes |
| Shuffle test (entry 28) | **~80 sec** | measured; 100 permutations x 4 arms x 2 universes, no refit |
| TOP_N revalidation (entry 27) | **~1 min** | measured; 12 backtests, no refit |
| Breadth live (entry C) | **not measured** | rescores 3 seed sets x 2 universes; by the ~17 min/universe/10-seed rate, of order 100 min |
| validate_sizing | **not measured** | rescores per test; same order |
| Nautilus reports / liquidity / depth | **not measured** | depth and liquidity also need the window moved off 1,842 days |
| **score rebuild itself** | **36 min 07 sec** | already done for the live universes |

The two cheap ones — the shuffle test and the TOP_N revalidation — are minutes and
need no refitting, because both consume an existing score panel. The expensive
ones are those that refit: the seed noise floor, breadth live, and
validate_sizing.

**NOTHING WAS RE-RUN TO PRODUCE THIS SECTION.** It is an inventory of what the
rebuild superseded, not a refresh.

---

## Leakage-side verification, as of 2026-09-02 — what has artefacts, and what does not

A summary of work already recorded elsewhere in this file and in `diagnostics/`.
**It makes no new claim.** Every line names the artefact behind it, and anything
without one is listed as open.

### Tested and closed

| failure mode | result | artefact |
|---|---|---|
| Feature causality | 17 of 17 features bit-exact at day *t* when every row after *t* is corrupted — two independent corruptions, both universes | `diagnostics/leakage_check1_causality.txt` |
| Normalisation scope | no whole-panel statistic fitted on anything the model sees; every feature operation trailing or same-day; the only forward-looking operations are the label and its artefact mask | `diagnostics/leakage_check3_normalisation.txt` |
| Walk-forward construction | no training row dated on or after the scored month, all 126 months, both universes | `diagnostics/leakage_check2_purge.txt` |
| Execution timing **[CORRECTED 2026-09-02 — see the second correction block at the end of this section]** | 976 of 977 and 971 of 973 fills at the fill day's open; **0 at any close**; all 1,950 one session after a recorded decision date | `diagnostics/checkB_execution_timing.txt` |
| Random-selection null | 0 of 100 score permutations beat the real arm on either gated arm on either universe | `diagnostics/shuffle_verdict.txt`, entry 28 |
| Bad values in the traded price column | 0 of 2,690 and 0 of 3,503 `close` values violate their own session's high/low; the out-of-bounds values are all in `adj_close`, which the engine does not use | `diagnostics/checkA_close_bad_values.txt` |

### Tested, failed, measured — not repaired

| failure mode | result | artefact |
|---|---|---|
| Label purging **[CORRECTED 2026-09-02 — see the correction block below this table]** | The purge is 32 **calendar** days against a label spanning 20 **trading** rows. The label reached into the scored month in **7 of 126 months** and touched its first day in **21 more**, identically on both universes. A trading-row purge with a 2-row embargo fixes it by construction (min gap 2 on all 126). **The fix is not applied**: `engine_core.py` still runs the calendar purge, and the correction exists only in a measurement script. The return impact could not be distinguished from re-fit noise. | `diagnostics/leakage_check2_purge.txt`, `diagnostics/purge_fix_measure.txt`, entry 29 |

**CORRECTION, 2026-09-02. THE LABEL-PURGING ROW ABOVE IS FALSE ON TWO COUNTS, AND
ITS ORIGINAL TEXT IS LEFT IN PLACE RATHER THAN REWRITTEN.**

The row states *"The fix is not applied: `engine_core.py` still runs the calendar
purge, and the correction exists only in a measurement script."* Both halves are
wrong, and the row was already wrong on the day it was written — the same day, and
in the same file, as the section *"The purge correction was applied, and the
headline moved"*, which is the accurate one. The two contradicted each other about
a live code path.

**What is true, established from code and artefacts rather than from either
document:**

1. **`engine_core.py` does not run the calendar purge by default.**
   `results/engine_core.py:413` reads
   `def score_monthly(raw, seeds, purge=PURGE, purge_mode="trading")`, and the
   branch at `results/engine_core.py:460` takes the trading-row cut
   `cut = _cal[i_first - HORIZON - PURGE_EMBARGO]` unless `"calendar"` is asked
   for by name. `results/build_scores_n100.py:50` and
   `results/build_scores_mid.py:47` both call `score_monthly(raw, SEEDS)` and so
   take the default. Only the four retired-universe sites pin `"calendar"`:
   `build_scores.py:31`, `build_scores74.py:36`, `engine_core.py:575`,
   `validate_breadth.py:66`.
2. **The correction does not exist "only in a measurement script."** It is in
   `score_monthly` itself, and it is what the shipping panels were built with —
   measured, not inferred, in *"Which purge the shipped panels were built with,
   measured"* above: 16 of 16 divergent months favour the trading candidate on
   both primary statistics, p = 1.526e-05, with controls confirming the probe has
   no branch preference.

**WHAT THIS CHANGES FOR THE HEADLINE: NOTHING.** `HANDOFF_SUMMARY.txt` section 2
and `v34_comparison.csv` were already on the corrected purge. The defect was in
this row's description of the code, not in any published number. **No figure in
this file is amended by this correction** — the 7 of 126 months, the 21 more, and
the min-gap-2 result are all still correct, and the return-impact sentence is still
correct.

**The row's placement is also wrong and is left alone.** Label purging now belongs
under *Tested and closed*, not under *Tested, failed, measured — not repaired*.
Moving it would renumber and reflow a record section; that is a separate decision.
Read the row as: tested, failed, measured, **and since repaired**.

**CORRECTION, 2026-09-02. THE EXECUTION-TIMING ROW CARRIES PRE-PURGE-FIX FILL
COUNTS. ITS ORIGINAL FIGURES ARE LEFT IN PLACE RATHER THAN OVERWRITTEN.**

The row reads *"976 of 977 and 971 of 973 fills at the fill day's open; 0 at any
close; all 1,950 one session after a recorded decision date."* Those counts are
from the fill record produced **before** the purge correction rebuilt the panels.
The check was re-run against the new `fills.csv` on 2026-09-02 at 15:17 and the
counts moved, because the corrected scores change which names are bought.

Read from `diagnostics/checkB_execution_timing.txt`, not from any summary:

| | recorded in the row | measured 2026-09-02 |
|---|---|---|
| n100, fills at the fill day's open | 976 of 977 | **977 of 978** |
| mid, fills at the fill day's open | 971 of 973 | **961 of 963** |
| total fills, one session after a decision date | 1,950 | **1,941** |
| fills executing at a close rather than an open | 0 | **0**, unchanged |

The artefact states *"FILLS EXECUTING AT A CLOSE RATHER THAN AN OPEN: 0"* on both
universes, so the substantive claim of the row — the only one it was making — is
unaffected. **What is wrong is the arithmetic, not the finding.** The three
exceptions are two one-paisa rounding misses and one symbol with no panel price
under its post-rename ticker.

---

### Open, with no artefact that closes them

- **Survivorship.** Point-in-time index membership reaches 2024-03-28 against a
  2019-01-01 start — 5 years 3 months of a 7.6-year window uncovered. Downloading
  the complete non-bond NSE archive added zero days. Not quantifiable with what is
  on disk. `diagnostics/membership/STATUS.md`.
- **The multiple-comparison denominator.** 29 recorded entries, 28 run, one
  acceptance. No result in this file is corrected for it, and the permutation test
  in entry 28 does not correct for it either.
- **No out-of-sample data.** Every number comes from one panel, 2019-01-01 to
  2026-05-29, on universes backfilled from today's index membership. Nothing has
  been held out, and no result has been produced on data the configuration was not
  chosen against.
- **The reproducibility limit.** The published headline cannot be reproduced from
  the artefacts on disk to better than roughly one CAGR point. A one-bit float
  difference between the in-memory panel and its CSV moves n100 v2 by +0.66; a
  0.01% change in training rows moves it by +0.54; redrawing the ten seeds gives a
  standard deviation of 0.97 to 2.14 with a range of 4.17 to 10.26. See
  `KNOWN_ISSUES.md` and entries 28 and 29.

### What this establishes

That six specific mechanisms by which a backtest can manufacture returns were
tested against artefacts, five held, and one failed and was measured. **It does
not establish that the returns are real.** The four items above are untested by
any of this work, and the first and third of them are the ones that would matter
most. **No confidence figure is attached to the headline, and none is available
from this work.**

---

## What is closed, and what is not

### Closed

| family | closed by | why |
|---|---|---|
| **Exposure / cash management** | 8 recorded attempts (3–9, 18, 19, 20) | IR ≈ IC × √BR. Exposure timing changes neither term. Breadth's information is fully extracted and linear mapping is its optimal use. |
| **Weight caps / position-size limits** | 25 | Premise refuted — no position ever reaches 20%. Not a threshold problem. |
| **Price-and-volume features** | 17 | High and low were the last unused columns on disk. They carry no stable 20-day cross-sectional signal. |
| **Volatility estimator substitution** | 12, 13 | Rolling wins, and the reason is cross-sectional comparability, not estimation quality. |
| **Linear signal combination** | 14, 15 | Recovers less than half of LightGBM's IC. The model's non-linearity is doing real work. |
| **Training scheme (window, fading)** | 16 | Expanding + uniform already wins both questions. More data is better; fading is monotonically harmful. |
| **Concentration count adaptivity** | 11 | Trailing IC is too noisy to adapt to. Fixed beats dynamic. |

### Not closed

- **EXP19 (entry 22)** is pre-registered, its trigger has fired, and it has not
  been authorised. It is the only unexecuted pre-registered experiment.
- **EXP20 (entry 23)** is a near-miss, not a refutation: it failed one sub-period
  by 0.02 Sharpe while passing its tradeability objective emphatically. Any
  revisit needs a fresh pre-registration carrying the full trial count, and must
  not loosen Gate C to the value that would have let it through.
- **Long-short (entry 2)** was never actually answered. It was rejected on a
  broken implementation.
- **Sizing (entry 26)** has no recorded verdict, and inverse-vol — which is in
  production — has no positive evidence behind it on the corrected panel.
  This is the only open question in the record that affects a live component.
- **The two levers the record points at were never tested**, because both are
  blocked on the same thing:
  - **New data** — fundamentals. Nothing in the record touches them.
  - **Higher breadth** — a wider, less efficient universe. Blocked on
    point-in-time index membership, which is reconstructed only from 2024-03-28
    against a 2019-01-01 backtest start (see
    `diagnostics/membership/STATUS.md`).

### The v1/v2 capital blend — recorded, not an experiment

From `HANDOFF_SUMMARY.txt`: blending v1 (always invested) and v2 (breadth-scaled)
capital is **not a free lunch, it is a slider**. Every 10% of v1 added costs
roughly **+0.55 CAGR / −0.027 Sharpe / −1.6 points of drawdown**. It was not
adopted because it is a capital-allocation decision, not an engineering one.
`results/test_v1_v2_blend.py` was kept for that reason, and was **deleted on
2026-09-11** with the 58 and the 74 -- it read only their artefacts. The slider
finding above is the whole of what it established; its two mean-invested
constants (58: 0.646, 74: 0.645) are transcribed in `RETIRED_UNIVERSES.md`.

---

## Provenance of every number in this file

Nothing here is from memory. Each entry's numbers come from one of:

Everything in this section describes the state after the 2026-08-23 consolidation,
in which the experiment scripts, the per-experiment result files and the EXP18
per-draw cache were deleted and the surviving documents were gathered into
`experiments/`.

**Still on disk, in `experiments/` alongside this file:**

| source | covers |
|---|---|
| `EXP14_PREREG.txt` | entry 17 |
| `EXP17_PREREG.txt` | entry 20 |
| `EXP18_EXP19_PREREG.txt` | entries 21, 22 |
| `EXP20_PREREG.txt` | entry 23 |
| `EXP21_EXP22_PREREG.txt` | entries 24, 25 |
| `rejected_experiments_REPORT.txt` | entries 3–7, 9–16 — **restored 2026-08-22** after being deleted in error; MD5-verified against the backup |
| `ewma_vs_rolling_REPORT.txt` | entries 12, 13 — **restored 2026-08-22**; MD5-verified against the backup |
| `HANDOFF_SUMMARY.txt` §4 | entries 1, 2, 8; the v1/v2 blend |
| `sizing_test.py` | entry 26 — the accept rule, in its docstring. Restored from backup 2026-08-23, then **deleted 2026-09-11** (it imported `config74` and ran on the 58/74/mid trio). The accept rule is quoted verbatim in entry 26 above, which is now the only copy |

**Consolidated into this file and then deleted.** These were the sources for the
entries named; their content is reproduced above and the originals are gone:

| deleted source | covered |
|---|---|
| `EXP14_REPORT.txt` | entry 17 |
| `EXP17_REPORT.txt` | entry 20 |
| `diagnostics/EXP18_RESULT.txt`, `diagnostics/exp18_causality.txt` | entry 21 |
| `diagnostics/exp20_result.txt`, `diagnostics/exp20_causality.txt` | entry 23 |
| `diagnostics/exp21_final.txt`, `diagnostics/exp21_exp22.txt` | entries 24, 25 |
| `diagnostics/exp18_cache/` (37 JSON files) | entry 21's Gate D distributions, reproduced in full in that entry |

**Never had an original document, or lost one before consolidation:**

| source | covers | status |
|---|---|---|
| operator's session transcript | entries 18, 19 (EXP15, EXP16) | **originals lost before 2026-08-22**; recovered verbatim and flagged in place |
| session measurement | entry 25's 19.69% max weight | **not in any result file**; flagged in place |

**The pre-registrations are kept, in `experiments/`.** They are the evidence that
the rules were written before the results were seen, and a summary of a prereg is
not the same as the prereg. Where this file quotes an accept rule verbatim, the
original is still on disk and should be read in preference to the quotation.

**Two entries have no original document and no numbers** (1 and 8), one has a
verdict but a broken implementation behind it (2), and one has a pre-registered
rule but no verdict at all (26). They are listed anyway, because a trial that
happened and was not counted is the most dangerous kind of missing record: it
makes every subsequent multiple-testing correction too generous.

---

## v2 against its own buy & hold, on eight universes. 2026-09-18, extended 2026-09-20.

> **SUPERSEDED 2026-09-24.** Every figure in this section was produced by the
> pre-fix numerics and is kept as it was. The eight universes were rebuilt on
> 2026-09-24 with numerics that give identical bits on macOS and Linux; the
> rebuilt v2-against-buy-&-hold table is in README.md, "Results". Two signs
> changed there: midcap100 v2 now leads its basket (+2.04) and smallcap250 v2 now
> trails it (-1.98). The other figures in this file are likewise pre-fix.

**Recorded, not concluded.** Written on four universes 2026-09-18 from each
universe's `results_<tag>/metrics/v34_comparison.csv`; midcap100 added
2026-09-19; **nifty200, smallcap250 and nifty500 added 2026-09-20, taking every
table in this entry that a taxed run can source to eight.** Eight single runs,
one per universe, default cadence 20, `--profile research`, window 2019-01-01 to
2026-05-29, 1,836 trading days. midcap50 was wired on 2026-09-18 and that was
its FIRST run.

**WHERE THE NUMBERS IN THIS ENTRY COME FROM, AS OF 2026-09-20.** The two tables
immediately below and every table in the tax sections are read from each
universe's `results_<tag>/metrics/TAX_TURNOVER_<tag>_tax.csv` -- a TAXED run's
own artefact in all eight cases -- taking `v2 before tax`, `v2 after tax`,
`bh_lots before tax`, `bh_lots after tax` and `bh published` from its
`cagr_full` column. Nothing here is read from an untaxed log and nothing is
back-derived from a CAGR table. Turnover figures come from
`HOLDING_PERIOD_<tag>_tax.csv` in the same run directory. **THE RISK COMPARISON
SECTION IS THE ONE EXCEPTION AND STILL STANDS AT FOUR ROWS** -- its columns
(MaxDD, AnnVol, Sharpe, Sortino, deployed) are not carried by TAX_TURNOVER at
all, so extending it was out of scope for this pass; that section says so on its
own heading.

### THE RETURN COMPARISON -- FOUR OF EIGHT

Restated 2026-09-19 with the benchmark named, extended to eight 2026-09-20. The
`b&h` column is **`bh published`** -- which matters, because there are two of
them. See the note that follows this table. Rows in REPORT_ORDER.

| universe | v2 CAGR% | bh published CAGR% | **v2 - bh published** | v2 CAGR n | run date |
|---|--:|--:|--:|--:|:--|
| nifty500 | 29.13 | 26.09 | **+3.04** | 1 | 2026-09-20 |
| nifty200 | 27.26 | 25.54 | **+1.73** | 1 | 2026-09-19 |
| nifty100 | 19.01 | 24.16 | **-5.15** | 10 | 2026-09-18 |
| nifty50 | 13.90 | 20.67 | **-6.77** | 1 | 2026-09-18 |
| midcap150 | 27.80 | 25.46 | **+2.34** | 10 | 2026-09-18 |
| midcap100 | 25.52 | 26.82 | **-1.31** | 1 | 2026-09-19 |
| midcap50 | 21.41 | 24.34 | **-2.93** | 1 | 2026-09-18 |
| smallcap250 | 28.63 | 27.15 | **+1.48** | 1 | 2026-09-19 |

**EVERY CELL ABOVE IS ONE RUN EXCEPT TWO, AND THE TWO ARE NOW LABELLED. ADDED
2026-09-22.** `v2 CAGR n` is the number of PRICE-PERTURBATION draws behind that
cell. It is not a seed count: all ten production seeds are held fixed inside every
draw. **n = 1 is a single run on the date given, and its spread was never
measured** -- the figure is one draw of a distribution of unknown width, not a
stable number.

**The `bh published` and `v2 - bh published` cells are n = 1 on all eight rows,
including the two measured ones.** `results/price_noise_measure.py` perturbs the
v2 arm and nothing else, so no benchmark figure in this table has ever been
re-run under noise. Where a gap below is quoted against perturbed v2 draws, the
benchmark inside it is held at its single unperturbed value and the gap's spread
is therefore the v2 leg's alone.

The two measured cells, ten draws each at sigma = 0.01%, taken 2026-09-20
(nifty100) and 2026-09-21 (midcap150) by `results/price_noise_measure.py`. **This
is price-perturbation spread, not seed spread.** The two are different quantities
and the repo carries both, so both are named rather than one being chosen:

| cell | published | n | mean | min | max | sd, price | sd, seed at K=10 |
|---|--:|--:|--:|--:|--:|--:|--:|
| nifty100 v2 CAGR% | 19.01 | 10 | 20.76 | 19.32 | 22.55 | 1.03 | 0.968 |
| midcap150 v2 CAGR% | 27.80 | 10 | 29.88 | 27.69 | 32.35 | 1.74 | 1.393 |

The seed column is entry 29's fitted sigma at K = 10, not a re-measurement. The
perturbation caveat these figures come from is the block in README.md headed
READ THIS BEFORE QUOTING ANY v2 FIGURE BELOW (lines 91-132 on 2026-09-22); it is
not restated here. Per-column labels for all eight universes, including the
columns that carry no spread at all, are in `diagnostics/v34_provenance.txt`.

**Sortino, Calmar and Deployed% are point estimates and inherit no error bar from
this.** `price_noise_measure` recomputes six columns -- CAGR%, Sharpe, MaxDD%,
Trades, FinalEquity, AnnVol% -- and those three are not among them. Nothing
measured here bounds them.

The six universes without a distribution are a deliberate deferral, not an
oversight; the cost and the reason are in KNOWN_ISSUES.md under "Measuring the six
unmeasured universes is costed and deferred".

**THE GAP'S SIGN SURVIVES ALL TWENTY STORED DRAWS. MEASURED 2026-09-22 FROM THE
EXISTING FILE -- NO NEW RUNS.** Read off the ten stored sigma = 0.01% draws per
universe in `diagnostics/price_noise_runs.csv`, against the same fixed
`bh published` used in the table above:

| draw seed | nifty100 v2 | gap vs 24.16 | midcap150 v2 | gap vs 25.46 |
|---|--:|--:|--:|--:|
| 101 | 21.30 | -2.86 | 31.88 | +6.42 |
| 202 | 19.32 | -4.84 | 31.24 | +5.78 |
| 303 | 21.15 | -3.01 | 28.03 | +2.57 |
| 404 | 19.38 | -4.78 | 31.02 | +5.56 |
| 505 | 22.55 | -1.61 | 29.94 | +4.48 |
| 606 | 21.45 | -2.71 | 32.35 | +6.89 |
| 707 | 19.84 | -4.32 | 28.07 | +2.61 |
| 808 | 21.47 | -2.69 | 30.20 | +4.74 |
| 909 | 20.50 | -3.66 | 27.69 | +2.23 |
| 1010 | 20.60 | -3.56 | 28.35 | +2.89 |

**nifty100: 10 of 10 keep the published sign (negative), range -4.84 to -1.61
against a published -5.15. midcap150: 10 of 10 keep the published sign
(positive), range +2.23 to +6.89 against a published +2.34.** 20 of 20 across
both.

Three limits on that count, all of which narrow it:

1. **The benchmark leg is frozen.** Only v2 was perturbed. A count over a gap
   whose other half never moved is not a count over the gap.
2. **It holds at this sigma only.** At the wider sigmas already on disk the
   sign does cross: that same README block records v2 beating its basket in 2
   of nifty100's 25 perturbed cells, and losing to it in 1 of midcap150's 20.
   Ten of ten at 0.01% is not twenty-five of twenty-five.
3. **A stable sign is not a reproduced figure, and on nifty100 it is not even a
   containing interval.** All ten nifty100 draws come in above the published
   19.01, so the gap interval they describe -- -4.84 to -1.61 -- does not
   contain the published -5.15. midcap150 differs: nine of its ten are above
   27.80 and the tenth, seed 909 at 27.69, is below, so its interval +2.23 to
   +6.89 does contain the published +2.34. The sign agrees on both universes
   and the figure is reproduced on neither.

No mechanism is offered for any of this, and none should be read into it. It is a
count of sign agreement over ten stored draws.

**"ONE OF FOUR" IS NOW FOUR OF EIGHT. AMENDED 2026-09-20.** This line read "One
universe's v2 beats its own equal-weight buy & hold. FOUR do not". On eight,
**four beat it -- nifty500, nifty200, midcap150, smallcap250 -- and four do
not.** The count moved because universes were added, not because anything was
re-measured: the five original rows are unchanged to the last decimal.

midcap100's row is still a SINGLE RUN of a universe wired the same day. The
claim that once sat here -- that it "carries the highest survivorship loading of
the five" -- **is false on eight** and is corrected in the after-tax section
below: smallcap250 is 90 of 248 late listers, 36.3%, against midcap100's 21 of
98, 21.4%.

### TWO DIFFERENT BENCHMARKS, AND EVERY GAP ROW MUST NAME WHICH

Added 2026-09-19, extended to eight 2026-09-20. There are two buy & hold lines
in this project and they are not the same series:

- **`bh published`** -- a costless, daily-rebalanced index line. Untaxable: it
  holds no lots, so there is nothing to assess. Reference only.
- **`bh_lots before tax`** -- an equal-rupee basket of actual lots, untaxed. It
  is the only benchmark that CAN be taxed, because it is the only one that owns
  positions.

| universe | bh published CAGR% | bh_lots before tax CAGR% | difference |
|---|--:|--:|--:|
| nifty500 | 26.09 | 24.43 | 1.66 |
| nifty200 | 25.54 | 23.69 | 1.85 |
| nifty100 | 24.16 | 23.38 | 0.78 |
| nifty50 | 20.67 | 19.62 | 1.05 |
| midcap150 | 25.46 | 23.55 | 1.90 |
| midcap100 | 26.82 | 24.48 | 2.35 |
| midcap50 | 24.34 | 25.97 | -1.63 |
| smallcap250 | 27.15 | 26.60 | 0.55 |

**The spread does not carry a consistent sign, and on eight it is still exactly
one universe.** midcap50's equal-rupee basket beats its index line; the other
seven do not. The spread ranges from -1.63 to +2.35 and its magnitude is not
ordered by universe size.

**midcap150's DIFFERENCE IS 1.90, NOT 1.91. CORRECTED 2026-09-20.** This row and
the paragraph below it both read 1.91, which is `25.46 - 23.55` -- the two
figures rounded to two places and then subtracted. The unrounded difference is
`25.4588 - 23.5541 = 1.9047`, which is 1.90. Every difference in this table is
now computed before rounding, not after. The other four original rows are
unaffected.

**Consequence for reading this entry:** the `v2 - bh published` column above and
the `gap_before_tax` / `gap_after_tax` rows below are measured against DIFFERENT
benchmarks. midcap150's pre-tax gap is **+2.34 against bh published** and
**+4.24 against bh_lots** -- the same run, 1.90 points apart, and the whole of
that difference is the benchmark swap. A reader who takes a number from the
first table and compares it with a number from the tax tables is reading a
two-benchmark artefact as a result. Every row below names its benchmark for
exactly this reason.

### THE SAME COMPARISON AFTER TAX

**EXTENDED TO EIGHT, 2026-09-20.** Source: each universe's
`results_<tag>/metrics/TAX_TURNOVER_<tag>_tax.csv`, read 2026-09-20. Every
figure in this section and the two that follow comes from that artefact or from
`HOLDING_PERIOD_<tag>_tax.csv` in the same run directory -- a taxed run in every
case, never an untaxed log, never back-derived from the pre-tax CAGR table
above. n = 8, one run each, cadence 20, `--profile research`. Benchmark
throughout is **bh_lots**, never bh published. Rows in REPORT_ORDER.

| universe | v2 before tax | v2 after tax | bh_lots before tax | bh_lots after tax | n | run date |
|---|--:|--:|--:|--:|--:|:--|
| nifty500 | 29.13 | 24.62 | 24.43 | 22.69 | 1 | 2026-09-20 |
| nifty200 | 27.26 | 23.17 | 23.69 | 21.97 | 1 | 2026-09-19 |
| nifty100 | 19.01 | 16.17 | 23.38 | 21.68 | 1 | 2026-09-18 |
| nifty50 | 13.90 | 11.96 | 19.62 | 18.12 | 1 | 2026-09-18 |
| midcap150 | 27.80 | 23.51 | 23.55 | 21.85 | 1 | 2026-09-18 |
| midcap100 | 25.52 | 21.50 | 24.48 | 22.73 | 1 | 2026-09-19 |
| midcap50 | 21.41 | 18.19 | 25.97 | 24.16 | 1 | 2026-09-18 |
| smallcap250 | 28.63 | 24.13 | 26.60 | 24.78 | 1 | 2026-09-19 |

**EVERY CELL IN THIS TABLE IS n = 1, INCLUDING nifty100's AND midcap150's. ADDED
2026-09-22.** The `n` column is price-perturbation draws, and there are none
behind any cell here. `results/price_noise_measure.py` runs untaxed
(`tax_enabled=False`) and perturbs the v2 arm only, so **no after-tax figure and
no bh_lots figure in this project has ever been re-run under noise.**

The `v2 before tax` column repeats the published v2 CAGR, and for nifty100 and
midcap150 that figure does have a measured spread -- 19.01 against ten draws
spanning 19.32 to 22.55, and 27.80 against 27.69 to 32.35, both at sigma = 0.01%.
**That spread does not propagate to the three columns beside it.** The after-tax
and bh_lots figures come from separate runs that were never perturbed, so the
tax deltas in this table are differences of single draws and their width is
unknown. See the labelled table above and `diagnostics/v34_provenance.txt`.

Tax paid by v2: nifty500 Rs 848,041.14; smallcap250 Rs 828,764.83; midcap150
Rs 771,494.59; nifty200 Rs 769,131.89; midcap100 Rs 656,939.61; midcap50
Rs 492,955.59; nifty100 Rs 397,607.08; nifty50 Rs 240,474.46.

**"THE HIGHEST LATE-LISTER RATE OF THE FIVE" WAS TRUE OF FIVE AND IS FALSE OF
EIGHT. AMENDED 2026-09-20.** This section said of midcap100: "21 of its 98
names -- 21.4% -- did not exist at BT_START_DATE ... It is the highest
late-lister rate of the five." **smallcap250 is 90 of 248, 36.3%**, and
nifty500 is 137 of 495, 27.7%, and midcap150 is 36 of 148, 24.3%. midcap100 is
fourth of eight. The full column is in `KNOWN_ISSUES.md` beside the same gaps.

This is the same shape as the two instances recorded further down -- "no sign
changes on any of the four" and "every pair clears dE2000 >= 10" -- and it is
the third. A correct count over the universes in hand, written as a ranking of
the thing counted, and read as true until the set grew. It was not a careless
number either.

**What survives the amendment:** midcap100's composition is still loaded
differently from midcap50's (21.4% against 16.3%) and a reader comparing those
two rows without it is still comparing panels loaded differently by a third
again. **The direction of the total survivorship effect is not known for any
universe here, and has been measured running BOTH ways.** That was never a
correction to apply and is not one now.

**THE v2 AFTER-TAX FIGURE DEPENDS ON THE UNASSESSED TAIL, AND TWO NUMBERS ARE IN
CIRCULATION.** `FY_EQUITY`'s close is the in-loop taxed curve: FY2026-27 is
assessed on the first session at or after 31 March 2027, outside the window, so
its liability is computed and never deducted. `TAX_TURNOVER`'s `v2 after tax`
settles that tail at the final session, so that v2 and bh_lots are comparable at
the same endpoint. They differ by exactly the tail, and by nothing else:

| universe | FY_EQUITY (tail unsettled) | TAX_TURNOVER (tail settled) | tail |
|---|--:|--:|--:|
| nifty500 | 24.62 | 24.62 | Rs 2,213.45 |
| nifty200 | 23.17 | 23.17 | Rs 0.00 |
| nifty100 | 16.23 | 16.17 | Rs 11,521.13 |
| nifty50 | 11.96 | 11.96 | Rs 0.00 |
| midcap150 | 23.63 | 23.51 | Rs 33,671.08 |
| midcap100 | 21.62 | 21.50 | Rs 32,409.13 |
| midcap50 | 18.19 | 18.19 | Rs 0.00 |
| smallcap250 | 24.32 | 24.13 | Rs 56,168.64 |

**READ nifty500'S ROW AS A ROUNDING COINCIDENCE, NOT A ZERO TAIL.** Its two
columns both print 24.62 and its tail is Rs 2,213.45, not nothing: the
unrounded figures are 24.6230 and 24.6157. Three universes -- nifty200, nifty50,
midcap50 -- have a tail of exactly Rs 0.00 and their columns are equal for that
reason. nifty500's are equal for a different one, and the two cases are not
interchangeable.

**Every gap and cost row below uses the tail-settled column**, because the
benchmark it is differenced against is settled at the same session. The columns
agree to two places on four of the eight and differ on the other four. Quoting
23.63 next to a gap computed from 23.51 does not reconcile -- it silently moves
midcap150's cost from -2.58 to -2.46 -- which is why both columns are printed
rather than one being chosen. smallcap250's tail is the largest of the eight at
Rs 56,168.64 and moves its figure by 0.19 points.

### TAX_COST_OF_TURNOVER

Defined as `gap_after_tax - gap_before_tax`, both gaps v2 minus **bh_lots**. It
is what turnover costs in tax, against a benchmark taxed by the identical rules.
Eight universes as of 2026-09-20, ordered by lots closed. `lots` and
`mean held` are the `lots` and `mean_held_days` columns of
`HOLDING_PERIOD_<tag>_tax.csv`.

| universe | lots closed | mean held, days | gap before tax | gap after tax | **TAX_COST_OF_TURNOVER** |
|---|--:|--:|--:|--:|--:|
| nifty500 | 555 | 43.81 | +4.71 | +1.92 | **-2.78** |
| smallcap250 | 549 | 45.70 | +2.03 | -0.65 | **-2.67** |
| midcap150 | 499 | 49.76 | +4.24 | +1.66 | **-2.58** |
| nifty200 | 488 | 51.61 | +3.58 | +1.20 | **-2.38** |
| nifty100 | 466 | 54.21 | -4.37 | -5.52 | **-1.15** |
| midcap100 | 450 | 57.42 | +1.04 | -1.23 | **-2.27** |
| nifty50 | 425 | 59.88 | -5.72 | -6.16 | **-0.44** |
| midcap50 | 424 | 63.72 | -4.56 | -5.97 | **WITHHELD** |

nifty200, smallcap250 and nifty500 added 2026-09-20, one run each; midcap100
added 2026-09-19, its own run, wired the same day.

**SEVEN COSTS, ONE WITHHELD, AND NO ORDERING IS CLAIMED. RESTATED FOR EIGHT,
2026-09-20.** This paragraph has now been rewritten twice -- it read "the cost
is larger where turnover is larger" on three universes, then "what is measured
now is four costs and no ordering" on four. On eight the position is this, and
it is arithmetic about the table rather than a claim about turnover:

- The two proxies **rank the eight identically**. Sorting by lots descending and
  by mean held ascending give the same order, the one printed above.
- On that shared ranking the seven reporting costs are -2.78, -2.67, -2.58,
  -2.38, -1.15, -2.27, -0.44. **Six of the seven steps down; one steps up.** The
  inversion is the adjacent pair nifty100 / midcap100, -1.15 followed by -2.27.
- **Which member of that pair is "out of place" is not determined by the data.**
  The 2026-09-19 text named midcap100, because midcap100 was the row that had
  just arrived. With three more universes the pair is simply inverted, and
  naming a culprit inside it would be reading arrival order as evidence.

**NO MECHANISM IS BEING ASSERTED AND NONE SHOULD BE READ IN.** Turnover and
cost may or may not move together; this table does not settle it, and the
project has already been wrong about it once at n = 4. Seven points, no
functional form, values not proportional to either proxy: lots fall 24% from
nifty500 to nifty50 while the cost falls 84%, and one interior point does not
lie between its neighbours. **What is measured is seven costs, one withheld, and
one inversion.**

**NOT that the eighth would fit.** midcap50 is withheld, and it is the SMALLEST
universe of the eight and the last row under both proxies -- the extrapolation a
reader is most tempted to make is precisely the point that was not measured. It
is also the only one of the EIGHT whose bh_lots basket beats its own index
line -- checked on all eight 2026-09-20 from the `bh published` and `bh_lots
before tax` rows of each TAX_TURNOVER artefact, and the other seven go the
other way. Its arithmetic difference is -1.41.
**That number is not the cost**, because the benchmark it is differenced against
was rejected.

**WHY midcap50 IS WITHHELD**, in the guard's own words, verbatim from the
`withheld_reason` column of `results_midcap50/metrics/TAX_TURNOVER_midcap50_tax.csv`:

> top-name weight 12.4% exceeds the 11.62% limit by 1.1x; DIXON alone moves the
> benchmark -2.22 pts against an effect size of 2.05, and the universe is
> SURVIVORSHIP_MODE=static so that name is in the basket because of the run it
> had

The row is written with a blank value rather than omitted. An absent row reads
as "not computed"; this was computed and rejected, and the file says which. It
is the only withheld row of the eight, and extending the table to eight did not
change its status either way.

### WHAT TAX DOES TO THE EARLIER FINDING

Eight universes as of 2026-09-20. Rows in REPORT_ORDER.

| universe | gap before tax | gap after tax | change | sign change? |
|---|--:|--:|--:|---|
| nifty500 | +4.71 | +1.92 | -2.78 | no -- stays positive |
| nifty200 | +3.58 | +1.20 | -2.38 | no -- stays positive |
| nifty100 | -4.37 | -5.52 | -1.15 | no -- stays negative |
| nifty50 | -5.72 | -6.16 | -0.44 | no -- stays negative |
| midcap150 | +4.24 | +1.66 | -2.58 | no -- stays positive |
| **midcap100** | **+1.04** | **-1.23** | **-2.27** | **YES -- positive to negative** |
| midcap50 | -4.56 | -5.97 | -1.41 | no -- stays negative |
| **smallcap250** | **+2.03** | **-0.65** | **-2.67** | **YES -- positive to negative** |

**THIS SECTION SAID "NO SIGN CHANGES ON ANY OF THE FOUR". THAT IS NOW FALSE.
AMENDED 2026-09-19, AND A SECOND CROSSING ADDED 2026-09-20.** It read: "Tax
moves every gap in the same direction -- against v2 -- and carries none of them
across zero." The first half survives on all eight; the second does not.
**midcap100 crosses**: +1.0392 before tax, -1.2280 after, cost -2.2672.
**smallcap250 crosses**: +2.0294 before tax, -0.6453 after, cost -2.6747. Two of
eight. For each, v2 beats its own equal-rupee basket before tax and loses to it
after, and tax alone decides which side of zero that universe sits on.

**FOUR OF FOUR WAS A COUNT, NEVER A PROPERTY, AND THE SENTENCE READ AS THOUGH
IT WERE ONE.** "Carries none of them across zero" is a claim about tax; what
had been measured was four universes in which it happened not to. The
distinction is invisible while the count holds and is the whole content of the
record once it does not. **And "six of eight do not cross" is also a count.**
Adding three universes turned one crossing into two, and the sentence to avoid
now is "tax crosses the small gaps" -- which is what six-of-eight looks like from the
inside, and is not established.

**IT IS THE SAME ERROR AS "every pair clears dE2000 >= 10"**, written on
midcap50's registry row on 2026-09-18 and false by 2026-09-19 for the identical
reason: both were true of what had been measured and asserted about what had
not, and both read as true until a further universe was added. Neither was a
careless number. Each was a correct measurement over a set, phrased as a
property of the thing being measured. **That is the shape to watch for, and this
entry now holds three instances** -- the third being "the highest late-lister
rate of the five", amended above on 2026-09-20.

**The counts, restated for eight.** Against `bh_lots before tax`, 5 of 8 are
positive -- nifty500, nifty200, midcap150, midcap100, smallcap250. After tax,
3 of 8 -- nifty500, nifty200, midcap150. **The after-tax count changed because
of tax; the before-tax count changed because universes were added.** Those are
two different things happening in the same table and the rows are marked so
they are not read as one. The `v2 - bh published` count in the first table of
this entry is a THIRD thing, measured against a different benchmark and giving
a third answer -- four of eight -- on the same eight runs.

**This is recorded, not concluded.** Everything the pre-tax entry declined to
claim it still declines to claim: eight single runs, one per universe, NO ERROR
BAR ON ANY OF THEM, NO SEED-NOISE BAND MEASURED ON ANY OF THE EIGHT, and both
crossings are ONE OBSERVATION each whose width is unmeasured. The gaps that
cross are +1.04 and +2.03 before tax and -1.23 and -0.65 after; seed noise has
previously been shown to cover differences of this size on this project's other
measurements, and **-0.65 is not distinguishable here from a gap of zero.** No
accept rule was pre-registered for the tax comparison. **Do not read "tax flips
the sign" as a finding about tax.** It is two runs in which it did.

### THE RISK COMPARISON -- FOUR OF FOUR ON DRAWDOWN (STILL FOUR ROWS)

**THIS IS THE ONE TABLE IN THIS ENTRY THAT WAS NOT EXTENDED TO EIGHT ON
2026-09-20, AND THE REASON IS PROVENANCE, NOT OVERSIGHT.** MaxDD, AnnVol,
Sharpe, Sortino and deployed% are not columns of `TAX_TURNOVER_<tag>_tax.csv`,
which is the artefact every other table above is now read from. Extending this
one would mean sourcing four new rows from somewhere else in the same pass, so
it was left at four and marked rather than quietly mixed. **Four rows here
beside eight rows above is a scope boundary, not a disagreement between
tables.** midcap100, nifty200, smallcap250 and nifty500 are absent from it.

| universe | MaxDD% b&h -> v2 | AnnVol% b&h -> v2 | Sharpe b&h -> v2 | Sortino b&h -> v2 | v2 deployed |
|---|---|---|---|---|--:|
| midcap150 | -37.73 -> **-20.01** | 18.42 -> 13.65 | 1.35 -> **1.90** | 1.52 -> 2.55 | 54.6% |
| midcap50 | -37.57 -> **-20.30** | 18.99 -> 13.22 | 1.26 -> **1.56** | 1.46 -> 2.12 | 55.5% |
| nifty100 | -38.65 -> **-21.87** | 18.67 -> 12.33 | 1.27 -> **1.50** | 1.45 -> 2.07 | 56.8% |
| nifty50 | -39.11 -> **-23.20** | 17.97 -> 12.26 | 1.15 -> **1.14** | 1.34 -> 1.49 | 57.2% |

Maximum drawdown falls on all four, from a 37-39% band to a 20-23% band.
Annualised volatility falls on all four, 18-19% to 12-14%. Sortino rises on all
four. Average exposure lands in 54.6-57.2% on all four without being targeted.

**ONE EXCEPTION, STATED BECAUSE IT IS THE ONLY ONE: nifty50's Sharpe does NOT
rise.** It goes 1.15 -> 1.14, a fall of 0.01. Its drawdown, volatility and Sortino
move with the other three; its Sharpe does not. Any sentence of the form "the
exposure rule raises Sharpe everywhere" is false as written, and the figure that
makes it false is this one.

### WHAT THESE NUMBERS ARE, IN ONE LINE EACH

- The drawdown and volatility reduction appears on every universe measured --
  and that is FOUR universes, not eight, because the risk table was not
  extended on 2026-09-20.
- The return advantage over `bh published` appears on **four of the eight**
  measured; over `bh_lots before tax` on five of eight before tax and three of
  eight after it. Three counts, three benchmarks, and they are not the same
  statement.
- **Those bullets are NOT about the same set of runs.** The first covers four
  universes, the second eight. Reading them as one sentence about one set is
  the error this bullet exists to prevent.

### WHAT IS NOT ESTABLISHED, AND IS NOT BEING CLAIMED HERE

**NOT that midcap150 is special.** Eight universes at one run each cannot
distinguish a property of that universe from a draw, and on eight it is no
longer even the largest pre-tax gap -- nifty500's is +4.71 against bh_lots. No attribution is offered:
not to capitalisation, not to constituent count, not to breadth behaviour, not to
the panel. **This entry names no cause.**

**NOT that the return edge is absent on the universes where it did not
appear.** A single run per universe has no error bar, and no seed-noise band
has been measured on ANY of the eight. `diagnostics/seed_noise.txt` exists for the earlier
universes precisely because seed choice moves these figures, and the edge
differences above are of a size that seed noise has previously been shown to
cover on this project's other measurements. Four negative single runs against
bh published are four observations, not a refutation.

**NOTHING ON midcap50 IS VALIDATED.** No seed-robustness, no sub-period split, no
shuffle test, no top-N sweep has been run on these 49 names. Its column above is a
SINGLE RUN with no measured dispersion. It is no longer the newest -- nifty200,
smallcap250 and nifty500 were wired and run later -- and **none of those three
is validated either.** The depth of validation behind the eight universes now
differs by more than it did at four, which is itself a reason not to read the
rows as equally supported.

**SURVIVORSHIP IS STATIC ON ALL EIGHT** -- every universe is today's index
members backfilled to 2019, and names that left during the window are absent
from all of them. The rate at which that bias is loaded differs, and it is not
small. Extended to eight 2026-09-20; the column is the same one carried beside
the gaps in `KNOWN_ISSUES.md`:

| universe | names starting after BT_START_DATE |
|---|--:|
| smallcap250 | 90 of 248 -- **36.3%** |
| nifty500 | 137 of 495 -- **27.7%** |
| midcap150 | 36 of 148 -- **24.3%** |
| midcap100 | 21 of 98 -- **21.4%** |
| midcap50 | 8 of 49 -- **16.3%** |
| nifty200 | 32 of 197 -- **16.2%** |
| nifty100 | 11 of 99 -- **11.1%** |
| nifty50 | 4 of 50 -- **8.0%** |

The spread is 8.0% to 36.3%, a factor of 4.5, and smallcap250 is loaded more
than four times as heavily as nifty50. The direction of the total survivorship
effect is NOT known for any of the eight -- see the survivorship record
elsewhere in this project, which measured it running BOTH ways -- so this table
is a statement about composition, not a correction to apply, and **no row above
was adjusted for it.**

### WHAT WOULD SETTLE IT

1. **Seed noise per universe.** Run the existing seed-noise measurement on all
   eight and put an error bar on each v2 - b&h difference. Until that exists,
   the +4.71 and the -2.93 cannot be compared, because neither has a width --
   and neither can the two crossings, which are -1.23 and -0.65.
2. **Sub-period splits**, the same halves used elsewhere in this file, on all
   eight. A return edge present in one half and absent in the other is a
   different finding from one present throughout.
3. **More universes -- DISCHARGED AS FAR AS IT CAN BE, 2026-09-20.** All eight
   supplier folders are now wired and run. There is no ninth folder, so no
   further universe can arrive from this data set. **That settles the count and
   nothing else:** it is still one run per universe, and eight measurements at
   n = 1 each is eight measurements.
4. **A pre-registered rule, written before those runs**, saying what result
   would count as the return edge reproducing and what would count as it
   failing to. **This was NOT written before the eight runs, and the eight runs
   are now done** -- so items 1 and 2 are the only ones a future run can still
   satisfy honestly, and item 4 can now only be written for a different
   question. Without one, this table is a trial count with no accept rule,
   which is the failure mode this file was started to prevent.

**Until at least 1 exists, this entry is eight measurements and no verdict, and
item 4 can no longer be satisfied for this table.**
