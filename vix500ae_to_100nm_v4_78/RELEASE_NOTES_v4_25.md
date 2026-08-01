# v4.25

State-recovery patch after accidental older-bundle execution.

- Adds `--recover-stage2-from-evidence` to rehydrate a validated v4.24+ Stage 2 PASS from `gain_ladder.json` or the evidence zip/directory.
- Preserves v4.24 Stage 2 state during v4.25 migration because the powered tuning policy is unchanged.
- Auto-repairs a missing Stage 2 pass flag if a measured selected gain/current seed is still present in the state file.
- Keeps Stage 3+ invalidated after recovery; Stage 3 must still be run from the latest bundle.

## v4.26 note
Stage 3 revalidates the proven Stage 2 gain seed first before testing nearby alternatives.
