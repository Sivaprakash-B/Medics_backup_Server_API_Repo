"""
/api/v1/system — admin dashboard endpoints for system stats,
schema introspection, and audit log viewing.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import engine, get_db

logger = logging.getLogger("audit")
router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/stats")
def system_stats(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return summary statistics for the dashboard."""
    from ..config import settings

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # Dynamic row count calculation across tables
    table_count = len(tables)

    user_count = 0
    if "users" in tables:
        try:
            user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        except Exception:
            pass
    elif "u_staff_m" in tables:
        try:
            user_count = db.execute(text("SELECT COUNT(*) FROM u_staff_m")).scalar() or 0
        except Exception:
            pass

    report_count = 0
    if "reports" in tables:
        try:
            report_count = db.execute(text("SELECT COUNT(*) FROM reports")).scalar() or 0
        except Exception:
            pass
    else:
        # Count total tables starting with rpt_
        rpt_tables = [t for t in tables if t.startswith("rpt_")]
        report_count = len(rpt_tables)

    db_type = "SQLite" if settings.use_sqlite else "MySQL"

    return {
        "table_count": table_count,
        "user_count": user_count,
        "report_count": report_count,
        "audit_log_count": 0,
        "database_engine": db_type,
        "database_name": settings.db_name,
        "database_url_masked": settings.sqlite_path if settings.use_sqlite else f"{settings.db_host}:{settings.db_port}/{settings.db_name}",
        "tables": tables,
    }


@router.get("/schema")
def database_schema(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return the database schema — tables, columns, types, constraints."""
    from ..config import settings

    if not settings.use_sqlite:
        try:
            sql = text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION"
            )
            rows = db.execute(sql).fetchall()
            schema_map = {}
            for t_name, c_name, c_type, is_null, c_def, c_key in rows:
                if t_name not in schema_map:
                    schema_map[t_name] = []
                schema_map[t_name].append({
                    "name": c_name,
                    "type": str(c_type),
                    "nullable": is_null == "YES",
                    "default": str(c_def) if c_def else None,
                    "primary_key": c_key == "PRI",
                })
            return {"tables": [{"name": k, "columns": v} for k, v in schema_map.items()]}
        except Exception as e:
            logger.warning("Batch schema inspection failed: %s", e)

    inspector = inspect(engine)
    tables = []
    for table_name in inspector.get_table_names():
        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "default": str(col.get("default")) if col.get("default") else None,
                "primary_key": False,
            })
        pk = inspector.get_pk_constraint(table_name)
        pk_cols = pk.get("constrained_columns", []) if pk else []
        for c in columns:
            if c["name"] in pk_cols:
                c["primary_key"] = True

        tables.append({
            "name": table_name,
            "columns": columns,
        })
    return {"tables": tables}


@router.get("/audit-logs")
def audit_logs(
    user: dict = Depends(get_current_user),
):
    """Return audit log entries."""
    return []
