
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${PICO_SDK_PATH:=$HOME/pico-sdk}"
: "${PICOTOOL_EXECUTABLE:=$HOME/.local/picotool-2.3.0/bin/picotool}"
export PICO_SDK_PATH PICOTOOL_EXECUTABLE
unset CMAKE_PREFIX_PATH

echo "Put the Pico 2 in BOOTSEL mode and wait for RP2350/RPI-RP2 to mount."
cd "$ROOT/firmware"
exec "$HOME/.platformio/penv/bin/pio" run \
  -e pico2_official_sdk \
  -t sdk_upload
