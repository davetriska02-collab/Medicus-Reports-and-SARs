"""Template management for medical reports. Built-in + custom templates."""
import json
import os

TEMPLATES_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "report_templates.json")


def _builtin_templates() -> list[dict]:
    """Pre-loaded report templates shipped with the app."""
    return [
        {
            "id": "tpl_insurance",
            "name": "Insurance Medical Report",
            "category": "insurance",
            "description": "Standard medical report for life/health insurance applications",
            "is_builtin": True,
            "questions": [
                {"id": "ins_q1", "text": "Does the patient have any current medical conditions or diagnoses?",
                 "question_type": "yes_no",
                 "keywords": ["diagnosis", "condition", "problem list", "active problems", "current conditions"],
                 "section_hints": ["active problems", "problem list", "diagnoses"], "order": 1},
                {"id": "ins_q2", "text": "Please list all current medications and dosages.",
                 "question_type": "free_text",
                 "keywords": ["medication", "prescription", "drug", "dose", "dosage", "repeat prescription"],
                 "section_hints": ["medications", "current medication", "repeat prescriptions"], "order": 2},
                {"id": "ins_q3", "text": "Has the patient been referred to or attended hospital in the last 5 years?",
                 "question_type": "yes_no",
                 "keywords": ["referral", "hospital", "admission", "outpatient", "A&E", "emergency", "discharge"],
                 "section_hints": ["referrals", "hospital letters"], "order": 3},
                {"id": "ins_q4", "text": "Does the patient have any history of mental health conditions?",
                 "question_type": "yes_no",
                 "keywords": ["mental health", "anxiety", "depression", "psychiatry", "CMHT", "counselling", "CBT"],
                 "section_hints": ["mental health", "psychiatric"], "order": 4},
                {"id": "ins_q5", "text": "Has the patient had any surgical procedures?",
                 "question_type": "yes_no",
                 "keywords": ["surgery", "operation", "procedure", "surgical", "anaesthetic"],
                 "section_hints": ["surgical history", "operations"], "order": 5},
                {"id": "ins_q6", "text": "Does the patient have a family history of significant medical conditions?",
                 "question_type": "free_text",
                 "keywords": ["family history", "hereditary", "genetic", "father", "mother", "sibling"],
                 "section_hints": ["family history"], "order": 6},
                {"id": "ins_q7", "text": "What is the patient's smoking and alcohol status?",
                 "question_type": "free_text",
                 "keywords": ["smoking", "tobacco", "alcohol", "units", "smoker", "non-smoker", "ex-smoker", "drinking"],
                 "section_hints": ["lifestyle", "smoking status", "alcohol"], "order": 7},
                {"id": "ins_q8", "text": "Are there any ongoing investigations or pending results?",
                 "question_type": "yes_no",
                 "keywords": ["investigation", "pending", "blood test", "scan", "MRI", "CT", "X-ray", "ultrasound", "biopsy"],
                 "section_hints": ["investigations", "results"], "order": 8},
                {"id": "ins_q9", "text": "Has the patient's BMI been recorded? If so, what is the latest value?",
                 "question_type": "free_text",
                 "keywords": ["BMI", "body mass index", "weight", "height", "obesity", "overweight"],
                 "section_hints": ["measurements", "observations"], "order": 9},
                {"id": "ins_q10", "text": "What is the patient's latest recorded blood pressure?",
                 "question_type": "free_text",
                 "keywords": ["blood pressure", "BP", "systolic", "diastolic", "hypertension", "mmHg"],
                 "section_hints": ["observations", "vital signs"], "order": 10},
            ],
        },
        {
            "id": "tpl_uc_fitness",
            "name": "Universal Credit Fitness Assessment",
            "category": "benefits",
            "description": "Medical assessment for UC capability for work / limited capability for work",
            "is_builtin": True,
            "questions": [
                {"id": "uc_q1", "text": "What is the patient's primary diagnosis or condition affecting their ability to work?",
                 "question_type": "free_text",
                 "keywords": ["diagnosis", "condition", "disability", "impairment", "chronic"],
                 "section_hints": ["active problems", "problem list"], "order": 1},
                {"id": "uc_q2", "text": "What treatment is the patient currently receiving?",
                 "question_type": "free_text",
                 "keywords": ["treatment", "therapy", "medication", "physiotherapy", "rehabilitation"],
                 "section_hints": ["current treatment", "management plan"], "order": 2},
                {"id": "uc_q3", "text": "What functional limitations does the patient experience in daily activities?",
                 "question_type": "free_text",
                 "keywords": ["mobility", "walking", "standing", "sitting", "lifting", "concentration", "fatigue", "pain"],
                 "section_hints": ["functional assessment", "daily activities"], "order": 3},
                {"id": "uc_q4", "text": "Is the patient's condition likely to improve, remain stable, or deteriorate?",
                 "question_type": "multiple_choice",
                 "options": ["Likely to improve", "Likely to remain stable", "Likely to deteriorate", "Uncertain"],
                 "keywords": ["prognosis", "outlook", "expected", "deterioration", "improvement", "progressive"],
                 "section_hints": ["prognosis"], "order": 4},
                {"id": "uc_q5", "text": "How long has the patient been affected by this condition?",
                 "question_type": "free_text",
                 "keywords": ["onset", "duration", "since", "diagnosed", "first presented"],
                 "section_hints": ["history"], "order": 5},
                {"id": "uc_q6", "text": "Has the patient been referred to any specialist services?",
                 "question_type": "yes_no",
                 "keywords": ["referral", "specialist", "consultant", "outpatient", "clinic"],
                 "section_hints": ["referrals"], "order": 6},
                {"id": "uc_q7", "text": "Does the patient have any mental health conditions that affect their capability for work?",
                 "question_type": "yes_no",
                 "keywords": ["mental health", "anxiety", "depression", "PTSD", "psychosis", "OCD", "bipolar"],
                 "section_hints": ["mental health"], "order": 7},
                {"id": "uc_q8", "text": "Are there any adaptations or support that might enable the patient to work?",
                 "question_type": "free_text",
                 "keywords": ["adaptation", "support", "reasonable adjustment", "occupational health", "phased return"],
                 "section_hints": ["recommendations"], "order": 8},
            ],
        },
        {
            "id": "tpl_military",
            "name": "Army Medical Report",
            "category": "military",
            "description": "Medical report for military recruitment, fitness assessment, or service records",
            "is_builtin": True,
            "questions": [
                {"id": "mil_q1", "text": "Does the patient have any history of mental health conditions (anxiety, depression, self-harm, eating disorders)?",
                 "question_type": "yes_no",
                 "keywords": ["mental health", "anxiety", "depression", "self-harm", "eating disorder", "psychiatry", "CAMHS", "counselling"],
                 "section_hints": ["mental health", "psychiatric history"], "order": 1},
                {"id": "mil_q2", "text": "Does the patient have any musculoskeletal conditions or history of fractures/joint problems?",
                 "question_type": "yes_no",
                 "keywords": ["fracture", "joint", "knee", "back", "spine", "musculoskeletal", "ligament", "tendon", "dislocation"],
                 "section_hints": ["musculoskeletal", "orthopaedic"], "order": 2},
                {"id": "mil_q3", "text": "Does the patient have any respiratory conditions (asthma, COPD)?",
                 "question_type": "yes_no",
                 "keywords": ["asthma", "inhaler", "COPD", "respiratory", "wheeze", "breathlessness", "peak flow"],
                 "section_hints": ["respiratory"], "order": 3},
                {"id": "mil_q4", "text": "Does the patient have any cardiovascular conditions or abnormal ECGs?",
                 "question_type": "yes_no",
                 "keywords": ["heart", "cardiac", "ECG", "murmur", "palpitations", "chest pain", "hypertension"],
                 "section_hints": ["cardiovascular", "cardiac"], "order": 4},
                {"id": "mil_q5", "text": "Does the patient have any history of seizures or epilepsy?",
                 "question_type": "yes_no",
                 "keywords": ["seizure", "epilepsy", "fit", "convulsion", "blackout", "loss of consciousness"],
                 "section_hints": ["neurological"], "order": 5},
                {"id": "mil_q6", "text": "What is the patient's current medication list?",
                 "question_type": "free_text",
                 "keywords": ["medication", "prescription", "drug", "dose", "repeat"],
                 "section_hints": ["medications", "repeat prescriptions"], "order": 6},
                {"id": "mil_q7", "text": "Does the patient have any skin conditions (eczema, psoriasis)?",
                 "question_type": "yes_no",
                 "keywords": ["eczema", "psoriasis", "dermatitis", "skin", "rash"],
                 "section_hints": ["dermatology", "skin"], "order": 7},
                {"id": "mil_q8", "text": "Does the patient have any visual or hearing impairments?",
                 "question_type": "yes_no",
                 "keywords": ["vision", "sight", "hearing", "deaf", "glasses", "contact lenses", "audiogram"],
                 "section_hints": ["ophthalmology", "audiology", "ENT"], "order": 8},
                {"id": "mil_q9", "text": "Has the patient had any surgical operations?",
                 "question_type": "yes_no",
                 "keywords": ["surgery", "operation", "procedure", "surgical", "appendectomy", "tonsillectomy"],
                 "section_hints": ["surgical history", "operations"], "order": 9},
                {"id": "mil_q10", "text": "Does the patient have any drug or alcohol history?",
                 "question_type": "yes_no",
                 "keywords": ["drug", "substance", "cannabis", "cocaine", "alcohol", "misuse", "addiction"],
                 "section_hints": ["substance misuse", "alcohol"], "order": 10},
            ],
        },
        {
            "id": "tpl_safeguarding",
            "name": "Safeguarding / MASH Response",
            "category": "safeguarding",
            "description": "Medical information for safeguarding enquiries and Multi-Agency Safeguarding Hub (MASH) requests",
            "is_builtin": True,
            "questions": [
                {"id": "sg_q1", "text": "Is the patient known to the practice? How long have they been registered?",
                 "question_type": "free_text",
                 "keywords": ["registered", "registration", "new patient", "temporary"],
                 "section_hints": ["registration"], "order": 1},
                {"id": "sg_q2", "text": "Does the patient have any known vulnerabilities or safeguarding concerns on record?",
                 "question_type": "yes_no",
                 "keywords": ["safeguarding", "vulnerable", "concern", "at risk", "MARAC", "child protection", "CP plan"],
                 "section_hints": ["safeguarding", "alerts"], "order": 2},
                {"id": "sg_q3", "text": "Are there any mental health diagnoses or concerns?",
                 "question_type": "free_text",
                 "keywords": ["mental health", "anxiety", "depression", "psychosis", "self-harm", "suicidal", "crisis", "sectioned"],
                 "section_hints": ["mental health"], "order": 3},
                {"id": "sg_q4", "text": "Is there any history of substance or alcohol misuse?",
                 "question_type": "yes_no",
                 "keywords": ["substance", "drug", "alcohol", "misuse", "addiction", "dependency", "methadone", "detox"],
                 "section_hints": ["substance misuse", "alcohol"], "order": 4},
                {"id": "sg_q5", "text": "Are there any indicators of domestic abuse or coercive control?",
                 "question_type": "yes_no",
                 "keywords": ["domestic", "abuse", "violence", "coercive", "control", "assault", "injury", "DV", "DASH"],
                 "section_hints": ["domestic abuse", "safeguarding"], "order": 5},
                {"id": "sg_q6", "text": "Has the patient presented with any unexplained injuries or frequent attendances?",
                 "question_type": "yes_no",
                 "keywords": ["injury", "bruise", "fracture", "burn", "unexplained", "frequent", "attendance", "A&E"],
                 "section_hints": ["presentations", "attendances"], "order": 6},
                {"id": "sg_q7", "text": "Are there children in the household? Any concerns about child welfare?",
                 "question_type": "free_text",
                 "keywords": ["child", "children", "minor", "dependant", "welfare", "neglect", "FGM", "CSE"],
                 "section_hints": ["family", "dependants", "child protection"], "order": 7},
                {"id": "sg_q8", "text": "What is the patient's current medication and are they compliant?",
                 "question_type": "free_text",
                 "keywords": ["medication", "prescription", "compliance", "non-compliance", "adherence", "missed appointment", "DNA"],
                 "section_hints": ["medications", "compliance"], "order": 8},
                {"id": "sg_q9", "text": "Has the patient been referred to or is known to any support services?",
                 "question_type": "free_text",
                 "keywords": ["social services", "CAMHS", "health visitor", "social worker", "refuge", "support", "CPN", "CMHT"],
                 "section_hints": ["referrals", "agencies"], "order": 9},
                {"id": "sg_q10", "text": "Are there any other risk factors or relevant information?",
                 "question_type": "free_text",
                 "keywords": ["risk", "concern", "trafficking", "exploitation", "isolation", "homelessness", "county lines"],
                 "section_hints": ["risk factors"], "order": 10},
            ],
        },
    ]


