# Installation Guide


## NHS network/home drives

Some NHS trusts map user home folders to a network UNC path like:
`\\server.nhs.uk\GP\Home\Emma.Parnell\Desktop\`

**CMD cannot use a UNC path as its working directory.** If you see:

```
UNC paths are not supported. Defaulting to Windows directory.
Access to the path 'C:\Windows\py-embed.zip' is denied.
```

The fix is simple: **copy the SAR Redact folder to your local C: drive** before running the bat.

1. Copy the `sar-redact-v2-package` folder to `C:\SAR Redact\`
2. Run `start_server.bat` from there

The data folder (`C:\SAR Redact\data\`) will then be on a local drive. SAR records are stored there, so this is also better for performance and reliability than running off a network share.

---
## Standard install (Python already on the machine)

1. Extract the zip to a permanent location (e.g. `C:\SAR Redact\`)
2. Double-click `start_server.bat`
3. First run downloads dependencies — takes 2–4 minutes
4. Open browser to `http://localhost:5000`

---

## NHS / locked-down Windows (no admin rights)

`start_server.bat` handles this automatically. When it can't find Python it uses
PowerShell — which is available on all Windows 10/11 NHS machines and **does not
require admin rights** — to download a portable Python runtime (~15 MB) and
extract it directly into the SAR Redact folder.

**No installer. No admin rights. Nothing written to Program Files or the registry.**

The sequence on a locked machine:

1. Extract zip → run `start_server.bat`
2. Bat detects no Python → downloads `python-3.12.9-embed-amd64.zip` via PowerShell
3. Extracts to `python-runtime\` inside the SAR Redact folder
4. Bootstraps pip, creates venv, installs Flask / PyMuPDF / Waitress
5. Starts the server

Subsequent runs skip all of this and go straight to step 5.

### If PowerShell downloads are blocked

Some NHS trusts block PowerShell web requests via proxy. If you see:

```
ERROR: Could not download Python runtime.
```

Options:

**Option A — Manual portable Python**
1. On any machine with internet access, download:
   `https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip`
2. Extract the zip into a folder called `python-runtime` inside the SAR Redact directory
3. Re-run `start_server.bat`

**Option B — Ask IT**
Ask your IT team to install Python 3.12 from `https://www.python.org/downloads`
with "Add python.exe to PATH" ticked. No other configuration needed.

**Option C — Pre-built bundle**
Contact the developer for a fully self-contained bundle with Python and all
dependencies pre-included (no internet required at all — ~300 MB zip).

---

## Network / multi-user setup

Run on one dedicated machine. The startup banner shows your LAN IP address.
All other machines on the same network can access SAR Redact at:

```
http://<IP address>:5000
```

No software needed on the other machines — just a browser.

---

## Data location

All patient data is stored in the `data\` subfolder of the SAR Redact directory.
Back this up regularly. Nothing is stored remotely.
