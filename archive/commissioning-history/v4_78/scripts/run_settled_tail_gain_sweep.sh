#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 host/vix_settled_tail_gain_sweep.py \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
