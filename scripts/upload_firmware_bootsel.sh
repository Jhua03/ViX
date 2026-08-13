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

echo "Put the Pico 2 in BOOTSEL mode and wait for RP2350/RPI-RP2 to mount."
cd "$ROOT/firmware"
exec "$PIO" run -e pico2_official_sdk -t sdk_upload
