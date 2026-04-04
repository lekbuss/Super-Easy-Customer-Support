from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.workflow import WorkflowDraftsRead, WorkflowOutcomeRead, WorkflowStartRequest
from app.services.draft_service import build_workflow_drafts
from app.services.workflow_service import approve_workflow_run, get_workflow_outcome, run_and_persist_workflow_for_ticket

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/run")
def run_workflow(payload: WorkflowStartRequest, db: Session = Depends(get_db)):
    try:
        workflow_run, result = run_and_persist_workflow_for_ticket(db=db, ticket_id=payload.ticket_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"workflow_run_id": workflow_run.id, "result": result}


@router.post("/{workflow_run_id}/approve")
def approve_workflow(workflow_run_id: int, approver: str = "dashboard_user", db: Session = Depends(get_db)):
    try:
        workflow_run = approve_workflow_run(db, workflow_run_id, approver=approver)
    except ValueError:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return {"workflow_run_id": workflow_run.id, "status": workflow_run.status.value, "next_action": workflow_run.next_action}


@router.get("/{workflow_run_id}/outcome", response_model=WorkflowOutcomeRead)
def get_workflow_outcome_endpoint(workflow_run_id: int, db: Session = Depends(get_db)):
    outcome = get_workflow_outcome(db, workflow_run_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    workflow_run, steps, approvals = outcome
    return {
        "workflow_run": workflow_run,
        "steps": steps,
        "approvals": approvals,
    }


@router.get("/{workflow_run_id}/drafts", response_model=WorkflowDraftsRead)
def get_workflow_drafts_endpoint(workflow_run_id: int, db: Session = Depends(get_db)):
    drafts = build_workflow_drafts(db, workflow_run_id)
    if drafts is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return drafts
