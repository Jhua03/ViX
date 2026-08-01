# Validation performed for v4.20

## Static and offline checks

- Python syntax compilation: PASS.
- Host built-in `--self-test`: PASS.
- Shell script syntax (`bash -n`): PASS.
- C source strict syntax check with Pico-SDK interface stubs and
  `clang -std=c11 -Wall -Wextra -Werror`: PASS.
- Mocked ABBA integration covering X4 enable + `ON`, move completion, Pico/ViX
  endpoint agreement, shams, final faults, invalid-transition accounting, and
  final 100 nm acceptance: PASS.
- Adversarial acceptance tests confirm rejection of poor repeatability, excessive
  endpoint error, sham motion, ViX PE, invalid transitions, and unverified
  energisation: PASS.
- Stage 6 with an empty state is rejected before either serial port is opened:
  PASS.

## Not possible to prove offline

No software review can guarantee bug-free behaviour on the actual custom drive.
These remain hardware gates:

1. Official Pico SDK must build the UF2 on the user's Fedora system.
2. Stage 0 must confirm the real raw input states and exact drive fingerprint.
3. Stage 1 must prove X4 enable polarity, serial `ON`, ST2.1 energisation, and
   safe de-energisation on the real hardware.
4. Stages 2-6 must pass in order with evidence and no override of a failed gate.

The package is ready for **Stage 0**, not for jumping directly to 100 nm motion.

## v4.10 additions

- Mocked zero-alignment path covers ViX `W(PA,0)` plus Pico `ZERO`.
- Mocked powered integration verifies ST2.1 stays asserted during data collection
  and clears after the independent enable plus OFF shutdown.


## v4.10 additional tests

- Interrupted-stage marker recovery and downstream invalidation: PASS.
- Cleanup failure causes stage failure rather than a saved pass: PASS.
- Pico safe-state proof rejects enabled/armed/moving readback: PASS.
- Pico CONFIG SHOW exact readback comparison: PASS.
- Stage 3 baseline is acquired after verified energisation: code-path audit PASS.


## Final release checks added in v4.10

- Simulated 100-count enable transient is excluded from the +1000-count
  direction/scale measurement: PASS.
- A mocked failure during final OFF/Z cleanup propagates as a stage failure:
  PASS.
- Input confirmation remains false while raw Limit+/fault/E-stop states are
  being checked, then is enabled and read back only after they pass: code-path
  audit PASS.
- Reset cleanup now verifies OFF/ST2.1, saved `MT` mode, the complete corrected
  MOTOR definition, and all four DF bytes: code-path audit PASS.
- Source/package fingerprints and the complete extracted file checksums are
  verified by `scripts/run_offline_checks.sh`: PASS.


## v4.10 additional adversarial checks

- Reused completed move ID is automatically replaced and cannot false-complete: PASS.
- Completion requires matching active ID and non-MOVING state: PASS.
- Incomplete DF1..DF4 record is rejected: PASS.
- Arbitrary/non-finite saved gains are rejected: PASS.
- ABBA trace-full condition is a hard failure: source-path audit PASS.
- Firmware protocol fingerprint, powered invalid-transition latch, queue-init
  check, and signed-magnitude helpers: source audit PASS.


## Final v4.10 audit additions

- Extended Pico trace-dump timeout to 120 seconds because a 4096-sample JSON
  trace cannot reliably transfer over 115200-baud USB CDC within 15 seconds.
- Re-samples and re-validates Limit+, fault, Home and E-stop states after the
  ViX is forced OFF and again after `CONFIRM_INPUTS=1`.
- Tightened Stage 2 firmware following-error cutoff to 2000 counts.
- Requires settled ViX PE and Pico following error after the Stage 3 scale move.
- Added a PIO clock-divider range guard.
- Fixed the C declaration order caught by strict C11 compilation.


## v4.10 loader regression

- Complete `pico_sdk_tasks.py` executed with `__file__` absent: PASS.
- `$PROJECT_DIR/extra_scripts` import path resolution: PASS.
- `sdk_build`, `sdk_upload`, and `sdk_clean` registration: PASS.
- Source audit forbids `Path(__file__)` in the PlatformIO wrapper: PASS.


## v4.10 fault-recovery validation

- Exact `DF1=10000000`, `DF3=00010000` stale back-drive signature clears in
  the mock while Pico enable and ViX ST2.1 remain false: PASS.
- Motor-HV over-voltage test fault is rejected without sending `ON`: PASS.
- Incomplete or malformed DF reports are rejected: PASS.
- Recovery is called by every stage preflight and Stage 8 safe restore:
  source-path audit PASS.
- Historical v4.10 firmware-identity regression (`vix-base-pico2-v2.5`): PASS. Current v4.19 requires v2.6/protocol 5.


## v4.10 additional regression tests

