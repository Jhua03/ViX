# v4.37 post-DIR-wiring fast resume

Purpose: after the AM26LV31 DIR wiring fix, skip the old sign discovery and use the coordinate frame shown by the latest v4.36 evidence.

Changes:
- Fast Stage 3 uses ENCSIGN=-1, DIRINV=0, ViXsign=+1.
- Keeps the validated Stage 2 seed: CL=2%, GAINS(0,0.1,2,1,0).
- Continues to require a short hold spot-check and +250/-250/+250 bidirectional STEP/DIR proof before Stage 4.
- Does not hide repeated ENCODER_INVALID or real DF/limit/fault conditions.
