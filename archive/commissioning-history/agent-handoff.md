# Agent Handoff — Raspberry Pi 5 GUI control for ViX500AE + Pico 2 + MX80L stage

**Date:** 2026-07-31  
**Current working goal:** use this axis for lithography with about **1 µm positioning accuracy**. Do **not** chase 100 nm as the production requirement right now.

---

## 1. System summary

This axis uses two serial links from the Raspberry Pi 5 GUI host:

1. **Pico 2 supervisory / pulse generator link**
   - Typical device: `/dev/ttyACM0`
   - Baud: `115200`
   - Format: `8N1`, newline-terminated ASCII commands
   - Replies: one-line JSON objects
   - Responsibilities:
     - Generate STEP/DIR pulses to ViX X4.
     - Read encoder A/B/Z through Pico-side receiver.
     - Monitor X5 limit/home inputs and ViX fault input.
     - Own the hardware-enable gate to X4 pin 11.
     - Enforce following-error and watchdog latches.

2. **ViX500AE/Base RS-232 link through USB-to-DB9**
   - Typical device: `/dev/ttyUSB0`
   - Baud: `9600`
   - Format: `8N1`, carriage-return terminated commands
   - Expected axis address: `2`
   - Responsibilities:
     - Put the drive in step/direction servo mode.
     - Set volatile gains/current clamp.
     - Send `ON` / `OFF`.
     - Read status/fault registers.

The GUI must talk to **both**. The Pico does not replace the ViX serial link. The ViX serial link configures and energizes the servo drive; the Pico safely issues the pulse commands.

---

## 2. Current proven motion status

Encoder scale:

```text
100000 counts/mm
1 count = 10 nm
10 counts = 100 nm
40 counts = 400 nm
50 counts = 500 nm
100 counts = 1 µm
```

Latest tuning result:

```text
Best production-ish candidate:
  damped_gi0p2_gp2_gv1p5_cl2

ViX gains/current:
  GF0 GI0.2 GP2 GV1.5 FT0
  CL=2
  PC=100
  IM=1
  IW=1000
```

Practical commanded-motion threshold from v4.77/v4.78:

```text
1 µm command:   good
500 nm command: strong
400 nm command: usable
350 nm command: borderline
300 nm command: partial
200 nm command: partial / not production
100 nm command: not working reliably
```

Production recommendation for lithography GUI:

```text
Use 1 µm grid/move as the normal guaranteed positioning increment.
Allow 500 nm fine nudges.
Allow 400 nm expert/fine-adjust nudges.
Do not advertise 100 nm as a working production step.
```

Important nuance: a command of `40 counts` is a **commanded 400 nm step**, but actual median response in testing was often around 300–400 nm. The GUI must log actual encoder response after every move. Do not assume commanded count equals achieved displacement at sub-micron scale.

---

## 3. Safety rules for the GUI agent

Do not bypass these.

1. **Never run the old Stage 6 workflow.** It re-enables/re-zeros in ways that are not valid for this stage.
2. **Never send `SV`, `MOTOR`, `SETUPFB`, or `RFS` from the GUI.** Keep all production GUI changes volatile.
3. **Never command ViX internal moves for lithography stepping.** Motion must go through Pico `MOVE ...` so the Pico can enforce latches and monitor the encoder/fault/limit inputs.
4. **Always drop Pico hardware enable before ViX `OFF` during shutdown.**
5. **Any Pico latch, ViX fault, encoder-invalid increment, or operator stop must stop motion and leave the drive OFF.**
6. **In final machine mode, require the real E-stop auxiliary input.** `ESTOPREQ 0` is only for attended bench testing.
7. The ViX manual warns that unexpected motion can occur during controller development. The GUI should treat enable and gain-apply as hazardous states and require operator acknowledgement before first energizing.

---

## 4. ViX serial protocol notes

Open the ViX USB-to-DB9 port as:

```python
serial.Serial('/dev/ttyUSB0', baudrate=9600, bytesize=8, parity='N', stopbits=1,
              timeout=0.03, write_timeout=1.0, xonxoff=False, rtscts=False, dsrdtr=False)
```

Commands are ASCII with `\r`. Prefix all normal commands with the axis address `2`.

Examples:

```text
2R(RV)      -> expect software revision, e.g. *2.4bD
2STATUS     -> product/status text
2R(DF)      -> drive fault word
2R(UF)      -> user fault word; full UF read clears UF
2OFF        -> de-energize drive
2ON         -> energize drive, but only after Pico ENABLE 1 is active
```

Expected identity:

```text
Product: ViX500AE-Base
Axis: 2
Firmware: REV 2.4bD
Motor resolution: 1300000 counts/electrical pitch
Stage scale used by host/Pico: 100000 counts/mm
```

---

## 5. Pico serial protocol notes

