# SAR Redact — Repository Audit & Improvement Plan

**Audited at:** v2.5.2 · **Report updated through:** v2.6.1 · **Date:** 2026-06-11

This audit was produced by a multi-stream review (backend, frontend/deployment/dependencies,
tests/data-flow) with every finding grounded in `file:line` evidence. Items marked
**✅ FIXED in 2.5.3** were actioned immediately after the audit; the rest form the
forward plan.

---

## Executive Summary

**Health grade: C+** (the redaction *core* is B+/A−; the surrounding web and
deployment tiers pull the overall grade down).

Strong safety engineering — honest redaction-failure reporting, thorough CSRF,
rate limiting, zip-bomb caps, atomic writes, append-only audit — sits alongside
risk that accumulated faster than test coverage during eight rapid feature
releases. The audit found one live Critical regression on the core screen, a
silent data-loss race on the review path, and several deployment/compliance gaps
that matter precisely because the operators are non-technical and the data is
whole medical records.

**Top 3 risks (at time of audit)**
1. **Live Critical bug** — orphaned `<script>` in `review.html` broke the file
   selector, viewer bootstrap, and admin gating. **✅ FIXED in 2.5.3.**
2. **Silent lost-update race** — concurrent reviewers can overwrite each other's
   redaction decisions. *Open — Milestone 1.*
3. **Plaintext session cookies by default + no data retention.** Cookie security
   **✅ FIXED in 2.5.3**; retention policy *open — Milestone 2.*

**Top 3 opportunities**
1. A template/smoke test tier (the Critical had no test that could catch it).
   **✅ DONE in 2.5.3** (`tests/test_html_templates.py`).
2. Run tests before releasing + the detection benchmark in CI. Release gate
   **✅ DONE in 2.5.3**; benchmark-in-CI *open — Milestone 0.*
3. One escaping helper + security headers. **✅ DONE in 2.5.3.**

---

## Repo Map

**Purpose:** On-premise Flask app for NHS GP practices to redact PII from medical
records before disclosing Subject Access Requests under UK GDPR. Flow: upload →
auto-detect PII → human review/approve → true redaction → disclosure documents +
audit trail.

**Stack:** Python 3.12 · Flask 3.1.2 · PyMuPDF 1.26.4 · Waitress/cheroot · SQLite
(WAL) · vanilla ES-module JS, no build step · Jinja2. Windows `.bat` deployment
with embedded Python, no admin rights.

**Shape (measured):** `app.py` ~1,890 lines / **91 routes** · `sar/` 30 modules,
~5,000 lines (well decomposed) · 17 templates · ~1,460 lines of JS · 153 tests.

**Architecture:** Monolithic controller (`app.py`) over a clean domain package
(`sar/`). The domain layer is the strong part; the controller is the god file.
Substantial business logic also lives in inline `<script>` blocks across 10
templates, parallel to the ES-module JS — the root of the Critical and XSS
findings.

**Surprise:** the redaction *core* (`sar/redactor.py`, 100% covered, honest
failure handling) is markedly more mature than the surrounding web tier.

---

## Audit Findings (severity-ordered)

### CRITICAL
- **C1 — Orphaned script block breaks the review screen.** `review.html:278–285`.
  Six globals rendered as text instead of executing; `main.js` could not populate
  the file selector or bootstrap the viewer. Regression from commit `fb6cb02`,
  undetected because nothing tested template rendering. **✅ FIXED in 2.5.3** +
  regression test added.

### HIGH
- **H1 — Lost-update race on `sar.candidates`.** Mutating routes do
  `_get → mutate → _save`; the per-SAR lock covers only the DB write, not the
  read-mutate window. Concurrent reviewers can silently overwrite decisions.
  **✅ FIXED in 2.5.4** (all mutating routes now hold the per-SAR RLock across the
  full read-mutate-save sequence via `_mutate` context manager; `_lock_for` uses
  `threading.RLock` to prevent self-deadlock).
- **H2 — No HTTP security headers.** **✅ FIXED in 2.5.3** (`_security_headers`
  after-request hook).
- **H3 — Session cookies plaintext by default.** **✅ FIXED in 2.5.3**
  (auto-secure under TLS, `SAR_COOKIE_SECURE` for proxy TLS, `session.permanent`).
- **H4 — Stored XSS on the Settings page.** `staff.html` built `innerHTML` from
  admin-entered names without escaping. **✅ FIXED in 2.5.3** (`esc()` + `data-`
  attribute handlers).
