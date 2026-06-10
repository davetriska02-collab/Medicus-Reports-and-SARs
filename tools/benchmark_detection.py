"""Detection benchmark — synthetic GP-record corpus, no real patient data.

Generates clinical-note-style text with planted PII in realistic formats,
runs the detectors, and reports precision/recall per category.

Usage:  python tools/benchmark_detection.py [--docs 200] [--seed 42]

The numbers this prints are the product's accuracy claims — run it after any
change to sar/name_detector.py, sar/detector.py or sar/nhs_patterns.py.
"""
import argparse
import random
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sar.name_detector import detect_names, UK_FIRST_NAMES, UK_LAST_NAMES
from sar.nhs_patterns import find_regex_matches, validate_nhs_number
from sar.models import PIICategory

FIRST = sorted(UK_FIRST_NAMES)
LAST = sorted(UK_LAST_NAMES)

# Sentence templates planting a third-party name. {f}=forename {s}=surname.
# Second element says what a correct detector must minimally find:
# "both" = forename+surname, "sur" = surname, "fore" = forename.
NAME_TEMPLATES = [
    ("Discussed with daughter {f} {s} who attended with patient.", "both"),
    ("Letter received from Dr {s} at the hospital.", "sur"),
    ("Seen with wife Mrs {s} today.", "sur"),
    ("Re: {S}, {f} - safeguarding review", "both"),
    ("Next of kin: {F} {S}", "both"),
    ("{f} {s} (Husband) reports symptoms worsening.", "both"),
    ("Dear Mr {s}, thank you for your letter.", "sur"),
    ("Neighbour {f} {s} raised concerns about the patient.", "both"),
    ("Contacted carer {f} regarding medication.", "fore"),
    ("cc: {s}, {f} (social worker)", "both"),
]

# Distractor sentences with NO third-party PII (clinical noise)
DISTRACTORS = [
    "ACTIVE PROBLEMS reviewed and updated.",
    "Blood Pressure 128/82 recorded at clinic.",
    "Diagnosis of Parkinson Disease confirmed by neurology.",
    "Barrett Oesophagus surveillance endoscopy due.",
    "MEDICATION, Aspirin 75mg od continued.",
    "Patient reports feeling much better this week.",
    "Repeat Prescription issued for two months.",
    "Chest examination normal, no wheeze heard.",
    "Routine bloods requested including HbA1c.",
    "Colles Fracture noted on previous imaging.",
    "Advised regular exercise and weight management.",
    "PAST HISTORY includes appendicectomy in childhood.",
]


def random_nhs_number(rng):
    while True:
        digits = [rng.randint(0, 9) for _ in range(9)]
        total = sum(d * (10 - i) for i, d in enumerate(digits))
        check = 11 - (total % 11)
        if check == 11:
            check = 0
        if check == 10:
            continue
        s = "".join(map(str, digits)) + str(check)
        return f"{s[:3]} {s[3:6]} {s[6:]}"


def random_postcode(rng):
    L = "ABCDEFGHJKLMNPRSTUWYZ"
    return (rng.choice(L) + rng.choice(L) + str(rng.randint(1, 9)) + " " +
            str(rng.randint(1, 9)) + rng.choice(L) + rng.choice(L))


def random_phone(rng):
    return rng.choice([
        f"07{rng.randint(100,999)} {rng.randint(100000,999999)}",
        f"01{rng.randint(200,999)} {rng.randint(100000,999999)}",
    ])


def build_doc(rng):
    """Returns (text, planted) where planted maps category → list of strings."""
    planted = {"name": [], "nhs": [], "postcode": [], "phone": []}
    lines = []
    for _ in range(rng.randint(8, 14)):
        roll = rng.random()
        if roll < 0.40:
            f, s = rng.choice(FIRST).title(), rng.choice(LAST).title()
            tpl, expect = rng.choice(NAME_TEMPLATES)
            lines.append(tpl.format(f=f, s=s, F=f.upper(), S=s.upper()))
            planted["name"].append((f, s, expect))
        elif roll < 0.50:
            n = random_nhs_number(rng)
            lines.append(f"Third party NHS number quoted: {n}")
            planted["nhs"].append(n)
        elif roll < 0.58:
            p = random_postcode(rng)
            lines.append(f"Previous address postcode {p} on file.")
            planted["postcode"].append(p)
        elif roll < 0.66:
            t = random_phone(rng)
            lines.append(f"Contact number given: {t}")
            planted["phone"].append(t)
        else:
            lines.append(rng.choice(DISTRACTORS))
    return "\n".join(lines), planted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    stats = {k: {"tp": 0, "fn": 0, "fp": 0} for k in
             ("name", "nhs", "postcode", "phone")}

    for _ in range(args.docs):
        text, planted = build_doc(rng)

        # Names
        found = detect_names(text)
        found_norm = [m.text.lower() for m in found]
        for f, s, expect in planted["name"]:
            fl, sl = f.lower(), s.lower()
            if expect == "both":
                hit = any(fl in t and sl in t for t in found_norm)
            elif expect == "sur":
                hit = any(sl in t for t in found_norm)
            else:  # fore
                hit = any(fl in t for t in found_norm)
            stats["name"]["tp" if hit else "fn"] += 1
        # Name false positives: detections containing no planted token
        planted_tokens = {w.lower() for f, s, _ in planted["name"] for w in (f, s)}
        for t in found_norm:
            words = set(t.replace(",", " ").split())
            # titles don't count as content
            words -= {"dr", "mr", "mrs", "ms", "miss", "dear"}
            if words and not (words & planted_tokens):
                stats["name"]["fp"] += 1

        # Regex categories
        rmatches = find_regex_matches(text, 0)
        by_cat = {}
        for m in rmatches:
            by_cat.setdefault(m["category"], []).append(m["text"])
        catmap = {"nhs": PIICategory.NHS_NUMBER, "postcode": PIICategory.POSTCODE,
                  "phone": PIICategory.PHONE_NUMBER}
        for key, cat in catmap.items():
            found_texts = by_cat.get(cat, [])
            for item in planted[key]:
                hit = any(item.replace(" ", "") == ft.replace(" ", "").replace("-", "")
                          or item == ft for ft in found_texts)
                stats[key]["tp" if hit else "fn"] += 1

    print(f"\nDetection benchmark — {args.docs} synthetic documents (seed {args.seed})")
    print(f"{'Category':<12} {'Recall':>8} {'Precision*':>11}   (tp/fn/fp)")
    print("-" * 48)
    for key, s in stats.items():
        total = s["tp"] + s["fn"]
        recall = s["tp"] / total if total else 0
        denom = s["tp"] + s["fp"]
        precision = s["tp"] / denom if denom else 1.0
        prec_str = f"{precision:.1%}" if key == "name" else "—"
        print(f"{key:<12} {recall:>8.1%} {prec_str:>11}   ({s['tp']}/{s['fn']}/{s['fp']})")
    print("\n* precision measured for names only; regex categories are pattern-")
    print("  validated (NHS numbers Modulus-11 checked) so FPs are rare by design.")


if __name__ == "__main__":
    main()
