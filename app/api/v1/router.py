from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.rag import router as rag_router
from app.api.v1.endpoints.ticket import router as ticket_router
from app.api.v1.endpoints.workflow import router as workflow_router

router = APIRouter()
router.include_router(health_router)
router.include_router(ticket_router)
router.include_router(workflow_router)
router.include_router(rag_router)
