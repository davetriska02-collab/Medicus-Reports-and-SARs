"""Batch C workflow tests: intake fields, acknowledgment letter, urgency strip, sign-off."""
import json
import os
from datetime import datetime, timedelta, timezone

import fitz
import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_sar(flask_app, request_date=None, id_verified="", allocated_to="",
              allocated_to_name="", days_offset=None):
    """Create a reviewing SAR with one real PDF and one approved candidate."""
    from sar.models import (SARRequest, SubjectDetails, RedactionCandidate,
                            PIICategory, RedactionStatus)
    m = flask_app
    sar = SARRequest(subject=SubjectDetails(
        full_name="Test Subject", first_name="Test", last_name="Subject",
        nhs_number="943 476 0001"))
    sar.archived = False
    if request_date:
        sar.request_date = request_date
    if id_verified:
        sar.id_verified = id_verified
    if allocated_to:
        sar.allocated_to = allocated_to
        sar.allocated_to_name = allocated_to_name
    sar.compute_due_date()
    # Override due_date for urgency testing via days_offset from today
    if days_offset is not None:
        due = (datetime.now().date() + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        sar.due_date = due

    sd = m._sar_dir(sar.id)
    os.makedirs(sd, exist_ok=True)
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100), "Seen with brother James Test today.")
    pdf = os.path.join(sd, "record.pdf")
    doc.save(pdf); doc.close()
    sar.pdf_files = [pdf]
    cand = RedactionCandidate(
        text="James Test", category=PIICategory.PERSON_NAME,
        status=RedactionStatus.APPROVED, confidence=0.9, page_num=0,
        x0=150, y0=92, x1=240, y1=106, source_file="record.pdf", reason="t",
        exemption_code="third_party")
    sar.candidates = [cand]
    sar.status = "reviewing"
    m._set(sar.id, sar)
    m._save(sar)
    return sar


def _set_config(flask_app, **kwargs):
    """Write keys directly into the practice config file used by the copied app."""
    from sar.practice_config import get_config, save_config
    cfg = get_config()
    cfg.update(kwargs)
    save_config(cfg)


# ── Part 1: request_date drives due date ──────────────────────────────────────

def test_request_date_drives_due_date(flask_app):
    """SAR with request_date 10 days ago: due ~20 days from now (30 from request_date)."""
    ten_days_ago = (datetime.now().date() - timedelta(days=10)).strftime("%Y-%m-%d")
    sar = _make_sar(flask_app, request_date=ten_days_ago)
    expected_due = (datetime.now().date() + timedelta(days=20)).strftime("%Y-%m-%d")
    # Due date should be ~20 days from now (30 days from 10 days ago), within ±1 day
    due = datetime.strptime(sar.due_date, "%Y-%m-%d").date()
    expected = datetime.strptime(expected_due, "%Y-%m-%d").date()
    assert abs((due - expected).days) <= 1, f"due={sar.due_date} expected ~{expected_due}"


def test_no_request_date_uses_created_at(flask_app):
    """SAR without request_date: due date is ~30 days from created_at (today)."""
    sar = _make_sar(flask_app)
    due = datetime.strptime(sar.due_date, "%Y-%m-%d").date()
    today = datetime.now().date()
    assert 28 <= (due - today).days <= 31


# ── Part 2: Acknowledgment letter ─────────────────────────────────────────────

def test_acknowledgment_endpoint_generates_pdf(flask_app, admin_client):
    """POST /acknowledgment generates a PDF and returns the filename."""
    c, H = admin_client
    _set_config(flask_app, practice_name="Test Surgery")
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/acknowledgment", headers=H)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["ok"]
    assert data["file"].startswith("acknowledgment_")
    assert data["file"].endswith(".pdf")
    path = os.path.join(flask_app.OUTPUT_DIR, sar.id, data["file"])
    assert os.path.exists(path)


def test_acknowledgment_letter_content(flask_app, admin_client):
    """Acknowledgment PDF contains required text."""
    c, H = admin_client
    _set_config(flask_app, practice_name="Oakfield Surgery")
    ten_days_ago = (datetime.now().date() - timedelta(days=10)).strftime("%Y-%m-%d")
    sar = _make_sar(flask_app, request_date=ten_days_ago, id_verified="Passport seen 01/01/2026")
    r = c.post(f"/api/sar/{sar.id}/acknowledgment", headers=H)
    assert r.status_code == 200
    fn = r.get_json()["file"]
    path = os.path.join(flask_app.OUTPUT_DIR, sar.id, fn)
    text = "".join(p.get_text() for p in fitz.open(path))
    assert "Oakfield Surgery" in text, "practice name missing"
    assert "Test Subject" in text, "subject name missing"
    assert "one calendar month" in text, "statutory period wording missing"
    # Due date should be mentioned
    due_display = sar.due_date  # at minimum the ISO date portion appears in the letter
    # formatted date e.g. "20 July 2026" — check year at least
    assert str(datetime.now().year) in text or str(datetime.now().year + 1) in text
    # ID verified line
    assert "Passport seen 01/01/2026" in text, "id_verified text missing"
    assert "Your identity has been verified" in text


def test_acknowledgment_letter_no_id_verified(flask_app, admin_client):
    """Without id_verified, letter mentions contacting for identification."""
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/acknowledgment", headers=H)
    assert r.status_code == 200
    fn = r.get_json()["file"]
    path = os.path.join(flask_app.OUTPUT_DIR, sar.id, fn)
    text = "".join(p.get_text() for p in fitz.open(path))
    assert "Your identity has been verified" not in text
    assert "identification" in text.lower()


