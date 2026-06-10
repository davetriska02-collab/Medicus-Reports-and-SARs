"""SQLite document store: round-trips, migration, backup snapshot."""
import json
import sqlite3

import pytest

import sar.store as store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(store, "_initialised", False)
    # Connections are cached per-thread against the old path — drop them
    monkeypatch.setattr(store, "_local", __import__("threading").local())
    return tmp_path


def test_sar_round_trip():
    doc = {"id": "abc123", "last_modified": "2026-01-01T00:00:00",
           "archived": False, "subject": {"full_name": "John Smith"},
           "candidates": []}
    store.save_sar_doc(doc)
    loaded = store.load_all_sar_docs()
    assert loaded == [doc]

    doc["archived"] = True
    store.save_sar_doc(doc)  # upsert
    assert store.load_all_sar_docs() == [doc]

    store.delete_sar_doc("abc123")
    assert store.load_all_sar_docs() == []


def test_report_round_trip():
    doc = {"id": "r1", "last_modified": "x", "patient": {"full_name": "A"}}
    store.save_report_doc(doc)
    assert store.load_report_doc("r1") == doc
    assert store.load_all_report_docs() == [doc]
    assert store.delete_report_doc("r1") is True
    assert store.delete_report_doc("r1") is False
    assert store.load_report_doc("r1") is None


def test_migrate_json_dir(tmp_path):
    legacy = tmp_path / "sars"
    legacy.mkdir()
    (legacy / "s1.json").write_text(json.dumps(
        {"id": "s1", "pdf_files": ["/old/abs/path/doc.pdf"], "candidates": []}))
    (legacy / "s2.json").write_text(json.dumps(
        {"id": "s2", "pdf_files": ["doc2.pdf"], "candidates": []}))
    (legacy / "junk.txt").write_text("ignore me")

    n = store.migrate_json_dir(str(legacy), "sar")
    assert n == 2
    docs = {d["id"]: d for d in store.load_all_sar_docs()}
    assert docs["s1"]["pdf_files"] == ["doc.pdf"]  # abs path normalised
    assert docs["s2"]["pdf_files"] == ["doc2.pdf"]
    # Folder renamed, originals preserved
    assert not legacy.exists()
    assert (tmp_path / "sars_migrated_to_db" / "s1.json").exists()


def test_backup_snapshot(tmp_path):
    store.save_sar_doc({"id": "s1", "last_modified": "", "candidates": []})
    dest = tmp_path / "backup" / "snap.db"
    store.backup_db_to(str(dest))
    rows = sqlite3.connect(str(dest)).execute("SELECT id FROM sars").fetchall()
    assert rows == [("s1",)]
