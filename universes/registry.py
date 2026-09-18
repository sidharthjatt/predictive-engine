"""
universes/registry.py -- the single definition of what a universe IS.
=====================================================================

WHY THIS EXISTS
    Nineteen files independently declare a `UNIVERSES` dict mapping a tag to its
    paths, under NINE mutually incompatible key vocabularies -- `perm`/`tmp` in
    validate_topn and shuffle_test, `score_perm`/`score_tmp`/`raw_perm`/`raw_tmp`
    in validate_sizing and validate_breadth_live, `sc`/`sc_tmp`/`raw`/`raw_tmp`/`md`
    in purge_fix_measure, `cache`/`scores`/`metrics`/`tag`/`end` in nt_run, and so
    on. They express the same handful of facts and cannot be checked against each
    other. Adding a universe means editing nineteen files; deleting one means
    finding all nineteen.

    This module is that definition, once. It began as a DECLARATIVE reader of the
    existing config modules; at step 7 it absorbed them, and config_mid.py and
    config_n100.py were deleted in the same commit. Nothing about any path changed
    in the move -- the values below are the values those files computed, and every
    artefact was checksummed pre/post on the same panel to prove it.

A UNIVERSE IS NOW ONE ROW HERE, AND THAT IS HOW IT IS REMOVED
    It used to be removable by deleting its config module, and _optional() existed
    so that deleting one did not make this module unimportable and take the others
    down with it. There is no config module to delete any more: a universe is added
    by writing a row and removed by deleting one, in this file, and neither touches
    the other rows. The property that mattered -- going through one universe to
    reach another -- is what the registry exists to prevent, and it still holds.

    DELETING A UNIVERSE'S DATA DOES NOT REMOVE THE UNIVERSE, and it did not before
    either: config_mid.py globbed a directory that might not exist, got an empty
    symbol list, and imported fine. A row whose data is gone is a registered
    universe with no symbols, which is a broken checkout rather than a removal.

WHAT IS DELIBERATELY NOT DERIVED BY FORMULA
    The cache filenames look like they follow a rule -- v5_expanding /
    v74_expanding / v_mid_expanding -- but they do not, quite: the raw panel is
    `raw_panel_20.csv` on the 58 and `raw_panel74_20.csv` on the 74, while its
    permanent copy is `raw_panel_cache.csv` and `raw_panel74_cache.csv`. A clever
    stem rule would reproduce three of the four and silently invent the fourth.
    They are written out per universe instead, because a wrong path that LOOKS
    derived is worse than four explicit strings.

THE 58's DATA DIRECTORY IS NOT config.RAW_DATA_DIR
    engine_core.build_panel defaults to `config.RAW_DATA_DIR / "nifty50"`, which
    holds the 58 CSVs; `config.RAW_DATA_DIR` itself is the parent and contains the
    other universes' folders. Pointing a panel build at the parent would sweep in
    every universe at once.

    Note also that `config.SYMBOLS` is NOT the 58's symbol list -- it holds five
    names, is used nowhere, and is vestigial. The 58 is defined by its directory,
    which is why `symbols()` returns None for it: there is no authoritative list
    to check a built panel against, unlike mid and n100.

THERE IS NO `frozen` FLAG ANY MORE, DELIBERATELY
    The 58 and the 74 carried `frozen=True`, which pinned purge_mode="calendar",
    value_at_open=False and a year-cut window so their published numbers could not
    move. Both universes were deleted on 2026-09-11 and the flag went with them
    rather than being kept "for the next retirement": an axis that is defined but
    drives nothing reads as live to the next person. If a universe needs freezing
    again, the field comes back then, with a universe actually setting it.
    See RETIRED_UNIVERSES.md.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# config IS NOT A UNIVERSE'S CONFIG, IT IS THE PROJECT'S -- BT_START_DATE,
# BT_END_DATE, read_price_csv and require_cache all live in it and every universe
# uses them. Its absence is a broken checkout, not a universe removal, so it is
# imported unconditionally and fails loudly. (It also happens to hold the retired
# 58's paths; removing the 58 means dropping its entry below, not deleting
# config.py.)
import config

HORIZON = 20          # engine_core.HORIZON; repeated here only to name the caches


class IndexFileError(RuntimeError):
    """A source directory does not name exactly one index file."""


class StaleConstituentFarm(RuntimeError):
    """A constituents directory holds links that do not come from its source."""


def normalise_stem(stem):
    """The spelling-insensitive key a file stem is compared under.

    WHY EQUALITY ON THE RAW STEM WAS NOT ENOUGH. The exclusion below is by name,
    and until 2026-09-18 by EXACT name. The supplier's directories spell the
    same index with spaces -- "NIFTY MIDCAP 150.csv", "NIFTY 100.csv" -- where
    this repository's own folders spelled it "NIFTYMIDCAP150.csv" and
    "NIFTY100.csv". Measured against the new folders before the change:
    _constituents(new_mid, "NIFTYMIDCAP150") returned 149 names and
    _constituents(new_n100, "NIFTY100") returned 100, each with the index among
    them, AND BOTH ASSERTS IN prepare_data_dir() PASSED -- the second one looks
    for the old spelling, which genuinely is not present, so the guard was
    satisfied by the very rename it exists to catch.

    Whitespace and case only. NOT punctuation, NOT digits, NOT a fuzzy match: a
    normaliser loose enough to pair two different instruments would silently
    delete a constituent, which is the same class of error pointing the other
    way. `IndexFileError` covers what this deliberately does not.
    """
    return "".join(stem.split()).casefold()


def _constituents(raw_dir, index_name):
    """The tradable names in a source folder: every CSV stem EXCEPT the index.

    THE INDEX FILE IS NOT A CONSTITUENT, and after step 7 this is the one place
    that says so. Both predecessors carried this expression and a paragraph
    explaining why it cannot be a bare glob, and the paragraph is the part worth
    keeping: engine_core.build_panel does Path(_src).glob("*.csv") over whatever
    directory it is handed, and an earlier make_final_chart_fair.py swept
    NIFTY100.csv in as a 100th "stock" -- so the published index was averaged
    together with its own members and the resulting line was labelled the
    benchmark. The exclusion is BY NAME, never by position and never by a bare
    glob, and prepare_data_dir() asserts it rather than assuming it.

    A MISSING DIRECTORY YIELDS (), NOT AN ERROR, which is what config_mid.py and
    config_n100.py did at import: Path.glob on a directory that does not exist
    simply produces nothing. See the module docstring on why that is a broken
    checkout rather than a universe removal.
    """
    files = sorted(raw_dir.glob("*.csv"))
    if not files:
        return ()
    if index_name is None:
        return tuple(f.stem for f in files)

    key = normalise_stem(index_name)
    hits = [f.stem for f in files if normalise_stem(f.stem) == key]
    if len(hits) != 1:
        raise IndexFileError(
            f"index_name {index_name!r} matches {len(hits)} files in {raw_dir}"
            + (f": {hits}" if hits else "")
            + ".\n"
            "  EXACTLY ONE IS REQUIRED. Zero means the exclusion below removes\n"
            "  nothing and every constituent list built from this directory is\n"
            "  one name too long, with the published index sitting in it as a\n"
            "  tradable stock. More than one means the directory does not say\n"
            "  which file is the index. Neither can be resolved by guessing:\n"
            "  correct index_name on the registry row, or correct the folder.")
    return tuple(f.stem for f in files if normalise_stem(f.stem) != key)


@dataclass(frozen=True)
class Universe:
    """One universe, as the repository already defines it.

    Field names are chosen to be readable rather than to match any one of the
    nineteen existing vocabularies -- matching one would misdescribe the others.
    """
    tag: str                      # "58" | "74" | "mid" | "n100"
    label: str                    # for chart titles and report headers
    data_dir: Path                # what build_panel is pointed at
    metrics_dir: Path             # where this universe's artefacts live
    score_tmp: Path               # working score panel
    score_cache: Path             # permanent score panel
    raw_tmp: Path                 # working raw feature panel
    raw_cache: Path               # permanent raw feature panel
    nautilus_scores: str          # parquet filename under nautilus/data/
    nautilus_end: str             # backtest end date the port uses
    purge_mode: str               # "trading" -- purge measured in trading rows
    index_name: Optional[str]     # published index, excluded from the universe
    # THE PUBLISHED INDEX PRICE FILE, or None where the universe has no published
    # index at all. index_name has always recorded that a universe HAS one; this
    # records WHERE it is, so a step that plots the cap-weighted benchmark can ask
    # the universe instead of importing that universe's config module by name.
    # None for the retired 58 and 74: they are directory-defined baskets with no
    # published index series, which is a fact about them and not a missing path.
    index_file: Optional[Path]
    year_range: Optional[Tuple[int, int]]      # retired universes cut by year; None here
    date_range: Optional[Tuple[object, object]]  # live universes cut by date

    # THE SOURCE FOLDER AS DELIVERED -- constituents AND the published index in one
    # directory. Arrived at step 7 from RAW_DATA_DIR_MID / RAW_DATA_DIR_N100. It is
    # NOT data_dir: data_dir is what build_panel may be pointed at, and pointing it
    # here would sweep the index in as one more tradable name.
    #
    # None MEANS THE DIRECTORY IS THE DEFINITION, which is the retired 58 and 74:
    # a basket with no published index and no authoritative symbol list, where
    # data_dir simply exists and symbols() answers None. That shape is kept
    # expressible because it was a real shape, not because a universe uses it now.
    raw_data_dir: Optional[Path]

    # WHAT THIS UNIVERSE'S MEMBERSHIP MEANS FOR ITS NUMBERS -- no default, so a row
    # that omits it fails at construction. The precedent is d3ae8ec, which made
    # DISPLAY, COLOURS and LIQUIDITY Universe fields for the same reason: a fact
    # that matters to every reader must not be omittable by a new row.
    #
    # ONE SENTENCE CARRYING BOTH THE MEANING AND THE PROVENANCE, and deliberately
    # NOT a "static" | "pit" enum. results/survivorship.py:117 already holds
    # SURVIVORSHIP_MODE as a process-wide global; a per-row enum would be a second
    # authority for the same word, and a row disagreeing with the global would have
    # no resolution rule. This field says what the FOLDER's membership means, which
    # the global cannot express per universe and the folder name does not carry.
    #
    # IT EXISTS BECAUSE ONE OF THOSE FOLDER NAMES READS BACKWARDS. A universe
    # sourced from data/raw/Final_Without_Survivorship_Data must say so in terms:
    # "Without_Survivorship" means without survivorship DATA -- current
    # constituents only -- not without survivorship BIAS.
    #
    # NOT DERIVED FROM, AND DOES NOT DERIVE, the SURVIVORSHIP: sentences in
    # chart_text and engine_text. Those interpolate live run values (mid's n_late)
    # and carry a per-universe benchmark carve-out (n100's cap-weighted index),
    # so a shared static string would either drop the computed figure or become a
    # template -- and a template with run-time interpolation stops being a
    # declaration. ONE AUTHORITY, TWO RENDERINGS: this field is the declaration and
    # is what fails the build; those are rendered prose for their own figures. If
    # they are ever unified, the chart text CITES this field rather than restating
    # it, and that is separate work.
    survivorship: str
    # THE TRADABLE NAMES, SORTED, INDEX EXCLUDED. Computed by _constituents() when
    # the row is built -- eagerly, exactly as config_mid.SYMBOLS_MID was computed
    # at config import -- so a mid-run change to the source folder cannot move it.
    # () when raw_data_dir is None.
    symbol_list: Tuple[str, ...]

    # ------------------------------------------------------------------
    # WHAT THE COMBINED CHART SHOWS FOR THIS UNIVERSE -- phase 2, 2026-09-16
    # ------------------------------------------------------------------
    # THREE TABLES IN results/make_combined_universes.py, MOVED HERE VERBATIM.
    # They were keyed by tag, so adding a universe meant finding all three; two of
    # the three refused loudly when one was missing and one did not.
    #
    # NO DEFAULTS, AND THAT IS THE POINT RATHER THAN A STYLE CHOICE. A field with
    # no default cannot be forgotten: a row that omits one fails at CONSTRUCTION
    # with a TypeError naming the field. A checker has to remember to look, and
    # three of registry_coverage_check.py's tables stop being NEEDED rather than
    # being silenced.

    # THE CHART TITLE'S SPELLING, WHICH IS NEITHER index_name NOR label. The title
    # has always said "NIFTY 100" (with a space) and "MIDCAP150" (without the
    # NIFTY prefix), while index_name holds the FILE's name -- "NIFTY100",
    # "NIFTYMIDCAP150" -- which is what the per-universe legend rows use. Deriving
    # one from the other would silently retitle a published chart.
    display_name: str

    # FOUR COLOURS PER UNIVERSE PLUS TWO. Slots 0-3 are v2, v1, buy&hold, index and
    # are UNCHANGED -- the published chart depends on them. Slots 4 and 5 are v3
    # and v4, appended rather than inserted so every existing index keeps pointing
    # at the same colour. A new universe adds a tuple that does not collide with
    # these; a chart that picks a colour by accident is not reproducible.
    chart_colours: Tuple[str, ...]

    # THE LIQUIDITY PARAGRAPH, WHICH IS A MEASURED RESULT AND NOT CHART FURNITURE.
    # Fill sizes against prior-20-day median volume, and what a realistic depth
    # model costs in CAGR points. It cannot be invented for a universe nobody has
    # measured, so None is the DECLARATION that it was not -- the shape LIQUIDITY's
    # NOT_MEASURED had, with the constructor now enforcing presence instead of a
    # checker.
    #
    # EVERY NUMBER IN A NOTE IS STAMPED WITH THE ENGINE THAT MEASURED IT. These
    # were measured before adj_close became the canonical price and before the
    # interior-gap guard, and the headline figures they quote have since moved.
    # They are kept as the liquidity finding, which is about fill sizes rather than
    # about CAGR, and marked rather than silently re-quoted under numbers they were
    # not measured against. Re-measure and restamp, or set None; do not edit them.
    liquidity_note: Optional[str]

    # WHAT THIS UNIVERSE'S SURVIVORSHIP COSTS, IN ITS OWN WORDS. Added
    # 2026-09-18, and it is a FIELD rather than a shared paragraph because the
    # shared one was written for a midcap universe and printed on every chart:
    # n50's run said "midcaps that FELL OUT of the index ... midcap churn is far
    # higher than large-cap churn" under a Nifty 50 heading. n100's says it too,
    # and always has.
    #
    # CONSOLE OUTPUT, NOT THE PNG. The subtitle that reaches the image is
    # chart_text["subtitle"]; this is the block make_chart prints above it,
    # which is what a reader sees in a run log and in a pipeline transcript. It
    # reaches no file on disk today, which is why moving it moves no artefact.
    #
    # NO DEFAULT, like the four fields promoted on 2026-09-18: a universe that
    # does not say what its own churn does cannot be constructed.
    churn_note: str

    # ------------------------------------------------------------------
    # WHAT THE ENGINE REPORTS FOR THIS UNIVERSE
    # ------------------------------------------------------------------
    # Added 2026-09-15 with step 5, the engine merge. engine_v2_final_mid.py and
    # engine_v2_final_n100.py had diverged in 95 lines of code beyond their tags --
    # unlike the step 3 and step 4 pairs, which differed only in the tag -- and some
    # of that divergence REACHES PUBLISHED ARTEFACTS: v2FINAL_params.json carries a
    # different key set and key ORDER per universe, and chart_v2FINAL.png carries a
    # different title.
    #
    # IT IS PRESERVED AS DATA, NOT UNIFIED. A merge is verifiable by the gate; an
    # artefact change is a judgement, and putting both in one commit would leave a
    # moved byte with two possible causes. Unifying any of this is a separate,
    # declared change.
    #
    # validation_status IS DELIBERATELY NOT A UNIFORM SHAPE. mid carries a dict of
    # eight measured results; n100 carries a sentence saying the work was not done
    # on this universe. That asymmetry is the RECORD OF WHICH UNIVERSE GOT THE WORK,
    # and flattening both into one shape would read as though both were measured.
    # The type tells them apart: dict means measured, str means not.
    # THREE OF THESE HAVE NO DEFAULT, AS OF 2026-09-18, AND THAT IS THE POINT.
    #
    # engine_params_keys defaulted to (), engine_text and chart_text to None.
    # Measured on a Universe constructed without them, before the change:
    #
    #   engine_params_keys = ()   ->  engine_v2_final.py:333 writes
    #       json.dumps({k: _vals[k] for k in u.engine_params_keys}, indent=2)
    #       which is the two bytes "{}". Valid JSON. No exception, no warning.
    #       v2FINAL_params.json exists, is well-formed, and says NOTHING -- and
    #       it is the file that records which arm, which sizing, which CAGR and
    #       which validation status produced the run beside it.
    #
    #   engine_text = None        ->  TypeError at engine_v2_final.py:138
    #   chart_text  = None        ->  TypeError at make_chart.py:176
    #       Loud, but not until STEP 10n and STEP 10p -- after build_scores has
    #       already spent its time on the panel.
    #
    # A FIELD WITH NO DEFAULT CANNOT BE FORGOTTEN, because the row fails at
    # CONSTRUCTION with a TypeError naming the field, before anything imports a
    # checker. That is the same argument registry_coverage_check.py's docstring
    # makes about DISPLAY, COLOURS and LIQUIDITY leaving its table: those three
    # stopped being NEEDED rather than being silenced. These three join them.
    #
    # THE ORDER OF THESE LINES IS A DATACLASS CONSTRAINT, not a preference: a
    # field with no default cannot follow one that has a default, so the three
    # required fields sit above the two that remain optional.
    engine_params_keys: tuple             # v2FINAL_params.json keys, IN ORDER
    engine_text: dict                     # banner, chart title, console blocks

    # WHAT THE CHART STEP RENDERS FOR THIS UNIVERSE. Added 2026-09-15 with step 6.
    # make_mid_chart.py and make_n100_chart.py diverged in 204 code lines ignoring
    # whitespace, and SOME OF IT REACHES THE PNG: two render parameters, one legend
    # label, and the output stem itself. Preserved, not harmonised, for the same
    # reason as the engine's: a merge is verifiable by the gate, an artefact change
    # is a judgement, and they do not belong in one commit.
    #
    # Most of the pair's labels are NOT here because they derive from data the
    # registry already has -- "<tag> buy&hold (equal-weight universe)" from tag,
    # "<index> (cap-weighted index)" from index_name. Only what cannot be derived
    # is written down.
    chart_text: dict

    # THE TWO THAT KEEP A DEFAULT, AND WHY EACH IS DIFFERENT FROM THE THREE ABOVE.
    #
    # engine_params_static: absent means "no key takes a static value". It is
    # consumed as `_vals.update(u.engine_params_static or {})` and then read as
    # `_vals[k]` for every key in engine_params_keys, so a row that omits it
    # while naming a key that needed it raises KeyError. It fails LOUDLY on the
    # only path where its absence matters, which is what the three above did not.
    #
    # validation_status JOINED THE REQUIRED FIELDS ON 2026-09-18, one commit after
    # the other three, once the decision was taken. Its default was None, and
    # None IS REACHABLE AS AN ARTEFACT VALUE: engine_v2_final.py:329 puts this
    # field straight into v2FINAL_params.json, so a row that left it alone wrote
    #
    #     "validation_status": null
    #
    # which is valid JSON and indistinguishable from a deliberate statement. A
    # universe nobody had validated and a universe whose validation status was
    # never considered produced the same four bytes.
    #
    # NOTHING WAS WRITING null WHEN THIS CHANGED -- all three live rows set the
    # field explicitly -- so this commit moves no byte. It closes the way the
    # next row could.
    #
    # THE SHAPE IS STILL DELIBERATELY NOT UNIFORM. mid carries a dict of eight
    # measured results; n100 and n50 carry sentences saying the work was not done
    # on those universes. The type tells them apart: dict means measured, str
    # means not. Requiring the field does not require a shape, and flattening the
    # two would read as though both were measured.
    validation_status: object

    # THE ONE FIELD THAT KEEPS A DEFAULT, and it is different in kind. It is read
    # as `u.engine_params_static or {}` and then as `_vals[k]` for every key in
    # engine_params_keys, so a row that omits it while naming a key that needed a
    # static value raises KeyError. It fails LOUDLY on the only path where its
    # absence matters, which is exactly what the four fields above did not.
    engine_params_static: dict = None     # values for keys that are not computed

    def symbols(self):
        """The tradable names as a SET, or None when the directory is the definition.

        A set, because that is the shape every caller compares a built panel's
        symbol index against, and it is what the two lambdas this replaced returned.
        `symbol_list` is the sorted tuple, for callers that iterate.
        """
        return None if self.raw_data_dir is None else set(self.symbol_list)

    def prepare_data_dir(self):
        """The directory build_panel should glob, READY TO USE.

        WHY THIS IS AN ACTION AND NOT JUST data_dir. For the 58 and the 74 the
        directory simply exists and this returns it. For mid and n100 it does not:
        their source folder holds the published INDEX alongside the constituents,
        and build_panel globs whatever directory it is handed, so pointing it at the
        source would sweep NIFTYMIDCAP150.csv or NIFTY100.csv in as one more
        tradable name. The answer is a symlink directory holding the constituents
        ONLY, rebuilt -- pruning anything stale -- each time it is asked for.

        That rebuild is the part `data_dir` cannot express. A merged build_scores
        that read data_dir and skipped the call would point build_panel at whatever
        symlinks happened to be on disk, and the index-exclusion guarantee would
        rest on luck rather than on a step that runs. So the universe carries how
        its directory comes into being, next to where it is.

        THE BODY IS ensure_constituents_dir(), WHICH BOTH PREDECESSORS CARRIED. With
        prose stripped and universe names normalised their two copies were
        line-for-line identical, so this is one implementation rather than a merge
        of two: LINKS, NOT COPIES, because the price data keeps a single source of
        truth in the source folder; and the two asserts are the guarantee, not
        decoration -- the first catches a farm that does not match the symbol list,
        the second catches the index leaking in.
        """
        if self.raw_data_dir is None:
            return self.data_dir
        src = self.raw_data_dir.resolve()

        # THE INDEX CHECK RUNS BEFORE ANY LINK IS WRITTEN, not only in the
        # asserts at the bottom. Those still stand, but they fire after the farm
        # has been built, so a poisoned symbol_list left 149 links on disk -- the
        # index among them -- and only then raised. A guard that refuses after
        # creating the thing it refuses is a guard the next reader has to clean
        # up after.
        if self.index_name is not None:
            key = normalise_stem(self.index_name)
            leaked = [x for x in self.symbol_list if normalise_stem(x) == key]
            if leaked:
                raise IndexFileError(
                    f"{self.tag}: symbol_list holds the index under "
                    f"{leaked} while index_name is {self.index_name!r}.\n"
                    "  These are the same name once whitespace and case are\n"
                    "  removed, so the published index would be linked into the\n"
                    "  constituents directory and averaged with its own members.\n"
                    "  Nothing has been written.")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        wanted = set(self.symbol_list)

        for link in self.data_dir.glob("*.csv"):        # drop anything stale
            if link.stem not in wanted:
                link.unlink()

        # EVERY SURVIVING ENTRY MUST ALREADY POINT INTO THE CURRENT SOURCE, and
        # one that does not is an ERROR rather than something to quietly repair.
        #
        # The creation loop below used to read `if not link.exists()`. A link
        # that exists is not evidence that it points anywhere this universe
        # still uses: measured on 2026-09-18, repointing mid's raw_data_dir at
        # the supplier's folder and calling this method left all 148 links
        # aimed at data/raw/MidCap150/clean, returned normally, and passed both
        # asserts -- a sha256 over (name -> resolved target) was byte-identical
        # before and after, so the call was a proven no-op. The prune loop above
        # did not catch it either: it drops by STEM, and no stem was stale.
        #
        # SILENTLY RELINKING WOULD ALSO BE WRONG. A farm full of foreign links
        # means someone changed raw_data_dir without migrating, or is running
        # against a tree they did not build; repairing it in passing throws away
        # the only moment that fact is visible. The caller deletes the farm --
        # `rm -rf` is the documented migration -- and this rebuilds it.
        foreign = []
        for link in sorted(self.data_dir.glob("*.csv")):
            if not link.is_symlink():
                foreign.append(f"{link.name}: a regular file, not a symlink")
                continue
            target = link.readlink()
            if not target.is_absolute():
                target = link.parent / target
            if target.parent.resolve() != src:
                foreign.append(f"{link.name} -> {target}")
        if foreign:
            shown = "\n".join(f"      {f}" for f in foreign[:5])
            more = (f"\n      ... and {len(foreign) - 5} more"
                    if len(foreign) > 5 else "")
            raise StaleConstituentFarm(
                f"{self.tag}: {len(foreign)} of "
                f"{len(list(self.data_dir.glob('*.csv')))} entries in\n"
                f"    {self.data_dir}\n"
                f"  do not come from this universe's current raw_data_dir\n"
                f"    {src}\n{shown}{more}\n"
                f"  The farm was built against a different source. Delete it and\n"
                f"  let it be rebuilt:\n"
                f"      rm -rf {self.data_dir}")

        # DERIVED FROM raw_data_dir EVERY TIME, not only when absent. Each link
        # is written from the source path on every call, so the farm is a
        # function of raw_data_dir rather than a cache of one.
        for sym in self.symbol_list:
            target = self.raw_data_dir / f"{sym}.csv"
            if not target.exists():
                raise StaleConstituentFarm(
                    f"{self.tag}: {target} does not exist, so the farm cannot be\n"
                    f"  derived from raw_data_dir. symbol_list and the source\n"
                    f"  directory disagree; a link written here would dangle.")
            link = self.data_dir / f"{sym}.csv"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)

        present = tuple(sorted(f.stem for f in self.data_dir.glob("*.csv")))
        assert present == self.symbol_list, \
            f"{self.tag}: constituents directory does not match symbol_list"
        assert all(f.readlink().parent.resolve() == src
                   for f in self.data_dir.glob("*.csv")), \
            f"{self.tag}: a link in the farm does not resolve into raw_data_dir"
        # NORMALISED, so the index cannot re-enter under a different spelling of
        # its own name. See normalise_stem().
        assert (self.index_name is None
                or normalise_stem(self.index_name)
                not in {normalise_stem(x) for x in present}), \
            f"{self.tag}: the index leaked into the constituent set"
        return self.data_dir

    def trading_days(self, index):
        """Restrict a price index to this universe's backtest window.

        ONLY THE DATE CUT IS LIVE. Every remaining universe cuts by DATE
        (config.BT_START_DATE..BT_END_DATE). The year-cut branch below is what the
        deleted 58 and 74 used (2019..2026 / 2019..2025, six trading days longer);
        no universe sets `year_range` any more, so it is currently unreachable.
        """
        if self.year_range is not None:
            y0, y1 = self.year_range
            return index[(index.year >= y0) & (index.year <= y1)]
        d0, d1 = self.date_range
        return index[(index >= d0) & (index <= d1)]


# ---------------------------------------------------------------------------
# WHERE EACH UNIVERSE'S DATA IS AND WHERE ITS ARTEFACTS GO -- arrived at step 7
# ---------------------------------------------------------------------------
# FROM config_mid.py AND config_n100.py, deleted in the same commit. Those two
# modules were 71 and 85 lines. With prose stripped and universe names normalised
# their CODE differed in exactly two expressions, both path shapes, and neither
# derivable from the other:
#
#   the source folder        mid   Final_NIFTYMidCap150_EoD_Data  <- supplier
#                            n100  Final_NIFTY100_EoD_Data        <-  folders,
#                                  both under Final_Without_Survivorship_Data/
#   the symlink farm         mid   data/raw/MidCap150/constituents  <- under the
#                                                                     universe folder
#                            n100  data/raw/N100_constituents       <- under data/raw
#
# THEY ARE WRITTEN OUT PER UNIVERSE RATHER THAN REDUCED TO A RULE, for the reason
# stated at the top of this file about the cache filenames: a stem rule would
# reproduce one of each pair and silently invent the other. Neither module was a
# superset of the other -- same nine public names, same order, same function body.
#
# RESULTS_DIR_MID AND RESULTS_DIR_N100 DO NOT BECOME FIELDS. Both predecessors
# defined them and nothing outside those two files ever read either one: they were
# local intermediates on the way to METRICS_DIR. A field that nothing drives reads
# as live to the next person -- see the note on the `frozen` flag above.
_RAW = ROOT / "data" / "raw"

# REPOINTED 2026-09-18. mid and n100 keep their tags, their metrics
# directories and their history; what changed underneath them is the panel.
# Both now read the supplier's without-survivorship set, and the spelling of
# the index file changed with it -- "NIFTYMIDCAP150" -> "NIFTY MIDCAP 150",
# "NIFTY100" -> "NIFTY 100". The constituent NAMES are identical across the
# move (148 and 99, nothing added, nothing dropped); the PRICES are not, and
# neither is the per-name history: 35 mid names and 16 n100 names now begin
# later than they did, and 8 mid names and 2 n100 names now begin after
# BT_START_DATE where they did not before. See PANEL_MIGRATION.md.
_WITHOUT_SURV = _RAW / "Final_Without_Survivorship_Data"

_MID_SOURCE = _WITHOUT_SURV / "Final_NIFTYMidCap150_EoD_Data"
_MID_LINKS = _RAW / "MidCap150" / "constituents"
_MID_METRICS = ROOT / "results_midcap150" / "metrics"
_MID_INDEX = "NIFTY MIDCAP 150"

_N100_SOURCE = _WITHOUT_SURV / "Final_NIFTY100_EoD_Data"
_N100_LINKS = _RAW / "N100_constituents"
_N100_METRICS = ROOT / "results_nifty100" / "metrics"
_N100_INDEX = "NIFTY 100"

_MID = Universe(
        tag="midcap150", label="MidCap150 (148 constituents)",
        data_dir=_MID_LINKS,
        raw_data_dir=_MID_SOURCE,
        survivorship=(
            "STATIC. 148 names are TODAY'S MidCap150 members backfilled to "
            "2019-01-01. Midcaps that left the index or delisted during the window "
            "are absent entirely, so both the strategy and its equal-weight "
            "buy&hold are inflated. Source: data/raw/MidCap150/clean."),
        symbol_list=_constituents(_MID_SOURCE, _MID_INDEX),
        metrics_dir=_MID_METRICS,
        score_tmp=Path("/tmp/v_midcap150_expanding.csv"),
        score_cache=_MID_METRICS / "v_midcap150_expanding_cache.csv",
        raw_tmp=Path(f"/tmp/raw_panel_midcap150_{HORIZON}.csv"),
        raw_cache=_MID_METRICS / "raw_panel_midcap150_cache.csv",
        nautilus_scores="scores_midcap150.parquet",
        nautilus_end=str(config.BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_MID_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable name.
        # Base 1-Apr-2005 = 1000, which the file reproduces exactly.
        index_file=_MID_SOURCE / f"{_MID_INDEX}.csv",
        year_range=None, date_range=(config.BT_START_DATE, config.BT_END_DATE),
        display_name="MIDCAP150",
        chart_colours=("#e377c2", "#17becf", "#8fd08f", "#7f7f7f",
                       "#1b9e77", "#e6ab02"),
        # VERBATIM, THE TEXT make_chart PRINTED FOR EVERY UNIVERSE. This one was
        # written for mid and is correct for mid; it moved here unchanged, and
        # mid's console output is byte-identical across the move.
        churn_note=(
            "More important than the late listers: midcaps that FELL OUT of the index\n"
            "or delisted between 2019 and 2026 are absent from this file entirely, and\n"
            "midcap churn is far higher than large-cap churn. The equal-weight buy&hold\n"
            "line is therefore an upper bound on a portfolio nobody could have held.\n"
            "Measured on the Nifty100 equivalent, this bias was worth about 10 points\n"
            "of CAGR. The buy&hold number below is NOT achievable."),
        liquidity_note=(
            "mid [measured pre-2026-09-10, close-basis engine]: 22 of 985 fills "
            "exceed 10%, the largest being 1,614% on AIIL; the same depth model "
            "cost 1.80 CAGR points, 29.16% -> 27.36%."),
        # MEASURED. Eight results from the post density-fix panel. The inv-vol half
        # of the old blanket "validated" claim was FALSE as written, which is why
        # this is stated per test: a stale validation claim is worse than no claim.
        validation_status={
            "measured_on": "post density-fix panel, 2026-08-13, caches rebuilt",
            "breadth_T1_seed_robustness": ("FAIL 2 of 3 seed sets "
                                           "(+0.14, -0.02, +0.16); was PASS 3 of 3"),
            "breadth_T2_sub_period": "PASS both halves (+0.21, +0.36)",
            "inv_vol_T1_baseline_control": "PASS",
            "inv_vol_T2_seed_robustness": ("FAIL 0 of 3 seed sets "
                                           "(-0.05, -0.01, -0.10); was PASS 3 of 3"),
            "inv_vol_T3_sub_period": "FAIL both halves (-0.04, -0.10); was PASS",
            "inv_vol_T4_vol_window": ("FAIL 0 of 4 windows beat equal-rupee 1.06 "
                                      "(1.00/1.00/1.04/1.03); was PASS 4 of 4"),
        },
        # THE KEY ORDER IS THE ARTEFACT. json.dumps preserves insertion order, so
        # this tuple is what makes v2FINAL_params.json byte-identical across the
        # merge. mid has no "universe" and no "n_symbols"; n100 has both and lacks
        # "validated"/"rejected". Neither set is more correct -- they are what the
        # two engines happened to write, and unifying them is a separate change.
        engine_params_keys=(
            "model", "sizing", "exposure", "top_n", "buffer", "rebalance_days",
            "avg_exposure_pct", "sharpe", "maxdd_pct", "cagr_pct", "cash_yield",
            "survivorship", "vs_buyhold", "validated", "validation_status",
            "rejected"),
        engine_params_static={
            "validated": "see validation_status",
            "rejected": ["slope regime", "absolute gate", "vol-targeting",
                         "feature pruning", "100-share sizing"],
        },
        engine_text={
            "banner": "ENGINE v2 FINAL -- cross-sectional ranking + inverse-vol "
                      "+ breadth scaling",
            "panel_what": "MidCap150 score panel",
            "bh_label": "Equal-weight buy & hold (MidCap150)",
            "chart_title": ("FINAL v2 strategy: ranking + inverse-vol + "
                            "breadth-scaled exposure\n"
                            "Breadth cuts exposure in weak markets -> ~half the "
                            "drawdown, higher Sharpe\n"),
            "assert_index_absent": False,
        },
        chart_text={
            "stem": "chart_midcap150_FINAL",
            # THE INDEX WINDOW END IS A DATA BOUNDARY, not a market one: it is the
            # last date this universe's index file carries. mid and n100 differ.
            #
            # CORRECTED 2026-09-18 FROM 2026-06-08. `NIFTY MIDCAP 150.csv` ends
            # 2026-08-06; the old value cut the printed index window 10 sessions
            # short of the file. It was display-only -- the sole reader is
            # make_chart.py, which slices the INDEX series for one console line
            # and never the score panel or the engine -- so no committed number
            # moved. WHY it was wrong is recorded as OPEN in PANEL_MIGRATION.md
            # section 6: the transposition reading does not explain the value
            # also landing exactly on the raw panel cutoff.
            "index_window_end": "2026-08-06",
            "dpi": 140,
            "legend_fontsize": 8,
            "rule_width": 94,
            # mid's chart says the equal-weight line is NOT investable in the
            # legend itself; n100's says it only in the prose below the chart.
            # Both statements are true of both universes -- which is an argument
            # for unifying them, in a commit that declares the artefact change.
            "bh_not_investable": True,
            # THE IC / EXTREME-RETURN DIAGNOSTIC BLOCK, mid only. Console output,
            # no artefact, but it re-reads the score panel, so running it for n100
            # would be new work rather than new formatting.
            "diagnostics": True,
            # THE DRAWDOWN-PANEL LEGEND LABEL, and it reaches the PNG. The two
            # originals differed in three ways on ONE continuation line: the split
            # token ("[" vs "  ["), the word "max", and the precision (.0f vs .1f).
            # A keyword survey of render parameters missed it because the line it
            # sits on contains no render keyword -- the grep matched the ax[1].plot
            # call and never reached its argument. Checksum found it; grep did not.
            "dd_label": lambda lab, mn: f"{lab.split('[')[0].strip()} ({mn:.0f}%)",
            # THE CHART SUBTITLE REACHES THE PNG, and the two universes' subtitles
            # are different prose that reads different values -- mid's quotes the
            # panel-density figures that only its diagnostics block computes.
            # A CALLABLE, like _symbols and _prepare above, so make_chart.py stays
            # free of per-universe text. `v` is the values the step computed.
            "subtitle": lambda v: (
                f"MidCap150 panel density: {v['n_panel']} of {v['n_all']} names "
                f"scored, median {v['per_day_median']} priced per day.\n"
                f"MidCap150 universe ({v['n_all']} constituents, index excluded)  |  "
                f"v2 holds {v['inv']}% invested on average  |  ALL NUMBERS AFTER TC "
                f"(Zerodha + 0.15% slippage)\n"
                f"Benchmarks: {v['index_name']} is the published CAP-WEIGHTED index "
                f"(investable). Equal-weight buy&hold is the universe, and is NOT "
                f"investable.\n"
                f"SURVIVORSHIP: {v['n_late']} of {v['n_all']} names did not exist at "
                f"2019-01-01, and midcaps that left the index or delisted 2019-2026 "
                f"are absent from this file altogether.\n"
                f"Midcap churn far exceeds large-cap churn; the same bias measured "
                f"about 10 CAGR points on Nifty100. Do not read buy&hold as "
                f"achievable.\n"
                "LIQUIDITY AND MARKET-IMPACT FIGURES ARE NOT AVAILABLE FOR THIS "
                "WINDOW: the depth and participation studies were run on the old "
                "1,842-day window\n"
                "ending 2026-06-08 and have not been re-run. Every number here is a "
                "research backtest with a flat 0.15% slippage and no market-impact "
                "model.\n"),
        },
    )

_N100 = Universe(
        tag="nifty100", label="Nifty 100 (99 constituents)",
        data_dir=_N100_LINKS,
        raw_data_dir=_N100_SOURCE,
        survivorship=(
            "STATIC. 99 names are TODAY'S Nifty 100 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. The published NIFTY100 index line is cap-weighted and is "
            "NOT survivorship-biased. Source: data/raw/nifty100_benchmark."),
        symbol_list=_constituents(_N100_SOURCE, _N100_INDEX),
        metrics_dir=_N100_METRICS,
        score_tmp=Path("/tmp/v_nifty100_expanding.csv"),
        score_cache=_N100_METRICS / "v_nifty100_expanding_cache.csv",
        raw_tmp=Path(f"/tmp/raw_panel_nifty100_{HORIZON}.csv"),
        raw_cache=_N100_METRICS / "raw_panel_nifty100_cache.csv",
        nautilus_scores="scores_nifty100.parquet",
        nautilus_end=str(config.BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_N100_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable name.
        # Base 1-Jan-2003 = 1000; the file reads 1,008.00 on 2003-01-02, consistent
        # with NSE's published methodology. Verified, not assumed.
        index_file=_N100_SOURCE / f"{_N100_INDEX}.csv",
        year_range=None, date_range=(config.BT_START_DATE, config.BT_END_DATE),
        display_name="NIFTY 100",
        chart_colours=("#c0392b", "#2e6da4", "#3a9d3a", "#000000",
                       "#7f3f98", "#d95f02"),
        # THE MIDCAP PARAGRAPH, KEPT VERBATIM ON A LARGE-CAP UNIVERSE, AND THAT
        # IS A GATE AND NOT AN ENDORSEMENT. n100 has printed this text since the
        # shared block existed; it is wrong here in the same way it was wrong on
        # n50 -- the Nifty 100 is not a midcap index and "midcap churn is far
        # higher than large-cap churn" is an argument about a different
        # universe. Correcting it changes what a reader sees in every n100 run
        # transcript, which is its own change with its own before/after. The
        # commit that moved this text was gated on n100's output not moving.
        churn_note=(
            "More important than the late listers: midcaps that FELL OUT of the index\n"
            "or delisted between 2019 and 2026 are absent from this file entirely, and\n"
            "midcap churn is far higher than large-cap churn. The equal-weight buy&hold\n"
            "line is therefore an upper bound on a portfolio nobody could have held.\n"
            "Measured on the Nifty100 equivalent, this bias was worth about 10 points\n"
            "of CAGR. The buy&hold number below is NOT achievable."),
        liquidity_note=(
            "n100 [measured pre-2026-09-10, close-basis engine]: 3 of 997 fills "
            "exceed 10% of prior-20-day median volume, and ZERO do on the 60-day "
            "window;\nmodelling realistic depth (10% of median daily volume per "
            "level, three levels) cost 0.01 CAGR points, 25.43% -> 25.42%."),
        # SURVIVORSHIP. These 99 names are TODAY'S index members backfilled to the
        # start of the backtest; companies that were in the Nifty 100 during the
        # window and were later dropped or delisted are absent entirely. It is
        # stated in the chart subtitle and in the forensic log header rather than
        # left to be inferred, and results/survivorship.py stays at "static".
        # NOT MEASURED, and a STRING rather than a dict so it cannot be mistaken
        # for mid's eight results. The seed-robustness and sub-period validations
        # on record were run elsewhere and are not claimed here.
        validation_status=("not measured on this universe. The seed-robustness "
                           "and sub-period validations on record were run on the "
                           "58 and the mid and are not claimed here."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        engine_params_static={
            "universe": "Nifty 100 (99 constituents, NIFTY100.csv excluded by name)",
        },
        engine_text={
            "banner": "ENGINE v2 FINAL -- Nifty 100 universe (99 names, index "
                      "excluded by name)",
            "panel_what": "Nifty 100 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 100, 99 names)",
            "chart_title": ("Nifty 100 universe -- ranking + inverse-vol + "
                            "breadth-scaled exposure\n"),
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_nifty100",
            # CORRECTED 2026-09-18, with the repoint that made it stale. The old
            # nifty100_benchmark/NIFTY100.csv ended 22-06-2026, so this value
            # was RIGHT until the source changed; Final_NIFTY100_EoD_Data's
            # index file carries 32 further rows and ends 06-08-2026. All 32
            # are past BT_END_DATE, so no number moved -- what was wrong was
            # the sentence under the chart saying where the benchmark stops.
            "index_window_end": "2026-08-06",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "bh_not_investable": False,
            "diagnostics": False,
            "dd_label": lambda lab, mn: f"{lab.split('  [')[0]} (max {mn:.1f}%)",
            "subtitle": lambda v: (
                f"Nifty 100 universe ({v['n_all']} constituents, index excluded "
                f"by name)  |  v2 holds {v['inv']}% invested on average  |  ALL "
                f"NUMBERS AFTER TC (Zerodha + 0.15% slippage)\n"
                # DERIVED, NOT SPELLED OUT. This read "NIFTY100" until
                # 2026-09-18, which was the file's name before the repoint;
                # index_name is "NIFTY 100" now and the subtitle went on
                # printing the old spelling onto the PNG. mid's row already
                # derived it. A hardcoded name is a second place for the same
                # fact to live, and it is the copy that nothing checks.
                f"Benchmarks: {v['index_name']} is the published CAP-WEIGHTED "
                f"index (investable, and NOT survivorship-biased). Equal-weight "
                f"buy&hold is the universe, and is NOT investable.\n"
                f"SURVIVORSHIP: these {v['n_all']} are TODAY'S index members "
                f"backfilled to 2019. Names dropped or delisted from the Nifty 100 "
                f"during the window are absent entirely,\nso both the strategy and "
                f"its equal-weight buy&hold are inflated. Do not read that buy&hold "
                f"as achievable.\n"
                # THE STUDY IS NOT MISSING, IT IS ABOUT A PANEL THAT IS GONE.
                # This used to say the figures were "not available for this
                # window" and name the old 1,842-day window ending
                # 2026-06-08, which described the kite extraction rather
                # than anything in this checkout. The measurement exists and
                # is recorded in liquidity_note; what it does not do is
                # describe these prices. See PANEL_MIGRATION.md.
                "LIQUIDITY AND MARKET-IMPACT FIGURES DO NOT DESCRIBE THIS PANEL: "
                "the depth and participation studies were measured on the kite "
                "extraction that\n"
                "was superseded on 2026-09-18, and have not been repeated on "
                "this one. Every number here is a research backtest with a flat "
                "0.15% slippage and no market-impact model.\n"),
        },
    )


# ---------------------------------------------------------------------------
# n50 -- THE FIRST OF THE SUPPLIER'S OTHER SIX, ADDED 2026-09-18
# ---------------------------------------------------------------------------
# WHY THIS ONE FIRST, AND WHY ONE AT A TIME. Every one of n50's 50 names is
# already in n100, measured on the supplier's directories: n50 is a STRICT
# SUBSET of n100, which was rebuilt on this same vendor panel over the same
# 1,836 sessions at 9d717b0. So n50 introduces no name this repository
# has not already priced, and a surprise in its output is attributable to the
# wiring rather than to data nobody has looked at.
#
# It also has the best coverage of the eight: 46 of 50 names are present at
# BT_START_DATE (92.0%, against n100's 88.9% and mid's 75.7%), and its latest
# first date is 2023-08-21 -- it is the only new universe with no name starting
# in the last two years. The four that start late are MAXHEALTH (2020-08-21),
# ETERNAL (2021-07-23), NESTLEIND (2023-08-01) and JIOFIN (2023-08-21), all four
# already among n100's eleven.
#
# NOTHING HAS BEEN RUN ON THIS UNIVERSE. No panel, no cache, no artefact, no
# chart. liquidity_note is None and validation_status says so in words, because
# a placeholder number here would be a claim nobody has earned.
_N50_SOURCE = _WITHOUT_SURV / "Final_NIFTY50_EoD_Data"
_N50_LINKS = _RAW / "N50_constituents"
_N50_METRICS = ROOT / "results_nifty50" / "metrics"
# THE SUPPLIER SPELLS THIS ONE IN TITLE CASE. Seven of the eight index files
# shout -- "NIFTY 100", "NIFTY MIDCAP 150", "NIFTY SMLCAP 250" -- and this one
# is "Nifty 50.csv". It is handled by normalise_stem() like any other spelling,
# and it is written out here rather than derived for exactly that reason.
_N50_INDEX = "Nifty 50"

_N50 = Universe(
        tag="nifty50", label="Nifty 50 (50 constituents)",
        data_dir=_N50_LINKS,
        raw_data_dir=_N50_SOURCE,
        survivorship=(
            "STATIC. 50 names are TODAY'S Nifty 50 members backfilled to "
            "2019-01-01. Names dropped or delisted during the window are absent "
            "entirely, so both the strategy and its equal-weight buy&hold are "
            "inflated. 4 of the 50 did not exist at BT_START_DATE. The published "
            "Nifty 50 index line is cap-weighted and is NOT survivorship-biased. "
            "Source: data/raw/Final_Without_Survivorship_Data/"
            "Final_NIFTY50_EoD_Data."),
        symbol_list=_constituents(_N50_SOURCE, _N50_INDEX),
        metrics_dir=_N50_METRICS,
        score_tmp=Path("/tmp/v_nifty50_expanding.csv"),
        score_cache=_N50_METRICS / "v_nifty50_expanding_cache.csv",
        raw_tmp=Path(f"/tmp/raw_panel_nifty50_{HORIZON}.csv"),
        raw_cache=_N50_METRICS / "raw_panel_nifty50_cache.csv",
        nautilus_scores="scores_nifty50.parquet",
        nautilus_end=str(config.BT_END_DATE.date()),
        purge_mode="trading",
        index_name=_N50_INDEX,
        # THE PUBLISHED CAP-WEIGHTED INDEX. Benchmark only, never a tradable
        # name. NO BASE VALUE IS CLAIMED HERE: the file begins on 03-01-2000 at
        # 1,592.20, which is a mid-series value, so unlike mid's and n100's rows
        # there is no base-date reading in this file to verify a methodology
        # against. Stating one would be repeating NSE's documentation rather
        # than checking it. The file carries 6,627 rows, 03-01-2000..26-08-2026.
        index_file=_N50_SOURCE / f"{_N50_INDEX}.csv",
        year_range=None, date_range=(config.BT_START_DATE, config.BT_END_DATE),
        display_name="NIFTY 50",
        # MEASURED, NOT PICKED. The first tuple here was matplotlib's tab10
        # head, chosen by eye, and it collided three ways against n100 in NORMAL
        # colour vision on the combined chart: buy&hold #2ca02c vs n100's
        # #3a9d3a at dE2000 2.13 -- below the 2.3 just-noticeable difference --
        # the index #111111 vs n100's #000000 at 2.96, and this universe's
        # SHIPPING line #1f77b4 vs n100's control #2e6da4 at 4.18. Under
        # protanopia it also collided with itself, #ff7f0e against #2ca02c at
        # 1.90.
        #
        # These six were searched out of a 12,015-colour in-gamut Lab grid
        # (L* 35-72, C* 28-95, so a line reads on white rather than merely
        # scoring well) under the constraint that mid's and n100's tuples do not
        # move. Every one clears dE2000 >= 10 against all twelve of their slots
        # and against each other, in normal vision, deuteranopia and protanopia
        # (Vienot 1999). Achieved minimum 11.24 overall; 15.29 among the four
        # slots the CANONICAL combined chart draws, which is the published
        # figure and is where the margin was spent.
        #
        # SLOT ORDER IS SEMANTIC, not the search's output order: buy&hold stays
        # green as it is on mid and n100, and the index stays the darkest of the
        # six. It is dark red rather than neutral, because a neutral would have
        # had to clear n100's black and mid's grey and nothing in the readable
        # band does. NOTHING CHECKS ANY OF THIS -- see KNOWN_ISSUES.md.
        chart_colours=("#7f4b70", "#4176fc", "#34c2a5", "#932d41",
                       "#1551e7", "#046e59"),
        # n50's OWN CHURN, not the midcap paragraph it inherited on its first
        # run. The Nifty 50 is the most stable index of the eight: its members
        # are the largest listed companies in the country and they leave it
        # rarely. That makes the survivorship bias SMALLER here than anywhere
        # else in this repository -- and it does not make it zero, which is the
        # part worth saying out loud on a chart whose buy&hold line looks
        # achievable.
        #
        # NO NUMBER IS CLAIMED FOR THE SIZE OF THE BIAS. mid's paragraph quotes
        # "about 10 points of CAGR" from the Nifty100 measurement; nothing
        # equivalent has been measured for the Nifty 50, and borrowing a midcap
        # or large-cap figure would be inventing one.
        churn_note=(
            "More important than the late listers: companies that LEFT the Nifty\n"
            "50 between 2019 and 2026, by falling out of the index or being taken\n"
            "over, are absent from this file entirely. Nifty 50 turnover is the\n"
            "lowest of any universe here, so this bias is smaller than on the\n"
            "midcap panels -- but it is not zero, and it runs one way: the names\n"
            "that left are the ones that did worst. NOTHING HAS BEEN MEASURED FOR\n"
            "THIS UNIVERSE. The equal-weight buy&hold line is an upper bound on a\n"
            "portfolio nobody could have held, and is NOT achievable."),
        # NOT MEASURED. None is the declaration, not a hole -- no depth or
        # participation study has been run on this panel, and the combined chart
        # drops the note rather than printing an empty one.
        liquidity_note=None,
        # NOT MEASURED, and a STRING rather than a dict, by the same rule n100
        # follows: the type tells a measured universe from an unmeasured one.
        validation_status=("not measured on this universe. No seed-robustness, "
                           "sub-period, shuffle or top-N work has been run here, "
                           "and none of the validations on record was run on "
                           "these 50 names."),
        engine_params_keys=(
            "universe", "model", "sizing", "exposure", "top_n", "buffer",
            "rebalance_days", "avg_exposure_pct", "n_symbols", "sharpe",
            "maxdd_pct", "cagr_pct", "cash_yield", "survivorship", "vs_buyhold",
            "validation_status"),
        # THE KEY SET AND ORDER FOLLOW n100's, not mid's. n50 is a strict subset
        # of n100 and is read against it, so a params file whose keys are in a
        # different order would make the two awkward to diff for no gain.
        engine_params_static={
            "universe": "Nifty 50 (50 constituents, 'Nifty 50.csv' excluded "
                        "by name)",
        },
        engine_text={
            "banner": "ENGINE v2 FINAL -- Nifty 50 universe (50 names, index "
                      "excluded by name)",
            "panel_what": "Nifty 50 score panel",
            "bh_label": "Equal-weight buy & hold (Nifty 50, 50 names)",
            "chart_title": ("Nifty 50 universe -- ranking + inverse-vol + "
                            "breadth-scaled exposure\n"),
            "assert_index_absent": True,
        },
        chart_text={
            "stem": "chart_nifty50",
            # THE LAST DATE THIS UNIVERSE'S INDEX FILE CARRIES, read off the
            # file: "Nifty 50.csv" ends 26-08-2026. That is twenty days later
            # than every other supplier index file, which end 06-08-2026.
            "index_window_end": "2026-08-26",
            "dpi": 150,
            "legend_fontsize": 8.5,
            "rule_width": 100,
            "bh_not_investable": False,
            "diagnostics": False,
            "dd_label": lambda lab, mn: f"{lab.split('  [')[0]} (max {mn:.1f}%)",
            "subtitle": lambda v: (
                f"Nifty 50 universe ({v['n_all']} constituents, index excluded "
                f"by name)  |  v2 holds {v['inv']}% invested on average  |  ALL "
                f"NUMBERS AFTER TC (Zerodha + 0.15% slippage)\n"
                # DERIVED, for the reason given on n100's row. This was
                # correct when written and that is exactly the problem: so was
                # n100's.
                f"Benchmarks: {v['index_name']} is the published CAP-WEIGHTED "
                f"index (investable, and NOT survivorship-biased). Equal-weight "
                f"buy&hold is the universe, and is NOT investable.\n"
                f"SURVIVORSHIP: these {v['n_all']} are TODAY'S index members "
                f"backfilled to 2019. Names dropped or delisted from the Nifty "
                f"50 during the window are absent entirely,\nso both the "
                f"strategy and its equal-weight buy&hold are inflated. Do not "
                f"read that buy&hold as achievable.\n"
                "NOTHING ON THIS UNIVERSE HAS BEEN VALIDATED. No seed, "
                "sub-period, shuffle or top-N test has been run on these 50 "
                "names, and no liquidity or\nmarket-impact study exists for "
                "this panel. Every number here is a research backtest with a "
                "flat 0.15% slippage and no market-impact model.\n"),
        },
    )

# ONLY THE UNIVERSES WHOSE CONFIG IS PRESENT. Declaration order is preserved, so
# a universe that is still here occupies the same position it always did -- LIVE's
# order is documented below as declaration order and callers rely on that.
#
# n50 IS APPENDED, NEVER INSERTED, so mid and n100 keep positions 0 and 1 and
# every caller relying on declaration order sees what it saw before. Same
# constraint as naming.AXES, same reason: position is load-bearing somewhere the
# row itself does not mention.
REGISTRY = {u.tag: u for u in (_MID, _N100, _N50)}

# THE METRICS DIRECTORY IS CREATED AT IMPORT, exactly as config_mid.py and
# config_n100.py did with METRICS_DIR.mkdir(parents=True, exist_ok=True) at module
# level. Steps write into it without checking it exists, so the side effect has to
# survive the merge or the first write on a fresh checkout fails.
for _u in REGISTRY.values():
    _u.metrics_dir.mkdir(parents=True, exist_ok=True)

# The universes that ship. Eighteen of the nineteen hand-rolled registries carry
# exactly these two; only nt_run.py knows all four.
#
# ITS ORDER IS DECLARATION ORDER (mid, n100) AND IS NOT THE REPORTING ORDER. Every
# study script in this repository iterates n100 FIRST and accumulates a combined
# verdict in that sequence, so a caller whose OUTPUT depends on order must name
# the universes explicitly -- REGISTRY["n100"], REGISTRY["mid"] -- rather than
# iterate LIVE. Using LIVE for that swapped the two blocks of
# verify_v34_arms.py's report, which is how this note came to exist.
LIVE = list(REGISTRY.values())


# ---------------------------------------------------------------------------
# REPORTING ORDER -- the sequence a MULTI-UNIVERSE report puts universes in.
# ---------------------------------------------------------------------------
# THIS IS NOT REGISTRY ORDER AND MUST NOT BE. Registry order is declaration order
# (58, 74, mid, n100) and it is the right answer for selection, where the question
# is "which universes", a set. It is the WRONG answer for a report, where position
# is visible in a filename, a legend and a colour assignment.
#
# n100 BEFORE mid, because every study script in this repository iterates n100
# first -- the note on LIVE above says so -- and the published combined chart is
# chart_COMBINED_n100_mid.png. Sorting these two the other way would rename a
# figure that is already referenced in docs/README.md.
#
# LIVE BEFORE RETIRED, because the live pair is the project's current scope and a
# combined chart that leads with a retired universe misstates what is being
# reported. Within the retired pair, declaration order: 58 then 74.
#
# A TAG ABSENT FROM REGISTRY IS SIMPLY SKIPPED, so this stays correct as universes
# are removed. A registered tag absent from THIS tuple would be dropped silently
# from every combined report, which is why report_order() raises on one instead.
# n50 SITS NEXT TO n100 BECAUSE IT IS A SUBSET OF IT, so the two large-cap
# lines are adjacent in every combined report rather than separated by mid.
REPORT_ORDER = ("nifty100", "nifty50", "midcap150", "58", "74")


# ---------------------------------------------------------------------------
# WHAT THIS RUN SELECTED -- registration and selection are NOT the same thing.
# ---------------------------------------------------------------------------
# REGISTRY answers "which universes EXIST in this checkout". A run answers a
# narrower question: "which universes did the caller ASK FOR". Until now the two
# were conflated, because every multi-universe step gated on `"74" in REGISTRY`.
# That is correct for a REMOVED universe and wrong for an UNSELECTED one:
# `run.py --universe mid,58` would still put 74 on the fair-comparison chart,
# because 74 is registered even though nobody asked for it.
#
# A REPORT MUST NEVER SHOW A UNIVERSE THE CALLER DID NOT SELECT. So selection is
# recorded here, next to the registry, and the steps that build multi-universe
# output ask `selected_tags()` instead of `REGISTRY`.
#
# THE DEFAULT IS EVERY REGISTERED UNIVERSE, which is exactly what those steps saw
# before this existed. So a step run on its own -- `python results/<step>.py`, a
# test, an import from a notebook -- behaves as it always did, and a full
# `--universe all` run is unchanged. Verified byte-identical on all 281 artefacts.
_SELECTED = None


def set_selection(tags):
    """Record which universes this run selected. Called once by run.py.

    Unknown tags raise: silently narrowing a selection to nothing is how a run
    produces no output and reports success. Passing None restores the default.
    """
    global _SELECTED
    if tags is None:
        _SELECTED = None
        return
    want = [t.tag if hasattr(t, "tag") else t for t in tags]
    unknown = [t for t in want if t not in REGISTRY]
    if unknown:
        raise KeyError(f"cannot select unregistered universe(s) {', '.join(unknown)}; "
                       f"registered: {', '.join(REGISTRY)}")
    _SELECTED = [t for t in REGISTRY if t in set(want)]


def selected_tags():
    """The tags this run is working on, in REGISTRY order.

    Defaults to every registered universe when nothing has set a selection.
    Intersected with REGISTRY on every call, so a universe removed after the
    selection was set cannot come back through this door.
    """
    if _SELECTED is None:
        return list(REGISTRY)
    return [t for t in _SELECTED if t in REGISTRY]


def selected():
    """selected_tags() as Universe objects."""
    return [REGISTRY[t] for t in selected_tags()]


def report_order(tags):
    """`tags` in REPORT_ORDER sequence. Accepts any iterable of tags or Universes.

    Raises on a registered tag this tuple does not name, rather than dropping it:
    a new universe added to REGISTRY and forgotten here would otherwise vanish from
    every multi-universe chart with no error, which is the failure mode the whole
    registry exists to prevent.
    """
    want = [t.tag if hasattr(t, "tag") else t for t in tags]
    missing = [t for t in want if t not in REPORT_ORDER]
    if missing:
        raise KeyError(
            f"universes/registry.REPORT_ORDER does not name {', '.join(missing)}. "
            "Every registered universe must have a position there, or it would be "
            "dropped from combined reports without an error. Add it.")
    seen = set(want)
    return [t for t in REPORT_ORDER if t in seen]


def get(tag):
    """One universe by tag, with a message that lists the alternatives."""
    try:
        return REGISTRY[tag]
    except KeyError:
        raise KeyError(
            f"unknown universe {tag!r}; known: {', '.join(sorted(REGISTRY))}") from None


def from_argv(argv, default=None):
    """Read --universe=<tag> from a command line.

    Reproduces what nt_run.py, nt_verify.py, shuffle_test.py and validate_topn.py
    each do by hand, including the convention that no flag means "every live
    universe" rather than an error.
    """
    picked = [t for t in REGISTRY if f"--universe={t}" in argv]
    if picked:
        return [REGISTRY[t] for t in picked]
    return [REGISTRY[default]] if default else list(LIVE)
