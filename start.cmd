@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe check_source.py --files-only
if errorlevel 1 goto fail
.venv\Scripts\python.exe main.py
if errorlevel 1 goto fail
exit /b 0
:fail
pause
exit /b 1
