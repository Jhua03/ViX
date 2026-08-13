# v4.74

Corrected package manifest/checksum issue from v4.73.  The test logic is the same settled-tail no-motion gain sweep:

- No STEP/DIR commanded moves.
- Enable once, allow bounded zero-gain ON transient.
- Sweep already-energised hold candidates.
- Score settled tail rather than pull-in transient.
- Confirm the best candidate twice before declaring it ready for a later motion proof.
- Auto-zip evidence on completion or safe abort.
