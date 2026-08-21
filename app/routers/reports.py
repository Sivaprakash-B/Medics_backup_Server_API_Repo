"""
/reports — CRUD endpoints for reports.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, require_role
from ..database import get_db

logger = logging.getLogger("audit")
router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/", response_model=list[schemas.ReportOut])
def list_reports(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all reports (any authenticated user)."""
    return db.query(models.Report).offset(skip).limit(limit).all()


@router.get("/{report_id}", response_model=schemas.ReportOut)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/", response_model=schemas.ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: schemas.ReportCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "editor")),
):
    """Create a report (admin or editor)."""
    db_obj = models.Report(
        title=payload.title,
        body=payload.body,
        created_by=user.get("sub", "unknown"),
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)

    logger.info("REPORT CREATED  by=%s  id=%s", user.get("sub"), db_obj.id)
    return db_obj


@router.patch("/{report_id}", response_model=schemas.ReportOut)
def update_report(
    report_id: int,
    payload: schemas.ReportUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "editor")),
):
    """Update a report (admin or editor)."""
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(report, key, value)

    db.commit()
    db.refresh(report)

    logger.info(
        "REPORT UPDATED  by=%s  id=%s  fields=%s",
        user.get("sub"),
        report.id,
        list(update_data.keys()),
    )
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Delete a report (admin only)."""
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    logger.info("REPORT DELETED  by=%s  id=%s", user.get("sub"), report.id)
    db.delete(report)
    db.commit()
