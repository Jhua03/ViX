
"""Deterministic PlatformIO front-end for the official Pico SDK build.

Safety-related runtime firmware is not modified here. This wrapper fixes two
host-build problems observed on Fedora:

* future-dated ZIP-extracted inputs causing endless CMake regeneration;
* Pico SDK 2.3.x Findpioasm.cmake creating a BUILD_ALWAYS ExternalProject.

A matching pioasm is built once in a user cache and injected as an imported
CMake target. The main Ninja graph is verified to be a true no-op after each
successful build before a UF2 is accepted.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import sys

Import("env")  # type: ignore[name-defined]

# PlatformIO/SCons executes extra_scripts with exec(), where __file__ is not
# guaranteed to exist. Derive every project-local path from PlatformIO's own
# absolute $PROJECT_DIR instead. This is stable in VS Code task, CLI, and
# SCons-script contexts.
PROJECT_DIR = Path(env.subst("$PROJECT_DIR")).resolve()
SCRIPT_DIR = PROJECT_DIR / "extra_scripts"
if not SCRIPT_DIR.is_dir():
    raise RuntimeError(f"PlatformIO extra_scripts directory is missing: {SCRIPT_DIR}")
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from normalize_cmake_timestamp import normalize_future_inputs

BUILD_DIR = PROJECT_DIR / env.GetProjectOption("custom_build_dir")
BOARD = env.GetProjectOption("custom_pico_board")
UF2_NAME = env.GetProjectOption("custom_firmware_name")
TARGET_NAME = "vix_base_pico2_controller"
UF2_PATH = BUILD_DIR / UF2_NAME
ELF_PATH = BUILD_DIR / f"{TARGET_NAME}.elf"
PICO_FAMILY = "rp2350-arm-s"
MIN_OUTPUT_SIZE = 1024


def _run(command, *, cwd=PROJECT_DIR, capture=False):
    printable = " ".join(str(part) for part in command)
    print(f"\n[pico-sdk] {printable}")
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture,
    )


def _require_tool(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise RuntimeError(f"Required tool {name!r} was not found in PATH.")
    return value


def _pico_sdk_path() -> Path:
    configured = os.environ.get("PICO_SDK_PATH", "").strip()
    candidate = Path(configured).expanduser() if configured else Path.home() / "pico-sdk"
    if not (candidate / "external" / "pico_sdk_import.cmake").is_file():
        raise RuntimeError(
            "PICO_SDK_PATH is not valid. Set it before building:\n"
            "  export PICO_SDK_PATH=$HOME/pico-sdk"
        )
    return candidate.resolve()


def _sdk_version(sdk: Path) -> str:
    text = (sdk / "pico_sdk_version.cmake").read_text(encoding="utf-8")
    values = {}
    for key in ("MAJOR", "MINOR", "REVISION"):
        match = re.search(
            rf"set\(PICO_SDK_VERSION_{key}\s+([0-9]+)\)", text
        )
        if not match:
            raise RuntimeError(f"Cannot determine Pico SDK {key.lower()} version.")
        values[key] = match.group(1)
    return f"{values['MAJOR']}.{values['MINOR']}.{values['REVISION']}"


def _pioasm_source_fingerprint(sdk: Path, version: str) -> str:
    digest = hashlib.sha256()
    digest.update(str(sdk).encode())
    digest.update(version.encode())
    source = sdk / "tools" / "pioasm"
    if not (source / "CMakeLists.txt").is_file():
        raise RuntimeError(f"Pico SDK pioasm source is missing: {source}")
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _pioasm_cache_root() -> Path:
    override = os.environ.get("VIX_PICO_HOST_TOOLS_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".cache" / "vix-pico-host-tools").resolve()


def _verify_pioasm(executable: Path, version: str) -> bool:
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return False
    result = subprocess.run(
        [str(executable), "--version"],
        text=True,
        capture_output=True,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0 and f"pioasm version: {version}" in output


def _ensure_pioasm(sdk: Path, cmake: str, ninja: str) -> Path:
    version = _sdk_version(sdk)
    fingerprint = _pioasm_source_fingerprint(sdk, version)
    root = _pioasm_cache_root() / "pioasm" / f"{version}-{fingerprint}"
    build = root / "build"
    install = root / "install"
    executable = install / "pioasm" / "pioasm"

    if _verify_pioasm(executable, version):
        print(f"[pico-sdk] Reusing verified pioasm {version}: {executable}")
        return executable

    print(f"[pico-sdk] Building matching host pioasm {version} once.")
    shutil.rmtree(root, ignore_errors=True)
    build.mkdir(parents=True, exist_ok=True)
    _run([
        cmake,
        "-S", sdk / "tools" / "pioasm",
        "-B", build,
        "-G", "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DPIOASM_VERSION_STRING={version}",
        "-DPIOASM_FLAT_INSTALL=1",
        f"-DCMAKE_INSTALL_PREFIX={install}",
    ])
    _run([cmake, "--build", build, "--parallel"])
    _run([cmake, "--install", build])
    if not _verify_pioasm(executable, version):
        raise RuntimeError(
            f"Built pioasm did not report the expected SDK version {version}: "
            f"{executable}"
        )
    return executable


def _cache_value(cache: Path, key: str) -> str | None:
    if not cache.is_file():
        return None
    prefix = f"{key}:"
    for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(prefix) and "=" in line:
            return line.split("=", 1)[1]
    return None


def _configuration_matches(sdk: Path, ninja: str, pioasm: Path) -> bool:
    cache = BUILD_DIR / "CMakeCache.txt"
    expected = {
        "PICO_BOARD": BOARD,
        "PICO_SDK_PATH": str(sdk),
        "PIOASM_EXECUTABLE": str(pioasm),
        "PICO_NO_PICOTOOL": "1",
        "CMAKE_MAKE_PROGRAM": ninja,
        "CMAKE_BUILD_TYPE": "Release",
    }
    return cache.is_file() and all(
        _cache_value(cache, key) == value for key, value in expected.items()
    )


def _configure(cmake: str, ninja: str, sdk: Path, pioasm: Path) -> None:
    if BUILD_DIR.exists() and not _configuration_matches(sdk, ninja, pioasm):
        print("[pico-sdk] Build configuration changed; cleaning build-pio.")
        shutil.rmtree(BUILD_DIR)
    if (BUILD_DIR / "CMakeCache.txt").is_file():
        print("[pico-sdk] Existing deterministic CMake configuration is valid.")
        return
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    _run([
        cmake,
        "-S", PROJECT_DIR,
        "-B", BUILD_DIR,
        "-G", "Ninja",
        f"-DPICO_BOARD={BOARD}",
        f"-DPICO_SDK_PATH={sdk}",
        f"-DPIOASM_EXECUTABLE={pioasm}",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DPICO_NO_PICOTOOL=1",
    ])


def _assert_no_external_pioasm() -> None:
    ninja_file = BUILD_DIR / "build.ninja"
    if not ninja_file.is_file():
        raise RuntimeError(f"Missing Ninja graph: {ninja_file}")
    text = ninja_file.read_text(encoding="utf-8", errors="replace")
    if "pioasmBuild" in text:
        raise RuntimeError(
            "The main build still contains Pico SDK's BUILD_ALWAYS "
            "pioasmBuild ExternalProject. Refusing to continue."
        )


def _assert_ninja_noop(ninja: str) -> None:
    result = subprocess.run(
        [ninja, "-C", str(BUILD_DIR), "-n"],
        text=True,
        capture_output=True,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(f"Ninja no-op verification failed:\n{output}")
    if "no work to do" not in output.lower():
        explain = subprocess.run(
            [ninja, "-C", str(BUILD_DIR), "-n", "-d", "explain"],
            text=True,
            capture_output=True,
        )
        details = (explain.stdout + explain.stderr).strip()
        raise RuntimeError(
            "The completed firmware graph is not a true no-op. "
            "Refusing to create/upload a UF2.\n" + details
        )
    print("[pico-sdk] Incremental graph verified: ninja: no work to do.")


def _find_picotool() -> str:
    override = os.environ.get("PICOTOOL_EXECUTABLE", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    direct = shutil.which("picotool")
    if direct:
        candidates.append(Path(direct))
    candidates.extend([
        Path.home() / ".local" / "picotool-2.3.0" / "bin" / "picotool",
        Path.home() / ".local" / "bin" / "picotool",
    ])
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            result = subprocess.run(
                [str(candidate), "version"], text=True, capture_output=True
            )
            if result.returncode == 0:
                print(f"[pico-sdk] Using external picotool: {candidate}")
                return str(candidate)
    raise RuntimeError(
        "A working picotool executable is required for ELF-to-UF2 conversion.\n"
        "Set PICOTOOL_EXECUTABLE or install it at:\n"
        "  ~/.local/picotool-2.3.0/bin/picotool"
    )


def _convert_elf_to_uf2() -> None:
    if not ELF_PATH.is_file() or ELF_PATH.stat().st_size < MIN_OUTPUT_SIZE:
        raise RuntimeError(f"ELF build output is missing or too small: {ELF_PATH}")
    if (
        UF2_PATH.is_file()
        and UF2_PATH.stat().st_size >= MIN_OUTPUT_SIZE
        and UF2_PATH.stat().st_mtime_ns >= ELF_PATH.stat().st_mtime_ns
    ):
        print(f"[pico-sdk] UF2 is already up to date: {UF2_PATH}")
        return
    picotool = _find_picotool()
    UF2_PATH.unlink(missing_ok=True)
    _run([
        picotool,
        "uf2", "convert", "--quiet",
        ELF_PATH,
        UF2_PATH,
        "--family", PICO_FAMILY,
        "--abs-block",
    ])
    if not UF2_PATH.is_file() or UF2_PATH.stat().st_size < MIN_OUTPUT_SIZE:
        raise RuntimeError(f"UF2 conversion failed or output is invalid: {UF2_PATH}")
    print(f"\n[pico-sdk] UF2 ready: {UF2_PATH}")


def sdk_build_callback(*_args, **_kwargs):
    changed = normalize_future_inputs(PROJECT_DIR)
    if changed:
        print("[timestamp-guard] Corrected future-dated project files:")
        for path in changed:
            print(f"  {path}")
    else:
        print("[timestamp-guard] Project timestamps are sane.")

    _require_tool("arm-none-eabi-gcc")
    cmake = _require_tool("cmake")
    ninja = _require_tool("ninja")
    sdk = _pico_sdk_path()
    pioasm = _ensure_pioasm(sdk, cmake, ninja)
    _configure(cmake, ninja, sdk, pioasm)
    _assert_no_external_pioasm()
    _run([cmake, "--build", BUILD_DIR, "--parallel"])
    _assert_no_external_pioasm()
    _assert_ninja_noop(ninja)
    _convert_elf_to_uf2()


def _mounted_bootsel_volume():
    user = os.environ.get("USER", "")
    roots = [Path("/run/media") / user, Path("/media") / user, Path("/Volumes")]
    names = {"RP2350", "RPI-RP2"}
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and child.name.upper() in names:
                return child
    return None


def _picotool_supports_usb_load(picotool: str) -> bool:
    result = subprocess.run(
        [picotool, "help", "load"], text=True, capture_output=True
    )
    return result.returncode == 0 and "load" in (result.stdout + result.stderr).lower()


def sdk_upload_callback(*_args, **_kwargs):
    sdk_build_callback()
    volume = _mounted_bootsel_volume()
    if volume is not None:
        destination = volume / UF2_PATH.name
        print(f"\n[pico-sdk] Copying UF2 to BOOTSEL volume: {destination}")
        shutil.copy2(UF2_PATH, destination)
        print("[pico-sdk] Upload complete. The Pico should reboot automatically.")
        return
    picotool = _find_picotool()
    if _picotool_supports_usb_load(picotool):
        print("\n[pico-sdk] No BOOTSEL volume found; trying USB picotool load.")
        _run([picotool, "load", "-f", "-x", UF2_PATH])
        return
    raise RuntimeError(
        "No mounted RP2350/RPI-RP2 BOOTSEL volume was found, and picotool "
        "has no USB load support. Hold BOOTSEL while plugging in the Pico, "
        "wait for RP2350 to mount, and run SDK Upload again. The verified "
        f"UF2 is at {UF2_PATH}."
    )


def sdk_clean_callback(*_args, **_kwargs):
    if BUILD_DIR.exists():
        print(f"[pico-sdk] Removing {BUILD_DIR}")
        shutil.rmtree(BUILD_DIR)


env.AddCustomTarget(
    name="sdk_build",
    dependencies=None,
    actions=sdk_build_callback,
    title="SDK Build",
    description="Build, prove Ninja no-op, and create a verified Pico 2 UF2",
)
env.AddCustomTarget(
    name="sdk_upload",
    dependencies=None,
    actions=sdk_upload_callback,
    title="SDK Upload",
    description="Build/verify and upload the Pico 2 UF2",
)
env.AddCustomTarget(
    name="sdk_clean",
    dependencies=None,
    actions=sdk_clean_callback,
    title="SDK Clean",
    description="Remove only the firmware build-pio directory",
)
