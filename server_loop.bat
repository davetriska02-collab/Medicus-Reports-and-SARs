@echo off
:: SAR Redact — server mode runner with restart-on-crash.
:: Run start_server.bat once first so Python + dependencies are installed.
title SAR Redact Server
cd /d "%~dp0"

set PYEXE=%~dp0python-runtime\python.exe
if not exist "%PYEXE%" set PYEXE=%~dp0venv\Scripts\python.exe
if not exist "%PYEXE%" set PYEXE=python

:loop
echo [%date% %time%] Starting SAR Redact server...
"%PYEXE%" "%~dp0serve.py"
echo.
echo [%date% %time%] Server stopped (crash or shutdown). Restarting in 5 seconds...
echo Close this window to stop SAR Redact permanently.
timeout /t 5 /nobreak >nul
goto loop
