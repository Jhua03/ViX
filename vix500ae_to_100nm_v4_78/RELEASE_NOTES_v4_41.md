# v4.41

Stage 4 fix after real CL fallback evidence showed the endpoint gate was still
using raw actual-to-actual displacement. ABBA moves are commanded relative to the
Pico command position, so if a previous leg ends a few counts off its target, the
next leg should settle to the new commanded endpoint/following-error rather than
fail on the previous residual.

Changes:
- Stage 4+ adaptive endpoint settle now uses Pico command-position endpoint error
  when available.
- Evidence rows include `command_position`, `target_position`, and
  `relative_error_counts`; `error_counts` is the commanded-endpoint error.
- ABBA metrics keep response-scale data but use settled following-error for
  endpoint/repeatability gates.
- Migrates v4.37/v4.39/v4.40 state while preserving the proven Stage 3 signs.
