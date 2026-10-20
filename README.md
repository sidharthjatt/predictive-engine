# predictive-engine

A cross-sectional equity ranking system for Indian markets, and the record of the
twenty-five ideas that were tested against it.

> **NAMING.** Every universe has one name, used in code, file names, output and
> current docs: `nifty50`, `nifty100`, `nifty200`, `nifty500`, `midcap50`,
> `midcap100`, `midcap150`, `smallcap250`, `microcap250`, and the three static-only
> market-cap buckets `mcap1500to5000`, `mcap5001to10000`, `mcapover10000`. The short tags `mid`, `n100` and
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
midcap50, midcap100, midcap150, smallcap250, microcap250, mcap1500to5000,
mcap5001to10000, mcapover10000), `--arm` (v1 to v4),
`--rebal <days>` (default 20), `--tax on|off` (default off) and
`--profile research|tradeable` (default research). For example:

```
./venv/bin/python run.py --universe nifty50 --arm v4 --rebal 30 --tax on --profile tradeable
```

`--survivorship static|pit` (default static) chooses the universe construction.
static is every published figure: today's members backfilled. pit uses the
supplier's point-in-time membership files and the with-survivorship prices, and
writes every artefact with a `_pit` suffix. The membership files fail validation
and are used by decision; each pit run records the verdict, the members it could
not price and a look-ahead note in its log, RUN.txt and params JSON. See
`SURVIVORSHIP_README.md` and KNOWN_ISSUES.md.

`--capital RUPEES` (whole rupees, at least 100000; default 1000000) sets the starting
capital of the strategy and of the investable buy & hold. Every published figure is at
the default, which adds nothing to any name; another capital adds `_cap<rupees>` to
files and `@cap<rupees>` to folders, and appears in chart titles, params.json and
RUN.txt. The default is defined once, in `capital_axis.py`. `nautilus/nt_verify.py
--capital=<rupees>` checks the port at that capital (static, research, tax off).

`--impact K` (default 0, off) adds square-root market impact to every buy and sell:
the fill pays the flat 0.15% plus K x sqrt(order shares / prior-20-session median
volume), the formula in `slippage.py`. `--cap F` (default the profile's own, 1.0 under
tradeable) replaces the participation cap. Both need `--profile tradeable`; under
research either one is refused. Neither has a chosen value. At the defaults nothing is
added to any name; otherwise `_impact<k>` and `_pcap<f>` follow every other suffix
(`_impact0p003_pcap0p1`, `@impact0p003@pcap0p1` in folders), and both appear in chart
titles, params.json and RUN.txt. With `--impact`, the cost report and the daily log
totals show impact as its own figure, apart from the flat slippage. The Nautilus port
applies neither (KNOWN_ISSUES.md).

`--fixed-capital` (default off) runs the strategy without reinvesting profit. At each
rebalance open the book is min(`--capital`, equity): buys are sized from it, and profit
above the base stays in cash at 0% and is never spent. Below the base the book is the
equity, so a loss is not topped up. Held names are not trimmed. Tax, charges and
slippage are paid from the account, as in every run. The mode is refused with `--dd`
and with the stop arms. Off adds nothing to any name; on adds `_fixed` after every
other suffix and `@fixed` to folders.

A fixed-capital run also writes `v34_fixed<sfx>.csv` and `v34_fixed_years<sfx>.csv`,
and `fixed.csv` and `fixed_years.csv` in each arm folder. They hold:
- `AvgAnnRet%`: (end equity - base) / base / years.
- `Year%`: each calendar year's rupee P&L / base, and `MeanFullYear%`, their mean
  over the full years.
- `MaxDD_Rs` and `MaxDD_base%`: the fall from the running peak in rupees, and over
  the base.
- `MaxInvested_base%`: the highest held value / base, with its date.
- CAGR, labelled as understating such a run.

The rows cover the strategy, and the basket and the index reset to min(base, equity)
on the strategy's grid days (`results/fixed_capital.py`). The port does not cover
the mode (KNOWN_ISSUES.md).

### The drawdown limit (`--dd`): exploratory, not validated

**Any result with `--dd` on is exploratory. It has not been validated, and it must
not be used to choose a live setting.** No limit, multiplier, floor or band was
pre-registered or tested out of sample. The option is off by default; without it
every run, file and figure is what it was.

```
./venv/bin/python run.py --universe nifty50 --arm v1 --dd 20
./venv/bin/python run.py --universe midcap150 --arm v3 --dd 15 --dd-m 4 --dd-floor 10
```

- `--dd L`: the limit in percent, above 0 and at most 50.
- `--dd-m m`: the cushion multiplier, above 0. Default 1/L, so the book is fully
  invested at a peak. Below 1/L the run prints a warning: the book is then never
  fully invested.
- `--dd-floor F`: the exposure floor in percent, above 0 and at most 100. Default 25.

At each close, with W the close equity and M its all-time peak since the start of
the run (never reset), the exposure limit is `E = max(F, min(1, m * (W - (1 - L) * M) / W))`.
When the invested fraction is more than 5 points above `min(E, arm exposure)`, every
holding is cut by the same proportion at the next open. After a cut, the book is
topped up the same way, at most to the arm's own level. The arm still chooses the
names. Fills go through the normal slippage, charges, participation cap and tax
ledger, as fill kinds `dd trim` and `dd top-up`. The floor keeps part of the book
invested so it can recover after the limit; it also means the limit is not a hard
stop, and an overnight gap can take the drawdown through it.

Each run reports the true worst close drawdown from the all-time peak against L,
whether and by how much L was breached, sessions below L, days at the floor, and
the charges, slippage and marginal tax of the limit's own fills (end of run.log and
`COST_SUMMARY_*.txt`). Every order and fill is in `daily_dd_events_*.csv`. With
`--dd`, `Deployed%` is the mean invested fraction at the close after the limit;
without it, it is the arm's own mean exposure, as before.

Names: `_dd20` after every other suffix (`_dd12p5`, `_dd20m3f10` when m or F is not
the default), `@dd20` in directory names, the limit in chart titles, a `dd` entry in
params.json and a `dd` line in RUN.txt. `--dd` is refused with v5 or v6, which carry
their own stop. The Nautilus port runs the limit; `nautilus/nt_verify.py --dd=20`
checks static, research, tax-off cells only. See KNOWN_ISSUES.md.

Two more arms exist and are not part of `--arm all`: v5 (v1 plus a drawdown stop)
and v6 (v3 plus the stop). The stop exits when the arm's close equity is 20% or more
below its running peak, sells everything at the next open, stays in cash for at
least one rebalance cycle, and re-enters at the first rebalance day with breadth of
0.50 or more; the peak resets at re-entry. The rule, the cells and the accept rule
were pre-registered in `experiments/DRAWDOWN_STOP_PREREG.txt` before either arm
existed in code. On each of 24 cells, the difference from the parent was judged
against a noise band of 2 x sqrt(2) times its standard deviation over 50 ten-seed
subsets of 20 model seeds (`experiments/DRAWDOWN_STOP_BAND.csv`).

Both arms are REJECTED, on the supplier's previous data delivery; the measurement has
not been re-run on the 2026-10-10 delivery, and v5 and v6 were not rebuilt on it. v5
fails criteria 1 to 3: its drawdown is shallower than
v1's by more than the band in 7 of 24 cells (18 needed), its Calmar higher in 6
(15 needed), and its CAGR lower in 10 (at most 6 allowed). v6 fails criteria 1 and
2: 14 of 24 and 8 of 24 (18 and 15 needed). Every cell is in `experiments/DRAWDOWN_STOP_RESULT.txt`.
v5 and v6 stay out of `--arm all`; they run only when selected by name, and write
companion `v34_stop_*` files.

Every v5 and v6 figure, including the Nautilus port check, was measured on the
previous data delivery. On that data the port verified 9 of the 16 v5/v6 cells
(research, tax off). Since 2026-10-10 no v5/v6 cell is gated in `check_all.py`:
both arms are rejected and outside `--arm all`, and their engine files were not
rebuilt on the new data.

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
`code_checks.py platform_identity` is reported as a named skip, and most delegates skip
until the runs they check have been made.

## The noise test, measured on the previous data delivery (2026-09-29)

**Every number in this section was measured on the supplier's previous data
delivery**, on the runs of 2026-09-27, the "published run" column included. The
delivery of 2026-10-10 moved every published figure (see "Republished 2026-10-10"
under Results), and this test has not been re-run on it. The current gaps are in
that section.

After tax, over 2019-01-01 to 2026-05-29, on the cleaned prices. The pre-registered
noise test (`experiments/CLEANED_NOISE_PREREG.txt`, n=10 draws per cell at sigma
0.01%) found an after-tax edge over the investable buy & hold in 15 of 32 cells under
both profiles. All 15 verified in nt_verify on that data. Gap = arm CAGR minus
investable buy & hold CAGR, points, research profile.

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
- **Every figure depends on the exact price path.** On the previous data, in 15 of 32
  cells the published run lies outside the range of all ten draws (nifty500: below every draw on three
  arms; nifty200: above every draw on all four). The cause is that the noise gives
  a sign to every exactly-zero return, which moves the up-day and downside
  features the same way in every draw. A live run is computed like the published
  run, not like a draw, but should be expected to differ from it by as much as
  the draws do. See "The noise draws and the published run" in KNOWN_ISSUES.md.
- **Survivorship.** The universes are today's index members applied back to 2019.
  The supplier's point-in-time membership files cannot say whether a name was a
  member for most of the position-days these arms held. Measured on the
  2026-10-14 research tax-on run, for the same 15 cells: 42% to 74% of each arm's
  profit comes from position-days the files cannot classify. Removing only the
  profit the files mark as held while not a member changes the gaps by -1.1 to
  +1.0 points; reading every unknown day as the files' events imply (which
  assumes no event is missing) changes them by -6.1 to +0.1 points, and leaves
  nifty500 v2 and v4 below zero. These are estimates, not backtests
  (`diagnostics/survivorship_attribution.txt`). The files are not good enough to
  run the strategy on point-in-time members: each of the six universes with a supported
  cell misses 6 to 9 of the 15 scheduled reviews in the window, and 2 to 75 names
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

That is why average deployment is 53–57% (53.3% to 57.4% across the eight universes
on the 2026-10-10 data, the same for v2 and v4). It is not an oversight; it is the
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

Decisions are made on the close and orders fill at the next open. A name is traded
only on a session with a row; a sale due on a session without one fills at the open of
its next row. Nothing in the pipeline trades on a price it could not have seen or
decides on a row dated after the decision.

