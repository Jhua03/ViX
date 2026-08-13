#!/usr/bin/env python3
"""Zero-move ViX enable/commutation kick probe for MX80L/Pico2 commissioning.

V4.63 is intentionally NOT a 100 nm validation script. It commands no moves.
It measures what happens around the X4-enable and ViX ON transition while the
position-loop gains are zero.  If the carriage moves with GF=GI=GP=GV=FT=0,
then the problem is below the normal servo tuning layer: motor-enable EMI,
commutation/phase setup, drive/motor interaction, brake/drag release, or a
power-stage torque-vector issue.

Evidence written:
  ENABLE_KICK_PROBE_SUMMARY.json
  ENABLE_KICK_VERDICT.txt
  per-repeat CSV files for OFF baseline, X4-enable-only, and ViX-ON zero-gain.
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
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from vix100nm_commission import (  # type: ignore
    CommissionAbort,
    Gains,
    RunLog,
    Pico,
    Vix,
    configure_pico_policy,
    deenergize_drive,
    energize_drive,
    preflight_with_serial_retry,
    prepare_pico_for_enable_with_stale_vix_reset,
    safe_pico_zero,
    temporary_vix_setup,
)

STOP_REQUESTED = False
COUNTS_PER_MM = 100_000
NM_PER_COUNT = 10
UM_PER_COUNT = 0.01
VIX500_CR_COUNTS_PER_A_RMS = 62136.0
ZERO_GAINS = Gains(0, 0, 0, 0, 0)
DIRINV = False
ENCSIGN = -1


def signal_handler(signum: int, frame: object) -> None:  # pragma: no cover - field path
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def make_run_dir(root: Path) -> Path:
    path = root / f"{now_stamp()}_enable_kick_probe"
    path.mkdir(parents=True, exist_ok=False)
    return path


def pct(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, max(0, int(math.ceil(q * len(sorted_values)) - 1)))
    return sorted_values[idx]


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "first": None,
            "last": None,
            "min": None,
            "max": None,
            "span": None,
            "drift": None,
            "median": None,
            "p95_abs_from_first": None,
            "max_abs_from_first": None,
        }
    ordered = sorted(values)
    n = len(values)
    median = ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2])
    first = values[0]
    abs_first = sorted(abs(v - first) for v in values)
    return {
        "n": n,
        "first": first,
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "span": max(values) - min(values),
        "drift": values[-1] - first,
        "median": median,
        "p95_abs_from_first": pct(abs_first, 0.95),
        "max_abs_from_first": max(abs_first),
    }


def read_vix_safe(vix: Vix, name: str) -> int | None:
    try:
        return vix.read_int(name)
    except Exception:
        return None


def read_vix_text_safe(vix: Vix, body: str) -> str | None:
    try:
        return vix.report(body)
    except Exception:
        return None


def snapshot(vix: Vix, pico: Pico) -> dict[str, Any]:
    ps = pico.status()
    faults = None
    with contextlib.suppress(Exception):
        faults = vix.faults()
    return {
        "t_monotonic": time.monotonic(),
        "pico_encoder_raw": int(ps.get("encoder_raw", 0)),
        "pico_encoder_position": int(ps.get("encoder_position", 0)),
        "pico_command_position": int(ps.get("command_position", 0)),
        "pico_following_error": int(ps.get("following_error", 0)),
        "pico_motion": str(ps.get("motion")),
        "pico_armed": bool(ps.get("armed")),
        "pico_enabled": bool(ps.get("enabled")),
        "pico_latched": bool(ps.get("latched")),
        "pico_latch": str(ps.get("latch")),
        "pico_encoder_invalid": int(ps.get("encoder_invalid", 0)),
        "pico_fault_active": bool(ps.get("fault_active")),
        "pico_raw_fault": int(ps.get("raw_fault", -1)),
        "pico_estop_safe": bool(ps.get("estop_safe")),
        "vix_pa": read_vix_safe(vix, "PA"),
        "vix_pe": read_vix_safe(vix, "PE"),
        "vix_pt": read_vix_safe(vix, "PT"),
        "vix_pf": read_vix_safe(vix, "PF"),
        "vix_cr": read_vix_safe(vix, "CR"),
        "vix_st2": read_vix_text_safe(vix, "R(ST2)"),
        "vix_faults": faults,
    }


def sample_window(
    *,
    vix: Vix,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    name: str,
    duration_s: float,
    interval_s: float,
    reference: dict[str, Any] | None,
    abort_span_counts: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    start = time.monotonic()
    ref_pico = int(reference.get("pico_encoder_position", 0)) if reference else None
    ref_raw = int(reference.get("pico_encoder_raw", 0)) if reference else None
    ref_vix = reference.get("vix_pa") if reference else None
    ref_invalid = int(reference.get("pico_encoder_invalid", 0)) if reference else None
    first_pico: int | None = None
    hard_stop: str | None = None

    while True:
        if STOP_REQUESTED:
            hard_stop = "operator_stop"
            break
        elapsed = time.monotonic() - start
        if elapsed >= duration_s:
            break
        try:
            row = snapshot(vix, pico)
        except Exception as exc:
            hard_stop = f"snapshot_failed:{exc}"
            break
        row["elapsed_s"] = elapsed
        if first_pico is None:
            first_pico = int(row["pico_encoder_position"])
        if ref_pico is not None:
            row["pico_delta_from_reference"] = int(row["pico_encoder_position"]) - ref_pico
        else:
            row["pico_delta_from_reference"] = None
        if ref_raw is not None:
            row["pico_raw_delta_from_reference"] = int(row["pico_encoder_raw"]) - ref_raw
        else:
            row["pico_raw_delta_from_reference"] = None
        if ref_vix is not None and row.get("vix_pa") is not None:
            row["vix_delta_from_reference"] = int(row["vix_pa"]) - int(ref_vix)
        else:
            row["vix_delta_from_reference"] = None
        if ref_invalid is not None:
            row["encoder_invalid_delta_from_reference"] = int(row["pico_encoder_invalid"]) - ref_invalid
        else:
            row["encoder_invalid_delta_from_reference"] = None
        rows.append(row)

        if bool(row.get("pico_latched")):
            hard_stop = f"pico_latch:{row.get('pico_latch')}"
            break
        if bool(row.get("pico_fault_active")):
            hard_stop = "pico_reports_vix_fault_active"
            break
        if ref_pico is not None and abs(int(row["pico_encoder_position"]) - ref_pico) > abort_span_counts:
            hard_stop = f"movement_exceeded_{abort_span_counts}_counts_from_reference"
            break
        if first_pico is not None and abs(int(row["pico_encoder_position"]) - first_pico) > abort_span_counts:
            hard_stop = f"movement_exceeded_{abort_span_counts}_counts_within_window"
            break
        time.sleep(interval_s)

    csv_path = run_dir / f"{name}.csv"
    if rows:
        # Flatten faults into JSON strings for CSV robustness.
        flat_rows: list[dict[str, Any]] = []
        for r in rows:
            rr = dict(r)
            if isinstance(rr.get("vix_faults"), dict):
                rr["vix_faults"] = json.dumps(rr["vix_faults"], sort_keys=True)
            flat_rows.append(rr)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()))
            writer.writeheader()
            writer.writerows(flat_rows)

    pico_vals = [float(r["pico_encoder_position"]) for r in rows]
    pico_delta_vals = [float(r["pico_delta_from_reference"]) for r in rows if r.get("pico_delta_from_reference") is not None]
    raw_delta_vals = [float(r["pico_raw_delta_from_reference"]) for r in rows if r.get("pico_raw_delta_from_reference") is not None]
    vix_delta_vals = [float(r["vix_delta_from_reference"]) for r in rows if r.get("vix_delta_from_reference") is not None]
    fe_vals = [float(r["pico_following_error"]) for r in rows]
    pe_vals = [float(r["vix_pe"]) for r in rows if r.get("vix_pe") is not None]
    cr_vals = [float(r["vix_cr"]) for r in rows if r.get("vix_cr") is not None]
    invalid_delta = None
    if rows and ref_invalid is not None:
        invalid_delta = int(rows[-1]["pico_encoder_invalid"]) - ref_invalid

    summary = {
        "name": name,
        "duration_requested_s": duration_s,
        "duration_observed_s": rows[-1]["elapsed_s"] if rows else 0,
        "samples": len(rows),
        "hard_stop": hard_stop,
        "pico_position": stats(pico_vals),
        "pico_delta_from_reference": stats(pico_delta_vals),
        "pico_raw_delta_from_reference": stats(raw_delta_vals),
        "vix_delta_from_reference": stats(vix_delta_vals),
        "following_error": stats(fe_vals),
        "vix_pe": stats(pe_vals),
        "vix_cr": stats(cr_vals),
        "vix_cr_amps_rms": {k: (v / VIX500_CR_COUNTS_PER_A_RMS if isinstance(v, (int, float)) else v) for k, v in stats(cr_vals).items()},
        "encoder_invalid_delta_from_reference": invalid_delta,
        "first_row": rows[0] if rows else None,
        "final_row": rows[-1] if rows else None,
        "csv": csv_path.name if rows else None,
    }
    (run_dir / f"{name}_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    d = summary["pico_delta_from_reference"]
    log.say(
        f"{name}: samples={len(rows)}, ref_delta_span={d.get('span')} counts, "
        f"ref_delta_final={d.get('last')} counts, invalid_delta={invalid_delta}, hard_stop={hard_stop}"
    )
    return summary


def safe_local_prepare(
    *,
    vix: Vix,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    args: argparse.Namespace,
    phase_result: dict[str, Any],
) -> None:
    temporary_vix_setup(
        vix,
        ZERO_GAINS,
        cl_percent=args.cl_percent,
        tl_counts=args.abort_span_counts,
        iw_counts=args.iw_counts,
    )
    configure_pico_policy(
        pico,
        args.bench_no_estop,
        dirinv=DIRINV,
        encsign=ENCSIGN,
        watchdog_ms=args.watchdog_ms,
    )
    zero_report = prepare_pico_for_enable_with_stale_vix_reset(
        vix,
        pico,
        log,
        phase_result,
        gains=ZERO_GAINS,
        cl_percent=args.cl_percent,
        tl_counts=args.abort_span_counts,
        ferrmax=args.abort_span_counts,
        bench_no_estop=args.bench_no_estop,
        dirinv=DIRINV,
        encsign=ENCSIGN,
        watchdog_ms=args.watchdog_ms,
    )
    phase_result["zero_report"] = zero_report


def run_one_repeat(
    *,
    repeat_index: int,
    vix: Vix,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    prefix = f"repeat_{repeat_index:02d}"
    result: dict[str, Any] = {
        "repeat": repeat_index,
        "zero_gains": asdict(ZERO_GAINS),
        "cl_percent": args.cl_percent,
        "iw_counts": args.iw_counts,
        "abort_span_counts": args.abort_span_counts,
    }

    # Always start de-energised and cleared.
    with contextlib.suppress(Exception):
        pico.stop_heartbeat()
    with contextlib.suppress(Exception):
        deenergize_drive(vix, pico, verify=False)
    with contextlib.suppress(Exception):
        pico.command("ABORT")
        pico.command("ENABLE 0")
        pico.command("DISARM")
        pico.command("CLEAR")
        pico.command("DIAG CLEAR")
    with contextlib.suppress(Exception):
        vix.reset_restore()

    # Local zero with zero gains but do not enable yet.
    safe_local_prepare(vix=vix, pico=pico, log=log, run_dir=run_dir, args=args, phase_result=result)
    ref = snapshot(vix, pico)
    result["reference_after_zero"] = ref

    result["pre_enable_off"] = sample_window(
        vix=vix, pico=pico, log=log, run_dir=run_dir,
        name=f"{prefix}_pre_enable_off",
        duration_s=args.pre_window_s,
        interval_s=args.sample_interval_s,
        reference=ref,
        abort_span_counts=args.abort_span_counts,
    )

    # Isolate X4 enable line from the ViX ON/power-stage command.
    log.say(f"{prefix}: X4 enable-only test; ViX remains OFF, no motion command.")
    pico.start_heartbeat()
    try:
        pico.command("ENABLE 1")
        result["x4_enable_only"] = sample_window(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            name=f"{prefix}_x4_enable_only_vix_off",
            duration_s=args.x4_enable_window_s,
            interval_s=args.sample_interval_s,
            reference=ref,
            abort_span_counts=args.abort_span_counts,
        )
    finally:
        with contextlib.suppress(Exception):
            pico.command("ENABLE 0")
        with contextlib.suppress(Exception):
            pico.stop_heartbeat()

    # Re-zero before the actual ViX ON zero-gain test so X4-only evidence cannot
    # contaminate the power-stage test.
    with contextlib.suppress(Exception):
        pico.command("ABORT")
        pico.command("ENABLE 0")
        pico.command("DISARM")
        pico.command("CLEAR")
    safe_local_prepare(vix=vix, pico=pico, log=log, run_dir=run_dir, args=args, phase_result=result)
    ref2 = snapshot(vix, pico)
    result["reference_before_vix_on"] = ref2

    log.say(f"{prefix}: ViX ON zero-gain test; GF/GI/GP/GV/FT all zero, no motion command.")
    pico.start_heartbeat()
    on_error: str | None = None
    try:
        before_on = snapshot(vix, pico)
        t_before_on = time.monotonic()
        energize_drive(vix, pico)
        t_after_on = time.monotonic()
        after_on = snapshot(vix, pico)
        result["vix_on_handshake"] = {
            "before_on": before_on,
            "after_on": after_on,
            "handshake_s": t_after_on - t_before_on,
            "after_on_pico_delta_counts": int(after_on["pico_encoder_position"]) - int(ref2["pico_encoder_position"]),
            "after_on_vix_delta_counts": (int(after_on["vix_pa"]) - int(ref2["vix_pa"])) if after_on.get("vix_pa") is not None and ref2.get("vix_pa") is not None else None,
        }
        result["vix_on_zero_gains"] = sample_window(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            name=f"{prefix}_vix_on_zero_gains",
            duration_s=args.on_window_s,
            interval_s=args.sample_interval_s,
            reference=ref2,
            abort_span_counts=args.abort_span_counts,
        )
    except Exception as exc:
        on_error = str(exc)
        result["vix_on_error"] = on_error
        log.say(f"{prefix}: ViX ON zero-gain test stopped safely: {on_error}")
    finally:
        with contextlib.suppress(Exception):
            deenergize_drive(vix, pico, verify=False)
        with contextlib.suppress(Exception):
            pico.stop_heartbeat()
        with contextlib.suppress(Exception):
            pico.command("ABORT")
            pico.command("ENABLE 0")
            pico.command("DISARM")

    result["post_off"] = sample_window(
        vix=vix, pico=pico, log=log, run_dir=run_dir,
        name=f"{prefix}_post_off",
        duration_s=args.post_window_s,
        interval_s=args.sample_interval_s,
        reference=ref2,
        abort_span_counts=args.abort_span_counts,
    )
    (run_dir / f"{prefix}_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else None


def max_abs_delta(section: dict[str, Any] | None) -> float | None:
    if not section:
        return None
    st = section.get("pico_delta_from_reference", {})
    vals = [num(st.get("min")), num(st.get("max")), num(st.get("last")), num(st.get("max_abs_from_first"))]
    vals2 = [abs(v) for v in vals if v is not None]
    return max(vals2) if vals2 else None


def classify(repeats: list[dict[str, Any]]) -> dict[str, Any]:
    x4_deltas: list[float] = []
    on_deltas: list[float] = []
    on_final_deltas: list[float] = []
    on_vix_deltas: list[float] = []
    invalid_total = 0
    hard_stops: list[str] = []
    directions: list[int] = []
    cr_peaks: list[float] = []

    for r in repeats:
        x4 = max_abs_delta(r.get("x4_enable_only"))
        if x4 is not None:
            x4_deltas.append(x4)
        on = r.get("vix_on_zero_gains")
        od = max_abs_delta(on)
        if od is not None:
            on_deltas.append(od)
        if on:
            st = on.get("pico_delta_from_reference", {})
            lf = num(st.get("last"))
            if lf is not None:
                on_final_deltas.append(lf)
                if abs(lf) > 20:
                    directions.append(1 if lf > 0 else -1)
            vix_st = on.get("vix_delta_from_reference", {})
            vf = num(vix_st.get("last"))
            if vf is not None:
                on_vix_deltas.append(vf)
            inv = on.get("encoder_invalid_delta_from_reference")
            if isinstance(inv, int):
                invalid_total += inv
            if on.get("hard_stop"):
                hard_stops.append(f"repeat {r.get('repeat')} ON: {on.get('hard_stop')}")
            cr = on.get("vix_cr_amps_rms", {}).get("max_abs_from_first")
            if isinstance(cr, (int, float)):
                cr_peaks.append(abs(float(cr)))
        if r.get("vix_on_error"):
            hard_stops.append(f"repeat {r.get('repeat')} ON error: {r.get('vix_on_error')}")

    x4_max = max(x4_deltas or [0.0])
    on_max = max(on_deltas or [0.0])
    on_median = sorted(on_deltas)[len(on_deltas)//2] if on_deltas else None
    final_abs = [abs(v) for v in on_final_deltas]
    consistent_direction = None
    if directions:
        consistent_direction = abs(sum(directions)) == len(directions)

    findings: list[str] = []
    next_steps: list[str] = []

    if x4_max <= 20:
        findings.append("X4 enable-only was quiet: the enable logic line alone is not the disturbance source.")
    elif x4_max > 50:
        findings.append("X4 enable-only caused measurable motion/noise before ViX ON: inspect enable wiring/reference/EMI path.")

    if on_max > 500:
        findings.append("ViX ON with zero gains caused >500 counts of motion: this is a power-stage/commutation/drive-enable kick, not normal PIVF gain tuning.")
    elif on_max > 50:
        findings.append("ViX ON with zero gains caused >50 counts of motion: ON transition is not quiet enough for 100 nm validation.")
    elif on_deltas:
        findings.append("ViX ON with zero gains stayed below 50 counts in this run; commutation kick is not reproduced strongly.")

    if invalid_total > 0:
        findings.append("Encoder-invalid incremented during enable-kick testing: motor-enable EMI or receiver margin remains plausible.")

    if consistent_direction is True:
        findings.append("The zero-gain ON kick direction was consistent across repeats: phase order/commutation/torsion preload is more likely than random encoder noise.")
    elif consistent_direction is False:
        findings.append("The zero-gain ON kick direction varied: random disturbance, mechanical relaxation, or intermittent EMI is more likely.")

    if hard_stops:
        findings.append("At least one repeat hit a hard stop/latch or local-zero failure; do not run Stage 6 until resolved.")

    if x4_max <= 20 and on_max > 500 and invalid_total == 0:
        likely = "vix_on_zero_gain_commutation_or_power_stage_kick"
        next_steps.extend([
            "Verify motor phase order U/V/W and commutation feedback A0/A1/A2 for the MX80L/Vix setup.",
            "Run the same probe after a clean power cycle; if the zero-gain ON kick repeats, treat it as commutation/drive setup before more servo tuning.",
            "Check for mechanical preload/brake/cable force released exactly when the drive energizes.",
        ])
    elif x4_max > 50:
        likely = "x4_enable_or_reference_noise_path"
        next_steps.extend([
            "Inspect X4 enable wiring, signal ground reference, and physical routing near encoder/Pico wiring.",
            "Keep ViX X4/control wiring away from U/V/W and HV wiring; check shield/0V bonding.",
        ])
    elif invalid_total > 0:
        likely = "motor_enable_emi_into_encoder_receiver"
        next_steps.extend([
            "Fix encoder receiver termination/decoupling/routing before more 100 nm validation.",
            "Scope A+/A- and B+/B- at the AM26LV32 during ViX ON if available.",
        ])
    elif on_max > 50:
        likely = "small_zero_gain_on_kick_or_mechanical_preload"
        next_steps.extend([
            "Repeat after power cycle and with cables mechanically supported; compare kick size/direction.",
            "If repeatable, inspect commutation/phase setup; if not, inspect mechanical/cable preload.",
        ])
    else:
        likely = "zero_gain_enable_kick_not_reproduced"
        next_steps.append("If zero-gain ON is quiet now, return to a softer hold-loop probe before any Stage 6 validation.")

    return {
        "likely_blocker": likely,
        "x4_enable_only_max_abs_delta_counts": x4_max,
        "vix_on_zero_gains_max_abs_delta_counts": on_max,
        "vix_on_zero_gains_median_abs_delta_counts": on_median,
        "vix_on_final_delta_counts": on_final_deltas,
        "vix_on_vix_pa_final_delta_counts": on_vix_deltas,
        "vix_on_final_delta_abs_counts": final_abs,
        "encoder_invalid_total": invalid_total,
        "consistent_kick_direction": consistent_direction,
        "hard_stops": hard_stops,
        "vix_cr_peak_delta_amps_rms_observed": max(cr_peaks or [0.0]),
        "findings": findings,
        "next_steps": next_steps,
    }


def run_probe(args: argparse.Namespace) -> int:
    run_dir = make_run_dir(args.output_root)
    log = RunLog(run_dir)
    vix: Vix | None = None
    pico: Pico | None = None
    repeats: list[dict[str, Any]] = []
    code = 1
    try:
        log.say("ENABLE/KICK PROBE v4.63: zero commanded moves; zero-gain enable/commutation discriminator.")
        log.say(f"Evidence directory: {run_dir}")
        vix = Vix(args.vix_port, args.vix_baud, log)
        pico = Pico(args.pico_port, args.pico_baud, log)
        preflight_with_serial_retry(
            vix, pico, log, run_dir,
            bench_no_estop=args.bench_no_estop,
            dirinv=DIRINV,
            encsign=ENCSIGN,
        )
        configure_pico_policy(
            pico,
            args.bench_no_estop,
            dirinv=DIRINV,
            encsign=ENCSIGN,
            watchdog_ms=args.watchdog_ms,
        )

        vix.off()
        pico.force_safe()
        with contextlib.suppress(Exception):
            pico.command("CLEAR")
            pico.command("DIAG CLEAR")
        safe_pico_zero(pico, reason="enable_kick_off_baseline")
        off_ref = snapshot(vix, pico)
        off_baseline = sample_window(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            name="off_disabled_baseline",
            duration_s=args.off_baseline_s,
            interval_s=args.sample_interval_s,
            reference=off_ref,
            abort_span_counts=args.abort_span_counts,
        )

        for repeat in range(1, args.repeats + 1):
            if STOP_REQUESTED:
                break
            log.say(f"\n--- Enable-kick repeat {repeat}/{args.repeats} ---")
            try:
                repeats.append(run_one_repeat(
                    repeat_index=repeat,
                    vix=vix,
                    pico=pico,
                    log=log,
                    run_dir=run_dir,
                    args=args,
                ))
            except Exception as exc:
                row = {"repeat": repeat, "error": str(exc)}
                repeats.append(row)
                log.say(f"repeat {repeat}: stopped safely: {exc}")
                # A true latch or large movement is diagnostic enough; do not keep cycling ON.
                text = str(exc)
                if any(token in text for token in ("VIX_FAULT", "ENCODER_INVALID", "movement_exceeded", "Local zero transaction failed")):
                    break
            finally:
                with contextlib.suppress(Exception):
                    pico.stop_heartbeat()
                with contextlib.suppress(Exception):
                    deenergize_drive(vix, pico, verify=False)
                with contextlib.suppress(Exception):
                    pico.command("ABORT")
                    pico.command("ENABLE 0")
                    pico.command("DISARM")
                time.sleep(args.between_repeats_s)

        verdict = classify(repeats)
        report = {
            "version": "v4.63",
            "created": datetime.now().isoformat(timespec="seconds"),
            "counts_per_mm": COUNTS_PER_MM,
            "nm_per_count": NM_PER_COUNT,
            "test_intent": "Separate X4-enable-only disturbance from ViX ON zero-gain power-stage/commutation kick. No commanded moves are issued.",
            "settings": {
                "zero_gains": asdict(ZERO_GAINS),
                "cl_percent": args.cl_percent,
                "iw_counts": args.iw_counts,
                "abort_span_counts": args.abort_span_counts,
                "repeats_requested": args.repeats,
                "pre_window_s": args.pre_window_s,
                "x4_enable_window_s": args.x4_enable_window_s,
                "on_window_s": args.on_window_s,
                "post_window_s": args.post_window_s,
                "sample_interval_s": args.sample_interval_s,
            },
            "off_disabled_baseline": off_baseline,
            "repeats": repeats,
            "verdict": verdict,
        }
        (run_dir / "ENABLE_KICK_PROBE_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        verdict_lines = [
            "ENABLE/KICK PROBE VERDICT",
            f"likely_blocker: {verdict['likely_blocker']}",
            f"x4_enable_only_max_abs_delta_counts: {verdict.get('x4_enable_only_max_abs_delta_counts')}",
            f"vix_on_zero_gains_max_abs_delta_counts: {verdict.get('vix_on_zero_gains_max_abs_delta_counts')}",
            f"encoder_invalid_total: {verdict.get('encoder_invalid_total')}",
            f"consistent_kick_direction: {verdict.get('consistent_kick_direction')}",
            "",
            "Findings:",
            *[f"- {x}" for x in verdict.get("findings", [])],
            "",
            "Next steps:",
            *[f"- {x}" for x in verdict.get("next_steps", [])],
            "",
        ]
        (run_dir / "ENABLE_KICK_VERDICT.txt").write_text("\n".join(verdict_lines), encoding="utf-8")
        log.say("\n" + "\n".join(verdict_lines))
        code = 0
    except Exception as exc:
        log.say(f"\nABORT: Enable/kick probe stopped safely: {exc}")
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
    p = argparse.ArgumentParser(description="V4.63 zero-move ViX ON/commutation kick probe")
    p.add_argument("--vix-port", default="/dev/ttyUSB0")
    p.add_argument("--pico-port", default="/dev/ttyACM0")
    p.add_argument("--vix-baud", type=int, default=9600)
    p.add_argument("--pico-baud", type=int, default=115200)
    p.add_argument("--bench-no-estop", action="store_true")
    p.add_argument("--output-root", type=Path, default=Path.home() / "vix100nm_runs")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--off-baseline-s", type=float, default=10.0)
    p.add_argument("--pre-window-s", type=float, default=2.0)
    p.add_argument("--x4-enable-window-s", type=float, default=2.0)
    p.add_argument("--on-window-s", type=float, default=3.0)
    p.add_argument("--post-window-s", type=float, default=2.0)
    p.add_argument("--between-repeats-s", type=float, default=1.0)
    p.add_argument("--sample-interval-s", type=float, default=0.05)
    p.add_argument("--watchdog-ms", type=int, default=5000)
    p.add_argument("--iw-counts", type=int, default=1000)
    p.add_argument("--cl-percent", type=int, default=1)
    p.add_argument("--abort-span-counts", type=int, default=10000)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(run_probe(parse_args()))
