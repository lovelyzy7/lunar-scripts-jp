#!/usr/bin/env bash
# lunar-scripts-jp 环境初始化（venv）
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
$PY -m venv .venv
. .venv/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "[ok] venv 就绪: $(pwd)/.venv"
echo "启用: source .venv/bin/activate"
echo "APK 工具: python android/build_apk.py tools   (需要 java)"