## Results

### The market-cap buckets, static only, 2026-10-16

**mcap1500to5000:** STATIC AND NOT AN INDEX. The supplier delivered these 477 names as a market-cap bucket, with no membership history. Only 2 of the 477 stop trading before the window ends, so the list appears to hold the bucket's members near the time of delivery, not the members at each date. A stock that left the bucket or was delisted is likely missing; a stock that grew into it is present for the whole window. Both the strategy and its buy & hold therefore likely carry survivorship and look-ahead bias, which cannot be measured without membership files. The benchmark index is the broad NIFTY 500, not a bucket index.

**mcap5001to10000:** STATIC AND NOT AN INDEX. The supplier delivered these 216 names as a market-cap bucket, with no membership history. Only 0 of the 216 stop trading before the window ends, so the list appears to hold the bucket's members near the time of delivery, not the members at each date. A stock that left the bucket or was delisted is likely missing; a stock that grew into it is present for the whole window. Both the strategy and its buy & hold therefore likely carry survivorship and look-ahead bias, which cannot be measured without membership files. The benchmark index is the broad NIFTY 500, not a bucket index.

**mcapover10000:** STATIC AND NOT AN INDEX. The supplier delivered these 538 names as a market-cap bucket, with no membership history. Only 2 of the 538 stop trading before the window ends, so the list appears to hold the bucket's members near the time of delivery, not the members at each date. A stock that left the bucket or was delisted is likely missing; a stock that grew into it is present for the whole window. Both the strategy and its buy & hold therefore likely carry survivorship and look-ahead bias, which cannot be measured without membership files. The benchmark index is the broad NIFTY 500, not a bucket index.

v1 to v4, tax off and on, research and tradeable, cadence 20, Rs 10 lakh, window 2019-01-01
to 2026-05-29, one run per cell. CAGR and MaxDD are each cell's `v34_comparison` row; the
basket is that file's equal-weight buy & hold (untaxed, daily rebalanced); NIFTY 500 is the
price index over the same dates; tax paid is COST_TAX_YEARS `total_tax`, cess included.
mcap1500to5000 is 477 names: the owner removed ELCIDIN on 2026-10-16, whose auction-day
gain could not have been traded (KNOWN_ISSUES.md). Rerun 2026-10-17 under the row rule:
a name is traded only on a session with a row. SANGHIIND's file ends on 2026-04-02, so
every mcap1500to5000 cell holds it to the end at its last close, 50.15, an assumption;
each run's RUN.txt gives the figures with it valued at zero (KNOWN_ISSUES.md). nt_verify
verifies the four mcapover10000 cells; the other eight are not gated (KNOWN_ISSUES.md). There are no pit figures: no membership files exist.

| universe | arm | profile | tax | CAGR% | basket CAGR% | NIFTY 500 CAGR% | MaxDD% | tax paid Rs |
|---|---|---|---|---:|---:|---:|---:|---:|
| mcap1500to5000 | v1 | research | off | 46.19 | 25.92 | 12.94 | -42.64 | 0.00 |
| mcap1500to5000 | v2 | research | off | 28.21 | 25.92 | 12.94 | -17.32 | 0.00 |
| mcap1500to5000 | v3 | research | off | 53.54 | 25.92 | 12.94 | -49.14 | 0.00 |
| mcap1500to5000 | v4 | research | off | 33.79 | 25.92 | 12.94 | -21.04 | 0.00 |
| mcap1500to5000 | v1 | research | on | 37.69 | 25.92 | 12.94 | -42.64 | 2,126,380.43 |
| mcap1500to5000 | v2 | research | on | 23.60 | 25.92 | 12.94 | -17.40 | 780,476.47 |
| mcap1500to5000 | v3 | research | on | 45.37 | 25.92 | 12.94 | -49.14 | 3,249,848.13 |
| mcap1500to5000 | v4 | research | on | 28.32 | 25.92 | 12.94 | -21.04 | 1,094,102.85 |
| mcap1500to5000 | v1 | tradeable | off | 41.62 | 25.92 | 12.94 | -41.45 | 0.00 |
| mcap1500to5000 | v2 | tradeable | off | 22.15 | 25.92 | 12.94 | -17.48 | 0.00 |
| mcap1500to5000 | v3 | tradeable | off | 48.61 | 25.92 | 12.94 | -42.72 | 0.00 |
| mcap1500to5000 | v4 | tradeable | off | 25.46 | 25.92 | 12.94 | -17.41 | 0.00 |
| mcap1500to5000 | v1 | tradeable | on | 34.90 | 25.92 | 12.94 | -41.45 | 1,609,345.42 |
| mcap1500to5000 | v2 | tradeable | on | 18.89 | 25.92 | 12.94 | -17.48 | 509,136.74 |
| mcap1500to5000 | v3 | tradeable | on | 41.13 | 25.92 | 12.94 | -42.72 | 2,308,735.50 |
| mcap1500to5000 | v4 | tradeable | on | 21.62 | 25.92 | 12.94 | -17.41 | 636,222.91 |
| mcap5001to10000 | v1 | research | off | 61.96 | 28.67 | 12.94 | -34.21 | 0.00 |
| mcap5001to10000 | v2 | research | off | 39.07 | 28.67 | 12.94 | -20.86 | 0.00 |
| mcap5001to10000 | v3 | research | off | 54.06 | 28.67 | 12.94 | -38.53 | 0.00 |
| mcap5001to10000 | v4 | research | off | 38.27 | 28.67 | 12.94 | -24.63 | 0.00 |
| mcap5001to10000 | v1 | research | on | 52.59 | 28.67 | 12.94 | -34.20 | 5,575,227.17 |
| mcap5001to10000 | v2 | research | on | 32.74 | 28.67 | 12.94 | -20.85 | 1,779,953.73 |
| mcap5001to10000 | v3 | research | on | 46.65 | 28.67 | 12.94 | -42.18 | 3,951,270.20 |
| mcap5001to10000 | v4 | research | on | 32.30 | 28.67 | 12.94 | -24.65 | 1,647,520.14 |
| mcap5001to10000 | v1 | tradeable | off | 53.42 | 28.67 | 12.94 | -31.11 | 0.00 |
| mcap5001to10000 | v2 | tradeable | off | 35.51 | 28.67 | 12.94 | -20.00 | 0.00 |
| mcap5001to10000 | v3 | tradeable | off | 52.22 | 28.67 | 12.94 | -33.06 | 0.00 |
| mcap5001to10000 | v4 | tradeable | off | 35.92 | 28.67 | 12.94 | -21.65 | 0.00 |
| mcap5001to10000 | v1 | tradeable | on | 46.81 | 28.67 | 12.94 | -31.11 | 3,969,447.28 |
| mcap5001to10000 | v2 | tradeable | on | 30.30 | 28.67 | 12.94 | -19.96 | 1,498,716.31 |
| mcap5001to10000 | v3 | tradeable | on | 45.59 | 28.67 | 12.94 | -35.82 | 3,501,137.11 |
| mcap5001to10000 | v4 | tradeable | on | 30.60 | 28.67 | 12.94 | -22.35 | 1,462,360.92 |
| mcapover10000 | v1 | research | off | 48.71 | 25.29 | 12.94 | -32.59 | 0.00 |
| mcapover10000 | v2 | research | off | 32.77 | 25.29 | 12.94 | -18.59 | 0.00 |
| mcapover10000 | v3 | research | off | 53.22 | 25.29 | 12.94 | -35.21 | 0.00 |
| mcapover10000 | v4 | research | off | 34.87 | 25.29 | 12.94 | -22.05 | 0.00 |
| mcapover10000 | v1 | research | on | 41.05 | 25.29 | 12.94 | -32.57 | 2,561,541.15 |
| mcapover10000 | v2 | research | on | 27.66 | 25.29 | 12.94 | -18.59 | 1,108,753.82 |
| mcapover10000 | v3 | research | on | 44.94 | 25.29 | 12.94 | -35.34 | 3,172,371.00 |
| mcapover10000 | v4 | research | on | 29.62 | 25.29 | 12.94 | -22.10 | 1,263,059.76 |
| mcapover10000 | v1 | tradeable | off | 48.44 | 25.29 | 12.94 | -32.58 | 0.00 |
| mcapover10000 | v2 | tradeable | off | 32.75 | 25.29 | 12.94 | -18.59 | 0.00 |
| mcapover10000 | v3 | tradeable | off | 53.19 | 25.29 | 12.94 | -35.66 | 0.00 |
| mcapover10000 | v4 | tradeable | off | 34.82 | 25.29 | 12.94 | -22.29 | 0.00 |
| mcapover10000 | v1 | tradeable | on | 40.92 | 25.29 | 12.94 | -32.59 | 2,540,468.25 |
| mcapover10000 | v2 | tradeable | on | 27.65 | 25.29 | 12.94 | -18.59 | 1,107,937.76 |
| mcapover10000 | v3 | tradeable | on | 44.81 | 25.29 | 12.94 | -35.73 | 3,151,393.61 |
| mcapover10000 | v4 | tradeable | on | 29.58 | 25.29 | 12.94 | -22.29 | 1,259,998.15 |

### Read these first

- **The supplier's data delivery of 2026-10-10 replaced the prices, and every cell was
  republished.** The current figures are in "Republished 2026-10-10" below. Every
  figure in the sections after it was computed on earlier data and is left as
  written. The delivery only removed rows: holiday rows the calendar already
  dropped, and four calendar sessions that no file has a row for. Three of them
  (2016-07-06, 2017-04-04, 2017-12-02) are in the model's training history and
  feature windows, so the scores differ from the first rebalance of 2019. The fourth,
  2020-01-07, is inside the window, so every rebalance after it also falls one
  session later (KNOWN_ISSUES.md). Together they moved the tax-on CAGR of the 32 research cells by
  2.63 points on average in either direction (range -11.29 to +4.89) and changed
  the sign of the gap against the investable buy & hold in 2 of them (nifty50 v1
  and nifty100 v1, from positive to negative).
- **Every current figure is one draw (n=1).** No noise draw has been made on the
  2026-10-10 data. The pre-registered noise test and every n=10 spread further
  down were measured on earlier data. Figures of this kind have moved by more than
  12 CAGR points under changes that are not strategy changes: the 2026-09-27
  cleaning touched 0.4% to 0.5% of rows, and the 2026-10-10 delivery removed four
  sessions, one of them inside the window.
