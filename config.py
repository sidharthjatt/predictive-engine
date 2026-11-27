"""
config.py -- reading price and panel files, and the score-cache keys.

read_price_csv / read_table / write_panel read and write every data file;
panel_code_key, cache_staleness and require_cache decide whether a cached score
panel is current. The constants and directories are in settings.py.
"""

from pathlib import Path

import pandas as _pd

from settings import PROJECT_ROOT, list_dir

# ============================================================================
# CENTRAL DATE HANDLING -- read every raw data file through this.
# Whatever the format (ISO / M-D-Y / D-M-Y / D-Mon-Y), it is auto-detected and
# converted to datetime. For a new data source, use read_price_csv() and nothing
# else needs to change.
#
# Detection is driven by evidence, not by guessing:
#   a value above 12 in slot 1  -> that slot is the DAY  -> dayfirst=True
#   a value above 12 in slot 2  -> that slot is the DAY  -> dayfirst=False
#   above 12 in both slots      -> corrupt or mixed -> raise (never fail silently)
#   never above 12 anywhere     -> genuinely ambiguous -> warn and assume DD-MM
# ============================================================================


def smart_parse_dates(s, source=""):
    """Detect the date format from the data itself and return datetimes."""
    s = _pd.Series(s).astype(str).str.strip()
    sample = s[s.ne("") & s.ne("nan")]
    if len(sample) == 0:
        return _pd.to_datetime(s, errors="coerce")

    # ISO (YYYY-MM-DD) -- unambiguous, year first
    if sample.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}").mean() > 0.9:
        return _pd.to_datetime(s, errors="coerce")

    parts = sample.str.extract(r"^(\d{1,4})[-/](\d{1,4})[-/]")
    if parts.isna().all().any():          # e.g. 03-Jan-2000
        return _pd.to_datetime(s, errors="coerce", dayfirst=True)

    a = _pd.to_numeric(parts[0], errors="coerce")
    b = _pd.to_numeric(parts[1], errors="coerce")
    first_is_day, second_is_day = bool((a > 12).any()), bool((b > 12).any())

    if first_is_day and second_is_day:
        raise ValueError(
            f"Ambiguous/corrupt dates in {source or 'input'}: "
            "both first and second slot exceed 12. Check the file."
        )
    if first_is_day:
        return _pd.to_datetime(s, errors="coerce", dayfirst=True)
    if second_is_day:
        return _pd.to_datetime(s, errors="coerce", dayfirst=False)

    print(f"    [WARN] {source or 'input'}: date format ambiguous "
          "(no day > 12 anywhere) -- assuming DD-MM. Verify if this is new data.")
    return _pd.to_datetime(s, errors="coerce", dayfirst=True)


# ---------------------------------------------------------------------------
# THE ONE READER FOR TABULAR DATA, AND THE ONE WRITER FOR PANELS
# ---------------------------------------------------------------------------
# MEASURED 2026-09-24 ON macOS arm64, Linux arm64 AND Linux amd64, same pandas
# 2.3.3: pandas' default read_csv float parser returns different last bits for
# the SAME bytes on macOS and on Linux (over a million cells of midcap50's raw
# panel), and on either platform it does not return the values the file was
# written from. float_precision="round_trip" is exact and identical on all
# three. A second checkout on another OS therefore read different scores from
# the same score panel. Every read of a CSV in this repository goes through
# read_table(); csv_reader_check.py fails on any pandas.read_csv call anywhere
# else.
#
# THE PANELS ARE PARQUET, not CSV: a binary column store round-trips float64
# exactly with no parsing at all. read_table() dispatches on the suffix, so a
# caller does not need to know which format a file is.
_PARQUET_KW = {"parse_dates", "usecols", "columns", "nrows"}


