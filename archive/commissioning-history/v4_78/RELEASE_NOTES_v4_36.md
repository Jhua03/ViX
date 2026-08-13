# v4.36 fast Stage-3 resume

Adds `--stage3-fast-resume` for the validated ViX500AE/MX80L setup. The fast path rehydrates the v4.24+ Stage-2 gain seed, skips the long gain ladder and sign rediscovery, performs one short hold spot-check, and runs a direct +250/-250/+250 bidirectional STEP/DIR proof at 250 cps with one 100 cps fallback.

Known validated assumptions from prior evidence:
- `CL=2%`
- `GAINS(0,0.1,2,1,0)`
- `ENCSIGN=+1`
- `DIRINV=0`
- raw ViX PA/PT comparison sign `-1`

It also retries incomplete ViX STATUS identity reads during fast preflight, while preserving hard stops for faults, limits, unsafe inputs, repeated encoder-invalid, I2t, runaway, and watchdog failures.

Convenience wrapper:

```bash
./scripts/run_stage_3_fast_resume.sh
```

or pass a different Stage-2 evidence zip as the first argument.
