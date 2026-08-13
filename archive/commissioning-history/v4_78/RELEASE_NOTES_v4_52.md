# v4.52 release notes

Stage 5 fine-ladder patch. v4.51 evidence showed a candidate with clean endpoint/fault/encoder metrics failing only because the non-latched Pico/ViX endpoint snapshots differed by 6 counts against a 5-count advisory threshold.

Changes:
- schema 37 / policy fine_safe_start_pico_vix_advisory_v4_52
- preserves validated Stage 2/3/4 data from v4.51 and earlier supported states
- Stage 5 keeps the safe-start gain order (GI 0.1, 0.15, 0.2)
- `amplitude_pass()` treats Pico/ViX delta mismatch as advisory only when following error, ViX PE, encoder-invalid, fault, latch, and I2t gates are clean

No persistent ViX writes are added.
