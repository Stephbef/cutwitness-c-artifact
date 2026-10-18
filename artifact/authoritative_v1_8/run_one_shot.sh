#!/usr/bin/env bash
# CutWitness-C one-shot campaign entry point. Fail-closed; safe to re-run for resume (same run directory).
# Usage: ./run_one_shot.sh [run_dir]          (default: runs/cutwitness_c)
# The Mobility Database refresh token must be supplied as environment variable CUTWITNESS_W1_TOKEN.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
RUN_DIR="${1:-runs/cutwitness_c}"
CONFIG="campaign/FROZEN_CAMPAIGN.yaml"
fail() { echo "ONE_SHOT_PREFLIGHT_FAILED: $*" >&2; mkdir -p "$RUN_DIR"; printf '{"verdict":"NOT_STARTED_OPERATIONAL","reason":"%s"}\n' "$*" > "$RUN_DIR/FINAL_VERDICT.json"; exit 3; }

# 1-2. package and pinned identities: every file must match the pre-execution manifest
python3 tools/verify_package.py || fail "package integrity (SHA-256 manifest) failed"
# 3. interpreter / platform required by the vendored wheels
python3 -c 'import sys,platform; assert sys.version_info[:2]==(3,12) and platform.machine()=="x86_64" and platform.system()=="Linux"' \
  || fail "Python 3.12 on Linux x86_64 is required by the vendored wheelhouse"
# 4-6. offline, hash-checked environment from the vendored wheelhouse only
if [ ! -x .venv/bin/python ]; then python3 -m venv --without-pip .venv || fail "cannot create venv"; fi
PIPWHL="$(ls vendor/wheels/pip-*.whl)"
.venv/bin/python "$PIPWHL/pip" install --no-index --find-links vendor/wheels --require-hashes --only-binary=:all: \
  --disable-pip-version-check --quiet -r vendor/requirements.lock || fail "offline hash-checked install failed"
.venv/bin/python -c "import duckdb, psycopg; assert duckdb.__version__=='1.1.3' and psycopg.__version__=='3.2.10'" \
  || fail "dependency check failed"
# 7. security preflight (no secrets, keys, private paths, secret Docker layers in the package)
.venv/bin/python -m cutwitness.security . >/dev/null || fail "security preflight found secrets or private data"
[ -n "${CUTWITNESS_W1_TOKEN:-}" ] || fail "CUTWITNESS_W1_TOKEN is not set"
command -v docker >/dev/null || fail "docker CLI not found"
# 8-13. controller: resource/duration preflight (45-day gate, no bypass), S4/S5 conformance gates, campaign,
#        parent journal, resume without duplicating committed units
exec .venv/bin/python -m cutwitness.one_shot --config "$CONFIG" --run-dir "$RUN_DIR"
