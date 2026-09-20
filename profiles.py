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
    INCREASES the mean number of names held (mid v3 7.60 -> 7.72) and REDUCES
    cash-short skips (131 -> 123), because the buy loop runs in score-descending
    order and shrinking an early oversized name frees cash for the tail it used to
    drop. The cap partially relieves the funding defect rather than compounding it.
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
CAP_INERT_NOTICE = (
    "CAP DID NOT BIND: measured 2026-09-20 at commit 7dd37d6, the participation "
    "cap fired on no fill of midcap150 v1 (n=850) or v2 (n=1006) -- zero rows with "
    "reason 'participation cap' in the run's daily_skipped artefact, highest "
    "participation 0.709 and 0.345 against a cap of 1.00 -- and every midcap150 "
    "tradeable artefact is byte-identical to its research twin. nifty100 is "
    "recorded inert too. These are not capped results; they are research results "
    "under a tradeable filename. Count the 'participation cap' rows in THIS run's "
    "daily_skipped artefact before repeating that."
)


def gate_status():
    """The gate caveat for this run's profile, or None when it is gated.

    `research` is the profile every gate cell uses and every document compares
    against, so it returns None and nothing is added to a research artefact -- the
    byte-identical gate depends on that.
    """
    return None if is_default() else f"{UNGATED_NOTICE} {CAP_INERT_NOTICE}"


def suffix():
    """"" for research, "_tradeable" otherwise -- the artefact name tail.

    THE DEFAULT IS UNSUFFIXED so every published filename keeps the name it has and
    the seven gates that read v34_comparison.csv keep reading the same file.
    """
    return "" if is_default() else f"_{selected()}"
