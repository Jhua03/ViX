# v4.63 — zero-move enable/commutation kick probe

Adds `host/vix_enable_kick_probe.py` and `scripts/run_enable_kick_probe.sh`.

Purpose: after Stage 5 proved 100 nm screening but Stage 6/hold probes showed ON-only drift, separate:

- X4 enable-line disturbance while the ViX power stage remains OFF
- ViX `ON` zero-gain power-stage/commutation kick
- encoder-invalid / motor-enable EMI symptoms
- consistent-direction zero-gain kicks that point toward phase/commutation/preload

The script commands **no moves**. It uses only zero loop gains (`GF0 GI0 GP0 GV0 FT0`), `CL=1%`, repeated local-zero preparation, X4-enable-only windows, and ViX-ON zero-gain windows. It writes `ENABLE_KICK_PROBE_SUMMARY.json`, `ENABLE_KICK_VERDICT.txt`, and per-repeat CSV evidence.
