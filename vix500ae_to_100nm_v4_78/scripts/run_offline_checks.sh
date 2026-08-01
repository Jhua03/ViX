#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Keep generated Python bytecode outside the verified source tree. This makes
# repeated checks deterministic and prevents __pycache__ files from becoming
# accidental package inputs.
PYCACHE_ROOT="$(mktemp -d)"
trap 'rm -rf "$PYCACHE_ROOT"' EXIT
export PYTHONPYCACHEPREFIX="$PYCACHE_ROOT"

if [[ -f "$ROOT/SHA256SUMS" ]]; then
  (
    cd "$ROOT"
    sha256sum --check --quiet SHA256SUMS
  )
fi

python3 -m py_compile \
  "$ROOT/host/vix100nm_commission.py" \
  "$ROOT/host/vix_hold_noise_probe.py" \
  "$ROOT/host/vix_enable_kick_probe.py" \
  "$ROOT/host/vix_post_enable_settle_probe.py" \
  "$ROOT/host/vix_limit_input_isolation_probe.py" \
  "$ROOT/host/vix_focused_motion_proof.py" \
  "$ROOT/host/vix_threshold_characterization.py" \
  "$ROOT/host/vix_threshold_refinement.py" \
  "$ROOT/host/analyze_latest.py" \
  "$ROOT/firmware/extra_scripts/pico_sdk_tasks.py" \
  "$ROOT/firmware/extra_scripts/normalize_cmake_timestamp.py" \
  "$ROOT/tests/offline_test.py" \
  "$ROOT/tests/firmware_source_audit.py" \
  "$ROOT/tests/build_helper_test.py" \
  "$ROOT/tests/firmware_c_syntax_test.py"

bash -n "$ROOT"/scripts/*.sh "$ROOT/firmware/build.sh"
python3 "$ROOT/host/vix100nm_commission.py" --self-test
python3 "$ROOT/tests/offline_test.py"
python3 "$ROOT/tests/firmware_source_audit.py"
python3 "$ROOT/tests/firmware_c_syntax_test.py"
python3 "$ROOT/tests/build_helper_test.py"

echo "All offline checks PASS"
