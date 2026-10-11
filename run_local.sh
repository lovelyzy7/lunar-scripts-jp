#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
exec "$PY" local/run_local.py "$@"
