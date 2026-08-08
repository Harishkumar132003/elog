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
from app.core.constants import DopsRole, EntryStatus, Role, role_labels
from app.data.axes import BY_ID as AXIS_BY_ID
from app.data.axes import FAMILY_LABELS, Family, candidate_axes, subject_class
from app.db import mongo
from app.schemas.flow import (
    AttemptOut,
    AttemptRequest,
    CandidateAxes,
    CaseSnapshot,
    CertifyRequest,
    ExerciseOut,
    ExerciseUpdate,
)
from app.services.axis_suggest import suggest_axes
from app.services.exercise import generate_questions
from app.services.scoring import pending_summary, score_answers

router = APIRouter(prefix="/entries", tags=["flow"])
logger = logging.getLogger(__name__)


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

    critical = [axis for axis in chosen if axis.critical]
    if len(critical) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Exactly one certified axis must carry the Critical (fatal-error) flag",
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


# --- Screen 3b · review, edit and release --------------------------------
def _shape_exercise(
    entry: dict[str, Any], exercise: dict[str, Any], attempted: bool
) -> dict[str, Any]:
    return {
        "entry_id": str(entry["_id"]),
        "status": entry.get("status", EntryStatus.CERTIFIED.value),
        "source": exercise.get("source", "corti"),
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
        "source": attempt.get("source", "corti"),
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
