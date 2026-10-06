@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [!] python not found in PATH. Install Python 3.9+ first.
  pause
  exit /b 1
)
python "local\run_local.py" %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo [!] failed ^(exit code %RC%^) - see log above.
  pause
  exit /b %RC%
)
pause
