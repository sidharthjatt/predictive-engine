# Known issues

> **NAMING.** Every universe has one name: `nifty50`, `nifty100`, `nifty200`,
> `nifty500`, `midcap50`, `midcap100`, `midcap150`, `smallcap250`. The short tags `mid`,
> `n100` and `n50` were retired on 2026-09-18 and are refused with the list of valid
> names; in dated records `mid` means midcap150, `n100` nifty100 and `n50` nifty50. The
> map is in [PANEL_MIGRATION.md](PANEL_MIGRATION.md). The universes called the 58 and the
> 74 were deleted on 2026-09-11 (`git show 50562ed:RETIRED_UNIVERSES.md`).

What is true of this repository now: open defects, limits, deliberate decisions a
reader has to know, and caveats on the published figures. Entries that were fixed,
closed or superseded have been removed; the full record up to 2026-09-29 is in git
history (`git show c63b45b:KNOWN_ISSUES.md`). The current figures are the 2026-09-27
republish on cleaned prices (README, "Current results").

Scope: live orders are built outside this repository (last section). Survivorship work
comes later.


---

## Reading the results

### The after-tax noise test on the cleaned prices, 2026-09-29

`experiments/CLEANED_NOISE_PREREG.txt` was committed before any draw (d4ea256). It ran
88 of 88 draws; all eight baselines passed and no draw failed. Report:
`diagnostics/cleaned_noise.txt`. Records: `diagnostics/cleaned_noise_runs.csv`.

- 15 of 32 cells are supported under both profiles, and research and tradeable agree
  on every cell. The table is in README, "Current results".
- No cell of nifty100 or midcap50 is supported. No v2 cell is supported outside
  nifty500, and nifty500 v2 passes even though its sigma-0 gap is -1.33.
- All 15 are port-verified since the quote-mid rule (Pass I). The report keeps the
  labels fixed at registration, so 8 of them still show as "not port-verified" there.
- The draws are biased in one direction per universe, so the rule's count of draws
  above zero is biased too. See "The noise draws and the published run".

### The noise draws are biased by exact zero returns

`results/nifty500_baseline_trace.py`, report `diagnostics/nifty500_baseline_trace.txt`.
- At sigma 0, 0.72% of close-to-close returns are exactly zero (nifty500, 2019 onward),
  from tick size, illiquidity and circuit locks. Every draw gives each a random sign.
- The raw 20-day up-day share behind `trend_consistency_20` therefore changes on 8.7% to
  9.1% of rows in every draw, always upward. `downside_vol_60` and `rev_1` shift the
  same way. Low-priced names with many flat days move most: JPPOWER moves +2.0
  cross-sectional sd on that feature.
- All ten nifty500 draws, on all four arms, first hold different names at the first
  rebalance (2019-01-01), and nearly the same names swap each time. It is not exact
  score ties and not the `clean_exempt` rows. Swapping in one draw's
  `trend_consistency_20` alone moves that first rebalance.
- The same effect is on every universe: the sigma-0 gap lies outside all ten draws in
  15 of 32 research cells (`diagnostics/cleaned_noise_runs.csv`), against about 6
  expected by chance. It is below every draw on nifty500 v1, v2 and v4 and midcap100
  v3, and above every draw on the other 11.

What to read into it. A live run is computed like the published run, because live
prices have exact zero returns too. The draw means are not a better estimate: the
nifty500 draws sit above the published run because of the shift. The spread still
measures sensitivity. Across a cell's ten draws CAGR spreads over 1.8 to 12.4 points
(median 5.3), and a live result should be expected to differ from the published one by
that much. The registration carries a dated addendum saying so; its verdicts stand.

### Survivorship bias is not removed

Every universe is today's index members applied back to 2019. The work to remove the
bias is planned for later. What is known now (`survivorship_attribution.py`,
`diagnostics/survivorship_attribution.txt`, an estimate, not a backtest, on the 15
supported cells):
- The supplier's membership files (`data/raw/Survivorship_Bias/`) are not point-in-time.
  Their symbols column is today's list edited backwards (the 2018 Nifty 50 rows list
  JIOFIN, listed 2023), and all eight fail `survivorship.validate`. Only their
  inclusion and exclusion events are usable, and those miss scheduled reviews: none of
  the files records the 2024-09 or 2025-03 reconstitution, and the six universes with a
  supported cell miss 6 to 9 of the 15 reviews in the window.
- So 46% to 79% of each arm's profit is on position-days the files cannot classify.
  Removing the profit they mark as held while not a member moves the gap by -3.3 to
  +1.0 points. Reading every unknown day as the events imply, which assumes no event is
  missing, moves it by -11.9 to +0.7 and leaves nifty500 v1 and v4 below zero.
- A run restricted to point-in-time members is not possible with these files: reviews
  are missing, and 3 to 96 names that left an index during the window have no price
  file (some may be renames outside the 15 validated ones).

### The rank-8/rank-9 boundary is thin on every universe

`results/selection_margin.py`, rows `diagnostics/selection_margin_cleaned_20260927.csv`.
On the cleaned prices, the median score gap between rank 8 and rank 9 at a rebalance
is 0.44% (nifty200, nifty500) to 1.08% (midcap100) of that day's score range. It is
under 1% of the range on 46% to 73% of rebalances. So a small change to any input can
swap a held name. That is why the cleaning and each noise draw move the figures as much
as they do. On the uncleaned data the margin did not predict which cells moved most
under the cleaning (Spearman -0.19, p 0.29, 32 cells).

### Two buy & holds are published, and a gap against one cannot be carried to the other

- **Reference.** A costless index line rebalanced daily. It holds no lots, so it cannot be taxed.
- **Investable.** An equal-rupee basket of real lots, bought at the first open and never sold. It is the only one that can be taxed, and every after-tax gap is measured against it (`bh_investable` in `diagnostics/cells_cleaned_20260927.csv`).

The difference between the two does not have one sign. On the cleaned prices the investable basket beats the reference in midcap50 (25.97 against 23.73) and, narrowly, in smallcap250 (26.60 against 26.56). It trails in the other six, by 0.52 (nifty100) to 1.77 points (midcap100). Take the benchmark from the same table as the arm's figure. Moving a figure between the tables changes the gap by up to 2.2 points, and none of that change comes from the strategy.

### v2 and v4 trade return for drawdown, and no published comparison separates the two

The breadth rule (v2, v4) moves the book to cash when breadth collapses. The same rule produces the shallower drawdown and misses the rebound days after a crash. On the cleaned prices (research, tax off, n=1), v2 has lower CAGR and shallower MaxDD than v1 in all eight universes. Example: nifty100 v1 28.01% / -33.02%, v2 20.44% / -19.78%.

Every published gap compares an arm that is partly in cash with a buy & hold that is always fully invested. That comparison mixes what selection earns with what the exposure rule spends and buys. No script builds an exposure-matched benchmark, meaning the universe held at the arm's own daily invested fraction. The only such measurement (2026-09-11, retired data) found that the exposure rule alone gave about 90% of the drawdown reduction. It has not been repeated on current data. Whether the trade is worth making is a risk decision and is not a defect.

`validate_sizing.py:242` and `results/validate_engine.py:215` print "CAGR moves +/-0.5% per refit". That figure was never measured. The last seed-noise measurement (`diagnostics/seed_noise.txt`, 2026-09-20, pre-numerics) found sd about 1 point.

