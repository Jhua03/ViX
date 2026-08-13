# v4.59 focused final 100 nm repeatability/noise discriminator

Purpose: stop the broad Stage-6 gain sweep after v4.58 showed GP3/GV1.5 variants were too aggressive and could trigger hard safety events. v4.59 uses only the Stage-5-proven fine gains, repeats 100 nm ABBA validation, and adds more interleaved sham/no-motion windows to separate commanded 100 nm response from background drift/noise.

Key behavior:
- Uses Stage-5 fine gains only: GF0 GI0.5 GP2 GV1 FT0 when recovered from the passed Stage-5 evidence.
- Does not try GP3/GV1.5 candidates.
- Runs focused 100 cps replicate A/B, then 75 cps and 50 cps focused replicates.
- Keeps hard stops for ViX DF, Pico latch, encoder-invalid, I2t, limit, wrong direction, and excessive motion.
- Writes FINAL_100NM_NOISE_DISCRIMINATOR_SUMMARY.json when no final pass is produced.
