# Changelog

## Repository cleanup / AH guide

- Reworked the repository around **ViX250AH / ViX500AH + Pico 2** rather than a single ViX500AE/MX80L experiment.
- Replaced the agent-handoff-style root README with a user-facing GitHub guide.
- Split the long ViX document into topic-focused Markdown files.
- Added a custom **X3 RS-232 cable** guide and diagram.
- Added a complete low-voltage **Pico 2 ↔ X4** interface using AM26LV31E/AM26LV32E, with KiCad source, SVG/PNG exports, and draw.io source.
- Added BOM, connector pinouts, DigiKey Canada links, and manufacturer datasheets.
- Added breadboard/perfboard/PCB construction guidance, including SOIC-to-DIP adapter-board wiring.
- Added `host/vix.py`, a small host utility for identity/status, volatile configuration, safe shutdown, and one-transaction MX80L jogging.
- Corrected documentation inconsistencies from the long-form source, including the 50-count unit conversion and the latest firmware encoder sign.
- Moved the full development/commissioning history into `archive/commissioning-history/`.

## Historical v4.x commissioning series

The archived v4.19–v4.78 work progressively added and hardened:

- Pico 2 STEP/DIR pulse generation and encoder feedback;
- ViX X4 hardware-enable/fault handling;
- limits, E-stop, heartbeat, following-error, and latch policies;
- guarded stale-fault recovery and offline safety audits;
- repeatable small-movement characterization and threshold sweeps;
- the final v4.78 threshold-refinement sweep around the measured 400 nm region.

The complete per-version notes are preserved unchanged in [`archive/commissioning-history/v4_78/`](archive/commissioning-history/v4_78/).