Open the Pico 2 port as:

```python
serial.Serial('/dev/ttyACM0', baudrate=115200, bytesize=8, parity='N', stopbits=1,
              timeout=0.05, write_timeout=1.0, xonxoff=False, rtscts=False, dsrdtr=False)
```

Commands are newline terminated: `COMMAND\n`. Replies are JSON lines.

Core commands:

```text
PING
INFO
STATUS
CONFIG SHOW
CONFIG <KEY> <VALUE>
ZERO
ARM I_UNDERSTAND
DISARM
ENABLE 0
ENABLE 1
MOVE <delta_counts> <max_rate_counts_s> <accel_counts_s2> <move_id>
ABORT
CLEAR
DIAG CLEAR
HB
```

The GUI must send `HB` about every `100 ms` while the Pico is armed/enabled. The current watchdog setting used during commissioning was `750 ms`.

Useful `STATUS` fields:

```text
motion                  IDLE / MOVING / ABORTED
armed                   true/false
enabled                 true/false
zeroed                  true/false
latched                 true/false
latch                   NONE / USER_ABORT / LIMIT_POS / VIX_FAULT / FOLLOWING_ERROR / ...
encoder_position        Pico encoder position relative to ZERO, counts
command_position        Pico accumulated command position, counts
following_error         command_position - encoder_position, counts
encoder_invalid         invalid quadrature transition counter
limit_pos_active        debounced +limit
limit_neg_active        debounced -limit; currently ignored by policy via HAS_LN=0
home_active             debounced home input
fault_active            ViX fault input as seen by Pico
estop_safe              E-stop auxiliary status
```

---

## 6. Required volatile ViX setup for this axis

Before energizing for GUI-controlled stepping, force the ViX setup. Do not save it.

Send over ViX serial:

```text
2OFF
2MP
2W(ES,0)
2W(EI,0)
2W(EO,2)
2W(CL,2)
2W(PC,100)
2W(TL,13000)
2W(IM,1)
2W(IW,1000)
2GAINS(0,0.2,2,1.5,0)
```

Meaning:

```text
MP      mode position, external step/direction servo mode
ES=0    X4 enable is active-low; Pico controls hardware enable line
EI=0    X4 input is STEP/DIR
EO=2    X4 encoder output mode is A/B
CL=2    current clamp; best result from threshold tests
PC=100  peak current scale kept conservative
TL=13000 tracking limit for guarded tests
IM=1    integral only inside window
IW=1000 integral window counts
GAINS   best practical sub-micron candidate found so far
```

Read back after setup:

```text
2R(M)   -> *MP
2R(ES)  -> *0
2R(EI)  -> *0
2R(EO)  -> *2
2R(CL)  -> *2
2R(PC)  -> *100
2R(IW)  -> *1000
2R(GI)  -> *0.2
2R(GP)  -> *2
2R(GV)  -> *1.5
```

---

## 7. Required Pico setup for this axis

Before arming, configure Pico policy while disabled/disarmed.

For current attended bench behavior:

```text
ABORT
ENABLE 0
DISARM
CONFIG LPOL 1
CONFIG LNPOL 0
CONFIG HPOL 1
CONFIG FPOL 1
CONFIG HAS_LN 0
CONFIG ENCSIGN -1
CONFIG DIRINV 0
CONFIG ESTOPREQ 0
CONFIG SOFTMIN -50000
CONFIG SOFTMAX 50000
CONFIG FERRMAX 5000
CONFIG WATCHDOG_MS 750
CONFIG CONFIRM_INPUTS 1
CONFIG SHOW
CLEAR
DIAG CLEAR
ZERO
ARM I_UNDERSTAND
```

For final machine GUI with working E-stop auxiliary input, use:

```text
CONFIG ESTOPREQ 1
```

instead of `ESTOPREQ 0`.

Expected inactive input policy:

```text
Limit+ raw inactive: 0
Home raw inactive: 0
ViX fault raw healthy: 0
Limit- is ignored by current policy: HAS_LN=0
```

After `ARM I_UNDERSTAND`, start sending heartbeat:

```text
HB every 100 ms
```

---

## 8. Energizing sequence

The ViX requires both the Pico-controlled X4 hardware enable and the serial `ON` command.

Use this order:

```text
# Pico already configured, ZEROed, armed, heartbeat running
Pico: ENABLE 1
wait 50 ms
ViX:  2ON
wait until ViX reports energized / no DF
wait 2 to 5 s for enable kick and gain pull-in to settle
read Pico STATUS and define the GUI's local logical reference from current encoder_position
```

Do not send a Pico `ZERO` while enabled. Pico firmware rejects zeroing while enabled/armed. For GUI local coordinates, maintain a software-level offset from the `encoder_position` read after settle.

---

## 9. Shutdown / safe stop sequence

