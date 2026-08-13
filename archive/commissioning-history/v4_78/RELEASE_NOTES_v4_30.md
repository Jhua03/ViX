# v4.30 release notes

Purpose: make Stage 3 stop failing one probe at a time when bidirectional direction evidence is inconsistent.

Changes:

- Stage 3 no longer aborts immediately on the first opposite corrected encoder response during +250/-250/+250 calibration.
- It completes a bounded bidirectional calibration matrix across the inferred DIRINV setting, alternate DIRINV, available ViX comparison signs, and fallback step rates.
- It writes `direction_scale_rate_diagnostics.json` during the matrix so partial results are preserved even if a later trial fails.
- It writes `direction_failure_diagnosis.json` with an explicit same-direction symptom detector. If both positive and negative commands produce the same encoder direction across DIRINV trials, the remaining issue is likely DIR signal wiring/line-driver/input behavior rather than servo hold tuning.
- v4.30 migrates v4.28/v4.29 state without erasing a validated Stage 2 hold seed.

Known state from the field before this patch:

- Stage 2 hold seed is good: CL=2%, GAINS(0,0.1,2,1,0).
- Stage 3 hold revalidation is good: PE near 0 to -5 counts, tail span about 1 count.
- Current blocker is bidirectional STEP/DIR proof, specifically the negative 250-count command producing positive encoder response in v4.29.
