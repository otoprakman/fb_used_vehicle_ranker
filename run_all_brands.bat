@echo off
setlocal enabledelayedexpansion

rem —------ user-specific creds/env file —------
set ENV_FILE=%~dp0creds.env

if not exist "%ENV_FILE%" (
    echo [ERROR] %ENV_FILE% not found & exit /b 1
)

for /f "usebackq tokens=1* delims==" %%A in ("%ENV_FILE%") do set "%%A=%%B"

rem --- fallbacks if a key is missing (optional) ---
if not defined BRANDS  set BRANDS="Toyota Prius"
if not defined RETRIES set RETRIES=2
if not defined WAIT    set WAIT=20
if not defined SCROLLS set SCROLLS=5

rem —--- resolve repo root regardless of location —---
set REPO=%~dp0
set PY="%REPO%env\Scripts\python.exe"
set SCRIPT="%REPO%run_pipeline.py"

for %%B in (%BRANDS%) do (
    echo ==== %%~B ====
    %PY% %SCRIPT% --retries %RETRIES% --wait %WAIT% --scrolls %SCROLLS% --search "%%~B"
)

exit /b 0
