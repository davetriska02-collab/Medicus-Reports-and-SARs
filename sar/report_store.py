"""Report persistence — SQLite-backed (see sar/store.py).

pdf_files are stored as basenames and resolved against uploads/reports/<id>/
on load, so moving the install folder never breaks existing reports.
"""
import os
from datetime import datetime, timezone
from sar import store

_BASE = __import__("pathlib").Path(__file__).resolve().parent.parent
REPORT_UPLOAD_DIR = str(_BASE / "uploads" / "reports")


def _resolve_pdf_path(report_id: str, stored: str) -> str:
    """Resolve a stored filename to an absolute path inside the report's
    upload directory, rejecting traversal attempts."""
    basename = os.path.basename(stored)
    resolved = os.path.join(REPORT_UPLOAD_DIR, report_id, basename)
    upload_root = os.path.realpath(REPORT_UPLOAD_DIR)
    if not os.path.realpath(resolved).startswith(upload_root):
        raise ValueError(f"Path traversal attempt rejected: {stored!r}")
    return resolved


def _hydrate(data: dict) -> dict:
    data["pdf_files"] = [_resolve_pdf_path(data["id"], p)
                         for p in data.get("pdf_files", [])]
    return data


def save_report(report_data: dict) -> None:
    report_data["last_modified"] = datetime.now(timezone.utc).isoformat()
    on_disk = dict(report_data)
    on_disk["pdf_files"] = [os.path.basename(p) for p in report_data.get("pdf_files", [])]
    store.save_report_doc(on_disk)


def load_report(report_id: str) -> dict | None:
    doc = store.load_report_doc(report_id)
    return _hydrate(doc) if doc else None


def load_all_reports() -> list[dict]:
    return [_hydrate(d) for d in store.load_all_report_docs()]


def delete_report(report_id: str) -> bool:
    return store.delete_report_doc(report_id)
