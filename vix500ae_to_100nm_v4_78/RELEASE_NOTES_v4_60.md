# v4.60 - Focused 100 nm noise classifier

Purpose: stop the Stage 6 back-and-forth loop after v4.59 showed late, bounded 100 nm settle misses. v4.60 keeps the Stage-5-proven gains only and does not retry aggressive GP3/GV1.5 candidates.

Changes:
- Stage 6 first runs one strict 100 cps final attempt.
- If strict validation misses, Stage 6 runs diagnostic/classifier 100 cps repeats that continue after bounded late settle misses and write full statistics.
- Diagnostic accepted settle misses are recorded and explicitly do not count as a final pass.
- Removed the 75/50 cps attempts that triggered Pico MOVE validation rejects in v4.59.
- Writes `FINAL_100NM_NOISE_CLASSIFIER_SUMMARY.json` when no strict pass is produced.

This package can still produce a true final pass only on the strict attempt. The classifier attempts are for deciding whether the remaining blocker is mechanics/drift/noise floor versus a real response problem.
