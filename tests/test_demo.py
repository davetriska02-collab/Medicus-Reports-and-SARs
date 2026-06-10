"""Tests for Batch D: demo mode, update.bat sanity check."""
import os
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


# ── Helpers ────────────────────────────────────────────────────────────────────

def _distinct_categories(sar):
    return {c.category.value for c in sar.candidates}


# ── Demo SAR unit tests ────────────────────────────────────────────────────────

def test_create_demo_sar_returns_id(flask_app):
    """create_demo_sar returns a non-empty string id."""
    from sar.demo import create_demo_sar
    sid = create_demo_sar(flask_app.UPLOAD_DIR, flask_app._set, flask_app._save)
    assert isinstance(sid, str) and sid


def test_demo_sar_has_pdf_on_disk(flask_app):
    """The demo SAR has at least one PDF file that exists on disk."""
    from sar.demo import create_demo_sar
    sid = create_demo_sar(flask_app.UPLOAD_DIR, flask_app._set, flask_app._save)
    sar = flask_app._get(sid)
    assert sar is not None
    assert len(sar.pdf_files) >= 1
    for p in sar.pdf_files:
        assert os.path.exists(p), f"PDF missing: {p}"


def test_demo_sar_has_diverse_candidates(flask_app):
    """Demo SAR candidates cover at least 3 distinct PII categories."""
    from sar.demo import create_demo_sar
    sid = create_demo_sar(flask_app.UPLOAD_DIR, flask_app._set, flask_app._save)
    sar = flask_app._get(sid)
    cats = _distinct_categories(sar)
    assert len(cats) >= 3, f"Only {len(cats)} distinct categories: {cats}"


def test_demo_sar_subject_name_contains_synthetic(flask_app):
    """Demo SAR subject name contains the word SYNTHETIC (unmistakably fake)."""
    from sar.demo import create_demo_sar
    sid = create_demo_sar(flask_app.UPLOAD_DIR, flask_app._set, flask_app._save)
    sar = flask_app._get(sid)
    assert "SYNTHETIC" in sar.subject.full_name.upper()


def test_demo_sar_is_reviewing(flask_app):
    """Demo SAR lands on the dashboard in 'reviewing' state with candidates."""
    from sar.demo import create_demo_sar
    sid = create_demo_sar(flask_app.UPLOAD_DIR, flask_app._set, flask_app._save)
    sar = flask_app._get(sid)
    assert sar.status == "reviewing"
    assert len(sar.candidates) > 0


# ── /api/demo-sar route tests ──────────────────────────────────────────────────

def test_api_demo_sar_creates_sar(flask_app, admin_client):
    """POST /api/demo-sar as admin returns ok + sar_id."""
    c, h = admin_client
    r = c.post("/api/demo-sar", headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert "sar_id" in data and data["sar_id"]


def test_api_demo_sar_idempotent(flask_app, admin_client):
    """A second POST /api/demo-sar returns the same sar_id, not a duplicate."""
    c, h = admin_client
    r1 = c.post("/api/demo-sar", headers=h)
    r2 = c.post("/api/demo-sar", headers=h)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.get_json()["sar_id"] == r2.get_json()["sar_id"]


def test_api_demo_sar_requires_admin(flask_app):
    """Non-admin (unauthenticated) POST /api/demo-sar gets 302 or 403."""
    c = flask_app.app.test_client()
    # Need a valid CSRF token — get one from login page
    r = c.get("/login")
    import re
    m = re.search(rb'name="_csrf_token" value="([^"]+)"', r.data)
    csrf = m.group(1).decode() if m else ""
    resp = c.post("/api/demo-sar", headers={"X-CSRF-Token": csrf})
    assert resp.status_code in (302, 403)


# ── update.bat sanity check ────────────────────────────────────────────────────

def test_update_bat_exists():
    """update.bat is present at the repo root."""
    p = REPO / "update.bat"
    assert p.exists(), "update.bat not found at repo root"


def test_update_bat_references_correct_repo():
    """update.bat references the correct GitHub repository URL."""
    text = (REPO / "update.bat").read_text(encoding="utf-8", errors="replace")
    assert "davetriska02-collab/Medicus-Reports-and-SARs" in text, (
        "update.bat does not reference the correct repository"
    )