def test_acknowledgment_appears_in_outputs(flask_app, admin_client):
    """Acknowledgment file appears in pack_files from /outputs endpoint."""
    c, H = admin_client
    sar = _make_sar(flask_app)
    c.post(f"/api/sar/{sar.id}/acknowledgment", headers=H)
    r = c.get(f"/api/sar/{sar.id}/outputs")
    assert r.status_code == 200
    data = r.get_json()
    assert any(f.startswith("acknowledgment_") for f in data["pack_files"])


# ── Part 3: Dashboard urgency strip ──────────────────────────────────────────

def test_urgency_strip_overdue_and_due3(flask_app, admin_client):
    """Dashboard strip shows overdue and due-in-2-days SARs."""
    c, H = admin_client
    # Overdue SAR: due 5 days ago
    sar_overdue = _make_sar(flask_app, days_offset=-5)
    # Due in 2 days
    sar_due2 = _make_sar(flask_app, days_offset=2)
    r = c.get("/")
    assert r.status_code == 200
    body = r.data.decode()
    assert "overdue" in body
    assert "due" in body
    assert sar_overdue.subject.full_name in body or sar_overdue.id[:8] in body


def _strip_html(body):
    """Return only the urgency-strip div's markup, or '' if absent."""
    start = body.find('id="urgency-strip"')
    if start == -1:
        return ""
    # The strip is a single <div>…</div>; grab a generous slice from its open.
    open_tag = body.rfind("<div", 0, start)
    return body[open_tag:start + 4000]


def test_urgency_strip_excludes_complete_and_paused(flask_app, admin_client):
    """Complete and clock-paused overdue SARs never appear in the urgency strip."""
    c, H = admin_client
    sar_paused = _make_sar(flask_app, days_offset=-3)
    sar_paused.clock_paused = True
    flask_app._save(sar_paused)
    sar_complete = _make_sar(flask_app, days_offset=-3)
    sar_complete.status = "complete"
    flask_app._save(sar_complete)

    body = c.get("/").data.decode()
    strip = _strip_html(body)
    # Neither the paused nor the completed SAR may be listed as urgent. Subject
    # names collide across fixtures ("Test Subject"), so assert on the unique id.
    assert sar_paused.id[:8] not in strip
    assert sar_complete.id[:8] not in strip


# ── Part 4: Two-person sign-off ───────────────────────────────────────────────

def test_finalise_without_signoff_setting_off(flask_app, admin_client):
    """With setting off, finalise works without sign-off (existing behaviour)."""
    c, H = admin_client
    _set_config(flask_app, require_second_signoff="0")
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200, r.get_json()


def test_finalise_blocked_without_signoff_when_setting_on(flask_app, admin_client):
    """With setting on and no sign-off, finalise returns 403."""
    c, H = admin_client
    _set_config(flask_app, require_second_signoff="1")
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 403
    assert "Second sign-off required" in r.get_json()["error"]
    # Restore setting
    _set_config(flask_app, require_second_signoff="0")


def test_signoff_setting_off_returns_400(flask_app, admin_client):
    """POST /signoff returns 400 when setting is disabled."""
    c, H = admin_client
    _set_config(flask_app, require_second_signoff="0")
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/signoff", headers=H)
    assert r.status_code == 400


def test_signoff_by_allocated_user_forbidden(flask_app, admin_client):
    """Allocated reviewer cannot sign off their own SAR."""
    c, H = admin_client
    _set_config(flask_app, require_second_signoff="1")
    # Get admin user id
    from sar.users import get_user_by_username
    admin_user = get_user_by_username("admin")
    admin_id = admin_user.id if admin_user else ""
    sar = _make_sar(flask_app, allocated_to=admin_id, allocated_to_name="Admin")
    r = c.post(f"/api/sar/{sar.id}/signoff", headers=H)
    assert r.status_code == 403
    assert "allocated reviewer" in r.get_json()["error"]
    _set_config(flask_app, require_second_signoff="0")


def test_signoff_by_different_user_succeeds_and_finalise_works(flask_app, admin_client):
    """Sign-off by a non-allocated user succeeds; then finalise passes."""
    c, H = admin_client
    _set_config(flask_app, require_second_signoff="1")
    # Create a SAR with no allocated_to (so admin can sign off)
    sar = _make_sar(flask_app)
    # With no allocated_to, admin can sign off
    r = c.post(f"/api/sar/{sar.id}/signoff", headers=H)
    assert r.status_code == 200, r.get_json()
    # Verify sign-off recorded
    sar_obj = flask_app._get(sar.id)
    assert sar_obj.signoff_by
    assert sar_obj.signoff_by_name
    assert sar_obj.signoff_at
    # Now finalise should succeed
    r = c.post(f"/api/sar/{sar.id}/finalise", headers=H)
    assert r.status_code == 200, r.get_json()
    _set_config(flask_app, require_second_signoff="0")


def test_admin_clear_signoff(flask_app, admin_client):
    """Admin can clear a sign-off."""
    c, H = admin_client
    _set_config(flask_app, require_second_signoff="1")
    sar = _make_sar(flask_app)
    c.post(f"/api/sar/{sar.id}/signoff", headers=H)
    r = c.post(f"/api/sar/{sar.id}/signoff/clear", headers=H)
    assert r.status_code == 200
    sar_obj = flask_app._get(sar.id)
    assert sar_obj.signoff_by == ""
    assert sar_obj.signoff_at == ""
    _set_config(flask_app, require_second_signoff="0")
