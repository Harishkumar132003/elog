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

# Everyone who works a case: the four DOPS identities, i.e. everyone but the
# professor. The same dependency as CurrentResident, named for what it gates.
CurrentParticipant = CurrentResident


def entry_filter_for(user: dict[str, Any]) -> dict[str, Any]:
    """The only entries this user is allowed to see.

    A participant sees their own logs; the professor sees every log.

    The professor's half used to be `professor_id == them`, which was right when
    residents were assigned to a supervisor. There is one professor now, so that
    filter distinguishes nothing — and it silently orphaned every log written
    before the fixed identities existed, because those carry the id of a
    professor account nobody can sign in as any more.

    Still applied as a query filter rather than a post-fetch check, so a log
    outside the caller's scope is never loaded in the first place.
    """
    if user["role"] == Role.PROFESSOR.value:
        return {}
    return {"resident_id": ObjectId(user["id"])}


def case_filter_for(user: dict[str, Any]) -> dict[str, Any]:
    """The only cases this user is allowed to see.

    A professor sees every case; anyone else sees the cases they were in.

    This gates the *case* — its shared clinical facts and its roster. It does
    not gate the logs written against it: a participant reads only their own,
    which `list_logs` and the shaped roster enforce separately. Their account is
    what each of them is assessed on, so it does not travel sideways.
    """
    if user["role"] == Role.PROFESSOR.value:
        return {}
    return {"participants.user_id": ObjectId(user["id"])}
