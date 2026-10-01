# predictive-engine

A cross-sectional equity ranking system for Indian markets, and the record of the
twenty-five ideas that were tested against it.

> **NAMING.** Every universe has one name, used in code, file names, output and
> current docs: `nifty50`, `nifty100`, `nifty200`, `nifty500`, `midcap50`,
> `midcap100`, `midcap150`, `smallcap250`. The short tags `mid`, `n100` and
> `n50` were retired on 2026-09-18 and are refused with an error that lists the
> valid names. They still appear in dated records, pre-registrations and old
> diagnostics, which are left as written; `mid` there means `midcap150`, `n100`
> means `nifty100` and `n50` means `nifty50`. The rename is recorded in
> [PANEL_MIGRATION.md](PANEL_MIGRATION.md).

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

## How to run

You need this tree, the price data and Python 3.12 or newer. The `data` folder's
price files are not in git: a clone has an empty `data/raw/`, and you must copy the
data folder in from a machine that has it (ask the owner, see "The price data").
`run.py` stops before the first step, naming the universe and the folder it looked
in, if a selected universe has no price files. The pinned requirements were resolved on
Python 3.12.13, and that is the version every published result was produced on. On
Python 3.11 pip installs nothing: `scipy==1.18.1` and `nautilus_trader==1.229.0`
need 3.12. `run.py` and `check_all.py` stop at start-up with a message naming the
version if they are started on an older Python.

Create the venv on the internal disk, not on an external exFAT or FAT drive: macOS
writes a `._` twin beside every file there, and those files break installed packages
(matplotlib fails at import when they sit in its style folder). `run.py` stops at
start-up if its venv is on such a drive or has `._` files in site-packages. The
repository folder itself may be on an external drive; `run.py` notes it and runs.

```
# 1. put the price data at data/raw/Final_Without_Survivorship_Data/ and check it
python3 check_data.py
# 2. build the environment with Python 3.12
python3.12 --version          # must print 3.12.x; 3.12.13 reproduces the results
python3.12 -m venv venv
./venv/bin/python -m pip install -r requirements.txt -c installed_versions.txt
# 3. run one combination
./venv/bin/python run.py --universe midcap50 --arm v2
```

`run.py` runs any combination: `--universe` (nifty50, nifty100, nifty200, nifty500,
midcap50, midcap100, midcap150, smallcap250), `--arm` (v1 to v4), `--rebal <days>`
(default 20), `--tax on|off` (default off) and `--profile research|tradeable`
(default research). For example:

```
./venv/bin/python run.py --universe nifty50 --arm v4 --rebal 30 --tax on --profile tradeable
```

Each run writes one folder, `runs/<timestamp>_<universe>_<arm>_r<cadence>/`, holding
`run.log`, the day-by-day log (`DAILY_LOG_*.txt`), the CSVs (daily holdings, trades,
decisions, rankings, the equity curve) and the charts (`chart_*.png`). The first run
of a universe builds its score panel: about 6 minutes for midcap50, 75 for nifty500.
Later runs of that universe reuse it and take under a minute. Use `./venv/bin/python`,
not `python3`.

**Where the costs are.** The end of every `run.log` is a cost summary for each arm:
charges by type, slippage and tax, in rupees, as a percent of starting capital and of
gross profit, per financial year, and against the buy & hold. The same block is in
`COST_SUMMARY_<tag>.txt` beside three CSVs, all in the run folder under
`results_<universe>/metrics/`:
- `COSTS_<tag>.csv`: every fill, with reference price, fill price, slippage in
  rupees, and each charge (STT, exchange fee, SEBI fee, stamp duty, DP charge, GST).
- `COST_LOTS_<tag>.csv`: every lot sold, with buy date, days held, short or long
  term, old or new regime, and the taxable gain.
- `COST_TAX_YEARS_<tag>.csv`: every financial year's buckets, netting, exemption,
  tax at each rate, and the day it was deducted. The tax columns are zero when tax
  is off.

Every figure is reconciled to the paisa against the run's cash and the tax rules
(`results/cost_report.py`); a run whose costs do not reconcile fails. Charges come from
the itemised Zerodha delivery rates in `results/qbeast_in_charges.py`; the charges
section of `data/reference/TAX_AND_CHARGES.docx` is out of date, and its tax rules are
the ones the code uses.

`./venv/bin/python check_all.py` runs the repository's checks. Outside a git checkout
`platform_identity_check.py` is reported as a named skip, and most delegates skip
until the runs they check have been made.

## Current results, 2026-09-29

After tax, over 2019-01-01 to 2026-05-29, on the cleaned prices. The pre-registered
noise test (`experiments/CLEANED_NOISE_PREREG.txt`, n=10 draws per cell at sigma
0.01%) found an after-tax edge over the investable buy & hold in 15 of 32 cells under
both profiles. All 15 now verify in nt_verify. Gap = arm CAGR minus investable buy &
hold CAGR, points, research profile.

| cell | published run (sigma 0) | draws: mean | min | max | draws above 0 |
|---|---:|---:|---:|---:|---:|
| nifty50 v3 | +3.63 | +1.58 | -0.14 | +2.65 | 9 of 10 |
| nifty200 v1 | +16.74 | +8.68 | +6.05 | +11.34 | 10 of 10 |
| nifty200 v3 | +18.19 | +9.25 | +5.90 | +15.59 | 10 of 10 |
| nifty200 v4 | +7.46 | +2.28 | -0.45 | +5.40 | 9 of 10 |
| nifty500 v1 | +5.18 | +12.00 | +7.45 | +13.94 | 10 of 10 |
| nifty500 v2 | -1.33 | +2.75 | -0.19 | +4.95 | 9 of 10 |
| nifty500 v3 | +12.47 | +18.27 | +12.32 | +24.40 | 10 of 10 |
| nifty500 v4 | +2.00 | +6.91 | +3.22 | +9.93 | 10 of 10 |
| midcap100 v1 | +2.85 | +3.49 | +0.64 | +6.61 | 10 of 10 |
| midcap100 v3 | +2.07 | +5.19 | +3.21 | +7.54 | 10 of 10 |
| midcap150 v1 | +10.34 | +8.39 | +2.11 | +11.91 | 10 of 10 |
| midcap150 v3 | +13.53 | +8.16 | +3.10 | +13.08 | 10 of 10 |
| midcap150 v4 | +4.37 | +3.22 | +1.04 | +6.17 | 10 of 10 |
| smallcap250 v1 | +15.69 | +9.38 | +5.52 | +12.99 | 10 of 10 |
| smallcap250 v3 | +14.95 | +15.39 | +9.17 | +21.52 | 10 of 10 |

Read these with the caveats below:

- **32 cells were tested.** A single supported cell on its own is not an edge.
- **Every figure depends on the exact price path.** In 15 of 32 cells the published
  run lies outside the range of all ten draws (nifty500: below every draw on three
  arms; nifty200: above every draw on all four). The cause is that the noise gives
  a sign to every exactly-zero return, which moves the up-day and downside
  features the same way in every draw. A live run is computed like the published
  run, not like a draw, but should be expected to differ from it by as much as
  the draws do. See "The noise draws and the published run" in KNOWN_ISSUES.md.
