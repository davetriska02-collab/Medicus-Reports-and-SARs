"""Tests for sar/dictionary.py — self-learning practice dictionary."""
import json
import os
import pathlib
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Ensure repo root is in path for direct imports
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── Helpers that work against live sar.dictionary from repo ──────────────────

def _get_dict_mod():
    """Return sar.dictionary, importing if needed."""
    if "sar.dictionary" not in sys.modules:
        import sar.dictionary  # noqa
    return sys.modules["sar.dictionary"]


# ── record_unknown_approved ───────────────────────────────────────────────────

def test_record_increments_count(tmp_path):
    import sar.dictionary as _d
    # Redirect paths for this test
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH
    _d._SUGGESTIONS_PATH = str(tmp_path / "name_suggestions.json")
    _d._EXTRA_PATH = str(tmp_path / "extra_surnames.json")
    try:
        from sar.models import RedactionStatus, PIICategory, SARRequest, SubjectDetails, RedactionCandidate
        c = RedactionCandidate(text="Dr Smithersfield", status=RedactionStatus.APPROVED,
                               category=PIICategory.PERSON_NAME)
        sar = SARRequest(subject=SubjectDetails(full_name="Test"))
        sar.candidates = [c]

        _d.record_unknown_approved(sar)
        _d.record_unknown_approved(sar)

        sugg = _d._load_suggestions()
        assert "smithersfield" in sugg, f"expected 'smithersfield' in {list(sugg.keys())}"
        assert sugg["smithersfield"]["count"] == 2
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra


def test_get_suggestions_returns_above_min_count(tmp_path):
    import sar.dictionary as _d
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH
    _d._SUGGESTIONS_PATH = str(tmp_path / "name_suggestions.json")
    _d._EXTRA_PATH = str(tmp_path / "extra_surnames.json")
    try:
        from sar.models import RedactionStatus, PIICategory, SARRequest, SubjectDetails, RedactionCandidate
        c = RedactionCandidate(text="Hollowfield", status=RedactionStatus.APPROVED,
                               category=PIICategory.PERSON_NAME)
        sar = SARRequest(subject=SubjectDetails(full_name="Test"))
        sar.candidates = [c]

        _d.record_unknown_approved(sar)  # count=1
        assert not _d.get_suggestions(min_count=2), "should not appear at count=1"

        _d.record_unknown_approved(sar)  # count=2
        sugg = _d.get_suggestions(min_count=2)
        names = [s["name"] for s in sugg]
        assert "hollowfield" in names
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra


def test_accept_adds_to_extra_surnames_and_detector_finds_it(tmp_path):
    import sar.dictionary as _d
    import sar.name_detector as _nd
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH
    _d._SUGGESTIONS_PATH = str(tmp_path / "name_suggestions.json")
    _d._EXTRA_PATH = str(tmp_path / "extra_surnames.json")
    try:
        seed = {"wetherspoonjr": {"count": 3, "last_seen": "2026-01-01T00:00:00+00:00",
                                   "examples": ["J Wetherspoonjr"]}}
        with open(_d._SUGGESTIONS_PATH, "w") as f:
            json.dump(seed, f)

        _d.accept_suggestion("wetherspoonjr")

        # extra_surnames.json should now contain it
        with open(_d._EXTRA_PATH) as f:
            extra = json.load(f)
        assert "wetherspoonjr" in extra

        # Suggestions should no longer list it
        assert not any(s["name"] == "wetherspoonjr" for s in _d.get_suggestions(min_count=1))

        # Detector should now find it (accept_suggestion calls _reload_name_detector)
        assert "wetherspoonjr" in _nd.UK_LAST_NAMES
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra
        # Don't remove from UK_LAST_NAMES — it's a set and won't affect correctness


def test_dismiss_removes_permanently(tmp_path):
    import sar.dictionary as _d
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH
    _d._SUGGESTIONS_PATH = str(tmp_path / "name_suggestions.json")
    _d._EXTRA_PATH = str(tmp_path / "extra_surnames.json")
    try:
        seed = {"flintwicke": {"count": 5, "last_seen": "2026-01-01T00:00:00+00:00", "examples": []}}
        with open(_d._SUGGESTIONS_PATH, "w") as f:
            json.dump(seed, f)

        _d.dismiss_suggestion("flintwicke")
        assert not any(s["name"] == "flintwicke" for s in _d.get_suggestions(min_count=1))

        from sar.models import RedactionStatus, PIICategory, SARRequest, SubjectDetails, RedactionCandidate
        c = RedactionCandidate(text="Dr Flintwicke", status=RedactionStatus.APPROVED,
                               category=PIICategory.PERSON_NAME)
        sar = SARRequest(subject=SubjectDetails(full_name="Test"))
        sar.candidates = [c]
        _d.record_unknown_approved(sar)
        assert not any(s["name"] == "flintwicke" for s in _d.get_suggestions(min_count=1))
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra


def test_known_surname_not_suggested(tmp_path):
    """A name that is already in UK_LAST_NAMES should not appear in suggestions."""
    import sar.dictionary as _d
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH
    _d._SUGGESTIONS_PATH = str(tmp_path / "name_suggestions.json")
    _d._EXTRA_PATH = str(tmp_path / "extra_surnames.json")
    try:
        from sar.models import RedactionStatus, PIICategory, SARRequest, SubjectDetails, RedactionCandidate
        c = RedactionCandidate(text="Dr Smith", status=RedactionStatus.APPROVED,
                               category=PIICategory.PERSON_NAME)
        sar = SARRequest(subject=SubjectDetails(full_name="Test"))
        sar.candidates = [c]
        for _ in range(5):
            _d.record_unknown_approved(sar)
        assert not any(s["name"] == "smith" for s in _d.get_suggestions(min_count=1))
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra


# ── Admin API endpoints ───────────────────────────────────────────────────────
# Use the session-scoped flask_app and admin_client fixtures from conftest.py

def _seed_suggestion(dict_path, name, count=3):
    existing = {}
    if os.path.exists(dict_path):
        with open(dict_path) as f:
            existing = json.load(f)
    existing[name] = {"count": count, "last_seen": "2026-01-01", "examples": [f"J {name.title()}"]}
    with open(dict_path, "w") as f:
        json.dump(existing, f)


def test_suggestions_endpoint_admin(flask_app, admin_client):
    """GET /api/admin/name-suggestions returns a list for admins."""
    import sar.dictionary as _d
    c, hdrs = admin_client
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH

    # Use a temp path within the app copy's data dir
    import tempfile, os as _os
    data_dir = str(pathlib.Path(flask_app.__file__).parent / "data")
    _os.makedirs(data_dir, exist_ok=True)
    tmp_sugg = str(pathlib.Path(data_dir) / "name_suggestions_test.json")
    _d._SUGGESTIONS_PATH = tmp_sugg
    _d._EXTRA_PATH = str(pathlib.Path(data_dir) / "extra_surnames_test.json")

    try:
        _seed_suggestion(tmp_sugg, "bramblewood")
        resp = c.get("/api/admin/name-suggestions", headers=hdrs)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert any(s["name"] == "bramblewood" for s in data)
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra
        try:
            _os.remove(tmp_sugg)
        except OSError:
            pass


def test_suggestions_endpoint_anon_redirect(client):
    """Non-admin gets 302/403 for name-suggestions endpoint."""
    resp = client.get("/api/admin/name-suggestions")
    assert resp.status_code in (302, 403)


def test_accept_endpoint(flask_app, admin_client):
    """POST /api/admin/name-suggestions/accept adds to extra_surnames."""
    import sar.dictionary as _d
    c, hdrs = admin_client
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH

    import os as _os
    data_dir = str(pathlib.Path(flask_app.__file__).parent / "data")
    _os.makedirs(data_dir, exist_ok=True)
    tmp_sugg = str(pathlib.Path(data_dir) / "name_suggestions_accept_test.json")
    tmp_extra = str(pathlib.Path(data_dir) / "extra_surnames_accept_test.json")
    _d._SUGGESTIONS_PATH = tmp_sugg
    _d._EXTRA_PATH = tmp_extra

    try:
        _seed_suggestion(tmp_sugg, "grumblethwaite")

        resp = c.post("/api/admin/name-suggestions/accept",
                      json={"name": "grumblethwaite"},
                      headers={**hdrs, "Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.get_json().get("ok")

        with open(tmp_extra) as f:
            extra = json.load(f)
        assert "grumblethwaite" in extra
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra
        for p in (tmp_sugg, tmp_extra):
            try:
                _os.remove(p)
            except OSError:
                pass


def test_dismiss_endpoint(flask_app, admin_client):
    """POST /api/admin/name-suggestions/dismiss marks dismissed."""
    import sar.dictionary as _d
    c, hdrs = admin_client
    orig_sugg = _d._SUGGESTIONS_PATH
    orig_extra = _d._EXTRA_PATH

    import os as _os
    data_dir = str(pathlib.Path(flask_app.__file__).parent / "data")
    _os.makedirs(data_dir, exist_ok=True)
    tmp_sugg = str(pathlib.Path(data_dir) / "name_suggestions_dismiss_test.json")
    _d._SUGGESTIONS_PATH = tmp_sugg
    _d._EXTRA_PATH = orig_extra

    try:
        _seed_suggestion(tmp_sugg, "murkswallow")

        resp = c.post("/api/admin/name-suggestions/dismiss",
                      json={"name": "murkswallow"},
                      headers={**hdrs, "Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.get_json().get("ok")

        sugg = _d.get_suggestions(min_count=1)
        assert not any(s["name"] == "murkswallow" for s in sugg)
    finally:
        _d._SUGGESTIONS_PATH = orig_sugg
        _d._EXTRA_PATH = orig_extra
        try:
            _os.remove(tmp_sugg)
        except OSError:
            pass
