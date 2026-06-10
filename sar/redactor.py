import fitz
import math
import os
from datetime import date
from sar.models import RedactionCandidate, RedactionStatus


def _stamp_page(page: fitz.Page, doc_name: str) -> None:
    """Add a diagonal 'REDACTED' watermark and footer stamp to each page."""
    rect = page.rect

    # Diagonal watermark — 45° via morph, 30% opacity so it doesn't obscure text
    # insert_text only accepts rotate 0/90/180/270, so we use morph
    # to rotate arbitrary angles around a pivot point.
    pivot = fitz.Point(rect.width * 0.5, rect.height * 0.5)
    angle = -45  # counter-clockwise
    morph = (pivot, fitz.Matrix(1, 0, 0, 1, 0, 0).prerotate(angle))
    page.insert_text(
        pivot - fitz.Point(160, 0),  # offset so text centres on pivot
        "REDACTED",
        fontsize=80,
        color=(0.5, 0.5, 0.5),
        fill_opacity=0.30,
        overlay=True,
        morph=morph,
    )

    # Footer stamp
    stamp = f"Redacted copy  ·  {date.today().strftime('%d %B %Y')}"
    page.insert_text(
        fitz.Point(36, rect.height - 18),
        stamp,
        fontsize=7,
        color=(0.55, 0.55, 0.55),
        overlay=True,
    )


def apply_redactions(
    pdf_path: str,
    candidates: list[RedactionCandidate],
    output_dir: str,
) -> str:
    """
    Apply confirmed redactions to a PDF and save the result.
    Returns the path to the redacted PDF.
    """
    doc = fitz.open(pdf_path)
    basename = os.path.basename(pdf_path)

    # Filter to only candidates that should be redacted for this file
    to_redact = [
        c for c in candidates
        if c.status in (RedactionStatus.AUTO_REDACT, RedactionStatus.APPROVED)
        and c.source_file == basename
    ]

    # Group by page
    by_page: dict[int, list[RedactionCandidate]] = {}
    for c in to_redact:
        by_page.setdefault(c.page_num, []).append(c)

    for page_num, page_candidates in by_page.items():
        if page_num >= len(doc):
            continue
        page = doc[page_num]

        for c in page_candidates:
            if c.x0 > 0 and c.y0 > 0 and c.x1 > 0 and c.y1 > 0:
                # We have coordinates from span mapping
                rect = fitz.Rect(c.x0, c.y0, c.x1, c.y1)
                page.add_redact_annot(
                    rect,
                    text="[REDACTED]",
                    fontsize=7,
                    fill=(0, 0, 0),
                    text_color=(1, 1, 1),
                )
            else:
                # Fallback: search for the text on the page
                instances = page.search_for(c.text)
                for inst in instances:
                    page.add_redact_annot(
                        inst,
                        text="[REDACTED]",
                        fontsize=7,
                        fill=(0, 0, 0),
                        text_color=(1, 1, 1),
                    )

        # Apply all redactions for this page at once
        # PDF_REDACT_IMAGE_PIXELS ensures image pixels are blanked (important for scanned docs)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_PIXELS,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        )

    # Add watermark stamp to every page
    doc_name = os.path.splitext(basename)[0]
    for page_num in range(len(doc)):
        _stamp_page(doc[page_num], doc_name)

    # Save redacted PDF
    name_part = os.path.splitext(basename)[0]
    output_path = os.path.join(output_dir, f"{name_part}_redacted.pdf")
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    return output_path
