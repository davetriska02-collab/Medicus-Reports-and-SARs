"""ICO response pack: cover letter + certificate generation and guards."""
import os

import fitz
import pytest


def _make_sar(flask_app, with_failure=False):
    """Create a finalisable SAR with one real PDF and one approved candidate."""
    from sar.models import (SARRequest, SubjectDetails, RedactionCandidate,
                            PIICategory, RedactionStatus)
    m = flask_app
    sar = SARRequest(subject=SubjectDetails(
        full_name="Alice Example", first_name="Alice", last_name="Example",
        nhs_number="943 476 5919", date_of_birth="1980-02-01",
        address="1 Test Lane\nGuildford"))
    sar.archived = False
    sar.compute_due_date()
    sd = m._sar_dir(sar.id)
    os.makedirs(sd, exist_ok=True)
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100),
                               "Seen with brother Brian Walker today.")
    pdf = os.path.join(sd, "record.pdf")
    doc.save(pdf)
    doc.close()
    sar.pdf_files = [pdf]
    cand = RedactionCandidate(
        text="Brian Walker", category=PIICategory.PERSON_NAME,
        status=RedactionStatus.APPROVED, confidence=0.9, page_num=0,
        x0=150, y0=92, x1=240, y1=106, source_file="record.pdf", reason="t",
        exemption_code="third_party")
    if with_failure:
        cand.x0 = cand.y0 = cand.x1 = cand.y1 = 0.0
        cand.text = "NotFindableAnywhere Xyz"
    sar.candidates = [cand]
    sar.status = "reviewing"
    m._set(sar.id, sar)
    m._save(sar)
    return sar


def test_pack_requires_finalise_first(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/response-pack", headers=H, json={})
    assert r.status_code == 400
    assert "Finalise" in r.get_json()["error"]


def test_pack_generates_letter_and_certificate(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200 and r.get_json()["failed_redactions"] == []

    r = c.post(f"/api/sar/{sar.id}/response-pack", headers=H,
               json={"custom_paragraph": "We have included custom wording."})
    assert r.status_code == 200, r.get_json()
    files = r.get_json()["files"]
    assert any(f.startswith("cover_letter_") for f in files)
    assert any(f.startswith("certificate_of_redaction_") for f in files)

    od = os.path.join(flask_app.OUTPUT_DIR, sar.id)
    letter_text = "".join(p.get_text() for p in
                          fitz.open(os.path.join(od, f"cover_letter_{sar.id}.pdf")))
    assert "Alice Example" in letter_text
    assert "Article 15" in letter_text
    assert "custom wording" in letter_text
    assert "Information Commissioner" in letter_text

    cert_text = "".join(p.get_text() for p in
                        fitz.open(os.path.join(od, f"certificate_of_redaction_{sar.id}.pdf")))
    assert "CERTIFICATE OF REDACTION" in cert_text
    assert "Redactions applied: 1" in cert_text
    assert "Third-party data" in cert_text
    assert "Authorised by" in cert_text

    # Pack files appear in the outputs listing
    d = c.get(f"/api/sar/{sar.id}/outputs").get_json()
    assert len(d["pack_files"]) == 2


def test_pack_refused_when_redactions_failed(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert len(r.get_json()["failed_redactions"]) == 1

    r = c.post(f"/api/sar/{sar.id}/response-pack", headers=H, json={})
    assert r.status_code == 409
    assert "failed" in r.get_json()["error"]