def read_table(path, **kw):
    """Read a CSV or parquet file exactly. CSV floats are parsed round-trip."""
    p = Path(path)
    if p.suffix == ".parquet":
        bad = set(kw) - _PARQUET_KW
        if bad:
            raise TypeError(f"read_table({p.name}): {sorted(bad)} has no meaning "
                            f"for a parquet file")
        cols = kw.get("usecols", kw.get("columns"))
        df = _pd.read_parquet(p, columns=list(cols) if cols is not None else None)
        for c in kw.get("parse_dates") or []:
            if c in df.columns and not _pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = _pd.to_datetime(df[c])
        return df.head(kw["nrows"]) if kw.get("nrows") is not None else df
    if "float_precision" in kw:
        raise TypeError("read_table: float_precision is fixed to round_trip")
    return _pd.read_csv(p, float_precision="round_trip", **kw)


def write_panel(df, path):
    """Write a score or raw panel as parquet. Integer columns are written as
    int64, the dtype the CSV panels were read back as before 2026-09-24."""
    df = df.copy()
    for c in df.columns:
        if _pd.api.types.is_integer_dtype(df[c]) and df[c].dtype != "int64":
            df[c] = df[c].astype("int64")
    # naming: axis-free -- the path is a registry cache attribute; panels carry no run axis
    df.to_parquet(path, index=False)


def read_price_csv(path, date_col="date", **kw):
    """Read any raw price CSV; dates auto-normalised to datetime."""
    df = read_table(path, **kw)
    if date_col in df.columns:
        df[date_col] = smart_parse_dates(df[date_col], source=str(path))
    return df


# ---------------------------------------------------------------------------
# CACHE RESOLUTION -- one place, so a stale or missing cache fails loudly
# ---------------------------------------------------------------------------
# A PANEL'S IDENTITY IS THE CONTENT OF THE CSVs IT WAS BUILT FROM.
#
# Until 2026-09-18 it was the path alone, and a repointed universe went on
# reading the old vendor's 217 MB panel. From 2026-09-18 to 2026-09-23 it was
# the path plus the source DIRECTORY, which caught a repoint and nothing else:
# removing SUZLON.csv from midcap50's source left the directory unchanged, the
# cached panel passed, and the run exited 0 still trading SUZLON 38 times.
#
# SO THE SIDECAR RECORDS seed_cache_key.source_key() OVER THE CONSTITUENT FARM:
# every CSV name and the sha256 of its bytes. The farm is what build_panel
# globs, so it is exactly the set of files scored. A panel is current only if
# that key matches the farm as it is now. The directory is recorded beside it
# for a reader and is not compared: the same bytes in another checkout are the
# same panel, which is what lets a copied tree reuse its cache.
#
# WHAT A MISS DOES DEPENDS ON WHO ASKED. The builder (build_scores_step) prints
# the reason and rebuilds. A reader raises CacheSourceError naming the reason and
# the command that rebuilds: a reader that rebuilt a 70-minute panel in passing
# would hide the fact that its input changed. There is no flag to accept a stale
# panel.
SOURCE_SIDECAR_SUFFIX = ".source"


class CacheSourceError(RuntimeError):
    """A cache could not be shown to have been built on the current source."""


def cache_source_file(cache_path):
    """The sidecar recording the source key `cache_path` was built from."""
    p = Path(cache_path)
    return p.with_name(p.name + SOURCE_SIDECAR_SUFFIX)


def source_key_for(u):
    """seed_cache_key.source_key over u's constituent farm, built if needed."""
    from seed_cache_key import source_key
    if u.raw_data_dir is None:
        raise CacheSourceError(
            f"{u.tag}: a universe with no raw_data_dir has no panel to key.")
    return source_key(list_dir(u.prepare_data_dir(), "*.csv"))


def _code_tokens(src):
    """The token stream of Python source with comments and blank lines removed.

    A comment or a blank line cannot change what the code computes, so neither
    may change a cache key. Everything else -- names, operators, literals,
    docstrings, error strings, indentation -- is kept, token by token.
    """
    import io
    import textwrap
    import tokenize
    toks = tokenize.generate_tokens(io.StringIO(textwrap.dedent(src)).readline)
    return "\x00".join(f"{t.type}:{t.string}" for t in toks
                        if t.type not in (tokenize.COMMENT, tokenize.NL))


