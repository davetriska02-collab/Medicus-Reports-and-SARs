"""Combined disclosure bundle for printing.

Practices hand SAR disclosures over on paper. Printing hundreds of individual
output files one at a time is slow, so this merges everything destined for the
data subject into a single PDF — one print job — in court-bundle style:

- Contents page listing every enclosed document and its starting page
- Order: cover letter, certificate of redaction, then the redacted documents
- Continuous "Page n of N" footer across the whole bundle
- Split into parts (max 5) only when the combined size exceeds the cap

The redaction log is deliberately EXCLUDED: it records the redacted text
verbatim, so including it would defeat the redaction. It remains available
as a separate internal file.
"""
import math
import os

import fitz

_A4_W, _A4_H = 595, 842
_MARGIN = 56
_FOOTER_Y = _A4_H - 26

# Above this combined size the bundle is split into parts
DEFAULT_MAX_PART_MB = 200
MAX_PARTS = 5

BUNDLE_PREFIX = "print_bundle_"


def _disclosure_files(output_dir: str) -> list[str]:
    """Files destined for the data subject, in print order.

    Cover letter first, certificate second, then redacted documents sorted
    by name. The redaction log and any previous bundles are excluded.
    """
    names = sorted(os.listdir(output_dir))
    letters = [f for f in names if f.startswith("cover_letter_")]
    certs = [f for f in names if f.startswith("certificate_of_redaction_")]
    redacted = [f for f in names if f.endswith("_redacted.pdf")]
    return letters + certs + redacted


def _label(filename: str) -> str:
    if filename.startswith("cover_letter_"):
        return "Cover letter"
    if filename.startswith("certificate_of_redaction_"):
        return "Certificate of redaction"
    return filename[:-len("_redacted.pdf")] + " (redacted)" \
        if filename.endswith("_redacted.pdf") else filename


def _split_into_parts(files: list[tuple[str, int]],
                      max_part_bytes: int) -> list[list[str]]:
    """Greedy contiguous split keeping print order; never exceeds MAX_PARTS.

    files: list of (filename, size_bytes). A single file larger than the cap
    gets a part to itself. If the greedy split produces too many parts the
    cap is raised until it fits — a hard MAX_PARTS guarantee matters more
    than the size preference.
    """
    total = sum(s for _, s in files)
    if total <= max_part_bytes:
        return [[f for f, _ in files]]

    cap = max(max_part_bytes, math.ceil(total / MAX_PARTS))
    while True:
        parts, current, current_size = [], [], 0
        for f, s in files:
            if current and current_size + s > cap:
                parts.append(current)
                current, current_size = [], 0
            current.append(f)
            current_size += s
        if current:
            parts.append(current)
        if len(parts) <= MAX_PARTS:
            return parts
        cap = int(cap * 1.25)


def _contents_page(doc: fitz.Document, *, subject_name: str, sar_id: str,
                   generated: str, part_num: int, n_parts: int,
                   entries: list[tuple[str, int]], total_pages: int):
    """Insert the contents page(s) at the front of a part.

    entries: (label, bundle_page_number) — page numbers are continuous
    across all parts. Returns nothing; pages are inserted at position 0.
    """
    lines_per_page = 38
    chunks = [entries[i:i + lines_per_page]
              for i in range(0, len(entries), lines_per_page)] or [[]]

    for ci, chunk in enumerate(reversed(chunks)):
        page = doc.new_page(pno=0, width=_A4_W, height=_A4_H)
        y = _MARGIN + 10
        first_contents_page = (ci == len(chunks) - 1)
        if first_contents_page:
            page.insert_text(fitz.Point(_MARGIN, y), "DISCLOSURE BUNDLE",
                             fontsize=15, fontname="hebo")
            y += 22
            page.insert_text(fitz.Point(_MARGIN, y),
                             f"Subject access request — {subject_name}",
                             fontsize=10)
            y += 15
            sub = f"Ref {sar_id} · Generated {generated} · {total_pages} pages"
            if n_parts > 1:
                sub += f" · Part {part_num} of {n_parts}"
            page.insert_text(fitz.Point(_MARGIN, y), sub,
                             fontsize=9, color=(0.35, 0.35, 0.35))
            y += 24
            page.insert_text(fitz.Point(_MARGIN, y), "Contents",
                             fontsize=11, fontname="hebo")
            y += 18
        for label, start_page in chunk:
            text = label[:88]
            page.insert_text(fitz.Point(_MARGIN, y), text, fontsize=9)
            page.insert_text(fitz.Point(_A4_W - _MARGIN - 60, y),
                             f"page {start_page}", fontsize=9,
                             color=(0.35, 0.35, 0.35))
            y += 14


