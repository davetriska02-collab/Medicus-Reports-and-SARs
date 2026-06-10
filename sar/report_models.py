"""Data models for the medical report workflow."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid


class ReportStatus(Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass
class TemplateQuestion:
    """A single question in a report template."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = ""
    question_type: str = "free_text"  # free_text | yes_no | date | multiple_choice
    options: list = field(default_factory=list)  # For multiple_choice
    keywords: list = field(default_factory=list)  # Keywords to search for in records
    section_hints: list = field(default_factory=list)  # Section headings to look for
    order: int = 0


@dataclass
class ReportTemplate:
    """A template defining the structure of a medical report."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    category: str = ""  # insurance | benefits | military | safeguarding
    description: str = ""
    questions: list = field(default_factory=list)  # list of TemplateQuestion dicts
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_builtin: bool = False


@dataclass
class EvidenceSnippet:
    """A piece of text extracted from records relevant to a question."""
    text: str = ""
    source_file: str = ""
    page_num: int = 0
    confidence: float = 0.0


@dataclass
class ReportAnswer:
    """An answer to a single template question."""
    question_id: str = ""
    question_text: str = ""
    answer: str = ""
    evidence: list = field(default_factory=list)  # list of EvidenceSnippet dicts
    reviewed: bool = False


@dataclass
class PatientDetails:
    """Patient details for a medical report."""
    full_name: str = ""
    date_of_birth: str = ""
    nhs_number: str = ""
    address: str = ""
    gp_name: str = ""
    gp_practice: str = ""


@dataclass
class MedicalReport:
    """A medical report in progress."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    template_id: str = ""
    template_name: str = ""
    patient: PatientDetails = field(default_factory=PatientDetails)
    pdf_files: list = field(default_factory=list)
    document_dates: dict = field(default_factory=dict)
    answers: list = field(default_factory=list)  # list of ReportAnswer dicts
    status: str = "draft"  # draft | in_progress | complete
    created_by: str = ""
    created_by_name: str = ""
