"""IG report: turnaround stats page and CSV export."""
import os

import fitz


def _completed_sar(flask_app):
    from sar.models import (SARRequest, SubjectDetails, RedactionCandidate,
                            PIICategory, RedactionStatus)
    m = flask_app
    sar = SARRequest(subject=SubjectDetails(full_name="Carol Stats",
                                            first_name="Carol", last_name="Stats"))
    sar.archived = False
    sar.compute_due_date()
    sd = m._sar_dir(sar.id)
    os.makedirs(sd, exist_ok=True)
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100), "Nothing sensitive here.")
    pdf = os.path.join(sd, "r.pdf")
    doc.save(pdf)
    doc.close()
    sar.pdf_files = [pdf]
    sar.candidates = [RedactionCandidate(
        text="x", category=PIICategory.PERSON_NAME,
        status=RedactionStatus.APPROVED, confidence=0.9, page_num=0,
        x0=80, y0=92, x1=120, y1=106, source_file="r.pdf", reason="t")]
    sar.status = "reviewing"
    m._set(sar.id, sar)
    m._save(sar)
    return sar


def test_ig_report_counts_completed_sar(flask_app, admin_client):
    c, H = admin_client
    sar = _completed_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200

    # completed_at recorded
    assert flask_app._get(sar.id).completed_at

    r = c.get("/admin/ig-report")
    assert r.status_code == 200
    assert b"Carol Stats" in r.data
    assert b"Within statutory deadline" in r.data

    r = c.get("/admin/ig-report.csv")
    assert r.status_code == 200
    body = r.data.decode()
    assert "sar_id,subject,received,completed" in body
    assert "Carol Stats" in body
    line = next(l for l in body.splitlines() if "Carol Stats" in l)
    assert ",yes," in line  # completed same day → within deadline
