# predictive-engine

A cross-sectional equity ranking system for Indian markets, and the record of the
twenty-five ideas that were tested against it.

> **NAMING.** The universe tags were renamed on 2026-09-18: `mid` ->
> `midcap150`, `n100` -> `nifty100`, `n50` -> `nifty50`. Code and live
> artefacts use the new names; records, diagnostics, `runs/` and all prose
> still use the old ones and are correct to. **An old tag is not a missing
> universe.** The map, and the full list of what deliberately keeps the old
> names, is in [PANEL_MIGRATION.md](PANEL_MIGRATION.md).

Strategy one of a planned series on the same market data. Later
strategies are meant to run against the same universes, the same cost model and
the same verification harness, so that a comparison between them means something.

The engine works and the numbers are below. But the part of this repository worth
your time is `experiments/`. Twenty-five ideas were tested. One was accepted. Every
rejection is written down with the accept rule that was fixed before the run, the
numbers that came back, which gate failed, and what the failure taught. Several of
the corrections in here are corrections to my own earlier claims, left visible with
dates rather than edited out. If you are about to propose an improvement, read
`experiments/EXPERIMENTS.md` first — most of the obvious ones are already closed
with evidence attached.

---

## What it does

Every twenty trading days the model ranks the universe. The top eight names are
held. A held name is sold only when it falls out of the top sixteen, which keeps
turnover down without loosening the selection. Positions are sized inverse to
trailing volatility, and the whole book is then scaled by market breadth — the
fraction of the universe with positive 20-day momentum. When breadth is 0.4, the
strategy deploys 40% of capital and the rest sits in cash earning nothing.

That is why average deployment is 54–56%. It is not an oversight; it is the
exposure rule doing what it was built to do. It also means comparing this to a
fully-invested benchmark on raw CAGR compares two different things, so the tables
below give both sides.

## The model, precisely

LightGBM regressor on cross-sectional rank targets. `n_estimators=400`,
`learning_rate=0.03`, `max_depth=6`, `num_leaves=48`, `subsample=0.8`,
`colsample_bytree=0.8`, `min_child_samples=100`. Ten seeds — `[7, 42, 99, 1, 2, 3,
11, 22, 33, 101]` — averaged. Retrained monthly on an expanding window with a
32-day purge between the training data and the scored month.

Seventeen features, defined as `FEATS_V2` in `results/features_v2.py`: three
momentum (`mom_20`, `mom_120`, `mom_12_1`), two reversal (`rev_5`, `rev_1`), five
volatility and risk (`vol_20`, `vol_ratio`, `idio_vol_60`, `beta_60`,
`downside_vol_60`), three liquidity (`amihud_20`, `turnover_z`, `vol_price_div`),
three trend quality (`trend_consistency_20`, `path_smooth_60`, `dist_high_252`),
and `rsi_14`.

Parameters live in `results/engine_core.py`:

    HORIZON, REBAL, TOP_N, BUFFER, VOL_WIN, PURGE = 20, 20, 8, 16, 60, 32
    SLIPPAGE      = 0.0015
    START_CAPITAL = 1_000_000
    CASH_YIELD    = 0.0

Costs are the real Zerodha delivery-equity schedule — brokerage, STT, stamp duty,
exchange and SEBI fees, GST, and the per-scrip DP charge on sells — computed in
`results/qbeast_in_charges.py`, plus 15 bps of slippage on top. Idle cash earns
nothing, which is deliberate and conservative.

Decisions are made on the close and orders fill at the next open. Nothing in the
pipeline trades on a price it could not have seen.

## Results

Two universes are live. Window 2019-01-01 to 2026-06-08, 1,842 trading days, from
a starting capital of Rs 10,00,000. All figures after costs.

**THESE NUMBERS ARE THE ANCHOR, AND THEY ARE WRITTEN DOWN HERE FOR THAT REASON.**
`results_*/metrics/` is gitignored, so until 2026-09-11 the only copy of any live
figure was an untracked directory. It is transcribed here at full precision,
verbatim from `v34_comparison.csv` in `forensic_snapshot_20260911T0100/`, which is
held in two copies on external media with a SHA-256 manifest
([RETIRED_UNIVERSES-manifest.txt](RETIRED_UNIVERSES-manifest.txt)). A rebuild that
disagrees with a number below is a finding, not a refresh.

