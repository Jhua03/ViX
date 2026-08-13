# v4.53 release notes

Stage 5 safe-start watchdog-margin patch.

Field evidence from v4.52 showed the 1 um block passed cleanly, then a 50-count
fine block latched HOST_WATCHDOG after one delayed Pico STATUS transaction. The
motion evidence at the latch had no drive fault, no encoder-invalid count change,
and only ~5 counts following error, so this was a host/USB scheduling/serial stall
against the 750 ms heartbeat window, not a motion failure.

Changes:

- Adds `FINE_ACTIVE_WATCHDOG_MS = 5000`.
- Allows `configure_pico_policy(..., watchdog_ms=...)`.
- Runs Stage 5 and Stage 6 fine-motion enabled tests with the 5 s Pico host
  watchdog margin while keeping the existing Pico following-error, limit, fault,
  encoder-invalid, soft-window, and ViX DF/I2t checks active.
- Preserves v4.52 Stage 2/3/4 validated state during migration.
- Records the active watchdog value in Stage 5 prep evidence.

No ViX settings are saved permanently.
