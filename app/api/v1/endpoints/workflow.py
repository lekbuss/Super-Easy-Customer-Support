from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.workflow import WorkflowStartRequest
from app.services.workflow_service import approve_workflow_run, run_and_persist_workflow

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/run")
def run_workflow(payload: WorkflowStartRequest, db: Session = Depends(get_db)):
    workflow_run, result = run_and_persist_workflow(
        db=db,
        external_id=f"api-{payload.ticket_id}-{int(datetime.utcnow().timestamp())}",
        customer_email="customer@example.com",
        subject="DocuWare support request",
        body="Customer reports indexing and retrieval mismatch in archive cabinet.",
    )
    return {"workflow_run_id": workflow_run.id, "result": result}


@router.post("/{workflow_run_id}/approve")
def approve_workflow(workflow_run_id: int, approver: str = "dashboard_user", db: Session = Depends(get_db)):
    try:
        workflow_run = approve_workflow_run(db, workflow_run_id, approver=approver)
    except ValueError:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return {"workflow_run_id": workflow_run.id, "status": workflow_run.status.value, "next_action": workflow_run.next_action}
