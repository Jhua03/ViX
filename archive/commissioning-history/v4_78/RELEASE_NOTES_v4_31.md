# v4.31 release notes

Purpose: reduce Stage 3 back-and-forth by fixing the OFF-state local-zero settle gate seen on 2026-07-30.

Changes:
- Treat Pico raw encoder as the primary physical stationarity witness during OFF-state local-zero preparation.
- Treat ViX PA movement during OFF+Z/reset reference refresh as advisory when Pico raw is quiet and ViX PA delta is bounded.
- Preserve the PA/PT/PF/PE zero transaction immediately after the advisory settle window, so stale ViX references are still cleaned before enabling.
- Migrate v4.30 state without erasing validated Stage 2 evidence/seed.
- Keep the v4.30 bidirectional direction diagnostic matrix for DIRINV/STEP-DIR investigation.
