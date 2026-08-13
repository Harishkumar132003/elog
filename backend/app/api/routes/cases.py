"""Screen 1 · a case, and the logs its participants write against it.

    case created (shared facts + roster)
      -> each participant adds their own log      (an `entries` document)
      -> the professor builds that log's questions (screens 2-3, unchanged)

A log *is* an entry: same collection, same fields, plus `case_id` and
`logged_at`. Everything downstream — certification, exercise, attempt, the
dashboard — keys on `entry_id` and needs no knowledge of cases at all.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.deps import CurrentParticipant, CurrentUser, case_filter_for, to_object_id
from app.api.routes.entries import _apply_corrections, _precompute_axis_hint
from app.core.constants import DopsRole, EntryStatus, Role, role_labels
from app.data.axes import subject_class
from app.db import mongo
from app.schemas.case import CaseCreate, CaseDetail, CaseOut, CasePage, LogCreate
from app.schemas.entry import EntryDetail
from app.services import catalogue, people
from app.services.ai import analyse_entry

router = APIRouter(prefix="/cases", tags=["cases"])
logger = logging.getLogger(__name__)


def _dops_role(user: dict[str, Any]) -> DopsRole:
    """Which of the four working identities this user is.

    The professor never gets here — every route that calls this is gated to
    participants — but a user seeded before `dops_role` existed would have none,
    so fall back rather than 500.
    """
    try:
        return DopsRole(user.get("dops_role") or "")
    except ValueError:
        return DopsRole.INDEPENDENT


def _label(role: str, subject: str) -> str:
    labels = role_labels(subject_class(subject))
    try:
        return labels.get(DopsRole(role), (role, ""))[0]
    except ValueError:
        return role


async def _visible_case(case_id: str, user: dict[str, Any]) -> dict[str, Any]:
    query = case_filter_for(user) | {"_id": to_object_id(case_id)}
    case = await mongo.cases().find_one(query)
    if case is None:
        # Same response whether it is missing or simply not theirs.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


async def _shape(
    case: dict[str, Any], viewer: dict[str, Any], *, detail: bool = False
) -> dict[str, Any]:
    """A case plus a row per participant, each showing how far their log has got.

    Shaped for the viewer. Everyone sees who was in the case and whether they
    have logged — that is roster, and the case header counts on it. Only the
    professor, and each person on their own row, sees more: the log's id (which
    is what opens it) and how far its assessment has got. A participant has no
    business reading a colleague's mark.
    """
    logs = {
        log["resident_id"]: log
        async for log in mongo.entries().find({"case_id": case["_id"]})
    }
    # One extra read for the whole roster rather than one per participant.
    exercises: dict[Any, dict[str, Any]] = {}
    if logs:
        cursor = mongo.exercises().find({"entry_id": {"$in": [log["_id"] for log in logs.values()]}})
        exercises = {exercise["entry_id"]: exercise async for exercise in cursor}

    is_professor = viewer.get("role") == Role.PROFESSOR.value
    me = ObjectId(viewer["id"])

    participants: list[dict[str, Any]] = []
    for participant in case.get("participants", []):
        log = logs.get(participant["user_id"])
        exercise = exercises.get(log["_id"]) if log else None
        # Their own row, or the professor's view of anyone's.
        mine = is_professor or participant["user_id"] == me
        participants.append(
            {
                "role": participant["role"],
                "role_label": _label(participant["role"], case["subject"]),
                "user_id": str(participant["user_id"]),
                "name": participant.get("name") or participant["role"],
                "is_creator": participant["user_id"] == case.get("created_by"),
                # Roster, and visible to everyone: the case header counts on it.
                "has_logged": log is not None,
                "logged_at": log.get("logged_at") if log else None,
                # The id is the key to the log and its exercise, so it is only
                # handed to someone entitled to open them.
                "entry_id": str(log["_id"]) if (log and mine) else None,
                "status": log.get("status") if (log and mine) else None,
                "questions": len(exercise.get("questions", [])) if (exercise and mine) else 0,
                "released": bool(exercise.get("released")) if (exercise and mine) else False,
            }
        )

    payload = mongo.serialize(case) or {}
    payload["subject_class"] = subject_class(case["subject"])
    payload["participants"] = participants
    if not detail:
        payload.pop("parsed", None)
    return payload


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
async def create_case(payload: CaseCreate, participant: CurrentParticipant) -> dict[str, Any]:
    """Enter the case once; everyone who was in it logs against it afterwards.

    The professor is refused by the dependency: they set questions, they do not
    work cases.
    """
    analysis = await analyse_entry(payload.narrative, payload.subject.value)
    competency = analysis["competency"]

    # The creator's choice wins over the AI's, but only within their own subject —
    # the system never files a case against something it did not offer.
    if payload.competency_id:
        chosen = await catalogue.by_slug(payload.competency_id)
        if chosen is None or chosen["subject"] != payload.subject.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "That competency is not one of this speciality's",
            )
        competency = chosen

    parsed = analysis["parsed"]
    parse_edited = _apply_corrections(parsed, payload)
    patient = parsed.get("patient") or {}

    mine = _dops_role(participant)
    roster = await _roster(mine, participant, payload.participants)

    professor = await people.by_key(people.PROFESSOR_KEY)
    document = {
        "subject": payload.subject.value,
        "narrative": payload.narrative.strip(),
        "competency_id": competency["id"] if competency else None,
        "competency_title": competency["title"] if competency else None,
        "confirmed": bool(payload.confirmed),
        "source": analysis["source"],
        "parse_edited": parse_edited,
        "diagnosis": (parsed.get("diagnosis") or {}).get("display"),
        "procedure": (parsed.get("procedure") or {}).get("display"),
        "patient_age": patient.get("age"),
        "patient_sex": patient.get("sex"),
        "parsed": parsed,
        "created_by": ObjectId(participant["id"]),
        "created_role": mine.value,
        "professor_id": professor["_id"] if professor else None,
        "participants": roster,
        "created_at": datetime.now(UTC),
    }

    result = await mongo.cases().insert_one(document)
    document["_id"] = result.inserted_id
    return await _shape(document, participant, detail=True)


async def _roster(
    mine: DopsRole, creator: dict[str, Any], others: list[DopsRole]
) -> list[dict[str, Any]]:
    """The creator first, then whoever else was in the room.

    Name and role are the same thing here, so choosing a role chooses the person —
    but the user id is resolved and stored, not the role string alone, so a later
    move to real accounts changes only this function.
    """
    roster = [
        {"role": mine.value, "user_id": ObjectId(creator["id"]), "name": creator["name"]}
    ]
    for role in others:
        if role == mine:
            continue  # you are already in your own case
        if any(existing["role"] == role.value for existing in roster):
            continue
        user = await people.by_key(role.value)
        if user is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such role: {role.value}"
            )
        roster.append({"role": role.value, "user_id": user["_id"], "name": user["name"]})
    return roster


@router.get("", response_model=CasePage)
async def list_cases(user: CurrentUser) -> dict[str, Any]:
    """Cases this user was in — every case, for a professor."""
    query = case_filter_for(user)
    collection = mongo.cases()
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("created_at", -1).limit(100)
    items = [await _shape(case, user) async for case in cursor]
    return {"items": items, "total": total}


# Declared before `/{case_id}`, which would otherwise swallow it.
@router.get("/roles/available", response_model=list[dict])
async def available_roles(user: CurrentUser) -> list[dict[str, Any]]:
    """The roles a case can be staffed with — everyone but the professor."""
    return [
        identity
        for identity in people.listing()
        if identity["role"] != Role.PROFESSOR.value
    ]


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case_detail(case_id: str, user: CurrentUser) -> dict[str, Any]:
    return await _shape(await _visible_case(case_id, user), user, detail=True)


@router.post("/{case_id}/logs", response_model=EntryDetail, status_code=status.HTTP_201_CREATED)
async def add_log(
    case_id: str,
    payload: LogCreate,
    participant: CurrentParticipant,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Your own account of a case you were in.

    The clinical facts come from the case, so this is only the participant's own
    words — what they did, saw or decided. Everything the downstream stages read
    is copied down onto the log, so they never need to know a case exists.
    """
    case = await _visible_case(case_id, participant)

    me = ObjectId(participant["id"])
    seat = next((p for p in case.get("participants", []) if p["user_id"] == me), None)
    if seat is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You were not part of this case")

    now = datetime.now(UTC)
    document = {
        "case_id": case["_id"],
        "resident_id": me,
        "professor_id": case.get("professor_id"),
        "subject": case["subject"],
        "narrative": payload.narrative.strip(),
        # The shared facts, carried so question generation can put the case and
        # this participant's own words side by side without a second lookup.
        "case_narrative": case["narrative"],
        "role": seat["role"],
        "competency_id": case.get("competency_id"),
        "competency_title": case.get("competency_title"),
        "confirmed": bool(case.get("confirmed")),
        "status": EntryStatus.LOGGED.value,
        "source": case.get("source", "rules"),
        "parse_edited": bool(case.get("parse_edited")),
        "diagnosis": case.get("diagnosis"),
        "procedure": case.get("procedure"),
        "patient_age": case.get("patient_age"),
        "patient_sex": case.get("patient_sex"),
        "parsed": case.get("parsed") or {},
        "logged_at": now,
        "created_at": now,
    }

    try:
        result = await mongo.entries().insert_one(document)
    except DuplicateKeyError:
        # The unique (case_id, resident_id) index. One log each, by design.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You have already logged this case"
        ) from None

    document["_id"] = result.inserted_id
    saved = mongo.serialize(document) or {}
    saved["role_label"] = _label(seat["role"], case["subject"])

    # Have the professor's axis shortlist ready before they ever open the log.
    if document["professor_id"] is not None:
        background.add_task(_precompute_axis_hint, saved)

    return saved


@router.get("/{case_id}/logs", response_model=list[EntryDetail])
async def list_logs(case_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    """The logs on this case that the caller is allowed to read.

    The professor sees every one — comparing accounts of the same event is how
    they judge what to ask each person. A participant sees only their own.

    Their accounts are what each of them is assessed on, and reading a senior's
    version before writing your own would change what you write. So the roster
    still shows *that* someone has logged; the text itself does not travel.
    """
    case = await _visible_case(case_id, user)
    query: dict[str, Any] = {"case_id": case["_id"]}
    if user["role"] != Role.PROFESSOR.value:
        query["resident_id"] = ObjectId(user["id"])

    order = {p["user_id"]: index for index, p in enumerate(case.get("participants", []))}

    logs: list[dict[str, Any]] = []
    async for log in mongo.entries().find(query):
        shaped = mongo.serialize(log) or {}
        shaped["role_label"] = _label(log.get("role", ""), case["subject"])
        logs.append(shaped)

    logs.sort(key=lambda log: order.get(ObjectId(log["resident_id"]), 99))
    return logs