def _data_lines(path):
    """A data file's bytes with its `#` comment lines removed.

    engine_core._load_calendar reads the calendar with comment="#", so a header
    comment is invisible to the code and must be invisible to the key.
    """
    return b"".join(l for l in Path(path).read_bytes().splitlines(keepends=True)
                    if not l.lstrip().startswith(b"#"))


def panel_code_key():
    """sha256 over everything besides the source CSVs that determines a panel.

    COMMENTS ARE NOT PART OF THE KEY SINCE 2026-09-25. The functions below are
    hashed as token streams without comment tokens (_code_tokens), and the
    calendar without its `#` header (_data_lines), so rewording a comment does
    not force a rebuild. Docstrings and error strings are code tokens and are
    still covered. Changing this function changed every key once; all eight
    panels were rebuilt on 2026-09-25 and were byte-identical to the panels the
    previous key described.

    ADDED 2026-09-24. The key recorded only the source data, so a change to the
    feature code left every cached panel "current": a panel built by the old
    code would have been read as the output of the new. Covered: the functions
    that build and score the panel, the feature functions and their constants,
    results/numerics.py, the seed list, HORIZON and the purge constants, the
    scoring floor (start_axis.score_floor), the trading calendar and the LightGBM
    version. Nothing else, so an edit to the
    backtest code does not force a 75-minute rebuild. results/ratio_clean.py was
    covered from 2026-09-27 until it was removed on 2026-10-22.
    """
    import hashlib
    import inspect
    import lightgbm
    import engine_core as ec
    import features_v2 as fv
    import numerics
    from build_scores_step import SEEDS
    h = hashlib.sha256()
    for fn in (ec.canonical_price, ec._load_calendar, ec._check_calendar,
               ec.build_panel, ec._fit_seed, ec.training_set, ec.score_monthly,
               fv.add_stock_features, fv.add_market_relative_features,
               fv.cross_sectional_normalize):
        h.update(_code_tokens(inspect.getsource(fn)).encode())
    h.update(_code_tokens(Path(numerics.__file__).read_text()).encode())
    h.update(_data_lines(ec.TRADING_CALENDAR))
    h.update(repr((list(SEEDS), ec.HORIZON, ec.PURGE_EMBARGO, str(ec.score_floor().date()),
                   list(fv.FEATS_V2), fv.EXTREME_RET_HI, fv.EXTREME_RET_LO,
                   lightgbm.__version__)).encode())
    return "sha256:" + h.hexdigest()


# THE KEY A NOISE DRAW RECORDS, 2026-09-27. A draw is a rebuild of u's panel
# from a perturbed copy of u's farm, so it is fully determined by the code that
# builds panels (panel_code_key) and the unperturbed farm's bytes (source_key_for),
# plus the draw's own sigma and seed, which the record already carries. Every
# draw file and runs-CSV row stores both; a harness reuses a record only when both
# equal the current values, and reports and re-runs any record that does not.
RUN_KEY_FIELDS = ("panel_code", "source_digest")


def run_key(u):
    """{"panel_code": ..., "source_digest": ...} for universe u as it is now."""
    return {"panel_code": panel_code_key(),
            "source_digest": source_key_for(u)["digest"]}


def run_key_matches(rec, key):
    """True only if record `rec` (a dict or a row) carries exactly `key`.

    A record written before these fields existed has none of them and does not
    match: it is stale, not current by default.
    """
    return all(str(rec.get(k, "")) == key[k] for k in RUN_KEY_FIELDS)


def write_cache_source(cache_path, u, key):
    """Record `key` beside a cache. Called by whoever writes the cache.

    The key is taken BEFORE the build by the caller and passed in, so the
    sidecar describes the files that were read, not whatever is on disk after.
    """
    import json
    rel = root_relative(u.raw_data_dir)
    rec = {"universe": u.tag, "raw_data_dir": rel, "digest": key["digest"],
           "code": panel_code_key(),
           "n_files": key["n_files"], "files": key["files"]}
    if getattr(u, "is_pit", False):
        rec["membership"] = pit_membership_key(u)
    # naming: axis-free -- the sidecar's name is its cache's name plus a fixed
    # suffix, so it carries whatever axes that cache carries and adds none of
    # its own; there is no arm, cadence, profile or tax choice expressed here.
    cache_source_file(cache_path).write_text(json.dumps(rec, indent=1) + "\n")