Provenance of this table: engine as of commit `54e9f31` — `adj_close` canonical,
interior-gap tradability guard active, `research` profile, cadence 20. **Every
figure here differs from the ones this README carried before 2026-09-11**, which
were measured on the close-price basis before those two corrections; mid's MaxDD
moved most, −18.98% to −15.68%.

> ### READ THIS BEFORE QUOTING ANY v2 FIGURE BELOW
>
> **The shipping arm's published CAGR is not reproducible under changes to the
> price data too small to see, and it is not the centre of its own distribution.**
> Measured 2026-09-20 and 2026-09-21 by `results/price_noise_measure.py`: 50 full
> re-runs of v2 — panel rebuilt, 10-seed ensemble refitted, backtest re-executed —
> on price data perturbed by multiplying `adj_close` by (1 + ε), ε ~ Normal(0, σ),
> drawn per symbol per day. The ten production seeds are held fixed throughout, so
> this dispersion is on top of the seed noise `KNOWN_ISSUES.md` already records.
>
> | | σ | n | published | mean | min | max | sd |
> |---|---|---:|---:|---:|---:|---:|---:|
> | nifty100 v2 | 0.01% | 10 | 19.01 | 20.76 | 19.32 | 22.55 | 1.03 |
> | | 0.50% | 5 | 19.01 | 21.58 | 19.57 | 25.25 | 2.26 |
> | midcap150 v2 | 0.01% | 10 | 27.80 | 29.88 | 27.69 | 32.35 | 1.74 |
> | | 0.50% | 5 | 27.80 | 28.74 | 24.78 | 32.11 | 2.77 |
>
> At σ = 0.01% — a perturbation smaller than the difference between the two price
> panels on 53 of nifty100's 99 names — **19 of the 20 draws across both universes
> came in above the published figure**, and across all 50 cells 43 did
> (p = 1.0e−07). nifty100's 19.01 is still 0.31 points below the minimum of its own
> ten draws. midcap150's 27.80 is not: taking that block from five seeds to ten on
> 2026-09-21 produced 27.69, the first draw below it, so on that universe the
> published figure is an extreme draw and not an unreachable one. On nifty100 at
> n = 10 the sd is 1.03 against the 0.968-point seed-noise floor, so a hundredth of
> a percent on the prices moves the result as much as the whole ensemble does.
>
> **The edge against the basket takes both signs in both universes.** nifty100's
> published −5.15 ranges −7.38 to +1.09 across its 25 perturbed cells; midcap150's
> published +2.34 ranges −0.68 to +7.06 across its 20. The arm beats its basket in
> 2 of 25 nifty100 runs and loses to it in 1 of 20 midcap150 runs.
>
> Mean daily holdings overlap against the unperturbed run falls from 0.662 at
> σ = 0.01% to 0.483 at σ = 0.50% on nifty100, and 0.707 to 0.511 on midcap150.
>
> **Nothing below is deleted or restated.** Every figure in the tables reproduces
> bit-for-bit from the price CSVs and is asserted on every grid start by an
> identity gate. They are legitimate draws. What is measured here is that they are
> extreme draws of their own input distribution, which is a different problem from
> being wrong, and the one that governs how many digits of them can be quoted.
> No mechanism for the one-sidedness is offered; see `KNOWN_ISSUES.md` for what
> was ruled out.

### Nifty 100 — 99 symbols

| arm | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | AnnVol% | Deployed% | FinalEquity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 invvol, 100% invested | 25.77 | 1.26 | 1.68 | -36.03 | 0.72 | 773 | 20.21 | 100.0 | 5461733.57 |
| v2 invvol, breadth-scaled | 19.01 | 1.50 | 2.07 | -21.87 | 0.87 | 940 | 12.33 | 56.8 | 3628639.83 |
| v3 provol, 100% invested | 27.29 | 1.14 | 1.54 | -41.07 | 0.66 | 716 | 24.10 | 100.0 | 5970524.87 |
| v4 provol, breadth-scaled | 21.33 | 1.34 | 1.82 | -24.54 | 0.87 | 934 | 15.62 | 56.8 | 4187801.56 |
| buy & hold equal-weight | 24.16 | 1.27 | 1.45 | -38.65 | 0.63 | 0 | 18.67 | 100.0 | 4969254.64 |

