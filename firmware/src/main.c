/*
 * ViX AE/AH base drive + MX80L + Raspberry Pi Pico 2 supervisory controller
 * -------------------------------------------------------------------
 *
 * INTENT
 *   Generate deterministic differential step/direction commands through an
 *   AM26LV31, independently count the ViX encoder-copy through an AM26LV32,
 *   monitor the MX80L limit/home signals and ViX fault output, and expose a
 *   conservative USB serial control protocol for commissioning and nanostep
 *   experiments.
 *
 * SAFETY BOUNDARY
 *   The ViX AE/AH base drive remains the high-bandwidth servo. This firmware does not configure
 *   MOTOR, feedback phasing, PIVF gains, or non-volatile memory. It boots
 *   disarmed and de-energised. A hardware E-stop/HV disconnect is still
 *   mandatory. The current stage has no working negative limit, so the default
 *   policy is a +/-2 mm software window around a manually centred temporary
 *   zero. No automatic homing or full-travel search is implemented.
 */

#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pico/util/queue.h"

#include "board_config.h"
#include "stepgen.pio.h"
#include "quadrature_encoder.pio.h"

#define LINE_BUFFER_SIZE 192u

typedef enum {
    MOTION_IDLE = 0,
    MOTION_MOVING = 1,
    MOTION_ABORTED = 2
} motion_state_t;

typedef enum {
    LATCH_NONE = 0,
    LATCH_ESTOP,
    LATCH_VIX_FAULT,
    LATCH_LIMIT_POS,
    LATCH_LIMIT_NEG,
    LATCH_FOLLOWING_ERROR,
    LATCH_HOST_WATCHDOG,
    LATCH_ENCODER_INVALID,
    LATCH_USER_ABORT,
    LATCH_RECOVERY_TIMEOUT,
    LATCH_INTERNAL
} latch_code_t;

typedef struct {
    int limit_pos_active_level;
    int limit_neg_active_level;
    int home_active_level;
    int z_active_level;
    int fault_active_level;
    bool has_limit_neg;
    int encoder_sign;
    bool command_dir_inverted;
    bool require_estop_aux;
    int32_t soft_min_counts;
    int32_t soft_max_counts;
    int32_t following_abort_counts;
    uint32_t host_watchdog_ms;
    bool inputs_confirmed;
} runtime_config_t;

typedef struct {
    int32_t delta_counts;
    uint32_t max_rate_counts_s;
    uint32_t accel_counts_s2;
    uint32_t move_id;
    uint32_t abort_epoch;
} move_request_t;

typedef struct {
    uint32_t t_us;
    int32_t encoder_position;
    int32_t command_position;
    int32_t following_error;
    uint32_t encoder_invalid;
    uint32_t flags;
} trace_sample_t;

#define TRACE_FLAG_ENABLED      (1u << 0)
#define TRACE_FLAG_ARMED        (1u << 1)
#define TRACE_FLAG_MOVING       (1u << 2)
#define TRACE_FLAG_LIMIT_POS    (1u << 3)
#define TRACE_FLAG_LIMIT_NEG    (1u << 4)
#define TRACE_FLAG_HOME         (1u << 5)
#define TRACE_FLAG_FAULT        (1u << 6)
#define TRACE_FLAG_ESTOP_SAFE   (1u << 7)
#define TRACE_FLAG_LATCHED      (1u << 8)
#define TRACE_FLAG_RECOVERY     (1u << 9)

static runtime_config_t g_cfg = {
    .limit_pos_active_level = DEFAULT_LIMIT_POS_ACTIVE_LEVEL,
    .limit_neg_active_level = DEFAULT_LIMIT_NEG_ACTIVE_LEVEL,
    .home_active_level = DEFAULT_HOME_ACTIVE_LEVEL,
    .z_active_level = DEFAULT_Z_ACTIVE_LEVEL,
    .fault_active_level = DEFAULT_FAULT_ACTIVE_LEVEL,
    .has_limit_neg = DEFAULT_HAS_LIMIT_NEG,
    .encoder_sign = DEFAULT_ENCODER_SIGN,
    .command_dir_inverted = DEFAULT_COMMAND_DIR_INVERTED,
    .require_estop_aux = DEFAULT_REQUIRE_ESTOP_AUX,
    .soft_min_counts = DEFAULT_SOFT_MIN_COUNTS,
    .soft_max_counts = DEFAULT_SOFT_MAX_COUNTS,
    .following_abort_counts = DEFAULT_FOLLOWING_ABORT_COUNTS,
    .host_watchdog_ms = DEFAULT_HOST_WATCHDOG_MS,
    .inputs_confirmed = false,
};

static queue_t g_move_queue;
static PIO g_step_pio = pio0;
static uint g_step_sm = 0;
static uint g_step_offset = 0;

/* PIO1 is dedicated to the high-rate quadrature decoder. The PIO state
 * machine counts continuously without CPU intervention. Core 0 refreshes this
 * cached count at 10 kHz; core 1 only reads the cache for following-error
 * protection, so the RX FIFO is never drained concurrently by both cores. */
static PIO g_encoder_pio = pio1;
static uint g_encoder_sm = 0;
static uint g_encoder_offset = 0;
static volatile int32_t g_encoder_raw = 0;
static volatile uint32_t g_encoder_invalid_transitions = 0;
static volatile uint32_t g_z_edges = 0;
static volatile int32_t g_last_z_raw = 0;

static trace_sample_t g_trace[TRACE_MAX_SAMPLES];
static volatile bool g_trace_active = false;
static volatile bool g_trace_full = false;
static volatile uint32_t g_trace_count = 0;
static volatile uint32_t g_trace_capacity = TRACE_MAX_SAMPLES;
static volatile uint32_t g_trace_period_us = TRACE_DEFAULT_PERIOD_US;
static volatile uint64_t g_trace_start_us = 0;
static volatile uint64_t g_trace_next_us = 0;

static volatile uint64_t g_last_heartbeat_us = 0;

/* X5 limit/home input guard. The MX80L limit/home lines are open-collector and
 * have shown single-sample phantom triggers on this bench. Treat an X5 safety
 * signal as active only after X5_INPUT_DEBOUNCE_SAMPLES consecutive firmware
 * samples at the active level. Samples are taken in the 10 kHz main-loop input
 * refresh. Inactive clears immediately; this is intentional so a released limit
 * is not artificially stretched. */
static volatile uint8_t g_limit_pos_active_streak = 0;
static volatile uint8_t g_limit_neg_active_streak = 0;
static volatile uint8_t g_home_active_streak = 0;
static volatile bool g_limit_pos_debounced = false;
static volatile bool g_limit_neg_debounced = false;
static volatile bool g_home_debounced = false;

static volatile int32_t g_encoder_zero_raw = 0;
static volatile int32_t g_command_position = 0;
static volatile bool g_zeroed = false;
static volatile bool g_armed = false;
static volatile bool g_drive_enabled = false;
static volatile bool g_abort_requested = false;
/* Incremented on every stop/abort request. Queued moves carry the epoch at
 * acceptance so an old queued request can never run after re-arming. */
