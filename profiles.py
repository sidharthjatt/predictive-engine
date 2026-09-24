"""profiles.py -- the execution-realism profile this run selected.

TWO PROFILES, NOT A BARE PARAMETER
    research   participation_cap = None   (the default)
    tradeable  participation_cap = 1.00

WHY A PROFILE AND NOT A NUMBER
    A single default cannot serve both readers. `research` must reproduce the
    published history EXACTLY -- it is what every gate and every document compares
    against, and v34_comparison.csv is byte-identical under it. `tradeable` is the
    question "what does this return if I can actually transact", and it should be
    one flag rather than a number somebody has to remember to pass.

WHY THIS IS SEPARATE FROM THE DATA GUARDS
    The interior-gap guard (results/tradability.py) corrects something that is
    WRONG: a fill at a price that did not trade. There is no version of the
    strategy that wanted it, so it applies unconditionally.

    The participation cap is different in kind. Nothing in the data is wrong when
    AIIL fills at 2,131% of its median volume -- the price is real and the date is
    real. What is wrong is that the backtest was never told it could not transact
    that size. Capping makes the number more REALISTIC, but it also changes what
    strategy is being measured, so it is opt-in.

WHY THIS IS NOT A MODULE GLOBAL ON test_exposure
    cadence.py records the hazard by file and line: rebal_cadence_sweep.py set
    test_exposure.REBAL and never restored it, so every later in-process step would
    have backtested the wrong cadence with nothing to say so. The cap is recorded
    here and handed to backtest_exposure as an ARGUMENT. A parameter cannot leak
    into the next step; a global can, and once did.

WHAT THE CAP MEANS
    A BUY is capped at `participation_cap` x the symbol's prior-20-session MEDIAN
    volume. Prior, so the cap never uses the day's own volume. Median rather than
    mean, because a single block trade should not licence a large fill.

    THE REMAINDER STAYS IN CASH. It is not reallocated to the next name -- that
    would change SELECTION and make the cap a strategy redesign rather than a
    realism constraint -- and it is not carried to the next session, which would
    need an order-state concept the engine does not have.

    Measured consequence, and it is the opposite of the obvious guess: capping
    INCREASES the mean number of names held (midcap150 v3 7.60 -> 7.72) and REDUCES
    cash-short skips (131 -> 123). The cap partially relieves the funding defect
    rather than compounding it.

    THAT DIRECTION HAS TWO SOURCES, NOT ONE. CORRECTED 2026-09-23. This paragraph
    used to end "...because the buy loop runs in score-descending order and
    shrinking an early oversized name frees cash for the tail it used to drop",
    naming one channel as the whole explanation. It predicted the right direction
    from an incomplete mechanism, which is worse than saying nothing: a correct
    prediction reads as confirmation and nobody looks again.

    CHANNEL 2 -- THE TAIL. The buy loop runs in score-descending order, so
    shrinking an early oversized name frees cash for names further down that the
    loop used to drop. This is the one this paragraph named.

    CHANNEL 3 -- AFFORDABILITY. The shrink does not free money for a LATER name; it
    brings THIS name inside the budget. A capped order can cost less than the cash
    on hand when the uncapped order cost more, so an order the research run refused
    for cash executes under the cap.

        nifty100 v1, 2019-01-30. Both runs intend 3,373 VBL shares against a
        2,312-share prior-20-session median, 145.9% of it.
          research:  needs Rs 158,161, has Rs 109,926 -> cash short, no fill.
          tradeable: capped to 2,312 sh = Rs 108,410  -> BUYS.
        The research run never holds VBL that day. The capped run does, and that
        cell finishes AHEAD of its twin: CAGR 25.77 -> 25.88.

    SO THE TRADEABLE PROFILE IS NOT A COST-ONLY TRANSFORM OF THE RESEARCH RUN. It
    changes which trades happen, in both directions. Measured over the full
    universe x arm grid on 2026-09-23 from runs of 2026-09-22: of 32 cells, 7
    diverge from their research twin; 3 of those 7 contain at least one channel-3
    bind, and 4 of the 16 binds across them are channel 3. One of the 7 finishes
    ahead. Channel 3 does NOT imply a gain -- two of the three cells carrying it
    finish behind. Those are counts on one date at the backtest's Rs 10,00,000, not
    properties of the cap.

    THE REMAINDER RULE (channel 1) IS UNCHANGED BY ANY OF THIS. Nothing is
    reallocated and nothing is carried forward; channels 2 and 3 are both about
    cash that was already there.
    """

