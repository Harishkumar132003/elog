from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.deps import CurrentProfessor, CurrentUser, to_object_id
from app.core.config import get_settings
from app.core.constants import Role
from app.core.security import create_access_token, hash_password, verify_password
from app.db import mongo
from app.schemas.auth import (
    IdentityOut,
    LoginRequest,
    RegisterRequest,
    SwitchRequest,
    TokenResponse,
    UserPublic,
)
from app.services import people

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()


def _public(user: dict[str, Any]) -> dict[str, Any]:
    """Strip the hash before a user document ever leaves the process."""
    return {
        "id": str(user.get("id") or user.get("_id")),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "dops_role": user.get("dops_role"),
        "professor_id": str(user["professor_id"]) if user.get("professor_id") else None,
        "department": user.get("department"),
        "year": user.get("year"),
        "created_at": user.get("created_at"),
    }


def _token_for(user: dict[str, Any]) -> dict[str, Any]:
    public = _public(user)
    return {
        "access_token": create_access_token(public["id"], public["role"]),
        "token_type": "bearer",
        "expires_in": _settings.jwt_ttl_minutes * 60,
        "user": public,
    }


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> dict[str, Any]:
    professor_id: ObjectId | None = None

    if payload.role is Role.RESIDENT:
        if not payload.professor_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A resident must be assigned to a professor",
            )
        professor_id = to_object_id(payload.professor_id)
        supervisor = await mongo.users().find_one(
            {"_id": professor_id, "role": Role.PROFESSOR.value}
        )
        if supervisor is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown professor")

    document = {
        "email": payload.email.lower(),
        "name": payload.name,
        "password_hash": hash_password(payload.password),
        "role": payload.role.value,
        "professor_id": professor_id,
        "department": payload.department,
        "year": payload.year,
        "created_at": datetime.now(UTC),
    }

    try:
        result = await mongo.users().insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists"
        ) from None

    document["_id"] = result.inserted_id
    return _token_for(document)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> dict[str, Any]:
    user = await mongo.users().find_one({"email": payload.email.lower()})
    # Same error either way — never reveal whether an email exists.
    if user is None or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return _token_for(user)


def _demo_only() -> None:
    if not _settings.demo_identities:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Identity switching is not enabled on this deployment"
        )


@router.get("/identities", response_model=list[IdentityOut])
async def list_identities() -> list[dict[str, Any]]:
    """The header's dropdown. Unauthenticated — it is what you use to get a token."""
    _demo_only()
    return people.listing()


@router.post("/switch", response_model=TokenResponse)
async def switch(payload: SwitchRequest) -> dict[str, Any]:
    """Become one of the five fixed identities.

    This is the whole of "signing in" here: name and role are the same thing, so
    choosing a role chooses the person. Deliberately unauthenticated — it is the
    entry point, and `demo_identities` is the gate.
    """
    _demo_only()
    user = await people.by_key(payload.role)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such identity: {payload.role}")
    return _token_for(user)


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> dict[str, Any]:
    return _public(user)


@router.get("/residents", response_model=list[UserPublic])
async def my_residents(professor: CurrentProfessor) -> list[dict[str, Any]]:
    """The residents this professor supervises."""
    cursor = mongo.users().find(
        {"professor_id": ObjectId(professor["id"]), "role": Role.RESIDENT.value}
    ).sort("name", 1)
    return [_public(doc | {"id": str(doc["_id"])}) async for doc in cursor]
