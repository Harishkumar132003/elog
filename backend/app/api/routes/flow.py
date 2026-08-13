"""Screens 2, 3 and 4 — analysis, certification, reasoning.

    entry logged  →  candidate axes (2)  →  professor certifies (3)
                  →  questions generated →  resident answers, marked (4)
"""

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.deps import CurrentProfessor, CurrentResident, CurrentUser, entry_filter_for, to_object_id
from app.core.config import get_settings
from app.core.constants import DopsRole, EntryStatus, Role, role_labels
from app.data.axes import BY_ID as AXIS_BY_ID
from app.data.axes import FAMILY_LABELS, Family, candidate_axes, subject_class
from app.data.bloom import AFFECTIVE_LEVELS, COGNITIVE_LEVELS, PSYCHOMOTOR_LEVELS
from app.db import mongo
from app.schemas.flow import (
    AttemptOut,
    AttemptRequest,
    CandidateAxes,
    CaseSnapshot,
    CertifyRequest,
    ExerciseOut,
    ExerciseUpdate,
    ParameterSuggestRequest,
    QuestionAdd,
    QuestionOut,
)
from app.services.axis_suggest import suggest_axes
from app.services.parameter_suggest import suggest_parameters
from app.services.exercise import (
    default_levels,
    default_psychomotor,
    generate_one,
    generate_questions,
)
from app.services.scoring import pending_summary, score_answers

router = APIRouter(prefix="/entries", tags=["flow"])
logger = logging.getLogger(__name__)
_settings = get_settings()


async def _owned_entry(entry_id: str, user: dict[str, Any]) -> dict[str, Any]:
    query = entry_filter_for(user) | {"_id": to_object_id(entry_id)}
    entry = await mongo.entries().find_one(query)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return entry


def _role_label(entry: dict[str, Any]) -> str:
    labels = role_labels(subject_class(entry["subject"]))
    try:
        role = DopsRole(entry.get("role", ""))
    except ValueError:
        return str(entry.get("role", ""))
    return labels.get(role, (str(role.value), ""))[0]


# --- Screen 2 · analysis -------------------------------------------------
async def _axes_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """The closed axis set, filtered by competency + DOPS/role (§2, §5)."""
    axes = candidate_axes(entry["subject"], entry["role"])

    grouped: list[dict[str, Any]] = []
    for family in Family:
        members = [axis for axis in axes if axis["family"] == family]
        if not members:
            continue
        label, description = FAMILY_LABELS[family]
        grouped.append(
            {"id": family.value, "label": label, "description": description, "axes": members}
        )

    certified = await mongo.certifications().find_one({"entry_id": entry["_id"]}, {"_id": 1})
    hint = entry.get("axis_hint") or {}
    return {
        "entry_id": str(entry["_id"]),
        "subject": entry["subject"],
        "subject_class": subject_class(entry["subject"]),
        "role": entry["role"],
        "role_label": _role_label(entry),
        "competency_title": entry.get("competency_title"),
        "families": grouped,
        "certified": certified is not None,
        "suggestions": hint.get("suggestions", []),
        "critical_axis": hint.get("critical_axis"),
        "critical_why": hint.get("critical_why", ""),
    }


@router.get("/{entry_id}/axes", response_model=CandidateAxes)
async def get_candidate_axes(entry_id: str, user: CurrentUser) -> dict[str, Any]:
    return await _axes_payload(await _owned_entry(entry_id, user))


@router.get("/{entry_id}/case", response_model=CaseSnapshot)
async def get_case(entry_id: str, user: CurrentUser) -> dict[str, Any]:
    """Everything one case screen needs, in a single request.

    Absent stages come back as null rather than as a 404 from a separate call:
    an uncertified case has no exercise, and an unattempted one has no result —
    those are ordinary states, not errors.
    """
    entry = await _owned_entry(entry_id, user)
    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    attempt = await mongo.attempts().find_one(
        {"entry_id": entry["_id"]}, sort=[("created_at", -1)]
    )

    # The release gate still applies: a resident sees no draft at all.
    if exercise is not None and user["role"] != Role.PROFESSOR.value and not exercise.get("released"):
        exercise = None

    entry_payload = mongo.serialize(entry) or {}
    entry_payload["role_label"] = _role_label(entry)

    return {
        "entry": entry_payload,
        "axes": await _axes_payload(entry),
        "exercise": _shape_exercise(entry, exercise, attempt is not None) if exercise else None,
        "attempt": _shape_attempt(entry, attempt) if attempt else None,
    }


