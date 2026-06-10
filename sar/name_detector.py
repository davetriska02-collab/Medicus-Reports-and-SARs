"""
Rule-based name detection for UK medical records.

Strategy (in order of confidence):
1. Title-anchored names: "Dr Smith", "Mr Jones", "Mrs Williams" etc.
   These are very reliable and cover the vast majority of names in clinical notes.
2. Context-anchored names: "patient's daughter Jane", "carer Michael" etc.
3. UK common first-name list matching for capitalised words in certain contexts.
4. "Dear [Name]" patterns (referral letters).

No ML libraries required - works on any Python version.
"""

import re
from dataclasses import dataclass

# ─── UK Name Lists ────────────────────────────────────────────────────────────
# A curated set of common UK first names (both genders).
# Drawn from ONS "Baby names in England and Wales" top 500 lists + classic names.

UK_FIRST_NAMES = {
    # Top UK male names
    "oliver","george","harry","jack","noah","charlie","jacob","alfie","freddie",
    "oscar","james","william","thomas","henry","leo","ethan","joshua","archie",
    "alexander","joseph","samuel","edward","adam","max","lucas","mason","ibrahim",
    "muhammad","daniel","logan","tyler","jayden","ryan","isaac","harrison",
    "jake","riley","reuben","stanley","teddy","reggie","louie","theo","finn",
    "evan","luca","leon","sebastian","dominic","hugo","felix","elliot","adam",
    "nathaniel","gabriel","albert","arthur","frankie","jenson","harley",
    "michael","david","christopher","andrew","mark","john","paul","stephen",
    "richard","robert","peter","alan","simon","graham","kevin","brian","gary",
    "ian","martin","neil","stuart","jonathan","matthew","nicholas","philip",
    "timothy","raymond","kenneth","patrick","derek","roger","geoffrey","ronald",
    "harold","donald","albert","frank","ernest","walter","stanley","norman",
    "raymond","leonard","victor","clifford","reginald","gerald","douglas",
    "anthony","barry","terry","gordon","nigel","trevor","scott","wayne",
    "darren","dean","lee","jason","craig","steven","paul","sean","keith",
    "colin","barry","tony","dave","rob","pete","mike","nick","will","tom",
    # Top UK female names
    "olivia","amelia","isla","ava","mia","isabella","sophia","grace","lily",
    "freya","poppy","phoebe","daisy","charlotte","ella","emily","evie","ruby",
    "scarlett","alice","lucy","florence","lola","rose","millie","harriet",
    "ivy","sienna","eleanor","eliza","emma","maya","zoe","imogen","abigail",
    "ellie","sophie","jessica","bethany","molly","layla","amber","holly",
    "elsie","willow","violet","matilda","eva","bella","hannah","anna","grace",
    "eleanor","eve","faith","hope","summer","autumn","heather","janet","karen",
    "linda","barbara","patricia","margaret","elizabeth","helen","diane","susan",
    "carol","janet","ann","claire","sarah","deborah","amanda","sharon","donna",
    "tracey","teresa","jacqueline","kathleen","jean","june","maureen","irene",
    "valerie","sandra","pamela","sheila","wendy","gillian","lesley","denise",
    "beverley","nicola","joanne","paula","alison","victoria","samantha",
    "rebecca","rachel","gemma","emma","lisa","kerry","jade","stacey","hayley",
    "natalie","kelly","louise","amy","laura","michelle","jennifer","lisa",
    "maria","mary","anne","kate","katie","kate","katherine","catherine",
    "eleanor","diana","diana","ruth","joan","dorothy","edna","doris","vera",
    "ethel","gladys","ivy","florence","winifred","phyllis","constance","hilda",
    "mabel","beatrice","edith","gertrude","violet","maud","agnes","alice",
    "amy","annie","clara","daisy","dora","elsie","emma","eva","grace","helen",
    "ida","irene","jane","lilly","lily","louisa","mabel","maggie","maud",
    "minnie","nellie","nora","rose","ruby","sarah","violet","winnie",
}

