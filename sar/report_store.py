"""JSON-on-disk persistence for medical reports.

pdf_files are stored as basenames and resolved against uploads/reports/<id>/
on load, so moving the install folder never breaks existing reports.
"""
import json
import os
from datetime import datetime, timezone
from sar.fsutil import atomic_write_json

_BASE = __import__("pathlib").Path(__file__).resolve().parent.parent
REPORT_DATA_DIR = str(_BASE / "data" / "reports")
REPORT_UPLOAD_DIR = str(_BASE / "uploads" / "reports")
os.makedirs(REPORT_DATA_DIR, exist_ok=True)


def _resolve_pdf_path(report_id: str, stored: str) -> str:
    """Resolve a stored filename to an absolute path inside the report's
    upload directory, rejecting traversal attempts."""
    basename = os.path.basename(stored)
    resolved = os.path.join(REPORT_UPLOAD_DIR, report_id, basename)
    upload_root = os.path.realpath(REPORT_UPLOAD_DIR)
    if not os.path.realpath(resolved).startswith(upload_root):
        raise ValueError(f"Path traversal attempt rejected: {stored!r}")
    return resolved


def save_report(report_data: dict) -> None:
    report_data["last_modified"] = datetime.now(timezone.utc).isoformat()
    on_disk = dict(report_data)
    on_disk["pdf_files"] = [os.path.basename(p) for p in report_data.get("pdf_files", [])]
    path = os.path.join(REPORT_DATA_DIR, f"{report_data['id']}.json")
    atomic_write_json(path, on_disk)


def _hydrate(data: dict) -> dict:
    data["pdf_files"] = [_resolve_pdf_path(data["id"], p)
                         for p in data.get("pdf_files", [])]
    return data


def load_report(report_id: str) -> dict | None:
    path = os.path.join(REPORT_DATA_DIR, f"{report_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return _hydrate(json.load(f))


def load_all_reports() -> list[dict]:
    reports = []
    if not os.path.isdir(REPORT_DATA_DIR):
        return reports
    for fname in os.listdir(REPORT_DATA_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(REPORT_DATA_DIR, fname)) as f:
                    reports.append(_hydrate(json.load(f)))
            except Exception:
                pass
    return reports


def delete_report(report_id: str) -> bool:
    path = os.path.join(REPORT_DATA_DIR, f"{report_id}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
