@echo off
title SAR Redact v2
color 0A

:: ── Keep window open no matter what ───────────────────────────────────────
if "%1"=="_INNER" goto :inner
cmd /k "%~f0" _INNER
exit

:inner
:: ── Set working directory, handling UNC network paths ─────────────────────
:: pushd maps UNC paths (\\server\share\...) to a temp drive letter.
:: We capture %CD% AFTER pushd so %ROOT% uses the mapped letter, not UNC.
pushd "%~dp0"
if errorlevel 1 (
    echo  WARNING: Could not map network path. Trying to continue anyway...
)
set ROOT=%CD%\

echo.
echo  ================================================
echo   SAR Redact v2
echo  ================================================
echo.

:: ── Step 1: locate Python ─────────────────────────────────────────────────
set PYEXE=%ROOT%python-runtime\python.exe

if exist "%PYEXE%" (
    echo  [OK] Using bundled Python runtime.
    goto :patch_pth
)

python --version >nul 2>&1
if not errorlevel 1 (
    echo  [OK] Using system Python.
    set PYEXE=python
    goto :setup_venv
)

:: ── Download embedded Python ───────────────────────────────────────────────
echo  Downloading portable Python runtime...
echo  (One-time ~15MB -- no admin rights needed)
echo.

:: SHA-256 of python-3.12.9-embed-amd64.zip (pinned at release time)
:: NOTE: get-pip.py is intentionally NOT hash-pinned because it is a
:: rolling bootstrap script that changes frequently upstream.
set PYEMBED_SHA256=17f5e624c5b41a357da654bd37fb92e563f40021809cf35d81730bb10011980e

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip' -OutFile '%ROOT%py-embed.zip' -UseBasicParsing; Write-Host 'DOWNLOAD_OK' } catch { Write-Host ('DOWNLOAD_FAIL: ' + $_.Exception.Message) }" > "%ROOT%dl_result.txt" 2>&1

findstr /C:"DOWNLOAD_OK" "%ROOT%dl_result.txt" >nul
if errorlevel 1 (
    echo  ERROR: Python download failed.
    type "%ROOT%dl_result.txt"
    echo.
    echo  If this folder is on a network drive, copy it to C:\SAR Redact\
    echo  and run start_server.bat from there. See INSTALL.md.
    del "%ROOT%dl_result.txt" 2>nul
    pause & exit /b 1
)
del "%ROOT%dl_result.txt" 2>nul

:: Verify SHA-256 of the downloaded Python embed
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$computed = (Get-FileHash -Path '%ROOT%py-embed.zip' -Algorithm SHA256).Hash.ToLower(); $expected = '%PYEMBED_SHA256%'.ToLower(); if ($computed -eq $expected) { Write-Host 'HASH_OK' } else { Write-Host ('HASH_MISMATCH:computed=' + $computed + ':expected=' + $expected) }" > "%ROOT%hash_result.txt" 2>&1

findstr /C:"HASH_OK" "%ROOT%hash_result.txt" >nul
if errorlevel 1 (
    echo.
    echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo   SECURITY ERROR: Python runtime SHA-256 checksum MISMATCH!
    echo   The downloaded file does not match the expected hash.
    echo   Aborting to protect your system.
    echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo.
    type "%ROOT%hash_result.txt"
    del "%ROOT%hash_result.txt" 2>nul
    del "%ROOT%py-embed.zip" 2>nul
    pause & exit /b 1
)
del "%ROOT%hash_result.txt" 2>nul
echo  [OK] Python runtime checksum verified.

:: Extract and check it worked
echo  Extracting Python runtime...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -Path '%ROOT%py-embed.zip' -DestinationPath '%ROOT%python-runtime' -Force; Write-Host 'EXTRACT_OK'"  > "%ROOT%ex_result.txt" 2>&1

