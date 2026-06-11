"""ICO/GDPR response pack — cover letter and certificate of redaction.

One click after finalising produces the documents practices currently
hand-write for every SAR disclosure:

- Cover letter on the practice letterhead (UK GDPR Article 15 response),
  listing enclosures and the patient's rights (ICO complaint route).
- Certificate of redaction: scope, methodology (true content-stream removal),
  decision counts by category and DPA 2018 exemption, authorised-by block.

The certificate is refused while any approved redaction failed to apply —
it must never certify something the output files don't deliver.
"""
import os
from datetime import datetime, date

import fitz

from sar.models import RedactionStatus
from sar.redaction_log import EXEMPTION_LABELS

_A4_W, _A4_H = 595, 842
_MARGIN = 56


class _Writer:
    """Minimal multi-page text writer (same approach as report_generator)."""

    def __init__(self):
        self.doc = fitz.open()
        self.page = None
        self.y = _A4_H

    def _ensure(self, needed: float):
        if self.page is None or self.y + needed > _A4_H - _MARGIN:
            self.page = self.doc.new_page(width=_A4_W, height=_A4_H)
            self.y = _MARGIN + 10

    def line(self, text: str = "", size: float = 10, bold: bool = False,
             indent: float = 0, colour=(0, 0, 0)):
        self._ensure(size * 1.5)
        if text:
            self.page.insert_text(
                fitz.Point(_MARGIN + indent, self.y), text[:230],
                fontsize=size, fontname="hebo" if bold else "helv", color=colour)
        self.y += size * 1.5

    def wrapped(self, text: str, size: float = 10, bold: bool = False,
                indent: float = 0):
        max_chars = int((_A4_W - 2 * _MARGIN - indent) / (size * 0.5))
        line = ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if len(trial) > max_chars:
                if line:
                    self.line(line, size=size, bold=bold, indent=indent)
                line = word
            else:
                line = trial
        if line:
            self.line(line, size=size, bold=bold, indent=indent)

    def gap(self, points: float = 8):
        self.y += points

    def save(self, path: str) -> str:
        self.doc.save(path)
        self.doc.close()
        return path


def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime("%d %B %Y")
    except (ValueError, TypeError):
        return str(iso)[:10]


def _redacted_candidates(sar):
    return [c for c in sar.candidates
            if c.status in (RedactionStatus.AUTO_REDACT, RedactionStatus.APPROVED)]


def generate_cover_letter(sar, cfg: dict, output_dir: str,
                          custom_paragraph: str = "") -> str:
    """Article 15 response letter addressed to the data subject."""
    os.makedirs(output_dir, exist_ok=True)
    w = _Writer()
    subj = sar.subject
    practice = cfg.get("practice_name", "")
    officer = cfg.get("sar_officer_name", "")
    officer_role = cfg.get("sar_officer_role", "Data Protection Lead")
    officer_email = cfg.get("sar_officer_email", "")

    # Letterhead
    w.line(practice, size=15, bold=True)
    for addr_line in (cfg.get("practice_address") or "").splitlines():
        if addr_line.strip():
            w.line(addr_line.strip(), size=9, colour=(0.35, 0.35, 0.35))
    w.gap(14)
    w.line(date.today().strftime("%d %B %Y"))
    w.gap(10)

    w.line("PRIVATE & CONFIDENTIAL", size=10, bold=True)
    w.line(subj.full_name or f"{subj.first_name} {subj.last_name}".strip())
    for addr_line in (subj.address or "").splitlines():
        if addr_line.strip():
            w.line(addr_line.strip())
    w.gap(14)

    w.line(f"Dear {subj.full_name or 'Sir/Madam'},")
    w.gap(6)
    ref_bits = [f"Subject Access Request — {subj.full_name}"]
    if subj.date_of_birth:
        ref_bits.append(f"DOB {subj.date_of_birth}")
    if subj.nhs_number:
        ref_bits.append(f"NHS No. {subj.nhs_number}")
    w.wrapped("Re: " + " · ".join(ref_bits), bold=True)
    w.gap(8)

    received = _fmt_date(sar.created_at)
    w.wrapped(
        f"Please find enclosed the information held by {practice} in response "
        f"to your subject access request received on {received}, provided in "
        "accordance with Article 15 of the UK General Data Protection "
        "Regulation and the Data Protection Act 2018.")
    w.gap(8)

    n_files = len(sar.pdf_files)
    n_redactions = len(_redacted_candidates(sar))
    w.wrapped(
        f"Enclosed: {n_files} document{'s' if n_files != 1 else ''} from your "
        "medical record, together with a redaction log describing the "
        "categories of information withheld.")
    w.gap(8)

    if n_redactions:
        w.wrapped(
            "Some information has been redacted. Redactions are made only "
            "where an exemption in the Data Protection Act 2018 applies — "
            "most commonly where material identifies another individual "
            "(third-party data) or where disclosure is otherwise restricted "
            "by Schedules 2 and 3 of the Act. The enclosed redaction log "
            "records each redaction and the reason for it.")
        w.gap(8)

    if custom_paragraph.strip():
        w.wrapped(custom_paragraph.strip())
        w.gap(8)

    contact = officer or practice
    contact_suffix = f" at {officer_email}" if officer_email else ""
    w.wrapped(
        f"If you believe information is missing, inaccurate or has been "
        f"incorrectly withheld, please contact {contact}{contact_suffix}. "
        "You also have the right to complain to the Information "
        "Commissioner's Office (ico.org.uk, 0303 123 1113).")
    w.gap(16)

    w.line("Yours sincerely,")
    w.gap(20)
    if officer:
        w.line(officer, bold=True)
        w.line(officer_role, size=9, colour=(0.35, 0.35, 0.35))
    w.line(practice, size=9, colour=(0.35, 0.35, 0.35))
    if cfg.get("footer_text"):
        w.gap(14)
        w.line(cfg["footer_text"], size=8, colour=(0.5, 0.5, 0.5))

    return w.save(os.path.join(output_dir, f"cover_letter_{sar.id}.pdf"))


