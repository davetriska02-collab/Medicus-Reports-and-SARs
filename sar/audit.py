"""Append-only access audit trail.

Healthcare IG (Caldicott / DSPT) expects a record of who viewed and changed
which patient's data and when. Events are appended as JSON lines to monthly
files in data/audit/ — append-only, human-readable, and trivially exported.
"""
import json
import os
import threading
from datetime import datetime, timezone

AUDIT_DIR = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "audit")

_lock = threading.Lock()


def log_event(action: str, *, user_id: str = "", username: str = "",
              target: str = "", detail: str = "", ip: str = "") -> None:
    """Append one audit event. Never raises — auditing must not break the app,
    but failures are printed so they surface in the server log."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user_id": user_id,
        "username": username,
        "target": target,
        "detail": detail,
        "ip": ip,
    }
    try:
        os.makedirs(AUDIT_DIR, exist_ok=True)
        fname = f"audit-{datetime.now(timezone.utc).strftime('%Y%m')}.jsonl"
        line = json.dumps(rec, ensure_ascii=False)
        with _lock:
            with open(os.path.join(AUDIT_DIR, fname), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f"[audit] WARNING: could not write audit event: {e}")


def read_events(limit: int = 500, action: str = "", username: str = "",
                target: str = "") -> list[dict]:
    """Return the newest events first, optionally filtered."""
    events: list[dict] = []
    if not os.path.isdir(AUDIT_DIR):
        return events
    files = sorted((f for f in os.listdir(AUDIT_DIR)
                    if f.startswith("audit-") and f.endswith(".jsonl")),
                   reverse=True)
    for fname in files:
        try:
            with open(os.path.join(AUDIT_DIR, fname), encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if action and rec.get("action") != action:
                continue
            if username and username.lower() not in rec.get("username", "").lower():
                continue
            if target and target not in rec.get("target", ""):
                continue
            events.append(rec)
            if len(events) >= limit:
                return events
    return events


def known_actions() -> list[str]:
    """Distinct actions present in the log (for the filter dropdown)."""
    return sorted({e["action"] for e in read_events(limit=5000)})
