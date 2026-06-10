"""Audit trail module + operational endpoints."""
import pytest

import sar.audit as audit


@pytest.fixture()
def audit_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "AUDIT_DIR", str(tmp_path / "audit"))
    return tmp_path / "audit"


def test_log_and_read_events(audit_dir):
    audit.log_event("login", username="admin", ip="10.0.0.1")
    audit.log_event("sar_viewed", username="admin", target="abc123", detail="John Smith")
    audit.log_event("sar_viewed", username="drjones", target="def456")

    events = audit.read_events()
    assert len(events) == 3
    # Newest first
    assert events[0]["action"] == "sar_viewed" and events[0]["target"] == "def456"

    # Filters
    assert len(audit.read_events(action="sar_viewed")) == 2
    assert len(audit.read_events(username="drjones")) == 1
    assert len(audit.read_events(target="abc123")) == 1
    assert audit.read_events(target="abc123")[0]["detail"] == "John Smith"


def test_log_event_never_raises(tmp_path, monkeypatch):
    # Point at an unwritable location — logging must not raise
    monkeypatch.setattr(audit, "AUDIT_DIR", "/proc/definitely/not/writable")
    audit.log_event("login", username="x")  # no exception


def test_known_actions(audit_dir):
    audit.log_event("login", username="a")
    audit.log_event("logout", username="a")
    audit.log_event("login", username="b")
    assert audit.known_actions() == ["login", "logout"]


def test_healthz_unauthenticated(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_render_page_cache(tmp_path, monkeypatch):
    import fitz
    import sar.pdf_parser as pp
    monkeypatch.setattr(pp, "_PAGE_CACHE_DIR", str(tmp_path / "cache"))

    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 100), "hello")
    p = tmp_path / "x.pdf"
    doc.save(str(p))
    doc.close()

    first = pp.render_page_image(str(p), 0)
    cached_files = list((tmp_path / "cache").glob("*.png"))
    assert len(cached_files) == 1
    second = pp.render_page_image(str(p), 0)
    assert first == second