PROFILES = {
    "research":  {"participation_cap": None},
    "tradeable": {"participation_cap": 1.00},
}
DEFAULT = "research"

_SELECTED = None


def set_selection(name):
    """Record this run's profile. Called once by run.py. None restores the default."""
    global _SELECTED
    if name is None:
        _SELECTED = None
        return
    if name not in PROFILES:
        raise ValueError(f"unknown profile {name!r}; known: {', '.join(PROFILES)}")
    _SELECTED = name


def selected():
    return DEFAULT if _SELECTED is None else _SELECTED


def is_default():
    return selected() == DEFAULT


def participation_cap():
    """The cap as a fraction of prior-20-session median volume, or None."""
    return PROFILES[selected()]["participation_cap"]


def cap_kwargs(u):
    """The participation-cap keywords for backtest_exposure on universe `u`.

    {"participation_cap": None} under research; the cap plus vol20 -- the
    prior-20-session median volume from the universe's own farm -- otherwise.
    ALWAYS CARRIES THE CAP, EVEN WHEN None: backtest_exposure refuses to guess
    which profile a caller meant.

    ONE DEFINITION, 2026-09-23. v34_common (twice), engine_v2_final and
    audit_step each built this dict by hand, and bh_lots_after_tax built it
    without vol20, so `--tax on --profile tradeable` died at STEP 17h on every
    universe. The engines and the audit must read the volume from the same place
    by the same call, which is now true by construction.
    """
    cap = participation_cap()
    if cap is None:
        return {"participation_cap": None}
    import config as _cfg
    import tradability as _tr
    from engine_core import _load_calendar
    return {"participation_cap": cap,
            "vol20": _tr.median_volume(u.prepare_data_dir(), _load_calendar(),
                                       _cfg.BT_START_DATE, _cfg.BT_END_DATE)}


def research_only(caller):
    """Declare that `caller` measures the research profile, and REFUSE if the run
    selected another one. Returns the research cap, which is None.

    WHY A DECLARATION AND NOT JUST `participation_cap=None`. Thirteen measurement
    tools passed `participation_cap()` and never passed the `vol20` the cap needs,
    so under `tradeable` they would have measured research and labelled it
    tradeable. They never did, but only because the profile axis cannot reach them
    today: none is in PIPELINE_ORDER, none accepts --profile, none calls
    set_selection, and no load-bearing module imports them. Verified 2026-09-15,
    all four routes.

    THOSE ARE PROPERTIES OF TODAY'S TREE, AND THE TREE IS BEING REWRITTEN. Safe by
    construction lasts until someone adds a flag; safe by declaration lasts. A tool
    that says `research_only(__name__)` and is later handed `--profile tradeable`
    STOPS, and the message names it. A tool that merely passes None goes on quietly
    measuring research under a tradeable label -- which is the whole defect, moved
    one file along.

    Use this ONLY where research is the intended measurement. A caller that should
    honour the selected profile passes participation_cap() and the vol20 that goes
    with it; see backtest_exposure's refusal.
    """
    if selected() != DEFAULT:
        raise SystemExit(
            f"{caller} is declared research-only, but this run selected "
            f"profile '{selected()}'.\n"
            f"  It passes no vol20, so the participation cap could not be applied "
            f"even though the profile asks for it, and the result would be a "
            f"research measurement wearing a '{selected()}' label.\n"
            f"  Either run it without --profile, or give it the vol20 that "
            f"backtest_exposure needs and drop this declaration.")
    return PROFILES[DEFAULT]["participation_cap"]


