"""Detection quality: name formats, exclusions, span mapping, regex patterns."""
import pytest

from sar.name_detector import detect_names
from sar.detector import (detect_pii, is_subject_match, build_page_text,
                          map_text_to_spans)
from sar.models import (TextSpan, SubjectDetails, PIICategory, RedactionStatus)
from sar.nhs_patterns import validate_nhs_number, find_regex_matches


def _texts(matches):
    return [m.text for m in matches]


# ── Name format coverage ────────────────────────────────────────────────────

def test_surname_comma_format_detected():
    matches = detect_names("SMITH, John was seen today with his wife.")
    assert any("SMITH, John" in t for t in _texts(matches))


def test_re_line_surname_comma():
    matches = detect_names("Re: JONES, Mary (DOB 01/02/1960)")
    assert any("JONES, Mary" in t for t in _texts(matches))


def test_allcaps_surname_comma_allcaps_forename():
    matches = detect_names("Patient: O'BRIEN, SIOBHAN")
    assert any("O'BRIEN" in t for t in _texts(matches))


def test_titlecase_comma_known_surname():
    matches = detect_names("cc Taylor, James (solicitor)")
    assert any(t.startswith("Taylor, James") for t in _texts(matches))


def test_titlecase_comma_unknown_first_word_not_detected():
    # "However" is not a surname — sentence punctuation must not fire
    matches = detect_names("However, John attended late.")
    assert not any(t.startswith("However") for t in _texts(matches))


def test_mc_name_with_title():
    matches = detect_names("Seen by neighbour Mr McDonald yesterday.")
    assert any("McDonald" in t for t in _texts(matches))


def test_apostrophe_name_with_title():
    matches = detect_names("Letter from Mrs O'Brien received.")
    assert any("O'Brien" in t for t in _texts(matches))


def test_allcaps_full_name_with_known_name():
    matches = detect_names("Next of kin: JOHN SMITH")
    assert any("JOHN SMITH" in t for t in _texts(matches))


def test_allcaps_section_headers_not_detected():
    for header in ("ACTIVE PROBLEMS", "BLOOD PRESSURE", "PAST HISTORY",
                   "REPEAT PRESCRIPTION"):
        matches = detect_names(header)
        assert not _texts(matches), f"header {header!r} wrongly detected"


def test_record_header_comma_lines_not_detected():
    matches = detect_names("MEDICATION, Aspirin 75mg od")
    assert not any("MEDICATION" in t for t in _texts(matches))


def test_eponyms_not_detected_as_names():
    for phrase in ("Parkinson Disease", "Barrett Oesophagus", "Colles Fracture"):
        matches = detect_names(f"Diagnosis: {phrase} confirmed.")
        assert not _texts(matches), f"eponym {phrase!r} wrongly detected"


def test_plain_full_name_still_detected():
    matches = detect_names("Spoke with Jane Wilson about the results.")
    assert any("Jane Wilson" in t for t in _texts(matches))


# ── Subject matching ────────────────────────────────────────────────────────

SUBJECT = SubjectDetails(full_name="John Smith", first_name="John",
                         last_name="Smith", nhs_number="943 476 5919",
                         address="12 High Street, Guildford")


def _spans_for_lines(lines):
    """One span per line, line i at y = 100*i."""
    return [TextSpan(text=ln, page_num=0, x0=72, y0=100 * i + 10,
                     x1=400, y1=100 * i + 22, block_no=0, line_no=i, span_no=0)
            for i, ln in enumerate(lines)]


def test_surname_first_subject_excluded_not_redacted():
    spans = _spans_for_lines(["SMITH, John attended with daughter Emma Watson."])
    cands = detect_pii("unused.pdf", spans, SUBJECT, "doc.pdf")
    by_text = {c.text: c for c in cands}
    subj = next((c for c in cands if "SMITH, John" in c.text), None)
    assert subj is not None and subj.status == RedactionStatus.EXCLUDED_SUBJECT
    third = next((c for c in cands if "Emma Watson" in c.text), None)
    assert third is not None and third.status in (RedactionStatus.AUTO_REDACT,
                                                  RedactionStatus.FLAGGED)