- **midcap150's edge is no longer carried by one name.** On the 2026-10-10 data
  midcap150 v2 beats its own buy & hold by +8.80 CAGR points (tax off, reference buy
  & hold). No single removal of its 148 names and none of 200 random 8-name removals
  makes that negative; the largest single drop is 1.79 points (SUZLON). On the
  uncleaned prices of 2026-09-25 the edge was +3.32 and removing TATAELXSI cut it to
  +0.07. Records: `diagnostics/jackknife_midcap150_20261010.txt` and
  `diagnostics/jackknife_midcap150_20260925.txt`.
- **The investable buy & hold pays no tax in the headline** because it never
  sells. That is what holding and never trading earns. The "sold on the last day"
  column prices the alternative: everything sold on 2026-05-29, with sell charges
  and capital-gains tax.
- **The after-tax noise test on the cleaned prices, 2026-09-29, on the previous data
  delivery**
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

<!-- tax-on tables: written by tools/readme_tax_tables.py; do not edit by hand -->

### Republished 2026-10-14 on the corrected tax ledger: every tax-on figure

The tax ledger now follows the Income-tax Act in four places it did not before: the 4% cess, a short-term loss set off against long-term gains within a year, loss carry-forward for 8 years, and a holding period of more than twelve calendar months (KNOWN_ISSUES.md, "The tax rules since 2026-10-14"). Every tax-on figure below is on those rules; every tax-off figure is unchanged. Old against new for every cell is in diagnostics/tax_ledger_fix_20261014.csv and experiments/EXPERIMENTS.md. Cadence 20, one run per cell (n=1). The investable buy & hold is whole shares of every name bought at the first open and held, taxed; gap is the tax-on headline CAGR minus it. microcap250's pit window starts 2021-10-29.

**static, research profile**

| universe | arm | tax off: CAGR% | MaxDD% | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | investable buy & hold, taxed: CAGR% | gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| midcap150 | v1 | 45.28 | -33.32 | 37.55 | -33.32 | 1.55 | 37.69 | 23.55 | +14.00 |
| midcap150 | v2 | 33.74 | -17.64 | 28.75 | -17.79 | 1.81 | 28.77 | 23.55 | +5.20 |
| midcap150 | v3 | 42.64 | -41.01 | 36.26 | -41.01 | 1.37 | 36.30 | 23.55 | +12.71 |
| midcap150 | v4 | 37.10 | -20.18 | 31.84 | -20.92 | 1.74 | 31.82 | 23.55 | +8.29 |
| nifty100 | v1 | 26.55 | -32.23 | 22.39 | -32.23 | 1.13 | 22.47 | 23.38 | -0.99 |
| nifty100 | v2 | 21.82 | -19.33 | 18.37 | -19.57 | 1.42 | 18.46 | 23.38 | -5.01 |
| nifty100 | v3 | 31.50 | -37.34 | 26.69 | -37.31 | 1.13 | 26.71 | 23.38 | +3.31 |
| nifty100 | v4 | 27.07 | -20.15 | 23.10 | -20.30 | 1.45 | 23.16 | 23.38 | -0.28 |
| nifty50 | v1 | 20.90 | -36.02 | 17.68 | -36.02 | 0.98 | 17.87 | 19.62 | -1.94 |
| nifty50 | v2 | 14.65 | -20.03 | 12.20 | -20.32 | 1.00 | 12.39 | 19.62 | -7.42 |
| nifty50 | v3 | 23.26 | -33.84 | 20.27 | -33.84 | 1.00 | 20.38 | 19.62 | +0.65 |
| nifty50 | v4 | 16.72 | -19.33 | 14.04 | -21.17 | 1.00 | 14.23 | 19.62 | -5.58 |
| midcap50 | v1 | 36.27 | -34.34 | 31.49 | -34.36 | 1.46 | 31.71 | 25.97 | +5.52 |
| midcap50 | v2 | 27.29 | -24.22 | 23.55 | -25.17 | 1.56 | 23.71 | 25.97 | -2.42 |
| midcap50 | v3 | 33.55 | -35.60 | 29.81 | -35.63 | 1.31 | 29.98 | 25.97 | +3.84 |
| midcap50 | v4 | 25.53 | -25.77 | 22.15 | -25.78 | 1.35 | 22.30 | 25.97 | -3.82 |
| midcap100 | v1 | 35.68 | -36.48 | 30.36 | -36.45 | 1.34 | 30.43 | 24.48 | +5.88 |
| midcap100 | v2 | 25.04 | -27.33 | 21.32 | -27.33 | 1.41 | 21.34 | 24.48 | -3.16 |
| midcap100 | v3 | 34.67 | -50.19 | 29.40 | -50.33 | 1.16 | 29.37 | 24.48 | +4.92 |
| midcap100 | v4 | 26.21 | -37.46 | 22.43 | -37.47 | 1.25 | 22.40 | 24.48 | -2.05 |
| nifty200 | v1 | 42.98 | -34.61 | 36.80 | -34.59 | 1.57 | 37.10 | 23.69 | +13.11 |
| nifty200 | v2 | 32.48 | -24.70 | 27.40 | -24.71 | 1.80 | 27.60 | 23.69 | +3.71 |
| nifty200 | v3 | 42.77 | -37.80 | 36.50 | -38.58 | 1.39 | 36.75 | 23.69 | +12.81 |
| nifty200 | v4 | 38.74 | -26.94 | 32.93 | -27.45 | 1.79 | 33.12 | 23.69 | +9.24 |
| smallcap250 | v1 | 37.00 | -43.70 | 31.08 | -43.74 | 1.34 | 31.03 | 26.60 | +4.48 |
| smallcap250 | v2 | 24.35 | -25.01 | 20.63 | -24.99 | 1.47 | 20.54 | 26.60 | -5.97 |
| smallcap250 | v3 | 51.09 | -37.21 | 43.99 | -37.39 | 1.66 | 43.46 | 26.60 | +17.39 |
| smallcap250 | v4 | 27.87 | -33.49 | 23.66 | -33.51 | 1.48 | 23.43 | 26.60 | -2.94 |
| nifty500 | v1 | 37.97 | -45.24 | 33.10 | -45.30 | 1.37 | 33.05 | 24.43 | +8.67 |
| nifty500 | v2 | 26.14 | -28.70 | 22.43 | -28.72 | 1.51 | 22.38 | 24.43 | -2.00 |
| nifty500 | v3 | 39.36 | -59.74 | 34.44 | -59.82 | 1.26 | 34.32 | 24.43 | +10.01 |
| nifty500 | v4 | 29.66 | -36.55 | 25.61 | -36.60 | 1.52 | 25.60 | 24.43 | +1.18 |
| microcap250 | v1 | 53.07 | -42.45 | 43.30 | -42.47 | 1.71 | 43.40 | 33.37 | +9.93 |
| microcap250 | v2 | 32.11 | -22.63 | 26.90 | -22.63 | 1.81 | 26.87 | 33.37 | -6.47 |
| microcap250 | v3 | 67.11 | -40.97 | 55.53 | -40.99 | 1.85 | 55.68 | 33.37 | +22.16 |
| microcap250 | v4 | 39.41 | -20.61 | 33.08 | -22.40 | 1.85 | 33.13 | 33.37 | -0.29 |
| mcap1500to5000 | v1 | 46.19 | -42.64 | 37.69 | -42.64 | 1.51 | 37.77 | 31.33 | +6.36 |
| mcap1500to5000 | v2 | 28.21 | -17.32 | 23.60 | -17.40 | 1.72 | 23.36 | 31.33 | -7.73 |
| mcap1500to5000 | v3 | 53.54 | -49.14 | 45.37 | -49.14 | 1.58 | 45.32 | 31.33 | +14.04 |
| mcap1500to5000 | v4 | 33.79 | -21.04 | 28.32 | -21.04 | 1.77 | 28.14 | 31.33 | -3.01 |
| mcap5001to10000 | v1 | 61.96 | -34.21 | 52.59 | -34.20 | 2.04 | 53.02 | 33.52 | +19.07 |
| mcap5001to10000 | v2 | 39.07 | -20.86 | 32.74 | -20.85 | 2.10 | 33.05 | 33.52 | -0.78 |
| mcap5001to10000 | v3 | 54.06 | -38.53 | 46.65 | -42.18 | 1.67 | 46.79 | 33.52 | +13.13 |
| mcap5001to10000 | v4 | 38.27 | -24.63 | 32.30 | -24.65 | 1.87 | 32.53 | 33.52 | -1.22 |
| mcapover10000 | v1 | 48.71 | -32.59 | 41.05 | -32.57 | 1.70 | 41.01 | 24.04 | +17.01 |
| mcapover10000 | v2 | 32.77 | -18.59 | 27.66 | -18.59 | 1.87 | 27.73 | 24.04 | +3.62 |
| mcapover10000 | v3 | 53.22 | -35.21 | 44.94 | -35.34 | 1.63 | 44.69 | 24.04 | +20.90 |
| mcapover10000 | v4 | 34.87 | -22.05 | 29.62 | -22.10 | 1.76 | 29.67 | 24.04 | +5.58 |

**static, tradeable profile**

