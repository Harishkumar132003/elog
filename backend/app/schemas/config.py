from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import Subject


class CompetencyRow(BaseModel):
    """One row of the catalogue as the Configuration screen sees it."""

    id: str
    subject: str
    title: str
    logs: str


class CompetencyList(BaseModel):
    subject: str
    items: list[CompetencyRow] = []
    updated_at: datetime | None = None
    updated_by: str | None = None


class CompetencyEdit(BaseModel):
    """A row the professor is saving. No id means it is new."""

    id: str | None = None
    title: str = Field(min_length=3, max_length=220)
    # Where a new row came from, for the record. Existing rows keep their own.
    source: str | None = Field(default=None, pattern="^(manual|pdf)$")


class CompetencySave(BaseModel):
    """The whole of one subject, saved at once.

    Sent as a complete list rather than per-row edits, so the server can work out
    what was removed. A row the professor deleted is simply absent.
    """

    subject: Subject
    items: list[CompetencyEdit] = Field(max_length=500)


class SaveResult(BaseModel):
    subject: str
    added: int
    updated: int
    removed: int
    items: list[CompetencyRow]


class ImportStarted(BaseModel):
    job_id: str
    pages_read: int
    pages_total: int
    chunks: int


class ImportJob(BaseModel):
    id: str
    subject: str
    status: str  # running | done | failed
    filename: str | None = None
    done: int = 0
    total: int = 0
    pages_read: int = 0
    pages_total: int = 0
    # True when the PDF was longer than the import ceiling and was read only in part.
    truncated: bool = False
    found: list[str] = []
    error: str | None = None
