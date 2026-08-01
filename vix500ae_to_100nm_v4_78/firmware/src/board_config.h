#ifndef VIX_BASE_PICO2_BOARD_CONFIG_H
#define VIX_BASE_PICO2_BOARD_CONFIG_H

/*
 * Conservative commissioning pin map.
 * Change only with the drive disabled and update WIRING.md at the same time.
 */
#define FW_VERSION "vix-base-pico2-v2.7"
#define PROTOCOL_REVISION 5
#define COUNTS_PER_MM 100000

#define PIN_STEP          2u
#define PIN_DIR           3u
#define PIN_ENCODER_A     4u
#define PIN_ENCODER_B     5u
#define PIN_ENCODER_Z     6u
#define PIN_LIMIT_POS     7u
#define PIN_LIMIT_NEG     8u
#define PIN_HOME          9u
#define PIN_VIX_FAULT    10u
#define PIN_DRIVE_ENABLE 11u
#define PIN_ESTOP_AUX    12u

/* These defaults cannot arm motion until CONFIRM_INPUTS is explicitly set. */
#define DEFAULT_LIMIT_POS_ACTIVE_LEVEL 1
#define DEFAULT_LIMIT_NEG_ACTIVE_LEVEL 0
#define DEFAULT_HOME_ACTIVE_LEVEL      1
#define DEFAULT_Z_ACTIVE_LEVEL         1
#define DEFAULT_FAULT_ACTIVE_LEVEL     1
#define DEFAULT_HAS_LIMIT_NEG          false

/* X5 limit/home safety inputs are open-collector/noisy in this setup.
 * Require this many consecutive 10 kHz firmware samples before an active
 * level is treated as true. 5 samples = about 0.5 ms. Inactive clears
 * immediately so a released switch is not artificially held active. */
#define X5_INPUT_DEBOUNCE_SAMPLES      5u

#define DEFAULT_ENCODER_SIGN           1
#define DEFAULT_COMMAND_DIR_INVERTED   false
#define DEFAULT_REQUIRE_ESTOP_AUX      true

/* 10 nm/count defaults. The host rewrites these volatile limits each session. */
#define DEFAULT_SOFT_MIN_COUNTS       (-200000)
#define DEFAULT_SOFT_MAX_COUNTS        200000
#define DEFAULT_FOLLOWING_ABORT_COUNTS 5000
#define DEFAULT_HOST_WATCHDOG_MS       750u

#define TRACE_MAX_SAMPLES              4096u
#define TRACE_DEFAULT_PERIOD_US        1000u

/* Guarded stale-fault recovery pulse. The host must also set zero gains and
 * CL=1% before requesting this. Firmware independently bounds both time and
 * encoder displacement while temporarily ignoring only the already-active
 * ViX fault input. */
#define RECOVERY_MIN_MS                 100u
#define RECOVERY_MAX_MS                2000u
#define RECOVERY_MAX_DELTA_COUNTS       5000u

/* Deliberately low commissioning limits. */
#define MIN_STEP_RATE_COUNTS_S 100u
#define MAX_STEP_RATE_COUNTS_S 20000u
#define MAX_ACCEL_COUNTS_S2    1000000u
#define STEP_SEGMENT_COUNTS    16u

#endif
