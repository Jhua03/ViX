# v4.46

Stage 4 coarse-ladder update after real evidence from v4.45:

- Preserves the validated Stage 2 hold and Stage 3 direction proof.
- Keeps the v4.45 bounded current ladder (`CL=2,3,5,8,12,16,20`, `IW=1000`).
- Treats non-latched Pico/ViX delta disagreement as advisory-only for the Stage 4 10 µm / 1 µm coarse blocks when:
  - Pico command-frame endpoint following error is clean,
  - ViX settled PE is clean,
  - encoder-invalid count does not increase,
  - drive faults remain zero.
- This prevents a clean 10 µm block from aborting only because the ViX PA/PE serial snapshot and Pico endpoint sample were not captured at the exact same instant.
