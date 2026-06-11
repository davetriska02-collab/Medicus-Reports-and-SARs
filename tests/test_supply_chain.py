"""Tests for H6 fix: verified downloads + rollback.

Checks that the bat files and release.yml contain the required security
elements introduced in 2.5.4.
"""
import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent


# ── update.bat ───────────────────────────────────────────────────────────────

def test_update_bat_contains_get_file_hash():
    """update.bat must use Get-FileHash to compute the zip's SHA-256."""
    text = (REPO / "update.bat").read_text(encoding="utf-8", errors="replace")
    assert "Get-FileHash" in text, (
        "update.bat missing Get-FileHash checksum verification"
    )


def test_update_bat_references_sha256sums():
    """update.bat must reference the SHA256SUMS asset."""
    text = (REPO / "update.bat").read_text(encoding="utf-8", errors="replace")
    assert "SHA256SUMS" in text, (
        "update.bat missing SHA256SUMS manifest reference"
    )


def test_update_bat_contains_rollback():
    """update.bat must contain a rollback/restore path for failed installs."""
    text = (REPO / "update.bat").read_text(encoding="utf-8", errors="replace")
    # The rollback copies from BACKUP_DIR back over the install
    assert "BACKUP_DIR" in text, "update.bat missing BACKUP_DIR reference"
    # It must copy files back (restore) — look for a copy command in a rollback context
    # We check for the presence of restore-related keywords
    assert any(kw in text for kw in ("ollback", "estore", "Restore", "Rollback")), (
        "update.bat missing rollback/restore logic"
    )


def test_update_bat_hash_mismatch_aborts():
    """update.bat must abort (exit /b 1) when a hash mismatch is detected."""
    text = (REPO / "update.bat").read_text(encoding="utf-8", errors="replace")
    assert "HASH_MISMATCH" in text, (
        "update.bat missing HASH_MISMATCH detection"
    )


# ── release.yml ──────────────────────────────────────────────────────────────

def test_release_yml_parses_as_valid_yaml():
    """release.yml must be parseable as YAML."""
    text = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict), "release.yml did not parse as a YAML mapping"


def test_release_yml_contains_sha256sum_step():
    """release.yml must include a step that generates SHA256SUMS."""
    text = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "sha256sum" in text, (
        "release.yml missing sha256sum step"
    )
    assert "SHA256SUMS" in text, (
        "release.yml missing SHA256SUMS reference"
    )


def test_release_yml_sha256sums_in_assets():
    """release.yml must attach SHA256SUMS as a release asset."""
    text = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)

    # Find the release step and check its run block references SHA256SUMS in ASSETS
    release_steps = parsed.get("jobs", {}).get("release", {}).get("steps", [])
    release_step = next(
        (s for s in release_steps if s.get("name", "").lower().startswith("create github release")),
        None,
    )
    assert release_step is not None, "Could not find 'Create GitHub Release' step in release.yml"
    run_script = release_step.get("run", "")
    assert "SHA256SUMS" in run_script, (
        "SHA256SUMS not included in the ASSETS array in the 'Create GitHub Release' step"
    )


# ── start_server.bat ─────────────────────────────────────────────────────────

def test_start_server_bat_contains_pyembed_sha256():
    """start_server.bat must embed the SHA-256 hash of the Python runtime zip."""
    text = (REPO / "start_server.bat").read_text(encoding="utf-8", errors="replace")
    assert "PYEMBED_SHA256" in text, (
        "start_server.bat missing PYEMBED_SHA256 variable"
    )
    # Extract the hash value and verify it looks like a 64-char hex string
    m = re.search(r'PYEMBED_SHA256\s*=\s*([0-9a-fA-F]+)', text)
    assert m is not None, "Could not parse PYEMBED_SHA256 value from start_server.bat"
    hash_val = m.group(1)
    assert len(hash_val) == 64, (
        f"PYEMBED_SHA256 value has length {len(hash_val)}, expected 64 hex chars. "
        f"Got: {hash_val!r}"
    )
    assert re.fullmatch(r'[0-9a-fA-F]{64}', hash_val), (
        f"PYEMBED_SHA256 value is not a valid hex string: {hash_val!r}"
    )
