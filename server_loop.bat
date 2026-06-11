@echo off
:: SAR Redact — server mode runner with restart-on-crash.
:: Includes escalating backoff, timestamped crash log, and crash-loop detection.
:: Run start_server.bat once first so Python + dependencies are installed.
title SAR Redact Server
cd /d "%~dp0"

set PYEXE=%~dp0python-runtime\python.exe
if not exist "%PYEXE%" set PYEXE=%~dp0venv\Scripts\python.exe
if not exist "%PYEXE%" set PYEXE=python

:: Log directory
if not exist "%~dp0data\logs" mkdir "%~dp0data\logs"
set LOOP_LOG=%~dp0data\logs\server_loop.log

:: Backoff state: consecutive rapid crashes
:: A "rapid" crash is one where the server exits within 5 minutes.
:: Backoff levels: 0=5s, 1=15s, 2+=60s.
:: A counter file (.crash_count) tracks consecutive rapid crashes.
set CRASH_COUNT_FILE=%~dp0data\logs\.crash_count

:: Reset crash count on fresh start
echo 0 > "%CRASH_COUNT_FILE%"

:loop
:: Record start time for uptime detection (use a marker file timestamped at start)
set MARKER_FILE=%~dp0data\logs\.loop_start_marker
copy /y nul "%MARKER_FILE%" >nul 2>nul

echo [%date% %time%] Starting SAR Redact server...
echo [%date% %time%] Starting SAR Redact server >> "%LOOP_LOG%"

"%PYEXE%" "%~dp0serve.py"

echo.
echo [%date% %time%] Server stopped (crash or shutdown). >> "%LOOP_LOG%"

:: Check how long the server was up by comparing marker file age.
:: We use a simple heuristic: forfiles can tell us if the marker is older than
:: 5 minutes (300 seconds). If the marker is still very recent the crash was rapid.
set RAPID_CRASH=1
forfiles /p "%~dp0data\logs" /m ".loop_start_marker" /d +0 /c "cmd /c exit 0" >nul 2>nul
:: forfiles /d +0 = modified today. We need finer granularity.
:: Use a PowerShell one-liner to check age in seconds.
for /f "delims=" %%A in ('powershell -NoProfile -Command "(Get-Date) - (Get-Item \"%MARKER_FILE%\").LastWriteTime | Select-Object -ExpandProperty TotalSeconds" 2^>nul') do set UPTIME_SECS=%%A
:: Default to rapid if powershell unavailable
if not defined UPTIME_SECS set UPTIME_SECS=0
:: Round down: if uptime_secs >= 300 it was not a rapid crash
for /f "delims=." %%A in ("%UPTIME_SECS%") do set UPTIME_INT=%%A
if not defined UPTIME_INT set UPTIME_INT=0

:: Check uptime: >= 300 seconds = not a rapid crash, reset counter
if %UPTIME_INT% GEQ 300 (
    echo 0 > "%CRASH_COUNT_FILE%"
    set RAPID_CRASH=0
)

:: Read current crash count
set /a CRASH_NUM=0
for /f "usebackq tokens=*" %%A in ("%CRASH_COUNT_FILE%") do set /a CRASH_NUM=%%A 2>nul
if not defined CRASH_NUM set CRASH_NUM=0

if "%RAPID_CRASH%"=="1" (
    set /a CRASH_NUM=CRASH_NUM+1
    echo %CRASH_NUM% > "%CRASH_COUNT_FILE%"
    echo [%date% %time%] Rapid crash detected. Consecutive rapid crashes: %CRASH_NUM% >> "%LOOP_LOG%"
) else (
    set CRASH_NUM=0
    echo [%date% %time%] Clean exit after >= 5 min uptime. Resetting backoff. >> "%LOOP_LOG%"
)

:: Crash-loop detection: 5 or more consecutive rapid crashes
if %CRASH_NUM% GEQ 5 (
    echo.
    echo =========================================================================
    echo   WARNING: SAR REDACT IS CRASH-LOOPING
    echo   The server has crashed %CRASH_NUM% times rapidly in a row.
    echo   Check:  data\logs\sar-redact.log  for the error.
    echo   If a recent update caused this, consider restoring:
    echo              backup_pre_update_*
    echo   Continuing to retry regardless...
    echo =========================================================================
    echo.
    echo [%date% %time%] CRASH-LOOP WARNING: %CRASH_NUM% consecutive rapid crashes. Check sar-redact.log. Consider restoring backup_pre_update_* >> "%LOOP_LOG%"
)

:: Escalating backoff: 5s (0-1 crashes), 15s (2-3), 60s (4+)
set DELAY=5
if %CRASH_NUM% GEQ 2 set DELAY=15
if %CRASH_NUM% GEQ 4 set DELAY=60

echo [%date% %time%] Restarting in %DELAY% seconds...
echo [%date% %time%] Restarting in %DELAY% seconds >> "%LOOP_LOG%"
echo Close this window to stop SAR Redact permanently.
timeout /t %DELAY% /nobreak >nul
goto loop
