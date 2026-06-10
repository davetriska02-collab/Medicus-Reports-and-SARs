@echo off
:: SAR Redact — register this machine as the practice's central server.
:: No admin rights required: uses the current user's Startup folder (and a
:: per-user scheduled task where permitted) so the server starts at logon.
::
:: Run start_server.bat once FIRST so Python and dependencies are installed.
title SAR Redact - Server Setup
cd /d "%~dp0"
set ROOT=%~dp0

echo.
echo  ================================================
echo   SAR Redact - install as central server
echo  ================================================
echo.

if not exist "%ROOT%python-runtime\python.exe" if not exist "%ROOT%venv\Scripts\python.exe" (
    echo  ERROR: Python runtime not found.
    echo  Run start_server.bat once first to install it, then re-run this.
    pause & exit /b 1
)

:: 1. Startup-folder shortcut (works for every locked-down account)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut('%STARTUP%\SAR Redact Server.lnk'); $lnk.TargetPath = '%ROOT%server_loop.bat'; $lnk.WorkingDirectory = '%ROOT%'; $lnk.WindowStyle = 7; $lnk.Description = 'SAR Redact central server'; $lnk.Save(); Write-Host '  [OK] Startup shortcut created (starts minimised at logon).'"

:: 2. Per-user scheduled task as well, when the trust policy allows it
schtasks /create /tn "SAR Redact Server" /tr "\"%ROOT%server_loop.bat\"" /sc onlogon /f >nul 2>&1
if not errorlevel 1 (
    echo   [OK] Logon task registered as well ^(schtasks^).
) else (
    echo   [i ] Scheduled task not permitted on this machine - the Startup
    echo        shortcut above is sufficient.
)

echo.
echo  ------------------------------------------------
echo   Server installed. Starting it now...
echo  ------------------------------------------------
echo.
echo   After startup, share the addresses in CONNECT.txt
echo   with practice staff. They need only a browser.
echo.
echo   Optional next steps (see INSTALL.md):
echo     - Set a backup folder in Settings (nightly backups)
echo     - Enable HTTPS: pip install cheroot cryptography
echo       then: python tools\generate_cert.py
echo.
start "" "%ROOT%server_loop.bat"
pause
