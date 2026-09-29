"""python_floor.py -- stop at start-up on a Python older than the pins need.

requirements.txt was resolved on Python 3.12.13 (the repo venv, and
installed_versions.txt is its `pip freeze`). scipy==1.18.1 and
nautilus_trader==1.229.0 have no release for 3.11, so on 3.11 pip installs
nothing and the failure surfaces later as an unrelated ImportError.

Call require() before any third-party import. This module imports only sys so
that it runs on the interpreter it is meant to reject.
"""
import sys

REQUIRED = (3, 12)
RESOLVED_ON = "3.12.13"


def require(script):
    """Exit with one message if the running Python is older than REQUIRED."""
    if sys.version_info[:2] >= REQUIRED:
        return
    need = "%d.%d" % REQUIRED
    have = "%d.%d.%d" % sys.version_info[:3]
    sys.exit(
        "%s needs Python %s or newer; this is Python %s (%s).\n"
        "The pinned requirements were resolved on Python %s. Build the venv with it:\n"
        "    python%s -m venv venv\n"
        "    ./venv/bin/python -m pip install -r requirements.txt -c installed_versions.txt\n"
        "then run ./venv/bin/python %s"
        % (script, need, have, sys.executable, RESOLVED_ON, need, script)
    )
