#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/host/vix_limit_input_isolation_probe.py" \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
