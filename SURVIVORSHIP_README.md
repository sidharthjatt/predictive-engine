# survivorship.py — point-in-time index membership, behind a switch

Removes survivorship bias from a backtest when a valid membership history is
available, and leaves existing behaviour byte-identical when it is not.

Self-contained: needs only `pandas` and `numpy`. Drop it next to your engine.

---

## The problem it solves

Every universe in this project is a list of **today's** index members, backfilled
to the start of the backtest. A name is in that list because it survived and
performed well enough to still be in the index now. Companies that were in the
index and were later dropped or delisted are absent entirely.

So the strategy picks from a set it could not have known in advance. Both the
strategy and its buy-and-hold benchmark are inflated by it.

Point-in-time membership fixes this: at every rebalance, the eligible set is the
membership actually in force on that date.

---

## Quick start

```python
import survivorship as sv

# 1. ALWAYS validate before trusting a file.
print(sv.validation_report("data/raw/index_membership_nifty100.csv",
                           index_name="nifty100",
                           price_dir="data/raw/N100/clean"))

# 2. Load. Raises MembershipError if it does not validate.
m = sv.load("data/raw/index_membership_nifty100.csv",
            index_name="nifty100",
            price_dir="data/raw/N100/clean")

# 3. Turn the switch on.
sv.set_mode("pit")          # "static" (default) | "pit"
sv.set_exit_policy("forced")  # "forced" (default) | "buffer"
```

From the command line:

```bash
python3 survivorship.py validate <membership.csv> --prices <dir> --index nifty100
python3 survivorship.py members  <membership.csv> 2021-06-15
python3 survivorship.py coverage <membership.csv> --prices <dir>
```

`validate` exits 0 on pass, 2 on fail — usable as a CI gate.

---

## Why validation raises instead of warning

The first membership file supplied to this project parsed cleanly: 76 dated rows,
100 symbols each, inclusions and exclusions columns, price data for 203 names.

It also contained **no RELIANCE**. Nor INFY, ITC, SBIN or ICICIBANK — absent from
all 76 lists, in an index they have been in continuously. And
`list[t] = list[t-1] + inclusions − exclusions` failed on 20 of 75 transitions.

A backtest on that file would have produced a survivorship-free-*looking* number
from a strategy that could never buy Reliance, benchmarked against an index largely
made of Reliance. It would have looked like the answer and been the least
trustworthy figure in the project.

So `load()` raises. A caveat gets dropped when a number is copied into a slide;
an exception does not.

Running the validator on that exact file:

```
ERRORS -- the file cannot be used:
  - 5 anchor names appear in ZERO of the 76 lists: RELIANCE, INFY, ICICIBANK, ITC, SBIN.
  - 1 symbols are not equity tickers: 722HPCL29.
  - inclusions/exclusions disagree with the symbols column on 20 of 75 transitions.

WARNINGS:
  - 59 of 231 members have no price file. Of those, 54 were dropped from the index
    at some point and 5 are current members. The gap is biased toward dropped names,
    so RESIDUAL SURVIVORSHIP REMAINS even in pit mode.

VERDICT: FAIL
```

That last warning matters even when a file passes. A membership history you cannot
fully price still leaves bias behind, and it must be reported with any result.

---

## What the validator checks

| Check | Severity | Why |
|---|---|---|
| `effective_date` parses, sorted, no duplicates | error | ordering is the whole mechanism |
| Anchor names present | **error** | a Nifty 100 history without Reliance is not one |
| No non-equity tickers | **error** | a bond (`722HPCL29`) cannot be a constituent |
| `list[t] = list[t-1] + inc − exc` | **error** | disagreement means no coherent series |
| Member count near expected | warning | a plausibility signal, not proof |
| Implied turnover plausible | warning | too little churn suggests a truncated history |
| Price coverage per member | warning | a limitation to disclose, not a defect |

Anchors live in `SANITY_ANCHORS`. Add an index by adding its list. Leave it empty
(as for `midcap150`) when no single name is guaranteed present throughout.

---

## Exit policy

**`forced` (default)** — a name is sold on the first trading day after it leaves the
index, regardless of rank or buffer status.

The point of a point-in-time universe is that the portfolio never holds what it
could not have held. Letting the buffer carry a name past its exclusion date
reintroduces the bias the module exists to remove. The cost is extra turnover on
reconstitution dates — the correct price, and one a real index mandate also pays.

**`buffer`** — the normal buffer rule applies and `forced_exits()` returns empty.
It exists so the two can be measured against each other. It is not the honest
default.

---

## Integration

Three touch points. All are no-ops in `static` mode, so they can sit permanently
in the pipeline.

### 1. Score panel — restrict what can be ranked

```python
p = p.dropna(subset=FEATS_V2)
p = sv.apply_to_panel(p, membership)      # no-op unless mode == "pit"
```

**Apply this to the score panel, never the price panel.** A name being sold after
exclusion still needs its price on the sale date.