def pit_membership_key(u):
    """What else a pit panel depends on: the membership file's bytes and the code
    that applies it (survivorship.apply_to_panel, member_mask and RENAMES). Static panels
    carry no such field, so their sidecars are unchanged."""
    import hashlib
    import inspect
    import survivorship as _sv
    h = hashlib.sha256(Path(u.membership_file).read_bytes())
    h.update(_code_tokens(inspect.getsource(_sv.apply_to_panel)).encode())
    h.update(_code_tokens(inspect.getsource(_sv.member_mask)).encode())
    h.update(repr(sorted(_sv.RENAMES.items())).encode())
    return "sha256:" + h.hexdigest()


def _cache_owner(path):
    """The registered universe whose cache `path` is, or None.

    IMPORTED LAZILY. settings.py is imported by this module at its own import
    time, and REGISTRY is built at the end of settings' import.
    """
    from settings import REGISTRY
    p = Path(path).resolve()
    for u in REGISTRY.values():
        for cand in (u.score_cache, u.raw_cache):
            if Path(cand).resolve() == p:
                return u
    return None


def cache_staleness(cache_path, u):
    """None if `cache_path` was built from u's current source, else the reason."""
    import json
    from seed_cache_key import key_difference
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return f"no panel at {cache_path}"
    side = cache_source_file(cache_path)
    if not side.exists():
        return f"no source sidecar ({side.name}), so what it was built from is unknown"
    try:
        rec = json.loads(side.read_text())
    except ValueError:
        return (f"{side.name} is in the pre-2026-09-23 format (a directory path "
                f"only), which cannot show whether a CSV was added or removed")
    code = panel_code_key()
    if rec.get("code") != code:
        return ("the code that builds panels changed since this one was built "
                "(config.panel_code_key)" if rec.get("code") else
                "it predates the code key (config.panel_code_key, 2026-09-24)")
    if getattr(u, "is_pit", False) and rec.get("membership") != pit_membership_key(u):
        return ("the membership file or the code that applies it changed since this "
                "pit panel was built (config.pit_membership_key)")
    cur = source_key_for(u)
    if rec.get("digest") == cur["digest"]:
        return None
    diff = key_difference(rec.get("files", {}), cur["files"])
    return (f"source changed since the panel was built ({rec.get('n_files')} -> "
            f"{cur['n_files']} files): {diff or 'digest differs'}")


def _verified(cache_path, what):
    """Return `cache_path` only if it was built from its universe's current source."""
    u = _cache_owner(cache_path)
    if u is None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  This path is not the score or raw cache of any registered\n"
            f"  universe, so which source it was built from cannot be\n"
            f"  established. A panel of unknown provenance is not usable as\n"
            f"  evidence. Add the row that owns it, or delete the file.")
    why = cache_staleness(cache_path, u)
    if why is not None:
        raise CacheSourceError(
            f"{what}: {cache_path}\n"
            f"  STALE PANEL -- refusing to return it: {why}.\n"
            f"  Every number computed from it would describe other data. Rebuild:\n"
            f"      ./venv/bin/python run.py --universe {u.tag} --steps pipeline")
    return cache_path


