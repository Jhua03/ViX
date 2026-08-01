# v4.45

Fixes guarded stale DF20/DF21 recovery when the Pico is correctly latched by an active physical ViX fault output.

v4.44 called the normal safe Pico ZERO helper inside guarded recovery. That helper clears a USER_ABORT latch before ZERO, but Pico firmware correctly rejects CLEAR while the physical X4 fault input remains active. v4.45 zeroes the Pico directly while disabled/disarmed during the guarded recovery profile, then performs the existing timed low-current ON/OFF recovery and only clears the latch after the ViX fault output has returned healthy.

No commissioning-state schema change.
