# Safety and shutdown policy

This repository controls a real servo drive. Software safety is supplementary to physical guarding, correct power wiring, a real emergency-stop circuit, and the ViX's own protections.

## Non-negotiable software rules

1. Keep the ViX **OFF** while changing configuration.
2. Do not use ViX internal motion commands for this controller; motion goes through Pico `MOVE` and X4 STEP/DIR.
3. Do not issue `SV`, `MOTOR`, `SETUPFB`, or `RFS` from the normal host workflow.
4. The Pico hardware-enable path must be active **before** sending ViX `ON`.
5. Remove Pico hardware enable **before** sending ViX `OFF` during shutdown.
6. Abort on any safety latch, ViX fault, active movement limit, invalid encoder transition increase, E-stop, communication failure, or operator stop.
7. Do not automatically resume after a safety latch. Require operator inspection/acknowledgement.
8. Use a real E-stop auxiliary input in the completed machine.
9. Treat gain/current changes and initial energisation as hazardous operations.

## Normal enable sequence

A safe commissioning transaction follows this order:

```text
1. Open Pico and ViX serial ports.
2. ViX OFF.
3. Apply X4 configuration.
4. Read back ViX configuration.
5. Configure Pico while disabled/disarmed.
6. Clear permitted latches/diagnostics.
7. ZERO while disabled.
8. ARM.
9. Start heartbeat.
10. Pico ENABLE 1.
11. Wait briefly (~50 ms).
12. ViX ON.
13. Allow servo pull-in/settling.
14. Re-read status before commanding motion.
```

Do not send `ZERO` after the Pico is armed/enabled; use a software coordinate offset if you need a local GUI zero after energisation.

## Shutdown / fault sequence

The software attempts every step independently so one communication failure does not prevent later stop actions:

```text
Pico ABORT
Pico ENABLE 0
Pico DISARM
ViX OFF
stop heartbeat
```

After a fault, record Pico status and the ViX fault word before clearing diagnostic evidence.

## E-stop policy

For a completed machine, run with E-stop supervision required. Bench bypass (`--bench-no-estop`) exists only for attended commissioning where the final auxiliary contact is not yet wired. Do not make bench bypass the normal production configuration.

The included example assumes a normally-closed E-stop auxiliary loop whose broken/pressed state becomes unsafe. Physically verify your implementation before trusting it.

## Limits and soft limits

Hard limit inputs protect travel only if they are physically installed, wired, and configured with the correct polarity. Software soft limits add another layer but are relative to the coordinate origin established by the controller.

The included generic default `-50000..+50000` counts is intentionally a small commissioning window. On the MX80L 10 nm example that equals ±0.5 mm. For another encoder scale it represents a different physical distance.

## First energisation

Do it near the center of travel with:

- the mechanism mechanically clear;
- a physical E-stop within immediate reach;
- conservative current/tuning already established for the attached motor;
- verified encoder direction and limit polarity;
- no person or fragile equipment in the path.

If the stage pulls hard in one direction, chatters, runs away, or the encoder sign is wrong, disable immediately and diagnose before trying again.