# ---------------------------------------------------------------------------
# THE SAME QUESTION, ONE LAYER UP: WHAT DATA DID A PUBLISHED ARTEFACT COME FROM
# ---------------------------------------------------------------------------
# The sidecar above protects CACHES. _cache_owner() matches only score_cache,
# raw_cache, score_tmp and raw_tmp, so a daily_trades or a v34_params -- the files
# people read and quote -- is covered by nothing.
#
# MEASURED 2026-09-20, WHICH IS WHY THIS EXISTS. midcap150's two tradeable
# artefacts were written 2026-09-17 against data/raw/MidCap150/clean. The universe
# was repointed at Final_Without_Survivorship_Data on 2026-09-18. Neither artefact
# said which source it came from, no gate compared one against the other, and the
# only reason it surfaced at all was someone reconstructing a median by hand. All
# seven gates were green throughout.
#
# WHOLE FILE, NOT A ROW COUNT. A row count catches a truncated or extended
# history and nothing else. The participation cap eats the VOLUME column, and a
# supplier that revised volume while leaving dates and prices untouched would pass
# a row count, pass a date-range check and pass a re-derivation of fill prices --
# every test available before this one. Hashing every byte catches it. It costs
# 0.11 s over midcap150's 96 MB and 0.30 s over nifty500's 312 MB, measured, which
# is small enough that there is no argument for a cheaper and weaker answer.
#
# THE LINK FARM IS WHAT IS HASHED, not raw_data_dir, because the farm is what
# build_panel globs. raw_data_dir is recorded beside it: if the two ever disagree
# the artefact carries both halves and the difference is readable.
def root_relative(p):
    """`p` resolved, as a path relative to the project root when it is inside it.
    A relative `p` is taken as already relative to the root, not to the cwd."""
    q = Path(p)
    q = (q if q.is_absolute() else PROJECT_ROOT / q).resolve()
    try:
        return str(q.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(q)


def data_fingerprint(data_dir, raw_data_dir):
    """What a published artefact records about the price data it was built from.

    Returns a dict with the resolved link directory, the resolved raw_data_dir,
    where the symlinks actually point, the file count, and
    seed_cache_key.source_key's digest over every CSV in the farm -- the same
    digest a panel's sidecar records.
    """
    from seed_cache_key import source_key
    import os
    d = Path(data_dir)
    files = list_dir(d, "*.csv")
    # WHERE THE FARM'S FILES COME FROM. Until 2026-09-24 the farm held symlinks
    # and this followed them. It now holds hard links or copies (see
    # Universe.prepare_data_dir), so each entry is checked against the file of
    # the same name in raw_data_dir: the same file, or a copy with the same size
    # and mtime. The recorded value is unchanged for a farm built from
    # raw_data_dir, which is what GATE 8 compares.
    raw = Path(raw_data_dir) if raw_data_dir else None

    def _from_raw(f):
        g = raw / f.name if raw is not None else None
        if g is None or not g.exists():
            return False
        if os.path.samefile(f, g):
            return True
        a, b = f.stat(), g.stat()
        return (a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns)

    if not files:
        target = None
    elif all(_from_raw(f) for f in files):
        target = str(raw.resolve())
    else:
        target = f"MIXED: {sum(not _from_raw(f) for f in files)} entries not from raw_data_dir"
    key = source_key(files)
    # PATHS ARE RECORDED RELATIVE TO THE PROJECT ROOT, 2026-09-23. They were
    # absolute, so the same data in a second checkout wrote a different
    # v34_params*.json. GATE 8 compares through root_relative() on both sides,
    # so artefacts written with absolute paths before this still compare.
    return {
        "link_dir": root_relative(d),
        "link_target_dir": root_relative(target) if target and not target.startswith("MIXED") else target,
        "raw_data_dir": root_relative(raw_data_dir) if raw_data_dir else None,
        "n_files": key["n_files"],
        "digest": key["digest"],
        "digest_covers": ("every byte of every CSV in link_dir, the volume column "
                          "included; recompute with config.data_fingerprint()"),
    }


def require_cache(path, what="score panel"):
    """Return `path` if it exists and is current, or raise with the remedy.

    ONE LOCATION PER PANEL SINCE 2026-09-23. There used to be a working copy in
    /tmp and a permanent copy under results*/metrics/, and this took both. /tmp
    is shared by every checkout on a machine, so a second checkout read the
    first one's panel. Both copies are now one file under cache/<tag>/.
    """
    p = Path(path)
    if p.exists():
        return _verified(p, what)
    u = _cache_owner(p)
    tag = u.tag if u is not None else "<universe>"
    raise FileNotFoundError(
        f"{what} not found at {p}.\n"
        f"  Build it with\n"
        f"      ./venv/bin/python run.py --universe {tag} --steps pipeline\n"
        f"  using the venv interpreter; see requirements.txt.")
