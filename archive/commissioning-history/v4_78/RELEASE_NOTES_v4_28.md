# v4.28 release notes

## Purpose

Reduce Stage 3 back-and-forth after the first validated 100 nm-class Stage 2 hold seed.

## Field evidence addressed

- Stage 2 v4.24 selected `CL=2%`, `GAINS(0,0.1,2,1,0)` with a 10-count-class hold.
- Stage 3 v4.27 revalidated the correct seed, but rejected it when ViX serial polling left the final time-based tail under-sampled: `PE=3 counts`, `tail span=1000000000` sentinel.

## Changes

- Stage 3 is now a seed-revalidation and direction/scale gate, not a second gain-tuning ladder.
- Stage 3 revalidates only the measured Stage 2 seed, avoiding optional neighbor comparisons that could create unnecessary aborts.
- Added a sparse-tail-safe Pico-only confirmation window while the drive is still enabled. If the ViX PE is already within the 10-count goal but the serial-poll tail is under-sampled, the script captures a short high-rate Pico tail before rejecting the seed.
- Direction probes now use the same bounded stale-PE local-zero reset recovery as the hold ladder.
- v4.28 migrates v4.27 state and preserves the validated Stage 2 seed.
- Added offline regressions for sparse-tail seed revalidation and Stage 3 seed-only candidate ordering.

## Still intentionally blocked

- Real ViX DF faults.
- Pico latches, Limit+, encoder-invalid transitions, watchdog loss, or fault-output assertion.
- Repeated dirty local-zero after bounded OFF+Z recovery.
- Actual excessive movement during hold or direction probes.
