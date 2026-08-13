# v4.34

Hardens Stage 3 energize retry recovery.

- Re-arms the Pico before retrying ENABLE after bounded ENCODER_INVALID cleanup.
- Clears host-generated USER_ABORT latch before a retry, but refuses to enable through any real safety latch.
- Re-zeros Pico local command/encoder coordinates after disabled recovery cleanup when needed.
- Keeps ENCODER_INVALID repeated-latch behavior as a hard stop for encoder signal-integrity diagnosis.
