"""pdf_parser.py coverage (M2.2).

Tests: extract_text_spans, get_page_count, get_page_dimensions,
render_page_image cache miss/hit, get_full_page_text.
"""
import os
import tempfile

import fitz
import pytest

from sar.pdf_parser import (
    extract_text_spans,
    get_full_page_text,
    get_page_count,
    get_page_dimensions,
    render_page_image,
    _PAGE_CACHE_DIR,
    _page_cache_key,
)


# ── Fixture: a real PDF with known text ──────────────────────────────────────

@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory):
    """Two-page PDF with planted text on each page."""
    d = tmp_path_factory.mktemp("pdf_parser")
    path = str(d / "sample.pdf")
    doc = fitz.open()
    # Page 0: known text with bounding-box-friendly insertion
    p0 = doc.new_page(width=595, height=842)
    p0.insert_text(fitz.Point(72, 100), "Hello World unique_token_page0")
    # Page 1: different content
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(fitz.Point(72, 100), "Second page unique_token_page1")
    doc.save(path)
    doc.close()
    return path


# ── get_page_count ────────────────────────────────────────────────────────────

def test_get_page_count(sample_pdf):
    assert get_page_count(sample_pdf) == 2


def test_get_page_count_single_page(tmp_path):
    path = str(tmp_path / "one.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    assert get_page_count(path) == 1


# ── get_page_dimensions ───────────────────────────────────────────────────────

def test_get_page_dimensions(sample_pdf):
    w, h = get_page_dimensions(sample_pdf, 0)
    # A4 in points: 595 × 842
    assert abs(w - 595) < 2
    assert abs(h - 842) < 2


# ── extract_text_spans ────────────────────────────────────────────────────────

def test_extract_text_spans_contains_text(sample_pdf):
    spans = extract_text_spans(sample_pdf)
    assert spans, "expected at least one span"
    combined = " ".join(s.text for s in spans)
    assert "Hello" in combined or "unique_token_page0" in combined


def test_extract_text_spans_bbox(sample_pdf):
    spans = extract_text_spans(sample_pdf)
    for span in spans:
        # Every span should have a valid bounding box (non-negative, x1>x0, y1>y0)
        assert span.x0 >= 0
        assert span.y0 >= 0
        assert span.x1 > span.x0
        assert span.y1 > span.y0


def test_extract_text_spans_page_numbers(sample_pdf):
    spans = extract_text_spans(sample_pdf)
    page_nums = {s.page_num for s in spans}
    # Both pages should have text
    assert 0 in page_nums
    assert 1 in page_nums


def test_extract_text_spans_correct_page_assignment(sample_pdf):
    """Text planted on page 0 should appear only on page_num=0 spans."""
    spans = extract_text_spans(sample_pdf)
    page0_text = " ".join(s.text for s in spans if s.page_num == 0)
    page1_text = " ".join(s.text for s in spans if s.page_num == 1)
    assert "unique_token_page0" in page0_text
    assert "unique_token_page1" in page1_text
    # Cross-page contamination check
    assert "unique_token_page0" not in page1_text
    assert "unique_token_page1" not in page0_text


# ── get_full_page_text ────────────────────────────────────────────────────────

def test_get_full_page_text(sample_pdf):
    text = get_full_page_text(sample_pdf, 0)
    assert "Hello" in text or "unique_token_page0" in text


def test_get_full_page_text_page1(sample_pdf):
    text = get_full_page_text(sample_pdf, 1)
    assert "unique_token_page1" in text


# ── render_page_image (cache miss then hit) ──────────────────────────────────

def test_render_page_image_returns_png_bytes(sample_pdf):
    img = render_page_image(sample_pdf, 0)
    assert isinstance(img, bytes)
    assert img[:4] == b"\x89PNG" or img[:4] == b"\x89PNG"[: 4]  # PNG magic bytes
    assert len(img) > 1000  # sanity: a real page image


def test_render_page_image_cache_miss_then_hit(tmp_path, monkeypatch):
    """Second call returns the same bytes, and cache file exists on disk."""
    import sar.pdf_parser as pp_mod

    # Build a fresh PDF file that has never been rendered, so there is no
    # cached entry for it yet.
    pdf_path = str(tmp_path / "cache_test.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200).insert_text(fitz.Point(10, 50), "cache_test_unique")
    doc.save(pdf_path)
    doc.close()

    # Use a temporary cache dir isolated from the real cache
    cache_dir = str(tmp_path / "pagecache")
    monkeypatch.setattr(pp_mod, "_PAGE_CACHE_DIR", cache_dir)

    # First call: cache miss — must render and write the file
    img1 = pp_mod.render_page_image(pdf_path, 0)
    assert img1[:4] == b"\x89PNG"[:4]

    # Cache file should now exist
    key = pp_mod._page_cache_key(pdf_path, 0, 2.0)
    cache_path = os.path.join(cache_dir, f"{key}.png")
    assert os.path.isfile(cache_path), "cache file not written after first render"

    # Second call: cache hit — must return the same bytes without re-rendering
    img2 = pp_mod.render_page_image(pdf_path, 0)
    assert img1 == img2, "cached bytes differ from original render"
