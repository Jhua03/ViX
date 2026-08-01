# v4.32 release notes

Intent: harden Stage 3 so non-hard diagnostic failures do not create a one-patch-per-abort loop.

Changes:

- Preserves v4.31/v4.30/v4.29/v4.28/v4.27/v4.26/v4.25/v4.24 Stage-2 evidence/state where the 100 nm-class hold seed is already validated.
- Keeps hard stops for real unsafe conditions: ViX drive faults, limits, E-stop/watchdog, I2t, encoder-invalid/runaway, unsafe cleanup, and serial port permission/open failures.
- Classifies polarity, endpoint settling, ViX/Pico disagreement, target-scale, and local-zero ambiguity as bounded diagnostic failures when safe, records them, and continues the Stage-3 bidirectional matrix instead of aborting immediately.
- Makes direction_scale_rate_diagnostics.json and direction_failure_diagnosis.json more likely to contain the full +250/-250/+250 matrix rather than only the first failing row.
- Adds an offline regression for Stage-3 diagnostic soft-fail classification.
