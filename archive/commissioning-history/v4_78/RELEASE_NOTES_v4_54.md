# v4.54 fine small-amplitude settle margin

Field evidence from v4.53 passed 1 um and 500 nm fine blocks, then stopped before
200 nm because the local-zero startup settle gate required <=2 counts even though
the stage was quiet at about 3 counts (30 nm) with no faults, no encoder-invalid
counts, and no latch.

Changes:
- Keeps v4.53's temporary 5 s host watchdog during fine enabled tests.
- Adds `adaptive_settle_goal_counts()` so 20-count and 10-count fine amplitudes
  may proceed when quiet within 5 counts.
- Decouples response tolerance from the adaptive wait gate, so relaxing the wait
  gate does not loosen 100 nm response validation arbitrarily.
- Accepts/migrates v4.53 state while preserving validated Stage 2/3/4 data.
