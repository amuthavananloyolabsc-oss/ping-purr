@echo off
setlocal
cd /d "%~dp0"
set "PYCMD="

where pythonw >nul 2>nul && set "PYCMD=pythonw"
if not defined PYCMD where py >nul 2>nul && set "PYCMD=py"
if not defined PYCMD where python >nul 2>nul && set "PYCMD=python"

if not defined PYCMD (
  echo "Ping & Purr needs Python 3.10 or newer."
  echo Install it from https://www.python.org/downloads/ - tick "Add to PATH" -
  echo then double-click run_windows.bat again.
  pause
  exit /b 1
)

start "" %PYCMD% pet_app.py