@router.post("/{entry_id}/axes/suggest")
async def suggest(entry_id: str, professor: CurrentProfessor) -> dict[str, Any]:
    """Shortlist the axes worth testing, from the ones already offered.

    Cached on the entry: opening the same case again never spends another call.
    """
    entry = await _owned_entry(entry_id, professor)
    cached = entry.get("axis_hint")
    if cached and cached.get("suggestions"):
        return cached

    hint = await suggest_axes(mongo.serialize(entry))  # type: ignore[arg-type]
    if hint["suggestions"]:
        await mongo.entries().update_one(
            {"_id": entry["_id"]}, {"$set": {"axis_hint": hint}}
        )
    return hint


@router.post("/{entry_id}/axes/{axis_id}/parameters/suggest")
async def suggest_parameters_for_axis(
    entry_id: str,
    axis_id: str,
    professor: CurrentProfessor,
    payload: ParameterSuggestRequest | None = None,
) -> dict[str, Any]:
    """Concrete ways to vary this case along one axis.

    Deliberately not cached, unlike the axis shortlist. Pressing it again should
    give a fresh set — a professor who did not like the first three wants
    different ones, not the same three served from the entry.

    What this log already has on this axis is read from its own certification
    and sent along, so the model proposes something new rather than the same
    obvious variation a third time.
    """
    entry = await _owned_entry(entry_id, professor)
    already = await _parameters_used(entry["_id"], axis_id)
    # Plus anything sitting unsaved in the professor's box, which the
    # certification cannot know about yet.
    already += [text for text in (payload.existing if payload else []) if text]
    return await suggest_parameters(
        mongo.serialize(entry),  # type: ignore[arg-type]
        axis_id,
        already,
    )


async def _parameters_used(entry_id: ObjectId, axis_id: str) -> list[str]:
    """The parameters already certified on this axis, for this one log.

    Read from the stored certification rather than taken from the client: the
    client holds generated questions, not the variations behind them, so it has
    no way to tell the model what has already been asked.

    Scoped to the entry, which is one participant's log of one case. So the
    observer and the supervisor on the same case may both be asked about the
    same variation — they are different people reasoning from different vantage
    points — but neither of them is ever asked it twice.
    """
    certification = await mongo.certifications().find_one({"entry_id": entry_id})
    if not certification:
        return []
    return [
        text
        for axis in certification.get("axes", [])
        if axis.get("axis_id") == axis_id
        for parameter in axis.get("parameters", [])
        if (text := (parameter.get("text") or "").strip())
    ]


# --- Screen 3 · configure ------------------------------------------------
@router.post("/{entry_id}/certify", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED)
async def certify(
    entry_id: str,
    payload: CertifyRequest,
    professor: CurrentProfessor,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """The professor certifies which axes discriminate and sets the Critical item."""
    entry = await _owned_entry(entry_id, professor)
    allowed = {axis["id"] for axis in candidate_axes(entry["subject"], entry["role"])}

    chosen = [axis for axis in payload.axes if axis.discriminates]
    if not chosen:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Certify at least one axis as discriminating",
        )

    # The axis list is closed: anything outside the role-filtered set is refused
    # here as well as in the UI, so no invented axis can reach the generator.
    unknown = [axis.axis_id for axis in payload.axes if axis.axis_id not in allowed]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Axis not offered for this entry: {', '.join(unknown)}",
        )

    # One question per parameter, so an axis with nothing filled in produces nothing.
    parameters = [p for axis in chosen for p in axis.parameters]
    if not parameters:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Add at least one parameter to a certified axis",
        )

    # Counted across every parameter, not per axis: the Critical item is one
    # question in the whole exercise (§3.4), wherever the professor put it.
    critical = [p for p in parameters if p.critical]
    if len(critical) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Exactly one parameter must be the critical question — found {len(critical)}",
        )

    certification = {
        "entry_id": entry["_id"],
        "professor_id": ObjectId(professor["id"]),
        "axes": [axis.model_dump() for axis in payload.axes],
        "certified_at": datetime.now(UTC),
    }
    await mongo.certifications().update_one(
        {"entry_id": entry["_id"]}, {"$set": certification}, upsert=True
    )

    # Writing the questions takes ~20-30s and Corti's latency varies several-fold.
    # Returning now and generating afterwards keeps the request well clear of any
    # proxy read timeout, and survives the professor reloading the page.
    exercise = {
        "entry_id": entry["_id"],
        "resident_id": entry["resident_id"],
        "professor_id": ObjectId(professor["id"]),
        "questions": [],
        "source": "pending",
        # Drafted, not yet handed over — the professor reviews first.
        "released": False,
        "edited": False,
        "generating": True,
        "failed": False,
        "created_at": datetime.now(UTC),
    }
    await mongo.exercises().update_one({"entry_id": entry["_id"]}, {"$set": exercise}, upsert=True)
    await mongo.entries().update_one(
        {"_id": entry["_id"]}, {"$set": {"status": EntryStatus.CERTIFIED.value}}
    )

    background.add_task(
        _generate_in_background, entry["_id"], mongo.serialize(entry), certification
    )
    entry["status"] = EntryStatus.CERTIFIED.value
    return _shape_exercise(entry, exercise, attempted=False)


