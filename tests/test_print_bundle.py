"""Combined print bundle: ordering, page numbering, splitting, guards."""
import os

import fitz

from tests.test_response_pack import _make_sar


def _make_pdf(path, n_pages=1, text="content"):
    doc = fitz.open()
    for i in range(n_pages):
        doc.new_page().insert_text(fitz.Point(72, 100), f"{text} p{i + 1}")
    doc.save(path)
    doc.close()


def _bundle_text(path):
    with fitz.open(path) as d:
        return "".join(p.get_text() for p in d)


def test_bundle_combines_everything_in_order(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    assert c.post(f"/api/sar/{sar.id}/finalise", headers=H).status_code == 200
    assert c.post(f"/api/sar/{sar.id}/response-pack", headers=H,
                  json={}).status_code == 200

    od = os.path.join(flask_app.OUTPUT_DIR, sar.id)
    # Add a second redacted document so ordering is observable
    _make_pdf(os.path.join(od, "another_redacted.pdf"), n_pages=2,
              text="second doc")

    r = c.post(f"/api/sar/{sar.id}/print-bundle", headers=H)
    assert r.status_code == 200, r.get_json()
    files = r.get_json()["files"]
    assert files == [f"print_bundle_{sar.id}.pdf"]

    bundle_path = os.path.join(od, files[0])
    text = _bundle_text(bundle_path)
    # Contents page present, with all documents listed
    assert "DISCLOSURE BUNDLE" in text
    assert "Cover letter" in text
    assert "Certificate of redaction" in text
    # Continuous page numbering footer
    assert "Page 1 of" in text
    # Cover letter content comes before the second redacted doc's content
    assert text.index("Article 15") < text.index("second doc")
    # The redaction log must NOT be merged into the disclosure
    assert "REDACTION LOG" not in text

    # Bundle appears in the outputs listing
    d = c.get(f"/api/sar/{sar.id}/outputs").get_json()
    assert d["bundle_files"] == files


def test_bundle_splits_into_parts_capped_at_five(tmp_path):
    from sar.print_bundle import build_print_bundle
    from sar.models import SARRequest, SubjectDetails

    od = tmp_path / "out"
    od.mkdir()
    for i in range(8):
        _make_pdf(str(od / f"doc{i}_redacted.pdf"), n_pages=2, text=f"doc{i}")

    sar = SARRequest(subject=SubjectDetails(full_name="Bob Sample"))
    # Force a split: cap far below the combined size of 8 PDFs
    names = build_print_bundle(sar, str(od), max_part_mb=0)
    assert 2 <= len(names) <= 5
    assert names[0].endswith(f"_part1of{len(names)}.pdf")

    # Page numbering is continuous across parts
    total = sum(fitz.open(str(od / n)).page_count for n in names)
    part2_text = _bundle_text(str(od / names[1]))
    assert f"Part 2 of {len(names)}" in part2_text

    # Re-running replaces old parts rather than accumulating
    names2 = build_print_bundle(sar, str(od), max_part_mb=200)
    leftover = [f for f in os.listdir(od) if f.startswith("print_bundle_")]
    assert sorted(leftover) == sorted(names2)
    assert len(names2) == 1


def test_bundle_requires_finalise_and_blocks_on_failures(flask_app, admin_client):
    c, H = admin_client
    sar = _make_sar(flask_app)
    r = c.post(f"/api/sar/{sar.id}/print-bundle", headers=H)
    assert r.status_code == 400
    assert "Finalise" in r.get_json()["error"]

    sar2 = _make_sar(flask_app, with_failure=True)
    c.post(f"/api/sar/{sar2.id}/finalise", headers=H)
    r = c.post(f"/api/sar/{sar2.id}/print-bundle", headers=H)
    assert r.status_code == 409
    assert "failed" in r.get_json()["error"]