### MidCap150 — 148 symbols

| arm | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | AnnVol% | Deployed% | FinalEquity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 invvol, 100% invested | 36.85 | 1.54 | 1.98 | -40.84 | 0.90 | 850 | 22.37 | 100.0 | 10209897.06 |
| v2 invvol, breadth-scaled | 27.80 | 1.90 | 2.55 | -20.01 | 1.39 | 1006 | 13.65 | 54.6 | 6150398.56 |
| v3 provol, 100% invested | 39.78 | 1.44 | 1.92 | -54.10 | 0.74 | 814 | 25.95 | 100.0 | 11945809.95 |
| v4 provol, breadth-scaled | 34.21 | 1.89 | 2.68 | -24.56 | 1.39 | 1002 | 16.61 | 54.6 | 8840521.94 |
| buy & hold equal-weight | 25.46 | 1.35 | 1.52 | -37.73 | 0.67 | 0 | 18.42 | 100.0 | 5375524.94 |

The shipping arm is v2 (breadth-scaled, inverse-vol). v1 is the always-invested
variant; v3 and v4 are measurement arms on pro-vol sizing and are not shipped.

**The published cap-weighted index is not in this table**, because it is not in
`v34_comparison.csv` and could not be re-sourced from the snapshot. The figures
this README previously carried — NIFTY100 10.93% / 0.69 / −38.10% and
NIFTYMIDCAP150 18.16% / 1.01 / −38.67% — were measured under the previous engine
and are left here **unverified against the current one**, marked rather than
silently reprinted.

> **The chart that stood here has been removed, 2026-09-12.** It was produced by
> `make_combined_universes.py`, which reads `v2FINAL_equity.csv` and the trade
> logs by their canonical names with **no cadence, arm or profile suffix** — so it
> plotted whichever run wrote those files last, and it records nothing about which
> run that was. The table above is transcribed from `v34_comparison.csv`, whose
> name proves its axes; the chart's provenance is not recoverable after the fact,
> and the two read as one artefact. It goes back once that step reads through the
> naming authority. See `KNOWN_ISSUES.md`.

Read those honestly, and read this paragraph before the tables above.

Against the equal-weight buy & hold of its own universe — the harder comparison,
and the one that matters — **the shipping arm now LOSES to its own basket on
nifty100, 19.01 against 24.16, and beats it on midcap150, 27.80 against 25.46.**
That is a sign change on nifty100, not a shrinking edge.

**Neither sign survives a perturbation of the prices too small to see, and that
was measured rather than suspected.** Across 45 full re-runs on 2026-09-20 and
2026-09-21, nifty100's −5.15 ranges −7.38 to +1.09 and midcap150's +2.34 ranges
−0.68 to +7.06; each universe produces the opposite sign in at least one cell.
Both figures above remain what the runs on disk say. Neither should be quoted as
though its sign were established. See the box before the tables and
`KNOWN_ISSUES.md`.

> *Superseded 2026-09-20: this paragraph read "the shipping arm's return edge is
> now 0.43 CAGR points on n100 (24.43 vs 24.00) and 0.89 on mid (29.23 vs 28.34)",
> and before that 2.18 and 1.99. The tables above and these figures are from the
> runs on disk after the 2026-09-18 repoint at
> `Final_Without_Survivorship_Data`; the superseded numbers were measured on the
> previous vendor's prices. Those are two vendors' prices for the same names over
> the same window, so neither set checks the other and the move is not a
> correction of an error. It is not attributed further: see
> `PANEL_MIGRATION.md` §4, which records the same ten-arm comparison and states
> that midcap150 v3's drawdown move, −29.60 to −54.10, has not been investigated.*

No measured noise floor exists to test any of these gaps against — see
`diagnostics/seed_noise.txt`, which reports a mismatch and no spread.

**The drawdown result is the part that still holds, and it is weaker than it was.**
nifty100 −21.87% against buy & hold's −38.65%, midcap150 −20.01% against −37.73%:
a little over half the depth on both, not less than half. On midcap150 the return
is still ahead; on nifty100 it is not. That a rule which goes to cash when breadth
collapses cuts drawdown is the part of the claim that survived the repoint.

