# v4.27 release notes

- Fixes v4.26 schema migration: accepts schema 16/17 state files created by v4.25/v4.26 after validated Stage-2 evidence rehydration.
- Preserves validated Stage 2 selected hold seed and current clamp while invalidating only Stage 3+ downstream results.
- Keeps v4.26 Stage 3 behavior: revalidate the selected Stage-2 seed before any softer/stiffer comparison candidates.
- Offline checks pass.
