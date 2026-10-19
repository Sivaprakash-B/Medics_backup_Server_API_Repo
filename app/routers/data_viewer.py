"""
/api/v1/tables & /api/v1/query - Dynamic read-only data viewer and SQL Query Engine.

Table names are NEVER exposed publicly.
Each table is assigned a numeric ID (1, 2, 3...) on first request.
All public URLs use the numeric ID only:  /api/v1/tables/3/data
"""

import logging
import re
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import MetaData, Table, select, func, text, literal_column, or_, cast, String, inspect
from sqlalchemy.orm import Session

from ..database import engine, get_db
from ..auth import get_current_user
from ..config import settings

logger = logging.getLogger("audit")
router = APIRouter(prefix="/api/v1", tags=["query-engine"])

metadata = MetaData()


# -- Numeric ID Registry -------------------------------------------------------
# Maps  integer_id  <->  real_table_name
# IDs are built once on first call and stay stable for the server lifetime.
# Real table names are NEVER returned to any API consumer.

_id_to_table: dict[int, str] = {}   # {1: "rpt_appointments", 2: "tbl_patient_master"}
_table_to_id: dict[str, int] = {}   # reverse lookup
_registry_built = False


def _build_registry() -> None:
    """Populate the numeric ID registry from live DB table list (idempotent)."""
    global _registry_built
    if _registry_built:
        return
    try:
        inspector = inspect(engine)
        real_names = sorted(inspector.get_table_names())   # sorted -> deterministic IDs
        for idx, name in enumerate(real_names, start=1):
            _id_to_table[idx] = name
            _table_to_id[name] = idx
        _registry_built = True
        logger.info("Table ID registry built: %d tables", len(_id_to_table))
    except Exception as e:
        logger.error("Failed to build table ID registry: %s", e)


def _resolve_id(table_id: int) -> str:
    """Resolve a public numeric ID -> real table name. Raises 404 if unknown."""
    _build_registry()
    real = _id_to_table.get(table_id)
    if not real:
        raise HTTPException(status_code=404, detail="Table not found")
    return real


class QueryRequest(BaseModel):
    sql: str


class TableFilterRequest(BaseModel):
    """Body for POST /api/v1/tables/{id}/query — filters stay off the URL."""
    where: Optional[str] = None
    search: Optional[str] = None
    order_by: Optional[str] = None
    skip: int = 0
    limit: Optional[int] = None


class TableSummaryRequest(BaseModel):
    """Body for POST /api/v1/tables/{id}/summary — returns counts, not rows."""
    where: Optional[str] = None
    group_by: Optional[str] = None   # e.g. "status" or "DATE(rs_sd_start_date)"


def reflect_table(table_name: str) -> Table:
    """Reflect table schema dynamically from engine."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if table_name not in tables:
        raise HTTPException(status_code=404, detail="Table not found in database schema")
    if table_name in metadata.tables:
        return metadata.tables[table_name]
    return Table(table_name, metadata, autoload_with=engine)


# -- Endpoints -----------------------------------------------------------------

@router.get("/tables")
def list_all_tables(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    List available tables with numeric IDs only.
    Real table names are NEVER returned.

    Response shape:
      { "tables": [ { "id": 1, "column_count": 12, "columns": [...] }, ... ] }
    """
    _build_registry()
    inspector = inspect(engine)
    all_real_names = inspector.get_table_names()

    raw_allowed = user.get("allowed_tables", ["*"])
    allowed = [str(t) for t in raw_allowed] if isinstance(raw_allowed, list) else ["*"]

    col_map: dict[str, list] = {}
    if not settings.use_sqlite:
        try:
            res = db.execute(text(
                "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME, ORDINAL_POSITION"
            )).fetchall()
            for t_name, c_name in res:
                col_map.setdefault(t_name, []).append(c_name)
        except Exception as e:
            logger.warning("Batch column info query failed: %s", e)

    result = []
    for real_name in all_real_names:
        table_id = _table_to_id.get(real_name)
        if table_id is None:
            continue

        if "*" not in allowed:
            if str(table_id) not in allowed and real_name not in allowed:
                continue

        if real_name in col_map:
            col_names = col_map[real_name]
            col_count = len(col_names)
        else:
            try:
                cols = inspector.get_columns(real_name)
                col_names = [c["name"] for c in cols]
                col_count = len(cols)
            except Exception as e:
                logger.warning("Column inspection failed for table %s: %s", real_name, e)
                col_names = []
                col_count = 0

        result.append({
            "id": table_id,
            "name": real_name,
            "column_count": col_count,
            "columns": col_names,
        })

    return {"tables": result}


