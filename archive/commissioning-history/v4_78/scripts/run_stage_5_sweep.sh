#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE="${1:-/home/eric/vix100nm_runs/20260730_212104_451345_coarse_ladder.zip}"
python3 "$ROOT/host/vix100nm_commission.py" \
  --stage 5 \
  --recover-stage4-from-evidence "$EVIDENCE" \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
