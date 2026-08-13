#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/host/vix100nm_commission.py" \
  --stage 6 \
  --recover-stage4-from-evidence /home/eric/vix100nm_runs/20260730_212104_451345_coarse_ladder.zip \
  --recover-stage5-from-evidence /home/eric/vix100nm_runs/20260730_230245_498415_fine_ladder.zip \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
