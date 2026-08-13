#!/usr/bin/env python3
"""Limit-input isolation probe for ViX500AE/AH + MX80L + Pico2.

V4.67 is a diagnostic-only no-STEP/DIR script.  It investigates the
LIMIT_POS latch seen in v4.66 after the ViX was already energised.  The goal is
not to prove 100 nm motion; it is to answer whether the Pico's +limit input is
actually going active/glitching, and whether that happens while OFF, during X4
enable-only, or only after the ViX power stage is ON.

Important: this script does not mask or disable Pico safety.  If LIMIT_POS goes
active while the Pico enable output is on, the firmware will still latch and
drop the enable output.  The script starts the Pico trace buffer before each
phase so the transient is captured instead of being hidden by the later latched
state.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from vix100nm_commission import (  # type: ignore
    CommissionAbort,
    Gains,
    Pico,
    RunLog,
    Vix,
    configure_pico_policy,
    deenergize_drive,
    preflight_with_serial_retry,
    safe_pico_zero,
    temporary_vix_setup,
)

STOP_REQUESTED = False
DIRINV = False
ENCSIGN = -1
ZERO_GAINS = Gains(0, 0, 0, 0, 0)
SOFT_GAIN = Gains(0, 0, 1.0, 0.75, 0)

TRACE_FLAG_ENABLED = 1 << 0
TRACE_FLAG_ARMED = 1 << 1
TRACE_FLAG_MOVING = 1 << 2
TRACE_FLAG_LIMIT_POS = 1 << 3
TRACE_FLAG_LIMIT_NEG = 1 << 4
TRACE_FLAG_HOME = 1 << 5
TRACE_FLAG_FAULT = 1 << 6
TRACE_FLAG_ESTOP_SAFE = 1 << 7
TRACE_FLAG_LATCHED = 1 << 8
TRACE_FLAG_RECOVERY = 1 << 9


def signal_handler(signum: int, frame: object) -> None:  # pragma: no cover
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def make_run_dir(root: Path) -> Path:
    path = root / f"{now_stamp()}_limit_input_isolation_probe"
    path.mkdir(parents=True, exist_ok=False)
    return path


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "first": None, "last": None, "min": None, "max": None, "span": None, "drift": None}
    return {
        "n": len(values),
        "first": values[0],
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "span": max(values) - min(values),
        "drift": values[-1] - values[0],
    }


def decode_trace_flags(flags: int) -> dict[str, bool]:
    return {
        "enabled": bool(flags & TRACE_FLAG_ENABLED),
        "armed": bool(flags & TRACE_FLAG_ARMED),
        "moving": bool(flags & TRACE_FLAG_MOVING),
        "limit_pos_active": bool(flags & TRACE_FLAG_LIMIT_POS),
        "limit_neg_active": bool(flags & TRACE_FLAG_LIMIT_NEG),
        "home_active": bool(flags & TRACE_FLAG_HOME),
        "fault_active": bool(flags & TRACE_FLAG_FAULT),
        "estop_safe": bool(flags & TRACE_FLAG_ESTOP_SAFE),
        "latched": bool(flags & TRACE_FLAG_LATCHED),
        "recovery": bool(flags & TRACE_FLAG_RECOVERY),
    }


def pico_trace_dump(pico: Pico, log: RunLog, timeout_s: float = 4.0) -> list[dict[str, Any]]:
    """Read Pico TRACE DUMP, preserving trace/event lines Pico.command ignores."""
    rows: list[dict[str, Any]] = []
    with pico.lock:
        log.pico(">", "TRACE DUMP")
        pico.ser.write(b"TRACE DUMP\n")
        pico.ser.flush()
        deadline = time.monotonic() + timeout_s
        saw_begin = False
        while time.monotonic() < deadline:
            raw = pico.ser.readline()
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace").strip()
            log.pico("<", text)
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if obj.get("event") == "TRACE_BEGIN":
                saw_begin = True
                continue
            if obj.get("trace"):
                flags = int(obj.get("flags", 0))
                rows.append({**obj, **decode_trace_flags(flags)})
                continue
            if obj.get("event") == "TRACE_END":
                return rows
            if obj.get("ok") is False:
                raise CommissionAbort(f"Pico TRACE DUMP rejected: {obj}")
        if saw_begin:
            raise CommissionAbort("TRACE DUMP timed out after TRACE_BEGIN")
        raise CommissionAbort("TRACE DUMP timed out before TRACE_BEGIN")


def trace_prepare(pico: Pico, args: argparse.Namespace) -> None:
    with contextlib.suppress(Exception):
        pico.command("TRACE STOP", timeout_s=0.8)
    pico.command("TRACE CLEAR", timeout_s=1.0)
    pico.command(f"TRACE START {args.trace_period_us} {args.trace_samples}", timeout_s=1.0)


def trace_stop_dump(pico: Pico, log: RunLog, run_dir: Path, name: str) -> list[dict[str, Any]]:
    with contextlib.suppress(Exception):
        pico.command("TRACE STOP", timeout_s=1.0)
    rows = pico_trace_dump(pico, log)
    if rows:
        path = run_dir / f"{name}_trace.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    return rows


def sample_status_window(
    *,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    name: str,
    duration_s: float,
    interval_s: float,
    stop_on_latch: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = time.monotonic()
    while time.monotonic() - start < duration_s:
        if STOP_REQUESTED:
            break
        try:
            row = pico.status()
        except Exception as exc:
            rows.append({"ok": False, "elapsed_s": time.monotonic() - start, "error": str(exc)})
            break
        row["elapsed_s"] = time.monotonic() - start
        rows.append(row)
        if bool(row.get("latched")) and stop_on_latch:
            log.say(f"{name}: Pico latched as {row.get('latch')}; ending this phase after trace capture.")
            break
        time.sleep(interval_s)
    if rows:
        path = run_dir / f"{name}_host_status.csv"
        keys: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
    return rows


def summarize_phase(name: str, host_rows: list[dict[str, Any]], trace_rows: list[dict[str, Any]], action_errors: list[str]) -> dict[str, Any]:
    host_raw_lp = [int(r["raw_limit_pos"]) for r in host_rows if "raw_limit_pos" in r]
    host_active_lp = [bool(r.get("limit_pos_active")) for r in host_rows if "limit_pos_active" in r]
    host_latched = [bool(r.get("latched")) for r in host_rows if "latched" in r]
    host_enc = [float(r["encoder_position"]) for r in host_rows if "encoder_position" in r]
    host_ferr = [float(r["following_error"]) for r in host_rows if "following_error" in r]
    host_invalid = [int(r["encoder_invalid"]) for r in host_rows if "encoder_invalid" in r]
    trace_lp = [bool(r.get("limit_pos_active")) for r in trace_rows]
    trace_latched = [bool(r.get("latched")) for r in trace_rows]
    trace_fault = [bool(r.get("fault_active")) for r in trace_rows]
    trace_enc = [float(r["enc"]) for r in trace_rows if "enc" in r]
    trace_ferr = [float(r["ferr"]) for r in trace_rows if "ferr" in r]

    def first_time(rows: list[dict[str, Any]], key: str, scale: float = 1.0) -> float | None:
        for r in rows:
            if bool(r.get(key)):
                t = r.get("elapsed_s") if "elapsed_s" in r else (float(r.get("t_us", 0)) / 1_000_000.0)
                return float(t) * scale
        return None

    invalid_delta = None
    if host_invalid:
        invalid_delta = host_invalid[-1] - host_invalid[0]

    return {
        "name": name,
        "action_errors": action_errors,
        "host_samples": len(host_rows),
        "trace_samples": len(trace_rows),
        "host_duration_s": host_rows[-1].get("elapsed_s") if host_rows else 0,
        "host_raw_limit_pos_unique": sorted(set(host_raw_lp)),
        "host_raw_limit_pos_high_count": sum(1 for v in host_raw_lp if v == 1),
        "host_raw_limit_pos_low_count": sum(1 for v in host_raw_lp if v == 0),
        "host_limit_pos_active_count": sum(1 for v in host_active_lp if v),
        "host_first_limit_pos_active_s": first_time(host_rows, "limit_pos_active"),
        "host_latched_count": sum(1 for v in host_latched if v),
        "host_first_latched_s": first_time(host_rows, "latched"),
        "host_final_latch": host_rows[-1].get("latch") if host_rows else None,
        "host_encoder_position": stats(host_enc),
        "host_following_error": stats(host_ferr),
        "host_encoder_invalid_delta": invalid_delta,
        "trace_limit_pos_active_count": sum(1 for v in trace_lp if v),
        "trace_first_limit_pos_active_s": first_time(trace_rows, "limit_pos_active"),
        "trace_latched_count": sum(1 for v in trace_latched if v),
        "trace_first_latched_s": first_time(trace_rows, "latched"),
        "trace_fault_active_count": sum(1 for v in trace_fault if v),
        "trace_encoder_position": stats(trace_enc),
        "trace_following_error": stats(trace_ferr),
        "host_status_csv": f"{name}_host_status.csv" if host_rows else None,
        "trace_csv": f"{name}_trace.csv" if trace_rows else None,
        "limit_pos_went_active": (sum(1 for v in host_active_lp if v) > 0) or (sum(1 for v in trace_lp if v) > 0),
        "latched": (sum(1 for v in host_latched if v) > 0) or (sum(1 for v in trace_latched if v) > 0),
    }


def configure_for_diagnostic(vix: Vix, pico: Pico, args: argparse.Namespace, gains: Gains = ZERO_GAINS, cl_percent: int = 1) -> None:
    temporary_vix_setup(vix, gains, cl_percent=cl_percent, tl_counts=args.tl_counts, iw_counts=args.iw_counts)
    configure_pico_policy(pico, args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN, watchdog_ms=args.watchdog_ms)
    pico.config("FERRMAX", args.ferrmax_counts)


def force_pico_ready(pico: Pico) -> None:
    with contextlib.suppress(Exception):
        pico.command("ABORT", timeout_s=0.8)
    with contextlib.suppress(Exception):
        pico.command("ENABLE 0", timeout_s=0.8)
    with contextlib.suppress(Exception):
        pico.command("DISARM", timeout_s=0.8)
    with contextlib.suppress(Exception):
        pico.command("CLEAR", timeout_s=0.8)
    with contextlib.suppress(Exception):
        pico.command("DIAG CLEAR", timeout_s=0.8)
    safe_pico_zero(pico, reason="limit_input_isolation")


def run_phase(
    *,
    name: str,
    vix: Vix,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    args: argparse.Namespace,
    action: str,
    duration_s: float,
) -> dict[str, Any]:
    action_errors: list[str] = []
    log.say(f"\nLIMIT INPUT PHASE: {name} ({action})")
    with contextlib.suppress(Exception):
        pico.stop_heartbeat()
    with contextlib.suppress(Exception):
        deenergize_drive(vix, pico, verify=False)
    force_pico_ready(pico)
    configure_for_diagnostic(vix, pico, args, ZERO_GAINS, 1)

    trace_prepare(pico, args)
    try:
        if action == "off_baseline":
            pass
        elif action == "x4_enable_only":
            pico.command("ARM I_UNDERSTAND", timeout_s=1.0)
            pico.start_heartbeat()
            pico.command("ENABLE 1", timeout_s=1.0)
        elif action == "vix_on_zero_gains":
            pico.command("ARM I_UNDERSTAND", timeout_s=1.0)
            pico.start_heartbeat()
            pico.command("ENABLE 1", timeout_s=1.0)
            try:
                vix.command("ON", timeout_s=1.2, quiet_s=0.15, allow_error=True)
            except Exception as exc:
                action_errors.append(f"vix ON reply failed/noncritical: {exc}")
        elif action == "vix_on_soft_gain":
            pico.command("ARM I_UNDERSTAND", timeout_s=1.0)
            pico.start_heartbeat()
            pico.command("ENABLE 1", timeout_s=1.0)
            try:
                vix.command("ON", timeout_s=1.2, quiet_s=0.15, allow_error=True)
            except Exception as exc:
                action_errors.append(f"vix ON reply failed/noncritical: {exc}")
            time.sleep(args.soft_gain_delay_s)
            try:
                configure_for_diagnostic(vix, pico, args, SOFT_GAIN, 1)
            except Exception as exc:
                action_errors.append(f"soft gain apply failed: {exc}")
        else:
            raise CommissionAbort(f"unknown action {action!r}")

        host_rows = sample_status_window(
            pico=pico,
            log=log,
            run_dir=run_dir,
            name=name,
            duration_s=duration_s,
            interval_s=args.host_sample_interval_s,
            stop_on_latch=True,
        )
    except Exception as exc:
        action_errors.append(str(exc))
        host_rows = []
    finally:
        with contextlib.suppress(Exception):
            pico.stop_heartbeat()
        with contextlib.suppress(Exception):
            vix.off()
        with contextlib.suppress(Exception):
            pico.command("ENABLE 0", timeout_s=0.8)
        with contextlib.suppress(Exception):
            pico.command("DISARM", timeout_s=0.8)
        # TRACE DUMP requires Pico disabled and not moving.  A LIMIT latch should
        # already have dropped enable; explicit disable above covers no-latch cases.
        try:
            trace_rows = trace_stop_dump(pico, log, run_dir, name)
        except Exception as exc:
            action_errors.append(f"trace dump failed: {exc}")
            trace_rows = []
        with contextlib.suppress(Exception):
            pico.command("CLEAR", timeout_s=0.8)
            pico.command("DIAG CLEAR", timeout_s=0.8)

    summary = summarize_phase(name, host_rows, trace_rows, action_errors)
    log.say(
        f"{name}: host_samples={summary['host_samples']}, trace_samples={summary['trace_samples']}, "
        f"limit_active={summary['limit_pos_went_active']}, latched={summary['latched']}, "
        f"host_raw_unique={summary['host_raw_limit_pos_unique']}, "
        f"first_active_trace_s={summary['trace_first_limit_pos_active_s']}, "
        f"encoder_span={summary['host_encoder_position'].get('span')} counts, errors={action_errors}"
    )
    (run_dir / f"{name}_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def classify(phases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    findings: list[str] = []
    next_steps: list[str] = []
    likely = "unknown"

    off = phases.get("off_baseline", {})
    en = phases.get("x4_enable_only", {})
    on = phases.get("vix_on_zero_gains", {})
    soft = phases.get("vix_on_soft_gain", {})

    if off.get("limit_pos_went_active"):
        likely = "limit_pos_polarity_or_wiring_fault_even_when_off"
        findings.append("+limit went active while Pico/ViX enable was OFF; this points to polarity, wiring, pull-up/sensor state, or a real active limit before drive-enable effects.")
        next_steps.append("Check raw_limit_pos away from the physical +limit. With the current policy it should stay inactive continuously before any enable tests.")
    elif en.get("limit_pos_went_active") or en.get("latched"):
        likely = "x4_enable_reference_or_transistor_coupling_into_limit_input"
        findings.append("OFF baseline was clean, but X4 enable-only produced +limit activity/latch before ViX ON; focus on Pico GP11 transistor enable wiring, X4 0V reference, X5 0V reference, and routing/coupling.")
        next_steps.append("Try a one-off manual direct X4 pin 11-to-X4 pin 3 enable jumper diagnostic, or reroute/shield the X4 enable wire away from X5 limit wiring.")
    elif on.get("limit_pos_went_active") or on.get("latched"):
        likely = "vix_power_stage_on_or_motor_emi_coupling_into_x5_limit_input"
        findings.append("OFF and X4 enable-only were clean, but ViX ON zero-gain produced +limit activity/latch; focus on X5 limit input conditioning, shield/reference bonding, motor U/V/W routing, and ViX power-stage EMI.")
        next_steps.append("Keep X5 limit wiring away from U/V/W and HV. Add stronger external conditioning/debounce/RC or Schmitt buffering before Pico if the raw line glitches.")
    elif soft.get("limit_pos_went_active") or soft.get("latched"):
        likely = "closed_loop_hold_current_or_gain_state_couples_into_limit_input"
        findings.append("Zero-gain ON was clean, but applying the soft hold gain produced +limit activity/latch; the glitch is coupled to motor current/servo activity rather than the enable edge alone.")
        next_steps.append("Treat X5 limit input as EMI-sensitive under motor current; condition the line before more gain tuning.")
    else:
        likely = "limit_input_clean_in_this_probe"
        findings.append("No +limit activity was captured in OFF, X4 enable-only, ViX ON zero-gain, or soft-gain phases.")
        next_steps.append("The v4.66 LIMIT_POS latch may have been intermittent; repeat once, then return to the post-enable settle probe if still clean.")

    for label, phase in phases.items():
        if phase.get("action_errors"):
            findings.append(f"{label} had action/errors: {phase.get('action_errors')}")

    return {"likely_blocker": likely, "findings": findings, "next_steps": next_steps}


def run_probe(args: argparse.Namespace) -> int:
    run_dir = make_run_dir(args.output_root)
    log = RunLog(run_dir)
    vix: Vix | None = None
    pico: Pico | None = None
    code = 1
    report: dict[str, Any] = {
        "version": "v4.68",
        "created": datetime.now().isoformat(timespec="seconds"),
        "test_intent": "Diagnose false/noisy LIMIT_POS latch with no STEP/DIR moves. Safety remains enabled; trace captures any transient limit event before the Pico disables GP11.",
        "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "trace_flags": {
            "enabled": TRACE_FLAG_ENABLED,
            "armed": TRACE_FLAG_ARMED,
            "moving": TRACE_FLAG_MOVING,
            "limit_pos_active": TRACE_FLAG_LIMIT_POS,
            "limit_neg_active": TRACE_FLAG_LIMIT_NEG,
            "home_active": TRACE_FLAG_HOME,
            "fault_active": TRACE_FLAG_FAULT,
            "estop_safe": TRACE_FLAG_ESTOP_SAFE,
            "latched": TRACE_FLAG_LATCHED,
            "recovery": TRACE_FLAG_RECOVERY,
        },
    }
    try:
        log.say("LIMIT INPUT ISOLATION PROBE v4.68: no STEP/DIR moves; capture LIMIT_POS glitches with Pico trace.")
        log.say(f"Evidence directory: {run_dir}")
        vix = Vix(args.vix_port, args.vix_baud, log)
        pico = Pico(args.pico_port, args.pico_baud, log)
        report["preflight"] = preflight_with_serial_retry(vix, pico, log, run_dir, bench_no_estop=args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN)

        phases: dict[str, dict[str, Any]] = {}
        phases["off_baseline"] = run_phase(
            name="off_baseline", vix=vix, pico=pico, log=log, run_dir=run_dir,
            args=args, action="off_baseline", duration_s=args.off_baseline_s,
        )
        phases["x4_enable_only"] = run_phase(
            name="x4_enable_only", vix=vix, pico=pico, log=log, run_dir=run_dir,
            args=args, action="x4_enable_only", duration_s=args.enable_only_s,
        )
        phases["vix_on_zero_gains"] = run_phase(
            name="vix_on_zero_gains", vix=vix, pico=pico, log=log, run_dir=run_dir,
            args=args, action="vix_on_zero_gains", duration_s=args.vix_on_s,
        )
        # Only run the soft-gain phase if the zero-gain ON phase did not already
        # show the problem; otherwise it adds no useful safety information.
        if not phases["vix_on_zero_gains"].get("latched") and not phases["vix_on_zero_gains"].get("limit_pos_went_active"):
            phases["vix_on_soft_gain"] = run_phase(
                name="vix_on_soft_gain", vix=vix, pico=pico, log=log, run_dir=run_dir,
                args=args, action="vix_on_soft_gain", duration_s=args.soft_gain_s,
            )
        else:
            phases["vix_on_soft_gain"] = {"skipped": True, "reason": "zero-gain ON already produced limit activity/latch"}

        report["phases"] = phases
        verdict = classify(phases)
        report["verdict"] = verdict
        (run_dir / "LIMIT_INPUT_ISOLATION_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        lines = [
            "LIMIT INPUT ISOLATION PROBE VERDICT",
            f"likely_blocker: {verdict.get('likely_blocker')}",
            "",
            "Phase summary:",
        ]
        for label, phase in phases.items():
            if phase.get("skipped"):
                lines.append(f"- {label}: skipped ({phase.get('reason')})")
            else:
                lines.append(
                    f"- {label}: limit_active={phase.get('limit_pos_went_active')}, "
                    f"latched={phase.get('latched')}, raw_unique={phase.get('host_raw_limit_pos_unique')}, "
                    f"trace_first_limit_s={phase.get('trace_first_limit_pos_active_s')}, "
                    f"host_encoder_span={phase.get('host_encoder_position', {}).get('span')} counts"
                )
        lines.extend([
            "",
            "Findings:",
            *[f"- {x}" for x in verdict.get("findings", [])],
            "",
            "Next steps:",
            *[f"- {x}" for x in verdict.get("next_steps", [])],
            "",
        ])
        (run_dir / "LIMIT_INPUT_ISOLATION_VERDICT.txt").write_text("\n".join(lines), encoding="utf-8")
        log.say("\n" + "\n".join(lines))
        code = 0
    except Exception as exc:
        report["abort"] = str(exc)
        report["verdict"] = {
            "likely_blocker": "aborted_before_verdict",
            "findings": ["The limit-isolation probe stopped before final classification; do not treat this run as a pass."],
            "next_steps": ["Inspect LIMIT_INPUT_ISOLATION_SUMMARY.json and per-phase CSV files, then rerun after clearing the physical/Pico latch."],
        }
        with contextlib.suppress(Exception):
            (run_dir / "LIMIT_INPUT_ISOLATION_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            (run_dir / "LIMIT_INPUT_ISOLATION_VERDICT.txt").write_text(
                "LIMIT INPUT ISOLATION PROBE VERDICT\n"
                "likely_blocker: aborted_before_verdict\n"
                f"abort: {exc}\n",
                encoding="utf-8",
            )
        log.say(f"\nABORT: Limit-input isolation probe stopped safely: {exc}")
        code = 1
    finally:
        if pico is not None:
            with contextlib.suppress(Exception):
                pico.stop_heartbeat()
        if vix is not None and pico is not None:
            with contextlib.suppress(Exception):
                deenergize_drive(vix, pico, verify=False)
        if vix is not None:
            with contextlib.suppress(Exception):
                vix.reset_restore()
            with contextlib.suppress(Exception):
                vix.close()
        if pico is not None:
            with contextlib.suppress(Exception):
                pico.close()
        log.say(f"Evidence directory: {run_dir}")
        log.close()
    return code


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V4.67 limit input isolation probe; no commanded STEP/DIR moves")
    p.add_argument("--vix-port", default="/dev/ttyUSB0")
    p.add_argument("--pico-port", default="/dev/ttyACM0")
    p.add_argument("--vix-baud", type=int, default=9600)
    p.add_argument("--pico-baud", type=int, default=115200)
    p.add_argument("--bench-no-estop", action="store_true")
    p.add_argument("--output-root", type=Path, default=Path.home() / "vix100nm_runs")
    p.add_argument("--watchdog-ms", type=int, default=5000)
    p.add_argument("--iw-counts", type=int, default=1000)
    p.add_argument("--tl-counts", type=int, default=13000)
    p.add_argument("--ferrmax-counts", type=int, default=13000)
    p.add_argument("--trace-period-us", type=int, default=1000)
    p.add_argument("--trace-samples", type=int, default=4096)
    p.add_argument("--host-sample-interval-s", type=float, default=0.05)
    p.add_argument("--off-baseline-s", type=float, default=3.0)
    p.add_argument("--enable-only-s", type=float, default=3.0)
    p.add_argument("--vix-on-s", type=float, default=4.0)
    p.add_argument("--soft-gain-s", type=float, default=4.0)
    p.add_argument("--soft-gain-delay-s", type=float, default=0.5)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(run_probe(parse_args()))