# --- Screen 3 · one question at a time -----------------------------------
def _checked_axis(entry: dict[str, Any], axis_id: str) -> dict[str, str]:
    """The axis, if it is one this entry's role actually offers.

    The closed set is enforced here as well as in the UI, so no invented axis can
    reach the generator or the stored certification.
    """
    allowed = {axis["id"] for axis in candidate_axes(entry["subject"], entry["role"])}
    axis = AXIS_BY_ID.get(axis_id)
    if axis is None or axis_id not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Axis not offered for this entry: {axis_id}",
        )
    return axis


@router.post("/{entry_id}/questions/preview", response_model=QuestionOut)
async def preview_question(
    entry_id: str, payload: QuestionAdd, professor: CurrentProfessor
) -> dict[str, Any]:
    """Write one question and hand it back WITHOUT storing it.

    The professor reads what the AI produced, edits the wording if it is not
    quite right, and only then saves. Splitting generation from the save is the
    whole point: a question they cannot read before committing is one they have
    to delete afterwards.

    Nothing here touches the exercise or the certification, so abandoning a
    preview leaves no trace — it costs one AI call and nothing else.
    """
    entry = await _owned_entry(entry_id, professor)
    _checked_axis(entry, payload.axis_id)

    question = await generate_one(
        mongo.serialize(entry),  # type: ignore[arg-type]
        payload.axis_id,
        payload.parameter.strip(),
        payload.marks,
        payload.critical,
    )
    if question is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The question could not be written — try again"
        )
    question.pop("source", None)
    # Id 0 = not placed yet. The slot is decided on save, by how many questions
    # the exercise holds then — a preview has no position in the set.
    question["id"] = 0
    return question


