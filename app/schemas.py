"""
Pydantic schemas for request validation and response serialization.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth ─────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: str
    role: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class AddUserPayload(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    password: Optional[str] = Field(None, max_length=128)
    role: str = Field(default="viewer")
    allowed_tables: list[str] = Field(default=["*"])


# ── Users ────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., max_length=255)          # use EmailStr if email-validator is installed
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="viewer", pattern=r"^(admin|editor|viewer)$")


class UserUpdate(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, pattern=r"^(admin|editor|viewer)$")
    is_active: Optional[int] = Field(None, ge=0, le=1)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Reports ──────────────────────────────────────────────────
class ReportCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: Optional[str] = Field(None, max_length=5000)


class ReportUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    body: Optional[str] = Field(None, max_length=5000)


class ReportOut(BaseModel):
    id: int
    title: str
    body: Optional[str] = None
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
