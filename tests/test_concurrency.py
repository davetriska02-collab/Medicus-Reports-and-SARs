"""Tests for H1 fix: serialised SAR mutations via _mutate context manager.

Two scenarios:
1. Concurrency: 2 threads × 15 sequential POSTs each, approving DISTINCT
   candidates.  After both threads finish, all 30 candidates must be approved —
   no decision silently lost.
2. Reentrancy: a single call through a _mutate-wrapped route must return 200
   (proves the RLock does not self-deadlock).
"""
import os
import threading

import fitz
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_sar_30(flask_app):
    """Create a SAR with 30 flagged candidates, each with a unique id."""
    from sar.models import (SARRequest, SubjectDetails, RedactionCandidate,
                            PIICategory, RedactionStatus)
    m = flask_app
    sar = SARRequest(subject=SubjectDetails(
        full_name="Concurrent Test", first_name="Concurrent", last_name="Test",
        nhs_number="943 476 5919", date_of_birth="1980-01-01",
        address="1 Thread Lane\nTestbury"))
    sar.archived = False
    sar.compute_due_date()

    sd = m._sar_dir(sar.id)
    os.makedirs(sd, exist_ok=True)

    # Build a minimal PDF
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100), "Concurrent test document.")
    pdf = os.path.join(sd, "record.pdf")
    doc.save(pdf)
    doc.close()
    sar.pdf_files = [pdf]

    # 30 flagged candidates at distinct positions
    for i in range(30):
        c = RedactionCandidate(
            text=f"Name{i:02d}",
            category=PIICategory.PERSON_NAME,
            status=RedactionStatus.FLAGGED,
            confidence=0.8,
            page_num=0,
            x0=10.0 + i, y0=10.0, x1=80.0 + i, y1=20.0,
            source_file="record.pdf",
            reason="test",
        )
        sar.candidates.append(c)

    sar.status = "reviewing"
    m._set(sar.id, sar)
    m._save(sar)
    return sar


def _admin_client_and_csrf(flask_app):
    """Return (client, csrf_headers) for a fresh admin session."""
    import re
    c = flask_app.app.test_client()
    pw = "password123"

    def _token(resp):
        m = (re.search(rb'name="_csrf_token" value="([^"]+)"', resp.data) or
             re.search(rb'name="csrf-token" content="([^"]+)"', resp.data))
        assert m, "no CSRF token found"
        return m.group(1).decode()

    r = c.get("/setup", follow_redirects=False)
    if r.status_code == 200:
        c.post("/setup", data={"_csrf_token": _token(r), "username": "admin",
                               "display_name": "Admin", "password": pw,
                               "confirm_password": pw})
    flask_app._login_clear("127.0.0.1", "admin")
    r = c.get("/login")
    c.post("/login", data={"_csrf_token": _token(r), "username": "admin",
                           "password": pw})
    r = c.get("/")
    assert r.status_code == 200, "admin login failed"
    return c, {"X-CSRF-Token": _token(r)}


# ── 1. Concurrency: no lost updates ──────────────────────────────────────────

def test_no_lost_updates_under_concurrent_approvals(flask_app):
    """2 threads × 15 POSTs each — all 30 distinct candidates end up APPROVED."""
    sar = _make_sar_30(flask_app)
    sid = sar.id
    cids = [c.id for c in sar.candidates]  # 30 distinct ids
    assert len(cids) == 30

    errors = []

    def _approve_batch(cid_slice):
        """Each thread gets its own test client (Flask clients are not thread-safe)."""
        c, H = _admin_client_and_csrf(flask_app)
        for cid in cid_slice:
            try:
                resp = c.post(
                    f"/api/sar/{sid}/candidate/{cid}/update",
                    headers=H,
                    json={"status": "approved"},
                )
                if resp.status_code != 200:
                    errors.append(f"cid={cid} status={resp.status_code} body={resp.get_data(as_text=True)}")
            except Exception as exc:
                errors.append(f"cid={cid} exception={exc}")

    # Split 30 candidates evenly between 2 threads
    t1 = threading.Thread(target=_approve_batch, args=(cids[:15],))
    t2 = threading.Thread(target=_approve_batch, args=(cids[15:],))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Requests failed:\n" + "\n".join(errors)

    # Reload from the store and check every candidate is approved
    reloaded = flask_app._get(sid)
    assert reloaded is not None, "SAR disappeared from store"

    approved = [c for c in reloaded.candidates if c.status.value == "approved"]
    not_approved = [c for c in reloaded.candidates if c.status.value != "approved"]

    assert len(approved) == 30, (
        f"Lost-update race detected: only {len(approved)}/30 candidates are approved. "
        f"Not-approved: {[(c.id, c.status.value) for c in not_approved]}"
    )


# ── 2. Reentrancy: RLock must not self-deadlock ───────────────────────────────

def test_mutate_route_no_deadlock(flask_app, admin_client):
    """A single request through a _mutate-wrapped route returns 200.
    This confirms the RLock allows re-entry from _save (which also acquires it)."""
    from sar.models import (SARRequest, SubjectDetails, RedactionCandidate,
                            PIICategory, RedactionStatus)
    m = flask_app
    c, H = admin_client

    sar = SARRequest(subject=SubjectDetails(
        full_name="Reentrant Test", first_name="Reentrant", last_name="Test",
        nhs_number="943 476 5919", date_of_birth="1990-01-01",
        address="2 Thread Lane"))
    sar.archived = False
    sar.compute_due_date()
    sd = m._sar_dir(sar.id)
    os.makedirs(sd, exist_ok=True)

    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100), "Reentrancy test.")
    pdf = os.path.join(sd, "record.pdf")
    doc.save(pdf)
    doc.close()
    sar.pdf_files = [pdf]

    cand = RedactionCandidate(
        text="Reentrant Test", category=PIICategory.PERSON_NAME,
        status=RedactionStatus.FLAGGED, confidence=0.9, page_num=0,
        x0=50, y0=90, x1=200, y1=110, source_file="record.pdf", reason="t")
    sar.candidates = [cand]
    sar.status = "reviewing"
    m._set(sar.id, sar)
    m._save(sar)

    # This call holds the lock and internally calls _save, which also acquires it.
    # If Lock (not RLock) were used, this would deadlock.
    resp = c.post(
        f"/api/sar/{sar.id}/candidate/{cand.id}/update",
        headers=H,
        json={"status": "approved"},
    )
    assert resp.status_code == 200, (
        f"RLock self-deadlock or unexpected error: {resp.status_code} {resp.get_data(as_text=True)}"
    )
    reloaded = flask_app._get(sar.id)
    assert reloaded.candidates[0].status.value == "approved"
