#!/usr/bin/env python3
"""Settled-tail gain mini-sweep for ViX500AE/MX80L/Pico2.

v4.74 deliberately does NOT command STEP/DIR moves.  The latest v4.72 run showed
Candidate B can have a settled-tail span near 200 counts in some starting states,
so motion proof is premature.  This script attacks the current blocker directly:
find a gain/current-clamp candidate that becomes quiet after the one-time enable
kick and after the candidate's own pull-in transient.

Workflow:
  1. Safe preflight and OFF baseline.
  2. Enable once with zero PIVF gains and low CL, allowing one bounded ON kick.
  3. Test a bounded mini-sweep of already-energised gain candidates.
  4. Score only the settled tail of each hold window, not the initial pull-in.
  5. Re-apply the best passing candidate and require confirmation windows.
  6. Restore/OFF and auto-zip evidence.

If this produces a confirmed candidate, use that exact candidate in the next
separate focused motion proof.  If it does not, do not keep trying 100 nm moves;
fix hold/noise/commutation/mechanics first.
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

# Reuse the Pico-fast post-enable helpers from the debugged v4.69+ diagnostic.
import vix_post_enable_settle_probe as settle  # type: ignore

STOP_REQUESTED = False
NM_PER_COUNT = 10
DIRINV = False
ENCSIGN = -1
ZERO_GAINS = Gains(0, 0, 0, 0, 0)

# Small, bounded sweep around the candidates that have looked promising, plus
# slightly more damping/filtering options.  Do not add aggressive GP/GV combos
# here; this is a hold/noise discriminator, not final tuning.
SWEEP_CANDIDATES: tuple[tuple[str, Gains, int], ...] = (
    ("soft_gp1_gv0p75_cl1", Gains(0, 0.00, 1.00, 0.75, 0), 1),
    ("soft_gp1_gv0p75_cl2", Gains(0, 0.00, 1.00, 0.75, 0), 2),
    ("mid_gi0p05_gp1p5_gv1_cl1", Gains(0, 0.05, 1.50, 1.00, 0), 1),
    ("mid_gi0p05_gp1p5_gv1_cl2", Gains(0, 0.05, 1.50, 1.00, 0), 2),
    ("mid_gi0p1_gp1p5_gv1_cl1", Gains(0, 0.10, 1.50, 1.00, 0), 1),
    ("mid_gi0p1_gp1p5_gv1_cl2", Gains(0, 0.10, 1.50, 1.00, 0), 2),
    ("stage2_gi0p1_gp2_gv1_cl1", Gains(0, 0.10, 2.00, 1.00, 0), 1),
    ("stage2_gi0p1_gp2_gv1_cl2", Gains(0, 0.10, 2.00, 1.00, 0), 2),
    ("stage4_gi0p2_gp2_gv1_cl1", Gains(0, 0.20, 2.00, 1.00, 0), 1),
    ("stage4_gi0p2_gp2_gv1_cl2", Gains(0, 0.20, 2.00, 1.00, 0), 2),
    ("fine_gi0p5_gp2_gv1_cl1", Gains(0, 0.50, 2.00, 1.00, 0), 1),
    ("fine_gi0p5_gp2_gv1_cl2", Gains(0, 0.50, 2.00, 1.00, 0), 2),
    ("damped_gi0p2_gp2_gv1p5_cl2", Gains(0, 0.20, 2.00, 1.50, 0), 2),
    ("damped_gi0p5_gp2_gv1p5_cl2", Gains(0, 0.50, 2.00, 1.50, 0), 2),
    ("filtered_gi0p2_gp2_gv1_ft1_cl2", Gains(0, 0.20, 2.00, 1.00, 1), 2),
    ("filtered_gi0p5_gp2_gv1_ft1_cl2", Gains(0, 0.50, 2.00, 1.00, 1), 2),
)


def signal_handler(signum: int, frame: object) -> None:  # pragma: no cover
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def make_run_dir(root: Path) -> Path:
    path = root / f"{now_stamp()}_settled_tail_gain_sweep"
    path.mkdir(parents=True, exist_ok=False)
    return path


def bundle_run_dir(run_dir: Path) -> Path:
    archive_base = run_dir.parent / run_dir.name
    zip_path = archive_base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    made = shutil.make_archive(str(archive_base), "zip", root_dir=run_dir.parent, base_dir=run_dir.name)
    return Path(made)


def prepare_local_zero_off(vix: Vix, pico: Pico, log: RunLog, args: argparse.Namespace) -> dict[str, Any]:
    temporary_vix_setup(vix, ZERO_GAINS, cl_percent=args.kick_cl_percent, tl_counts=args.tl_counts, iw_counts=args.iw_counts)
    configure_pico_policy(pico, args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN, watchdog_ms=args.watchdog_ms)
    pico.config("FERRMAX", args.ferrmax_counts)

    old_counts = vixcore.LOCAL_ZERO_STATIONARY_COUNTS
    old_window = vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S
    old_wait = vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S
    vixcore.LOCAL_ZERO_STATIONARY_COUNTS = int(args.local_zero_settle_counts)
    vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S = float(args.local_zero_window_s)
    vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S = float(args.local_zero_max_wait_s)
    prep: dict[str, Any] = {"phase": "settled_tail_gain_sweep_pre_enable_local_zero"}
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


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def tail_metrics_from_sample_csv(summary: dict[str, Any], run_dir: Path, *, tail_s: float) -> dict[str, Any]:
    csv_name = summary.get("csv")
    if not csv_name:
        return {"ok": False, "reason": "missing_csv_name"}
    csv_path = run_dir / str(csv_name)
    if not csv_path.exists():
        return {"ok": False, "reason": f"missing_csv:{csv_path.name}"}
    rows = _read_csv_rows(csv_path)
    if not rows:
        return {"ok": False, "reason": "no_rows"}
    try:
        t_end = max(float(r["elapsed_s"]) for r in rows)
        tail = [r for r in rows if float(r["elapsed_s"]) >= t_end - float(tail_s)]
        vals = [float(r["pico_delta_from_reference"]) for r in tail]
        fe_vals = [float(r["pico_following_error"]) for r in tail if "pico_following_error" in r]
    except Exception as exc:
        return {"ok": False, "reason": f"parse_error:{exc}"}
    if len(vals) < 8:
        return {"ok": False, "reason": f"insufficient_tail_samples:{len(vals)}"}
    return {
        "ok": True,
        "tail_s": tail_s,
        "tail_samples": len(vals),
        "tail_first": vals[0],
        "tail_last": vals[-1],
        "tail_min": min(vals),
        "tail_max": max(vals),
        "tail_span_counts": max(vals) - min(vals),
        "tail_drift_counts": vals[-1] - vals[0],
        "tail_abs_drift_counts": abs(vals[-1] - vals[0]),
        "tail_max_abs_from_first_counts": max(abs(v - vals[0]) for v in vals),
        "tail_median_counts": statistics.median(vals),
        "tail_fe_span_counts": (max(fe_vals) - min(fe_vals) if fe_vals else None),
    }


def gate_tail(metrics: dict[str, Any], args: argparse.Namespace) -> bool:
    if not metrics.get("ok"):
        return False
    return bool(
        float(metrics.get("tail_span_counts", 1e9)) <= float(args.hold_tail_span_counts)
        and abs(float(metrics.get("tail_drift_counts", 1e9))) <= float(args.hold_tail_drift_counts)
        and float(metrics.get("tail_max_abs_from_first_counts", 1e9)) <= float(args.hold_tail_span_counts)
    )


def candidate_score(c: dict[str, Any]) -> tuple[float, float, float, float]:
    m = c.get("tail_metrics", {})
    if not m.get("ok"):
        return (1e9, 1e9, 1e9, 1e9)
    full_span = c.get("hold_summary", {}).get("pico_delta_from_reference", {}).get("span")
    return (
        float(m.get("tail_span_counts", 1e9)),
        abs(float(m.get("tail_drift_counts", 1e9))),
        float(m.get("tail_max_abs_from_first_counts", 1e9)),
        float(full_span) if isinstance(full_span, (int, float)) else 1e9,
    )


def no_hard_failure(summary: dict[str, Any], args: argparse.Namespace) -> bool:
    return bool(
        not summary.get("hard_stop")
        and int(summary.get("samples") or 0) >= int(args.min_samples)
        and int(summary.get("encoder_invalid_delta_from_reference") or 0) == 0
    )


def apply_and_measure_candidate(
    *,
    vix: Vix,
    pico: Pico,
    log: RunLog,
    run_dir: Path,
    label: str,
    gains: Gains,
    cl_percent: int,
    args: argparse.Namespace,
    phase_prefix: str,
) -> dict[str, Any]:
    c: dict[str, Any] = {
        "label": label,
        "gains": asdict(gains),
        "gains_label": gains.label(),
        "cl_percent": int(cl_percent),
        "phase_prefix": phase_prefix,
    }
    log.say(f"\nTesting settled-tail candidate {label}: gains={gains.label()}, CL={cl_percent}%")
    settle.apply_gains_while_on(vix, ZERO_GAINS, args.kick_cl_percent, args)
    time.sleep(float(args.candidate_settle_before_zero_s))
    c["pre_candidate_vix_zero"] = settle.vix_post_kick_zero(vix, log)
    c["reference_before_gains"] = settle.snapshot(vix, pico)

    settle.apply_gains_while_on(vix, gains, int(cl_percent), args)
    time.sleep(float(args.candidate_settle_after_gain_s))
    c["post_gain_vix_zero"] = settle.vix_post_kick_zero(vix, log)
    candidate_ref = settle.snapshot(vix, pico)
    c["reference_after_gain_settle"] = candidate_ref

    c["hold_summary"] = settle.sample_window(
        vix=vix,
        pico=pico,
        log=log,
        run_dir=run_dir,
        name=f"{phase_prefix}_hold_{label}",
        duration_s=float(args.hold_window_s),
        interval_s=float(args.sample_interval_s),
        reference=candidate_ref,
        min_samples=int(args.min_samples),
        abort_from_reference_counts=None,
        abort_within_window_counts=int(args.hold_abort_span_counts),
    )
    c["tail_metrics"] = tail_metrics_from_sample_csv(c["hold_summary"], run_dir, tail_s=float(args.hold_tail_s))
    c["passes_tail_gate"] = bool(no_hard_failure(c["hold_summary"], args) and gate_tail(c["tail_metrics"], args))
    c["score_tuple"] = candidate_score(c)
    hs = c["hold_summary"]
    log.say(
        f"{label}: whole_span={hs.get('pico_delta_from_reference', {}).get('span')} "
        f"tail_span={c['tail_metrics'].get('tail_span_counts')} "
        f"tail_drift={c['tail_metrics'].get('tail_drift_counts')} "
        f"tail_pass={c['passes_tail_gate']}"
    )
    return c


def classify(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    candidates = report.get("candidates", [])
    passing = [c for c in candidates if c.get("passes_tail_gate")]
    confirmed = report.get("best_confirmation", [])
    confirmed_pass = bool(confirmed and all(c.get("passes_tail_gate") for c in confirmed))
    kick = report.get("kick_window", {}).get("pico_delta_from_reference", {}).get("max_abs_from_first")

    findings: list[str] = []
    next_steps: list[str] = []
    best = min(candidates, key=candidate_score) if candidates else None
    if isinstance(kick, (int, float)):
        findings.append(f"Enable kick was bounded at {kick} counts = {float(kick) * NM_PER_COUNT:.0f} nm.")
    if best:
        m = best.get("tail_metrics", {})
        findings.append(
            f"Best first-pass candidate: {best.get('label')} with tail span {m.get('tail_span_counts')} counts "
            f"and tail drift {m.get('tail_drift_counts')} counts."
        )
    if passing:
        findings.append("At least one candidate passed the settled-tail hold gate in the first sweep.")
    else:
        findings.append("No candidate passed the settled-tail hold gate; do not run motion proof yet.")
    if confirmed_pass:
        best_conf = confirmed[-1]
        findings.append(
            f"Best candidate was re-applied and confirmed: {best_conf.get('label')} "
            f"tail span {best_conf.get('tail_metrics', {}).get('tail_span_counts')} counts."
        )
        next_steps.append("Use this confirmed candidate in the next focused 500/200/100 nm motion proof.")
        status = "confirmed_settled_tail_candidate_ready_for_motion_proof"
    elif passing:
        next_steps.append("A candidate passed once but did not confirm twice; repeat this sweep before motion proof.")
        status = "candidate_found_but_not_confirmed"
    else:
        next_steps.append("Fix hold/noise/settling first: cable preload, grounding/shielding, commutation/start-position dependence, or try a wider low-gain damping sweep.")
        status = "post_enable_hold_not_stable_enough_for_motion"
    return {
        "status": status,
        "passing_candidates": [c.get("label") for c in passing],
        "best_candidate": best,
        "confirmed_candidate": confirmed[-1] if confirmed_pass else None,
        "findings": findings,
        "next_steps": next_steps,
        "settings_used": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
    }


def run_probe(args: argparse.Namespace) -> int:
    run_dir = make_run_dir(args.output_root)
    log = RunLog(run_dir)
    vix: Vix | None = None
    pico: Pico | None = None
    code = 1
    report: dict[str, Any] = {
        "version": "v4.74",
        "created": datetime.now().isoformat(timespec="seconds"),
        "test_intent": "Enable once, run an already-energised settled-tail gain mini-sweep, confirm the best candidate, and do not command motion.",
        "candidates_planned": [{"label": l, "gains": asdict(g), "cl_percent": cl} for l, g, cl in SWEEP_CANDIDATES],
        "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
    }
    try:
        log.say("SETTLED-TAIL GAIN MINI-SWEEP v4.74: no STEP/DIR moves; find/confirm a quiet already-energised hold candidate.")
        log.say(f"Evidence directory: {run_dir}")
        vix = Vix(args.vix_port, args.vix_baud, log)
        pico = Pico(args.pico_port, args.pico_baud, log)
        report["preflight"] = preflight_with_serial_retry(
            vix, pico, log, run_dir, bench_no_estop=args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN
        )

        with contextlib.suppress(Exception):
            deenergize_drive(vix, pico, verify=False)
        with contextlib.suppress(Exception):
            pico.force_safe()
        with contextlib.suppress(Exception):
            pico.command("CLEAR")
            pico.command("DIAG CLEAR")
        safe_pico_zero(pico, reason="settled_tail_gain_sweep_initial")
        report["pre_enable_local_zero"] = prepare_local_zero_off(vix, pico, log, args)
        reference_before_enable = settle.snapshot(vix, pico)
        report["reference_before_enable"] = reference_before_enable

        report["off_pre_enable_baseline"] = settle.sample_window(
            vix=vix,
            pico=pico,
            log=log,
            run_dir=run_dir,
            name="sweep_off_pre_enable_baseline",
            duration_s=float(args.off_baseline_s),
            interval_s=float(args.sample_interval_s),
            reference=reference_before_enable,
            min_samples=int(args.min_samples),
            abort_from_reference_counts=int(args.max_allow_kick_counts),
            abort_within_window_counts=int(args.pre_off_abort_span_counts),
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
            name="sweep_post_enable_kick_window_zero_gains",
            duration_s=float(args.kick_window_s),
            interval_s=float(args.sample_interval_s),
            reference=reference_before_enable,
            min_samples=int(args.min_samples),
            abort_from_reference_counts=int(args.max_allow_kick_counts),
            abort_within_window_counts=None,
        )
        if report["kick_window"].get("hard_stop"):
            raise CommissionAbort(f"Hard stop during bounded kick window: {report['kick_window'].get('hard_stop')}")

        candidates: list[dict[str, Any]] = []
        for label, gains, cl_percent in SWEEP_CANDIDATES:
            if STOP_REQUESTED:
                raise CommissionAbort("operator_stop")
            try:
                c = apply_and_measure_candidate(
                    vix=vix,
                    pico=pico,
                    log=log,
                    run_dir=run_dir,
                    label=label,
                    gains=gains,
                    cl_percent=cl_percent,
                    args=args,
                    phase_prefix="sweep",
                )
            except Exception as exc:
                c = {
                    "label": label,
                    "gains": asdict(gains),
                    "gains_label": gains.label(),
                    "cl_percent": cl_percent,
                    "error": str(exc),
                    "passes_tail_gate": False,
                    "score_tuple": [1e9, 1e9, 1e9, 1e9],
                }
                log.say(f"Candidate {label} stopped safely: {exc}")
                text = str(exc)
                if any(token in text for token in ("Pico latch", "fault line", "Encoder-invalid", "Movement exceeded", "operator_stop")):
                    candidates.append(c)
                    break
            candidates.append(c)
            (run_dir / "SETTLED_TAIL_GAIN_SWEEP_INTERMEDIATE.json").write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")

        report["candidates"] = candidates
        passing = [c for c in candidates if c.get("passes_tail_gate")]
        if passing:
            best = min(passing, key=candidate_score)
            report["best_first_pass"] = best
            log.say(f"\nConfirming best first-pass candidate: {best.get('label')}")
            # Repeat the best candidate twice.  If it cannot repeat, it is not ready for motion proof.
            chosen_label = str(best["label"])
            chosen_tuple = next((item for item in SWEEP_CANDIDATES if item[0] == chosen_label), None)
            confirmations: list[dict[str, Any]] = []
            if chosen_tuple is not None:
                for idx in range(1, int(args.confirmation_windows) + 1):
                    label, gains, cl_percent = chosen_tuple
                    conf = apply_and_measure_candidate(
                        vix=vix,
                        pico=pico,
                        log=log,
                        run_dir=run_dir,
                        label=f"{label}_confirm{idx}",
                        gains=gains,
                        cl_percent=cl_percent,
                        args=args,
                        phase_prefix="confirm",
                    )
                    conf["base_label"] = label
                    confirmations.append(conf)
            report["best_confirmation"] = confirmations
        else:
            report["best_first_pass"] = min(candidates, key=candidate_score) if candidates else None
            report["best_confirmation"] = []

        report["verdict"] = classify(report, args)
        lines = [
            "SETTLED-TAIL GAIN SWEEP VERDICT",
            f"status: {report['verdict'].get('status')}",
            f"passing_candidates: {', '.join(report['verdict'].get('passing_candidates', [])) or 'none'}",
            f"confirmed_candidate: {report['verdict'].get('confirmed_candidate', {}).get('base_label') if report['verdict'].get('confirmed_candidate') else 'none'}",
            "",
            "Findings:",
            *[f"- {x}" for x in report["verdict"].get("findings", [])],
            "",
            "Next steps:",
            *[f"- {x}" for x in report["verdict"].get("next_steps", [])],
            "",
        ]
        (run_dir / "SETTLED_TAIL_GAIN_SWEEP_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (run_dir / "SETTLED_TAIL_GAIN_SWEEP_VERDICT.txt").write_text("\n".join(lines), encoding="utf-8")
        log.say("\n" + "\n".join(lines))
        code = 0
    except Exception as exc:
        report["abort"] = str(exc)
        if "verdict" not in report:
            report["verdict"] = {
                "status": "aborted_before_verdict",
                "passing_candidates": [],
                "confirmed_candidate": None,
                "findings": ["Sweep stopped safely before final verdict; do not treat as a pass."],
                "next_steps": ["Inspect SETTLED_TAIL_GAIN_SWEEP_SUMMARY.json and per-window CSVs, then fix the abort reason."],
            }
        with contextlib.suppress(Exception):
            (run_dir / "SETTLED_TAIL_GAIN_SWEEP_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        log.say(f"\nABORT: Settled-tail gain sweep stopped safely: {exc}")
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
                (run_dir / "SETTLED_TAIL_GAIN_SWEEP_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            log.say(f"Evidence bundle: {bundle_path}")
        except Exception as exc:
            log.say(f"Evidence bundle creation failed: {exc}")
        log.close()
    return code


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v4.74 settled-tail gain mini-sweep; no commanded moves")
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
    p.add_argument("--off-baseline-s", type=float, default=3.0)
    p.add_argument("--kick-window-s", type=float, default=2.5)
    p.add_argument("--hold-window-s", type=float, default=6.0)
    p.add_argument("--candidate-settle-before-zero-s", type=float, default=0.5)
    p.add_argument("--candidate-settle-after-gain-s", type=float, default=6.0)
    p.add_argument("--sample-interval-s", type=float, default=0.05)
    p.add_argument("--hold-tail-s", type=float, default=2.0)
    p.add_argument("--hold-tail-span-counts", type=int, default=25)
    p.add_argument("--hold-tail-drift-counts", type=int, default=15)
    p.add_argument("--min-samples", type=int, default=20)
    p.add_argument("--local-zero-settle-counts", type=int, default=20)
    p.add_argument("--local-zero-window-s", type=float, default=0.25)
    p.add_argument("--local-zero-max-wait-s", type=float, default=20.0)
    p.add_argument("--confirmation-windows", type=int, default=2)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(run_probe(parse_args()))
