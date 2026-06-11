# Data Protection Impact Assessment (DPIA) — SAR Redact

> **Template status:** pre-filled with the product's actual architecture and
> controls. Sections marked **[PRACTICE]** must be completed and signed by the
> deploying practice — a DPIA is owned by the data controller, not the vendor.

| | |
|---|---|
| Processing activity | Preparation of Subject Access Request disclosures and structured medical reports from GP records |
| System | SAR Redact (locally hosted web application) |
| Data controller | **[PRACTICE]** |
| DPO / IG lead consulted | **[PRACTICE]** |
| Date / review date | **[PRACTICE]** |

## 1. Description of processing

### 1.1 Nature
Practice staff upload documents from a patient's medical record (PDF, TIFF,
RTF, images, GP2GP CDA). The system converts them to PDF, detects personal
identifiers and sensitive categories using local rule-based analysis, and
presents every detection to an authorised human reviewer who decides what is
redacted. Approved redactions are applied by content removal and the
disclosure bundle (redacted documents, redaction log, cover letter,
certificate of redaction) is produced for release to the data subject.

### 1.2 Scope of data
- Full medical record content of the data subject (special category data —
  health, and potentially all other special categories as recorded in notes)
- Third-party personal data incidentally present in the record (relatives,
  carers, other patients, complainants)
- Staff names (excluded from redaction by design — staff acting in a
  professional capacity)
- Application user accounts (name, username, hashed password)
- Audit trail (user actions, timestamps, source IP)

### 1.3 Context and location of processing
All processing occurs on practice-controlled hardware on the practice
network. **No patient data leaves the premises**: there is no cloud service,
no vendor access, and the only outbound traffic is an optional version-check
carrying no personal data (see `SECURITY.md`; can be disabled).

### 1.4 Purposes and lawful basis
- Compliance with data subject rights — UK GDPR Article 15 (legal obligation,
  Article 6(1)(c); Article 9(2)(f)/(h) for special category data, with
  DPA 2018 Schedule 1 conditions as applicable). **[PRACTICE to confirm
  lawful basis wording matches the practice's record of processing]**
- Production of medical reports (insurance, DWP, DVLA etc.) — consent /
  legal obligation depending on report type. **[PRACTICE]**

## 2. Necessity and proportionality

The alternative is manual redaction in general-purpose tools, which carries a
documented history of cosmetic-redaction failures (text recoverable beneath
drawn boxes) and no audit trail. SAR Redact processes only the documents
staff choose to upload, for the period required, with deletion controls and
automatic statutory-deadline tracking. Data minimisation is supported by
review-before-disclosure of every detection and an exemptions-coded
redaction log.

## 3. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigations (product) | Residual |
|---|---|---|---|---|---|
| 1 | Third-party data disclosed unredacted (missed detection) | Medium | High | Multi-pattern detection benchmarked on a synthetic corpus (published recall/precision); every page reviewable; manual draw mode; grouped by-name review reduces reviewer fatigue; safeguarding/sexual-health terms always flagged, never auto-redacted | Medium-Low — human review remains the control; see Clinical Safety Case hazard H1 |
| 2 | Redaction applied cosmetically and recoverable | Low | High | Content-stream removal + image pixel erasure (PyMuPDF redactions); failures reported, never silent; certificate blocked while failures exist | Low |
| 3 | Unauthorised access on the LAN | Medium | High | Per-user accounts, roles, login rate limiting, idle timeout, POST-only logout, CSRF protection, optional TLS, full access audit trail | Low — **[PRACTICE: confirm physical/network controls]** |
| 4 | Data loss / corruption | Low | Medium | Transactional SQLite storage, atomic writes, nightly backups with retention, originals preserved before destructive edits | Low — **[PRACTICE: confirm backup destination and restore test]** |
| 5 | Excessive retention of SAR working copies | Medium | Medium | Archive/delete controls per SAR; deletion removes uploads, outputs and records; **automatic scheduled deletion of completed SARs after a configurable period (default 180 days); every deletion is recorded in the audit trail** | Low — confirm or adjust the default retention period in Settings (Workflow Settings → GDPR data retention) |
| 6 | Wrong patient's documents uploaded to a SAR | Low | High | Subject details shown throughout review; subject-match exclusions make mismatches visible; audit trail of who uploaded what | Low-Medium — procedural control required **[PRACTICE]** |
| 7 | Insider misuse (browsing records without need) | Low | High | Append-only audit of every record view with user/time/IP; admin review + CSV export | Low |

## 4. Consultation
**[PRACTICE]** — record DPO advice, Caldicott Guardian view, and any staff
consultation here.

## 5. Sign-off

| Role | Name | Date | Outcome |
|---|---|---|---|
| Information Asset Owner | **[PRACTICE]** | | |
| DPO | **[PRACTICE]** | | |
| Caldicott Guardian | **[PRACTICE]** | | |
