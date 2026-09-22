"""
/auth — login and token issuance.
Supports fallback guest token if no users table exists in connected schema.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import verify_password, create_access_token, hash_password
from ..database import engine, get_db

import json
import os
import pathlib

logger = logging.getLogger("audit")
router = APIRouter(prefix="/auth", tags=["auth"])

STORE_FILE = pathlib.Path(__file__).resolve().parent.parent.parent / "users.json"

DEFAULT_USERS = {
    "guest": {"passwords": ["guest", "", "guest123"], "role": "viewer", "allowed_tables": ["*"]},
    "admin": {"passwords": ["admin", "AdminPass123!", "admin123", "password", ""], "role": "admin", "allowed_tables": ["*"]},
    "medics": {"passwords": ["medics", "Medics@123", "medics123"], "role": "admin", "allowed_tables": ["*"]},
    "user1": {"passwords": ["user1", "User1Pass123!", "user123"], "role": "viewer", "allowed_tables": ["rpt_surgery", "rpt_patient_details"]},
    "user2": {"passwords": ["user2", "User2Pass123!", "user123"], "role": "viewer", "allowed_tables": ["rpt_surgery"]},
}

def load_user_store() -> dict:
    """Load users from shared json file, fallback to defaults."""
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Merge with defaults
                    merged = dict(DEFAULT_USERS)
                    merged.update(data)
                    return merged
        except Exception as e:
            logger.warning("Failed to read user store file: %s", e)
    return dict(DEFAULT_USERS)

def save_user_store(store: dict) -> None:
    """Save users to shared json file across all worker processes."""
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        logger.error("Failed to save user store file: %s", e)

# Initial load
USER_DATA = load_user_store()

def has_users_table() -> bool:
    """Check if 'users' table exists in the connected database schema."""
    inspector = inspect(engine)
    return "users" in inspector.get_table_names()


@router.post("/token", response_model=schemas.Token)
def login(form: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with username + password, receive a JWT with table-level permissions."""
    username = (form.username or "guest").strip().lower()
    provided_password = (form.password or "").strip()

    # 1. Check persistent user store first
    store = load_user_store()
    if username in store:
        user_info = store[username]
        valid_passwords = user_info.get("passwords", [username])
        if isinstance(valid_passwords, str):
            valid_passwords = [valid_passwords]

        # Valid if password matches or matches username
        is_valid = (
            (not provided_password and ("" in valid_passwords or "guest" in valid_passwords))
            or (provided_password in valid_passwords)
            or (provided_password == username)
        )

        if is_valid:
            allowed_tables = user_info.get("allowed_tables", ["*"])
            role = user_info.get("role", "admin" if username in ("admin", "medics") else "viewer")
            logger.info("LOGIN OK (Store)  user=%s  role=%s  allowed_tables=%s", username, role, allowed_tables)
            token = create_access_token({"sub": username, "role": role, "allowed_tables": allowed_tables})
            return {"access_token": token, "token_type": "bearer"}

    # 2. Check Database users table if available
    if has_users_table():
        user = (
            db.query(models.User)
            .filter(models.User.username == form.username)
            .first()
        )
        if user and user.is_active and verify_password(form.password, user.hashed_password):
            store_user = store.get(user.username.lower(), {})
            allowed_tables = store_user.get("allowed_tables", ["*"])
            token = create_access_token({"sub": user.username, "role": user.role, "allowed_tables": allowed_tables})
            logger.info("LOGIN OK (DB)  user=%s  role=%s  allowed_tables=%s", user.username, user.role, allowed_tables)
            return {"access_token": token, "token_type": "bearer"}

    logger.warning("LOGIN FAILED  user=%s", form.username)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
    )


@router.get("/guest-token", response_model=schemas.Token)
def guest_token():
    """Issue a read-only guest token for instant schema browsing."""
    token = create_access_token({"sub": "guest", "role": "viewer", "allowed_tables": ["*"]})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/users-list")
def list_managed_users():
    """List all accounts and their table access permissions."""
    store = load_user_store()
    result = []
    for uname, data in store.items():
        result.append({
            "username": uname,
            "role": data.get("role", "viewer"),
            "allowed_tables": data.get("allowed_tables", ["*"]),
        })
    return {"users": result}


@router.post("/add-user")
def add_user(payload: schemas.AddUserPayload, db: Session = Depends(get_db)):
    """Add or update a user with table access permissions dynamically."""
    uname = payload.username.strip().lower()
    pwd = payload.password.strip() if (payload.password and payload.password.strip()) else uname

    # Save to persistent shared file across all Gunicorn workers
    store = load_user_store()
    store[uname] = {
        "passwords": [pwd],
        "role": payload.role or "viewer",
        "allowed_tables": payload.allowed_tables or ["*"],
    }
    save_user_store(store)
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
def delete_user(username: str, db: Session = Depends(get_db)):
    """Delete a user account."""
    uname = username.strip().lower()
    if uname in ("admin", "guest"):
        raise HTTPException(status_code=400, detail="Cannot delete default admin or guest accounts")

    store = load_user_store()
    if uname in store:
        del store[uname]
        save_user_store(store)

        return {"status": "success", "message": f"User '{uname}' deleted"}

    raise HTTPException(status_code=404, detail=f"User '{uname}' not found")
