"""Scheduled backups for server mode.

When the practice sets a backup folder (Settings → backup_dir, e.g. a NAS
share or synced drive), a background thread writes a nightly zip containing
the database snapshot, config/user files, the audit trail and (optionally)
uploaded/output documents. Oldest backups beyond the retention count are
deleted. Status is written to data/last_backup.json and shown on
/admin/status.
"""
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone

from sar import store
from sar.fsutil import atomic_write_json

_BASE = __import__("pathlib").Path(__file__).resolve().parent.parent
_STATUS_PATH = str(_BASE / "data" / "last_backup.json")

CHECK_INTERVAL_S = 3600        # how often the thread wakes up
BACKUP_EVERY_S = 24 * 3600     # one backup per day
RETENTION = 7                  # keep this many zips

_thread_started = False


def get_status() -> dict:
    try:
        with open(_STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def perform_backup(backup_dir: str, include_documents: bool = True) -> str:
    """Write one backup zip into backup_dir. Returns the zip path."""
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = os.path.join(backup_dir, f"sarredact-backup-{stamp}.zip")

    # Consistent db snapshot first (never zip the live WAL db directly)
    fd, db_snap = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store.backup_db_to(db_snap)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_snap, "data/sarredact.db")
            data_dir = str(_BASE / "data")
            for name in ("users.json", "practice.json", "staff_list.json",
                         "custom_words.json", "extra_surnames.json",
                         "report_templates.json"):
                p = os.path.join(data_dir, name)
                if os.path.exists(p):
                    zf.write(p, f"data/{name}")
            audit_dir = os.path.join(data_dir, "audit")
            if os.path.isdir(audit_dir):
                for f in os.listdir(audit_dir):
                    zf.write(os.path.join(audit_dir, f), f"data/audit/{f}")
            if include_documents:
                for top in ("uploads", "output"):
                    root_dir = str(_BASE / top)
                    for root, _, files in os.walk(root_dir):
                        for f in files:
                            full = os.path.join(root, f)
                            rel = os.path.relpath(full, str(_BASE))
                            try:
                                zf.write(full, rel)
                            except OSError:
                                pass
    finally:
        try:
            os.remove(db_snap)
        except OSError:
            pass

    # Retention: delete oldest beyond RETENTION
    backups = sorted(f for f in os.listdir(backup_dir)
                     if f.startswith("sarredact-backup-") and f.endswith(".zip"))
    for old in backups[:-RETENTION]:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass

    atomic_write_json(_STATUS_PATH, {
        "last_backup": datetime.now(timezone.utc).isoformat(),
        "zip": zip_path,
        "size_mb": round(os.path.getsize(zip_path) / 1e6, 1),
        "ok": True,
    })
    return zip_path


def start_backup_thread(get_config, audit_fn=None) -> None:
    """Start the hourly check loop. get_config() must return the practice
    config dict (read fresh each cycle so settings changes apply live)."""
    global _thread_started
    if _thread_started:
        return
    _thread_started = True

    def _loop():
        while True:
            try:
                cfg = get_config()
                backup_dir = (cfg.get("backup_dir") or "").strip()
                if backup_dir:
                    last = get_status().get("last_backup", "")
                    due = True
                    if last:
                        try:
                            last_dt = datetime.fromisoformat(last)
                            age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                            due = age >= BACKUP_EVERY_S
                        except ValueError:
                            pass
                    if due:
                        zip_path = perform_backup(backup_dir)
                        if audit_fn:
                            audit_fn("backup_completed", detail=os.path.basename(zip_path))
            except Exception as e:
                atomic_write_json(_STATUS_PATH, {
                    "last_attempt": datetime.now(timezone.utc).isoformat(),
                    "ok": False, "error": str(e)[:300],
                })
                print(f"[backup] WARNING: backup failed: {e}")
            time.sleep(CHECK_INTERVAL_S)

    threading.Thread(target=_loop, daemon=True, name="backup").start()
