# Changelog

All notable changes to SAR Redact are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.3.0] — 2026-06-10

### Added
- **ICO response pack** — one-click generation of an Article 15 cover letter + certificate of redaction (PDF), including a DPA 2018 exemption schedule with codes and per-category line-item counts. Blocked when any redaction failures exist.
- **IG compliance dashboard** (`/admin/ig-report`) — turnaround vs 30-day statutory deadline, monthly volumes, per-SAR table with on-time ✓/✗ flags. CSV export for ICO returns.
- **Grouped review** — candidates grouped by name across all uploaded files with a ×N count badge and "Redact all / Keep all" bulk-action buttons.
- **Context snippets** — ±70-character excerpt shown under every candidate so reviewers see the surrounding sentence without opening the PDF.
- **Presence indicator** — live chip showing which other users have the same SAR open; allocation warning when a SAR is assigned to someone else.
- **Before/after disclosure preview** — side-by-side original vs redacted page modal on the completion screen.
- **J/K keyboard triage** — J = next candidate, K = previous (in addition to existing S/← shortcuts).
- **Offline bundle builder** (`tools/build_offline_bundle.py`) — packages the application, an embedded Python 3.12 runtime, and all Windows wheels into a single ~20 MB zip for practices whose proxy blocks PowerShell downloads. `--tls` variant includes cheroot + cryptography.
- **Easy Install Guide** (`EASY_INSTALL_GUIDE.md`) — plain-English step-by-step guide written for non-technical NHS administrative staff, covering first-time install, daily use, whole-practice server setup, and the USB-stick offline install path.
- **DCB0129 clinical safety case** (`docs/trust-pack/CLINICAL_SAFETY_CASE.md`) — eight hazards (H1–H8) with severity / likelihood / residual risk ratings, mitigations, and design links.
- **DPIA** (`docs/trust-pack/DPIA.md`) — pre-filled Data Protection Impact Assessment template for GP practices.
- **DSPT mapping** (`docs/trust-pack/DSPT_MAPPING.md`) — ten DSPT standards cross-referenced to product controls.
- **SECURITY.md** — full security architecture document covering data flows, threat model, and the no-remote-processing guarantee.
- **Automated compliance review** (`.github/workflows/docs-review.yml`) — weekly Claude Haiku loop that diffs recent code changes against the DPIA and clinical safety case, then opens GitHub issues when documents may need updating.
- **Automated release workflow** (`.github/workflows/release.yml`) — builds standard and offline-bundle zips and creates a GitHub release on every `v*.*.*` tag push.

### Fixed
- **XSS** — PDF-derived text HTML-escaped before insertion into `innerHTML` via `_esc()` helper in `candidates.js`.
- **Admin review-page 500 error** — missing `gp_users` context variable added to the review route.
- **`@nhs.net` NHSmail addresses** — plain `@nhs.net` domain was not matched by the previous `.endswith(".nhs.net")` check; explicit `domain in ("nhs.net", "nhs.uk")` check added.
- **Cross-line name false positives** — `TITLE_NAME_PATTERN` separator changed from `\s+` to `[ \t]+` so names are never matched across line breaks.
- **Wrong-location redaction boxes** — page text now built from PDF spans with precomputed character offsets; repeated names always map to the correct occurrence.
- **Update checker repo URL** — `sar/updater.py` now points to the correct repository (`Medicus-Reports-and-SARs`).

---

## [2.2.0] — 2026-05-15

### Added
- **SQLite storage** (`sar/store.py`) — WAL-mode SQLite replaces per-SAR JSON files. Automatic migration on first run.
- **Access audit trail** (`sar/audit.py`) — append-only JSONL log of every action (login, upload, view, approve, finalise). Admin viewer with filtering and CSV export.
- **Nightly backups** (`sar/backup.py`) — SQLite backup API snapshot + config + audit files in a date-stamped zip. Seven-zip rolling retention. Backup folder configurable in Settings.
- **HTTPS support** (`serve.py`, `tools/generate_cert.py`) — cheroot + self-signed certificate; no admin rights required. Auto-detected on startup.
- **`install_as_server.bat`** — registers SAR Redact as a per-user Startup folder autostart item via `server_loop.bat` restart-on-crash wrapper. Writes `CONNECT.txt` with LAN address.
- **Idle session timeout** — configurable in Settings (default 30 minutes).
- **Page-render cache** (`sar/pdf_parser.py`) — SHA1-keyed disk cache for rendered PDF page images; LRU eviction at 4,000 entries.
- **`/healthz`** and **`/admin/status`** — machine-readable health check and operational status endpoint (uptime, backup status, job counts).
- **Surname-first detection** — `SMITH, John` and `JOHN SMITH` ALL-CAPS formats with confidence-weighted scoring.
- **Mc/Mac/O'/De/Van name prefix support** throughout all name patterns.
- **Detection benchmark** (`tools/benchmark_detection.py`) — synthetic 200-document GP-record corpus; 99.4% recall / 100% precision on names.

### Fixed
- Thread-safety: per-SAR threading locks prevent interleaved saves under concurrent users.
- Relative path storage: uploaded/output file paths stored as basenames, removing machine-specific absolute paths from the database.

---

## [2.1.0] — 2026-04-20

### Added
- **Redaction failure reporting** — candidates that could not be placed on the PDF are listed in a banner and in the redaction log; certificate of redaction refused if failures exist.
- **Atomic writes** (`sar/fsutil.py`) — all JSON/config writes use `atomic_write_json` (temp → fsync → `os.replace`) to prevent corruption on crash or power loss.
- **Per-SAR locks** — concurrent finalise/delete calls on the same SAR are serialised.
- **Login rate limiting** — five failures per five minutes per source IP.
- **CSRF protection** on all state-changing forms and API routes.
- **POST-only logout** with CSRF token.
- **Upload and ZIP size caps** — 1 GB per upload; 4 GB uncompressed total; 2,000 ZIP entries; 800 MB per entry.
- **Originals preserved on page delete** — original PDF archived rather than deleted.
- **Nine new report templates** — PIP (PIP2), DVLA Group 1 and 2, firearms, adoption, occupational health, travel insurance, mental capacity, housing authority.
- **Pinned dependencies** in `requirements.txt`.
- **Rotating file logging**.
- **pytest suite** — 52 tests across auth, detection, store, backup, response pack, IG report, audit, fsutil, templates, and redactor.

### Fixed
- Redaction log never overstates completeness: failures are explicitly listed rather than silently omitted.

---

## [2.0.0] — 2026-03-01

### Changed
- **Medicus Suite rebrand** — updated design language throughout.
- **Thread-safe in-memory store** with background persistence.
- **Relative path storage** for portability across reinstalls and server moves.
- **Archive / redetect endpoints** added.
- **ES module JavaScript** — review UI split into pdf-viewer, candidates, draw, filters, main, api, and shortcuts modules.

---

## [1.0.0] — 2026-01-15

Initial release — Witley & Milford Surgery Subject Access Request Redaction System.