static volatile uint32_t g_abort_epoch = 0;
static volatile bool g_safety_latched = false;
static volatile latch_code_t g_latch_code = LATCH_NONE;
static volatile motion_state_t g_motion_state = MOTION_IDLE;
static volatile int g_motion_direction = 0;
static volatile uint32_t g_active_move_id = 0;
static volatile uint32_t g_completed_move_id = 0;

/* Dedicated, internally timed stale-fault recovery gate. This is deliberately
 * separate from normal ARM/ENABLE operation: it can assert GP11 while the ViX
 * fault input is already active, but only for a bounded interval and with an
 * independent raw-encoder displacement limit. */
static volatile bool g_recovery_active = false;
static volatile uint64_t g_recovery_started_us = 0;
static volatile uint64_t g_recovery_deadline_us = 0;
static volatile int32_t g_recovery_encoder_start_raw = 0;
static volatile uint32_t g_recovery_invalid_start = 0;
static volatile uint32_t g_recovery_max_abs_delta = 0;
static volatile uint32_t g_recovery_elapsed_ms = 0;
static volatile bool g_recovery_timed_out = false;
static volatile bool g_recovery_fault_cleared = false;
static volatile bool g_recovery_fault_reasserted = false;

static void latch_and_disable(latch_code_t code);
static inline uint32_t magnitude_i32(int32_t value);
static inline uint32_t magnitude_following_error(void);
static void recovery_stop(bool timed_out);

static const char *motion_state_name(motion_state_t state) {
    switch (state) {
        case MOTION_IDLE: return "IDLE";
        case MOTION_MOVING: return "MOVING";
        case MOTION_ABORTED: return "ABORTED";
        default: return "UNKNOWN";
    }
}

static inline void refresh_encoder_count(void) {
    g_encoder_raw = quadrature_encoder_get_count(g_encoder_pio, g_encoder_sm);
}

static const char *latch_name(latch_code_t code) {
    switch (code) {
        case LATCH_NONE: return "NONE";
        case LATCH_ESTOP: return "ESTOP";
        case LATCH_VIX_FAULT: return "VIX_FAULT";
        case LATCH_LIMIT_POS: return "LIMIT_POS";
        case LATCH_LIMIT_NEG: return "LIMIT_NEG";
        case LATCH_FOLLOWING_ERROR: return "FOLLOWING_ERROR";
        case LATCH_HOST_WATCHDOG: return "HOST_WATCHDOG";
        case LATCH_ENCODER_INVALID: return "ENCODER_INVALID";
        case LATCH_USER_ABORT: return "USER_ABORT";
        case LATCH_RECOVERY_TIMEOUT: return "RECOVERY_TIMEOUT";
        case LATCH_INTERNAL: return "INTERNAL";
        default: return "UNKNOWN";
    }
}

static inline bool raw_level(uint pin) {
    return gpio_get(pin) != 0;
}

static inline bool active_level(uint pin, int active) {
    return raw_level(pin) == (active != 0);
}

static inline bool limit_pos_active_raw(void) {
    return active_level(PIN_LIMIT_POS, g_cfg.limit_pos_active_level);
}

static inline bool limit_neg_active_raw(void) {
    return g_cfg.has_limit_neg &&
           active_level(PIN_LIMIT_NEG, g_cfg.limit_neg_active_level);
}

static inline bool home_active_raw(void) {
    return active_level(PIN_HOME, g_cfg.home_active_level);
}

static inline void update_one_x5_debounce(bool raw_active,
                                          volatile uint8_t *streak,
                                          volatile bool *debounced) {
    if (raw_active) {
        if (*streak < X5_INPUT_DEBOUNCE_SAMPLES) {
            *streak = (uint8_t)(*streak + 1u);
        }
        if (*streak >= X5_INPUT_DEBOUNCE_SAMPLES) {
            *debounced = true;
        }
    } else {
        *streak = 0u;
        *debounced = false;
    }
}

static inline void update_x5_debounced_inputs(void) {
    update_one_x5_debounce(
        limit_pos_active_raw(),
        &g_limit_pos_active_streak,
        &g_limit_pos_debounced
    );
    update_one_x5_debounce(
        limit_neg_active_raw(),
        &g_limit_neg_active_streak,
        &g_limit_neg_debounced
    );
    update_one_x5_debounce(
        home_active_raw(),
        &g_home_active_streak,
        &g_home_debounced
    );
}

static inline bool limit_pos_active(void) {
    return g_limit_pos_debounced;
}

static inline bool limit_neg_active(void) {
    return g_cfg.has_limit_neg && g_limit_neg_debounced;
}

static inline bool home_active(void) {
    return g_home_debounced;
}

static inline bool z_active(void) {
    return active_level(PIN_ENCODER_Z, g_cfg.z_active_level);
}

static inline bool vix_fault_active(void) {
    return active_level(PIN_VIX_FAULT, g_cfg.fault_active_level);
}

static inline bool estop_safe(void) {
    if (!g_cfg.require_estop_aux) {
        return true;
    }
    /* NC auxiliary contact: closed -> raw low -> safe. */
    return !raw_level(PIN_ESTOP_AUX);
}

static inline int32_t encoder_position(void) {
    const int32_t delta = g_encoder_raw - g_encoder_zero_raw;
    return (g_cfg.encoder_sign >= 0) ? delta : -delta;
}

static inline int32_t following_error(void) {
    return g_command_position - encoder_position();
}

static uint32_t trace_flags(void) {
    uint32_t flags = 0u;
    if (g_drive_enabled) flags |= TRACE_FLAG_ENABLED;
    if (g_armed) flags |= TRACE_FLAG_ARMED;
    if (g_motion_state == MOTION_MOVING) flags |= TRACE_FLAG_MOVING;
    if (limit_pos_active()) flags |= TRACE_FLAG_LIMIT_POS;
    if (limit_neg_active()) flags |= TRACE_FLAG_LIMIT_NEG;
    if (home_active()) flags |= TRACE_FLAG_HOME;
    if (vix_fault_active()) flags |= TRACE_FLAG_FAULT;
    if (estop_safe()) flags |= TRACE_FLAG_ESTOP_SAFE;
    if (g_safety_latched) flags |= TRACE_FLAG_LATCHED;
    if (g_recovery_active) flags |= TRACE_FLAG_RECOVERY;
    return flags;
}

static void trace_sample_if_due(uint64_t now_us) {
    if (!g_trace_active || now_us < g_trace_next_us) {
        return;
    }
    refresh_encoder_count();
    if (g_trace_count >= g_trace_capacity || g_trace_count >= TRACE_MAX_SAMPLES) {
        g_trace_active = false;
        g_trace_full = true;
        return;
    }
    trace_sample_t *sample = &g_trace[g_trace_count++];
    sample->t_us = (uint32_t)(now_us - g_trace_start_us);
    sample->encoder_position = encoder_position();
    sample->command_position = g_command_position;
    sample->following_error = following_error();
    sample->encoder_invalid = g_encoder_invalid_transitions;
    sample->flags = trace_flags();
    g_trace_next_us += g_trace_period_us;
    if (now_us > g_trace_next_us + (uint64_t)g_trace_period_us * 4u) {
        g_trace_next_us = now_us + g_trace_period_us;
    }
}

