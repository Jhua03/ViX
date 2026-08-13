# v4.61 — No-motion hold/noise/stability probe

Adds `host/vix_hold_noise_probe.py` and `scripts/run_hold_noise_probe.sh`.

Purpose: diagnose why Stage 6 final 100 nm validation is failing after Stage 5 passed once.
The probe performs no commanded moves. It measures:

- OFF/disabled encoder drift/noise
- ON hold with GF0 GI0.1 GP2 GV1 FT0, CL=2%, IW=1000
- ON hold with GF0 GI0.2 GP2 GV1 FT0, CL=2%, IW=1000
- ON hold with GF0 GI0.3 GP2 GV1 FT0, CL=2%, IW=1000
- ON hold with GF0 GI0.5 GP2 GV1 FT0, CL=2%, IW=1000
- ON hold with GF0 GI0.5 GP2 GV1 FT0, CL=1%, IW=1000

It writes per-phase CSV files, JSON summaries, and `HOLD_NOISE_VERDICT.txt`.

No GP3/GV1.5 variants are used. No 100 nm moves are commanded.