### v2's smaller drawdown comes mostly from the breadth rule, not from selection

v2 and v1 hold the same selection; v2 scales exposure by breadth and v1 stays
fully invested. On the 2026-09-27 figures (research, tax off, against the
reference buy & hold), v2's drawdown is 9.6 to 24.5 points shallower than buy &
hold's in every universe. v1's is at most 13 points shallower, and on nifty500
(-47.08 against -41.56) and midcap150 (-40.76 against -37.67) it is deeper than
buy & hold. The share of v2's advantage that survives at full deployment runs from
-47% (nifty500) to 53% (smallcap250).

So the drawdown result is the exposure rule going to cash when breadth falls. It
also keeps the book partly out of the market in rebounds, which is part of why v2,
after tax, trails the investable buy & hold in six of eight universes. Do not read v2's
drawdown as evidence that the model picks safer stocks.

### New positions are funded from cash alone, so v1 and v3 often hold fewer than eight names

`backtest_exposure` sizes each entrant as a share of the whole portfolio
(`invest_val = port_val * exposure * 0.98`) but pays for it from cash only: held
names are never resized and buffer names (ranks 9-16 still held) carry capital
with no target weight. When the entrants do not fit, the lowest-ranked are
skipped and logged `cash short (before TC)`.

On the 2026-09-27 figures, the 100%-invested arms skip 98 to 165 buys per run and
hold a mean of 7.68 to 8.10 names across the eight universes; the breadth-scaled
arms skip 1 to 8 and hold 9.0 to 10.1. The counts are in every
`v34_comparison*.csv` (`CashShortSkips`, `MeanNamesHeld`). This is why
`results/validate_engine.py` fails T1 (mean book below `TOP_N`) on v1.

It is a trade-off, not a bug. Every alternative measured in 2026-09 that fills
the book (trimming the buffer, strict target weights, `funding="prorata"`) cost
CAGR on every universe then tested, because it spread capital over more,
lower-ranked names. `funding="prorata"` is implemented and off by default;
switching it moves every published figure and must be mirrored in
`nautilus/nt_strategy.py` in the same commit.

### The held-lots buy & hold is concentration-limited, and midcap50 exceeds the limit

bh_lots_after_tax.py withholds its tax-cost-of-turnover figure when one name
exceeds 11.62% of the held-lots buy & hold's final value. On the 2026-09-27 outputs
it withholds on midcap50 only: DIXON is 12.4% of that basket
(results_midcap50/metrics/BH_LOTS_midcap50_tax.csv). The README's midcap50 gaps
against the investable buy & hold use the same basket and carry no such note, so
treat them as resting on one name more than the other universes' gaps do. The
basket holds today's members backfilled to 2019, so a name that rose is in it
because it rose. The 11.62% limit and its 2.05-point effect size were calibrated on
the pre-repoint nifty100 measurement and have not been re-derived.

### The seed ensemble reduces variance far less than independent seeds would

The production score is the mean of ten LightGBM fits that differ only in seed
(`SEEDS` in `results/build_scores_step.py`). An ensemble of independent models
has error falling as K^-0.5. When this was measured (2026-09-02, 40 seeds,
nifty100 and midcap150, `results/seed_noise_measure.py`) the fitted exponent was
between -0.15 and -0.25 on every arm: seed-to-seed variation is mostly shared, so
ten seeds remove much less of it than the design assumes, and no practical K makes
a single run stable to half a CAGR point.

The measurement predates the 2026-09-24 numerics change and the 2026-09-27
cleaning, and `diagnostics/seed_noise.txt` does not reproduce its own baseline.
It has not been repeated. Do not quote its spreads as the current noise floor; the
current sensitivity evidence is the cleaned noise test
(`diagnostics/cleaned_noise.txt`), which holds the seeds fixed.

### The tradeable profile is ungated, and the cap can raise or lower a cell's CAGR

`--profile tradeable` adds only the participation cap (`profiles.py`). Nothing replays
the port under it (`profiles.UNGATED_NOTICE`). The figures are in
`diagnostics/tradeable_tax_all_arms.csv`, tax on, cleaned prices:
- The cap binds in 10 of 32 cells and changes the CAGR in 7. In nifty100 v1 and
  midcap50 v1 and v3 it binds without changing the CAGR.
- Largest changes: smallcap250 v3 -1.87 points (4 binds) and nifty500 v1 -0.98.
  midcap100 v1 gains +0.43 tax on but loses -0.94 tax off (README). Neither is
  investigated.
- Few binds does not mean small cost: 4 binds cost smallcap250 v3 almost two points.

### The tradeable profile does not cap the opening purchase

The cap needs each symbol's prior-20-session median volume. `results/tradability.py`
(`median_volume`, lines 157-161) drops every row before `BT_START_DATE` before it takes
the rolling median, and `profiles.cap_kwargs` passes that date. So no symbol has a
median for the first 20 sessions of 2019. `_participation_limit` then returns None, and
the fills of the 2019-01-02 rebalance go through uncapped (results/test_exposure.py:117-123).
The raw files hold warm-up data from 2018, so the median could be computed. The window
start is simply cut first. The unused impact model (`slippage.impact`) refuses such fills
and exempts them explicitly (`slippage.first_priced_date`, `resolve`). The cap does
neither and logs nothing.

### The participation cap changes which trades happen, not only what they cost

The cap in `backtest_exposure` (results/test_exposure.py:568-599) acts in three ways:
1. A shrunk order's unspent cash stays in cash for the session.
2. That cash can fund a lower-ranked name the loop used to drop.
3. The shrink can bring the order itself under the cash on hand. An order the research
   run skips as `cash short (before TC)` then executes under the cap.
So a tradeable run can hold a position its research twin never opened, and can finish
ahead of it. On 2026-09-22 this happened on nifty100 v1: VBL on 2019-01-30, +0.11.
Channel 3 does not imply a gain: two of the three cells where it appeared then finished
behind. Which channel drives today's midcap100 v1 gain (+0.43 tax on) has not been
checked. All of this moves with capital. Count the `participation cap` rows in a run's
own `daily_skipped` before repeating any of it.

### liquidity_participation.py cannot say a cell is unaffected by the cap

`liquidity_participation.py` compares executed research fills (`daily_trades`) with the
prior-20-session median volume. The cap acts on intended orders, and an order skipped
for cash never becomes a fill. So `research_fills_at_or_over_cap = 0` means only that
no executed fill reaches the cap. It does not mean the tradeable run equals the
research run: on 2026-09-22 nifty100 v1 scored 0 and still diverged. A non-zero count
does prove divergence. A correct predicate needs intended share counts, and no artefact
records them: `daily_skipped` gives the rupee need for a cash-short skip and no
quantity. `diagnostics/participation_predicate.csv` is from 2026-09-22, before the
numerics fix and the cleaning. Run the tradeable profile to find out.

### Tax deductions overdraw cash in 20 of 32 taxed cells, and the overdraft is free

`results/test_exposure.py` deducts each year's tax without a clamp. Measured with
`results/overdraft_measure.py` (`diagnostics/overdraft_on_tax_day.txt`), tax on, cadence
20, both profiles, read-only:
- Cash goes below zero in the same 20 of 32 cells under each profile: every v1 and v3
  cell, and v2 and v4 on midcap50 and smallcap250. Each episode starts on an assessment
  day; a cell spends 4 to 53 sessions below zero in all (median 21.5). The deepest is
  Rs -5,93,269 (nifty200 v3, 2025-04-01).