# Common UK last names (for additional context matching)
UK_LAST_NAMES = {
    "smith","jones","williams","taylor","brown","davies","evans","wilson",
    "thomas","roberts","johnson","lewis","walker","robinson","wood","thompson",
    "white","watson","jackson","wright","green","harris","cooper","king",
    "lee","martin","clarke","james","morgan","hughes","edwards","hill",
    "moore","clark","harrison","scott","young","morris","hall","ward",
    "turner","campbell","mitchell","cook","carter","richardson","bailey",
    "collins","bell","shaw","murphy","miller","cox","rogers","kelly",
    "richardson","marshall","brooks","price","ward","gray","henderson",
    "james","stone","newman","o'brien","mason","fox","mcdonald","fisher",
    "patel","ali","khan","hussain","begum","ahmed","hassan","miah","rahman",
    "islam","chowdhury","ahmed","malik","kaur","singh","kumar","sharma",
    "rao","gupta","das","ghosh","nair","iyer","shah","mehta","verma",
    # Additional common UK surnames
    "simpson","pearson","butler","russell","barker","andrews","lawson",
    "hunt","cross","fletcher","harvey","stephens","griffin","foster",
    "hawkins","wade","atkinson","perkins","barlow","newman","powell",
    "bates","burns","knight","west","webb","ryan","bond","grant",
    "jennings","gilbert","woods","reid","murray","dixon","reid","barr",
    "bush","riley","obrien","norris","pearce","booth","stokes",
    "wilkins","farmer","yates","briggs","lawton","blake","wilkinson",
    "walters","gates","moran","holt","haynes","marsh","sutton","austin",
    "saunders","lloyd","berry","douglas","rowe","hamilton","gardner",
    "nicholson","knight","long","holt","higgins","newton","miles",
    "mccoy","mackenzie","mcbride","mcintyre","mckenzie","mclean",
    "mcdonald","macdonald","o'brien","o'connor","o'neill","o'sullivan",
    "galloway","nicholls","constantine","campbell","davies",
}

# Per-practice supplementary surnames (local staff/community names that boost
# detection). Loaded once at startup from data/extra_surnames.json — a JSON
# list of strings. Replaces the previous hard-coded practice-specific names.
def _load_extra_surnames() -> set[str]:
    import json, os
    path = str(__import__("pathlib").Path(__file__).resolve().parent.parent
               / "data" / "extra_surnames.json")
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return {str(n).strip().lower() for n in json.load(f) if str(n).strip()}
    except Exception:
        pass
    return set()

UK_LAST_NAMES |= _load_extra_surnames()

# Titles that reliably precede names
NAME_TITLES = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "professor",
    "rev", "reverend", "sir", "lord", "lady", "cllr", "councillor",
    "nurse", "sister", "brother", "fr", "father",
    "mx",  # gender-neutral title
}

# Suffixes that follow names (excluded from name capture)
NAME_SUFFIXES = {"jr", "sr", "jnr", "snr", "i", "ii", "iii", "iv"}

# Words that look capitalised but are not names
NOT_NAMES = {
    # Medical
    "nhs", "gp", "a&e", "gmc", "hiv", "aids", "copd", "uti", "ibs", "ms",
    "adhd", "autism", "asthma", "cancer", "diabetes", "ecg", "mri", "ct",
    "xray", "scan", "ward", "clinic", "surgery", "hospital", "trust",
    # Months
    "january","february","march","april","may","june","july","august",
    "september","october","november","december",
    "jan","feb","mar","apr","jun","jul","aug","sep","oct","nov","dec",
    # Days
    "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
    "mon","tue","wed","thu","fri","sat","sun",
    # Common non-name proper nouns
    "england","wales","scotland","uk","britain","london","manchester",
    "birmingham","leeds","liverpool","bristol","sheffield","nottingham",
    "leicester","coventry","bradford","belfast","edinburgh","glasgow",
    # Document terms
    "dear","sincerely","yours","regards","re","ref","subject","page",
    "date","time","tel","fax","email","please","thank","thanks",
    "yours","faithfully","sincerely","truly",
    # Section headers common in medical records
    "contacts","problems","active","past","history","examination","impression",
    "plan","procedure","comment","additional","document","attachment",
    "prescription","investigation","results","administration","consultation",
    "presenting","reason","linked","communication","note","record","filing",
    "performing","performer","requester","specimen","outbound","inbound",
    # UK street suffixes (prevent "Roke Lane" being a name)
    "lane","road","street","avenue","close","drive","place","court","way",
    "terrace","gardens","grove","crescent","mews","rise","walk","row",
    # Record header words (prevent "MEDICATION, Aspirin" style false positives
    # from the surname-comma pattern)
    "medication","medications","allergies","allergy","immunisation",
    "immunisations","vaccination","vaccinations","diagnosis","diagnoses",
    "pathology","radiology","haematology","biochemistry","microbiology",
    "screening","referral","referrals","appointment","appointments",
    "letter","letters","report","reports","telephone","urgent","routine",
    "normal","abnormal","review","summary","alert","alerts","template",
    "recall","smear","bloods","values","dob","nhs",
}