> *Superseded 2026-09-20: this paragraph read "n100 −18.38% against buy & hold's
> −37.79%, mid −15.68% against −36.54%: less than half the depth, for a return that
> is still ahead." Every arm's drawdown worsened on both universes, buy & hold
> included, which `PANEL_MIGRATION.md` §4 records as uniform in a way the CAGR
> column is not.*

Two universes were retired, and on **2026-09-11 they were deleted** -- code, raw
data and registry entries. Their figures are kept here because the experiment
record refers to them constantly; the terminal record, including the full-precision
tables and a SHA-256 manifest of every surviving artefact, is
[RETIRED_UNIVERSES.md](RETIRED_UNIVERSES.md).

| universe | window | CAGR | Sharpe | MaxDD | own equal-weight buy & hold |
|---|---|---|---|---|---|
| 58 (deleted 2026-09-11) | 2019-01-01 → 2026-06-08 | 17.01% | 1.39 | −14.34% | 18.02% |
| 74 (deleted 2026-09-11) | 2019-01-01 → 2025-12-23 | 16.25% | 1.43 | −17.85% | 23.78% |

Both lost to their own buy & hold on return. On 74 it is not close. That is here
rather than quietly dropped, because those two universes are where most of the
experiment record was generated, and a reader should know the ground those
conclusions were measured on.

## The execution layer, and what it is worth

`nautilus/` holds a port of the execution path onto NautilusTrader 1.228. No model
runs inside it. The research pipeline exports `date | symbol | score` to parquet
and the port consumes that; the parquet is the only channel between the two.

The port reconciles against the research engine on every rebalance date at zero
tolerance — plain equality on integer share counts, no epsilon. Both live universes
pass:

| universe | 0.01-tick reconciliation | artefact |
|---|---|---|
| mid | 93 of 93 | recorded in `nautilus/NAUTILUS_STATUS.md` |
| n100 | 93 of 93 | `diagnostics/nt_verify_n100.txt` |

What that proves: the two implementations are identical in logic. Order lifecycle,
cash accounting, fee computation and decision timing all survive the move into an
event-driven framework.

What it does not prove: the port runs against a synthetic 09:15 quote built from
the day's open, with `QUOTE_DEPTH` set to ten million shares. Every order fills
instantly, in full, at one price, whatever its size. There is no order book — no L2
data exists anywhere in this project, and the depth model that does exist
synthesises levels from median volume rather than reading them. Slippage is a flat
15 bps baked into that quote, the same for a Rs 1,000 order and a Rs 10,00,000 one.
No latency, no queue position, no market impact, no rejection except for cash.

So the execution layer is a faithful simulation of bookkeeping and timing. It is
not a simulation of execution. `NAUTILUS_STATUS.md` says the same in its own words
and lists what would have to happen before real money.

One number from the n100 verification is worth quoting because it is unflattering.
At the traded 0.05 tick grid, against the close-valued reference, the port matches
on only 2 of 93 rebalances, with a maximum quantity error of 14.29%. That is the
expected consequence of two documented differences — the reference values the
portfolio at a close the strategy cannot see, and quantity is a floor division by a
tick-snapped price — and against the fair baseline the figure is 89 of 93 with a
maximum error of 0.13%. But the 14.29% is real and it is in the artefact, so it is
here too.

## What is wrong with these results

**Survivorship bias, unresolved.** Every universe is today's index membership
backfilled to 2019. Names dropped or delisted during the window are absent
entirely, so both the strategy and its buy & hold benchmark are inflated by an
unknown amount. `results/survivorship.py` implements a point-in-time switch and it
works, but the mode is `static` and the results above are biased. Rebuilding real
membership from the NSE press-release archive reached 2024-03-28 onward — the last
2.5 years of a 7.6-year backtest. `diagnostics/membership/STATUS.md` records the
whole attempt, including that downloading the complete non-bond archive back to
2016 did not extend coverage by a single day, and that the walk still breaks on a
missing IREDA exclusion that is in no press release on disk.

**The edge is concentrated in very few names.** mid beats its own buy & hold by
1.99 points. Remove LLOYDSME and that becomes +0.02. Remove TATAINVEST as well and
it is −0.30. Those figures are from `experiments/EXP21_EXP22_PREREG.txt`, written
before the experiment that measured them ran. One stock going up 123x is carrying
the result.