- **Survivorship.** The universes are today's index members applied back to 2019.
  The supplier's point-in-time membership files cannot say whether a name was a
  member for most of the position-days these arms held: 46% to 79% of each arm's
  profit comes from position-days the files cannot classify. Removing only the
  profit the files mark as held while not a member changes the gaps by -3.3 to
  +1.0 points; reading every unknown day as the files' events imply (which
  assumes no event is missing) changes them by -11.9 to +0.7 points, and leaves
  nifty500 v1 and v4 below zero. These are estimates, not backtests
  (`diagnostics/survivorship_attribution.txt`). The files are not good enough to
  run the strategy on point-in-time members: each of the six universes with a supported
  cell misses 6 to 9 of the 15 scheduled reviews in the window, and 3 to 96 names
  that left an index during the window have no price file.
- **The tradeable profile is ungated**, and a live run is not possible yet: see
  "Live orders" in KNOWN_ISSUES.md.

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

### Read these first

- **The prices were cleaned on 2026-09-27 and every cell was republished.** The
  current figures are in "Republished 2026-09-27 on cleaned prices" below. Every
  other figure in this file, in every section, was computed on the uncleaned
  prices and is superseded by that date; they are left as written. The cleaning
  moved the tax-on CAGR of the 32 research cells by 3.57 points on average in
  either direction (range -5.00 to +12.28) and changed the sign of the gap against
  the investable buy & hold in 7 of them.
- **Every current figure is one draw (n=1).** No noise draw has been made on the
  cleaned prices. The n=10 spreads further down were measured on the uncleaned
  prices. Figures of this kind have moved by more than 12 CAGR points under
  changes that are not strategy changes (the cleaning touched 0.4% to 0.5% of
  rows).
- **One name carried midcap150's edge on the uncleaned prices.** midcap150 v2 beat
  its own buy & hold by +3.32 CAGR points, and removing TATAELXSI cut that to
  +0.07 (tax off, reference buy & hold, measured 2026-09-25). Not re-measured on
  the cleaned prices.
- **The investable buy & hold pays no tax in the headline** because it never
  sells. That is what holding and never trading earns. The "sold on the last day"
  column prices the alternative: everything sold on 2026-05-29, with sell charges
  and capital-gains tax.
- **The after-tax noise test on the cleaned prices, 2026-09-29**
  (`experiments/CLEANED_NOISE_PREREG.txt`, 32 cells, sigma 0.01%, n=10, research
  and tradeable): 15 of 32 cells pass the registered rule under both profiles.
  7 of them verified in nt_verify at registration: nifty50 v3, midcap150 v4,
  smallcap250 v1 and v3, nifty200 v1, nifty500 v1 and v2. The other 8 verify
  since nt_verify's quote-mid valuation rule of 2026-09-29, which passes all 32
  cells. 32 cells were tested, so a single supported cell on its own is
  not to be read as an edge, and the tradeable profile is ungated. Report:
  `diagnostics/cleaned_noise.txt`. The earlier tests on the uncleaned prices are
  superseded.
- **The cleaning, 2026-09-27.** On about 0.4% of rows adj_close/close moved for one
  to five sessions and came back, which no corporate action does. Those sessions
  now take the previous session's ratio (`experiments/DATA_CLEANING_SPEC.txt`).
  The rule reads up to five later sessions to decide, so it is a data repair and
  not something a live book could compute on the day.
- **The survivorship bias is permanent.** Every universe is today's index members
  backfilled to 2019 (see "What is wrong with these results").

### Republished 2026-09-27 on cleaned prices: every universe, arm and profile

Window 2019-01-01 to 2026-05-29, 1,836 trading days, from Rs 10,00,000, all figures
after costs, cadence 20. All eight panels were rebuilt with the adj_close/close
cleaning of `experiments/DATA_CLEANING_SPEC.txt`: a ratio move that returns within
0.1% of the previous session's ratio within five sessions takes the previous ratio
(0.39% to 0.54% of each universe's rows in the window; counts in
`diagnostics/ratio_clean_counts.txt`). The raw files are unchanged. They were produced
by four runs of 2026-09-27 (research and tradeable, tax off and on) whose run folders
are no longer kept; every figure is in `diagnostics/cells_cleaned_20260927.csv`,
`diagnostics/tax_on_all_arms.csv` and `diagnostics/tradeable_tax_all_arms.csv`, and
`run.py` reproduces any cell. Every figure here is one run (n=1). The noise test on the
cleaned prices is in "Current results" above; the tables here carry no error bar;
the n=10 spreads published earlier were measured on the uncleaned data.

Tax on, headline and sold on the last day, are as defined in the 2026-09-25 section
below; no tax rule changed.

`research` profile:

