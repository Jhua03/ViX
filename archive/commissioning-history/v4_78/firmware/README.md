# Pico 2 firmware v2.7

Identity:

```text
vix-base-pico2-v2.7
protocol 5
```

## Guarded recovery command

```text
RECOVER START <100..2000 ms> I_UNDERSTAND
RECOVER STOP
```

This command is separate from normal ARM/ENABLE. It may assert GP11 while the
ViX fault input is already active, solely so recoverable DF20/DF21 can enter a
valid enabled state and clear.

Firmware independently enforces:

- 2000 ms absolute maximum;
- 5000 counts / 50 µm raw displacement;
- 750 ms host heartbeat;
- E-stop and limits;
- invalid quadrature transitions;
- timeout latch;
- fault-clear then fault-reassert shutdown.

The normal `ENABLE 1` path still refuses an active fault or safety latch.

## Build and upload

From the package root:

```bash
source ~/Downloads/vix250ah_pico2_controller_v1/.venv/bin/activate
export PICO_SDK_PATH="$HOME/pico-sdk"
export PICOTOOL_EXECUTABLE="$HOME/.local/picotool-2.3.0/bin/picotool"
bash scripts/build_and_verify_firmware.sh
```

Expected output:

```text
firmware/build-pio/vix_base_pico2_controller.uf2
```

Then put the Pico 2 in BOOTSEL mode and run:

```bash
bash scripts/upload_firmware_bootsel.sh
```
