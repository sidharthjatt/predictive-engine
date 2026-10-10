#!/usr/bin/env python3
"""check_data.py -- does your copy of the price data match the one the results were built on?

    python3 check_data.py                                  # all eight universes
    ./venv/bin/python check_data.py --universe=midcap50    # one universe's folder
    python3 check_data.py --write                          # owner only: rewrite both manifests
    python3 check_data.py --pit                            # the point-in-time inputs

Run it after copying the price data into data/raw/ and before running anything
else. It needs only the Python standard library, so it works before the venv is
built. Exit 0 means every file the manifest lists is present with the same
SHA-256, and no extra CSV sits in a folder the pipeline reads. Anything else
exits 1 and names each file that is missing, different or extra.

--universe=<tag> checks only that universe's folder, for a copy holding one
universe. The folder comes from universes/registry.py (the row's raw_data_dir), so
this form needs the venv; the plain form needs only the standard library. An
unknown tag exits 2 with the list of valid universes.

WHY EXTRA FILES FAIL. A universe is defined by the CSVs in its supplier folder
(universes/registry.py builds each symbol list from the folder), so one extra
constituent file changes that universe and every figure computed on it.

WHAT IS COVERED. Only data/raw/Final_Without_Survivorship_Data/, the one folder
the pipeline reads (every universe's raw_data_dir in universes/registry.py is
under it). Other folders under data/raw/ are not read by any pipeline step and
are not in the manifest. The manifest has the sha256sum format, one
"<sha256>  <path relative to the repository root>" line per file, sorted by path,
so `shasum -a 256 -c data/RAW_DATA_SHA256.txt` checks it too (without the
extra-file test).

THE SECOND MANIFEST, 2026-10-10. data/RAW_DATA_SHA256_PIT.txt covers what only a
--survivorship pit run reads: data/raw/Final_With_Survivorship_Data/ and the
membership files in data/raw/Survivorship_Bias/. --pit checks it, and run.py
checks the selected universes' part of it before a pit run starts (check_pit).
The plain form still checks only the static manifest.
"""
import hashlib
import sys
from pathlib import Path
from paths import list_dir

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "data" / "RAW_DATA_SHA256.txt"
COVERED = ROOT / "data" / "raw" / "Final_Without_Survivorship_Data"
PIT_MANIFEST = ROOT / "data" / "RAW_DATA_SHA256_PIT.txt"
PIT_COVERED = (ROOT / "data" / "raw" / "Final_With_Survivorship_Data",
               ROOT / "data" / "raw" / "Survivorship_Bias")
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def on_disk():
    """Every file under COVERED, as repository-relative POSIX paths, sorted."""
    if not COVERED.is_dir():
        return []
    return sorted(p.relative_to(ROOT).as_posix() for p in list_dir(COVERED, recursive=True)
                  if p.is_file())


def read_manifest(manifest=MANIFEST):
    out = {}
    for n, line in enumerate(manifest.read_text().splitlines(), 1):
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64:
            raise SystemExit(f"{manifest.name}:{n}: not '<sha256>  <path>': {line!r}")
        out[rel] = digest
    return out


def pit_on_disk():
    """Every file under PIT_COVERED, as repository-relative POSIX paths, sorted."""
    return sorted(p.relative_to(ROOT).as_posix() for d in PIT_COVERED if d.is_dir()
                  for p in list_dir(d, recursive=True) if p.is_file())


def write():
    files = on_disk()
    if not files:
        raise SystemExit(f"nothing to hash: {COVERED.relative_to(ROOT)} is missing or empty")
    lines = [f"{sha256(ROOT / f)}  {f}" for f in files]
    # naming: axis-free -- one fixed manifest of the static price files.
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}: {len(lines)} files")
    pit = pit_on_disk()
    if pit:
        # naming: axis-free -- one fixed manifest of the pit input files.
        PIT_MANIFEST.write_text("\n".join(f"{sha256(ROOT / f)}  {f}" for f in pit) + "\n")
        print(f"wrote {PIT_MANIFEST.relative_to(ROOT)}: {len(pit)} files")
    return 0


