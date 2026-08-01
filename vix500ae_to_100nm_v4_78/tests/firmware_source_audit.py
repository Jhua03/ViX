#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / 'firmware/src/main.c').read_text()
hdr = (ROOT / 'firmware/src/board_config.h').read_text()
host = (ROOT / 'host/vix100nm_commission.py').read_text()
combined = main + '\n' + hdr

required = [
    'PROTOCOL_REVISION 5',
    'vix-base-pico2-v2.7',
    'LATCH_ENCODER_INVALID',
    'motion queue initialization failed',
    'move_id == g_completed_move_id',
    'magnitude_following_error',
    'RECOVERY_MAX_MS',
    'RECOVERY_MAX_DELTA_COUNTS',
    'RECOVER START %lu %31s',
    'g_recovery_active',
    'g_recovery_deadline_us',
    'g_recovery_encoder_start_raw',
]
for item in required:
    assert item in combined, item

assert 'EXPECTED_PICO_PROTOCOL = 5' in host
assert 'FW_REQUIRED = "vix-base-pico2-v2.7"' in host
assert re.search(
    r'completed_id\s*==\s*move_id\s*and\s*motion\s*!=\s*["\']MOVING["\']',
    host,
)
assert 'ABBA_TRACE_PERIOD_US = 5_000' in host
assert 'TRACE_MAX_SAMPLES = 4096' in host
assert 'def plan_enabled_hold_trace(duration_s: float)' in host
assert 'HOLD_TRACE_TARGET_SAMPLES = 3600' in host
assert 'complete_enable_disable_envelope' in host
assert 'DIRECTION_CAL_COUNTS = 250' in host
assert 'def get_encoder_sign(state:' in host
assert 'def infer_direction_corrections(' in host
assert 'def wait_corrected_endpoint(' in host
assert 'vix_target_response' in host
assert 'ENCSIGN {encsign:+d}' in host
assert 'result["pico_response"] < -500' not in host
assert '"ENCSIGN": 1' not in host
assert 'Pico trace period readback mismatch' in host
assert 'def trace_dump(self, timeout_s: float = 120.0)' in host
assert 'validate_pico_input_snapshot(' in host
assert 'confirmation_zero_report = prepare_pico_for_enable_with_stale_vix_reset(' in host
assert 'LOCAL_ZERO_STATIONARY_MAX_WAIT_S = 2.0' in host
assert 'settle_history' in host
assert 'divider < 65536.0f' in main
assert 'static inline uint32_t magnitude_following_error(void);' in main
assert 'static inline uint32_t magnitude_i32(int32_t value);' in main

# Recovery tolerates only the already-active ViX fault. Independent physical,
# serial-link and motion protections remain live inside the timed window.
recovery_start = main.index('if (g_recovery_active) {')
recovery_end = main.index('\n    if (!estop_safe()) {', recovery_start)
recovery_branch = main[recovery_start:recovery_end]
for required_guard in (
    '!estop_safe()',
    'limit_pos_active()',
    'limit_neg_active()',
    'g_encoder_invalid_transitions != g_recovery_invalid_start',
    'g_recovery_fault_cleared',
    'g_recovery_fault_reasserted = true',
    'delta > RECOVERY_MAX_DELTA_COUNTS',
    'LATCH_HOST_WATCHDOG',
    'now_us >= g_recovery_deadline_us',
):
    assert required_guard in recovery_branch, required_guard
assert 'if (vix_fault_active())' in recovery_branch
assert 'if (g_recovery_fault_cleared)' in recovery_branch
assert 'fresh host heartbeat is required' in main
assert 'LATCH_RECOVERY_TIMEOUT' in main
assert 'gpio == PIN_VIX_FAULT && vix_fault_active() && !g_recovery_active' in main
assert 'g_safety_latched && g_latch_code != LATCH_VIX_FAULT' in main
assert 'confirmed input polarity policy is required' in main
assert 'ViX fault input is not active; recovery not needed' in main
assert 'duration_ms < RECOVERY_MIN_MS || duration_ms > RECOVERY_MAX_MS' in main
assert 'recovery_stop(true)' in main
assert 'recovery_stop(false)' in main

# All JSON printf format strings must have no duplicate literal keys per call.
for call in re.findall(r'printf\((.*?);', main, flags=re.S):
    literals = ''.join(re.findall(r'"((?:\\.|[^"\\])*)"', call))
    keys = re.findall(r'\\"([A-Za-z0-9_]+)\\"\s*:', literals)
    assert len(keys) == len(set(keys)), (keys, call[:160])

