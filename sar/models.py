from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import uuid


@dataclass
class User:
    """An application user (admin coordinator or GP)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    username: str = ""
    display_name: str = ""
    role: str = "gp"           # "admin" | "gp"
    is_superuser: bool = False
    password_hash: str = ""


class PIICategory(Enum):
    PERSON_NAME = "person_name"
    NHS_NUMBER = "nhs_number"
    DATE_OF_BIRTH = "date_of_birth"
    ADDRESS = "address"
    PHONE_NUMBER = "phone_number"
    POSTCODE = "postcode"
    EMAIL = "email"
    SAFEGUARDING = "safeguarding"
    SEXUAL_HEALTH = "sexual_health"
    CUSTOM_WORD = "custom_word"
    MANUAL = "manual"


class RedactionStatus(Enum):
    AUTO_REDACT = "auto_redact"
    FLAGGED = "flagged"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXCLUDED_SUBJECT = "excluded_subject"
    EXCLUDED_STAFF = "excluded_staff"


@dataclass
class TextSpan:
    """A piece of text with its position on a PDF page."""
    text: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    block_no: int = 0
    line_no: int = 0
    span_no: int = 0


@dataclass
class RedactionCandidate:
    """A detected piece of PII that may need redacting."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = ""
    category: PIICategory = PIICategory.PERSON_NAME
    status: RedactionStatus = RedactionStatus.FLAGGED
    confidence: float = 0.0
    page_num: int = 0
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    reason: str = ""
    exemption_code: str = ""
    risk_flags: list = field(default_factory=list)
    source_file: str = ""


@dataclass
class SubjectDetails:
    """Details of the data subject making the SAR."""
    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    nhs_number: str = ""
    date_of_birth: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    aliases: list = field(default_factory=list)


@dataclass
class DetectionSettings:
    """Configurable detection thresholds and category toggles."""
    auto_redact_threshold: float = 0.80
    flag_threshold: float = 0.50
    enabled_categories: list = field(default_factory=lambda: [
        "person_name", "nhs_number", "address", "phone_number",
        "postcode", "email", "safeguarding", "sexual_health",
        "custom_word", "manual",
    ])  # Note: date_of_birth excluded by default


@dataclass
class SARRequest:
    """Represents a single SAR processing job."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    subject: SubjectDetails = field(default_factory=SubjectDetails)
    pdf_files: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    detection_settings: DetectionSettings = field(default_factory=DetectionSettings)
    status: str = "pending"
    due_date: str = ""
    notes: str = ""
    workflow_status: str = "new"     # "new" | "in_review" | "ready_for_signoff" | "complete"
    allocated_to: str = ""           # User.id of allocated GP
    allocated_to_name: str = ""      # Denormalised display name
    last_modified: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Document date ordering: {filename: "YYYY-MM-DD" or None}
    document_dates: dict = field(default_factory=dict)

    # Original extraction order (list of basenames), captured before date-sort
    file_order: list = field(default_factory=list)
    # Basename of the "main record" file — always pinned first regardless of sort order
    main_record_file: str = ""

    # Stop-the-clock fields
    clock_paused: bool = False
    paused_at: str = ""              # ISO timestamp when clock was paused
    total_paused_days: int = 0       # Accumulated paused days from previous pauses
    pause_log: list = field(default_factory=list)  # [{paused_at, resumed_at, reason, days}]

    def compute_due_date(self) -> None:
        """Set due_date to 30 calendar days from created_at."""
        try:
            dt = datetime.fromisoformat(self.created_at)
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
        self.due_date = (dt + timedelta(days=30)).strftime("%Y-%m-%d")

    @property
    def _live_paused_days(self) -> int:
        """Days elapsed since the clock was paused (0 if not paused)."""
        if not self.clock_paused or not self.paused_at:
            return 0
        try:
            paused = datetime.fromisoformat(self.paused_at).date()
            return max(0, (datetime.now().date() - paused).days)
        except (ValueError, TypeError):
            return 0

    @property
    def days_remaining(self) -> int:
        """Days until the statutory deadline, accounting for paused time."""
        if not self.due_date:
            return 99
        try:
            due = datetime.strptime(self.due_date, "%Y-%m-%d").date()
            effective_due = due + timedelta(days=self.total_paused_days + self._live_paused_days)
            return (effective_due - datetime.now().date()).days
        except (ValueError, TypeError):
            return 99
