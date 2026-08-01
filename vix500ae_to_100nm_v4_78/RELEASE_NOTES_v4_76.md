# v4.76 Release Notes

Exploratory multi-candidate motion sweep after v4.75 showed good 1 µm ABBA closure but one strict per-leg endpoint miss.

Changes:
- Uses multiple v4.74 settled-tail candidates.
- Does not abort on a single endpoint-settle miss; records it and continues if safety gates remain clear.
- Still hard-aborts on Pico latch, ViX fault line, encoder-invalid change, operator stop, or excessive movement.
- Runs a bounded 100/50/20/10 count ladder with fewer default blocks per candidate to keep supervised runtime reasonable.
- Auto-zips evidence.
