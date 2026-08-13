#!/usr/bin/env python3
"""Threshold-characterization motion sweep for ViX500AE/MX80L/Pico2.

V4.77 is a supervised threshold-characterization sweep. It does not try to declare a final 100 nm pass. It maps the practical small-signal motion threshold using the best v4.76 candidates and a dense amplitude ladder:

  1. Configure ViX/Pico safely while OFF.
  2. Enable once with zero PIVF gains and low CL, allowing one bounded ON kick.
  3. Apply confirmed candidate mid_gi0p05_gp1p5_gv1_cl2.
  4. Re-reference the ViX at the post-kick/post-gain location.
  5. Run sham/no-step, then +/-100 count (1 um), +/-50 count (500 nm),
     +/-75, +/-50, +/-40, +/-30, +/-25, +/-20, +/-15, and +/-10 count ABBA blocks from the already-energised state.

The Pico cannot ZERO while enabled, so Pico following_error is not used as an
absolute endpoint pass/fail metric after the enable kick.  Motion quality is
measured by incremental encoder response from each leg's local start position.
Fault line, X5 limits, encoder-invalid, bounded movement, and host watchdog are
still active safety gates.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import shutil
import signal
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import vix100nm_commission as vixcore  # type: ignore
from vix100nm_commission import (  # type: ignore
    CommissionAbort,
    Gains,
    RunLog,
    Pico,
    Vix,
    configure_pico_policy,
    deenergize_drive,
    preflight_with_serial_retry,
    prepare_pico_for_enable_with_stale_vix_reset,
    safe_pico_zero,
    temporary_vix_setup,
)

# Reuse the already-debugged Pico-fast helpers from v4.69.  Those helpers avoid
# slow/fragile ViX R(PT)/R(ST2) reports inside tight post-enable windows.
import vix_post_enable_settle_probe as settle  # type: ignore

STOP_REQUESTED = False
NM_PER_COUNT = 10
DIRINV = False
ENCSIGN = -1
ZERO_GAINS = Gains(0, 0, 0, 0, 0)

FOCUSED_CANDIDATES: tuple[tuple[str, Gains, int], ...] = (
    # v4.76 showed this is the best small-motion candidate: clean 1 um,
    # good 500 nm, correct-direction 200 nm, but not yet 100 nm.
    ("stage4_gi0p2_gp2_gv1_cl2", Gains(0, 0.20, 2.00, 1.00, 0), 2),
    # This had good 500 nm performance and is a less-integral comparison.
    ("stage2_gi0p1_gp2_gv1_cl2", Gains(0, 0.10, 2.00, 1.00, 0), 2),
    # This is the main damping comparison.
    ("damped_gi0p2_gp2_gv1p5_cl2", Gains(0, 0.20, 2.00, 1.50, 0), 2),
)


def signal_handler(signum: int, frame: object) -> None:  # pragma: no cover
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def make_run_dir(root: Path) -> Path:
    path = root / f"{now_stamp()}_threshold_characterization"
    path.mkdir(parents=True, exist_ok=False)
    return path


def bundle_run_dir(run_dir: Path) -> Path:
    archive_base = run_dir.parent / run_dir.name
    zip_path = archive_base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    made = shutil.make_archive(str(archive_base), "zip", root_dir=run_dir.parent, base_dir=run_dir.name)
    return Path(made)


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "min": None, "max": None, "span": None, "median": None, "p95": None, "max_abs": None}
    ordered = sorted(values)
    idx95 = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "span": max(values) - min(values),
        "median": statistics.median(values),
        "p95": ordered[idx95],
        "max_abs": max(abs(v) for v in values),
    }


def prepare_local_zero_off(vix: Vix, pico: Pico, log: RunLog, args: argparse.Namespace) -> dict[str, Any]:
    """Relaxed OFF local-zero prep copied from the diagnostic workflow.

    This is not the final validation gate.  It just prevents stale post-fault
    ViX references from poisoning the enable-once workflow.
    """
    temporary_vix_setup(vix, ZERO_GAINS, cl_percent=args.kick_cl_percent, tl_counts=args.tl_counts, iw_counts=args.iw_counts)
    configure_pico_policy(pico, args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN, watchdog_ms=args.watchdog_ms)
    pico.config("FERRMAX", args.ferrmax_counts)

    old_counts = vixcore.LOCAL_ZERO_STATIONARY_COUNTS
    old_window = vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S
    old_wait = vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S
    vixcore.LOCAL_ZERO_STATIONARY_COUNTS = int(args.local_zero_settle_counts)
    vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S = float(args.local_zero_window_s)
    vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S = float(args.local_zero_max_wait_s)
    prep: dict[str, Any] = {"phase": "threshold_motion_pre_enable_local_zero"}
    try:
        evidence = prepare_pico_for_enable_with_stale_vix_reset(
            vix,
            pico,
            log,
            prep,
            gains=ZERO_GAINS,
            cl_percent=args.kick_cl_percent,
            tl_counts=args.tl_counts,
            ferrmax=args.ferrmax_counts,
            bench_no_estop=args.bench_no_estop,
            dirinv=DIRINV,
            encsign=ENCSIGN,
            watchdog_ms=args.watchdog_ms,
        )
        prep["evidence"] = evidence
        return prep
    finally:
        vixcore.LOCAL_ZERO_STATIONARY_COUNTS = old_counts
        vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S = old_window
        vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S = old_wait


def pico_status_checked(pico: Pico, *, context: str, invalid_baseline: int | None = None) -> dict[str, Any]:
    status = pico.status()
    if bool(status.get("latched")):
        raise CommissionAbort(f"Pico latch during {context}: {status}")
    if bool(status.get("fault_active")):
        raise CommissionAbort(f"Pico reports ViX fault line active during {context}: {status}")
    if invalid_baseline is not None and int(status.get("encoder_invalid", 0)) != int(invalid_baseline):
        raise CommissionAbort(
            f"Encoder-invalid counter changed during {context}: "
            f"{invalid_baseline}->{status.get('encoder_invalid')}"
        )
    return status


def wait_relative_endpoint(
    pico: Pico,
    *,
    start_position: int,
    command_counts: int,
    invalid_baseline: int,
    max_s: float,
    goal_counts: int,
    stable_span_counts: int,
    movement_limit_counts: int,
    context: str,
) -> dict[str, Any]:
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    while time.monotonic() - started < max_s:
        if STOP_REQUESTED:
            raise CommissionAbort("operator_stop")
        pico.check_heartbeat()
        status = pico_status_checked(pico, context=context, invalid_baseline=invalid_baseline)
        response = int(status["encoder_position"]) - int(start_position)
        if abs(response) > int(movement_limit_counts):
            raise CommissionAbort(
                f"Movement exceeded {movement_limit_counts} counts during {context}: response={response}, status={status}"
            )
        row = {
            "elapsed_s": time.monotonic() - started,
            "encoder_position": int(status["encoder_position"]),
            "command_position": int(status.get("command_position", 0)),
            "following_error": int(status.get("following_error", 0)),
            "response_counts": response,
            "relative_error_counts": int(command_counts) - response,
            "motion": str(status.get("motion")),
        }
        samples.append(row)
        tail = [r for r in samples if row["elapsed_s"] - float(r["elapsed_s"]) <= 0.45]
        if len(tail) >= 5:
            responses = [float(r["response_counts"]) for r in tail]
            span = max(responses) - min(responses)
            error = abs(float(row["relative_error_counts"]))
            if error <= goal_counts and span <= stable_span_counts and str(status.get("motion")) != "MOVING":
                return {
                    "settled": True,
                    "settle_time_s": row["elapsed_s"],
                    "goal_counts": goal_counts,
                    "stable_span_counts": stable_span_counts,
                    "tail_span_counts": span,
                    "final_response_counts": response,
                    "final_error_counts": row["relative_error_counts"],
                    "samples": samples,
                }
        time.sleep(args_global_sample_interval())
    errors = [abs(float(r["relative_error_counts"])) for r in samples]
    tail_responses = [float(r["response_counts"]) for r in samples[-8:]]
    return {
        "settled": False,
        "settle_time_s": time.monotonic() - started,
        "goal_counts": goal_counts,
        "stable_span_counts": stable_span_counts,
        "tail_span_counts": (max(tail_responses) - min(tail_responses) if len(tail_responses) >= 2 else None),
        "late_abs_error_counts": statistics.median(errors[-4:]) if errors else None,
        "final_response_counts": samples[-1]["response_counts"] if samples else None,
        "final_error_counts": samples[-1]["relative_error_counts"] if samples else None,
        "samples": samples,
    }


# Global interval so wait_relative_endpoint remains simple and py_compile-safe.
_SAMPLE_INTERVAL_S = 0.05


def args_global_sample_interval() -> float:
    return _SAMPLE_INTERVAL_S


def endpoint_goal_counts(amplitude: int) -> int:
    # v4.76 endpoint observation gate.  This controls when a leg is considered
    # settled for logging.  Failing this gate no longer aborts; it becomes part
    # of the candidate score.
    a = abs(amplitude)
    if a <= 10:
        return 12
    if a <= 20:
        return 15
    if a <= 50:
        return 20
    return 35


def endpoint_max_s(amplitude: int) -> float:
    a = abs(amplitude)
    if a <= 20:
        return 3.0
    if a <= 50:
        return 4.0
    return 5.0


def response_acceptance_window(amplitude: int) -> tuple[float, float]:
    # Threshold characterization window. For small commands this is deliberately
    # wider than a final validation gate; the point is to find where the stage
    # stops responding, not to overfit pass/fail around one number.
    a = abs(amplitude)
    if a <= 10:
        return 3.0, 22.0
    if a <= 15:
        return 5.0, 28.0
    if a <= 20:
        return 8.0, 35.0
    if a <= 25:
        return 10.0, 42.0
    if a <= 30:
        return 14.0, 50.0
    if a <= 40:
        return 22.0, 60.0
    if a <= 50:
        return 30.0, 72.0
    if a <= 75:
        return 48.0, 105.0
    if a <= 100:
        return 70.0, 135.0
    return 0.65 * a, 1.35 * a


def parse_amplitudes(text: str) -> list[int]:
    values: list[int] = []
    for part in text.replace(';', ',').split(','):
        clean = part.strip()
        if not clean:
            continue
        value = int(clean)
        if value <= 0 or value > 200:
            raise ValueError(f"amplitude out of bounded range 1..200 counts: {value}")
        values.append(value)
    if not values:
        raise ValueError("empty amplitude list")
    out: list[int] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def blocks_for_amplitude(amplitude: int) -> int:
    # Keep runtime bounded while giving extra repeats near the suspected threshold.
    if amplitude >= 50:
        return 1
    if amplitude >= 20:
        return 2
    return 3


def amplitude_iter_from_args(args: argparse.Namespace) -> list[tuple[int, int]]:
    return [(amp, blocks_for_amplitude(amp)) for amp in parse_amplitudes(args.amplitudes)]


def issue_move_already_on(pico: Pico, delta: int, rate: int, accel: int, move_id: int) -> tuple[int, dict[str, Any]]:
    # vixcore.issue_move is already hardened for stale move IDs and motion state.
    return vixcore.issue_move(pico, delta, rate, accel, move_id)


def run_sham_window(
    *,
    pico: Pico,
    run_dir: Path,
    name: str,
    duration_s: float,
    invalid_baseline: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    start = time.monotonic()
    first: int | None = None
    while time.monotonic() - start < duration_s:
        status = pico_status_checked(pico, context=name, invalid_baseline=invalid_baseline)
        pos = int(status["encoder_position"])
        if first is None:
            first = pos
        rows.append({
            "elapsed_s": time.monotonic() - start,
            "encoder_position": pos,
            "delta_from_first": pos - first,
            "command_position": int(status.get("command_position", 0)),
            "following_error": int(status.get("following_error", 0)),
        })
        time.sleep(args_global_sample_interval())
    if rows:
        with (run_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    vals = [float(r["delta_from_first"]) for r in rows]
    summary = {
        "name": name,
        "duration_s": duration_s,
        "samples": len(rows),
        "delta_from_first": stats(vals),
        "first_row": rows[0] if rows else None,
        "final_row": rows[-1] if rows else None,
    }
    (run_dir / f"{name}_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary



def tail_gate_from_sample_csv(summary: dict[str, Any], run_dir: Path, *, tail_s: float, span_counts: int, drift_counts: int) -> dict[str, Any]:
    """Gate only the late quiet tail of a hold/sham window.

    v4.71 showed Candidate B can have a one-time post-gain pull-in spike, then
    become quiet.  Final nano motion should be judged after the already-on
    servo has stopped pulling in, so this helper deliberately scores the last
    tail_s seconds rather than the full hold window.
    """
    csv_name = summary.get("csv")
    if not csv_name:
        return {"passes": False, "reason": "missing_csv_name"}
    csv_path = run_dir / str(csv_name)
    if not csv_path.exists():
        return {"passes": False, "reason": f"missing_csv:{csv_path.name}"}
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return {"passes": False, "reason": "no_rows"}
    try:
        t_end = max(float(r["elapsed_s"]) for r in rows)
        tail = [r for r in rows if float(r["elapsed_s"]) >= t_end - float(tail_s)]
        vals = [float(r["pico_delta_from_reference"]) for r in tail]
    except Exception as exc:
        return {"passes": False, "reason": f"parse_error:{exc}"}
    if len(vals) < 8:
        return {"passes": False, "reason": f"insufficient_tail_samples:{len(vals)}"}
    span = max(vals) - min(vals)
    drift = vals[-1] - vals[0]
    max_abs_from_tail_first = max(abs(v - vals[0]) for v in vals)
    return {
        "passes": bool(span <= span_counts and abs(drift) <= drift_counts and max_abs_from_tail_first <= span_counts),
        "tail_s": tail_s,
        "tail_samples": len(vals),
        "tail_first": vals[0],
        "tail_last": vals[-1],
        "tail_min": min(vals),
        "tail_max": max(vals),
        "tail_span_counts": span,
        "tail_drift_counts": drift,
        "tail_max_abs_from_first_counts": max_abs_from_tail_first,
        "span_gate_counts": span_counts,
        "drift_gate_counts": drift_counts,
    }

def run_abba_relative(
    *,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    candidate_label: str,
    amplitude: int,
    blocks: int,
    rate: int,
    accel: int,
    invalid_baseline: int,
    move_id_seed: int,
) -> tuple[int, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    settles: list[dict[str, Any]] = []
    move_id = move_id_seed
    for block in range(1, blocks + 1):
        sequence = (+amplitude, -amplitude, -amplitude, +amplitude)
        if block % 2 == 0:
            sequence = tuple(-v for v in sequence)
        block_start_status = pico_status_checked(pico, context=f"{candidate_label} {amplitude} block {block} start", invalid_baseline=invalid_baseline)
        block_start_pos = int(block_start_status["encoder_position"])
        for leg, command in enumerate(sequence, 1):
            if STOP_REQUESTED:
                raise CommissionAbort("operator_stop")
            before = pico_status_checked(pico, context=f"{candidate_label} {amplitude} block {block} leg {leg} before", invalid_baseline=invalid_baseline)
            p0 = int(before["encoder_position"])
            cmd0 = int(before.get("command_position", 0))
            move_id += 1
            move_id, move_status = issue_move_already_on(pico, command, rate, accel, move_id)
            settle = wait_relative_endpoint(
                pico,
                start_position=p0,
                command_counts=command,
                invalid_baseline=invalid_baseline,
                max_s=endpoint_max_s(amplitude),
                goal_counts=endpoint_goal_counts(amplitude),
                stable_span_counts=endpoint_goal_counts(amplitude),
                movement_limit_counts=max(500, abs(amplitude) * 10 + 200),
                context=f"{candidate_label} amplitude {amplitude} block {block} leg {leg}",
            )
            after = pico_status_checked(pico, context=f"{candidate_label} {amplitude} block {block} leg {leg} after", invalid_baseline=invalid_baseline)
            p1 = int(after["encoder_position"])
            response = p1 - p0
            signed_response = response if command > 0 else -response
            row = {
                "candidate": candidate_label,
                "amplitude_counts": amplitude,
                "block": block,
                "leg": leg,
                "command_counts": command,
                "pico_start": p0,
                "pico_end": p1,
                "pico_response": response,
                "signed_response": signed_response,
                "response_error_counts": command - response,
                "abs_response_error_counts": abs(command - response),
                "closure_from_block_start_counts": p1 - block_start_pos,
                "command_position_before": cmd0,
                "command_position_after": int(after.get("command_position", 0)),
                "following_error_after": int(after.get("following_error", 0)),
                "move_id": move_id,
                "move_status": json.dumps(move_status, sort_keys=True),
                "settled": bool(settle.get("settled")),
                "settle_time_s": float(settle.get("settle_time_s") or 0.0),
                "settle_tail_span_counts": settle.get("tail_span_counts"),
                "settle_final_error_counts": settle.get("final_error_counts"),
            }
            rows.append(row)
            settle_light = dict(settle)
            sample_list = settle_light.pop("samples", [])
            settle_light["sample_count"] = len(sample_list)
            settle_light["last_samples"] = sample_list[-8:]
            settle_light.update({"block": block, "leg": leg, "command_counts": command})
            settles.append(settle_light)
            log.say(
                f"{candidate_label} amp={amplitude} block={block} leg={leg} "
                f"cmd={command:+d} response={response:+d} error={command-response:+d} "
                f"settled={settle.get('settled')} closure={p1 - block_start_pos:+d}"
            )
            if not bool(settle.get("settled")):
                # v4.76: this is an exploratory motion sweep, not final validation.
                # A stable but offset endpoint (for example v4.75 leg 4 at +67/100
                # counts with good ABBA closure) is useful data, not a reason to
                # abort the entire ladder.  Safety faults, encoder-invalid changes,
                # latches, and movement-limit violations are still hard aborts in
                # wait_relative_endpoint()/pico_status_checked().
                log.say(
                    f"{candidate_label} amp={amplitude} block={block} leg={leg} "
                    f"did not meet endpoint gate; recording and continuing if safe."
                )
    csv_path = run_dir / f"{candidate_label}_{amplitude}_counts_records.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    (run_dir / f"{candidate_label}_{amplitude}_counts_settling.json").write_text(
        json.dumps(settles, indent=2) + "\n", encoding="utf-8"
    )
    signed = [float(r["signed_response"]) for r in rows]
    errors = [float(r["abs_response_error_counts"]) for r in rows]
    endpoint_errors = [abs(float(r["settle_final_error_counts"] or r["response_error_counts"])) for r in rows]
    closures = [abs(float(r["closure_from_block_start_counts"])) for r in rows if int(r["leg"]) == 4]
    lo, hi = response_acceptance_window(amplitude)
    summary = {
        "candidate": candidate_label,
        "amplitude_counts": amplitude,
        "amplitude_nm": amplitude * NM_PER_COUNT,
        "blocks": blocks,
        "move_legs": len(rows),
        "rate_counts_per_s": rate,
        "accel_counts_per_s2": accel,
        "signed_response": stats(signed),
        "abs_response_error_counts": stats(errors),
        "endpoint_error_counts": stats(endpoint_errors),
        "closure_abs_counts": stats(closures),
        "unsettled_legs": sum(0 if r["settled"] else 1 for r in rows),
        "correct_direction_fraction": (sum(v > 0 for v in signed) / len(signed) if signed else None),
        "response_acceptance_window_counts": [lo, hi],
        "within_response_window_fraction": (sum(lo <= v <= hi for v in signed) / len(signed) if signed else None),
    }
    endpoint_gate = 25 if amplitude <= 10 else (30 if amplitude <= 20 else (40 if amplitude <= 50 else 60))
    closure_gate = 30 if amplitude <= 10 else (35 if amplitude <= 20 else (50 if amplitude <= 50 else 75))
    summary["passes_practical_gate"] = bool(
        len(rows) > 0
        and summary["unsettled_legs"] == 0
        and float(summary["correct_direction_fraction"] or 0.0) >= 1.0
        and float(summary["within_response_window_fraction"] or 0.0) >= 0.85
        and float(summary["endpoint_error_counts"].get("max_abs") or 1e9) <= endpoint_gate
        and float(summary["closure_abs_counts"].get("max_abs") or 1e9) <= closure_gate
    )
    summary["endpoint_gate_counts"] = endpoint_gate
    summary["closure_gate_counts"] = closure_gate
    median_response = summary["signed_response"].get("median")
    median_endpoint_error = summary["endpoint_error_counts"].get("median")
    max_closure = summary["closure_abs_counts"].get("max_abs")
    response_ratio = (float(median_response) / float(amplitude)) if isinstance(median_response, (int, float)) and amplitude else None
    summary["response_ratio_median"] = response_ratio
    summary["strong_threshold_gate"] = bool(
        len(rows) > 0
        and float(summary["correct_direction_fraction"] or 0.0) >= 0.90
        and response_ratio is not None and 0.65 <= float(response_ratio) <= 1.35
        and float(median_endpoint_error or 1e9) <= max(15.0, 0.40 * abs(amplitude))
        and float(max_closure or 1e9) <= max(20.0, 0.50 * abs(amplitude))
    )
    summary["usable_threshold_gate"] = bool(
        len(rows) > 0
        and float(summary["correct_direction_fraction"] or 0.0) >= 0.80
        and response_ratio is not None and 0.50 <= float(response_ratio) <= 1.60
        and float(median_endpoint_error or 1e9) <= max(20.0, 0.65 * abs(amplitude))
        and float(max_closure or 1e9) <= max(30.0, 0.85 * abs(amplitude))
    )
    if summary["strong_threshold_gate"]:
        summary["threshold_class"] = "strong"
    elif summary["usable_threshold_gate"]:
        summary["threshold_class"] = "usable"
    elif float(summary["correct_direction_fraction"] or 0.0) >= 0.75 and response_ratio is not None and float(response_ratio) > 0.20:
        summary["threshold_class"] = "partial"
    else:
        summary["threshold_class"] = "stuck_or_noise"
    (run_dir / f"{candidate_label}_{amplitude}_counts_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return move_id, summary


def classify(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    candidates = report.get("candidates", [])
    findings: list[str] = []
    next_steps: list[str] = []
    best_records: list[dict[str, Any]] = []
    for c in candidates:
        label = c.get("label")
        if c.get("error"):
            findings.append(f"{label} stopped safely: {c.get('error')}")
            continue
        if not c.get("passes_hold_gate"):
            findings.append(f"{label} did not pass the pre-motion quiet-tail hold/sham gate.")
            continue
        summaries = c.get("amplitude_summaries", {}) or {}
        strong: list[int] = []
        usable: list[int] = []
        partial: list[int] = []
        for amp_text, summary in summaries.items():
            try:
                amp = int(amp_text)
            except Exception:
                continue
            rec = {
                "candidate": label,
                "amplitude_counts": amp,
                "amplitude_nm": amp * NM_PER_COUNT,
                "threshold_class": summary.get("threshold_class"),
                "median_response_counts": summary.get("signed_response", {}).get("median"),
                "response_ratio_median": summary.get("response_ratio_median"),
                "correct_direction_fraction": summary.get("correct_direction_fraction"),
                "endpoint_error_median_counts": summary.get("endpoint_error_counts", {}).get("median"),
                "closure_max_abs_counts": summary.get("closure_abs_counts", {}).get("max_abs"),
            }
            best_records.append(rec)
            if summary.get("strong_threshold_gate"):
                strong.append(amp)
            elif summary.get("usable_threshold_gate"):
                usable.append(amp)
            elif summary.get("threshold_class") == "partial":
                partial.append(amp)
        if strong:
            findings.append(f"{label}: strongest clean threshold reached {min(strong)} counts = {min(strong)*NM_PER_COUNT} nm.")
        elif usable:
            findings.append(f"{label}: usable threshold reached {min(usable)} counts = {min(usable)*NM_PER_COUNT} nm.")
        elif partial:
            findings.append(f"{label}: partial small-signal response down to {min(partial)} counts = {min(partial)*NM_PER_COUNT} nm, but not usable yet.")
        else:
            findings.append(f"{label}: no usable threshold in the tested ladder.")

    qualified = [r for r in best_records if r.get("threshold_class") in {"strong", "usable"}]
    partials = [r for r in best_records if r.get("threshold_class") == "partial"]
    def score(r: dict[str, Any]) -> tuple[int, float, float, float]:
        return (
            int(r.get("amplitude_counts") or 999999),
            float(r.get("endpoint_error_median_counts") if r.get("endpoint_error_median_counts") is not None else 1e9),
            float(r.get("closure_max_abs_counts") if r.get("closure_max_abs_counts") is not None else 1e9),
            -float(r.get("correct_direction_fraction") or 0.0),
        )
    best = min(qualified, key=score) if qualified else None
    best_partial = min(partials, key=score) if partials else None

    if best:
        likely = "threshold_characterization_completed_usable_threshold_found"
        next_steps.append(
            f"Use {best['candidate']} for the next proof around {best['amplitude_counts']} counts "
            f"({best['amplitude_nm']} nm), then tune toward the next smaller amplitude."
        )
        if int(best["amplitude_counts"]) <= 10:
            next_steps.append("A 100 nm candidate exists; next run should be longer repeatability validation at this exact position.")
        elif int(best["amplitude_counts"]) <= 20:
            next_steps.append("200 nm looks within reach; try integrator/current/profile refinements before claiming 100 nm.")
        else:
            next_steps.append("Do not claim 100 nm yet; use the threshold result to decide whether to accept sub-micron motion or investigate friction/deadband/current threshold.")
    elif best_partial:
        likely = "threshold_characterization_completed_partial_only"
        next_steps.append(
            f"Best partial response was {best_partial['candidate']} at {best_partial['amplitude_counts']} counts "
            f"({best_partial['amplitude_nm']} nm). Run a targeted current/profile/deadband test before another 100 nm proof."
        )
    else:
        likely = "threshold_characterization_no_small_signal_response"
        next_steps.append("Return to gain/current/commutation/mechanical threshold diagnosis; do not run 100 nm proof yet.")

    return {
        "likely_blocker_or_status": likely,
        "best_usable_record": best,
        "best_partial_record": best_partial,
        "findings": findings,
        "next_steps": next_steps,
        "all_threshold_records": sorted(best_records, key=score),
        "settings_used": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
    }


def run_probe(args: argparse.Namespace) -> int:
    global _SAMPLE_INTERVAL_S
    _SAMPLE_INTERVAL_S = float(args.sample_interval_s)
    run_dir = make_run_dir(args.output_root)
    log = RunLog(run_dir)
    vix: Vix | None = None
    pico: Pico | None = None
    code = 1
    report: dict[str, Any] = {
        "version": "v4.77",
        "created": datetime.now().isoformat(timespec="seconds"),
        "test_intent": "Threshold-characterization: enable once, apply best v4.76 candidates already energised, then map 1000/750/500/400/300/250/200/150/100 nm response without treating one endpoint miss as a final failure.",
        "amplitude_plan": amplitude_iter_from_args(args),
        "candidates_planned": [{"label": l, "gains": asdict(g), "cl_percent": cl} for l, g, cl in FOCUSED_CANDIDATES],
        "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
    }
    try:
        log.say("THRESHOLD CHARACTERIZATION v4.77: best v4.76 candidates; dense 1000/750/500/400/300/250/200/150/100 nm ladder. Stay present.")
        log.say(f"Evidence directory: {run_dir}")
        vix = Vix(args.vix_port, args.vix_baud, log)
        pico = Pico(args.pico_port, args.pico_baud, log)
        report["preflight"] = preflight_with_serial_retry(vix, pico, log, run_dir, bench_no_estop=args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN)

        with contextlib.suppress(Exception):
            deenergize_drive(vix, pico, verify=False)
        with contextlib.suppress(Exception):
            pico.force_safe()
        with contextlib.suppress(Exception):
            pico.command("CLEAR")
            pico.command("DIAG CLEAR")
        safe_pico_zero(pico, reason="threshold_motion_initial")
        report["pre_enable_local_zero"] = prepare_local_zero_off(vix, pico, log, args)
        reference_before_enable = settle.snapshot(vix, pico)
        report["reference_before_enable"] = reference_before_enable

        report["off_pre_enable_baseline"] = settle.sample_window(
            vix=vix,
            pico=pico,
            log=log,
            run_dir=run_dir,
            name="threshold_off_pre_enable_baseline",
            duration_s=args.off_baseline_s,
            interval_s=args.sample_interval_s,
            reference=reference_before_enable,
            min_samples=args.min_samples,
            abort_from_reference_counts=args.max_allow_kick_counts,
            abort_within_window_counts=args.pre_off_abort_span_counts,
        )

        log.say("Enabling once with zero gains and low current clamp; allowing bounded ON kick.")
        pico.start_heartbeat()
        before_on = settle.snapshot(vix, pico)
        handshake = settle.energize_once_without_st2_poll(vix, pico)
        after_on = settle.snapshot(vix, pico)
        report["energize_handshake"] = {**handshake, "before_on": before_on, "after_on": after_on}
        report["kick_window"] = settle.sample_window(
            vix=vix,
            pico=pico,
            log=log,
            run_dir=run_dir,
            name="threshold_post_enable_kick_window_zero_gains",
            duration_s=args.kick_window_s,
            interval_s=args.sample_interval_s,
            reference=reference_before_enable,
            min_samples=args.min_samples,
            abort_from_reference_counts=args.max_allow_kick_counts,
            abort_within_window_counts=None,
        )
        if report["kick_window"].get("hard_stop"):
            raise CommissionAbort(f"Hard stop during bounded kick window: {report['kick_window'].get('hard_stop')}")

        invalid_baseline = int(pico.status().get("encoder_invalid", 0))
        move_id_seed = int(time.time()) & 0x7FFFFFFF
        candidate_reports: list[dict[str, Any]] = []
        for label, gains, cl_percent in FOCUSED_CANDIDATES:
            if STOP_REQUESTED:
                raise CommissionAbort("operator_stop")
            log.say(f"\nThreshold candidate {label}: gains={gains.label()}, CL={cl_percent}%")
            c: dict[str, Any] = {"label": label, "gains": asdict(gains), "cl_percent": int(cl_percent)}
            try:
                settle.apply_gains_while_on(vix, ZERO_GAINS, args.kick_cl_percent, args)
                time.sleep(args.candidate_settle_before_zero_s)
                c["pre_candidate_vix_zero"] = settle.vix_post_kick_zero(vix, log)
                c["reference_before_gains"] = settle.snapshot(vix, pico)

                # Apply the actual holding gains and deliberately wait for the
                # one-time pull-in to finish before scoring hold noise.  v4.70
                # scored immediately after applying gains, which made B look
                # like 22 counts even though v4.69 had shown it can be much
                # quieter after settling.
                settle.apply_gains_while_on(vix, gains, int(cl_percent), args)
                time.sleep(args.candidate_settle_after_gain_s)
                c["post_gain_vix_zero"] = settle.vix_post_kick_zero(vix, log)
                candidate_ref = settle.snapshot(vix, pico)
                c["reference_after_gain_settle"] = candidate_ref

                c["quiet_hold"] = settle.sample_window(
                    vix=vix,
                    pico=pico,
                    log=log,
                    run_dir=run_dir,
                    name=f"threshold_hold_{label}",
                    duration_s=args.hold_window_s,
                    interval_s=args.sample_interval_s,
                    reference=candidate_ref,
                    min_samples=args.min_samples,
                    abort_from_reference_counts=None,
                    abort_within_window_counts=args.hold_abort_span_counts,
                )
                # v4.72: score the quiet tail, not the whole window.  The full-window
                # span is still recorded; a hard stop or insufficient sampling still fails.
                c["whole_hold_gate"] = settle.candidate_ok(c["quiet_hold"], args)
                c["quiet_hold_tail_gate"] = tail_gate_from_sample_csv(
                    c["quiet_hold"],
                    run_dir,
                    tail_s=float(args.hold_tail_s),
                    span_counts=int(args.hold_tail_span_counts),
                    drift_counts=int(args.hold_tail_drift_counts),
                )
                c["passes_hold_gate"] = bool(c["quiet_hold_tail_gate"].get("passes"))
                log.say(
                    f"Candidate {label} hold whole_span={c['quiet_hold'].get('pico_delta_from_reference', {}).get('span')} "
                    f"tail_span={c['quiet_hold_tail_gate'].get('tail_span_counts')} "
                    f"tail_drift={c['quiet_hold_tail_gate'].get('tail_drift_counts')} "
                    f"tail_pass={c['passes_hold_gate']}"
                )
                if not c["passes_hold_gate"]:
                    log.say(f"Candidate {label} failed quiet tail hold gate; skipping commanded motion for this candidate.")
                    candidate_reports.append(c)
                    continue

                c["post_candidate_vix_zero"] = settle.vix_post_kick_zero(vix, log)
                c["reference_before_motion"] = settle.snapshot(vix, pico)
                c["sham"] = run_sham_window(
                    pico=pico,
                    run_dir=run_dir,
                    name=f"threshold_sham_{label}",
                    duration_s=args.sham_window_s,
                    invalid_baseline=invalid_baseline,
                )
                sham_span = c["sham"].get("delta_from_first", {}).get("span")
                c["passes_sham_gate"] = isinstance(sham_span, (int, float)) and float(sham_span) <= args.quiet_span_counts
                if not c["passes_sham_gate"]:
                    log.say(f"Candidate {label} failed sham/no-step gate; skipping commanded motion.")
                    candidate_reports.append(c)
                    continue

                amp_summaries: dict[str, Any] = {}
                for amplitude, blocks in amplitude_iter_from_args(args):
                    move_id_seed, summary = run_abba_relative(
                        pico=pico,
                        log=log,
                        run_dir=run_dir,
                        candidate_label=label,
                        amplitude=amplitude,
                        blocks=int(blocks),
                        rate=args.rate_counts_per_s,
                        accel=args.accel_counts_per_s2,
                        invalid_baseline=invalid_baseline,
                        move_id_seed=move_id_seed,
                    )
                    amp_summaries[str(amplitude)] = summary
                    if not bool(summary.get("passes_practical_gate")):
                        log.say(f"Candidate {label} amplitude {amplitude} did not pass practical gate; continuing ladder if safe.")
                c["amplitude_summaries"] = amp_summaries
                c["passes_threshold_motion_proof"] = bool(
                    any(s.get("usable_threshold_gate") or s.get("strong_threshold_gate") for s in amp_summaries.values())
                )
            except Exception as exc:
                c["error"] = str(exc)
                c["passes_threshold_motion_proof"] = False
                log.say(f"Candidate {label} stopped safely: {exc}")
                # Keep testing the second candidate only for bounded practical failures.
                text = str(exc)
                if any(token in text for token in ("Pico latch", "fault line", "Encoder-invalid", "Movement exceeded", "operator_stop")):
                    candidate_reports.append(c)
                    break
            candidate_reports.append(c)
            (run_dir / "THRESHOLD_CHARACTERIZATION_INTERMEDIATE.json").write_text(json.dumps(candidate_reports, indent=2) + "\n", encoding="utf-8")

        report["candidates"] = candidate_reports
        report["verdict"] = classify(report, args)
        best = report["verdict"].get("best_usable_record")
        partial = report["verdict"].get("best_partial_record")
        lines = [
            "THRESHOLD CHARACTERIZATION VERDICT",
            f"status: {report['verdict'].get('likely_blocker_or_status')}",
            f"best_usable_record: {best if best else 'none'}",
            f"best_partial_record: {partial if partial else 'none'}",
            "",
            "Findings:",
            *[f"- {x}" for x in report["verdict"].get("findings", [])],
            "",
            "Next steps:",
            *[f"- {x}" for x in report["verdict"].get("next_steps", [])],
            "",
        ]
        (run_dir / "THRESHOLD_CHARACTERIZATION_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (run_dir / "THRESHOLD_CHARACTERIZATION_VERDICT.txt").write_text("\n".join(lines), encoding="utf-8")
        log.say("\n" + "\n".join(lines))
        code = 0
    except Exception as exc:
        report["abort"] = str(exc)
        if "verdict" not in report:
            report["verdict"] = {
                "likely_blocker_or_status": "aborted_before_verdict",
                "passed_candidates": [],
                "findings": ["Threshold characterization stopped safely before final verdict; do not treat as a pass."],
                "next_steps": ["Inspect THRESHOLD_CHARACTERIZATION_SUMMARY.json and per-window CSVs, then fix the abort reason before final validation."],
            }
        with contextlib.suppress(Exception):
            (run_dir / "THRESHOLD_CHARACTERIZATION_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        log.say(f"\nABORT: Threshold characterization stopped safely: {exc}")
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
        try:
            bundle_path = bundle_run_dir(run_dir)
            report["evidence_bundle"] = str(bundle_path)
            with contextlib.suppress(Exception):
                (run_dir / "THRESHOLD_CHARACTERIZATION_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            log.say(f"Evidence bundle: {bundle_path}")
        except Exception as exc:
            log.say(f"Evidence bundle creation failed: {exc}")
        log.close()
        with contextlib.suppress(Exception):
            bundle_run_dir(run_dir)
    return code


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V4.77 threshold-characterization motion sweep: dense 100/75/50/40/30/25/20/15/10 count ladder")
    p.add_argument("--vix-port", default="/dev/ttyUSB0")
    p.add_argument("--pico-port", default="/dev/ttyACM0")
    p.add_argument("--vix-baud", type=int, default=9600)
    p.add_argument("--pico-baud", type=int, default=115200)
    p.add_argument("--bench-no-estop", action="store_true")
    p.add_argument("--output-root", type=Path, default=Path.home() / "vix100nm_runs")
    p.add_argument("--watchdog-ms", type=int, default=5000)
    p.add_argument("--iw-counts", type=int, default=1000)
    p.add_argument("--kick-cl-percent", type=int, default=1)
    p.add_argument("--tl-counts", type=int, default=13000)
    p.add_argument("--ferrmax-counts", type=int, default=13000)
    p.add_argument("--max-allow-kick-counts", type=int, default=10000)
    p.add_argument("--pre-off-abort-span-counts", type=int, default=500)
    p.add_argument("--hold-abort-span-counts", type=int, default=1000)
    p.add_argument("--quiet-span-counts", type=int, default=25)
    p.add_argument("--off-baseline-s", type=float, default=3.0)
    p.add_argument("--kick-window-s", type=float, default=2.5)
    p.add_argument("--hold-window-s", type=float, default=6.0)
    p.add_argument("--sham-window-s", type=float, default=1.5)
    p.add_argument("--candidate-settle-before-zero-s", type=float, default=0.5)
    p.add_argument("--candidate-settle-after-gain-s", type=float, default=5.0)
    p.add_argument("--sample-interval-s", type=float, default=0.05)
    p.add_argument("--hold-tail-s", type=float, default=1.5)
    p.add_argument("--hold-tail-span-counts", type=int, default=25)
    p.add_argument("--hold-tail-drift-counts", type=int, default=15)
    p.add_argument("--min-samples", type=int, default=20)
    p.add_argument("--local-zero-settle-counts", type=int, default=20)
    p.add_argument("--local-zero-window-s", type=float, default=0.25)
    p.add_argument("--local-zero-max-wait-s", type=float, default=20.0)
    p.add_argument("--amplitudes", default="100,75,50,40,30,25,20,15,10", help="Comma-separated positive count amplitudes to test; default maps 1000 to 100 nm.")
    p.add_argument("--blocks-10", type=int, default=3)
    p.add_argument("--blocks-20", type=int, default=2)
    p.add_argument("--blocks-50", type=int, default=1)
    p.add_argument("--blocks-100", type=int, default=1)
    p.add_argument("--rate-counts-per-s", type=int, default=100)
    p.add_argument("--accel-counts-per-s2", type=int, default=5000)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(run_probe(parse_args()))
