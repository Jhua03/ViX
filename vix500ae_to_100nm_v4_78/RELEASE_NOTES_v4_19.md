# v4.19 comprehensive adaptive commissioning revision

## Why this revision exists

The v4.18 Stage 3 run did not lose STEP pulses. It failed before issuing the
250-count move because the baseline target estimator required five nearly
stationary `PA -> PE -> PA` brackets and obtained four. The field sequence moved
from `PA=+189` to approximately `PA=-136` counts while the reconstructed target
remained clustered around zero. That was a slow enabled settling response from
the conservative Stage 2 gain, not bad encoder data or a target-scale failure.

v4.19 addresses the entire downstream design mismatch rather than adding
another one-line exception.

## Comprehensive Stage 3

Stage 3 now performs, in one attended run:

1. A complete bounded zero-target GP/GV hold sweep at `CL=2%`.
2. Selection of the quietest candidate that holds with `|PE| <= 10` counts.
3. A small sign probe that independently determines `ENCSIGN` and `DIRINV`.
4. Robust STEP/count validation using time-interpolated `PA -> PE -> PA`
   brackets.
5. `+250, -250, +250` verification, automatically retried at slower STEP rates
   only when needed.
6. Full `+1000` and `-1000` adaptive-settling tests.

The gain sweep is bounded to predefined zero-integral candidates from
`GP/GV=2/1` through `64/64`. `GF=GI=FT=0`, `PC=100%`, `TL=5000`, and
`CL=2%` remain enforced. Any fault, Limit+, impossible encoder transition,
I2t indication, watchdog loss, or 20 micrometre hold displacement stops the
sweep immediately.

## Target estimator

The ViX500AE does not reliably return `R(PT)`. v4.19 uses the field-observed
relationship `PE = PA - PT`, but no longer requires the stage to be stationary.

For every bracket it timestamps `PA1`, `PE`, and `PA2`, interpolates PA to the
PE timestamp, and computes the target. Seven estimates are robustly clustered;
outliers are rejected and the measured estimator uncertainty becomes the scale
tolerance, bounded to 5-12 counts.

This directly covers both prior failures:

- asynchronous PA/PE values cannot create a false 234/250 result;
- slow baseline movement cannot fail merely because only four stationary
  brackets were collected.

## Stages 4-7 audited in advance

All commanded ABBA legs now use adaptive endpoint settling. Fixed sleeps are
no longer used as evidence that a move settled. The gate checks:

- corrected Pico endpoint error;
- endpoint span over a recent time window;
- ViX fault output and DF status;
- Limit+;
- impossible encoder transitions;
- I2t;
- verified energisation.

The first-block trace period is planned from the worst-case move and adaptive
settling duration, preventing a later 4096-sample trace overflow. Shams use a
matched dwell based on recent real settling times. Evidence now records every
leg's settle time, goal, tail span, and pass/fail state.

## Firmware and saved state

This is a host-side commissioning revision. Pico firmware remains
`vix-base-pico2-v2.7`, protocol 5. No reflash is required when v2.6 is already
installed.

State schema remains 10, but the fingerprint now includes the v4.19
commissioning-policy ID. v4.18 and v2.5 legacy states are migrated explicitly:
Stages 0-2 are preserved, while Stage 3 and all downstream pass flags, signs,
motion gains, and 100 nm metrics are invalidated and recalculated.


## Additional release audit corrections

- The first real ABBA block always precedes shams, so trace capture is
  deterministic and sham timing has measured settling data available.
- Sham dwell follows the recent real-leg settling median up to the same
  amplitude-specific endpoint budget; it is no longer truncated at 3 seconds.
- Current instructions consistently require Pico v2.6/protocol 5.
- The Stage 3 prompt reports the actual 20 µm zero-target hold cutoff and 50 µm
  probe following-error window.
