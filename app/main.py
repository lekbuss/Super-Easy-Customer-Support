import logging

from fastapi import FastAPI

from app.api.v1.router import router as api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, ensure_sqlite_schema

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
def startup_event():
    ensure_sqlite_schema()
    Base.metadata.create_all(bind=engine)

    try:
        from app.rag.admin import get_stats
        stats = get_stats()
        logger.info(
            "ChromaDB ready — collection='%s' documents=%d",
            stats["collection"],
            stats["document_count"],
        )
    except Exception as exc:
        logger.warning("ChromaDB stats unavailable at startup: %s", exc)