def test_subject_nhs_number_excluded():
    spans = _spans_for_lines(["NHS Number: 943 476 5919"])
    cands = detect_pii("unused.pdf", spans, SUBJECT, "doc.pdf")
    nhs = next((c for c in cands if c.category == PIICategory.NHS_NUMBER), None)
    assert nhs is not None and nhs.status == RedactionStatus.EXCLUDED_SUBJECT


def test_staff_label_context_excludes_practitioner():
    spans = _spans_for_lines(["Practitioner: Dr David Jones"])
    cands = detect_pii("unused.pdf", spans, SUBJECT, "doc.pdf")
    staff = next((c for c in cands if "Jones" in c.text), None)
    assert staff is not None and staff.status == RedactionStatus.EXCLUDED_STAFF


def test_context_snippet_captured():
    spans = _spans_for_lines(["Seen with daughter Emma Watson at the clinic today."])
    cands = detect_pii("unused.pdf", spans, SUBJECT, "doc.pdf")
    emma = next(c for c in cands if "Emma Watson" in c.text)
    assert "daughter" in emma.context and "clinic" in emma.context


def test_address_house_number_anchoring():
    # Same street, different number → NOT the subject's address
    assert not is_subject_match("14 High Street Guildford", SUBJECT)
    # Subject's own address → matches
    assert is_subject_match("12 High Street Guildford", SUBJECT)


# ── Span mapping exactness ──────────────────────────────────────────────────

def test_repeated_text_maps_to_correct_occurrence():
    spans = [
        TextSpan(text="Dr", page_num=0, x0=72, y0=10, x1=90, y1=22,
                 block_no=0, line_no=0, span_no=0),
        TextSpan(text="Smith", page_num=0, x0=95, y0=10, x1=140, y1=22,
                 block_no=0, line_no=0, span_no=1),
        TextSpan(text="Dr", page_num=0, x0=72, y0=110, x1=90, y1=122,
                 block_no=0, line_no=1, span_no=0),
        TextSpan(text="Wilson", page_num=0, x0=95, y0=110, x1=150, y1=122,
                 block_no=0, line_no=1, span_no=1),
    ]
    text, offsets = build_page_text(spans)
    assert text == "Dr Smith\nDr Wilson"

    # The second "Dr" (chars 9-11) must map to the second span, not the first
    mapped = map_text_to_spans(spans, offsets, 9, 18)
    assert [s.y0 for s in mapped] == [110, 110]

    # End to end: the "Dr Wilson" candidate's box must be on line 2
    cands = detect_pii("unused.pdf", spans, SUBJECT, "doc.pdf")
    wilson = next(c for c in cands if "Wilson" in c.text)
    assert wilson.y0 >= 110


# ── Regex patterns ──────────────────────────────────────────────────────────

def test_nhs_number_mod11():
    assert validate_nhs_number("943 476 5919")       # valid check digit
    assert not validate_nhs_number("943 476 5918")   # invalid check digit
    assert not validate_nhs_number("12345")


def test_regex_categories():
    text = ("Contact on 07700 900123 or john.doe@example.com. "
            "Postcode GU8 5SU. NHS 943 476 5919.")
    matches = find_regex_matches(text, 0)
    cats = {m["category"] for m in matches}
    assert PIICategory.PHONE_NUMBER in cats
    assert PIICategory.EMAIL in cats
    assert PIICategory.POSTCODE in cats
    assert PIICategory.NHS_NUMBER in cats


def test_nhs_domain_emails_skipped():
    matches = find_regex_matches("From: surgery.admin@nhs.net", 0)
    assert PIICategory.EMAIL not in {m["category"] for m in matches}
