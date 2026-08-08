from datetime import UTC, datetime
from typing import Any

import logging

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.api.deps import CurrentResident, CurrentUser, entry_filter_for, to_object_id
from app.core.config import get_settings
from app.core.constants import DopsRole, EntryStatus, role_labels
from app.data.axes import subject_class
from app.db import mongo
from app.schemas.entry import (
    EntryCreate,
    EntryDetail,
    EntryOut,
    EntryPage,
    ParseRequest,
    ParseResponse,
)
from app.services import catalogue
from app.services.ai import analyse_entry
from app.services.axis_suggest import suggest_axes

router = APIRouter(prefix="/entries", tags=["entries"])
logger = logging.getLogger(__name__)
_settings = get_settings()


async def _precompute_axis_hint(entry: dict[str, Any]) -> None:
    """Shortlist the axes right after saving, in the background.

    Nothing depends on this finishing: the certify screen still has its own
    button, and the professor sees the shortlist ready only because the work was
    already done. Never let a failure here surface to the resident, who has by
    then had a successful save.
    """
    try:
        hint = await suggest_axes(entry)
        if hint["suggestions"]:
            await mongo.entries().update_one(
                {"_id": ObjectId(entry["id"])}, {"$set": {"axis_hint": hint}}
            )
    except Exception:
        logger.exception("Background axis suggestion failed for entry %s", entry.get("id"))


def _with_role_label(document: dict[str, Any]) -> dict[str, Any]:
    """The same role id reads differently by subject class (§4A.2)."""
    labels = role_labels(subject_class(document.get("subject", "")))
    try:
        role = DopsRole(document.get("role", ""))
    except ValueError:
        return document
    document["role_label"] = labels.get(role, (str(role.value), ""))[0]
    return document


@router.post("/parse", response_model=ParseResponse)
async def parse(payload: ParseRequest, user: CurrentUser) -> dict[str, Any]:
    """Live preview for the entry form. Nothing is persisted."""
    return await analyse_entry(payload.narrative, payload.subject.value)


def _apply_corrections(parsed: dict[str, Any], payload: EntryCreate) -> bool:
    """Overlay the resident's corrections onto the parse.

    Written back into `parsed`, not just the flat columns, because question
    generation reads `parsed` — a correction the resident made here has to be
    the version the reasoning exercise is built from.
    """
    sent = payload.model_fields_set
    edited = False

    if "diagnosis" in sent:
        value = (payload.diagnosis or "").strip()
        before = (parsed.get("diagnosis") or {}).get("display")
        parsed["diagnosis"] = (
            {"core": value, "qualifiers": [], "display": value} if value else None
        )
        edited |= value != (before or "")

    if "procedure" in sent:
        value = (payload.procedure or "").strip()
        before = (parsed.get("procedure") or {}).get("display")
        parsed["procedure"] = (
            {"name": value, "detail": None, "display": value, "steps": []} if value else None
        )
        edited |= value != (before or "")

    if "patient_age" in sent or "patient_sex" in sent:
        before = parsed.get("patient") or {}
        age = payload.patient_age or None
        sex = (payload.patient_sex or "").strip() or None
        if age or sex:
            display = f"{age} · {sex}" if age and sex else str(age or sex)
            parsed["patient"] = {"age": age, "sex": sex, "display": display}
        else:
            parsed["patient"] = None
        edited |= age != before.get("age") or sex != before.get("sex")

    return edited


@router.post("", response_model=EntryDetail, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: EntryCreate, resident: CurrentResident, background: BackgroundTasks
) -> dict[str, Any]:
    analysis = await analyse_entry(payload.narrative, payload.subject.value)
    competency = analysis["competency"]

    # The resident's choice wins over the AI's, but only within their own subject —
    # the same rule the axes follow: the system never files a case against something
    # it did not offer.
    if payload.competency_id:
        chosen = await catalogue.by_slug(payload.competency_id)
        if chosen is None or chosen["subject"] != payload.subject.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "That competency is not one of this subject's",
            )
        competency = chosen

    parsed = analysis["parsed"]
    parse_edited = _apply_corrections(parsed, payload)
    patient = parsed.get("patient") or {}

    document = {
        "resident_id": ObjectId(resident["id"]),
        "professor_id": ObjectId(resident["professor_id"]) if resident.get("professor_id") else None,
        "subject": payload.subject.value,
        "narrative": payload.narrative.strip(),
        "role": payload.role.value,
        "competency_id": competency["id"] if competency else None,
        "competency_title": competency["title"] if competency else None,
        "confirmed": bool(payload.confirmed),
        "status": EntryStatus.LOGGED.value,
        "source": analysis["source"],
        "parse_edited": parse_edited,
        "diagnosis": (parsed.get("diagnosis") or {}).get("display"),
        "procedure": (parsed.get("procedure") or {}).get("display"),
        "patient_age": patient.get("age"),
        "patient_sex": patient.get("sex"),
        "parsed": parsed,
        "created_at": datetime.now(UTC),
    }

    result = await mongo.entries().insert_one(document)
    document["_id"] = result.inserted_id
    saved = _with_role_label(mongo.serialize(document))  # type: ignore[arg-type]

    # Have the shortlist ready before a professor ever opens the case. Only worth
    # it when there is a professor to see it.
    if document["professor_id"] is not None:
        background.add_task(_precompute_axis_hint, saved)

    return saved


@router.get("", response_model=EntryPage)
async def list_entries(
    user: CurrentUser,
    subject: str | None = None,
    entry_status: str | None = Query(default=None, alias="status"),
    resident_id: str | None = None,
    limit: int = Query(default=_settings.default_page_size, ge=1, le=_settings.max_page_size),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # Visibility is a query filter, so an entry outside the caller's scope is
    # never even read from the database.
    query = entry_filter_for(user)
    if subject:
        query["subject"] = subject
    if entry_status:
        query["status"] = entry_status
    if resident_id:
        query["resident_id"] = to_object_id(resident_id)

    collection = mongo.entries()
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
    items = [_with_role_label(mongo.serialize(document)) async for document in cursor]  # type: ignore[arg-type]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{entry_id}", response_model=EntryDetail)
async def get_entry(entry_id: str, user: CurrentUser) -> dict[str, Any]:
    query = entry_filter_for(user) | {"_id": to_object_id(entry_id)}
    entry = await mongo.entries().find_one(query)
    if entry is None:
        # Same response whether it is missing or simply not theirs.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return _with_role_label(mongo.serialize(entry))  # type: ignore[arg-type]
