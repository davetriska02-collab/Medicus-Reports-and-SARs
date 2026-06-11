import re
from typing import Optional
from sar.models import (
    RedactionCandidate, PIICategory, RedactionStatus,
    SubjectDetails, TextSpan, DetectionSettings,
)
from sar.nhs_patterns import find_regex_matches
from sar.staff_list import is_staff_name
from sar.name_detector import detect_names
from sar.custom_words import get_custom_words
from sar.risk_words import check_text_for_risk
from sar import ocr as _ocr
from sar.pdf_parser import page_needs_ocr as _page_needs_ocr

# Default confidence thresholds (used when no DetectionSettings provided)
AUTO_REDACT_THRESHOLD = 0.80
FLAG_THRESHOLD = 0.50

# Labels that indicate a name belongs to a staff member / practitioner.
# Use inline (?i:...) only for the label keywords; name-part stays case-sensitive.
_STAFF_LABEL_RE = re.compile(
    r'(?i:Practitioner|Record\s+author|Filed\s+by|Requested\s+by|'
    r'Authorised\s+by|Discontinued\s+by|Performed\s+by|Cancellation\s+reason)'
    r':\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Sister|Nurse|Rev|Mx)\.?\s+)*',
)

# Pattern to extract a staff name following a staff label.
# Stops at § (field separator), newline, "at " (org separator), or end of string.
# No re.IGNORECASE — name-part [A-Z][a-z] must remain case-sensitive.
_STAFF_NAME_EXTRACT_RE = re.compile(
    r'(?i:Practitioner|Record\s+author|Filed\s+by|Requested\s+by|'
    r'Authorised\s+by|Discontinued\s+by|Performed\s+by)\s*:\s*'
    r'((?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Sister|Nurse|Rev|Mx)\.?\s+)?'
    r'[A-Z][a-z\'-]+(?:[ \t]+[A-Z][a-z\'-]+){0,3})'
    r'(?=[ \t]*(?:\xa7|\n|$|at\s+[A-Z]))',
)


def normalize(text: str) -> str:
    return text.strip().lower()


def _strip_punctuation(text: str) -> str:
    """Remove trailing/leading punctuation from names."""
    return re.sub(r'^[\s\.,;:\'"-]+|[\s\.,;:\'"-]+$', '', text)


def _extract_page_staff_names(page_text: str) -> set[str]:
    """
    Extract names that appear in staff-labelled positions on this page.
    E.g. "Practitioner: Dr David Triska" → {"david triska", "dr david triska"}
    """
    staff = set()
    for m in _STAFF_NAME_EXTRACT_RE.finditer(page_text):
        raw = m.group(1).strip()
        staff.add(normalize(raw))
        # Also add without title prefix
        parts = raw.split()
        titles = {"mr", "mrs", "ms", "miss", "dr", "prof", "sister", "nurse", "rev", "mx"}
        while parts and parts[0].lower().rstrip('.') in titles:
            parts.pop(0)
        if parts:
            staff.add(normalize(" ".join(parts)))
    return staff


def _is_in_staff_label_context(page_text: str, name_start: int) -> bool:
    """
    Check if the name at name_start is directly preceded by a staff label
    (e.g. "Practitioner:", "Record author:").
    """
    # Look back up to 90 chars to allow for title prefix after the colon
    pre = page_text[max(0, name_start - 90):name_start]
    return bool(_STAFF_LABEL_RE.search(pre))


