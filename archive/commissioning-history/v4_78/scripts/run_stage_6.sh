#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/host/vix100nm_commission.py" --stage 6   --vix-port /dev/ttyUSB0 --pico-port /dev/ttyACM0 "$@"
