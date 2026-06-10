"""Self-learning practice dictionary.

At finalise time, surnames that reviewers manually approved (status=APPROVED,
category=PERSON_NAME) but that were not in the built-in or extra-surname lists
are recorded in data/name_suggestions.json.  Admins can then promote them into
data/extra_surnames.json so future SARs detect them automatically.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone

log = logging.getLogger("sar.dictionary")

_DATA_DIR = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data")
_SUGGESTIONS_PATH = os.path.join(_DATA_DIR, "name_suggestions.json")
_EXTRA_PATH = os.path.join(_DATA_DIR, "extra_surnames.json")


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_suggestions() -> dict:
    try:
        if os.path.exists(_SUGGESTIONS_PATH):
            with open(_SUGGESTIONS_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_suggestions(data: dict) -> None:
    from sar.fsutil import atomic_write_json
    atomic_write_json(_SUGGESTIONS_PATH, data)


def _load_extra() -> set:
    try:
        if os.path.exists(_EXTRA_PATH):
            with open(_EXTRA_PATH, encoding="utf-8") as f:
                return {str(n).strip().lower() for n in json.load(f) if str(n).strip()}
    except Exception:
        pass
    return set()


def _reload_name_detector() -> None:
    """Reload extra_surnames into name_detector's UK_LAST_NAMES at runtime."""
    try:
        import sar.name_detector as _nd
        extra = _load_extra()
        _nd.UK_LAST_NAMES |= extra
    except Exception:
        log.debug("Could not reload name detector", exc_info=True)


# ── public API ────────────────────────────────────────────────────────────────

def record_unknown_approved(sar) -> None:
    """Record surnames from APPROVED PERSON_NAME candidates not already known.

    Called at finalise time.  Never raises.
    """
    try:
        from sar.models import RedactionStatus, PIICategory
        from sar.name_detector import UK_LAST_NAMES, NOT_NAMES
        extra = _load_extra()
        known = UK_LAST_NAMES | extra
        suggestions = _load_suggestions()
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for c in sar.candidates:
            if c.status != RedactionStatus.APPROVED:
                continue
            if c.category != PIICategory.PERSON_NAME:
                continue
            # Tokenise: alpha words, len>=3, not known, not in NOT_NAMES
            for token in re.findall(r"[A-Za-z''\-]{3,}", c.text):
                w = token.lower().strip("'-")
                if not w or len(w) < 3:
                    continue
                if w in known or w in NOT_NAMES:
                    continue
                entry = suggestions.setdefault(w, {"count": 0, "last_seen": now, "examples": []})
                entry["count"] += 1
                entry["last_seen"] = now
                if len(entry["examples"]) < 3 and c.text not in entry["examples"]:
                    entry["examples"].append(c.text)
                changed = True
        if changed:
            _save_suggestions(suggestions)
    except Exception:
        log.exception("record_unknown_approved failed (non-fatal)")


def get_suggestions(min_count: int = 2) -> list:
    """Return suggestions sorted by count desc, excluding known/dismissed names."""
    extra = _load_extra()
    suggestions = _load_suggestions()
    dismissed = suggestions.get("_dismissed", [])
    result = []
    for name, info in suggestions.items():
        if name == "_dismissed":
            continue
        if name in extra:
            continue
        if name in dismissed:
            continue
        if info.get("count", 0) < min_count:
            continue
        result.append({
            "name": name,
            "count": info["count"],
            "last_seen": info.get("last_seen", ""),
            "examples": info.get("examples", []),
        })
    return sorted(result, key=lambda x: x["count"], reverse=True)


def accept_suggestion(name: str) -> None:
    """Add name to extra_surnames.json and remove from suggestions."""
    name = name.strip().lower()
    if not name:
        return
    # Load and update extra_surnames.json
    existing = []
    if os.path.exists(_EXTRA_PATH):
        try:
            with open(_EXTRA_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    if name not in [str(n).strip().lower() for n in existing]:
        existing.append(name)
    from sar.fsutil import atomic_write_json
    atomic_write_json(_EXTRA_PATH, existing)
    # Remove from suggestions
    suggestions = _load_suggestions()
    suggestions.pop(name, None)
    _save_suggestions(suggestions)
    # Reload detector so it picks up the new name immediately
    _reload_name_detector()


def dismiss_suggestion(name: str) -> None:
    """Mark a suggestion as dismissed so it never reappears."""
    name = name.strip().lower()
    if not name:
        return
    suggestions = _load_suggestions()
    dismissed = suggestions.setdefault("_dismissed", [])
    if name not in dismissed:
        dismissed.append(name)
    suggestions.pop(name, None)
    _save_suggestions(suggestions)
