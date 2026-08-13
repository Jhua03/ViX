# Pico 2 firmware, GPIO and protocol

## 1. GPIO mapping

The included firmware uses:

```text
GP2   STEP logic -> AM26LV31E -> X4 STEP pair
GP3   DIR logic  -> AM26LV31E -> X4 DIR pair
GP4   encoder A  <- AM26LV32E <- X4 A pair
GP5   encoder B  <- AM26LV32E <- X4 B pair
GP6   encoder Z  <- AM26LV32E <- X4 Z pair
GP7   positive limit
GP8   negative limit
GP9   home
GP10  ViX X4 fault
GP11  NPN hardware-enable control for X4 pin 11
GP12  E-stop auxiliary input
```

For physical header numbers, see [`../hardware/connector-pinouts.md`](../hardware/connector-pinouts.md).

## 2. USB serial format

The Pico uses native USB CDC, normally at `/dev/ttyACM0` on Linux. The host sends:

- ASCII text commands;
- newline termination;
- one command at a time.

The Pico answers with one-line JSON objects. The host checks the `ok` field and treats a rejected command as an error.

## 3. Core commands

| Command | Purpose |
|---|---|
| `PING` | basic communication check |
| `INFO` | firmware/system identity |
| `STATUS` | full current state |
| `CONFIG SHOW` | report configuration |
| `CONFIG <KEY> <VALUE>` | change runtime configuration |
| `ZERO` | zero the Pico encoder/command frame while disabled |
| `ARM I_UNDERSTAND` | arm after checks |
| `DISARM` | disarm |
| `ENABLE 0/1` | control the X4 hardware-enable transistor |
| `MOVE ...` | generate one STEP/DIR move |
| `ABORT` | abort motion |
| `CLEAR` | clear ordinary latches when allowed |
| `DIAG CLEAR` | clear diagnostic state |
| `HB` | watchdog heartbeat |

The archived commissioning firmware also contains a tightly bounded guarded-recovery command for specific stale ViX fault states. That is an advanced commissioning feature and is intentionally not part of the beginner workflow.

## 4. MOVE command

```text
MOVE <delta_counts> <max_rate_counts_s> <accel_counts_s2> <move_id>
```

`move_id` should be nonzero and unique. The host waits for both:

```text
motion == IDLE
move_completed_id == requested move_id
```

before treating a move as complete.

## 5. Runtime configuration used by the simple CLI

The generic Pico configuration includes:

```text
CONFIG LPOL 1
CONFIG LNPOL 0
CONFIG HPOL 1
CONFIG FPOL 1
CONFIG ENCSIGN 1
CONFIG DIRINV 0
CONFIG ESTOPREQ 1
CONFIG SOFTMIN -50000
CONFIG SOFTMAX 50000
CONFIG FERRMAX 5000
CONFIG WATCHDOG_MS 750
```

`HAS_LN`, `ESTOPREQ`, and `CONFIRM_INPUTS` are selected from CLI arguments. `ENCSIGN=1` matches the latest included firmware/wiring package; older long-form notes that said `-1` are superseded for this repository state.

## 6. Heartbeat

When armed/enabled, the host sends `HB` approximately every 100 ms. The default watchdog is 750 ms. The heartbeat runs in a separate thread so a blocked main command loop does not silently stop watchdog service.

A heartbeat is **not** a substitute for the explicit shutdown sequence. On exit or error, the host still attempts ABORT, hardware-disable, DISARM, and ViX OFF.

## 7. Useful STATUS fields

Expect fields such as:

```text
motion
armed
enabled
zeroed
latched
latch
encoder_position
command_position
following_error
encoder_invalid
limit_pos_active
limit_neg_active
home_active
fault_active
estop_safe
move_completed_id
```

Treat an unexpected increase in `encoder_invalid`, a latch, a ViX fault, an unsafe limit/E-stop, or excessive following error as a reason to stop commissioning and diagnose the hardware.
