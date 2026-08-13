#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FINE_EVIDENCE="${1:-/home/eric/vix100nm_runs/20260730_230245_498415_fine_ladder.zip}"
python3 "$ROOT/host/vix100nm_commission.py" \
  --stage 6 \
  --recover-stage5-from-evidence "$FINE_EVIDENCE" \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
