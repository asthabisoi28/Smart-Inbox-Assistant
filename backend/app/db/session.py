import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

database_url = settings.get_database_url()

# Configure engine arguments based on dialect
engine_kwargs = {"echo": False}
if database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
elif "oracle" in database_url:
    # Recommended connection pool settings for Oracle
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(database_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session and ensures proper closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates all database tables defined in SQLAlchemy models."""
    # Ensure all models are imported before creating tables
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    if database_url.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN review_status VARCHAR(50) DEFAULT 'PENDING_REVIEW'"))
                conn.commit()
        except Exception:
            pass  # Column already exists
    logger.info("Database initialized and tables verified.")


def check_db_connection() -> bool:
    """Verifies active connectivity to the configured database."""
    try:
        with engine.connect() as conn:
            # Oracle supports 'SELECT 1 FROM DUAL', SQLite/Postgres supports 'SELECT 1'
            query = "SELECT 1 FROM DUAL" if "oracle" in database_url else "SELECT 1"
            conn.execute(text(query))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