Use this for normal stop, error stop, and GUI exit:

```text
Pico: ABORT
Pico: ENABLE 0
Pico: DISARM
ViX:  2OFF
Pico: STATUS
ViX:  2R(DF)
```

If the Pico reports a hardware/safety latch, do not auto-resume. Surface the latch to the operator, save a log, and require explicit acknowledgement before `CLEAR`/`DIAG CLEAR`/re-arm.

---

## 10. Motion command mapping

Use counts as the only low-level unit.

Formula:

```text
delta_counts = round(delta_nm / 10)
delta_nm = delta_counts * 10
```

Step table:

| Requested GUI move | Pico delta_counts | Comment |
|---:|---:|---|
| 100 nm | 10 | Experimental only; not production reliable on this stage |
| 150 nm | 15 | Experimental only |
| 200 nm | 20 | Partial response only |
| 300 nm | 30 | Partial / maybe useful for future testing |
| 350 nm | 35 | Borderline |
| 400 nm | 40 | Usable fine nudge |
| 500 nm | 50 | Strong fine nudge |
| 1 µm | 100 | Recommended normal lithography fine step |
| 10 µm | 1000 | Larger alignment nudge; use slower rate first |
| 100 µm | 10000 | Coarse nudge only within soft limits |
| 1 mm | 100000 | Outside current +/-0.5 mm soft window unless GUI expands SOFTMIN/SOFTMAX intentionally |

Recommended initial sub-micron command parameters:

```text
max_rate_counts_s = 100
accel_counts_s2   = 5000
```

Example Pico commands:

```text
# +400 nm commanded fine nudge
MOVE 40 100 5000 1001

# -400 nm commanded fine nudge
MOVE -40 100 5000 1002

# +500 nm commanded fine nudge
MOVE 50 100 5000 1003

# -500 nm commanded fine nudge
MOVE -50 100 5000 1004

# +1 µm commanded move
MOVE 100 100 5000 1005

# -1 µm commanded move
MOVE -100 100 5000 1006
```

`move_id` must be fresh and nonzero. Increment it monotonically in the GUI.

---

## 11. GUI motion transaction

Each GUI move should be a transaction:

1. Read Pico `STATUS`.
2. Reject the command if any of these are true:
   - `latched == true`
   - `motion == MOVING`
   - `armed == false`
   - `enabled == false`
   - `fault_active == true`
   - `limit_pos_active == true` and requested delta is positive
   - `limit_neg_active == true` and requested delta is negative, once a real Limit- policy exists
   - `abs(following_error) > 5000`
3. Send `MOVE <delta> <rate> <accel> <fresh_move_id>`.
4. Poll `STATUS` every 50 ms until:
   - `motion == IDLE`, and
   - `move_completed_id == move_id`.
5. Continue polling for settle. For production 1 µm usage, use a practical gate such as:
   - last 0.5 to 1.0 s encoder span <= 20 counts, and
   - `abs(following_error)` not increasing.
6. Log commanded and measured motion:
   - `before_encoder_position`
   - `after_encoder_position`
   - `actual_response_counts = after - before`
   - `actual_response_nm = actual_response_counts * 10`
   - `commanded_counts`
   - `commanded_nm`
   - `following_error`
   - `latched/fault/limit state`

Do not use the ViX `IP` flag as the only settle proof. The Pico encoder-side readback is the main truth for this GUI.

---

## 12. Suggested GUI controls

Expose these normal controls:

```text
Enable axis
Disable axis
Abort / E-stop style stop
Read status
Jog +1 µm / -1 µm
Jog +500 nm / -500 nm
Jog +400 nm / -400 nm
Jog +10 µm / -10 µm, if soft window allows
Set local GUI zero offset, software-only
Export motion log CSV
```

Hide these behind an expert/developer toggle:

```text
100 nm command
150 nm command
200 nm command
Gain/current override
Pico CONFIG override
ViX raw command terminal
```

Do not expose raw ViX `SV`, `MOTOR`, `SETUPFB`, `RFS`, or internal `G` move commands in the normal GUI.

---

## 13. Current best production recipe

For lithography where the real requirement is about 1 µm:

```text
ViX setup:
  MP, EI=0, EO=2, ES=0
  CL=2, PC=100, TL=13000
  IM=1, IW=1000
  GAINS(0,0.2,2,1.5,0)

Pico setup:
  ENCSIGN=-1
  DIRINV=0
  FERRMAX=5000
  WATCHDOG_MS=750
  soft window initially +/-50000 counts around startup local zero

Normal move unit:
  100 counts = 1 µm

Fine nudge:
  50 counts = 500 nm
  40 counts = 400 nm

Do not depend on:
  10 counts = 100 nm
```

---

## 14. Minimal Python-style pseudocode for the GUI agent

