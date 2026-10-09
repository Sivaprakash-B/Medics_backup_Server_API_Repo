"""
JWT authentication + role-based access control (RBAC).
Uses bcrypt directly for password hashing (passlib has compatibility
issues with newer bcrypt versions).
"""

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import settings

logger = logging.getLogger("audit")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ── Password helpers ─────────────────────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT helpers ──────────────────────────────────────────────
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    if settings.access_token_expire_minutes > 0:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
        to_encode.update({"exp": expire})
    # When access_token_expire_minutes is 0, no "exp" claim → token never expires
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# ── Dependencies ─────────────────────────────────────────────
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode JWT and return the payload (username, role, …)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


def require_role(*roles: str):
    """Return a dependency that enforces the caller has one of the listed roles."""

    def checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            logger.warning(
                "ACCESS DENIED  user=%s  required_roles=%s  actual_role=%s",
                user.get("sub"),
                roles,
                user.get("role"),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


def check_table_access(user: dict, table_name: str):
    """Verify if user has permission to access the requested table."""
    allowed = user.get("allowed_tables", ["*"])
    if "*" in allowed or table_name in allowed:
        return True

    logger.warning(
        "TABLE ACCESS DENIED  user=%s  requested_table=%s  allowed_tables=%s",
        user.get("sub"),
        table_name,
        allowed,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied: Account '{user.get('sub')}' is not authorized to access table '{table_name}'. Allowed tables: {allowed}",
    )