- **H5 — `.sarpack` import path traversal.** `_do_import` uses `sd["id"]` from the
  uploaded file directly as a directory name; a crafted id can write outside
  `UPLOAD_DIR` (admin-gated, but a code-overwrite path).
  **✅ FIXED in 2.5.4** (id validated against `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`
  and `os.path.realpath` containment check; rejected ids are audit-logged).
- **H6 — No integrity verification on downloaded code.** `update.bat` xcopies a
  release zip over the live install with no checksum and no rollback;
  `start_server.bat` fetches Python + `get-pip.py` unverified.
  **✅ FIXED in 2.5.4** (`update.bat` downloads and verifies `SHA256SUMS`, auto-restores
  backup on install failure; `start_server.bat` pins and verifies the Python embed
  SHA-256; `release.yml` generates `SHA256SUMS` and attaches it to every release).
- **H7 — No GDPR retention / auto-deletion.** Completed SARs (full medical records)
  are deleted only by manual admin action; the DPIA flags this as unfinished.
  **✅ FIXED in 2.6.0** (`sar/retention.py` background sweep; 180-day default;
  configurable/disable-able in Settings; every deletion audited).
- **H8 — Releases published without running tests.** **✅ FIXED in 2.5.3**
  (`pytest` gate added to `release.yml`).
- **H9 — Unpinned deps on the system-Python install path.** **✅ FIXED in 2.5.3**
  (venv path now pins flask/waitress/striprtf/pymupdf).

### MEDIUM
- Detection benchmark runs nowhere automatically — 99.4%/100% can regress
  silently. **✅ FIXED in 2.6.1** (`tests.yml` benchmark gate step added; `--ci`
  flag exits non-zero if NAME recall < 0.97 or precision < 0.99).
- ~~`redetect_sar` double-saves the same object from request + background thread →
  possible corrupt snapshot.~~ **✅ FIXED in 2.6.0** (subject-detail mutation + initial
  save now under `_mutate` before thread start; background thread's final save also
  under `_mutate`; no sync save after thread start).
- God file / god function — `app.py` 91 routes; `detect_pii` 277 lines,
  `detect_names` 185 lines. *Open — Milestone 3.*
- ~~Double OCR-probe per page re-opens the PDF (`detector.py:275` + `:286`).~~
  **✅ FIXED in 2.6.0** (pre-computed `_ocr_needed` dict used in both places).
- CI actions tag-pinned not SHA-pinned; release workflow has `contents: write`.
  **✅ FIXED in 2.6.1** (SHA pins confirmed present in all three workflow files;
  `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4` and
  `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5`).
- TLS key 10-year validity; `chmod 0o600` no-ops on Windows → key world-readable.
  **✅ FIXED in 2.6.1** (validity reduced to 825 days; `icacls` added for Windows).
- `server_loop.bat` restarts every 5s with no backoff and no crash-log capture.
  **✅ FIXED in 2.6.1** (timestamped log, escalating backoff 5s/15s/60s, crash-loop
  warning after 5 consecutive rapid crashes).

### LOW
- `_presence` dict leaks one key per deleted SAR. **✅ FIXED in 2.6.0** (cleanup
  present in `_delete_sar_data`; confirmed and verified at 2.6.1 audit sweep).
- Several `complete.html` fetches lack `.catch()`. **✅ FIXED in 2.6.1**
  (`saveNotes` shows red "Could not save"; `archiveSar`, `deleteSar`,
  `resumeClock` alert with error message).
- Review UI accessibility (no ARIA on the redaction overlay, no `aria-live`).
  **✅ FIXED in 2.6.1** (`role="application" aria-label="Redaction overlay"` on
  SVG; `aria-live="polite"` on candidate list container).
- Password policy length-only. *Open.*
- Stale docs (`~20 MB` bundle is really ~40–60 MB; install-time "2 min" vs
  "3–8 min"). **✅ FIXED in 2.6.1** (INSTALL.md, README.md, EASY_INSTALL_GUIDE.md
  all updated to "~40 MB" / "3–8 minutes").

### Strengths (preserve these)
Redaction-failure honesty (never overstates) · `redactor.py` 100% covered ·
thorough CSRF (before-request + `compare_digest` + fetch patch) · zip-bomb caps ·
atomic writes + `os.replace` · sliding-window login rate-limit · corrupt-users
lockdown · secret-key generation (`os.urandom(32)`, persisted) · the
failure-triage/override workflow is thoroughly tested end-to-end · `.gitignore`
excludes all patient data · rotating logs.

