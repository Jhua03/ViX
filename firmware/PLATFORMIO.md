# PlatformIO / official Pico SDK workflow

PlatformIO is used only as a convenient command/task front-end. The firmware is
configured and compiled by the official Raspberry Pi Pico SDK for
`PICO_BOARD=pico2`.

## Requirements

Install:

- Python 3 and PlatformIO;
- CMake;
- Ninja;
- an Arm embedded GCC toolchain;
- the Raspberry Pi Pico SDK.

Example Python setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip platformio
export PICO_SDK_PATH="$HOME/pico-sdk"
```

On Fedora, the native packages are typically along the lines of CMake, Ninja,
`arm-none-eabi-gcc*`, and newlib; exact package names vary by Fedora release.

## Command-line build

From repository root:

```bash
bash scripts/build_and_verify_firmware.sh
```

The script discovers `pio` from `PIO_EXECUTABLE`, the active `PATH`, or the
usual `~/.platformio/penv/bin/pio` location.

The resulting UF2 is:

```text
firmware/build-pio/vix_base_pico2_controller.uf2
```

## VS Code

Open the **repository root** or `firmware/` in VS Code with the PlatformIO
extension. The environment is named:

```text
pico2_official_sdk
```

The custom tasks are:

```text
SDK Build
SDK Upload
```

For the first upload, put the Pico 2 in BOOTSEL mode. Later upload behavior can
use picotool when the host permissions are configured.
