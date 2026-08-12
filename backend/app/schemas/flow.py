from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.entry import EntryDetail


class AxisOut(BaseModel):
    id: str
    family: str
    label: str
    varies: str
    example: str


class AxisFamilyOut(BaseModel):
    id: str
    label: str
    description: str
    axes: list[AxisOut]


class AxisSuggestion(BaseModel):
    axis_id: str
    label: str
    reason: str = ""
    example: str = ""


class CandidateAxes(BaseModel):
    """Screen 2 — candidate axes, filtered by competency + DOPS/role."""

    entry_id: str
    subject: str
    subject_class: str
    role: str
    role_label: str
    competency_title: str | None = None
    families: list[AxisFamilyOut]
    certified: bool = False
    # The AI's shortlist. Always a subset of `families`; empty until requested.
    suggestions: list[AxisSuggestion] = []
    critical_axis: str | None = None
    critical_why: str = ""


class ParameterChoice(BaseModel):
    """One variation to test, and the question it becomes.

    Marks and the Critical flag live here rather than on the axis: each parameter
    is its own question, and a question is what carries them.
    """

    text: str = Field(default="", max_length=400)
    marks: int = Field(default=10, ge=1, le=100)
    critical: bool = False


class AxisChoice(BaseModel):
    axis_id: str
    # "The professor may tick, untick and set parameters within these axes, and mark
    # each as discriminates or cosmetic for the entity."
    discriminates: bool = True
    # An axis is a *kind* of variation, so one case can be worth testing along it
    # several ways. Each entry here becomes one question.
    parameters: list[ParameterChoice] = []


class CertifyRequest(BaseModel):
    axes: list[AxisChoice] = Field(min_length=1)


class QuestionOut(BaseModel):
    id: int
    axis_id: str
    axis_label: str
    prompt: str
    cognitive: str
    affective: str
    psychomotor: str
    marks: int
    critical: bool


class ExerciseOut(BaseModel):
    entry_id: str
    status: str
    source: str
    questions: list[QuestionOut]
    competency_title: str | None = None
    role_label: str | None = None
    attempted: bool = False
    # Drafted questions stay with the professor until they release them.
    released: bool = False
    edited: bool = False
    # True while the questions are still being written in the background.
    generating: bool = False
    failed: bool = False


class QuestionEdit(BaseModel):
    id: int
    prompt: str = Field(min_length=10, max_length=1200)
    marks: int = Field(ge=1, le=100)
    critical: bool = False
    cognitive: str = Field(min_length=1, max_length=40)
    affective: str = Field(min_length=1, max_length=40)


class ExerciseUpdate(BaseModel):
    questions: list[QuestionEdit] = Field(min_length=1)


class AnswerIn(BaseModel):
    question_id: int
    answer: str = Field(default="", max_length=4000)


class AttemptRequest(BaseModel):
    # No product cap on questions — an axis may carry as many parameters as the
    # professor wants. This bound is a safety limit only: an unbounded list in a
    # request body is a denial-of-service surface, and 100 is far past real use.
    answers: list[AnswerIn] = Field(min_length=1, max_length=100)


class ResultOut(BaseModel):
    question_id: int
    axis_label: str
    prompt: str
    # What the resident actually wrote — stored since the first attempt, never surfaced.
    answer: str = ""
    cognitive: str
    affective: str
    psychomotor: str
    marks: int
    marks_awarded: int
    critical: bool
    critical_failed: bool
    verdict: str
    feedback: str


class AttemptSummary(BaseModel):
    marks_awarded: int
    marks_available: int
    percentage: int
    critical_failed: bool
    highest_cognitive: str | None = None
    outcome: str


class AttemptOut(BaseModel):
    entry_id: str
    competency_title: str | None = None
    source: str
    results: list[ResultOut]
    summary: AttemptSummary
    # True while the answers are still being marked in the background.
    marking: bool = False
    created_at: datetime


class CaseSnapshot(BaseModel):
    """One case screen in one response — absent stages are null, not 404."""

    entry: EntryDetail
    axes: CandidateAxes | None = None
    exercise: ExerciseOut | None = None
    attempt: AttemptOut | None = None
