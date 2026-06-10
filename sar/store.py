"""SQLite-backed document store for SARs and reports.

One file (data/sarredact.db), WAL journal mode: transactional writes that
survive crashes, safe concurrent readers across waitress threads, a single
artefact to back up, and no thousands-of-small-files folders for NHS
antivirus to crawl. Documents are stored as JSON blobs — the in-memory model
is unchanged; this is the storage engine, not a schema rewrite.

Legacy JSON folders (data/sars/, data/reports/) are imported automatically on
first start and renamed *_migrated_to_db so the originals are kept.
"""
import json
import os
import sqlite3
import threading

DB_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent
              / "data" / "sarredact.db")

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False


def _conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        c = sqlite3.connect(DB_PATH, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.conn = c
    return c


def init_db() -> None:
    global _initialised
    with _init_lock:
        if _initialised:
            return
        with _conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS sars(
                id TEXT PRIMARY KEY,
                doc TEXT NOT NULL,
                last_modified TEXT DEFAULT '',
                archived INTEGER DEFAULT 0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS reports(
                id TEXT PRIMARY KEY,
                doc TEXT NOT NULL,
                last_modified TEXT DEFAULT '')""")
        _initialised = True


# ── SARs ────────────────────────────────────────────────────────────────────

def save_sar_doc(doc: dict) -> None:
    init_db()
    with _conn() as c:
        c.execute(
            "INSERT INTO sars(id, doc, last_modified, archived) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET doc=excluded.doc, "
            "last_modified=excluded.last_modified, archived=excluded.archived",
            (doc["id"], json.dumps(doc), doc.get("last_modified", ""),
             1 if doc.get("archived") else 0))


def load_all_sar_docs() -> list[dict]:
    init_db()
    return [json.loads(row[0]) for row in
            _conn().execute("SELECT doc FROM sars")]


def delete_sar_doc(sar_id: str) -> None:
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM sars WHERE id=?", (sar_id,))


# ── Reports ─────────────────────────────────────────────────────────────────

def save_report_doc(doc: dict) -> None:
    init_db()
    with _conn() as c:
        c.execute(
            "INSERT INTO reports(id, doc, last_modified) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET doc=excluded.doc, "
            "last_modified=excluded.last_modified",
            (doc["id"], json.dumps(doc), doc.get("last_modified", "")))


def load_report_doc(report_id: str) -> dict | None:
    init_db()
    row = _conn().execute("SELECT doc FROM reports WHERE id=?",
                          (report_id,)).fetchone()
    return json.loads(row[0]) if row else None


def load_all_report_docs() -> list[dict]:
    init_db()
    return [json.loads(row[0]) for row in
            _conn().execute("SELECT doc FROM reports")]


def delete_report_doc(report_id: str) -> bool:
    init_db()
    with _conn() as c:
        cur = c.execute("DELETE FROM reports WHERE id=?", (report_id,))
        return cur.rowcount > 0


# ── Legacy JSON folder migration ────────────────────────────────────────────

def migrate_json_dir(json_dir: str, kind: str) -> int:
    """Import data/<sars|reports>/*.json into the db, then rename the folder
    to <dir>_migrated_to_db so originals are preserved. Returns count."""
    if not os.path.isdir(json_dir):
        return 0
    init_db()
    migrated = 0
    for fname in sorted(os.listdir(json_dir)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(json_dir, fname), encoding="utf-8") as f:
                doc = json.load(f)
            # Normalise legacy absolute pdf paths to basenames
            if "pdf_files" in doc:
                doc["pdf_files"] = [os.path.basename(p) for p in doc["pdf_files"]]
            if kind == "sar":
                save_sar_doc(doc)
            else:
                save_report_doc(doc)
            migrated += 1
        except Exception as e:
            print(f"[store] WARNING: could not migrate {fname}: {e}")
    if migrated or not os.listdir(json_dir):
        target = json_dir.rstrip("/\\") + "_migrated_to_db"
        try:
            if not os.path.exists(target):
                os.rename(json_dir, target)
        except OSError:
            pass
    return migrated


# ── Backup ──────────────────────────────────────────────────────────────────

def backup_db_to(dest_path: str) -> None:
    """Consistent snapshot of the live database via the SQLite backup API
    (safe while writes are happening — never just copy the .db file)."""
    init_db()
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    dest = sqlite3.connect(dest_path)
    try:
        _conn().backup(dest)
    finally:
        dest.close()
