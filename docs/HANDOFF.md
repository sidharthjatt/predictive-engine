# Handoff — what ships, in the order you unpack it

## Read this paragraph before anything else

**Cross-machine reproducibility has never been tested.** Nobody has run this
pipeline on a second machine and compared the numbers. On 2026-09-12 a cold
rebuild reproduced both universes' published figures byte-identically on every
field — but that was the **same machine, the same `venv`, the same interpreter**.
It is evidence that the one pinned dependency is pinned in the right place. It is
not evidence that you will get the same numbers, and it should not be quoted as
if it were.

Expect to reproduce the *structure* — the shape of the equity curve, the trade
count within a few, the drawdown within a point. If you reproduce the headline
CAGR to two decimal places on different hardware, that is a stronger result than
this project has ever demonstrated, and it is worth reporting back.

Before trusting any number you produce, read `KNOWN_ISSUES.md` from the top. The
first entry is the one that matters: the strategy's return edge over a
fully-invested benchmark is smaller than the noise it is measured through, and
its drawdown advantage does not survive the control that holds exposure fixed.

---

## 1. The code

Every `.py` file — 82 of them, all tracked. Ship the directory layout exactly as
it is:

```
run.py  run_all.py  paths.py  config.py  config_mid.py  config_n100.py
cadence.py  profiles.py  module_state.py  check_pipeline_order.py  (+ root tools)
results/     the engine, the steps, and the shared libraries
nautilus/    the execution port (STEP 16, STEP 17)
universes/   registry.py — the single definition of what a universe is
arms/        registry.py — the single definition of what an arm is
experiments/ specs and pre-registrations (not executed by the pipeline)
diagnostics/ findings files (not executed by the pipeline)
```

**There is no `__init__.py` anywhere.** `results/`, `nautilus/`, `universes/` and
`arms/` are plain directories that work because every entry point manipulates
`sys.path`. Flattening the layout, or turning them into packages, breaks imports
in ways that will not be obvious.

## 2. The trading calendar — ships, and cannot be rebuilt

```
data/nse_trading_calendar.csv     6,574 sessions, 2000-01-03 to 2026-06-08
```

**Tracked, required by every panel build, and there is no longer any code that
can regenerate it.** It was derived from a universe called "the 58", which was
deleted on 2026-09-11 along with `results/make_trading_calendar.py`. The file is
now source data in the same sense as a raw price file. If you lose it, restore it
from git; nothing can recompute it.

Its end date, 2026-06-08, is a **data** boundary, not a market one — it is simply
the last date present in the deleted universe's files. See
`RETIRED_UNIVERSES.md` section 6.

## 3. The price data — 172 MB, untracked, and no source is recorded

```
data/raw/MidCap150/clean/          149 files    95 MB   148 constituents + NIFTYMIDCAP150.csv
data/raw/nifty100_benchmark/       100 files    77 MB    99 constituents + NIFTY100.csv
```

**A `git clone` does not produce a runnable repository.** These directories are
excluded from git and must be copied separately. Worse, and recorded in
`KNOWN_ISSUES.md` as its own entry: **no source, vendor, download date or
licence is recorded anywhere for this data.** If you lose it you cannot
re-acquire it from anything in this repository.

Column contract: `date, open, high, low, close, adj_close, volume, open_interest`
at minimum. `adj_close` is the canonical price and is resolved into `close` at the
single load boundary in `engine_core.build_panel`.

## 4. The symlink farms — ship them empty, never broken

```
data/raw/MidCap150/constituents/
data/raw/N100_constituents/
```

These contain **symlinks**, not files. They are rebuilt on import by
`config_mid.ensure_constituents_dir()` and `config_n100.ensure_constituents_dir()`,
so shipping them empty is correct and costs nothing.

**Shipping them containing stale absolute symlinks is not.** A copy that
preserves broken links pointing at the source machine's paths will fail in ways
that look like missing data rather than like a bad copy. `rsync` without `-L`,
and `zip` without care, both do this. Delete the contents and let the code
rebuild them.

