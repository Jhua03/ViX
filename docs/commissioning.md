# Commissioning: first connection to first controlled move

This procedure assumes the ViX motor/feedback wiring and base motor configuration are already correct. It covers the host/X3 + Pico/X4 controller in this repository.

## 1. Power OFF checks

Before applying drive power:

- compare every X3 wire against [the custom cable table](serial-x3.md);
- compare every X4 wire against [`hardware/connector-pinouts.md`](../hardware/connector-pinouts.md);
- continuity-check ground and differential pair assignments;
- confirm U1/U2 are powered from **3.3 V** with local 100 nF decoupling;
- confirm GP11's NPN defaults OFF so X4-11 is released;
- confirm no 5 V source is tied to Pico GPIO;
- confirm the stage is near a safe middle-of-travel position.

## 2. Connect without motion

Connect both USB interfaces, activate the Python environment, and identify device names:

```bash
source .venv/bin/activate
ls -l /dev/ttyUSB* /dev/ttyACM*
```

Read identity/status only:

```bash
python host/vix.py info \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --axis 1
```

If this fails, do not continue. Use [Troubleshooting](troubleshooting.md).

## 3. Verify inputs physically

With the drive still not energised, read:

```bash
python host/vix.py status --axis 1
```

Operate each accessible limit, home, and E-stop input by hand and confirm the reported raw/active behavior changes exactly as intended. Also confirm the ViX fault input is healthy.

Only after this physical check should you use `--confirm-inputs`.

## 4. Apply interface configuration while remaining OFF

For a generic ViX AH installation whose motor tuning is already stored/managed separately:

```bash
python host/vix.py configure \
  --profile io-only \
  --confirm-inputs \
  --axis 1
```

For attended bench work before the final E-stop auxiliary is installed, `--bench-no-estop` exists, but the completed machine should not use it.

The command leaves the ViX OFF and the Pico disarmed.

## 5. MX80L 10 nm example only

If — and only if — the attached system is the validated MX80L/10 nm configuration documented in this repository, you may apply:

```bash
python host/vix.py configure \
  --profile mx80l-10nm \
  --confirm-inputs \
  --axis 2
```

The archived/tested machine used axis address 2. Your drive address may differ.

## 6. First one-transaction jog

The supported CLI does not leave the stage energized between separate shell commands. `jog` performs a complete configure → arm → heartbeat → enable → move → safe-disable transaction.

For the validated MX80L profile, an example 1 µm move is:

```bash
python host/vix.py jog \
  --profile mx80l-10nm \
  --um 1 \
  --confirm-inputs \
  --i-understand \
  --axis 2
```

Stay at the machine with the physical E-stop ready. For the first run, use conservative rate/acceleration and a central stage location.

On completion, the CLI reports commanded counts, pre/post Pico status, and measured encoder change, then attempts safe shutdown.

## 7. Acceptance sequence for the MX80L example

The original long-form commissioning document used ABBA-style small-move sequences. For the 10 nm/count stage:

```text
1 µm   = 100 counts
500 nm = 50 counts
400 nm = 40 counts
```

A useful validation sequence is:

```text
+100, -100, -100, +100 counts
+50,  -50,  -50,  +50 counts
+40,  -40,  -40,  +40 counts
```

Confirm that:

- no Pico latch occurs;
- no ViX drive fault occurs;
- `encoder_invalid` does not increase;
- every requested move ID completes;
- the stage settles before the next move;
- final closure is consistent with your application's requirement.

The archived v4.78 commissioning tools contain more extensive automated threshold tests. Use them only after the basic hardware/firmware path is understood and safe.

## 8. Always finish with a safe stop

You can explicitly request:

```bash
python host/vix.py disable --axis 1
```

This attempts Pico `ABORT -> ENABLE 0 -> DISARM`, followed by ViX `OFF`.