@router.post("/{entry_id}/questions", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED)
async def add_question(
    entry_id: str, payload: QuestionAdd, professor: CurrentProfessor
) -> dict[str, Any]:
    """Write one question and append it to this log's set.

    The builder screen works a card at a time — choose an axis, settle on a
    parameter, generate, read it, edit it, keep it — rather than certifying a
    batch and waiting for the whole exercise. So this both extends the
    certification and extends the exercise, keeping the two in step.

    Send `prompt` and this stores that wording as given; omit it and this
    generates one. The builder always sends it, because the professor has just
    read the preview — generating here too would spend a second call and throw
    away the version they approved.
    """
    entry = await _owned_entry(entry_id, professor)
    axis = _checked_axis(entry, payload.axis_id)

    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    if exercise and exercise.get("released"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This exercise has been released and can no longer be changed",
        )

    if payload.prompt:
        cognitive, affective = default_levels(payload.axis_id)
        question = {
            "axis_id": payload.axis_id,
            "axis_label": axis["label"],
            "prompt": payload.prompt.strip(),
            # The levels are the professor's if they set them, and the axis's own
            # otherwise — never a value outside the two closed Bloom lists.
            "cognitive": payload.cognitive if payload.cognitive in COGNITIVE_LEVELS else cognitive,
            "affective": payload.affective if payload.affective in AFFECTIVE_LEVELS else affective,
            "psychomotor": payload.psychomotor
            if payload.psychomotor in PSYCHOMOTOR_LEVELS
            else default_psychomotor(entry),
            "marks": payload.marks,
            "critical": payload.critical,
            # The wording came from the preview and may have been reworded since,
            # so the provider is what produced it either way.
            "source": _settings.ai_provider,
        }
    else:
        question = await generate_one(
            mongo.serialize(entry),  # type: ignore[arg-type]
            payload.axis_id,
            payload.parameter.strip(),
            payload.marks,
            payload.critical,
        )
    if question is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The question could not be written — try again"
        )

    existing = list(exercise.get("questions", [])) if exercise else []
    # Exactly one Critical item per exercise (§3.4). Ticking it here takes it off
    # whichever question held it — last wins — because demanding the invariant on
    # every save would make it impossible to move.
    if payload.critical:
        for other in existing:
            other["critical"] = False

    source = question.pop("source", _settings.ai_provider)
    question["id"] = len(existing) + 1
    questions = existing + [question]

    await mongo.exercises().update_one(
        {"entry_id": entry["_id"]},
        {
            "$set": {
                "questions": questions,
                "source": source,
                "generating": False,
                "failed": False,
                "edited": True,
            },
            "$setOnInsert": {
                "entry_id": entry["_id"],
                "resident_id": entry["resident_id"],
                "professor_id": ObjectId(professor["id"]),
                "released": False,
                "created_at": datetime.now(UTC),
            },
        },
        upsert=True,
    )

    # Keep the certification in step: the dashboard's axis roll-up and the
    # certification screen both read it, and a question with no certified axis
    # behind it would be invisible to them.
    await _record_certified(entry, professor, payload, clear_critical=payload.critical)
    await mongo.entries().update_one(
        {"_id": entry["_id"]}, {"$set": {"status": EntryStatus.CERTIFIED.value}}
    )
    entry["status"] = EntryStatus.CERTIFIED.value

    # Echo the fields just written, not the document as it was read. `exercise`
    # is None on the first question, so shaping from it alone reported the
    # default source of "corti" for a question that actually came from the
    # scripted fallback — the stored value was right, the answer was not.
    return _shape_exercise(
        entry,
        {
            **(exercise or {}),
            "questions": questions,
            "source": source,
            "generating": False,
            "failed": False,
            "edited": True,
        },
        attempted=False,
    )


async def _record_certified(
    entry: dict[str, Any],
    professor: dict[str, Any],
    payload: QuestionAdd,
    clear_critical: bool,
) -> None:
    """Append this parameter to the entry's certification, creating it if needed."""
    certification = await mongo.certifications().find_one({"entry_id": entry["_id"]})
    axes: list[dict[str, Any]] = list(certification.get("axes", [])) if certification else []

    if clear_critical:
        for axis in axes:
            for parameter in axis.get("parameters", []):
                parameter["critical"] = False

    parameter = {
        "text": payload.parameter.strip(),
        "marks": payload.marks,
        "critical": payload.critical,
    }
    for axis in axes:
        if axis["axis_id"] == payload.axis_id:
            axis.setdefault("parameters", []).append(parameter)
            break
    else:
        axes.append(
            {"axis_id": payload.axis_id, "discriminates": True, "parameters": [parameter]}
        )

    await mongo.certifications().update_one(
        {"entry_id": entry["_id"]},
        {
            "$set": {
                "axes": axes,
                "professor_id": ObjectId(professor["id"]),
                "certified_at": datetime.now(UTC),
            },
            "$setOnInsert": {"entry_id": entry["_id"]},
        },
        upsert=True,
    )


@router.delete("/{entry_id}/questions/{question_id}", response_model=ExerciseOut)
async def remove_question(
    entry_id: str, question_id: int, professor: CurrentProfessor
) -> dict[str, Any]:
    """Drop one question and renumber. Refused once released."""
    entry = await _owned_entry(entry_id, professor)
    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No exercise for this entry")
    if exercise.get("released"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This exercise has been released and can no longer be changed",
        )

    questions = [q for q in exercise.get("questions", []) if q["id"] != question_id]
    if len(questions) == len(exercise.get("questions", [])):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question")

    # Renumber so ids stay 1..n. Safe: an attempt can only exist after release,
    # and a released exercise never reaches here.
    for position, question in enumerate(questions, start=1):
        question["id"] = position

    await mongo.exercises().update_one(
        {"_id": exercise["_id"]}, {"$set": {"questions": questions}}
    )
    exercise["questions"] = questions
    return _shape_exercise(entry, exercise, attempted=False)


