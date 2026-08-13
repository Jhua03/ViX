# v4.43

Stage 4 now distinguishes a real low-current endpoint residual from the earlier false-fail gates.

Changes:
- Preserves the validated v4.37 Stage 3 sign state: ENCSIGN=-1, DIRINV=0, ViXsign=+1.
- Keeps the selected hold gain seed: GF0 GI0.1 GP2 GV1 FT0.
- Stage 4 keeps IM=1 and IW=1000, but expands the temporary motion-only CL ladder from 2/3/5% to 2/3/5/8/12/16/20%.
- Adds `get_motion_current_clamp()` so later stages can use a Stage-4-selected motion clamp above the ultra-low hold clamp.
- Settings remain volatile; nothing is saved to the ViX drive.

Use after the v4.42 evidence showed quiet, clean, fault-free endpoints stuck about 125 to 338 counts short at CL<=5%.
