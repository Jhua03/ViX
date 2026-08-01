# v4.26 release notes

Purpose: fix Stage 3 after a validated v4.24/v4.25 Stage 2 hold pass.

## Field failure addressed

v4.25 rehydrated the validated Stage 2 seed correctly, but Stage 3 revalidated from the soft beginning of the ladder (`GF0 GI0 GP0.25 GV0.25 FT0`) and aborted as soon as that known-too-soft candidate drifted. It therefore never reached the measured Stage 2 pass seed (`GF0 GI0.1 GP2 GV1 FT0`, `CL=2%`).

## Changes

- Stage 3 now revalidates the selected Stage 2 seed first.
- If the seed revalidates, Stage 3 may score bounded nearby comparison candidates.
- A softer post-seed comparison candidate becoming unsettled no longer invalidates the already-revalidated seed.
- v4.25 and v4.24 states preserve Stage 2 during migration.
- Stages 3+ remain invalidated on migration.

## Safety behavior unchanged

Stage 3 still aborts before sign/scale motion if the selected Stage 2 seed itself is rejected, unsettled, faults, exceeds the local motion gate, trips Pico following-error/watchdog/limit checks, or leaves unrecoverable dirty zero state.
