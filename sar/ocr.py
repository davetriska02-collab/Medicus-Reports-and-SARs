"""OCR support for scanned PDF pages.

Provides Tesseract availability detection and per-page OCR via PyMuPDF.
This module is the single place that knows about Tesseract; all other
modules call into it rather than invoking PyMuPDF OCR APIs directly.
"""
import os
import shutil
import pathlib
import fitz  # PyMuPDF

from sar.models import TextSpan

# ── Tesseract discovery ───────────────────────────────────────────────────────
# Cached result: either a path string (truthy) or None (unavailable).
_tesseract_path: str | None | bool = False   # False = not yet probed


def tesseract_available() -> str | None:
    """Return the Tesseract executable path, or None if not found.

    Checks in order:
    1. tools/tesseract/tesseract.exe relative to the repo root
       (bundled portable Windows build).
    2. Any ``tesseract`` on the system PATH.

    The result is cached after the first call.
    """
    global _tesseract_path
    if _tesseract_path is not False:
        return _tesseract_path  # type: ignore[return-value]

    # Repo root is two levels up from this file (sar/ocr.py → sar/ → repo/)
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    bundled = repo_root / "tools" / "tesseract" / "tesseract.exe"
    if bundled.is_file():
        _tesseract_path = str(bundled)
        return _tesseract_path

    found = shutil.which("tesseract")
    _tesseract_path = found  # str or None
    return _tesseract_path


def tessdata_dir() -> str | None:
    """Return the tessdata directory to pass to PyMuPDF, or None.

    If the bundled Tesseract is in use, return the tessdata directory
    alongside it.  Otherwise, respect the ``TESSDATA_PREFIX`` environment
    variable, falling back to None (PyMuPDF/Tesseract will use its own
    default).
    """
    tess = tesseract_available()
    if tess is None:
        return None

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    bundled = repo_root / "tools" / "tesseract" / "tesseract.exe"
    if pathlib.Path(tess).resolve() == bundled.resolve():
        td = repo_root / "tools" / "tesseract" / "tessdata"
        return str(td) if td.is_dir() else None

    return os.environ.get("TESSDATA_PREFIX") or None


def ocr_page_spans(pdf_path: str, page_num: int) -> list[TextSpan]:
    """Return OCR-derived text spans for a single page.

    Uses PyMuPDF's ``page.get_textpage_ocr`` which drives Tesseract under
    the hood.  Spans are in the same shape as those produced by
    :func:`sar.pdf_parser.extract_text_spans` so the detector works
    unchanged.

    Returns an empty list when Tesseract is unavailable or when OCR fails.
    """
    if tesseract_available() is None:
        return []

    td = tessdata_dir()
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        tp = page.get_textpage_ocr(full=True, language="eng", dpi=300,
                                    tessdata=td)
        page_data = page.get_text("dict", textpage=tp, sort=True)
        doc.close()
    except Exception:
        return []

    spans: list[TextSpan] = []
    for block_idx, block in enumerate(page_data.get("blocks", [])):
        if block["type"] != 0:   # 0 = text
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
    return spans