| universe | arm | tax off: CAGR% | MaxDD% | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | investable buy & hold, taxed: CAGR% | gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| midcap150 | v1 | 45.28 | -33.32 | 37.55 | -33.32 | 1.55 | 37.69 | 23.55 | +14.00 |
| midcap150 | v2 | 33.74 | -17.64 | 28.75 | -17.79 | 1.81 | 28.77 | 23.55 | +5.20 |
| midcap150 | v3 | 42.64 | -41.01 | 36.26 | -41.01 | 1.37 | 36.30 | 23.55 | +12.71 |
| midcap150 | v4 | 37.10 | -20.18 | 31.84 | -20.92 | 1.74 | 31.82 | 23.55 | +8.29 |
| nifty100 | v1 | 26.77 | -32.24 | 22.56 | -32.24 | 1.14 | 22.64 | 23.38 | -0.82 |
| nifty100 | v2 | 21.82 | -19.33 | 18.37 | -19.57 | 1.42 | 18.46 | 23.38 | -5.01 |
| nifty100 | v3 | 31.50 | -37.34 | 26.69 | -37.31 | 1.13 | 26.71 | 23.38 | +3.31 |
| nifty100 | v4 | 27.07 | -20.15 | 23.10 | -20.30 | 1.45 | 23.16 | 23.38 | -0.28 |
| nifty50 | v1 | 20.90 | -36.02 | 17.68 | -36.02 | 0.98 | 17.87 | 19.62 | -1.94 |
| nifty50 | v2 | 14.65 | -20.03 | 12.20 | -20.32 | 1.00 | 12.39 | 19.62 | -7.42 |
| nifty50 | v3 | 23.26 | -33.84 | 20.27 | -33.84 | 1.00 | 20.38 | 19.62 | +0.65 |
| nifty50 | v4 | 16.72 | -19.33 | 14.04 | -21.17 | 1.00 | 14.23 | 19.62 | -5.58 |
| midcap50 | v1 | 36.22 | -34.37 | 31.48 | -34.37 | 1.46 | 31.69 | 25.97 | +5.51 |
| midcap50 | v2 | 27.29 | -24.22 | 23.55 | -25.17 | 1.56 | 23.71 | 25.97 | -2.42 |
| midcap50 | v3 | 33.52 | -35.63 | 30.56 | -35.60 | 1.33 | 30.73 | 25.97 | +4.59 |
| midcap50 | v4 | 25.53 | -25.77 | 22.15 | -25.78 | 1.35 | 22.30 | 25.97 | -3.82 |
| midcap100 | v1 | 35.66 | -36.45 | 30.34 | -36.44 | 1.34 | 30.42 | 24.48 | +5.86 |
| midcap100 | v2 | 25.04 | -27.33 | 21.32 | -27.33 | 1.41 | 21.34 | 24.48 | -3.16 |
| midcap100 | v3 | 34.62 | -50.04 | 29.37 | -50.20 | 1.16 | 29.34 | 24.48 | +4.89 |
| midcap100 | v4 | 26.21 | -37.46 | 22.43 | -37.47 | 1.25 | 22.40 | 24.48 | -2.05 |
| nifty200 | v1 | 42.98 | -34.61 | 36.80 | -34.59 | 1.57 | 37.10 | 23.69 | +13.11 |
| nifty200 | v2 | 32.48 | -24.70 | 27.40 | -24.71 | 1.80 | 27.60 | 23.69 | +3.71 |
| nifty200 | v3 | 42.77 | -37.80 | 36.50 | -38.58 | 1.39 | 36.75 | 23.69 | +12.81 |
| nifty200 | v4 | 38.74 | -26.94 | 32.93 | -27.45 | 1.79 | 33.12 | 23.69 | +9.24 |
| smallcap250 | v1 | 36.29 | -43.71 | 30.52 | -43.63 | 1.32 | 30.47 | 26.60 | +3.92 |
| smallcap250 | v2 | 24.35 | -25.01 | 20.63 | -24.99 | 1.47 | 20.54 | 26.60 | -5.97 |
| smallcap250 | v3 | 48.01 | -37.19 | 41.16 | -37.40 | 1.57 | 40.64 | 26.60 | +14.56 |
| smallcap250 | v4 | 27.87 | -33.49 | 23.66 | -33.51 | 1.48 | 23.43 | 26.60 | -2.94 |
| nifty500 | v1 | 37.79 | -45.61 | 32.94 | -45.65 | 1.36 | 32.89 | 24.43 | +8.51 |
| nifty500 | v2 | 26.14 | -28.70 | 22.43 | -28.72 | 1.51 | 22.38 | 24.43 | -2.00 |
| nifty500 | v3 | 39.64 | -59.74 | 34.69 | -59.82 | 1.26 | 34.57 | 24.43 | +10.26 |
| nifty500 | v4 | 29.66 | -36.55 | 25.61 | -36.60 | 1.52 | 25.60 | 24.43 | +1.18 |
| microcap250 | v1 | 52.40 | -39.26 | 43.20 | -39.28 | 1.73 | 43.30 | 33.37 | +9.83 |
| microcap250 | v2 | 32.26 | -21.73 | 27.19 | -21.73 | 1.83 | 27.17 | 33.37 | -6.18 |
| microcap250 | v3 | 62.32 | -45.44 | 54.51 | -45.43 | 1.83 | 54.66 | 33.37 | +21.14 |
| microcap250 | v4 | 39.45 | -20.64 | 33.13 | -22.41 | 1.85 | 33.18 | 33.37 | -0.24 |
| mcap1500to5000 | v1 | 41.62 | -41.45 | 34.90 | -41.45 | 1.48 | 34.44 | 31.33 | +3.57 |
| mcap1500to5000 | v2 | 22.15 | -17.48 | 18.89 | -17.48 | 1.53 | 18.62 | 31.33 | -12.44 |
| mcap1500to5000 | v3 | 48.61 | -42.72 | 41.13 | -42.72 | 1.61 | 40.69 | 31.33 | +9.80 |
| mcap1500to5000 | v4 | 25.46 | -17.41 | 21.62 | -17.41 | 1.60 | 21.41 | 31.33 | -9.71 |
| mcap5001to10000 | v1 | 53.42 | -31.11 | 46.81 | -31.11 | 1.89 | 47.23 | 33.52 | +13.29 |
| mcap5001to10000 | v2 | 35.51 | -20.00 | 30.30 | -19.96 | 2.01 | 30.60 | 33.52 | -3.22 |
| mcap5001to10000 | v3 | 52.22 | -33.06 | 45.59 | -35.82 | 1.68 | 45.94 | 33.52 | +12.07 |
| mcap5001to10000 | v4 | 35.92 | -21.65 | 30.60 | -22.35 | 1.84 | 30.82 | 33.52 | -2.92 |
| mcapover10000 | v1 | 48.44 | -32.58 | 40.92 | -32.59 | 1.70 | 40.87 | 24.04 | +16.88 |
| mcapover10000 | v2 | 32.75 | -18.59 | 27.65 | -18.59 | 1.87 | 27.73 | 24.04 | +3.61 |
| mcapover10000 | v3 | 53.19 | -35.66 | 44.81 | -35.73 | 1.62 | 44.56 | 24.04 | +20.77 |
| mcapover10000 | v4 | 34.82 | -22.29 | 29.58 | -22.29 | 1.76 | 29.64 | 24.04 | +5.54 |

**pit, research profile**

| universe | arm | tax off: CAGR% | MaxDD% | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | investable buy & hold, taxed: CAGR% | gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| midcap150 | v1 | 33.03 | -38.01 | 28.19 | -38.15 | 1.26 | 28.21 | 20.50 | +7.69 |
| midcap150 | v2 | 23.30 | -15.02 | 19.61 | -17.65 | 1.36 | 19.70 | 20.50 | -0.89 |
| midcap150 | v3 | 35.86 | -45.44 | 30.38 | -45.67 | 1.20 | 30.36 | 20.50 | +9.88 |
| midcap150 | v4 | 24.80 | -20.19 | 21.02 | -20.25 | 1.29 | 21.01 | 20.50 | +0.52 |
| nifty100 | v1 | 25.72 | -32.36 | 21.68 | -32.34 | 1.20 | 21.77 | 18.97 | +2.71 |
| nifty100 | v2 | 14.31 | -15.84 | 12.09 | -16.41 | 1.10 | 12.20 | 18.97 | -6.88 |
| nifty100 | v3 | 26.50 | -30.44 | 22.15 | -30.44 | 1.10 | 22.16 | 18.97 | +3.18 |
| nifty100 | v4 | 14.29 | -21.25 | 12.19 | -21.23 | 0.96 | 12.23 | 18.97 | -6.78 |
| nifty50 | v1 | 16.66 | -40.58 | 14.40 | -40.61 | 0.83 | 14.60 | 17.24 | -2.84 |
| nifty50 | v2 | 12.84 | -21.47 | 10.69 | -21.48 | 0.96 | 10.81 | 17.24 | -6.55 |
| nifty50 | v3 | 15.72 | -47.56 | 12.76 | -47.56 | 0.69 | 12.85 | 17.24 | -4.48 |
| nifty50 | v4 | 12.09 | -25.54 | 10.04 | -25.57 | 0.83 | 10.12 | 17.24 | -7.20 |
| midcap50 | v1 | 26.61 | -34.86 | 22.05 | -34.84 | 1.15 | 22.33 | 18.72 | +3.33 |
| midcap50 | v2 | 20.69 | -23.27 | 17.43 | -23.27 | 1.35 | 17.62 | 18.72 | -1.29 |
| midcap50 | v3 | 24.48 | -39.93 | 20.59 | -39.93 | 0.98 | 20.92 | 18.72 | +1.87 |
| midcap50 | v4 | 20.94 | -25.28 | 17.66 | -25.28 | 1.21 | 17.90 | 18.72 | -1.06 |
| midcap100 | v1 | 39.47 | -32.75 | 33.09 | -32.75 | 1.42 | 33.33 | 18.78 | +14.31 |
| midcap100 | v2 | 25.09 | -22.02 | 21.01 | -22.02 | 1.39 | 21.15 | 18.78 | +2.23 |
| midcap100 | v3 | 49.28 | -38.01 | 41.77 | -38.04 | 1.53 | 42.01 | 18.78 | +22.99 |
| midcap100 | v4 | 28.72 | -24.56 | 24.14 | -24.56 | 1.39 | 24.22 | 18.78 | +5.36 |
| nifty200 | v1 | 37.57 | -32.13 | 32.22 | -32.13 | 1.38 | 32.28 | 18.57 | +13.65 |
| nifty200 | v2 | 26.23 | -19.25 | 22.33 | -19.25 | 1.48 | 22.39 | 18.57 | +3.76 |
| nifty200 | v3 | 42.95 | -32.91 | 36.95 | -32.91 | 1.37 | 37.03 | 18.57 | +18.38 |
| nifty200 | v4 | 26.04 | -21.71 | 22.31 | -21.71 | 1.25 | 22.40 | 18.57 | +3.74 |
| smallcap250 | v1 | 44.68 | -41.88 | 38.27 | -41.88 | 1.52 | 38.16 | 23.42 | +14.85 |
| smallcap250 | v2 | 26.23 | -26.41 | 22.28 | -26.41 | 1.49 | 22.25 | 23.42 | -1.14 |
| smallcap250 | v3 | 58.32 | -38.52 | 49.99 | -38.52 | 1.77 | 49.78 | 23.42 | +26.57 |
| smallcap250 | v4 | 31.31 | -23.89 | 26.79 | -23.89 | 1.60 | 26.67 | 23.42 | +3.37 |
| nifty500 | v1 | 57.12 | -37.52 | 48.53 | -37.52 | 1.83 | 48.60 | 21.53 | +27.00 |
| nifty500 | v2 | 32.40 | -18.06 | 27.50 | -18.18 | 1.78 | 27.54 | 21.53 | +5.97 |
| nifty500 | v3 | 58.58 | -44.14 | 49.92 | -44.14 | 1.66 | 49.92 | 21.53 | +28.39 |
| nifty500 | v4 | 32.14 | -26.78 | 27.20 | -26.78 | 1.62 | 27.20 | 21.53 | +5.67 |
| microcap250 | v1 | 30.00 | -31.54 | 25.15 | -32.81 | 1.06 | 24.68 | 29.66 | -4.51 |
| microcap250 | v2 | 21.46 | -13.56 | 18.04 | -16.01 | 1.29 | 17.93 | 29.66 | -11.62 |
| microcap250 | v3 | 37.07 | -32.46 | 30.54 | -32.78 | 1.16 | 30.53 | 29.66 | +0.88 |
| microcap250 | v4 | 30.07 | -17.93 | 25.17 | -20.09 | 1.46 | 25.21 | 29.66 | -4.49 |
| mcap1500to5000 | v1-v4 | not available: no membership file for this supplier bucket | | | | | | | |
| mcap5001to10000 | v1-v4 | not available: no membership file for this supplier bucket | | | | | | | |
| mcapover10000 | v1-v4 | not available: no membership file for this supplier bucket | | | | | | | |