static void continuous_enabled_safety(uint64_t now_us) {
    if (!g_drive_enabled) {
        return;
    }

    if (g_recovery_active) {
        /* The pre-existing ViX fault is the only condition temporarily
         * tolerated. Once the X4 fault output has returned healthy, any
         * reassertion is a new fault and immediately drops GP11. */
        if (!estop_safe()) {
            latch_and_disable(LATCH_ESTOP);
            return;
        }
        if (limit_pos_active()) {
            latch_and_disable(LATCH_LIMIT_POS);
            return;
        }
        if (limit_neg_active()) {
            latch_and_disable(LATCH_LIMIT_NEG);
            return;
        }
        if (g_encoder_invalid_transitions != g_recovery_invalid_start) {
            latch_and_disable(LATCH_ENCODER_INVALID);
            return;
        }

        if (vix_fault_active()) {
            if (g_recovery_fault_cleared) {
                g_recovery_fault_reasserted = true;
                latch_and_disable(LATCH_VIX_FAULT);
                return;
            }
        } else {
            g_recovery_fault_cleared = true;
        }

        const uint32_t delta = magnitude_i32(
            g_encoder_raw - g_recovery_encoder_start_raw
        );
        if (delta > g_recovery_max_abs_delta) {
            g_recovery_max_abs_delta = delta;
        }
        if (delta > RECOVERY_MAX_DELTA_COUNTS) {
            latch_and_disable(LATCH_FOLLOWING_ERROR);
            return;
        }

        const uint64_t watchdog_us =
            (uint64_t)g_cfg.host_watchdog_ms * 1000u;
        if (watchdog_us > 0u &&
            now_us - g_last_heartbeat_us > watchdog_us) {
            latch_and_disable(LATCH_HOST_WATCHDOG);
            return;
        }
        if (now_us >= g_recovery_deadline_us) {
            recovery_stop(true);
        }
        return;
    }

    if (!estop_safe()) {
        latch_and_disable(LATCH_ESTOP);
        return;
    }
    if (vix_fault_active()) {
        latch_and_disable(LATCH_VIX_FAULT);
        return;
    }
    if (limit_pos_active()) {
        latch_and_disable(LATCH_LIMIT_POS);
        return;
    }
    if (limit_neg_active()) {
        latch_and_disable(LATCH_LIMIT_NEG);
        return;
    }
    if (g_zeroed && magnitude_following_error() > (uint32_t)g_cfg.following_abort_counts) {
        latch_and_disable(LATCH_FOLLOWING_ERROR);
        return;
    }
    const uint64_t watchdog_us = (uint64_t)g_cfg.host_watchdog_ms * 1000u;
    if (watchdog_us > 0u && now_us - g_last_heartbeat_us > watchdog_us) {
        latch_and_disable(LATCH_HOST_WATCHDOG);
    }
}

static void encoder_pio_irq_handler(void) {
    if (pio_interrupt_get(g_encoder_pio, 1u)) {
        pio_interrupt_clear(g_encoder_pio, 1u);
        g_encoder_invalid_transitions++;
        if (g_drive_enabled) {
            latch_and_disable(LATCH_ENCODER_INVALID);
        }
    }
}

static void drive_output_set(bool enable) {
    gpio_put(PIN_DRIVE_ENABLE, enable ? 1 : 0);
    g_drive_enabled = enable;
}

static void recovery_stop(bool timed_out) {
    if (g_recovery_active && g_recovery_started_us != 0u) {
        g_recovery_elapsed_ms = (uint32_t)(
            (time_us_64() - g_recovery_started_us) / 1000u
        );
    }
    drive_output_set(false);
    g_recovery_active = false;
    if (timed_out) {
        g_recovery_timed_out = true;
        g_safety_latched = true;
        g_latch_code = LATCH_RECOVERY_TIMEOUT;
    }
}

static void pio_abort_burst(void) {
    pio_sm_set_enabled(g_step_pio, g_step_sm, false);
    pio_sm_clear_fifos(g_step_pio, g_step_sm);
    pio_interrupt_clear(g_step_pio, 0);
    pio_sm_restart(g_step_pio, g_step_sm);
    /* Re-initialise the program counter at the pull instruction. Merely
     * restarting the SM can leave the PC in the pulse loop after an abort. */
    stepgen_program_init(
        g_step_pio, g_step_sm, g_step_offset, PIN_STEP
    );
}

static void request_abort(bool invalidate_zero_if_moving) {
    g_abort_epoch++;
    g_abort_requested = true;
    if (invalidate_zero_if_moving && g_motion_state == MOTION_MOVING) {
        /* A PIO segment can be stopped between pulses, so the exact number of
         * emitted counts is not reconstructable. Require a fresh ZERO. */
        g_zeroed = false;
    }
}

static void latch_and_disable(latch_code_t code) {
    request_abort(true);
    g_safety_latched = true;
    g_latch_code = code;
    recovery_stop(false);
}

static void gpio_irq_callback(uint gpio, uint32_t events) {
    (void)events;

    if (gpio == PIN_ENCODER_Z) {
        g_z_edges++;
        g_last_z_raw = g_encoder_raw;
        return;
    }

    if (gpio == PIN_VIX_FAULT && vix_fault_active() && !g_recovery_active) {
        latch_and_disable(LATCH_VIX_FAULT);
        return;
    }

    if (gpio == PIN_ESTOP_AUX && !estop_safe()) {
        latch_and_disable(LATCH_ESTOP);
        return;
    }

    if (gpio == PIN_LIMIT_POS && limit_pos_active() && g_motion_direction > 0) {
        latch_and_disable(LATCH_LIMIT_POS);
        return;
    }

    if (gpio == PIN_LIMIT_NEG && limit_neg_active() && g_motion_direction < 0) {
        latch_and_disable(LATCH_LIMIT_NEG);
    }
}

static inline uint32_t magnitude_i32(int32_t value) {
    return value < 0 ? (uint32_t)(-(int64_t)value) : (uint32_t)value;
}

static inline uint32_t magnitude_following_error(void) {
    const int64_t value = (int64_t)following_error();
    return (uint32_t)(value < 0 ? -value : value);
}

static uint64_t isqrt_u64(uint64_t value) {
    uint64_t result = 0;
    uint64_t bit = (uint64_t)1 << 62;
    while (bit > value) {
        bit >>= 2;
    }
    while (bit != 0) {
        if (value >= result + bit) {
            value -= result + bit;
            result = (result >> 1) + bit;
        } else {
            result >>= 1;
        }
        bit >>= 2;
    }
    return result;
}

