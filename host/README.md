# `vix.py` host utility

`vix.py` is the small, supported starting point for a ViX250AH/ViX500AH + Pico 2 installation. It is intentionally much simpler than the archived threshold-refinement runner.

## Install

From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Architecture

The process opens two independent serial links:

```text
--vix-port   USB-to-RS232 -> custom DB9 cable -> ViX X3
--pico-port  USB -> Pico 2
```

Motion is generated only by Pico STEP/DIR over X4. The script does not use ViX internal motion commands.

## Commands

### Identity

```bash
python host/vix.py info --vix-port /dev/ttyUSB0 --pico-port /dev/ttyACM0 --axis 1
```

### Status

```bash
python host/vix.py status --axis 1
```

### Apply volatile I/O configuration

```bash
python host/vix.py configure \
  --profile io-only \
  --confirm-inputs \
  --axis 1
```

The command leaves the drive OFF and Pico disarmed.

### MX80L 10 nm example configuration

```bash
python host/vix.py configure \
  --profile mx80l-10nm \
  --confirm-inputs \
  --axis 2
```

Only use this profile on a system you have validated for the included MX80L parameters.

### One complete jog transaction

```bash
python host/vix.py jog \
  --um 1 \
  --confirm-inputs \
  --i-understand \
  --axis 2
```

`jog` currently requires the `mx80l-10nm` profile. It performs the full enable/move/safe-disable transaction in one process so the watchdog heartbeat remains alive and shutdown is deterministic.

### Safe disable

```bash
python host/vix.py disable --axis 1
```

## Bench E-stop bypass

`--bench-no-estop` exists only for attended commissioning before a final E-stop auxiliary input is available. Do not use it for a completed machine.

## Soft limits and negative limit

Defaults are:

```text
--soft-min -50000
--soft-max  50000
```

Add `--has-negative-limit` only after a real negative-limit input has been physically tested. The archived MX80L machine had no working negative-limit input and used `HAS_LN=0`.

## What this utility intentionally does not do

It does not:

- save tuning/configuration with `SV`;
- change motor/feedback setup with `MOTOR`, `SETUPFB`, or `RFS`;
- perform ViX internal motion;
- run the advanced guarded stale-fault recovery workflow;
- claim that one motor's gains are safe for another motor.

For advanced historical characterization tools, see `archive/commissioning-history/v4_78/`.
