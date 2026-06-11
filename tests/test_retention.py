"""GDPR retention sweep tests (H7 / M2.1)."""
import json
import os
import threading
from datetime import datetime, timedelta, timezone

import fitz
import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _dt_ago(days: int) -> str:
    """ISO timestamp for *days* days ago (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _make_complete_sar(flask_app, completed_days_ago: int, sid: str | None = None):
    """Create a completed SAR whose completed_at is *completed_days_ago* days ago."""
    from sar.models import (SARRequest, SubjectDetails, RedactionCandidate,
                            PIICategory, RedactionStatus)
    m = flask_app
    sar = SARRequest(subject=SubjectDetails(
        full_name="Retention Test", first_name="Retention", last_name="Test",
        nhs_number="943 476 0002"))
    if sid:
        sar.id = sid
    sar.archived = False
    sar.status = "complete"
    sar.completed_at = _dt_ago(completed_days_ago)
    sar.compute_due_date()

    sd = m._sar_dir(sar.id)
    os.makedirs(sd, exist_ok=True)
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100), "Retention test content.")
    pdf = os.path.join(sd, "record.pdf")
    doc.save(pdf)
    doc.close()
    sar.pdf_files = [pdf]
    sar.candidates = []
    m._set(sar.id, sar)
    m._save(sar)
    return sar


# ── find_expired unit tests (no Flask needed) ────────────────────────────────

class _FakeSAR:
    def __init__(self, sid, status, completed_at="", last_modified=""):
        self.id = sid
        self.status = status
        self.completed_at = completed_at
        self.last_modified = last_modified


def test_find_expired_expired():
    """A completed SAR 181 days old is returned."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "complete", completed_at=_dt_ago(181))
    result = ret.find_expired([sar], 180, now=now)
    assert result == ["s1"]


def test_find_expired_not_yet():
    """A completed SAR 179 days old is NOT returned."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "complete", completed_at=_dt_ago(179))
    result = ret.find_expired([sar], 180, now=now)
    assert result == []


def test_find_expired_non_complete_old_sar_ignored():
    """A non-complete SAR that is 500 days old is never returned."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "reviewing", completed_at=_dt_ago(500))
    result = ret.find_expired([sar], 180, now=now)
    assert result == []


def test_find_expired_empty_timestamps_never_deleted():
    """A completed SAR with both completed_at and last_modified empty is never deleted."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "complete", completed_at="", last_modified="")
    result = ret.find_expired([sar], 180, now=now)
    assert result == []


def test_find_expired_unparseable_timestamp_never_deleted():
    """A completed SAR with an unparseable timestamp is never deleted."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "complete", completed_at="not-a-date", last_modified="also-bad")
    result = ret.find_expired([sar], 180, now=now)
    assert result == []


