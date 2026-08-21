"""
/users — CRUD endpoints for user management.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, require_role, hash_password
from ..database import get_db

logger = logging.getLogger("audit")
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[schemas.UserOut])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all users (any authenticated user)."""
    return db.query(models.User).offset(skip).limit(limit).all()


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.post("/", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Create a new user (admin only)."""
    # Check uniqueness
    exists = (
        db.query(models.User)
        .filter(
            (models.User.username == payload.username)
            | (models.User.email == payload.email)
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Username or email already exists")

    db_obj = models.User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)

    logger.info(
        "USER CREATED  by=%s  new_user=%s  role=%s",
        user.get("sub"),
        db_obj.username,
        db_obj.role,
    )
    return db_obj


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Update user fields (admin only)."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.commit()
    db.refresh(db_user)

    logger.info(
        "USER UPDATED  by=%s  target=%s  fields=%s",
        user.get("sub"),
        db_user.username,
        list(update_data.keys()),
    )
    return db_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Delete a user (admin only)."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(
        "USER DELETED  by=%s  target=%s", user.get("sub"), db_user.username
    )
    db.delete(db_user)
    db.commit()
