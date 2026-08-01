# v4.10 engineering audit

## Verdict on v3

v3 was not ready for powered commissioning. The most important defect was that
it asserted the X4 enable input but never issued the required ViX `ON` command.
The zero-gain and gain-hold stages could therefore appear stable while the motor
was not energised.

Additional problems found were missing stage-order enforcement, a default gain
fallback, incomplete fault/invalid checks during shams, delayed Ctrl+C handling,
and acceptance criteria that relied too heavily on medians and sham span.

## Corrective actions in v4

1. Added X4-enable + serial-`ON` transaction and ST2.1 confirmation.
2. Added strict stage prerequisites and hardware/software state fingerprinting.
3. Removed guessed gains.
4. Added complete-run invalid-transition, latch, and DF checks.
5. Added bracketed Pico/ViX endpoint acquisition.
6. Added 95th-percentile and repeatability gates for the final 100 nm claim.
7. Added sham absolute-motion gates, not only sham range.
8. Added immediate KeyboardInterrupt cleanup.
9. Added mocked integration and adversarial offline tests.

## Known physical constraints retained

- Limit+ works: raw 1 active, raw 0 inactive.
- Limit- is unavailable and disabled by policy.
- Home works: raw 1 active, raw 0 inactive.
- No automatic homing or end search.
- Every powered stage creates a local zero and limits commands to +/-0.5 mm.
- Operator must confirm at least 1 mm physical clearance in both directions.
- Initial HE500 current clamp remains 1% to 2%, approximately 0.15 A to 0.30 A
  under the audited configuration.

## Release decision

Use v4.10 only. Flash Pico v2.3, run the offline checks, and run Stage 0. Do not run
Stage 1 until Stage 0 passes and the E-stop/hardware disconnect is ready.

## Additional v4.10 review

A second audit found no new route to bypass the staged gates, but added two
defensive controls before hardware release: explicit local target alignment using
`W(PA,0)` while OFF, and strict post-test proof that both the Pico enable output
and ViX ST2.1 are de-energised. Powered results are rejected if ST2.1 drops
unexpectedly during the measurement.


## v4.10 findings from the additional audit

The v4.1 release was not accepted unchanged. Two defects were found:

- **Pass-state/cleanup ordering:** stage functions wrote pass state before the
  context-manager cleanup. Cleanup errors were suppressed, so a failed
  de-energisation or restore could coexist with a saved pass flag.
- **Direction-probe baseline timing:** the initial encoder baseline was captured
  before energisation and could include enable-settling displacement.

v4.10 introduces strict cleanup error propagation, stage-in-progress crash
recovery, failure-driven downstream invalidation, and a post-energisation
direction baseline. It also expands exact Pico and ViX preflight readback.


## v4.19 audit note

The previous 234/250 result was caused by asynchronous PA/PE sampling. v4.19 forbids target inference from an unbracketed PA or PE value and preserves every accepted/rejected bracket in evidence.


## v4.19 forward audit

The following downstream failure modes were reviewed before release:

- slow zero-target settling from the Stage 2 gain;
- asynchronous PA/PE target reconstruction;
- opposite target sign before DIRINV correction;
- estimator precision tighter than serial timing supports;
- fixed waits in coarse, fine, and 100 nm ABBA tests;
- trace overflow when adaptive settling lengthens a block;
- Pico/ViX endpoint comparison at different timestamps;
- shams with unrealistically short dwell;
- carrying the Stage 2 hold gain into all later motion stages;
- stale Stage 3/downstream state after a gain or sign change.

The host now records a separate `motion_gains` state value selected by Stage 3.
Stages 4-7 cannot silently fall back to an uncharacterized higher gain.


## Final forward-audit findings corrected

1. Added an explicit v4.19 commissioning-policy fingerprint and v4.18 migration,
   preventing a previous Stage 3 pass from bypassing the new gain/settling rules.
2. Forced the first ABBA block to precede all shams and made trace selection
   deterministic.
3. Removed the 3-second sham cap; sham timing now follows measured settling up to
   the amplitude-specific endpoint budget.
4. Corrected current-firmware instructions to v2.6/protocol 5 and retained v2.5
   only as clearly labelled historical context.
5. Corrected the Stage 3 prompt to match the actual 20 µm hold and 50 µm probe
   safety windows.
