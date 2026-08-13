# v4.71 — B-only post-gain-settle motion ladder

- Keeps Pico firmware vix-base-pico2-v2.7 from v4.68/v4.69.
- Uses only the best v4.69/v4.70 candidate: GF0 GI0.5 GP2 GV1 FT0, CL=2%.
- Waits after applying the actual gain candidate, then re-zeros/re-references before scoring hold noise.
- Runs a supervised ladder in the safer order: 500 nm, 200 nm, then 100 nm.
- Keeps auto-zipped evidence.