def is_subject_match(entity_text: str, subject: SubjectDetails) -> bool:
    """Check if detected text matches the data subject's known details."""
    cleaned = normalize(_strip_punctuation(entity_text))

    # Full name check
    if subject.full_name:
        if cleaned == normalize(subject.full_name):
            return True
        if normalize(subject.full_name) in cleaned:
            return True

    # First name (only match single-word entities — lone first name)
    if subject.first_name:
        entity_words = cleaned.split()
        if entity_words == [normalize(subject.first_name)]:
            return True

    # Last name: match lone surname OR full name where first word also matches the subject
    if subject.last_name:
        subj_last = normalize(subject.last_name)
        entity_words = cleaned.split()
        if subj_last in entity_words:
            if len(entity_words) == 1:
                return True  # Lone surname
            elif subject.first_name and normalize(subject.first_name) in entity_words:
                return True  # Both first & last name match subject

    # Aliases
    for alias in subject.aliases:
        if alias and cleaned == normalize(alias):
            return True

    # NHS number
    if subject.nhs_number:
        stripped_entity = re.sub(r'[\s\-]', '', entity_text)
        stripped_subject = re.sub(r'[\s\-]', '', subject.nhs_number)
        if stripped_entity == stripped_subject:
            return True

    # Date of birth
    if subject.date_of_birth and cleaned == normalize(subject.date_of_birth):
        return True

    # Phone
    if subject.phone:
        stripped_entity = re.sub(r'[\s\-\(\)]', '', entity_text)
        stripped_subject = re.sub(r'[\s\-\(\)]', '', subject.phone)
        if stripped_entity == stripped_subject:
            return True

    # Email
    if subject.email and cleaned == normalize(subject.email):
        return True

    # Address
    if subject.address:
        addr_norm = normalize(subject.address)
        addr_words = set(addr_norm.split())
        entity_words = set(cleaned.split())
        stopwords = {"the", "a", "an", "and", "of", "in", "at", "on", "to"}
        entity_words -= stopwords
        # House-number anchor: "14 High Street" is NOT the subject's address
        # when the subject lives at "12 High Street" — word overlap alone
        # would wrongly exclude neighbours and relatives at similar addresses.
        subj_numbers = set(re.findall(r'\b\d+[a-z]?\b', addr_norm))
        entity_numbers = set(re.findall(r'\b\d+[a-z]?\b', cleaned))
        numbers_conflict = (subj_numbers and entity_numbers
                            and not (subj_numbers & entity_numbers))
        if (not numbers_conflict and entity_words
                and len(entity_words & addr_words) >= max(1, len(entity_words) * 0.7)):
            return True

    return False


def build_page_text(page_spans: list[TextSpan]) -> tuple[str, list[tuple[int, int]]]:
    """
    Construct the page text by concatenating span texts, recording each span's
    exact [start, end) offset in the result.

    Spans on the same line are joined with a space, line/block changes with a
    newline. Because offsets are recorded during construction, mapping a regex
    match back to its spans is exact — repeated text ("Dr", dates, page
    furniture) can never cause a redaction box on the wrong occurrence.
    """
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    pos = 0
    prev = None
    for span in page_spans:
        if prev is not None:
            sep = " " if (span.block_no == prev.block_no and
                          span.line_no == prev.line_no) else "\n"
            parts.append(sep)
            pos += len(sep)
        parts.append(span.text)
        offsets.append((pos, pos + len(span.text)))
        pos += len(span.text)
        prev = span
    return "".join(parts), offsets


def map_text_to_spans(
    page_spans: list[TextSpan],
    offsets: list[tuple[int, int]],
    char_start: int,
    char_end: int,
) -> list[TextSpan]:
    """Return the spans whose recorded offsets overlap [char_start, char_end)."""
    return [span for span, (s, e) in zip(page_spans, offsets)
            if s < char_end and e > char_start]


def _name_variants(entity_text: str) -> list[str]:
    """Variants of a detected name for subject/staff comparison.
    'SMITH, John' also yields 'John SMITH' so surname-first formats match
    subject details entered as 'John Smith'."""
    variants = [entity_text]
    if "," in entity_text:
        left, _, right = entity_text.partition(",")
        reversed_form = f"{right.strip()} {left.strip()}".strip()
        if reversed_form:
            variants.append(reversed_form)
    return variants


def _context_snippet(page_text: str, start: int, end: int, pad: int = 70) -> str:
    """Surrounding text for the reviewer's reading pane — most decisions can
    be made from this without locating the match on the page image."""
    s = max(0, start - pad)
    e = min(len(page_text), end + pad)
    snippet = " ".join(page_text[s:e].split())
    prefix = "…" if s > 0 else ""
    suffix = "…" if e < len(page_text) else ""
    return f"{prefix}{snippet}{suffix}"


_OCR_CONFIDENCE_CAP = 0.85  # OCR text is less reliable; cap confidence here


