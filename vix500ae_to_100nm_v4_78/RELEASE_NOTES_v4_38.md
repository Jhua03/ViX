# v4.38 Release Notes — coarse endpoint IW/current fallback

Purpose: after the corrected STEP/DIR wiring and a passing fast Stage 3, Stage 4 reached the 100 um ABBA ladder but failed endpoint settling on block 1 leg 3 with a quiet residual around 173 counts. That pattern is not a direction failure; it is a post-move endpoint capture issue.

Changes:

- Adds a temporary motion integral-window policy for coarse/fine/validation moves: `W(IM,1)` and `W(IW,1000)`.
- Keeps the proven gain seed `GAINS(0,0.1,2,1,0)` unless earlier stages select something else.
- Stage 4 first tries the 100 um ABBA block using the selected CL, then bounded fallbacks `CL=3%` and `CL=5%` if needed.
- Records `coarse_10000_candidate_attempts.json` so current-limit versus endpoint-settle behavior is distinguishable.
- Stores `motion_cl_percent` and `motion_iw_counts` on Stage 4 pass; Stages 5-7 use these motion settings.
- No settings are saved to the ViX drive.

Run Stage 4 from this folder after Stage 3 has passed.
