# vix500ae_to_100nm_v4_78

Targeted threshold-refinement package for the ViX500AE/Base + MX80L + Pico2 setup.

Use after v4.77 found the best strong threshold at 40 counts / 400 nm using:

```text
damped_gi0p2_gp2_gv1p5_cl2
GF0 GI0.2 GP2 GV1.5 FT0, CL=2%
```

Run:

```bash
./scripts/run_offline_checks.sh

python3 host/vix100nm_commission.py \
  --stage 8 \
  --vix-port /dev/ttyUSB0 \
  --pico-port /dev/ttyACM0 \
  --bench-no-estop

./scripts/run_threshold_refinement.sh
```

Default amplitudes are 50, 40, 35, 30, 25, 20, 15, 10 counts, equal to 500, 400, 350, 300, 250, 200, 150, 100 nm.

The sweep validates the 400 nm threshold and tests conservative current/gain nudges:

```text
damped_gi0p2_gp2_gv1p5_cl2
damped_gi0p2_gp2_gv1p5_cl3
damped_gi0p2_gp2_gv1p5_cl4
damped_gi0p3_gp2_gv1p5_cl3
```

This is not final 100 nm validation. It is a threshold-refinement test to see whether the usable threshold can be pushed from 400 nm toward 300/250/200 nm. Stay present; the script commands real moves.
