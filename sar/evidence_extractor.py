"""Rule-based evidence extraction from medical records for report questions."""
import os
import re
from sar.pdf_parser import get_full_page_text, get_page_count


def extract_evidence(pdf_files: list[str], question: dict) -> list[dict]:
    """
    Search uploaded PDFs for text snippets relevant to a template question.
    Uses keyword matching against paragraphs of text.

    Returns list of evidence snippet dicts sorted by relevance (max 5).
    """
    keywords = [kw.lower() for kw in question.get("keywords", [])]
    section_hints = [sh.lower() for sh in question.get("section_hints", [])]
    if not keywords and not section_hints:
        return []

    snippets = []

    for pdf_path in pdf_files:
        if not os.path.exists(pdf_path):
            continue
        basename = os.path.basename(pdf_path)
        try:
            page_count = get_page_count(pdf_path)
        except Exception:
            continue

        for page_num in range(page_count):
            try:
                page_text = get_full_page_text(pdf_path, page_num)
            except Exception:
                continue
            if not page_text.strip():
                continue

            # Split into paragraphs (double newline or single newline before uppercase)
            paragraphs = re.split(r'\n\s*\n', page_text)

            for para in paragraphs:
                para_stripped = para.strip()
                if len(para_stripped) < 10:
                    continue

                para_lower = para_stripped.lower()
                score = 0.0

                # Score keyword matches
                matched = 0
                for kw in keywords:
                    if kw in para_lower:
                        matched += 1
                if keywords:
                    score += matched / len(keywords)

                # Bonus for section hint matches
                for sh in section_hints:
                    if sh in para_lower:
                        score += 0.3

                if score > 0:
                    # Trim snippet to reasonable length
                    snippet_text = para_stripped[:500]
                    if len(para_stripped) > 500:
                        snippet_text += "..."

                    snippets.append({
                        "text": snippet_text,
                        "source_file": basename,
                        "page_num": page_num,
                        "confidence": min(1.0, score),
                    })

    # Sort by confidence (highest first), take top 5
    snippets.sort(key=lambda s: s["confidence"], reverse=True)
    return snippets[:5]
