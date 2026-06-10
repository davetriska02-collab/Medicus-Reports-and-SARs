"""Extract document dates from page text for chronological ordering."""
import re
from datetime import datetime
from typing import Optional

_FILENAME_DATE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})[_\s]')


def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract date from filename prefix like '2024-04-23_hash_desc.pdf'.
    Returns ISO date string "YYYY-MM-DD" or None.
    """
    m = _FILENAME_DATE_RE.match(filename)
    if m:
        date_str = m.group(1)
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            pass
    return None


_MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9,
    'oct': 10, 'nov': 11, 'dec': 12,
}

_MONTH_RE = '|'.join(_MONTH_NAMES.keys())

# Ordered by specificity — labelled dates first, then named-month, then numeric
_DATE_PATTERNS = [
    # "Date: 12 March 2024" or "Dated: 12th March 2024"
    re.compile(
        r'date[d]?\s*[:]\s*(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'(' + _MONTH_RE + r')\s+(\d{4})',
        re.IGNORECASE
    ),
    # "12 March 2024" or "12th March 2024"
    re.compile(
        r'(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'(' + _MONTH_RE + r')\s+(\d{4})',
        re.IGNORECASE
    ),
    # "March 12, 2024"
    re.compile(
        r'(' + _MONTH_RE + r')\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})',
        re.IGNORECASE
    ),
    # "12/03/2024" or "12-03-2024" (UK DD/MM/YYYY)
    re.compile(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})'),
]


def extract_document_date(page_text: str) -> Optional[str]:
    """
    Extract the most likely document date from page text.
    Scans the first ~2000 characters (typically the top of page 1
    where letter dates and document headers appear).

    Returns ISO date string "YYYY-MM-DD" or None.
    """
    search_text = page_text[:2000]

    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(search_text):
            try:
                groups = match.groups()
                g0, g1, g2 = groups

                if g0.isdigit() and not g1.isdigit() and g2.isdigit():
                    # day, month_name, year
                    day = int(g0)
                    month = _MONTH_NAMES.get(g1.lower())
                    year = int(g2)
                elif not g0.isdigit() and g1.isdigit() and g2.isdigit():
                    # month_name, day, year
                    month = _MONTH_NAMES.get(g0.lower())
                    day = int(g1)
                    year = int(g2)
                elif g0.isdigit() and g1.isdigit() and g2.isdigit():
                    # DD/MM/YYYY (UK format)
                    day = int(g0)
                    month = int(g1)
                    year = int(g2)
                else:
                    continue

                if not month or month < 1 or month > 12:
                    continue
                if day < 1 or day > 31:
                    continue
                if year < 1990 or year > 2040:
                    continue

                # Validate the date is real
                dt = datetime(year, month, day)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

    return None
