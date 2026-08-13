
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = ROOT / 'firmware/extra_scripts/normalize_cmake_timestamp.py'


def load_normalizer():
    spec = importlib.util.spec_from_file_location('normalizer', NORMALIZER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_timestamp_guard() -> None:
    module = load_normalizer()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        cmake = root / 'CMakeLists.txt'
        source = root / 'src/main.c'
        excluded = root / 'build-pio/generated.c'
        source.parent.mkdir()
        excluded.parent.mkdir()
        cmake.write_text('project(test)\n')
        source.write_text('int main(void){return 0;}\n')
        excluded.write_text('generated\n')
        now = time.time()
        future = now + 3600
        os.utime(cmake, (future, future))
        os.utime(source, (future, future))
        os.utime(excluded, (future, future))
        changed = module.normalize_future_inputs(root, now=now)
        assert set(changed) == {cmake, source}
        assert cmake.stat().st_mtime <= now
        assert source.stat().st_mtime <= now
        assert excluded.stat().st_mtime > now
        assert cmake.read_text() == 'project(test)\n'


def test_imported_pioasm_target_bypasses_finder() -> None:
    cmake = shutil.which('cmake')
    if not cmake:
        raise AssertionError('cmake is required for build-helper test')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fake = root / 'pioasm'
        fake.write_text('#!/bin/sh\nexit 0\n')
        fake.chmod(0o755)
        modules = root / 'modules'
        modules.mkdir()
        (modules / 'Findpioasm.cmake').write_text(
            'if(NOT TARGET pioasm)\n'
            '  message(FATAL_ERROR "finder would create ExternalProject")\n'
            'endif()\n'
            'get_target_property(PIOASM_LOCATION pioasm IMPORTED_LOCATION)\n'
            'if(NOT PIOASM_LOCATION)\n'
            '  message(FATAL_ERROR "imported pioasm has no location")\n'
            'endif()\n'
        )
        (root / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.13)\n'
            'project(imported_pioasm NONE)\n'
            f'set(CMAKE_MODULE_PATH "{modules.as_posix()}")\n'
            f'set(PIOASM_EXECUTABLE "{fake.as_posix()}")\n'
            'add_executable(pioasm IMPORTED GLOBAL)\n'
            'set_property(TARGET pioasm PROPERTY IMPORTED_LOCATION "${PIOASM_EXECUTABLE}")\n'
            'find_package(pioasm REQUIRED)\n'
        )
        result = subprocess.run(
            [cmake, '-S', root, '-B', root / 'build'],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr




def test_platformio_extra_script_without_dunder_file() -> None:
    """PlatformIO/SCons may exec extra_scripts without defining __file__."""
    script = ROOT / 'firmware/extra_scripts/pico_sdk_tasks.py'

    class FakeEnv:
        def __init__(self) -> None:
            self.targets: list[str] = []

        def subst(self, value: str) -> str:
            assert value == '$PROJECT_DIR'
            return str(ROOT / 'firmware')

        def GetProjectOption(self, key: str) -> str:
            values = {
                'custom_build_dir': 'build-pio',
                'custom_pico_board': 'pico2',
                'custom_firmware_name': 'vix_base_pico2_controller.uf2',
            }
            return values[key]

        def AddCustomTarget(self, **kwargs) -> None:
            self.targets.append(kwargs['name'])

    fake = FakeEnv()
    namespace = {
        '__name__': 'platformio_extra_script_test',
        # Deliberately omit __file__ to reproduce SCons behaviour.
        'env': fake,
        'Import': lambda name: None,
    }
    source = script.read_text(encoding='utf-8')
    exec(compile(source, str(script), 'exec'), namespace)
    assert namespace['PROJECT_DIR'] == (ROOT / 'firmware').resolve()
    assert namespace['SCRIPT_DIR'] == (ROOT / 'firmware/extra_scripts').resolve()
    assert fake.targets == ['sdk_build', 'sdk_upload', 'sdk_clean']

def main() -> int:
    test_timestamp_guard()
    print('future timestamp guard PASS')
    test_imported_pioasm_target_bypasses_finder()
    print('imported pioasm target bypass PASS')
    test_platformio_extra_script_without_dunder_file()
    print('PlatformIO no-__file__ loader PASS')
    print('build helper tests PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