def check_pit(tags=None):
    """The pit inputs against PIT_MANIFEST: every file, or only the with-survivorship
    folders and membership files of `tags`. 0 on a match, 1 otherwise."""
    if not PIT_MANIFEST.exists():
        print(f"FAIL -- {PIT_MANIFEST.relative_to(ROOT)} is missing from this checkout.")
        return 1
    want, have = read_manifest(PIT_MANIFEST), pit_on_disk()
    if tags is not None:
        sys.path.insert(0, str(ROOT))
        from universes.registry import REGISTRY
        keep = []
        for t in tags:
            u = REGISTRY[t]
            keep.append(Path(u.survivorship_data_dir).resolve().relative_to(ROOT).as_posix() + "/")
            keep.append(Path(u.membership_file).resolve().relative_to(ROOT).as_posix())
        sel = lambda f: any(f == k or (k.endswith("/") and f.startswith(k)) for k in keep)
        want = {f: d for f, d in want.items() if sel(f)}
        have = [f for f in have if sel(f)]
    missing = sorted(f for f in want if f not in set(have))
    extra = sorted(f for f in have if f not in want)
    changed = [f for f in sorted(set(have) & set(want)) if sha256(ROOT / f) != want[f]]
    for label, items in (("MISSING", missing), ("DIFFERENT", changed), ("EXTRA", extra)):
        for f in items:
            print(f"  {label:<9} {f}")
    if missing or changed or extra:
        print(f"FAIL -- pit inputs: {len(missing)} missing, {len(changed)} different, "
              f"{len(extra)} extra, of {len(want)} files in "
              f"{PIT_MANIFEST.relative_to(ROOT)}.")
        return 1
    print(f"PASS -- all {len(want)} pit input files match "
          f"{PIT_MANIFEST.relative_to(ROOT)} and no extra file is present.")
    return 0


def _universe_folder(argv):
    """The one folder --universe=<tag> names, as a repository-relative prefix, or None."""
    vals = [a.split("=", 1)[1] for a in argv if a.startswith("--universe=")]
    if not vals:
        return None
    sys.path.insert(0, str(ROOT))
    from universes.registry import REGISTRY, check_tags
    tag = check_tags(vals[-1:])[0]
    return Path(REGISTRY[tag].raw_data_dir).resolve().relative_to(ROOT).as_posix() + "/"


def not_covered():
    """(folder, bytes) for every folder under data/raw/ this check does not cover."""
    raw = ROOT / "data" / "raw"
    out = []
    for d in (p for p in list_dir(raw) if p.is_dir() and p != COVERED
              and p not in PIT_COVERED):
        out.append((d.name, sum(f.stat().st_size for f in list_dir(d, recursive=True) if f.is_file())))
    return out


def check(argv=()):
    if not MANIFEST.exists():
        print(f"FAIL -- {MANIFEST.relative_to(ROOT)} is missing from this checkout.")
        return 1
    want = read_manifest()
    have = on_disk()
    prefix = _universe_folder(argv)
    if prefix is not None:
        want = {f: d for f, d in want.items() if f.startswith(prefix)}
        have = [f for f in have if f.startswith(prefix)]
        print(f"  checking one folder: {prefix}")
    if not have:
        print(f"FAIL -- {prefix or (COVERED.relative_to(ROOT).as_posix() + '/')} is "
              "missing or empty. Copy the price data there first; see README, "
              "'The price data'.")
        return 1
    have_set = set(have)
    missing = sorted(f for f in want if f not in have_set)
    extra = sorted(f for f in have if f not in want)
    changed = []
    for i, f in enumerate(sorted(have_set & set(want)), 1):
        if sha256(ROOT / f) != want[f]:
            changed.append(f)
        if i % 250 == 0:
            print(f"  ... {i} files hashed", flush=True)
    for label, items in (("MISSING", missing), ("DIFFERENT", changed), ("EXTRA", extra)):
        for f in items:
            print(f"  {label:<9} {f}")
    if missing or changed or extra:
        print(f"FAIL -- {len(missing)} missing, {len(changed)} different, {len(extra)} "
              f"extra, of {len(want)} files in the manifest. Do not run the pipeline "
              "on this copy: its figures would not be the published ones.")
        return 1
    print(f"PASS -- all {len(want)} files match {MANIFEST.relative_to(ROOT)} "
          "and no extra file is present.")
    extra_dirs = not_covered()
    if extra_dirs:
        print("  not checked, read by no pipeline step: "
              + ", ".join(f"data/raw/{n}/ ({b / 1e6:,.0f} MB)" for n, b in extra_dirs))
    print(f"  the pit inputs are checked by --pit against "
          f"{PIT_MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    _a = sys.argv[1:]
    raise SystemExit(write() if "--write" in _a else check_pit() if "--pit" in _a
                     else check(_a))
