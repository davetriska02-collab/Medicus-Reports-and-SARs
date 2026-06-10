import hashlib
import os
import tempfile
import threading
import fitz  # PyMuPDF
from sar.models import TextSpan

# ── Rendered-page cache ──────────────────────────────────────────────────────
# Page PNGs are cached on disk keyed by (path, mtime, page, zoom). Re-renders
# (and OCR re-runs on scanned pages) are the dominant cost when several
# reviewers page through the same record on a shared server. Keys include the
# file mtime, so editing a document (e.g. page deletion) invalidates naturally.
_PAGE_CACHE_DIR = str(__import__("pathlib").Path(__file__).resolve().parent.parent
                      / "data" / "cache" / "pages")
_PAGE_CACHE_MAX_FILES = 4000   # prune oldest beyond this
_page_cache_lock = threading.Lock()

# In-memory page-count cache: {abspath: (mtime, count)}
_page_count_cache: dict[str, tuple[float, int]] = {}


def _page_cache_key(pdf_path: str, page_num: int, zoom: float) -> str:
    try:
        mtime = os.path.getmtime(pdf_path)
    except OSError:
        mtime = 0
    raw = f"{os.path.abspath(pdf_path)}|{mtime}|{page_num}|{zoom}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _page_cache_prune():
    try:
        files = [(os.path.getmtime(os.path.join(_PAGE_CACHE_DIR, f)), f)
                 for f in os.listdir(_PAGE_CACHE_DIR)]
    except OSError:
        return
    if len(files) <= _PAGE_CACHE_MAX_FILES:
        return
    files.sort()
    for _, f in files[:len(files) - _PAGE_CACHE_MAX_FILES + 500]:
        try:
            os.remove(os.path.join(_PAGE_CACHE_DIR, f))
        except OSError:
            pass

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
    Results are cached on disk (see _PAGE_CACHE_DIR).
    """
    key = _page_cache_key(pdf_path, page_num, zoom)
    cache_path = os.path.join(_PAGE_CACHE_DIR, f"{key}.png")
    try:
        with open(cache_path, "rb") as f:
            return f.read()
    except OSError:
        pass

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()

    try:
        os.makedirs(_PAGE_CACHE_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_PAGE_CACHE_DIR, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(img_bytes)
        os.replace(tmp, cache_path)
        with _page_cache_lock:
            _page_cache_prune()
    except OSError:
        pass  # cache failure must never break rendering

    return img_bytes


def get_page_count(pdf_path: str) -> int:
    apath = os.path.abspath(pdf_path)
    try:
        mtime = os.path.getmtime(apath)
        cached = _page_count_cache.get(apath)
        if cached and cached[0] == mtime:
            return cached[1]
    except OSError:
        mtime = None
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    if mtime is not None:
        _page_count_cache[apath] = (mtime, count)
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


def page_needs_ocr(page_or_path, page_num: int | None = None) -> bool:
    """Return True when a page has at least one image and fewer than ~30
    non-whitespace characters of extractable text.

    Accepts either:
    - a :class:`fitz.Page` object (``page_num`` is ignored), or
    - a path string and a ``page_num`` integer.

    Scanned documents (Lloyd George cards, hospital letters) typically
    embed the whole page as an image with no text layer at all; the 30-char
    threshold gives a small margin for pages that carry both a faint text
    stamp and a scanned image.
    """
    _TEXT_THRESHOLD = 30

    if isinstance(page_or_path, str):
        doc = fitz.open(page_or_path)
        page = doc[page_num]
        _close = True
    else:
        page = page_or_path
        _close = False

    try:
        has_images = bool(page.get_images())
        raw = page.get_text("dict", sort=True)
        chars = sum(
            len(s["text"].replace(" ", "").replace("\n", "").replace("\t", ""))
            for block in raw["blocks"] if block["type"] == 0
            for line in block["lines"]
            for s in line["spans"]
        )
        return has_images and chars < _TEXT_THRESHOLD
    finally:
        if _close:
            doc.close()
