#!/bin/bash
# Stages 1 and 2 of experiments/DRAWDOWN_STOP_PREREG.txt: fit 20 seeds per judged
# universe and store each seed's scores, midcap50 first.
#
#     scripts/run_seed_band_fit.sh
#
# Resumable: run the same command again after an interruption. A universe already
# stored with a passed reproduction check and unchanged inputs is skipped, so only
# the unfinished universe is repeated. A failed check stops the run. caffeinate
# keeps the machine awake while it runs.
set -u -o pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p noise_runs/seed_band
caffeinate -ims ./venv/bin/python results/seed_band_fit.py fit "$@" 2>&1 \
    | tee -a noise_runs/seed_band/fit.log
