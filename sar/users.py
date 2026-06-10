"""
User management for SAR Redact.
Follows the same JSON-file pattern as staff_list.py and custom_words.py.
"""
import json
import os
import threading
from werkzeug.security import generate_password_hash, check_password_hash
from sar.models import User
from sar.fsutil import atomic_write_json

USERS_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "users.json")


class UsersFileCorrupt(Exception):
    """data/users.json exists but cannot be parsed.

    Deliberately distinct from "no users yet": a corrupt file must lock the
    app down, NOT redirect to /setup where anyone could create a new admin.
    """


# mtime-validated cache — load_user runs on every request (including every
# page-image fetch), so re-reading the file each time is needless I/O.
_cache_lock = threading.Lock()
_cache: list[dict] | None = None
_cache_mtime: float | None = None


def _load_users() -> list[dict]:
    global _cache, _cache_mtime
    with _cache_lock:
        try:
            mtime = os.path.getmtime(USERS_PATH)
        except OSError:
            _cache, _cache_mtime = None, None
            return []
        if _cache is not None and _cache_mtime == mtime:
            return _cache
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("users.json root must be a list")
        except (ValueError, OSError) as e:
            raise UsersFileCorrupt(f"Cannot read {USERS_PATH}: {e}") from e
        _cache, _cache_mtime = data, mtime
        return data


def _save_users(users: list[dict]) -> None:
    global _cache, _cache_mtime
    atomic_write_json(USERS_PATH, users)
    with _cache_lock:
        _cache, _cache_mtime = None, None  # force re-read next access


def _user_from_dict(d: dict) -> User:
    return User(
        id=d["id"],
        username=d["username"],
        display_name=d["display_name"],
        role=d.get("role", "gp"),
        is_superuser=d.get("is_superuser", False),
        password_hash=d["password_hash"],
    )


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "role": u.role,
        "is_superuser": u.is_superuser,
        "password_hash": u.password_hash,
    }


# ── Public API ─────────────────────────────────────────────────────────────

def users_file_exists() -> bool:
    """True if data/users.json exists and contains at least one user."""
    return len(_load_users()) > 0


def get_all_users() -> list[User]:
    return [_user_from_dict(d) for d in _load_users()]


def get_user_by_id(user_id: str) -> User | None:
    for d in _load_users():
        if d["id"] == user_id:
            return _user_from_dict(d)
    return None


def get_user_by_username(username: str) -> User | None:
    for d in _load_users():
        if d["username"].lower() == username.lower():
            return _user_from_dict(d)
    return None


def create_user(
    username: str,
    display_name: str,
    role: str,
    password: str,
    is_superuser: bool = False,
) -> User:
    users = _load_users()
    user = User(
        username=username.strip(),
        display_name=display_name.strip(),
        role=role,
        is_superuser=is_superuser,
        password_hash=generate_password_hash(password),
    )
    users.append(_user_to_dict(user))
    _save_users(users)
    return user


def set_password(user_id: str, new_password: str) -> bool:
    users = _load_users()
    for d in users:
        if d["id"] == user_id:
            d["password_hash"] = generate_password_hash(new_password)
            _save_users(users)
            return True
    return False


def delete_user(user_id: str) -> bool:
    users = _load_users()
    filtered = [d for d in users if d["id"] != user_id]
    if len(filtered) == len(users):
        return False
    _save_users(filtered)
    return True


def authenticate(username: str, password: str) -> User | None:
    """Return User if credentials are valid, else None."""
    user = get_user_by_username(username)
    if user and check_password_hash(user.password_hash, password):
        return user
    return None


def get_gp_users() -> list[User]:
    """Return all GP users, for the allocation dropdown."""
    return [u for u in get_all_users() if u.role == "gp"]
