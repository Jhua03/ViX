# v4.33 release notes

Intent: reduce one-abort-per-transient behavior while keeping encoder safety hard.

Changes:

- Adds one bounded ENCODER_INVALID recovery during the X4-enable/ViX-ON handshake.
- If the first ENCODER_INVALID happens, the host disables X4, sends OFF, clears Pico latch/diagnostics, verifies the encoder-invalid counter stays quiet while disabled, then retries energising once.
- If ENCODER_INVALID repeats, the script stops with a hardware-oriented diagnosis instead of needing another patch.
- Keeps ENCODER_INVALID as a hard safety gate for actual motion and repeated enable-time failures. 100 nm movement is not trustworthy if the quadrature stream is producing impossible transitions while enabled.
- Keeps the v4.32 Stage-3 diagnostic matrix behavior for non-hard direction/polarity/settling cases.
