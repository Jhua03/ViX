#!/usr/bin/env bash
set -euo pipefail

: "${PICO_SDK_PATH:?Set PICO_SDK_PATH to the Raspberry Pi Pico SDK directory}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${PIO_EXECUTABLE:-}" && -x "${PIO_EXECUTABLE}" ]]; then
  pio="$PIO_EXECUTABLE"
elif command -v pio >/dev/null 2>&1; then
  pio="$(command -v pio)"
elif [[ -x "$HOME/.platformio/penv/bin/pio" ]]; then
  pio="$HOME/.platformio/penv/bin/pio"
else
  echo "PlatformIO 'pio' not found; install platformio or set PIO_EXECUTABLE." >&2
  exit 2
fi

cd "$root"
exec "$pio" run -e pico2_official_sdk -t sdk_build
