# SAR Redact — Improvement & Central-Server Plan

*Goal: market-leading SAR redaction and report processing for GP practices,
deployable on locked-down NHS machines with **no admin rights**, run as a
**central server** on the practice LAN with staff connecting from their own
browsers.*

Companion document: [`CODE_REVIEW.md`](CODE_REVIEW.md) — issue IDs (C1, H2 …)
referenced below are defined there.

---

## Guiding constraints (do not break these)

1. **No admin rights, ever.** Everything must be xcopy-deployable: embedded
   Python, pip-installable pure wheels, per-user Startup folder / `schtasks`
   only. No services, no MSI, no registry, no Program Files.
2. **No patient data leaves the building.** All processing local; only the
   version-check touches the internet, and it stays opt-out-able.
3. **Small dependency surface.** Each new pip package must justify itself and
   must ship in the offline bundle.
4. **The audit trail must never overstate what happened** (DCB0129).

---

## Phase 0 — Safety & integrity fixes (do first, ~days)

These are small, high-leverage, and unblock everything else.

| # | Item | Fixes |
|---|------|-------|
| 0.1 | `apply_redactions` returns per-candidate success/failure; finalise blocks download and shows a "X items could not be placed — review manually" screen; redaction log records failures honestly | **C1** |
| 0.2 | Atomic writes everywhere: `tmp + os.replace()` helper used by `_save`, `_save_users`, `save_report`, `practice_config` | **C2** |
| 0.3 | Per-SAR `threading.Lock` around mutate-then-save; `If-Match: last_modified` precondition on candidate/batch/notes APIs → 409 with refresh prompt on conflict | **C3** |
| 0.4 | Stop overwriting originals on page delete: keep `original/` copy on upload, apply page exclusions at finalise | **C4** |
| 0.5 | `MAX_CONTENT_LENGTH` (e.g. 1 GB), zip extraction caps (entries, cumulative bytes, compression ratio) | **C5** |
| 0.6 | Login rate-limit + lockout backoff, CSRF token enforced on login/setup forms, `/logout` → POST | **H4** |
| 0.7 | Cache `users.json` with mtime check; treat present-but-corrupt users file as fatal (refuse to serve, don't offer `/setup`) | **H5, M2** |
| 0.8 | Filename collision suffixing on upload; reports store relative paths + migration (port the SAR-side fix) | **M8, M3** |
| 0.9 | Pin dependency versions + ship `constraints.txt`; bat installs from it | low |
| 0.10 | Replace `print` with `logging` (rotating file in `data/logs/`) | low |

**Exit criteria:** a crash, a concurrent reviewer, or a hostile upload cannot
corrupt state or silently leak PII; failed redactions are impossible to miss.

---

## Phase 1 — Test harness & detection quality (~1–2 weeks)

Detection quality is the product. Make it measurable before making it better.

1. **Pytest suite + synthetic corpus.** Generate fake GP-record PDFs (EMIS-style
   journals, Docman letters, hospital discharge summaries) with known planted
   PII — no real patient data — and assert precision/recall per category.
   Run in CI on every push. Publish the scores in the README: *measurable
   accuracy is a sales weapon nobody else in this niche has.*
2. **`SURNAME, Forename` and ALL-CAPS name detection** (**H1**) — the highest-value
   single detection improvement. Handle `SMITH, John`, `Re: JONES, Mary`,
   `McDonald` / `MacKay` / `O'Brien` / `van der Berg` internal capitals.
3. **Replace `map_text_to_spans`** with PyMuPDF-native per-occurrence rectangles
   (`page.search_for` with hit indexing, or char-offset mapping via `rawdict`)
   so boxes always land on the right occurrence (**H2**).
4. **Subject-identity hardening**: house-number-anchored address matching
   (**M4**); move hard-coded surnames into per-practice config (**M6**).
5. **Noise reduction**: medical-eponym blocklist for `FULL_NAME_PATTERN`
   ("Parkinson", "Barrett", "Crohn", drug names); measure reviewer-facing
   false-positive rate on the corpus and tune thresholds with evidence (**M5**).
6. **Whole-record name aggregation**: once a name is confirmed staff/subject/
   third-party anywhere in the SAR, propagate that decision to every other
   occurrence (the UI already has batch-by-text; make it automatic with an
   undo). This is the single biggest reviewer-time saver.

**Exit criteria:** precision/recall numbers per category in CI; `SMITH, John`
detected; no wrong-location boxes on the corpus.

---

## Phase 2 — Central server deployment kit (~2–3 weeks)

Turn "run the bat on a PC" into a supported, dependable practice service.
All items respect the no-admin constraint.

1. **SQLite storage backend** (stdlib, zero install). One `data/sarredact.db`,
   WAL mode for concurrent readers, tables for sars / candidates / reports /
   users / audit. Migrate existing JSON on first boot (keep JSON export for
   `.sarpack`). Removes the load-everything-at-boot ceiling, makes writes
   transactional, and enables dashboard queries over years of history.
2. **Server mode in the launcher.** `start_server.bat --server` (or a separate
   `install_as_server.bat`) that:
   - copies itself to a stable local path (`C:\SARRedact\`),
   - registers per-user autostart (`schtasks /create /sc onlogon` — no admin —
     with Startup-folder shortcut fallback),
   - wraps `serve.py` in a restart-on-crash loop,
   - writes the access URL (`http://<hostname>:<port>`) to a `CONNECT.txt` +
     prints a QR/short URL on the console for staff onboarding.
3. **TLS without admin rights.** Waitress cannot terminate TLS; swap to
   **cheroot** (pure-Python, pip wheel, same WSGI app) with a self-signed cert
   generated on first boot (via the `cryptography` wheel). Document the
   browser-trust step for practices that want the padlock; keep HTTP as
   fallback. Then flip `SESSION_COOKIE_SECURE=True` under TLS (**M7**).
4. **Access audit log** (**H3**): append-only audit table — login/logout/failed
   login, SAR viewed, candidate decisions, finalise, download, export, delete,
   user admin. Admin UI page with filter + CSV export. This is a procurement
   checkbox competitors miss.
5. **Operational endpoints**: `/healthz` (for a monitoring ping), `/admin/status`
   (version, uptime, disk free, DB size, last backup, active sessions).
6. **Scheduled backup**: nightly zip of `data/` to a configurable second path
   (practice NAS / synced folder), retention count, restore documented and
   tested. Surface "last successful backup" on the dashboard.
7. **Performance for shared use** (**H6**): LRU cache of open `fitz.Document`
   handles; disk cache of rendered page PNGs keyed by (file, mtime, page, zoom);
   pre-render next/previous page in the background. Target: <150 ms page turn
   on a 400-page record with 5 concurrent users on a mid-range desktop.
8. **Session hygiene for shared NHS workstations**: idle timeout (configurable,
   default 30 min), "switch user" affordance, concurrent-session listing on the
   account page.
9. **SSE job-queue TTL cleanup** (**M1**).
10. **Offline bundle pipeline**: CI job that builds the ~300 MB
    "everything included" zip (embedded Python + wheels + optional Tesseract
    portable) per release, so proxied-off practices install with zero internet.

**Exit criteria:** one machine in the practice runs SAR Redact as an
auto-starting, TLS, self-backing-up service; everyone else just browses to it;
two reviewers can work the same SAR without conflicts.

---

## Phase 3 — Reviewer experience (~2–4 weeks, parallelisable with Phase 2)

The review screen is where users spend 95% of their time; speed here is the
perceived quality of the product.

1. **Name-centric review mode**: group candidates by normalised name across the
   whole SAR ("Jane Doe — 47 occurrences across 12 documents: Redact all /
   Keep all / Review each"). Combined with Phase 1.6 this collapses hours into
   minutes for big records.
2. **Presence & assignment surfacing**: show who else has the SAR open; warn on
   entering a SAR allocated to someone else.
3. **Keyboard-first triage**: the shortcuts module exists — extend to full
   J/K + R(edact)/X(keep)/F(lag) flow with auto-advance, like email triage.
4. **Before/after preview** at finalise: side-by-side original vs redacted page
   render so the signing GP sees exactly what leaves the building.
5. **Reading-pane context**: show ±2 lines of surrounding text for each
   candidate in the sidebar so most decisions don't require looking at the page.
6. **Progress persistence per reviewer** (resume where you left off) and a
   "documents reviewed" checklist per file.
7. **Accessibility pass to WCAG 2.2 AA** (NHS service standard expectation):
   focus order, contrast, screen-reader labels on the canvas overlay.

---

## Phase 4 — Market-leading differentiators (~ongoing)

In rough order of sales impact per engineering effort:

1. **ICO response pack generator**: one click produces the disclosure bundle —
   redacted PDFs, redaction log, *response cover letter* from a template
   (practice config already holds the letterhead data), certificate of
   redaction, exemptions schedule. Practices currently hand-write these.
2. **IG/Compliance dashboard**: SAR volume, turnaround vs statutory deadline,
   stop-the-clock usage, monthly report export — what an IG lead pastes into
   their DSPT evidence and practice-meeting pack.
3. **Optional NER model pack**: a separately-downloaded "enhanced detection"
   bundle (e.g. spaCy small English NER, pip-installable, ~50 MB, still no
   admin) that runs *alongside* the rule engine and is benchmarked by the
   Phase 1 corpus. Rules stay as the floor; the model adds recall on unusual
   names. Local-only inference preserves the "nothing leaves the building"
   guarantee. (A local-LLM tier can follow the same pattern later.)
4. **Tesseract in the offline bundle**: the portable Tesseract binaries are
   xcopy-deployable — bundling them makes scanned-document OCR work
   out-of-the-box instead of "if installed". OCR coverage of Lloyd George
   scanned notes is a major competitive gap in this market.
5. **Email-in / Docman-folder watch**: a watched intake folder (practices can
   drag exports from EMIS/Docman into a share) that auto-creates draft SARs.
   No API integration needed — fits NHS reality.
6. **Multi-practice / PCN mode**: practice_id scoping over the SQLite schema so
   a PCN can run one server for several practices with data partitioning —
   the central-server work in Phase 2 makes this nearly free, and PCN-level
   procurement is where the volume is.
7. **Trust pack**: DPIA template, DCB0129 clinical safety case + hazard log,
   penetration-test summary, DSPT mapping document — shipped in `docs/`.
   For NHS buyers the paperwork *is* the product.
8. **Redaction styles**: configurable replacement text (`[THIRD PARTY]`,
   exemption code in the box), colour coding by category in output.

---

## Sequencing summary

```
Phase 0  Safety & integrity            ──► immediately, before more users
Phase 1  Tests + detection quality     ──► next; quality is measurable from here on
Phase 2  Central-server kit            ──► the headline ask; SQLite → TLS → audit → cache → backup
Phase 3  Reviewer experience           ──► parallel with late Phase 2
Phase 4  Differentiators               ──► continuous, driven by sales conversations
```

Each phase leaves the product shippable; nothing requires admin rights at any
point.