# --- Screen 3b · review, edit and release --------------------------------
def _shape_exercise(
    entry: dict[str, Any], exercise: dict[str, Any], attempted: bool
) -> dict[str, Any]:
    return {
        "entry_id": str(entry["_id"]),
        "status": entry.get("status", EntryStatus.CERTIFIED.value),
        "source": exercise.get("source", _settings.ai_provider),
        "questions": exercise["questions"],
        "competency_title": entry.get("competency_title"),
        "role_label": _role_label(entry),
        "attempted": attempted,
        "released": bool(exercise.get("released")),
        "edited": bool(exercise.get("edited")),
        "generating": bool(exercise.get("generating")),
        "failed": bool(exercise.get("failed")),
    }


async def _generate_in_background(
    entry_id: ObjectId, entry: dict[str, Any], certification: dict[str, Any]
) -> None:
    """Write the questions after the response has gone out."""
    try:
        generated = await generate_questions(entry, certification)
        await mongo.exercises().update_one(
            {"entry_id": entry_id},
            {
                "$set": {
                    "questions": generated["questions"],
                    "source": generated["source"],
                    "generating": False,
                    "failed": not generated["questions"],
                }
            },
        )
    except Exception:
        logger.exception("Background question generation failed for entry %s", entry_id)
        await mongo.exercises().update_one(
            {"entry_id": entry_id}, {"$set": {"generating": False, "failed": True}}
        )


@router.put("/{entry_id}/exercise", response_model=ExerciseOut)
async def update_exercise(
    entry_id: str, payload: ExerciseUpdate, professor: CurrentProfessor
) -> dict[str, Any]:
    """Reword the drafted questions before they reach the resident.

    The professor owns the wording; the axis each question came from is not
    editable, because that is what the closed set guarantees.
    """
    entry = await _owned_entry(entry_id, professor)
    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No exercise for this entry")
    if exercise.get("generating"):
        raise HTTPException(status.HTTP_409_CONFLICT, "The questions are still being written")
    if exercise.get("released"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This exercise has been released and can no longer be edited",
        )

    edits = {edit.id: edit for edit in payload.questions}
    critical = [edit for edit in payload.questions if edit.critical]
    if len(critical) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Exactly one question must carry the Critical (fatal-error) flag",
        )

    questions: list[dict[str, Any]] = []
    for question in exercise["questions"]:
        edit = edits.get(question["id"])
        if edit is None:
            continue  # dropped by the professor
        questions.append(
            {
                **question,
                "prompt": edit.prompt.strip(),
                "marks": edit.marks,
                "critical": edit.critical,
                "cognitive": edit.cognitive,
                "affective": edit.affective,
                "psychomotor": edit.psychomotor
                if edit.psychomotor in PSYCHOMOTOR_LEVELS
                else question.get("psychomotor") or default_psychomotor(entry),
            }
        )

    if not questions:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "An exercise needs at least one question"
        )

    await mongo.exercises().update_one(
        {"_id": exercise["_id"]},
        {"$set": {"questions": questions, "edited": True, "edited_at": datetime.now(UTC)}},
    )
    exercise["questions"] = questions
    exercise["edited"] = True
    return _shape_exercise(entry, exercise, attempted=False)


@router.post("/{entry_id}/exercise/release", response_model=ExerciseOut)
async def release_exercise(entry_id: str, professor: CurrentProfessor) -> dict[str, Any]:
    """Hand the exercise to the resident. Until this, they cannot see it."""
    entry = await _owned_entry(entry_id, professor)
    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No exercise for this entry")
    if exercise.get("generating") or not exercise.get("questions"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The questions are not ready to release yet"
        )

    # Checked here rather than on every save: the set is built a question at a
    # time, so demanding a whole-exercise invariant mid-build would make the
    # Critical item impossible to place. Release is the moment it must hold.
    critical = [q for q in exercise["questions"] if q.get("critical")]
    if len(critical) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Exactly one question must be the critical question — "
            f"found {len(critical)}",
        )

    await mongo.exercises().update_one(
        {"_id": exercise["_id"]},
        {"$set": {"released": True, "released_at": datetime.now(UTC)}},
    )
    await mongo.entries().update_one(
        {"_id": entry["_id"]}, {"$set": {"status": EntryStatus.RELEASED.value}}
    )
    exercise["released"] = True
    entry["status"] = EntryStatus.RELEASED.value
    return _shape_exercise(entry, exercise, attempted=False)


