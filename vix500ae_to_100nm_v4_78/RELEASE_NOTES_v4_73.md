# v4.74

## Purpose

v4.72 proved that the single Candidate B motion proof is too narrow: the candidate can be quiet in one run and have a ~200-count settled tail in another. v4.74 replaces the one-candidate motion proof with a no-command settled-tail gain mini-sweep.

## What changed

- Adds `host/vix_settled_tail_gain_sweep.py`.
- Adds `scripts/run_settled_tail_gain_sweep.sh`.
- No STEP/DIR moves are commanded.
- Enables once with zero gains and low current clamp, allowing a bounded enable transient.
- Sweeps a bounded set of already-energised gain/current candidates.
- Scores the last 2.0 seconds of each hold window, not the gain pull-in transient.
- Re-applies the best first-pass candidate for two confirmation windows.
- Auto-zips evidence on success or safe abort.

## Intended decision

- If a candidate passes and confirms, use that exact candidate for the next focused 500/200/100 nm motion proof.
- If no candidate passes, do not keep trying 100 nm motion; fix hold/noise/settling first.
