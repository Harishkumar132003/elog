"""A case, its roster, and the logs written against it.

The case holds what everyone in the room shares — subject, patient, diagnosis,
competency. Each participant's own account of it is an ordinary entry, so nothing
here restates the entry schema.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import DopsRole, Subject
from app.schemas.entry import ParsedCase


class CaseCreate(BaseModel):
    subject: Subject
    narrative: str = Field(min_length=1, max_length=4000)

    # Who else was in the room. The creator is added automatically and is refused
    # here — you cannot invite yourself twice.
    participants: list[DopsRole] = Field(default=[], max_length=4)

    confirmed: bool = False
    competency_id: str | None = None

    # Corrections to what the parser read (§4A.1), applied exactly as they are on
    # an entry: only fields actually sent are used, so "" means clear it.
    diagnosis: str | None = Field(default=None, max_length=180)
    procedure: str | None = Field(default=None, max_length=180)
    patient_age: int | None = Field(default=None, ge=0, le=120)
    patient_sex: str | None = Field(default=None, max_length=8)


class LogCreate(BaseModel):
    """One participant's own account. The case supplies everything else."""

    narrative: str = Field(min_length=1, max_length=4000)


class ParticipantOut(BaseModel):
    role: str
    role_label: str
    user_id: str
    name: str
    is_creator: bool = False

    # Roster, shown to everyone on the case.
    has_logged: bool = False
    logged_at: datetime | None = None

    # Only for the professor, and for each person on their own row. `entry_id`
    # is what opens a log and its exercise, so it is withheld rather than the
    # client being trusted to hide it; the rest is somebody's assessment.
    entry_id: str | None = None
    status: str | None = None
    questions: int = 0
    released: bool = False


class CaseOut(BaseModel):
    id: str
    subject: str
    subject_class: str
    narrative: str
    competency_id: str | None = None
    competency_title: str | None = None
    confirmed: bool = False
    source: str = "rules"
    parse_edited: bool = False
    diagnosis: str | None = None
    procedure: str | None = None
    patient_age: int | None = None
    patient_sex: str | None = None
    created_by: str
    created_role: str
    created_at: datetime
    participants: list[ParticipantOut] = []


class CaseDetail(CaseOut):
    parsed: ParsedCase


class CasePage(BaseModel):
    items: list[CaseOut]
    total: int
