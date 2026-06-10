"""Redaction safety: failures must be reported, never silently swallowed,
and applied redactions must actually remove text from the content stream."""
import fitz
import pytest

from sar.redactor import apply_redactions
from sar.redaction_log import generate_redaction_log
from sar.models import RedactionCandidate, PIICategory, RedactionStatus


def _candidate(**kw):
    base = dict(category=PIICategory.PERSON_NAME, status=RedactionStatus.APPROVED,
                confidence=0.9, page_num=0, source_file="doc.pdf", reason="test")
    base.update(kw)
    return RedactionCandidate(**base)


@pytest.fixture()
def sample_pdf(tmp_path):
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text(fitz.Point(72, 100), "Patient seen with mother Jane Bloggs today.")
    p = tmp_path / "doc.pdf"
    doc.save(str(p))
    doc.close()
    return str(p)


def test_redaction_paths_and_failures(sample_pdf, tmp_path):
    cands = [
        _candidate(text="Jane Bloggs", x0=200, y0=90, x1=280, y1=105),  # coords
        _candidate(text="mother"),                                       # search fallback
        _candidate(text="NotOnThePage Xyz"),                             # unfindable → fail
        _candidate(text="ghost", page_num=7),                            # bad page → fail
    ]
    out, failed = apply_redactions(sample_pdf, cands, str(tmp_path))
    assert {c.text for c in failed} == {"NotOnThePage Xyz", "ghost"}

    rd = fitz.open(out)
    txt = rd[0].get_text()
    rd.close()
    assert "Jane Bloggs" not in txt
    assert "mother" not in txt
    assert "Patient seen" in txt  # non-redacted text untouched


def test_log_reports_failures_honestly(sample_pdf, tmp_path):
    cands = [
        _candidate(text="Jane Bloggs", x0=200, y0=90, x1=280, y1=105),
        _candidate(text="NotOnThePage Xyz"),
    ]
    _, failed = apply_redactions(sample_pdf, cands, str(tmp_path))
    lp = generate_redaction_log(cands, str(tmp_path), "testsar",
                                failed_ids={c.id for c in failed})
    log_doc = fitz.open(lp)
    log_text = "".join(p.get_text() for p in log_doc)
    log_doc.close()
    assert "REDACTION FAILURES" in log_text
    assert "NotOnThePage Xyz" in log_text
    assert "Redactions applied: 1" in log_text
    assert "NOT applied): 1" in log_text


def test_no_failures_means_clean_log(sample_pdf, tmp_path):
    cands = [_candidate(text="Jane Bloggs", x0=200, y0=90, x1=280, y1=105)]
    _, failed = apply_redactions(sample_pdf, cands, str(tmp_path))
    assert failed == []
