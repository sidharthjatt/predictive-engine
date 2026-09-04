"""
_frozen_guard.py -- refuses to regenerate a retired universe's artefacts by accident.
=====================================================================================

WHAT IS FROZEN, AND WHY IT NEEDS A GUARD AT ALL
    The 58 and the 74 are retired. Their published numbers must not move, which is
    why their builders pin the defective `purge_mode="calendar"`, why their engines
    pin `value_at_open=False`, and why their windows are still on the old year cut
    rather than config.BT_START_DATE/BT_END_DATE.

    Every one of those pins survives a re-run. What does NOT survive a re-run is the
    artefact itself: `results*/metrics/` is gitignored in full, so the CSVs, charts
    and JSON in those directories exist in exactly one copy, on one machine, with no
    version-control history behind them. A single stray
    `python results/engine_v2_final.py` overwrites a published artefact with no way
    back. That is the accident this guard exists to prevent -- not a wrong number,
    but an unrecoverable one.

HOW IT BEHAVES
    Import it and call guard() before the script writes anything. By default it
    refuses and exits. Setting ALLOW_FROZEN_WRITE=1 in the environment lets the write
    proceed.

    run_all.py sets that variable once, before it spawns any step, so a full pipeline
    run regenerates the retired universes exactly as it always did -- the guard is
    invisible to it. What the guard stops is the OTHER way these scripts get run: by
    hand, one at a time, usually while investigating something unrelated.

WHY AN ENVIRONMENT VARIABLE RATHER THAN A FLAG
    Because the thing being guarded is a subprocess spawned by run_all.py, and a
    child inherits os.environ at spawn. A command-line flag would have to be threaded
    through run() and every PIPELINE_ORDER entry; an env var is set once at the top of
    run_all.py, beside the determinism pin that is already set the same way and for
    the same reason.

THIS GUARD DOES NOT MAKE A FROZEN SCRIPT SAFE TO EDIT
    It protects the OUTPUT. The literals inside these files -- the year windows, the
    purge mode, TOP_N/BUFFER, the value_at_open pins -- are still load-bearing and
    still must not change. See KNOWN_ISSUES.md.
"""
import os
import sys

ENV_OVERRIDE = "ALLOW_FROZEN_WRITE"


def guard(universe, what="artefacts"):
    """Refuse to run unless the caller has explicitly allowed frozen writes.

    `universe` is the retired universe this script serves ("58", "74", "58/74"),
    used only in the message so the reader knows what was about to be overwritten.
    """
    if os.environ.get(ENV_OVERRIDE) == "1":
        return
    script = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else "this script"
    print("\n" + "!" * 88, file=sys.stderr)
    print(f"REFUSING TO RUN {script} -- it writes FROZEN {universe} {what}",
          file=sys.stderr)
    print("!" * 88, file=sys.stderr)
    print(f"""
  The {universe} universe is retired. Its published {what} must not move, and they
  are NOT in version control -- results*/metrics/ is gitignored in full, so what is
  on disk is the only copy. Running this script would overwrite it with no way back.

  If that is genuinely what you want, say so explicitly:

      ALLOW_FROZEN_WRITE=1 ./venv/bin/python {sys.argv[0] if sys.argv else script}

  run_all.py sets ALLOW_FROZEN_WRITE=1 for every step it spawns, so a full pipeline
  run is unaffected by this guard and needs no special handling.

  Before overriding, copy results/metrics, results74/metrics, results_mid/metrics
  and results_n100/metrics somewhere outside the repository. That is a copy, not a
  change, and it is the only thing standing between a re-run and a lost artefact.
""", file=sys.stderr)
    raise SystemExit(2)