**pit, tradeable profile**

| universe | arm | tax off: CAGR% | MaxDD% | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | investable buy & hold, taxed: CAGR% | gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| midcap150 | v1 | 33.03 | -38.01 | 28.18 | -38.15 | 1.26 | 28.21 | 20.50 | +7.68 |
| midcap150 | v2 | 23.30 | -15.02 | 19.61 | -17.65 | 1.36 | 19.70 | 20.50 | -0.89 |
| midcap150 | v3 | 35.86 | -45.44 | 30.38 | -45.67 | 1.20 | 30.36 | 20.50 | +9.88 |
| midcap150 | v4 | 24.80 | -20.19 | 21.02 | -20.25 | 1.29 | 21.01 | 20.50 | +0.52 |
| nifty100 | v1 | 25.81 | -32.34 | 21.75 | -32.33 | 1.20 | 21.84 | 18.97 | +2.78 |
| nifty100 | v2 | 14.31 | -15.84 | 12.09 | -16.41 | 1.10 | 12.20 | 18.97 | -6.88 |
| nifty100 | v3 | 26.55 | -30.43 | 22.19 | -30.44 | 1.10 | 22.20 | 18.97 | +3.22 |
| nifty100 | v4 | 14.29 | -21.25 | 12.19 | -21.23 | 0.96 | 12.23 | 18.97 | -6.78 |
| nifty50 | v1 | 16.66 | -40.58 | 14.40 | -40.61 | 0.83 | 14.60 | 17.24 | -2.84 |
| nifty50 | v2 | 12.84 | -21.47 | 10.69 | -21.48 | 0.96 | 10.81 | 17.24 | -6.55 |
| nifty50 | v3 | 15.72 | -47.56 | 12.76 | -47.56 | 0.69 | 12.85 | 17.24 | -4.48 |
| nifty50 | v4 | 12.09 | -25.54 | 10.04 | -25.57 | 0.83 | 10.12 | 17.24 | -7.20 |
| midcap50 | v1 | 26.61 | -34.86 | 22.05 | -34.84 | 1.15 | 22.33 | 18.72 | +3.33 |
| midcap50 | v2 | 20.69 | -23.27 | 17.43 | -23.27 | 1.35 | 17.62 | 18.72 | -1.29 |
| midcap50 | v3 | 24.48 | -39.93 | 20.59 | -39.93 | 0.98 | 20.92 | 18.72 | +1.87 |
| midcap50 | v4 | 20.94 | -25.28 | 17.66 | -25.28 | 1.21 | 17.90 | 18.72 | -1.06 |
| midcap100 | v1 | 39.47 | -32.75 | 33.09 | -32.75 | 1.42 | 33.33 | 18.78 | +14.31 |
| midcap100 | v2 | 25.09 | -22.02 | 21.01 | -22.02 | 1.39 | 21.15 | 18.78 | +2.23 |
| midcap100 | v3 | 49.28 | -38.01 | 41.77 | -38.04 | 1.53 | 42.01 | 18.78 | +22.99 |
| midcap100 | v4 | 28.72 | -24.56 | 24.14 | -24.56 | 1.39 | 24.22 | 18.78 | +5.36 |
| nifty200 | v1 | 37.57 | -32.13 | 32.22 | -32.13 | 1.38 | 32.28 | 18.57 | +13.65 |
| nifty200 | v2 | 26.23 | -19.25 | 22.33 | -19.25 | 1.48 | 22.39 | 18.57 | +3.76 |
| nifty200 | v3 | 42.95 | -32.91 | 36.95 | -32.91 | 1.37 | 37.03 | 18.57 | +18.38 |
| nifty200 | v4 | 26.04 | -21.71 | 22.31 | -21.71 | 1.25 | 22.40 | 18.57 | +3.74 |
| smallcap250 | v1 | 46.35 | -42.41 | 38.32 | -42.41 | 1.52 | 38.22 | 23.42 | +14.90 |
| smallcap250 | v2 | 26.23 | -26.41 | 22.28 | -26.41 | 1.49 | 22.25 | 23.42 | -1.14 |
| smallcap250 | v3 | 58.54 | -38.76 | 49.88 | -38.76 | 1.77 | 49.67 | 23.42 | +26.46 |
| smallcap250 | v4 | 31.32 | -23.89 | 26.80 | -23.89 | 1.60 | 26.67 | 23.42 | +3.38 |
| nifty500 | v1 | 55.29 | -37.51 | 48.56 | -37.51 | 1.83 | 48.63 | 21.53 | +27.03 |
| nifty500 | v2 | 32.40 | -18.06 | 27.50 | -18.18 | 1.78 | 27.54 | 21.53 | +5.97 |
| nifty500 | v3 | 59.31 | -44.08 | 50.46 | -44.08 | 1.68 | 50.46 | 21.53 | +28.93 |
| nifty500 | v4 | 32.14 | -26.78 | 27.20 | -26.78 | 1.62 | 27.20 | 21.53 | +5.67 |
| microcap250 | v1 | 30.00 | -31.54 | 25.15 | -32.81 | 1.06 | 24.68 | 29.66 | -4.51 |
| microcap250 | v2 | 21.46 | -13.56 | 18.04 | -16.01 | 1.29 | 17.93 | 29.66 | -11.62 |
| microcap250 | v3 | 37.08 | -32.46 | 30.54 | -32.80 | 1.16 | 30.53 | 29.66 | +0.88 |
| microcap250 | v4 | 30.07 | -17.93 | 25.17 | -20.09 | 1.46 | 25.21 | 29.66 | -4.49 |
| mcap1500to5000 | v1-v4 | not available: no membership file for this supplier bucket | | | | | | | |
| mcap5001to10000 | v1-v4 | not available: no membership file for this supplier bucket | | | | | | | |
| mcapover10000 | v1-v4 | not available: no membership file for this supplier bucket | | | | | | | |

<!-- end of tax-on tables -->

### SUPERSEDED 2026-10-14 for its tax-on figures (tax-off figures still current) -- Republished 2026-10-10 on the supplier's new data delivery: every universe, arm and profile

Window 2019-01-01 to 2026-05-29, 1,835 trading days (the delivery has no row for
2020-01-07; see KNOWN_ISSUES.md), from Rs 10,00,000, all figures after costs, cadence
20, with the adj_close/close cleaning of `experiments/DATA_CLEANING_SPEC.txt`. Produced
by four runs of 2026-10-10 (research and tradeable, tax off and on;
`runs/20261010T015553_all_all_r20`, `20261010T050655`, `20261010T052337` and
`20261010T053852`, not tracked). Every figure is in `diagnostics/cells_20261010.csv`,
`diagnostics/tax_on_all_arms.csv` and `diagnostics/tradeable_tax_all_arms.csv`, and the
change against the previous delivery is in `diagnostics/cells_prev_vs_20261010.csv`.
Every figure is one run (n=1); no noise draw has been made on this data. Tax on,
headline and sold on the last day, are as defined in the 2026-09-25 section below.
microcap250, added with this delivery, is reported separately at the end of this
section: it was rerun after PRIVISCL was removed.

`research` profile:

