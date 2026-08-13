from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=120)
    role: Role = Role.RESIDENT
    # Residents must belong to a professor; ignored when role is professor.
    professor_id: str | None = None
    department: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1, le=6)


class SwitchRequest(BaseModel):
    """Become one of the five fixed identities. No password — there is no sign-in."""

    role: str = Field(min_length=1, max_length=40)


class IdentityOut(BaseModel):
    key: str
    name: str
    role: Role
    # None for the professor, who never works a case.
    dops_role: str | None = None


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: Role
    # Which of the five they are. Drives what a participant may do on a case.
    dops_role: str | None = None
    professor_id: str | None = None
    department: str | None = None
    year: int | None = None
    created_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
