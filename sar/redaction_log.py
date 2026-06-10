import fitz
import os
from datetime import datetime
from sar.models import RedactionCandidate, RedactionStatus

EXEMPTION_LABELS = {
    "third_party": "Third-party data (s.16(4))",
    "serious_harm": "Serious harm (Sch 3, Para 2)",
    "crime_prevention": "Crime prevention (Sch 2, Para 2)",
    "legal_privilege": "Legal privilege (Sch 2, Para 19)",
    "management_forecast": "Management forecasting (Sch 2, Para 22)",
    "confidential_ref": "Confidential reference (Sch 2, Para 24)",
    "child_abuse": "Child abuse data (Sch 3, Para 3)",
    "regulatory": "Regulatory functions (Sch 2, Para 7)",
    "national_security": "National security (s.26)",
    "other": "Other (see notes)",
}


def generate_redaction_log(
    candidates: list[RedactionCandidate],
    output_dir: str,
    sar_id: str,
) -> str:
    """
    Generate a PDF redaction log listing all redaction decisions.
    Returns path to the log PDF.
    """
    doc = fitz.open()

    redacted = [c for c in candidates if c.status in
                (RedactionStatus.AUTO_REDACT, RedactionStatus.APPROVED)]
    excluded_subject = [c for c in candidates
                        if c.status == RedactionStatus.EXCLUDED_SUBJECT]
    excluded_staff = [c for c in candidates
                      if c.status == RedactionStatus.EXCLUDED_STAFF]
    rejected = [c for c in candidates
                if c.status == RedactionStatus.REJECTED]
    flagged = [c for c in candidates
               if c.status == RedactionStatus.FLAGGED]

    lines = [
        "SUBJECT ACCESS REQUEST - REDACTION LOG",
        f"SAR Reference: {sar_id}",
        f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        "",
        "SUMMARY",
        "-" * 50,
        f"Total detections: {len(candidates)}",
        f"Redactions applied: {len(redacted)}",
        f"Excluded (data subject): {len(excluded_subject)}",
        f"Excluded (staff): {len(excluded_staff)}",
        f"Rejected by reviewer: {len(rejected)}",
        f"Unreviewed (not redacted): {len(flagged)}",
        "",
        "=" * 60,
        "REDACTIONS APPLIED",
        "=" * 60,
    ]

    for i, c in enumerate(redacted, 1):
        method = "Auto-redacted" if c.status == RedactionStatus.AUTO_REDACT else "Manually approved"
        lines.extend([
            "",
            f"{i}. [{c.category.value.upper()}]",
            f"   Text: \"{c.text}\"",
            f"   File: {c.source_file}",
            f"   Page: {c.page_num + 1}",
            f"   Confidence: {c.confidence:.0%}",
            f"   Reason: {c.reason}",
            f"   Method: {method}",
        ])
        if c.exemption_code:
            exemption_label = EXEMPTION_LABELS.get(c.exemption_code, c.exemption_code)
            lines.append(f"   Exemption: {exemption_label}")
        if c.risk_flags:
            flags_str = ", ".join(f"{f['category']}: {f['phrase']}" for f in c.risk_flags)
            lines.append(f"   Risk flags: {flags_str}")

    if rejected:
        lines.extend([
            "",
            "=" * 60,
            "REJECTED (NOT REDACTED)",
            "=" * 60,
        ])
        for i, c in enumerate(rejected, 1):
            lines.extend([
                "",
                f"{i}. [{c.category.value.upper()}]",
                f"   Text: \"{c.text}\"",
                f"   File: {c.source_file}",
                f"   Page: {c.page_num + 1}",
                f"   Reason for detection: {c.reason}",
            ])

    if flagged:
        lines.extend([
            "",
            "=" * 60,
            "UNREVIEWED (NOT REDACTED)",
            "=" * 60,
        ])
        for i, c in enumerate(flagged, 1):
            lines.extend([
                "",
                f"{i}. [{c.category.value.upper()}]",
                f"   Text: \"{c.text}\"",
                f"   File: {c.source_file}",
                f"   Page: {c.page_num + 1}",
                f"   Confidence: {c.confidence:.0%}",
            ])

    # Write to PDF
    fontsize = 9
    margin = 50
    line_height = fontsize * 1.5
    page_height = 842
    page_width = 595

    page = None
    y_pos = 0

    for line_text in lines:
        if page is None or y_pos > page_height - margin:
            page = doc.new_page(width=page_width, height=page_height)
            y_pos = margin

        # Bold for headers
        is_header = (
            line_text.startswith("SUBJECT ACCESS")
            or line_text.startswith("SUMMARY")
            or line_text.startswith("REDACTIONS APPLIED")
            or line_text.startswith("REJECTED")
            or line_text.startswith("UNREVIEWED")
        )

        page.insert_text(
            fitz.Point(margin, y_pos),
            line_text,
            fontsize=fontsize + 2 if is_header else fontsize,
            fontname="helv",
        )
        y_pos += line_height

    output_path = os.path.join(output_dir, f"redaction_log_{sar_id}.pdf")
    doc.save(output_path)
    doc.close()
    return output_path
