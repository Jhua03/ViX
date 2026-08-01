#!/usr/bin/env python3
"""Post-enable settle discriminator for ViX500AH/MX80L/Pico2 commissioning.

V4.69 is intentionally NOT a final 100 nm validation script.  It allows the
known ViX ON transient to occur once, then asks the useful question: after the
kick, can the already-energised system be re-referenced and hold quietly?

No STEP/DIR motion moves are commanded.  The only potentially state-changing
operations while energised are:
  * keep zero PIVF gains during the initial ON transition,
  * optionally issue a bounded ViX W(PA,0)/W(PT,0)/W(PF,0)/W(PE,0) post-kick
    reference reset while CL is low and gains are zero,
  * apply bounded hold-gain candidates while already energised and watch for
    quiet hold/noise, faults, encoder invalid, or runaway.

The Pico is NOT zeroed while X4 enable is high; firmware correctly forbids
that.  This is diagnostic evidence, not a final stage pass.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import signal
import shutil
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

STOP_REQUESTED = False
NM_PER_COUNT = 10
VIX500_CR_COUNTS_PER_A_RMS = 62136.0
ZERO_GAINS = Gains(0, 0, 0, 0, 0)
DIRINV = False
ENCSIGN = -1

# Bounded candidates.  These are not final tune recommendations; they ask if
# any already-energised hold configuration stays quiet after the ON transient.
HOLD_CANDIDATES: tuple[tuple[str, Gains, int], ...] = (
    ("zero_gains_cl1", Gains(0, 0, 0, 0, 0), 1),
    ("soft_gp0p25_gv0p25_cl1", Gains(0, 0, 0.25, 0.25, 0), 1),
    ("soft_gp0p5_gv0p5_cl1", Gains(0, 0, 0.50, 0.50, 0), 1),
    ("nog_i_gp1_gv0p75_cl1", Gains(0, 0, 1.00, 0.75, 0), 1),
    ("nog_i_gp2_gv1_cl1", Gains(0, 0, 2.00, 1.00, 0), 1),
    ("tiny_gi0p02_gp2_gv1_cl1", Gains(0, 0.02, 2.00, 1.00, 0), 1),
    ("tiny_gi0p05_gp2_gv1_cl1", Gains(0, 0.05, 2.00, 1.00, 0), 1),
    ("stage2_gi0p1_gp2_gv1_cl1", Gains(0, 0.10, 2.00, 1.00, 0), 1),
    ("stage4_gi0p2_gp2_gv1_cl1", Gains(0, 0.20, 2.00, 1.00, 0), 1),
    ("fine_gi0p5_gp2_gv1_cl1", Gains(0, 0.50, 2.00, 1.00, 0), 1),
    ("stage2_gi0p1_gp2_gv1_cl2", Gains(0, 0.10, 2.00, 1.00, 0), 2),
    ("stage4_gi0p2_gp2_gv1_cl2", Gains(0, 0.20, 2.00, 1.00, 0), 2),
    ("fine_gi0p5_gp2_gv1_cl2", Gains(0, 0.50, 2.00, 1.00, 0), 2),
)


def signal_handler(signum: int, frame: object) -> None:  # pragma: no cover
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def make_run_dir(root: Path) -> Path:
    path = root / f"{now_stamp()}_post_enable_settle_probe"
    path.mkdir(parents=True, exist_ok=False)
    return path


def bundle_run_dir(run_dir: Path) -> Path:
    """Create an adjacent .zip evidence bundle for this run directory.

    The archive is made in run_dir.parent as <run_dir.name>.zip, so it is not
    recursively included inside itself.  This is called even on safe aborts.
    """
    archive_base = run_dir.parent / run_dir.name
    zip_path = archive_base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    made = shutil.make_archive(str(archive_base), "zip", root_dir=run_dir.parent, base_dir=run_dir.name)
    return Path(made)


def pct(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, max(0, int(math.ceil(q * len(sorted_values)) - 1)))
    return sorted_values[idx]


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "first": None, "last": None, "min": None, "max": None, "span": None, "drift": None, "median": None, "p95_abs_from_first": None, "max_abs_from_first": None}
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


def snapshot(vix: Vix, pico: Pico) -> dict[str, Any]:
    """Fast Pico-only status snapshot for repeated no-motion windows.

    The Pico is the high-rate observer for this test: it receives the ViX X4
    encoder outputs and sees the ViX fault line.  Repeated ViX serial reports
    are deliberately not used here because this particular drive sometimes
    returns echo-only/no-data replies for reports such as R(PT)/R(ST2) around
    enable.  Those slow/missing reports made v4.64/v4.65 either false-pass
    one-sample windows or abort before the real post-enable hold test.
    """
    del vix  # Keep signature stable; this is intentionally Pico-fast.
    ps = pico.status()
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
        "vix_pa": None,
        "vix_pe": None,
        "vix_pt": None,
        "vix_pf": None,
        "vix_cr": None,
        "vix_st2": None,
        "vix_faults": None,
    }


def vix_snapshot_optional(vix: Vix) -> dict[str, Any]:
    """One non-critical ViX serial snapshot, never used inside fast windows."""
    out: dict[str, Any] = {}
    for name in ("PA", "PE", "CR", "CL", "GF", "GI", "GP", "GV", "FT"):
        try:
            if name in {"GF", "GI", "GP", "GV", "FT"}:
                out[name] = vix.read_float(name)
            else:
                out[name] = vix.read_int(name)
        except Exception as exc:
            out[name] = None
            out[f"{name}_error"] = str(exc)
    with contextlib.suppress(Exception):
        out["faults"] = vix.faults()
    return out


def energize_once_without_st2_poll(vix: Vix, pico: Pico) -> dict[str, Any]:
    """Enable X4 + issue ON without using ViX ST2 as a required handshake.

    v4.65 showed that immediately after ON this drive may stop returning data
    to read-only reports even while the Pico remains alive.  For this
    diagnostic, the proof is the encoder/fault behaviour observed by the Pico;
    ViX ST2 is not allowed to abort the test before the post-enable window.
    """
    pre = pico.status()
    if bool(pre.get("latched")) and str(pre.get("latch")) == "USER_ABORT":
        pico.command("CLEAR")
        pico.command("DIAG CLEAR")
        pre = pico.status()
    if bool(pre.get("latched")):
        raise CommissionAbort(f"Pico latched before energize: {pre}")
    if not bool(pre.get("zeroed", False)) or abs(int(pre.get("following_error", 0))) > 10:
        safe_pico_zero(pico, reason="post_enable_fast_energize_reference_zero")
        pre = pico.status()
    if not bool(pre.get("armed")):
        pico.command("ARM I_UNDERSTAND")
    pico.command("ENABLE 1")
    time.sleep(0.05)
    raw_on = vix.command("ON", timeout_s=1.2, quiet_s=0.15, allow_error=True)
    time.sleep(0.20)
    after = pico.status()
    if bool(after.get("latched")):
        raise CommissionAbort(f"Pico latched during energize: {after}")
    if bool(after.get("fault_active")):
        raise CommissionAbort(f"Pico reports ViX fault line active after ON: {after}")
    return {"before_pico": pre, "raw_on_reply": raw_on, "after_pico": after}


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
    min_samples: int,
    abort_from_reference_counts: int | None,
    abort_within_window_counts: int | None,
    hard_stop_on_fault: bool = True,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    start = time.monotonic()
    ref_pico = int(reference.get("pico_encoder_position", 0)) if reference else None
    ref_raw = int(reference.get("pico_encoder_raw", 0)) if reference else None
    ref_vix = reference.get("vix_pa") if reference else None
    ref_invalid = int(reference.get("pico_encoder_invalid", 0)) if reference else None
    first_pico: int | None = None
    hard_stop: str | None = None

    min_samples = max(2, int(min_samples))
    # Keep sampling until both the requested time and the minimum sample count
    # are satisfied.  This avoids v4.64's one-sample false-pass behaviour when
    # serial reports are slow.
    while True:
        if STOP_REQUESTED:
            hard_stop = "operator_stop"
            break
        elapsed_before = time.monotonic() - start
        if elapsed_before >= duration_s and len(rows) >= min_samples:
            break
        try:
            row = snapshot(vix, pico)
        except Exception as exc:
            hard_stop = f"snapshot_failed:{exc}"
            break
        elapsed = time.monotonic() - start
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
        if hard_stop_on_fault and bool(row.get("pico_fault_active")):
            hard_stop = "pico_reports_vix_fault_active"
            break
        if abort_from_reference_counts is not None and ref_pico is not None:
            if abs(int(row["pico_encoder_position"]) - ref_pico) > abort_from_reference_counts:
                hard_stop = f"movement_exceeded_{abort_from_reference_counts}_counts_from_reference"
                break
        if abort_within_window_counts is not None and first_pico is not None:
            if abs(int(row["pico_encoder_position"]) - first_pico) > abort_within_window_counts:
                hard_stop = f"movement_exceeded_{abort_within_window_counts}_counts_within_window"
                break
        time.sleep(interval_s)

    csv_path = run_dir / f"{name}.csv"
    if rows:
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

    cr_stats = stats(cr_vals)
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
        "vix_cr": cr_stats,
        "vix_cr_amps_rms": {k: ((v / VIX500_CR_COUNTS_PER_A_RMS) if isinstance(v, (int, float)) and k not in {"n"} else v) for k, v in cr_stats.items()},
        "encoder_invalid_delta_from_reference": invalid_delta,
        "first_row": rows[0] if rows else None,
        "final_row": rows[-1] if rows else None,
        "csv": csv_path.name if rows else None,
    }
    (run_dir / f"{name}_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    st = summary["pico_delta_from_reference"]
    log.say(
        f"{name}: samples={len(rows)}, ref_delta_span={st.get('span')} counts, "
        f"ref_delta_final={st.get('last')} counts, FE_span={summary['following_error'].get('span')} counts, "
        f"PE_span={summary['vix_pe'].get('span')} counts, invalid_delta={invalid_delta}, hard_stop={hard_stop}"
    )
    return summary


def temporary_setup(vix: Vix, pico: Pico, args: argparse.Namespace, gains: Gains, cl_percent: int) -> None:
    temporary_vix_setup(
        vix,
        gains,
        cl_percent=cl_percent,
        tl_counts=args.tl_counts,
        iw_counts=args.iw_counts,
    )
    configure_pico_policy(
        pico,
        args.bench_no_estop,
        dirinv=DIRINV,
        encsign=ENCSIGN,
        watchdog_ms=args.watchdog_ms,
    )
    pico.config("FERRMAX", args.ferrmax_counts)


def prepare_local_zero_off(vix: Vix, pico: Pico, log: RunLog, result: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    temporary_setup(vix, pico, args, ZERO_GAINS, args.kick_cl_percent)

    # v4.68 evidence after the X5 debounce firmware showed the OFF encoder was
    # no longer noisy, but the carriage/drive reference could relax by roughly
    # 10-15 counts per 250 ms immediately after Stage 8.  The shared Stage-2/3
    # local-zero helper is intentionally strict (5 counts and a small total
    # drift cap), which is good for final validation but too aggressive for this
    # diagnostic discriminator.
    #
    # For this probe only, relax the local-zero preparation gate while still
    # bounding it to the same order as the post-enable quiet gate.  We record the
    # values in the summary settings.  Final 100 nm proof will use stricter
    # gates after this diagnostic tells us whether already-energised hold can
    # settle.
    old_counts = vixcore.LOCAL_ZERO_STATIONARY_COUNTS
    old_window = vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S
    old_wait = vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S
    vixcore.LOCAL_ZERO_STATIONARY_COUNTS = int(args.local_zero_settle_counts)
    vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S = float(args.local_zero_window_s)
    vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S = float(args.local_zero_max_wait_s)
    try:
        return prepare_pico_for_enable_with_stale_vix_reset(
            vix,
            pico,
            log,
            result,
            gains=ZERO_GAINS,
            cl_percent=args.kick_cl_percent,
            tl_counts=args.tl_counts,
            ferrmax=args.ferrmax_counts,
            bench_no_estop=args.bench_no_estop,
            dirinv=DIRINV,
            encsign=ENCSIGN,
            watchdog_ms=args.watchdog_ms,
        )
    finally:
        vixcore.LOCAL_ZERO_STATIONARY_COUNTS = old_counts
        vixcore.LOCAL_ZERO_STATIONARY_WINDOW_S = old_window
        vixcore.LOCAL_ZERO_STATIONARY_MAX_WAIT_S = old_wait


def vix_post_kick_zero(vix: Vix, log: RunLog) -> dict[str, Any]:
    """Reset ViX references at the current energized location without report polling.

    v4.65 proved that read-only reports can fail/no-data immediately after ON.
    This diagnostic therefore treats the W(...) command echoes as the transaction
    evidence and does not wait on R(PT)/R(PF)/R(ST2).  The Pico encoder is the
    trusted observer for quiet/unsafe motion in this probe.
    """
    commands = ["W(PE,0)", "W(PT,0)", "W(PF,0)", "W(PA,0)"]
    history: list[dict[str, Any]] = []
    for cmd in commands:
        try:
            raw = vix.command(cmd, timeout_s=1.2, quiet_s=0.12, allow_error=True)
            history.append({"cmd": cmd, "raw": raw, "ok": True})
        except Exception as exc:
            history.append({"cmd": cmd, "error": str(exc), "ok": False})
            log.say(f"Post-kick zero command {cmd} did not complete cleanly: {exc}")
        time.sleep(0.05)
    return {"ok": all(bool(h.get("ok")) for h in history), "history": history}


def apply_gains_while_on(vix: Vix, gains: Gains, cl_percent: int, args: argparse.Namespace) -> None:
    # De-energised changes are preferred in normal use.  This diagnostic keeps
    # the power stage ON to avoid causing a fresh commutation kick per candidate.
    # CL is set first, then gains are applied from zero/low values.
    for cmd in (f"W(CL,{cl_percent})", f"W(TL,{args.tl_counts})", "W(PC,100)", "W(IM,1)", f"W(IW,{args.iw_counts})", gains.command()):
        vix.command(cmd, timeout_s=2.0, quiet_s=0.15)
        time.sleep(0.06)


def candidate_ok(summary: dict[str, Any], args: argparse.Namespace) -> bool:
    if summary.get("hard_stop"):
        return False
    if int(summary.get("samples") or 0) < int(args.min_samples):
        return False
    if (summary.get("encoder_invalid_delta_from_reference") or 0) != 0:
        return False
    pico_span = summary.get("pico_delta_from_reference", {}).get("span")
    fe_span = summary.get("following_error", {}).get("span")
    pico_abs = summary.get("pico_delta_from_reference", {}).get("max_abs_from_first")
    fe_abs = summary.get("following_error", {}).get("max_abs_from_first")
    vals = [pico_span, fe_span, pico_abs, fe_abs]
    return (
        all(isinstance(v, (int, float)) for v in vals)
        and float(pico_span) <= args.quiet_span_counts
        and float(fe_span) <= args.quiet_span_counts
        and float(pico_abs) <= args.quiet_span_counts
        and float(fe_abs) <= args.quiet_span_counts
    )


def classify(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    kick = report.get("kick_window", {})
    kick_max = kick.get("pico_delta_from_reference", {}).get("max_abs_from_first")
    post = report.get("post_kick_zero_gains_quiet", {})
    post_span = post.get("pico_delta_from_reference", {}).get("span")
    candidates = report.get("hold_candidates", [])
    valid_candidates = [c for c in candidates if c.get("passes_quiet_hold_gate")]
    one_sample_windows = []
    for key in ("off_pre_enable_baseline", "kick_window", "post_kick_zero_gains_quiet"):
        if int(report.get(key, {}).get("samples") or 0) < int(args.min_samples):
            one_sample_windows.append(key)
    for c in candidates:
        if int(c.get("hold_summary", {}).get("samples") or 0) < int(args.min_samples):
            one_sample_windows.append(str(c.get("label")))
    best = None
    if candidates:
        def score(c: dict[str, Any]) -> float:
            s = c.get("hold_summary", {}).get("pico_delta_from_reference", {}).get("span")
            return float(s) if isinstance(s, (int, float)) else 1e18
        best = min(candidates, key=score)
    findings: list[str] = []
    next_steps: list[str] = []
    likely = "unknown"

    if one_sample_windows:
        findings.append(f"Insufficient samples in windows: {', '.join(one_sample_windows[:6])}. This run is not usable for a pass/fail decision.")
        likely = "insufficient_sampling_rerun_required"
        next_steps.append("Rerun v4.69 or newer; do not use v4.64/v4.65 output as proof if it aborted before verdict.")
        return {
            "likely_blocker": likely,
            "enable_kick_max_abs_counts": kick_max,
            "post_kick_zero_gains_span_counts": post_span,
            "quiet_span_gate_counts": args.quiet_span_counts,
            "valid_candidates": [],
            "best_candidate": best,
            "findings": findings,
            "next_steps": next_steps,
        }

    if isinstance(kick_max, (int, float)):
        if kick_max > args.max_allow_kick_counts:
            findings.append(f"Enable kick exceeded the bounded allowance: {kick_max} counts.")
        elif kick_max > 500:
            findings.append(f"Enable kick is large but bounded: {kick_max} counts.")
        else:
            findings.append(f"Enable kick is small in this run: {kick_max} counts.")
    if isinstance(post_span, (int, float)):
        if post_span <= args.quiet_span_counts:
            findings.append(f"After the kick, zero-gain ON hold was quiet: span {post_span} counts.")
        else:
            findings.append(f"After the kick, zero-gain ON hold was still noisy: span {post_span} counts.")
    if valid_candidates:
        likely = "enable_kick_can_be_ignored_after_post_enable_settle"
        labels = ", ".join(str(c.get("label")) for c in valid_candidates[:4])
        findings.append(f"At least one already-energised hold candidate stayed under the quiet gate: {labels}.")
        next_steps.append("Do not run old Stage 6 yet. The next script should use an enable-once/post-kick-settle workflow rather than re-zeroing before every validation attempt.")
        next_steps.append("Use the quietest candidate from POST_ENABLE_SETTLE_SUMMARY.json for the next focused motion proof.")
    else:
        if isinstance(kick_max, (int, float)) and kick_max > args.max_allow_kick_counts:
            likely = "enable_kick_unbounded_do_not_ignore"
            next_steps.append("Do not ignore the kick; inspect commutation/phase/mechanics before more energised tests.")
        elif isinstance(post_span, (int, float)) and post_span > args.quiet_span_counts:
            likely = "post_enable_hold_not_quiet"
            next_steps.append("Do not run final 100 nm validation; the stage does not become quiet after the enable transient.")
            next_steps.append("Reduce mechanical preload/cable force or resolve drive-enable interaction, then repeat this probe.")
        else:
            likely = "no_hold_candidate_passed"
            next_steps.append("No hold candidate passed the quiet gate; inspect per-candidate CSVs before choosing a next tune.")
    return {
        "likely_blocker": likely,
        "enable_kick_max_abs_counts": kick_max,
        "post_kick_zero_gains_span_counts": post_span,
        "quiet_span_gate_counts": args.quiet_span_counts,
        "valid_candidates": valid_candidates,
        "best_candidate": best,
        "findings": findings,
        "next_steps": next_steps,
    }


def run_probe(args: argparse.Namespace) -> int:
    run_dir = make_run_dir(args.output_root)
    log = RunLog(run_dir)
    vix: Vix | None = None
    pico: Pico | None = None
    code = 1
    report: dict[str, Any] = {
        "version": "v4.69",
        "created": datetime.now().isoformat(timespec="seconds"),
        "test_intent": "Allow one ViX ON transient, then test whether post-kick already-energised hold can become quiet. No STEP/DIR moves are commanded.",
        "settings": {**{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}, "hold_candidates": [{"label": l, "gains": asdict(g), "cl_percent": cl} for l, g, cl in HOLD_CANDIDATES]},
    }
    try:
        log.say("POST-ENABLE SETTLE PROBE v4.69: allow one ON kick, then require quiet hold; relaxed pre-zero settle; auto-bundle evidence. No commanded moves.")
        log.say(f"Evidence directory: {run_dir}")
        vix = Vix(args.vix_port, args.vix_baud, log)
        pico = Pico(args.pico_port, args.pico_baud, log)
        preflight = preflight_with_serial_retry(vix, pico, log, run_dir, bench_no_estop=args.bench_no_estop, dirinv=DIRINV, encsign=ENCSIGN)
        report["preflight"] = preflight

        with contextlib.suppress(Exception):
            deenergize_drive(vix, pico, verify=False)
        with contextlib.suppress(Exception):
            pico.force_safe()
        with contextlib.suppress(Exception):
            pico.command("CLEAR")
            pico.command("DIAG CLEAR")
        safe_pico_zero(pico, reason="post_enable_settle_initial")

        zero_result: dict[str, Any] = {}
        report["off_local_zero"] = prepare_local_zero_off(vix, pico, log, zero_result, args)
        report["off_local_zero_recovery"] = zero_result.get("local_zero_reset_recovery")
        ref = snapshot(vix, pico)
        report["reference_before_enable"] = ref

        report["off_pre_enable_baseline"] = sample_window(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            name="off_pre_enable_baseline",
            duration_s=args.off_baseline_s,
            interval_s=args.sample_interval_s,
            reference=ref,
            min_samples=args.min_samples,
            abort_from_reference_counts=args.max_allow_kick_counts,
            abort_within_window_counts=args.pre_off_abort_span_counts,
        )

        log.say("Enabling ViX once with zero gains and low CL; initial kick is allowed only within the bounded window.")
        pico.start_heartbeat()
        before_on = snapshot(vix, pico)
        t0 = time.monotonic()
        handshake = energize_once_without_st2_poll(vix, pico)
        t1 = time.monotonic()
        after_on = snapshot(vix, pico)
        report["energize_handshake"] = {
            **handshake,
            "before_on": before_on,
            "after_on": after_on,
            "handshake_s": t1 - t0,
            "after_on_pico_delta_counts": int(after_on["pico_encoder_position"]) - int(ref["pico_encoder_position"]),
            "after_on_vix_delta_counts": None,
        }
        report["kick_window"] = sample_window(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            name="post_enable_kick_window_zero_gains",
            duration_s=args.kick_window_s,
            interval_s=args.sample_interval_s,
            reference=ref,
            min_samples=args.min_samples,
            abort_from_reference_counts=args.max_allow_kick_counts,
            abort_within_window_counts=None,
        )
        if report["kick_window"].get("hard_stop"):
            raise CommissionAbort(f"Hard stop during bounded kick window: {report['kick_window'].get('hard_stop')}")

        # Define the ViX's current energized location as local zero after the kick.
        report["post_kick_vix_zero"] = vix_post_kick_zero(vix, log)
        post_zero_ref = snapshot(vix, pico)
        report["reference_after_post_kick_vix_zero"] = post_zero_ref

        report["post_kick_zero_gains_quiet"] = sample_window(
            vix=vix, pico=pico, log=log, run_dir=run_dir,
            name="post_kick_zero_gains_quiet_hold",
            duration_s=args.post_kick_quiet_s,
            interval_s=args.sample_interval_s,
            reference=post_zero_ref,
            min_samples=args.min_samples,
            abort_from_reference_counts=None,
            abort_within_window_counts=args.hold_abort_span_counts,
        )

        hold_results: list[dict[str, Any]] = []
        for label, gains, cl_percent in HOLD_CANDIDATES:
            if STOP_REQUESTED:
                break
            log.say(f"Testing already-energised hold candidate {label}: gains={gains.label()}, CL={cl_percent}%.")
            candidate: dict[str, Any] = {"label": label, "gains": asdict(gains), "cl_percent": cl_percent}
            try:
                # Re-zero ViX at current already-energised location with zero gains before each candidate.
                apply_gains_while_on(vix, ZERO_GAINS, args.kick_cl_percent, args)
                time.sleep(args.candidate_settle_before_zero_s)
                candidate["pre_candidate_vix_zero"] = vix_post_kick_zero(vix, log)
                candidate_ref = snapshot(vix, pico)
                candidate["reference"] = candidate_ref
                apply_gains_while_on(vix, gains, cl_percent, args)
                candidate["hold_summary"] = sample_window(
                    vix=vix, pico=pico, log=log, run_dir=run_dir,
                    name=f"hold_{label}",
                    duration_s=args.hold_window_s,
                    interval_s=args.sample_interval_s,
                    reference=candidate_ref,
                    min_samples=args.min_samples,
                    abort_from_reference_counts=None,
                    abort_within_window_counts=args.hold_abort_span_counts,
                )
                candidate["passes_quiet_hold_gate"] = candidate_ok(candidate["hold_summary"], args)
            except Exception as exc:
                candidate["error"] = str(exc)
                candidate["passes_quiet_hold_gate"] = False
                log.say(f"Candidate {label} stopped safely: {exc}")
                text = str(exc)
                if any(token in text for token in ("VIX_FAULT", "ENCODER_INVALID", "movement_exceeded", "pico_latch")):
                    hold_results.append(candidate)
                    break
            hold_results.append(candidate)
        report["hold_candidates"] = hold_results
        verdict = classify(report, args)
        report["verdict"] = verdict
        (run_dir / "POST_ENABLE_SETTLE_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        lines = [
            "POST-ENABLE SETTLE PROBE VERDICT",
            f"likely_blocker: {verdict.get('likely_blocker')}",
            f"enable_kick_max_abs_counts: {verdict.get('enable_kick_max_abs_counts')}",
            f"post_kick_zero_gains_span_counts: {verdict.get('post_kick_zero_gains_span_counts')}",
            f"quiet_span_gate_counts: {verdict.get('quiet_span_gate_counts')}",
            "",
            "Findings:",
            *[f"- {x}" for x in verdict.get("findings", [])],
            "",
            "Next steps:",
            *[f"- {x}" for x in verdict.get("next_steps", [])],
            "",
        ]
        (run_dir / "POST_ENABLE_SETTLE_VERDICT.txt").write_text("\n".join(lines), encoding="utf-8")
        log.say("\n" + "\n".join(lines))
        code = 0
    except Exception as exc:
        report["abort"] = str(exc)
        if "verdict" not in report:
            report["verdict"] = {
                "likely_blocker": "aborted_before_verdict",
                "abort": str(exc),
                "findings": [
                    "The probe stopped before final classification; do not treat this run as a pass.",
                    "Use the partial windows in POST_ENABLE_SETTLE_SUMMARY.json to diagnose the stop reason.",
                ],
                "next_steps": [
                    "Run the fixed Pico-fast post-enable probe or inspect serial/power state before motion validation.",
                ],
            }
        with contextlib.suppress(Exception):
            (run_dir / "POST_ENABLE_SETTLE_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            verdict = report["verdict"]
            lines = [
                "POST-ENABLE SETTLE PROBE VERDICT",
                f"likely_blocker: {verdict.get('likely_blocker')}",
                f"abort: {verdict.get('abort')}",
                "",
                "Findings:",
                *[f"- {x}" for x in verdict.get("findings", [])],
                "",
                "Next steps:",
                *[f"- {x}" for x in verdict.get("next_steps", [])],
                "",
            ]
            (run_dir / "POST_ENABLE_SETTLE_VERDICT.txt").write_text("\n".join(lines), encoding="utf-8")
        log.say(f"\nABORT: Post-enable settle probe stopped safely: {exc}")
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
        bundle_path: Path | None = None
        bundle_error: str | None = None
        try:
            bundle_path = bundle_run_dir(run_dir)
            report["evidence_bundle"] = str(bundle_path)
            (run_dir / "POST_ENABLE_SETTLE_SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            log.say(f"Evidence bundle: {bundle_path}")
        except Exception as exc:
            bundle_error = str(exc)
            report["evidence_bundle_error"] = bundle_error
            log.say(f"Evidence bundle creation failed: {bundle_error}")
        log.close()
        # Recreate the bundle once more after the final log line and any summary
        # bundle path update, so the .zip contains the final LOG.txt as well.
        with contextlib.suppress(Exception):
            bundle_run_dir(run_dir)
    return code


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V4.69 post-enable settle discriminator; relaxed pre-zero settle; Pico-fast sampling; no commanded moves; auto-bundles evidence")
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
    p.add_argument("--quiet-span-counts", type=int, default=20)
    p.add_argument("--off-baseline-s", type=float, default=5.0)
    p.add_argument("--kick-window-s", type=float, default=3.0)
    p.add_argument("--post-kick-quiet-s", type=float, default=5.0)
    p.add_argument("--hold-window-s", type=float, default=6.0)
    p.add_argument("--candidate-settle-before-zero-s", type=float, default=0.5)
    p.add_argument("--sample-interval-s", type=float, default=0.05)
    p.add_argument("--min-samples", type=int, default=20)
    p.add_argument("--local-zero-settle-counts", type=int, default=20)
    p.add_argument("--local-zero-window-s", type=float, default=0.25)
    p.add_argument("--local-zero-max-wait-s", type=float, default=20.0)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(run_probe(parse_args()))
