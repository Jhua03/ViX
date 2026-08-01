# v4.70 — Focused post-enable 100 nm motion proof

Adds `host/vix_focused_motion_proof.py` and `scripts/run_focused_motion_proof.sh`.

Purpose:
- Do not run old Stage 6.
- Enable once with zero gains and low current clamp, allowing one bounded ViX ON kick.
- Apply only the two best already-energised hold candidates from v4.69:
  - `GF0_GI0_GP1_GV0.75_FT0`, `CL=1%`
  - `GF0_GI0.5_GP2_GV1_FT0`, `CL=2%`
- Run a short supervised proof: sham/no-step, ±10 count/100 nm ABBA, ±50 count/500 nm ABBA.
- Auto-bundle evidence on pass or safe abort.

Important:
- This is a focused proof, not final unattended validation.
- Pico following-error is not treated as an absolute endpoint metric after the enable kick because the Pico cannot ZERO while enabled; incremental encoder response per leg is used instead.
