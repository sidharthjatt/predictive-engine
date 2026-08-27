"""
survivorship.py -- point-in-time index membership, behind a switch.

WHY THIS EXISTS
    Every universe in this project is built from a list of TODAY'S index members,
    backfilled to the start of the backtest. That is survivorship bias: a name only
    appears in the list because it survived and performed well enough to still be in
    the index now. Companies that were in the index and were later dropped or
    delisted are absent entirely, so the strategy is choosing from a set it could not
    have known in advance.

    This module removes that bias when a valid membership file is available, and
    leaves the existing behaviour untouched when it is not. Nothing else changes.

THE SWITCH
    SURVIVORSHIP_MODE = "static"  -- today's members, backfilled. The existing
                                     behaviour. This is the default.
    SURVIVORSHIP_MODE = "pit"     -- point-in-time. At every rebalance the eligible
                                     set is the membership in force on that date.

    Set it in config, or per-run:

        import survivorship as sv
        sv.set_mode("pit")

WHY THERE IS A VALIDATION GATE, AND WHY IT REFUSES RATHER THAN WARNS
    The first membership file supplied to this project was broken in a way that
    looked fine at a glance: 76 dated rows, 100 symbols each, inclusions and
    exclusions columns, and price data for 203 names including many that had been
    dropped. It parsed cleanly.

    It also contained no RELIANCE. Nor INFY, ITC, SBIN, ICICIBANK, HDFCBANK,
    KOTAKBANK or SUNPHARMA -- eight of the largest companies in the Indian market,
    absent from all 76 lists, in an index they have been in continuously. And
    list[t] = list[t-1] + inclusions - exclusions failed on 20 of 75 transitions,
    so the columns disagreed with each other.

    A backtest run on that file would have produced a survivorship-free-looking
    number from a strategy that could never buy Reliance, compared against an index
    largely made of Reliance. It would have looked like the answer and been the least
    trustworthy figure in the project.

    So validate() raises. It does not warn and continue. A caveat gets dropped when
    a number is copied into a slide; a raised exception does not.

HOW A NAME LEAVING THE INDEX IS HANDLED
    Forced exit on the exclusion date, not a buffer exit at the next rebalance.

    The point of a point-in-time universe is that the portfolio never holds what it
    could not have held. Letting the buffer carry a name past its exclusion date
    reintroduces exactly the bias this module exists to remove. The cost is extra
    turnover on the reconstitution dates, which is the correct price to pay -- and a
    real index-tracking mandate pays it too.

    EXIT_POLICY = "forced"  -- sell on the first trading day after exclusion (default)
    EXIT_POLICY = "buffer"  -- let the normal buffer rule handle it

    "buffer" exists so the two can be measured against each other. It is not the
    honest default.

EXPECTED FILE FORMAT
    A CSV with one row per reconstitution date:

        effective_date,symbols,inclusions,exclusions
        2019-03-29,"RELIANCE,TCS,INFY,...","ABC,DEF","XYZ"

    effective_date : the date the change takes effect
    symbols        : comma-separated full membership list in force from that date
    inclusions     : comma-separated names added on that date (optional)
    exclusions     : comma-separated names removed on that date (optional)

    Only effective_date and symbols are required. If inclusions/exclusions are
    present they are cross-checked against symbols, and a disagreement is an error,
    because it means the file has no single coherent membership series.

USAGE

    import survivorship as sv

    # 1. Check a file before trusting it. Run this first, always.
    print(sv.validation_report("data/raw/index_membership_nifty100.csv",
                               price_dir="data/raw/N100/clean"))

    # 2. Load it. Raises if it does not validate.
    m = sv.load("data/raw/index_membership_nifty100.csv")

    # 3. Ask what was eligible on a date.
    m.members_on("2021-06-15")            # -> set of symbols

    # 4. Filter a panel to point-in-time membership.
    panel = sv.apply_to_panel(panel, m)   # no-op when mode is "static"

    # 5. Names to force out at a rebalance, given what is held.
    m.forced_exits(held_symbols, decision_date)

COMMAND LINE

    python3 survivorship.py validate <membership.csv> [--prices <dir>]
    python3 survivorship.py members <membership.csv> <date>
    python3 survivorship.py coverage <membership.csv> --prices <dir>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# switches
# ---------------------------------------------------------------------------

SURVIVORSHIP_MODE = "static"     # "static" | "pit"
EXIT_POLICY = "forced"           # "forced" | "buffer"


def set_mode(mode: str) -> None:
    """Set the survivorship mode for this process."""
    global SURVIVORSHIP_MODE
    if mode not in ("static", "pit"):
        raise ValueError(f"mode must be 'static' or 'pit', got {mode!r}")
    SURVIVORSHIP_MODE = mode


def set_exit_policy(policy: str) -> None:
    """Set how a name leaving the index is handled."""
    global EXIT_POLICY
    if policy not in ("forced", "buffer"):
        raise ValueError(f"policy must be 'forced' or 'buffer', got {policy!r}")
    EXIT_POLICY = policy


def is_pit() -> bool:
    return SURVIVORSHIP_MODE == "pit"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class MembershipError(Exception):
    """Raised when a membership file cannot be trusted. Never downgraded to a warning."""


# Names that must appear somewhere in a genuine history of these indices. If a file
# claims to be Nifty 100 membership and contains no Reliance, the file is wrong --
# there is no reading of the data under which that is a coverage gap.
SANITY_ANCHORS = {
    "nifty100": ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "ITC", "SBIN"],
    "nifty50": ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "ITC", "SBIN"],
    "midcap150": [],   # no single name is guaranteed present across a midcap history
}

# A constituent symbol is an equity ticker. These patterns are debt or derivative
# identifiers that appeared in the first broken file (e.g. "722HPCL29" = 7.22% HPCL
# 2029, a debenture) and cannot be index constituents.
def _looks_non_equity(sym: str) -> bool:
    """Flag debt identifiers without flagging equities that start with a digit.

    A first version rejected anything beginning with a digit, which is wrong:
    3MINDIA (3M India) and 8KMILES (8K Miles Software) are ordinary NSE equities.
    A bond identifier is a coupon followed by an issuer and a maturity year --
    722HPCL29 is 7.22% HPCL 2029 -- so it carries THREE OR MORE leading digits and
    ends in a two-digit year. That pattern is what is rejected, not the leading
    digit alone."""
    if not sym:
        return True
    if len(sym) > 20:
        return True
    lead = len(sym) - len(sym.lstrip("0123456789"))
    if lead >= 3 and sym[-2:].isdigit():
        return True               # 722HPCL29, 1025GOI30, 828GS2027
    # Issuer code followed by a FOUR-digit year, with no coupon prefix: GS2027.
    # Four trailing digits forming a plausible year is a debt signature, and no NSE
    # equity ticker ends that way. Kept deliberately narrow -- see the note below on
    # what is NOT claimed.
    if re.fullmatch(r"[A-Z&\-]{2,8}(19|20)\d{2}", sym):
        return True
    # NOT DETECTED, AND DELIBERATELY SO: an issuer code plus a TWO-digit year with no
    # coupon prefix (NHAI31, IRFC24, IIFL27 in shape). Rejecting every symbol that
    # ends in two digits would be the only way to catch those, and that cannot be
    # done safely -- it is indistinguishable from an equity ticker by pattern alone,
    # and a false positive here rejects a whole valid membership file. Verified
    # against 938 real tickers drawn from this repo's price files and the membership
    # file itself: zero equities are rejected by the rules above.
    return False


@dataclass
class ValidationResult:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def __str__(self) -> str:
        lines = ["=" * 74,
                 "MEMBERSHIP FILE VALIDATION",
                 "=" * 74]
        for k, v in self.stats.items():
            lines.append(f"  {k:<44}{v}")
        if self.errors:
            lines.append("")
            lines.append("  ERRORS -- the file cannot be used:")
            for e in self.errors:
                lines.append(f"    - {e}")
        if self.warnings:
            lines.append("")
            lines.append("  WARNINGS -- usable, but the result carries these caveats:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        lines.append("")
        lines.append("  VERDICT: " + ("PASS" if self.ok else "FAIL"))
        lines.append("=" * 74)
        return "\n".join(lines)


def _read_raw(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    if "effective_date" not in cols or "symbols" not in cols:
        raise MembershipError(
            f"{path}: required columns 'effective_date' and 'symbols' not found. "
            f"Columns present: {list(df.columns)}")
    df = df.rename(columns={cols["effective_date"]: "effective_date",
                            cols["symbols"]: "symbols"})
    for opt in ("inclusions", "exclusions"):
        if opt in cols:
            df = df.rename(columns={cols[opt]: opt})
        else:
            df[opt] = ""
    # Try ISO first, then day-first. Doing it in this order avoids pandas warning
    # on ISO input, and avoids silently reading 03/02/2019 as 2 March.
    raw = df["effective_date"].astype(str)
    parsed = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        alt = pd.to_datetime(raw, dayfirst=True, errors="coerce")
        parsed = parsed.fillna(alt)
    df["effective_date"] = parsed
    if df["effective_date"].isna().any():
        n = int(df["effective_date"].isna().sum())
        raise MembershipError(f"{path}: {n} rows have an unparseable effective_date")
    return df.sort_values("effective_date").reset_index(drop=True)


def _split(cell) -> set:
    if pd.isna(cell):
        return set()
    return {s.strip().upper() for s in str(cell).split(",") if s.strip()
            and s.strip().lower() != "nan"}


def validate(path, index_name: str = "nifty100", price_dir=None,
             expected_size: int | None = None) -> ValidationResult:
    """Check a membership file without loading it into the engine.

    Returns a ValidationResult. Does not raise -- use load() for that, or check
    result.ok yourself. price_dir is optional; when given, price coverage is
    measured and reported as a warning rather than an error, because a coverage
    gap is a limitation to disclose, not a reason the file is wrong.
    """
    res = ValidationResult(ok=True)
    df = _read_raw(path)
    lists = [_split(s) for s in df["symbols"]]
    all_syms = set().union(*lists) if lists else set()

    res.stats["rows (reconstitution dates)"] = len(df)
    res.stats["date range"] = (f"{df.effective_date.min().date()} -> "
                               f"{df.effective_date.max().date()}")
    res.stats["distinct symbols ever a member"] = len(all_syms)
    sizes = [len(L) for L in lists]
    res.stats["members per date (min/median/max)"] = (
        f"{min(sizes)} / {int(np.median(sizes))} / {max(sizes)}")

    # --- 1. dates strictly increasing, no duplicates -----------------------
    if df["effective_date"].duplicated().any():
        res.errors.append("duplicate effective_date rows")
    if not df["effective_date"].is_monotonic_increasing:
        res.errors.append("effective_date is not sorted ascending after sorting")

    # --- 2. anchors: names that must be present ----------------------------
    anchors = SANITY_ANCHORS.get(index_name.lower(), [])
    missing = [a for a in anchors if a not in all_syms]
    if missing:
        res.errors.append(
            f"{len(missing)} anchor names appear in ZERO of the {len(df)} lists: "
            f"{', '.join(missing)}. These are among the largest constituents of "
            f"{index_name} and cannot be absent from a genuine history. This is the "
            f"exact failure mode of the first file supplied to this project.")
    present = {a: sum(a in L for L in lists) for a in anchors if a in all_syms}
    if present:
        res.stats["anchor presence (of %d dates)" % len(df)] = ", ".join(
            f"{k} {v}" for k, v in present.items())

    # --- 3. non-equity identifiers -----------------------------------------
    junk = sorted(s for s in all_syms if _looks_non_equity(s))
    if junk:
        res.errors.append(
            f"{len(junk)} symbols are not equity tickers: {', '.join(junk[:8])}"
            f"{' ...' if len(junk) > 8 else ''}. An equity index cannot contain "
            f"bonds or debentures.")

    # --- 4. self-consistency of inclusions/exclusions ----------------------
    have_incexc = (df["inclusions"].astype(str).str.strip().ne("").any() or
                   df["exclusions"].astype(str).str.strip().ne("").any())
    if have_incexc:
        bad = []
        for i in range(1, len(df)):
            inc = _split(df.iloc[i]["inclusions"])
            exc = _split(df.iloc[i]["exclusions"])
            expected = (lists[i - 1] | inc) - exc
            if expected != lists[i]:
                bad.append(str(df.iloc[i]["effective_date"].date()))
        res.stats["transitions checked"] = len(df) - 1
        res.stats["transitions failing list[t]=list[t-1]+inc-exc"] = len(bad)
        if bad:
            res.errors.append(
                f"inclusions/exclusions disagree with the symbols column on "
                f"{len(bad)} of {len(df)-1} transitions (first: {bad[0]}). The file "
                f"has no single coherent membership series.")
    else:
        res.warnings.append(
            "no inclusions/exclusions columns -- membership is taken from the "
            "symbols column alone and cannot be cross-checked.")

    # --- 4b. cumulative-list detection -------------------------------------
    # A membership list is a snapshot, not a running total. If each row is a
    # superset of the one before, the generating script accumulated names instead
    # of removing exclusions -- the second real file supplied to this project did
    # exactly that, reaching 854 names for a 100-name index.
    # AN EARLIER VERSION OF THIS CHECK COUNTED NON-STRICT SUPERSETS AND FIRED ON
    # LEGITIMATE FILES. Two false positives were measured against it:
    #   (a) a stable history whose membership barely changes -- consecutive rows are
    #       IDENTICAL, and a set is a superset of itself, so 9 of 11 transitions
    #       counted as "cumulative". It reported a file that "grows from 100 to 100
    #       names" as a running total, which is self-evidently not what it is.
    #   (b) a genuine index expansion, Nifty 50 -> Nifty 100 partway through the
    #       history: every transition is a (non-strict) superset, so it fired at
    #       11 of 11. An index that genuinely widens is not a broken file.
    #
    # Three conditions now have to hold together, and they are what actually
    # distinguishes accumulation from both of those:
    #   - the list has to GROW substantially end to end (rules out (a));
    #   - growth has to be SUSTAINED across several separate reconstitutions, not
    #     one step (rules out (b), which grows exactly once);
    #   - names must almost never LEAVE. This is the real signature: a snapshot
    #     history removes roughly as many names as it adds over time, while an
    #     accumulating script removes almost none.
    grew = [i for i in range(1, len(lists)) if lists[i - 1] < lists[i]]
    added = sum(len(lists[i] - lists[i - 1]) for i in range(1, len(lists)))
    removed = sum(len(lists[i - 1] - lists[i]) for i in range(1, len(lists)))
    if (len(lists) > 3 and max(sizes) >= 1.5 * sizes[0]
            and len(grew) >= 3 and removed <= 0.25 * added):
        res.errors.append(
            f"the symbols column looks CUMULATIVE: it grows from {sizes[0]} to "
            f"{max(sizes)} names across {len(grew)} separate reconstitutions, adding "
            f"{added} names while only ever removing {removed}. A membership list is "
            f"a snapshot of who is in the index on that date, not a running total of "
            f"everyone who has ever been in it. The generating script is adding "
            f"inclusions without removing exclusions.")

    # Excluded names must actually leave the list they were excluded from.
    if have_incexc:
        still, checked = 0, 0
        both, total_exc = 0, 0
        for i in range(1, len(df)):
            inc_i = _split(df.iloc[i]["inclusions"])
            for e in _split(df.iloc[i]["exclusions"]):
                total_exc += 1
                # A name listed in BOTH inclusions and exclusions on the same date is
                # the one legitimate way an excluded name can still be in that row's
                # symbols -- removed and re-added in the same reconstitution. Counting
                # it as an unremoved exclusion would be a false positive, so it is
                # excluded from that count and checked separately below: rare is
                # plausible, routine is a defect in its own right.
                if e in inc_i:
                    both += 1
                    continue
                checked += 1
                if e in lists[i]:
                    still += 1
        if total_exc:
            res.stats["names in both inclusions and exclusions"] = \
                f"{both} of {total_exc}"
        # BOTH conditions, not either: an absolute floor so a one-off re-add in a
        # small file stays a warning, and a proportional floor so a handful of them
        # in a long history does not become an error on volume alone.
        if both >= 3 and both >= 0.05 * total_exc:
            res.errors.append(
                f"{both} of {total_exc} exclusion entries name a symbol that the SAME "
                f"row also lists as an inclusion. A reconstitution adds a name or "
                f"drops it, not both on one date, so at this frequency the two "
                f"columns are not describing a single index event -- most likely the "
                f"generating script is merging rows from more than one source list.")
        elif both:
            res.warnings.append(
                f"{both} of {total_exc} exclusion entries are also listed as an "
                f"inclusion on the same date (removed and re-added in one "
                f"reconstitution). Rare but not impossible; worth confirming.")
        if checked:
            res.stats["exclusions still present in same row"] = f"{still} of {checked}"
        if still:
            res.errors.append(
                f"{still} of {checked} names listed in `exclusions` are STILL in the "
                f"symbols column of the same row. An excluded name must be absent "
                f"from the membership that takes effect on its exclusion date.")

    # --- 5. size plausibility ----------------------------------------------
    if expected_size:
        off = [i for i, n in enumerate(sizes) if abs(n - expected_size) > 2]
        if off:
            res.warnings.append(
                f"{len(off)} dates have a member count more than 2 away from the "
                f"expected {expected_size}.")

    # --- 6. churn plausibility ---------------------------------------------
    years = max((df.effective_date.max() - df.effective_date.min()).days / 365.25, 1)
    turnover = (len(all_syms) - int(np.median(sizes))) / years
    res.stats["names added per year (implied)"] = f"{turnover:.1f}"
    if turnover < 2.0 and years > 5:
        res.warnings.append(
            f"implied turnover of {turnover:.1f} names/year is low for an index of "
            f"this size over {years:.0f} years; verify the history is complete.")

    # --- 7. price coverage (a disclosure, not an error) --------------------
    if price_dir is not None:
        files = {p.stem.upper() for p in Path(price_dir).glob("*.csv")}
        have = all_syms & files
        missing_px = all_syms - files
        res.stats["symbols with a price file"] = f"{len(have)} of {len(all_syms)}"
        if missing_px:
            last = lists[-1] if lists else set()
            ever_out = all_syms - last
            miss_out = len(missing_px & ever_out)
            miss_in = len(missing_px & last)
            res.warnings.append(
                f"{len(missing_px)} of {len(all_syms)} members have no price file. "
                f"Of those, {miss_out} were dropped from the index at some point and "
                f"{miss_in} are current members. The gap is biased toward dropped "
                f"names, so RESIDUAL SURVIVORSHIP REMAINS even in pit mode. Report "
                f"this alongside any result.")

    res.ok = not res.errors
    return res


def validation_report(path, index_name="nifty100", price_dir=None,
                      expected_size=None) -> str:
    """Human-readable validation output. Run this before trusting a file."""
    return str(validate(path, index_name, price_dir, expected_size))


# ---------------------------------------------------------------------------
# the membership object
# ---------------------------------------------------------------------------

@dataclass
class Membership:
    """Point-in-time index membership, validated at construction."""
    dates: list                  # sorted effective dates (pd.Timestamp)
    lists: list                  # parallel list of symbol sets
    exclusions: dict             # effective_date -> set removed on that date
    source: str
    validation: ValidationResult

    def __post_init__(self):
        # np.searchsorted against a LIST of Timestamps works on some pandas/numpy
        # combinations and raises TypeError on others ("'<' not supported between
        # instances of 'Timestamp' and 'int'"). A real datetime64 array behaves
        # identically everywhere, so the comparison basis is fixed once here rather
        # than depending on the environment.
        object.__setattr__(self, "_dates64",
                           np.array(self.dates, dtype="datetime64[ns]"))

    def _pos(self, when):
        """Index of the membership list in force at each date in `when`.
        -1 where the date precedes the first effective date."""
        vals = pd.DatetimeIndex(pd.to_datetime(when)).values
        return np.searchsorted(self._dates64, vals, side="right") - 1

    def members_on(self, date) -> set:
        """The membership in force on `date` -- the most recent effective_date at
        or before it. Empty before the first effective date, which is correct: the
        universe is not defined before the history starts."""
        i = int(self._pos([pd.Timestamp(date)])[0])
        if i < 0:
            return set()
        return self.lists[i]

    def is_member(self, symbol, date) -> bool:
        return symbol.upper() in self.members_on(date)

    def forced_exits(self, held, date) -> set:
        """Of the names currently held, those no longer in the index on `date`.

        Under EXIT_POLICY="forced" these are sold regardless of their rank or
        buffer status. Under "buffer" this returns an empty set and the normal
        buffer rule applies."""
        if EXIT_POLICY != "forced":
            return set()
        m = self.members_on(date)
        if not m:
            return set()
        return {s for s in held if s.upper() not in m}

    def eligible_mask(self, panel_dates, symbols) -> pd.DataFrame:
        """Boolean DataFrame [date x symbol], True where the symbol was a member.

        Use this to mask scores before ranking, so a name is only ever selectable
        on dates it was actually in the index."""
        idx = pd.DatetimeIndex(pd.to_datetime(panel_dates))
        cols = [s.upper() for s in symbols]
        out = pd.DataFrame(False, index=idx, columns=cols)
        pos = self._pos(idx)
        for i, p in enumerate(pos):
            if p < 0:
                continue
            members = self.lists[p] & set(cols)
            if members:
                out.iloc[i, out.columns.get_indexer(list(members))] = True
        return out

    def coverage_table(self, price_dir) -> pd.DataFrame:
        """Per reconstitution date: members in force, members with price data,
        and the coverage percentage. Report this with any pit-mode result."""
        files = {p.stem.upper() for p in Path(price_dir).glob("*.csv")}
        rows = []
        for d, L in zip(self.dates, self.lists):
            have = len(L & files)
            rows.append({"effective_date": d, "members": len(L),
                         "with_price": have,
                         "coverage_pct": round(have / len(L) * 100, 1) if L else np.nan})
        return pd.DataFrame(rows)


def load(path, index_name="nifty100", price_dir=None,
         expected_size=None, allow_invalid=False) -> Membership:
    """Load and validate a membership file.

    Raises MembershipError if validation fails. allow_invalid=True bypasses that
    and exists only for inspecting a known-broken file -- never for producing a
    number. Anything computed under allow_invalid must not be reported.
    """
    res = validate(path, index_name, price_dir, expected_size)
    if not res.ok and not allow_invalid:
        raise MembershipError(
            f"{path} failed validation and will not be loaded.\n\n{res}\n\n"
            f"Fix the file rather than bypassing this. A number produced from an "
            f"invalid membership history looks more authoritative than the biased "
            f"one it replaces, which makes it worse.")
    df = _read_raw(path)
    lists = [_split(s) for s in df["symbols"]]
    excl = {d: _split(e) for d, e in zip(df["effective_date"], df["exclusions"])}
    return Membership(dates=list(df["effective_date"]), lists=lists,
                      exclusions=excl, source=str(path), validation=res)


# ---------------------------------------------------------------------------
# panel integration
# ---------------------------------------------------------------------------

def apply_to_panel(panel: pd.DataFrame, membership: Membership | None,
                   date_col="date", symbol_col="symbol") -> pd.DataFrame:
    """Restrict a long-format panel to point-in-time membership.

    In "static" mode this returns the panel unchanged, so the call can sit
    permanently in the pipeline. In "pit" mode it drops every (date, symbol) row
    where the symbol was not in the index on that date.

    PRICES ARE NOT DROPPED FROM THE EXECUTION PATH BY THIS FUNCTION. Apply it to
    the SCORE panel -- the set of names that may be ranked and bought. A name being
    sold after exclusion still needs its price on the sale date, and this project
    has already been bitten once by filtering prices for a non-price reason: the
    dropna(subset=FEATS_V2) that fed ffill and manufactured returns of up to
    +24,773%. Keep price and eligibility separate.
    """
    if not is_pit() or membership is None:
        return panel
    if panel.empty:
        return panel
    pos = membership._pos(panel[date_col])
    syms = panel[symbol_col].astype(str).str.upper().values
    keep = np.zeros(len(panel), dtype=bool)
    for i, (p, s) in enumerate(zip(pos, syms)):
        if p >= 0 and s in membership.lists[p]:
            keep[i] = True
    return panel[keep].copy()


def describe_state() -> str:
    """One line naming the current configuration, for logs and chart subtitles."""
    if not is_pit():
        return ("SURVIVORSHIP_MODE=static -- universe is today's members backfilled; "
                "results carry survivorship bias")
    return (f"SURVIVORSHIP_MODE=pit, EXIT_POLICY={EXIT_POLICY} -- universe is "
            f"point-in-time membership")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv):
    if len(argv) < 3:
        print(__doc__.split("COMMAND LINE")[1])
        return 1
    cmd, path = argv[1], argv[2]
    rest = argv[3:]
    price_dir = None
    if "--prices" in rest:
        price_dir = rest[rest.index("--prices") + 1]
    index_name = "nifty100"
    if "--index" in rest:
        index_name = rest[rest.index("--index") + 1]

    if cmd == "validate":
        print(validation_report(path, index_name, price_dir))
        return 0 if validate(path, index_name, price_dir).ok else 2

    if cmd == "members":
        if not rest:
            print("usage: survivorship.py members <file> <date>")
            return 1
        m = load(path, index_name, price_dir, allow_invalid=True)
        s = sorted(m.members_on(rest[0]))
        print(f"{len(s)} members on {rest[0]}:")
        for x in s:
            print(" ", x)
        return 0

    if cmd == "coverage":
        if price_dir is None:
            print("coverage needs --prices <dir>")
            return 1
        m = load(path, index_name, price_dir, allow_invalid=True)
        print(m.coverage_table(price_dir).to_string(index=False))
        return 0

    print(f"unknown command {cmd!r}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