| universe | arm | tax off: CAGR% | MaxDD% | Sharpe | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| nifty50 | v1 | 23.20 | -29.50 | 1.27 | 20.16 | -29.47 | 1.11 | 20.47 | n=1 |
| nifty50 | v2 | 15.31 | -15.11 | 1.29 | 13.15 | -16.65 | 1.10 | 13.37 | n=1 |
| nifty50 | v3 | 27.18 | -33.76 | 1.30 | 23.25 | -33.76 | 1.13 | 23.45 | n=1 |
| nifty50 | v4 | 18.29 | -16.83 | 1.30 | 15.80 | -16.80 | 1.13 | 15.95 | n=1 |
| nifty100 | v1 | 28.01 | -33.02 | 1.37 | 23.70 | -33.02 | 1.17 | 23.75 | n=1 |
| nifty100 | v2 | 20.44 | -19.78 | 1.60 | 17.24 | -20.31 | 1.34 | 17.39 | n=1 |
| nifty100 | v3 | 30.36 | -39.06 | 1.26 | 26.15 | -39.04 | 1.10 | 26.18 | n=1 |
| nifty100 | v4 | 21.61 | -20.99 | 1.43 | 18.37 | -21.52 | 1.22 | 18.50 | n=1 |
| nifty200 | v1 | 47.04 | -34.58 | 1.93 | 40.42 | -34.57 | 1.67 | 40.56 | n=1 |
| nifty200 | v2 | 32.25 | -16.77 | 2.11 | 27.64 | -16.74 | 1.79 | 27.81 | n=1 |
| nifty200 | v3 | 49.40 | -46.72 | 1.78 | 41.88 | -46.97 | 1.53 | 41.91 | n=1 |
| nifty200 | v4 | 36.41 | -24.97 | 1.99 | 31.15 | -25.40 | 1.70 | 31.24 | n=1 |
| nifty500 | v1 | 34.36 | -47.08 | 1.44 | 29.61 | -47.09 | 1.25 | 29.78 | n=1 |
| nifty500 | v2 | 27.29 | -29.77 | 1.88 | 23.10 | -29.77 | 1.56 | 23.25 | n=1 |
| nifty500 | v3 | 44.21 | -62.84 | 1.56 | 36.90 | -63.14 | 1.33 | 37.01 | n=1 |
| nifty500 | v4 | 31.30 | -39.00 | 1.85 | 26.43 | -39.04 | 1.54 | 26.50 | n=1 |
| midcap50 | v1 | 34.47 | -35.73 | 1.59 | 29.12 | -35.78 | 1.36 | 29.32 | n=1 |
| midcap50 | v2 | 22.80 | -28.35 | 1.62 | 19.40 | -29.42 | 1.37 | 19.54 | n=1 |
| midcap50 | v3 | 34.80 | -41.20 | 1.47 | 29.93 | -41.19 | 1.28 | 30.27 | n=1 |
| midcap50 | v4 | 23.63 | -29.22 | 1.52 | 20.21 | -29.18 | 1.29 | 20.38 | n=1 |
| midcap100 | v1 | 32.64 | -35.36 | 1.45 | 27.32 | -35.36 | 1.23 | 27.60 | n=1 |
| midcap100 | v2 | 26.26 | -22.60 | 1.69 | 22.19 | -22.56 | 1.43 | 22.33 | n=1 |
| midcap100 | v3 | 32.33 | -48.17 | 1.29 | 26.55 | -48.29 | 1.08 | 26.76 | n=1 |
| midcap100 | v4 | 26.13 | -31.29 | 1.48 | 22.14 | -31.30 | 1.26 | 22.28 | n=1 |
| midcap150 | v1 | 41.86 | -40.76 | 1.77 | 33.89 | -40.76 | 1.46 | 34.10 | n=1 |
| midcap150 | v2 | 28.46 | -24.95 | 1.88 | 24.04 | -24.95 | 1.57 | 24.17 | n=1 |
| midcap150 | v3 | 43.70 | -41.12 | 1.65 | 37.09 | -41.12 | 1.42 | 37.31 | n=1 |
| midcap150 | v4 | 32.69 | -21.21 | 1.86 | 27.92 | -21.21 | 1.58 | 28.04 | n=1 |
| smallcap250 | v1 | 50.21 | -35.96 | 2.02 | 42.29 | -35.91 | 1.73 | 42.36 | n=1 |
| smallcap250 | v2 | 28.69 | -24.43 | 2.03 | 24.21 | -24.35 | 1.68 | 24.24 | n=1 |
| smallcap250 | v3 | 49.05 | -36.49 | 1.82 | 41.55 | -36.52 | 1.59 | 41.86 | n=1 |
| smallcap250 | v4 | 30.74 | -30.97 | 1.89 | 25.87 | -31.01 | 1.58 | 25.88 | n=1 |

Buy & hold, the same for every arm of a universe (definitions as in the 2026-09-25
section). The investable buy & hold's CAGR moved by at most 0.0006 points: it buys at
the first session's open and is valued at the last session's close, and neither
session was cleaned. The reference index fell by 0.22 to 0.62 points in every
universe. It rebalances daily, and a price that jumps and reverts adds a small
rebalancing gain to a daily-rebalanced basket each time; the cleaning removed those.

| universe | buy & hold, reference (untaxed, daily-rebalanced index): CAGR% | MaxDD% | buy & hold, investable (held lots), taxed, headline: CAGR% | MaxDD% | held lots, sold on the last day: CAGR% | v2 tax on headline minus investable headline | v2 sold on the last day minus held lots sold on the last day |
|---|---:|---:|---:|---:|---:|---:|---:|
| nifty50 | 20.45 | -37.31 | 19.62 | -35.65 | 18.35 | -6.47 | -4.97 |
| nifty100 | 23.90 | -37.40 | 23.38 | -34.52 | 21.97 | -6.14 | -4.59 |
| nifty200 | 25.12 | -38.03 | 23.69 | -35.54 | 22.27 | +3.95 | +5.54 |
| nifty500 | 25.60 | -41.56 | 24.43 | -35.99 | 22.91 | -1.33 | +0.33 |
| midcap50 | 23.73 | -37.92 | 25.97 | -37.91 | 24.51 | -6.57 | -4.97 |
| midcap100 | 26.25 | -38.89 | 24.48 | -38.41 | 23.04 | -2.29 | -0.72 |
| midcap150 | 24.95 | -37.67 | 23.55 | -35.32 | 22.16 | +0.48 | +2.01 |
| smallcap250 | 26.56 | -48.94 | 26.60 | -44.91 | 24.95 | -2.39 | -0.70 |

All four arms against the investable taxed buy & hold, tax-on headline minus investable
headline, CAGR points (`diagnostics/tax_on_all_arms.csv`, full precision):

| universe | investable buy & hold | v1 gap | v2 gap | v3 gap | v4 gap |
|---|---:|---:|---:|---:|---:|
| nifty50 | 19.62 | +0.54 | -6.47 | +3.63 | -3.82 |
| nifty100 | 23.38 | +0.32 | -6.14 | +2.77 | -5.01 |
| nifty200 | 23.69 | +16.74 | +3.95 | +18.19 | +7.46 |
| nifty500 | 24.43 | +5.18 | -1.33 | +12.47 | +2.00 |
| midcap50 | 25.97 | +3.14 | -6.57 | +3.95 | -5.76 |
| midcap100 | 24.48 | +2.85 | -2.29 | +2.07 | -2.34 |
| midcap150 | 23.55 | +10.34 | +0.48 | +13.53 | +4.37 |
| smallcap250 | 26.60 | +15.69 | -2.39 | +14.95 | -0.73 |

`tradeable` profile (participation cap). The cap binds in 10 of 32 cells
(`diagnostics/tradeable_tax_all_arms.csv`) and changes the CAGR in the seven below; in
the other 25 the tradeable figures equal the research ones exactly. All 64 (cell, profile) rows are in
`diagnostics/cells_cleaned_20260927.csv`. The profile is UNGATED
(`profiles.UNGATED_NOTICE`).

| universe | arm | research, tax off | tradeable, tax off | research, tax on | tradeable, tax on | tradeable, sold on the last day | gap, research | gap, tradeable |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| nifty500 | v1 | 34.36 | 33.54 | 29.61 | 28.63 | 28.80 | +5.18 | +4.20 |
| nifty500 | v2 | 27.29 | 27.26 | 23.10 | 23.07 | 23.21 | -1.33 | -1.36 |
| nifty500 | v3 | 44.21 | 44.17 | 36.90 | 36.87 | 36.98 | +12.47 | +12.44 |
| midcap100 | v1 | 32.64 | 31.70 | 27.32 | 27.75 | 28.03 | +2.85 | +3.28 |
| midcap100 | v3 | 32.33 | 32.32 | 26.55 | 26.50 | 26.71 | +2.07 | +2.02 |
| smallcap250 | v1 | 50.21 | 49.40 | 42.29 | 41.33 | 41.40 | +15.69 | +14.73 |
| smallcap250 | v3 | 49.05 | 47.06 | 41.55 | 39.68 | 39.98 | +14.95 | +13.08 |

