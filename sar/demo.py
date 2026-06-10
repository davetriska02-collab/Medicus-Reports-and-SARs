"""Demo mode — creates a synthetic patient SAR for evaluator walkthroughs.

The generated record contains realistic-looking PII of several kinds so
reviewers see varied detection candidates immediately on first run, without
needing to supply real patient data.

Usage (internal — called by the /api/demo-sar route)::

    from sar.demo import create_demo_sar
    sar_id = create_demo_sar(upload_dir, set_fn, save_fn)
"""
import os
import random

import fitz  # PyMuPDF

from sar.models import (SARRequest, SubjectDetails, DetectionSettings)
from sar.pdf_parser import extract_text_spans
from sar.detector import detect_pii
from sar.date_extractor import extract_document_date, extract_date_from_filename


# ── Utility generators (inlined from tools/benchmark_detection.py) ──────────

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


# ── NHS-11-valid demo number: 943 476 0001 (passes Modulus-11) ──────────────
# We use a fixed but valid NHS number so it is always detected as nhs_number.
_DEMO_NHS = "943 476 0001"

# ── Fixed RNG so the record is deterministic ─────────────────────────────────
_RNG = random.Random(20240101)

# ── Synthetic subject details ────────────────────────────────────────────────
_SUBJECT = SubjectDetails(
    full_name="DEMO PATIENT — SYNTHETIC DATA",
    first_name="Demo",
    last_name="Patient",
    nhs_number=_DEMO_NHS,
    date_of_birth="1970-01-01",
    address="1 Imaginary Lane, Testbury, TS1 1AA",
    phone="07700 900000",
    email="demopatient@example.com",
    aliases=[],
)

# ── Helper: NHS-11-valid number reusing benchmark generator ──────────────────

def _nhs():
    return random_nhs_number(_RNG)

def _postcode():
    return random_postcode(_RNG)

def _phone():
    return random_phone(_RNG)


# ── Build a 4-page synthetic GP record as a fitz document ───────────────────

def _build_demo_pdf() -> fitz.Document:
    doc = fitz.open()
    _page1(doc)
    _page2(doc)
    _page3(doc)
    _page4(doc)
    return doc


def _insert(page, y, text, fontsize=10):
    """Insert a line of text at y coordinate; returns next y."""
    page.insert_text(fitz.Point(50, y), text, fontsize=fontsize, fontname="helv")
    return y + fontsize + 3


def _page1(doc):
    """Patient summary + registration."""
    pg = doc.new_page()
    y = 50
    y = _insert(pg, y, "PATIENT SUMMARY RECORD", fontsize=13)
    y += 4
    y = _insert(pg, y, f"Patient: DEMO PATIENT — SYNTHETIC DATA")
    y = _insert(pg, y, f"NHS Number: {_DEMO_NHS}")
    y = _insert(pg, y, f"Date of Birth: 01/01/1970")
    y = _insert(pg, y, f"Address: 1 Imaginary Lane, Testbury, TS1 1AA")
    y = _insert(pg, y, f"Phone: 07700 900000")
    y = _insert(pg, y, f"Email: demopatient@nhs.net")
    y += 8
    y = _insert(pg, y, "CURRENT PROBLEMS")
    y = _insert(pg, y, "Hypertension — reviewed 12 Mar 2024")
    y = _insert(pg, y, "Type 2 Diabetes Mellitus — ongoing")
    y = _insert(pg, y, "Ischaemic Heart Disease — stable")
    y += 8
    y = _insert(pg, y, "CURRENT MEDICATION")
    y = _insert(pg, y, "Ramipril 10mg once daily")
    y = _insert(pg, y, "Metformin 500mg twice daily")
    y = _insert(pg, y, "Aspirin 75mg once daily")
    y += 8
    y = _insert(pg, y, "ALLERGIES")
    y = _insert(pg, y, "Penicillin — anaphylaxis (documented 2003)")


def _page2(doc):
    """Consultation notes with third-party names."""
    pg = doc.new_page()
    y = 50
    y = _insert(pg, y, "CONSULTATION NOTES", fontsize=13)
    y += 4
    nhs2 = _nhs()
    y = _insert(pg, y, f"21 Mar 2024 — Annual review")
    y = _insert(pg, y, f"Seen with daughter Mrs HARGREAVES, Susan who attended with patient.")
    y = _insert(pg, y, f"BP 138/86, weight 84kg. Discussed lifestyle changes.")
    y = _insert(pg, y, f"Third party NHS number quoted: {nhs2}")
    y += 4
    y = _insert(pg, y, f"14 Feb 2024 — Urgent appointment")
    y = _insert(pg, y, f"Patient attended with carer. Neighbour Patel, Raj raised concerns.")
    phone2 = _phone()
    y = _insert(pg, y, f"Contact number given: {phone2}")
    y += 4
    y = _insert(pg, y, f"05 Jan 2024 — Telephone consultation")
    y = _insert(pg, y, f"Letter received from Dr WHITFIELD at the hospital.")
    y = _insert(pg, y, f"Re: JOHNSON, Emily — safeguarding review requested.")
    y = _insert(pg, y, f"Next of kin: MICHAEL HARGREAVES (husband)")
    y += 4
    postcode2 = _postcode()
    y = _insert(pg, y, f"Previous address postcode {postcode2} on file.")
    y = _insert(pg, y, f"Recorded by: Dr Sarah Owen  |  Practice: Testbury Surgery")


