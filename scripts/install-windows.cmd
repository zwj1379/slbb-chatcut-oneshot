@echo off
chcp 65001 >nul
cd /d "%~dp0.."

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py"
)
if not defined PY (
  where python3 >nul 2>nul && set "PY=python3"
)

if not defined PY (
  echo Python 3 not found.
  echo Install it from https://www.python.org/downloads/ and re-run this file.
  pause
  exit /b 1
)

%PY% scripts\ensure-chatcut.py
echo.
pause
