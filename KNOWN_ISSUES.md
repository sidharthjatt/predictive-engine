# Known issues

> **NAMING.** The universe tags were renamed on 2026-09-18: `mid` ->
> `midcap150`, `n100` -> `nifty100`, `n50` -> `nifty50`. Code and live
> artefacts use the new names; records, diagnostics, `runs/` and all prose
> still use the old ones and are correct to. **An old tag is not a missing
> universe.** The map, and the full list of what deliberately keeps the old
> names, is in [PANEL_MIGRATION.md](PANEL_MIGRATION.md).

> **THE 58 AND THE 74 WERE DELETED ON 2026-09-11.** Both universes, their raw
> data, their registry entries and the 26 scripts that served them are gone from
> this repository. Every reference to them below is **historical**: it records what
> was measured and when, and none of it can be re-run. The figures are preserved at
> full precision, with a SHA-256 manifest of every surviving artefact, in
> [RETIRED_UNIVERSES.md](RETIRED_UNIVERSES.md). Where a passage names a deleted file, it is
> describing what that file did, not something you can run.

Defects that are recorded but not fixed. Anything found and left alone belongs
here, with what it is, where it lives, and what a reader would wrongly conclude
because of it. Nothing in this file is a plan; it is a list of things that are
currently wrong.

---

## The `b&h` column carried two different benchmarks, and the two are not comparable

Found 2026-09-19, while amending the four-universe entry with tax. Open, in the
sense that the two columns still sit in one entry and only prose separates them.

`bh published` is a costless, daily-rebalanced index line and is untaxable -- it
holds no lots, so there is nothing to assess. `bh_lots` is an equal-rupee basket
of real lots and is the only benchmark that can be taxed. The pre-tax gaps in
`experiments/EXPERIMENTS.md` ("THE RETURN COMPARISON -- ONE OF FOUR") are
measured against the first; every tax gap in the same entry ("TAX_COST_OF_TURNOVER"
and "WHAT TAX DOES TO THE EARLIER FINDING") is measured against the second.
midcap150's pre-tax gap is +2.34 on one and +4.24 on the other -- the same run,
1.91 points apart, all of it the benchmark swap.

**The spread does not hold a sign, so it cannot be corrected for by a constant
or by intuition:** midcap50's equal-rupee basket BEATS its index line (25.97 vs
24.34) while the other three do not (midcap150 23.55 vs 25.46, nifty100 23.38 vs
24.16, nifty50 19.62 vs 20.67). A reader who carries a number from the first
table into the second is reading a two-benchmark artefact as a result. The two
columns were never comparable, including before the tax work named the
difference.

## THE EIGHT-UNIVERSE READ, 2026-09-20 -- n = 8 of 8, and what that does and does not discharge

All eight supplier folders on disk are wired and run. Recorded 2026-09-20.

**PROVISIONAL-UNTIL-EIGHT IS DISCHARGED FOR THE UNIVERSES ON DISK, AND FOR
NOTHING ELSE.** The standing rule in the class entry below has applied to every
cross-universe claim here since 2026-09-19. It is satisfied as of 2026-09-20:
there is no ninth supplier folder, so no further universe can arrive and
falsify a count. That is the only thing it discharges.

**IT DOES NOT MAKE ANY OF THE BELOW A PROPERTY.** As of 2026-09-20, on these
eight universes: each has had EXACTLY ONE RUN, at cadence 20, `--profile
research`. There is NO ERROR BAR on any figure below. No seed-noise band has
been measured on any of the eight. No accept rule was pre-registered for the
tax comparison. Eight measurements with n = 1 each is eight measurements, and a
count over them is a count.

### 1. SIGN -- two of eight cross zero under tax, as measured 2026-09-20

Gaps are v2 minus **bh_lots**, the equal-rupee basket, never `bh published`.

| universe | gap before tax | gap after tax | TAX_COST_OF_TURNOVER | crosses? | late listers |
|---|--:|--:|--:|---|--:|
| nifty500 | +4.7050 | +1.9230 | -2.7819 | no | 137/495 = 27.7% |
| midcap150 | +4.2438 | +1.6633 | -2.5805 | no | 36/148 = 24.3% |
| nifty200 | +3.5752 | +1.1994 | -2.3757 | no | 32/197 = 16.2% |
| **smallcap250** | **+2.0294** | **-0.6453** | **-2.6747** | **YES** | 90/248 = 36.3% |
| **midcap100** | **+1.0392** | **-1.2280** | **-2.2672** | **YES** | 21/98 = 21.4% |
| nifty100 | -4.3710 | -5.5188 | -1.1478 | no | 11/99 = 11.1% |
| midcap50 | -4.5592 | -5.9713 | WITHHELD | no | 8/49 = 16.3% |
| nifty50 | -5.7221 | -6.1598 | -0.4377 | no | 4/50 = 8.0% |

**What these eight rows show, as of 2026-09-20:** two of the eight have a
positive gap before tax and a negative gap after it. Three have a positive gap
on both sides. Three have a negative gap on both sides. Tax moved every one of
the eight gaps in the same direction, against v2.

**NO RELATION BETWEEN LATE LISTING AND CROSSING IS ASSERTED HERE, AND THE TABLE
IS ORDERED SO THE TEMPTATION IS VISIBLE RATHER THAN HIDDEN.** nifty500 is 27.7%
and does not cross; smallcap250 is 36.3% and does; midcap100 is 21.4% and does;
midcap150 is 24.3% and does not. The late-lister column is beside the gaps
because a reader will want it, not because it explains them. **Nothing was
regressed and nothing should be read as ordered.**

**BOTH CROSSINGS ARE SMALL.** -1.2280 and -0.6453. This project has previously
shown seed choice to move measurements of this kind by amounts that cover
differences of this size, and no seed-noise band has been measured on either
universe. A crossing of -0.65 is not distinguishable, on the evidence here,
from a gap of zero.

**midcap50's cost is WITHHELD, not missing.** Its bh_lots basket is 12.4% one
name against an 11.62% limit. The gap columns are arithmetic and are shown; the
cost is not, because the benchmark it would be differenced against was
rejected.

### 2. COST -- linear in panel rows, as measured 2026-09-20

**30.592 min per million panel rows, intercept +0.37 min.** Fitted on two
universes (0.38M and 0.85M rows) and tested on two more:

| universe | symbols | panel rows | scoring | rows/min | model error |
|---|--:|--:|--:|--:|--:|
| midcap100 | 98 | 383,486 | 12.1 min | 31,693 | fitted |
| nifty200 | 197 | 854,197 | 26.5 min | 32,234 | fitted |
| smallcap250 | 248 | 798,981 | 23.5 min | 33,999 | -5.2% |
| nifty500 | 495 | 1,834,542 | 57.5 min | 31,905 | +1.8% |

Held to **1.8% at 1.83M rows, 2.2x the largest point it was fitted on**.
rows/min spans **31,693 to 33,999** across a **4.8x** span in panel size.

**SYMBOL COUNT IS NOT THE VARIABLE, and two models built on it failed** -- a
fixed-cost reading and an `n^1.123` superlinear reading, in that order. See the
entry above. smallcap250 has 26% more symbols than nifty200 and scored 3
minutes faster, which no model in symbols can produce.

**NO CURVATURE TERM IS ADDED ON 1.8%.** The nifty500 miss is HIGH, which is the
direction a small superlinearity would give and also the size of ordinary
machine noise. Four points cannot separate those. Adding a term to fit 1.8% is
what produced `n^1.123`.

### 3. PALETTE -- four points, both decrement sequences flattening, measured 2026-09-19/20

| existing slots | best single in-band | T (6-tuple) | universe added |
|--:|--:|--:|---|
| 24 | 10.2452 | 8.712634 | midcap100 |
| 30 | 8.5514 | 7.484141 | nifty200 |
| 36 | 7.2555 | 6.801402 | smallcap250 |
| 42 | 6.5910 | 6.136133 | nifty500 |

T decrements -1.2285, -0.6827, -0.6653; single-colour -1.6938, -1.2959,
-0.6645. **Both flattened rather than accelerating**, so **the readable band was
not exhausted at eight universes**. A linear projection off the first two T
points would have said about 5.6 for the eighth and understated it by half a
point.

**nifty500's worst pair is 6.136 and that is 1.9x the worst pair the repository
already ships.** THE REAL WORST PAIR REMAINS 3.26 -- nifty100/v1 vs
nifty100/v3, under deuteranopia, a within-universe pair that has shipped
throughout. Every palette searched since 2026-09-19 clears a threshold the
incumbent tuples do not.

## build_scores was modelled on symbol count, and the third universe broke it by 31%

Found 2026-09-19, when smallcap250 ran. Open only as a record -- the model is
replaced below. What is worth keeping is how it failed.

**THE MISS.** The prediction was recorded before the run, in
`diagnostics/build_scores_cost.txt`, precisely so it could fail:

    predicted   34.3 min scoring (power law), 33.9 (linear)
    ACTUAL      23.5 min      -- 31% below, the falsifier that file named

**NO FUNCTION OF SYMBOL COUNT CAN PRODUCE THIS RESULT.** smallcap250 has 248
symbols against nifty200's 197 -- **26% MORE** -- and scored **3 minutes
FASTER**. Any model in symbols, of any shape, is monotonic in symbols and
predicts the opposite sign.

| universe | symbols | panel rows | scoring | rows/min |
|---|--:|--:|--:|--:|
| midcap100 | 98 | 383,486 | 12.1 min | 31,693 |
| nifty200 | 197 | 854,197 | 26.5 min | 32,234 |
| smallcap250 | 248 | 798,981 | 23.5 min | 33,999 |

**ROWS IS THE VARIABLE.** Fitting the first two points on rows gives **30.592
min per million rows, intercept +0.37 min**. That intercept is small and
POSITIVE, which is what a real fixed cost looks like -- and it is what the
nifty200 "intercept" claim was reaching for and got backwards. The row model
predicts smallcap250 at 24.8 against 23.5 actual: **5%, against the symbol
model's 31%**.

**TWO SUCCESSIVE EXPLANATIONS WERE OFFERED FOR THE SAME MISS AND BOTH WERE
WRONG.** First, in `615e257`: nifty200's 9% overrun was "the fixed cost the
linear model ignored" -- backwards, since a positive fixed cost makes scaling
sub-linear and nifty200 came in above proportional. Then, in `ec2820c`: mild
superlinearity, `n^1.123`, with the negative intercept named as its signature.
The second explanation fit the two points better than the first. **It was still
wrong, because both regressed the wrong variable.**

**A BETTER FIT ON THE WRONG AXIS IS NOT EVIDENCE.** The `n^1.123` power law
reproduced both measured points closely; that is what fitting two points with
two parameters does, and it carried no information about whether symbols were
the right regressor at all. The thing that settled it was a third point chosen
to be able to disagree -- and it disagreed by 31%.

**THE FACT THAT TIES IT TOGETHER.** Panel rows are symbols x sessions each
symbol actually traded, and **90 of smallcap250's 248 names postdate
BT_START_DATE**, so rows and symbols come apart: more names, fewer rows.

**That one number, 36.3%, now causes three separate things: the calendar guard
firing, the symbol cost model breaking, and the panel being thinner than its
size suggests.** Each was diagnosed on its own before the common cause was
visible. The registry row for `smallcap250`, the calendar-guard entry above and
`diagnostics/build_scores_cost.txt` all point here.

**nifty500'S 70-75 MINUTE ESTIMATE IS WITHDRAWN.** It was computed from symbol
count -- 495 names scaled against a symbol-count fit -- and is evidence of
nothing. Count nifty500's panel rows and apply 30.6 min per million. Do not
scale its 495 names against smallcap250's 248; that is the same error a third
time.

**The row model has been fitted on two points and tested on one, at 5%. It is
untested outside 0.38-0.85 million rows**, and nifty500 will be well outside
that. n = 3 measured universes, 2026-09-19.

## The calendar density guard was LOOSENED on 2026-09-19, from the global median to the per-year median

**This is a loosening, recorded as one.** The guard is weaker than it was. It is
not a fix and it did not correct an unsound test.

**What it does.** `engine_core._check_calendar` refuses to filter any phantom
date that carries as many symbols as a normal day. "Normal day" was the median
over the panel's whole history, 2000-2026; it is now the median of that date's
own year.

**What it passes.** Measured over all seven wired universes, n = 7, 2026-09-19:
**exactly the 23 smallcap250 dates that abort today, and nothing else
anywhere.**

| universe | global med | window med | phantom | ≥global | ≥era | ≥window |
|---|--:|--:|--:|--:|--:|--:|
| midcap150 | 93 | 128 | 237 | 0 | 0 | 0 |
| nifty100 | 79 | 93 | 237 | 0 | 0 | 0 |
| nifty50 | 43 | 48 | 228 | 0 | 0 | 0 |
| midcap50 | 33 | 46 | 237 | 0 | 0 | 0 |
| midcap100 | 64 | 89 | 237 | 0 | 0 | 0 |
| nifty200 | 143 | 182 | 237 | 0 | 0 | 0 |
| **smallcap250** | **125** | **196** | 231 | **23** | **0** | **0** |

`era ⊆ global` and `window ⊆ global` on every universe; `era \ global` and
`window \ global` are EMPTY everywhere. Both alternatives are strictly looser
or equal, never tighter. **No date is caught by the new rule that the old rule
missed.**

**Why it is defensible.** No phantom date on any universe exceeds **0.60 of its
era**; the threshold is 1.00, so the nearest miss has **40 points of margin**:

| universe | max ratio-to-era | on |
|---|--:|---|
| smallcap250 | 0.599 | 2025-12-25 |
| midcap50 | 0.511 | 2024-12-25 |
| midcap100 | 0.495 | 2025-12-25 |
| midcap150 | 0.490 | 2025-12-25 |
| nifty200 | 0.370 | 2025-12-25 |
| nifty100 | 0.247 | 2025-12-25 |
| nifty50 | 0.188 | 2023-12-25 |

**The global rule's margin on smallcap250 was ZERO** -- 125 symbols against a
threshold of 125, an exact tie. It aborted on a coin-flip.

**Why the old rule misfired here.** The global median measures 26 years, most of
which smallcap250 did not exist for. (This is one of THREE consequences of the
same 36.3% -- see the build_scores entry above for the other two.) The gap between global and window median
is a measure of how much a universe's composition changed over that span:

    nifty50       43 -> 48     stable membership, tiny gap
    smallcap250  125 -> 196    the panel more than doubles in density

smallcap250's density by year: 2019 159, 2020 163, 2021 174, 2022 196,
2023 204, 2024 220, 2025 237, 2026 248.

**THE 36.3% LATE-LISTER RATE AND THIS FAILURE ARE ONE FACT.** smallcap250 is the
first universe whose composition changes enough across 2000-2026 to decouple the
global median from the era median, and the reason is already on its registry
row: 90 of 248 names did not exist at BT_START_DATE, the highest rate of the
seven. A panel that grows from 125 to 248 names has no single "normal day", and
the old threshold assumed it did.

**Verification that these are holidays and not sessions.** Union of phantom
dates across all seven universes: **237. In the NSE calendar: 0.** All 23 of the
flagged dates are **weekdays, Mon-Fri**, and all fall inside the calendar's span
(latest 2026-05-28, calendar ends 2026-06-08), so they are not a tail coverage
gap. Every one of them is partial on all seven panels at once -- 2025-12-25 runs
0.18 nifty50, 0.25 nifty100, 0.37 nifty200, 0.49 midcap150, 0.60 smallcap250. A
genuine session wrongly dropped would be near 1.00 somewhere; none is anywhere.

**PROVISIONAL UNTIL EIGHT.** n = 7, measured 2026-09-19. nifty500 is not wired.
Per the standing rule in the class entry below, this is a claim about seven
universes and not a property of the guard.

## A CLASS: a correct measurement over the set in hand, phrased as a property of the thing measured

Promoted to a class 2026-09-19, after the third instance in two days. Open as a
class -- the instances are corrected; what is open is that nothing catches the
next one, and the honest reason is below.

**The shape.** Someone measures every case available and writes down what they
all share. The measurement is correct. The sentence is not a sentence about
those cases -- it is a sentence about the mechanism, and it reads as a law. It
stays true for exactly as long as the set does not grow.

**Three instances, all within two days, two of them in the same entry:**

| claim | measured over | broke on |
|---|---|---|
| "No sign changes on any of the four" | 4 universes | midcap100: +1.0392 -> -1.2280 |
| "the cost is larger where turnover is larger" | 3 universes | midcap100: fewer lots, longer hold, twice the cost |
| "every pair clears dE2000 >= 10" | 18 slots, cross-universe only | the 5th palette search -- and 5 shipped pairs were ALREADY below it, worst 3.26 |

None was a careless number. Each was a correct measurement, and the third was
worse than the other two: it was already false when written, because it had
been measured over cross-universe pairs and stated over all pairs.

**THE DETECTOR, AND IT IS GREPPABLE.** A claim quantified over universes, arms,
slots or pairs -- "every", "all", "none", "each", "on all four", "in every
universe" -- with no statement of how many were measured. Grep the prose for
the quantifier, then look for an n beside it. No n, instance.

**AND HERE IS ITS LIMIT, STATED SO THE ENTRY DOES NOT IMPLY A SWEEP THAT
CANNOT EXIST.** That detector would have caught instance 1 and instance 3. It
would NOT have caught instance 2. "Across the THREE universes that reported,
the cost is larger where turnover is larger" **carried its count**, said three
out loud, and was still wrong -- because the defect is not a missing n. It is a
sentence shaped like a mechanism sitting where a sentence about three
observations belongs. **A grep cannot tell those apart.** Carrying the count
makes the claim auditable; it does not make it true, and an entry that implied
otherwise would be committing this class's own error about its own detector.

What closes the gap is not a checker. It is the phrasing rule below.

**THE STANDING RULE THIS IMPLIES, AND IT APPLIES TO EVERY CROSS-UNIVERSE CLAIM
IN THIS REPOSITORY.** Eight universes exist on disk as supplier folders. FIVE
are wired -- midcap150, nifty100, nifty50, midcap50, midcap100 -- and THREE are
not: nifty200, smallcap250, nifty500.

**So every cross-universe claim here is provisional until eight**, and three of
the eight can still break any of them. Any such claim MUST carry its n and its
date: "on the five universes wired as of 2026-09-19", not "on every universe".
The n is what lets the next reader see whether the set has grown since. The
date is what lets them see whether to re-measure. A claim with neither is
indistinguishable from a law, which is the whole defect.

Related: the never-wired class above. That one is about a guard that was never
called; this one is about a measurement that was called correctly and written
up as more than it was. Both survive because prose is the only place the error
lives and nothing reads prose.

## make_daily_log's cash identity does not model the tax deduction, so every taxed run ends "some days failed"

Found 2026-09-19, on midcap100's first taxed run. Open. **The numbers are
correct; the check is wrong about them.**

`results/make_daily_log.py:668` reports `reconciliation cash 1829/1836 ...
*** CHECK FAILURES ***` on all four arms of every taxed universe. The seven
mismatched days on midcap100 are not arbitrary:

```
2019-04-01  cash   +1,609.11      2024-04-01  cash +183,155.54
2021-03-31  cash  +81,069.11      2025-04-01  cash +113,226.62
2022-03-31  cash  +71,687.51      2026-04-01  cash +107,200.98
2023-03-31  cash  +66,581.61
                                  total       Rs 624,530.48
```

**They are the Section 3(9) assessment dates, and they sum to GATE 6's assessed
tax to the paisa.** The cash identity at `make_daily_log.py:82` is `opening
cash + yield + sale proceeds - purchases - fees = closing cash`. Tax is
deducted before the day's fills and is not a fee, a purchase or a sale, so on
exactly the days tax moves cash the identity is short by exactly the tax.

**IT IS UNIVERSAL, NOT A midcap100 DEFECT.** Every taxed universe shows it, and
on every one the mismatched-cash total equals its own assessed figure:

| universe | mismatched days | cash total | GATE 6 assessed |
|---|--:|--:|--:|
| midcap150 | 6 | 737,823.51 | 737,823.52 |
| midcap100 | 7 | 624,530.48 | 624,530.48 |
| nifty100 | 7 | 386,085.95 | 386,085.95 |
| nifty50 | 6 | 240,474.46 | 240,474.46 |
| midcap50 | 8 | 492,955.60 | 492,955.59 |

The day counts differ because the number of assessed financial years differs
per universe, not because the defect varies.

**THIS IS NOT A DEFECT IN THE NUMBERS, AND THAT IS WHY IT IS FILED HERE RATHER
THAN AS A CORRECTNESS BUG.** The tax is right. GATE 6 proves it independently:
`taxed equity == FY_EQUITY to a paisa` on all five, and `tax_report.reconcile`
raises rather than writing if the statement and the engine's deductions
disagree. Two checks agree the tax is correct and a third reports failure
because it was written before tax existed.

**THE DEFECT IS A CHECK THAT REPORTS FAILURE ON CORRECT BEHAVIOUR.** Every
taxed run ends `VERDICT: some days failed -- see above.` A reader who
investigates once, finds the tax, and moves on has learned that this verdict
does not mean what it says -- and the next time the cash identity breaks for a
REAL reason, it will print the same line into the same trained blindness.

**SAME SHAPE AS THE UNTRACKED `.docx`** that `.gitignore` closed in f2d20a4: a
standing exception that makes a real gate unreadable. That one was cosmetic and
cost nothing; this one sits on the only per-day arithmetic check in the
pipeline. An exception that never clears stops being read as an exception.

**Not fixed.** The fix is to give the identity a tax term -- the ledger already
knows the amount and the date, `Ledger.due_on` returns exactly the rupees
deducted before that day's fills -- but changing `make_daily_log` rewrites
every DAILY_LOG artefact on five universes, which is an artefact change and its
own commit. Named, measured, recorded.

## A CLASS: written, declared to be the fix, never wired

Found 2026-09-19, by noticing the third instance. Open as a class -- the
individual instances are fixed or recorded separately; what is open is that
nothing detects the next one.

**The shape.** A function or module is written. Its docstring states, often
forcefully, what it guards against or what it makes correct. Other prose starts
citing it as the answer to that problem. It is never called. The problem it
names then happens, in silence, and the silence is read as absence.

It is worse than no guard at all. No guard leaves the problem visible; an
unwired guard converts an open problem into a solved one in every document that
mentions it, and the mention is what the next reader finds.

**Five instances, all in this repository, all distinct in how far they got:**

1. **`naming.py`** -- written as "the single naming authority". Its only
   importers are `naming_declare_check.py:211` and
   `tax_acceptance_check.py:81`. **Two checkers, no producer.** Nothing that
   actually writes an artefact composes its name through it. Recorded in full
   further down this file; re-verified 2026-09-18.

2. **`tax.set_selection`** -- its docstring named a caller, and described the
   axis as working. `--tax on` did not charge tax at any call site on the
   published path until 9338a5b/21c6624 (2026-09-18): the axis renamed
   artefacts and charged nothing, and 36 of 40 suffixed files were
   byte-identical to their untaxed twins. Two acceptance conditions passed
   throughout, because both compared strings.

3. **`tax_util.max_holding_days`** -- written 2026-09-17 with the docstring
   "EXISTS SO A GATE CAN WATCH THE 326-DAY CEILING ... the failure mode is
   silent". **Zero call sites** until 2026-09-19. The ceiling was crossed on
   2026-09-18 -- nifty50 588 days, nifty100 443, four lots past LTCG_HOLD_DAYS
   -- and nothing said so. The routing was correct; three separate documents
   went on asserting the branch never fires. Wired as GATE 7 in `check_all.py`
   (b3a2c84), and demonstrated red before green, because the point of the
   class is that nobody had ever watched these fail.

4. **`b3a2c84`'s own subject line** -- "max_holding_days() gets a call site,
   **seven years** after the docstring promised it one." There is no seven
   years. `git log -S"def max_holding_days"` puts the function at `041bc66`,
   **2026-09-17**: it had a caller two days later. The number was carried over
   from the backtest window, 7.4 years, and turned into rhetoric.

   **This is the only instance where the false number is in the message of the
   commit that removes the others**, and that is worth saying plainly rather
   than burying. `1529bfd` deleted "a 326-day maximum with 39 days of headroom"
   from a docstring on the grounds that a number in prose has nothing computing
   it and will eventually be wrong. `b3a2c84`, the next commit, put a new one
   in its own subject. The discipline held for one commit.

   **Two days is the stronger fact anyway**, which is the part that makes the
   rhetoric not merely false but a loss: a guard unwired for the whole of its
   two-day life, and the ceiling crossed on day two. The invented number
   replaced a better true one.

   **Not amended. The history stands**, because rewriting it would remove the
   only instance of this class that is visible without reading code, and a
   force-push to hide a wrong number is a worse record than the wrong number.
   Recorded here instead.

5. **`make_chart.py`'s palette** -- the largest chart producer in the
   repository does not import `chart_colours` at all. There is no reference to
   it anywhere in the file; it hardcodes six colours at `results/make_chart.py`
   lines 284, 286, 302, 433 and 434 and draws EVERY universe in them. The
   registry field is the declared palette authority, `palette_distance.py`
   enforces it, a registry comment guaranteed its separation -- and the
   per-universe chart, which is the figure most often looked at, ignores all
   three.

   **MEASURED 2026-09-19, BECAUSE "IT PROBABLY MATCHES ONE OF THEM" IS THE
   ASSUMPTION THIS CLASS IS MADE OF.** It matches no universe's tuple:

   | universe | slotwise match | set overlap |
   |---|--:|--:|
   | nifty100 | 4 of 6 | 4 of 6 |
   | midcap150 | 2 of 6 | 2 of 6 |
   | nifty50 | 0 of 6 | 0 of 6 |
   | midcap50 | 0 of 6 | 0 of 6 |

   **It is a chimera of two of them.** v2 `#c0392b`, v1 `#2e6da4`, bh
   `#3a9d3a` and ix `#000000` are nifty100's slots 0, 1, 2 and 3; v3 `#1b9e77`
   and v4 `#e6ab02` are midcap150's slots 4 and 5. Six colours assembled from
   two different universes' searched tuples, belonging to neither.

   **So it is a SIXTH PALETTE, and `palette_distance.py` has never measured
   it** -- that script builds its line list from `REGISTRY[t].chart_colours`
   and this set is not in the registry. Measured here for the first time: its
   own internal minimum is dE 13.10 normal, **7.55 deutan** (v2 vs bh), 10.75
   protan. One pair below 10, on the chart every universe is drawn with.

   **Not scheduled and not fixed.** Changing `make_chart.py` re-renders four
   universes' published figures, which is an artefact change and its own
   decision -- recorded at the "per-universe palette" paragraph further down
   this file. What belongs here is only that the authority is unwired, which
   is the shape, and that nobody had checked what the unwired thing actually
   contains.

**THE DETECTOR, AND IT IS GREPPABLE.** The signature is: *a function whose
docstring states what it guards against, and which has no call site.* Both
halves are mechanical. For every `def` in the tree, take the name, grep the
tree for it, and subtract its own definition and its own docstring; if what
remains is empty while the docstring contains a guard verb -- exists so, must,
fails when, catches, guards, prevents, asserts -- it is an instance.

**IT WOULD CATCH INSTANCE 5.** `chart_colours` is a registry field with a
stated authority and a consumer that never reads it; the same "declared, not
imported" grep finds it. That instance was found by eye, not by the sweep,
which is the argument for writing the sweep.

**IT DOES NOT CATCH INSTANCE 4, AND NOTHING WOULD.** A commit message has no
call site to be missing; it is prose in a place no checker reads, and it is
immutable once pushed. The sweep covers instances 1-3, which are code. Instance
4 is here to mark the boundary of the detector, not to be found by it -- the
only control on a commit message is reading it before writing it.

That check does not exist yet. **This entry is the specification for it, not
the check.** The next hand can sweep for the pattern by hand in the meantime;
three instances in one tree is not a coincidence, and the third was found by
accident while diagnosing something else.

**What would close this:** the sweep above, wired into `check_all.py` with a
declared baseline count in the manner of `naming_declare_check`, so that a new
unwired guard is a growth against the baseline rather than a discovery.


## The strategy sells return to buy drawdown, and the record reports the two halves separately

Found 2026-09-11, by transcribing the live figures into tracked prose for the
first time. Open. **This is the most serious open item in this file.** It is not
about the universe retirement that surfaced it.

### The finding: one mechanism, not two results

This project has always reported a drawdown win and a return tie. They are the
same trade. Breadth scaling moves the book to cash when breadth collapses; that
is what produces the shallower drawdown, and it is the same rule that sits out
the recovery. Measured on the six best market days for nifty100:

```
date         b&h day   v2 day   capture   invested
2020-04-07    +6.73%   +0.82%     0.12x      23.1%
2019-09-20    +5.39%   +2.47%     0.46x      48.6%
2020-03-20    +5.27%   +1.32%     0.25x      21.4%
2019-05-20    +4.35%   +1.50%     0.34x      98.2%
2020-04-09    +4.35%   +0.53%     0.12x      23.9%
2026-04-08    +4.21%   +1.50%     0.36x      25.1%
mean capture 0.28x    mean invested 40.0%   (window mean 67.8%)
```

Four of the six are post-crash rebounds. The rule avoids the crash and it avoids
the recovery. Reporting those as a drawdown result and a separate return result
makes the strategy look like it wins on one axis and ties on the other, when it
is doing one thing with a cost and a benefit.

### The decomposition the record has never made

Hold the universe at the strategy's own daily invested fraction -- same cash
path, no selection -- and the halves separate:

| | CAGR% | Sharpe | MaxDD% |
|---|---:|---:|---:|
| **nifty100** buy & hold, 100% invested | 24.01 | 1.28 | -37.79 |
| nifty100 same exposure path, no selection | 18.08 | 1.49 | -19.84 |
| nifty100 strategy v2 | 24.43 | 1.72 | -18.38 |
| **midcap150** buy & hold, 100% invested | 28.36 | 1.49 | -36.54 |
| midcap150 same exposure path, no selection | 17.96 | 1.61 | -17.21 |
| midcap150 strategy v2 | 29.23 | 1.99 | -15.68 |

**The exposure rule alone captures 92.5% of nifty100's drawdown benefit and 92.7% of
midcap150's.** Selection adds 1.46 and 1.53 points of drawdown protection, against the
19.41 and 20.86 the record quotes versus a fully-invested benchmark.

**Exposure-matched, the selection edge is +6.35 and +11.27 CAGR points** -- not
the +0.43 and +0.87 the record quotes. The exposure rule spends 5.9 (nifty100) and
10.4 (midcap150) of those points to buy roughly 18 and 19 points of drawdown reduction.

Against a fully-invested benchmark those two effects nearly cancel on return and
stack on drawdown, which is precisely why the published comparison reads the way
it does.

### The exposure-matched edge, with its null and its noise

**+6.35 and +11.27 are the largest numbers in this record, so they get the same
treatment as everything else in it.** Both controls below are computable from
artefacts already on disk.

**The null.** The shuffle permutes scores while holding every mechanic fixed, and
`shuffle_draws.csv` shows `Deployed%` is **identical across all 100 draws** --
sd 0.0000, one unique value, both universes. Exposure really is score-independent,
so the exposure-matched benchmark is the same constant under every draw and the
null distribution of the matched edge is the null CAGR distribution shifted:

| | real edge | null median | null p95 | null max | null sd | draws beating | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| nifty100 | **+6.35** | −6.65 | −2.89 | +1.57 | 2.50 | 0 of 100 | 0.0099 |
| midcap150 | **+11.27** | −6.72 | −1.68 | +4.06 | 2.88 | 0 of 100 | 0.0099 |

The real edge is 4.0x and 2.8x the best of 100 random-selection draws, and 5.2
and 6.2 null standard deviations above the null median.

**THIS IS NOT A SECOND, INDEPENDENT CONTROL, AND MUST NOT BE READ AS ONE.**
Because the benchmark is constant across draws, subtracting it does not change
the ordering of the draws -- so this test is ARITHMETICALLY THE SAME TEST as the
raw CAGR shuffle above, re-expressed in matched units. It inherits every defect
of that test without exception: p is at the 1/101 floor rather than measured, the
configuration was chosen after at least 26 trials on this data so multiplicity is
untreated, and the run that produced it had 36 uncommitted files. What the
matched form adds is a readable effect size, not additional evidence.

**The seed noise.** The 1.07 and 1.01 figures are the sd of v2's CAGR, which is
the numerator of the matched edge. The benchmark is built from the strategy's
realised invested path; the breadth MULTIPLIER is provably seed-independent (see
the Deployed% result above), but the realised path depends on which names are
held and so is not exactly seed-invariant. Under the assumption that the
benchmark does not move with the seeds:

| universe | matched edge | sd(CAGR) at K=10 | edge in sigma |
|---|---:|---:|---:|
| nifty100 | +6.35 | 1.07 | **5.9** |
| midcap150 | +11.27 | 1.01 | **11.2** |

