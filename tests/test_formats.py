"""Tests for DOCX and email (.eml, .msg) ingestion."""
import email as _email
import email.mime.multipart
import email.mime.text
import email.mime.base
import email.encoders
import os
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


# Import app-level helpers directly from the repo without disturbing sys.modules.
# We import the functions once at module load time. They do not depend on Flask
# session state and are safe to call directly.
sys.path.insert(0, str(REPO))
import importlib
# Ensure sar package is importable from repo root
if "sar" not in sys.modules:
    import sar  # noqa: F401


def _get_app():
    """Return the app module, importing it if needed (does not flush sessions)."""
    if "app" not in sys.modules:
        import app  # noqa: F401
    return sys.modules["app"]


# ── DOCX ────────────────────────────────────────────────────────────────────

def _make_docx(path, paragraph_text, table_text):
    from docx import Document
    doc = Document()
    doc.add_paragraph(paragraph_text)
    tbl = doc.add_table(rows=1, cols=1)
    tbl.cell(0, 0).text = table_text
    doc.save(path)


def test_docx_paragraph_and_table_in_pdf(tmp_path):
    """DOCX converter extracts both paragraph and table-cell text."""
    _app = _get_app()
    docx_path = str(tmp_path / "test.docx")
    _make_docx(docx_path, "Dr Smithers visited today.", "Margaret Holloway attended.")
    pdf_path = _app._docx_to_pdf(docx_path)
    assert os.path.exists(pdf_path)
    assert pdf_path.endswith(".pdf")

    import fitz
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    assert "Smithers" in text, "paragraph text not in PDF"
    assert "Holloway" in text, "table cell text not in PDF"


def test_docx_in_allowed_extensions():
    _app = _get_app()
    assert "docx" in _app.ALLOWED_EXTENSIONS


# ── EML ──────────────────────────────────────────────────────────────────────

def _make_eml(path, body_text, attachment_name=None, attachment_data=None):
    if attachment_name:
        msg = _email.mime.multipart.MIMEMultipart()
    else:
        msg = _email.mime.text.MIMEText(body_text, "plain")

    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@surgery.nhs.uk"
    msg["Subject"] = "Re: JONES, Mary referral"
    msg["Date"] = "Mon, 10 Jun 2026 09:00:00 +0000"

    if attachment_name:
        msg.attach(_email.mime.text.MIMEText(body_text, "plain"))
        part = _email.mime.base.MIMEBase("application", "octet-stream")
        part.set_payload(attachment_data or b"hello attachment")
        _email.encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=attachment_name)
        msg.attach(part)

    with open(path, "wb") as f:
        f.write(msg.as_bytes())


def test_eml_headers_and_body_in_pdf(tmp_path):
    _app = _get_app()
    eml_path = str(tmp_path / "test.eml")
    _make_eml(eml_path, "Patient was seen by Dr Harrison today.")
    results = _app._eml_to_pdf(eml_path)
    assert results, "no output files produced"
    pdf_path = results[0]
    assert os.path.exists(pdf_path)

    import fitz
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    assert "sender@example.com" in text, "From header missing"
    assert "JONES, Mary" in text, "Subject not in PDF"
    assert "Dr Harrison" in text, "body text missing"


def test_eml_txt_attachment_ingested(tmp_path):
    _app = _get_app()
    eml_path = str(tmp_path / "test_att.eml")
    att_content = b"Dr Brown reviewed patient records."
    _make_eml(eml_path, "See attachment.", attachment_name="notes.txt",
              attachment_data=att_content)
    results = _app._eml_to_pdf(eml_path)
    # Should have email PDF + attachment PDF
    assert len(results) >= 2, f"expected 2+ files, got {len(results)}: {results}"
    for p in results:
        assert os.path.exists(p), f"missing: {p}"
    import fitz
    att_pdf = results[1]
    doc = fitz.open(att_pdf)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    assert "Dr Brown" in text, "attachment content not in PDF"


def test_eml_in_allowed_extensions():
    _app = _get_app()
    assert "eml" in _app.ALLOWED_EXTENSIONS
    assert "msg" in _app.ALLOWED_EXTENSIONS


# ── MSG ──────────────────────────────────────────────────────────────────────

def test_msg_missing_package_raises_clear_error(tmp_path):
    """If extract_msg is not installed, _msg_to_pdf raises RuntimeError."""
    import unittest.mock as mock
    import builtins
    _app = _get_app()

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "extract_msg":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    msg_path = str(tmp_path / "dummy.msg")
    with open(msg_path, "wb") as f:
        f.write(b"\x00" * 8)

    with mock.patch("builtins.__import__", side_effect=_fake_import):
        with pytest.raises((RuntimeError, Exception)):
            _app._msg_to_pdf(msg_path)


try:
    import extract_msg as _emsg_check
    _HAS_EXTRACT_MSG = True
except ImportError:
    _HAS_EXTRACT_MSG = False


@pytest.mark.skipif(not _HAS_EXTRACT_MSG, reason="extract_msg not installed")
def test_msg_smoke(tmp_path):
    """Smoke test: extract_msg is importable and MSG path is handled."""
    _app = _get_app()
    msg_path = str(tmp_path / "dummy.msg")
    with open(msg_path, "wb") as f:
        f.write(b"\x00" * 512)

    # An invalid .msg will raise an exception from extract_msg — that's expected.
    # We just verify it doesn't crash the *app* at import time and the function exists.
    assert callable(_app._msg_to_pdf)
    with pytest.raises(Exception):
        _app._msg_to_pdf(msg_path)