def generate_acknowledgment(sar, cfg: dict, output_dir: str) -> str:
    """Article 12 acknowledgment letter confirming receipt of the SAR."""
    os.makedirs(output_dir, exist_ok=True)
    w = _Writer()
    subj = sar.subject
    practice = cfg.get("practice_name", "")
    officer = cfg.get("sar_officer_name", "")
    officer_role = cfg.get("sar_officer_role", "Data Protection Lead")
    officer_email = cfg.get("sar_officer_email", "")

    # Letterhead (matches generate_cover_letter exactly)
    w.line(practice, size=15, bold=True)
    for addr_line in (cfg.get("practice_address") or "").splitlines():
        if addr_line.strip():
            w.line(addr_line.strip(), size=9, colour=(0.35, 0.35, 0.35))
    w.gap(14)
    w.line(date.today().strftime("%d %B %Y"))
    w.gap(10)

    w.line("PRIVATE & CONFIDENTIAL", size=10, bold=True)
    w.line(subj.full_name or f"{subj.first_name} {subj.last_name}".strip())
    for addr_line in (subj.address or "").splitlines():
        if addr_line.strip():
            w.line(addr_line.strip())
    w.gap(14)

    w.line(f"Dear {subj.full_name or 'Sir/Madam'},")
    w.gap(6)
    ref_bits = [f"Subject Access Request — {subj.full_name}"]
    if subj.date_of_birth:
        ref_bits.append(f"DOB {subj.date_of_birth}")
    if subj.nhs_number:
        ref_bits.append(f"NHS No. {subj.nhs_number}")
    w.wrapped("Re: " + " · ".join(ref_bits), bold=True)
    w.gap(8)

    # Determine receipt date and due date
    receipt_iso = (getattr(sar, "request_date", "") or "").strip() or sar.created_at
    receipt_display = _fmt_date(receipt_iso)
    # Due date from model (already accounts for request_date)
    due_display = _fmt_date(sar.due_date) if sar.due_date else "within one calendar month"

    w.wrapped(
        f"We are writing to confirm that {practice} has received your subject "
        f"access request on {receipt_display}. Your request is being processed "
        "in accordance with Article 15 of the UK General Data Protection "
        "Regulation and the Data Protection Act 2018.")
    w.gap(8)

    w.wrapped(
        f"We will respond to your request within one calendar month of the date "
        f"of receipt. The deadline for our response is {due_display}.")
    w.gap(8)

    w.wrapped(
        "Please note that in cases of complexity or where a large volume of "
        "information is involved, we may extend this period by up to a further "
        "two months. If we need to do so, we will notify you within one calendar "
        "month of your request, explaining the reasons for the extension.")
    w.gap(8)

    id_verified = (getattr(sar, "id_verified", "") or "").strip()
    if id_verified:
        w.wrapped(
            f"Your identity has been verified ({id_verified}). "
            "No further identification documents are required at this time.")
        w.gap(8)
    else:
        w.wrapped(
            "If we have not already verified your identity, we may contact you "
            "to request suitable identification documents before we are able to "
            "release personal data.")
        w.gap(8)

    contact = officer or practice
    contact_suffix = f" at {officer_email}" if officer_email else ""
    w.wrapped(
        f"If you have any questions about your request, please contact "
        f"{contact}{contact_suffix}. You also have the right to complain to the "
        "Information Commissioner's Office (ico.org.uk, 0303 123 1113).")
    w.gap(16)

    w.line("Yours sincerely,")
    w.gap(20)
    if officer:
        w.line(officer, bold=True)
        w.line(officer_role, size=9, colour=(0.35, 0.35, 0.35))
    w.line(practice, size=9, colour=(0.35, 0.35, 0.35))
    if cfg.get("footer_text"):
        w.gap(14)
        w.line(cfg["footer_text"], size=8, colour=(0.5, 0.5, 0.5))

    return w.save(os.path.join(output_dir, f"acknowledgment_{sar.id}.pdf"))


