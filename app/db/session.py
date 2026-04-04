from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _prepare_sqlite_path(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    sqlite_path = database_url.removeprefix("sqlite:///")
    if sqlite_path in {":memory:", ""}:
        return
    path = Path(sqlite_path)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)


DATABASE_URL = _normalize_database_url(settings.database_url)
_prepare_sqlite_path(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_sqlite_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'")
        ).fetchone()
        if table_exists is None:
            return

        columns = conn.execute(text("PRAGMA table_info(tickets)")).fetchall()
        column_names = {row[1] for row in columns}
        if "source" not in column_names:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN source VARCHAR(64) NOT NULL DEFAULT 'unknown'"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
