# v4.49 – Stage 4 evidence recovery CLI flag fix

- Fixes the v4.48 packaging error where `--recover-stage4-from-evidence` was implemented in `main()` but missing from `argparse`.
- No motion policy change versus v4.48.
- Intended use: rehydrate the validated v4.47 Stage 4 coarse ladder evidence and continue directly to Stage 5.
