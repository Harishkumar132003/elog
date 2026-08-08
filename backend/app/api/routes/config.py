"""Configuration — the professor's competency catalogue.

The catalogue is global: one spine shared by every professor, as agreed, with an
admin role to come. Every write records who made it so a shared edit is at least
attributable before there is a role to restrict it.

Saving is whole-subject rather than row-by-row. The screen holds a list the
professor has been editing; sending it back complete lets the server work out what
was added, changed and removed in one request, and there is no window where half
the edits have landed.

Importing a PDF takes minutes, so it follows the same shape as question generation
in `flow.py`: the request returns a job id immediately and the browser polls.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import CurrentProfessor
from app.core.constants import Subject
from app.db import mongo
from app.schemas.config import (
    CompetencyList,
    CompetencySave,
    ImportJob,
    ImportStarted,
    SaveResult,
)
from app.services import catalogue, competency_import, import_jobs
from app.services.competency_import import ImportError_
from app.services.corti_templates import ensure_template, parse_template

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)


async def _reprovision(subject: str) -> None:
    """Rebuild the subject's Corti parse template after a catalogue change.

    The template's competency enum is the catalogue, so an edit invalidates it. It
    would re-provision itself on the next parse anyway — this just moves the seven
    HTTP calls off the next resident to press Analyse.
    """
    try:
        await ensure_template(parse_template(subject))
    except Exception:
        logger.exception("Could not re-provision the parse template for %s", subject)


@router.get("/competencies", response_model=CompetencyList)
async def list_competencies(
    professor: CurrentProfessor,
    subject: Annotated[Subject, Query()],
) -> dict[str, Any]:
    items = await catalogue.list_for(subject.value)

    # Who last touched this subject, so a shared catalogue shows its last editor.
    latest = await mongo.competencies().find_one(
        {"subject": subject.value, "updated_at": {"$ne": None}}, sort=[("updated_at", -1)]
    )
    editor = None
    if latest and latest.get("updated_by"):
        user = await mongo.users().find_one({"_id": latest["updated_by"]}, {"name": 1})
        editor = user["name"] if user else None

    return {
        "subject": subject.value,
        "items": items,
        "updated_at": latest.get("updated_at") if latest else None,
        "updated_by": editor,
    }


@router.put("/competencies", response_model=SaveResult)
async def save_competencies(
    payload: CompetencySave,
    professor: CurrentProfessor,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Save one subject's catalogue whole: insert, update and archive in one pass."""
    subject = payload.subject.value
    now = datetime.now(UTC)
    editor = ObjectId(professor["id"])
    collection = mongo.competencies()

    existing: dict[str, dict[str, Any]] = {}
    # A title the professor removed and then re-added should come back as the row
    # it was, not as a new one — otherwise entries logged against it stay orphaned
    # from a competency that is visibly on the list again.
    archived_by_title: dict[str, dict[str, Any]] = {}
    async for document in collection.find({"subject": subject}):
        if document.get("archived"):
            archived_by_title.setdefault(
                competency_import.dedupe_key(document["title"]), document
            )
        else:
            existing[document["slug"]] = document

    # Slugs are unique across the whole catalogue, not just this subject.
    taken = {document["slug"] async for document in collection.find({}, {"slug": 1})}

    titles = [item.title.strip() for item in payload.items]
    if any(not title for title in titles):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A competency cannot be blank")

    seen_keys: set[str] = set()
    added = updated = 0
    kept: set[str] = set()

    for order, item in enumerate(payload.items):
        title = item.title.strip()

        # Two identical rows would give the AI an impossible choice between them.
        key = competency_import.dedupe_key(title)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        current = existing.get(item.id) if item.id else None
        if current is not None:
            kept.add(current["slug"])
            changes: dict[str, Any] = {"order": order}
            if current["title"] != title:
                changes |= {"title": title, "updated_at": now, "updated_by": editor}
                updated += 1
            await collection.update_one({"_id": current["_id"]}, {"$set": changes})
            continue

        revived = archived_by_title.get(key)
        if revived is not None:
            await collection.update_one(
                {"_id": revived["_id"]},
                {
                    "$set": {
                        "archived": False,
                        "title": title,
                        "order": order,
                        "updated_at": now,
                        "updated_by": editor,
                    }
                },
            )
            kept.add(revived["slug"])
            added += 1
            continue

        slug = catalogue.slugify(subject, title, taken)
        await collection.insert_one(
            {
                "slug": slug,
                "subject": subject,
                "title": title,
                "logs": catalogue.LOGS_BY_SUBJECT.get(subject, catalogue.DEFAULT_LOGS),
                "archived": False,
                "source": item.source or "manual",
                "order": order,
                "created_at": now,
                "updated_at": now,
                "updated_by": editor,
            }
        )
        kept.add(slug)
        added += 1

    # Anything the professor dropped is archived, never deleted: entries logged
    # against it keep resolving, and the dashboard keeps its history.
    gone = [slug for slug in existing if slug not in kept]
    if gone:
        await collection.update_many(
            {"slug": {"$in": gone}},
            {"$set": {"archived": True, "updated_at": now, "updated_by": editor}},
        )

    catalogue.invalidate(subject)
    background.add_task(_reprovision, subject)

    return {
        "subject": subject,
        "added": added,
        "updated": updated,
        "removed": len(gone),
        "items": await catalogue.list_for(subject),
    }


# --- PDF import -----------------------------------------------------------
async def _run_import(job_id: str, subject: str, text: str) -> None:
    """Extract in the background, recording progress the browser can poll."""

    async def progress(done: int, total: int) -> None:
        import_jobs.update(job_id, done=done, total=total)

    try:
        known = {
            competency_import.dedupe_key(item["title"])
            for item in await catalogue.list_for(subject)
        }
        found, truncated = await competency_import.extract(text, known, progress)
        import_jobs.update(job_id, status="done", found=found, truncated=truncated)
    except Exception as exc:
        logger.exception("Competency import failed for job %s", job_id)
        import_jobs.update(
            job_id, status="failed", error=f"The import did not finish: {exc}"
        )


@router.post("/competencies/import", response_model=ImportStarted, status_code=status.HTTP_202_ACCEPTED)
async def import_competencies(
    professor: CurrentProfessor,
    background: BackgroundTasks,
    subject: Annotated[Subject, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Start reading a curriculum PDF for one subject.

    The text is extracted here, synchronously, because it takes milliseconds and a
    bad upload should fail loudly at the point of upload rather than inside a job.
    The AI pass is what runs in the background.
    """
    data = await file.read()
    try:
        text, pages_read, pages_total = competency_import.read_pdf_text(data)
    except ImportError_ as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    finally:
        # The PDF is not ours to keep — only the text it contained is used.
        del data

    chunks, _ = competency_import.chunk(text)
    job_id = import_jobs.create(
        professor_id=professor["id"],
        subject=subject.value,
        filename=file.filename,
        total=len(chunks),
        pages_read=pages_read,
        pages_total=pages_total,
    )
    background.add_task(_run_import, job_id, subject.value, text)

    return {
        "job_id": job_id,
        "pages_read": pages_read,
        "pages_total": pages_total,
        "chunks": len(chunks),
    }


@router.get("/competencies/import/{job_id}", response_model=ImportJob)
async def get_import(job_id: str, professor: CurrentProfessor) -> dict[str, Any]:
    job = import_jobs.get(job_id, professor["id"])
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That import is no longer available")
    return job
