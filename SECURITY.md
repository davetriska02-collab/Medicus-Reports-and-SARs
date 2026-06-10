# SAR Redact — Security Overview

*This document describes the security architecture of SAR Redact as shipped.
It is referenced by the in-app update checker and the trust pack documents
in `docs/trust-pack/`.*

## Data flows

**All patient data stays on the practice's own machine/network.** There is no
cloud component, no vendor telemetry, and no account with the developer.

The only outbound connection the application ever makes is an optional,
once-per-startup HTTPS GET to `api.github.com` to check for a newer release.
It transmits the app version string in a User-Agent header — no patient data,
no usernames, no machine identifiers beyond ordinary CDN connection logs.
Disable it entirely with the environment variable `UPDATE_CHECK_ENABLED=0`.

During first-time setup, the bootstrap script downloads Python and packages
from python.org / PyPI. Practices behind restrictive proxies can use the
fully offline bundle instead (no internet required at any point).

## Storage

| Data | Location | Notes |
|---|---|---|
| SAR/report records | `data/sarredact.db` | SQLite, WAL mode, transactional writes |
| Uploaded documents | `uploads/` | Originals preserved; page edits keep an untouched copy in `originals/` |
| Redacted output | `output/` | Generated at finalise |
| User accounts | `data/users.json` | Passwords hashed (Werkzeug PBKDF2); never stored in plaintext |
| Audit trail | `data/audit/*.jsonl` | Append-only, monthly files |
| Session secret | `data/.secret_key` | Generated on first run, `chmod 600` where supported |

All JSON writes are atomic (temp file + rename) so a crash cannot truncate a
record. Nightly backups (database snapshot via the SQLite backup API, config,
audit trail, documents) can be pointed at a NAS share with 7-zip retention.

## Authentication & sessions

- Per-user accounts with admin/GP roles; first-run setup creates the admin.
- Login rate limiting: 5 failed attempts per username+IP in 5 minutes locks
  further attempts for the remainder of the window.
- Idle timeout (default 30 minutes, configurable) signs out inactive sessions
  on shared workstations; absolute session lifetime 8 hours.
- Logout is POST-only; cookies are `HttpOnly` + `SameSite=Strict`
  (+ `Secure` when TLS is enabled).
- A corrupt user database locks the application down rather than re-offering
  first-run setup to anyone on the network.

## Request protection

- CSRF tokens are enforced on every mutating request, including login/setup.
- Upload size is capped (1 GB request limit) and zip extraction is bounded
  (entry count, per-entry and cumulative size) against decompression bombs.
- Stored filenames are sanitised and resolved paths are verified to stay
  inside the expected directories (traversal rejected).
- Text extracted from uploaded documents is treated as untrusted and
  HTML-escaped before rendering in the review UI.

## Transport

Default deployment is HTTP on the practice LAN. For server mode, TLS is
supported without admin rights: generate a self-signed certificate with
`tools/generate_cert.py` and install `cheroot`; the launcher detects the
certificate and switches to HTTPS automatically.

## Redaction integrity

Redaction is true content removal — redacted text is deleted from the PDF
content stream and underlying image pixels are erased, not covered with a
drawing. If an approved redaction cannot be placed, the failure is surfaced
to the reviewer, recorded honestly in the redaction log, and blocks
generation of the certificate of redaction. The audit trail never claims a
redaction happened when it did not.

## Audit

An append-only audit trail records logins (including failures), record
views, redaction decisions, finalisation, downloads, exports/imports,
deletions and user administration — with user, timestamp and source IP.
Admins can filter and export it as CSV (`Admin → Audit`).

## Reporting a vulnerability

Contact the developer (see README). Please do not include patient data in
reports.