| universe | arm | tax off: CAGR% | MaxDD% | Sharpe | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| nifty50 | v1 | 20.90 | -36.02 | 1.14 | 17.79 | -36.02 | 0.98 | 17.89 | n=1 |
| nifty50 | v2 | 14.65 | -20.03 | 1.21 | 12.29 | -20.24 | 1.01 | 12.47 | n=1 |
| nifty50 | v3 | 23.26 | -33.84 | 1.13 | 20.39 | -33.83 | 1.01 | 20.50 | n=1 |
| nifty50 | v4 | 16.72 | -19.33 | 1.18 | 14.15 | -21.09 | 1.00 | 14.34 | n=1 |
| nifty100 | v1 | 26.55 | -32.23 | 1.32 | 22.35 | -32.23 | 1.13 | 22.43 | n=1 |
| nifty100 | v2 | 21.82 | -19.33 | 1.70 | 18.49 | -19.58 | 1.43 | 18.59 | n=1 |
| nifty100 | v3 | 31.50 | -37.34 | 1.30 | 26.44 | -37.33 | 1.12 | 26.47 | n=1 |
| nifty100 | v4 | 27.07 | -20.15 | 1.71 | 23.26 | -20.30 | 1.46 | 23.32 | n=1 |
| nifty200 | v1 | 42.98 | -34.61 | 1.81 | 36.92 | -34.60 | 1.57 | 37.22 | n=1 |
| nifty200 | v2 | 32.48 | -24.70 | 2.16 | 27.51 | -24.71 | 1.81 | 27.71 | n=1 |
| nifty200 | v3 | 42.77 | -37.80 | 1.60 | 36.15 | -38.54 | 1.38 | 36.40 | n=1 |
| nifty200 | v4 | 38.74 | -26.94 | 2.10 | 32.92 | -27.44 | 1.79 | 33.12 | n=1 |
| nifty500 | v1 | 37.97 | -45.24 | 1.57 | 32.89 | -45.29 | 1.36 | 32.84 | n=1 |
| nifty500 | v2 | 26.14 | -28.70 | 1.78 | 22.23 | -28.72 | 1.49 | 22.17 | n=1 |
| nifty500 | v3 | 39.36 | -59.74 | 1.41 | 33.92 | -59.83 | 1.24 | 33.80 | n=1 |
| nifty500 | v4 | 29.66 | -36.55 | 1.79 | 25.30 | -36.60 | 1.50 | 25.29 | n=1 |
| midcap50 | v1 | 36.27 | -34.34 | 1.67 | 31.69 | -34.35 | 1.47 | 31.91 | n=1 |
| midcap50 | v2 | 27.29 | -24.22 | 1.83 | 23.70 | -25.10 | 1.58 | 23.86 | n=1 |
| midcap50 | v3 | 33.55 | -35.60 | 1.46 | 29.92 | -35.63 | 1.32 | 30.10 | n=1 |
| midcap50 | v4 | 25.53 | -25.77 | 1.56 | 22.27 | -25.77 | 1.36 | 22.42 | n=1 |
| midcap100 | v1 | 35.68 | -36.48 | 1.56 | 30.42 | -36.45 | 1.34 | 30.50 | n=1 |
| midcap100 | v2 | 25.04 | -27.33 | 1.66 | 21.28 | -27.33 | 1.41 | 21.31 | n=1 |
| midcap100 | v3 | 34.67 | -50.19 | 1.34 | 29.06 | -50.32 | 1.15 | 29.04 | n=1 |
| midcap100 | v4 | 26.21 | -37.46 | 1.45 | 22.23 | -37.47 | 1.24 | 22.21 | n=1 |
| midcap150 | v1 | 45.28 | -33.32 | 1.85 | 37.70 | -33.32 | 1.56 | 37.84 | n=1 |
| midcap150 | v2 | 33.74 | -17.64 | 2.17 | 28.92 | -18.06 | 1.83 | 28.95 | n=1 |
| midcap150 | v3 | 42.64 | -41.01 | 1.58 | 35.95 | -41.01 | 1.36 | 35.99 | n=1 |
| midcap150 | v4 | 37.10 | -20.18 | 2.05 | 31.94 | -20.79 | 1.74 | 31.92 | n=1 |
| smallcap250 | v1 | 37.00 | -43.70 | 1.57 | 30.99 | -43.73 | 1.33 | 30.95 | n=1 |
| smallcap250 | v2 | 24.35 | -25.01 | 1.77 | 20.53 | -25.00 | 1.46 | 20.45 | n=1 |
| smallcap250 | v3 | 51.09 | -37.21 | 1.90 | 44.13 | -37.27 | 1.66 | 43.62 | n=1 |
| smallcap250 | v4 | 27.87 | -33.49 | 1.76 | 23.55 | -33.51 | 1.47 | 23.33 | n=1 |

Buy & hold, the same for every arm of a universe. The investable buy & hold did not
move: it buys at the first session's open and is valued at the last session's close,
and neither changed. The reference index moved by -0.007 to +0.001 points. The
previous table also gave the investable basket's MaxDD; no tracked script writes it,
so it is not given here.

| universe | buy & hold, reference (untaxed, daily-rebalanced index): CAGR% | MaxDD% | buy & hold, investable (held lots), taxed, headline: CAGR% | held lots, sold on the last day: CAGR% | v2 tax on headline minus investable headline | v2 sold on the last day minus held lots sold on the last day |
|---|---:|---:|---:|---:|---:|---:|
| nifty50 | 20.45 | -37.31 | 19.62 | 18.35 | -7.33 | -5.88 |
| nifty100 | 23.91 | -37.40 | 23.38 | 21.97 | -4.89 | -3.38 |
| nifty200 | 25.12 | -38.03 | 23.69 | 22.27 | +3.82 | +5.44 |
| nifty500 | 25.60 | -41.56 | 24.43 | 22.91 | -2.20 | -0.74 |
| midcap50 | 23.72 | -37.92 | 25.97 | 24.51 | -2.28 | -0.65 |
| midcap100 | 26.25 | -38.89 | 24.48 | 23.04 | -3.19 | -1.74 |
| midcap150 | 24.94 | -37.67 | 23.55 | 22.16 | +5.37 | +6.79 |
| smallcap250 | 26.56 | -48.95 | 26.60 | 24.95 | -6.06 | -4.50 |

All four arms against the investable taxed buy & hold, tax-on headline minus investable
headline, CAGR points (`diagnostics/tax_on_all_arms.csv`, full precision):

| universe | investable buy & hold | v1 gap | v2 gap | v3 gap | v4 gap |
|---|---:|---:|---:|---:|---:|
| nifty50 | 19.62 | -1.83 | -7.33 | +0.77 | -5.47 |
| nifty100 | 23.38 | -1.03 | -4.89 | +3.06 | -0.12 |
| nifty200 | 23.69 | +13.23 | +3.82 | +12.46 | +9.24 |
| nifty500 | 24.43 | +8.46 | -2.20 | +9.49 | +0.87 |
| midcap50 | 25.97 | +5.72 | -2.28 | +3.95 | -3.70 |
| midcap100 | 24.48 | +5.94 | -3.19 | +4.59 | -2.24 |
| midcap150 | 23.55 | +14.15 | +5.37 | +12.39 | +8.38 |
| smallcap250 | 26.60 | +4.40 | -6.06 | +17.53 | -3.05 |

`tradeable` profile (participation cap). The cap binds in 9 of 32 cells
(`diagnostics/tradeable_tax_all_arms.csv`), and those are the nine below; in the
other 23 the tradeable figures equal the research ones exactly. All 64 (cell,
profile) rows are in `diagnostics/cells_20261010.csv`. The profile is UNGATED
(`profiles.UNGATED_NOTICE`).

| universe | arm | research, tax off | tradeable, tax off | research, tax on | tradeable, tax on | tradeable, sold on the last day | gap, research | gap, tradeable |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| nifty100 | v1 | 26.55 | 26.77 | 22.35 | 22.47 | 22.56 | -1.03 | -0.91 |
| nifty500 | v1 | 37.97 | 37.79 | 32.89 | 32.72 | 32.67 | +8.46 | +8.29 |
| nifty500 | v3 | 39.36 | 39.64 | 33.92 | 34.15 | 34.03 | +9.49 | +9.73 |
| midcap50 | v1 | 36.27 | 36.22 | 31.69 | 31.66 | 31.88 | +5.72 | +5.69 |
| midcap50 | v3 | 33.55 | 33.52 | 29.92 | 30.68 | 30.86 | +3.95 | +4.71 |
| midcap100 | v1 | 35.68 | 35.66 | 30.42 | 30.40 | 30.48 | +5.94 | +5.92 |
| midcap100 | v3 | 34.67 | 34.62 | 29.06 | 29.01 | 28.99 | +4.59 | +4.53 |
| smallcap250 | v1 | 37.00 | 36.29 | 30.99 | 30.41 | 30.37 | +4.40 | +3.82 |
| smallcap250 | v3 | 51.09 | 48.01 | 44.13 | 41.23 | 40.73 | +17.53 | +14.64 |

**Previous delivery against the new one, research profile, tax on headline** (previous:
the 2026-09-27 figures in the next section; `diagnostics/cells_prev_vs_20261010.csv`
has every column for both profiles). The tax-on CAGR rose in 15 cells and fell in 17,
by 2.63 points on average in either direction (range -11.29 to +4.89). The gap
against the investable buy & hold changed sign in 2 cells under both profiles, both
from positive to negative: nifty50 v1 and nifty100 v1. The data lost four sessions,
three in the training history and one inside the window; moves this size are the
single-draw instability recorded elsewhere in this file, not a change in the
strategy.

| universe | arm | tax-on CAGR old | new | change | gap old | gap new | sign changed |
|---|---|---:|---:|---:|---:|---:|---|
| nifty50 | v1 | 20.16 | 17.79 | -2.37 | +0.54 | -1.83 | **yes** |
| nifty50 | v2 | 13.15 | 12.29 | -0.86 | -6.47 | -7.33 | no |
| nifty50 | v3 | 23.25 | 20.39 | -2.86 | +3.63 | +0.77 | no |
| nifty50 | v4 | 15.80 | 14.15 | -1.64 | -3.82 | -5.47 | no |
| nifty100 | v1 | 23.70 | 22.35 | -1.35 | +0.32 | -1.03 | **yes** |
| nifty100 | v2 | 17.24 | 18.49 | +1.25 | -6.14 | -4.89 | no |
| nifty100 | v3 | 26.15 | 26.44 | +0.29 | +2.77 | +3.06 | no |
| nifty100 | v4 | 18.37 | 23.26 | +4.89 | -5.01 | -0.12 | no |
| nifty200 | v1 | 40.42 | 36.92 | -3.51 | +16.74 | +13.23 | no |
| nifty200 | v2 | 27.64 | 27.51 | -0.13 | +3.95 | +3.82 | no |
| nifty200 | v3 | 41.88 | 36.15 | -5.73 | +18.19 | +12.46 | no |
| nifty200 | v4 | 31.15 | 32.92 | +1.77 | +7.46 | +9.24 | no |
| nifty500 | v1 | 29.61 | 32.89 | +3.28 | +5.18 | +8.46 | no |
| nifty500 | v2 | 23.10 | 22.23 | -0.88 | -1.33 | -2.20 | no |
| nifty500 | v3 | 36.90 | 33.92 | -2.98 | +12.47 | +9.49 | no |
| nifty500 | v4 | 26.43 | 25.30 | -1.12 | +2.00 | +0.87 | no |
| midcap50 | v1 | 29.12 | 31.69 | +2.58 | +3.14 | +5.72 | no |
| midcap50 | v2 | 19.40 | 23.70 | +4.29 | -6.57 | -2.28 | no |
| midcap50 | v3 | 29.93 | 29.92 | -0.01 | +3.95 | +3.95 | no |
| midcap50 | v4 | 20.21 | 22.27 | +2.06 | -5.76 | -3.70 | no |
| midcap100 | v1 | 27.32 | 30.42 | +3.10 | +2.85 | +5.94 | no |
| midcap100 | v2 | 22.19 | 21.28 | -0.91 | -2.29 | -3.19 | no |
| midcap100 | v3 | 26.55 | 29.06 | +2.51 | +2.07 | +4.59 | no |
| midcap100 | v4 | 22.14 | 22.23 | +0.09 | -2.34 | -2.24 | no |
| midcap150 | v1 | 33.89 | 37.70 | +3.81 | +10.34 | +14.15 | no |
| midcap150 | v2 | 24.04 | 28.92 | +4.88 | +0.48 | +5.37 | no |
| midcap150 | v3 | 37.09 | 35.95 | -1.14 | +13.53 | +12.39 | no |
| midcap150 | v4 | 27.92 | 31.94 | +4.01 | +4.37 | +8.38 | no |
| smallcap250 | v1 | 42.29 | 30.99 | -11.29 | +15.69 | +4.40 | no |
| smallcap250 | v2 | 24.21 | 20.53 | -3.67 | -2.39 | -6.06 | no |
| smallcap250 | v3 | 41.55 | 44.13 | +2.58 | +14.95 | +17.53 | no |
| smallcap250 | v4 | 25.87 | 23.55 | -2.32 | -0.73 | -3.05 | no |