**No significance test was ever run on the headline edge.** Not that it failed one
— nobody ran one. Individual experiments carry noise controls and shuffle tests,
and several were rejected on them, but the top-level claim that the strategy beats
its buy & hold has never been tested against a null. Given the concentration above,
treat the edge as suggestive rather than established.

![Quarterly rank IC, volatility dispersion, and factor-family IC by half](docs/chart_decay.png)

*Quarterly rank IC on the 58 universe: roughly a third of quarters are negative,
and the two halves read +0.0403 and +0.0214. It was generated by
`results/diagnose_decay.py`, which ran on the 58 only; both the universe and the
script were deleted on 2026-09-11, so **this figure cannot be regenerated and no
equivalent exists for either surviving universe.** See
[RETIRED_UNIVERSES.md](RETIRED_UNIVERSES.md).*

**midcap150 holds positions it could not have bought.** Re-measured 2026-09-20 at
the backtest's own Rs 10,00,000: **12 of 998 fills** with a prior-20-session median
exceed 10% of it (n=1,006 fills in all). The worst is TATAINVEST on 2019-12-26 at
**34.46%**. nifty100 is cleaner: **3 of 932** above 10% (n=940). Modelling depth
properly now costs midcap150 **0.04 CAGR points**, 27.79% to 27.75%, with Sharpe
going 1.90 to 1.89 and 11 orders walking the book (n=1,006 fills, re-run
2026-09-20), and costs nifty100 **0.00 points**, 19.00% to 19.00%, 3 orders walking
(n=940). Details in `diagnostics/liquidity_participation.txt` and
`diagnostics/depth_compare.txt`.

> *Superseded 2026-09-20: this paragraph read "22 of 985 fills", "3 fills of 997",
> and "the worst is AIIL on 2021-06-07 at 1,614% of median daily volume — sixteen
> days of the entire market's volume in that name, in one order." Two things moved.
> The universes were repointed at `Final_Without_Survivorship_Data` on 2026-09-18,
> so the fill counts are from different runs; and AIIL's price file now begins
> 2024-04-23, so the tree holds no 2021 row for it and that order does not exist in
> any current `daily_trades`. The 1,614% was not recomputed smaller — the run that
> produced it cannot be reproduced. Separately, `liquidity_participation.py` had its
> own median-volume definition until 2026-09-20 and now uses the participation cap's;
> measured on the same fills that change moves the aggregate almost not at all
> (midcap150 max 34.458% either way). The depth-model CAGR figures are from
> `depth_compare.py` and are not restated here.* A filter that removed untradeable names was tested
as EXP20 and rejected, failing one sub-period gate by 0.02 Sharpe.

Those depth figures are measured on the Nautilus port, not on the research engine,
so they do not line up exactly with the results table above. The depth cost is
quoted port-to-port -- 27.79% to 27.75% is one system measured twice -- which is
the only way the figure means anything.

> *Superseded 2026-09-20: this paragraph read "the port reads mid at 29.16% where
> the research engine reads 29.18%, and n100 at 25.43% against 25.36%", and quoted
> the depth cost as 1.80 points, 29.16% to 27.36%. `depth_compare.py` was re-run on
> 2026-09-20 against the repointed data and now reports midcap150 27.79% unlimited
> against 27.75% volume, and nifty100 19.00% against 19.00%. The port-versus-engine
> comparison above is not restated: those research-engine figures were measured
> before the repoint too and nobody has re-run them. The depth cost fell from 1.80
> points to 0.04, the unlimited baseline moved with it (29.16 to 27.79), and the
> move is NOT attributed -- swapping only the depth model's volume source changes
> nothing, and reproducing the 2026-09-17 run would need its code as well as its
> data. See `diagnostics/depth_compare.txt`.*

**The trial count is understated.** The pre-registrations maintained a running
count and it drifted. The true number of looks at this dataset is at least 25 and
possibly more. The error runs toward more looks, never fewer, so every
multiple-testing argument in the project was made against a denominator that is too
small.

## The experiment record

`experiments/EXPERIMENTS.md` is the point of this repository. Twenty-six numbered
entries, twenty-five actually run, one acceptance — reducing the held book from
twelve names to eight.

