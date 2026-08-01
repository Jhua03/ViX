# v4.50 - Stage 5 safe-start gain fallback

Fixes the v4.49 Stage-5 startup-hold instability seen after Stage-4 evidence rehydration.

Changes:
- Preserves validated Stage 2/3/4 state across the v4.50 fingerprint migration.
- Stage 5 now tries bounded safe-start gain candidates:
  - the older proven quiet hold seed first, usually GF0 GI0.1 GP2 GV1 FT0,
  - then GI0.15,
  - then the Stage-4 GI0.2 motion gain.
- Each candidate gets an independent OFF/Z/restore and stale-PE recovery path before testing.
- The first candidate that passes 1 um, 500 nm, 200 nm, and 100 nm is saved as `fine_gains`.
- Stage 6 and Stage 7 use `fine_gains` when available instead of blindly returning to the Stage-4 coarse gain.

No ViX settings are saved persistently.