def test_find_expired_falls_back_to_last_modified():
    """When completed_at is empty, last_modified is used."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "complete", completed_at="", last_modified=_dt_ago(200))
    result = ret.find_expired([sar], 180, now=now)
    assert result == ["s1"]


def test_find_expired_disabled_returns_empty():
    """retention_days=0 returns empty list immediately."""
    import sar.retention as ret
    now = datetime.now(timezone.utc)
    sar = _FakeSAR("s1", "complete", completed_at=_dt_ago(9999))
    result = ret.find_expired([sar], 0, now=now)
    assert result == []


def test_run_sweep_disabled_returns_zero(tmp_path, monkeypatch):
    """Sweep with retention_days=0 returns 0 and calls delete_fn zero times."""
    import sar.retention as ret
    monkeypatch.setattr(ret, "_STATUS_PATH", str(tmp_path / "last_retention.json"))

    deleted_ids = []
    audited = []

    ret.run_retention_sweep(
        get_config=lambda: {"retention_days": "0"},
        list_sars_fn=lambda: [_FakeSAR("s1", "complete", completed_at=_dt_ago(9999))],
        delete_fn=lambda sid: deleted_ids.append(sid),
        audit_fn=lambda action, target="", detail="": audited.append(action),
    )

    assert deleted_ids == []
    # Status file written with disabled=True
    status = ret.get_status()
    assert status.get("disabled") is True


# ── End-to-end sweep with real Flask app ─────────────────────────────────────

def test_sweep_deletes_expired_and_writes_status(flask_app, tmp_path, monkeypatch):
    """End-to-end: expired completed SAR is deleted; dirs gone; audit event written."""
    import sar.retention as ret
    import sar.audit as audit_mod

    monkeypatch.setattr(ret, "_STATUS_PATH", str(tmp_path / "last_retention.json"))

    # Create a completed SAR that expired 200 days ago
    sar = _make_complete_sar(flask_app, completed_days_ago=200)
    sid = sar.id

    # Verify the directories exist before the sweep
    upload_dir = os.path.join(flask_app.UPLOAD_DIR, sid)
    output_dir = os.path.join(flask_app.OUTPUT_DIR, sid)
    os.makedirs(output_dir, exist_ok=True)
    assert os.path.isdir(upload_dir), "upload dir should exist before sweep"

    deleted = ret.run_retention_sweep(
        get_config=lambda: {"retention_days": "180"},
        list_sars_fn=flask_app._all,
        delete_fn=flask_app._delete_sar_data,
        audit_fn=lambda action, target="", detail="": audit_mod.log_event(
            action, target=target, detail=detail),
    )

    assert deleted == 1
    # SAR gone from in-memory store
    assert flask_app._get(sid) is None
    # Upload and output dirs removed
    assert not os.path.isdir(upload_dir)
    assert not os.path.isdir(output_dir)
    # Audit event written
    events = audit_mod.read_events(action="sar_retention_deleted", target=sid)
    assert events, "sar_retention_deleted event not found in audit log"
    # Status file written
    status = ret.get_status()
    assert status["deleted"] == 1
    assert status["retention_days"] == 180


def test_sweep_leaves_recent_sar_intact(flask_app, tmp_path, monkeypatch):
    """A completed SAR only 10 days old survives a 180-day sweep."""
    import sar.retention as ret
    import sar.audit as audit_mod

    monkeypatch.setattr(ret, "_STATUS_PATH", str(tmp_path / "last_retention.json"))

    sar = _make_complete_sar(flask_app, completed_days_ago=10)
    sid = sar.id

    deleted = ret.run_retention_sweep(
        get_config=lambda: {"retention_days": "180"},
        list_sars_fn=flask_app._all,
        delete_fn=flask_app._delete_sar_data,
        audit_fn=lambda action, target="", detail="": audit_mod.log_event(
            action, target=target, detail=detail),
    )

    assert deleted == 0
    assert flask_app._get(sid) is not None, "recent SAR should still exist"


def test_sweep_one_failure_does_not_abort_others(flask_app, tmp_path, monkeypatch):
    """If one deletion raises, the sweep still deletes the others and audits the failure."""
    import sar.retention as ret
    import sar.audit as audit_mod

    monkeypatch.setattr(ret, "_STATUS_PATH", str(tmp_path / "last_retention.json"))

    sar_ok = _make_complete_sar(flask_app, completed_days_ago=200)
    sar_fail = _make_complete_sar(flask_app, completed_days_ago=200)

    failed_id = sar_fail.id
    ok_id = sar_ok.id

    fail_audited = []

    def _delete(sid):
        if sid == failed_id:
            raise RuntimeError("simulated delete failure")
        flask_app._delete_sar_data(sid)

    def _audit(action, target="", detail=""):
        audit_mod.log_event(action, target=target, detail=detail)
        if action == "sar_retention_delete_failed":
            fail_audited.append(target)

    ret.run_retention_sweep(
        get_config=lambda: {"retention_days": "180"},
        list_sars_fn=flask_app._all,
        delete_fn=_delete,
        audit_fn=_audit,
    )

    # The non-failing SAR was deleted
    assert flask_app._get(ok_id) is None
    # The failing SAR still exists (delete raised)
    assert flask_app._get(failed_id) is not None
    # The failure was audited
    assert failed_id in fail_audited
