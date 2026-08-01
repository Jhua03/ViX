# v4.75 Release Notes

Confirmed-candidate focused motion proof after v4.74 settled-tail gain sweep.

## Main changes
- Uses the v4.74 confirmed settled-tail candidate only:
  - `GF0_GI0.05_GP1.5_GV1_FT0`, `CL=2%`
- Keeps the enable-once/post-gain-tail-gated workflow.
- Runs a supervised motion ladder:
  - sham/no-step
  - ±100 counts = ±1000 nm
  - ±50 counts = ±500 nm
  - ±20 counts = ±200 nm
  - ±10 counts = ±100 nm
- Auto-zips evidence on completion or safe abort.

## Safety
- Stay present. This script commands real STEP/DIR moves.
- Do not run old Stage 6 for this workflow.
