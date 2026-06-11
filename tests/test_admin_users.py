"""Admin user-management routes: create, list, password-reset, delete.

Coverage for app.py admin/user routes (M2.2).

Self-deletion finding: the /admin/users/<uid>/delete route guards
self-deletion with:
    if uid == g.current_user.id: return jsonify({"error": "Cannot delete your own account."}), 400
so an admin CANNOT delete their own account — returns HTTP 400.
"""
import re

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _csrf(resp):
    m = (re.search(rb'name="_csrf_token" value="([^"]+)"', resp.data) or
         re.search(rb'name="csrf-token" content="([^"]+)"', resp.data))
    assert m, "no CSRF token found in page"
    return m.group(1).decode()


def _make_gp_client(flask_app):
    """Create a GP user and return (client, csrf_headers, user_id)."""
    from sar.users import create_user, get_user_by_username
    un = "gpuser_test_m22"
    # Remove if already exists from a prior run
    existing = get_user_by_username(un)
    if not existing:
        create_user(un, "GP Test User", "gp", "password123")
    user = get_user_by_username(un)
    c = flask_app.app.test_client()
    flask_app._login_clear("127.0.0.2", un)
    r = c.get("/login")
    c.post("/login", data={"_csrf_token": _csrf(r), "username": un,
                           "password": "password123"})
    r = c.get("/")
    assert r.status_code == 200, "GP login failed"
    return c, {"X-CSRF-Token": _csrf(r)}, user.id


# ── List users ────────────────────────────────────────────────────────────────

def test_admin_list_users_happy_path(flask_app, admin_client):
    """Admin can GET /admin/users and sees the users table."""
    c, H = admin_client
    r = c.get("/admin/users")
    assert r.status_code == 200
    assert b"admin" in r.data.lower() or b"Admin" in r.data


def test_non_admin_users_page_redirects(flask_app):
    """Non-admin user is denied /admin/users."""
    gp_client, gp_H, _ = _make_gp_client(flask_app)
    r = gp_client.get("/admin/users", follow_redirects=False)
    # Should be 403 or redirect to login/403
    assert r.status_code in (302, 403), f"expected 302 or 403, got {r.status_code}"


# ── Create user ──────────────────────────────────────────────────────────────

def test_admin_create_user_happy_path(flask_app, admin_client):
    """Admin can create a new GP user."""
    c, H = admin_client
    data = {"username": "newgp_m22_create", "display_name": "New GP",
            "role": "gp", "password": "password123"}
    r = c.post("/admin/users/create", data=data, headers=H, follow_redirects=True)
    assert r.status_code == 200
    from sar.users import get_user_by_username
    u = get_user_by_username("newgp_m22_create")
    assert u is not None
    assert u.role == "gp"


def test_admin_create_user_non_admin_forbidden(flask_app):
    """Non-admin cannot create a user — gets 403 or redirect."""
    gp_client, gp_H, _ = _make_gp_client(flask_app)
    data = {"username": "shouldfail_m22", "display_name": "Fail",
            "role": "gp", "password": "password123"}
    r = gp_client.post("/admin/users/create", data=data, headers=gp_H,
                       follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_create_user_duplicate_username(flask_app, admin_client):
    """Creating a user with an existing username returns an error page (not 302)."""
    c, H = admin_client
    un = "dup_m22_user"
    from sar.users import get_user_by_username, create_user
    if not get_user_by_username(un):
        create_user(un, "Dup User", "gp", "password123")
    data = {"username": un, "display_name": "Dup2",
            "role": "gp", "password": "password123"}
    r = c.post("/admin/users/create", data=data, headers=H, follow_redirects=False)
    # Should NOT redirect (redirect = success); should show error
    assert r.status_code == 200
    assert b"already exists" in r.data


def test_admin_create_user_short_password(flask_app, admin_client):
    """Creating a user with a < 8-char password returns an error."""
    c, H = admin_client
    data = {"username": "shortpw_m22", "display_name": "Short PW",
            "role": "gp", "password": "abc"}
    r = c.post("/admin/users/create", data=data, headers=H, follow_redirects=False)
    assert r.status_code == 200
    assert b"8 characters" in r.data or b"Password" in r.data


# ── Password reset ────────────────────────────────────────────────────────────

def test_admin_reset_password_happy_path(flask_app, admin_client):
    """Admin can reset another user's password via the JSON API."""
    c, H = admin_client
    from sar.users import create_user, get_user_by_username
    un = "resetpw_m22"
    if not get_user_by_username(un):
        create_user(un, "Reset User", "gp", "password123")
    u = get_user_by_username(un)
    r = c.post(f"/admin/users/{u.id}/reset-password",
               json={"new_password": "newpassword99"}, headers=H)
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_admin_reset_password_non_admin_forbidden(flask_app):
    """Non-admin cannot reset passwords — gets 302/403."""
    gp_client, gp_H, gp_id = _make_gp_client(flask_app)
    r = gp_client.post(f"/admin/users/{gp_id}/reset-password",
                       json={"new_password": "newpassword99"}, headers=gp_H,
                       follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_reset_password_too_short(flask_app, admin_client):
    """Password reset with < 8-char password returns 400."""
    c, H = admin_client
    from sar.users import create_user, get_user_by_username
    un = "resetpw_m22_short"
    if not get_user_by_username(un):
        create_user(un, "Short Reset", "gp", "password123")
    u = get_user_by_username(un)
    r = c.post(f"/admin/users/{u.id}/reset-password",
               json={"new_password": "x"}, headers=H)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_admin_reset_password_not_found(flask_app, admin_client):
    """Resetting password for nonexistent uid returns 404."""
    c, H = admin_client
    r = c.post("/admin/users/nonexistent_uid_xyz/reset-password",
               json={"new_password": "password123"}, headers=H)
    assert r.status_code == 404


# ── Delete user ───────────────────────────────────────────────────────────────

def test_admin_delete_user_happy_path(flask_app, admin_client):
    """Admin can delete another user."""
    c, H = admin_client
    from sar.users import create_user, get_user_by_username
    un = "deleteme_m22"
    if not get_user_by_username(un):
        create_user(un, "Delete Me", "gp", "password123")
    u = get_user_by_username(un)
    r = c.post(f"/admin/users/{u.id}/delete", headers=H, follow_redirects=True)
    assert r.status_code == 200
    # User gone
    assert get_user_by_username(un) is None


def test_admin_delete_non_admin_forbidden(flask_app):
    """Non-admin cannot delete a user."""
    gp_client, gp_H, gp_id = _make_gp_client(flask_app)
    r = gp_client.post(f"/admin/users/{gp_id}/delete", headers=gp_H,
                       follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_cannot_delete_own_account(flask_app, admin_client):
    """An admin attempting to delete their own account gets HTTP 400.

    Finding: the route guards self-deletion at the HTTP level
    (returns 400 with 'Cannot delete your own account') — this is correct
    behaviour and this test asserts it.
    """
    c, H = admin_client
    from sar.users import get_user_by_username
    admin_user = get_user_by_username("admin")
    assert admin_user is not None
    r = c.post(f"/admin/users/{admin_user.id}/delete", headers=H)
    assert r.status_code == 400
    data = r.get_json()
    assert "Cannot delete your own account" in data.get("error", "")


def test_admin_delete_nonexistent_user_returns_404(flask_app, admin_client):
    """Deleting a nonexistent uid returns 404."""
    c, H = admin_client
    r = c.post("/admin/users/no_such_uid_xyz/delete", headers=H)
    assert r.status_code == 404
