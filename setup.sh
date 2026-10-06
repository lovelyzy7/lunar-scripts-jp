#!/usr/bin/env bash
# lunar-scripts-jp environment setup (venv)
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
$PY -m venv .venv
. .venv/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "[ok] venv ready: $(pwd)/.venv"
echo "Activate: source .venv/bin/activate"
echo "APK tools: python android/build_apk.py tools   (java required)"
