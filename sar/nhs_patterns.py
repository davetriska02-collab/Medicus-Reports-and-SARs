import re
from sar.models import PIICategory


# NHS Number: 10 digits, optionally in 3-3-4 groups
NHS_NUMBER_PATTERN = re.compile(
    r'\b(\d{3}[\s\-]?\d{3}[\s\-]?\d{4})\b'
)

# UK phone numbers: landline and mobile
UK_PHONE_PATTERN = re.compile(
    r'\b((?:0\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})'
    r'|(?:\+44[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})'
    r'|(?:07\d{3}[\s\-]?\d{3}[\s\-]?\d{3}))\b'
)

# UK postcodes
UK_POSTCODE_PATTERN = re.compile(
    r'\b([A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2})\b',
    re.IGNORECASE
)

# Email addresses
EMAIL_PATTERN = re.compile(
    r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b'
)

# ── Safeguarding patterns ────────────────────────────────────────────────────
# Flagged for review — context determines whether third-party data is involved.
_SAFEGUARDING_PATTERNS = [
    (re.compile(r'\bsafeguarding\b', re.I),                                    "Safeguarding reference"),
    (re.compile(r'\bdomestic\s+(?:abuse|violence)\b', re.I),                   "Domestic abuse/violence"),
    (re.compile(r'\b(?:child\s+protection|child\s+at\s+risk|children\s+at\s+risk|child\s+in\s+need)\b', re.I), "Child protection"),
    (re.compile(r'\b(?:non[-\s]accidental\s+injury|NAI)\b', re.I),             "Non-accidental injury (NAI)"),
    (re.compile(r'\bMARAC\b', re.I),                                            "MARAC referral"),
    (re.compile(r'\b(?:FGM|female\s+genital\s+mutilation)\b', re.I),           "FGM reference"),
    (re.compile(r'\bat\s+risk\s+of\s+(?:harm|abuse)\b', re.I),                 "At risk of harm/abuse"),
    (re.compile(r'\bvulnerable\s+adult\b', re.I),                               "Vulnerable adult"),
    (re.compile(r'\b(?:physical|emotional|sexual)\s+abuse\b', re.I),           "Abuse type reference"),
    (re.compile(r'\bneglect(?:ed)?\b', re.I),                                  "Neglect reference"),
    (re.compile(r'\b(?:DA|DV)\s+referral\b', re.I),                            "DA/DV referral"),
    (re.compile(r'\bsocial\s+services\s+referral\b', re.I),                    "Social services referral"),
]

# ── Sexual health patterns ───────────────────────────────────────────────────
# Flagged for review — always needs human judgement (subject vs third-party).
_SEXUAL_HEALTH_PATTERNS = [
    (re.compile(r'\bHIV\b|\bhuman\s+immunodeficiency\s+virus\b', re.I),        "HIV reference"),
    (re.compile(r'\bAIDS\b|\bacquired\s+immuno?deficiency\s+syndrome\b', re.I), "AIDS reference"),
    (re.compile(r'\bchlamydia\b', re.I),                                        "STI: Chlamydia"),
    (re.compile(r'\bgonorrh(?:oe|e)a\b', re.I),                                "STI: Gonorrhoea"),
    (re.compile(r'\bsyphilis\b', re.I),                                         "STI: Syphilis"),
    (re.compile(r'\b(?:genital\s+herpes|HSV[-\s]?[12])\b', re.I),             "STI: Herpes"),
    (re.compile(r'\b(?:genital\s+warts?|HPV|human\s+papillomavirus)\b', re.I), "HPV/genital warts"),
    (re.compile(r'\btrichomonas(?:is)?\b', re.I),                              "STI: Trichomonas"),
    (re.compile(r'\b(?:sexually\s+transmitted\s+(?:infection|disease)|STI|STD)\b', re.I), "STI/STD reference"),
    (re.compile(r'\b(?:GUM\s+clinic|sexual\s+health\s+clinic|genitourinary\s+medicine)\b', re.I), "Sexual health clinic"),
    (re.compile(r'\b(?:sexual\s+assault|rape)\b', re.I),                       "Sexual assault/rape"),
    (re.compile(r'\b(?:PrEP|PEP)\b'),                                          "HIV prevention medication"),
]


def validate_nhs_number(candidate: str) -> bool:
    """Validate NHS number using the Modulus 11 check digit algorithm."""
    digits_only = re.sub(r'[\s\-]', '', candidate)
    if len(digits_only) != 10 or not digits_only.isdigit():
        return False

    total = sum(int(digits_only[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    check = 11 - remainder

    if check == 11:
        check = 0
    if check == 10:
        return False

    return check == int(digits_only[9])


def find_regex_matches(text: str, page_num: int) -> list[dict]:
    """
    Scan text for regex-detectable PII patterns.
    Returns list of dicts with: text, category, start, end, confidence, reason.
    """
    matches = []

    for match in NHS_NUMBER_PATTERN.finditer(text):
        candidate = match.group(1)
        if validate_nhs_number(candidate):
            matches.append({
                "text": candidate,
                "category": PIICategory.NHS_NUMBER,
                "start": match.start(1),
                "end": match.end(1),
                "confidence": 0.95,
                "reason": "Valid NHS number (Modulus 11 verified)",
            })

    for match in UK_PHONE_PATTERN.finditer(text):
        matches.append({
            "text": match.group(1),
            "category": PIICategory.PHONE_NUMBER,
            "start": match.start(1),
            "end": match.end(1),
            "confidence": 0.90,
            "reason": "UK phone number pattern",
        })

    for match in UK_POSTCODE_PATTERN.finditer(text):
        matches.append({
            "text": match.group(1),
            "category": PIICategory.POSTCODE,
            "start": match.start(1),
            "end": match.end(1),
            "confidence": 0.75,  # Flagged for review (surgery postcodes appear frequently)
            "reason": "UK postcode pattern",
        })

    for match in EMAIL_PATTERN.finditer(text):
        # Skip common NHS/surgery domain emails
        email = match.group(1).lower()
        if email.endswith(".nhs.uk") or email.endswith(".nhs.net"):
            continue
        matches.append({
            "text": match.group(1),
            "category": PIICategory.EMAIL,
            "start": match.start(1),
            "end": match.end(1),
            "confidence": 0.85,
            "reason": "Email address",
        })

    # Safeguarding — always flagged for human review (never auto-redact)
    for pattern, reason in _SAFEGUARDING_PATTERNS:
        for match in pattern.finditer(text):
            matches.append({
                "text": match.group(0),
                "category": PIICategory.SAFEGUARDING,
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.75,  # Below auto-redact threshold → always flagged
                "reason": reason,
            })

    # Sexual health — always flagged for human review (never auto-redact)
    for pattern, reason in _SEXUAL_HEALTH_PATTERNS:
        for match in pattern.finditer(text):
            matches.append({
                "text": match.group(0),
                "category": PIICategory.SEXUAL_HEALTH,
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.75,  # Below auto-redact threshold → always flagged
                "reason": reason,
            })

    return matches
