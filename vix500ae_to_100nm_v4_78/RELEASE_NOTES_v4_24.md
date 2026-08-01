# v4.24 release notes

## Field evidence that triggered this patch

Two v4.23 Stage 2 runs exposed two separate, recoverable cases after the gain ladder started working:

1. The long-hold ladder found a real 10-count-class candidate at CL=2%:
   `GAINS(0,0.1,2,1,0)` passed with `PE=-6 counts` and `tail span=2 counts`.
2. The selected-gain trace confirmation then hit the same stale ViX PE local-zero state that candidate preparation already knew how to recover from. The confirmation path still used the old direct `prepare_pico_for_enable()` call, so it aborted with `PE=-13` instead of using the bounded OFF+Z reset wrapper.
3. A second run aborted because the stage moved only about 6-8 counts during the single 0.25 s local-zero quiet check. That is 60-80 nm at this encoder scale and should be treated as a short relaxation window to wait through, not as immediate failure, unless it keeps creeping or exceeds the bounded total drift gate.

## Host changes

- Stage 2 selected-gain confirmation now uses the same bounded stale-PE reset wrapper as the candidate loop:
  - OFF
  - Pico disable/disarm/clear
  - ViX Z reset/restore
  - re-apply volatile MP/gain/CL/TL setup
  - re-apply Pico policy
  - retry local-zero once
- Local-zero preparation now waits for one quiet 0.25 s window, up to 2.0 s total, instead of aborting on a single 6-8 count relaxation interval.
- Continuous creep is still rejected: total drift beyond the bounded local-zero allowance or no quiet window by the deadline aborts.
- Stage 2+ is invalidated on migration from v4.23 because the selected-gain confirmation and local-zero settle rules changed.

## Expected behavior

A rerun of Stage 2 should preserve Stages 0-1, retest the ladder, select the observed stable seed if it repeats, then proceed into the selected-gain confirmation instead of aborting on stale PE or a one-window nanometer-scale relaxation.
