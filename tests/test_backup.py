"""Backup zips: contents, retention, status file."""
import json
import os
import threading
import zipfile

import pytest

import sar.backup as backup
import sar.store as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(store, "_initialised", False)
    monkeypatch.setattr(store, "_local", threading.local())
    monkeypatch.setattr(backup, "_BASE", tmp_path)
    monkeypatch.setattr(backup, "_STATUS_PATH", str(tmp_path / "last_backup.json"))
    (tmp_path / "data").mkdir()
    (tmp_path / "uploads").mkdir()
    (tmp_path / "output").mkdir()
    return tmp_path


def test_backup_contents_and_status(tmp_path):
    store.save_sar_doc({"id": "s1", "last_modified": "", "candidates": []})
    (tmp_path / "data" / "users.json").write_text("[]")
    (tmp_path / "data" / "audit").mkdir()
    (tmp_path / "data" / "audit" / "audit-202606.jsonl").write_text("{}\n")
    (tmp_path / "uploads" / "doc.pdf").write_bytes(b"%PDF-fake")

    dest = tmp_path / "backups"
    zip_path = backup.perform_backup(str(dest))

    names = set(zipfile.ZipFile(zip_path).namelist())
    assert "data/sarredact.db" in names
    assert "data/users.json" in names
    assert "data/audit/audit-202606.jsonl" in names
    assert any(n.startswith("uploads") and n.endswith("doc.pdf") for n in names)

    status = backup.get_status()
    assert status["ok"] is True and status["zip"] == zip_path


def test_backup_excludes_documents_when_disabled(tmp_path):
    (tmp_path / "uploads" / "doc.pdf").write_bytes(b"%PDF-fake")
    zip_path = backup.perform_backup(str(tmp_path / "backups"),
                                     include_documents=False)
    names = set(zipfile.ZipFile(zip_path).namelist())
    assert not any(n.startswith("uploads") for n in names)


def test_backup_retention(tmp_path):
    dest = tmp_path / "backups"
    dest.mkdir()
    # Pre-seed more than RETENTION old backups
    for i in range(backup.RETENTION + 3):
        (dest / f"sarredact-backup-2026010{i % 10}-00000{i}.zip").write_bytes(b"x")
    backup.perform_backup(str(dest))
    zips = [f for f in os.listdir(dest) if f.endswith(".zip")]
    assert len(zips) == backup.RETENTION
