"""JSON-on-disk persistence for medical reports."""
import json
import os
from datetime import datetime, timezone

REPORT_DATA_DIR = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "reports")
os.makedirs(REPORT_DATA_DIR, exist_ok=True)


def save_report(report_data: dict) -> None:
    report_data["last_modified"] = datetime.now(timezone.utc).isoformat()
    path = os.path.join(REPORT_DATA_DIR, f"{report_data['id']}.json")
    with open(path, "w") as f:
        json.dump(report_data, f, indent=2)


def load_report(report_id: str) -> dict | None:
    path = os.path.join(REPORT_DATA_DIR, f"{report_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def load_all_reports() -> list[dict]:
    reports = []
    if not os.path.isdir(REPORT_DATA_DIR):
        return reports
    for fname in os.listdir(REPORT_DATA_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(REPORT_DATA_DIR, fname)) as f:
                    reports.append(json.load(f))
            except Exception:
                pass
    return reports


def delete_report(report_id: str) -> bool:
    path = os.path.join(REPORT_DATA_DIR, f"{report_id}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
