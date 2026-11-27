@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe check_source.py
if errorlevel 1 goto fail
.venv\Scripts\python.exe analysis\build_mcps.py
if errorlevel 1 goto fail
exit /b 0
:fail
pause
exit /b 1