# --- Screen 4 · reason ---------------------------------------------------
@router.get("/{entry_id}/exercise", response_model=ExerciseOut)
async def get_exercise(entry_id: str, user: CurrentUser) -> dict[str, Any]:
    entry = await _owned_entry(entry_id, user)
    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    if exercise is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This case has not been certified by a professor yet"
        )
    # A draft belongs to the professor until released.
    if user["role"] != Role.PROFESSOR.value and not exercise.get("released"):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Your professor has not released this exercise yet"
        )
    attempt = await mongo.attempts().find_one({"entry_id": entry["_id"]}, {"_id": 1})
    return _shape_exercise(entry, exercise, attempted=attempt is not None)


@router.post("/{entry_id}/attempt", response_model=AttemptOut, status_code=status.HTTP_201_CREATED)
async def submit_attempt(
    entry_id: str,
    payload: AttemptRequest,
    resident: CurrentResident,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """The resident's free-text answers, marked across the three domains."""
    entry = await _owned_entry(entry_id, resident)
    exercise = await mongo.exercises().find_one({"entry_id": entry["_id"]})
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No exercise for this entry")
    if not exercise.get("released"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Your professor has not released this exercise yet"
        )

    answers = {answer.question_id: answer.answer for answer in payload.answers}

    # The answers are persisted before marking starts, so a slow or failed
    # marking pass can never lose the resident's work.
    attempt = {
        "entry_id": entry["_id"],
        "exercise_id": exercise["_id"],
        "resident_id": ObjectId(resident["id"]),
        "professor_id": entry.get("professor_id"),
        "competency_id": entry.get("competency_id"),
        "competency_title": entry.get("competency_title"),
        # BSON keys must be strings — the slot numbers are ints internally.
        "answers": {str(slot): text for slot, text in answers.items()},
        "results": [],
        "summary": pending_summary(),
        "source": "pending",
        "marking": True,
        "created_at": datetime.now(UTC),
    }
    inserted = await mongo.attempts().insert_one(attempt)
    await mongo.entries().update_one(
        {"_id": entry["_id"]}, {"$set": {"status": EntryStatus.ANSWERED.value}}
    )

    background.add_task(
        _mark_in_background, inserted.inserted_id, exercise["questions"], answers
    )
    return _shape_attempt(entry, attempt)


def _shape_attempt(entry: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    # The answers are stored keyed by slot; put each one back beside its mark so a
    # professor can judge whether the mark was fair.
    answers = attempt.get("answers", {}) or {}
    results = [
        {**result, "answer": answers.get(str(result.get("question_id")), "")}
        for result in attempt.get("results", [])
    ]
    return {
        "entry_id": str(entry["_id"]),
        "competency_title": attempt.get("competency_title"),
        "source": attempt.get("source", _settings.ai_provider),
        "results": results,
        "summary": attempt["summary"],
        "marking": bool(attempt.get("marking")),
        "created_at": attempt["created_at"],
    }


async def _mark_in_background(
    attempt_id: ObjectId, questions: list[dict[str, Any]], answers: dict[int, str]
) -> None:
    """Mark after the response has gone out; the answers are already saved."""
    try:
        scored = await score_answers(questions, answers)
        update = {
            "results": scored["results"],
            "summary": scored["summary"],
            "source": scored["source"],
            "marking": False,
        }
    except Exception:
        logger.exception("Background marking failed for attempt %s", attempt_id)
        update = {"marking": False, "source": "rules-fallback"}
    await mongo.attempts().update_one({"_id": attempt_id}, {"$set": update})


@router.get("/{entry_id}/attempt", response_model=AttemptOut)
async def get_attempt(entry_id: str, user: CurrentUser) -> dict[str, Any]:
    """The recorded result — the roll-up screen (§3.5)."""
    entry = await _owned_entry(entry_id, user)
    attempt = await mongo.attempts().find_one(
        {"entry_id": entry["_id"]}, sort=[("created_at", -1)]
    )
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This exercise has not been attempted yet")
    return _shape_attempt(entry, attempt)


# Kept for the certification screen: what the professor already ticked.
@router.get("/{entry_id}/certification")
async def get_certification(entry_id: str, user: CurrentUser) -> dict[str, Any]:
    entry = await _owned_entry(entry_id, user)
    certification = await mongo.certifications().find_one({"entry_id": entry["_id"]})
    if certification is None:
        return {"entry_id": str(entry["_id"]), "axes": [], "certified": False}
    return {
        "entry_id": str(entry["_id"]),
        "axes": [
            {**axis, "label": (AXIS_BY_ID.get(axis["axis_id"]) or {}).get("label", axis["axis_id"])}
            for axis in certification["axes"]
        ],
        "certified": True,
        "certified_at": certification.get("certified_at"),
    }