def generate_certificate(sar, cfg: dict, output_dir: str,
                         page_counts: dict | None = None,
                         manual_verification_note: int = 0) -> str:
    """Certificate of redaction with category and exemption breakdowns.

    Caller must ensure there are no failed redactions before calling —
    this document certifies that approved redactions were applied.

    When manual_verification_note > 0, the caller has invoked an admin
    override: N redactions could not be machine-verified.  Section 4 is
    replaced with an honest statement and the failed candidates' texts are
    NOT printed (they may be the very third-party data being protected).
    This variant must only be generated under an explicit admin override.
    """
    if getattr(sar, "redaction_failures", []) and not manual_verification_note:
        raise ValueError("Cannot certify: approved redactions failed to apply")

    os.makedirs(output_dir, exist_ok=True)
    w = _Writer()
    redacted = _redacted_candidates(sar)
    total_pages = sum((page_counts or {}).values())

    w.line("CERTIFICATE OF REDACTION", size=15, bold=True)
    w.line(cfg.get("practice_name", ""), size=10, colour=(0.35, 0.35, 0.35))
    w.gap(10)
    w.line(f"SAR reference: {sar.id}", size=10)
    w.line(f"Data subject: {sar.subject.full_name}", size=10)
    w.line(f"Generated: {date.today().strftime('%d %B %Y')}", size=10)
    w.gap(12)

    w.line("1. Scope", size=11, bold=True)
    scope = f"{len(sar.pdf_files)} source document(s)"
    if total_pages:
        scope += f" totalling {total_pages} page(s)"
    w.wrapped(scope + " were processed for disclosure.")
    w.gap(8)

    w.line("2. Methodology", size=11, bold=True)
    w.wrapped(
        "Documents were screened by automated detection of personal "
        "identifiers and sensitive categories, and every detection was "
        "reviewed by an authorised member of staff. Redactions were applied "
        "by content removal: redacted text is deleted from the document "
        "content stream and underlying image pixels are erased. Redacted "
        "material cannot be recovered from the disclosed files.")
    w.gap(8)

    w.line("3. Redaction decisions", size=11, bold=True)
    w.wrapped(f"Redactions applied: {len(redacted)}")
    by_cat = {}
    for c in redacted:
        by_cat[c.category.value] = by_cat.get(c.category.value, 0) + 1
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        w.line(f"- {cat.replace('_', ' ')}: {n}", size=9, indent=10)
    w.gap(6)

    w.wrapped("Exemptions relied upon (Data Protection Act 2018):", size=10)
    by_ex = {}
    for c in redacted:
        by_ex[c.exemption_code or ""] = by_ex.get(c.exemption_code or "", 0) + 1
    for code, n in sorted(by_ex.items(), key=lambda kv: -kv[1]):
        label = EXEMPTION_LABELS.get(code) if code else \
            "Third-party data (no specific code recorded)"
        w.line(f"- {label or code}: {n}", size=9, indent=10)
    w.gap(8)

    w.line("4. Verification", size=11, bold=True)
    if manual_verification_note:
        n = manual_verification_note
        w.wrapped(
            f"{n} redaction(s) could not be machine-verified as applied. "
            "The authorised signatory has manually verified the disclosed "
            "documents before release.")
    else:
        w.wrapped(
            "All redactions approved during review were verified as applied to "
            "the output documents. The accompanying redaction log records each "
            "individual decision, including detections reviewed and not redacted.")
    w.gap(16)

    w.line("Authorised by:", size=10, bold=True)
    w.gap(4)
    officer = cfg.get("sar_officer_name", "")
    if officer:
        w.line(f"{officer} — {cfg.get('sar_officer_role', '')}", size=10)
    w.gap(18)
    w.line("Signature: " + "_" * 40, size=10)
    w.gap(10)
    w.line("Date: " + "_" * 24, size=10)

    return w.save(os.path.join(output_dir,
                               f"certificate_of_redaction_{sar.id}.pdf"))
