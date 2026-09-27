#!/bin/bash
# Run one stage of experiments/CLEANED_NOISE_PREREG.txt.
#
#     scripts/run_noise_stage.sh 1      (then 2, then 3)
#
# Resumable: after an interruption or a power cut, run the same command again.
# Every draw with a result file under noise_runs/cleaned/draws/ whose record
# carries the current code and data key is skipped; a stale one is re-run, and an
# interrupted draw is recomputed from the same seed with the same code.
# caffeinate keeps the machine awake while the stage runs. At the end it prints
# how many draws are finished per universe.
set -u -o pipefail
cd "$(dirname "$0")/.." || exit 1
case "${1:-}" in
    1|2|3) ;;
    *) echo "usage: scripts/run_noise_stage.sh 1|2|3" >&2; exit 2 ;;
esac
mkdir -p noise_runs/cleaned/logs
caffeinate -ims ./venv/bin/python results/noise_parallel.py stage "$1" \
    --out noise_runs/cleaned 2>&1 | tee -a "noise_runs/cleaned/logs/stage$1.log"
