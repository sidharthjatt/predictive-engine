# EXPERIMENTS — the complete record

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

**This file lists 27 entries, of which 26 were actually run.** Entry 27 was added
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

"At least" is meant literally. Two of the twenty-seven entries have no surviving
mechanism (1, 8), one has no surviving verdict (26), and the count was
demonstrably wrong three separate times. **Treat 26 as a floor, not a
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

One acceptance in twenty-six trials, and one trial whose outcome was never
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

**Verdict.** **ACCEPTED.** The only acceptance in twenty-six trials. Both
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

And modelling depth natively rather than as flat slippage costs mid **1.80 CAGR
points and 0.10 Sharpe** (29.16% → 27.36%, Sharpe 2.00 → 1.90, 19 orders walking
the book), against **0.01 points** for n100.

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

*Pre-registration: `experiments/sizing_test.py` (kept) — the accept rule is in the
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
`results/test_v1_v2_blend.py` is kept for that reason.

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
| `sizing_test.py` | entry 26 — the accept rule, in its docstring. **Restored from backup 2026-08-23**; the only artefact of that experiment |

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
