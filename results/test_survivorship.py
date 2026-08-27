"""
test_survivorship.py -- test suite for survivorship.py

Run it:
    python3 test_survivorship.py

Exit code 0 means every test passed. Non-zero means something is broken and the
module should not be trusted until it is fixed.

No pytest required -- it runs on a bare Python with pandas and numpy, so anyone
can check the module on their own machine without installing anything.

WHAT IS TESTED, AND WHY EACH TEST EXISTS

    Every test below corresponds to a way this module could silently produce a
    wrong backtest. The validation tests in particular are modelled on the real
    broken file this project received: 76 clean-looking rows that contained no
    RELIANCE. A test suite that only checked the happy path would have passed that
    file too.

    The most important property under test is the one that is easiest to lose in a
    refactor: static mode must be a byte-identical no-op. If someone edits this
    module and static mode starts filtering rows, every existing result in the
    project silently changes. test_static_mode_is_noop guards that.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import survivorship as sv


# ---------------------------------------------------------------------------
# tiny test harness
# ---------------------------------------------------------------------------

_PASS, _FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        _PASS.append(name)
    else:
        _FAIL.append((name, detail))


def section(title):
    print(f"\n--- {title} " + "-" * max(0, 62 - len(title)))


def run(name, fn):
    try:
        fn()
        print(f"  ok    {name}")
    except AssertionError as e:
        _FAIL.append((name, str(e)))
        print(f"  FAIL  {name}\n          {e}")
    except Exception as e:
        _FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ERROR {name}\n          {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

TMP = Path(tempfile.mkdtemp(prefix="surv_test_"))

ANCHORS = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "ITC", "SBIN"]


def write_csv(name, rows) -> str:
    p = TMP / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return str(p)


def valid_file() -> str:
    """A small but structurally correct membership history.

    Anchors present throughout, inclusions/exclusions consistent with the symbols
    column, three reconstitution dates with one change each."""
    base = ANCHORS + ["LT", "AXISBANK", "WIPRO"]
    r1 = list(base)
    r2 = [x for x in r1 if x != "WIPRO"] + ["MARUTI"]
    r3 = [x for x in r2 if x != "AXISBANK"] + ["TITAN"]
    return write_csv("valid.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r2),
         "inclusions": "MARUTI", "exclusions": "WIPRO"},
        {"effective_date": "2020-03-27", "symbols": ",".join(r3),
         "inclusions": "TITAN", "exclusions": "AXISBANK"},
    ])


def price_dir(symbols, name="prices") -> str:
    d = TMP / name
    d.mkdir(exist_ok=True)
    for s in symbols:
        (d / f"{s}.csv").write_text("date,close\n2019-01-01,100\n")
    return str(d)


# ---------------------------------------------------------------------------
# 1. validation -- the gate
# ---------------------------------------------------------------------------

def test_valid_file_passes():
    r = sv.validate(valid_file(), index_name="nifty100")
    assert r.ok, f"a structurally correct file failed: {r.errors}"
    assert not r.errors, f"unexpected errors: {r.errors}"


def test_missing_anchor_is_error():
    """The exact failure of the real broken file: an index history with no Reliance."""
    base = [a for a in ANCHORS if a != "RELIANCE"] + ["LT", "WIPRO"]
    p = write_csv("no_reliance.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "a file with no RELIANCE was accepted"
    assert any("RELIANCE" in e for e in r.errors), \
        f"the error does not name RELIANCE: {r.errors}"


def test_bond_ticker_is_error():
    """722HPCL29 is a debenture and appeared in the real broken file."""
    p = write_csv("bond.csv", [
        {"effective_date": "2019-03-29",
         "symbols": ",".join(ANCHORS + ["722HPCL29"]),
         "inclusions": "", "exclusions": ""}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "a file containing a bond was accepted"
    assert any("722HPCL29" in e for e in r.errors), \
        f"the error does not name the bond: {r.errors}"


def test_inconsistent_transitions_is_error():
    """symbols column disagrees with inclusions/exclusions."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    r2 = [x for x in r1 if x != "WIPRO"] + ["MARUTI"]
    p = write_csv("inconsistent.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        # claims nothing changed, but WIPRO left and MARUTI arrived
        {"effective_date": "2019-09-27", "symbols": ",".join(r2),
         "inclusions": "", "exclusions": ""}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "an internally inconsistent file was accepted"
    assert any("disagree" in e for e in r.errors), \
        f"the error does not mention the disagreement: {r.errors}"


def test_duplicate_dates_is_error():
    row = {"effective_date": "2019-03-29", "symbols": ",".join(ANCHORS),
           "inclusions": "", "exclusions": ""}
    p = write_csv("dupes.csv", [row, dict(row)])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "duplicate effective_date rows were accepted"


def test_unparseable_date_raises():
    p = write_csv("baddate.csv", [
        {"effective_date": "not-a-date", "symbols": ",".join(ANCHORS),
         "inclusions": "", "exclusions": ""}])
    try:
        sv.validate(p, index_name="nifty100")
    except sv.MembershipError:
        return
    raise AssertionError("an unparseable date did not raise")


def test_missing_required_column_raises():
    p = write_csv("nocol.csv", [{"date": "2019-03-29", "names": "RELIANCE"}])
    try:
        sv.validate(p, index_name="nifty100")
    except sv.MembershipError as e:
        assert "effective_date" in str(e), f"error should name the missing column: {e}"
        return
    raise AssertionError("a file missing required columns did not raise")


def test_load_raises_on_invalid():
    base = [a for a in ANCHORS if a != "RELIANCE"]
    p = write_csv("load_invalid.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    try:
        sv.load(p, index_name="nifty100")
    except sv.MembershipError:
        return
    raise AssertionError("load() accepted a file that failed validation")


def test_allow_invalid_bypasses():
    """The escape hatch must work, for inspecting a broken file."""
    base = [a for a in ANCHORS if a != "RELIANCE"]
    p = write_csv("bypass.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    m = sv.load(p, index_name="nifty100", allow_invalid=True)
    assert not m.validation.ok, "validation result should still record the failure"


def test_index_with_no_anchors_skips_that_check():
    """midcap150 has no guaranteed-present name; the check must not fire."""
    p = write_csv("midcap.csv", [
        {"effective_date": "2019-03-29", "symbols": "SUZLON,LLOYDSME,AIIL",
         "inclusions": "", "exclusions": ""}])
    r = sv.validate(p, index_name="midcap150")
    assert r.ok, f"midcap file rejected despite no anchors defined: {r.errors}"


def test_price_coverage_is_warning_not_error():
    p = valid_file()
    pd_dir = price_dir(["RELIANCE", "INFY"])       # deliberately incomplete
    r = sv.validate(p, index_name="nifty100", price_dir=pd_dir)
    assert r.ok, "incomplete price coverage must not fail the file"
    assert any("no price file" in w for w in r.warnings), \
        f"coverage gap not reported as a warning: {r.warnings}"
    assert any("RESIDUAL SURVIVORSHIP" in w for w in r.warnings), \
        "the residual-bias disclosure is missing"


# ---------------------------------------------------------------------------
# 2. members_on -- the lookup
# ---------------------------------------------------------------------------

def test_members_on_before_first_date_is_empty():
    m = sv.load(valid_file())
    assert m.members_on("2018-01-01") == set(), \
        "membership before the history starts must be empty, not the first list"


def test_members_on_exact_boundary_is_inclusive():
    """On the effective date itself, the NEW list applies."""
    m = sv.load(valid_file())
    on = m.members_on("2019-09-27")
    assert "MARUTI" in on, "the inclusion is not active on its own effective date"
    assert "WIPRO" not in on, "the exclusion is still present on its effective date"


def test_members_on_day_before_boundary():
    m = sv.load(valid_file())
    on = m.members_on("2019-09-26")
    assert "WIPRO" in on, "a name was removed a day early"
    assert "MARUTI" not in on, "a name was added a day early"


def test_members_on_after_last_date_carries_forward():
    m = sv.load(valid_file())
    assert m.members_on("2030-01-01") == m.members_on("2020-03-27"), \
        "the last known membership must carry forward"


def test_is_member_is_case_insensitive():
    m = sv.load(valid_file())
    assert m.is_member("reliance", "2019-06-01"), "lowercase symbol not matched"
    assert m.is_member("RELIANCE", "2019-06-01")


def test_whitespace_in_symbols_is_stripped():
    p = write_csv("spaces.csv", [
        {"effective_date": "2019-03-29",
         "symbols": " RELIANCE , INFY ,TCS,HDFCBANK,ICICIBANK,ITC,SBIN ",
         "inclusions": "", "exclusions": ""}])
    m = sv.load(p)
    assert "RELIANCE" in m.members_on("2019-06-01"), "whitespace broke the parse"
    assert " RELIANCE " not in m.members_on("2019-06-01")


# ---------------------------------------------------------------------------
# 3. forced_exits -- the exit policy
# ---------------------------------------------------------------------------

def test_forced_exit_sells_excluded_name():
    m = sv.load(valid_file())
    sv.set_exit_policy("forced")
    out = m.forced_exits({"RELIANCE", "WIPRO", "INFY"}, "2019-10-01")
    assert out == {"WIPRO"}, f"expected WIPRO forced out, got {out}"


def test_forced_exit_keeps_current_members():
    m = sv.load(valid_file())
    sv.set_exit_policy("forced")
    out = m.forced_exits({"RELIANCE", "INFY", "TCS"}, "2019-10-01")
    assert out == set(), f"current members were forced out: {out}"


def test_buffer_policy_returns_empty():
    m = sv.load(valid_file())
    sv.set_exit_policy("buffer")
    out = m.forced_exits({"RELIANCE", "WIPRO"}, "2019-10-01")
    assert out == set(), f"buffer policy must not force exits, got {out}"
    sv.set_exit_policy("forced")


def test_forced_exit_before_history_is_empty():
    """With no membership defined, nothing can be forced out."""
    m = sv.load(valid_file())
    sv.set_exit_policy("forced")
    out = m.forced_exits({"RELIANCE", "WIPRO"}, "2018-01-01")
    assert out == set(), "names were force-sold on a date with no membership"


# ---------------------------------------------------------------------------
# 4. the switch -- static must be a no-op
# ---------------------------------------------------------------------------

def _panel():
    return pd.DataFrame({
        "date": pd.to_datetime(["2019-10-01"] * 3 + ["2019-06-01"] * 3),
        "symbol": ["RELIANCE", "WIPRO", "MARUTI"] * 2,
        "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    })


def test_static_mode_is_noop():
    """The property that protects every existing result in the project."""
    m = sv.load(valid_file())
    sv.set_mode("static")
    p = _panel()
    out = sv.apply_to_panel(p, m)
    assert out.equals(p), "static mode altered the panel"
    assert len(out) == len(p), f"static mode dropped rows: {len(p)} -> {len(out)}"


def test_static_mode_noop_even_with_no_membership():
    sv.set_mode("static")
    p = _panel()
    assert sv.apply_to_panel(p, None).equals(p), \
        "static mode with no membership altered the panel"


def test_pit_mode_filters_correctly():
    m = sv.load(valid_file())
    sv.set_mode("pit")
    out = sv.apply_to_panel(_panel(), m)
    got = set(zip(out["date"].dt.strftime("%Y-%m-%d"), out["symbol"]))
    expect = {("2019-10-01", "RELIANCE"), ("2019-10-01", "MARUTI"),
              ("2019-06-01", "RELIANCE"), ("2019-06-01", "WIPRO")}
    assert got == expect, f"pit filter wrong.\n  got    {sorted(got)}\n  expect {sorted(expect)}"
    sv.set_mode("static")


def test_pit_mode_with_none_membership_is_noop():
    """Guards against a crash if the switch is on but no file was loaded."""
    sv.set_mode("pit")
    p = _panel()
    assert sv.apply_to_panel(p, None).equals(p), \
        "pit mode with membership=None should pass through, not crash"
    sv.set_mode("static")


def test_empty_panel_survives():
    m = sv.load(valid_file())
    sv.set_mode("pit")
    empty = pd.DataFrame({"date": pd.Series([], dtype="datetime64[ns]"),
                          "symbol": pd.Series([], dtype=str)})
    assert len(sv.apply_to_panel(empty, m)) == 0, "empty panel broke the filter"
    sv.set_mode("static")


def test_apply_to_panel_does_not_mutate_input():
    m = sv.load(valid_file())
    sv.set_mode("pit")
    p = _panel()
    before = p.copy()
    sv.apply_to_panel(p, m)
    assert p.equals(before), "apply_to_panel mutated its input"
    sv.set_mode("static")


# ---------------------------------------------------------------------------
# 5. eligible_mask
# ---------------------------------------------------------------------------

def test_eligible_mask_shape_and_values():
    m = sv.load(valid_file())
    dates = pd.to_datetime(["2019-06-01", "2019-10-01"])
    syms = ["RELIANCE", "WIPRO", "MARUTI"]
    mask = m.eligible_mask(dates, syms)
    assert mask.shape == (2, 3), f"wrong shape {mask.shape}"
    assert bool(mask.loc["2019-06-01", "WIPRO"]), "WIPRO should be eligible in June"
    assert not bool(mask.loc["2019-10-01", "WIPRO"]), "WIPRO eligible after exclusion"
    assert bool(mask.loc["2019-10-01", "MARUTI"]), "MARUTI not eligible after inclusion"
    assert not bool(mask.loc["2019-06-01", "MARUTI"]), "MARUTI eligible before inclusion"


def test_eligible_mask_before_history_all_false():
    m = sv.load(valid_file())
    mask = m.eligible_mask(pd.to_datetime(["2018-01-01"]), ["RELIANCE"])
    assert not mask.values.any(), "names eligible before the history starts"


def test_eligible_mask_unknown_symbol_is_false():
    m = sv.load(valid_file())
    mask = m.eligible_mask(pd.to_datetime(["2019-10-01"]), ["NOTALISTEDNAME"])
    assert not mask.values.any(), "an unknown symbol was marked eligible"


# ---------------------------------------------------------------------------
# 6. switches and reporting
# ---------------------------------------------------------------------------

def test_set_mode_rejects_bad_value():
    try:
        sv.set_mode("sometimes")
    except ValueError:
        assert sv.SURVIVORSHIP_MODE in ("static", "pit"), "mode was corrupted"
        return
    raise AssertionError("set_mode accepted an invalid value")


def test_set_exit_policy_rejects_bad_value():
    try:
        sv.set_exit_policy("maybe")
    except ValueError:
        return
    raise AssertionError("set_exit_policy accepted an invalid value")


def test_describe_state_names_the_bias_in_static():
    sv.set_mode("static")
    s = sv.describe_state()
    assert "static" in s and "survivorship bias" in s, \
        f"static mode must disclose the bias on its face: {s!r}"


def test_describe_state_names_policy_in_pit():
    sv.set_mode("pit")
    sv.set_exit_policy("forced")
    s = sv.describe_state()
    assert "pit" in s and "forced" in s, f"pit state under-described: {s!r}"
    sv.set_mode("static")


def test_coverage_table():
    m = sv.load(valid_file())
    d = price_dir(["RELIANCE", "INFY", "TCS"], name="cov")
    t = m.coverage_table(d)
    assert len(t) == 3, f"expected one row per effective date, got {len(t)}"
    assert set(t.columns) == {"effective_date", "members", "with_price", "coverage_pct"}
    assert (t["with_price"] == 3).all(), "coverage count wrong"


# ---------------------------------------------------------------------------
# 7. date format handling
# ---------------------------------------------------------------------------

def test_iso_and_dayfirst_both_parse():
    """The project's CSVs mix 27-01-2003 and 3/2/2003 in one column."""
    p = write_csv("dayfirst.csv", [
        {"effective_date": "29-03-2019", "symbols": ",".join(ANCHORS),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "27-09-2019", "symbols": ",".join(ANCHORS + ["LT"]),
         "inclusions": "LT", "exclusions": ""}])
    m = sv.load(p)
    assert m.dates[0] == pd.Timestamp("2019-03-29"), \
        f"day-first date misparsed: {m.dates[0]}"
    assert m.dates[1] == pd.Timestamp("2019-09-27")


def test_searchsorted_works_across_pandas_versions():
    """Regression: np.searchsorted against a LIST of Timestamps raises
    "'<' not supported between instances of 'Timestamp' and 'int'" on some
    pandas/numpy combinations and silently works on others. This suite passed on
    pandas 3.0.2 and failed five tests on an older build. Membership now compares
    against a datetime64 array, so the behaviour is environment-independent.

    Exercises every array-valued lookup path with a variety of date containers."""
    m = sv.load(valid_file())
    containers = [
        pd.DatetimeIndex(["2019-06-01", "2019-10-01"]),
        pd.Series(pd.to_datetime(["2019-06-01", "2019-10-01"])),
        ["2019-06-01", "2019-10-01"],
        pd.to_datetime(["2019-06-01", "2019-10-01"]).values,
    ]
    for c in containers:
        pos = m._pos(c)
        assert list(pos) == [0, 1], f"wrong positions for {type(c).__name__}: {pos}"
        mask = m.eligible_mask(pd.DatetimeIndex(pd.to_datetime(c)), ["RELIANCE"])
        assert mask.values.all(), f"mask failed for {type(c).__name__}"
    sv.set_mode("pit")
    out = sv.apply_to_panel(_panel(), m)
    assert len(out) == 4, f"apply_to_panel wrong after fix: {len(out)}"
    sv.set_mode("static")


def test_dates_are_sorted_regardless_of_file_order():
    p = write_csv("unsorted.csv", [
        {"effective_date": "2020-03-27", "symbols": ",".join(ANCHORS + ["TITAN"]),
         "inclusions": "TITAN", "exclusions": ""},
        {"effective_date": "2019-03-29", "symbols": ",".join(ANCHORS),
         "inclusions": "", "exclusions": ""}])
    m = sv.load(p, allow_invalid=True)
    assert m.dates == sorted(m.dates), "dates not sorted after load"
    assert "TITAN" not in m.members_on("2019-06-01"), \
        "out-of-order rows produced a wrong lookup"


# ---------------------------------------------------------------------------
# 8. golden test -- the real broken file
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# gate: one synthetic fixture per error class
#
# THESE REPLACED A TEST THAT READ A FILE OFF DISK.
#     The old `golden: the real broken file still fails` searched for
#     data/raw/N100_Survivorship/index_membership_nifty100.csv and asserted that
#     three specific errors fired on whatever it found. That silently assumed the
#     file at that path would always be the ORIGINAL broken one. When a second,
#     differently-broken file was placed there -- all seven anchors present,
#     RELIANCE on 50 of 50 dates -- the missing-anchor assertion failed and the
#     suite reported 38/39. The module was fine; the test was coupled to a file
#     that changed underneath it.
#
#     A test that reads whatever happens to be at a path is not a regression test:
#     it cannot fail for a reason you control, and it cannot tell you which error
#     class regressed. Each fixture below is built in-process and exercises exactly
#     ONE failure mode, so a failure names the defect.
# ---------------------------------------------------------------------------

def test_gate_missing_anchor():
    """A Nifty 100 history with no RELIANCE anywhere."""
    syms = [a for a in ANCHORS if a != "RELIANCE"] + ["LT", "WIPRO"]
    p = write_csv("gate_anchor.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(syms),
         "inclusions": "", "exclusions": ""}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "a Nifty 100 history without RELIANCE was accepted"
    assert any("RELIANCE" in e and "anchor" in e for e in r.errors), \
        f"missing-anchor error did not fire: {r.errors}"


def test_gate_non_equity_ticker():
    """A debenture identifier among the constituents."""
    p = write_csv("gate_bond.csv", [
        {"effective_date": "2019-03-29",
         "symbols": ",".join(ANCHORS + ["722HPCL29"]),
         "inclusions": "", "exclusions": ""}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "a file containing a debenture was accepted"
    assert any("722HPCL29" in e for e in r.errors), \
        f"non-equity error did not fire: {r.errors}"


def test_gate_inconsistent_transitions():
    """symbols contradicts inclusions/exclusions: list[t] != list[t-1]+inc-exc."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    r2 = ANCHORS + ["LT", "WIPRO", "MARUTI", "TITAN"]   # TITAN is not declared
    p = write_csv("gate_transition.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r2),
         "inclusions": "MARUTI", "exclusions": ""}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "a self-contradicting file was accepted"
    assert any("disagree" in e for e in r.errors), \
        f"transition-consistency error did not fire: {r.errors}"


def test_gate_cumulative_list():
    """Each row a superset of the last, growing from ~100 to ~800 names.

    This is the defect in the second real file: the generating script adds
    inclusions without ever removing exclusions, so the 'membership' becomes a
    running total of everyone who was ever in the index."""
    cur = ANCHORS + [f"EQ{i:03d}" for i in range(93)]
    rows, start = [], len(cur)
    for i in range(20):
        add = [f"ADD{i:02d}{j:02d}" for j in range(35)]
        cur = cur + add
        rows.append({"effective_date": f"{2006+i}-03-31", "symbols": ",".join(cur),
                     "inclusions": ",".join(add), "exclusions": ""})
    assert start == 100 and len(cur) > 750, \
        f"fixture does not span ~100 -> ~800 names: {start} -> {len(cur)}"
    r = sv.validate(write_csv("gate_cumulative.csv", rows), index_name="nifty100")
    assert not r.ok, "a cumulative file was accepted"
    assert any("CUMULATIVE" in e for e in r.errors), \
        f"cumulative error did not fire: {r.errors}"


def test_gate_exclusion_not_removed():
    """A name in `exclusions` is still present in the same row's `symbols`."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    p = write_csv("gate_exclusion.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": "WIPRO"}])
    r = sv.validate(p, index_name="nifty100")
    assert not r.ok, "an unremoved exclusion was accepted"
    assert any("STILL in the" in e for e in r.errors), \
        f"exclusion-not-removed error did not fire: {r.errors}"


# --- the two false positives that the cumulative check used to produce --------

def test_cumulative_does_not_fire_on_stable_history():
    """A membership that barely changes is not a running total.

    Consecutive rows are IDENTICAL here, and a set is a superset of itself. The
    first version of the check counted that as evidence of accumulation and
    reported a file growing 'from 100 to 100 names' as cumulative."""
    cur = ANCHORS + [f"EQ{i:03d}" for i in range(93)]
    rows = []
    for i in range(12):
        inc = exc = ""
        if i and i % 4 == 0:
            exc = cur[-1]; cur = cur[:-1] + [f"NEW{i}"]; inc = f"NEW{i}"
        rows.append({"effective_date": f"{2010+i}-03-31", "symbols": ",".join(cur),
                     "inclusions": inc, "exclusions": exc})
    r = sv.validate(write_csv("stable.csv", rows), index_name="nifty100")
    assert not any("CUMULATIVE" in e for e in r.errors), \
        f"cumulative error fired on a stable legitimate history: {r.errors}"


def test_cumulative_does_not_fire_on_genuine_index_expansion():
    """A real Nifty 50 -> Nifty 100 style widening must not read as accumulation.

    Every transition is a non-strict superset, which is why the first version of
    the check fired at 11 of 11. The distinguishing facts are that the growth
    happens in ONE step rather than being sustained across reconstitutions."""
    n50 = ANCHORS + [f"EQ{i:03d}" for i in range(43)]
    n100 = n50 + [f"EX{i:03d}" for i in range(50)]
    rows = [{"effective_date": f"{2010+i}-03-31",
             "symbols": ",".join(n50 if i < 6 else n100),
             "inclusions": ",".join(f"EX{j:03d}" for j in range(50)) if i == 6 else "",
             "exclusions": ""} for i in range(12)]
    r = sv.validate(write_csv("expansion.csv", rows), index_name="nifty100")
    assert not any("CUMULATIVE" in e for e in r.errors), \
        f"cumulative error fired on a genuine index expansion: {r.errors}"


def test_exclusion_check_allows_same_date_removal_and_readd():
    """A name in BOTH inclusions and exclusions on one date is not a defect."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    p = write_csv("readd.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r1),
         "inclusions": "WIPRO", "exclusions": "WIPRO"}])
    r = sv.validate(p, index_name="nifty100")
    assert not any("STILL in the" in e for e in r.errors), \
        f"same-date removal and re-add was reported as a defect: {r.errors}"
    assert any("re-added" in w for w in r.warnings), \
        f"a single same-date re-add should still be disclosed as a warning: {r.warnings}"


def test_routine_inclusion_exclusion_collision_is_an_error():
    """One same-date remove-and-re-add is plausible; dozens are a merge bug.

    This is what the second real file does: 45 of its 114 exclusion entries name a
    symbol the same row also lists as an inclusion. Guarding the unremoved-exclusion
    check against that case is correct, but it must not make the symptom invisible."""
    r1 = ANCHORS + ["LT", "WIPRO", "MARUTI", "TITAN"]
    rows = [{"effective_date": "2019-03-29", "symbols": ",".join(r1),
             "inclusions": "", "exclusions": ""}]
    for i, s in enumerate(("WIPRO", "MARUTI", "TITAN", "LT")):
        rows.append({"effective_date": f"{2020+i}-03-29", "symbols": ",".join(r1),
                     "inclusions": s, "exclusions": s})
    r = sv.validate(write_csv("collision.csv", rows), index_name="nifty100")
    assert not r.ok, "routine inclusion/exclusion collisions were accepted"
    assert any("also lists as an inclusion" in e for e in r.errors), \
        f"collision error did not fire: {r.errors}"


# --- the non-equity rule, against real tickers -------------------------------

def test_digit_leading_equities_are_not_rejected():
    """Real NSE equities that begin with digits must pass.

    The first version of _looks_non_equity rejected anything starting with a
    digit, which is wrong: these are all ordinary listed equities."""
    for sym in ("3MINDIA", "8KMILES", "5PAISA", "63MOONS", "20MICRONS",
                "21STCENMGM", "3IINFOLTD", "360ONE", "3PLAND"):
        assert not sv._looks_non_equity(sym), f"{sym} is a real NSE equity"


def test_debt_identifiers_are_rejected():
    """Coupon-prefixed debt, and issuer-plus-four-digit-year debt."""
    for sym in ("722HPCL29", "828GS2027", "1025GOI30", "685NHAI29",
                "795HDFC28", "760IRFC30", "GS2027"):
        assert sv._looks_non_equity(sym), f"{sym} is a debt identifier"


def test_ordinary_equities_are_not_rejected():
    """Including the punctuation and digit forms that appear in real files."""
    for sym in ("RELIANCE", "TCS", "INFY", "HDFCBANK", "TV18BRDCST", "M&M",
                "L&TFH", "IDFCFIRSTB", "BAJAJ-AUTO", "MOTHERSON"):
        assert not sv._looks_non_equity(sym), f"{sym} is a real NSE equity"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

TESTS = [
    ("validation: valid file passes", test_valid_file_passes),
    ("validation: missing anchor is an error", test_missing_anchor_is_error),
    ("validation: bond ticker is an error", test_bond_ticker_is_error),
    ("validation: inconsistent transitions are an error", test_inconsistent_transitions_is_error),
    ("validation: duplicate dates are an error", test_duplicate_dates_is_error),
    ("validation: unparseable date raises", test_unparseable_date_raises),
    ("validation: missing column raises", test_missing_required_column_raises),
    ("validation: load() raises on invalid", test_load_raises_on_invalid),
    ("validation: allow_invalid bypasses", test_allow_invalid_bypasses),
    ("validation: index with no anchors skips check", test_index_with_no_anchors_skips_that_check),
    ("validation: price coverage is a warning", test_price_coverage_is_warning_not_error),

    ("members_on: before history is empty", test_members_on_before_first_date_is_empty),
    ("members_on: effective date is inclusive", test_members_on_exact_boundary_is_inclusive),
    ("members_on: day before boundary", test_members_on_day_before_boundary),
    ("members_on: after last date carries forward", test_members_on_after_last_date_carries_forward),
    ("members_on: case insensitive", test_is_member_is_case_insensitive),
    ("members_on: whitespace stripped", test_whitespace_in_symbols_is_stripped),

    ("exits: forced sells excluded name", test_forced_exit_sells_excluded_name),
    ("exits: forced keeps current members", test_forced_exit_keeps_current_members),
    ("exits: buffer policy returns empty", test_buffer_policy_returns_empty),
    ("exits: before history is empty", test_forced_exit_before_history_is_empty),

    ("switch: STATIC IS A NO-OP", test_static_mode_is_noop),
    ("switch: static no-op with no membership", test_static_mode_noop_even_with_no_membership),
    ("switch: pit filters correctly", test_pit_mode_filters_correctly),
    ("switch: pit with membership=None passes through", test_pit_mode_with_none_membership_is_noop),
    ("switch: empty panel survives", test_empty_panel_survives),
    ("switch: does not mutate input", test_apply_to_panel_does_not_mutate_input),

    ("mask: shape and values", test_eligible_mask_shape_and_values),
    ("mask: before history all false", test_eligible_mask_before_history_all_false),
    ("mask: unknown symbol is false", test_eligible_mask_unknown_symbol_is_false),

    ("config: set_mode rejects bad value", test_set_mode_rejects_bad_value),
    ("config: set_exit_policy rejects bad value", test_set_exit_policy_rejects_bad_value),
    ("config: static state discloses bias", test_describe_state_names_the_bias_in_static),
    ("config: pit state names the policy", test_describe_state_names_policy_in_pit),
    ("config: coverage table", test_coverage_table),

    ("dates: iso and day-first both parse", test_iso_and_dayfirst_both_parse),
    ("dates: sorted regardless of file order", test_dates_are_sorted_regardless_of_file_order),
    ("dates: searchsorted works across pandas versions", test_searchsorted_works_across_pandas_versions),

    # One synthetic fixture per error class. No test in this suite reads a file it
    # did not create -- see the note above test_gate_missing_anchor.
    ("gate: missing anchor", test_gate_missing_anchor),
    ("gate: non-equity ticker", test_gate_non_equity_ticker),
    ("gate: inconsistent transitions", test_gate_inconsistent_transitions),
    ("gate: cumulative list", test_gate_cumulative_list),
    ("gate: exclusion not removed", test_gate_exclusion_not_removed),

    ("falsepos: cumulative quiet on stable history",
     test_cumulative_does_not_fire_on_stable_history),
    ("falsepos: cumulative quiet on genuine expansion",
     test_cumulative_does_not_fire_on_genuine_index_expansion),
    ("falsepos: same-date removal and re-add allowed",
     test_exclusion_check_allows_same_date_removal_and_readd),
    ("gate: routine inc/exc collision is an error",
     test_routine_inclusion_exclusion_collision_is_an_error),

    ("tickers: digit-leading equities pass", test_digit_leading_equities_are_not_rejected),
    ("tickers: debt identifiers rejected", test_debt_identifiers_are_rejected),
    ("tickers: ordinary equities pass", test_ordinary_equities_are_not_rejected),
]


def main():
    print("=" * 74)
    print(" SURVIVORSHIP MODULE -- TEST SUITE")
    print("=" * 74)
    last = None
    for name, fn in TESTS:
        head = name.split(":")[0]
        if head != last:
            section(head)
            last = head
        run(name, fn)

    print("\n" + "=" * 74)
    total = len(TESTS)
    failed = len(_FAIL)
    print(f"  {total - failed} passed, {failed} failed, of {total}")
    if _FAIL:
        print("\n  FAILURES:")
        for n, d in _FAIL:
            print(f"    {n}\n      {d}")
        print("\n  The module must not be used until these pass.")
    else:
        print("\n  All tests passed. Static mode is a verified no-op, the validation")
        print("  gate rejects each failure mode and passes legitimate files, and the")
        print("  point-in-time lookup is correct at its boundaries.")
    print("=" * 74)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
