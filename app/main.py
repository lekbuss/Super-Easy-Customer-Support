from fastapi import FastAPI

from app.api.v1.router import router as api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, ensure_sqlite_schema

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
def startup_event():
    ensure_sqlite_schema()
    Base.metadata.create_all(bind=engine)
