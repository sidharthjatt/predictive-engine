"""seed_cache_key.py -- the key for a cached model fit, in one place.

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
