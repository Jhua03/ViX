# v4.39

Stage-4 state migration hotfix.

- Accepts schema 26/27 state from v4.36/v4.37/v4.38.
- Preserves a validated v4.36/v4.37 Stage-3 DIR proof when entering Stage 4.
- Keeps Stage-4 coarse endpoint policy from v4.38: IM=1, IW=1000, CL fallback 2/3/5%.
- Prevents unnecessary reruns of Stage 2/3 after the wiring-corrected Stage-3 pass.