static uint32_t profile_rate(const move_request_t *request,
                             uint32_t completed,
                             uint32_t remaining) {
    const uint64_t v0_sq = (uint64_t)MIN_STEP_RATE_COUNTS_S *
                           (uint64_t)MIN_STEP_RATE_COUNTS_S;
    const uint64_t accel_up_sq = v0_sq +
        2ull * request->accel_counts_s2 * completed;
    const uint64_t decel_down_sq = v0_sq +
        2ull * request->accel_counts_s2 * remaining;

    uint32_t rate_up = (uint32_t)isqrt_u64(accel_up_sq);
    uint32_t rate_down = (uint32_t)isqrt_u64(decel_down_sq);
    uint32_t rate = request->max_rate_counts_s;
    if (rate_up < rate) rate = rate_up;
    if (rate_down < rate) rate = rate_down;
    if (rate < MIN_STEP_RATE_COUNTS_S) rate = MIN_STEP_RATE_COUNTS_S;
    if (rate > MAX_STEP_RATE_COUNTS_S) rate = MAX_STEP_RATE_COUNTS_S;
    return rate;
}

static bool move_safety_ok(int direction) {
    if (g_abort_requested || !g_armed || !g_drive_enabled) {
        return false;
    }
    if (!estop_safe()) {
        latch_and_disable(LATCH_ESTOP);
        return false;
    }
    if (vix_fault_active()) {
        latch_and_disable(LATCH_VIX_FAULT);
        return false;
    }
    if (direction > 0 && limit_pos_active()) {
        latch_and_disable(LATCH_LIMIT_POS);
        return false;
    }
    if (direction < 0 && limit_neg_active()) {
        latch_and_disable(LATCH_LIMIT_NEG);
        return false;
    }
    if (magnitude_following_error() > (uint32_t)g_cfg.following_abort_counts) {
        latch_and_disable(LATCH_FOLLOWING_ERROR);
        return false;
    }
    return true;
}

static bool run_pulse_segment(uint32_t pulse_count, uint32_t rate_counts_s) {
    if (pulse_count == 0u) {
        return true;
    }

    const uint32_t sys_hz = clock_get_hz(clk_sys);
    const float divider = (float)sys_hz /
                          (33.0f * (float)rate_counts_s);
    if (!(divider >= 1.0f && divider < 65536.0f)) {
        latch_and_disable(LATCH_INTERNAL);
        return false;
    }
    pio_sm_set_clkdiv(g_step_pio, g_step_sm, divider);
    pio_interrupt_clear(g_step_pio, 0);
    pio_sm_put_blocking(g_step_pio, g_step_sm, pulse_count - 1u);

    while (!pio_interrupt_get(g_step_pio, 0)) {
        if (g_abort_requested) {
            pio_abort_burst();
            return false;
        }
        tight_loop_contents();
    }
    pio_interrupt_clear(g_step_pio, 0);
    return true;
}

static void execute_move(const move_request_t *request) {
    const int direction = request->delta_counts > 0 ? +1 : -1;
    uint32_t total = magnitude_i32(request->delta_counts);
    uint32_t remaining = total;
    uint32_t completed = 0;

    g_active_move_id = request->move_id;
    if (request->abort_epoch != g_abort_epoch || g_abort_requested ||
        !g_armed || !g_drive_enabled) {
        g_motion_state = MOTION_ABORTED;
        g_motion_direction = 0;
        g_completed_move_id = request->move_id;
        return;
    }
    g_motion_state = MOTION_MOVING;
    g_motion_direction = direction;

    const bool physical_positive =
        (direction > 0) != g_cfg.command_dir_inverted;
    gpio_put(PIN_DIR, physical_positive ? 1 : 0);
    sleep_us(10);

    while (remaining > 0u) {
        if (!move_safety_ok(direction)) {
            g_motion_state = MOTION_ABORTED;
            break;
        }

        const uint32_t segment =
            remaining < STEP_SEGMENT_COUNTS ? remaining : STEP_SEGMENT_COUNTS;
        const uint32_t rate = profile_rate(request, completed, remaining);
        if (!run_pulse_segment(segment, rate)) {
            if (!g_safety_latched) {
                g_latch_code = LATCH_USER_ABORT;
            }
            g_motion_state = MOTION_ABORTED;
            break;
        }

        g_command_position += direction * (int32_t)segment;
        completed += segment;
        remaining -= segment;
    }

    g_motion_direction = 0;
    g_completed_move_id = request->move_id;
    if (g_motion_state == MOTION_MOVING) {
        g_motion_state = MOTION_IDLE;
    } else {
        /* Partial PIO segments make the old logical zero untrustworthy. */
        g_zeroed = false;
    }
}

static void core1_entry(void) {
    move_request_t request;
    while (true) {
        queue_remove_blocking(&g_move_queue, &request);
        execute_move(&request);
    }
}

static void print_config_json(void) {
    printf("{\"ok\":true,\"cmd\":\"CONFIG\","
           "\"limit_pos_active_level\":%d,"
           "\"limit_neg_active_level\":%d,"
           "\"home_active_level\":%d,"
           "\"z_active_level\":%d,"
           "\"fault_active_level\":%d,"
           "\"has_limit_neg\":%s,"
           "\"encoder_sign\":%d,"
           "\"command_dir_inverted\":%s,"
           "\"require_estop_aux\":%s,"
           "\"soft_min_counts\":%" PRId32 ","
           "\"soft_max_counts\":%" PRId32 ","
           "\"following_abort_counts\":%" PRId32 ","
           "\"host_watchdog_ms\":%" PRIu32 ","
           "\"x5_debounce_samples\":%u,"
           "\"inputs_confirmed\":%s}\n",
           g_cfg.limit_pos_active_level,
           g_cfg.limit_neg_active_level,
           g_cfg.home_active_level,
           g_cfg.z_active_level,
           g_cfg.fault_active_level,
           g_cfg.has_limit_neg ? "true" : "false",
           g_cfg.encoder_sign,
           g_cfg.command_dir_inverted ? "true" : "false",
           g_cfg.require_estop_aux ? "true" : "false",
           g_cfg.soft_min_counts,
           g_cfg.soft_max_counts,
           g_cfg.following_abort_counts,
           g_cfg.host_watchdog_ms,
           X5_INPUT_DEBOUNCE_SAMPLES,
           g_cfg.inputs_confirmed ? "true" : "false");
}