# Disease/anatomy words that follow eponyms — "Parkinson Disease",
# "Barrett Oesophagus", "Colles Fracture" are not people.
EPONYM_FOLLOWERS = {
    "disease","syndrome","oesophagus","esophagus","contracture","palsy",
    "fracture","tendon","sign","test","node","nodes","tube","tubes",
    "canal","ligament","manoeuvre","maneuver","triangle","membrane",
    "lymphoma","chorea","tremor",
}


# ─── Detection Patterns ───────────────────────────────────────────────────────

# A single name token: Title-Case, with optional Mc/Mac/O'/De internal-capital
# prefix so McDonald, MacKay, O'Brien, DeSouza all match.
_NAME = r"(?:Mc|Mac|O'|De|Van)?[A-Z][a-z'\-]+"

# Pattern 1: Title followed by optional initial and surname
# Matches: Dr Smith, Mr J. Smith, Mrs Jane Smith, Prof. Williams, Dr McDonald,
# and ALL-CAPS after a title (Dr SMITH) — a title anchor is strong evidence.
# NOTE: Use inline (?i:...) only for the title part so name parts stay case-sensitive.
TITLE_NAME_PATTERN = re.compile(
    r'\b'
    r'((?i:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?|Professor|Rev\.?|Reverend|'
    r'Sir|Lord|Lady|Nurse|Sister|Brother|Mx\.?))'
    r'[ \t]+'
    r'(?:[A-Z]\.?[ \t]+)?'                    # Optional initial
    rf"({_NAME}|[A-Z][A-Z'\-]+)"              # First name component (Title-Case or CAPS)
    rf"(?:[ \t]+({_NAME}|[A-Z][A-Z'\-]+))?"   # Optional second component (same line only)
    r'\b',
)

# Pattern 1b: "SURNAME, Forename" — the most common format in EMIS/SystmOne
# headers, Docman filing and hospital letters: "SMITH, John", "Re: JONES, Mary",
# "O'BRIEN, Siobhan". ALL-CAPS surname is required; a Title-Case word before a
# comma is too ambiguous ("However, John").
SURNAME_COMMA_PATTERN = re.compile(
    r"\b([A-Z][A-Z'\-]+(?:[ \t][A-Z][A-Z'\-]+)?),[ \t]+"   # CAPS surname(s) + comma
    rf"({_NAME}|[A-Z][A-Z'\-]+)"                            # Forename (Title-Case or CAPS)
    rf"(?:[ \t]({_NAME}|[A-Z]\.?))?"                        # Optional middle name/initial
    r'\b',
)

# Pattern 1c: Title-Case "Surname, Forename" — only accepted when the surname
# is a known UK surname, to avoid "However, John" style false positives.
TITLECASE_COMMA_PATTERN = re.compile(
    rf"\b({_NAME}),[ \t]+({_NAME})\b",
)

# Pattern 1d: ALL-CAPS full name "JOHN SMITH" — accepted only when at least
# one word is a known UK first/last name (filters "ACTIVE PROBLEMS" headers).
ALLCAPS_NAME_PATTERN = re.compile(
    r"\b([A-Z][A-Z'\-]{1,})[ \t]+([A-Z][A-Z'\-]{1,})\b",
)

# Pattern 2: "Dear [Title] [Name]" (letters)
DEAR_PATTERN = re.compile(
    rf"\bDear\s+(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?)?\s*({_NAME}(?:\s+{_NAME})?)\b"
)

