@echo off
rem UTF-8 console output (prevents mojibake for non-ASCII text)
chcp 65001 >nul
rem lunar-scripts-jp environment setup (venv)
rem Keep this file ASCII-only: cmd.exe decodes .bat with the OEM code page,
rem so UTF-8 Chinese text would be garbled on most Windows systems.
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
echo [ok] venv ready: %~dp0.venv
echo Activate: .venv\Scripts\activate.bat
echo APK tools: python android\build_apk.py tools   (java required)
