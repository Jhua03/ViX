# v4.51 - Stage 5 intermediate GI candidate allowed

## Why this exists

v4.50 introduced a Stage 5 safe-start ladder using GI=0.1, GI=0.15, then GI=0.2. The code still validated fine-ladder gains against the Stage 4 motion-candidate set, which accidentally excluded GI=0.15 and aborted before any fine motion test.

## Changes

- Adds bounded intermediate candidate `GF0 GI0.15 GP2 GV1 FT0` to the motion-gain allow-list.
- Keeps the Stage 5 safe-start order: GI=0.1, GI=0.15, then the Stage-4 coarse-proven gain.
- Does not save the intermediate gain unless it passes the full 1 um -> 500 nm -> 200 nm -> 100 nm ladder.
- Migrates v4.50 state while preserving validated Stage 2/3/4 data when present.

## Run

```bash
python3 host/vix100nm_commission.py \
  --stage 5 \
  --recover-stage4-from-evidence /home/eric/vix100nm_runs/20260730_212104_451345_coarse_ladder.zip \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop
```
