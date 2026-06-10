# Clinical Safety Case Report — SAR Redact

*Prepared in accordance with DCB0129 (Clinical Risk Management: its
Application in the Manufacture of Health IT Systems).*

| | |
|---|---|
| System | SAR Redact |
| Clinical Safety Officer | Dr D Triska, GMC 6159481 |
| Safety case status | Living document — update at each release |
| Intended use | Preparation of SAR disclosures and medical reports from GP records by authorised practice staff |

## 1. System definition and clinical context

SAR Redact is an information-handling tool. It does not diagnose, treat,
alert or influence direct clinical decision-making. The clinical risk
surface is **information governance harm**: wrongful disclosure of
third-party or exempt information, or wrongful withholding of the data
subject's own information, and the downstream distress/safeguarding
consequences of either.

A human reviewer remains the decision-maker for every redaction. The system
is decision-support for disclosure preparation, not an autonomous redactor —
although high-confidence detections default to "auto-redact", all are
visible, reviewable and reversible before any output exists.

## 2. Hazard log

Severity/likelihood use the DCB0129 5×5 convention; scores are
post-mitigation (residual).

### H1 — Third-party identifier not detected, disclosed to subject
- **Cause:** unusual name format, OCR noise, identifier type outside pattern set
- **Effect:** third party's presence in the record revealed; potential
  safeguarding consequence (e.g. abuser learns of disclosure by victim)
- **Controls:** layered detection (title-anchored, surname-first, relational,
  known-name, ALL-CAPS patterns; Modulus-11-validated NHS numbers; postcode,
  phone, email patterns); regression-tested against a synthetic corpus with
  published recall; full-page human review with manual draw mode; grouped
  by-name review and context snippets to reduce fatigue; safeguarding terms
  flagged for mandatory human attention
- **Residual:** Severity 4, Likelihood 2 → tolerable with human review;
  detection benchmark monitored per release

### H2 — Approved redaction silently not applied
- **Cause:** candidate without page coordinates whose text cannot be located
- **Effect:** reviewer believes material is redacted; it is disclosed
- **Controls (v2.1+):** redactor returns per-candidate success/failure;
  failures alert the reviewer at finalise, are shown on the completion page,
  recorded in a dedicated REDACTION FAILURES section of the audit log, and
  block generation of the certificate of redaction
- **Residual:** Severity 4, Likelihood 1 → acceptable

### H3 — Redaction box on the wrong location
- **Cause:** ambiguous mapping of detected text to page coordinates
- **Effect:** wrong text obscured; intended text disclosed
- **Controls (v2.2+):** page text built directly from PDF spans with exact
  character offsets — mapping is deterministic; regression test covers
  repeated-text pages
- **Residual:** Severity 3, Likelihood 1 → acceptable

### H4 — Cosmetic redaction recoverable from disclosed file
- **Cause:** overlay-style redaction leaving text in content stream
- **Controls:** PyMuPDF redact annotations applied with content removal and
  image pixel erasure; methodology stated in certificate of redaction;
  output verified by automated test asserting text absence from the
  content stream
- **Residual:** Severity 4, Likelihood 1 → acceptable

### H5 — Subject's own data wrongly withheld
- **Cause:** over-aggressive exclusion/redaction (e.g. subject's address
  variant treated as third-party, or vice versa)
- **Controls:** subject-match exclusions shown to reviewer (not hidden);
  house-number-anchored address matching prevents neighbour conflation;
  rejected/unreviewed items listed in the redaction log so the disclosing
  clinician can verify
- **Residual:** Severity 2, Likelihood 2 → acceptable

### H6 — Loss or corruption of SAR working data
- **Cause:** crash mid-write, concurrent reviewers, disk failure
- **Controls:** transactional SQLite (WAL), atomic file writes, per-SAR
  locks, originals preserved before destructive page edits, nightly
  backups with retention and restore documentation
- **Residual:** Severity 2, Likelihood 1 → acceptable

### H7 — Unauthorised access to record content
- **Cause:** shared workstations, weak credentials, network access
- **Controls:** per-user auth with roles, login rate limiting, idle session
  timeout, CSRF protection, optional TLS, append-only access audit trail
  of every record view
- **Residual:** Severity 3, Likelihood 1 → acceptable (subject to practice
  physical/network controls per DPIA)

### H8 — Statutory deadline missed (process harm)
- **Cause:** workload, lost track of due dates
- **Controls:** automatic 30-day due-date computation, dashboard countdown,
  stop-the-clock with logged reasons, IG report of on-time performance
- **Residual:** Severity 1, Likelihood 2 → acceptable

## 3. Test evidence

- Automated suite (50+ tests) run on every change: redaction integrity
  (H2/H4), span mapping (H3), detection formats and exclusions (H1/H5),
  storage and backup (H6), authentication and audit (H7)
- Detection benchmark (`tools/benchmark_detection.py`) publishing per-category
  recall/precision on a synthetic GP-record corpus — no real patient data is
  used in testing

## 4. Release management

Each release: run the test suite and benchmark, review this hazard log for
new/changed hazards, update residual scores, and record the release in the
README version history. Defects with safety relevance are fixed before
feature work (see H2, introduced and closed in v2.1).

## 5. CSO sign-off

| Release | CSO | Date | Signature |
|---|---|---|---|
| 2.3.0 | Dr D Triska | | |
