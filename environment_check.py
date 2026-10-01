"""environment_check.py -- stop at start-up if the venv is on an exFAT or FAT drive.

macOS writes a "._" AppleDouble file beside every file it copies to an exFAT or
FAT drive. Inside site-packages those files break installed packages, so a venv
there fails later with an unrelated import or decode error. The repository
itself may sit on such a drive: every directory listing in the code skips "._"
files (paths.list_dir), so that is reported as a note and the run continues.

Call require() before any third-party import. Standard library only, so it runs
on an environment too broken to import pandas.
"""
import os
import re
import subprocess
import sys
import sysconfig
from pathlib import Path

FAT_TYPES = {"exfat", "msdos", "vfat", "fat", "fat12", "fat16", "fat32"}


def fs_type(path):
    """The file system type of the volume holding `path`, lower case, or None."""
    p = Path(path).resolve()
    if sys.platform == "win32":
        import ctypes
        root = p.anchor
        buf = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0, None, None, None, buf, len(buf))
        return buf.value.lower() if ok else None
    try:
        out = subprocess.run(["mount"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    best, kind = None, None
    for line in out.splitlines():
        # macOS: "/dev/disk4s1 on /Volumes/T7 (exfat, local, ...)"
        # Linux: "/dev/sda1 on /mnt/usb type vfat (rw, ...)"
        m = re.match(r"^.+? on (.+?) (?:\((\w+)|type (\w+))", line)
        if not m:
            continue
        mp = Path(m.group(1))
        if (p == mp or mp in p.parents) and (best is None or len(mp.parts) > len(best.parts)):
            best, kind = mp, (m.group(2) or m.group(3)).lower()
    return kind


def first_appledouble(root):
    """The first "._" file under `root`, or None."""
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.startswith("._"):
                return Path(dirpath) / f
    return None


def require(script, repo):
    """Exit with one message if the running environment is on an exFAT or FAT
    drive or has "._" files in site-packages. Print a note if only `repo` is."""
    env = Path(sys.prefix)
    env_fs = fs_type(env)
    site = sorted({sysconfig.get_paths()[k] for k in ("purelib", "platlib")})
    stray = next((x for x in map(first_appledouble, site) if x), None)
    repo_fs = fs_type(repo)
    repo_line = (f"The repository folder {repo} is on a drive formatted as {repo_fs}. That alone is fine:\n"
                 f"the code skips \"._\" files."
                 if repo_fs in FAT_TYPES else
                 f"The repository folder {repo} is not on an exFAT or FAT drive.")
    if env_fs in FAT_TYPES or stray:
        found = []
        if env_fs in FAT_TYPES:
            found.append(f"the environment {env} is on a drive formatted as {env_fs}")
        if stray:
            found.append(f"site-packages holds \"._\" files, for example {stray}")
        sys.exit(
            f"{script} cannot start: {' and '.join(found)}.\n"
            "The venv is on an external drive. macOS writes \"._\" files on exFAT and FAT\n"
            "drives, and in site-packages they break installed packages. Create the venv\n"
            "on the internal disk and run with it:\n"
            "    python3.12 -m venv ~/venvs/algo_trading\n"
            "    ~/venvs/algo_trading/bin/python -m pip install -r requirements.txt "
            "-c installed_versions.txt\n"
            f"    ~/venvs/algo_trading/bin/python {script}\n"
            f"{repo_line}")
    if repo_fs in FAT_TYPES:
        print(f"NOTE: {repo_line}")
