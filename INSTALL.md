# Installation Guide

> **Non-technical staff:** use the [Easy Install Guide](EASY_INSTALL_GUIDE.md)
> instead. This document is the technical reference.


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

**Option C — Offline bundle (recommended for proxied-off practices)**
A fully self-contained zip (~20 MB) with Python and all dependencies
pre-installed — the recipient extracts it and runs `start_server.bat` with
no internet needed at any point. Build it on any machine with internet:

```
python tools\build_offline_bundle.py          # standard
python tools\build_offline_bundle.py --tls    # includes HTTPS support
```

The zip appears in `dist\`. Transfer it on a USB stick or via NHSmail.

---

## Network / multi-user setup (central server)

Run SAR Redact on one dedicated machine; everyone else uses a browser.

**Quick way:** run `start_server.bat` and share the addresses shown in the
banner (also written to `CONNECT.txt`).

**Proper way — install as a server (no admin rights needed):**

1. Run `start_server.bat` once so Python and dependencies install
2. Run `install_as_server.bat`

This registers the server to start automatically (minimised) every time the
user logs on, with an automatic restart if it ever crashes, and writes
`CONNECT.txt` with the addresses to share with staff:

```
http://<hostname>:5000      e.g. http://RECEPTION-PC2:5000
```

### Nightly backups

In **Settings**, set *Backup folder* to a NAS share or synced folder
(e.g. `\\practice-nas\backups\sarredact`). A backup zip is written daily —
database, configuration, audit trail and documents — keeping the last 7.
Backup status is visible at `/admin/status`.

### HTTPS (optional, recommended for server mode)

Waitress serves plain HTTP. To enable TLS — still without admin rights:

1. `pip install cheroot cryptography` (using the same Python as SAR Redact)
2. `python tools\generate_cert.py`
3. Restart the server — it detects `data/tls/cert.pem` and switches to HTTPS

The certificate is self-signed, so browsers show a one-time warning that
staff can accept (or IT can trust the cert centrally via group policy).

---

## Data location

All patient data is stored in the `data\` subfolder of the SAR Redact
directory (`data\sarredact.db` plus configuration files and the audit
trail in `data\audit\`). Uploaded and redacted documents live in
`uploads\` and `output\`. Nothing is stored remotely — set a backup
folder in Settings (above) for automatic nightly backups.
