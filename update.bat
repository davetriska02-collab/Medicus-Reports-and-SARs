@echo off
title SAR Redact Updater
color 0A

:: ── Keep window open no matter what ───────────────────────────────────────
if "%1"=="_INNER" goto :inner
cmd /k "%~f0" _INNER
exit

:inner
pushd "%~dp0"
if errorlevel 1 (
    echo  WARNING: Could not map network path. Trying to continue anyway...
)
set ROOT=%CD%\

echo.
echo  ================================================
echo   SAR Redact — One-Click Updater
echo  ================================================
echo.
echo  This updates SAR Redact in place.
echo  Your data, uploads and output folders are NOT touched.
echo.
echo  Press any key to continue (Ctrl+C to abort)...
pause >nul

:: ── Step 1: Query GitHub API for latest release ─────────────────────────
echo.
echo  [1/7] Checking for latest release on GitHub...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -Uri 'https://api.github.com/repos/davetriska02-collab/Medicus-Reports-and-SARs/releases/latest' -UseBasicParsing; Set-Content '%ROOT%_api_response.txt' $r.Content; Write-Host 'API_OK' } catch { Write-Host ('API_FAIL: ' + $_.Exception.Message) }" > "%ROOT%_api_result.txt" 2>&1

findstr /C:"API_OK" "%ROOT%_api_result.txt" >nul
if errorlevel 1 (
    echo  ERROR: Could not reach GitHub API.
    type "%ROOT%_api_result.txt"
    echo.
    echo  Check your internet connection and try again.
    del "%ROOT%_api_result.txt" 2>nul
    del "%ROOT%_api_response.txt" 2>nul
    pause & exit /b 1
)
del "%ROOT%_api_result.txt" 2>nul

:: Extract tag_name and download URL from response
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$json = Get-Content '%ROOT%_api_response.txt' -Raw | ConvertFrom-Json; $json.tag_name | Set-Content '%ROOT%_latest_tag.txt'; ($json.assets | Where-Object { $_.name -match '^sar-redact-v[^-]+\.zip$' } | Select-Object -First 1).browser_download_url | Set-Content '%ROOT%_dl_url.txt'; Write-Host 'PARSE_OK'" > "%ROOT%_parse_result.txt" 2>&1

findstr /C:"PARSE_OK" "%ROOT%_parse_result.txt" >nul
if errorlevel 1 (
    echo  ERROR: Could not parse GitHub API response.
    type "%ROOT%_parse_result.txt"
    del "%ROOT%_parse_result.txt" 2>nul
    del "%ROOT%_api_response.txt" 2>nul
    del "%ROOT%_latest_tag.txt" 2>nul
    del "%ROOT%_dl_url.txt" 2>nul
    pause & exit /b 1
)
del "%ROOT%_parse_result.txt" 2>nul
del "%ROOT%_api_response.txt" 2>nul

set /p LATEST_TAG=<"%ROOT%_latest_tag.txt"
set /p DL_URL=<"%ROOT%_dl_url.txt"
del "%ROOT%_latest_tag.txt" 2>nul
del "%ROOT%_dl_url.txt" 2>nul

if "%LATEST_TAG%"=="" (
    echo  ERROR: Could not determine latest version tag.
    pause & exit /b 1
)
if "%DL_URL%"=="" (
    echo  ERROR: Could not find sar-redact-v*.zip asset in latest release.
    echo  Check https://github.com/davetriska02-collab/Medicus-Reports-and-SARs/releases
    pause & exit /b 1
)

:: Strip leading 'v' from tag to get version number
set LATEST_VER=%LATEST_TAG:v=%

echo  Latest release: %LATEST_TAG%

:: ── Step 2: Read current version from app.py ─────────────────────────────
echo.
echo  [2/7] Reading current installed version...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "(Select-String -Path '%ROOT%app.py' -Pattern 'APP_VERSION\s*=\s*""([^""]+)""').Matches[0].Groups[1].Value | Set-Content '%ROOT%_cur_ver.txt'; Write-Host 'VER_OK'" > "%ROOT%_ver_result.txt" 2>&1

findstr /C:"VER_OK" "%ROOT%_ver_result.txt" >nul
if errorlevel 1 (
    echo  WARNING: Could not read current version from app.py — will proceed with update anyway.
    set CURRENT_VER=unknown
) else (
    set /p CURRENT_VER=<"%ROOT%_cur_ver.txt"
)
del "%ROOT%_ver_result.txt" 2>nul
del "%ROOT%_cur_ver.txt" 2>nul

echo  Installed: v%CURRENT_VER%  ->  Latest: v%LATEST_VER%

if "%CURRENT_VER%"=="%LATEST_VER%" (
    echo.
    echo  ================================================
    echo   Already up to date (v%CURRENT_VER%).
    echo  ================================================
    echo.
    pause & exit /b 0
)

