import json
import os

_DATA_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "custom_words.json")


def _load() -> list[dict]:
    if not os.path.exists(_DATA_PATH):
        return []
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(words: list[dict]) -> None:
    os.makedirs(os.path.dirname(_DATA_PATH), exist_ok=True)
    with open(_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2)


def get_custom_words() -> list[dict]:
    return _load()


def add_custom_word(phrase: str, case_sensitive: bool = False) -> None:
    words = _load()
    if not any(w["phrase"].lower() == phrase.lower() for w in words):
        words.append({"phrase": phrase, "case_sensitive": case_sensitive})
        _save(words)


def remove_custom_word(phrase: str) -> None:
    words = _load()
    words = [w for w in words if w["phrase"].lower() != phrase.lower()]
    _save(words)
