"""Static integrity checks for the Jinja/HTML templates.

These catch structural bugs that unit tests on Python code cannot — most
importantly unbalanced <script> tags, which silently drop JavaScript (and
render Jinja expressions as visible page text). A real regression of exactly
this kind shipped in review.html (v2.5.1) and reached users; this guards it.
"""
import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_HTML_FILES = sorted(TEMPLATES_DIR.rglob("*.html"))


def test_templates_exist():
    assert _HTML_FILES, "no templates found"


@pytest.mark.parametrize("path", _HTML_FILES, ids=lambda p: p.name)
def test_script_tags_balanced(path):
    """Every <script ...> must have a matching </script>.

    An orphaned </script> (or a missing opening tag) causes the browser to
    render the following JS as text — the v2.5.1 review.html bug.
    """
    text = path.read_text(encoding="utf-8")
    opens = len(re.findall(r"<script\b", text))
    closes = len(re.findall(r"</script\s*>", text))
    assert opens == closes, (
        f"{path.name}: {opens} <script> opens vs {closes} </script> closes "
        "— unbalanced script tags will break the page's JavaScript")


@pytest.mark.parametrize("path", _HTML_FILES, ids=lambda p: p.name)
def test_no_window_assignment_outside_script(path):
    """A `window.X = {{ ... }}` line must sit inside a <script> block.

    Detects the precise C1 failure mode: globals stranded in HTML body where
    they render as text instead of executing.
    """
    text = path.read_text(encoding="utf-8")
    # Remove all script blocks; any window.* assignment left over is stranded.
    stripped = re.sub(r"<script\b.*?</script\s*>", "", text,
                      flags=re.DOTALL | re.IGNORECASE)
    stray = re.findall(r"^\s*window\.\w+\s*=", stripped, flags=re.MULTILINE)
    assert not stray, (
        f"{path.name}: window assignment(s) outside any <script> block "
        f"({stray}) — they will render as page text, not execute")