```python
def pico_cmd(port, text, timeout=2.0):
    port.write((text + "\n").encode())
    port.flush()
    # Read JSON lines until a dict with key "ok" appears.
    # Raise on ok:false.
    return json_obj


def vix_cmd(port, axis, body, timeout=2.0):
    port.write((f"{axis}{body}\r").encode("ascii"))
    port.flush()
    # Read until quiet. Parse '*' payload lines for reports.
    return raw_text


def setup_vix_for_gui(vix):
    for body in [
        "OFF",
        "MP",
        "W(ES,0)",
        "W(EI,0)",
        "W(EO,2)",
        "W(CL,2)",
        "W(PC,100)",
        "W(TL,13000)",
        "W(IM,1)",
        "W(IW,1000)",
        "GAINS(0,0.2,2,1.5,0)",
    ]:
        vix_cmd(vix, 2, body)


def setup_pico_for_gui(pico, bench_no_estop=True):
    for cmd in ["ABORT", "ENABLE 0", "DISARM"]:
        pico_cmd(pico, cmd)
    config = {
        "LPOL": 1,
        "LNPOL": 0,
        "HPOL": 1,
        "FPOL": 1,
        "HAS_LN": 0,
        "ENCSIGN": -1,
        "DIRINV": 0,
        "ESTOPREQ": 0 if bench_no_estop else 1,
        "SOFTMIN": -50000,
        "SOFTMAX": 50000,
        "FERRMAX": 5000,
        "WATCHDOG_MS": 750,
        "CONFIRM_INPUTS": 1,
    }
    for k, v in config.items():
        pico_cmd(pico, f"CONFIG {k} {v}")
    pico_cmd(pico, "CLEAR")
    pico_cmd(pico, "DIAG CLEAR")
    pico_cmd(pico, "ZERO")
    pico_cmd(pico, "ARM I_UNDERSTAND")


def enable_axis(pico, vix):
    start_heartbeat_thread(pico, period_s=0.1)
    pico_cmd(pico, "ENABLE 1")
    time.sleep(0.05)
    vix_cmd(vix, 2, "ON")
    time.sleep(2.0)  # allow enable kick/gain pull-in to settle
    return pico_cmd(pico, "STATUS")


def move_counts(pico, delta_counts, move_id, rate=100, accel=5000):
    before = pico_cmd(pico, "STATUS")
    assert before["motion"] == "IDLE"
    assert before["armed"] and before["enabled"]
    assert not before["latched"]
    pico_cmd(pico, f"MOVE {delta_counts} {rate} {accel} {move_id}")
    while True:
        st = pico_cmd(pico, "STATUS")
        if st["latched"]:
            raise RuntimeError(f"Pico latch: {st}")
        if st["motion"] == "IDLE" and st["move_completed_id"] == move_id:
            break
        time.sleep(0.05)
    after = pico_cmd(pico, "STATUS")
    response_counts = after["encoder_position"] - before["encoder_position"]
    return {
        "commanded_counts": delta_counts,
        "commanded_nm": delta_counts * 10,
        "response_counts": response_counts,
        "response_nm": response_counts * 10,
        "before": before,
        "after": after,
    }


def disable_axis(pico, vix):
    try:
        pico_cmd(pico, "ABORT")
    finally:
        pico_cmd(pico, "ENABLE 0")
        pico_cmd(pico, "DISARM")
        vix_cmd(vix, 2, "OFF")
        stop_heartbeat_thread()
```

---

## 15. What not to misinterpret

- A `MOVE 40 ...` command means **40 commanded counts = 400 commanded nm**. It does not guarantee the stage physically moved exactly 400 nm. Use encoder feedback.
- The current best threshold is about **400–500 nm commanded motion**, not 100 nm.
- Higher current did not improve threshold in the latest two v4.78 runs. Default back to `CL=2`.
- 80 V bus voltage is not the current suspected limiter for sub-micron moves. Small-signal breakaway/stiction/deadband is the likely limiter.
- The GUI should be built around robust 1 µm and 500/400 nm movements, not 100 nm.

---

## 16. Suggested acceptance test for GUI integration

Before using the GUI for lithography, run this small test from the GUI at the current center position:

```text
1. Enable axis.
2. Wait 2 s.
3. Log baseline encoder_position for 2 s.
4. Command +100 counts, -100 counts, -100 counts, +100 counts.
5. Command +50 counts, -50 counts, -50 counts, +50 counts.
6. Command +40 counts, -40 counts, -40 counts, +40 counts.
7. Confirm no Pico latch, no ViX DF, no encoder-invalid increase.
8. Confirm closure after each ABBA block is within about 20 counts for 1 µm/500 nm and about 30 counts for 400 nm.
9. Disable axis.
10. Save CSV log.
```

If that passes, the GUI is good enough to proceed with 1 µm-class lithography integration on this axis.
