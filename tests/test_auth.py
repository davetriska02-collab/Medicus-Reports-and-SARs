"""Auth flow: setup, CSRF enforcement, login throttling, POST-only logout.

Tests share one app instance and run in order (setup → login → logout).
"""
import re

import pytest

PW = "password123"


def _csrf(resp):
    m = re.search(rb'name="_csrf_token" value="([^"]+)"', resp.data)
    assert m, "no CSRF token in page"
    return m.group(1).decode()


def test_first_visit_redirects_to_setup(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and "/setup" in r.location


def test_setup_without_csrf_rejected(client):
    r = client.post("/setup", data={"username": "admin", "display_name": "Admin",
                                    "password": PW, "confirm_password": PW})
    assert r.status_code == 403


def test_setup_with_csrf_creates_admin(client):
    token = _csrf(client.get("/setup"))
    r = client.post("/setup", data={"_csrf_token": token, "username": "admin",
                                    "display_name": "Admin", "password": PW,
                                    "confirm_password": PW})
    assert r.status_code == 302


def test_login_throttled_after_five_failures(client, flask_app):
    token = _csrf(client.get("/login"))
    for _ in range(5):
        r = client.post("/login", data={"_csrf_token": token,
                                        "username": "admin", "password": "wrong"})
        assert r.status_code == 200
    r = client.post("/login", data={"_csrf_token": token,
                                    "username": "admin", "password": "wrong"})
    assert r.status_code == 429
    # Even the correct password is refused while throttled
    r = client.post("/login", data={"_csrf_token": token,
                                    "username": "admin", "password": PW})
    assert r.status_code == 429
    flask_app._login_clear("127.0.0.1", "admin")


def test_login_success_and_dashboard(client):
    token = _csrf(client.get("/login"))
    r = client.post("/login", data={"_csrf_token": token,
                                    "username": "admin", "password": PW})
    assert r.status_code == 302
    r = client.get("/")
    assert r.status_code == 200


def test_logout_get_rejected_post_works(client):
    assert client.get("/logout").status_code == 405
    token = _csrf(client.get("/login"))
    client.post("/login", data={"_csrf_token": token,
                                "username": "admin", "password": PW})
    token = _csrf(client.get("/"))
    r = client.post("/logout", data={"_csrf_token": token})
    assert r.status_code == 302
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.location


def test_api_mutation_without_csrf_rejected(client):
    r = client.post("/api/staff", json={"name": "Dr Test"},
                    headers={"X-CSRF-Token": "bogus"})
    assert r.status_code == 403