@router.get("/{table_id}")
@router.get("/{table_id}/data")
@router.get("/tables/{table_id}/data")
@router.get("/tables/{table_id}/query")
def get_table_data(
    table_id: int,
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    search: Optional[str] = None,
    where: Optional[str] = None,
    order_by: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Fetch rows by numeric table ID (e.g. /api/v1/14). Real table name is resolved internally."""
    real_table_name = _resolve_id(table_id)

    raw_allowed = user.get("allowed_tables", ["*"])
    allowed = [str(t) for t in raw_allowed] if isinstance(raw_allowed, list) else ["*"]
    if "*" not in allowed:
        if str(table_id) not in allowed and real_table_name not in allowed:
            raise HTTPException(status_code=403, detail="Access denied to this table")

    table = reflect_table(real_table_name)
    columns = [c.name for c in table.columns]
    query = select(table)

    if search:
        search_pattern = f"%{search.strip()}%"
        conditions = [cast(col, String).ilike(search_pattern) for col in table.columns]
        if conditions:
            query = query.where(or_(*conditions))

    if where:
        cleaned_where = _clean_where(where)
        query = query.where(text(cleaned_where))

    if order_by:
        cleaned_order = order_by.strip()
        if not re.search(r";|\b(UPDATE|DELETE|INSERT|DROP|ALTER|CREATE|GRANT|TRUNCATE)\b", cleaned_order, re.IGNORECASE):
            query = query.order_by(text(cleaned_order))

    if not search and not where:
        try:
            if not settings.use_sqlite:
                total_records = db.execute(text(
                    "SELECT TABLE_ROWS FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tname"
                ), {"tname": real_table_name}).scalar()
                if total_records is None or total_records == 0:
                    total_records = db.execute(select(func.count()).select_from(table)).scalar() or 0
            else:
                total_records = db.execute(select(func.count()).select_from(table)).scalar() or 0
        except Exception as e:
            logger.error("Error executing count query: %s", e)
            total_records = 0
    else:
        try:
            total_records = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        except Exception as e:
            logger.error("Error executing count query: %s", e)
            total_records = 0

    query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)

    try:
        rows = db.execute(query).mappings().all()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query execution error: {str(e)}")

    data = []
    for r in rows:
        row_dict = {}
        for k, v in dict(r).items():
            if hasattr(v, "isoformat"):
                row_dict[k] = v.isoformat()
            elif isinstance(v, (bytes, bytearray)):
                row_dict[k] = f"<binary {len(v)}b>"
            else:
                row_dict[k] = v
        data.append(row_dict)

    return {
        "table_id": table_id,
        "table_name": real_table_name,
        "columns": columns,
        "total": total_records,
        "skip": skip,
        "limit": limit if limit is not None else "all",
        "data": data,
    }


@router.post("/tables/{table_id}/query")
def post_table_data(
    table_id: int,
    payload: TableFilterRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    POST version of table data fetch — all filters go in the JSON body.
    URL stays clean: POST /api/v1/tables/13/query
    Body: { "where": "DATE(rs_sd_start_date) >= ...", "limit": 50 }
    """
    # Reuse the GET handler logic by calling it with body values
    return get_table_data(
        table_id=table_id,
        skip=payload.skip,
        limit=payload.limit,
        search=payload.search,
        where=payload.where,
        order_by=payload.order_by,
        db=db,
        user=user,
    )



# ---------------------------------------------------------------------------
# Helper: validate & clean a WHERE clause string
# ---------------------------------------------------------------------------
def _clean_where(where: str) -> str:
    """Strip optional leading WHERE keyword and reject unsafe SQL."""
    cleaned = where.strip()
    if cleaned.upper().startswith("WHERE "):
        cleaned = cleaned[6:].strip()
    if re.search(r";|\b(UPDATE|DELETE|INSERT|DROP|ALTER|CREATE|GRANT|TRUNCATE)\b", cleaned, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Invalid characters or non-read-only commands in WHERE clause")
    return cleaned


# ---------------------------------------------------------------------------
# Summary endpoints  —  counts only, no raw rows
# ---------------------------------------------------------------------------

@router.get("/tables/{table_id}/summary")
def get_table_summary(
    table_id: int,
    where: Optional[str] = Query(None),
    group_by: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Return a count summary for the table (no raw rows).

    - **where**    – optional filter expression (same syntax as the data endpoint)
    - **group_by** – optional column / expression to group counts by

    ### Examples
    ```
    # Plain total for current month
    GET /api/v1/tables/14/summary
        ?where=rs_sd_start_date >= DATE_FORMAT(CURDATE(),'%Y-%m-01') AND rs_sd_start_date < CURDATE()

    # Grouped by status
    GET /api/v1/tables/14/summary
        ?where=rs_sd_start_date >= DATE_FORMAT(CURDATE(),'%Y-%m-01')
        &group_by=status
    ```
    """
    real_table_name = _resolve_id(table_id)

    raw_allowed = user.get("allowed_tables", ["*"])
    allowed = [str(t) for t in raw_allowed] if isinstance(raw_allowed, list) else ["*"]
    if "*" not in allowed:
        if str(table_id) not in allowed and real_table_name not in allowed:
            raise HTTPException(status_code=403, detail="Access denied to this table")

    table = reflect_table(real_table_name)

    # ── Validate group_by ────────────────────────────────────────────────────
    if group_by:
        cleaned_group = group_by.strip()
        if re.search(r";|\b(UPDATE|DELETE|INSERT|DROP|ALTER|CREATE|GRANT|TRUNCATE)\b", cleaned_group, re.IGNORECASE):
            raise HTTPException(status_code=400, detail="Invalid group_by expression")
    else:
        cleaned_group = None

    # ── Build query ──────────────────────────────────────────────────────────
    if cleaned_group:
        # literal_column() supports .label() unlike text(); needed for SQLAlchemy 2.x
        grp_col = literal_column(cleaned_group)
        query = select(
            grp_col.label("group_value"),
            func.count().label("count"),
        ).select_from(table)
    else:
        query = select(func.count().label("count")).select_from(table)

    if where:
        cleaned_where = _clean_where(where)
        query = query.where(text(cleaned_where))

    if cleaned_group:
        query = query.group_by(literal_column(cleaned_group)).order_by(literal_column(cleaned_group).asc())

    # ── Execute ──────────────────────────────────────────────────────────────
    try:
        rows = db.execute(query).mappings().all()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Summary query error: {str(e)}")

    if cleaned_group:
        breakdown = [{"group": r["group_value"], "count": r["count"]} for r in rows]
        total = sum(b["count"] for b in breakdown)
        return {
            "table_id": table_id,
            "where": where or None,
            "group_by": cleaned_group,
            "total": total,
            "breakdown": breakdown,
        }
    else:
        total = rows[0]["count"] if rows else 0
        return {
            "table_id": table_id,
            "where": where or None,
            "group_by": None,
            "total": total,
        }


@router.post("/tables/{table_id}/summary")
def post_table_summary(
    table_id: int,
    payload: TableSummaryRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    POST version of the summary endpoint (filters in JSON body instead of query params).

    Body: `{ "where": "rs_sd_start_date >= DATE_FORMAT(CURDATE(),'%Y-%m-01') AND rs_sd_start_date < CURDATE()", "group_by": "status" }`
    """
    return get_table_summary(
        table_id=table_id,
        where=payload.where,
        group_by=payload.group_by,
        db=db,
        user=user,
    )


def execute_sql_query(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Execute custom SQL SELECT query directly against the MySQL database.
    Strictly enforces read-only execution (SELECT / WITH).
    """
    sql_str = payload.sql.strip()

    if not re.match(r"^\s*(SELECT|WITH|EXPLAIN|SHOW|DESCRIBE)\b", sql_str, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="Only read-only SQL queries (SELECT, WITH, SHOW, DESCRIBE) are allowed."
        )

    forbidden = r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|GRANT|REVOKE|TRUNCATE|EXECUTE)\b"
    if re.search(forbidden, sql_str, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="Modifying operations (INSERT, UPDATE, DELETE, DROP, etc.) are strictly prohibited."
        )

    allowed = user.get("allowed_tables", ["*"])
    if "*" not in allowed:
        _build_registry()
        for real_name, tid in _table_to_id.items():
            if re.search(rf"\b{re.escape(real_name)}\b", sql_str, re.IGNORECASE):
                if str(tid) not in allowed and real_name not in allowed:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied: Not authorized to query that table."
                    )

    try:
        result = db.execute(text(sql_str))
        columns = list(result.keys()) if result.returns_rows else []
        rows = result.mappings().all() if result.returns_rows else []

        data = []
        for r in rows:
            row_dict = {}
            for k, v in dict(r).items():
                if hasattr(v, "isoformat"):
                    row_dict[k] = v.isoformat()
                elif isinstance(v, (bytes, bytearray)):
                    row_dict[k] = f"<binary {len(v)}b>"
                else:
                    row_dict[k] = v
            data.append(row_dict)

        return {
            "columns": columns,
            "row_count": len(data),
            "data": data,
        }
    except Exception as e:
        logger.error("SQL execution error: %s", e)
        raise HTTPException(status_code=400, detail=f"SQL Execution Error: {str(e)}")