static void print_status_json(void) {
    refresh_encoder_count();
    const uint64_t now_us = time_us_64();
    const uint64_t recovery_elapsed_ms = g_recovery_active
        ? (now_us - g_recovery_started_us) / 1000u
        : g_recovery_elapsed_ms;
    const uint64_t recovery_remaining_ms =
        g_recovery_active && g_recovery_deadline_us > now_us
        ? (g_recovery_deadline_us - now_us) / 1000u : 0u;
    printf("{\"ok\":true,\"cmd\":\"STATUS\","
           "\"fw\":\"%s\","
           "\"motion\":\"%s\","
           "\"armed\":%s,\"enabled\":%s,\"zeroed\":%s,"
           "\"latched\":%s,\"latch\":\"%s\","
           "\"encoder_raw\":%" PRId32 ","
           "\"encoder_position\":%" PRId32 ","
           "\"command_position\":%" PRId32 ","
           "\"following_error\":%" PRId32 ","
           "\"move_active_id\":%" PRIu32 ","
           "\"move_completed_id\":%" PRIu32 ","
           "\"z_edges\":%" PRIu32 ",\"last_z_raw\":%" PRId32 ","
           "\"encoder_invalid\":%" PRIu32 ","
           "\"host_watchdog_ms\":%" PRIu32 ","
           "\"x5_debounce_samples\":%u,"
           "\"heartbeat_age_ms\":%" PRIu64 ","
           "\"trace_active\":%s,\"trace_count\":%" PRIu32 ","
           "\"trace_full\":%s,"
           "\"recovery_active\":%s,"
           "\"recovery_timed_out\":%s,"
           "\"recovery_fault_cleared\":%s,"
           "\"recovery_fault_reasserted\":%s,"
           "\"recovery_elapsed_ms\":%" PRIu64 ","
           "\"recovery_remaining_ms\":%" PRIu64 ","
           "\"recovery_max_abs_delta\":%" PRIu32 ","
           "\"raw_limit_pos\":%d,\"raw_limit_neg\":%d,"
           "\"raw_home\":%d,\"raw_z\":%d,"
           "\"raw_fault\":%d,\"raw_estop\":%d,"
           "\"limit_pos_raw_active\":%s,\"limit_neg_raw_active\":%s,"
           "\"home_raw_active\":%s,"
           "\"limit_pos_streak\":%u,\"limit_neg_streak\":%u,"
           "\"home_streak\":%u,"
           "\"limit_pos_active\":%s,\"limit_neg_active\":%s,"
           "\"home_active\":%s,\"z_active\":%s,"
           "\"fault_active\":%s,\"estop_safe\":%s}\n",
           FW_VERSION,
           motion_state_name(g_motion_state),
           g_armed ? "true" : "false",
           g_drive_enabled ? "true" : "false",
           g_zeroed ? "true" : "false",
           g_safety_latched ? "true" : "false",
           latch_name(g_latch_code),
           g_encoder_raw,
           encoder_position(),
           g_command_position,
           following_error(),
           g_active_move_id,
           g_completed_move_id,
           g_z_edges,
           g_last_z_raw,
           g_encoder_invalid_transitions,
           g_cfg.host_watchdog_ms,
           X5_INPUT_DEBOUNCE_SAMPLES,
           (time_us_64() - g_last_heartbeat_us) / 1000u,
           g_trace_active ? "true" : "false",
           g_trace_count,
           g_trace_full ? "true" : "false",
           g_recovery_active ? "true" : "false",
           g_recovery_timed_out ? "true" : "false",
           g_recovery_fault_cleared ? "true" : "false",
           g_recovery_fault_reasserted ? "true" : "false",
           recovery_elapsed_ms,
           recovery_remaining_ms,
           g_recovery_max_abs_delta,
           raw_level(PIN_LIMIT_POS),
           raw_level(PIN_LIMIT_NEG),
           raw_level(PIN_HOME),
           raw_level(PIN_ENCODER_Z),
           raw_level(PIN_VIX_FAULT),
           raw_level(PIN_ESTOP_AUX),
           limit_pos_active_raw() ? "true" : "false",
           limit_neg_active_raw() ? "true" : "false",
           home_active_raw() ? "true" : "false",
           (unsigned)g_limit_pos_active_streak,
           (unsigned)g_limit_neg_active_streak,
           (unsigned)g_home_active_streak,
           limit_pos_active() ? "true" : "false",
           limit_neg_active() ? "true" : "false",
           home_active() ? "true" : "false",
           z_active() ? "true" : "false",
           vix_fault_active() ? "true" : "false",
           estop_safe() ? "true" : "false");
}

static void reply_error(const char *cmd, const char *reason) {
    printf("{\"ok\":false,\"cmd\":\"%s\",\"error\":\"%s\"}\n",
           cmd, reason);
}

static bool parse_bool_int(const char *text, bool *value) {
    if (strcmp(text, "0") == 0) {
        *value = false;
        return true;
    }
    if (strcmp(text, "1") == 0) {
        *value = true;
        return true;
    }
    return false;
}

static void handle_config(char *line) {
    char key[32];
    char value[32];
    if (strcmp(line, "CONFIG SHOW") == 0) {
        print_config_json();
        return;
    }
    if (sscanf(line, "CONFIG %31s %31s", key, value) != 2) {
        reply_error("CONFIG", "use CONFIG SHOW or CONFIG <key> <value>");
        return;
    }
    if (g_armed || g_drive_enabled || g_motion_state == MOTION_MOVING) {
        reply_error("CONFIG", "disarm and disable before configuration");
        return;
    }

    runtime_config_t next = g_cfg;
    bool b = false;
    char *endptr = NULL;
    long v = strtol(value, &endptr, 10);
    if (endptr == value || *endptr != '\0') {
        reply_error("CONFIG", "value must be an integer");
        return;
    }

    if (strcmp(key, "LPOL") == 0 && (v == 0 || v == 1)) {
        next.limit_pos_active_level = (int)v;
    } else if (strcmp(key, "LNPOL") == 0 && (v == 0 || v == 1)) {
        next.limit_neg_active_level = (int)v;
    } else if (strcmp(key, "HPOL") == 0 && (v == 0 || v == 1)) {
        next.home_active_level = (int)v;
    } else if (strcmp(key, "ZPOL") == 0 && (v == 0 || v == 1)) {
        next.z_active_level = (int)v;
    } else if (strcmp(key, "FPOL") == 0 && (v == 0 || v == 1)) {
        next.fault_active_level = (int)v;
    } else if (strcmp(key, "HAS_LN") == 0 && parse_bool_int(value, &b)) {
        next.has_limit_neg = b;
    } else if (strcmp(key, "DIRINV") == 0 && parse_bool_int(value, &b)) {
        next.command_dir_inverted = b;
    } else if (strcmp(key, "ENCSIGN") == 0 && (v == -1 || v == 1)) {
        next.encoder_sign = (int)v;
    } else if (strcmp(key, "ESTOPREQ") == 0 && parse_bool_int(value, &b)) {
        next.require_estop_aux = b;
    } else if (strcmp(key, "SOFTMIN") == 0 && v >= INT32_MIN && v <= INT32_MAX) {
        next.soft_min_counts = (int32_t)v;
    } else if (strcmp(key, "SOFTMAX") == 0 && v >= INT32_MIN && v <= INT32_MAX) {
        next.soft_max_counts = (int32_t)v;
    } else if (strcmp(key, "FERRMAX") == 0 && v >= 100 && v <= 1000000) {
        next.following_abort_counts = (int32_t)v;
    } else if (strcmp(key, "WATCHDOG_MS") == 0 && v >= 250 && v <= 5000) {
        next.host_watchdog_ms = (uint32_t)v;
    } else if (strcmp(key, "CONFIRM_INPUTS") == 0 && parse_bool_int(value, &b)) {
        next.inputs_confirmed = b;
    } else {
        reply_error("CONFIG", "unknown key or invalid value");
        return;
    }

    if (next.soft_min_counts >= next.soft_max_counts) {
        reply_error("CONFIG", "soft minimum must be below soft maximum");
        return;
    }
    g_cfg = next;
    print_config_json();
}

