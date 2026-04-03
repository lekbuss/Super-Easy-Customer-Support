from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import ApprovalAction, Ticket, WorkflowRun, WorkflowStatus, WorkflowStep
from app.workflows.support_workflow import run_support_workflow


def run_and_persist_workflow(
    db: Session,
    external_id: str,
    customer_email: str,
    subject: str,
    body: str,
) -> tuple[WorkflowRun, dict]:
    ticket = Ticket(
        external_id=external_id,
        customer_email=customer_email,
        subject=subject,
        body=body,
        status=WorkflowStatus.received,
    )
    db.add(ticket)
    db.flush()

    workflow_run = WorkflowRun(ticket_id=ticket.id, status=WorkflowStatus.drafting)
    db.add(workflow_run)
    db.flush()

    result = run_support_workflow(ticket.id, subject, body)
    final_status = WorkflowStatus(result["status"])

    workflow_run.status = final_status
    workflow_run.iteration_count = result["iteration"]
    workflow_run.final_decision = result["decision"]
    workflow_run.final_draft_response = result["draft_response"]
    workflow_run.final_review_notes = result["review_notes"]
    workflow_run.next_action = result["next_action"]
    workflow_run.completed_at = datetime.utcnow()

    ticket.status = final_status

    for row in result["iteration_history"]:
        db.add(
            WorkflowStep(
                workflow_run_id=workflow_run.id,
                iteration=row["iteration"],
                status="reviewing",
                decision=row["decision"],
                draft_response=row["draft_response"],
                review_notes=row["review_notes"],
                next_action="iteration_recorded",
            )
        )

    db.commit()
    db.refresh(workflow_run)
    return workflow_run, result


def approve_workflow_run(db: Session, workflow_run_id: int, approver: str, notes: str | None = None):
    workflow_run = db.get(WorkflowRun, workflow_run_id)
    if workflow_run is None:
        raise ValueError("workflow_run_not_found")

    approval = ApprovalAction(
        workflow_run_id=workflow_run_id,
        approver=approver,
        action="approved",
        notes=notes,
    )
    db.add(approval)

    workflow_run.status = WorkflowStatus.approved
    workflow_run.next_action = "ready_for_sending_stage"
    workflow_run.completed_at = datetime.utcnow()

    ticket = db.get(Ticket, workflow_run.ticket_id)
    if ticket is not None:
        ticket.status = WorkflowStatus.approved

    db.commit()
    db.refresh(workflow_run)
    return workflow_run


def get_iteration_history(db: Session, workflow_run_id: int) -> list[WorkflowStep]:
    return (
        db.query(WorkflowStep)
        .filter(WorkflowStep.workflow_run_id == workflow_run_id)
        .order_by(WorkflowStep.iteration.asc(), WorkflowStep.id.asc())
        .all()
    )
