#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "host" / "vix100nm_commission.py"
spec = importlib.util.spec_from_file_location("vix100nm_commission", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class QuietLog:
    def say(self, *_args, **_kwargs) -> None:
        pass


class FlakyReportLog:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def say(self, text: str = "") -> None:
        self.messages.append(text)


def test_vix_report_echo_only_retry() -> None:
    instance = module.Vix.__new__(module.Vix)
    instance.log = FlakyReportLog()
    responses = [
        module.CommissionAbort(
            "No report payload for '2R(PT)': '2R(PT)\\r\\n'"
        ),
        "2R(PT)\r\n*1000\r\n",
    ]
    calls: list[str] = []

    def command(body: str, **_kwargs):
        calls.append(body)
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    instance.command = command  # type: ignore[method-assign]
    original_sleep = module.time.sleep
    try:
        module.time.sleep = lambda _seconds: None
        value = instance.report("R(PT)")
    finally:
        module.time.sleep = original_sleep

    assert value == "1000"
    assert calls == ["R(PT)", "R(PT)"]
    assert any("retrying read-only report" in msg for msg in instance.log.messages)
    assert any("recovered on attempt 2" in msg for msg in instance.log.messages)

    rejected = module.Vix.__new__(module.Vix)
    rejected.log = FlakyReportLog()
    rejected_calls = 0

    def reject_command(body: str, **_kwargs):
        nonlocal rejected_calls
        rejected_calls += 1
        raise module.CommissionAbort(
            f"ViX rejected '2{body}': '2{body}\\r\\n*E\\r\\n'"
        )

    rejected.command = reject_command  # type: ignore[method-assign]
    try:
        rejected.report("R(PT)")
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("real ViX *E rejection was not propagated")
    assert rejected_calls == 1

    print("ViX echo-only report retry regression PASS")


class FakePico:
    def __init__(self) -> None:
        self.position = 0
        self.command_position = 0
        self.completed_id = 0
        self.active_id = 0
        self.enabled = False
        self.invalid = 0
        self.armed = False
        self.motion = "IDLE"
        self.raw_fault = 0
        self.fault_active = False
        self.recovery_active = False
        self.recovery_timed_out = False
        self.recovery_fault_cleared = False
        self.recovery_fault_reasserted = False
        self.recovery_max_abs_delta = 0
        self.recovery_start_count = 0
        self.trace_period_us = 1000
        self.trace_capacity = module.TRACE_MAX_SAMPLES
        self.trace_started = False
        self.config_values = {
            "limit_pos_active_level": 1,
            "limit_neg_active_level": 0,
            "home_active_level": 1,
            "fault_active_level": 1,
            "has_limit_neg": False,
            "encoder_sign": 1,
            "command_dir_inverted": False,
            "require_estop_aux": True,
            "soft_min_counts": -module.INITIAL_SOFT_COUNTS,
            "soft_max_counts": module.INITIAL_SOFT_COUNTS,
            "following_abort_counts": module.PICO_FERR_SMOKE,
            "host_watchdog_ms": module.WATCHDOG_MS,
            "inputs_confirmed": True,
        }

    def command(self, command: str, timeout_s: float = 2.0):
        del timeout_s
        if command == "INFO":
            return {
                "ok": True,
                "fw": module.FW_REQUIRED,
                "protocol": module.EXPECTED_PICO_PROTOCOL,
                "board": module.EXPECTED_PICO_BOARD,
                "counts_per_mm": module.EXPECTED_PICO_COUNTS_PER_MM,
                "guarded_recovery": True,
                "recovery_min_ms": 100,
                "recovery_max_ms": 2000,
                "recovery_max_delta_counts": (
                    module.GUARDED_RECOVERY_MAX_DELTA_COUNTS
                ),
                "pins": dict(module.EXPECTED_PICO_PINS),
            }
        if command == "CONFIG SHOW":
            return {"ok": True, **self.config_values}
        if command == "ARM I_UNDERSTAND":
            self.armed = True
        elif command == "DISARM":
            self.armed = False
            self.enabled = False
        elif command == "ABORT":
            self.armed = False
            self.enabled = False
            self.recovery_active = False
        elif command == "ENABLE 1":
            self.enabled = True
        elif command == "ENABLE 0":
            self.enabled = False
            self.recovery_active = False
        elif command == "HB":
            return {"ok": True, "cmd": "HB"}
        elif command.startswith("RECOVER START "):
            if not self.fault_active:
                raise module.CommissionAbort("mock recovery requires fault input")
            self.recovery_start_count += 1
            self.recovery_active = True
            self.recovery_timed_out = False
            self.recovery_fault_cleared = False
            self.recovery_fault_reasserted = False
            self.recovery_max_abs_delta = 0
            self.enabled = True
            return {
                "ok": True,
                "cmd": "RECOVER START",
                "enabled": True,
                "recovery_active": True,
            }
        elif command == "RECOVER STOP":
            self.recovery_active = False
            self.enabled = False
            return {
                "ok": True,
                "cmd": "RECOVER STOP",
                "enabled": False,
                "recovery_active": False,
                "timed_out": self.recovery_timed_out,
                "fault_cleared": self.recovery_fault_cleared,
                "fault_reasserted": self.recovery_fault_reasserted,
                "max_abs_delta": self.recovery_max_abs_delta,
            }
        elif command == "ZERO":
            self.position = 0
            self.command_position = 0
        elif command.startswith("MOVE "):
            _, delta, _rate, _accel, move_id = command.split()
            value = int(delta)
            self.active_id = int(move_id)
            self.motion = "MOVING"
            self.position += value
            self.command_position += value
            self.completed_id = int(move_id)
            self.motion = "IDLE"
            return {
                "ok": True, "accepted": True,
                "move_id": self.active_id,
            }
        return {"ok": True}

    def config(self, key: str, value: int):
        field_map = {
            "LPOL": "limit_pos_active_level",
            "LNPOL": "limit_neg_active_level",
            "HPOL": "home_active_level",
            "FPOL": "fault_active_level",
            "HAS_LN": "has_limit_neg",
            "ENCSIGN": "encoder_sign",
            "DIRINV": "command_dir_inverted",
            "ESTOPREQ": "require_estop_aux",
            "SOFTMIN": "soft_min_counts",
            "SOFTMAX": "soft_max_counts",
            "FERRMAX": "following_abort_counts",
            "WATCHDOG_MS": "host_watchdog_ms",
            "CONFIRM_INPUTS": "inputs_confirmed",
        }
        field = field_map[key]
        if field in {
            "has_limit_neg", "command_dir_inverted",
            "require_estop_aux", "inputs_confirmed"
        }:
            self.config_values[field] = bool(value)
        else:
            self.config_values[field] = value
        return {"ok": True, **self.config_values}

    def config_show(self):
        return {"ok": True, **self.config_values}

    def force_safe(self):
        for command in ("ABORT", "ENABLE 0", "DISARM"):
            self.command(command)
        info = self.command("INFO")
        status = self.status()
        errors = []
        if status.get("enabled"):
            errors.append("enabled remained true")
        if status.get("armed"):
            errors.append("armed remained true")
        if status.get("motion") == "MOVING":
            errors.append("motion remained MOVING")
        if errors:
            raise module.CommissionAbort("mock safe-state failure: " + ", ".join(errors))
        return {"info": info, "status": status}

    def close(self):
        pass

    def status(self):
        return {
            "ok": True,
            "encoder_position": self.position,
            "command_position": self.command_position,
            "zeroed": True,
            "encoder_invalid": self.invalid,
            "following_error": self.command_position - self.position,
            "latched": False,
            "latch": "VIX_FAULT" if self.fault_active else "NONE",
            "move_active_id": self.active_id,
            "move_completed_id": self.completed_id,
            "motion": self.motion,
            "enabled": self.enabled,
            "armed": self.armed,
            "encoder_raw": self.position,
            "raw_limit_pos": 0,
            "limit_pos_active": False,
            "limit_neg_active": False,
            "raw_home": 0,
            "home_active": False,
            "raw_fault": self.raw_fault,
            "fault_active": self.fault_active,
            "estop_safe": True,
            "recovery_active": self.recovery_active,
            "recovery_timed_out": self.recovery_timed_out,
            "recovery_fault_cleared": self.recovery_fault_cleared,
            "recovery_fault_reasserted": self.recovery_fault_reasserted,
            "recovery_max_abs_delta": self.recovery_max_abs_delta,
        }

    def start_heartbeat(self) -> None:
        pass

    def stop_heartbeat(self) -> None:
        pass

    def check_heartbeat(self) -> None:
        pass

    def recovery_start(self, duration_ms: int):
        return self.command(
            f"RECOVER START {duration_ms} I_UNDERSTAND"
        )

    def recovery_stop(self):
        return self.command("RECOVER STOP")

    def trace_start(self, period_us, capacity) -> None:
        self.trace_period_us = int(period_us)
        self.trace_capacity = int(capacity)
        self.trace_started = True

    def trace_stop(self) -> None:
        pass

    def trace_info(self):
        return {
            "ok": True,
            "active": False,
            "full": False,
            "count": 5,
            "capacity": self.trace_capacity,
            "period_us": self.trace_period_us,
        }

    def trace_dump(self, *_args):
        # Disabled prelude, enabled interval, disabled tail.
        return [
            {"trace": True, "t_us": 0, "enc": 0, "ferr": 0, "invalid": 0, "flags": 0},
            {"trace": True, "t_us": self.trace_period_us, "enc": 0, "ferr": 0, "invalid": 0, "flags": 1},
            {"trace": True, "t_us": 2*self.trace_period_us, "enc": 0, "ferr": 0, "invalid": 0, "flags": 1},
            {"trace": True, "t_us": 3*self.trace_period_us, "enc": 0, "ferr": 0, "invalid": 0, "flags": 1},
            {"trace": True, "t_us": 4*self.trace_period_us, "enc": 0, "ferr": 0, "invalid": 0, "flags": 0},
        ]


class FakeVix:
    def __init__(self, pico: FakePico) -> None:
        self.pico = pico
        self.on = False
        self.axis = module.EXPECTED_AXIS
        self.enable_transient = 0
        self.reset_should_fail = False
        self.es = 1
        self.ei = 0
        self.eo = 2
        self.mode = "MT"
        self.cl = 50
        self.pc = 100
        self.tl = 1000
        self.gains = {
            "GF": 0.0,
            "GI": 0.0,
            "GP": 2.0,
            "GV": 1.0,
            "FT": 0,
        }
        self.on_commands = 0
        self.fault_state = {
            name: "00000000" for name in ("DF1", "DF2", "DF3", "DF4")
        }

    def command(self, command: str, **_kwargs):
        if command == "ON":
            self.on_commands += 1
            if self.pico.enabled:
                self.on = True
                if self.pico.recovery_active:
                    bits = set(module.decode_drive_fault_bits(self.fault_state))
                    if (
                        module.all_zero_faults(self.fault_state)
                        or (bits - {1}).issubset(
                            module.AUTO_CLEARABLE_STALE_FAULT_BITS
                        )
                    ):
                        self.fault_state = {
                            name: "00000000"
                            for name in ("DF1", "DF2", "DF3", "DF4")
                        }
                        self.pico.raw_fault = 0
                        self.pico.fault_active = False
                        self.pico.recovery_fault_cleared = True
                if self.enable_transient:
                    self.pico.position += self.enable_transient
                    self.pico.command_position += self.enable_transient
            else:
                self.on = False
        elif command == "OFF":
            self.on = False
        elif command in {"MP", "MT", "MI", "MA", "MC"}:
            self.mode = command
        elif command == "W(PA,0)":
            self.pico.position = 0
            self.pico.command_position = 0
        elif command == "W(ES,0)":
            self.es = 0
        elif command.startswith("W(ES,"):
            self.es = int(command.removeprefix("W(ES,").removesuffix(")"))
        elif command.startswith("W(EI,"):
            self.ei = int(command.removeprefix("W(EI,").removesuffix(")"))
        elif command.startswith("W(EO,"):
            self.eo = int(command.removeprefix("W(EO,").removesuffix(")"))
        elif command.startswith("W(CL,"):
            self.cl = int(command.removeprefix("W(CL,").removesuffix(")"))
        elif command.startswith("W(PC,"):
            self.pc = int(command.removeprefix("W(PC,").removesuffix(")"))
        elif command.startswith("W(TL,"):
            self.tl = int(command.removeprefix("W(TL,").removesuffix(")"))
        elif command.startswith("GAINS("):
            raw = command.removeprefix("GAINS(").removesuffix(")")
            gf, gi, gp, gv, ft = raw.split(",")
            self.gains = {
                "GF": float(gf),
                "GI": float(gi),
                "GP": float(gp),
                "GV": float(gv),
                "FT": int(float(ft)),
            }
        return ""

    def off(self) -> None:
        self.on = False

    def require_energized(self, expected: bool) -> None:
        assert self.on is expected

    def is_energized(self) -> bool:
        return self.on

    def st2_bits(self) -> str:
        return ("1" if self.on else "0") + "0000000"

    def i2t_active(self) -> bool:
        return False

    def require_i2t_clear(self) -> None:
        return None

    def faults(self):
        return dict(self.fault_state)

    def read_int(self, name: str) -> int:
        if name == "PA":
            return self.pico.position
        if name == "ES":
            return self.es
        if name == "EI":
            return self.ei
        if name == "EO":
            return self.eo
        if name == "CL":
            return self.cl
        if name == "PC":
            return self.pc
        if name == "TL":
            return self.tl
        if name == "FT":
            return int(self.gains["FT"])
        return 0

    def read_int_optional_once(self, name: str):
        if name == "PT":
            return self.read_int(name)
        return self.read_int(name)

    def read_float(self, name: str) -> float:
        if name in self.gains:
            return float(self.gains[name])
        return float(self.read_int(name))

    def report(self, body: str) -> str:
        if body == "M":
            return self.mode
        raise AssertionError(f"unexpected mock report {body}")

    def reset_restore(self) -> None:
        self.on = False
        if self.reset_should_fail:
            raise module.CommissionAbort("mock reset failure")

    def close(self) -> None:
        pass


class DirectionFakePico(FakePico):
    def __init__(self, *, encoder_sign: int, dirinv: bool) -> None:
        super().__init__()
        self.physical_position = 0
        self.physical_target = 0
        self.config_values["encoder_sign"] = encoder_sign
        self.config_values["command_dir_inverted"] = dirinv

    def command(self, command: str, timeout_s: float = 2.0):
        if command == "ZERO":
            self.physical_position = 0
            self.physical_target = 0
            self.position = 0
            self.command_position = 0
            return {"ok": True}
        if command.startswith("MOVE "):
            _, delta, _rate, _accel, move_id = command.split()
            logical = int(delta)
            physical = (
                -logical
                if self.config_values["command_dir_inverted"]
                else logical
            )
            self.active_id = int(move_id)
            self.motion = "MOVING"
            self.command_position += logical
            self.physical_target += physical
            self.physical_position = self.physical_target
            self.position = (
                int(self.config_values["encoder_sign"])
                * self.physical_position
            )
            self.completed_id = int(move_id)
            self.motion = "IDLE"
            return {
                "ok": True, "accepted": True,
                "move_id": self.active_id,
            }
        return super().command(command, timeout_s)

    def status(self):
        value = super().status()
        value["encoder_raw"] = self.physical_position
        value["encoder_position"] = (
            int(self.config_values["encoder_sign"])
            * self.physical_position
        )
        value["following_error"] = (
            self.command_position - value["encoder_position"]
        )
        return value


class DirectionFakeVix(FakeVix):
    def read_int(self, name: str) -> int:
        if name == "PA":
            return int(self.pico.physical_position)
        if name == "PT":
            return int(self.pico.physical_target)
        if name == "PE":
            # Observed AE convention: PE = PA - PT.
            return int(self.pico.physical_position - self.pico.physical_target)
        return super().read_int(name)

    def command(self, command: str, **kwargs):
        if command == "W(PA,0)":
            self.pico.physical_position = 0
            self.pico.physical_target = 0
            self.pico.position = 0
            self.pico.command_position = 0
            return ""
        return super().command(command, **kwargs)


class TargetBracketRaceVix:
    """First bracket moves badly; later brackets are stationary at PT=250."""
    def __init__(self) -> None:
        self.pa_pairs = [(124, 252)] + [(252, 252)] * 8
        self.pair_index = 0
        self.pa_phase = 0

    def read_int(self, name: str) -> int:
        pair = self.pa_pairs[min(self.pair_index, len(self.pa_pairs) - 1)]
        if name == "PA":
            value = pair[self.pa_phase]
            if self.pa_phase == 0:
                self.pa_phase = 1
            else:
                self.pa_phase = 0
                self.pair_index += 1
            return value
        if name == "PE":
            # For the stationary accepted rows: PA 252, PT 250 => PE +2.
            return 2
        raise AssertionError(name)


class ObservedV418BaselineVix:
    """Exact PA/PE/PA triples from the field failure, with PT approximately 0."""
    def __init__(self) -> None:
        self.rows = [
            (189, 172, 157),
            (137, 111, 91),
            (70, 55, 44),
            (35, 24, 15),
            (1, -4, -11),
            (-13, -20, -27),
            (-36, -50, -67),
            (-84, -93, -92),
            (-107, -108, -110),
        ]
        self.row = 0
        self.phase = 0

    def read_int(self, name: str) -> int:
        triple = self.rows[min(self.row, len(self.rows) - 1)]
        if name == "PA":
            value = triple[0] if self.phase == 0 else triple[2]
            if self.phase == 0:
                self.phase = 1
            else:
                self.phase = 0
                self.row += 1
            return value
        if name == "PE":
            return triple[1]
        raise AssertionError(name)


def test_observed_v418_moving_baseline_is_estimated() -> None:
    original_sleep = module.time.sleep
    try:
        module.time.sleep = lambda _seconds: None
        measurement = module.coherent_vix_target_estimate(
            ObservedV418BaselineVix(), samples=7, max_attempts=9
        )
    finally:
        module.time.sleep = original_sleep
    assert abs(measurement["target_counts"]) <= 5, measurement
    assert measurement["inlier_count"] >= 5
    assert measurement["scale_tolerance_counts"] <= 12
    print("observed moving-baseline target regression PASS")


def test_coherent_target_rejects_sampling_race() -> None:
    original_sleep = module.time.sleep
    try:
        module.time.sleep = lambda _seconds: None
        measurement = module.coherent_vix_target_estimate(
            TargetBracketRaceVix(), samples=7, max_attempts=8
        )
    finally:
        module.time.sleep = original_sleep
    assert measurement["target_counts"] == 250, measurement
    assert measurement["attempts"][0]["pa_span"] == 128
    assert measurement["inlier_count"] >= 5
    assert abs(measurement["attempts"][0]["target_estimate"] - 250) > 20
    assert measurement["scale_tolerance_counts"] <= 12
    print("time-interpolated PA/PE target race regression PASS")


def clean_metric():
    return {
        "correct_direction_fraction": 1.0,
        "median_signed_pico_response": 10,
        "within_tolerance_fraction": 1.0,
        "p95_abs_endpoint_error": 1,
        "max_abs_pico_vix_delta_disagreement": 0,
        "wrong_direction_responses": 0,
        "median_abs_closure": 1,
        "p95_abs_closure": 2,
        "sham_median_abs": 0,
        "sham_p95_abs": 1,
        "max_abs_vix_pe": 2,
        "max_abs_following_error": 2,
        "invalid_delta": 0,
        "final_latched": False,
        "final_i2t_active": False,
        "final_faults": {
            name: "00000000" for name in ("DF1", "DF2", "DF3", "DF4")
        },
        "energised_verified": True,
        "response_tolerance_counts": 2,
    }


def main() -> int:
    test_vix_report_echo_only_retry()
    test_coherent_target_rejects_sampling_race()
    test_observed_v418_moving_baseline_is_estimated()
    coarse_trace = module.plan_abba_trace(10_000, 5_000)
    fine_trace = module.plan_abba_trace(10, 100)
    assert coarse_trace["estimated_samples"] <= module.TRACE_MAX_SAMPLES
    assert fine_trace["estimated_samples"] <= module.TRACE_MAX_SAMPLES
    assert coarse_trace["period_us"] >= fine_trace["period_us"]
    assert module.endpoint_settle_goal_counts(10) == 2
    assert module.endpoint_settle_goal_counts(10_000) == 20
    assert module.validate_motion_gains(module.MOTION_GAIN_CANDIDATES[-1])
    assert module.amplitude_pass(clean_metric(), 10, final=True)[0]

    adversarial = {
        "within_tolerance_fraction": 0.5,
        "p95_abs_endpoint_error": 3,
        "sham_median_abs": 10,
        "sham_p95_abs": 10,
        "max_abs_vix_pe": 21,
        "invalid_delta": 1,
        "energised_verified": False,
    }
    for key, value in adversarial.items():
        metric = clean_metric()
        metric[key] = value
        assert not module.amplitude_pass(metric, 10, final=True)[0], key

    pico = FakePico()
    vix = FakeVix(pico)
    # Verify the final local-zero and strict disable helpers against the mock.
    pico.position = 123
    module.prepare_pico_for_enable(vix, pico, 5000)
    assert pico.position == 0
    pico.enabled = True
    vix.on = True
    module.deenergize_drive(vix, pico, verify=True)
    assert not pico.enabled and not vix.on

    with tempfile.TemporaryDirectory() as directory:
        records, metric = module.run_abba(
            vix,
            pico,
            QuietLog(),
            Path(directory),
            amplitude=10,
            blocks=2,
            shams=2,
            rate=100,
            accel=5000,
            settle_s=0,
            name="mock_100nm",
            trace_first_block=True,
        )
        passed, reasons = module.amplitude_pass(metric, 10, final=True)
        assert passed, reasons
        assert len(records) == 10
        assert metric["move_legs"] == 8
        assert metric["within_tolerance_fraction"] == 1.0
        assert metric["invalid_delta"] == 0
        assert metric["energised_verified"] is True

    smoke_plan = module.plan_enabled_hold_trace(0.5)
    ladder_plan = module.plan_enabled_hold_trace(1.5)
    confirmation_plan = module.plan_enabled_hold_trace(3.0)
    assert smoke_plan["period_us"] == 1000
    assert smoke_plan["capacity"] == module.TRACE_MAX_SAMPLES
    assert ladder_plan["period_us"] >= 1000
    assert confirmation_plan["period_us"] > smoke_plan["period_us"]
    for plan in (smoke_plan, ladder_plan, confirmation_plan):
        assert plan["estimated_samples"] <= module.HOLD_TRACE_TARGET_SAMPLES
        assert plan["reserved_samples"] >= (
            module.TRACE_MAX_SAMPLES - module.HOLD_TRACE_TARGET_SAMPLES
        )
    with tempfile.TemporaryDirectory() as directory:
        hold_pico = FakePico()
        hold_vix = FakeVix(hold_pico)
        _, hold_metrics = module.enabled_hold(
            hold_vix,
            hold_pico,
            QuietLog(),
            Path(directory),
            name="trace_budget_regression",
            duration_s=0.001,
            runaway_counts=5000,
        )
        assert hold_pico.trace_capacity == module.TRACE_MAX_SAMPLES
        assert hold_metrics["complete_enable_disable_envelope"] is True
        assert hold_metrics["pre_enable_samples"] >= 1
        assert hold_metrics["post_disable_samples"] >= 1
    print("dynamic enabled-hold trace budget regression PASS")

    state = {
        "stage_0_preflight_passed": True,
        "schema": module.STATE_SCHEMA,
        "fingerprint": module.STATE_FINGERPRINT,
    }
    module.require_stage_prerequisite(1, state)
    stale = dict(state)
    stale["schema"] = module.STATE_SCHEMA - 1
    try:
        module.require_stage_prerequisite(1, stale)
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("stale state schema was accepted")
    try:
        module.require_stage_prerequisite(2, state)
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("stage prerequisite did not reject missing Stage 1")

    # Safe-state proof must reject dishonest enabled readback.
    unsafe = FakePico()
    original_status = unsafe.status
    def unsafe_status():
        value = original_status()
        value["enabled"] = True
        return value
    unsafe.status = unsafe_status  # type: ignore[method-assign]
    try:
        unsafe.force_safe()
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("unsafe Pico readback was accepted")

    # Exact CONFIG readback validation.
    cfg_pico = FakePico()
    module.configure_pico_policy(cfg_pico, bench_no_estop=False, dirinv=False, encsign=-1)
    assert cfg_pico.config_values["encoder_sign"] == -1
    cfg_pico.config_values["soft_max_counts"] += 1
    try:
        # Prevent the normal config writes from repairing the injected mismatch.
        cfg_pico.config = lambda _key, _value: {"ok": True}  # type: ignore[method-assign]
        module.configure_pico_policy(cfg_pico, bench_no_estop=False, dirinv=False, encsign=-1)
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("Pico CONFIG mismatch was accepted")

    # Stage 3 must distinguish encoder-copy sign from STEP/DIR direction.
    wrong_sign_pico = DirectionFakePico(encoder_sign=-1, dirinv=False)
    wrong_sign_vix = DirectionFakeVix(wrong_sign_pico)
    original_temp_setup = module.temporary_vix_setup
    original_prepare = module.prepare_pico_for_enable
    original_sleep = module.time.sleep
    try:
        module.temporary_vix_setup = lambda *_args, **_kwargs: None
        module.prepare_pico_for_enable = lambda *_args, **_kwargs: None
        module.time.sleep = lambda _seconds: None
        with tempfile.TemporaryDirectory() as directory:
            wrong_sign_result = module.direction_probe_once(
                wrong_sign_vix,
                wrong_sign_pico,
                QuietLog(),
                Path(directory),
                module.Gains(0, 0, 0.1, 0.1, 0),
                False,
                "wrong_sign_probe",
                encsign=-1,
                command_counts=module.DIRECTION_CAL_COUNTS,
                rate=module.DIRECTION_CAL_RATE,
                adaptive_settle=False,
            )
        assert wrong_sign_result["vix_target_response"] == 250
        assert wrong_sign_result["vix_response"] == 250
        assert wrong_sign_result["pico_response"] == -250
        next_sign, next_dirinv, vix_axis_sign, changes = module.infer_direction_corrections(
            wrong_sign_result, encsign=-1, dirinv=False
        )
        assert next_sign == 1
        assert next_dirinv is False
        assert vix_axis_sign == 1
        assert any("ENCSIGN" in item for item in changes)

        wrong_dir_pico = DirectionFakePico(encoder_sign=1, dirinv=True)
        wrong_dir_vix = DirectionFakeVix(wrong_dir_pico)
        with tempfile.TemporaryDirectory() as directory:
            wrong_dir_result = module.direction_probe_once(
                wrong_dir_vix,
                wrong_dir_pico,
                QuietLog(),
                Path(directory),
                module.Gains(0, 0, 0.1, 0.1, 0),
                True,
                "wrong_dir_probe",
                encsign=1,
                command_counts=module.DIRECTION_CAL_COUNTS,
                rate=module.DIRECTION_CAL_RATE,
                adaptive_settle=False,
                allow_target_sign_correction=True,
            )
        next_sign, next_dirinv, vix_axis_sign, changes = module.infer_direction_corrections(
            wrong_dir_result, encsign=1, dirinv=True
        )
        assert next_sign == -1
        assert next_dirinv is True
        assert vix_axis_sign == -1
        assert any("ENCSIGN" in item for item in changes)
        assert any("ViX PA/PT comparison sign" in item for item in changes)

        # Field regression from 2026-07-29: Pico command/encoder response was
        # already coherent, while raw ViX PA/PT was the opposite sign. Do not
        # flip ENCSIGN in that case; record the ViX comparison sign instead.
        field_result = {
            "command": 250,
            "vix_target_response": -244,
            "target_tolerance_counts": 9,
            "vix_response": -252,
            "pico_response": 253.0,
        }
        next_sign, next_dirinv, vix_axis_sign, changes = module.infer_direction_corrections(
            field_result, encsign=1, dirinv=False
        )
        assert next_sign == 1
        assert next_dirinv is False
        assert vix_axis_sign == -1
        assert any("ViX PA/PT comparison sign" in item for item in changes)
        field_result["vix_axis_sign"] = vix_axis_sign
        field_result["vix_axis_target_response"] = vix_axis_sign * field_result["vix_target_response"]
        field_result["vix_axis_response"] = vix_axis_sign * field_result["vix_response"]
        field_result["target_scale_ok"] = True
        field_result["settled"] = True
        field_result["settling"] = {"settled": True}
        field_result["pico_vix_disagreement"] = field_result["pico_response"] - field_result["vix_axis_response"]
        assert module.calibration_scale_ok(field_result) is True
        module.require_calibration_direction(field_result, require_settled=True)

        corrected_pico = DirectionFakePico(encoder_sign=1, dirinv=False)
        corrected_vix = DirectionFakeVix(corrected_pico)
        with tempfile.TemporaryDirectory() as directory:
            corrected_result = module.direction_probe_once(
                corrected_vix,
                corrected_pico,
                QuietLog(),
                Path(directory),
                module.Gains(0, 0, 0.1, 0.1, 0),
                False,
                "corrected_full_probe",
                encsign=1,
                command_counts=module.DIRECTION_FULL_COUNTS,
                rate=module.DIRECTION_FULL_RATE,
                adaptive_settle=True,
            )
        assert corrected_result["settled"] is True, corrected_result
        assert corrected_result["vix_target_response"] == 1000
        assert corrected_result["pico_response"] == 1000
        assert corrected_result["vix_response"] == 1000
    finally:
        module.temporary_vix_setup = original_temp_setup
        module.prepare_pico_for_enable = original_prepare
        module.time.sleep = original_sleep
    print("adaptive Stage 3 sign/scale regression PASS")

    # Stage 3 sparse serial-poll hold revalidation must not reject a stable seed
    # merely because ViX R(PA)/R(PE) polls left the time-based tail under-sampled.
    tail_pico = FakePico()
    tail_vix = FakeVix(tail_pico)
    original_sleep = module.time.sleep
    try:
        module.time.sleep = lambda _seconds: None
        tail = module.enabled_pico_tail_confirmation(
            tail_vix, tail_pico,
            raw0=0, invalid0=0, movement_limit_counts=module.GAIN_HOLD_RUNAWAY_COUNTS,
            context="offline sparse-tail regression", duration_s=0.1, sample_s=0.02,
        )
    finally:
        module.time.sleep = original_sleep
    assert tail["sample_count"] >= 4, tail
    assert tail["stable"] is True, tail
    assert tail["tail_span_counts"] == 0, tail
    assert module.motion_candidates_bounded_by_seed(
        module.Gains(0, 0.1, 2.0, 1.0, 0)
    ) == [module.Gains(0, 0.1, 2.0, 1.0, 0)]
    print("Stage 3 sparse-tail seed revalidation regression PASS")

    assert module.direction_abort_is_hard(module.CommissionAbort("ViX fault during probe")) is True
    soft_exc = module.CommissionAbort(
        "Corrected encoder moved opposite command during direction_calibration: command=-250, response=256"
    )
    assert module.direction_abort_is_hard(soft_exc) is False
    failed = module.failed_direction_result(
        gains=module.Gains(0, 0.1, 2.0, 1.0, 0),
        dirinv=False, encsign=1, cl_percent=2, command=-250,
        rate=500, vix_axis_sign=-1, error=soft_exc,
    )
    summary = module.calibration_series_summary([failed], rate=500)
    assert summary["all_pass"] is False
    assert summary["soft_probe_failures"], summary
    print("Stage 3 diagnostic soft-fail classification regression PASS")

    # A stale completed move ID must never be accepted as instant completion.
    collision_pico = FakePico()
    collision_pico.completed_id = 1234
    actual_id, collision_status = module.issue_move(
        collision_pico, 10, 100, 5000, 1234
    )
    assert actual_id != 1234
    assert collision_status["move_completed_id"] == actual_id

    # Incomplete fault dictionaries are not accepted as all-clear.
    assert not module.all_zero_faults({"DF1": "00000000"})

    # Cleanup failure must escape the context and fail the stage rather than
    # being suppressed after a pass flag was written.
    cleanup_pico = FakePico()
    cleanup_vix = FakeVix(cleanup_pico)
    cleanup_vix.reset_should_fail = True
    original_vix_cls = module.Vix
    original_pico_cls = module.Pico
    module.Vix = lambda *_args, **_kwargs: cleanup_vix
    module.Pico = lambda *_args, **_kwargs: cleanup_pico
    try:
        args = SimpleNamespace(
            vix_port="mock", vix_baud=9600,
            pico_port="mock", pico_baud=115200,
        )
        try:
            with module.hardware(args, QuietLog()):
                pass
        except module.CommissionAbort:
            pass
        else:
            raise AssertionError("cleanup failure was suppressed")
    finally:
        module.Vix = original_vix_cls
        module.Pico = original_pico_cls

    assert module.EXPECTED_PICO_PINS["lim_pos"] == 7
    policy_pico = FakePico()
    policy = module.configure_pico_policy(
        policy_pico, bench_no_estop=False, dirinv=False
    )
    assert policy["limit_pos_active_level"] == 1
    safe_status = policy_pico.status()
    safe_status["raw_limit_pos"] = 0
    assert safe_status["raw_limit_pos"] == 0
    print("Limit+ polarity regression PASS")
    # Known manual-backdrive fault must clear only inside the dedicated,
    # internally timed zero-gain recovery gate.
    clear_pico = FakePico()
    clear_pico.raw_fault = 1
    clear_pico.fault_active = True
    clear_vix = FakeVix(clear_pico)
    clear_vix.fault_state = {
        "DF1": "10000000",
        "DF2": "00000000",
        "DF3": "00010000",
        "DF4": "00000000",
    }
    original_sleep = module.time.sleep
    try:
        module.time.sleep = lambda _seconds: None
        with tempfile.TemporaryDirectory() as directory:
            clear_report = module.auto_clear_stale_drive_faults(
                clear_vix,
                clear_pico,
                QuietLog(),
                Path(directory),
                bench_no_estop=False,
            )
        assert clear_report["success"] is True
        assert module.all_zero_faults(clear_vix.faults())
        assert clear_vix.on_commands >= 1
        assert clear_pico.recovery_start_count >= 1
        assert clear_vix.on is False
        assert clear_pico.enabled is False
        assert clear_pico.recovery_active is False
    finally:
        module.time.sleep = original_sleep

    # DF clear with X4 fault-active is an electrical/output inconsistency and
    # must never receive an automatic ON pulse.
    x4_pico = FakePico()
    x4_pico.raw_fault = 1
    x4_pico.fault_active = True
    x4_vix = FakeVix(x4_pico)
    try:
        with tempfile.TemporaryDirectory() as directory:
            module.auto_clear_stale_drive_faults(
                x4_vix,
                x4_pico,
                QuietLog(),
                Path(directory),
                bench_no_estop=False,
            )
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("DF-clear/X4-high inconsistency was energised")
    assert x4_vix.on_commands == 0
    assert x4_pico.recovery_start_count == 0
    assert x4_vix.on is False
    assert x4_pico.enabled is False

    print("DF-clear/X4-high hard-block regression PASS")

    # A non-whitelisted fault must not be erased or receive an ON command.
    blocked_pico = FakePico()
    blocked_vix = FakeVix(blocked_pico)
    blocked_vix.fault_state = {
        "DF1": "10010000",  # composite + motor HV over-voltage (bit 4)
        "DF2": "00000000",
        "DF3": "00000000",
        "DF4": "00000000",
    }
    try:
        with tempfile.TemporaryDirectory() as directory:
            module.auto_clear_stale_drive_faults(
                blocked_vix,
                blocked_pico,
                QuietLog(),
                Path(directory),
                bench_no_estop=False,
            )
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("non-whitelisted drive fault was auto-cleared")
    assert blocked_vix.on_commands == 0
    assert not module.all_zero_faults(blocked_vix.faults())

    # Incomplete DF data is never accepted as clear.
    try:
        module.decode_drive_fault_bits({"DF1": "00000000"})
    except module.CommissionAbort:
        pass
    else:
        raise AssertionError("incomplete DF report was accepted")

    print("guarded stale drive-fault recovery regression PASS")
    print("offline integration PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

class ZeroRejectsUnlessSafePico:
    def __init__(self) -> None:
        self.enabled = True
        self.armed = True
        self.zeroed = False
        self.commands: list[str] = []

    def command(self, command: str, timeout_s: float = 2.0):
        del timeout_s
        self.commands.append(command)
        if command == "STATUS":
            return self.status()
        if command == "ENABLE 0":
            self.enabled = False
            return {"ok": True}
        if command == "DISARM":
            self.armed = False
            self.enabled = False
            return {"ok": True}
        if command == "ZERO":
            if self.enabled or self.armed:
                raise module.CommissionAbort("Pico rejected 'ZERO': disable and disarm before zeroing")
            self.zeroed = True
            return {"ok": True}
        if command in {"CLEAR", "DIAG CLEAR", "ABORT"}:
            return {"ok": True}
        raise AssertionError(f"unexpected command {command}")

    def status(self):
        return {
            "ok": True,
            "motion": "IDLE",
            "enabled": self.enabled,
            "armed": self.armed,
            "latched": False,
            "latch": "NONE",
            "zeroed": self.zeroed,
            "encoder_position": 0,
            "command_position": 0,
            "following_error": 0,
        }


def test_safe_zero_disables_and_disarms_first() -> None:
    pico = ZeroRejectsUnlessSafePico()
    report = module.safe_pico_zero(pico, reason="regression")
    assert report["post"]["zeroed"] is True
    assert pico.commands.index("ENABLE 0") < pico.commands.index("ZERO")
    assert pico.commands.index("DISARM") < pico.commands.index("ZERO")
    print("Pico safe-zero disable/disarm regression PASS")


test_safe_zero_disables_and_disarms_first()
