# v4.66 — Pico-fast post-enable settle probe

Fixes the v4.65 failure mode where the ViX stopped returning report payloads immediately after ON.

Changes:
- Post-enable repeated sample windows now use Pico status only for high-rate encoder/fault evidence.
- The script no longer requires ViX ST2 readback after ON for this diagnostic.
- Post-kick ViX zero sends bounded W(...) commands without R(PT)/R(PF) polling.
- Summary always includes a verdict object if the script aborts before final classification.

This remains a diagnostic gate only: it proves whether an already-energised stage can settle quietly after the enable transient; it is not final 100 nm validation.
