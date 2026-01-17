"""Database connection and session management for PostgreSQL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings


# Use lazy initialization to avoid connection at import time
# This allows tests to override dependencies before database connection
_engine = None
_SessionLocal = None

Base = declarative_base()


def get_engine():
    """Get or create the database engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def get_session_local():
    """Get or create the session factory (lazy initialization)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


# Keep backward compatibility
@property
def engine():
    return get_engine()


@property
def SessionLocal():
    return get_session_local()


def get_db():
    """Dependency that provides a database session."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables. Call this on application startup."""
    Base.metadata.create_all(bind=get_engine())
