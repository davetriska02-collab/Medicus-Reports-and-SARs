# SAR Redact — Toolset Overview

*What the product is and what it does today. For what changed in each release, see [CHANGELOG.md](../CHANGELOG.md). For installation, see [EASY_INSTALL_GUIDE.md](../EASY_INSTALL_GUIDE.md) or [INSTALL.md](../INSTALL.md).*

---

## 1. What SAR Redact Is

SAR Redact is a Flask web application that helps GP practices produce safe, compliant disclosures in response to Subject Access Requests under UK GDPR Article 15. It runs entirely on practice hardware — a single Windows PC or a small LAN server — and no patient data ever leaves the building. It requires no admin rights to install or update, deploys by unzipping a folder, and can run on a standard locked-down NHS Windows machine without IT involvement. Multiple staff (GPs, administrators, IG leads) share a single installation through their browsers.

---

## 2. Document Intake

### Supported formats

| Format | Notes |
|--------|-------|
| PDF | Native; rendered page-by-page |
| TIF / TIFF | Converted to PDF on ingest |
| RTF | Converted to PDF on ingest |
| TXT | Converted to PDF on ingest |
| DOCX | Word documents converted to PDF |
| EML | Outlook email files; body and attachments extracted |
| MSG | Outlook message files; body and attachments extracted |
| PNG / JPG | Images converted to PDF |
| ZIP | Archive extracted; supported files inside processed individually |
| CDAX | GP2GP clinical documents converted to PDF |

Email files (EML, MSG) have their attachments extracted and processed alongside the message body if the attachment type is itself supported.

ZIP files are bounded: maximum 1 GB per upload request, 4 GB uncompressed total, 2,000 entries, and 800 MB per individual entry. These caps prevent decompression-bomb attacks.

### Intake fields

When creating a new SAR, the reviewer records:

- **Request date** — starts the statutory 30-day clock; shown in the SAR list and feeds the IG turnaround report.
- **ID verification** — the method used to confirm the data subject's identity.
- **Scope notes** — free-text notes about what is in scope for the disclosure.

---

## 3. Detection

### Name detection

The name detector handles several real-world GP record formats:

- Titled forms: `Dr Jane Smith`, `Mr John Smith`
- Surname-first: `SMITH, John`
- ALL-CAPS: `JOHN SMITH`
- Prefixes: `Mc`, `Mac`, `O'`, `De`, `Van`

Confidence weighting is applied across formats. A cross-line false-positive fix ensures names are never matched across a line break.

### NHS numbers

NHS numbers are validated using the Modulus-11 check digit algorithm, not just by pattern. Only numbers that pass the check are raised as candidates.

### Other personal data

The detector also identifies UK addresses, telephone numbers, and email addresses (including `@nhs.net` and `@nhs.uk` NHSmail addresses).

### OCR for scanned pages

When Tesseract OCR is installed, SAR Redact automatically screens image-only pages (Lloyd George cards, scanned hospital letters, handwritten notes). Pages that could not be screened — because OCR is unavailable or a page failed — are flagged with an **amber warning banner** on the review screen and the completion screen, so reviewers know those pages require manual inspection before disclosure.

### Self-learning practice dictionary

SAR Redact learns from reviewer decisions. Names that are repeatedly approved for redaction are surfaced as suggestions; admins can accept or dismiss them from the Settings page. Accepted entries are added to a practice-specific dictionary that is consulted on subsequent SARs.

### Detection benchmark

A 200-document synthetic GP-record corpus gives **99.4% recall and 100% precision on names** (born-digital text). This benchmark does not cover handwritten or scanned records, where OCR quality is the limiting factor.

---

## 4. Review Experience

### Candidate list

Redaction candidates are **grouped by name** across all uploaded files, with a count badge showing the total number of occurrences. Bulk actions ("Redact all N occurrences" / "Keep all") are available per group.

Each candidate shows a ±70-character context snippet from the surrounding text so reviewers can assess the hit without opening the PDF.

### Navigation

Keyboard shortcuts are available throughout the review screen:

- **J** — next candidate
- **K** — previous candidate
- **S / ←** — keep (suppress) candidate

### Presence and allocation

A live chip shows which other users currently have the same SAR open. If a SAR is already allocated to someone else, an allocation warning appears. This prevents two reviewers from making conflicting decisions simultaneously.

### Before/after preview

On the completion screen, a side-by-side modal shows the original page alongside the redacted version, so the reviewer can confirm the result before generating disclosure documents.

### Draw-mode manual redaction

Reviewers can draw freehand redaction boxes on any page to cover items the automatic detector did not identify. These are applied as true content removals, not cosmetic overlays.

### Two-person sign-off (optional)

Practices can require a second reviewer to sign off before a SAR is finalised. The sign-off must be by a different person from the allocated reviewer. This setting is configurable in Settings.

---

## 5. True Redaction

Redaction in SAR Redact is not a visual overlay. When a SAR is finalised:

- Text is **removed from the PDF content stream** — it cannot be recovered by copying and pasting from the output PDF.
- Image pixels on scanned pages are **erased** — not painted over.

If an approved redaction cannot be placed (for example, the text position could not be resolved in the PDF structure), that failure is:

- Listed explicitly in a banner visible to the reviewer.
- Recorded in the redaction log.
- Used to **block generation of the certificate of redaction** until the failure is resolved.

The redaction log never claims a redaction succeeded when it did not.

---

## 6. Disclosure Outputs

SAR Redact generates the following documents:

| Document | Trigger | Notes |
|----------|---------|-------|
| Article 12 acknowledgment letter | One-click from review screen | Confirms receipt and states the statutory deadline |
| Article 15 cover letter | One-click on completion screen | UK GDPR Article 15 disclosure letter |
| Certificate of redaction | One-click on completion screen | Includes DPA 2018 exemption schedule with codes and per-category counts; refused while any redaction failures exist |
| Combined print bundle | One-click on completion screen | Merges cover letter + certificate + all redacted documents into 1–5 PDFs; includes a contents page and continuous "Page n of N" numbering throughout |

The **redaction log is deliberately excluded from the disclosure bundle**. It records redacted text verbatim and is an internal record only. The UI labels it "Internal — do not disclose".

Bundles over 200 MB are automatically split into at most 5 parts with continuous page numbering across parts.

---

## 7. Compliance and Oversight

### IG dashboard

The IG report (`Admin → IG`) shows:

- Turnaround time against the 30-day statutory deadline for every completed SAR.
- Monthly volumes.
- Per-SAR on-time flags.
- CSV export for ICO returns.

### Deadline urgency strip

Non-archived, non-complete SARs with 7 days or fewer remaining are highlighted on the dashboard with colour-coded badges: overdue, ≤3 days, and ≤7 days.

### Audit trail

Every significant action is recorded in an append-only JSONL audit trail: logins (including failures), record views, redaction decisions, finalisation, downloads, exports, deletions, and user administration. Each entry records the user, timestamp, and source IP. Admins can filter and export the full trail as CSV (`Admin → Audit`).

### Exemption codes

The certificate of redaction includes DPA 2018 Schedule 2 and Schedule 3 exemption codes with per-category line-item counts, giving the practice a structured basis for withholding specific data categories.

### Trust pack

The `docs/trust-pack/` folder contains ready-to-use compliance evidence:

- **DPIA** — pre-filled Data Protection Impact Assessment template; practice completes and signs the `[PRACTICE]` sections.
- **DCB0129 clinical safety case** — eight hazards (H1–H8) with severity, likelihood, residual risk scores, mitigations, and design links.
- **DSPT mapping** — ten DSPT data security standards cross-referenced to product controls.
- **SECURITY.md** — full security architecture document.

### Automated compliance-document review

A weekly GitHub Actions workflow diffs recent code changes against the DPIA and clinical safety case, then opens GitHub issues when those documents may need updating to reflect code changes.

---

## 8. Deployment and Operations

### Installation paths

SAR Redact requires no admin rights on any path:

| Path | How |
|------|-----|
| Standard (Python on PATH) | Extract zip, double-click `start_server.bat` |
| Locked NHS machine (no Python) | `start_server.bat` uses PowerShell to download a portable Python 3.12 runtime into the app folder — no installer, nothing written to Program Files or the registry |
| Offline / proxy-blocked | Build an offline bundle (`tools/build_offline_bundle.py`) containing Python and all Windows wheels (~20 MB zip); no internet needed at any point. A `--tls` variant includes HTTPS support |
| Central server | Run `install_as_server.bat` on one machine; registers a per-user Startup item with an automatic restart-on-crash wrapper; writes `CONNECT.txt` with the LAN address for staff |

### Updates

Double-clicking `update.bat` queries the GitHub releases API, compares with the installed version, downloads a new release only when available, backs up current app files to `backup_pre_update_<version>\`, then copies the new files over. The `data\`, `uploads\`, and `output\` folders are never touched. No admin rights needed.

SAR Redact also checks for updates on each server start and displays a banner when a newer version is available.

### HTTPS

HTTPS is supported without admin rights. Generate a self-signed certificate with `tools/generate_cert.py` and install `cheroot`; the launcher detects the certificate and switches to HTTPS automatically.

### Nightly backups

A nightly backup runs automatically: SQLite database snapshot, configuration, audit trail, and documents are packaged into a date-stamped zip. Seven copies are retained (rolling). The backup folder is configurable in Settings and can point to a NAS share or synced folder.

### Health endpoints

- `/healthz` — machine-readable health check.
- `/admin/status` — operational status: uptime, backup status, job counts.

### Demo mode

An admin button creates a fully synthetic 4-page GP record with planted PII (names in multiple formats, valid Modulus-11 NHS numbers, addresses, phone numbers, NHSmail addresses). This lets staff walk through the full workflow without using real patient data. The subject is unmistakably labelled "DEMO PATIENT — SYNTHETIC DATA". A second click returns the same demo SAR rather than creating duplicates.

---

## 9. Security

**All patient data stays on the practice's own machine or network.** There is no cloud component and no vendor telemetry.

| Mechanism | Detail |
|-----------|--------|
| Local-only processing | No patient data is transmitted externally under any circumstances |
| Single outbound call | Once-per-startup HTTPS GET to `api.github.com` to check for updates; transmits only the app version string. Disable entirely with `UPDATE_CHECK_ENABLED=0` |
| CSRF protection | Enforced on every mutating request, including login and setup |
| Login rate limiting | Five failures per username+IP in five minutes locks further attempts for the remainder of the window |
| Idle timeout | Default 30 minutes, configurable; absolute session lifetime 8 hours |
| Password storage | PBKDF2 via Werkzeug; never stored in plaintext |
| Append-only audit | The audit trail cannot be edited; records are JSONL append-only monthly files |
| Atomic writes | All JSON and config writes use temp-file-then-rename, so a crash cannot corrupt a record |
| Path traversal protection | Stored filenames are sanitised and resolved paths are verified to stay inside expected directories |
| Upload bounds | 1 GB per upload; ZIP extraction bounded against decompression bombs |
| Session cookies | `HttpOnly` + `SameSite=Strict`; `Secure` when TLS is active |
| Corrupt user database | Locks the application rather than re-offering first-run setup to anyone on the network |

---

## 10. Where to Go Next

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Quick start, supported formats, version history |
| [EASY_INSTALL_GUIDE.md](../EASY_INSTALL_GUIDE.md) | Step-by-step plain-English install guide for non-technical staff |
| [INSTALL.md](../INSTALL.md) | Technical install reference: server mode, HTTPS, OCR, offline bundle |
| [SECURITY.md](../SECURITY.md) | Security architecture, data flows, threat model |
| [CHANGELOG.md](../CHANGELOG.md) | Full version history (v1.0.0 → v2.5.0) |
| [docs/trust-pack/](trust-pack/README.md) | DPIA, DCB0129 clinical safety case, DSPT mapping |