Each entry states what the idea did in enough detail to reimplement it, why it was
worth trying at the time rather than in hindsight, the accept rule quoted verbatim
where a pre-registration survives, the measured result, which gate failed, and what
the failure taught beyond the verdict. Five pre-registrations are kept alongside it
in full, because a summary of a pre-registration is not the same as the
pre-registration — they are the evidence that the rules were written before the
numbers were seen.

Some of what is in there. The exposure and portfolio-construction family is closed
after eight attempts; the Fundamental Law explains why, since IR ≈ IC × √BR and
exposure timing changes neither term. EXP18 fixed a diagnosed IC inversion exactly
as predicted and made performance worse, which means a positive IC does not imply
better performance in this system. EXP22's premise was refuted rather than merely
rejected: no position ever reached 20% of portfolio value, so no weight cap at any
threshold can address mid's concentration, and that closes a whole family of
remedies. One experiment, the sizing test, has a pre-registered rule and no
recorded verdict at all, and it is listed that way rather than guessed at.

Inverse-vol sizing, which is in production and carries real money, went from 4/4 to
1/4 on its own validation suite after a data bug was fixed. That is recorded in the
engines' own `validation_status` block and is the one open question touching a live
component.

If you are about to propose an idea, it is probably in there.

## Repository layout

    results/          the research engine: features, model, walk-forward, backtest,
                      charts, and the survivorship switch
    nautilus/         the NautilusTrader port, its verification harness, and
                      NAUTILUS_STATUS.md
    experiments/      EXPERIMENTS.md, five pre-registrations, and the two restored
                      early test records
    diagnostics/      measured findings: liquidity, depth, tick behaviour, equity
                      reconciliations, and the membership rebuild
    docs/             published copies of two pipeline figures, for this README
    data/reference/   NSE press-release manifest, symbol rename map, circular index
    run_all.py        the whole pipeline, ordered, with a static check that no step
                      reads a file a later step writes

Not tracked, and why: `venv/`, everything under `results*/metrics/`,
`nautilus/reports/`, the score parquets and `cache/` are all rebuilt by
`run_all.py`. `cache/<universe>/` holds the score and raw panels and the
constituent symlink farm; a panel is reused only while its sidecar's content key
matches the source CSVs, so adding, removing or editing a CSV forces a rebuild.
`data/raw/` is about 396 MB of vendor OHLCV and is excluded for size — the code
cannot run without it, so it has to come from a backup rather than from here. Six
small files under `data/raw/` are tracked as exceptions: the three index membership
workbooks and their reference cases, plus the reconstructed Nifty 100 membership.
Those cannot be regenerated, because the press-release PDFs they were derived from
were deleted.

## Running it

Python 3.12.13. Every direct dependency is pinned exactly in `requirements.txt`;
`installed_versions.txt` pins the rest.

```
python3.12 -m venv venv
./venv/bin/python -m pip install -r requirements.txt -c installed_versions.txt
./venv/bin/python run_all.py
```

**Not `python3 run_all.py`.** `run_all.py` spawns every step with
`sys.executable`, so whichever interpreter launches it is used for all 32 steps —
the launch command is load-bearing, and there is no fallback. On the machine this
project was built on, `python3` is Python 3.11: it has no `lightgbm`, so the run
dies at STEP 1, and it is below the 3.12 floor named above. Both failures have
the one cause. Corrected 2026-09-02; this section previously said
`python3 run_all.py`. See `KNOWN_ISSUES.md`, *"The documented commands are not
verified against the machine they run on"*.

Two full `--fresh` rebuilds are recorded at 141.9 and 143.9 minutes
(`run_all_ewma2_log.txt`, `run_all_ewma_log.txt`), but both are from a
two-universe pipeline — those runs built the 58 and the 74, both since deleted.
The current pipeline builds mid and n100 and has no recorded full-rebuild time. With the
panels under `cache/` current, the score-building steps report `score panel
current, skipping build` and the model is not refitted at all.

`python3 nautilus/nt_verify.py --universe=n100` runs the reconciliation. It
executes two complete backtests. One run on 2026-08-27 took roughly 30 minutes,
which is an observed duration on a single run rather than a timed benchmark.