static void handle_line(char *line) {
    while (*line == ' ' || *line == '\t') line++;
    const size_t len = strlen(line);
    while (len > 0 && (line[strlen(line) - 1] == ' ' ||
                       line[strlen(line) - 1] == '\t')) {
        line[strlen(line) - 1] = '\0';
    }

    if (strcmp(line, "HB") == 0) {
        g_last_heartbeat_us = time_us_64();
        printf("{\"ok\":true,\"cmd\":\"HB\"}\n");
        return;
    }
    if (strncmp(line, "TRACE", 5) == 0) {
        if (strcmp(line, "TRACE INFO") == 0) {
            printf("{\"ok\":true,\"cmd\":\"TRACE INFO\","
                   "\"active\":%s,\"full\":%s,"
                   "\"count\":%" PRIu32 ",\"capacity\":%" PRIu32 ","
                   "\"period_us\":%" PRIu32 "}\n",
                   g_trace_active ? "true" : "false",
                   g_trace_full ? "true" : "false",
                   g_trace_count, g_trace_capacity, g_trace_period_us);
            return;
        }
        if (strcmp(line, "TRACE STOP") == 0) {
            g_trace_active = false;
            printf("{\"ok\":true,\"cmd\":\"TRACE STOP\","
                   "\"count\":%" PRIu32 "}\n", g_trace_count);
            return;
        }
        if (strcmp(line, "TRACE CLEAR") == 0) {
            if (g_trace_active || g_drive_enabled || g_motion_state == MOTION_MOVING) {
                reply_error("TRACE CLEAR", "stop trace and disable first");
                return;
            }
            g_trace_count = 0;
            g_trace_full = false;
            printf("{\"ok\":true,\"cmd\":\"TRACE CLEAR\"}\n");
            return;
        }
        unsigned long period_us = 0;
        unsigned long capacity = 0;
        if (sscanf(line, "TRACE START %lu %lu", &period_us, &capacity) == 2) {
            if (g_trace_active || g_motion_state == MOTION_MOVING) {
                reply_error("TRACE START", "trace or motion already active");
                return;
            }
            if (period_us < 250u || period_us > 100000u ||
                capacity < 10u || capacity > TRACE_MAX_SAMPLES) {
                reply_error("TRACE START", "period 250..100000 us, samples 10..4096");
                return;
            }
            g_trace_period_us = (uint32_t)period_us;
            g_trace_capacity = (uint32_t)capacity;
            g_trace_count = 0;
            g_trace_full = false;
            g_trace_start_us = time_us_64();
            g_trace_next_us = g_trace_start_us;
            g_trace_active = true;
            printf("{\"ok\":true,\"cmd\":\"TRACE START\","
                   "\"period_us\":%lu,\"capacity\":%lu}\n",
                   period_us, capacity);
            return;
        }
        if (strcmp(line, "TRACE DUMP") == 0) {
            if (g_trace_active || g_drive_enabled || g_motion_state == MOTION_MOVING) {
                reply_error("TRACE DUMP", "stop trace and disable first");
                return;
            }
            printf("{\"event\":\"TRACE_BEGIN\",\"count\":%" PRIu32 "}\n",
                   g_trace_count);
            for (uint32_t i = 0; i < g_trace_count; ++i) {
                const trace_sample_t *sample = &g_trace[i];
                printf("{\"trace\":true,\"i\":%" PRIu32 ","
                       "\"t_us\":%" PRIu32 ",\"enc\":%" PRId32 ","
                       "\"cmd_pos\":%" PRId32 ",\"ferr\":%" PRId32 ","
                       "\"invalid\":%" PRIu32 ",\"flags\":%" PRIu32 "}\n",
                       i, sample->t_us, sample->encoder_position,
                       sample->command_position, sample->following_error,
                       sample->encoder_invalid, sample->flags);
            }
            printf("{\"event\":\"TRACE_END\",\"count\":%" PRIu32 "}\n",
                   g_trace_count);
            return;
        }
        reply_error("TRACE", "use INFO, START <period_us> <samples>, STOP, CLEAR, DUMP");
        return;
    }
    if (strcmp(line, "DIAG CLEAR") == 0) {
        if (g_drive_enabled || g_motion_state == MOTION_MOVING) {
            reply_error("DIAG CLEAR", "disable and stop first");
            return;
        }
        g_encoder_invalid_transitions = 0;
        g_z_edges = 0;
        g_limit_pos_active_streak = 0;
        g_limit_neg_active_streak = 0;
        g_home_active_streak = 0;
        g_limit_pos_debounced = false;
        g_limit_neg_debounced = false;
        g_home_debounced = false;
        printf("{\"ok\":true,\"cmd\":\"DIAG CLEAR\"}\n");
        return;
    }
    if (strcmp(line, "PING") == 0) {
        printf("{\"ok\":true,\"cmd\":\"PING\",\"reply\":\"PONG\",\"fw\":\"%s\"}\n",
               FW_VERSION);
        return;
    }
    if (strcmp(line, "INFO") == 0) {
        printf("{\"ok\":true,\"cmd\":\"INFO\",\"fw\":\"%s\","
               "\"protocol\":%d,\"board\":\"pico2\",\"counts_per_mm\":%d,"
               "\"guarded_recovery\":true,"
               "\"recovery_min_ms\":%u,\"recovery_max_ms\":%u,"
               "\"recovery_max_delta_counts\":%u,"
               "\"x5_debounce_samples\":%u,"
               "\"pins\":{\"step\":%u,\"dir\":%u,\"enc_a\":%u,"
               "\"enc_b\":%u,\"enc_z\":%u,\"lim_pos\":%u,"
               "\"lim_neg\":%u,\"home\":%u,\"fault\":%u,"
               "\"enable\":%u,\"estop\":%u}}\n",
               FW_VERSION, PROTOCOL_REVISION, COUNTS_PER_MM,
               RECOVERY_MIN_MS, RECOVERY_MAX_MS,
               RECOVERY_MAX_DELTA_COUNTS, X5_INPUT_DEBOUNCE_SAMPLES,
               PIN_STEP, PIN_DIR, PIN_ENCODER_A, PIN_ENCODER_B,
               PIN_ENCODER_Z, PIN_LIMIT_POS, PIN_LIMIT_NEG, PIN_HOME,
               PIN_VIX_FAULT, PIN_DRIVE_ENABLE, PIN_ESTOP_AUX);
        return;
    }
    if (strcmp(line, "STATUS") == 0 || strcmp(line, "RAW") == 0) {
        print_status_json();
        return;
    }
    if (strncmp(line, "RECOVER", 7) == 0) {
        if (strcmp(line, "RECOVER STOP") == 0) {
            recovery_stop(false);
            printf("{\"ok\":true,\"cmd\":\"RECOVER STOP\","
                   "\"enabled\":false,\"recovery_active\":false,"
                   "\"timed_out\":%s,"
                   "\"fault_cleared\":%s,"
                   "\"fault_reasserted\":%s,"
                   "\"max_abs_delta\":%" PRIu32 "}\n",
                   g_recovery_timed_out ? "true" : "false",
                   g_recovery_fault_cleared ? "true" : "false",
                   g_recovery_fault_reasserted ? "true" : "false",
                   g_recovery_max_abs_delta);
            return;
        }

        unsigned long duration_ms = 0;
        char acknowledgement[32] = {0};
        if (sscanf(line, "RECOVER START %lu %31s",
                   &duration_ms, acknowledgement) != 2 ||
            strcmp(acknowledgement, "I_UNDERSTAND") != 0) {
            reply_error(
                "RECOVER",
                "use RECOVER START <100..2000 ms> I_UNDERSTAND or RECOVER STOP"
            );
            return;
        }
        if (duration_ms < RECOVERY_MIN_MS || duration_ms > RECOVERY_MAX_MS) {
            reply_error("RECOVER", "duration outside guarded recovery range");
            return;
        }
        if (g_recovery_active || g_drive_enabled || g_armed ||
            g_motion_state == MOTION_MOVING) {
            reply_error("RECOVER", "must be stopped, disarmed and disabled");
            return;
        }
        if (!g_cfg.inputs_confirmed) {
            reply_error("RECOVER", "confirmed input polarity policy is required");
            return;
        }
        if (!estop_safe()) {
            reply_error("RECOVER", "E-stop auxiliary condition is unsafe");
            return;
        }
        if (limit_pos_active() || limit_neg_active()) {
            reply_error("RECOVER", "start away from active limits");
            return;
        }
        if (!vix_fault_active()) {
            reply_error("RECOVER", "ViX fault input is not active; recovery not needed");
            return;
        }
        const uint64_t recovery_watchdog_us =
            (uint64_t)g_cfg.host_watchdog_ms * 1000u;
        const uint64_t recovery_now_us = time_us_64();
        if (recovery_watchdog_us > 0u &&
            recovery_now_us - g_last_heartbeat_us > recovery_watchdog_us) {
            reply_error("RECOVER", "fresh host heartbeat is required");
            return;
        }
        if (g_safety_latched && g_latch_code != LATCH_VIX_FAULT &&
            g_latch_code != LATCH_USER_ABORT) {
            reply_error("RECOVER", "non-ViX safety latch blocks recovery");
            return;
        }

        request_abort(true);
        g_armed = false;
        refresh_encoder_count();
        g_recovery_encoder_start_raw = g_encoder_raw;
        g_recovery_invalid_start = g_encoder_invalid_transitions;
        g_recovery_max_abs_delta = 0u;
        g_recovery_elapsed_ms = 0u;
        g_recovery_timed_out = false;
        g_recovery_fault_cleared = false;
        g_recovery_fault_reasserted = false;
        g_recovery_started_us = time_us_64();
        g_recovery_deadline_us =
            g_recovery_started_us + (uint64_t)duration_ms * 1000u;
        g_recovery_active = true;
        drive_output_set(true);
        printf("{\"ok\":true,\"cmd\":\"RECOVER START\","
               "\"enabled\":true,\"recovery_active\":true,"
               "\"duration_ms\":%lu,\"max_delta_counts\":%u}\n",
               duration_ms, RECOVERY_MAX_DELTA_COUNTS);
        return;
    }
    if (strncmp(line, "CONFIG", 6) == 0) {
        handle_config(line);
        return;
    }
    if (strcmp(line, "CLEAR") == 0) {
        if (g_drive_enabled || g_motion_state == MOTION_MOVING) {
            reply_error("CLEAR", "disable and stop motion first");
            return;
        }
        if (!estop_safe() || vix_fault_active()) {
            reply_error("CLEAR", "physical fault or E-stop condition remains");
            return;
        }
        g_safety_latched = false;
        g_latch_code = LATCH_NONE;
        g_abort_requested = false;
        g_motion_state = MOTION_IDLE;
        g_encoder_invalid_transitions = 0;
        printf("{\"ok\":true,\"cmd\":\"CLEAR\"}\n");
        return;
    }
    if (strcmp(line, "ZERO") == 0) {
        if (g_drive_enabled || g_motion_state == MOTION_MOVING || g_armed) {
            reply_error("ZERO", "disable and disarm before zeroing");
            return;
        }
        refresh_encoder_count();
        g_encoder_zero_raw = g_encoder_raw;
        g_command_position = 0;
        g_zeroed = true;
        g_motion_state = MOTION_IDLE;
        printf("{\"ok\":true,\"cmd\":\"ZERO\",\"encoder_zero_raw\":%" PRId32 "}\n",
               g_encoder_zero_raw);
        return;
    }
    if (strcmp(line, "ARM I_UNDERSTAND") == 0) {
        if (!g_zeroed || !g_cfg.inputs_confirmed) {
            reply_error("ARM", "ZERO and confirmed input polarities are required");
            return;
        }
        if (g_motion_state == MOTION_MOVING) {
            reply_error("ARM", "motion is still stopping");
            return;
        }
        if (g_safety_latched || vix_fault_active() || !estop_safe()) {
            reply_error("ARM", "clear safety condition first");
            return;
        }
        if (limit_pos_active() || limit_neg_active()) {
            reply_error("ARM", "start away from active limits");
            return;
        }
        g_armed = true;
        printf("{\"ok\":true,\"cmd\":\"ARM\",\"armed\":true}\n");
        return;
    }
    if (strcmp(line, "DISARM") == 0) {
        request_abort(true);
        recovery_stop(false);
        g_armed = false;
        printf("{\"ok\":true,\"cmd\":\"DISARM\",\"armed\":false}\n");
        return;
    }
    if (strncmp(line, "ENABLE ", 7) == 0) {
        int enable = -1;
        if (sscanf(line, "ENABLE %d", &enable) != 1 ||
            (enable != 0 && enable != 1)) {
            reply_error("ENABLE", "use ENABLE 0 or ENABLE 1");
            return;
        }
        if (enable == 0) {
            request_abort(true);
            recovery_stop(false);
            printf("{\"ok\":true,\"cmd\":\"ENABLE\",\"enabled\":false}\n");
            return;
        }
        if (!g_armed || g_safety_latched || !g_zeroed ||
            g_motion_state == MOTION_MOVING ||
            !estop_safe() || vix_fault_active()) {
            reply_error("ENABLE", "not armed or safety condition is unsafe");
            return;
        }
        g_abort_requested = false;
        g_last_heartbeat_us = time_us_64();
        drive_output_set(true);
        printf("{\"ok\":true,\"cmd\":\"ENABLE\",\"enabled\":true}\n");
        return;
    }
    if (strcmp(line, "ABORT") == 0) {
        request_abort(true);
        g_latch_code = LATCH_USER_ABORT;
        recovery_stop(false);
        g_armed = false;
        printf("{\"ok\":true,\"cmd\":\"ABORT\","
               "\"enabled\":false,\"armed\":false}\n");
        return;
    }
    if (strncmp(line, "MOVE ", 5) == 0) {
        long long delta = 0;
        unsigned long long rate = 0;
        unsigned long long accel = 0;
        unsigned long long move_id = 0;
        if (sscanf(line, "MOVE %lld %llu %llu %llu",
                   &delta, &rate, &accel, &move_id) != 4) {
            reply_error("MOVE", "use MOVE <delta> <max_rate> <accel> <move_id>");
            return;
        }
        if (delta == 0 || delta <= INT32_MIN || delta > INT32_MAX ||
            rate < MIN_STEP_RATE_COUNTS_S ||
            rate > MAX_STEP_RATE_COUNTS_S || accel == 0 ||
            accel > MAX_ACCEL_COUNTS_S2 || move_id == 0 ||
            move_id > UINT32_MAX || move_id == g_active_move_id ||
            move_id == g_completed_move_id) {
            reply_error("MOVE", "delta/rate/acceleration/id invalid or move_id not fresh");
            return;
        }
        if (!g_armed || !g_drive_enabled || g_safety_latched ||
            g_abort_requested || g_motion_state == MOTION_MOVING) {
            reply_error("MOVE", "not enabled/armed, latched/aborting, or already moving");
            return;
        }
        const int64_t target = (int64_t)g_command_position + (int64_t)delta;
        if (target < g_cfg.soft_min_counts || target > g_cfg.soft_max_counts) {
            reply_error("MOVE", "target exceeds software travel window");
            return;
        }
        if ((delta > 0 && limit_pos_active()) ||
            (delta < 0 && limit_neg_active())) {
            reply_error("MOVE", "requested direction enters active hard limit");
            return;
        }
        move_request_t request = {
            .delta_counts = (int32_t)delta,
            .max_rate_counts_s = (uint32_t)rate,
            .accel_counts_s2 = (uint32_t)accel,
            .move_id = (uint32_t)move_id,
            .abort_epoch = g_abort_epoch,
        };
        /* Reserve the motion state before queueing to close the tiny window in
         * which a second MOVE could otherwise be accepted before core 1 starts. */
        g_motion_state = MOTION_MOVING;
        g_active_move_id = request.move_id;
        if (!queue_try_add(&g_move_queue, &request)) {
            g_motion_state = MOTION_IDLE;
            reply_error("MOVE", "motion queue full");
            return;
        }
        printf("{\"ok\":true,\"cmd\":\"MOVE\",\"accepted\":true,"
               "\"delta\":%lld,\"move_id\":%llu}\n", delta, move_id);
        return;
    }

    reply_error("UNKNOWN", "unknown command");
}

