# v4.78

Targeted threshold-refinement sweep after v4.77 found a strong threshold at 40 counts / 400 nm.

Changes:

- Adds `host/vix_threshold_refinement.py`.
- Adds `scripts/run_threshold_refinement.sh`.
- Uses the v4.77 best damped candidate and conservative CL/gain nudges.
- Default amplitude ladder: 50,40,35,30,25,20,15,10 counts.
- More repeats near the 40-count threshold.
- Keeps hard safety aborts for Pico latch, ViX fault line, encoder-invalid change, operator stop, and excessive movement.

Purpose: validate 400 nm repeatability and determine whether 300/250/200 nm is reachable before any renewed 100 nm proof attempt.
