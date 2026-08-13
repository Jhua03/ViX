# v4.68 — LIMIT_POS input isolation probe

Purpose: diagnose the `pico_latch:LIMIT_POS` seen during v4.66 post-enable hold testing.

This release adds:

- `host/vix_limit_input_isolation_probe.py`
- `scripts/run_limit_input_isolation_probe.sh`

The probe commands no STEP/DIR moves. It runs phased evidence collection:

1. OFF baseline with Pico/ViX disabled.
2. X4 enable-only, before serial `ON`.
3. ViX `ON` with zero gains and CL=1%.
4. A soft already-energised hold gain only if zero-gain ON did not already show a limit issue.

The script starts the Pico trace buffer before each phase so short +limit glitches are recorded. It does not mask Pico safety: if LIMIT_POS goes active while GP11 enable is on, the firmware still latches and disables the drive.

Outputs:

- `LIMIT_INPUT_ISOLATION_SUMMARY.json`
- `LIMIT_INPUT_ISOLATION_VERDICT.txt`
- per-phase `*_host_status.csv`
- per-phase `*_trace.csv`

Interpretation:

- OFF baseline +limit active: polarity/wiring/sensor state issue.
- X4 enable-only +limit active: enable/reference/transistor coupling into the limit input.
- ViX ON zero-gain +limit active: motor power stage / EMI / grounding / X5 conditioning issue.
- Soft gain only +limit active: servo-current/gain-dependent EMI into the X5 line.