:: ── Step 3: Warn user to close server window ─────────────────────────────
echo.
echo  ================================================
echo   IMPORTANT: If the black server window is open,
echo   close it now, then press a key to continue.
echo  ================================================
echo.
pause >nul

:: ── Step 4: Download the release zip ─────────────────────────────────────
echo.
echo  [3/7] Downloading %LATEST_TAG% from GitHub...
echo  URL: %DL_URL%

set TMPZIP=%TEMP%\sar-redact-%LATEST_TAG%.zip
set TMPDIR=%TEMP%\sar-redact-%LATEST_TAG%-extract

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Invoke-WebRequest -Uri '%DL_URL%' -OutFile '%TMPZIP%' -UseBasicParsing; Write-Host 'DLZIP_OK' } catch { Write-Host ('DLZIP_FAIL: ' + $_.Exception.Message) }" > "%ROOT%_dlzip_result.txt" 2>&1

findstr /C:"DLZIP_OK" "%ROOT%_dlzip_result.txt" >nul
if errorlevel 1 (
    echo  ERROR: Download failed.
    type "%ROOT%_dlzip_result.txt"
    del "%ROOT%_dlzip_result.txt" 2>nul
    pause & exit /b 1
)
del "%ROOT%_dlzip_result.txt" 2>nul
echo  Download complete.

:: ── Step 5: Extract to temp folder ───────────────────────────────────────
echo.
echo  [4/7] Extracting update...

if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Expand-Archive -Path '%TMPZIP%' -DestinationPath '%TMPDIR%' -Force; Write-Host 'EXTRACT_OK' } catch { Write-Host ('EXTRACT_FAIL: ' + $_.Exception.Message) }" > "%ROOT%_extract_result.txt" 2>&1

findstr /C:"EXTRACT_OK" "%ROOT%_extract_result.txt" >nul
if errorlevel 1 (
    echo  ERROR: Extraction failed.
    type "%ROOT%_extract_result.txt"
    del "%ROOT%_extract_result.txt" 2>nul
    del "%TMPZIP%" 2>nul
    pause & exit /b 1
)
del "%ROOT%_extract_result.txt" 2>nul
del "%TMPZIP%" 2>nul

set NEWFILES=%TMPDIR%\sar-redact

if not exist "%NEWFILES%\app.py" (
    echo  ERROR: Expected sar-redact\app.py inside zip — update package may be malformed.
    pause & exit /b 1
)
echo  Extraction complete.

:: ── Step 6: Back up current app files ────────────────────────────────────
echo.
echo  [5/7] Backing up current v%CURRENT_VER% files...

set BACKUP_DIR=%ROOT%backup_pre_update_%CURRENT_VER%
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

:: Copy each app item individually (skip data/uploads/output)
for %%I in (app.py serve.py requirements.txt start_server.bat start_server.sh server_loop.bat install_as_server.bat update.bat SAR-Redact.html README.md INSTALL.md EASY_INSTALL_GUIDE.md SECURITY.md CHANGELOG.md) do (
    if exist "%ROOT%%%I" copy /Y "%ROOT%%%I" "%BACKUP_DIR%\%%I" >nul 2>&1
)
for %%D in (sar static templates tools) do (
    if exist "%ROOT%%%D" xcopy /E /Y /I /Q "%ROOT%%%D" "%BACKUP_DIR%\%%D\" >nul 2>&1
)
echo  Backup saved to: %BACKUP_DIR%

:: ── Step 7: Copy new files over install ──────────────────────────────────
echo.
echo  [6/7] Installing new files...

:: Copy individual app files from the zip's sar-redact/ folder
for %%I in (app.py serve.py requirements.txt start_server.bat start_server.sh server_loop.bat install_as_server.bat update.bat SAR-Redact.html README.md INSTALL.md EASY_INSTALL_GUIDE.md SECURITY.md CHANGELOG.md) do (
    if exist "%NEWFILES%\%%I" copy /Y "%NEWFILES%\%%I" "%ROOT%%%I" >nul 2>&1
)

:: Copy app directories (sar, static, templates, tools) — NOT data/uploads/output
for %%D in (sar static templates tools) do (
    if exist "%NEWFILES%\%%D" (
        xcopy /E /Y /I /Q "%NEWFILES%\%%D" "%ROOT%%%D\" >nul 2>&1
    )
)

echo  New files installed.

:: Clean up temp extract
rmdir /s /q "%TMPDIR%" 2>nul

echo.
echo  ================================================
echo   [7/7] Update complete!
echo   Installed: v%CURRENT_VER%  ->  v%LATEST_VER%
echo  ================================================
echo.
echo  Run start_server.bat to launch the updated server.
echo  (New dependencies, if any, install automatically on first run.)
echo.
echo  Your backup of v%CURRENT_VER% is in:
echo  %BACKUP_DIR%
echo.
pause
popd