# ---------------------------------------------------------------------------
# A NON-RESEARCH PROFILE IS UNGATED, AND MUST SAY SO WHEREVER IT PUBLISHES
# ---------------------------------------------------------------------------
# `--profile tradeable` could not complete until 2026-09-16; the input guard
# blocked STEP 16. It completes now. THAT IS NOT THE SAME AS BEING VERIFIED, and
# the distance between the two is exactly the kind a reader closes by accident:
# a run that finishes, writes every artefact and exits 0 looks like a run that was
# checked.
#
# IT HAS NEVER BEEN CHECKED. gate_compare.STANDING_GATE's two tradeable cells are
# [PARTIAL] and stop at STEP 10d/12b/15b; STEP 16 and STEP 17 had never executed
# under this profile before 2026-09-16, and no cell compares what they produce
# against anything. Until a gate cell exists, every tradeable number is a number
# nothing has replayed.
#
# SO THE STATEMENT TRAVELS WITH THE NUMBERS, not just with the run: run.py banners
# it at the start and end of a non-default-profile run, and v34_common writes it
# into v34_params{SFX}.json. One definition here so the two cannot drift, and so
# deleting the caveat is one edit that shows up in a diff rather than three.
UNGATED_NOTICE = (
    "UNGATED: no gate cell covers this profile. It completes end to end, which is "
    "not the same as being verified -- STEP 16 and STEP 17 first ran under it on "
    "2026-09-16 and nothing replays what they produce. Do not publish these "
    "numbers as checked."
)

# A TRADEABLE FILENAME DOES NOT MEAN THE CAP CHANGED ANYTHING. Measured 2026-09-20
# at commit 7dd37d6, and the wording is deliberate: this is what the cap did on
# those runs, not a property of the cap or of the universe.
#
# On midcap150 the cap fired on NO fill in either arm. daily_skipped_midcap150_v1_
# tradeable.csv and daily_skipped_midcap150_tradeable.csv carry zero rows with
# reason "participation cap" (n=850 and n=1006 fills). The highest participation
# any fill reached was 0.709 of its prior-20-session median on v1 and 0.345 on v2,
# against a cap of 1.00. All eight of {trades, skipped, holdings, summary} x {v1,
# v2} are BYTE-IDENTICAL to their unsuffixed research twins.
#
# nifty100 was already recorded as inert in KNOWN_ISSUES.md. So as of this commit
# neither published universe has a run in which the cap bound.
#
# THIS IS A DATED MEASUREMENT AND IT WILL ROT. It depends on the capital, the
# universe and the data, all of which move. Re-measure by counting "participation
# cap" rows in the run's own daily_skipped artefact; do not carry this sentence
# forward on trust.
# RE-MEASURED 2026-09-22, WITH THE SELL SIDE NOW CAPPED TOO. The notice below was
# written when only BUYs were capped. Both sides are capped as of 2026-09-22, and
# at cap=1.00 the cap still binds on NO fill of either universe on either side --
# nifty100 940 fills, midcap150 1006, zero rows with reason "participation cap".
# So the inertness above survived the sell side being added, and the
# research/tradeable byte-identity it describes is a property of THE CAP VALUE,
# not of the cap.
#
# AT cap=0.10 THE IDENTITY ENDS, BY DESIGN AND MEASURED:
#
#     nifty100    2 BUY + 1 SELL binds of 941 fills    CAGR 19.01 -> 18.88  (-0.13)
#     midcap150   7 BUY + 3 SELL binds of 1009 fills   CAGR 27.80 -> 27.61  (-0.19)
#
# A tradeable artefact that differs from its research twin is then the cap doing
# its job, not a regression. Anything reading the notice below as "tradeable always
# equals research" is reading a statement about 1.00.
#
# The full grid, with per-cell bind counts and the cap/slippage split, is
# diagnostics/impact_sweep_{universe}.csv from results/impact_sweep.py.
# CAP_INERT_NOTICE WAS A STORED CLAIM AND IS GONE. SUPERSEDED 2026-09-22.
#
# IT READ, VERBATIM:
#
#     "CAP DID NOT BIND: measured 2026-09-20 at commit 7dd37d6, the participation
#     cap fired on no fill of midcap150 v1 (n=850) or v2 (n=1006) -- zero rows with
#     reason 'participation cap' in the run's daily_skipped artefact, highest
#     participation 0.709 and 0.345 against a cap of 1.00 -- and every midcap150
#     tradeable artefact is byte-identical to its research twin. nifty100 is
#     recorded inert too. These are not capped results; they are research results
#     under a tradeable filename. Count the 'participation cap' rows in THIS run's
#     daily_skipped artefact before repeating that."
#
# WHY IT WAS REMOVED RATHER THAN EDITED. On 2026-09-22 six tradeable cells were
# run in which the cap DID bind -- nifty500 v1 and v3, midcap100 v1 and v3,
# smallcap250 v1 and v3 -- and this banner printed "CAP DID NOT BIND" over every
# one of them. Its last sentence told the reader to count the rows themselves,
# which is honest and is not what a reader takes from a headline in exclamation
# marks.
#
# THIS IS THE STALE-ASSERTION CLASS, THIRD INSTANCE. gate_compare's register
# described its cells as cap-binding after they stopped being so, and this notice
# was itself written to correct that. A measurement about two universes, stored as
# a sentence, printed over runs of universes it never measured, is the same defect
# one turn later. The cure is not a better sentence: a banner that can be wrong
# about the run it heads must not be a stored claim at all.
#
# WHAT REPLACED IT: cap_report() below, which reads THIS run's own daily_skipped
# artefacts and reports what they contain. The one thing still stored is
# UNGATED_NOTICE, which is a property of the tree -- no gate cell covers this
# profile -- and not a measurement of any run.

