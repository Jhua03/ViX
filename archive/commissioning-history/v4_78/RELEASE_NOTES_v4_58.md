# v4.58

Stage 6 final 100 nm validation sweep.

- Keeps Stage 5 evidence recovery.
- Replaces the v4.57 two-attempt final validation with a bounded matrix: Stage-5-proven gains first, then nearby GI/GP/GV variants.
- Adds per-run startup-zero gate overrides so a quiet 6-8 count local preload does not block a replicate.
- Final endpoint/closure/sham/fault/encoder/I2t gates remain hard.