# Pattern 3: Relational context — "patient's mother Sarah", "carer John"
# Captures Title-Cased word(s) following relation keywords.
# Use inline flag for the keyword part only; name part is case-sensitive.
RELATIONAL_PATTERN = re.compile(
    r'\b(?i:mother|father|son|daughter|sister|brother|wife|husband|partner|'
    r'carer|guardian|parent|grandparent|grandmother|grandfather|uncle|aunt|'
    r'nephew|niece|friend|neighbour|next\s+of\s+kin|nok)\s+'
    r'(?i:is\s+|was\s+|called\s+|named\s+)?'
    rf"({_NAME}(?:\s+{_NAME})?)\b",
)

# Pattern 4: "Name (Relationship)" — e.g. "Adam Simpson (Husband)"
# High confidence. Name must be at least two Title-Cased words on the same line.
NAME_WITH_RELATION_PATTERN = re.compile(
    rf"\b({_NAME}(?:[ \t]+{_NAME})+)[ \t]*\("
    r'(?i:Husband|Wife|Partner|Mother|Father|Son|Daughter|Brother|Sister|'
    r'Uncle|Aunt|Nephew|Niece|Grandson|Granddaughter|Grandparent|'
    r'Grandfather|Grandmother|Guardian|Carer|Friend|Neighbour|'
    r'Next\s+of\s+Kin|NOK|Ex-?Husband|Ex-?Wife|Ex-?Partner|Stepmother|'
    r'Stepfather|Stepson|Stepdaughter)'
    r'\)',
)

# Pattern 5: Full name patterns (two consecutive Title-Cased words on the same line,
# at least one of which is a known name) — lower confidence, used carefully.
# Uses [ \t]+ to avoid crossing newlines.
FULL_NAME_PATTERN = re.compile(
    r"\b((?:Mc|Mac|O'|De|Van)?[A-Z][a-z'\-]{2,})(?:[ \t]+[A-Z]\.?[ \t]+|[ \t]+)"
    r"((?:Mc|Mac|O'|De|Van)?[A-Z][a-z'\-]{2,})\b"
)


@dataclass
class NameMatch:
    text: str
    start: int
    end: int
    confidence: float
    reason: str


def _is_valid_name_word(word: str) -> bool:
    """Return True if word could plausibly be a name."""
    w = word.lower().rstrip('.,;:')
    if w in NOT_NAMES:
        return False
    if len(w) < 2:
        return False
    if w.isdigit():
        return False
    return True


