@echo off
rem lunar-scripts-jp 环境初始化（venv）
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
echo [ok] venv 就绪: %~dp0.venv
echo 启用: .venv\Scripts\activate.bat
echo APK 工具: python android\build_apk.py tools   (需要 java)
