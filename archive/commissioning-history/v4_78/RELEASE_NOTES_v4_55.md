# v4.55 fine comprehensive sweep

- Replaces one-by-one Stage 5 fine-ladder retries with a bounded comprehensive gain/current sweep.
- Skips already-passed Stages 2-4 by using `--recover-stage4-from-evidence`.
- Adds minor bounded settle-miss acceptance for Stage 5 screening only: quiet tail, no faults/latches/encoder invalid, and endpoint error within screening tolerance.
- Uses the Stage-5 selected `fine_cl_percent` for Stage 6.
- Writes `fine_sweep_plan.json`, `fine_ladder_candidate_attempts.json`, and `fine_sweep_ranked_candidates.json` so a failed sweep still gives useful ranking data.
