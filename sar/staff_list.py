import json
import os

STAFF_LIST_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "staff_list.json")


def _load_staff() -> list[dict]:
    if not os.path.exists(STAFF_LIST_PATH):
        return []
    with open(STAFF_LIST_PATH, "r") as f:
        return json.load(f)


def _save_staff(staff: list[dict]):
    os.makedirs(os.path.dirname(STAFF_LIST_PATH), exist_ok=True)
    with open(STAFF_LIST_PATH, "w") as f:
        json.dump(staff, f, indent=2)


def get_staff_list() -> list[dict]:
    return _load_staff()


def add_staff_member(name: str, role: str = ""):
    staff = _load_staff()
    # Avoid duplicates
    if any(s["name"].lower() == name.lower() for s in staff):
        return
    staff.append({"name": name, "role": role})
    _save_staff(staff)


def remove_staff_member(name: str):
    staff = _load_staff()
    staff = [s for s in staff if s["name"].lower() != name.lower()]
    _save_staff(staff)


def is_staff_name(detected_name: str) -> bool:
    """
    Check if a detected name matches any staff member.
    Uses normalized comparison on full name and individual components.
    """
    staff = _load_staff()
    norm_detected = detected_name.strip().lower()
    detected_parts = set(norm_detected.split())

    for member in staff:
        staff_name = member["name"].strip().lower()
        staff_parts = set(staff_name.split())

        # Exact match
        if norm_detected == staff_name:
            return True

        # Check if detected name is a component of a staff name
        if norm_detected in staff_parts:
            return True

        # Check if any meaningful overlap (excluding titles like "dr", "mr", "mrs")
        titles = {"dr", "mr", "mrs", "ms", "miss", "prof", "professor", "nurse", "sister"}
        meaningful_detected = detected_parts - titles
        meaningful_staff = staff_parts - titles

        if meaningful_detected and meaningful_staff:
            if meaningful_detected & meaningful_staff:
                return True

    return False