def _stamp_footers(doc: fitz.Document, *, first_number: int, total: int,
                   n_contents_pages: int, part_num: int, n_parts: int):
    """Continuous page numbers on document pages; contents pages unnumbered."""
    n = first_number
    for i, page in enumerate(doc):
        if i < n_contents_pages:
            continue
        text = f"Page {n} of {total}"
        if n_parts > 1:
            text += f"  ·  Part {part_num} of {n_parts}"
        width = fitz.get_text_length(text, fontsize=8)
        page.insert_text(
            fitz.Point((page.rect.width - width) / 2, _FOOTER_Y),
            text, fontsize=8, color=(0.4, 0.4, 0.4))
        n += 1


def build_print_bundle(sar, output_dir: str,
                       max_part_mb: int = DEFAULT_MAX_PART_MB) -> list[str]:
    """Merge the disclosure files in output_dir into 1–5 printable PDFs.

    Returns the bundle filenames (basenames). Raises ValueError if there is
    nothing to bundle or a source file cannot be merged — a broken source
    must fail loudly rather than silently vanish from a legal disclosure.
    """
    from datetime import date

    files = _disclosure_files(output_dir)
    if not files:
        raise ValueError("No disclosure files to bundle — finalise the SAR first")

    # Remove bundles from a previous run so stale parts can't linger
    for f in os.listdir(output_dir):
        if f.startswith(BUNDLE_PREFIX):
            os.remove(os.path.join(output_dir, f))

    sized = [(f, os.path.getsize(os.path.join(output_dir, f))) for f in files]
    parts = _split_into_parts(sized, max_part_mb * 1024 * 1024)
    n_parts = len(parts)

    # Page counts first so contents pages can show continuous numbering
    page_counts: dict[str, int] = {}
    for f in files:
        try:
            with fitz.open(os.path.join(output_dir, f)) as d:
                page_counts[f] = d.page_count
        except Exception as e:
            raise ValueError(f"Cannot read {f} for bundling: {e}") from e
    total_pages = sum(page_counts.values())

    generated = date.today().strftime("%d %B %Y")
    subject_name = (sar.subject.full_name
                    or f"{sar.subject.first_name} {sar.subject.last_name}").strip()

    out_names: list[str] = []
    page_cursor = 1
    for pi, part_files in enumerate(parts, start=1):
        bundle = fitz.open()
        entries = []
        cursor = page_cursor
        for f in part_files:
            entries.append((_label(f), cursor))
            cursor += page_counts[f]
            try:
                with fitz.open(os.path.join(output_dir, f)) as src:
                    bundle.insert_pdf(src)
            except Exception as e:
                bundle.close()
                raise ValueError(f"Cannot merge {f} into bundle: {e}") from e

        n_doc_pages = bundle.page_count
        _contents_page(bundle, subject_name=subject_name, sar_id=sar.id,
                       generated=generated, part_num=pi, n_parts=n_parts,
                       entries=entries, total_pages=total_pages)
        n_contents = bundle.page_count - n_doc_pages
        _stamp_footers(bundle, first_number=page_cursor, total=total_pages,
                       n_contents_pages=n_contents, part_num=pi,
                       n_parts=n_parts)
        page_cursor = cursor

        if n_parts == 1:
            name = f"{BUNDLE_PREFIX}{sar.id}.pdf"
        else:
            name = f"{BUNDLE_PREFIX}{sar.id}_part{pi}of{n_parts}.pdf"
        bundle.save(os.path.join(output_dir, name), garbage=3, deflate=True)
        bundle.close()
        out_names.append(name)

    return out_names
