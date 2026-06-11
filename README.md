# SAR Redact v2
### Witley & Milford Surgery — Subject Access Request Redaction System

[![Tests](https://github.com/davetriska02-collab/Medicus-Reports-and-SARs/actions/workflows/tests.yml/badge.svg)](https://github.com/davetriska02-collab/Medicus-Reports-and-SARs/actions/workflows/tests.yml)

Built on the Medicus Suite design language. Processes GP medical records for Subject Access Request disclosure under UK GDPR.

---

## Quick start

> 🟢 **Not technical?** Read the [**Easy Install Guide**](EASY_INSTALL_GUIDE.md)
> instead — step-by-step, written for normal humans, covers everything
> including the "downloads blocked" case and the whole-practice server setup.

**Windows**
1. Extract this folder somewhere permanent (e.g. `C:\SAR Redact\`)
2. Double-click `start_server.bat`
3. First run installs dependencies automatically — takes ~2 minutes
4. Browse to `http://localhost:5000`

**Mac / Linux**
1. Extract the folder
2. Run `./start_server.sh` in terminal
3. Browse to `http://localhost:5000`

---

## Network access (multi-user)

Run `serve.py` on a dedicated machine. The startup banner shows your LAN address — any machine on the same network can access the app at `http://<IP>:5000`. Recommended for practices with multiple GPs reviewing SARs.

---

## First-run setup

On first launch you will be prompted to create an admin account. From there you can add GP users via **Admin → Users**.

---

## Updates

**Easy path:** double-click `update.bat`. It downloads the latest release from GitHub, backs up your current app files, and installs the new version — without touching your `data/`, `uploads/`, or `output/` folders. No admin rights needed.

**Manual path:** download the latest zip from the releases page, extract alongside your existing install, and copy your `data/` folder across.

SAR Redact also checks for updates automatically on server start — a green banner appears on the dashboard when a newer version is available.

Updates are published to:  
`https://github.com/davetriska02-collab/Medicus-Reports-and-SARs/releases`

---

## Supported file formats

PDF · TIF/TIFF · RTF · TXT · DOCX · EML · MSG · PNG · JPG · ZIP (containing any of the above) · CDAX (GP2GP clinical documents)

---

## Data storage

All data is stored locally in the `data/` subfolder. Nothing is transmitted externally except the optional GitHub update check (version number only, no patient data).

---

## Compliance & security

- [`SECURITY.md`](SECURITY.md) — security architecture and data flows
- [`docs/trust-pack/`](docs/trust-pack/) — DPIA template, DCB0129 clinical safety case + hazard log, DSPT mapping
- [`docs/TOOLSET_OVERVIEW.md`](docs/TOOLSET_OVERVIEW.md) — full capability overview
- `Admin → Audit` — access audit trail · `Admin → IG` — SAR turnaround report
- **Automatic GDPR retention** — completed SARs are automatically deleted after 180 days by default (configurable in Settings; 0 = never); every deletion is audited.

---

## Version history

| Version | Notes |
|---------|-------|
| 2.5 | Demo mode (synthetic patient SAR for walkthroughs) · CI on every push · one-click `update.bat` updater (no admin rights) · OCR for scanned pages + unscreened-page warnings · DOCX/EML/MSG ingestion with attachment handling · self-learning detection dictionary · intake fields + statutory 30-day clock from request date · Article 12 acknowledgment letter · dashboard deadline urgency strip · optional two-person sign-off |
| 2.4 | Combined print bundle: one-click merge of cover letter + certificate + all redacted documents into a single printable PDF (max 5 parts if very large) with contents page and continuous page numbering — one print job instead of hundreds · redaction log clearly marked internal-only |
| 2.3 | ICO response pack (one-click Article 15 cover letter + certificate of redaction with DPA 2018 exemptions schedule) · IG report dashboard (turnaround vs statutory deadline, monthly volumes, CSV export) · grouped by-name review ("Redact all 12 occurrences") · context snippets on every candidate · presence indicator + allocation warning · before/after disclosure preview · J/K keyboard triage · XSS fix for PDF-derived text · admin review-page 500 fix |
| 2.2 | Central-server release: SQLite storage (auto-migrates JSON) · access audit trail with admin viewer + CSV export · nightly backups with retention · optional HTTPS (cheroot + self-signed cert tool) · `install_as_server.bat` autostart + restart-on-crash + CONNECT.txt · idle session timeout · page-render cache · `/healthz` + `/admin/status` · surname-first (SMITH, John) and ALL-CAPS name detection · exact span mapping · detection benchmark (names 99.4% recall / 100% precision on synthetic corpus) |
| 2.1 | Redaction-failure reporting (audit log never overstates) · atomic writes · per-SAR locks · login rate limiting · CSRF on all forms · POST-only logout · upload/zip size caps · originals preserved on page delete · 9 new report templates (PIP, DVLA, firearms, adoption, occupational health, travel insurance, mental capacity, Group 2 driver, housing) · pinned dependencies · rotating file logging · pytest suite |
| 2.0 | Medicus Suite rebrand · thread-safe store · relative path storage · archive/redetect endpoints · ES module JS split |
| 1.0 | Initial release |

---

*Graysbrook Ltd · Dr D Triska GMC 6159481 · DCB0129 Clinical Safety Officer*
