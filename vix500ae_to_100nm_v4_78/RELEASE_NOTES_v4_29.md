# v4.29 release notes

Fixes Stage 3 direction/scale coordinate handling after v4.28 proved the selected Stage 2 gain seed but aborted when Parker ViX PA/PT used the opposite sign from the Pico command coordinate.

Key changes:

- Keeps the Pico encoder sign aligned to the Pico MOVE command coordinate, because that is the coordinate used by the firmware following-error safety latch.
- Adds `vix_axis_sign` so raw ViX PA/PT deltas can be transformed into the Pico command coordinate for evidence comparisons.
- Stage 3 no longer flips ENCSIGN merely to make Pico encoder response match raw Parker PA polarity.
- Direction/scale, coarse, fine, final 100 nm, and experimental 20/30 nm summaries now compare Pico and ViX after applying `vix_axis_sign`.
- Preserves the proven Stage 2 seed path and remains bounded by the same CL, TL, fault, limit, I2t, watchdog, and encoder-invalid gates.
