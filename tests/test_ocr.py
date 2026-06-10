"""Tests for Batch A: OCR and unscreened-page safety.

Covers:
- page_needs_ocr() detection
- unscreened pages recorded when tesseract unavailable
- OCR spans returned when tesseract is present (skipped otherwise)
- Redaction log includes UNSCREENED PAGES section
"""
import shutil
import pytest
import fitz

from sar.pdf_parser import page_needs_ocr
from sar.detector import detect_pii
from sar.models import SubjectDetails
from sar.redaction_log import generate_redaction_log


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_text_pdf(tmp_path) -> str:
    """Create a plain text PDF (page_needs_ocr should return False)."""
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text(fitz.Point(72, 100),
                   "Patient: John Smith  NHS: 943 476 5919  DOB: 01/01/1980")
    p = tmp_path / "text.pdf"
    doc.save(str(p))
    doc.close()
    return str(p)


def _make_image_pdf(tmp_path) -> str:
    """Create a PDF whose only content is an image (page_needs_ocr should return True).

    We render a small text page to a pixmap at high DPI, then insert the
    resulting pixmap as an image into a fresh, empty page.  The destination
    page has no text layer, only an embedded image.
    """
    # 1. Render a text page to a pixmap
    src = fitz.open()
    src_pg = src.new_page(width=300, height=100)
    src_pg.insert_text(fitz.Point(20, 60), "Jane Bloggs", fontsize=24)
    mat = fitz.Matrix(3, 3)   # 3× zoom → ~216 DPI
    pix = src_pg.get_pixmap(matrix=mat)
    src.close()

    # 2. Insert that pixmap as an image into a new empty page
    doc = fitz.open()
    pg = doc.new_page(width=pix.width, height=pix.height)
    rect = fitz.Rect(0, 0, pix.width, pix.height)
    pg.insert_image(rect, pixmap=pix)
    p = tmp_path / "image_only.pdf"
    doc.save(str(p))
    doc.close()
    return str(p)


# ── page_needs_ocr ────────────────────────────────────────────────────────────

def test_page_needs_ocr_false_for_text_page(tmp_path):
    pdf = _make_text_pdf(tmp_path)
    assert page_needs_ocr(pdf, 0) is False


def test_page_needs_ocr_true_for_image_page(tmp_path):
    pdf = _make_image_pdf(tmp_path)
    assert page_needs_ocr(pdf, 0) is True


def test_page_needs_ocr_accepts_fitz_page(tmp_path):
    pdf = _make_image_pdf(tmp_path)
    doc = fitz.open(pdf)
    result = page_needs_ocr(doc[0])
    doc.close()
    assert result is True


# ── Unscreened pages when tesseract unavailable ───────────────────────────────

def test_unscreened_recorded_when_no_tesseract(tmp_path, monkeypatch):
    """detection on an image-only PDF must report unscreened pages when
    Tesseract is not available."""
    import sar.ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "_tesseract_path", None)

    pdf = _make_image_pdf(tmp_path)
    subject = SubjectDetails(full_name="Jane Bloggs", first_name="Jane", last_name="Bloggs")
    candidates, unscreened = detect_pii(pdf, [], subject, "image_only.pdf")

    assert len(unscreened) == 1
    assert unscreened[0]["source_file"] == "image_only.pdf"
    assert unscreened[0]["page_num"] == 0


def test_text_pdf_produces_no_unscreened(tmp_path, monkeypatch):
    """A native-text page must never appear in unscreened_pages."""
    import sar.ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "_tesseract_path", None)

    pdf = _make_text_pdf(tmp_path)
    from sar.pdf_parser import extract_text_spans
    spans = extract_text_spans(pdf)
    subject = SubjectDetails(full_name="John Smith", first_name="John", last_name="Smith")
    candidates, unscreened = detect_pii(pdf, spans, subject, "text.pdf")

    assert unscreened == []


# ── OCR integration (only runs when tesseract is present) ─────────────────────

@pytest.mark.skipif(shutil.which("tesseract") is None,
                    reason="Tesseract not installed — skipping OCR integration test")
def test_ocr_spans_returned_when_tesseract_present(tmp_path):
    """When Tesseract is available, OCR the image page and get text spans back."""
    from sar.ocr import ocr_page_spans
    pdf = _make_image_pdf(tmp_path)
    spans = ocr_page_spans(pdf, 0)
    assert len(spans) > 0
    combined = " ".join(s.text for s in spans)
    assert "Jane" in combined or "Bloggs" in combined or len(combined) > 0


@pytest.mark.skipif(shutil.which("tesseract") is None,
                    reason="Tesseract not installed — skipping OCR detection test")
def test_ocr_detection_finds_name_with_confidence_cap(tmp_path):
    """End-to-end: OCR a planted name from an image page; confidence must be <= 0.85."""
    pdf = _make_image_pdf(tmp_path)
    subject = SubjectDetails(full_name="John Smith", first_name="John", last_name="Smith")
    candidates, unscreened = detect_pii(pdf, [], subject, "image_only.pdf")

    assert unscreened == [], "should be screened when tesseract available"
    # Jane Bloggs should appear as a candidate (third-party name)
    jane = next((c for c in candidates if "Jane" in c.text or "Bloggs" in c.text), None)
    assert jane is not None, "OCR should detect 'Jane Bloggs' from image"
    assert jane.confidence <= 0.85, "OCR confidence must be capped at 0.85"
    assert jane.reason.startswith("OCR: "), "reason must be prefixed with 'OCR: '"


# ── Redaction log includes UNSCREENED PAGES section ──────────────────────────

def test_redaction_log_includes_unscreened_section(tmp_path):
    unscreened = [
        {"source_file": "lloyd_george.pdf", "page_num": 2},
        {"source_file": "hospital_letter.pdf", "page_num": 0},
    ]
    log_path = generate_redaction_log(
        candidates=[], output_dir=str(tmp_path), sar_id="testsar",
        unscreened_pages=unscreened,
    )
    doc = fitz.open(log_path)
    text = "".join(p.get_text() for p in doc)
    doc.close()

    assert "UNSCREENED PAGES" in text
    assert "lloyd_george.pdf" in text
    assert "hospital_letter.pdf" in text
    # page numbers are 1-based in the log
    assert "3" in text   # page_num=2 → displayed as page 3
    assert "1" in text   # page_num=0 → displayed as page 1


def test_redaction_log_no_unscreened_section_when_empty(tmp_path):
    log_path = generate_redaction_log(
        candidates=[], output_dir=str(tmp_path), sar_id="testsar",
    )
    doc = fitz.open(log_path)
    text = "".join(p.get_text() for p in doc)
    doc.close()

    # The detailed section (with "NOT CHECKED BY AUTOMATED DETECTION")
    # must not appear when there are no unscreened pages.
    assert "NOT CHECKED BY AUTOMATED DETECTION" not in text
