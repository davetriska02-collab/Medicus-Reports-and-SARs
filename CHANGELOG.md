# Changelog

All notable changes to SAR Redact are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.5.4] — 2026-06-11

### Fixed
- **Lost-update race on SAR candidates** — before this fix, two reviewers approving different candidates at the same time could interleave their read-mutate-write cycles, causing one reviewer's decision to silently overwrite the other's. All mutating SAR routes now hold the per-SAR RLock across the full read-mutate-save sequence via a `_mutate` context manager.

### Security
- **`.sarpack` import id validation** — the id field extracted from an uploaded sarpack was previously used directly as a directory name; a crafted id such as `../../evil` could write files outside `UPLOAD_DIR`. The import now validates the id against a strict alphanumeric pattern and confirms the resolved path stays within the uploads root.
- **Checksum-verified updates with auto-rollback** — `update.bat` now downloads the `SHA256SUMS` manifest from the same GitHub release, verifies the zip's SHA-256 before installing, aborts with a loud error on mismatch, and automatically restores the pre-update backup if any file copy step fails during install. Releases older than 2.5.4 that have no checksum manifest require an explicit keypress to continue.
- **Pinned Python runtime hash** — `start_server.bat` now embeds the SHA-256 of `python-3.12.9-embed-amd64.zip` and verifies it after download before extracting. The hash is `17f5e624c5b41a357da654bd37fb92e563f40021809cf35d81730bb10011980e`. `get-pip.py` is intentionally left unverified (it is a rolling bootstrap script).

---

## [2.5.3] — 2026-06-11

### Fixed
- **Critical: review screen JavaScript was broken by an orphaned `<script>` tag** (`templates/review.html`). Six page globals (file lists, main record, admin flag, current user) rendered as text instead of executing, breaking the file selector, PDF-viewer bootstrap, and admin gating. Introduced in v2.5.1 and missed because nothing tested template rendering. A new static test suite (`tests/test_html_templates.py`) now fails the build on unbalanced script tags or stranded `window.*` assignments across every template.

### Security
- **HTTP security headers** added on every response (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and a Content-Security-Policy with `frame-ancestors 'none'` / `object-src 'none'`) — defence-in-depth against clickjacking and MIME-sniffing on shared practice networks.
- **Stored-XSS hardening on the Settings page** — staff names, custom words, and dictionary suggestions are now HTML-escaped before display, and their action buttons read values from `data-` attributes instead of inline string interpolation.
- **Secure session cookies under TLS** — `SESSION_COOKIE_SECURE` is now enabled automatically when serving HTTPS and can be forced on behind a TLS-terminating proxy via `SAR_COOKIE_SECURE=1`. Login now marks the session permanent so the intended 8-hour absolute lifetime is actually enforced.

### Changed
- **Releases now run the full test suite before publishing** (`.github/workflows/release.yml`) — a failing suite blocks the release.
- **Pinned the four previously-unpinned packages** on the system-Python (venv) install path in `start_server.bat`, matching the embedded-Python path and `requirements.txt`.
- Added `docs/AUDIT.md` — a full principal-level audit of the codebase with severity-rated findings and a milestone task plan.

---

## [2.5.2] — 2026-06-11

### Fixed
- **Mark-fixed re-fail loop** — clicking "Mark fixed" in the guided fix queue removed the failure entry from `sar.redaction_failures` but left the original candidate in APPROVED status. Re-finalising would then re-attempt the unplaceable redaction, fail again, and re-populate the same failure — creating an infinite loop. The resolve endpoint's mark-fixed path now also sets the original candidate's status to REJECTED (with the reason annotated "Superseded by manual redaction via fix queue"), so re-finalise sees only the reviewer's manually drawn box and produces no new failures.
- **Admin override for disclosure blocks** — practices that have manually checked the disclosed output documents are no longer hard-locked out of the print bundle or response pack. Admins can now confirm an override (surfaced via a browser confirm dialog when a 409 is returned), which proceeds despite outstanding failures or a pending re-finalise. The override is audited (`print_bundle_override` / `response_pack_override`) and the certificate of redaction honestly states "N redaction(s) could not be machine-verified as applied. The authorised signatory has manually verified the disclosed documents before release." instead of the normal machine-verification confirmation. Non-admin override attempts return 403.

---

## [2.5.1] — 2026-06-11

