# v4.69 post-enable settle probe patch

Purpose: keep the v4.68 X5 debounce firmware, but make the post-enable settle
probe more useful after field evidence showed the old local-zero preparation was
too strict immediately after Stage 8.

Changes:
- `vix_post_enable_settle_probe.py` reports v4.69.
- The pre-enable local-zero preparation gate is relaxed for this diagnostic only:
  default 20 counts over a 0.25 s window, max wait 20 s.
- The post-enable quiet/hold pass gate is unchanged.
- The evidence directory is automatically zipped next to the run directory on
  both success and safe abort.

This is still not a final 100 nm validation script. It asks only whether the
already-energised stage can settle quietly after the enable transient.
