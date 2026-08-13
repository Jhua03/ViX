# v4.22 release notes

Purpose: fix the Stage 2 v4.21 field result where `GP0.25/GV0.25` held safely but drifted about 11 um, then the host stopped before trying the rest of the already-bounded gain ladder.

Changes:

- Stage 2 now distinguishes **too-soft/unsettled but safe** from a true safety abort.
- A safe, unsettled candidate no longer stops the Stage 2 sweep before higher bounded candidates.
- The sweep starts at `CL=2%`; if all bounded gains are still too soft, it adaptively repeats at `CL=3%` and then `CL=5%`.
- Later stages reuse the Stage 2 selected current clamp instead of assuming `CL=2%`.
- Stage 3 still refuses to go beyond the Stage 2-qualified seed during sign/scale work.
- v4.21 state migrates by preserving Stages 0-1 and invalidating Stage 2+.

Safety gates kept:

- ViX DF abort
- Pico fault/limit/E-stop abort
- encoder-invalid abort
- I2t abort
- watchdog abort
- dirty local-zero abort
- 20 um Stage 2 hold displacement gate
- 50/100 um later-stage motion guard windows