- While overdrawn the book buys nothing but keeps holding more than its equity, and
  with CASH_YIELD = 0.0 the negative balance costs no interest.
- Paying the tax instead by selling a pro-rata slice of every holding at the
  assessment day's open, with the usual slippage and charges and the sale's own gain
  taxed in the next financial year, moves the CAGR by -0.66 (smallcap250 v1 research)
  to +1.26 points (midcap150 v1), mean -0.04 over the overdrawn cells. The sign varies
  because the sale changes which names the later rebalances hold. The published
  figures are the engine's and are unchanged.
### Charges use the 2026-04-01 rate table for every fill since 2019; tax is dated

results/tax_util.py applies the capital-gains regime by sale date (15%/10% before
2024-07-23, 20%/12.5% from it). results/qbeast_in_charges.py has no date input:
compute_leg_charges() takes no date, and SPEC_LOCK fixes rates effective
2026-04-01, so STT, stamp duty, exchange and SEBI fees and GST are charged at
today's rates on every fill from 2019-01-01. The tax figures are period-accurate
and the charge figures are not, and nothing in an output says so. The size and
sign of the error are unknown because the historical rate tables are not in the
repository. Making charges dated changes every published cost figure.

### Nautilus figures differ from the engine's by up to 1.8%, and on the 100%-invested arms can hold different names

nt_verify gates the port against ARM D on the 0.01 grid, and all 32 cells pass. The
production port fills on the NSE 0.05 grid and the research engine does not round
prices (README, "The execution layer"). On v1 and v3 a buy is funded whole or skipped.
So a book a fraction of a percent different can fund a different name at a cash-short
skip, and that name's return then carries into the equity.
`diagnostics/nt_verify_all_arms_20260929.txt`: port minus reference final equity is
-1.82% (midcap100 v1) to +1.08% (midcap150 v3). Against the close-valued reference, the
port holds a different symbol set on 1 or 2 rebalances in 7 cells, all v1 or v3.
`nt_attribution.run` with only `tick_round` changed reproduced both sides of the two
largest forks on 2026-09-26. A Nautilus figure is not the engine's figure to the rupee.


---

## Tax and costs

### Costs are reported and reconciled in every run

`results/cost_report.py`, called from `results/audit_step.py` for every universe, arm,
cadence, profile and tax setting, writes `COSTS_<tag>.csv` (every fill: reference
price, fill price, slippage in rupees, each charge), `COST_LOTS_<tag>.csv` (every lot
sold), `COST_TAX_YEARS_<tag>.csv` (every financial year) and `COST_SUMMARY_<tag>.txt`,
which `run.py` prints at the end of `run.log`. The summary compares the arm with the
investable buy & hold held to the end and sold on the last day.
- The run fails unless, to the paisa: cash reconciles every day; slippage and the
  itemised charges every fill; tax every financial year (by replaying
  `tax_util.Ledger`); the totals; and the buy & hold, held and sold, against
  `bh_held.held_lots`. `cost_reconcile_check.py` (check_all) runs this on all 32 cells
  under both profiles with tax off and on, and each universe's buy & hold: 144
  combinations.
- Slippage in both profiles is `slippage.py`'s flat 0.15% of the reference price, the
  execution day's open (the close for the last-day sale where the open is missing).
  The size-sensitive term exists and no production caller uses it. The tradeable
  profile adds only the participation cap.
- Charges are the itemised Zerodha delivery rates in `results/qbeast_in_charges.py`.
  The charges section of `data/reference/TAX_AND_CHARGES.docx` (flat 0.11%, 4.5% cash
  yield, no DP charge) is out of date and is kept as a reference copy; its tax rules
  are the ones used.
- The report rounds as the engine does. The engine's prices are numpy floats, and
  round() on 1607.585 gives 1607.58 there and 1607.59 on a Python float; the buy & hold
  (`bh_held`) uses Python floats.

### How tax is settled at the window's end, and on a 31 March trading day

The rules are in `data/reference/TAX_AND_CHARGES.docx`. The owner decided the choices
below, on 2026-09-23 and 2026-09-25:
- FY2026-27, cut short by the data ending 2026-05-29, is settled on the last session
  with the full Rs 1,25,000 exemption (`tax_util.Ledger.due_on`, `assessed_basis =
  "backtest end"`). The document does not cover a window that ends mid-year.
- On a trading 31 March (2020 to 2023), the year is assessed after that day's fills, so
  a sale made that day is taxed. Every other year is assessed before the fills.
- The headline never sells, so the investable buy & hold pays no tax.
- "Sold on the last day" (`end_sale=True`) sells at the open, so it can come out above
  the headline (midcap50 v2).
- That sale is not participation-capped under `--profile tradeable`
  (results/test_exposure.py:619-642), and README publishes that column anyway. Deferred.
- `tax_acceptance_check.py` condition 4 checks all of this against hand-worked numbers.

### When in the day the annual tax is deducted

