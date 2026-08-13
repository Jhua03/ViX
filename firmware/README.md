# Pico 2 firmware

Firmware identity:

```text
vix-base-pico2-v2.7
protocol 5
```

This firmware is for **Raspberry Pi Pico 2 only**. It generates X4 STEP/DIR,
counts the ViX encoder copy, supervises limits/fault/E-stop/following error, and
controls the X4 hardware-energise transistor.

The authoritative GPIO mapping is in `src/board_config.h` and is summarized in
[`../hardware/connector-pinouts.md`](../hardware/connector-pinouts.md).

## Build

From the repository root, create/activate a Python environment and install
PlatformIO if you do not already have it:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip platformio
```

Install the native build prerequisites for your OS (CMake, Ninja and an Arm
embedded GCC toolchain), install/clone the official Raspberry Pi Pico SDK, then:

```bash
export PICO_SDK_PATH="$HOME/pico-sdk"
bash scripts/build_and_verify_firmware.sh
```

The expected output is:

```text
firmware/build-pio/vix_base_pico2_controller.uf2
```

The PlatformIO project is only a task/front-end; the actual firmware build is
performed by the official Pico SDK CMake/Ninja project.

## Upload

For the first upload, hold **BOOTSEL** while plugging the Pico 2 into USB, then
run:

```bash
bash scripts/upload_firmware_bootsel.sh
```

You can also copy the UF2 manually to the Pico 2 mass-storage device.

## Guarded recovery is advanced commissioning functionality

The firmware contains:

```text
RECOVER START <100..2000 ms> I_UNDERSTAND
RECOVER STOP
```

This path was developed for tightly bounded recovery from particular stale ViX
fault states. It is separate from normal `ARM`/`ENABLE` and is **not** part of
the beginner commissioning workflow in the main guide.

Firmware independently bounds that recovery path with timeout, displacement,
heartbeat, E-stop/limit, encoder-validity, and fault-state checks. The normal
`ENABLE 1` path still refuses an active fault or safety latch.

For the full development rationale and tests, see
[`../archive/commissioning-history/v4_78/`](../archive/commissioning-history/v4_78/).
