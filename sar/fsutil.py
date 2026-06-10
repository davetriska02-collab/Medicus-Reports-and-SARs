"""Filesystem helpers shared by the JSON stores.

Atomic writes: write to a temp file in the same directory then os.replace(),
which is atomic on both Windows (NTFS) and POSIX. A crash or concurrent reader
mid-write can never observe a truncated file.
"""
import json
import os
import tempfile


def atomic_write_json(path: str, data) -> None:
    dirname = os.path.dirname(os.path.abspath(path))
    os.makedirs(dirname, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dirname, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def unique_path(directory: str, filename: str) -> str:
    """Return a path in directory for filename, suffixing -2, -3... on collision."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base}-{n}{ext}")
        n += 1
    return candidate
