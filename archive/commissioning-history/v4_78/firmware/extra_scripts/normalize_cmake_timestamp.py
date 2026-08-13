
#!/usr/bin/env python3
"""Normalize only future-dated project inputs before CMake/Ninja runs.

ZIP timestamps do not carry a timezone. A bundle created in UTC and unpacked
on a UTC-07 host can therefore appear several hours in the future. Ninja then
keeps rebuilding build.ninja because CMake cannot write an output newer than
the future-dated input.

This utility changes timestamps only; it never changes file contents.
Generated/build directories are excluded.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import time
from typing import Iterable

EXCLUDED_DIRS = {
    '.git', '.pio', '.vscode', '__pycache__',
    'build', 'build-pio', '.host-tools',
}
INPUT_SUFFIXES = {
    '.c', '.cc', '.cmake', '.cpp', '.cxx', '.h', '.hh', '.hpp',
    '.ini', '.pio', '.py', '.s', '.S', '.sh', '.txt',
}
INPUT_NAMES = {'CMakeLists.txt', 'platformio.ini'}


def iter_project_inputs(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for current, directories, files in os.walk(root):
        directories[:] = [name for name in directories if name not in EXCLUDED_DIRS]
        base = Path(current)
        for name in files:
            path = base / name
            if name in INPUT_NAMES or path.suffix in INPUT_SUFFIXES:
                yield path


def normalize_future_inputs(
    root: Path,
    *,
    now: float | None = None,
    tolerance_s: float = 2.0,
) -> list[Path]:
    if tolerance_s < 0:
        raise ValueError('tolerance_s must be non-negative')
    current = time.time() if now is None else float(now)
    replacement = current - 1.0
    changed: list[Path] = []
    for path in iter_project_inputs(root):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if stat.st_mtime > current + tolerance_s:
            os.utime(path, (stat.st_atime, replacement), follow_symlinks=False)
            changed.append(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--tolerance-seconds', type=float, default=2.0)
    args = parser.parse_args()
    changed = normalize_future_inputs(
        args.root,
        tolerance_s=args.tolerance_seconds,
    )
    if changed:
        print('[timestamp-guard] Normalized future-dated project inputs:')
        for path in changed:
            print(f'  {path}')
    else:
        print('[timestamp-guard] Project input timestamps are sane.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
