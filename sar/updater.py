"""
SAR Redact — GitHub update checker.

Runs once in a background thread at startup. Fetches the latest release from
GitHub and caches the result. The /api/update-check route exposes it to the UI.
No auth required — the repo's releases are public.
"""
import threading
import urllib.request
import urllib.error
import json
import re
from datetime import datetime, timezone

GITHUB_REPO    = "davetriska02-collab/Medicus-Reports-and-SARs"
RELEASES_URL   = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE  = f"https://github.com/{GITHUB_REPO}/releases"

# Populated by _check_thread once it completes
_result: dict = {
    "checked": False,
    "update_available": False,
    "current_version": None,
    "latest_version": None,
    "release_name": None,
    "release_notes": None,
    "release_url": None,
    "download_url": None,
    "published_at": None,
    "error": None,
}
_lock = threading.Lock()


def _parse_version(tag: str) -> tuple:
    """Turn 'v2.1.3' or '2.1' into (2, 1, 3) for comparison."""
    tag = tag.lstrip("vV").strip()
    parts = re.split(r"[.\-]", tag)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            pass
    return tuple(result) if result else (0,)


def _do_check(current_version: str):
    global _result
    try:
        req = urllib.request.Request(
            RELEASES_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"SAR-Redact/{current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        latest_tag  = data.get("tag_name", "")
        latest_ver  = _parse_version(latest_tag)
        current_ver = _parse_version(current_version)
        available   = latest_ver > current_ver

        # First ZIP asset is the download, fall back to releases page
        dl_url = RELEASES_PAGE
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(".zip"):
                dl_url = asset["browser_download_url"]
                break

        with _lock:
            _result.update({
                "checked": True,
                "update_available": available,
                "current_version": current_version,
                "latest_version": latest_tag.lstrip("vV"),
                "release_name": data.get("name", latest_tag),
                "release_notes": (data.get("body") or "")[:500],
                "release_url": data.get("html_url", RELEASES_PAGE),
                "download_url": dl_url,
                "published_at": data.get("published_at", ""),
                "error": None,
            })

    except urllib.error.HTTPError as e:
        if e.code == 404:
            # No releases yet — not an error, just nothing to report
            with _lock:
                _result.update({"checked": True, "update_available": False,
                                 "current_version": current_version, "error": None})
        else:
            with _lock:
                _result.update({"checked": True, "error": f"HTTP {e.code}"})
    except Exception as exc:
        with _lock:
            _result.update({"checked": True, "error": str(exc)[:120]})


def start(current_version: str):
    """Kick off the background check. Call once at app startup.

    Disable by setting: UPDATE_CHECK_ENABLED=0

    What is transmitted: a single HTTPS GET to api.github.com with a
    User-Agent header containing only the app version string. No patient
    data, no machine identifiers beyond what GitHub CDN logs normally.
    See SECURITY.md for full details.
    """
    import os
    if os.environ.get("UPDATE_CHECK_ENABLED", "1").strip() == "0":
        _result["checked"] = True
        _result["update_available"] = False
        _result["current_version"] = current_version
        return
    _result["current_version"] = current_version
    t = threading.Thread(target=_do_check, args=(current_version,), daemon=True)
    t.start()


def get_result() -> dict:
    with _lock:
        return dict(_result)
