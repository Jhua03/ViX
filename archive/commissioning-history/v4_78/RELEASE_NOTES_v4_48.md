# v4.48 — Preserve/recover validated Stage 4 for fine ladder

Field issue: v4.47 found the correct Stage-4 motion gains (`GF0 GI0.2 GP2 GV1 FT0`) and passed the 100 um / 10 um / 1 um coarse ladder, but the saved fingerprint still said v4.46. Starting Stage 5 then migrated the state as if Stage 4 had to be invalidated.

Fixes:

- Updates the commissioning fingerprint to a v4.48 fine-screen policy.
- Preserves a validated v4.47 Stage-4 coarse pass during migration when motion gains are recorded.
- Adds `--recover-stage4-from-evidence /path/to/coarse_ladder.zip` to rehydrate Stage 4 from a validated `coarse_ladder_summary.json` without rerunning the motion.
- Extends bounded motion-gain validation to include the Stage-4 GI/GP/GV candidates used by v4.47.

Operator path after the v4.47 Stage-4 pass:

```bash
python3 host/vix100nm_commission.py \
  --stage 5 \
  --recover-stage4-from-evidence /home/eric/vix100nm_runs/20260730_212104_451345_coarse_ladder.zip \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
```
