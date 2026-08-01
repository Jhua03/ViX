# v4.42

Stage 4 patch after the v4.41 100 um evidence showed clean traces and settled Pico endpoints but a false `Pico/ViX disagreement` quality-gate failure.

Changes:

- Fix adaptive-settle completion to use commanded endpoint/following-error error for MOVE legs.
- Use the final adaptive-settle Pico sample for Stage 4 endpoint/following-error metrics rather than a later non-latched status read.
- Use a bounded amplitude-aware Pico/ViX coherence tolerance for coarse Stage 4 ABBA blocks.
- Preserve validated Stage 2 and Stage 3 state from v4.37-v4.41.
