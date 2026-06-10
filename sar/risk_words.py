import json
import os
import re

_DATA_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "risk_words.json")


def _load() -> dict[str, list[str]]:
    if not os.path.exists(_DATA_PATH):
        return {}
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_risk_words() -> dict[str, list[str]]:
    return _load()


def check_text_for_risk(text: str) -> list[dict]:
    """Check text against risk word dictionary.
    Returns list of {"phrase": ..., "category": ...} matches.
    Uses word-boundary matching to avoid false positives.
    """
    if not text:
        return []
    matches = []
    for category, words in _load().items():
        for word in words:
            if re.search(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE):
                matches.append({"phrase": word, "category": category})
    return matches
