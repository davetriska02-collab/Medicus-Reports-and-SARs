"""Tests for the guided fix queue for unplaced redactions (failure triage)."""
import os

import fitz
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_sar(flask_app, with_failure=False, unfindable_text=False):
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

    # Build a PDF with known text
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100),
                               "Seen with brother Brian Walker today.")
    pdf = os.path.join(sd, "record.pdf")
    doc.save(pdf)
    doc.close()
    sar.pdf_files = [pdf]

    text = "NotFindableAnywhere Xyz" if (with_failure or unfindable_text) else "Brian Walker"
    x0, y0, x1, y1 = (0, 0, 0, 0) if with_failure else (150, 92, 240, 106)
    cand = RedactionCandidate(
        text=text, category=PIICategory.PERSON_NAME,
        status=RedactionStatus.APPROVED, confidence=0.9, page_num=0,
        x0=x0, y0=y0, x1=x1, y1=y1, source_file="record.pdf", reason="t",
        context="brother Brian Walker today")
    sar.candidates = [cand]
    sar.status = "reviewing"
    m._set(sar.id, sar)
    m._save(sar)
    return sar


# ── 1. Finalise failure entries include context ───────────────────────────────

def test_finalise_failure_entry_includes_context(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200
    data = r.get_json()
    failures = data["failed_redactions"]
    assert len(failures) == 1
    entry = failures[0]
    assert "context" in entry
    # context was set on the candidate
    assert entry["context"] == "brother Brian Walker today"


def test_finalise_sets_needs_refinalise_false(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200
    # Reload SAR
    sar_reloaded = flask_app._get(sar.id)
    assert getattr(sar_reloaded, 'needs_refinalise', False) is False


# ── 2. Resolve endpoint ───────────────────────────────────────────────────────

def test_resolve_removes_failure_sets_needs_refinalise_audits(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    # Finalise to create failures
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200
    failures = r.get_json()["failed_redactions"]
    assert len(failures) == 1
    cand_id = failures[0]["id"]

    # Resolve
    r2 = c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H,
                json={})
    assert r2.status_code == 200
    assert r2.get_json()["ok"] is True

    # SAR now has no failures, but needs_refinalise=True
    sar_r = flask_app._get(sar.id)
    assert getattr(sar_r, 'redaction_failures', []) == []
    assert getattr(sar_r, 'needs_refinalise', False) is True


def test_resolve_idempotent(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    sar_r = flask_app._get(sar.id)
    cand_id = sar_r.redaction_failures[0]["id"]

    # First call
    r1 = c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H, json={})
    assert r1.status_code == 200

    # Second call (idempotent — already removed)
    r2 = c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H, json={})
    assert r2.status_code == 200
    d = r2.get_json()
    assert d["ok"] is True
    assert "already resolved" in d.get("note", "")


def test_resolve_unknown_sar_404(flask_app, admin_client):
    c, H = admin_client
    r = c.post("/api/sar/nonexistent_id/failures/abc/resolve", headers=H, json={})
    assert r.status_code == 404


# ── 3. Dismiss variant ────────────────────────────────────────────────────────

def test_dismiss_variant_removes_and_audits_differently(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    sar_r = flask_app._get(sar.id)
    cand_id = sar_r.redaction_failures[0]["id"]

    r = c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H,
               json={"dismissed": True})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    sar_r2 = flask_app._get(sar.id)
    assert sar_r2.redaction_failures == []
    assert sar_r2.needs_refinalise is True

    # Check audit log contains dismiss action
    from sar.audit import read_events as _audit_read
    events = _audit_read(limit=20)
    assert any(e["action"] == "redaction_failure_dismissed" for e in events)


# ── 4. Response-pack and print-bundle blocked when needs_refinalise=True ──────

def test_pack_blocked_when_needs_refinalise(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    # Finalise (creates failures)
    c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    sar_r = flask_app._get(sar.id)
    cand_id = sar_r.redaction_failures[0]["id"]

    # Dismiss the failure (clears redaction_failures but sets needs_refinalise)
    c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H,
           json={"dismissed": True})

    # Pack should be blocked (needs_refinalise is True)
    r = c.post(f"/api/sar/{sar.id}/response-pack", headers=H, json={})
    assert r.status_code == 409
    assert "re-finalise" in r.get_json()["error"].lower()


def test_bundle_blocked_when_needs_refinalise(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    sar_r = flask_app._get(sar.id)
    cand_id = sar_r.redaction_failures[0]["id"]
    c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H,
           json={"dismissed": True})

    r = c.post(f"/api/sar/{sar.id}/print-bundle", headers=H, json={})
    assert r.status_code == 409


def test_pack_succeeds_after_refinalise_following_dismiss(flask_app, admin_client):
    """After dismissing an unfindable failure and re-finalising, pack generates."""
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    # Finalise → creates failure
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200
    assert len(r.get_json()["failed_redactions"]) == 1
    sar_r = flask_app._get(sar.id)
    cand_id = sar_r.redaction_failures[0]["id"]

    # Dismiss the failure
    c.post(f"/api/sar/{sar.id}/failures/{cand_id}/resolve", headers=H,
           json={"dismissed": True})

    # Re-finalise (failure text not in doc, no new failures)
    r2 = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r2.status_code == 200
    assert r2.get_json()["failed_redactions"] == []

    sar_r2 = flask_app._get(sar.id)
    assert sar_r2.needs_refinalise is False
    assert sar_r2.redaction_failures == []

    # Pack should now succeed
    r3 = c.post(f"/api/sar/{sar.id}/response-pack", headers=H, json={})
    assert r3.status_code == 200


# ── 5. find-on-page endpoint ──────────────────────────────────────────────────

def test_find_on_page_returns_rects_for_present_text(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    # "Brian Walker" is in the PDF
    r = c.get(f"/api/sar/{sar.id}/find-on-page?file=record.pdf&page=0&text=Brian+Walker")
    assert r.status_code == 200
    data = r.get_json()
    assert "rects" in data
    assert len(data["rects"]) >= 1
    rect = data["rects"][0]
    for key in ("x0", "y0", "x1", "y1"):
        assert key in rect


def test_find_on_page_returns_empty_for_absent_text(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.get(f"/api/sar/{sar.id}/find-on-page?file=record.pdf&page=0&text=NotHereAtAllXyz")
    assert r.status_code == 200
    assert r.get_json()["rects"] == []


def test_find_on_page_returns_empty_for_bad_page(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.get(f"/api/sar/{sar.id}/find-on-page?file=record.pdf&page=99&text=Brian")
    assert r.status_code == 200
    assert r.get_json()["rects"] == []


# ── 6. Review page renders with ?fix=all for SAR with failures ────────────────

def test_review_page_with_fix_all_returns_200(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app, with_failure=True)
    c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    r = c.get(f"/review/{sar.id}?fix=all")
    assert r.status_code == 200
    # Failures should be embedded in the page as window.REDACTION_FAILURES
    html = r.data.decode()
    assert "REDACTION_FAILURES" in html
    assert "NotFindableAnywhere Xyz" in html
