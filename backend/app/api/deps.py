"""Shared request dependencies: authentication and role gating."""

from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.constants import Role
from app.core.security import decode_access_token
from app.db import mongo

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed id") from None


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise _UNAUTHORIZED

    claims = decode_access_token(credentials.credentials)
    if not claims or "sub" not in claims:
        raise _UNAUTHORIZED

    try:
        user = await mongo.users().find_one({"_id": ObjectId(claims["sub"])})
    except (InvalidId, TypeError):
        raise _UNAUTHORIZED from None
    if user is None:
        raise _UNAUTHORIZED

    return mongo.serialize(user)  # type: ignore[return-value]


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


def require_role(*allowed: Role):
    """Gate an endpoint to specific roles."""

    async def dependency(user: CurrentUser) -> dict[str, Any]:
        if user.get("role") not in {role.value for role in allowed}:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires role: {', '.join(role.value for role in allowed)}",
            )
        return user

    return dependency


CurrentResident = Annotated[dict[str, Any], Depends(require_role(Role.RESIDENT))]
CurrentProfessor = Annotated[dict[str, Any], Depends(require_role(Role.PROFESSOR))]


def entry_filter_for(user: dict[str, Any]) -> dict[str, Any]:
    """The only entries this user is allowed to see.

    A resident sees their own; a professor sees those of the residents they own.
    Applied as a query filter rather than a post-fetch check, so an unauthorised
    document is never loaded in the first place.
    """
    if user["role"] == Role.PROFESSOR.value:
        return {"professor_id": ObjectId(user["id"])}
    return {"resident_id": ObjectId(user["id"])}
