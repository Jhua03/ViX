#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 host/vix100nm_commission.py \
  --stage 3 \
  --stage3-fast-resume \
  --recover-stage2-from-evidence /home/eric/vix100nm_runs/20260729_230445_164053_gain_hold_ladder.zip \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
