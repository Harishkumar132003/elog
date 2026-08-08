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
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()


def _public(user: dict[str, Any]) -> dict[str, Any]:
    """Strip the hash before a user document ever leaves the process."""
    return {
        "id": str(user.get("id") or user.get("_id")),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
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