### Added
- **Guided fix queue for unplaced redactions** — when finalise reports that approved redactions could not be placed, the warning now leads straight into a fix queue instead of leaving the reviewer to hunt through hundreds of documents. Each failure automatically opens the right file at the right page with draw mode armed, shows the surrounding context sentence, and flashes a highlight over the text when it can be located. "Mark fixed" advances the queue; "Dismiss" requires confirmation and is audited. Per-failure "Fix →" links and a "Fix all" button on the completion screen provide the same queue.
- **Re-finalise guard** — resolving or dismissing failures can no longer unblock the disclosure documents on its own: the certificate of redaction and print bundle stay blocked (with a clear message) until the SAR is re-finalised so the manual redaction boxes are actually applied to the output PDFs.

---

## [2.5.0] — 2026-06-10

### Added
- **Demo mode** — admin button "🎓 Try a demo SAR" on the dashboard creates a fully synthetic 4-page GP record with planted PII of several kinds (names in titled/surname-first/ALL-CAPS forms, NHS numbers that pass Modulus-11, addresses, phone numbers, `@nhs.net` emails). Reviewers see real detection candidates instantly without needing to supply patient data. A second click returns the same demo SAR rather than stacking duplicates. Subject is unmistakably synthetic: "DEMO PATIENT — SYNTHETIC DATA". (`sar/demo.py`, `app.py` `/api/demo-sar`).
- **Continuous integration** — GitHub Actions workflow (`.github/workflows/tests.yml`) runs the full pytest suite on every push and pull request, keeping the main branch green.
- **One-click updater** (`update.bat`) — double-click to update SAR Redact in place on any NHS Windows machine without admin rights. Queries the GitHub releases API, compares with the installed version (`APP_VERSION` in `app.py`), downloads only when a new version is available, backs up current app files to `backup_pre_update_<version>\`, then copies the new files over — leaving `data\`, `uploads\`, and `output\` untouched. Runs via PowerShell only; no admin rights needed. Added to both the standard zip and offline bundle manifests.
- **OCR for scanned pages** — Tesseract integration screens image-only pages automatically; an amber warning banner lists any pages that could not be OCR'd so reviewers know to check them manually before disclosure. (`sar/ocr.py`, `INSTALL.md`).
- **Unscreened-page warnings** — pages that could not be screened (e.g. scanned with no OCR engine available) are highlighted on the review and completion screens so nothing is inadvertently disclosed unreviewed.
- **DOCX / EML / MSG ingestion** — Word documents, Outlook `.eml` emails, and Outlook `.msg` files are converted to PDF for review; email attachments of supported types are extracted and processed alongside the message body.
- **Self-learning detection dictionary** (`sar/dictionary.py`) — SAR Redact learns from reviewer decisions: names that were repeatedly approved for redaction are suggested for the practice dictionary; admins can accept or dismiss suggestions from the Settings page.
- **Intake fields** (`request_date`, `id_verified`, `scope_notes`) — capture date received, identity verification method, and scope notes at SAR creation time. `request_date` starts the statutory 30-day clock; date is shown in the SAR list and feeds the IG report.
- **Article 12 acknowledgment letter** — one-click generation of a UK GDPR Article 12 acknowledgment letter from the review screen, confirming receipt and quoting the statutory deadline.
- **Dashboard deadline urgency strip** — non-archived, non-complete SARs with ≤7 days remaining are highlighted on the dashboard with colour-coded badges (overdue / ≤3 days / ≤7 days).
- **Optional two-person sign-off** (`signoff_by`, `signoff_by_name`, `signoff_at`) — practices can require a second reviewer to sign off before finalising; the sign-off must be by a different person from the allocated reviewer. Configurable in Settings.

---

## [2.4.0] — 2026-06-10

### Added
- **Combined print bundle** — one click on the completion screen merges the cover letter, certificate of redaction, and every redacted document into a single PDF for printing (court-bundle style): contents page listing each document and its starting page, continuous "Page n of N" footer throughout. Bundles over 200 MB are split into at most 5 parts with continuous page numbering across parts. Replaces printing hundreds of individual files one at a time when disclosures are handed over on paper.
- The redaction log is deliberately excluded from the bundle — it records redacted text verbatim and is an internal record; the UI now labels it "Internal — do not disclose".

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
