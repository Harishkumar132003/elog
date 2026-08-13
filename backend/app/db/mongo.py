"""MongoDB connection and index management.

One Motor client is created at application start-up and shared by every request;
Motor pools connections internally, so creating a client per request would be
both slower and a socket leak.
"""

import asyncio
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ConfigurationError, PyMongoError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect(attempts: int = 3) -> None:
    """Connect and build indexes.

    `mongodb+srv://` needs a DNS SRV *and* TXT lookup before the client can be
    constructed at all, and a flaky local resolver turns that into a hard boot
    failure. Retry rather than die — the cluster is usually fine, the resolver isn't.
    """
    global _client, _db
    if _client is not None:
        return

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _client = AsyncIOMotorClient(
                _settings.mongo_uri,
                serverSelectionTimeoutMS=15_000,
                connectTimeoutMS=15_000,
                tz_aware=True,
            )
            _db = _client[_settings.mongo_db]
            await _client.admin.command("ping")
            await _ensure_indexes(_db)
            return
        except (ConfigurationError, PyMongoError) as exc:
            last = exc
            if _client is not None:
                _client.close()
            _client, _db = None, None
            logger.warning("Mongo connect attempt %s/%s failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(2 * attempt)

    raise RuntimeError(f"Could not connect to MongoDB after {attempts} attempts: {last}")


async def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
        _client, _db = None, None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Mongo is not connected — call connect() during lifespan")
    return _db


# --- collection accessors ------------------------------------------------
def users() -> AsyncIOMotorCollection:
    return get_db()["users"]


def cases() -> AsyncIOMotorCollection:
    """The shared clinical facts and the roster of who worked the case.

    One case, many logs: each participant's own account of it is an `entries`
    document carrying this case's `_id`.
    """
    return get_db()["cases"]


def entries() -> AsyncIOMotorCollection:
    """One participant's log. Still called `entries` because it is unchanged —
    every stage after it (certification, exercise, attempt) keys on `entry_id`."""
    return get_db()["entries"]


def certifications() -> AsyncIOMotorCollection:
    """Screen 3 — the professor's certified axes and the Critical item."""
    return get_db()["certifications"]


def exercises() -> AsyncIOMotorCollection:
    """Screen 4 — the generated question set for an entry."""
    return get_db()["exercises"]


def attempts() -> AsyncIOMotorCollection:
    """Screen 4 — the resident's answers and their marks."""
    return get_db()["attempts"]


def competencies() -> AsyncIOMotorCollection:
    """The competency spine, editable by a professor from Configuration."""
    return get_db()["competencies"]


def corti_templates() -> AsyncIOMotorCollection:
    return get_db()["corti_templates"]


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Idempotent — safe to run on every boot."""
    await db["users"].create_index([("email", ASCENDING)], unique=True)
    await db["users"].create_index([("professor_id", ASCENDING)])

    # The two read patterns: a resident's own logbook, and a professor's queue.
    await db["entries"].create_index([("resident_id", ASCENDING), ("created_at", DESCENDING)])
    await db["entries"].create_index([("professor_id", ASCENDING), ("created_at", DESCENDING)])
    await db["entries"].create_index([("competency_id", ASCENDING)])

    # A case lists by who was in it; its logs read together, in role order.
    await db["cases"].create_index([("participants.user_id", ASCENDING), ("created_at", DESCENDING)])
    await db["entries"].create_index([("case_id", ASCENDING)])
    # One log per participant per case. Partial, because entries predating cases
    # have no `case_id` and would otherwise all collide on null.
    await db["entries"].create_index(
        [("case_id", ASCENDING), ("resident_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"case_id": {"$exists": True}},
    )

    # One certification and one exercise per entry; many attempts.
    await db["certifications"].create_index([("entry_id", ASCENDING)], unique=True)
    await db["exercises"].create_index([("entry_id", ASCENDING)], unique=True)
    await db["attempts"].create_index([("entry_id", ASCENDING), ("created_at", DESCENDING)])
    await db["attempts"].create_index([("resident_id", ASCENDING)])

    await db["corti_templates"].create_index([("key", ASCENDING)], unique=True)

    # The catalogue: `slug` is the public id entries already store, so it must be
    # unique; the compound index serves the only read there is — one subject's
    # live rows, in order.
    await db["competencies"].create_index([("slug", ASCENDING)], unique=True)
    await db["competencies"].create_index(
        [("subject", ASCENDING), ("archived", ASCENDING), ("order", ASCENDING)]
    )

    # `competency_code` was indexed but never written; the field is `competency_id`.
    # Dropping it costs one write-path lookup per entry insert.
    try:
        await db["entries"].drop_index("competency_code_1")
    except PyMongoError:
        pass  # already gone, which is the steady state


def serialize(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mongo `_id` → JSON-safe `id`."""
    if document is None:
        return None
    out = dict(document)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    for key in ("resident_id", "professor_id", "entry_id", "exercise_id", "case_id", "created_by"):
        if out.get(key) is not None:
            out[key] = str(out[key])
    return out
