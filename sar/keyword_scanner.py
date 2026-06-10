"""Scan uploaded medical records for template-specific keywords and return flagged matches."""
import os
import re

from sar.pdf_parser import get_full_page_text, get_page_count


def scan_keywords(pdf_files: list[str], questions: list) -> list:
    """
    Scan all uploaded PDFs for keywords defined in the template questions.

    Does a single read-pass through every page across all files, then checks
    each question's keyword list against the cached text.

    Returns a list of flag dicts — one per question that has at least one match:
    {
        question_id: str,
        question_text: str,
        matched_keywords: [str],   # de-duplicated, sorted
        match_count: int,           # total matches across all keywords
        matches: [                  # capped at 10 per question
            {keyword, source_file, page_num, context}
        ]
    }
    """
    if not pdf_files or not questions:
        return []

    # ── Phase 1: read every page once ────────────────────────────────────────
    pages: list[tuple[str, int, str]] = []   # (source_file, page_num, text)
    for pdf_path in pdf_files:
        if not os.path.exists(pdf_path):
            continue
        basename = os.path.basename(pdf_path)
        try:
            n = get_page_count(pdf_path)
        except Exception:
            continue
        for page_num in range(n):
            try:
                text = get_full_page_text(pdf_path, page_num)
            except Exception:
                continue
            if text and text.strip():
                pages.append((basename, page_num, text))

    if not pages:
        return []

    # ── Phase 2: per-question keyword search ─────────────────────────────────
    flags = []
    for q in questions:
        keywords = q.get("keywords", [])
        if not keywords:
            continue

        q_matches: list[dict] = []
        matched_kws: set[str] = set()

        for kw in keywords:
            if not kw:
                continue
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            kw_hit_count = 0

            for source_file, page_num, text in pages:
                for m in pattern.finditer(text):
                    if kw_hit_count >= 3:     # cap: 3 pages per keyword
                        break

                    # Extract ~120-char context window
                    start = max(0, m.start() - 120)
                    end = min(len(text), m.end() + 120)
                    ctx = text[start:end].replace("\n", " ").strip()
                    if start > 0:
                        ctx = "\u2026" + ctx
                    if end < len(text):
                        ctx = ctx + "\u2026"

                    q_matches.append({
                        "keyword": kw,
                        "source_file": source_file,
                        "page_num": page_num,
                        "context": ctx,
                    })
                    matched_kws.add(kw)
                    kw_hit_count += 1

                if kw_hit_count >= 3:
                    break

            if len(q_matches) >= 10:
                break  # enough matches for this question

        if q_matches:
            flags.append({
                "question_id": q["id"],
                "question_text": q["text"],
                "matched_keywords": sorted(matched_kws),
                "match_count": len(q_matches),
                "matches": q_matches[:10],
            })

    return flags
