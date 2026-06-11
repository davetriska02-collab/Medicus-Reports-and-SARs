"""Scheduled GDPR data-retention enforcement for completed SARs.

When the practice configures a retention period (Settings → retention_days,
default 180 days), a background thread wakes hourly and — at most once per
24 hours — deletes every completed SAR whose completion timestamp is older
than the configured period.  Every deletion is written to the audit trail.
Status is written to data/last_retention.json and shown on /admin/status.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

from sar.fsutil import atomic_write_json

_BASE = __import__("pathlib").Path(__file__).resolve().parent.parent
_STATUS_PATH = str(_BASE / "data" / "last_retention.json")

CHECK_INTERVAL_S = 3600        # how often the thread wakes up
SWEEP_EVERY_S = 24 * 3600      # run a sweep at most once per day

_thread_started = False


def get_status() -> dict:
    try:
        with open(_STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def find_expired(sars: list, retention_days: int, now: datetime | None = None) -> list[str]:
    """Return the ids of SARs that should be deleted under the retention policy.

    A SAR qualifies when ALL of:
    - status == "complete"
    - its completion timestamp (completed_at, falling back to last_modified)
      is older than *retention_days* days
    - the timestamp is non-empty and parseable (we never delete on a parse
      failure — that would be unacceptably destructive)

    Parameters
    ----------
    sars:
        Iterable of SAR objects (or dicts).  Both the dataclass form used in
        active_requests and the plain-dict form returned by store iteration
        are supported via attribute / key fallback.
    retention_days:
        Minimum age in days; must be > 0.
    now:
        Override "now" for testing; defaults to UTC now.
    """
    if retention_days <= 0:
        return []

    if now is None:
        now = datetime.now(timezone.utc)

    expired = []
    for sar in sars:
        # Support both object attributes and plain dicts
        def _get(attr, default=""):
            if isinstance(sar, dict):
                return sar.get(attr, default)
            return getattr(sar, attr, default)

        status = _get("status")
        if status != "complete":
            continue

        # Prefer completed_at, fall back to last_modified
        ts_str = (_get("completed_at") or "").strip()
        if not ts_str:
            ts_str = (_get("last_modified") or "").strip()
        if not ts_str:
            # No parseable date — never delete
            continue

        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            # Unparseable date — never delete
            continue

        # Ensure the timestamp is timezone-aware for comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        age_days = (now - ts).total_seconds() / 86400
        if age_days >= retention_days:
            expired.append(_get("id"))

    return expired


def run_retention_sweep(get_config, list_sars_fn, delete_fn, audit_fn) -> int:
    """Execute one retention sweep.  Returns the number of SARs deleted.

    Parameters
    ----------
    get_config:
        Callable returning the current practice config dict.
    list_sars_fn:
        Callable returning an iterable of SAR objects/dicts.
    delete_fn:
        Callable ``delete_fn(sid)`` that performs the full deletion.
        Must not raise for the sweep to continue past failures.
    audit_fn:
        Callable ``audit_fn(action, *, target, detail)`` — mirrors
        ``sar.audit.log_event``.
    """
    cfg = get_config()
    try:
        retention_days = int(cfg.get("retention_days") or 0)
    except (ValueError, TypeError):
        retention_days = 0

    if retention_days <= 0:
        atomic_write_json(_STATUS_PATH, {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "deleted": 0,
            "retention_days": retention_days,
            "disabled": True,
        })
        return 0

    sars = list(list_sars_fn())
    expired_ids = find_expired(sars, retention_days)

    # Build a quick lookup of display info before we start deleting
    _info: dict[str, dict] = {}
    for sar in sars:
        def _get(attr, default="", s=sar):
            if isinstance(s, dict):
                return s.get(attr, default)
            return getattr(s, attr, default)

        sid = _get("id")
        subj = _get("subject")
        if isinstance(subj, dict):
            name = subj.get("full_name", sid)
        elif subj is not None:
            name = getattr(subj, "full_name", sid)
        else:
            name = sid
        completed = (_get("completed_at") or _get("last_modified") or "")
        _info[sid] = {"name": name, "completed": completed}

    deleted = 0
    for sid in expired_ids:
        info = _info.get(sid, {})
        detail = (f"subject={info.get('name', sid)}; "
                  f"completed={info.get('completed', '')}; "
                  f"retention_days={retention_days}")
        try:
            delete_fn(sid)
            audit_fn("sar_retention_deleted", target=sid, detail=detail)
            deleted += 1
        except Exception as exc:
            audit_fn("sar_retention_delete_failed", target=sid,
                     detail=f"{detail}; error={exc!s:.200}")

    atomic_write_json(_STATUS_PATH, {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "deleted": deleted,
        "retention_days": retention_days,
    })
    return deleted


def start_retention_thread(get_config, list_sars_fn, delete_fn, audit_fn) -> None:
    """Start the hourly check loop.  Runs a sweep when the last sweep was
    >= 24 hours ago (or has never run).  Mirrors backup.py's wake/due pattern
    exactly so the guard in app.py is identical."""
    global _thread_started
    if _thread_started:
        return
    _thread_started = True

    def _loop():
        while True:
            try:
                last = get_status().get("ran_at", "")
                due = True
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                        due = age >= SWEEP_EVERY_S
                    except ValueError:
                        pass
                if due:
                    run_retention_sweep(get_config, list_sars_fn, delete_fn, audit_fn)
            except Exception as e:
                print(f"[retention] WARNING: retention sweep failed: {e}")
            time.sleep(CHECK_INTERVAL_S)

    threading.Thread(target=_loop, daemon=True, name="retention").start()