static void init_input(uint pin) {
    gpio_init(pin);
    gpio_set_dir(pin, GPIO_IN);
    gpio_pull_up(pin);
}

int main(void) {
    stdio_init_all();

    gpio_init(PIN_DIR);
    gpio_set_dir(PIN_DIR, GPIO_OUT);
    gpio_put(PIN_DIR, 0);

    gpio_init(PIN_DRIVE_ENABLE);
    gpio_set_dir(PIN_DRIVE_ENABLE, GPIO_OUT);
    gpio_put(PIN_DRIVE_ENABLE, 0);

    init_input(PIN_ENCODER_Z);
    init_input(PIN_LIMIT_POS);
    init_input(PIN_LIMIT_NEG);
    init_input(PIN_HOME);
    init_input(PIN_VIX_FAULT);
    init_input(PIN_ESTOP_AUX);

    gpio_set_irq_enabled_with_callback(PIN_ENCODER_Z,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, &gpio_irq_callback);
    gpio_set_irq_enabled(PIN_VIX_FAULT,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
    gpio_set_irq_enabled(PIN_ESTOP_AUX,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
    gpio_set_irq_enabled(PIN_LIMIT_POS,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
    gpio_set_irq_enabled(PIN_LIMIT_NEG,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);

    /* The official Raspberry Pi quadrature program uses computed jumps and
     * must occupy PIO instruction address 0. PIO1 is otherwise unused. */
    if (!pio_can_add_program_at_offset(
            g_encoder_pio, &quadrature_encoder_program, 0u)) {
        panic("quadrature encoder PIO program cannot be placed at offset 0");
    }
    g_encoder_offset = pio_add_program_at_offset(
        g_encoder_pio, &quadrature_encoder_program, 0u);
    (void)g_encoder_offset;
    g_encoder_sm = pio_claim_unused_sm(g_encoder_pio, true);
    quadrature_encoder_program_init(
        g_encoder_pio, g_encoder_sm, PIN_ENCODER_A, 0);
    refresh_encoder_count();

    pio_interrupt_clear(g_encoder_pio, 1u);
    irq_set_exclusive_handler(PIO1_IRQ_0, encoder_pio_irq_handler);
    pio_set_irq0_source_enabled(g_encoder_pio, pis_interrupt1, true);
    irq_set_enabled(PIO1_IRQ_0, true);

    g_step_offset = pio_add_program(g_step_pio, &stepgen_program);
    g_step_sm = pio_claim_unused_sm(g_step_pio, true);
    stepgen_program_init(g_step_pio, g_step_sm, g_step_offset, PIN_STEP);

    if (!queue_init(&g_move_queue, sizeof(move_request_t), 1)) {
        panic("motion queue initialization failed");
    }
    multicore_launch_core1(core1_entry);

    sleep_ms(1200);
    printf("{\"event\":\"BOOT\",\"fw\":\"%s\","
           "\"enabled\":false,\"armed\":false,"
           "\"note\":\"Run STATUS, confirm input polarities, ZERO, then ARM\"}\n",
           FW_VERSION);

    char line[LINE_BUFFER_SIZE];
    size_t used = 0;
    latch_code_t last_reported_latch = LATCH_NONE;
    absolute_time_t next_encoder_refresh = make_timeout_time_us(100u);
    g_last_heartbeat_us = time_us_64();

    while (true) {
        if (time_reached(next_encoder_refresh)) {
            refresh_encoder_count();
            update_x5_debounced_inputs();
            next_encoder_refresh = make_timeout_time_us(100u);
        }
        const uint64_t now_us = time_us_64();
        continuous_enabled_safety(now_us);
        trace_sample_if_due(now_us);

        const int ch = getchar_timeout_us(100);
        if (ch != PICO_ERROR_TIMEOUT) {
            if (ch == '\r' || ch == '\n') {
                if (used > 0) {
                    line[used] = '\0';
                    handle_line(line);
                    used = 0;
                }
            } else if (used + 1u < sizeof(line)) {
                line[used++] = (char)ch;
            } else {
                used = 0;
                reply_error("INPUT", "line too long");
            }
        }

        if (g_safety_latched && g_latch_code != last_reported_latch) {
            printf("{\"event\":\"SAFETY_LATCH\",\"latch\":\"%s\","
                   "\"enabled\":false}\n", latch_name(g_latch_code));
            last_reported_latch = g_latch_code;
        }
        if (!g_safety_latched) {
            last_reported_latch = LATCH_NONE;
        }
        tight_loop_contents();
    }
}
