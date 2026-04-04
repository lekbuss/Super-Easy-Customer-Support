from fastapi import APIRouter

from app.rag.admin import get_stats

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/stats")
def rag_stats():
    return get_stats()
