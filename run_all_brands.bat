@echo off
setlocal enabledelayedexpansion

rem —------ user-specific creds/env file —------
set ENV_FILE=%~dp0creds.env

if not exist "%ENV_FILE%" (
    echo [ERROR] %ENV_FILE% not found & exit /b 1
)

for /f "usebackq tokens=1* delims==" %%A in ("%ENV_FILE%") do set "%%A=%%B"

rem --- fallbacks if a key is missing (optional) ---
if not defined FB_SEARCH_TERM  set FB_SEARCH_TERM=Toyota Prius
if not defined RETRIES set RETRIES=2
if not defined WAIT    set WAIT=20
if not defined SCROLLS set SCROLLS=5
if not defined USER_CITY set USER_CITY=Chicago, IL

rem —--- resolve repo root regardless of location —---
set REPO=%~dp0
set PY="%REPO%env\Scripts\python.exe"
set SCRIPT="%REPO%run_pipeline.py"

rem Prefer comma-separated list for multi-word terms; if no comma, treat as a single term
set "__LIST=%FB_SEARCH_TERM%"
set "__REMAINDER=%__LIST%"

if not "%__LIST:%=_%"=="%__LIST%" goto :_loop_by_comma

rem No commas -> single run with entire string
echo ==== %__LIST% ====
%PY% %SCRIPT% --retries %RETRIES% --wait %WAIT% --scrolls %SCROLLS% --search "%__LIST%" --user-city "%USER_CITY%"
goto :eof

:_loop_by_comma
:again
for /f "tokens=1* delims=," %%A in ("%__REMAINDER%") do (
    set "__ITEM=%%~A"
)
setlocal enabledelayedexpansion
set "__ITEM=!__ITEM:~0!"
for /f "tokens=* delims= " %%Z in ("!__ITEM!") do set "__ITEM=%%~Z"
endlocal & set "__ITEM=%__ITEM%"
if not "%__ITEM%"=="" (
    echo ==== %__ITEM% ====
    %PY% %SCRIPT% --retries %RETRIES% --wait %WAIT% --scrolls %SCROLLS% --search "%__ITEM%" --user-city "%USER_CITY%"
)
for /f "tokens=1* delims=," %%A in ("%__REMAINDER%") do (
    set "__REMAINDER=%%~B"
)
if defined __REMAINDER goto again

exit /b 0
