import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import ApprovalAction, ReviewMemory, Ticket, WorkflowRun, WorkflowStatus, WorkflowStep
from app.services.ticket_service import create_ticket, get_ticket_by_id


def _extract_review_comment(review_notes: str | None) -> str:
    if not review_notes:
        return ""
    try:
        return json.loads(review_notes).get("review_comment", review_notes)
    except (json.JSONDecodeError, AttributeError):
        return review_notes


def _extract_key_concerns(review_notes: str | None) -> list[str]:
    if not review_notes:
        return []
    try:
        return json.loads(review_notes).get("key_concerns", [])
    except (json.JSONDecodeError, AttributeError):
        return []
from app.workflows.support_workflow import run_support_workflow


def run_and_persist_workflow_for_ticket(
    db: Session,
    ticket_id: int,
    rejection_reason: str | None = None,
) -> tuple[WorkflowRun, dict]:
    ticket = get_ticket_by_id(db, ticket_id)
    if ticket is None:
        raise ValueError("ticket_not_found")

    workflow_run = WorkflowRun(ticket_id=ticket.id, status=WorkflowStatus.drafting)
    db.add(workflow_run)
    db.flush()

    result = run_support_workflow(ticket.id, ticket.subject, ticket.body, rejection_reason=rejection_reason)
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


def run_and_persist_workflow(
    db: Session,
    external_id: str,
    customer_email: str,
    subject: str,
    body: str,
    source: str = "dashboard",
) -> tuple[WorkflowRun, dict]:
    ticket = create_ticket(
        db=db,
        external_id=external_id,
        customer_email=customer_email,
        subject=subject,
        body=body,
        source=source,
    )
    return run_and_persist_workflow_for_ticket(db=db, ticket_id=ticket.id)


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

    # Persist review data to ReviewMemory for future few-shot example enrichment
    ticket = db.get(Ticket, workflow_run.ticket_id)
    memory_payload = {
        "ticket_topic": ticket.subject if ticket else "",
        "draft_summary": (workflow_run.final_draft_response or "")[:200],
        "uchiyama_review": _extract_review_comment(workflow_run.final_review_notes),
        "decision": workflow_run.final_decision or "",
        "review_pattern": "人工承認済み事例",
        "key_concerns": _extract_key_concerns(workflow_run.final_review_notes),
    }
    db.add(ReviewMemory(
        ticket_id=workflow_run.ticket_id,
        memory_text=json.dumps(memory_payload, ensure_ascii=False),
        reviewer_action=workflow_run.final_decision or "approve",
    ))

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


def list_recent_workflow_runs(db: Session, limit: int = 20) -> list[tuple[WorkflowRun, Ticket]]:
    return (
        db.query(WorkflowRun, Ticket)
        .join(Ticket, WorkflowRun.ticket_id == Ticket.id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .limit(limit)
        .all()
    )


def get_workflow_run(db: Session, workflow_run_id: int) -> WorkflowRun | None:
    return db.get(WorkflowRun, workflow_run_id)


def get_ticket_for_workflow_run(db: Session, workflow_run: WorkflowRun) -> Ticket | None:
    return db.get(Ticket, workflow_run.ticket_id)


def get_approval_actions(db: Session, workflow_run_id: int) -> list[ApprovalAction]:
    return (
        db.query(ApprovalAction)
        .filter(ApprovalAction.workflow_run_id == workflow_run_id)
        .order_by(ApprovalAction.created_at.asc(), ApprovalAction.id.asc())
        .all()
    )


def list_workflow_runs_for_ticket(db: Session, ticket_id: int, limit: int = 30) -> list[WorkflowRun]:
    return (
        db.query(WorkflowRun)
        .filter(WorkflowRun.ticket_id == ticket_id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .limit(limit)
        .all()
    )


def get_workflow_outcome(
    db: Session,
    workflow_run_id: int,
) -> tuple[WorkflowRun, list[WorkflowStep], list[ApprovalAction]] | None:
    workflow_run = get_workflow_run(db, workflow_run_id)
    if workflow_run is None:
        return None

    steps = get_iteration_history(db, workflow_run_id)
    approvals = get_approval_actions(db, workflow_run_id)
    return workflow_run, steps, approvals


def reject_and_rerun_workflow(
    db: Session,
    workflow_run_id: int,
    reason: str,
) -> tuple[WorkflowRun, dict]:
    """Mark current run as rejected, then start a fresh run with the rejection reason."""
    workflow_run = get_workflow_run(db, workflow_run_id)
    if workflow_run is None:
        raise ValueError("workflow_run_not_found")

    ticket = db.get(Ticket, workflow_run.ticket_id)
    if ticket is None:
        raise ValueError("ticket_not_found")

    # Mark the old run as failed/escalated so it is clearly superseded
    workflow_run.next_action = f"rejected: {reason[:120]}"
    workflow_run.completed_at = datetime.utcnow()
    db.flush()

    return run_and_persist_workflow_for_ticket(
        db=db,
        ticket_id=ticket.id,
        rejection_reason=reason,
    )


def generate_inquiry_email(db: Session, workflow_run_id: int) -> dict:
    """Generate a professional English inquiry email to DocuWare tech support."""
    from app.llm.client import AnthropicClient, LLMServiceError

    workflow_run = get_workflow_run(db, workflow_run_id)
    if workflow_run is None:
        raise ValueError("workflow_run_not_found")

    ticket = db.get(Ticket, workflow_run.ticket_id)
    if ticket is None:
        raise ValueError("ticket_not_found")

    # Collect what was tried (last draft + review notes)
    steps = get_iteration_history(db, workflow_run_id)
    last_draft = steps[-1].draft_response if steps else (workflow_run.final_draft_response or "")
    last_review = _extract_review_comment(steps[-1].review_notes if steps else "") if steps else ""

    system_prompt = (
        "You are a professional technical support engineer at a DocuWare partner company in Japan. "
        "Write a concise, professional English email to DocuWare technical support requesting assistance. "
        "Output ONLY a JSON object with two keys: \"email_subject\" (string) and \"email_body\" (string). "
        "The email_body should be plain text, ready to send."
    )

    user_message = (
        f"Customer inquiry subject: {ticket.subject}\n"
        f"Customer inquiry body:\n{ticket.body.strip()[:800]}\n\n"
        f"Our attempted reply draft:\n{last_draft[:600]}\n\n"
        f"Review feedback received:\n{last_review[:400]}\n\n"
        "Please write a professional email to DocuWare technical support asking for help with this issue. "
        "Include: problem description, what we have already tried, and what we need clarified."
    )

    client = AnthropicClient()
    import json as _json
    try:
        raw = client.chat_sync(system_prompt, user_message)
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = _json.loads(text)
        return {
            "email_subject": data.get("email_subject", ""),
            "email_body": data.get("email_body", raw),
        }
    except (LLMServiceError, Exception):
        subject = f"Technical Support Request: {ticket.subject[:80]}"
        body = (
            f"Dear DocuWare Technical Support,\n\n"
            f"We are writing to request assistance with the following customer issue.\n\n"
            f"Subject: {ticket.subject}\n\n"
            f"Issue Description:\n{ticket.body.strip()[:600]}\n\n"
            "We would appreciate your guidance on how to resolve this matter.\n\n"
            "Best regards,\nTechnical Support Team"
        )
        return {"email_subject": subject, "email_body": body}
