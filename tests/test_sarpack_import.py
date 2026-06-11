"""Tests for H5 fix: .sarpack import id validation (path traversal guard)."""
import io
import json
import os
import zipfile

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_sarpack(sar_id, extra_sd=None):
    """Build an in-memory .sarpack zip with the given SAR id."""
    sd = {
        "id": sar_id,
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_modified": "2026-01-01T00:00:00+00:00",
        "status": "reviewing",
        "archived": False,
        "redaction_failures": [],
        "needs_refinalise": False,
        "unscreened_pages": [],
        "due_date": "",
        "notes": "",
        "workflow_status": "new",
        "completed_at": "",
        "request_date": "",
        "id_verified": "",
        "scope_notes": "",
        "signoff_by": "",
        "signoff_by_name": "",
        "signoff_at": "",
        "allocated_to": "",
        "allocated_to_name": "",
        "clock_paused": False,
        "paused_at": "",
        "total_paused_days": 0,
        "pause_log": [],
        "subject": {
            "full_name": "Test Subject",
            "first_name": "Test",
            "last_name": "Subject",
            "nhs_number": "",
            "date_of_birth": "",
            "address": "",
            "phone": "",
            "email": "",
            "aliases": [],
        },
        "detection_settings": {
            "auto_redact_threshold": 0.9,
            "flag_threshold": 0.6,
            "enabled_categories": [],
        },
        "document_dates": {},
        "file_order": [],
        "main_record_file": "",
        "pdf_files": [],
        "candidates": [],
    }
    if extra_sd:
        sd.update(extra_sd)

    manifest = {"format_version": "1", "app_version": "2.5.4", "sar_id": sar_id}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("sar.json", json.dumps(sd))
    buf.seek(0)
    return buf


# ── 1. Traversal id is rejected with 400 ─────────────────────────────────────

def test_import_rejects_traversal_id(flask_app, admin_client, tmp_path):
    """A sarpack with id '../../evil' must be rejected with 400 and not create
    any directory outside UPLOAD_DIR."""
    c, H = admin_client
    evil_id = "../../evil"
    buf = _make_sarpack(evil_id)

    r = c.post(
        "/api/sar/import",
        headers=H,
        data={"sarpack": (buf, "evil.sarpack")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400, (
        f"Expected 400 for traversal id, got {r.status_code}: {r.get_data(as_text=True)}"
    )
    data = r.get_json()
    assert "error" in data
    assert "id" in data["error"].lower() or "invalid" in data["error"].lower()

    # Belt-and-braces: no 'evil' directory must exist anywhere near UPLOAD_DIR
    upload_parent = os.path.dirname(os.path.realpath(flask_app.UPLOAD_DIR))
    evil_path = os.path.join(upload_parent, "evil")
    assert not os.path.exists(evil_path), (
        f"Traversal succeeded: directory created at {evil_path}"
    )


def test_import_rejects_dotdot_slash_id(flask_app, admin_client):
    """Various traversal-style ids are rejected."""
    c, H = admin_client
    for bad_id in ["../escape", "a/b", "a\\b", "", "."]:
        buf = _make_sarpack(bad_id)
        r = c.post(
            "/api/sar/import",
            headers=H,
            data={"sarpack": (buf, "bad.sarpack")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400, (
            f"id={bad_id!r} should have been rejected with 400, got {r.status_code}"
        )


# ── 2. Happy-path: normal uuid-style id succeeds ─────────────────────────────

def test_import_accepts_valid_id(flask_app, admin_client):
    """A sarpack with a normal uuid-style id imports successfully."""
    c, H = admin_client
    valid_id = "test-sarpack-import-01"
    # Make sure it doesn't already exist
    if flask_app._get(valid_id):
        pytest.skip("SAR already exists in store — id collision, skip")

    buf = _make_sarpack(valid_id)
    r = c.post(
        "/api/sar/import",
        headers=H,
        data={"sarpack": (buf, "good.sarpack")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, (
        f"Valid import failed: {r.status_code} {r.get_data(as_text=True)}"
    )
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("sar_id") == valid_id

    # SAR should now be in store
    sar = flask_app._get(valid_id)
    assert sar is not None, "Imported SAR not found in store"
