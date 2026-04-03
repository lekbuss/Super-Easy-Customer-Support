from typing import Literal

from pydantic import BaseModel


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