Each financial year is assessed once, on the first trading day on or after
31 March (TAX_AND_CHARGES.docx section 3(9)). The document does not say where in
that day the money leaves. results/test_exposure.py deducts it before the day's
fills, so the tax reduces the cash the morning's orders are sized from. Two cases
are deducted after the fills instead: a year assessed on 31 March while that day
is still inside the year (so a sale that day is in its own year's bill), and the
settlement on the final session. This ordering is our decision, not a quoted rule.

Because tax leaves cash inside the loop, a taxed run trades differently from an
untaxed one, and its tax is not the tax computed from an untaxed run's trade log.

### STCG and LTCG are netted in opposite orders, on purpose

results/tax_util.py allocates the short-term taxable base old-rate portion first
(line 345) and the long-term base new-rate portion first (line 357). Both are
copied from section 3.4 of data/reference/TAX_AND_CHARGES.docx (sha256
a5be987a1a75238796dd059c777b370b14be43f8a418206c93ee4201ddec8972; the file is
gitignored and not distributed). The point is to measure the strategy under that
document's rules, so do not make the two orders match. Change them only if the
document changes.

### The LTCG exemption follows the financial year; the rate follows the sale date

results/tax_util.py:207 gives the Rs 1,25,000 exemption to every year from FY2024-25,
while regime_of() sets the rate by sale date against 2024-07-23. So a lot sold in
May 2024 is taxed at the old 10% but draws the new exemption. The document's
section 3.1 table suggests otherwise; section 3.4's formula and section 3.6's
worked FY2024-25 row (split regime, exemption 125,000) give the FY reading, which
is what the code follows. It is not an off-by-one-year bug.


---

## Verification and gates

### nt_verify passes a cell on quote-mid valuation only if it reproduces every rebalance

`nautilus/nt_verify.py` passes a 0.01-grid difference beyond the one-share signature
only if the reference valued at the port's quote mid (`mid_valued`) reproduces the
port's holdings, names and share counts, on every rebalance. All 32 cells verify
(`diagnostics/nt_verify_all_arms_20260929.txt`): 20 by the one-share signature and 12
by this rule, none of those 12 with a different set of names. check_all gates all 32.
`experiments/CLEANED_NOISE_PREREG.txt`'s report keeps the labels fixed at registration,
so eight supported cells still read "not port-verified" in `diagnostics/cleaned_noise.txt`.

### Gates loosened or failing after the cleaning, accepted by the owner 2026-09-27

- `verify_v34_arms.ONE_SHARE_TOLERATED` (verify_v34_arms.py:107) lets midcap150 v1, v2
  and v3 pass when every divergence is exactly one share. These cells stand at 89, 90
  and 88 of 92 rebalances, from quote-mid rounding. The list is closed. The record
  `diagnostics/verify_v34_arms.txt` predates the cleaning and still shows 92 of 92.
- validate_engine fails 4 of 8 (T1 and T3 on both certified universes).
  validate_breadth_live fails T2 on nifty100. validate_sizing fails 2 of 4 on each, but
  its records date from 2026-09-20. All three are `--slow`, so they do not gate commits.
  No thresholds were changed.
- TOP_N trial (`diagnostics/topn_verdict.txt`): the incumbent TOP_N=8 is contradicted on
  both certified universes. Nothing in config changed, and TOP_N=12 is not promoted.

### Which checks cover which arm

All four arms, all eight universes:
- GATE 9 (`check_b_exec_timing`, leakage checks 1 and 2), GATE 6 and GATE 7 tax.
- `tax_report.py`, `bh_lots_after_tax.py`, `cost_reconcile_check.py`.
- `nautilus/nt_verify.py`: 32 of 32 gated.
- The cleaned after-tax noise test (`results/noise_parallel.py`).

All four arms, nifty100 and midcap150 only: `verify_v34_arms.py`, with the one-share
tolerance for midcap150 v1 to v3.

Not extended beyond v2 (or v1 against v2), because each would be a new test needing its
own spec:
- `validate_engine`, `validate_sizing`: inverse-vol against equal weight at 100%.
- `validate_breadth_live`: `experiments/BREADTH_LIVE_SPEC.txt`.
- `validate_topn`: `experiments/TOPN_SPEC.txt`.
- `results/price_noise_measure.py`, jackknife, pinned mask, drawdown exit, shuffle,
  seed noise.

Decision, owner, 2026-09-29: the gates stay as they are. The correctness gates
(nt_verify, the cost reconciliation, execution timing, GATE 6 to 8) cover all four
arms on all eight universes. The validation tests compare one rule against another
(inverse-vol against equal weight, breadth against full exposure, v1 against v2) and
are pairwise by design, so they are not extended to v3 and v4.

### Validation of sizing and breadth, as of 2026-09-27

Three suites, run as slow `check_all.py` delegates on nifty100 and midcap150 only
(`registry.CERTIFIED`):
- `results/validate_engine.py`: the four inverse-vol tests against the shipping
  engine. FAIL, 2 of 4 on each universe; T1 (mean book below `TOP_N`, see the
  cash-funding entry) and T3 (sub-period) fail
  (`diagnostics/validate_engine_verdict.txt`).
- `results/validate_breadth_live.py`: the breadth rule on the shipping engine.
  midcap150 PASS; nifty100 FAIL on T2 sub-period stability. T3, the
  constant-exposure control, is reported and ungated by design.
- `validate_sizing.py`: the same four tests on `engine_core.backtest`, which is not
  the engine that ships. Its verdicts say nothing direct about published figures.

The owner ruled on 2026-09-27 to record these failures and change no thresholds.
No suite has been run on the other six universes.

### validate_engine: 2 of 4 on both certified universes, cleaned prices, 2026-09-27

`results/validate_engine.py` runs T1-T4 against the shipping engine (`test_exposure.backtest_exposure`), inverse-vol against equal-rupee at 100% invested. Record: `diagnostics/validate_engine_{midcap150,nifty100,verdict}.txt`.
- T2 (seed sets) and T4 (vol window) pass on both. The smallest margins are +0.0205 (midcap150 T2) and +0.0076 Sharpe (nifty100 T4, vol_win=40).
- T3 fails on both. Inverse-vol loses 2019-2022 (-0.2038 midcap150, -0.0776 nifty100) and wins 2023-2026.
- T1 fails on both because the mean book is 7.91 and 7.88, below TOP_N=8. The cause is cash-short skipped buys; see the funding-gap entry.
- No noise band was applied. Any band has to be pre-registered against a measured seed floor before the tests are read again.
- The tests gate Sharpe only. Inverse-vol's MaxDD is shallower than equal-rupee's on every T2 seed set, and no drawdown test exists.
- "CAGR moves +/-0.5% per refit" (line 215) is an unmeasured number that is still printed.

### validate_engine and validate_sizing answer T3 with different engines

`results/validate_engine.py` decides its sub-period test (T3, inverse-vol against
equal-rupee) on `test_exposure.backtest_exposure`, the engine that produces the
published figures. `validate_sizing.py` decides the same test on
`engine_core.backtest`, which has a slot cap and no exposure mode. On 2026-09-22 they
disagreed in sign on both halves of nifty100 and by a factor of four on midcap150's
late half. Neither engine was shown to be wrong. validate_sizing's records date from
2026-09-20 and have not been re-run on the current numerics or cleaned prices. Quote a
T3 result only with its engine named. A sign-agreement gate would be a new
pre-registered test and was not added. See "Three backtest implementations and one port".

### registry.CERTIFIED still names two universes -- DEFERRED

`universes/registry.CERTIFIED` is `("nifty100", "midcap150")`. These checks have never
run on the other six: `verify_v34_arms.py`, `validate_sizing.py`,
`results/validate_breadth_live.py`, `results/validate_engine.py`,
`results/validate_topn.py`, `results/shuffle_test.py` and the combined pair chart. The
refit validations cost about 22 minutes per universe each. nt_verify and GATE 9 already
cover all eight. So "certified" means "covered by the refit validations", not "the only
universes that verify". The owner deferred widening it on 2026-09-25.

### Leakage check 3 (normalisation scope) has no script, and two documents cite its output

`experiments/LEAKAGE_SPEC.txt:140` specifies CHECK 3: list every scaling, rank or standardisation between the raw CSV and the model input, with its scope. Line 254 names the output `diagnostics/leakage_check3_normalisation.txt`. No script implements it and the file has never existed. It is still cited as evidence in the leakage table of this file and in `experiments/EXPERIMENTS.md:3866,3925`. Those citations point at nothing. Row 4's primary evidence, `leakage_check1_causality.txt`, does exist.

Checks 1, 2 and 4 are wired into `check_all.py`, but none of them would catch a scaler fitted over the whole panel. Their passing results say nothing about normalisation scope.

### `results/leakage_check2_purge.py` is retired; the live purge rule is tested by the trading-day check

`leakage_check2_purge.py` builds the training cut by calendar days. The engine uses `purge_mode="trading"` (`engine_core.score_monthly`), so this script audits a path production does not take. It stays in the tree as the record of the calendar rule, and `check_all.py` lists it under `RETIRED_DELEGATES`. Do not wire it.

The live rule is checked by `results/leakage_check2_trading_purge.py`, which is wired and passing. It calls `score_monthly` itself and finds a gap of exactly `PURGE_EMBARGO` = 2 trading days in every month (`diagnostics/leakage_check2_trading_purge.txt`). The sentence in `diagnostics/gate_verdicts.txt:80` saying no script tests the live purge rule is out of date.

### The port is certified at cadence 20 only

nt_verify's gate runs at cadence 20. `nautilus/nt_verify.py --universe=<u> --rebal=<n>`
prints the port against the vectorised engine at another cadence and always exits 0.
No tolerance has been argued for, so it is not gated. The last measurement, on
2026-09-23 under nautilus_trader 1.229.0 with nifty100 v2, was identical to the paisa at
cadences 20, 3 and 1. That was before the 2026-09-24 numerics change and the cleaning,
and it has not been repeated. The drift recorded under 1.221 came from that version's
fill matching.

### Nautilus reports are not byte-reproducible

`event_id`, `position_id` and `init_id` in the Nautilus report CSVs are random UUIDs
and change between two runs in the same venv. To compare two runs, drop those three
columns and sort the rows. Every other column must match. nautilus_trader is pinned at
1.229.0. Versions before 1.223 stamped most fills 15:30 instead of 09:16, with the same
prices, so a report from an unpinned venv can look like a close fill when it is not.

### The Nautilus port skips a rebalance the engine would make when no symbol has momentum

nautilus/nt_strategy.py:548 returns from rebalance() when no symbol has 20-day
momentum data. Under mode="none" (arms v1 and v3) the research engine never reads
momentum, so on such a date it would trade and the port would not. With
WARMUP_DAYS = 200 (nautilus/nt_run.py:70) the case does not arise in the current
window. The guard is left as it is because changing it changes when the port
rebalances. If nt_verify ever fails on a v1 or v3 cell at the first rebalance after
a data gap, look here first.

### Cross-platform identity is proven on one universe

pandas grouped and rolling variance, and its default CSV float parser, gave different
bits on macOS and Linux. The pipeline uses numpy replacements (`results/numerics.py`)
and reads every CSV through `config.read_table` (`float_precision="round_trip"`).
`platform_identity_check.py` (GATE 5) fails on any direct `pd.read_csv` or pandas
rolling or grouped variance in a tracked file. On 2026-09-24, midcap50 v2 built on macOS
arm64, linux/arm64 and linux/amd64 (the amd64 one under Rosetta) gave byte-identical
panels and CSVs. The other seven universes have not been rebuilt off the Mac.

### platform_identity_check needs a git checkout or a tracked-file manifest

`platform_identity_check.py` lists the tracked `.py` files with `git ls-files`. Outside
a checkout it falls back to `TRACKED_FILES_SHA256.txt` ("<sha256>  <path>" per line),
whose listed files must still match; with neither it exits 3, which check_all reports
as a named skip. No such manifest is in the tree yet, so a copy without `.git` skips
this check.

### Documented commands are checked by hand, not by any gate

The README "How to run" commands (`check_data.py`, venv build, `./venv/bin/python run.py ...`) were run in a fresh copy with a fresh venv on 2026-09-29, and five combinations reproduced byte for byte. `check_all.py` GATE 1 imports every module under the interpreter it runs in, so a missing package fails it by name. Nothing runs the commands the documentation gives. Module docstrings still say `python3 <script>` in about 30 places (e.g. `validate_sizing.py:71`, `gate_compare.py:29`). On the owner's machine `python3` is 3.11 without lightgbm, and every child step inherits the launching interpreter (`sys.executable`). Only `check_data.py` works under plain `python3`, because it uses the standard library alone. Use `./venv/bin/python` for everything else.

### Run the gates after `git add`, and quote that run

naming_declare_check.py and check_all.py scan the working tree, untracked files
included. A figure taken before the change is staged describes a tree the commit
does not contain, and it always shows no change, so it reads as proof exactly when
it proves nothing. Run check_all.py after `git add` and before `git commit`, and
quote the numbers from that run. There is no hook enforcing this.

### A check has to test the code that shipped, and these guards exist because some did not

In September 2026 several changes were declared safe on evidence about something else. Examples: a gate that counted untouched baseline files as matches, a merged module gated on cached panels so none of it ran, and an audit that replayed the uncapped strategy against the capped curve. The guards added in response are load-bearing:
- `gate_compare.py` compares only files the cell under test wrote, and fails on any file it cannot account for;
- `registry_coverage_check.py`, called from `run.py` preflight, fails if a registered universe is missing from any of the seven per-universe tables;
- `backtest_exposure` refuses a participation cap passed without `vol20`;
- scripts outside the profile axis call `profiles.research_only`, which refuses a non-research profile.

Nothing checks that a commit message's "not exercised" or "verified" claim matches what ran. When a commit says a branch was not exercised, run that path yourself before accepting it.

### Rule: a claim over universes, arms or cells carries its n and its date

A correct measurement over the cases in hand, written as "every universe" or "no sign changes", reads as a property of the mechanism. It breaks as soon as the set grows. Three such claims broke within two days in September 2026. One of them already carried its count ("across the three universes") and was still wrong, so a grep for quantifiers without an n finds some instances and misses others. Write "on the eight universes, cleaned prices, 2026-09-27", not "on every universe". The set can still grow along other axes, such as arms, profiles or cadences, even though no ninth universe exists.


---

## Data, calendar and cleaning

### Prices are cleaned at the load boundary; the rule is not causal

`experiments/DATA_CLEANING_SPEC.txt`, implemented in `results/ratio_clean.py` and called
from `engine_core.build_panel` just before `canonical_price`. The rule: an adj_close/close
ratio move that comes back within 0.1% within five sessions takes the previous ratio for
the whole event. It touches 0.39% to 0.54% of rows in the window. The raw files are
unchanged. `results/ratio_clean_check.py` (check_all) fails if a reverting event is left
in the window.
- Whether a session is cleaned depends on up to five later sessions. It is a data repair
  and a live book cannot compute it on the day.
- `results/leakage_check4_corpactions.py` reads the raw files and neither checks the
  cleaning nor is affected by it.

### The price data is not in the repository and can only come from the owner

The pipeline reads `data/raw/Final_Without_Survivorship_Data/`, eight folders and 1,392 CSVs, which is untracked vendor OHLCV. A clone cannot run without a copy from the owner. `check_data.py` compares a copy against the tracked `data/RAW_DATA_SHA256.txt` and fails on any missing, changed or extra file. The files carry vendor columns (`source`, `_window*`, `_dq_score`, `_gap_filled`, `_merged_at`) that show a private merged extract, and no document describes those columns. There is no licence and no fetch script. If the owner's copy is lost, it cannot be rebuilt from this repository.

`survivorship_attribution.py` also reads `data/raw/Survivorship_Bias/*_membership.csv` and the price files of `Final_With_Survivorship_Data/`. Neither is in the checksum manifest.

### The NSE trading calendar is frozen data with no generator and no way to extend it

`data/nse_trading_calendar.csv` is tracked and filters every panel (`results/engine_core._load_calendar`, `_check_calendar`). It was built once from a retired universe's raw files by `results/make_trading_calendar.py`. Both the script and the files were deleted in 2fe48ff. The calendar ends on 2026-06-08, and nothing in the repository appends to it. Any data past that date needs a new source of sessions, and that source has not been chosen. Do not hand-edit it: a wrong tail changes every backtest window.

Deriving the calendar from a live universe does not reproduce it. The live panels carry 237 dates that are absent from the calendar, 107 of them inside the backtest window. A coverage threshold cannot separate them either: over the full range no threshold reproduces the calendar on nifty100 or midcap150 (`experiments/CALENDAR_DECOUPLE_SPEC.txt`, marked BLOCKED; `diagnostics/calendar_coverage_probe.txt`). No external NSE holiday list has been checked against the calendar.

### The calendar density guard compares against the per-year median, which is weaker than the old rule

`results/engine_core._check_calendar` refuses to drop a date that the calendar marks as a holiday if that date carries as many symbols as the median day of its own year. Until 2026-09-19 it compared against the median over 2000-2026. That was loosened for smallcap250: most of its names did not exist for most of those years, so 23 phantom holidays cleared the long-run median and aborted the run.

The per-year rule flags a subset of what the old rule flagged. Measured on seven universes (not nifty500), 2026-09-19: the change passed exactly those 23 smallcap250 dates and nothing else. The highest ratio of a phantom date to its year's median was 0.60 (smallcap250, 2025-12-25), against a threshold of 1.00. None of the 237 phantom dates is in the NSE calendar. nifty500 has not been measured.

### The vendor's `_gap_filled` and `_dq_score` columns are not read

Every supplier price file carries `_gap_filled` (the vendor synthesised the row) and
`_dq_score` (an undocumented quality score, 0.62 to 1.00). No engine, panel or
participation-cap code reads either.

- Synthetic rows are flat bars with made-up volume. Inside the window almost all
  fall on non-trading days, and the panel is built over the NSE calendar, so they
  are never traded. That is the only protection. A different calendar or a vendor
  extract whose synthetic rows land on trading days would feed their volume
  straight into `tradability.median_volume`, the cap's denominator.
- 17% to 28% of in-window trading-day rows score below 0.9, on large liquid names
  as well as small ones. Nothing is filtered, because the scale is undocumented.

### Neither buy & hold passes through the tradability guard

The reference buy & hold (`px.pct_change().mean(axis=1)`, results/v34_common.py:256)
and the investable held-lots buy & hold (results/bh_held.py) are built from the
forward-filled price panel without consulting results/tradability.py. The guard
gates the strategy's trades only.

On the current data this changes nothing: tradability.gaps() finds no interior gap
in any universe inside the window. It would matter after a data refresh that
brings back a price hole, because a multi-year hole enters both benchmarks as one
large daily return. tradability.gaps() also trims rows to the window before
pairing them, so a hole that starts before 2019-01-01 is not reported at all.

### The farm's copy fallback trusts size and modification time

Where `Universe.prepare_data_dir` cannot hard-link a raw file, it copies it with
`shutil.copy2` and recopies only when size or mtime differ
(universes/registry.py:515-543). An in-place edit of a raw file that keeps both would
leave a stale copy in the farm. `config.data_fingerprint` reports such a copy as coming
from `raw_data_dir` (config.py:549). Hard links, the normal case, cannot go stale.

### Artefacts computed on uncleaned prices sit beside current ones, and GATE 8 passes them

The published figures are the 2026-09-27 republish on cleaned prices. Many older
outputs remain in results_*/metrics/: 51 of 88 v34_params*.json files, and 457
files in all, predate 2026-09-27 (arm subsets, other cadences, tradeable runs).
Their data_source digest matches the current one, because the cleaning happens at
load and the raw files did not change, so GATE 8 cannot tell them apart. Check
run_date in the params file before quoting any figure. diagnostics/ has the same
problem: SUPERSEDED_20260927.txt names ten files, 35 pre-repoint files carry a
"PRE-REPOINT DIAGNOSTIC" header, and seed_noise.txt, drawdown_exit.txt,
purge_fix_measure.txt, rebal_cadence_sweep.txt, shuffle_*.txt and
topn_{mid,n100,verdict}.txt are pre-repoint and carry no marking.

### Most files in diagnostics/ describe panels that no longer exist

`diagnostics/` is a mix of current outputs and dated records, and nothing marks
which is which. Files rewritten by `check_all.py` delegates (for example
`topn_verdict.txt`, `validate_engine_verdict.txt`, `breadth_live_<universe>.txt`)
describe today's panels. Most others were computed before the 2026-09-24
numerics change or the 2026-09-27 cleaning, and those with old tags in their names
(`*_n100.txt`, `*_mid.txt`, `*_58.txt`, `seed_noise.txt`, `shuffle_*.txt`) are on
data the repository no longer uses.

Several of these files print the sha256 of the panel they were computed from, but
nothing compares it with the current panel. Before quoting a figure from
`diagnostics/`, check its date against the 2026-09-27 republish or re-run its
script.

### results/price_noise_measure.py measures v2 only, and cleans after perturbing

`run_arm(u, data_dir)` takes no arm and backtests `arm_reg.ARMS["v2"]`
(results/price_noise_measure.py:326, :351), and the draws file has no arm column.
The module perturbs the raw farm and then builds the panel with the default
`clean=True` (:328). The cleaning therefore removes part of the perturbation, the order
the owner ruled out on 2026-09-27. `results/after_tax_noise.py` shares this path. The
current noise measurement is `results/noise_parallel.py`, which cleans first and runs
all four arms. Treat `diagnostics/price_noise.txt` (2026-09-24, uncleaned, v2 only) as
superseded, and do not re-run either module expecting the current method.


---

## Code and maintenance

### Three backtest implementations and one port, and which one each check tests

- `results/test_exposure.backtest_exposure` is the shipping engine. It produces every published figure, and `validate_engine.py`, `audit_step.py`, `tax_report.py` and the sweeps all run it.
- `results/engine_core.backtest` has no breadth mode and sizes against cash rather than portfolio value. Only `validate_sizing.py` uses it. validate_sizing's verdicts describe this engine, not what ships.
- `nautilus/nt_attribution.run` is a deliberate independent copy, used as nt_verify's reference.
- `nautilus/nt_strategy.py` is the Nautilus port that nt_verify tests.

`results/drawdown_exit_measure.py` also execs a patched copy of `backtest_exposure`'s source, and refuses if the patch point has changed. `TOP_N` and `BUFFER` are centralised in config. Rule changes are not: a change to one engine's rules has to be made in each of the others. When two of them disagree, as they do on the T3 sub-period sign (see "validate_engine and validate_sizing answer T3 with different engines"), do not assume the shipping engine is the one that is right.

### VOL_WIN = 60 is defined in 20 files and nothing checks they agree

The 60-day volatility lookback sets inverse-vol position sizes and the portfolio
volatility used by the shipping engine. `config.py` does not define it. Twenty
tracked files each assign their own `VOL_WIN = 60`, including the shipping engine
(`results/test_exposure.py`, `results/engine_v2_final.py`), the Nautilus port
(`nautilus/nt_strategy.py`, `nautilus/nt_attribution.py`) and the noise harnesses
(`results/noise_parallel.py`, `results/after_tax_noise.py`). Only
`results/validate_breadth_live.py` imports it from `engine_core`.

Every copy reads 60 today. If one changed, sizing would change in that script
alone, and the first sign would be a reconciliation failure elsewhere (nt_verify,
the cost reconciliation), not an error at the edit. Centralising it needs the same
byte-identity proof `TOP_N` and `BUFFER` got (`topn_centralise_check.py`); it has
not been done. `grep -n "VOL_WIN *=" $(git ls-files '*.py')` gives the current
list.

### Which axes an artefact's name carries is written in two places, and nothing compares them

An artefact name is a stem plus up to four axis suffixes: arm, cadence, profile, tax. Each is empty at its default. The axes an artefact actually carries are stated twice:
- at the writer, by a `# naming:` directive, which `naming_declare_check.py` checks against a non-default selection;
- at the reader, by the compulsory fourth field of each `run_all.REQUIRED_INPUTS` entry, which `check_inputs._present()` composes.

No check compares the two, so they can drift apart, and `_present`'s docstring still describes itself as a stopgap. `naming.py` builds directory tails (`path_tail`) and chart titles (`run_label`). File names are still assembled by hand in `results/audit_step.py:106,169` (`artefact_tag`), `results/v34_common.py:319` and `results/engine_v2_final.py:115`. The next step is to have `naming_declare_check` cross-check each `REQUIRED_INPUTS` axis field against the producing writer's directive.

### Artefact names are composed by hand, and only the writers are checked

Four axes name an artefact (naming.AXES: arm, cadence, profile, tax). naming.tail()
composes them, but about eight sites still build the suffix by hand, among them
results/arm_sources.py:57, audit_step.py:169, make_chart.py:168 and
make_combined_universes.py:422. naming_declare_check.py and naming.CARRIES verify
that writers carry the axes they declare. Readers are not checked. A reader that
misses an axis resolves to the default file, and when the check it feeds re-ran
under the same default it reports a match that could not have failed; this
happened with the tax axis in audit_step.py. Adding an axis (a survivorship axis
is planned, after tax) means editing every one of these sites.

### check_pipeline_order resolves edges per script, not per universe

check_pipeline_order.py records each script's reads and writes once, however many
universes its steps run for, so a line in its output means "some step running
this script touches this file for some universe", not "this step produces it for
this universe". registry_coverage_check.py is what checks that every universe is
wired.

Since 2026-09-24 a path built inside a loop over `REGISTRY[tag].metrics_dir`
(make_combined_universes.py) is expanded over every universe in the row's declared
span. A file the loop writes for only some universes, behind an `if`, would be
credited to all of them, and no check would notice.

### run_all.PIPELINE_ORDER is written out by hand -- DEFERRED

`run_all.PIPELINE_ORDER` lists 52 rows, one per (step, universe) (`PIPELINE_ROW_COUNT`,
run_all.py:291). Adding a universe means adding six rows with new labels, so a universe
is not yet just a registry row. The labels are keys: GATE 2, check_pipeline_order,
check_plan_order and the run logs name steps by them. Generating the rows would renumber
every step, including the irregular `10za` and `10.01`, and every reader would have to
move in one change. The owner deferred this on 2026-09-25.

### `Universe.year_range` is read on every panel build and set by no universe

`universes/registry.Universe.window()` cuts by `year_range` if it is set and by `date_range` otherwise. Every universe passes `year_range=None`, so every run takes the date cut (`config.BT_START_DATE` to `BT_END_DATE`). That result is correct, but it is a default no universe chooses. The year branch is unreachable, and it would run six sessions past `BT_END_DATE`, to the end of the price data. It was left in place when the retired universes that used it were deleted on 2026-09-11. Remove the field and the branch, or make the date range the only window.

### --arm narrows the v34 files and per-arm outputs, not v2FINAL_*

`results/engine_v2_final.py` always backtests v1 and v2 and writes
`v2FINAL_comparison.csv`, `v2FINAL_yearly.csv`, `v2FINAL_equity.csv`
(columns `v1_invvol_none`, `v2_invvol_breadth`, `buyhold`), `v2FINAL_params.json`
and `chart_v2FINAL.png` on every run, whatever `--arm` selects. So `--arm v3`
still produces v1 and v2 figures in those files, and a run of v5 or v6 alone
rewrites all five. Only the v1 trade log, `daily_trades_v1_<tag>.csv`, checks the
selection. The `buyhold` column there is the daily-rebalanced reference basket,
not the investable buy & hold.

v1 and v2 are computed regardless because later steps need them: `run_v34` takes
their curves to build every other arm's table, `make_chart.py` and
`make_combined_universes.py` read `v2FINAL_equity` and `v2FINAL_params`, and
`audit_step.py` reads `v2FINAL_equity`. The rewrite does not change the numbers.
On 2026-10-03 the v5/v6 runs over all eight universes and four settings left every
`v2FINAL_equity` file byte-identical, and the two `v2FINAL_params` files that
changed carried the same Sharpe, MaxDD and CAGR as the published v2 rows. The 21
charts that changed could not be compared with their previous versions, which were
not kept. None of these files is tracked by git (`results_*/metrics/` is ignored),
so the rewrite shows in no diff. `arms/registry.py` records the same gap: making
`v2FINAL_*` arm-aware means restructuring it into per-arm columns and
re-baselining the identity gates. Not fixed.

Everything else follows the selection. `v34_comparison`, `v34_equity`,
`v34_params` and `chart_v34` take a selection suffix (`_v3`, `_v1_v3`) and a
subset never overwrites the canonical four-arm file, which the identity gates
read. Audit trails, daily logs and trade logs are written per selected arm.

### Guards and authorities that are declared but not called, and the one still standing

A function whose docstring says what it guards against, but which has no call site, reads as a solved problem to anyone who finds the docstring. This happened with `tax.set_selection` and `tax_util.max_holding_days`, and both are now wired.

Still open: `results/make_chart.py`, the per-universe chart, ignores the registry palette. Lines 290, 292, 308, 445 and 446 hardcode six colours, nifty100's slots 0-3 and midcap150's slots 4-5, and every universe is drawn in them. `palette_distance.py` measures only `REGISTRY[t].chart_colours`, so this set has never been gated. Its closest pair under deuteranopia is v2 against buy & hold at dE 7.55. Fixing it re-renders every universe's chart.

No check finds a new case. The detector would grep every `def` whose docstring contains a guard verb for call sites outside its own definition, and flag growth against a declared baseline in the way `naming_declare_check` does. It has not been written.

### The drawdown-panel label is copied into seven registry rows

universes/registry.py carries `chart_text["dd_label"]` on every row. Seven rows hold
the same lambda text; midcap150's (line 727) is different. results/make_chart.py:459
draws it on the drawdown panel of every per-universe chart. The copies are
deliberate, because the registry keeps each universe to one self-contained row,
but an edit to one row will not reach the others and nothing compares them. Lambda
objects never compare equal, so a comparison has to render each label on a sample
input.

### Two line pairs on the combined chart look identical under deuteranopia

On the combined chart, midcap150 v2 (#e377c2) vs v1 (#17becf) and nifty100 v1
(#2e6da4) vs v3 (#7f3f98) are dE2000 4.24 and 3.26 apart under deuteranopia, and
both pairs are solid lines of the same universe (diagnostics/palette_distance.txt).
In normal vision no pair is closer than about 11.7. The palettes are left alone
because changing them re-renders published charts. No gate checks palettes;
palette_distance.py reports only, and a gate was declined because it would fail
on these pairs the day it landed. New palettes cannot all clear dE 10: the measured
ceiling is 8.712634 (diagnostics/palette_ceiling.txt). Per-universe charts do not
read chart_colours at all (results/make_chart.py hardcodes six colours).

### Combined charts may not be byte-reproducible across sessions

`results/make_combined_universes.py` saves with `bbox_inches="tight"`. On
2026-09-04 the tight bounding box of the nifty100/midcap150 pair chart came out
two pixels taller in one session than another, on identical code and inputs. The
cause was not found and nothing has re-tested it. The plotted numbers do not
change. Do not use a `chart_COMBINED_*.png` as a byte-comparison fixture.

### make_chart prints no independent check of the index return

results/make_chart.py used to print a hardcoded `expected` index return beneath
the measured one. It held midcap150's figures, was printed for every universe, and
was wrong for all of them after a window change. It was deleted (comment at
make_chart.py:248). Do not bring it back computed from the same price slice: that
line would agree by construction and could never fail. The only check worth
printing is the index provider's own published return for the window, per
universe, and the repository does not have it.

### Documents cite code by line number, and the numbers go stale silently

`KNOWN_ISSUES.md`, `experiments/HANDOFF_SUMMARY.txt`, code comments and
docstrings cite code as `file.py:NNN`. Any insertion above the cited line, even a
comment, moves the target, and a stale reference fails silently: it points at a
different plausible line. Example: a record cited `test_exposure.py:625` for the rebalance guard
`i < len(dates) - 1`, which is now at line 645.

Before inserting lines into a file, grep for `<file>.py:` references into it.
Citing by symbol name (`test_exposure.backtest_exposure`, the `invest_val`
assignment) does not have this failure. Pre-registrations under `experiments/`
keep their original line numbers on purpose: they record what was true when they
were written.

### A file that nothing imports or runs is not necessarily dead

Many scripts here are not in `run_all.PIPELINE_ORDER` and are imported by nothing,
but produce a diagnostic that `EXPERIMENTS.md`, a spec or this file cites as
evidence. Deleting one leaves the cited `.txt` with no way to regenerate it. Some
write only to stdout (`verify_v34_arms.py` has no file write at all; its record
was made by redirection), so a scan for writes finds nothing either.

A file is dead only if all four hold: it is not in `PIPELINE_ORDER` or
`check_all.DELEGATES`; no `.py` imports it; its name, stem or a glob matching it
appears in no tracked `.md`, `.txt` or `.json`; and nothing it writes, including by
redirection, is cited anywhere. Exclude `diagnostics/INVENTORY.csv` from the name
search: it lists every file in the repository and makes everything look
referenced.

### Searching for a file's basename does not show whether it is referenced

This repository cites files by stem and by glob (`diagnostics/nt_verify_*.txt` in
nautilus/NAUTILUS_STATUS.md, `validate_engine_` in prose), so `grep -F <basename>`
misses real references. Before calling a file unreferenced or deleting it, search
for its stem and for globs that would match it, across every tracked file plus
diagnostics/, docs/ and experiments/. Do not reuse an exclusion list from an
earlier search: a directory skipped for one question may hold the answer to the
next.

### Files with retired tags are old records, not duplicates

Some files still carry the retired tags: runs/mid/, runs/n100/, runs/n50/,
diagnostics/shuffle_{mid,n100}.txt, topn_{mid,n100}.txt, breadth_live_{mid,n100}.txt,
n100_jackknife.txt and pre_repoint_baseline/metrics_{mid,n100}/. They are records
written before the 2026-09-18 rename and repoint; `mid` means midcap150, `n100`
nifty100 and `n50` nifty50 (README, NAMING). Their current-name siblings, where
present, were produced later on different data. Do not rename them, and read "An
old-looking name is not evidence of an old-named duplicate" in PANEL_MIGRATION.md
before deleting any. In older prose, names such as make_mid_chart.py refer to
scripts that were merged, not renamed; no file of the new-tag spelling ever existed.

### Old names and an old window left in place on purpose

- `topn_test.py` cuts the window with engine_core's integer years (`BT_START`,
  `BT_END`, topn_test.py:97), so it runs to 2026-06-08 (1,842 sessions) instead of the
  pipeline's 2026-05-29 (1,836). It carries a pre-registered accept rule, so changing
  what it measures is the owner's decision. jackknife had the same defect and was fixed.
- Comments and docstrings still name deleted files where they describe what that file
  did (`engine_v2_final_mid.py`, `make_n100_chart.py`, ...). None of these can be run.
- Tracked diagnostics written before 2026-09-24 keep the old tags (`*_n100.txt`,
  `*_mid.txt`) and were not regenerated.
- Per-universe measured constants (seed-noise floors, tradability counts, purge months,
  price-noise sigma) are declared per universe through `measured_universes.py`, because
  they are results.

### Small limits from the 2026-09-23 audit

- `runs/mid`, `runs/n100` and `runs/n50` (old tags) predate the `profile` and `tax`
  keys in params.json. Any of them may hold a taxed or tradeable run, and the file
  cannot say which. Run folders from before 2026-09-23 are frozen at whatever the last
  run of their selection wrote, not at their own run. Nothing reads either.
- `heldout_prereg_run.py` does not support `--profile tradeable`. It passes the cap
  without `vol20` and backtest_exposure raises TypeError.
- requirements.txt pins direct dependencies only. Install with
  `-c installed_versions.txt` to reproduce the venv exactly.

### Two merged pull request refs on GitHub still hold the old history

On 2026-09-29 the history was rewritten to remove a non-English comment and one other
line, and to translate a non-English passage in `experiments/rejected_experiments_REPORT.txt`
and its quote in `experiments/EXPERIMENTS.md` into English; `main`, `v1.0` and `v1.1`
were force-pushed. GitHub keeps a read-only ref for each merged pull request,
`refs/pull/1/head` (b417907) and `refs/pull/2/head` (ee06823). They point at commits
from before the rewrite and still hold the old wording. A push cannot delete them;
only GitHub support can. The owner accepted leaving them. `main` and both tags on
GitHub, and every object in the local repository, are clean. The pre-rewrite history
is kept outside the repository, in a git bundle the owner holds.

### Small stale comments and one leaking check

- `tax_acceptance_check.py` creates two temporary directories per run
  (`tempfile.mkdtemp`, lines 81 and 130) and never removes them.
- `paths.py:39` still calls the score panel a `.csv`; `config.read_table`'s docstring
  names `csv_reader_check.py`, which no longer exists; `results/engine_v2_final.py:180`
  and `:261` and `results/arm_sources.py:5` name the deleted `make_final_chart_fair.py`;
  `results/validate_engine.py:57` and `:380` mention `FINAL_val_*.csv`.
- `diagnostics/gate_verdicts.txt:80` says the live purge rule is tested by no script;
  `results/leakage_check2_trading_purge.py` tests it.


---

## Out of scope

### Live orders are outside this repository's scope

Producing orders for the open of D+1 from data ending on D is being built elsewhere.
What this code does and does not do, recorded for whoever builds it:
- It scores every name on the last day of its data, but never makes a decision on the
  window's last day (`test_exposure.backtest_exposure`, the rebalance guard
  `i < len(dates) - 1`), and sizes buys from the execution day's open.
- Rebalance days are counted from 2019-01-01, so an arbitrary D is usually not one.
- The book always starts as a simulated Rs 10,00,000 in 2019; there is no input for real
  holdings, cash or tax lots, and nothing writes a "trade next" file.
- The trading calendar and data stop at 2026-06-08, and new data forces a full score
  rebuild because the cache key covers every source byte.
- What it would take: a data and calendar append path; an end-date override; a "decide
  on D" mode that emits the target; seeding from real holdings, cash and lots; an order
  writer with the participation cap from volume through D; pre-trade checks (corporate
  actions on D+1, current membership, T+1 cash); a broker link.
