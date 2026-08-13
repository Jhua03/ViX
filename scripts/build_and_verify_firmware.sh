#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find_pio() {
  if [[ -n "${PIO_EXECUTABLE:-}" && -x "${PIO_EXECUTABLE}" ]]; then
    printf '%s\n' "$PIO_EXECUTABLE"; return
  fi
  if command -v pio >/dev/null 2>&1; then
    command -v pio; return
  fi
  if [[ -x "$HOME/.platformio/penv/bin/pio" ]]; then
    printf '%s\n' "$HOME/.platformio/penv/bin/pio"; return
  fi
  echo "PlatformIO 'pio' not found. Activate a venv with 'pip install platformio' or set PIO_EXECUTABLE." >&2
  exit 2
}

: "${PICO_SDK_PATH:=$HOME/pico-sdk}"
: "${PICOTOOL_EXECUTABLE:=$HOME/.local/picotool-2.3.0/bin/picotool}"
export PICO_SDK_PATH PICOTOOL_EXECUTABLE
unset CMAKE_PREFIX_PATH
PIO="$(find_pio)"

cd "$ROOT"
bash scripts/run_offline_checks.sh

cd "$ROOT/firmware"
"$PIO" run -e pico2_official_sdk -t sdk_build

test -s build-pio/vix_base_pico2_controller.elf
test -s build-pio/vix_base_pico2_controller.uf2
grep -q 'vix-base-pico2-v2.7' src/board_config.h
strings build-pio/vix_base_pico2_controller.elf | grep -q 'vix-base-pico2-v2.7'
ls -lh build-pio/vix_base_pico2_controller.elf build-pio/vix_base_pico2_controller.uf2

echo
echo "Firmware build and no-op verification PASS."
echo "UF2: $ROOT/firmware/build-pio/vix_base_pico2_controller.uf2"
