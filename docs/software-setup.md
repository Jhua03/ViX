# Software setup

## 1. Host computer requirements

The host does not have to be a Raspberry Pi. It needs:

- Python 3;
- one USB port for the Pico 2;
- one USB port for the USB-to-RS232 adapter connected to ViX X3;
- permission to open the two serial devices.

The small supported CLI uses **pyserial**.

## 2. Install the Python environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` currently contains:

```text
pyserial>=3.5
```

On Linux, if Python reports `Permission denied` for `/dev/ttyUSB0` or `/dev/ttyACM0`, add your user to the distribution's serial-device group (commonly `dialout` or `uucp`) and log in again, or create an appropriate udev rule.

## 3. Confirm both serial devices

With the Pico 2 and USB-RS232 adapter attached:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
```

Then try the non-motion identity command:

```bash
python host/vix.py info \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --axis 1
```

If your ViX uses a different software axis address, change `--axis`.

## 4. Build the Pico 2 firmware

The firmware uses the official Raspberry Pi Pico SDK and targets **Pico 2 only**.

A typical Linux build requires CMake, an Arm embedded GCC toolchain, and the Pico SDK. Point `PICO_SDK_PATH` at your SDK checkout, then from the repository root run:

```bash
export PICO_SDK_PATH="$HOME/pico-sdk"
bash scripts/build_and_verify_firmware.sh
```

The expected UF2 is:

```text
firmware/build-pio/vix_base_pico2_controller.uf2
```

For details, see [`../firmware/README.md`](../firmware/README.md) and [`../firmware/PLATFORMIO.md`](../firmware/PLATFORMIO.md).

## 5. Flash the Pico 2

For the first flash:

1. disconnect the stage/drive enable path or otherwise make motion impossible;
2. hold **BOOTSEL** while connecting the Pico 2 over USB;
3. copy the UF2 to the Pico mass-storage device, or use:

```bash
bash scripts/upload_firmware_bootsel.sh
```

After flashing, reconnect the Pico's USB CDC serial port and run `python host/vix.py info ...` again.

## 6. Use the CLI

Read [`../host/README.md`](../host/README.md) before using commands that configure or move hardware. The normal progression is:

```text
info -> status -> configure -> commissioning checks -> one jog -> disable
```

Configuration is intentionally **volatile**; the supported utility does not issue `SV` to save experimental settings into the drive.
