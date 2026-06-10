"""
User management for SAR Redact.
Follows the same JSON-file pattern as staff_list.py and custom_words.py.
"""
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash
from sar.models import User

USERS_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "users.json")


def _load_users() -> list[dict]:
    if not os.path.exists(USERS_PATH):
        return []
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: list[dict]) -> None:
    os.makedirs(os.path.dirname(USERS_PATH), exist_ok=True)
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


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
