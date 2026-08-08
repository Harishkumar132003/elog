from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import DopsRole, Subject


class Diagnosis(BaseModel):
    core: str
    qualifiers: list[str] = []
    display: str


class Procedure(BaseModel):
    name: str
    detail: str | None = None
    display: str
    steps: list[dict] = []


class Patient(BaseModel):
    age: int | None = None
    sex: str | None = None
    display: str


class Omission(BaseModel):
    id: str
    short: str
    label: str


class ParsedCase(BaseModel):
    diagnosis: Diagnosis | None = None
    procedure: Procedure | None = None
    patient: Patient | None = None
    laterality: str | None = None
    omissions: list[Omission] = []


class CompetencyOut(BaseModel):
    id: str
    subject: str
    title: str
    logs: str


class ParseRequest(BaseModel):
    subject: Subject
    narrative: str = Field(min_length=1, max_length=4000)


class ParseResponse(BaseModel):
    parsed: ParsedCase
    competency: CompetencyOut | None = None
    confidence: float = 0.0
    source: str = "rules"


class EntryCreate(BaseModel):
    subject: Subject
    narrative: str = Field(min_length=1, max_length=4000)
    role: DopsRole
    confirmed: bool = False

    # The competency the resident settled on. A subject now has many, so the AI's
    # pick is a proposal; this is the answer. Omitted means "keep what the AI chose".
    competency_id: str | None = None

    # Corrections to what the parser read (§4A.1: the strip exists to make the
    # parse "visible and correctable"). Only fields actually sent are applied,
    # so an empty string means "clear this", not "leave it alone".
    diagnosis: str | None = Field(default=None, max_length=180)
    procedure: str | None = Field(default=None, max_length=180)
    patient_age: int | None = Field(default=None, ge=0, le=120)
    patient_sex: str | None = Field(default=None, max_length=8)


class EntryOut(BaseModel):
    id: str
    resident_id: str
    professor_id: str | None = None
    subject: str
    narrative: str
    role: str
    role_label: str | None = None
    competency_id: str | None = None
    competency_title: str | None = None
    confirmed: bool = False
    status: str
    source: str = "rules"
    # True when the resident corrected what the parser read.
    parse_edited: bool = False
    diagnosis: str | None = None
    procedure: str | None = None
    patient_age: int | None = None
    patient_sex: str | None = None
    created_at: datetime


class EntryDetail(EntryOut):
    parsed: ParsedCase


class EntryPage(BaseModel):
    items: list[EntryOut]
    total: int
    limit: int
    offset: int


class Bucket(BaseModel):
    key: str
    label: str
    count: int


class Stats(BaseModel):
    total: int
    certified: int
    answered: int
    by_subject: list[Bucket]
    by_role: list[Bucket]
    by_competency: list[Bucket]
