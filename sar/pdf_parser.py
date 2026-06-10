import os
import fitz  # PyMuPDF
from sar.models import TextSpan

# Ensure Tesseract can find its data files on Windows (set before first OCR call)
if not os.environ.get("TESSDATA_PREFIX"):
    # Tesseract is optional — only used for scanned PDFs.
    # Common paths tried in order; falls back gracefully if not installed.
    _tess_dir = None
    for _candidate in [
        r"C:\Program Files\Tesseract-OCR\tessdata",
        r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
    ]:
        if __import__("os").path.isdir(_candidate):
            _tess_dir = _candidate
            break
    if _tess_dir and os.path.isdir(_tess_dir):
        os.environ["TESSDATA_PREFIX"] = _tess_dir

# Whether PyMuPDF's Tesseract OCR integration is available
_OCR_AVAILABLE: bool | None = None  # None = not yet tested


def _check_ocr_available() -> bool:
    """Test once whether Tesseract OCR is available via PyMuPDF."""
    global _OCR_AVAILABLE
    if _OCR_AVAILABLE is not None:
        return _OCR_AVAILABLE
    try:
        doc = fitz.open()
        page = doc.new_page()
        page.get_textpage_ocr(flags=0)
        doc.close()
        _OCR_AVAILABLE = True
    except Exception:
        _OCR_AVAILABLE = False
    return _OCR_AVAILABLE


def _has_text_content(page_data: dict) -> bool:
    """Return True if the page dict contains any non-empty text spans."""
    return any(
        block["type"] == 0 and any(
            s["text"].strip()
            for line in block["lines"]
            for s in line["spans"]
        )
        for block in page_data["blocks"]
    )


def _get_text_page(page: fitz.Page) -> fitz.TextPage | None:
    """
    Get a TextPage for the page, using OCR if the page has no native text
    and Tesseract is available.
    Returns None if OCR is needed but unavailable.
    """
    raw = page.get_text("dict", sort=True)
    if _has_text_content(raw):
        return None  # use native extraction

    if _check_ocr_available():
        try:
            return page.get_textpage_ocr(flags=3, language="eng", dpi=300)
        except Exception:
            pass
    return None  # image-only, no OCR


def extract_text_spans(pdf_path: str) -> list[TextSpan]:
    """
    Extract all text spans from a PDF (or TIF) with their bounding boxes.
    Falls back to OCR for image-only pages when Tesseract is available.
    Returns a flat list of TextSpan objects across all pages.
    """
    spans = []
    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        ocr_tp = _get_text_page(page)

        if ocr_tp is not None:
            page_data = page.get_text("dict", textpage=ocr_tp, sort=True)
        else:
            page_data = page.get_text("dict", sort=True)

        for block_idx, block in enumerate(page_data["blocks"]):
            if block["type"] != 0:  # 0 = text, 1 = image
                continue
            for line_idx, line in enumerate(block["lines"]):
                for span_idx, span in enumerate(line["spans"]):
                    text = span["text"].strip()
                    if not text:
                        continue
                    bbox = span["bbox"]
                    spans.append(TextSpan(
                        text=text,
                        page_num=page_num,
                        x0=bbox[0],
                        y0=bbox[1],
                        x1=bbox[2],
                        y1=bbox[3],
                        block_no=block_idx,
                        line_no=line_idx,
                        span_no=span_idx,
                    ))

    doc.close()
    return spans


def render_page_image(pdf_path: str, page_num: int, zoom: float = 2.0) -> bytes:
    """
    Render a PDF page to PNG bytes for display in the review UI.
    zoom=2.0 gives 144 DPI (2x the default 72 DPI).
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def get_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def get_page_dimensions(pdf_path: str, page_num: int) -> tuple[float, float]:
    """Get page width and height in PDF points."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    rect = page.rect
    doc.close()
    return rect.width, rect.height


def get_full_page_text(pdf_path: str, page_num: int) -> str:
    """Get plain text of a page for pattern detection (uses OCR if needed)."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    ocr_tp = _get_text_page(page)
    if ocr_tp is not None:
        text = page.get_text("text", textpage=ocr_tp)
    else:
        text = page.get_text("text")
    doc.close()
    return text


def is_image_only_page(pdf_path: str, page_num: int) -> bool:
    """Return True if this page has no native text (requires OCR to read)."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    raw = page.get_text("dict", sort=True)
    result = not _has_text_content(raw)
    doc.close()
    return result
