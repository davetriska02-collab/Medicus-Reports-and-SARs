# SAR Redact v2 — Code Review

*Reviewed: June 2026 · Version reviewed: 2.0.5*

This review covers the full codebase: Flask backend (`app.py`, ~1,100 lines), the
`sar/` detection and processing package (~2,300 lines), the vanilla-JS frontend
(~1,000 lines), and the zero-admin Windows bootstrap (`start_server.bat`).

---

## 1. What is genuinely good

These are worth calling out because they should be **preserved** through any refactor.

1. **The zero-admin install strategy is the product's moat.** Downloading the
   embeddable Python zip via PowerShell, patching `._pth`, bootstrapping pip — no
   registry, no Program Files, no admin. This is exactly the right approach for
   NHS lockdown machines and most competitors require an MSI or a cloud account
   (which triggers a DPIA and IG review). Keep this sacred.

2. **True redaction, not cosmetic redaction.** Using PyMuPDF redact annotations
   with `apply_redactions(images=PDF_REDACT_IMAGE_PIXELS)` actually removes text
   from the content stream and scrubs image pixels. Many commercial tools have
   shipped "black box drawn over text" failures (the Manchester Arena inquiry
   leak being the famous example). This is a genuine differentiator — market it.

3. **Domain depth.** Modulus-11 NHS number validation, DPA 2018 Schedule 2/3
   exemption codes in the redaction log, stop-the-clock deadline tracking,
   staff-context exclusion ("Practitioner: Dr X" → excluded as staff), GP2GP
   CDA/CDAX parsing, safeguarding and sexual-health flag categories that are
   *never* auto-redacted. A generic redaction vendor has none of this.

4. **Sensible security baseline for a v2**: hashed passwords (Werkzeug), CSRF
   tokens on mutating API routes, `HttpOnly`/`SameSite=Strict` cookies, path
   traversal rejection in `_resolve_path`, `secure_filename` everywhere,
   role-based access (admin vs GP), first-run setup flow.

5. **No heavyweight dependencies.** Four pip packages, no database server, no
   node build step. The frontend is server-rendered Jinja + ES modules. This is
   the right call for the deployment constraint and keeps the bundle small.

6. **Audit artefacts**: the redaction log PDF lists every decision with category,
   confidence, reason, method and exemption. The `.sarpack` export/import format
   with manifest versioning is a smart portability mechanism.

---

## 2. Issues, by severity

### 2.1 Critical (clinical-safety / data-integrity relevant)

**C1. Silent redaction failure when a candidate has no coordinates.**
`sar/redactor.py` falls back to `page.search_for(c.text)` when bbox is all
zeros. If the search finds nothing (OCR'd text never exactly matches, hyphenated
line breaks, ligatures), **the item is not redacted but the redaction log still
lists it as "applied"**. For a DCB0129-managed product this is the worst failure
mode: the audit trail asserts something that didn't happen, and third-party PII
goes out the door. Fix: `apply_redactions` must return a per-candidate
applied/failed result; failures must surface in the UI before download and be
recorded honestly in the log.

**C2. Non-atomic JSON writes can corrupt SAR state.**
`_save()` in `app.py`, `_save_users()`, `save_report()` all write directly to the
target file with `open(path, "w")`. A crash, full disk, or two concurrent writers
(the whole point of LAN multi-user) mid-write leaves truncated JSON → that SAR
fails to load forever (`_load_all` prints a warning and drops it). Fix: write to
`tmpfile` + `os.replace()` (atomic on Windows and POSIX), and take the per-SAR
lock during serialisation. Longer term: SQLite (see roadmap).

**C3. Lost updates between concurrent reviewers.**
The store lock (`_ar_lock`) protects the *dict*, not the *objects*. Two GPs
reviewing the same SAR: A updates candidate 1, B updates candidate 2, both call
`_save(sar)` — last writer wins at file level, but worse, both mutate the same
in-memory object with no candidate-level lock, and `_to_dict` can serialise a
half-mutated state. Also no UI presence indicator, so two people can
unknowingly review the same document. Fix: per-SAR `threading.Lock`, plus a
`last_modified` precondition (ETag-style) on mutating API calls so a stale
client gets a 409 instead of clobbering.

