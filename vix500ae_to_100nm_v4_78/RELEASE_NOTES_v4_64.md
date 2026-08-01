# v4.64 post-enable settle discriminator

Adds `host/vix_post_enable_settle_probe.py` and `scripts/run_post_enable_settle_probe.sh`.

This is not a final 100 nm validation stage. It commands no STEP/DIR moves. It allows one bounded ViX ON transient with zero gains and low current clamp, then tests whether the already-energised system can be re-referenced in the ViX and hold quietly with bounded gain candidates.

Intent:
- Decide whether the observed 40–50 µm enable kick can be treated as a startup transient.
- Require post-kick quiet hold before any future 100 nm validation workflow.
- Avoid aggressive GP3/GV1.5 variants and avoid repeated enable cycling.

Evidence:
- `POST_ENABLE_SETTLE_SUMMARY.json`
- `POST_ENABLE_SETTLE_VERDICT.txt`
- per-window CSV traces
