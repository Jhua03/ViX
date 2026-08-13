# v4.77 Release Notes

Purpose: threshold-characterization sweep after v4.76 showed 1 um and 500 nm motion are close/usable but 100 nm is not yet validated.

Changes:
- Adds `host/vix_threshold_characterization.py`.
- Adds `scripts/run_threshold_characterization.sh`.
- Uses the best v4.76 candidates: `stage4_gi0p2_gp2_gv1_cl2`, `stage2_gi0p1_gp2_gv1_cl2`, and `damped_gi0p2_gp2_gv1p5_cl2`.
- Dense amplitude ladder: 100, 75, 50, 40, 30, 25, 20, 15, and 10 counts.
- Does not abort on one endpoint miss; hard-aborts only on safety latches/fault line/encoder invalid/movement-limit/operator stop.
- Scores median response ratio, direction fraction, endpoint error, closure, and strong/usable/partial/stuck class per amplitude.
- Auto-zips evidence and writes `THRESHOLD_CHARACTERIZATION_SUMMARY.json`.

Expected runtime: about 20-45 minutes depending on settling and how many candidates pass hold/sham gates.
