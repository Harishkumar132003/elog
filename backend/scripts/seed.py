"""Seed demo accounts: one professor supervising three residents.

Idempotent — re-running updates the existing accounts rather than duplicating.

    cd backend && .venv/bin/python -m scripts.seed
"""

import asyncio
from datetime import UTC, datetime

from app.core.constants import Role, Subject
from app.core.security import hash_password
from app.db import mongo

DEMO_PASSWORD = "opbook360"

PROFESSOR = {
    "email": "prof.rao@opbook360.ai",
    "name": "Dr. S. Rao",
    "department": Subject.ORTHOPAEDICS.value,
}

RESIDENTS = [
    {"email": "resident@opbook360.ai", "name": "Dr. A. Resident", "year": 2,
     "department": Subject.ORTHOPAEDICS.value},
    {"email": "n.menon@opbook360.ai", "name": "Dr. N. Menon", "year": 3,
     "department": Subject.GENERAL_SURGERY.value},
    {"email": "k.iyer@opbook360.ai", "name": "Dr. K. Iyer", "year": 1,
     "department": Subject.PATHOLOGY.value},
]


async def upsert(document: dict) -> str:
    """Insert or update by email; never rewrite an existing password hash."""
    email = document["email"]
    await mongo.users().update_one(
        {"email": email},
        {
            "$set": {k: v for k, v in document.items() if k != "password_hash"},
            "$setOnInsert": {
                "password_hash": document["password_hash"],
                "created_at": datetime.now(UTC),
            },
        },
        upsert=True,
    )
    user = await mongo.users().find_one({"email": email}, {"_id": 1})
    return str(user["_id"])


async def main() -> None:
    await mongo.connect()
    try:
        professor_id = await upsert(
            {
                **PROFESSOR,
                "role": Role.PROFESSOR.value,
                "professor_id": None,
                "year": None,
                "password_hash": hash_password(DEMO_PASSWORD),
            }
        )
        print(f"professor  {PROFESSOR['email']:<28} {professor_id}")

        from bson import ObjectId

        for resident in RESIDENTS:
            resident_id = await upsert(
                {
                    **resident,
                    "role": Role.RESIDENT.value,
                    "professor_id": ObjectId(professor_id),
                    "password_hash": hash_password(DEMO_PASSWORD),
                }
            )
            print(f"resident   {resident['email']:<28} {resident_id}")

        print(f"\npassword for every demo account: {DEMO_PASSWORD}")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
