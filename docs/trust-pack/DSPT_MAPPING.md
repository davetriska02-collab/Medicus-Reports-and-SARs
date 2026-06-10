# DSPT Evidence Mapping — SAR Redact

How SAR Redact's controls support a GP practice's **Data Security and
Protection Toolkit** submission. This maps product features to the DSPT's
ten data security standards (NDG standards); the practice remains
responsible for organisational items (training, policies, physical security).

> Evidence shortcuts: `Admin → Audit` (access trail + CSV),
> `Admin → IG` (SAR turnaround report + CSV), `Admin → Status` (backup
> status), `SECURITY.md`, `docs/trust-pack/DPIA.md`,
> `docs/trust-pack/CLINICAL_SAFETY_CASE.md`.

## Standard 1 — Personal confidential data (need-to-know)
- Per-user accounts with admin/GP roles; SAR allocation to a named reviewer
- Append-only audit of every record view, decision, download and deletion,
  with user, timestamp and IP — exportable as CSV for spot-check audits
- Presence indicator and allocation warnings reduce casual opening of
  records assigned to others

## Standard 2 — Staff responsibilities
- Named SAR officer configured in Settings and shown on disclosure
  documents; redaction log records who finalised
- **[PRACTICE]**: include SAR Redact in induction/leaver checklists
  (account creation/deletion is admin-controlled and audited)

## Standard 3 — Training
- **[PRACTICE]** organisational item. The in-app Help page documents the
  review workflow and keyboard shortcuts; the grouped-review and context
  features reduce error-prone repetitive decisions

## Standard 4 — Managing data access
- Role-based access; admin-only destructive actions (delete SAR, delete
  page, finalise, user admin)
- Login rate limiting and idle session timeout for shared workstations
- Quarterly access review supported by the user list + audit CSV
  **[PRACTICE: schedule the review]**

## Standard 5 — Process reviews (learning from incidents)
- Redaction failures are surfaced, logged and block certification — every
  such event is reviewable in the audit trail
- IG report provides on-time performance trending to catch process slippage
- Clinical Safety Case hazard log is the living record of identified risks

## Standard 6 — Responding to incidents
- Audit trail supports incident reconstruction (who, what, when, from where)
- `SECURITY.md` documents the vulnerability reporting route
- **[PRACTICE]**: link to the practice incident procedure / DSPT incident
  reporting tool

## Standard 7 — Continuity planning
- Nightly automated backups (database snapshot, config, audit trail,
  documents) to a practice-chosen location with retention; last-backup
  status surfaced on `Admin → Status` and `/healthz` for monitoring
- Restore procedure documented in `INSTALL.md`; single-file database makes
  recovery a copy-back operation **[PRACTICE: perform and record an annual
  restore test]**

## Standard 8 — No unsupported systems
- Pinned dependency versions; release process includes the automated test
  suite and detection benchmark; update checker notifies of new releases
  without transmitting personal data

## Standard 9 — IT protection (technical security)
- CSRF protection on all mutating requests; HTML-escaping of
  document-derived text; upload size caps and zip-bomb guards; path
  traversal rejection
- Passwords hashed (PBKDF2); session cookies HttpOnly/SameSite-Strict;
  optional TLS for LAN transport without admin rights
- No inbound internet exposure: the application binds to the LAN and is not
  designed for WAN exposure **[PRACTICE: confirm firewall posture]**

## Standard 10 — Accountable suppliers
- This trust pack (DPIA template, DCB0129 safety case, security overview)
  constitutes the supplier evidence; no data processor relationship exists
  because no personal data flows to the supplier