**Old against new, research profile, tax on headline** (old: 2026-09-25/26 on the
uncleaned prices; `diagnostics/cells_old_vs_new_20260927.csv` has every column for
both profiles). The tax-on CAGR rose in 24 cells and fell in 8, by 3.57 points on
average in either direction (range -5.00 to +12.28). The gap against the investable
buy & hold changed sign in 7 cells under both profiles: five from negative to
positive (nifty50 v1 and v3, nifty100 v1, midcap50 v1 and v3) and two from positive
to negative (nifty500 v2 and midcap100 v2, the two v2 edges that were positive).
Moves this size are the scale of the single-draw instability recorded elsewhere in
this file; they do not say the cleaning made any arm better or worse as a strategy.

| universe | arm | tax-on CAGR old | new | change | gap old | gap new | sign changed |
|---|---|---:|---:|---:|---:|---:|---|
| nifty50 | v1 | 15.11 | 20.16 | +5.05 | -4.51 | +0.54 | **yes** |
| nifty50 | v2 | 11.41 | 13.15 | +1.74 | -8.21 | -6.47 | no |
| nifty50 | v3 | 18.65 | 23.25 | +4.59 | -0.97 | +3.63 | **yes** |
| nifty50 | v4 | 13.21 | 15.80 | +2.58 | -6.41 | -3.82 | no |
| nifty100 | v1 | 21.53 | 23.70 | +2.17 | -1.85 | +0.32 | **yes** |
| nifty100 | v2 | 16.43 | 17.24 | +0.81 | -6.95 | -6.14 | no |
| nifty100 | v3 | 23.68 | 26.15 | +2.47 | +0.30 | +2.77 | no |
| nifty100 | v4 | 17.46 | 18.37 | +0.91 | -5.92 | -5.01 | no |
| nifty200 | v1 | 32.35 | 40.42 | +8.07 | +8.66 | +16.74 | no |
| nifty200 | v2 | 24.06 | 27.64 | +3.58 | +0.37 | +3.95 | no |
| nifty200 | v3 | 29.60 | 41.88 | +12.28 | +5.92 | +18.19 | no |
| nifty200 | v4 | 24.57 | 31.15 | +6.58 | +0.88 | +7.46 | no |
| nifty500 | v1 | 33.53 | 29.61 | -3.93 | +9.11 | +5.18 | no |
| nifty500 | v2 | 26.32 | 23.10 | -3.21 | +1.89 | -1.33 | **yes** |
| nifty500 | v3 | 36.89 | 36.90 | +0.01 | +12.46 | +12.47 | no |
| nifty500 | v4 | 28.31 | 26.43 | -1.88 | +3.88 | +2.00 | no |
| midcap50 | v1 | 25.21 | 29.12 | +3.91 | -0.76 | +3.14 | **yes** |
| midcap50 | v2 | 17.81 | 19.40 | +1.60 | -8.17 | -6.57 | no |
| midcap50 | v3 | 22.06 | 29.93 | +7.87 | -3.91 | +3.95 | **yes** |
| midcap50 | v4 | 16.38 | 20.21 | +3.83 | -9.59 | -5.76 | no |
| midcap100 | v1 | 32.32 | 27.32 | -5.00 | +7.84 | +2.85 | no |
| midcap100 | v2 | 24.49 | 22.19 | -2.30 | +0.01 | -2.29 | **yes** |
| midcap100 | v3 | 30.90 | 26.55 | -4.35 | +6.42 | +2.07 | no |
| midcap100 | v4 | 19.36 | 22.14 | +2.78 | -5.11 | -2.34 | no |
| midcap150 | v1 | 30.95 | 33.89 | +2.94 | +7.40 | +10.34 | no |
| midcap150 | v2 | 24.16 | 24.04 | -0.12 | +0.60 | +0.48 | no |
| midcap150 | v3 | 30.49 | 37.09 | +6.60 | +6.94 | +13.53 | no |
| midcap150 | v4 | 29.00 | 27.92 | -1.08 | +5.44 | +4.37 | no |
| smallcap250 | v1 | 41.06 | 42.29 | +1.23 | +14.46 | +15.69 | no |
| smallcap250 | v2 | 21.05 | 24.21 | +3.16 | -5.55 | -2.39 | no |
| smallcap250 | v3 | 39.37 | 41.55 | +2.18 | +12.77 | +14.95 | no |

### SUPERSEDED 2026-09-27, computed on the uncleaned prices -- Republished 2026-09-25: tax off and tax on, every universe and arm

> *Superseded 2026-09-27: every figure in this section, including the after-tax
> noise verdict and the four-arm gap table, was computed on prices before the
> adj_close/close cleaning. The current figures are in the section above. Nothing
> below is changed.*

Window 2019-01-01 to 2026-05-29, 1,836 trading days, from Rs 10,00,000, all
figures after costs, cadence 20, `research` profile. Run folders
`runs/20260925T101022_all_all_r20` (tax off) and `runs/20260925T102105_all_all_r20`
(tax on).

- **Tax off** figures are identical to the 2026-09-24 publication (all 536 CSVs
  compared; the Nautilus reports differ only in random identifier columns).
- **Tax on, headline**: capital-gains tax is paid from cash in the loop under
  TAX_AND_CHARGES.docx; the last, partial financial year (FY2026-27) is settled on
  the final session on the gains realised by then; nothing is sold at the end.
- **Tax on, sold on the last day**: the same run, with every holding sold at the
  final session's open (its close where the open is missing), paying the usual
  sell charges, and the realised gains taxed under the same rules. The sale fills
  at the open because every trade in the engine does, so this figure can come out
  above the headline when the held names close below their open that day.
- **The last, partial year gets the full exemption.** FY2026-27 is taxed with the
  whole annual Rs 1,25,000 long-term exemption, not a pro-rated share: the
  exemption is set per financial year, and this year is cut short only because
  the data ends on 2026-05-29.