**microcap250, rerun 2026-10-10 without PRIVISCL.** PRIVISCL's price file had a
3,336-fold jump on 2020-08-21 that does not revert, so the cleaning rule left it in, and
that day entered the market-level features the model reads. The owner removed PRIVISCL's
price files for bad data, and microcap250 was rerun on its other 241 names: the same
window, cadence and four settings as above, arms v1 to v4. Every figure is one run
(n=1) and is in the same three files.

| arm | tax off: CAGR% | MaxDD% | Sharpe | tax on, headline: CAGR% | MaxDD% | Sharpe | tax on, sold on the last day: CAGR% | n |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| v1 | 53.07 | -42.45 | 2.07 | 43.09 | -42.47 | 1.70 | 43.18 | n=1 |
| v2 | 32.11 | -22.63 | 2.21 | 26.84 | -22.63 | 1.81 | 26.82 | n=1 |
| v3 | 67.11 | -40.97 | 2.20 | 55.54 | -40.99 | 1.85 | 55.70 | n=1 |
| v4 | 39.41 | -20.61 | 2.24 | 33.20 | -22.19 | 1.85 | 33.26 | n=1 |

Buy & hold: reference index 27.89% CAGR, MaxDD -48.60%; investable held lots, taxed,
headline 33.37%, sold on the last day 31.41%. Tax-on headline minus investable headline:
v1 +9.71, v2 -6.53, v3 +22.17, v4 -0.17 points.

`tradeable` profile: the participation cap binds in all four cells (19, 4, 25 and 3
skipped rows for v1 to v4), against 9 of the other 32.

| arm | research, tax off | tradeable, tax off | research, tax on | tradeable, tax on | tradeable, sold on the last day | gap, research | gap, tradeable |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 53.07 | 52.40 | 43.09 | 43.10 | 43.20 | +9.71 | +9.73 |
| v2 | 32.11 | 32.26 | 26.84 | 27.14 | 27.12 | -6.53 | -6.23 |
| v3 | 67.11 | 62.32 | 55.54 | 54.39 | 54.55 | +22.17 | +21.02 |
| v4 | 39.41 | 39.45 | 33.20 | 33.23 | 33.28 | -0.17 | -0.14 |

PRIVISCL's removal took the investable buy & hold from 132.69% to 33.37% and the
reference index from 95.35% to 27.89%. The arms moved less: research tax-on v1 from
52.83% to 43.09%, v3 from 65.31% to 55.54%. microcap250 has no figure on the previous
delivery to compare with. 102 of its 241 names have no row before 2019-01-01 and 83
none before 2021-01-01, so the early part of the window ranks fewer names.

### SUPERSEDED 2026-10-14 for its tax-on figures (tax-off figures still current) -- Point-in-time (pit) results, 2026-10-10: every universe, arm and profile

**smallcap250 and nifty500: every figure in this section, tax off included, is superseded.** They were rerun on 2026-10-17 under the row rule (KNOWN_ISSUES.md, "The engine's tradeability guard read rows dated after the decision day"); the current figures are in the tax-on tables above.

Produced by `run.py --survivorship pit` (four settings per universe: research and
tradeable, tax off and on, arms v1 to v4, cadence 20) and compared with the static runs
above by `results/survivorship_sheet.py pit-compare` (until 2026-10-18
`results/pit_compare.py`); every row, both profiles, is in
`diagnostics/pit_vs_static_20261010.csv`. Every figure is one run (n=1). The static
figures above are unchanged.

**Read every pit figure with these three caveats.**

- **Validator verdict: FAIL on all nine membership files.** Inclusions and exclusions
  disagree with the symbols column, and some excluded names are still listed in the
  same row. The files are used as delivered by the owner's decision of 2026-10-10.
- **Residual survivorship.** Members in the window that have no with-survivorship
  price file could not be held, so some bias remains (count per universe below;
  names in each run's RUN.txt).
- **Look-ahead.** The symbols column reads like today's member list edited backwards
  (the 2018 and 2019 Nifty 50 rows list JIOFIN, listed in 2023, and TRENT, BEL, INDIGO
  and MAXHEALTH, which joined in 2024 and 2025). Used as membership, it makes some later
  members eligible early.

| universe | window | verdict | members with no price file (dropped, current) |
|---|---|---|---|
| nifty50 | 2019-01-01 to 2026-05-29 | FAIL | 1 of 56 (1, 0) |
| nifty100 | 2019-01-01 to 2026-05-29 | FAIL | 3 of 125 (2, 1) |
| nifty200 | 2019-01-01 to 2026-05-29 | FAIL | 10 of 248 (7, 3) |
| nifty500 | 2019-01-01 to 2026-05-29 | FAIL | 39 of 641 (32, 7) |
| midcap50 | 2019-01-01 to 2026-05-29 | FAIL | 5 of 97 (4, 1) |
| midcap100 | 2019-01-01 to 2026-05-29 | FAIL | 9 of 166 (7, 2) |
| midcap150 | 2019-01-01 to 2026-05-29 | FAIL | 17 of 220 (15, 2) |
| smallcap250 | 2019-01-01 to 2026-05-29 | FAIL | 38 of 412 (34, 4) |
| microcap250 | 2021-10-29 to 2026-05-29 | FAIL | 18 of 320 (5, 13) |

microcap250's membership file starts on 2021-10-29, so its pit window starts there,
and its static figures below are the static run's curves cut to that window (not a
run started there). Its with-survivorship prices also come from a different source
(KNOWN_ISSUES.md). For the other eight the windows are the same.

`research` profile. CAGR% and MaxDD%, static -> pit. Buy & hold is the investable
held-lots basket, taxed, headline; in pit it holds the members on the first pit
rebalance. Gap is the tax-on headline CAGR minus that buy & hold. **bold** marks an
arm that beats buy & hold in static but not in pit.

| universe | arm | tax off: CAGR% | tax off: MaxDD% | tax on: CAGR% | pit buy & hold | gap, static | gap, pit |
|---|---|---|---|---|---:|---:|---:|
| nifty50 | v1 | 20.90 -> 16.66 | -36.02 -> -40.58 | 17.79 -> 14.45 | 17.24 | -1.83 | -2.79 |
| nifty50 | v2 | 14.65 -> 12.84 | -20.03 -> -21.47 | 12.29 -> 10.73 | 17.24 | -7.33 | -6.51 |
| **nifty50** | **v3** | 23.26 -> 15.72 | -33.84 -> -47.56 | 20.39 -> 12.16 | 17.24 | +0.77 | **-5.08** |
| nifty50 | v4 | 16.72 -> 12.09 | -19.33 -> -25.54 | 14.15 -> 9.80 | 17.24 | -5.47 | -7.44 |
| nifty100 | v1 | 26.55 -> 25.72 | -32.23 -> -32.36 | 22.35 -> 21.83 | 18.97 | -1.03 | +2.85 |
| nifty100 | v2 | 21.82 -> 14.31 | -19.33 -> -15.84 | 18.49 -> 12.12 | 18.97 | -4.89 | -6.86 |
| nifty100 | v3 | 31.50 -> 26.50 | -37.34 -> -30.44 | 26.44 -> 22.45 | 18.97 | +3.06 | +3.47 |
| nifty100 | v4 | 27.07 -> 14.29 | -20.15 -> -21.25 | 23.26 -> 12.13 | 18.97 | -0.12 | -6.85 |
| nifty200 | v1 | 42.98 -> 37.57 | -34.61 -> -32.13 | 36.92 -> 31.98 | 18.57 | +13.23 | +13.41 |
| nifty200 | v2 | 32.48 -> 26.23 | -24.70 -> -19.25 | 27.51 -> 22.35 | 18.57 | +3.82 | +3.78 |
| nifty200 | v3 | 42.77 -> 42.95 | -37.80 -> -32.91 | 36.15 -> 36.71 | 18.57 | +12.46 | +18.13 |
| nifty200 | v4 | 38.74 -> 26.04 | -26.94 -> -21.71 | 32.92 -> 22.23 | 18.57 | +9.24 | +3.66 |
| nifty500 | v1 | 37.97 -> 57.40 | -45.24 -> -37.52 | 32.89 -> 48.90 | 21.53 | +8.46 | +27.36 |
| nifty500 | v2 | 26.14 -> 32.50 | -28.70 -> -18.06 | 22.23 -> 27.62 | 21.53 | -2.20 | +6.09 |
| nifty500 | v3 | 39.36 -> 58.88 | -59.74 -> -44.14 | 33.92 -> 50.04 | 21.53 | +9.49 | +28.51 |
| nifty500 | v4 | 29.66 -> 32.25 | -36.55 -> -26.78 | 25.30 -> 27.06 | 21.53 | +0.87 | +5.53 |
| midcap50 | v1 | 36.27 -> 26.61 | -34.34 -> -34.86 | 31.69 -> 22.09 | 18.72 | +5.72 | +3.37 |
| midcap50 | v2 | 27.29 -> 20.69 | -24.22 -> -23.27 | 23.70 -> 17.42 | 18.72 | -2.28 | -1.30 |
| midcap50 | v3 | 33.55 -> 24.48 | -35.60 -> -39.93 | 29.92 -> 20.58 | 18.72 | +3.95 | +1.86 |
| midcap50 | v4 | 25.53 -> 20.94 | -25.77 -> -25.28 | 22.27 -> 17.70 | 18.72 | -3.70 | -1.01 |
| midcap100 | v1 | 35.68 -> 39.47 | -36.48 -> -32.75 | 30.42 -> 33.29 | 18.78 | +5.94 | +14.51 |
| midcap100 | v2 | 25.04 -> 25.09 | -27.33 -> -22.02 | 21.28 -> 21.08 | 18.78 | -3.19 | +2.30 |
| midcap100 | v3 | 34.67 -> 49.28 | -50.19 -> -38.01 | 29.06 -> 42.05 | 18.78 | +4.59 | +23.27 |
| midcap100 | v4 | 26.21 -> 28.72 | -37.46 -> -24.56 | 22.23 -> 24.31 | 18.78 | -2.24 | +5.53 |
| midcap150 | v1 | 45.28 -> 33.03 | -33.32 -> -38.01 | 37.70 -> 27.76 | 20.50 | +14.15 | +7.26 |
| **midcap150** | **v2** | 33.74 -> 23.30 | -17.64 -> -15.02 | 28.92 -> 19.61 | 20.50 | +5.37 | **-0.90** |
| midcap150 | v3 | 42.64 -> 35.86 | -41.01 -> -45.44 | 35.95 -> 29.76 | 20.50 | +12.39 | +9.26 |
| midcap150 | v4 | 37.10 -> 24.80 | -20.18 -> -20.19 | 31.94 -> 20.84 | 20.50 | +8.38 | +0.33 |
| smallcap250 | v1 | 37.00 -> 44.90 | -43.70 -> -41.88 | 30.99 -> 38.49 | 23.42 | +4.40 | +15.07 |
| smallcap250 | v2 | 24.35 -> 26.29 | -25.01 -> -26.41 | 20.53 -> 22.22 | 23.42 | -6.06 | -1.21 |
| smallcap250 | v3 | 51.09 -> 58.57 | -37.21 -> -38.52 | 44.13 -> 50.36 | 23.42 | +17.53 | +26.93 |
| smallcap250 | v4 | 27.87 -> 31.39 | -33.49 -> -23.89 | 23.55 -> 26.78 | 23.42 | -3.05 | +3.35 |
| **microcap250** | **v1** | 47.95 -> 30.00 | -25.31 -> -31.54 | 35.44 -> 25.34 | 29.66 | +3.98 | **-4.32** |
| microcap250 | v2 | 32.25 -> 21.46 | -13.57 -> -13.56 | 25.54 -> 18.15 | 29.66 | -5.93 | -11.51 |
| microcap250 | v3 | 57.53 -> 37.07 | -25.91 -> -32.46 | 43.54 -> 30.81 | 29.66 | +12.07 | +1.15 |
| microcap250 | v4 | 37.33 -> 30.07 | -17.07 -> -17.93 | 29.62 -> 25.35 | 29.66 | -1.85 | -4.31 |

