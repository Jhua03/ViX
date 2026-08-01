# v4.68 – X5 limit/home consecutive-sample safety guard

Purpose: stop single-sample phantom X5 limit/home glitches from immediately
latching the Pico while preserving real hard-limit protection.

Changes:

- Firmware bumped to `vix-base-pico2-v2.7`, protocol 5.
- Added a fixed 5-consecutive-sample debounce guard for the X5 safety inputs:
  `LIMIT_POS`, `LIMIT_NEG`, and `HOME`.
- Sampling is performed in the existing 10 kHz firmware refresh loop, so five
  consecutive samples is approximately 0.5 ms.
- Inactive clears immediately. A real active limit still latches quickly, but a
  one-sample EMI spike does not count as active.
- `STATUS`, `RAW`, `INFO`, and `CONFIG SHOW` now report the debounce count/state:
  `x5_debounce_samples`, raw-active booleans, and active streak counters.
- The safety latch still uses the debounced limit state. The underlying raw pins
  are still reported for diagnostics.

Expected behavior:

- A single noisy pulse on X5 +limit/home should appear at most as a short raw
  event and should not become `limit_pos_active=true` unless it persists for five
  consecutive 10 kHz samples.
- A real limit held active for >0.5 ms will still latch.

Required action:

- Reflash the Pico firmware before running v4.68 host scripts.