### Test posture (measured at audit)
61% overall; `app.py` 55%, `pdf_parser.py` 26%, `ocr.py` 31%,
`report_templates.py` 23% (custom-template CRUD untested), settings CRUD
untested. **Absent:** template/JS tests (now partially addressed),
browser e2e, concurrency tests despite WAL being a headline feature. Two
urgency-strip tests asserted only `status==200` — **✅ rewritten in 2.5.3** to
assert real exclusion behaviour.

---

## Improvement Strategy — five themes

1. **Close the test blind spots that hide whole bug classes** (templates,
   concurrency, benchmark-in-CI). *Done when:* CI fails on unbalanced template
   tags ✅, on a concurrent-write regression, and on detection recall below a
   floor.
2. **Make the web tier as safe as the redaction core** (headers ✅, escaping ✅,
   traversal guard, lost-update fix).
3. **Harden the supply chain end-to-end** (checksum-verify downloads, pin all
   install paths ✅, test-before-release ✅, SHA-pin actions).
4. **Honour the compliance promises the docs already make** (retention policy;
   session-lifetime ✅).
5. **Tame the monolith — carefully** (blueprints; decompose `detect_pii`).
   Deliberately last: highest effort, lowest immediate risk, and unsafe to churn
   before the test net exists.

**Not fixing now:** full WCAG 2.1 AA (real but not the current risk profile);
wholesale inline-script → ES-module migration (do opportunistically); replacing
SQLite (correct for the single-server target).

---

## Task Plan

**⚡ Quick wins** — **all ✅ DONE in 2.5.3:** C1 fix, security headers, release
test-gate, venv pins, the template smoke test + urgency-test rewrite, settings
XSS escaping, secure-cookie/session-lifetime.

**Milestone 0 — Safety net (remaining)**
- M0.1 (M): broaden template tests to assert key globals are defined after render.
- M0.2 (M): concurrency test proving the H1 race, then guard it.
- ~~M0.3 (S): wire `tools/benchmark_detection.py` into CI with a recall/precision floor.~~ **✅ FIXED in 2.6.1**

**Milestone 1 — Critical & High correctness/security (remaining)**
- ~~M1.1 (M): fix H1 lost-update — re-read-under-lock or optimistic version check.~~ **✅ FIXED in 2.5.4**
- ~~M1.3 (S): H5 — validate `sd["id"]` on `.sarpack` import (realpath-contained).~~ **✅ FIXED in 2.5.4**
- ~~M1.4 (M): H6 — checksum-verify downloads; auto-restore backup on update failure.~~ **✅ FIXED in 2.5.4**

**Milestone 2 — High-leverage**
- ~~M2.1 (L): H7 — configurable retention + scheduled deletion of completed SARs.~~ **✅ FIXED in 2.6.0**
- ~~M2.2 (M): coverage for `app.py` admin/user routes and `pdf_parser.py`.~~ **✅ DONE in 2.6.0** (`tests/test_admin_users.py`, `tests/test_pdf_parser.py`)
- ~~M2.3 (S): fix `redetect_sar` double-save; de-duplicate the per-page OCR probe.~~ **✅ FIXED in 2.6.0**

**Milestone 3 — Quality & polish**
~~SHA-pin CI actions~~ ✅ · ~~`server_loop.bat` backoff + crash log~~ ✅ ·
~~TLS validity + Windows `icacls`~~ ✅ · ~~`.catch()` on `complete.html` fetches~~ ✅ ·
~~doc corrections~~ ✅ · ~~`_presence` leak~~ ✅ · ~~accessibility wins~~ ✅ ·
begin blueprint split of `app.py` *(remaining — high churn, scheduled separately)*.

**Remaining plan (after 2.6.1)**
- M0.1: broaden template tests to assert key globals are defined after render.
- M0.2: concurrency test proving the H1 race, then guard it.
- Blueprint split of `app.py` (91 routes into Flask blueprints — deliberately
  last due to high churn; requires solid test net to be safe).
- Password-complexity policy (length-only policy is a low risk vs. above work).
- Full WCAG 2.1 AA (real but not the current risk profile).

---

## Open Questions
1. Does branch protection require `tests.yml` to pass before a tag is pushed?
2. What completed-SAR retention does the practice IG policy require, and should
   deletion be automatic or admin-confirmed?
3. Is HTTPS expected via cheroot or a reverse proxy? (Affects the cookie config.)
4. Is `scrypt` available on the oldest target NHS Windows Python builds?
5. Should `/healthz` expose `APP_VERSION` unauthenticated, or be tightened?
