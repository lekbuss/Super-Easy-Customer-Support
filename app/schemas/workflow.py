from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.db.models import WorkflowStatus


class WorkflowStartRequest(BaseModel):
    ticket_id: int


class WorkflowStateResponse(BaseModel):
    ticket_id: int
    status: Literal[
        "drafting",
        "reviewing",
        "revising",
        "needs_human_approval",
        "escalated",
        "failed",
    ]
    draft_response: str
    decision: Literal["approve", "revise", "escalate"] | None
    iteration: int
    needs_human_approval: bool
    escalated: bool
    escalation_reason: str | None
    next_action: str


class WorkflowRunRead(BaseModel):
    id: int
    ticket_id: int
    status: WorkflowStatus
    iteration_count: int
    final_decision: str | None
    final_draft_response: str | None
    final_review_notes: str | None
    next_action: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowStepRead(BaseModel):
    iteration: int
    status: str
    decision: str | None
    draft_response: str
    review_notes: str
    next_action: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalActionRead(BaseModel):
    approver: str
    action: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowOutcomeRead(BaseModel):
    workflow_run: WorkflowRunRead
    steps: list[WorkflowStepRead]
    approvals: list[ApprovalActionRead]


class WorkflowDraftsRead(BaseModel):
    workflow_run_id: int
    ticket_id: int
    customer_reply_draft: str | None
    vendor_escalation_draft: str | None
    internal_summary: str