findstr /C:"EXTRACT_OK" "%ROOT%ex_result.txt" >nul
if errorlevel 1 (
    echo  ERROR: Extraction failed.
    type "%ROOT%ex_result.txt"
    del "%ROOT%ex_result.txt" 2>nul
    del "%ROOT%py-embed.zip" 2>nul
    pause & exit /b 1
)
del "%ROOT%ex_result.txt" 2>nul
del "%ROOT%py-embed.zip" 2>nul

if not exist "%PYEXE%" (
    echo  ERROR: python.exe not found after extraction. Disk may be full or write-protected.
    pause & exit /b 1
)

:: Enable import site (required for pip in embedded Python)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "(Get-Content '%ROOT%python-runtime\python312._pth') -replace '#import site','import site' | Set-Content '%ROOT%python-runtime\python312._pth'"

echo  [OK] Python runtime ready.

:: ── Patch ._pth to include project root ───────────────────────────────────
:: Uses wildcard to find the correct ._pth file regardless of Python version
:patch_pth
set PTH_FILE=
for %%F in ("%ROOT%python-runtime\python3*._pth") do set PTH_FILE=%%F

if "%PTH_FILE%"=="" (
    echo  ERROR: Could not find python3*._pth in python-runtime folder.
    echo  The Python runtime may be incomplete. Delete python-runtime\ and retry.
    pause & exit /b 1
)

:: Enable import site if not already done
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "(Get-Content '%PTH_FILE%') -replace '#import site','import site' | Set-Content '%PTH_FILE%'"

:: Add project root to path
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pth='%PTH_FILE:\=\\%'; $proj='%ROOT:\=\\%'.TrimEnd('\\'); $lines=Get-Content $pth; if ($lines -notcontains $proj) { Add-Content $pth $proj; Write-Host '  [OK] Project path registered.' } else { Write-Host '  [OK] Project path already registered.' }"

:: ── Install dependencies ───────────────────────────────────────────────────
if exist "%ROOT%python-runtime\Lib\site-packages\flask" (
    echo  [OK] Dependencies already installed.
    goto :launch
)

:: Bootstrap pip with error check
"%PYEXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo  Bootstrapping pip...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "try { Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%ROOT%get-pip.py' -UseBasicParsing; Write-Host 'PIP_OK' } catch { Write-Host ('PIP_FAIL: ' + $_.Exception.Message) }" > "%ROOT%pip_result.txt" 2>&1
    findstr /C:"PIP_OK" "%ROOT%pip_result.txt" >nul
    if errorlevel 1 (
        echo  ERROR: Could not download pip.
        type "%ROOT%pip_result.txt"
        del "%ROOT%pip_result.txt" 2>nul
        pause & exit /b 1
    )
    del "%ROOT%pip_result.txt" 2>nul
    "%PYEXE%" "%ROOT%get-pip.py" --quiet --no-warn-script-location
    del "%ROOT%get-pip.py" 2>nul
)

echo.
echo  ------------------------------------------------
echo   First-time setup: installing packages
echo   This takes 3-8 minutes depending on connection
echo  ------------------------------------------------
echo.

echo  [1/6] Installing Flask (web framework)...
"%PYEXE%" -m pip install flask==3.1.2 --quiet --no-warn-script-location
if errorlevel 1 ( echo  ERROR: Flask install failed. & pause & exit /b 1 )
echo  [1/6] Done.

echo  [2/6] Installing Waitress (server)...
"%PYEXE%" -m pip install waitress==3.0.2 --quiet --no-warn-script-location
if errorlevel 1 ( echo  ERROR: Waitress install failed. & pause & exit /b 1 )
echo  [2/6] Done.

echo  [3/6] Installing striprtf (RTF support)...
"%PYEXE%" -m pip install striprtf==0.0.29 --quiet --no-warn-script-location
if errorlevel 1 ( echo  ERROR: striprtf install failed. & pause & exit /b 1 )
echo  [3/6] Done.

