# ViX500AE + MX80L route to encoder-side 100 nm motion — v4.10

## Confirmed starting state

- Target drive: ViX500AE-Base, custom product CP13269 rev 3, HE500.
- Saved motor definition corrected to the 10 nm MX80L-D13 definition:
  `MOTOR(49420,1.6,1300000,138,80,4.75,1.80,4.500)`.
- ViX X4 quadrature copy and the Pico PIO count agreed exactly over more than
  1.5 million counts in both directions.
- Limit+ works and is active-high at the Pico input: raw 1 at the limit, raw 0 away from it.
- Limit- does not work and is excluded from the safety policy.
- Home works and is active-high: raw 1 at home, raw 0 away from home.
- Initial motion stays inside a manually centred +/-0.5 mm software window.

## Why firmware v2.3 is required

The v2.3 firmware adds four safeguards/measurement features before powered
commissioning:

1. A 750 ms host heartbeat lease. Loss of the laptop process disables X4-11.
2. Continuous following-error and limit checks even while holding with no MOVE
   active.
3. A real invalid-quadrature-transition counter driven by a rare-event PIO IRQ.
4. A 1 kHz on-Pico trace buffer for command position, encoder position,
   following error, invalid count, motion state and safety state.

## Stage gates

### Stage 0 - Input and identity preflight

No motion and no enable.

- Verify exact drive identity, corrected MOTOR definition, 75-85 V motor bus,
  and all DF bytes zero.
- Apply the runtime Pico policy:
  - `LPOL=1`
  - `HPOL=1`
  - `HAS_LN=0`
  - `FPOL=1`
  - `ENCSIGN=1`
  - software window `[-50000,+50000]` counts
  - watchdog 750 ms
- Require Limit+ to be inactive (`raw=0`) before arming.
- Home may read 0 or 1 depending on carriage location; it is a reference input,
  not a hard-stop input.

Gate: all checks pass.

### Stage 1 - Zero-gain enable smoke

- ViX temporary mode: MP, EI=0, EO=2, ES=0.
- `GAINS(0,0,0,0,0)`.
- CL=1% on HE500, approximately 0.15 A maximum.
- No STEP pulse. A pass is impossible unless the drive is confirmed energised.
- Start heartbeat, assert X4 enable, issue `ON`, and require `R(ST2)` to show ST2.1 motor-energised. Enable for 0.5 s with Pico trace, then drop X4 enable before `OFF`.

Purpose: validate X4 enable, fault polarity and absence of an enable transient
or unexpected torque before asking the position loop to hold.

Gate: no DF, no latch, no invalid transitions and no displacement beyond the
50 um firmware cutoff.

### Stage 2 - Low-gain hold ladder

Test, in order:

1. GP=0.10, GV=0.10
2. GP=0.25, GV=0.25
3. GP=0.50, GV=0.50
4. GP=1.00, GV=0.75
5. GP=2.00, GV=1.00

GF=GI=FT=0 during this stage. Each candidate is enabled for 1.5 s at CL=1%.
The stiffest stable candidate is repeated for 3 s at CL=2%, approximately
0.30 A maximum.

Gate: actual energisation confirmed, no fault/latch/invalid transition, no runaway, and bounded tail motion.
The selected gains are stored in `~/vix100nm_state.json`.

### Stage 3 - Direction and scale probe

- Command +1000 pulses, equal to 10 um at 10 nm/count.
- Rate 1000 counts/s.
- Compare Pico encoder change and ViX PA change.
- If direction is reversed, disable, toggle `DIRINV`, re-zero and retry once.

Gate:

- positive commanded response;
- 1000 +/- 5 encoder counts;
- Pico and ViX changes agree within 2 counts.

### Stage 4 - Coarse functional ladder

ABBA tests at:

- 100 um = 10000 counts
- 10 um = 1000 counts
- 1 um = 100 counts

CL=2%, local +/-0.5 mm window, both directions, no-command shams and first-block
1 kHz traces.

Gate: correct direction on every leg, response within 2% or five counts,
Pico/ViX agreement within two counts, clean faults and invalid counter.

### Stage 5 - Fine screening ladder

ABBA plus sham tests at:

- 1 um = 100 counts
- 500 nm = 50 counts
- 200 nm = 20 counts
- 100 nm = 10 counts

The runner stops at the first amplitude that fails. This is an efficient screen,
not the final 100 nm claim.

### Stage 6 - Final 100 nm validation

- 24 ABBA blocks.
- 96 commanded 10-count legs.
- 12 interleaved no-command sham holds.
- 100 counts/s, so each 100 nm command is generated over 0.1 s.

Gate:

- at least 95% correct-direction responses;
- median response 8-12 counts;
- no more than one wrong-direction leg;
- median ABBA closure <=3 counts;
- Pico/ViX path disagreement <=2 counts;
- sham span <=6 counts;
- no drive faults and no invalid quadrature transitions.

Passing this stage supports the statement: **the system commanded and measured
100 nm using its own 10 nm encoder path**. It is not independent physical
metrology because no interferometer is present.

### Stage 7 - Optional 30 nm / 20 nm stretch tests

Only after Stage 6 passes:

- 30 nm = 3 counts
- 20 nm = 2 counts
- 32 ABBA blocks and 20 shams per amplitude

These are quantised encoder-count experiments. They should not be described as
independently verified physical displacement.

## What remains deliberately excluded

- Automatic homing.
- Negative-limit search.
- Full-travel motion.
- Non-volatile gain or mode changes.
- MOTOR, SETUPFB, RFS or SV commands.
- Current above the initial CL=2% commissioning clamp.

## Mandatory ordering and reset policy

The runner refuses to enter a stage unless the preceding stage is recorded as passed for the exact drive/MOTOR/Pico fingerprint. Rerunning an earlier stage clears all later pass flags so stale evidence cannot unlock 100 nm validation.


## Fault recovery gate

Each stage begins by clearing only stale DF bit 20/21 signatures in a verified
non-energising transaction. Any other DF bit prevents commissioning from
continuing.


## Stage 3 v4.19 decision logic

The small probe classifies independent sign domains before evaluating final
settling. ViX PT is the command-domain reference, ViX PA is the drive feedback
reference, and the Pico encoder copy is compared against PA. The full probe only
passes after command scale, physical direction, cross-reader agreement, and
settling are all independently demonstrated.


## Guarded recovery gate added in v4.19

Any preflight DF20/DF21 is handled before motion-stage setup by the bounded
Pico v2.6 recovery transaction described in the release notes. No other DF is
automatically cleared.


## v4.19 Stage 3 decision path

1. Coherent 250-count sign probe. 2. Apply ENCSIGN/DIRINV correction. 3. Three coherent 250-count verifications. 4. Slower-rate diagnosis only after repeated mismatch. 5. 1000-count adaptive settling.


## v4.19 execution plan

1. Preserve passed Stages 0-2.
2. Run all bounded zero-target motion-gain candidates.
3. Select the best stable candidate using PE, tail span, and settling time.
4. Resolve encoder-copy sign and STEP/DIR direction independently.
5. Verify signed 250-count commands at the fastest passing STEP rate.
6. Verify signed 1000-count commands.
7. Reuse the selected motion gain for adaptive coarse/fine/final ABBA stages.
8. Stop only for a real safety, integrity, tuning-range, or acceptance failure;
   do not stop for a single missing serial payload, a moving target-estimator
   bracket, or a fixed dwell expiring.
