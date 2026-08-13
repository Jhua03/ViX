#!/usr/bin/env python3
"""Small, safety-oriented ViX250AH/ViX500AH + Pico 2 host utility.

The ViX is configured/statused over X3 RS-232. Motion is sent only through the
Pico 2, which generates differential STEP/DIR for X4 and supervises encoder,
limits, fault, E-stop and the hardware energise input.

This tool intentionally does not issue ViX internal motion commands and never
saves volatile setup to the drive with SV.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    import serial
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pyserial is required: python -m pip install -r requirements.txt") from exc


class VixError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mx80lProfile:
    counts_per_mm: int = 100_000
    gf: float = 0.0
    gi: float = 0.2
    gp: float = 2.0
    gv: float = 1.5
    ft: int = 0
    cl: int = 2
    pc: int = 100
    tl: int = 13_000
    im: int = 1
    iw: int = 1_000


MX80L = Mx80lProfile()


class Pico:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.ser = serial.Serial(
            port,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.25,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self.lock = threading.Lock()
        self.ser.reset_input_buffer()

    def close(self) -> None:
        self.ser.close()

    def command(self, text: str, timeout: float = 2.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self.lock:
            self.ser.write((text.rstrip("\r\n") + "\n").encode("ascii"))
            self.ser.flush()
            while time.monotonic() < deadline:
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if not obj.get("ok", False):
                    raise VixError(f"Pico rejected {text!r}: {obj.get('error', obj)}")
                return obj
        raise VixError(f"Pico timeout waiting for response to {text!r}")


class Vix:
    def __init__(self, port: str, axis: int = 1, baud: int = 9600) -> None:
        self.axis = axis
        self.ser = serial.Serial(
            port,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.05,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self.ser.reset_input_buffer()

    def close(self) -> None:
        self.ser.close()

    def command(self, body: str, timeout: float = 1.5) -> str:
        text = f"{self.axis}{body}\r"
        self.ser.write(text.encode("ascii"))
        self.ser.flush()
        deadline = time.monotonic() + timeout
        chunks: list[bytes] = []
        last_rx: float | None = None
        while time.monotonic() < deadline:
            waiting = self.ser.in_waiting
            data = self.ser.read(waiting or 1)
            if data:
                chunks.append(data)
                last_rx = time.monotonic()
                continue
            if last_rx is not None and time.monotonic() - last_rx >= 0.08:
                break
        raw = b"".join(chunks).decode("ascii", errors="replace")
        # ViX can echo commands. A literal *E report is a command rejection.
        if any(line.strip() == "*E" for line in raw.replace("\r", "\n").split("\n")):
            raise VixError(f"ViX rejected {body!r}: {raw!r}")
        return raw

    def report(self, body: str, attempts: int = 3) -> str:
        for attempt in range(1, attempts + 1):
            raw = self.command(body)
            reports = [
                line.strip()[1:]
                for line in raw.replace("\r", "\n").split("\n")
                if line.strip().startswith("*") and line.strip() != "*E"
            ]
            if reports:
                return reports[-1]
            if attempt < attempts:
                time.sleep(0.2)
        raise VixError(f"No report payload for {self.axis}{body}")


class Heartbeat:
    def __init__(self, pico: Pico, period_s: float = 0.10) -> None:
        self.pico = pico
        self.period_s = period_s
        self.stop_evt = threading.Event()
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="pico-heartbeat", daemon=True)

    def _run(self) -> None:
        while not self.stop_evt.wait(self.period_s):
            try:
                self.pico.command("HB", timeout=max(0.4, self.period_s * 3))
            except BaseException as exc:  # save error; caller handles safe stop
                self.error = exc
                self.stop_evt.set()
                return

    def start(self) -> None:
        # Send one immediately so the watchdog never waits for the first period.
        self.pico.command("HB")
        self.thread.start()

    def stop(self) -> None:
        self.stop_evt.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)


def safe_stop(pico: Pico | None, vix: Vix | None) -> None:
    """Best-effort stop. Each command is independent so one failure does not block the rest."""
    if pico is not None:
        for cmd in ("ABORT", "ENABLE 0", "DISARM"):
            try:
                pico.command(cmd, timeout=0.8)
            except Exception:
                pass
    if vix is not None:
        try:
            vix.command("OFF", timeout=0.8)
        except Exception:
            pass


def configure_vix(vix: Vix, profile: str) -> None:
    # All setup is volatile. Do not add SV here.
    commands = ["OFF", "MP", "W(ES,0)", "W(EI,0)", "W(EO,2)"]
    if profile == "mx80l-10nm":
        commands += [
            f"W(CL,{MX80L.cl})",
            f"W(PC,{MX80L.pc})",
            f"W(TL,{MX80L.tl})",
            f"W(IM,{MX80L.im})",
            f"W(IW,{MX80L.iw})",
            f"GAINS({MX80L.gf:g},{MX80L.gi:g},{MX80L.gp:g},{MX80L.gv:g},{MX80L.ft})",
        ]
    for body in commands:
        vix.command(body)


def verify_vix_io(vix: Vix) -> dict[str, str]:
    expected = {"R(M)": "MP", "R(ES)": "0", "R(EI)": "0", "R(EO)": "2"}
    actual: dict[str, str] = {}
    for cmd, want in expected.items():
        got = vix.report(cmd).lstrip("*")
        actual[cmd] = got
        if got != want:
            raise VixError(f"ViX verification failed: {cmd} returned {got!r}, expected {want!r}")
    return actual


def configure_pico(
    pico: Pico,
    *,
    estop_required: bool,
    has_negative_limit: bool,
    soft_min: int,
    soft_max: int,
    confirm_inputs: bool,
) -> dict[str, Any]:
    # Safe state before any configuration change.
    for cmd in ("ABORT", "ENABLE 0", "DISARM"):
        pico.command(cmd)
    cfg = {
        "LPOL": 1,
        "LNPOL": 0,
        "HPOL": 1,
        "FPOL": 1,
        "HAS_LN": 1 if has_negative_limit else 0,
        "ENCSIGN": 1,
        "DIRINV": 0,
        "ESTOPREQ": 1 if estop_required else 0,
        "SOFTMIN": soft_min,
        "SOFTMAX": soft_max,
        "FERRMAX": 5000,
        "WATCHDOG_MS": 750,
        "CONFIRM_INPUTS": 1 if confirm_inputs else 0,
    }
    for key, value in cfg.items():
        pico.command(f"CONFIG {key} {value}")
    return pico.command("CONFIG SHOW")


def print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def open_ports(args: argparse.Namespace) -> tuple[Pico, Vix]:
    pico = Pico(args.pico_port, args.pico_baud)
    try:
        vix = Vix(args.vix_port, args.axis, args.vix_baud)
    except Exception:
        pico.close()
        raise
    return pico, vix


def cmd_info(args: argparse.Namespace) -> int:
    pico, vix = open_ports(args)
    try:
        result = {
            "pico": pico.command("INFO"),
            "pico_status": pico.command("STATUS"),
            "vix_revision": vix.report("R(RV)"),
            "vix_status_raw": vix.command("STATUS"),
        }
        print_json(result)
        return 0
    finally:
        pico.close(); vix.close()


def cmd_status(args: argparse.Namespace) -> int:
    pico, vix = open_ports(args)
    try:
        print_json({
            "pico": pico.command("STATUS"),
            "vix_drive_fault": vix.report("R(DF)"),
            "vix_status_raw": vix.command("STATUS"),
        })
        return 0
    finally:
        pico.close(); vix.close()


def cmd_configure(args: argparse.Namespace) -> int:
    pico, vix = open_ports(args)
    try:
        safe_stop(pico, vix)
        configure_vix(vix, args.profile)
        verification = verify_vix_io(vix)
        pico_cfg = configure_pico(
            pico,
            estop_required=not args.bench_no_estop,
            has_negative_limit=args.has_negative_limit,
            soft_min=args.soft_min,
            soft_max=args.soft_max,
            confirm_inputs=args.confirm_inputs,
        )
        print_json({"vix_verified": verification, "pico": pico_cfg})
        print("Configuration applied VOLATILELY. Drive remains OFF and Pico remains disarmed.")
        return 0
    finally:
        safe_stop(pico, vix)
        pico.close(); vix.close()


def wait_move(pico: Pico, move_id: int, timeout_s: float, hb: Heartbeat) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if hb.error:
            raise VixError(f"Heartbeat failed: {hb.error}")
        status = pico.command("STATUS")
        if status.get("latched"):
            raise VixError(f"Pico safety latch: {status.get('latch')}")
        if status.get("motion") == "IDLE" and status.get("move_completed_id") == move_id:
            return status
        time.sleep(0.05)
    raise VixError("Timed out waiting for motion completion")


def jog_transaction(args: argparse.Namespace) -> dict[str, Any]:
    if not args.i_understand:
        raise VixError("jog requires --i-understand because it energizes and moves the axis")
    if not args.confirm_inputs:
        raise VixError("jog requires --confirm-inputs after you have verified input polarities")
    if args.profile != "mx80l-10nm":
        raise VixError("jog currently requires --profile mx80l-10nm; add and validate a motor-specific tuning profile before using another motor")

    if (args.counts is None) == (args.um is None):
        raise VixError("choose exactly one of --counts or --um")
    delta = args.counts if args.counts is not None else round(args.um * MX80L.counts_per_mm / 1000.0)
    if delta == 0:
        raise VixError("requested move rounds to zero counts")

    pico, vix = open_ports(args)
    hb: Heartbeat | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    try:
        safe_stop(pico, vix)
        configure_vix(vix, args.profile)
        verify_vix_io(vix)
        configure_pico(
            pico,
            estop_required=not args.bench_no_estop,
            has_negative_limit=args.has_negative_limit,
            soft_min=args.soft_min,
            soft_max=args.soft_max,
            confirm_inputs=True,
        )
        pico.command("CLEAR")
        pico.command("DIAG CLEAR")
        pico.command("ZERO")
        pico.command("ARM I_UNDERSTAND")

        hb = Heartbeat(pico)
        hb.start()
        pico.command("ENABLE 1")
        time.sleep(0.05)
        vix.command("ON")
        time.sleep(args.pull_in_s)

        before = pico.command("STATUS")
        if before.get("latched") or before.get("fault_active"):
            raise VixError(f"unsafe pre-move status: {before}")
        move_id = int(time.monotonic_ns() & 0x7FFFFFFF) or 1
        pico.command(f"MOVE {delta} {args.rate} {args.accel} {move_id}")
        completed = wait_move(pico, move_id, args.timeout, hb)
        time.sleep(args.settle_s)
        after = pico.command("STATUS")
        if after.get("encoder_invalid", 0) != before.get("encoder_invalid", 0):
            raise VixError("encoder_invalid increased during movement")
        return {
            "move_id": move_id,
            "commanded_counts": delta,
            "commanded_um": delta * 1000.0 / MX80L.counts_per_mm,
            "before": before,
            "completed": completed,
            "after": after,
            "measured_counts": after.get("encoder_position", 0) - before.get("encoder_position", 0),
        }
    finally:
        if hb is not None:
            hb.stop()
        safe_stop(pico, vix)
        pico.close(); vix.close()


def cmd_jog(args: argparse.Namespace) -> int:
    print_json(jog_transaction(args))
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    pico, vix = open_ports(args)
    try:
        safe_stop(pico, vix)
        print("Safe-stop attempted: Pico ABORT -> ENABLE 0 -> DISARM, then ViX OFF.")
        return 0
    finally:
        pico.close(); vix.close()


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pico-port", default="/dev/ttyACM0", help="Pico 2 USB CDC port")
    parser.add_argument("--vix-port", default="/dev/ttyUSB0", help="USB-to-RS232 port connected to ViX X3")
    parser.add_argument("--pico-baud", type=int, default=115200)
    parser.add_argument("--vix-baud", type=int, default=9600)
    parser.add_argument("--axis", type=int, default=1, help="ViX software axis address (factory default is normally 1)")


def add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", choices=("io-only", "mx80l-10nm"), default="io-only")
    parser.add_argument("--bench-no-estop", action="store_true", help="allow attended bench testing without the final NC E-stop auxiliary input")
    parser.add_argument("--has-negative-limit", action="store_true")
    parser.add_argument("--soft-min", type=int, default=-50_000)
    parser.add_argument("--soft-max", type=int, default=50_000)
    parser.add_argument("--confirm-inputs", action="store_true", help="assert that limit/home/fault/E-stop polarities were physically verified")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="read Pico identity/status and ViX revision/status")
    add_common(p); p.set_defaults(func=cmd_info)

    p = sub.add_parser("status", help="read current Pico status and ViX drive fault/status")
    add_common(p); p.set_defaults(func=cmd_status)

    p = sub.add_parser("configure", help="apply volatile X4/Pico setup while leaving the drive disabled")
    add_common(p); add_config_args(p); p.set_defaults(func=cmd_configure)

    p = sub.add_parser("jog", help="run one complete enable -> move -> safe-disable transaction")
    add_common(p); add_config_args(p)
    p.set_defaults(profile="mx80l-10nm")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--counts", type=int)
    group.add_argument("--um", type=float)
    p.add_argument("--rate", type=int, default=100, help="Pico counts/s")
    p.add_argument("--accel", type=int, default=5000, help="Pico counts/s^2")
    p.add_argument("--pull-in-s", type=float, default=2.0)
    p.add_argument("--settle-s", type=float, default=0.75)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--i-understand", action="store_true")
    p.set_defaults(func=cmd_jog)

    p = sub.add_parser("disable", help="best-effort safe shutdown")
    add_common(p); p.set_defaults(func=cmd_disable)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (VixError, serial.SerialException, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
