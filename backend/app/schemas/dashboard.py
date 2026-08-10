from datetime import datetime

from pydantic import BaseModel


class ResidentRow(BaseModel):
    id: str
    name: str
    year: int | None = None
    department: str | None = None
    cases: int = 0
    answered: int = 0
    critical_failures: int = 0


class Totals(BaseModel):
    cases: int = 0
    awaiting_certification: int = 0
    in_review: int = 0
    ready_to_answer: int = 0
    reasoned: int = 0


class CoveredCompetency(BaseModel):
    id: str
    title: str
    logged: int = 0
    # Logged against a competency since removed from the catalogue. Still shown —
    # the cases happened — but outside the coverage ratio.
    retired: bool = False


class CompetencyGap(BaseModel):
    """A competency in the curriculum with no evidence logged against it yet."""

    id: str
    title: str


class CoverageRow(BaseModel):
    """One per subject: the ratio, then only the competencies with evidence.

    Listing every competency stopped being useful once a real curriculum could be
    loaded — forty blanks under each subject says nothing the ratio does not.
    """

    subject: str
    total: int = 0
    covered: int = 0
    percentage: int = 0
    competencies: list[CoveredCompetency] = []
    gaps: list[CompetencyGap] = []


class Bucket(BaseModel):
    key: str
    label: str
    count: int


class AxisRow(BaseModel):
    """How the resident scores when the case is varied along one axis."""

    axis_id: str
    label: str
    family: str
    questions: int
    awarded: int
    available: int
    percentage: int


class CognitiveRow(BaseModel):
    level: str
    correct: int
    asked: int
    target: bool = False


class DocumentationRow(BaseModel):
    """How often this resident leaves a given thing out of their entries."""

    id: str
    label: str
    missing: int
    of: int
    percentage: int


class RecentCase(BaseModel):
    id: str
    resident_id: str
    resident_name: str | None = None
    diagnosis: str | None = None
    competency_title: str | None = None
    subject: str
    status: str
    outcome: str | None = None
    percentage: int | None = None
    critical_failed: bool = False
    created_at: datetime


class Dashboard(BaseModel):
    resident_id: str | None = None
    residents: list[ResidentRow] = []
    totals: Totals = Totals()
    coverage: list[CoverageRow] = []
    outcomes: list[Bucket] = []
    critical_failed: int = 0
    attempts: int = 0
    axes: list[AxisRow] = []
    cognitive: list[CognitiveRow] = []
    documentation: list[DocumentationRow] = []
    recent: list[RecentCase] = []
