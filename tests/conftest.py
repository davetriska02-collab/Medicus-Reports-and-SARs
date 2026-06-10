"""Test fixtures.

The Flask app resolves its data/uploads/output directories relative to its
own file, so app-level tests run against a throwaway copy of the codebase —
never against the working tree's data folders.
"""
import pathlib
import shutil
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def app_copy(tmp_path_factory):
    d = tmp_path_factory.mktemp("appcopy")
    for item in ("app.py", "serve.py", "sar", "templates", "static"):
        src = REPO / item
        if src.is_dir():
            shutil.copytree(src, d / item, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, d / item)
    return d


@pytest.fixture(scope="session")
def flask_app(app_copy):
    # Drop any repo-level imports of the same module names, then import the copy
    for mod in [m for m in list(sys.modules) if m == "app" or m == "sar" or m.startswith("sar.")]:
        del sys.modules[mod]
    sys.path.insert(0, str(app_copy))
    import app as app_module
    yield app_module
    sys.path.remove(str(app_copy))


@pytest.fixture()
def client(flask_app):
    return flask_app.app.test_client()
