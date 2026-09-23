"""seed_cache_key.py -- the keys for cached model fits and cached panels, in one place.

Two keys live here: seed_cache_key() for a cached fit, and source_key() for the
price CSVs a score or raw panel is built from (see the block above
source_key()). Both hash content, never a path or an mtime.

WHY THIS EXISTS. Two scripts cache score_monthly's output under /tmp and read it
back on a later run: validate_sizing.py's T2 and results/validate_engine.py's T2.
Both were keyed on the universe and the INDEX into SEED_SETS and nothing else --
no code hash, no panel hash -- so neither could miss on a code change or a panel
change. A cache written by any earlier engine against any earlier panel landed on
the path a later run reads and was read back as current, with no warning.

    validate_sizing  /tmp/VALSIZE_{universe}_seed{i}.csv     found 2026-09-22
    validate_engine  /tmp/V2VAL_{mid,n100}_seed{i}.csv       found 2026-09-22

The first was fixed with a private copy of this logic. The second needed the same
thing, and a second copy is how this repository already lost four tables to
drift -- REQUIRED_INPUTS, PIPELINE_ORDER, REPORT_ORDER and FILES. One definition,
both callers.

WHAT A CALLER MUST PASS, AND WHY EACH ONE.
    code_files  every source file whose contents can change the fit. Both callers
                pass results/engine_core.py (score_monthly IS the computation),
                config.py (the backtest window), and THEIR OWN FILE, because each
                chooses the seed sets and the columns written to the cache.
    panel_path  the data fit against. Hashed by CONTENT, streamed. Not by path
                and not by mtime: two panels at one path is how this repository
                lost track of which source produced midcap150's artefacts.
    parts       everything else that selects the computation -- the universe tag,
                the seed list, the purge mode. Values, not indices: "seed set 1"
                is not a fact about the seeds.

This file hashes ITSELF as well. It cannot change the fit, but a key function
that can be edited without invalidating the keys it already issued is the same
defect one level up.

THERE IS NO OVERRIDE FLAG AND THERE SHOULD NOT BE. An escape hatch on a
correctness key is the silent reuse this replaces. A miss is a refit.
"""
import hashlib
from pathlib import Path

_SELF = Path(__file__).resolve()


def seed_cache_key(code_files, panel_path, parts, length=16):
    """Return a short hex key over code, panel content and the parts given.

    `code_files` and `panel_path` are paths; `parts` is any repr-able structure.
    Raises rather than returning a weak key if a named file is missing: a key
    computed over a file that is not there would silently collide with one that
    had it.
    """
    h = hashlib.sha256()
    for f in list(code_files) + [_SELF]:
        p = Path(f)
        if not p.exists():
            raise FileNotFoundError(
                f"seed_cache_key: {p} does not exist, so the key would not "
                f"describe the code that produced the fit")
        h.update(p.read_bytes())
    p = Path(panel_path)
    if not p.exists():
        raise FileNotFoundError(f"seed_cache_key: panel {p} does not exist")
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    h.update(repr(parts).encode())
    return h.hexdigest()[:length]


# ---------------------------------------------------------------------------
# THE SOURCE-DATA KEY. Same rule as the fit key above -- content, never a path or
# an mtime -- applied to the directory of price CSVs a panel is built from.
# ---------------------------------------------------------------------------
# Until 2026-09-23 a score panel's sidecar recorded only the DIRECTORY it was
# built from. Removing SUZLON.csv from midcap50's source left the directory name
# unchanged, the cached panel passed its check, and the run exited 0 trading
# SUZLON 38 times under a header that said "48 constituents".
#
# THE ALGORITHM IS config.data_fingerprint's, MOVED HERE, NOT A SECOND ONE. For
# each file in name order: the stem, then the sha256 of its bytes. Every
# published v34_params*.json records a digest computed this way, and GATE 8
# compares against it, so changing the algorithm would fail every artefact on
# disk. This function does NOT hash its own source, unlike seed_cache_key: its
# output is a fingerprint of data recorded in published artefacts, and it must
# stay stable across edits to this file.
_FILE_HASHES = {}      # (resolved path, size, mtime_ns) -> hex, per process


def _file_sha256(p):
    st = p.stat()
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _FILE_HASHES:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _FILE_HASHES[k] = h.hexdigest()
    return _FILE_HASHES[k]


def source_key(files):
    """Content key over a set of source CSVs.

    Returns {"digest": "sha256:<hex>", "n_files": n, "files": {stem: sha256}}.
    `files` may be symlinks; the bytes read are the targets'. The per-file map is
    what lets a key miss say WHICH names were added, removed or changed.
    """
    h = hashlib.sha256()
    per = {}
    for f in sorted((Path(x) for x in files), key=lambda x: x.name):
        d = _file_sha256(f.resolve())
        per[f.stem] = d
        h.update(f.stem.encode())
        h.update(bytes.fromhex(d))
    return {"digest": "sha256:" + h.hexdigest(), "n_files": len(per), "files": per}


def key_difference(old_files, new_files):
    """One line naming what changed between two `files` maps, or None if equal."""
    removed = sorted(set(old_files) - set(new_files))
    added = sorted(set(new_files) - set(old_files))
    changed = sorted(s for s in set(old_files) & set(new_files)
                     if old_files[s] != new_files[s])
    if not (removed or added or changed):
        return None

    def _few(xs):
        return ", ".join(xs[:8]) + (f" (+{len(xs) - 8} more)" if len(xs) > 8 else "")
    parts = []
    if removed:
        parts.append(f"{len(removed)} removed: {_few(removed)}")
    if added:
        parts.append(f"{len(added)} added: {_few(added)}")
    if changed:
        parts.append(f"{len(changed)} changed content: {_few(changed)}")
    return "; ".join(parts)
