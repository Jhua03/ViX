# Field analysis: v4.18 Stage 3 baseline failure

Evidence bundle:
`20260729_211837_913716_direction_scale.zip`

## What happened

No STEP move was issued. After `W(PA,0)`, X4 enable, and `ON`, the conservative
`GP=2, GV=1` hold response moved slowly while the target remained approximately
zero.

Selected observed brackets:

| Attempt | PA1 | PE | PA2 | midpoint target estimate |
|---:|---:|---:|---:|---:|
| 1 | 189 | 172 | 157 | 1 |
| 2 | 137 | 111 | 91 | 3 |
| 5 | 1 | -4 | -11 | -1 |
| 10 | -112 | -112 | -112 | 0 |
| 14 | -129 | -132 | -131 | 2 |

The old v4.18 gate accepted only brackets with `abs(PA2-PA1) <= 2` counts. It
obtained four accepted rows out of the required five and aborted.

## Conclusion

- Encoder-invalid delta: zero.
- ViX DF1-DF4: zero.
- X4 fault input: healthy.
- Limit+: inactive.
- Target estimate: consistently near zero despite substantial PA motion.
- Root cause: overly strict stationary-sample policy plus a gain seed too weak
  for efficient downstream settling.

v4.19 therefore changes both the estimator and the motion-settling strategy,
rather than weakening one threshold.