def detect_names(text: str) -> list[NameMatch]:
    """
    Detect potential third-party names in text using rule-based patterns.
    Returns a list of NameMatch objects sorted by position.
    """
    matches: list[NameMatch] = []
    seen_spans: list[tuple[int, int]] = []

    def add_match(m: NameMatch):
        # Avoid duplicate overlapping spans
        for s, e in seen_spans:
            if m.start < e and m.end > s:
                return
        matches.append(m)
        seen_spans.append((m.start, m.end))

    # Pattern 1b: "SURNAME, Forename" — record headers, Docman, hospital letters.
    # Known forename → high confidence; unknown forename → flag for review.
    for match in SURNAME_COMMA_PATTERN.finditer(text):
        surname, forename = match.group(1), match.group(2)
        if not _is_valid_name_word(surname) or not _is_valid_name_word(forename):
            continue
        known = (forename.lower() in UK_FIRST_NAMES or
                 surname.lower() in UK_LAST_NAMES)
        add_match(NameMatch(
            text=match.group(0),
            start=match.start(),
            end=match.end(),
            confidence=0.90 if known else 0.72,
            reason="Surname-first record format (SURNAME, Forename)",
        ))

    # Pattern 1c: Title-Case "Surname, Forename" — requires a known surname
    for match in TITLECASE_COMMA_PATTERN.finditer(text):
        surname, forename = match.group(1), match.group(2)
        if surname.lower() not in UK_LAST_NAMES:
            continue
        if not _is_valid_name_word(surname) or not _is_valid_name_word(forename):
            continue
        add_match(NameMatch(
            text=match.group(0),
            start=match.start(),
            end=match.end(),
            confidence=0.72,
            reason="Surname-first format (known UK surname)",
        ))

    # Pattern 1: Title + Name (highest confidence)
    for match in TITLE_NAME_PATTERN.finditer(text):
        full = match.group(0).strip()
        # Build the name part (excluding the title)
        title = match.group(1)
        surname = match.group(2)
        extra = match.group(3)

        name_text = surname
        if extra:
            name_text = f"{surname} {extra}"
        full_text = f"{title} {name_text}"

        if not _is_valid_name_word(surname):
            continue

        add_match(NameMatch(
            text=full_text,
            start=match.start(),
            end=match.end(),
            confidence=0.90,
            reason=f"Name with title ({title})",
        ))

    # Pattern 2: Dear [Name]
    for match in DEAR_PATTERN.finditer(text):
        name_text = match.group(1).strip()
        if not _is_valid_name_word(name_text.split()[0]):
            continue
        add_match(NameMatch(
            text=name_text,
            start=match.start(1),
            end=match.end(1),
            confidence=0.85,
            reason="Name in salutation (Dear...)",
        ))

    # Pattern 3: Relational context
    for match in RELATIONAL_PATTERN.finditer(text):
        name_text = match.group(1).strip()
        if not _is_valid_name_word(name_text.split()[0]):
            continue
        add_match(NameMatch(
            text=name_text,
            start=match.start(1),
            end=match.end(1),
            confidence=0.80,
            reason="Name in relational context",
        ))

    # Pattern 4: "Name (Relationship)" — "Adam Simpson (Husband)" — high confidence
    for match in NAME_WITH_RELATION_PATTERN.finditer(text):
        name_text = match.group(1).strip()
        words = name_text.split()
        if not all(_is_valid_name_word(w) for w in words):
            continue

        already_covered = any(
            match.start(1) >= s and match.end(1) <= e
            for s, e in seen_spans
        )
        if already_covered:
            continue

        add_match(NameMatch(
            text=name_text,
            start=match.start(1),
            end=match.end(1),
            confidence=0.92,
            reason="Name with relational bracket (e.g. Husband, Carer)",
        ))

    # Pattern 5: Two capitalised words (same line) where at least one is a known UK name
    # (medium confidence — catches "Jane Doe" style names without a title)
    for match in FULL_NAME_PATTERN.finditer(text):
        word1 = match.group(1).lower()
        word2 = match.group(2).lower()
        full_text = match.group(0)

        # Skip if already covered by a higher-confidence pattern
        already_covered = any(
            match.start() >= s and match.end() <= e
            for s, e in seen_spans
        )
        if already_covered:
            continue

        # Medical eponyms are not people: "Parkinson Disease", "Colles Fracture"
        if word2 in EPONYM_FOLLOWERS:
            continue

        # At least one word must be a known UK first or last name
        is_name = (
            word1 in UK_FIRST_NAMES or word1 in UK_LAST_NAMES or
            word2 in UK_FIRST_NAMES or word2 in UK_LAST_NAMES
        )
        if not is_name:
            continue

        if not _is_valid_name_word(match.group(1)) or not _is_valid_name_word(match.group(2)):
            continue

        add_match(NameMatch(
            text=full_text,
            start=match.start(),
            end=match.end(),
            confidence=0.65,
            reason="Full name (capitalised words, known name)",
        ))

    # Pattern 6: ALL-CAPS full name "JOHN SMITH" — needs a known UK name to
    # avoid section headers ("ACTIVE PROBLEMS", "BLOOD PRESSURE")
    for match in ALLCAPS_NAME_PATTERN.finditer(text):
        word1 = match.group(1).lower()
        word2 = match.group(2).lower()

        already_covered = any(
            match.start() < e and match.end() > s
            for s, e in seen_spans
        )
        if already_covered:
            continue
        if word2 in EPONYM_FOLLOWERS:
            continue
        if not (word1 in UK_FIRST_NAMES or word1 in UK_LAST_NAMES or
                word2 in UK_FIRST_NAMES or word2 in UK_LAST_NAMES):
            continue
        if not _is_valid_name_word(match.group(1)) or not _is_valid_name_word(match.group(2)):
            continue

        add_match(NameMatch(
            text=match.group(0),
            start=match.start(),
            end=match.end(),
            confidence=0.70,
            reason="ALL-CAPS full name (known UK name)",
        ))

    return sorted(matches, key=lambda m: m.start)