echo  [4/6] Installing PyMuPDF (PDF engine -- largest, ~2-5 min)...
"%PYEXE%" -m pip install pymupdf==1.26.4 --quiet --no-warn-script-location
if errorlevel 1 ( echo  ERROR: PyMuPDF install failed. & pause & exit /b 1 )
echo  [4/6] Done.

echo  [5/6] Installing python-docx (DOCX support)...
"%PYEXE%" -m pip install python-docx==1.2.0 --quiet --no-warn-script-location
if errorlevel 1 ( echo  ERROR: python-docx install failed. & pause & exit /b 1 )
echo  [5/6] Done.

echo  [6/6] Installing extract-msg (MSG email support)...
"%PYEXE%" -m pip install extract-msg==0.55.0 --quiet --no-warn-script-location
if errorlevel 1 ( echo  ERROR: extract-msg install failed. & pause & exit /b 1 )
echo  [6/6] Done.

echo.
echo  ------------------------------------------------
echo   [OK] All packages installed.
echo  ------------------------------------------------
goto :launch

:: ── System Python: venv path ───────────────────────────────────────────────
:setup_venv
if not exist "%ROOT%venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    "%PYEXE%" -m venv "%ROOT%venv"
    if errorlevel 1 (
        echo  ERROR: Failed to create virtual environment.
        echo  If on a network drive, copy this folder to C:\SAR Redact\ first.
        pause & exit /b 1
    )
    echo.
    echo  ------------------------------------------------
    echo   First-time setup: installing packages
    echo   This takes 3-8 minutes depending on connection
    echo  ------------------------------------------------
    echo.
    echo  [1/6] Installing Flask...
    "%ROOT%venv\Scripts\pip" install flask==3.1.2 --quiet --no-warn-script-location
    if errorlevel 1 ( echo  ERROR: Flask install failed. & pause & exit /b 1 )
    echo  [1/6] Done.
    echo  [2/6] Installing Waitress...
    "%ROOT%venv\Scripts\pip" install waitress==3.0.2 --quiet --no-warn-script-location
    if errorlevel 1 ( echo  ERROR: Waitress install failed. & pause & exit /b 1 )
    echo  [2/6] Done.
    echo  [3/6] Installing striprtf...
    "%ROOT%venv\Scripts\pip" install striprtf==0.0.29 --quiet --no-warn-script-location
    if errorlevel 1 ( echo  ERROR: striprtf install failed. & pause & exit /b 1 )
    echo  [3/6] Done.
    echo  [4/6] Installing PyMuPDF (~2-5 min)...
    "%ROOT%venv\Scripts\pip" install pymupdf==1.26.4 --quiet --no-warn-script-location
    if errorlevel 1 ( echo  ERROR: PyMuPDF install failed. & pause & exit /b 1 )
    echo  [4/6] Done.
    echo  [5/6] Installing python-docx (DOCX support)...
    "%ROOT%venv\Scripts\pip" install python-docx==1.2.0 --quiet --no-warn-script-location
    if errorlevel 1 ( echo  ERROR: python-docx install failed. & pause & exit /b 1 )
    echo  [5/6] Done.
    echo  [6/6] Installing extract-msg (MSG email support)...
    "%ROOT%venv\Scripts\pip" install extract-msg==0.55.0 --quiet --no-warn-script-location
    if errorlevel 1 ( echo  ERROR: extract-msg install failed. & pause & exit /b 1 )
    echo  [6/6] Done.
    echo.
    echo  ------------------------------------------------
    echo   [OK] All packages installed.
    echo  ------------------------------------------------
)
set PYEXE=%ROOT%venv\Scripts\python.exe

:: ── Launch ─────────────────────────────────────────────────────────────────
:launch
echo.
echo  Opening browser launcher...
start "" "%ROOT%SAR-Redact.html"
ping -n 2 localhost >nul 2>&1

echo  Server running -- keep this window open while working.
echo  Press Ctrl+C to stop.
echo.
"%PYEXE%" "%ROOT%serve.py"

popd
echo.
echo  Server stopped. Press any key to close.
pause