def detect_pii(
    pdf_path: str,
    text_spans: list[TextSpan],
    subject: SubjectDetails,
    source_filename: str,
    settings: Optional[DetectionSettings] = None,
) -> tuple[list[RedactionCandidate], list[dict]]:
    """Detect third-party PII in a single PDF.

    Combines rule-based name detection with regex patterns.  For pages that
    appear to be scanned images (image present, very little native text):

    - If Tesseract is available: OCR the page and screen the resulting spans
      exactly like normal spans (confidence capped at 0.85).
    - If Tesseract is unavailable: record the page as unscreened.

    Returns a tuple ``(candidates, unscreened_pages)`` where
    ``unscreened_pages`` is a list of ``{"source_file": str, "page_num": int}``
    dicts for pages that were not checked due to missing OCR.

    For backwards compatibility with callers that only capture the first
    element of the return value, the tuple unpacks naturally:
    ``candidates = detect_pii(...)[0]``  or  ``candidates, _ = detect_pii(...)``
    """
    if settings is None:
        settings = DetectionSettings()

    auto_thresh = settings.auto_redact_threshold
    flag_thresh = settings.flag_threshold
    enabled = set(settings.enabled_categories)

    candidates = []
    unscreened_pages: list[dict] = []

    # Load custom words once for the whole document
    custom_words = get_custom_words()

    # Group spans by page
    pages: dict[int, list[TextSpan]] = {}
    for span in text_spans:
        pages.setdefault(span.page_num, []).append(span)

    # Determine total page count for the PDF so we can check pages that have
    # no spans at all (pure image pages produce zero spans from extract_text_spans).
    try:
        import fitz as _fitz
        _doc = _fitz.open(pdf_path)
        _total_pages = len(_doc)
        _doc.close()
    except Exception:
        _total_pages = max((p + 1 for p in pages), default=0)

    # Pre-compute OCR requirement for every page once, so the PDF is opened
    # at most once per page (M2.3: duplicate OCR-probe fix).
    _ocr_needed: dict[int, bool] = {}
    for _pn in range(_total_pages):
        try:
            _ocr_needed[_pn] = _page_needs_ocr(pdf_path, _pn)
        except Exception:
            _ocr_needed[_pn] = False

    # Build a combined set of page numbers to process:
    # pages that yielded spans + any pages that need OCR and have no spans.
    _all_page_nums: set[int] = set(pages.keys())
    for _pn in range(_total_pages):
        if _pn not in _all_page_nums:
            if _ocr_needed.get(_pn, False):
                _all_page_nums.add(_pn)
                pages[_pn] = []   # empty span list; will be OCR'd below

    for page_num, page_spans in sorted(pages.items()):
        # ── OCR / unscreened detection ────────────────────────────────────
        _use_ocr_spans = False
        _page_candidates_start = len(candidates)
        _needs_ocr = _ocr_needed.get(page_num, False)
        if _needs_ocr:
            if _ocr.tesseract_available():
                ocr_spans = _ocr.ocr_page_spans(pdf_path, page_num)
                if ocr_spans:
                    page_spans = ocr_spans
                    _use_ocr_spans = True
            else:
                unscreened_pages.append({"source_file": source_filename,
                                         "page_num": page_num})
                continue   # skip — cannot screen without OCR
        # Text is built from the spans themselves so regex match offsets map
        # exactly back to span bounding boxes (and the PDF is never re-opened).
        page_text, span_offsets = build_page_text(page_spans)
        if not page_text.strip():
            continue

        # Extract practitioner/author names from labelled fields on this page
        # (e.g. "Practitioner: Dr David Triska") for contextual staff exclusion
        page_staff_names = _extract_page_staff_names(page_text)

        # ── Name detection ────────────────────────────────────────────────
        name_matches = detect_names(page_text)

        for nm in name_matches:
            entity_text = _strip_punctuation(nm.text)
            if not entity_text:
                continue

            variants = _name_variants(entity_text)
            if any(is_subject_match(v, subject) for v in variants):
                candidates.append(RedactionCandidate(
                    text=entity_text,
                    category=PIICategory.PERSON_NAME,
                    status=RedactionStatus.EXCLUDED_SUBJECT,
                    confidence=1.0,
                    page_num=page_num,
                    reason="Matched data subject",
                    source_file=source_filename,
                    context=_context_snippet(page_text, nm.start, nm.end),
                ))
                continue

            # Check staff list first, then contextual staff names from labelled fields
            entity_norm = normalize(entity_text)
            # Strip title from entity for contextual check
            entity_words = entity_norm.split()
            titles = {"mr", "mrs", "ms", "miss", "dr", "prof", "sister", "nurse", "rev", "mx"}
            entity_no_title = " ".join(w for i, w in enumerate(entity_words)
                                       if not (i == 0 and w.rstrip('.') in titles))

            in_staff_label = _is_in_staff_label_context(page_text, nm.start)
            in_page_staff = (entity_norm in page_staff_names or
                             entity_no_title in page_staff_names)

            if any(is_staff_name(v) for v in variants) or in_staff_label or in_page_staff:
                reason = "Matched staff list"
                if in_staff_label:
                    reason = "Name in staff-labelled field (Practitioner/Author)"
                elif in_page_staff:
                    reason = "Name matched practitioner on this page"
                candidates.append(RedactionCandidate(
                    text=entity_text,
                    category=PIICategory.PERSON_NAME,
                    status=RedactionStatus.EXCLUDED_STAFF,
                    confidence=1.0,
                    page_num=page_num,
                    reason=reason,
                    source_file=source_filename,
                    context=_context_snippet(page_text, nm.start, nm.end),
                ))
                continue

            matched_spans = map_text_to_spans(page_spans, span_offsets, nm.start, nm.end)

            if matched_spans:
                x0 = min(s.x0 for s in matched_spans)
                y0 = min(s.y0 for s in matched_spans)
                x1 = max(s.x1 for s in matched_spans)
                y1 = max(s.y1 for s in matched_spans)
            else:
                x0 = y0 = x1 = y1 = 0.0

            confidence = nm.confidence
            status = (
                RedactionStatus.AUTO_REDACT
                if confidence >= auto_thresh
                else RedactionStatus.FLAGGED
            )

            candidates.append(RedactionCandidate(
                text=entity_text,
                category=PIICategory.PERSON_NAME,
                status=status,
                confidence=confidence,
                page_num=page_num,
                x0=x0, y0=y0, x1=x1, y1=y1,
                reason=nm.reason,
                source_file=source_filename,
                context=_context_snippet(page_text, nm.start, nm.end),
            ))

        # ── Regex detection ───────────────────────────────────────────────
        regex_matches = find_regex_matches(page_text, page_num)

        for rm in regex_matches:
            entity_text = rm["text"]

            if is_subject_match(entity_text, subject):
                candidates.append(RedactionCandidate(
                    text=entity_text,
                    category=rm["category"],
                    status=RedactionStatus.EXCLUDED_SUBJECT,
                    confidence=1.0,
                    page_num=page_num,
                    reason=f"Matched data subject ({rm['category'].value})",
                    source_file=source_filename,
                    context=_context_snippet(page_text, rm["start"], rm["end"]),
                ))
                continue

            matched_spans = map_text_to_spans(
                page_spans, span_offsets, rm["start"], rm["end"]
            )

            if matched_spans:
                x0 = min(s.x0 for s in matched_spans)
                y0 = min(s.y0 for s in matched_spans)
                x1 = max(s.x1 for s in matched_spans)
                y1 = max(s.y1 for s in matched_spans)
            else:
                x0 = y0 = x1 = y1 = 0.0

            confidence = rm["confidence"]
            status = (
                RedactionStatus.AUTO_REDACT
                if confidence >= auto_thresh
                else RedactionStatus.FLAGGED
            )

            candidates.append(RedactionCandidate(
                text=entity_text,
                category=rm["category"],
                status=status,
                confidence=confidence,
                page_num=page_num,
                x0=x0, y0=y0, x1=x1, y1=y1,
                reason=rm["reason"],
                source_file=source_filename,
                context=_context_snippet(page_text, rm["start"], rm["end"]),
            ))

        # ── Custom word detection ─────────────────────────────────────────────
        for cw in custom_words:
            phrase = cw["phrase"]
            flags = 0 if cw.get("case_sensitive", False) else re.IGNORECASE
            pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', flags)
            for match in pattern.finditer(page_text):
                matched_spans = map_text_to_spans(
                    page_spans, span_offsets, match.start(), match.end()
                )
                if matched_spans:
                    x0 = min(s.x0 for s in matched_spans)
                    y0 = min(s.y0 for s in matched_spans)
                    x1 = max(s.x1 for s in matched_spans)
                    y1 = max(s.y1 for s in matched_spans)
                else:
                    x0 = y0 = x1 = y1 = 0.0

                candidates.append(RedactionCandidate(
                    text=match.group(0),
                    category=PIICategory.CUSTOM_WORD,
                    status=RedactionStatus.AUTO_REDACT,
                    confidence=1.0,
                    page_num=page_num,
                    x0=x0, y0=y0, x1=x1, y1=y1,
                    reason=f"Custom redaction word/phrase",
                    source_file=source_filename,
                    context=_context_snippet(page_text, match.start(), match.end()),
                ))

        # ── OCR: cap confidence and prefix reason ────────────────────────
        if _use_ocr_spans:
            for c in candidates[_page_candidates_start:]:
                if c.confidence > _OCR_CONFIDENCE_CAP:
                    c.confidence = _OCR_CONFIDENCE_CAP
                if not c.reason.startswith("OCR: "):
                    c.reason = "OCR: " + c.reason

    # Deduplicate: same text + page + file + category
    # Also filter out disabled categories (except excluded_subject/staff which are always kept)
    seen = set()
    deduped = []
    for c in candidates:
        # Filter by enabled categories (always keep excluded items for audit trail)
        if (c.category.value not in enabled and
                c.status not in (RedactionStatus.EXCLUDED_SUBJECT, RedactionStatus.EXCLUDED_STAFF)):
            continue
        key = (normalize(c.text), c.page_num, c.source_file, c.category)
        if key not in seen:
            seen.add(key)
            # Compute risk flags for all candidates
            if not c.risk_flags:
                c.risk_flags = check_text_for_risk(c.text)
            deduped.append(c)

    return deduped, unscreened_pages
