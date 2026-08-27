# Nautilus port — current state and what to do next

Read this before touching anything under `nautilus/`.

## What this project is

`results/` holds the **reference engine**: a cross-sectional LightGBM ranking
system for Indian equities. It is finished, validated and reproducible. Its
official numbers are CAGR 13.16%, Sharpe 1.11, MaxDD −18.22%, final equity
Rs 25,09,835 from Rs 10,00,000 over 2019–2026, on a 58-stock universe.

> **These numbers changed on 2026-08-13.** Everything previously reported
> (CAGR 16.45%, Sharpe 1.36, MaxDD −17.09%, final equity Rs 31,01,677) was
> measured on a panel degraded by a feature-density bug: `beta_60` and
> `idio_vol_60` were computed with `rolling(60)` over the UNION date index, so a
> symbol that did not trade on a union date lost its next 60 windows, and every
> affected row was then dropped by `dropna(subset=FEATS_V2)`. The bug acted as a
> filter that happened to select favourable rows. Fixing it moved all three
> universes:
>
> | universe | CAGR | Sharpe |
> |---|---|---|
> | 58  | 16.45% → **13.16%** (−3.29) | 1.36 → **1.11** (−0.25) |
> | 74  | 14.65% → **15.22%** (+0.57) | 1.27 → **1.35** (+0.08) |
> | mid | 9.06% → **27.34%** (+18.28) | 1.63 → **1.70** (+0.07) |
>
> The fix was verified not to alter any value it should not: where both old and
> new are defined the max absolute difference is 5.2e-13 (`beta_60`) and 3.3e-15
> (`idio_vol_60`), with zero rows lost, and a truncation causality test returns
> exactly 0.000e+00. The movement comes entirely from 68,260 rows that now clear
> `dropna` and enter training — a larger training set, not changed values.
>
> Read plainly: at 13.16% the 58 strategy is 2.2 points ahead of NIFTY100
> (10.93%) and **5.5 points behind an equal-weight buy&hold of its own universe**
> (18.65%).

`nautilus/` holds a **port of the execution layer only** into NautilusTrader
1.228. No model is trained inside Nautilus. The research pipeline runs offline
exactly as before and exports `date | symbol | score` to
`nautilus/data/scores_58.parquet`. That parquet is the only channel between
research and execution.

The goal of the port is **not** better performance. It is to run the same
strategy inside an event-driven framework whose code path could later run live.
Success means the port reproduces the reference engine, or that every difference
has a measured explanation.

## Current state: VERIFIED

```
python3 nautilus/nt_verify.py
```

is the single measure of progress. As of the last run:

```
final equity   reference Rs 3,237,591
               port      Rs 3,236,727   (-0.03%)
rebalances     reference 93   port 93
fills          reference 929  port 929

vs REFERENCE (valued at the execution day's close)
  identical holdings      : 5 of 93
  differing by symbol set : 0
  differing by quantity   : 88     median 0.40%  max 7.14%

vs ARM D     (same engine, valued at the open, 0.05 ticks)
  identical holdings      : 93 of 93
  differing by symbol set : 0
  differing by quantity   : 0

control: ARM A vs the reference's own holdings   93 of 93 identical
reconciliation on a 0.01 tick grid (both sides)  93 of 93 identical
```

**On a 0.01 tick grid the port and the open-valued reference agree on every
holding at every rebalance.** The two systems are identical in logic. Everything
that differs at the real 0.05 grid is one of exactly two measured, documented
things, neither of which is a bug:

- the reference values the portfolio at the execution day's **close**, which a
  strategy standing at 09:15 cannot know;
- quantity is a floor division by a tick-snapped price, and one 0.05 tick is
  0.19% of a Rs 27 share; the outliers are the cheapest names in the universe.

**Universe verification history:**