| universe | arm | tax off: CAGR% | MaxDD% | Sharpe | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | n (tax off) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| nifty50 | v1 | 18.54 | -37.73 | 0.99 | 15.11 | -37.73 | 0.83 | 15.30 | n=1 |
| nifty50 | v2 | 13.40 | -23.11 | 1.11 | 11.41 | -23.11 | 0.95 | 11.65 | n=1 |
| nifty50 | v3 | 21.87 | -42.06 | 1.04 | 18.65 | -42.06 | 0.90 | 18.90 | n=1 |
| nifty50 | v4 | 15.46 | -24.43 | 1.10 | 13.21 | -25.29 | 0.94 | 13.43 | n=1 |
| nifty100 | v1 | 25.71 | -37.52 | 1.25 | 21.53 | -37.52 | 1.06 | 21.53 | n=1 |
| nifty100 | v2 | 19.40 | -21.81 | 1.50 | 16.43 | -21.82 | 1.26 | 16.45 | n=10, sd 1.29 |
| nifty100 | v3 | 27.58 | -40.72 | 1.15 | 23.68 | -40.72 | 1.01 | 23.66 | n=1 |
| nifty100 | v4 | 20.38 | -26.66 | 1.28 | 17.46 | -26.66 | 1.11 | 17.48 | n=1 |
| nifty200 | v1 | 38.22 | -41.05 | 1.55 | 32.35 | -41.06 | 1.33 | 32.55 | n=1 |
| nifty200 | v2 | 28.21 | -20.41 | 1.82 | 24.06 | -20.41 | 1.54 | 24.25 | n=1 |
| nifty200 | v3 | 34.88 | -56.70 | 1.29 | 29.60 | -56.46 | 1.12 | 29.65 | n=1 |
| nifty200 | v4 | 29.12 | -26.40 | 1.68 | 24.57 | -26.86 | 1.41 | 24.62 | n=1 |
| nifty500 | v1 | 39.98 | -51.70 | 1.55 | 33.53 | -51.70 | 1.33 | 33.54 | n=1 |
| nifty500 | v2 | 31.14 | -30.83 | 2.07 | 26.32 | -30.83 | 1.72 | 26.40 | n=1 |
| nifty500 | v3 | 46.39 | -60.72 | 1.57 | 36.89 | -60.83 | 1.30 | 36.78 | n=1 |
| nifty500 | v4 | 33.44 | -42.28 | 1.92 | 28.31 | -42.28 | 1.60 | 28.34 | n=1 |
| midcap50 | v1 | 28.74 | -34.95 | 1.39 | 25.21 | -34.96 | 1.22 | 25.47 | n=1 |
| midcap50 | v2 | 20.97 | -22.21 | 1.54 | 17.81 | -22.20 | 1.30 | 17.89 | n=1 |
| midcap50 | v3 | 26.09 | -38.20 | 1.18 | 22.06 | -38.21 | 1.02 | 22.29 | n=1 |
| midcap50 | v4 | 19.47 | -26.08 | 1.34 | 16.38 | -26.04 | 1.13 | 16.49 | n=1 |
| midcap100 | v1 | 37.90 | -36.96 | 1.59 | 32.32 | -36.98 | 1.37 | 32.43 | n=1 |
| midcap100 | v2 | 28.86 | -20.29 | 1.81 | 24.49 | -20.30 | 1.54 | 24.58 | n=1 |
| midcap100 | v3 | 35.99 | -45.07 | 1.32 | 30.90 | -45.06 | 1.17 | 31.03 | n=1 |
| midcap100 | v4 | 23.12 | -36.10 | 1.26 | 19.36 | -36.10 | 1.07 | 19.47 | n=1 |
| midcap150 | v1 | 36.84 | -42.21 | 1.53 | 30.95 | -42.21 | 1.31 | 31.05 | n=1 |
| midcap150 | v2 | 28.78 | -21.39 | 1.94 | 24.16 | -21.39 | 1.61 | 24.24 | n=10, sd 2.23 |
| midcap150 | v3 | 36.34 | -47.80 | 1.36 | 30.49 | -47.80 | 1.17 | 30.54 | n=1 |
| midcap150 | v4 | 33.99 | -25.61 | 1.90 | 29.00 | -25.61 | 1.62 | 29.04 | n=1 |
| smallcap250 | v1 | 48.81 | -36.71 | 1.93 | 41.06 | -36.71 | 1.66 | 41.07 | n=1 |
| smallcap250 | v2 | 25.17 | -24.47 | 1.82 | 21.05 | -24.46 | 1.50 | 21.09 | n=1 |
| smallcap250 | v3 | 46.69 | -40.19 | 1.67 | 39.37 | -40.19 | 1.44 | 39.50 | n=1 |
| smallcap250 | v4 | 24.60 | -31.89 | 1.54 | 20.37 | -31.94 | 1.27 | 20.48 | n=1 |

Buy & hold, the same for every arm of a universe. The reference is the costless
daily-rebalanced equal-weight index the strategy tables have always used, and it
is untaxed. The investable buy & hold buys equal rupees of every name once, pays
the strategy's buy charges, and never trades again; taxed, its headline realises
nothing and pays nothing, and "sold on the last day" pays the strategy's sell
charges and long-term tax on the whole gain. The two right-hand columns are v2
(tax on) against the investable buy & hold, headline against headline and
last-day against last-day.

| universe | buy & hold, reference (untaxed, daily-rebalanced index): CAGR% | MaxDD% | buy & hold, investable (held lots), taxed, headline: CAGR% | MaxDD% | held lots, sold on the last day: CAGR% | v2 tax on headline minus investable headline | v2 sold on the last day minus held lots sold on the last day |
|---|---:|---:|---:|---:|---:|---:|---:|
| nifty50 | 20.67 | -39.11 | 19.62 | -37.78 | 18.35 | -8.21 | -6.70 |
| nifty100 | 24.16 | -38.65 | 23.38 | -35.99 | 21.97 | -6.95 | -5.52 |
| nifty200 | 25.54 | -38.44 | 23.69 | -36.36 | 22.27 | +0.37 | +1.98 |
| nifty500 | 26.09 | -41.43 | 24.43 | -36.29 | 22.91 | +1.89 | +3.49 |
| midcap50 | 24.34 | -37.57 | 25.97 | -38.55 | 24.51 | -8.16 | -6.62 |
| midcap100 | 26.82 | -38.42 | 24.48 | -38.56 | 23.04 | +0.01 | +1.54 |
| midcap150 | 25.46 | -37.73 | 23.55 | -35.88 | 22.16 | +0.61 | +2.08 |
| smallcap250 | 27.15 | -48.65 | 26.60 | -44.98 | 24.95 | -5.55 | -3.86 |

*Superseded 2026-09-27 (uncleaned prices): on the cleaned prices nifty500 v2's gap is
-1.33 and midcap150 v2's +0.48; neither has been noise-tested.* nifty500 +1.89 and
midcap150 +0.61 are single draws. Under the pre-registered
after-tax price-noise test (`experiments/AFTER_TAX_PREREG.txt`, n=10, sigma 0.01%,
seeds 101 to 1010), neither after-tax edge is supported: midcap150 beat the
investable buy & hold in 8 of 10 draws (mean gap +1.51, sd 1.99), nifty500 in 2 of
10 (mean gap -0.27, sd 1.20). Report: `diagnostics/after_tax_noise.txt`; per-run
record: `diagnostics/after_tax_noise_runs.csv`.

