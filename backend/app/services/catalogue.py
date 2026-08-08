"""The competency catalogue, read from MongoDB.

Until now the spine was a five-row Python tuple — one competency per subject, so
"which competency does this case log against?" had a single mechanical answer. A
real NMC curriculum has dozens per subject, and a professor loads their own from
Configuration. That makes the catalogue data rather than code.

`app/data/competencies.py` survives as the seed: a fresh database starts with the
five rows the specification names, keeping their original slugs so entries logged
before this change still resolve.

Every entry parse reads this, so it sits behind a short in-process TTL cache —
the same idiom as the parse memo in `ai.py`. Writes clear it outright rather than
waiting the TTL out, so a professor who saves the catalogue sees the effect on the
very next entry.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import UTC, datetime
from typing import Any

from app.core.constants import Subject
from app.data.competencies import CATALOGUE
from app.db import mongo

logger = logging.getLogger(__name__)

# The catalogue changes when a professor saves it — minutes apart at worst, never
# mid-request. A short TTL keeps parse latency off the database without making a
# save feel unapplied.
_TTL_SECONDS = 30.0
_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}

# A subject's competencies all log the same kind of thing, so `logs` is a property
# of the subject and is never asked per row.
LOGS_BY_SUBJECT: dict[str, str] = {item["subject"]: item["logs"] for item in CATALOGUE}
DEFAULT_LOGS = "A patient case"

# Slugs are what Corti is shown and what it returns, so they stay readable.
_SUBJECT_PREFIX: dict[str, str] = {
    Subject.GENERAL_SURGERY.value: "gs",
    Subject.ORTHOPAEDICS.value: "or",
    Subject.PATHOLOGY.value: "pa",
    Subject.FORENSIC_MEDICINE.value: "fm",
    Subject.PHYSIOLOGY.value: "py",
}

_SLUG_WORDS = 6


def _public(document: dict[str, Any]) -> dict[str, str]:
    """The shape every caller wants: the old catalogue dict, unchanged."""
    return {
        "id": document["slug"],
        "subject": document["subject"],
        "title": document["title"],
        "logs": document.get("logs") or LOGS_BY_SUBJECT.get(document["subject"], DEFAULT_LOGS),
    }


def slugify(subject: str, title: str, taken: set[str]) -> str:
    """A readable, stable id for a competency, unique within `taken`."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_title.lower())[:_SLUG_WORDS]
    stem = f"{_SUBJECT_PREFIX.get(subject, 'cx')}-{'-'.join(words) or 'competency'}"

    slug, suffix = stem, 2
    while slug in taken:
        slug = f"{stem}-{suffix}"
        suffix += 1
    taken.add(slug)
    return slug


def invalidate(subject: str | None = None) -> None:
    """Drop cached reads. Called by every write path."""
    if subject is None:
        _cache.clear()
    else:
        _cache.pop(subject, None)


async def list_for(subject: str) -> list[dict[str, str]]:
    """One subject's live competencies, in the professor's order."""
    hit = _cache.get(subject)
    if hit is not None and time.monotonic() - hit[0] <= _TTL_SECONDS:
        return hit[1]

    cursor = (
        mongo.competencies()
        .find({"subject": subject, "archived": {"$ne": True}})
        .sort([("order", 1), ("_id", 1)])
    )
    items = [_public(document) async for document in cursor]
    _cache[subject] = (time.monotonic(), items)
    return items


async def ids_for(subject: str) -> list[str]:
    """The slugs Corti is allowed to choose from for this subject."""
    return [item["id"] for item in await list_for(subject)]


async def by_slug(slug: str) -> dict[str, str] | None:
    """Resolve one competency, archived or not.

    Archived rows still resolve: an entry logged last month keeps pointing at the
    competency it was filed under, whether or not the professor has since removed
    it from the menu.
    """
    if not slug:
        return None
    document = await mongo.competencies().find_one({"slug": slug})
    return _public(document) if document else None


async def retired_with_slugs(subject: str, slugs: list[str]) -> list[dict[str, str]]:
    """Archived competencies from `slugs` — evidence logged against a removed row.

    A professor tidying the catalogue must not make a resident's logged cases
    disappear from the coverage panel. They stay, marked as retired.
    """
    if not slugs:
        return []
    cursor = mongo.competencies().find(
        {"subject": subject, "archived": True, "slug": {"$in": slugs}}
    )
    return [_public(document) async for document in cursor]


async def count_by_subject() -> dict[str, int]:
    """How many live competencies each subject has — for the subject picker."""
    rows = await mongo.competencies().aggregate(
        [
            {"$match": {"archived": {"$ne": True}}},
            {"$group": {"_id": "$subject", "n": {"$sum": 1}}},
        ]
    ).to_list(length=None)
    return {row["_id"]: row["n"] for row in rows}


async def seed_if_empty() -> int:
    """Plant the specification's five competencies in an empty catalogue.

    Slugs are carried over verbatim, so entries created before the catalogue moved
    into the database still resolve to the same competency.
    """
    if await mongo.competencies().count_documents({}, limit=1):
        return 0

    now = datetime.now(UTC)
    await mongo.competencies().insert_many(
        [
            {
                "slug": item["id"],
                "subject": item["subject"],
                "title": item["title"],
                "logs": item["logs"],
                "archived": False,
                "source": "seed",
                "order": index,
                "created_at": now,
                "updated_at": now,
                "updated_by": None,
            }
            for index, item in enumerate(CATALOGUE)
        ]
    )
    invalidate()
    logger.info("Seeded competency catalogue with %s rows", len(CATALOGUE))
    return len(CATALOGUE)