`tradeable` profile: the same three cells, nifty50 v3, midcap150 v2 and microcap250 v1,
beat buy & hold in static but not in pit; every tradeable row is in the CSV.

Tax-on pit CAGR is below static in 24 of 36 research cells and above it in 12,
on nifty500 and smallcap250 (all four arms), midcap100 v1, v3 and v4, and nifty200 v3.
On nifty500 v1 (research, tax off), names only the pit universe holds account for
Rs 2.4 lakh of the Rs 2.78 crore profit; the rest comes from names the static universe
also holds, held at different times, since the pit model trains and ranks on
point-in-time members. Why pit is higher on those cells has not been investigated
further.

### SUPERSEDED 2026-10-10, computed on the previous data delivery -- Republished 2026-09-27 on cleaned prices: every universe, arm and profile

> *Superseded 2026-10-10: the supplier's new data delivery moved every figure in this
> section. The current figures are in the section above. Nothing below is changed.
> `diagnostics/tax_on_all_arms.csv` and `tradeable_tax_all_arms.csv` now hold the
> 2026-10-10 figures; the 2026-09-27 versions are in git history
> (`git show 82d1a3c:diagnostics/tax_on_all_arms.csv`). "Current results" is now "The
> noise test, measured on the previous data delivery".*

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

All four arms verify on nifty100 and midcap150. The table is the 2026-09-26
measurement. check_all now gates 39 cells; the 9 that do not verify (midcap100 v3 and
eight market-cap bucket cells) are listed in `check_all.py` with their reasons. Every
Nautilus figure for a cell that is not gated is unverified.

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

**On the 2026-10-10 data the midcap150 edge is not concentrated in a few names.**
Re-measured 2026-10-10 with `jackknife.py` on the published v2 run (window
2019-01-01 to 2026-05-29, 1,835 sessions, cadence 20, research profile, tax off;
the script's baseline reproduces `v2FINAL_equity.csv` exactly). midcap150 beats its
own buy & hold by **8.80** points. The most damaging single removal, SUZLON, takes
it to **+7.01**; removing LLOYDSME and TATAINVEST together leaves **+8.18**. No
single removal of the 148 and **none of 200** random 8-name removals makes the edge
negative. On nifty100 the edge is **−2.09**, and every one of the 99 single removals
and 192 of the 200 random removals leave it negative. Each figure is one draw (n=1).
Records: `diagnostics/jackknife_midcap150_20261010.txt`,
`diagnostics/jackknife_nifty100_20261010.txt`.

> *Superseded 2026-10-10: this paragraph read, from the 2026-09-25 measurement on the
> uncleaned prices: "midcap150 beats its own buy & hold by 3.32 points. Removing
> TATAELXSI alone takes that to +0.07. Removing LLOYDSME leaves +2.94, and removing
> TATAINVEST as well +2.65. No single removal of the 148 makes the edge negative; 30
> of 200 random 8-name removals do. On nifty100 the edge is −4.76 and every one of the
> 99 single removals leaves it negative." Records:
> `diagnostics/jackknife_midcap150_20260925.txt`,
> `diagnostics/jackknife_nifty100_20260925.txt`.*

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

**midcap150 holds positions it could not have bought.** Re-measured 2026-10-15, on the
2026-10-10 data, at the backtest's own Rs 10,00,000: **18 of 973 fills** with a
prior-20-session median
exceed 10% of it (n=973 fills in all). The worst is TATAINVEST on 2019-12-26 at
**34.48%**. nifty100 is cleaner: **3 of 954** above 10% (n=954). Modelling depth
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

## Results dashboard

`dashboard/` builds one HTML page that shows every finished run: the run with its
equity, drawdown, yearly returns, costs and command; a grid over any two axes; up to
six runs compared; the capital ladder; three ways of stating the return; a table of
all runs; and the known issues. It reads finished runs under `runs/<timestamp>_*/`
and the newest `diagnostics/capital_ladder_*.csv` only. It runs no backtest and
writes nothing outside `dashboard/`. From the repository root:

    ./venv/bin/python dashboard/export_dashboard_data.py
    python3 dashboard/build_dashboard.py

The page is `dashboard/dashboard.html`, built from `dashboard/dashboard_data.json`.
Open it by double-clicking: it needs no network. Both files are about 24 MB, change
on every rebuild and are not tracked. `dashboard/test_dashboard.py` drives the page
in headless Chrome and needs Chrome installed.

**After every successful `run.py` run the dashboard is rebuilt** with the two
commands above, within 120 seconds; on any error or timeout it prints one warning
line, leaves the previous dashboard as it was, and the run's exit code is unchanged.
It then compares README.md's tax-on tables with `tools/readme_tax_tables.py --print`
and prints one warning line naming any table that differs. Neither writes outside
`dashboard/`.

**Published and ad hoc runs.** `dashboard/PUBLISHED_RUNS.txt` names the run folders
behind the published figures (`[published]`) and the earlier runs they replaced
(`[superseded]`, not shown). A run from any other folder, such as a demonstration
with unusual settings, appears only under "Ad hoc runs", labelled as such: it never
replaces a published cell and feeds neither the export's check f nor the ladder. A
rerun is published only when its folder is moved into `[published]` and the one it
replaces into `[superseded]`. The refresh prints "PUBLISHED_RUNS.txt needs updating"
when a newer run of a published combination has a different CAGR, max drawdown, final
value, basket CAGR or tax; to update, move that newer folder's name from wherever it is
into `[published]` and the folder it names as published into `[superseded]`.

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
    dashboard/        the results dashboard: export, page builder, page template,
                      browser test
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

The pipeline reads exactly one folder, 2,868 CSV files: 1,634 in the nine index
folders (1,024 MB) and 1,234 in the three market-cap bucket folders the supplier added
on 2026-10-16 (about 650 MB). Put it at this path, with these twelve subfolders, one per
universe:

    data/raw/Final_Without_Survivorship_Data/
        Final_NIFTY50_EoD_Data/            nifty50       51 CSV   (50 constituents + Nifty 50.csv)
        Final_NIFTY100_EoD_Data/           nifty100     100 CSV   (99 + NIFTY 100.csv)
        Final_NIFTY200_EoD_Data/           nifty200     198 CSV   (197 + NIFTY 200.csv)
        Final_NIFTY500_EoD_Data/           nifty500     496 CSV   (495 + NIFTY500.csv)
        Final_NIFTYMidCap50_EoD_Data/      midcap50      50 CSV   (49 + NIFTY MIDCAP 50.csv)
        Final_NIFTYMidCap100_EoD_Data/     midcap100     99 CSV   (98 + NIFTY MIDCAP 100.csv)
        Final_NIFTYMidCap150_EoD_Data/     midcap150    149 CSV   (148 + NIFTY MIDCAP 150.csv)
        Final_NIFTYSmallCap250_EoD_Data/   smallcap250  249 CSV   (248 + NIFTY SMLCAP 250.csv)
        Final_NiftyMicroCap250_EoD_Data/   microcap250  242 CSV   (241 + NIFTY MICROCAP250.csv)
        Final_Universe_MarcketCap_1500_5000/   mcap1500to5000   478 CSV   (477 + NIFTY 500.csv)
        Final_Universe_MarcketCap_5001_10000/  mcap5001to10000  217 CSV   (216 + NIFTY 500.csv)
        Final_Universe_MarcketCap_GT_10000/    mcapover10000    539 CSV   (538 + NIFTY 500.csv)

Each folder holds one CSV per constituent, named by NSE symbol (`ABB.csv`), and one
for the published index. A universe's constituents are whatever CSVs are in its
folder, so an extra or missing file changes that universe and every figure on it.
For one universe only, copy just its folder; for the published figures, all twelve.
The three market-cap folders are static only (no membership files); see "The
market-cap buckets" under Results and KNOWN_ISSUES.md.
Other folders the owner's copy may have under `data/raw/` are not read by the
pipeline: `Final_With_Survivorship_Data/` (1,470 MB) and `Survivorship_Bias/` (1 MB).
`survivorship_attribution.py` alone reads `Survivorship_Bias/` and the price files of
`Final_With_Survivorship_Data/`; neither is in the checksum manifest.

**Check your copy before running anything:**

```
python3 check_data.py
```

It compares every file against the tracked manifest `data/RAW_DATA_SHA256.txt`
(SHA-256 per file) and exits 0 only if all 2,868 match and no extra file is present;
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
