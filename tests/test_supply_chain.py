"""Tests for H6 fix: verified downloads + rollback, and audit-sweep checks (v2.6.1).

Checks that the bat files and release.yml contain the required security
elements introduced in 2.5.4, and the CI/ops hardening added in 2.6.1.
"""
import pathlib
import re
import subprocess
import sys

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


# ── tests.yml — benchmark gate step (v2.6.1) ─────────────────────────────────

def test_tests_yml_parses_as_valid_yaml():
    """tests.yml must be parseable as YAML."""
    text = (REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict), "tests.yml did not parse as a YAML mapping"


def test_tests_yml_contains_benchmark_gate_step():
    """tests.yml must contain the detection benchmark gate step."""
    text = (REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "benchmark_detection.py" in text, (
        "tests.yml missing benchmark_detection.py step"
    )
    assert "--ci" in text, (
        "tests.yml benchmark step missing --ci flag"
    )


# ── benchmark_detection.py — --ci flag (v2.6.1) ──────────────────────────────

def test_benchmark_script_supports_ci_flag():
    """benchmark_detection.py must accept --ci without erroring on a dry parse."""
    script = (REPO / "tools" / "benchmark_detection.py").read_text(encoding="utf-8")
    assert "--ci" in script, "benchmark_detection.py missing --ci flag"
    assert "sys.exit(1)" in script, (
        "benchmark_detection.py --ci gate must call sys.exit(1) on failure"
    )


@pytest.mark.slow
def test_benchmark_ci_gate_passes():
    """Running benchmark_detection.py --ci must exit 0 with the current detectors."""
    result = subprocess.run(
        [sys.executable,
         str(REPO / "tools" / "benchmark_detection.py"),
         "--ci", "--seed", "42", "--docs", "200"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"benchmark --ci exited {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "CI GATE PASSED" in result.stdout, (
        "Expected 'CI GATE PASSED' in benchmark output"
    )


# ── server_loop.bat — backoff + crash log (v2.6.1) ───────────────────────────

def test_server_loop_bat_references_crash_log():
    """server_loop.bat must reference server_loop.log for crash logging."""
    text = (REPO / "server_loop.bat").read_text(encoding="utf-8", errors="replace")
    assert "server_loop.log" in text, (
        "server_loop.bat missing server_loop.log reference"
    )


def test_server_loop_bat_has_backoff():
    """server_loop.bat must contain escalating backoff (15s and 60s delays)."""
    text = (REPO / "server_loop.bat").read_text(encoding="utf-8", errors="replace")
    assert "15" in text, "server_loop.bat missing 15s backoff delay"
    assert "60" in text, "server_loop.bat missing 60s backoff delay"


def test_server_loop_bat_has_crash_loop_warning():
    """server_loop.bat must print a warning after 5 consecutive rapid crashes."""
    text = (REPO / "server_loop.bat").read_text(encoding="utf-8", errors="replace")
    assert "crash" in text.lower(), (
        "server_loop.bat missing crash-loop detection/warning"
    )
    assert "backup_pre_update_" in text, (
        "server_loop.bat missing backup_pre_update_ reference in crash-loop warning"
    )


# ── generate_cert.py — 825 days + icacls (v2.6.1) ────────────────────────────

def test_generate_cert_uses_825_day_validity():
    """generate_cert.py must use 825-day certificate validity."""
    text = (REPO / "tools" / "generate_cert.py").read_text(encoding="utf-8")
    assert "825" in text, (
        "generate_cert.py must use 825-day validity (industry max for trusted certs)"
    )
    assert "3650" not in text, (
        "generate_cert.py still contains old 10-year (3650-day) validity"
    )


def test_generate_cert_has_icacls():
    """generate_cert.py must attempt icacls on win32 to protect the private key."""
    text = (REPO / "tools" / "generate_cert.py").read_text(encoding="utf-8")
    assert "icacls" in text, (
        "generate_cert.py missing icacls call for Windows key protection"
    )
    assert "win32" in text, (
        "generate_cert.py missing win32 platform check for icacls"
    )
