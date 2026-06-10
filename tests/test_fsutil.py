"""Atomic write + unique path helpers."""
import json
import os

import pytest

from sar.fsutil import atomic_write_json, unique_path


def test_atomic_write_creates_and_replaces(tmp_path):
    p = tmp_path / "x.json"
    atomic_write_json(str(p), {"a": 1})
    atomic_write_json(str(p), {"a": 2})
    assert json.load(open(p)) == {"a": 2}
    # No temp files left behind
    assert os.listdir(tmp_path) == ["x.json"]


def test_atomic_write_failure_leaves_original(tmp_path):
    p = tmp_path / "x.json"
    atomic_write_json(str(p), {"a": 1})
    with pytest.raises(TypeError):
        atomic_write_json(str(p), {"bad": object()})  # not JSON-serialisable
    assert json.load(open(p)) == {"a": 1}  # original intact
    assert sorted(os.listdir(tmp_path)) == ["x.json"]  # temp cleaned up


def test_unique_path_suffixes(tmp_path):
    first = unique_path(str(tmp_path), "scan.pdf")
    assert first.endswith("scan.pdf")
    open(first, "w").close()
    second = unique_path(str(tmp_path), "scan.pdf")
    assert second.endswith("scan-2.pdf")
    open(second, "w").close()
    third = unique_path(str(tmp_path), "scan.pdf")
    assert third.endswith("scan-3.pdf")