cmake = (ROOT / 'firmware/CMakeLists.txt').read_text()
wrapper = (ROOT / 'firmware/extra_scripts/pico_sdk_tasks.py').read_text()
assert 'set(PICO_NO_PICOTOOL 1 CACHE BOOL' in cmake
normalizer = (ROOT / 'firmware/extra_scripts/normalize_cmake_timestamp.py').read_text()
assert 'normalize_future_inputs' in normalizer
assert 'add_executable(pioasm IMPORTED GLOBAL)' in cmake
assert 'IMPORTED_LOCATION "${PIOASM_EXECUTABLE}"' in cmake
assert 'ExternalProject_Add' not in cmake
assert 'BUILD_ALWAYS 1' not in cmake
assert '_ensure_pioasm' in wrapper
assert 'pioasmBuild' in wrapper and 'Refusing to continue' in wrapper
assert '_assert_ninja_noop' in wrapper
assert 'no work to do' in wrapper
assert 'normalize_future_inputs(PROJECT_DIR)' in wrapper
assert 'sys.path.insert(0, str(SCRIPT_DIR))' in wrapper
assert 'Path(__file__)' not in wrapper
assert 'PROJECT_DIR / "extra_scripts"' in wrapper
assert '"-DPIOASM_EXECUTABLE=' in wrapper
assert 'PICO_NO_PICOTOOL=1' in wrapper
assert '"uf2", "convert"' in wrapper
assert 'rp2350-arm-s' in wrapper
assert 'UF2_PATH.stat().st_size < MIN_OUTPUT_SIZE' in wrapper
print('firmware deterministic build audit PASS')

# Host must use the dedicated Pico recovery gate, zero gains and lowest current,
# verify ST2.1, then prove OFF and restore the prior volatile drive settings.
assert 'AUTO_CLEARABLE_STALE_FAULT_BITS = frozenset({20, 21})' in host
assert 'def auto_clear_stale_drive_faults(' in host
assert 'GUARDED_RECOVERY_DURATION_MS = 1800' in host
assert 'GUARDED_RECOVERY_MAX_DELTA_COUNTS = 5_000' in host
assert 'def recovery_start(self, duration_ms: int)' in host
assert 'RECOVER START {duration_ms} I_UNDERSTAND' in host
assert 'GAINS(0,0,0,0,0)' in host
assert 'W(CL,1)' in host
assert 'W(PC,100)' in host
assert 'W(TL,5000)' in host
assert 'W(PA,0)' in host
assert 'pico.command("HB")' in host
assert 'pico.start_heartbeat()' in host
assert 'recovery_fault_reasserted' in host
assert 'st2[0] != "1"' in host
assert 'pico.recovery_stop()' in host
assert '_restore_vix_recovery_settings' in host
assert 'Only DF20 velocity/manual-backdrive and DF21 external-enable' in host
assert 'fault_auto_clear_policy": "guarded_timed_recovery_v3"' in host
assert 'DF is clear but the independent X4 fault output is active' in host
assert 'df_clear_before and not pico_fault_line_active' in host
assert 'status_health_before_recovery' in host
preflight_src = host[host.index('def preflight('):host.index('def temporary_vix_setup', host.index('def preflight('))]
assert preflight_src.index('_validate_vix_identity_and_health(') < preflight_src.index('auto_clear_stale_drive_faults(')
recovery_src = host[host.index('def auto_clear_stale_drive_faults('):host.index('def numeric_confirm', host.index('def auto_clear_stale_drive_faults('))]
assert recovery_src.index('attempt["off_response"] = vix.command(') < recovery_src.index('attempt["pico_stop_reply"] = pico.recovery_stop()')
assert 'for number, key in STAGE_PASS_KEYS.items()' in host
assert 'VIX_REPORT_ATTEMPTS = 3' in host
assert 'echo_without_payload' in host
assert 'retrying read-only report' in host
assert 'if not message.startswith("No report payload for ")' in host
assert 'def coherent_vix_target_estimate(' in host
assert 'PA/PE/PA' in host
assert 'DIRECTION_CAL_VERIFY_REPEATS = 3' in host
assert 'MOTION_GAIN_CANDIDATES = SAFE_GAIN_CANDIDATES' in host
assert 'def select_motion_gains(' in host
assert 'def plan_abba_trace(' in host
assert 'time-interpolated PA/PE' in host
assert 'time.sleep(settle_s)' not in host
assert 'unsettled_legs' in host
assert 'known_baseline_target_counts' in host
assert 'read_int_optional_once' in host
assert 'migrate_legacy_state_to_v426' in host
assert 'comprehensive_adaptive_v4_27' in host
assert 'comprehensive_adaptive_v4_26' in host
assert 'comprehensive_adaptive_v4_25' in host
assert 'comprehensive_adaptive_v4_21' in host
assert 'comprehensive_adaptive_v4_20' in host
assert 'LEGACY_V418_FINGERPRINT' in host
assert 'LEGACY_V419_FINGERPRINT' in host
assert 'zero_vix_and_pico_transaction' in host
assert 'W(PE,0)' in host
assert 'W(PT,0)' in host
assert 'dirty PA/PT/PF/PE zero' in host
assert 'events: list[tuple[str, int]] = [("block", 1)]' in host
assert 'endpoint_settle_max_s(amplitude)' in host
assert 'min(3.0, max(float(settle_s), matched_wait))' not in host
print('guarded drive-fault recovery audit PASS')
print('firmware source audit PASS')

assert '--recover-stage2-from-evidence' in host
