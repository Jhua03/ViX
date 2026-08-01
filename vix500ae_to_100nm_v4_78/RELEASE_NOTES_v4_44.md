# v4.44

Fixes the v4.43 state migration allow-list so valid v4.42/schema-31 Stage-3 proof state can migrate into the bounded Stage-4 current ladder.

No motion-policy changes versus v4.43:
- Stage-4 temporary `IW=1000`
- Stage-4 temporary `CL` ladder: 2%, 3%, 5%, 8%, 12%, 16%, 20%
- Preserves validated Stage-2 hold seed and Stage-3 coordinate signs.

Adds a self-test regression for schema-31 migration preservation.
