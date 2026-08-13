# v4.62

Adds a deeper no-motion hold/EMI/integrator discriminator. It runs no commanded moves.

Changes from v4.61:
- Adds power-stage ON with zero gains.
- Adds no-GI GP/GV hold phases before GI phases.
- Adds low-current CL=1% GI threshold phases.
- Fixes premature probe stopping on the literal word `latched` inside diagnostic snapshots.
- Adds a more specific verdict separating motor-enable EMI, P/V loop instability, and integral hunting.
