#!/usr/bin/env python3
"""No-motion hold/noise/stability discriminator for ViX500AE + Pico2.

V4.62 adds a power-stage/zero-GI/GI-threshold matrix so the field result can
separate motor-enable EMI from proportional/velocity-loop instability and
true integral hunting without any commanded moves.

This script intentionally performs NO commanded moves.  It is meant to run after
Stage 5 has shown that 100 nm moves are possible, but Stage 6 final validation is
failing from startup drift, late settle misses, or intermittent hunting.

It separates four likely cases:
  * OFF drift/noise: mechanical/cable/bench disturbance or encoder signal noise.
  * ON-only noise: servo hold-loop instability or motor-enable EMI.
  * GI-dependent hunting: integral gain too aggressive for final validation.
  * Pico/ViX relative disagreement: encoder-copy / receiver / reference issue.

It writes JSON/CSV evidence and a human-readable HOLD_NOISE_VERDICT.txt.
"""

from __future__ import annotations

import argparse
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

# Import the commissioned host utilities without duplicating serial/safety logic.
from vix100nm_commission import (  # type: ignore
    CommissionAbort,
    Gains,
    RunLog,
    Pico,
    Vix,
    PICO_FERR_SMOKE,
    configure_pico_policy,
    deenergize_drive,
    energize_drive,
    preflight_with_serial_retry,
    safe_pico_zero,
    temporary_vix_setup,
)

STOP_REQUESTED = False
COUNTS_PER_MM = 100_000
NM_PER_COUNT = 10
VIX500_CR_COUNTS_PER_A_RMS = 62136.0


def signal_handler(signum: int, frame: object) -> None:  # pragma: no cover - field path
    global STOP_REQUESTED
    STOP_REQUESTED = True


def now_stamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S_%f')


def make_run_dir(root: Path) -> Path:
    path = root / f"{now_stamp()}_hold_noise_probe"
    path.mkdir(parents=True, exist_ok=False)
    return path


def stats(values: list[float]) -> dict[str, float | int | None]:
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
            "p95_abs_from_median": None,
            "rms_from_first": None,
            "slope_counts_per_s": None,
        }
    ordered = sorted(values)
    n = len(values)

    def pct(sorted_values: list[float], q: float) -> float:
        idx = min(len(sorted_values) - 1, max(0, int(math.ceil(q * len(sorted_values)) - 1)))
        return sorted_values[idx]

    median = ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2])
    first = values[0]
    abs_first = sorted(abs(v - first) for v in values)
    abs_med = sorted(abs(v - median) for v in values)
    rms_first = math.sqrt(sum((v - first) ** 2 for v in values) / n)
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
        "p95_abs_from_median": pct(abs_med, 0.95),
        "rms_from_first": rms_first,
        "slope_counts_per_s": None,
    }


def slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    xm = sum(xs) / len(xs)
    ym = sum(ys) / len(ys)
    den = sum((x - xm) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den


def read_vix_safe(vix: Vix, name: str) -> int | None:
    try:
        return vix.read_int(name)
    except Exception:
        return None


def sample_phase(
    *,
    vix: Vix,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    phase_name: str,
    duration_s: float,
    interval_s: float,
    movement_abort_counts: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    start_t = time.monotonic()
    first_pico: int | None = None
    first_raw: int | None = None
    first_vix_pa: int | None = None
    first_invalid: int | None = None
    hard_stop: str | None = None

    while True:
        if STOP_REQUESTED:
            hard_stop = "operator_stop"
            break
        elapsed = time.monotonic() - start_t
        if elapsed >= duration_s:
            break
        try:
            ps = pico.status()
        except Exception as exc:
            hard_stop = f"pico_status_failed: {exc}"
            break
        vix_pa = read_vix_safe(vix, "PA")
        vix_pe = read_vix_safe(vix, "PE")
        vix_cr = read_vix_safe(vix, "CR")
        vix_st2 = None
        with contextlib_suppress():
            vix_st2 = vix.report("R(ST2)")
        faults = None
        with contextlib_suppress():
            faults = vix.faults()

        pico_pos = int(ps.get("encoder_position", 0))
        pico_raw = int(ps.get("encoder_raw", 0))
        invalid = int(ps.get("encoder_invalid", 0))
        if first_pico is None:
            first_pico = pico_pos
            first_raw = pico_raw
            first_vix_pa = vix_pa
            first_invalid = invalid
        row = {
            "elapsed_s": elapsed,
            "pico_encoder_position": pico_pos,
            "pico_encoder_raw": pico_raw,
            "pico_command_position": int(ps.get("command_position", 0)),
            "pico_following_error": int(ps.get("following_error", 0)),
            "pico_latched": bool(ps.get("latched")),
            "pico_latch": str(ps.get("latch")),
            "pico_enabled": bool(ps.get("enabled")),
            "pico_armed": bool(ps.get("armed")),
            "pico_fault_active": bool(ps.get("fault_active")),
            "pico_raw_fault": int(ps.get("raw_fault", -1)),
            "pico_encoder_invalid": invalid,
            "pico_invalid_delta": invalid - (first_invalid if first_invalid is not None else invalid),
            "vix_pa": vix_pa,
            "vix_pe": vix_pe,
            "vix_cr": vix_cr,
            "vix_st2": vix_st2,
            "vix_faults": faults,
        }
        if first_vix_pa is not None and vix_pa is not None and first_pico is not None:
            row["pico_vix_relative_delta"] = (pico_pos - first_pico) - (vix_pa - first_vix_pa)
        else:
            row["pico_vix_relative_delta"] = None
        rows.append(row)

        if bool(ps.get("latched")):
            hard_stop = f"pico_latch:{ps.get('latch')}"
            break
        if bool(ps.get("fault_active")):
            hard_stop = "pico_reports_vix_fault_active"
            break
        if first_pico is not None and abs(pico_pos - first_pico) > movement_abort_counts:
            hard_stop = f"movement_exceeded_{movement_abort_counts}_counts"
            break
        time.sleep(interval_s)

    csv_path = run_dir / f"{phase_name}.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    pico_vals = [float(r["pico_encoder_position"]) for r in rows]
    raw_vals = [float(r["pico_encoder_raw"]) for r in rows]
    fe_vals = [float(r["pico_following_error"]) for r in rows]
    vix_vals = [float(r["vix_pa"]) for r in rows if r.get("vix_pa") is not None]
    pe_vals = [float(r["vix_pe"]) for r in rows if r.get("vix_pe") is not None]
    cr_vals = [float(r["vix_cr"]) for r in rows if r.get("vix_cr") is not None]
    disagreement = [float(r["pico_vix_relative_delta"]) for r in rows if r.get("pico_vix_relative_delta") is not None]
    times = [float(r["elapsed_s"]) for r in rows]

    pico_stats = stats(pico_vals)
    pico_stats["slope_counts_per_s"] = slope(times, pico_vals)
    raw_stats = stats(raw_vals)
    raw_stats["slope_counts_per_s"] = slope(times, raw_vals)
    vix_stats = stats(vix_vals)
    vix_stats["slope_counts_per_s"] = slope(times[:len(vix_vals)], vix_vals) if vix_vals else None

    invalid_delta = None
    if rows:
        invalid_delta = int(rows[-1]["pico_encoder_invalid"]) - int(rows[0]["pico_encoder_invalid"])

    summary = {
        "phase": phase_name,
        "duration_requested_s": duration_s,
        "duration_observed_s": rows[-1]["elapsed_s"] if rows else 0,
        "sample_interval_s": interval_s,
        "samples": len(rows),
        "hard_stop": hard_stop,
        "pico_position": pico_stats,
        "pico_raw": raw_stats,
        "vix_pa": vix_stats,
        "following_error": stats(fe_vals),
        "vix_pe": stats(pe_vals),
        "vix_cr": stats(cr_vals),
        "vix_cr_amps_rms": {k: (v / VIX500_CR_COUNTS_PER_A_RMS if isinstance(v, (int, float)) else v) for k, v in stats(cr_vals).items()},
        "pico_vix_relative_delta": stats(disagreement),
        "encoder_invalid_delta": invalid_delta,
        "final_row": rows[-1] if rows else None,
        "csv": str(csv_path.name) if rows else None,
    }
    (run_dir / f"{phase_name}_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    span = summary["pico_position"]["span"]
    drift = summary["pico_position"]["drift"]
    log.say(
        f"{phase_name}: samples={len(rows)}, span={span} counts, drift={drift} counts, "
        f"invalid_delta={invalid_delta}, hard_stop={hard_stop}"
    )
    return summary


class contextlib_suppress:
    def __enter__(self):
        return None
    def __exit__(self, exc_type, exc, tb):
        return True


def classify(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {s["phase"]: s for s in summaries}

    def span(name: str) -> float:
        v = by_name.get(name, {}).get("pico_position", {}).get("span")
        return float(v) if v is not None else float("nan")

    def invalid(name: str) -> int:
        v = by_name.get(name, {}).get("encoder_invalid_delta")
        return int(v) if v is not None else 0

    def finite(v: float) -> bool:
        return math.isfinite(v)

    def quiet(v: float, limit: float = 20.0) -> bool:
        return finite(v) and v <= limit

    off_span = span("off_disabled")
    off_invalid = invalid("off_disabled")
    on_names = [k for k in by_name if k.startswith("on_")]
    on_spans = {k: span(k) for k in on_names}
    on_invalids = {k: invalid(k) for k in on_names}
    finite_on = [v for v in on_spans.values() if finite(v)]
    worst_on_span = max(finite_on or [float("nan")])
    best_on_span = min(finite_on or [float("nan")])
    hard_stops = {s["phase"]: s.get("hard_stop") for s in summaries if s.get("hard_stop")}

    zero_span = span("on_zero_gains_cl1")
    no_gi_spans = {k: v for k, v in on_spans.items() if "_gi0_" in k or k.startswith("on_gi0_")}
    gi_spans = {k: v for k, v in on_spans.items() if "gi0p" in k}

    findings: list[str] = []
    next_steps: list[str] = []

    if hard_stops:
        findings.append("At least one no-motion phase hit a hard stop/latch or preparation failure; inspect that phase before more 100 nm validation.")
    if off_invalid > 0:
        findings.append("Encoder-invalid increments occurred while OFF/disabled: encoder signal integrity is bad even before servo force is involved.")
    elif finite(off_span) and off_span <= 10:
        findings.append("OFF/disabled encoder floor is excellent: the stage/encoder was quiet with motor disabled.")
    elif finite(off_span) and off_span > 50:
        findings.append("OFF/disabled encoder span is large, so mechanical/environmental drift or encoder signal noise exists even with motor disabled.")

    if any(v > 0 for v in on_invalids.values()):
        findings.append("Encoder-invalid increments appear during ON hold: motor-enable EMI or receiver margin remains plausible.")

    if quiet(off_span) and quiet(zero_span):
        findings.append("Power stage ON with zero gains stayed quiet: plain motor-enable EMI is less likely than servo-loop hunting.")
    elif quiet(off_span) and finite(zero_span) and zero_span > 50:
        findings.append("Power stage ON with zero gains was noisy: motor-enable EMI, commutation noise, or drive/encoder interaction is likely.")

    quiet_no_gi = [(k, v) for k, v in no_gi_spans.items() if quiet(v)]
    noisy_no_gi = [(k, v) for k, v in no_gi_spans.items() if finite(v) and v > 50]
    quiet_gi = [(k, v) for k, v in gi_spans.items() if quiet(v)]
    noisy_gi = [(k, v) for k, v in gi_spans.items() if finite(v) and v > 50]

    if quiet_no_gi and noisy_gi:
        findings.append("No-GI hold can be quiet but GI-enabled hold is noisy: this points strongly to integral hunting/static-friction limit cycle.")
    elif noisy_no_gi:
        findings.append("Even no-GI proportional/velocity hold is noisy: this points to base P/V hold-loop instability, commutation interaction, or mechanical resonance.")
    elif quiet_no_gi:
        findings.append("At least one no-GI hold phase stayed quiet; use this as the safe baseline for the next tuning step.")

    for phase in sorted(on_spans):
        v = on_spans[phase]
        if finite(v):
            findings.append(f"{phase} span={v} counts ({v * NM_PER_COUNT:.0f} nm).")
        elif phase in by_name:
            findings.append(f"{phase} did not produce a valid span; hard_stop={by_name[phase].get('hard_stop')}")

    quiet_candidates = [
        (name, val) for name, val in on_spans.items()
        if quiet(val) and not by_name[name].get("hard_stop")
    ]
    quiet_candidates.sort(key=lambda x: x[1])
    if quiet_candidates:
        next_steps.append(
            f"Best quiet ON hold candidate: {quiet_candidates[0][0]} with span {quiet_candidates[0][1]} counts. Use this gain family for the next final-validation candidate, not the noisy GI setting."
        )
    elif finite(best_on_span):
        next_steps.append(
            f"No ON hold phase stayed under 20 counts; best observed ON span was {best_on_span} counts. Do not keep running Stage 6 until hold noise is reduced."
        )

    if quiet(off_span) and finite(zero_span) and zero_span > 50:
        likely = "motor_enable_emi_or_drive_encoder_interaction"
        next_steps.append("Check encoder receiver termination/decoupling/routing while the drive is ON, before changing servo gains.")
    elif quiet(off_span) and quiet(zero_span) and noisy_gi and quiet_no_gi:
        likely = "integral_gain_limit_cycle_or_static_friction_hunting"
        next_steps.append("Retune final validation from the quiet no-GI/low-GI baseline; avoid GI values that create large no-motion span.")
    elif quiet(off_span) and noisy_no_gi:
        likely = "base_servo_pv_hold_instability_or_commutation_interaction"
        next_steps.append("Try softer GP/GV or added FT damping before adding GI; inspect commutation/phase setup if all P/V holds hunt.")
    elif off_invalid > 0 or any(v > 0 for v in on_invalids.values()):
        likely = "encoder_signal_integrity_or_motor_enable_emi"
        next_steps.append("Fix encoder signal integrity before more 100 nm validation.")
    elif finite(off_span) and off_span > 50:
        likely = "mechanical_or_environmental_drift_floor"
        next_steps.append("Reduce bench/stage/cable mechanical disturbance before servo tuning.")
    else:
        likely = "servo_hold_loop_instability"

    return {
        "likely_blocker": likely,
        "off_span_counts": off_span,
        "off_span_nm": off_span * NM_PER_COUNT if finite(off_span) else None,
        "zero_gains_on_span_counts": zero_span if finite(zero_span) else None,
        "worst_on_span_counts": worst_on_span,
        "best_on_span_counts": best_on_span,
        "hard_stops": hard_stops,
        "findings": findings,
        "next_steps": next_steps,
    }


def run_probe(args: argparse.Namespace) -> int:
    run_dir = make_run_dir(args.output_root)
    log = RunLog(run_dir)
    vix: Vix | None = None
    pico: Pico | None = None
    summaries: list[dict[str, Any]] = []
    code = 1
    try:
        log.say("Stage 6 HOLD/NOISE PROBE: no commanded motion will be run.")
        log.say(f"Evidence directory: {run_dir}")
        vix = Vix(args.vix_port, args.vix_baud, log)
        pico = Pico(args.pico_port, args.pico_baud, log)
        preflight_with_serial_retry(
            vix, pico, log, run_dir,
            bench_no_estop=args.bench_no_estop,
            dirinv=False,
            encsign=-1,
        )
        configure_pico_policy(
            pico, args.bench_no_estop, dirinv=False, encsign=-1,
            watchdog_ms=args.watchdog_ms,
        )

        # Phase 1: disabled encoder drift/noise, no servo force.
        vix.off()
        pico.force_safe()
        with contextlib_suppress():
            pico.command("CLEAR")
            pico.command("DIAG CLEAR")
        safe_pico_zero(pico, reason="off_disabled_hold_noise_probe")
        summaries.append(sample_phase(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            phase_name="off_disabled",
            duration_s=args.off_duration_s,
            interval_s=args.sample_interval_s,
            movement_abort_counts=args.abort_span_counts,
        ))

        # V4.62 phase order: start with drive-enabled/no-servo-force, then
        # no-integral P/V hold, then add tiny GI.  This tells us whether the
        # blocker is motor-enable EMI, base servo-loop instability, or GI hunting.
        phases = [
            ("on_zero_gains_cl1", Gains(0, 0, 0, 0, 0), 1),
            ("on_gi0_gp0p25_gv0p25_cl1", Gains(0, 0, 0.25, 0.25, 0), 1),
            ("on_gi0_gp0p5_gv0p5_cl1", Gains(0, 0, 0.50, 0.50, 0), 1),
            ("on_gi0_gp1_gv0p75_cl1", Gains(0, 0, 1.00, 0.75, 0), 1),
            ("on_gi0_gp2_gv1_cl1", Gains(0, 0, 2.00, 1.00, 0), 1),
            ("on_gi0p02_gp2_gv1_cl1", Gains(0, 0.02, 2.00, 1.00, 0), 1),
            ("on_gi0p05_gp2_gv1_cl1", Gains(0, 0.05, 2.00, 1.00, 0), 1),
            ("on_gi0p1_gp2_gv1_cl1", Gains(0, 0.10, 2.00, 1.00, 0), 1),
            ("on_gi0p1_gp2_gv1_cl2", Gains(0, 0.10, 2.00, 1.00, 0), 2),
            ("on_gi0p2_gp2_gv1_cl1", Gains(0, 0.20, 2.00, 1.00, 0), 1),
            ("on_gi0p3_gp2_gv1_cl1", Gains(0, 0.30, 2.00, 1.00, 0), 1),
            ("on_gi0p5_gp2_gv1_cl1", Gains(0, 0.50, 2.00, 1.00, 0), 1),
        ]
        for phase_name, gains, cl in phases:
            if STOP_REQUESTED:
                break
            log.say(f"Preparing {phase_name}: gains={gains.label()}, CL={cl}%, IW={args.iw_counts}; no commanded move.")
            phase_result: dict[str, Any] = {
                "phase": phase_name,
                "gains": asdict(gains),
                "cl_percent": cl,
                "iw_counts": args.iw_counts,
            }
            try:
                temporary_vix_setup(
                    vix, gains, cl_percent=cl,
                    tl_counts=args.abort_span_counts,
                    iw_counts=args.iw_counts,
                )
                configure_pico_policy(
                    pico, args.bench_no_estop, dirinv=False, encsign=-1,
                    watchdog_ms=args.watchdog_ms,
                )
                zero_report = safe_prepare(vix, pico, args.abort_span_counts)
                phase_result["zero_report"] = zero_report
                pico.start_heartbeat()
                energize_drive(vix, pico)
                summaries.append(sample_phase(
                    vix=vix, pico=pico, log=log, run_dir=run_dir,
                    phase_name=phase_name,
                    duration_s=args.on_duration_s,
                    interval_s=args.sample_interval_s,
                    movement_abort_counts=args.abort_span_counts,
                ))
            except Exception as exc:
                phase_result["error"] = str(exc)
                log.say(f"{phase_name}: stopped/failed safely: {exc}")
                summaries.append({
                    **phase_result,
                    "hard_stop": str(exc),
                    "samples": 0,
                    "pico_position": stats([]),
                    "encoder_invalid_delta": None,
                })
                # A no-motion latch during ON is diagnostic and safety-relevant.
                # Stop later ON phases after a real Pico/ViX latch or large movement.
                text = str(exc)
                hard_safety_tokens = (
                    "pico_latch:", "VIX_FAULT", "ENCODER_INVALID",
                    "movement_exceeded", "pico_reports_vix_fault_active",
                )
                if any(word in text for word in hard_safety_tokens):
                    break
            finally:
                if pico is not None:
                    with contextlib_suppress():
                        pico.stop_heartbeat()
                if vix is not None and pico is not None:
                    with contextlib_suppress():
                        deenergize_drive(vix, pico)
                    with contextlib_suppress():
                        pico.command("ABORT")
                        pico.command("ENABLE 0")
                        pico.command("DISARM")

        verdict = classify(summaries)
        report = {
            "version": "v4.62",
            "created": datetime.now().isoformat(timespec="seconds"),
            "counts_per_mm": COUNTS_PER_MM,
            "nm_per_count": NM_PER_COUNT,
            "durations": {
                "off_duration_s": args.off_duration_s,
                "on_duration_s": args.on_duration_s,
                "sample_interval_s": args.sample_interval_s,
            },
            "summaries": summaries,
            "verdict": verdict,
        }
        (run_dir / "HOLD_NOISE_PROBE_SUMMARY.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        verdict_text = [
            "HOLD/NOISE PROBE VERDICT",
            f"likely_blocker: {verdict['likely_blocker']}",
            f"off_span_counts: {verdict.get('off_span_counts')} ({verdict.get('off_span_nm')} nm)",
            f"best_on_span_counts: {verdict.get('best_on_span_counts')}",
            f"worst_on_span_counts: {verdict.get('worst_on_span_counts')}",
            "",
            "Findings:",
            *[f"- {x}" for x in verdict.get("findings", [])],
            "",
            "Next steps:",
            *[f"- {x}" for x in verdict.get("next_steps", [])],
            "",
        ]
        (run_dir / "HOLD_NOISE_VERDICT.txt").write_text("\n".join(verdict_text), encoding="utf-8")
        log.say("\n" + "\n".join(verdict_text))
        code = 0
    except Exception as exc:
        log.say(f"\nABORT: Hold/noise probe stopped safely: {exc}")
        code = 1
    finally:
        if pico is not None:
            with contextlib_suppress():
                pico.stop_heartbeat()
        if vix is not None and pico is not None:
            with contextlib_suppress():
                deenergize_drive(vix, pico, verify=False)
        if vix is not None:
            with contextlib_suppress():
                vix.close()
        if pico is not None:
            with contextlib_suppress():
                pico.close()
        log.say(f"Evidence directory: {run_dir}")
        log.close()
    return code


def safe_prepare(vix: Vix, pico: Pico, ferrmax: int) -> dict[str, Any]:
    # Import here to keep the top import list focused and preserve the original helper.
    from vix100nm_commission import prepare_pico_for_enable  # type: ignore
    return prepare_pico_for_enable(vix, pico, ferrmax)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V4.62 no-motion hold/EMI/integrator discriminator for ViX/Pico 100 nm commissioning")
    p.add_argument("--vix-port", default="/dev/ttyUSB0")
    p.add_argument("--pico-port", default="/dev/ttyACM0")
    p.add_argument("--vix-baud", type=int, default=9600)
    p.add_argument("--pico-baud", type=int, default=115200)
    p.add_argument("--bench-no-estop", action="store_true")
    p.add_argument("--output-root", type=Path, default=Path.home() / "vix100nm_runs")
    p.add_argument("--off-duration-s", type=float, default=30.0)
    p.add_argument("--on-duration-s", type=float, default=20.0)
    p.add_argument("--sample-interval-s", type=float, default=0.20)
    p.add_argument("--watchdog-ms", type=int, default=5000)
    p.add_argument("--iw-counts", type=int, default=1000)
    p.add_argument("--abort-span-counts", type=int, default=5000)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(run_probe(parse_args()))
