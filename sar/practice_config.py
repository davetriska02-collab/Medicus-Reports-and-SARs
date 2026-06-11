"""
Practice configuration — name, address, SAR officer details.
Stored in data/practice.json. Editable from the Settings page by admins.
"""
import json
import os
from sar.fsutil import atomic_write_json

_CONFIG_PATH = str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'data' / 'practice.json')

DEFAULTS = {
    "practice_name":    "My Surgery",
    "practice_address": "",
    "sar_officer_name": "",
    "sar_officer_role": "Data Protection Lead",
    "sar_officer_email": "",
    "sar_officer_gmc":  "",
    "footer_text":      "",
    # Server mode: nightly backup destination (NAS share / synced folder).
    # Empty = backups disabled.
    "backup_dir":       "",
    # Minutes of inactivity before a session is signed out (0 = disabled)
    "idle_timeout_minutes": "30",
    # Two-person sign-off: "1" = require a second reviewer before finalising
    "require_second_signoff": "0",
    # GDPR retention: automatically delete completed SARs after this many days.
    # "0" or "" disables automatic deletion entirely.
    "retention_days": "180",
}


def get_config() -> dict:
    """Return current config, falling back to defaults for missing keys."""
    try:
        path = os.path.abspath(_CONFIG_PATH)
        if os.path.exists(path):
            with open(path, 'r') as f:
                saved = json.load(f)
            return {**DEFAULTS, **saved}
    except Exception:
        pass
    return dict(DEFAULTS)


def save_config(data: dict) -> None:
    """Persist a subset of allowed keys."""
    current = get_config()
    for key in DEFAULTS:
        if key in data:
            current[key] = str(data[key]).strip()
    atomic_write_json(os.path.abspath(_CONFIG_PATH), current)


def is_default() -> bool:
    """True if the practice name has never been set."""
    return get_config()['practice_name'] == DEFAULTS['practice_name']
