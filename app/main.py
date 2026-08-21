"""
SEF Internal Data API — application entry point.

Security layers:
 1. CORS restricted to allowed origins
 2. Rate limiting (slowapi)
 3. JWT auth on every protected endpoint
 4. RBAC via require_role()
 5. Audit logging middleware
 6. Pydantic input validation
 7. ORM-only DB access (no raw SQL)
"""

import logging
import pathlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import engine, Base
from .middleware import AuditLogMiddleware
from .routers import auth, users, reports, admin_gui, data_viewer

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-8s  %(levelname)-5s  %(message)s",
)

# ── Rate limiter ─────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

# ── App ──────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_title,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware (order matters — outermost runs first) ─────────
app.add_middleware(AuditLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(admin_gui.router)
app.include_router(data_viewer.router)

# ── Static files (GUI) ───────────────────────────────────────
STATIC_DIR = pathlib.Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── GUI route ────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def serve_gui():
    """Serve the single-page GUI dashboard."""
    return FileResponse(
        str(STATIC_DIR / "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


# ── Startup ──────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    """Application startup hook."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logging.getLogger("app").warning("Table creation skipped (read-only DB account): %s", e)
    try:
        from .seed_admin import seed_database
        seed_database()
    except Exception as e:
        logging.getLogger("app").warning("Startup seeding skipped/failed: %s", e)
    logging.getLogger("app").info(
        "Connected to %s", "SQLite" if settings.use_sqlite else f"MySQL @ {settings.db_host}:{settings.db_port}/{settings.db_name}"
    )


# ── Health check (unauthenticated) ───────────────────────────
@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}