def _page3(doc):
    """Correspondence — letter from specialist."""
    pg = doc.new_page()
    y = 50
    y = _insert(pg, y, "HOSPITAL CORRESPONDENCE", fontsize=13)
    y += 4
    nhs3 = _nhs()
    phone3 = _phone()
    postcode3 = _postcode()
    y = _insert(pg, y, f"Cardiology Outpatient Letter — 03 Feb 2024")
    y = _insert(pg, y, f"Patient: DEMO PATIENT — SYNTHETIC DATA  DOB: 01/01/1970")
    y = _insert(pg, y, f"NHS No: {nhs3}  (third-party letter reference)")
    y = _insert(pg, y, f"Address: 1 Imaginary Lane, Testbury, TS1 1AA")
    y += 4
    y = _insert(pg, y, f"Dear Dr Owen,")
    y = _insert(pg, y, f"Thank you for referring this patient. I reviewed them on 03 Feb 2024.")
    y = _insert(pg, y, f"Their son HARGREAVES, Daniel was also present during the consultation.")
    y = _insert(pg, y, f"We have arranged a follow-up stress echocardiogram.")
    y += 4
    y = _insert(pg, y, f"Clinic contact: {phone3}")
    y = _insert(pg, y, f"Clinic address postcode: {postcode3}")
    y = _insert(pg, y, f"From: Consultant Cardiologist Dr OKONKWO, Adaeze")
    y = _insert(pg, y, f"cc: HARGREAVES, Susan (daughter, health proxy)")
    y = _insert(pg, y, f"Email: adaeze.okonkwo@nhs.net")


def _page4(doc):
    """Social care note — additional third-party names + contact."""
    pg = doc.new_page()
    y = 50
    y = _insert(pg, y, "SOCIAL CARE LIAISON", fontsize=13)
    y += 4
    phone4 = _phone()
    postcode4 = _postcode()
    y = _insert(pg, y, f"Social care referral — 10 Jan 2024")
    y = _insert(pg, y, f"Referral from social worker: FLETCHER, Amanda (BANES Social Care)")
    y = _insert(pg, y, f"Contact: {phone4}  Email: amanda.fletcher@nhs.net")
    y = _insert(pg, y, f"Concern raised by neighbour — name: Patel, Raj")
    y += 4
    y = _insert(pg, y, f"Home visit completed. Patient at address TS1 1AA.")
    y = _insert(pg, y, f"Family present: HARGREAVES, Susan and HARGREAVES, Michael.")
    y = _insert(pg, y, f"Previous carer address postcode: {postcode4}")
    y += 4
    y = _insert(pg, y, f"** NOTE — SYNTHETIC DATA FOR DEMONSTRATION PURPOSES ONLY **")
    y = _insert(pg, y, f"** All names, NHS numbers, addresses and phone numbers are **")
    y = _insert(pg, y, f"** entirely fictional and do not relate to any real person. **")
    y = _insert(pg, y, f"** This record may be deleted from the dashboard at any time.**")


# ── Public API ───────────────────────────────────────────────────────────────

def create_demo_sar(upload_dir: str, set_fn, save_fn) -> str:
    """Build a demo SAR and register it.

    Parameters
    ----------
    upload_dir:
        Same ``UPLOAD_DIR`` used by the main app (``uploads/``).
    set_fn:
        ``app._set`` — registers the SAR in the in-memory store.
    save_fn:
        ``app._save`` — persists it to the SQLite store.

    Returns
    -------
    str
        The id of the newly created (or previously existing) SAR.
    """
    sar = SARRequest(subject=_SUBJECT)
    sar.archived = False
    sar.request_date = "2026-06-10"
    sar.scope_notes = (
        "GENERATED DEMO RECORD — synthetic data only. "
        "No real patient information. May be deleted from the dashboard at any time."
    )
    sar.notes = (
        "This is a demonstration SAR created by the 'Try a demo SAR' button. "
        "It contains entirely synthetic data and can be deleted like any other SAR."
    )
    sar.compute_due_date()

    sd = os.path.join(upload_dir, sar.id)
    os.makedirs(sd, exist_ok=True)

    pdf_path = os.path.join(sd, "demo_record.pdf")
    doc = _build_demo_pdf()
    doc.save(pdf_path)
    doc.close()

    sar.pdf_files = [pdf_path]
    sar.file_order = ["demo_record.pdf"]
    sar.main_record_file = "demo_record.pdf"
    sar.document_dates = {"demo_record.pdf": "2024-03-21"}

    # Run detection synchronously — the file is small (4 pages).
    spans = extract_text_spans(pdf_path)
    candidates, unscreened = detect_pii(
        pdf_path, spans, _SUBJECT, "demo_record.pdf",
        settings=DetectionSettings()
    )
    sar.candidates = candidates
    sar.unscreened_pages = unscreened
    sar.status = "reviewing"

    set_fn(sar.id, sar)
    save_fn(sar)
    return sar.id