**That assumption is not verified and cannot be, from what survives.** The
per-seed stores (`results/SEEDNOISE_*.npy`) were never tracked and are gone, so
the matched edge's sigma cannot be computed directly. Settling it means re-running
the 40-seed study and recording the matched edge per sub-ensemble, which has not
been done.

**Status, stated plainly: measured, controlled against random selection at the
test's floor, and NOT controlled for multiplicity, for the benchmark's own
construction, or for seed variation in the benchmark.** It is a larger and better
identified effect than the +0.43, not an established one.

### This table is not a recommendation

It does not say to remove the breadth rule. **Removing it is v1, and v1's numbers
are already known:** CAGR 30.56 and 50.12, at MaxDD -31.92 and -35.88, against
buy & hold's -37.79 and -36.54. That is the same trade priced the other way --
more return, nearly all of the drawdown back.

What the table establishes is that the trade is **visible and priced**, which is a
different statement from saying it is mispriced. Whether 5.9 CAGR points on nifty100
and 10.4 on midcap150 is a fair price for roughly 18 and 19 points of drawdown
reduction is a decision about risk appetite, not a defect. Nobody has been in a
position to make that decision before, because the two halves were never reported
together.

A reader six months from now should find the price here, not an instruction.

### Two controls on the drawdown side, by different constructions

**1. The shuffle test** (`diagnostics/shuffle_verdict.txt`): scores permuted,
every mechanic including exposure held identical.

```
            realDD   nullDD med   p(DD)   deploy%
n100  v1    -31.92      -38.71   0.0693    100.0
mid   v1    -35.88      -39.27   0.2673    100.0
n100  v2    -18.38      -20.12   0.3564     56.6
mid   v2    -15.68      -19.29   0.1188     56.6
```

**TWO MEASURED FACTS ABOUT THAT TABLE, recorded because they are easy to lose and
neither is a finding.**

**First: `nifty100 v1`'s p(DD) = 0.0693 is the only shuffle statistic in this project
that is not pinned at the test's floor.** Every CAGR p here reads 0.0099, which is
`(1 + 0)/(100 + 1)` exactly -- the floor, carrying no information about magnitude.
0.0693 means six draws of a hundred beat it. It is a measured p-value rather than a
bound, and it is still above any conventional bar.