# WHICH ARM OWNS WHICH FILENAME. v2 is the shipping arm and its artefacts carry no
# arm token; this is the project-wide convention, not an omission.
_ARM_TOKEN = {"v1": "_v1", "v2": "", "v3": "_v3", "v4": "_v4"}


def cap_report(cells):
    """What the participation cap actually did, read from this run's artefacts.

    `cells` is an iterable of (universe_tag, arm_name). Returns a list of lines.

    NOTHING HERE IS STORED. Every number is counted out of the
    daily_skipped_<tag>[_<arm>]_tradeable.csv this run just wrote. A cell whose
    artefact is absent is reported absent rather than assumed inert -- that is the
    distinction the notice this replaces could not make.
    """
    import csv
    from pathlib import Path
    from universes.registry import REGISTRY

    if is_default():
        return []
    out, total, unread = [], 0, 0
    for tag, arm in cells:
        f = (Path(REGISTRY[tag].metrics_dir)
             / f"daily_skipped_{tag}{_ARM_TOKEN[arm]}_{selected()}.csv")
        if not f.exists():
            out.append(f"    {tag} {arm}: daily_skipped artefact not written "
                       f"({f.name}) -- NOT MEASURED, not inert")
            unread += 1
            continue
        n = sum(1 for r in csv.DictReader(f.open(newline=""))
                if r["reason"].strip().lower() == "participation cap")
        total += n
        out.append(f"    {tag} {arm}: {n} fill(s) capped"
                   f"{'' if n else '  -- cap inert on this cell, this run'}")
    head = (f" PARTICIPATION CAP, COUNTED FROM THIS RUN'S OWN daily_skipped: "
            f"{total} capped fill(s) across {len(out) - unread} cell(s)"
            + (f", {unread} NOT MEASURED" if unread else ""))
    return [head] + out


def gate_status():
    """The gate caveat for this run's profile, or None when it is gated.

    `research` is the profile every gate cell uses and every document compares
    against, so it returns None and nothing is added to a research artefact -- the
    byte-identical gate depends on that.
    """
    return None if is_default() else (
        f"{UNGATED_NOTICE} THE CAP'S EFFECT ON THIS RUN IS NOT ASSERTED HERE: it "
        f"is counted from this run's own daily_skipped artefacts and printed in "
        f"the closing banner. No stored sentence in this file says whether the cap "
        f"bound, because one used to and it was wrong about six runs on "
        f"2026-09-22.")


def suffix():
    """"" for research, "_tradeable" otherwise -- the artefact name tail.

    THE DEFAULT IS UNSUFFIXED so every published filename keeps the name it has and
    the seven gates that read v34_comparison.csv keep reading the same file.
    """
    return "" if is_default() else f"_{selected()}"
