# v4.47 Stage-4 gain/current endpoint diagnostic

Use this after v4.46 shows a quiet, fault-free 100 um endpoint residual that does not improve with CL=2..20%.

Changes:
- Preserves the v4.37 Stage-3 sign proof and v4.46 state fingerprint/schema to avoid unnecessary state resets.
- Stage 4 now tries a bounded gain/current matrix instead of current alone:
  - Keeps the selected seed first: GF0 GI0.1 GP2 GV1 FT0.
  - Then tries increased GI with the same GP/GV.
  - Then tries modest GP/GV stiffness/damping variants.
  - Keeps IW=1000 and the monitored CL ladder.
- If a 100 um candidate passes, it saves the selected temporary motion gains/current in the state and continues to 10 um and 1 um blocks.
- No settings are saved to the ViX drive.
