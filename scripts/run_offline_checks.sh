#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
python3 -m py_compile host/vix.py
python3 tests/test_cli_structure.py
python3 tests/check_repo.py

# Re-run the original comprehensive v4.78 offline commissioning suite unchanged.
(
  cd archive/commissioning-history/v4_78
  bash scripts/run_offline_checks.sh
)

echo
echo "Cleaned repository offline checks PASS."
