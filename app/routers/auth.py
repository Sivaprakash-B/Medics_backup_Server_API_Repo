"""
/auth — login and token issuance.
Supports fallback guest token if no users table exists in connected schema.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import verify_password, create_access_token
from ..database import engine, get_db

logger = logging.getLogger("audit")
router = APIRouter(prefix="/auth", tags=["auth"])


USER_ALLOWED_TABLES = {
    "guest": ["*"],
    "admin": ["*"],
    "medics": ["*"],
    "user1": ["rpt_surgery", "rpt_patient_details"],
    "user2": ["rpt_surgery"],
}

USER_PASSWORDS = {
    "guest": ["guest", "", "guest123"],
    "admin": ["admin", "AdminPass123!", "admin123", "password", ""],
    "medics": ["medics", "Medics@123", "medics123"],
    "user1": ["user1", "User1Pass123!", "user123"],
    "user2": ["user2", "User2Pass123!", "user123"],
}


def has_users_table() -> bool:
    """Check if 'users' table exists in the connected database schema."""
    inspector = inspect(engine)
    return "users" in inspector.get_table_names()


@router.post("/token", response_model=schemas.Token)
def login(form: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with username + password, receive a JWT with table-level permissions."""
    username = (form.username or "guest").strip().lower()
    provided_password = (form.password or "").strip()
    
    if not has_users_table():
        # Validate predefined accounts when database has no writable 'users' table
        valid_passwords = USER_PASSWORDS.get(username, [username])
        if isinstance(valid_passwords, str):
            valid_passwords = [valid_passwords]

        # If password is provided and not in valid passwords list (and not matching username)
        if provided_password and provided_password not in valid_passwords and provided_password != username:
            logger.warning("LOGIN FAILED  user=%s", username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )
        
        allowed_tables = USER_ALLOWED_TABLES.get(username, ["*"])
        role = "admin" if username in ("admin", "medics") else "viewer"
        logger.info("LOGIN OK (Read-Only DB)  user=%s  role=%s  allowed_tables=%s", username, role, allowed_tables)
        token = create_access_token({"sub": username, "role": role, "allowed_tables": allowed_tables})
        return {"access_token": token, "token_type": "bearer"}

    user = (
        db.query(models.User)
        .filter(models.User.username == form.username)
        .first()
    )
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("LOGIN FAILED  user=%s", form.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    allowed_tables = USER_ALLOWED_TABLES.get(user.username.lower(), ["*"])
    token = create_access_token({"sub": user.username, "role": user.role, "allowed_tables": allowed_tables})
    logger.info("LOGIN OK  user=%s  role=%s  allowed_tables=%s", user.username, user.role, allowed_tables)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/guest-token", response_model=schemas.Token)
def guest_token():
    """Issue a read-only guest token for instant schema browsing."""
    token = create_access_token({"sub": "guest", "role": "viewer", "allowed_tables": ["*"]})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/users-list")
def list_managed_users():
    """List all accounts and their table access permissions."""
    result = []
    for uname, tables in USER_ALLOWED_TABLES.items():
        result.append({
            "username": uname,
            "role": "admin" if uname == "admin" else "viewer",
            "allowed_tables": tables,
        })
    return {"users": result}


@router.post("/add-user")
def add_user(payload: schemas.AddUserPayload):
    """Add or update a user with table access permissions dynamically."""
    uname = payload.username.strip().lower()
    USER_ALLOWED_TABLES[uname] = payload.allowed_tables
    if payload.password and payload.password.strip():
        USER_PASSWORDS[uname] = payload.password.strip()
    elif uname not in USER_PASSWORDS:
        USER_PASSWORDS[uname] = uname

    logger.info("USER ADDED/UPDATED  username=%s  allowed_tables=%s", uname, payload.allowed_tables)
    return {
        "status": "success",
        "message": f"User '{uname}' registered successfully",
        "user": {
            "username": uname,
            "role": payload.role,
            "allowed_tables": payload.allowed_tables,
        }
    }


@router.delete("/delete-user/{username}")
def delete_user(username: str):
    """Delete a user account."""
    uname = username.strip().lower()
    if uname in ("admin", "guest"):
        raise HTTPException(status_code=400, detail="Cannot delete default admin or guest accounts")
    if uname in USER_ALLOWED_TABLES:
        del USER_ALLOWED_TABLES[uname]
        USER_PASSWORDS.pop(uname, None)
        return {"status": "success", "message": f"User '{uname}' deleted"}
    raise HTTPException(status_code=404, detail=f"User '{uname}' not found")
