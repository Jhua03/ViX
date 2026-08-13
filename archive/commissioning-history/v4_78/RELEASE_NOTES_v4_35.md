# v4.35 release notes

## Intent

Harden Stage 3 against host-side Pico ZERO ordering bugs exposed by the v4.34 direction-scale run.

## Changes

- Adds `safe_pico_zero()`, a single transaction for every host-side Pico zero:
  1. abort only if motion is active,
  2. force `ENABLE 0`,
  3. force `DISARM`,
  4. clear only host-generated `USER_ABORT`,
  5. then issue `ZERO` and verify it stuck.
- Replaces all host-side direct `ZERO` calls with `safe_pico_zero()` in guarded recovery, local-zero transactions, energize retry cleanup, and encoder-invalid retry cleanup.
- Preserves Stage 2 when migrating from v4.32-v4.34 policy state, but still invalidates Stage 3+.
- Adds an offline regression for the exact firmware rule: Pico rejects `ZERO` unless disabled and disarmed.

## Safety behavior

This does not bypass hardware latches. Repeated `ENCODER_INVALID`, active limit, fault input, unsafe E-stop state, ViX DF, runaway/following-error, or a Pico latch other than host-generated `USER_ABORT` still stops the test.