All four arms against the investable taxed buy & hold, tax-on headline minus
investable headline, CAGR points (`diagnostics/tax_on_all_arms.csv`, computed at full
precision from each arm's taxed equity curve, 2026-09-26). The arm CAGRs are the ones
in the tables above. Every cell is one draw (n=1); only v2 on nifty500 and midcap150
has been tested under price noise, and neither edge was supported. A few v2 gaps
here differ by 0.01 from the table above (midcap150 +0.60 against +0.61), because
this table rounds after subtracting and that one subtracts rounded figures.

| universe | investable buy & hold | v1 gap | v2 gap | v3 gap | v4 gap |
|---|---:|---:|---:|---:|---:|
| nifty50 | 19.62 | -4.51 | -8.21 | -0.97 | -6.41 |
| nifty100 | 23.38 | -1.85 | -6.95 | +0.30 | -5.92 |
| nifty200 | 23.69 | +8.66 | +0.37 | +5.92 | +0.88 |
| nifty500 | 24.43 | +9.11 | +1.89 | +12.46 | +3.88 |
| midcap50 | 25.97 | -0.76 | -8.17 | -3.91 | -9.59 |
| midcap100 | 24.48 | +7.84 | +0.01 | +6.42 | -5.11 |
| midcap150 | 23.55 | +7.40 | +0.60 | +6.94 | +5.44 |
| smallcap250 | 26.60 | +14.46 | -5.55 | +12.77 | -6.23 |

### SUPERSEDED 2026-09-25 for its tax-on figures -- rebuilt 2026-09-24, and identical on macOS and Linux

*The tax-off figures in this section are unchanged and still current. Its tax-on
figures predate the 2026-09-25 settlement of FY2026-27 and are superseded by the
section above; they are kept as they were.*

Every panel and every published cell was rebuilt on 2026-09-24 after the
feature builder's variance, the CSV float parser and the panel format were
replaced so that macOS arm64, Linux arm64 and Linux amd64 produce identical
bits (see "Running it" and `KNOWN_ISSUES.md`). Window 2019-01-01 to 2026-05-29,
1,836 trading days, from Rs 10,00,000, all figures after costs, cadence 20,
`research` profile. The `tax on` column charges Indian capital-gains tax in the
loop; the buy & hold column is untaxed.

**Read this before any figure below.** A change to the last bits of the
arithmetic, with no change to any strategy rule, moved published figures by up
to 5.9 CAGR points and reversed the sign of two v2 gaps against buy & hold:
midcap100 v2 went from 1.30 points behind its basket to 2.04 ahead, and
smallcap250 v2 from 1.48 ahead to 1.98 behind. Every figure in these tables is
one draw from a distribution. Where that distribution has been measured, the
`n` column gives the number of draws and their spread; every other cell is
marked `n=1` and has no error bar.

#### Nifty 100 (99 constituents) -- tax off

| arm | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | AnnVol% | Deployed% | FinalEquity | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| v1 invvol, 100% invested | 25.71 | 1.25 | 1.63 | -37.52 | 0.69 | 751 | 20.36 | 100.0 | 5442885.74 | n=1 |
| v2 invvol, breadth-scaled | 19.4 | 1.5 | 2.01 | -21.81 | 0.89 | 938 | 12.59 | 56.8 | 3716705.42 | n=10, sd 1.29, 18.74 to 22.79 |
| v3 provol, 100% invested | 27.58 | 1.15 | 1.56 | -40.72 | 0.68 | 726 | 24.06 | 100.0 | 6072338.23 | n=1 |
| v4 provol, breadth-scaled | 20.38 | 1.28 | 1.73 | -26.66 | 0.76 | 930 | 15.69 | 56.8 | 3948930.66 | n=1 |
| buy & hold equal-weight | 24.16 | 1.27 | 1.45 | -38.65 | 0.63 | 0 | 18.67 | 100.0 | 4969254.64 | n=1 |

#### MidCap150 (148 constituents) -- tax off

| arm | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | AnnVol% | Deployed% | FinalEquity | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| v1 invvol, 100% invested | 36.84 | 1.53 | 1.95 | -42.21 | 0.87 | 874 | 22.53 | 100.0 | 10205162.44 | n=1 |
| v2 invvol, breadth-scaled | 28.78 | 1.94 | 2.63 | -21.39 | 1.35 | 1016 | 13.76 | 54.6 | 6510101.81 | n=10, sd 2.23, 26.72 to 33.42 |
| v3 provol, 100% invested | 36.34 | 1.36 | 1.82 | -47.8 | 0.76 | 840 | 25.59 | 100.0 | 9931484.57 | n=1 |
| v4 provol, breadth-scaled | 33.99 | 1.9 | 2.75 | -25.61 | 1.33 | 1012 | 16.37 | 54.6 | 8730268.78 | n=1 |
| buy & hold equal-weight | 25.46 | 1.35 | 1.52 | -37.73 | 0.67 | 0 | 18.42 | 100.0 | 5375524.94 | n=1 |

#### v2 against its own equal-weight buy & hold, all eight universes

The distributions are v2 CAGR% under a 0.01% price perturbation, measured
2026-09-24 on these numerics (`diagnostics/price_noise.txt`). Every tax-on
figure and every buy & hold figure is n=1.

| universe | v2 CAGR% tax off | buy & hold | gap | v2 CAGR% tax on | v2 Sharpe | v2 MaxDD% | v2 trades | n, v2 tax off |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| midcap150 | 28.78 | 25.46 | +3.32 | 24.29 | 1.94 | -21.39 | 1016 | n=10, sd 2.23, 26.72 to 33.42 |
| nifty100 | 19.40 | 24.16 | -4.76 | 16.46 | 1.50 | -21.81 | 938 | n=10, sd 1.29, 18.74 to 22.79 |
| nifty50 | 13.40 | 20.67 | -7.27 | 11.41 | 1.11 | -23.11 | 864 | n=1 |
| midcap50 | 20.97 | 24.34 | -3.37 | 17.81 | 1.54 | -22.21 | 865 | n=1 |
| midcap100 | 28.86 | 26.82 | +2.04 | 24.65 | 1.81 | -20.29 | 898 | n=1 |
| nifty200 | 28.21 | 25.54 | +2.67 | 24.06 | 1.82 | -20.41 | 969 | n=1 |
| smallcap250 | 25.17 | 27.15 | -1.98 | 21.23 | 1.82 | -24.47 | 1086 | n=1 |
| nifty500 | 31.14 | 26.09 | +5.05 | 26.32 | 2.07 | -30.83 | 1119 | n=1 |

### SUPERSEDED 2026-09-24 -- produced by the pre-fix numerics

Everything from here to "The execution layer" was produced before 2026-09-24
and is kept as it was, not restated. The rebuilt figures are above.

Two universes are live. Window 2019-01-01 to 2026-06-08, 1,842 trading days, from
a starting capital of Rs 10,00,000. All figures after costs.

**THESE NUMBERS ARE THE ANCHOR, AND THEY ARE WRITTEN DOWN HERE FOR THAT REASON.**
`results_*/metrics/` is gitignored, so until 2026-09-11 the only copy of any live
figure was an untracked directory. It is transcribed here at full precision,
verbatim from `v34_comparison.csv` in `forensic_snapshot_20260911T0100/`, which is
held in two copies on external media with a SHA-256 manifest
(`RETIRED_UNIVERSES-manifest.txt`, removed from the tree on 2026-09-24; `git show
50562ed:RETIRED_UNIVERSES-manifest.txt`). A rebuild that
disagrees with a number below is a finding, not a refresh.

Provenance of this table: engine as of commit `54e9f31` — `adj_close` canonical,
interior-gap tradability guard active, `research` profile, cadence 20. **Every
figure here differs from the ones this README carried before 2026-09-11**, which
were measured on the close-price basis before those two corrections; midcap150's MaxDD
moved most, −18.98% to −15.68%.

### Price noise re-measured 2026-09-24 on the new numerics

The same measurement as the superseded box below, sigma 0.01% only, seeds 101 to
1010, n=10 per universe. Report: `diagnostics/price_noise.txt`; per-run record:
`diagnostics/price_noise_runs.csv`. The sigma 0.50% blocks were not re-run.

| v2, sigma 0.01% | published | mean | sd | min | max | draws above published |
|---|---:|---:|---:|---:|---:|---:|
| nifty100 | 19.40 | 21.21 | 1.29 | 18.74 | 22.79 | 9 of 10 |
| midcap150 | 28.78 | 29.64 | 2.23 | 26.72 | 33.42 | 7 of 10 |

nifty100's published figure is now inside its own range; the old 19.01 was below
the old minimum. 16 of the 20 draws are above the published figure, against 19 of
20 before.

> **SUPERSEDED 2026-09-24.** Everything in this box was measured on the pre-fix
> numerics. The old per-run record is
> `diagnostics/price_noise_runs_superseded_20260924.csv` and the old report is
> `diagnostics/price_noise_superseded_20260924.txt`.
>
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
record refers to them constantly. The terminal record, including the full-precision
tables and a SHA-256 manifest of every surviving artefact, was RETIRED_UNIVERSES.md;
it was removed from the tree on 2026-09-24 and is in git history (`git show
50562ed:RETIRED_UNIVERSES.md`). The two universes were known by their sizes, 58 and
74, and the table keeps those names because the experiment record uses them.

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

The port is checked against the research engine on every rebalance date at zero
tolerance — plain equality on integer share counts, no epsilon. Measured
2026-09-25 on the current numerics with `nautilus/nt_verify.py --universe=<tag>`,
v2, cadence 20, n = 92 rebalances per universe. check_all gates nifty100 and
midcap150 on every run; the other six were measured once:

| universe | rebalances with the same names | rebalances with identical holdings (0.01 tick) | differences nt_verify cannot explain | status |
|---|---:|---:|---:|---|
| nifty100 | 92 of 92 | 92 of 92 | 0 | reconciled, gated |
| midcap150 | 92 of 92 | 92 of 92 | 0 | reconciled, gated |
| nifty50 | 92 of 92 | 92 of 92 | 0 | matched once, not gated |
| smallcap250 | 92 of 92 | 92 of 92 | 0 | matched once, not gated |
| midcap50 | 91 of 92 | 92 of 92 | 0 | **not reconciled** |
| midcap100 | 92 of 92 | 80 of 92 | 12 | **not reconciled** |
| nifty200 | 92 of 92 | 91 of 92 | 1 | **not reconciled** |
| nifty500 | 92 of 92 | 91 of 92 | 1 | **not reconciled** |

**midcap50, midcap100, nifty200 and nifty500 are not reconciled.** On midcap50 the
port holds a different set of names from the research engine on 1 of 92
rebalances. On midcap100 the holdings differ on 12 of 92 rebalances, and on
nifty200 and nifty500 on 1 of 92 each. None of these differences is explained,
and none has been investigated. Every Nautilus figure for those four universes is
unverified. See `KNOWN_ISSUES.md`.

> *Superseded 2026-09-26 for midcap50: its "91 of 92" and the sentence saying the port
> holds a different set of names there came from nt_verify's control re-run, which
> valued the book at the close, not from the port. With that re-run valuing at the open
> as the research engine does, midcap50 v2 is 92 of 92 on names, 92 of 92 on the 0.01
> grid, and verified. The other seven rows are unchanged.*

> *Superseded 2026-09-25: this table read "midcap150 93 of 93, nifty100 93 of 93",
> measured before the 2026-09-24 numerics rebuild, when the window held 93
> rebalances.*

**Every arm, measured 2026-09-26** with `nt_verify.py --arm=<arm>` on all eight
universes (`diagnostics/nt_verify_all_arms_20260926.txt`; for v2 only midcap50 changes,
see the note under the table above):

| arm | verified | not verified |
|---|---|---:|
| v1 invvol, 100% invested | 4 of 8: nifty100, midcap150, nifty50, midcap100 | 4 |
| v2 invvol, breadth-scaled | 5 of 8: nifty100, midcap150, nifty50, midcap50, smallcap250 | 3 |
| v3 provol, 100% invested | 2 of 8: nifty100, midcap150 | 6 |
| v4 provol, breadth-scaled | 5 of 8: nifty100, midcap150, nifty50, midcap100, smallcap250 | 3 |

All four arms verify on nifty100 and midcap150. check_all gates every verified cell,
16 in all, since 2026-09-26; the 16 that do not verify are listed in `check_all.py`.
The port picks the same names as the reference on every rebalance of all 32 cells;
the 16 failures are share-count differences that nt_verify cannot explain as
quantization, on the 0.01 tick grid. Not investigated; see `KNOWN_ISSUES.md`. Every
Nautilus figure for a cell marked not verified is unverified.

> *Superseded 2026-09-26: this block first read "No v1 or v3 cell is verified by
> nt_verify on any universe" (v1 0 of 8, v3 0 of 8, both 8 inconclusive). The
> reference re-run inside nt_verify valued the book at the close while the research
> engine values it at the open; on the 100%-invested arms that changed which buys the
> cash covered. With the reference set to value at the open, its holdings equal the
> research engine's on all 32 cells, and the verdicts are the ones above.*

What that proves, on nifty100 and midcap150 (and, measured once, nifty50 and smallcap250): the two implementations are identical in logic. Order lifecycle,
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

One number from the nifty100 verification is worth quoting because it is unflattering.
At the traded 0.05 tick grid, against the close-valued reference, the port matches
on only 43 of 92 rebalances, with a maximum quantity error of 11.11% (measured
2026-09-25, n = 92). That is the expected consequence of two documented differences
— the reference values the portfolio at a close the strategy cannot see, and
quantity is a floor division by a tick-snapped price — and against the fair
baseline (the same engine valued at the open on 0.05 ticks) the figure is 90 of 92
with a maximum error of 0.05%. But the 11.11% is real and it is in the output, so
it is here too.

> *Superseded 2026-09-25: this paragraph read "2 of 93 rebalances, with a maximum
> quantity error of 14.29% ... against the fair baseline the figure is 89 of 93 with
> a maximum error of 0.13%", measured before the 2026-09-24 numerics rebuild.*

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

**The edge is concentrated in very few names, but not the ones it used to be.**
Re-measured 2026-09-25 with `jackknife.py` on the published v2 run (window
2019-01-01 to 2026-05-29, 1,836 sessions, cadence 20, research profile, tax off;
the script's baseline reproduces `v2FINAL_equity.csv` exactly). midcap150 beats its
own buy & hold by **3.32** points. Removing **TATAELXSI** alone takes that to
**+0.07**. Removing LLOYDSME leaves **+2.94**, and removing TATAINVEST as well
**+2.65**. No single removal of the 148 makes the edge negative; **30 of 200**
random 8-name removals do. On nifty100 the edge is −4.76 and every one of the 99
single removals leaves it negative. Each figure is one draw (n=1). Records:
`diagnostics/jackknife_midcap150_20260925.txt`,
`diagnostics/jackknife_nifty100_20260925.txt`.

> *Superseded 2026-09-25: this paragraph read "midcap150 beats its own buy & hold
> by 1.99 points. Remove LLOYDSME and that becomes +0.02. Remove TATAINVEST as well
> and it is −0.30. Those figures are from `experiments/EXP21_EXP22_PREREG.txt`,
> written before the experiment that measured them ran. One stock going up 123x is
> carrying the result." Those figures were measured on the price data used before
> the 2026-09-18 repoint and before the 2026-09-24 numerics rebuild, with the
> jackknife's old window, which ran six sessions past the backtest's end to
> 2026-06-08. The pre-registration keeps them as written.*

**No significance test was ever run on the headline edge.** Not that it failed one
— nobody ran one. Individual experiments carry noise controls and shuffle tests,
and several were rejected on them, but the top-level claim that the strategy beats
its buy & hold has never been tested against a null. Given the concentration above,
treat the edge as suggestive rather than established.

![Quarterly rank IC, volatility dispersion, and factor-family IC by half](docs/chart_decay.png)

*Quarterly rank IC on the retired 58-name universe: roughly a third of quarters are negative,
and the two halves read +0.0403 and +0.0214. It was generated by
`results/diagnose_decay.py`, which ran on that universe only; both the universe and
the script were deleted on 2026-09-11, so **this figure cannot be regenerated and no
equivalent exists for any current universe.** See `git show
50562ed:RETIRED_UNIVERSES.md`.*

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
threshold can address midcap150's concentration, and that closes a whole family of
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
`run_all.py`. `cache/<universe>/` holds the score and raw panels (parquet) and the
constituent farm (hard links to the source CSVs, or copies where a hard link cannot
be made); a panel is reused only while its sidecar's content key matches the source
CSVs and the code that builds it, so adding, removing or editing a CSV forces a
rebuild.

## The price data

**The price data is not in this repository and cannot be downloaded from anywhere
public. It comes from the owner of this repository: ask them for a copy.** It is
vendor OHLCV, not redistributed here, and nothing runs without it.

The pipeline reads exactly one folder, 876 MB, 1,392 CSV files. Put it at this path,
with these eight subfolders, one per universe:

    data/raw/Final_Without_Survivorship_Data/
        Final_NIFTY50_EoD_Data/            nifty50       51 CSV   (50 constituents + Nifty 50.csv)
        Final_NIFTY100_EoD_Data/           nifty100     100 CSV   (99 + NIFTY 100.csv)
        Final_NIFTY200_EoD_Data/           nifty200     198 CSV   (197 + NIFTY 200.csv)
        Final_NIFTY500_EoD_Data/           nifty500     496 CSV   (495 + NIFTY500.csv)
        Final_NIFTYMidCap50_EoD_Data/      midcap50      50 CSV   (49 + NIFTY MIDCAP 50.csv)
        Final_NIFTYMidCap100_EoD_Data/     midcap100     99 CSV   (98 + NIFTY MIDCAP 100.csv)
        Final_NIFTYMidCap150_EoD_Data/     midcap150    149 CSV   (148 + NIFTY MIDCAP 150.csv)
        Final_NIFTYSmallCap250_EoD_Data/   smallcap250  249 CSV   (248 + NIFTY SMLCAP 250.csv)

Each folder holds one CSV per constituent, named by NSE symbol (`ABB.csv`), and one
for the published index. A universe's constituents are whatever CSVs are in its
folder, so an extra or missing file changes that universe and every figure on it.
For one universe only, copy just its folder; for the published figures, all eight.
Other folders the owner's copy may have under `data/raw/` are not read by the
pipeline: `Final_With_Survivorship_Data/` (1,337 MB), `MidCap150/` (99 MB),
`nifty100_benchmark/` (81 MB) and `Survivorship_Bias/` (1 MB), earlier vendor pulls.
`survivorship_attribution.py` alone reads `Survivorship_Bias/` and the price files of
`Final_With_Survivorship_Data/`; neither is in the checksum manifest.

**Check your copy before running anything:**

```
python3 check_data.py
```

It compares every file against the tracked manifest `data/RAW_DATA_SHA256.txt`
(SHA-256 per file) and exits 0 only if all 1,392 match and no extra file is present;
otherwise it lists each missing, different or extra file. It needs only the Python
standard library. For a copy holding one universe, check just that folder (this
form reads universes/registry.py, so it needs the venv):

```
./venv/bin/python check_data.py --universe=midcap50
```

## Running it

**Platforms.** Verified byte-identical on 2026-09-24 on macOS arm64 (Mac mini M4, Python 3.12.13) and on Linux arm64 and Linux amd64 (Docker `python:3.12.13` on the same Mac; amd64 runs under Rosetta translation, not on a physical Intel or AMD CPU). For a midcap50 v2 run, the score and raw panels and every CSV match byte for byte, the Nautilus reports match once their random identifier columns (`event_id`, `position_id`, `init_id`) are dropped and rows sorted, and the charts match pixel for pixel. **Windows is untested.** Nothing in the code needs a symlink any more and `.gitattributes` stops line-ending conversion, but no run has been made on Windows. On Windows the venv interpreter is `venv\Scripts\python.exe`.

**Linux prerequisites:** git, and Python 3.12.13 with its venv module (on Debian
or Ubuntu the `python3.12-venv` package). The official Docker image
`python:3.12.13` has both; the floating tag `python:3.12` is a later patch release.

```
git clone https://github.com/sidharthjatt/predictive-engine.git
cd predictive-engine
# copy the price data into data/raw/ -- see "The price data"
python3 check_data.py
python3.12 -m venv venv
./venv/bin/python -m pip install -r requirements.txt -c installed_versions.txt
```

Every direct dependency is pinned exactly in `requirements.txt`, and
`installed_versions.txt` pins the rest. **Use the venv interpreter, not
`python3`**: every step runs in the interpreter that launched the run, and on the
machine this project was built on `python3` is 3.11 with no `lightgbm`.

**One universe and one arm:**

```
./venv/bin/python run.py --universe midcap50 --arm v2
./venv/bin/python run.py --list        # the universes and arms, and the plan, without running
```

`--rebal <days>`, `--tax on` and `--profile tradeable` select the other axes.
Every run writes a folder under `runs/` with its artefacts and `run.log`.

**How long it takes** (Mac mini M4, measured 2026-09-23). The FIRST run of a
universe builds its score panel, which dominates: midcap50 6.5 min, nifty50 8.8,
midcap100 11.9, nifty100 16.0, midcap150 17.0, nifty200 29.6, smallcap250 34.5,
nifty500 74.7 (measured while other work shared the machine; treat them as upper
bounds). A REPEAT run reuses the panel: 13-35 s for one midcap50 cell, across the
48 combinations of arm, tax, profile and cadence swept that day.

**Everything:** `./venv/bin/python run_all.py` runs all eight universes and all
four arms.

`./venv/bin/python nautilus/nt_verify.py --universe=nifty100` runs the
reconciliation for v2 (`--arm=v1`, `v3` or `v4` for another arm;
`--universe=midcap150` for the other certified universe;
`--rebal=<n>` reports the port-versus-vectorised gap at another cadence without
gating it). It executes two complete backtests. One run on 2026-08-27 took roughly 30 minutes,
which is an observed duration on a single run rather than a timed benchmark.