**C4. `delete-page` destructively rewrites the original uploaded file.**
`doc.save(pp, incremental=False)` overwrites the source document. The original
record as received is evidence; under ICO scrutiny you want to show what came in
vs what went out. Originals should be immutable; page exclusions should be
applied at finalise time.

**C5. No upload size limit and no zip-bomb guard.**
`MAX_CONTENT_LENGTH` is unset (unbounded request body) and `_extract_zip`
extracts whatever is inside with no cumulative size cap or entry limit. On a
shared central server one malformed upload can fill the disk and take the
service down for the whole practice.

### 2.2 High

**H1. Detection misses the most common name format in GP records: `SMITH, John`.**
All name patterns require `[A-Z][a-z'-]+` Title-Case. ALL-CAPS surnames
(ubiquitous in EMIS/SystmOne headers, Docman, hospital letters: "SMITH, John",
"Re: JONES, Mary") and `Surname, Forename` ordering are not matched at all.
Also `Mc`/`Mac`/internal-capital names ("McDonald", "DeSouza") fail the
`[a-z'-]+` tail. This is the single biggest detection-quality win available.

**H2. `map_text_to_spans` is fragile and quadratic.**
It re-`find`s each span's text inside the page text; repeated short spans (page
furniture, "Dr", dates) can match the wrong occurrence, producing a redaction
box on the **wrong location**. The `sort=True` dict extraction and `get_text("text")`
orderings are not guaranteed to agree either. PyMuPDF can do this natively:
`page.search_for(needle, clip=...)` or character-level `rawdict` offsets give
exact, per-occurrence rectangles. Given C1, wrong-location boxes are also a
disclosure risk, not just a cosmetic one.

**H3. No access audit trail.**
For health data, "who viewed which patient's record and when" is a Caldicott /
DSPT expectation and every serious procurement question asks for it. Currently
logins and record views are not logged at all. An append-only `audit.log`
(user, action, SAR id, timestamp, IP) is cheap to add and is a tender checkbox.

**H4. Login endpoint has no rate limiting or lockout**, and the login form is
explicitly exempted from CSRF (login-CSRF is a real if minor attack). `/logout`
is a GET (can be triggered cross-site). On a LAN with shared machines, password
brute-force against `POST /login` is the realistic attack. A tiny in-memory
sliding-window limiter (5 attempts / 5 min / username+IP) suffices.

**H5. Re-reading `users.json` from disk on *every request*.**
`load_user` + `users_file_exists` each do file I/O per request, and every page
image request on the review screen is a request. With 8 waitress threads and a
reviewer paging through a 400-page Lloyd George record this is thousands of
needless reads. Cache with an mtime check.

**H6. Repeated document opens make review sluggish on big records.**
`get_full_page_text` opens/closes the PDF once per page (so `detect_pii` over an
N-page doc opens the file N+1 times); `render_page_image` opens the doc per HTTP
request and re-renders the PNG every time, with OCR re-running per call on
scanned pages. An LRU of open `fitz.Document` handles plus a rendered-page PNG
cache (disk, keyed by file mtime + page + zoom) would make page-turning feel
instant and cut server CPU dramatically — this matters once one box serves the
whole practice.

**H7. Zero automated tests.**
There is no test suite at all. The detection logic is exactly the kind of code
that regresses invisibly (a regex tweak silently stops matching postcodes). A
pytest suite with a synthetic-document golden corpus (no real patient data) and
a CI run on push is foundational for everything else in the roadmap, and
"detection regression suite" is also a DCB0129 hazard-mitigation you can cite.

### 2.3 Medium

- **M1.** SSE job queues (`_job_queues`) leak if the client never attaches or
  disconnects mid-stream; entries are only popped on completion through a
  connected stream. Add TTL cleanup.
- **M2.** `users_file_exists()` returning False redirects *every* route to
  `/setup` — but a corrupted/empty `users.json` then locks everyone out and lets
  the next visitor create a fresh admin. Treat unreadable-but-present file as
  fatal, not as "no users".
- **M3.** `report_review` and `report_store` persist **absolute** `pdf_files`
  paths — same bug the SAR side already fixed with `_resolve_path`/migration.
  Moving the install folder breaks all reports.