- DF zero plus stale X4 fault-active input triggers a safe output refresh: PASS.
- Output refresh leaves Pico enable false and ViX ST2.1 de-energised: PASS.
- Permanently high/open X4 fault input remains a hard failure: PASS.
- Non-whitelisted DF faults still receive no `ON` clear transaction: PASS.


## v4.19 trace-budget regression

- 0.5 s hold selects 4096 samples at 1000 us: PASS.
- 1.5 s and 3.0 s holds remain below the protected 3600-sample budget: PASS.
- Complete disabled-before/enabled/disabled-after envelope is required: PASS.
- Requested capacity and period must match Pico TRACE INFO readback: PASS.
- TRACE INFO count must match dumped rows: PASS.
- Existing v4.10 state schema remains accepted: PASS.


## v4.19 Stage 3 regressions

- Opposite Pico/Vix PA signs correct `ENCSIGN`, not `DIRINV`: PASS.
- Negative ViX PT response corrects `DIRINV`: PASS.
- ViX PT verifies one STEP pulse per target count: PASS.
- Corrected +1000-count probe passes adaptive settling in the mock plant: PASS.
- Encoder sign readback is exact and persisted for downstream policy: PASS.
- Existing trace, safety, stale-fault, build-helper, and firmware audits: PASS.


## v4.19 packaging regressions

- Clean extracted package verifies `SHA256SUMS`: PASS.
- Manifest contains no `__pycache__` or `.pyc` entries: PASS.
- Offline checks create no bytecode inside the package tree: PASS.
- Adaptive Stage 3 sign/scale regression remains PASS.


## v4.19 serial-report regressions

- First `R(PT)` attempt echo-only, second attempt valid: PASS.
- Recovered numeric payload preserved exactly: PASS.
- Real `*E` receives no retry: PASS.
- Existing adaptive Stage 3 regression: PASS.
- Fresh-extraction checks and checksum manifest: PASS.


## v4.19 guarded-recovery validation

- Exact firmware/protocol identity updated to Pico v2.6 / protocol 5.
- Dedicated recovery command requires explicit DF20/DF21 acknowledgement.
- Internal 500-2000 ms deadline and RECOVERY_TIMEOUT latch audited.
- E-stop, limits, following error, invalid encoder and watchdog remain active.
- Initial fault may be ignored only until the line first clears; reassertion latches.
- Host applies zero gains, CL=1%, 50 um cutoff and complete trace.
- Normal completion proves serial OFF before X4 gate drop.
- DF-clear/X4-high physical fault is never auto-refreshed.
- Compatible v4.14 state migration preserves only Stages 0-2.


## v4.19 regressions

- Moving PA around a PE report is rejected as incoherent: PASS.
- Five stationary brackets reconstruct PT=250 exactly: PASS.
- Encoder-copy sign remains independent of STEP/DIR direction: PASS.
- Three-probe scale policy and slower-rate fallback source audit: PASS.
- Guarded DF20/DF21 firmware and host regressions: PASS.


## v4.19 comprehensive regressions

- Exact v4.18 moving-baseline PA/PE/PA sequence reconstructs target near zero:
  PASS.
- Large asynchronous PA outlier is rejected by robust target clustering: PASS.
- Target estimator derives a bounded 5-12 count uncertainty rather than
  hard-coding a false 2-count precision: PASS.
- Motion-gain values are restricted to the predefined zero-integral bounded
  candidate set: PASS.
- Signed positive and negative direction/scale probes: PASS.
- Adaptive endpoint settling replaces every commanded-leg fixed sleep: PASS.
- 100 micrometre and 100 nanometre first-block trace plans remain below 4096
  samples under worst-case adaptive settling: PASS.
- ABBA records contain settle time, settle goal, and settled status: PASS.
- Existing guarded DF20/DF21 recovery, fault polarity, Limit+, trace-envelope,
  firmware C11 syntax, PlatformIO helper, and clean-extraction tests: PASS.


## v4.19 final release audit

- v4.18 fingerprint migrates while preserving only Stages 0-2: PASS.
- v2.5 legacy fingerprint migrates directly to v4.19 policy: PASS.
- Stage 3/downstream gains, signs, and metrics are invalidated on migration: PASS.
- First ABBA event is a commanded block before any sham: source audit PASS.
- Sham dwell uses measured settling and amplitude-specific cap: source audit PASS.
- Current firmware documentation says v2.6/protocol 5: PASS.


## v4.20 validation addendum

- `python3 host/vix100nm_commission.py --self-test`: PASS.
- `python3 tests/offline_test.py`: PASS.
- `python3 tests/firmware_source_audit.py`: PASS.
- `python3 tests/firmware_c_syntax_test.py`: PASS.
- `python3 tests/build_helper_test.py`: PASS.
- `./scripts/run_offline_checks.sh`: PASS after regenerating `SHA256SUMS`.

v4.20 specifically validates the schema/policy migration, local PA/PT/PF/PE zero
transaction, and the no-escalation-after-unsettled-hold Stage 3 rule.