> **CORRECTION, 2026-08-27 — this table said "All three universes are verified
> the same way" and listed 58, 74 and mid as though all three were current. Two
> things were wrong with that.**
>
> **1. 58 and 74 are retired, not current.** Both were dropped from the project
> during EXP18 — recorded in `experiments/EXPERIMENTS.md` ("58 and 74 were
> dropped from the project during EXP18") and in
> `results/make_combined_n100_mid.py` ("Project scope narrowed to Nifty 100 and
> MidCap150"). Neither has a `nautilus/reports/` directory any more; only `mid/`
> and `n100/` exist. **Their rows are kept below, because the verification
> history is evidence and deleting it would destroy the record of what was proven
> and when.** They are marked RETIRED so nobody reads them as current.
>
> **2. n100 was missing entirely**, despite being one of the two live universes.
> It is added below — but **with no numbers**, because none are recorded. The
> three `diagnostics/nt_verify_*.txt` artefacts and
> `diagnostics/task3_ntverify.txt` all cover 58, 74 and mid only; no artefact
> anywhere in the project contains an n100 verification result. A verification
> run WAS performed on 2026-08-23 and reported VERIFIED, but its output was never
> written to a project artefact, so there is nothing on disk to cite and the
> numbers are deliberately NOT reproduced from memory. **Re-run
> `nt_verify.py --universe=n100` and capture the output to `diagnostics/` before
> filling that row in.**
>
> How both were found: a read-only audit of the Nautilus layer on 2026-08-23
> traced the reports directories and the universe scope, and this table was the
> only place still presenting the retired pair as live.

> **CORRECTION, 2026-08-23 — the `fills` column below is not a verification
> result, and this table implied that it was.**
>
> The column was written as `929/929`, `883/883`, `985/985`, in the same `x/y`
> form as the reconciliation columns beside it, under a heading saying the
> universes are "verified the same way". Read naturally, that says fill counts
> were reconciled and passed. **They were not reconciled at all.**
>
> `nt_verify.py` does print `fills reference N port M` side by side (line 212),
> but the VERIFIED / NOT VERIFIED verdict at lines 225-250 tests exactly four
> things — `idx_ok`, `a_check[0]`, `d_sym` and `t_stats[0]`. **Fill count is not
> one of them.** A run with mismatched fill counts would still print VERIFIED.
>
> How it was found: a read-only audit on 2026-08-23 traced the verdict logic and
> found no gate consuming the fill counts.
>
> **What the reconciliation actually establishes:** the port and the research
> engine agree on **93 of 93 rebalance dates, at zero tolerance on integer share
> counts**. `compare()` at `nt_verify.py:43-57` is plain dict equality on
> `{symbol: int qty}` — no epsilon, no percentage band. Measured on a 0.01 tick
> grid, which is a CONTROL configuration, not the traded 0.05 grid.
>
> The fill counts themselves are accurate as counts; only their placement in a
> verification table was wrong. The column is retained below, relabelled.

| universe | status | rebalances | fills (informational, not a gate) | symbol-set diffs | ARM A control | ARM D @0.05 | 0.01-tick reconciliation |
|---|---|---|---|---|---|---|---|
| mid  | **LIVE** | 93/93 | 985/985 | 0 | 93 of 93 | 92 of 93 | **93 of 93** — VERIFIED |
| n100 | **LIVE** | *not recorded* | *not recorded* | *not recorded* | *not recorded* | *not recorded* | *NOT YET RECORDED — see correction above* |
| 58   | retired | 93/93 | 929/929 | 0 | 93 of 93 | 93 of 93 | **93 of 93** — VERIFIED |
| 74   | retired | 87/87 | 883/883 | 0 | 87 of 87 | 86 of 87 | **87 of 87** — VERIFIED |

Retired rows are historical: they record what was verified while those universes
were in scope, on the panels of the time. They are not re-run and do not describe
the current pipeline.

### The bar tick was a bug, and removing it is what verified mid

mid previously reconciled at only 49 of 93 on the 0.01 grid, and that was blamed
on tick granularity being coarser in relative terms on cheap names. It was not.
The cause was that `nt_data.py` snapped the daily bar's OHLC to the tick grid
before handing it to the strategy. A tick governs the price an order may be
PLACED at; a historical close is already a traded price, so rounding it a second
time models nothing. The strategy estimates 60-day volatility from those closes
to build its inverse-vol weights, and on a Rs 2.59 share a 0.01 tick is 0.4% of
price — the same order as the daily return being measured. The weights were
therefore perturbed, on exactly the sub-Rs-10 names where the mismatches sat.

The bar now carries the raw price and the quote keeps its tick. Measured effect:

| | 58 | 74 | mid |
|---|---|---|---|
| 0.01 reconciliation, before | 93/93 | 87/87 | **49/93** |
| 0.01 reconciliation, after  | 93/93 | 87/87 | **93/93** |
| ARM D @0.05, before | 35/93 | 32/87 | 15/93 |
| ARM D @0.05, after  | **93/93** | **86/87** | **92/93** |
| final equity, before | 3,236,149.21 | 2,858,906.90 | 6,805,825.55 |
| final equity, after  | 3,236,727.28 | 2,859,300.28 | 6,807,127.33 |

58 and 74 moved by +0.018% and +0.014%. They were expected not to, on the premise
that they hold nothing cheap enough for the effect to bite; that premise was
wrong. 58 holds 13 names under Rs 10 over 7,672 held-days, where one 0.05 tick is
1.09% of price. The movement is the bug being removed from those names, and the
0.01 reconciliation for both is unchanged at 93/93 and 87/87.

`PRICE_PRECISION` went from 2 to 6 at the same time, because 10.7% of the mid
panel's prices carry more than two decimals and would otherwise be re-rounded by
the formatter. That change was measured separately and moves nothing: at legacy
bar-tick the equity is identical to the paisa at precision 2 and precision 6.

`nt_verify.py` reports all four comparisons, including both controls. The ARM A
control is what licenses ARM D as a baseline at all: if ARM A ever stops
reproducing the reference's own holdings, the ARM D number means nothing, and the
script says INCONCLUSIVE rather than passing.

**Verified is not the same as ready to trade.** This reconciles a backtest
against a backtest. Nothing here has been run against live or paper data, and the
live code path has never been exercised.

## Files

| File | Role |
|---|---|
| `nt_data.py` | Builds instruments and market data. Reads `results/metrics/v5_expanding_cache.csv` — the same price panel the engine uses. |
| `nt_export_scores.py` | Exports model scores to parquet. Run once; already done. |
| `nt_strategy.py` | The strategy: ranking, buffer, inverse-vol sizing, breadth exposure. |
| `nt_run.py` | Assembles the venue and runs the backtest. `--full` for 2019–2026. |
| `nt_verify.py` | **The progress metric.** Run after every change. |
| `nt_holdings_compare.py` | Finds the first rebalance where holdings differ, and prints both systems' fills. |
| `nt_daily_compare.py` | Finds the first day the equity curves separate. |
| `nt_attribution.py` | Re-implements the reference engine locally and isolates single causes. ARM A reproduces the reference exactly (93 of 93 rebalances), which is what makes it trustworthy. |
| `verify_next_open_execution.py` | Proves the execution timing model. |

## Reports: `nautilus/reports/<universe>/`

Every run writes `orders.csv`, `fills.csv` and `positions.csv` into a directory named
for its universe, and prints the path it wrote to. Current row counts:

| universe | orders.csv | fills.csv | positions.csv |
|---|---|---|---|
| 58  | 929 | 929 | 469 |
| 74  | 883 | 883 | 446 |
| mid | 985 | 985 | 497 |

This used to be a single shared `reports/` directory. A verification loop over the
three universes therefore left only the LAST one on disk, having silently overwritten
the other two — the files looked current while describing a run nobody had asked
about. For a period, `reports/` held mid's 985 fills and 124 midcap symbols while
appearing to be the 58's output.

### `orders.csv` CANNOT show a DENIED, CANCELED or REJECTED order

It is generated by `eng.trader.generate_order_fills_report()` (`nt_run.py:119`), which
is built from FILL events. **Every row it can contain is FILLED by construction.**
Reading "all 929 orders are FILLED" as proof that nothing was denied is therefore
circular: that report has no way to represent an order that never filled, so its
silence is not evidence.

The actual evidence for zero denials is two independent facts, and it is these that
should be quoted, never the report:

1. **The strategy's denial handler.** `on_order_denied` (`nt_strategy.py:202`) logs a
   warning on every denial. Across all three universes this produces zero denial log
   lines and no "DENIED" anywhere in the run output.
2. **Submitted equals filled.** `nt_run.py` counts submissions from the strategy and
   filled orders from `eng.cache.orders()` filtered on the real status string. These
   agree exactly: 929/929, 883/883, 985/985. An order that was denied would be
   submitted and not filled, so equality is what rules it out.

This matters because denial is the failure mode this port has actually suffered. An
early version had every order denied for 6.5 years (`CUM_NOTIONAL_EXCEEDS_FREE_BALANCE`,
1,333 submitted and 103 filled), and a fills-only report would have shown nothing
wrong at all — just a short, entirely FILLED file.

## Execution model (established by measurement, do not change casually)

Each trading day is fed as two events:

- **09:15** `QuoteTick` with bid = open×0.9985 and ask = open×1.0015 — this is what
  orders execute against.
- **15:30** `Bar` with the day's OHLC — this is what signals are computed from.

The strategy **plans** at 15:31 and **submits** when the next morning's quote
arrives, so the fill is at the next open. Verified on a single order end to end:
expected 183.2745, filled 183.2500 (the residual is the 0.05 tick grid).

Three earlier configurations were tried and rejected by measurement:

| Configuration | Result |
|---|---|
| Bars only, no latency | Filled at the **same bar's close** — look-ahead |
| Bars + LatencyModel | Filled on the right day but at the **stale** book, i.e. the *previous* day's open |
| Quote + plan/submit split | Correct |

Venue settings that matter: `bar_execution=False`, `allow_cash_borrowing=False`,
`fee_model=QbeastIndianFeeModel(..., include_dp=True)`, no latency model.

## Bugs already found and fixed (do not reintroduce)

1. **Execution timing.** Orders were filling at the *previous* day's open while
   carrying the correct date. Found by tracing one order.
2. **Data source.** The loader read raw CSVs; the engine reads the cache panel.
   The panel's union date index changes what `shift(20)` means, so breadth came
   out 27/53 where the engine had 17/53 — exposure 51% instead of 32%.
3. **Cash headroom.** A guessed 5% buffer shrank every buy. Replaced with
   `allow_cash_borrowing=False`, which lets Nautilus deny an overdrawing order.
4. **DP charge.** `QbeastIndianFeeModel` defaults `include_dp=False`, so every
   SELL was undercharged by about Rs 15.34 against the reference. Now enabled.
5. **Buy sizing.** Quantities were computed at the decision close instead of the
   execution open.
6. **A hardcoded number** in `nt_attribution.py` produced a stale verdict. It now
   runs the port live. Watch for this pattern anywhere.
7. **Buys were sent before sells.** Orders went out from `on_quote_tick`, so the
   sequence was quote-arrival order, i.e. alphabetical. On 2019-10-29 four buys
   drained free cash 208,612.23 -> 4,760.83 before any sell was sent, the sells
   were then denied for lack of cash, the positions were never released, and
   every order for the remaining 6.5 years was denied too: 1,333 submitted, 103
   filled. Orders are now released at 09:16, sells first.
8. **A batch of orders shares one stale account snapshot.** Every `submit_order`
   inside one callback is queued and matched only after the callback returns, so
   both the risk check and `self.portfolio` see the PRE-SELL balance for all of
   them. On 2020-08-17 six buys sized off one valuation drove the account to
   -77,885.60 INR and the engine stopped the backtest; on 2020-09-14 five buys
   were denied against a balance the sell proceeds had already covered. The
   queue is now drained one order at a time, each released by the previous fill.
9. **Sells denied by the cash-account risk check.** The venue carries
   `base_currency=INR`, so `RiskEngine._check_order` compares a SELL's notional
   against free CASH and denies selling shares already owned once fully
   invested (2021-03-05 CIPLA: free 171,275.57 vs notional 209,378.00). The same
   function exempts reduce-only orders (`risk/engine.pyx:825`). Sells are now
   submitted with `reduce_only=True`, which is also what they are.
10. **Bars could fill a resting order.** `bar_execution` defaults to True, so an
    order that found no 09:15 quote rested until the 15:30 bar and filled at that
    day's CLOSE (2021-03-05 LTF). The venue now sets `bar_execution=False`, and
    the strategy skips any symbol that did not quote this morning, as the
    reference skips a symbol whose open is NaN.
11. **Buys were funded alphabetically.** When cash runs short the trailing buys
    are skipped, so iteration order decides which name is dropped. The reference
    iterates `top`, which is score-descending. Alphabetical order made the port
    buy JSWSTEEL 413 on 2020-08-17 and skip NESTLEIND, where the reference bought
    NESTLEIND 222 and never held JSWSTEEL. Fixing this took symbol-set
    differences from 5 to 0.

## Causes measured and ruled out (do not re-test these)

| Candidate | Measured effect |
|---|---|
| Sizing at close vs next open | −0.57% |
| Tick rounding to 0.05 | −0.04% (0.01 vs 0.05 tick: −6.26% vs −6.30%) |
| The reference engine's own look-ahead | +0.01% |
| `vol60` calculation | identical to 6 decimal places |
| `n_buy` counting convention | behaviour identical, count differs only |

## One deliberate, permanent difference

The reference values the portfolio at the **execution day's close** when sizing.
Verified by hand on 2019-01-30: portfolio 973,921.51 → invest value 144,025.46 →
BEL 613 shares, which is exactly what it filled. Valuing at the open gives 612.

The port uses the **open**, because a strategy standing at 09:15 cannot know that
day's close. Matching the reference here would require feeding future data. The
measured cost of the reference's look-ahead is +0.01% of final equity, so this is
reported rather than engineered away.

## What to do next

The reconciliation is complete: symbol sets, fill counts and — on a 0.01 tick
grid — every share count agree. There is no known unexplained difference left in
the backtest, so the next work is not more reconciliation.

What has **not** been done, and should come before real money:

1. Run the strategy against paper or live data. Everything verified so far is
   backtest against backtest, on a synthetic 09:15 quote built from the open.
2. Decide what a real fill looks like. The venue currently offers unlimited depth
   at one price; a Rs 3,000 order in BEL is not the same as a Rs 30,00,000 one.
3. Handle the cases the backtest never hit: a rejected order, a partial fill, a
   halted or suspended scrip, a corporate action.

Two rules from this work are worth keeping. Do not propose a cause without a
number attached. And when a number looks wrong, check the measuring instrument
before the system: the "missing" 93rd rebalance was a counting artefact in
`nt_verify.py`, and the quantity gap was measured against a baseline the port was
never designed to match.

Method that has worked every time on this project, and guessing that has not:

1. Run `nt_holdings_compare.py` to find the first rebalance whose **symbol sets**
   differ.
2. Trace that single rebalance end to end in both systems: the ranking, the buffer
   set, the held set, the planned orders, the fills.
3. Change one thing, then run `nt_verify.py` and report
   "identical holdings X of 92".

Four separate hypotheses about this gap were wrong before measurement caught them.
Do not propose a cause without a number attached, and do not widen a tolerance to
make a result pass.

## Rules for this repository

- Everything in every file — code, comments, docstrings, logs, documents — is
  **English only**.
- Verify logic before writing code. Grep the actual paths, columns and regexes.
- Ask before deleting or changing anything.
- Write the accept/reject rule **before** running a test, then look at the result.
- Never introduce look-ahead, leakage or an assumption that flatters the result.
- `results/` and `results74/` are the reference. Read them; never write to them.