- **M4.** `is_subject_match` address heuristic (`70% word overlap`) will exclude
  third-party addresses that share street/town words with the subject —
  i.e. neighbours and family at similar addresses, which is exactly the
  third-party data SARs go wrong on. Needs house-number anchoring.
- **M5.** `FULL_NAME_PATTERN` (two title-cased words, one in a known-name list)
  fires on clinical eponyms ("Parkinson Disease" — `parkinson` isn't in
  NOT_NAMES, "Barrett Oesophagus") and drug/place pairs. Confidence 0.65 means
  flag-not-auto, which is correct, but the noise level drives reviewer fatigue —
  measure precision on a corpus and tune.
- **M6.** Hard-coded practice-specific surnames in `name_detector.py`
  (`"triska"`, `"overington"`, …) should move into the configurable staff list /
  a per-practice supplementary name list, or competitors will rightly say it's
  hand-tuned to one surgery.
- **M7.** `SESSION_COOKIE_SECURE=False` and plain HTTP on the LAN. Acceptable
  short-term inside an NHS network, but credentials and patient data transit in
  cleartext; see roadmap for the no-admin TLS option.
- **M8.** `secure_filename()` collision: two uploads named differently can map to
  the same safe name within a SAR and silently overwrite (`f.save(fp)`); suffix
  with a counter.
- **M9.** Werkzeug default `pbkdf2` is fine, but no password complexity beyond
  length ≥8 and no forced rotation of the first admin password if the bundle is
  pre-provisioned.
- **M10.** `_csrf_protect` compares with `compare_digest` but skips `login`,
  `setup` entirely rather than enforcing the form token that templates already
  render.

### 2.4 Low / polish

- `_to_dict`/`_load_all` hand-rolled (de)serialisation will drift from the
  dataclasses; derive it (`dataclasses.asdict` + enum handling) or define a
  schema once.
- `format_date` imports `platform` per call; `name_detector` has duplicate
  entries in its sets; `pdf_parser` uses `__import__("os")` despite importing
  `os` at top.
- 404 handler renders `403.html` — confusing during support calls.
- `print()` for logging throughout — switch to `logging` with a rotating file
  handler so a central server has a supportable log.
- `requirements.txt` is unpinned (`flask>=3.0`) while the bat installs
  unpinned too — a bad PyMuPDF release will brick fresh installs; pin exact
  versions and ship a `constraints.txt`.
- The dashboard, review and reports templates each redefine similar modal/JS
  helpers inline; consolidate into `static/js/`.

---

## 3. Architecture assessment for the central-server goal

The good news: **the architecture is already 80% a central server.** Waitress on
`0.0.0.0`, multi-user auth, roles, allocation workflow — the LAN deployment in
the README is real. What's missing is the difference between "works on a LAN"
and "is a dependable shared service":

| Concern | Today | Needed for central server |
|---|---|---|
| Storage | JSON files + full in-memory load at boot | SQLite (stdlib, zero-install) with WAL; survives crashes, scales to years of SARs |
| Write safety | Non-atomic, last-writer-wins | Atomic writes now; row-level updates + optimistic concurrency later |
| Transport | Plain HTTP | TLS via pip-installable server (waitress can't terminate TLS) |
| Identity of server | "Whatever PC ran the bat" | Pinned host, auto-start at logon (no admin: Startup folder / `schtasks /sc onlogon` works per-user), static port, documented `http(s)://hostname:port` |
| Resilience | None | Health endpoint, scheduled backup of `data/`, log rotation, restart-on-crash wrapper in the bat |
| Performance | Re-open/re-render per request | Doc-handle LRU + page-image cache |
| Observability | stdout prints | `logging` + access audit log + simple `/admin/status` page |

None of these require admin rights. SQLite is in the stdlib; TLS can be done by
swapping waitress for `cheroot` (CherryPy's server, pure pip, supports HTTPS
with a bundled self-signed cert) while keeping the same Flask app; auto-start
uses the per-user Startup folder.

The full prioritised plan is in [`IMPROVEMENT_PLAN.md`](IMPROVEMENT_PLAN.md).