def get_all_templates() -> list[dict]:
    """Load all templates (builtins + custom)."""
    templates = _builtin_templates()
    if os.path.exists(TEMPLATES_PATH):
        with open(TEMPLATES_PATH) as f:
            custom = json.load(f)
        templates.extend(custom)
    return templates


def get_template(template_id: str) -> dict | None:
    for t in get_all_templates():
        if t["id"] == template_id:
            return t
    return None


def save_custom_template(template: dict) -> None:
    custom = []
    if os.path.exists(TEMPLATES_PATH):
        with open(TEMPLATES_PATH) as f:
            custom = json.load(f)
    custom.append(template)
    with open(TEMPLATES_PATH, "w") as f:
        json.dump(custom, f, indent=2)


def update_custom_template(template_id: str, updates: dict) -> bool:
    if not os.path.exists(TEMPLATES_PATH):
        return False
    with open(TEMPLATES_PATH) as f:
        custom = json.load(f)
    for t in custom:
        if t["id"] == template_id:
            t.update(updates)
            with open(TEMPLATES_PATH, "w") as f:
                json.dump(custom, f, indent=2)
            return True
    return False


def delete_custom_template(template_id: str) -> bool:
    if not os.path.exists(TEMPLATES_PATH):
        return False
    with open(TEMPLATES_PATH) as f:
        custom = json.load(f)
    before = len(custom)
    custom = [t for t in custom if t["id"] != template_id]
    if len(custom) == before:
        return False
    with open(TEMPLATES_PATH, "w") as f:
        json.dump(custom, f, indent=2)
    return True
