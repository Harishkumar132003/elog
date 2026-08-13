"""The five fixed identities this system is demonstrated with.

There is no sign-in: a reviewer picks who they are from the header and the app
becomes that person. So the "accounts" are not accounts in any real sense — they
are the roles themselves, one user per role, name and role the same string.

Seeded on every boot and idempotent: matched on `identity_key`, not on email.
The email is a derived, cosmetic address here — matching on it would mean any
change to the domain silently created a second set of users rather than renaming
the first.

Real sign-in is not removed, only unused — `/auth/login` and `/auth/register`
still work. Turning `demo_identities` off closes the switch endpoint and leaves
them as the only way in.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.constants import DopsRole, Role
from app.core.security import hash_password
from app.db import mongo

logger = logging.getLogger(__name__)

# The professor is not a DOPS role — they never work a case, they set the
# questions — so their key is the app role instead.
PROFESSOR_KEY = Role.PROFESSOR.value

# Who can create a case and log against one: everyone except the professor.
PARTICIPANT_ROLES: tuple[DopsRole, ...] = (
    DopsRole.OBSERVED,
    DopsRole.SUPERVISED,
    DopsRole.INDEPENDENT,
    DopsRole.SUPERVISOR,
)

# key -> (display name, app role, dops role). The key is what the header sends.
IDENTITIES: dict[str, tuple[str, Role, DopsRole | None]] = {
    DopsRole.OBSERVED.value: ("Observer", Role.RESIDENT, DopsRole.OBSERVED),
    DopsRole.SUPERVISED.value: (
        "Performer with supervision",
        Role.RESIDENT,
        DopsRole.SUPERVISED,
    ),
    DopsRole.INDEPENDENT.value: ("Independent performer", Role.RESIDENT, DopsRole.INDEPENDENT),
    DopsRole.SUPERVISOR.value: ("Supervisor", Role.RESIDENT, DopsRole.SUPERVISOR),
    PROFESSOR_KEY: ("Professor", Role.PROFESSOR, None),
}

# Where a reviewer lands with no token at all. A participant rather than the
# professor, because the flow starts by creating a case.
DEFAULT_IDENTITY = DopsRole.INDEPENDENT.value

# Nobody receives mail here, but `UserPublic.email` is an `EmailStr` and the
# validator rejects the reserved TLDs (.local, .test, .example), so this has to
# be a domain that could in principle exist.
_DOMAIN = "demo.opbook360.ai"


def email_for(key: str) -> str:
    return f"{key}@{_DOMAIN}"


async def seed() -> None:
    """Create any missing identity. Safe to call on every boot."""
    professor_id = await _upsert(PROFESSOR_KEY, professor_id=None)
    for key in IDENTITIES:
        if key != PROFESSOR_KEY:
            await _upsert(key, professor_id=professor_id)


async def _upsert(key: str, professor_id: Any) -> Any:
    name, role, dops_role = IDENTITIES[key]
    email = email_for(key)

    existing = await mongo.users().find_one({"identity_key": key}, {"_id": 1})
    if existing is not None:
        # Keep the mutable half current without touching the id anything already
        # points at — cases and logs reference these users by _id.
        await mongo.users().update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "email": email,
                    "name": name,
                    "role": role.value,
                    "dops_role": dops_role.value if dops_role else None,
                    "professor_id": professor_id,
                }
            },
        )
        return existing["_id"]

    result = await mongo.users().insert_one(
        {
            "email": email,
            "name": name,
            # Nothing signs in as these, but the field is not nullable elsewhere
            # and an unusable hash is safer than an empty one.
            "password_hash": hash_password(f"disabled-{key}"),
            "role": role.value,
            "dops_role": dops_role.value if dops_role else None,
            "identity_key": key,
            "professor_id": professor_id,
            "department": "Demonstration",
            "year": None,
            "created_at": datetime.now(UTC),
        }
    )
    logger.info("Seeded identity %s", key)
    return result.inserted_id


async def by_key(key: str) -> dict[str, Any] | None:
    if key not in IDENTITIES:
        return None
    return await mongo.users().find_one({"identity_key": key})


def listing() -> list[dict[str, Any]]:
    """The header's dropdown, in the order it should read."""
    return [
        {
            "key": key,
            "name": name,
            "role": role.value,
            "dops_role": dops_role.value if dops_role else None,
        }
        for key, (name, role, dops_role) in IDENTITIES.items()
    ]
