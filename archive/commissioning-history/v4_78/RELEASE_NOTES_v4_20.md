# v4.20 Stage 2/3 long-hold and local-zero hardening

## Why this revision exists

The 2026-07-29 Stage 3 evidence showed that the previously saved Stage 2 gain
seed `GF0_GI0_GP2_GV1_FT0` could pass the short ladder but then fail the longer
Stage 3 hold. During that failed hold the carriage drifted on the order of
100-200 encoder counts, which is already much larger than the 10-count/100 nm
final goal. After the failed hold, the next local-zero attempt reported
`ViX PA=0`, `Pico=0`, but `ViX PE=-195`, proving the host must not assume the
ViX target/error registers are clean merely because PA was set to zero.

## Host changes

- Bumped host commissioning state schema to 11 and policy fingerprint to
  `comprehensive_adaptive_v4_20`.
- Migrates v4.19/v4.18/v2.5 states by preserving only Stages 0-1. Stage 2 and
  downstream are invalidated so the gain seed is retested under the new long
  quiet-hold rule.
- Replaced the single `W(PA,0)` local-zero assumption with a verified
  PA/PT/PF/PE + Pico encoder/command/following-error transaction.
- Uses bounded recovery sequences while OFF: `W(PA,0)`, then
  `W(PE,0); W(PT,0); W(PA,0)`, then
  `W(PE,0); W(PT,0); W(PF,0); W(PA,0)` if needed.
- Stage 2 now uses the same long-hold PE/tail-span/tail-slope rule that gates
  Stage 3 motion.
- Stage 3 no longer escalates to higher stiffness after an unsettled hold. It
  revalidates only the conservative candidates up to the Stage 2 seed, stops at
  the first unsettled candidate, and performs no sign/scale moves unless a quiet
  hold exists.

## Operator impact

After installing v4.20, restart from Stage 2. Existing Stage 0/1 proof may be
preserved by the migration, but old Stage 2/3 pass flags are intentionally
removed.

Recommended command:

```bash
python3 host/vix100nm_commission.py \
  --stage 2 \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
```

Do not rerun v4.19 Stage 3. The v4.20 host will refuse to proceed from the old
gain seed and dirty reference-state assumptions.

## Validation

`./scripts/run_offline_checks.sh` passes after updating checksums.
