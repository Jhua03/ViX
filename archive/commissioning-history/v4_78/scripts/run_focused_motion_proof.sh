#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 host/vix_focused_motion_proof.py \
  --vix-port "${VIX_PORT:-/dev/ttyUSB0}" \
  --pico-port "${PICO_PORT:-/dev/ttyACM0}" \
  --bench-no-estop "$@"
