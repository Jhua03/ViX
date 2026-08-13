
#!/usr/bin/env bash
set -euo pipefail

: "${PICO_SDK_PATH:?Set PICO_SDK_PATH to the Raspberry Pi Pico SDK directory}"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pio="${PIO_EXECUTABLE:-$HOME/.platformio/penv/bin/pio}"

[[ -x "$pio" ]] || {
  echo "PlatformIO executable not found: $pio" >&2
  exit 1
}

cd "$root"
exec "$pio" run -e pico2_official_sdk -t sdk_build
