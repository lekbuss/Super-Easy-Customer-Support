from fastapi import APIRouter

from app.schemas.workflow import WorkflowStartRequest
from app.workflows.support_workflow import run_support_workflow

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/run")
def run_workflow(payload: WorkflowStartRequest):
    result = run_support_workflow(
        ticket_id=payload.ticket_id,
        subject="DocuWare support request",
        body="Customer reports indexing and retrieval mismatch in archive cabinet.",
    )
    return result
