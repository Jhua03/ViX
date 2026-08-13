# v4.56 Stage-6 recovery after v4.55 fine-screen pass

Fixes the v4.55 Stage-6 state migration bug that invalidated a freshly passed
Stage-5 fine-screen result before validation could start.

Changes:
- Bumps state schema/policy to `fine_validation_recovery_v4_56`.
- Treats an already-current v4.56 state as a no-op during migration.
- Preserves a validated Stage-5 fine-screen pass during policy migration when
  `stage_5_fine_screen_passed` and `fine_gains` are present.
- Adds `--recover-stage5-from-evidence` to rehydrate a validated fine-ladder
  PASS bundle after the v4.55 migration bug already erased the pass flag.
- The Stage-5 evidence recovery validates the 1 µm, 500 nm, 200 nm, and
  100 nm metrics for clean direction, clean faults, zero encoder-invalid
  deltas, no latches, no I2t, and fine-screen acceptance before unlocking
  Stage 6.