## 5. Tooling data — ships, but the pipeline does not read it

```
data/reference/*.csv                  3 files, 9.6 MB   membership tooling
data/raw/membership_workbooks/*.xlsx  4 files, 116 KB   survivorship tooling
data/raw/N100_Survivorship/…          160 MB            point-in-time membership
```

None of this is on the pipeline path. The survivorship membership file is read
only when `SURVIVORSHIP_MODE = "pit"`, which **no pipeline step sets** — the
default is `"static"`, today's constituents backfilled. Ship it if you intend to
work on survivorship; the pipeline runs without it.

## 6. The environment

**Python 3.12 or newer.** A hard floor, set by `nautilus_trader`, not a
preference.

**`requirements.txt` pins exactly one thing, deliberately:**

```
lightgbm==4.6.0
```

Every score in this project comes from `lgb.LGBMRegressor`. A one-bit float
difference is enough to flip a split decision, reorder near-tied names at the
`TOP_N=8` boundary, and move the headline CAGR by two thirds of a point — that is
measured, not feared; see `KNOWN_ISSUES.md`, *"The headline is not reproducible
from the artefacts on disk to better than about a point"*. A minor-version bump
is free to change split arithmetic, so a floor would not preserve the numbers.

Everything else is a range, with the versions present at the last published
headline recorded in `requirements.txt` as provenance. There is one data point on
what that looseness costs: on 2026-09-12, five of those libraries had drifted from
the recorded versions (`scipy`, `scikit-learn`, `joblib`, `matplotlib`,
`nautilus_trader`) while `lightgbm`, `numpy` and `pandas` matched — and the
numbers reproduced byte-identically. One observation, same machine.

**`/tmp` must exist and be writable, with about 1.5 GB free.** It is hardcoded in
37 places as the working directory for the score and raw panels. This is a POSIX
assumption, not a configurable path.

**Nothing else outside the repository is read.** No absolute paths, no home
directory, no environment variable is ever read — `PYTHONHASHSEED` and the
thread-count caps are set by the code, never consulted from outside.

## 7. First run

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

# Confirm the real cost model is active, not the 0.11% fallback.
# If this prints FALLBACK, every cost figure will differ by about 9%.
./venv/bin/python -c "import sys;sys.path.insert(0,'results');\
import engine_core,inspect;\
print('REAL' if 'compute_leg_charges' in inspect.getsource(engine_core.calc_tc) else 'FALLBACK')"

./venv/bin/python run.py --list                     # resolved plan, runs nothing
./venv/bin/python run.py --universe mid --arm v2    # ~20 min, most of it scoring
```

Use `./venv/bin/python`, not `python3`. Every step is spawned with
`sys.executable`, so the launching interpreter propagates to every child.

**Expect about 35 minutes for a cold two-universe run**, of which 34 is the two
LightGBM scoring steps (measured 2026-09-12: 18.5 min for mid, 15.7 for n100).
Every other step is seconds. Once the panels exist in `/tmp`, or have been
persisted by STEP 15b, scoring is skipped and a full run is a couple of minutes.

## 8. What is not settled, and what you should not assume

- **Cross-machine reproducibility.** Untested. This is the open item this file
  exists to flag: nothing in this repository can answer whether anyone else can
  reproduce these numbers, and nobody has tried. It is the first thing a new
  holder of this code is in a position to establish, and it would be worth more
  than any further backtest.
- **Combination coverage.** Of roughly 540 nominal selection combinations
  (universe × arm × cadence × profile × steps), a small minority have ever been
  run. Nine of fifteen arm subsets have never been exercised; the `tradeable`
  profile appears in two runs out of fifty-five. Three separate axes have now
  produced the same class of bug — a hardcoded name where a selection-derived one
  belonged — on the cadence, arm and profile axes in turn.
- **The numbers themselves.** `KNOWN_ISSUES.md` is long and it is the honest
  half of this repository. Read it before the README.