**Second: the ordering inverts between the arms.** On v1, at 100% deployment, nifty100
is the stronger universe (0.0693 against midcap150's 0.2673). On v2, with breadth
scaling on, midcap150 is (0.1188 against nifty100's 0.3564). The two arms cannot both be
cited as pointing the same way, and neither ordering should be carried forward as
a property of either universe: MaxDD is a single-episode statistic, and on both
universes that episode is the same one -- the COVID trough of 2020-03-23.

Random selection through the same breadth rule reproduces **91% of nifty100's
drawdown advantage and 83% of midcap150's**. The drawdown result is not significant
against the null that controls for exposure, on either universe. The spec
predicted this in advance -- *"exposure is score-independent"* -- and the file
records *"the prediction is BORNE OUT"* on both.

**2. The exposure-matched benchmark above**, which reaches 92.5% and 92.7%.

Unlike the return case -- where subtracting a constant benchmark leaves the
shuffle test arithmetically unchanged -- these two genuinely differ in
construction: one replaces the selection with random names at the same exposure,
the other removes selection entirely by holding the whole universe at that
exposure. MaxDD is not linear in the return path, so neither reduces to the other.
They are two methods agreeing, not two independent samples of evidence.

### The comparison this project has never run

There is no exposure-matched comparison anywhere in the record. Not in code, not
in prose, not in any artefact: no return per rupee deployed, no benchmark held at
the strategy's exposure, no normalisation of any kind. `Deployed%` is printed as
a column in every comparison table and never used as a denominator. **The only
place deployment is held constant is inside the shuffle null**, where it compares
the strategy against itself.

The record has also never stated the drawdown benefit and the return cost as one
mechanism. The closest it comes is the shuffle's own note -- *"the breadth arms
deploy about 57% while buy & hold is 100% invested, so a breadth arm below buy &
hold on CAGR is not evidence of anything on its own"* -- which identifies the
mismatch on the return side only and then declines to draw the conclusion.

**So the question the record should be asking, and does not, is whether the trade
is priced correctly**: selection earns 6 to 11 CAGR points, the exposure rule
spends most of them, and what it buys is drawdown reduction that mostly does not
require the selection at all. "Is the edge significant against a fully-invested
benchmark" is the wrong question, because that comparison is mismatched on
exposure in both directions at once.

### Why the headline +0.43 does not resolve, for three independent reasons

**1. Seed noise.** From `diagnostics/seed_noise.txt` section 1, at the shipped
K=10, measured on the current engine:

| universe | edge vs b&h | sd(CAGR) at K=10 | edge in sigma |
|---|---:|---:|---:|
| nifty100 v2 | +0.43 | 1.07 | **0.40** |
| midcap150 v2 | +0.89 | 1.01 | **0.88** |

Changing nothing but the random seeds moves the result by more than the entire
claimed edge.

**2. The benchmark's own instability, and it differs by universe.**

- **midcap150: the denominator is contaminated.** Six single-day moves above 55% sit
  inside the window -- MEDANTA +548.8%, 360ONE +464.1%, PATANJALI +413.6%,
  SBICARD +109.6% and two more. Buy & hold reads 28.34% as computed and 24.23%
  with those six days neutralised, so the same edge is +0.89 or +5.0 depending on
  a data-handling choice nobody has made.
  **CORRECTED 2026-09-13: 24.23% is wrong. Measured against current data the
  neutralised benchmark is 27.84%, the range is 0.50 points rather than 4.11, and
  the edge is +0.89 or +1.39 -- not +5.0. Four of the five moves are price holes
  rather than single-day moves and three never reach the benchmark at all. See
  "The midcap150 benchmark is better defined than this file said, and the edge is
  worse" below. The correction makes the return case weaker.** This is not a claim that the edge is 5
  points -- survivorship pulls the other way -- it is that the denominator is not
  defined to better than about 4 points.
- **nifty100: zero moves above 55%, and a different problem.** Its six largest days
  are real. But removing them symmetrically moves the edge from +0.43 to +3.92, a
  factor of nine, because the strategy captures them at 0.28x while the benchmark
  takes them in full. Six days out of 1,836 move the estimate by eleven times the
  quantity being claimed.

**3. Nothing is attributable to a commit.** Of the 65 artefacts in this project
that record their git state, **65 were produced with a dirty working tree** --
one batch of 44 on top of a commit with 117 modified or untracked files. The
identity gates confirm the outputs agree with what ships; they say nothing about
which source produced them. This applies to every figure in this entry, including
the shuffle p-values below.

### What the shuffle does and does not establish

Against **random selection**, the shuffle gates CAGR at p = 0.0099 on v1 and v2,
both universes. Two things must be read with that number.

**It is the test's floor, not a measurement.** `shuffle_params.json` records
`n_shuffles: 100`, and the p-value is `(1 + beat) / (len + 1)`. With `beat = 0`
that is 1/101 = 0.009901 exactly. The correct reading is **"no draw in 100 beat
it"**; the test cannot express anything smaller.

**And the floor is not the defect -- multiplicity is.** `shuffle_verdict.txt`
states the configuration was chosen after at least 26 recorded trials on this
same data. A shuffle run afterwards is not testing that selection; it is testing
the winner on the data it won on. Raising N lowers the floor and does not touch
the bias: a p of 0.0001 obtained the same way would carry the identical defect.
**The remedy is held-out data, or a pre-registered configuration tested once --
not more shuffles.** The file says as much itself: *"IT DOES NOT CORRECT FOR THE
TRIAL DENOMINATOR. A small p here is NOT the probability that the strategy is
noise."*

### Two benchmarks, not a contradiction

These answer different questions against different nulls, and both are true:

- **Against random selection** (shuffle): p at the floor on both gated arms.
  **The selection carries information.** That is a low bar, and the test's own
  caveats -- trial denominator, survivorship, tradability -- all still apply.
- **Against buy & hold** (the economically meaningful comparison): +0.43 and
  +0.89, at 0.40 and 0.88 sigma of seed noise, against a denominator that is
  itself unstable by several points. **The magnitude is not resolvable.**
  **That denominator is `diagnostics/seed_noise.txt`, which is the weakest-cleared
  of the fifteen artefacts checked for profile contamination on 2026-09-13** -- the
  only one of the fifteen cleared by inference rather than by an identity gate
  reproducing the research baseline exactly. See *"seed_noise.txt is the weakest of
  the fifteen clearances, and it is the sigma's denominator"* below. The sigma
  should not be quoted as firmer than that chain.

Beating a random-selection null while being unable to measure how far you beat
buy & hold are compatible statements. The record currently reports only the
second, and only its point estimate.

### Realised invested capital, labelled

Mean of daily `invested_pct` for v2 over 1,836 days: **nifty100 67.8%, midcap150 61.1%**;
medians **67.4%** and **64.5%**. This is *not* the `Deployed%` column of
`v34_comparison.csv` (56.6% and 54.1%), which is the mean breadth exposure
multiplier. Two different quantities, and they must not be conflated -- the
exposure-matched rows above use the realised figure.

### The floor that was invented is still printed as fact

The 0.5-point noise floor that `seed_noise_measure.py`'s docstring calls
*"INVENTED, not measured"* is still asserted in program output, in three code
sites, and has propagated into five tracked artefacts:

```
results/engine_core.py:711     comment  "retraining shifts it by +/-0.5% run to run"
results/engine_core.py:717     print    "(CAGR varies +/-0.5% per retrain -- not checked)"
results/validate_engine.py:227 print    "CAGR is not checked -- it moves +/-0.5% per refit"
validate_sizing.py:177         print    "(CAGR varies +/-0.5% per retrain -- not checked)"

diagnostics/validate_engine_{58,mid,n100}.txt    diagnostics/validate_sizing_{mid,n100}.txt
```

The measured value is 1.07 and 1.01 -- roughly twice the asserted one. Every
comparison judged against +/-0.5 (purge, buffer, TOP_N, EWMA, sizing, cadence)
was judged against half the real bar. Not corrected here: correcting the prints
without re-running what they gated would replace one unexamined number with
another.

### What would settle it

Nothing in this entry is fixed. In order of what it would take:

1. Report every headline comparison **exposure-matched**, and state the trade
   explicitly: what selection earns, what the exposure rule spends, what it buys.
2. Test on **held-out data or a pre-registered configuration** -- the only
   remedy for the trial denominator.
3. Re-run the 40-seed study whenever the engine changes, quote intervals rather
   than point estimates, and record the EXPOSURE-MATCHED edge per sub-ensemble --
   without it, the 5.9 and 11.2 sigma above rest on an unverified assumption that
   the benchmark does not move with the seeds.
4. Decide the midcap150 benchmark's data-handling question (truncate or stitch a
   symbol's history across a corporate event of that size) rather than leaving
   the denominator undefined.

## Universe.year_range has a reader and no setter

Found 2026-09-11 during the 58/74 retirement. Open, and deliberately not fixed in
that pass.

`universes/registry.Universe.window()` branches on `year_range`:

```python
if self.year_range is not None:
    y0, y1 = self.year_range
    return index[(index.year >= y0) & (index.year <= y1)]
d0, d1 = self.date_range
return index[(index >= d0) & (index <= d1)]
```

The only two universes that ever set `year_range` were the 58 (2019–2026) and the
74 (2019–2025). Both were deleted on 2026-09-11. **Every remaining universe
constructs with `year_range=None`, so the first branch is unreachable and every
run silently takes the date cut** — which is correct, and which nobody currently
chooses.

**THIS IS NOT THE SAME AS THE `frozen` FLAG DELETED IN THE SAME PASS, AND THE
DIFFERENCE IS THE POINT.** `frozen` was dead: it had no reader left once its call
sites went. `year_range` is **live** — `window()` reads it on every panel
construction, for every universe, on every run. An axis with a reader and no
setter is not dead code; it is a default nobody chose, sitting in the path of
every run, which is precisely the defect class the retirement pass existed to
remove. It was left because removing it was outside that pass's scope, not
because it is benign.

Note also that the two cuts are not equivalent: the year cut ran **six trading
days longer** than the date cut. Anything comparing a pre-retirement figure
against a current one is comparing across that difference.

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
| ~10 module docstrings, e.g. `results/engine_core.py:113`, `results/make_trading_calendar.py:29` [FILE DELETED 2026-09-11, commit `2fe48ff` -- the line number points into a file that is no longer in the tree], `results/validate_breadth_live.py:52-53` | `python3 results/<script>.py` | unverified; each fails the same way if the venv is not active |

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
move nifty100 v2 CAGR by 0.66 points — see *"The headline is not reproducible from
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

**THERE IS NO FETCH SCRIPT.** The only downloader in the project,
`results/extract_membership.py`, retrieves NSE press releases for the survivorship
work — not prices. Nothing records how to obtain the OHLCV data again or what "the
backup archive" is, so if it is lost it cannot be re-acquired from this repository.

**BUT THERE IS A NAMED SOURCE, CORRECTED 2026-09-13.** This paragraph said "no
named source" and cited the vendor as `source=kite`. **There are three vendors —
`dhan`, `kite` and `upstox` — mixed within single files**, alongside `exchange`,
`product_class`, `_window*`, `_dq_score`, `_gap_filled` and `_merged_at`. They
indicate a pre-processed private extract rather than a public download, which was
the correct reading; the vendor count and the existence of a source were not.

**The merge vintages differ by universe:** midcap150 `2026-08-11`, nifty100 `2026-07-20`,
N100_Survivorship `2026-07-23` and `2026-07-30`. **The two live universes' prices
were extracted three weeks apart**, and no result in this project states it. See
`docs/HANDOFF.md` section 3, corrected in the same pass. What is genuinely missing
is a licence, a fetch script, and any prose describing these columns.

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

**`results/make_trading_calendar.py` WAS DELETED ON 2026-09-11, commit `2fe48ff`,
with the 58 universe it read. The line number above points into a file that is no
longer in the tree.** The entry is kept unedited below because it records why the
calendar is shaped the way it is, and that reasoning is still load-bearing: the
file it describes writing is still tracked and still read on every panel build.

so the NSE trading calendar is derived from the **retired 58 universe's** raw
files. It writes `data/nse_trading_calendar.csv`, and
`engine_core._load_calendar()` raises `FileNotFoundError` if that artefact is
absent — **for every universe, including midcap150 and nifty100**.

The calendar exists for a measured reason: 70 of 148 MidCap150 source files carry
rows on NSE holidays, putting 237 phantom dates into the midcap150 union index, 107 of
them inside the backtest window. Deriving the calendar from midcap150 itself is
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
instead — was measured against nifty100. `SOURCE_DIR` was pointed at the nifty100 raw
data, a second calendar was built to a scratch path, and it was compared against
the tracked 58-derived artefact over the shared range. **The tracked artefact was
not written**: SHA256 `9ce2a4bd…f96f0` before and after.

    shared range 2000-01-03 .. 2026-06-08
    n100-derived    6,811 dates
    tracked-58      6,574 dates
    n100-only         237
    tracked-58-only     0

**THEY ARE NOT IDENTICAL, AND THE DIRECTION IS ONE-WAY.** The nifty100-derived
calendar carries **237 dates the 58-derived one does not**, and **not one** date
goes the other way. **107 of the 237 fall inside the 2019-01-01 to 2026-05-29
backtest window.** They span 2009 to 2026, 8 to 18 per year, every year, and none
is a weekend. Measured on both readings of "the nifty100 data" — the 100-file
benchmark directory and the 99-file constituents directory that
`build_scores_n100.py` actually scores — which agree with each other on all 237.

**NOTED WITHOUT BEING TESTED: THE 58 MAY BE ACTING AS A FILTER RATHER THAN MERELY
AS A SOURCE.** `results/make_trading_calendar.py`'s own docstring -- the file was
deleted 2026-09-11, commit `2fe48ff`, so the docstring is quoted here from before
that and cannot now be re-read in the tree -- reports the same
two counts for MidCap150 — *"237 phantom dates into the mid union index (107
inside the backtest window)"* — and calls them phantom. The nifty100 comparison
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
range the files cover, nifty100 comes out **2 dates short** and midcap150 **22 dates short** —
all pre-2019, all one-directional, the filter dropping dates the calendar has.

**No threshold can fix it.** A threshold T reproduces the calendar only if
`max(coverage of excluded dates) < T ≤ min(coverage of included dates)`. Measured
over the full range that requires `24.24% < T ≤ 13.85%` on nifty100 and
`47.30% < T ≤ 4.35%` on midcap150. **Both intervals are empty**; the groups overlap by
10.40 and 42.95 points. The binding cases are calendar dates with very thin
coverage — 2017-12-02 (Sat, 4.35% on midcap150), 2003-03-22 (Sat, 13.85% / 4.92%),
2017-04-04 (Tue, 33.33% / 37.39%), and eighteen consecutive January 2003 sessions
at 47.54% on midcap150.

**It would have moved published numbers.** The missing dates are pre-2019 and so
are training rows rather than scored rows, but `build_panel` filters the whole
panel and training reaches back to 2001. `experiments/EXPERIMENTS.md` entry 28
measured a 0.01% training-row change moving nifty100 v2 CAGR by 0.54 points.

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

| | 58 (retired) | midcap150 | nifty100 |
|---|---|---|---|
| shipping engine, 2026-09-04 | **4 of 4** | **0 of 4** | **4 of 4** |
| mean book / trades | 8.15 / 734 | 7.98 / 845 | 8.01 / 831 |
| Sharpe, equal → invvol | 1.24 → 1.24 | 1.87 → **1.81** | 1.45 → 1.62 |

midcap150 goes from "1 of 4" on the validation engine to **0 of 4** on the engine that
ships, and each of the four fails for its own reason rather than from one common
cause — T1 by 0.02 on mean book (7.98 against a [8, 16] range), T2 on 0 of 3 seed
sets, T3 in the 2019-2022 half, T4 on the vol window. The Sharpe column says why:
**on midcap150, inverse-vol does not beat equal-rupee** — 1.87 → 1.81 — so the tests
that ask "does inverse-vol still win" correctly answer no. Corroborated
independently on 2026-09-05: an equal-weight arm run through `run.py` on midcap150
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

## No component owns which axes an artefact carries, and that has now produced three defects

Found 2026-09-15, by fixing the participation-cap contract and watching a
`tradeable` run die one step further along for an unrelated reason. Open, and
DELIBERATELY NOT FIXED -- see the last section. **This is one design conclusion,
not three bugs, and the three below are symptoms of it.**

### The conclusion

An artefact's name is composed from three axes -- arm, cadence, profile -- each
unsuffixed at its default. `naming.py` exists as "the single naming authority" and
its own docstring records why: the same bug appeared on the cadence axis, then the
arm axis, then the profile axis, each fixed at its own call site, "so each new axis
re-opened the same hole somewhere else."

**IT IS NOT A MISSING AUTHORITY. IT IS AN UNADOPTED ONE.** `naming.py` is written,
it declares itself the fix, and **no module in the live tree imports it** --
verified 2026-09-15. Every writer, reader and guard retypes the composition, and
`run_all._present()` retypes it as `f.stem + _cd.suffix() + _pf.suffix()`. Every
entry in this file that points at `naming.py` as the eventual solution has been
pointing at a file nobody calls.

**MEASURED 2026-09-18: TEN EXECUTABLE SITES, NOT THIRTEEN.** An earlier count of
thirteen included three that are PROSE -- `run_all.py:447`,
`check_pipeline_order.py:118` and `v34_common.py:178` are comments describing the
composition, not performing it. Excluding those, ten places compose a chain in
executable code, and `naming.py`'s adoption cost is not uniform across them:

| | sites | adoption |
|---|--:|---|
| drop-in `tail()` or `tail(subset)` | **8** | one call each; several also shed a redundant `is_default()` guard, because a default suffix is already `""` |
| needs `tail()` to grow a parameter | **1** | `make_chart.py:161` |
| not a site at all | **1** | `run_all.py:782` |

**`make_chart.py:161` CANNOT ADOPT AS `tail()` STANDS**, and the reason is not
laziness at that call site. Its arm term is
`arm_reg.suffix(arms_on) if set(arms_on) != {"v2", "v1"} else ""` -- the arm value
comes from a **passed-in `arms_on` set**, not from the run's global selection that
`tail()`'s arm term reads, and it carries a **canonical-pair exemption** giving
`{v2, v1}` a bare name. `tail()` takes an axes SUBSET; it takes neither an arm
value nor a per-axis override. Adoption here is an API change, not an edit.

**`run_all.py:782` IS BOUNDED BY DECLARATION, NOT UNDER-SPECIFIED.** It composes
only the axes an entry DECLARES, and every live entry declares
`CADENCE_PROFILE = "cadence,profile"`; `naming.AXES` appears there only inside a
commented-out example. It omits tax because nothing it resolves carries tax. It is
not a fourth instance and should not be counted as one.

**WHY THIS ENTRY HAS NOT MOVED: IT HOLDS TWO PROBLEMS AND THEY HAVE BEEN
SCHEDULED AS ONE.**

- **The retyped chain** -- instance 6 of the class entry below, four instances
  measured, the fourth fixed 2026-09-18 at `arm_sources.py`. **Adoption fixes
  this**, for eight sites immediately and a ninth after the API change.
- **The guard side** -- which axes an ARTEFACT carries, as opposed to which a
  COMPOSER can express. **Adoption does not touch this at all.** A tree where
  every site calls `tail()` still leaves `_present()` free to decide, wrongly,
  that a score panel carries a profile, which `run_all.py` records having done.

Two problems, one file, and every previous plan has required both before either
ships. **That is why neither has.** They are separable: the eight drop-in sites
can adopt without any per-artefact work, and the per-artefact register can be
written without waiting for adoption. NOT SCHEDULED HERE -- recorded so the next
reader does not re-derive the coupling and conclude, again, that it is one job.

Re-verified 2026-09-18: the only importers of `naming` remain
`naming_declare_check.py:211` and `tax_acceptance_check.py:81`. **Two checkers, no
producer** -- the same shape `tax.set_selection`'s docstring had when it claimed a
caller in `run.py` that did not exist.

**AND ADOPTING IT AS IT STANDS WOULD NOT HAVE PREVENTED DEFECT 3.** `naming.CARRIES`
registers which axes a COMPOSER can express; nothing records which axes an ARTEFACT
carries. So the naming work is two pieces, in this order: **extend `naming.py` to
record per-artefact axes, then adopt it at every writer, reader and guard.**
Adoption alone would standardise the composition and leave the guard still free to
decide, wrongly, that a score panel carries a profile.

**AND THE AUTHORITY WOULD NOT SETTLE THIS EVEN IF ADOPTED.** `naming.CARRIES`
registers which axes a COMPOSER can express -- `_c(` carries cadence and profile,
`selection_suffix` carries arm. It says nothing about which axes an ARTEFACT
carries. That is the missing fact. A score panel carries none of the three; a
daily trail carries all three; `v2FINAL_equity.csv` carries cadence and profile but
not arm, because the arms are columns. **Nothing anywhere records this**, so each
writer, reader and guard decides separately, and they disagree.

### The three defects it has produced

**1. CADENCE -- a reader disagreed with a writer.** `audit_step._reference_curve`
resolved to the canonical cadence-20 curve under `--rebal 40`, reconciling a
cadence-40 trail against it: measured, v1 MISMATCH Rs 2,923,934 and v2 MISMATCH
Rs 1,825,210 on midcap150. Fixed at that call site by appending `cadence.suffix()`.

**2. PROFILE -- a guard disagreed with a writer.** `f6b970b` (2026-09-12) made the
engines and charts profile-aware while `check_inputs` did not, so a research file
left on disk satisfied the guard during a `tradeable` run. Fixed at that call site
by `_present()`, which demands "exactly the name this run's axes produce".

**3. PROFILE AGAIN, IN THE OPPOSITE DIRECTION -- the guard now over-applies it.**
`_present()` appends the profile suffix to EVERY entry in `REQUIRED_INPUTS`,
including the score panel:

```
nt_export_scores.py needs 1 file(s) that do not exist:
  MISSING  results_mid/metrics/v_mid_expanding_cache_tradeable.csv
    present in that directory: v_mid_expanding_cache.csv
```

**The score panel has no profile dimension.** Scoring runs before any trading, the
participation cap acts only on fills, and the two profiles' panels are
byte-identical. The guard is asking for a file that should not exist, and the fix
at its own call site -- a special case for the score panel -- would create a FOURTH
place that knows which artefacts carry a profile dimension. That is the disease,
not the cure.

### What this blocks right now

**`--profile tradeable` reconciles and does not complete, and those are different
statements.** Since `bc75d66` the audit replays the capped strategy correctly and
all four midcap150 arms MATCH the engine to under a paisa. The run proceeds through
STEP 10b, 10c, 10d, 12b, 15 and 15b, writing every artefact including midcap150's
tradeable audit trail -- and then dies at **STEP 16** on the name above.

**Nobody should read the cap entry and conclude the profile runs end to end.** It
does not. What was fixed there was the measurement; what remains here is the name.

### The blocker is closed. The authority it was an argument for is not.

**UPDATE 2026-09-16.** `--profile tradeable` completes: `--universe midcap150 --arm v2
--profile tradeable` runs all nine steps, exit 0, and `--universe midcap150 --arm v3
--rebal 200` does the same on the cadence axis. Instance 3 above was right about
the cause — the guard over-applies — and the scope was fixed rather than the cache:
every `REQUIRED_INPUTS` entry now declares which axes its name carries, the fourth
field is compulsory with no default, and `_present()` composes only what is
declared. The score panel's `axis-free` classification is measured, not assumed;
see instance eight below for the two measurements.

**COMPLETING IS NOT BEING VALIDATED.** STEP 16 and STEP 17 have now RUN under the
tradeable profile for the first time. Nothing yet measures whether what they
produced is correct, and no gate cell covers it.

**AND THIS ENTRY'S OWN WARNING STILL STANDS, PARTLY AGAINST THE FIX.** It says a
special case at the call site "would create a FOURTH place that knows which
artefacts carry a profile dimension. That is the disease, not the cure." The fix is
not a special case — every entry declares, uniformly — but the declaration lives at
the READER and restates what the WRITER already says: `build_scores_step` carries
`# naming: axis-free` and `audit_step` carries `# naming: arm,cadence,profile via
artefact_tag`. Two copies of one fact, which can drift.

**SO THE SINGLE AUTHORITY IS STILL OWED, AND THE NEXT STEP IS NOW SMALLER AND
CHECKABLE:** `naming_declare_check` already reads every writer's `# naming:`
directive and already measures what a composer carries. Making it cross-check the
guard's fourth field against the producing writer's directive would turn the two
copies into one claim and one verification, without a fourth decider. That is the
work; it is not done.

### The sequencing that was decided, and how it turned out

Deliberately parked until after the collapse (steps 4-8), by explicit decision on
2026-09-15. Three instances of one missing authority is a design conclusion, and
patching the third at its call site would add the fourth place that decides
independently -- repeating exactly what `naming.py`'s docstring says caused the
first three.

The work is to give artefacts a declared axis set that writers, readers and guards
all read. It is sequenced after the collapse because the collapse takes the
per-universe module pairs from ten files to four: **there will be four composers to
teach instead of ten.** Doing it first means teaching six modules that are about to
be deleted.

---
## The tradeable profile could not complete a run -- first because the audit disagreed with the engine, then because a guard asked for a file that cannot exist (CLOSED 2026-09-16)

Found 2026-09-15, by enumerating the cells a step-6 gate would need and running
each one instead of reasoning about it. Open. **Every gate this project has run
used the research profile**, which is why a whole profile has been unrunnable for
at least two days without anyone noticing.

### What breaks

`--profile tradeable` exits 1 on both universes, and both failures trace to one
absent file:

```
mid   dies at STEP 10d  make_mid_chart.py needs 1 file(s) that do not exist:
                          MISSING results_mid/metrics/daily_trades_mid_tradeable.csv
                          writer STEP 10c make_mid_audit.py
n100  dies at STEP 12b  make_combined_universes.py needs the SAME file --
                          results_MID_/metrics/daily_trades_mid_tradeable.csv
```

nifty100 completes all eight of its own steps and dies on **midcap150's** missing file,
because STEP 12b is cross-universe. One universe's defect makes the profile
unrunnable for both.

**THE MISSING FILE IS A SYMPTOM, NOT THE DEFECT.** `make_mid_audit` runs, and
refuses to write its trail, because its replay does not reproduce the engine's
curve:

```
mid / v1   v1 equity vs the engine's recorded curve : *** MISMATCH Rs 3,851,027.09 ***
mid        v2 equity vs the engine's recorded curve : *** MISMATCH Rs   605,030.57 ***
mid / v3   v3 equity vs the engine's recorded curve : *** MISMATCH Rs 3,510,367.57 ***
mid / v4   v4 equity vs the engine's recorded curve : *** MISMATCH Rs   958,629.05 ***
           !! audit logging changed something -- do not go further
```

The guard is doing its job. **The defect is that the audit replay and the engine
disagree about what the participation cap does**, by up to Rs 3.85M on a Rs 16.4M
final equity -- 23% of the terminal value on v1.

### It is specific to where the cap binds, and that is only midcap150

Measured the same day, all four arms, same command shape:

| cell | audit verdict |
|---|---|
| midcap150, research | **MATCH on all four arms**, trades reconcile (852 / 1,019 / 822 / --) |
| nifty100, tradeable | **MATCH on all four arms**, trades reconcile (795 / 965 / 754 / 967) |
| **midcap150, tradeable** | **MISMATCH on all four arms** |

nifty100 passes under tradeable for the reason this file already records elsewhere:
**the participation cap never binds on nifty100**, so a tradeable run there reproduces
the research run exactly and the audit is certifying a configuration the cap did
not touch. midcap150 is the universe where the cap binds, and it is the one where the
replay diverges. **The two facts are the same fact.**

It predates the invocation-contract work: reproduced at `67a644d` on 2026-09-13,
where nifty100 tradeable dies at STEP 12b on the identical missing midcap150 file.

### What is and is not recoverable -- correcting an earlier count

**An earlier statement in this session that 47 tradeable artefacts on disk "are
not reproducible by anything runnable" was wrong, and wrong in the direction that
matters.** It was inferred from the exit code rather than from what the run wrote.
Measured:

| | tradeable artefacts on disk | reproduced by the failing run |
|---|---:|---:|
| midcap150 | 11 | **11** |
| nifty100 | 36 | **36** |

**All 47 regenerate.** The engine writes `v34_*_tradeable` and `v2FINAL_*_tradeable`
at STEP 10b/10f, well before the step that dies. What a tradeable run cannot
produce is **a completed run** -- no run folder, no `RUN.txt`, no combined chart --
and, on midcap150, **no audit trail at all**, which is the thing that would certify the
figures rather than merely restate them.

### Every tracked citation of a tradeable number, and all of them reproduce

`KNOWN_ISSUES.md` is the only tracked document that cites tradeable figures. The
other files that contain the word use it in the unrelated liquidity sense
("untradeable names", `README.md:238`, `experiments/EXPERIMENTS.md:1607,1710,1933`)
or describe the profile without quoting it (`docs/HANDOFF.md:260`,
`nautilus/NAUTILUS_STATUS.md:198`). No `experiments/*_PREREG.txt` cites one.

| citation | figures | reproduced 2026-09-15 |
|---|---|---|
| `KNOWN_ISSUES.md:2968` | midcap150 v1 tradeable **45.90**, MaxDD −35.88, 860 trades, TC 692,730 | **exact** |
| `KNOWN_ISSUES.md:2970` | midcap150 v2 tradeable **27.59**, MaxDD −15.68, 1,019 trades, TC 228,963 | **exact** |
| `KNOWN_ISSUES.md:3011` | the same four, attributed to the snapshot | **exact** |
| `KNOWN_ISSUES.md:2952-2955` | nifty100 tradeable = research: 30.56 / 24.43 / 23.14 / 21.36, b&h 24.00 | **exact**, and byte-identical to the research file as recorded |

So **no published figure is unreproducible**, and the refactor is not blocked.
What the profile cannot give is the *audit* of those figures -- and on midcap150 the
audit does not merely go missing, it disagrees with the engine by Rs 3.85M.

**This sharpens the existing item** *"The universe where the cap binds is the one
with no tradeable audit trail"* rather than replacing it. That entry says midcap150's
shipping arm "has never been audited at all" on the tradeable profile and calls
the figures UNRECONCILED. This one says why: the audit has been run, and it does
not reconcile.

### RESOLVED 2026-09-15, and the four cited figures are CONFIRMED

The cause was `audit_step` passing `participation_cap` without the `vol20` the cap
is computed against, so its replay ran uncapped. It now builds `vol20` by the same
expression the engines use. All four midcap150 arms reconcile under `tradeable`:

```
mid / v1   MATCH    trades logged   860  (engine reported   860)  OK
mid        v2       MATCH           1,019 (engine reported 1,019) OK
mid / v3   MATCH    trades logged   828  (engine reported   828)  OK
mid / v4   MATCH    trades logged 1,019  (engine reported 1,019)  OK
```

**No figure moved, so there is no old value to keep as record.** What changed is
what stands behind them: the numbers below were the engine agreeing with itself,
and they now have an independent replay -- a second implementation, logging every
fill -- reconciling to under a paisa and to the trade.

| citation | figure | disposition |
|---|---|---|
| `KNOWN_ISSUES.md:2968` | midcap150 v1 tradeable 45.90, −35.88, 860, TC 692,730 | **CONFIRMED** |
| `KNOWN_ISSUES.md:2970` | midcap150 v2 tradeable 27.59, −15.68, 1,019, TC 228,963 | **CONFIRMED** |
| `KNOWN_ISSUES.md:3011` | the same four, attributed to the snapshot | **CONFIRMED** |
| `KNOWN_ISSUES.md:2952` | nifty100 tradeable = research, 30.56 / 24.43 / 23.14 / 21.36 | **CONFIRMED**, unchanged |

**THE ITEM ABOVE IS NOW ANSWERED.** It said midcap150's shipping arm "has never been
audited at all" on the tradeable profile and called the figures UNRECONCILED. They
are reconciled, and midcap150's tradeable trail exists for the first time.

**THIS IS THE FIRST CAP-BINDING REPLAY IN THE PROJECT'S LIFE.** Not the first
tradeable audit that passed -- nifty100's passed, and passed for as long as the profile
has existed -- but the first time any configuration where the participation cap
ACTUALLY BINDS has been independently replayed and reconciled. nifty100's cap never
binds, so its green audit certified a run the cap did not touch; midcap150's is the only
cap that bites, and until 2026-09-15 midcap150's audit was silently uncapped. **Every
cap-binding number this project has ever published rested on the engine agreeing
with itself.** `midcap150 v1 tradeable` and `midcap150 v2 tradeable` are standing gate cells so
that cannot recur.

**THE PROFILE STILL CANNOT COMPLETE, FOR A DIFFERENT AND SMALLER REASON.** It now
runs through STEP 15b and dies at STEP 16:

```
nt_export_scores.py needs 1 file(s) that do not exist:
  MISSING  results_mid/metrics/v_mid_expanding_cache_tradeable.csv
    present in that directory: v_mid_expanding_cache.csv
```

`run_all._present()` -- a documented stopgap from 2026-09-12 -- demands "exactly
the name this run's axes produce" for every entry in `REQUIRED_INPUTS`, and applies
the profile suffix uniformly. **The score panel has no profile dimension**: scoring
runs before any trading, the cap acts only on fills, and the two profiles' panels
are byte-identical. So the guard is asking for a file that should not exist. The
expectation is wrong here, not the writer -- and `_present`'s own docstring says
the real fix is a single naming authority every writer, reader and guard calls.

**Not fixed, and deliberately so.** It is the third instance of one missing
authority, not a third bug: see *"No component owns which axes an artefact
carries"* above, which records all three and why patching this one at its call site
would make the problem worse. **Do not read this entry as saying the profile runs
end to end -- it reconciles through STEP 15b and dies at STEP 16.**

### Superseded: what was open before 2026-09-15

Which of the engine and the audit is right about the
cap was the open question, and it is now settled: the engine implements
`profiles.py`'s stated rule and the audit was not applying a cap at all. The
figures are the engine's and the engine is correct.

---
## The verification claims describe something other than what ships, six times in one week

Found 2026-09-15, by fixing the fourth one and looking back at the other three;
two more landed the same day. Open. **This is not a bug in any one artefact.** It is a
defect in how this project establishes that a change is safe, and it is the
reason three of the four survived review: each was accompanied by a statement of
what had been checked, and in each case that statement was about something other
than the thing that shipped.

### The six

**1. THE ULP FIGURE.** `4.441e-16` across 2,638,259 cells, and the "two thirds of
a point" consequence drawn from it, are recorded in this file with no script
behind them. The claim was then quoted outward as fact -- the project's owner
repeated "the system cannot reproduce its own numbers" when asked whether the
work could be handed to someone else. Two rebuilds on 2026-09-13 failed to
reproduce any such divergence. See *"The headline is not reproducible from the
artefacts on disk to better than about a point"* directly below, which now
carries the correction and the external cost.

**2. THE `--list` COST CLAIM.** The invocation-contract design (commit `5c636cf`)
stated that moving the cached-panel skip into `build_scores_step` would cost
`--list` its advance notice of which score steps would skip. `--list` never
printed that; the skip was only ever announced at run time. The claim was
reasoned from the code's shape and never run. Corrected in place at the dispatch
site in `run.py`. Cost: nothing, which is the only reason it is a footnote.

**3. `905e598`'s UNREACHABLE BRANCH.** The commit that made a missing trade log
fatal in `make_mid_chart` stated:

> *"The `--arm v3` path does not ask for v1's curve, so the regression run does
> not exercise the changed branch; the standalone before-and-after above does."*

The line directly above the change asked for v1's curve **unconditionally**. The
v3 path reached the new `raise` and died in it, and **`--universe mid --arm v3`
-- one of the two gate cells -- was unrunnable from 2026-09-13 15:46 until
`e5654ac` on 2026-09-15.** The claim is why nobody looked: it asserted the branch
was unreachable from the path under test, so the crash was attributed, when it
appeared two days later, to the invocation contract that had landed in between.
It took a checkout of `67a644d` and a re-run to establish otherwise.

The underlying error was a half-port: `baa5daa` fixed `make_n100_chart` with two
halves -- the fatality AND the arm-awareness guard -- and only the fatality
reached midcap150. `make_n100_chart` was never affected, and no chart was ever drawn
from a curve it did not request.

**4. THE GATE'S DENOMINATOR.** Every regression verdict quoted in the week to
2026-09-15 came from a comparison script rewritten fresh in the session that
needed it, and each walked the BASELINE DIRECTORY, sha-ing whatever stood at each
name in the live tree -- without asking whether the run had written that file. A
baseline directory is a snapshot of a whole metrics folder, so it holds artefacts
belonging to other arms and other profiles. Those files are not touched by the
cell under test. **They match themselves, every time, whatever the change did.**

Measured 2026-09-15: of the 36 deterministic artefacts in the `mid_v3` baseline,
`--universe midcap150 --arm v3` writes **17**. The other 19 are v2's and the tradeable
profile's.

| verdict as quoted | files that could actually move | leftovers counted as matches |
|---|---:|---:|
| `905e598` -- "35 of 36 deterministic mid artefacts byte-identical" | <= 17 | **>= 19** |
| `67a644d` -- "36 compared, 34 byte-identical, 2 moved" | <= 17 | **>= 19** |
| `91729f9` -- "16 of 17 deterministic n100 artefacts byte-identical" | 17 | **0** |

**nifty100 was never inflated** -- all 17 of its deterministic baseline artefacts are
written by its cell -- and that is precisely why the defect survived: half the
evidence was sound, and the two universes were quoted side by side.

**The midcap150 figures are worse than the table shows for any commit after `905e598`.**
With the chart step crashing, `DAILY_LOG_mid_v3.txt` and `chart_mid_FINAL_v3.png`
were not rewritten either, so **16** deterministic artefacts could move, not 17 --
and the two the crash had frozen were being compared, and passing, on mtimes
predating the defect.

**5. THE STEP-3 GATE CLEARED A MERGED SCORING MODULE WITHOUT RUNNING IT.** Step 3's
entire content was the merge of the two score-build entry points, and both gate
cells ran on cached panels, so `build_scores_step.run()` returned early and not one
line of the merged path executed. The commit said so, which is the only reason this
is a footnote rather than an instance with consequences. Closed the same day by a
forced rebuild: both panels byte-identical, 20.5 minutes.

**6. `_CAP_REQUIRED` WAS BUILT TO ABOLISH THIS EXACT FAILURE AND ABOLISHED HALF OF
IT.** This is the expensive one, and it is instance 3's mechanism operating on the
instrument rather than on a chart.

`backtest_exposure` takes a participation cap and the volume series the cap is
computed against. The cap is mandatory -- `_CAP_REQUIRED`, a sentinel, with a
docstring that states the reasoning exactly:

> `participation_cap=None` used to be the signature default, so a caller that
> simply forgot it silently got `research` behaviour -- an uncapped fill -- and
> nothing in the output said which profile produced the number.

**`vol20` kept the silent `None` default that sentence condemns**, and the cap is
applied only `if participation_cap is not None and vol20 is not None`. So a caller
could satisfy the mandatory flag, omit the optional data the flag operates on, and
be refused the cap three hundred lines later without a word.

`results/audit_step.py` did exactly that. Under `--profile tradeable` on midcap150 it
replayed the RESEARCH strategy and reconciled it against the TRADEABLE curve:

```
v1 MISMATCH Rs 3,851,027.09      v3 MISMATCH Rs 3,510,367.57
v2 MISMATCH Rs   605,030.57      v4 MISMATCH Rs   958,629.05
```

Reproduced 2026-09-15 by calling `backtest_exposure` twice with identical inputs,
differing only in whether `vol20` was passed:

```
with vol20 (engine)     vs tradeable curve Rs         0.00   vs research Rs 3,851,027.09
without vol20 (audit)   vs tradeable curve Rs 3,851,027.09   vs research Rs         0.00
trades: engine 860 / TC 692,730     audit 852 / TC 839,393
```

860 and 692,730 are the published TRADEABLE figures; 852 and 839,393 are the
published RESEARCH ones. The audit was not approximately wrong; it was exactly the
other profile.

**THE MANDATORY FLAG IS WHAT MADE THE OPTIONAL DATA INVISIBLE.** Nobody re-examined
the pairing, because the parameter that had been identified as dangerous was
already guarded and the guard was known to be there. **A half-enforced contract is
worse than no contract**: it delivers the assurance without the guarantee, and it
spends the attention that would otherwise have gone to checking. An unguarded
parameter gets checked by the next person who touches it. A parameter sitting next
to a guarded one does not.

**AND THIRTEEN MORE CALLERS HAD THE SAME PAIRING.** Of the live callers passing the
cap, eight supply `vol20` (both engines, `v34_common` x4) and fourteen did not.
Thirteen of those fourteen were unreachable by the profile axis, established
2026-09-15 by four independent routes, each checked: none is in `PIPELINE_ORDER`,
none accepts `--profile`, none calls `profiles.set_selection`, and no load-bearing
module imports any of them (AST walk over the load-bearing set: zero). In a fresh
process `profiles.selected()` is `research` and the cap is `None`, so their numbers
are research numbers correctly labelled. **No published figure was ever
mislabelled, and nothing in this file needed correcting.**

**But they were safe BY CONSTRUCTION, not BY DECLARATION** -- safe because the axis
could not reach them, not because they paired the cap with its data. Those are
properties of a tree that steps 4-8 of the collapse are actively rewriting, and the
first `--profile` flag added to any of them would have restored the defect silently.
All thirteen now declare `profiles.research_only(__name__)`, which returns the
research cap and REFUSES if a non-research profile is ever selected, naming the
caller. `backtest_exposure` refuses a cap passed without `vol20`, naming the call
site. Both halves of the contract are now enforced.

### What they have in common

Not carelessness, and not a missing test. In every case **a verification was
performed and reported accurately** -- the gate did compare 36 files, the ULP
figure was measured on something, `--arm v3` genuinely did not plot v1. What was
wrong each time is the mapping from what was measured to what was claimed:

- a number measured under an engine configuration that has since changed (1)
- a cost reasoned from code shape and never executed (2)
- a path described from a call site thirty lines away from the one that runs (3)
- a denominator that includes files the run cannot touch (4)
- a module merged and gated without one line of it executing (5)
- a contract half-enforced, so the guarded half hid the unguarded one (6)
- a table that tolerates a missing entry, so being registered reads as being
  covered (7)
- a rule applied uniformly to items that do not all carry the same axes (8)

**AND THE GENERAL FORM, WHICH FIVE OF THE SIX SHARE: A FALLBACK THAT SILENTLY
RESTORES PRE-FIX BEHAVIOUR IS INDISTINGUISHABLE FROM NO FIX.** The safeguard is
present, the guarantee is absent, and the presence of the safeguard is what stops
anyone looking for the guarantee. `vol20` defaulting to `None` left the cap
inert while `_CAP_REQUIRED` stood beside it. And the prose stripper written on
2026-09-15 to close instance 3's mechanism did the same thing within a day of
being written: its bare `except` returned the text UNSTRIPPED, so a `TypeError`
on `ast.IfExp.body` restored the exact behaviour the function existed to remove --
and it passed its two-line test while doing nothing at all on the real tree. The
test proved the happy path; the fallback governed every other path and proved
nothing. **A fallback must fail loudly or not exist.**

**INSTANCE SEVEN, AND IT IS THE PATTERN RATHER THAN A BUG: A TABLE THAT SILENTLY
TOLERATES A MISSING ENTRY IS INDISTINGUISHABLE FROM A TABLE THAT COVERS IT.** Same
family as the silent fallback above, and the same mechanism: the structure that
should produce the guarantee is present, the guarantee is absent, and the presence
of the structure is what stops anyone checking. A fallback answers the wrong
question quietly; a table with a hole answers no question at all and looks the
same from outside.

Found 2026-09-16 by asking what an eleventh universe costs. Seven tables must
carry a row for every universe in `universes/registry.py`, and **three of the seven
tolerated a missing row in silence**:

| table | on a missing row, before |
|---|---|
| `REPORT_ORDER` | raises, naming the tag |
| `make_combined.COLOURS` | `SystemExit` at import, naming the tag |
| `make_combined.FILES` | `KeyError`, loud but unexplained |
| `make_combined.DISPLAY` | **silent** — `.get(t, t)` draws the raw tag where a display name belongs |
| `make_combined.LIQUIDITY` | **silent**, and documented as optional |
| `run_all.PIPELINE_ORDER` | **silent, and the worst of them** |
| `run_all.REQUIRED_INPUTS` | **silent** — that universe's inputs are unguarded |

**`PIPELINE_ORDER` is the one that matters.** A universe registered but absent from
it runs **no scores, no engine, no audit and no chart** — and `run.py` reports
success, over a pipeline that did a fraction of the work, with no line of output
saying which fraction. Registration and execution were two independent facts and
nothing compared them.

**Closed by refusal, not by derivation.** `registry_coverage_check.py` asserts
every registered tag against all seven, reads the four `make_combined` tables with
`ast` rather than by importing (importing dies on the one case it exists to
report), and names the tag, the table and the consequence. `run.py` calls it from
`preflight()`, over the whole registry rather than the selection, because coverage
is a property of the repository and a one-universe run would otherwise pass while
the other is half-wired. **A table that cannot be found at all is also a failure**,
because a coverage check silently checking nothing is this same defect one level up.

Deriving `REQUIRED_INPUTS` from the registry would remove one of the seven, and is
deliberately NOT done here: making the silence loud is verifiable on its own, and
the derivation moves a guard table four consumers read. Refusal first.

**INSTANCE EIGHT, AND IT IS THE PATTERN: A RULE APPLIED UNIFORMLY TO ITEMS THAT DO
NOT ALL CARRY THE SAME AXES. THE MACHINERY IS CORRECT AND ITS SCOPE IS NOT.**

What makes this one expensive is the last part: **it is indistinguishable at the
call site from a missing artefact, because the refusal it produces is identical.**
A guard that correctly refuses a substitute and a guard that demands a file which
cannot exist print the same sentence, name the same path, and stop the same run.
Nothing in the message tells you which of the two you are looking at, so the
reader's first move — look for the step that failed to write it — is the wrong one,
and it is wrong in a way that cannot be discovered by reading the message again.

**THE INSTANCE, measured 2026-09-16.** `run_all.check_inputs._present()` composed
`cadence.suffix() + profiles.suffix()` onto **every** required input, as though all
five carried the same axes. `--universe mid --arm v3 --rebal 200` completed eight
of nine steps and died at STEP 16 demanding
`results_mid/metrics/v_mid_expanding_cache_r200.csv`.

**STEP 15b had not failed.** It wrote `v_mid_expanding_cache.csv`, which is its job:
the score panel does not vary with cadence, so there is no `_r200` copy of it to
write. The first diagnosis — "a step reported success while not writing what its
consumer needs" — was wrong, and it was wrong *because the refusal looks the same
either way*. The correct reading is that the consumer asked for a file that should
not exist.

**THE MEASUREMENT THAT SETTLED IT**, because the two fixes are opposites and
picking wrong duplicates caches or silently shares one across cadences:

| axis | evidence |
|---|---|
| cadence | Panels built from source at r20 and r200, one process, determinism pinned before any numeric import. Raw and score panels **byte-identical** — `163ad6db…` and `4dae4a55…` — and both equal the shipped caches and the `/tmp` working copies. 19.0 and 17.4 minutes of scoring. |
| profile | The transitive import closure of `build_scores_step` is seven modules and **none** imports or references `profiles`. Code that never reads a value cannot vary with it. |

`build_scores_step` already carried `# naming: axis-free` on both writes. That was
a claim; it is now a measured one — and the same over-application was why
`--profile tradeable` could not complete, STEP 16 having demanded a
`_tradeable` score panel that has no dimension to produce. **One scope, two blocked
axes.**

**CLOSED BY SCOPING, NOT BY LOOSENING.** Every `REQUIRED_INPUTS` entry declares
which axes its name carries; the fourth field is compulsory, checked at import,
with no default — a default is the defect. No cadence-tagged cache was added and
the substitution refusal is unchanged, demonstrated in both directions with the
canonical file present and not accepted.

**A green check whose subject is not the shipped thing is worse than no check**,
because it is quoted. Instance 1 left this repository in conversation. Instance 3
was quoted back at a crash to exonerate the wrong commit. A check nobody had run
would have done neither.

### Fixed, and not fixed

`gate_compare.py` is tracked, and replaces the per-session comparison script. It
partitions explicitly -- WRITTEN BY THIS CELL (compared), NOT WRITTEN (listed,
never counted, with the reason per file: wrong arm, wrong profile, wrong
universe) -- and treats an artefact it cannot explain as **fatal**, because "not
written, and nobody knows why" is indistinguishable from a step that stopped
writing. Instances 2 and 3 are corrected at their sites; instance 1 carries its
correction in the entry below.

**What is NOT fixed is the general case.** Nothing checks that a verification
claim in a commit message describes the code path that shipped, and nothing
could. The only defence available is the one this entry exists to encourage:
**when a commit says a branch was not exercised, run the path it names before
believing it.** Three of these four would have been caught by one command.

---

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
| nifty100 v2 CAGR | 26.15 | 25.49 | **+0.66** |
| nifty100 v2 Sharpe | 1.92 | 1.88 | +0.04 |
| nifty100 v2 MaxDD | −17.67 | −18.64 | +0.97 |
| midcap150 v2 CAGR | 29.93 | 30.22 | **−0.29** |

**The mechanism is not mysterious.** A last-bit change to a feature can flip a
LightGBM split decision; a flipped split changes a predicted score by up to
3.45e-02 (measured); a changed score reorders near-tied names at the TOP_N=8
boundary; a different name enters the book. The chain from one bit to one CAGR
point is short and it is entirely deterministic.

**CONSEQUENCE, STATED PLAINLY. The published headline cannot be reproduced from
the artefacts in this repository to better than roughly one CAGR point.** Anyone
re-running the scoring from `raw_panel_*_cache.csv` — the only panel artefact on
disk — gets 26.15 on nifty100, not the published 25.49. Both are correct outputs of
the code; they differ because one scored a CSV and one scored memory.

**IT IS THE SAME PHENOMENON AS TWO OTHER ENTRIES, AT THREE SCALES OF
PERTURBATION.** These are not three defects; they are three measurements of one
property.

| perturbation | size | effect on headline CAGR | recorded in |
|---|---|---|---|
| one bit of float precision | 4.441e-16 relative | +0.66 (nifty100 v2) | this entry |
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
| nifty100 | v1 | 2.180·K^(−0.150) | **−0.150** | 2.158 | 1.743 |
| nifty100 | v2 | 1.559·K^(−0.226) | **−0.226** | 1.568 | 0.968 |
| midcap150 | v1 | 3.632·K^(−0.245) | **−0.245** | 3.845 | 2.137 |
| midcap150 | v2 | 1.801·K^(−0.168) | **−0.168** | 1.876 | 1.393 |

**Every exponent is between −0.15 and −0.25, less than half of −0.5.** The
variation between seeds is therefore largely COMMON rather than independent —
ten models trained on the same panel make correlated errors, and averaging them
removes far less than the ensemble design assumes.

**What it costs in practice.** Going from one seed to ten buys a σ reduction from
1.57 to 0.97 on nifty100 v2 — a factor of 1.6 for ten times the compute, where
independence would have bought 3.2. On nifty100 v1 it buys a factor of 1.24.

**Extrapolated seeds for ±0.5-point stability**, assuming the fitted exponent
holds far outside the measured range: nifty100 v2 **152**, midcap150 v2 **2,044**, midcap150 v1
**3,310**, nifty100 v1 **17,889**. No tested K up to 40 approaches the bar. These are
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

## The published v2 CAGR is not reproducible under rounding-level price changes, and it is not the centre of its own distribution

Measured 2026-09-20 (nifty100) and 2026-09-21 (midcap150) by
`results/price_noise_measure.py`; per-run record in
`diagnostics/price_noise_runs.csv`, report in `diagnostics/price_noise.txt`.
Open. **This is a finding about what the published numbers are, not a caveat on
one of them.**

### Why it was asked

nifty100 v2 went from +0.43 CAGR points over its own basket to −5.15 when the
universe was repointed on 2026-09-18. Decomposing the fall by name on 2026-09-20
showed it was not located where the data changed: 53 of the 99 constituents carry
108% of the drop in final equity and every one of those 53 has an in-window
`adj_close` identical to the old panel's to within 0.01%. MAZDOCK alone carries
42.8% of it with 1,477 of 1,477 in-window sessions unchanged. The names whose
prices genuinely moved were net positive.

### What was run

45 full re-runs of v2 — panel rebuilt, 10-seed ensemble refitted, backtest
re-executed, nothing reused from stored fills. `adj_close` multiplied by (1 + ε),
ε ~ Normal(0, σ), drawn independently per (symbol, date). **The ten production
seeds are held fixed in every run**, so this dispersion is on top of the seed
noise the entry above records, not a re-measurement of it.

σ = 0 is run first through the same code path and must reproduce the published
`v34_comparison.csv` row; the gate is asserted at run time and stops the grid on
a mismatch. It passed on both universes on every start.

```
nifty100    baseline 19.01   basket 24.16    n = 1,836 sessions
   sigma  runs   mean     min     max     sd  spread  overlap
   0.01%    10  20.76   19.32   22.55   1.03    3.23    0.662
   0.05%     5  20.75   16.78   24.13   2.62    7.35    0.638
   0.10%     5  21.85   20.08   24.83   1.92    4.75    0.600
   0.50%     5  21.58   19.57   25.25   2.26    5.68    0.483

midcap150   baseline 27.80   basket 25.46    n = 1,836 sessions
   0.01%     5  30.42   28.03   31.88   1.51    3.85    0.707
   0.05%     5  29.24   27.55   31.31   1.69    3.76    0.682
   0.10%     5  30.45   27.29   32.52   2.45    5.23    0.649
   0.50%     5  28.74   24.78   32.11   2.77    7.33    0.511
```

### What it establishes

**The published figures sit below their own distributions.** At σ = 0.01% all ten
nifty100 draws and all five midcap150 draws came in above the published number —
15 of 15, and 39 of all 45 perturbed cells (exact one-sided p = 2.7e−07 under a
symmetric null). nifty100's 19.01 is 0.31 points below the minimum of its ten
draws; midcap150's 27.80 is 0.23 below the minimum of its five. **They are
legitimate draws and they reproduce bit-for-bit. They are extreme draws, which is
a different problem from being wrong, and it is the one that governs how many
digits can be quoted.**

**A hundredth of a percent moves the result as much as the whole ensemble does.**
nifty100 at σ = 0.01%, n = 10, sd 1.03 against the 0.968-point seed floor at
K = 10 recorded above — 1.06 times it, with the seeds frozen.

**Both signs of the edge are reachable in both universes.** nifty100's published
−5.15 ranges −7.38 to +1.09 over its 25 perturbed cells and beats its basket in 2
of them; midcap150's published +2.34 ranges −0.68 to +7.06 over its 20 and loses
to its basket in 1. The arm that "loses to its basket" and the arm that "beats
its basket" are the same arm at two points of one distribution.

**It is not specific to the universe that embarrassed it.** midcap150 was run as
the control precisely because it keeps a positive edge, and it shows the same
displacement. Its 0.01% block is n = 5, p = 0.031 — suggestive, not the 1-in-1,024
nifty100 has, and it has not been taken to ten seeds.

**The only monotone quantity in the grid is the holdings overlap**, 0.662 → 0.483
on nifty100 and 0.707 → 0.511 on midcap150. Neither the spread nor the mean
orders with σ at n = 5 per block.

### What was ruled out, and what is not offered

**No mechanism is proposed for the one-sidedness.** The one asymmetry in the
construction was measured and points the wrong way. `canonical_price` falls back
to the raw close when `adj_close` leaves [low, high], and under noise it fires on
1.3% of nifty100 rows and 2.3% of midcap150 rows against 0.036% and 0.007% at
baseline. It is one-sided by count — 3,259 to 3,389 upward corrections against
2,808 to 2,971 downward on nifty100, tracking the 6,176 rows that sit on the low
against 5,766 on the high — but its net effect on delivered ε is **−2.8e−06 to
−5.2e−06**, a downward displacement, while every outcome moved up.

The draw itself is unbiased: realised mean ε is 5e−08 to 1.7e−07 per run against
a sampling sd of 1.45e−07 over 473,311 rows. The write path preserves it; a
round trip through the CSVs reproduces the intended value to 7.3e−12 per row and
the mean to 5e−10.

**The construction was not adjusted.** Changing it to make the noise land cleanly
would have measured a different engine and made the levels incomparable.

### What it does not settle

**Whether the 2026-09-18 repoint caused the −5.15 is still open.** Its 5.42-point
move is inside the spread at σ = 0.05%, 0.10% and 0.50% and outside it at 0.01%.
What can be said is that 5.42 is not a large number for this arm: it is between
one and two spreads of a change too small to see.

**Why the arm is this sensitive is not addressed here.** Whether the answer is
the ensemble, the ranking rule's behaviour at near-ties, the breadth gate, or the
sizing, this measurement does not distinguish them and nothing in it should be
read as doing so.

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
`diagnostics/leakage_labels_hashes.txt`. **NOT regenerable:**
`results/hash_58_engine_core.py` was deleted on 2026-09-11 in `aafe6cb` and the
58 panel it hashed is gone, so the hashes stand as evidence of what was measured
rather than as something that can be reproduced. That file carries the reason at
the point of citation.

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
| 3 | Execution timing | **TESTED, held — re-run 2026-09-02 against the post-purge-fix fills** | `diagnostics/checkB_execution_timing.txt` — **977 of 978** (nifty100) and **961 of 963** (midcap150) fills at the fill day's open, **0 at any close**, all 1,941 one session after a recorded decision date. The earlier 976/977 and 971/973 described the pre-rebuild `fills.csv` and are superseded |
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
| `data/nse_trading_calendar.csv` (STEP 0) | `make_trading_calendar.py:86` -- **writer deleted 2026-09-11, commit `2fe48ff`; there is no STEP 0 any more and nothing writes this file** | already OK when measured |

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
| nifty100 v2 CAGR | 26.15 | 25.49 | **+0.66** |
| midcap150 v2 CAGR | 29.93 | 30.22 | **−0.29** |

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
| `liquidity_participation.py` | `liquidity_participation.txt` — the 1,614.52% figure, **superseded 2026-09-20**, now 34.46% max on midcap150 (n=1,006 fills) | DRAWDOWN_EXIT_SPEC.txt, EXPERIMENTS.md, README.md |
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
`KNOWN_ISSUES.md:2211` and `diagnostics/leakage_labels_hashes.txt:28`, the latter as
*"Regenerate with: ./venv/bin/python results/hash_58_engine_core.py"* — it is the
named regeneration path for a cited hash artefact, the exact pattern the table
above documents. It was tracked in git and was restored intact.

**AND THEN IT WAS DELETED ON PURPOSE. THE SECOND HALF, ADDED 2026-09-20, BECAUSE
THE PARAGRAPH ABOVE ENDS AT "restored intact" AND READS AS THOUGH THE FILE IS
STILL THERE.** It is not. `results/hash_58_engine_core.py` was restored on
2026-09-03, and deleted on 2026-09-11 in commit `aafe6cb` -- "Delete eight scripts
the retirement left with nothing to run on" -- with the reason stated there:
*"hashes the 58's equity curve; the panel is gone"*. The 58, its raw files and its
cache went the same day in `2fe48ff`, so the script had nothing left to hash.

**THAT IS NOT THE ERROR REPEATING ITSELF.** The 2026-09-03 deletion failed the
four-test procedure -- the file was cited, and the citation was a live
regeneration path. By 2026-09-11 the *artefact* it regenerated had become
unregenerable for a reason that had nothing to do with the script, so the
citation was history rather than an instruction. `diagnostics/leakage_labels_hashes.txt`
now says so at the point of citation, and the hashes it carries were not deleted.
The lesson below is unchanged and is the reason this half is recorded rather than
left for someone to rediscover.

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
universe.

**THE SCOPE IS RESTATED, 2026-09-12, BECAUSE ITS ORIGINAL PROOF NO LONGER HOLDS.**
This paragraph used to close by naming the two figures `README.md` embedded —
`docs/chart_COMBINED_n100_mid.png` and `docs/chart_decay.png` — and observing that
neither was in this chain. The combined chart was withdrawn on 2026-09-12 and is
no longer embedded anywhere, so that sentence proved nothing about a file that had
stopped being published.

The confinement itself is unchanged, and it rests on the chain, not on the
figures: STEP 13 and STEP 14 run only over the retired pair, and the live
universes reach their own audit and chart steps. **The defect's scope was never a
property of what the README happened to embed.** Stating it that way made a real
containment argument look as though it depended on a chart, and then made it look
false when the chart went.

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
| nifty100 | 7 | **0** |
| midcap150 | 1 | **0** |

**Why.** `invest_val` is a single portfolio-wide number, and it is split `TOP_N`
ways. Raising `TOP_N` does not raise the total to be funded — it **shrinks each
entrant's slice**, so every individual buy is easier to cover from cash and the
score-descending loop exhausts it less often. The binding quantity is the size of
one entrant's target against available cash, not the count of entrants.

**A second effect points the same way.** A larger `TOP_N` against a pinned
`BUFFER=16` holds a fuller book — mean names held rises 9.54 → 12.88 on nifty100 and
9.23 → 12.88 on midcap150 — so more of the target set is already held and **skipped by
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
| nifty100 | v1 invvol, 100% invested | 119 | 8.01 | 12 |
| nifty100 | v2 invvol, breadth-scaled | 7 | 9.54 | 1 |
| nifty100 | v3 provol, 100% invested | 140 | 7.78 | 24 |
| nifty100 | v4 provol, breadth-scaled | 9 | 9.52 | 1 |
| midcap150 | v1 invvol, 100% invested | 92 | 8.04 | 14 |
| midcap150 | v2 invvol, breadth-scaled | 1 | 9.23 | 0 |
| midcap150 | v3 provol, 100% invested | 129 | 7.63 | 34 |
| midcap150 | v4 provol, breadth-scaled | 1 | 9.23 | 0 |

The skipped name's rank is median 7 or 8 of 8 in every arm — the tail of the buy
loop, as the mechanism predicts. `qty < 1 after sizing` is **zero** for v1 and v3
in both universes, so this is not a rounding-to-zero effect; it is cash exhaustion.

**IT AFFECTS THE PRODUCTION BASELINE, INDEPENDENTLY OF ANY OF THIS.** v1 is the
always-invested inverse-vol arm that ships. It fails to fill its own eight-name
target on **12 of 91 rebalances on nifty100 and 14 of 91 on midcap150**, and it does so 119
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

| model | midcap150 CAGR / blocked | nifty100 CAGR / blocked | 58 CAGR / blocked | trades |
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
before funding entrants raises skips from 93 to 100 on midcap150.

**And their CAGR effect has no consistent sign** — A is -0.41/-1.28/+0.99, B2 is
+0.72/-0.88/+0.61 across midcap150/nifty100/58. That is inside the seed-noise floor this
project measured at sd 0.97-2.14 CAGR points (`EXPERIMENTS.md` entry 29).

**One thing the gap does cost, measurably.** It is why the shipping engine holds a
mean book of 7.98 on midcap150 — BELOW `TOP_N` — which is the failure
`results/validate_engine.py` reports as T1 on that universe. A, B2, C and D all lift
it back into `[TOP_N, BUFFER]`; B does not.

**Decision, 2026-09-04: not implemented.** This is a trade-off between churn
control and full funding, not a defect with a correct repair. Every model that
closes the gap degrades performance on all three universes, so selecting one after
seeing these numbers would be fitting the strategy to the result. If it is taken
up, it belongs in `experiments/` as a pre-registration with its gates written
first. `results/test_exposure.py` is unchanged by this entry.

### 2026-09-05: A SIXTH MODEL, PRE-REGISTERED. IT CLOSES THE GAP AND STILL COSTS.

Taken up on instruction, under `experiments/FUNDING_SPEC.txt`, which is the
pre-registration the paragraph above asked for: gates and predictions were written
and committed before the model was run.

**Model E, "pro-rata entrant scaling".** It is the one funding model that keeps the
whole-portfolio sizing base AND the buffer AND the no-resize rule. It changes a
single thing: when the entrant block does not fit in cash, the entrants are scaled
down *together* by one factor rather than the tail being dropped one at a time.

    f   = min(1, cash * 0.98 / (invest_val * sum of entrant weights))
    q_i = int((invest_val * w_i * f) // price_i)

`invest_val` is untouched, so the whole-portfolio base survives. `f` is one scalar
applied to every entrant, so the inverse-vol proportions survive. Nothing is sold,
nothing is topped up, no buffer name is trimmed — `V34_SPEC.txt:125` holds. The
0.98 is the haircut the function already applies; no new constant, nothing tuned.

**It closes the gap completely.** Unfilled buy targets go to **zero** in all six
measured cells — and `qty < 1 after sizing` stays at zero too, so the failure was
removed rather than moved into a different skip reason. Mean names held rises into
`[TOP_N, BUFFER]` everywhere (9.18 / 9.56 / 9.98), clearing the T1 failure
`results/validate_engine.py` reports on midcap150.

**And it fails the performance and churn gates, as the four models before it did:**

| universe | arm | CAGR cash → prorata | dCAGR | unfilled | mean held | trades |
|---|---|---|---|---|---|---|
| midcap150 | v1 | 45.87 → 41.42 | **-4.45** | 92 → **0** | 8.00 → 9.18 | +16.0% |
| midcap150 | v3 | 49.70 → 42.91 | **-6.79** | 125 → **0** | 7.58 → 9.18 | +22.7% |
| nifty100 | v1 | 34.90 → 33.25 | **-1.65** | 118 → **0** | 8.02 → 9.56 | +21.6% |
| nifty100 | v3 | 28.10 → 26.76 | **-1.34** | 142 → **0** | 7.65 → 9.56 | +26.4% |
| 58 | v1 | 24.62 → 22.06 | **-2.56** | 135 → **0** | 8.21 → 9.98 | +28.0% |
| 58 | v3 | 23.47 → 22.91 | -0.56 | 165 → **0** | 7.77 → 9.98 | +39.2% |

Five of six cells breach the -0.97 CAGR bar, which is the LOW end of this project's
own seed-noise band (`EXPERIMENTS.md` entry 29) and was chosen before the run
precisely so a real loss could not hide inside a band picked afterwards. All six
breach the 10% churn bar.

**THE COST IS NOT CASH DRAG, AND THAT IS THE POINT.** Mean invested percentage
*rises* under prorata in every cell — 94.46 → 96.35 on midcap150 v1, 94.16 → 96.89 on
nifty100 v1. The book is fuller in names and more fully invested and still earns less.
The loss is **dilution**: the same capital spread over 9.2–10.0 names instead of
7.6–8.2, and the marginal names are the lowest-ranked of the target set. **The
funding gap was, accidentally, a concentration filter, and the concentration was
worth more than the names it cost.** Model D reached the same conclusion by
dissolving the buffer; E reaches it while preserving the buffer, which makes it
much harder to attribute the loss to anything but concentration itself.

**One thing the measurement settled that was previously only asserted.** Under
prorata, v1 and v3 hold the same number of names and make the same number of trades
within each universe (9.18/9.18 and 969/969 on midcap150). Under the cash rule they do
not. That confirms this entry's own claim that the two arms "did not hold the same
portfolio": the divergence was entirely an artefact of the funding gap, and once
every target is filled the arms differ only in position size, which is what a
sizing rule should differ in. Not predicted, not gated on — recorded because it
corroborates the mechanism independently.

**Status: implemented, defaulted OFF.** `backtest_exposure` now takes
`funding="cash"` (unchanged, and the default) or `funding="prorata"`. The default
path does not compute `f` at all, and all six baseline equity curves reproduce
**byte for byte** — diffed as files, not compared as metrics. So no published
figure moves and the seven identity gates on `v34_comparison.csv` are untouched.
`nautilus/nt_strategy.py` mirrors this sizing rule and is therefore still exact; if
the default is ever flipped, the port must be updated in the same commit.

**The gap is now a priced decision rather than an open defect.** Six models have
been measured and every one that closes it costs 1.3 to 6.8 CAGR points. Anyone
proposing to close it is choosing to pay that, not fixing a bug.

---

## Breadth is validated on both live universes; sizing still is not

Found 2026-08-28. Breadth CLOSED 2026-08-29. The sizing half remains open.

Breadth sets total exposure at every rebalance — `expo = mean(mom_20 > 0)`, which
is why average deployment sits at 54–56% rather than 100% — and every published v2
and v4 figure depends on it entirely. Until 2026-08-29 it had been validated only
on the retired 58, by `results/validate_breadth.py`, which has never run on nifty100 or
midcap150.

**Closed by `results/validate_breadth_live.py`**, run on both universes on
2026-08-29 under `experiments/BREADTH_LIVE_SPEC.txt`. T1 and T2 are copied verbatim
from the 58's suite, thresholds included; the underived `dMaxDD > 3` bar was not
recalibrated for either universe.

    n100   3 of 3 gated criteria   PASS
    mid    3 of 3 gated criteria   PASS

Both universes pass, so the split-result clause of the spec did not fire.

**IT ALSO REPRODUCES SHIPPING v2 EXACTLY.** Its breadth arm returns CAGR 25.49 /
Sharpe 1.88 / MaxDD −18.64 on nifty100 and 30.22 / 2.06 / −18.98 on midcap150 — identical to
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
production, so its 4-of-4 on nifty100 and 1-of-4 on midcap150 say nothing directly about the
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

so on nifty100 and midcap150 the full period and the 2023-2026 half end on the same day.
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
The entry above is built on LLOYDSME as midcap150's dominant name. Measured:

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
| nifty100 | 11.67% | 27.76% | 39.61% | **61.24%** | 93 |
| **midcap150** | 9.49% | 27.73% | **43.48%** | **68.94%** | 122 |

**midcap150 is roughly 8 points more concentrated than nifty100 at both the top-5 and
top-10 cuts, on a universe 50% larger** (148 names against 99). That is the
direction the record has always asserted, now with a number attached. It is also
the first time either universe's concentration has been quantified at all.

**WHAT THIS MEASUREMENT IS NOT.** Removing the top contributor arithmetically —
midcap150's realised P&L falls 9.5% without TATAINVEST, nifty100's falls 11.7% without
MAZDOCK — **is not the strategy re-run without that name.** The model would have
selected differently and the capital would have gone elsewhere. A true
leave-one-out requires re-running the engine, which `mid_jackknife.py` does and
this does not. The two must not be quoted interchangeably.

Artefacts: `diagnostics/attribution_v2.txt`,
`results_{n100,mid}/metrics/attribution_v2_per_symbol.csv` and
`attribution_v2_round_trips.csv`.

**UNRESOLVED, AND THE `mid` ABOVE IS DELIBERATELY NOT RENAMED.** Checked
2026-09-18: `attribution_v2_per_symbol.csv` exists NOWHERE on disk -- not under
`results_mid/`, which no longer exists, and not under `results_midcap150/`, which
does. **Do not read this line as a live pointer.** It cannot be told apart from a
record of an artefact that was produced and later deleted, and the two want
opposite treatment: a live pointer should carry the new name, a record should keep
the old one. Renaming it would manufacture a false record of a file that never
existed under that name, which is the more expensive of the two mistakes.
Resolving it means finding out whether this artefact was ever written, and by
which step.

---

## The MidCap150 chart declares itself invalid, and is not

Found 2026-08-27. Open.

`results_midcap150/metrics/chart_midcap150_FINAL.png` renders with this as its first line:

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
void. The project treats them as valid — midcap150 is one of the two live universes, it
reconciles against the Nautilus port on 93 of 93 rebalances, and its numbers are in
the README. The chart is the only thing in the repository still saying otherwise,
and it says it in 14-point type at the top of the image.

**Not fixed deliberately.** The stale text is evidence of when the density fix
landed and what it changed, and editing it away would remove that. Fixing it
properly means deciding whether the blocker note should be recomputed from the
current panel, rewritten as a dated historical note, or deleted — that is a
judgement about what the chart is for, not a typo correction.

**Consequence for the README, RESTATED 2026-09-12.** `chart_mid_FINAL.png` is
still not embedded in `README.md` while this stands, and that part is unchanged.

**WHAT CHANGED IS THE ALTERNATIVE.** This used to say the published figure is
`docs/chart_COMBINED_n100_mid.png`, "which covers mid and n100 together and
carries no stale text". That chart was withdrawn on 2026-09-12 — its producer
reads its inputs by canonical name with no arm, cadence or profile suffix, so it
plotted whichever run wrote them last and recorded nothing about which.

**SO THE README NOW PUBLISHES NO CHART AT ALL**, and this entry no longer names a
substitute. The two blockers are independent and both are open: the midcap150 chart
carries stale blocker text, and the combined chart cannot say what it reads.
Resolving either one is what puts a figure back. Neither is waiting on the other,
and the absence of a published chart is not evidence that either was fixed.

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
| nifty100 | `af9a28ac9e58032c...` | `163927a65e89165d...` |
| midcap150  | `aa277d1bd2c86774...` | `1e2d85df4d8fee73...` |

So the numbers on record were computed from a panel that is no longer the one
`results_nifty100/metrics/v_nifty100_expanding_cache.csv` and
`results_midcap150/metrics/v_midcap150_expanding_cache.csv` hold.

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

| | nifty100 was | nifty100 now | midcap150 was | midcap150 now |
|---|---|---|---|---|
| CAGR% (TOP_N=8) | 25.49 | **25.78** | 30.22 | **29.70** |
| Sharpe | 1.88 | **1.86** | 2.06 | **2.03** |
| MaxDD% | −18.64 | **−19.87** | −18.98 | **−18.88** |
| dSharpe (8 minus 12) | +0.1900 | **+0.2000** | +0.1200 | **+0.0400** |
| trades | 981 | 978 | 973 | 963 |

**The midcap150 dSharpe is the one to look at.** TOP_N=8's Sharpe advantage over
TOP_N=12 on the MidCap150 falls from +0.12 to **+0.04**. The pre-registered rule
in `experiments/TOPN_SPEC.txt` is not a threshold on that margin, so the verdict
stands as written -- but +0.04 is inside the seed-noise floor this project
measured at sd 0.97 to 2.14 CAGR points (`EXPERIMENTS.md` entry 29), and anyone
quoting the midcap150 TOP_N result as evidence of a margin should quote this number
rather than the old one.

**Why this is filed as a class and not just a correction.** Nothing checks that a
diagnostics artefact still matches the panel it names, even though every one of
these three files prints the hash that would make the check trivial. The hash is
recorded and then never compared. The same gap is described from the other
direction in *An artefact was used three times without checking it was the one the
code reads*.

---

## A non-default selection could not run from cold at all -- four defects

Found 2026-09-06 by running `--universe mid --arm v1,v3 --rebal 40` from an empty
tree. It failed at four separate steps, one after another. **Every one of them had
passed warm**, because a previous default run had left the file on disk.

    1. check_inputs demanded the canonical daily_trades_mid.csv, but --rebal 40
       writes daily_trades_mid_r40.csv and leaves the cadence-20 file alone.
    2. make_mid_chart / make_n100_chart read the canonical trade logs. before_tc
       returns (None, 0, 0) for a file that does not exist, so this was not a
       crash -- it was a legend reading "CAGR None% before TC".
    3. daily_trades_<tag>.csv is v2's trail and was demanded unconditionally, so
       `--arm v1,v3` could not run from cold whatever the cadence.
    4. nt_export_scores required ALL FOUR universes' score caches and iterated all
       of REGISTRY. **Warm, this did not error: it exported Nautilus input parquet
       for three universes the run never built, from whatever an earlier run had
       left behind.** Stale output that looks like success is worse than a stop.

**FIXED.** `check_inputs` accepts a cadence-named sibling; a requirement may name
the arm it belongs to (`"v2"`) or the universe (`"u:midcap150"`) and is skipped when
that is not selected; `make_daily_log` skips with a reason when v2 is not selected
or the cadence is not default -- it is v2's forensic log and says so in its own
header; `nt_export_scores` exports only the selected universes.

**Verified from an empty tree afterwards:** exit 0, 0 tracebacks, 19.0 min with
the midcap150 score panel rebuilt from data/ (18.9 min), checker 42/9/0. All 36
artefacts are midcap150-scoped and carry `_r40`, `runs/mid/v1@r40` and `v3@r40`, and no
58, 74 or nifty100 artefact is produced at all.

**`runs/mid/v1@r40` AND `v3@r40` ARE NOT ON DISK, AND WERE ALREADY NOT ON DISK
BEFORE THE 2026-09-20 RUN-FOLDER DELETION.** Checked on 2026-09-20 before
anything was removed: no path matching `@r40` existed anywhere in the tree, in
any of the eleven directories deleted that day, or in
`forensic_snapshot_20260911T0100`. **The deletion did not break this citation and
must not be blamed for it.** The measurement above is a real record of a run that
wrote those directories; they were cleaned up at some point that nothing recorded.
`runs/mid/` itself survives and was deliberately not deleted -- see the note in
`PANEL_MIGRATION.md`.

**THE TWO UNSUFFIXED FILES ARE CORRECT.** `v_mid_expanding_cache.csv` and
`raw_panel_mid_cache.csv` carry no `_r40` because the score panel does not depend
on the rebalance cadence -- it is the model's output, and the cadence governs how
often the book is rebuilt from it. Suffixing them would claim a dependency that
does not exist and would rebuild an identical panel per cadence.

### What this says about the earlier composition claim

Step 3 reported that the three axes compose, citing this exact invocation. That
test ran WARM. It was true of the artefacts produced and false as a claim that
the combination works from a clean checkout -- the run consumed four files it had
not produced. The same caveat applies to the G7 and cadence content sweeps: they
verified CONTENT correctly and could not, by construction, catch a step quietly
reading pre-existing state.

## A cold run found a regression that every warm byte-comparison had passed

Found 2026-09-06 by running the pipeline from `.py` + `data/` alone, with every
generated directory removed and `/tmp` emptied.

**THE DEFECT.** `make_mid_chart.py` and `make_n100_chart.py` gated their canonical
`savefig` on the arm selection BEING exactly `{v2, v1}`:

    if set(ARMS_ON) == {"v2", "v1"} and cadence.is_default():
        plt.savefig(M / "chart_mid_FINAL.png", ...)
    else:
        plt.savefig(M / (... + arm_reg.suffix(ARMS_ON) + ...))

The DEFAULT is `--arm all`, so `ARMS_ON` is all four arms, the `else` branch ran,
and `chart_mid_FINAL.png` / `chart_n100.png` **were never written at all**. Only
the four-arm files were produced. Introduced by a1ab05f.

**WHY EVERY GATE PASSED ANYWAY, AND THIS IS THE PART WORTH REMEMBERING.** The two
canonical charts were still on disk from before a1ab05f. Nothing overwrote them,
so every G1 byte-comparison found them present and unchanged and reported
identical. **A byte-comparison against a directory that already contains the
artefact cannot tell "regenerated correctly" from "not regenerated at all."** The
manifest compares content; it says nothing about provenance.

**Only an empty tree distinguishes the two**, which is exactly what the cold run
provided: 319 of 321 artefacts identical, and the two missing ones named.

**Fixed** by giving both charts the dual-output rule the combined chart already
had: the canonical figure is drawn whenever v2 and v1 are both selected, and the
selection figure is drawn alongside it whenever the selection differs. Both
canonical charts then reproduce **byte-identically** to the pre-regression
baseline, which is what proves the canonical render is unchanged rather than
merely present.

**A STANDING CONSEQUENCE FOR HOW THIS PROJECT VERIFIES ITSELF.** Warm
byte-comparison is necessary and is not sufficient. It catches a changed artefact
and is blind to a no-longer-produced one. Any change to which FILENAME a step
writes needs either a cold run or an explicit check that the file's mtime moved.

## --rebal is a real axis now, and it used to overwrite what it should not have

Implemented 2026-09-06, the third and last selection axis.

**TWO DEFECTS FOUND BY MEASURING, NOT BY READING.**

    --universe mid --arm v1 --rebal 40
        v2FINAL_equity.csv       UNCHANGED  -- the engine ignored --rebal
        runs/mid/v1/comparison.csv  CHANGED -- and REPLACED the cadence-20 result

`--rebal` was half-wired and destructive where it worked. The engines carried
their own `REBAL = 20` and never consulted the flag, so every pipeline artefact
stayed at cadence 20; the arm run honoured it and wrote into `runs/mid/v1/`,
whose path says nothing about cadence. `params.json` recorded `rebal: 40`, so the
FILE said what it was while the PATH said otherwise.

**ON THE FROZEN UNIVERSES IT WAS WORSE.** `--rebal 40 --universe 58` was
silently accepted and overwrote `runs/58/v1/` with cadence-40 data, on a universe
whose published numbers must not move. Checksummed before and after.

**WHAT IT DOES NOW.** The cadence reaches the pipeline -- engines, v34, the audit
trails and every chart -- and the canonical/suffix rule applies to all of it:

    --rebal omitted / 20   every published filename exactly as before
    --rebal 40             v2FINAL_equity_r40.csv, v34_comparison_v1_v2_r40.csv,
                           daily_holdings_mid_v1_r40.csv, chart_mid_FINAL_r40.png,
                           runs/mid/v1@r40/ ... and the canonical files untouched

**FROZEN UNIVERSES ARE REFUSED, NOT SILENTLY RUN AT 20.** Both halves: the arm
runs AND the whole pipeline. Running the 58 at 20 under a `--rebal 40` request
answers a different question from the one asked, so it is dropped with a reason
on stdout. Refusing the arm runs while letting the pipeline through was an
inconsistency this work introduced and then removed -- measured: three 58 files
appeared from a run that asked for 40.

**THE CADENCE IS A PARAMETER, NEVER A MODULE GLOBAL.** `cadence.py` records it
and every engine passes `rebal=` to `backtest_exposure`. `test_exposure.REBAL` is
never reassigned. module_state.py names why: `rebal_cadence_sweep.py:172` sets
that global and never restores it, and "every later step would silently backtest
on the wrong rebalance cadence and nothing would say so".

### Two bugs the sweeps caught that reading the code would not have

**A file named for one cadence whose contents claimed another.**
`v2FINAL_params_r40.json` recorded `rebalance_days: 20`, because the engine wrote
the module constant instead of the cadence it ran. The name looked right, which
makes it the worse of the two possible errors. Caught by reading the produced
JSON across five cadences, not by inspecting the writer.

**A published summary overwritten by a narrowed arm selection.** Found while
baselining this step: `make_final_summary.py` read `fair_comparison_table_v1.csv`
and wrote the CANONICAL `FINAL_SUMMARY_TABLE.csv`, so `--arm v1` silently replaced
the published summary with a one-arm one. That was a defect in a1ab05f, fixed
here.

### Gates

    G1  321 of 321 byte-identical at the default, nothing missing, nothing changed
    G3  identity gate re-run: ok, no gate re-baselined
    G5  92 of 92 on all eight combinations
    G6  42 resolved / 9 unresolved / 0 inversions -- held through every change,
        because cadence-dependent writers keep the literal in the call:
        `_c(M / "v2FINAL_equity.csv")`, not a precomputed name
    G8  no 58 or 74 artefact changed under any cadence
    cadence sweep  five cadences (omitted, 5, 10, 40, 60), verified by READING
        the produced params files: each records its own cadence, no artefact is
        named for another, and the canonical params still say 20
    composition  --universe mid,58 --arm v1,v3 --rebal 40 produces only mid
        artefacts, every one carrying r40, canonical untouched, and both 58
        combinations refused with their own distinct reasons

## --arm is reflected in every chart that can carry it; two limits remain

Completed 2026-09-06, closing the gaps the entry below records. It supersedes
that entry's GAP 1 and GAP 2; the entry is kept as the record of why they existed.

**WIDENING IS ALLOWED, BUT ONLY INTO SUFFIXED FILENAMES.** The canonical
unsuffixed figures are the v2+v1 published pair and are produced exactly as
before, byte for byte. Anything else the run selects is drawn into a file named
for that selection:

    --arm all      chart_COMBINED_n100_mid_58_74.png        (canonical, v2+v1)
                   chart_COMBINED_n100_mid_58_74_v1_v2_v3_v4.png   (all four)
                   chart_mid_FINAL.png / chart_mid_FINAL_v1_v2_v3_v4.png
                   chart_n100.png     / chart_n100_v1_v2_v3_v4.png
    --arm v3       chart_COMBINED_..._v3.png, chart_mid_FINAL_v3.png -- DRAWN,
                   showing v3. It no longer skips with a reason.
    --arm v1,v3    ..._v1_v3.png, and no canonical, because the pair is not
                   fully selected.

**THE v1 TRADE-LOG LEAK IS CLOSED**, and how it was closed matters. `--arm v2`
used to write daily_trades_v1_<tag>.csv. Gating that write had failed once,
because STEP 10d demanded the file unconditionally through
run_all.REQUIRED_INPUTS. Those entries now carry a third field naming the arm
they belong to, and check_inputs skips an entry whose arm is not selected. **The
paths stay literal in the same shape**, so check_pipeline_order's static
inventory is untouched -- 42 resolved, 9 unresolved, 0 inversions, unchanged.
Only the RUNTIME requirement became conditional.

### LIMIT 1: the fair chart cannot widen, and this is structural

`make_final_chart_fair.py` ran only on the retired 58 and 74 — both deleted on
2026-09-11, the script with them — and **those
universes have no v3/v4 curve anywhere on disk** -- their engines never call
v34_common. Selecting v3 or v4 cannot add a line there because there is no line
to add. The step now says so on stdout and writes no `_v1_v2_v3_v4`-named file,
because a filename promising four arms while showing two is worse than no file.
So "`--arm all` produces a four-arm version of EVERY chart" holds for the
combined, midcap150 and nifty100 charts and cannot hold for this one.

### LIMIT 2: v2FINAL_* still carries both v1 and v2 regardless of selection

Spec Step 5 -- the engine computing only the selected arms -- **was attempted and
stopped under the spec's own decision rule.** The engine feeds five published
artefacts from v1 and v2 (v2FINAL_comparison/yearly/equity/params and
chart_v2FINAL.png). Conditionalising it means giving all five the
canonical/suffix treatment, and then **eleven reader files** must learn to find
the suffixed names: n100_jackknife, attribution_v2, audit_step,
diagnose_cash_drag, make_combined_universes, make_final_chart_fair,
make_mid_chart, make_n100_chart, reality_check, test_v1_v2_blend and v34_common.

There is no safe subset of it either: both curves feed the canonical artefacts,
which are written on every run, so neither computation can be skipped while the
canonical files are still produced. The benefit is one skipped backtest and one
unused column; the risk is moving a published number across five artefacts and
eleven readers. **Stopped and reported rather than proceeded**, which is what
rule 4 and experiments/ARM_SUBSET_SPEC.txt both require.

### Gates, re-verified after every change

    G1  318 of 318 byte-identical, nothing missing, nothing CHANGED
    G3  identity gate re-run: ok, and no gate re-baselined -- they read
        v34_comparison.csv, which is byte-identical
    G5  92 of 92 on all eight combinations
    G6  42 resolved / 9 unresolved / 0 inversions
    G7  nine selections, artefacts READ not code: Config rows, equity column
        headers, params.arms maps and audit-trail filenames all show exactly the
        selected arms
    G8  no 58 or 74 artefact changed under any selection

The three artefacts added by `--arm all` are exactly the four-arm charts.

## --arm reaches the published outputs; two gaps remain, both recorded

Implemented 2026-09-06 under `experiments/ARM_SUBSET_SPEC.txt`. This supersedes
the boundary the entry below describes -- that entry is kept because it is the
record of why the boundary existed.

**WHAT NOW FOLLOWS THE ARM SELECTION.** `v2FINAL_equity.csv` carries arm-keyed
columns (`v1_invvol_none`, `v2_invvol_breadth`) on the live universes; all nine
readers go through `arms/registry.equity_series`; the combined chart, the fair
chart and the final summary plot the selected arms; and a per-arm audit trail is
built for every selected arm -- `daily_*_<tag>_<arm>.csv` -- each reconciled
against the engine's own recorded curve for that arm.

**THE FROZEN 58 AND 74 STILL WRITE `strategy`/`baseline_invvol`, permanently.**
Their engines are those universes' provenance and are not modified, so
`equity_series`' fallback is not a transition shim awaiting deletion -- it is how
a frozen universe's file is read.

**NARROWING, NOT WIDENING.** The combined and fair charts compare through the
SHIPPING arms (v2 and its v1 control). A selection narrows them; it never widens
them. Plotting every selected arm would put four lines per universe on the
published figures under the default `--arm all`, changing a published figure as a
side effect of a structural change, which the spec forbids (G1). So `--arm v3`
draws neither chart and says why: v3 and v4 are measurement arms and their
comparison is `chart_v34`. **A narrowed arm selection writes suffixed files** --
`chart_COMBINED_n100_mid_v2.png`, `fair_comparison_table_v1.csv` -- and leaves the
published ones untouched, the same rule the universe axis uses.

### GAP 1: make_mid_chart.py and make_n100_chart.py are NOT arm-aware

The two per-universe published charts still plot v1 and v2 unconditionally. They
were not converted, and that is the honest state.

### GAP 2: daily_trades_v1_<tag>.csv is written even when v1 is not selected

`--arm v2` still produces a file named for v1. **Gating it was tried and
reverted**, and the reason is worth recording: STEP 10d `make_<tag>_chart.py`
declares that file in `run_all.REQUIRED_INPUTS` as a hard edge, so a gated write
makes `--arm v2` die at `check_inputs` with a missing file. Removing the edge
would weaken the static contract and cost the checker a resolved dependency, which
the spec's G6 forbids. The two gaps are the same gap: closing GAP 2 requires
closing GAP 1 first.

### The gate results, in full

    G1  default reproduces the baseline    280 of 282 byte-identical, nothing
                                           missing; the two exceptions are the
                                           v2FINAL_equity.csv files, whose columns
                                           this change is about
    G2  curves untouched                   every new column .equals() the old one
                                           it replaced, exactly, on both universes
    G3  seven identity gates               NOT re-baselined and did not need to be:
                                           they read v34_comparison.csv, which is
                                           byte-identical, so they cannot see this
                                           change. purge_fix_measure re-run: ok
    G4  v34 measurement untouched          v34_comparison/equity/chart identical
    G5  Nautilus                           92 of 92 on all eight combinations
    G6  static checker                     42 resolved / 9 unresolved / 0 inversions
    G7  no unselected arm leaks            clean except GAP 2
    G8  frozen universes                   every 58 and 74 artefact identical

**G6 FAILED FIRST AND WAS FIXED, WHICH THE SPEC PREDICTED (P4).** Routing
`fair_comparison_table.csv` through a computed `TABLE_NAME`, and `v2FINAL_equity.csv`
through `Path(M) / "..."` instead of `M / "..."`, made three edges vanish from the
scanner while the code ran perfectly: 42 resolved fell to 40. The canonical names
are now written as literals on the common path, with the suffixed form only in the
`else` branch.

## --arm subsets the v34 MEASUREMENT only; v1/v2 still ship in every run

Recorded 2026-09-06, when `--arm` gained subset selection. This entry states the
boundary deliberately, because the obvious reading of "unselected arms must not
appear in outputs" is not what the code does, and the reason is structural.

**WHAT --arm NOW CONTROLS.** Any subset of `{v1, v2, v3, v4}`, defaulting to all
four. It selects:

    runs/<universe>/<arm>/          one directory per selected combination
    v34_comparison_<sel>.csv        only the selected arms, plus buy & hold
    v34_subperiods_<sel>.csv
    v34_equity_<sel>.csv            one column per selected arm
    v34_params_<sel>.json           its `arms` map lists only what was measured
    chart_v34_<sel>.png             title and colours derived from the selection

A FULL selection writes the canonical unsuffixed `v34_*` files exactly as before.

**WHAT IT DOES NOT CONTROL, AND WHY.** `v1` and `v2` are not only measurement
arms. They are the SHIPPING strategy and its always-invested control, computed by
each engine and written as the `strategy` and `baseline_invvol` COLUMNS of
`v2FINAL_equity.csv`. So on any run at all:

  - `v2FINAL_*` is written with both, regardless of `--arm`;
  - the daily audit trail is v2's — `audit_step.run()` hardcodes `mode="breadth"`
    and ASSERTS its equity against `v2FINAL_equity.csv["strategy"]`, and
    `make_daily_log.py` is headed "v2 FINAL (breadth-scaled)";
  - the combined chart, `make_final_chart_fair.py` and `make_final_summary.py` read
    those two columns and know nothing of v3/v4, which live in a different file.

**So `--arm v3` still produces artefacts showing v1 and v2.** That is the honest
statement of the current boundary. Making it otherwise means restructuring
`v2FINAL_equity.csv` into per-arm columns and re-pointing eight consumers, which
moves published artefacts and is deferred to its own step.

**THE CANONICAL v34 TABLE IS NEVER OVERWRITTEN BY A SUBSET, and that protects
seven gates.** `purge_fix_measure`, `seed_noise_measure`, `seed_noise_report`,
`shuffle_test`, `validate_topn`, `rebal_cadence_sweep` and `drawdown_exit_measure`
all read `v34_comparison.csv`, and six assert their own control against its **v2
row**. A two-arm subset overwriting that file would leave all six comparing against
a table without their reference, and they would fail later, elsewhere, as a missing
row rather than as this run's doing. A subset writes its own selection-named file
and leaves the canonical one alone — the same rule the universe work adopted.

**`make_v34_report.py` is unaffected and intentionally so.** It is not a pipeline
step; it reads the canonical four-arm table and quotes `V34_SPEC.txt` predictions
that compare v2 against v4 and v1 against v3. Those comparisons have no meaning on
a subset, and since a subset never overwrites the canonical table, the report keeps
reading the four-arm measurement it was written for.

**Frozen universes have no v3/v4 at all.** `arm_steps()` drops those combinations,
and as of this change the run announces them under a NOT RUN heading instead of
silently doing three of the four things it was asked for — which is what
`--universe mid,58 --arm v1,v3` did before.

## The combined chart is per-selection, and the published pair chart is always drawn

Recorded 2026-09-06, when `make_combined_n100_mid.py` became
`make_combined_universes.py` and started comparing whichever universes the run
selected instead of a hardcoded pair.

**What each selection produces:**

    --universe mid          nothing; one universe is not a comparison
    --universe mid,58       chart_COMBINED_mid_58.png
    --universe n100,mid     chart_COMBINED_n100_mid.png                 (one file)
    --universe n100,mid,58  chart_COMBINED_n100_mid_58.png  AND  chart_COMBINED_n100_mid.png
    --universe all          chart_COMBINED_n100_mid_58_74.png  AND  chart_COMBINED_n100_mid.png

**TWO RULES, NOT ONE.** The N-way chart answers "how do the selected universes
compare" and its filename names exactly the selection. The nifty100+midcap150 pair chart
answers a different, standing question -- "how do the two live universes compare"
-- and it is the figure `docs/README.md` embeds and the top-level README displays.
It is refreshed whenever BOTH its universes are in the selection, not only when
they are the whole of it, because that second question does not stop being asked
because a retired universe was also run.

**AN INTERMEDIATE VERSION GOT THIS WRONG AND IT IS WORTH RECORDING.** For one
commit, `--universe all` wrote only the four-universe chart, on the reasoning that
"exactly one chart across exactly the selection" was the whole rule. That left the
docs copy stale after every full run with nothing saying so -- the file was not
overwritten with different numbers, it simply stopped being written, which is the
harder failure to notice. The fix was not to choose between the two charts but to
recognise they answer different questions.

**At N == 2 the pair chart is not drawn twice.** When the selection IS nifty100+midcap150,
the N-way chart already writes exactly that file; the extra pass is skipped rather
than rendering the same figure to the same path.

**BOTH CHARTS COME FROM THE SAME LOADED ROWS**, so they cannot disagree about a
number, and the pair chart's subtitle is derived from the universes ON THE FIGURE
rather than from the selection. That is what makes it reproducible: "58 and 74 are
out of scope and are not plotted" does not change depending on whether 58 and 74
also ran. Verified: `chart_COMBINED_n100_mid.png` is byte-identical to the
pre-change baseline under `--universe all`, `--universe n100,mid,58` and
`--universe n100,mid` alike.

**WHAT THAT VERIFICATION IS EVIDENCE OF, NARROWED 2026-09-12. It is still true,
and it now certifies less than it reads.**

The byte-identity result is sound and stands. It establishes SELECTION-INVARIANCE:
the plotting code emits the same figure whether or not 58 and 74 were also in the
run. Nothing since has disturbed that, and the same-session method was the correct
control for it — see the caveat below, which is about a different axis and does
not weaken this one.

**BUT "the same loaded rows" was never shown to be a KNOWN set of rows.** The
withdrawal of 2026-09-12 established that `make_combined_universes.py` reads
`v2FINAL_equity.csv`, `v2FINAL_params.json` and the trade logs **by canonical name
with no arm, cadence or profile suffix** — bypassing even the `_ci` helper in its
own file. So the rows it loaded came from whichever run wrote those filenames
last, on any of the four axes, and the chart recorded nothing about which run that
was.

**The claim survives; its subject does not.** This entry proves the chart
faithfully and invariantly reproduces a panel whose identity was never recorded.
That is a real property of the plotting code and a worthless guarantee about the
figure, and the two were not distinguished when this was written. **A
reproducibility result about an unidentified input is not a provenance result**,
and this one was read as though it were.

It becomes evidence again — unchanged, re-run, not re-argued — once the producer
reads through the naming authority and the figure can say what it plots.

**Caveat on every byte-identity claim above.** They are SAME-SESSION results, and
the next entry records that this specific PNG has drifted by two pixels of height
ACROSS sessions on identical inputs. The comparisons are valid against that known
limit and no stronger.

## chart_COMBINED_n100_mid.png is not byte-reproducible across sessions

Found 2026-09-04. The step that draws it -- `make_combined_universes.py`, which was
`make_combined_n100_mid.py` until 2026-09-06 -- saves with `bbox_inches="tight"`, and
the tight bounding box has been observed to differ by two pixels of height (1764 vs
1766) between sessions on identical inputs and identical code. The same file run
twice in one session is stable, so this is not run-to-run noise -- it drifts across
process invocations over time. The trigger was not identified; the matplotlib font
cache predates both runs. Nothing else about the chart changes and every printed
figure is identical. It matters only for byte-comparison: this PNG cannot be used
as a fixture.

---

## Four verification claims describe an older engine than the one that ships

Written 2026-09-13. **Open, all four.** These had been queued since the
KNOWN_ISSUES rewrite and never landed, which is why the entry after this one
opened by referring to four items that were not in the file. A record asserting
its own completeness on a base that is missing is the same defect this file spends
the rest of its length auditing.

**THE SHARED CAUSE.** Each of the four is a VERIFICATION claim -- a gate, a
reconciliation, a significance test -- that was true when it was measured and now
describes an engine older than the one that ships. None of them is a wrong number.
Each is a correct number about a configuration that has since moved: the price
basis became `adj_close` (`092ee62`), the window shortened, the profile axis
arrived. The failure mode is uniform: **the claim is still printed in the present
tense.**

### 1. The return edge is inside the seed noise it is measured through

The published edge against buy & hold is **+0.43 CAGR on nifty100 and +0.89 on midcap150**.
The seed-noise sd at K=10 is 1.07 and 1.01, so those edges are **0.40 sigma (nifty100)
and 0.88 sigma (midcap150)** -- both below one standard deviation of the ensemble's own
run-to-run variation.

The figures are in the table under *"Why the headline +0.43 does not resolve"*
above. What is missing is the plain statement: **the shipping arm's return
advantage is smaller than the noise floor of the method that produced it.** It is
not a measured edge that happens to be small; it is a number the measurement
cannot separate from zero.

The denominator is `diagnostics/seed_noise.txt`, whose own standing is recorded
two entries below -- it is the weakest-cleared of the fifteen artefacts checked for
profile contamination, cleared by inference rather than reconciliation.

### 2. The drawdown advantage does not survive its exposure control

Reported as a drawdown win against a fully-invested benchmark. Against a null that
controls for exposure it is not significant on either universe:

```
            realDD   nullDD med   p(DD)
n100  v2    -18.38      -20.12   0.3564
mid   v2    -15.68      -19.29   0.1188
```

**Random selection through the same breadth rule reproduces 91% of nifty100's drawdown
advantage and 83% of midcap150's.** The exposure rule alone captures **92.5% and 92.7%**
of the benefit; selection adds **1.46 and 1.53 points** against the 19.41 and 20.86
the record quotes versus a fully-invested benchmark.

**And the whole number is set in one month.** Four of the six best market days for
nifty100 are post-crash rebounds, three of them in March and April 2020, with mean
capture 0.28x at mean invested 40.0% against a window mean of 67.8%. The rule
avoids the crash and avoids the recovery; that is one mechanism with a cost and a
benefit, not a drawdown result and a separate return result.

**The spec predicted this in advance** -- *"exposure is score-independent"* -- and
the shuffle file records *"the prediction is BORNE OUT"* on both universes. The
prediction landing is not the same as the claim holding.

**THE SAME FINDING FROM THE OTHER SIDE: turn the exposure rule OFF and almost
nothing is left on midcap150.** v1 is v2's selection with breadth scaling off, held at
100% deployment. Measured against the fully-invested benchmark:

| | b&h MaxDD% | v2 MaxDD% | v2 advantage | v1 MaxDD% | v1 advantage | share surviving full exposure |
|---|---:|---:|---:|---:|---:|---:|
| midcap150 | −36.54 | −15.68 | **20.86** | −35.88 | **0.66** | **3%** |
| nifty100 | −37.79 | −18.38 | **19.41** | −31.92 | **5.87** | **30%** |

Source: `forensic_snapshot_20260911T0100/results_{mid,n100}/metrics/v34_comparison.csv`,
which is where the only surviving `v34_comparison.csv` pair lives -- `results/metrics/`
is empty and the live universe directories are gitignored.

**On midcap150, 97% of the drawdown advantage is the cash rule and not the selection.**
Hold the same names at full deployment and the drawdown goes back to the
benchmark's: −35.88 against −36.54. nifty100 is the milder case at 30% surviving, and
the asymmetry is itself unexplained.

This is a different cut of the same finding, not a replacement for the 92.5% /
92.7% figures above. That one holds exposure fixed and asks what selection adds;
this one removes exposure entirely and asks what selection retains alone. They
agree, and neither is independent evidence of the other.

### 3. The universe where the cap binds is the one with no tradeable audit trail

**CORRECTED 2026-09-13, THE SAME DAY IT WAS WRITTEN. The first version of this
item asserted that nifty100 "has never been run tradeable at all" and that "no v2
audit trail exists under tradeable on either universe." BOTH WERE FALSE**, and
the correction is recorded here rather than by silently replacing the text,
because the way it became false matters more than the claim did.

**HOW IT BECAME FALSE.** The claim came from a survey that listed
`results_mid/metrics` and `results_n100/metrics` -- the live tree -- and did not
look at `forensic_snapshot_20260911T0100/`. That snapshot is excluded by
`SKIP_PREFIX = ("forensic_snapshot_",)` in the discovery scripts written for the
naming audit, where excluding it is correct: snapshot copies would be phantom
write sites. Carrying that exclusion into a question about *what has ever been
run* was wrong. **This is the third occurrence of that same exclusion in one
session, and the first that reached a committed record.** The first two were
caught before landing: a claim that no `v34_comparison.csv` survives on disk, and
a claim that the v1 drawdown share could not be sourced. Both were in the
snapshot. So was this.

**WHAT IS ACTUALLY ON DISK.**

| | live tree | snapshot 2026-09-11 01:00 |
|---|---|---|
| nifty100 tradeable artefacts | **0** | **33**, including a complete v2 trail |
| midcap150 tradeable artefacts | 11 | 17, trail is **v3 at r200 only** |

**nifty100's tradeable v2 audit trail exists and it RECONCILES.** The snapshot carries
`daily_holdings_n100_tradeable.csv`, `daily_summary_n100_tradeable.csv`,
`daily_trades_n100_tradeable.csv`, `v34_comparison_tradeable.csv` and
`v34_equity_tradeable.csv`. Checked read-only on 2026-09-13: the trail's daily
`total` against the engine's own `v2_invvol_breadth` curve over all **1,836
overlapping days** gives a maximum absolute difference of **Rs 0.0050** -- under a
paisa, which is the tolerance `audit_step` itself requires. Final equity agrees
exactly at Rs 5,047,246.65.

**AND THE REASON THAT RECONCILIATION IS WORTH NOTHING.**

**`v34_comparison_tradeable.csv` is BYTE-IDENTICAL to `v34_comparison.csv` on
nifty100.** Every figure: v1 30.56, v2 24.43, v3 23.14, v4 21.36, buy & hold 24.00,
MaxDD −31.92 / −18.38 / −41.57 / −22.32 / −37.79.

**The participation cap never binds on nifty100.** A tradeable run there reproduces the
research run exactly, so the trail reconciles because there is nothing to
reconcile -- it is an audit of the research configuration wearing a tradeable
filename. `EXPERIMENTS.md:1737-1739` recorded the same inertness under the older
engine: nifty100 unlimited 25.43 against volume 25.42. *(Superseded 2026-09-20:
re-run on the repointed data, nifty100 is 19.00 unlimited against 19.00 volume,
n=940 fills, 3 orders walking. The inertness the sentence is citing holds under
both runs.)*

**On midcap150 the cap does bind, and midcap150 is the universe with no v2 trail.** Research
against tradeable, from the snapshot:

| midcap150 | CAGR% | MaxDD% | Trades | TC_Rs |
|---|---:|---:|---:|---:|
| v1, research | 50.12 | −35.88 | 852 | 839,393 |
| v1, tradeable | **45.90** | −35.88 | 860 | 692,730 |
| v2, research | 29.23 | −15.68 | 1019 | 249,150 |
| v2, tradeable | **27.59** | −15.68 | 1019 | 228,963 |

v2 loses **1.64 CAGR points** and v1 loses **4.22**. Those are the numbers a
tradeable audit would exist to verify, and **the only tradeable `daily_*` trail
midcap150 has ever had is `v3 at r200`** -- a measurement arm at a non-default cadence,
in the snapshot, not the shipping arm and not the shipping cadence.

### CORRECTION 2026-09-20: the cap does not bind on midcap150 either

**The table above is from the snapshot and the tree has moved past it.** Re-measured
at commit `7dd37d6` against the artefacts now on disk, the midcap150 cap fires on
**no fill in either arm**:

- `daily_skipped_midcap150_v1_tradeable.csv` and `daily_skipped_midcap150_tradeable.csv`
  carry **zero** rows with reason `participation cap`, over n=850 and n=1006 fills.
  Every skip in them is `cash short (before TC)`.
- Highest participation any fill reached is **0.709** of its prior-20-session median
  on v1 and **0.345** on v2, against a cap of **1.00**.
- All eight of {`daily_trades`, `daily_skipped`, `daily_holdings`, `daily_summary`}
  x {v1, v2} are **byte-identical** to their unsuffixed research twins, and
  `v34_comparison.csv` carries the same v1 and v2 rows as the two
  `v34_comparison_v*_tradeable.csv` files: v1 CAGR 36.85 / 850 trades / final equity
  10,209,897.06, v2 27.80 / 1006 / 6,150,398.56.

So the sentence "On midcap150 the cap does bind" and the Rs 3.85M cap effect quoted
in `gate_compare.py` are **withdrawn as descriptions of the current tree**. They
describe the snapshot and are kept above as history. **As of this commit neither
published universe has a run in which the participation cap changed a single fill**,
and the two tradeable gate cells replay a configuration the cap did not touch --
which is the same thing this item already says about nifty100.

The correction is written where a reader meets the numbers: `profiles.CAP_INERT_NOTICE`
travels into every tradeable `v34_params{SFX}.json` and is bannered by `run.py`, and
`gate_compare.py`'s register no longer describes the cells as cap-binding.

**This is a dated measurement, not a property.** Capital, universe and data all move
it. Count the `participation cap` rows in the run's own `daily_skipped` artefact
before repeating either claim.

**WHAT THE ITEM REDUCES TO.**

**Neither universe has a reconcilable tradeable audit of a configuration where the
cap changes anything.** nifty100's trail is complete, reconciles to a paisa, and
certifies a run the cap did not touch. midcap150's cap costs 1.64 CAGR points on the
shipping arm and has never been audited at all on that arm. The tradeable figures
are UNRECONCILED, not wrong -- and the check that would settle them has never been
run where it would mean something.

A further consequence, since the live tree no longer carries nifty100's tradeable
artefacts: **that run is not reproducible from the live tree.** It survives only
in the snapshot, which is untracked working-tree state, not a git object.

**AND THE SNAPSHOT'S CANONICAL midcap150 FILES ARE THEMSELVES TRADEABLE OUTPUT. READ
THIS BEFORE READING ANY midcap150 FILE OUT OF THE SNAPSHOT.** Established 2026-09-13 by
a full rebuild. The 11 tradeable artefacts counted above are the ones that SAY
tradeable in their names. They are not the problem. **The problem is the ones that
do not.**

At **2026-09-10 17:14** a `tradeable` run wrote, in the same minute:

| file | name says | contents are |
|---|---|---|
| `v34_comparison_tradeable.csv` | tradeable | tradeable -- correct |
| **`v2FINAL_comparison.csv`** | **research (canonical)** | **tradeable -- WRONG** |
| **`v2FINAL_equity.csv`** | **research (canonical)** | **tradeable -- WRONG** |

`SFX` already composed the profile; `_c` did not until `f6b970b`, 32 hours later.
So the same run named one output correctly and one incorrectly.

**The two are byte-identical in value**, which is what makes the mislabelled pair
undetectable by inspection:

    snapshot v2FINAL_comparison.csv  (17:14)   v1 45.90   v2 27.59   Trades 860 / 1019   TC 692,730 / 228,963
    snapshot v34_comparison_tradeable.csv      v1 45.90   v2 27.59   Trades 860 / 1019   TC 692,730 / 228,963
    snapshot v34_comparison.csv      (16:46)   v1 50.12   v2 29.23   Trades 852 / 1019   TC 839,393 / 249,150
    REBUILD at 8dd4427, research               v1 50.12   v2 29.23

**THE ONLY WAYS TO TELL THEM APART ARE MTIME AND THE SUFFIXED TWIN.** Nothing
inside `v2FINAL_comparison.csv` records the profile -- no column, no header, no
companion JSON field. A reader opening it sees a canonically-named file with
plausible numbers. **This project has done exactly that twice in one week**, once
concluding a rebuild was unstable and once that a figure could not be sourced.

**`RETIRED_UNIVERSES.md` IS NOT AFFECTED, and that is determinable rather than
assumed.** Its 58 table transcribes `results/metrics/v2FINAL_comparison.csv`, which
carries the same 17:14 mtime -- so it needed checking. But `17.01` entered the
tracked record on **2026-08-27 16:31**, the initial commit, and `24.62` on
**2026-08-30**, while the tradeable profile did not exist until **2026-09-10
23:31**. Both figures predate the profile by two weeks. Either the 17:14 run was
research for the 58, or the cap never bound there -- and in the second case the
output is identical to research anyway. Consistent with this, the snapshot holds
**zero** tradeable files for the 58 or the 74, whose frozen engines only ever write
old-style names.

**No midcap150 figure quoted anywhere in this repository has been traced to the
mislabelled pair.** The drawdown decomposition that reads the snapshot is built
from `MaxDD`, and `MaxDD` is IDENTICAL across both files for every cell on both
universes -- the two disagree on CAGR only, and only on midcap150. That is luck, not
design.

### 4. The Nautilus certification was taken on a different window and a different price basis

`nt_verify` reports **92 of 92 rebalances on all four arms**, and the per-universe
reconciliation reads 93 of 93. Both were certified **2026-08-27**, and the
configuration they certified is not the one that ships:

| | certified under | ships today |
|---|---|---|
| window | 2019-01-01 → **2026-06-08**, **1,842** trading days | → **2026-05-29**, **1,836** days |
| price basis | pre-`adj_close` | `adj_close` canonical (`092ee62`) |
| calendar | the **58-derived** trading calendar | unchanged, and the 58 is deleted |
| tick grid | 0.01, a CONTROL configuration | traded grid is 0.05 |

The six-day window difference is not cosmetic: `092ee62` moved every published
figure when the price basis changed, and the certification predates it.

**midcap150 and nifty100 are STALE, RE-RUNNABLE** -- their inputs exist and `nt_verify` can
re-establish them. **58 and 74 are NOT RE-DERIVABLE** -- both universes, their raw
price data and their frozen axis were deleted 2026-09-11, and no figure of theirs
can be reproduced by anything. That distinction is recorded in
`nautilus/NAUTILUS_STATUS.md` and, for the retired pair, in `RETIRED_UNIVERSES.md`.

The calendar line deserves its own note: the NSE trading calendar this project
runs on is derived from the retired 58 universe's raw files, is tracked, and is no
longer rebuildable by anything in the repository.

### What survives all four

**The shuffle result.** Against random selection, CAGR gates at **p = 0.0099 on
both gated arms and both universes** -- no draw in 100 beat it. That is a real
result and it is not touched by anything above: it tests selection against a null
that holds every mechanic fixed, so the window, the price basis and the profile
cancel out of it.

**Read with two limits, both already recorded above.** The p is the test's floor,
`(1 + 0)/(100 + 1)`, not a measurement -- it cannot express anything smaller. And
**multiplicity is uncorrected**: `shuffle_verdict.txt` records the configuration
was chosen after at least 26 trials on this same data, so the test measures the
winner on the data it won on. Raising N lowers the floor and does not touch the
bias.

**The remedy is named and it is not more shuffles.** It is held-out data, or a
pre-registered configuration tested once. `experiments/HELDOUT_PREREG.txt` is that
pre-registration, written 2026-09-12 before any data after 2026-05-29 was
examined, and **it has not been run**. The window it reserves is spendable exactly
once.

---

## Two readers could mislabel a published curve, by opposite routes, at the same time

Written 2026-09-13. Both are fixed; **neither had been recorded anywhere until now,
and that is the first thing to say.** `_ci` appears once in this file, in passing,
inside the chart-withdrawal item. `arm_sources` and "fail-closed" appear zero
times. The two most consequential reader defects found this week -- the ones that
would have put the wrong curve on a published chart under the right label -- lived
only in commit messages and in the code's own docstrings. This entry is not a
tidying of an existing record; it is the record, arriving late.

### The same outcome, reached two ways

Both routes end at a chart whose curve does not match its title. They fail in
OPPOSITE directions, through different readers, and **both were live in the same
code path feeding the same three charts.**

| | route A -- `_ci` | route B -- `arm_sources` |
|---|---|---|
| where | inside each chart module | the module the charts read through |
| composed | cadence only | neither axis on the profile; cadence only on the curve |
| on a miss | fell through to the canonical file | fell through to the canonical file |
| under `--profile tradeable` | plotted **research** curves under a **tradeable** title | handed **tradeable** data to a chart labelled **research** |

`make_combined_universes.py`'s `_ci` composed `cadence.suffix()` alone while the
two same-named helpers in `make_mid_chart.py` and `make_n100_chart.py` composed
`cadence.suffix() + profiles.suffix()`. Three functions, one name, two behaviours.
`arm_sources.equity_path_and_series` composed the cadence and never the profile,
then fell through to the unsuffixed name; `trades_path` tried four candidates and
ended at an unsuffixed one.

**In every case the substitution was unrecorded.** `equity_path_and_series`
returned the path it used and all four callers bound it to `_`, so nothing in any
output said which file had been plotted.

### Why route B survived the audit that found route A

Route A was found by the naming audit of 2026-09-12, which enumerated every
artefact WRITER and made each declare its axes. Route B is a READER, and **nothing
measured readers.** The audit's own gate, `naming_declare_check.py`, discovers
`to_csv`/`savefig`/`write_text` call sites. A reader resolving a filename is
invisible to it.

That asymmetry is the transferable part: **a naming authority that governs writers
and not readers closes half the loop.** The composed name being correct does not
help if the thing reading it accepts a different file when the correct one is
absent.

### And route B is why the missing-log crash became reachable

`make_mid_chart.py`'s `before_tc` returned `(None, 0.0, 0)` for a missing trade
log -- fixed 2026-09-13, having been fixed in `make_n100_chart.py` by `baa5daa` a
day earlier and never back-ported. It could not fire while `arm_sources` was
substituting: the reader always found *something*, so the log was never missing.

Making `arm_sources` fail-closed **converted a silent wrong answer into a missing
one**, and `before_tc` then converted the missing one into a fake zero -- printing
"0 trades, Rs 0" for an arm the engine had reported 852 trades for, and dying
thirty lines later formatting the `None`.

**Fixing one reader exposed the defect in the next.** That is not an argument
against fixing it. It is the reason the crash is evidence the fix worked: the
failure moved from silent and wrong to loud and named, one layer at a time.

### The third link, for completeness

The file `arm_sources` correctly reported missing was itself announced as written.
Both engines gated the write on the arm selection and left the print outside the
condition, so `--arm v3` logged `v1 baseline trade log: 852 trades, TC Rs 839,393
-> daily_trades_v1_mid.csv` and wrote nothing. Fixed 2026-09-13.

**That one was identical in both engines -- not a fix applied to one sibling and
not the other.** Worth stating against the rest of this record, where the midcap150/nifty100
pairs diverge: **duplication copies defects as faithfully as it hides
divergence**, and the ten duplicated modules do both at once.

---

## The vendor ships a gap flag and a quality score, and nothing reads either

Measured 2026-09-13, read-only. **Neither is a defect on its own. One is inert and
one is not, and the difference was never checked.**

### `_gap_filled` does not mark what `tradability.py` looks for

The vendor flags rows it synthesised. This project built `tradability.py` to infer
holes by asking whether a raw row existed. **They are disjoint by construction** —
a vendor-filled row is PRESENT, so the inference cannot see it; an absent row has
no flag to carry.

Measured:

| | `_gap_filled=1` rows | inside window | **on the trading calendar** | `tradability.gaps()` interior gaps |
|---|---:|---:|---:|---:|
| midcap150 | 840 across 79 symbols | 31 | **0** | 46 gaps, 3 symbols, 1,193 sessions |
| nifty100 | 1,253 across 73 symbols | 2 | **0** | 0 |

**EVERY FLAGGED ROW IS OFF-CALENDAR.** They carry `open == close == adj_close` with
fabricated volume and land on non-trading days — PATANJALI's 24 include Christmas
2020 and Republic Day 2021. The panel is built over calendar sessions, so the
backtest never selects one.

**AND NONE OF THE FIVE KNOWN ARTEFACTS IS FLAGGED.** MEDANTA 2022-11-16, 360ONE
2019-09-19, SBICARD 2020-03-16, PATANJALI 2020-01-27 and YESBANK 2020-03-17 are all
on-calendar and all `_gap_filled=0`.

**So the flag neither confirms nor contradicts the gap work.** It is not
independent corroboration, and `tradability.py` is not redundant: it finds a class
the vendor does not mark.

### The synthetic rows themselves, and what is actually protecting us from them

**2,093 fabricated rows sit in the price data**, and the flag is how we know:

| | `_gap_filled=1` rows | symbols | inside the backtest window | on the trading calendar |
|---|---:|---:|---:|---:|
| midcap150 | **840** | 79 of 148 | 31 | **0** |
| nifty100 | **1,253** | 73 of 99 | 2 | **0** |

Each carries `open == close == adj_close` — a flat bar — with **non-zero volume**
that no one traded. PATANJALI's 24 include Christmas Day 2020 and Republic Day
2021.

**THE PROTECTION IS THE CALENDAR FILTER, NOT A CHECK.** Nothing in this pipeline
tests `_gap_filled`, rejects a flat bar, or questions a volume figure. The panel
happens to be built over NSE trading sessions, and these rows happen to fall
outside them, so they are never selected. **Change the calendar, widen a window, or
take a vendor extract whose synthetic rows land on trading days, and every one of
them becomes a tradeable bar with fabricated volume** — and `median_volume()` feeds
the `tradeable` profile's participation cap directly from that column.

**THIS IS THE SAME SHAPE AS THE BENCHMARK PROBLEM RECORDED ELSEWHERE IN THIS FILE.**
The buy & hold is protected from three of the five price-hole artefacts by a window
boundary rather than by the tradability guard; the synthetic rows are protected by a
calendar filter rather than by any check on the flag that marks them. In both cases
the outcome is correct and the mechanism is incidental. **An incidental mechanism
is not a control, and it does not survive a change nobody connected to it.**

### `_dq_score` is unread, reaches held positions, and is not about small names

Per-row quality score, 0.62–1.00, in-window and on-calendar:

| | below 0.9 | below 0.8 | below 0.7 |
|---|---:|---:|---:|
| midcap150 (240,625 rows) | 45,034 — **18.72%** | 9,483 — 3.94% | 5,305 — 2.20% |
| nifty100 (171,625 rows) | 44,965 — **26.20%** | 13,516 — 7.88% | 7,369 — 4.29% |

**It reaches the book.** Against the shipping arm's own holdings:

| | held rows < 0.9 | share of held VALUE | held rows < 0.8 | share of value |
|---|---:|---:|---:|---:|
| midcap150 | 3,086 — 18.06% | **10.70%** | 221 — 1.29% | 0.83% |
| nifty100 | 3,903 — 22.44% | **17.86%** | 826 — 4.75% | 4.45% |

**On nifty100 roughly one held rupee in six sits on a row the vendor scored below 0.9,
and nothing consults the score.**

**THE LOW SCORES ARE NOT ON OBSCURE NAMES**, which is what makes this hard to
dismiss as an illiquidity proxy. Worst offenders below 0.8 are ITC, VEDL, TMPV,
COALINDIA, SIEMENS, ONGC, BPCL, GAIL on nifty100; HEROMOTOCO, M&MFIN, OFSS, NMDC,
HINDPETRO, PETRONET on midcap150. Several are names with dense corporate-action history,
which would fit a source-disagreement or reconciliation score, but **the scale is
undocumented and no file in this repository says what `_dq_score` measures.** The
counts fall steadily from 2019 to 2026, consistent with older data being harder to
reconcile across three vendors.

**Not filtered, not fixed, nothing published.** Acting on an undocumented score
would be worse than ignoring it. What is recorded here is that it exists, that it
is unread, and how much of the book it touches — so the decision is a decision
rather than an omission.

---

## The parked survivorship measurement was taken on a price basis the engine does not use

Found 2026-09-13, read-only. **This is a precondition on the largest parked item in
the project, not a footnote.**

Survivorship is the open item that has been deferred since the start, and PIT
membership is the single largest measured hit to any result in this record: **midcap150
v1 from +19.03 to +9.68**. Those slices were computed against
`data/raw/N100_Survivorship/clean/`. **The shipping engine never reads that tree.**
`config_n100.py` resolves nifty100 to `data/raw/nifty100_benchmark/`, and
`results/test_survivorship.py` is the only consumer of the survivorship tree.

### The two trees are not the same prices

Extracted three days apart -- nifty100 `2026-07-20`, survivorship `2026-07-23` -- with
the same three vendors, and they differ on **70 of 99 shared symbols**:

    shared symbols             99
    overlapping dated rows     481,118
    rows where adj_close differs   28,568
    rows where close differs       28,753
    rows where _dq_score differs   22,379

`close` itself differs, not only an adjustment column.

**IT IS NOT VENDOR DISAGREEMENT, and that was the first hypothesis.** On TRENT,
**2,642 rows were drawn from the SAME vendor by both trees and the price agrees on
0.00% of them.** On VEDL, 4,901 same-vendor rows, 19 agree. The difference is
applied after the vendor data, by the build.

**IT IS CORPORATE-ACTION BACK-ADJUSTMENT, and the repository names the action.**
`data/reference/nse_circulars_2019_2026.csv` records a **TRENT bonus issue
effective 2026-06-01 to 2026-06-03** -- after `BT_END_DATE`, before both
extractions. The nifty100 tree carries TRENT's traded prices (2026-05-29 close
**4,224.00**); the survivorship tree carries the bonus-adjusted series
(**2,872.54**), including at the most recent date.

### Whether it changes a return depends on the symbol, and for some it does

| symbol | daily returns differing | max daily diff | cumulative in-window return |
|---|---:|---:|---|
| TRENT | 1,787 of 1,835 | 1.89 pp | +1067.01% both -- **the scalar cancels** |
| VEDL | 1,804 of 1,835 | 6.54 pp | nifty100 **+366.47%** vs surv **+369.41%** -- **0.63% apart** |

A clean scalar cancels out of `pct_change`, which is why TRENT's enormous level
difference leaves the compounded return identical. **VEDL's does not cancel**, so at
least some symbols carry genuinely different returns between the two trees.

### What this means for the parked work

**THE PIT RESULT CANNOT BE CARRIED INTO A LIVE CONCLUSION UNTIL THE BASES ARE
RECONCILED.** +19.03 to +9.68 was measured on a tree whose returns differ from the
engine's for an unknown number of symbols. The measurement is not wrong; it is
**not on the same footing as the figure it would be compared against**, and nothing
in the survivorship record says so.

This does not re-open the survivorship analysis. `SURVIVORSHIP_README.md` records
that work as deferred with a known next step -- acquiring the 186 dropped names'
prices -- and that stands. **It adds a precondition to the step after it:** when
that data lands, the reconciliation question comes first, because a PIT slice built
on one basis and compared against a headline built on another measures the basis
difference as well as the bias.

**Not reconciled here, and no attempt made.** Determining which tree is right for a
backtest ending 2026-05-29 is a data-handling decision -- traded prices as they
stood, or a series back-adjusted for an action that had not yet happened -- and it
belongs with the same unmade decision this file already records for the midcap150
benchmark.

---

## Basename grep is not a reference check

Recorded 2026-09-13, after it produced four wrong answers in one week.

**`grep -F "<basename>"` does not answer "is this file referenced."** It misses
every citation written as a pattern, a stem, or a glob, and this repository cites
things that way routinely.

**The instance that caught it.** A cleanup survey ran literal-basename grep over
every tracked file and reported `nt_verify_after_bartick.txt`,
`nt_verify_after_finalday.txt`, `nt_verify_post_finalday.txt`,
`nt_verify_post_runall.txt` and the three `validate_engine_*.txt` as referenced by
nothing. **All seven are cited.** `nautilus/NAUTILUS_STATUS.md` names them as
`diagnostics/nt_verify_*.txt` and `KNOWN_ISSUES.md` cites `validate_engine_` by
stem. Neither spelling contains a full basename, so neither could match.

**FOUR INSTANCES THIS WEEK, three of them the same exclusion rather than the same
pattern.** A scan that skipped `forensic_snapshot_20260911T0100/` concluded in turn
that no `v34_comparison.csv` survives on disk, that the v1 drawdown share could not
be sourced, and that nifty100 had never been run tradeable -- the third reached a
committed record and had to be corrected in place. The fourth is this one.

**What a reference check must cover.** Every tracked file, plus `diagnostics/`,
`docs/`, `experiments/`, every tracked `.md`, and the snapshot -- and it must match
STEMS and GLOBS, not just full basenames. A directory excluded because it is noisy
for one question is not excluded for the next one. **The exclusion list belongs to
the question, not to the tool.**

---

## The score panels are gone from every location, and that prices every rebuild

Found 2026-09-13 by a cleanup survey. **Nothing to fix; this is what it now costs
to run anything.**

There is no score panel anywhere:

    mid   score_cache  MISSING  results_mid/metrics/v_mid_expanding_cache.csv
    mid   score_tmp    MISSING  /tmp/v_mid_expanding.csv
    n100  score_cache  MISSING  results_n100/metrics/v_n100_expanding_cache.csv
    n100  score_tmp    MISSING  /tmp/v_n100_expanding.csv

**Not in the live tree, not in `/tmp`, and NOT IN THE SNAPSHOT** -- a `find` for
`*cache*.csv` and `*expanding*` across `forensic_snapshot_20260911T0100/` returns
nothing. The snapshot preserved outputs, not inputs.

**WHAT EVERY REBUILD NOW COSTS.** A re-score, before any downstream step:
**about 34 minutes** for both universes -- 18.5 midcap150, 15.7 nifty100, the figures
`docs/HANDOFF.md` measured on 2026-09-12. Every step that resolves its panel
through `config.require_cache` inherits that, including `rebal_cadence_sweep.py`,
both engines and every chart step.

**AND REGENERABLE IS NOT REPRODUCIBLE.** This file already records why, under
*"The headline is not reproducible from the artefacts on disk to better than about
a point"*: the engines score the IN-MEMORY panel and write the CSV as a by-product,
and the two differ by **one unit in the last place -- 4.441e-16 across 2,638,259
cells** -- which is enough to change a split decision, reorder near-tied names at
the `TOP_N = 8` boundary, and move the headline CAGR by about two thirds of a
point.

**MEASURED 2026-09-13, AND THE PARAGRAPH ABOVE IS TOO STRONG AS IT STANDS.**
A full rebuild was run at commit `8dd4427` -- both panels re-scored from raw, 34.0
minutes -- and its output compared against `forensic_snapshot_20260911T0100`:

| series | rows | max abs difference |
|---|---:|---|
| midcap150 `v34_equity` | 1,836 | **0 -- exact** |
| nifty100 `v34_equity` | 1,836 | **0 -- exact** |
| nifty100 `v2FINAL_equity` | 1,836 | **0 -- exact** |
| midcap150 `v2FINAL_equity` | 1,836 | 3.85e+06 |

**Three of four came back bit-identical, and the fourth is not a rebuild
difference at all.** The snapshot's midcap150 `v2FINAL_*` pair is tradeable output
written into canonical filenames -- see *"The universe where the cap binds..."* --
confirmed by mtime and value: `v34_comparison_tradeable.csv` and
`v2FINAL_comparison.csv` both carry mtime 2026-09-10 17:14 and identical figures
(45.90 / 27.59, Trades 860 / 1019, TC 692,730 / 228,963). The rebuild reproduces
the research values the correctly-named file carries.

**WHAT THIS DOES AND DOES NOT ESTABLISH.** It does NOT establish that rebuilds are
deterministic. **One rebuild, one machine, one venv, four series is not that
claim**, and this file has been burned before by reading a single agreement as a
general property. What it establishes is narrower and still worth having: on this
occasion the rebuilt panel reproduced every uncontaminated series exactly, so
"a rebuilt panel is a DIFFERENT panel" is not something to assert without
measuring it again.

**AND THE ORIGINAL ULP OBSERVATION'S SOURCE IS NOW UNKNOWN.** The 4.441e-16 figure
and the "two thirds of a point" consequence are recorded above without a script
behind them, and the rebuild that would have shown the effect did not show it.
**That does not make the original wrong.** It was measured under an engine
configuration that has since changed -- `adj_close` became canonical, the
tradability guard landed, the profile axis arrived -- and the in-memory-versus-CSV
divergence it describes is a real mechanism in code that still exists. What cannot
be said is which of the two observations describes the engine as it ships. Neither
has been re-derived against the other.

**OBSERVED THREE TIMES; THE SECOND IS THE STRONGEST AND THE THIRD THE MOST USEFUL.** The first
observation compared downstream artefacts, where rounding can absorb a small panel
difference. The second cleared `/tmp` and re-scored both universes from raw at
commit `4b906f7` -- 34.5 minutes, a 10-seed LightGBM ensemble over 589,269 and
482,116 rows -- and compared the result against copies preserved earlier the same
day:

```
raw_panel_mid_20.csv     IDENTICAL   (18.3 min, vs 18.2 originally)
v_mid_expanding.csv      IDENTICAL
raw_panel_n100_20.csv    IDENTICAL   (16.2 min, vs 15.8 originally)
v_n100_expanding.csv     IDENTICAL
```

**All four byte-identical -- the panel itself, not a figure derived from it.** That
is the object the 4.441e-16 claim is about, and there is nothing left to absorb a
difference. Recorded in `meta/BASELINE.txt` of the preserved baseline directory.

**OBSERVATION 3, 2026-09-15, and it was spent on a different question.** Step 3 of
the collapse merged the two score-build entry points, and the standing gate cleared
it on cached panels without executing one line of the merged scoring module. A
forced rebuild -- `--fresh`, midcap150 v3, 20.5 minutes -- was run to close that gap, and
both panels came back byte-identical again:

```
raw_panel_mid_20.csv   37b6852b35f0601497827fff8080a8de   before and after
v_mid_expanding.csv    bf0af8676696dd7fc0d85c7927d18a20   before and after
```

The score panel also matches the copy preserved on 2026-09-13, so the same
checksum now spans a module merge as well as two days.

**Three observations on one machine, in one venv, across two days is still not a
determinism claim.** What can now be said is this: the 4.441e-16 divergence has not
been reproduced by any measurement taken since, and the original's source remains
unknown rather than disproved.

**THIS CLAIM LEFT THE REPOSITORY, AND IT WAS WRONG WHEN IT DID.** The first version
of this entry -- the unqualified reading that a rebuilt panel is a DIFFERENT panel
-- did not stay in this file. It was stated to the project's owner as fact, and
repeated by them when they were asked whether this project could be handed to
someone else to run: that the system cannot reproduce its own numbers. On the
evidence now available that was not true, and it was never supported at any point.
The figure behind it had no script, and nobody had checked.

**THE LESSON IS NOT THAT THE FIGURE WAS WRONG.** It is that **an unsourced number
in a record gets quoted as fact.** This file is read as the honest half of the
repository, and that is exactly what makes an unsourced claim inside it expensive:
it travels, and it travels carrying this file's authority. A measurement with no
script behind it must be written as what it is at the moment it is written -- not
qualified two weeks later, after it has already been repeated to someone.

**CROSS-MACHINE IS UNTESTED -- NOT "PROBABLY FINE".** It is an open question, and it
has a shape worth naming, because every item below differs for the next person who
runs this code and **not one of them has been varied here**:

- **a different machine** -- a different CPU and instruction set, and the FMA and
  vectorisation decisions the compiler made for it
- **a different `venv`** -- built from ranges, not pins; `requirements.txt` fixes
  exactly one thing, `lightgbm==4.6.0`
- **a different LightGBM and `libomp` build** -- the pin fixes the version, not the
  wheel it was built into, and not the OpenMP runtime underneath it
- **a different thread count** -- the code caps threads, but the reduction order of
  a histogram build is not guaranteed invariant across a different core count

**Two observations on one machine say nothing about any of these.** They were taken
with all four held fixed, which is precisely the condition under which the question
cannot be asked. **Anyone handed this repository is in exactly that untested
position**, and `docs/HANDOFF.md` flags it as the first thing a new holder of this
code is in a position to establish.

**PRACTICAL READING.** Do not tell anyone the system cannot reproduce its own
numbers; it is not supported, and saying it has already cost this project once. Do
not tell them it can, either. The supported statement is narrow, and it should be
given with its boundary attached: **on this machine, in this venv, panel rebuilds
reproduced byte-identically twice on 2026-09-13, and reproducibility has never been
tested anywhere else.**

**THE TWO THINGS THIS IS ABOUT TO BITE.** Both are currently on hold, and both
carry this risk the moment they are not:

- **the `nt_verify` re-run** for midcap150 and nifty100. It is unblocked -- site 12 no longer
  poisons the destination -- but it will certify against a freshly scored panel,
  not the one the 2026-08-27 figures were taken on, so a difference is expected
  and is not evidence of a port defect.
- **republishing the withdrawn combined chart.** Its producer can now say what it
  reads, but the rows it will read come from a rebuilt panel, so the figure will
  not be byte-identical to the withdrawn one and the numbers on it may differ in
  the second decimal.

Neither is a reason not to proceed. Both are reasons not to read a difference as a
regression.

---

## The two constituent symlink farms ship populated, with absolute paths

Recorded 2026-09-13. **Not changed.**

`data/raw/N100_constituents/` holds **99 symlinks**, every one an absolute path of
the form
`/Users/<user>/Downloads/algo_trading_project/data/raw/nifty100_benchmark/<SYM>.csv`,
dated 2026-08-20. `data/raw/MidCap150/constituents/` is the same construction. Both
report 0 bytes because symlinks carry no content, which is why a size-based survey
walks past them.

`docs/HANDOFF.md` states the two farms **"must ship empty rather than carrying
stale absolute links."** They are not empty. On any machine whose user is not this
one, all 99 links dangle, and `config_n100.py` resolves the universe's tradable
names through that directory -- so the failure lands at universe resolution, not at
a clear "file not found" on a price file.

Left as found. Emptying them is a deliberate act and it changes what a copy of the
working directory can do, which is the distinction this file already draws between
a clone and a zip.

---

## The midcap150 benchmark is better defined than this file said, and the edge is worse

Measured 2026-09-13, read-only, against current data. **This CLOSES the last
escape route for midcap150's return edge, and we closed it ourselves.**

**THE DIRECTION FIRST, BECAUSE THE ARITHMETIC IS EASY TO MISREAD AS GOOD NEWS.**
This file said midcap150's buy & hold denominator was undefined to about four CAGR
points, which left room for the edge to be as large as +5.0 once a data-handling
choice was made. **It is defined to half a point.** So midcap150's return edge is
**+0.89 and nothing else**, and the +5.0 alternative never existed. The
correction makes the return case WEAKER, not stronger. Nothing here rescues it.

### CORRECTED AGAIN 2026-09-13. The 24.23 figure was never wrong; this entry was.

**24.23% IS CORRECT FOR WHAT PRODUCES IT.** The first version of this entry said it
was wrong and should read 27.84%. That was a third wrong answer about the same
figure, and the reason is recorded below because the reason is the useful part.

**THE DEFECT IS A CONFLATION IN CODE, NOT A SLIP IN A DOCUMENT.**
`results/make_mid_chart.py:253-265` prints, in adjoining sentences:

    "The PRICE panel still contains {len(_ext)} single-day moves above 55% ..."
        ... four of them listed ...
    "buy&hold reads {..}% as computed, but {_bh_ex:.2f}% with the six largest
     days neutralised"

`_ext` is the set of **>55% single-symbol artefact moves**. `_bh_ex` neutralises
`_top`, the **six largest equal-weight BENCHMARK days**. They are different sets
and their overlap is **ZERO**:

| set | days | buy & hold after neutralising |
|---|---|---:|
| `_ext` -- the artefact moves | 2019-09-19, 2020-01-27, 2020-03-06, 2020-03-16, 2020-03-17, 2022-11-16 | **28.25%** |
| `_top` -- largest benchmark days | 2019-09-20, 2020-03-20, 2020-03-26, 2020-04-07, 2025-05-12, 2026-04-08 | **24.23%** |

They *should* have zero overlap: one symbol at +548.8% carries 1/148 of an
equal-weight index and moves it about 3.7%, while the largest benchmark days are
broad COVID-rebound moves. **The artefacts were never the largest days.** A reader
takes the second sentence as the consequence of the first, and that is printed on a
published chart, not buried in a comment.

**THE CHAIN, RECORDED AS IT HAPPENED:** chart prose -> reader -> this file. The
conflation was read off the chart output, transcribed into `KNOWN_ISSUES.md:222-226`
as though the six artefact days produced 24.23, and then "corrected" here in the
wrong direction. The prose is fixed in the chart as a separate commit.

### The figures, corrected

| | value | what it measures |
|---|---:|---|
| midcap150 b&h, as computed | **28.36%** | the benchmark |
| neutralising the six ARTEFACT days | **28.25%** | **0.11 pts** -- the artefact sensitivity |
| neutralising the six largest BENCHMARK days | **24.23%** | 4.13 pts -- says nothing about artefacts |

**THE DIRECTION, STATED SO NO ONE READS THIS AS A RESCUE.** The artefact
sensitivity is **0.11 points, not the 4.11 this file first claimed and not the 0.50
the first correction claimed.** The denominator is therefore TIGHTER than either
version said, and midcap150's edge is **+0.89 with less room around it, not more**. Both
sets of numbers were wrong and the conclusion moved FURTHER AGAINST the strategy
each time. Nothing here rescues anything.

`KNOWN_ISSUES.md:222-226`'s *"the same edge is +0.89 or +5.0 depending on a
data-handling choice nobody has made"* is wrong on the artefact question: the
artefact choice is worth 0.11 of a point. The +5.0 alternative never existed.

### What the six moves actually are

All the named moves reproduce exactly through the project's own loader
(`config.read_price_csv` -> `smart_parse_dates`): MEDANTA +548.8%, 360ONE +464.1%,
SBICARD +109.6%, PATANJALI +413.6%. **The count is five, not six**, on
`close` union `adj_close` inside the window; the sixth is not reproducible at that
threshold.

**FOUR OF THE FIVE ARE NOT SINGLE-DAY MOVES. THEY ARE PRICE HOLES.** Each is a
`pct_change` spanning a multi-year absence of rows:

| symbol | date | move | gap since previous raw row |
|---|---|---:|---:|
| MEDANTA | 2022-11-16 | +548.8% | **2,122 days** |
| SBICARD | 2020-03-16 | +109.6% | **1,873 days** |
| 360ONE | 2019-09-19 | +464.1% | **1,345 days** |
| PATANJALI | 2020-01-27 | +413.6% | 51 sessions |
| YESBANK | 2020-03-17 | +58.1% | 1 day -- **a real move** |

They are the PATANJALI class this project has known about since `tradability.py`
was written, and the record describes them as single-day market moves without
qualification.

**AND THREE OF THE FIVE NEVER REACH THE BENCHMARK AT ALL.** MEDANTA, SBICARD and
360ONE each have their first valid panel date ON the resumption date -- the window
boundary truncates the hole -- so `pct_change` is NaN there and the equal-weight
mean skips it. Only PATANJALI's +413.6% is a gap artefact that actually enters
`bh`. YESBANK's is real and must NOT be neutralised. That is why the corrected
range is 0.50 and not the 0.56 a blunt five-day cut suggests.

**nifty100 reproduces exactly at zero.** Zero moves above 55% in the window, and zero
interior gaps.

### A separate and larger defect: the benchmark is computed outside the guard

**THE BUY & HOLD BENCHMARK DOES NOT PASS THROUGH THE TRADABILITY GUARD.** This is
by the guard's own design statement -- `tradability.py` says it *"gates
TRANSACTING, not ranking"* -- and the benchmark does not transact. `TRADEABLE` is
consumed in exactly one place, `results/test_exposure.py:186`, inside
`backtest_exposure`. The benchmark is built beside it:

    bh = START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()

from a panel that is `.ffill()`ed, with no guard consulted. **That line appears in
seven places** -- `v34_common.py:246` and `:471`, `engine_v2_final_mid.py:173`,
`engine_v2_final_n100.py`, `engine_core.py:678`, `test_exposure.py:510`,
`shuffle_test.py:169` -- identically, and unguarded in all of them. `tradability.py`
records the scale of the exposure: *"px and op are pivots with .ffill() applied --
41 such pivots across 37 files."*

**The practical exposure, measured:** midcap150 has **46 interior gaps across 3 symbols**
(HEXT 1,069 sessions, PATANJALI 51, AIIL the rest) totalling 1,193 missing
sessions. **nifty100 has zero.** Of midcap150's, only PATANJALI's resumption produces a
material return in `bh`. HEXT's resumption enters as **+0.0%** -- the relisting
close exactly matches the pre-delisting close, 762.55 against 762.55, across 4.3
years -- which is a fabricated zero rather than a real flat day.

**THE GUARD ALSO MISSES A CLASS IT LOOKS LIKE IT SHOULD CATCH.** `tradability.gaps()`
filters each symbol's rows to the window BEFORE pairing them, so a hole whose last
real row precedes `BT_START_DATE` is invisible: MEDANTA, SBICARD and 360ONE are not
among the 46. It happens not to matter for `bh`, because the same truncation makes
their returns NaN -- but the guard is not the reason they are harmless, and it would
not catch them if they were.

**So 28.34 is not defective, on the evidence here -- but it is not guarded either.**
The number the entire midcap150 edge is measured against is protected by a window
boundary rather than by the guard that exists for this, and the difference has
never been stated. Not fixed; recorded.

### How the wrong figures got in -- and a provenance claim WITHDRAWN

**WITHDRAWN: "no script produces either."** This entry claimed the six-moves list
and the 24.23 figure were hand-written numbers in prose, and counted this as a
third instance of that class. **That is false.** `results/make_mid_chart.py:241-266`
computes BOTH, live, from the score panel on every run. The claim came from
grepping the `.py` files for `MEDANTA` and `548.8` and finding nothing -- **a null
grep for LITERALS read as absence of a PRODUCER.** The chart derives them from data
and holds no literal to match.

**The general point survives only where it still holds:** the +24,772.7% PATANJALI
figure that `tradability.py`'s docstring records, and the stale README headlines
that went uncorrected through an engine change. **This instance was wrongly added
to that list and is removed from it.**

`f1d9bc8` (2026-09-12 01:02) did introduce the figures into prose eighteen minutes
before `cf22431` wrote the pre-registration -- but it transcribed them from the
chart's output rather than inventing them.

**AND THE COUNT IS SIX, NOT FIVE.** An earlier version of this entry said five. The
sixth is **YESBANK −56.1% on 2020-03-06**, and it was missed because the scan
filtered `r > 0.55` while the chart filters `abs(r) > 0.55`. **A one-sided filter
cannot see a negative move.**

### The pattern behind all three wrong answers

Every one came from the same habit: **computing something ADJACENT to a claim and
treating agreement or disagreement as decisive, without first reading the code that
produced the claim.** The raw-file scan, the window-filtered scan, and the
artefact-day neutralisation were each a reasonable measurement of something the
chart was not measuring. Reading `make_mid_chart.py:241-266` first would have
settled it in one step and did, eventually.

`config.read_price_csv` versus an ad-hoc parse was the same lesson on the data side.
**The producing code is the authority, and a measurement that agrees with a figure
is not evidence that it measured the same thing.**

**THREE SCAN ERRORS PRECEDED THIS ENTRY, all mine, and the lesson is the same one.**
A first sweep using pandas `parse_dates` silently coerced ~190,000 rows per universe
to NaT and reported the moves absent. A second using `errors="coerce"` admitted
mis-parsed dates and reported 475 spurious moves clustered on the 1st and 12th of
months -- day/month ambiguity, not markets. A third applied the window filter
BEFORE `pct_change`, which dropped the pre-window row forming each hole and made
three of the four artefacts disappear. **Only `config.read_price_csv` gives the
answer the engine sees.** Any figure about this data computed with an ad-hoc parse
is untrustworthy, which is exactly how the numbers being corrected here were made.

### The two universes' prices are three weeks apart -- tested, benign by proxy

`_merged_at` records midcap150 extracted **2026-08-11** and nifty100 **2026-07-20**. The
pre-registration's statistic pools both universes, so if a later extraction revised
history the pooled test would mix two vintages. Tested 2026-09-13, read-only.

**THE DIRECT TEST IS IMPOSSIBLE: midcap150 and nifty100 share ZERO symbols.** MidCap150 and
the Nifty 100 are disjoint by index construction. The proxy is
`N100_Survivorship/clean` (extracted 2026-07-23/30), which overlaps both:

| comparison | shared symbols | rows compared | row-count diffs | adj_close diffs |
|---|---:|---:|---:|---:|
| midcap150 (Aug 11) vs surv (Jul 23/30) -- **3 weeks apart** | 54 | **257,202** | 0 | **0** |

Not one `adj_close`, `close`, `_dq_score` or row count differs across a quarter of
a million rows over a longer interval than the gap in question.

**VERDICT: tested and found benign, by proxy. No caveat is added to
`experiments/HELDOUT_PREREG.txt`, and none is needed.**

**Three limits on that clearance, stated:**

1. **It rests on a proxy.** midcap150 and nifty100 share no symbols, so the gap between those
   two trees specifically can never be tested directly. What was tested is the
   MECHANISM -- does re-extraction revise history -- over a longer interval.
2. **It tests re-extraction, not build policy.** Two trees can differ enormously
   with no vintage gap at all: nifty100 (Jul 20) against survivorship (Jul 23/30), three
   days apart, differs on 70 of 99 symbols. midcap150-against-nifty100 has never been checked
   for a policy difference and cannot be, for the same reason.
3. **The prereg's window closes 2026-05-29**, before both extractions, so this
   concerns revision of history only, never coverage. That is what makes the test
   clean.

**AND A FOURTH LIMIT, FOUND AFTER THE CLEARANCE WAS FIRST GIVEN AND MORE IMPORTANT
THAN THE OTHER THREE.** "Re-extraction does not revise history" is TOO STRONG as
stated. It does not revise history **absent a corporate action**. When one lands
between two extractions, the vendor back-adjusts the entire series and every
historical row changes -- which is exactly what separates the nifty100 and survivorship
TRENT series, and `data/reference/nse_circulars_2019_2026.csv` names the cause:
a **TRENT bonus issue, 2026-06-01 to 2026-06-03**, after `BT_END_DATE` and before
both extractions.

**The clearance survives, for a narrower reason than the one first given.** It is
not that extraction date is inert. It is that **midcap150 and nifty100 share no symbols, so
each universe's prices are internally consistent**, and the pooled statistic
combines two internally-consistent universes rather than two versions of one.

---

### The pre-registration is unaffected and is usable as-is

`experiments/HELDOUT_PREREG.txt` cites the six-moves figure in section 5, *"What
this test cannot do"* -- descriptive caveat only. **Its frozen configuration, its
statistic and its pass/fail rule do not depend on it** and are untouched by any of
the above. The file remains usable exactly as written.

**THIS CORRECTION LIVES OUTSIDE THAT FILE DELIBERATELY.** The pre-registration's
entire value is that it was fixed before the held-out window was seen, and an
amendment destroys that regardless of how honest the amendment is. It is not
edited, and it should not be.

---

## Fifteen artefacts were cleared by a control nobody designed

Found 2026-09-12, checked 2026-09-13. **The clearance holds. The mechanism is the
problem.**

This is not one of the four entries immediately above -- *"Four verification
claims describe an older engine than the one that ships"* -- and should not be
read as one. Those four are claims that described an older engine than the one
they labelled. **This is a claim that was CORRECT, for a reason nobody chose.**

### The window

`profiles.py` and the `tradeable` profile did not exist before commit `7acac3b`
(2026-09-10 23:31:48). The engines' `_c()` did not suffix by profile until
`f6b970b` (2026-09-12 01:44:33). For those **26 hours** a `tradeable` run wrote
CAPPED numbers into the CANONICAL filenames -- not through a fallback, through a
direct overwrite. `docs/HANDOFF.md` records the tradeable profile appearing in two
runs out of fifty-five.

Fifteen tracked diagnostics artefacts were written in or beside that window:
`drawdown_exit.{txt,cells.csv,equity.csv,events.csv}`, `purge_fix_measure.txt`,
`rebal_cadence_{sweep.txt,cells.csv,equity.csv}`, `seed_noise.txt`,
`shuffle_{mid,n100,verdict}.txt`, `topn_{mid,n100,verdict}.txt`.

### Why they are clear, and why that is luck

`v34_common.py`'s `SFX` gained `profiles.suffix()` **in the same commit that
created the profile** -- verified: `profiles.py` does not exist at `7acac3b~1`,
and `SFX` reads `selection_suffix() + cadence.suffix()` there and
`selection_suffix() + cadence.suffix() + profiles.suffix()` at `7acac3b`.

So `v34_comparison.csv` has been research-only for its entire lifetime: before
`7acac3b` no cap existed, and from `7acac3b` a tradeable run writes
`v34_comparison_tradeable.csv` and leaves the canonical file untouched.

Every one of the fifteen carries an identity gate reconciling its own re-run of v2
against that canonical file. A capped run cannot reproduce an uncapped baseline.
**The identity gates therefore functioned as profile provenance checks.**

**THAT IS NOT A DESIGNED CONTROL AND IT DOES NOT GENERALISE.** The gates were
built to check that a harness reproduces the shipped figures. Nothing in their
design, their names or their documentation concerns provenance, and no artefact in
this repository records the profile it ran under -- not the diagnostics headers,
not `v34_params.json`, not `RUN.txt`, which records universes, arms and cadence and
stops there.

**HAD `SFX` LAGGED THE WAY `_c` DID, the canonical baseline would itself have been
capped, every gate would have reproduced it exactly, and the same green would have
CONFIRMED contamination instead of excluding it.** One commit's ordering is the
whole difference between an exclusion and a false clearance, and the gates cannot
tell those two states apart. Do not cite a passing identity gate as provenance
evidence again without re-establishing that its baseline is what it claims.

### The clearance, per artefact

TWO CHECKS. **Timing:** mtimes, trustworthy here because the reflog shows one
working-tree-rewriting operation since these files were written -- a checkout at
2026-09-11 17:24 -- and every mtime predates it, so git never rewrote them.
**Content:** the identity gate's reconciliation against the research-only
canonical file, where `Trades` and `TC_Rs` are the cap-sensitive fields.

| artefact | mtime | vs window | content evidence | verdict |
|---|---|---|---|---|
| `rebal_cadence_sweep.txt` + `cells.csv` + `equity.csv` | 09-10 22:43 | 49 min before | all 4 arms reproduce published incl. Trades, TC_Rs | research, decisive |
| `seed_noise.txt` | 09-10 22:46 | 46 min before | gate MISMATCHES; offset inconsistent with a cap | research, **by inference only** |
| `purge_fix_measure.txt` | 09-10 23:21 | 10 min before | gate ok, 24.43 / 1.72 / −18.38 exact | research, thin margin |
| `shuffle_n100.txt` | 09-10 23:21 | 10 min before | gate ok, 24.43 / 1.72 / −18.38 exact | research, thin margin |
| `shuffle_mid.txt` | 09-10 23:22 | 9 min before | gate ok, 29.23 / 1.99 / −15.68 exact | research, decisive |
| `shuffle_verdict.txt` | 09-10 23:22 | 9 min before | aggregates both universes | research |
| `topn_mid.txt` | 09-10 23:22 | 9 min before | gate ok, 29.23 / 1.99 / −15.68 exact | research, decisive |
| `topn_n100.txt` | 09-10 23:22 | 9 min before | gate ok, 24.43 / 1.72 / −18.38 exact | research, thin margin |
| `topn_verdict.txt` | 09-10 23:22 | 9 min before | aggregates both universes | research |
| `drawdown_exit.txt` + `cells` + `equity` + `events` | **09-11 00:13** | **42 min INSIDE** | **Trades 965 = 965, TC_Rs 213158 = 213158**, CAGR/Sharpe/MaxDD/AnnVol/FinalEq all MATCH, G1 PASS | research, decisive |

**NOTHING WAS CLEARED ON TIMING ALONE.** The 23:21--23:22 cluster sits 9--10
minutes before the commit that created the profile, and the code existed in the
working tree for an unknown period before that commit. Nine minutes is inside any
plausible authoring margin, so those seven rest on content, not on the clock.

The complete form of the content argument, for the artefacts that reconcile
`Trades` and `TC_Rs`: if a cap had bound, those fields would differ; they do not;
so either the run was research, or the cap never bound -- and in the second case
the output is numerically identical to research output anyway.

### Two caveats on the clearance, stated

**1. The cap magnitudes are pre-`adj_close` and indicative, not current.** The
figures used to size the cap's effect -- midcap150 29.16 -> 27.36 CAGR, nifty100
25.43 -> 25.42 -- come from `experiments/EXPERIMENTS.md:1733-1739`, measured under
the engine BEFORE `adj_close` became canonical (commit `092ee62`).

> *Superseded 2026-09-20, and the caveat understated it. `depth_compare.py` re-run
> on the repointed data gives midcap150 27.79 -> 27.75 (a 0.04-point cost, n=1,006
> fills, 11 orders walking) and nifty100 19.00 -> 19.00 (n=940, 3 walking). The
> midcap150 magnitude these rows were sized against was 1.80 points; it is now
> 0.04. The nifty100 margin was 0.01 and is now 0.00. Anything marked "thin margin"
> on the strength of those numbers is resting on a magnitude that has since
> collapsed, and the move is not attributed -- see `diagnostics/depth_compare.txt`.* The nifty100 margin
is 0.01 CAGR, which is why three rows above are marked *thin margin*: they are
decidable at two decimal places and by no wider a gap than that, against a
magnitude taken from a superseded engine.

**2. `seed_noise.txt` is cleared by inference, not by reconciliation** -- see the
next entry, which states why that matters more than it looks.

### Two dead readers found in the same survey, not a substitution risk

`nautilus/nt_holdings_compare.py:39,76` and `nautilus/nt_daily_compare.py:75`
hardcode `daily_holdings_58.csv` and `daily_trades_58.csv`. Those artefacts were
deleted on 2026-09-11 and `results/metrics/` is empty. Both reads are unguarded
`pd.read_csv` with no `try`/`except` anywhere in either file, so they raise
`FileNotFoundError` and **fail loudly**. Recorded as deleted-artefact references
with no silent-substitution risk; not fixed.

---

## seed_noise.txt is the weakest of the fifteen clearances, and it is the sigma's denominator

Both facts belong in one place, because a reader -- including us, later -- will
otherwise trust the sigma more than the file it rests on.

**The clearance is the weakest of the fifteen.** Every other artefact in the entry
above was cleared by an identity gate reproducing the research baseline exactly.
`seed_noise.txt`'s gate MISMATCHES: it records `production 10 seeds from this
store: CAGR 23.01` against `recorded in v34_comparison.csv: CAGR 24.43`, an offset
of −1.42. It is cleared not by reconciliation but by the offset being INCONSISTENT
with a cap -- capping moves nifty100 by about 0.01 CAGR and leaves MaxDD unchanged,
while this file moves CAGR by 1.42 and MaxDD by 2.54. The stated cause is the
one-ULP panel readback, which is documented elsewhere in this file and is not a
profile effect.

That is sound, and it is inference about magnitudes rather than an exact
reproduction — and the magnitude it is measured against is itself pre-`adj_close`.

**And this file is the denominator for the 0.40 and 0.88 sigma figures** quoted
under *"Two benchmarks, not a contradiction"* above. The +0.43 and +0.89 CAGR
edges against buy & hold are expressed in units of the seed noise this artefact
measures. So the weakest-cleared file in the set is the one the headline
uncertainty is denominated in.

**This is not a dispute of the clearance.** It is a statement of what the sigma
rests on: a noise floor whose own provenance was established by inference, whose
baseline offset is explained by a defect documented separately, and which is
already described in this file as *"a denominator that is itself unstable by
several points"*. The sigma should not be quoted as though it were firmer than
that chain.

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
v1 was measured against v2 directly on the nifty100:

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

---

## results/engine_v2.py is absent, and two modules still import it

**This predates the 58/74 retirement.** It is recorded here because the retirement
surfaced it, not because the retirement caused it: `results/engine_v2.py` was
already missing at commit `56a4136`, before a single file was deleted.

```
results/audit_leakage.py    ModuleNotFoundError: No module named 'engine_v2'
results/stability_test.py   ModuleNotFoundError: No module named 'engine_v2'
```

Both fail **at import**, so neither has run for as long as the file has been gone.
`build_panel` was moved into `engine_core.py` when `engine_v2.py` was deleted — its
docstring records that it "was nearly lost" then — but these two callers were never
repointed. Neither module is registered as a pipeline step, so nothing failed
loudly and nothing noticed.

**`stability_test.py` matters more than its status suggests, and the reason is
new.** The 58/74 retirement demoted `results/metrics` from being the 58's output
home to being the directory for **shared, non-universe output**, and `run.py`'s
pre-flight now refuses to start if anything universe-tagged is written there. The
only shared non-universe artefacts this project has ever produced are
`stability_raw.csv` and `stability_summary.csv` — and they are written by
`stability_test.py`, which cannot run.

So the demotion is currently **half hollow**: `results/metrics` is a directory with
an enforced rule and no legitimate occupant. That is stated plainly here rather
than left to imply that the shared directory is in use. Fixing it means repointing
both modules at `engine_core.build_panel` — which now requires an explicit
`data_dir`, so the fix also has to decide which universe each one measures. That is
new work, not recovery, and it has not been done.

---

## The feature documentation was generated from the 58, and has no replacement

`results/export_feature_docs.py` called `build_panel(HORIZON)` **without
`data_dir`**. That parameter defaulted to `config.RAW_DATA_DIR / "nifty50"`, so the
script silently built the 58's panel and wrote three artefacts into
`results/metrics`:

```
feature_dictionary.csv    the feature list, with the real code line and comment
panel_sample.csv          the first 500 rows of "the model's input"
panel_summary.csv         per-column statistics
```

Nothing in their names says which universe they describe, and every reader has been
entitled to assume they describe the pipeline. They describe the 58.

This is the same class of defect as the two contaminated charts recorded above: not
stale, **wrong**. All three artefacts are untracked, are absent from the working
tree, and survive only in `forensic_snapshot_20260911T0100/results/metrics/`. The
script was deleted on 2026-09-11 with the universe it was silently reading.

**There is currently no feature dictionary, panel sample or panel summary for midcap150
or nifty100, and no code that would produce one.** `build_panel` now requires
`data_dir` explicitly — the fallback that caused this is gone — so a replacement
must name its universe. Writing one is its own decision and is not scheduled.

---

## The tax model is date-exact to the day; the charge engine it sits beside is not

Found 2026-09-17, while verifying the reference document's own section 5
limitations against our charge engine before implementing its section 3. Open,
and deliberately not fixed: the charge engine is not to be touched.

### The inconsistency

`results/tax_util.py` splits the capital-gains regime on a single day. Section
3(8) of the document fixes the rate by the sale date, `CGT_REGIME_CHANGE =
2024-07-23`, and a lot sold on the 22nd is taxed at 15% while one sold on the
23rd is taxed at 20%. That is exact to the day, by design, and it is checked.

`results/qbeast_in_charges.py` has no concept of a date at all.
`compute_leg_charges()` takes `(broker, segment, product, side, price, quantity,
exchange)` and no date parameter, so there is no argument through which a
historical rate could be selected. Its `SPEC_LOCK` reads:

```
"rates_effective": "2026-04-01",   # post Budget-2026 F&O STT hike
"verified_on":     "2026-06-25",
```

So **the 2026-04-01 rate table is applied to every fill from 2019-01-01
onward** -- 1,836 sessions and 505 lots on midcap150, 478 on nifty100 -- while the tax
code beside it distinguishes two regimes seven years into that same window.

Equity-delivery STT is likewise a single constant, `"stt_rate": "0.001"` on both
sides. The file documents that F&O STT moved twice (Oct'24, Apr'26) and records
those changes in its own comments, which makes the omission on the equity leg a
recorded fact rather than an oversight -- but it is still a constant applied
across a window in which real rates moved.

### What a reader would wrongly conclude

That the combined model is period-accurate because one half of it obviously is.
The tax figures carry a visible, checkable regime boundary; the cost figures
carry none, and nothing in an artefact distinguishes the two. A reader who sees
`FY_TAX_STATEMENT` correctly splitting FY2024-25 at 23 July has every reason to
assume the charges underneath were computed on the rates in force at the time.
They were not. They were computed on the rates in force in April 2026.

The direction of the error is not stated here because it is not known: it would
require the historical rate tables, which are not in this repository.

### Why it is not being fixed

The charge engine is the more faithful half of the model and it was left
untouched on purpose. Verified against the document's section 5, three of its
five stated limitations do not apply to us at all:

```
doc limitation                              ours
"DP charges are not modelled at all"        MODELLED: DP_BASE[ZERODHA] = 13.00
  (~Rs 13-16 + GST per scrip per sell day)    -> Rs 15.34 incl GST, SELL only
"Charges are symmetric; reality is not"     ASYMMETRIC: stamp 0.015% BUY only,
                                              DP SELL only. Measured: BUY leg
                                              0.001188, SELL leg 0.001256
"No brokerage minimum"                      N/A: Zerodha delivery brokerage is
                                              zero, so a floor cannot bind
"STT is assumed constant"                   SHARED -- equity delivery is one rate
"No rate changes over time in COST_PCT"     SHARED -- no date parameter exists
```

Making the last two period-accurate means adding a date argument to
`compute_leg_charges()` and a historical rate table behind it. That changes
every cost figure in the repository, which breaks the reproduction gate against
the shipped `v2FINAL_equity.csv` and every hash in
`RETIRED_UNIVERSES-manifest.txt`. It is not a change to make in passing, and the
held-out window is already spent.

### Why it is recorded now rather than when it becomes a problem

Because the window it is currently wrong over is short and the next one may not
be. The present backtest starts in 2019 and the rate table is dated 2026, so the
error is bounded by whatever moved in those seven years. A universe with a
longer history -- and the survivorship work makes clear that longer histories are
what this project keeps reaching for -- back-applies the same 2026 table over
however many additional years it brings, with no gate anywhere that would notice.

---

## The tax lump sum is deducted before the day's fills, and the document does not say so

Recorded 2026-09-17 with the in-loop tax hook. This is a STATED DECISION, not a
defect and not a quoted rule. It is here because a reader comparing our output
against the reference document would otherwise have no way to tell which of the
two it is.

### What the document fixes, and what it leaves open

Section 3(9) fixes the amount and the date: each financial year is assessed
exactly once, on the first trading day at or after 31 March, and the whole tax
leaves cash as a single lump sum. It gives a reason, quoted:

> "It reduces NAV and therefore reduces the capital available to trade the
> following year -- tax genuinely compounds against you."

It does not say where in that day the deduction falls. Our engine does several
things on a single session: it accrues cash, force-exits untradeable names,
sells the rebalance exits, sizes the entrants from whatever cash is left, and
fills them. A lump sum can land before or after any of those.

### The decision, and the reasoning

`results/test_exposure.py` TOUCH POINT 6 deducts it FIRST -- immediately after
the cash-yield line and before any fill that session.

The document's own sentence is only true this way. Order sizing reads cash
directly, `q = int((invest_val * w * f) // pr)`, and the cash test below it
refuses an order the balance cannot carry. Money removed after the fills would
reduce the reported NAV without ever having reduced the capital available to
trade, which is the opposite of what the quoted sentence describes.

Cash may go negative and is NOT clamped. A clamp would forgive part of a real
liability and silently improve the result; an overdrawn book simply buys nothing
that morning, which is the honest consequence.

### The edge this ordering creates, which is detected rather than assumed away

Section 3(9) can put a year's assessment inside that same year. FY2019-20 falls
due on the first trading day at or after 31-Mar-2020, which is 2020-03-31 --
still inside FY2019-20. A sell later that same day lands in a financial year
already assessed "exactly once", so its gain would never be taxed at all.

It does not occur on the current window. Checked across both universes: no sell
falls on an assessment date belonging to its own financial year, and the only
sell that lands on an assessment date at all is 2024-04-01, which is FY2024-25
trading while FY2023-24 is assessed. `tax_util.Ledger.leaked()` reports 0 on
both universes.

That is calendar luck and not a property. A different cadence, a different
window or a different universe calendar can put a sell on a 31-March assessment
date, so `leaked()` exists to name the rows rather than let a run lose a realised
gain in silence. It is a reporting hook, not a guard: nothing currently fails the
run when it is non-empty.

### One consequence worth stating separately

Because the liability depends on the trades and the trades depend on the cash,
the tax charged by a taxed run is NOT the tax computed from an untaxed run's
trade log. Measured on midcap150: Rs 833,105 from the untaxed log against Rs 798,365
actually charged, because after the first deduction the taxed book is holding
smaller positions and realising smaller gains. The ledger accrues inside the
loop for this reason, and any figure quoted for "the tax" must say which of the
two runs produced it.

---

## A gate count measured before the change it describes is a claim about a tree that no longer exists

Recorded 2026-09-17, at the pattern level, after the second instance. Open as a
practice; both individual numbers have been corrected.

### The pattern

A commit message reports a gate's figures -- "111 undeclared calls across 50
sites", "0 defects", "exit 0" -- as evidence that the change it accompanies did
not move them. The number is obtained by running the gate, then writing the
message, then staging the change. But several of this project's gates SCAN THE
WORKING TREE, including files that are not yet tracked. A gate run before
`git add` is measuring a tree that does not contain the commit, so the figure
quoted as proof of the commit's innocence was taken from a tree the commit does
not describe.

It fails in exactly one direction, which is why it survives review: the number is
always the OLD one, so it always shows no change, so it always looks like the
evidence the message wanted. A regression introduced by the commit is invisible
precisely when the message is most confident.

### Both instances

**ecfbac3** reported GATE 1 at 111 undeclared calls across 50 sites. The
pre-registration runner and its artefacts were added in that commit; the count
was taken before they were staged.

**7846f67** reported GATE 1 at 111 and stated the count was "byte-identical on
HEAD and untouched by this commit". It took it to 112.
`tax_acceptance_check.py`, added by that commit, contains
`f.write_text(PROBE)` -- a throwaway probe source written to a temp directory,
but `write_text` is in `naming_declare_check.WRITERS` and the call carried no
directive. The count was measured before the file was staged, so the message
reported the figure from a tree without it.

Corrected in 59dff90: the probe write is declared `# naming: axis-free`, and
GATE 1 is back to 111 across 50 sites.

### What a reader would wrongly conclude

That a gate figure in a commit message is a measurement of that commit. It is
only a measurement of whatever was on disk when the command ran, and for an
untracked file that is a tree the commit does not describe. The figures in
KNOWN_ISSUES.md and in commit messages should be read as claims about a tree,
and the tree should be named.

### Why this is not fixed with a hook

The obvious fix -- a pre-commit hook that re-runs the gates against the index --
would run four to six checks on every commit in a repository where one of them
spawns a backtest. It would also not have caught either instance, because both
messages were written honestly from a command that really did print that number.
The defect is in WHEN the command is run, not in what it prints. The practice is
therefore: run the gate AFTER `git add` and before `git commit`, and quote the
figure from that run. Recorded here rather than automated, because a practice
that is written down and cited twice is cheaper than a hook nobody can afford to
run.

---

## The edge is +0.46 before tax and -1.59 after, on the one universe where the question can be asked

Measured 2026-09-17 in 3f0ef05, reproducible with `./venv/bin/python
bh_lots_after_tax.py`. Open. This is a RESULT, not a defect, and it is recorded
here because it changes how every published figure in this repository should be
read.

### The finding

Against a genuine held-lots buy & hold -- equal-rupee across every priced name on
session one, no rebalance, a single realisation at BT_END_DATE, the same 0.15%
slippage and the same Zerodha charge engine as the strategy -- on **nifty100**, over
2019-01-01 .. 2026-05-29:

```
                                                          FULL   2019-2022   2023-2026
v2  before tax                                          24.43%      22.16%      27.21%
v2  after tax  (8 deductions in-loop, tail settled)     20.66%      19.71%      21.84%
bh_lots before tax                                      23.97%      30.25%      17.11%
bh_lots after tax  (nil in-loop, settled at end)        22.25%      30.25%      13.60%

EDGE  v2 - bh_lots   before tax  +0.46      after tax  -1.59      swing -2.05
```

WHEN THE TAX LEFT CASH, which is what the two labels carry:

```
          deducted in-loop        settled at end
v2           Rs 634,420              Rs       0
bh_lots      Rs       0              Rs 479,999
```

Both lines are settled at the final session, so the comparison is like-for-like
at the endpoint -- `bh_lots_after_tax.py:163-168` deducts v2's unassessed tail
and bh_lots' whole liability together. It is NOT like-for-like along the path,
and the labels say so: v2 has been paying since 2020 and lost the compounding on
every rupee it paid; bh_lots pays once, at the end.

THAT DEFERRAL IS NOT AN ARTEFACT OF THE SETTLEMENT and must not be "corrected"
out. It is the advantage a low-turnover book actually earns, it is already inside
the -1.59, and removing it would delete the effect this benchmark exists to
measure. On nifty100 v2's unassessed tail is Rs 0, so the settlement pulls forward
only bh_lots' Rs 479,999 -- and with `CASH_YIELD = 0.0` in this engine
(results/test_exposure.py:63) discounting that back to its real FY2026-27 due
date returns exactly the settled figure. The -1.59 is therefore a MEASURE of the
turnover cost under this construction, not a lower bound on it.

**The edge does not survive tax.** It is +0.46 points before and -1.59 after, and
the sign changes.

### The swing is the turnover cost, and it is the whole mechanism

v2 loses **3.77** CAGR points to tax. bh_lots loses **1.72**. The **2.05** points
between them is not a rate difference applied to the same trades -- it is the
difference between **478 short-term realisations taxed annually** and **one
long-term realisation taxed once, deferred to the end of the window**.

Every v2 lot is short-term: maximum holding 322 days on nifty100 against a 365-day
threshold, so the long-term branch never fires and 100% of gains are taxed at the
short-term rate in the financial year they are earned. The tax then leaves cash
before the next morning's fills, so it also removes the capital that would have
compounded. bh_lots holds for 2,705 days, realises once at 12.5% long-term, and
pays nothing until the end -- visible in the sub-periods, where its after-tax
CAGR equals its before-tax CAGR in 2019-2022 (30.25% both) and takes the entire
hit in 2023-2026.

That is the cost of churn, measured rather than asserted, and it is the number
the parked tax_util.py was written to produce and never did.

### On midcap150, the question is unanswerable, and the tooling now refuses to answer it

midcap150's bh_lots basket is **53.0% one name** at terminal value -- AIIL, 956x over
the window -- and 68.4% in three, against a median name multiple of 3.45x.
Dropping that single name moves the benchmark CAGR by **-13.98 points**, against
an effect size of 2.05. The instrument cannot resolve the effect.

The cause is survivorship, not arithmetic. `SURVIVORSHIP_MODE=static` means
today's MidCap150 members backfilled to 2019, so AIIL is in the basket PRECISELY
BECAUSE it went up 956x. Buy-and-hold is the most survivorship-exposed
construction available, and midcap150's 44.34% bh_lots CAGR is what that exposure looks
like rather than an achievable return.

`bh_lots_after_tax.py` therefore WITHHOLDS the edge when top-name weight exceeds
11.62%, printing the concentration and the refusal in its place. Annotating the
number was tried first and was not enough: a figure gets copied out of a terminal
more often than the caveat beside it does.

### What a reader would wrongly conclude

That the published **+0.89 on midcap150 and +0.43 on nifty100** are the edge. They are the
edge **before tax, against a costless daily-rebalanced index that holds no lots
and cannot be taxed at all**. Both statements remain true and both reproduce
exactly. But that benchmark cannot answer an after-tax question, and the
benchmark that can gives +0.46 -> -1.59 on the only universe where it is
diversified enough to be believed.

A tax=off run is the DEFAULT, so every headline figure this repository prints is
pre-tax unless it says otherwise.

### What was deliberately not done

Nothing in the strategy was changed in response to this. No parameter, no
cadence, no arm, no rebalance rule. The result was produced by a measurement that
ran once against a window that is already spent -- there is nothing left to
validate a change against, so any change made now would be fitted to a number
with no out-of-sample left to check it. The finding is recorded and the strategy
is untouched.

---

## The two netting orders are opposite, and that asymmetry is carried deliberately

Written 2026-09-17, while implementing section 3 of
`data/reference/TAX_AND_CHARGES.docx`
(sha256 `a5be987a1a75238796dd059c777b370b14be43f8a418206c93ee4201ddec8972`).
DELIBERATE. Do not unify these.

THE DOCUMENT IS DELIBERATELY NOT IN THIS REPOSITORY. It is RegimeSwitch's
internal reference describing that system's own code, it is not ours to
redistribute, and this repository is public. The sha256 above is recorded so that
anyone holding the file can verify every quote in these entries against the exact
revision they were taken from; a different hash means a different document and
the quotes must be re-checked before they are relied on.

`results/tax_util.py:313-330` allocates the two taxable bases in **opposite**
orders:

```
stcg_old_t = min(max(b["short_old"], 0.0), stcg_taxable)   # OLD-rate first
ltcg_new_t = min(ltcg_taxable, max(b["long_new"], 0.0))    # NEW-rate first
```

Both are the reference document's section 3.4, copied expression for expression.
The document writes STCG as `stcg_old_t = min(max(short_old, 0), stcg_taxable)`
with the comment "old-rate portion consumed first", and LTCG as
`ltcg_new_t = min(ltcg_taxable, max(long_new, 0))` with "new-rate portion taxed
first" -- which is what leaves the annual exemption sitting against the
pre-cutoff gains, the order the document calls "chronologically correct".

### Why it looks like a bug and is not

The two rules are genuinely asymmetric and no single sentence covers both. A
reader arriving at `tax_for_fy` will see one base allocated oldest-first and the
other newest-first within twenty lines of each other, and the obvious tidy-up is
to pick one and apply it to both.

**That tidy-up would void the comparison this module exists to produce.** We are
reproducing RegimeSwitch's rules in order to measure our strategy under them, not
designing a tax engine. A unified rule would be a rule the source document does
not contain, and every after-tax figure computed under it would be measuring a
regime that exists nowhere.

### What would justify changing it

Only a change in the source document. Not a reading of the Income Tax Act, not
symmetry, not simplification. If the document is ever revised, re-quote section
3.4 and re-derive; until then the asymmetry stands and is checked by the
verbatim quotes recorded in this file.

---

## The LTCG exemption keys on the financial year, not the sale date

Written 2026-09-17. DELIBERATE, and the document contradicts itself here --
this records which reading we follow and why. The document itself is not in this
repository and its sha256 is recorded in the netting-asymmetry entry above,
against which these quotes can be verified.

`results/tax_util.py:198-206` keys the annual exemption on the financial year:

```
def exemption_for_fy(fy):
    return LTCG_EXEMPTION_NEW if fy >= LTCG_EXEMPTION_FY_CUT else LTCG_EXEMPTION_OLD
```

So a lot **sold in May 2024** is pre-cutoff and taxed at the OLD 10% rate by
`regime_of()`, yet draws the **NEW Rs 1,25,000** exemption, because it falls in
FY2024. Rate and exemption key on different conditions, and that is intended.

### The document reads both ways, and section 3.6 settles it

Section 3.1's rate table binds the exemption to the rate row, i.e. to the sale
date:

```
Sale before 23-Jul-2024 | 15% | 10% above Rs 1,00,000
Sale on/after 23-Jul-2024 | 20% | 12.5% above Rs 1,25,000
```

Section 3.4 binds it to the financial year:

```
ltcg_taxable = max(ltcg_net - exemption, 0)   # Rs 1.00L (FY<2024) or Rs 1.25L (FY>=2024)
```

These disagree for FY2024-25, the only straddle year in the window.

**Section 3.6's worked statement is the tiebreak.** Its FY 2024-25 row reads
`Regime: split @ 23-Jul-2024` and `Exemption: 125,000` -- a year containing
pre-cutoff sales drawing the full new allowance. That is the FY reading, printed
by the source implementation itself, so section 3.1's table is loose phrasing in
a rate summary rather than a competing rule.

### Why it is recorded rather than "fixed"

Reading section 3.1 alone makes the code look like an off-by-one-year bug worth
Rs 25,000 of exemption. It is not. Anyone proposing to key the exemption on the
sale date must first explain section 3.6's worked row, which they cannot, because
that row is the source implementation's own output.

---

## The unclamped negative-cash path has never executed

Written 2026-09-17. DELIBERATE and correct-by-argument -- but, unlike everything
around it, NOT correct-by-measurement.

`results/test_exposure.py:228-234` deducts the annual tax lump sum without
clamping:

```
# CASH MAY GO NEGATIVE HERE AND IS NOT CLAMPED. A clamp would forgive part
# of a real liability and silently improve the result; an overdrawn book
# buys nothing that morning, which is the honest consequence.
...
                cash -= _due
```

### It has never happened, measured on both universes

Measured 2026-09-17, tax=on, full 1,836-session in-sample window:

```
              cum tax        TOUCH POINT 6 events   sessions cash<0   min cash
mid      Rs 798,365.53                7                   0      Rs 64,075.85  (2021-01-07)
n100     Rs 634,420.14                8                   0      Rs  1,106.69  (2021-02-05)
```

Every one of the 15 deductions left cash positive. The smallest post-deduction
balance was Rs 63,509.83 (nifty100, 2019-04-01).

### Two things a reader should not conclude

**Not that the branch is dead code.** nifty100's minimum balance across the whole run
is Rs 1,106.69 -- the book runs close to fully invested, and a larger liability,
a different cadence, or a smaller `START_CAPITAL` could reach zero. The branch is
reachable; it has simply never been reached by a shipping configuration.

**Not that negative cash would compound as debt.** `results/test_exposure.py:63`
sets `CASH_YIELD = 0.0` -- "no yield assumed on idle cash" -- so `cash_daily` is
exactly 0.0 and a negative balance accrues nothing. The reference document's
4.5% (its section 5, `config.py:83`) is RegimeSwitch's and is not ours. The
compounding-a-debt-at-a-deposit-rate artefact is structurally absent here, and
any future change to `CASH_YIELD` reintroduces it.

### What was deliberately not done

No clamp, no forced liquidation, no yield suspension. A clamp forgives a real
liability. A forced liquidation invents a selling rule the document does not
contain, and those sales would realise gains inside the assessment day, making
the liability circular. Yield suspension is a no-op at `CASH_YIELD = 0.0`. The
path stays as written and this entry records that it is untested by measurement.

---

## check_pipeline_order attributes every edge to every step that runs the script, ignoring the universe

Found 2026-09-18 while probing the checkers at `len(REGISTRY) > 2`. RECORDED, NOT
FIXED, and the reason it is deferred is in the last paragraph.

`check_pipeline_order.py` resolves a producer edge by matching the SCRIPT alone.
`run_all._step_label()` matches on `(script, tag)` and gets the universe right;
the edge scanner does not use the tag it already has. So every step that runs
`make_chart.py` claims every universe's `make_chart` inputs:

```
STEP 10d  make_chart.py   results_mid/v2FINAL_equity.csv    engine_v2_final.py
STEP 10d  make_chart.py   results_n100/v2FINAL_equity.csv   engine_v2_final.py   <- 10d is MID's row
STEP 10h  make_chart.py   results_mid/v2FINAL_equity.csv    engine_v2_final.py   <- 10h is N100's
```

### It is pre-existing, and it scales as noise rather than as blindness

Measured against a 2-universe baseline on the same day: `STEP 10d` already claims
`results_nifty100/` files today, with nothing added. A third universe multiplies the
cross-attribution -- each `make_chart` step claimed 12 edges at 3 universes rather
than 4 -- but introduces no new failure mode. At 10 universes each such step would
claim 40.

**IT CANNOT HIDE A MISSING UNIVERSE, AND IS NOT THE CHECK THAT WOULD.**
`registry_coverage_check.py` is what answers universe-completeness, and it was
probed on the same day with a throwaway third row: it fails closed, names the
universe, names the table, and states the consequence of each gap. The scanner's
`unresolved` count also scaled 6 -> 8 with the third universe, so it is not blind
to the universe -- it simply does not discriminate on it when attributing edges.

**What the output therefore does NOT mean.** A line here is not the answer to
"which step produces this file for this universe". It is "some step running this
script produces this file for some universe". Read it as a script-level edge list.

### Why it is recorded rather than done

Fixing it changes edge resolution, and `run_all.REQUIRED_INPUTS` is derived from
the same `PIPELINE_ORDER` table through `_step_label()` -- so a change to how
edges resolve moves a guard table four consumers read, and needs its own pre/post
edge-inventory diff. That is the same reason `REQUIRED_INPUTS` derivation was
itself sequenced separately. It is a one-line discriminator and a multi-step
verification, and the verification is the cost.

---

## An operation reports success having done part or none of the work

**One class, six instances inside two weeks, each caught by a different
accident.** Four were separate entries in this file until 2026-09-18; they are
one entry now, because treating them separately is what let the fourth happen
after the first three were written down -- and the fifth was found after that,
which is why it is filed here rather than opened as its own.

`check_all.py` is the answer to the first four. One command, five gates, run
before every commit and in CI. **It is not the answer to the fifth**, which no
gate catches: nothing can tell a checker that a number in prose was true when it
was written and is false now. Re-measure before citing.

### The six

**1. TEN things a new universe must be wired into, and a survey that said
seven.** `registry_coverage_check.py` checks twelve tables and is excellent at
it; the cost survey for wiring a universe was conducted entirely through it and
the other static checkers, and reported the cost as seven items.

**THE COUNT WAS NINE UNTIL `b98f64c`, AND IS TEN NOW.** That commit added
`run_all.PIPELINE_ROW_COUNT`, a hand-maintained declaration of `PIPELINE_ORDER`'s
length, AFTER the nine were counted -- so this entry undercounted its own subject
within a week of being written. A universe adds five PIPELINE_ORDER rows, and the
constant must move with them. Re-measured 2026-09-18 while costing midcap50.

**THREE OF THE TEN ARE INVISIBLE TO EVERY STATIC CHECK, and that is the
distinction worth carrying:**

| invisible item | when it bites |
|---|---|
| `make_combined_universes.PAIR_CHART_REGISTRY_SIZE` | STEP 12b's RUN TIME |
| `seed_noise_measure.LABELS` | IMPORT of a module the pipeline never imports |
| the `data/raw/<X>_constituents/` symlink farm | filesystem, not code -- no checker reads it |

The first cost a run: `run.py --universe nifty50` exited 1 at STEP 12b with four
of ten steps unexecuted, after the expensive one.

**ITEM 1 IMPLIES A PER-UNIVERSE PALETTE, AND THERE IS NOT ONE.** Wiring a
universe includes choosing `chart_colours`, and on midcap50 that was a real
search -- 369 pairs, dE2000 >= 10 against all eighteen existing slots under three
visions. **It governs less than the entry suggests.** Resolved 2026-09-18 by
reading every consumer in the repository:

| reads `chart_colours` | does not |
|---|---|
| `make_combined_universes.py:365` -- the COMBINED chart | `make_chart.py` -- the PER-UNIVERSE chart |
| `palette_distance.py` -- which measures those same lines | |

`make_chart.py` hardcodes six colours and draws EVERY universe in them:
`#c0392b` v2, `#2e6da4` v1, `#1b9e77` v3, `#e6ab02` v4, `#3a9d3a` buy&hold,
`#000000` index. So `chart_<tag>.png` looks the same whatever the tuple says, and
a searched palette is invisible until two or more universes are selected and
STEP 12b renders.

**midcap50's PALETTE HAS STILL NEVER BEEN DRAWN.** Its first full run selected one
universe, so STEP 12b skipped with "it overlays two or more universes and only 1
is selected". The dE 10.28 figure is a computed floor that nothing has yet
displayed. **Do not cite it as a visual result.**

**Whether the per-universe charts SHOULD use the tuple is a real question and is
deliberately not answered here.** Changing `make_chart.py` re-renders three
universes' published figures, which is an artefact change and its own commit.

**THE CEILING IS MEASURED NOW, AND IT IS 8.712634, NOT 10.** Amended 2026-09-19
while costing midcap100, the fifth universe this paragraph was written to warn
about. The warning was right that the band was full and wrong about what
follows from it.

- **The "against all 24 slots" rule is not over-strict.** 166 drawable images
  were enumerated; the co-appearing slot pairs number 276 and the full cross
  product numbers 276. **Zero pairs can never share an image**, because
  `--arm all` is the default and draws slots 4 and 5 beside 0-3 for every
  selected universe. Constraining the search to co-appearing pairs changes
  nothing.
- **dE 10 is genuinely unreachable inside L* 30-72.** On a step-4 grid,
  exactly four in-band colours clear it and all four are the same olive green
  (`#588050`, `#647c50`, `#687c54`, `#5c8050`, L* ~49.5), mutually closer than
  10. Largest mutually-separated subset: 1. Six are needed.
- **T = 8.712634 across all three visions**, binary searched to 1e-4. Not
  rounded, deliberately -- rounding a measured ceiling to 8.5 or to 10 is how
  it becomes a remembered one, which is the defect this file records five
  times.
- **Optimising under normal vision alone gives T = 20.655653 and is a trap.**
  Normal vision was never the binding constraint. That tuple's deutan collision
  is 2.560, WORSE than anything currently shipped.
- **The standard being enforced on a new universe was stricter than the one the
  shipped palettes meet.** Five within-universe pairs already ship below 10,
  the worst at 3.26 (nifty100/v1 vs v3, deutan), and all five co-appear. The
  taken tuple's worst pair under any vision is 8.713 -- 2.7x better than the
  project's current worst.

Full numbers, method and the rejected tuple: `diagnostics/palette_ceiling.txt`.
The midcap50 registry comment claiming "every pair clears dE2000 >= 10" was
corrected in the same commit; it was false when written.

**`PIPELINE_ROW_COUNT` IS NOT IN THAT TABLE, AND THE DIFFERENCE IS THE POINT.**
It is fully visible: omit it and `check_all.py` GATE 2 fails immediately, by name,
before anything runs -- "PIPELINE_ORDER has 25 rows, PIPELINE_ROW_COUNT says 20".
A tenth item that fails loudly at the cheapest possible moment is not the same
kind of cost as three that fail silently, late, or never. **Count it, budget it,
and do not file it with the other three.**

**2. Two modules unimportable for two weeks, beside four green checkers.** From
the day nifty50 was registered, `seed_noise_measure` and `seed_noise_report` raised
`SystemExit` at import. Nothing imports them -- not `run_all`, not any checker --
so the failure waited for a person. Found in the CONTROL ARM of an unrelated
rename experiment.

**3. A regex over `PIPELINE_ORDER` matching 12 of 15 rows, twice.** The script
column contains digits (`engine_v2_final.py`), so `"[a-z_]+\.py"` skips the
three engine rows. Both times the half-renamed table imported cleanly until
`_step_label` could not name a producer; both times the only thing that caught
it at the point of edit was an `assert n == 15` the author happened to write.

**4. `make_daily_log.py` run directly: wrote nothing, exited 0.** Its body moved
into `main()` when the pipeline stopped spawning subprocesses and the `__main__`
guard was deleted rather than left calling it. The string `"__main__"` still
appears in `main()`'s docstring, so a text search passes the file. A regeneration
pass during the rename "succeeded" that way and changed not one byte; it was
caught by diffing against copies saved beforehand.

**5. A count that was never re-measured, presented as a measurement, used to
justify a deferral.** `PANEL_MIGRATION.md` recorded "seven `v34_params*.json` and
one `v2FINAL_params.json`" carrying a stale `universe_tag`. Measured on disk
2026-09-18 by parsing every file and reading the key: **six**, not eight. The
seven counted files matching a glob rather than files needing work -- nifty50's
is correct and never held an old tag -- and **no `v2FINAL_params.json` has a
`universe_tag` key at all**, so the claimed eighth could not be stale. The number
was then the basis for deferring the fix to a tax run that could never have
collected it. **A count nobody re-measured is an assertion, not a measurement**,
and it reports success -- "we know the size of this" -- having done none of the
work.

**6. A hand-composed suffix chain, under-specified three times, where a missed
term makes the check PASS.** `results/audit_step.py:165` binds the reference
curve the audit reconciles against:

```
_cad = cadence.suffix() + profiles.suffix()      # tax was missing
```

| axis | what the mispairing cost | how it was caught |
|---|---|---|
| cadence | v1 MISMATCH **Rs 2,923,934**, v2 **Rs 1,825,210** on mid at `--rebal 40` | it failed loudly |
| profile | "a MISMATCH of the cap's whole effect" | it failed loudly |
| tax | **Rs 761,619** | **it did not fail** -- found only while GATE 6 was being written |

**THE THIRD INSTANCE IS DIFFERENT IN KIND, AND THAT IS THE ENTRY.** The first two
resolved to the WRONG curve and the reconciliation reported a MISMATCH -- the
check working on the wrong pair, which is noisy but safe. The third resolved to
the UNTAXED curve while the audit re-run was ALSO untaxed, so the two agreed and
it reported MATCH. **A missed term stopped the check from being able to fail.**
On a cold tree it is worse rather than better: `_reference_curve` returns None and
the trail is not written at all.

**THE POINT IS NOT THAT SOMEBODY FORGOT TAX.** Each fix was per-axis, so the
expression must be extended BY HAND every time an axis is added. `naming.tail()`
exists precisely so nobody hand-writes the chain -- it composes from `AXES`, and
an axis added there appears everywhere `tail()` is used. **Thirteen sites compose
the chain by hand anyway**, and each is one edit away from the same defect.

**A FOURTH INSTANCE IS LIVE AND IS NOT FIXED.** `results/arm_sources.py:41`:

```
sfx = cadence.suffix() + _pf.suffix()            # no tax term
```

Measured 2026-09-18: under `--tax on` it returns `v2FINAL_equity.csv`,
`daily_trades_midcap50.csv` and `v34_equity.csv` -- **byte-identical paths to the
tax=off selection**. It is `make_chart`'s source lookup (STEP 10t), so a chart
written under a `_tax` name draws its arm series from untaxed curves, while
`make_chart.py:161`'s own `_ci()` does carry the tax term. One step, two
conventions. NOT FIXED HERE.

**IT IS AN AXIS WIRING ITEM, NOT THE ELEVENTH UNIVERSE ONE, AND THE DISTINCTION
IS LOAD-BEARING.** Wiring midcap50 on 2026-09-18 required no change to either
expression; both needed changing when the tax AXIS landed. Appending it to the
ten-item list above would make that list assert something false about what a new
universe costs -- which is the defect this file records five other instances of.
**Adding an AXIS requires extending every hand-composed chain**, and no static
check sees any of them: `registry_coverage_check` reads twelve tables and none is
this, `check_pipeline_order.py:118` merely NOTES the binding, and
`tax_acceptance_check` checks names rather than the pairing they resolve to.


### A SECOND SHAPE: a check that cannot produce a false pass, and is still wrong

**This is not a seventh instance. It is the class seen from the other side**, and
it is worth its own heading because the six above all share a tell that this one
does not have: they let something through. This one lets nothing through and is
still false.

**GATE 6 asserted against the wrong number and could not have failed for it.**
Written 2026-09-18, it summed every `FY_TAX_STATEMENT` row -- including the final
year's UNASSESSED liability, which section 3(9) charges after the window closes
and for which no cash was ever deducted -- while its message and its docstring
called that figure `cum_tax`. Since `total >= assessed`, `gap >= total` implies
`gap >= assessed`: the assertion was STRICTER than the identity, so **no
implementation could fail it that would have passed the correct one.** Nothing
was let through. The label was simply not true, and the derived "foregone
compounding" it printed was understated by the unassessed amount -- midcap150
Rs 568,484.22 reported against Rs 602,155.30 actual.

**A GATE EXERCISED ON A SINGLE CASE IS A GATE WHOSE LABELS HAVE NOT BEEN READ.**
It was written against midcap50, whose unassessed row is 0.00 -- as is nifty50's.
On either, the total and the assessed figure are the same number and the label
reads correctly. It took midcap150 (Rs 33,671.08) and nifty100 (Rs 11,521.13) to
separate them.

**WHAT FOUND IT WAS WIDENING THE INPUT SET, AND THAT IS NOW THE THIRD TIME:**

| defect | what it was doing | what widened |
|---|---|---|
| `seed_noise_measure` / `seed_noise_report` unimportable for two weeks beside four green checkers (instance 2) | nothing imported them, so nothing failed | the CONTROL ARM of an unrelated rename experiment |
| `make_combined_universes.FILES` naming six trade logs that do not exist | six producer edges resolved to nothing, silently | wiring a FOURTH universe -- midcap50, with nothing run on it, had better edge coverage than the three producing the published numbers |
| GATE 6 labelling the statement total as `cum_tax` | passing, by being stricter | running it on four universes instead of the one it was written against |

**NONE OF THE THREE WAS FOUND BY A CHECK.** Each was found because something was
run over a wider set than the set it was built against, and the widening was
incidental every time -- a control arm, a new universe, a second and third and
fourth run of an existing gate. **A checker validated on one case is evidence
about one case.** There is no gate for this and this entry does not propose one;
what it proposes is that a new check be run against every case available before
it is trusted, and that the cost of doing so be counted as part of writing it.


### What they have in common

Not that the checks were missing. **Success and partial success were
indistinguishable at the only moment anybody looked.** Every one of them would
have passed `git commit`; three of the four would have passed CI.

Related in kind, and already recorded separately because their mechanism is
different: `unresolved` is not fatal in `check_pipeline_order` (below), and the
`.source` sidecar the cache-restore path used to drop -- a panel that arrived
without its provenance and was trusted anyway.

### What check_all.py does

| gate | what it refuses |
|---|---|
| 1 IMPORTS | any module in the repository that does not import. Instance 2, on day one. |
| 2 TABLE | `PIPELINE_ORDER`'s row count against `run_all.PIPELINE_ROW_COUNT`, every script column resolved to a file, and every row naming a REGISTERED universe. Instance 3, at the table rather than at the first consumer. |
| 3 ENTRY POINTS | a pipeline script with no live `__main__` block, **by AST** -- a grep passes instance 4. |
| 4 OUTPUTS | with `--since`, a step that ran and left nothing with a moved mtime inside its declared span. Instance 4 again, from the other side. |
| 5 DELEGATES | the four existing checkers, folded in, so "I ran the checks" means one thing. |

Two declarations keep it honest rather than permanently red: `KNOWN_UNIMPORTABLE`
names four modules that cannot import, each with its reason, and **fails if a
listed one starts importing** -- a stale exception is how such a list stops
meaning anything. `NAMING_UNDECLARED_BASELINE` pins
`naming_declare_check`'s pre-existing 111 undeclared writes and fails only if the
number grows.

**What gate 4 is not.** It was specified as a per-step output manifest. It is not
one, deliberately: a second list of what each step writes is a list that can
disagree with the code, which is what `REQUIRED_INPUTS`, `PIPELINE_ORDER`,
`REPORT_ORDER` and `FILES` each did once. `check_pipeline_order`'s scanner cannot
supply it either -- `_scan` on an entry point alone returns ZERO writes for all
ten steps, because a step is scanned concatenated with its helpers. So gate 4
uses the span the table already declares and asserts an mtime moved inside it.
Coarser than a manifest; exact on the case that has happened four times. Four
whole-run steps declare no span at all, and gate 4 SAYS SO per step rather than
counting them as passed.

---

## `unresolved` is not fatal, which is why the same silent failure has happened four times

Written 2026-09-18. OPEN, and this entry exists because it has been a comment in
`check_pipeline_order.py` rather than a tracked issue, which is why there have
been four.

### The mechanism

`check_pipeline_order.py` classifies every path expression it finds as a write, a
read, or `unresolved`. A step that cannot be FOUND is fatal -- that was made fatal
deliberately, and the comment at its raise says why: *"It was a banner, and that is
how STEP 16 went unchecked from whenever it was added until 2026-09-04, and STEP 17
from 2026-09-11."*

**`unresolved` was never given the same treatment.** It is printed at the end of
the run and gates nothing. The check exits 0 today with six entries in it.

So any change that stops an edge resolving does not fail the build. It removes the
edge from the ordering check and prints one more line in a list that is six lines
long already.

### The four instances, all recorded in that file's own comments

| # | what changed | what was lost |
|---|---|---|
| 1 | STEP 16 added | the step was unchecked from whenever it was added until 2026-09-04 |
| 2 | STEP 17 added | unchecked 2026-09-11 until the run that found it |
| 3 | the three audit scripts collapsed into `audit_step.py` | `TAG_CALL` matched nothing, four producer edges vanished, check still reported success |
| 4 | `config_mid.py` / `config_n100.py` folded into the registry (step 7) | `DIR_ASSIGN` and `PATH_EXPR`'s dotted branch key on a `config*` module and no source names one any more; without `REG_ASSIGN` all eight STEP 12b producer edges would have gone, silently |

Instances 1 and 2 were fixed by making a missing STEP fatal. Instances 3 and 4
were each fixed by adding a pattern -- and each was found by a human reading the
output, not by the check failing.

### THE FIFTH INSTANCE WAS PREVENTED ON 2026-09-18, AND THAT IS A DECISION TAKEN

The planned work was a registry-driven `FILES` loop in
`results/make_combined_universes.py`, replacing two hand-written per-universe
blocks. `REG_ASSIGN` and `REGISTRY_CALL` both require a QUOTED LITERAL tag, so
`M = REGISTRY[t].metrics_dir` matches neither, and the loop's edges would have
fallen into `unresolved` with the check still reporting success. Instance five, by
the same mechanism as three and four.

The obvious repair was to teach the scanner to fan a loop-bound variable out over
its row's declared span. **IT WAS MEASURED BEFORE IT WAS BUILT, AND IT WAS NOT
BUILT.** Probed on synthetic source:

```
declared span ('mid','n100'), source writes results_mid ONLY
    (an `if t == "mid":` guard inside the loop)
with fan-out, the scanner would credit  results_n100/mid_only_artefact.csv
```

**That converts the failure from a SILENT MISS into a SILENT INVENTION**, and
`unresolved` is structurally incapable of catching the second: it grows when
something fails to resolve, and never when something resolves WRONGLY. A missing
edge leaves the ordering check weaker; an invented edge makes it assert an
ordering the code does not have.

So fan-out was rejected and the `FILES` loop was not written. The two hand-written
blocks stay. They are repetitive, but each one is honest, and
`registry_coverage_check.py` fails closed when a universe is missing from them --
which is a real net, unlike `unresolved`. Eight more universes may land as eight
more blocks. **This is a decision taken, not an idea someone had and dropped.**

See also `run_all.SPANS_REGISTRY`, whose definition records that the sentinel is an
unverifiable claim about its own source for the same reason.

### Triage of the six current entries, 2026-09-18

Making `unresolved` fatal today would fail the build at six. They are not one kind
of thing:

**Two are not pipeline edges at all, and are MISATTRIBUTED.**
`make_chart.py -> results_midcap150/{sym}.csv` and its nifty100 twin come from
`results/make_chart.py:211`, `config.read_price_csv(_raw / f"{sym}.csv")` where
`_raw = u.prepare_data_dir()` -- the CONSTITUENTS SYMLINK DIRECTORY under
`data/raw`, not a metrics directory. The scanner has attributed a raw price read to
`results_midcap150/`. It lands in `unresolved` only because `{sym}` cannot expand, which
accidentally conceals the misattribution: were the placeholder expandable it would
resolve to the WRONG directory. These should be excluded from candidacy, not
resolved.

**Two are real edges and are fixable.**
`make_audit.py -> results_{midcap150,nifty100}/v2FINAL_equity{_cad}.csv`, from
`results/audit_step.py:166`, where `_cad = cadence.suffix() + profiles.suffix()`.
The edge is real -- at the default selection both suffixes are `""` and the file
is the canonical `v2FINAL_equity.csv` written by `engine_v2_final.py`. The scanner
refuses to expand a runtime-composed placeholder. Pinning axis suffixes to their
defaults when scanning would resolve these, and matches the naming rule the whole
project already uses: the default is unsuffixed.

**Two are real edges and are NOT fixable without the mechanism just rejected.**
`make_daily_log.py -> ?/daily_skipped_{tag}.csv` and `?/{f}_{tag}.csv`, from
`results/make_daily_log.py:219-220` inside `load(M, tag)`. Both the directory and
the tag are FUNCTION PARAMETERS. The reads are real -- the trail files are written
by `make_audit.py` -- but binding a parameter to a directory is the same capability
as binding a loop variable, and it carries the same silent-invention risk. Note the
directory prints as `?`: not even the universe is known.

### WHAT THIS MEANS FOR THE GOAL

"Make `unresolved` fatal" is NOT achievable as stated, and that is the useful
finding. Two of the six cannot be resolved without building the thing that was
just declined on safety grounds.

What is achievable is **fatal against a declared allowlist**: exclude the two
misattributions from candidacy, resolve the two suffix ones, and DECLARE the two
parameter-bound ones as known-unresolvable with their reason written down -- then
make any entry outside that list fatal. That is strictly better than today,
because a NEW unresolved entry becomes a build failure while the known ones stop
being anonymous. It is the same shape as `REQUIRED_INPUTS`' fourth field: the thing
that cannot be derived is declared, and the declaration is what fails.

NOT DONE HERE. Recorded so the sixth instance is recognised as the sixth.


---

## `dd_label` is two identical lambdas, and the next edit will reach only one of them

Recorded 2026-09-18, read-only, while reviewing nifty50's wiring. **Not a defect
today: the two copies are byte-identical and produce identical output.** It is
recorded because the mechanism is the one this file already has a name for --
*duplication copies defects as faithfully as it hides divergence* -- and this is
a fresh instance created on purpose, with nothing watching it.

### What it is

`universes/registry.py` carries `chart_text["dd_label"]` on three rows. midcap150's
differs from the other two and always did; nifty100's and nifty50's are the same
expression:

```python
"dd_label": lambda lab, mn: f"{lab.split('  [')[0]} (max {mn:.1f}%)",
```

Verified by `inspect.getsource` on both objects: identical source text, and
identical output on a sample input (`'v2 drawdown (max -21.9%)'`). They compare
unequal only because two lambda objects have different `repr`s, which is exactly
what would hide the divergence if one were edited.

### Why it was written twice rather than shared

nifty50's row was authored by following nifty100's, deliberately: nifty50 is a strict subset
of nifty100 and the two are meant to be read against each other, so the rows were
kept parallel. The label reaches the PNG's drawdown panel. A shared constant
would have been the alternative and was not taken, because the registry's whole
design is that a universe is ONE ROW and rows do not reach into each other --
the same argument that keeps `FILES` written out per universe instead of looped.

### What makes this the recognisable shape

The drawdown-panel label is the specific thing that a checksum found and a grep
did not, on 2026-09-15: the line it sits on contains no render keyword, so a
keyword survey of render parameters missed it. That note is in this file already.
The label now exists in two places, and the survey that missed it once would
miss it twice.

### What would actually close it

Not a shared constant -- a comparison. Any check that renders every registered
universe's `chart_text` values and refuses when two rows disagree in a way no row
declares would catch a one-sided edit. Nothing like that exists, and five more
universes are coming, each of which will copy one of these three rows.

NOT DONE HERE. Recorded so a one-sided edit is recognised as one.


---

## Three chart-line colour pairs are indistinguishable, and nothing checks any palette

Measured 2026-09-18 with CIEDE2000 over sRGB->Lab (D65), and over Vienot 1999
dichromat simulations for deuteranopia and protanopia, on the exact line set
`make_combined_universes._series()` draws: per universe its selected arms plus
its own buy&hold (`chart_colours[2]`) and its own cap-weighted index
(`chart_colours[3]`). Twelve lines on the canonical chart, eighteen under
`--arm all`.

### The three, none of which involves nifty50

| pair | vision | dE2000 |
|---|---|---|
| `midcap150/v2` `#e377c2` vs `midcap150/v1` `#17becf` | deuteranopia | **4.24** |
| `nifty100/v1` `#2e6da4` vs `nifty100/v3` `#7f3f98` | deuteranopia | **3.26** |
| `midcap150/v4` `#e6ab02` vs `nifty100/bh` `#3a9d3a` | protanopia | **10.75** |

The just-noticeable difference is about 2.3. The first two are barely above it:
for a reader with deuteranopia those lines are the same colour, and in both
cases the two lines belong to the SAME universe, so the legend's universe label
does not separate them either. The third is just over 10 and is listed for
completeness rather than as a defect.

**In normal colour vision the shipped palettes have no pair below 11.7.** This is
a colour-vision-deficiency finding, not a general legibility one.

### Known, unfixed, and untouched by the commit that found them

They were found while checking nifty50's palette, and nifty50's was replaced in that
commit. **These three were deliberately not touched.** midcap150's and nifty100's tuples
are used by `chart_mid_FINAL.png`, `chart_v34*.png`, `chart_n100*.png` and every
combined figure; changing any of them re-renders published artefacts for a
reason that has nothing to do with the panel migration those artefacts were just
regenerated for. An artefact that moves should move for one stated reason, and
"the colour was hard to tell apart under deuteranopia" is a different reason from
"the panel changed". It belongs in its own commit, with its own before/after.

Linestyle carries some of the load already -- arms solid, buy&hold dashed, index
dotted -- so `midcap150/v2` vs `midcap150/v1` is two solid lines and is the worst of the
three in practice.

### NOTHING GATES THIS, AND THE NEXT UNIVERSE CAN REINTRODUCE IT

nifty50's first palette was matplotlib's `tab10` head, chosen by eye. It collided
with nifty100 three ways IN NORMAL VISION -- buy&hold `#2ca02c` vs `#3a9d3a` at
**2.13**, below the JND; index `#111111` vs `#000000` at **2.96**; and nifty50's
SHIPPING line `#1f77b4` vs nifty100's control `#2e6da4` at **4.18** -- and it passed
every check in this repository. `registry_coverage_check.py` verifies that a
universe HAS a `chart_colours` entry, and the field having no default means the
row cannot be constructed without one. Neither asks what the colours ARE.

Five more universes are coming. Each will copy one of the three existing rows.

### Is a check cheap enough for registry_coverage_check.py?

**Computationally, yes, and by a wide margin.** Eight universes at six slots is
48 colours, 1,128 pairs, three vision models -- microseconds. It needs no new
dependency: sRGB->Lab, the Vienot matrices and CIEDE2000 are about 90 lines of
arithmetic, and `requirements.txt` gains nothing. The checker already imports
`universes.registry` directly at `main()`, so unlike the four tables it reads
with `ast` there is no import-refusal problem to work around -- the values are
right there as data.

**The cost is not the code. It is that the check FAILS THE DAY IT IS ADDED**, on
the three pairs above, none of which this commit is willing to move. So adding it
means one of:

  - fixing midcap150's and nifty100's palettes first, which re-renders published artefacts
    and is the separate commit described above; or
  - shipping it with a declared-exception list naming those three pairs and the
    reason each is tolerated -- the same shape as `gate_compare.py`'s accepted
    `git_state` field and `check_pipeline_order`'s allowlist, where the exception
    is DATA the gate reads rather than an argument made at review time.

The second is the cheaper and the more honest of the two, and it has this
repository's own precedent behind it. It also has the failure mode those
precedents warn about: an exception list is a place to put a pair you did not
want to fix, and it grows.

A third consideration decides nothing but is worth stating: the threshold itself
is a judgement. dE 10 is what nifty50's replacement was searched against, and it is
neither a standard nor a measurement -- it is four times the JND, chosen because
it was achievable against the fixed palettes without moving them. A gate would
have to write that number down and defend it.

NOT DONE HERE. Recorded so the next palette chosen by eye is recognised as the
second one.

---

## Compound identifiers still carry old tags, and most of them cannot be renamed

Three prose passes on 2026-09-18 renamed the BARE tags in this file: `mid` ->
`midcap150` (166 of 215), `n100` -> `nifty100` (142 of 170), `n50` -> `nifty50`
(12 of 13). **None of them touched a compound identifier**, and that is not an
oversight -- `\bn100\b` does not match `build_scores_n100.py`, because `_n` is not
a word boundary. Compounds are a separate population of 142 occurrences, surveyed
disk-first on 2026-09-18.

### THE 49 THAT NAME MERGED SCRIPTS -- DO NOT RENAME THESE

**These eleven names exist on disk under NO name, old or new, because the scripts
were MERGED rather than renamed:**

| what this file says | what actually happened |
|---|---|
| `make_mid_chart.py`, `make_n100_chart.py` | merged into `results/make_chart.py` |
| `config_mid.py`, `config_n100.py` | merged into `config.py` |
| `build_scores_mid.py`, `build_scores_n100.py` | merged into `results/build_scores.py` |
| `engine_v2_final_mid.py`, `engine_v2_final_n100.py` | merged into `results/engine_v2_final.py` |
| `make_mid_audit.py`, `make_n100_audit.py` | merged into `results/make_audit.py` |
| `make_combined_n100_mid.py` | merged into `results/make_combined_universes.py` |

**A token-for-token rename here INVENTS ELEVEN FILES THAT HAVE NEVER EXISTED** --
`make_midcap150_chart.py` is not a file this repository has ever contained. It is
the false-record mistake, at a third of the compound population in one go.

**WHOEVER DOES THIS REWRITES THE SENTENCES, NOT THE TOKENS.** "the two chart
scripts" became one script; a sentence built on there being one per universe does
not survive a substitution, however careful. It is a separate job and is NOT
QUEUED. Until it is done, every one of these 49 sites is knowingly stale, and
that is preferable to 49 sites that are confidently wrong.

### Compounds whose file still exists under its OLD name -- also not candidates

`mid_jackknife.py`, `n100_jackknife.py`, `mid_topn_test.py`, `runs/mid/`,
`diagnostics/shuffle_{mid,n100}.txt`, `diagnostics/topn_{mid,n100}.txt`,
`diagnostics/n100_jackknife.txt`. The prose pointing at these is CORRECT AS IT
STANDS. Renaming it breaks a working reference. Same standing note as the bare-tag
passes: whoever renames these files comes back to this document.

**Before DELETING any of these, read "An old-looking name is not evidence of an old-named duplicate" under "If you are reading an old-named thing" in `PANEL_MIGRATION.md`.**

### Four compounds that looked unresolved, and what they turned out to be

Recorded because each cost a lookup and three of the four are now CLOSED:

1. **`results_MID_/metrics/daily_trades_mid_tradeable.csv`** -- **CLOSED.** It is
   inside a fenced block: verbatim captured console output. The odd casing is what
   the tool printed. A record, and it stays exactly as it is.
2. **`mid_v3`** -- **CLOSED, and the claim still holds on a narrower proof.** Not
   a file but a run/baseline stem. It existed on disk under that name in three
   places: `runs/20260917T011927_mid_v3_r20`, `runs/20260917T002447_mid_v3_r20`,
   and `pre_repoint_baseline/metrics_mid/`*`_mid_v3.csv`.
   **THE TWO `runs/` DIRECTORIES WERE DELETED ON 2026-09-20** with the other nine
   timestamped old-panel run folders. They were kept until then for exactly this
   sentence -- they were the on-disk proof that `mid_v3` is a real stem and not a
   typo, and that is why a cleanup on 2026-09-18 left them alone. The proof is
   now `pre_repoint_baseline/metrics_mid/`*`_mid_v3.csv`, which is not going
   anywhere: it is the only surviving copy of the pre-repoint figures. Old name
   exists, so still not a candidate.
3. **`mid_jackknife.edge`** -- **CLOSED.** Not a file extension. It is a METHOD:
   `mid_jackknife.py:50`, `def edge(drop=())`. The module exists under its old
   name; nothing to rename.
4. **`diagnostics/mid_jackknife.txt` IS ABSENT WHILE `diagnostics/n100_jackknife.txt`
   EXISTS -- OPEN.** The jackknife diagnostic was written for one universe and not
   the other, and nothing in this repository says which of the two it is: never
   produced for midcap150, or produced and deleted. **Do not write prose that
   assumes the pair is symmetric**, and do not let a reader rediscover this from
   scratch -- it was found on 2026-09-18 during the compound survey. Resolving it
   means finding the step that writes `n100_jackknife.txt` and asking why it has
   no midcap150 sibling.

---

## The chart's `expected` cross-check is deleted, and must not return as a derived value

`results/make_chart.py` printed, directly beneath the measured index window:

```
    expected                : 6,342 -> 21,926 = 3.46x = 18.16% CAGR
```

**It was a hardcoded literal, printed for EVERY universe.** Those are midcap150's
figures. nifty100 measures `11,148.80 -> 25,757.40 = 2.3103x = 11.6567%` and
nifty50 `10,910.10 -> 24,207.75 = 2.2188x = 10.9808%`, and both printed
midcap150's numbers underneath their own as though confirming them.

**It was right for one of three universes, and since `43fbd2f` it was right for
none** -- that commit corrected midcap150's `index_window_end` from `2026-06-08`
to `2026-08-06`, which moved midcap150's own measured line to
`23,310.55 / 3.6758x / 18.6968%` and left the literal behind. A line that was
wrong twice became wrong three times, and nothing failed, because nothing compared
them.

### Why it was deleted rather than fixed, and why the obvious fix is worse

**DERIVING IT FROM THE SLICE IS A TAUTOLOGY.** `expected` sat one line below a
figure computed from `_w`; computing `expected` from `_w` as well makes the two
agree by construction. It would print a permanently green line that CANNOT FAIL.
A check that cannot fail is worse than no check, because it occupies the place a
real one would take and reads, to anyone scanning the output, exactly like
confirmation.

**WHAT WOULD EARN A REGISTRY FIELD: the index provider's own published return for
this span, per universe.** That is an independent number -- it comes from outside
the computation it is checking, which is the whole point -- and **this repository
does not have it.** Until it does there is no check to make, so none is printed.

**DO NOT HELPFULLY REINTRODUCE THIS AS A DERIVED VALUE.** The deletion site in
`make_chart.py` carries the same reasoning in a comment, so the next reader meets
it before writing the line back.

## Two definitions of "prior-20-session median volume", and one is gone

Found and fixed 2026-09-20, at commit `7dd37d6`.

`tradability.median_volume` -- the one the participation cap actually consumes --
is `rolling(20).median().shift(1)` over the trading calendar, restricted to the
backtest window, with no `volume > 0` filter and **no value at all until 20
sessions exist**. `liquidity_participation.py` had its own: the last 20 dated rows
of the symbol's own file with `volume > 0`, taking whatever was there even when
fewer than 20 existed.

Both called themselves "prior-20-session median volume". They are not the same
number. Measured over every fill in the two midcap150 tradeable arms:

| | v1 (n=842 with both) | v2 (n=998 with both) |
|---|---:|---:|
| differ by more than 1% | 175 (20.78%) | 215 (21.54%) |
| differ by more than 10% | 61 | 77 |
| identical | 658 | 772 |
| largest divergence | 140.11% | 140.11% |

The largest is AUBANK 2019-10-29, where the cap's definition gives 16,661 and the
other 6,939. On v1 the two even disagree about whether a fill clears a 0.10 cap, on
n=1 fill of 842.

**`liquidity_participation.py` now calls `tradability.median_volume`** and has no
definition of its own. `volume_panel()` is deleted; it had no caller outside that
file. The cap's definition survives because a measurement of the cap that used a
different median than the cap would be measuring something nobody runs.

**`diagnostics/liquidity_participation.txt` on disk predates this change.** Its
figures -- including the 1,614.52% quoted in `EXPERIMENTS.md` and
`DRAWDOWN_EXIT_SPEC.txt`, and the "22 of 985 fills above 10%" in `EXP20_PREREG.txt`
-- were produced by the deleted definition. Regenerate before citing them again.

## The concentration figure: one basis, and the one that was rejected

Settled 2026-09-20 at commit `7dd37d6`, on the midcap150 tradeable arms.

**THE SURVIVING DEFINITION.** Share of total return earned on fills that would be
hard to execute:

> Match every fill into lots, FIFO per symbol, from `daily_trades`. A lot's P&L is
> `(exit price - entry price) x qty`; a lot still open at the window end is marked
> at its final holding price, so **every lot is counted, not just the closed ones**.
> Rank lots by the participation ratio of their ENTRY fill -- `qty / med20`, the
> cap's own denominator -- and take the top decile. The figure is their summed P&L
> over **total return, final equity minus starting capital**.

Entry-side ranking because the entry is the fill whose size you choose; total
return as the denominator because that is the number a reader is deciding about,
and it includes the transaction cost the lots do not carry.

| | lots | top-decile cutoff | lots in decile | share of total return |
|---|---:|---:|---:|---:|
| midcap150 v1 | 421 | q/med20 >= 0.0269 | 43 | **6.83%** |
| midcap150 v2 | 499 | q/med20 >= 0.0110 | 50 | **5.50%** |

The attribution reconciles: closed P&L plus unrealised minus TC comes to
Rs 9,209,690 against v1's actual total return of Rs 9,209,897, and Rs 5,150,186
against v2's Rs 5,150,399 -- a gap of about Rs 210 on each, from rounding in the
published TC.

**REJECTED, 2026-09-20: "realised P&L on closed lots only".** This was the Stage 1
basis and it gave 7.19% (v1) and 6.89% (v2). Rejected because its denominator is
the P&L of closed lots rather than the return anyone earned, so it silently drops
both the unrealised P&L and the transaction cost, and the number it produces cannot
be checked against final equity. It is recorded here rather than deleted because
the two figures differ by only about a third of a point and someone will otherwise
recompute it and think the difference is a bug.

**ALSO REJECTED: the 18-19% that circulated before Stage 1.** It has no surviving
basis. Nothing in this tree produces it, and none of the eight bases computed on
2026-09-20 comes near it -- the closest, winners-only closed lots, gives 12.43% on
v1 and 9.61% on v2. The 18-19% figures that ARE in the tree are participation
percentages in `diagnostics/liquidity_participation.txt`, not return shares, which
is the most likely origin. **Do not cite 18-19% for concentration of return.**

**A STAGE 1 CAVEAT WITHDRAWN.** Stage 1 said roughly half of equity sat in
still-open positions and labelled its figure "closed half only". That was wrong: it
compared the open lots' COST BASIS against final equity. Only n=8 lots are open per
arm, worth Rs 62,265 unrealised on v1 and Rs 33,306 on v2 -- **0.7% and 0.6% of
total return**. Closed lots are 99.3% and 99.4% of it. Final holdings are indeed
98.07% and 87.43% of final equity, but that is market value of positions bought
along the way, not P&L still to be attributed. The question is answerable on
essentially the whole return, and no figure above needs a "closed half" label.

## What still rests on pre-repoint data

Surveyed 2026-09-20 at commit `8015eb6`. The universes were repointed at
`Final_Without_Survivorship_Data` on **2026-09-18**. Anything produced before that
date describes price data the tree no longer holds. This is an inventory, not a
re-measurement -- none of the figures below has been re-run.

**RE-RUN 2026-09-20 at commit `aa385d8`. This paragraph is kept as the record of
what was stale and is no longer current.** Both arms were re-run on the repointed
data; both params files now carry a `data_source`, GATE 8 failed on both for still
being listed as exemptions, and `GATE8_EXEMPT` dropped from 18 names to 16. The new
figures reproduce `PANEL_MIGRATION.md` §4's "new" column exactly: midcap150 v3
39.78 CAGR / 1.44 Sharpe / −54.10 MaxDD / 814 trades / final equity 11,945,809.95,
and nifty100 v2 19.01 / 1.50 / −21.87 / 940 / 3,628,639.83. The old figures were
52.69 / 1.86 / −29.60 / 822 / 22,977,199.75 and 24.43 / 1.72 / −18.38 / 965 /
5,047,246.65. The moves are not attributed; §4 of PANEL_MIGRATION records that
midcap150 v3's drawdown move has not been investigated.

**Published metrics artefacts: 10, all from 2026-09-17 01:19.** They were two arms
that nothing had re-run since:

- `results_midcap150/metrics/` -- `v34_comparison_v3.csv`, `v34_equity_v3.csv`,
  `v34_subperiods_v3.csv`, `chart_v34_v3.png`, `chart_midcap150_FINAL_v3.png`
- `results_nifty100/metrics/` -- `v34_comparison_v2.csv`, `v34_equity_v2.csv`,
  `v34_subperiods_v2.csv`, `chart_v34_v2.png`, `chart_nifty100_v2.png`

Every other artefact under `results_*/metrics` (683 files across eight universes)
and all 399 under `nautilus/reports` post-date the repoint. Two of the 18 GATE 8
exemptions -- `v34_params_v3.json` on midcap150 and `v34_params_v2.json` on
nifty100 -- are these same two arms, which is why they have no `data_source`.

**Diagnostics: 36 of 63 predate the repoint**, all stamped 2026-09-17 00:12. The
ones whose headline numbers are quoted elsewhere in this file or in
`experiments/`:

`v34_report.txt`, `verify_v34_arms.txt`, `validate_sizing_mid.txt`,
`validate_sizing_n100.txt`, `breadth_live_mid.txt`, `breadth_live_n100.txt`,
`n100_jackknife.txt`, `task1_v1_vs_v2.txt`, `task2_ic_decay.txt`,
`task3_impact.txt`, `edge_alive_n100.txt`, `vol_scaled_comparison.txt`,
`equity_gap.txt`, `equity_gap_reconcile.txt`, `mid_reconcile_cause.txt`,
`mid_weight_proof.txt`, `mid_investval_probe.txt`, `locked_cash_check.txt`,
`listing_history_check.txt`, `n100_membership_v2_report.txt`,
`nt_reports_verify.txt`, `nt_verify_n100.txt`, `nt_verify_after_bartick.txt`,
`nt_verify_after_finalday.txt`, `nt_verify_post_finalday.txt`,
`nt_verify_post_runall.txt`, `bar_tick_fix_ab.txt`, `bar_tick_fix_detail.txt`,
`equity_final_day_fix.txt`, `task3_ntverify.txt`, `topn_centralise_hashes.txt`,
`PIPELINE_AUDIT.txt`, `nse_tick_circulars.txt`, and the three under
`diagnostics/membership/`.

`liquidity_participation.txt` and `depth_compare.txt` were on this list and were
regenerated on 2026-09-20. Both now carry their date, commit and data digest;
nothing else here does.

**ALL 36 WERE STAMPED 2026-09-20.** Each now opens with a header giving its
production date, saying it predates the repoint, giving the two re-measured figures
that moved further than the findings they supported, and saying its numbers are not
to be quoted without a re-run. Ten of the 36 have no row in
`diagnostics/INVENTORY.csv`, so their production date is genuinely unknown and the
header says so rather than guessing: `PIPELINE_AUDIT.txt`, `breadth_live_mid.txt`,
`breadth_live_n100.txt`, `n100_jackknife.txt`, `nt_verify_n100.txt`,
`topn_centralise_hashes.txt`, `v34_report.txt`, `validate_sizing_mid.txt`,
`validate_sizing_n100.txt`, `verify_v34_arms.txt`. The 2026-09-17 00:12 filesystem
stamp they all share is when the tree was copied, not when they were measured.

**`task3_impact.txt` CANNOT BE RE-RUN, and that is a finding rather than a gap in
this turn's work.** It was scheduled for a re-run on 2026-09-20 because Stage 2B's
impact model was to be judged against it. No generator script for it survives
anywhere in the tree, and two of its three universes -- the 58 and the 74 -- were
deleted on 2026-09-11 with their raw data and registry entries. Its header says so.
**Stage 2B has no pre-repoint impact baseline to be judged against**, and one
cannot be reconstructed from this repository.

**WHY THIS MATTERS MORE THAN THE DATE SUGGESTS.** Two figures have now been re-run
after the repoint and both moved further than "a data refresh" implies: the largest
midcap150 participation went from 1,614.52% to 34.46%, and the depth cost from 1.80
CAGR points to 0.04. In both cases the change was larger than the finding itself.
**Do not assume a pre-repoint diagnostic is approximately right.** Either re-run it
or quote it with its date.

