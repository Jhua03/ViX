# v4.40

- Stage 4 now clears stale ViX PE/PT state between bounded current-clamp attempts.
- Stage 4 uses the same OFF+Z reset/local-zero recovery used by Stage 3 before each coarse 100 um candidate.
- This lets CL=3% and CL=5% actually run after a CL=2% endpoint-shortfall, instead of being blocked by stale PE left by the failed leg.
- Preserves v4.37/v4.39 Stage 2+3 state.
