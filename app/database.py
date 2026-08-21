"""
SQLAlchemy engine, session factory, and Base declarative class.
Supports both SQLite (dev) and MySQL (prod) based on config.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# ── Engine kwargs vary by backend ─────────────────────────────
if settings.use_sqlite:
    engine_kwargs = {
        "connect_args": {"check_same_thread": False},
    }
else:
    engine_kwargs = {
        "pool_pre_ping": True,       # reconnect on stale connections
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,         # recycle connections every 30 min
    }

engine = create_engine(settings.database_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