This project has already been bitten once by filtering prices for a non-price
reason: `dropna(subset=FEATS_V2)` fed the price pivot, `ffill` bridged the holes,
and the result was manufactured single-day returns of up to **+24,773%** that
reached live trading decisions. Keep price and eligibility separate.

### 2. Ranking — mask ineligible names

```python
if sv.is_pit():
    eligible = membership.members_on(decision_date)
    scores = scores[[s for s in scores.index if s in eligible]]
top = scores.sort_values(ascending=False).index[:TOP_N]
```

### 3. Rebalance — force out excluded names

```python
to_sell = {s for s in held if s not in keep}          # existing buffer rule
to_sell |= membership.forced_exits(held, decision_date)  # empty unless forced+pit
```

### Logs and charts

```python
print(sv.describe_state())
```

Emits one line naming the configuration. Put it in the chart subtitle. A result
produced in `static` mode should say so on its face — otherwise someone reads a
biased number as a clean one six months later.

---

## API

| Call | Returns |
|---|---|
| `set_mode(m)` / `is_pit()` | switch `"static"` \| `"pit"` |
| `set_exit_policy(p)` | `"forced"` \| `"buffer"` |
| `validate(path, index_name, price_dir)` | `ValidationResult` (`.ok`, `.errors`, `.warnings`, `.stats`) |
| `validation_report(...)` | the same, formatted |
| `load(...)` | `Membership` — **raises** on failure |
| `Membership.members_on(date)` | `set` in force on that date |
| `Membership.is_member(sym, date)` | `bool` |
| `Membership.forced_exits(held, date)` | `set` to sell now |
| `Membership.eligible_mask(dates, syms)` | `DataFrame[date × symbol]` of `bool` |
| `Membership.coverage_table(price_dir)` | per-date price coverage |
| `apply_to_panel(panel, m)` | filtered long panel; no-op in static |
| `describe_state()` | one-line configuration string |

`load(..., allow_invalid=True)` bypasses the gate for **inspecting** a broken file.
Anything computed under it must not be reported.

---

## File format

```csv
effective_date,symbols,inclusions,exclusions
2019-03-29,"RELIANCE,TCS,INFY,...",,
2019-09-27,"RELIANCE,TCS,MARUTI,...","MARUTI","WIPRO"
```

`effective_date` and `symbols` are required. `inclusions`/`exclusions` are optional
but strongly recommended — they are what makes the file checkable against itself.
Dates may be ISO or day-first; both are handled.

---

## What this does not fix

- **Unpriced members.** If a dropped name has no price file it cannot be held, so
  residual bias remains. The validator quantifies it; report it.
- **Corporate actions.** Unadjusted splits are a separate problem.
- **Index promotion.** A midcap promoted to large-cap leaves the midcap index for a
  good reason. Point-in-time membership handles the mechanics, not whether the
  benchmark still means the same thing across the window.

---

## Tests

```bash
python3 test_survivorship.py
echo $?    # 0 = all passed
```

50 tests, no pytest needed — bare Python with pandas and numpy, so anyone can
verify the module on their own machine without installing anything.

What they cover:

| Group | Tests | Guards against |
|---|---|---|
| validation | 11 | a broken file being accepted |
| members_on | 6 | off-by-one at a reconstitution boundary |
| exits | 4 | a name held past its exclusion, or sold early |
| switch | 6 | **static mode ceasing to be a no-op** |
| mask | 3 | an ineligible name being rankable |
| config | 5 | an invalid mode silently accepted |
| dates | 2 | day-first vs ISO misparse |
| gate | 6 | one error class regressing, one fixture each |
| falsepos | 3 | the gate rejecting a legitimate file |
| tickers | 3 | a real equity read as a bond, or a bond as an equity |

Two are worth calling out.

**`switch: STATIC IS A NO-OP`** is the most important test in the file. If someone
edits this module and static mode starts filtering rows, every existing result in
the project silently changes. That test asserts byte-identity of the panel.

**No test reads a file it did not create.** The `gate` group replaced a single
test that searched for the real broken Nifty 100 file on disk and asserted three
error classes fired on whatever it found. That coupled the suite to a path rather
than to behaviour: when a second, differently-broken file was placed there — all
seven anchors present this time — the missing-anchor assertion failed and the
suite reported 38/39, with nothing wrong in the module. Each `gate` test now
builds one synthetic fixture exercising exactly one failure mode, so a failure
names the defect instead of describing the current contents of a directory.

The `falsepos` group is the other half of that discipline. A validation gate is
only as good as its willingness to pass a good file, and the cumulative-list check
originally failed two legitimate histories: one that barely changes (identical
consecutive rows are supersets of each other) and one where the index genuinely
widens in a single step. Both are now fixtures.

---

## Testing your own file

```bash
python3 survivorship.py validate your_file.csv --prices your_price_dir
echo $?    # 0 = pass, 2 = fail
```
